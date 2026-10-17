# Task 16 report
Status: DONE. Commit on vehicle-model/phase1 (see git log HEAD).
Implemented ageText, heldLimitText (VIN then API numeric ID), addVehicleByVIN, POST /vehicle/add, addVehicleError attribute, template globals (ageText, heldLimitText, registry), registry table + add form + "Charge history" retitle, CHANGELOG. Tests: tests/unit/test_vehicles_page.py (5, incl. escaping); full unit suite 1072 passed.
Notes: addVehicleByVIN skips creating a settings["Vehicles"] entry if a case-insensitive match exists; scanForVehicles is called outside settingsLock. Forget action not added (Phase 6 per brief).
Autoescape confirmed on in production templateEnv (HTTPControl.py: autoescape=True). Brief/ruling conflict: Forget action (brief says Phase 6; dispatch said registry-only here) - not implemented. setdefault replaced by case-insensitive check (TeslaBLE _settingsKey is case-insensitive); scanForVehicles outside settingsLock (lock order).

## Fix round 1
str() coercion of the vin field (getFieldValue returns int for all-digit input; previously AttributeError). Tests added: numeric input (failed before fix with AttributeError), known VIN marked user-asserted without duplicate, case-insensitive settings dedupe.
