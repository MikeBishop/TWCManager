# Slim Task 7 review (163d8c1..ccbe58c)

Spec compliance: PASS.
Task quality: APPROVED, with one Important non-blocking gap and minors.

Focused tests, run in the checkout: test_outcome_desired, test_workers and test_provider_outcomes_local gave 64 passed.

## Checklist
- Interfaces: every name in the brief exists as written. These are `NOT_SENT`, `isNotSent`, `Desired` without `forced`, `AttemptRecord` (all fields, `newDesire`, `exclude`, `summary`), `FreeChannel`, `ControlState`, and `DesiredStore.set`, `clearIf`, `adopt`, `free` and `noteOutcome`.
- `forget` and the registry hook: unchanged, and covered by two tests (`test_forget_drops_every_trace_of_a_key`, `test_registry_removals_forget_desired_state`).
- `isNotSent`: matches the brief's set plus the "rules: " prefix. `LANE_DETAILS` is a subset of `NOT_SENT`.
- Failed wake: `paidRetryDue` is evaluated before `paidAt` is set, and "wake " details are excluded. `test_a_failed_paid_wake_sets_no_retry` covers it.
- `FreeChannel.failure`: uses `is None`. The 0.0 case is tested.
- Clock: the store stamps with `self._clock`, and `noteOutcome` takes a caller `now`. `test_default_clock_is_wall_time` covers the production clock for `set` and `adopt`.
- Locking: one leaf lock. `noteOutcome` does no I/O, no notify and no submit. `adopt` notifies after releasing the lock. No `Workers.submit` or `cancel` appears under the lock.
- Removed tests: they covered only removed features. Release is replaced by `clearIf`, the stale-report path is covered, and the broken-reconciler test went with `_chargingLike`.
- Removed API: grep over lib and tests found no references. The remaining hits are unrelated (`backgroundTasksLock.release`, BLE `_keyRefusal.refused`).

## Report concerns 2-4
- 2, `adopt(..., None)` stays a silent no-op: accept. It preserves the old rule that an unread value is never the user's. Task 8 should know this.
- 3, the `RULES` constant: accept. It is used by `isNotSent`.
- 4, `AttemptRecord.reset()` removed: accept. Its only caller was `endSession`, and no references remain.

## Critical
None.

## Important
- Outcome.py:39-47 and Run.py:205,208: `ERROR "no vehicle"` and `ERROR "no provider"` made no request but are not in `NOT_SENT`, which matches the brief literally. `noteOutcome` therefore counts them as sent, so a paid one sets `paidAt` and `paidRetryDue` and a free one calls `free.failure`. Fix in Task 8 or 9: add the two details to `NOT_SENT` (and to the `isNotSent` test), or have the caller not report them.

## Minor
- Desired.py `noteOutcome`: `_checkAspect(aspect)` raises `ValueError` for `aspect=None` (a debug one-shot attempt). The caller in Task 8 must skip `noteOutcome` for those, or `noteOutcome` should return False for None.
- Desired.py `noteOutcome` (SETTLED branch): a free provider's `SATISFIED "read"` or "rules: ..." (no request sent) still calls `free.success`, so a read-only success can clear `failingSince`. This is brief-literal. Consider gating on `not isNotSent` if Task 9 wants the channel to reflect sent commands only.
- `newDesire` does not reset `lastSentAt`. The brief does not list it, so this is correct. The test pins it.
