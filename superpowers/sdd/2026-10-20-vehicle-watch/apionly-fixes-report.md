# API-only soak fixes: report

Status: DONE_WITH_CONCERNS (one parity row outside fix 1 moved in its free count; see "Parity").

## Commits (vehicle-model/phase5, on a7f11121)

| SHA | Subject | lib +/- (net) |
|---|---|---|
| 01bbedb4 | Count a wake as done when the car connects seconds later | +19 -4 (+15) |
| d770b716 | Count current at the car's TWC as the car charging, for a start | +13 -8 (+5) |
| 3027a953 | Recheck a cloud hold with the online check alone | +16 -8 (+8) |

New tips: phase5 **3027a953**, phase6 **8e2afe2f** (rebased with `git rebase --onto 3027a953 a7f11121`).

Lib lines (`find lib -name '*.py' | xargs cat | wc -l`):
- phase5: 26564 -> 26592 (+28)
- phase6: 27137 -> 27165 (+28)

## Fix 1: an offline/asleep/waking wake answer

`TeslaAPI.wakeOutcome`: after a wake_up whose answer is asleep, waking or offline, it polls `onlineState(..., maxAge=0)` every `WAKE_POLL_SECONDS` (5), `WAKE_POLLS` (9) times. Both constants sit next to `WAKE_RETRY_SECONDS`. `onlineState` gained a `maxAge=120` parameter, and 0 skips the cache. It still prefers fresh telemetry that is newer than its own GET. If the car comes online, the code takes the existing `state == "online"` path: `_wakeSettled`, `car.online`/`onlineCheckedAt`, the 5 s settle, then DONE. Otherwise the existing failure path runs, with the same back-off and log line. There is never a second wake_up and never a vehicle_data read. A comment says that blocking about 45 s is fine on the cloud worker.

Docs: a CHANGELOG bugfix line, and the `wakeDelayMins` row in docs/modules/Vehicle_TeslaAPI.md.

## Fix 2: where and why

The fix is in `Belief.known(vehicle, aspect, desired=None)`. When the desire is a start (`desired is True`), a TWC `actualCurrent` reading of at least 1 A (the existing `standIn`, which reads the newest Gen2TWC/Gen3TWC observation) wins over the car's own chargingState if the TWC reading is newer. Otherwise `known` behaves as before.

Why here: `plan()`'s `R.satisfied(aspect, d.value, k)` gate and `_startWanted` both read `known`. Passing the desire means one fact the registry already holds (the TWC's own amps observation) suppresses both the first start and the blind paid retry, as well as the limit "riding" a start. A stop calls `known` with no desire, so it still sees the car's reading and is unaffected. The newer-than rule keeps an old TWC reading from overriding a fresh car read. HTTPControl's pending-commands list passes the desire too, so the page stops showing a start as pending while the car charges.

Docs: a CHANGELOG bugfix line, and one sentence in docs/Settings.md (Vehicle Command Policy).

## Fix 3: the cause

`_asleepCheckDue` made `plan()` treat a due recheck (15 min at home, 30 min away) as if there were no hold. It skipped the `waiting` gate and the `last == ASLEEP and asleep` gate, so each recheck planned and submitted the whole attempt again. In runAttempt that attempt did the free online check, got ASLEEP, and `report()` logged "satisfied rules: held: asleep" again. That is the line seen every 15 minutes. With BLE also loaded, every recheck re-tried BLE first as well.

The fix: when a recheck is due, `plan()` submits a cloud-worker Job (`"onlineCheck"`) that only calls the hold's provider `online(vehicle)`, stamps a new record field, `checkedAt`, for the cadence, and returns. An asleep answer only observes `state=asleep`, which is not a sign of life, so nothing re-plans and nothing is logged. An awake answer observes `state=online`, a sign of life, and the next pass plans the command as before. `submitJob` gained a `worker` argument; phase6 already had one, and its version was kept in the rebase. The test InlineQueue now runs `onlineCheck` jobs inline, as it does plugCheck.

Docs: the CHANGELOG "sleeping car" feature line, and the FAQ in docs/modules/Vehicle_TeslaBLE.md. Both now say that an asleep answer changes nothing and is not logged again.

## Tests and mutation results

