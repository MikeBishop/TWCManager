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
- Produces (`Gen3TWCs`): `sharedControl = True`; `devices() -> List[Gen3TWC]` (every configured unit from the cache, reachable or not); `unitTargets -> Dict[str, float]` (watts per unit); `DAMP_AMPS = 1.0`; `MIN_AMPS = 6.0`; `setUnitTarget(self, unitId, watts) -> None` records the unit's own target (the distributor and charging points address Gen3 units **separately**, exactly as Gen2 slaves; only the controller, which owns the one fake-Neurio value, aggregates) and calls `republish()`; `headroom() -> float` (the first device's current headroom `F_1 - H` in amps, rounded to 0.01); `demandAmps(unit) -> float` from the unit's cached vitals: its measured `vehicle_current_a` when `1.0 <= measured < h_i - DAMP_AMPS` and `evse_state == "charging"` (car-limited: a full battery drawing 3 A); otherwise `inf` (unknown, unreachable, or drawing at the headroom — never 0, so a unit with a target is always served); `solve() -> float` (G2, water-filling): targets in amps `A_i = t_i / (V * phases_i)` over units with `t_i > 0`; the house load in amps `H` is chosen by bisection on `[0, max fuse]` (20 steps, then rounded to 0.01 A so the published watts are exact) as the largest `H` with `sum_i min(d_i, max(0, F_i - H)) >= sum_i A_i` — each unit in its own terms (`h_i = F_i - H`, per-device fuse; with equal fuses and unconstrained units this is `h = sum(A_i) / n`; with one unit it is `h = A_1`, today's behaviour) — then clamped so every targeted unit keeps `h_i >= MIN_AMPS`; when every target is 0, `H = max fuse` (the full fuse as load, a stop); zero-target units are **excluded** from the sum (they cannot be stopped individually through the shared value and may still draw up to `h`); `republish()`: recomputes and calls `setHouseWatts(watts=H * V, phases=p, voltage=V)` (`p`/`V` from the first device as today) only when the new `h` differs from the published one by more than `DAMP_AMPS` or the target set changed (damping); `noteVitals(self, unit, rising: bool) -> None` (called by each unit at the end of its own `refreshVitals()`): the damped `republish()` (closed loop on the existing cadence, no new polling loop, G5; Task 7 adds the VIN reader here); `refreshVitals()` → `refreshVitals()` on every device and nothing else. `allEVSEs` → devices whose cached `isReachable` is `True`; when any device `vitalsStale()`, `master.queue_background_task({"cmd": "gen3Vitals"})`.
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

