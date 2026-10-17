### Task 7: Slim the desired-state store

Under the user's decisions the store needs:
- desired values, with adoption for `CHARGE_LIMIT` only;
- a small per-aspect attempt record;
- one free-channel record per car;
- `lastStopProvider`.

Session bounds, per-provider channel health, the backoff ladder, the probe slot, `offering` and the charging adoption logic go.

**Files:**
- Modify: `lib/TWCManager/Vehicle/Reconcile/Desired.py`, `Reconcile/__init__.py`, `Reconcile/Outcome.py` (add `NOT_SENT`).
- Test: rewrite `tests/unit/test_outcome_desired.py`.

**Interfaces:**
- Produces (`Outcome.py`): `NOT_SENT = LANE_DETAILS | {"backoff", "wake held", "wake refused", "no command token", "not listed", "online check failed", "read"}`, plus any detail starting `"rules: "` (`isNotSent(outcome) -> bool` covers both; pre-flight L3). An outcome with one of these details made no request, so it is neither a paid call nor a sent command.
- Produces (`Desired.py`). Aspects, `FIELD_FOR`, `CAPABILITY_FOR` and `Attempt` are unchanged. `Desired(value, by, at, adopted=False, restore=False, lift=False)` (`forced` is gone).
- `class AttemptRecord`:
  - `inFlight`, `lastOutcome`, `lastOutcomeAt`, `lastProvider` as now.
  - `excluded: Dict[str, str]` (provider → kind).
  - `lastSentAt: float = 0` (any provider) and `lastFreeAt: float = 0` (a free provider).
  - `paidAt: Optional[float]`: the paid or disruptive request for the current desire.
  - `paidRetryDue: bool = False`: the last paid request failed (`ERROR`/`UNREACHABLE`, detail not in `NOT_SENT`) and its one blind retry is unused.
  - `settledAt: Optional[float]`.
  - `pendingSave: Any`.
  - `newDesire()`: drops UNSUPPORTED exclusions and keeps REFUSED ones (ledger L17 ruling); resets `lastFreeAt`, `paidAt`, `paidRetryDue` and `settledAt`.
  - `exclude(provider, kind)`; `summary()`.
- `class FreeChannel` (one per car, shared by every aspect; replaces `ChannelHealth`):
  - `failingSince: Optional[float]` and `lastAttemptAt: float = 0`.
  - `success(at)` sets `lastAttemptAt` and clears `failingSince`.
  - `failure(at)`: `if failingSince is None: failingSince = at`; `lastAttemptAt = at` (never `or`: a 0.0 stamp is a valid time; pre-flight M1).
  - `summary()`.
- `class ControlState`: `desired`, `records`, `free: FreeChannel`, `lastStopProvider: Optional[str]`.
- `class DesiredStore`:
  - Kept as is: `__init__(clock=time.time)`; `get`; `clear`; `decision`; `forget`; `followRegistry`; `record`; `state`; `peek`; `settled`; `keys`; `onChange`; `summary`.
  - `set(key, aspect, value, by, decision=False, restore=False, lift=False) -> bool`: an adopted desire holds unless `decision`; an unchanged value is a no-op.
  - `clearIf(key, aspect, value) -> bool`: clears when the desired value equals `value`. It replaces `release`.
  - `adopt(key, aspect, value)`: `CHARGE_LIMIT` only (`ValueError` otherwise). It sets `Desired(value, "user", now, adopted=True)`.
  - `free(key) -> FreeChannel`.
  - `noteOutcome(self, key, aspect, attempt, outcome, now, paid: bool, freeProvider: bool) -> bool` is the only mutation of a record after submit, under the lock (ledger L16). It returns False and changes nothing when `record.inFlight is not attempt`. Otherwise:
    - `inFlight = None`.
    - Detail in `LANE_DETAILS`: stop here (the attempt never ran).
    - `lastOutcome/At/Provider`.
    - Not `isNotSent(outcome)`: `lastSentAt = now`; `lastFreeAt = now` when `freeProvider`; when `paid`: `paidRetryDue = (paidAt is None and kind in RETRYABLE and not detail.startswith("wake "))`, evaluated before `paidAt = now` (a failed wake gets no blind retry; pre-flight M8). It is True only after the desire's first paid request failed, and False after the retry's outcome, whatever that is.
    - `SETTLED`: `settledAt = now`; `free.success(now)` when `freeProvider`.
    - `RETRYABLE` with detail ≠ `"pairing"` (ledger L52), or `REFUSED`, on a free provider: `free.failure(now)`.
    - `EXCLUDING`: `exclude(provider, kind)`.
