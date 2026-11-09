# SDD ledger — plan: /home/mbishop/github/TWCManager/.superpowers/plans/2026-11-01-fleet-charge-backfill.md

Spec: /home/mbishop/github/TWCManager/.superpowers/specs/2026-11-01-fleet-charge-backfill-design.md
Worktree: /home/mbishop/github/TWCManager/.claude/worktrees/fleet-backfill (branch feat/fleet-charge-backfill from origin/main d83c1591)
Baseline: 2585 passed, 1 xfailed.
Scope this session: Tasks 1-7, then final review. Task 8 stops for the user (ship gate: several days of load log). Task 9 only after user go-ahead.

Ruling: test command is `PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration` from the worktree — the shared .venv (symlink) has an editable install pointing at the main checkout's lib; without PYTHONPATH tests run the wrong code — cost if wrong: none.

## Pre-flight scan

| Pair / task | Produces -> consumes | Finding |
|---|---|---|
| T1 -> T4 | field `chargeEnergyAdded` -> Snapshot.energy | consistent |
| T2 -> T4, T6 | Snapshot, ChargeLedger.observe/end/isOpen/wattsBetween/toJSON/fromJSON/prune | consistent names/types |
| T3 -> T4, T5, T6 | believedAmps(v), chargingAmps(ledgered) | consistent; T4 liveWatts builds on believedAmps |
| T4 -> T5 | suspect(vin, at, why), fleetOnly(master, v) | consistent |
| T4 -> T6 | Watch.ledger, liveWatts(vin) | T6 restores ledger in loadSettings: builder must check Watch exists by then |
| T5 <-> T4 | both edit Watch._visit triggers | T4 owns poll/session; T5 owns trigger sources. Ruling: T4 may leave today's wake/arrival/plug/door asks as they are; T5 converts them to suspect() for fleetOnly cars |
| T1 self | tests vs code | consistent |
| T2 self | table vs tests | consistent |
| T3 self | allocation pin expected to pass before code | intentional pin, not a vacuous test (asserts specific amps) |
| T4 self | removes paid paths, tests updated not deleted | consistent |
| T5 self | afterWrite needs send time | plan allows recording it in Run.py |
| T6 self | consistent |
| T7 self | changelog depends on tag check | consistent |

