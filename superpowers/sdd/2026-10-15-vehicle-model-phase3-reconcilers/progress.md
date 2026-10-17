# SDD ledger — plan: .superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md
Spec: .superpowers/specs/2026-10-13-vehicle-model-design.md
User answers (2026-10-15): (Q1) 60 s BLE-first before a disruptive stop only when BLE is actually set up for that car (ready BLE claim); otherwise disruptive stop at once. (Q2) live check incl. rfkill window OK, but user not home now — schedule later. (New) no separate multi-minute fallback per property: free-channel failure must be shared per car across aspects.
User: if BLE hasn't been attempted for a while, do a BLE ping before assuming it's still down (shared-fallback rule).
Pre-flight 1: 50 findings (14 High) in preflight.md. Ruling: plan returned to planner for revision against all findings (spec binding, proposed rulings as default); second pre-flight after. No code until user approves the revised plan.
Plan revised: 49/50 resolved; F3 partial rejection (no probe when no paid candidate — BLE retry at RETRY cadence already serves) accepted. Second pre-flight dispatched.
Pre-flight 2: 45 resolved, 5 partial (F3 ok, F11, F26, F37, F38), 13 new (1 High N1: settled-without-stamp re-sent every pass — disruptive stop loop, repeated paid charge_stop; N12 backoff 3600 s survives new desire). Ruling: planner revises (N1 per proposed fix: re-plan a settled desire only on new evidence; Gen2 heartbeat records current; plus all partials and new mediums/lows); narrow third check after.
Plan revision 3: 17 resolved (N1-N13, F11, F26, F37, F38), 0 rejected. Narrow pre-flight 3 dispatched.
Pre-flight 3: 16 resolved, N5 partial, 6 new Medium (S1-S6) + 2 Low. Rulings: N5 helper must run on make()/setup() masters (stub getModuleByName for Interface/Policy/webhook, fakeMaster in CONFIG, bytes TWCID); S1 None guard; S2 default policyAmpsRequested + no second num_cars_charging_now(); S3 new desire resets FREE-provider backoff only, paid backoff resets on success/arrival/plug-in per spec; S4 TWC current is new evidence only for cars no vehicle source describes; S5 import order; S6 hands-off when point offers nothing applies at plan time too; Lows fixed.
Plan revision 4: 9 resolved (N5, S1-S8), 0 rejected; drive helper verified at base. Pre-flight considered converged (3 rounds: 50 -> 13 -> 8 findings, all resolved); remaining risk to per-task reviews. Awaiting user approval.
User approved plan 2026-10-15; be sparing with Fable (Opus default).
Worktree: scratchpad/wt-vm3, branch vehicle-model/phase3 off 6a6c14e. Baseline 1326 passed, 1 xfailed.
Task 1: BASE 6a6c14e
Task 1: implementer dispatched (opus)
Task 1: implementer DONE d9939bf (1339 pass)
Task 1: carry -> Tasks 3/6: report clears inFlight only by identity (endSession resets while lane holds attempt); records/health mutated outside store lock — single thread or store methods. carry -> later: store forget(key) hook on registry forget.
Task 1 review: spec PASS, quality PASS WITH FINDINGS — I1 no forget(key) (anon churn leak), I2 newDesire keeps UNSUPPORTED exclusions. Ruling: add forget(key) + call from registry forget/anon session end; newDesire drops UNSUPPORTED keeps REFUSED; minors (tests for concern-4 behaviours, lazy import outside lock + no masking). Task 1: fix round 1/5 dispatched
Task 1: fix round 1 DONE 7d5b87e (1347 pass)
Task 1: carry -> task creating master.desired: call master.desired.followRegistry(master.vehicleRegistry); Task 6: use AttemptRecord.exclude(provider, kind).
Task 1: fix round 1/5 (I1, I2, minors addressed; d9939bf..7d5b87e; task-1-rereview-1.md)
Task 1: carry -> Task 8: desired on anon key dropped at merge — re-set for the VIN.
Task 1: complete (commits d9939bf..7d5b87e, re-review clean)
Task 2: BASE 7d5b87e
Task 2: implementer DONE 0fd13a1 2588587 (1370 pass). Rulings: c1 accept (VIN wins, id: kept for Task 10); c2 REJECT drop — keep the user's outside limit as (80, None) with a warning (never lose the normal limit); c3 accept (reviewer to confirm wake comparison); c4 accept; c5 accept; c6 add a warning on case-collision; c7 accept.
Task 2: rulings applied 6e600dc (1373 pass)
Task 2 review: spec PASS, quality PASS WITH FINDINGS — I1 float limits read back as nothing (HA observes floats), I2 id: entry not adopted when TeslaAPI lists before loadSettings. Ruling: fix both (int-coerce integral floats; sweep carApiVehicles after heldLimits.load() and adopt on every _bind) + tests; m3 add vehicleListLock->settingsLock to lock-order comment; m1 note in CHANGELOG. Carry -> Task 6: adoption saves registry floats via the same int coercion. Task 2: fix round 1/5 dispatched
Task 2: fix round 1 DONE 2d87ed8 (1380 pass)
Task 2: follow-ups n1 n2 DONE 9a44495 (1383 pass); set stores rounded int without 50-100 clamp (accepted; apply-time rules clamp — carry to Task 6: decideChargeLimit must clamp held values to 50-100)
Task 2: fix round 1/5 (I1, I2, m1-m3; 6e600dc..2d87ed8; task-2-rereview-1.md) + n1, n2
Task 2: complete (commits 0fd13a1..9a44495, re-review clean)
Task 3: BASE 9a44495
Task 3: implementer dispatched (opus)
Task 3: first implementer stopped (usage limit) — left untracked tests/unit/test_lanes.py only. User said resume; fresh implementer dispatched (opus) treating the draft as a starting point.
Task 3: implementer DONE_WITH_CONCERNS 3f40b3d 43886b9 (1410 pass); lanes never mutate records (store methods only)
Ruling (Task 3 c1, c2): debug route 400 until Task 7 / bool returns reported ERROR until Tasks 4-5 — accepted as interim (no mid-phase deploy).
Task 3: carry -> Task 4: dispatch reads Outcome.kind in SETTLED before any provider returns Outcome through it. -> Task 6: report callback may run on lane or submitter thread, mutate via DesiredStore methods; beforeWrite gets one-shot attempts aspect=None; Desired._chargingLike passes raw value to satisfied (plan's takes Observation).
Task 3 review: COMPLIANT; APPROVED WITH REQUIRED FIXES — I1 post-success stamp/afterWrite raise reported as ERROR (paid resend), I2 billed wake ERROR doesn't abort. Stress probe: report-once holds. Ruling: fix I1, I2, M1 + cheap minors. Task 3: fix round 1/5 dispatched
Task 3: carry -> Task 6/7: dropped/replaced/cancelled outcomes report on the submit/cancel caller's thread — reconciler must never call submit/cancel while holding the DesiredStore lock.
Task 3: fix round 1 DONE 97377b8 (1415 pass; probe strict 9/9 x6)
Ruling (Task 3 M2): rate slot recorded only when a command is actually sent (final wave); M4 drain deadline may use monotonic (duration) — final wave; M6 noted.
Task 3: fix round 1/5 (I1, I2, M1, M3, M5, M7, M8; 43886b9..97377b8; task-3-rereview-1.md)
Task 3: minors (deferred, final wave): M2 rate slot only on send, M4 drain deadline monotonic, M6 BaseException kills thread
Task 3: complete (commits 3f40b3d..97377b8, re-review clean)
Task 4: BASE 97377b8
Task 4: implementer dispatched (opus)
Task 4: implementer DONE_WITH_CONCERNS bb512d0 (1423 pass)
Ruling (Task 4): c1 interim accepted (legacy BLE setAmps until Task 10; no deploy mid-phase); c2 fix now — demote raw tesla-control output logs to DEBUG (token-safety); c3 accept; c4 fix — ready() must not create store entries (non-creating lookup).
Task 4 review: COMPLIANT; PASS WITH FINDINGS — I1 raw tesla-control stderr at WARNING (2x), I2 ready() creates ControlState, I3 refusal in pairing window returns REFUSED (excludes BLE -> paid/backoff on first pairing). Ruling: fix all; I3 per review — return Outcome(ERROR, 'pairing') inside the pairing window, update the brief test; M1 + cheap Lows (L1 class attribute). Task 4: fix round 1/5 dispatched
Task 4: fix round 1 DONE f394844 (1428 pass)
Task 4: carry -> Task 8: Gen2 mode-2 start ready only while the slave exists (~26 s after stop); missing slave != not-stopped-by-us. -> Tasks 6/11: rc 0 with unknown output = retryable ERROR unknown (today's behaviour). -> Phase 4: pre-existing off-serial-thread RS-485 writes HTTPControl.py:906, TWCManager.py:370.
Task 4: fix round 1/5 (I1, I2, I3, M1, L1; bb512d0..f394844; task-4-rereview-1.md)
Ruling (carry -> Task 6): ERROR 'pairing' does not count as a BLE health failure (hold paid fallback while the pairing window is open); test it.
Task 4: complete (commits bb512d0..f394844, re-review clean)
Task 5: BASE f394844
Task 5: implementer DONE 81dc39b (1440 pass)
Ruling (Task 5): c1 RETIRED_ON_REFUSAL={command} accepted (keeps Storm Watch); c2 deviations accepted pending review; c3 interim paid increase on legacy dispatch path (Fleet setAmps 2 posts on failure, HA posts every time) accepted only as interim — Task 10 deletes the path; Task 11 parity must show no increase vs base. c4 carry -> Tasks 6/8 (firstChargeNeededTime reset; wakeDue before first wakeOutcome). c5 accepted.
Task 5 review: COMPLIANT; PASS WITH FINDINGS — I1 412 latches reads but commands stay usable (paid commands + wake every 30 min to refused token). 20 paid-call changes (9 up: 6 c3 legacy, debug repeat ok, 412 latch ok, M3 grace skip). Ruling: I1 — 412 on a command adds 'command' to refusedPurposes until token changes; a command 412 does not latch reads; M3/c4 reset firstChargeNeededTime when a need ends without waking; M4 wakeDue uses now for backoff; cheap minors. Task 5: fix round 1/5 dispatched
Task 5: fix round 1 DONE 098f7c8 (1451 pass); I1, M1, M3/c4, M4, L1-L4 fixed; listed: M2, M5 (with c3), M6 (Task 6 must call Lanes.allows), M7.
Simplification discussion with user (2026-10-15): proposed pausing after Task 5 to measure options 1-4 (drop unverified Gen3 cloud VIN/multi-unit headroom/HA commands; lanes on existing worker; one fallback rule; adoption for charge limit only; providers as data) before Tasks 6-11. Awaiting user choice.
Task 5 re-review 1: not clean — N1 (Important) M1 fix clears slot (wipes refresh token) on transient refresh failure. Ruling: fix N1 per review (refuse('command') for non-success/non-unreachable refresh; later success lifts it); M2 deferred to Task 6; N2 Low noted for Task 8. Task 5: fix round 2/5 dispatched
Task 5: fix round 2 DONE 39d7cfb (1454 pass); N1 tokens kept, refuse(command) on failed refresh
User decision (2026-10-15): simplify per options 2 (lanes on existing worker, two workers BLE/cloud), 3 (one fallback rule, keep per-aspect PAID_AFTER), 4 (adoption for charge limit only; CHARGING/AMPS stateless re-assert gated by own-write stamp — drop user-started/user-lowered session bounds), 5 (provider declarations as data where cheap). Option 1 not taken. Opus drafting revised plan for rework + Tasks 6-11.
Task 5: fix round 2/5 (N1; 098f7c8..39d7cfb; task-5-rereview-2.md); fix round 1 (I1, M1, M3, M4, L1-L4; task-5-rereview-1.md)
Task 5: minors (deferred): M2 wake_up 403 retires command purpose (-> Task 6/slim plan); M5, M6 (Lanes.allows), M7; new Low: 401 'expired' while expiry >1h left -> background refresh never retries, commands refused until token change/restart (final wave)
Task 5: complete (commits 81dc39b..39d7cfb, re-review clean)
User approved slim plan (.superpowers/plans/2026-10-15-vehicle-model-phase3-slim.md) with recommendations: Q1 one retry of a failed Fleet call after the retry gap (<= $0.001 extra per desire); Q2 'failing for the whole window + recent failure' confirmed; Q3 fixed hourly restore retry OK; Q4 keep (repeat stop waits for newer vehicle reading).
Pre-flight slim: 3 High, 10 Medium, 12 Low (preflight-slim.md). Ruling: accept all proposed rulings — H1 keep attempts() until Task 13; H2 hold NOT_SENT outcomes for RETRY[aspect]; H3 respectVehicleSchedule handsOff in Task 9 + Task 11 test + Task 14 row; M8 Q1 retry never includes a wake (keeps user-approved <= $0.001 extra); Task 13 checks the stated budget (<=1,400 added, >=3,000 removed) too. Planner applies; then Task 6.
Slim plan revised with all pre-flight rulings (0 rejected). Note: Decision 5 cost = <=$0.001 extra per desire plus at most one $0.002 read on a Fleet-only car (told user).
Executing slim plan (.superpowers/plans/2026-10-15-vehicle-model-phase3-slim.md) Tasks 6-14 in this ledger.
Task 6: BASE 39d7cfb
Slim Task 6: implementer dispatched (opus)
Slim Task 6: implementer DONE ff84ff3 (1455 pass); lib +664/-800 (net -136); gross adds include moved runAttempt.
Ruling (budget): moved code counts as added in the gross budget — re-forecast after Task 9; the binding checks are net Phase 3 growth vs 6a6c14e and Task 13 removed>=added; report gross per task. Legacy queue behaviour changes (bool put, 64 cap, exit when closed, drop on unstarted drain, type-name logging) to be judged in review.
Slim Task 6 review: COMPLIANT; APPROVED WITH REQUIRED FIX — I1 stop put during worker exit gap accepted but never run/reported. Legacy queue changes judged safe. Ruling: fix I1 per review + M4 (traceback at DEBUG) if cheap. Slim Task 6: fix round 1/5 dispatched
Slim Task 6: fix round 1 DONE 163d8c1 (1458 pass; probe 14/14 x5); Task 6 total lib +683/-800
Carry -> Task 7: stale-desire value equality, start() before first submit, remove probeInFlight; never submit/cancel under DesiredStore lock. -> Task 13: 'lane' wording, LANE_DETAILS.
Slim Task 6: fix round 1/5 (I1, M2-M4; slim-task-6-rereview-1.md, probe 15/15 x3)
Slim Task 6: complete (commits ff84ff3..163d8c1, re-review clean)
Slim Task 7: BASE 163d8c1
Slim Task 7: implementer dispatched (opus)
Slim Task 7: implementer DONE ccbe58c (1454 pass; 4 tests removed with removed features); lib +151/-261 (net -110)
Slim Task 7: review PASS/APPROVED (slim-task-7-review.md).
Ruling: carry -> Task 8: add ERROR 'no vehicle'/'no provider' to NOT_SENT (no paidAt/free.failure); noteOutcome returns False for aspect=None (debug one-shot).
Slim Task 7: complete (commits ccbe58c, review clean)
Slim Task 8: BASE ccbe58c
Slim Task 8: implementer dispatched (opus) with Task 7 carries
Slim Task 8: implementer DONE cf63e52 (1551 pass; parity 7 shapes x 4 policies x 3 stop modes); lib +132/-92 (net +40)
Carry -> Task 9: noteOutcome never marks free channel failed for not-sent outcomes incl. free 'rules:' early return — confirm fits rules.
Slim Task 8: review PASS/APPROVED (3 mutations caught by parity test).
Carry -> Task 9: (a) Run.py _tagged mislabels 'backoff'/'no command token' as 'wake ...' so they miss NOT_SENT — fix; (b) wakeOutcome: do free online check before the wake-purpose refusal so an online car still gets commands after a wake refusal; (c) legacy wakeVehicle 403 -> reportScopeRefused('wake'); (d) persistent UNREACHABLE from a rules hook never starts Fleet fallback timer — decide.
Slim Task 8: complete (commits cf63e52, review clean)
Slim Task 9: BASE cf63e52
Slim Task 9: implementer dispatched (opus) with carries a-d
Slim Task 9: implementer DONE c4cbc50 1b69ec0 fd3f25f 3fbb5e4 (1637 pass); lib +586/-31; Reconciler.py 425, Rules.py 137
Ruling (Task 9 c5): NOT_SENT hold must not delay a NEW desire (esp. a stop) — hold is per desired value; fix in review round. c6 carry -> Task 10 (satisfied restore leaves held record).
Line re-forecast after Task 9: since 39d7cfb +1515/-1147 (net +368; gross adds already > 1,400 budget); since 6a6c14e +2994/-302 (net +2692). Forecast Phase 3 final net vs 6a6c14e ~ +1,000 (range +800..+1,300) assuming Tasks 10-12 ~+500 net and Task 13 ~-2,150. Slim estimate was +375. Raised with user.
User (2026-10-15): line budget is a target, not a limit; rearchitecture must simplify/dedupe — substantial non-test growth means we may be doing it wrong. Withdrawn: my proposal to loosen the Task 13 check. Action: dedup audit before Task 10.
Slim Task 9 review: CHANGES REQUIRED — C1 late outcome lands on replaced desire (stop never sent), I1 NOT_SENT hold spans desires, I2 any newer reading reopens paid path (12-50 paid/h), I3 paid fallback pays vehicle_data first. Ruling: C1 per review; I1 hold keyed on attempt.since >= d.at; I2 hard cap 2 paid sends per desire (one + one retry) AND a reading reopens only if its value differs from belief at the paid send; I3 blind retry skips the read, paid attempts accept readings up to PAID_AFTER+READ_MAX_AGE; minors M1-M5 per review. Slim Task 9: fix round 1/5 dispatched
Dedup audit dispatched (opus, read-only) -> dedup-audit.md; runs alongside Task 9 fix round.
Slim Task 9: fix round 1 DONE d2a7a57 (1645 pass; probe 24/24); lib +57/-22; I1 via newDesire clearing lastOutcome (accepted pending re-review); c2 one vehicle_data after a mid-flight desire change on Fleet-only-read installs — accepted (safety).
Slim Task 9 re-review 1: C1, I1, I3, M1-M5 resolved, I2 cap holds; new N1 (Important): Fleet-only lowered limit failing twice vs sleeping car (408) never resent; later start charges to 90 not 50. Ruling: paid sends that only got UNREACHABLE re-arm on any newer reading of the field (still bounded: <=2 per reading-episode, test counts); plus a start must not be submitted while that car's charge-limit desire is unsettled (limit-before-start holds even after paid cap). Slim Task 9: fix round 2/5 dispatched
Dedup audit done (dedup-audit.md): main 23,180; now 30,210; after planned Task 13 ~28,500 (+23%); all 10 ops ~26,750 (+15%); floor ~25.5-26k. 7 user decisions pending.
Slim Task 9: fix round 2 DONE d98d643 (1650 pass; probe 26/26); lib +40/-4; Reconciler.py 472. Open concerns: c2 a source republishing chargeLimit while car sleeps (HA) re-arms once per RETRY -> up to 12 paid/h; c4 REFUSED after <2 sends never counts as spent -> HA can block start indefinitely. Held pending user's audit decisions (esp. command-stack consolidation).
User decisions on dedup audit (2026-10-15): YES 1 (dissolve CarApiVehicle into registry Vehicle — own small phase before Phase 5), 2 (delete TeslaBLE retry layer + breaker, keep one in-call retry), 3 (held limits: migrate once at load, keep heldLimits, Rules native on HeldLimit), 4 (consolidate command stack), 6 (HA 10 s limit -> one reconciler minimum gap), 7 (delete unread summaries now). NO to 5: keep Gen3 cloud VIN and headroom solver (Gen3 is majority of deployed devices). Mechanical items (Task 13 misses, already-dead code, dead declarations, read-source/provider merge, one TeslaAPI HTTP helper, redundant rate limits) folded in.
Slim Task 9: closed at d98d643 (probe 26/26); open c2 (HA republish re-arms paid ~12/h) and c4 (REFUSED never spent -> HA blocks start) carried into the command-stack consolidation task with paid-count tests; branch not deployable until they land.
Slim Task 9: complete (commits c4cbc50..d98d643)

## Slim plan revision (Tasks 10–14) — user decisions 2026-10-15
- Planner revised Tasks 10, 11, 12a, 12b, 13a, 13b, 13c, 13, 14 in place; projected lib ≈27,000 (from 30,246 at d98d643).
- User: unmatched numeric-ID held limits are DROPPED after one warning (not kept in chargeLimits). Applies to Task 11.
- User: Fleet Telemetry readings ALWAYS re-arm paid sends, like BLE and TeslaAPI reads; HA and TeslaMate only when the value changed. Applies to Task 10 (c2).
- User: accept ≈250 over the 26,750 target; Phase 3.5 (CarApiVehicle dissolve) closes it.
- Pre-flight r4 dispatched (Opus) on revised tasks; output preflight-r4.md.

## Pre-flight r4 rulings (1 Critical, 10 Important, 11 Minor)
- Ruling: accept C1, I1, I3, I5, I6 (amps gap 15 s, matching main), I7 (30 s edge gap), I10, and all Minors — each verified against d98d643 by the reviewer — cost if wrong: small rework.
- Ruling: I2 accept — a Telemetry re-arm is allowed once per desire, so at most 4 paid sends per desire; the source must be exactly FleetTelemetryMQTT. This bounds the user's decision 2 without reversing it — cost if wrong: one fewer retry on a flaky Fleet.
- Ruling: I4 accept, with the same once-per-desire cap on the "reading shows charging" re-arm — otherwise repeated HA charging reports would re-arm without limit.
- Ruling: I8 — don't raise the 600-line stop rule. Keep the runner as its own small module (slimmed Run.py) instead of folding it into Reconciler.py; Workers and the lazy hook still go — cost if wrong: one extra file.
- Ruling: I9 — match against every usable token's list; drop only after at least one non-empty list; log the dropped VIN-less ID and limit value (no secrets) — matches user decision 1.
- Slim Task 10: dispatched, BASE d98d643
- Slim Task 10: implementer DONE_WITH_CONCERNS, commits 44c4ddb 846349b, suite 1666 passed 1 xfailed, lib −139 (expected −200; Run.py kept per I8 ruling).
  - Ruling: concern 1 (limit counts as spent when its one re-arm is used and no blind retry is left) is accepted — c4's intent is that an undeliverable limit never blocks the start; reviewer to verify no extra paid calls — cost if wrong: start before limit on a car that could still be reached.
  - Concern 4 (an UNSUPPORTED or REFUSED outcome stamps the send gap, delaying the fallback 10 s): reviewer to judge; lean toward stamping only outcomes that reached a transport.
  - Concern 7 carried to Task 11: wire registry.removed=desired.forget, reconciler.start()/drain(), master.reconciler.
- Slim Task 10 review: spec PASS; quality NOT YET (0 Critical, 2 Important, 6 Minor).
  - Ruling: I1 fix (the re-arm clears paidRetryDue). Concern 1's clause is kept only with this fix.
  - Ruling: I2 — c4 exclusion is computed over candidates(vehicle, SET_CHARGE_LIMIT), not the global ordered(); rewrite the M11 test.
  - Ruling: M1 — the send gap is stamped only for outcomes not in EXCLUDING. The brief is overridden: the gap exists to space real sends.
  - Ruling: M2 accepted as a known cost of the 4-send cap — if the one re-arm is spent before a start is wanted, the start goes without the limit. Revisit if it is seen live.
  - Ruling: M3 — "Complete" does not count as charging. Fix M4 and M6 and the remaining Minors.
  - Fix round 1: resume the implementer.
- Slim Task 10 fix round 1: bba7c4f, suite 1671 passed 1 xfailed, lib −134 total. M2 recorded above. Scoped re-review dispatched.
- Slim Task 10: complete (commits 44c4ddb 846349b bba7c4f; re-review APPROVED; lib −134)
- Slim Task 11: dispatched, BASE bba7c4f
- Slim Task 11: implementer DONE_WITH_CONCERNS, commits c4d9037 23cb7e8 2ecf54f, suite 1661 passed 1 xfailed (legacy tests deleted), lib −440.
  - Ruling: concern 2 (unmatched IDs are dropped only when every usable slot's list came back) is accepted as stricter and safer than the ruling.
  - Concerns 1 and 6 (vehicle-list loading and atHome for Fleet-only cars) go to the reviewer against pre-flight C1.
- Slim Task 11 review: spec PASS; quality NOT YET (1 Critical, 2 Important, 5 Minor).
  - Ruling: C1 — use the paid option. checkDeparture calls update_location(0) for cars we hold a limit on, never waking the car; this is the pre-task behaviour. Treating an unplug as a departure would change semantics: an unplug in the garage would restore the limit. Phase 5 (presence) replaces this — cost if wrong: the same per-departure read as main.
  - Ruling: I1 fix as reviewed — remember the VINs present at load(), merge later-added ones to HeldLimit(legacy.outside, store.held), and log any discard.
  - Ruling: I2 fix — queue a rate-limited checkCharge from an existing periodic path while the list is empty or IDs are waiting. Required before 12a.
  - Ruling: fix the Minors, except "limit-before-start lost until 12a", which is by design and closed by 12a.
  - Fix round 1: resume the implementer.
- Slim Task 11 fix round 1: d35a95c, suite 1666 passed 1 xfailed, lib −387 total. Concern 1 (3 paid reads for a held car unplugged at home) matches main — accepted; Phase 5 replaces it. Scoped re-review dispatched.
- Slim Task 11: complete (commits c4d9037 23cb7e8 2ecf54f d35a95c; re-review APPROVED; lib −387). Parked nit: HeldLimits.py:209-211 says 'kept' for a malformed entry — fold into Task 13.
- Slim Task 12a: dispatched, BASE d35a95c
- Slim Task 12a: implementer DONE_WITH_CONCERNS, commits f8b20ce c563d70, suite 1666 passed 1 xfailed (32 tests added, 32 removed), lib −977 (expected −850; 12b's delete list shrinks accordingly).
  - Ruling: concern 1 — main parity is required. An anonymous Gen2 point in mode 1 must still get start/stop, so the desire fans out to the cars whose atHome is set and which no other point claims, as main's broadcast car_api_charge did. Losing the stop entirely is a regression for the user's own Gen2 — cost if wrong: the same extra commands main sent.
  - Ruling: concern 2 — mode 2 must not add paid starts. On main a mode-2 start only offered amps, so paid (Fleet/Owner/HA) starts are suppressed in mode 2 like stops; a free BLE start is allowed — cost if wrong: a car that stopped itself waits for the next plug-in, as on main.
  - Concern 3 (a stop no longer resets the wake hold) and concern 4 (lost INFO8 token-state log): reviewer to judge; concern 4 should be restored somewhere cheap.
  - Concern 5 (an unreadable limit holds the start up to 300 s): reviewer to judge against c4.
- Slim Task 12a review: spec PASS; quality NOT YET (1 Critical, 4 Important, 5 Minor).
  - Ruling: C1 — on a paid provider, the attempt's wake (when the attempt may wake) runs before the read-before-write. Backstop: a repeated "could not read" counts as spent. Restores still never wake.
  - Ruling: I1 replaces my concern-1 ruling — follow main exactly. A mode-1 start with no VIN goes out unaddressed. A mode-1 stop, or a mode-3 start, for an anonymous point fans out to every at-home car on TeslaAPI's list plus every BLE-known VIN, with no exclusion of cars on other points. Apply the same rule in cancelStopCarsCharging and the zero-offer clear.
  - Ruling: I2 — suppress cloud starts in mode 2 only; mode 3's paid start matches main.
  - Ruling: I3 — restore minChargeLevel in handsOff.
  - Ruling: I4 — keep the delivered start record when the same value comes back with no newer reading. Test: offer flaps don't multiply charge_start.
  - Ruling: Minors — fix the concern-3 comment, restore the concern-4 log (once per change of reason), and fix the rejected-VIN block and the #591 check if each is small (≤15 lines); otherwise park with a note.
  - Fix round 1: resume the implementer.
- Slim Task 12a fix round 1: 5a42a6d, suite 1675 passed 1 xfailed, lib −852 total (+125 restored main behaviour). Concern 1 (a wake before the read may buy nothing) goes to re-review: a wake only when the value is genuinely unknown, and a stop never wakes an asleep car.
- Slim Task 12a re-review 1: NOT APPROVED. All 10 findings are fixed; new N1 and N2 (Important), N3 and N4 (Minor).
  - Ruling: N1 fix — _startWanted requires a start candidate that is not local and declares WAKE. Accept the bounded 300–600 s start delay in mode 2 for an asleep car with an unreadable limit.
  - Ruling: N2 fix — the provider's stopCharging returns early, settled, for a car known asleep; it spends no paid budget and doesn't re-poll. This is main parity.
  - Ruling: N3 — bound keep in one line to main's 60 s.
  - Ruling: N4 parked — rare, bounded by the backstop.
  - Fix round 2: resume the implementer.
- Slim Task 12a fix round 2: 8b22849, suite 1678 passed 1 xfailed, lib −833 total. Scoped re-review 2 dispatched (Sonnet).
- Slim Task 12a: complete (commits f8b20ce c563d70 5a42a6d 8b22849; re-review 2 APPROVED; lib −833). Carried to 12b: add the two N1 parametrised tests described in slim-task-12a-rereview-2.md. Parked: N4, and the 120 s asleep cache (matches main).
- Slim Task 12b: dispatched, BASE 8b22849
- Slim Task 12b: implementer DONE_WITH_CONCERNS, commits 11f9222 d2022a3 7deb924 d960e0c 9d3fb64, suite 1610 passed 1 xfailed (99 legacy tests deleted, 35 added), lib −820. Reconciler.py is 599/600.
  - Ruling: Gen3 units carry their own target in every mode (no layering) — wiring safety for the shared headroom outranks main's mode-2 routing of MergedEVSE — cost if wrong: a Gen3 mode-2 car is capped by its unit, not the car.
  - Ruling: VIN-less Gen2 in mode 2/3 must not pay N× — fan out only to at-home cars whose latest reading shows them plugged in or charging; if none is known, fall back to main's vehicles[0]. Reviewer to confirm the shape.
  - Ruling: the INFO "Tesla API is read-only" hint is restored now (cheap), not deferred.
  - Concern: the TWC-only heartbeat amps desire is not withdrawn below the minimum — reviewer to judge.
  - Added requirement (user question 2026-10-15): every deleted test must map to a replacement test or a ruling. The reviewer audits 12b's 99 deletions; the separate audit covers d98d643..8b22849 (deleted-test-audit.md).
- Deleted-test audit d98d643..8b22849: 79 deleted tests — 45 COVERED, 12 PLUMBING-ONLY, 10 INTENTIONALLY CHANGED, 11 PARTIAL, 1 GAP. 22 rewritten tests — 1 PARTIAL. Full table: deleted-test-audit.md.
  - Ruling: GAP row 61 — follow main. broadcastVehicles also includes HA cars that are at home and connected (main's unaddressed HA start/stop). Fix plus test.
  - Ruling: every PARTIAL gets its proposed test — rows 16, 28/29/31/32 (two-Fleet-car isolation with real requests), 56, 63/68/69/71 (add test_fleet_then_ha_never_in_one_pass), 77.
  - Ruling: R9 — the reconciler's report path must keep secrets out of logs at EVERY level, including DEBUG tracebacks. The test captures all levels. Fix if any exception text can carry a token.
  - These are bundled into Task 12b's fix round (same files).
- Slim Task 12b review: spec PASS with 3 deviations; quality NOT YET (0 Critical, 3 Important, 8 Minor). Deleted tests (100): 56 COVERED, 8 PARTIAL, 7 GAP, 10 INTENTIONALLY CHANGED, 19 PLUMBING-ONLY.
  - Ruling: I1 — gate the mode-3 lift on vehicleRateRaised, and reset it in ChargingPoint's below-floor branch. The brief's "user change after lift left alone" is honoured.
  - Ruling: I2 — use the reviewer's _anonCars() shape: plugged-in or charging by the latest vehicle-source chargingState, else vehicles[0]; applied to the heartbeat and the lift; withdraw desires for cars that leave the set.
  - Ruling: I3 — restore the hint once per Fleet slot change, plus the two refusal-logging tests.
  - Ruling: M2 — withdraw the heartbeat desire below the minimum.
  - Ruling: M8 — keep the design. HA is reached only when Fleet is unavailable or has REFUSED, never after a plain failure, so there is no double billing. Pin it with test_fleet_then_ha_never_in_one_pass (shared with the audit's PARTIAL rows 63/68/69/71).
  - Fix round 1 = the 12b review items + all 12b GAP/PARTIAL tests + all audit items (row 61 GAP, PARTIALs, R9).
- Slim Task 12b fix round 1: 3ba16dc..889e510 (7 commits), suite 1657 passed 1 xfailed, lib −742 total for 12b. Reconciler.py is 515 lines, Belief.py 100.
  - Ruling: row 61 follows main literally (an HA car counts as connected only via a TWC-reported VIN) — accepted.
  - Ruling: M6 cap = 4 matches the per-desire cap ruling — accepted.
  - Ruling: M3 mode 2 with an undeliverable rate behaves as on main — Task 14 row.
  - Parked for Task 13: WallConnectorVins.py:152 exc_info DEBUG traceback.
- Slim Task 12b re-review 1: NOT APPROVED. All six code fixes are pinned; the mapping spot-check caught 14/15 mutations. Ruling: fix N1 (positive plugged-in set; an HA reading counts only when 'Charging') and N2 (store a refresh token in the fixture). Fix round 2.
- Slim Task 12b fix round 2: 841eadd 464d83c, suite 1657 passed 1 xfailed, lib −731 total. N2's token is stored per test, not in the fixture (the 401 tests need none) — accepted.
- Slim Task 12b: complete (commits 11f9222..464d83c; re-review 2 APPROVED; lib −731). Known gap: an HA-only car that is plugged in but not charging falls back to vehicles[0].
- Slim Task 13a: dispatched, BASE 464d83c
- Live check: box deployed 464d83c (Task 12b complete) at 22:04 2026-10-15; rollback cfd0086 + ~/twcmanager-settings.json.bak-20261015-phase3. Overnight watchdog ~/phase3-watchdog (cron */10, 00:30–04:00, user OK'd). Midnight test: scheduled policy raises limit 50→70 (SOC 51), BLE-only start.
- Slim Task 13a: implementer DONE, commits 21ed474 9db3f1b, suite 1664 passed 1 xfailed, lib −282. Ruling: a 'ble: timeout' output is retried once; the unused config reads are deleted.
- Slim Task 13a review: spec OK, quality approved with I1 (the retry matches 'connection' in -debug output) and 3 Minors. Ruling: fix I1 (classify on the final error line, test with real -debug output), add the M1 test, log M3's quick retry at INFO, drop M2's redundant reset. Ruling: the box stays on 464d83c tonight — 13a stretches the retry after a timed-out limit to the 300 s gap, and the 00:30 watchdog could then roll back a slow start.
- Slim Task 13a fix round 1: f0327e5, suite 1670 passed 1 xfailed, lib −272 total. Scoped re-review (Sonnet).
- Slim Task 13a: complete (commits 21ed474 9db3f1b f0327e5; re-review APPROVED; lib −272). Parked: pre-session BLE errors (failed to discover service, etc.) aren't quick-retried; they fall to the reconciler's retry.
- Slim Task 13b: dispatched, BASE f0327e5
- Slim Task 13b: implementer DONE_WITH_CONCERNS, commits e3c7d71 fc7bd2f, suite 1675 passed 1 xfailed, lib −160. Ruling: the read cascade lives in ProviderOrder.read (reuses ordered/_ready; Registry doesn't import Providers) — accepted.
- Slim Task 13b: complete (commits e3c7d71 fc7bd2f; review APPROVED, 0C/0I/3M; lib −160). Carried to 13c: pin Minor 1 (a TeslaAPI status deferral ends the read walk; test for no HA read) and fix Minor 3 (HA fetch guard). Minor 2 parked.
- Slim Task 13c: dispatched, BASE fc7bd2f
- Slim Task 13c: implementer DONE, commits 9ca6210 f5d6a03 7ea8250 9e888b2 1028283, suite 1711 passed 1 xfailed, lib −85 (expected −120; the per-path differences are kept on purpose).
  - Ruling: accept both behaviour changes — vehicle reads time out after 10 s, and a refreshed token refused again retires the slot.
  - Ruling: vehicleListLock held across HTTP is pre-existing — reviewer to judge whether it can block the main loop; otherwise fix in Task 13.
  - Ruling: Storm Watch (TeslaPowerwall2.getStormWatch) gets the timeout and no exception text in Task 13.
- LIVE FAIL 2026-10-16 00:00: on 464d83c the Scheduled policy took over at 00:00:07, but the limit stayed at held 50 (SOC 51), so no charge. Nothing from the reconciler at INFO; TWC lastVIN '' after the 22:04 restart (car asleep, plugged in). Manually rolled back to cfd0086 + settings backup at ~00:14 (watchdog marked rolled-back). Saved log: box ~/phase3-watchdog/phase3-run.log. Hypothesis: after a restart with the car already plugged in and asleep, the car isn't "present" (no twcVin; atHome not set), so the policy limit is never desired.
- Live-fail diagnosis (live-fail-20261016.md): after a restart, a plugged-in, asleep car on a Gen2 is never present. _present falls back to api.atHome (default False); it is set only by plug or power edges; TeslaMate's free position is never turned into atHome. Still present at 1028283. A probe reproduces it. The existing tests set atHome=True by hand. cfd0086 raised the limit to 70 (via Fleet despite ble_only — a 1.3.4 behaviour, flag to the user) and BLE's rate command woke the car.
  - Ruling: new Task 12c "restart presence", before Task 13, done as a separate task with a review:
    (a) atHome is recomputed each policy pass from the latest free position (TeslaMate/telemetry); with no position, a held car counts as present (old behaviour) and the check falls through to the BLE claim;
    (b) departure by free position on the policy pass, not only on a power-drop edge;
    (c) a Gen2 with no VIN after a restart behaves as main (an anonymous plug session/fan-out), so BLE reaches and wakes the car;
    (d) the regression test from the write-up, with zero paid calls.
  - Wt-vm3's dirty TeslaAPI.py edits seen during the 13c review are reviewer mutations (temporary); verify the tree is clean before the next dispatch.
- Slim Task 13c review: spec PASS (deviation I1); quality NOT YET (0C/2I/5M); 31 of 34 mutations killed. Ruling: fix I1 (the 3-try budget covers every request sent; test expects 3 GETs and 1 refresh) and I2 (tests pin the per-car 429 backoff versus the module-wide one for the list), plus the Minors. Fix round 1.
- Slim Task 13c fix round 1: 2edf146 bcb4042, suite 1717 passed 1 xfailed, lib −57 total. Scoped re-review (Sonnet).
- Slim Task 13c: complete (commits 9ca6210..bcb4042; re-review APPROVED; lib −57). Carried to Task 13: collapse _request's resend/retried into one tries argument. Slim Task 12c (restart presence): dispatched, BASE bcb4042.
- Slim Task 12c: implementer DONE, commits 3ff40e2 14e0b53 717dbff 4fd7c9d, suite 1723 passed 1 xfailed, lib +45. At status 00 there is deliberately no fan-out (an empty TWC also reports 00). Review dispatched.
- Slim Task 12c review: spec pass with 2 deviations; quality pass with fixes (0C/2I/7M). Live scenario traced end to end: works (status 03 and 00).
  - Ruling: I1 — add the held-fallback test (no position, no BLE claim, a non-BLE provider) and mutation-check it.
  - Ruling: I2 — middle ground. At status 00, start an anonymous session only when a free source (TeslaMate/BLE) shows an at-home car plugged in.
  - Ruling: M2 — make the main restart test fail with the presence change reverted (independent of the sweep's side effect).
  - Ruling: M4 — keep main's telemetry-liveness gate on onDeparture; the restore is only delayed, never lost.
  - Ruling: position-age guard — restore on "away" only if the position is newer than our last limit write.
  - Ruling: fix the two test fakes, drop the getattr, share the sweep with onDeparture. Document no-home-set behaviour in Task 13 docs.
  - Fix round 1: resume the implementer.
- Slim Task 12c fix round 1: 6c75533, suite 1727 passed 1 xfailed, lib +60 total. Scoped re-review (Opus — this is the live-test candidate).
- Slim Task 12c: complete (commits 3ff40e2 14e0b53 717dbff 4fd7c9d 6c75533; re-review APPROVED; lib +60). The live scenario was traced and probed at status 03 and 00: BLE limit 70 and lift, zero HTTP. Carried to Task 13: N1 (comment plus a boundary test for the age guard's <=).
- Slim Task 13: dispatched, BASE 6c75533
- Slim Task 13: implementer DONE_WITH_CONCERNS, commits 0364f3a..b4f3b39 (9), suite 1729 passed 1 xfailed, lib −401, total 27,331 (581 over 26,750; removed ≥ added since 39d7cfb passes). Ruling: keep numCarsAtHome/minBatteryLevelAtHome (user policies reach them via modules.X.Y). Ruling: Storm Watch stays off _request (timeout and type-only logs added).
- Slim Task 13 review: spec PASS (deviation: validate_float deleted); quality CHANGES REQUIRED (1C/2I/5M); 18/18 mutations killed; line figures exact. Ruling: fix C1 (restore validate_float plus a unit pin, and grep every other deleted name against HTTPControl and tests/integration), I1 (use the review's changelog wording), I2 (docs and config comment), M1–M4. M5: no change.
- Slim Task 13 fix round 1: c726cad 64766fb e6e67d7, suite 1733 passed 1 xfailed, lib 27,354 (Task 13 −378). Scoped re-review (Sonnet).
- Slim Task 13: complete (commits 0364f3a..e6e67d7; re-review APPROVED; lib −378; total 27,354).
- Slim Task 14 (parity table only; live check deferred to the user): dispatched, BASE e6e67d7
- Slim Task 14 (offline): bef82f0 adds test_command_path_parity.py (30 tests, 31 rows); suite 1763 passed 1 xfailed; lib 0. Main was measured with a harness on origin/main 03d7932. 2 unruled differences:
  - Ruling (row 16, HA-only): keep Phase 3's HA commands. HA is a spec'd provider (rank 6, commandPolicy). Main never reached HA because it had no VehiclePriority entry, and the audit's row-61 premise was wrong. Flag to the user as a behaviour change on HA-only installs — cost if wrong: HA-billed commands where main sent none.
  - Ruling (row 26, restart): fix. A "Complete" reading satisfies the start only if it is newer than our last limit raise for that car; otherwise send the start over BLE (free), as main did. It relied on the car resuming by itself, which it did live, but that isn't guaranteed.
  - Correct the wording of Decision 8 / 12b M3: main re-sends a failing mode-2 rate about every 21 s indefinitely (172 paid/h); Phase 3 sends 2. Phase 3 is the bounded one.
  - Rows where Phase 3 pays more (13 +2, 17b +2, 23 +3 on 408s) are all ruled.
- Row-26 fix: fc6eba7 (also: the battery-at-limit hands-off check uses our own limit write until a newer reading arrives), suite 1764 passed 1 xfailed, lib +18. Final whole-branch review dispatched (Opus), range 6a6c14e..fc6eba7.
- Final review (final-review.md): ready for the live check — yes (box cycle traced as BLE-only, 0 HTTP). 0C/2I/13M; suite 1764 passed 1 xfailed.
  - Ruling: I1 fix — while a car's amps desire is unsettled, the TWC offers the target instead of its max (chargeRateControl 2, and mode 3 below the floor). Free; closes a sustained overshoot under the wiring rule.
  - Ruling: I2 — take the ~140 lines with no behaviour change now (dead EVSEInstance start/stop, dead/test-only methods, the duplicated anon-key test, duplicate constants/helpers, the "is car home" duplicates if behaviour-neutral). The HeldLimits one-shot migration shrink is deferred to Phase 3.5 alongside CarApiVehicle.
  - Ruling: fix the Minors that are cheap and safe; park the rest with notes.
  - One fix dispatch, then one scoped re-review (SDD final loop).
- Final fix: fc6eba7..db47522 (9 commits), suite 1764 passed 1 xfailed, lib 27,270 (−102; 520 over target). The I1 mode-2 change (the TWC drops to target until the car confirms) is visible behaviour — flag to the user (6 A firmware drop risk). Scoped re-review (Opus).
- Final fix re-review: APPROVED (db47522). Suite 1764 passed 1 xfailed, black clean, lib 27,270.
  - Parked for the user/live check (chargeRateControl 2 only): N1 (an unconfirmed rate skips the 6 A spike workaround), N2 (wiringMaxAmps below the spike setting), N3 (verify on the box that chargeCurrentRequest is not capped by the TWC offer — compare it with charger_pilot_current). Nit: the test_registry_callers regex.
- PHASE 3 COMPLETE pending: the user's live check (Task 14 procedure in slim-task-14-report.md) and the user's OK to push vehicle-model/phase3 (not pushed). Box on cfd0086; watchdog inert (rolled-back marker), cron entry still present.
- Pushed vehicle-model/phase3 (db47522) to origin, no PR (user OK 2026-10-16).
- User 2026-10-16: HA-only commands are fine (row 16 ruling confirmed). The mode-2 I1 change is fine: the 6 A firmware behaviour is known only from code comments and is likely long fixed. Go ahead with Phase 3.5.
