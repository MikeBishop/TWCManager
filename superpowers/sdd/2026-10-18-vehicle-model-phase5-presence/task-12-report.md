# Task 12 report: return and leave without plugging in (box, 2026-10-19 14:28–14:44)

Three commits on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent da500aa1). Not pushed.

| Commit | Issue |
|---|---|
| 977860d7 Log a repeated hold at DEBUG | 1 |
| c41e775e Try BLE first when a car comes back | 2 |
| 0251646b Restore at the drive start, while BLE is still in range | 3 |

## The sequence, reconstructed

The box log is INFO only, so the sequence was rebuilt from the log, `~/twc-events/teslamate.log` and the code. It was then reproduced in the new parity row, which shows the same lines in the same order.

- **13:21:29.** BLE `done`: that morning's restore to 100. The held entry was therefore most likely empty at the 14:28:36 restart.
  - **Correction to the brief:** the attempts at 14:28:44, 14:34:09 and 14:39:15 were the **policy apply (50)**, not a restore to 100. `inapplicable` returns None for a restore, so the 14:34:09 "not here (away)" clear can only come from an apply. Also, 14:34:09 is exactly 14:29:08 + RETRY.
  - `{VIN: [100, 50]}` was written by the paid apply at 14:40:08.
- **14:28:44, the first policy pass after the restart.** Nothing was known about the car yet (TeslaMate's retained topics arrived at 14:29:09), so it was PRESUMED and got the apply 50.
  - The BLE pre-flight ping timed out, and the scan missed at 14:29:08.
  - Results: an `absent` mark, `UNREACHABLE no BLE answer`, and the free channel `failingSince = lastAttemptAt = 14:29:08`.
- **14:29:09.** The retained position placed the car outside: NOT_HOME.
- **14:34:09** (RETRY after the miss). The free channel had been failing for at least PAID_AFTER, and was tried less than PROBE_AFTER ago, so the apply went to Fleet. Its verdict was NOT_HERE "away", and `clearIf` removed the desire.
- **14:39:15, a policy pass.** The car was inside the 1,000 ft radius while driving: PRESUMED "driving", so it got a new apply desire.
  - The free channel was last tried at 14:29:08, more than PROBE_AFTER ago, so the probe went to BLE.
  - The ping timed out at 14:39:30, and the scan missed at 14:39:40. That gave `absent` at 14:39:40, a free failure (`lastAttemptAt = 14:39:40`), and `rec.lastFreeAt = 14:39:40`.
- **14:39:50 to 14:40:03.** On every newer observation the desire was planned again. Fleet was chosen: failing since 14:29:08 (at least 300 s) and tried 10 s ago (under 600 s). The verdict was HOLD "driving".
  - `inapplicable` logged "hold (driving)" once.
  - `report()` logged the outcome line at INFO every time.
- **14:40:05, shift P.** This marked `driveEnd`; the parked fix inside the radius made the car HOME, and the verdict was SEND. Two gates both still chose Fleet:
  - `freeFailed`: failing since 14:29:08, last tried 14:39:40;
  - the desire's free gap: `now - lastFreeAt(14:39:40) < RETRY`, so BLE could not go anyway.
  - The result was a $0.001 `set_charge_limit` at 14:40:08 (no wake, because "not plugged in here" makes the message quiet), and held [100, 50].
- **14:41:25, shift D.** This marked `driveStart`. `decide` → PRESUMED "driving", and `departed()` returned None for it. No restore was planned.
- **Between 14:42:46 and 14:43:16.** A fix arrived outside the radius. (TeslaMate's geofence, smaller than the radius, was left at 14:41:43.) The car became NOT_HOME, and `departed` = the fix time.
- **14:43:16, the policy pass.** `_restoreDeparted` set the restore. Planned at once, it went to Fleet, because `freeFailed` was still True: failing since 14:29:08, last tried 14:39:40, 216 s ago, under PROBE_AFTER. Result: $0.001 at 14:43:17.

## Issue 1: repeated hold logs

**Root cause.** What re-plans every second is **TeslaMate's position stream** while the car drives: `latitude` and `longitude` at about 1 Hz.
- Each `Vehicle.observe` stamps `lastObservedAt` (Vehicle.py:127), and `plan` re-plans a held desire whenever `lastObservedAt > heldAt` (Reconciler.py:227).
- The re-plan ends in the same HOLD, and `report()` logged its outcome line at INFO every time.
- The tick is not involved:
  - TWC 8244 sat at 00 naming no car, so `TWCSlave`'s `actualCurrent` observe (the only heartbeat observe) had no vehicle;
  - nothing else on the 1 s reconciler tick observes.
- teslamate.log does not show the lat/lon topics because its follower logs only the topics it filters. The parity row reproduces the 14 lines with position pushes alone.

**Fix.** These are log-only changes; re-planning is left as it is. Narrowing the re-plan to verdict-relevant fields would touch the F3 ruling and Task 8's gate.
- `report()` reads the record before `noteOutcome`. When `rec.heldAt` is set and `rec.lastOutcome == outcome`, it logs at DEBUG. That is the same hold, for the same reason, already logged.
- `inapplicable`'s "hold (why)" line now logs when no hold is current, or when the current hold's outcome differs. A changed reason therefore logs again.
- Side benefit: Task 8's repeated `held: asleep` outcome line (its concern 7) is quieted the same way.

**Test.** `test_presence::test_a_repeated_hold_logs_at_info_once_and_again_for_a_new_reason`.
- A Fleet car driving, with a pushed reading every second for 60 s, gives 1 INFO `held: driving` line, 1 `hold (driving)`, and at least 3 DEBUG repeats.
- It then parks with no position: 1 INFO `held: not known here` and 1 `hold (not known here)`.
- Paid (0, 0, 0).
- **RED** on da500aa1: `assert 60 == 1`.

## Issue 2: paid Fleet on arrival without trying BLE

**Root cause.** It was the **free-failure clock spanning the car's absence (candidate b)**, in two gates. Both point at Reconciler.py `plan`:
1. `freeFailed` reads the per-car `FreeChannel`, which spans desires: `failingSince` 14:29:08 (away) and `lastAttemptAt` 14:39:40 (the miss while driving in). At 14:40:05 it had been failing for at least 300 s and was tried less than 600 s ago, so paid was chosen.
2. Even with (1) off, the desire's own free gap `now - rec.lastFreeAt >= RETRY` was closed: `lastFreeAt` was 14:39:40, from the miss while driving in.

**Candidate (a), the `absent` mark, is ruled out:**
- `TeslaBLEProvider.ready` reads only the claim, so the mark never removes BLE from the candidates.
- At park, the parked-inside fix is newer than the mark, so `decide` → HOME.

**Fix.**
- `Presence.returned(v) = max(driveEnd, plugIn)` is when the car last came back.
- In `plan`:
  - `freeFailed` additionally requires `ch.lastAttemptAt >= back`, and measures PAID_AFTER from `max(failingSince, back)`;
  - the free branch also opens when `rec.lastFreeAt < back`.
- So failures from before the car came back never open the paid path, and the car gets one free try once it is back.
- A failure after the arrival counts as before. A tie counts as after, so a failure in the same instant as the plug-in still opens the paid path.
- `contact` is deliberately not an arrival: a ping answer marks contact, so contact would reset the clock on every ping and a silent radio would never fall to Fleet.

**Tests.**
- **Parity row** `test_box_2026_10_19_return_and_leave_unplugged_goes_over_ble` (TeslaMate + BLE + Fleet, never plugged). Its sequence:
  - starts PRESUMED and driving;
  - the BLE ping fails, giving `absent`;
  - the car is placed outside and Fleet's attempt finds it away (cleared);
  - 15 minutes away;
  - it returns inside the radius while still driving and out of BLE range: one more BLE miss, then a position each second (one INFO hold line);
  - it parks (P, online) with BLE in range: `charging-set-limit 50` over BLE within 3 s, and no new paid request;
  - held [100, 50].
- **RED** on 977860d7: `assert [] == [50]`, meaning the apply went to Fleet (`(0, 0, 1)` in the probe run).
- **Paid tuple.** The row compares paid with the count taken at the return, so the return-to-departure span is (0, 0, 0). The away phase spends what BASE spends there: the Fleet attempt that finds the car away.
- **Note on "ping, then send".** With TeslaMate pushing `online` at P, the car is known awake, so `runAttempt` skips the pre-flight by design (Task 8 round 1, Important 4) and the command itself is the reach test. The row shows the BLE command with no ping at park.
- **Variant probed (not kept as a row).** Positions stop 30 s before P, so the last fix is older than the miss.
  - `decide` then says PRESUMED "no newer evidence", because `driveEnd` is not home evidence, and the first verdict is HOLD "not known here".
  - The next re-plan goes to BLE (the arrival opened it). Its PRESUMED ping answers and marks contact, the car is HOME, and the limit goes over BLE.
  - So it heals as long as BLE answers; see Concerns.

## Issue 3: departure restore 112 s late

**Root cause.** It was **a gate in `departed()`, plus the policy-pass cadence**.
- `departed()` (Presence.py) returned a departure only for a HOME car (unplugged, leaving after arriving) or a NOT_HOME one. A car driving off is PRESUMED "driving", so nothing was planned at D (14:41:25).
- The restore waited for a fix outside the 1,000 ft radius, which came between 14:42:46 and 14:43:16. It then waited for `_restoreDeparted`, which runs only on the 30 s policy pass (14:43:16) or the TWC unplug's background `checkDeparture` reads.
- The departure read schedule played no part: no TWC unplug happened.
- It then went to Fleet for issue 2's reason.

**Fix.**
- `departed()` checks NOT_HOME first, as before (the seen-gone time). It also counts a car that is driving and has come back (`returned(v) > NEVER`), when its leaving is newer than its arriving. That is the user's "a drive start inside the radius after an arrival".
- Requiring the arrival keeps a car seen only driving (no arrival mark) undeparted. The two existing hold rows that drive inside the radius with no arrival keep their apply desire and their counts.
- `noteObservation`'s `driveStart` branch calls `onDeparture(master, read=False)` (lazy import, like `onArrival`). The drive start itself plans the restore on the observing thread: no I/O, and the same calls `onArrival` already makes from that thread.
- `onDeparture` gains `read=True` (the background path is unchanged).
- A double fire (state and shiftState in the same second) is a no-op `desired.set`.
- The restore never wakes, and `inapplicable` never gates a restore. With issue 2 fixed, the free channel succeeded at arrival, so the restore goes BLE first (a PRESUMED car is pinged first, then sent).

**Test.** The same parity row, departure half.
- 75 s parked, so no policy pass falls on the D second; then shift D and state driving, and one reconcile pass.
- Result: `limits == [50, 100]`, held cleared, the car still inside the radius, no new paid request.
- **RED** on c41e775e: `assert [50] == [50, 100]`.
- **Second test** `test_presence::test_a_car_seen_outside_while_still_driving_has_departed`.
  - The car parks inside (`driveEnd`), then is next seen outside while still driving, with no drive start inside the radius.
  - `departed()` must still return the outside fix's time, and a policy pass must set the restore.
  - This pins the NOT_HOME branch ahead of the new driving branch. Review caught that a first draft returned None here, because `arriving > leaving`.
  - **RED** on that draft: `assert None == 1602.0`. It passes on BASE and after the fix.

## Parity moves (timing only; commands and paid counts unchanged)

| Row | Old | New | Reason |
|---|---|---|---|
| `test_arrive_limit_set_then_shift_to_d_in_the_driveway_restores_over_ble` | after D, 60 s of passes: no restore ("moving: nothing yet"); restore over BLE once the fix is outside; runs `[None, 50, 90]` | restore over BLE at the first pass after D, still inside the radius; runs `[None, 50, 90]`; nothing more once outside; no HTTP | Issue 3: the drive start after an arrival is the departure |
| `test_departing_car_is_never_presumed_present` (scenario 19) | unplugged, D, 120 s: `b.runs == []`; restore `[90]` after the outside fix | restore `[90]` at the first pass after D; presence still PRESUMED; nothing more after the outside fix; no HTTP | Issue 3: the plug-in is the arrival, and the drive start the departure |

No other parity count or timing moved.

**Plumbing (PLUMBING-ONLY):**
- `test_limit_reconciler::test_stale_free_failure_gets_the_real_command_over_ble_before_paid` and `::test_a_recent_free_failure_goes_paid_without_a_new_ble_try` planted their free failure before `setup()`'s plug-in mark (c = 1000). The plug-in is now an arrival that discounts older failures.
- Both now advance the clock by the planted age first, so the failure starts at the plug-in. Asserts are unchanged.

## Suites

- `tests/unit` + `tests/EMS`:
  - baseline 2140;
  - after 977860d7: 2141;
  - after c41e775e: 2142;
  - after 0251646b: **2143 passed**.
- Each commit was run on its own.
- Black is clean on every touched file. Deleted tests: none.

## Lib delta

- Before (da500aa1): 26,257. (The brief's "about 26,263" was approximate.) After: **26,277 (+20)**.
- `git diff --shortstat da500aa1 -- lib`: 3 files changed, 33 insertions(+), 13 deletions(-).

| Change | Net |
|---|---|
| Issue 1: `report`'s level, and `inapplicable`'s line on a reason change | +3 |
| Issue 2: two gates and their comment | +5 |
| Issue 3: the `returned()` helper (shared with issue 2), the `departed` widening with NOT_HOME first, the drive-start hook and the `onDeparture(read)` parameter | +12 |

- Cuts taken: the `_holding` helper was folded into two inline compares, the `departed` comment was kept at two lines, and `returned` is shared by both fixes.
- No duplication was found to delete in the touched code (`arriving`, `leaving`, `returned` and `departed` each have distinct callers).

## Concerns

1. **Lib +20, not near zero.** Most of it is issue 3's hook and helper. Dropping the drive-start hook (−4) would leave the restore on the 30 s policy cadence (still inside the driveway on most departures, but not "within a tick or two").
2. **`driveEnd` is not home evidence in `decide`.** If the last position predates a BLE `absent` mark (the car crept in and sat still before shifting to P), the parked car is PRESUMED "no newer evidence". The apply then gets HOLD "not known here" until BLE's ping marks contact. This heals whenever BLE answers. A car with no BLE (TeslaMate + Fleet only) cannot have an `absent` mark, so it is unaffected. Adding `driveEnd` to `decide`'s home evidence would close it fully; I left it out of scope.
3. **Re-planning a hold on every observation is unchanged.** Only the log changes. With BLE as the provider for a PRESUMED driving car, every re-plan pings. A driving car inside the radius out of BLE range costs one ping and scan per pass, serialized on the BLE worker. This is not new (the `test_ble_contact_while_driving_still_holds` behaviour), but the box now shows it each time a car drives in out of range. Gating the re-plan on verdict-relevant fields is the follow-up if it matters.
4. **Repositioning in the driveway now restores and re-applies.** A shift from P to D inside the radius after an arrival is a departure, so the restore goes. Parking again (`driveEnd`) re-applies. That is two free BLE commands per reposition, which is the user's event design. Over Fleet it would be two paid commands, but only when BLE has failed since the car came back.
5. **One extra free try per arrival, and paid about 301 s after the return.** A car whose BLE is truly broken gets one BLE try when it comes back. Because PAID_AFTER is then measured from the arrival, Fleet goes about 301 s after the return, not at once. That is the intended trade (corrected in fix round 1).

## Fix round 1 (commit c7410df0 "Hold a driving car without re-planning; trim")

**Changes**

- **Important: BLE ping churn while a held car drives in range.**
  - `plan` now returns None for a desire held "driving" while `Presence.drivingNow(vehicle)` is true. The check sits next to the newer-evidence gate.
  - A driving hold can change only once the car stops, so position pushes no longer re-plan it.
  - Ping count:
    - new `test_presence::test_a_held_car_driving_in_ble_range_is_pinged_once` (inside the radius, BLE answering, a position each second for 120 s) gives **120 pings → 1**;
    - **RED** on 0251646b: `assert 120 == 1`.
- **Cut 1.** `report()`'s repeat-hold DEBUG branch is gone, and every outcome logs at INFO again. `inapplicable`'s reason-change compare is gone (nothing needs it), so the hold line logs once per hold, as at da500aa1.
  - Issue 1's 14 lines are now prevented at the source: a driving hold is not re-planned.
  - Holds for other reasons ("not known here") still log their outcome line on each re-plan. "asleep" has its own gate.
- **Cuts 2–5:**
  - `onDeparture` is back to its da500aa1 form, and the drive start calls `Targets._restoreDeparted(master, read=False)`;
  - `noteObservation` has one lazy `from .Reconcile import Targets` at its top;
  - `departed()`'s tail is folded;
  - the `held` local is gone (the original return is restored).
- **M1.** Report concern 5 is corrected: broken BLE now means paid about 301 s after the return, not about 25 s.
- **M2.** The box row asserts `paid == (0, 0, 0)` for the whole sequence; `spent` is gone, and the comment says so.

**Tests**

- `test_presence::test_a_repeated_hold_logs_at_info_once_and_again_for_a_new_reason` is replaced by `test_a_driving_hold_waits_for_the_car_to_stop`. Over 60 s of readings it gives one `held: driving` line and one `hold (driving)` line. Once the car stops, the hold is planned again ("not known here"). Paid (0, 0, 0).
  - It already passed on 0251646b (the DEBUG branch hid the repeats there), so it pins the behaviour rather than proving the fix. The ping test is the RED one.
- **Parity move:** `test_ble_contact_while_driving_still_holds`: `len(b.pings) > 1` → `== 1`. Commands and paid counts are unchanged; the reason is the driving-hold gate.
- Covering tests (presence, parity, sleeping car, limit reconciler, limit wiring): 321 passed.
- `tests/unit` + `tests/EMS`: **2144 passed**.
- Black is clean.

**Lib delta vs da500aa1:** 26,257 → **26,272 (+15)**. `--shortstat`: 2 files changed, 26 insertions(+), 11 deletions(-). Targets.py is net 0.
