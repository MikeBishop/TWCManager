# SDD ledger — plan: .superpowers/plans/2026-10-09-vehicle-presence.md

Spec: .superpowers/specs/2026-10-09-vehicle-presence-design.md (uncommitted). Branch fix/vehicle-presence on origin/ble-command-worker 3574692. Baseline 500.

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1 → T3, T7, T8 | queue (cmd,vin) keying, cancel(), dispatch vin/remoteOnly; TWCMaster cancelStop(vin) | consistent |
| T2 → T3, T7 | VIN-keyed normal limits; migrate in TeslaAPI.addVehicle | consistent |
| T3 → T6, T7 | VehiclePriority.applyChargeLimit(remoteOnly)/resetChargeLimitState; update_charge(allowBle) | consistent |
| T4 → T5 | T4 calls observeContact before T5 defines it; guarded by getattr(master,"vehiclePresence",None) | ordering inverted but guarded — acceptable |
| T5 ← T6, T7 | T6/T7 replace T5's default sources/handlers | consistent |
| T5/T7 → T8 | nominate/observeLocation/start/stop wiring | consistent |
| T9 | controller live | see ruling |

Ruling: implementer commit trailers name the actual implementing model, not the plan's "Fable 5.1" — accurate attribution — cost: cosmetic.
Ruling: controller runs T9 (deploy + live checks) — ops — cost: unreviewed ops.
Ruling: plan writer's spec corrections accepted (no Policy.stop() on this base; migration in addVehicle; observeContact probe flag; ""→None VIN; restore read path off BLE) — consistent with spec goals — cost: rework if user disagrees.

## Progress

## Coordination: peer session "Tesla API call patterns in twcmanager"
Peer branch fix/teslamate-vehicle-mapping b3bff0e (off main 0b7d143, unpushed; also on box atop dace4e9). Adds TeslaAPI.loadVehicleList() (extracted from car_api_available, idempotent, RLock vehicleListLock, False on failure) + Telemetry name memory and 5-min retry timer. addVehicle untouched — ours.
Ruling: no plan change for Tasks 2/6 — migration call in addVehicle runs for vehicles loaded via either path; vehicleOnlineStates is a separate GET. Do not restructure the vehicle-list GET; if touched, keep loadVehicleList() as single entry point. Peer rebases on us. Possible textual overlap in Telemetry.py (Task 8 applyDataToVehicle) — peer told. Bonus: their fix lets BLE-only installs with TeslaMate get CarApiVehicle objects, which the telemetry presence source needs.
Peer confirmed: their applyDataToVehicle edit is only in vehicleNameTopic branch; our _reportLocation in elif-events/syncSource block as planned. Early events parked in unknownVehicles and replayed ~1s later after mapping — presence sees them late, not never; acceptable (presence is eventual).

