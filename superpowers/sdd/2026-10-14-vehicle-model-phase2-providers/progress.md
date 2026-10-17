# SDD ledger — plan: .superpowers/plans/2026-10-14-vehicle-model-phase2-providers.md
Spec: .superpowers/specs/2026-10-13-vehicle-model-design.md
Worktree: scratchpad/wt-vm2, branch vehicle-model/phase2 off vehicle-model/phase1 8e07669. Baseline 1153 passed (tests minus API/integration). venv scratchpad/venv.
Rule: every pytest run capped: timeout 300 systemd-run --user --scope -q -p MemoryMax=2G <venv>/bin/python -m pytest ... --timeout=60 -p no:cacheprovider
User approved plan (Gen3 provider, summed headroom, cloud VIN via live_status) 2026-10-14.
Pre-flight scan: 24 findings (8 high) in preflight.md; no forward deps; findings 4,5,9 confirmed by running fixtures at base.
Ruling (pre-flight 1-24): accept every proposed ruling in preflight.md as written; #15 HA stays last per spec (reached only after free providers and Fleet fail; suppressed under ble_only), constraint reworded + CHANGELOG; #16 api_only keeps suppressing TeslaBLE only (reason given). Plan text corrected in place by the planner before Task 1 so briefs carry the fixes — cost if wrong: rework visible in review.
Plan corrected in place (all 24 applied; Decision 36). Task 1: BASE 8e07669
Task 1: implementer dispatched (sonnet). Open question to user: mode-3 handoff threshold — TWCSlave hardcodes 6 (TWCSlave.py chargeRateControl==3 and desiredAmpsOffered < 6), preflight #1 mirrored it in ampsRange; user suggests 'below the TWC's supported min'. Settle before Task 3.
Task 1: implementer DONE 84316de (1157 pass)
Ruling (user, mode-3 threshold): chargeRateControl 3 hands off to the vehicle API below the TWC's own minimum to offer = max(minAmpsTWCSupports, config minAmpsPerTWC), not the literal 6; TWCSlave mode-3 condition and Gen2TWCProvider.ampsRange floor (preflight #1) both use it; tests per TWC kind (6 A, protocol-1 5 A, 3-phase 1 A). User unsure 3-phase accepts <6 A offers but chose to trust minAmpsTWCSupports. Carry into Task 3 dispatch (overrides plan's 'floors at 6 A under mode 3') — cost if wrong: 3-phase mode-3 users offered 1-5 A by the TWC instead of via API; revisit if live reports show it.
Task 1: minor (deferred, final wave): __all__ omits capability names
Task 1: complete (commits 84316de, review clean)
Task 2: BASE 84316de
Task 2: implementer dispatched (opus)
Task 2: implementer DONE_WITH_CONCERNS 02ed0d7 (1176 pass); wiring (providerOrder/registerProviders/noticeOnce) is Task 3/8 per plan
Task 2: minor (deferred, final wave): OverflowError escapes debugCommand (Order.py:273)
Task 2: carry -> Tasks 3-5: ampsRange() must never be None while ready() for Gen2TWC/Gen3TWC/TeslaBLE (else Fleet billed)
Task 2: complete (commits 02ed0d7, review clean)
Task 3: BASE 02ed0d7
Task 3: implementer dispatched (opus) with mode-3 user ruling + ampsRange-not-None constraint
Ruling (user, supersedes earlier mode-3 ruling): Option 1 — least code; TWCSlave mode-3 handoff keeps literal 6 (minAmpsToOffer() refactor stays); Gen2TWCProvider mode-3 floor = max(6, minAmpsToOffer()) so provider matches TWCSlave; no CHANGELOG line; real behaviour comes with Phase 3 layered actuators.
Task 3: implementer DONE 8e86068 33dc48a (1189 pass); fallback minAmpsPerTWC 6
Task 3: minors (deferred, final wave): range floor = max(slave.minAmps, minAmpsToOffer()) (mode 3 max(6, that)); M3 key race ready()/ampsRange() -> Order.py; maxAmps override uncapped by wiring; mode-2 stopCharging ignores VIN; _slaveForKey lowercase VIN; minAmpsPerTWC default inconsistency (6/12/5); document controller.Gen2TWCs.ranges
Task 3: complete (commits 8e86068..33dc48a, review clean)
Task 4: BASE 33dc48a
Task 4: implementer dispatched (opus)
Task 4: implementer DONE_WITH_CONCERNS 1c71d67 7e2019b (1204 pass); concerns 1-7 in report; docs Controller_Gen3TWCs.md stale
Task 4 review: spec PASS, quality FAIL — C1 3-phase house load divided by phases (stop doesn't stop), C2 served(0)<wanted publishes H=0 (full fuse; single unit not unchanged), I1 Gen3 docs stale. Ruling: fix C1 (plan's H*V formula wrong; correct to H*V*phases), C2 (re-solve with all demands unlimited), I1 docs rewrite; minors M1-M8 per reviewer's fix-now advice in task-4-review.md — cost: none. Task 4: fix round 1/5 dispatched
Task 4: fix round 1 DONE f6b1517 84eb6fb (1210 pass); left M2 (ramp overshoot -> Task 7+), M3 (documented), M5, M6 (-> charging points); plan formula corrected to H*V*p
Task 4: fix round 1/5 (C1,C2,I1 + M1,M4,M7,M8 addressed; commits 7e2019b..84eb6fb; task-4-rereview-1.md)
Task 4: carry -> Task 7: N1 orphan anon vehicle if observe raises after correlation; update Controller_Gen3TWCs.md 'later release will use cloud VIN' line; M2 ramp overshoot (optional)
Task 4: minors (deferred): M3 documented, M5 ready/ampsRange race, M6 dedup by VIN -> Task 11
Task 4: complete (commits 1c71d67..84eb6fb, re-review clean)
Task 5: BASE 84eb6fb
Task 5: implementer dispatched (opus)
Task 5: implementer DONE_WITH_CONCERNS 607e6d1 (1216 pass)
Ruling (Task 5 c1): api_only BLE-read gap between Task 5 and Task 8 accepted (branch not deployed per task, as Phase 1 Task 9 ruling); Task 8 must close it — add to Task 8 dispatch: test api_only suppresses BLE reads once registerProviders runs — cost if wrong: none unless a mid-phase commit is deployed.
Task 5: minor (deferred): ampsRange inverted if availableCurrent in (0,1) (legacy vehicleMaxAmps)
Task 5: complete (commits 607e6d1, review clean)
Task 6: BASE 607e6d1
Task 6: implementer dispatched (opus)
Task 6: implementer DONE_WITH_CONCERNS 3f89dea (1226 pass); c1 Owner 401/403 mid-read -> Fleet reads same cycle (one paid read earlier, error path only)
Task 6 review: spec PASS, quality PASS WITH FIXES — I1 paused-slot test passes without guard (needs requests_mock call_count==0), I2 no test pins paused-Owner->Fleet handoff (M2 survives). Concern 1 ruling KEEP (measured: worst +$0.002/car/h only while Owner token keeps 403/410/412; no wake/command cost).
Ruling: fix I1, I2 (+ minors the review marks fix-now); carry -> Task 7: ready() rejects None vehicle/undeclared cap; Task 7 calls ready(None, READ_WALL_CONNECTOR_VINS) — relax there. Later idea (out of phase): stop hourly retry of an Owner token Tesla keeps refusing (412).
Task 6: fix round 1/5 dispatched
Task 6: fix round 1 DONE 70b53af (tests only; 1228 pass); m2 two claims shown per Tesla -> Task 10
Task 6: fix round 1/5 (I1,I2,m1 addressed; 3f89dea..70b53af; task-6-rereview-1.md)
Task 6: complete (commits 3f89dea..70b53af, re-review clean)
Task 7: BASE 70b53af
Task 7: implementer dispatched (opus) with carries: ready(None) relax, N1 orphan anon, Gen3 docs cloud VIN, late-VIN attach
Task 7: implementer DONE_WITH_CONCERNS 1f197e3 9ba3504 (1255 pass)
Ruling (Task 7 c1, user-approved order): cloud VIN outranks single-candidate. A single-candidate identity is provisional: polling continues while the session has no cloud-confirmed VIN, and a cloud VIN that differs replaces the guess (re-attribute the session). Polling stops only on a cloud VIN. Fix in fix round — cost: polls continue at ~60 s (free) while a Gen3 is occupied with a guessed car.
Ruling (Task 7 c2): reviewer to judge stale-VIN risk; minimal mitigation acceptable (e.g. ignore a cloud VIN equal to the unit's just-ended session VIN until a later poll confirms it) — decide in review.
Ruling (Task 7 c3): add backoff for failing /api/1/version (e.g. 10 min) — background thread must not spend 3 s every 5 s.
Ruling (Task 7 c4, c5): accept; documented.
Task 7 review: spec PASS, quality PASS WITH FIXES — I1 c1 provisional guess + replace, I2 stale departed VIN ignored until >=60 s after edge, I3 version 600 s backoff + 404 final, I4 latch 410/412 (+404 live_status on Owner). Ruling: fix all + fix-now minors. Task 7: fix round 1/5 dispatched
Task 7: fix round 1 DONE 61ca7ea (1266 pass); not fixed M2,M4,M5; I2 residuals noted
Task 7: fix round 1/5 (I1-I4, M1, M3 addressed; 9ba3504..61ca7ea; task-7-rereview-1.md)
Task 7: minors (deferred): M2, M4, M5 (task-7-review.md)
Task 7: complete (commits 1f197e3..61ca7ea, re-review clean)
Task 8: BASE 61ca7ea
Task 8: implementer dispatched (opus) with api_only BLE-read carry
Task 8: implementer DONE_WITH_CONCERNS f0b6f27 (1281 pass); api_only carry closed
Task 8 review: spec PASS, quality PASS WITH FIXES — I-1 guard registerProviders per module (warn, skip), I-2 realistic pure-Gen2 boot test (unconfigured TeslaAPI+HA). Concerns 1-3 accepted (c2 release note: HA providerSuppressions now drops HA reads). Task 8: fix round 1/5 dispatched
Task 8: fix round 1 DONE eee9425 (1283 pass)
Task 8: fix round 1/5 (I-1, I-2, c2, M-1, M-2 addressed; f0b6f27..eee9425; task-8-rereview-1.md)
Task 8: minors (deferred): M-3, M-4 (task-8-review.md)
Task 8: complete (commits f0b6f27..eee9425, re-review clean)
Task 9: BASE eee9425
Task 9: implementer dispatched (opus); carries OverflowError in debugCommand (Task 2 minor)
Task 9: implementer NEEDS_CONTEXT (9e4e8f9 b6fa18d 558b967 committed; 1263 pass) — brief's test drops the #660 vehicle-rate raise over Fleet.
Ruling (Task 9 raise): keep today's behaviour — façade setChargeRate passes amps=None to candidates (the local-amps rule applies only to the setAmps queue command / Task 10 endpoints); drop the brief test's first assertion; test that a Fleet-only raise reaches Fleet. Why: the TWC cannot lift the car's own current limit; dropping the raise caps a throttled car (regression of #660). Supersedes plan Decision 8's "raise dropped" clause. Cost: one $0.001 command per session, as today.
Ruling (Task 9 attempts): per-provider attempt counts must equal today's _calculate_retries result for that module (HA 1 if today 1, etc.); debugCommand makes exactly one attempt per provider (user-initiated; no double-billed wake).
Ruling (Task 9 HA): HA provider receives its own vehicle (lookup by VIN) for setChargeRate; HA available() = module enabled(); test both.
Ruling (Task 9 accepted): 0->1 clamp for selection, False when nothing succeeds, BLE doc label edit, stats keys by provider, api_only keeps BLE out of reads. Debug dropdown BLE-only wake -> Phase 6 (minor).
Task 9: fix round 1/5 dispatched (rulings)
Task 9: rulings applied edf61bf (1269 pass); setChargeRate walks every ready unsuppressed provider for the car (no amps/local-path rule); BLE tried only with a claim on that VIN (accepted: keyless VIN would time out anyway)
Task 9 review: spec PASS, quality FAIL — C1 targeted commands skip Fleet while TeslaAPI vehicle list unloaded (BLE+Fleet: no fallback when BLE fails), I1 HA legacy car_api_charge/applyChargeLimit ignore VIN (Fleet+HA two cars: stop all). Ruling: fix C1 per review; I1 skip HA for targeted car_api_charge/applyChargeLimit (today's behaviour, no HomeAssistant.py edit); minor: debug setChargeRate must not apply local-path rule (match façade); other minors per review fix-now. Task 9: fix round 2/5 dispatched
Task 9: fix round 2 DONE 006818f (1275 pass). Ruling: accept I1 narrowing (HA skipped for targeted car_api_charge/applyChargeLimit unless the target is HA's only car) — keeps HA-only installs with TeslaAPI disabled working as at eee9425 (D7).
Task 9 re-review 1: C1, I1(as ruled), M1-M4 addressed; new N1 (HA-only with 2+ HA cars: targeted start/stop sends nothing). Ruling (N1): option (b) — HA car_api_charge/applyChargeLimit honour the target VIN when given (act only on that car; broadcasts unchanged); drop the _ownVehicleOnly restriction; extends Task 9 file list to HomeAssistant.py. Why: fixes Fleet+HA, HA-only multi-car and HA+unconfigured TeslaAPI alike, instead of re-opening stop-all. Changes HA-only multi-car targeted stop from 'all HA cars' to 'the target car' (a fix; CHANGELOG line). Plus m-1 test comment/assert. Task 9: fix round 3/5 dispatched
Task 9: fix round 3 DONE acd223f (1277 pass)
Task 9: fix round 2/5 (C1, I1 narrowed, M1-M4; task-9-rereview-1.md) and fix round 3/5 (N1 via HA honours VIN, m-1; task-9-rereview-2.md) addressed
Task 9: minors (deferred): m-2 HA 10 s rate limit shared across cars (delayed, not lost); M5 debug dropdown BLE-only wake -> Phase 6
Task 9: complete (commits 9e4e8f9..acd223f, re-review clean)
Task 10: BASE acd223f
Task 10: implementer dispatched (opus); carry Task 6 m2 (two claims shown per Tesla)
Task 10: implementer DONE_WITH_CONCERNS 4aa71a1 (1267 pass)
Ruling (Task 10 c1): interim double-budget/paid path via lastVIN-attributed stopped car accepted only as intermediate (not deployed mid-phase); Task 11 MUST close it with tests: stopped car on its Gen2 (lastVIN) is one point, no separate VehicleEndpoint budget, no Fleet setAmps; mode 2 no second Fleet path beside TWCSlave's setChargeRate. Branch must not be deployed between Task 10 and Task 11.
Carry Task 6 m2 (two claims shown) -> Task 11 or final wave.
Task 10: review clean (spec PASS, APPROVED); c3-c5 accepted (c5 follow-up: 60 s retry backoff on failed send, final wave/Phase 3)
Task 10: minors (deferred): BLE-only endpoint positive test; HA billed-tier amps writer (by design); setAmps dropped if VehiclePriority disabled; lost controller-test coverage; blind pass resets last-sent. Gen3 occupied key None not blind -> Task 11.
Task 10: complete (commits 4aa71a1, review clean)
Task 11: BASE 4aa71a1
Task 11: implementer dispatched (opus) with Task 10 concern-1 test list + Gen3 key None blind + BLE positive test; Step 6 live check held for coordinator/user
Task 11: implementer DONE (Steps 1-5) 9358db4 (1286 pass); 8 real-object tests fail on old distributor (5 A / 20 A setAmps shown). Gen2 state 00 + sleeping car pinned as pre-Task-10 behaviour (Phase 5).
Task 11 review: spec PASS, quality NOT APPROVED — I1 stale Gen2 lastVIN groups two TWCs into one point, each gets full target (32+32 A on 40 A budget; wiring-budget regression). Ruling: fix per review (a local endpoint never joins a group with a local member) + real-object test; also clear/limit consideration of lastVIN left to implementer if minimal. Task 11: fix round 1/5 dispatched
Task 11: fix round 1 DONE b72c79c (1289 pass); m3,m4 fixed; m1,m2 carried; m5,m6 CHANGELOG wording -> final wave
Task 11: fix round 1/5 (I1 wiring overload, m3, m4 addressed; 9358db4..b72c79c; task-11-rereview-1.md, 6,860-case wiring sweep clean)
Task 11: minors (deferred): m1, m2; m5, m6 CHANGELOG wording; Phase 5: mode-2 lastVIN charge rate to a departed car (TWCSlave.py:1242-1250); Gen2-00 sleeping car paid path
Task 11: complete through Step 5 (commits 9358db4..b72c79c); Step 6 live check pending box availability
Final review dispatched (fable): review-final-8e07669..b72c79c.diff
Suite at b72c79c: 1289 passed, 1 xfailed (capped).
Final review: WITH FIXES — C1 TeslaAPI.applyChargeLimit returns None on success -> façade falls through to HA (second billed command on Fleet+HA); I1 idle-TWC minimum offers minAmpsTWCSupports (6) but heartbeat zeroes below minAmpsPerTWC (default 12) so rule inert; M1-M5.
Ruling (final wave): fix C1 + audit every façade-walked method on every provider module for success-as-None (and any other ambiguous return) with a table in the report; I1 (Gen2TWC.minAmps = max(minAmpsTWCSupports, minAmpsPerTWC, honouring override) + real-object test with minAmpsPerTWC 12); M1 stale chargingState if cheap; M2 docs/CHANGELOG (Gen3 provider, cloud VIN, din, Gen2TWCs.ranges, default Fleet-never-sets-amps rule + BLE-claimed UMC effect, relabels, m5/m6); M3 remove dead declarations; deferred fix-now: lost controller-test coverage, BLE-only endpoint positive test (if still missing). M4, M5: no. One fix dispatch + one re-review.
Final fix wave dispatched (BASE b72c79c)
Final fix wave DONE: 0ec5853 69343f2 3458ef0 1430ab3 b9d0713 25a451b 03537f3 940c1c2 (1309 pass). Audit found 2 more C1-class paths (throttle "error" -> "skipped"; car_api_available during wake hold).
Ruling (final-wave concerns, same wave before re-review): c1 — when the walk reaches HA only because an earlier billed provider returned "error", throttle HA per (VIN, command) to Fleet's 60 s cadence (façade); c2 — real TeslaBLE/TeslaAPI applyChargeLimit accept vin/remoteOnly and honour vin (act only on that car), tests with the real methods; c3 — TWCSlave.py:577 startCarsCharging gate uses minAmpsToOffer(); c4 — re-reviewer to verify wire sum incl. heartbeat idle offer never exceeds wiring max/budget.
Concern rulings DONE f007fb3 d761a9d 8bdb9a6 (1318 pass); remoteOnly -> TeslaBLE declines (accepted). Final re-review dispatched.
Final re-review 1: Ready to merge YES (wire-sum sweep 14,760 cases: overshoot only via pre-existing TWCSlave rules, identical before/after). Ruling: fix both new minors now (targeted applyChargeLimit passes vin=target to car_api_available — avoids $0.02 wake of other cars; idle reservation also requires controller budget >= minPower) — one-line each + tests.
Last minors DONE 992c396 8959380 (1320 pass); controller budgets now built even when no point wants power (idle reservation deducts) — accepted.
Phase 2 code complete at 8959380 (branch vehicle-model/phase2 on phase1 8e07669). Pending: Task 11 Step 6 live check (box held by 1.3.4 session); user decision on landing.
User (2026-10-15): configured limits are already the 80% continuous derating; brief excursions into the buffer are fine if the next allocator cycle rebalances; the idle-TWC minimum is deliberately NOT counted. Ruling: revert 8959380's controller-budget gate+deduction AND drop the remaining_watts gate on the idle minimum (idle TWC gets its minimum whenever the policy allows any charging, available_watts > 0); not deducted from budgets. Wire-sum reviews must apply this rule (transient OK, sustained overshoot is a bug). Open to user: idle minimum is minAmpsToOffer (12 A with default minAmpsPerTWC 12) vs hardware 6 A.
User ruling: idle TWC always offers the HARDWARE minimum (minAmpsTWCSupports), to minimise overshoot; minAmpsPerTWC governs allocation only — a charging point that can't be allocated at least minAmpsPerTWC (minAmpsToOffer) gets a stop (0). Heartbeat must let the idle hardware-minimum offer reach the wire (not zero it below minAmpsPerTWC) on the distributor path.
User: Gen2 TWC treats an offer of 0 as its hardware minimum (current behaviour) — no heartbeat change; builder told to skip it.
Idle minimum DONE c010817 (1325 pass): distributor idle target 0 (Gen2 treats 0 as hw min), nothing gated/deducted; idleMinimum flag now unread. Verified in main/1.3.4: heartbeat offers minAmpsTWCSupports to idle TWC when other cars charge and power per car >= min; 0 (code 05) when none charging.
Idle review APPROVE (17 probes: wire 6 A when another car charges with enough power, 0 when none — matches main; paused-car start request matches main). Cleanup dispatched: remove idleMinimum, stale docstring/test header, CHANGELOG/Interface_RS485 wording, wire-6A test.
Idle cleanup DONE 6a6c14e (1326 pass): idleMinimum removed, docstrings/CHANGELOG/RS485 docs corrected, wire-6A test added. Phase 2 head now 6a6c14e.
Task 11 Step 6 live check (box, 07:15-07:19, 6a6c14e): PASS except one item not exercisable.
- Boot: "Providers: Gen2TWC, TeslaBLE, TeslaMateVehicle, OwnerAPI, FleetAPI, HomeAssistant" (rank order); VehicleEndpoints registered; 1 boot-time "Main loop stalled 2.2s" (same as 8e07669), none after.
- Car plugged, charge Complete, TWC state 00: one point Point-Gen2TWC-8244 (anonymous, no VIN at 00); zero Fleet set_charging_amps; raise sent over BLE (48 A).
- BLE charge-limit apply 50% landed on attempt 1; no HomeAssistant fall-through (0 lines).
- Debug-page wakeVehicle -> HTTP 200, served by TeslaBLE (free).
- No token in logs (tesla-control "Set OAuth token name to ''" only).
- Not exercised: a Point-<VIN> while the car actively charges (car already Complete); covered by Task 11 real-object tests.
- Rolled back 07:19 to cfd0086, config restored (logLevel 20), settings kept; service active, no errors.
Task 11: complete (commits 9358db4..6a6c14e incl. final wave; live check done).
User: push, don't merge. Pushed to origin (ngardiner/TWCManager): vehicle-model/phase1 8e07669, vehicle-model/phase2 6a6c14e. No PRs opened.
