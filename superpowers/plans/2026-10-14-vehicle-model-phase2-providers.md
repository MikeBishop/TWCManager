# Vehicle Model Phase 2: Providers and Charging Points — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every channel TWCManager talks through (Gen2 TWC, Gen3 TWC, TeslaBLE, Owner API, Fleet API, TeslaMate/Fleet telemetry, HomeAssistant) becomes a `Provider` that declares capabilities with per-operation cost, locality, per-vehicle readiness, per-device amps ranges and rate limits; a fixed `ProviderOrder` (cost tier, then a fixed rank) with per-provider/per-capability suppressions (`commandPolicy` mapped onto them) replaces the static priority table behind a `VehiclePriority` façade; and charging endpoints are grouped generically into charging points, replacing `MergedEVSE`, `getDedupedEVSEs` and the type knowledge in `TeslaAPIController`.

**Architecture:** A new package `lib/TWCManager/Vehicle/Providers/` holds the capability vocabulary, the `Provider` base, `Suppressions`, `ProviderOrder` and one provider class per channel; each Vehicle module exposes `providers()` and `TWCMaster` owns `master.providerOrder`. The existing `EVSEInstance` base stays as the charging-endpoint class and gains `vehicleKey`/`occupied`; `ChargingPoint` (one per correlated set of endpoints, merge count may be one) plus `groupEndpoints()` replace `MergedEVSE`; `VehicleEndpoint` (order-driven, queued amps) replaces `TeslaAPIEVSE`; `VehicleEndpoints` replaces `TeslaAPIController`. No desired state, reconcilers, lanes, control tick or presence: Phases 3–5. The distributor still runs on the serial loop but no longer does vehicle I/O there.

**Tech Stack:** Python 3.8+ (CI matrix 3.8–3.11), `threading`, `jinja2`, `pytest` (`tests/unit`).

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (sections "Charging points", "Providers and capabilities", "Order, policy and suppressions", "Layered actuators" for the transitional rule, "Threading"). Roadmap: `.superpowers/plans/2026-10-13-vehicle-model-roadmap.md` (Phase 2 row). Inventory: `.superpowers/gut-inventory.md` (A1, A2, A8, A9, A10, A17, A18, A24, A26). Settings meaning: `.superpowers/settings-history.md`. Phase 1 ledger carry-forwards: `.superpowers/sdd/2026-10-13-vehicle-model-phase1-registry/progress.md` (I5, M8, cost rules, lock order).

**Branch:** `git switch -c vehicle-model/phase2 8e07669` (the Phase 1 head, branch `vehicle-model/phase1`). Baseline at 8e07669: 1153 passed.

## Global Constraints

- Nothing blocks or delays the RS-485 heartbeat loop; **the serial thread does no vehicle I/O**: `distributeEVSEPower`, `chargingPoints()`, every endpoint/point property and `ProviderOrder.candidates()` read registry values (`vehicle.value()`, claims, settings keys) and never call `Vehicle.read()`, a module command or HTTP. A vehicle endpoint's `setTargetPower` queues to the vehicle worker (today's `TeslaAPIEVSE.setTargetPower` calls Fleet synchronously on the serial loop; this phase removes that).
- Lock order: `TeslaBLE._bleLock` → `master.settingsLock` → `VehicleRegistry._lock` → `Vehicle._lock`. No lock is held across I/O. `ProviderOrder` and providers take no lock of their own; readiness checks are single-key settings reads and claim lookups.
- **No new Fleet paid path.** Fleet prices (spec): `GET vehicles/{vin}` and `live_status` free; commands $0.001; `vehicle_data` $0.002; wake $0.02. Paid providers order after free ones; "Fleet never sets amps" is the default whenever a local amps path covers the target; the Fleet read source is used only when the Owner slot cannot read (today's `slotFor("read")` rule); nothing wakes a car to read. HomeAssistant, a user-loaded billed-tier provider, joins the order last: it is reached only after the free providers and Fleet have failed, and `ble_only` suppresses it.
- `config.json` and `settings.json` stay backward compatible: `commandPolicy` (`prefer_ble`/`ble_only`/`api_only`), `chargeRateControl` (1/2/3) and `chargeStopMode` (1/2/3) keep their values and keep working; new keys are optional (`settings["providerSuppressions"]`, config `vehicle.providerSuppressions`, config `controller.Gen2TWCs.ranges`).
- No regression for a pure-Gen2 install (no Vehicle modules loaded: `providerOrder` holds only the Gen2 provider, the distributor stays off), BLE-only installs, Owner/Fleet token users and TeslaMate users. Docker `:latest` tracks main.
- Python 3.8 syntax floor: no `X | Y` unions, no `dataclass(slots=True)`, no `match`.
- `black` only on files you touched; never `black .`.
- Every pytest run uses the capped form (an uncapped run once crashed the host):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `PYTEST="timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest"`
  then `$PYTEST <paths> -q --timeout=60 -p no:cacheprovider`. The full suite is `$PYTEST tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider` and must pass after every task.
- No log line may contain a token (access, refresh, HA long-lived, BLE private key); exceptions from providers are logged by type name only.
- Commit trailer on every commit per the session's attribution reminder (`Co-Authored-By: <the model that wrote the commit> <noreply@anthropic.com>`).

## Review Focus

1. A `settings.json` with `commandPolicy: "api_only"` (a user without working Bluetooth): TeslaBLE is suppressed for every operation, commands still reach Fleet, one INFO notice at startup explains the mapping; no BLE timeout is paid before each command. Tests in Task 2 (`test_api_only_suppresses_ble_for_everything`) and Task 9 (`test_api_only_walks_fleet_without_ble`).
2. A pure-Gen2 install (no Vehicle module loaded): `VehiclePriority` with no modules returns `False` for any method without raising; `providerOrder.providers()` is `[Gen2TWC]`; the distributor is still skipped because only `Gen2TWCs` is registered. Tests in Task 9 (`test_no_modules_returns_false`) and Task 11 (`test_pure_gen2_leaves_distributor_off`).
3. A Fleet-only car (no BLE) on a Gen2 TWC with `chargeRateControl` 3 and a 4 A target: the TWC's range (6 A floor) does not cover 4 A, so the default rule does not drop Fleet and mode 3 keeps working; at 10 A the TWC covers it and Fleet is dropped. Test in Task 2 (`test_default_fleet_amps_rule_uses_target_and_range`).
4. A malformed `providerSuppressions` (a string, a list, unknown provider or capability names): ignored without raising, every provider stays available. Test in Task 2 (`test_malformed_suppressions_are_ignored`).
5. A car that stops charging on its TWC (TWCSlave clears `currentVIN` five seconds after amps drop; the TWC reports state 03/04): the TWC endpoint and the car's vehicle endpoint stay one charging point, so the car gets no separate power share or Fleet amps command (ledger I5, inventory A18). Tests in Task 3 (`test_vehicle_key_keeps_last_vin_while_plugged_state`), Task 10 (`test_last_vin_plugged_twc_keeps_other_cars_listed`: the blind rule keys on `vehicleKey`, so a stopped car neither blinds the install nor gets its own endpoint) and Task 11 (`test_stopped_car_stays_one_point`).

---

## File structure

Created:
- `lib/TWCManager/Vehicle/Providers/__init__.py` — re-exports.
- `lib/TWCManager/Vehicle/Providers/Capability.py` — capability names, cost tiers and prices, `Cost`, `RateLimit`, `Declaration`.
- `lib/TWCManager/Vehicle/Providers/Provider.py` — `Provider` base, `vehicleMaxAmps()`.
- `lib/TWCManager/Vehicle/Providers/Suppressions.py` — `Suppressions` (`commandPolicy` mapping, explicit per-provider/per-capability suppressions).
- `lib/TWCManager/Vehicle/Providers/Order.py` — `ProviderOrder` (registration, fixed order, candidates, read-source ordering, dispatch walk, debug command).
- `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `WallConnectorVins.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py` (`OwnerAPIProvider`, `FleetAPIProvider`), `TelemetryProvider.py`, `HomeAssistantProvider.py`.
- `lib/TWCManager/EVSEInstance/ChargingPoint.py` — `ChargingPoint`, `groupEndpoints()`.
- `lib/TWCManager/EVSEInstance/VehicleEndpoint.py` — `VehicleEndpoint`.
- `lib/TWCManager/EVSEController/VehicleEndpoints.py` — `VehicleEndpoints` controller.
- Tests: `tests/unit/test_provider_capabilities.py`, `test_provider_order.py`, `test_gen2twc_provider.py`, `test_gen3twc_provider.py`, `test_wall_connector_vins.py`, `test_teslable_provider.py`, `test_teslaapi_providers.py`, `test_provider_registration.py`, `test_vehicle_priority.py` (rewritten), `test_vehicle_endpoint.py`, `test_charging_points.py`.

Modified:
- `lib/TWCManager/TWCMaster.py` (`providerOrder`, Gen2 provider registration, `chargingPoints()`, `distributeEVSEPower`), `lib/TWCManager/TWCManager.py` (provider registration after module load, `VehicleEndpoints` registration), `lib/TWCManager/VehicleCommandQueue.py` (`setAmps` command).
- `lib/TWCManager/EVSEInstance/EVSEInstance.py` (`vehicleKey`, `occupied`, `provider`, `idleMinimum`), `Gen2TWC.py` (ranges, `vehicleKey`, `occupied`), `Gen3TWC.py` (vitals fetch off the serial loop, plug sessions, correlation), `lib/TWCManager/EVSEController/Gen3TWCs.py` (`setUnitTarget`, `devices`, `refreshVitals`).
- `lib/TWCManager/Vehicle/Registry/ReadSource.py` (`provider` attribute), `VehicleRegistry.py` (`useReadOrder`), `Sources.py` (BLE source drops the `api_only` lookup; `TeslaAPIReadSource` per slot).
- `lib/TWCManager/Vehicle/TeslaAPI.py` (`providers()`, per-slot read sources, `get_car_api(slot=)`, split claims, `apiDebugInterface` removed), `TeslaBLE.py` (`providers()`, `readSource`), `HomeAssistant.py` (`providers()`, `readSource`), `Telemetry.py` (`providers()`).
- `lib/TWCManager/Vehicle/VehiclePriority.py` (façade over the order).
- `lib/TWCManager/Control/HTTPControl.py` (`/api/sendTeslaAPICommand` via the order), `lib/TWCManager/Control/themes/Default/settings.html.j2` (relabels).
- `docs/Settings.md`, `CHANGELOG.md`.
- Tests touched: `tests/unit/test_teslaapi_readonly_gate.py`, `test_carapivehicle_registry.py`, `test_registry_callers.py`, `test_telemetry_registry.py`, `test_distributor_loop.py`, `test_reads_no_wake.py` (if it asserts the BLE `api_only` skip).

Deleted: `lib/TWCManager/EVSEInstance/MergedEVSE.py`, `lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py`, `lib/TWCManager/EVSEController/TeslaAPIController.py`, `tests/unit/test_teslaapi_controller.py` (its cases move to `test_vehicle_endpoint.py`).

---

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

### Task 3: Gen2 TWC provider with per-device ranges and the disruptive stop

`minAmpsTWCSupports` lives on `TWCSlave` (class default 6, `lib/TWCManager/TWCSlave.py:25`); `TWCManager.py:1270-1278` sets it to 5 for a protocol-1 TWC (14-byte linkready) and 6 for protocol 2, and `:1424-1426` sets it to 1 A when all three phases report ≥ 200 V. The reported maximum is `TWCSlave.maxAmps` (80 US / 32 EU from linkready) and the wiring limit is `wiringMaxAmps` (config `wiringMaxAmpsPerTWC`).

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py`.
- Modify: `lib/TWCManager/EVSEInstance/EVSEInstance.py:92-100` (defaults), `lib/TWCManager/EVSEInstance/Gen2TWC.py:108-114` (ranges), new properties; `lib/TWCManager/TWCMaster.py` `__init__` (`providerOrder`, registration, after `self.vehicleRegistry = VehicleRegistry(config)`) and `stopCarsCharging` (`stopRespondingToSlaves`).
- Test: `tests/unit/test_gen2twc_provider.py`.

**Interfaces:**
- Consumes: `Provider`, `ProviderOrder`, capability names; `TWCSlave.minAmpsTWCSupports`, `.maxAmps`, `.wiringMaxAmps`, `.currentVIN`, `.lastVIN`, `.reportedState`, `.reportedAmpsActual`; `VehicleRegistry.get("anon:<id>")`.
- Produces (`EVSEInstance`): `vehicleKey -> Optional[str]` (default `None`: the registry key of the vehicle this endpoint serves), `occupied -> Optional[bool]` (default `None`: `True` a car is connected, `False` none, `None` unknown), `provider: str = ""`, `idleMinimum: bool = False` (`True` when an idle endpoint must be offered its minimum to detect a plug-in; `Gen2TWC` sets it `True`, Gen3 leaves it `False`).
- Produces (`Gen2TWC`):
  - `twcid -> str` (`"%02X%02X"`), `PLUGGED_STATES = (0x01, 0x03, 0x04, 0x05, 0x08, 0x09)`.
  - `minAmps -> float`: config override `master.config.get("controller.Gen2TWCs", {}).get("ranges", {}).get(twcid, {}).get("minAmps")` when a positive number, else `minAmpsTWCSupports`. `maxOfferAmps -> float` (named so because `TWCSlave.maxAmps` is already the linkready value): the override's `maxAmps` key when a positive number, else `min(wiringMaxAmps, self.maxAmps or wiringMaxAmps)`. `minPower`/`maxPower` use these (today `minAmpsTWCSupports` / `wiringMaxAmps`).
  - `vehicleKey`: `currentVIN.upper()` when set; else the anonymous plug-session key `"anon:" + twcid` when `master.vehicleRegistry.get(...)` holds it; else `lastVIN.upper()` while `reportedState in PLUGGED_STATES` (the car that was last confirmed here has shown no unplug evidence; ledger I5: not the charging session); else `None`.
  - `occupied`: `True` when `currentVIN` or `reportedAmpsActual >= 1.0` or `reportedState in PLUGGED_STATES`; otherwise `None` (a Gen2 reports 00 for a sleeping plugged car, so 00 is not "empty").
  - `provider = "Gen2TWC"`, `idleMinimum = True`.
- Produces (`Gen2TWCProvider.py`) `class Gen2TWCProvider(Provider):` `name = "Gen2TWC"`, `rank = 0`, `local = True`, `module = None`; `__init__(self, master)`; `declarations()`: `READ_PLUG`, `READ_VIN`, `READ_AMPS` → `Declaration(LOCAL, passive=True)`; `SET_AMPS` → `Declaration(LOCAL)`; `STOP_CHARGING` → `Declaration(DISRUPTIVE)`. `slaveFor(self, vehicle) -> Optional[TWCSlave]` (the slave in `master.getSlaveTWCs()` whose `vehicleKey == vehicle.key`); `stopMode(self) -> int` (`int(settings.get("chargeStopMode", 1))`); `ready(vehicle, cap)`: reads and `SET_AMPS` → `slaveFor` is not None, and for `SET_AMPS` additionally `int(settings.get("chargeRateControl", 1)) != 2` (mode 2 hands the rate to the vehicle); `STOP_CHARGING` → `slaveFor` is not None and `stopMode() in (2, 3)` (off by default; a disruptive stop is only ever selected by `chargeStopMode`). `ampsRange(vehicle)` → `(slave.minAmps, slave.maxOfferAmps)`, except under `chargeRateControl == 3` where the floor is the hard-coded 6 A at which `TWCSlave.send_master_heartbeat` hands the rate to the vehicle (`(6, slave.maxOfferAmps)`): a protocol-1 TWC (`minAmps` 5) or a 3-phase one (`minAmps` 1) would otherwise 'cover' a target the TWC never carries, Fleet would be dropped, and a Fleet-only car would run at the wiring maximum; `setAmps(vin, amps)` → `slave.setTargetPower(slave.convertAmpsToWatts(amps))`, `True` (publishing a target the serial loop sends on the next heartbeat; never reached by `dispatch`, Task 2); `stopCharging(self, vin) -> bool`: mode 2 → `master.stopRespondingToSlaves()`; mode 3 → `master.sendStopCommand(slave.TWCID)`; else `False`. **No Phase 2 caller uses `stopCharging`**: `TWCMaster.stopCarsCharging` is unchanged; the Phase 3 reconciler is the caller.
- Produces (`TWCMaster`): `stopRespondingToSlaves(self) -> None` (under `settingsLock`: `respondToSlaves = 0`, `respondToSlavesExpiry = time.time() + 60`), factored out of `stopCarsCharging`'s mode-2 branch, which now calls it. `__init__`: `self.providerOrder = ProviderOrder(self)` after `self.vehicleRegistry`, then `self.providerOrder.register(Gen2TWCProvider(self))` and `self.vehicleRegistry.useReadOrder(self.providerOrder.orderReadSources)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_gen2twc_provider.py
from unittest.mock import Mock
from TWCManager.TWCMaster import TWCMaster
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Gen2TWCProvider import Gen2TWCProvider
VIN = "5YJ3E1EA1KF000001"
CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False, "treatGenerationAsGridDelivery": False,
          "wiringMaxAmpsAllTWCs": 80, "wiringMaxAmpsPerTWC": 32, "maxAmpsAllowedFromGrid": None}}

