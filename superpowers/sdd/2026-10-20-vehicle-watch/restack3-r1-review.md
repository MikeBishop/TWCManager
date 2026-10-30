# restack3 r1 review: Phases 3, 3.5, 4 and fix/disabled-teslable

Base: origin/main = 02822e74. Reviewed restack3/phase3 (2512b8a5), restack3/phase3.5 (0167cdd2), restack3/phase4 (8566063a) and fix/disabled-teslable (09c60309) against the old pushed heads fe9eca64, 87a9eff1 and f1e98620.

## Verdicts

- **Spec compliance: PASS.** Main's guarantees hold at every tip, and no stack behaviour was lost. Both folds landed intact. The CHANGELOG follows the rules. The fix branch is one commit, applies to main and is pinned by a test that fails without it.
- **Quality: PASS with Minor findings.** None blocks the push.

Counts: Critical 0, Important 0, Minor 7.

## Method

- **Lost behaviour:**
  - For each phase I built (old pushed head + origin/main) with `git merge-tree` (the merge base is 26fc3f3d for all three) and diffed it against the new tip.
  - Outside the files that conflict, the only differences are the deliberate resolutions:
    - `_budgets` and the `test_charging_points`/`test_distributor_voltage` updates (Phase 4);
    - "(#721)" dropped from main's createServer comment in HTTPControl, which b54a2dee's no-issue-numbers guard requires (Phase 4).
  - The conflicting files are CHANGELOG, TeslaAPI, VehiclePriority (deleted, as before), TeslaTokenSlot (Phase 4), and test_vehicle_priority, test_teslable_pairing_status, test_teslaapi_command_401 and test_provider_outcomes_cloud. I read each resolution.
- **Range-diffs:** run in full. **The package is incomplete for Phase 3.** It shows entries 1 to 7 only, but entries 9 (4f9db3f5), 11 (9c25ca3a), 14 (ddf59bac), 15 (13f80d39), 16 (239bb70f) and 19 (2512b8a5) are also "!". Entry 11 holds the main #689/#690 resolution for the request helper. I reviewed all of them directly.
- **Main's tests from #666, #721, the MQTT log, Fronius, 3ba22d0f and #690** (`test_teslaapi_refresh_lock.py`) are byte-identical to main at every tip. #716's `test_distributor_voltage.py` changes only for the stack's names.
- **Suites:**
  - Phase 3: 1958 passed. Phase 3.5: 1932 passed. Phase 4: 2033 passed. Each also had 1 xfailed.
  - Per-commit run over origin/main..restack3/phase4: PER_COMMIT_RESULT
- **fix/disabled-teslable:**
  - The test fails on main's TeslaBLE.py (`'TeslaBLE' not in ['Gen2TWC', 'TeslaBLE']`) and passes with the fix.
  - Cherry-picked onto restack3/phase4 without conflict, it passes there too (503 provider/BLE tests).
  - `test_command_path_parity.py` is unchanged at every tip.

## Guarantees checked

- **#714, null voltage or current:**
  - Phases 3 and 3.5: VehicleEndpoint reads `value("voltage", 0) or 0` and `value("actualCurrent", 0) or 0`, and `phases` falls back to numberOfPhases. Main's test file is unchanged.
  - Phase 4 deletes currentAmps/currentPower, as the old Phase 4 did. The voltage fallback and its tests stay. See M4 for the current test.
- **#716 and 3ba22d0f, measured voltage:**
  - The maintainer's `convertAmpsToWatts` in distributeEVSEPower is kept in every phase. Gen2TWC falls back to defaultVoltage on every configured phase.
  - Phase 4's `_budgets` now converts the wiring cap at the measured voltage too (TWCMaster.py:510-519), so the two caps can't disagree. That was a real latent disagreement in the old Phase 4 and is now fixed. See M5 for the coverage.
- **e3710ec9, enabled():** `VehiclePriority.enabled()` and main's `_enabledFacade` tests are present in every Phase 3 commit until dd9540ba deletes VehiclePriority. After that nothing named VehiclePriority remains in lib, so no lookup can dispatch.
- **#689, 401 on commands:**
  - Phase 3's single helper (`_request` plus `_classify`) handles it:
    - an expired token is refreshed once and the request sent once more;
    - any other 401 clears the slot and queues saveSettings;
    - a 401 for a token replaced while the request was out sends the new token once;
    - a cleared slot sends nothing;
    - the tries budget bounds every loop.
  - Main's test is ported with a well-formed VIN and covers charge_stop, set_charging_amps, wake_up and set_charge_limit. The replaced-token case moved to test_provider_outcomes_cloud.
  - The stack is deliberately stricter than main in one case: an expired token refused again right after its refresh is cleared. The CHANGELOG says so.
