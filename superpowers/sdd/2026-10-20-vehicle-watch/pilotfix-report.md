# Pilot-cap fix — report (2026-10-22)

Root cause: `overnight-miss-2026-10-22.md`. Fixed as a new commit at the tip of Phase 2. Every later branch is rebased onto it. Nothing has been pushed.

## Branches

| Branch | Backup (old tip) | New tip | Suite (full, `tests/` minus API/integration) |
|---|---|---|---|
| vehicle-model/phase2 | backup/phase2-pre-pilotfix 4b012c27 | **94140b9a** | 1531 passed, 1 xfailed |
| vehicle-model/phase3 | backup/phase3-pre-pilotfix aa9a7b99 | **cbe4822b** | 1911 passed, 1 xfailed |
| vehicle-model/phase3.5 | backup/phase3.5-pre-pilotfix a765b6f4 | **261a66b1** | 1885 passed, 1 xfailed |
| vehicle-model/phase4 | backup/phase4-pre-pilotfix 7432894b | **a844c07a** | 1986 passed, 1 xfailed |
| vehicle-model/phase5 | backup/phase5-pre-pilotfix 36e69be6 | **ddec49ae** | 2276 passed, 1 xfailed |
| vehicle-model/phase6 | backup/phase6-pre-pilotfix 62a0e08c | **44f08d50** | 2391 passed, 1 xfailed |
| docs/gen3-vehicle-model (#707) | backup/gen3docs-pre-pilotfix 6f284ce9 | **ba4e4a46** | 1531 passed, 1 xfailed |

Each branch was moved by a rebase in the worktree that has it checked out (wt-py38, wt-vm3, wt-vm35, wt-vm4, wt-vm5, wt-vm6, wt-gen3docs).

The local `docs/gen3-vehicle-model` was stale: 6f284ce9 sits on the old pre-squash history, while 1255db41 is on origin and `restack2/707`. I rebased its single docs commit onto the new Phase 2. The resulting diff is the same as 1255db41's, plus this fix.

## The Phase 2 commit, 94140b9a "Cap a car by its own charging maximum, not the charger's pilot"

1. `vehicleMaxAmps` now returns `chargeCurrentRequestMax`, falling back to `wiringMaxAmpsPerTWC` (default 32). It never uses the pilot.
   - The field did not exist at Phase 2, so the commit adds it to `Fields.FIELDS` and to the BLE read fields (`Sources.CHARGE_FIELDS`).
   - It is mapped from TeslaAPI `charge_current_request_max` (as a `RegistryField` plus the vehicle_data loop), from TeslaMate `charge_current_request_max` (using the same `_optNum` helper Phase 5 adds), and from BLE `chargeState.chargeCurrentRequestMax`.
   - Fleet's mapping still lands in Phase 5's existing commit.
   - `carAmpsRange` and every provider's `ampsRange` follow, so BLE and Fleet can carry a lift above the pilot.
2. `ChargingPoint.minPower` and `maxPower` convert each member's limit to amps at that member's own voltage, then price it at the point's voltage (the local member's voltage). The comment in `_atPointVoltage` explains why. This removes the 240 V vs 243 V toggle.
3. `TWCMaster._noteRefusedPoint` logs one INFO line when:
   - the fair share covers the point's minimum but the offer is 0, and
   - the point holds a plugged (`occupied is True`), named (VIN, not anonymous) car.
   - The line includes each member's min–max amps. It repeats at most once an hour per point.
   - A budget below the minimum is not logged, so solar flapping cannot cause spam.
