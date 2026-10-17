# Final whole-branch review: fix/vehicle-presence (3574692..32bd76b)

Reviewer: Fable 5.1 (self-reviewed). Read-only. Reviewed in passes: spec in
full; ledger; the lib diff file by file; the surrounding unchanged code the
diff depends on (queue internals, TWCMaster normal-limit helpers and init
order, Policy.enforcePolicy, TWCSlave stop/start block, TeslaAPI read/wake
paths, TeslaBLE lock decorator and applyChargeLimit body, Telemetry push);
test list and queue/handler/presence test names. Ran the suite: 669 passed,
1 pre-existing warning; black clean.

## Strengths

- VehiclePresence.py is a clean, small state machine. The lock discipline the
  ledger demanded actually holds: observers take only `_lock` and set the
  event; `runPass` snapshots under the lock, releases it before every source
  call, probe and handler; `knownVehicles()` is called with the lock
  released. The only cross-thread order is `_bleLock -> presence._lock`
  (TeslaBLE `_reportContact` under `@_serialized`), and presence never
  enters BLE while holding its own lock. No cycle with
  `backgroundTasksLock` either: `recordVehicleVIN` does not hold it, and
  handlers call `queue_background_task` only without the presence lock.
- No presence source wakes a car. `probePresence` runs only
  `body-controller-state`; the BLE limit read is gated on the probe's awake
  flag; `apiSource` gates on the vehicle-list state before `vehicle_data`;
  `get_car_api` does not wake; `ready()`/`is_awake()` only read state. The
  remote-only restore goes `update_charge(allowBle=False)` so no BLE wake
  fallback is reachable from a departure.
- The (cmd, vin) queue keying, `cancel()`, `cancelStopCarsCharging(vin)`
  and stop-cancels-start are straightforward and tested, including
  "running entry is left alone".
- TeslaAPI.applyChargeLimit is much simpler than before and now returns a
  real "success"/"error" so VehiclePriority's fallback is meaningful.
- Migration of chargeLimits ID -> VIN happens at the first moment both keys
  are known (addVehicle), is idempotent, and deletes a stale ID entry when
  a VIN entry already exists. BLE installs were already VIN-keyed.
- Good defensive handling in the handlers (`hasRemoteChannel` token check,
  departure suppressed on hand-set limit, restore never replayed) and in
  `_probe` (exception/non-dict results are no-answers).
- The install-matrix reasoning in the spec is reflected: HA is only an
  arrival channel, BLE-only logs the undeliverable restore, Fleet-only
  probes only online cars.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **Policy-wide TeslaAPI apply commands away cars in TeslaMate + API-channel installs (regression vs base).**
   `lib/TWCManager/Vehicle/TeslaAPI.py:1005-1009`. The vin=None loop gates on
   `vehicle.atHome` and then goes straight to `update_charge()` and the
   command. For a telemetry-synced vehicle (`syncSource != "TeslaAPI"`)
   `atHome` is only ever refreshed by `update_location()`'s else-branch
   (`TeslaAPI.py:1845-1848`), which this path no longer calls; the only
   remaining callers are `car_api_charge` (start/stop commands) and
   `vehicleIsDefinitelyHome`. `Telemetry._reportLocation` tells presence but
   does not touch `vehicle.atHome`. So after a car leaves, TeslaAPI still
   "believes" it is home until the next charge start/stop command, and every
   policy limit change (`limit != lastApplied` clears `stopTryingToApplyLimit`
   at :960-963) is sent to the away car over the Fleet API, waking it when
   the limit rose (`needToWake` -> `car_api_available(applyLimit=True)`).
   The base code called `vehicle.update_location()` in the loop and treated
   `not vehicle.atHome` as "departed, skip". The live box (BLE channel) is
   unaffected; `api_only`/`prefer_api` with TeslaMate, or BLE-unreachable
   fallback to API, is. Fix (either, both is fine): (a) in
   `Telemetry._reportLocation` also set `vehicle.atHome = atHome` (and
   `lat/lon`) so TeslaAPI's view stays coherent for every caller; (b) in the
   vin=None loop, before the atHome gate, `if vehicle.syncSource != "TeslaAPI":
   vehicle.update_location()` (no I/O for sync vehicles). Consulting
   `master.vehiclePresence.state(vehicle.VIN) == AWAY` is also reasonable
   but couples TeslaAPI back to presence.

2. **Unbounded `_observations` growth when the presence thread is not running.**
   `lib/TWCManager/VehiclePresence.py:148-152` (and :137-146). By design
   (spec Lifecycle) observers record when `fakeMaster != 1`, but nothing ever
   drains the list. TeslaMateVehicle is loaded regardless of `fakeMaster`
   (TWCManager.py:674 loop has no mode gate) and pushes a lat and a lon
   message per position change, each appending a tuple. In a slave/sniffer
   install with TeslaMate this grows forever (thousands of entries per hour
   of driving). Also `_due[None]` grows per HTTP nominate. Low urgency (rare
   configuration, slow), trivial fix: drop observations when
   `self._thread is None` (never started) or collapse per VIN / cap the
   list. If you keep "record even when not started", bound it.

