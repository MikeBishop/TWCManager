# SDD ledger — plan: .superpowers/plans/2026-10-13-vehicle-model-phase1-registry.md
Spec: .superpowers/specs/2026-10-13-vehicle-model-design.md
Worktree: scratchpad/wt-vm, branch vehicle-model/phase1 off origin/main eb457dc. Baseline 803 passed.
PY: /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python
Waiting: planner amendment (report-on-change freshness) before pre-flight.
Pre-flight: table in preflight.md (17 findings). Rulings (all sent to planner to amend plan text before Task 1):
Ruling: P1 tie — an observation at the same timestamp as our write is NOT fresher (strict >) — spec "older than our last write not trusted" errs safe — cost if wrong: one extra live read.
Ruling: P2 T5 stub gains sourceLiveAt — interface completeness — cost: none.
Ruling: P3 lock-count tests use a counting wrapper/MagicMock, not Mock(wraps=RLock()) — TypeError verified — cost: none.
Ruling: P4 getSetting stays unlocked (ruling 3); drop the test requiring a lock — cost: none.
Ruling: P5 loadSettings reads the file outside the lock, assigns under it — Global Constraint no lock across I/O — cost: none.
Ruling: P6 add HTTPControl :624, :1611-1612, MQTTControl :178 to locked writers — cost: none.
Ruling: P7 T9 keeps syncSource/syncTimestamp assignable (setters map to observations) until T11 removes the assigners — no broken window between tasks — cost: none.
Ruling: P8 liveness set in TeslaMateVehicle/FleetTelemetryMQTT mqttConnect overrides too (call super or set flag); TeslaMate liveness additionally requires its `teslamate/cars/N/healthy` topic true when published — user: fresh only if TeslaMate is healthy and still polling — cost: none.
Ruling: P9 upgrade seed: main never writes BLEPeeringStatus/bleProven, and scanForVehicles makes keys for every known VIN; seed every settings["Vehicles"] entry with a privKey as an UNPROVEN BLE claim that still lets BLE be tried (today's behaviour); a refused outcome drops it; proof moves it to Paired — preserves upgrade continuity — cost if wrong: history-only VINs get BLE attempts as they do today.
Ruling: P10 Add-by-VIN generates BLE keys for the VIN (same code path as scanForVehicles), so pairing works — spec bootstrap path — cost: none.
Ruling: P11 held-limit column looks up by VIN, then by the car's numeric API ID (main keys chargeLimits by ID) — cost: none.
Ruling: P12 update_location(0) means force fresh: maxAge 0 → 0, not 300 — preserves vehicleIsDefinitelyHome — cost: none.
Ruling: P13 during statusDeferral the cascade returns the stored value as success (update_charge returns True as today) — no behaviour change in Phase 1 — cost: none.
Ruling: P14 BLE read source drops None values — today's behaviour — cost: none.
Ruling: P15 RegistryField observes only keys present in the response, never defaults (10000/-1) or unchanged carry-overs — cost: none.
Ruling: P16 registry expiry not gated by fakeMaster (housekeeping) — cost: none.
Ruling: P17 add import pytest; render "last scan" age server-side from scannedAt; bleScan task key per VIN — cost: none.
Spec: Fleet per-operation prices added (vehicles/{vin} free, commands $0.001, vehicle_data $0.002, wake $0.02).
Task 1: BASE eb457dc
Task 1: implementer DONE e993e7f d8e14b7 ef9288a (815 pass)
Task 1: minor (deferred): cherry-picked test line >88 cols (verbatim)
Task 1: minor (deferred): startCarsCharging no longer replaces pending stop; no-arg cancelStopCarsCharging cancels all cars (upstream design, benign)
Task 1: complete (commits eb457dc..ef9288a, review clean)
Task 2: waiting on planner amendments
Planner amendments applied (P1-P17, prices). Task 2: BASE ef9288a
Task 2: implementer DONE 86d26a7 (820 pass)
Task 2: minor (deferred): respondToSlaves writes in stop/startCarsCharging also reached from policy thread (single-key, safe)
Task 2: minor (deferred -> carry to Task 13): add comment pinning json.dumps default args (C encoder) at TWCMaster saveSettings
Task 2: minor (deferred -> carry to Task 13): TeslaBLE loops over settings["Vehicles"] (:271,:628,:695) should iterate list(...)
Task 2: minor (deferred): addkWhDelivered read-modify-write unlocked; tests cover TWCMaster only; process_save_schedule long lock (no I/O)
Task 2: complete (commits ef9288a..86d26a7, review clean)
Task 3: BASE 86d26a7
Task 3: implementer DONE 7cf8eb5 (829 pass)
Ruling (Task 3 minors 1-2 -> fix): observe/noteWrite keep the newer `at`; clock read inside lock — later tasks feed one field from several threads/sources — cost if wrong: none.
Task 3: minor (deferred): read methods do not validate field names
Task 3: fix round 1/5 dispatched
Task 3: fix round 1/5 (2 addressed, 0 open; commits 7cf8eb5..1c30ee8)
Task 3: complete (commits 86d26a7..1c30ee8, review clean)
Task 4: BASE 1c30ee8
Task 4: implementer DONE 835a0b0 08bcbb4 (842 pass)
Ruling (Task 4 minors 1-5 -> fix): liveness-aware summary age (+changedAge), clamp lastSeen to clock, single claim evaluation, raising claim = False, ASCII-only VIN — visible on the Vehicles tab, cheap — cost: none.
Task 4: minor (deferred -> Task 6): Vehicle doesnt enforce key/vin agreement or uppercase; anon key prefix assumed
Task 4: fix round 1/5 dispatched
Task 4: fix round 1/5 (5 addressed, 0 open; commits 08bcbb4..6271e89)
Task 4: complete (commits 1c30ee8..6271e89, review clean)
Task 5: BASE 6271e89
Task 5: implementer DONE 6a76b2e (856 pass)
Ruling (Task 5 minors 1-7 -> fix): token-safe exception log (type name only), read honours trusted()/FEED_LAG, continue cascade if source lacks field, deterministic tests, docstrings — token rule is a hard constraint; feed-lag rule is spec — cost: none.
Task 5: fix round 1/5 dispatched
Task 5: fix round 1/5 (6 addressed, 0 open; commits 6a76b2e..7433281)
Task 5: note for final review: after our write, polled fields cascade until a newer observation lands (one fetch normally; repeated if fetch keeps failing) — check cost with paid sources in Task 10
Task 5: complete (commits 6271e89..7433281, review clean)
Task 6: BASE 7433281
Task 6: implementer DONE 8131814 6a3f370 (882 pass)
Task 6: carry -> Task 7: getOrCreate raises ValueError for empty/non-str/anon: VINs; serial-thread callers (recordVehicleVIN) must guard
Ruling (Task 6 minors 1-3,7a,7d -> fix): same ASCII key rule in getOrCreate/load, liveness value via _number, forgetAfterDays<=0 -> default, persisted-load log to DEBUG, toJSON-omits-anon test — cheap, avoids page errors — cost: none.
Ruling (Task 6 minor 4, commit trailers): keep the Sonnet 5.5 trailers (accurate attribution of the model that wrote them) and do not rewrite history to match global-constraints.md — cost if wrong: a cosmetic trailer mismatch, fixable by a squash before PR.
Task 6: carry -> Task 8: initialise lastVehicleExpiry to time.time() so startup expiry does not run before providers claim cars
Task 6: carry -> Tasks 9/11: callers holding Vehicle refs go stale after forget/expire; re-resolve via registry.get() or check a removed flag
Task 6: minor (deferred): lastSeen read at :121 without vehicle lock; version written never checked; garbage lastSeen loads as now
Task 6: fix round 1/5 dispatched
Task 6: fix round 1/5 (5 addressed, 0 open; commits 6a3f370..b7ced59)
Task 6: complete (commits 7433281..b7ced59, review clean)
Task 7: BASE b7ced59
Task 7: implementer DONE dca0d13 (901 pass)
Ruling (Task 7 items 1-2 -> fix): bounded confirmation retries while pending (per-TWC dedupe), and delayed-queue tie-breaker + call inside try — a lost confirmation leaves a car anonymous all session (no commands in later phases); queue tie would stall heartbeats 5 s — cost: none.
Task 7: minor (deferred): first-seen VIN entitlement/status run twice (idempotent); _plugSession reachable from HTTP thread (locked, benign twcVin race); anon vehicle leak on deleteSlaveTWC; first session recorded 5-30 s late until Task 8 persistence
Task 7: fix round 1/5 dispatched
Task 7: fix round 1/5 (2 addressed, 0 open; commits dca0d13..e162463)
Task 7: note for final review: backgroundTasksDelayed insort (serial) vs pop(0) (worker) unlocked — pre-existing race, more serial-thread use now
Task 7: complete (commits b7ced59..e162463, review clean)
Task 8: BASE e162463
Task 8: implementer DONE 055e286 (912 pass)
Task 8: minor (deferred): stale vehicleRegistry snapshot kept in settings between saves; round-trip test skips name/userAsserted/lastSeen; TWCManager wiring untested
Task 8: complete (commits e162463..055e286, review clean)
Task 9: BASE 055e286
Task 9: implementer DONE 985990d 290f7d1 (928 pass)
Ruling (Task 9 c1/c2): intermediate regression accepted within the phase (branch not deployed per task); Task 11 must make syncSource use liveness-aware age so a sleeping car on a live/healthy feed stays telemetry-sourced (user rule: old-but-current while feed healthy) and Task 10 removes wake-on-read — deploy only after Task 11 — cost if wrong: none (not deployed).
Task 9: carry -> Tasks 10/11: writes mis-stamped "TeslaAPI" (Telemetry setattr, rename, BLE update paths); "telemetry has resumed" INFO spam until T11
Task 9: carry -> Phase 6: Forget must also drop the CarApiVehicle, else next write re-creates
Task 9: carry -> Task 11 checklist: _telemetryPluggedIn (TeslaAPIController:87-94) also depends on syncSource; verify liveness keeps a sleeping plugged car telemetry-sourced while TeslaMate is quiet and healthy
Task 9: carry -> Task 10: observe gps_as_of only when truthy (null observed as 0 today)
Task 9: carry -> Task 15: WebIPC debug dump use carapi.registry.get(VIN).summary() (None-guarded); CHANGELOG note: debug API now takes VIN
Task 9: complete (commits 055e286..290f7d1, review clean)
Task 10: BASE 290f7d1
Task 10: implementer DONE 1e02481 (946 pass)
Ruling (Task 10 c2/c3, cost vs main): Task 11 liveness callables return the current clock time while the feed is healthy (connected and TeslaMate healthy), so age = 0 for a live report-on-change value and update_location(0)/maxAge 0 is satisfied by TeslaMate without a paid read — matches main (telemetry cars never fetched) — Task 11 must test: TeslaMate car, healthy feed, update_location(0) makes no API call — cost if wrong: paid vehicle_data per deferral window per TeslaMate car.
Task 10: note: pre-existing gap: vehicle_data without drive/charge state sets neither deferral nor error time (next read pays again)
Ruling (Task 10 Important 1): vehicleIsDefinitelyHome moves off the serial thread to a background task — global constraint; Task 13 would add a 5 s BLE block there — cost: up to one background-loop delay before the home check.
Task 10: carry -> Task 11: liveness only helps when the latest observation is from TeslaMate; a TeslaAPI-sourced value on a parked car may never be replaced (TeslaMate publishes on change). Consider keeping the live feed as voucher when its last-reported value equals the current one.
Task 10: minor (deferred): deferral with no stored value returns False (main True); lat set then missing longitude reports success with old lon; vehicleIsDefinitelyHome no longer forces atHome when asleep; all-None BLE reply falls to cloud (accepted)
Task 10: fix round 1/5 dispatched
Task 10: fix round 1/5 (2 addressed, 0 open; commits 1e02481..a2a3e24)
Task 10: complete (commits 290f7d1..a2a3e24, review clean)
Task 11: BASE a2a3e24
Task 11: implementer DONE ac202a1 (976 pass)
Ruling (Task 11 C1/I3): retained MQTT redelivery — unchanged value is not news (no observe, no lastSeen); changed value stamped min(now, lastWrite.at) when we wrote that field, seen=False — preserves the 09:17 rule and ageing on unhealthy feeds and lets expiry fire — cost if wrong: a genuinely new retained value waits up to FEED_LAG before being trusted over our write.
Ruling (Task 11 I2): telemetry re-resolves stale Vehicle refs after forget; carHealthy assumes healthy for unmapped cars per brief — cost: none.
Task 11: fix round 1/5 dispatched (C1, I2, I3 + minors 4,6,8,9)
Task 11: fix round 1/5 (C1, I2, minors addressed; I3 partial; new: NB1 stale-stamp latent, NB2 re-creation — commits ac202a1..0f63241)
Ruling (Task 11 NB1): clamp differing retained value to write.at only when the feed has not reported since our write — reviewer verified on scratch copy — cost: none.
Ruling (Task 11 NB2): retained MQTT messages never create or revive a vehicle; only live messages create (a real sighting) — keeps Forget/expiry effective — cost if wrong: on a first boot with no saved registry, a TeslaMate-only car attaches on its first live message instead of immediately.
Task 11: minor (deferred): refreshIdentities only reloads while carVINs empty and some name unmapped; empty cars table queried every retry
Task 11: fix round 2/5 dispatched
Task 11: fix round 2/5 (NB1, NB2, I3, OOS1 addressed; commits 0f63241..1dda627)
Ruling (Task 11 round-2 minors -> fix in round 3): bound parked store per (car,event); warn once then debug; forgotten car retry uses loadList=False; Fleet derives no state from retained; Fleet attaches by topic VIN on live messages — cheap, Fleet attach gap breaks non-retaining brokers — cost: none.
Task 11: fix round 3/5 dispatched
Task 11: fix round 3/5 (4 addressed, 0 open Critical/Important; commits 1dda627..0fe3413)
Task 11: minor (deferred, final-review fix wave): record orphanedIds in _dropIfOrphan (retained display_name-first path); never let a retained parked entry replace a live one; Fleet multi-topic state (older DISCONNECTED overriding newer driving); 17-char VIN shape check in FleetTelemetryMQTT.vinFor
Task 11: complete (commits a2a3e24..0fe3413, review clean)
Task 12: BASE 0fe3413
Task 12: implementer DONE b486b44 (1003 pass)
Ruling (Task 12 Important 1, plan-mandated): HA read source returns fields actually observed or None, reports failure when HA unreachable, advertises only its six fields, ordered after TeslaAPI (spec: HA last), fails fast — brief said return {} which stops cascades on stale data — cost: none.
Task 12: minor (deferred): HA claim static (has_charge_switch always true); batching at end of refresh
Task 12: fix round 1/5 dispatched
Ruling (Task 12 fix deviation): fetch returns the dict of fresh fields even without the requested one — cascade continues past it (Task 5 rule) and keeps the fresh values — accepted — cost: none.
Task 12: fix round 1/5 (4 addressed, 0 open; commits b486b44..a0e24f4)
Task 12: complete (commits 0fe3413..a0e24f4, review clean)
Task 13: BASE a0e24f4
Task 13: implementer DONE_WITH_CONCERNS c938b36 (1024 pass)
Ruling (Task 13 concerns, before review): pairing = unproven claim; refusal inside a pairing window keeps "Pairing"; failed re-pair of a Paired car (non-refusal) keeps Paired with a transient last-attempt message; only well-formed VINs get settings records/keys; ErrKeyNotPaired not retried; lock tests use a real RLock — user-visible status must not flip to "Key refused" before the key-card tap — cost if wrong: a genuinely revoked key shows "Pairing" for up to the window.
Task 13: concerns fixed d62e3b1 (1033 pass)
Ruling (Task 13 review minors 1,2,3,5,6 -> fix): unproven BLE claims do not block expiry; seed all keyed entries only on the upgrade boot (no saved registry), afterwards only registry-held VINs; well-formed VIN filter; upper-case VINs at TeslaBLE boundaries; pairing_failed keeps an unproven claim — user wants phantoms to age out — cost if wrong: a never-proven car that only BLE knows ages out after 30 days unseen and must be re-added.
Task 13: minor (deferred): refused car never trips circuit breaker (one tesla-control run per cycle)
Task 13: fix round 1/5 dispatched
Task 13: fix round 1/5 (5 addressed, 0 open; commits d62e3b1..b113e90)
Task 13: minor (deferred): expired never-proven car reappearing at a TWC regains unproven BLE claim only on next boot (commands still reach it; self-heals)
Task 13: complete (commits a0e24f4..b113e90, review clean)
Task 14: BASE b113e90
Task 14: implementer DONE_WITH_CONCERNS 448b92c (1056 pass)
Ruling (Task 14 c1-c4): charge-rate stamp never creates a vehicle (registry.get, skip on None); stamping on already_set accepted; HA VIN upper-cased; all-vehicles BLE per-success stamps accepted — write paths must not revive forgotten cars — cost: none.
Task 14: concerns fixed cfb39fd (1057 pass)
Task 14: minor (deferred, final-review wave): HomeAssistant.setChargeRate does not stamp availableCurrent
Task 14: complete (commits b113e90..cfb39fd, review clean)
Task 15: BASE cfb39fd
Task 15: implementer DONE f1d11a2 (1064 pass)
Ruling (Task 15 minors 0,1,4,5 -> fix): home-location guard + hide button, debug dropdown only TeslaAPI-attached cars, grep test cwd-independent, dead scaffolding — cheap — cost: none.
Task 15: minor (deferred, final review): debug dump lost CarApiVehicle state (summary only); pre-existing unchecked TeslaAPI uses in WebIPCControl dumpState/:134 and Policy.py:316
Task 15: fix round 1/5 dispatched
Task 15: fix round 1/5 (4 addressed, 0 open; commits f1d11a2..d29e01a)
Task 15: minor (deferred): process_home_location del on unset raises KeyError (pre-existing)
Task 15: complete (commits cfb39fd..d29e01a, review clean)
Task 16: BASE d29e01a
Task 16: implementer DONE 8e6c59a (1072 pass)
Ruling (Task 16 c1): Forget action deferred to Phase 6 as the brief says (my dispatch was wrong) — a Forget that does not also drop the CarApiVehicle would be undone by the next write — cost: no Forget button until Phase 6.
Ruling (Task 16 c2): case-insensitive existence check in addVehicleByVIN accepted — matches _settingsKey — cost: none.
Ruling (Task 16 minors): fix numeric VIN crash + tests; adding a known VIN marks it user-asserted (accepted) — cost: none.
Task 16: fix round 1/5 dispatched
Task 16: fix round 1/5 (2 addressed, 0 open; commits 8e6c59a..2b91330)
Task 16: minor (deferred, final wave): read the raw vin field in /vehicle/add (getFieldValue int-coerces and drops leading zeros)
Task 16: complete (commits d29e01a..2b91330, review clean)
Task 17: BASE 2b91330
Task 17: implementer DONE b0d3d00 aba5fff (1099 pass); live check partial (implementer ran bluetoothctl scans on the box; no errors)
Note: box now runs cfd0086 (port-fleet-wake-poll-1.3.4, another session) — do not deploy phase 1 without coordinating
Ruling (Task 17 I1/I2 + minors 4,5,6,9): failed/timed-out scan = Range unknown (no bleReach observation); in-progress set so Scanning shows, 10 s debounce; MAC fallback only [NEW]/[CHG] RSSI numeric lines; label wording; re-queue leftover requests; no live-box testing this round (box in use by 1.3.4 testing) — cost: none.
Task 17: minor (deferred): Pair still synchronous on HTTP thread under _bleLock up to 30 s; scans block background thread ~8 s per VIN
Task 17: fix round 1/5 dispatched
Host restart wiped /tmp scratch: wt-vm re-added at aba5fff, venv rebuilt (+requests_mock, pytest-mock) at scratchpad/venv; suite 1099 pass. Task 17 fix round 1 lost (nothing committed) — re-dispatching fresh.
Peer report: previous Task 17 fix-round pytest run hit 11 GB RSS and crashed WSL (14:27). Rule: all pytest runs under MemoryMax/prlimit + timeout; re-queue bounded to once per drain; mocks finite. Sent to fix-round implementer.
Task 17: fix round 1 DONE 2d872e4 (1123 pass). OOM root cause: committed runPendingScans `while True` drain loops forever when a VIN is re-requested during its scan; now bounded (3 passes) + debounce; requeue moved after doneBackgroundTask (at most one follow-up).
Task 17: carry -> live check: healthy bluetoothctl scan exit code unknown (nonzero would make misses read Range unknown)
Task 17: fix round 1/5 (6 addressed, 0 open; commits aba5fff..2d872e4; re-review task-17-rereview-1.md)
Task 17: minor (deferred, final wave): _bluezAddresses nonzero exit with output gives empty set (Not in range, not unknown); TWCManager.py requeue glue untested
Task 17: complete (commits 2b91330..2d872e4, review clean)
Note: re-reviewer's full-suite run hit its 300 s timeout (no output) — verifying suite timing before final review
Final review dispatched (fable): review-final-eb457dc..2d872e4.diff -> final-review.md
Live check (box, 2026-10-14): bluetoothctl --timeout 8 scan on exits 0 on a healthy run; devices exits 0; output carries ANSI color even to a file (stripped by _stripAnsi). Carry closed: a miss reads Not in range. Page round trip still unchecked (box runs cfd0086).
Suite at 2d872e4 (tests minus tests/API, capped): 1132 passed, 2 skipped, 1 xfailed; 210 errors all tests/integration setup timeouts needing a server on <teslamate-host>:8088 (environmental). Full tests/ run exceeds 300 s because of these.
Live check (box, phase1 2d872e4 deployed 15:06; rollback cfd0086 + ~/twcmanager-settings.json.bak-20261014-phase1, must be back before midnight): boot clean, registry added car via TeslaBLE; page scan round trip OK: button Scanning… disabled during, 'in range' logged, Last scan shown, status Paired. Task 17 Step 6 done.
Final review: WITH FIXES — C1, I1-I5, M1-M10 (final-review.md)
Ruling (final wave): fix C1 (healthy report-on-change feed vouches for any field it has reported, regardless of value equality), I1 (Forget only for user-asserted vehicles with no provider attachment; full Forget stays Phase 6), I2 (all-vehicle BLE loops skip VINs whose TeslaBLE claim was dropped/refused; unproven claims still included so upgrade users keep working), I3+I4 (isWellFormedVIN at vinFor and at registry getOrCreate), M1 comment, M2 lock, M3 None on nonzero exit, M4 HA stamp, M5 pop, M6 endPlugSession, M7 no record on key-prep failure, M9 reject all-zero VIN. I5: no code; carried to Phase 2/5 plans ("plug session" == isCharging today). M8, M10: no. — cost if wrong: small, each has a test.
Final fix wave dispatched (BASE 2d872e4)
Final fix wave DONE_WITH_CONCERNS: a888760..85641a1 (11 commits), 1153 pass. Concerns (C1 changed 2 tests asserting old rule; I2 keyed on stored status; M7 broader) accepted pending re-review.
15:41 box redeployed 8e07669 (detached; branch vehicle-model/phase1-b on box). Boot OK; one 'Main loop stalled 2.2s' at boot (none in prior 2 h on cfd0086) — watch. BLE set-limit first attempt times out, retry OK (same as 2d872e4).
Final re-review 1: all in-scope ADDRESSED, no new Critical/Important (final-rereview-1.md). Residual minors parked: Forget offered on a user-asserted car a provider later saw (harmless, hint wording); forgetVehicle paired re-check race (microseconds); all-zero placeholder with key still in all-vehicle targets (as main). Branch complete at 8e07669.
User: leave branch as-is (no merge/PR yet) at 8e07669. 5 PM trip cancelled; no cycle needed. Soak on box until 21:37 then rollback to cfd0086 (session cron).
Departure 18:41 on 8e07669: TeslaMate saw unplug/driving; registry fresh via TeslaMate; zero TeslaAPI calls since 18:43 (C1 cost OK); no main-loop stalls since boot; BLE sent nothing to absent car. Limit stayed 50% (no restore): main behaviour — checkDeparture goes via VehiclePriority to TeslaBLE first, which ignores it; unchanged by phase 1, fixed by Phase 5 presence port.
19:15 return: TWC VIN read, registry fresh, no anon row; BLE dedupe skipped 50% (main behaviour, in-memory flag). 19:18 restart -> 50% set first try; no stall.
Soak 15:41-21:37 (8e07669): no Tesla API calls of any kind (only module registration lines), no WARNING+/Traceback beyond boot module notices, no main-loop stalls in retained journal (journal retains ~20 min at DEBUG; capture file lacks stall lines, so 15:41-21:25 stall count unverified beyond the one at boot). 21:37 rolled back to cfd0086, service active, current settings.json kept (no load errors), other session's debug capture still running.
User: push, don't merge. Pushed to origin (ngardiner/TWCManager): vehicle-model/phase1 8e07669, vehicle-model/phase2 6a6c14e. No PRs opened.
