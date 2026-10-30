# Phase 5: fix the second final review's findings

Branch vehicle-model/phase5, tip cf89bf5f, restacked onto the new main. Review: final-review-2.md in this directory. Rulings: the last block of progress.md in this directory.

## Fix (each with a test that fails without it; mutation-check it)

1. **Finding 1: home learned from a retained copy.** `learnHome` (and anything else that moves home) refuses unless the lat and lon observations were actually seen (`seen` True), not retained or redelivered.
2. **Finding 2: Fleet asleep hold (user ruling, option a).**
   - A no-wake cloud attempt to a car its free online check found asleep ends as a hold, `asleep`, like BLE: no paid send and no blind retry.
   - It follows the existing BLE asleep-hold mechanism: re-plan only on a sign of life, and repeated asleep readings don't re-plan.
   - The online re-check:
     - **With a live feed covering the car:** no re-checks at all; the feed's state change is the sign of life.
     - **Otherwise:** no more often than every 15 min while the car is HOME, and every 30 min otherwise.
     - Put those two numbers where Phase 6's watch will be able to share them, not as magic numbers in Run.py.
   - Parity row 18 (the Fleet restore to an asleep car) moves from paid (0,0,2) to (0,0,0) by this ruling. That is the one parity edit allowed; any other count that moves is a stop-and-report.
   - The CHANGELOG and Vehicle_TeslaBLE.md already describe this behaviour; make them exact.
3. **Finding 3: scan-only ping answer.** When the sleep state is unknown (only the range scan answered), `pick.fits` and `checkPlug` must not run a BLE charge read that could wake the car. Gate the read on `asleep(v) is False`, or treat unknown the way the review suggests.
4. **Finding 4:** `TWCSlave.heardFrom` goes back to what is actually read (a bool, or remove it), with the comment fixed.
5. **Finding 5:** `withdrawOffers` resets `master.offered`.
6. **Finding 6:** the Fleet Telemetry doc notes that the config check warns daily for cars on the account that can't stream.
7. **Finding 7:** reproduce the "may repeat a 'not here' line" residual (PolicyCustomization.md:95-96) with a test. If it can't happen, delete the sentence; if it can, say so precisely.
8. **Size cuts** (~−8) as listed in the review.
9. **Finding 8:** rebuild `.superpowers/pr-drafts/pr-notes.md` for Phase 5 from the final code and CHANGELOG.
   - Get the current numbers from the code: the test count, lib lines, and the Δ against main and against Phase 4.
   - Base it on the new main (bd5a7603) and Phase 4 (#710).
   - Write the PR description draft to `.superpowers/pr-drafts/pr-phase5.md`, in the style of the #710 description (`gh pr view 710 --repo ngardiner/TWCManager`).
   - Include the Fleet-only driveway-shuffle cost and the lib target miss, stated plainly.
   - End it with "🤖 Generated with [Claude Code](https://claude.com/claude-code)".

## Constraints

- No wake to observe, and restores never wake.
- No I/O on the tick or the serial thread.
- Lock order: TeslaBLE._bleLock → settingsLock → registry leaf.
- Python 3.8. Run black on touched .py files.
- Comments say why; no history, no phase, task or ruling IDs.
- Report lib lines before and after; the cuts should offset the additions.
- Suite: `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`. BASE: 2252 passed, 1 xfailed.
- Commits: a few logical ones on vehicle-model/phase5, each ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't push. Never bare `git stash`.
