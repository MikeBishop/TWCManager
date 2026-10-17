# Task 10 report: reads cascade BLE then API, never wake (closes A6)

Status: DONE. Commit 1e02481 on vehicle-model/phase1 (base 290f7d1).
Tests: 946 passed (928 + 18 new in tests/unit/test_reads_no_wake.py: the brief's 10 verbatim, plus 8).

## What changed

- `lib/TWCManager/Vehicle/Registry/Sources.py` (new): `CHARGE_FIELDS`, `LOCATION_FIELDS`,
  `TeslaBLEReadSource` (order 0) and `TeslaAPIReadSource` (order 1) per the brief.
  - BLE: `canRead` = VIN and a `TeslaBLE` claim and policy != `api_only`. `fetch` maps location
    to `lat/lon/gpsAsOf` only (heading dropped: an unknown key would raise KeyError out of the
    cascade's observe loop), drops None values (P14) and a falsy gpsAsOf; a reply with nothing left
    returns None, not `{}` (which the cascade would read as "recorded itself" and stop short of the
    API; tesla-control omits zero-valued fields, so this is reachable); wakes + one retry only
    when `allowWake`. Observations are stamped `TeslaBLE` by the cascade (fixes Task 9 carry).
  - API: never wakes. Order: `now < car.statusDeferral` → `{}` (stored values, no request, as
    `update_vehicle_data` always did; also skips the online check) → free `car.is_awake()`;
    False → None → paid `update_vehicle_data()`; `{}` on success, None on failure.
- `TeslaAPI.py`: registers `TeslaAPIReadSource` in `__init__`; `CarApiVehicle.READ_MAX_AGE = 300`;
  new `_readFresh(field, maxAge)` shared by `update_charge` (batteryLevel, 300 s) and
  `update_location(minInterval)` (lat, maxAge = minInterval; 0 forces a fetch, P12). No
  `wakeVehicle` in either. The `syncSource` branches are gone: registry freshness replaces them.
  - Success test: a newer observation landed (`obs.at > before.at`, or none before), or age <=
    maxAge, or inside `statusDeferral` (P13). Deviation from the brief's literal formula: with
    maxAge 0, `age <= 0` is never true on a real clock, so the brief's own location tests would
    fail; the "newer observation" clause fixes that. A stale value returned after every source
    failed is still a failure.
  - `lastAPIAccessTime` is set only when a BLE observation landed during this call (as main's BLE
    path did); a cache hit does not set it (would make `ready()` skip `is_awake`). API reads set it
    in `get_car_api` as before.
  - `update_location` recomputes `atHome` on every success; gpsAge uses gpsAsOf only if that
    observation is at least as new as the lat observation (else None, as main's BLE path did when
    no fix time was reported).
  - `update_charge` sets `lastCurrentChangeTime` when `actualCurrent` changed during the read
    (the cascade observes directly, bypassing the setter).
  - `update_vehicle_data` observes `gps_as_of` only when truthy (Task 9 carry).
- `TeslaBLE.py`: after the binary check passes, registers `TeslaBLEReadSource(self, master)` on
  `VehicleRegistry.forMaster(master)`.
- CHANGELOG Architecture line added verbatim.

## Cost bound after our own write (asked for by the caller)

`noteWrite` has no callers outside the Registry package yet, so `batteryLevel` and `lat` (the
two fields these methods read) are never own-written in Phase 1: `trusted()` cannot force a
cascade for them. For any future own-written polled field, a failing source cannot become a paid
`vehicle_data` per read because, in order:
1. `statusDeferral` (>= 300 s after every successful `vehicle_data`): the API source returns `{}`
   without any request; and a success lands a newer observation, ending the cascade.
2. `is_awake()` (free `vehicles/{vin}`, cached 120 s, trusts telemetry asleep/offline): asleep →
   no paid call.
3. On a request failure, `get_car_api` → `updateCarApiLastErrorTime` → `ready()` false for the
   retry window → no request sent.
Residual gap (pre-existing): `update_vehicle_data` returning False after a 200 with drive_state or
charge_state missing sets neither deferral nor error time, so the next read pays again. Callers
are rate-bounded today (car_api_available, checkCharge cadence); worth a deferral on that path when
Phase 2 adds read callers.

## Concerns

1. Until Task 13 seeds `TeslaBLE` claims, no production vehicle has one, so BLE reads are never
   tried and every read goes to the cloud. Within the accepted "deploy after Task 11" window.
2. Telemetry (TeslaMate) cars: main's `update_location()` only recomputed `atHome`; now default
   callers (TeslaAPI.py car_api_available / applyChargeLimit paths) pass maxAge 0 and force a
   fresh read, i.e. a possible paid `vehicle_data` when the car is online. Bounded by the free
   `is_awake` (trusts telemetry asleep) and `statusDeferral` (at most one per >= 300 s per car),
   but it is new cloud traffic for TeslaMate users and Task 11 liveness will not remove it
   (maxAge 0 never consults the cache). Consider passing a small maxAge from those callers.
3. `update_charge` for a telemetry car whose batteryLevel is > 300 s old cascades until Task 11
   wires liveness (already in progress.md). TeslaMate does map battery_level -> batteryLevel
   (TeslaMateVehicle.py:63), so liveness will cover it.
4. A BLE miss costs the command timeout under `_bleLock`; `update_charge` then `update_location`
   in `car_api_available` can try BLE twice per call when it is unreachable (same as main).
5. Cosmetic: `update_location` recomputes `atHome` on cache hits too; with home unset and a stale
   fix, `is_location_home` logs its INFO line per call rather than per fetch.

## Fix round 1

Commit a2a3e24 (on 1e02481). Full suite: 952 passed (946 + 6 new; all 6 seen failing first).

1. Important (serial thread): `TWCMaster.recordVehicleVIN` no longer calls
   `TeslaAPI.vehicleIsDefinitelyHome`; it queues `{"cmd": "vehicleIsDefinitelyHome", "vin": vin}`.
   `_taskKey` dedupes that cmd per VIN (two TWCs' cars are both checked). New
   `TWCMaster.vehicleIsDefinitelyHome(vin)` delegates to the TeslaAPI module (no-op without it);
   `background_tasks_thread` dispatches the cmd to it next to `expireVehicles`. Behaviour is
   otherwise unchanged, only deferred to the background thread.
   Tests (test_twcmaster_vin_confirmation.py): recordVehicleVIN does not call the module and
   queues the task; two VINs do not collapse in the real queue (fresh queue/dedupe table, as they
   are class attributes); the master method delegates; the handler dispatch is checked from
   TWCManager.py source via `ast.get_source_segment` (the launcher can't be imported; 3.8-safe).
2. Minor 4: `_readFresh` uses `fetched = obs is not before` (each observe stores a new
   Observation; a cache hit or failed cascade returns the same object), and the BLE
   `lastAPIAccessTime` rule no longer compares `obs.at` with `time.time()`. Tests: a BLE read on an
   injected registry clock (50.0) marks the car awake; a real read stamped equal to the previous
   observation counts as fetched.

Correction to concern 2 above (per review): Task 11 liveness can remove the maxAge-0 cost for
TeslaMate cars, since `age = now - max(obs.at, liveAt)` is 0 while the feed is live, so `read()`
returns the stored value even at maxAge 0. This holds only while the latest observation's source is
TeslaMate; a `TeslaAPI`-sourced `lat` landed by `vehicle_data` on a parked car may not be displaced.
