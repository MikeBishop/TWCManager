# Pre-flight: Vehicle Model Phase 4 (control tick)

Plan: `.superpowers/plans/2026-10-17-vehicle-model-phase4-control-tick.md`. Code: `scratchpad/wt-vm4` at 1029809b (`vehicle-model/phase4`). Read-only review; nothing was run or changed.

**Verdict: GO-WITH-FIXES.** Fix findings 1–3 in the plan before Task 3 or Task 4 is dispatched. Findings 4–13 are text fixes to the task briefs. The rest are notes.

Severity: HIGH = will break the "green after every task" or the parity constraint, or is an untagged behaviour change. MEDIUM = a defect the implementer would probably meet and improvise around. LOW = a note or nit.

---

## 1. Task pairs that share a file or interface

| Pair | Producer → consumer | Conflict |
|---|---|---|
| T1–T3 | T1 puts WebIPC's send through `sendRS485`; T3 moves `processIPC` to the tick and relies on that. T1 adds the flush at TWCManager.py ≈ :897; T3 edits :925–1004. | None for the send. processIPC on the tick still walks the live round-robin through `getSlaveTWCID(i)` and `slaveTWCRoundRobin[i]` (WebIPCControl.py:179–193). That contradicts "the tick never iterates the live list" (finding 15). |
| T1–T4 | T1 removes `stopRequested` from `send_master_heartbeat` (:434–437) and from Gen2TWC :42–44. T4 rewrites `send_master_heartbeat` and Gen2TWC :40/:224–225. T1 changes Gen2TWCProvider mode 3; T4 fixes the :84 comment. | Line numbers shift after T1 and T3. T4 already says "after the Task 3 cut". Otherwise none. |
| T1–T5 | Both edit `send_master_heartbeat` (T1 the stop flag, T5 the gate block 541–658). | None. |
| T1–T6 | T6's guard greps for `stopRequested`. | None. |
| T2–T3 | Both edit the serial loop: T2 deletes :1006–1017, T3 deletes :983–985 and :1000–1004. T2 queues `refreshTokens` next to `checkCharge`; T3 starts ControlTick after `reconciler.start()` (:819), on adjacent lines. | None. The T2 static test (`loopSource`) and T3's `test_the_serial_loop_no_longer_distributes_or_processes_ipc` read the same text. Consistent. |
| T2–(tests) | T2 removes `lastTeslaTokenRefreshCheck`. | `test_limit_wiring.py:236–239` indexes the loop source on that string and raises ValueError. Not mapped (finding 11). |
| T3–T4 | T3 produces `drive()` with `controlPass`, `tickThenBeat`, `heardFrom`, the pure `num_cars_charging_now`, `observeChargingSessions`, and `distributeEVSEPower -> List[ChargingPoint]`. T4 consumes all of them: `ctx.carsCharging`, `ctx.confirmed` from the returned points, and the `plugSessions` bump inside `observeChargingSessions`. | (i) `drive()` now runs the distributor, which overwrites the targets that T4's tests set by hand with `pt.setTargetPower` and zeroes amps_max=0 beats (finding 1). (ii) T4 says offers are set "for every slave", but Review Focus 1 says `offerFor` never runs for a slave with `heardFrom` False (finding 9). (iii) `tickThenBeat` call order differs between BASE and after (finding 8). |
| T3–T5 | T3 produces `controlPass` and ControlTick; T5 adds the gate mapping. | Gates move off the heartbeat, so the `respondToSlaves==0` early return no longer covers them (finding 7). |
| T3–T6 | T3 registers `VehicleEndpoints` in `TWCMaster.__init__` and rewrites the `distributeEVSEPower` docstring. T6 replaces both with `vehicleEndpoints(master)` and `_budgets()`. | T3 does not say where the `heardFrom` filter lives. If it lives in `Gen2TWCs.allEVSEs`, T6 must carry it into `getAllEVSEs` (finding 19). |
| T4–T5 | T4 produces `Offer` and `slave.offer`; T5's `chargeGate` reads `offer.amps`. | T4's deletion range 818–1121 includes BASE 1114–1116 (cancel a pending stop when the offer is above 0), which T5 says it moves. Between T4 and T5 nothing does it (finding 4). |
| T4–T6 | Both edit Gen2TWC and ChargingPoint: T4 adds `_carKeys`, `confirmed` and `anonymousCars`; T6 drops the aggregates and changes the base to the mixin. | ChargingPoint still needs `convertWattsToAmps` and `currentVoltage`; the mixin keeps both. The new name `targetAmps` is banned by the existing guard that T6 extends (finding 3). |
| T5–T6 | T6's `test_one_distributor_entry` checks that only `controlPass` calls `distributeEVSEPower`. | None. |

