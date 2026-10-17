# Task 3 report

Status: DONE_WITH_CONCERNS. Commit 14ffaf2.

Changed: VehiclePriority (applyChargeLimit with remoteOnly skip, resetChargeLimitState fan-out, __getattr__ -> _dispatch with skip), TeslaBLE (vin/remoteOnly, resetChargeLimitState), TeslaAPI (applyChargeLimit rewrite, update_charge(allowBle), resetChargeLimitState, car_api_charge call), HomeAssistant (vin filter, no-op reset), TWCManager.py (removed checkArrival/checkDeparture branches). Tests per brief.

RED: 22 failures (brief predicted 23; test_no_vin_applies_to_every_vehicle already passed under the old signature, so BLE had 4 not 5).
GREEN: 540 passed, 1 warning (brief 539, +1 from Task 1). black check clean.

Deviations: commit trailer is Claude Sonnet 5.5 (dispatch said actual model; global-constraints says Fable 5.1). First test-extraction pass wrote blank stubs; reverted and redone.

Concerns:
- TWCSlave.py (655-665) and HTTPControl.py (591-598) still queue checkArrival/checkDeparture; background_tasks_thread silently ignores them until Task 8 (the /api/checkArrival and /api/checkDeparture endpoints are no-ops meanwhile).
- Deleted comment in TWCManager.py: use master.lastChargeLimitApplied (0 -> -1), not TeslaAPI's own lastChargeLimitApplied, which stays 0 when BLE manages limits. VehiclePresence must account for this when re-applying on arrival.

## Fix round 1

Commit: see git log (follows 14ffaf2). Changes:
- TeslaAPI.applyChargeLimit: loop-1 flag reset treats an unsaved VIN as -1 and, for vin=None, only runs for atHome vehicles; the vin=None not-atHome skip now precedes update_charge. Per-VIN still bypasses atHome.
- HomeAssistant.applyChargeLimit: per-VIN apply that processed nothing returns "error".
- TeslaAPI.car_api_available(..., vin=None): wake loop skips other VINs; applyChargeLimit passes vin.
- Tests added (RED confirmed against the old lib for all four TeslaAPI/HA tests; the away-car-per-VIN test is a regression guard): unsaved at-home car read at most once over 3 restores; away saved(-1) car never read over 3 applies of 70; per-VIN apply still reads an away car; per-VIN apply wakes only the target; HA per-VIN no-op returns error.
- Full suite: 545 passed, 1 warning; black clean.
