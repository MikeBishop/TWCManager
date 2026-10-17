### Task 9: `VehiclePriority` as a façade over the order (closes A1, A2, A10, A26)

The module keeps its name, its `commandPolicy` properties and its method-call shape (every caller passes module-specific arguments: `car_api_charge(task)`, `applyChargeLimit(limit, vin=…)`, `setChargeRate(amps, vehicle)`, `startCharging(vin)`, `wakeVehicle(vin|vehicle)`), but the walk is the order: providers' legacy modules in order position, suppressed ones skipped, and — when the call names a vehicle — providers not ready for it skipped. HomeAssistant joins the walk at the end. Phase 3 removes the façade.

**Files:**
- Modify: `lib/TWCManager/Vehicle/VehiclePriority.py` (rewrite), `lib/TWCManager/VehicleCommandQueue.py:33-40` (`setAmps`), `lib/TWCManager/Vehicle/TeslaAPI.py:200-225` (delete `apiDebugInterface`), `lib/TWCManager/Control/HTTPControl.py:915-937` (`/api/sendTeslaAPICommand`), `lib/TWCManager/Control/themes/Default/settings.html.j2` (the `chargeStopMode`, `chargeRateControl` and `commandPolicy` `optionList` blocks; relabels), `docs/Settings.md`, `CHANGELOG.md`.
- Test: `tests/unit/test_vehicle_priority.py` (rewrite: drop `TestRetryCalculation`, `TestPriorityOrdering` and every `getModuleByPriority` fixture), `tests/unit/test_teslaapi_readonly_gate.py:170-210` (the four `TestVehiclePriority…` tests rebuilt on the order; `TestTeslaAPIEVSE` moves to Task 10), `tests/unit/test_registry_callers.py:163-185` (the debug-route tests, including `test_send_teslaapi_command_without_teslaapi_is_400`, which now sets `master.providerOrder.debugCommand.return_value = False` and still expects 400), `tests/unit/test_carapivehicle_registry.py:130-140` (`apiDebugInterface` tests → `providerOrder.debugCommand` on a master whose order holds `api.providers()`, after `api.storeToken(fleet_token())` so `FleetAPIProvider.ready(WAKE)` holds).

**Interfaces:**
- Consumes: `ProviderOrder.ordered/candidates/dispatch/debugCommand`, `Suppressions.commandPolicy/commandPolicyOverridden/VALID_COMMAND_POLICIES`, `Provider.module/attempts/local`.
- Produces (`VehiclePriority`):
  - `COMMAND_METHODS` unchanged; `COMMAND_CAPABILITIES = {"car_api_charge": None, "setChargeRate": SET_AMPS, "startCharging": START_CHARGING, "stopCharging": STOP_CHARGING, "applyChargeLimit": SET_CHARGE_LIMIT, "wakeVehicle": WAKE}` (`car_api_charge` resolves to `STOP_CHARGING` when `task.get("charge") is False`, else `START_CHARGING`).
  - `__init__(self, master)`: `self.master`, `self.order = master.providerOrder`; `commandPolicy`, `commandPolicyOverridden`, `VALID_COMMAND_POLICIES` delegate to `self.order.suppressions`; `updateSettings()` → `True`.
  - `@staticmethod targetVIN(name, args, kwargs) -> Optional[str]`: `car_api_charge` → `args[0].get("vin")` when a dict; `applyChargeLimit` → `kwargs.get("vin")`; `setChargeRate` → the `vehicle` (second positional or kwarg): `getattr(v, "VIN", None) or getattr(v, "vin", None) or (v if isinstance(v, str) else None)`; `startCharging`/`stopCharging`/`wakeVehicle` → the first argument by the same rule; upper-cased; `None` when absent (a broadcast).
  - `@staticmethod targetAmps(name, args, kwargs) -> Optional[float]`: `setChargeRate` → `args[0]`/`kwargs["charge_rate"]` as float when numeric; else `None`.
  - `modulesFor(self, name, args, kwargs) -> List[Tuple[Provider, Any]]` (provider, its legacy module), distinct modules in order: for a command method, `candidates(vehicle, cap, amps)` when `targetVIN` resolves to a registry vehicle, else `ordered(cap)`; for any other method, `self.order.providers()` minus those `suppressions.suppressed(p, READ_CHARGE)` (so `api_only` keeps BLE out of reads too, as `orderReadSources` does); providers with `module is None` are skipped; the same module appearing under two providers (Owner and Fleet) is kept once at its first position with that provider's attempts.
  - `__getattr__(name)` → a method that walks `modulesFor(...)` exactly as today's loop does (skip modules lacking the attribute; `ret and ret != "error"` wins; `attempts` tries; `master.stats["moduleSuccess"/"moduleFailures"]` keyed by the provider's name; exceptions logged by type name), returning `False` when nothing succeeds or no module exists. `modulesFor` therefore returns `(provider, module)` pairs; attempts come from the provider.
  - `setAmps(self, vin, amps) -> bool` (explicit, not via `__getattr__`): `vehicle = registry.get(vin)`; `False` when `None`; else `self.order.dispatch(vehicle, SET_AMPS, lambda p: p.setAmps(vin, amps), amps=amps)`.
