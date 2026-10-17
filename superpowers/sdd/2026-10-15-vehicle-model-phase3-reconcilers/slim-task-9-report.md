# Slim Task 9 report: charge-limit rules and the reconciler with the one fallback rule

**Status:** DONE
**Base:** cf63e52. **Commits** (on vehicle-model/phase3 in scratchpad/wt-vm3):
- c4cbc50: carries (a), (b) and (c).
- 1b69ec0: `Reconcile/Rules.py` and the ported `test_charge_limit_rules.py`.
- fd3f25f: `Reconcile/Reconciler.py`, Run.py placeholders removed, Desired pairing change, `test_limit_reconciler.py`.
- 3fbb5e4: a test that a restore on BLE+Fleet never wakes and pays at most twice.

**Tests:** full suite `tests --ignore=tests/API --ignore=tests/integration`: **1637 passed, 1 xfailed** (1551 at cf63e52). The 86 new tests are 46 rules, 38 reconciler and 2 carry tests; one carry test was an edit to an existing test.

**Lib line delta (cf63e52..3fbb5e4):** +586 / −31 = **+555 net** over 5 files.
- `Reconciler.py` is new at **425 lines**. That is under the 550 stop line but 65 over the plan's ~360 estimate. The ledger asks for a budget re-forecast after Task 9.
- `Rules.py` is new at 137 lines (the estimate was 140).
- Run.py 24 changed (net −14), Desired.py 19 changed, TeslaAPI.py +10/−2.

## What was built

### Rules.py
- `decideChargeLimit(desired, restore, current, held, sendWhenUnknown)` and `needsLiveRead(restore, current, held)` are ported from `presence/2-charge-limits:lib/TWCManager/ChargeLimitRules.py`. The branch order and every reason string are kept verbatim.
- The mapping: `held is None` means nothing saved. `held.held is None` means −1. `restore` means `limit == -1`. Every `(x, -1)` save becomes `HeldLimit(x, None)`.
- The original's local `held` is renamed `isHeld`, because `held` is now the parameter.
- The one addition (L28): `desired` and `held.outside` are clamped to 50–100 before deciding.
- `telemetryChargeLimit` is not ported. It reads the legacy CarApiVehicle, and `needsLiveRead` plus `force` replace it.

### Reconciler.py
- Constants, `satisfied`, `known` (with the TWC `actualCurrent` stand-in for CHARGING), `newerReading`, `handsOff`, `allowWake` and `VehicleReconciler` follow the brief.
  - `handsOff` takes an extra `config=None` argument so it can read `respectVehicleSchedule` on every call.
- `plan()` follows the brief's pseudo-code line by line: the H2 NOT_SENT hold, adoption (CHARGE_LIMIT only), satisfied/lift, restore-with-nothing-held, hands-off, the settled gate, the candidate filters, `freeFailed`/`paidAgain`, limit-before-start, and the wake rule with no wake on the blind retry.
- `pass_()` plans every key and aspect in an explicit `(CHARGE_LIMIT, CHARGING, AMPS)` order, then submits.
  - Each submit is in its own `try`.
  - A submit that raises, or returns False, is cleared through `noteOutcome(..., Outcome(ERROR, "dropped"))` (L10). That call does nothing if the worker already reported the attempt.
  - The return value counts accepted submits.
- `report()` returns at once for a one-shot (L2). Otherwise it resolves the tier, with an unknown provider or cost counted as paid (fails closed), then calls `noteOutcome` and `wake()`. It never calls submit or cancel, and the reconciler takes no lock of its own.
- `beforeWrite` and `afterWrite`:
  - The rules run on the worker after the read.
  - `saveNow` is saved at once. A settled restore clears its desire with `clearIf`. `send is None` becomes UNREACHABLE.
  - `saveOnSuccess` is kept as `record.pendingSave` and saved on SETTLED.
  - `afterWrite` sets `lastStopProvider` on a settled CHARGING False.
- `run()` waits on an Event for at most `TICK`, exits on `stop()`, and logs exceptions by type name.
- Hands-off and "no provider" messages are logged once per (key, aspect). The map is pruned to the store's keys on every pass.

### Run.py
- The `_satisfied`/`_VEHICLE_SOURCES_EXCLUDED` placeholders and the `ModuleNotFoundError` fallback are removed. `_reconcilerParts()` is now a plain lazy import.
- `test_workers.py` now uses `Reconciler.satisfied` in its two monkeypatches.

