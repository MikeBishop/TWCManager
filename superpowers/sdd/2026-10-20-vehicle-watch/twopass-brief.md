# Two-pass power split: admission, then water-level allocation (closes #709)

## Context

TWCManager is an EV charging manager in Python. The vehicle-model stack is now on `origin/main`.

A bug on the live box led to a first fix. A plugged-in car that was asleep and "Complete" at its old limit was never woken when a policy raised its limit, because the wake check refused any car the split had offered 0 A. That fix is commit `d053ddc7` "Wake and start a car that would charge, if there is room", on branch `fix/admit-would-charge` in worktree `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-admit`, on `origin/main` `d8f036d1`. It added:
- `wouldCharge`, `_room` and `admissible` in `lib/TWCManager/Vehicle/Reconcile/Belief.py`;
- a start loop and a Gen2 "withdraw" skip in `TWCMaster.controlPass`;
- the removal of `master.offered`.

**Read first:**
- `admit-brief.md`, `admit-report.md` and `admit-review.md` in `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/sdd/2026-10-20-vehicle-watch/`. The review's verdict is fix first: 4 important and 8 minor findings.
- Issue ngardiner/TWCManager#709: `GH_REPO=ngardiner/TWCManager gh issue view 709`.

The user has decided to build #709 now, on top of that commit, so that the admission the fix introduced becomes the split's first pass.

## Design (decided with the user)

### Pass 1: admission (once per control tick, in or beside `distributeEVSEPower`)

**Candidates:**
- (a) Points that are drawing, first. This is the hysteresis: a charging car keeps its seat.
- (b) Points whose car `wouldCharge`.

`wouldCharge` is as in `d053ddc7`:
- plugged in at home;
- its effective limit (pending, else held, else believed) is above its battery level, where an unknown battery or limit counts as "would charge";
- `_refusesStart` raises no refusal: not `scheduledChargingPending` under `respectVehicleSchedule`, and not Disconnected or NoPower.

**Drop the stop-desire condition from `wouldCharge`.** The user's ruling: "Stopped" is just a state, and admission alone decides.

**Admitting:** go through candidates in order, using a stable tie-break (e.g. existing order or point ID). Admit a candidate while the sum of admitted minimums fits the total available power and each controller's budget (`_budgets()`). A candidate that doesn't fit is not admitted.

**Mapping a would-charge car to its point:** use the car's own point. That is its car-side `VehicleEndpoint`, a TWC naming it, or a TWC still holding it (`heldKey`). A car the stations can't place (e.g. an unnamed TWC with no match) gets no admission, so delete `_room`'s `idle=[1]` guess.

Read-only points never get budget, as today.

### Pass 2: water-level allocation, among admitted points only

Every admitted point gets `clamp(L, min, max)`, where L is chosen so that the sum equals the available power, capped by each point's maximum.
- If the sum of maximums is under the total, everyone gets their maximum.
- Compute L by sorting the breakpoints and doing one pass. Keep it short (about a dozen lines).
- Equalise in amps at each point's own voltage, with the budget in watts, the way the code prices points today.
- Respect per-controller budgets (Gen3 `maxPower`). If one binds, clamp that controller's points as a group. Keep it simple and test it.

Points that weren't admitted get 0, as non-wanting points do now. An idle Gen2 still gets its hardware minimum through the existing 0 offer.

This replaces the current ascending fair-share loop and its bookkeeping. Delete the loop.

### Desired charging follows admission

**On every pass:**
- An admitted car that isn't charging is wanted charging (a start desire), with no start already pending.
- A car that isn't admitted and is drawing is wanted stopped. On car-side, that's a stop desire. On Gen2, that's the existing chargeGate on a 0 offer.

**Stale desires:** none outlive a change of admission. When admission flips, the opposite desire replaces it, so a dusk stop can't block a midnight start.

**Gen2 TWC "withdraw start" skip:** keep the skip for an admitted car, but move it into `withdrawStartCharging`, as the review suggested.

**Don't fight a Gen2 chargeGate:** make sure the gate and admission don't loop start, stop, start. Test 20 passes with a stable input.

### Wake check

- `whyQuiet` uses admission: "no room to start" when the car's point isn't admitted.
- The wake check runs only where a wake is possible. It must not run for stops, restores or limit lowers.
- If computing admission raises, the answer is "no room", and stops, restores and limits still go out. This fixes review finding 1.
- Admission is computed once per tick and cached for the reconciler, so the reconciler thread doesn't rebuild points per car. Make it thread-safe: an immutable snapshot swapped by reference.
- `withdrawOffers`, the path for a failing control pass, clears the admitted set, so nothing is woken while the pass fails.

