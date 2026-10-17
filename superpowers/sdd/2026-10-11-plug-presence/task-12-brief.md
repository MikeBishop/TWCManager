### Task 12: A BLE-silent car plugged in at home may get a Fleet EVSE

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py` (`bleSilent`), `lib/TWCManager/EVSEController/TeslaAPIController.py` (`allEVSEs`)
- Test: `tests/unit/test_teslaapi_controller.py`

**Interfaces:**
- Produces: `VehiclePresence.bleSilent(vin) -> bool`. It is True when `bleApplies(master, vin)` and the last recorded contact is a failure with no success within `BLE_REACH_MAX_AGE`.
- `allEVSEs`: a car that #694's `blind` or `unknown and telemetry-plugged` rule would exclude is listed anyway when `presence.isPluggedHome(vin)`, `presence.bleSilent(vin)` and `presence.vinForTwc` names no TWC for it, i.e. `vin not in` the `_twcVin` values. Expose that as `presence.isTwcAttributed(vin) -> bool`. With no presence, #694 is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_ble_silent_umc_car_gets_a_fleet_evse_beside_an_idle_vin_less_twc():   # real VehiclePresence: telemetry plugged + inside -> HOME -> nominated probe runs with probePresence unreachable -> bleSilent; unknown=True -> listed
def test_never_probed_car_is_not_ble_silent():   # no contact recorded -> bleSilent False -> #694 exclusion still applies
def test_ble_reachable_car_beside_a_vin_less_twc_gets_no_fleet_evse():
def test_car_attributed_to_a_vin_less_twc_gets_no_fleet_evse():
def test_without_presence_694_rules_are_unchanged():
```

- [ ] **Step 2: Run the tests and confirm they fail**
- [ ] **Step 3: Implement `bleSilent`, `isTwcAttributed` and the `allEVSEs` exception**
- [ ] **Step 4: Run the full suite and confirm it passes**

Run: `<PY> -m pytest tests/unit -q`.

- [ ] **Step 5: Commit**

Subject: `A BLE-silent car plugged in at home may get a Fleet API EVSE`.

---

## Branch `deploy/presence-3`

