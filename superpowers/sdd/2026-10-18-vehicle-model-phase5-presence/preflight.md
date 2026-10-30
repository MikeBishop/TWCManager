# Pre-flight: Phase 5 presence plan (2026-10-18)

Plan: `.superpowers/plans/2026-10-18-vehicle-model-phase5-presence.md`. Checked against code at **57dcea94** (`scratchpad/wt-vm5`), the inventory's user decisions, the "Presence model — final" section and the later bullets (later wins), the unplug evidence, and the Phase 4 constraints. Read-only.

**Verdict: go-with-fixes.** Tasks 0 and 1 can go now (Task 1 needs finding 14). Tasks 2–5 should wait for fixes to findings 1–7, which are about the presence algebra itself. Most of those changes are a few lines of plan text each: define the missing semantics, not redesign.

---

## 1. Task pairs sharing a file or interface

| Pair | Producer → consumer | Conflict |
|---|---|---|
| T0 × T2/T3/T4/T5 | T0 edits `TWCMaster.py` (1223, 1444, 1526–1535, 1997), `HTTPControl.py` (194–201, 495, 696, 1856–1903, 2014), `TeslaBLE.py:115–118`, `Telemetry.py:61–64` | Line numbers cited by later tasks drift by up to about −10. No semantic conflict. Executors should cite by symbol. |
| T1 × T3 | T1 adds the telemetry change hook and says "Logging only: no decision reads anything added here". T3 calls `onArrival` from that hook (pushed `pluggedIn` False → True). | **Conflict.** T1's text forbids exactly what T3 does. Reword T1, or give T3 its own hook. |
| T1 × T3 | `Reconciler.report` at INFO (T1); `beforeWrite`/`plan` (T3) | None. A HOLD's "rules: held …" outcome now logs at INFO on every hold. Fine, given finding 3's re-plan fix. |
| T2 × T3 | T2 produces `evidence`, `presence`, `homeForLimits`, `pluggedHere`, `leaving`, `arriving` and marks. T3 consumes them in `applicable`, `_restoreDeparted` and `applyPolicyLimit`. | T2 never defines what `None` means in `arriving > leaving`, nor "parked" with no `shiftState` observed. T3's HOME-not-plugged cell and its `applyPolicyLimit` filter depend on both (finding 4). T2's H row 4 ("except contact stamped by a restore's own exchange") is half-built in T2 and needs T3 plumbing that neither task budgets (finding 10). |
| T2 × T4 | T4 writes `pluggedIn False` (`Gen2TWC`). T2 counts it as D. T2 rule 1 makes `twcVin` HOME unconditionally, and T4/Q2 keeps `twcVin` alive until the filtered unplug. | **Conflict** (finding 2): a missed unplug pins the car HOME. D is a state, not an event (finding 1). |
| T2 × T4 | T4's `_unplugged` (T12, the "single candidate") uses T2's `candidates()` | T5 later redefines `candidates()` (next row). T12 semantics change between T4 and T5. |
| T2 × T5 | `candidates()`: T2 says "`homeForLimits` when a capability is given". T5 says "inside or reachable, or `homeForLimits`, and not named by a TWC". `TWCSlave.pluggedCars`: T2 rewrites it as a thin call, then T5 deletes it. | Two definitions of one interface (finding 13). The T2 rewrite is throw-away work. |
| T3 × T4 | T4: "No further gates: the loop property comes from Task 3." T3: restores never wake; arrivals happen at plug edges. | **Gap** (finding 6). A raising arrival at a plug edge can wake. |
| T3 × T4 | `VehicleEndpoint._telemetryPluggedIn` (kept in T3) and `Presence.telemetrySaysPlugged` (new in T4) | The same predicate twice (finding 16). |
| T3 × T5 | T5's `attribute` calls `onArrival` for the winner. T3 also calls `onArrival` at "Gen3's rising edge, once the car is named". | A Gen3 guess gets `onArrival` twice. It's idempotent, but pick one. |
| T4 × T5 | After an unplug, T4 clears `twcVin`. At the next 03, `TWCMaster:1346` opens an anonymous session. T5 then queues `attributePlug`, which ends in `onArrival`. | This is the loop path in finding 6. |
| T3 × parity harness | T3's ping "shares `_fetch_state_json`'s runner". The harness `realBle` stubs `_fetch_state_json = lambda vin, kind: None` and records only `_sendCommand_internal`. | **Conflict** (finding 5). In parity the ping never answers. |
| T2/T3 × T6 | T6 rewords `PolicyCustomization.md:59, 226–228, 277` | It misses `:49–80` (the at-home rules and first-fix seeding, changed by (f)) and `Settings.md:14`. |

