### Task 1: Capability vocabulary and the `Provider` base

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/__init__.py`, `lib/TWCManager/Vehicle/Providers/Capability.py`, `lib/TWCManager/Vehicle/Providers/Provider.py`.
- Test: `tests/unit/test_provider_capabilities.py`.

**Interfaces:**
- Produces (`Capability.py`; nothing here imports the Registry package, so `ReadSource` can stay import-free of providers):
  - Capability names (str constants): `READ_LIST = "readList"`, `READ_ONLINE = "readOnline"`, `READ_CHARGE = "readCharge"`, `READ_LOCATION = "readLocation"`, `READ_PLUG = "readPlug"`, `READ_VIN = "readVin"`, `READ_AMPS = "readAmps"`, `READ_WALL_CONNECTOR_VINS = "wallConnectorVins"` (an energy-site read: which VIN each Wall Connector on the account reports; Task 7), `SET_CHARGE_LIMIT = "setChargeLimit"`, `START_CHARGING = "startCharging"`, `STOP_CHARGING = "stopCharging"`, `SET_AMPS = "setAmps"`, `WAKE = "wake"`; `READS`, `COMMANDS`, `ALL` (frozensets).
  - Tiers: `TIER_LOCAL = 0`, `TIER_CLOUD_FREE = 1`, `TIER_BILLED = 2`, `TIER_DISRUPTIVE = 3`.
  - `class Cost(NamedTuple): tier: int; price: Optional[float] = None` (USD per operation; `None` = unknown). Constants: `LOCAL = Cost(0, 0.0)`, `CLOUD_FREE = Cost(1, 0.0)`, `FLEET_COMMAND = Cost(2, 0.001)`, `FLEET_DATA = Cost(2, 0.002)`, `FLEET_WAKE = Cost(2, 0.02)`, `HA_BILLED = Cost(2, None)`, `DISRUPTIVE = Cost(3, 0.0)`.
  - `class RateLimit(NamedTuple): calls: int; perSeconds: float`.
  - Limitation names a provider may declare per vehicle: `NO_INDIVIDUAL_STOP = "noIndividualStop"` (a stop through this provider also affects other endpoints; Gen3 units on one bus).
  - `class Declaration(NamedTuple): cost: Cost; rateLimit: Optional[RateLimit] = None; passive: bool = False` (`passive`: the provider reports this on its own and cannot be asked — telemetry).
- Produces (`Provider.py`):
  - `class Provider:` class attributes `name: str = ""`, `rank: int = 100` (fixed tie-break inside a tier; Gen2TWC 0, Gen3TWC 1, TeslaBLE 2, telemetry 3, OwnerAPI 4, FleetAPI 5, HomeAssistant 6, anything else 100), `local: bool = False`, `sharedControl: bool = False` (`True` when the provider's endpoints share one actuator, as Gen3 units on one Neurio bus do), `module = None` (the legacy Vehicle module the façade calls; `None` for providers with no module), `readSource = None` (a `ReadSource` or `None`). The `vin` argument of the command methods is the vehicle's registry key: a VIN, or an `anon:…` key that only local providers can serve. Methods: `declarations(self) -> Dict[str, Declaration]` (default `{}`), `declares(self, capability) -> bool`, `cost(self, capability) -> Optional[Cost]`, `ready(self, vehicle, capability) -> bool` (default `False`; per-vehicle; never does I/O), `ampsRange(self, vehicle) -> Optional[Tuple[float, float]]` (default `None`), `covers(self, vehicle, amps) -> bool` (`ampsRange` is not None and `lo <= amps <= hi`), `setAmps(self, vin: str, amps: int) -> bool` and `wake(self, vin: str) -> bool` (default raise `NotImplementedError`), `attempts(self) -> int` (`3` when `local` else `2`: today's BLE 3 / API 2), `limitations(self, vehicle) -> FrozenSet[str]` (default `frozenset()`), `available(self, capability) -> bool` (default `True`; a vehicle-less gate the order applies to every walk, so a broadcast never reaches a provider that cannot command at all — today's read-only skip), `summary(self, vehicle) -> dict` = `{"name", "local", "capabilities": {cap: {"tier", "price", "ready"}}}` (for Phase 6's provider panels).
  - `vehicleMaxAmps(vehicle, configConfig: dict) -> float`: `vehicle.value("availableCurrent")` when truthy, else `configConfig.get("wiringMaxAmpsPerTWC", 32)` (today's `TeslaAPIEVSE.maxPower` rule).
  - `__init__.py` re-exports `Provider`, `ProviderOrder` (Task 2) and the `Capability` names.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_capabilities.py
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Provider import Provider, vehicleMaxAmps
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

class Stub(Provider):
    name = "Stub"; local = True
    def declarations(self):
        return {C.SET_AMPS: C.Declaration(C.LOCAL), C.WAKE: C.Declaration(C.FLEET_WAKE, C.RateLimit(50, 60))}
    def ampsRange(self, vehicle): return (6, 32)

def test_vocabulary_and_prices():
    assert C.READS | C.COMMANDS == C.ALL and C.SET_AMPS in C.COMMANDS and C.READ_ONLINE in C.READS
    assert (C.FLEET_COMMAND.price, C.FLEET_DATA.price, C.FLEET_WAKE.price) == (0.001, 0.002, 0.02)
    assert C.LOCAL.tier < C.CLOUD_FREE.tier < C.FLEET_COMMAND.tier < C.DISRUPTIVE.tier
    assert C.HA_BILLED.price is None and C.HA_BILLED.tier == C.TIER_BILLED

def test_provider_defaults_and_declarations():
    p = Stub()
    assert p.declares(C.SET_AMPS) and not p.declares(C.READ_CHARGE)
    assert p.cost(C.WAKE) == C.FLEET_WAKE and p.cost(C.READ_CHARGE) is None
    assert p.declarations()[C.WAKE].rateLimit == C.RateLimit(50, 60)
    assert p.ready(None, C.SET_AMPS) is False and p.attempts() == 3 and Provider().attempts() == 2 and p.limitations(None) == frozenset() and Provider().available(C.WAKE) is True
    assert p.covers(None, 6) and p.covers(None, 32) and not p.covers(None, 4) and not Provider().covers(None, 10)

def test_summary_lists_each_capability():
    s = Stub().summary(None)
    assert s["name"] == "Stub" and s["capabilities"][C.WAKE] == {"tier": 2, "price": 0.02, "ready": False}

def test_vehicle_max_amps_falls_back_to_wiring():
    v = VehicleRegistry({}).getOrCreate(VIN, "t")
    assert vehicleMaxAmps(v, {"wiringMaxAmpsPerTWC": 40}) == 40
    v.observe("availableCurrent", 16, "TeslaAPI")
    assert vehicleMaxAmps(v, {}) == 16
```

- [ ] **Step 2: Run to verify failure** — `$PYTEST tests/unit/test_provider_capabilities.py -q --timeout=60 -p no:cacheprovider` → FAIL with `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers'`.

- [ ] **Step 3: Implement `Capability.py`, `Provider.py` and `__init__.py`** per Interfaces (the `ProviderOrder` re-export is added in Task 2).

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Providers/
git add lib/TWCManager/Vehicle/Providers tests/unit/test_provider_capabilities.py
git commit -m "Add the provider capability vocabulary with per-operation cost and the Provider base"
```

