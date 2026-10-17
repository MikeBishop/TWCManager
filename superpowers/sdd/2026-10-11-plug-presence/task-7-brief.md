### Task 7: HOME is the only "home": wakes, policy-wide applies, HomeAssistant, Fleet EVSEs, counts

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`car_api_available`), `lib/TWCManager/Vehicle/HomeAssistant.py`, `lib/TWCManager/EVSEController/TeslaAPIController.py`
- Test: `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_homeassistant_presence.py`, `tests/unit/test_teslaapi_controller_presence.py` (new; branch 2 has no controller tests, and branch 5's `ace0fef` creates `test_teslaapi_controller.py`, so a separate file avoids an add/add conflict in Task 11)

**Interfaces:**
- Consumes: `isHome` and `isPluggedHome` (Task 2).
- `car_api_available` wake loop: `if not vehicle.atHome: continue`. The `vehicle.lat != 10000` clause goes away, because presence is the authority.
- HomeAssistant: `_atHome(self, v) -> bool` returns `presence.isHome(v.vin)` when `master.vehiclePresence` exists and `v.vin` is set, and `v.at_home` otherwise. It is used in `car_api_charge`, `applyChargeLimit`, `numCarsAtHome` and `minBatteryLevelAtHome`.
- `TeslaAPIController.allEVSEs`: lists a vehicle only if `presence.isPluggedHome(v.VIN)`, or `v.atHome` when there is no presence. A presumed car gets no Fleet EVSE, because an EVSE sends rates without reading first.
- `numCarsAtHome`, `minBatteryLevelAtHome`, `updateChargeAtHome` and `vehicleScheduledChargingPending` keep reading `atHome`, which now counts HOME and PRESUMED cars.

- [ ] **Step 1: Write the failing tests**

```python
def test_asleep_plugged_car_is_woken_to_charge():         # HOME, ready() False -> wakeVehicle called
def test_asleep_unplugged_car_is_never_woken():           # NOT_HOME with lat 10000 -> wakeVehicle not called
def test_departing_car_is_never_woken():
def test_counts_include_only_plugged_or_presumed_cars():  # V1 HOME, V2 NOT_HOME, V3 DEPARTING -> numCarsAtHome == 1; minBatteryLevelAtHome == V1.batteryLevel
def test_update_charge_at_home_skips_unplugged_cars():
def test_scheduled_charging_pending_ignores_unplugged_cars():
def test_ha_policy_wide_apply_skips_a_departing_car():     # set_value not called
def test_ha_charge_uses_presence_over_its_own_location():
def test_fleet_evse_only_for_a_plugged_home_car():         # HOME -> listed; PRESUMED, DEPARTING -> not listed
def test_policy_wide_apply_skips_departing_on_every_channel():  # VehiclePriority(prefer_ble) + TeslaBLE + TeslaAPI + HA; DEPARTING V1 -> no sendCommand, no POST, no set_value
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement the wake rule, `_atHome` in HomeAssistant and the EVSE filter**

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `HOME is the single meaning of at home for wakes, applies and EVSEs`.

---