## Carry-forwards

- **(a)** `_tagged` leaves an outcome alone when `isNotSent(outcome)`. "backoff", "no command token" and "online check failed" keep their NOT_SENT detail. "wake asleep" and "wake 500" are still prefixed, so `noteOutcome`'s `paidRetryDue` guard works.
  - Test: `test_workers.py::test_a_wake_that_sent_no_request_keeps_its_not_sent_detail`.
- **(b)** `wakeOutcome` order is now: no command slot, then backoff, then `_askChargeNeed`, then the free `is_awake` check (SATISFIED "online"), then "online check failed", then `slot.usable("wake")` ("wake refused"), then the hold and `wake_up`.
  - `test_provider_tables.py::test_a_403_on_wake_refuses_wakes_only` changed. The second refused wake now makes one free GET (cache expired). An online car now returns SATISFIED "online" with `wake_up` still at 1.
  - Side effect: `_askChargeNeed` and the `firstChargeNeededTime` stamp now run before the wake-refused return. This is harmless today; Task 11's `wakeDelayMins` work should know about it.
- **(c)** A legacy `wakeVehicle` 403 calls `slot.reportScopeRefused("wake", refused=True)`.
  - I used `refused=True`, as `_paidPost` does. With `refused=False`, a token whose `scp` lists `vehicle_cmds` retires nothing, so it would be a no-op for most tokens.
  - Test: `test_provider_tables.py::test_a_403_on_the_legacy_wake_refuses_wakes_only` (one `wake_up` POST across two calls; commands stay usable).
- **(d) Choice: a free provider always sends when the limit is unknown.** `beforeWrite` passes `sendWhenUnknown = tier < TIER_BILLED` rather than the original Task 6's `provider.local`.
  - A free provider therefore never returns a rules UNREACHABLE. A free channel that cannot reach the car fails a real request, `noteOutcome` marks `failingSince`, and the PAID_AFTER timer starts.
  - A paid provider still never sends blind.
  - This changes nothing for any provider that exists today. The free commanders (TeslaBLE, Gen2, Gen3) are all local, OwnerAPI declares no commands, and telemetry is passive.
  - Why this instead of "count a free rules UNREACHABLE as a failure":
    - It adds no new failure meaning to Desired, so Task 8's rule "a failure needs a request" stands.
    - The free channel always produces a real request to judge.
    - Sending blind costs nothing on a free channel, which is BLE's behaviour today.
  - Test: `test_a_free_channel_that_cannot_reach_the_car_still_starts_the_paid_timer`. A non-local CLOUD_FREE scripted provider with no known limit sends; its UNREACHABLE sets `failingSince`; Fleet goes once at +300 s and stays at 1 call. It also checks `beforeWrite` directly: the free provider sends and Fleet returns UNREACHABLE.
- **Pairing (L52):** a free provider's ERROR "pairing" now calls `free.success(now)` in `DesiredStore.noteOutcome`. This changes Desired's meaning, not just the reconciler's.
  - Reason: inside the pairing window the car answers, so the channel works and the paid fallback is held.
  - Without the change, a failure already on record still opened the paid window: the limit fails at t0, a start gets "pairing" at t0+30, and Fleet would start the car at t0+60.
  - Tests: `test_pairing_error_does_not_open_the_paid_window` (brief) and `test_an_open_pairing_window_holds_a_paid_fallback_already_due`.
- **Never submit or cancel under a lock:** `pass_` plans, then submits, with no lock held. `report` only calls `noteOutcome` and `wake`.
- **respectVehicleSchedule (H3):** `handsOff` covers every provider, and BLE's own "scheduled" check stays. Test: `test_a_scheduled_charge_is_left_alone`.
- **NOT_SENT hold (H2):** tests `test_a_not_sent_outcome_is_not_replanned_inside_retry` and `test_no_resubmit_loop_during_a_30_minute_wake_hold` (30 submits over 1800 s, 0 commands).
- **Q1 blind retry never wakes (M8):** tests `test_paid_retry_never_wakes_and_a_failed_wake_gets_no_blind_retry` and `test_a_wake_held_outcome_is_not_counted_as_the_paid_call`.

