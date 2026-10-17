# Rebase the vehicle-model stack onto origin/main (#699)

## Situation
- Stack (linear, each an ancestor of the next), merge-base eb457dca with origin/main:
  vehicle-model/phase1 (8e07669, 50 commits) → phase2 (6a6c14e, +40) → phase3 (db47522, +90) → phase3.5 (5c133bef, +17).
- origin/main (03d79325) is 6 commits ahead of the merge-base: #699 "Fleet wake-poll"
  (4e525db1, e86ad609, 2e1e9413, d9094bd3, merge 6c96930d, changelog 03d79325). It touches TeslaAPI.py, CHANGELOG.md and
  adds/edits tests/unit/test_teslaapi_wake.py.
- The four branches are pushed and checked out in worktrees under the controller's scratchpad
  (wt-vm, wt-vm2, wt-vm3, wt-vm35). DO NOT rebase those branches in place, and do not force-push anything.

## Do
1. Create a new worktree in the scratchpad (e.g. `scratchpad/wt-rebase`) on new branches
   `rebase/phase1`, `rebase/phase2`, `rebase/phase3`, `rebase/phase3.5` pointing at the current four tips.
   Then from `rebase/phase3.5`: `git rebase --update-refs origin/main` (or rebase each phase in order onto the new tip of
   the one below) so all four new branches move together.
2. Conflict rule (from the merge plan, .superpowers/branch-roadmap-2026-10-16.md "Finding 1"): where #699's wake path
   conflicts with the stack's, take the STACK's wake path (Phase 3 rewrote it: free online check cached 120 s with
   newest-observation-wins telemetry, wake hold WAKE_RETRY_SECONDS=1800). Keep #699 behaviour only where the stack
   didn't replace that code yet (phase1/phase2 still run the legacy path — keep #699 there, so each phase tip works on its
   own). CHANGELOG: keep both sides' entries.
3. #699's tests/unit/test_teslaapi_wake.py: at phases where the legacy path still exists, keep the tests passing. Where a
   phase deletes the legacy wake path, port each test's INTENT to the new structure (most naturally as rows in
   tests/unit/test_command_path_parity.py or tests next to the reconciler wake tests) and delete the legacy test, with a
   map (intent → new test, or "superseded because …").
4. Add the merge plan's Finding 1 parity row on the phase3 (or phase3.5) tip: Fleet-only, car asleep, `wake_up` answers
   offline, car reports online at +59 s; expect exactly one `wake_up`, the limit command within ~2.5 min, and no second
   wake inside 30 min.
5. At EACH of the four new tips run the unit suite and record pass counts and lib line count
   (`git ls-files lib | grep '\.py$' | xargs cat | wc -l`). Every tip must be green (stacked PRs merge one at a time).
   Black-check changed lib files.
6. Do not push. Leave the four `rebase/*` branches and the worktree for the controller.

## Constraints
- No behaviour change to the stack beyond adopting #699 where the legacy path survives.
- No new paid calls; test_command_path_parity.py existing rows must keep their counts at the phase3/phase3.5 tips.
- If conflicts become unmanageable (dozens of commits each needing hand edits in the same hunks), STOP and report with
  the options you see (e.g. rebase commit-by-commit vs. squash-per-phase) rather than guessing.
- Commit messages for any new commits end with: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Rebased commits keep their original messages; amend a commit only to resolve its conflict.

## Commands
Tests: `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G <scratchpad>/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration --timeout=60 -p no:cacheprovider -q`
(scratchpad = /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad)
Pre-rebase baselines: phase3.5 tip 1849 passed, 1 xfailed; lib 27,376.