def make(config=CONFIG):
    m = TWCMaster("AB", config); m.getModuleByName = Mock(return_value=None)
    s = m.newSlave(b"\x82\x44", 80); return m, s          # slaveTWCs is keyed by bytes

def test_master_registers_gen2_provider_and_read_order():
    m, s = make()
    assert [p.name for p in m.providerOrder.providers()] == ["Gen2TWC"]
    assert m.vehicleRegistry._readOrder is not None

def test_ranges_follow_the_device_and_wiring():
    m, s = make(); s.minAmpsTWCSupports = 5
    assert (s.minAmps, s.maxOfferAmps) == (5, 32)
    s.maxAmps = 24; assert s.maxOfferAmps == 24
    m2, s2 = make(dict(CONFIG, **{"controller.Gen2TWCs": {"ranges": {"8244": {"minAmps": 6, "maxAmps": 16}}}}))
    assert (s2.minAmps, s2.maxOfferAmps) == (6, 16) and s2.minPower == 6 * 240

def test_vehicle_key_keeps_last_vin_while_plugged_state():       # Review Focus 5 / ledger I5
    m, s = make(); reg = m.vehicleRegistry
    assert s.vehicleKey is None and s.occupied is None
    s.currentVIN = VIN.lower(); assert s.vehicleKey == VIN and s.occupied is True
    s.currentVIN = ""; s.lastVIN = VIN; s.reportedState = 0x03
    assert s.vehicleKey == VIN and s.occupied is True
    s.reportedState = 0x00; assert s.vehicleKey is None and s.occupied is None
    reg.beginPlugSession("8244"); assert s.vehicleKey == "anon:8244" and s.idleMinimum is True

def test_provider_readiness_and_range_per_vehicle():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t")
    assert p.ready(v, C.SET_AMPS) is False and p.ampsRange(v) is None
    s.currentVIN = VIN
    assert p.ready(v, C.SET_AMPS) and p.ampsRange(v) == (6, 32) and p.covers(v, 6) and not p.covers(v, 4)
    s.minAmpsTWCSupports = 5; assert p.ampsRange(v) == (5, 32) and p.covers(v, 5)
    m.settings["chargeRateControl"] = "3"; assert p.ampsRange(v) == (6, 32) and not p.covers(v, 5)   # mode 3 hands off below 6 A: Fleet stays a candidate
    m.settings["chargeRateControl"] = "2"; assert p.ready(v, C.SET_AMPS) is False
    assert p.ready(v, C.READ_VIN) and p.declarations()[C.READ_VIN].passive

def test_disruptive_stop_declared_very_high_cost_and_off_by_default():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t"); s.currentVIN = VIN
    assert p.cost(C.STOP_CHARGING) == C.DISRUPTIVE and p.ready(v, C.STOP_CHARGING) is False
    assert p.stopCharging(VIN) is False
    m.settings["chargeStopMode"] = "2"
    assert p.ready(v, C.STOP_CHARGING) and p.stopCharging(VIN) is True and m.settings["respondToSlaves"] == 0
    m.settings["respondToSlaves"] = 1; m.stopCarsCharging(VIN); assert m.settings["respondToSlaves"] == 0         # same helper
    m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    assert p.stopCharging(VIN) is True; m.sendStopCommand.assert_called_once_with(s.TWCID)

def test_set_amps_publishes_a_target_for_the_heartbeat():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); s.currentVIN = VIN
    assert p.setAmps(VIN, 16) is True and s._evseTargetAmps == 16
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Gen2TWCProvider`).

- [ ] **Step 3: Implement** per Interfaces. `TWCMaster` imports `ProviderOrder` and `Gen2TWCProvider` at module top (the Providers package imports nothing from `TWCMaster`).

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_gen2twc_provider.py tests/unit/test_twcmaster.py tests/unit/test_twcslave.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Providers/ lib/TWCManager/EVSEInstance/ lib/TWCManager/TWCMaster.py
git add lib/TWCManager tests/unit/test_gen2twc_provider.py
git commit -m "Add the Gen2 TWC provider with per-device amps ranges and a very-high-cost disruptive stop"
```

