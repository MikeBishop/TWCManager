### Spec Compliance
Compliant.
- bleSilent (VehiclePresence.py:423-431): bleApplies and last contact record is a failure; never-probed (no _reach) is False. isTwcAttributed (:433-436) matches the brief.
- allEVSEs restructure (TeslaAPIController.py ~158-168): with presence None, _umcCar is False, so the filter reduces to the old one. blind -> [] is equivalent to the per-car `not (blind or ...)`. The exception waives only blind and unknown-and-telemetry; `v.VIN not in served` stays outside it.
- All 5 brief tests exist and are non-vacuous (the never-probed test proves the #694 exclusion applies without the contact). 3 extra tests (blind TWC, no-BLE, failed scan) added. Focused run: 25 passed.

### Strengths
- Locking is sound: bleApplies read outside the lock, _reach and _twcVin under it.
- _scanFailed fail-closed cleanly tested.

### Issues
Critical: none. Important: none.
Minor:
- bleSilent ignores "no success within BLE_REACH_MAX_AGE": _reach holds only the latest contact, so a failure shortly after a success reads silent. Matches broadcastVINs' existing rule; the docstring wording slightly over-claims.
- test_car_attributed... writes presence._twcVin directly (private state).

### Assessment
**Task quality:** Approved
**Reasoning:** Behaviour matches the brief, no-presence #694 behaviour is unchanged, the exception is narrowly scoped, tests are meaningful.
