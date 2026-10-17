### Finding Verdicts — ADDRESSED | NOT ADDRESSED with file:line
1. **ADDRESSED.** lib/TWCManager/TWCMaster.py:1528 (recordVehicleVIN now only queues `vehicleIsDefinitelyHome`); handler TWCMaster.py:1530-1534; dispatch lib/TWCManager/TWCManager.py:389-390 inside background_tasks_thread. Per-VIN dedupe at TWCMaster.py:341-343 (`_taskKey`), so two TWCs' cars both queue. Behaviour otherwise unchanged (same TeslaAPI.vehicleIsDefinitelyHome(vin); it now takes the VIN instead of slaveTWC.currentVIN, the same value). Caller sweep: Vehicle.read()/update_location/update_charge are reached only from TeslaAPI car_api_charge, applyChargeLimit, updateChargeAtHome and vehicleIsDefinitelyHome. Those are called from background_tasks_thread (TWCManager.py:332-341, 390) or via VehicleCommandQueue. TWCSlave.py:588 and :1243 and TWCMaster.py:1152/1637 only touch getCarApiVehicles, flags, tokens and settings, with no reads. The RX loop (TWCManager.py ~1000) only calls refreshTokenIfNeeded. No remaining serial-thread path reaches a vehicle read.
2. **ADDRESSED.** lib/TWCManager/Vehicle/TeslaAPI.py `_readFresh` uses `fetched = obs is not before`. The `start = time.time()` and `obs.at >= start` are removed. Registry Observation is an immutable NamedTuple (Registry/Fields.py:9, new object per observe at :77), so identity is sound. Remaining `obs.at` uses (TeslaAPI.py:2130, :2358) compare registry stamps to registry stamps only. Tests cover an injected clock and an equal-stamp read.

Dispatch-source test (test_background_thread_dispatches_the_home_check): acceptable, not vacuous. It fails if either dispatch line is removed or renamed, and the justification (TWCManager.py starts the app on import) is real. It is weak: it proves the text exists in the function, not that the branch is reachable, and it is sensitive to quoting style. Fine as a guard.

Focused tests: test_reads_no_wake.py and test_twcmaster_vin_confirmation.py, 34 passed.

### New Breakage in the Fix Diff
None. Note that the home-check now runs asynchronously, so `atHome` may update slightly later than the TWC VIN confirmation. That is the intended tradeoff.

### Out-of-Scope Observations
None.

### Verdict — **Fix round:** All findings addressed, no new Critical/Important breakage
