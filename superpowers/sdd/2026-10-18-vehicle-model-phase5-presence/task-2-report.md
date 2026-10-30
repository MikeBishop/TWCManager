# Task 2 report: Presence from events; one home check

Status: DONE_WITH_CONCERNS (lib grew +120 against an expected −88; see "Lib delta")
Commit: f29c370f on vehicle-model/phase5 (wt-vm5), parent e8934852. Not pushed.

## What was implemented

- New `Vehicle/Presence.py`. It computes HOME, PRESUMED or NOT_HOME fresh from events, following the brief's rules 1–6. All comparisons are strict, so ties fall through to PRESUMED (F8). Missing times are `NEVER = -inf` (F4).
- **Marks.** `Vehicle.mark(name, at)` max-merges under the leaf lock; `Vehicle.markAt(name)` returns -inf when unset.
- **Observe hook.** `VehicleRegistry.onObserve` is wired in `TWCMaster.__init__` as `functools.partial(Presence.noteObservation, master)`.
  - `Vehicle.observe` captures the same source's prior observation before the store. After the store, outside the lock, it hands the hook the source's own new observation (the incoming reading, not the field's kept one).
  - The hook skips a reading older than the source's last.
  - A hook exception is logged at DEBUG and swallowed.
- **The marks:**
  - `plugIn`/`unplug` per source, through the plug mapping and narrowing (l). A Gen2TWC unplug is always a transition.
  - `driveStart`/`driveEnd` from `shiftState` and `state`.
  - `outside` from a lat/lon pair.
  - `contact`/`absent` from `bleReach`.
- **twcVin bound (F2).** The point must still report a plug: a Gen2 slave whose `twcid` matches with `reportedState != 0`, or a Gen3 unit whose `pointId` matches with `vitals["vehicle_connected"]`. No `driveStart` or `outside` mark may be newer than the twcVin observation. `observeTwcVin` clears `twcVin` on any other car attributed to that point.
- **Callers:**
  - `presentVehicles` uses `homeForLimits`, with BASE's anonymous rule.
  - `TWCMaster._chargeTargets` uses `Presence.candidates(self, capability)`.
  - `_restoreDeparted`:
    - Reads `chargingState` at READ_MAX_AGE (no wake).
    - Restores NOT_HOME cars.
    - The stale guard compares the deciding event's time with `lastWrite("chargeLimit")` using `<=` (ruling Q2).
  - TeslaAPI:
    - `updateChargeAtHome` reads HOME cars only.
    - `numCarsAtHome`/`minBatteryLevelAtHome` go through `homeCars`.
    - The `update_vehicle_data` ladder runs on `not inside(...)`. It observes `shiftState` and the five charger fields; the charger fields share the charge fields' stamp and are observed before `chargingState`.
    - `is_far_from_home` has its own 1.4° box test.
  - HA:
    - Caches only `battery_level`.
    - Coordinates go to the registry only; the zone name `"home"` is no longer a location.
    - Its counts go through `homeCars`.
  - TeslaBLE:
    - `_noteBleProof` observes `bleReach` True. The scan already wrote True/False.
    - `get_charge_state` maps the five charger fields.
    - `_scheduleBlocksStart` and the provider's schedule branch are deleted.
  - TeslaMate maps `shift_state`, `charger_power` and `charge_current_request_max`.
  - `recordVehicleVIN` calls `Presence.learnHome`. `vehicleIsDefinitelyHome` is deleted in TeslaAPI, the master and TWCManager.py, along with the `_taskKey` branch.
  - `HTTPControl`: `lastAtHome = presence(...) == HOME`.
- Forced name swaps (approved):
  - `Gen3TWC._correlate`: an API-attached car must be HOME, as BASE's `atHome`.
  - `VehicleEndpoint`: `presence == HOME`.
  - `TWCSlave.pluggedCars`: `candidates(..., SET_AMPS)`, `inside(...) is False`, `_PLUGGED` imported from Presence. No logic rewrite.
- CHANGELOG: one line for the `atHomeRadius` 1,000 ft default and home learning, (e)/(f). The `etc/twcmanager/*.json` comments that still say "default 10560" are left for the docs task.

## Interfaces later tasks consume (exact)

- `Presence` exports these names:
  - **Constants:** `HOME = "home"`, `PRESUMED = "presumed"`, `NOT_HOME = "notHome"`, `NEVER = -math.inf`, `HOME_RADIUS_FT = 1000`, `HOME_FIX_MAX_AGE = 600.0`, `REACH_WINDOW = 300.0`, `HOME_CHARGER_TYPES`, `_PLUGGED`.
  - **The hook:** `noteObservation(master, vehicle, field, obs, previous) -> None`. **It takes `field`**, which the brief's signature lacks: an `Observation` has no field name, and lat and lon can't be told apart without it.
  - **State:**
    - `decide(master, v) -> (state, why, at)`. It is public so Targets' stale guard gets the deciding event's time.
    - `presence(master, v) -> str`
    - `why(master, v) -> str`
    - `homeForLimits(master, v) -> bool`
    - `pluggedHere(master, v) -> bool`
    - `pluggedNow(master, v) -> bool`, which takes **master** because car sources need the radius.
    - `drivingNow(v) -> bool`
  - **Event times:** `leaving(v) -> float`, `arriving(v) -> float`, `twcVinAt(master, v) -> float` (NEVER when twcVin is not valid home evidence).
  - **Position:** `inside(master, v) -> Optional[bool]`.
  - **Car sets:** `candidates(master, capability=None) -> List[Vehicle]`, `homeCars(master, attachment) -> List[(Vehicle, attachment)]`.
  - **Home learning:** `learnHome(master, vehicle) -> bool`.
- `parkedNow` is inlined into `decide`; it is not exported.
- `Vehicle.mark(name, at)`, `Vehicle.markAt(name) -> float`.
- `VehicleRegistry.onObserve`: a callable `(vehicle, field, obs, previous)`.
- `Fields.OBSERVED_EVENTS = {pluggedIn, chargingState, shiftState, state, lat, lon, bleReach}`. `bleReach` is hooked too, so the contact/absent marks come from the one hook. Task 3's ping only needs to observe `bleReach` False on an unanswered VCSEC ping.
- **No `onArrival` call** in `noteObservation` (ruling Q1). Task 3 adds the one-line call where it marks `"plugIn"` from `TeslaMateVehicle`/`FleetTelemetryMQTT`/`Gen3TWC`, i.e. in the `elif plugged is True and was is not True:` branch. The one-arg `Targets.onArrival(master)` is unchanged.

## Decisions within the brief

- **Lat/lon pairing: a same-source tolerance `_PAIR_WINDOW = 2.0` s, not source pairing.** TeslaMate and Fleet Telemetry deliver latitude and longitude as separate MQTT messages. Each is stamped on arrival, so they can never share an `at`, and source-side stamping can't cover the feeds that most need it. The tolerance covers every observer in one place. TeslaAPI's charge fields do share one stamp per response, but for the narrowing rule, not for pairing.
- **`_restoreDeparted` read gate.** I kept BASE's "TeslaAPI attached and `syncSource == "TeslaAPI"`" gate. Without it, `test_live_telemetry_places_a_departing_car_for_free` paid a `vehicle_data` read: `chargingState` had never been observed, so the read cascaded to the cloud. The count would have moved.
- **No BLE `pluggedIn`.** The brief says to add it. It is redundant with BLE's `chargingState` (a strong source, mapped the same way), and the BLE provider filters to `CHARGE_FIELDS`, so `pluggedIn` would need to join that set, which would also tell the order that TeslaAPI can fetch it. Left out.
- **`learnHome` freshness.** It uses the fix's own stamp (`registry.now() - lat.at`), not the liveness-aware `age()`. On a healthy feed `age()` is 0, which would pass a frozen fix.
- **Gen3 `_correlate`.** It keeps BASE's shape: an API-attached car must be HOME. PRESUMED no longer counts as `atHome`.

## Tests and results

- Full suite: **1981 passed, 1 xfailed, 1 warning**. BASE was 1959 passed, 1 xfailed and also 1 warning (verified on a detached HEAD worktree). The +22 is 24 new presence tests, minus 4 vin-confirmation tests folded into 1, plus 1 unplug-guard test.
- Parity: `tests/unit/test_command_path_parity.py` passes. The only edit is `:1306`, `api.locate(v) is True` → `Presence.presence(m, v) == Presence.HOME`, plus the import line it needs. No count or timing moved. Row 26 passes: TeslaMate `Complete` with a fix inside marks `plugIn` → HOME.
- The grep for retired names finds only these hits:
  - `docs/modules/Vehicle_HomeAssistant.md:88`, left for Task 6/7;
  - `TWCMaster.py:1165` (the word "locate");
  - parity's `install(located=…)`;
  - the kept test name `test_a_listed_car_not_yet_located_is_in_the_broadcast`.

## TDD evidence

- I wrote the Presence module before `test_presence.py`, so test-first was not literal. Evidence that the tests are not vacuous:
  - `test_presence.py` run on a detached worktree at e8934852 fails at import (`cannot import name 'Presence'`).
  - During development, three of the new tests failed against my first implementation and changed things:
    - the DC case exposed the source's previous plugged value;
    - the BLE-reach candidate needed contact older than the outside fix;
    - the ladder test needed a point within 1.4°.
  - The pinned tests failed after the lib change (50 failures) and were then re-plumbed per the mapping.

## Files changed

- **lib:**
  - `Vehicle/Presence.py` (new);
  - `Vehicle/Registry/{Vehicle,VehicleRegistry,Fields}.py`;
  - `Vehicle/Providers/{Capability,TeslaBLEProvider}.py`;
  - `Vehicle/Reconcile/Targets.py`;
  - `Vehicle/{TeslaAPI,HomeAssistant,TeslaBLE,TeslaMateVehicle}.py`;
  - `TWCMaster.py`, `TWCManager.py`, `TWCSlave.py`;
  - `EVSEInstance/{Gen3TWC,VehicleEndpoint}.py`;
  - `Control/HTTPControl.py`.
- **tests:** `test_presence.py` (new), plus the files in the mapping below.
- `CHANGELOG.md`.

## Test mapping (old → new)

| Test | Fate |
|---|---|
| `test_limit_wiring::test_present_rule_until_phase_5` | Renamed `test_present_rule`; assertions unchanged (PLUMBING-ONLY) |
| `::test_a_fleet_car_that_unplugs_and_leaves…` | `car.atHome is False` → `presence == NOT_HOME`; paid list unchanged |
| `::test_an_unplug_at_home_is_not_a_departure` | Unchanged; passes (shift D on the read → driveStart → PRESUMED) |
| `::test_live_telemetry_places_a_departing_car_for_free` | Unchanged (passes with the read gate kept); comment reworded |
| `::test_a_restart_with_the_car_plugged_in_and_asleep…` | `presence == HOME` (PLUMBING-ONLY) |
| `::test_a_held_car_with_no_known_position_is_present` | First half kept. Second half INTENTIONALLY CHANGED (a): PRESUMED; with the BLE stub requiring a claim, no candidate under `ble_only` → no desire, no request; claim → present |
| `::test_a_held_car_a_free_position_places_away…` | `presence == NOT_HOME` (PLUMBING-ONLY) |
| `::test_a_car_its_twc_names_stays_at_home…` | Rewritten: TWC at 03 names it after an away fix → HOME, present, not in `candidates(START)`; TWC at 00 → the fix decides (NOT_HOME) |
| `::test_a_held_car_with_no_position_or_ble_is_present_for_a_cloud_provider` | Second half INTENTIONALLY CHANGED (b): PRESUMED → present (was absent) |
| `::test_a_listed_car_not_yet_located_is_in_the_broadcast` | On `candidates(m, START_CHARGING)`: PRESUMED → in; AWAY → out |
| `::test_an_away_fix_older_than_our_last_limit_write_is_no_departure` | Kept unchanged (the deciding-event guard, Q2) |
| (new) `::test_an_unplug_older_than_our_last_limit_write_is_no_departure` | The unplug-mark variant of the guard |
| `test_twcmaster_vin_confirmation.py` 4 home-check tests | → `test_presence::test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix` + `test_a_confirmed_vin_learns_home_from_the_cars_fresh_fix_without_io`: behavioural, in place of the static check. It proves `recordVehicleVIN` → `learnHome` with no module I/O. INTENTIONALLY CHANGED (f) |
| `test_reads_no_wake.py` (5 tests) | `vehicle.read("lat", 0)` in place of `update_location`; `is_location_home` Mocks deleted; counts unchanged. Two renamed: `test_location_read_recomputes_at_home` → `test_location_read_observes_the_position`; `test_location_ignores_a_fix_time_older_than_the_position` → `test_a_location_read_with_no_fix_time_keeps_the_older_one` (gpsAge to the home check is gone; it still pins that a null `gps_as_of` keeps the older one) (PLUMBING-ONLY) |
| `test_telemetry_registry.py:214–251` | `read("lat", 0) is not None` in place of `update_location(...) is True`; counts unchanged (PLUMBING-ONLY) |
| `test_teslaapi_providers.py`, `test_teslaapi_registry.py` | `is_location_home` Mocks deleted; `is_far_from_home` Mocks kept; `atHome` left the tuple (PLUMBING-ONLY) |
| `teslatokens.py:146`, `test_teslaapi_wake.py:79` | Lines deleted. No placement was needed: nothing in those tests reads presence, and they pass as is (PLUMBING-ONLY) |
| `reconcile_helpers.py:20` | Comment reworded |
| `test_registry_callers::test_get_slave_twcs…` | Mock master gets `getHomeLatLon`; lastAtHome False while PRESUMED (new assert), True once parked at home. This is the brief's `test_last_at_home_is_true_only_for_home`, kept here rather than duplicated (PLUMBING-ONLY) |
| `test_homeassistant_registry.py:96` | Mock removed |
| `test_charging_reconciler::test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars` | HA cars placed HOME by `placeAt` instead of `at_home=True`; audience unchanged (PLUMBING-ONLY) |
| `test_provider_outcomes_local::test_ble_schedule_block_is_satisfied_without_a_command` | → `test_a_pending_schedule_gets_no_ble_start_attempt` (reconciler + `Belief.handsOff`: no start call). The refusal test's `getModuleByName=None` line, which existed only for schedule data, was removed (PLUMBING-ONLY, F16) |
| Fixtures not in the brief's table | `test_charging_points.real()/car()`, `test_vehicle_endpoint.master()/car()` (`atHome` param → `home`; master gets `getHomeLatLon`), and `test_gen2_idle_minimum` ×3: `atHome=True` → `placeAt(m, v)`; `carapi.locate` Mocks removed. `test_twcmaster.py` fixture: `getModuleByName("Gen3TWCs")` → None (a Mock module isn't iterable for the point lookup). `test_registry_fields::test_constants`: FIELDS 18 → 24. All PLUMBING-ONLY |

