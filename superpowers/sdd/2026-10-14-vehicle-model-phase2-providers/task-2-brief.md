### Task 2: Suppressions and the fixed `ProviderOrder`

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/Suppressions.py`, `lib/TWCManager/Vehicle/Providers/Order.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/ReadSource.py:11-13` (add `provider`), `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py:246-257` (`useReadOrder`, `readSources`), `lib/TWCManager/Vehicle/Providers/__init__.py`.
- Test: `tests/unit/test_provider_order.py`.

**Interfaces:**
- Consumes: `Provider`, `Declaration`, `Cost`, capability names (Task 1); `master.settings`, `master.config`, `master.stats`, `master.vehicleRegistry`.
- Produces (`Suppressions.py`) `class Suppressions:`
  - `VALID_COMMAND_POLICIES = ("prefer_ble", "ble_only", "api_only")`; `__init__(self, master)`; property `commandPolicy -> str` (config `vehicle.commandPolicy` when valid — an invalid config value logs an error once and is ignored, as `VehiclePriority` does today — else `settings["commandPolicy"]`, invalid → `"prefer_ble"`); property `commandPolicyOverridden -> bool`.
  - `explicit(self) -> Dict[str, FrozenSet[str]]`: `settings.get("providerSuppressions")` with config `vehicle.providerSuppressions` merged over it; shape `{"FleetAPI": ["setAmps", "wake"], "HomeAssistant": ["*"]}` (`"*"` → `ALL`); anything not a dict of str → list-of-str, and any name not in `ALL`, is ignored (DEBUG log, never raises).
  - `suppressed(self, provider, capability) -> bool`: explicit entry; or `ble_only` and `not provider.local` and `capability in COMMANDS`; or `api_only` and `provider.name == "TeslaBLE"` (every capability: today `api_only` blocks BLE commands and the BLE read source). `prefer_ble` adds nothing.
  - `noticeOnce(self)`: when `commandPolicy == "api_only"` logs INFO once per `Suppressions` instance (an instance flag, so tests stay order-independent): `commandPolicy api_only: TeslaBLE is suppressed for every operation (set providerSuppressions for finer control)`.
- Produces (`Order.py`) `class ProviderOrder:`
  - `__init__(self, master, suppressions: Optional[Suppressions] = None)` (`Suppressions(master)` by default); attribute `suppressions`.
  - `register(self, provider) -> None` (replaces a same-named provider); `provider(self, name) -> Optional[Provider]`; `providers(self) -> List[Provider]` sorted by `(rank, registration index)`.
  - `orderKey(self, provider, capability) -> tuple` = `(provider.cost(capability).tier, provider.rank, index)`.
  - `ordered(self, capability) -> List[Provider]`: providers declaring `capability`, not passive, not suppressed, and `available(capability)`, sorted by `orderKey`.
  - `candidates(self, vehicle, capability, amps: Optional[float] = None) -> List[Provider]`: `ordered(capability)` filtered by `provider.ready(vehicle, capability)`; when `amps` is given, a candidate whose `ampsRange(vehicle)` is known and does not cover `amps` is dropped (spec, layered actuators: outside the preferred provider's range the next provider carries T); then, for `SET_AMPS`, the **default paid-amps rule**: a local candidate counts as "a local amps path" when `amps is None or provider.covers(vehicle, amps)`; when one exists, candidates with `cost.tier >= TIER_BILLED` are dropped (spec: "Fleet never sets amps" only when the charging point has a local way to set amps). A `ready()` that raises counts as not ready (DEBUG, type name only).
  - `orderReadSources(self, sources: List[ReadSource]) -> List[ReadSource]`: keeps sources whose owning provider (`self.provider(source.provider)`) is absent or not suppressed for `READ_CHARGE`; sorts by `(min tier over the provider's READ_* declarations, provider.rank, source.order, index)`, with an unknown provider sorted as tier 9 / rank 999 (Phase 1's `order` then decides).
  - `dispatch(self, vehicle, capability, call: Callable[[Provider], Any], amps=None) -> Any`: for each of `candidates(vehicle, capability, amps)`, up to `provider.attempts()` tries of `call(provider)`; the first result that is truthy and not `"error"` is returned and `master.stats["moduleSuccess"][provider.name]` incremented; an exhausted provider increments `moduleFailures`; exceptions are logged at DEBUG by type name and count as a failed attempt; returns `False` when nothing succeeds. Providers with `module is None` (the TWC providers) are skipped by `dispatch`: a dispatched vehicle command runs on the HTTP or worker thread and must not write a TWC target (`_evseTargetAmps` would latch and override policy wherever the distributor is off); they still count as the local amps path in `candidates`, and the TWC target stays the distributor's alone until Phase 3. Never holds a lock.
  - `registerProviders(master) -> List[str]` (module-level in `Order.py`, called from `TWCManager.py` after the module-load loop; it lives here because `TWCManager.py` starts the app at import and nothing in it is importable by tests): `for mod in master.getModulesByType("Vehicle"): for provider in getattr(mod["ref"], "providers", lambda: [])(): master.providerOrder.register(provider)`; returns the registered names in rank order and logs INFO `Providers: <names>`.
  - `debugCommand(self, command: str, vin: str, parameters: str) -> bool` (closes A26): `vehicle = master.vehicleRegistry.get(vin)` (`None` → `False`); `"setChargeRate"` → `dispatch(vehicle, SET_AMPS, lambda p: p.setAmps(vin, amps), amps=amps)` with `amps = max(1, int(float(json.loads(parameters).get("charge_rate", 0))))` (bad JSON → `{}`; vehicle amps are never 0, and 0 would drop every candidate); `"wakeVehicle"` → `dispatch(vehicle, WAKE, lambda p: p.wake(vin))`; other commands → `False`; result is `bool(...)`.
