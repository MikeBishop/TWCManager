# Slim Task 11 re-review 1 (2ecf54f..d35a95c)

Method: read the diff and code at d35a95c; reverted each lib hunk to 2ecf54f and ran tests/unit/test_limit_wiring.py (21 pass at d35a95c). The tree is clean after each revert.

- C1 addressed. Targets.onDeparture calls api.update_location(0) for held cars with a TeslaAPI attachment and no twcVin. Revert: 3 tests fail (unplug-and-leave, unplug-at-home, policy-change-while-away). The test counts paid calls: exactly vehicle_data, then set_charge_limit; no wake_up.
- I1 addressed. HeldLimits._loadedVins is set in load(); a later-recorded VIN merges to HeldLimit(legacy.outside, store.held); the discard is logged (this also covers M5). Revert: the probe test and test_legacy_ids_resolve_once_from_the_first_vehicle_list fail.
- I2 addressed. The 5-minute token tick queues loadVehicleList while listPending(); the handler calls loadList(), which makes free GETs only. Revert of TWCManager.py: test_a_failed_boot_list_load_recovers_without_an_arrival fails (on its source assertion; the behaviour part uses lib code that is unchanged by that revert, so the source pin is what protects the tick).
- M1 addressed: resolveHeldLimits runs after the vehicleListLock block exits (TeslaAPI.py:~404).
- M3 addressed (mock and doc). M4 addressed (level 1 on root and TeslaAPI loggers, and it asserts the INFO8/DEBUG lines were captured). M5 addressed (via I1). M2 unchanged, by ruling.

Checks:
- Paid calls: one vehicle_data per held car per departure check (Targets.py:88-89), as on main. The cascade is Vehicle.read, which BLE-first and never wakes. If Fleet fails and Owner is also usable, the cascade could try a second source, which is the same as main. A restored car drops out of holding(), so the 20 and 45 min checks read nothing.
- Wake: none in the departure path. The test asserts there is no wake_up.
- Locks: update_location runs on the background thread with no lock held. resolveLegacyIds logs and saves after releasing settingsLock. The second-slot GET is now outside vehicleListLock (an improvement). Order is unchanged.
- Tokens in logs: none. The new INFO line names only the ID, the VIN and two percentages.
- Periodic list load: loadList does GET /vehicles only (loadVehicleList, resolveHeldLimits and refreshTokenIfNeeded, which is the existing token refresh). It never calls update_charge or vehicle_data. On installs with no token, slotFor("read") is None and no HTTP call is made.

Size: +53 lib lines are proportionate. HeldLimits +26 is the largest, mostly the merge log block (which could be a little tighter), TeslaAPI +11, TWCManager +8, Targets +8. There is no duplication; loadList moved code out of updateChargeAtHome instead of copying it.

New issues: none blocking. Nit: HeldLimits.py:209-211, when the store entry is malformed (own is None) the log reports "kept" with limit == own, so the line is slightly misleading.

APPROVED
