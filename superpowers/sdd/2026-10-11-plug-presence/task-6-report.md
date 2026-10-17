# Task 6 report: discovery on wake

Worktree: scratchpad/wt-plug, branch presence/3-plug-presence (base 80a5b03).

## Commits
- 0b74afc Read before acting: a car read as unplugged or away gets nothing
- aff0d37 Plug evidence only from what a read actually said (deferred findings 1-3)

## Implemented
- `VehiclePresence.discover(vin, pluggedIn, source, inside=None, fastCharger=False) -> bool`:
  record-only, no I/O. It calls observePlugState(edge=False) only for a bool
  pluggedIn and observeLocation only for a bool inside, so None is never
  recorded as an unplug. It returns False for pluggedIn False, for fastCharger,
  or for inside False without bleReachable. Otherwise it returns True.
- TeslaBLE:
  - `get_charge_state` reports `observePlugState(vin, p, "ble", fastCharger=...)`
    through a new `_reportPlug` helper, only when pluggedIn isn't None.
  - `_readChargeLimit` was renamed to `_readChargeState`. The breaker check is
    kept, and `["chargeLimit"]` is None when it isn't valid.
  - `applyChargeLimit` gates `limit != -1` (per-VIN and policy-wide) after the
    read. The plug value comes from the BLE read, or from `telemetryPluggedIn`
    with source "telemetry" when telemetry answered the limit. A car found not
    here gets an INFO log line, `attempted_count -= 1; skipped_count += 1`, and
    `_stopTryingToApplyLimit` stays unset. An all-skipped apply returns True,
    so VehiclePriority doesn't fall through to the Fleet API for a car that
    was just read as unplugged.
  - A start answered "could not execute command: disconnected" reports
    `observePlugState(vin, False, "ble")`.
- TeslaAPI:
  - `CarApiVehicle.lastVehicleDataFetch` and `lastChargeRead` (monotonic) are
    stamped on every successful `update_vehicle_data`. `lastChargeRead` is
    also stamped on the BLE path of `update_charge`. `update_vehicle_data`
    reports `observePlugState(vin, plugged, "api", fastCharger=...)` from this
    read's `charging_state`.
  - `TeslaAPI._discover(vehicle, before)` is shared by both gates:
    - plugged comes from chargingState, but only if the charge state was read
      in this call (or a telemetry feed is live);
    - inside and fastCharger count only if vehicle_data was fetched in this
      call;
    - no extra update_location call is made.
  - `applyChargeLimit` puts the gate after both update_charge calls and before
    decideChargeLimit. Nothing is saved or settled, and a `notHere` flag makes
    the return "success", so there is no channel fallthrough.
  - `car_api_charge` gates starts only. The gate sits after the atHome block
    and before the Disconnected/Complete skip, and sets
    stopAskingToStartCharging the same way the skips next to it do.
- `PresenceSources.chargingStatePlugged(state)` maps Disconnected to False;
  missing, non-string, "", Unknown and SNA to None; any other state to True.
  `update_vehicle_data`, the gates, apiSource and blePluggedIn all use it.
- Telemetry `_reportPlug`: the first bool value is reported as
  `observeTelemetryPlug(vin, v, edge=False)`, a change with `edge=True`, and
  a repeat not at all.

## Deferred fixes (commit aff0d37)
1. `blePluggedIn`: latch/cable checks first, then the charging state goes
   through chargingStatePlugged. Unknown, SNA, `{}` and "Unknown" now give
   None.
2. `apiSource` returns {} if `lastVehicleDataFetch` didn't change, and reads
   plug and fast-charger evidence from `vehicle.lastChargeState`, the raw
   charge_state dict of this fetch. A field the read lacked is never filled
   from cache.
3. `WEAK_PLUG_MAX_AGE = 3600`. `_reapplyWeakPlugged`, the only path that
   promotes an old weak record, refuses a weak plugged record older than this
   unless live telemetry currently says plugged. `runPass` now also runs the
   `_pluggedInFor` lookup, without the lock, for VINs with
   contact-True/location-True observations. `_inside` doesn't age, because a
   parked car's last fix is legitimately old. Both choices are documented at
   the constant.

## Tests (TDD)
- RED (main): 13 new or changed tests failed as expected: no `discover`, no
  plug reports, set-limit sent to an unplugged car, a POST to a Fleet car
  that was found away, a supercharger start not blocked, and the telemetry
  edge semantics. `test_ble_restore_is_never_gated` and
  `test_presumed_plugged_car_on_the_fleet_path_gets_the_limit` passed from the
  start, as positive controls.
- GREEN: 1042 passed.
- RED (deferred): 11 failed: blePluggedIn x4, apiSource x4, the
  update_vehicle_data lastChargeState test, and weak-age x2. GREEN: 1052
  passed (full suite, `tests/unit`).
- The brief's 11 named tests are present. "DEPARTING" is asserted as
  not_home, with onDeparting run. Extra tests: discover with BLE reach /
  unknown / record-only, live-telemetry re-assert, fresh weak plug.