## 2. Per-task self-consistency, symbol existence and callers

| Task | Text consistent with itself? | Deleted symbols exist at 1029809b? | Callers handled? |
|---|---|---|---|
| T1 outbox and VIN | Yes. Tests and interfaces agree. The counts are right: 2 starts + 1 stop = 3, and 1 VIN query + 2 kWh polls = 3. | Yes: `stopRequested` at TWCSlave :36–38 and :434–437 and Gen2TWC :42–44; TWCMaster :713/:832/:1803/:1813; HTTPControl :942; WebIPC :258; Gen2TWCProvider :111–115; VIN :1491–1570; background stop at :344. | **No.** `stopRequested` is asserted in `test_charging_reconciler.py:55,56,107,126` and `test_provider_outcomes_local.py:49,51,98`; only `test_gen2twc_provider.py:176` is mapped. The plan's grep scope leaves out `tests/unit`. There is no final flush on shutdown (finding 16). `vinCheckDigitValid` must uppercase, and the caller must keep the len-0 "non-Tesla, stop querying" branch (finding 20). |
| T2 tokens | Mostly. The discard rule covers `setTokens` only. The 401 path (`refresh` → `self.clear()`) can still wipe a token pasted during the POST (finding 10). | Yes. `lastTeslaTokenRefreshCheck` is at :57 (the plan says :55). | **No.** `test_limit_wiring.py:236–239` (static source index) breaks. Other `refreshTokenIfNeeded` callers (TeslaPowerwall2.py:240, TeslaAPI.py:599/:788) are fine under single-flight. |
| T3 tick, one distributor, flex | **No.** It calls the `drive()` change "PLUMBING-ONLY for every caller", which is false (finding 1). The `drive()` caller list also omits `test_amps_reconciler.py` and `test_limit_wiring.py`, which import it as `heartbeat`. `VehicleEndpoints.allEVSEs` returns `[]` at :105, not :96. | Yes: flex :42/:394/:1830; Policy :59/:82/:287; TWCSlave :66/:99–101 and :767–816; gate :554–562; registration :759–776; loop :925–930, :983–985, :1000–1004; the 4 `setAllowedFlex` mocks in test_policy (:273/:436/:532/:610); `test_pure_gen2_leaves_distributor_off` (test_charging_points:100). | Partly. `test_distributor_loop.py` is never named; its comment "A non-Gen2 controller makes the distributor run" goes stale, and T6 breaks it. The missing slave-count gate (finding 2) is not discussed. Docs and example configs are listed. |
| T4 offers on the tick | **No.** (a) Range 126–183 includes `minAmpsToOffer` (:175–179), which is still needed (finding 5). (b) Range 818–1121 swallows :1114–1116 (finding 4). (c) Files says `anonymousCars(master)`, Interfaces says `anonymousCars(master, slave)`. (d) "for every slave" vs Review Focus 1. (e) The `by` "heartbeat"→"distributor" relabel is called INTENTIONALLY CHANGED but names none of (a)–(f). | Yes: car helpers :126–183; `_ampsKeys` :86; `APIcontrol` :94; `set_last_amps_offered` :1180; the spike block; TWCMaster :91/:819/:1954; linkready :1237/:1242; HTTP :2005–2012; debug.html.j2 :113–117; Gen2TWC :28/:40/:225. | **No.** (i) `test_no_legacy_command_paths.py:19` greps `lib` for `targetAmps` and must stay empty (finding 3). (ii) `test_amps_reconciler.py:105` assigns `s.vehicleRateRaised = True`, which a read-only property rejects; :30, :100 and :102 call the removed helpers; `test_limit_wiring.py:308` must also be covered. (iii) The "test_twcmaster.py spike rows" do not exist: the only spike-named tests (:600–670, `test_returns_positive_when_charger_spiked`) are `getMaxAmpsForTargetGridUsage`/`subtractChargerLoad` regressions and must stay (finding 12). (iv) `test_gen2_idle_minimum.offers(spike=True)` is on by default, so rows that omit `spike=` ran with the spike at BASE. The plan covers this. |
| T5 gates | Yes. `chargeGate` matches BASE :548–658. Dropping the unreachable `< 4.0` is correct. | Yes: :541–658. | Partly. The `respondToSlaves==0` shun guard is lost (finding 7). The `test_charging_reconciler` rows go through `drive`, which carries finding 1's risk. |
| T6 scaffolding | Yes. | Yes: EVSEController.py (50), Gen2TWCs.py (44), VehicleEndpoints.py (137), EVSEInstance.py (147); class-level `settings` at :69–84 (the plan says :66–81). `VehicleEndpoint` is stateless (:21–25), so dropping the cache is safe. | Partly. `test_distributor_loop.py` builds a master with `__new__` and no `wiringMaxAmpsAllTWCs`, so `_budgets()` raises KeyError. `test_charging_points.py` and `test_distributor_loop.py` use `TWCMaster.__new__`, which falls back to class-level `settings`, so deleting it is a "class-level reader" case. The guard regex `-w "Gen2TWCs\("` cannot match `Gen2TWCs(self)` (finding 18). Gen3 keeps its name, type, `maxPower` (:505) and `stop` (:516). |