- Removed: `SessionBounds`, `ChannelHealth`, `bounds()`, `health()`, `release`, `endSession`, `noteOffering`, `probeInFlight`, `offering`/`offeringSince`, `_chargingLike`/`_stoppedLike`/`CHARGING_LIKE`/`STOPPED_LIKE`, and the record's `tried/paid/backoff/backoffUntil/notBefore/newRound`.

- [ ] **Step 1: Write the failing tests.**
  - Keep, adjusted: `test_outcome_vocabulary` (plus `"wake held" in O.NOT_SENT`), `test_set_get_clear_and_change_signal`, `test_default_clock_is_wall_time`, `test_adopted_slow_aspect_holds_until_a_decision`, `test_a_by_only_change_is_a_no_op`, `test_a_decision_on_the_adopted_value_takes_it_over_in_place`, `test_a_raising_change_callback_is_dropped_and_others_still_run`, `test_scripted_provider_and_order_helpers`, `test_forget_drops_every_trace_of_a_key`, `test_registry_removals_forget_desired_state`, `test_a_new_desire_drops_unsupported_exclusions_and_keeps_refused`.
  - Delete the bounds, health, round, offering and broken-reconciler tests.
  - Add:

```python
def test_adopt_is_for_the_charge_limit_only():
    s = DesiredStore(); s.adopt(VIN, CHARGE_LIMIT, 80); assert s.get(VIN, CHARGE_LIMIT).adopted
    with pytest.raises(ValueError): s.adopt(VIN, CHARGING, "Charging")

def test_clear_if_drops_only_a_matching_value():
    s = DesiredStore(); s.set(VIN, CHARGING, True, "heartbeat")
    assert s.clearIf(VIN, CHARGING, False) is False and s.clearIf(VIN, CHARGING, True) is True and s.get(VIN, CHARGING) is None

def test_free_channel_is_per_car_and_shared_by_aspects():
    s = DesiredStore(); f = s.free(VIN); f.failure(0.0); f.failure(70.0)
    assert (f.failingSince, f.lastAttemptAt) == (0.0, 70.0) and s.free(VIN) is f and s.free(VIN2) is not f
    f.success(80.0); assert f.failingSince is None and f.lastAttemptAt == 80.0

def test_note_outcome_bookkeeping():
    c = Clock(); s = DesiredStore(clock=c); s.set(VIN, CHARGE_LIMIT, 50, "policy"); r = s.record(VIN, CHARGE_LIMIT)
    a = attempt("FleetAPI"); r.inFlight = a
    assert s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.ERROR, "500"), 100.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0 and r.lastSentAt == 100.0 and r.inFlight is None and s.free(VIN).failingSince is None
    b = attempt("TeslaBLE"); r.inFlight = b
    s.noteOutcome(VIN, CHARGE_LIMIT, b, O.Outcome(O.ERROR, "pairing"), 110.0, paid=False, freeProvider=True)
    assert s.free(VIN).failingSince is None and r.lastFreeAt == 110.0                        # pairing window: not a failure
    r.inFlight = b; s.noteOutcome(VIN, CHARGE_LIMIT, b, O.Outcome(O.UNREACHABLE, "no reply"), 120.0, paid=False, freeProvider=True)
    assert s.free(VIN).failingSince == 120.0
    assert s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.DONE), 130.0, paid=True, freeProvider=False) is False   # stale report
    r.inFlight = a; s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.UNREACHABLE, "wake held"), 140.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0                                                                  # nothing was sent
    r.inFlight = a; s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.UNREACHABLE, "rules: limit unknown"), 150.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0                                                                  # rules outcome: no request
```

  The helpers `attempt(provider, aspect=CHARGE_LIMIT)` and `VIN2` are defined at the top of `test_outcome_desired.py` (pre-flight L5); add `test_a_failed_paid_wake_sets_no_retry` (`UNREACHABLE "wake asleep"` → `paidRetryDue` False).

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: clearIf`).
- [ ] **Step 3: Implement** per Interfaces. Fix the importers: `Gen2TWCProvider.ready` still reads `peek(key).lastStopProvider`.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_outcome_desired.py tests/unit/test_workers.py tests/unit/test_provider_outcomes_local.py -q --timeout=60 -p no:cacheprovider`, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Slim the desired-state store: charge-limit adoption only, one free-channel record per car, no session bounds or backoff ladder"`