## 2. Per-task check

| Task | Self-consistency | Deleted symbols exist at 57dcea94 | Callers handled | Notes |
|---|---|---|---|---|
| 0 | Consistent. | All 53 Rule A sites match `scratchpad/find_try.py` (51, plus Kostal and TeslaBLE, which the scanner misses). The 3 left alone are right. All 17 Rule B sites match `find_ifs.py`. | n/a | **Behaviour-identical: verified.** `.get(k, {})` returns a present explicit `null` unchanged, as BASE did. A `null` at the first level crashed with `TypeError` before and `AttributeError` now; both are uncaught at the same line. The Kostal claim holds: `TWCManager.py:171` already needs `config["config"]`. For `or {}`: a present `{}` becomes a fresh `{}`, and nothing aliases these. The one real difference is that `TWCMaster.py:1444` (`recordVehicleSessionEnd`, outside `settingsLock`) now re-assigns `settings["Vehicles"]` on every call. It's the same object and the dict size doesn't change, so it's benign. black wraps at least 6 replacements (OWM 94 columns; `HTTPControl` 495/696/1871/1889/1902 at 97–115 columns). Δ is about −160..−168, at the low end of the range. |
| 1 | `test_free_requests_log_nothing` covers only the list and `vehicles/{vin}`. | n/a | n/a | `purpose` can't identify a paid request: `"read"` covers the free `vehicles/{vin}` too, and Owner API requests (free) use the same purposes (finding 14). Geofence logging belongs in `TeslaMateVehicle`, not the shared path (the plan half-says this). |
| 2 | **No.** H row 5 "`shiftState` `P` or None": does a missing observation count as None? The answer decides HOME vs PRESUMED for every bare fix inside, and parity rows break either way (finding 4). D re-stamps on every read (finding 1). `_restoreDeparted(read=True)` claims "the same paid count as BASE", but the deferral ladder removal makes the 20/45-minute reads real (finding 11). | Yes: `Targets` 19–46/60–78/126–145; `TeslaAPI` 51, 656–714, 1675–1726, 1901–1925, 1961–2008; HA 68–73, 152–162, 553–593; `TWCMaster` 37/202/364–366/1563–1572; `TWCManager` 386–387; `HTTPControl` 558; `TeslaBLE` 177–191 and 488/517/652 (`_noteBleProof`). | **Partly.** Unmapped: `tests/unit/teslatokens.py:146` and `test_teslaapi_wake.py:79` (`car.atHome = True`, now dead); `test_charging_reconciler.py:440–452` (HA `at_home` broadcast, which now changes behaviour: finding 11); the comment at `reconcile_helpers.py:20`. The Step 6 expected-hit list is wrong: `-w atHome` matches the new `Presence.atHome`, and `-w located` matches parity's `install(located=…)` (`:181, 205, 497, 785, 808`). | `atHome(master, attachment)`: does PRESUMED count? Unstated (R21 said "or presumed"). `TeslaAPIProviders.py:61` also reads `statusDeferral`, which the plan doesn't list. |
| 3 | **No.** Review Focus 2's expected "no command while driving" conflicts with H row 4 > M plus E1 when a ping answers (finding 7). The HOLD re-plan rule can't see pushed evidence (finding 3). The PRESUMED column has no "inside, not driving" cell. `test_presumed_fleet_only_car_gets_the_limit_through_the_paid_sequence` reaches the HOME column after its read, where an unplugged car with no marks gets NOT_HERE. | Yes: `TWCManager.py:45, 323–327`; `TWCSlave.py:673–679`; `HTTPControl.py:775–786` (the final `else` at 1123 returns 404 ✓); `VehicleEndpoint.py:170–198`. | Integration test deletion ✓. `test_limit_wiring.py:46` `onArrival(m)` ✓. `test_charging_points.py:116,132` ✓. `test_gen2_idle_minimum.py` ✓. Missed: removing `checkArrival` also drops `master.updateChargeAtHome()` on every power start (`TWCManager.py:325–327`), which is not in (a)–(m). | `beforeWrite` is CHARGE_LIMIT-only today (`Reconciler.py:486`). AMPS attempts never read (`maxAge` None), and a cloud wake runs before the read (`Run.py` `wakeFirst`). The table should say the gate runs on registry state for amps and after the wake for cloud raises and starts. |
| 4 | Mostly. The `beforeMax == 0` → "passes" choice inverts the binding's filter (a) (finding 6). | Yes: `TWCMaster.py:1340` (`_plugSession(slaveTWC, False)`); `Gen2TWC.py:49–51` (the `lastVIN` branch). | Test list omits `test_gen2twc_provider.py` and `test_outcome_desired.py`, which use `_plugSession`/`endPlugSession`. | `vehicleAt` returns a `Vehicle`, while `vehicleKey` returns a key, so `.key` is needed. `observeTwcVin` never clears another car's `twcVin` at the same point (`VehicleRegistry.py:201–240`), so `vehicleAt` can name a stale car (finding 2). |
| 5 | Budget vs "ported verbatim": the reference `PresenceAttribution.py` is 71 lines, against a 45-line budget. | Yes: `ChargingPoint.py:182–190`; `TWCSlave.py:7–16, 121–141`; `Gen3TWC.py:68, 275–297`; `WallConnectorVins.py:168` (calls `_correlate`, kept). | The Gen3 `_correlate` tests aren't named (`test_charging_points.py` ×2, `test_gen3twc_provider.py`, `test_vehicle_endpoint.py`). `test_amps_reconciler.py:166` ✓. | The `pickPluggedCar` pool needs reach or inside, which narrows Gen3's guess (finding 12). |
| 6 | Docs list incomplete (above). | — | — | — |