- Produces (`ReadSource`): class attribute `provider: str = ""` (name of the owning provider; `""` = unowned).
- Produces (`VehicleRegistry`): `useReadOrder(self, fn: Optional[Callable[[List[ReadSource]], List[ReadSource]]]) -> None` (stored as `self._readOrder`); `readSources()` returns `fn(registered)` when one is installed (registered = the registration-ordered list), else the Phase 1 `(order, index)` sort.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_order.py
import logging
from unittest.mock import Mock
import pytest
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Order import ProviderOrder
from TWCManager.Vehicle.Providers.Provider import Provider
from TWCManager.Vehicle.Providers.Suppressions import Suppressions
from TWCManager.Vehicle.Registry.ReadSource import ReadSource
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

class P(Provider):
    def __init__(self, name, rank, local, caps, ready=True, amps=None, readTier=None):
        self.name, self.rank, self.local, self._caps, self._ready, self._amps = name, rank, local, caps, ready, amps
        self.calls = []; self.module = Mock()          # dispatch skips module-less (TWC) providers
        if readTier is not None:
            self.readSource = ReadSource(); self.readSource.name = name; self.readSource.provider = name
            self._caps = dict(self._caps, **{C.READ_CHARGE: C.Declaration(C.Cost(readTier))})
    def declarations(self): return self._caps
    def ready(self, vehicle, cap): return self._ready
    def ampsRange(self, vehicle): return self._amps
    def setAmps(self, vin, amps): self.calls.append(("setAmps", vin, amps)); return self._result
    def wake(self, vin): self.calls.append(("wake", vin)); return self._result
    _result = True

def twc(ready=True, amps=(6, 32)):  return P("Gen2TWC", 0, True, {C.SET_AMPS: C.Declaration(C.LOCAL)}, ready, amps)
def ble(ready=True):  return P("TeslaBLE", 2, True, {C.SET_AMPS: C.Declaration(C.LOCAL), C.WAKE: C.Declaration(C.LOCAL)}, ready, (1, 32), readTier=0)
def owner():          return P("OwnerAPI", 4, False, {}, readTier=1)
def fleet(ready=True): return P("FleetAPI", 5, False, {C.SET_AMPS: C.Declaration(C.FLEET_COMMAND), C.WAKE: C.Declaration(C.FLEET_WAKE)}, ready, (1, 32), readTier=2)
def ha(ready=True):   return P("HomeAssistant", 6, False, {C.SET_AMPS: C.Declaration(C.HA_BILLED)}, ready, (1, 32), readTier=2)

