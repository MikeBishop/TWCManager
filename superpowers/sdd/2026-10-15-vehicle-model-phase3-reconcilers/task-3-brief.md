### Task 3: Lanes: per-channel attempt runners with classified outcomes, rate limits and a bounded queue

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Lanes.py`.
- Modify: `lib/TWCManager/Vehicle/Providers/Order.py` (`debugCommand` submits a one-shot; `dispatch` stays until Task 10 — `VehiclePriority.setAmps` still calls it), `lib/TWCManager/Vehicle/Providers/Provider.py` (command method signatures), `tests/unit/test_provider_order.py` (`test_debug_command_goes_through_the_order` and `test_debug_set_charge_rate_reaches_fleet_past_a_covering_twc` rewritten on a master with `lanes = Lanes(m, inline=True)` — the second keeps its final `dispatch` assertion; `test_debug_command_tries_each_provider_once` becomes one provider per command: BLE is called once and Fleet not at all; the other `dispatch` tests stay), `tests/unit/test_registry_callers.py` and `test_carapivehicle_registry.py` (debug-route assertions: `debugCommand` returns True when an attempt was submitted).
- Test: `tests/unit/test_lanes.py`.

**Interfaces:**
- Produces (`Provider.py`): `setChargeLimit(self, vin, limit: int) -> Outcome`, `startCharging(self, vin) -> Outcome`, `stopCharging(self, vin) -> Outcome`, `setAmps(self, vin, amps: int) -> Outcome`, `wake(self, vin) -> Outcome`, `probe(self, vin) -> Outcome` (a cheap, non-waking reachability check: `DONE` when the car answered) — defaults return `Outcome(UNSUPPORTED, "not implemented")`. `PROBE = "probe"` (a lane-only pseudo-capability, never in `Capability.COMMANDS`); `commandMethod(capability) -> str` maps a capability (or `PROBE`) to the method name.
- Produces (`Lanes.py`):
  - `LANE_PROVIDERS = {"local": frozenset({"Gen2TWC", "Gen3TWC"}), "ble": frozenset({"TeslaBLE"}), "cloud": frozenset({"OwnerAPI", "FleetAPI", "HomeAssistant", "TeslaMateVehicle", "FleetTelemetryMQTT"})}`; an unknown provider name maps to `"cloud"`.
  - `entryKey(attempt) -> tuple`: `(key, aspect)` for an aspect attempt, `(key, "probe")` for a probe, `(key, "debug", <sequence>)` for a one-shot — probes and one-shots never replace each other.
  - `class Lane:` `MAX_PENDING = 64`; `__init__(self, name, providers: FrozenSet[str], master, report: Callable[[Attempt, Outcome], None], clock=time.time, inline=False)` (`clock` stamps nothing itself; it is the domain the attempts carry; the rate-limit window alone uses `time.monotonic` internally); `submit(self, attempt) -> bool` (a pending entry with the same `entryKey` is **replaced and reported** as `Outcome(ERROR, "replaced")`; stop attempts (`capability == STOP_CHARGING`) go to the front; when full the oldest non-stop entry is **dropped and reported** as `Outcome(ERROR, "dropped")` with one WARNING; `inline` runs it now on the caller's thread and reports before returning); `pending() -> int`; `busy -> bool`; `allows(self, provider, capability, vin) -> bool` (the provider's declared `RateLimit` for the capability, per `(provider.name, capability, vin)` sliding window over `rateLimit.perSeconds`; `True` when none is declared; `note(provider, capability, vin)` records a run); `cancel(key) -> int` (removes pending `STOP_CHARGING` entries for the key only — never a start — and reports each as `Outcome(ERROR, "cancelled")`; the running attempt is left alone); `start()`, `stop()`, `drain(timeout) -> bool` (sets stopping; drops every pending non-stop entry with a report each (INFO with the count); runs or waits for pending stops and the running attempt up to `timeout`; callable on a lane that was never started, in which case it runs the pending stops on the caller's thread; returns whether it finished); `_run()` loops `while not self._stopping` on a `Condition.wait(timeout=1.0)`, pops one, runs `runAttempt`, reports; a raising `report` is logged by type name. Every entry that enters a lane is reported exactly once: run, replaced, dropped, cancelled or drained.
  - `runAttempt(master, lane, attempt) -> Outcome` (module-level; the one place vehicle I/O happens): `vehicle = master.vehicleRegistry.get(attempt.key)` (`None` → `Outcome(ERROR, "no vehicle")`); `provider = master.providerOrder.provider(attempt.provider)` (`None` → `ERROR`); `lane.note(...)`; `attempt.capability == PROBE` → return `provider.probe(vin)` at once (no read, no wake, no stamp); `hooks = master.reconciler if isinstance(getattr(master, "reconciler", None), VehicleReconciler) else None` (lazy import; a master without a reconciler takes the pass-through path); **read before write**: when `attempt.aspect` is set and `attempt.maxAge is not None`, `vehicle.read(FIELD_FOR[aspect], attempt.maxAge, allowWake=False, sources=[s for s in master.vehicleRegistry.readSources() if s.provider in lane.providers], force=attempt.force)`; then `believed = vehicle.believed(field, exclude=VEHICLE_SOURCES_EXCLUDED)`; if `satisfied(aspect, attempt.value, believed)` (imported from `Reconciler`; Task 6) → `Outcome(SATISFIED, "read")` with no command; then `value, early = hooks.beforeWrite(vehicle, attempt, provider, believed) if hooks else (attempt.value, None)` (Task 6; the charge-limit rules run here, after the read) and `early` is returned when not `None`; **wake first** when `attempt.wake` and `provider.declares(WAKE)`: `w = provider.wake(vin)`; `REFUSED` → return it; `UNREACHABLE` → return it for a non-local provider, proceed for a local one (today's BLE behaviour: a failed wake is logged and the command still goes out); then `outcome = getattr(provider, commandMethod(attempt.capability))(vin, value)` (`setAmps`/`setChargeLimit` take the value, start/stop take only `vin`); `isOutcome` false → `Outcome(ERROR, "bad return <type>")` (the contract, logged at WARNING once per provider+method); **stamp**: on `DONE` with an aspect, and on `SATISFIED` for `CHARGE_LIMIT`/`AMPS` only, when `provider.cost(capability).tier != TIER_DISRUPTIVE`: `vehicle.noteWrite(field, writtenValue(aspect, value), provider.name)` where `writtenValue` is the limit, `"Charging"`/`"Stopped"`, or the amps — the lane stamps, providers never do; a disruptive stop is never stamped (the bus resumes by itself; only an observation can satisfy it) and a `SATISFIED` start/stop leaves the state the read gave; then `hooks.afterWrite(vehicle, attempt, outcome)` when `hooks` (saves a held limit); exceptions → `Outcome(ERROR, type name)`. Runs with no lock held.
  - `class Lanes:` `__init__(self, master, report=None, clock=time.time, inline=False)` builds the three lanes (`"local"` is always inline: its providers do no I/O); `laneFor(providerName) -> Lane`; `submit(attempt) -> bool`; `allows(provider, capability, vin)`; `cancel(key) -> int`; `start()`, `drain(timeout) -> bool` (drains `cloud` and `ble`); `setReport(callback)`; `pending() -> int`; `summary() -> dict`.
- Produces (`Order.py`): `debugCommand(self, command, vin, parameters) -> bool`: `provider` = the first of `candidates(vehicle, cap, amps, localRule=False)` whose `module is not None` (a TWC target is never written from the HTTP thread, as `dispatch` never did); builds a one-shot `Attempt(key=vin, aspect=None, capability, value, provider.name, wake=False, maxAge=None, restore=False, since=time.time())` and returns `master.lanes.submit(attempt)`; `False` when no candidate; one provider per debug command, no fall-through (documented in the route's docstring); the one-shot's outcome is logged at INFO by the lane (`Debug <command> for <vin> via <provider>: <kind> <detail>`). `dispatch` is unchanged here (Task 4 teaches it outcomes; Task 10 deletes it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_lanes.py
import time
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import AMPS, CHARGE_LIMIT, CHARGING, Attempt
from TWCManager.Vehicle.Reconcile.Lanes import Lane, Lanes, runAttempt
from tests.unit.reconcile_helpers import Clock, ScriptedProvider, make_order
VIN = "5YJ3E1EA1KF000001"

def attempt(cap=C.SET_CHARGE_LIMIT, value=80, provider="TeslaBLE", aspect=CHARGE_LIMIT, wake=False, maxAge=None):
    return Attempt(VIN, aspect, cap, value, provider, wake, maxAge, False, time.time())

def setup(*providers, inline=True):
    m, o = make_order({}, *providers); m.providerOrder = o; m.vehicleRegistry.getOrCreate(VIN, "t")
    reports = []; m.lanes = Lanes(m, report=lambda a, out: reports.append((a.provider, out.kind, out.detail)), inline=inline); return m, reports

def kinds(reports): return [r[1] for r in reports]

def test_lane_membership_and_unknown_provider_goes_to_cloud():
    m, _ = setup(); assert m.lanes.laneFor("TeslaBLE").name == "ble" and m.lanes.laneFor("Gen2TWC").name == "local" and m.lanes.laneFor("Nope").name == "cloud"

def test_inline_lane_runs_reports_and_stamps_the_write():
    p = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.DONE)]); m, reports = setup(p)
    assert m.lanes.submit(attempt()) is True and kinds(reports) == [O.DONE] and p.calls == [("setChargeLimit", VIN, 80)]
    w = m.vehicleRegistry.get(VIN).lastWrite("chargeLimit"); assert (w.value, w.source) == (80, "TeslaBLE") and abs(w.at - time.time()) < 5   # wall-clock domain

def test_bad_return_and_exception_become_error_outcomes_without_a_stamp():
    p = ScriptedProvider("FleetAPI", 5, False, []); p.setChargeLimit = lambda vin, limit: "success"; m, reports = setup(p)
    m.lanes.submit(attempt(provider="FleetAPI")); assert reports[-1][1] == O.ERROR and m.vehicleRegistry.get(VIN).lastWrite("chargeLimit") is None
    def boom(vin, limit): raise RuntimeError("secret-token")
    p.setChargeLimit = boom; m.lanes.submit(attempt(provider="FleetAPI")); assert reports[-1][1] == O.ERROR

def test_wake_first_refused_aborts_and_a_failed_local_wake_still_sends():
    p = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.REFUSED, "key"), O.Outcome(O.DONE)]); m, reports = setup(p)
    m.lanes.submit(attempt(wake=True)); assert kinds(reports) == [O.REFUSED] and p.calls == [("wake", VIN, None)]
    p = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.UNREACHABLE), O.Outcome(O.DONE)]); m, reports = setup(p)
    m.lanes.submit(attempt(wake=True)); assert kinds(reports) == [O.DONE] and [x[0] for x in p.calls] == ["wake", "setChargeLimit"]
    f = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.UNREACHABLE), O.Outcome(O.DONE)]); m, reports = setup(f)
    m.lanes.submit(attempt(provider="FleetAPI", wake=True)); assert kinds(reports) == [O.UNREACHABLE] and [x[0] for x in f.calls] == ["wake"]

def test_read_before_write_satisfied_skips_the_command():
    p = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.DONE)]); m, reports = setup(p)
    m.vehicleRegistry.get(VIN).observe("chargeLimit", 80, "TeslaBLE")
    m.lanes.submit(attempt(maxAge=300)); assert kinds(reports) == [O.SATISFIED] and p.calls == []

def test_disruptive_stop_and_satisfied_start_are_not_stamped():
    g = ScriptedProvider("Gen2TWC", 0, True, [O.Outcome(O.DONE)], caps={C.STOP_CHARGING: C.Declaration(C.DISRUPTIVE)}); m, reports = setup(g)
    m.lanes.submit(attempt(C.STOP_CHARGING, False, "Gen2TWC", CHARGING)); assert kinds(reports) == [O.DONE] and m.vehicleRegistry.get(VIN).lastWrite("chargingState") is None
    b = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.SATISFIED, "complete")]); m, reports = setup(b)
    m.lanes.submit(attempt(C.START_CHARGING, True, "TeslaBLE", CHARGING)); assert m.vehicleRegistry.get(VIN).lastWrite("chargingState") is None

def test_rate_limit_per_provider_capability_and_vin(monkeypatch):
    import TWCManager.Vehicle.Reconcile.Lanes as L
    mono = Clock(); monkeypatch.setattr(L.time, "monotonic", mono)
    p = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)]); p.declarations = lambda: {C.SET_AMPS: C.Declaration(C.FLEET_COMMAND, C.RateLimit(2, 60))}
    m, _ = setup(p)
    for _ in range(2): assert m.lanes.allows(p, C.SET_AMPS, VIN); m.lanes.submit(attempt(C.SET_AMPS, 10, "FleetAPI", AMPS))
    assert not m.lanes.allows(p, C.SET_AMPS, VIN) and m.lanes.allows(p, C.SET_AMPS, "5YJ3E1EA1KF000002")
    mono.t += 61; assert m.lanes.allows(p, C.SET_AMPS, VIN)

def test_queue_coalesces_per_key_aspect_stops_first_and_is_bounded_and_reports_the_losers():
    p = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)]); m, reports = setup(p, inline=False); lane = m.lanes.laneFor("FleetAPI")
    for i in range(70): lane.submit(attempt(C.SET_AMPS, i, "FleetAPI", AMPS)._replace(key="5YJ3E1EA1KF%06d" % i))
    assert lane.pending() == Lane.MAX_PENDING and [r[2] for r in reports] == ["dropped"] * 6
    lane.submit(attempt(C.STOP_CHARGING, False, "FleetAPI", CHARGING)); assert lane.pending() == Lane.MAX_PENDING and lane._peek().capability == C.STOP_CHARGING
    lane.submit(attempt(C.SET_AMPS, 5, "FleetAPI", AMPS)); lane.submit(attempt(C.SET_AMPS, 6, "FleetAPI", AMPS))
    assert sum(1 for a in lane._entries() if a.key == VIN and a.aspect == AMPS) == 1 and reports[-1][2] == "replaced"

def test_cancel_removes_only_stops_and_reports_them():
    p = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)]); m, reports = setup(p, inline=False); lane = m.lanes.laneFor("FleetAPI")
    lane.submit(attempt(C.STOP_CHARGING, False, "FleetAPI", CHARGING)); lane.submit(attempt(C.START_CHARGING, True, "FleetAPI", CHARGING)._replace(key="5YJ3E1EA1KF000002"))
    assert m.lanes.cancel(VIN) == 1 and reports == [("FleetAPI", O.ERROR, "cancelled")] and lane.pending() == 1 and lane._peek().capability == C.START_CHARGING

def test_probe_and_one_shot_do_not_replace_each_other():
    p = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.DONE)]); m, reports = setup(p, inline=False); lane = m.lanes.laneFor("TeslaBLE")
    lane.submit(attempt("probe", None, "TeslaBLE", None)); lane.submit(attempt(C.WAKE, None, "TeslaBLE", None)); assert lane.pending() == 2

def test_drain_runs_pending_stops_only():                                  # Review Focus 5
    p = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)]); m, reports = setup(p, inline=False); lane = m.lanes.laneFor("FleetAPI")
    lane.submit(attempt(C.SET_CHARGE_LIMIT, 80, "FleetAPI", CHARGE_LIMIT)); lane.submit(attempt(C.STOP_CHARGING, False, "FleetAPI", CHARGING))
    assert m.lanes.drain(5) is True                                                        # never started: the stop runs here
    assert [c[0] for c in p.calls] == ["stopCharging"] and lane.pending() == 0 and sorted(r[2] for r in reports) == ["", "dropped"]

def test_debug_command_submits_a_one_shot_past_a_twc():
    t = ScriptedProvider("Gen2TWC", 0, True, [O.Outcome(O.DONE)], caps={C.SET_AMPS: C.Declaration(C.LOCAL)}, amps=(6, 32)); t.module = None
    p = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)]); m, reports = setup(t, p)
    assert m.providerOrder.debugCommand("setChargeRate", VIN, '{"charge_rate": "12"}') is True and p.calls == [("setAmps", VIN, 12)] and t.calls == []
    assert m.providerOrder.debugCommand("wakeVehicle", "5YJ3E1EA1KF000009", "{}") is False and reports[-1][1] == O.DONE
```
(`Lane._peek()` returns the next entry, `Lane._entries()` the pending list, both test-only snapshots under the condition.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Lanes`).

- [ ] **Step 3: Implement** per Interfaces. `runAttempt` imports `satisfied` and `VEHICLE_SOURCES_EXCLUDED` lazily from `Reconciler` (Task 6 provides them; until then `Lanes.py` carries a minimal `satisfied(aspect, desired, believed)` = `believed is not None and believed.value == desired` and an empty exclusion set that Task 6 replaces). Rewrite only the debug test in `test_provider_order.py`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_lanes.py tests/unit/test_provider_order.py tests/unit/test_registry_callers.py tests/unit/test_carapivehicle_registry.py tests/unit/test_provider_capabilities.py tests/unit/test_vehicle_priority.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Add per-channel lanes that run attempts with read-before-write, wake-first, rate limits and classified outcomes"
```

