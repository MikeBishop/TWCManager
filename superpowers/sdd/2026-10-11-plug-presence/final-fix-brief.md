# Final-review fix round (plug presence)

Source: `final-review.md` in this directory (read I1, I2, M1, M2, M7 in full there; fixes and tests are specified per finding).

Correction to the review's premise: the live box now has BOTH an Owner slot and a Fleet slot (`carApiBearerToken` set) with `commandPolicy: ble_only`. So "Owner-only token refuses every Fleet command" is false there. As part of I2, determine whether the Fleet EVSE rate path (`TeslaAPIController` -> queued `fleetSetChargeRate` -> `TeslaAPI.setChargeRate`) honours `commandPolicy: ble_only`. If it bypasses it, say so in the report (do not change commandPolicy semantics in this round unless the fix is a one-line gate that clearly belongs; if you add one, test it).

## Branch work, in order

Worktree: scratchpad/wt-plug (currently on deploy/presence-3 at cce331f, clean). Never push. Never use git stash (shared across worktrees); use WIP commits or a `git archive` copy for mutation checks. Branches listed below are local-only and unpushed, so rebasing presence/4-fleet-rate-queue is allowed; do not touch any other branch.

1. `presence/3-plug-presence` (3e20776): commit fixes for I1, M1, M2, M7, each its own commit with tests. Also carry back from deploy/presence-3 commit cce331f:
   - the `test_teslable_presence` and `test_teslaapi_presence` changes (use `carApiBearerToken = "token"` style instead of `storeToken`, since token slots don't exist on this branch; verify the new no-fix wake test can send commands here);
   - make `test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing` discriminate the same way (policy moves to 60% while the car holds 50%), and prove with a mutation (TeslaAPI policy-wide away-skip -> `if False:`) that it fails.
   Full suite green.
2. Rebase `presence/4-fleet-rate-queue` onto the new presence/3 tip (`git rebase --onto presence/3-plug-presence 3e20776 presence/4-fleet-rate-queue`). Then commit the I2 fix there with tests. Full suite green.
3. On `deploy/presence-3`: `git merge --no-ff presence/4-fleet-rate-queue` (subject `Merge presence fixes into deploy/presence-3`). Resolve conflicts with cce331f's test edits by keeping the slot-API form. Full suite green. Black only touched lib files. Token-in-log grep over `git diff presence/4-fleet-rate-queue -- lib` still clean.

## Report

Append to `final-fix-report.md` in this directory: per finding, commit SHA, what changed, the test and its fail-before evidence; the commandPolicy finding; new branch tips for presence/3, presence/4, deploy/presence-3; suite counts per branch.
