### Task 8: Send charge commands to the car the plug evidence names

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py`, `lib/TWCManager/TWCSlave.py`, `lib/TWCManager/Vehicle/TeslaAPI.py` (`car_api_charge`), `lib/TWCManager/Vehicle/TeslaBLE.py` (`car_api_charge`), `lib/TWCManager/Vehicle/HomeAssistant.py` (`car_api_charge`)
- Test: `tests/unit/test_twcslave.py`, `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_teslable_presence.py`, `tests/unit/test_homeassistant_presence.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Consumes: `vinForTwc(twc)` (Task 4), `isHome` and `bleReachable` (Task 2).
- `VehiclePresence.broadcastVINs() -> list[str]`: the known VINs, sorted, that are `isHome(v)` or here (`_inside` True or `bleReachable(v)`). A car that is neither is never included. **Also excluded (user-approved, 2026-10-11):** a car with evidence that it's plugged in somewhere else, i.e. attributed to another TWC (`vinForTwc`), or home with evidence and BLE-silent (on a UMC; `bleSilent` arrives in Task 12, so here use `isPluggedHome(v) and not bleReachable(v) and v not in twcVins()` only when a BLE contact failure is recorded). A purely presumed car stays included until its first read gives evidence. Test: `test_vin_less_broadcast_skips_a_car_plugged_in_elsewhere`.
- `TWCSlave._chargeVIN() -> str | None`: `currentVIN`, else `plugVIN` when it is neither None nor `NON_TESLA`, else `master.vehiclePresence.vinForTwc(self._presenceKey())`, else None. It replaces `self.currentVIN` in the `startCarsCharging`, `stopCarsCharging` and `cancelStopCarsCharging` calls.
- `TeslaAPI.car_api_charge(task)`: `vin = task.get("vin")`. The targets are that vehicle alone, or for `vin` None the vehicles in `presence.broadcastVINs()` (every vehicle when there's no presence). It calls `car_api_available(charge=charge, vin=vin)`. The stop-path reset loop covers only the targets.
- `TeslaBLE.car_api_charge`, for `vin` None: `settings["Vehicles"]` ∩ `presence.broadcastVINs()`.
- `HomeAssistant.car_api_charge`: honours `task["vin"]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_goes_to_the_vin_the_twc_reads():                  # startCarsCharging called with V1 (currentVIN "")->plugVIN
def test_start_on_a_vin_less_twc_goes_to_its_attributed_car():
def test_unattributed_vin_less_start_broadcasts_to_candidates_only():  # V1 inside, V2 NOT_HOME outside -> only V1 commanded
def test_api_charge_with_a_vin_touches_no_other_car():          # charge_start POST only for V1; V2.update_charge not called
def test_ble_broadcast_skips_a_car_away_and_unplugged():
def test_ha_charge_with_a_vin_touches_no_other_car():
def test_broadcast_vins_never_include_an_away_unplugged_car():
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `broadcastVINs`, `_chargeVIN` and the `car_api_charge` targeting in the three modules**

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `Charge commands go to the car the plug names, broadcasts to candidates`.

---

