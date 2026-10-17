# Task 14 report

Status: DONE_WITH_CONCERNS. Commit 448b92c (branch vehicle-model/phase1). 1056 passed (was 1042; +14 in tests/unit/test_own_write_stamps.py). Black clean on touched files.

Stamps on success only, value actually sent: TeslaAPI _recordChargeRate (availableCurrent) and apply_charge_limit (chargeLimit); TeslaBLE setChargeRate (per-vehicle and all-vehicles branch) and applyChargeLimit (target_limit, so -1 restore stamps the restored value) via a new _stampWrite helper (registry.get, upper-case VIN, None-guarded); HomeAssistant applyChargeLimit after _call_service ok.

Concerns:
1. _recordChargeRate uses getattr(vehicle, "vehicle", None) as the brief mandates; on a real CarApiVehicle .vehicle calls getOrCreate, so a charge-rate write can re-create a forgotten registry vehicle. This is in tension with "write paths never create vehicles"; left per brief for the reviewer/Phase 3. apply_charge_limit uses _liveVehicle() (registry.get).
2. apply_charge_limit also stamps when reason == "already_set" (treated as success; value equals car's limit).
3. HA passes v.vin to registry.get without .upper(); safe since VIN_REGEX admits only upper case.
4. BLE all-vehicles setChargeRate branch also stamps per successful VIN (beyond the brief's per-vehicle branch).

## Concerns fixed
- (1) _recordChargeRate now resolves the registry vehicle via the non-creating _liveVehicle() and skips the stamp when it is None; test added (forgotten vehicle stays forgotten). The brief's Mock fake now supplies _liveVehicle.
- (3) HA VIN is upper-cased before registry.get.
- (2) and (4) kept per ruling.
