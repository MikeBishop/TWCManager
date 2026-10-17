### Task 8: Telemetry and HomeAssistant providers; provider registration at startup; read order by cost (closes A9, A10 basis)

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/TelemetryProvider.py`, `lib/TWCManager/Vehicle/Providers/HomeAssistantProvider.py`.
- Modify: `lib/TWCManager/Vehicle/Telemetry.py` (`providers()`), `lib/TWCManager/Vehicle/HomeAssistant.py:264` (`self.readSource`, `providers()`), `lib/TWCManager/Vehicle/Registry/Sources.py:106-110` (`HomeAssistantReadSource.provider = "HomeAssistant"`), `lib/TWCManager/TWCManager.py` (call `registerProviders(master)` after the module-load loop, i.e. before the `TeslaAPIController` registration block `if master.getModuleByName("TeslaAPI") is not None:`; call `master.providerOrder.suppressions.noticeOnce()` right after `master.loadSettings()`, where a settings-based `api_only` is finally known).
- Test: `tests/unit/test_provider_registration.py`.

**Interfaces:**
- Consumes: `TelmetryBase.feedLiveAt(vehicle)`, `HomeAssistant.enabled()`, `.setChargeRate(amps, vehicle=HaVehicle)`, `HaVehicle.has_charge_switch/has_charge_current_number/has_charge_limit_number`.
- Produces `class TelemetryProvider(Provider):` `rank = 3`, `local = False`, `module = None`, `readSource = None`; `__init__(self, telemetry)`: `name = telemetry.__class__.__name__` (`"TeslaMateVehicle"` / `"FleetTelemetryMQTT"`, the registry's liveness/source name); `declarations()`: `READ_CHARGE`, `READ_LOCATION`, `READ_PLUG`, `READ_ONLINE` → `Declaration(CLOUD_FREE, passive=True)`; `ready(vehicle, cap)` → `telemetry.feedLiveAt(vehicle)` is a number. `TelmetryBase.providers()` → `[TelemetryProvider(self)]`.
- Produces `class HomeAssistantProvider(Provider):` `name = "HomeAssistant"`, `rank = 6`, `local = False`; `__init__(self, ha)`: `module = ha`, `readSource = ha.readSource`; `declarations()`: `READ_CHARGE`, `READ_LOCATION` → `Declaration(HA_BILLED)`; `SET_CHARGE_LIMIT`, `START_CHARGING`, `STOP_CHARGING`, `SET_AMPS` → `Declaration(HA_BILLED)` (HA's Tesla integration is commonly the user's own Fleet app; price unknown, treated as billed and ranked after Fleet, as the spec lists it and Phase 1 ruled for reads); no `WAKE`; `ready(vehicle, cap)`: `ha.enabled()` and `hv = vehicle.attachment("HomeAssistant")` present, and for `SET_AMPS` `hv.has_charge_current_number`, for `START_CHARGING`/`STOP_CHARGING` `hv.has_charge_switch`, for `SET_CHARGE_LIMIT` `hv.has_charge_limit_number`; `ampsRange` → `(1, vehicleMaxAmps(vehicle, ha.master.config["config"]))`, read on every call; `setAmps(vin, amps)` → `hv = ha.registry.get(vin)` → `.attachment("HomeAssistant")` (`False` when either is missing), then `bool(ha.setChargeRate(amps, vehicle=hv))`. `HomeAssistant.providers()` → `[HomeAssistantProvider(self)]`; `self.readSource = HomeAssistantReadSource(self)` (still registered).
- Produces (`TWCManager.py`): one call to `registerProviders(master)` (Task 2, `Providers/Order.py`) after the module-load loop, and `master.providerOrder.suppressions.noticeOnce()` right after `master.loadSettings()`. Nothing new is defined in `TWCManager.py` (it starts the app at import).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_registration.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.HomeAssistantProvider import HomeAssistantProvider
from TWCManager.Vehicle.Providers.Order import ProviderOrder, registerProviders
from TWCManager.Vehicle.Providers.TelemetryProvider import TelemetryProvider
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from tests.unit.test_homeassistant_registry import make_ha
from tests.unit.test_provider_order import ble as bleStub   # the Phase 1 fixture: (ha, registry)
VIN = "5YJ3E1EA1KF000001"
live = {"at": 100.0}

class TeslaMateVehicle:                                   # the provider takes its name from the module's class
    def feedLiveAt(self, vehicle=None): return live["at"]

def test_telemetry_provider_is_passive_free_and_ready_while_live():
    live["at"] = 100.0; p = TelemetryProvider(TeslaMateVehicle())
    assert (p.name, p.rank, p.readSource, p.module) == ("TeslaMateVehicle", 3, None, None)
    assert p.declarations()[C.READ_PLUG] == C.Declaration(C.CLOUD_FREE, passive=True) and p.ready(None, C.READ_PLUG)
    live["at"] = None; assert p.ready(None, C.READ_PLUG) is False

def test_home_assistant_provider_follows_entities():
    ha, reg = make_ha(); (p,) = ha.providers(); v = reg.getOrCreate(VIN, "t")
    assert (p.name, p.rank, p.cost(C.SET_AMPS), p.readSource.provider) == ("HomeAssistant", 6, C.HA_BILLED, "HomeAssistant")
    assert p.ready(v, C.SET_AMPS) is False
    hv = Mock(has_charge_switch=True, has_charge_current_number=False, has_charge_limit_number=True); v.attach("HomeAssistant", hv)
    assert p.ready(v, C.START_CHARGING) and p.ready(v, C.SET_CHARGE_LIMIT) and not p.ready(v, C.SET_AMPS) and not p.declares(C.WAKE)
    ha.setChargeRate = Mock(return_value=True); hv.has_charge_current_number = True
    assert p.setAmps(VIN, 8) is True; ha.setChargeRate.assert_called_once_with(8, vehicle=hv)

def test_passive_providers_never_enter_the_walk():
    m = Mock(); m.settings = {}; m.config = {}; m.stats = {"moduleSuccess": {}, "moduleFailures": {}}; m.vehicleRegistry = VehicleRegistry({})
    o = ProviderOrder(m); live["at"] = 1.0
    o.register(TelemetryProvider(TeslaMateVehicle()))
    assert o.ordered(C.READ_PLUG) == [] and [p.name for p in o.providers()] == ["TeslaMateVehicle"]

def test_register_providers_collects_every_vehicle_module_in_rank_order():
    m = Mock(); m.settings = {}; m.config = {}; m.stats = {}; m.vehicleRegistry = VehicleRegistry({}); m.providerOrder = ProviderOrder(m)
    ha, reg = make_ha(); ble = Mock(); ble.providers = lambda: [bleStub()]
    m.getModulesByType = Mock(return_value=[{"name": "HomeAssistant", "ref": ha}, {"name": "TeslaBLE", "ref": ble}, {"name": "VehiclePriority", "ref": object()}])
    assert registerProviders(m) == ["TeslaBLE", "HomeAssistant"]      # rank order, not module order
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `TelemetryProvider`).

- [ ] **Step 3: Implement** per Interfaces. `TWCManager.py` only gains the two calls (`registerProviders(master)` after the module loop; `noticeOnce()` after `loadSettings()`); both run on every install, and a pure-Gen2 install registers nothing new.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_registration.py tests/unit/test_homeassistant_registry.py tests/unit/test_telemetry_registry.py tests/unit/test_twcmanager.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/ lib/TWCManager/TWCManager.py
git add lib/TWCManager tests/unit/test_provider_registration.py
git commit -m "Add telemetry and HomeAssistant providers and register every module's providers at startup"
```

