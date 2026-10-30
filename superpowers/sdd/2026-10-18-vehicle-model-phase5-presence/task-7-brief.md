### Task 7: Docs, changelog, PR notes; whole-branch check (expected lib Δ 0)

- [ ] **Step 1: Docs (F17).**
  - `docs/PolicyCustomization.md:49–80`: the at-home rules and first-fix seeding.
  - `PolicyCustomization.md:226–228, 277`: the counts.
  - `docs/Settings.md:14`: home is set from a car at a VIN-reporting TWC, or here.
  - `docs/modules/Vehicle_HomeAssistant.md:88–93`.
- [ ] **Step 2: CHANGELOG.** The radius default; how home is set; the removed hint endpoints; the Gen2 plug-session end; the new INFO lines.
- [ ] **Step 3: PR notes:** (a)–(m), one sentence each.
  - Call out (d): the 5/20/45 reads stay.
  - Call out (h): the reversed Phase 3 ruling.
  - Call out (b): presumed cars resolved on the paid path, close to main.
  - Call out the Gen2 filters: the evidence and its n=2 caveat.
- [ ] **Step 4: Whole-branch checks.**
  - Run every grep and the full suite.
  - `git diff 57dcea94 -- tests/unit/test_command_path_parity.py` shows only new rows, `:1306` and the `realBle` ping stub.
  - Record the lib total.
- [ ] **Step 5: Commit.** `git commit -m "Document event-based presence"`

**Per-group fates of the presence-branch tests (F18):**

| Branch file / group | Fate |
|---|---|
| `test_plug_presence_scenarios.py` (19) | All ported as parity rows (Tasks 3–5) |
| `test_presence_attribution.py` (10) | Ported as is (Task 5) |
| `test_vehicle_presence.py` TestStates 6, TestPlugEvidence 15, TestLocation 2, TestRecords 1, TestHomeProof 1 | → `test_presence.py` Task 2 rows (states, plug mapping, radius, marks, `twcVin`) |
| TestProbes 2 | → `test_a_presumed_car_is_pinged_first…` and `test_driving_inside_is_presumed_even_with_ble_contact` |
| TestVinLessAttribution 10 | → Task 5 rows (single, pilot, ambiguous, T12 only-candidate, non-Tesla) |
| TestDepartingRestore 3, TestRemoteRestoreBackoff 2 | → parity `test_unplug_restores_over_ble_at_once`, `test_ble_gone_five_minutes…`, `test_ble_only_departure_never_pays`, `test_fleet_only_failed_remote_restore…` |
| TestReturnPluggedIn 2, TestDepartAndReturn 1 | → `test_2026_10_12_*`, `test_a_plug_or_a_newer_arrival_cancels…` |
| TestDiscoveryWithAHeldLimit 2, TestDiscover 3, TestDiscoverEvidenceOrder 2 | → `test_applicability_every_cell` and the startup parity rows 9–11 |
| TestHeldWhileNotHome 3 | → `test_policy_wide_apply_skips_a_departed_car…` and the vanished-car rows (kept) |
| TestWeakPlugMaxAge 3 | **Dropped**: superseded by stickiness (final model); `test_home_is_sticky_while_plugged_or_asleep` |
| TestBroadcastVINs 4 | → `test_candidates_for_a_broadcast_are_only_cars_base_reached` |
| `test_teslaapi_presence.py`: DiscoveryOnWake 5, DiscoveryEvidenceOrder 2 | → the startup rows and `test_presumed_fleet_only_car_*` |
| ChargeTargets 4 | → `test_start_and_amps_need_a_plug_here` |
| ReconcileHomeLocation 2 | → `test_home_is_learned_only_from_a_twc_named_car…` (Q5) |
| CountsFollowPresence 3, HomeRadius 2 | → `test_counts_include_presumed_cars`, `test_home_radius…` |
| WakeOnlyForAHomeCar 4 | → `test_wake_only_a_home_car` (x4) |
| AtHomeFollowsPresence 3 | → `test_last_at_home_is_true_only_for_home` |
| `test_teslable_presence.py`: ContactReporting 2 | → `test_ble_absence_only_from…` |
| SkipsAwayVehicles 2, ChargeTargets 3 | → `test_applicability_every_cell` |
| plug derivation 2 | → `test_charging_state_maps_to_plug_values` |
| DiscoveryOnWake 5 | → startup rows |
| every-channel departing regression 1 | → `test_policy_wide_apply_skips…` |
| `test_twcslave.py`: TestPlugDebounce 9, TestUnplugNeedsAPluggedRun 7 | → `test_gen2_unplug.py` |
| TestPlugVIN 5 | `plugEnded` cases dropped (`vehicleAt` replaces `plugVIN`); non-Tesla → `test_a_non_tesla_plug_departs_nobody`; stale `lastVIN` → `test_vehicle_key_names_the_car_after…` |
| TestPresenceTriggers 2 | → `test_power_start_still_queues_check_charge` and the 5/20/45 reads (kept) |
| TestChargeVIN 3 | → `vehicleKey` tests (Task 4) |
| `test_presence_handlers.py` 3 | → `test_arrival_is_one_decision…`, `test_ble_only_departure_never_pays`, the departing-with-nothing-held case in `test_applicability_every_cell` |
| `test_presence_sources.py` 7 | → Task 2 mapping, radius and plug-with-fix rows |
| `test_homeassistant_presence.py` 5 | → `test_policy_wide_apply_skips…`, the HA-coordinates rows, `test_counts_include_presumed_cars`, `test_home_radius…` (default and override) |
| `test_teslaapi_controller_presence.py` 1, `test_teslaapi_controller.py` 2 | → `test_endpoints_list_cars_plugged_here…` and E3 |
| `test_twcmaster.py` 2 | → `test_charge_stop_keeps_twc_vin…`; the per-VIN cancel already exists |
| TeslaMate/telemetry 2 | → `test_charging_state_maps_to_plug_values` (odd payload is unknown) and `test_marks_record_events_when_observed…` (a retained value is a read, not an event when unchanged) |

