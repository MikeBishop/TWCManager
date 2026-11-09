import json

from TWCManager.Control import Views
from TWCManager.Control.Views import fingerprint, jsonSafe
from tests.unit.live_helpers import callAPI
from unittest.mock import Mock


def test_fingerprint_is_stable_and_shape_sensitive():
    assert fingerprint("a", ["x"]) == fingerprint("a", ["x"])
    assert fingerprint("a", ["x"]) != fingerprint("a", ["y"])
    assert len(fingerprint()) == 12


def test_fingerprint_changes_with_start_time(monkeypatch):
    before = fingerprint("a")
    monkeypatch.setattr(Views, "STARTED", Views.STARTED + 1)
    assert fingerprint("a") != before


def test_json_safe_non_finite_and_objects():
    out = jsonSafe({"a": float("nan"), "b": [float("inf"), 1.5], 3: object, "c": (1,)})
    assert out["a"] is None and out["b"] == [None, 1.5] and out["c"] == [1]
    assert out["3"].startswith("<class")
    json.loads(json.dumps(out, allow_nan=False))


def test_call_api_records_status_headers_body():
    m = Mock()
    m.config = {"config": {}}
    status, headers, body = callAPI(m, "/api/getConfig")
    assert status == 200 and headers["Content-type"] == "application/json"
    assert isinstance(json.loads(body), dict)


def test_send_json_headers_and_safety():
    import io
    from TWCManager.Control.HTTPControl import CreateHTTPHandlerClass
    cls = CreateHTTPHandlerClass(Mock())
    h = cls.__new__(cls)
    h.url = Mock(path="/x"); h.client_address = ("127.0.0.1", 0); h.wfile = io.BytesIO()
    seen = {}
    h.send_response = lambda c, m=None: seen.__setitem__("code", c)
    h.send_header = lambda k, v: seen.__setitem__(k, v)
    h.end_headers = lambda: None
    h.sendJSON({"a": float("nan")}, 201)
    assert seen["code"] == 201 and seen["Cache-Control"] == "no-store"
    assert json.loads(h.wfile.getvalue()) == {"a": None}


# /api/getChargingPoints

import pytest
from unittest.mock import MagicMock, patch
from TWCManager.Control.Views import chargingPointsView, slaveTotals
from TWCManager.EVSEInstance.Gen3TWC import Gen3TWC
from TWCManager.Vehicle.Reconcile.Desired import AMPS
from TWCManager.Vehicle.Registry.Vehicle import Vehicle
from tests.unit.test_charging_points import VIN, VIN2, car, real
from tests.unit.test_gen3twc_provider import vitals


def emptyVitals(unit):
    # A reachable unit whose vitals carry none of the fields read
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = b"{}"
    with patch("urllib.request.urlopen", return_value=resp):
        assert unit.refreshVitals()


def withGen2AndCars(m):
    # A Gen2 TWC with its car, and a car on no TWC rated 16 A
    s = m.newSlave(b"\x82\x44", 80)
    s.currentVIN = VIN; s.reportedAmpsMax = 32; s.reportedAmpsActual = 10.5
    s.lastAmpsOffered = 16.333; s.lifetimekWh = 1234; s.isCharging = 1
    car(m, VIN, "Charging")
    car(m, VIN2, "Charging")
    m.desired.set(VIN2, AMPS, 16, "distributor")
    return m


@pytest.fixture
def gen2_master():
    return withGen2AndCars(real())


@pytest.fixture
def mixed_master():
    # ...and a Gen3 unit with no car
    m = withGen2AndCars(real(gen3=True))
    (u,) = m.getModuleByName("Gen3TWCs").devices()
    vitals(u, False, 0.0, state="not_connected")
    return m


@pytest.fixture
def idle_master():
    m = real(gen3=True)
    m.newSlave(b"\x82\x44", 80)
    (u,) = m.getModuleByName("Gen3TWCs").devices()
    emptyVitals(u)
    return m


def test_slave_totals_match_get_slave_twcs(gen2_master):
    status, _, body = callAPI(gen2_master, "/api/getSlaveTWCs")
    total = json.loads(body)["total"]
    assert total == slaveTotals(gen2_master)
    assert total["lastAmpsOffered"] == 32.33  # the TWC's 16.333 and the car's 16


def test_points_list_every_kind(mixed_master):  # one Gen2 with car, one Gen3, one car-only
    view = chargingPointsView(mixed_master)
    kinds = sorted(tuple(p["controllers"]) for p in view["points"])
    assert ("Gen3TWCs",) in kinds and ("VehicleEndpoints",) in kinds
    gen2 = next(p for p in view["points"] if p["gen2"])
    assert gen2["gen2"]["twcid"] == "8244" and gen2["vin"] == VIN
    assert gen2["local"] is True and gen2["ampsOffered"] == 16.333
    assert gen2["ampsDrawn"] == 10.5 and gen2["gen2"]["chargingSince"] is None
    car = next(p for p in view["points"] if p["controllers"] == ["VehicleEndpoints"])
    assert car["local"] is False and car["ampsOffered"] == 16  # its desired AMPS
    assert car["gen2"] is None and car["vin"] == VIN2
    assert view["total"] == slaveTotals(mixed_master)


def test_points_with_missing_facts(idle_master):  # Review Focus 4
    view = chargingPointsView(idle_master)  # idle Gen2 (no car), Gen3 with empty vitals
    assert len(view["points"]) == 2
    for p in view["points"]:
        assert p["vin"] is None and p["name"] == "" and p["soc"] is None
        assert isinstance(p["ampsDrawn"], float)
    json.dumps(view, allow_nan=False)


def test_points_route_headers(mixed_master):
    status, headers, body = callAPI(mixed_master, "/api/getChargingPoints")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert json.loads(body)["fingerprint"] == fingerprint("home")


def test_points_never_fetch(mixed_master, monkeypatch):
    monkeypatch.setattr(Gen3TWC, "refreshVitals", Mock(side_effect=AssertionError))
    monkeypatch.setattr(Vehicle, "read", Mock(side_effect=AssertionError))
    chargingPointsView(mixed_master)