### Task 4: Gen3 TWC provider: plug sessions without a VIN, shared headroom

A Gen3 (`EVSEController/Gen3TWCs.py`, `EVSEInstance/Gen3TWC.py`; `docs/modules/Controller_Gen3TWCs.md`) is controlled through a fake Neurio Modbus server: every Gen3 on the bus reads **one** shared house load and charges at `fuse − house`. Reads come from the unit's local HTTP `/api/1/vitals` (`vehicle_connected`, `vehicle_current_a`, `grid_v`, `evse_state`); there is no VIN. Today `Gen3TWC._fetch_vitals` does that HTTP inside every property, i.e. on the serial loop; this task keeps its cadence and caching (`_VITALS_SUCCESS_TTL` 5 s / `_VITALS_CACHE_TTL` 10 s) but moves the fetch to the background thread. No Gen3 hardware exists on the user's box: this task is verified by unit tests only (G6).

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/Gen3TWCProvider.py`.
- Modify: `lib/TWCManager/EVSEInstance/Gen3TWC.py:80-108` (fetch split), `:122-130` (`isLocal`), `:136-199` (cache-only properties, `vehicleKey`, `occupied`), `:205-254` (targets via the controller); `lib/TWCManager/EVSEController/Gen3TWCs.py:186-227` (`setUnitTarget`, `solve`, `republish`), `:320-337` (`allEVSEs`, `devices`, `refreshVitals`); `lib/TWCManager/TWCManager.py` (`gen3Vitals` branch in `background_tasks_thread`'s `elif task["cmd"] == ...` chain; provider registration inside the existing `_gen3_cfg` / `if _gen3_cfg.get("enabled", False):` block, after its `registerModule`).
- Test: `tests/unit/test_gen3twc_provider.py`.

**Interfaces:**
- Consumes: `Provider`, `ProviderOrder`, capability names; `VehicleRegistry.beginPlugSession/endPlugSession/vehicleAt/observeTwcVin/now`; `master.queue_background_task` (coalesces by `cmd`).
- Produces (`Gen3TWC`):
  - `vitals -> dict` (the cache; never fetches), `vitalsStale() -> bool` (today's TTL rule), `refreshVitals() -> bool` (today's HTTP body; **background thread only**; after a successful fetch runs the plug-session edges and observations below, outside any lock, and ends with `controller.noteVitals(self, rising)`), `isReachable` → cached `_vitals_ok`. `isCharging`, `wantsToCharge`, `currentAmps`, `currentVoltage` read `vitals` only.
  - `pointId -> str` = `ID` (`"Gen3TWC-<ip>"`); `fuseAmps`, `phases`; `isLocal` → `True` (the old `False` only made `MergedEVSE` prefer Gen2; grouping by key makes that moot); `idleMinimum = False` (vitals report `vehicle_connected` whatever the headroom, so an idle Gen3 needs no minimum to detect a car); `occupied` → `bool(vitals["vehicle_connected"])` when reachable, else `None`; `vehicleKey` → `registry.vehicleAt(pointId).key` when a vehicle is at the point (correlated car or anonymous session), else `None`; `lastTarget: float`.
  - Plug-session edges in `refreshVitals()`: `vehicle_connected` rising → `registry.beginPlugSession(pointId)` then `_correlate()`; falling → `registry.endPlugSession(pointId)`; while connected, observe on `registry.vehicleAt(pointId)`: `pluggedIn=True`, `actualCurrent`, `voltage` (source `"Gen3TWC"`).
  - `CORRELATE_WINDOW = 120.0`; `cloudVin: Optional[str] = None` (set by Task 7's energy-site reader; checked first, G7); `_correlate(self) -> Optional[str]` (G3): when `cloudVin` is set → `registry.observeTwcVin(pointId, cloudVin)` and return it; else `now = registry.now()`; candidates = non-anonymous registry vehicles whose `latest("pluggedIn")` is `True` with `now - obs.at <= CORRELATE_WINDOW` (the plug *change*, not feed liveness), `value("twcVin")` is `None` (not already on another point), and whose `attachment("TeslaAPI")`, when present, has `atHome` true; exactly one → `registry.observeTwcVin(pointId, vin)` (a known VIN confirms at once and merges the anonymous vehicle; Phase 1 Task 7) and return it; otherwise stay anonymous (INFO `Gen3TWC <ip>: car connected, <n> candidates; left anonymous`) and return `None`. Anything smarter is the separate VIN-less fingerprinting design (inventory A27).
  - `setTargetPower(watts)` → `lastTarget = watts; controller.setUnitTarget(ID, watts)`; `stopCharging()` → `controller.setUnitTarget(ID, 0)`; `startCharging()` → `controller.setUnitTarget(ID, lastTarget or minPower)`.
- Produces (`Gen3TWCs`): `sharedControl = True`; `devices() -> List[Gen3TWC]` (every configured unit from the cache, reachable or not); `unitTargets -> Dict[str, float]` (watts per unit); `DAMP_AMPS = 1.0`; `MIN_AMPS = 6.0`; `setUnitTarget(self, unitId, watts) -> None` records the unit's own target (the distributor and charging points address Gen3 units **separately**, exactly as Gen2 slaves; only the controller, which owns the one fake-Neurio value, aggregates) and calls `republish()`; `headroom() -> float` (the first device's current headroom `F_1 - H` in amps, rounded to 0.01); `demandAmps(unit) -> float` from the unit's cached vitals: its measured `vehicle_current_a` when `1.0 <= measured < h_i - DAMP_AMPS` and `evse_state == "charging"` (car-limited: a full battery drawing 3 A); otherwise `inf` (unknown, unreachable, or drawing at the headroom — never 0, so a unit with a target is always served); `solve() -> float` (G2, water-filling): targets in amps `A_i = t_i / (V * phases_i)` over units with `t_i > 0`; the house load in amps `H` is chosen by bisection on `[0, max fuse]` (20 steps, then rounded to 0.01 A so the published watts are exact) as the largest `H` with `sum_i min(d_i, max(0, F_i - H)) >= sum_i A_i` — each unit in its own terms (`h_i = F_i - H`, per-device fuse; with equal fuses and unconstrained units this is `h = sum(A_i) / n`; with one unit it is `h = A_1`, today's behaviour) — then clamped so every targeted unit keeps `h_i >= MIN_AMPS`; when every target is 0, `H = max fuse` (the full fuse as load, a stop); zero-target units are **excluded** from the sum (they cannot be stopped individually through the shared value and may still draw up to `h`); `republish()`: recomputes and calls `setHouseWatts(watts=H * V * p, phases=p, voltage=V)` (setHouseWatts divides by phases; corrected in Task 4 fix round 1) (`p`/`V` from the first device as today) only when the new `h` differs from the published one by more than `DAMP_AMPS` or the target set changed (damping); `noteVitals(self, unit, rising: bool) -> None` (called by each unit at the end of its own `refreshVitals()`): the damped `republish()` (closed loop on the existing cadence, no new polling loop, G5; Task 7 adds the VIN reader here); `refreshVitals()` → `refreshVitals()` on every device and nothing else. `allEVSEs` → devices whose cached `isReachable` is `True`; when any device `vitalsStale()`, `master.queue_background_task({"cmd": "gen3Vitals"})`.
- Produces (`Gen3TWCProvider.py`) `class Gen3TWCProvider(Provider):` `name = "Gen3TWC"`, `rank = 1`, `local = True`, `module = None`, `sharedControl = True`; `__init__(self, controller, master)`; `declarations()`: `READ_PLUG`, `READ_AMPS` → `Declaration(LOCAL, passive=True)`; `SET_AMPS`, `START_CHARGING`, `STOP_CHARGING` → `Declaration(LOCAL)` (G4: a zero-headroom stop is a normal local stop, not a disruptive one; unverified on hardware); `unitFor(vehicle)` → the device in `controller.devices()` whose `vehicleKey == vehicle.key`; `ready(vehicle, cap)` → `unitFor` is not None; `ampsRange(vehicle)` → `(6, unit.fuseAmps)`; `limitations(vehicle)` → `frozenset({NO_INDIVIDUAL_STOP})` when more than one unit has `occupied is True` (declared so Phase 3 can pick another actuator, e.g. BLE or Fleet on that car), else empty; `setAmps(key, amps)` → `unit.setTargetPower(unit.convertAmpsToWatts(amps))`, `True`; `stopCharging(key)` → `unit.stopCharging()`, `True`; `startCharging(key)` likewise (no Phase 2 caller for either; Phase 3). The `key` is a registry key (a VIN or `anon:…`), per Task 1.
- Produces (`TWCManager.py`): `elif task["cmd"] == "gen3Vitals": g = master.getModuleByName("Gen3TWCs"); g and g.refreshVitals()` on the background thread; inside the existing `if _gen3_cfg.get("enabled", False):` block, after `registerModule`, `master.providerOrder.register(Gen3TWCProvider(gen3, master))` (G1: with Gen3 disabled nothing changes).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_gen3twc_provider.py
import json
from unittest.mock import MagicMock, Mock, patch
from TWCManager.EVSEController.Gen3TWCs import Gen3TWCs
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Gen3TWCProvider import Gen3TWCProvider
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN1 = "5YJ3E1EA1KF000001"; VIN2 = "5YJ3E1EA1KF000002"; IP1, IP2 = "10.0.0.1", "10.0.0.2"

class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def make(ips=(IP1,), clock=None):
    m = Mock(); m.vehicleRegistry = VehicleRegistry({}, clock=clock or Clock())
    m.config = {"config": {"defaultVoltage": 240}, "controller.Gen3TWCs": {"enabled": True, "devices": [{"ip": ip, "fuseAmps": 48, "phases": 1} for ip in ips]}}
    with patch.object(Gen3TWCs, "_start_server"):
        ctl = Gen3TWCs(m)
    ctl.setHouseWatts = Mock(); return m, ctl, Gen3TWCProvider(ctl, m)

def vitals(unit, connected, amps=0.0, state="charging"):
    resp = MagicMock(); resp.__enter__.return_value.read.return_value = json.dumps(
        {"vehicle_connected": connected, "vehicle_current_a": amps, "grid_v": 240.0, "evse_state": state}).encode()
    with patch("urllib.request.urlopen", return_value=resp):
        return unit.refreshVitals()

def test_properties_never_fetch_and_a_stale_cache_queues_one_background_task():   # G5
    m, ctl, p = make(); (u,) = ctl.devices()
    with patch("urllib.request.urlopen", side_effect=AssertionError("no HTTP on the caller's thread")):
        assert ctl.allEVSEs == [] and u.isReachable is False and u.occupied is None and u.wantsToCharge is False
    m.queue_background_task.assert_called_once_with({"cmd": "gen3Vitals"})
    assert vitals(u, True, 12.0) is True and ctl.allEVSEs == [u] and u.currentAmps == 12.0 and u.isLocal and u.idleMinimum is False

def test_connect_begins_an_anonymous_session_and_disconnect_ends_it():            # G3
    m, ctl, p = make(); (u,) = ctl.devices(); reg = m.vehicleRegistry
    vitals(u, True, 6.0); anon = reg.get("anon:" + u.ID)
    assert anon is not None and u.vehicleKey == anon.key and u.occupied is True
    assert anon.latest("pluggedIn").value is True and anon.latest("actualCurrent").value == 6.0 and anon.latest("voltage").source == "Gen3TWC"
    vitals(u, False)
    assert reg.get("anon:" + u.ID) is None and u.vehicleKey is None and u.occupied is False

def test_single_candidate_car_is_correlated():                                     # G3
    m, ctl, p = make(); (u,) = ctl.devices(); reg = m.vehicleRegistry
    car = reg.getOrCreate(VIN1, "TeslaMateVehicle"); car.observe("pluggedIn", True, "TeslaMateVehicle")
    other = reg.getOrCreate(VIN2, "TeslaMateVehicle"); other.observe("pluggedIn", False, "TeslaMateVehicle")
    vitals(u, True)
    assert u.vehicleKey == VIN1 and reg.get("anon:" + u.ID) is None and car.value("twcVin") == u.ID
    assert p.ready(car, C.SET_AMPS) and p.ampsRange(car) == (6, 48) and not p.ready(other, C.SET_AMPS)

def test_two_candidate_cars_stay_anonymous():                                      # G3
    m, ctl, p = make(); (u,) = ctl.devices(); reg = m.vehicleRegistry
    for vin in (VIN1, VIN2): reg.getOrCreate(vin, "t").observe("pluggedIn", True, "TeslaMateVehicle")
    vitals(u, True)
    assert u.vehicleKey == "anon:" + u.ID and reg.get(VIN1).value("twcVin") is None and reg.get(VIN2).value("twcVin") is None

def test_old_plug_evidence_or_a_car_already_on_a_twc_is_not_a_candidate():
    c = Clock(); m, ctl, p = make(clock=c); (u,) = ctl.devices(); reg = m.vehicleRegistry
    car = reg.getOrCreate(VIN1, "t"); car.observe("pluggedIn", True, "TeslaMateVehicle"); c.t += 121
    vitals(u, True); assert u.vehicleKey == "anon:" + u.ID
    vitals(u, False); car.observe("pluggedIn", True, "TeslaMateVehicle"); car.observe("twcVin", "8244", "TWC")
    vitals(u, True); assert u.vehicleKey == "anon:" + u.ID

def test_capabilities_normal_tier_stop_and_declared_shared_control():              # G2, G4
    m, ctl, p = make()
    assert (p.name, p.rank, p.local, p.sharedControl, ctl.sharedControl) == ("Gen3TWC", 1, True, True, True)
    assert p.cost(C.STOP_CHARGING) == C.LOCAL and p.cost(C.SET_AMPS) == C.LOCAL and p.declarations()[C.READ_PLUG].passive

def test_single_unit_headroom_equals_its_target_as_today():                        # G2
    m, ctl, p = make(); (u,) = ctl.devices()
    u.setTargetPower(4800); ctl.setHouseWatts.assert_called_with(watts=11520 - 4800, phases=1, voltage=240)
    u.setTargetPower(2400); ctl.setHouseWatts.assert_called_with(watts=11520 - 2400, phases=1, voltage=240)
    u.setTargetPower(0);    ctl.setHouseWatts.assert_called_with(watts=11520, phases=1, voltage=240)

def test_two_unconstrained_units_share_the_mean():                                  # G2
    m, ctl, p = make((IP1, IP2)); a, b = ctl.devices(); vitals(a, True); vitals(b, True)
    a.setTargetPower(4800); b.setTargetPower(2400)                             # 20 A + 10 A over two units: h = 15 A
    assert ctl.headroom() == 15 and ctl.setHouseWatts.call_args.kwargs == {"watts": (48 - 15) * 240, "phases": 1, "voltage": 240}

def test_car_limited_unit_raises_h_so_the_net_matches_and_small_changes_are_damped():   # G2
    m, ctl, p = make((IP1, IP2)); a, b = ctl.devices(); vitals(a, True); vitals(b, True)
    a.setTargetPower(4800); b.setTargetPower(2400); n = ctl.setHouseWatts.call_count
    vitals(b, True, amps=3.0)                                                  # b is full and draws 3 A: a may take 27 A
    assert ctl.headroom() == 27 and ctl.setHouseWatts.call_args.kwargs["watts"] == (48 - 27) * 240 and ctl.setHouseWatts.call_count == n + 1
    vitals(b, True, amps=3.4)                                                  # within DAMP_AMPS: no republish
    assert ctl.setHouseWatts.call_count == n + 1

def test_zero_target_beside_a_charging_sibling_declares_no_individual_stop():       # G2
    m, ctl, p = make((IP1, IP2)); a, b = ctl.devices(); vitals(a, True); vitals(b, True); reg = m.vehicleRegistry
    a.setTargetPower(4800); b.setTargetPower(0)                                # h covers a's 20 A only; b may still draw up to h
    assert ctl.headroom() == 20 and ctl.setHouseWatts.call_args.kwargs["watts"] == (48 - 20) * 240
    assert p.limitations(reg.get("anon:" + b.ID)) == frozenset({C.NO_INDIVIDUAL_STOP})
    a.setTargetPower(0); assert ctl.setHouseWatts.call_args.kwargs["watts"] == 11520    # everyone stopped: the full fuse as load
    vitals(b, False); assert p.limitations(reg.get("anon:" + a.ID)) == frozenset()

def test_provider_commands_go_to_the_unit():
    m, ctl, p = make(); (u,) = ctl.devices(); vitals(u, True); anon = m.vehicleRegistry.get("anon:" + u.ID)
    assert p.setAmps(anon.key, 16) is True; ctl.setHouseWatts.assert_called_with(watts=11520 - 3840, phases=1, voltage=240)
    assert p.stopCharging(anon.key) is True; ctl.setHouseWatts.assert_called_with(watts=11520, phases=1, voltage=240)
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Gen3TWCProvider`).