3. **No test drives the depart-then-return cycle through a real queue.**
   (Ledger Task 7 Minor, promoted.) The branch's reason to exist is the
   depart/return cycle, and the one spec guarantee that depends on the
   queue's behaviour, "a pending restore is replaced by the arrival apply
   under the same key" (spec Departure step 5), is only covered indirectly
   (`test_apply_charge_limit_latest_wins`, `..._per_vin_does_not_merge_with_policy_wide`).
   Nothing exercises `VehiclePresence` with the real handlers, a real
   `VehicleCommandQueue` (with a stub module gated by an Event so commands
   stay pending) and a transition HOME -> AWAY -> HOME, asserting the module
   received exactly one `applyChargeLimit(limit=policy, vin=X)` and no
   `-1`. Such a test is cheap given the existing fixtures and would also
   have surfaced Minor 1 below.

### Minor (Nice to Have)

1. **Queue replace-in-place keeps the old position, so a refreshed policy-wide apply can run before an older per-VIN apply.**
   `lib/TWCManager/VehicleCommandQueue.py:88-89`: `table[key] = ...` on an
   existing key keeps the OrderedDict position. Sequence while the worker is
   busy: policy apply 50 pending (pos 1), arrival apply X=50 (pos 2), policy
   changes to 80 and `put` overwrites pos 1 -> worker sends 80 to all, then
   the stale 50 to X. Self-heals on the next `enforcePolicy` loop (it
   re-queues every iteration, Policy.py:326-327 from the loop at :247, and the per-VIN dedupe sees
   50 != 80), so bounded to one policy cycle. If you want it exact:
   `table.move_to_end(key)` on replace, or have the per-VIN task read
   `master.lastChargeLimitApplied` at execution time rather than at handler
   time (`PresenceHandlers.py:55-59`).

2. **Arrival before the first policy evaluation restores instead of applying.**
   `lib/TWCManager/PresenceHandlers.py:55`: `master.lastChargeLimitApplied
   or -1` turns the initial `0` (Policy has not run) into a restore. At
   startup, the first heartbeat's power-start nominates (often `None` since
   `currentVIN` is empty), every reachable car goes unknown -> home, and if
   the handler wins the race against `Policy._run`, TeslaBLE restores and
   `removeNormalChargeLimit`s each car; Policy's apply then saves
   `outside = target_limit` (TeslaBLE.py:818-822, pre-existing), so the real
   normal limit is lost until the user sets it again. Pre-existing: the old
   `checkArrival` used the same `!= 0 else -1`. Cheap improvement: treat
   `0` as "policy not evaluated yet; skip" (Policy writes -1 when it has no
   limit, so 0 is unambiguous).

3. **TeslaMate publishes latitude and longitude as separate messages; `_reportLocation` fires on each.**
   `lib/TWCManager/Vehicle/Telemetry.py:174-175, 182-194`. The first of the
   pair evaluates (new lat, old lon). At the geofence boundary this can
   produce an extra away/home flip inside one pass; the handlers then queue
   restore + apply (+ restore) which coalesce under one key, so the net
   effect is a spurious command or two at the crossing. Spec-compliant
   ("once both are valid"). If it shows up live, debounce by only reporting
   when both coordinates changed within a short window.

4. **`cancelStopCarsCharging("")` cancels every pending stop.**
   `lib/TWCManager/TWCMaster.py:175-181` with `TWCSlave.py:1090`. A slave
   that cannot read its VIN cancels another car's VIN-specific stop whenever
   it offers amps. Matches the pre-#667 "cancel all" behaviour, so not a
   regression, but the per-VIN cancel was the point. Consider cancelling only
   `vin is None` stops when the caller's VIN is unknown.

5. **nominate() does not dedupe due times (ledger Task 8).** Re-judged:
   stays Minor. `_due` entries expire within 45 min, `_timeUntilNextDue` is
   O(n) over a few thousand floats at worst, and the 60 s rate limit caps
   probes at one per VIN per minute. The real cost of a Gen2 state-00 flap
   is that an unreachable car gets probed every minute for 45 min (15 s BLE
   lock hold each) instead of 3 times; the away rule has long since fired so
   nothing changes. Cheap mitigation: round due times to the second or skip a
   delay whose due time is within a few seconds of an existing one.