## 3. Hidden behaviour changes (beyond (a)–(f) and the user decisions)

| # | Change | Evidence | Severity |
|---|---|---|---|
| H1 | **The distributor runs with zero Gen2 slaves.** At BASE (and on main) `distributeEVSEPower` is called only inside `if master.countSlaveTWC() > 0` and only at round-robin index 0 (TWCManager.py:923–930). Gen3-only and vehicle-only installs never ran it: the Gen3 house load stays at maxFuse (`Gen3TWCs.solve` → `maxFuse` with no targets), and VehicleEndpoints never write AMPS. ControlTick would distribute every second in those installs. Gen3 units get throttled (untagged), and a UMC car at home with Fleet as its only amps path gets `set_charging_amps` desires: **new paid calls**. | TWCManager.py:923–930; Gen3TWCs.py:323–340; VehicleEndpoint.setTargetPower :144–155 | HIGH |
| H2 | **Gates and the positive-offer cancel run during the chargeStopMode-2 shun.** BASE `send_master_heartbeat` returns before the gate block while `respondToSlaves==0` (:439–451). With no heartbeats there are no replies, so the receive-side cancel (:1114) never runs either. On the tick, `chargeGate` and `cancelStopCarsCharging` act on stale `reported*` values for up to 60 s, and the cancel can drop the stop being delivered. | TWCSlave.py:439–451, :1114–1116; Gen2TWCProvider.stopCharging mode 2 | MEDIUM |
| H3 | **A runtime mode switch from 2 to 1 no longer re-lifts.** BASE resets `vehicleRateRaised` on every mode-2 pass and every mode-3 pass below 6 A, for every point type (TWCSlave.py:934). The plan maps only TWCMaster:1317 and ChargingPoint:191. The mode-1 lift exists for "leftover from API control" (comment :948–953). | TWCSlave.py:929–935 | MEDIUM |
| H4 | **The own-rate distinction is lost.** BASE `_clearCarAmps` clears only `d.by == "heartbeat"` (:154). After relabelling to "distributor", the "key left the set → clear non-lift" rule can clear a VehicleEndpoint's rate for the same car. That can happen with `vehicles[0]` in the anonymous fan-out while VehicleEndpoints is not blind (slave at 00, not drawing). The rate then flips between set and clear across passes, and each set can be a paid send. | TWCSlave.py:150–155; VehicleEndpoints.py:108–119; TWCSlave._anonCars :126–134 | LOW–MED |
| H5 | **targetAmps gets a second writer.** `Gen2TWCProvider.setAmps` runs on the reconciler lane thread and calls `slave.setTargetPower` (Gen2TWCProvider.py:91–97). The ownership table says only the tick writes it. This is benign, because the next tick overwrites the value, but the table is wrong. | Gen2TWCProvider.py:91–97 | LOW |
| H6 | **The tick sees an unheard slave in the round-robin.** A slave is added at linkready and is in the list before its first reply. The plan's `heardFrom` skip covers the distributor; T4's controlPass loop must skip it too (finding 9). `_blindTWCs` still reads an unheard slave as state 00 / 0 A, which is not blind. That matches BASE. | TWCMaster.newSlave :1239; VehicleEndpoints._blindTWCs | (finding 9) |
| H7 | **Startup with budget 0.** The Policy thread's first evaluation is asynchronous. If a slave is heard before `maxAmpsToDivideAmongSlaves` is set (class default 0), the first offer is 0, which drops a charging car to its minimum. This is pre-existing at BASE (the distributor runs at the first round-robin), but Review Focus 1's "never offers zero" test does not cover it. Separately, that test's "heartbeat sends 32" step gets a `00` payload if amps_max is 32 (`_amps_heartbeat` sends "no change" when the reported max matches). Use amps_max ≠ 32 or assert `offer.amps`. | TWCMaster :63, :160–163; TWCSlave._amps_heartbeat :1158–1178 | LOW |
| H8 | **Shutdown drops queued RS-485 messages.** The outbox is not flushed after the loop exits, so a mode-3 stop that `reconciler.drain` delivers after Task 1 is enqueued and lost. BASE lost the `stopRequested` flag the same way. A final `flushRS485()` before `getInterfaceModule().close()` would fix it, and `ControlTick.stop()` should join with a timeout before `reconciler.stop()`. | TWCManager.py:2025–2060 | LOW |
| H9 | **Web IPC is serviced once per second.** `processIPC` takes one message per call (`receive(False, 2)`, WebIPCControl.py:111). On the tick that is one message per second instead of one per 25 ms. PHP waits 5 s per query (index.php:603), so multi-query pages get slower but nothing breaks. | WebIPCControl.py:100–111 | LOW |
| H10 | **60 s gate timing.** `timeLastAmpsOfferedChanged` now changes on the tick, not on the heartbeat. Finding (e) re-caps every pass, but BASE re-capped every pass whenever `desired != lastAmpsOffered`, so cap jitter is the same. No new change. | TWCSlave.py:1191 | none |
| H11 | **Idle-TWC minimum, wiring cap, Gen3, mode 2/3 and the anonymous fan-out.** Ported faithfully apart from H1, H3 and H4. `offerFor`'s probe rule matches BASE :834–928, and the 5 s hold matches BASE :1080–1091 (mode 1 only, as at BASE). The mode-3 TWC-only branch below 6 A is reachable only when the minimum is under 6 (protocol 1, or 3-phase at 1 A). | — | none |
| H12 | **Thread ownership.** The serial thread writes `reported*`, `heardFrom`, `isCharging`, VIN and session state, `plugSessions` and `masterHeartbeatData`. The tick writes `offer`, `lastAmpsOffered`, `timeLastAmpsOfferedChanged`, `liftedSession` and `_lastKeys`. `stopTimeout` gets two writers, `observeChargingSessions` (serial) and `stopCarsCharging` (tick); BASE already had cross-thread writers there through getStatus and policy. Policy `clearOverride`/`overrideLimit` move from the serial thread to the tick: still not the Policy thread, same exposure. | TWCMaster :1262–1346, :1998–2020 | LOW |

