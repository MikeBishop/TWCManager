# Task 9 re-review 1: fix round 2 (edf61bf..006818f)

**Verdict: PASS WITH FIXES.** C1, M1, M2, M3 and M4 are fixed, and M5 stays deferred. I1 is fixed for its stated case (Fleet+HA with several HA cars). The accepted narrowing has one gap it was meant to close: an HA-only install with **two or more** HA cars loses targeted start and stop (N1, Important).

## Method

- I re-ran my harness against a fresh detached eee9425 worktree and against 006818f. The worktree has since been removed.
- The extended copy is `scratchpad/probe-t9/harness2.py`, with comparison script `cmp.py`. Output is in `old.2.json`, `new.2.json` and `diff2.txt`. It keeps every original scenario and adds five:
  - `Owner{listLoaded False}`;
  - `HA{haCars 2}`, an HA-only install;
  - `Fleet+HA` with one HA car;
  - `Fleet+HA{haCars 2}`;
  - `Fleet+HA{haCars 2, listLoaded False}`.
- The HA spy now has `getVehicleCount()`, which the real `HomeAssistant` module has at `:568`. HA cars are attached by VIN, as `HomeAssistant.py:409-416` does.
- I compared edf61bf (my earlier `new.json`) with 006818f on the original scenarios. **Only the C1 cells changed**, and each changed to eee9425's call counts. No other cell moved, including every ble_only and Owner cell.
- Focused tests pass:
  - `test_vehicle_priority`, `test_provider_order`, `test_carapivehicle_registry`: 64 passed;
  - `test_homeassistant_registry`, `test_vehicle_command_queue`, `test_teslaapi_providers`, `test_teslaapi_chargerate`, `test_teslaapi_charge_vin`: 72 passed.

## Findings

| ID | Verdict | Evidence |
|---|---|---|
| C1 | **Fixed** | Rows `Fleet{listLoaded False}` and `BLE+Fleet{listLoaded False}`, start(vin)/stop(vin)/limit80(vin), under prefer_ble and api_only: OLD `TeslaAPI:2` (after `TeslaBLE:3` with BLE), NEW the same. The only remaining difference is D4's return type. |
| I1 | **Fixed** (narrowed as ruled) | `Fleet+HA{haCars 2}`, targeted start/stop/limit with Fleet failing: NEW `TeslaAPI:2` only, so HA is not called. Broadcasts and reads still reach HA, which is D5/D6 and intended. `Fleet+HA` with one car reaches HA after Fleet fails; that car is the target. |
| M1 | **Fixed** | `debugCommand("setChargeRate")` now calls `dispatch(attempts=1, localRule=False)` with no amps, the same as the façade. Each provider gets one attempt. See m-1 below for a stale comment. |
| M2 | **Fixed** | `targetAmps` is marked for removal in Phase 3. |
| M3 | **Fixed** | The façade no longer calls `order._ready`; it uses `candidates(..., localRule=False)`. |
| M4 | **Fixed** | `Settings.md` names `Gen3TWC`, `TeslaMateVehicle` and `FleetTelemetryMQTT`. |
| M5 | Deferred (Phase 6) | Unchanged. |

## Checks requested

1. **C1's Fleet walk while the list is empty:**
   - `_listUnloaded` only adds providers drawn from `self.order.ordered(capability)`. `ordered` has already applied the policy, `providerSuppressions` and `available(cap)`.
   - **Owner-only:** the Owner slot never grants commands, so FleetAPI is not available. `Owner{listLoaded False}` sends no command under any policy (harness).
   - **ble_only:** `Fleet{listLoaded False}|ble_only` and `Fleet+HA…|ble_only` send nothing. `BLE+Fleet{listLoaded False}|ble_only` sends to TeslaBLE only, and the counts match eee9425.
   - **Attempts:** the walk uses `provider.attempts()`, which is 2 for Fleet. No call site gains attempts; every C1 cell is `TeslaAPI:2`, as at eee9425. Because `seen` dedupes the module, TeslaAPI is walked at most once per call.
2. **`localRule` and the queue's setAmps rule:**
   - `localRule` defaults to True in both `candidates` and `dispatch`.
   - Only two places pass False: `debugCommand("setChargeRate")`, and `modulesFor` for `setChargeRate` (whose rule was already readiness only at edf61bf).
   - For every other façade command the flag is a no-op, because only `SET_AMPS` applies the rule.
   - `VehiclePriority.setAmps`, the queue's `setAmps`, still calls `dispatch(..., amps=amps)` with the default.
   - `test_set_amps_keeps_the_local_amps_rule` passes, and the new M1 test asserts that `dispatch(amps=16)` keeps the rule.
3. **No new paid call path:**
   - **C1:** restores eee9425's TeslaAPI calls exactly. It does not add any; the harness shows identical counts.
   - **Debug setChargeRate:** may now reach Fleet once after BLE fails, even where BLE or the TWC covers the rate. It is user-initiated with a single attempt, and at eee9425 the same call always went to TeslaAPI. Net paid calls are ≤ eee9425.
   - **I1:** removes calls; it adds none.

## New issues

### Important

**N1: an HA-only install with two or more HA cars no longer sends targeted start or stop** (`VehiclePriority._ownVehicleOnly`, `count != 1`).

- **What changed:** at eee9425 HA was the resolved module, so `stopCarsCharging(currentVIN)`, queued by `TWCSlave.py:574` with the TWC-reported VIN, called HA directly. HA stopped every HA car at home and connected, including the target. At 006818f the façade skips HA because `getVehicleCount() == 2`. Nothing is sent, so the target keeps charging against policy under the default `chargeStopMode` 1. Targeted start has the same gap.
- **Harness evidence:** `HA{haCars 2}` under prefer_ble and api_only, start(vin)/stop(vin): OLD `HomeAssistant:1`, NEW `-`. This is a regression against both eee9425 and edf61bf.
- **Why the narrowing misses it:** HA cars always carry a VIN and an attachment (`HomeAssistant.py:409-416`), so D8 ("no attachment, skipped") does not cover this case. The narrowing was accepted on the grounds that it "keeps HA-only installs with TeslaAPI disabled working as at eee9425". That is true for a single car only.
- **Fix options:**
  - **(a) Façade only, my preference.** In `_ownVehicleOnly`, also pass HA when no other provider in `ordered(cap)` can carry the command, meaning HA is the last resort. That is the eee9425 condition under which HA was called directly. It reopens stop-all only where eee9425 had it. One difference: HA plus an unconfigured TeslaAPI (pure Gen2 with HA, review D5) would also gain it, whereas at eee9425 HA was never reached on that shape.
  - **(b) Needs a ruling.** HA's two methods honour the VIN. This is the clean fix, but `HomeAssistant.py` is outside the file list.
  - **(c) Accept explicitly.** Accept the regression with a release note.
- **Test (for a):** HA-only with two HA cars, a targeted stop calls HA once; Fleet+HA with two cars still skips HA.

### Minor

- **m-1** (`tests/unit/test_provider_order.py`, `test_debug_command_tries_each_provider_once`): the comment "BLE covers 3 A: Fleet stays off" is now false. With `localRule=False` and no amps, Fleet is called after BLE fails; I confirmed that `f.calls == [("setAmps", VIN, 3)]`. The assertion only checks `b.calls`, so the test still passes. Fix the comment, and assert `f.calls` to pin the M1 behaviour.