- [ ] **Step 3: Implement** per Interfaces (keep the Modbus server code untouched; `_fetch_vitals` becomes `refreshVitals`).

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_gen3twc_provider.py tests/unit/test_twcmanager.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Providers/ lib/TWCManager/EVSEInstance/Gen3TWC.py lib/TWCManager/EVSEController/Gen3TWCs.py lib/TWCManager/TWCManager.py
git add lib/TWCManager tests/unit/test_gen3twc_provider.py
git commit -m "Add the Gen3 TWC provider: anonymous plug sessions from vitals, one shared headroom, fetches off the serial loop"
```

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

### Task 6: Owner API and Fleet API as separate providers (closes A24)

The two token slots become two providers over the one `TeslaAPI` module. Reads split by slot so their cost is honest: the Owner slot reads for free; the Fleet slot's `vehicle_data` costs $0.002 and is used only when the Owner slot cannot read (today's `slotFor("read")` rule, so no new paid path). Commands and wake exist only on Fleet. The registry claim splits the same way; the attachment name stays `"TeslaAPI"`.

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Sources.py:72-99` (`TeslaAPIReadSource` per slot); `lib/TWCManager/Vehicle/TeslaAPI.py:144` (two read sources), `:2080-2091` (`_registryVehicle` claims), `:2165` (`is_awake(slot=None)`), `:2190` (`get_car_api(..., slot=None)`), `:2330` (`update_vehicle_data(slot=None)`), new `providers()`.
- Test: `tests/unit/test_teslaapi_providers.py`; update `tests/unit/test_carapivehicle_registry.py:161,172` (`"TeslaAPI" in v.claims` → `"FleetAPI" in v.claims`); its `test_vehicle_joins_registry_and_claims_teslaapi` (list first, then `setTokens(fleet_token())` → managed) keeps passing because the Fleet claim's callable is live. `api_with_registry()` starts with both slots empty.