## 4. Lib-delta realism; missed behaviour-neutral deletions

| Task | Plan Δ | Assessment |
|---|---|---|
| T1 | −50 | Realistic: VIN −55, outbox +15, flag −10. |
| T2 | +15 | Realistic, likely +20 to +25 once the `clear()` guard and requeue-in-`finally` are added. |
| T3 | −60 | Realistic: about 135 out, 65 in. |
| T4 | −370 | Optimistic; expect about −310 to −330. ChargingPoint must write rates for keys that have no VehicleEndpoint object (desired.set/clearIf, a requestedAmps read from the registry, `_lastKeys` clearing, the mode-2 lift reset), which is more than the 30 lines budgeted. Keeping `minAmpsToOffer` saves 5 fewer lines than planned. |
| T5 | −90 | Realistic: 118 out, about 30 in. |
| T6 | −310 | Realistic. |
| **End** | ≈ 26,560 | ≈ 26,600–26,650 likely; still below 27,425. |

Missed deletions that change no behaviour (≈ −15 to −20):
- `ChargingPoint.currentAmps` (ChargingPoint.py:82–87). Nothing reads it; the only reference is its own definition.
- `ChargingPoint.isLocal` (:55–57). Callers use the members' `e.isLocal`.
- After T4, TWCSlave's unused imports: `AMPS`, `known`, `satisfied`, `isAnonKey` (:7–11). `broadcastVehicles`/`located` stay for `pluggedCars`.
- `TWCMaster.getAllEVSEs` and `chargingPoints` have one caller each and can be inlined in T6 (about 8 lines).
- Fix the stale docstring in VehicleEndpoint.py:4–5 ("the distributor runs on the serial thread").

