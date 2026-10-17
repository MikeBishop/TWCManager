### Task 6: Discovery on wake: every command path reads before it acts

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py` (`discover`), `lib/TWCManager/Vehicle/TeslaBLE.py`, `lib/TWCManager/Vehicle/TeslaAPI.py`, `lib/TWCManager/Vehicle/Telemetry.py`
- Test: `tests/unit/test_teslable_presence.py`, `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_telemetry_timers.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Produces: `VehiclePresence.discover(vin, pluggedIn: bool | None, source: str, inside: bool | None = None, fastCharger: bool = False) -> bool`. It runs synchronously, is record-only (it calls `observePlugState(..., edge=False)` and `observeLocation` for the values it's given) and does no I/O. It returns False when `pluggedIn is False`, when `fastCharger` is set, or when `inside is False and not bleReachable(vin)`. Otherwise it returns True. Callers use it only for applies with `limit != -1` and for charge starts. A restore is never gated.
- TeslaBLE:
  - `get_charge_state` reports every successful read with `observePlugState(vin, pluggedIn, "ble", fastCharger=fastChargerPresent is True)` when `pluggedIn` isn't None.
  - `_readChargeLimit` becomes `_readChargeState(vin) -> dict | None`. It keeps the breaker check and gives the limit as `["chargeLimit"]`.
  - In `applyChargeLimit`, for `limit != -1`, after the read (or the telemetry lookup, which uses `telemetryPluggedIn` as its plug value): if presence exists and `not presence.discover(vin, plugged, source)`, send nothing, count the car as skipped, log INFO `"%s is not plugged in here; charge limit not sent"`, and leave `_stopTryingToApplyLimit` unset.
  - A start whose output `_is_already_satisfied` with "disconnected" reports `observePlugState(vin, False, "ble")`.
- TeslaAPI:
  - `update_vehicle_data` reports `observePlugState(vin, charging_state != "Disconnected", "api", fastCharger=charge.get("fast_charger_present") is True)` when `charging_state` is present.
  - `CarApiVehicle.lastVehicleDataFetch`: a new attribute, set to `time.monotonic()` by every successful `update_vehicle_data`.
  - `applyChargeLimit`, for `limit != -1` and per vehicle after `update_charge`: if `not presence.discover(vin, plugged, "api", inside=vehicle._locationAtHome if lastVehicleDataFetch changed during this call else None, fastCharger=...)`, it skips the vehicle. Here `plugged` is False for `"Disconnected"`, None for `"Unknown"`, and True otherwise. There is no extra `update_location()` call: an API read already includes location, a BLE read is strong, and telemetry pushes its location.
  - `car_api_charge` puts the same gate after its `update_charge`/`update_location`, ahead of the carried `"Disconnected"/"Complete"` skip.
- Telemetry `_reportPlug(vehicle, previous, pluggedIn)`: the first bool value (`previous` isn't a bool) is reported with `observeTelemetryPlug(vin, value, edge=False)`, and a change with `edge=True`. This replaces 94cf1c5's "the retained value is not a change".

- [ ] **Step 1: Write the failing tests**

```python
def test_ble_apply_to_a_car_read_as_unplugged_sends_nothing():   # charging-set-limit never sent; presence.state -> DEPARTING after runPass (was HOME)
def test_ble_restore_is_never_gated():                           # limit -1 with read unplugged -> charging-set-limit sent
def test_ble_read_reports_plug_state():                          # observePlugState called with (V1, True, "ble", fastCharger=False)
def test_ble_start_answered_disconnected_reports_unplugged():
def test_api_vehicle_data_reports_plug_and_fast_charger():
def test_presumed_car_found_away_on_the_fleet_path_gets_nothing():  # PRESUMED, BLE breaker open, Fleet read: Disconnected + outside -> no set_charge_limit POST; after runPass state NOT_HOME
def test_presumed_plugged_car_on_the_fleet_path_gets_the_limit():
def test_api_charge_start_skips_a_car_at_a_supercharger():        # fast_charger_present True -> no charge_start
def test_retained_telemetry_value_is_reported_once_as_a_read():   # first value -> observeTelemetryPlug(V, True, edge=False); same value again -> nothing
def test_telemetry_change_is_reported_as_an_edge():
def test_discover_returns_false_outside_radius_without_ble():
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `discover`, the TeslaBLE/TeslaAPI reports and gates, and the Telemetry initial-value report**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_teslable_presence.py tests/unit/test_teslaapi_presence.py tests/unit/test_telemetry_timers.py tests/unit/test_vehicle_presence.py -q`.

- [ ] **Step 5: Commit**

Subject: `Read before acting: a car read as unplugged or away gets nothing`.

---

