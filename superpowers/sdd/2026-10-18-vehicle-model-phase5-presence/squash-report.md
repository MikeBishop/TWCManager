# Phase 5 squash report

**Status:** DONE. Branch `vehicle-model/phase5-squashed` has 17 commits on 044e5262. Its tip is `34784a64c6c269e5c1cb16b28344cb5405263915`.
Worktree: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-sq`.
`vehicle-model/phase5` and `backup/phase5-pre-squash` still point at 4f2a3275 and were not touched. Nothing was pushed.

## Commits (old numbers refer to squash-commits.txt)

| # | SHA | Subject | Old commits | Brief group |
|---|-----|---------|-------------|-------------|
| 1 | 267adc37 | Read config defaults as one-liners | 1, 2 | A |
| 2 | fc7bc01e | Log reconciler outcomes, paid requests and telemetry changes at INFO | 3, 4 | B |
| 3 | 48255ca7 | Compute presence from events; one home check | 5, 6, 7, 29 | C (+29) |
| 4 | 19615d01 | Decide each message by one applicability rule; hold within the paid budget | 8, 9, 32, 35 | D (+32) |
| 5 | ecf80c13 | Release the car's own limit when the policy has none | 10, 11, 12 | E (+12) |
| 6 | c60f713c | Trim the vehicle model | 13–19 | F |
| 7 | 0af635b0 | Apply a charging point's own commands; plugged follows plug events | 20, 21, 22 | G (+20) |
| 8 | 2cd65106 | Attribute a VIN-less plug | 23, 24, 31, 33 | H (part) |
| 9 | 025bb766 | Show presence and pending commands on the Vehicles pages | 25, 26 | I (part) |
| 10 | ae5accc7 | Import vehicle-model modules by name; trim | 27, 28, 36, 37, 38 | P (+36, 37) |
| 11 | 1a2592aa | Leave a sleeping car alone until it shows life or must wake | 39, 40, 44, 45 | J (part) + I (44, 45) |
| 12 | cbed427b | Run BLE scans and attribution reads on the BLE worker | 42, 43, 46, 47 | K + H (46) + Q (47) |
| 13 | f03b9db3 | Only live evidence is a sign of life; a BLE range scan is a sighting | 58, 59, 60, 61, 62 | N + J (60–62) |
| 14 | 23216824 | Wake a car only when it is expected to charge | 48, 49, 57 | L (minus 12) |
| 15 | 833b1df8 | A returning car tries BLE first; restore at the drive start; hold a driving car quietly | 50–56 | M + H (54, 56) |
| 16 | 858c9e3c | Check the car on a Gen2 status change; drop the timed departure reads | 34, 63–73 | O (minus 20) |
| 17 | 34784a64 | Document leaving a sleeping car alone and how home is learned | 30, 41 | Q (minus 29, 47) |

All 73 commits are accounted for, each exactly once. Every message has a plain subject, a body with no history or IDs, and the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer. The original author is kept.

## Deviations from the groups, with reasons

How I found them: I cherry-picked every candidate order onto 044e5262. When a commit conflicted, a script found the smallest set of earlier commits it needed. The order below cherry-picks cleanly.

- **Commit 27 splits the history.** It changed the import style to `Capability as C`. Every later commit is written against that style, so nothing after 28 can move before 27/28 without a conflict. The brief's late fix-ups for C, D, H and I were therefore folded into groups that come after P, or into P itself.
- **29 → C** (docs for event-based presence): 32 edits the docs that 29 writes, so 29 must come first.
- **32 → D**: 32 needs 9's `learnHome(master, vehicle, lat, lon)` signature.
- **12 → E**: it applies cleanly in its own position, and moving it to L would cross the 27 split. Its theme, a limit raise, fits E.
- **20 → G**: 22 (and later commits) change `test_gen2_unplug.py`, which 20 creates, so 20 cannot move to O at the end.
- **36, 37 → P**: 36 needs 33, and 37 needs 27's rename. Both are trims.
- **38** joined P directly, as the brief planned.
- **44, 45 → J (commit 11)**: the test 44 changes (`test_pending_shows_a_limit_held_asleep_until_the_car_reports_it`) needs J's asleep hold (39/40). With 44 in I, the I commit failed that test.
- **46, 47 → K**: 46 needs 42/43, and its BLE job raised a NameError without 39/40, so K comes after J. 47 is changelog text for 46.
- **J split, and 60–62 joined N (commit 13)**: 62 needs 46 and 58/59, so 60–62 come after K and N. Commit 11 holds 39/40; commit 13 holds 58–62.
- **54, 56 → M**: 54 needs 39–53, and 56 needs 55.
- **Group order** (changed from the brief's A..Q): A B C D E F G H I P J K N L M O Q.

## Per-commit test counts (tests/unit + tests/EMS, run at each new commit)

| # | Result |
|---|--------|
| 1 | 1960 passed |
| 2 | 1965 passed |
| 3 | 1989 passed |
| 4 | 2038 passed |
| 5 | 2041 passed |
| 6 | 2040 passed |
| 7 | 2064 passed |
| 8 | 2091 passed |
| 9 | 2100 passed |
| 10 | 2101 passed |
| 11 | 2124 passed |
| 12 | 2131 passed |
| 13 | 2140 passed |
| 14 | 2154 passed |
| 15 | 2165 passed |
| 16 | 2189 passed |
| 17 | 2189 passed |

Every run had 0 failures and 1 warning. The tests ran on an earlier build of the same 17 trees. Only the messages of commits 10, 15 and 16 changed after that (history phrasing removed), and every commit's tree was checked identical. On the first build, which put 44/45 in I and K before J, commits 9–12 failed (1 failure, then 1, 10 and 10). Those failures drove the J/K/N reorder.

## Tree identity

`git diff 4f2a3275 34784a64` prints nothing (0 bytes).

## Lib line count at the tip

- `lib/**/*.py`: 26,356 lines. The base 044e5262 had 26,531, so this is 175 fewer.
- `lib/TWCManager/Vehicle/**/*.py`: 9,470 lines.