## 3. Plan vs binding decisions

| Binding point | Plan | Match? |
|---|---|---|
| Presence computed fresh; sticky while plugged or asleep; only movement re-opens it | Rules 1–5 over the newest H/M/D/O times | **Partly.** (i) Rule 1 makes `twcVin` HOME whatever the movement, but the binding says a TWC plug is re-opened by movement too (finding 2). (ii) D is the newest unplugged *reading*, not the last unplug *event*, so a parked-unplugged car at home turns NOT_HOME on any read (finding 1). (iii) `bleReach` False from any transient BLE failure is movement, so a sleeping car stops being sticky (finding 9). |
| Fix inside = PRESUMED; a pushed parked/plugged/asleep confirms | H row 5: inside and parked, with `shiftState` None counted as parked | Ambiguous. If a missing `shiftState` counts as None, a bare fix inside is HOME, contrary to the binding (finding 4). |
| BLE sleep-safe ping as the free first step | `Run.py` ping for a PRESUMED car on the `TeslaBLE` provider; an answer is HOME | ✓ in intent. The parity harness can't answer it (finding 5). |
| Applicability per message; arriving/leaving with drive start as leaving | `leaving = max(D, driveStart)`, `arriving = max(outside, driveEnd)` | The rule matches. D is the wrong quantity (finding 1), `None` is undefined (finding 4), and contact while driving trumps the hold (finding 7). |
| Start and amps need the plug | Table cell, plus "presumed plugged = a held car with no unplug evidence" | Close. The held-means-plugged stand-in brings back the inventory's R14 "held ⇒ present" shape for starts. It's minor, because the cloud read runs first. |
| Restores are ordinary messages that never wake on the paid path | `allowWake` refuses any restore, on every provider | ✓. A raising *arrival* can still wake (finding 6). |
| Two unplug filters | (a) the amps drop; (b) the telemetry veto | Filter (a) treats "already 0" as passing. The binding defines (a) as a drop from >0 to 0 (finding 6). |
| No polling | The hold waits for evidence. `updateChargeAtHome` reads HOME cars only. | **Not as specified**: the `lastSeen` trigger misses pushes and fires on HA/BLE/own reads (finding 3). |
| Paid only after free failed repeatedly, with the existing wait | `freeFailed` unchanged; a missed ping is one free failure | Equivalent to BASE, but one failed ping plus 300 s opens paid at the next plan (`Reconciler.py:323–328`, then `paid` is preferred at 371–373). "Repeatedly" isn't enforced. State that this is accepted, or require two failures. |
| The car's own AC max for DC detection | `chargerPower×1000 > chargeCurrentRequestMax × max(V,240) × 1.1` | ✓ |
| `/api/checkArrival` and `/api/checkDeparture` answer 404 | Branches deleted; falls to `else` → 404 | ✓ |

