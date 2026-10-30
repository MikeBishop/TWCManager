### Task 2: An asleep car draws nothing; after Charging it wants nothing

**Files:**
- Modify: `lib/TWCManager/EVSEInstance/VehicleEndpoint.py:45-60, 100-106`
- Test: `tests/unit/test_vehicle_endpoint.py`

**Interfaces:**
- Produces: `VehicleEndpoint.isCharging -> bool`, `VehicleEndpoint.currentAmps -> float` (both already read by `EVSEInstance` callers; today inherited from `EVSEInstance`: read `lib/TWCManager/EVSEInstance/EVSEInstance.py` for their base definitions and keep the same names), `wantsToCharge` sleep-aware.
- Behaviour changes (named): (d) `Presence.asleep(v) is True` ⇒ `isCharging` False and `currentAmps` 0.0; (e) asleep and `chargingState == "Charging"` ⇒ `wantsToCharge` False; asleep and `"Stopped"` ⇒ True as today.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_vehicle_endpoint.py`; use its existing master/registry fixture and `VehicleEndpoint(v, m.providerOrder, m)`)

```python
def endpoint():
    m, r, v, c = setup(here=False)                    # test_limit_reconciler.setup
    placeAt(m, v, HOME); v.observe("pluggedIn", True, "TeslaBLE")
    return m, v, VehicleEndpoint(v, m.providerOrder, m)

def test_asleep_after_charging_releases_its_share():
    m, v, e = endpoint()
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 24, "TeslaBLE")
    assert e.wantsToCharge and e.isCharging and e.currentAmps == 24
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    assert not e.wantsToCharge and not e.isCharging and e.currentAmps == 0

def test_asleep_after_stopped_still_wants_to_charge():
    m, v, e = endpoint()
    v.observe("chargingState", "Stopped", "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    assert e.wantsToCharge and not e.isCharging and e.currentAmps == 0

def test_a_sign_of_life_after_sleep_restores_the_readings():
    m, v, e = endpoint()
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 24, "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "online", "TeslaBLE")
    assert e.wantsToCharge and e.isCharging and e.currentAmps == 24
```

- [ ] **Step 2: Run to verify they fail.** Expected: the first two fail on the asleep assertions.

- [ ] **Step 3: Implement** in `VehicleEndpoint`: a private `_asleep(self) -> bool` returning `Presence.asleep(self.vehicle) is True`; `isCharging` = not asleep and `chargingState == "Charging"`; `currentAmps` = 0.0 when asleep else `vehicle.value("actualCurrent", 0) or 0`; `wantsToCharge` = state in ("Charging", "Stopped") and not (asleep and state == "Charging"). One comment on why Stopped keeps wanting (a start is allowed to wake). `occupied` unchanged.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass; the distributor tests (`test_charging_points.py`, `test_distributor_*.py`) unchanged since their cars are never observed asleep.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/EVSEInstance/VehicleEndpoint.py tests/unit/test_vehicle_endpoint.py
git commit -m "An asleep car draws nothing; asleep after Charging, it has finished"
```

---

