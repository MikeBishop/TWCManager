### Task 1: Outcome vocabulary and the desired-state store

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/__init__.py`, `Outcome.py`, `Desired.py`; `tests/unit/reconcile_helpers.py`.
- Test: `tests/unit/test_outcome_desired.py`.

**Interfaces:**
- Produces (`Outcome.py`): kinds `DONE = "done"`, `SATISFIED = "satisfied"`, `UNSUPPORTED = "unsupported"`, `UNREACHABLE = "unreachable"`, `REFUSED = "refused"`, `ERROR = "error"`; `KINDS` (frozenset); `SETTLED = {DONE, SATISFIED}`, `RETRYABLE = {UNREACHABLE, ERROR}` (same provider again after `RETRY[aspect]`), `EXCLUDING = {UNSUPPORTED, REFUSED}` (provider skipped for the rest of the round; `REFUSED` additionally means the provider has retired its slot or claim). `class Outcome(NamedTuple): kind: str; detail: str = ""` (`detail` is a short reason or status code, never a body or token). `isOutcome(x) -> bool`. `LANE_DETAILS = frozenset({"cancelled", "dropped", "replaced"})`: an `ERROR` with one of these details was produced by the lane itself, not by a provider, and counts against nothing. The module docstring carries the provider return contract: every `Provider` command method (`setChargeLimit`, `startCharging`, `stopCharging`, `setAmps`, `wake`, `probe`) returns an `Outcome`, never `None`, `True`, `"success"` or a dict; a raised exception is converted by the lane to `Outcome(ERROR, <type name>)`.
- Produces (`Desired.py`):
  - Aspects: `CHARGE_LIMIT = "chargeLimit"`, `CHARGING = "charging"`, `AMPS = "amps"`; `ASPECTS`; `SLOW_ASPECTS = frozenset({CHARGE_LIMIT})` (user changes replace desired until the next decision); fast aspects become session bounds. `FIELD_FOR = {CHARGE_LIMIT: "chargeLimit", CHARGING: "chargingState", AMPS: "chargeCurrentRequest"}` (the car's own current request, Task 9; never `availableCurrent`, which is the charger's pilot); `CAPABILITY_FOR(aspect, value) -> str` (`SET_CHARGE_LIMIT`; `START_CHARGING` when value is True else `STOP_CHARGING`; `SET_AMPS`).
  - `class Desired(NamedTuple): value: Any; by: str; at: float; adopted: bool = False; restore: bool = False; lift: bool = False; forced: bool = False` (`restore`: the value is the outside limit being put back; `lift`: a raise-to-max of the car's own current limit, which ignores the local-amps rule, #660; `forced`: a stop the wiring or a controller limit requires, which a user-start bound does not override).
  - `class Attempt(NamedTuple): key: str; aspect: Optional[str]; capability: str; value: Any; provider: str; wake: bool; maxAge: Optional[float]; restore: bool; since: float; force: bool = False` (`aspect` is `None` for a probe or a one-shot debug command; `force`: the pre-write read cascades even when the stored value is fresh).
  - `class AttemptRecord:` fields `inFlight: Optional[Attempt]`, `lastOutcome: Optional[Outcome]`, `lastOutcomeAt: float`, `lastProvider: str`, `tried: Dict[str, int]` (failures per provider this round), `excluded: Set[str]`, `paid: Set[str]` (names of billed/disruptive providers tried this round; `report` adds them), `backoff: float` (0 until the first exhaustion), `backoffUntil: float`, `settledAt: Optional[float]`, `notBefore: float` (an unstamped settled outcome — a disruptive stop, a SATISFIED start/stop — may be re-planned no sooner than this, N1), `pendingSave: Any = None`; `newDesire()` (drops `tried` entries for providers not in `paid`, sets `notBefore = 0`, and clears `backoff`/`backoffUntil` only when `paid` is empty: a new value gets a prompt free attempt, while a paid provider's `tried` and backoff persist until success or a session event, as the spec's "reset on success/arrival/plug-in"); `reset()` (clears everything but `lastOutcome`/`lastOutcomeAt`/`lastProvider`); `newRound()` (clears `tried` and `excluded`; keeps `paid`, so a backed-off round still knows it was paid); `summary() -> dict`.
  - `class ChannelHealth:` per car and free provider, shared by every aspect: `lastSuccessAt: Optional[float]`, `failingSince: Optional[float]`, `lastFailureAt: Optional[float]`; `success(at)` (sets `lastSuccessAt`, clears `failingSince`), `failure(at)` (`failingSince = failingSince or at`, `lastFailureAt = at`); `failing -> bool`; `summary()`.
  - `class SessionBounds:` `maxAmps: Optional[float] = None`, `wantsCharge: bool = False`, `userStopped: bool = False`, `lifted: bool = False`; `clear()`.
  - `class ControlState:` `desired: Dict[str, Desired]`, `records: Dict[str, AttemptRecord]`, `bounds: SessionBounds`, `health: Dict[str, ChannelHealth]` (by provider name), `probeInFlight: Optional[Attempt]` (at most one BLE reachability probe per car), `lastStopProvider: Optional[str]` (the provider that delivered the last `CHARGING` False; a start goes back through it, Task 8), `offering: Optional[bool]` (`None` until the point reports; `True` when it offered at least its minimum on the last cycle; a stopped read that arrives while we offer nothing is our doing, not the user's, and no start is planned while it is `False`, Task 8), `offeringSince: float`.
  - `class DesiredStore:` `__init__(self, clock=time.time)` (the registry's clock domain: every stamp in this package is `time.time`); leaf `threading.Lock`; `set(self, key, aspect, value, by, decision=False, restore=False, lift=False, forced=False) -> bool` (returns True when desired changed — and then `record(key, aspect).newDesire()`; unchanged values touch nothing; **ignored** (False, DEBUG log) when the existing desired is `adopted` and `decision` is False; when `aspect == CHARGING`, `value is False`, `bounds.wantsCharge` and not `forced`; or when `aspect == CHARGING`, `value is True` and `bounds.userStopped`); `get(key, aspect) -> Optional[Desired]`; `clear(key, aspect) -> bool`; `release(key, aspect, value, by) -> bool` (clears desired only when it equals `(value, by)` and `not settled(key, aspect)`: a pending distributor stop that never went out); `adopt(key, aspect, value) -> None` (slow aspect: `Desired(value, "user", now, adopted=True)`; fast aspects: `CHARGING` with a value `satisfied(CHARGING, True, value)` (Task 6's rule: "Charging"/"Starting"/"Complete") → `bounds.wantsCharge = True`, a stopped-like value → `bounds.userStopped = True`, desired cleared either way; `AMPS` → `bounds.maxAmps = value` and desired cleared); `decision(key) -> None` (clears `adopted` flags: the next `set` applies); `endSession(key) -> None` (bounds cleared, adopted flags cleared, records reset, health reset, `lastStopProvider` cleared); `record(key, aspect) -> AttemptRecord`; `health(key, provider) -> ChannelHealth` (created on demand); `state(key) -> ControlState` (created on demand); `bounds(key) -> SessionBounds`; `settled(key, aspect) -> bool` (record's `settledAt >= desired.at`); `noteOffering(key, offering: bool) -> None` (the distributor or heartbeat records each cycle whether the point was offered at least its minimum: `state(key).offering`, and `state(key).offeringSince` is stamped on the None/False→True transition; adoption of a stopped-like read requires both, so a car that stopped while we offered nothing is not marked `userStopped` once we offer again); `keys() -> List[str]`; `onChange(callback) -> None` (`callback(key, aspect)`, called outside the lock after any change, for the reconciler's wake); `summary(key) -> dict` (desired per aspect, record summaries, bounds, health; Phase 6).
- Produces (`tests/unit/reconcile_helpers.py`): `class Clock` (`t`, `__call__`); `class ScriptedProvider(Provider)`: `__init__(self, name, rank, local, outcomes: List[Outcome], caps=COMMAND_CAPS, amps=(1, 32), tier=None, module=object(), readyFor=None)` whose command methods pop the next scripted outcome (last one repeats) and append `(method, vin, value)` to `self.calls`; `wake(vin)` and `probe(vin)` likewise (`("wake"|"probe", vin, None)`); `outcomes` is a public list a test may reset; `ready(vehicle, cap)` = `bool(vehicle and vehicle.vin)` and, when given, `readyFor(vehicle, cap)`; `clock = time.time` (Task 5's Fleet provider has the same attribute); `def make_order(settings=None, *providers) -> (master Mock, ProviderOrder)` as `test_provider_order.master/order` do, with `del m.reconciler` so a lane without a reconciler takes its pass-through path (a plain `Mock` would answer `beforeWrite` with a Mock).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_outcome_desired.py
import time
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import AMPS, CHARGE_LIMIT, CHARGING, DesiredStore
from tests.unit.reconcile_helpers import Clock
VIN = "5YJ3E1EA1KF000001"

def test_outcome_vocabulary():
    assert O.SETTLED | O.RETRYABLE | O.EXCLUDING == O.KINDS and O.isOutcome(O.Outcome(O.DONE)) and not O.isOutcome("done")
    assert O.Outcome(O.REFUSED, "401").detail == "401" and "cancelled" in O.LANE_DETAILS

def test_set_get_clear_and_change_signal():
    c = Clock(); s = DesiredStore(clock=c); seen = []; s.onChange(lambda key, aspect: seen.append((key, aspect)))
    assert s.set(VIN, CHARGE_LIMIT, 80, "policy") is True and s.set(VIN, CHARGE_LIMIT, 80, "policy") is False
    assert s.get(VIN, CHARGE_LIMIT).value == 80 and s.get(VIN, CHARGE_LIMIT).by == "policy" and seen == [(VIN, CHARGE_LIMIT)]
    assert s.clear(VIN, CHARGE_LIMIT) and s.get(VIN, CHARGE_LIMIT) is None

def test_default_clock_is_wall_time():
    s = DesiredStore(); before = time.time(); s.set(VIN, CHARGE_LIMIT, 80, "policy")
    assert before <= s.get(VIN, CHARGE_LIMIT).at <= time.time()

def test_adopted_slow_aspect_holds_until_a_decision():
    s = DesiredStore(); s.set(VIN, CHARGE_LIMIT, 50, "policy"); s.adopt(VIN, CHARGE_LIMIT, 80)
    assert s.get(VIN, CHARGE_LIMIT).value == 80 and s.get(VIN, CHARGE_LIMIT).adopted
    assert s.set(VIN, CHARGE_LIMIT, 50, "policy") is False and s.get(VIN, CHARGE_LIMIT).value == 80
    assert s.set(VIN, CHARGE_LIMIT, 50, "policy", decision=True) is True and s.get(VIN, CHARGE_LIMIT).value == 50

def test_fast_aspects_adopt_as_session_bounds():
    s = DesiredStore(); s.set(VIN, CHARGING, False, "distributor"); s.adopt(VIN, CHARGING, "Charging")
    assert s.get(VIN, CHARGING) is None and s.bounds(VIN).wantsCharge
    assert s.set(VIN, CHARGING, False, "distributor") is False                 # user started it: not re-stopped this session
    assert s.set(VIN, CHARGING, False, "distributor", forced=True) is True      # unless the wiring requires it
    s.set(VIN, AMPS, 32, "distributor"); s.adopt(VIN, AMPS, 16)
    assert s.bounds(VIN).maxAmps == 16 and s.get(VIN, AMPS) is None
    s.endSession(VIN); assert s.bounds(VIN).maxAmps is None and not s.bounds(VIN).wantsCharge and s.set(VIN, CHARGING, False, "distributor")

def test_adopting_a_user_stop_holds_off_starts_for_the_session():
    s = DesiredStore(); s.set(VIN, CHARGING, True, "distributor"); s.adopt(VIN, CHARGING, "Stopped")
    assert s.get(VIN, CHARGING) is None and s.bounds(VIN).userStopped and s.set(VIN, CHARGING, True, "distributor") is False
    s.endSession(VIN); assert s.set(VIN, CHARGING, True, "distributor") is True

def test_release_drops_only_an_undelivered_matching_desire():
    c = Clock(); s = DesiredStore(clock=c); s.set(VIN, CHARGING, False, "distributor")
    assert s.release(VIN, CHARGING, False, "distributor") is True and s.get(VIN, CHARGING) is None
    s.set(VIN, CHARGING, False, "distributor"); s.record(VIN, CHARGING).settledAt = c.t                 # same instant: settled
    assert s.settled(VIN, CHARGING) and s.release(VIN, CHARGING, False, "distributor") is False

def test_record_round_and_summary():
    s = DesiredStore(); r = s.record(VIN, AMPS); r.tried["TeslaBLE"] = 3; r.excluded.add("FleetAPI"); r.backoff = 600
    r.newRound(); assert r.tried == {} and r.excluded == set() and r.backoff == 600
    r.reset(); assert r.backoff == 0 and s.summary(VIN)["records"][AMPS]["backoff"] == 0 and s.keys() == [VIN]

def test_a_new_desire_resets_free_tries_and_a_free_only_backoff():
    c = Clock(); s = DesiredStore(clock=c); s.set(VIN, CHARGING, False, "distributor"); r = s.record(VIN, CHARGING)
    r.tried["TeslaBLE"] = 3; r.backoff = 600; r.backoffUntil = c.t + 600; r.notBefore = c.t + 60
    assert s.set(VIN, CHARGING, False, "distributor") is False and r.backoffUntil == c.t + 600            # unchanged: nothing reset
    assert s.set(VIN, CHARGING, True, "distributor") is True and (r.tried, r.backoff, r.backoffUntil, r.notBefore) == ({}, 0, 0, 0)
    r.tried.update({"TeslaBLE": 3, "FleetAPI": 2}); r.paid.add("FleetAPI"); r.backoff = 600; r.backoffUntil = c.t + 600
    assert s.set(VIN, CHARGING, False, "distributor") is True and r.tried == {"FleetAPI": 2} and r.backoffUntil == c.t + 600   # the paid backoff persists
    r.reset(); assert r.paid == set() and r.backoffUntil == 0
    assert s.state(VIN).offering is None; s.noteOffering(VIN, True); assert s.state(VIN).offering and s.state(VIN).offeringSince == c.t

def test_channel_health_is_per_car_and_provider_and_shared_by_aspects():
    s = DesiredStore(); h = s.health(VIN, "TeslaBLE"); assert not h.failing and h.failingSince is None
    h.failure(10.0); h.failure(70.0); assert h.failing and (h.failingSince, h.lastFailureAt) == (10.0, 70.0)
    h.success(80.0); assert not h.failing and h.lastSuccessAt == 80.0 and s.health(VIN, "TeslaBLE") is h and s.health(VIN, "FleetAPI") is not h
    h.failure(90.0); s.state(VIN).lastStopProvider = "TeslaBLE"; s.endSession(VIN)
    assert not s.health(VIN, "TeslaBLE").failing and s.state(VIN).lastStopProvider is None
```

- [ ] **Step 2: Run to verify failure** — `$PYTEST tests/unit/test_outcome_desired.py -q --timeout=60 -p no:cacheprovider` → FAIL with `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile'`.

- [ ] **Step 3: Implement `Outcome.py`, `Desired.py`, `__init__.py` and `reconcile_helpers.py`** per Interfaces. `adopt` for `CHARGING` imports `satisfied` lazily from `Reconciler` (Task 6); until then a value is "charging-like" when it is `True` or in `("Charging", "Starting", "Complete")`. `onChange` callbacks run after the lock is released; a raising callback is logged by type name and dropped.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Reconcile/ tests/unit/reconcile_helpers.py
git add lib/TWCManager/Vehicle/Reconcile tests/unit/reconcile_helpers.py tests/unit/test_outcome_desired.py
git commit -m "Add the outcome vocabulary and the per-vehicle desired-state store with attempt records, channel health and session bounds"
```

