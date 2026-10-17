# Slim Task 7 report: Slim the desired-state store

**Status:** DONE
**Commit:** ccbe58c (on vehicle-model/phase3, parent 163d8c1)
**Tests:** the targeted run (test_outcome_desired, test_workers, test_provider_outcomes_local) gave 64 passed. The full suite (`tests --ignore=tests/API --ignore=tests/integration`) gave 1454 passed, 1 xfailed. The baseline was 1458 at 163d8c1; this task took test_outcome_desired from 21 tests to 17, so the expected count is 1458 − 4 = 1454.
**Lib line delta** (`git diff --stat 163d8c1 -- lib | tail -1`): `3 files changed, 151 insertions(+), 261 deletions(-)`, a net change of −110.

## What changed
- `Outcome.py` adds `NOT_SENT`, which is `LANE_DETAILS` plus backoff, wake held, wake refused, no command token, not listed, online check failed and read. It also adds `RULES = "rules: "` and `isNotSent(outcome)`, which covers both the set and the prefix.
- `Desired.py`:
  - **Removed:**
    - `SessionBounds`, `ChannelHealth`, `bounds()`, `health()`, `release`, `endSession` and `noteOffering`.
    - `probeInFlight`, `offering` and `offeringSince`.
    - `_chargingLike`, `_stoppedLike`, `CHARGING_LIKE`, `STOPPED_LIKE`, `SLOW_ASPECTS` and `Desired.forced`.
    - On the record: `tried`, `paid`, `refused`, `backoff`, `backoffUntil`, `notBefore`, `newRound` and `reset`.
  - **Added:**
    - `AttemptRecord` now has `excluded: Dict[str, str]`, `lastSentAt`, `lastFreeAt`, `paidAt` and `paidRetryDue`. `newDesire()` drops UNSUPPORTED exclusions, keeps REFUSED ones, and resets `lastFreeAt`, `paidAt`, `paidRetryDue` and `settledAt`.
    - `FreeChannel` has `failingSince` and `lastAttemptAt`. `failure()` uses `is None`, not `or`.
    - `ControlState` now holds `desired`, `records`, `free` and `lastStopProvider`.
    - `DesiredStore` gains `clearIf`, `free` and `noteOutcome`. `noteOutcome` follows the brief exactly and runs under the leaf lock. It does no notify and no submit.
  - **Changed:**
    - `adopt` is for CHARGE_LIMIT only and raises ValueError for any other aspect.
    - `set` no longer takes `forced`.
- `__init__.py` exports `FreeChannel` and no longer exports SLOW_ASPECTS, ChannelHealth or SessionBounds.
- Importers: `Gen2TWCProvider.ready` still reads `peek(key).lastStopProvider`, and test_provider_outcomes_local still sets `state(VIN).lastStopProvider`. Neither needed a change.
- Tests: `tests/unit/test_outcome_desired.py` was rewritten.
  - I kept and adjusted the 11 tests the brief named.
  - I deleted the bounds, health, round, offering and broken-reconciler tests.
  - I added the brief's four new tests and `test_a_failed_paid_wake_sets_no_retry`. I also added `test_a_new_desire_resets_the_per_desire_stamps`, which replaces the old new-desire reset test.
  - `test_note_outcome_bookkeeping` is extended beyond the brief to cover:
    - the retry being used up after a second paid failure (`paidRetryDue` becomes False);
    - a LANE_DETAILS loser, which clears `inFlight` and nothing else;
    - a REFUSED free outcome, which records the exclusion and a free failure while `failingSince` keeps its first stamp;
    - a DONE on a free provider, which sets `settledAt`, calls `free.success` and leaves the aspect settled.
  - `test_default_clock_is_wall_time` also covers `adopt`, as a second production-clock check.

## Fail-before (before implementation, with the new tests in place)
```
E   AttributeError: module 'TWCManager.Vehicle.Reconcile.Outcome' has no attribute 'NOT_SENT'
E   Failed: DID NOT RAISE ValueError
E   AttributeError: 'DesiredStore' object has no attribute 'clearIf'. Did you mean: 'clear'?
E   AttributeError: 'DesiredStore' object has no attribute 'free'
E   AttributeError: 'DesiredStore' object has no attribute 'noteOutcome'
E   AttributeError: 'DesiredStore' object has no attribute 'noteOutcome'
E   assert (1.0, 2.0, True, 3.0, 4.0) == (0, None, False, None, 4.0)
E     
E     At index 0 diff: 1.0 != 0
E     Use -v to get more diff
E   AttributeError: 'DesiredStore' object has no attribute 'free'
E   AssertionError: assert {'FleetAPI', 'Gen2TWC'} == {'Gen2TWC': '...I': 'refused'}
E     
E     Use -v to get more diff
E   AssertionError: assert (False is False and Desired(value... forced=False) == (False, 'dist... False, False)
E    +  where False = set('5YJ3E1EA1KF000001', 'charging', False, 'heartbeat')
E    +    where set = <TWCManager.Vehicle.Reconcile.Desired.DesiredStore object at 0x7af677732ff0>.set
E     
E     Left contains one more item: False
E     Use -v to get more diff)
FAILED tests/unit/test_outcome_desired.py::test_outcome_vocabulary - Attribut...
FAILED tests/unit/test_outcome_desired.py::test_adopt_is_for_the_charge_limit_only
FAILED tests/unit/test_outcome_desired.py::test_clear_if_drops_only_a_matching_value
FAILED tests/unit/test_outcome_desired.py::test_free_channel_is_per_car_and_shared_by_aspects
FAILED tests/unit/test_outcome_desired.py::test_note_outcome_bookkeeping - At...
FAILED tests/unit/test_outcome_desired.py::test_a_failed_paid_wake_sets_no_retry
FAILED tests/unit/test_outcome_desired.py::test_a_new_desire_resets_the_per_desire_stamps
FAILED tests/unit/test_outcome_desired.py::test_forget_drops_every_trace_of_a_key
FAILED tests/unit/test_outcome_desired.py::test_a_new_desire_drops_unsupported_exclusions_and_keeps_refused
FAILED tests/unit/test_outcome_desired.py::test_a_by_only_change_is_a_no_op
```

## Concerns (none blocking)
1. **Line delta against the budget.** The net change is −110 against the plan's "Desired −250" estimate. Task 13's `--stat` check should absorb the shortfall; I did not pad the deletions.
2. **`adopt(key, CHARGE_LIMIT, None)` is still a silent no-op.** The brief does not mention this case. I kept the old rule that an unread value is never the user's, and a test covers it.
3. **The `RULES = "rules: "` constant** in Outcome.py goes beyond the brief's interface. It is harmless, and Task 9 can use it.
4. **`AttemptRecord.reset()` is gone.** The brief lists it neither as kept nor as removed. Its only caller was `endSession`, which this task removes.
5. **The test file went from 21 tests to 17.** The deleted tests are the ones the brief said to delete.
6. **The 1 xfailed predates this task.** It comes from `tests/scenarios/bugs/test_regression_template.py`, which this task did not touch.