## Paid-path tests (each counts ScriptedProvider calls)
- **RF1:** `test_fleet_waits_for_ble_to_time_out_and_is_sent_once`.
- **RF2:** `test_failed_paid_call_retries_once_then_waits_for_a_newer_reading_or_a_new_value`.
- **Retry, refusal and not-sent cases:** `test_a_paid_retry_that_succeeds_is_not_repeated`, `test_a_refused_or_not_sent_paid_outcome_gets_no_blind_retry`, `test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car`, `test_a_satisfied_outcome_without_a_stamp_is_not_resent_until_new_evidence`.
- **Free-channel cases:** `test_stale_free_failure_gets_the_real_command_over_ble_before_paid`, `test_a_recent_free_failure_goes_paid_without_a_new_ble_try`, `test_a_free_channel_that_cannot_reach_the_car_still_starts_the_paid_timer`.
- **Restore:** `test_a_restore_falls_to_fleet_without_a_wake_and_at_most_twice` (BLE+Fleet: no wake, 2 paid calls in total).
- **Rate limit:** `test_rate_limited_provider_is_skipped_at_plan_time` (`allows` is called).
- **One clock domain:** `test_default_clocks_share_one_domain` runs on real clocks. `test_the_thread_runs_a_pass_on_a_change_and_exits_on_stop` checks the bounded loop exits on stop.

## Fail-before

- **Carries (cf63e52 plus the new tests):**
  ```
  FAILED test_workers.py::test_a_wake_that_sent_no_request_keeps_its_not_sent_detail
    AssertionError: assert (('unreachable...wake backoff') == ('unreachable', 'backoff')
  FAILED test_provider_tables.py::test_a_403_on_wake_refuses_wakes_only
    AssertionError: assert 2 == (2 + 1)      # no free online check before the refusal
  FAILED test_provider_tables.py::test_a_403_on_the_legacy_wake_refuses_wakes_only
    AssertionError: assert (not True)  where True = usable('wake')
  3 failed, 129 passed
  ```
- **Rules:** `E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile.Rules'`.
- **Reconciler (Reconciler.py moved aside):** `E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile.Reconciler'`.
- **Mutation checks** (each mutation was reverted; each was caught):
  - H2 hold removed: 2 tests fail.
  - Blind retry allowed to wake: 2 fail.
  - `sendWhenUnknown=provider.local`: the (d) test fails.
  - Pairing not counted as success: 2 fail.
  - Schedule hands-off removed: 1 fails.
  - PROBE_AFTER clause removed: the stale test fails.
  - `paidAgain` gate removed: RF2 and M8 fail.
  - Limit-then-start gap removed: the clock test fails.
  - Restore hourly retry removed: 1 fails.

## Concerns / notes for review

1. **Line budget.** The reconciler is 425 lines against an estimate of ~360. Task 9's net lib change is +555. Please re-forecast.
2. **The H2 hold spans desires on the same aspect.** The pseudo-code is followed verbatim: the hold does not check `d.at`. A new value inside the hold therefore waits up to `RETRY[aspect]`. For example, a CHARGING stop right after a start's "wake held" waits up to 60 s. It is cost-safe, and the car was asleep anyway. `test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car` advances `RETRY` before the new decision because of this. Adding `rec.lastOutcomeAt >= d.at` would make a new desire re-plan at once; I left it out to keep the pseudo-code.
3. **The settled gate's `RETRY` clause survived mutation.** It is redundant: every sent outcome also stamps `lastFreeAt` or `paidAt`, and those gaps hold the resend. It is kept per the pseudo-code.
4. **A restore that is already satisfied never clears the held record.** If the car is already at the outside limit, `satisfied` returns before the rules run. `heldLimits` then stays `(90, 50)`, `holding()` keeps listing the VIN, and the restore desire stays in place. No request is sent. The next decision handles it correctly: the hand-set rule treats 90 as normal. Task 10 consumes `holding()`, so it should be aware of this (Low).
5. **`rec.inFlight` and `pendingSave` are assigned outside the store lock.** `inFlight` is set on the reconciler thread while nothing is in flight. `pendingSave` is set by the one worker running that attempt. Both are single-writer, as the pseudo-code assigns them.
6. **AMPS (lift-clear, stand-in) has no test here.** `chargeCurrentRequest` joins `FIELDS` only in Task 12.

## Fix round 1

**Status:** DONE. **Commit:** d2a7a57, on top of 3fbb5e4.

**Tests:**
- Full suite: **1645 passed, 1 xfailed**. That is 8 new tests, and 4 existing tests updated.
- Reviewer's probe: run on a copy at `scratchpad/probe-slim9-fr1/`, so the reviewer's `results.json` is left untouched. **24/24 pass**, with one probe assertion corrected (see below).

