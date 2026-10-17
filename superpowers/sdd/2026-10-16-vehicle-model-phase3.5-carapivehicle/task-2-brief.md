### Task 2: The registry answers sync state; nothing outside TeslaAPI reads CarApiVehicle's data (expected lib Δ ≈ −20)

Callers outside TeslaAPI stop reading `CarApiVehicle` data attributes. The sync-source rule moves to the registry `Vehicle`, where Task 3's `is_awake` also needs it. Two dead members go: `actualCurrent`'s change timing, which nothing in lib reads. `RegistryField` stays until Task 3, because `CarApiVehicle`'s own methods still use it.

**Files:**
- Modify `lib/TWCManager/Vehicle/Registry/Vehicle.py`: add `SYNC_TIMEOUT`, `telemetryState()` and `syncSource`, and import `TELEMETRY_SOURCES` from `.Fields`.
- Modify `Vehicle/TeslaAPI.py`:
  - Delete `CarApiVehicle.syncTimeout/_telemetryState/syncSource`, the `actualCurrent` property and setter, and `lastCurrentChangeTime`.
  - The descriptor `_actualCurrent` becomes `actualCurrent = RegistryField("actualCurrent", 0)`.
  - `update_charge` loses its change timing.
  - `is_awake` calls `vehicle.telemetryState()` on `self._liveVehicle()`, returning `(None, None)` when that is None: the same no-create read as today. Its `self.syncTimeout / 4` becomes `Vehicle.SYNC_TIMEOUT / 4`.
- Modify `TWCSlave.py` (`getLastVehicle`), `Control/HTTPControl.py:509–514`, `TWCMaster.py:679–692`, `EVSEController/VehicleEndpoints.py:81–90,122`, and `Vehicle/Reconcile/Targets.py:66,136`.

**Interfaces:**
- `Vehicle.SYNC_TIMEOUT = 60 * 60`. The comment moves verbatim from `CarApiVehicle.syncTimeout`.
- `Vehicle.telemetryState(self) -> Tuple[Optional[Observation], Optional[float]]`: `(latest "state", None)` unless its source is in `TELEMETRY_SOURCES`, when it is `(obs, self.age("state"))`. This is `_telemetryState` verbatim.
- `Vehicle.syncSource` (property, str): `obs.source` when the age is not None and is ≤ `SYNC_TIMEOUT`, else `"TeslaAPI"`.
- `TWCSlave.getLastVehicle() -> Optional[Vehicle]`: the registry `Vehicle` for `currentVIN`, then `lastVIN`, that has a `"TeslaAPI"` attachment. It is still a lookup only: it never creates a vehicle.
- `/api/getSlaveTWCs` reads, for a non-None `vehicle`:
  - `lastAtHome = vehicle.attachment("TeslaAPI").atHome`;
  - `lastBatterySOC = vehicle.value("batteryLevel", 10000)`;
  - `lastChargeLimit = vehicle.value("chargeLimit", -1)`;
  - `lastTimeToFullCharge = vehicle.value("timeToFullCharge", 0.0)`.
- `TWCMaster.getScheduledAmpsTimeFlex` reads `vehicle.value("chargeLimit", -1)` and `vehicle.value("batteryLevel", 10000)` at each of its three reads.
- `VehicleEndpoints._telemetryPluggedIn(vehicle)` takes the registry vehicle and returns `vehicle.syncSource != "TeslaAPI" and vehicle.value("pluggedIn") is True`. Its caller at :122 passes `vehicle`, not `car`.
- `Targets.broadcastVehicles.reached` checks `v.value("lat", 10000) == 10000` in place of `getattr(api, "lat", 0) == 10000`.
- `Targets._restoreDeparted` checks `vehicle.syncSource == "TeslaAPI"`.

- [ ] **Step 1: Characterization tests (pass at BASE and after).**
  - `tests/unit/test_registry_callers.py::test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults`. A listed car with no observations gives `lastAtHome False`, `lastBatterySOC 10000`, `lastChargeLimit -1`, `lastTimeToFullCharge 0.0`. After observing 61 / 80 / 1.5 and setting `atHome`, the endpoint reports those values. Use the `_handler(master)` helper already in that file.
  - `tests/unit/test_registry_callers.py::test_flex_start_reads_the_listed_cars_limit_and_battery`. No test covers `TWCMaster.getScheduledAmpsTimeFlex` at BASE. One TWC whose `lastVIN` is a listed car, with `scheduledAmpsFlexStart` on, `scheduledAmpsMax` > 0 (else `TWCMaster.py:682` divides by zero; pre-flight F17), limit 80 and battery 40, gives the same `startHour` at BASE and after. A second case, with no observations, uses the -1 / 10000 defaults; record today's value and pin it.
