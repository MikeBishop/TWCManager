### Task 5: TeslaBLE provider

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/TeslaBLEProvider.py`.
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py:233` (keep the read source on `self.readSource`), new `providers()`; `lib/TWCManager/Vehicle/Registry/Sources.py:34-39` (`canRead` drops the `VehiclePriority`/`api_only` lookup: the order filters suppressed sources now) and `TeslaBLEReadSource.provider = "TeslaBLE"`.
- Test: `tests/unit/test_teslable_provider.py`; adjust `tests/unit/test_reads_no_wake.py` if it asserts the BLE source skips under `api_only` (move that assertion to Task 2's `test_api_only_suppresses_ble_for_everything`, which already covers it).

**Interfaces:**
- Consumes: `TeslaBLE.setChargeRate(charge_rate, vehicle=<vin>)`, `wakeVehicle(vin)`, `Vehicle.claims`, `vehicleMaxAmps`.
- Produces `class TeslaBLEProvider(Provider):` `name = "TeslaBLE"`, `rank = 2`, `local = True`; `__init__(self, ble, master)`: `module = ble`, `readSource = ble.readSource`; `declarations()`: `READ_CHARGE`, `READ_LOCATION`, `READ_PLUG`, `READ_ONLINE`, `SET_CHARGE_LIMIT`, `START_CHARGING`, `STOP_CHARGING`, `SET_AMPS`, `WAKE` → `Declaration(LOCAL)`; `ready(vehicle, cap)`: `vehicle.vin` is set and `"TeslaBLE" in vehicle.claims` (paired or unproven; a refused key dropped its claim — Phase 1 ruling I2); `ampsRange(vehicle)` → `(1, vehicleMaxAmps(vehicle, master.config["config"]))` (vehicle amps 1..max, never 0); `setAmps(vin, amps)` → `ble.setChargeRate(int(amps), vin)`; `wake(vin)` → `ble.wakeVehicle(vin)`.
- Produces (`TeslaBLE`): `self.readSource = TeslaBLEReadSource(self, master)` (still registered with the registry as today); `providers(self) -> List[Provider]` = `[TeslaBLEProvider(self, self.master)]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_teslable_provider.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from tests.unit.test_teslable_pairing_status import make, VIN

def test_provider_is_local_free_and_ready_for_claimed_vins():
    ble, reg, master = make(); (p,) = ble.providers()
    assert (p.name, p.local, p.cost(C.SET_AMPS), p.module, p.readSource) == ("TeslaBLE", True, C.LOCAL, ble, ble.readSource)
    v = reg.getOrCreate(VIN, "t")
    assert p.ready(v, C.SET_AMPS) is False
    ble._claimUnproven(v); assert p.ready(v, C.SET_AMPS) and p.ready(v, C.READ_CHARGE)
    v.dropClaim("TeslaBLE"); assert p.ready(v, C.WAKE) is False
    assert p.ready(reg.beginPlugSession("8244"), C.SET_AMPS) is False

def test_amps_range_is_one_to_vehicle_max():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t")
    master.config = {"config": {"wiringMaxAmpsPerTWC": 48}}
    assert p.ampsRange(v) == (1, 48)
    v.observe("availableCurrent", 16, "TeslaBLE"); assert p.ampsRange(v) == (1, 16)

def test_commands_call_the_module_by_vin():
    ble, reg, master = make(); (p,) = ble.providers()
    ble.setChargeRate = Mock(return_value=True); ble.wakeVehicle = Mock(return_value=False)
    assert p.setAmps(VIN, 12.6) is True; ble.setChargeRate.assert_called_once_with(12, VIN)
    assert p.wake(VIN) is False; ble.wakeVehicle.assert_called_once_with(VIN)

def test_read_source_no_longer_consults_command_policy():
    ble, reg, master = make(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    master.getModuleByName = Mock(side_effect=AssertionError("must not look up VehiclePriority"))
    assert ble.readSource.canRead(v) is True and ble.readSource.provider == "TeslaBLE"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TeslaBLE' object has no attribute 'providers'`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_teslable_provider.py tests/unit/test_reads_no_wake.py tests/unit/test_teslable_pairing_status.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Add the TeslaBLE provider: local, free, ready for claimed VINs"
```

