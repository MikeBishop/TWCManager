# Fleet EVSE zero-share stop

Branch fix/fleet-evse-zero-stop (worktree scratchpad/wt-zerostop, off origin/main). Local only.
Commits: (1) fix distributeEVSEPower loop skipping every other EVSE; (2) stop/start for TeslaAPIEVSE.
Seam: TeslaAPIEVSE.setTargetPower (per-instance _stopRequested flag; instances are cached by TeslaAPIController so state persists). Distributor, TeslaAPI.setChargeRate and TeslaAPIController untouched.
Tests: tests/unit/test_distributor_zero_share.py; full suite 609 passed.
Concerns:
- Found a real bug: `for evse in pending` + pending.remove() skipped every other EVSE (it never got setTargetPower). Fixed with list(pending) in its own commit.
- Resume sends startCharging whenever we had stopped, regardless of polled (maybe stale) state.
- stopCarsCharging(vin) with chargeStopMode 2/3 is not VIN-targeted (stops all slaves / sends stop to all TWCs).
- stopCarsCharging mode 1 also touches stopTimeout/Policy.overrideLimit, as for TWCSlave.
- MergedEVSE (car on TWC + API) routes setTargetPower to local by default, so API stop does not apply there (Gen2 heartbeat handles it).
- Gen2 EVSE code unchanged.

## Fix (coordinator review)
Concerns 3-4 resolved: TeslaAPIEVSE._queueCharge(bool) calls master.queue_background_task({"cmd":"charge","charge":bool,"vin":VIN}) (goes to the vehicle command worker, normal channel order). No master.start/stopCarsCharging, so no chargeStopMode dependence, no stopTimeout/Policy side effects. Tests parametrized over chargeStopMode 1/2/3 with a real TWCMaster: only the VIN task queued, no sendStopCommand, no respondToSlaves, stopTimeout unchanged, overrideLimit/clearOverride not called. Suite: 612 passed. New commit (not amended).
Residual: queue key for charge tasks is (cmd, None), so a queued VIN stop/start can coalesce with another pending charge task (pre-existing queue behaviour).

## Fix 2 (TeslaAPI honours vin)
TeslaAPI.car_api_charge reads task["vin"]: skips other vehicles in the stop-reset loop and the command loop, and passes vin to car_api_available (new optional vin=None) which skips other vehicles in its wake loop. vin None: unchanged. Tests: tests/unit/test_teslaapi_charge_vin.py (vin stop/start POST only V1, no update/wake for V2; no-vin hits both; zero-share stop through VehiclePriority with BLE failing reaches TeslaAPI and POSTs only V1). Verified the new tests fail without the fix. Suite: 616 passed.
Note: the vehicle command queue keys "charge" tasks as (cmd, None) on main, so a queued VIN stop can coalesce over another pending charge task. That is fixed separately by per-VIN queue keying in the presence stack (#667 fix); this fix pairs with it.