**Interfaces:**
- Consumes: `TeslaTokenSlot.usable(purpose)`, `.empty()`; `TeslaAPI.ownerSlot`, `.fleetSlot`, `.setChargeRate(charge_rate, vehicle=)`, `.wakeVehicle(vehicle)`, `.getVehicleByVIN(vin)`.
- Produces (`Sources.py`): `TeslaAPIReadSource.__init__(self, carapi, kind: str = "owner")`; `name = "TeslaAPI"` (observation source unchanged), `provider = "OwnerAPI"` or `"FleetAPI"`, `order = 1`; `slot()` → `carapi.ownerSlot`/`fleetSlot`; `canRead(vehicle)`: attachment present and `slot().usable("read")`, and for `"fleet"` additionally `not carapi.ownerSlot.usable("read")`; `fetch` as today but `car.is_awake(slot=self.slot())` / `car.update_vehicle_data(slot=self.slot())`.
- Produces (`TeslaAPI`): `self.ownerReadSource = TeslaAPIReadSource(self, "owner")`, `self.fleetReadSource = TeslaAPIReadSource(self, "fleet")`, both registered; `providers()` → `[OwnerAPIProvider(self), FleetAPIProvider(self)]`; `CarApiVehicle.get_car_api(path, checkReady=True, provesOnline=True, slot=None)` (`slot` overrides `slotFor("read")`), `is_awake(slot=None)`, `update_vehicle_data(slot=None)`; `_registryVehicle` always makes both claims at bind, with live callables: `"OwnerAPI"` (`canCommand=False`, status `"listed"`) and `"FleetAPI"` (`canCommand=lambda: carapi.fleetSlot.usable("command")`, status `"listed"`), so a token pasted or synced after the listing makes the car managed without a re-list (the spec's managed rule is live); the `"TeslaAPI"` claim is no longer made. `apiDebugInterface` is deleted in Task 9.
- Produces (`TeslaAPIProviders.py`):
  - `class OwnerAPIProvider(Provider):` `name = "OwnerAPI"`, `rank = 4`, `local = False`; `__init__(self, carapi)`: `module = carapi`, `readSource = carapi.ownerReadSource`; `declarations()`: `READ_LIST`, `READ_ONLINE`, `READ_CHARGE`, `READ_LOCATION` → `Declaration(CLOUD_FREE)`; `ready(vehicle, cap)` → `carapi.ownerSlot.usable("read")` and `vehicle.attachment("TeslaAPI") is not None`.
  - `class FleetAPIProvider(Provider):` `name = "FleetAPI"`, `rank = 5`, `local = False`; `module = carapi`, `readSource = carapi.fleetReadSource`; `declarations()`: `READ_LIST`, `READ_ONLINE` → `CLOUD_FREE`; `READ_CHARGE`, `READ_LOCATION` → `FLEET_DATA`; `SET_CHARGE_LIMIT`, `START_CHARGING`, `STOP_CHARGING`, `SET_AMPS` → `Declaration(FLEET_COMMAND, RateLimit(50, 60))` (Tesla's published per-vehicle command limit; declared, not enforced until Phase 3 lanes); `WAKE` → `FLEET_WAKE`; `ready(vehicle, cap)`: attachment present and, for reads, `fleetSlot.usable("read") and not ownerSlot.usable("read")`; for commands and wake, `fleetSlot.usable("command")`; `available(capability)`: commands and `WAKE` → `fleetSlot.usable("command")`, reads → `fleetSlot.usable("read")` (the broadcast gate: an Owner-only install never sends a vehicle-less command to TeslaAPI, today's read-only skip); `ampsRange(vehicle)` → `(1, vehicleMaxAmps(vehicle, carapi.master.config["config"]))`; `setAmps(vin, amps)` → `carapi.setChargeRate(int(amps), vehicle=carapi.getVehicleByVIN(vin))` (`False` when the VIN is unknown); `wake(vin)` → `carapi.wakeVehicle(car)` likewise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_teslaapi_providers.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from tests.unit.test_carapivehicle_registry import api_with_registry, VIN
from tests.unit.teslatokens import fleet_token, owner_token

def test_two_providers_with_honest_costs():
    api, reg = api_with_registry(); owner, fleet = api.providers()
    assert (owner.name, owner.rank, fleet.name, fleet.rank, owner.local) == ("OwnerAPI", 4, "FleetAPI", 5, False)
    assert owner.cost(C.READ_CHARGE) == C.CLOUD_FREE and owner.cost(C.SET_AMPS) is None
    assert fleet.cost(C.READ_ONLINE) == C.CLOUD_FREE and fleet.cost(C.READ_CHARGE) == C.FLEET_DATA
    assert fleet.cost(C.SET_AMPS) == C.FLEET_COMMAND and fleet.cost(C.WAKE) == C.FLEET_WAKE
    assert fleet.declarations()[C.SET_AMPS].rateLimit == C.RateLimit(50, 60)
    assert fleet.available(C.SET_AMPS) is False and owner.available(C.READ_CHARGE) is True     # no tokens yet
    assert (owner.readSource.provider, fleet.readSource.provider) == ("OwnerAPI", "FleetAPI")

def test_fleet_reads_only_when_owner_cannot():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); v = reg.get(VIN)
    owner, fleet = api.providers()
    api.storeToken(fleet_token())
    assert fleet.ready(v, C.READ_CHARGE) and fleet.readSource.canRead(v) and not owner.ready(v, C.READ_CHARGE)
    api.storeToken(owner_token())
    assert owner.ready(v, C.READ_CHARGE) and not fleet.ready(v, C.READ_CHARGE) and not fleet.readSource.canRead(v)
    assert fleet.ready(v, C.SET_AMPS) and fleet.ready(v, C.WAKE) and fleet.available(C.WAKE)

def test_claims_are_live_and_follow_the_slots():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); v = reg.get(VIN)   # both slots empty
    assert set(v.claims) == {"OwnerAPI", "FleetAPI"} and v.tier == "observed"
    assert v.claims["OwnerAPI"].status == "listed" and v.claims["OwnerAPI"].commands is False
    api.storeToken(fleet_token()); assert v.tier == "managed"                 # pasted after the listing: no re-list needed
    api.fleetSlot.clear(); assert v.tier == "observed"
    api.storeToken(owner_token()); assert v.tier == "observed"

def test_fleet_commands_resolve_the_car_by_vin():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); car = api.getCarApiVehicles()[0]
    owner, fleet = api.providers(); api.setChargeRate = Mock(return_value=True); api.wakeVehicle = Mock(return_value=True)
    assert fleet.setAmps(VIN, 10) is True; api.setChargeRate.assert_called_once_with(10, vehicle=car)
    assert fleet.wake(VIN) is True; api.wakeVehicle.assert_called_once_with(car)
    assert fleet.setAmps("5YJ3E1EA1KF000009", 10) is False

def test_read_source_passes_its_slot_to_the_car():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); car = api.getCarApiVehicles()[0]
    api.storeToken(owner_token()); v = reg.get(VIN); car.statusDeferral = 0
    car.is_awake = Mock(return_value=True); car.update_vehicle_data = Mock(return_value=True)
    assert api.ownerReadSource.fetch(v, "chargeLimit", False) == {}
    car.is_awake.assert_called_once_with(slot=api.ownerSlot); car.update_vehicle_data.assert_called_once_with(slot=api.ownerSlot)
```
(`owner_token` exists in `tests/unit/teslatokens.py` beside `fleet_token`; if it is named differently there, use that name.)

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: providers`).

- [ ] **Step 3: Implement** per Interfaces; update the two `test_carapivehicle_registry.py` assertions.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_teslaapi_providers.py tests/unit/test_carapivehicle_registry.py tests/unit/test_reads_no_wake.py tests/unit/test_teslaapi_readonly_gate.py tests/unit/test_teslaapi_owner_read.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Split the Tesla API into Owner and Fleet providers with per-slot read sources and claims"
```

### Task 7: Wall Connector VIN from the energy site (G7–G11)

The Fleet API's `GET /api/1/energy_sites/{id}/live_status` is **free** (user's price list) and returns `wall_connectors: [{din, vin?, wall_connector_state, wall_connector_fault_state, wall_connector_power, ocpp_status}]` with `vin` present while a car is connected (source: the tesla-fleet-api npm types; **unverified on hardware**). Energy sites come from `GET /api/1/products` (entries with `energy_site_id`, as `EMS/TeslaPowerwall2.py:257-292` already reads them); the token needs the `energy_device_data` scope (`TeslaTokenSlot.SCOPES["energy"]`); whether the Owner API serves the same path is unconfirmed, so the Owner slot is tried first and a refusal falls to Fleet. The local Gen3 `/api/1/version` gives `part_number` and `serial_number`; the DIN is assumed to be `<part_number>--<serial_number>` (unconfirmed; overridable). Gen2 TWCs never use this path (G11): their RS-485 VIN stays the source, and with no local Gen3 units nothing is queried. Unit tests only (G6).

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/WallConnectorVins.py`.
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`energySites`, `wallConnectorVins`, refusal state), `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py` (declaration, readiness, `wallConnectorVins()`), `lib/TWCManager/EVSEInstance/Gen3TWC.py` (`din`, `refreshVersion`, `cloudVin`), `lib/TWCManager/EVSEController/Gen3TWCs.py` (`noteVitals` extended with the VIN reader), `docs/modules/Controller_Gen3TWCs.md` (the `din` device key and the cloud-VIN behaviour).
- Test: `tests/unit/test_wall_connector_vins.py`.

