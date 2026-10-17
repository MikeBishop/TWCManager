### Task 6: Source adapters, the `presenceSources` setting, TeslaAPI online check and location reporting

**Files:**
- Create: `lib/TWCManager/PresenceSources.py`
- Modify: `lib/TWCManager/VehiclePresence.py` (`__init__` default for `sources`)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (add `vehicleOnlineStates` after `getCarApiVehicles`, line 1123; add `CarApiVehicle._reportLocation`; call it at lines 1762-1764 and 1831)
- Modify: `etc/twcmanager/config.json:822` (document `presenceSources`)
- Test: `tests/unit/test_presence_sources.py` (create), `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Consumes: `TeslaBLE.probePresence(vin)`, `TeslaBLE.get_charge_state(vin) -> {"chargeLimit": ...} | None` (existing), `TeslaAPI.getCarApiVehicles()`, `TeslaAPI.getCarApiBearerToken()`, `TeslaAPI.is_location_home(lat, lon)`, `CarApiVehicle.update_vehicle_data()`, `CarApiVehicle.syncSource/syncLat/syncLon/chargeLimit/atHome/statusDeferral`.
- Produces (`lib/TWCManager/PresenceSources.py`):
  - `telemetrySource(master) -> callable(vin)`, `bleSource(master) -> callable(vin)`, `apiSource(master) -> callable(vin)`; each returns `None` (not applicable) or `{"atHome": bool|None, "limit": int|None}`.
  - `buildSources(master) -> {"telemetry": ..., "ble": ..., "api": ...}`.
  - `VehiclePresence(master)` with `sources=None` now uses `buildSources(master)`.
  - `TeslaAPI.vehicleOnlineStates() -> {VIN: state}` from one GET of the vehicle list; `{}` on any failure.
  - `CarApiVehicle._reportLocation()` calls `master.vehiclePresence.observeLocation(VIN, atHome)` after every location read.

- [ ] **Step 1: Write the failing source adapter tests**

Create `tests/unit/test_presence_sources.py`:

```python
"""
Presence source adapters. Each adapter is a callable(vin) that returns None
when the source does not apply, or {"atHome": bool | None, "limit": int | None}.
"""

from unittest.mock import Mock

import pytest

from TWCManager.PresenceSources import (
    apiSource,
    bleSource,
    buildSources,
    telemetrySource,
)

VIN = "5YJ3E1EA1KF000001"


class FakeVehicle:
    def __init__(self, syncSource="TeslaAPI", fetchResult=True):
        self.VIN = VIN
        self.syncSource = syncSource
        self.syncLat = 10000
        self.syncLon = 10000
        self.chargeLimit = -1
        self.atHome = False
        self.statusDeferral = 9e12
        self.fetchResult = fetchResult
        self.updates = 0
        self.deferralAtUpdate = None

    def update_vehicle_data(self):
        self.updates += 1
        self.deferralAtUpdate = self.statusDeferral
        if self.fetchResult:
            self.atHome = True
            self.chargeLimit = 80
        return self.fetchResult


def make_master(api=None, ble=None):
    master = Mock()
    modules = {"TeslaAPI": api, "TeslaBLE": ble}
    master.getModuleByName = Mock(side_effect=lambda name: modules.get(name))
    return master


def make_api(vehicle=None, token="token", states=None):
    api = Mock()
    api.getCarApiVehicles = Mock(return_value=[vehicle] if vehicle else [])
    api.getCarApiBearerToken = Mock(return_value=token)
    api.vehicleOnlineStates = Mock(return_value=states or {})
    # Home is at latitude 1.0 in these tests.
    api.is_location_home = Mock(side_effect=lambda lat, lon: lat == 1.0)
    return api


def make_ble(reachable, awake, charge=None):
    ble = Mock()
    ble.probePresence = Mock(return_value={"reachable": reachable, "awake": awake})
    ble.get_charge_state = Mock(return_value=charge)
    return ble


