# Wake regression (row 4b, D2): a car that comes online after an offline wake

Date: 2026-10-17. Worktree: `scratchpad/wt-rebase` (left on `rebase/phase3.5`, clean). Nothing pushed. `vehicle-model/*`, `deploy/*`, other worktrees and the box were not touched. The temporary `scratchpad/wt-check` worktree has been removed, and no background processes are running.

## Result

| Branch | Old tip | New tip | Unit suite | lib lines |
|---|---|---|---|---|
| rebase/phase3 | 1455ddba | **2a973cc0** (+1 commit) | 1778 passed, 1 xfailed (was 1775 + 2 xfailed: row 4b now passes, plus 2 new rows) | 27,272 → 27,291 (+19) |
| rebase/phase3.5 | 6fcbd4a2 | **58c43197** (17 rebased + 1 new) | 1864 passed, 1 xfailed (was 1860 + 2 xfailed: row 4b, 2 new rows, the Owner "off" row) | 27,377 → 27,394 (+17) |

The remaining xfail at each tip is the existing, unrelated one. Black `--check` passes on the changed lib files (`Reconcile/Desired.py`, `Reconcile/Reconciler.py`, `Providers/Provider.py`) at both tips. The rebase was `git rebase --onto 2a973cc0 1455ddba rebase/phase3.5`. It hit one conflict, in 6fcbd4a2 "Log vehicle wake decisions at INFO" (see below). After it, every phase3.5 commit passes the parity, limit-reconciler, charging-reconciler and wake test files (checked per commit in a temporary worktree).

## Root cause

A Fleet `wake_up` that answers asleep, waking or offline comes back to the reconciler as `UNREACHABLE "wake offline"`. The runner tags it in `Run._wake`, `Reconcile/Run.py:114-118`. The reconciler counts that as the desire's paid send:

- `Desired.noteOutcome` (`Reconcile/Desired.py:352-362` at 1455ddba) sets `paidSends=1`. It sets `paidRetryDue=False` on purpose, because a blind retry never follows a failed wake (M8).
- `Reconciler.plan` (`Reconcile/Reconciler.py:340-344` at 1455ddba) then allows another paid attempt only after a blind retry is due (`paidRetryDue`) or after a reading that reached the car (`reached`). The re-arm block at `:325-331` needs a reading as well (`reached`, `ride`, or charging seen).
- A Fleet-only car has no free provider (`free == []`) and no telemetry, so nothing produces such a reading.

The free online check (`vehicles/{vin}`, cached 120 s) runs only inside the provider's wake (`TeslaAPI.wakeOutcome`, `Vehicle/TeslaAPI.py:1355`), and no attempt is ever planned to reach it again. The car comes online, nobody looks, and the desire stays stranded: `paidSends=1, paidReached=False, paidRetryDue=False, rearmed=False, lastOutcome=(unreachable, "wake offline")`. I reproduced this before changing anything. Re-setting the same limit changes nothing (`DesiredStore.set` treats it as "Unchanged").

The H2 hold, RETRY and the NOT_SENT/EXCLUDING semantics are not the cause, and they are unchanged.

## Fix (2a973cc0, "Check again after a cloud wake the car did not answer (#699)")