**Interfaces:**
- Consumes: `TeslaAPI.slotFor("energy")`, `TeslaTokenSlot.usable("energy")`, `.reportScopeRefused("energy", refused=True)`, `.changes`, `.baseURL`; `ProviderOrder.candidates`; `VehicleRegistry.observeTwcVin` (an unknown VIN is `pending` on the first report and confirmed by the next one, exactly as a Gen2 TWC VIN is by its re-query; a known VIN confirms at once).
- Produces (`TeslaAPI`): `ENERGY_SITES_TTL = 3600`; `energySites(slot=None) -> List[dict]` (`/products` entries with `energy_site_id`, via `slotFor("energy")` unless given; cached per slot kind for an hour; `[]` on failure, never raises); `wallConnectorVins(slot) -> Optional[Dict[str, str]]` (`{din: vin}` over every site's `live_status.wall_connectors` with a `vin`; sites whose `live_status` carries no `wall_connectors` key are dropped from later polls; `None` on a transport error; a 401/403 → `slot.reportScopeRefused("energy", refused=True)`, `self._wallConnectorsRefused[slot.kind] = slot.changes`, one INFO `Wall Connector VINs: <slot kind> token refused energy data; not asking again until the token changes`, returns `None`); `wallConnectorVinsReady(slot) -> bool` → slot `usable("energy")`, `_wallConnectorsRefused.get(slot.kind) != slot.changes`, and the slot's sites are not *known* to be empty (`_energySitesEmpty.get(slot.kind) is not True`) — cache reads only, no I/O (Task 1's `ready` contract): products discovery happens inside `wallConnectorVins()` on the background thread, which is the only caller of `energySites()` and sets `_energySitesEmpty[slot.kind]` from its result. No call here ever wakes a car or requests `vehicle_data` (G8).
- Produces (`TeslaAPIProviders.py`): both providers declare `READ_WALL_CONNECTOR_VINS → Declaration(CLOUD_FREE, RateLimit(2, 60))` (one edge query plus one poll per minute, G9); `ready(vehicle, READ_WALL_CONNECTOR_VINS)` (`vehicle` may be `None`): Owner → `carapi.wallConnectorVinsReady(ownerSlot)`; Fleet → `carapi.wallConnectorVinsReady(fleetSlot) and not carapi.wallConnectorVinsReady(ownerSlot)` (the read-slot rule; free either way); `wallConnectorVins()` → `carapi.wallConnectorVins(<its slot>)`.
- Produces (`WallConnectorVins.py`) `class WallConnectorVinReader:` `POLL_SECONDS = 60.0`; `__init__(self, master, order, clock=time.time)` (`self.clock` is the only clock it reads, for `lastQuery` and the rate window alike); `due(self, units) -> bool`: some unit has `occupied is True` and an anonymous `vehicleKey`, and (a connect edge was flagged by `noteConnect()` or `clock() - lastQuery >= POLL_SECONDS`); `query(self, units) -> Dict[str, str]`: for the first provider in `order.candidates(None, READ_WALL_CONNECTOR_VINS)` whose `wallConnectorVins()` is not `None`, honouring its declared `RateLimit` (skip when the limit would be exceeded), return the map (`{}` otherwise); `match(self, units, vins) -> Dict[str, str]` (G10): `unit.din in vins` → that VIN; a unit whose `din` is `None` (no override, version unknown or without a part number) takes the single cloud entry when exactly one unit is local and `vins` has exactly one entry; a known DIN that matches nothing is evidence of a different connector and is skipped; otherwise one INFO `Wall Connector VINs: no DIN match for <ID> (<n> cloud connectors)` and nothing. `apply(self, units)`: `if due: vins = query(); for unit, vin in match().items(): unit.cloudVin = vin; unit._correlate()`; a unit whose `vehicleKey` is a VIN is skipped (polling stops once the session has a VIN, G9).
- Produces (`Gen3TWC`): `_version: Optional[dict] = None` (the `/api/1/version` cache; `{}` once fetched without a part number); `din -> Optional[str]` (config `devices[].din`, else `"<part_number>--<serial_number>"` from `_version`, else `None`); `refreshVersion() -> bool` (one `GET /api/1/version` into `_version`, background thread, retried on the next refresh until it succeeds); `cloudVin` cleared on the disconnect edge.
- Produces (`Gen3TWCs`): `self.vinReader = WallConnectorVinReader(master, master.providerOrder)`; `noteVitals(unit, rising)` (Task 4) additionally calls `unit.refreshVersion()` while `unit._version is None`, `vinReader.noteConnect()` when `rising`, then `vinReader.apply(self.devices())` — so a unit-level `refreshVitals()` (what the tests drive) reaches the reader. Products discovery runs on the first query and then at most hourly (the `TeslaAPI` cache). Nothing here runs on the serial thread or under a lock.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_wall_connector_vins.py
import re, threading
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Order import ProviderOrder
from TWCManager.Vehicle.Providers.WallConnectorVins import WallConnectorVinReader
from tests.unit.test_carapivehicle_registry import VIN
from tests.unit.test_gen3twc_provider import Clock, make as make_gen3, vitals
from tests.unit.teslatokens import new_api, owner_token
DIN = "1457768-02-G--TG123"
PRODUCTS = {"response": [{"energy_site_id": 7, "site_name": "Home"}]}
def live(vin=VIN, din=DIN): return {"response": {"wall_connectors": [{"din": din, "vin": vin, "wall_connector_state": 2}]}}

def setup(requests_mock, status=200, vin=VIN, din=DIN):
    m, ctl, p = make_gen3(); m.config["vehicle"] = {"teslaAPI": {"enabled": True}}; m.tokenSyncEnabled.return_value = False
    m.modules = {}; m.settings = {}; m.settingsLock = threading.RLock(); m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    api = new_api(master=m); api.carApiVehicles = []; api.storeToken(owner_token()); reg = m.vehicleRegistry
    requests_mock.get(re.compile(r".*/api/1/products$"), json=PRODUCTS)
    requests_mock.get(re.compile(r".*/energy_sites/7/live_status$"), status_code=status, json=live(vin, din) if status == 200 else {})
    m.providerOrder = ProviderOrder(m); [m.providerOrder.register(x) for x in api.providers()]
    ctl.vinReader = WallConnectorVinReader(m, m.providerOrder, clock=Clock()); (u,) = ctl.devices(); u.device_cfg["din"] = din
    return api, reg, ctl, u

def liveCalls(requests_mock): return [r for r in requests_mock.request_history if "live_status" in r.url]

def test_vin_from_live_status_confirms_the_session(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    vitals(u, True)                                  # connect edge: pending (first report of an unknown VIN)
    assert reg.get(VIN) is None and len(liveCalls(requests_mock)) == 1
    ctl.vinReader.clock.t += 60; vitals(u, True)     # next poll confirms, as a Gen2 re-query would
    assert u.vehicleKey == VIN and reg.get(VIN).value("twcVin") == u.ID and reg.get("anon:" + u.ID) is None

def test_known_vin_confirms_at_once_and_polling_stops(requests_mock):
    api, reg, ctl, u = setup(requests_mock); reg.getOrCreate(VIN, "TeslaMateVehicle")
    vitals(u, True); assert u.vehicleKey == VIN
    ctl.vinReader.clock.t += 600; vitals(u, True); vitals(u, True)
    assert len(liveCalls(requests_mock)) == 1

def test_din_mismatch_falls_to_single_candidate(requests_mock):
    api, reg, ctl, u = setup(requests_mock, din="other--din"); u.device_cfg["din"] = DIN
    car = reg.getOrCreate(VIN, "t"); car.observe("pluggedIn", True, "TeslaMateVehicle")
    vitals(u, True)
    assert u.cloudVin is None and u.vehicleKey == VIN            # a known, mismatching DIN: G3 did it, not the cloud

def test_single_local_single_cloud_matches_without_din(requests_mock):
    api, reg, ctl, u = setup(requests_mock, din="whatever"); u.device_cfg.pop("din", None); u._version = {}
    vitals(u, True); ctl.vinReader.clock.t += 60; vitals(u, True)
    assert u.cloudVin == VIN

def test_403_marks_the_capability_not_ready_once(requests_mock):
    api, reg, ctl, u = setup(requests_mock, status=403)
    vitals(u, True); ctl.vinReader.clock.t += 60; vitals(u, True)
    assert len(liveCalls(requests_mock)) == 1
    assert not api.providers()[0].ready(None, C.READ_WALL_CONNECTOR_VINS)
    api.storeToken(owner_token()); assert api.providers()[0].ready(None, C.READ_WALL_CONNECTOR_VINS)   # token change re-arms

def test_no_query_without_an_occupied_gen3_and_no_vehicle_calls(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    ctl.vinReader.apply(ctl.devices()); assert liveCalls(requests_mock) == []
    vitals(u, True)
    assert all(not re.search(r"wake_up|vehicle_data", r.url) for r in requests_mock.request_history)

def test_rate_limit_is_respected(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    for _ in range(4): ctl.vinReader.noteConnect(); ctl.vinReader.apply(ctl.devices()); vitals(u, True)   # one clock, no time passes
    assert len(liveCalls(requests_mock)) <= 2
```
(`api.storeToken` bumps `slot.changes`; if `tests.unit.teslatokens.owner_token` lacks the energy scope, pass `scp=` with `energy_device_data` as `fleet_token` allows.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `WallConnectorVins`).

- [ ] **Step 3: Implement** per Interfaces; document the `din` key and the cloud-VIN order (cloud VIN, single candidate, anonymous) in `docs/modules/Controller_Gen3TWCs.md`, marked unverified on hardware.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_wall_connector_vins.py tests/unit/test_gen3twc_provider.py tests/unit/test_teslaapi_providers.py tests/unit/test_teslapowerwall2_ems.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle lib/TWCManager/EVSEInstance/Gen3TWC.py lib/TWCManager/EVSEController/Gen3TWCs.py
git add lib/TWCManager tests/unit/test_wall_connector_vins.py docs/modules/Controller_Gen3TWCs.md
git commit -m "Identify the car on a Gen3 TWC from the energy site's free live_status before falling back to a single candidate"
```

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

### Task 11: Charging points by generic grouping; the distributor allocates per point (closes A18)

Within a point, Phase 2 uses a transitional rule: when the point has a local (TWC) member it carries the whole target and `TWCSlave.send_master_heartbeat` applies `chargeRateControl` exactly as today (mode 2 / mode 3 below 6 A queue the car's rate through the façade and offer the wiring maximum); vehicle members of such a point get no direct amps command from the distributor, which ends the `MergedEVSE`-vs-`_evseTargetAmps` fight (inventory I3). Points without a local member send the target to their vehicle endpoints. Phase 3's layered actuators replace this rule.

**Files:**
- Create: `lib/TWCManager/EVSEInstance/ChargingPoint.py`.
- Delete: `lib/TWCManager/EVSEInstance/MergedEVSE.py`.
- Modify: `lib/TWCManager/TWCMaster.py:504-532` (`getDedupedEVSEs` → `chargingPoints`), `:534-620` (`distributeEVSEPower`), `tests/unit/test_distributor_loop.py:27` (`m.chargingPoints = lambda: evses`), `CHANGELOG.md`.
- Test: `tests/unit/test_charging_points.py`.

**Interfaces:**
- Consumes: `EVSEInstance.vehicleKey/occupied/isLocal/isReadOnly/minPower/maxPower/wantsToCharge/setTargetPower`, `Gen2TWC`, `VehicleEndpoint`.
- Produces (`ChargingPoint.py`):
  - `class ChargingPoint(EVSEInstance):` `__init__(self, master, key: str, endpoints: List[EVSEInstance])`; `key`, `endpoints` (copy); `localEndpoints` / `vehicleEndpoints` (by `isLocal`); `ID` = `"Point-" + key`; `isReadOnly` → all; `isLocal` → any; `isCharging`/`wantsToCharge` → any; `occupied` → `True` if any member is `True`, else `False` if all are `False`, else `None`; `currentAmps`/`currentVoltage`/`currentPower` → averaged over the local members when any, else all (as `MergedEVSE`); `minPower` → max over members; `maxPower` → min over members; `currentVIN` → first non-empty; `vehicleKey` → `key`; `controllers` → union in order; `setTargetPower(watts)`: local members when any (each gets `watts`), else every non-read-only member; `startCharging` → every member; `stopCharging` → `chargeStopMode` 1: non-local non-read-only members, else local members, falling back to all (as `MergedEVSE`; no Phase 2 caller).
  - `groupEndpoints(master, endpoints: List[EVSEInstance]) -> List[ChargingPoint]`: endpoints sharing a `vehicleKey` (upper-cased, `None` never groups) form one point keyed by it; an endpoint with `vehicleKey None` is its own point keyed by its `ID`; order: first appearance.
- Produces (`TWCMaster`): `chargingPoints(self) -> List[ChargingPoint]` = `groupEndpoints(self, self.getAllEVSEs())`; `getDedupedEVSEs` removed. `distributeEVSEPower`: same activation rule (a controller other than `Gen2TWCs` registered), iterates `chargingPoints()`; after the water-fill, the **idle-TWC rule**: every point not in `wants_power`, not read-only, with a member whose `idleMinimum` is `True` (a Gen2 TWC) is offered `point.minPower` when `remaining_watts >= point.minPower` (then `remaining_watts -= point.minPower`), else `0` — in both the early `not wants_power` branch and the final zero-out loop; every other idle point (a Gen3 unit, which reports `vehicle_connected` whatever its headroom, or a vehicle endpoint) still gets `0`. A Gen3 endpoint takes part in `groupEndpoints` like any other: its `vehicleKey` is the correlated VIN or its anonymous key, so two Gen3 units are two points and a correlated car's vehicle endpoint joins its Gen3's point. The distributor never sums Gen3 units: each unit's point gets its own target and `Gen3TWC.setTargetPower` hands it to `Gen3TWCs.setUnitTarget`, where the shared headroom is derived (Task 4, G2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_charging_points.py
from unittest.mock import MagicMock, Mock
from TWCManager.EVSEInstance.ChargingPoint import ChargingPoint, groupEndpoints
from TWCManager.TWCMaster import TWCMaster
VIN = "5YJ3E1EA1KF000001"

def ep(ID, key=None, local=False, minW=1200, maxW=7680, wants=True, ro=False, occupied=None, amps=0.0, idleMin=None):
    e = MagicMock(); e.ID = ID; e.vehicleKey = key; e.isLocal = local; e.minPower = minW; e.maxPower = maxW
    e.idleMinimum = local if idleMin is None else idleMin                  # a Gen2 TWC by default; Gen3 passes idleMin=False
    e.wantsToCharge = wants; e.isReadOnly = ro; e.occupied = occupied; e.currentAmps = amps; e.currentVoltage = [240, 0, 0]
    e.currentVIN = key if key and not key.startswith("anon:") else ""; e.controllers = ["Gen2TWCs" if local else "VehicleEndpoints"]; return e

def test_grouping_is_by_vehicle_key_and_merge_count_may_be_one():
    twc = ep("Gen2TWC-8244", VIN.lower(), local=True); car = ep("Vehicle-" + VIN, VIN); idle = ep("Gen2TWC-8245", None, local=True); anon = ep("Gen2TWC-8246", "anon:8246", local=True)
    pts = groupEndpoints(Mock(), [twc, car, idle, anon])
    assert [p.ID for p in pts] == ["Point-" + VIN, "Point-Gen2TWC-8245", "Point-anon:8246"]
    assert pts[0].endpoints == [twc, car] and pts[0].isLocal and pts[0].currentVIN == VIN and pts[0].vehicleKey == VIN
    assert pts[1].endpoints == [idle] and pts[1].vehicleKey == "Gen2TWC-8245"

def test_point_limits_and_occupancy():
    p = ChargingPoint(Mock(), VIN, [ep("a", VIN, local=True, minW=1440, maxW=7680, occupied=True), ep("b", VIN, minW=1200, maxW=3840, ro=True)])
    assert (p.minPower, p.maxPower, p.isReadOnly, p.occupied) == (1440, 3840, False, True)
    assert ChargingPoint(Mock(), "x", [ep("a"), ep("b")]).occupied is None

def test_target_goes_to_the_local_member_only_when_present():
    twc = ep("t", VIN, local=True); car = ep("c", VIN)
    ChargingPoint(Mock(), VIN, [twc, car]).setTargetPower(2400)
    twc.setTargetPower.assert_called_once_with(2400); car.setTargetPower.assert_not_called()
    ChargingPoint(Mock(), VIN, [car]).setTargetPower(2400); car.setTargetPower.assert_called_once_with(2400)

def distributor(points, amps, controllers=("Gen2TWCs", "VehicleEndpoints")):
    m = TWCMaster.__new__(TWCMaster); m.config = {"config": {"defaultVoltage": 240, "numberOfPhases": 1}}
    ctrl = MagicMock(); ctrl.maxPower = 100000
    m.getModulesByType = lambda t: [{"name": n, "ref": ctrl} for n in controllers]
    m.chargingPoints = lambda: points; m.getMaxAmpsToDivideAmongSlaves = lambda: amps; return m

def test_stopped_car_stays_one_point():                             # Review Focus 5 / A18
    twc = ep("Gen2TWC-8244", VIN, local=True, wants=False); car = ep("Vehicle-" + VIN, VIN, wants=True)
    pts = groupEndpoints(Mock(), [twc, car]); assert len(pts) == 1
    distributor(pts, 40).distributeEVSEPower()
    twc.setTargetPower.assert_called_once_with(7680); car.setTargetPower.assert_not_called()

def test_idle_twc_keeps_its_minimum_when_budget_allows():
    busy = ep("Vehicle-" + VIN, VIN, maxW=4800); idle = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440)
    distributor(groupEndpoints(Mock(), [busy, idle]), 40).distributeEVSEPower()           # 9600 W: 4800 to the car, 1440 to the idle TWC
    assert busy.setTargetPower.call_args.args[0] == 4800 and idle.setTargetPower.call_args.args[0] == 1440
    busy2 = ep("Vehicle-" + VIN, VIN, maxW=4800); idle2 = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440)
    distributor(groupEndpoints(Mock(), [busy2, idle2]), 20).distributeEVSEPower()          # 4800 W: nothing left for the idle TWC
    assert idle2.setTargetPower.call_args.args[0] == 0
    idle3 = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440); remote = ep("Vehicle-x", "X", wants=False)
    distributor(groupEndpoints(Mock(), [idle3, remote]), 40).distributeEVSEPower()         # nobody wants power: idle TWC still gets its minimum
    assert idle3.setTargetPower.call_args.args[0] == 1440 and remote.setTargetPower.call_args.args[0] == 0

def test_idle_gen3_units_get_zero_and_two_units_are_two_points():                  # G2 (grouping side)
    g1 = ep("Gen3TWC-10.0.0.1", "anon:Gen3TWC-10.0.0.1", local=True, wants=True, maxW=11520, idleMin=False)
    g2 = ep("Gen3TWC-10.0.0.2", None, local=True, wants=False, minW=1440, idleMin=False)
    pts = groupEndpoints(Mock(), [g1, g2]); assert [p.ID for p in pts] == ["Point-anon:Gen3TWC-10.0.0.1", "Point-Gen3TWC-10.0.0.2"]
    distributor(pts, 40).distributeEVSEPower()
    assert g1.setTargetPower.call_args.args[0] == 9600 and g2.setTargetPower.call_args.args[0] == 0

def test_correlated_car_joins_its_gen3_point():
    g = ep("Gen3TWC-10.0.0.1", VIN, local=True, idleMin=False); car = ep("Vehicle-" + VIN, VIN)
    (pt,) = groupEndpoints(Mock(), [g, car]); pt.setTargetPower(2400)
    g.setTargetPower.assert_called_once_with(2400); car.setTargetPower.assert_not_called()

def test_pure_gen2_leaves_distributor_off():                         # Review Focus 2
    idle = ep("Gen2TWC-8245", None, local=True, wants=False)
    distributor([ChargingPoint(Mock(), "Gen2TWC-8245", [idle])], 40, controllers=("Gen2TWCs",)).distributeEVSEPower()
    idle.setTargetPower.assert_not_called()

def test_no_type_knowledge_left():
    import subprocess
    from pathlib import Path
    out = subprocess.run(["git", "grep", "-l", "MergedEVSE\\|getDedupedEVSEs\\|TeslaAPIEVSE\\|TeslaAPIController", "--", "lib/TWCManager"],
                         capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2])).stdout.split()
    assert out == []
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `ChargingPoint`).