class TestTelemetrySource:
    def test_not_applicable_without_api_vehicle(self):
        assert telemetrySource(make_master())(VIN) is None
        assert telemetrySource(make_master(api=make_api()))(VIN) is None

    def test_not_applicable_when_telemetry_is_not_live(self):
        vehicle = FakeVehicle(syncSource="TeslaAPI")
        vehicle.syncLat = vehicle.syncLon = 1.0
        assert telemetrySource(make_master(api=make_api(vehicle)))(VIN) is None

    def test_not_applicable_without_a_fix(self):
        vehicle = FakeVehicle(syncSource="TeslaMateVehicle")
        assert telemetrySource(make_master(api=make_api(vehicle)))(VIN) is None

    def test_live_fix_inside_geofence_is_home_with_limit(self):
        vehicle = FakeVehicle(syncSource="TeslaMateVehicle")
        vehicle.syncLat = vehicle.syncLon = 1.0
        vehicle.chargeLimit = 80
        source = telemetrySource(make_master(api=make_api(vehicle)))
        assert source(VIN) == {"atHome": True, "limit": 80}

    def test_live_fix_outside_geofence_is_away_without_limit(self):
        vehicle = FakeVehicle(syncSource="TeslaMateVehicle")
        vehicle.syncLat, vehicle.syncLon = 2.0, 1.0
        source = telemetrySource(make_master(api=make_api(vehicle)))
        assert source(VIN) == {"atHome": False, "limit": None}


class TestBleSource:
    def test_not_applicable_without_ble(self):
        assert bleSource(make_master())(VIN) is None

    def test_unreachable_is_no_answer_and_reads_nothing(self):
        ble = make_ble(reachable=False, awake=False)
        assert bleSource(make_master(ble=ble))(VIN) == {"atHome": None, "limit": None}
        ble.get_charge_state.assert_not_called()

    def test_reachable_asleep_is_home_and_never_reads_state(self):
        ble = make_ble(reachable=True, awake=False)
        assert bleSource(make_master(ble=ble))(VIN) == {"atHome": True, "limit": None}
        ble.get_charge_state.assert_not_called()

    def test_reachable_awake_reads_the_limit(self):
        ble = make_ble(reachable=True, awake=True, charge={"chargeLimit": 80})
        assert bleSource(make_master(ble=ble))(VIN) == {"atHome": True, "limit": 80}
        ble.get_charge_state.assert_called_once_with(VIN)

    def test_awake_with_failed_state_read_is_still_home(self):
        ble = make_ble(reachable=True, awake=True, charge=None)
        assert bleSource(make_master(ble=ble))(VIN) == {"atHome": True, "limit": None}


class TestApiSource:
    def test_not_applicable_without_api_or_vehicle(self):
        assert apiSource(make_master())(VIN) is None
        assert apiSource(make_master(api=make_api()))(VIN) is None

    def test_not_applicable_without_a_token(self):
        api = make_api(FakeVehicle(), token="")
        assert apiSource(make_master(api=api))(VIN) is None
        api.vehicleOnlineStates.assert_not_called()

    @pytest.mark.parametrize("state", ["asleep", "offline", None])
    def test_not_online_is_no_answer_and_reads_nothing(self, state):
        vehicle = FakeVehicle()
        api = make_api(vehicle, states={VIN: state} if state else {})
        assert apiSource(make_master(api=api))(VIN) == {"atHome": None, "limit": None}
        assert vehicle.updates == 0

    def test_online_reads_location_and_limit_bypassing_deferral(self):
        vehicle = FakeVehicle()
        api = make_api(vehicle, states={VIN: "online"})
        assert apiSource(make_master(api=api))(VIN) == {"atHome": True, "limit": 80}
        assert vehicle.updates == 1
        assert vehicle.deferralAtUpdate == 0

    def test_online_but_fetch_fails_is_no_answer(self):
        vehicle = FakeVehicle(fetchResult=False)
        api = make_api(vehicle, states={VIN: "online"})
        assert apiSource(make_master(api=api))(VIN) == {"atHome": None, "limit": None}


def test_build_sources_names_all_three():
    sources = buildSources(Mock())
    assert set(sources) == {"telemetry", "ble", "api"}
    assert all(callable(fn) for fn in sources.values())
```

Append to `tests/unit/test_teslaapi_presence.py`:

```python
class TestVehicleOnlineStates:
    def test_parses_the_vehicle_list(self):
        api = make_api()
        api.baseURL = "https://proxy.example/api/1/vehicles"
        response = Mock()
        response.text = json.dumps(
            {"response": [{"vin": VIN1, "state": "asleep"}, {"vin": VIN2, "state": "online"}]}
        )
        with patch("TWCManager.Vehicle.TeslaAPI.requests.get", return_value=response) as get:
            assert api.vehicleOnlineStates() == {VIN1: "asleep", VIN2: "online"}
        assert get.call_args[0][0] == "https://proxy.example/api/1/vehicles"

    def test_failure_gives_empty_dict(self):
        import requests

        api = make_api()
        api.baseURL = "https://proxy.example/api/1/vehicles"
        with patch(
            "TWCManager.Vehicle.TeslaAPI.requests.get",
            side_effect=requests.exceptions.ConnectionError("down"),
        ):
            assert api.vehicleOnlineStates() == {}

    def test_no_token_or_url_reads_nothing(self):
        api = make_api()
        api.carApiBearerToken = ""
        with patch("TWCManager.Vehicle.TeslaAPI.requests.get") as get:
            assert api.vehicleOnlineStates() == {}
        get.assert_not_called()


