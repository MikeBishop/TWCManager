Task 2 DONE. Commit 356c1d15 on vehicle-model/phase6.
VehicleEndpoint: _asleep(), isCharging, currentAmps (new properties; EVSEInstance base defines neither), sleep-aware wantsToCharge.
Tests: 3 added to tests/unit/test_vehicle_endpoint.py (used setup(here=False), placeAt from existing helpers). Full suite 2251 passed, 1 xfailed.
Lib lines 26460 -> 26475 (+15). Red step not run separately (isCharging/currentAmps did not exist).

Fix round 1: removed isCharging/currentAmps (no reader); kept _asleep + wantsToCharge. Tests: asleep w/ chargingState None and Complete unchanged; distributor-level test (test_charging_points.py) that a car asleep after Charging has its desired amps cleared. Amended to ba715698. Lib 26460 -> 26467 (+7). Suite 2253 passed, 1 xfailed.
