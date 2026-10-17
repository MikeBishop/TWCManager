### Task 10: Vehicle endpoints from the order (closes A8, A17)

**Files:**
- Create: `lib/TWCManager/EVSEInstance/VehicleEndpoint.py`, `lib/TWCManager/EVSEController/VehicleEndpoints.py`.
- Delete: `lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py`, `lib/TWCManager/EVSEController/TeslaAPIController.py`, `tests/unit/test_teslaapi_controller.py`.
- Modify: `lib/TWCManager/TWCManager.py` (the `TeslaAPIController` registration block, `if master.getModuleByName("TeslaAPI") is not None:`, now registers `VehicleEndpoints`; same condition), docstrings naming the old classes: `lib/TWCManager/EVSEInstance/EVSEInstance.py:13-16`, `lib/TWCManager/EVSEController/EVSEController.py:17-18`, `lib/TWCManager/EVSEInstance/Gen3TWC.py:129` (Task 11's grep test requires none left), `tests/unit/test_telemetry_registry.py:9,254,258` (`VehicleEndpoints._telemetryPluggedIn`), `tests/unit/test_registry_callers.py:20-25` (the `getCarApiVehicles` grep list drops `TeslaAPIController.py`), `tests/unit/test_teslaapi_readonly_gate.py:212-230` (`TestTeslaAPIEVSE` → `VehicleEndpoint`, moved into the new test file).
- Test: `tests/unit/test_vehicle_endpoint.py`.

**Interfaces:**
- Consumes: `ProviderOrder.candidates(vehicle, SET_AMPS, amps)`, `vehicleMaxAmps`, `Vehicle.value()`, `master.queue_vehicle_command`, `master.startCarsCharging/stopCarsCharging`, `TWCSlave.reportedState/reportedAmpsActual/currentVIN`.
- Produces `class VehicleEndpoint(EVSEInstance):` `REFRESH_SECONDS = 600`; `__init__(self, vehicle, order, master, clock=time.time)`; `ID` = `"Vehicle-<vin>"`; `isLocal` `False`; `provider` → first candidate's name or `""`; `isReadOnly` → `not order.candidates(vehicle, SET_AMPS)`; `isCharging` → `vehicle.value("chargingState") == "Charging"`; `wantsToCharge` → `in ("Charging", "Stopped")`; `currentAmps` → `vehicle.value("actualCurrent", 0) or 0`; `currentVoltage` → today's `TeslaAPIEVSE` rule over `vehicle.value("voltage", 0)` / `vehicle.value("phases")`; `currentPower`; `minPower` → 5 A; `maxPower` → `vehicleMaxAmps(vehicle, configConfig)` in watts; `currentVIN` → `vehicle.vin`; `vehicleKey` → `vehicle.key`; `occupied` → `True` when `wantsToCharge` or `vehicle.value("pluggedIn") is True`, else `None`; `controllers` → `["VehicleEndpoints"]`; `setTargetPower(watts)`: `0` → return (a stop is a stop command, never `setAmps(0)`); else `amps = max(1, int(convertWattsToAmps(...)))`, and when `amps != self._lastAmps or clock() - self._lastQueuedAt >= REFRESH_SECONDS`: `master.queue_vehicle_command({"cmd": "setAmps", "vin": vehicle.vin, "amps": amps})` and record. Never calls a provider directly (serial thread). `startCharging`/`stopCharging` → `master.startCarsCharging(vin)`/`stopCarsCharging(vin)` as today.
- Produces `class VehicleEndpoints(EVSEController):` `name = "VehicleEndpoints"`; `__init__(self, master)`; `_cache: Dict[str, VehicleEndpoint]`; `POWER_FLOWING_AMPS = 1.0`; `_blindTWCs(self) -> Tuple[bool, bool]` (`blind`, `unknown`): a slave names its car when its `vehicleKey` is a VIN (Task 3's rule: `currentVIN`, else `lastVIN` while the TWC reports a plugged state — so a stopped car does not blind the install); a slave is unknown when `vehicleKey` is `None` or starts with `anon:`, and blind when such an unknown slave reports `reportedState != 0x00` or draws `>= POWER_FLOWING_AMPS`; a scan failure is `(True, True)`; also `blind` when a Gen3 unit — `master.getModuleByName("Gen3TWCs").devices()` when that module exists — has `occupied is True` and a `vehicleKey` starting with `"anon:"`: an uncorrelated car on a Gen3 could be any account car, so no vehicle endpoint, hence no Fleet amps, while it is held anonymous, G3); `@staticmethod _telemetryPluggedIn(vehicle)` unchanged; `allEVSEs`: `[]` when TeslaAPI is absent/disabled or `blind`; otherwise one cached `VehicleEndpoint` per non-anonymous registry vehicle with `car = vehicle.attachment("TeslaAPI")` present, `car.atHome` true, and not (`unknown` and `_telemetryPluggedIn(car)`); cache entries for other VINs dropped. The served-VIN exclusion goes: an endpoint for a car on a named TWC is merged into that TWC's point by Task 11's grouping. Read-only endpoints are still listed (the distributor skips them).
- Produces (`TWCManager.py`): registers `{"name": "VehicleEndpoints", "ref": VehicleEndpoints(master), "type": "EVSEController"}` when `master.getModuleByName("TeslaAPI") is not None` (today's condition; BLE-only and HA-only installs keep the per-slave path until Phase 4).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_vehicle_endpoint.py
from types import SimpleNamespace
from unittest.mock import Mock
from TWCManager.EVSEController.VehicleEndpoints import VehicleEndpoints
from TWCManager.EVSEInstance.VehicleEndpoint import VehicleEndpoint
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Order import ProviderOrder
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from tests.unit.test_provider_order import ble, fleet, twc
VIN1 = "5YJ3E1EA1KF000001"; VIN2 = "5YJ3E1EA1KF000002"

class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def master(settings=None, *providers, slaves=()):
    m = Mock(); m.settings = settings or {}; m.config = {"config": {"wiringMaxAmpsPerTWC": 32, "defaultVoltage": 240}}
    m.stats = {"moduleSuccess": {}, "moduleFailures": {}}; m.vehicleRegistry = VehicleRegistry({}); m.providerOrder = ProviderOrder(m)
    for p in providers: m.providerOrder.register(p)
    carapi = Mock(); carapi.enabled.return_value = True
    m.getModuleByName = lambda n: carapi if n == "TeslaAPI" else None; m.getSlaveTWCs = lambda: list(slaves); return m

def car(m, vin, atHome=True, syncSource="TeslaAPI", pluggedIn=None):
    v = m.vehicleRegistry.getOrCreate(vin, "TeslaAPI"); v.attach("TeslaAPI", SimpleNamespace(VIN=vin, atHome=atHome, syncSource=syncSource, pluggedIn=pluggedIn)); return v

def slave(key=None, amps=0.0, state=0x00): return SimpleNamespace(vehicleKey=key, reportedAmpsActual=amps, reportedState=state)

def test_read_only_when_no_amps_candidate_and_ble_only_excludes_fleet():   # A17
    m = master({"commandPolicy": "ble_only"}, fleet()); e = VehicleEndpoint(car(m, VIN1), m.providerOrder, m)
    assert e.isReadOnly and e.provider == ""
    m2 = master({}, fleet()); e2 = VehicleEndpoint(car(m2, VIN1), m2.providerOrder, m2)
    assert not e2.isReadOnly and e2.provider == "FleetAPI" and e2.ID == "Vehicle-" + VIN1 and e2.vehicleKey == VIN1

def test_state_from_registry_values_without_reads():
    m = master({}, fleet()); v = car(m, VIN1); e = VehicleEndpoint(v, m.providerOrder, m); v.read = Mock(side_effect=AssertionError("no reads"))
    assert not e.wantsToCharge and e.occupied is None and e.maxPower == 32 * 240 and e.minPower == 5 * 240
    v.observe("chargingState", "Stopped", "TeslaAPI"); v.observe("availableCurrent", 16, "TeslaAPI"); v.observe("actualCurrent", 0, "TeslaAPI")
    assert e.wantsToCharge and not e.isCharging and e.occupied is True and e.maxPower == 16 * 240

def test_set_target_power_queues_on_change_or_after_refresh():
    c = Clock(); m = master({}, fleet()); e = VehicleEndpoint(car(m, VIN1), m.providerOrder, m, clock=c)
    e.setTargetPower(0); m.queue_vehicle_command.assert_not_called()
    e.setTargetPower(2400); e.setTargetPower(2400)
    m.queue_vehicle_command.assert_called_once_with({"cmd": "setAmps", "vin": VIN1, "amps": 10})
    c.t += 600; e.setTargetPower(2400); assert m.queue_vehicle_command.call_count == 2
    e.setTargetPower(100); assert m.queue_vehicle_command.call_args.args[0]["amps"] == 1

def test_controller_lists_at_home_api_cars_and_keeps_blind_rules():
    m = master({}, fleet()); car(m, VIN1); car(m, VIN2, atHome=False); m.vehicleRegistry.beginPlugSession("8244")
    ctl = VehicleEndpoints(m)
    assert [e.currentVIN for e in ctl.allEVSEs] == [VIN1] and ctl.allEVSEs[0] is ctl.allEVSEs[0]
    m.getSlaveTWCs = lambda: [slave(amps=5.0)]; assert ctl.allEVSEs == []                                 # blind VIN-less TWC
    m.getSlaveTWCs = lambda: [slave()]; car(m, VIN2, pluggedIn=True, syncSource="TeslaMateVehicle"); m.vehicleRegistry.get(VIN2).attachment("TeslaAPI").atHome = True
    assert [e.currentVIN for e in ctl.allEVSEs] == [VIN1]                                                  # unknown TWC + telemetry plug
    m.getSlaveTWCs = lambda: [slave(key=VIN1)]
    assert sorted(e.currentVIN for e in ctl.allEVSEs) == [VIN1, VIN2]                                      # named TWC: grouping merges, not exclusion

def test_last_vin_plugged_twc_keeps_other_cars_listed():                           # Review Focus 5 / I5
    m = master({}, fleet()); car(m, VIN1); car(m, VIN2)
    m.getSlaveTWCs = lambda: [slave(key=VIN1, state=0x03)]                      # stopped car: currentVIN cleared, lastVIN attributed
    assert sorted(e.currentVIN for e in VehicleEndpoints(m).allEVSEs) == [VIN1, VIN2]
    m.getSlaveTWCs = lambda: [slave(key="anon:8244", state=0x03)]
    assert VehicleEndpoints(m).allEVSEs == []

def test_controller_empty_without_tesla_api():
    m = master({}, ble()); m.getModuleByName = lambda n: None; car(m, VIN1)
    assert VehicleEndpoints(m).allEVSEs == []

def test_anonymous_car_on_a_gen3_is_blind_but_a_correlated_one_is_not():           # G3
    m = master({}, fleet()); car(m, VIN1); carapi = m.getModuleByName("TeslaAPI")
    gen3 = Mock(); gen3.devices = lambda: [SimpleNamespace(occupied=True, vehicleKey="anon:Gen3TWC-10.0.0.1")]
    m.getModuleByName = lambda n: {"TeslaAPI": carapi, "Gen3TWCs": gen3}.get(n)
    assert VehicleEndpoints(m).allEVSEs == []
    gen3.devices = lambda: [SimpleNamespace(occupied=True, vehicleKey=VIN1)]
    assert [e.currentVIN for e in VehicleEndpoints(m).allEVSEs] == [VIN1]
```
Move `TestTeslaAPIEVSE`'s two cases here as `test_read_only_follows_fleet_slot` (an Owner-only `TeslaAPI` → `FleetAPIProvider.ready` False → read-only) using `tests.unit.test_carapivehicle_registry.api_with_registry`.

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `VehicleEndpoints`).

- [ ] **Step 3: Implement** per Interfaces; delete the three old files and the old test; update the listed tests.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_vehicle_endpoint.py tests/unit/test_telemetry_registry.py tests/unit/test_registry_callers.py tests/unit/test_teslaapi_readonly_gate.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/EVSEInstance/ lib/TWCManager/EVSEController/ lib/TWCManager/TWCManager.py
git add -A lib/TWCManager/EVSEInstance lib/TWCManager/EVSEController lib/TWCManager/TWCManager.py tests/unit
git commit -m "Replace TeslaAPIEVSE/TeslaAPIController with order-driven vehicle endpoints that queue amps"
```

