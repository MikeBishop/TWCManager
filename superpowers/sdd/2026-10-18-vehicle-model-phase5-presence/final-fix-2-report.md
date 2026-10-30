# Phase 5 final fix 2: report

Branch vehicle-model/phase5 in scratchpad/wt-vm5, cf89bf5f → c0de62bb (6 commits, not pushed). File refs by name (review refs were pre-restack).

| Commit | What |
|---|---|
| 0614063f | F1: home only from a seen position |
| b40be126 | F3: BLE charge read only for a car known awake (+ parity harness ping) |
| 90e3e5a2 | F4 + F5: heardFrom bool; withdrawOffers zeroes the offer map |
| 5ed4fb28 | F6 + F7: FT doc clause; "not here" residual pinned and sentence removed; checkConfigs cut; home doc clause |
| 1d426a3e | Size cuts |
| c0de62bb | F2: Fleet asleep hold + re-check cadence; scenario 18 parity edit; CHANGELOG/TeslaBLE doc |

Every commit before c0de62bb passes the suite (2253/2257/2258/2260/2260 passed, 1 xfailed each, run with `-n 4`). At c0de62bb the official command gives **2262 passed, 1 failed, 1 xfailed**. The one failure is the stop-and-report row below.

## Finding 1: home from a retained copy
- **Change:** `Presence.learnHome` returns False unless `lat.seen and lon.seen`. This covers every path that moves home: `recordVehicleVIN` and the `noteObservation` lat/lon hook both go through `learnHome`. The only other `setHomeLat` is the user's Settings button. Docs: PolicyCustomization.md says a retained copy never counts.
- **Test:** `test_presence.py::test_a_retained_position_never_moves_home_at_a_vin_read` runs through `recordVehicleVIN` with `seen=False` lat/lon observations.
- **Mutation:** dropping the `seen` clause fails the test.