Task 1: implemented bbf0af2 (sonnet a000dd8c43d8ab2df). Review: spec compliant, quality approved w/ 1 Important.
Ruling: fix Important (vin=None kwarg breaks real modules until Task 3) by passing vin only when non-None — keeps every commit deployable/bisectable — cost if wrong: trivial.
Ruling: park Minor 1 (two lock acquisitions in stopCarsCharging; harmless), Minor 2 (test line length; black excludes tests), Minor 3 (start doesn't cancel pending stops under other key; queue FIFO executes stop then start, brief-specified).
Task 1 fix round 1: dispatched to a000dd8c43d8ab2df.
Task 1 fix round 1: b7e2739 — controller verified diff (vin conditional, new legacy-signature test, 512 pass). Re-review: addressed.
Task 1: complete (bbf0af2, b7e2739)
Task 2: BASE b7e2739
Task 2: implemented 9733ec7 (sonnet a05f97145ef49fbf0), 517 pass (counts +1 vs plan from T1 fix test).
Task 2 review: spec compliant, approved; upgrade migration verified safe. Ruling: park 3 minors (brittle source-inspection test, unused imports in test_teslaapi_presence.py, ID entry dropped when VIN entry exists — by design) for final review sweep.
Task 2: complete (9733ec7)
Task 3: BASE 9733ec7
Task 3: implemented 14ffaf2 (sonnet a91e52fef5203114f), 540 pass. DONE_WITH_CONCERNS.
Ruling: concern 1 (checkArrival/checkDeparture tasks still queued by TWCSlave/HTTPControl, ignored until Task 8) accepted — plan sequencing; no crash, arrival re-apply inert between T3 and T8; don't deploy mid-branch.
Ruling: concern 2 (deleted comment re master.lastChargeLimitApplied 0→-1) — covered by Task 7 arrivalHandler (plan line ~3389 'master.lastChargeLimitApplied or -1'); no action.
Task 3 review (opus aa477a84cf46b4dbf): spec compliant; Needs fixes. Important 1 (plan-mandated): vin=None dedupe lost (unsaved at-home car re-read every minute; away car w/ saved -1 un-latched).
Ruling: fix Important 1 both parts (unsaved treated as -1; vin=None skips away cars before update_charge) — cost if wrong: away cars no longer opportunistically refresh atHome via policy reads; presence owns arrival now.
Ruling: fix Minor 1 (HA returns "success" when vin given and nothing processed — blocks fallback for remoteOnly restore) → return "error". Keep at_home check (spec known limitation).
Ruling: fix cross-task note now: car_api_available(vin=) scopes wake loop to target VIN — prevents waking another car; minimal, avoids peer's loadVehicleList block.
Ruling: park Minor 2 (car_api_charge re-apply throttled 60s; limit was just applied), Minor 3 (stopAskingToStartCharging cleared only on increase; Policy/TWCSlave clear elsewhere — final review to judge), Minor 4 (test scaffolding; likely used by Task 4).
Note for Task 7/9: per-VIN API apply still won't wake target if TeslaAPI cached atHome False (stale); BLE path covers BLE installs; check in live test.
Task 3 fix round 1: dispatched to a91e52fef5203114f.
Task 3 fix round 1: 9d513dd (545 pass). Re-review (sonnet ac51351cc48f5db0d): all 3 addressed. Ruling: park new Minor (test_unsaved_at_home_car_is_read_once asserts <=1, weak) and known stale-atHome wake gap (noted for T9).
Task 3: complete (14ffaf2, 9d513dd)
Task 4: BASE 9d513dd
Task 4: implemented 0059579 (sonnet a06ab7653531b698f), 558 pass. DONE_WITH_CONCERNS.
Ruling: concern 1 (any None result reports unreachable, probe=False) harmless — Task 5 observeContact treats non-probe failures as no evidence. Concern 2 (probe early returns skip observeContact) fine — probe pass reads return value. Concern 3 (not red-first) accepted; tests verbatim from brief.
Task 4 review (sonnet a9def8718628f6c32): spec compliant, approved; 6 minors. Ruling: observeContact under _bleLock is safe given Task 5 brief code: presence._lock never held across _probe/handlers; lock order _bleLock→presence._lock only. Carry invariant into Task 5 dispatch. Park other minors (no-evidence early returns, parse-failure reported unreachable non-probe, missing lock/exception-path tests).
Task 4: complete (0059579)
Task 5: BASE 0059579
Task 5: implemented 0c54080 (sonnet a147e38dd188b74a9), 588 pass, presence tests 8/8 loops.
Ruling: accept deviation — knownVehicles() (TeslaAPI call) moved out of presence lock; None-nomination expansion now after explicit VINs. Upholds lock invariant; no later brief references _collectDue. Accept skipped red step (tests verbatim).
Task 5 review (opus a59496582f0492ae0): spec compliant, approved; lock invariant holds. 6 minors.
Ruling: fix minors 1 (knownVehicles raise loses pass), 2 (home location fix resets failed-probe count — presence proven), 4 (non-dict source result aborts pass). Park 3 (logging under lock), 5 (no lock test for sources), 6 (start after stop mid-pass no-op; only shutdown uses stop).
Note for Task 6: failed BLE probes count toward away only when run by presence pass — ensure bleSource goes through presence probe path.
Task 5 fix round 1: dispatched to a147e38dd188b74a9.
Task 5 fix round 1: 901e3fa (596 pass). Controller verified lib diff: all 3 addressed (source home answer already resets via _applyProbe). Re-review: addressed.
Task 5: complete (0c54080, 901e3fa)
Task 6: BASE 901e3fa
Task 6: implemented 83e92da (sonnet a8f6a17e8dce234f0), 619 pass. Telemetry-branch location push deferred to Task 8 Telemetry._reportLocation per plan.
Task 6 review (sonnet a74df1b88a2752aa7): spec compliant; Needs fixes. Important: no timeout in vehicleOnlineStates (plan-mandated); bleSource can't tell non-enrolled VIN from out-of-range → spurious AWAY for API-only car in mixed install.
Ruling: fix both Importants + Minor stale-GPS/home-unset (atHome None when home unset — avoid spurious departure). Park: statusDeferral=0 on fetch failure, second GET in ready()/is_awake, telemetry seeding home via is_location_home, (timeout/header test folded into fix 1).
Task 6 fix round 1: dispatched to a8f6a17e8dce234f0.
Task 6 fix round 1: 31374a5 (622 pass). Controller check: fixes 1,3 good; fix 2 ineffective — settings['Vehicles'] holds every TWC-seen VIN (recordVehicleVIN), no BLE peering marker exists.
Ruling: TeslaBLE persists settings['Vehicles'][vin]['bleProven']=True on any successful BLE contact; bleSource probes any known VIN (success = arrival proof) but failure counts toward away only when bleProven, else None — cost if wrong: a BLE car never yet reached by BLE after upgrade can't be declared away by BLE-only until first contact.
Task 6 fix round 2: dispatched to a8f6a17e8dce234f0.
Task 6 fix round 2: ff47b7e (628 pass). Controller verified diff: bleProven set in _reportContact on reachable; bleSource gates failure on bleProven. Re-review: addressed.
Task 6: complete (83e92da, 31374a5, ff47b7e)
Task 7: BASE ff47b7e
Ruling (Task 7 dispatch): hasRemoteChannel also requires a Fleet API bearer token — BLE-only installs often load TeslaAPI without token; else departure restore queued to a channel that can't deliver — cost if wrong: none (restore would fail anyway).
Task 7: dispatched (sonnet a67903cbe41909cb4).
Task 7: implemented 3d79941 (sonnet a67903cbe41909cb4), 651 pass.
Task 7 review (sonnet ae7c7a5ce9ce600f1): spec compliant, approved; risks a-d pass. Park 3 minors (no real-queue depart-then-return test — candidate for final review; red run not observed; token truthiness only).
Task 7: complete (3d79941)
Task 8: BASE 3d79941
Ruling (Task 8 dispatch): Telemetry._reportLocation skips when home unset or sync coords 10000 — consistent with Task 6 fix 3.
Task 8: dispatched (sonnet a638e880313674c60).
Task 8: implemented 32bd76b (sonnet a638e880313674c60), 669 pass incl SIGTERM e2e. presence.stop() first in shutdown (no Policy.stop on this branch — merge with #670 must order Policy.stop then presence.stop or either first).
Task 8 review (sonnet abba216c450bcdb9b): spec compliant, approved; risks a-e pass. Minors: nominate doesn't dedupe delay timestamps (state-00 flap adds entries; bounded by expiry) — forward to final review; identical HTTP branches; source-grep lifecycle tests. Parked.
Task 8: complete (32bd76b)
Final review: range 3574692..32bd76b

## Final review (fable a8e7b1ab3a0ead779): ready with fixes. See final-review.md.
## Live (deploy/presence a85e40a = branch + box cbf490b merge, on box 17:03:29; rollback cbf490b)
- 17:04:16 unknown->home (TeslaMate last fix; BLE probe timed out) -> arrival apply 50 queued.
- 17:05:52 home->away via TeslaMate -> departure restore queued (remote channel: token set). Saved normal [50,50] so restore is a no-op either way; TeslaAPI logs nothing at INFO.
- Observed: policy re-queues apply 50 every 30 s; TeslaBLE retries + wake attempts for away car each tick (~30 s BLE busy). Pre-existing (BLE has no atHome concept) but presence now knows AWAY.
Ruling: final fix dispatch covers Important 1 (atHome stale for telemetry vehicles; set in Telemetry._reportLocation + TeslaAPI vin=None gate honours presence AWAY), NEW: TeslaBLE vin=None skips VINs presence says AWAY, Important 2 (bound observations when thread not started), Important 3 (real-queue HOME->AWAY->HOME test), Minor 2 (lastChargeLimitApplied 0 -> skip arrival apply), Minor 6 (resetChargeLimitState clears stopAskingToStartCharging), plus INFO log for remote restore outcome. Other minors parked.
Ruling (user steer): presence is sole authority. CarApiVehicle.atHome becomes property: getter = presence state when home/away, else raw location value; setter stores raw. apiSource/_reportLocation read raw (avoid feedback loop). Replaces fix item 1(a)(b). Sent to a34db1414429ccfe4 mid-run.
Ruling (user steer): vehicleIsDefinitelyHome subsumed — TWC VIN = home proof to presence (no I/O in recordVehicleVIN, which runs on serial main loop); geofence repair moves to presence thread via injected TeslaAPI reconcile hook; hook no longer sets atHome. Fix item 8 sent to a34db1414429ccfe4.
Final fix pass: 32bd76b..16a4bfd (opus a34db1414429ccfe4) items 1-8; 707 pass. Controller commit (amended) re-evaluates atHome after home move (agent's open decision; yes — avoids extra fetch). Accepted concerns: reconcile may BLE-wake a plugged-in car (TWC-proof path only, plug-in already wakes), no hand-set adoption on TWC-proof arrival (same as BLE contact), no geofence repair in non-master modes (matches policy gating).
Final re-review (opus a1c6ba12e8edb8488): items 1-8 addressed; new minors N1 (away fix behind proof in same batch) and N2 (earliest-64 cap crowds out late checks) fixed by controller in 244b02c, 709 pass, both new tests fail on prior code. Parked: other cars' raw atHome vs old home after home move; stale-GPS reconcile leaves raw False (pre-existing form).
Final review: complete.
Post-review addition (user-approved): hand-set limit fix — (1) TeslaBLE reads current limit before set (mirrors TeslaAPI adopt/restore rules; fixes bogus outside=target normal, box shows [50,50]); (2) pushed arrivals fill limit from live telemetry chargeLimit. Dispatched opus aa4924de0b5ef0733. Box's [50,50] entry needs one manual clear after deploy.
Hand-set fix: cfc59d6 (BLE read-before-write), 4efa266 (pushed arrivals carry telemetry limit); 733 pass. Ruling: telemetry fill arrivals only (stale telemetry on departure would skip restore and corrupt normal; TeslaAPI restore checks car itself). User: plug-in resets BLE breaker → also any BLE contact success resets it. Investigate ~3 BLE applies per policy tick. Follow-up sent to aa4924de0b5ef0733.
Follow-ups: b6722c2 (arrival-only telemetry fill), 4cb6a43 (breaker closes on BLE success / TWC proof), efb8a14 (skip read while breaker open — fixes regression from cfc59d6); 748 pass. 3 BLE applies/tick = VehiclePriority retries=priority//10 (pre-existing) — parked as separate follow-up.
User design: BLE-confirmed arrival — ARRIVING state for bleProven VINs on location-home; probe each 60 s; HOME on first reachable probe or after 600 s; away cancels silently. Dispatched to aa4924de0b5ef0733.
User-approved (after ARRIVING lands): DEPARTING state on unplug.
- Unplug = TWC state 00 sustained 60 s (Gen2 flicker debounce); VIN from currentVIN→lastVIN.
- Departing (bleProven VINs): if no remote channel, BLE restore of outside immediately (TeslaBLE read-before-write keeps hand-set); with remote channel, restore waits for real departure (unchanged). Probe 60 s; 2 failures → AWAY (no second restore). Policy-wide applies skip departing cars. Probe cap 30 min then stop probing, stay departing.
- Replug: TWC state leaves 00 (03/01/08) sustained, or VIN proof → HOME + arrival (re-apply policy).
- VIN-less TWCs (DIP 2 down / non-Tesla / no CAN): track departing sets per TWC. Unplug at TWC X w/o VIN → candidates = HOME bleProven VINs not attributed to another TWC's currentVIN. Early BLE restore only if exactly one candidate; several → probe only (away by failures; remote restore if channel). Replug at TWC X → its departing set → HOME + arrival. Ensures exit signal exists without VIN (else car excluded from policy forever).
ARRIVING: 15f9d21 (770 pass). Ruling: arriving probes BLE then full source order (location away cancels) — accepted; ARRIVING reported as UNKNOWN. Ruling: timeout-HOME VINs exempt from BLE-only away rule until a BLE contact succeeds (prevents HOME/AWAY flap). DEPARTING dispatched to aa4924de0b5ef0733 incl. VIN-less per-TWC tracking; BLE contact must NOT exit DEPARTING.
User: early BLE restore on DEPARTING even with Fleet API (commands costlier than queries). Saved-limit state is the record: successful BLE restore removes saved normal → departure handler skips remote restore; failed → remote fallback. Sent to aa4924de0b5ef0733.
DEPARTING: ab545e7, a00451e, 516916a (814 pass). Rulings: per-plug plugVIN (NON_TESLA sentinel on empty VIN) replaces lastVIN for departing attribution; early restore localOnly (VehiclePriority skips non-BLE); probe cap → slow probe every 600 s instead of stop. Sent to aa4924de0b5ef0733. Pending user: drop handler adoption + telemetry fill when extracting shared limit-decision function.
Departing fixes: 5fa7b69 (plugVIN), b502780 (localOnly), e250fee (slow probe); 825 pass. Ruling: NON_TESLA trusted only on TWC that reported a real VIN this run; modules accept localOnly (TeslaAPI localOnly → no-op error). Sent.
7295a10: NON_TESLA trust + localOnly everywhere; 830 pass. Waiting on user for extraction scope (drop handler adoption + telemetry fill?).
User: drop handler adoption + telemetry fill; prefer fresh TeslaMate value over live read (TeslaAPI update_charge already does when syncSource is telemetry; TeslaBLE to match). Extraction dispatched to fresh opus.
Extraction: f674d37 389815e ca9e14d eec589b 87a4dc9 (871 pass). Accepted: adopt-on-apply in shared rules (BLE's), sendWhenUnknown param, restore saves (normal,-1) for BLE too, log wording. Parked: adoption saved only after successful send. Ruling: restores trust telemetry only when it equals lastApplied; else live read (BLE first; API only when needed). Sent to adeff421e3f722aab.
944f6ec restore live-read fix (888 pass). Accepted: remote-only restore for asleep car fails its read and sends nothing (dropped, not replayed). Review 2 (fable) range 244b02c..944f6ec.
Review 2 (fable af8523d93759c89c8): ready with fixes. Rulings: fix I1 (drop departure-handler adoption), I2 (plug evidence on TWC w/o departing set → home iff exactly one DEPARTING VIN overall), I3 (exclude other slaves' plugVIN), minors 1,2,5, and 3 if clean. Accept minors 4,6,7,8. Dispatched fresh opus.
User noted scope grew far beyond bug report; proposed split into 4 stacked PRs after a few days live: (1) queue keying+cancel, (2) charge-limit correctness, (3) presence tracker, (4) arriving/departing.
Box: event logger installed (~/twc-events/events.log). Box has not rebooted since 2026-10-07 17:18; journal start 10:07 today was rotation, not reboot.
Review 2 fixes: bac6dbd 5d0f608 e198ace 33d92ff 2622e74 ef2305d (905 pass). Accepted narrowing (VIN-reading TWC plug evidence ignored for no-departing-set case), concerns 4-7 parked. Follow-up: verify same-TWC 03 replug w/o VIN/current exits DEPARTING; power-start evidence only within 300 s of 00→plugged.
Follow-ups: 927bc67 (same-TWC replug test passes as-is), f27c287 (power-start window 300 s); 908 pass. Deploying.
PR668: pushed 2c38506 (RS485 NameError swallowed SIGTERM; shutdown flag backstop); merged into fix/vehicle-presence. Live: spurious unplug after restart (Gen2 TWC reports steady 00 for plugged idle car after re-link; TeslaMate plugged_in=true). Then user set outside 100 and started charge: VIN proof → departing→home, arrival applied 50, saved [100,50] — works. Seen: 3 main-loop stalls in distributeEVSEPower→evse.setTargetPower at charge start (pre-existing, not presence).
INCIDENT 19:29: TeslaAPIController (EVSE for every atHome vehicle) + atHome-via-presence → 3 Fleet set_charging_amps POSTs (proxy log 19:29:16/:20/:22) on main loop while TWC EVSE had no VIN. Box rolled back to cbf490b 19:31. Also 17:46:40 Fleet set_charge_limit = VehiclePriority prefer_ble fallback after BLE breaker open (pre-existing design). User-approved fix: TeslaAPIController skips vehicles a TWC serves/may serve (plugVIN/currentVIN; any car while a VIN-less TWC draws power) + setChargeRate dedupe per car. Queued after unplug-fix agent.
Unplug fix: 6437f29 (plugged run ≥60 s + 300 s link grace, noteLinkReady on re-link), f27532d (telemetry plug state in presence), a70fe5e (TeslaMate plugged_in); 937 pass. Concerns accepted. EVSE fix dispatched (opus). Asked user re upstream issue for EVSE exposure on main.
Filed ngardiner/TWCManager#672 (EVSE Fleet set_charging_amps exposure); PR held until open PRs settle (user worried about swamping maintainer). Open from this effort: PRs #668 #669 #670 (#671 peer's), issues #666 #667 #672.
EVSE: b48f3af 6aca1eb 8e04ca8 (955 pass). Review 3 range a78fe3d..8e04ca8.
Review 3 (opus a4eb67e083507323b): ready with fixes. Rulings: fix I1 (blind on no-VIN TWC plugged/≥1A; exclude telemetry-pluggedIn cars while any TWC lacks VIN), I2 (EVSE setChargeRate via vehicle worker, timeout 10 s), M1-M4. Park M5 (mostly covered by I1), M6, M7 (note in PR: chargeRateControl==2 MergedEVSE routing now dead for TWC cars).
Review 3 re-review (sonnet): all addressed; 1641265 docstring. Deploying.
2026-10-10 Backports prepared; see backports-report.md. Release branches: 62 pre-existing unit failures, no test CI.
#671-1.3.3 port review (sonnet): ok; low-severity test gaps only (timer path, timeout assert) — same as upstream #671 tests.
2026-10-10 PRs opened: #673 (RS485 main), #674 RS485 1.3.x, #675 #669 1.3.x, #676 #670 1.3.x (all base release/1.3.4, note clean cherry-pick to 1.3.3), #677 #671→1.3.4, #678 #671→1.3.3. TeslaMate token facts in proposal addendum (owner token carries ou_code too).
2026-10-10 PR1 opened: #679 main, #680 1.3.4, #681 1.3.3 (after independent review + fixes + re-review).
2026-10-10 live: sync on box via tunnel. Fixed live: private.tokens (127c022), bytea (941f3ff), Cloak AAD AES256GCM; owner list via /products (fix/owner-api-read 18f0c5d, first PR2 commit). Box on deploy/presence 182aec9: owner token read-only, telemetry attached, BLE-only commands.
2026-10-10 Owner API refresh (PR2): fix/owner-api-refresh 1e72329, port-owner-api-refresh-1.3.4 8383233; independent review (opus) + fixes + re-review (sonnet) all addressed. Accepted lows: clear-then-restore window, unreachable keeps paste, 5xx wording. Pre-existing: INFO4 logs full refresh response incl. tokens; req.status_code in other loops. Awaiting user OK to push/open PRs.
