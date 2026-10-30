# Squash one phase of the vehicle-model PR stack (user, 2026-10-20: "For ease of review, it might be worth giving the other PRs the same squashy treatment.")

Stack (each PR's base is the previous branch): main 03d79325 ← phase1 ec8790ca (#703, 50 commits) ← phase2 75746bea
(#704, 41) ← phase3 ed521403 (#705, 97) ← phase3.5 3be7a5b2 (#706, 22) ← phase4 044e5262 (#710, 28). Phase 5 was
already squashed the same way (example of the result: `git log --format='%h %s%n%b' 044e5262..34784a64`).

You squash ONE phase: BASE..TIP given in your dispatch. Each phase is done independently on its ORIGINAL base; the
controller later rewires parents (trees at the boundaries are identical, so no commit's tree changes).

## Steps
1. Read `git log --reverse --format='%h %s' BASE..TIP` and the diffs as needed. Group the commits into logical changes
   a reviewer can read one at a time: roughly 8–20 groups (fewer for small phases), each one coherent feature or
   cleanup, fix-ups and review-fix commits folded into the change they fix, docs folded into the feature they document
   unless a docs-only commit reads better. Write the numbered list and groups to the plan file named in your dispatch
   before building.
2. Build on a new branch `<branch>-squashed` in a new worktree under
   /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/
   starting at BASE (non-interactive rebase with a prepared todo via GIT_SEQUENCE_EDITOR, or cherry-picks + amend).
   Prefer keeping original order; reorder only where grouping requires and it applies cleanly; where a move conflicts
   badly, fold into the nearest group and note it.
3. Hard requirement: `git diff TIP <new tip>` prints nothing.
4. Every new commit passes the suite: `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests/unit tests/EMS -q --timeout=60 -p no:cacheprovider`
   run from the worktree at each commit (check out detached in your worktree). Record pass counts. If the ORIGINAL
   commit at that point also failed the same tests, say so and accept; otherwise merge/reorder groups until each passes.
   Note: tests directories may not exist at the earliest commits — fine, report.
5. Messages: plain subject (imperative, what the change does), short body on what and why — no history ("previously",
   "now", "fix review finding"), no phase/PR/issue/ruling/task IDs — ending with a blank line and
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Keep the original author (Mike Bishop) as author.
6. Do not touch the original branch; do not push; never bare `git stash`; don't modify .gitignore.

## Report (to the report file in your dispatch)
Group table (new SHA, subject, original commits folded), deviations, per-commit pass counts, tree-identity proof.
