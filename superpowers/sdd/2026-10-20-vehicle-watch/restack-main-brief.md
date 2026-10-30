# Restack the vehicle-model stack onto the new main (user, 2026-10-21: "Phase 1 has merge conflicts, which blocks everything else.")

## What landed on origin/main since the stack's base (03d79325)
- **#702**, Owner API commands for cars listed with `command_signing: off` (1596fcc3…fc66a4db, adc6fb47, 3068144a). Phase 3.5 (#706) already ports #659 onto the provider model, so the stack's version supersedes it from 3.5 on. Phases 1–3 must still contain main's behaviour where their code still runs it.
- **#711**, Docker BLE exec fix (27f479b7): nsenter as separate args, setsid always, CAP_SYS_PTRACE in compose. Phase 6's commit e3a08225 makes the same fix its own way; keep one consistent version.
- **bd5a7603** (Nathan Gardiner, the maintainer): "Cancel pending stops and rate limit charge commands per vehicle". It changes:
  - `VehicleCommandQueue`: charge commands are keyed per VIN (None = every car) and replace each other; a car gets at most one charge start/stop per `CHARGE_COMMAND_INTERVAL` = 60 s; `cancel_stop(vin)`.
  - `TWCMaster.cancelStopCarsCharging(vin)`, `queue_background_task({"cmd":"charge",…,"vin":vin})`.
  - `TWCSlave` passes `currentVIN`.
  - Tests in `tests/unit/test_vehicle_command_queue.py`; CHANGELOG lines (closes #667).

## The stack
Local branches (squashed, current with origin):

| Phase | Branch | Tip | PR |
|---|---|---|---|
| 1 | vehicle-model/phase1 | 45c21341 | #703, base main |
| 2 | vehicle-model/phase2 | ff4eba64 | #704 |
| 3 | vehicle-model/phase3 | 4998127b | #705 |
| 3.5 | vehicle-model/phase3.5 | b55af397 | #706 |
| 4 | vehicle-model/phase4 | 3aa44301 | #710 |
| 5 | vehicle-model/phase5 | 52a2652c | local only |
| 6 | vehicle-model/phase6 | 7e2eb1d5 | local only |

Also docs/gen3-vehicle-model (#707), one docs commit on phase2 (the origin head; the rebased commit is e3dfc3b4 on restack/707 if the user pushed it).

Phase 1 already keys commands by (cmd, vin) with explicit cancellation, and fixes #667 its own way. Phase 3 replaces fire-and-forget commands with desired state and a reconciler; later phases pace sends through the reconciler (holds, paid budget, back-off).

## Task
1. Rebase each phase in order onto the new base: phase1 onto origin/main, phase2 onto the new phase1, and so on through phase6, then #707 onto the new phase2.
   - Work in new branches `restack2/<phase>` in a fresh worktree. Don't touch the existing branches.
   - Keep each phase's commit grouping and messages. Adjust a message only where the merged behaviour changes what it says.
2. Resolve conflicts on behaviour, not by picking a side.
   - **Phase 1:** the merged result must keep main's guarantees: a pending stop is cancelled per car when charging should continue, and a refused charge command is not retried back to back (at most one charge start/stop per car per 60 s). Express them in Phase 1's own queue design if it already has the concept. Otherwise adopt main's code. Keep main's tests for these guarantees, adapted to the stack's interfaces.
   - **Phase 3 onward:** where a phase deletes or replaces the code that carried a guarantee, make sure the replacement still provides it, and keep or port a test that pins it:
     - a stop isn't sent while charging should continue;
     - no back-to-back retry of a refused start/stop.
     If the reconciler already guarantees one by another rule, name that rule and its test in the report instead of adding code.
   - **#702 code:** follow it into the phases. From Phase 3.5 the stack's port supersedes it; make sure nothing from main's #702 is lost that the 3.5 port lacks. Compare behaviours, including latching and logging levels.
   - **Docker fix:** from #711 on main, keep main's version through Phases 1–5. In Phase 6, fold e3a08225 onto it, so Phase 6 adds only the scan/readiness parts and doesn't redo the exec fix.
   - **CHANGELOG:** keep main's lines. Where the stack's own entries overlap (#667), merge them so nothing is said twice.
3. Every rebased commit must pass the suite.
   - Command, run from the worktree: `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`.
   - Python 3.8 compatible; black on resolved .py files.
   - Phase 4's and Phase 6's parity files (`tests/unit/test_command_path_parity.py`): counts must not move. If one does, stop and report it.
4. Report per phase:
   - the conflicts and how each was resolved;
   - behaviour decisions;
   - tests added or ported;
   - pass counts per commit (at least per phase tip);
   - the lib line delta per phase versus the new base.

## Constraints
- Don't push. The user force-pushes.
- Never bare `git stash`. Don't modify .gitignore.
- Comments say why; no history and no phase, task or ruling IDs.
- Don't drop any of main's behaviour silently. If a guarantee can't be kept in some phase without large changes, stop and report.
