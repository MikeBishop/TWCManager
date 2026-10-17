# Task 10 report: plug-presence scenarios end to end, and the branch gate

Status: DONE_WITH_CONCERNS (minor concerns only; no library change was needed)

Worktree: `.../scratchpad/wt-plug`, branch `presence/3-plug-presence`
Commit: `3e20776` Test the plug-presence scenarios end to end, including 2026-10-11 (on top of `fc880f9`; not pushed)
Interpreter: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python` (the `<PY>` from global-constraints.md; no venv exists inside the worktree)

## What the test wires (tests/unit/test_plug_presence_scenarios.py)

Real components:
- a real `TWCMaster` (its own background-task queue/lock/cmds replaced per instance so the class-level ones don't leak); `getNormalChargeLimit` / `saveNormalChargeLimit`, `queue_vehicle_command`, `queue_background_task`, `startCarsCharging`, `recordVehicleVIN`, the module registry and `getModuleByPriority` are all the master's own;
- `VehiclePresence(master, clock=fake)` with every other hook at its default: `buildSources` (real BLE / telemetry / API sources), real `arrivalHandler` / `departingHandler` / `departureHandler` / `homeProofHandler`, default `bleApplies`, known vehicles, TWC VINs/amps (from the real slaves), `restoreQueued` (from the real queue). `runPass` is driven by the test; the thread is never started;
- the master's real `VehicleCommandQueue`, drained synchronously by a helper that does what `_run` does;
- `VehiclePriority` (policy from `settings["commandPolicy"]`), `TeslaBLE`, `TeslaAPI`, `TeslaMateVehicle` (no MQTT; fed through `applyDataToVehicle`, so `Telemetry._reportLocation/_reportPlug` are real), `TeslaAPIController`;
- real `TWCSlave`s fed a heartbeat every 5 s through `_checkPresenceTriggers` (so the 60 s debounce, 300 s link grace and VIN-less `observePlug`/`observeUnplug` are the real code).

Fakes, at the edges only:
- **tesla-control**: stubbed at `TeslaBLE._run_command_with_timeout` (the process boundary) rather than at `sendCommand` / `probePresence` / `_fetch_state_json` as the brief worded it. Stubbing one layer down keeps `_reportContact`, `_reportPlug`, `_markBLEProven`, `blePluggedIn`, `parseCommandOutput`, the retry wrapper and the circuit breaker real; those are exactly how BLE feeds presence in these scenarios, and stubbing the three methods would have meant re-implementing those reports in the stub. `sendCommand` is additionally *spied* (not stubbed) so the assertions see every command TeslaBLE tried, including ones its circuit breaker stopped before tesla-control ran.
- **Fleet API**: `requests.get` / `requests.post` in TeslaAPI replaced by a fake that records every request (method, VIN, endpoint, body) and answers vehicle list, `/{vin}` state, `vehicle_data` (408 while asleep), `wake_up`, `command/set_charge_limit`, `command/charge_start`.
- One `Car` model per VIN behind both fakes (in range, awake, plugged, limit, location, pilot, charger type).
- One clock: presence's clock, and `time` in TeslaAPI and Telemetry (sleep is a no-op). `TeslaAPI.Thread` is patched so `CarApiVehicle`'s sync watchdog thread never starts.
- An arrival spy wraps `VehiclePresence._runArrival` (calls the real one) so "one apply" can be checked against arrivals too.

## Scenarios (16, all pass)

| Test | What it drives | Key assertions |
|---|---|---|
| `test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing` | BLE + Fleet token, prefer_ble, TeslaMate location. Startup BLE read -> home (evidence); policy apply sets 50 (saved [80, 50]). VIN-less TWC unplug with the car already out of BLE range: the early BLE restore fails (limit still held = "departing"). TeslaMate keeps reporting inside the radius. 10 policy cycles of `applyChargeLimit(50)` (vin None) 25 s apart through the queue, plus TeslaAPI's own policy-wide apply each cycle (rate limiter cleared) as if VehiclePriority had fallen through. | No `charging-set-limit` tried over BLE, no Fleet `set_charge_limit`, no wake on either channel, no Fleet `vehicle_data` read during the cycles; `isHome` False throughout. After BLE has been gone 5 min: exactly one Fleet `set_charge_limit` with percent 80 (the restore); 10 more cycles add nothing; the only Fleet POST ever is that one. |
| `test_plug_in_on_a_vin_twc_comes_home_with_one_apply` | Parked unplugged (startup BLE read says unplugged -> not home); plugs into a VIN-reading TWC. | home; one arrival; exactly one BLE `charging-set-limit 50` across two later policy cycles. |
| `test_vin_less_single_candidate_plug_one_apply` | Same, VIN-less TWC, car asleep (no pilot read): the single-candidate rule. | `vinForTwc` = V1; home; one arrival; one set-limit 50. |
| `test_vin_less_two_candidates_ble_pilot_one_apply` | V1 awake (pilot 47 = TWC offer, ACSingleWireCAN), V2 in range asleep. | attributed to V1 by the pilot; V2 stays not home, never woken or sent anything; one arrival, one apply to V1. |
| `test_vin_less_ambiguous_plug_applies_to_nobody` | Two cars asleep in range. | no attribution, both not home, no arrival, no wake, no set-limit. |
| `test_supercharger_telemetry_plugged_is_not_home` | Fleet + TeslaMate, no BLE. TeslaMate `plugged_in` true 30 miles away. | not home, no arrival, no Fleet POST, no `vehicle_data` read over 3 policy cycles. |
| `test_unplug_restores_over_ble_at_once` | Home on a VIN TWC with 50 held; unplug in range. | BLE `charging-set-limit 80` in the unplug pass; saved [80, -1]; no Fleet; nothing more in 10 min. |
| `test_replug_cancels_the_pending_remote_restore` | (a) unplug out of range, back and replugged after 3 min; (b) unplug, fallback queues the remote restore, replug + pass before the worker runs. | (a) no Fleet `set_charge_limit` over the next 15 min; (b) the queued `remoteOnly` restore is gone after the arrival pass, and no Fleet `set_charge_limit` follows. |
| `test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it` | Asleep, plugged, VIN-less TWC; 10 min after startup. | presumed; no BLE `wake` / `state`, no Fleet POST or `vehicle_data`; car still asleep. Then `startCarsCharging(_chargeVIN())` -> one BLE wake + `charging-start`. |
| `test_startup_wake_finds_the_car_unplugged_and_sends_nothing` | Asleep, unplugged; first policy apply wakes and reads. | not home after the read; no set-limit; later cycles send no wake, no set-limit, no Fleet. |
| `test_startup_wake_finds_the_car_plugged_and_starts_charging` | Asleep, plugged, VIN-less TWC. | the policy apply's read makes it home and sets 50; `charging-start` goes to it; no Fleet. |
| `test_gen2_steady_00_after_link_does_not_block_startup_charging` | Real TWCSlave: 03 for 120 s after the link, then a steady 00 for 15 min with the car still plugged. | still presumed (no unplug inside the link grace), no wake before charging; then `charging-start` and the apply reach it. |
| `test_ble_silent_umc_car_with_telemetry_inside_radius_is_home` | BLE-paired car out of BLE range on a mobile connector; TeslaMate plugged_in + inside. | home on evidence (`isPluggedHome`), and `TeslaAPIController.allEVSEs` lists it. |
| `test_no_gps_source_plug_unplug_cycle_end_to_end` | BLE + VIN-less TWC only, no TeslaAPI module, no telemetry. | plug -> home -> 50; unplug -> BLE restore 80; an hour away; replug -> attributed, home -> 50. BLE set-limits exactly `["50", "80", "50"]`. |
| `test_fleet_only_unplug_one_remote_restore_plug_one_remote_apply` | No TeslaBLE module, Fleet token, VIN TWC. | unplug -> one Fleet restore (80) right away, nothing more in 10 min; replug -> one arrival and one Fleet apply (50). |
| `test_departing_car_is_never_presumed_present` | Unplug out of range and drive away; a startup-style `nominate(None)`; fallback restore; back in BLE range parked unplugged, another startup-style check (BLE reachable, read unplugged). | `isHome` False at every step; once back in range: no wake, no set-limit, no Fleet POST over 3 policy cycles. |

The test names and behaviours follow the brief; I added no scenarios and dropped none. No scenario as written contradicted the spec.

### Checked that the scenarios can fail

Each mutation below was applied to the library one at a time, the scenarios were rerun, and the change was reverted (`git status` clean afterwards):

| Mutation | Scenarios that fail |
|---|---|
| TeslaBLE policy-wide apply ignores `isHome` | 2026-10-11, two-candidates, ambiguous, startup-unplugged, departing-never-presumed |
| `hasRemoteChannel` always False | 2026-10-11, replug, fleet-only, departing-never-presumed |
| `LINK_GRACE = 0` | gen2 steady 00 |
| `pickPluggedCar` never picks | single-candidate, two-candidates, no-GPS cycle |
| weak plugged evidence without "here" | supercharger |
| the BLE probe reads the charge state of an asleep car | startup-asleep |
| no immediate remote restore for a car without BLE | fleet-only |
| no arrival handler | replug |
| arrival also from presumed | VIN TWC plug, single-candidate, two-candidates, fleet-only |
| BLE-gone fallback at once | 2026-10-11, replug, departing-never-presumed |
| no early BLE restore on unplug | unplug-restores-at-once, no-GPS cycle, fleet-only |
| TeslaBLE broadcast goes to nobody | startup-asleep, startup-plugged, gen2 |
| TeslaAPI policy-wide apply ignores `atHome` | supercharger (2026-10-11 still passes: discovery on wake and the car's limit already being 50 hold it) |
| `_cancelRestore` a no-op | none: see concern 1 |

## Library fixes

None. All 16 scenarios passed against `fc880f9` once the rig was right; every failure on the way was in the test rig (TWC debounce timing, settings entries missing `chargeSessions`, the 300 s reach window, a probe skipped right after a departing record ended).

## Branch gate (step 3), exactly as given

1. `<PY> -m pytest tests/unit -q` -> **1113 passed, 1 warning** (baseline 1097 + 16 new; the warning is present at baseline too, 1097 passed with 1 warning when the new file is deselected). 0 failed.
2. `<PY> -m black --check $(git diff --name-only presence/2-charge-limits -- lib)` -> **16 files would be left unchanged** (clean). The new test file is black-clean as well.
3. `git diff presence/2-charge-limits -- lib | grep -nE '^\+.*log.*(oken|Bearer)'` -> **no hits** (exit 1). Nothing to review; no added log line mentions a token.
4. `git grep -nE 'ARRIVING|AWAY_AFTER_FAILED_PROBES|_failedProbes|_timeoutHome|presenceSources' presence/3-plug-presence -- lib` -> two lines, both the allowed deprecation warning in `VehiclePresence._warnPresenceSources`: line 238 (the `"presenceSources" in vehicle` check that triggers it) and line 240 (the warning string). Nothing else.

## Concerns (minor; none blocks the branch)

1. **`_cancelRestore` on arrival is redundant on the tested paths.** The arrival's per-VIN apply has the same queue key `("applyChargeLimit", vin)` as the pending remote restore, so `VehicleCommandQueue.put` already replaces it. The replug scenario proves the outcome (no restore is sent), not which mechanism did it. The cancel still matters when the arrival queues nothing (`lastChargeLimitApplied == 0`, before the first policy evaluation); `test_presence_handlers.py` covers that case at unit level.
2. **A departed car's last location fix stays "inside".** `_inside` isn't refreshed while a car is not home (departing probes are BLE-only, by design: no location polling). So a car that drove off with no telemetry stays in `broadcastVINs()` as a VIN-less broadcast candidate on its stale inside fix. The consequences are small: TeslaAPI won't wake it (`atHome` is False), TeslaBLE's start fails out of range, and a Fleet charge-start broadcast may cost one `vehicle_data` read before discovery or `atHome` stops it. No command reaches the car. I dropped an assertion the advisor had suggested (`V1 not in broadcastVINs()` after departure), because the spec's candidate rule ("inside the radius or reachable over BLE") doesn't clearly exclude this case. One option would be to clear or age `_inside` when a car leaves. Not changed.
3. **TeslaAPI `_discover` treats a cached `chargingState` as live whenever a telemetry feed is live.** That's correct if TeslaMate publishes `charging_state` (it does), but a feed that publishes location and `plugged_in` without `charging_state` would make a stale Fleet `Disconnected` count as an unplug read. I hit this only because the rig's first TeslaMate fake didn't publish `charging_state`; the rig now publishes it alongside `plugged_in`. I looked for a library bug in the related ordering question (a weak "plugged" applied before the same read's location) and found none: `CarApiVehicle.update_vehicle_data` reports location before plug itself.
4. **One skipped probe after a departing record ends.** When a due departing probe finds nothing held, `runPass` ends the record and `continue`s without probing, and it has already set `_lastProbe`. So a `nominate(None, "startup")` that lands in that pass, or within 60 s of it, doesn't probe that car. This is harmless (the next nomination probes it), and the scenario works around it.
5. **The test stubs one layer lower than the brief said** (process boundary, not `sendCommand`/`probePresence`/`_fetch_state_json`); see above for why.