4. Tests:
   - Updated the three tests that pinned the pilot rule: `test_vehicle_max_amps_falls_back_to_wiring`, `test_amps_range_is_one_to_vehicle_max`, and `test_state_from_registry_values_without_reads`. Each now also asserts that a 6 A pilot does not cap.
   - Updated `test_amps_range_is_never_none_while_ready`; its 0 now goes through `chargeCurrentRequestMax`.
   - Updated `test_registry_fields` (field count 17 → 18).
   - New tests:
     - `test_a_car_read_under_the_sleep_pilot_still_gets_the_share`: the merged point at 243 V gets 47.4 A, and 32 A once the car reports 32.
     - `test_members_are_compared_at_the_points_voltage`: at 240/241/243 V, `maxPower == minPower` and the target is 6 A.
     - `test_a_named_plugged_car_refused_by_its_point_is_logged_once`.
     - BLE, TeslaAPI and TeslaMate mapping tests.
   - The scratch tests that need `offerFor`, `offered`, `whyQuiet` or `carAmpsRange` do not apply at Phase 2. Their substance is in the Phase 6 replay.
   - Mutation checks: every new or updated test fails under the matching mutation:
     - pilot rule reverted;
     - member comparison reverted to raw watts;
     - log call removed, rate limit removed, or fair-share gate removed;
     - each source mapping or field dropped.

## Rebase notes (behaviour-level resolutions)

- **Phase 3**
  - `chargeCurrentRequest` is added next to `chargeCurrentRequestMax`; both are kept everywhere. The field count is 19.
  - `Sources.py` is deleted in "Read vehicle fields through the providers". The field moved to `Capability.CHARGE_FIELDS`, and the BLE mapping test now goes through the provider's `fetch`.
  - A fixup was squashed into "Remove dead and test-only helpers" (`getCarApiVehicles()` → `carApiVehicles`) so the commit's own tests pass.
- **Phase 3.5**
  - In "Dissolve CarApiVehicle", I took that commit's version of TeslaAPI and re-added the `charge_current_request_max` line to its observe loop.
  - A fixup was squashed into the same commit to port the TeslaAPI mapping test to `api.update_vehicle_data(vehicle)`. I checked it at that commit.
  - In the slot-source commit, test sources changed from TeslaAPI to OwnerAPI.
- **Phase 4**
  - "Collapse the EVSE scaffolding" removes `ChargingPoint.currentPower`, `currentVIN` and `occupied`. The refused-point log now names the car from its members' non-anonymous `vehicleKey`, and counts the point as plugged when any member reports `occupied`.
  - An `edit` stop at "Compute TWC offers on the control tick" moved the new tests to `pointAmps` (the rename happens there). The tip tree was unchanged.
- **Phase 5**
  - "Compute presence from events" already adds the field, the TeslaAPI line, `_optNum` and the TeslaMate mapping. I kept Phase 5's versions and dropped my duplicate TeslaAPI loop line. The field count stays 24.
  - A fixup was squashed into "Check the car on a Gen2 status change" to keep `isAnonKey` in TWCMaster's import (that commit dropped its last other use).
- **Phase 6**
  - The `test_charging_points` additions merge with "An asleep car draws nothing…". Both tests are kept.
  - A new commit, 44f08d50 "Replay the missed overnight charge under a 6 A sleep pilot", adds `tests/unit/test_sleep_pilot_replay.py`. It replays the night:
    - a restart (empty registry);
    - a BLE read at a 6 A pilot (2 V, Stopped, limit 50, battery 50), then the car goes to sleep;
    - the TWC naming the car at 03 (twcVin, max 6 A, 243 V);
    - midnight: 48 A, then a policy limit of 70.
  - The test asserts:
    - `pointAmps` is 47.4 and the offer is 47 A;
    - `offered[VIN] > 0` and a start is desired;
    - `whyQuiet` is None;
    - TeslaBLE wakes before `setChargeLimit`.
  - It fails on the old phase6 tip (target 0.0) and under the pilot-rule mutation.
- The fix holds at every tip: `vehicleMaxAmps` returns the car's maximum, `carAmpsRange` follows it, the point compares members at the point's voltage, and the log is present.
- The scratch replay (`overnight-miss/test_overnight_miss.py`) now fails in exactly the six cases that pinned the bug. Its `test_fix_*` case fails only on its last line: the car's 32 A now binds at exactly 32 A instead of 32 × 240/243.