## Lib delta

- Before: 26,352. After: 26,472. **Δ +120**, against an expected −88 (−70..−110). That is ≈208 over the target and > 25 over.
- `git diff --shortstat e8934852 -- lib`: 17 files changed, 410 insertions(+), 290 deletions(-).
- Deletions are on plan: 290 gross against the plan's 282. The overshoot is all on the add side:

| File | +/− | Plan "in" |
|---|---|---|
| Presence.py | +273 (≈198 code, ≈45 blank lines black puts between ~22 top-level defs, ≈30 comments) | ≈125 |
| Registry/Vehicle.py | +25/−1 (marks 8, hook with prior capture + guard 14) | 9 |
| Fields + Capability + TeslaMate | +25 | ≈21 |
| VehicleRegistry | +7 | 4 |
| TeslaAPI | +20/−120 | (delegations + ladder ≈20 shared) |
| Targets | +14/−67 | 15 |
| HA | +12/−42 | — |
| TWCMaster | +12/−22 | — |
| TeslaBLE / provider | +10/−21 | — |

- Where the estimate broke:
  - The plan's per-item Presence budget has no blank lines.
  - It allows 6 lines for the twcVin bound, which needs a Gen2 + Gen3 point lookup (≈15).
  - It allows 18 for mapping plus narrowing; the narrowing rule alone is ≈20.
  - It allows 9 for the Vehicle hook.
