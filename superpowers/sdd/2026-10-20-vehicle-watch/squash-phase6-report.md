# Phase 6 squash report

Branch `vehicle-model/phase6-squashed` (worktree `scratchpad/wt-sq`), base `36e69be6`, tip **`62a0e08c`**, 10 commits. Author Mike Bishop <<email>> on every commit. Not pushed. `vehicle-model/phase6` and `backup/phase6-pre-squash` were left at `ac3e74a1`.

## Groups

| # | New SHA | Subject | Original commits folded |
|---|---|---|---|
| 1 | 81a6f7e9 | Read the charge-port door on the sleep-safe ping; a closed door is an unplug | ecca0092, plus the log-line shortening from 1532a381 |
| 2 | 6cc3eb6b | An asleep car draws nothing; asleep after Charging, it has finished | e8a7f97b |
| 3 | 5cc7ec25 | Add a monthly budget for paid vehicle reads, kept across restarts | 4ae5026a |
| 4 | d282ead4 | Watch cars no TWC or live feed covers; read one when something changes | bc1ff751, de5e0255, b613a784; the door read and RETRY/anonymous parts of f3780011 and f9270375; the Policy.readsBattery charging-read rule, cloudOnly and the held-command check, and the matching tests from ac3e74a1 |
| 5 | 92c91bc0 | Hear an away car come back; read a car only the cloud sees on a clock | 65bdc048, 91adebf7, fb8b0c9e (Watch part), the miss/scan parts of f3780011 and f9270375, 53fa4364, and the API-only rule from ac3e74a1 (written directly in its final form) |
| 6 | 43de24f6 | Read the watched car a consumption step may come from | 9c30e125, the courtesy-window load step from f3780011, and pollEMS from 7c1b2d8e |
| 7 | 98af7689 | Scan for cars from Docker; say why when no range scan can run | 58304f4a, plus radioUp/RADIO_DOWN, the warning text and the radio-down tests from ac3e74a1 |
| 8 | 5147b6e6 | Run the watch on the control tick; show it on the Vehicles page | 7c1b2d8e (launcher, tick, enabled, page), the HTTPControl part of 1532a381 |
| 9 | ea1755f3 | Let the watch replace the deferral ladder and the half-hourly battery refresh | e202554c, the TeslaAPI parts of fb8b0c9e and 1532a381, and the cloudUpdateInterval comments in etc/*.json from b8d3b828 |
| 10 | 62a0e08c | Document the vehicle watch | b8d3b828, 56a9753a, and the doc parts of 58304f4a, f3780011, f9270375, b613a784, ac3e74a1 |

None of these ever appears in the history: the away-location read, its per-stretch bookkeeping, the driving re-read, the cloud status checks for a lost BLE car, the "falls back to slower checks" warning, and the cloudUpdateInterval log line. I grepped every added line in the new range to confirm.

## Deviations from the suggested grouping

- **Wiring moved before polling.** Commit 8 (wiring) now comes before commit 9 (polling), so no commit removes the half-hourly refresh while the launcher still doesn't run the watch. Both commits pass in this order.
- **Docs:** all doc text goes in commit 10. The exception is the etc/*.json cloudUpdateInterval comments, which went to commit 9.
- **pollEMS** is in commit 6, so the load-sample hook never sits in TWCManager.check_green_energy. Its test stays in commit 8's test_control_tick, which is where the original put it.

## Code an earlier new commit adds that a later one changes

I blame-checked every removed line against earlier commits in the new range. Every hit is a small extension of a line, not an old path being replaced:

- Commit 4 swaps the budget line from commit 3 to `settingsOf(config)`.
- Commit 5 extends things commit 4 added: the import lines, the DEFAULTS line (adding scanAwaySecs and returnKph), RETRY gaining TWICE, KINDS gaining "scan", the parameters of `_source`, `_read` and `readNow`, and status(). It also turns `_source`'s plain ping into the miss-aware ping, with the scan on a second miss.
- Commit 6 adds names to the import and DEFAULTS lines.
- Commit 7 makes `radio()` check `radioUp`, and changes the scan docstring to "(see canScan)".

## Tests (full suite, per commit, run from each commit's checkout)

I ran the suite on the commits before rewording their messages. Each tree matches its reworded commit (tree hashes in `scratchpad/sq6/map.txt`).

| Commit | Result |
|---|---|
| 81a6f7e9 | 2277 passed, 1 xfailed |
| 6cc3eb6b | 2282 passed, 1 xfailed |
| 5cc7ec25 | 2288 passed, 1 xfailed |
| d282ead4 | 2328 passed, 1 xfailed |
| 92c91bc0 | 2358 passed, 1 xfailed |
| 43de24f6 | 2365 passed, 1 xfailed |
| 98af7689 | 2380 passed, 1 xfailed |
| 5147b6e6 | 2385 passed, 1 xfailed |
| ea1755f3 | 2384 passed, 1 xfailed |
| 62a0e08c | 2384 passed, 1 xfailed |

No commit failed.

## Trees match

```
$ git diff ac3e74a1 62a0e08c          # prints nothing, exit 0
$ git rev-parse 62a0e08c^{tree} ac3e74a1^{tree}
9ab474509302e4fcf1cc2679aeb76e4b85adfa98
9ab474509302e4fcf1cc2679aeb76e4b85adfa98
```

Because the trees match, `tests/unit/test_command_path_parity.py` is identical to ac3e74a1's.