def master(settings=None, config=None):
    m = Mock(); m.settings = settings or {}; m.config = config or {}
    m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    m.vehicleRegistry = VehicleRegistry({}); return m

def order(m, *providers):
    o = ProviderOrder(m)
    for p in providers: o.register(p)
    return o

def test_fixed_order_is_tier_then_rank_regardless_of_registration():
    o = order(master(), ha(), fleet(), ble(), twc())
    assert [p.name for p in o.ordered(C.SET_AMPS)] == ["Gen2TWC", "TeslaBLE", "FleetAPI", "HomeAssistant"]
    assert [p.name for p in o.ordered(C.WAKE)] == ["TeslaBLE", "FleetAPI"]

def test_candidates_require_readiness_and_ordered_requires_availability():
    o = order(master(), twc(ready=False), ble(ready=False), fleet())
    assert [p.name for p in o.candidates(None, C.SET_AMPS)] == ["FleetAPI"]
    f = fleet(); f.available = lambda cap: cap != C.SET_AMPS
    assert order(master(), f).ordered(C.SET_AMPS) == [] and [p.name for p in order(master(), f).ordered(C.WAKE)] == ["FleetAPI"]

def test_dispatch_skips_providers_without_a_module():
    t = twc(); t.module = None; o = order(master(), t, fleet())
    assert o.dispatch(None, C.SET_AMPS, lambda p: p.setAmps(VIN, 10), amps=10) is False and t.calls == []   # TWC path exists, so Fleet is dropped; TWC is never written

def test_default_fleet_amps_rule_uses_target_and_range():      # Review Focus 3
    o = order(master(), twc(), fleet())
    assert [p.name for p in o.candidates(None, C.SET_AMPS)] == ["Gen2TWC"]           # unknown target: local path exists
    assert [p.name for p in o.candidates(None, C.SET_AMPS, amps=10)] == ["Gen2TWC"]  # covered: Fleet dropped
    assert [p.name for p in o.candidates(None, C.SET_AMPS, amps=4)] == ["FleetAPI"]  # below the TWC floor: Fleet allowed
    o = order(master(), fleet())
    assert [p.name for p in o.candidates(None, C.SET_AMPS, amps=10)] == ["FleetAPI"] # UMC car: Fleet is the only path

def test_ble_only_suppresses_remote_commands_not_reads():
    o = order(master({"commandPolicy": "ble_only"}), ble(), fleet(), ha())
    assert [p.name for p in o.ordered(C.SET_AMPS)] == ["TeslaBLE"]
    assert [s.name for s in o.orderReadSources([p.readSource for p in (ha(), fleet(), ble())])] == ["TeslaBLE", "FleetAPI", "HomeAssistant"]

def test_api_only_suppresses_ble_for_everything(caplog):        # Review Focus 1
    m = master({"commandPolicy": "api_only"}); o = order(m, ble(), fleet())
    assert [p.name for p in o.ordered(C.SET_AMPS)] == ["FleetAPI"]
    assert [s.name for s in o.orderReadSources([ble().readSource, fleet().readSource])] == ["FleetAPI"]
    with caplog.at_level(logging.INFO):
        o.suppressions.noticeOnce(); o.suppressions.noticeOnce()
    assert sum("api_only" in r.message for r in caplog.records) == 1

def test_config_policy_overrides_settings():
    s = Suppressions(master({"commandPolicy": "ble_only"}, {"vehicle": {"commandPolicy": "api_only"}}))
    assert s.commandPolicy == "api_only" and s.commandPolicyOverridden
    assert Suppressions(master({"commandPolicy": "banana"})).commandPolicy == "prefer_ble"

