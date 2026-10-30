# SDD ledger — plan: .superpowers/plans/2026-10-17-vehicle-model-phase4-control-tick.md

BASE 1029809b (phase3.5 tip, PR #706). Lib 27,425 (main 23,180). Phase 4 must end smaller than it starts.
User decisions 2026-10-17: drop the 6 A spike workaround (call out in PR body for Nathan); no adoption of manual charging on/off or amps (spec amended); two-pass distributor deferred to issue ngardiner/TWCManager#709.
User 2026-10-17: target main parity (23,180) by end of Phase 5 → −4,245 across Phases 4+5; Phase 4 aim ≈ −2,000+. Sent to planner.
Planner draft: ≈ −830 (≈ 26,595). 6 tasks.
User 2026-10-17: flex and dampening are NOT ported into the rearchitecture (delete; call them out in the PR, with the spike workaround, as features not ported — re-add on demand). Size goal softened in #703–#706 ("expected to shrink further; may not reach main's size; remaining gap stated and explained").
Ruling: keep the distributor's water-fill fair share (plan Decision 2) — default install unchanged; only TeslaAPI-disabled installs move — cost if wrong: those installs' sharing differs from the old formula.
Plan revision dispatched to planner (flex/dampening removal).
Plan revised: ≈ 26,560 projected (−865).

## Pre-flight (preflight.md, tables there): GO-WITH-FIXES, 22 findings
Ruling F1: tests get an offers-only beat; rows depending on the distributor get realistic amps_max or a (b) tag; parity row 26 counts must not change — test plumbing must not move paid counts — cost: a few tests.
Ruling F2: keep BASE's countSlaveTWC() > 0 gate on controlPass — main/BASE never ran the distributor without a Gen2 slave; dropping it is an untagged behaviour change with possible paid Fleet amps — cost if wrong: Gen3-only installs keep today's behaviour.
Ruling F3: rename the new attribute (not targetAmps) so the existing legacy guard stays meaningful.
Ruling F4: Task 4 keeps the stop-cancel call until Task 5 moves it (no gap between tasks).
Ruling F5: keep minAmpsToOffer.
Ruling F6: port BASE's per-pass clear of the lift flag in mode 2 (mode switch mid-session re-lifts as today).
Ruling F7: gates and stop-cancel stay suppressed during the chargeStopMode-2 silence, as BASE returns early.
Ruling F8: tick/beat ordering must reproduce BASE's observable order; the test helper encodes it per path.
Ruling F9: slaves not yet heard from get no offer (Review Focus 1 wins over Task 4 text).
Ruling F10: Task 2 handles the 401 path (no clear() of a token pasted mid-POST), locks restore(), re-queues refreshTokens in finally.
Ruling F11/F12: map the listed tests (widen grep to tests/unit); keep the subtractChargerLoad regressions (not spike tests).
Ruling F13: keep BASE's own-rate check — no relabel that lets a TWC point clear a VehicleEndpoint's rate.
Ruling F14–F21: apply as written. F22: take the ~15–20 extra behaviour-neutral deletions.
Plan revision dispatched to planner.
Plan revised per pre-flight: ≈ 26,615. Task 1 BASE 1029809b.
Task 1: dispatched implementer (opus, skill template) a0b986b87bd8e0592, BASE 1029809b
Task 1: implementer DONE_WITH_CONCERNS 874a20d9 (−48 lib; 1881 passed).
Task 1: review spec ✅, quality Approved.
Task 1: minor (deferred): test_rs485_serial_only.py:220 uses ast.unparse (Python 3.9+; CI matrix has 3.8; precedent in test_provider_registration.py:151)
Task 1: minor (deferred): shutdown flushRS485 unguarded — a send error skips close() (TWCManager.py:1985); loop drops one message on send error (TWCMaster.py:349) — comment
Task 1: minor (deferred): invalid-length VIN now upper-cased before logging (log text only)
Task 1: minor (deferred): _baseRule copy kept in test (brief contradicted itself; only reading that keeps the 10k test)
Task 1: complete (commits 1029809..874a20d, review clean)
Task 2 BASE 874a20d9
Task 2: dispatched implementer (opus) a269b9e3e13ed5fce, BASE 874a20d9
Task 2: implementer DONE_WITH_CONCERNS b782b843 (+32 lib; 1895 passed).
Task 2: review spec ❌ (waiter shares in-flight result after the slot changed → pasted refresh token refused unsent, spent r1 restored; reproduced). Quality: Needs fixes.
Task 2: minor (deferred): refreshToken/clientID read after the claim outside the lock (TeslaTokenSlot.py:219 vs :244) — capture under _cond
Task 2: minor (deferred): readers (snapshot/usable/status) unlocked; comment overclaims "never half-written"
Task 2: minor (deferred): first periodic refresh + listPending retry move to +300 s (TWCManager.py:839) — note in PR body
Task 2: minor (deferred): lib +32 vs expected +22
Task 2: minor (deferred): full suite "1 warning" unattributed
Task 2: minor (deferred): test_teslatokenslot.py:373–383 assumes threads start within 0.2 s (flaky)
Task 2: fix round 1 implemented 984f889e (1896 passed; lib +39 total).
Task 2: fix round 1/5 (1 addressed, 0 open — paste during in-flight refresh now POSTs; commits b782b84..984f889)
Task 2: minor (deferred): rare redundant extra refresh when a caller enters after setTokens but before _refreshing clears (valid, single-use-safe); _refreshOnce could advance _claimedAt
Task 2: complete (commits 874a20d..984f889, review clean)
Task 3 BASE 984f889e
Task 3: dispatched implementer (opus) afb044dc21bc4d15f, BASE 984f889e
Ruling (supersedes F2, user 2026-10-17: Gen3-only is valid): distribute when ≥1 Gen2 slave OR ≥1 Gen3 unit; vehicle-only keeps BASE (no distribution, no Fleet amps). Gen3-only was never controlled on main/BASE (only distributeEVSEPower call gated on countSlaveTWC()>0) — tag (g), call out in PR — cost if wrong: Gen3-only installs start being throttled, which is the point. Sent to Task 3 implementer mid-task. Gen3 Modbus server already runs on its own thread (Gen3TWCs._server_thread), parallel to the Gen2 serial loop.
Ruling update (user 2026-10-17): distribute whenever any endpoint with a working provider exists (Gen2, Gen3, BLE-only, API-only, HA); countSlaveTWC gate dropped. Vehicle-only Fleet amps bounded by reconciler rules; new parity row (h) with paid counts; Gen3-only (g). Sent to Task 3 implementer.
User 2026-10-17: keep the 1 s control tick.
Task 3: implementer BLOCKED (WIP a5560c20): parity row 26 — 0 HTTP still, but BLE charging-start now precedes set-amps 32 (lift and start first desired on the same pass after the one-beat lag; reconciler order LIMIT, CHARGING, AMPS).
Ruling: accept the reorder under (d) and update row 26's expected order as INTENTIONALLY CHANGED — no paid call, no lost command; the car starts at its previous amps and gets 32 A on the next send (≤15 s) — cost if wrong: ~15 s of lower-rate charging at session start.
Ruling: (h) partial — a BLE-only install with no TeslaAPI-listed car gets no VehicleEndpoint (presence only from TeslaAPI atHome); defer to Phase 5 (presence port), note in PR — cost: BLE-only vehicle control waits for Phase 5.
Task 3: implementer DONE 87c48973 (−38 lib; 1910 passed; parity rows unchanged except 26 (d); new rows 29/30 (h)).
Task 3: review spec ❌ / Needs fixes — Important 1: no-slave windows on a Gen2 install (startup before linkready, after slaveTimeout, dead adapter) make home cars look vehicle-only → paid set_charging_amps.
Ruling: while a Gen2 RS-485 interface is configured, a window with no slave heard (startup, timeout until re-link, dead adapter) counts as blind: cars that could be on that TWC get no VehicleEndpoint — ruling 1 meant vehicle-only installs, not Gen2 installs with a transient gap — cost if wrong: a car on a dead-adapter TWC isn't amps-controlled via API (TWC falls back to its own limit).
Task 3: minor (deferred): unexplained "1 warning" in full suite
Task 3: minor (deferred): stale docstrings (VehicleEndpoints.py:4-5, test_control_tick.py:1-2, docs/config_examples.md:10-12 flex text)
Task 3: minor (deferred): ControlTick failure log has no detail (add exc_info at DEBUG or first occurrence)
Task 3: minor (deferred): fragile side_effect list in test_control_tick.py:1802
Task 3: minor (deferred): untargeted-beat early return skips print_status/override — comment
Task 3: minor (deferred): lib −38 vs −58 planned; trim expanded docstrings
Task 3: fix round 1 implemented 8c673fc7 (1911 passed; lib Task 3 −33).
Task 3: fix round 1/5 (1 addressed, 0 open — Gen2 install with no slave linked is blind in all three windows; commits 87c4897..8c673fc)
Task 3: minor (deferred): RS485 defaults enabled — vehicle-only control (h) needs the RS485 interface disabled; a car on an install that leaves RS485 enabled with no TWC is treated as blind. Note in PR.
Task 3: complete (commits 984f889..8c673fc, review clean)
Task 4 BASE 8c673fc7
Task 4: dispatched implementer (opus) ae8640193b05f88fe, BASE 8c673fc7
User 2026-10-17: rate should be set before the start command (minimises overshoot when tracking solar). Ruling: reverses the row-26 acceptance — when AMPS and a CHARGING start are both due for a car on the same pass, send AMPS first (reconciler order CHARGE_LIMIT, AMPS, CHARGING, keeping the limit-then-start gap). Queued as Task 4b after Task 4 (same reconciler area; avoid parallel edits). Row 26 should return to BASE order.
Task 4: implementer DONE_WITH_CONCERNS a84079f4 (−293 lib; 1928 passed; parity counts unchanged). Row 26 back to BASE order (amps before start) — matches the user's wish; Ruling: accept, (d) annotation removal correct. Task 4b still adds the reconciler guarantee (amps before start when both due on one pass) with its own test.
Task 4: review spec ✅, quality Approved.
Task 4: minor (deferred → carried into Task 5): first beat after a slave's first reply runs the protocol-2 gates with lastAmpsOffered == -1 → may withdrawStartCharging for ≤1 s; skip gates while offer is None (TWCSlave.py:880–881, :690–699)
Task 4: minor (deferred): ChargingPoint.setTargetPower ~75 lines with nested withdraw/own closures (most of the −293 vs −320 shortfall)
Task 4: minor (deferred): stale comment Gen2TWCProvider.setAmps ~85 ("serial loop sends on the next heartbeat")
Task 4: minor (deferred): per-TWC cap DEBUG line now logs every tick (TWCSlave.py:933–946); de-dup like _cappedLogged
Task 4: minor (deferred): debug.html.j2 Advanced Settings table now empty — drop section/form
Task 4: minor (deferred): no test pins TWC-only point holding raw watts (mode 3 <6 A, protocol-1 min 5)
Task 4: minor (deferred): suite "1 warning" detail not recorded (-rw)
Task 4: complete (commits 8c673fc..a84079f, review clean)
Task 4b: brief written by controller (user decision; not in plan file). BASE a84079f4
Task 4b: dispatched implementer (opus) a19b56e68328c0adf, BASE a84079f4
Task 4b: implementer DONE 6b89f9fd (+2 lib; 1933 passed; parity counts and order identical in all 51). Warning = pre-existing urllib3 InsecureRequestWarning in test_enphase_ems.
Task 4b: review spec ✅, quality Approved.
Task 4b: parked — cross-queue race (rate on cloud worker, start on BLE worker) — Ruling: out of scope; Fleet never sets amps where BLE/TWC can, so mixed-worker rate+start is rare — cost if wrong: occasional start-before-rate on such installs.
Task 4b: minor (deferred): real-Fleet ordering test uses sleep loop (test_charging_reconciler.py:~185)
Task 4b: minor (deferred): no combined limit→rate→held-start test
Task 4b: minor (deferred): Reconciler.py:92-94 comment omits why stops keep stop-first
Task 4b: complete (commits a84079f..6b89f9f, review clean)
Task 5 BASE 6b89f9fd
Task 5: dispatched implementer (opus) a76291e61c9524218, BASE 6b89f9fd (carries Task 4 minor: gates skip while offer is None)
User 2026-10-17: comment rule (as-designed, no history; alternatives only where the obvious isn't right). Added to global-constraints.md for all later tasks and reviews; Task 6 sweep to remove history-style comments across files the stack touched (expected a few hundred lines). Memory saved.
Line counts without comments: 1.3.4 code 14,617; main 16,382; phase3.5 19,579 (+19.5%); phase4@6b89f9fd 19,411. Comment lines main 3,141 vs phase3.5 3,945.
User: no phases or PR/issue numbers in code comments (added to rule).
Task 5: implementer DONE 9e3e72c8 dc2609f5 (−66 lib; 1942 passed; parity identical).
Task 5: review spec ✅, quality Approved.
Ruling: chargeGate may take the key as an argument (brief's pinned signature relaxed) — closes the read-twice race cheaply — carried into Task 6 — cost: trivial signature change.
Task 5: minor (deferred → Task 6): vacuous assertion in test_no_gate_acts_before_the_first_offer (test_control_tick.py:413–414) — replace with controlPass on an unheard slave
Task 5: minor (deferred): chargeGate lacks type hints/docstring
Task 5: minor (deferred): DEBUG text differs from BASE wording (cosmetic)
Task 5: complete (commits 6b89f9f..dc2609f, review clean)
Task 6 BASE dc2609f5 (brief + controller additions)
Task 6: dispatched implementer (opus) a921f5bca63fd243d, BASE dc2609f5
Task 6: implementer DONE_WITH_CONCERNS 6dd84437 159070c0 02bfb49d f506104d (lib 27,026→26,450, −576; phase −975; 1947 passed; parity unchanged). Comment sweep itself removed only 11 lines (implementer judged most comments explain why).
Task 6: review spec ✅, quality Approved (comment sample: 0/70 narrate history; 159070c0 behaviour-neutral, −42).
Task 6: minor (deferred): test_one_distributor_entry misses module-level calls (serial loop is module code)
Task 6: minor (deferred): test_control_tick.py:1–3 header stale + phase tag
Task 6: minor (deferred): ragged comment reflows (Rules.py:3 107 chars; TeslaAPI._readFresh mid-sentence break)
Task 6: minor (deferred): live-check.sh — REPO hard-coded to scratchpad, rollback leaves detached HEAD, cp without sudo
Task 6: minor (deferred): EVSEInstance.controllers = [] shared mutable default
Task 6: complete (commits dc2609f..f506104, review clean)
Final review dispatched (fable — threading/concurrency, big diff) a076cc09844810cd4 on 1029809b..f506104d. Pushed vehicle-model/phase4 as backup (no PR).

## Final review (final-review.md): With fixes — 3 Important, 9 Minor; triage table there.
Ruling I1: guard the serial loop and shutdown on an Interface module being present (fakeMaster send block, RX, linkready, flushRS485, close) so Gen3-only and vehicle-only installs run without a traceback loop — the user asked for these installs to be supported — cost: a handful of guards.
Ruling I2: ControlTick logs the traceback (exc_info) on the first failure and every 60th; after 30 consecutive failed passes it withdraws offers (zero offer; the TWC falls back to its idle minimum) and logs ERROR, resuming normal offers on the first successful pass — fail safe like BASE's stalled loop (heartbeats stopped) rather than holding a stale offer — cost if wrong: a persistent bug stops charging instead of overshooting.
Ruling I3: capture (refreshToken, clientID) under _cond at the claim and pass into _refreshOnce.
Ruling minors: fix 4 (test tags/header), 5 (black on test_control_tick.py), 6 (drop empty Advanced Settings section), 7 (config_examples flex rationale), 8 (no offer/timestamp drift during the mode-2 silence — restore BASE), 9 (publish amps_offered/amps_desired only on change), 10 (one liftedSession reset); leave 11, 12 and the triage table's "Leave" lines.
Final fix dispatch: one fresh implementer (opus).
User 2026-10-17: fail-safe (withdraw offers after 30 failed passes) confirmed. No Phase 4 PR until ≥1 day soak on the box; deploy after the final fix wave + re-review.
Final fix wave: f506104d..7648704d, 10 commits (1955 passed; lib 26,492, +42; parity byte-identical).
Final fix re-review: 10/10 addressed; NEW Important: publish-on-change (ef1c8fc5) + MQTT's default 60 s ratelimit drops changes → ampsOffered/ampsDesired stale indefinitely. Minors: withdrawal doesn't reduce a vehicle-only car carrying its own rate (comment overclaims); stale lastAmpsOffered during withdrawal; noisy WARNING if chargingPoints keeps raising; (a)–(h) tags remain in tests.
Ruling (residual, load-bearing, surfaced to user per skill — no second fix wave): smallest fix is reverting ef1c8fc5 (MQTT's limiter already bounds traffic) — before the soak deploy.
User 2026-10-17: approved follow-up (revert ef1c8fc5; reword withdrawOffers comment; replace (a)–(h) tags with plain statements; PR notes name tests). Brief followup-brief.md.
Follow-up: decde9ed 57dcea94 (1954 passed; lib 26,490). pr-notes size updated by controller.
Follow-up re-review: all addressed. Phase 4 tasks + final review + follow-up complete. Deployed 57dcea94 to box 2026-10-17 21:34 (backups ~/twcmanager-{settings,config}.json.bak-20261017-phase4; rollback target 1029809b). Soak ≥1 day before PR.
Soak: midnight 2026-10-18 PASS on 57dcea94 — 00:00:16 Scheduled; 00:00:18 BLE wake before setChargeLimit: done; set-limit failed rc1 'unknown' first try, quick retry landed; 00:00:39 wake before startCharging; charging 00:00:41 at 48.7 A (SOC 61, limit 70). No tick failures, no tracebacks.
Soak day 1 (2026-10-17 21:34 → 2026-10-18 21:35): no restarts, 0 control-tick failures/tracebacks; midnight charge 00:00:41; two real depart/return cycles handled; 102 BLE command failures (mostly no-wake limit lowering to a sleeping car every 5 min); paid calls not directly logged (logging gap) — inferred Fleet set_charge_limit at 11:30, ~13:15+ restore, 15:18 (≈$0.003). Soak PASS pending user OK to open the Phase 4 PR.
Follow-up (user 2026-10-18 'Fix the code'): Gen2 RS-485 link never needs disabling — brief followup-gen2-link-brief.md, opus implementer dispatched on 57dcea94. Ruling: closed Gen2 link retries every 30 s and doesn't blind; same-port-as-Gen3 stands down — keeps late USB enumeration working for Gen2 users — cost if wrong: API may rate a car on a Gen2 TWC while its adapter is out (TWC on fallback limit). Phase 5 rebases onto the result; live check (not new full soak) before PR.
Gen2-link follow-up: implemented 6f59b1a4 (+32 lib); review pending
Gen2-link review (opus): Needs fixes — Important: queued RS-485 msgs sent late on reopen (stale mode-3 stop). Fix round 1 dispatched: drop outbox while closed; getBufferLen catches OSError (real unplug reaches retry path; pre-existing gap); drop redundant close() guard. Stale slaves while closed accepted (errs safe).
Gen2-link fix round 1: 8754a516 verified inline (drop outbox while closed + INFO count; OSError catch on read/send/getBufferLen; close() reverted). Approved. lib +41 vs +30 target — accepted (drop branch). Next: live check on box, then PR text.
2026-10-18 23:10: box on 8754a516 (deploy/phase4-gen2link); slave 8244 linked, SHB flowing, 0 tracebacks. Midnight cycle tonight on this build. Rollback 57dcea94.
2026-10-19 00:00: midnight on 8754a516 PASSED — policy 00:00:28, BLE limit (1 retry), start 00:00:57, 48 A by 00:01:15, 0 tracebacks.