- I trimmed what was trimmable without style tricks: inlined `parkedNow`, merged imports, compacted `learnHome`. Further cuts would mean lambda assignments or fewer blank lines.

## Self-review

- **Completeness:** every brief item is done except BLE `pluggedIn` and the onArrival call (both explained above).
- **Comment rule:** no history, phase, ruling or PR ids in lib comments. Comments explain why.
- **Threading:**
  - `noteObservation` runs unlocked on the observing thread, reads settings unlocked (two floats) and marks under the leaf lock.
  - `learnHome` on the serial thread takes only `settingsLock` through `setHomeLat`/`setHomeLon` and queues tasks. It does no I/O.
- No new polling or paid calls. Parity counts are unchanged.

## Concerns

1. **Lib grew +120 instead of shrinking ≈88** (table above). The user's rule is that line budgets are targets and growth is a red flag. The overshoot is the Presence module's size against a budget that omitted black's blank lines and under-counted the point lookup and narrowing. No duplicate code is left to remove in this task's scope. The remaining duplication (`TWCSlave.pluggedCars`' plug mapping, `VehicleEndpoint._telemetryPluggedIn`, Gen3's guess loop) is scheduled for deletion in Tasks 3 and 5.
2. `updateChargeAtHome` now reads HOME cars only, and home is never seeded from a first fix. A Fleet-only install with no home set therefore reads no car at power start until home is set on the Settings page or learned from a TWC-named car. This follows from (f) plus F11, and the user may not have foreseen it.
3. Narrowing at mark time can't see TeslaMate's `charger_power`, which arrives after `plugged_in`. A pushed plug-in at a fast charger inside the radius therefore marks `plugIn` (HOME). `pluggedNow` excludes it once the power arrives, but the mark stands.
4. `_restoreDeparted` keeps BASE's TeslaAPI-attached and syncSource gates beyond the brief's wording. Without them a paid count moved.
5. `noteObservation` gained a `field` argument, and `pluggedNow` takes `master` (interface notes above).