**Lib delta for this round:** +57 / −22 = **+35 net**, in Desired.py and Reconciler.py. `Reconciler.py` is now 441 lines. The round started at +41; folding the stand-in path into `newerReading` brought it down to +35.

### What changed

- **C1** (Desired `noteOutcome`).
  - An attempt counts as "current" only when the desire still exists, has the same value, and `attempt.since >= desire.at`. Only a current attempt sets `lastOutcome`, `lastOutcomeAt`, `lastProvider`, `lastSentAt`, `lastFreeAt`, `paidSends`, `paidAt`, `paidRetryDue` or `settledAt`.
  - Any attempt that ran still clears `inFlight` and feeds the free channel (success, failure, pairing).
  - A superseded attempt adds an exclusion only for REFUSED. UNSUPPORTED can depend on the value, so it applies only to the attempt's own desire.
- **I1.** I did this by removing state rather than adding a `since` field: `newDesire()` now also clears `lastOutcome` and `lastOutcomeAt`.
  - With C1 in place, a late report for the old desire never writes them again.
  - So the existing hold check, `rec.lastOutcome ... now - lastOutcomeAt < RETRY`, now applies only to the desire the outcome came from. `plan()` itself is unchanged.
- **I2.**
  - New record fields `paidSends` (which replaces the `paidAt is None` test) and `paidSaw`. `paidSaw` is the believed value when a paid attempt is planned; both are reset by `newDesire`.
  - The rule is now `paidAgain = paidSends == 0 or (paidSends < 2 and gap and (paidRetryDue or newerReading(..., unlike=paidSaw)))`.
  - `newerReading(vehicle, aspect, since, unlike=None)` folds the stand-in into one return. A reading of `unlike`, or of `None`, is no evidence.
- **I3.**
  - The blind retry has `maxAge=None` (no pre-write read) and never wakes; both come from one `blind` flag.
  - A paid attempt otherwise uses `maxAge = READ_MAX_AGE + PAID_AFTER[aspect]`. A free attempt keeps `READ_MAX_AGE`.
- **M1.** If a restore is already satisfied while a limit is held, the reconciler saves `HeldLimit(current, None)` and clears the desire.
- **M2–M5.**
  - M2: unchanged. The review judged the code correct as written; `begin()` was optional.
  - M3: unchanged, because it is a spec-level call and the brief's RF1 test pins the current behaviour.
  - M4: the settled-gate `RETRY` clause is kept.
  - M5: the stand-in branch of `newerReading` is folded in. I didn't trim `_sayOnce`/`_save` further.

### Tests

- **New in `test_limit_reconciler.py`:**
  - `test_a_stop_set_while_a_start_is_in_flight_is_sent_on_the_next_pass` (C1).
  - `test_a_limit_changed_while_in_flight_sends_the_new_value` (C1).
  - `test_a_stop_set_after_a_start_s_wake_held_goes_on_the_first_pass` (I1).
  - `test_a_failing_paid_call_under_a_poll_pays_at_most_twice_an_hour` (I2: 500 plus a 1-minute poll gives 2 paid in 1 h).
  - `test_a_satisfied_stop_with_a_stale_feed_pays_once_an_hour` (I2: 1 paid in 1 h).
  - `test_the_blind_retry_and_a_fallback_buy_no_paid_read` (I3, with a counting Fleet read source): 500 then 500 over 12 h gives 2 commands and 0 reads; a BLE failure that takes 20 s, then a Fleet fallback, gives 1 command and 0 reads.
  - `test_a_satisfied_restore_settles_the_held_limit_and_its_desire` (M1).
- **New in `test_outcome_desired.py`:** `test_a_superseded_attempt_feeds_the_free_channel_but_never_the_new_desire`.
- **Updated:**
  - RF2 test: after 2 failed sends, a reading of a new value (85) no longer reopens the paid path, because the cap holds. A new desired value still does.
  - The N1 test: it now uses a differing reading ("Starting"). Repeated "Charging" readings never cause a third send.
  - `test_a_refused_fleet_wake…`: the RETRY workaround is removed.
  - `test_a_failed_paid_wake_sets_no_retry`: the attempt's `since` now matches the desire's `at`.
  - `test_a_new_desire_resets_the_per_desire_stamps`: now also checks `paidSends`, `paidSaw` and `lastOutcome`.