| Test | Fix | Mutation (fix reverted) |
|---|---|---|
| test_teslaapi_wake.py::test_offline_wake_answer_then_online_is_done | 1 | fails |
| test_teslaapi_wake.py::test_wake_that_never_comes_online_fails_after_bounded_polls | 1 | fails |
| test_command_path_parity.py::test_fleet_only_car_online_seconds_after_an_offline_wake_gets_the_limit (one wake_up, set_charge_limit in the same pass, paid (0,1,1)) | 1 | fails |
| test_command_path_parity.py::test_fleet_only_start_no_retry_while_the_twc_draws[True] (1 charge_start; the stop's view is still "Stopped") | 2 | fails (2 starts) |
| ...[False] (no current: 2 starts, as before) | 2 | passes (control) |
| test_sleeping_car.py::test_a_fleet_restore_held_asleep_logs_once_and_rechecks_without_replanning (4 h: 1 hold line, 1 attempt, 16-18 free checks; online then: set_charge_limit once) | 3 | fails (16 hold lines) |

Existing tests changed:
- test_teslaapi_wake.py::test_state_check_with_both_tokens_is_a_state_get: GET count 3 -> 3 + WAKE_POLLS.
- the parity bound in test_fleet_only_car_never_online_after_an_offline_wake: + wakes * WAKE_POLLS.

## Parity: every moved row

Per-row request counts were compared before and after on all of test_command_path_parity.py and test_sleeping_car.py, on both branches with identical results. **No paid count moved** (vehicle_data, wake_up, command, ha and other are all unchanged).

Free counts that moved, all from fix 1, each exactly 9 polls per wake that did not answer online:

| Row | free before -> after |
|---|---|
| test_a_lower_that_wakes_a_refusing_car_rides_the_start_once_it_wakes | 16 -> 25 |
| test_both_tokens_off_car_matches_owner_only[asleep] (2 free Owner wakes) | 31 -> 49 |
| test_owner_only_off_car_matches_fleet_only[asleep] | 31 -> 49 |
| test_every_billed_wake_holds_the_next | 2 -> 11 |
| test_fleet_only_car_never_online_after_an_offline_wake[False-4] | 47 -> 83 |
| test_fleet_only_car_never_online_after_an_offline_wake[True-7] | 94 -> 156 (7 x 9, less one cache hit) |
| test_fleet_only_car_online_after_a_later_wake_gets_the_limit[2400-2] | 20 -> 38 |
| test_fleet_only_car_online_after_a_later_wake_gets_the_limit[4000-3] | 33 -> 60 |
| test_fleet_only_car_online_after_an_offline_wake_gets_the_limit | 2 -> 11 |
| test_fleet_only_car_online_after_an_offline_wake_gets_the_start | 2 -> 11 |
| test_owner_off_car_online_after_an_offline_wake_gets_the_limit | 5 -> 14 |

One row moved from fix 3, not from the polls:

| Row | free before -> after |
|---|---|
| test_vanished_car_restore_with_fleet_is_bounded (away, asleep, BLE silent, 3 h) | 3 -> 6 |

Before the fix, each recheck re-planned the restore, which went to BLE first (a free attempt that went unanswered) and then to Fleet. That pushed the cloud check to about once an hour. Now BLE is tried once, and the free online check runs on its documented 30-minute away cadence. The row gains three free GETs and loses two BLE attempts (four tesla-control runs). Its assertion (no command, no paid request) still holds.

## Suite results

Both runs used `tests --ignore=tests/API --ignore=tests/integration`.

| Branch | Before | After |
|---|---|---|
| phase5 | 2287 passed, 1 xfailed | 2293 passed, 1 xfailed |
| phase6 | 2403 passed, 1 xfailed | 2409 passed, 1 xfailed |

## Rebase conflicts (phase6), resolved by behaviour

- `Belief.known`: kept the fix 2 logic, using phase6's public `standIn`.
- `Reconciler.submitJob`: took phase6's version (`worker=`, `done=`); the fix 3 call works with it unchanged. Phase6's `Watch.cloudOnly` early-return in `_asleepCheckDue` is kept beside the `checkedAt` cadence.
- CHANGELOG and docs/modules/Vehicle_TeslaBLE.md: took phase6's watch wording and added the fix 3 sentence.

## Concerns

- The vanished-car parity row's free count moved for fix 3, as described above. It is fewer requests overall, but it is a moved free count that is not fix 1's polls.
- Fix 3 changes one more behaviour: a held cloud command no longer re-tries other free providers (BLE) on each recheck. It waits for a sign of life, as the hold rule says. On a BLE+Fleet install whose BLE is unreachable, the hold now rests until the free check or another source shows life.

## Fix round 1

Each fix went into the commit it belongs to, using `--fixup` and then `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash`. Two CHANGELOG conflicts during the autosquash were resolved by hand. The final tree is identical to the tree of the un-squashed fixup tip. Phase6 was then rebased with `git rebase --onto b48dd13b 3027a953`.

New tips: phase5 **b48dd13b**, phase6 **e976d6d0**.

| phase5 commit | Subject | lib net |
|---|---|---|
| 48474e05 | Count a wake as done when the car connects seconds later | +17 |
| ee237bd4 | Count current at the car's TWC as the car charging, for a start | +8 |
| b48dd13b | Recheck a cloud hold with the online check alone | +11 |

Lib lines:
- phase5: 26564 -> 26600 (+36; round 0 was +28)
- phase6: 27137 -> 27173 (+36)

The extra 8 lines: I1 +3, M1 +3, M4 +3, and the M5 cache-test trim -2 (the rest is comment rewording).

### What changed

- **I1 (fix 2).** `known(..., desired=True)` now needs the TWC reading to be newer than `max(car reading, now - FEED_LAG)`. FEED_LAG is the existing 30 s registry constant. A Gen2 heartbeats about every second and a Gen3's vitals are cached for 5 s, so a TWC still delivering current is always inside the window. The clock is the vehicle's own registry clock.
  - New test row `test_fleet_only_start_no_retry_while_the_twc_draws[stale]`: a single 48 A reading that is never repeated. The retry goes, giving 2 starts.
- **M1 (fix 1).** A `time.monotonic()` deadline of WAKE_POLLS x WAKE_POLL_SECONDS (45 s) is checked before each poll. The count stays as a backstop, because the tests' sleeps are no-ops and a time-only loop would spin there.
  - New test `test_slow_polls_stop_at_the_deadline`: each poll takes 20 s, and polling stops after 3.
- **M2 (fix 1).** After a poll finds the car online, `onlineCheckedAt` keeps the poll's newer stamp (`max(now, onlineCheckedAt)`). The comment says "the wake's or a poll's answer". `test_offline_wake_answer_then_online_is_done` now asserts the stamp.
- **M5.**
  - onlineState's cache comment now reads "Not more often than maxAge (120 s by default)", and `age =` puts the test back on one line (fix 1).
  - The Run.py Job comment no longer says "BLE worker" (fix 3).
  - On phase6, the Run.py rebase conflict was resolved to phase6's comment with "a status or online check".
- **M6 (fix 1).** The CHANGELOG now says "A Tesla API wake_up". Vehicle_TeslaAPI.md now says "asleep, offline or waking". The fix 2 CHANGELOG and Settings.md lines now say "in the last 30 seconds".
- **M7 (fix 2).** New `test_fleet_only_stop_is_the_same_while_the_twc_draws[True|False]`. It finds what "unchanged" means for a stop: with a stale "Stopped" and the TWC drawing 48 A, the stale reading settles the stop, so no stop goes out with or without current. That matches the behaviour before the fix; it is a pre-existing gap, not one this work introduced. The test pins it, and the old `known(v, CHARGING)` assertions it replaces are dropped.
- **M3.** Accepted per the ruling; no change.

### M4: reproduced and fixed (+3 lib lines, folded into the fix 3 commit)

Test `test_sleeping_car.py::test_a_fleet_rate_held_asleep_waits_for_life_not_heartbeats` reproduces it:
- Mode 2, Fleet-only, with an asleep car whose last chargingState was "Charging".
- The rate desire `wakes`, but a billed provider never wakes for amps, so runAttempt holds it as ASLEEP.
- The `not wakes` gate did not apply. Every Gen2 heartbeat (`seen=False` still bumps lastObservedAt) passed the `waiting` gate, so the attempt re-ran and logged "held: asleep" on every pass: **720 lines in 2 h**, not once per recheck.

The fix: the gate now uses `mayWake = wakes and (aspect != AMPS or the holding provider is local)`. A rate held through Fleet waits for a sign of life, which the 15-minute free check can supply. A BLE (local) hold whose desire may wake still breaks as before, so `test_a_raise_held_at_0_a_wakes_once_offered` still passes. This stays inside the hold rule: the command re-plans only on a sign of life or for a message that may wake.

After the fix the test shows one hold line over 2 h, no paid request, at most 10 free checks, and `set_charging_amps` once the car is online.

The blind-paid-retry variant the review names is not changed. It would need the `paidRetryDue` state threaded into the gate, which is more than this round's budget, and I did not reproduce it.

### Mutation checks (fix reverted, test fails)

- M1 deadline lines removed: `test_slow_polls_stop_at_the_deadline` fails (9 polls).
- M2 reverted to `now`: `test_offline_wake_answer_then_online_is_done` fails.
- I1 window replaced by `-inf`: `...twc_draws[stale]` fails (1 start).
- Stand-in applied to any desire (`desired is not None`): `...stop_is_the_same_while_the_twc_draws[True]` fails.
- M4 gate reverted: `...rate_held_asleep_waits_for_life_not_heartbeats` fails (720 hold lines).

### Parity

Re-compared phase5 against a7f11121. No paid count moved, and every common row's counts are identical to round 0's.

### Suites

| Branch | Base | Round 0 | Round 1 |
|---|---|---|---|
| phase5 | 2287 | 2293 | 2298 passed, 1 xfailed |
| phase6 | 2403 | 2409 | 2414 passed, 1 xfailed |
