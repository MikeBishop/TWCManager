### Task 12: HomeAssistant vehicles in the registry

**Files:**
- Modify: `lib/TWCManager/Vehicle/HomeAssistant.py:88-140` (`refresh_from_home_assistant`), `:151-235` (`__init__`), `:308-360` (`_build_vehicles_from_registry`); `lib/TWCManager/Vehicle/Registry/Sources.py` (`HomeAssistantReadSource`).
- Test: `tests/unit/test_homeassistant_registry.py`.

**Interfaces:**
- Produces:
  - `HomeAssistant.registry = VehicleRegistry.forMaster(master)` (before the enabled check).
  - `_build_vehicles_from_registry` (HA's device registry; unrelated name): for each `HaVehicle` built: `v = self.registry.getOrCreate(vin, "HomeAssistant")`, `v.attach("HomeAssistant", hv)`, `v.observe("name", name, "HomeAssistant")`, `v.claim("HomeAssistant", hv.has_charge_switch or hv.has_charge_limit_number or hv.has_charge_current_number, "entities")`.
  - `HaVehicle.refresh_from_home_assistant(api)`: after each successful parse also `v = api.registry.get(self.vin)` and, when `v` is not None, `v.observe(field, value, "HomeAssistant")` for `batteryLevel`, `chargeLimit`, `availableCurrent`, `lat`, `lon`, and `chargingState` (`"Charging"` when `charging` else `"Stopped"`).
  - `class HomeAssistantReadSource(ReadSource)`: `name="HomeAssistant"`, `order=1`, fields `CHARGE_FIELDS|LOCATION_FIELDS`; `canRead` = attachment present; `fetch` → `hv.refresh_from_home_assistant(ha)` and `{}`; registered in `HomeAssistant.__init__` once enabled.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_homeassistant_registry.py
from unittest.mock import Mock, patch
from TWCManager.Vehicle.HomeAssistant import HomeAssistant, HaVehicle
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

def make_ha():
    reg = VehicleRegistry({}); master = Mock(); master.vehicleRegistry = reg
    master.config = {"config": {}, "vehicle": {"HomeAssistant": {"enabled": True, "url": "http://ha", "longLivedToken": "x" * 40}}}
    with patch("TWCManager.Vehicle.HomeAssistant.requests.Session") as S:
        S.return_value.get.return_value = Mock(raise_for_status=Mock())
        with patch.object(HomeAssistant, "_discover_vehicles"):
            ha = HomeAssistant(master)
    return ha, reg

def test_discovered_vehicle_is_attached_and_claimed():
    ha, reg = make_ha()
    devices = [{"id": "d1", "name": "Car", "manufacturer": "Tesla", "identifiers": [["teslemetry", VIN]]}]
    with patch.object(ha, "_map_tesla_entities", return_value={"charge_switch": "switch.car_charge", "battery_level_sensor": "sensor.b"}):
        ha._build_vehicles_from_registry(devices, [])
    v = reg.get(VIN)
    assert isinstance(v.attachment("HomeAssistant"), HaVehicle) and v.tier == "managed" and v.name == "Car"

def test_refresh_observes_with_source():
    ha, reg = make_ha(); hv = HaVehicle("Car", VIN, "d1", {"battery_level_sensor": "sensor.b", "charge_limit_number": "number.l"})
    reg.getOrCreate(VIN, "HomeAssistant").attach("HomeAssistant", hv)
    ha._get_state = Mock(side_effect=lambda ent: {"sensor.b": {"state": "73"}, "number.l": {"state": "90"}}.get(ent))
    hv.refresh_from_home_assistant(ha)
    v = reg.get(VIN)
    assert (v.latest("batteryLevel").value, v.latest("batteryLevel").source) == (73.0, "HomeAssistant")
    assert v.latest("chargeLimit").value == 90.0

def test_read_source_registered():
    ha, reg = make_ha()
    assert [s.name for s in reg.readSources()] == ["HomeAssistant"]
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: registry`).

- [ ] **Step 3: Implement** per Interfaces (`_build_vehicles_from_registry` requires `manufacturer` containing "tesla" and both `battery_level_sensor` and `charge_switch` entities; the fixture above satisfies that).

- [ ] **Step 4: Run tests** → PASS; full suite.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/HomeAssistant.py lib/TWCManager/Vehicle/Registry/Sources.py
git add lib/TWCManager/Vehicle tests/unit/test_homeassistant_registry.py
git commit -m "Register HomeAssistant vehicles, claims and reads in the vehicle registry"
```