## 5. Deleted-test mapping completeness

| Test (file:line) | Task | Mapped? | Needed |
|---|---|---|---|
| test_charging_reconciler.py:55, :56, :107, :126 (`stopRequested`, `sendStopCommand` sent by the heartbeat) | T1 | No | Rewrite to `m._outbox`/`flushRS485`, PLUMBING-ONLY |
| test_provider_outcomes_local.py:49, :51, :98 | T1 | No | Same |
| test_gen2twc_provider.py:176 | T1 | Yes | — |
| test_limit_wiring.py:236–239 (loop-source index) | T2 | No | Point at the `refreshTokens` handler, PLUMBING-ONLY |
| test_charging_reconciler.py:195 `test_an_offer_starts_the_car_from_the_heartbeat`; test_limit_wiring.py:304–320; parity `test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit` (:1206) | T3 (`drive`) | Listed as plumbing; **wrong** | Under the distributor an amps_max=0, 0 A beat gets target 0, so no start and no lift. Either set a realistic amps_max (PLUMBING-ONLY, with the reason that a real TWC echoes its offer) or classify as (b). The parity command list is at risk. |
| test_amps_reconciler.py:68–89; parity `test_mode_2_twc_holds_the_target_until_the_car_rate_lands` (:1089) | T3/T4 | Listed as plumbing; **wrong** | Inside `drive`, `controlPass` overwrites the hand-set `pt.setTargetPower`. These need an offers-only beat helper. |
| test_distributor_loop.py (whole file) | T3/T6 | No | Comment stale after T3; `_budgets()` breaks it at T6 |
| test_amps_reconciler.py:30, :100, :102, :105, :107, :177, :198 | T3/T4 | Partly (:107 only) | :105 assigns a read-only property |
| test_limit_wiring.py:308 (`vehicleRateRaised`) | T4 | No | Reading works through the property; the setup depends on finding 1 |
| test_twcmaster.py "spike rows" | T4 | Mis-mapped | Keep :600–670 (subtractChargerLoad) |
| test_twcslave.py:285 `test_slave_last_amps_desired`, :327, :344, :428–448 | T3/T4 | Yes | — |
| test_twcslave.py:176 `test_slave_heartbeat_data_default` | T4 | Not mentioned | Keeps passing (class default) |
| test_no_legacy_command_paths.py:19 (`targetAmps` banned) | T4 | No | Rename the new attribute |
| test_charging_points.py (`__new__` masters, `_evseTargetAmps`, `pointOwnsAmps`, :100) | T3/T4/T6 | Yes, generically | Watch class-level `settings` |
| test_gen2_idle_minimum.py:54 (own `heartbeat` helper calls `distributeEVSEPower`) | T3/T4 | Yes | — |
| test_registry_callers.py:52, :229; tests/API/test_getConfig.py:22 (flex keys in config dicts or comments) | T3 | Not needed | Harmless |
| test_telemetry_registry.py, test_vehicle_endpoint.py, test_gen3twc_provider.py, test_provider_registration.py (`VehicleEndpoints`/`EVSEController` imports) | T6 | "others from the Global grep" | Covered only if T6 greps `tests/unit`; its Global scope does not |

---

## Numbered findings