## 4. Hidden behaviour changes, paid risks, threading, the anti-loop property

| Item | Evidence | Risk |
|---|---|---|
| Parity rows whose counts change, not listed by the plan | Row 2 `test_ble_only_limits_never_wake_to_lower` (fix inside, no plug, BLE). Row 4 `test_fleet_only_raise_costs_the_same` (1,1,1). Rows 5–6 `test_ble_plus_fleet_waits_five_minutes` (asserts `len(b.runs)==2`). | Under either reading of "parked", these lose their apply (HOME, unplugged, no marks → no desire or NOT_HERE). Or, as PRESUMED, the stubbed ping fails. The plan says "Expected: none for paid counts" without tracing it. |
| HOLD costs | A HOLD is `rules: held` → `isNotSent` (`Outcome.py:62`), so it never counts toward `paidSends`. A cloud raise or start wakes *before* the read (`Run.py` `wakeFirst`). | Every re-plan of a held desire can cost a wake and a `vehicle_data` ($0.022) with no budget bound. Re-plans fire on `lastSeen`, and the HA refresh (`HomeAssistant.numCarsAtHome` → `updateChargeAtHome`) bumps that on each policy evaluation. |
| Broadcast audience | `_chargeTargets(None)` → `presentVehicles` → `homeForLimits` (PRESUMED included) | BASE excluded unlocated, unheld cars. A gate-driven broadcast stop can now reach a car charging elsewhere after a restart, and stops are never gated. HA's "at home **and** on a TWC" broadcast rule disappears (`test_charging_reconciler.py::test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars`). |
| The power-start refresh is lost | `TWCManager.py:325–327` | `updateChargeAtHome` (list load plus HOME reads) no longer runs at power start. |
| Deferral ladder | `TeslaAPIProviders.py:61`, `TeslaAPI.py:1892`: BASE's 1800/3600 s deferral for away cars suppressed reads | With one 300 s value, the 20/45-minute `checkDeparture` reads and paid restore reads for away cars can now pay. Contradicts "same paid count". |
| `lastAtHome` | It reads `homeForLimits` | PRESUMED shows as "at home" in `/api/getSlaveTWCs`. |
| Thread safety of the marks | `Vehicle.observe` (any thread) → `noteObservation` outside the leaf lock; `mark` max-merges under `Vehicle._lock` | OK. `previous` is read in a separate store lock from the write, so two same-source writers can race; the only same-source multi-writer is `FleetAPI` (lane and background). `FieldStore._store` returns the *kept* observation when an older stamp arrives, so the hook must use the incoming value and `at`. `lon` without the matching `lat` (TeslaMate topics arrive in either order) can mis-mark "outside", so hook both. |
| Lock order | The hook reads `master.settings` without a lock and takes only the vehicle leaf lock. `learnHome` takes `settingsLock` (an RLock) on the serial thread. `onArrival` from the MQTT thread takes the Desired lock and the HeldLimits/settings lock. | No inversion found. `attribute` (Gen3) runs BLE reads synchronously on the background thread inside `gen3Vitals`, which is slow but lock-safe. |
| Anti-loop (car asleep at home plus a false TWC 00 must never be woken) | Restore: never wakes ✓. Lowering re-apply: never wakes ✓. Ping: VCSEC ✓. | **Broken in one path.** Filter (a) passes when `beforeMax == 0`, the normal idle-plugged state with offer 0. With no telemetry, nothing vetoes. The next 03 opens an anonymous session (`TWCMaster:1346`, because `vehicleKey` is now None), then `attributePlug` → `onArrival`. If the policy limit is above the car's limit, that's a raise, and BLE wakes for raises (`allowWake`). The car wakes, the TWC reports 00, and the cycle repeats. `test_a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore` pins only lowering re-applies. |
| Stuck NOT_HOME after a false unplug | `twcVin` is cleared and D is newest; a sleeping car gets no new H | Until a VIN read (charge start) or a non-restore BLE exchange, policy, start and amps all skip a car that's plugged in at home. |