- Produces (`VehicleCommandQueue._DISPATCH`): `"setAmps": lambda module, task: _setAmps(module, task)` where module-level `_setAmps` calls `getattr(module, "setAmps", None)`; when the resolved module lacks it (VehiclePriority disabled in config, so the fallback is HA/BLE/TeslaAPI) it logs one DEBUG line and returns `False` (keyed `("setAmps", vin)` by the generic rule).
- Produces (`HTTPControl` `/api/sendTeslaAPICommand`): `res = master.providerOrder.debugCommand(command, vin, params)`; 200 when `True`, else 400; the `TeslaAPI is None → 400` check goes (BLE-only installs can wake over BLE from the debug page).
- Produces (`settings.html.j2`): `chargeRateControl` labels `Use TWC exclusively to control charge rate` / `Use a vehicle command (BLE or API) exclusively to control charge rate` / `Use TWC >= 6A + vehicle command (BLE or API) < 6A`; `commandPolicy` labels `Prefer local (BLE), fall back to cloud` / `Local only - never send billed cloud commands` / `Cloud only - never use BLE`; `chargeStopMode` option 1 label `Vehicle command (BLE or API)`.
- Produces (`docs/Settings.md`): a "Vehicle Command Policy" section stating the three values and their suppression meaning, and a "providerSuppressions" paragraph with the JSON shape, provider names (`Gen2TWC`, `TeslaBLE`, `OwnerAPI`, `FleetAPI`, `HomeAssistant`) and capability names.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_vehicle_priority.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Order import ProviderOrder
from TWCManager.Vehicle.Providers.Provider import Provider
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.VehiclePriority import VehiclePriority
VIN = "5YJ3E1EA1KF000001"
CMDS = {c: C.Declaration(C.LOCAL) for c in (C.SET_AMPS, C.START_CHARGING, C.STOP_CHARGING, C.SET_CHARGE_LIMIT, C.WAKE)}

class P(Provider):
    def __init__(self, name, rank, local, module, ready=True, caps=CMDS, amps=(1, 32)):
        self.name, self.rank, self.local, self.module, self._ready, self._caps, self._amps = name, rank, local, module, ready, caps, amps
    def declarations(self): return self._caps
    def ready(self, vehicle, cap): return self._ready
    def ampsRange(self, vehicle): return self._amps
    def setAmps(self, vin, amps): return self.module.setAmps(vin, amps)

def make(settings=None, *providers):
    m = Mock(); m.settings = settings or {}; m.config = {}; m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    m.vehicleRegistry = VehicleRegistry({}); m.providerOrder = ProviderOrder(m)
    for p in providers: m.providerOrder.register(p)
    return m, VehiclePriority(m)

def mod(**results):
    x = Mock(spec=list(results)); [setattr(x, k, Mock(return_value=v)) for k, v in results.items()]; return x

def test_command_policy_properties_delegate():
    m, vp = make({"commandPolicy": "ble_only"})
    assert vp.commandPolicy == "ble_only" and vp.commandPolicyOverridden is False and vp.updateSettings() is True

def test_no_modules_returns_false():                              # Review Focus 2
    m, vp = make()
    assert vp.startCharging(VIN) is False and vp.car_api_charge({"charge": True}) is False

def test_walk_is_order_position_with_local_three_attempts_and_ha_last():
    ble = mod(startCharging=False); api = mod(startCharging=False); ha = mod(startCharging=True)
    m, vp = make({}, P("HomeAssistant", 6, False, ha), P("FleetAPI", 5, False, api), P("TeslaBLE", 2, True, ble))
    assert vp.startCharging(VIN) is True
    assert (ble.startCharging.call_count, api.startCharging.call_count, ha.startCharging.call_count) == (3, 2, 1)
    assert m.stats["moduleFailures"] == {"TeslaBLE": 1, "FleetAPI": 1} and m.stats["moduleSuccess"] == {"HomeAssistant": 1}

