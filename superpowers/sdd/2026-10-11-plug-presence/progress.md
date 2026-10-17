# SDD ledger — plan: /home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/plans/2026-10-11-plug-presence.md

Spec: .superpowers/specs/2026-10-11-plug-presence-design.md (approved 2026-10-11). Execution: subagent-driven (user-chosen pattern for these plans).
Worktree: /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-plug (created by Task 1, branch presence/3-plug-presence from presence/2-charge-limits).

## Pre-flight scan

| Rows | Produces vs consumes | Finding |
|---|---|---|
| T1 -> T2 | T2 must provide every observer signature carried code calls (nominate, observeContact, observeProof, observeUnplug, observePlug, observeTelemetryPlug, observeLocation, state, start, stop) | consistent |
| T2 -> T3 | T3 defines _probe/sources consumed by T2 runPass (no-op until T3) | consistent |
| T2 -> T5 | T2 row "plugState(False, read) on PRESUMED -> NOT_HOME"; T5 (controller addition) "with held limit -> DEPARTING" | CONFLICT (intentional override) |
| T3 -> T4 | Evidence dict keys (reach,pluggedIn,inside,pilot,actual,fastChargerType,fastChargerPresent) | consistent |
| T4 -> T8, T12 | vinForTwc, _twcVin, isTwcAttributed | consistent |
| T2 -> T6 | observePlugState(edge=False) via discover | consistent |
| T2 -> T7 | isHome / isPluggedHome | consistent |
| T7 -> T11 | allEVSEs filter isPluggedHome vs #694 rewrite | consistent (T11 resolution rule) |
| T11 -> T12 | bleSilent/isTwcAttributed on rebased branch | consistent |
| T12 -> T13 | deploy merge + 92dae4d port | consistent |
| T1..T13 self | tests vs interfaces per task | consistent; T10 adds no lib code |

