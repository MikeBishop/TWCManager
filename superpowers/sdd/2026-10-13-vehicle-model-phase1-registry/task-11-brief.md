### Task 11: Telemetry attaches to registry vehicles (closes A34)

**Files:**
- Modify: `lib/TWCManager/Vehicle/Telemetry.py` (`applyDataToVehicle`, `updateVehicles`, new `vinFor`), `lib/TWCManager/Vehicle/TeslaMateVehicle.py:62-100` (events, `__init__`, new `loadCarVINs`), `lib/TWCManager/Vehicle/FleetTelemetryMQTT.py:17-30,38-110` (events, `mqttMessage`).
- Modify tests: `tests/unit/test_telemetry_mapping.py` (rewrite against the registry), `tests/unit/test_teslamate_plugged_in.py` (unchanged assertions still hold).
- Test: `tests/unit/test_telemetry_registry.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.forMaster/getOrCreate/findByName`, `Vehicle.observe/latest`.
- Produces:
  - `TelmetryBase.registry` = `VehicleRegistry.forMaster(master)` (set in `__init__` before the enabled check returns).
  - Feed liveness (spec "Report-on-change sources"): the concrete detection is **MQTT connection state, plus TeslaMate's per-car `healthy` topic** (ruling P8) — `TelmetryBase.connected: bool`, set True in `TelmetryBase.mqttConnect`, False in `mqttDisconnect` and at the start of `resetMQTT`; both subclasses' `mqttConnect` overrides call `super().mqttConnect(...)` first (today neither does). `TelmetryBase.feedLiveAt(vehicle) -> Optional[float]` = `time.time()` when `self.connected and self.carHealthy(vehicle)` else `None`; base `carHealthy` returns True. `TeslaMateVehicle` subscribes to `teslamate/cars/+/healthy` as well, routes it in `mqttMessage` to `noteHealthy(car_id, payload)` (`self.healthy[car_id] = payload.strip().lower() == "true"`), and `carHealthy(vehicle)` returns `self.healthy.get(id, True)` for the car id mapped to that vehicle (unpublished → assume healthy; "fresh only if TeslaMate is healthy and still polling"). `__init__` registers `self.registry.registerLiveness(self.__class__.__name__, self.feedLiveAt)`. (Per-car "last message" was rejected: a sleeping car legitimately sends nothing for hours on a healthy feed; paho's keepalive already proves the broker link.) So a connected, healthy feed makes telemetry fields age 0 and lets `trusted()` resolve the own-write case after `FEED_LAG`; a disconnected or unhealthy feed makes them age from the last change and never overrides our write.
  - `FleetTelemetryMQTT.mqttMessage` reads the previous state as `obs = self.vehicles[vin].latest("state") if self.vehicles.get(vin) else None; syncState = obs.value if obs else None`.
  - `TelmetryBase.vinFor(self, vehicle_id) -> Optional[str]`: base returns `None`; `FleetTelemetryMQTT.vinFor` returns `vehicle_id` (its topic id is the VIN); `TeslaMateVehicle.vinFor` returns `self.carVINs.get(str(vehicle_id))`.
  - `TeslaMateVehicle.loadCarVINs() -> Dict[str, str]`: when `db_host/db_name/db_user/db_pass` are all set, `SELECT id, vin FROM cars` via `psycopg2` (connection errors logged at INFO, returns `{}`); called once in `__init__` (independent of `syncTokens`); stored in `self.carVINs`.
  - `TelmetryBase.vehicles: Dict[str, Vehicle]` now maps telemetry id → registry `Vehicle`.
  - `updateVehicles(vehicle_id, vehicle_name, loadList=True) -> bool`: if mapped → observe `name` and return True; `vin = self.vinFor(vehicle_id)` → `registry.getOrCreate(vin, self.__class__.__name__)`, observe `name`, map, log INFO, return True; else `registry.findByName(vehicle_name)`; else (as today) when `loadList` and TeslaAPI is present and `not carapi.getCarApiRetryRemaining()`: `carapi.loadVehicleList()` then `findByName` again; else warn and return False.
  - `applyDataToVehicle(id, event, payload)`: for a mapped vehicle `vehicle.observe(field, converter(payload), source=self.__class__.__name__)`; unmapped → park in `unknownVehicles` (unchanged); no `syncSource`/`syncTimestamp` writes.
  - Event tables map to registry field names: TeslaMate `latitude→lat`, `longitude→lon`, `state→state`; FleetTelemetry `latitude→lat`, `longitude→lon`, `syncState→state`. With no assigner left, delete the transitional `syncSource` setter, `syncTimestamp` setter, `syncState`, `syncLat`, `syncLon` and `_legacySyncSource` from `CarApiVehicle` (the `syncSource`/`syncTimestamp` getters stay for `_telemetryPluggedIn`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_telemetry_registry.py
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.Telemetry import TelmetryBase
from TWCManager.Vehicle.TeslaMateVehicle import TeslaMateVehicle
from TWCManager.Vehicle.FleetTelemetryMQTT import FleetTelemetryMQTT
VIN = "5YJ3E1EA1KF000001"

class Probe(TelmetryBase):
    configName = "Probe"; unmappedRetrySecs = 3600
    events = {"charge_limit_soc": ["chargeLimit", int], "latitude": ["lat", float]}
    def scheduleUnmappedRetry(self, delay=None): self.scheduled = True

def make(cls=Probe, carapi=None, vins=None, clock=None):
    reg = VehicleRegistry({}, **({"clock": clock} if clock else {})); master = Mock(); master.vehicleRegistry = reg
    master.config = {"config": {}, "vehicle": {cls.configName: {"enabled": True}}}
    master.getModuleByName = Mock(return_value=carapi)
    t = cls(master)
    if vins is not None: t.carVINs = vins
    return t, reg

def test_vin_keyed_telemetry_creates_registry_vehicle_and_observes_with_source():
    t, reg = make(); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "charge_limit_soc", "80")      # before the name: parked
    assert reg.vehicles() == [] and t.unknownVehicles["1"] == [["charge_limit_soc", "80"]]
    t.applyDataToVehicle("1", "display_name", "TestCar")   # maps and replays at once
    v = reg.get(VIN)
    assert v.name == "TestCar" and t.vehicles["1"] is v
    assert (v.latest("chargeLimit").value, v.latest("chargeLimit").source) == (80, "Probe")

def test_name_match_against_registry_without_cloud_list():
    t, reg = make(); reg.getOrCreate(VIN, "TeslaBLE").observe("name", "TestCar", "TeslaAPI")
    assert t.updateVehicles("1", "TestCar", loadList=False) is True
    assert t.vehicles["1"] is reg.get(VIN)

def test_unidentifiable_car_is_parked_and_never_raises():   # Review Focus 4
    t, reg = make()
    t.applyDataToVehicle("1", "charge_limit_soc", "80"); t.applyDataToVehicle("1", "display_name", "Ghost")
    assert "1" not in t.vehicles and t.unknownVehicles["1"] == [["charge_limit_soc", "80"]] and t.scheduled
    assert reg.vehicles() == []

def test_task9_legacy_sync_names_are_gone():
    from TWCManager.Vehicle.TeslaAPI import CarApiVehicle
    assert not any(hasattr(CarApiVehicle, n) for n in ("syncState", "syncLat", "syncLon", "_legacySyncSource"))

def test_connection_state_is_the_feed_liveness():
    t, reg = make(); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "display_name", "TestCar"); v = reg.get(VIN)
    v.observe("chargeLimit", 50, "Probe", at=0.0)
    assert reg.sourceLiveAt("Probe") is None and v.age("chargeLimit") > 1e6     # not connected yet
    t.mqttConnect(None, None, None, 0)
    assert v.age("chargeLimit") < 1.0                                          # healthy feed: value is current
    t.mqttDisconnect(None, None, None, 7)
    assert reg.sourceLiveAt("Probe", v) is None

