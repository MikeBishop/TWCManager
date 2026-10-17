### Task 14: Own-write stamps on charge limit and charge rate (A33 home)

Records only; no decision uses the stamps until Phase 3 ports `ChargeLimitRules`.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:2433-2500` (`apply_charge_limit` success), `:1743-1836` (`setChargeRate` → `_recordChargeRate`); `lib/TWCManager/Vehicle/TeslaBLE.py:587-668` (`setChargeRate` per-vehicle success), `:736-760` (`applyChargeLimit` success); `lib/TWCManager/Vehicle/HomeAssistant.py:569-626` (`applyChargeLimit` after `_call_service` ok).
- Test: `tests/unit/test_own_write_stamps.py`.

**Interfaces:**
- Consumes: `Vehicle.noteWrite(field, value, source)`.
- Produces: on each successful send: `vehicle.noteWrite("chargeLimit", limit, "<module>")` (TeslaAPI, TeslaBLE, HomeAssistant; for BLE `-1` restore the stamped value is `target_limit`), `vehicle.noteWrite("availableCurrent", amps, "<module>")` for charge rate (TeslaAPI `_recordChargeRate` via `getattr(vehicle, "vehicle", None)` so `test_teslaapi_chargerate.py`'s attribute-only fake keeps working; TeslaBLE per-vehicle branch). Registry vehicle located via `registry.get(vin)`; a missing vehicle is skipped silently.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_own_write_stamps.py
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.TeslaAPI import TeslaAPI
from tests.unit.test_teslable_pairing_status import make as make_ble
VIN = "5YJ3E1EA1KF000001"

def test_api_charge_rate_stamps_available_current():
    reg = VehicleRegistry({}); v = reg.getOrCreate(VIN, "TeslaAPI"); car = Mock(VIN=VIN, vehicle=v)
    TeslaAPI._recordChargeRate(car, 16)
    assert v.lastWrite("availableCurrent").value == 16 and v.lastWrite("availableCurrent").source == "TeslaAPI"

def test_ble_set_charge_rate_stamps_on_success():
    ble, reg, master = make_ble(); reg.getOrCreate(VIN, "TeslaBLE")
    ble.wakeVehicle = Mock(return_value=True); ble.sendCommand = Mock(return_value="ok"); ble.parseCommandOutput = Mock(return_value=True)
    assert ble.setChargeRate(12, VIN) is True
    assert reg.get(VIN).lastWrite("availableCurrent").value == 12

def test_ble_set_charge_rate_no_stamp_on_failure():
    ble, reg, master = make_ble(); reg.getOrCreate(VIN, "TeslaBLE")
    ble.wakeVehicle = Mock(return_value=True); ble.sendCommand = Mock(return_value=None)
    assert ble.setChargeRate(12, VIN) is False and reg.get(VIN).lastWrite("availableCurrent") is None
```
Plus one test each for `TeslaAPI.CarApiVehicle.apply_charge_limit` (requests_mock `set_charge_limit` → `{"response": {"result": true}}`; assert `lastWrite("chargeLimit") == 80`) and `TeslaBLE.applyChargeLimit` (single VIN in settings, `sendCommand` mocked to `"ok"`; assert `lastWrite("chargeLimit").value == 80`), following the fixture styles of `test_teslaapi_readonly_gate.py` and the BLE `make()` above.

- [ ] **Step 2: Run to verify failure** → FAIL (`lastWrite(...) is None`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/Vehicle/HomeAssistant.py
git add lib/TWCManager/Vehicle tests/unit/test_own_write_stamps.py
git commit -m "Stamp the registry with our own successful charge-limit and charge-rate writes"
```