class TestLocationReporting:
    def test_update_vehicle_data_reports_location(self):
        from TWCManager.Vehicle.TeslaAPI import CarApiVehicle

        carapi = Mock()
        carapi.is_location_home = Mock(return_value=True)
        carapi.getCarApiBaseURL = Mock(return_value="https://proxy.example/api/1/vehicles")
        vehicle = CarApiVehicle({"id": 1, "vin": VIN1, "display_name": "Car"}, carapi, {"config": {}})
        vehicle.statusDeferral = 0
        vehicle.get_car_api = Mock(
            return_value=(
                True,
                {
                    "drive_state": {"latitude": 1.0, "longitude": 2.0, "gps_as_of": 0},
                    "charge_state": {"charge_limit_soc": 80},
                    "vehicle_state": {"vehicle_name": "Car"},
                },
            )
        )
        assert vehicle.update_vehicle_data() is True
        carapi.master.vehiclePresence.observeLocation.assert_called_once_with(VIN1, True)
        assert vehicle.chargeLimit == 80
```

Add `import json` to the imports at the top of `tests/unit/test_teslaapi_presence.py`.

Append to `tests/unit/test_vehicle_presence.py`:

```python
class TestDefaults:
    def test_default_sources_are_built_from_the_master(self):
        master = Mock()
        master.config = {"config": {}}
        presence = VehiclePresence(master, knownVehicles=lambda: [])
        assert presence._order == ["telemetry", "ble", "api"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_presence_sources.py tests/unit/test_teslaapi_presence.py tests/unit/test_vehicle_presence.py -q -p no:cacheprovider`
Expected: collection error for `test_presence_sources.py` (`No module named 'TWCManager.PresenceSources'`); run the other two files alone and expect 4 failures (`vehicleOnlineStates` missing; `observeLocation` not called; `_order == []`).

- [ ] **Step 3: Implement the adapters**

Create `lib/TWCManager/PresenceSources.py`:

```python
# Presence sources: adapters from the vehicle modules to VehiclePresence.
#
# Each factory takes the master and returns a callable(vin) that answers
#   None                                  the source does not apply to this VIN
#   {"atHome": True | False, "limit": n}  a definite answer (limit may be None)
#   {"atHome": None, "limit": None}       the source applies but has no answer
#
# None of them ever wakes a car: telemetry is a push feed, the BLE probe talks
# to the body controller only and the API path first checks that the car is
# already online.
from TWCManager.Logging.LoggerFactory import LoggerFactory

logger = LoggerFactory.get_logger("PresenceSources", "Vehicle")

NO_ANSWER = {"atHome": None, "limit": None}


def _apiVehicle(master, vin):
    # (TeslaAPI module, CarApiVehicle) for this VIN, or (None, None).
    api = master.getModuleByName("TeslaAPI")
    if not api:
        return None, None
    for vehicle in api.getCarApiVehicles():
        if vehicle.VIN == vin:
            return api, vehicle
    return api, None


def _limit(vehicle):
    limit = getattr(vehicle, "chargeLimit", None)
    return limit if limit is not None and limit > 0 else None


def telemetrySource(master):
    # Applies when a telemetry module (TeslaMate, Fleet Telemetry) is live
    # for this vehicle: its syncSource is that module, not "TeslaAPI".
    # TeslaMate keeps the last fix of a parked car, so a stale timestamp
    # still gives the right position.
    def probe(vin):
        api, vehicle = _apiVehicle(master, vin)
        if vehicle is None or vehicle.syncSource == "TeslaAPI":
            return None
        if vehicle.syncLat == 10000 or vehicle.syncLon == 10000:
            return None
        atHome = api.is_location_home(vehicle.syncLat, vehicle.syncLon)
        return {"atHome": bool(atHome), "limit": _limit(vehicle)}

    return probe


def bleSource(master):
    # body-controller-state answers while the car sleeps. The charge limit
    # is read only when the probe reported the car awake, so a sleeping car
    # is never woken for it.
    def probe(vin):
        ble = master.getModuleByName("TeslaBLE")
        if not ble:
            return None
        result = ble.probePresence(vin)
        if not result.get("reachable"):
            return dict(NO_ANSWER)
        limit = None
        if result.get("awake"):
            charge = ble.get_charge_state(vin)
            if charge and charge.get("chargeLimit") is not None:
                limit = charge["chargeLimit"]
        return {"atHome": True, "limit": limit}

    return probe


def apiSource(master):
    # Online check first (the vehicle list endpoint does not wake the car).
    # Only an online car is asked for its location and charge state. A
    # sleeping or offline car is a non-answer: it hasn't moved since it fell
    # asleep, so its presence stays as it was.
    def probe(vin):
        api, vehicle = _apiVehicle(master, vin)
        if vehicle is None or not api.getCarApiBearerToken():
            return None
        if api.vehicleOnlineStates().get(vin) != "online":
            return dict(NO_ANSWER)
        # update_vehicle_data() returns True without fetching while deferred.
        vehicle.statusDeferral = 0
        if not vehicle.update_vehicle_data():
            return dict(NO_ANSWER)
        return {"atHome": bool(vehicle.atHome), "limit": _limit(vehicle)}

    return probe


def buildSources(master):
    return {
        "telemetry": telemetrySource(master),
        "ble": bleSource(master),
        "api": apiSource(master),
    }
```

In `lib/TWCManager/VehiclePresence.py`, add the import after `from TWCManager.Logging.LoggerFactory import LoggerFactory`:

```python
from TWCManager.PresenceSources import buildSources
```

and change the `sources` default line in `__init__` from `self._sources = {} if sources is None else dict(sources)` to:

```python
        self._sources = buildSources(master) if sources is None else dict(sources)
```

In `lib/TWCManager/Vehicle/TeslaAPI.py`, add after `getCarApiVehicles` (after line 1123):

```python
    def vehicleOnlineStates(self):
        # One GET of the vehicle list: it reports each car's state
        # (online / asleep / offline) without waking anything. Returns
        # {VIN: state}, or {} when the list can't be read.
        url = self.getCarApiBaseURL()
        if not self.getCarApiBearerToken() or not url:
            return {}
        headers = {
            "accept": "application/json",
            "Authorization": "Bearer " + self.getCarApiBearerToken(),
        }
        try:
            req = requests.get(url, headers=headers, verify=self.verifyCert)
            req.raise_for_status()
            response = json.loads(req.text).get("response") or []
        except (
            requests.exceptions.RequestException,
            json.decoder.JSONDecodeError,
            AttributeError,
            TypeError,
        ) as e:
            logger.debug("Could not read the vehicle list for presence: %s", e)
            return {}
        return {
            v.get("vin"): v.get("state")
            for v in response
            if isinstance(v, dict) and v.get("vin")
        }
```

In `class CarApiVehicle`, add after `checkSyncNotStale` (before `def ready`):

```python
    def _reportLocation(self):
        # Presence is tracked outside this module; tell it about every
        # location we read. VehiclePresence only records, so this is cheap.
        presence = getattr(self.carapi.master, "vehiclePresence", None)
        if presence is None:
            return
        try:
            presence.observeLocation(self.VIN, bool(self.atHome))
        except Exception as e:
            logger.debug("observeLocation failed for %s: %s", self.VIN, e)
```

In `update_location`, after the BLE-branch assignment (lines 1762-1764):

```python
                        self.atHome = self.carapi.is_location_home(
                            self.lat, self.lon, gpsAge
                        )
```
add on the next line (same indentation):
```python
                        self._reportLocation()
```

In `update_vehicle_data`, after line 1831 (`self.atHome = self.carapi.is_location_home(self.lat, self.lon, gpsAge)`) add:

```python
            self._reportLocation()
```

In `etc/twcmanager/config.json`, after the `#"commandPolicy": "prefer_ble",` line (822) add:

```
        # presenceSources is the ordered list of sources used to decide
        # whether each car is at home: "telemetry" (TeslaMate / Fleet Telemetry
        # position), "ble" (a body-controller-state probe that does not wake
        # the car) and "api" (Fleet API, only when the car is already online).
        # The first source with a definite answer decides. Remove entries you
        # don't want consulted. The default is:
        #"presenceSources": ["telemetry", "ble", "api"],
```

- [ ] **Step 4: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `605 passed, 1 warning`.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/PresenceSources.py lib/TWCManager/VehiclePresence.py lib/TWCManager/Vehicle/TeslaAPI.py etc/twcmanager/config.json tests/unit/test_presence_sources.py tests/unit/test_teslaapi_presence.py tests/unit/test_vehicle_presence.py
git commit -m "$(cat <<'EOF'
Add presence sources: telemetry, BLE probe and online-only API

Each source answers home/away (and the current limit when it can read
one) without waking the car. The API source checks the vehicle list
for online status before reading location, and TeslaAPI now reports
every location it reads to VehiclePresence. vehicle.presenceSources
sets the order.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

