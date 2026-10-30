### Task 2: Presence from events; one home check (expected lib Δ ≈ −88)

**Events and readings** (`Presence.py`). Every time is a float, and a missing one is `-inf` (F4).

**Events recorded when the observation arrives** (`Presence.noteObservation`):
- **The hook.** `VehicleRegistry.onObserve` is set by the master at startup. `Vehicle.observe` calls it for `pluggedIn`, `chargingState`, `shiftState`, `state`, `lat` and `lon`, after the store and outside the leaf lock, with the incoming observation and the same source's prior value.
- **Storage.** `Vehicle.mark(name, at)` / `markAt(name)`: max-merge under the leaf lock, memory-only. Nothing is evaluated later, so a 20 s drive between two policy passes is still seen.
- **The marks:**
  - `"plugIn"` / `"unplug"` (F1): a plug transition, per source, using the mapped plug value (below):
    - plugged → unplugged marks `"unplug"` at `obs.at`;
    - unplugged or none → plugged marks `"plugIn"`.
    - A first unplugged reading with no plugged one before it marks nothing, so repeated Disconnected reads of a car parked unplugged are not a departure.
    - `Gen2TWC` writes only filtered unplugs (Task 4), so it is always a transition.
    - Car sources count only with the newest fix inside.
  - `"driveStart"`: `shiftState` from P/None to D/R/N, or `state` becoming `"driving"`, with the newest fix not outside.
  - `"driveEnd"`: `shiftState` back to P, or `state` leaving `"driving"`, with the newest fix inside.
  - `"outside"`: a fix outside the radius. Both `lat` and `lon` call the hook, and the test runs only once the other coordinate from the same source is at the same `at` (TeslaMate topics arrive in either order).
  - `"contact"`: `bleReach` True. `"absent"`: `bleReach` False. Both are written only by Task 2's BLE paths.
- **Plug-in arrivals (c):** when `noteObservation` marks `"plugIn"` from a pushed source (`TeslaMateVehicle`, `FleetTelemetryMQTT`) or from `Gen3TWC`, it calls `Targets.onArrival(master, vehicle)`. This is its own hook, not Task 1's logging (F14).

**Plug value mapping** (per source):
- `pluggedIn` as is.
- `chargingState`:
  - `"Disconnected"` → unplugged;
  - `""`, `"Unknown"`, `"SNA"`, `"None"` and `None` → nothing;
  - `_PLUGGED = {"Charging","Starting","Stopped","Complete","NoPower"}` → plugged;
  - HomeAssistant: only `"Charging"`.
- **Narrowing (l)** for car sources: a plugged value is not plug evidence when the same source reports, at or after it, any of:
  - `fastChargerPresent` True, or `fastChargerType` not in `HOME_CHARGER_TYPES = {"ACSingleWireCAN","MCSingleWireCAN","<invalid>",""}`;
  - `connChargeCable` `"<invalid>"` or `""`;
  - `chargerPower` × 1000 > `chargeCurrentRequestMax` × max(`voltage`, 240) × 1.1.

**Current state:**
- `pluggedNow(v)`: the newest plug value across qualifying sources (TWC, `Gen3TWC`, `TeslaBLE`, and car sources with the newest fix inside) is plugged. Ties go to the strong source (`Gen2TWC`/`Gen3TWC`/`TeslaBLE`).
- `drivingNow(v)`: the newest drive reading is `state == "driving"` or `shiftState` in D/R/N.
- `parkedNow(v)`: `shiftState == "P"`. With no `shiftState` ever observed, it is `not drivingNow(v)` (F4).

**`twcVin` (F2)** is home evidence only while all hold:
- the point still reports a plug: Gen2 slave `reportedState != 0x00`, or Gen3 `vehicle_connected`;
- no `"driveStart"` or `"outside"` mark is newer than its observation.

`observeTwcVin(point, vin)` also clears `twcVin` on any other car attributed to that point (`VehicleRegistry.py:201–240`, +3). A pushed unplug or an outside fix makes it stale through the rule above.

**`H` (home time)** = the newest of:
- a valid `twcVin` observation;
- `markAt("plugIn")`;
- `markAt("contact")`;
- the newest fix inside while `parkedNow` (its `at`).