6. **`stopAskingToStartCharging` now cleared only on a limit increase (ledger Task 3).**
   Re-judged: stays Minor. The old clears that are gone were "any limit
   change for saved vehicles" (a decrease never needs a start command) and
   "on checkArrival" (which only fired once current was already flowing).
   Policy.py:271-274 clears on every policy change and TWCSlave.py:606-616
   clears on any car drawing >= 1 A, which covers the cases that matter.
   Recommendation: also clear it in `TeslaAPI.resetChargeLimitState`
   (`TeslaAPI.py:1501-1506`), which restores the old "has arrived" semantics
   at no cost and removes the one residual gap (car returns with the flag set
   from a completed charge, then needs an API start under the same policy).

7. **`probePresence` calls `sendPrivateKey` outside the try/finally.**
   `lib/TWCManager/Vehicle/TeslaBLE.py:1002`. If it raises, no
   `_ensure_pipe_closed` and no `_reportContact`. Same shape as
   `_fetch_state_locked` (pre-existing), so consistent; mention only.

8. **`apiSource` issues one vehicle-list GET per VIN per pass.**
   `lib/TWCManager/PresenceSources.py:97`. A `None` nomination with N API
   vehicles is N list GETs plus N `vehicle_data` GETs (ledger Task 6 parked).
   Cache the list result per `runPass` if Fleet API cost matters.

9. **`_markBLEProven` mutates `settings["Vehicles"]` from the BLE caller's thread under `_bleLock`.**
   `TeslaBLE.py:205-225`. Same class of race as `recordVehicleVIN` versus the
   background `saveSettings` json dump (dict changed size during iteration if
   a new VIN entry is inserted mid-dump). Only inserts for VINs not already in
   settings, which the probe and state paths exclude; `_sendCommand_internal`
   can still insert for an ad-hoc VIN. Pre-existing pattern; noting it.

10. Ledger-parked test minors (brittle source-inspection tests in
    test_teslaapi_presence.py / lifecycle tests; `<= 1` assertion in
    `test_unsaved_at_home_car_is_read_once`) stand as Minor.

## Challenge of ledger rulings

None of the rulings causes a defect. Two are worth restating because they
bear on the findings above:

- Task 3 ruling "vin=None skips away cars before update_charge" is correct
  for arrival (presence owns it) but assumed `vehicle.atHome` stays fresh
  for departure; it does not for telemetry-synced vehicles (Important 1).
- Task 6 `bleProven` ruling: verified `_reportContact` sets it on any
  successful BLE contact and `bleSource` only counts failures when set. The
  documented upgrade cost stands: an enrolled BLE car cannot be declared
  away by BLE alone until its first successful contact after upgrade, which
  the first policy-wide BLE apply provides.

## Spec / behaviour-matrix check

- BLE-only (no token): sources = ble (telemetry/api return None). Arrival on
  probe success or any BLE contact; away after 2 failed probes; departure
  logs "no remote channel" (hasRemoteChannel false without token). OK.
- Fleet-only: apiSource only when the list says online; departure restore via
  API; policy-wide apply gate uses `vehicle.atHome`, refreshed by the probe's
  `update_vehicle_data`. OK, with the known "asleep before the +45 probe"
  limitation the spec accepts.
- TeslaMate + BLE (live box, `ble_only`): telemetry decides; BLE failures do
  not count while telemetry is live; arrival resets BLE dedupe and sends the
  per-VIN apply, which is the incident fix. No restore (documented). OK.
- TeslaMate + API channel: Important 1.
- HomeAssistant: arrival channel only; `vin` filter on `v.vin`; returns
  "error" when nothing processed for a VIN so fallback works. HA-only installs
  have no presence source, same as before in effect because HA has no dedupe
  and the periodic policy apply reaches it. OK.
- Upgrade: ID-keyed chargeLimits migrate at addVehicle; `getNormalChargeLimit`
  str()s keys; no path reads by VIN before the vehicle object exists. OK.
- Lifecycle: start after queue start under `fakeMaster == 1`; stop first in
  shutdown. OK.
- Removals: checkArrival/checkDeparture branches gone; HTTP endpoints
  nominate and return 202. OK.

## Recommendations

- Fix Important 1 in Telemetry (set `vehicle.atHome`) so every TeslaAPI
  caller benefits, and add a test: telemetry departure then policy-wide
  `applyChargeLimit(vin=None)` must not call `apply_charge_limit` on that
  vehicle.
- Bound `_observations` and add the real-queue depart/return test
  (Important 2, 3).
- Consider Minor 2 and 6 as one-liners in this branch; the rest can wait
  for live results.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The design is implemented faithfully, the locking and
no-wake invariants hold on inspection, and the incident path is fixed. One
behavioural regression remains for TeslaMate installs that use the Fleet
API as a command channel (policy limit changes reach away cars), plus an
unbounded list in non-master modes and a missing integration test; all
three are small, contained fixes.
