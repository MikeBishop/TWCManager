# Fix: home moved to a position taken before the car reached its TWC

## Evidence: box, 2026-10-23, API-only (no BLE, no telemetry)

- 12:19: unplug. Neither plug check could answer.
- 12:39: the watch's read found the car away and disconnected. That read recorded a position fix about 4.2 km from home, and the original limit was restored (paid).
- 12:48:04: the car was plugged back in at home, and the Gen2 TWC read its VIN.
- 12:48:17: "Home set to <VIN>'s position on a TWC". `TWCMaster` (around line 1632) called `Presence.learnHome` with `vehicle.latest("lat"/"lon")`. That was still the 12:39 away fix: 9 minutes old, under `HOME_FIX_MAX_AGE` (600 s), and outside the radius, so home moved 4.2 km to it.
- 12:48:19: "chargeLimit: not here (away)". The car on its own TWC counted as away, and the limit was never applied.
- Home has been restored on the box by hand.

## Required

`learnHome` (`lib/TWCManager/Vehicle/Presence.py`) moves or sets home only from a fix that shows the car where the TWC is.

- **Not BLE:** a fix that isn't from BLE must be dated, by its GPS time, no earlier than the car's `plugIn` mark minus a short parking slack. Use 300 s as a named constant beside `HOME_FIX_MAX_AGE`, with a one-line reason: a parked car's last GPS fix is from when it stopped, a minute or two before the plug went in.
- **BLE:** a BLE location read is exempt from the plug rule, since BLE answers only within range. It keeps the existing age rule.
- **Both call paths** must follow the rule:
  - the TWC VIN read in `TWCMaster`;
  - `Presence.observe`'s lat/lon branch, while `twcVinAt > NEVER`.
- Check the order of events: at the VIN-read call, is the `plugIn` mark already set for this session? If not, use the plug session's start or the `twcVin` time, whichever the code actually has. State which one you used.

## Tests

Each test must fail without the fix.

- The bug: an away fix 9 minutes before the plug-in, then a TWC VIN read. Home must not move, and the car must count as home.
- A fix 60 s before the plug-in, outside the radius, with no home yet or with home elsewhere: home is learned. That's the legitimate case.
- A BLE fix: unchanged.

## Constraints

- Work on `vehicle-model/phase5` at its current tip, worktree `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-vm5`.
- One new commit, subject "Learn home only from a fix taken after the car reached its TWC". End the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Then rebase `vehicle-model/phase6` (worktree `wt-vm6`) onto it.
- Update the CHANGELOG and docs sentence that describes how home is learned.
- Python 3.8, black. Comments say why; no history, no phase IDs. Lib growth should be minimal; report it.
- Mutation-check the tests. Run the full suite on phase5 and phase6:
  `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`
  Parity paid counts must not move.
- Never print home coordinates, tokens or the owner's car name. Don't push. No bare `git stash`.

## Report

Write it to `.superpowers/sdd/2026-10-20-vehicle-watch/homefix-report.md` in the session worktree.
