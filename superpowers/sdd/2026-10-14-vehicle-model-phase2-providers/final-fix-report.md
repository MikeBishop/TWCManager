# Final fix wave report: vehicle-model Phase 2

Branch `vehicle-model/phase2`. Base was b72c79c and HEAD is now 940c1c2, eight commits on top. The worktree is `scratchpad/wt-vm2`.
Full suite, capped (`tests --ignore=tests/API --ignore=tests/integration`): **1309 passed, 1 xfailed** (1289 at b72c79c, plus 20 new tests). Last run was at 69343f2; 940c1c2 changes only the CHANGELOG.

| Commit | Finding |
|---|---|
| 0ec5853 | C1, plus the audit fixes |
| 69343f2 | C1 audit: Fleet's wake hold read as failure |
| 3458ef0 | I1 |
| 1430ab3 | M1 |
| b9d0713 | M3 |
| 25a451b | Deferred: lost controller coverage |
| 03537f3, 940c1c2 | M2 (docs and CHANGELOG) |

## C1: a Fleet success or skip reached Home Assistant (0ec5853)

### Fix

These are the lib changes:

- `TeslaAPI.applyChargeLimit` returns `"success"` at the end of its pass, after the `checkArrival` refresh.
- The audit found the same paid fall-through on both 60 s throttles:
  - `TeslaAPI.applyChargeLimit`'s non-arrival throttle returned `"error"`.
  - `TeslaAPI.car_api_charge`'s start/stop throttle also returned `"error"`.
  - Both now return `"skipped"`, which is truthy and not `"error"`, so the walk ends there.
  - The `car_api_charge` case was the worse one:
    - `TWCSlave.py:582` calls `startCarsCharging` on every heartbeat while a plugged car draws nothing.
    - Fleet sends once a minute. Every queued `charge` in between got `"error"` and went on to `HomeAssistant.car_api_charge`.
    - HA has its own 10 s throttle and sends `switch.turn_on` whenever its stale cache says the car is not charging. That could mean up to about 6 billed HA calls per Fleet call.
- `TeslaAPI.updateChargeAtHome` returns `bool(self.carApiVehicles)`. When it holds cars the walk ends there; when it holds none, HA still refreshes. Before, the façade called it twice (2 attempts), because None read as failure.
- `HomeAssistant.updateChargeAtHome` returns True.
- The façade comment now states the rule: any truthy return except `"error"` ends the walk.

### Follow-up fix: the wake hold (69343f2)

The final advisor pass caught a third C1-class path.

- `car_api_available()` returns False both on a failure and while it holds off waking a sleeping car on purpose:
  - the pre-wake hold: `wakeDelayMins`, 3 minutes by default;
  - the 30-minute wait after a wake that left the car asleep.
- On Fleet+HA, a sleeping car that had just plugged in had its start request queued on every heartbeat.
- `car_api_charge` returned `"error"`, so `HomeAssistant.car_api_charge` turned the charge switch on every 10 s. That was billed, and it woke the car the hold meant to leave asleep.
- `applyChargeLimit(applyLimit=True)` had the same shape.

Fix: a new `TeslaAPI._unavailableResult()`.

- It returns `"skipped"` when all of these hold:
  - a command slot is usable;
  - a read slot is usable;
  - the vehicle list is loaded;
  - `getCarApiRetryRemaining()` is 0.
- In that state only the hold windows return False. I read every `return False` in `car_api_available`: a wake whose state is `"error"` sets the error time, and a wake that reports asleep or offline sets the 30-minute wait.
- Anything else stays `"error"`: no token, no list, or the error backoff.

Tests:

- `test_the_pre_wake_hold_is_not_a_failure`: a real TeslaAPI with a home car that is asleep. It asserts the hold began, that HA gets neither the start nor the limit, and that there is no HTTP.
- Fail-before: `assert 'error' not in (None, False, 'error')`.
- `test_a_failed_fleet_start_still_falls_to_ha` now drives the real error backoff (`updateCarApiLastErrorTime`), not a mocked `car_api_available`. It pins the failure case only.

### Tests

New file `tests/unit/test_vehicle_priority_returns.py`. It drives the real `TeslaAPI` methods, with only the `car_api_available` guard patched where needed, and uses `requests_mock` to assert no HTTP. A real `FleetAPI`/`OwnerAPI` provider pair is followed by an HA mock provider:

- `test_a_none_return_is_a_failure_and_the_walk_continues`: a façade walk with a None-returning module.
- `test_teslaapi_apply_charge_limit_returns_success`
- `test_ha_is_not_reached_after_a_fleet_apply_charge_limit` (C1)
- `test_throttled_apply_charge_limit_is_not_a_failure`
- `test_throttled_start_is_not_a_failure`
- `test_a_failed_fleet_start_still_falls_to_ha`: a real failure still falls through, as ruled.
- `test_update_charge_at_home_ends_at_teslaapi_when_it_holds_cars`
- `test_update_charge_at_home_reaches_ha_when_teslaapi_holds_no_car`
- `test_home_assistant_update_charge_at_home_returns_true`

### Fail-before (before the lib edit): 7 failed, 2 passed

The 2 that passed pin existing behaviour.

```
assert api.applyChargeLimit(80, checkArrival=True) == "success"   ->  assert None == 'success'
assert ha.applyChargeLimit.call_count == 0                         ->  assert 1 == 0
  (log: FleetAPI.applyChargeLimit() failed after 2 attempts, trying next provider)
assert api.applyChargeLimit(80) not in (None, False, "error")     ->  'error'
assert api.car_api_charge({"charge": True}) not in (...)           ->  'error'
car.update_charge.call_count == 1 and ha...call_count == 0          ->  (2 == 1)
  (log: OwnerAPI.updateChargeAtHome() failed after 2 attempts, trying next provider)
api.updateChargeAtHome() is False                                   ->  None is False
ha.updateChargeAtHome() is True                                     ->  None is True
```

### Audit: every façade-walked method on every module that can be walked

Modules a walk can reach (`Provider.module` not None): TeslaBLE, TeslaAPI (OwnerAPI and FleetAPI share it and it is walked once), and HomeAssistant. Gen2TWC, Gen3TWC and the telemetry providers have no module.

Callers that actually walk the façade:

- `TWCManager.py:333/335/342`: `applyChargeLimit` and `updateChargeAtHome`.
- `VehicleCommandQueue._DISPATCH`: `car_api_charge`, `applyChargeLimit` and `setChargeRate`.
- `setAmps`, a real method that goes through `order.dispatch`.

`startCharging`, `stopCharging` and `wakeVehicle` are in `COMMAND_METHODS`, but nothing calls them on the façade. Wake goes through `debugCommand` → `Provider.wake`.

| Method | Module | Success values | Failure values | Fixed? |
|---|---|---|---|---|
| car_api_charge | TeslaAPI | `"success"` (also when every car is skipped) | `"error"`: read-only, car_api_available False on a real failure (no slot, no list, error backoff), update/locate failed, send failed, VCP required | Throttle `"error"` → `"skipped"`, wake hold `"error"` → `"skipped"` (**fixed**) |
| car_api_charge | TeslaBLE | True (also True when every car is skipped: "already in desired state") | False | OK |
| car_api_charge | HomeAssistant | `"success"` | `"error"` (10 s throttle, unavailable, unknown VIN, no switch, service failed) | OK (last in the order) |
| applyChargeLimit | TeslaAPI | **None** → `"success"` | `"error"`: read-only, limit out of range, car_api_available False on a real failure | **Fixed**: success; throttle and wake hold `"error"` → `"skipped"` |
| applyChargeLimit | TeslaBLE | True (also when every car is skipped) | False | OK |
| applyChargeLimit | HomeAssistant | `"success"` | `"error"` | OK |
| setChargeRate | TeslaAPI | True (skip-repeat); response dict (sent) | False (guards, request/JSON error) | **Deliberately left**: a *rejected* send returns a truthy dict, read as success (see below) |
| setChargeRate | TeslaBLE | True | False | OK |
| setChargeRate | HomeAssistant | True (sent, or skipped: not connected / already at rate) | False | OK |
| updateChargeAtHome | TeslaAPI | **None** → True when it holds cars | → False when it holds none | **Fixed** |
| updateChargeAtHome | HomeAssistant | **None** → True | none | **Fixed** |
| updateChargeAtHome | TeslaBLE | n/a (no such method, skipped by `hasattr`) | n/a | n/a |
| startCharging / stopCharging / wakeVehicle | all | BLE bool; TeslaAPI wake returns dict/False | | N/A: no façade caller |
| setAmps (dispatch) | TeslaBLEProvider | `bool(ble.setChargeRate)` | | OK |
| setAmps (dispatch) | FleetAPIProvider | `bool(carapi.setChargeRate)`: True even when rejected | | Left (same reasoning as setChargeRate) |
| setAmps (dispatch) | HomeAssistantProvider | `bool(ha.setChargeRate)` | | OK |
| wake (debugCommand) | TeslaBLEProvider / FleetAPIProvider | bool / `bool(dict)`: True even on `"response": None` | | Left: user-initiated, one attempt, last paid provider anyway |

