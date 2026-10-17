### Task 3: Sleep-safe evidence probes and startup discovery

**Files:**
- Modify: `lib/TWCManager/PresenceSources.py`, `lib/TWCManager/VehiclePresence.py` (`_probe`, `start`), `lib/TWCManager/Vehicle/TeslaBLE.py` (`get_charge_state`), `lib/TWCManager/TWCSlave.py` (remove the nominations)
- Test: `tests/unit/test_presence_sources.py`, `tests/unit/test_vehicle_presence.py`, `tests/unit/test_teslable_presence.py`, `tests/unit/test_twcslave.py`

**Interfaces:**
- Produces, in `PresenceSources.py`: each source is `callable(vin) -> None | dict` and returns a subset of the Evidence keys: `reach: bool`, `pluggedIn: bool|None`, `inside: bool|None`, `pilot: float|None`, `actual: float|None`, `fastChargerType: str|None`, `fastChargerPresent: bool|None`. The `"limit"` key is removed.
  - `telemetrySource` gives `inside` (None while home is unset) and `pluggedIn` from `telemetryPluggedIn`. It applies only while telemetry is live.
  - `bleSource` gives `reach` from `probePresence`. Only when the probe says the car is awake does it call `get_charge_state` and add `pluggedIn`, `pilot` (=`availableCurrent`), `actual`, `fastChargerType` and `fastChargerPresent`. It returns None for a VIN that isn't in `settings["Vehicles"]`. Reach False is recorded for every car in Vehicles. `bleProven` gating moves to `bleApplies` (Task 5).
  - `apiSource` is unchanged in shape and keeps its online-only rule. It gives `inside` (raw `_locationAtHome`; None while home is unset), and `pluggedIn = chargingState != "Disconnected"`, which is None when chargingState is `"Unknown"`, plus `fastChargerPresent`.
- `VehiclePresence._probe(vin, bleOnly=False) -> dict` merges every applicable source: `reach` from ble; `pluggedIn` from ble, else telemetry, else api, with the source name kept; `inside` from telemetry, else api. `runPass` applies the result as `contact(reach, probe=True)`, `plugState(pluggedIn, source, edge=False, fastCharger=...)` and `location(inside)`, in that order.
- `nominate(vin, reason, delays)` keeps its meaning of "probe this VIN (None = every known VIN) at those times". `start()` calls `nominate(None, "startup")` once.
- TeslaBLE: module-level `blePluggedIn(cs: dict) -> bool | None`, where `cs` is the raw `chargeState`. True if `chargePortLatch` is Engaged, or `connChargeCable` contains "SAE" or "IEC", or `chargingState` is anything but Disconnected/None. False if `chargingState` is Disconnected and the latch isn't Engaged. Otherwise None. Enum values go through `_extract_enum_value`. `get_charge_state` adds the keys `pluggedIn`, `chargePortLatch`, `connChargeCable`, `chargeCurrentRequest`, `fastChargerType` and `fastChargerPresent`.
- TWCSlave: remove `_nominatePresence` and `_presenceVIN` and their three call sites (power-start, power-drop 300/1200/2700, unplug 300/1200/2700). Location isn't polled any more. HTTPControl's `nominate(None, "api")` stays.

- [ ] **Step 1: Write the failing tests**

```python
# test_teslable_presence.py
@pytest.mark.parametrize("cs,expected", [
    ({"chargePortLatch": "ChargePortLatchEngaged", "chargingState": "Stopped"}, True),
    ({"connChargeCable": "ChargeCableTypeSAE"}, True),
    ({"chargingState": "Disconnected", "chargePortLatch": "ChargePortLatchDisengaged"}, False),
    ({}, None)])
def test_ble_plugged_in_derivation(cs, expected): assert blePluggedIn(cs) is expected
def test_get_charge_state_exposes_plug_and_pilot_fields():  # keys pluggedIn, availableCurrent==47, fastChargerType=="ACSingleWireCAN"
# test_presence_sources.py
def test_ble_source_reads_charge_only_when_awake():   # awake False -> get_charge_state not called; result == {"reach": True}
def test_ble_source_reports_unreachable_as_reach_false():
def test_api_source_never_queries_an_offline_car():   # vehicleOnlineStates -> "asleep": update_vehicle_data not called
def test_api_source_reports_plug_and_fast_charger():
def test_telemetry_source_gives_inside_and_plugged():
# test_vehicle_presence.py
def test_startup_nominates_every_known_vin_once():
def test_probe_of_an_asleep_ble_car_keeps_it_presumed():  # reach True, no read -> PRESUMED, contact recorded
def test_probe_merges_ble_plug_over_telemetry():          # ble pluggedIn False, telemetry True -> plugState source "ble"
def test_ble_only_probe_calls_only_the_ble_source():
# test_twcslave.py: TestPresenceTriggers
def test_twc_events_nominate_nothing():  # power-start, power-drop, unplug: master.vehiclePresence.nominate.assert_not_called()
```

Delete the old nomination tests in `TestPresenceTriggers`: `test_power_start_nominates_current_vin_now`, `test_power_drop_nominates_with_departure_delays` and `test_unplug_without_a_power_drop_still_nominates`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `<PY> -m pytest tests/unit/test_presence_sources.py tests/unit/test_vehicle_presence.py tests/unit/test_teslable_presence.py tests/unit/test_twcslave.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement the sources, `_probe`, startup nominate, `blePluggedIn` and the `get_charge_state` keys; remove the TWCSlave nominations**

- [ ] **Step 4: Run the same tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `Presence probes gather sleep-safe plug evidence; startup discovers`.

---

