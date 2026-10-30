# SDD ledger — plan: .superpowers/plans/2026-10-16-vehicle-model-phase3.5-carapivehicle.md

Worktree: scratchpad/wt-vm35, branch vehicle-model/phase3.5, BASE db47522, lib 27,270 (target 26,750).
Planner projection: ~27,025 (26,965–27,085), no behaviour change. 4 tasks: held-limit one-pass migrate (−65), registry answers sync state (−20), dissolve CarApiVehicle (−155), sweep + live check (−5).

Ruling: TeslaAPI per-car bookkeeping (online cache, status deferral, wake hold, 429 backoff, atHome) lives as the attachment("TeslaAPI") record on the registry Vehicle — keeps 7 callers + 1 template that read attachment as "listed"; registry fields would show on Vehicles tab and reset the forget window; a side dict recreates the second map — if wrong, Phase 5 presence port moves atHome anyway.
Pending user: accept ~275 over target or name a lever (only in-phase lever: drop wait-for-every-slot, −35, reverses user semantics).
Box: phase3 db47522 deployed 2026-10-16 09:45 for daytime soak + midnight run; watchdog re-armed. Migration OK (heldLimits 5YJ…561 outside 100 held 50; numeric ID merged).

## Pre-flight (preflight.md): go-with-fixes, 20 findings
Ruling F1,F2,F4,F5,F8,F12,F13,F14,F15,F17,F18,F20: apply as written in plan text — test-list/path corrections — cost if wrong: one fix round.
Ruling F3: failed online check keeps returning False (not None); three-state is internal only — "no behaviour change" is binding — cost: a few lines.
Ruling F6: no new paid call allowed even in edge; the fold must keep the second is_awake gate before vehicle_data (or equivalent) — paid-call constraint binding — cost: a few lines.
Ruling F7: canForget+forget become one atomic registry operation (check under registry lock) rather than keeping the rejoin path — removes the race at source — cost: small registry change; if wrong, car unlisted until next restart only.
Ruling F9: waiting() requires a dict — avoids perpetual free list GETs — trivial.
Ruling F10: accept (malformed loaded entry + two IDs for one VIN; never seen in practice) — note in plan as INTENTIONALLY CHANGED edge.
Ruling F11/F16/F19: accept; run box jq "id:" check before Task 1 (done separately by controller).
Ruling extra savings: take all five (anonCars, allEVSEs, _snapshot inline, say() inline, HA attached) — behaviour-neutral — cost: ~15 lines of review.
Plan revised per pre-flight; projection ~27,065. Task 1 BASE db47522.
Task 1: dispatched implementer (opus) a8d8784118e032392, BASE db47522
Task 1: implementer DONE c518644, -45 lib, 1769 passed
Task 1: review spec ✅ quality approved (20k-case differential fuzz: only F10 class differs). Fix round 1 dispatched for minors 1-3 (vinsNow, is not None, F9 test). Minor 4 (black noise) and 5 (id: key stays, harmless) parked.
Task 1 fix round 1: b44ea1e (1770 passed; lib 27,230, -40). Controller checked 2-hunk lib diff: correct, re-review not needed. Task 1: complete. Task 2 BASE b44ea1e.
Task 2: dispatched implementer (opus) af4a232cc0ce5542b, BASE b44ea1e
Task 2: implementer DONE_WITH_CONCERNS f82744e, -18 lib, 1773 passed. Ruling: keep test_ble_read_observes_actual_current (brief's covering claim was wrong; keeping closes a mapping gap) — cost if wrong: one redundant test.
Task 2: review spec ✅ quality approved. Minor (Targets.py:66 lat==10000 'not yet located' clause untested) carried into Task 3 dispatch. Nit parked. Task 2: complete. Task 3 BASE f82744e.
Task 3: dispatched implementer (opus) ab11d19514fd41739, BASE f82744e
Task 3: implementer DONE 424be4b eebe6df 7d946ab, -74 lib (27,138; brief ~-130), 1780 passed. Concern: located()/_restoreDeparted call getModuleByName('TeslaAPI') with no None guard — reviewer to check HA-only/TeslaAPI-disabled installs.
Task 3: review spec ✅ quality approved. n1: no None guard needed (TeslaAPI always loaded; disabled crashes at BASE in loadSettings). Fix round 1 dispatched: m1 expire skips attached, m2 stop no-answer test, savings ~-13. m3 parked (test plumbing, no current victim). n2/n3 parked (pre-existing).
Task 3 fix round 1: c02e333, 1782 passed, lib 27,123 (-89 task, -147 phase).
Task 3 re-review: all addressed. Unused 'Any' import TeslaAPI.py:13 carried into Task 4 sweep. Task 3: complete. Task 4 BASE c02e333.
Task 4: dispatched implementer (sonnet) ac9ebcd19a05aab8d, BASE c02e333. Ruling: implementer writes live-check procedure, controller executes on box — box is shared/pre-approved only for controller.
Task 4: implementer DONE e7973a3, lib 0 (27,123), 1782 passed.
Task 4: controller read 127-line diff (CHANGELOG, comment, import, guard test): correct. Task 4: complete. Final review BASE db47522 HEAD e7973a3.

## #659 Owner API commands (from peer session "Owner API token command permissions")
Reference: local branch vehicle-model/phase3-owner-commands (on db47522): 2ef5ba3 f0a7b4b 3a3c4ff 72439ec 3489e93; review at /tmp/claude-1000/-home-mbishop-github-homelab-compose/f4cc993f-e661-48c7-89fd-9a38b1bb02e0/scratchpad/wt-p3/review-659-p3.md. Conflicts with 7d946ab (CarApiVehicle gone) — needs port, not merge.
Ruling: this session owns the port as Task 5 (after the final review + fix) — peer handed it over at user's request — cost if wrong: duplicate work.
3489e93 (Owner refusals NOT_SENT; H2 hold skips EXCLUDING): controller view keep — affects only NOT_SENT∩EXCLUDING ("no command token", HA "not listed", Owner details); BLE "key" untouched; exclusion per desire. User decision pending; port it unless user says drop.
User 2026-10-16: keep 3489e93 — port it in Task 5.

## Final review (final-review.md): ready, 3 Minors. Paid-call differential: 211 common tests, 0 request diffs. Parity 31/31. Integration 209 pass (60s-continuous test needs --timeout=120; passes).
Ruling: expire skipping attached cars (m1) is INTENTIONALLY CHANGED but unobservable — both attach sites claim keepsAlive at once and nothing detaches; it closes the listing/expire race the deleted rejoin path used to heal — cost if wrong: a detached-but-attached car outlives 30 days.
Ruling: final fix dispatch takes all behaviour-neutral savings (dead .VIN branch + guard regex, Vehicle import, shadowed enabled, listed-car lookup helper, atHome helper, error-block loop with exact messages/order, HeldLimits frozenset, dead __email/__password/__resp); NOT the case-insensitive VIN unification (behaviour edge).
Final fix: 6c4ba54, 1783 passed, lib 27,098 (-25; -172 phase). Items 4,5 not taken (grew lib).
Final fix re-review: all addressed (guard regex nit parked). Phase 3.5 Tasks 1-4 + final review: complete at 6c4ba54, lib 27,098. Task 5 (#659 port) BASE 6c4ba54; brief written by controller (task-5-brief.md).
Task 5: dispatched implementer (opus) aabbfbe6eca17fc9d, BASE 6c4ba54
Task 5: implementer DONE 5190831 3ffd8c8 40f77ca, lib +260 (27,358), 1829 passed.
Task 5: review spec ✅ quality approved; per-desire paid records owner-only == Fleet-only (scratch). Fix round 1: S1 drop _signingState, S2 merge reason branches, L2 test nit, adopt paid-records test. L1 (H2 skip also covers 'not listed' refusals) → mention in PR/ledger, harmless. L3 parked (dup log under race, same as reference). S3 not taken (pinned by brief req 3).
Task 5 fix round 1: b2f0cdb 64c3932, 1830 passed, lib 27,347 (+249 feature). Controller checked lib diff: correct. ble_only suppresses OwnerAPI commands (cloud locality rule). Task 5: complete. Deploying 64c3932 to box for soak + midnight (roll-forward from db47522; watchdog armed).
User 2026-10-16: overage accepted for now; Phases 4 and 5 expected to reduce size.
Roadmap (.superpowers/branch-roadmap-2026-10-16.md) immediate steps: Task 5 review done (_signingState dropped). Branch cleanup (ff main, remove 3 worktrees, delete 19 local branches) BLOCKED by auto-mode classifier — SHAs saved in .superpowers/branch-shas-20261016.txt; awaiting user. Deviation: tonight's gate runs phase3.5 64c3932 (superset of phase3) not phase3. Overnight log collection scheduled 00:25.
User approved cleanup: done (main ff to 03d7932, 3 worktrees removed, 19 local branches deleted; SHAs in .superpowers/branch-shas-20261016.txt). #659 main PR opened: ngardiner/TWCManager#702 (fix/659-owner-commands-unsigned adc6fb4, 989 passed); #701 body points to #702; tracker updated.
User 2026-10-16: on 3.5 only, commands follow provider order (Owner rank 4 before Fleet 5); main/#701/#702 keep Fleet-first. Task 6 brief by controller; dispatched implementer (opus) a4a8df274021d407f, BASE 64c3932. Box stays on 64c3932 for tonight (ble_only unaffected).
Task 6: implementer DONE 2facd2f, lib -6 (27,341), 1846 passed. Concern 1 (refusal log suggests Fleet token when held) parked.
Task 6: review spec ✅ quality approved (I-1..I-5 info, L-1/L-2 low). Controller fixed I-5 docs (617fc48→amended). Rest parked; I-1 (Owner 429 backs off car incl. Fleet) + unsigned Owner commands with both tokens → PR notes. Task 6: complete.

## Live gate 2026-10-17 00:00 — PASS (box on 64c3932, restarted 13:15 with car plugged in; SOC 58, schedule limit 70, ble_only)
00:00:13 Scheduled policy. 00:00:21/29 BLE set-limit timed out twice (car asleep). 00:05:36 next attempt (limit RETRY 300 s): first try timed out, quick retry succeeded. 00:05:52 charge session started, 48.6 A; limit 70, atHome True. charging-start BLE timed out (car already charging). Zero paid calls (only free token-refresh log lines). Watchdog 00:30: amps 48.64, no rollback. No tracebacks.
Note for tuning: the first start waited one 300 s limit RETRY after two BLE timeouts (~6 min late); cfd0086 took ~17 min the night before.
2026-10-17 00:42: box config moduleConfiguration.TeslaBLE.commandTimeout 5→15 (user OK; backup ~/twcmanager-config.json.bak-20261017-bletimeout), restarted mid-charge. Task 7 (INFO wake logging) dispatched (sonnet) a77bf9f835b4d5ea1, BASE 1a4c8ec.
Task 7: 5c133bef (+35 lib, 27,376; 1849 passed). Controller read lib diff: correct, no behaviour change. Task 7: complete. Pushed phase3.5; deployed 5c133bef to box 2026-10-17 ~00:50.
User 2026-10-17: green energy rare; INFO wake lines fine. Rebase onto origin/main dispatched (opus) ab3829473bcfb0e14 → rebase/* branches in new worktree; old branches untouched; no force-push until user confirms.

## Rebase (rebase-report.md): rebase/phase1 ec8790ca, phase2 31e5d185, phase3 1455ddba, phase3.5 6fcbd4a2 on origin/main 03d79325. All tips green.
Ruling C1: Finding-1 row exposes a real regression vs main (Fleet-only asleep car, wake_up answers offline, online at +59 s → limit never sent; same at original db47522). Must fix before any PR — "no paid/behaviour regression vs main" binding — fix as a new commit on rebase/phase3, carry to 3.5 — cost: a debug round.
Ruling C2: keep #699's newest-observation-wins rule inside the stack (agent's choice) — it is main's fixed behaviour; Finding 1's description of Phase 3 was wrong — cost if wrong: one extra free GET on a stale 'asleep'.
Ruling C3: accept the 4 amended commits (test fix folded into the commit that broke it).
Ruling C4: accept "BLE read moves the wake hold" as superseded (fewer wakes) — cost: a hold up to one read longer.
C5: deploy/phase35-live retarget at next deploy.
Wake regression fix: rebase/phase3 2a973cc0 (1778 passed, +19 lib), rebase/phase3.5 58c43197 (1864 passed, +17). Review dispatched.
Wake fix review: approve. Ruling F1: a spent arm whose last send was a failed wake may use the desire's one re-arm (≤2 more wakes, ≤4 paid/desire) — car offline 30–60 min must still get its limit like main — cost if wrong: ≤$0.04 more per stranded desire. Ruling F2: free checks 120 s apart after a failed wake (free only). F3 test, F4/F5/F6 trims, F8 clear inFlight last. Fix round dispatched to the fixer.
Wake fix round 1: rebase/phase3 dc48ccdd (1782 passed, lib 27,302), rebase/phase3.5 a698f753 (1868 passed, lib 27,405). Worst case never-online limit+start: 7 wakes/4h then stop. rebase/* pushed as backup (new names; vehicle-model/* untouched).
Wake fix re-review: all rulings applied; R1 (ERROR wake blocks re-arm) taken — one-line, closes the last stranded case. Round 2 dispatched.
Wake fix round 2: rebase/phase3 3fcae411 (1783 passed, lib 27,303), rebase/phase3.5 5df98114 (1869 passed, lib 27,406). Controller read lib diff. Wake fix: complete. rebase/phase3, rebase/phase3.5 backup branches updated (force-with-lease, own backup refs).
2026-10-17: vehicle-model/* force-pushed to rebased tips (phase1 ec8790ca, phase2 31e5d185, phase3 3fcae411, phase3.5 5df98114; old tips 8e07669/6a6c14e/db47522/5c133bef); rebase/* removed. Docs archived to fork branch docs/vehicle-model-planning f2be0f60.
User 2026-10-17: PR titles by phase (not n/4); PR2 drops #374 and HA live claim; BLE default timeout → 15 s (dispatched, sonnet a466373fc6f346684, on phase3.5).
BLE default timeout 15 s: a3b9c60 pushed (1869 passed). PR drafts updated.
heldLimits rationale: CHANGELOG + HeldLimits header on phase3.5 (54059990, ff push); PR3 draft explains format change.
User 2026-10-17: drop heldLimits rename — keep chargeLimits key + (outside, held) tuple keyed by VIN; absence = not overriding. Task 8 dispatched (opus) aa0681a07c855c6c8 on phase3 then rebase 3.5; force-push after review; box settings converted by hand at next deploy.
Task 8: phase3 7ff8d9ae (1781 passed, lib 27,241 −62), phase3.5 ab6df576 (1866, 27,386 −21). Kept [outside,-1] when nothing held (Rules.decideChargeLimit uses outside for blind BLE applies). Review dispatched.
Task 8 review: approve after Important (c6 removes entry). Ruling: entry stays once written ([outside,-1] = nothing held) — protects blind BLE applies — except Forget drops it. Fix round dispatched.
User 2026-10-17: never write a charge limit when the current limit is unknown (any provider); current may come from any channel. → drop sendWhenUnknown; absence is the only 'nothing held'; remove entries. Task 8 fix round redirected.
User UI notes 2026-10-17 → Task 9 brief (drop Tier, providers one per line, source names, rename Held limit). Dispatch after Task 8 lands on phase3.5. Open PRs not gated on midnight run (user).
Task 9 brief + item 5 (capability instead of 'listed').
Task 8 redirected round: phase3 a678b9b5 (1778, lib 27,215), phase3.5 6af811a1 (1863, 27,360); parity counts unchanged. Accepted: load drops nothing-held entries silently; expiry drops entry. Asked to fold log-test fix into 48b4ff9b so every 3.5 commit is green.
Task 9 + item 7 (scan button stuck: auto-refresh while scanPending).
Task 8 fold: phase3.5 ad029963 (1863 passed; every 3.5 commit green on affected tests). Re-review of redirect + Task 9 dispatched.
Task 8 re-review: rule holds on every write path. Ruling F1: a load that drops nothing-held entries may save — dropping them is a real change, one write, harmless; the 'no save' requirement was only for clean files — accept. Nits 2/3 parked (keep '-1 sentinel' phrase removed: policy charge_limit -1 still exists). Task 8: complete.
Task 9: b6a4d5f4 (1867 passed, lib +60 → 27,420). keepsAlive=False for telemetry claim (accepted: lastSeen keeps reported cars). Review dispatched.
User 2026-10-17: Gen3 doc changes came in Phase 2 → separate follow-up PR (on top of phase3.5) after the stack opens, not Task 10 in 3.5.
Gen3 docs: separate PR on top of phase2 (user); branch docs/gen3-vehicle-model; dispatched.
Task 9 review: approved; 5e254a06 (tier deleted; 1866 passed; lib 27,414). Force-pushed phase3 a678b9b5, phase3.5 5e254a06.
User: 'TeslaAPI' must never show as a source — Owner API or Fleet API. Fix dispatched (opus) aef12a9e9a41ab42f: observations record slot (OwnerAPI/FleetAPI). Gen3 docs: docs/gen3-vehicle-model 6f284ce9 (merge-tree clean vs phase3.5), not pushed.
Source names: 1029809b (OwnerAPI/FleetAPI; syncSource stays internal 'TeslaAPI'; 1868 passed; lib 27,425). Pushed. Dev-box stale lastSeenSource accepted (refreshes on next sighting).
2026-10-17: opened ngardiner/TWCManager#703 (phase1→main), #704 (phase2→phase1), #705 (phase3→phase2), #706 (phase3.5→phase3), #707 (Gen3 docs→phase2). Tracker updated. Close #702 if #706 merges first.
Linked #703–#706 as GitHub stack #708 (gh stack link). #707 not in the stack (branches off phase2).