Why `TeslaAPI.setChargeRate` was left alone (after an advisor reconcile):

- Making a rejection return False would make the façade spend its second Fleet attempt, a second paid call that is useless against an asleep car, and then reach HA.
- That is a higher paid frequency than 8e07669 on the busiest path (mode-3 `_queueChargeRate`).
- The `TWCSlave` raise callback (`result is not False`) also reads a rejected dict as raised. That was already the case at 8e07669.

Consequence to record: a broadcast `applyChargeLimit` or `car_api_charge` now stops at TeslaAPI when it succeeds or skips. A car that only HA holds gets no broadcast limit or start in that case. That matches 8e07669, where HA was never walked, and the ruling that HA is reached only after Fleet has failed.

## I1: idle Gen2 minimum zeroed on the wire (3458ef0)

### Fix

- `Gen2TWC.minAmps` is now `self.minAmpsToOffer()`.
- `Gen2TWC.minAmpsToOffer()` returns the `controller.Gen2TWCs.ranges.<twcid>.minAmps` override when one is set, never below `minAmpsTWCSupports`. Otherwise it returns `TWCSlave.minAmpsToOffer()`, which is `max(minAmpsPerTWC, minAmpsTWCSupports)`.
- The heartbeat already compares against `self.minAmpsToOffer()`, so `point.minPower` is now what goes on the wire, with or without an override.
- The mode-3 floor `max(6, slave.minAmpsToOffer())` is unchanged without an override. With an override it follows it, by design.

### Tests

New file `tests/unit/test_gen2_idle_minimum.py`. It uses a real `TWCMaster`, `Gen2TWC`, `VehicleEndpoints` and the real `receive_slave_heartbeat` + `send_master_heartbeat`, and reads the wire offer from the interface's `send`:

- `test_idle_twc_is_offered_min_amps_per_twc_on_the_wire` (minAmpsPerTWC 12):
  - distributor target 12;
  - `point.minPower == 12 A`;
  - every wire offer > 0 over 10 heartbeats with the spike workaround on;
  - exactly 12 every heartbeat with spikes off.
- `test_range_override_is_what_the_heartbeat_sends` (override 8 below minAmpsPerTWC 12): target 8, minPower 8 A, wire 8.
- `test_override_never_goes_below_what_the_twc_supports`
- `test_min_amps_is_min_amps_to_offer_without_an_override`
- `test_idle_minimum_does_not_starve_a_charging_twc`:
  - a 40 A feed gives (32, 0);
  - a 50 A feed gives (32, 12);
  - the charging point keeps its allocation.

Three asserts in `test_gen2twc_provider.py` that pinned the old `minAmps = minAmpsTWCSupports` (5 or 1 A under minAmpsPerTWC 6) were updated. The mode-3 parametrised test still asserts `(6, 32)` for every case.

### Fail-before: 5 failed

```
s._evseTargetAmps == 12              -> 6.0 == 12
s.minAmps == 8 and s.minAmpsToOffer() == 8 -> (8 == 8 and 12 == 8)
s.minAmps == 6 (override 2)          -> 2 == 6
s.minAmps == 12                      -> 6 == 12
chargingAndIdle(40) == (32, 0)       -> (32.0, 6.0)
```

The reviewer's probe, run on the unfixed code, shows the wire: `minAmps 12 -> (target 6.0, lastAmpsOffered 0.0, cmd 5, wire 0.0)`.

## M1: stale registry chargingState made a merged point want power (1430ab3)

### Fix

`ChargingPoint.wantsToCharge` is now `any(e.wantsToCharge for e in self._preferLocal())`. When the point has a local member, the TWC's report decides, as at 8e07669. `isCharging` is unchanged.

### Tests

- New: `test_the_twc_decides_whether_its_point_wants_power` in `test_charging_points.py`:
  - TWC A has finished and the registry still says "Charging"; car B is charging;
  - with a 9600 W budget, B gets 7680 and A gets its idle minimum;
  - the stale endpoint gets no command;
  - with no local member, the car decides.