**`M` (movement time)** = max of `markAt("driveStart")`, `markAt("absent")` and `markAt("unplug")`.

**`presence(master, v)`**, computed fresh. The first match wins; **ties fall through to PRESUMED, which means hold** (F8):
1. `v.isAnonymous` → HOME.
2. The newest fix is outside, and its `at > H` → NOT_HOME.
3. `drivingNow(v)` → PRESUMED. Contact proves presence, not parked (F7).
4. `H > M` → HOME. This is the stickiness: plugged-in or asleep cars produce no movement.
5. `markAt("unplug") > H` → NOT_HOME (a confirmed departure).
6. Otherwise PRESUMED.

**Derived values:**
- `leaving(v)` = max(`markAt("unplug")`, `markAt("driveStart")`).
- `arriving(v)` = max(`markAt("outside")`, `markAt("driveEnd")`).
- `pluggedHere(master, v)` = HOME and `pluggedNow(v)`.
- `homeForLimits` = HOME or PRESUMED.
- `inside(master, v)`: None when home or the position is unknown; otherwise BASE's box test at `atHomeRadius` feet (default 1,000).

**BLE presence (F9).** `bleReach` True comes from every successful exchange (the `_noteBleProof` sites `TeslaBLE.py:488, 517, 652`) and from scans. `bleReach` False comes **only** from a scan miss (:1103) or a ping that gets no answer from VCSEC (Task 3). A command or state-read failure never writes it.

