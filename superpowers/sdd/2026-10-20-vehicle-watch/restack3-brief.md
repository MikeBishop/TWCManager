# Restack Phases 2–6 onto the new main, folding in the late fixes

The user, 2026-10-26: "start the rebase, including folding in the fixes. Update the open PRs."

## Where things stand

**Phase 1 (#703)** merged into main as-is: merge commit 9ef97b2f, with Phase 1 tip 8070d5c3 as its second parent. 1.4.0 was tagged just before, at f3d1d7cf. The maintainer's d814be60 then gave main's #689 tests a well-formed VIN, because Phase 1 rejects malformed VINs.

**New base:** `origin/main` = d814be60 (run `git fetch origin` first; if main has moved, use its tip and report the new commits).

**Main commits since 8070d5c3** (non-merge; `git log --no-merges 8070d5c3..origin/main`):
- **Charging and voltage:**
  - #714, 429b637c: a null Fleet API voltage or current counts as unknown in TeslaAPIEVSE.
  - #716, 6e798594: distributeEVSEPower budgets with the measured TWC voltage.
  - 3ba22d0f: Gen2TWC falls back to defaultVoltage on every configured phase.
  - da599a07: docs.
- **Tesla API:**
  - #689, e14f6d94: handle a 401 on vehicle commands.
  - #690, e4000e11: serialize token refreshes per token slot.
- **Other code:**
  - e3710ec9: VehiclePriority.enabled() answers without priority dispatch.
  - #666, 55c4878a: a POST without Content-Length is an empty body.
  - #721, 95c3a389: HTTPControl falls back to IPv4 when it can't listen on IPv6.
  - daac195f: a skipped MQTT publish is logged once per broker outage.
  - a3ca1505: Fronius timeout.
- **Other changes:** the Docker, workflow and doc commits #717 and #719; PHP removal 3ffec768; the version bump; the changelog commits.

## The stack (local branches, all ahead of origin)

| Phase | Branch | Local tip | On origin | PR |
|---|---|---|---|---|
| 2 | vehicle-model/phase2 | 4c40dd70 | 26fc3f3d | #704 (base vehicle-model/phase1, to be retargeted to main) |
| 3 | vehicle-model/phase3 | f933cbe5 | fe9eca64 | #705 |
| 3.5 | vehicle-model/phase3.5 | f6eb5261 | 87a9eff1 | #706 |
| 4 | vehicle-model/phase4 | 3c4b865b | f1e98620 | #710 |
| 5 | vehicle-model/phase5 | 7e7d3517 | unpushed | none yet |
| 6 | vehicle-model/phase6 | f538b780 | unpushed | none yet |
| #707 | docs/gen3-vehicle-model | 71227c1a | | #707 (on phase2) |

The worktrees under `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/` hold these branches: wt-py38 (phase2), wt-vm3, wt-vm35, wt-vm4, wt-vm5, wt-vm6 and wt-gen3docs. Don't move those branches. Work on new branches `restack3/<phase>` in a fresh worktree.

## Task

### 1. Fold the late fixes into the commits they fix

Each phase keeps logical, reviewable commits. A late fix folds into the commit whose behaviour it fixes, and that commit's message is adjusted only if the fold changes what it says. The candidates:
- **Phase 2:**
  - 26fc3f3d "Cap a car by its own charging maximum, not the charger's pilot" folds into the commit that introduced `Provider.vehicleMaxAmps`, or the charging-point commit 415493d7 for its `_atPointVoltage` part. Split the fix if it spans both.
  - 4c40dd70 "Keep a disabled TeslaBLE module out of the provider order" folds into edeaa2d7 "Add the TeslaBLE provider".
- **Phase 3.5:** f6eb5261 (the caplog test) folds into 85b5d862 "Dissolve CarApiVehicle…", where that test was added.
- **Phase 4:** check whether any commit is a fix to an earlier Phase 4 commit rather than its own feature. 3c4b865b "Keep running when the Gen2 RS-485 adapter is absent" is a feature; keep it.
- **Phase 5:** many fix commits came after the phase's feature commits, from review rounds and soak fixes, from a960d5d2 on. Examples:
  - a960d5d2, 48c112c0, 9f167500, 4977ef3a, 5b2b77d7, be8d90b2, 66129c6e, 64a822f2, a9d9950c, 72e758ff;
  - a7f11121 (the follow-up plug check), 48474e05 (wake polling), ee237bd4 (current at the TWC counts as charging), b48dd13b (the hold recheck) and 7e7d3517 (learning home).

  Fold each into the feature commit it fixes when one clearly owns that behaviour. A fix that is really a feature of its own (the follow-up plug check, wake polling, TWC current as charging, the cloud hold) stays a separate commit. Use judgment; aim for a history a reviewer can read commit by commit.
- **Phase 6:** fold f538b780 (the replay test) into the commit whose behaviour it pins, if one does; otherwise keep it.

**The tree must not change:** after folding and before the rebase, each phase's tip tree must equal its current tip tree. Check with `git diff <old tip> <new tip>`, which must be empty.

### 2. Rebase onto the new main

Rebase phase2 onto `origin/main` (its old base is 8070d5c3). Then rebase each later phase onto the new tip of the phase before it, and #707 onto the new phase2.

Resolve every conflict by behaviour, not by picking a side. Keep main's guarantee wherever the stack's replacement code runs the same path, with a test that pins it:
- **#714, null voltage or current:** the stack deletes TeslaAPIEVSE (Phase 2's vehicle endpoints). Make sure a null `charger_voltage` or `charger_actual_current` from the Fleet API is treated as unknown where the stack reads it, not as 0 or a crash.
- **#716 and 3ba22d0f, measured voltage:** the stack prices in ChargingPoint and has `_atPointVoltage`. Keep the stack's design, but make sure the budget uses the measured TWC voltage, with `defaultVoltage` on every configured phase as the fallback, and that the two never disagree.
- **e3710ec9, VehiclePriority.enabled():** Phase 2 makes VehiclePriority a facade. Keep the guarantee that enabled() answers without dispatch.
- **#689, 401 on commands:** the stack's command path (Phase 3's single request helper and status classifier, Phase 3.5's TeslaAPI) must classify a 401 on a command the way main does: refresh once, then a clear refusal, never a blind retry loop. Port main's test, using a well-formed VIN as in d814be60.
- **#690, refresh serialization per slot:** Phase 4 already has "one refresh per slot at a time". Merge into one mechanism; don't keep two.
- **#666, #721, MQTT log, Fronius:** these should apply without conflict. Keep them.
- **CHANGELOG:** every stack entry goes under `## v1.4.1 - Upcoming` (Phase 1's entries are already there). Nothing stays under v1.4.0, and nothing is said twice.

### 3. Verify

- **Suite at every phase tip:** run it from the worktree with
  `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`.
  If folding is heavy, also run every new commit in Phase 5.
- **Parity:** the paid counts in `tests/unit/test_command_path_parity.py` must not move. If one moves because of main's behaviour (for example, a 401 now refreshes), stop and report it before changing the row.
- Python 3.8 compatible; run black on resolved .py files.

## Report

Write `restack3-report.md` in `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/sdd/2026-10-20-vehicle-watch/`. Per phase, include:
- the folds made (fix → target);
- the tree-identity check;
- each conflict and how it was resolved;
- tests ported;
- suite counts;
- lib lines against the new base;
- the new tips.

## Constraints

- Don't push. Never use bare `git stash`. Don't modify .gitignore.
- Comments say why the code is what it is; no history, and no phase, task or ruling IDs.
- Don't drop any of main's behaviour silently. If a guarantee can't be kept without large changes, stop and report.
- Never print tokens, home coordinates or the owner's car name.