- Fail-before: `assert [True, True] == [False, True]`.

Existing tests changed:

- `test_mode_2_named_twc…` and `test_car_on_no_twc…`: a charging TWC had no reported amps. These only passed because the endpoint masked it. They now report current.
- `test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum` and `test_twc_point_sets_the_twc_target_and_never_the_endpoint`:
  - A TWC that reports no demand now gets the idle minimum.
  - The tests then show the recovery: the car draws, and the full share follows on the next pass.
- `test_stopped_car_stays_one_point` (mock): the premise is kept (`wants=False`). It now expects the idle minimum (1200 W), and the car still gets no command.

This change depends on I1, which puts the idle minimum on the wire.

## M3: dead declarations (b9d0713)

I grepped lib and tests first. Removed:

- `ProviderOrder.orderKey`: no caller.
- `Provider.readSource` and its copies in TeslaBLE, Owner, Fleet and HA (HA's was a read-through property). Nothing in lib read them; `orderReadSources` keys on `ReadSource.provider`. Tests now assert on the modules' read sources instead.
- `EVSEInstance.provider`, `Gen2TWC.provider` and `Gen3TWC.provider`: no reader. `VehicleEndpoint.provider` is a real property and stays.

Kept: `ChargingPoint.startCharging`/`stopCharging`. `EVSEInstance` declares them `@abc.abstractmethod`, so removing them would make `ChargingPoint` impossible to instantiate.

No fail-before applies to a removal. The full suite passed.

## Deferred fix-now items (25a451b)

Added to `test_vehicle_endpoint.py`:

- `test_a_failed_scan_fails_closed` (slave scan, and the Gen3 walk inside the same guard)
- `test_just_below_power_flowing_is_not_blind` (0.99 A is not blind; 1.0 A is)
- `test_disabled_tesla_api_lists_nothing`
- `test_a_cached_endpoint_is_dropped_once_hidden`

These restore coverage, so they passed on arrival. To show each one bites, I mutated `VehicleEndpoints.py` one line at a time and reverted afterwards. Each mutation fails exactly its test:

| Mutation | Failing test |
|---|---|
| Scan failure returns `(False, False)` | fails_closed |
| `>=` becomes `> 0.98` | just_below |
| `enabled()` check removed | disabled |
| Blind returns `[]` without `_keep({})` | dropped_once_hidden |

The BLE-only endpoint positive test already existed: `test_a_car_only_ble_can_serve_is_writable_over_ble`.

## M2: docs and CHANGELOG (03537f3)

CHANGELOG:

- Features gained a Gen3 line: per-unit targets, shared headroom, and the free cloud VIN lookup. It needs Tesla app registration and an `energy_device_data` token; the `din` key is optional.
- Features gained a `controller.Gen2TWCs.ranges` line.
- Architecture:
  - The charging-point line now says "an idle Gen2 TWC" (m5).
  - The unreleased stopped-car Bugfixes entry is folded into it (m6).
  - New line: the Fleet API never sets amps where a TWC or BLE can, so a BLE-paired car on a UMC gets BLE only, with no Fleet fallback.
  - New line: HA is a billed-tier amps writer, tried after Fleet.
  - New line: the Settings relabels.
- Bugfixes: the idle Gen2 minimum. It was zeroed at main too.
- 940c1c2 scopes the Fleet amps rule to the power distributor. Charge Rate Control modes 2 and 3 still may use Fleet.

Docs:

- `docs/Settings.md`: a new "Who sets a car's charge rate" section.
- `docs/modules/Interface_RS485.md`: a new "Per-TWC amps range" section.
- The Gen3 cloud-VIN requirements were already accurate in `Controller_Gen3TWCs.md`.

## Not done

M4 and M5, as ruled.

## Concerns (need a ruling, not fixed)

1. **HA cadence during a Fleet error backoff.**
   - The wake-hold part of this is fixed (69343f2).
   - What remains is the genuine error backoff: `"error"` → HA is the sanctioned fall-through. But HA then runs at its own 10 s cadence (start-charge requests every heartbeat) for the length of the backoff, not Fleet's 60 s.
   - HA-only installs already behave this way; what is new is HA becoming active mid-backoff.
2. **Targeted `applyChargeLimit(vin=…)` raises TypeError on the real modules.**
   - TeslaBLE and TeslaAPI `applyChargeLimit` do not accept `vin`/`remoteOnly`. The façade counts the exception as failure and falls through to HA, the only module that accepts `vin`.
   - Nothing queues a `vin` today; only Policy's broadcast does. So this is latent, but the existing façade tests mock it as working.
3. **The start request ignores the range override.**
   - `TWCSlave.py:577` sends `startCarsCharging` only when `lastAmpsOffered >= config["minAmpsPerTWC"]`, not `>= self.minAmpsToOffer()`.
   - With an override below minAmpsPerTWC, the TWC now offers the override on the wire but never asks a paused car to start. Before I1 that wire offer was 0, so this is not a regression.
   - One-line candidate fix; outside the brief.
4. **I1 visible effect: the idle TWC now reserves 12 A, not 6, under the default config.**
   - On a 40 A feed beside a 32 A car, the distributor gives the idle TWC 0 (it was 6).
   - The heartbeat's existing `numCarsCharging > 0` rule still puts `minAmpsTWCSupports` (6 A) on the wire. A DEBUG `Point-…=0 W` is not the wire offer (Task 11 m2).
5. **M1 visible effect on old firmware.**
   - A paused car on an old-firmware Gen2 that reports max 0 resumes through the idle minimum, with one distributor pass of delay. Before, it got a full share at once.
   - Gen3 is unaffected, because its `wantsToCharge` is based on the connection.
6. Task 11 Step 6 live check is still pending (unchanged).

## Concern rulings

These are on top of 940c1c2, written test first. HEAD is now 8bdb9a6. The full capped suite gives **1318 passed, 1 xfailed** (9 more tests).

### 1. HA during a Fleet error backoff (8bdb9a6)

The throttle is in `VehiclePriority`.

How it works:

- During the walk, once a billed provider fails a command, the walk is in fallback mode. "Billed" means `cost(capability).tier >= TIER_BILLED` (Fleet), and "fails" means every attempt returns None, False or "error", or raises.
- In fallback mode, every later provider (in practice HA) is called at most once per `FALLBACK_INTERVAL` = 60 s per `(provider, capability, VIN or None)`. A provider that is not due is skipped.
- The check-and-record runs under a small lock with no I/O inside it. The clock is `time.monotonic` and can be injected for tests.

HA-only installs, and BLE-then-HA installs (BLE is not billed), never enter fallback mode, so HA keeps its own 10 s cadence. Start and stop are separate capabilities and are held separately.

Tests (`test_vehicle_priority_returns.py`):

- `test_ha_after_a_fleet_failure_is_held_to_fleets_cadence`:
  - HA is called at t, held at t+10 (Fleet is still tried), and called again at t+61.
- `test_the_hold_is_per_car_and_per_command`:
  - another car, stop versus start, and applyChargeLimit each get their own slot;
  - a repeat limit within 60 s is held.
- `test_ha_only_install_keeps_its_own_cadence`:
  - three calls 10 s apart all reach HA.

Fail-before:
- `assert 'success' is False` in the first two tests: HA was called at t+10.
- The HA-only test passed both before and after.

### 2. Targeted applyChargeLimit (d761a9d)

Both real methods now take `vin=None, remoteOnly=False`, matching what the façade and queue pass.

TeslaAPI:
- With a `vin`, both of its loops (the wake check and the apply) run over that car only.
- A VIN it does not hold returns "error", so the walk moves on.
- A targeted call neither waits on nor resets the once-a-minute broadcast throttle. It does not change the module-wide `lastChargeLimitApplied` either.
- `remoteOnly` is accepted; TeslaAPI is already the remote path.

TeslaBLE:
- With a `vin`, its targets are filtered to that VIN (case-insensitive).
- `remoteOnly=True` returns False without sending anything. The caller asked for a cloud path, so the walk moves on to Fleet.
- This is a judgment call: the flag had no defined meaning and no producer.

Broadcasts are unchanged.

Tests (new `test_targeted_charge_limit.py`, real methods, two cars):

| Test | Checks |
|---|---|
| `test_ble_targeted_limit_touches_only_that_car` | lower-case VIN in; only that car is sent to |
| `test_ble_broadcast_limit_is_unchanged` | both cars are sent to |
| `test_ble_declines_a_remote_only_limit` | `remoteOnly` returns False, nothing sent |
| `test_teslaapi_targeted_limit_touches_only_that_car` | only that car's `apply_charge_limit` and `update_charge` run |
| `test_teslaapi_broadcast_limit_is_unchanged` | both cars |

Fail-before: `TypeError: TeslaBLE.applyChargeLimit() got an unexpected keyword argument 'vin'` (twice), and the same TypeError for TeslaAPI.

### 3. TWCSlave start gate (f007fb3)

The protocol-2 `startCarsCharging` gate now compares `lastAmpsOffered >= self.minAmpsToOffer()` instead of the raw `minAmpsPerTWC`.

Without an override, the gate now uses `max(minAmpsPerTWC, minAmpsTWCSupports)`. That differs from before only when minAmpsPerTWC is below what the TWC supports. In that case the heartbeat zeroes offers below the TWC's minimum anyway.

Test: `test_start_request_follows_the_range_override` in `test_gen2_idle_minimum.py`.
- Setup: minAmpsPerTWC 12, override 8, protocol 2.
- An offer of 8 asks the car to start; an offer of 7 does not.
- Fail-before: `assert 0 == 1` (startCarsCharging was never called).

### 4. No change, as ruled.

## Last minors

1. Targeted applyChargeLimit no longer wakes other cars: `car_api_available(applyLimit=True, vin=target)` (TeslaAPI.py). Test `test_teslaapi_targeted_limit_never_wakes_another_car` uses the real car_api_available with a mocked wakeVehicle. Fail-before: the other car was woken (`assert <other> not in [<car>, <other>]`). Commit 992c396.
2. Idle Gen2 reservation now also requires every controller budget >= point.minPower, and deducts it (TWCMaster.py; budgets are now built even when no point wants power). Test `test_idle_minimum_respects_the_controller_budget` (wiringMaxAmpsAllTWCs 33, one TWC at 32 A, one idle). Fail-before: `assert 12.0 == 0`. Commit 8959380.
Full suite: 1320 passed, 1 xfailed.

## Idle minimum not counted

User ruling: the idle TWC minimum is never counted against, or gated on, any budget (configured limits are already 80% derated; the next cycle rebalances). Amended: a Gen2 TWC treats an offer of 0 as its hardware minimum, so TWCSlave's heartbeat is unchanged.

- TWCMaster.distributeEVSEPower: reverted 8959380's controller-budget gate and deduction, and moved the controller budget construction back inside `if wants_power`. I chose the simplest form: every point that does not want power gets target 0 (the idle loop no longer reads `idleMinimum`; the flag remains on the endpoint classes but is unused by the distributor). On the wire a Gen2 sends 0 = hardware minimum. Task 11 (two TWCs never share a point) untouched.
- Charging points: fair-share already turns a share below `point.minPower` (minAmpsToOffer) into 0, never a partial amount; now tested (single car under floor, two cars under floor, distributor-level).
- CHANGELOG and docs/modules/Interface_RS485.md updated (previously said an idle TWC is offered minAmpsPerTWC).
- Tests: replaced 8959380's test_idle_minimum_respects_the_controller_budget (12.0 == 0). New in test_gen2_idle_minimum.py: idle sends 0 on the wire with minAmpsPerTWC 12 (comment: Gen2 treats 0 as hardware minimum); car takes the whole budget; ignores the controller budget; policy budget 0 gives 0; next cycle the two points share 16/16 (sum <= budget); below-floor charging point gets a stop. Updated tests that encoded the old gate/minimum: test_gen2_idle_minimum.py test_idle_minimum_does_not_starve_a_charging_twc (expected (32,0) at feed 40, (32,12) at 50), test_idle_twc_is_offered_min_amps_per_twc_on_the_wire and test_range_override_is_what_the_heartbeat_sends (idle sent minimum; now 0, allocation floor still asserted); test_charging_points.py test_idle_twc_keeps_its_minimum_when_budget_allows (renamed), test_stopped_car_stays_one_point, test_the_twc_decides_whether_its_point_wants_power, test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum, test_twc_point_sets_the_twc_target_and_never_the_endpoint, test_gen2_at_00_with_a_sleeping_car_is_two_points_as_before_task_10 (idle target 6/1200/1440 W -> 0).
- Fail-before: 9 of the changed/new tests failed against the unfixed lib (the "not counted" budget tests pass trivially at 8959380 because idle was 0 there too, and now pass because the target is 0).
- Full suite: 1325 passed, 1 xfailed.
- Note: with an idle offer of 0 the paused-car start request (lastAmpsOffered >= minAmpsToOffer) does not fire from the idle path; unchanged from before the minimum was added.
