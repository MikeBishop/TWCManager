# API-only soak fixes (three)

These came from the box's API-only soak on 2026-10-22/23: BLE off, TeslaMate telemetry off, Gen2 TWC that reads VINs, OwnerAPI and FleetAPI both present.

Work on branch `vehicle-model/phase5`. Its worktree is `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-vm5` (tip a7f11121). Make one commit per fix.

When all three are in, rebase `vehicle-model/phase6` onto the new Phase 5 tip. Its worktree is `.../scratchpad/wt-vm6`. The old base is a7f11121:

```
git -C <wt-vm6> rebase --onto <new p5> a7f11121
```

Resolve any conflicts by behaviour.

The user approved all three fixes.

## Fix 1: a wake that answers offline/asleep/waking is not a failed wake

**Evidence, 00:00–00:10:**
- Scheduled Charging wanted a 70% limit. The car was asleep. After `wakeDelayMins` (3 min), `TeslaAPI.wakeOutcome` sent Fleet `wake_up` ($0.02).
- Tesla answered `state: "offline"`. That is normal: wake_up returns the state at that moment, and the car connects some seconds later.
- The code treated it as a failure: "Car API wake ... failed (unreachable offline). Will try again in 1800 seconds."
- The car woke anyway; the TWC status changed 4 s later. But the limit went out only at 00:10, five minutes late.

**Required behaviour:**
- After a wake_up whose answer is asleep, offline or waking, poll the FREE online check (`vehicles/{vin}`, via `onlineState`, bypassing its 120 s cache) every 5 s for up to about 45 s.
- If the car comes online, the wake is DONE. Do what the `state == "online"` path does: `_wakeSettled`, set `car.online` and `onlineCheckedAt`, and the short settle.
- Only if it never comes online is the wake a failure, with the existing WAKE_RETRY_SECONDS back-off and log line.
- Never a second wake_up. Never vehicle_data.
- This runs on the cloud worker, never on the tick. Blocking for 45 s is acceptable there; say so in a short comment.
- Put the numbers in named constants next to WAKE_RETRY_SECONDS.

**Tests:**
- offline answer, then online on the 2nd poll: DONE, exactly one wake_up, and the command goes out.
- Never online: the failure and back-off are unchanged, there is no second wake_up, and the number of polls is bounded.
- The parity file (`tests/unit/test_command_path_parity.py`) must not move in PAID counts. A moved free count is allowed only if it is these polls; report every moved row.

## Fix 2: current on the car's TWC means the car is charging

**Evidence:**
- 00:10:29 set_charge_limit was done. Raising the limit made the car start charging by itself.
- 00:10:35 charge_start answered result false with no reason ("error not accepted").
- 00:10:45 the TWC showed 16 A, then 48 A.
- 00:11:37 a "blind paid retry" charge_start went out anyway, also not accepted.
- With no BLE or telemetry, the car's `chargingState` is stale, so `R.satisfied(CHARGING, True, known)` didn't see the charge. The reconciler is in `lib/TWCManager/Vehicle/Reconcile/Reconciler.py`; see `_startWanted` and `_whyNoWake` "blind paid retry".

**Required behaviour:**
- When the car's charging point (a Gen2 or Gen3 TWC the car is on) reports at least 1 A actually flowing, a start counts as satisfied.
- No start command and no retry may go out while that holds.
- Find the cheapest place for this: the known value for CHARGING, or `_startWanted`. Prefer a fact the registry already holds, such as an existing observation of the TWC's amps or `chargerActualCurrent`.
- A stop desire is unaffected.

**Tests:**
- Fleet-only, with no feed and a stale chargingState: the TWC draws 48 A after the first start fails, and no retry goes out.
- Without current, the existing retry behaviour is unchanged.

## Fix 3: a held-asleep limit re-plans and logs every 15 minutes

**Evidence:**
- The policy change at 05:00 wanted the limit restored while the car slept.
- "chargeLimit setChargeLimit for <VIN> via FleetAPI: satisfied rules: held: asleep" was logged at 05:00, 05:15, ... 08:45: every free 15-minute status recheck.

**Rule, from Phase 5:**
- A no-wake cloud attempt to a car its free online check found asleep ends as a hold, `asleep`, like BLE.
- It re-plans only on a sign of life. Repeated asleep readings don't re-plan, and the hold is logged once.
- The 15/30-minute online recheck may run (it's free), but an asleep answer must neither re-plan the command nor log the line again.
- Find why each recheck re-plans. Likely the recheck's asleep observation counts as new evidence, or the recheck re-submits the attempt. Fix it so that only a change (awake/online, or another sign of life) re-plans.

**Tests:**
- An asleep Fleet-only car with a held limit, stepped through 4 hours of rechecks: one hold log line and no new attempt. When the car is next seen online, the limit goes out once.

## Constraints

- Never wake to observe. Never keep a car awake. Restores never wake. No new paid calls.
- No I/O on the tick or the serial thread. Lock order: TeslaBLE._bleLock → settingsLock → registry leaf.
- Python 3.8. Run black on the .py files you touch.
- Comments say why the code is what it is. No history, and no phase, task or ruling IDs. Match the surrounding comment density.
- Lib growth is a red flag. Keep each fix small and report the lib line delta. Count with `find lib -name '*.py' | xargs cat | wc -l`.
- Mutation-check each new test: revert the fix and watch it fail.
- Full suite, before and after, on both phase5 and phase6:
  `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`
  BASE: phase5 2287 passed, phase6 2403 passed, 1 xfailed each.
- Update the CHANGELOG and docs where they describe these behaviours: the wake, the start retry, the asleep hold. Check `docs/modules/Vehicle_TeslaBLE.md`, `docs/PolicyCustomization.md` and `docs/Settings.md`.
- Each commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't push. Never use bare `git stash`.
- Never print tokens, secrets, home coordinates or the owner's car name.

## Report

Write the full report to `.superpowers/sdd/2026-10-20-vehicle-watch/apionly-fixes-report.md` in the session worktree `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`. Include:
- the commits;
- the cause found for fix 3;
- the place chosen for fix 2, and why;
- the tests and mutation results;
- every parity row that moved;
- lib lines before and after;
- the suite results;
- the new phase5 and phase6 tips.

Return only a status, the commits, a one-line suite summary and any concerns.