1. **HIGH.** T3's `drive()` change is not plumbing-only. Test masters at BASE had no VehicleEndpoints, so they ran the legacy path. After the change every beat redistributes: hand-set `pt.setTargetPower` targets are overwritten, and amps_max=0 / 0 A beats get target 0. That breaks a start test, an anonymous-session test and parity row 26 (paid counts at risk). Fix: split `controlPass` into distribute and publish-offers-plus-gates, and give tests an offers-only beat. Enumerate the rows that need a realistic amps_max, or tag them (b).
2. **HIGH.** `controlPass` drops the `countSlaveTWC() > 0` gate (TWCManager.py:923–930). Gen3-only and vehicle-only installs would start distributing: Gen3 throttling, and possibly paid Fleet amps. Keep the gate or get an explicit (g) ruling with a paid-call test.
3. **HIGH.** The new attribute name `targetAmps` fails the existing guard `test_no_legacy_command_paths.py:19` (it greps `lib` for `targetAmps`). Rename it.
4. **MEDIUM.** T4's range 818–1121 deletes the positive-offer `cancelStopCarsCharging` (:1114–1116) that T5 says it moves. Put it in `controlPass` in T4.
5. **MEDIUM.** T4's range 126–183 includes `minAmpsToOffer` (:175–179), which is still needed. Delete 126–174 and 181–183 only.
6. **MEDIUM.** The BASE mode-2 (and mode-3 below 6 A) lift reset at TWCSlave:934 is not ported, so a runtime 2→1 switch no longer re-lifts. Add the reset and a test.
7. **MEDIUM.** Gates and the cancel now run during the chargeStopMode-2 shun (BASE returned early at :439–451). Skip them while `respondToSlaves==0` and the expiry has not passed.
8. **MEDIUM.** `tickThenBeat` order: BASE equivalence needs distribute→receive→send at BASE and receive→controlPass→send after. "controlPass then heartbeat" uses stale values and skips unheard slaves.
9. **MEDIUM.** T4 says `controlPass` sets an offer for "every slave", which contradicts Review Focus 1. Skip `heardFrom` False there too.
10. **MEDIUM.** T2's discard rule misses the 401 path: `refresh` → `clear()` can wipe a token pasted during the POST. Also put `restore()` under `_cond`, and re-queue `refreshTokens` in `finally`.
11. **MEDIUM.** Unmapped tests: `stopRequested` (test_charging_reconciler ×4, test_provider_outcomes_local ×3, T1); test_limit_wiring:236–239 (T2); test_amps_reconciler:105 assigns the read-only `vehicleRateRaised` (T4); test_distributor_loop.py (T3/T6). The plan's grep scope leaves out `tests/unit`.
12. **MEDIUM.** T4 says to delete "test_twcmaster.py spike rows", but none exist. The spike-named tests at :600–670 are `subtractChargerLoad` regressions and must stay.
13. **LOW–MED.** Relabelling `by` "heartbeat"→"distributor" loses BASE's own-rate check, so the "key left the set" clear can remove a VehicleEndpoint's rate for the same car (paid resend churn). Keep a distinct label. The relabel also cites none of (a)–(f).
14. **LOW.** `Gen2TWCProvider.setAmps` (reconciler thread) writes `targetAmps` too. It is benign, but the ownership table should say so.
15. **LOW.** `processIPC` on the tick walks the live round-robin (WebIPCControl:179–193) and now handles one IPC message per second.
16. **LOW.** Shutdown never flushes the RS-485 outbox. Add a final `flushRS485()`, and have `ControlTick.stop()` join before `reconciler.stop()`.
17. **LOW.** The restart test's "sends 32" step gets a `00` payload when amps_max is 32. The startup window with budget 0 (pre-existing) is not covered.
18. **LOW.** T6's guard `git grep -w "Gen2TWCs\(|VehicleEndpoints\("` never matches `Gen2TWCs(self)`. Drop `-w` for those alternatives.
19. **LOW.** Interface drift: `anonymousCars(master)` vs `anonymousCars(master, slave)`. The location of the `heardFrom` filter must survive T6.
20. **LOW.** `vinCheckDigitValid` must uppercase, and the caller must keep BASE's len-0 "non-Tesla, stop querying" branch.
21. **LOW.** Line-reference nits: `lastTeslaTokenRefreshCheck` is at :57, class-level `settings` at :69–84, and VehicleEndpoints' `[]` at :105. The deleted-test rule says (a)–(e), but (f) exists.
22. **INFO.** The lib estimates are realistic apart from T4 (expect about −320). The end figure is ≈ 26,600–26,650, still below BASE. About 15–20 more lines can go: `ChargingPoint.currentAmps`/`isLocal`, TWCSlave's unused imports, and inlining `getAllEVSEs`/`chargingPoints`.