## 5. Lib delta realism and missed deletions

| Task | Plan Δ | Realistic | Why |
|---|---|---|---|
| 0 | −175 | −160..−168 | black re-wraps at least 6 lines into 3; Rule B `or {}` lines over 88 columns save nothing. |
| 1 | +15 | +15..+20 | Plus the fleet/path discriminator. |
| 2 | −112 | −90..−110 | Narrowing in 8 lines and evidence in 35 are tight. A transition-based D mark (fix 1) adds about 4. |
| 3 | +51 | +65..+80 | Not budgeted: the `heldAt` field plus the `settledAt` bypass, the "logged once per desire" state, restore-contact plumbing into `TeslaBLE` (or drop it: finding 10), and `beforeWrite` for non-limit aspects. |
| 4 | +47 | +45..+55 | OK. |
| 5 | +25 | +45..+55 | The verbatim module is 71 lines, not 45. That's 25 over expected, which trips the stop rule. |
| **End** | ≈26,340 | ≈26,380–26,410 | Presence work (Tasks 2–5) nets about +55..+75, not +11. |

Missed behaviour-neutral (or near-neutral) deletions:
- `VehicleEndpoint.py:164–168` `_telemetryPluggedIn` duplicates T4's `telemetrySaysPlugged`. Keep one: about −5.
- `TeslaBLE.py:177–191` `_scheduleBlocksStart` plus `TeslaBLEProvider.py:95–98` duplicate `Belief.handsOff`'s scheduled-charging rule (`Belief.py:99–103`), which already gates every provider at plan time. About −18, near-neutral: only the run-time re-check is lost. It's pinned by `test_provider_outcomes_local.py:28`. This beats T2's planned rewrite of `_scheduleBlocksStart`.
- Don't rewrite `TWCSlave.pluggedCars` in T2 only to delete it in T5. Leave it untouched until T5, or move T5's fan-out change into T2. About 8 lines of churn.
- `Gen3TWC.CORRELATE_WINDOW` (120) and T5's `PLUGGED_JUST_NOW` (120) are one constant. The plan already deletes the former ✓.

## 6. Deleted-test mapping completeness