- The old `test_plugged_in_changes_are_pushed_to_presence` was replaced by
  the two new telemetry tests. `test_an_odd_plugged_in_payload...` was
  updated: after an unknown value, the next value is a read (edge=False).
  The FakeVehicle in test_presence_sources gained
  lastVehicleDataFetch/lastChargeState.
- Black: all touched lib files and the clean test files were reformatted.
  test_teslaapi_presence.py and test_teslable_presence.py weren't clean
  before and weren't reformatted; the new hunks are written in black style.

## Files
lib/TWCManager/VehiclePresence.py, lib/TWCManager/Vehicle/TeslaBLE.py,
lib/TWCManager/Vehicle/TeslaAPI.py, lib/TWCManager/Vehicle/Telemetry.py,
lib/TWCManager/PresenceSources.py; tests/unit/test_vehicle_presence.py,
test_teslable_presence.py, test_teslaapi_presence.py,
test_telemetry_timers.py, test_presence_sources.py.

## Self-review / deviations
- `update_vehicle_data` doesn't report "Unknown"/"SNA" as plugged. The brief
  said to report whenever charging_state is present; the same false-evidence
  argument as finding 1 applies.
- In TeslaAPI, plugged only counts from a read made in this call. The brief
  derives it from chargingState after update_charge, but a deferred
  update_vehicle_data returns True with cached values. Without this guard, a
  stale "Disconnected" would block an arrival apply until the deferral ran
  out.
- Double reporting is expected and harmless: bleSource/apiSource call reads
  that now report themselves, and `_applyEvidence` reports again. The same
  applies to the BLE read followed by discover.

## Concerns
- `discover(vin, False, "api"/"telemetry")` returns False even when a TWC
  currently names the car. The tracker correctly ignores that weak unplug and
  presence stays HOME, but the apply is skipped and not settled, so it
  retries every policy cycle (one Fleet read a minute) until the API or
  telemetry catches up. It heals itself, but costs reads in that window.
- A BLE strong "plugged" read with fastChargerPresent True still makes the car
  HOME in the tracker (`_applyPlugged` ignores fastCharger for strong
  sources), even though discover returns False. That can't happen in practice
  because BLE is out of range at a supercharger, but the two disagree.
- In car_api_charge, a supercharger car gets stopAskingToStartCharging until
  the next stop cycle. If it's presumed and the location says inside (home
  radius set wide), only the fast_charger flag keeps it out.
- Fleet path with a BLE fallback read: if TeslaAPI.update_charge takes its
  BLE branch, chargingState comes from the BLE enum alone. "Disconnected"
  with the latch Engaged is plugged by blePluggedIn, but `_discover` reads it
  as unplugged. Presence stays correct, because the strong BLE "plugged" wins
  inside the hold, but the apply is skipped and retried. The path is narrow
  and heals itself. To fix it, stash the BLE read's pluggedIn on the vehicle
  and prefer it.
- If `tracker.discover` raised in TeslaBLE's loop, the outer except would
  leave attempted_count incremented. An all-skipped apply could then return
  False and fall through to the Fleet API. discover can't realistically raise.

## Post-review touch
After the advisor review, `test_presumed_plugged_car_on_the_fleet_path_gets_the_limit`
was tightened to `state == "home"`, and the change was squashed into
0b74afc. The full suite gives 1052 passed.

## Fix round 1 (review task-6-review.md), commit 66e1038
1. Evidence order in `discover`: fastCharger still returns False. A strong
   source (ble/twc) reading unplugged still returns False. A weak source
   reading unplugged, or inside False without BLE reach, now returns True
   when `vin in _twcVinsNow()` (looked up without the lock, and only when
   it would otherwise refuse) or when `_strongWithinHold(vin, True)`
   (checked under the lock). These are the same cases `_applyUnplugged`
   ignores. The observations are still recorded.
   Tests:
   - VehiclePresence: TWC names V1, so api unplugged, telemetry outside and
     ble unplugged give True / True / False.
   - VehiclePresence: a BLE plug 60 s ago plus a telemetry unplug gives True
     and the state stays HOME; after the hold it gives False.
   - TeslaAPI: TWC names VIN1 and the Fleet read says Disconnected, so 70 is
     sent.
2. Fail closed:
   - TeslaBLE's gate wraps discover. If it raises, the apply logs a WARNING
     naming the exception type only (no token, no message), sends nothing,
     counts the car as skipped and leaves it unsettled.
   - TeslaAPI._discover returns False with a WARNING. So applyChargeLimit
     sends nothing (notHere, so no channel fallthrough), and a start is
     skipped.
   - Tests cover both paths.
RED: 5 failed. GREEN: the covering files give 240 passed, and the full suite
gives 1057 passed. Black was run on the touched lib files and
test_vehicle_presence.py. The two test files that weren't clean have no new
black hunks (still the 7 that were there before).
Left deferred, as ruled: the other minors from the review.
Side effect: in car_api_charge, a failing discover also sets
stopAskingToStartCharging until the next stop cycle. That is fail-closed and
consistent with the skips next to it.