---

## Parity rows traced (F4), under the Task 2/3 definitions

| Row | Car evidence | Presence → cell | Count/timing |
|---|---|---|---|
| 2 `test_ble_only_limits_never_wake_to_lower` | fix inside, no `shiftState`, no driving | HOME (inside and parked), not plugged, `L == -inf` → apply `SEND`; HOME, so no ping | unchanged |
| 4 `test_fleet_only_raise_costs_the_same` | fix inside; Fleet asleep | HOME, `L == -inf` → wake (a raise, `allowWake`) → read (Stopped, inside) → `SEND` | (1,1,1) unchanged |
| 5 `test_ble_plus_fleet_waits_five_minutes` | fix inside; BLE answers None | HOME → BLE ×2 fail (command failures write no `bleReach`, F9) → paid after `PAID_AFTER` | (0,0,1); `len(b.runs) == 2`; timing unchanged |
| 6 `test_ble_plus_fleet_stop_waits_a_minute` | stop | never gated | unchanged |
| 17a/b vanished car | fix outside newer than H | NOT_HOME → restore `SEND` | unchanged |
| 25 `test_vinless_rate_goes_to_the_plugged_in_car_only` | VIN Disconnected (no prior plugged: no unplug mark), VIN2 Charging | VIN HOME not plugged (not in the fan-out); VIN2 `pluggedHere` | `[VIN2]`, `[10]` unchanged |
| 26 restart, asleep | TeslaMate Complete, fix inside | `plugIn` → HOME plugged | BLE run list unchanged; 0 requests |
| pure Gen2 (:496) | no attachments | broadcast audience empty (F11) | unchanged |
| `test_anonymous_stop_fans_out_as_main` | two Fleet cars Charging inside | HOME plugged; broadcast reaches both (TeslaAPI-attached) | unchanged |
| mode-2 rows (`onTwc`) | `twcVin` with the TWC at 0x00 in setup → `twcVin` not counted (F2); fix inside → HOME | start needs plugged: TeslaMate Charging inside | unchanged |

**No existing row is expected to move.**

---

## Line budget

