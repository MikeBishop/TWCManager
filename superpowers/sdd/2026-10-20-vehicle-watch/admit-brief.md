# Wake and start a car that would charge, if there's room: a small admission check

## Problem (live box, 2026-10-27 00:00)

A car was plugged in at home, asleep, and had finished its last session at its old limit ("Complete"). At midnight the Scheduled Charging policy raised its limit. Nothing woke it.

The cause is in the wake check, `Belief.whyQuiet` (lib/TWCManager/Vehicle/Reconcile/Belief.py). It refuses with "nothing offered" when `master.offered[car] == 0`. The power split (`TWCMaster.distributeEVSEPower`) only offers power to points whose `wantsToCharge` is true, and that means "drawing now". So a car that isn't charging can never get the wake that would start it. The same shape applies to a car-side point at "Complete", a Gen2 echoing 0, and a Gen3 reporting "complete".

An earlier attempt (commits ef7be20f and 920c6505 on branch fix/car-side-wants-power) taught the split to predict which idle cars would charge. It works, but it grew 70 lib lines and dragged scarcity, conflicting hardware reports and schedules into the split. **Do not build on it, and do not copy it.** The user wants the simple version.

## Design (decided with the user)

Decouple the wake and start decision from the per-car offer. Ask instead: "would this car be admitted if it started now?" This is a first step toward issue ngardiner/TWCManager#709 (two-pass distributor: admission, then allocation); read it with `GH_REPO=ngardiner/TWCManager gh issue view 709`. Don't build #709 itself. Build one function its admission pass can later consume.

1. **`wouldCharge(master, vehicle)`** is true when all of these hold:
   - **Plugged in at home:** use the existing helpers (`Presence.pluggedHere`, `pluggedNow`, `presence`).
   - **Limit above battery:** the effective limit is above the battery level. The effective limit is the pending desired limit, else the held limit, else the believed one, the same resolution `whyQuiet` already does; reuse it, don't copy it. An unknown limit or battery counts as "would charge", as `whyQuiet` already assumes.
   - **No stop desired.**
   - **No refusal from `handsOff`:** not scheduledChargingPending under respectVehicleSchedule, not Disconnected/NoPower. Share `handsOff`'s code.
2. **`admissible(master, vehicle)`** is `wouldCharge` plus room. Room means the policy's available amps (`getMaxAmpsToDivideAmongSlaves`, or whatever the split itself starts from), minus the minimums of the points already drawing that are not this car's own point, is at least this car's point minimum. Counting drawing points first gives hysteresis: a charging car keeps its place, and a new car is admitted only into real headroom. Keep it a few lines. Compute "drawing" from what the split already knows (each point's or endpoint's current draw). Don't add new per-class properties unless one is genuinely missing.
3. **Wake check:** in `whyQuiet`, replace the per-car `offered == 0` refusal with `not admissible`, worded e.g. "no room to start". A limit raise wakes only when the car is admissible and the raise is above both its current limit and its battery level. A car that won't start keeps the existing rule: changes wait until it is awake anyway.
4. **Start:** find where a start desire (`CHARGING` True) is created today. The Gen2 `chargeGate` makes one for TWCs; a car-side point may have nothing. If an admissible car that isn't drawing has no path that ever wants it started, add the smallest one: one place that sets the start desire for admissible, not-drawing cars, with no start desire or stop desire pending. A stop desire blocks the start, which prevents a start→stop→start loop when the split drops a car. Starts must not repeat every pass once they are delivered or refused. Check how the reconciler settles a delivered start and a "Complete" refusal.
5. **The power split is untouched.** After a car starts and draws, it counts like any other. An overshoot of up to one cycle is acceptable, because configured limits are already derated to 80% continuous.

## Tests (write each first and watch it fail on base 1a0b7d67, where meaningful)

1. **Last night's replay, car-side:**
   - setup: car plugged in at home, asleep, "Complete", battery 70, limit 70, BLE able to set amps;
   - action: the policy raises the limit to 90 with 32 A available;
   - expect: wake, setChargeLimit 90, start (or the car starting on its own after the limit, whichever the code does), amps set.
2. **Same car, no raise (limit 70):** no wake, no start.
3. **Same car, scheduledChargingPending under respectVehicleSchedule:** no wake, no start, over repeated passes.
4. **Same car, stop desired:** no wake, no start.
5. **No room:** 0 A available (Track Green Energy at night). No wake.
6. **Room only after the drawing car's minimum:**
   - With 9 A, a car charging at a 6 A minimum and this car with a 5 A minimum: not admitted, no wake.
   - With 16 A: admitted.
7. **The Gen2 echo-0 case:** a car on a Gen2 TWC with a command path, the TWC echoing 0, and a pending raise: woken and started.
8. **Waking on repeat:** a car that is woken and then refuses ("Complete" with no raise) is not woken again every pass.

## Constraints

- **Worktree:** /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-admit. Create it from origin/vehicle-model/phase6 (1a0b7d67) on a new branch, `fix/admit-would-charge`: `git -C /home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96 worktree add -b fix/admit-would-charge <path> 1a0b7d67`.
- **Venv:** /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv.
- **Suite:** `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G <venv>/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`. Check pytest's exit code. The baseline is 2,459 passed and 1 xfailed.
- **Parity:** the paid counts in `tests/unit/test_command_path_parity.py` must not move. Explain any free-count move. If a paid count moves, stop and report.
- **Size:** the earlier attempt was +70 lib lines. This should be a small fraction of that, and every line should earn its place. Prefer replacing the `offered` check over adding beside it. If `master.offered` loses its last consumer, remove it.
- **Code style:**
  - Python 3.8.
  - Run black on touched code only.
  - Comments say why the code is what it is, with no history and no phase, PR or issue IDs. One comment may note that this is the admission check a later two-pass split can share, without citing the issue number.
- **Commits:** one commit, or two if a start path has to be added. Use a CHANGELOG line under v1.4.1 Bugfixes, written for users, e.g. "A plugged-in car is woken and started when a policy raises its limit, if there is power to give it." End each message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Don't** push, use a bare `git stash`, or print VINs, coordinates or the car's name.
- **No subagents.** The `advisor` tool is available if stuck, or for a check before finishing.

## Report

Write `admit-report.md` next to this brief, covering:
- the design as built: where each function lives and why;
- the start path you found, or added;
- each test, failing before and passing after;
- suite counts, parity, and the lib line delta against 1a0b7d67.

Return only: status, commits, suite counts, the lib delta, and any concerns.