## Parity

`tests/unit/test_command_path_parity.py` is byte-identical between each backup and new tip for Phase 4, 5 and 6, and it passes. No count changed.

## Lib Δ (backup → new tip)

| Phase | Lines |
|---|---|
| 2 | +66 / −4 |
| 3 | +66 / −4 |
| 3.5 | +65 / −4 |
| 4 | +70 / −4 |
| 5 | +62 / −5 |
| 6 | +62 / −5 (net +57) |

About 32 lines of the growth is the refused-point log helper; the rest is the voltage comparison (~15) and the field and mappings.

## Concerns

- **Lib growth of about 57 lines at Phase 6.** Most of it is the INFO helper. It could be cut by about 15 lines by dropping the per-member min–max text, at the cost of the diagnostic.
- **Commits other than the new ones were changed** by autosquash fixups, so each commit's own tests keep passing:
  - Phase 3: "Remove dead and test-only helpers";
  - Phase 3.5: "Dissolve CarApiVehicle…";
  - Phase 4: "Compute TWC offers on the control tick…";
  - Phase 5: "Check the car on a Gen2 status change…".
  - Only targeted tests were run at those commits; the full suite was run only at each tip.
- **`test_charging_points.py` and `test_vehicle_endpoint.py` were not run through black.** They were never black-formatted, and running black would rewrite each whole file and conflict through every phase. My additions follow their compact style. Every other touched file is black-clean.
- **Unaddressed: budget voltage vs the TWC's measured voltage.** The distributor's budget is priced at `defaultVoltage` while a TWC's minimum is priced at its measured voltage. A budget of exactly the minimum amps (6 A × 240 V against 6 A × 243 V) still gives 0. That is not the member mismatch fixed here.
- **`availableCurrent` still carries the pilot and our own charge-rate writes.** Nothing caps on it now, but its meaning stays mixed.
- **The live box still runs deploy/phase6-diag (the bug).** Nothing was deployed.
- **Housekeeping.** The `wt-scratch` worktree was moved temporarily for per-commit checks and is back at a765b6f4. Scratch helpers are in `scratchpad/pilotfix/`.

## Round 2: review fixes, amended into the Phase 2 commit (94140b9a → ccecae62)

Backups of the round-1 tips are `backup/<phase>-pilotfix-r1` and `backup/gen3docs-pilotfix-r1`.

- **Finding 2, the lift regression.**
  - The amps-range filter in `ProviderOrder.candidates` now applies only when `localRule` is set; the car clamps a vehicle rate to its own maximum. This is a one-line change.
  - Phase 2 test `test_a_vehicle_rate_above_the_cars_maximum_still_reaches_it` checks the Order level.
  - The Phase 6 replay commit is amended with `test_a_car_left_at_a_lowered_request_is_lifted_above_its_own_maximum`. A car with a 32 A maximum on 48 A wiring, asking for 10 A, gets the lift and BLE `setAmps 48`.
  - Both tests fail with the filter put back.
- **Finding 3.**
  - The INFO line is gated on `point.maxPower < point.minPower <= fair_share`.
  - The test now covers a wiring budget of 5 A, where the members are fine, and checks that nothing is logged.
- **Finding 4.**
  - The helper no longer prints each member's limits, and no longer uses `__dict__.setdefault`; it uses a class-level `_refusedPointLogged` and an inline 3600 s.
  - ChargingPoint has one `_atPointVoltage(limit, pick)` helper.
  - Lib is down 14 lines net at every tip compared with round 1: −15 in the helper and ChargingPoint, +1 net in Order.
- **Re-rebase conflicts:**
  - the log test in "Compute TWC offers…" (`pointAmps`);
  - ChargingPoint and the log condition in "Collapse the EVSE scaffolding…", as before;
  - `test_charging_points` against "An asleep car draws nothing…".