def test_ble_only_skips_cloud_commands_but_not_reads():
    ble = mod(startCharging=False, updateChargeAtHome=False); api = mod(startCharging=True, updateChargeAtHome=True)
    m, vp = make({"commandPolicy": "ble_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    assert vp.startCharging(VIN) is False and api.startCharging.call_count == 0
    assert vp.updateChargeAtHome() is True and api.updateChargeAtHome.call_count == 1

def test_api_only_walks_fleet_without_ble():                      # Review Focus 1
    ble = mod(applyChargeLimit=True, updateChargeAtHome=True); api = mod(applyChargeLimit="success", updateChargeAtHome=True)
    m, vp = make({"commandPolicy": "api_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    assert vp.applyChargeLimit(limit=80) == "success" and ble.applyChargeLimit.call_count == 0
    assert vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0        # reads too: no BLE timeout

def test_broadcast_skips_a_provider_that_is_not_available():
    api = mod(applyChargeLimit="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    m, vp = make({}, f)
    assert vp.applyChargeLimit(limit=80) is False and api.applyChargeLimit.call_count == 0 and m.stats["moduleFailures"] == {}

def test_targeted_call_skips_providers_not_ready_for_that_car():
    ble = mod(applyChargeLimit=True); api = mod(applyChargeLimit="success")
    m, vp = make({}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api))
    m.vehicleRegistry.getOrCreate(VIN, "t")
    assert vp.applyChargeLimit(limit=80, vin=VIN) == "success" and ble.applyChargeLimit.call_count == 0
    assert vp.applyChargeLimit(limit=80) is True and ble.applyChargeLimit.call_count == 1      # broadcast: readiness unknown

def test_set_charge_rate_target_and_amps_apply_the_default_fleet_rule():
    twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = mod(setChargeRate=True)
    m, vp = make({}, twc, P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)})); m.vehicleRegistry.getOrCreate(VIN, "t")
    car = Mock(VIN=VIN)
    assert vp.setChargeRate(10, car) is False and api.setChargeRate.call_count == 0            # TWC covers 10 A
    assert vp.setChargeRate(4, car) is True and api.setChargeRate.call_args.args == (4, car)   # below the floor
    assert VehiclePriority.targetVIN("setChargeRate", (10, car), {}) == VIN and VehiclePriority.targetVIN("wakeVehicle", (VIN.lower(),), {}) == VIN
    assert VehiclePriority.targetVIN("car_api_charge", ({"charge": False, "vin": VIN},), {}) == VIN

def test_set_amps_dispatches_through_the_order():
    ble = Mock(); ble.setAmps = Mock(return_value=True)
    m, vp = make({}, P("TeslaBLE", 2, True, ble)); m.vehicleRegistry.getOrCreate(VIN, "t")
    assert vp.setAmps(VIN, 12) is True and ble.setAmps.call_args.args == (VIN, 12)
    assert vp.setAmps("5YJ3E1EA1KF000009", 12) is False

def test_queue_dispatches_set_amps():
    from TWCManager.VehicleCommandQueue import VehicleCommandQueue
    vp = Mock(); vp.setAmps = Mock(return_value=True); q = VehicleCommandQueue(lambda: vp)
    assert q._execute({"cmd": "setAmps", "vin": VIN, "amps": 7}) is True and VehicleCommandQueue._key({"cmd": "setAmps", "vin": VIN}) == ("setAmps", VIN)
    assert VehicleCommandQueue(lambda: Mock(spec=[]))._execute({"cmd": "setAmps", "vin": VIN, "amps": 7}) is False   # fallback module without setAmps
```
Rebuild `test_teslaapi_readonly_gate.py`'s `TestVehiclePriority…` cases on this `make()` with a real `TeslaAPI` from `api_with_registry()` and its `api.providers()`: read-only (Owner-only) → `FleetAPIProvider.available(cap)` False for commands, so a broadcast never reaches TeslaAPI (`"FleetAPI" not in moduleFailures`); after `storeToken(fleet_token())` it does; reads unaffected. In `test_registry_callers.py`, the debug-route test asserts `master.providerOrder.debugCommand.assert_called_once_with("wakeVehicle", VIN, "{}")` and that a 200 follows `True`; in `test_carapivehicle_registry.py` the two `apiDebugInterface` assertions become `master.providerOrder.debugCommand(...)` on a master whose order holds `api.providers()`.

- [ ] **Step 2: Run to verify failure** — `$PYTEST tests/unit/test_vehicle_priority.py -q --timeout=60 -p no:cacheprovider` → FAIL (`AttributeError: 'VehiclePriority' object has no attribute 'order'`).

- [ ] **Step 3: Implement** per Interfaces; delete `TeslaAPI.apiDebugInterface`; relabel the template; write the docs section.

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Architecture`: `    * (@MikeBishop) - Vehicle channels are providers that declare capabilities with per-operation cost and locality; commands walk a fixed order (TWC, BLE, then cloud; billed last) with per-provider suppressions (settings providerSuppressions); commandPolicy maps onto them; HomeAssistant, when loaded, joins the command order last (after Fleet) and is suppressed under ble_only; the debug API goes through the same order`.
```bash
black lib/TWCManager/Vehicle/VehiclePriority.py lib/TWCManager/VehicleCommandQueue.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager tests/unit docs/Settings.md CHANGELOG.md
git commit -m "Make VehiclePriority a facade over the provider order; route the debug API through it"
```

