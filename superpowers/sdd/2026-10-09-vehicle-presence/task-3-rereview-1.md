# Task 3 re-review 1 (14ffaf2..9d513dd)

1. Important 1 (policy-wide dedupe): ADDRESSED. TeslaAPI.py flag reset now `(vin is not None or vehicle.atHome) and limit != (lastApplied if hasSaved else -1)`; no save of (chargeLimit,-1) added (the unsaved/limit -1 branch still only latches). vin=None away cars skip before update_charge. Per-VIN still bypasses atHome.
2. Minor 1 (HA per-VIN nothing processed): ADDRESSED. HomeAssistant.py returns "error" when vin is not None and vehicles_processed == 0; at_home check untouched.
3. Cross-task wake scoping: ADDRESSED. car_api_available(vin=) skips other VINs in the wake loop; applyChargeLimit passes vin; vehicle-list GET block untouched in the diff.

Policy-wide at-home saved path: unchanged (same limit != lastApplied reset, same 60 s throttle, same needToWake).

New breakage: none.
Minor: test_unsaved_at_home_car_is_read_once uses `<= 1`, weak (would pass with zero reads).
Observation (pre-existing, out of scope): car_api_available still refuses to wake the per-VIN target if its cached atHome is False.