## Round 3: new commit at the tip of Phase 5, c02bb803 "Scan for the car when a plug-in finds no candidate"

- **The scan.**
  - `Presence.attribute` checks three things when `pick` finds nothing: `candidates()` is empty, BLE may be used (a Gen2 offer is given, so this runs on the BLE worker), and the plug-in has not been scanned yet (the anonymous vehicle's `scan` mark is older than its `plugIn` mark).
  - It then runs one `TeslaBLE.scanForVehicleInRange(every registry VIN)` and picks again.
  - A hit is recorded as `bleReach` True → contact → HOME, so the car becomes a candidate.
  - Gen3 attribution (no offer, never a BLE read) never scans.
  - The scan is passive: no wake and no paid call.
- **Re-attempts.**
  - `attributePlugs` now also queues an anonymous session that is drawing current (≥ 1 A), not only one plugged in within the last 120 s.
  - `noteObservation` calls `attributePlugs` on new contact: a `bleReach` True on a car not reached within `REACH_WINDOW` and not named by a TWC.
  - It also calls it on a plug-in edge from any source other than a charger. Before, only the telemetry feeds triggered this.
  - What existed already: re-attempts on status edges (beginning a plug session) and on telemetry plug-ins.
  - The "left anonymous" INFO line now logs once per plug-in. The parity row `test_vinless_ambiguous_plug_rates_nobody_and_logs_once` asserts one line, and a contact-triggered re-attempt would have logged a second one.
- **BLE scan.** `TeslaBLE.scanForVehicleInRange` takes one VIN or several and does one bluetoothctl run for all of them. This is the subset of the Phase 6 change ("Hear an away car come back…"); at that commit the conflict resolves to Phase 6's version.
- **Tests:**
  - `test_a_car_lost_to_ble_is_named_on_its_plug_edge_by_one_scan` (real TeslaBLE, fake bluetoothctl);
  - `test_an_unnamed_session_drawing_current_is_named_on_news_of_its_car`, with two cases: contact, and a cloud plug-in report at home;
  - `test_one_scan_answers_for_several_cars`.
  - Mutation-checked: removing the scan, the contact trigger, the drawing-current re-attempt, the once-per-plug-in guard, or the wider plug-report sources each fails a test.
- **Phase 6 rebase.**
  - TeslaBLE conflict in "Hear an away car come back…": I took that commit's version. The multi-VIN test's `_bluezAddresses` mock becomes `{}`.
  - Test conflict in "Scan for cars from Docker…": kept both tests.
  - A fixup was squashed into that commit: the plug-in scan test's fake bluetoothctl answers `bluetoothctl show`, the readiness check that commit adds. Checked at that commit and the one before it.

## Final tips

| Branch | Tip | Suite |
|---|---|---|
| phase2 | ccecae62 | 1532 passed, 1 xfailed |
| phase3 | bd73ffff | 1912 passed, 1 xfailed |
| phase3.5 | 1bcded30 | 1886 passed, 1 xfailed |
| phase4 | bbfc4d85 | 1987 passed, 1 xfailed |
| phase5 | c02bb803 | 2281 passed, 1 xfailed |
| phase6 | 3c38c2eb | 2397 passed, 1 xfailed |
| docs/gen3-vehicle-model | a3613b71 | 1532 passed, 1 xfailed |

- **Parity:** `test_command_path_parity.py` is byte-identical to the original backups at Phase 4, 5 and 6, and passes everywhere. No count moved.
- **Lib Δ from the original tips:**

| Phase | Lines |
|---|---|
| 2 | +54 / −6 |
| 3 | +54 / −6 |
| 3.5 | +53 / −6 |
| 4 | +58 / −6 |
| 5 | +105 / −40 (the scan commit alone is +55 / −33) |
| 6 | +74 / −12 |

- **Backup before round 3:** `backup/phase6-prescan`.

## Round 4: docs, the driving-hold fix, and full suites at the fixup commits

Backups of the round-3 tips are `backup/<phase>-pilotfix-r2` and `backup/phase6-pilotfix-r3`.

- **Phase 2 fix commit, amended (26fc3f3d).** CHANGELOG Bugfixes gets one bullet covering:
  - the 6 A sleep-pilot cap and the 0 offer above 240 V;
  - the car's own maximum as its limit;
  - a raise still reaching a car whose maximum is lower;
  - the INFO line, quoted, at most hourly.
  - The only conflicts in the re-rebase were CHANGELOG ones; both sides kept.
- **Phase 5 scan commit, amended (7af64ea1).**
  - CHANGELOG Bugfixes bullet.
  - `docs/PolicyCustomization.md` gets a paragraph on VIN-less Gen2 naming:
    - the order of evidence;
    - the plug-in as arrival evidence, with one passive scan;
    - the re-attempt while the plug draws current;
    - the once-per-plug-in log line.
- **New Phase 5 commit b92d35c1 "Stop treating a plugged-in car as driving".**
  - `Presence.drivingNow` returns False when any of these is newer than the driving reading (`shiftState` or the feed's `state`):
    - the `plugIn` mark;
    - a `twcVin` naming;
    - a `chargingState` of "Charging";
    - `actualCurrent` of 1 A or more.
  - Lib: +13/−3.
  - PolicyCustomization's "Probably home" text and the CHANGELOG are updated.
  - Test `test_a_car_named_on_its_twc_after_an_unended_drive_is_not_driving`: a drive start with no drive end, then a TWC naming the car. The car is HOME, not driving, and the policy limit 50 goes out over BLE.
  - The test also covers each evidence kind: Gen2 current, a cloud "Charging" at a charger elsewhere, and a Gen2 plug. Each kind's clause is mutation-checked.
  - The existing applicability row "driving, plugged earlier → HOLD driving" still holds, because there the plug is older than the drive.
  - Phase 6 rebased cleanly onto it.

### Full suite at the five fixup-modified commits

| Commit | Suite |
|---|---|
| 5961fc49 "Remove dead and test-only helpers" (Phase 3) | 1907 passed, 1 xfailed |
| c7beac1f "Dissolve CarApiVehicle…" (Phase 3.5) | 1930 passed, 1 xfailed |
| e98faa2a "Compute TWC offers on the control tick…" (Phase 4) | 1947 passed, 1 xfailed |
| a1b313fb "Check the car on a Gen2 status change…" (Phase 5) | 2216 passed, 1 xfailed |
| e3ce7e48 "Scan for cars from Docker…" (Phase 6, after the final rebase) | 2392 passed, 1 xfailed |

Its pre-rebase twin, c47ebe73, also passed: 2391 passed, 1 xfailed.

### Final tips

| Branch | Tip | Suite |
|---|---|---|
| phase2 | 26fc3f3d | 1532 passed, 1 xfailed |
| phase3 | fe9eca64 | 1912 passed, 1 xfailed |
| phase3.5 | 4c00d9a6 | 1886 passed, 1 xfailed |
| phase4 | 0e3e5687 | 1987 passed, 1 xfailed |
| phase5 | b92d35c1 | 2282 passed, 1 xfailed |
| phase6 | bba534df | 2398 passed, 1 xfailed |
| docs/gen3-vehicle-model | 2d565e48 | 1532 passed, 1 xfailed |

- **Parity:** `test_command_path_parity.py` is byte-identical to the original tips everywhere.
- **Lib Δ from the original tips:**

| Phase | Lines |
|---|---|
| 2 | +54 / −6 |
| 3 | +54 / −6 |
| 3.5 | +53 / −6 |
| 4 | +58 / −6 |
| 5 | +118 / −43 |
| 6 | +87 / −15 |