- **`AttemptRecord.wakeCheckBy`** (Desired.py): the provider whose wake the car did not answer on the last paid send. It is set in `noteOutcome`'s paid branch when the outcome is RETRYABLE and its detail starts with `"wake "`. Any other paid outcome clears it, and `newDesire()` resets it. `paidRetryDue` keeps its old value; the expression is only rewritten.
- **`Reconciler.plan`**: one new `paidAgain` clause. It needs all of the following:
  - `paidSends < 2`
  - `now - paidAt >= WAKE_CHECK` (120 s, the online check's cache)
  - the desire still wants a wake (`wakes`, the existing `allowWake(...) or ride and not restore`, now computed once and reused for the attempt's `wake`)
  - `paid[0]` is the provider named in `wakeCheckBy`

  The attempt that follows wakes through that provider again (it is not blind). Because the provider holds its own wake for `WAKE_RETRY_SECONDS`, the attempt is just the free online check:
  - **Car still asleep:** the answer is `"wake held"` (NOT_SENT, no paid count). H2 spaces the next check at `RETRY[aspect]`, unchanged.
  - **Car online:** `SATISFIED "online"`, then the usual read and the command. This is the arm's second paid send.
  - **Hold over:** one more wake. This is the arm's second paid send, and if it also fails, `paidSends == 2` closes the clause.

  The I2 caps (2 per arm, 1 re-arm, at most 4 per desire) are untouched, and there is no resubmit loop of paid calls.
- **Comments:** the Reconciler header now states the budget rule. `Provider.wake` states the contract the clause relies on: a billed wake that fails holds the next one itself. Today the only billed providers that wake are FleetAPI and, at phase3.5, OwnerAPI for "off" cars. Both go through `wakeOutcome`'s per-car hold.
- **Locks:** none added. The new field is written under the store's leaf lock in `noteOutcome` and read without it in `plan`, like `paidRetryDue`. There is no I/O under any lock.

Phase3.5 conflict (6fcbd4a2): that commit hoists the attempt's wake expression into `wake = (...)` for `wakeSkipped`. Resolved as `wake = wakes and (p.local or aspect != AMPS) and not blind` with `wake=wake`. Same semantics in both structures. The dissolution of CarApiVehicle did not touch the fix, which lives in `Reconcile/`; phase3.5's `wakeOutcome` keeps the same hold (`car.delayNextWakeAttempt`).

## Tests

`tests/unit/test_command_path_parity.py`. All existing rows keep their counts. The helper `offlineWake()` makes `wake_up` answer offline and brings the car online N s later. phase3.5 also gets `wakeUps()`, because `counts()` counts Owner `wake_up`s as free.

- **Row 4b** `test_fleet_only_car_online_after_an_offline_wake_gets_the_limit`: no longer xfail. Runs 3600 s and asserts:
  - the limit goes out ≤150 s after the car is online
  - `paid == (1 vehicle_data, 1 wake_up, 1 command)` over the whole hour, so there is no second wake
  - `["set_charge_limit"]`, the car at 80, $0.023
  - `paidSends == 2`
- **New** `test_fleet_only_car_never_online_after_an_offline_wake_is_woken_twice`: 4 h with a car that never answers. Two wakes, more than 1800 s apart. `paid == (0, 2, 0)`, and only free checks in between.
- **New** `test_fleet_only_car_online_after_an_offline_wake_gets_the_start`: the same scenario for CHARGING. `charge_start` ≤150 s after online, one wake, one command.
- **New at phase3.5 (58c43197)** `test_owner_off_car_online_after_an_offline_wake_gets_the_limit`: Owner token only, car listed `command_signing: "off"`. One Owner `wake_up`, the limit ≤150 s after online, nothing billed, no "other" requests.
- **Changed** `tests/unit/test_limit_reconciler.py::test_paid_retry_never_wakes_and_a_failed_wake_gets_no_blind_retry` (M8, not a parity row). Its failed-wake leg uses a scripted Fleet provider that has no wake hold. It now expects `["wake", "wake"]` and `paidSends == 2`: the follow-up wakes again, and there is still no blind command. The blind-retry leg is unchanged.
- **Mutation check:** with the fix's `Desired.py` reverted, all four offline-wake rows fail at both tips (`KeyError 'sent'`, or 1 wake instead of 2).

## Paid-count evidence (probe on 2a973cc0; t relative to the policy change)

| Scenario | Requests | Timing |
|---|---|---|
| Limit, online at wake+59 s | GET (free) · wake_up · GET (free) · vehicle_data · set_charge_limit | wake t=2, online t=61, command t=122, which is 61 s after online. No further requests in the hour |
| Start, same | GET · wake_up · GET · vehicle_data · charge_start | identical timings |
| Never online, 4 h | GETs at t=2, 122, 422, 722, 1022, 1322, 1622, 1922 (8 free) · wake_up at t=2 and t=1922 | nothing after t=1922; `paidSends=2` |

Row 4b costs exactly row 4: $0.023. The `vehicle_data` is the I3 pre-write read (the seeded reading is older than 600 s), the same read row 4 makes. The brief's "1 wake + 1 command" matches the reconciler's paid sends (`paidSends == 2`), and the test asserts the full HTTP tuple `(1, 1, 1)` rather than leaving the read out.

## Shared paths considered

- **Start (CHARGING) via Fleet:** affected, now fixed and covered by a test.
- **Owner-"off" car (phase3.5):** OwnerAPI is TIER_BILLED (`OWNER_COMMAND`), declares WAKE, and wakes through the same `wakeOutcome`. It was affected the same way, is fixed by the same clause, and is pinned by a test at phase3.5.
- **Gen3 without BLE:** `Gen3TWCProvider` declares only SET_AMPS, START and STOP (LOCAL) and never wakes. A Gen3 car's start is local and free, so it is unaffected. Its limit has the same Fleet-only candidate list as row 4b, so it takes the same planner path and gets the same fix. No separate test: a Gen3 + Fleet fixture did not correlate the car to the unit (the Wall Connector VIN read under `install(fleet=True)`), and I did not pursue it.

## Concerns / decisions for a human

1. **Contract dependence.** The follow-up relies on the billed provider holding its own wake after a failure. That is true for FleetAPI and OwnerAPI (`wakeOutcome`), and it is now documented on `Provider.wake`. A future billed provider that wakes without a hold would get a second wake WAKE_CHECK (120 s) after the first. That is still capped at 2 per arm.
2. **Behaviour change for a car that never answers.** It now gets a second wake about 32 min after the first, at the first free check after the 30-min hold. Before the fix the stack never re-woke. Main re-wakes every 30 min while a charge is needed. Each arm stops at 2.
3. **Cadence after the first follow-up.** For a limit it is H2's RETRY of 300 s, so a car that comes online more than 120 s after the wake is noticed up to about 5 min later. For CHARGING it is 60 s. Main polled every 60 s for 10 min. I left H2 alone as the brief asked. Shortening "wake held" holds to WAKE_CHECK while `wakeCheckBy` is set would be a one-line change if wanted.
4. **More wakes for a car that never answers while a limit and a start are both wanted.** I measured this with a 4 h probe (Fleet-only, the policy raises the limit, a start every pass, the car never online):
   - Before the fix: 3 wakes, at t=2 s, 2102 s and 3903 s.
   - After the fix: 5 wakes, at t=2 s, 1922 s, 3723 s, 5583 s and 7442 s, then nothing more. That is $0.10 instead of $0.06.

   They come from the limit's two arms (the ride re-arm already existed) and from the start's own arm. Each arm now also gets its second wake after the hold. Everything stays inside the caps: at most 4 paid sends for the limit's desire, 2 per arm for the start. Main would re-wake every 30 min for as long as the charge was needed, which is about 8 wakes in 4 h.
5. **D2 resolved.** #699's first CHANGELOG entry no longer overclaims at the phase3 and phase3.5 tips.
6. **lib growth:** +19 lines at phase3 and +17 at phase3.5, which is against the "rearchitecture must shrink" rule. About 10 of those lines are comments: the Reconciler header sentence, the `Provider.wake` contract and the `WAKE_CHECK` constant. The logic added is the field, its reset, its assignment, the `wakes` hoist and the one clause. The header sentence and the `Provider.wake` comment overlap and could be cut by about 3 lines.
7. **`deploy/phase35-live`** still points at the old 5c133bef (D5). Retarget it to 58c43197 when deploying.

## Fix round 1 (rulings from wake-fix-review.md)

| Branch | New tip | Unit suite | lib lines (baseline → round 0 → round 1) |
|---|---|---|---|
| rebase/phase3 | **dc48ccdd** (2a973cc0 + 1 commit) | 1782 passed, 1 xfailed | 27,272 → 27,291 → 27,302 (+30 in total) |
| rebase/phase3.5 | **a698f753** (17 rebased + Owner-"off" pin) | 1868 passed, 1 xfailed | 27,377 → 27,394 → 27,405 (+28 in total) |

Black passes on the changed lib and test files at both tips. I rebased phase3.5 with `git rebase --onto <new phase3> 2a973cc0 rebase/phase3.5` and resolved the conflicts:

- **1ad0f505 (#659):** H2 now carries the new `last.kind not in EXCLUDING` line together with the WAKE_CHECK gap.
- **The Owner-"off" pin:** took the `api=FLEET` helper signature.

phase3.5's own Owner-"off" commit amends the hold test to list the car "off" and to assert that `[FleetAPI, OwnerAPI]` both hold. Every phase3.5 commit passes the parity, limit-reconciler, charging-reconciler and wake test files (checked per commit in a temporary worktree, since removed).

To keep every commit green, the phase3 hold test filters on `p.ready(v, WAKE)`. Without that filter, the commits between #659's OwnerAPI WAKE declaration and the "off" fixture would fail it, because the OwnerAPI wake is refused for a car that is not "off".

### Changes (dc48ccdd)

- **F1 (re-arm option):** the re-arm condition gains `or rec.paidSends >= 2 and rec.wakeCheckBy and wakes`. A spent arm that ended on a failed wake uses the desire's one re-arm when the desire still wants a wake. That allows at most 2 more wakes, so it is still at most 4 paid sends per desire (I2), and each wake is held 30 min by the provider.
  - `wakes` is now computed before the re-arm block, so a re-arm never leads to a send without a wake.
- **F2:** H2 is now `now - rec.lastOutcomeAt < (WAKE_CHECK if rec.wakeCheckBy else RETRY[aspect])`.
  - For a limit, "wake held" free checks are now 120 s apart instead of 300 s.
  - For CHARGING the gap goes from 60 s to 120 s. That is free, because the online check is cached for 120 s.
- **F3:** new test `test_every_billed_wake_holds_the_next`. It takes every provider that declares WAKE at a billed tier and is ready to wake the car (FleetAPI at phase3; FleetAPI and OwnerAPI "off" at phase3.5). For each, a failed wake followed, WAKE_CHECK later, by another wake must return `UNREACHABLE "wake held"`, and only one `wake_up` must be sent. No lib lines. Mutation check: with `WAKE_RETRY_SECONDS = 0` the test fails.
- **F4:** `woke` renamed to `failedWake`. **F5:** `bool(paid)` dropped. **F6:** the explanation now lives only on `Provider.wake` and the `WAKE_CHECK` constant. The header and clause comments reference it.
  - This did not shrink the lib: round 1 adds 11 lines net. F1 and F2 cost about 12 lines (black splits both conditions), F8 about 3, and F6 saves about 5.
- **F8:** `noteOutcome` clears `inFlight` last, including on the QUEUE_DETAILS early return.

### New and changed rows (paid = vehicle_data, wake_up, command; 4 h runs at 1 s steps)

| Row | Wakes (t, s) | Paid | Result |
|---|---|---|---|
| Limit, online at +59 s (row 4b) | 1 | (1,1,1) | sent 61 s after online |
| Limit, online at +2400 s (new) | 2 (2, 1922) | (1,2,1) | sent 60 s after online. The re-arm's first attempt is inside the second wake's hold, so no third wake is needed |
| Limit, online at +4000 s (new) | 3 (2, 1922, 3782) | (1,3,1) | sent 20 s after online, after the third wake |
| Limit, never online (changed: 2 → 4 wakes) | 4 (2, 1922, 3782, 5702) | (0,4,0) | 47 free GETs (bound ≤ 50) |
| **Limit + start, never online (worst case, new)** | **7** (2, 1922, 3723, 5642, 7443, 9303, 11223) | (0,7,0) | 94 free GETs (bound ≤ 100) |
| Start, online at +59 s | 1 | (1,1,1) | unchanged |
| Owner "off", online at +59 s (phase3.5) | 1 Owner wake | (0,0,0) | unchanged |

Probes from this round, not pinned:

- Limit, online at +300 s: sent 60 s after online.
- Limit, online at +1700 s: sent 100 s after online.
- Limit + start, online at +600 s: 1 wake, limit then start 120 s after online.
- Limit + start, online at +2400 s: 2 wakes, limit at +120 s and start at +125 s after online.

Worst case: **7 wakes in 4 h** ($0.14), from the limit and the start each using their two arms. Consecutive wakes are always more than 1800 s apart, because the provider's hold is per car. So it is at most 2 per hour, and the run stops at about 3.1 h. main would send about 8 in 4 h and never stop.

### Unit tests changed (scripted provider with no wake hold, not parity rows)

- **`test_paid_retry_never_wakes_and_a_failed_wake_gets_no_blind_retry`:** the failed-wake leg now expects `["wake"] * 4`, `paidSends == 2` and `rearmed`. It still never sends a blind `setChargeLimit`.
- **`test_a_limit_whose_ride_wake_failed_does_not_block_the_start_forever`:** the bound goes from `len(calls) <= 6` to `<= 8`: each desire's I2 cap, with failed wakes now re-arming once. With the real Fleet provider those wakes are 30 min apart.

### Mutation checks

- With the F1 re-arm clause disabled, the +2400 s and +4000 s rows and both never-online rows fail.
- With `WAKE_RETRY_SECONDS = 0`, the hold test fails.

Clean-up: `wt-rebase` is clean on `rebase/phase3.5`, the temporary worktree is removed, and no background processes are running.

## Fix round 2 (R1 from wake-fix-rereview.md)

| Branch | New tip | Unit suite | lib lines |
|---|---|---|---|
| rebase/phase3 | **3fcae411** (dc48ccdd + 1 commit) | 1783 passed, 1 xfailed | 27,303 (+31 over the 27,272 baseline, +1 this round) |
| rebase/phase3.5 | **5df98114** (18 rebased) | 1869 passed, 1 xfailed | 27,406 (+29 over 27,377, +1 this round) |

How the counts were taken: `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G <scratchpad>/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration --timeout=60 -p no:cacheprovider -q`, run from the worktree root on each tip. That is the whole of `tests/` minus API and integration, so it is not just `tests/unit` (the re-review's 1769/1855 came from a smaller collection). Black passes on the changed files.

`git rebase --onto 3fcae411 dc48ccdd rebase/phase3.5` applied with no conflicts. Every phase3.5 commit passes the parity, limit-reconciler, charging-reconciler and wake test files (checked per commit in a temporary worktree, since removed).

### Change (3fcae411)

`Desired.noteOutcome`: `paidReached |= outcome.kind != UNREACHABLE and not failedWake`.

- A wake that fails at the HTTP level (a `_paidPost` error), or that answers an unexpected state, comes back as ERROR `"wake …"`. Before this change it counted as a paid send that reached the car, and that blocked the F1 re-arm.
- A failed wake never reaches the car, whatever its kind.
- `failedWake` already requires RETRYABLE (UNREACHABLE or ERROR), so only failed wakes change. A failed command keeps its ERROR → `paidReached` meaning.

### New parity row

`test_fleet_only_wake_http_errors_then_online_gets_the_limit`, run for 4 h:

- Fleet-only. `wake_up` answers HTTP 500 at t=2 and at about t=1922, more than 1800 s apart.
- The car comes online 600 s after the second wake, and the limit goes out within 150 s of that.
- Paid: `(1 vehicle_data, 2 wake_up, 1 command)`, so at most 4. The command is `set_charge_limit` and the car ends at 80.
- Without the fix the limit is never sent (`KeyError 'sent'`).
