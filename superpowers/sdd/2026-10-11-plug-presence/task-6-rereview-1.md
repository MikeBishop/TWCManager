# Task 6 re-review 1
1. Weak unplugged/outside vs TWC-named or strong-within-hold: ADDRESSED (VehiclePresence.py:520-541 mirrors _applyUnplugged:1002-1016; fastCharger and strong unplugged still False; tests in test_vehicle_presence.py TestDiscoverEvidenceOrder cover both, plus an API-level TWC test).
2. Fail closed in TeslaBLE loop and TeslaAPI _discover: ADDRESSED (TeslaBLE.py ~893-915, TeslaAPI.py ~1220; WARNING logs type name only; tests on both).
New breakage: none Critical/Important.
Minor: no test for "outside + BLE-unreachable" weak case with strong hold; the shared code path covers it.