---

## Fix round 1 (commit 1d4635d4)

The review file `task-2-review.md` was not on disk, so these fixes follow the cut list and issue IDs in the coordinator's message.

- **I1.** The ladder in `update_vehicle_data` now tests `inside(...) is False`. With no home set, the next read is deferred 300 s. Covered by the first row of `test_away_cars_keep_the_status_deferral_ladder`.
- **I2(a).** In `noteObservation`, the lat/lon branch calls `learnHome` while `twcVinAt > NEVER`. Test: `test_a_fix_while_a_twc_names_the_car_teaches_home` (no home set; the TWC names the car; TeslaMate's lat then lon → home learned).
- **I2(b).** A once-per-process WARNING with the given wording. It is an `lru_cache`'d `_warnNoHome()` called from `Presence._within` when home is unset. That is the one function every presence radius test goes through, so it fires on the first need. Test: the end of `test_home_radius_defaults_to_1000_ft_and_config_overrides` (two checks, one warning). No CHANGELOG change in this round.
- **Cut list:**
  - **BLE charger fields:** removed from `TeslaBLE.get_charge_state`.
  - **CHARGE_FIELDS:** the additions are removed.
  - **`_pointPlugged`:** the Gen3 lookup is removed. A Gen2 point uses its slave's `reportedState`. A point no Gen2 slave owns counts as plugged only if it is a Gen3 point (`"Gen3TWC-"` id), because Gen3 clears twcVin at its falling edge. Returning True for every unknown point broke `test_an_anonymous_point_fans_out_as_main_did` (a car on an unlinked "8245" point dropped out of the fan-out). The test now names a Gen3 point.
  - **bleReach → marks:** `candidates` reads `markAt("contact")` within REACH_WINDOW instead of the `bleReach` field. The hook's bleReach branch is one line.
  - **`why` dropped:** tests use `decide(...)[1]`.
  - **Header** shortened.
  - **`since()` lines** compacted.
  - **`_plugEvidence`** reduced to one expression.
  - **`learnHome` log** is one line.
  - **OBSERVED_EVENTS:** removed from Fields. `noteObservation`'s `elif` chain is the filter, and the hook is called for every field.
  - **Hook:** a single `logger.exception` line; the `mine is not None` check is dropped (M1).
  - **math imports** removed (`float("-inf")`).
  - **Registry comment** is one line.
  - **TeslaMate converters** are plain `float`/`int`.
  - **`vehicleScheduledChargingPending`** deleted (it had no callers).
- **Other cuts:**
  - The master wires the hook with a one-line lambda; the `functools` import is gone.
  - The `decide` movement tuple became a single `max`.
  - `_within` drops a None-check that its callers make redundant.
- **M3.** A coordinate pairs with the same source's latest other coordinate, with no time window. Tests cover either order, a single-coordinate update and a different source.
- **M5.** `test_presence.py` is rewritten without `;` joins or `__import__`, and black-clean. The parity line is now a comment line plus the assert, also black-clean.
- **M6.** Renamed to `test_a_fast_charger_inside_the_radius_marks_no_plug_in`.
- **M2, interface note for Task 3.** TeslaMate's plug narrowing is blind at plug-in, because `charger_power` arrives after `plugged_in`. `onArrival` must therefore check `pluggedNow(master, v)` when it decides, not trust the `plugIn` mark alone.

**Interfaces after this round:**
- `why` is gone; use `decide(master, v)[1]`.
- The hook sees every field.
- `Fields.OBSERVED_EVENTS` is gone.
- The rest is unchanged.

**Tests:** covering tests 228 passed; full suite **1982 passed, 1 xfailed, 1 warning** (BASE's warning).

**Lib delta against e8934852:** 26,352 → 26,415, **+63**. `git diff --shortstat e8934852 -- lib`: 16 files changed, 361 insertions(+), 298 deletions(-). This round alone is −57. That is still growth, against the expected −88. Presence.py is 247 lines, of which ≈45 are blank lines that black requires. Everything left in it is used more than once, or is a brief interface (`pluggedHere` is unused until Task 3).

---

## Fix round 2 (commit after 1d4635d4: "Keep the BLE absence and empty TeslaMate payload guards")

1. **`candidates` near rule:**
   - It is now `reach = max(v.markAt("absent"), registry.now() - REACH_WINDOW)` followed by `near = reach < v.markAt("contact")`. This is the given expression split over two lines so black doesn't wrap it awkwardly.
   - New test (extending `test_candidates_for_a_broadcast_are_only_cars_base_reached`): contact, then absent, then an outside fix. The car is NOT_HOME and is not near.
2. **TeslaMate converters:**
   - A shared module-level `_optNum(a)` (`float(a) if a else None`) is used for both `charger_power` and `charge_current_request_max`.
   - New test `test_telemetry_registry::test_an_empty_charger_payload_is_no_reading`: an empty payload gives None with no exception, and "16.0" gives 16.0.
3. **bleReach branch:** marks only for a bool value. True gives contact; False gives absent.

**Tests:** covering tests pass. Full suite: **1983 passed, 1 xfailed, 1 warning**.

**Black:** clean on all touched lib files, `test_presence.py` and parity. `test_telemetry_registry.py` was already not black-clean at e8934852; the lines I added are clean.

**Lib delta against e8934852:** 26,352 → 26,422, **+70**. This round is +7.