Ruling: T5's held-limit rule overrides T2's "PRESUMED read unplugged -> NOT_HOME" only when _restorePending(vin); T2 implements the table as written and its test (nothing held) stays valid; T5 adds the held-limit branch and its tests — spec intent (restore the user's outside limit) + user-approved ruling — cost if wrong: one extra restore command after a restart.
Ruling: execution order T1..T13 as written; box deploy of deploy/presence-3 is a controller step after T13 (not in plan) — cost if wrong: none.
Ruling: black only on touched files (venv black reformats untouched files) — same as previous plan — cost if wrong: none.
Task 1: implementer DONE c66f3a2 (958 pass; tree == presence/4 except 2 tracker files)
Task 1: minor (deferred): 7 partial commits carry new author dates
Task 1: complete (commits presence/2..c66f3a2, review clean)
Task 2: BASE c66f3a2
Ruling (user-directed): presence is binary (home + basis evidence|presumed); limit state is the separate held-limit dimension; Task 5 becomes a reconciler on presence x held limit; no DEPARTING tracker state. Task 2 implementer redirected mid-task. Spec + plan Task 5 updated.
Task 2: implementer DONE b8127c1 + 9fd8493 (user model change) (959 pass)
Task 2: cannot-verify resolved: Task 7 narrows Fleet EVSE to isPluggedHome (plan T7); Task 5 brief already rewritten as reconciler.
Task 2: minor (deferred): handlers judged on batch end state (H->N->H runs onArrival; double onDeparting possible)
Task 2: minor (deferred): hold/reach ages measured at apply time not observation time
Task 2: minor (deferred -> carry to Task 6): weak plugged record and _inside never age out; stale telemetry plugged + fresh BLE contact can make HOME
Task 2: minor (deferred): TeslaBLE.py:774 stale "DEPARTING or NOT_HOME" comment
Task 2: minor (deferred): _applyProof records source "twc" regardless
Task 2: minor (deferred): presenceSources warning fires on null/empty
Task 2: minor (deferred): duplicated VehiclePresence test setup x3
Task 2: complete (commits c66f3a2..9fd8493, review clean)
Task 3: BASE 9fd8493
Ruling (user-approved): Task 8 broadcast also excludes cars with evidence of being plugged elsewhere; distributor zero-share stop goes to a separate branch off main (not this plan).
Task 3: implementer DONE b7ab12d (974 pass); extra: fastChargerPresent on CarApiVehicle (TeslaAPI.py)
Task 3: minor (deferred -> carry to Task 6): blePluggedIn treats Unknown/SNA/{} chargingState as plugged; should be None (false strong evidence)
Task 3: minor (deferred -> carry to Task 6): apiSource uses cached chargingState/fastChargerPresent even if vehicle_data lacked charge_state
Task 3: complete (commits 9fd8493..b7ab12d, review clean)
Task 4: BASE b7ab12d
Task 4: implementer DONE a0fbb5d (994 pass)
Task 4: minor (load-bearing for T8): named-VIN unplug does not pop _twcVin[twc]
Task 4: minor (load-bearing): VIN-less single-candidate unplug writes no strong unplugged record
Task 4: minor (load-bearing for T8): telemetry-kept target loses attribution; re-insert
Task 4: minor (deferred): rule-4 single-candidate guess gets strong "twc" label; consider distinct
Task 4: minor (deferred): ambiguous plug swept twice; throttle
Task 4: minor (deferred): tests missing for _defaultTwcAmps, target-in-excluded, telemetry-kept target
Task 4: verify on box later: reportedAmpsMax == BLE chargerPilotCurrent
Ruling: fold Task 4 minors 1,2,4 into the Task 5 dispatch (same file, load-bearing for Task 8 vinForTwc and for stale-plug evidence) — cost if wrong: slightly larger Task 5 diff.
Task 4: complete (commits b7ab12d..a0fbb5d, review clean)
Task 5: BASE a0fbb5d
Task 5: implementer DONE 9219183 + f4d6837 (1023 pass); touched VehicleCommandQueue (queued(), running task)
Ruling (Task 5 I1, plan-mandated): spec wins — after the fallback (sent or not, e.g. ble_only), keep slow BLE-only probing while the limit is held and retry localOnly when reachable; fallbackSent stays unconditional to avoid zero-delay probing — cost if wrong: one BLE probe per 10 min per held car.
Ruling (Task 5 I2): add a per-pass sweep of not-home VINs with a held limit and no record (spec calls this a reconciler) — cost if wrong: negligible CPU.
Task 5: minor (deferred): slow-mode outside nomination can start a second probe chain
Task 5: minor (deferred): unheld departing due skips coinciding nominations
Task 5: minor (deferred): BLE retry re-runs onDeparting; if BLE gone, immediate remote
Task 5: minor (deferred): first departing probe competes with queued localOnly restore for BLE
Task 5: minor (deferred): _startDeparting uses pass-start now
Task 5: fix round 1/5 dispatched (I1, I2)
Task 5: fix round 1/5 (2 addressed, 0 open; commits f4d6837..80a5b03)
Task 5: complete (commits a0fbb5d..80a5b03, review clean)
Task 6: BASE 80a5b03
Task 6: implementer DONE 0b74afc + aff0d37 (1052 pass)
Ruling (Task 6 I1, plan gap): discover must not let weak evidence return False when a TWC names the car or a strong plug record is within the hold — spec evidence order — cost if wrong: none.
Ruling (Task 6 minor 4, load-bearing safety): discover failures fail closed in TeslaBLE and TeslaAPI (anti-goal: no limit to a car not plugged in) — fold into fix round 1.
Task 6: note -> Task 8: TeslaBLE charge start ungated; VIN-less BLE start loop hits every configured car (Task 8 restricts to broadcastVINs).
Task 6: minor (deferred): TeslaAPI _discover BLE branch uses chargingState only, recorded as api
Task 6: minor (deferred): strong BLE plugged+fastCharger makes HOME (disagrees with discover; impractical)
Task 6: minor (deferred): tests missing for BLE gate telemetry branch, API start gate Disconnected/away
Task 6: fix round 1/5 dispatched (I1 + fail-closed)
Task 6: fix round 1/5 (2 addressed, 0 open; commits aff0d37..66e1038)
Task 6: minor (deferred): no test for weak outside+BLE-unreachable variant
Task 6: complete (commits 80a5b03..66e1038, review clean)
Task 7: BASE 66e1038
Task 7: implementer DONE 02c040a (1070 pass)
Task 7: presumed car woken = intended (user: presume presence, discover on wake)
Task 7: minor (deferred): TeslaAPIController isPluggedHome call unguarded (presence exception breaks allEVSEs)
Task 7: minor (deferred): test_departing_car_is_never_woken convoluted
Task 7: complete (commits 66e1038..02c040a, review clean)
Task 8: BASE 02c040a
Task 8: implementer DONE 4f6cda9 (1088 pass)
Task 8: extra accepted: broadcastVINs also skips cars a VIN-reading TWC names (tell user)
Ruling (Task 8 I1, plan-mandated): pass the target VIN set into car_api_available so a broadcast wakes only targets — spec "broadcast only to candidates" — cost if wrong: none.
Ruling: TeslaBLE.setChargeRate(vehicle=None) also limited to broadcastVINs candidates (same rule, no later task covers it) — fold into fix round.
Task 8: minor (deferred): fail-open on presence exception kept (reviewer agrees)
Task 8: minor (deferred): targeted start runs policy-wide applyChargeLimit; pass vin
Task 8: minor (deferred): BLE stop clears _stopAskingToStartCharging for all cars
Task 8: minor (deferred): failed-probe exclusion never ages (Task 12 bleSilent)
Task 8: minor (deferred): no test for vinForTwc raising in TWCSlave
Task 8: minor (deferred): HA targeted VIN not held returns success
Task 8: minor (deferred): enphase test warning pre-existing
Task 8: fix round 1/5 dispatched (I1, I2, BLE setChargeRate)
Task 8: fix round 1/5 implementer DONE 0fe75a8 (1093 pass)
Task 8: fix round 1 re-review dispatched (sonnet)
Task 8: fix round 1/5 (3 addressed, 0 open; commits 4f6cda9..0fe75a8)
Task 8: complete (commits 02c040a..0fe75a8, review clean)
Task 9: BASE 0fe75a8
Task 9: implementer dispatched (sonnet)
Task 9: implementer DONE fc880f9 (1097 pass)
Task 9: review dispatched (sonnet)
Task 9: minor (deferred): docs/modules/Vehicle_HomeAssistant.md:97 atHomeRadius default not mentioned
Task 9: complete (commits 0fe75a8..fc880f9, review clean)
Task 10: BASE fc880f9
Task 10: implementer dispatched (opus); told brief DEPARTING = not-home + limit held (spec two-dimension model)
Task 10: implementer DONE_WITH_CONCERNS 3e20776 (1113 pass, gate clean, no lib change)
Ruling (Task 10 c1): legacy grep 2 lines (check + string of the one presenceSources warning) satisfies the gate's intent — cost if wrong: none.
Ruling (Task 10 c2): stub at _run_command_with_timeout instead of sendCommand/probePresence/_fetch_state_json accepted — keeps real BLE reporting + breaker in scenario — cost if wrong: none.
Task 10: for final review: c3 _cancelRestore redundant with queue key replacement; c4 departed car w/o telemetry stays broadcastVINs candidate (one Fleet read at most); c5 TeslaAPI _discover trusts cached chargingState when a telemetry feed is live (stale Disconnected if feed lacks charging_state; TeslaMate publishes it); c6 _lastProbe set without probe on departing end.
Task 10: review dispatched (sonnet)
Task 10: minor (deferred): scenario fixture ~600 lines reaches private internals
Task 10: complete (commits fc880f9..3e20776, review clean)
Task 11: BASE 3e20776 (rebase of presence/5 b7e1623 stack); implementer dispatched (sonnet)
Task 11: implementer DONE 8cb9dee (1151 pass, scenarios 16/16; 2 conflicts in allEVSEs; 2 test fixes autosquashed)
Task 11: complete (presence/4-fleet-rate-queue 8cb9dee, review clean)
Task 12: BASE 8cb9dee
Task 12: implementer dispatched (sonnet)
Task 12: implementer DONE a80a524 (1159 pass)
Task 12: extra accepted: _scanFailed keeps TWC-scan failure fail-closed against the UMC exception
Task 12: note: bleSilent never ages (old failure); residual only if a UMC->TWC move goes unseen
Ruling (Task 12 minor 1 -> must-fix): bleSilent must honour "no success within BLE_REACH_MAX_AGE" (brief) — one flaky probe would give a TWC car a Fleet EVSE — cost if wrong: small extra state.
Task 12: minor (deferred): test writes presence._twcVin directly
Task 12: fix round 1/5 dispatched (bleSilent success window)
Task 12: fix round 1 DONE 14ae080 (1160 pass); re-review dispatched (sonnet)
Task 12: fix round 1/5 (1 addressed, 0 open; commits a80a524..14ae080)
Task 12: complete (presence/4-fleet-rate-queue 8cb9dee..14ae080, review clean)
Task 13: BASE 14ae080 + feat/token-slots fe764ff
Task 13: implementer dispatched (opus)
Task 13: implementer DONE a8ef9cb (merge) + 3b7fdd0 (port), 1330 pass
Task 13: check in review: "car with no location fix no longer woken" vs startup presumed-present wake requirement
Task 13: review approved (opus); wake gate verified OK (atHome = presence.isHome incl. presumed)
Ruling (Task 13 minors 1-3 -> must-fix): TeslaAPI policy-wide away-skip untested (the 2026-10-11 path); add no-fix presumed Fleet wake test; reword report — cost if wrong: test-only work.
Task 13: minor (deferred): atHome falls back to location if presence.isHome raises (pre-existing presence/4)
Task 13: minor (deferred): charge_start/wake POST without timeout (token-slots branch; box watch list)
Task 13: fix round 1/5 dispatched; tests to carry back to presence/3 before PRs
Task 13: fix round 1 DONE cce331f (1331 pass)
Task 13: carry-back list (to presence/3 then presence/4): test_teslable_presence + test_teslaapi_presence changes from cce331f (bearer token form), and test_2026_10_11 scenario policy 60% change
Task 13: fix round 1/5 (3 addressed, 0 open; commits 3b7fdd0..cce331f)
Task 13: complete (deploy/presence-3 a8ef9cb..cce331f, review clean)
Final review: dispatched (fable) presence/2-charge-limits..presence/4-fleet-rate-queue + deploy/presence-3
Final review: done (fable) — deploy Yes; PRs With fixes (I1 single-shot remote restore; I2 bleSilent one failure + no re-probe; M1, M2, M7). Full table in final-review.md.
Ruling: deploy waits for the fix round — box now has a Fleet slot (carApiBearerToken set) + ble_only, so review's "Owner-only refuses Fleet" premise is false; I2 could send paid set_charging_amps if Fleet EVSE path ignores commandPolicy — cost if wrong: deploy delayed ~1h.
Final fix round: dispatched (opus), brief final-fix-brief.md; includes carry-back tests, restack presence/4, merge into deploy/presence-3.
Ruling (user, I1 redesign): remote restore = state reconciliation from the saved limit table; per-VIN backoff 600s doubling, cap 1h, reset on success/arrival; sweep owns remote retries; no per-departure counter — sent to fix agent mid-round.
Final fix round: DONE presence/3 6c61310 (1125), presence/4 8f47928 (1183), deploy/presence-3 1d4258b (1353). Finding: Fleet EVSE rate ignored ble_only before (now gated in TeslaAPIEVSE.setTargetPower); EVSE still listed/power share under ble_only.
Final re-review (opus): all addressed; deploy Yes. Pre-PR minors: contradictory "restoring remotely" INFO under ble_only (VehiclePresence.py:1381); add presumed-car-never-restored test. Out of scope: Fleet EVSE power share under ble_only (allEVSEs/isReadOnly should honour ble_only); apiDebugInterface manual bypass; slow probes never stop while limit held.
Return fix (live 09:17 bug): DONE presence/3 8233d6b (1154), presence/4 e987d0a (1212), deploy/presence-3 8da7e41 (1382). Check 3 broken at startup (rate broadcast excluded TWC-named car before vehicle list loaded) — fixed.
