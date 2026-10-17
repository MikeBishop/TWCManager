## Global Constraints

- Two states per vehicle: HOME (plugged in here) and NOT HOME, which is internally DEPARTING after an unplug. No AWAY and no ARRIVING anywhere.
- Charge-limit policy applies only to HOME (or presumed-present) cars. "DEPARTING is always excluded" and "A DEPARTING car is never presumed present."
- "No wake is ever sent just to find out whether the car should be woken later."
- Evidence strength: "A TWC naming the car, or a BLE charge read, decides on its own." "When they disagree, BLE or the TWC wins."
- "BLE silent: says nothing about whether the car is home."
- The carried TWC rules are unchanged: "a plugged run of at least 60 s before a change counts, there is a 300 s grace after a TWC re-link, and TeslaMate `plugged_in` overrides a Gen2 TWC's steady 00 for an idle plugged car."
- `atHomeRadius` default: **1,000 ft** (was 10,560). An explicit config value still overrides it.
- Departure-restore fallback after BLE has been unreachable for N = **5 minutes**, only "if `commandPolicy` allows a remote channel".
- The fingerprint (offset current) is **not** built here. It's a follow-up.
- Branches 1 and 2, `feat/token-slots` (#692/#693) and IntegrationOrder stay unchanged. `presence/5-fleet-rate-queue` and `deploy/presence-2` are left as they are; new branches are created next to them.
- Every branch passes the full suite: `<PY> -m pytest tests/unit -q`, where `<PY>` = `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python`. Individual commits don't have to pass.
- Run `<PY> -m black` only on the files a commit touches. Don't reformat a test file that wasn't black-clean before; write the new hunks in black style.
- Every new commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Cherry-picked commits keep their messages (see Task 1).
- No log line may contain a token.
- Work in your own worktree. Don't check out branches in, or edit tracked files of, `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`. Nothing is pushed. The live box stays on `commandPolicy: ble_only`, and this plan includes no deploy.
