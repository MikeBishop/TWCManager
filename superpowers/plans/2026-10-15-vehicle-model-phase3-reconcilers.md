# Vehicle Model Phase 3: Desired State and Reconcilers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decision-makers (policy, the distributor, the TWC heartbeat, arrival/departure checks, the debug page) stop issuing vehicle commands and set **desired state** per car and aspect (charge limit, charging on/off, amps); one reconciler converges known state on it through the provider order with one attempt in flight per car and aspect, classified outcomes from per-channel lanes, time-aware paid fallback, re-assert/adopt/hands-off, and layered actuators inside a charging point. `VehiclePriority`, `VehicleCommandQueue`, the three `lastChargeLimitApplied` copies, the `-1` sentinel and the per-channel dedupe flags go.

**Architecture:** A new package `lib/TWCManager/Vehicle/Reconcile/` holds the outcome vocabulary, the desired-state store (desired values, attempt records, session bounds), the held-limit store (persisted; replaces `settings["chargeLimits"]`'s `-1`), the ported charge-limit rules, lanes (BLE, cloud, local-inline) that run attempts (read-before-write, wake-first, own-write stamp) and report outcomes, and a `VehicleReconciler` thread (1 s bounded wait; Phase 4 folds it into the control tick) that plans at most one attempt per (car, aspect). Providers gain command methods that return an `Outcome`. `ChargingPoint.setTargetPower` applies the layered-actuator rule (`chargeRateControl` maps onto it). Legacy module command methods, the façade and the queue are deleted last, after every decision-maker writes desired state.

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `threading`, `requests_mock`, `pytest` (`tests/unit`).

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (sections "Desired state and reconcilers", "Order, policy and suppressions" incl. layered actuators and `chargeStopMode`, "Providers and capabilities" (disruptive stops, rate limits), "Fields and reads" (own-write stamp, feed lag), "Threading"). Roadmap: `.superpowers/plans/2026-10-13-vehicle-model-roadmap.md` (Phase 3 row). Inventory: `.superpowers/gut-inventory.md` (A5, A11, A12, A13, A14, A19, A21). Ledgers: `.superpowers/sdd/2026-10-14-vehicle-model-phase2-providers/progress.md`, `.../final-review.md`, `.superpowers/sdd/2026-10-13-vehicle-model-phase1-registry/progress.md` (every Phase 3 carry is listed under "Ledger carries" below). Port source: `git show presence/2-charge-limits:lib/TWCManager/ChargeLimitRules.py` (and `deploy/presence-3:` for the stamp helpers and `restore=` live-read rule).

**Branch:** `git switch -c vehicle-model/phase3 <Phase 2 head>` (branch `vehicle-model/phase2`, 8959380 plus the pending idle-minimum commit; take whatever `git rev-parse vehicle-model/phase2` is when Task 1 starts and record it in the ledger). Baseline at the Phase 2 head (6a6c14e): 1326 passed, 1 xfailed.

## Global Constraints

- **Threading.** Vehicle I/O (tesla-control, HTTP to Tesla/HA) runs only on a lane thread (`Lane("ble")`, `Lane("cloud")`); never on the serial thread, the reconciler thread, the policy thread, the background thread or an HTTP handler. No RS-485 I/O off the serial thread: a Gen2 stop or target is published (`stopRequested`, `_evseTargetAmps`) and `send_master_heartbeat` sends it. One clock domain: every timestamp in `Reconcile/` (desired, records, health, attempts, lane reports) is `time.time()`, the registry's clock; `time.monotonic` appears only inside `Lane`'s rate-limit window. An attempt record always reaches a reportable state: every entry a lane accepts is reported exactly once (run, replaced, dropped, cancelled or drained), so nothing stays in flight. The reconciler only compares registry values and desired state and submits attempts. The serial thread only writes desired state (dict work under the store's leaf lock). No lock is held across I/O. Lock order: `TeslaBLE._bleLock` → `master.settingsLock` → `VehicleRegistry._lock` → `Vehicle._lock` → `DesiredStore._lock` (leaf; never held while calling a provider, the registry or settings). Every loop is bounded: the reconciler does one pass per wake over a snapshot; lanes hold at most `Lane.MAX_PENDING = 64` entries; no `while True` without a wait.
- **Cost.** Fleet prices: `vehicle_data` $0.002, wake $0.02, commands $0.001; `vehicles/{vin}` and `live_status` free. A billed or disruptive provider is attempted only when no free candidate exists for the car (today's Fleet-only install; a Gen2 disruptive stop for a car TeslaBLE is not ready for), or when every free candidate has been failing for that car — on any aspect, or by a Phase 1 `bleReach` False observation — for at least `PAID_AFTER[aspect]` (`CHARGE_LIMIT` 300 s, `CHARGING` 60 s, `AMPS` 60 s) counted from the channel's first failure since its last success (`ChannelHealth.failingSince`), not from the aspect's own start; a free success clears it. Nothing paid happens unless a free check failed first: a Fleet command only after the free candidates failed as above, a Fleet wake only after the free online check (`vehicles/{vin}`) says the car is asleep. A paid provider is tried at most `attempts()` times per round, rounds backing off 600 s → 3600 s; one attempt in flight per (car, aspect), `RETRY[aspect]` between attempts on the same provider. A Fleet wake is sent only when the attempt's `wake` flag is set (limit raises and charge starts; never a restore, never a stop, never amps) and `TeslaAPI.wakeDue(vehicle)` (today's hold schedule) says so. Our own stamps never count as confirmation of a physical effect: a disruptive stop is never stamped and a `SATISFIED` start/stop leaves the read state; only an observation satisfies them. No new paid path: every task that touches TeslaAPI or HomeAssistant has a test counting `requests_mock` calls per URL.
- **Wiring.** Configured limits are the 80 % continuous derating; brief excursions are fine if the next allocator cycle rebalances, sustained overshoot is a bug. An idle Gen2 TWC is offered 0, which it treats as its hardware minimum; that minimum is never counted against the budget. `minAmpsPerTWC` governs allocation only: a point that cannot be allocated at least `minAmpsToOffer()` gets a stop. Layered actuators hold the TWC at its floor (not its max) when the car carries a sub-floor target, so overshoot is bounded to the floor.
- **No regression** for pure-Gen2 (no Vehicle modules: no desired state is ever set, the reconciler idles), BLE-only, Owner/Fleet, TeslaMate, HomeAssistant and Gen3 installs. `commandPolicy`, `chargeRateControl` (1/2/3), `chargeStopMode` (1/2/3), `providerSuppressions`, `settings["chargeLimits"]` (migrated) keep working; new keys are optional.
- **Logging** never carries a token, a response body or a BLE key; outcomes carry status codes and reason strings only; exceptions are logged by type name.
- Python 3.8 syntax floor; `black` only on files you touched; commit trailer per the session's attribution reminder.
- Every pytest run is capped:
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `PYTEST="timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest"`
  then `$PYTEST <paths> -q --timeout=60 -p no:cacheprovider`. Full suite: `$PYTEST tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`, must pass after every task.
- Tests for behaviour that crosses modules use real objects (`TWCMaster`, `TeslaAPI` with `requests_mock`, `TeslaBLE` with tesla-control patched as `tests/unit/test_teslable_pairing_status.make` does, real `Lanes(inline=True)`), never a mock that returns the success value the real method never returns (Phase 2 final-review C1).

## Review Focus

1. The user sets 80 % in the Tesla app while TWCManager holds the car at 50 %: the next vehicle read (newer than our write) is adopted, 80 becomes the outside value, nothing is sent back. Test: Task 6 `test_app_set_limit_is_adopted_and_becomes_outside`.
2. Bluetooth is down (every BLE attempt times out) on a BLE+Fleet install: no Fleet command inside 300 s (limit) / 60 s (start, stop); then exactly one; BLE keeps being retried at its own cadence and never produces a second Fleet call. Tests: Task 6 `test_fleet_waits_for_ble_to_time_out_and_is_sent_once`, `test_ble_only_install_keeps_retrying_ble_at_the_retry_cadence`, Task 8 `test_stop_falls_to_fleet_after_60s_once`.
3. Restart with `settings["chargeLimits"]` in the old shape (`(80, -1)`, `(80, 50)`, `80`, numeric-ID keys): migrated to `heldLimits`, a departure then restores 80 once. Test: Task 2 `test_legacy_charge_limits_migrate`.
4. Preconditioning: the TWC reports 10 A while desired charging is False and the car's last vehicle read says "Stopped": no re-stop, no adoption, no attempt. Test: Task 8 `test_twc_current_alone_never_adopts_charging`.
5. SIGTERM with a stop pending on the cloud lane and a limit pending on the BLE lane: the stop is delivered inside the drain, the limit is dropped, exit is not held past the timeout. Test: Task 3 `test_drain_runs_pending_stops_only`.

---

## File structure

Created:
- `lib/TWCManager/Vehicle/Reconcile/__init__.py` — re-exports.
- `lib/TWCManager/Vehicle/Reconcile/Outcome.py` — outcome vocabulary and the provider return contract.
- `lib/TWCManager/Vehicle/Reconcile/Desired.py` — aspects, `Desired`, `Attempt`, `AttemptRecord`, `SessionBounds`, `ControlState`, `DesiredStore`.
- `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py` — `HeldLimit`, `HeldLimits` (persisted, migrates `chargeLimits`).
- `lib/TWCManager/Vehicle/Reconcile/Rules.py` — `decideChargeLimit`, `needsLiveRead` (ported from `presence/2`).
- `lib/TWCManager/Vehicle/Reconcile/Lanes.py` — `Lane`, `Lanes`, `runAttempt`.
- `lib/TWCManager/Vehicle/Reconcile/Reconciler.py` — `VehicleReconciler` (plan, report, aspects, adoption, hands-off, timing).
- `lib/TWCManager/Vehicle/Reconcile/Targets.py` — `presentVehicles`, `targetsFor`, `applyPolicyLimit`, `onArrival`, `onDeparture` (the Phase 5 seam).
- Tests: `tests/unit/reconcile_helpers.py`, `test_outcome_desired.py`, `test_held_limits.py`, `test_lanes.py`, `test_provider_outcomes_local.py`, `test_provider_outcomes_cloud.py`, `test_charge_limit_rules.py` (ported), `test_limit_reconciler.py`, `test_limit_wiring.py`, `test_charging_reconciler.py`, `test_amps_reconciler.py`, `test_command_path_parity.py`.

Modified:
- `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`believed(exclude=)`, `latestFrom`, `read(sources=, force=)`), `Registry/Fields.py` and `Registry/Sources.py` (`chargeCurrentRequest`), `lib/TWCManager/Vehicle/Providers/Provider.py` (command methods return `Outcome`), `Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `Suppressions.py` (billed stops under `chargeStopMode` 2/3), `Order.py` (`debugCommand` submits to a lane; `dispatch` reads outcomes until Task 10 deletes it).
- `lib/TWCManager/Vehicle/TeslaBLE.py` (`commandOutcome`), `TeslaAPI.py` (`command`, `wakeDue`, `wakeOutcome`, 401/403/412 retire, `charge_current_request`; legacy methods deleted in Task 10), `TeslaTokenSlot.py` (412 latch, refused purposes), `HomeAssistant.py` (`_post_service`), `FleetTelemetryMQTT.py` (`ChargeCurrentRequest`).
- `lib/TWCManager/TWCMaster.py` (`desired`, `heldLimits`, `lanes`, `reconciler`, `policyLimit`, `startCarsCharging`/`stopCarsCharging`/`cancelStopCarsCharging` rewritten, queue and façade plumbing removed), `TWCManager.py` (start/stop wiring, `checkArrival`/`checkDeparture`), `TWCSlave.py` (`_queueChargeRate`, the rate raise, `stopRequested` sent on the heartbeat, `vehicleKey`/`forced` stop calls, `stopAskingToStartCharging` uses), `Policy/Policy.py` (`setPolicyLimit`), `EVSEInstance/ChargingPoint.py` (layered `setTargetPower`), `EVSEInstance/Gen2TWC.py` (`stopRequested`, `pointOwnsAmps`, `endSession`), `EVSEInstance/Gen3TWC.py` (`endSession`), `EVSEInstance/VehicleEndpoint.py` (desired amps, bounds), `Control/HTTPControl.py` (`heldLimitText`, debug route), `docs/Settings.md`, `CHANGELOG.md`.

Deleted (Task 10): `lib/TWCManager/Vehicle/VehiclePriority.py`, `lib/TWCManager/VehicleCommandQueue.py`, `tests/unit/test_vehicle_priority.py`, `test_vehicle_priority_returns.py`, `test_vehicle_command_queue.py`, `test_targeted_charge_limit.py`, `test_teslaapi_charge_vin.py`, `test_teslaapi_chargerate.py`, `test_own_write_stamps.py` (their still-valid assertions move to the new files named in Tasks 4–9).

---

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

### Task 2: Registry support (`believed`, restricted reads) and the held-limit store (removes the `-1` sentinel's storage)

`settings["chargeLimits"][ID] = (outside, lastApplied)` with `lastApplied == -1` meaning "we hold none" (`TWCMaster.getNormalChargeLimit`, `saveNormalChargeLimit`, `removeNormalChargeLimit`; keyed by VIN from BLE and by numeric API ID from TeslaAPI; `HTTPControl.heldLimitText` tries both). The new store is VIN-keyed, `held` is `None` when nothing is held, and the old key is migrated on load.

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`read(sources=, force=)`, new `believed`, `latestFrom`); `lib/TWCManager/TWCMaster.py` (`self.heldLimits = HeldLimits(self)` in `__init__`; `loadSettings` calls `self.heldLimits.load()` after the settings dict is assigned; `getNormalChargeLimit`/`saveNormalChargeLimit`/`removeNormalChargeLimit` become thin wrappers over it until Task 10 deletes them); `lib/TWCManager/Vehicle/TeslaAPI.py` `CarApiVehicle._bind` (calls `carapi.master.heldLimits.adoptLegacyId(self.ID, self.VIN)`); `lib/TWCManager/Control/HTTPControl.py` (`heldLimitText` reads `master.heldLimits.get(vehicle.vin)`, keeping today's "N% (restored)" text when `held` is `None`).
- Test: `tests/unit/test_held_limits.py`; `tests/unit/test_registry_read_cascade.py` gains the `sources=` and `force=` cases; `tests/unit/test_vehicles_page.py` held-limit assertions adjusted to the new store.

**Interfaces:**
- Produces (`Vehicle`): `latestFrom(self, field, exclude=()) -> Optional[Observation]`: the newest observation of `field` whose source is not in `exclude` (over `reportedBy` per source). `believed(self, field, exclude=()) -> Optional[Observation]`: `latestFrom(field, exclude)` when it is strictly newer than `lastWrite(field)`, else the last own write, else that observation, else `None` — the value we act on (`presence/2`'s `latestChargeLimit` rule on the registry; `exclude` lets the reconciler leave TWC-sourced observations out of a car's own state). `trusted(self, field, exclude=()) -> Optional[Observation]`: as the Phase 1 `trusted`, computed over `latestFrom(field, exclude)` (so an excluded source that wrote the field last does not hide a trusted vehicle read). `read(self, field, maxAge, allowWake=False, sources=None, force=False)`: when `sources` is given the cascade runs over `[s for s in sources if s in self._registry.readSources()]` in registry order instead of every source; `force=True` skips the freshness check and cascades even when the stored value is fresh (a live report-on-change feed makes `age()` 0, which a restore must not trust).
- Produces (`HeldLimits.py`): `class HeldLimit(NamedTuple): outside: int; held: Optional[int]`. `class HeldLimits:` `KEY = "heldLimits"`, `LEGACY_KEY = "chargeLimits"`; `__init__(self, master)`; `load(self) -> None` (under `settingsLock`: reads `settings["heldLimits"]` (`{VIN: {"outside": int, "held": int|null}}`); when absent and `chargeLimits` exists, migrates each entry: an int `n` → `HeldLimit(n, None)`; `(o, -1)`/`(o, None)`/`(o, 0)` → `HeldLimit(o, None)`; `(o, n)` with `50 <= n <= 100` → `HeldLimit(o, n)`; a well-formed VIN key goes into the store under the VIN, any other key is **persisted** under `"id:<key>"` (never memory-only: an install whose TeslaAPI does not bind the car this run keeps its held limit); then deletes `chargeLimits`, writes `heldLimits` and queues `saveSettings`; malformed entries are dropped with one WARNING per key); `get(self, vin) -> Optional[HeldLimit]`; `set(self, vin, outside, held) -> None` (under `settingsLock`, then `saveSettings`); `remove(self, vin) -> None`; `adoptLegacyId(self, legacyId, vin) -> None` (moves an `id:` entry under the VIN unless the VIN already has one, and saves); `vins() -> List[str]` and `holding() -> List[str]` (VINs with `held is not None`) return well-formed VIN keys only, never `id:` entries. All VINs upper-cased. The interim `TWCMaster` wrappers accept a numeric ID as well: they resolve it to a VIN through TeslaAPI's vehicle list when loaded, else read or write the `id:` entry.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_held_limits.py
from TWCManager.Vehicle.Reconcile.HeldLimits import HeldLimit, HeldLimits
from tests.unit.test_gen2twc_provider import make, VIN
VIN2 = "5YJ3E1EA1KF000002"

def test_legacy_charge_limits_migrate():                                   # Review Focus 3
    m, s = make(); m.settings["chargeLimits"] = {VIN: (80, -1), VIN2.lower(): [90, 50], "12345": 85, "bad": "x"}
    m.heldLimits.load()
    assert m.heldLimits.get(VIN) == HeldLimit(80, None) and m.heldLimits.get(VIN2) == HeldLimit(90, 50)
    assert "chargeLimits" not in m.settings and m.settings["heldLimits"][VIN2] == {"outside": 90, "held": 50} and m.settings["heldLimits"]["id:12345"] == {"outside": 85, "held": None}
    assert m.getNormalChargeLimit(12345) == (True, 85, -1)                                       # the interim wrapper still answers by ID
    m.heldLimits.adoptLegacyId(12345, "5YJ3E1EA1KF000003"); assert m.heldLimits.get("5YJ3E1EA1KF000003") == HeldLimit(85, None) and "id:12345" not in m.settings["heldLimits"]
    assert m.heldLimits.holding() == [VIN2]

def test_set_remove_and_wrappers_keep_working():
    m, s = make(); m.heldLimits.load(); m.heldLimits.set(VIN, 80, 50)
    assert m.getNormalChargeLimit(VIN) == (True, 80, 50)
    m.heldLimits.set(VIN, 80, None); assert m.getNormalChargeLimit(VIN) == (True, 80, -1)      # wrapper keeps the old tuple until Task 10
    m.heldLimits.remove(VIN); assert m.heldLimits.get(VIN) is None and m.getNormalChargeLimit(VIN) == (False, None, None)

def test_believed_prefers_a_newer_read_over_our_write():
    m, s = make(); v = m.vehicleRegistry.getOrCreate(VIN, "t"); c = m.vehicleRegistry._clock
    v.observe("chargeLimit", 90, "TeslaAPI"); assert v.believed("chargeLimit").value == 90
    v.noteWrite("chargeLimit", 50, "TeslaBLE"); assert v.believed("chargeLimit").value == 50          # our write is newer than the read
    v.observe("chargeLimit", 80, "TeslaMateVehicle", at=v.lastWrite("chargeLimit").at + 1); assert v.believed("chargeLimit").value == 80
    v.observe("chargingState", "Charging", "Gen2TWC", at=v.lastWrite("chargeLimit").at + 2)
    assert v.believed("chargingState", exclude={"Gen2TWC"}) is None and v.latestFrom("chargingState").source == "Gen2TWC"
```
Add to `tests/unit/test_registry_read_cascade.py`: `test_read_with_sources_skips_other_sources` (two registered sources; `read(field, 0, sources=[second])` calls only the second's `fetch`) and `test_force_reads_past_a_live_feed` (a `TeslaMateVehicle` observation with `registerLiveness` returning now: `read(field, 300)` fetches nothing, `read(field, 300, force=True)` calls the source's `fetch` once).

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `HeldLimits`; `AttributeError: believed`).

- [ ] **Step 3: Implement** per Interfaces; `heldLimitText` shows `held` as the applied limit and keeps today's "N% (restored)" wording when `held` is `None`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_held_limits.py tests/unit/test_registry_read_cascade.py tests/unit/test_registry_vehicle.py tests/unit/test_vehicles_page.py tests/unit/test_twcmaster.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Reconcile/ lib/TWCManager/Vehicle/Registry/Vehicle.py lib/TWCManager/TWCMaster.py lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager tests/unit
git commit -m "Store held charge limits by VIN without the -1 sentinel and let a vehicle report the value it believes"
```

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

### Task 4: Local provider command methods return outcomes (TeslaBLE, Gen2, Gen3)

Today `TeslaBLE.sendCommand` returns the tesla-control output or `None`; `_sendCommand_internal` sets `_keyRefusal.refused` and records a refusal through `_noteBleRefusal` → `_setBleStatus`, which drops the registry claim except inside `PAIRING_WINDOW`; `parseCommandOutput` and `_is_already_satisfied` classify output; `_scheduleBlocksStart` says the car's own schedule blocks a start; `_sendCommand_internal` calls `_noteBleProof` on any answered command. `Gen2TWCProvider.stopCharging` has no caller yet, compares the raw key (final-review M5) and, in mode 3, would call `master.sendStopCommand` (an RS-485 write) from whatever thread runs it. `ProviderOrder.dispatch` is still called by `VehiclePriority.setAmps` until Task 10 and reads success by truthiness, which an `Outcome` tuple always is.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py` (`commandOutcome`, `probe`, `_sendCommand_internal(..., noteProof=True)`), `lib/TWCManager/Vehicle/Providers/TeslaBLEProvider.py`, `Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `lib/TWCManager/Vehicle/Providers/Suppressions.py` (billed stops under `chargeStopMode` 2/3), `lib/TWCManager/Vehicle/Providers/Order.py` (`dispatch` reads outcomes), `lib/TWCManager/TWCSlave.py` (`stopRequested` sent by `send_master_heartbeat`), `lib/TWCManager/EVSEInstance/Gen2TWC.py` (`stopRequested` attribute), `tests/unit/test_teslable_provider.py` (`test_commands_call_the_module_by_vin`), `test_gen2twc_provider.py` (`test_disruptive_stop_declared_very_high_cost_and_off_by_default`, `test_set_amps_publishes_a_target_for_the_heartbeat`), `tests/unit/test_gen3twc_provider.py` (`test_provider_commands_go_to_the_unit`) — return values are outcomes now.
- Test: `tests/unit/test_provider_outcomes_local.py`; create `tests/unit/gen2_helpers.py` (the real-heartbeat driver Tasks 8 and 9 reuse).

**Interfaces:**
- Produces (`tests/unit/gen2_helpers.py`): `drive(master, slave, amps_actual, state=0x04, amps_max=0.0) -> Mock` — works on the `make()`/`setup()` masters (verified against base 6a6c14e under the capped pytest: one heartbeat per call, `iface.send` once per call): on first use it (1) completes `master.config["config"]` **and** `slave.configConfig` with `fakeMaster = 1` and `displayMilliseconds = False` (`print_status` reads them), (2) gives `master.TWCID` the bytes value `b"\x77\x77"` when it is not bytes (`make()` passes `"AB"`), (3) replaces `master.getModuleByName` with a dict lookup that answers `"Policy"` with a Mock whose `policyIsGreen()` is False (the heartbeat calls `fireWebhook` and `policyIsGreen` on it) and `"Dummy"` with a Mock interface, falling back to the previous lookup (`None` on error) for other names, and (4) wraps `master.getModulesByType` so `"Interface"` yields `[{"name": "Dummy", "ref": iface, "type": "Interface"}]`; then feeds one `receive_slave_heartbeat` with the given state/max/actual (the 7-byte layout `test_gen2_idle_minimum.heartbeat()` builds) and one `send_master_heartbeat`; returns the interface mock so a test can read the wire offer. The stubs are kept on `master._driveStubs` so repeated calls reuse them. `test_gen2_idle_minimum.py` keeps its own helpers.
- Produces (`TeslaBLE`): `commandOutcome(self, vin, command, args=None) -> Outcome`: `vin` upper-cased; `_keyRefusal.refused` after the call, or a stored BLE status of `"refused"` → `Outcome(REFUSED, "key")` — the claim is whatever `_setBleStatus` made of it (dropped outside the pairing window, kept inside it); this method never touches claims; `sendCommand` → `None` → `Outcome(UNREACHABLE, "no reply")` (timeout, circuit breaker open, binary missing, VIN not in settings); output with `_is_already_satisfied` → `Outcome(SATISFIED, <reason word>)`; `parseCommandOutput` True → `DONE`; else `Outcome(ERROR, <error category>)`. Never logs the output beyond today's DEBUG lines. `probe(self, vin) -> Outcome`: one `_sendCommand_internal(vin, "body-controller-state", noteProof=False)` (tesla-control's VCSEC query, answered while infotainment sleeps and without an authenticated session, so it never wakes the car and must not count as key proof; one shot, no `_execute_with_retry` backoff, bounded by `commandTimeout` under `_bleLock`), classified as `commandOutcome` does. `_sendCommand_internal(self, vin, command, args=None, noteProof=True)`: `noteProof=False` skips `_noteBleProof`.
- Produces (`TeslaBLEProvider`): `probe(vin)` → `ble.probe(vin)`; `setChargeLimit(vin, limit)` → `commandOutcome(vin, "charging-set-limit", int(limit))`; `startCharging(vin)` → `Outcome(SATISFIED, "scheduled")` when `ble._scheduleBlocksStart(vin)` (today: treated as done, not re-asked), else `commandOutcome(vin, "charging-start")`; `stopCharging(vin)` → `"charging-stop"`; `setAmps(vin, amps)` → `"charging-set-amps"` with `int(amps)`; `wake(vin)` → `commandOutcome(vin, "wake")`. No pre-wake inside the provider: the lane wakes when the attempt says so.
- Produces (`Gen2TWC`): `stopRequested: bool = False` (set off the serial thread, consumed on it).
- Produces (`TWCSlave.send_master_heartbeat`): at the top, `if self.stopRequested: self.stopRequested = False; self.master.sendStopCommand(self.TWCID)` — the only place a stop reaches RS-485, on the serial thread.
- Produces (`Gen2TWCProvider`): `declarations()` adds `START_CHARGING: Declaration(LOCAL)`; `ready(vehicle, START_CHARGING)` → `stopMode() == 2 and slaveFor(vehicle) and master.desired.state(vehicle.key).lastStopProvider == "Gen2TWC"` (mode 2's "start" is to answer slaves again; it undoes only a stop this provider delivered, never a BLE or cloud stop — Task 8); `startCharging(vin)` → under `settingsLock` `settings["respondToSlaves"] = 1` → `Outcome(DONE, "respond")`; `stopCharging(vin)`: no slave for the key → `Outcome(UNSUPPORTED, "no slave")`; mode 1 → `Outcome(UNSUPPORTED, "mode 1")`; mode 2 → `master.stopRespondingToSlaves()` → `Outcome(DONE, "respond")`; mode 3 → `slave.stopRequested = True` → `Outcome(DONE, "queued")` (the heartbeat sends it); `_slaveForKey` upper-cases a VIN key (M5); `setAmps(vin, amps)` → publishes the target → `Outcome(DONE)` (still never chosen for the `AMPS` aspect: Task 9).
- Produces (`Gen3TWCProvider`): `startCharging`/`stopCharging`/`setAmps` return `Outcome(DONE)`; `Outcome(UNSUPPORTED, "no unit")` when `unitFor(vehicle)` is `None`. The zero-headroom stop stays at the local tier, unverified on hardware (Phase 2 G4).
- Produces (`Suppressions.suppressed`): additionally `True` when `capability == STOP_CHARGING`, `not provider.local` and `int(settings.get("chargeStopMode", 1)) in (2, 3)` — a user who chose a disruptive local stop pays nothing for stops today and keeps paying nothing (Decision 7).
- Produces (`ProviderOrder.dispatch`): a result `r` counts as success when `isOutcome(r) and r.kind in SETTLED`, or, for a legacy non-outcome return, `r and r != "error"` as today — the façade's `setAmps` keeps working with outcome-returning providers until Task 10 deletes both.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_outcomes_local.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import DesiredStore
from tests.unit.reconcile_helpers import ScriptedProvider
from tests.unit.test_teslable_pairing_status import make, VIN
from tests.unit.test_gen2twc_provider import make as make_gen2

def test_ble_outcomes_follow_tesla_control_output():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    ble.sendCommand = Mock(return_value=None);        assert p.setChargeLimit(VIN, 80) == O.Outcome(O.UNREACHABLE, "no reply")
    ble.sendCommand = Mock(return_value="Command executed successfully"); assert p.setChargeLimit(VIN, 80).kind == O.DONE
    ble.sendCommand = Mock(return_value="Error: car could not execute command: already_set"); assert p.setChargeLimit(VIN, 80) == O.Outcome(O.SATISFIED, "already_set")
    ble.sendCommand = Mock(return_value="connection failed"); assert p.stopCharging(VIN) == O.Outcome(O.ERROR, "connection")
    assert ble.sendCommand.call_args.args == (VIN, "charging-stop")

def test_ble_key_refusal_is_refused_and_the_claim_follows_the_pairing_window():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    def refuse(vin, command, args=None): ble._keyRefusal.refused = True; ble._noteBleRefusal(vin, ble.KEY_REFUSED_TEXT); return None
    ble.sendCommand = refuse
    assert p.startCharging(VIN).kind == O.REFUSED and "TeslaBLE" not in reg.get(VIN).claims and p.ready(reg.get(VIN), C.START_CHARGING) is False
    ble._claimUnproven(v); ble._setBleStatus(VIN, "pairing", pairingSent=__import__("time").time())
    assert p.startCharging(VIN).kind == O.REFUSED and "TeslaBLE" in reg.get(VIN).claims                   # inside the window: not a refusal of the key

def test_ble_probe_is_one_non_waking_body_controller_query_that_proves_nothing():
    ble, reg, master = make(); (p,) = ble.providers(); v = reg.getOrCreate(VIN, "t"); ble._claimUnproven(v)
    ble._run_command_with_timeout = Mock(return_value=(b"", b"ok", 0)); ble.sendPrivateKey = Mock(return_value=True); ble._execute_with_retry = Mock(side_effect=AssertionError("no retry wrapper"))
    master.settings.setdefault("Vehicles", {})[VIN] = {"privKey": "k"}
    assert p.probe(VIN).kind == O.DONE and ble._run_command_with_timeout.call_args.args[0][-1] == "body-controller-state"
    assert reg.get(VIN).claims["TeslaBLE"].status == "unproven"                                           # no proof from a VCSEC answer
    ble._run_command_with_timeout = Mock(return_value=(None, None, None)); assert p.probe(VIN).kind == O.UNREACHABLE

def test_ble_schedule_block_is_satisfied_without_a_command():
    ble, reg, master = make(); (p,) = ble.providers(); ble._scheduleBlocksStart = lambda vin: True; ble.sendCommand = Mock()
    assert p.startCharging(VIN) == O.Outcome(O.SATISFIED, "scheduled") and ble.sendCommand.call_count == 0

def test_gen2_stop_and_start_outcomes_and_the_billed_stop_suppression():
    m, s = make_gen2(); m.desired = DesiredStore(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t"); s.currentVIN = VIN.lower()
    assert p.stopCharging(VIN.lower()) == O.Outcome(O.UNSUPPORTED, "mode 1") and p.ready(v, C.START_CHARGING) is False
    m.settings["chargeStopMode"] = "2"
    assert p.stopCharging(VIN).kind == O.DONE and m.settings["respondToSlaves"] == 0 and p.ready(v, C.START_CHARGING) is False   # no Gen2 stop recorded yet
    m.desired.state(VIN).lastStopProvider = "Gen2TWC"
    assert p.ready(v, C.START_CHARGING) and p.startCharging(VIN).kind == O.DONE and m.settings["respondToSlaves"] == 1
    m.desired.state(VIN).lastStopProvider = "TeslaBLE"; assert p.ready(v, C.START_CHARGING) is False      # a BLE stop is undone over BLE
    fleet = Mock(local=False, name="FleetAPI"); assert m.providerOrder.suppressions.suppressed(fleet, C.STOP_CHARGING) and not m.providerOrder.suppressions.suppressed(fleet, C.START_CHARGING)
    m.settings["chargeStopMode"] = "1"; assert not m.providerOrder.suppressions.suppressed(fleet, C.STOP_CHARGING)
    assert p.stopCharging("5YJ3E1EA1KF000009") == O.Outcome(O.UNSUPPORTED, "no slave")

def test_mode_3_stop_is_sent_by_the_heartbeat_not_the_caller():
    from tests.unit.gen2_helpers import drive
    m, s = make_gen2(); m.desired = DesiredStore(); p = m.providerOrder.provider("Gen2TWC"); s.currentVIN = VIN; m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    assert p.stopCharging(VIN) == O.Outcome(O.DONE, "queued") and s.stopRequested and m.sendStopCommand.call_count == 0
    drive(m, s, amps_actual=12.0)                                                                         # the serial thread's own heartbeat
    m.sendStopCommand.assert_called_once_with(s.TWCID); assert not s.stopRequested

def test_dispatch_reads_outcomes_until_the_facade_goes():
    m, s = make_gen2(); v = m.vehicleRegistry.getOrCreate(VIN, "t")
    a = ScriptedProvider("TeslaBLE", 2, True, [O.Outcome(O.UNREACHABLE)]); b = ScriptedProvider("FleetAPI", 5, False, [O.Outcome(O.DONE)], tier=C.FLEET_COMMAND)
    m.providerOrder.register(a); m.providerOrder.register(b)
    assert m.providerOrder.dispatch(v, C.SET_AMPS, lambda p: p.setAmps(VIN, 10), amps=10, localRule=False).kind == O.DONE and len(a.calls) == 3 and len(b.calls) == 1
```
(`send_master_heartbeat` needs an Interface module and a Policy; `drive` registers both.) Add to `test_gen3twc_provider.py`: `test_gen3_commands_return_outcomes` (`p.stopCharging(anon.key).kind == O.DONE`, unknown key → `UNSUPPORTED`).

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: setChargeLimit`).

- [ ] **Step 3: Implement** per Interfaces; adjust the Phase 2 provider tests named in Files to `.kind == O.DONE`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_outcomes_local.py tests/unit/test_teslable_provider.py tests/unit/test_gen2twc_provider.py tests/unit/test_gen3twc_provider.py tests/unit/test_provider_order.py tests/unit/test_vehicle_priority.py tests/unit/test_lanes.py tests/unit/test_gen2_idle_minimum.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/ lib/TWCManager/TWCSlave.py lib/TWCManager/EVSEInstance/Gen2TWC.py
git add lib/TWCManager tests/unit
git commit -m "Give the local providers command methods with classified outcomes; the Gen2 stop is sent by the heartbeat"
```

### Task 5: Cloud provider command methods return outcomes (Fleet, Owner, HomeAssistant); refused retires the slot (closes A21, #689)

Today `CarApiVehicle.apply_charge_limit` posts `set_charge_limit` three times on `could_not_wake_buses`, `setChargeRate` returns the raw response dict (a 401 body is truthy), `car_api_charge` and `wakeVehicle` treat 401 by refreshing once; `slotRequestFailed` clears a 401 slot and pauses a 403/410/412 slot for reads only; `TeslaTokenSlot.reportScopeRefused` only logs, so `usable("command")` stays True after a 403. `car_api_available` checks `vehicle.ready()` (the free `vehicles/{vin}` online state) before every wake; the wake hold lives there too (`firstWakeAttemptTime`, `delayNextWakeAttempt` = 30 min after a failed wake, the hour-long "please report" notice, `wakeDelayMins` before the first wake after a charge need). HA's `_call_service` returns a bool, swallows `Timeout`/`HTTPError`, logs `response.text[:200]`, and `car_api_charge` gates all cars on one 10 s timer (ledger m-2).

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (new `command`, `wakeDue`, `wakeOutcome`, `commandRefused`, `now`; `CarApiVehicle.is_awake(slot=None, now=None)`), `lib/TWCManager/Vehicle/TeslaTokenSlot.py` (412 latch, refused purposes), `lib/TWCManager/Vehicle/HomeAssistant.py` (new `_post_service`), `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `tests/unit/test_teslaapi_providers.py` (`test_fleet_commands_resolve_the_car_by_vin`), `tests/unit/test_provider_registration.py` (`test_home_assistant_provider_follows_entities`) — outcomes.
- Test: `tests/unit/test_provider_outcomes_cloud.py`.

**Interfaces:**
- Produces (`TeslaTokenSlot`): `pause(self, now=None, latch=False) -> None`: `latch=True` sets `pausedUntil = float("inf")` so the slot is not retried for reads until `setTokens`/`clear` bump `changes` (ledger "stop retrying an Owner token Tesla keeps refusing (412)"); `status()` reports `"paused": True` for it. `refusedPurposes: Set[str]` recorded by `reportScopeRefused(purpose, refused=True)` and cleared by `setTokens`/`clear`; `usable(purpose)` is `False` for a refused purpose. `TeslaAPI.slotRequestFailed` passes `latch=True` for 412 ("only available on fleetapi": a token kind Tesla will keep refusing), plain `pause()` for 403/410 as today.
- Produces (`TeslaAPI`): `command(self, vehicle, name: str, body: Optional[dict] = None) -> Outcome`: one `requests.post(slot.baseURL + "/" + VIN + "/command/" + name, json=body, timeout=10)` on `slotFor("command")` (`None` → `Outcome(REFUSED, "no command token")`); HTTP 200 with `response.result` True → `DONE`; `result` False with reason in `("already_set", "charging", "is_charging", "not_charging", "complete", "disconnected", "requested")` → `Outcome(SATISFIED, reason)`; reason `could_not_wake_buses`, `vehicle_unavailable`, or HTTP 408 → `Outcome(UNREACHABLE, reason or "408")`; HTTP 401 with "expired" and a refreshable slot → `refreshSlot` once and retry once, otherwise `commandRefused(slot, 401)` → `REFUSED`; 403 → `slot.reportScopeRefused("command", refused=True)` → `REFUSED`; 412 → `slot.pause(latch=True)` → `REFUSED`; 429 → `updateCarApiLastErrorTime(vehicle)` → `Outcome(ERROR, "429")`; other statuses, `RequestException`, JSON errors → `ERROR` with the status or type name. `commandRefused(slot, code)`: 401 → `slot.clear()` + `saveSettings` + one ERROR log (`Tesla Fleet API token was rejected (HTTP 401); removing it.`). `getCarApiRetryRemaining(vehicle)` holds → `Outcome(UNREACHABLE, "backoff")` before any request. `TeslaAPI.now = time.time` (an instance attribute: the module's one clock hook, which a test replaces instead of patching the process-wide `time.time`; `wakeDue`, `wakeOutcome` and `is_awake` default to it). `wakeDue(self, vehicle, now=None) -> bool` (`now` defaults to `self.now()`; every comparison inside uses it, so a caller may drive it with a test clock): today's hold — `False` while `now - vehicle.lastAPIAccessTime <= vehicle.delayNextWakeAttempt`, or while `wakeDelayMins * 60` has not passed since `vehicle.firstChargeNeededTime` (set on the first `wakeOutcome` call for a need), or during `getCarApiRetryRemaining`. `CarApiVehicle.is_awake(self, slot=None, now=None)` (signature change; its existing callers pass nothing): its 120 s cache (`lastVehicleAwakeTime`) is measured against `now` (default `self.carapi.now()`), so a caller on a test clock drives it. `wakeOutcome(self, vehicle, now=None) -> Outcome`: **free online check first** — `vehicle.is_awake(slot=self.slotFor("command"), now=now)` (`GET vehicles/{vin}`, free; cached 120 s) → online → `Outcome(SATISFIED, "online")` with no `wake_up` posted and the counters reset; then not due → `Outcome(UNREACHABLE, "wake held")`; then posts `wake_up` (timeout 10); state `online` → `DONE` and the counters reset as `car_api_available` resets them, plus the 5 s settle sleep; `asleep`/`waking`/`offline` → `delayNextWakeAttempt = 1800`, `firstWakeAttemptTime` set, → `UNREACHABLE`; the hour-long failure INFO stays; 401/403/412/429 as for `command`.
- Produces (`FleetAPIProvider`): `_car(vin)` → `carapi.getVehicleByVIN(vin)` (`None` → `Outcome(UNSUPPORTED, "not listed")`); `clock = time.time` (an attribute a test may replace; passed as `now=` to `wakeOutcome`/`wakeDue`); `setChargeLimit(vin, limit)` → `command(car, "set_charge_limit", {"percent": int(limit)})`; `startCharging` → `"charge_start"`, except that a `disconnected` reason on a start is `Outcome(UNSUPPORTED, "disconnected")` (nothing to start; the lane must not record a start); `stopCharging` → `"charge_stop"`; `setAmps(vin, amps)` → `"set_charging_amps"` `{"charging_amps": int(amps)}`, and for `amps < 5` a second identical post 5 s later (TeslaPy #42; both must be `DONE`/`SATISFIED`); `wake(vin)` → `wakeOutcome(car, now=self.clock())`. `OwnerAPIProvider` declares no commands; its inherited defaults return `UNSUPPORTED`.
- Produces (`HomeAssistant`): `_post_service(self, domain, service, data) -> Outcome` (the one place the REST call is made, under `_rest_lock`): `200` → `DONE`; `Timeout` → `UNREACHABLE`; `HTTPError` 401/403 → `Outcome(REFUSED, str(status))` (logged once at ERROR: `Home Assistant refused a service call (HTTP <code>); check the long-lived token`); other `HTTPError` → `ERROR` with the status; other exceptions → `ERROR` by type name. Nothing here logs `response.text` (today's `[:200]` body log goes). `_call_service(domain, service, data) -> bool` becomes `self._post_service(...).kind == DONE` for its remaining legacy callers.
- Produces (`HomeAssistantProvider`): `_entity(vin, kind) -> Tuple[Optional[HaVehicle], Optional[str]]`; `setChargeLimit(vin, limit)` → `number.set_value` on `charge_limit_number`; `startCharging`/`stopCharging` → `switch.turn_on`/`turn_off` on `charge_switch`; `setAmps(vin, amps)` → `number.set_value` on `charge_current_number` with `amps` clamped to `[1, 32]` as today — all through `ha._post_service`; a missing entity → `Outcome(UNSUPPORTED, "no <kind> entity")`; `declarations()` add `RateLimit(1, 10)` on `START_CHARGING`/`STOP_CHARGING` (today's 10 s gate, now per car through the lane; closes ledger m-2); no `wake`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_outcomes_cloud.py
import re
from unittest.mock import Mock
import requests_mock as rm
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from tests.unit.test_carapivehicle_registry import api_with_registry, VIN
from tests.unit.teslatokens import fleet_token, owner_token
from tests.unit.test_homeassistant_registry import make_ha

def fleet(requests_mock, status=200, result=True, reason=""):
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); api.storeToken(fleet_token())
    requests_mock.post(re.compile(r".*/command/.*"), status_code=status, json={"response": {"result": result, "reason": reason}})
    return api, reg, api.providers()[1]

def calls(requests_mock, part): return [r for r in requests_mock.request_history if part in r.url]

def test_fleet_command_outcomes_and_one_request_each(requests_mock):
    api, reg, p = fleet(requests_mock); assert p.setChargeLimit(VIN, 80).kind == O.DONE and len(calls(requests_mock, "set_charge_limit")) == 1
    assert calls(requests_mock, "set_charge_limit")[0].json() == {"percent": 80}
    api, reg, p = fleet(requests_mock, result=False, reason="already_set"); assert p.setChargeLimit(VIN, 80) == O.Outcome(O.SATISFIED, "already_set")
    api, reg, p = fleet(requests_mock, result=False, reason="could_not_wake_buses"); assert p.startCharging(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "charge_start")) == 1
    api, reg, p = fleet(requests_mock, status=500); assert p.stopCharging(VIN) == O.Outcome(O.ERROR, "500")
    assert p.setChargeLimit("5YJ3E1EA1KF000009", 80) == O.Outcome(O.UNSUPPORTED, "not listed")

def test_fleet_401_retires_the_slot_and_403_refuses_the_scope(requests_mock):
    api, reg, p = fleet(requests_mock, status=401); assert p.setAmps(VIN, 10).kind == O.REFUSED
    assert api.fleetSlot.empty() and p.ready(reg.get(VIN), C.SET_AMPS) is False and len(calls(requests_mock, "set_charging_amps")) == 1
    api, reg, p = fleet(requests_mock, status=403); assert p.setAmps(VIN, 10).kind == O.REFUSED and not api.fleetSlot.usable("command") and api.fleetSlot.usable("read")
    assert p.ready(reg.get(VIN), C.SET_AMPS) is False; api.storeToken(fleet_token()); assert api.fleetSlot.usable("command")     # a new token clears the refusal

def test_start_on_a_disconnected_car_is_unsupported(requests_mock):
    api, reg, p = fleet(requests_mock, result=False, reason="disconnected"); assert p.startCharging(VIN) == O.Outcome(O.UNSUPPORTED, "disconnected")

def test_owner_412_is_latched_until_the_token_changes(requests_mock):
    api, reg = api_with_registry(); api.storeToken(owner_token())
    requests_mock.get(re.compile(r".*/api/1/(vehicles|products).*"), status_code=412, json={})
    assert api.loadVehicleList() is False and api.ownerSlot.usable("read") is False
    api.ownerSlot.pausedUntil -= 7200; assert api.ownerSlot.usable("read") is False             # an hour later: still paused
    api.storeToken(owner_token()); assert api.ownerSlot.usable("read") is True

def test_low_amps_are_sent_twice_and_counted(requests_mock, monkeypatch):
    import TWCManager.Vehicle.TeslaAPI as T
    api, reg, p = fleet(requests_mock); api.master.config = {"config": {}}; monkeypatch.setattr(T.time, "sleep", Mock())
    assert p.setAmps(VIN, 4).kind == O.DONE and len(calls(requests_mock, "set_charging_amps")) == 2
    assert p.setAmps(VIN, 10).kind == O.DONE and len(calls(requests_mock, "set_charging_amps")) == 3

def test_wake_checks_the_free_online_state_first_and_holds_between_wakes(requests_mock, monkeypatch):
    import TWCManager.Vehicle.TeslaAPI as T
    from tests.unit.reconcile_helpers import Clock
    clk = Clock(1000.0); api, reg, p = fleet(requests_mock); car = api.getCarApiVehicles()[0]; p.clock = clk
    monkeypatch.setattr(T.time, "sleep", Mock()); api.now = clk                                                    # TeslaAPI's own clock hook follows the test clock; time.time itself is untouched
    requests_mock.get(re.compile(r".*/api/1/vehicles/%s$" % VIN), json={"response": {"state": "online"}})
    assert p.wake(VIN) == O.Outcome(O.SATISFIED, "online") and calls(requests_mock, "wake_up") == [] and len(calls(requests_mock, "/vehicles/" + VIN)) == 1   # free check, no $0.02
    assert p.wake(VIN) == O.Outcome(O.SATISFIED, "online") and len(calls(requests_mock, "/vehicles/" + VIN)) == 1   # 120 s cache: not even the free call
    clk.t += 121; requests_mock.get(re.compile(r".*/api/1/vehicles/%s$" % VIN), json={"response": {"state": "asleep"}})
    requests_mock.post(re.compile(r".*/wake_up$"), json={"response": {"state": "asleep"}})
    car.delayNextWakeAttempt = 1800; car.lastAPIAccessTime = clk()
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake held") and calls(requests_mock, "wake_up") == [] and len(calls(requests_mock, "/vehicles/" + VIN)) == 2
    car.delayNextWakeAttempt = 0; api.wakeDelayMins = 0
    assert p.wake(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "wake_up")) == 1 and car.delayNextWakeAttempt == 1800
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake held") and len(calls(requests_mock, "wake_up")) == 1   # not twice
    clk.t += 1801; assert p.wake(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "wake_up")) == 2        # the hold expired on the same clock

def test_ha_outcomes_and_per_car_rate_limit():
    ha, reg = make_ha(); (p,) = ha.providers(); v = reg.getOrCreate(VIN, "t")
    hv = Mock(entity_ids={"charge_switch": "switch.c", "charge_limit_number": None, "charge_current_number": "number.a"}, has_charge_switch=True, has_charge_limit_number=False, has_charge_current_number=True)
    v.attach("HomeAssistant", hv); ha._post_service = Mock(return_value=O.Outcome(O.DONE))
    assert p.stopCharging(VIN).kind == O.DONE and ha._post_service.call_args.args == ("switch", "turn_off", {"entity_id": "switch.c"})
    assert p.setChargeLimit(VIN, 80) == O.Outcome(O.UNSUPPORTED, "no charge_limit_number entity")
    assert p.setAmps(VIN, 40).kind == O.DONE and ha._post_service.call_args.args[2]["value"] == 32.0
    assert p.declarations()[C.STOP_CHARGING].rateLimit == C.RateLimit(1, 10) and not p.declares(C.WAKE)
    ha._post_service = ha.__class__._post_service.__get__(ha); import requests
    ha._session.post = Mock(side_effect=requests.exceptions.Timeout()); assert p.startCharging(VIN).kind == O.UNREACHABLE
    resp = Mock(status_code=403, text="secret-token"); ha._session.post = Mock(return_value=resp); resp.raise_for_status = Mock(side_effect=requests.exceptions.HTTPError(response=resp))
    assert p.startCharging(VIN) == O.Outcome(O.REFUSED, "403") and ha._call_service("switch", "turn_on", {}) is False
```
(`test_homeassistant_registry.make_ha` gives a real `HomeAssistant` with a mock session; if `_session` is named differently there, use that name. `fleet()` resets `requests_mock` matchers per call; keep `api.master.config["config"]` present as `api_with_registry` builds it.)

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TeslaAPI' object has no attribute 'command'`).

- [ ] **Step 3: Implement** per Interfaces. The legacy methods stay untouched until Task 10; `command` is new code beside them.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_outcomes_cloud.py tests/unit/test_teslaapi_providers.py tests/unit/test_provider_registration.py tests/unit/test_teslaapi_token_slots.py tests/unit/test_teslatokenslot.py tests/unit/test_teslaapi_request_errors.py tests/unit/test_homeassistant_registry.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Give the cloud providers command methods with classified outcomes; a refused Fleet command retires its slot"
```

### Task 6: Charge-limit rules (ported) and the reconciler engine with the charge-limit aspect

The engine is generic over aspects; this task lands it with `CHARGE_LIMIT` only and drives it with scripted providers on inline lanes. Tasks 7 and 8 add the other two aspects and the real decision-makers.

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Rules.py`, `lib/TWCManager/Vehicle/Reconcile/Reconciler.py`.
- Modify: `lib/TWCManager/Vehicle/Reconcile/Lanes.py` (`runAttempt` imports `satisfied`/`VEHICLE_SOURCES_EXCLUDED` from `Reconciler`; the placeholders go), `lib/TWCManager/Vehicle/Reconcile/Desired.py` (`adopt` imports `satisfied`).
- Test: `tests/unit/test_charge_limit_rules.py` (ported from `presence/2-charge-limits:tests/unit/test_charge_limit_rules.py`, reshaped to the new record), `tests/unit/test_limit_reconciler.py`.

**Interfaces:**
- Produces (`Rules.py`): `class ChargeLimitDecision(NamedTuple): send: Optional[int]; saveNow: Optional[HeldLimit]; saveOnSuccess: Optional[HeldLimit]; settled: bool; reason: str`. `decideChargeLimit(desired: int, restore: bool, current: Optional[int], held: Optional[HeldLimit], sendWhenUnknown: bool) -> ChargeLimitDecision` — `presence/2`'s rules **verbatim**, with `(hasSaved, outside, lastApplied)` mapped as `held is None` ⇔ `not hasSaved`, `held.held is None` ⇔ `lastApplied == -1`, `held.outside` ⇔ `outside`, and `limit == -1` ⇔ `restore` (then `desired == held.outside`); every `(outside, -1)` the original saves becomes `HeldLimit(outside, None)`; the branch order (unknown-current first, then "nothing saved to restore", then the known-current rules) and every reason string are the original's. `needsLiveRead(restore: bool, current: Optional[int], held) -> bool` → `restore and current is not None and held is not None and held.held is not None and current != held.held`.
- Produces (`Reconciler.py`):
  - Constants: `TICK = 1.0`; `PAID_AFTER = {CHARGE_LIMIT: 300.0, CHARGING: 60.0, AMPS: 60.0}`; `RETRY = {CHARGE_LIMIT: 300.0, CHARGING: 60.0, AMPS: 60.0}` (`CarApiVehicle.lastLimitAttemptTime`'s 300 s and the 60 s start/stop gate today); `BACKOFF_START = 600.0`, `BACKOFF_MAX = 3600.0` (today's restore schedule); `PROBE_AFTER = 600.0` (when BLE is marked failing but its last attempt for this car is older than this, one non-waking probe runs before going paid; twice the longest `PAID_AFTER`, so an aspect reaching its own window never probes first, while a channel nobody has tried for ten minutes gets one ping before money is spent); `READ_MAX_AGE = 300.0` (`CarApiVehicle.READ_MAX_AGE`); `LIMIT_THEN_START_GAP = 5.0`; `VEHICLE_SOURCES_EXCLUDED = frozenset({"TWC", "Gen2TWC", "Gen3TWC"})` (observations that never adopt and never stand for the car's own state); `POWER_FLOWING_AMPS = 1.0`.
  - `satisfied(aspect, desired, believed: Optional[Observation]) -> bool` (module-level; the lane and `DesiredStore.adopt` use it too): `CHARGE_LIMIT`: `believed.value == desired`; `CHARGING`: desired True → `value in ("Charging", "Starting", "Complete")`, desired False → `value in ("Stopped", "Complete", "Disconnected", "NoPower")`; `AMPS`: `int(believed.value) == int(desired)`; `None` believed → False.
  - `known(vehicle, aspect) -> Optional[Observation]` = `vehicle.believed(FIELD_FOR[aspect], exclude=VEHICLE_SOURCES_EXCLUDED)` — plus, for `CHARGING` only, when that is `None` (a car no vehicle source has ever described: anonymous, non-Tesla, unclaimed), a TWC-sourced `actualCurrent` observation stands in as `"Charging"` when `>= POWER_FLOWING_AMPS` and `"Stopped"` otherwise (so a disruptive stop is satisfied by the bus going quiet and re-asserted when it resumes; such a stand-in never adopts).
  - `handsOff(aspect, desired, known) -> Optional[str]`: `CHARGING` True with known in `("Disconnected", "NoPower")` → a reason (car cannot or will not charge; nothing to send); otherwise `None`.
  - `allowWake(aspect, desired: Desired, known) -> bool`: `CHARGE_LIMIT`: `known is not None and desired.value > known.value and not desired.restore` (a raise, never to lower (#698), never when unknown; a restore never wakes — today's departure restore waits for the car, and a vanished car backs off to hourly without a wake, as the spec requires); `CHARGING`: `desired.value is True`; `AMPS`: `True`. The attempt's flag is `allowWake(...) and (p.local or aspect != AMPS)`: a billed provider wakes only for a limit raise or a start.
  - `class VehicleReconciler(threading.Thread):` `__init__(self, master, clock=time.time)` (one clock domain with the registry, the store and the lanes; daemon, name `"VehicleReconciler"`; registers `master.desired.onChange(self.wake)` and `master.lanes.setReport(self.report)`); `wake(*args)`; `stop()`; `run()`: `while not self._stopping: self._event.wait(TICK); self._event.clear(); self.pass_()` with the pass wrapped so an exception is logged by type name and never kills the thread.
  - `pass_(self, now=None) -> int` (attempts submitted): snapshot `desired.keys()`; for each key: `vehicle = registry.get(key)` (`None` → `desired.endSession(key)` and skip); **session end** when, since the last pass, the vehicle's `value("twcVin")` went from set to `None`, or a vehicle-sourced `pluggedIn` observation went from True to False → `desired.endSession(key)` (`heldLimits` untouched; the TWC and Gen3 endpoints also call `endSession` directly for their `vehicleKey` when their plug session ends, Task 8); fold `bleReach` into health (below); then plan every aspect with a desired value first (`self.plan(vehicle, aspect, now)` in `ASPECTS` order, so a probe or a limit attempt planned for one aspect is seen by the next) and submit the planned attempts afterwards (an inline lane reports before `submit` returns, so planning and submitting are kept apart).
  - `plan(self, vehicle, aspect, now) -> Optional[Attempt]` — the one algorithm in this phase the signatures do not determine:
    1. `d = desired.get(key, aspect)`, `rec = desired.record(key, aspect)`; `None` desired or `rec.inFlight` → `None`. **Settled gate**: when `desired.settled(key, aspect)` holds, return `None` unless new evidence has arrived since `rec.settledAt` — an observation of `FIELD_FOR[aspect]` from a source not in `VEHICLE_SOURCES_EXCLUDED` with `at > rec.settledAt`, or, **only when `known(vehicle, CHARGING)` is using the TWC stand-in** (no vehicle source has ever described the car), an `actualCurrent` observation newer than `settledAt` — and `now >= rec.notBefore`. For a car a vehicle source describes, the heartbeat's readings are never evidence (they arrive every second). A desired change or a session event resets the record, so those re-plan by themselves; an outcome that settled without a stamp (a disruptive stop, a SATISFIED start/stop) is therefore re-sent only on a newer reading and never inside `RETRY[aspect]` of the last one.
    2. `field = FIELD_FOR[aspect]`; `k = known(vehicle, aspect)`; `latest = vehicle.believed(field, exclude=VEHICLE_SOURCES_EXCLUDED)` restricted to observations (`vehicle.latestFrom(field, exclude=...)`, Task 2); `write = vehicle.lastWrite(field)`.
    3. **Adopt**: `latest` not None, `write` not None, `latest.at > max(write.at, d.at)`, `vehicle.trusted(field, exclude=VEHICLE_SOURCES_EXCLUDED) is latest`, and the read disagrees with the write **in the stamp's domain**: for `CHARGE_LIMIT`/`AMPS` `latest.value != write.value`; for `CHARGING` `satisfied(CHARGING, True, latest) != satisfied(CHARGING, True, write)` (both the stamp "Charging"/"Stopped" and the read are mapped to charging-like before comparing) → `self.adopt(vehicle, aspect, latest.value)` → `None` (a vehicle read newer than both our write and the current desire, disagreeing with what we wrote, is the user's change; a read that merely confirms our write never adopts, whatever desired has become). For `CHARGE_LIMIT` adoption also saves `heldLimits.set(vin, outside=latest.value, held=None)`. Two `CHARGING` exceptions are **hands off**, not adoption: a charging-like read after our own disruptive stop (`state.lastStopProvider == "Gen2TWC"`: the bus resumed by itself), and a stopped-like read while `not state.offering` or `latest.at < state.offeringSince` (the point offered nothing when the car stopped — Track Green Energy dropped the offer — so the car stopping is our doing; INFO once; once we offer again the old stopped read is stale and the start is re-asserted).
    4. `satisfied(aspect, d.value, k)` → `rec.reset(); rec.settledAt = now` → `None`. 4b. `CHARGE_LIMIT` restore with `heldLimits.get(vin)` `None` or `.held is None` → nothing to restore: `desired.clear(key, aspect)`, `rec.reset()` → `None` (no attempt, no loop).
    5. `handsOff(...)` → log once per (key, aspect, reason) at INFO → `None`. 5b. `CHARGING` True while `desired.state(key).offering is False` (the point reported that it offers nothing: Track Green Energy at 0, a budget shortfall) → `None` (DEBUG once): a start is never sent, and no wake, while the car has nothing to draw — today the heartbeat asks for a start only while it offers at least the minimum. `None` (never reported) does not block.
    6. `now < rec.backoffUntil` → `None`.
    7. `capability = CAPABILITY_FOR(aspect, d.value)`; `cands = order.candidates(vehicle, capability, amps=d.value if aspect == AMPS else None, localRule=(aspect == AMPS and not d.lift))`; drop `p.name in rec.excluded`; drop module-less providers for `AMPS` (the TWC target is the distributor's); drop providers with `NO_INDIVIDUAL_STOP in p.limitations(vehicle)` when `capability == STOP_CHARGING`; drop providers `not master.lanes.allows(p, capability, vin)`; keep order. No candidates → DEBUG once per (key, aspect) → `None` (an observed-tier or pure-Gen2 car: nothing to deliver, nothing to log at INFO).
    8. `free = [p for p in cands if p.cost(capability).tier < TIER_BILLED]`; `h(p) = desired.health(key, p.name)`; **paid eligible** = `not free` or every `p in free` has `h(p).failing and now - h(p).failingSince >= PAID_AFTER[aspect]` (the channel has failed this car on every attempt, whatever the aspect, since `failingSince`). Eligibility of a single `p`: `rec.tried.get(p.name, 0) < p.attempts()` and (`tried == 0` or `now - rec.lastOutcomeAt >= RETRY[aspect]`); a free provider stays eligible on these terms whether or not its health is failing (it is retried at the aspect's cadence, bounded by `attempts()` and the backoff below — the probe and health only decide when money may be spent). **Stale-failure probe**: when a paid/disruptive candidate is eligible now, `TeslaBLE` is in `cands`, `h(TeslaBLE).failing` and `now - h(TeslaBLE).lastFailureAt >= PROBE_AFTER` (with no paid candidate the free retry itself is the probe, so none is added): if `state.probeInFlight` → `None` (every aspect due now shares that probe); else return `Attempt(key, None, PROBE, None, "TeslaBLE", wake=False, maxAge=None, restore=False, since=now)` with `state.probeInFlight = attempt` (one per car). **Pick** (first match in this order): when paid eligible, the first eligible paid/disruptive `p` in `cands` order (the paid pick takes the aspect's one in-flight slot; a free retry continues only on passes where no paid attempt is due); otherwise the first eligible free `p`.
    9. No pick and every candidate exhausted (`tried >= attempts()` for all, or a free provider with `tried >= attempts()` and no paid candidate) → `rec.backoff = min(BACKOFF_MAX, rec.backoff * 2 or BACKOFF_START)`; `rec.backoffUntil = now + rec.backoff`; `rec.newRound()`; INFO once (`<vin> <aspect>: no provider could deliver; next try in N s`) → `None`. No pick otherwise → `None` (waiting on a timer).
    10. `CHARGE_LIMIT`: `force = needsLiveRead(d.restore, k.value if k else None, heldLimits.get(vin))` (telemetry showing a limit that is not ours cannot settle a restore: the lane reads the car even though the feed is live), `maxAge = READ_MAX_AGE`; the rules themselves run on the lane after its read (`beforeWrite`), so a cloud-only car with no known limit gets its read first, as `update_charge()` gave it today. `AMPS`: `maxAge = None` (stamp-based; today's `setChargeRate` reads nothing, and a Fleet `vehicle_data` before every rate would be a new paid read). `CHARGING`: `maxAge = READ_MAX_AGE`.
    11. `CHARGING` True while a `CHARGE_LIMIT` attempt for the car is in flight or planned in this pass, or within `LIMIT_THEN_START_GAP` of a `chargeLimit` own write → `None` (today's 5 s sleep after a limit before a start; a limit always goes first).
    12. Build `Attempt(key, aspect, capability, value, p.name, wake=allowWake(aspect, d, k) and (p.local or aspect != AMPS), maxAge, restore=d.restore, since=now, force=force)`; `rec.inFlight = attempt` → return it.
  - `beforeWrite(self, vehicle, attempt, provider, believed) -> Tuple[Any, Optional[Outcome]]` (lane thread, after the read): `CHARGE_LIMIT` → `decision = decideChargeLimit(attempt.value, attempt.restore, believed.value if believed else None, heldLimits.get(vin), sendWhenUnknown=provider.local)`; `decision.saveNow` → `heldLimits.set(...)`; `decision.settled` → **reconcile the desire so the pass cannot loop**: a restore → `desired.clear(key, CHARGE_LIMIT)`; an apply settles only as "already at N%", which the next pass's `satisfied` check ends by itself, so the desire is left as it is (not adopted: `limitOverride`'s later lowering must still apply) — then `(None, Outcome(SATISFIED, decision.reason))`; `decision.send is None` → `(None, Outcome(UNREACHABLE, decision.reason))` (the car's limit could not be read: retry, wake per the rules); else `(decision.send, None)` and `decision.saveOnSuccess` is kept on the record as `pendingSave`; other aspects → `(attempt.value, None)`. `afterWrite(self, vehicle, attempt, outcome)`: `CHARGE_LIMIT` and `outcome.kind in SETTLED` and a `pendingSave` → `heldLimits.set(*pendingSave)`; `CHARGING` False and `outcome.kind in SETTLED` → `state.lastStopProvider = provider.name`; `AMPS` lift and `SETTLED` → `bounds.lifted = True`.
  - `report(self, attempt, outcome)` (lane thread; dict work under the store lock, then `wake()`), in this order: (a) `attempt.capability == PROBE` → clear `state.probeInFlight`; `SETTLED` → `health(key, "TeslaBLE").success(now)` (the next pass sends the attempt over BLE); anything else → `.failure(now)` (the next pass goes paid at once: `lastFailureAt` is fresh, so no second probe); return. (b) `outcome.detail in LANE_DETAILS` (cancelled, dropped, replaced) → `rec.inFlight = None` **only when `rec.inFlight is attempt`** (a late report for an older entry never clears a newer attempt; `probeInFlight` likewise) and nothing else (no health, no `tried`): the attempt never ran. (c) one-shot (`aspect is None`) → INFO only. (d) otherwise (`rec.inFlight is attempt` again; a stale report is logged at DEBUG and ignored) `rec.inFlight = None`, `lastOutcome/At/Provider`, and `rec.paid.add(p)` when the provider's tier is billed or disruptive; `SETTLED` → `rec.reset()`, `settledAt = now`, and when the outcome left no stamp (`provider.cost(capability).tier == TIER_DISRUPTIVE`, or `SATISFIED` on `CHARGING`) `rec.notBefore = now + RETRY[aspect]`; `RETRYABLE` → `rec.tried[p] += 1`; `EXCLUDING` → `rec.excluded.add(p)`; then, for a free provider only, `health(key, p).success(now)` on `SETTLED` and `.failure(now)` on `RETRYABLE`/`REFUSED` — every aspect feeds the one per-car channel record. `pass_()` also folds the Phase 1 range scan in: a `bleReach` observation newer than the health's last stamp is `success(obs.at)` when True and `failure(obs.at)` when False, on the `TeslaBLE` health (same `time.time` domain as every other stamp here).
  - `adopt(self, vehicle, aspect, value)`: `desired.adopt(key, aspect, value)`, INFO `"<vin> <aspect> set elsewhere to <value>; adopted"`.
  - `summary(key) -> dict` → `desired.summary(key)` plus `heldLimits.get(vin)` (Phase 6).

- [ ] **Step 1: Write the failing tests**

Port `presence/2`'s `test_charge_limit_rules.py` (`test_rules` parametrised table, `test_invariants`, `test_reasons`, `test_needs_live_read`) with each `(hasSaved, outside, lastApplied)` row rewritten as `None` / `HeldLimit(outside, None)` / `HeldLimit(outside, n)` and each `limit=-1` row as `restore=True, desired=outside`; the expected `saveNow`/`saveOnSuccess` become `HeldLimit`s with `-1` → `None`; no row is dropped or changed otherwise. Then:

```python
# tests/unit/test_limit_reconciler.py
import time
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import CHARGE_LIMIT, CHARGING, DesiredStore
from TWCManager.Vehicle.Reconcile.HeldLimits import HeldLimit
from TWCManager.Vehicle.Reconcile.Lanes import Lanes
from TWCManager.Vehicle.Reconcile.Reconciler import VehicleReconciler, PAID_AFTER, RETRY, BACKOFF_START, LIMIT_THEN_START_GAP
from tests.unit.reconcile_helpers import Clock, ScriptedProvider
from tests.unit.test_gen2twc_provider import make as make_master, VIN

def setup(*providers, clock=True):
    m, s = make_master(); c = Clock(1000.0) if clock else time.time
    if clock: m.vehicleRegistry._clock = c
    for p in providers: m.providerOrder.register(p)
    m.desired = DesiredStore(clock=c); m.lanes = Lanes(m, clock=c, inline=True); m.heldLimits.load()
    r = VehicleReconciler(m, clock=c); v = m.vehicleRegistry.getOrCreate(VIN, "t"); return m, r, v, c

def ble(*outs): return ScriptedProvider("TeslaBLE", 2, True, list(outs))
def fleet(*outs): return ScriptedProvider("FleetAPI", 5, False, list(outs), tier=C.FLEET_COMMAND)
def cmds(p): return [x[0] for x in p.calls if x[0] != "wake"]

def test_limit_is_sent_once_and_recorded_as_held():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    assert r.pass_() == 1 and m.providerOrder.provider("TeslaBLE").calls == [("setChargeLimit", VIN, 50)]
    assert m.heldLimits.get(VIN) == HeldLimit(90, 50) and v.believed("chargeLimit").value == 50
    assert r.pass_() == 0 and m.desired.settled(VIN, CHARGE_LIMIT)                            # satisfied by our own write

def test_default_clocks_share_one_domain():                                  # production clocks, no fake
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE)), clock=False); v.observe("chargeLimit", 50, "TeslaBLE"); v.observe("chargingState", "Stopped", "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy"); m.desired.set(VIN, CHARGING, True, "distributor")
    assert r.pass_() == 1 and m.desired.settled(VIN, CHARGE_LIMIT) and m.desired.get(VIN, CHARGING) is not None
    assert r.pass_() == 0                                                     # inside the 5 s start gap, measured on one clock
    w = v.lastWrite("chargeLimit"); assert abs(w.at - time.time()) < 5 and abs(m.desired.record(VIN, CHARGE_LIMIT).settledAt - w.at) < 5

def test_app_set_limit_is_adopted_and_becomes_outside():                     # Review Focus 1
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_()
    c.t += 10; v.observe("chargeLimit", 80, "TeslaMateVehicle")
    assert r.pass_() == 0 and m.desired.get(VIN, CHARGE_LIMIT).value == 80 and m.desired.get(VIN, CHARGE_LIMIT).adopted
    assert m.heldLimits.get(VIN) == HeldLimit(80, None) and len(m.providerOrder.provider("TeslaBLE").calls) == 1
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); assert r.pass_() == 0                     # not undone until a decision
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy", decision=True); assert r.pass_() == 1

def test_a_confirming_read_is_not_adopted_when_desired_changes():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_()
    c.t += 10; v.observe("chargeLimit", 50, "TeslaMateVehicle")                                 # the car confirms our 50
    c.t += 10; m.desired.set(VIN, CHARGE_LIMIT, 70, "policy", decision=True)
    assert r.pass_() == 1 and m.desired.get(VIN, CHARGE_LIMIT).value == 70 and not m.desired.get(VIN, CHARGE_LIMIT).adopted
    assert cmds(m.providerOrder.provider("TeslaBLE")) == ["setChargeLimit", "setChargeLimit"]

def test_a_read_not_newer_than_our_write_is_reasserted_not_adopted():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_()
    v.observe("chargeLimit", 90, "TeslaAPI", at=v.lastWrite("chargeLimit").at)                 # stale poll, same instant
    assert r.pass_() == 0 and v.believed("chargeLimit").value == 50

def test_no_wake_to_lower_wake_to_raise_never_for_a_restore():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE), O.Outcome(O.DONE))); p = m.providerOrder.provider("TeslaBLE"); v.observe("chargeLimit", 90, "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert [x[0] for x in p.calls] == ["setChargeLimit"]
    c.t += 400; v.observe("chargeLimit", 50, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 70, "policy", decision=True); r.pass_()
    assert [x[0] for x in p.calls][1:] == ["wake", "setChargeLimit"]
    c.t += 400; v.observe("chargeLimit", 70, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 90, "restore", decision=True, restore=True); r.pass_()
    assert [x[0] for x in p.calls][3:] == ["setChargeLimit"] and m.heldLimits.get(VIN) == HeldLimit(90, None)   # a restore raises without a wake

def test_fleet_waits_for_ble_to_time_out_and_is_sent_once():                # Review Focus 2
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaAPI")
    f = m.providerOrder.provider("FleetAPI"); b = m.providerOrder.provider("TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    r.pass_(); assert len(b.calls) == 1 and f.calls == [] and m.desired.health(VIN, "TeslaBLE").failingSince == 1000.0
    c.t += PAID_AFTER[CHARGE_LIMIT] - 1; r.pass_(); assert f.calls == [] and len(b.calls) == 1              # BLE retry gap is 300 s too; nothing yet
    c.t += 1; assert r.pass_() == 1 and len(f.calls) == 1 and len(b.calls) == 1 and m.heldLimits.get(VIN) == HeldLimit(90, 50)   # paid pick takes the slot
    c.t += 3600; assert r.pass_() == 0 and len(f.calls) == 1

def test_ble_only_install_keeps_retrying_ble_at_the_retry_cadence():        # a failing free provider is still retried
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE))); b = m.providerOrder.provider("TeslaBLE"); v.observe("chargeLimit", 90, "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(4): r.pass_(); c.t += RETRY[CHARGE_LIMIT]
    assert len(b.calls) == 3 and m.desired.record(VIN, CHARGE_LIMIT).backoff == BACKOFF_START       # attempts() == 3, then backoff
    c.t += BACKOFF_START; r.pass_(); assert len(b.calls) == 4

def test_fleet_only_car_goes_at_once_and_backs_off_when_it_fails():
    m, r, v, c = setup(fleet(O.Outcome(O.ERROR, "500"))); f = m.providerOrder.provider("FleetAPI"); v.observe("chargeLimit", 90, "TeslaAPI")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); assert r.pass_() == 1
    for _ in range(3): c.t += RETRY[CHARGE_LIMIT]; r.pass_()
    assert len(f.calls) == 2 and m.desired.record(VIN, CHARGE_LIMIT).backoff == BACKOFF_START       # attempts() == 2, then backoff
    c.t += BACKOFF_START + 1; r.pass_(); assert len(f.calls) == 3

def test_refused_excludes_the_provider_and_unsupported_falls_through():
    m, r, v, c = setup(ble(O.Outcome(O.REFUSED, "key")), fleet(O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaAPI")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); rec = m.desired.record(VIN, CHARGE_LIMIT)
    assert rec.excluded == {"TeslaBLE"} and m.desired.health(VIN, "TeslaBLE").failing
    c.t += PAID_AFTER[CHARGE_LIMIT] + 1; r.pass_(); assert len(m.providerOrder.provider("FleetAPI").calls) == 1

def test_restore_with_telemetry_showing_a_limit_not_ours_forces_a_live_read():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); m.heldLimits.set(VIN, 90, 50); v.observe("chargeLimit", 80, "TeslaMateVehicle")
    m.vehicleRegistry.registerLiveness("TeslaMateVehicle", lambda vehicle=None: c())            # a healthy feed: age 0 without force
    m.desired.set(VIN, CHARGE_LIMIT, 90, "restore", restore=True)
    attempt = r.plan(v, CHARGE_LIMIT, c()); assert attempt is not None and attempt.force and attempt.value == 90

def test_restore_with_nothing_held_clears_the_desire_and_unknown_limit_on_cloud_reads_first():
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); m.desired.set(VIN, CHARGE_LIMIT, 90, "restore", restore=True)
    assert r.pass_() == 0 and m.desired.get(VIN, CHARGE_LIMIT) is None                           # nothing held: settled at plan time, no loop
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy", decision=True); assert r.pass_() == 1 and m.providerOrder.provider("FleetAPI").calls == []   # read first; nothing known → nothing sent
    assert m.desired.record(VIN, CHARGE_LIMIT).lastOutcome.kind == O.UNREACHABLE

def test_a_rules_settled_restore_clears_the_desire_and_does_not_loop():
    m, r, v, c = setup(ble(O.Outcome(O.DONE)), clock=False); m.heldLimits.set(VIN, 90, 50); v.observe("chargeLimit", 80, "TeslaBLE")   # hand-set before a restart: no write stamp
    m.desired.set(VIN, CHARGE_LIMIT, 90, "restore", restore=True)
    assert r.pass_() == 1 and m.providerOrder.provider("TeslaBLE").calls == [] and m.desired.get(VIN, CHARGE_LIMIT) is None
    assert m.heldLimits.get(VIN) == HeldLimit(80, None)
    for _ in range(5): assert r.pass_() == 0                                                   # real clock, no busy loop

def test_a_new_desire_resets_a_free_only_backoff():                         # N12, BLE-only
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE), O.Outcome(O.UNREACHABLE), O.Outcome(O.UNREACHABLE), O.Outcome(O.DONE))); b = m.providerOrder.provider("TeslaBLE"); v.observe("chargeLimit", 90, "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(4): r.pass_(); c.t += RETRY[CHARGE_LIMIT]
    assert len(b.calls) == 3 and m.desired.record(VIN, CHARGE_LIMIT).backoffUntil > c()
    m.desired.set(VIN, CHARGE_LIMIT, 60, "policy", decision=True); assert r.pass_() == 1 and b.calls[-1] == ("setChargeLimit", VIN, 60)   # prompt, no hour-long wait

def test_a_satisfied_outcome_without_a_stamp_is_not_resent_until_new_evidence():   # N1(b), paid repeat counted
    m, r, v, c = setup(fleet(O.Outcome(O.SATISFIED, "not_charging"))); f = m.providerOrder.provider("FleetAPI"); v.observe("chargingState", "Charging", "TeslaAPI")
    m.desired.set(VIN, CHARGING, False, "distributor"); r.pass_()
    for _ in range(5): r.pass_()
    assert cmds(f) == ["stopCharging"] and v.lastWrite("chargingState") is None                     # settled, unstamped, not repeated
    c.t += 10; v.observe("chargingState", "Charging", "TeslaAPI"); assert r.pass_() == 0               # new evidence inside RETRY: still held
    c.t += RETRY[CHARGING]; assert r.pass_() == 1 and len(cmds(f)) == 2                              # new evidence past RETRY: one more

def test_pass_is_bounded_and_survives_a_raising_provider():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargeLimit", 90, "TeslaBLE"); p = m.providerOrder.provider("TeslaBLE")
    def boom(vin, limit): raise RuntimeError("x")
    p.setChargeLimit = boom; m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    assert r.pass_() == 1 and m.desired.record(VIN, CHARGE_LIMIT).lastOutcome.kind == O.ERROR and r.pass_() == 0
```
(`ScriptedProvider.ready` is `bool(vehicle.vin)`, so BLE is ready for `VIN` without a claim here; `test_registry_read_cascade.py` gains `test_force_reads_past_a_live_feed` in Task 2.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Rules`/`Reconciler`).

- [ ] **Step 3: Implement** per Interfaces; `ScriptedProvider(tier=C.FLEET_COMMAND)` declares its commands at that cost so `candidates` ranks it billed.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_charge_limit_rules.py tests/unit/test_limit_reconciler.py tests/unit/test_lanes.py tests/unit/test_outcome_desired.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Reconcile/
git add lib/TWCManager/Vehicle/Reconcile tests/unit
git commit -m "Add the reconciler: ported charge-limit rules, re-assert/adopt/hands-off, shared channel health, time-aware paid fallback and backoff"
```

### Task 7: Charge-limit decision-makers write desired state; the three `lastChargeLimitApplied` copies and the limit dedupe flags go (closes A5, A11, A12)

Today: `Policy.enforcePolicy` sets `master.lastChargeLimitApplied` and queues `applyChargeLimit`; `background_tasks_thread` turns `checkArrival`/`checkDeparture` into `applyChargeLimit(limit or -1, checkArrival/checkDeparture=True)`; `TeslaAPI.lastChargeLimitApplied`, `HomeAssistant.lastChargeLimitApplied`, `TeslaAPI.stopTryingToApplyLimit`, TeslaBLE's `_stopTryingToApplyLimit`/`_lastAppliedChargeLimit` dicts; HA could never act on `-1` (A11).

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Targets.py`.
- Modify: `lib/TWCManager/TWCMaster.py` (`policyLimit`, `setPolicyLimit`, `desired`/`lanes`/`reconciler` construction, `lastChargeLimitApplied` deleted), `lib/TWCManager/Policy/Policy.py` (`enforcePolicy`), `lib/TWCManager/TWCManager.py` (the `checkArrival`/`checkDeparture` tasks; `master.lanes.start(); master.reconciler.start()` replace `vehicleCommandQueue.start()` — the queue object stays alive until Task 10 but nothing starts it, so `VehicleEndpoint`/`TWCSlave` rate commands queue silently from this task until Task 9 rewires them: acceptable under Decision 29, the branch is not deployed mid-phase; shutdown: `master.reconciler.stop(); master.lanes.drain(timeout=60)`), `lib/TWCManager/Control/HTTPControl.py` (unchanged routes; they still queue the two tasks), `lib/TWCManager/Vehicle/TeslaAPI.py` (`lastChargeLimitApplied` and its `applyChargeLimit(self.lastChargeLimitApplied, ...)` call), `lib/TWCManager/Vehicle/HomeAssistant.py` (`lastChargeLimitApplied`).
- Test: `tests/unit/test_limit_wiring.py`; `tests/unit/test_policy.py` (`lastChargeLimitApplied` assertions become `policyLimit`/desired assertions).

**Interfaces:**
- Produces (`Targets.py`): `presentVehicles(master, capability) -> List[Vehicle]`: registry vehicles that are (a) on a point (`value("twcVin")` truthy), or (b) `attachment("TeslaAPI")` present with `atHome` True, or (c) no TeslaAPI attachment, `attachment("HomeAssistant")` present with `at_home` True, or (d) no TeslaAPI and no HomeAssistant attachment and `"TeslaBLE" in claims` (today's BLE broadcast reach: every keyed car; Phase 5 replaces this function with presence). — plus, for `START_CHARGING`/`STOP_CHARGING`, the anonymous vehicles on a point — filtered to vehicles with at least one candidate for `capability` (`order.candidates(v, capability)` non-empty: an observed-tier car with no command path, or an anonymous car on a TWC under `chargeStopMode` 1, gets no desired state, per the spec). `targetsFor(master, vin: Optional[str], capability=STOP_CHARGING) -> List[Vehicle]`: the one registry vehicle for `vin` (a VIN or an `anon:` key; present or not — a targeted command names its car), else `presentVehicles(master, capability)`. `applyPolicyLimit(master, limit: Optional[int], decision: bool) -> int` (vehicles touched): for each present vehicle with a VIN and a `SET_CHARGE_LIMIT` candidate: `limit` → `desired.set(key, CHARGE_LIMIT, limit, "policy", decision=decision)`; `None` → `held = heldLimits.get(vin)`; `held and held.held is not None` → `desired.set(key, CHARGE_LIMIT, held.outside, "restore", decision=decision, restore=True)`; else `desired.clear(key, CHARGE_LIMIT)`. `onArrival(master) -> None` → `applyPolicyLimit(master, master.policyLimit, decision=True)` (a plug-in is a decision). `onDeparture(master) -> None`: for each VIN in `heldLimits.holding()` whose vehicle is not present → `desired.set(key, CHARGE_LIMIT, held.outside, "restore", decision=True, restore=True)`.
- Produces (`TWCMaster`): `policyLimit: Optional[int] = None` (replaces `lastChargeLimitApplied`'s `0`/`-1`); `setPolicyLimit(self, limit: Optional[int], transition: bool) -> None` → stores it and `applyPolicyLimit(self, limit, decision=transition)`; in `__init__`: `self.desired = DesiredStore()`, `self.lanes = Lanes(self)`, `self.reconciler = VehicleReconciler(self)` after `providerOrder` — all three on their default `time.time` clock, the registry's.
- Produces (`Policy.enforcePolicy`): `limit = ... ; self.master.setPolicyLimit(None if limit == -1 else limit, transition=<self.active_policy changed in this call>)` in place of the `lastChargeLimitApplied` assignment and the queued task. The `limitOverride` arithmetic stays.
- Produces (`TWCManager.py` background thread): `checkArrival` → `onArrival(master)`; `checkDeparture` → `onDeparture(master)`; `checkCharge` unchanged (`vehicleModule.updateChargeAtHome()` until Task 10 reroutes it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_limit_wiring.py
from types import SimpleNamespace
from TWCManager.Vehicle.Reconcile.Desired import CHARGE_LIMIT
from TWCManager.Vehicle.Reconcile.HeldLimits import HeldLimit
from TWCManager.Vehicle.Reconcile.Targets import applyPolicyLimit, onArrival, onDeparture, presentVehicles, targetsFor
from TWCManager.Vehicle.Providers import Capability as C
from tests.unit.test_limit_reconciler import setup, ble, VIN
from TWCManager.Vehicle.Reconcile import Outcome as O
VIN2 = "5YJ3E1EA1KF000002"; VIN3 = "5YJ3E1EA1KF000003"

def cars(m):
    reg = m.vehicleRegistry; a = reg.get(VIN); a.observe("twcVin", "8244", "TWC")
    b = reg.getOrCreate(VIN2, "t"); b.attach("TeslaAPI", SimpleNamespace(atHome=False, ID=2, VIN=VIN2))
    d = reg.getOrCreate(VIN3, "t"); d.claim("TeslaBLE", True, "paired"); return a, b, d

def test_present_rule_until_phase_5():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); a, b, d = cars(m); anon = m.vehicleRegistry.beginPlugSession("8245")
    assert [x.vin for x in presentVehicles(m, C.SET_CHARGE_LIMIT)] == [VIN, VIN3]            # on a TWC; BLE-only with no location evidence; not the away API car, not the anonymous one
    assert [x.key for x in targetsFor(m, None, C.STOP_CHARGING)] == [VIN, VIN3] and targetsFor(m, anon.key) == [anon]   # mode 1: the anonymous car has no stop candidate
    m.settings["chargeStopMode"] = "2"; m.newSlave(b"\x82\x45", 80)
    assert [x.key for x in targetsFor(m, None, C.STOP_CHARGING)] == [VIN, VIN3, anon.key]                            # mode 2: the Gen2 stop can reach it
    m.providerOrder.provider("TeslaBLE").ready = lambda vehicle, cap: False
    assert m.setPolicyLimit(50, transition=True) is None and m.desired.get(VIN, CHARGE_LIMIT) is None   # no candidate: no desired state

def test_policy_limit_sets_desired_for_present_cars_and_none_restores():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); a, b, d = cars(m); m.heldLimits.set(VIN, 90, 50)
    m.setPolicyLimit(50, transition=True); assert m.policyLimit == 50 and m.desired.get(VIN, CHARGE_LIMIT).value == 50 and m.desired.get(VIN2, CHARGE_LIMIT) is None
    m.setPolicyLimit(None, transition=True); assert m.desired.get(VIN, CHARGE_LIMIT).restore and m.desired.get(VIN, CHARGE_LIMIT).value == 90 and m.desired.get(VIN3, CHARGE_LIMIT) is None

def test_periodic_reenforce_does_not_undo_an_adopted_limit():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); cars(m); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.desired.adopt(VIN, CHARGE_LIMIT, 80)
    m.setPolicyLimit(50, transition=False); assert m.desired.get(VIN, CHARGE_LIMIT).value == 80
    onArrival(m); assert m.desired.get(VIN, CHARGE_LIMIT).value == 50

def test_departure_restores_a_held_limit_for_an_absent_car_once():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE))); a, b, d = cars(m); m.heldLimits.set(VIN2, 90, 50)
    m.providerOrder.provider("TeslaBLE").ready = lambda vehicle, cap: vehicle.vin != VIN2            # no BLE claim for the away car
    onDeparture(m); d = m.desired.get(VIN2, CHARGE_LIMIT); assert d.value == 90 and d.restore and m.desired.get(VIN, CHARGE_LIMIT) is None
    r.pass_(); assert m.providerOrder.provider("TeslaBLE").calls == []           # BLE not ready for a car it holds no claim on; nothing sent, nothing paid

def test_policy_thread_calls_set_policy_limit(monkeypatch):
    from TWCManager.Policy.Policy import Policy
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); seen = []; m.setPolicyLimit = lambda limit, transition: seen.append((limit, transition))
    p = Policy(m); p.enforcePolicy({"name": "Charge Now", "charge_amps": "value", "value": 10, "charge_limit": 80})
    p.enforcePolicy({"name": "Charge Now", "charge_amps": "value", "value": 10})
    assert seen == [(80, True), (None, False)] and not hasattr(m, "lastChargeLimitApplied")

def test_no_module_holds_a_copy_of_the_policy_limit():
    import subprocess; from pathlib import Path
    out = subprocess.run(["git", "grep", "-l", "lastChargeLimitApplied\\|stopTryingToApplyLimit\\|_lastAppliedChargeLimit", "--", "lib/TWCManager"], capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2])).stdout.split()
    assert out == []
```
(`Policy(m)` may need `m.config`/`m.getModulesByType` from the real `TWCMaster` built by `setup`; `test_policy.py` shows the minimal construction — reuse its fixture if `Policy(m)` needs more.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Targets`).

- [ ] **Step 3: Implement** per Interfaces (`applyPolicyLimit` sets a restore desire only when `held.held is not None`; a present car with a saved-but-not-held record gets its desire cleared, so Task 6's plan-time rule and this agree). Delete `TeslaAPI.lastChargeLimitApplied`, `HomeAssistant.lastChargeLimitApplied`, `master.lastChargeLimitApplied`, `CarApiVehicle.stopTryingToApplyLimit` and TeslaBLE's two limit dicts **with their uses**: the legacy `applyChargeLimit` bodies in TeslaAPI/TeslaBLE/HA lose their dedupe branches now (they are deleted whole in Task 10; until then they must still run for the façade walk the old tests exercise, so keep them compiling and keep the tests in `test_targeted_charge_limit.py`/`test_own_write_stamps.py` passing by having those bodies send unconditionally).

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager
git add lib/TWCManager tests/unit
git commit -m "Policy, arrival and departure set desired charge limits; the three lastChargeLimitApplied copies and the limit dedupe flags go"
```

### Task 8: Charging on/off as desired state: start/stop from the heartbeat and the distributor, session bounds, disruptive stops, Gen3 per-unit stops (closes A13, A14, A19)

Today `TWCSlave.send_master_heartbeat` calls `master.stopCarsCharging(self.currentVIN)` while a car draws current it should not, `startCarsCharging(self.currentVIN)` when it offers power and the car does not draw, `cancelStopCarsCharging()` whenever it offers > 0 — with `currentVIN` `""` for a non-Tesla or VIN-less car, which `targetsFor(None)` would turn into "every present car"; `TWCMaster.stopCarsCharging` queues a `charge` task (mode 1) or acts on the bus (modes 2/3) and feeds `Policy.overrideLimit` via `stopTimeout`; `startCarsCharging` calls `Policy.clearOverride()` with no guard; `VehicleEndpoint.startCharging/stopCharging` call the same; `stopAskingToStartCharging` is cleared/set in `Policy.enforcePolicy`, `TWCSlave.send_master_heartbeat`/`receive_slave_heartbeat`, `TeslaAPI.py` (many). The Gen3 zero-share stop latch (`_stopRequested`, A14) is replaced by the record. Mode 2 resumes the bus by itself after 60 s (`respondToSlavesExpiry`).

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py` (`startCarsCharging`, `stopCarsCharging`, `cancelStopCarsCharging`, `policyAmpsRequested`), `lib/TWCManager/TWCSlave.py` (`receive_slave_heartbeat` observes `actualCurrent`; the three heartbeat call sites pass `self.vehicleKey` and the `forced` flag; `noteOffering`; delete the `stopAskingToStartCharging` uses), `lib/TWCManager/Vehicle/Reconcile/Targets.py` (`capability` on the present list), `lib/TWCManager/EVSEInstance/Gen2TWC.py` (plug-session end → `master.desired.endSession(key)`), `lib/TWCManager/EVSEInstance/Gen3TWC.py` (falling `vehicle_connected` edge → `endSession`), `lib/TWCManager/Policy/Policy.py` (delete the `stopAskingToStartCharging` loop), `lib/TWCManager/EVSEInstance/VehicleEndpoint.py` (`wantsToCharge`, `maxPower` honour bounds), `lib/TWCManager/EVSEInstance/ChargingPoint.py` (`startCharging`/`stopCharging` → desired for the point's vehicle key).
- Test: `tests/unit/test_charging_reconciler.py`; `tests/unit/test_twcslave.py` and `test_twcmaster.py` assertions on `queue_background_task({"cmd": "charge", ...})` become desired-state assertions; `tests/unit/test_vehicle_endpoint.py` gains the bounds cases.

**Interfaces:**
- Produces (`TWCMaster`): `startCarsCharging(self, vin=None) -> None`: `for v in targetsFor(self, vin, START_CHARGING): self.desired.set(v.key, CHARGING, True, "distributor")`; under `chargeStopMode` 1 `policy = self.getModuleByName("Policy"); policy and policy.clearOverride()`. `stopCarsCharging(self, vin=None, forced=False) -> None`: `for v in targetsFor(self, vin, STOP_CHARGING): self.desired.set(v.key, CHARGING, False, "distributor", forced=forced)` (a user-started car ignores it unless `forced`); under mode 1 the `stopTimeout`/`overrideLimit` logic stays, guarded the same way. Modes 2/3 no longer act on the bus here: the reconciler reaches `Gen2TWCProvider.stopCharging` (tier 3) once a ready BLE has failed for 60 s, or at once when the car has no free stop candidate (TeslaBLE not ready: an anonymous, non-Tesla or unclaimed car). `cancelStopCarsCharging(self, vin=None) -> int`: `desired.release(v.key, CHARGING, False, "distributor")` per target plus `lanes.cancel(v.key)` (stops only); returns the count released. `vin` is a registry key: a VIN or an `anon:` key.
- Produces (`Targets.targetsFor`): as Task 7 defines it (`anon:` keys resolve like a VIN; anonymous cars on a point are start/stop targets when a provider can reach them). `TWCMaster.setMaxAmpsToDivideAmongSlaves(amps)` records the policy's request before the wiring clamp as `self.policyAmpsRequested`.
- Produces (`TWCSlave`): `receive_slave_heartbeat` **observes its readings**: `v = registry.get(self.vehicleKey)` whenever `vehicleKey` is set, and `v.observe("actualCurrent", self.reportedAmpsActual, "Gen2TWC", seen=False)` **only when `v` is not `None`** (while a freshly heard VIN is pending or rejected, `currentVIN` names a car the registry does not hold: skip, never raise on the serial thread) — a leaf-lock dict update, as the TWC VIN write already is; the producer of the TWC current the reconciler's `known()` stand-in reads. `TWCMaster.policyAmpsRequested = 0` as a class default (nothing forced before the first policy pass). `send_master_heartbeat`: the stop call becomes `self.master.stopCarsCharging(self.vehicleKey, forced=self._stopIsForced(numCarsCharging))` where `_stopIsForced(self, numCarsCharging) -> bool` is `self.master.policyAmpsRequested / max(1, numCarsCharging) >= self.minAmpsToOffer()` with the `numCarsCharging` the heartbeat already computed (never a second `num_cars_charging_now()`: it publishes Status and runs session transitions) — the policy's **unclamped** request would have allowed this car its minimum, so the shortfall comes from the `wiringMaxAmpsAllTWCs`/controller clamp, which a user start must not override; the start and cancel calls pass `self.vehicleKey`; a `None` key sends nothing; each heartbeat also calls `master.desired.noteOffering(self.vehicleKey, self.lastAmpsOffered >= self.minAmpsToOffer())`. `ChargingPoint.setTargetPower` does the same for vehicle members (`watts >= point.minPower`).
- Produces (`Gen2TWC`): where the slave ends a plug session (`currentVIN`/`lastVIN` cleared on unplug evidence, the same place `registry.endPlugSession` is called today) → `master.desired.endSession(<the key it served>)`. (`Gen3TWC.refreshVitals` falling edge likewise.)
- Produces (`VehicleEndpoint`): `wantsToCharge` → also `True` when `master.desired.bounds(vehicle.key).wantsCharge`, and `False` when `bounds.userStopped`; `maxPower` → `min(vehicleMaxAmps(...), bounds.maxAmps or inf)` in watts.
- Produces (`ChargingPoint`): `startCharging()`/`stopCharging(forced=False)` → `master.startCarsCharging(key)`/`stopCarsCharging(key, forced)` when `key` is a registry key (VIN or `anon:`), else nothing.
- Reconciler (`CHARGING` aspect, generic since Task 6): `known()` falls back to the heartbeat's `actualCurrent` observations for cars no vehicle source describes; the lane stamps `chargingState` on `DONE` only and never for a disruptive stop; an unstamped settled stop is re-planned only on a newer reading and never inside `RETRY[CHARGING]` (step 1's settled gate); adoption of a vehicle-sourced `"Charging"` newer than our stop stamp → `bounds.wantsCharge = True`, of a vehicle-sourced stopped-like state newer than our start stamp **while the point was offering power** → `bounds.userStopped = True` (while we offer nothing the stop is ours: hands off); a TWC-sourced observation never adopts; a resume after our own disruptive stop never adopts; `NO_INDIVIDUAL_STOP` drops the Gen3 provider for a stop on a multi-unit bus; under `chargeStopMode` 2/3 billed stop providers are suppressed (Task 4); `afterWrite` records `lastStopProvider`, which gates the Gen2 mode-2 start (Task 4).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_charging_reconciler.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import CHARGING, CHARGE_LIMIT
from TWCManager.Vehicle.Reconcile.Reconciler import PAID_AFTER, RETRY, LIMIT_THEN_START_GAP
from tests.unit.test_limit_reconciler import setup, ble, fleet, cmds, VIN

def onTwc(m, v): v.observe("twcVin", "8244", "TWC"); m.getSlaveTWCs()[0].currentVIN = VIN

def test_heartbeat_stop_is_sent_once_and_a_stale_read_does_not_reassert():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE"); b = m.providerOrder.provider("TeslaBLE")
    for _ in range(5): m.stopCarsCharging(VIN)
    assert r.pass_() == 1 and b.calls == [("stopCharging", VIN, None)] and v.believed("chargingState").value == "Stopped" and m.desired.state(VIN).lastStopProvider == "TeslaBLE"
    assert r.pass_() == 0
    c.t += 10; v.observe("chargingState", "Charging", "TeslaBLE", at=v.lastWrite("chargingState").at)      # same instant as our write: not adopted
    assert r.pass_() == 0 and m.desired.get(VIN, CHARGING).value is False

def test_user_started_car_is_adopted_as_a_session_bound_and_not_restopped():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE"); m.stopCarsCharging(VIN); r.pass_()
    c.t += 30; v.observe("chargingState", "Charging", "TeslaMateVehicle")
    assert r.pass_() == 0 and m.desired.bounds(VIN).wantsCharge and m.desired.get(VIN, CHARGING) is None
    m.stopCarsCharging(VIN); assert m.desired.get(VIN, CHARGING) is None and len(m.providerOrder.provider("TeslaBLE").calls) == 1
    m.getSlaveTWCs()[0].currentVIN = ""; v.observe("twcVin", None, "TWC"); r.pass_(); assert not m.desired.bounds(VIN).wantsCharge   # unplug clears the bound

def test_a_wiring_forced_stop_is_delivered_despite_a_user_start():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE"); m.stopCarsCharging(VIN); r.pass_()
    c.t += 30; v.observe("chargingState", "Charging", "TeslaMateVehicle"); r.pass_(); assert m.desired.bounds(VIN).wantsCharge
    m.stopCarsCharging(VIN, forced=True); assert m.desired.get(VIN, CHARGING).value is False and m.desired.get(VIN, CHARGING).forced
    r.pass_(); assert cmds(m.providerOrder.provider("TeslaBLE")) == ["stopCharging", "stopCharging"]
    s = m.getSlaveTWCs()[0]; m.config = {"config": dict(m.config["config"], wiringMaxAmpsAllTWCs=16)}                 # a copy: CONFIG is shared
    m.setMaxAmpsToDivideAmongSlaves(40); assert m.getMaxAmpsToDivideAmongSlaves() == 16 and s._stopIsForced(3)         # policy 40 A would allow 13 A each for 3 cars: the wiring clamp binds
    m.setMaxAmpsToDivideAmongSlaves(10); assert not s._stopIsForced(3)                                                  # policy 10 A: 3 A each, the policy binds

def test_a_stop_caused_by_our_own_zero_offer_is_hands_off():                   # N3
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Stopped", "TeslaBLE"); m.startCarsCharging(VIN); r.pass_()
    m.desired.noteOffering(VIN, False); c.t += 30; v.observe("chargingState", "Stopped", "TeslaMateVehicle")                 # Track Green Energy dropped the offer; the car stopped
    assert r.pass_() == 0 and not m.desired.bounds(VIN).userStopped and m.desired.get(VIN, CHARGING).value is True
    c.t += 30; m.desired.noteOffering(VIN, True); assert r.pass_() == 1 and cmds(m.providerOrder.provider("TeslaBLE"))[-1] == "startCharging"   # offering again: the stale stop is not the user's; start re-asserted

def test_heartbeat_skips_the_registry_write_for_a_pending_vin():             # S1
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = m.getSlaveTWCs()[0]; s.currentVIN = "5YJ3E1EA1KF000009"                # heard, not yet confirmed: not in the registry
    drive(m, s, amps_actual=12.0); assert m.vehicleRegistry.get("5YJ3E1EA1KF000009") is None                                 # no raise, nothing created
    s.currentVIN = VIN; drive(m, s, amps_actual=12.0); assert v.latest("actualCurrent").value == 12.0

def test_a_stop_before_the_first_policy_pass_is_not_forced():                 # S2
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = m.getSlaveTWCs()[0]; s.currentVIN = VIN; v.observe("chargingState", "Charging", "TeslaBLE")
    assert m.policyAmpsRequested == 0 and s._stopIsForced(1) is False
    s.timeLastAmpsOfferedChanged = s.timeReportedAmpsActualChangedSignificantly = c() - 61; m.num_cars_charging_now = Mock(return_value=1)
    drive(m, s, amps_actual=12.0); assert m.desired.get(VIN, CHARGING).value is False and not m.desired.get(VIN, CHARGING).forced
    assert m.num_cars_charging_now.call_count == 1                                                                        # the heartbeat's own call only

def test_heartbeat_readings_are_not_evidence_for_a_car_with_vehicle_reads():   # S4, paid repeat counted
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(fleet(O.Outcome(O.SATISFIED, "not_charging"))); s = m.getSlaveTWCs()[0]; s.currentVIN = VIN; f = m.providerOrder.provider("FleetAPI")
    v.observe("chargingState", "Charging", "TeslaAPI"); m.stopCarsCharging(VIN); r.pass_(); assert cmds(f) == ["stopCharging"]
    for _ in range(10): c.t += 61; drive(m, s, amps_actual=12.0); r.pass_()                                                # readings every heartbeat, past RETRY each time
    assert cmds(f) == ["stopCharging"]                                                                                    # no vehicle read arrived: not re-sent

def test_zero_offer_sends_no_start_or_wake():                                 # S6, paid calls counted
    m, r, v, c = setup(fleet(O.Outcome(O.SATISFIED, "complete"))); onTwc(m, v); f = m.providerOrder.provider("FleetAPI"); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.desired.noteOffering(VIN, False); m.startCarsCharging(VIN)
    for _ in range(5): c.t += 61; v.observe("chargingState", "Stopped", "TeslaAPI"); r.pass_()
    assert f.calls == [] and m.desired.get(VIN, CHARGING).value is True                                                   # nothing offered: no start, no wake
    m.desired.noteOffering(VIN, True); c.t += 61; r.pass_(); assert [x[0] for x in f.calls] == ["wake", "startCharging"]   # offering again: one start

def test_user_stop_in_the_app_holds_off_starts_for_the_session():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Stopped", "TeslaBLE"); m.startCarsCharging(VIN); r.pass_()
    m.desired.noteOffering(VIN, True); c.t += 30; v.observe("chargingState", "Stopped", "TeslaMateVehicle"); assert r.pass_() == 0 and m.desired.bounds(VIN).userStopped
    m.startCarsCharging(VIN); assert m.desired.get(VIN, CHARGING) is None

def test_twc_current_alone_never_adopts_charging():                          # Review Focus 4
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Stopped", "TeslaBLE"); m.stopCarsCharging(VIN); r.pass_()
    c.t += 30; v.observe("actualCurrent", 10.0, "Gen2TWC"); v.observe("chargingState", "Charging", "Gen2TWC")
    assert r.pass_() == 0 and not m.desired.bounds(VIN).wantsCharge and m.providerOrder.provider("TeslaBLE").calls == []

def test_start_waits_five_seconds_after_a_limit_write_and_wakes():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); b = m.providerOrder.provider("TeslaBLE")
    v.observe("chargeLimit", 50, "TeslaBLE"); v.observe("chargingState", "Stopped", "TeslaBLE")
    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy"); m.startCarsCharging(VIN); r.pass_()
    assert [x[0] for x in b.calls] == ["wake", "setChargeLimit"] and r.pass_() == 0
    c.t += LIMIT_THEN_START_GAP + 1; r.pass_(); assert [x[0] for x in b.calls][2:] == ["wake", "startCharging"]

def test_complete_or_disconnected_car_is_left_alone():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Disconnected", "TeslaBLE"); m.startCarsCharging(VIN)
    assert r.pass_() == 0 and m.providerOrder.provider("TeslaBLE").calls == []

def test_cancel_releases_an_undelivered_stop_only():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE")
    m.stopCarsCharging(VIN); assert m.cancelStopCarsCharging() == 1 and m.desired.get(VIN, CHARGING) is None
    m.stopCarsCharging(VIN); r.pass_(); assert m.cancelStopCarsCharging(VIN) == 0 and m.desired.get(VIN, CHARGING).value is False
    m.startCarsCharging(VIN); assert m.cancelStopCarsCharging(VIN) == 0 and m.desired.get(VIN, CHARGING).value is True   # a start is never cancelled

def test_stop_falls_to_fleet_after_60s_once():                               # Review Focus 2
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaAPI"); f = m.providerOrder.provider("FleetAPI")
    m.stopCarsCharging(VIN); r.pass_(); assert f.calls == [] and len(m.providerOrder.provider("TeslaBLE").calls) == 1
    c.t += PAID_AFTER[CHARGING] - 1; r.pass_(); assert f.calls == []
    c.t += 1; r.pass_(); assert f.calls == [("stopCharging", VIN, None)]
    c.t += 3600; r.pass_(); assert len(f.calls) == 1

def test_disruptive_stop_waits_for_ble_only_when_ble_is_set_up_for_the_car():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaAPI")
    m.settings["chargeStopMode"] = "2"; m.stopCarsCharging(VIN); r.pass_()
    assert m.settings.get("respondToSlaves", 1) == 1 and len(m.providerOrder.provider("TeslaBLE").calls) == 1   # BLE ready for this car: tried first
    c.t += PAID_AFTER[CHARGING]; r.pass_(); assert m.settings["respondToSlaves"] == 0 and m.providerOrder.provider("FleetAPI").calls == []   # billed stops suppressed under mode 2
    m2, r2, v2, c2 = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m2, v2); v2.observe("chargingState", "Charging", "TeslaAPI")
    m2.providerOrder.provider("TeslaBLE").ready = lambda vehicle, cap: False                                   # no key, or a refused one
    m2.settings["chargeStopMode"] = "2"; m2.stopCarsCharging(VIN); r2.pass_()
    assert m2.settings["respondToSlaves"] == 0 and m2.providerOrder.provider("TeslaBLE").calls == []           # at once

def test_disruptive_stop_is_sent_once_until_new_evidence_then_reasserted():   # N1(a), real heartbeat readings
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = m.getSlaveTWCs()[0]; anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "2"
    drive(m, s, amps_actual=12.0); assert anon.latest("actualCurrent").value == 12.0 and anon.latest("actualCurrent").source == "Gen2TWC"   # the heartbeat records current
    m.stopCarsCharging(anon.key); assert r.pass_() == 1 and m.settings["respondToSlaves"] == 0 and anon.lastWrite("chargingState") is None     # never stamped
    m.settings["respondToSlaves"] = 1
    for _ in range(5): assert r.pass_() == 0                                                                    # no new reading: not re-sent
    c.t += 30; drive(m, s, amps_actual=12.0); assert r.pass_() == 0 and m.settings["respondToSlaves"] == 1         # newer reading, inside RETRY: held
    c.t += 31; drive(m, s, amps_actual=12.0); m.stopCarsCharging(anon.key); assert r.pass_() == 1 and m.settings["respondToSlaves"] == 0   # resumed, past RETRY: re-stopped
    m.settings["respondToSlaves"] = 1; c.t += 61; drive(m, s, amps_actual=0.5); assert r.pass_() == 0 and m.settings["respondToSlaves"] == 1   # quiet bus: satisfied

def test_disruptive_stop_on_the_real_clock_is_sent_once():                    # N1(a), production clock
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(ble(O.Outcome(O.DONE)), clock=False); s = m.getSlaveTWCs()[0]; anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    drive(m, s, amps_actual=12.0); m.stopCarsCharging(anon.key)
    sent = sum(r.pass_() for _ in range(20)); drive(m, s, amps_actual=12.0)
    assert sent == 1 and m.sendStopCommand.call_count == 1 and not s.stopRequested                                # one relay stop, not one per pass

def test_mode_2_start_after_a_ble_stop_goes_through_ble():
    m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE"); m.settings["chargeStopMode"] = "2"
    m.stopCarsCharging(VIN); r.pass_(); assert m.desired.state(VIN).lastStopProvider == "TeslaBLE"
    c.t += 61; m.startCarsCharging(VIN); r.pass_(); assert cmds(m.providerOrder.provider("TeslaBLE")) == ["stopCharging", "startCharging"] and m.settings.get("respondToSlaves", 1) == 1

def test_heartbeat_stop_targets_the_anonymous_car():                         # real TWCSlave heartbeat, non-Tesla car
    from tests.unit.gen2_helpers import drive as heartbeat                                                    # the real receive_slave_heartbeat + send_master_heartbeat
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = m.getSlaveTWCs()[0]; anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    s.timeLastAmpsOfferedChanged = s.timeReportedAmpsActualChangedSignificantly = c() - 61                      # past the heartbeat's own 60 s stop gates
    m.setMaxAmpsToDivideAmongSlaves(0); heartbeat(m, s, amps_actual=12.0)                                      # offer 0, car still drawing
    assert m.desired.get(anon.key, CHARGING).value is False and r.pass_() == 1 and s.stopRequested
    heartbeat(m, s, amps_actual=12.0); m.sendStopCommand.assert_called_once_with(s.TWCID)                    # sent by the heartbeat, on its thread

def test_shared_channel_health_lets_a_later_aspect_go_paid_at_once():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); f = m.providerOrder.provider("FleetAPI")
    v.observe("chargeLimit", 90, "TeslaAPI"); v.observe("chargingState", "Stopped", "TeslaAPI"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    r.pass_(); c.t += PAID_AFTER[CHARGE_LIMIT]; r.pass_(); assert cmds(f) == ["setChargeLimit"]
    c.t += LIMIT_THEN_START_GAP + 1; m.startCarsCharging(VIN); r.pass_(); assert cmds(f) == ["setChargeLimit", "startCharging"]   # no fresh 60 s wait

def test_shared_channel_health_windows_run_concurrently_not_summed():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); f = m.providerOrder.provider("FleetAPI")
    v.observe("chargeLimit", 90, "TeslaAPI"); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.startCarsCharging(VIN); r.pass_()
    c.t += PAID_AFTER[CHARGING]; r.pass_(); assert cmds(f) == ["startCharging"]
    c.t += PAID_AFTER[CHARGE_LIMIT] - PAID_AFTER[CHARGING]; r.pass_(); assert cmds(f) == ["startCharging", "setChargeLimit"]

def test_a_free_success_puts_ble_first_again():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE), O.Outcome(O.UNREACHABLE), O.Outcome(O.DONE)), fleet(O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); b = m.providerOrder.provider("TeslaBLE"); f = m.providerOrder.provider("FleetAPI")
    v.observe("chargeLimit", 90, "TeslaAPI"); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.startCarsCharging(VIN); r.pass_(); c.t += PAID_AFTER[CHARGING]; r.pass_(); assert cmds(f) == ["startCharging"] and [x[0] for x in f.calls] == ["wake", "startCharging"]   # BLE's wake and start consumed the two UNREACHABLEs; Fleet woke (free check inside) then started
    v.observe("bleReach", True, "TeslaBLE"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_()
    assert cmds(b) == ["startCharging", "setChargeLimit"] and len(cmds(f)) == 1 and not m.desired.health(VIN, "TeslaBLE").failing

def test_paid_calls_never_exceed_desired_changes():
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); f = m.providerOrder.provider("FleetAPI")
    v.observe("chargeLimit", 90, "TeslaAPI"); v.observe("chargingState", "Stopped", "TeslaAPI"); changes = 0
    for limit, start in ((50, True), (60, False), (70, True)):
        m.desired.set(VIN, CHARGE_LIMIT, limit, "policy", decision=True); changes += 1
        (m.startCarsCharging if start else m.stopCarsCharging)(VIN); changes += 1
        for _ in range(12): c.t += 60; r.pass_()
    assert len(cmds(f)) <= changes

def probeSetup(probe):
    m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE), probe, O.Outcome(O.DONE)), fleet(O.Outcome(O.DONE))); onTwc(m, v)
    v.observe("chargeLimit", 90, "TeslaAPI"); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.desired.health(VIN, "TeslaBLE").failure(c() - 600)                                                        # last BLE attempt 10 min ago (PROBE_AFTER)
    return m, r, v, c, m.providerOrder.provider("TeslaBLE"), m.providerOrder.provider("FleetAPI")

def test_stale_ble_failure_is_probed_and_a_good_probe_sends_over_ble():
    m, r, v, c, b, f = probeSetup(O.Outcome(O.DONE)); b.outcomes = [O.Outcome(O.DONE), O.Outcome(O.DONE)]
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert [x[0] for x in b.calls] == ["probe"] and f.calls == []
    r.pass_(); assert [x[0] for x in b.calls] == ["probe", "setChargeLimit"] and f.calls == [] and not m.desired.health(VIN, "TeslaBLE").failing

def test_stale_ble_failure_is_probed_once_and_a_bad_probe_goes_paid_at_once():
    m, r, v, c, b, f = probeSetup(O.Outcome(O.UNREACHABLE)); b.outcomes = [O.Outcome(O.UNREACHABLE)]
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert [x[0] for x in b.calls] == ["probe"]
    r.pass_(); assert [x[0] for x in b.calls] == ["probe"] and cmds(f) == ["setChargeLimit"] and m.desired.health(VIN, "TeslaBLE").lastFailureAt == c()

def test_a_recent_ble_failure_is_not_probed():
    m, r, v, c, b, f = probeSetup(O.Outcome(O.DONE)); m.desired.health(VIN, "TeslaBLE").failure(c() - 30); m.desired.health(VIN, "TeslaBLE").failingSince = c() - 600
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert b.calls == [] and cmds(f) == ["setChargeLimit"]

def test_two_aspects_due_together_share_one_probe():
    m, r, v, c, b, f = probeSetup(O.Outcome(O.DONE)); b.outcomes = [O.Outcome(O.DONE), O.Outcome(O.DONE), O.Outcome(O.DONE)]
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.startCarsCharging(VIN); r.pass_(); assert [x[0] for x in b.calls] == ["probe"]
    r.pass_(); assert [x[0] for x in b.calls][1:] == ["setChargeLimit"] and f.calls == []                        # the start waits 5 s after the limit write
    c.t += LIMIT_THEN_START_GAP + 1; r.pass_(); assert [x[0] for x in b.calls] == ["probe", "setChargeLimit", "wake", "startCharging"] and f.calls == []

def test_non_tesla_car_on_a_twc_gets_the_disruptive_stop_at_once():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"
    anon.observe("actualCurrent", 12.0, "Gen2TWC"); m.stopCarsCharging(anon.key); assert r.pass_() == 1 and m.getSlaveTWCs()[0].stopRequested

def test_gen3_multi_unit_stop_uses_the_car_not_the_bus():
    from tests.unit.test_gen3twc_provider import make as make_gen3, vitals
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); g, ctl, gp = make_gen3(("10.0.0.1", "10.0.0.2")); gp.master = m; m.providerOrder.register(gp)
    a, b = ctl.devices(); vitals(a, True); vitals(b, True); car = m.vehicleRegistry.getOrCreate(VIN, "t"); car.observe("pluggedIn", True, "TeslaMateVehicle")
    gp.unitFor = lambda vehicle: a if vehicle.vin == VIN else None; v.observe("chargingState", "Charging", "TeslaBLE")
    m.stopCarsCharging(VIN); r.pass_(); assert m.providerOrder.provider("TeslaBLE").calls == [("stopCharging", VIN, None)] and ctl.setHouseWatts.call_count == 0

def test_endpoint_bounds_feed_the_distributor():
    from TWCManager.EVSEInstance.VehicleEndpoint import VehicleEndpoint
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); e = VehicleEndpoint(v, m.providerOrder, m); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.desired.bounds(VIN).maxAmps = 16; assert e.maxPower == 16 * 240 and e.wantsToCharge
    v.observe("chargingState", "Disconnected", "TeslaAPI"); m.desired.bounds(VIN).wantsCharge = True; assert e.wantsToCharge
    m.desired.bounds(VIN).wantsCharge = False; m.desired.bounds(VIN).userStopped = True; v.observe("chargingState", "Stopped", "TeslaAPI"); assert not e.wantsToCharge

def test_plug_session_end_without_a_twc_vin_clears_the_bounds():
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); v.observe("pluggedIn", True, "TeslaMateVehicle"); m.desired.bounds(VIN).maxAmps = 16; r.pass_()
    c.t += 10; v.observe("pluggedIn", False, "TeslaMateVehicle"); r.pass_(); assert m.desired.bounds(VIN).maxAmps is None
```
(`tests/unit/gen2_helpers.drive` (Task 4) drives a real slave through `receive_slave_heartbeat` and `send_master_heartbeat`. `make_gen3` and `vitals` come from Phase 2's Gen3 tests; the Gen3 provider's `limitations` reports `NO_INDIVIDUAL_STOP` while both units are occupied.) Rewrite the `test_twcslave.py`/`test_twcmaster.py` cases that assert a queued `charge` task to assert `master.desired.get(key, CHARGING)`.

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TWCMaster' object has no attribute 'desired'` or the stop still queues a task).

- [ ] **Step 3: Implement** per Interfaces; delete the `stopAskingToStartCharging` uses in `TWCSlave.py`, `Policy.py` (the TeslaAPI attribute itself goes in Task 10 with the legacy `car_api_charge`).

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager
git add lib/TWCManager tests/unit
git commit -m "Start and stop charging as desired state: session bounds for user changes, disruptive stops last, per-unit Gen3 stops via the car"
```

### Task 9: Amps as desired state with layered actuators inside a charging point (closes A13's amps half; replaces `chargeRateControl`'s branches on the distributor path)

Today `ChargingPoint.setTargetPower` hands the whole target to the TWC member and `TWCSlave.send_master_heartbeat` queues `setChargeRate` under mode 2 / mode 3 below 6 A and raises the car to `wiringMaxAmps` once under mode 1 (`_requestVehicleRateRaise`, `vehicleRateRaised`); `VehicleEndpoint.setTargetPower` queues `setAmps` on change or every `REFRESH_SECONDS` (600 s). `VehicleEndpoints` is registered only with TeslaAPI, so a BLE-only or pure-Gen2 point has no vehicle member and the heartbeat's mode-2/3 branch is its only car-side actuator. The registry's `availableCurrent` is `charger_pilot_current` — the EVSE's offer, not the car's own setting; the car's setting is `charge_current_request` (Fleet `vehicle_data`, BLE `state charge`, Fleet Telemetry `ChargeCurrentRequest`). Phase 2 ledger: a failed send waits 600 s (should be 60 s); `targetAmps` goes with the façade.

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Fields.py` (`chargeCurrentRequest` in `FIELDS`), `lib/TWCManager/Vehicle/Registry/Sources.py` (`CHARGE_FIELDS` gains it), `lib/TWCManager/Vehicle/TeslaAPI.py` (`update_vehicle_data` observes `charge_state.charge_current_request`), `lib/TWCManager/Vehicle/TeslaBLE.py` (`get_charge_state` maps `chargeCurrentRequest`), `lib/TWCManager/Vehicle/FleetTelemetryMQTT.py` (`ChargeCurrentRequest`), `lib/TWCManager/EVSEInstance/ChargingPoint.py` (`setTargetPower`), `lib/TWCManager/EVSEInstance/Gen2TWC.py` (`pointOwnsAmps`), `lib/TWCManager/EVSEInstance/VehicleEndpoint.py` (`setTargetPower`), `lib/TWCManager/TWCSlave.py` (`_queueChargeRate`, `_requestVehicleRateRaise`, `_resetVehicleRateRaised`, `vehicleRateRaised`; the mode 2/3 branch and the raise skip when `pointOwnsAmps`; the `__lastAPIAmps*` repeat counters go), `tests/unit/test_charging_points.py` (`test_target_goes_to_the_local_member_only_when_present`), `tests/unit/test_vehicle_endpoint.py` (`test_set_target_power_queues_on_change_or_after_refresh`), `tests/unit/test_twcslave.py` (mode 2/3 and raise cases), `tests/unit/test_registry_fields.py` (the new field), `tests/unit/test_carapivehicle_registry.py` / `test_telemetry_registry.py` (one observation case each).
- Test: `tests/unit/test_amps_reconciler.py`.

**Interfaces:**
- Produces (`Fields`): `"chargeCurrentRequest"` in `FIELDS` (the car's own charge-current setting in amps). Sources: TeslaAPI observes `charge_state["charge_current_request"]`, TeslaBLE `chargeCurrentRequest` from `state charge`, Fleet Telemetry `ChargeCurrentRequest`; TeslaMate does not publish it. `FIELD_FOR[AMPS]` is this field (Task 1); until a source reports it for a car, `known(vehicle, AMPS)` is the own-write stamp alone (satisfied by our write, never adopted).
- Produces (`Gen2TWC`): `pointOwnsAmps: bool = False` — set by `ChargingPoint.setTargetPower` on every pass (`True` when the point has a non-read-only vehicle member); while `True` the heartbeat neither queues a car rate nor lifts: the point owns the car's `AMPS` aspect; one writer per cycle.
- Produces (`ChargingPoint`): `carriers(self) -> Tuple[bool, bool]` = `(localCarries, vehicleCarries)` from `chargeRateControl`: `1` → `(True, False)`, `2` → `(False, True)`, `3` → `(True, True)`; `setTargetPower(self, watts)`:
  - `amps = int(convertWattsToAmps(watts, currentVoltage))`; `local = localEndpoints[0]` when any; `cars` = `vehicleEndpoints` that are not read-only; per car `vmax = min(vehicleMaxAmps(vehicle, config), bounds.maxAmps or inf)` (the rate clamp) and `liftMax = min(config["wiringMaxAmpsPerTWC"] (32 default), bounds.maxAmps or inf)` (the lift target: today's `wiringMaxAmps`, never the car's own current limit, which is what the lift raises); `local.pointOwnsAmps = bool(cars)` when `local` is a `Gen2TWC`.
  - No local member → each car `setTargetPower(watts)` (Phase 2 behaviour; the endpoint turns it into desired amps below).
  - Local member and **no car** (BLE-only, pure Gen2, HA-only points) → `local.setTargetPower(watts)` and nothing else: the Phase 2 path; the heartbeat applies `chargeRateControl` exactly as today (its branches write desired amps through `_queueChargeRate`, below).
  - `watts == 0` → `local.setTargetPower(0)`; nothing for cars (a stop is the `CHARGING` aspect).
  - Local member and a car, the layered rule by mode: `(True, False)` mode 1: `local.setTargetPower(watts)`; once per plug session (`bounds.lifted` False and `known(AMPS)` unknown or below `liftMax`): `desired.set(key, AMPS, liftMax, "lift", lift=True)`. `(False, True)` mode 2: `local.setTargetPower(local.maxPower)`; cars `desired.set(key, AMPS, clamp(amps, 1, vmax), "distributor")`. `(True, True)` mode 3: `lo = local.minAmps`; `amps >= lo` → `local.setTargetPower(watts)` and, when a car's `known(AMPS)` is known and below `amps`, `desired.set(key, AMPS, liftMax, "lift", lift=True)` (raise only when the car would cap; unknown → no lift; otherwise leave it — undershoot is safe, and this is the hysteresis); `amps < lo` → `local.setTargetPower(local.minPower)` (hold at the floor, not the max) and cars `desired.set(key, AMPS, max(1, amps), "distributor")`.
- Produces (`VehicleEndpoint`): `setTargetPower(self, watts)`: `0` → return; else `desired.set(vehicle.key, AMPS, max(1, int(convertWattsToAmps(...))), "distributor")`; `REFRESH_SECONDS`, `_lastAmps`, `_lastQueuedAt` deleted (the record and `known` replace the resend rule).
- Produces (`TWCSlave`): `_queueChargeRate(self, amps, callback=None)` → `master.desired.set(self.vehicleKey, AMPS, int(amps), "heartbeat")` when `vehicleKey` is set and `not self.pointOwnsAmps`; `_requestVehicleRateRaise()` → `master.desired.set(self.vehicleKey, AMPS, self.wiringMaxAmps, "lift", lift=True)` under the same guard; `vehicleRateRaised` → read-only property `master.desired.bounds(self.vehicleKey).lifted` (delete the `__init__` assignment; `False` when `vehicleKey` is `None`); `_resetVehicleRateRaised()` → `master.desired.clear(self.vehicleKey, AMPS)` and `bounds.lifted = False`; the `__lastAPIAmpsValue/Repeat/Request` block collapses to one `_queueChargeRate(desiredAmpsOffered)` call per heartbeat (the store coalesces unchanged values).
- Reconciler (`AMPS` aspect): candidates with `localRule = not d.lift` (#660: a lift reaches Fleet even where the TWC covers the rate; a distributor rate does not), module-less providers dropped; `maxAge = None` (no read before a rate); `satisfied` on `int(known) == int(desired)`; adoption of a vehicle-sourced `chargeCurrentRequest` newer than our write and the desire, differing from our write → `bounds.maxAmps` when lower (the user lowered it in the app); `RETRY[AMPS] = 60` (ledger: 60 s, not 600 s); `afterWrite` marks `bounds.lifted` on a settled lift.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_amps_reconciler.py
from TWCManager.EVSEInstance.ChargingPoint import groupEndpoints
from TWCManager.EVSEInstance.VehicleEndpoint import VehicleEndpoint
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from TWCManager.Vehicle.Reconcile.Desired import AMPS
from TWCManager.Vehicle.Reconcile.Reconciler import RETRY
from tests.unit.test_limit_reconciler import setup, ble, fleet, cmds, VIN

def point(m, v, mode, car=True):
    m.settings["chargeRateControl"] = str(mode); s = m.getSlaveTWCs()[0]; s.currentVIN = VIN; v.observe("twcVin", "8244", "TWC")
    (pt,) = groupEndpoints(m, [s] + ([VehicleEndpoint(v, m.providerOrder, m)] if car else [])); return pt, s

def test_mode_1_twc_carries_and_the_car_is_lifted_once_per_session():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargeCurrentRequest", 16, "TeslaBLE"); pt, s = point(m, v, 1)
    pt.setTargetPower(2400); assert s._evseTargetAmps == 10 and s.pointOwnsAmps and m.desired.get(VIN, AMPS).lift and m.desired.get(VIN, AMPS).value == 32
    r.pass_(); assert cmds(m.providerOrder.provider("TeslaBLE")) == ["setAmps"] and m.providerOrder.provider("TeslaBLE").calls[-1] == ("setAmps", VIN, 32) and m.desired.bounds(VIN).lifted
    pt.setTargetPower(4800); r.pass_(); assert len(cmds(m.providerOrder.provider("TeslaBLE"))) == 1   # lifted already this session: no new command

def test_amps_use_the_cars_request_not_the_pilot():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); pt, s = point(m, v, 1); pt.setTargetPower(2400); r.pass_()
    c.t += 30; v.observe("availableCurrent", 8, "TeslaBLE")                                      # the TWC's own offer, read back from the car
    assert r.pass_() == 0 and m.desired.bounds(VIN).maxAmps is None and m.desired.settled(VIN, AMPS)
    c.t += 30; v.observe("chargeCurrentRequest", 16, "TeslaMateVehicle")                         # the user lowered the car's setting
    assert r.pass_() == 0 and m.desired.bounds(VIN).maxAmps == 16

def test_mode_3_layers_below_the_floor_and_holds_the_twc_at_its_floor():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargeCurrentRequest", 32, "TeslaBLE"); pt, s = point(m, v, 3)
    pt.setTargetPower(4 * 240); assert s._evseTargetAmps == s.minAmps and m.desired.get(VIN, AMPS).value == 4 and not m.desired.get(VIN, AMPS).lift
    r.pass_(); assert cmds(m.providerOrder.provider("TeslaBLE")) == ["setAmps"] and m.providerOrder.provider("TeslaBLE").calls[-1] == ("setAmps", VIN, 4)
    pt.setTargetPower(10 * 240); assert s._evseTargetAmps == 10 and m.desired.get(VIN, AMPS).lift              # back in range: the car (at 4) would cap, so lift
    v.observe("chargeCurrentRequest", 32, "TeslaBLE", at=c() + 1); pt.setTargetPower(12 * 240); assert m.desired.get(VIN, AMPS).lift  # unchanged desire, no new command needed

def test_mode_2_car_carries_and_the_twc_offers_its_max():
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); pt, s = point(m, v, 2); pt.setTargetPower(10 * 240)
    assert s._evseTargetAmps == s.maxOfferAmps and m.desired.get(VIN, AMPS).value == 10
    r.pass_(); assert m.providerOrder.provider("FleetAPI").calls == [("setAmps", VIN, 10)]   # TWC not an amps path under mode 2: Fleet allowed, no read first

def test_twc_only_point_keeps_the_heartbeat_path_under_mode_2():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); pt, s = point(m, v, 2, car=False); pt.setTargetPower(10 * 240)
    assert s._evseTargetAmps == 10 and not s.pointOwnsAmps and m.desired.get(VIN, AMPS) is None   # the heartbeat's mode-2 branch sets the car's amps from the target
    s._queueChargeRate(10); assert m.desired.get(VIN, AMPS).value == 10 and m.desired.get(VIN, AMPS).by == "heartbeat"

def test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member():
    from tests.unit.gen2_helpers import drive as heartbeat
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); pt, s = point(m, v, 3); pt.setTargetPower(4 * 240)
    heartbeat(m, s, amps_actual=4.0); assert m.desired.get(VIN, AMPS).value == 4 and m.desired.get(VIN, AMPS).by == "distributor"   # no "heartbeat" write, no lift
    s.pointOwnsAmps = False; heartbeat(m, s, amps_actual=4.0); assert m.desired.get(VIN, AMPS).by == "lift"             # the TWC branch's raise, now unguarded

def test_fleet_never_sets_a_rate_the_twc_covers_but_carries_a_lift():
    m, r, v, c = setup(fleet(O.Outcome(O.DONE), O.Outcome(O.DONE))); f = m.providerOrder.provider("FleetAPI"); pt, s = point(m, v, 3)
    pt.setTargetPower(10 * 240); r.pass_(); assert f.calls == []                                 # 10 A: TWC covers it; chargeCurrentRequest unknown → no lift under mode 3
    v.observe("chargeCurrentRequest", 6, "TeslaAPI"); pt.setTargetPower(10 * 240); r.pass_(); assert f.calls == [("setAmps", VIN, 32)]
    pt.setTargetPower(4 * 240); r.pass_(); assert f.calls[-1] == ("setAmps", VIN, 4)

def test_user_lowered_amps_become_a_session_bound():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); pt, s = point(m, v, 2); pt.setTargetPower(20 * 240); r.pass_()
    c.t += 30; v.observe("chargeCurrentRequest", 16, "TeslaMateVehicle")
    assert r.pass_() == 0 and m.desired.bounds(VIN).maxAmps == 16 and pt.maxPower == 16 * 240
    pt.setTargetPower(20 * 240); assert m.desired.get(VIN, AMPS).value == 16

def test_failed_rate_is_retried_after_60s_and_an_unchanged_rate_is_never_resent():
    m, r, v, c = setup(fleet(O.Outcome(O.ERROR, "500"), O.Outcome(O.DONE))); f = m.providerOrder.provider("FleetAPI"); e = VehicleEndpoint(v, m.providerOrder, m)
    e.setTargetPower(10 * 240); r.pass_(); c.t += 30; r.pass_(); assert len(f.calls) == 1
    c.t += RETRY[AMPS]; r.pass_(); assert len(f.calls) == 2
    c.t += 3600; e.setTargetPower(10 * 240); r.pass_(); assert len(f.calls) == 2

def test_new_amps_values_do_not_reset_a_paid_backoff():                     # S3, paid repeat counted
    from TWCManager.Vehicle.Reconcile.Reconciler import BACKOFF_START
    m, r, v, c = setup(fleet(O.Outcome(O.ERROR, "500"))); f = m.providerOrder.provider("FleetAPI"); e = VehicleEndpoint(v, m.providerOrder, m)
    e.setTargetPower(10 * 240); r.pass_(); c.t += RETRY[AMPS]; r.pass_(); c.t += RETRY[AMPS]; r.pass_()                # attempts() == 2, then backoff
    assert len(f.calls) == 2 and m.desired.record(VIN, AMPS).backoffUntil > c()
    for amps in (11, 12, 13, 14, 15): e.setTargetPower(amps * 240); c.t += 30; r.pass_()
    assert len(f.calls) == 2                                                                                             # five new values inside the backoff: no paid attempt
    c.t += BACKOFF_START; r.pass_(); assert len(f.calls) == 3 and f.calls[-1] == ("setAmps", VIN, 15)                   # the backoff, not the change, lets the next one out

def test_legacy_heartbeat_path_sets_desired_and_the_lift_once():
    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = m.getSlaveTWCs()[0]; s.currentVIN = VIN
    s._queueChargeRate(7); assert m.desired.get(VIN, AMPS).value == 7 and m.desired.get(VIN, AMPS).by == "heartbeat"
    s._requestVehicleRateRaise(); assert m.desired.get(VIN, AMPS).lift and not s.vehicleRateRaised
    r.pass_(); assert s.vehicleRateRaised; s._resetVehicleRateRaised(); assert not s.vehicleRateRaised and m.desired.get(VIN, AMPS) is None
```
Update `test_charging_points.py::test_target_goes_to_the_local_member_only_when_present` (mode 1 with a vehicle member now also sets a lift desire: assert `m.desired.get(...)` instead of `car.setTargetPower.assert_not_called()`) and `test_vehicle_endpoint.py::test_set_target_power_queues_on_change_or_after_refresh` → `test_set_target_power_sets_desired_amps` (`desired.get(VIN1, AMPS).value == 10`, `0` sets nothing). Add one `chargeCurrentRequest` observation case to the TeslaAPI and telemetry registry tests.

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: carriers` / `KeyError: chargeCurrentRequest`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager
git add lib/TWCManager tests/unit
git commit -m "Amps as desired state with layered actuators: the point owns the car's rate, the TWC holds its floor below range"
```

### Task 10: Retire the legacy command paths: `VehiclePriority`, `VehicleCommandQueue`, the module command methods, `targetAmps`

After Tasks 7–9 nothing produces a `charge`, `applyChargeLimit`, `setChargeRate` or `setAmps` task, and nothing walks the façade; `checkCharge` is the last façade call.

**Files:**
- Delete: `lib/TWCManager/Vehicle/VehiclePriority.py`, `lib/TWCManager/VehicleCommandQueue.py`, `tests/unit/test_vehicle_priority.py`, `test_vehicle_priority_returns.py`, `test_vehicle_command_queue.py`, `test_targeted_charge_limit.py`, `test_teslaapi_charge_vin.py`, `test_teslaapi_chargerate.py`, `test_own_write_stamps.py`.
- Modify: `lib/TWCManager/TWCMaster.py` (`VEHICLE_COMMANDS`, the `queue_background_task` routing, `queue_vehicle_command`, `_resolveVehicleCommandModule`, `calculateModulePriority`, `getModuleByPriority`, the `"priority"` key in `registerModule`, `getNormalChargeLimit`/`saveNormalChargeLimit`/`removeNormalChargeLimit` wrappers, `self.vehicleCommandQueue`), `lib/TWCManager/TWCManager.py` (`get_vehicle_module`, the `vehicleModule` lookup; `checkCharge` → `for mod in master.getModulesByType("Vehicle")` whose providers are not suppressed for `READ_CHARGE` (`api_only` keeps BLE out, as the façade walk did): `getattr(mod["ref"], "updateChargeAtHome", lambda: None)()` — the reads every module did when walked, now called once each), the comment mentions of `VehiclePriority` in `lib/TWCManager/Vehicle/Providers/Provider.py`, `HomeAssistantProvider.py` and `TeslaAPI.py` (reworded), the `VehiclePriority` entry in the module-load list, `lib/TWCManager/Vehicle/TeslaAPI.py` (delete `car_api_charge`, `applyChargeLimit`, `_unavailableResult`, `setChargeRate`, `_chargeRateAccepted`, `_recordChargeRate`, `CHARGE_RATE_RESEND_AFTER`, `wakeVehicle`, `carApiLastChargeLimitApplyTime`, `getLastStartOrStopChargeTime`/`carApiLastStartOrStopChargeTime`, `CarApiVehicle.apply_charge_limit`, `.stopAskingToStartCharging`, `.lastLimitAttemptTime`, `.lastChargeRateSent`, `.lastChargeRateSentTime`, and the `charge`/`applyLimit`/`vin` wake loop inside `car_api_available` (the block after the vehicle-list check; what remains is the token/list check); `refuseCommandIfReadOnly` stays for the Storm Watch/debug callers if any remain, else goes), `lib/TWCManager/Vehicle/TeslaBLE.py` (delete `car_api_charge`, `applyChargeLimit`, `setChargeRate`, `startCharging`, `stopCharging`, `_stopAskingToStartCharging`, `_allVehicleTargets` if unused; keep `wakeVehicle` (the read source uses it), `commandOutcome`, `_scheduleBlocksStart`), `lib/TWCManager/Vehicle/HomeAssistant.py` (delete `car_api_charge`, `applyChargeLimit`, `setChargeRate`, `carApiLastStartOrStopChargeTime`, `_vehiclesFor` if unused), `lib/TWCManager/Vehicle/Providers/Provider.py` (`module`/`vehicleAttachment` attributes stay: `registerProviders` and the lanes use `module is None` for TWC providers), `lib/TWCManager/Control/HTTPControl.py` (any remaining `getModuleByName("VehiclePriority")`), `lib/TWCManager/Control/themes/Default/*.j2` (nothing references the façade; verify), `docs/Settings.md`, `CHANGELOG.md`, `tests/unit/test_teslaapi_readonly_gate.py` (the `TestVehiclePriority…` classes go; the read-only read cases stay), `test_twcmaster.py`, `test_twcslave.py`, `test_vehicle_endpoint.py`, `test_registry_callers.py`, `test_provider_registration.py` (`test_register_providers_collects_every_vehicle_module_in_rank_order`: no `VehiclePriority` module entry), `test_sigterm_shutdown.py` (drain assertions move to `lanes.drain`).
- Test: `tests/unit/test_no_legacy_command_paths.py`.

**Interfaces:**
- Produces (`TWCMaster`): `queue_background_task` no longer special-cases vehicle commands; `getNormalChargeLimit`/`saveNormalChargeLimit`/`removeNormalChargeLimit` deleted (callers use `heldLimits`); `registerModule` records no `"priority"`.
- Produces (`TWCManager.py` shutdown order): `Policy.stop()` → `queue saveSettings` → `master.reconciler.stop()` → `master.lanes.drain(timeout=60)` → background-queue wait as today.
- Produces (`docs/Settings.md`): "Stop Charging Method" rewritten: the vehicle command is always tried first (BLE, then the cloud after the free providers have timed out), "Stop Responding to Slaves"/"Send stop command" are used only after the vehicle command has failed for a minute, or at once for a car no vehicle provider can command (a non-Tesla car); with either of them selected the Fleet API and Home Assistant are never asked to stop a car. "Charge Rate Control" paragraph: mode 1 TWC carries the rate and the car is raised to its maximum once per plug session; mode 2 the car carries it; mode 3 the TWC carries rates it can offer and holds its minimum while the car carries lower rates. A "How commands are delivered" paragraph: desired state, one attempt in flight per car and aspect, the 5 min / 60 s paid fallback, backoff 10 min doubling to an hour, user changes adopted (limit until the next policy change or plug event; charge rate and start/stop for the plug session).
- Produces (`CHANGELOG.md` `* Architecture`): `(@MikeBishop) - Vehicle commands are no longer fired at a car: policy, the power distributor and the TWC heartbeat set the charge limit, charging on/off and amps each car should have, and one reconciler delivers them through the provider order with one attempt in flight per car, classified outcomes, a paid (Fleet API, Home Assistant) fallback only after the free providers have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and backoff. A limit or charge rate changed in the car or the Tesla app is adopted, not undone. Removes VehiclePriority, the vehicle command queue, the per-module charge-limit copies and the -1 restore sentinel; held charge limits move from chargeLimits to heldLimits in settings.json (migrated on first start; downgrading afterwards loses them)`. `* Bugfixes`: `(@MikeBishop) - A failed BLE command no longer falls through to a billed Fleet API command at once (#698 for lowering, the 2026-10-11 stray command); Home Assistant can now restore a car's normal limit; a rejected Fleet API token stops being chosen for commands (#689); charge limit lowers never wake the car over BLE (#698); a BLE wake that fails before a command still lets the command go out, as before, while a failed Fleet wake ends the attempt`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_no_legacy_command_paths.py
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def grep(pattern): return subprocess.run(["git", "grep", "-l", pattern, "--", "lib/TWCManager"], capture_output=True, text=True, cwd=str(ROOT)).stdout.split()

def test_facade_queue_and_module_command_methods_are_gone():
    assert grep("VehiclePriority\\|VehicleCommandQueue\\|queue_vehicle_command\\|calculateModulePriority\\|getModuleByPriority\\|targetAmps") == []
    assert grep("def car_api_charge\\|def applyChargeLimit\\|def setChargeRate\\|def apply_charge_limit\\|stopAskingToStartCharging\\|getNormalChargeLimit\\|saveNormalChargeLimit") == []
    assert grep("def dispatch\\|def orderKey") == []
```

- [ ] **Step 2: Run to verify failure** → FAIL (files listed).

- [ ] **Step 3: Delete and rewrite** per Files; move the still-meaningful assertions: `test_own_write_stamps.py`'s stamp cases are covered by `test_lanes.py::test_inline_lane_runs_reports_and_stamps_the_write` (add one case per provider there: BLE, Fleet, HA via `ScriptedProvider` is enough since the lane stamps); `test_targeted_charge_limit.py`'s "touches only that car" is `test_limit_wiring.py::test_policy_limit_sets_desired_for_present_cars_and_none_restores`; `test_teslaapi_charge_vin.py`'s "a VIN stop commands only that vehicle" becomes a `test_provider_outcomes_cloud.py` case asserting one `charge_stop` POST with that VIN in the URL.

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager
git add -A lib/TWCManager tests/unit docs/Settings.md CHANGELOG.md
git commit -m "Retire VehiclePriority, the vehicle command queue and the module command methods: the reconciler delivers every vehicle command"
```

### Task 11: Old-vs-new behaviour table with real objects, paid-call sweep, live check

**Files:**
- Test: `tests/unit/test_command_path_parity.py`.
- Modify: `.superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md` (this table gains a "Measured" column filled from the passing tests).

**Interfaces:**
- Consumes: real `TWCMaster` (`tests.unit.test_gen2twc_provider.make`), real `TeslaAPI` (`tests.unit.test_carapivehicle_registry.api_with_registry` + `requests_mock` matching every `/command/`, `/wake_up`, `/vehicle_data`, `/vehicles` URL), real `TeslaBLE` (`tests.unit.test_teslable_pairing_status.make`, `sendCommand` patched to return `None` for "radio down" and a success string otherwise), real `HomeAssistant` (`make_ha`), real `Lanes(inline=True)`, real `VehicleReconciler` driven by `pass_()` with a `Clock`.
- Produces: one test per row of the table below; each asserts the provider calls and the paid-request counts (`vehicle_data`, `wake_up`, `/command/`) for a scripted sequence of time steps.

| # | Install / setting | Trigger | Phase 2 (façade) | Phase 3 | Paid calls Phase 2 → 3 | Test |
|---|---|---|---|---|---|---|
| 1 | Pure Gen2, no Vehicle module | heartbeat stop/start | `VehiclePriority` with no modules → `False` | no candidates; desired set for the anonymous car, nothing attempted, DEBUG only (Task 6 step 7) | 0 → 0 | `test_pure_gen2_sets_desired_and_attempts_nothing` |
| 2 | BLE-only (claimed, no location) | policy limit 50 then lower to 40 | `TeslaBLE.applyChargeLimit` to every keyed VIN, wake first each time | BLE `setChargeLimit` to present claimed cars; no wake on a lower, wake on a raise | 0 → 0 | `test_ble_only_limits_never_wake_to_lower` |
| 3 | Owner-only token | policy limit, stop | `available(SET_CHARGE_LIMIT)` False → nothing | Fleet not ready → no candidates | 0 → 0 | `test_owner_only_never_commands` |
| 4 | Fleet-only, no BLE, Owner slot empty | policy limit raise 50→80 on a sleeping car | free `vehicles/{vin}` check, `vehicle_data` read once awake, wake with hold, `set_charge_limit` | free online checks (cached 120 s), one `wake_up` ($0.02) when due, one `vehicle_data` ($0.002) once awake, one `set_charge_limit` ($0.001); nothing after our stamp settles it | 3 → 3 | `test_fleet_only_raise_costs_the_same` |
| 5 | BLE + Fleet, radio down | policy limit | 3 BLE attempts then Fleet at once (the 2026-10-11 stray) | Fleet after 300 s; once | 1 → 1 (later) | `test_ble_plus_fleet_waits_five_minutes` |
| 6 | BLE + Fleet, radio down | heartbeat stop | 3 BLE then Fleet at once | Fleet after 60 s; once | 1 → 1 (later) | `test_ble_plus_fleet_stop_waits_a_minute` |
| 7 | TeslaMate + BLE | user sets 80 in the app while we hold 50 | TeslaMate value ignored for apply; BLE re-sends 50 on the next policy pass | adopted; outside 80; nothing sent | 0 → 0 | `test_telemetry_change_is_adopted` |
| 8 | Fleet + HA | policy limit, Fleet fails | Fleet 2 attempts, HA held to 60 s | Fleet 2 attempts 300 s apart, HA after `PAID_AFTER`; never both in one pass | ≤2+1 → ≤2+1 | `test_fleet_then_ha_never_in_one_pass` |
| 9 | Gen3 two units | stop one car | no caller | `NO_INDIVIDUAL_STOP` → BLE/Fleet; single unit → Gen3 local stop | 0 → 0 | `test_gen3_stop_routes` |
| 10 | `chargeStopMode` 2 + BLE + Fleet | heartbeat stop | `stopRespondingToSlaves` at once, no vehicle command | car with a BLE key: BLE first, disruptive after 60 s; car without one: disruptive at once; Fleet never | 0 → 0 | `test_stop_mode_2_ble_then_disruptive` (both cars) |
| 11 | `chargeRateControl` 3, Fleet-only car on a TWC | 4 A then 10 A | 4 A: Fleet `set_charging_amps` (×2, low-amps repeat); 10 A: TWC only | same | 2 → 2 | `test_mode_3_fleet_only_below_floor` |
| 12 | `chargeRateControl` 1, Fleet-only car on a TWC | plug-in | raise to `wiringMaxAmps` over Fleet once per session | lift once per session, only when `chargeCurrentRequest` is unknown or below the max; no `vehicle_data` before it | 1 → ≤1 | `test_mode_1_lift_once_per_session` |
| 13 | Fleet, token rejected (401) | policy limit | 401 body truthy → counted as success; chosen again next time | `REFUSED`; slot cleared; no further Fleet request | n → 1 | `test_fleet_401_retires` |
| 14 | HA-only, two cars | heartbeat stop for one | HA stops that car | same, via `switch.turn_off` for that car only; 10 s per-car limit | 1 → 1 | `test_ha_only_targeted_stop` |
| 15 | Any | SIGTERM with a pending stop | `drain_high_priority(60)` | `lanes.drain(60)` runs the stop, drops the rest | — | covered by `test_lanes.py::test_drain_runs_pending_stops_only` |

- [ ] **Step 1: Write the failing tests** — one function per row with the row's name; each counts `requests_mock.request_history` by URL fragment and asserts the "Phase 3" column's calls. Row 4 example:

```python
def test_fleet_only_raise_costs_the_same(requests_mock):
    m, r, api, reg, c = fleet_install(requests_mock, asleep=True)   # helper in this file: real TWCMaster + TeslaAPI with a Fleet token, car listed, at home; the store, lanes, reconciler, the Fleet provider's clock and `api.now` all run on c, so is_awake's 120 s cache follows it without touching the process-wide `time.time`; `api.wakeDelayMins = 0` so the first wake is due at once (today's 3 min pre-wake hold is covered by Task 5's test)
    m.heldLimits.set(VIN, 90, 50); reg.get(VIN).observe("chargeLimit", 50, "TeslaAPI", at=c() - 600)
    m.setPolicyLimit(80, transition=True); r.pass_()
    assert counts(requests_mock) == {"vehicles/" + VIN: 1, "vehicle_data": 0, "wake_up": 1, "set_charge_limit": 0}      # asleep: the read source reads nothing (one free check, cached for the wake's own check), the wake is sent, the command waits
    wake_online(requests_mock); c.t += 1801; r.pass_()
    assert counts(requests_mock) == {"vehicles/" + VIN: 2, "vehicle_data": 1, "wake_up": 1, "set_charge_limit": 1}      # online now: one paid read, no second wake, one command
    for _ in range(5): c.t += 600; r.pass_()
    assert counts(requests_mock) == {"vehicles/" + VIN: 2, "vehicle_data": 1, "wake_up": 1, "set_charge_limit": 1}      # settled by our stamp: nothing more
```

- [ ] **Step 2: Run to verify failure** → the helpers do not exist yet (FAIL with `NameError`/`ImportError`).

- [ ] **Step 3: Implement the helpers and tests**; fill the "Measured" column of the table above in this plan from the passing tests' counts.

- [ ] **Step 4: Run the full suite** → PASS (baseline 1326 minus the deleted files plus this phase's tests; record the count in the ledger).

- [ ] **Step 5: Commit**

```bash
black tests/unit/test_command_path_parity.py
git add tests/unit/test_command_path_parity.py .superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md
git commit -m "Pin the old-vs-new command behaviour per install type with real objects and paid-call counts"
```

- [ ] **Step 6: Live check on the user's box — approved, including the rfkill window, but scheduled with the user (not run by the implementer; the user is away and sets the time)**

When the user gives the go-ahead: deploy `vehicle-model/phase3` to `twcmanager`, restart, and confirm in the log over at least one policy transition and one plug cycle: boot shows `Providers: ...` and no `Main loop stalled` beyond the boot one; a policy limit change produces exactly one `setChargeLimit` INFO via `TeslaBLE` and no Fleet request; a limit set in the app is logged as `set elsewhere to N%; adopted` and not undone; the car page's held limit reads from `heldLimits`; with Bluetooth disabled on the host (`rfkill block bluetooth`) a limit change produces BLE `unreachable` outcomes for 5 minutes and then one Fleet `set_charge_limit`, after which `rfkill unblock`; unplug → `endSession` logged, held limit restored on departure per today's schedule; zero `wake_up` requests except for raises. Record findings in the PR description, then roll the box back per the ledger's rollback note.

---

## Inventory rows this phase closes

- **A5** (wake gating is the attempt's `wake` flag plus `TeslaAPI.wakeDue`; reads cascade through the lane's own sources; `applyChargeLimit`'s read-then-command loop is gone), **A11** (one restore path: desired = outside value; HA restores through `number.set_value`), **A12** (one charge-limit rule in `Reconciler.allowWake`/`Rules.decideChargeLimit`; BLE never wakes to lower), **A13** (the broader charge/limit pass: desired state + outcomes), **A14** (outcome-driven stop/resume replaces the queue-time latch), **A19** (every command is targeted by registry key; a VIN-less TWC targets the present set, never wakes another car), **A21** (401/403/412 on a command retire the slot; a 412 Owner token stays paused until it changes). Also closed: `#689`, `#698`, the 2026-10-11 stray-command cause (no immediate paid fall-through), the 09:17 return race (`believed` + restore live read), ledger items listed below.

## Ledger carries (every Phase 3 line in the Phase 1/2 ledgers)

| Carry | Where it lands |
|---|---|
| Layered actuators; mode-3 "TWC holds its minimum, car goes lower" (Phase 2 Task 3 ruling, Decision 11, final-review carry) | Task 9 |
| `NO_INDIVIDUAL_STOP`: BLE/Fleet for a per-unit Gen3 stop | Task 8 |
| Gen3 zero-headroom stop unverified (G4) | Task 4 keeps it local-tier; Task 11 row 9; still hardware-unverified (no Gen3 on the box) |
| Gen2 disruptive `STOP_CHARGING` (tier 3, `chargeStopMode` 2/3) gets its caller; `stopCarsCharging`/`startCarsCharging` modes 2/3 | Tasks 4, 8 |
| Fleet `RateLimit` declaration unenforced | Task 3 (`Lane.allows`, per provider/capability/VIN) |
| 60 s retry backoff for a failed queued `setAmps` (was 600 s) | Task 9 (`RETRY[AMPS] = 60`; the 600 s unchanged-rate resend is replaced by `believed`) |
| Stop retrying an Owner token Tesla keeps refusing (412) | Task 5 (`pause(latch=True)`) |
| Remove `targetAmps` | Task 10 |
| HA 10 s rate limit shared across cars (m-2) | Task 5 (`RateLimit(1, 10)` per car) |
| 09:17 return-race rules: own-write stamps beat older telemetry; restore forces a live read | Task 2 (`believed`, `read(force=True)`), Task 6 (`needsLiveRead` → a forced read past a live feed) |
| Final-review M1 (`wantsToCharge` local-first) | already in the Phase 2 head (`ChargingPoint._preferLocal`); nothing to do |
| Final-review M3 (`ChargingPoint.start/stopCharging`, `EVSEInstance.provider` uncalled; `dispatch` with one caller) | Task 8 gives `ChargingPoint.start/stopCharging` their caller; Task 10 deletes `dispatch` with the façade; `EVSEInstance.provider` is read by Phase 6's panels — left |
| Final-review M4 (`Suppressions.explicit()` re-parses per call) | ruled out: still cheap; not in scope |
| Final-review M5 (`_slaveForKey` raw key) | Task 4 |
| Task 10 m6 (callback-driven short backoff on a failed send) | superseded by Task 9's record |
| Task 9 rereview-2 "Phase 3's per-provider HA commands could keep the stamp per car" | Task 3 (the lane stamps per car) |
| Phase 1 Task 14 M4 (HA `setChargeRate` stamp) | moot: the lane stamps; HA's method is deleted in Task 10 |
| Phase 1 Task 9 carry "Forget must also drop the CarApiVehicle" | Phase 6 (unchanged) |
| Phase 1 Task 17 "Pair still synchronous on the HTTP thread under `_bleLock`" | ruled out of Phase 3: pairing is not a vehicle command; Phase 6 (the pairing page) owns it |
| Phase 2 Task 11 Phase 5 carries (mode-2 `lastVIN` rate to a departed car; Gen2-00 sleeping-car paid path) | Phase 5 (presence attribution); `targetsFor` keeps today's reach |
| Phase 2 Task 9 M5 (debug dropdown lists TeslaAPI cars only) | Phase 6 |
| `#660` raise over Fleet for a Fleet-only car on a TWC (Phase 2 carry: decide whether $0.001/session is worth it) | Task 9: kept as the `lift`, and only sent when `chargeCurrentRequest` is unknown or below the max (Decision 15) |
| `apiDebugInterface` through the same path | Task 3 (`debugCommand` → one-shot on a lane) |

## Decisions made in this plan

1. Package `lib/TWCManager/Vehicle/Reconcile/` with one module per concern (outcomes, desired store, held limits, rules, lanes, reconciler, targets) — the spec leaves layout to the builder; mirrors Phase 2's `Providers/` package.
2. Provider command methods return an `Outcome` NamedTuple; the lane converts bad returns and exceptions to `ERROR` and warns once — Phase 2's C1 (None-as-success) cannot recur because truthiness is never consulted. `ProviderOrder.dispatch` stays until Task 10 (the façade's `setAmps` still calls it) and reads outcomes by `kind in SETTLED` from Task 4.
3. Three lanes: `ble` (thread), `cloud` (thread; Owner, Fleet, HA, telemetry), `local` (inline; TWC providers do no I/O) — the spec's "BLE serial; cloud separate"; HA shares the cloud lane because it is reached only after Fleet and never concurrently with it for the same car.
4. The reconciler is its own daemon thread with a 1 s bounded wait, woken by desired changes and outcomes; Phase 4 folds `pass_()` into the control tick — the spec leaves scheduling to the builder and Phase 4 owns the tick. It plans every aspect of a car before submitting any attempt, so one pass sees its own probe or limit attempt.
5. One clock domain: the desired store, lanes, reconciler, channel health and attempt stamps all use `time.time()`, the registry's clock; `time.monotonic` only inside the lane's rate-limit window — a start gap or a settled check compared across domains would never hold.
6. Read-before-write runs on the lane through only that lane's read sources (`Vehicle.read(sources=)`), so a cloud attempt never waits on the BLE radio — spec: a BLE timeout for car A must not hold a Fleet command for car B. A restore that telemetry cannot settle reads with `force=True`, past a live feed's age-0 rule.
7. "Known" is `Vehicle.believed(field, exclude=)`: the newer of the latest vehicle-sourced observation and our own write — `presence/2`'s `latestChargeLimit` rule on the registry, with TWC-sourced observations left out of a car's own state; a successful write satisfies desired until a newer read differs, which removes the 600 s unchanged-rate resend. For `CHARGING` on a car no vehicle source describes, TWC current stands in for satisfaction only (never adoption), so a disruptive stop is confirmed by the bus going quiet and re-asserted when it resumes.
8. Adoption: a vehicle-sourced observation newer than both our own write and the current desire, disagreeing with what we wrote in the stamp's own domain (charging-like vs stopped-like for `CHARGING`), is the user's change; a read that merely confirms our write never adopts, whatever desired has since become; TWC-sourced observations never adopt; a resume after our own disruptive stop and a stop while we offered the point nothing are hands off, not adoption; slow aspects replace desired until a `decision=True` set (policy transition, arrival/departure), fast aspects become `SessionBounds` (`wantsCharge`, `userStopped`, `maxAmps`) cleared when the plug session ends (`twcVin` gone, a vehicle-sourced `pluggedIn` False, or the endpoint's own session end).
9. Under `chargeStopMode` 2/3 billed stop providers are suppressed, so a mode-2/3 user keeps paying nothing for stops; the disruptive stop waits 60 s for a BLE stop only when TeslaBLE is ready for that car (a non-refused claim with a key) and is sent at once otherwise (user ruling): today's immediate stop is kept wherever BLE is not set up. The mode-3 stop is published on the slave (`stopRequested`) and sent by `send_master_heartbeat`: no RS-485 write off the serial thread. The disruptive stop is never stamped.
10. `PAID_AFTER`: 300 s for charge limits (today's restore rule), 60 s for start/stop and amps; `RETRY` 300/60/60 s; a paid provider gets at most `attempts()` tries per round, rounds backing off 600 s doubling to 3600 s; a car with no free candidate at all goes to its paid provider at once (today's Fleet-only behaviour, no new paid path).
11. Channel health is per car and free provider, shared by every aspect (user ruling): `failingSince` is set by the first failed attempt on any aspect (or a `bleReach` False observation) and cleared by any free success (or `bleReach` True); an aspect goes paid as soon as the channel has been failing for its own `PAID_AFTER`, counted from that first failure, so a later change never waits out a fresh window. Health governs only when money may be spent: a failing free provider is still retried at the aspect's `RETRY` cadence, bounded by `attempts()` and backoff, so a BLE-only install recovers on its own; once paid is eligible the paid pick takes the aspect's one in-flight slot and the free retry continues on passes where no paid attempt is due.
12. Stale-failure probe (user ruling): when an aspect would go paid because BLE is marked failing but the car's last BLE attempt is older than `PROBE_AFTER` (600 s: twice the longest `PAID_AFTER`, so an aspect that has just reached its own window goes paid without a probe, while a channel untried for ten minutes gets one ping before money is spent), the BLE lane first runs one tesla-control `body-controller-state` query — the VCSEC answers it while infotainment sleeps, so it proves the car answers without waking it, unlike `state charge` (needs infotainment) or the Phase 1 bluetoothctl range scan (sees the advertisement only, ~8 s on the background thread); it is sent without key proof (`noteProof=False`: an unauthenticated VCSEC answer must not mark a key paired); one probe per car, bounded by `commandTimeout`, no retries; success clears `failingSince` and the attempt goes over BLE, failure refreshes `lastFailureAt` and the aspect goes paid at once.
13. Wake rule: limits wake only for a raise (desired > known; never to lower, never when unknown, **never for a restore** — today's departure restore waits for the car and a vanished car backs off hourly without a wake, per the spec), a start wakes, a stop never, amps wake only through a free provider. A Fleet wake is preceded by the free `vehicles/{vin}` online check (today's `vehicle.ready()`) and obeys today's `wakeDue` hold; a failed BLE wake still lets the command go out (today's behaviour), a failed Fleet wake ends the attempt.
14. A rules-settled charge-limit attempt reconciles the desire: a restore with nothing to restore clears it (at plan time when nothing is held, on the lane otherwise); an apply settles only as "already at N%", which the plan-time `satisfied` check ends on its own, so it is left unadopted (`limitOverride`'s later lowering must still apply) — desired and known never stay apart with nothing to send.
15. The `#660` raise is kept as a per-session `lift` that bypasses the local-amps rule, sent only when the car's `chargeCurrentRequest` is unknown or below the maximum — at most today's $0.001 per session, often less; AMPS attempts never read first (`maxAge None`), so no `vehicle_data` precedes a Fleet rate, as today.
16. The AMPS aspect reads and stamps `chargeCurrentRequest` (the car's own setting, reported by Fleet `vehicle_data`, BLE `state charge` and Fleet Telemetry), never `availableCurrent` (the charger's pilot, which would adopt the TWC's own offer as a user bound); until a source reports it the own-write stamp alone decides.
17. `chargeRateControl` maps onto the layered rule as which members may carry a rate: 1 = TWC (plus the lift), 2 = car (TWC at its max), 3 = both (TWC at its floor below range) — applied only when the point has a vehicle member; a TWC-only point (BLE-only, pure Gen2, HA-only) keeps the Phase 2 whole-target path and the heartbeat's branches, which write desired amps instead of queueing. Each car's AMPS aspect has one writer per cycle: the point when it has a vehicle member (`Gen2TWC.pointOwnsAmps`), the heartbeat otherwise.
18. Mode-3 hysteresis: coming back into the TWC's range, the car is lifted only when its known `chargeCurrentRequest` is below the new target — the spec leaves hysteresis to the builder; undershoot is the safe direction.
19. A distributor stop is ignored for a car the user started this session (`bounds.wantsCharge`): the car is admitted and the TWC's own offer still bounds its power (the spec's "treated as wanting charge") — except a `forced` stop, which the heartbeat sends when the policy's **unclamped** request (`policyAmpsRequested`, recorded before the `wiringMaxAmpsAllTWCs` clamp; 0 until the first policy pass) would have allowed the car its minimum, so the wiring or a controller clamp is what binds (computed from the heartbeat's own car count, never a second `num_cars_charging_now()`); a user stop in the app (`userStopped`) holds off distributor starts for the session the same way, but only when the point was offering power at the time (`noteOffering`) — a car that stops because we offered nothing is our doing, and while a point reports that it offers nothing no start (and no wake) is planned at all.
20. A mode-2 "start" (answer slaves again) is offered by the Gen2 provider only when the last delivered stop was its own (`lastStopProvider`); a stop delivered over BLE or the cloud is undone over the same channel — otherwise a BLE-stopped car would never restart.
21. The heartbeat passes `vehicleKey` (a VIN or an `anon:` key) to stop, start and cancel, and `targetsFor` resolves anonymous keys, so a non-Tesla or VIN-less car is stopped under modes 2/3 as today; `cancelStopCarsCharging` cancels pending stops only, never a start.
22. Every lane entry reports exactly once: a replaced, dropped, cancelled or drained entry reports `Outcome(ERROR, "replaced"|"dropped"|"cancelled")`, which the reconciler uses only to clear `inFlight` (no health, no `tried`); probes and one-shots have their own coalescing keys.
23. "Present" until Phase 5 (`Targets.presentVehicles`): on a point, or a TeslaAPI car `atHome`, or an HA car `at_home`, or a BLE-claimed car with no other evidence — today's reach of each module's broadcast, in one place, replaced wholesale by the presence port; anonymous cars on a point are targets for `CHARGING` only; a vehicle with no candidate for the capability gets no desired state (spec: only managed vehicles get vehicle-command desired state) and a zero-candidate round logs at DEBUG.
24. Held limits move to `settings["heldLimits"]` (`{VIN: {"outside", "held"}}`, `held` null when none) with a one-time migration of `chargeLimits` (tuples, ints, `-1`; numeric-ID keys persisted as `id:<n>` until TeslaAPI binds the car) — removes the sentinel from storage and logic without losing a held limit; downgrade loses held limits (CHANGELOG); the page keeps "N% (restored)".
25. The charge-limit rules are ported verbatim from `presence/2` with `held is None` ⇔ nothing saved and `held.held is None` ⇔ `-1`, and the original test table unchanged; the "nothing to restore" case is settled at plan time.
26. 412 on an Owner read latches the slot paused until the token changes; a 401 on a Fleet command clears the slot, a 403 records the refused purpose so `usable("command")` is False until a new token — the ledger's "stop retrying an Owner token Tesla keeps refusing" and #689.
27. Rate limits are enforced per `(provider, capability, VIN)` in the lane; Fleet keeps `RateLimit(50, 60)`, HA gains `RateLimit(1, 10)` on start/stop — Tesla's limit is per vehicle; HA's gate was per install. HA's REST call becomes `_post_service -> Outcome` so timeouts and 401/403 classify and no response body is logged.
28. The debug API submits a one-shot attempt to a lane and returns whether it was queued (its outcome is logged); it skips module-less providers (never a TWC target from the HTTP thread) and uses one provider with no fall-through — vehicle I/O leaves the HTTP thread; the page already said "sent".
29. The legacy module command methods, façade and queue are deleted in one late task after every producer writes desired state, so the suite stays green per task and the branch is never deployed mid-phase (Phase 2 ruling precedent); between Tasks 7 and 9 rate commands queue silently on the unstarted queue.
32. A settled desire is re-planned only on new evidence: a newer vehicle-sourced observation of the aspect's field (the heartbeat's `actualCurrent` counts only for a car no vehicle source has ever described, where it is the car's only state), a desired change (which clears the free providers' tries and a free-only backoff; a paid provider's tries and backoff persist until success or a session event, per the spec) or a session event; an outcome that left no stamp (a disruptive stop, a SATISFIED start/stop) is additionally held `RETRY[aspect]` after it settled — so a mode-3 relay stop goes out once per new reading at most once a minute, and a Fleet `not_charging` is never repeated on the same evidence. The Gen2 heartbeat publishes its `actualCurrent` into the registry (source `Gen2TWC`) so that evidence exists.
33. A lane report clears `inFlight` only for the attempt it names (`rec.inFlight is attempt`); a late report for a replaced entry never clears a newer attempt.
34. Present lists and `targetsFor` take the capability they serve; a vehicle with no candidate for it (an anonymous car on a TWC under `chargeStopMode` 1, an observed-tier car) gets no desired state. `HeldLimits.holding()`/`vins()` return VIN keys only.
35. `CarApiVehicle.is_awake(now=)` measures its 120 s cache against the caller's clock; TeslaAPI's own clock is one instance hook, `TeslaAPI.now`, which the Fleet provider's `clock` and the tests drive, so every Tesla-side stamp shares the reconciler's domain without patching the process-wide `time.time`.
30. `checkCharge` calls each loaded Vehicle module's `updateChargeAtHome()` once, skipping modules whose provider is suppressed for `READ_CHARGE` — what the façade walk did for a non-command method, without the façade.
31. A `disconnected` reason on a Fleet start is `UNSUPPORTED`, not a satisfied start, and a `SATISFIED` start/stop is never stamped: a start that did not happen must not be recorded as one.

## Questions for the user

None: the two earlier questions are ruled in the ledger (the disruptive-stop wait and the live check), and every pre-flight ruling could be applied as proposed without contradicting a user ruling.
