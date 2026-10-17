### Task 10: Reads cascade BLE then API and never wake (closes A6)

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/Sources.py`.
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:2223-2273` (`update_location`), `:2371-2422` (`update_charge`), `__init__` (register sources); `lib/TWCManager/Vehicle/TeslaBLE.py:98-185` (`__init__`: register the BLE source).
- Test: `tests/unit/test_reads_no_wake.py`.

**Interfaces:**
- Consumes: `ReadSource`, `Vehicle.read`, `TeslaBLE.get_charge_state/get_location_state/wakeVehicle`, `CarApiVehicle.update_vehicle_data`.
- Produces (`Sources.py`):
  - `CHARGE_FIELDS = frozenset({"batteryLevel","chargeLimit","chargingState","availableCurrent","actualCurrent","voltage","phases","scheduledChargingPending","timeToFullCharge"})`, `LOCATION_FIELDS = frozenset({"lat","lon","gpsAsOf"})`.
  - `class TeslaBLEReadSource(ReadSource)`: `__init__(ble, master)`, `name="TeslaBLE"`, `order=0`, `fields=CHARGE_FIELDS|LOCATION_FIELDS`; `canRead(vehicle)` = `vehicle.vin` and `"TeslaBLE" in vehicle.claims` (unpaired keys are never tried: each miss costs the BLE timeout) and the `VehiclePriority.commandPolicy` (via `master.getModuleByName`) is not `"api_only"` (today's behaviour, kept until Phase 2 maps the policy to suppressions); `fetch(vehicle, field, allowWake)`: charge field → `ble.get_charge_state(vin)`, location field → `ble.get_location_state(vin)` mapped to `lat/lon/gpsAsOf`; keys whose value is `None` are dropped from the returned dict (ruling P14, today's behaviour); when the read returns `None` and `allowWake` → `ble.wakeVehicle(vin)` then one retry; never wakes otherwise.
  - `class TeslaAPIReadSource(ReadSource)`: `__init__(carapi)`, `name="TeslaAPI"`, `order=1`, same fields; `canRead(vehicle)` = `vehicle.attachment("TeslaAPI") is not None`; `fetch`: first the **free** online check `car.is_awake()` (`vehicles/{vin}`, cached 2 min, trusts fresh telemetry; Fleet prices: `vehicles/{vin}` free, `vehicle_data` $0.002, wake $0.02) — `False` → return `None` without spending on `vehicle_data`; `True` → `car.update_vehicle_data()` (writes through descriptors) and return `{}` on success, `None` on failure. Never wakes, whatever `allowWake` says (a cloud wake is never worth a read).
  - `class HomeAssistantReadSource` is Task 12.
  - `TeslaAPI.__init__`: `self.registry.registerReadSource(TeslaAPIReadSource(self))`; `TeslaBLE.__init__` (after the binary check passes): `VehicleRegistry.forMaster(master).registerReadSource(TeslaBLEReadSource(self, master))`.
  - `CarApiVehicle.READ_MAX_AGE = 300`; `update_charge()` → `maxAge = READ_MAX_AGE; obs = self.vehicle.read("batteryLevel", maxAge=maxAge)`; returns `obs is not None and (self.vehicle.age("batteryLevel") <= maxAge or time.time() < self.statusDeferral)` (the cascade hands back a stale value when every source fails, which is a failure as today — except during an API `statusDeferral`, when today's code also reports success without fetching; ruling P13); `update_location(minInterval=0)` → same with field `"lat"` and `maxAge = minInterval` (`0` means force a fresh read, as `vehicleIsDefinitelyHome` relies on; ruling P12); on success recompute `self.atHome = carapi.is_location_home(lat, lon, gpsAge)` and `lastAPIAccessTime = now`. No `wakeVehicle` anywhere in either method.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_reads_no_wake.py
import time
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.Registry.Sources import TeslaBLEReadSource, TeslaAPIReadSource
from tests.unit.teslatokens import FakeMaster, new_api
VIN = "5YJ3E1EA1KF000001"

def setup(ble_result):
    master = FakeMaster(); reg = master.vehicleRegistry = VehicleRegistry({})
    ble = Mock(); ble.get_charge_state.return_value = ble_result; ble.get_location_state.return_value = None
    master.modules.update({"VehiclePriority": Mock(commandPolicy="prefer_ble"), "TeslaBLE": ble})
    api = new_api(master=master); api.carApiVehicles = []
    reg.registerReadSource(TeslaBLEReadSource(ble, master)); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.is_awake = Mock(return_value=True)
    # The API source writes through descriptors; the stand-in must too.
    car.update_vehicle_data = Mock(side_effect=lambda: car.vehicle.observe("batteryLevel", 50, "TeslaAPI") and True)
    reg.get(VIN).claim("TeslaBLE", True, "paired")
    return car, ble, reg

def test_ble_read_fills_fields_and_api_untouched():
    car, ble, reg = setup({"batteryLevel": 61, "chargeLimit": 80, "chargingState": "Charging", "phases": None})
    assert car.update_charge() is True
    assert (car.batteryLevel, reg.get(VIN).latest("chargeLimit").source) == (61, "TeslaBLE")
    assert reg.get(VIN).latest("phases") is None                                   # P14: None dropped
    car.update_vehicle_data.assert_not_called(); ble.wakeVehicle.assert_not_called()

def test_api_source_checks_free_online_state_before_paid_vehicle_data():
    car, ble, reg = setup(None); car.is_awake = Mock(return_value=False)
    assert car.update_charge() is False
    car.update_vehicle_data.assert_not_called(); ble.wakeVehicle.assert_not_called()

def test_status_deferral_counts_as_success_without_fetch():      # P13
    car, ble, reg = setup(None); car.update_vehicle_data = Mock(return_value=True)   # deferral path: no observe
    reg.get(VIN).observe("batteryLevel", 40, "TeslaAPI", at=0.0); car.statusDeferral = time.time() + 1800
    assert car.update_charge() is True

def test_update_location_zero_forces_a_fresh_read():            # P12
    car, ble, reg = setup(None); reg.get(VIN).observe("lat", 1.0, "TeslaAPI"); reg.get(VIN).observe("lon", 2.0, "TeslaAPI")
    ble.get_location_state.return_value = {"latitude": 3.0, "longitude": 4.0, "heading": 0, "gpsAsOf": 5}
    car.carapi.is_location_home = Mock(return_value=True)
    assert car.update_location(0) is True and car.lat == 3.0
    ble.get_location_state.assert_called_once()

def test_ble_failure_falls_to_api_without_waking():     # A6
    car, ble, reg = setup(None)
    assert car.update_charge() is True and car.batteryLevel == 50
    car.update_vehicle_data.assert_called_once(); ble.wakeVehicle.assert_not_called()

def test_all_sources_failing_reports_failure_even_with_stale_value():
    car, ble, reg = setup(None); car.update_vehicle_data = Mock(return_value=False)
    reg.get(VIN).observe("batteryLevel", 40, "TeslaAPI", at=0.0)
    assert car.update_charge() is False and car.batteryLevel == 40

def test_unpaired_vin_skips_ble():
    car, ble, reg = setup({"batteryLevel": 1}); reg.get(VIN).dropClaim("TeslaBLE")
    car.update_charge(); ble.get_charge_state.assert_not_called(); car.update_vehicle_data.assert_called_once()

def test_fresh_observation_skips_both():
    car, ble, reg = setup({"batteryLevel": 1}); reg.get(VIN).observe("batteryLevel", 50, "TeslaMateVehicle")
    assert car.update_charge() is True
    ble.get_charge_state.assert_not_called(); car.update_vehicle_data.assert_not_called()

def test_allow_wake_wakes_once_then_retries():
    car, ble, reg = setup(None); ble.wakeVehicle.return_value = True
    ble.get_charge_state.side_effect = [None, {"batteryLevel": 9}]
    assert reg.get(VIN).read("batteryLevel", maxAge=0, allowWake=True).value == 9
    ble.wakeVehicle.assert_called_once_with(VIN)

def test_location_read_recomputes_at_home():
    car, ble, reg = setup(None)
    ble.get_location_state.return_value = {"latitude": 1.0, "longitude": 2.0, "heading": 0, "gpsAsOf": 5}
    car.carapi.is_location_home = Mock(return_value=True)
    assert car.update_location() is True and car.atHome is True and (car.lat, car.lon) == (1.0, 2.0)
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: Sources`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_reads_no_wake.py tests/unit/test_teslaapi_charge_vin.py tests/unit/test_teslable_lock.py -q` → PASS; then the full suite.

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Architecture`: `    * (@MikeBishop) - One vehicle registry keyed by VIN holds every per-vehicle field with its source and age; reads cascade BLE then cloud and never wake a car unless asked; a TWC-reported VIN is confirmed by a second query before a vehicle is created; vehicles unseen for 30 days (config vehicle.forgetAfterDays) are forgotten`
```bash
black lib/TWCManager/Vehicle/Registry/Sources.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaBLE.py
git add lib/TWCManager/Vehicle tests/unit/test_reads_no_wake.py CHANGELOG.md
git commit -m "Read vehicle state through the registry cascade and stop waking cars on reads"
```