def test_explicit_suppressions_per_provider_and_capability():
    o = order(master({"providerSuppressions": {"FleetAPI": ["setAmps"], "HomeAssistant": ["*"]}}), fleet(), ha())
    assert o.ordered(C.SET_AMPS) == [] and [p.name for p in o.ordered(C.WAKE)] == ["FleetAPI"]

@pytest.mark.parametrize("bad", ["x", ["FleetAPI"], {"FleetAPI": "setAmps"}, {"Nope": ["setAmps"]}, {"FleetAPI": ["fly"]}, {"FleetAPI": [3]}])
def test_malformed_suppressions_are_ignored(bad):                 # Review Focus 4
    o = order(master({"providerSuppressions": bad}), fleet())
    assert [p.name for p in o.ordered(C.SET_AMPS)] == ["FleetAPI"]

def test_read_sources_ordered_by_tier_then_rank_and_unknown_last():
    o = order(master(), fleet(), owner(), ble())
    other = ReadSource(); other.name = "X"; other.order = 0
    got = o.orderReadSources([other, fleet().readSource, owner().readSource, ble().readSource])
    assert [s.name for s in got] == ["TeslaBLE", "OwnerAPI", "FleetAPI", "X"]

def test_registry_uses_installed_read_order():
    r = VehicleRegistry({}); a = ReadSource(); a.name = "a"; a.order = 1; b = ReadSource(); b.name = "b"; b.order = 0
    r.registerReadSource(a); r.registerReadSource(b)
    assert [s.name for s in r.readSources()] == ["b", "a"]
    r.useReadOrder(lambda sources: list(sources))                 # registration order, no sort
    assert [s.name for s in r.readSources()] == ["a", "b"] and r.useReadOrder(None) is None
    assert [s.name for s in r.readSources()] == ["b", "a"]

def test_dispatch_walks_candidates_with_attempts_and_stats():
    m = master(); b = ble(); b._result = False; f = fleet()
    o = order(m, b, f)
    assert o.dispatch(None, C.WAKE, lambda p: p.wake(VIN)) is True
    assert b.calls == [("wake", VIN)] * 3 and f.calls == [("wake", VIN)]
    assert m.stats["moduleFailures"] == {"TeslaBLE": 1} and m.stats["moduleSuccess"] == {"FleetAPI": 1}

def test_dispatch_treats_error_and_exceptions_as_failures():
    b = ble(); b._result = "error"; f = fleet(); f.wake = Mock(side_effect=RuntimeError("secret-token"))
    o = order(master(), b, f)
    assert o.dispatch(None, C.WAKE, lambda p: p.wake(VIN)) is False and f.wake.call_count == 2

def test_debug_command_goes_through_the_order():
    m = master(); m.vehicleRegistry.getOrCreate(VIN, "t"); f = fleet(); o = order(m, f)
    assert o.debugCommand("setChargeRate", VIN, '{"charge_rate": "12"}') is True and f.calls == [("setAmps", VIN, 12)]
    assert o.debugCommand("setChargeRate", VIN, '{"charge_rate": 0}') is True and f.calls[-1] == ("setAmps", VIN, 1)
    assert o.debugCommand("wakeVehicle", VIN, "not json") is True and f.calls[-1] == ("wake", VIN)
    assert o.debugCommand("wakeVehicle", "5YJ3E1EA1KF000009", "{}") is False and o.debugCommand("honk", VIN, "{}") is False
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Order`).

- [ ] **Step 3: Implement `Suppressions.py`, `Order.py` (incl. `registerProviders`), the `ReadSource.provider` attribute and `VehicleRegistry.useReadOrder`** per Interfaces; export `ProviderOrder`, `Suppressions` and `registerProviders` from `__init__.py`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_order.py tests/unit/test_registry_read_cascade.py tests/unit/test_registry_membership.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Providers/ lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle tests/unit/test_provider_order.py
git commit -m "Add the fixed provider order by cost tier with per-provider, per-capability suppressions"
```