- **#690, refresh serialization:**
  - Phases 3 and 3.5 use main's RLock. `refreshSlot` checks that the token it is spending is unchanged. The 401 handling, paste, delete and store all run under the lock (RLock, so a refresh from inside the 401 handling is reentrant).
  - Phase 4 removes the RLock entirely and keeps one mechanism, the slot's Condition claim. `_classify` swaps the lock for `slot.changes` captured at send time plus a compare-and-clear `slot.clear(sent)` (TeslaAPI.py:329, 384-389, 417-419).
  - Main's four refresh-lock tests pass unchanged against it. No `slot.lock`, `ifNeeded` or `_…Locked` remains.
- **#666, #721, the MQTT log, Fronius:** identical to main.

## Folds

- **87a9eff1 (caplog filter)** is now in 7b7e8d95 (Dissolve CarApiVehicle), the commit that adds `test_an_incomplete_vehicle_data_answer_logs_what_is_missing`. Its whitespace hunk on the `availableCurrent` line went to 0167cdd2, where that line lives.
- **38867464 (hold offers during the chargeStopMode 2 silence):**
  - The early return and the new test went into fc769e57 (Compute TWC offers). Its message now says why.
  - The comment wording ("no gate runs") and the `beat(m, s)` setup of `test_no_gate_runs_during_the_mode_2_silence` went into d68fe513 (Decide TWC start and stop).
  - The Phase 4 tip's TWCMaster.controlPass, test_control_tick.py and test_offer_characterization.py match old f1e98620 exactly.

## CHANGELOG

- The v1.4.0 section is byte-identical to main at every tip.
- Every stack line is under `## v1.4.1 - Upcoming`.
- Against the old heads, nothing stack-authored was lost:
  - "(closes #667)" is dropped from the reconciler line, since #667 closed in 1.4.0.
  - The old heads' deletions of released v1.4.0 lines (#667, the per-minute queue, the VehiclePriority "error" fix) are correctly not repeated.
  - The old Phase 3.5 rewrite of the released #659 line became a new v1.4.1 line (see M6).

---

## Critical

None.

## Important

None.

## Minor

### M1. The review package omits six changed Phase 3 commits

`restack3-r1-package.md`, Phase 3 section. The range-diff stops after entry 7. Entries 9, 11, 14, 15, 16 and 19 are "!" too. Entry 11 (9c25ca3a) holds the #689/#690 resolution for the request helper, the `slot.lock`/`nullcontext` block at TeslaAPI.py:357-374 in Phase 3.

- **Failure scenario:** a reviewer working only from the package never sees how a 401 is serialized in Phase 3. Nor does a maintainer reading the package before re-review on #705.
- **Fix:** regenerate the package with the full range-diff, or say that it is truncated.

### M2. Rebased commit messages don't mention the main guarantees they now carry

Only fc769e57's message changed. These commits now carry behaviour from main, and their messages don't say so:

- **7719490b:** sends the new token once after a 401 for a token replaced mid-request (#689).
- **9c25ca3a:** handles a 401 under the slot's lock.
- **72344f2c:**
  - removes main's per-slot RLock and `refreshSlot`'s spent-token check in favour of the Condition claim;
  - replaces the lock around 401 handling with `slot.changes` plus a compare-and-clear.
- **1c5beef8:** `_budgets` converts the wiring cap at the measured voltage.

**Failure scenario:** the maintainer reviewing #710 sees `self.lock = RLock()` (his #690) deleted in 72344f2c. The message says only "setTokens, clear and restore write under the lock". Nothing tells him the deletion is deliberate, or that the mechanism replacing it still covers paste, delete and the 401 race.

**Fix:** add one sentence per commit. For 72344f2c, for example: "This one claim replaces the per-slot lock: a 401 compares the slot's change count from send time and clears only the token it sent."

### M3. `_budgets` comment runs two comments together

TWCMaster.py:511-514 (Phase 4).

```
# Watts each group of endpoints may draw in all: the wiring for the
# Gen2 slaves, the fuses for the Gen3 units; each car limits itself
# The wiring's amps convert at the voltage the TWCs measure, as the
# policy's amps do, so the two caps never disagree
```

The first sentence has no full stop, so it reads "each car limits itself The wiring's amps…".

- **Failure scenario:** none at runtime. It's a readability nit in a comment that explains a non-obvious choice.
- **Fix:** add a full stop, or leave a blank `#` line between the two comments.

### M4. Phase 4's #714 current test doesn't exercise the path that reads current

`tests/unit/test_teslaapi_evse_unplugged.py:54` (Phase 4). The test asserts `_newer(vehicle, "actualCurrent", -inf) == []` with the default `twc=False`. The only production reader of actualCurrent is `_standIn` (Reconcile/Belief.py:32), and it calls `_newer(..., twc=True)`, which excludes the TeslaAPI source anyway. So the test pins a combination nothing runs.

- **Failure scenario:** a later change makes `_standIn` (or a new reader) treat a null current as 0 or compare None. This test still passes.
- **Fix:** assert through `_standIn` or `Belief`'s public answer for a car whose only current reading is a null from TeslaAPI. Or say in the test that, since 1c5beef8, no consumer reads a vehicle's own actualCurrent. Then the test documents a guarantee instead of pinning a helper.

### M5. The wiring-budget voltage conversion is pinned only incidentally, in the safe direction

TWCMaster.py:516 (Phase 4) and `tests/unit/test_charging_points.py:268`.

I reverted `_budgets` to `wiringMaxAmpsAllTWCs * defaultVoltage * numberOfPhases`. Only `test_a_car_read_under_the_sleep_pilot_still_gets_the_share` fails, getting 47.4 A instead of 48 A. That test is named for the sleep pilot, and its case is the undershoot.

The dangerous case is #716's: defaultVoltage 400 on 3 phases while the TWCs measure about 240 V. There the old formula budgets 48 × 400 × 3 W, which converts back to 80 A at the TWC. Nothing pins that case. The per-TWC caps limit the harm today.

- **Failure scenario:** a refactor of `_budgets` reintroduces the defaultVoltage product. One test changes its expected value, and a reviewer may "fix" the test rather than the code.
- **Fix:** add a #716-shaped case to `test_distributor_voltage.py`: two TWCs measuring 240 V on 3 phases, defaultVoltage 400, wiringMaxAmpsAllTWCs 48. Assert that the summed pointAmps stays at 48 or below.

### M6. The v1.4.1 #659 entry restates the released v1.4.0 one

CHANGELOG.md:26 (Phases 3.5 and 4) and CHANGELOG.md:110 (v1.4.0).

- **v1.4.0** already says "Allow Owner API commands per vehicle when Tesla reports `command_signing: off`… (#659)".
- **The new v1.4.1 line** opens by restating that ("A vehicle Tesla lists with `command_signing: off` sends its commands through the free Owner API…") before the parts that are new: the place ahead of Fleet in the order, the hand-off to Fleet on refusal, and the 410/412 latch.

**Failure scenario:** a 1.4.1 reader sees #659 listed twice and can't tell what changed.

**Fix:** lead with the change, for example: "Owner API commands for a car listed with `command_signing: off` now sit just ahead of the Fleet API in the command order, and go to the Fleet API once Tesla refuses them; a 410 or 412 … (#659)".

### M7. A user-facing CHANGELOG line cites an internal incident date

CHANGELOG.md:29 (all three phases): "(#698 for lowering, the 2026-10-11 stray command)". The date refers to an internal soak event that users can't look up. This predates the restack, but the restack is what puts it under v1.4.1.

- **Failure scenario:** a 1.4.1 reader has no referent for "the 2026-10-11 stray command".
- **Fix:** drop the parenthetical, or keep only "(#698)".

## Not findings

These were checked and are fine:

- **Phase 4 reads `sent = slot.changes` separately from the token in the Authorization header** (TeslaAPI.py:329-336). A token change between the two reads makes `_classify` treat the 401 as "replaced meanwhile" and resend once. The tries budget bounds it. It costs at most one extra request and loses no token.
- **`from contextlib import nullcontext` (Phases 3 and 3.5)** is Python 3.7 or later, so it's fine on 3.8.
- **The fix branch's release-in-`__init__`** works because `registerModule` refuses names in `releasedModules`. The loader registers after `__init__`, and the guard holds there.
- **No CHANGELOG line for fix/disabled-teslable** is right. 1.4.0's VehiclePriority honoured `enabled()`, so the bug exists only in code that hasn't been released.