| Task | Out | In | Expected Δ (range) | Running total |
|---|---|---|---|---|
| 0 config one-liners | 53 blocks, 17 if-pairs | (black re-wraps ≥ 6) | **≈ −164** (−160..−168) | ≈ 26,326 |
| 1 logging | — | paid classifier + line 10, telemetry log 6, report level 1 | **≈ +18** (+15..+22) | ≈ 26,344 |
| 2 presence from events | TeslaAPI home/radius 56, `vehicleIsDefinitelyHome` 36, `update_location`/`locate` 25, `atHome` 3, helpers 25, HA 52, Targets presence half 66, `_scheduleBlocksStart` + provider branch 19 (≈ 282) | `Presence.py` ≈ 125 (`noteObservation` + marks 30, mapping/narrowing 18, current state 12, `presence` 12, `twcVin` bound 6, `leaving`/`arriving` 4, `inside` 10, `candidates` 14, `homeCars`/`learnHome` 14, `why` 5), `Vehicle` mark/hook 9, registry hook + `observeTwcVin` clear 4, fields + mappings ≈ 21, Targets filters ≈ 15, delegations + ladder on `inside` ≈ 20 | **≈ −88** (−70..−110) | ≈ 26,256 |
| 3 applicability; ping; holds; hints gone | HTTP hints 12, `checkArrival` 5, endpoint gate 5, `_telemetryPluggedIn` 5 | `applicable` 32, `ping` + `_runPing` 14, `Run.py` 6, `beforeWrite` past limits 8, hold + budget + `settledAt` 14, record fields 4, `lastObservedAt` 2, `_restoreDeparted`/`applyPolicyLimit` 6, `onArrival` + calls 8, `telemetrySaysPlugged` 5, logs 4, `checkCharge` 1 | **≈ +77** (+65..+90) | ≈ 26,333 |
| 4 Gen2 unplug (on `TWCSlave`) | charge-stop end 1, `vehicleKey` branch 3 | `unplugStep`/`linkReady` + constants ≈ 30, `_unplugged` + T12 ≈ 12, wiring 3 | **≈ +41** (+35..+50) | ≈ 26,374 |
| 5 attribution; fan-out | `pluggedCars` + imports 26, `anonymousCars` 6, Gen3 loop 22, `CORRELATE_WINDOW` 2 | verbatim module 71, single-car guess 8, `attribute` 22, task/queue 6 | **≈ +51** (+45..+60) | ≈ 26,425 |
| 6 docs | — | — | 0 | **≈ 26,425** |

- **Projected end ≈ 26,425** (range ≈ 26,330–26,520): ≈ −65 from BASE. Task 0 is −164, logging +18, and **the presence work (Tasks 2–5) nets ≈ +81**.
- The pre-flight estimated 26,380–26,410. This is higher because of the F11 keeps (the deferral ladder, broadcast audience and HA rule stay), the F2/F3 bounds, and filling every cell. The F16 deletions take back ≈ 24.
- **The gap to main is ≈ 3,245 lines.** Biggest contributors: `Vehicle/Reconcile/` +1,946 (+30 here), `Vehicle/Providers/` +1,346, `Vehicle/Registry/` +870 (+15 here), `HTTPControl.py` +213, `ChargingPoint.py` +211, `VehicleEndpoint.py` +198, `Gen3TWCs.py` +157, `Telemetry.py` +137, `Gen3TWC.py` +124, `TWCMaster.py` +118, `VehicleCommandQueue.py` +96, `TeslaMateVehicle.py` +90, `ControlTick.py` +75, `TeslaTokenSlot.py` +74, and `Presence.py` ≈ +225 after this phase.
- Per the roadmap, still above 23,180 means: stop and audit the design (Reconcile, Providers, Registry first) before Phase 6.

## Decisions made in this plan

1. **Presence from events, computed fresh.** The only remembered data is event times (marks), recorded when the observation arrives. Event times beat readings: a repeated Disconnected read is not a departure (F1).
2. **`twcVin` is bounded** (F2): valid only while the point reports a plug, and not after a newer drive start or outside fix. Another VIN at the point clears it.
3. **Holds re-plan on any newer observation, within a paid budget of 4 per desire** (F3). `heldAt` is separate from `settledAt`.
4. **Ties hold** (F8); missing times are `-inf`; no `shiftState` means parked unless driving (F4). Contact never overrides driving (F7).
5. **`bleReach` False only from definitive absence** (F9).
6. **Restores and applies ride the policy pass** (E2), and nothing excludes the restore's own reply (F10).
7. **BASE kept where F11 lists it:** the ladder, `updateChargeAtHome` at power start, the broadcast audience and HA rule, `lastAtHome` for HOME only. Q7's single deferral is withdrawn.
8. **One `candidates()`** (F13). **One arrival per plug-in event** (F20). **One telemetry-plugged predicate** (F16).
9. **BASE Gen3's single-car guess stays decisive** (F12).
10. **The Gen2 rule lives on `TWCSlave` with a strict filter (a)** (F6).
11. **The paid path is BASE's rule** (F20), and held ⇒ presumed plugged for starts (F20).
12. **Task 0 uses `d.get(k) or {}` at the falsy/`None` tests**, which is exact for JSON `null`.

## Pending user decisions

None. All pre-flight findings are applied per the rulings in `sdd/2026-10-18-vehicle-model-phase5-presence/progress.md`.

## Self-review (against 57dcea94)

- **Symbols and hooks.** Every symbol planned for deletion or kept exists at the cited lines.
  - Hooks:
    - `Reconciler.report` :523–537, `beforeWrite` :485, the `settledAt` gate :294–299, `freeFailed` :323–328;
    - `Run.py` `wakeFirst`;
    - `Belief.allowWake` :107–117, `Belief.handsOff` :99–103;
    - `TeslaAPI._request` :306, `is_awake` :1794;
    - `TeslaBLE._fetch_state_json` :613 (the ping seam), scan :1103;
    - `FieldStore._store` (returns the kept observation);
    - `Telemetry.py:277` (`seen=False`, hence `lastObservedAt`).