**`candidates(master, capability=None)`** is one definition, used by Tasks 3–5 (F13). It returns non-anonymous cars with no valid `twcVin`, sorted by key:
- **Without a capability** (attribution, T12): `homeForLimits` or here, where here is inside or `bleReach` True ≤ 300 s.
- **With a capability** (broadcasts; F11: only cars BASE reached): `order.candidates(v, capability)` non-empty, plus one of:
  - HOME or PRESUMED and attached to TeslaAPI;
  - a `TeslaBLE` claim and `homeForLimits`;
  - HA-attached, HOME, and `master.getTWCbyVIN(v.vin)` (BASE's HA rule).

**Callers after this task:**
- `presentVehicles` uses `homeForLimits`, with BASE's anonymous rule.
- `_chargeTargets` (:202) uses `candidates(master, capability)`.
- `_restoreDeparted`:
  - With `read=True` (the 5/20/45 reads), for a held car with no valid `twcVin`, call `vehicle.read("chargingState", READ_MAX_AGE)`. No wake. The away-car deferral ladder stays (F11), so the count matches BASE.
  - Restore cars that are NOT_HOME (Task 3 adds HOME-unplugged-leaving). The stale guard compares `markAt("unplug")` with `lastWrite("chargeLimit")`, keeping the `<=` comment.
- TeslaAPI:
  - `updateChargeAtHome` reads HOME cars only.
  - The counts use `Presence.homeCars(master, "TeslaAPI")` (HOME or PRESUMED; renamed from `atHome`, F17).
  - `update_vehicle_data` keeps the ladder with `inside(...)` in place of `car.atHome`, and observes `shiftState`.
- HA caches only `battery_level`; its counts go through `homeCars(master, "HomeAssistant")`.
- `TeslaBLE._scheduleBlocksStart` and the `TeslaBLEProvider.startCharging` schedule branch are deleted (F16). `Belief.handsOff` covers them.
- `recordVehicleVIN` calls `Presence.learnHome(self, vehicle)`.
- `HTTPControl.py:558`: `lastAtHome = presence(...) == HOME` (F11).
- `TWCSlave.pluggedCars` is untouched until Task 5.

**New fields:** `shiftState`, `fastChargerPresent`, `fastChargerType`, `connChargeCable`, `chargerPower`, `chargeCurrentRequestMax`, added to `FIELDS` and `CHARGE_FIELDS`. They are mapped from:
- TeslaAPI (`drive_state.shift_state` and `charge_state` keys);
- `TeslaBLE.get_charge_state` (plus `pluggedIn`);
- TeslaMate (`shift_state`, `charger_power`, `charge_current_request_max`).

**Files:**
- Create `Vehicle/Presence.py`.
- Modify:
  - `Vehicle/Registry/Vehicle.py` (`mark`, `markAt`, the observe hook call);
  - `Vehicle/Registry/VehicleRegistry.py` (`onObserve`; `observeTwcVin` clears others);
  - `Vehicle/Registry/Fields.py`, `Vehicle/Providers/Capability.py`;
  - `Vehicle/Reconcile/Targets.py`;
  - `Vehicle/TeslaAPI.py` (:51, :656–711, :1675–1726, :1901–1925, :1961–2008);
  - `Vehicle/HomeAssistant.py` (:68–73, :152–162, :553–593);
  - `Vehicle/TeslaBLE.py` (:177–191, :488/:517/:652, :660–680), `Vehicle/Providers/TeslaBLEProvider.py:95–98`;
  - `Vehicle/TeslaMateVehicle.py`;
  - `TWCMaster.py` (:37, :202, :364–366, :1563–1572, `__init__` hook wiring);
  - `TWCManager.py:386–387`;
  - `Control/HTTPControl.py:558`.
- Tests: `tests/unit/test_presence.py` (new); rewrites per the mapping.

**Interfaces:**
- Produces (`Presence.py`):
  - `HOME`, `PRESUMED`, `NOT_HOME`;
  - `HOME_RADIUS_FT = 1000`, `HOME_FIX_MAX_AGE = 600.0`, `REACH_WINDOW = 300.0`, `HOME_CHARGER_TYPES`, `_PLUGGED`;
  - `noteObservation(master, vehicle, obs, previous) -> None`;
  - `presence(master, vehicle) -> str`;
  - `homeForLimits`, `pluggedHere`, `pluggedNow`, `drivingNow`;
  - `leaving(v) -> float`, `arriving(v) -> float`;
  - `inside(master, v) -> Optional[bool]`;
  - `candidates(master, capability=None) -> List[Vehicle]`;
  - `homeCars(master, attachment) -> List[Tuple[Vehicle, Any]]`;
  - `learnHome(master, vehicle) -> bool`;
  - `why(master, v) -> str` (the deciding event, for logs).
- Also: `Vehicle.mark(name, at)`, `Vehicle.markAt(name) -> float` (-inf when unset), `VehicleRegistry.onObserve`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_presence.py`, a real registry on a test clock, distinct times per event, F8).

```python
def test_nothing_known_is_presumed():
def test_inside_and_parked_is_home_with_no_shift_state_meaning_not_driving():   # F4
def test_driving_inside_is_presumed_even_with_ble_contact():                   # F7
def test_home_is_sticky_while_plugged_or_asleep():                            # 6 h, no movement
def test_repeated_disconnected_reads_are_not_a_departure():                   # F1, Review Focus 5
def test_an_unplug_event_newer_than_home_evidence_is_a_departure():
def test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix():       # F2, Review Focus 3
def test_twc_vin_counts_only_while_the_twc_reports_a_plug():
def test_another_vin_at_the_point_clears_the_old_cars_twc_vin():
def test_marks_record_events_when_observed_not_when_evaluated():             # incl. a 20 s drive with no evaluation between
def test_lat_and_lon_in_either_order_mark_outside_once():
def test_ble_absence_only_from_a_scan_miss_or_unanswered_ping():             # F9: a command failure writes nothing
def test_ties_resolve_to_presumed():                                          # F8
def test_dc_power_above_the_cars_ac_max_is_not_plug_evidence():
def test_a_fast_charger_inside_the_radius_is_not_home():
def test_a_plugged_report_with_no_cable_is_not_home():
def test_charging_state_maps_to_plug_values():
def test_home_radius_defaults_to_1000_ft_and_config_overrides():
def test_candidates_for_a_broadcast_are_only_cars_base_reached():            # F11, incl. HA at home and on a TWC
def test_counts_include_presumed_cars():
def test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix():
def test_update_charge_at_home_reads_only_home_cars(requests_mock):
def test_away_cars_keep_the_status_deferral_ladder():                         # F11
def test_last_at_home_is_true_only_for_home():                                # F11
def test_policy_wide_apply_skips_a_departed_car_on_every_channel(requests_mock):   # R24
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** and delete the retired names.
- [ ] **Step 4: Rewrite the pinned tests** (mapping) → PASS.
- [ ] **Step 5: Parity** → PASS with no edit beyond `:1306`. Row 26: TeslaMate `Complete` with a fix inside → `plugIn` mark → HOME.
- [ ] **Step 6: Grep** `-w` for `located|_present|broadcastVehicles|update_location|locate|is_location_home|is_location_within_radius|vehicleIsDefinitelyHome|atHome|at_home|_scheduleBlocksStart`. Expected hits:
  - docs (Task 6);
  - `numCarsAtHome`/`minBatteryLevelAtHome`;
  - `TWCMaster.py:1167` (the word "locate" in a log string);
  - parity's `install(located=…)` keyword (`:181, 205, 497, 785, 808`; a test parameter, kept).
- [ ] **Step 7: Full suite** → PASS. **Commit.** `git commit -m "Compute presence from plug, drive, position and BLE events; one home check for every module"`

**Test mapping (Task 2):**

| Test | Fate |
|---|---|
| `test_limit_wiring.py::test_present_rule_until_phase_5` | Renamed `test_present_rule`; assertions unchanged (`[VIN, VIN3]`) (PLUMBING-ONLY) |
| `::test_a_fleet_car_that_unplugs_and_leaves_gets_its_normal_limit_back`, `::test_an_unplug_at_home_is_not_a_departure`, `::test_live_telemetry_places_a_departing_car_for_free` | Kept; `atHome` asserts become `presence`; paid lists unchanged |
| `::test_a_restart_with_the_car_plugged_in_and_asleep_still_gets_the_policy_limit` | `presence == HOME` (PLUMBING-ONLY) |
| `::test_a_held_car_with_no_known_position_is_present` | First half kept; second half INTENTIONALLY CHANGED (a): PRESUMED, but no claim → no desire, no request |
| `::test_a_held_car_with_no_position_or_ble_is_present_for_a_cloud_provider` | Second half INTENTIONALLY CHANGED (b); send sequence pinned in Task 3 |
| `::test_a_car_its_twc_names_stays_at_home_whatever_its_stale_fix_says` | Rewritten: `twcVin` with the TWC at 03 and no newer drive start → HOME (no `car.atHome`) |
| `::test_a_listed_car_not_yet_located_is_in_the_broadcast` | On `candidates(m, START_CHARGING)`: listed and unlocated → PRESUMED → in (as BASE); AWAY → out |
| `::test_an_away_fix_older_than_our_last_limit_write_is_no_departure` | On the `unplug`-mark stale guard |
| `test_twcmaster_vin_confirmation.py:205–256` | `test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix` plus a static check that `recordVehicleVIN` calls `learnHome`. INTENTIONALLY CHANGED (f) |
| `test_reads_no_wake.py`, `test_telemetry_registry.py:214–251` | `vehicle.read("lat", 0)` in place of `update_location`; counts unchanged (PLUMBING-ONLY) |
| `test_teslaapi_providers.py`, `test_teslaapi_registry.py` location Mocks; `:308` | `is_location_home` Mocks deleted; `is_far_from_home` Mocks kept (ladder); `atHome` leaves the tuple (PLUMBING-ONLY) |
| `teslatokens.py:146`, `test_teslaapi_wake.py:79` (`car.atHome = True`) | Lines deleted; the car is placed at HOME through `placeAt` (PLUMBING-ONLY) |
| `reconcile_helpers.py:20` | Comment reworded: presence from events |
| `test_registry_callers.py:257–269` | `lastAtHome` True only for HOME (PLUMBING-ONLY) |
| `test_homeassistant_registry.py:96` | Mock removed; HA coordinates |
| `test_charging_reconciler.py:440–452` (`test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars`) | Kept: the HA car is placed HOME instead of `at_home=True`; the audience is unchanged (F11 HA rule) (PLUMBING-ONLY) |
| `test_provider_outcomes_local.py:28` (`_scheduleBlocksStart`) | Re-pointed at `Belief.handsOff`: the same scheduled car gets no start attempt (PLUMBING-ONLY, F16) |

---

