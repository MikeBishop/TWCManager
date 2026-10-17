### Spec Compliance
- ✅ Spec compliant. Diff matches the brief file by file: migrateNormalChargeLimit (TWCMaster.py:944-959), addVehicle hook (TeslaAPI.py:113-118), all five normal-limit calls in applyChargeLimit switched to vehicle.VIN (TeslaAPI.py:927,975,1025,1027,1044), both test files.
- Test count 517 vs brief 516 is the expected +1 from Task 1.

### Named risk: upgrade of an existing install
Checked: (a) every reader/writer of chargeLimits in lib (grep): only TWCMaster get/save/remove, TeslaAPI (now VIN) and TeslaBLE (already VIN); no ID-keyed consumer remains. (b) Migration trigger: addVehicle is called per vehicle from the vehicle-list load (TeslaAPI.py:282), and applyChargeLimit only iterates carApiVehicles, so a vehicle's ID entry is migrated before its VIN key is first read; no window where the old entry is missed. (c) Preservation: ID entry is moved by pop/assign, value untouched (test_moves_id_key_to_vin); settings.json persisted via queued saveSettings. (d) Clobber: existing VIN entry is never overwritten; the stale ID entry is dropped (test covers). (e) Idempotent: second call returns False, no extra save. (f) str() normalisation handles JSON string keys vs int ID. Result: safe.

### Strengths
Small, focused, idempotent; str-normalised keys; no-op guard (empty/missing limits, oldKey == vin); logs and queues save only on change; tests cover move, VIN-wins, and no-op.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- TeslaAPI test file test_teslaapi_presence.py:44-47 `test_apply_charge_limit_uses_vin_keys` is a source-text inspection, not a behavioral test; brittle but brief-mandated and cheap. A behavior test running applyChargeLimit with a Mock master would be stronger.
- Unused imports (time, patch, pytest, VIN2) in test_teslaapi_presence.py are placeholders for later tasks; harmless.
- When both keys exist, the ID entry's data is discarded (TWCMaster.py:952-954); by design, but it means a VIN entry written by BLE can shadow a newer API-saved one on first upgrade. Accepted by spec.

### Assessment
**Task quality:** Approved
**Reasoning:** Upgrade path preserves existing ID-keyed limits, never clobbers a VIN entry, and no reader is left on the old keys.