| Source (inventory §2) | Inventory fate | Plan | Gap |
|---|---|---|---|
| `test_plug_presence_scenarios.py` 19 | adapt 19 | All 19 named across T3–T5 ✓ | — |
| `test_presence_attribution.py` 10 | as-is 10 | T5 ✓ (10 tests confirmed on the branch) | — |
| `test_vehicle_presence.py` 62 adapt | per group | T6: "≈62 rules → test_presence.py". About 45 presence tests are named across T2–T5. | No per-group map. Groups the final model drops need explicit fates: TestWeakPlugMaxAge 3 (R7, superseded by stickiness), TestReturnPluggedIn 2, TestRemoteRestoreBackoff 2, TestDiscoveryWithAHeldLimit 2, TestHeldWhileNotHome 3, TestDiscover 3, TestDiscoverEvidenceOrder 2, TestBroadcastVINs 4, TestVinLessAttribution 10. |
| `test_teslaapi_presence.py` 25 | adapt | WakeOnlyForAHomeCar ×4 ✓; counts 1/3; radius 1/2 | DiscoveryOnWake 5, DiscoveryEvidenceOrder 2, ChargeTargets 4, ReconcileHomeLocation 2 (now Q5): no named fate. |
| `test_teslable_presence.py` 15 | adapt | Contact 1 ✓, the every-channel departing regression ✓ | SkipsAwayVehicles 2, plug derivation 2, DiscoveryOnWake 5, ChargeTargets 3: no fate. |
| `test_twcslave.py` 26 | adapt | `test_gen2_unplug.py` 7 plus T4 presence 6 | TestPlugVIN 5 (the `plugEnded` cases are gone with `vehicleAt`; say so), TestPresenceTriggers 2, TestChargeVIN 3: no fate. |
| handlers 3, sources 7, HA 5, controller 3, twcmaster 2, TeslaMate/telemetry 2 | adapt | Mostly implicit | HA 5 (radius override, presence over HA's own location, counts) and TeslaMate "an odd `plugged_in` payload is unknown" / "a retained value is a read" are not named. |
| Phase 4 tests rewritten | — | T2–T5 mapping tables | Missing: `test_charging_reconciler.py:440–452` (behaviour changes), `teslatokens.py:146`, `test_teslaapi_wake.py:79`, `test_gen2twc_provider.py` and `test_outcome_desired.py` (plug sessions), and the Gen3 `_correlate` tests. |

---

## Numbered findings

1. **HIGH:** D (departure) is "the newest unplugged/Disconnected *observation*". Every read or push of a car parked unplugged at home re-stamps it, which makes the car NOT_HOME. On equal stamps it's PRESUMED instead. This breaks (k): the apply attempt's own BLE or Fleet read returns Disconnected, so the result is NOT_HERE. It also restores held cars sitting at home after any read. The binding says "last unplug here". Mark an unplug *transition* in `noteObservation`, as for `driveStart`.
2. **HIGH:** Rule 1 (`twcVin` → HOME before outside or movement) combined with Q2 (`twcVin` lives until the filtered Gen2 unplug only, and `observeTwcVin` never clears another car's `twcVin`) means a missed unplug pins the car HOME while it's away. That brings back the 2026-10-11 root cause, and no restore goes out. Make `twcVin` timed H evidence, and clear it on a pushed unplug, an outside fix, or another VIN at the point.
3. **HIGH:** The HOLD re-plan trigger `vehicle.lastSeen > heldAt` misses pushed telemetry, because `Telemetry.py:277` observes with `seen=False`. HA refreshes, BLE observes and our own reads do bump it. A HOLD is NOT_SENT, so each re-plan can wake and read on the paid path with no budget limit. The SATISFIED `settledAt` gate (`Reconciler.py:294–299`) also conflicts with it. Review Focus 2 and 4 can't pass as specified.
4. **HIGH:** Three things are undefined: `None` in `arriving > leaving`, "parked" when no `shiftState` was ever observed, and a PRESUMED "inside, not driving" cell. Under any reading, parity Row 2 (`test_ble_only_limits_never_wake_to_lower`), Row 4 (`test_fleet_only_raise_costs_the_same`) and rows 5–6 (`test_ble_plus_fleet_waits_five_minutes`) change. Define "no departure seen ⇒ apply allowed", and trace every parity row before Task 2.
5. **HIGH:** The parity harness `realBle` stubs `_fetch_state_json` to None and records only `_sendCommand_internal`. A ping that shares the state runner never answers in parity, so PRESUMED BLE rows go UNREACHABLE and then pay after 300 s; they don't simply "gain a run-list entry". Specify the ping's fake before Task 3.
6. **HIGH:** An anti-loop gap. Filter (a) passes when `beforeMax == 0` (the idle plugged car at offer 0), which inverts the binding's ">0 → 0 drop". With no telemetry, the next 03 leads to an anonymous session, then attribution, then `onArrival`. If that's a raise, BLE wakes the car and the loop repeats. The test pins only lowering re-applies. Treat "unknown" as no TWC unplug, or forbid wakes for TWC-only arrivals.
7. **HIGH/MED:** BLE contact newer than a pushed "driving" makes the car HOME (H row 4 > M). With arriving > leaving, an answered ping while driving inside the radius sends the apply. That contradicts Review Focus 2 and the binding's "inside and driving ⇒ hold". Treat the current driving state as ongoing movement.
8. **MED:** Tie semantics: one read stamps fix, `shiftState` and `chargingState` microseconds apart (equal on test clocks), and the rules use strict `>`. Production and tests then diverge (NOT_HOME vs PRESUMED). Define a read as one evidence instant.
9. **MED:** `bleReach` False on any transient BLE failure counts as movement. Commands to a sleeping car fail routinely (the box's "lower never wakes" every 5 min), so HOME re-opens for cars without `twcVin`. That breaks "sticky while asleep", drops the endpoint (`pluggedHere`) and churns pings. Restrict it to ping or scan no-answer.
10. **MED:** The restore's-own-contact exclusion is redundant under E1: HOME, unplugged, leaving newer still restores, and an apply needs arriving newer. It also needs attempt-context plumbing into `_noteBleProof` that isn't budgeted. Drop it.
11. **MED:** Hidden changes not in (a)–(m):
    - `updateChargeAtHome` is no longer run at power start (`TWCManager.py:325–327`).
    - Broadcast start/stop now reaches PRESUMED cars, which BASE excluded unless located or held.
    - HA's "at home and on a TWC" broadcast rule is lost, and `test_charging_reconciler.py:446` is unmapped.
    - One `statusDeferral` removes the away-car read suppression, so the 20/45-minute and restore reads can pay, which contradicts "same paid count".
    - `lastAtHome` is True for PRESUMED.
12. **MED (Gen3):** `pickPluggedCar`'s pool needs reach or inside. BASE guessed the single car plugged within 120 s that wasn't known away. Fleet-only and HA-only Gen3 users without home set or BLE lose the guess. Keep "plugged-just-now, single candidate" decisive.
13. **MED:** `candidates()` is defined differently in Task 2 and Task 5, and Task 4's T12 "single candidate" runs in between. Fix one definition in Task 2.
14. **MED (Task 1):** `_request`'s `purpose` can't identify paid calls (`"read"` covers the free `vehicles/{vin}`, and Owner API calls are free). Key on the Fleet slot plus the path. Task 3's arrival hook contradicts Task 1's "logging only" text.
15. **MED:** The lib budget is optimistic. Task 5's verbatim module is 71 lines against 45, which trips the 25-over stop. Task 3 omits the `heldAt`/`settledAt` work, the once-per-desire log state and the contact plumbing. Expect about 26,380–26,410 at the end, with presence work at about +55..+75, not +11.
16. **LOW:** Missed near-neutral deletions:
    - `VehicleEndpoint._telemetryPluggedIn` duplicates `telemetrySaysPlugged` (about −5).
    - `TeslaBLE._scheduleBlocksStart` plus the `TeslaBLEProvider.startCharging` branch duplicate `Belief.handsOff` (about −18).
    - Skip T2's throw-away `pluggedCars` rewrite.
17. **LOW:** Grep and mapping gaps:
    - The Step 6 grep hits `Presence.atHome` (rename it), parity's `install(located=…)`, `reconcile_helpers.py:20`, `teslatokens.py:146` and `test_teslaapi_wake.py:79`.
    - Unmapped tests: `test_gen2twc_provider.py`, `test_outcome_desired.py`, and the Gen3 `_correlate` tests.
    - Docs: `PolicyCustomization.md:49–80` and `Settings.md:14` are missing from Task 6.
18. **LOW:** Deleted-test mapping has no per-group fate for about 120 of the inventory's 169 adapted presence-branch tests (`test_vehicle_presence`, `teslaapi`, `teslable`, `twcslave`, HA groups). The 19 scenarios and the 10 attribution tests are complete.
19. **LOW (Task 0):** Verified exact. The sites exist, and explicit `null` and the Kostal case are handled. black wraps at least 6 lines, so Δ is about −160..−168. `TWCMaster:1444` now re-assigns `settings["Vehicles"]` outside the lock: the same object, so benign.
20. **LOW:** One missed ping plus 300 s opens the paid path. That's BASE's rule, but not "repeatedly"; state it as accepted. "Presumed plugged = a held car" brings back R14's held ⇒ present shape for starts. Gen3 gets `onArrival` twice (from T3 and T5).