- **Pre-flight F1–F20**, each applied:
  - F1 unplug event mark;
  - F2 the `twcVin` bound and clear;
  - F3 holds and budget;
  - F4 cells, `-inf`, parked;
  - F5 the ping stub;
  - F6 strict filter (a) and the raise-loop row;
  - F7 driving holds;
  - F8 ties;
  - F9 `bleReach` sources;
  - F10 no exclusion;
  - F11 BASE kept;
  - F12 Gen3 guess;
  - F13 one `candidates`;
  - F14 the paid classifier and a separate arrival hook;
  - F15 deltas;
  - F16 the three deletions;
  - F17 rename, mapping and docs;
  - F18 per-group fates;
  - F19 Task 0;
  - F20 the paid rule, held ⇒ plugged, and one arrival.
- **User decisions:** Q1–Q9, the final model, E1/E2 and the paid fallback are all mapped in Global Constraints and Tasks 2–4.
- **Box rows:** 13:08, 15:18 → 15:21, 15:25:58–15:36:27, the 07:58–08:40 sequence, the 20 s drive and the loop rows (lowering and raise).
- **Interfaces line up:**
  - `noteObservation`, `presence`, `pluggedNow`, `drivingNow`, `leaving`, `arriving`, `candidates`, `homeCars` and `why` are defined in Task 2.
  - `applicable`, `telemetrySaysPlugged`, `ping`, `onArrival` and `lastObservedAt` are defined in Task 3.
  - `unplugStep`/`_unplugged` are in Task 4. `attribute` is in Task 5 and calls `onArrival` once.

---
## Controller addendum (rulings since the plan; all must be documented)
Base for whole-branch checks is now **044e5262** (Phase 4 tip after the Python 3.8 test fix), not 57dcea94. Parity check: `git diff 044e5262 -- tests/unit/test_command_path_parity.py` shows only appended rows plus fixture plumbing (list each non-append hunk in the PR notes with its reason).
Document (docs + CHANGELOG 1.4.0 + PR notes), from progress.md "Ruling" lines:
- Home is learned from a car a TWC names (fresh fix) **or a fix that arrived over BLE**; never from a first fix. A car-only install with no TWC and no BLE must set home on the Settings page (a WARNING says so once). Cars on such an install with no home are never treated as home and are not rated.
- A policy always has a charge limit; "no limit" is a release to the car's own limit, applied like any limit (raise may wake, lowering never). A departure restore is separate: sent wherever the car is, never wakes.
- No wake for a raise (limit, release-as-raise, amps) while the car's point/endpoint is offered 0 A.
- A charging point's own commands (Gen2/Gen3 start, stop, amps) are never gated by presence; only commands addressed to the car are.
- "Plugged" for a car-addressed start/amps: the current plug reading first; a TWC naming the car counts if no newer reading says unplugged; a held car counts when nothing reads the plug; a Gen2 00 alone never unplugs.
- Gen2 unplug: the two filters (max amps > 0 before → 0 on the first 00; live telemetry pluggedIn vetoes), 60 s debounce, link grace, plugged-run guard; the INFO lines (onset, verdict, "TWC x: unplugged, VIN departs"). Evidence caveat n=2.
- VIN-less attribution (Gen2 queued to the background thread; Gen3 never reads BLE), the 00-probe deletion (label (h)), Gen2 attributed plug counts only while the point reports a plug.
- Paid budget counts paid requests actually made; holds never spend it.
- New INFO logging: reconciler outcomes, each paid Fleet request (endpoint + price; never URL/VIN/token), telemetry plug/state/geofence changes.
- Removed endpoints `/api/checkArrival`, `/api/checkDeparture` (404).
- Vehicles page: Presence column; per-car Pending commands (one line each); the per-field summary is gone from the WebIPC debug dump.
- Known residuals for docs: a guest car later on the same TWC can keep a departed idle car HOME (named by its point) until an outside fix or drive start; a VIN rejected during a charge session stays rejected until the unplug; an away car whose departure restore failed may log a RELEASE/NOT_HERE line per policy pass (unconfirmed).
- Size: Phase 5 lib 26,531 → final (record it); main 23,180.
Write PR notes to `.superpowers/sdd/2026-10-18-vehicle-model-phase5-presence/pr-notes.md` (not in the repo). Docs/CHANGELOG commit in the repo. Keep docs plain and user-facing; no ruling IDs.