### Unknown state after a restart (the user's default)

Straight after a restart the registry has no battery, limit or charging state. A sleeping, plugged-in car with no feed reporting is treated as "would charge", and may be woken at most **once per restart** to learn its state. Make it cheap to switch off.

Test: on a Fleet-only install, a sleeping plugged-in car whose charging state is unknown gets exactly one paid wake per restart, never more, across many passes.

### Other review findings

Fix all the remaining ones in `admit-review.md` that this design doesn't make moot. In particular:
- **Parity fixture:** stop pinning `gen2()` at 0 A, and stop `gen2()` overwriting power set before it. Run the parity rows with power on. Assert every paid count.
- **Test realism:** use real point keys and a TWC still holding the car in tests, not fake points.

**No CHANGELOG line for the bug.** 1.4.0 never had it. #709's own improvement (an endpoint whose minimum can't be met no longer wastes the share set aside for it) is a user-visible change to how power is shared. It gets one v1.4.1 line, unless the CHANGELOG has no suitable section. Write it for users.

## Tests (each written first, and failing on d053ddc7 where meaningful)

1. **#709's example:** 25 A, EVSE A (6–32 A) and EVSE B (min 20 A). Exactly one is admitted. With neither drawing, the tie-break decides. If A is drawing, A gets 25. If B is drawing, B gets 25 (clamped by its max).
2. **Water level:**
   - 30 A with Gen3 (16–48) and a car (5–32): 16 / 14.
   - 40 A with Gen3 (16–48) and two cars (5–32): 16 / 12 / 12.
   - 48 A with A capped at 16 and B (6–48): 16 / 32.
   - Total above the sum of maximums: everyone at their maximum.
3. **No eviction:**
   - A Gen2 car drawing (min 6) and a car-side arrival (min 5) at 11 A: both admitted, 6 / 5.
   - At 10 A: the arrival is not admitted, and the Gen2 car keeps 10.
4. **Hysteresis:** two cars that both fit alternately; the drawing car keeps its seat across 20 passes with fluctuating power near the edge.
5. **Last night's replay:** a car-side car, asleep, "Complete" at 70, plugged in; the policy raises it to 90 with 32 A available. Expect wake, limit, start, amps, with exactly one real wake request on Fleet. Use a scripted Fleet car like the reviewer's.
6. **Dusk stop, then midnight start:** a Gen2 car stopped by a 0 offer at dusk is woken and started when a raise comes with power available.
7. **A car on its own schedule:** never admitted.
8. **Stops still go out when computing admission raises.**
9. **The Fleet-only restart:** one wake per restart, as above.
10. **The Gen2 chargeGate:** no start/stop loop.

## Constraints

- **Worktree:** wt-admit, on branch `fix/admit-would-charge`. Commit on top of `d053ddc7` as a second commit. Squash only if one commit reads better. Don't push.
- **Venv:** `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv`.
- **Suite:** `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G <venv>/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`. Check pytest's exit code. The `d053ddc7` baseline is 2,472 passed and 1 xfailed.
- **Parity:** paid counts must not rise, except for the Fleet-only restart wake ruled above, which must be asserted. Explain every count that moves.
- **Size:** the project treats lib growth as a red flag. The fair-share loop and `_room` go away, so the net lib delta against `origin/main` (`d8f036d1`) should be near zero or negative. Report it.
- **Code style:**
  - Python 3.8.
  - Black on touched code only.
  - Comments say why it is, with no history and no phase or PR IDs. Citing "#709" in the commit message is fine; don't cite it in code.
- **Commit message:** end it with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use "Closes #709" in the body.
- **Don't** spawn subagents. The `advisor` tool is available if stuck, or for a check before finishing.
- **Never** print VINs, coordinates or the car's name. Never use a bare `git stash`.

## Report

Write `twopass-report.md` next to this brief, covering:
- the design as built: where admission and allocation live, the snapshot, and the desire rules;
- each test, failing before and passing after;
- each review finding: fixed or moot, and why;
- suite counts, parity moves, and the lib delta against `d8f036d1`.

Return only: status, commits, suite counts, the lib delta, and any concerns.
