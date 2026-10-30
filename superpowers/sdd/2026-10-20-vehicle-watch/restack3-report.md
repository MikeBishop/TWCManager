# Restack 3: Phases 3–6 onto main 02822e74, with the late fixes folded in

## Summary

Base: `origin/main` = 02822e74, the maintainer's merge of Phase 2 (#704 at 26fc3f3d) onto d814be60. His resolutions are taken as settled:
- the distributor converts the policy's amps with `convertAmpsToWatts`;
- VehiclePriority keeps main's `enabled()` alongside `providers()`;
- TeslaAPIEVSE is deleted, and the #714 test is ported to VehicleEndpoint.

All branches are local and nothing was pushed. The work tree is scratchpad `wt-r3`.

| Branch | Tip | Commits on base | Full suite at tip | lib .py lines vs main (28006) |
|---|---|---|---|---|
| fix/disabled-teslable | 09c60309 (now also 33aef75b on origin, not mine) | 1 | 1584 passed, 1 xfailed | +8 |
| restack3/phase3 | ae3d2e3f | 19 | see "Final suites" | −430 |
| restack3/phase3.5 | ede3d143 | +9 | see "Final suites" | −454 |
| restack3/phase4 | 1bd6423d | +14 | see "Final suites" | −1369 |
| restack3/phase5 | 9be4228a | +25 | see "Final suites" | −1356 |
| restack3/phase6 | 92be7eef | +11 | see "Final suites" | −783 |
| restack3/707 | bd990bba | 1 (on origin/main) | docs only | — |

The local branch restack3/phase2 is deleted because it is merged. Tags preserve each stage:
- `r3-folded-<phase>` is the folded stack on the old base;
- `r3r1-<phase>` is the stack before the review fixes.

## Fold stage (before the rebase; every tip tree equal to its original)

`git diff vehicle-model/<p> r3-folded-<p>` was empty for phases 2, 3, 3.5, 4, 5 and 6, and `docs/gen3-vehicle-model` matched too.