- [ ] **Step 3: Implement** per Interfaces; delete `MergedEVSE.py`; update `test_distributor_loop.py`.

- [ ] **Step 4: Run the full suite** → PASS (baseline 1153 plus this phase's tests).

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Architecture`: `    * (@MikeBishop) - Charging endpoints (a TWC, or a car whose amps BLE, Fleet or HomeAssistant can set) are grouped into charging points by the car they serve; the distributor allocates per point, an idle TWC keeps its minimum, and a car's amps are queued to the vehicle worker instead of being sent to the Fleet API from the RS-485 loop`. `* Bugfixes`: `    * (@MikeBishop) - A car that stops charging on its TWC no longer gets a second power share and Fleet charge-rate commands of its own`.
```bash
black lib/TWCManager/EVSEInstance/ lib/TWCManager/TWCMaster.py
git add -A lib/TWCManager/EVSEInstance lib/TWCManager/TWCMaster.py tests/unit CHANGELOG.md
git commit -m "Group charging endpoints into charging points and allocate per point"
```

- [ ] **Step 6: Live check on the user's box (deploy branch, pre-approved; coordinate first — the ledger notes another session may hold the box)**

Deploy `vehicle-model/phase2` to `twcmanager`, restart, and confirm in the log: `Providers: Gen2TWC, TeslaBLE, ...` at boot in rank order; no `Main loop stalled` beyond the boot-time one seen on 8e07669; with the car on the TWC, exactly one `Point-<VIN>` in a `distributeEVSEPower` DEBUG line (add the line if absent: one DEBUG per round listing point IDs and offers) and **zero** Fleet `set_charging_amps` requests while the TWC serves the car; a BLE charge-limit apply still lands (façade walk BLE first); `/api/sendTeslaAPICommand` wake from the debug page works and is logged under the provider that served it. Record findings in the PR description, then roll the box back per the ledger's rollback note.

---

## Inventory rows this phase closes

- **A1** (`Capability`/provider interface, fixed order replacing `calculateModulePriority`/`getModuleByPriority` as the policy; those two methods stay in `TWCMaster` unused until Phase 3 deletes `VehiclePriority`), **A2** (`commandPolicy` as suppressions on the order), **A8** (`VehicleEndpoint` asks the order; `isReadOnly` and `provider` derived from candidates; `isLocal` stays `False`, which the charging-point rule relies on), **A9** (cost per operation; read sources ordered free before billed; Fleet reads only when Owner cannot), **A10** (HomeAssistant in the order, last; default-on when loaded), **A17** (read-only under `ble_only` → no power share), **A18** (grouping by vehicle key; a stopped car stays one point), **A24** (Owner and Fleet are separate providers; the order, not `slotFor`, decides which channel a command uses; `slotFor` remains only inside `TeslaAPI`'s own methods), **A26** (debug API via `ProviderOrder.debugCommand`).
- Declared for Phase 3: Gen2 disruptive stop (`STOP_CHARGING`, tier 3, `chargeStopMode` 2/3), Fleet rate limit, `Provider.summary()` for Phase 6 panels.

## Carry-forwards to later phases

- Phase 3 (amps reconciler, layered actuators): `ChargingPoint.setTargetPower`'s TWC-carries-all rule and `TWCSlave`'s `chargeRateControl` branch are replaced; the `#660` raise-to-max over Fleet for a Fleet-only car on a TWC is dropped by the default paid-amps rule in this phase (BLE still raises for free) — decide there whether a one-time raise is worth $0.001/session.
- Phase 3: `Gen2TWCProvider.stopCharging` gets its caller; `TWCMaster.stopCarsCharging`/`startCarsCharging` go. The Gen3 zero-headroom stop is declared at the normal local tier but is unverified on hardware: treat it as a normal stop and watch the car's behaviour (G4); on a multi-unit bus the provider declares `NO_INDIVIDUAL_STOP`, so the reconciler picks another actuator (BLE or Fleet on that car) for a per-unit stop.
- Separate design (inventory A27): Gen3 correlation beyond "exactly one freshly plugged candidate" is VIN-less fingerprinting.
- Phase 5: `Gen2TWC.vehicleKey`'s `lastVIN`-while-plugged-state rule and `occupied` become presence attribution; the registry plug session is still `isCharging`-based (ledger I5).
- Phase 6: `Provider.summary(vehicle)` feeds the per-car provider panels; Forget drops the `CarApiVehicle` (ledger M8).

## Decisions made in this plan

1. Package layout: `lib/TWCManager/Vehicle/Providers/` for the provider layer; endpoints keep the `EVSEInstance` base class and file names; `ChargingPoint`, `VehicleEndpoint`, `VehicleEndpoints` replace `MergedEVSE`, `TeslaAPIEVSE`, `TeslaAPIController` (files deleted) — minimal churn, spec's "endpoint + charging point" vocabulary.
2. Cost is `(tier, price)`; the order sorts by `(tier, fixed rank)`; locality is folded into tier 0 — "by cost then locality" with one key.
3. Fixed ranks: Gen2TWC 0, Gen3TWC 1, TeslaBLE 2, telemetry 3, OwnerAPI 4, FleetAPI 5, HomeAssistant 6 — the spec's list order with Gen3 beside Gen2 (G1: its own rank rather than a tie, so the order is total).
4. HomeAssistant is billed-tier with unknown price and ranked after Fleet for reads and commands — spec lists HA last; Phase 1 ruled HA reads last; HA's Tesla integration is commonly the user's own Fleet app.
5. One `Gen2TWCProvider` for every TWC (readiness per vehicle via attribution) rather than one provider per TWC — slaves appear and vanish at runtime; ranges are still per device.
6. `api_only` keeps meaning "TeslaBLE suppressed for every operation" with a one-time INFO notice, instead of mapping to the default — users chose it because Bluetooth does not work for them; the default would add a 5–15 s BLE timeout before every command (the "reason that surfaces" the spec allowed for).
7. `ble_only` suppresses every remote provider for commands (Fleet and HomeAssistant), not only TeslaAPI — HA is now reachable.
8. The default "Fleet never sets amps" rule considers the requested amps: a local path counts only when its range covers the target — keeps `chargeRateControl` 3 working below 6 A over Fleet and makes mode 2 (TWC not an amps path) work; the `#660` raise over Fleet is dropped when the TWC covers the target (spec default; BLE still raises).
9. Fine-grained suppressions live in `settings["providerSuppressions"]` / config `vehicle.providerSuppressions` with no UI this phase; `commandPolicy` stays the UI control, relabelled — Phase 6 owns provider UI.
10. Ledger I5: TWC endpoint correlation is `currentVIN`, else the anonymous plug session, else `lastVIN` while the TWC reports a plugged state; `occupied` is tri-state (Gen2 00 is unknown, not empty); the registry plug session stays `isCharging`-based until Phase 5 — charging points no longer inherit "session == charging".
11. Inside a point the TWC member carries the whole target and `TWCSlave` applies `chargeRateControl` as today; vehicle members of a TWC point get no distributor amps command — removes the I3 fight without pre-empting Phase 3's layered actuators.
12. `VehicleEndpoints` is registered only when TeslaAPI is loaded and lists TeslaAPI-attached at-home cars (today's condition and rule) — BLE-only and HA-only installs stay on the per-slave path until Phase 4, so no new code path on their boxes.
13. `VehicleEndpoint.setTargetPower` queues `setAmps` to the vehicle worker (on change or every 600 s) instead of calling Fleet synchronously on the serial loop — threading constraint; TeslaAPI's own repeat-skip still gates paid resends.
14. The Fleet read source is ready only when the Owner slot cannot read — reproduces `slotFor("read")`, so splitting the sources adds no paid read.
15. Claims split into `OwnerAPI` (listed, no commands) and `FleetAPI` (commands when the slot can); the attachment name stays `"TeslaAPI"` — tier semantics unchanged, Vehicles tab shows which slot does what.
16. Fleet declares `RateLimit(50, 60)` on commands (Tesla's published per-vehicle limit), unenforced until Phase 3 lanes; other providers declare none.
17. Gen2 disruptive stops are one `STOP_CHARGING` capability at tier 3, ready only when `chargeStopMode` is 2 or 3 (off by default), with `stopCharging(vin)` implemented but uncalled this phase; `TWCMaster.stopCarsCharging` is unchanged.
18. Idle-TWC minimum is a distributor rule: a local point not wanting power gets its minimum when the remaining budget allows — spec "must be kept"; today's distributor path offered 0.
19. Per-device range override config key `controller.Gen2TWCs.ranges.<TWCID>.{minAmps,maxAmps}` — mirrors the existing `controller.Gen3TWCs` key shape.
20. `calculateModulePriority`/`getModuleByPriority` stay in `TWCMaster` unused by the façade — removed with `VehiclePriority` in Phase 3.
21. `TeslaAPI.apiDebugInterface` is deleted; `/api/sendTeslaAPICommand` calls `ProviderOrder.debugCommand`, which honours suppressions and readiness and works on BLE-only installs.
22. G1: Gen3 TWC is a provider (Task 4, right after Gen2): local, free, tier 0, its own rank 1 (not a tie with Gen2, so the order stays total); capabilities `setAmps` with range 6..fuse per device, start/stop, passive plug/amps reads from vitals; registered only inside the existing `controller.Gen3TWCs.enabled` block, so a disabled Gen3 changes nothing.
23. G2 (revised, user direction): Gen3 units are separate endpoints with their own targets for the distributor and charging points; only `Gen3TWCs`, which owns the one fake-Neurio value, aggregates: it water-fills one shared headroom `h` so the net draw matches the sum of per-unit targets (unknown demand = unlimited; a unit measured below `h` is car-limited and its vitals amps are its demand; all unconstrained → `h = sum/n`; one unit → `h = target`, today's behaviour), each unit in its own fuse terms (bisection on the house amps `H` with `h_i = F_i − H`; no smallest-fuse approximation), clamped to `[6 A, fuse]`, recomputed on target changes and once per vitals refresh, damped at 1 A. A zero-target unit beside a charging sibling cannot be stopped through the shared value: it is excluded from the sum, may draw up to `h`, and the provider declares `NO_INDIVIDUAL_STOP` while more than one unit is occupied; all targets 0 is still a full-fuse house load. Tested: two unconstrained, one car-limited, one zero-target, single unit.
24. G3: `vehicle_connected` rising starts `anon:Gen3TWC-<ip>` through the Phase 1 plug-session API and falling ends it; `occupied` is `vehicle_connected`; the car is correlated only when exactly one non-anonymous registry car reports `pluggedIn` True within 120 s of the connect, is not already attributed to another point, and is not known away (`atHome` False) — then `observeTwcVin` merges the anonymous vehicle and the car's vehicle endpoint joins the Gen3's point; otherwise it stays anonymous (VIN-less fingerprinting is its own design) and the `VehicleEndpoints` blind rule lists no vehicle endpoints, so no Fleet amps go to any candidate.
25. G4: the Gen3 zero-headroom stop is `STOP_CHARGING` at the normal local tier, unlike Gen2's tier-3 disruptive stops; unverified on hardware, carried to Phase 3.
26. G5: no new polling loop — `Gen3TWC.refreshVitals()` keeps today's 5 s / 10 s TTLs and runs on the background thread via a `gen3Vitals` task queued when `allEVSEs` finds a stale cache; every property reads the cache; no HTTP on the serial thread or under a registry/settings lock. Cost: the first distributor round after boot sees no Gen3 units (one round of delay).
27. G6: Gen3 is verified by unit tests only (no hardware on the box).
28. Gen3 `isLocal` becomes `True` (on-premise, tier 0): the old `False` only steered `MergedEVSE`, which is gone.
29. Idle Gen3 units get 0 headroom (today's distributor behaviour): plug detection comes from vitals, not from an offered minimum, so the idle-TWC-minimum rule is keyed on a new `EVSEInstance.idleMinimum` flag that only `Gen2TWC` sets.
30. G7: Gen3 car identity in order: a cloud VIN from `live_status.wall_connectors` matched by DIN, then the single-candidate rule (G3), then anonymous; a cloud VIN goes through the same `observeTwcVin` path as a Gen2 TWC VIN (unknown VIN pending until the next poll confirms it; known VIN at once) — it is evidence of which car is plugged in, nothing more. Facts about `live_status`/DIN are from the tesla-fleet-api types and unverified on hardware.
31. G8: a free read capability `wallConnectorVins` on the Owner and Fleet providers (`Declaration(CLOUD_FREE, RateLimit(2, 60))`), ordered after local sources; ready only when the slot has a token with energy scope, the products list holds an energy site, and no 401/403 has been seen since the token last changed (one INFO on refusal); Owner tried first, Fleet only when Owner cannot (free either way); never wakes a car, never touches vehicle endpoints.
32. G9: no new free-running loop — queried on a Gen3 `vehicle_connected` rising edge and then every 60 s while a Gen3 is occupied without a VIN, stopping once the session has one; products discovery at first use then at most hourly; all from `refreshVitals()` on the background thread, no HTTP under locks or on the serial thread; the provider's `RateLimit` is honoured by the reader.
33. G10: DIN match primary `<part_number>--<serial_number>` from local `/api/1/version` (fetched once, cached; format unconfirmed), config override `controller.Gen3TWCs.devices[].din`; fallback only when the local DIN is unknown: exactly one local Gen3 and exactly one cloud wall connector; a known DIN that matches nothing is skipped (it is evidence of a different connector); otherwise one INFO and fall to G3.
34. G11: Gen2 TWCs never use the energy-site path; a Gen2-only install with wall connectors on the account has no local Gen3 units, so nothing is queried.
36. Pre-flight rulings 1–24 (`.superpowers/sdd/2026-10-14-vehicle-model-phase2-providers/preflight.md`) are folded into the tasks above; the ones that change behaviour: a candidate whose known range does not cover the target is dropped (spec's layered rule); Gen2 `ampsRange` floors at 6 A under `chargeRateControl` 3 (the threshold `TWCSlave` really uses); `dispatch` never reaches TWC providers (no TWC target written off the serial thread); both TeslaAPI claims are made at bind with live callables; `Provider.available()` gates broadcasts (today's read-only skip); the blind rule keys on `vehicleKey`; HomeAssistant stays last and is named as such in the constraint and CHANGELOG; `api_only` keeps suppressing TeslaBLE only.
35. Task split: G7–G11 are their own Task 7 ("Wall Connector VIN from the energy site"), placed after the Owner/Fleet providers it extends rather than directly after the Gen3 task, because Task 4 already carries the plug sessions, correlation and shared headroom and the capability lives on `TeslaAPIProviders.py` (created in Task 6).

## Questions for the user

None — every open point above is decided with its reason; say so if any decision should go the other way before Task 1 starts.
