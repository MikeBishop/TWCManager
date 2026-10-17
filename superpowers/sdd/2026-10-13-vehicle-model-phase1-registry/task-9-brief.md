### Task 9: `CarApiVehicle` backed by the registry

Migration approach for `CarApiVehicle`: the class stays, every caller keeps `vehicle.batteryLevel`, `vehicle.VIN`, `vehicle.name` etc., but the per-vehicle *field* attributes become descriptors over `self.vehicle` (the registry `Vehicle`). Reads return the latest observation's value (or the legacy default); writes record an observation with source `"TeslaAPI"`. The per-vehicle `checkSyncNotStale` thread goes: "sync" is now "the latest observation's source and age". The `syncSource`/`syncTimestamp`/`syncState`/`syncLat`/`syncLon` names stay **assignable** in this task (their setters map onto observations, ruling P7) so that `Telemetry.py`, which still assigns them until Task 11, keeps working between the two tasks; Task 11 deletes the five. Command-dedupe flags (`stopAskingToStartCharging`, `stopTryingToApplyLimit`, `lastChargeRateSent`, wake timers, `atHome`, `statusDeferral`) stay plain attributes (Phase 3/5 remove them).

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:116-165` (`__init__`, `addVehicle`), `:1975-2120` (`CarApiVehicle` class attrs, `__init__`, `checkSyncNotStale`, `is_awake`), `:2424-2431` (`actualCurrent`).
- Modify tests that monkeypatch `teslaapi.Thread` (`tests/unit/test_teslaapi_charge_vin.py`, `tests/unit/teslatokens.py` `no_threads`, any other `grep -l '"Thread"' tests/unit`): drop the patch lines (the thread no longer exists).
- Test: `tests/unit/test_carapivehicle_registry.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.forMaster`, `Vehicle.observe/latest/age/claim/attach`, `TELEMETRY_SOURCES`.
- Produces:
  - `TeslaAPI.__init__`: `self.registry = VehicleRegistry.forMaster(master)`.
  - `class RegistryField:` descriptor in `TeslaAPI.py`: `RegistryField(field: str, default: Any, source="TeslaAPI")`; `__get__` → `instance.vehicle.latest(field).value` or `default`; `__set__` → `instance.vehicle.observe(field, value, source)`.
  - `CarApiVehicle` descriptors: `name ("")`, `batteryLevel (10000)`, `chargeLimit (-1)`, `chargingState ("Unknown")`, `availableCurrent (0)`, `voltage (0)`, `phases (0)`, `timeToFullCharge (0.0)`, `scheduledChargingPending (False)`, `lat (10000)`, `lon (10000)`, `gpsAsOf (0)`, `pluggedIn (None)`; `actualCurrent` keeps its property (backing field `"actualCurrent"`, `lastCurrentChangeTime` updated on change).
  - `CarApiVehicle.__init__(json, carapi, config)`: `self.vehicle = carapi.registry.getOrCreate(json["vin"], "TeslaAPI")`; `self.vehicle.attach("TeslaAPI", self)`; `self.vehicle.claim("TeslaAPI", lambda: not carapi.readOnly, "listed")`; `self.name = json["display_name"] or VIN or str(ID) or "unknown"` (an observation with `seen=True`: a cloud listing is a sighting, ruling 4). No thread.
  - `TeslaAPI.getVehicleByVIN(vin) -> CarApiVehicle | False`; `apiDebugInterface(command, vin, parameters)` resolves the car by VIN (ruling 2; the Fleet API paths already use the VIN, so the numeric `ID` is no longer needed by any command).
  - `CarApiVehicle.syncSource` → property: getter returns the source of `latest("state")` when it is in `TELEMETRY_SOURCES` and `age("state") <= syncTimeout` (3600), else `"TeslaAPI"`; setter stores `self._legacySyncSource = value` (the source the legacy telemetry code will write with next). `syncTimestamp` → getter `latest("state").at` or 0; setter is a no-op (observation times come from `observe`). `syncState`, `syncLat`, `syncLon` → properties whose setters call `self.vehicle.observe("state"|"lat"|"lon", value, source=self._legacySyncSource or "TeslaAPI")` and whose getters read the fields. (`TeslaAPIController._telemetryPluggedIn` keeps working unchanged.)
  - `update_vehicle_data()` observes only keys present in the response: `if "charge_limit_soc" in charge: self.chargeLimit = charge["charge_limit_soc"]` etc., never `charge.get(key, self.x)` (ruling P15: a carried-over or default value must not become a fresh `"TeslaAPI"` observation).
  - `is_awake()`: `obs = self.vehicle.latest("state")`; if `obs and obs.source in TELEMETRY_SOURCES`: `asleep|offline` → False; fresh (`age <= syncTimeout/4`) → `obs.value in ("online","charging","updating","driving")`; otherwise fall through to the existing 2-minute-cached API check (which does **not** write `state`, so a telemetry "asleep" keeps suppressing paid calls as today).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_carapivehicle_registry.py
from unittest.mock import Mock
from tests.unit.teslatokens import FakeMaster, fleet_token, new_api
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

def api_with_registry():
    master = FakeMaster(); master.vehicleRegistry = VehicleRegistry({})
    api = new_api(master=master); api.carApiVehicles = []
    return api, master.vehicleRegistry

def test_vehicle_joins_registry_and_claims_teslaapi():
    api, reg = api_with_registry()
    api.addVehicle({"id": 1, "vin": VIN, "display_name": "TestCar"})
    v = reg.get(VIN)
    assert v.attachment("TeslaAPI") is api.getCarApiVehicles()[0] and v.name == "TestCar"
    api.fleetSlot.clear()
    assert v.tier == "observed"            # no command slot: read-only
    api.fleetSlot.setTokens(fleet_token())
    assert v.tier == "managed"

def test_attributes_are_observations_with_source_and_defaults():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]
    assert car.batteryLevel == 10000 and car.chargeLimit == -1 and car.lat == 10000
    car.chargeLimit = 80
    obs = reg.get(VIN).latest("chargeLimit")
    assert (obs.value, obs.source) == (80, "TeslaAPI") and car.chargeLimit == 80
    car.actualCurrent = 12; assert car.lastCurrentChangeTime > 0 and car.actualCurrent == 12

def test_master_without_registry_gets_a_private_one():
    api = new_api(); api.carApiVehicles = []
    api.addVehicle({"id": 1, "vin": "V1", "display_name": "x"})
    assert api.getCarApiVehicles()[0].VIN == "V1" and isinstance(api.registry, VehicleRegistry)

def test_is_awake_trusts_fresh_telemetry_and_asleep_without_api_call():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.get_car_api = Mock(side_effect=AssertionError("no API call"))
    reg.get(VIN).observe("state", "asleep", "TeslaMateVehicle")
    assert car.is_awake() is False and car.syncSource == "TeslaMateVehicle"
    reg.get(VIN).observe("state", "online", "TeslaMateVehicle")
    assert car.is_awake() is True

def test_legacy_sync_setters_still_feed_the_registry():          # P7: Telemetry assigns these until Task 11
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.get_car_api = Mock(side_effect=AssertionError("no API call"))
    car.syncTimestamp = 123.0; car.syncSource = "TeslaMateVehicle"; car.syncState = "asleep"; car.syncLat = 1.5
    obs = reg.get(VIN).latest("state")
    assert (obs.value, obs.source) == ("asleep", "TeslaMateVehicle") and reg.get(VIN).latest("lat").value == 1.5
    assert car.is_awake() is False and car.syncSource == "TeslaMateVehicle" and car.syncTimestamp == obs.at

def test_update_vehicle_data_observes_only_present_keys():        # P15
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; reg.get(VIN).observe("phases", 3, "TeslaBLE", at=5.0)
    car.get_car_api = Mock(return_value=(True, {"drive_state": {"latitude": 1.0, "longitude": 2.0},
                                                "charge_state": {"battery_level": 61}, "vehicle_state": {}}))
    car.carapi.is_location_home = Mock(return_value=False); car.carapi.is_far_from_home = Mock(return_value=False)
    assert car.update_vehicle_data() is True
    phases = reg.get(VIN).latest("phases")
    assert car.batteryLevel == 61 and (phases.value, phases.source, phases.at) == (3, "TeslaBLE", 5.0)   # untouched
    assert reg.get(VIN).latest("chargeLimit") is None                                                   # no default observed

def test_debug_interface_resolves_by_vin():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    api.wakeVehicle = Mock()
    assert api.apiDebugInterface("wakeVehicle", VIN, "{}") is True
    api.wakeVehicle.assert_called_once_with(api.getCarApiVehicles()[0])
    assert api.apiDebugInterface("wakeVehicle", "5YJ3E1EA1KF000009", "{}") is False

def test_stale_telemetry_falls_back_to_api_check():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]
    reg.get(VIN).observe("state", "online", "TeslaMateVehicle", at=0.0)
    car.get_car_api = Mock(return_value=(True, {"state": "asleep"}))
    assert car.is_awake() is False and car.get_car_api.called and car.syncSource == "TeslaAPI"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TeslaAPI' object has no attribute 'registry'`).

- [ ] **Step 3: Implement** per Interfaces. Remove `checkSyncNotStale` and the `Thread` import; replace the sync class attributes with the properties above; `update_location`'s `else` branch (sync path) becomes: compute `atHome` from `lat/lon` (Task 10 rewrites the method anyway). Drop the `Thread` monkeypatches in tests.

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests/unit -q` → PASS (expect to touch assertions in `test_teslaapi_*` only where they set `syncSource`/`syncLat` directly: replace with `vehicle.vehicle.observe(...)`).

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/TeslaAPI.py
git add lib/TWCManager/Vehicle/TeslaAPI.py tests/unit
git commit -m "Back CarApiVehicle fields with the registry and derive sync state from observation source and age"
```