- **Phase 2** (since dropped, because main merged #704 as pushed):
  - 26fc3f3d was split five ways (60836e47, edeaa2d7, b6d6265f, 4118bec0, 415493d7).
  - 4c40dd70's lib change went into edeaa2d7 and its test into 4911a0e8.
  - Now superseded by fix/disabled-teslable.
- **Phase 3:** no folds.
- **Phase 3.5:**
  - f6eb5261 (caplog filter) folded into 85b5d862 (Dissolve CarApiVehicle).
  - Its whitespace hunk went into 82ef6470, which owns that line.
- **Phase 4:**
  - cf65abf5 (hold offers during the chargeStopMode 2 silence) is split: the lib change and control-tick tests went into 7bc39e19 (Compute TWC offers), and the gate test and comment into e69b85c8 (Decide TWC start and stop).
  - Kept as features: ff84ec4c (bug also on main), ca1bf711, 3c4b865b, dc2f53e8, 993c887b and 3ac364a6.
- **Phase 5** (35 commits become 25):

  | Fix | Target |
  |---|---|
  | 7e7d3517 (learn home only after the car reached its TWC), lib and tests | c0f91bc6 |
  | 7e7d3517 docs | 4f9f9c80 |
  | 9f167500, offer-map zeroing | ef4794ea |
  | 9f167500, heardFrom flag | 17f7cd77 |
  | 5b2b77d7, TeslaAPI and Reconciler comment trims | 9502ed6c |
  | 5b2b77d7, Presence | 17f7cd77 |
  | 72e758ff | 1fdeb0c1 |
  | a960d5d2 | 19ac1d63 |
  | 48c112c0, 64a822f2 | 17f7cd77 |
  | 4977ef3a, PolicyCustomization and test | 4f9f9c80 |
  | 4977ef3a, Fleet Telemetry doc and log line | 29c7b4b1 |
  | 66129c6e line 1 | b2be238e |
  | 66129c6e line 2 | 29c7b4b1 |
  | b48dd13b | be8d90b2 |

  Kept separate: be8d90b2 (cloud hold), a9d9950c (plug-in scan), a7f11121, 48474e05 and ee237bd4.
- **Phase 6:** f538b780 (the replay test) is kept. It pins behaviour from Phases 2 to 5, and no single Phase 6 commit owns it.

## Rebase onto 02822e74: conflicts and resolutions

### fix/disabled-teslable
- 4c40dd70 cherry-picked onto origin/main with its original message.
- 1584 passed, 1 xfailed.
- The new test fails on main's TeslaBLE.py.

### Phase 3
Phase 3 doesn't depend on 4c40dd70; its tip passes without it.

- **#689, 401 on commands (7719490b, 9c25ca3a):**
  - Main added `slotCommandFailed` to the legacy paths. Its "token replaced by another thread" rule is ported onto the stack's single request path.
  - In Phase 3 this lives first in `_paidPost`/`_commandUnauthorized`, then in `_request`. The 401 is handled under main's `slot.lock`.
  - A 401 for a token that changed while the request was out sends the new token once, and never clears it. A cleared slot sends nothing.
  - An expired token is refreshed once. Any other 401 clears the slot.
  - As the legacy paths are deleted, `slotCommandFailed` goes with them. Main's `test_teslaapi_command_401.py` was ported step by step to the provider path (`api.command`, `_paidPost` for the wake), with the well-formed VIN, and covers charge_stop, set_charging_amps, wake_up and set_charge_limit.
  - The replaced-token case is `test_provider_outcomes_cloud.py::test_a_401_for_a_token_replaced_meanwhile_sends_the_new_one_once`, which also covers a slot cleared mid-request. I mutation-checked it: it fails without the check.
- **e3710ec9, enabled():**
  - Main's `enabled()` tests (`_enabledFacade`) are kept in `test_vehicle_priority.py` until dd9540ba deletes VehiclePriority.
  - After that nothing named VehiclePriority remains in lib, so nothing can dispatch.
  - The maintainer had black-formatted `test_vehicle_priority.py`. Its conflicts were resolved by a 3-way merge of black-normalised versions.
- **CHANGELOG:**
  - The v1.4.0 section is never edited. The stack's deletions of released lines (#667, the per-minute queue, the VehiclePriority "error" fix) are not repeated.
  - Stack lines are inserted into "v1.4.1 - Upcoming" by section.
  - "(closes #667)" is dropped from the reconciler line, because #667 closed in 1.4.0.
  - The heldLimits-migration line, which 33acc5ef had placed in v1.4.0 by context, moved to Upcoming. f933cbe5 replaces it, because heldLimits never shipped.
- **Other test ports:**
  - Main's `test_pairing_debug_output_alone_is_not_a_sent_request` is kept.
  - `test_teslaapi_command_401` follows `getCarApiVehicles()` → `carApiVehicles` at 239bb70f.

### Phase 3.5
- **Dissolve CarApiVehicle:** the 401 check moved to the `car` record; the 401 test uses `add_home_vehicle` and `api.registry`.
- **Owner command_signing off:** the owner pre-check moved into `_classify` (theirs). The 401 check was kept, and the test passes `slot=`.
- **CHANGELOG:** the released v1.4.0 #659 line was restored, and the stack's change became a new v1.4.1 line.

### Phase 4
- **#690, two mechanisms merged into one (72344f2c):**
  - Phase 4's slot-level Condition claim stays. Main's per-slot RLock, `refreshSlot`'s spent-token check, `ifNeeded` and the `with slot.lock` wrappers around paste, remove and store are removed.
  - The 401 path records `slot.changes` at send time. `_classify` resends once when it changed, and clears only with `slot.clear(sent)` (compare-and-clear).
  - Main's four `test_teslaapi_refresh_lock.py` tests pass unchanged on the merged mechanism.
- **#716 and 3ba22d0f, voltage (1c5beef8):**
  - Phase 4's `_budgets` priced the Gen2 wiring cap at defaultVoltage while the policy's amps use the measured voltage. With defaultVoltage 400 on three phases and TWCs measuring 240 V, the old formula budgets 80 A for 48 A of wiring.
  - `_budgets` now uses `convertAmpsToWatts` (measured voltage, with defaultVoltage on every configured phase as the fallback).
  - Tests:
    - `test_distributor_voltage.py`'s harness follows the stack's names, and `pointAmps` replaces `_evseTargetAmps`.
    - A new #716-shaped case was added: two TWCs, 400 V default, 48 A wiring, sum ≤ 48. It fails with the old formula at 80 A.
    - The sleep-pilot tests now expect 48 A (was 48·240/243 = 47.4 A). These are `test_charging_points` here and the Phase 6 replay test, where the offer goes from 47 to 48.
- **#714 at 1c5beef8:** `currentAmps` and `currentPower` are gone. The current test now pins that a null TWC current never stands in as charging (`Belief._standIn`), and says that nothing reads a car's own actualCurrent. It fails if `_newer` stops filtering None. The voltage-fallback tests are unchanged.
- **Comment guard:** b54a2dee's no-issue-numbers guard required dropping "(#721)" from main's createServer comment.
- **test_distributor_loop at 1bf6d440:** its mocked slaves gained zero voltages, because the measured-voltage conversion read MagicMock volts. 1c5beef8 removes them with the harness.
- **CHANGELOG:** the RS-485 line goes into Upcoming Bugfixes.

### Phase 5
- **CHANGELOG:**
  - Lines go into Upcoming.
  - Per the ruling, these lines are dropped because they describe bugs only stack code had:
    - 72e758ff's "stayed driving";
    - a9d9950c's "came home out of BLE range";
    - ee237bd4's "TWC current as charging" (the 1.4.0 heartbeat never started a car drawing ≥ 1 A).
  - Every other Bugfixes line describes released behaviour.
- **c0f91bc6's message** now says the docs "describe the BLE fix and the GPS dating"; the home-reach rule's docs land in 4f9f9c80.
- **#666 test:** main's `/api/checkArrival` endpoint is removed at "Decide each message by one applicability rule", so `test_post_without_content_length` now posts to `/api/saveSettings`.
- **#689 port:** the `Outcome` → `O.Outcome` import change at "Import vehicle-model modules by name; trim" carried over to the 401 lines.
- **Conflict at "Warn when a car's Fleet Telemetry config lacks needed fields"** (the "config" purpose): `_classify` keeps the `sent` parameter.

### Phase 6
- **Dockerfile:** main's `ARG TWC_REF` and `git clone --branch` were kept, with the stack's `bluez` added.
- **Replay test:** 48 A and offer 48, as above.
- **#714 current test:** "Watch cars no TWC or live feed covers" renames `Belief._standIn` to `standIn`, and the test follows the rename.

### #707
Rebased cleanly onto origin/main. The docs diff is identical to the original commit's.

## Review round (restack3-r1-review.md)

- **M2:** one sentence was added to each of the messages for 7719490b, 9c25ca3a, 72344f2c (the reviewer's wording) and 1c5beef8.
- **M3:** the `_budgets` comment's first sentence now ends with a full stop.
- **M4, M5:** done as above, and mutation-checked.
- **M6:** the v1.4.1 #659 line now leads with what changed.
- **M7:** dropped "the 2026-10-11 stray command", leaving "(#698 for lowering)".
- **M1:** the package; ignored, as instructed.

## Verification

- **Per commit:** every commit was checked before the review round; all passed, with 1 xfailed each:
  - Phase 4: 14/14, 1945 → 2033;
  - Phase 5: 25/25, 2033 → 2347;
  - plus the Phase 3, 3.5 and 6 tips.

  Logs are in `scratchpad/r3/verify-phase4-r0.log` and `verify-phase5-r0.log`. The review round changed only commit messages, CHANGELOG text, one comment and two tests, so the final suites were run at the tips.
- **Parity:** `tests/unit/test_command_path_parity.py` is byte-identical to the originals at the Phase 4, 5 and 6 tips. No paid count moved. 51 tests pass at Phase 4.
- **CHANGELOG audit:** for every commit from origin/main to restack3/phase6, the v1.4.0 section and everything older is byte-identical to main.
- **black:** run on every .py file resolved or edited.
- **Python 3.8:** `contextlib.nullcontext` (Phases 3 and 3.5) is 3.7+. Nothing newer is used.

## Final suites

Full suite at each tip, after the review round:

| Tip | Result |
|---|---|
| restack3/phase3 ae3d2e3f | 1958 passed, 1 xfailed |
| restack3/phase3.5 ede3d143 | 1932 passed, 1 xfailed |
| restack3/phase4 1bd6423d | 2034 passed, 1 xfailed |
| restack3/phase5 9be4228a | 2348 passed, 1 xfailed |
| restack3/phase6 92be7eef | 2464 passed, 1 xfailed |

`test_command_path_parity.py` passes at each tip: 51 tests at Phase 4, 120 at Phases 5 and 6. Its file is byte-identical to the originals, so no paid count moved.

## Concerns

- **Behaviour change versus main:** the Gen2 wiring budget is now priced at the measured voltage. On a TWC measuring above defaultVoltage, the distributor offers the full wiring amps (48 A instead of 47.4 A at 243 V). Below defaultVoltage, the budget is lower than before. This is the "never disagree" fix the brief asked for. The per-TWC wiring caps in amps still apply on every offer.
- **Read path:** the replaced-token 401 rule also covers reads, because `_request` is the single path. That goes beyond main's commands-only fix.
- **Phase 3 is stricter than main in one case:** a refresh that fails while not unreachable refuses commands on that slot until a refresh succeeds. This is Phase 3's existing design; main only returns False.

## restack4: Phases 4 to 6 onto main 686b36ec

The maintainer merged the old pushed heads of Phase 3 (#705, fe9eca64), Phase 3.5 (#706, 87a9eff1) and #707. His conflict resolutions are taken as settled. Nothing was pushed.

| Branch | Tip | Commits on its base | Full suite at tip |
|---|---|---|---|
| restack4/phase4 | eb7e65e0 | 15 on origin/main (1 new, then the 14 of Phase 4) | 2023 passed, 1 xfailed |
| restack4/phase5 | a50ff0de | 25 | 2337 passed, 1 xfailed |
| restack4/phase6 | a97abeff | 12 (11, plus the coordinator's 7011795a kept) | 2454 passed, 1 xfailed |

`test_command_path_parity.py` is byte-identical to the original Phase 4, 5 and 6 files, and to origin/vehicle-model/phase6. No paid count moved. For every commit, the v1.4.0 and older CHANGELOG sections are byte-identical to main.

### Phase 4: conflicts
Only "Refresh Tesla tokens off the serial loop, one refresh per slot at a time" conflicted, in `TeslaAPI._classify`.

- Main's version guards a 401 under `slot.lock` with `sent` = the access token: `slot.accessToken != sent` returns _REFRESHED, or REFUSED when the slot is cleared.
- Phase 4 removes `slot.lock`. Its change was applied to his version, keeping one mechanism:
  - `sent` is `slot.changes` at send time, and `slot.changes != sent` returns _REFRESHED, or REFUSED when cleared;
  - the dead-token clear is a compare-and-clear, `slot.clear(sent)`.
- The replaced-token guarantee holds: the new token is resent once, and nothing is sent if the slot was cleared.
- His comment's "(#689)" went with the rewrite, as Phase 4's no-issue-number guard requires.
- The commit message's sentence still holds: "a 401 compares the slot's change count from send time and clears only the token it sent".
- His `test_teslaapi_command_401.py` (token replaced, dead token cleared) and `test_teslaapi_refresh_lock.py` pass unchanged.

All other Phase 4 commits applied cleanly. "Keep running when the Gen2 RS-485 adapter is absent" puts its CHANGELOG line into Upcoming Bugfixes.

### Carried from restack3 (not in main)
- **New first commit, "Say each change once in the v1.4.1 changelog":**
  - M7: "(#698 for lowering, the 2026-10-11 stray command)" becomes "(#698 for lowering)".
  - "(closes #667)" is dropped from the reconciler line, because #667 closed in 1.4.0.

  No Phase 4 commit touches those lines, hence the separate commit.
- **Test:** `test_teslaapi_command_401.py::test_token_cleared_while_command_ran_sends_nothing_more` was added, a slot cleared while the command was out. It went into the Phase 4 refresh commit, which owns the 401 path. Main's tests cover only a replaced token. restack3 had this case in test_provider_outcomes_cloud.
- **Stack-only bug lines** (72e758ff, a9d9950c, ee237bd4): these are Phase 5 lines, already absent from restack3/phase5 and so from restack4/phase5. None was in main.

### Judged equivalent (not carried)
- **M6:** main's #659 line already leads with the change ("Owner API commands for a `command_signing: off` vehicle sit just ahead of the Fleet API…"). It sits under Bugfixes, while restack3 had it under Architecture.
- **401 guard placement:** main does it in `_classify`; restack3/phase3 did it in `_request`. The behaviour is the same.
- **Main's narrower `test_teslaapi_command_401.py`** in place of restack3's port. He says test_provider_outcomes_cloud covers refresh-once, a dead token and a 403. restack3's extra cases were the wake_up and set_charge_limit paths through the same `_request`/`_classify`, so they add no distinct path.
- **CHANGELOG line order** within v1.4.1, and black reformatting of one `test_teslable_pairing_status.py` statement.

### Phases 5 and 6
- **Phase 5:** rebased from 1bd6423d. Only CHANGELOG conflicts, resolved into Upcoming. The diff against restack3/phase5 is exactly main's Phase 3/3.5 resolutions plus the Phase 4 changes above.
- **Phase 6:** rebased from 9be4228a with 7011795a ("Count every charger the meter sees in the charger load"). Its CHANGELOG line goes into Upcoming Bugfixes.
