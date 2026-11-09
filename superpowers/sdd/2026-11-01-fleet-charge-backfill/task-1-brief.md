### Task 1: Observe `charge_energy_added`

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Fields.py` (add `"chargeEnergyAdded"` to `FIELDS`, beside the charge fields)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:1872-1891` (`_observeCharge`: add `("charge_energy_added", "chargeEnergyAdded")`)
- Modify: `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py` (the cached and paid Fleet providers' `FIELDS` include it if they enumerate fields)
- Test: `tests/unit/test_watch_cached.py`

**Interfaces:**
- Produces: registry field `"chargeEnergyAdded"` (kWh, float, battery side) observed by every Fleet read path at the snapshot's stamp.

- [ ] **Step 1: Write the failing test**

```python
def test_a_snapshot_carries_the_session_energy(requests_mock):
    m, r, v, c = setup(here=False); chargingFleetCar(requests_mock, m, v)
    requests_mock.get(FLEET + VIN + "/vehicle_data_cached", json={"response": {"charge_state": {
        "timestamp": 1_000_000, "charging_state": "Charging", "charge_energy_added": 1.02}, "vehicle_state": {}}})
    m.getModuleByName("TeslaAPI").read_cached(v)
    obs = v.latest("chargeEnergyAdded"); assert obs.value == 1.02 and obs.at == 1000.0
```

- [ ] **Step 2: Run it, expect FAIL** (`latest` returns None)

Run: `pytest tests/unit/test_watch_cached.py::test_a_snapshot_carries_the_session_energy -v`

- [ ] **Step 3: Add the field and the mapping** (two one-line changes; check `test_registry_fields.py`/`test_provider_tables.py` for field lists that must grow too)

- [ ] **Step 4: Run the test and the registry/provider table tests, expect PASS**

Run: `pytest tests/unit/test_watch_cached.py tests/unit/test_registry_fields.py tests/unit/test_provider_tables.py -q`

- [ ] **Step 5: Commit** `feat: observe the Fleet session energy (charge_energy_added)`

---