**Fail-before** (the new and updated reconciler tests, at 3fbb5e4):
```
FAILED test_failed_paid_call_retries_once_then_waits_for_a_newer_reading_or_a_new_value   (assert 3 == 2)
FAILED test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car                       (['wake'] == ['wake', 'setChargeLimit'])
FAILED test_a_satisfied_outcome_without_a_stamp_is_not_resent_until_new_evidence          (10 extra stops)
FAILED test_a_stop_set_while_a_start_is_in_flight_is_sent_on_the_next_pass               (settledAt 1003.0 is not None)
FAILED test_a_limit_changed_while_in_flight_sends_the_new_value                           (settled(...) True)
FAILED test_a_stop_set_after_a_start_s_wake_held_goes_on_the_first_pass                   (pass_() 0 == 1)
FAILED test_a_failing_paid_call_under_a_poll_pays_at_most_twice_an_hour                   (12 == 2)
FAILED test_a_satisfied_stop_with_a_stale_feed_pays_once_an_hour                          (60 stops)
FAILED test_the_blind_retry_and_a_fallback_buy_no_paid_read                               (fetched 1 == 0)
FAILED test_a_satisfied_restore_settles_the_held_limit_and_its_desire                     (HeldLimit(90,50))
10 failed, 35 passed
```

### Probe results (fr1)

| Scenario | Before | After |
|---|---|---|
| Fleet 500 then 500 (12 h) | 2 cmd + 1 data | **2 cmd + 0 data** |
| BLE fails slowly (20 s), Fleet fallback | 1 cmd + 1 data | **1 cmd + 0 data** |
| Fleet 500 + 1-min poll of the same value (1 h) | 12 cmd | **2 cmd** |
| Stop SATISFIED + stale "Charging" feed (1 h) | 50 cmd | **1 cmd** |
| Desire changes while in flight (50→60) | 60 never sent | **bodies [50, 60]** |
| Stop while a start is in flight (no feed) | stop never sent | **stop on the next pass** |
| New stop after a start's "wake held" | 56 s late | **first pass** |
| All other rows | — | unchanged: retry never wakes; restore never wakes; 0 lock violations |

- **Probe assertion corrected.** `test_new_stop_held_behind_a_start_wake_held` asserts `waited == 0`. Its loop increments `waited` after the pass that sends the stop, so a stop sent on the first pass reports `waited == 1`. In the copy I added a direct check: the first `pass_()` returns 1 and `charge_stop` has been sent. It passes.

### Notes

- **Two scenarios still buy one `vehicle_data` for the new desire.** These are "Desire changes while in flight" and "Stop while a start is in flight", on an install whose only read token is Fleet.
  - Cause: the registry's freshness rule, "a reading not newer than our own write is not fresh", forces a read before the second command. That rule comes from Phase 2 and is not new here.
  - It is one $0.002 read per changed desire. I left it alone; it is the coordinator's call.
- **A reading of `None` no longer counts as new evidence.** This applies to the settled gate and to the paid reopen.

## Fix round 2

**Status:** DONE. **Commit:** d98d643, on top of d2a7a57.

**Tests:**
- Full suite: **1650 passed, 1 xfailed** (5 new tests, 1 rewritten).
- The reviewer's current probe, copied to `scratchpad/probe-slim9-fr2/` (with the N1/N2 rows and the off-by-one fixed): **26/26 pass**.
- The fr1 copy: 24/24 pass.

**Lib delta for this round:** +40 / −4 = **+36 net**, in Desired.py (+4) and Reconciler.py. `Reconciler.py` is now 472 lines, under the 550 stop line.

### What changed

- **Ruling 1: re-arm when no paid send reached the car.**
  - New record field `paidReached`, reset by `newDesire`. `noteOutcome` sets it with `paidReached |= kind != UNREACHABLE` on each paid send. A sent wake failure ("wake asleep") is UNREACHABLE too, so it counts as not reached.
  - In `plan()`: when `paidSends` is nonzero, nothing has reached the car, `RETRY` has passed since `paidAt`, and either (a newer reading of the field exists, of any value) or (`ride`, below), then `paidSends = 0`.
  - The next two sends then follow the normal rules, so it is at most 2 per re-arm. While no reading arrives and no start is pending, nothing is sent.
