## Global Constraints

- Branch `fix/vehicle-presence`, stacked on `origin/ble-command-worker` (PR #668) at 3574692. Never commit anything under `.superpowers/`; never edit a tracked `.gitignore`.
- Tests: `$VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider` with `VENV=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv`. Baseline: `500 passed, 1 warning`. The warning is pre-existing.
- Formatting: `$VENV/bin/black --exclude="setup.py|tests/*" --check .` must pass before every commit (CI runs it). Run `$VENV/bin/black lib/` to fix.
- Run every command from `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`.
- Observers (`nominate`, `observeContact`, `observeLocation`) do no I/O and take only the presence lock. They are called from under `TeslaBLE._bleLock` and from the MQTT thread, so they must never call back into a vehicle module.
- The presence thread never holds the presence lock while running a source or a handler.
- Presence never runs `wake`, `state` (without a preceding awake probe) or `ping` over BLE, and never calls `wake_up` over the API.
- Concurrency tests use `threading.Event` / gates for positive assertions, never `time.sleep`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Expected test counts are cumulative: 500 → 511 → 516 → 539 → 552 → 582 → 605 → 625 → 640.

---