## Finding 2: Fleet asleep hold (option a)
- **Change:**
  - `Provider.online(vehicle)`: a free awake check, default None.
  - `_TeslaAPIProvider.online` wraps `canCommand` + `onlineState` (the cached free GET, or a fresh telemetry state). `stopCharging` now uses it, so its gate is not duplicated.
  - `Run.runAttempt`: after the read and its SATISFIED check, a non-local, no-wake, non-stop attempt whose `provider.online(vehicle) is False` returns `O.ASLEEP`. That is the existing BLE hold outcome: `heldAt` is set, and nothing is sent or blind-retried.
  - `Reconciler.plan`: `_asleepCheckDue` makes a cloud ASLEEP hold re-plan after `HOME_ASLEEP_SECS` (900) at HOME and `AWAY_ASLEEP_SECS` (1800) otherwise. It never does so when `Presence.covered` (a live feed for the car's syncSource). Otherwise the hold keeps the BLE rules: re-plan only on newer evidence, and repeated asleep readings don't re-plan.
  - The two numbers and `covered()` live in `Presence.py`, so Phase 6's `Watch.DEFAULTS` and `notWatched` can import them.
  - CHANGELOG and Vehicle_TeslaBLE.md now state the rule for both channels and give the cadence.
- **Why the check is in the provider, not only `asleep(vehicle)`:** in scenario 18 the read is skipped (the TeslaMate limit is fresh), so no online check ran. The reviewer's `asleep(vehicle)` gate held nothing, and (0,0,2) stayed. `provider.online` reuses the read's cached answer, or makes the one free GET.
- **Tests:** `test_sleeping_car.py`:
  - `test_a_fleet_lowering_to_a_car_found_asleep_holds_and_checks_each_15_min`: 4 online GETs in an hour at home, no paid request, then the command once the car is online.
  - `test_a_fleet_restore_to_a_car_away_and_asleep_is_checked_each_30_min`: 2 GETs in an hour.
  - `test_a_live_feed_replaces_the_online_checks_of_a_car_held_asleep`: 0 requests and one hold log line in an hour, then the command on the feed's `online`.
  - Parity scenario 18 is renamed `test_fleet_only_restore_to_a_car_found_asleep_is_held` and now asserts (0,0,0) with no commands.
- **Mutations:**

  | Mutation | Tests failed |
  |---|---|
  | Hold disabled | 3/3 |
  | Re-check disabled | 2/3 |
  | Home cadence 1800 | 1 |
  | Away cadence 900 | 1 |
  | `covered()` always False | 1 |
- **STOP AND REPORT:** parity row 17b `test_vanished_car_restore_with_fleet_is_bounded` moves too. It is the same ruling and the same shape: a restore to an asleep Fleet-only car, here away. Its paid count goes from (0,0,2) to (0,0,0), and `commands == ["set_charge_limit"] * 2` becomes `[]`. Its `paid[2] <= 2` bound still holds. I left it unedited, so it fails at c0de62bb. The proposed edit is one line: `assert commands(requests_mock) == []`, plus the comment "the free online check holds the restore". The trace shows a hold at t=60 s, then a re-check every 1800 s, all free. No other parity count moved.
- **The asleep-hold Fleet cost from the review is gone:** while asleep, an away Fleet-only car with no telemetry gets one free GET every 30 min, not every 5.

## Finding 3: scan-only ping answer
- **Change:**
  - `pick.fits`: BLE charge read only when `asleep(v, now - REACH_WINDOW) is False`.
  - `checkPlug`: a ping answer with `asleep(v, now - REACH_WINDOW) is not False` returns True (plugged, the fail-safe side).
  - I used the REACH_WINDOW `lately` rather than the review's bare `asleep(v)`. With no window, a car seen awake an hour ago still reads as not asleep after a scan-only answer, and the read could wake it. The tests cover both cases.
  - `runAttempt` is untouched. Docs: the PolicyCustomization and CHANGELOG plug-check sentences.
- **Tests:** `test_presence.py::test_an_attribution_never_reads_a_car_the_scan_alone_answered_for[False/True]` and `test_a_plug_check_keeps_a_car_the_scan_alone_answered_for[False/True]`.
- **Mutations:**

  | Mutation | Tests failed |
  |---|---|
  | Old code in fits | 2 |
  | Old code in checkPlug | 2 |
  | `is False` without `lately` | 1 |
  | `is not False` without `lately` | 1 |
- **Parity harness change (flag):** `realBle(ping=True)` was a bare True that never reported sleep status. Real VCSEC always reports it. With the fix, 5 parity rows broke on that stub: the BLE departure restore, the no-GPS plug/unplug cycle, the two-candidate pilot, the returning car on an unnamed Gen2, and attributed-before-policy. All of them expected a BLE read after the ping.
  - I changed the stub so that `ping=True` also observes `state online` from TeslaBLE, which is VCSEC's awake answer. The docstring says so.
  - With that, the whole suite passed and no parity count or assertion moved. The scan-only tests use `ping=lambda vin: True`.
  - This is a harness change, not a count change. Tell me if you want it as a per-row callable instead.
  - It is folded into b40be126 so that commit is green. Its message does not mention the harness.

## Finding 4: heardFrom
- **Change:** `TWCSlave.heardFrom = False`, set to `True` at the first reply. The comment reads "Set by the first reply".
- **Test:** `test_control_tick.py::test_restart_with_a_car_charging_never_offers_zero` now asserts `heardFrom is False` and then `is True`.
- **Mutation:** the old timestamp code fails it.

## Finding 5: withdrawOffers
- **Change:** `self.offered = dict.fromkeys(self.offered, 0)`, not `{}`. `B.whyQuiet` tests `.get(key) == 0`, so an empty map would make every car look offered power, which is the opposite of the fix.
- **Test:** `test_control_tick.py::test_a_withdrawal_leaves_no_car_offered_power`.
- **Mutations:** removing the line fails it, and `= {}` fails it too.

## Finding 6: FT config check doc
- **Change:** Vehicle_FleetTelemetryMQTT.md says the check covers every car on the Fleet account, so a car you don't stream warns too, once each time TWCManager starts.
- **Test:** none; this is a doc clause. The warning is once per start because the claim status holds it.

## Finding 7: "not here" residual
- **Not reproducible:**
  - `presentVehicles` excludes NOT_HOME cars and `applyPolicyLimit` skips departed ones, so an away car never gets a policy desire.
  - A restore is exempt from `inapplicable`, so a failing restore never logs "not here".
  - I traced BLE-only, Fleet and Owner shapes over 9 h with policy 50, 80 and none: 0 lines.
- **Change:** the sentence is deleted from PolicyCustomization.md.
- **Test:** `test_presence.py::test_a_failing_restore_to_an_away_car_logs_no_not_here[50/80]`: three hours, every BLE restore failing, at least 6 runs, and no "not here".
- **Mutation:** dropping `attempt.restore` from `inapplicable`'s exemption gives exactly the documented repeat, and fails 2/2. Mutating `presentVehicles` alone is masked: the restore set after it wins the pass.

## Finding 8: size cuts

| Cut | Lines |
|---|---|
| `checkPlug` feed read via `telemetryPlug(v, since, seen=True)` with `:=` (pinned by `test_a_retained_redelivery_inside_the_wait_is_no_answer`; mutation dropping `seen=True` fails it) | −1 |
| `update_charge` comment | −3 |
| Reconciler re-arm note | −1 |
| `checkConfigs` debug line | −1 |
| `plugCheckDue` text inline | 0 (not taken: black expands the call to 9 lines, +7) |
| Total | −6 |

## Finding 9: PR notes
- `.superpowers/sdd/2026-10-18-vehicle-model-phase5-presence/pr-notes.md` is rebuilt from the final code. The brief named `.superpowers/pr-drafts/pr-notes.md`, which doesn't exist; the stale file was the sdd one.
- `.superpowers/pr-drafts/pr-phase5.md` is written in #710's style. It covers the Fleet-only driveway shuffle cost and states the target miss plainly.
- Numbers:
  - main bd5a7603: 23,472
  - Phase 4: 26,534
  - this PR: 26,447, which is −87 vs Phase 4 and +2,975 vs main
  - target 26,140: missed by 307
  - tests: 2,263 once row 17b is updated
- **Gap:** no CHANGELOG line covers the Fleet Telemetry field mapping or the config check. The PR draft takes them from the code; I didn't add one because it was out of scope.

## Lib
26,417 → 26,447 (+30). Per finding:

| Finding | Lines |
|---|---|
| F1 | +1 |
| F3 | +2 |
| F4 + F5 | +1 |
| F6 + F7 | −1 |
| Cuts | −5 |
| F2 | +32 |

The cuts offset everything except F2's hold. F2 is spread over: provider `online` (+4 base, +2 TeslaAPI net), Run (+4), Reconciler (+15), and Presence constants and `covered` (+8). `covered` and the constants are meant to be shared with Phase 6.

## Follow-up to the coordinator's ruling (2026-10-21)

These steps were done after the report above was written. The history was rebased and is still linear and unpushed.

- **Row 17b edited** (amended into the F2 commit) to `commands == [] and paid == (0, 0, 0)`. No other parity edits.
- **CHANGELOG:** one doc commit adds two lines, one for the Fleet Telemetry field mapping (with the typed values and the `minimum_delta` advice) and one for the config check. Rewriting the pre-cf89bf5f FT commits would have been messy, so this is a separate commit.
- **b40be126 reworded** (now 116ce53f): its message now mentions the realBle(ping=True) harness change.

New SHAs, cf89bf5f..vehicle-model/phase5:

| SHA | Commit |
|---|---|
| 0614063f | F1 |
| 116ce53f | F3 + harness |
| 0c410886 | F4 + F5 |
| e5acac20 | F6 + F7 |
| 1e616dda | cuts |
| 2dcb08e7 | F2 + scenario 18 + row 17b |
| f0788013 | FT CHANGELOG |

**Suite at the tip** (f0788013, official command): 2263 passed, 1 xfailed. Lib stays 26,447.

## Re-review round (2026-10-21)

These fixes are folded into the fix commits they belong to, plus one new commit. History is linear and not pushed. Lib went 26,447 → 26,464 (+17); in total it is 26,417 → 26,464 (+47).

1. **An "offline" answer re-planned on every heartbeat** (Reconciler).
   - Change: the asleep gate now reads `Presence.asleep(vehicle, rec.heldAt or 0) is not False`, so only a sign of life since the hold re-plans.
   - Test: the 15-min Fleet test is parametrized over `asleep` and `offline`.
   - Mutation: going back to `Presence.asleep(vehicle)` fails the `offline` case.
2. **The offer map lost the car at a 00.**
   - Change: `Gen2TWC.heldKey` is the car `vehicleAt` its TWC (base `EVSEInstance.heldKey = None`). `distributeEVSEPower` maps each held car to its TWC's offer before the served and fan-out keys, which still win.
   - The coordinator's suggestion, keeping the key only while the check is pending, was not enough. The probe showed the wake landing right after the check cleared `edgeAt`, at t = 30 s. Keeping `vehicleKey` itself broke 8 tests, so the fix lives only in the offer map.
   - Test: `test_presence.py::test_a_car_its_twc_still_holds_at_00_is_offered_the_twcs_nothing`.
   - Mutation: going back to the previous TWCMaster fails it.
3. **Idle 0 A row's ping.** The row's ping now observes `state asleep` from TeslaBLE and returns True.
   - Without fix 2, the row fails: BLE `wake` and then the limit.
   - With fix 2, the row passes.
4. **Home Assistant's polled lat/lon could move home.**
   - Change: HA observes them `seen=False`. That costs +2 lines; the learnHome source check would have wrapped to more.
   - Test: `test_presence.py::test_a_home_assistant_position_never_moves_home_at_a_vin_read`.
   - Mutation: `seen=True` fails it.
5. **No hold when there is no online check.** When `provider.online()` is None and `asleep(vehicle)` is True, the attempt holds as well.
   - Test: `test_sleeping_car.py::test_a_cloud_command_with_no_online_check_holds_for_a_car_known_asleep`. It uses a Home Assistant provider with TeslaMate reporting asleep: no HA call while asleep, and one call once the car is online.
   - Mutation: `awake is False` only fails it.
6. **PR draft and notes:**
   - 42 carried, 59 new, 101 total.
   - One free GET in 15 rows.
   - The idle row's change.
   - Tests 2,267.
   - Lib 26,464 (−70 vs Phase 4, +2,992 vs main, 324 over target).
7. **CHANGELOG "except while its charger is offered 0 A":** now true; no text change needed.

**Parity request counts, before → after** (per-row request counts compared with the reviewer's counting plugin across all 113 tests in the file): only one row changed.
- `test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise`: BLE runs `[charging-set-limit 80]` → `[]`, free GETs 6 → 0, pings 7 → 7, paid (0,0,0) → (0,0,0). The cause is fixes 2 and 3: the asleep car keeps its TWC's 0 A offer, so the raise is opportunistic and is held.

**SHAs:**

| SHA | Commit |
|---|---|
| 2f50f594 | F1 + HA polled position |
| 3769153a | F3 |
| c573fd29 | F4 + F5 |
| c5de0cad | F6 + F7 |
| 03cbdd23 | cuts |
| a49a2e6c | F2 + offline + no-check hold |
| 4e7e0420 | FT CHANGELOG |
| cc227a6f | Gen2 held car on its TWC's offer + idle row ping |

**Suite:** every commit is green (2254/2258/2259/2261/2261/2266/2266 passed, 1 xfailed, run with `-n 4`). At the tip, the official command gives 2267 passed, 1 xfailed.

## Re-review of cc227a6f (2026-10-21)

Both fixes are folded into the tip commit, which is now **36e69be6**. The earlier commits are unchanged.

1. **Item 2 regression: a sleeping car's raise was held forever.**
   - Change: the offer map keeps a held car only `if w or remaining_watts < p.minPower`, i.e. when its TWC got power or none was left for it.
   - New parity row `test_a_sleeping_car_at_00_with_power_available_is_woken_for_a_raise`. Setup: 32 A to share, the named car asleep at 00 with max 0 A, limit and battery at 50, then policy 50→80 for 30 min. Result: BLE `wake` then `charging-set-limit` 80, paid (0,0,0).
   - Mutation: dropping the condition fails the row (no BLE runs).
2. **heldKey kept a car that had moved.**
   - Change: `Gen2TWC.heldKey` returns the key only while the car's `twcVin.at` is later than its drive start and its outside mark, as `Presence.twcVinAt` does.
   - Test: `test_presence.py::test_a_twc_at_00_stops_holding_a_car_that_moved_since_it_was_named[driveStart/outside]`.
   - Mutation: dropping the time check fails both cases.

**Parity:** I compared request counts for all 113 existing rows between cc227a6f's lib and the new lib, and none differ. The one new row is the case above. Rows: 102 (42 carried, 60 new).

**Suite at 36e69be6** (official command): 2270 passed, 1 xfailed.

**Lib:** 26,464 → 26,471 (+7). Against the bases: −63 vs Phase 4, +2,999 vs main, 331 over target.