- [ ] **Step 2: Interface tests (fail first).** In `tests/unit/test_registry_vehicle.py`:
  - `test_sync_source_is_a_fresh_telemetry_state_else_teslaapi`: no state gives `"TeslaAPI"`; TeslaMate "online" just now gives `"TeslaMateVehicle"`; a TeslaMate state 3,601 s old on an untracked feed gives `"TeslaAPI"`; a `"TeslaAPI"`-sourced state gives `"TeslaAPI"`.
  - `test_telemetry_state_ages_only_telemetry`.
- [ ] **Step 3: Retarget existing tests** (plumbing unless noted):
  - `test_registry_callers.py::test_get_last_vehicle_uses_registry_attachment`: `getLastVehicle() is car` becomes `is reg.get(VIN)` (**INTENTIONALLY CHANGED**: the return type is the registry Vehicle; Task 2 interface).
  - `test_carapivehicle_registry.py`:
    - `car.syncSource` becomes `reg.get(VIN).syncSource` in `test_is_awake_trusts_fresh_telemetry_and_asleep_without_api_call`, `test_sync_getters_have_legacy_defaults_before_any_state`, `test_stale_telemetry_falls_back_to_api_check` and `test_telemetry_feed_drives_a_real_car`;
    - `car.pluggedIn` becomes `reg.get(VIN).value("pluggedIn")`.
  - The other `syncSource` readers (pre-flight F1; this is the complete list at BASE):
    - `test_limit_wiring.py:202` (`car.syncSource`);
    - `test_telemetry_registry.py:264–272`.
    - `test_teslaapi_providers.py`, `test_teslaapi_readonly_gate.py` and `test_reads_no_wake.py` have **no** `syncSource` reader; leave them to Task 3.
  - **Stub-driven test (F1):** `test_vehicle_endpoint.py::test_controller_lists_at_home_api_cars_and_keeps_blind_rules` (l.64) attaches a `SimpleNamespace(syncSource=…, pluggedIn=…)` as "TeslaAPI". `_telemetryPluggedIn` now reads the registry, so the stub fields stop driving it. Instead, observe `state` from `"TeslaMateVehicle"` and `pluggedIn=True` on the registry vehicle (plumbing; assertions unchanged). Check `test_charging_points.py` and `test_gen2_idle_minimum.py` for the same stub shape and treat them the same way.
  - Deleted, mapped (F2):
    - `test_carapivehicle_registry.py::test_actual_current_change_time_only_moves_on_change`, **PLUMBING-ONLY**: `lastCurrentChangeTime` has no reader in lib at BASE (`git grep -n lastCurrentChangeTime -- lib` shows only TeslaAPI's own writes).
    - `test_reads_no_wake.py::test_ble_actual_current_change_is_timed` (l.158–163), **PLUMBING-ONLY** for the same reason. Its other half, `latest("actualCurrent").source == "TeslaBLE"`, is covered by `test_ble_read_fills_fields_and_api_untouched`.
  - `test_attributes_are_observations_with_source_and_defaults` drops its two `actualCurrent`/`lastCurrentChangeTime` lines (plumbing). Its `latest("actualCurrent")` assertion stays, now written through the `actualCurrent` descriptor.
- [ ] **Step 4: Implement**, deleting the replaced members in the same commit.
- [ ] **Step 5: Full suite** → PASS. Grep: `git grep -nE '\.syncSource|_telemetryState|syncTimeout|lastCurrentChangeTime' -- lib html tests/integration tests/API` shows only `Vehicle.py`, `TeslaAPI.is_awake`'s registry call, Targets and VehicleEndpoints.
- [ ] **Step 6: Commit.** `git commit -m "The registry vehicle answers sync state; callers read registry fields, not CarApiVehicle"`

**Review focus (Task 2):**
- Every new `value(field, D)` uses the descriptor default from the table above.
- `getLastVehicle` still returns None for an unlisted car and never creates one.
- `VehicleEndpoints.allEVSEs` lists exactly the same cars (its `atHome` read is untouched).

---