- **Ruling 2: limit before start.**
  - A start is now blocked when the limit desire exists, is unsatisfied, has been tried for this desire (`lastOutcome is not None`), and is not spent on a car that answered (`paidSends >= 2 and paidReached`). The existing blocks for a limit in flight and the 5 s gap after a limit write still apply.
  - `ride` is computed in the limit's plan: a start is desired, unsatisfied, and not hands-off. It re-arms an unreached paid budget, and it lets the limit wake (restores never wake). So when a start would wake the car, the limit goes first in that awake window, then the start, whose own wake hits the free online check.
  - While the car stays asleep, `wakeOutcome`'s 30-minute hold limits this to one `wake_up` per 30 min, which is the same as a start on its own would cost.
- **N2:** `since=max(now, d.at)`, so a desire set after the pass sampled `now` still counts its own sends.

### Tests (all in `test_limit_reconciler.py`)

**New:**
- `test_paid_sends_that_never_reached_the_car_rearm_on_a_reading_after_it_wakes`:
  - 2 sends get 408.
  - An hour of TWC heartbeat readings every minute (`actualCurrent`/`pluggedIn` from Gen2TWC): still 2 sends.
  - Then one `chargeLimit` reading of the same value: 1 more send. A second 408 adds 1 more, and that is the cap.
  - Then a reading after wake: DONE, and nothing further.
- `test_a_start_wakes_the_car_for_the_limit_first`:
  - Sequence: set, set (408), then 2 h later a start. The calls are `wake, setChargeLimit` (the limit, carrying the start's wake), then `wake, startCharging`.
  - The limit's write stamp comes before the start's.
- `test_a_start_waits_for_an_unsettled_limit`: BLE down on a BLE+Fleet car. There is no Fleet start at +60 ahead of the limit. At +300 the calls are `wake, setChargeLimit, wake, startCharging`.
- `test_a_limit_no_provider_can_deliver_never_holds_a_start`: pins the `lastOutcome is not None` condition, for installs such as pure-Gen2 or Owner-only where no provider can set the limit.
- `test_a_desire_set_during_a_pass_still_counts_its_paid_sends` (N2): 2 paid sends over 12 h.

**Rewritten:** `test_an_open_pairing_window_holds_a_paid_fallback_already_due`. It now seeds the free-channel failure directly instead of through a limit desire, because the new gate correctly holds the start behind that limit. A mutation check confirms that removing pairing-as-success still fails it.

**Fail-before** (at d2a7a57):
```
FAILED test_paid_sends_that_never_reached_the_car_rearm_on_a_reading_after_it_wakes   (assert 2 == 3)
FAILED test_a_start_wakes_the_car_for_the_limit_first                                 (index 3: 'startCharging' != 'setChargeLimit')
FAILED test_a_start_waits_for_an_unsettled_limit                                       (Fleet wake + start before the limit)
FAILED test_a_desire_set_during_a_pass_still_counts_its_paid_sends                     (assert 3 == 2)
4 failed, 46 passed
```

**Mutation checks:** each of these fails at least one test:
- dropping the ride wake;
- re-arming only on a reading;
- re-arming only on a ride;
- dropping the start gate;
- dropping the gate's `lastOutcome` condition (the no-provider test fails);
- `since=now`.

### Probe rows that changed (d2a7a57 → d98d643)

| Scenario | d2a7a57 | d98d643 |
|---|---|---|
| Fleet-only lower to a sleeping car (408 ×2), wakes 2 h later to charge | POSTs `set_charge_limit 50 ×2, charge_start`. **The car charges to 90** | POSTs `set_charge_limit 50 ×3, charge_start`. The limit is resent after the wake, before the start; 0 paid wakes, since the car is already online |
| Desire set during a pass (now < d.at), Fleet 500, 12 h | 3 paid | **2 paid** |

Every other row is unchanged, with 0 lock violations.

### Consequences of the ruling (accepted, not bugs)

1. **A source that republishes the field while the car sleeps re-arms once per `RETRY`.** HomeAssistant re-publishing its entity with fresh stamps is the example. That allows up to 12 paid sends an hour to an unreachable car, and `RETRY` is the only bound.
   - In the cases tested here, an asleep car produces no `chargeLimit` reading from a vehicle source: telemetry is silent and the poll is gated by `is_awake`.
   - I read "readings every minute while asleep" as TWC heartbeat readings, which `newerReading` excludes.
2. **On a free-only install, a limit that keeps failing blocks the start indefinitely.** On such an install the start would fail the same way.
3. **A limit excluded by REFUSED with `paidSends < 2` never counts as spent, so it can hold a start.** For a Fleet 403 the start is refused too. A HomeAssistant install would block.