## Tasks
Task 1: dispatched (haiku), BASE d83c159, implementer a3ac88b41abed7f73
Task 1: review d83c159..b166b8f: Needs fixes. Important: CHARGE_FIELDS makes BLE claim chargeEnergyAdded it never observes.
Task 1: minor (deferred): test does not assert observation source.
Ruling: fix by mapping BLE chargeState.chargeEnergyAdded in TeslaBLE.get_charge_state (the car's ChargeState carries it), not by excluding BLE — BLE cars then supply the field too — cost if wrong: BLE claims a field its JSON lacks; fall-back to excluding.
Ruling: BLE JSON key chargeEnergyAdded unverified (box has BLE disabled) — verify on a BLE install before ship — cost if wrong: BLE cars never supply energy; Fleet still does
Task 1: fix round 1/5 (2 addressed, 0 open; commits b166b8f..85b38e9)
Task 1: complete (commits d83c159..85b38e9, review clean)
Task 2: dispatched (sonnet), BASE 85b38e9
Task 2: complete (commits 85b38e9..36b798a, review clean)
Task 2: minor (deferred, LIKELY FIX before merge): backfilled start not clamped to the car's last segment end — a later session's energy backfill can overlap earlier segments and double-count (ChargeLedger._open)
Task 2: minor (deferred): prune drops 'seen' with the car; live() called for non-overlapping open spans; edge tests missing (partial clip, hint after stamp, None energy on close, json.dumps round-trip); test literal 11520*700/700
Task 3: dispatched (sonnet), BASE 36b798a
Task 3: complete (commits 36b798a..00a9c0f, review clean)
Task 3: minor (deferred): pin's first assertion only an upper bound (<=8); stale rate write older than reading used for a new start; dense newer-lambda readability; report lacked raw pytest output
Task 4: dispatched (opus), BASE 00a9c0f
Ruling (T4 concern 1): fleetOnly requires a paid cloud charge read; Owner-only cars stay as today — spec non-goal 'Owner API installs behave as today' — cost if wrong: none
Ruling (T4 concerns 4,5): carried to Task 5 — (4) a fleetOnly car believed charging with no session and no suspicion gets suspect(now, 'believed charging') in _visit; (5) a load step during an open suspicion records its time as the start hint while T stays earliest — both are trigger semantics — cost if wrong: a stuck charging belief / a less precise start
Ruling (T4 concern 2): fleetOnly(master, v, deaf) param is acceptable; all Task 5 callers are inside Watch, which holds deaf state — cost if wrong: Reconciler.afterWrite misses deaf BLE cars; Task 5 must route through a Watch method
Task 4: review 00a9c0f..24e56de: Needs fixes. Important: (1) deaf gate lets detection wants pay and skip snapshot; (2) fleetOnly depends on transient readiness, orphaning open sessions / double-count in T6.
Ruling (T4 minor 1, away poll): brief scopes polling to cars at home — treated as spec deviation, fixed in round 1 — cost if wrong: a few lines
Task 4: minor (deferred): retry gate can pull a fleetOnly fix retry forward on a pending detection want; no test of fleetOnly fix-read retry / courtesy read still paying; watts computed for non-Charging snapshots (contract says 0) [folded into round 1 as trivial? no — deferred]; why.startswith('load step') string coupling (-> Task 5); load-step hint lost behind earlier wake (-> Task 5)
Task 4: fix round 1/5 (3 addressed, 0 open; commits 24e56de..2c94fc7)
Task 4: complete (commits 00a9c0f..2c94fc7, review clean)
Task 4: minor (deferred): _locate consumed even when courtesy-window want yielded; _locate/_unheard not cleared when a car leaves (one bounded paid read possible on return)
Task 5: dispatched (opus), BASE 2c94fc7
Task 5: review 2c94fc7..507401d: Needs fixes. Important: believed-charging rule and _stale re-suspect on unchanged evidence after give-up -> ~55 polls/hour until sleep (probe-confirmed).
Task 5: minor (deferred): afterWrite calls commanded() before CHARGE_LIMIT _save (exception would lose save); _wakeCheck check-then-submit race can erase TWICE/inflight; load-step 'first' sample can be arbitrarily old after a gap (suspicion given up at once); fleetOnly wake still asks a read for deaf BLE car; wake/door T = noticing pass; staleness also gated on emsTrigger (undocumented); hint uses latest step (per ruling) vs spec 'earliest'
Task 5: fix round 1/5 (1 addressed, 0 open; commits 507401d..12a99f3)
Task 5: complete (commits 2c94fc7..12a99f3, review clean)
Task 5: minor (deferred): _spent never pruned (one per car); Watch.py not black-clean (pre-existing) — check repo formatter policy at final review
Task 6: dispatched (sonnet), BASE 12a99f3
Task 6: complete (commits 12a99f3..2225a25, review clean)
Task 6: minor (deferred): one-tick undercount/overlap at class transitions; test_registry_callers import tidy; HTTPControl ledgerWatts conditional readability; pre-existing DST offset in stored history keys
Task 7: dispatched (sonnet), BASE 2225a25
Task 7: complete (commits 2225a25..16959bf, review clean)
Task 7: minor (deferred): FAQ repeats 'a few minutes late'; preconditioning sentence wording; pre-existing 'charger' at Vehicle_TeslaAPI.md:79
Final review: dispatching (fable) over d83c159..16959bf
Final review d83c159..16959bf: No. Critical: charge_energy_added is per plug-in, not per charge (resets on unplug) — resume while plugged backfills cumulative energy (double count / spike). Important: afterWrite -> commanded(sentAt=None) raises TypeError on SATISFIED-by-read, skipping the charge-limit save. Minor: _wakeCheck duplicates _visit status submit (+race).
Ruling: Critical confirmed by our own 24 h log — 11-01 00:05 session followed a 10-31 12:31 session with no unplug; snapshot energy 0.26 before, 3.28 after vs TWC 3.35 (ratio 0.98, implausible for a fresh counter; 0.26 carried over fits 0.93) — fix in the final wave — cost if wrong: none (delta and clamp are safe either way)
Ruling: include reviewer Minor 1 (_wakeCheck fold into _visit) in the fix wave — user treats library growth as a red flag and it removes a race — cost if wrong: small rework
Final fix wave: dispatched (opus), FIX_BASE 16959bf
Final fix wave: re-review 16959bf..084b0f4: findings 1-3 ADDRESSED; new Important I-1: counter drift-down after a stop is never observed (polling stops after close), so a low-amp resume whose first snapshot hasn't regrown past the drift is read as a reset -> full-counter spike (repro: 42 kW for 5 min).
Ruling: I-1 is real and load-bearing (green-tracking stop/start pattern); no second fix wave per process — surfaced to the user with the smallest fix: treat snap.energy >= last - margin (~0.5 kWh or a fraction of last) as continuation with delta max(0, snap.energy - last), plus a test resuming without observing the drift — cost if wrong: history spikes on low-amp resumes until fixed; must be fixed before Task 9.
Branch state: 13 commits d83c159..084b0f4, 2649 passed / 1 xfailed, not pushed. Workspace kept (final review not clean).
User 2026-11-02: fix I-1 now; live test need not wait on logger. Fix 09abbe38 (DRIFT_KWH 0.5 + 2 tests), sonnet re-review Approve (minors applied in amend). Suite 2650 passed / 1 xfailed.
BLE key verified on box via tesla-control state charge: chargeState.chargeEnergyAdded (float) — ruling closed.
Deployed 2026-11-02 07:15 as 4c520694 = box a843b942 + 14 commits (suite green on that stack). Rollback a843b942; backups ~/twcmanager-{config,settings}.json.bak-20261102-071043-backfill.
Live 2026-11-02 08:47: car came home and plugged in; last fix (08:36) on the road so NOT_HOME; load step skipped it (pre-existing rule); caught by 08:56 courtesy read. User: fix it, cherry-pick cleanly. Fix on main-based branch fix/away-car-load-step 10e491c9 (rise brings an away cloud-only car's courtesy read forward once it could be back; docs/Settings.md line); sonnet review Approve (minor: up to 2 reads/window, accepted, comment says so). Cherry-picked clean onto feat (5f5db217). Suites: main 2587, feat 2657, box stack 2653 — all green. Deployed 153f57a8 at 09:09.
Live 2026-11-02 10:33: away-car fix worked (read 10:34:50 = backAt, limit lowered 10:34:55). Ledger missed the charge: paid read saw Charging, first free snapshot already Complete. User: count paid reads, never trigger one; a paid read alone may open a session (accepted: per-minute free polls until a newer free snapshot or sleep). Fix ec03b836 on feat (poll feeds FleetAPI + cached snapshots oldest first; 3 belief tests now use a HomeAssistant reading). Sonnet review Approve (minors: cross-source clock stamps; paid read alone clears suspicion — both pre-existing shape). Suite 2655 / 1 xfailed. Deployed 014b428e 11:55.
Live 2026-11-02 13:30: arrival read 13:31:28 (rise), limit lowered; ledger again missed it — away car got no load-step suspicion, command suspicion (13:31:29) postdated the paid read. Fix 8315da0c (rise suspects an away awake Fleet-only car from the step; no polls while away). Sonnet review Approve (minors: give-up at 600 s if backAt later; dryer-step since can predate an arrival — optional hardening). Suite 2655 + 1 flaky wall-clock test (test_the_current_slot_..., Task 6) fixed in 3cb842c0. Deployed 765bdd0e 14:05.