def test_subclass_connects_set_liveness_and_teslamate_healthy_gates_it(monkeypatch):   # P8
    monkeypatch.setattr(TeslaMateVehicle, "loadCarVINs", lambda self: {"7": VIN})
    monkeypatch.setattr(TeslaMateVehicle, "doSyncTokens", lambda self, firstrun=False: None)
    t, reg = make(TeslaMateVehicle); client = Mock()
    t.mqttConnect(client, None, None, 0)
    assert t.connected and any("healthy" in c.args[0] for c in client.subscribe.call_args_list)
    t.applyDataToVehicle("7", "display_name", "C"); v = reg.get(VIN)
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is not None
    t.noteHealthy("7", "false")
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is None
    t.noteHealthy("7", "true")
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is not None
    f, _ = make(FleetTelemetryMQTT); f.mqtt_prefix = "telemetry"; f.client = Mock()
    f.mqttConnect(f.client, None, None, 0)
    assert f.connected

def test_own_write_then_silent_healthy_feed_is_trusted_after_feed_lag():   # 09:17 shape, end to end
    from TWCManager.Vehicle.Registry.Fields import FEED_LAG
    now = {"t": 1000.0}
    t, reg = make(clock=lambda: now["t"]); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "display_name", "C"); v = reg.get(VIN); t.mqttConnect(None, None, None, 0)
    t.applyDataToVehicle("1", "charge_limit_soc", "50")          # TeslaMate value from before our write
    v.noteWrite("chargeLimit", 100, "TeslaBLE")                  # we write 100 at t
    now["t"] = 1003.0
    assert v.trusted("chargeLimit") is None                      # t+3 s: not trusted, apply uses 100
    now["t"] = 1000.0 + FEED_LAG + 1
    assert v.trusted("chargeLimit").value == 50                  # healthy feed, no change event: write did not land
    t.mqttDisconnect(None, None, None, 7)
    assert v.trusted("chargeLimit") is None                      # feed down: silence proves nothing

def test_teslamate_maps_by_db_vin(monkeypatch):
    monkeypatch.setattr(TeslaMateVehicle, "loadCarVINs", lambda self: {"7": VIN})
    monkeypatch.setattr(TeslaMateVehicle, "doSyncTokens", lambda self, firstrun=False: None)
    t, reg = make(TeslaMateVehicle)
    assert t.vinFor("7") == VIN and t.vinFor("8") is None
    assert TeslaMateVehicle.events["latitude"][0] == "lat" and TeslaMateVehicle.events["state"][0] == "state"

def test_fleet_telemetry_topic_id_is_the_vin():
    t, reg = make(FleetTelemetryMQTT)
    assert t.vinFor(VIN) == VIN and FleetTelemetryMQTT.events["syncState"][0] == "state"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: vinFor`).

- [ ] **Step 3: Implement** per Interfaces; rewrite `tests/unit/test_telemetry_mapping.py` so `FakeCarApi.loadVehicleList` populates the registry (`registry.getOrCreate(...).observe("name", ...)`) and assertions check `t.vehicles["1"] is registry.get(VIN)` and observation sources instead of `syncSource`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_telemetry_registry.py tests/unit/test_telemetry_mapping.py tests/unit/test_teslamate_plugged_in.py tests/unit/test_telemetry_timers.py tests/unit/test_teslamate_token_sync.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Telemetry.py lib/TWCManager/Vehicle/TeslaMateVehicle.py lib/TWCManager/Vehicle/FleetTelemetryMQTT.py
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Attach telemetry to registry vehicles by VIN (TeslaMate DB, Fleet topic) or name"
```

