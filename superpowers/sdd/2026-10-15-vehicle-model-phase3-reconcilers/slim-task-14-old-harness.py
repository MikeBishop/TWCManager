# Slim Task 14 "old" harness: the parity table's scenarios run against
# origin/main (03d7932). Real TeslaAPI (requests_mock counts every request),
# real TeslaBLE (only the tesla-control run is replaced), real
# VehiclePriority, called the way main's VehicleCommandQueue dispatches:
# applyChargeLimit every policy pass (30 s), car_api_charge per heartbeat
# start/stop request, setChargeRate per queued rate. Time is a test clock.
import collections
import json
import logging
import re
import threading
import time
import types
from unittest.mock import Mock, patch

import pytest
import requests
from requests_mock import ANY

from tests.unit.teslatokens import FakeMaster, fleet_token, new_api, owner_token

VIN = "5YJ3E1EA1KF000001"
VIN2 = "5YJ3E1EA1KF000002"
FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/"
HOME = (37.0, -122.0)  # FakeMaster.getHomeLatLon
AWAY = (40.0, -86.0)
PRICE = {"vehicle_data": 0.002, "wake_up": 0.02, "command": 0.001}
RESULTS = {}
OUT = __file__ + ".results.jsonl"
logging.disable(logging.CRITICAL)


def counts(requests_mock):
    out = dict.fromkeys(("vehicle_data", "wake_up", "command", "ha", "free", "other"), 0)
    for q in requests_mock.request_history:
        path = q.url.split("?")[0]
        if "fleet-api" not in path and re.search(r"/(vehicle_data|wake_up|command/)", path):
            out["free"] += 1
        elif "/command/" in path:
            out["command"] += 1
        elif path.endswith("/wake_up"):
            out["wake_up"] += 1
        elif path.endswith("/vehicle_data"):
            out["vehicle_data"] += 1
        elif "/api/services/" in path:
            out["ha"] += 1
        elif re.search(r"/api/1/(vehicles|products)(/[^/]+)?$|/live_status$", path):
            out["free"] += 1
        else:
            out["other"] += 1
    return out


def paid(requests_mock):
    c = counts(requests_mock)
    return (c["vehicle_data"], c["wake_up"], c["command"])


def dollars(requests_mock):
    c = counts(requests_mock)
    return round(sum(PRICE[k] * c[k] for k in PRICE), 4)


def commands(requests_mock):
    return [q.url.split("?")[0].rsplit("/", 1)[-1] for q in requests_mock.request_history if "/command/" in q.url]


def record(name, requests_mock, ble=None, **extra):
    cmds = commands(requests_mock)
    RESULTS[name] = dict(counts(requests_mock), dollars=dollars(requests_mock),
                         commands=dict(collections.Counter(cmds)), firstCommands=cmds[:6],
                         ble=dict(collections.Counter(c for v, c, a in ble.runs)) if ble is not None else None,
                         bleFirst=[(c, a) for v, c, a in ble.runs][:8] if ble is not None else None, **extra)
    with open(OUT, "a") as f:
        f.write(json.dumps({"row": name, **RESULTS[name]}, default=str) + "\n")
    print("\nOLD", name, RESULTS[name])


class FleetCar:
    # Same car model as the new-side test file
    def __init__(self, requests_mock, vin=VIN, state="asleep", limit=50, charging="Stopped", soc=40, at=HOME, wakes=True, script=None):
        self.vin, self.state, self.wakes = vin, state, wakes
        self.charge = {"charge_limit_soc": limit, "charging_state": charging, "battery_level": soc, "charge_current_request": 32,
                       "charger_pilot_current": 32, "scheduled_charging_pending": False}
        self.at, self.script = at, list(script or [(200, True, "")])
        base = FLEET + vin
        requests_mock.get(base, json=lambda req, ctx: {"response": {"state": self.state, "vin": vin}})
        requests_mock.post(base + "/wake_up", json=self._wake)
        requests_mock.get(base + "/vehicle_data", json=self._data)
        requests_mock.post(re.compile(re.escape(base) + r"/command/.*"), json=self._command)

    def _wake(self, req, ctx):
        if self.wakes:
            self.state = "online"
        return {"response": {"state": self.state}}

    def _data(self, req, ctx):
        if self.state != "online":
            ctx.status_code = 408
            return {"response": None, "error": "vehicle unavailable"}
        return {"response": {"drive_state": {"latitude": self.at[0], "longitude": self.at[1], "shift_state": None},
                             "charge_state": dict(self.charge), "vehicle_state": {}}}

    def _command(self, req, ctx):
        if self.state != "online":
            ctx.status_code = 408
            return {"response": None, "error": "vehicle unavailable"}
        status, result, reason = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        ctx.status_code = status
        if status != 200:
            return {"response": None, "error": "x"}
        if result:
            name = req.url.rsplit("/", 1)[-1]
            body = req.json() if req.body else {}
            if name == "set_charge_limit":
                self.charge["charge_limit_soc"] = body["percent"]
            elif name == "charge_start":
                self.charge["charging_state"] = "Charging"
            elif name == "charge_stop":
                self.charge["charging_state"] = "Stopped"
        return {"response": {"result": result, "reason": reason}}


class Clock:
    # After the real now: main's TWCSlave stamps some timers with it at init
    def __init__(self, t=None):
        self.t = t if t is not None else time.time() + 100

    def __call__(self):
        return self.t


class _NoThread:
    daemon = False

    def start(self):
        pass


@pytest.fixture
def clock(monkeypatch, requests_mock):
    import TWCManager.TWCMaster as twcmaster
    import TWCManager.TWCSlave as twcslave
    import TWCManager.Vehicle.HomeAssistant as homeassistant
    import TWCManager.Vehicle.TeslaAPI as teslaapi
    import TWCManager.Vehicle.TeslaBLE as teslable

    c = Clock()
    for module in (teslaapi, teslable, twcslave, twcmaster, homeassistant):
        monkeypatch.setattr(module.time, "time", c)
        monkeypatch.setattr(module.time, "sleep", lambda s: None)
        monkeypatch.setattr(module.time, "monotonic", c)
    monkeypatch.setattr(teslaapi, "Thread", lambda *a, **k: _NoThread())
    requests_mock.register_uri(ANY, ANY, status_code=599, json={})
    return c


class OldMaster(FakeMaster):
    # FakeMaster plus main's TWCMaster helpers the vehicle modules call
    def __init__(self):
        super().__init__()
        from TWCManager.TWCMaster import TWCMaster

        self.stats = {"moduleDispatch": {}, "moduleFailures": {}, "moduleSuccess": {}}
        self.settingsLock = threading.RLock()
        self.vehicleModules = {}
        self.lastChargeLimitApplied = 0
        for name in ("getNormalChargeLimit", "saveNormalChargeLimit", "removeNormalChargeLimit", "getModuleByPriority",
                     "calculateModulePriority"):
            setattr(self, name, types.MethodType(getattr(TWCMaster, name), self))
        self.releaseModule = Mock()
        self.getSlaveTWCs = Mock(return_value=[])
        self.getTWCbyVIN = Mock(return_value=None)

    def getModulesByType(self, kind):
        return [{"name": n, "ref": ref, "priority": self.calculateModulePriority(kind, n)}
                for n, ref in self.vehicleModules.items() if kind == "Vehicle"]

    def add(self, name, ref):
        self.vehicleModules[name] = ref
        self.modules[name] = ref


def oldInstall(fleet=False, owner=False, policy=None, held=None, at=HOME, heldBy="id"):
    # heldBy: the chargeLimits key, the TeslaAPI vehicle ID or (as main's
    # BLE module and the live box write it) the VIN
    from TWCManager.Vehicle.VehiclePriority import VehiclePriority

    m = OldMaster()
    if policy:
        m.settings["commandPolicy"] = policy
    api = None
    if fleet or owner:
        api = new_api(master=m)
        api.wakeDelayMins = 0
        if owner:
            api.storeToken(owner_token())
        if fleet:
            api.storeToken(fleet_token())
        api.addVehicle({"id": 1, "vin": VIN, "display_name": "Car"})
        m.add("TeslaAPI", api)
    if held:
        m.settings["chargeLimits"] = {("1" if api and heldBy == "id" else VIN): list(held)}
    vp = VehiclePriority(m)
    m.modules["VehiclePriority"] = vp
    return m, vp, api


def oldBle(m, answers="ok", vins=(VIN,)):
    from TWCManager.Vehicle.TeslaBLE import TeslaBLE

    m.settings.setdefault("Vehicles", {}).update({vin: {"privKey": "x"} for vin in vins})
    m.config["config"]["teslaControlPath"] = "/bin/true"
    with patch.object(TeslaBLE, "_start_dbus_session"), patch.object(TeslaBLE, "_cleanup_stale_pipe"):
        b = TeslaBLE(m)
    b.runs, b.answers = [], answers

    def run(vin, command, args=None):
        b.runs.append((vin, command, args))
        return b.answers(command, args) if callable(b.answers) else b.answers

    b._sendCommand_internal = run
    b._fetch_state_json = lambda vin, kind: None
    m.add("TeslaBLE", b)
    return b


def every(clock, seconds, step, fn):
    for _ in range(int(seconds / step)):
        clock.t += step
        fn()


# Row 4


def test_fleet_only_raise(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True, held=(90, 50))
    car = FleetCar(requests_mock, limit=50)
    api.getCarApiVehicles()[0].atHome = True
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=80))
    record("4 fleet-only raise", requests_mock, limit=car.charge["charge_limit_soc"])


def bleRuns(b, vin=VIN):
    return [cmd for v, cmd, args in b.runs if v == vin]


CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False, "treatGenerationAsGridDelivery": False,
          "wiringMaxAmpsAllTWCs": 80, "wiringMaxAmpsPerTWC": 32, "maxAmpsAllowedFromGrid": None, "minAmpsPerTWC": 6,
          "fakeMaster": 1, "displayMilliseconds": False}}


def oldSlave(m, vp):
    # main's real TWCMaster and TWCSlave; a queued vehicle command runs at
    # once through VehiclePriority, as main's VehicleCommandQueue would
    from TWCManager.TWCMaster import TWCMaster
    from TWCManager.VehicleCommandQueue import VehicleCommandQueue

    tm = TWCMaster(b"\x77\x77", CONFIG)
    pol = Mock()
    pol.policyIsGreen.return_value = False
    tm.getModuleByName = lambda n: {"Policy": pol}.get(n) or m.modules.get(n)
    iface = Mock()
    real = tm.getModulesByType
    tm.getModulesByType = lambda k: [{"name": "Dummy", "ref": iface, "type": k}] if k == "Interface" else real(k)

    def queue(task, callback=None):
        result = VehicleCommandQueue._DISPATCH[task["cmd"]](vp, task)
        if callback:
            callback(result)

    tm.queue_vehicle_command = queue
    tm.settings = m.settings
    s = tm.newSlave(b"\x82\x44", 80)
    s.protocolVersion = 2
    return tm, s


def beat(s, amps, state=1):
    ac = int(amps * 100)
    s.receive_slave_heartbeat(bytearray([state, 0, 0, ac >> 8, ac & 0xFF, 0, 0]))
    s.send_master_heartbeat()


def oldHa(m, requests_mock, *cars):
    from TWCManager.Vehicle.HomeAssistant import HaVehicle, HomeAssistant

    m.config["vehicle"] = dict(m.config.get("vehicle", {}), HomeAssistant={"enabled": True, "url": "http://ha", "longLivedToken": "x" * 40})
    with patch("TWCManager.Vehicle.HomeAssistant.requests.Session"), patch.object(HomeAssistant, "_discover_vehicles"):
        ha = HomeAssistant(m)
    ha._session = requests.Session()
    requests_mock.post(re.compile(r"http://ha/api/services/.*"), json=[])
    requests_mock.get(re.compile(r"http://ha/api/states/.*"), json={"state": "on"})
    for vin, entities in cars:
        hv = HaVehicle("Car", vin, "d-" + vin, entities)
        ha.carApiVehicles.append(hv)
    m.add("HomeAssistant", ha)
    return ha


# Row 1


def test_pure_gen2(clock, requests_mock):
    m, vp, api = oldInstall()
    assert vp.car_api_charge({"cmd": "charge", "charge": False}) is False
    assert vp.car_api_charge({"cmd": "charge", "charge": True}) is False
    record("1 pure gen2", requests_mock)


# Row 2


def test_ble_only_lowers(clock, requests_mock):
    m, vp, api = oldInstall()
    b = oldBle(m)
    every(clock, 600, 30, lambda: vp.applyChargeLimit(limit=70))
    every(clock, 600, 30, lambda: vp.applyChargeLimit(limit=60))
    record("2 ble-only lowers", requests_mock, b)


# Row 3


def test_owner_only(clock, requests_mock):
    m, vp, api = oldInstall(owner=True)
    FleetCar(requests_mock, state="online", charging="Charging")
    every(clock, 600, 10, lambda: (vp.applyChargeLimit(limit=70), vp.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN})))
    record("3 owner-only", requests_mock)


# Rows 5 and 6


def test_ble_plus_fleet_limit_radio_down(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    b = oldBle(m, answers=None)
    car = FleetCar(requests_mock, state="online", limit=90)
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    first = next((i for i, q in enumerate(requests_mock.request_history) if "/command/" in q.url), None)
    record("5 ble+fleet limit, radio down", requests_mock, b, firstFleetCommandIndex=first, limit=car.charge["charge_limit_soc"])


def test_ble_plus_fleet_stop_radio_down(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    b = oldBle(m, answers=None)
    car = FleetCar(requests_mock, state="online", charging="Charging")
    every(clock, 3600, 10, lambda: car.charge["charging_state"] == "Charging" and vp.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN}))
    record("6 ble+fleet stop, radio down", requests_mock, b, state=car.charge["charging_state"])


# Row 7


def test_app_limit_while_held(clock, requests_mock):
    m, vp, api = oldInstall()
    b = oldBle(m)
    every(clock, 60, 30, lambda: vp.applyChargeLimit(limit=50))
    before = len(b.runs)
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))      # the app set 80 meanwhile: BLE reads nothing
    record("7 app sets 80 while held at 50", requests_mock, b, runsAfterApp=len(b.runs) - before, saved=m.settings.get("chargeLimits"))


# Row 8


def test_app_start_overridden(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    car = FleetCar(requests_mock, state="online", charging="Charging")

    def answer(command, args):
        if command == "charging-stop":
            car.charge["charging_state"] = "Stopped"
        return "ok"

    b = oldBle(m, answers=answer)
    stop = lambda: car.charge["charging_state"] == "Charging" and vp.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN})
    every(clock, 600, 10, stop)
    car.charge["charging_state"] = "Charging"                           # the app starts it
    every(clock, 600, 10, stop)
    record("8 app start overridden", requests_mock, b)


# Rows 9 and 10


def test_fleet_500_limit(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online", limit=90, script=[(500, None, None)])
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("9 fleet 500 limit", requests_mock)


def test_fleet_then_ha(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    oldHa(m, requests_mock, (VIN, {"charge_limit_number": "number.limit", "charge_switch": "switch.c", "battery_level_sensor": "sensor.b"}))
    FleetCar(requests_mock, state="online", limit=90, script=[(500, None, None)])
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("10 fleet 500 then HA", requests_mock)


# Rows 11 and 29: two Gen3 units, one shared fake-Neurio register


def gen3Units():
    from TWCManager.EVSEInstance.Gen3TWC import Gen3TWC

    ctl = Mock()
    units = []
    for ip in ("10.0.0.1", "10.0.0.2"):
        u = Gen3TWC({"ip": ip, "fuseAmps": 48, "phases": 1}, ctl, Mock(config={"config": {"defaultVoltage": 240}}))
        u._vitals = {"grid_v": 240.0, "vehicle_connected": True}
        units.append(u)
    return ctl, units


def headroomAmps(ctl):
    house = ctl.setHouseWatts.call_args.kwargs["watts"]
    return round(48 - house / 240, 2)


def test_gen3_stop_one_unit(clock, requests_mock):
    ctl, (a, b) = gen3Units()
    a.setTargetPower(4800)
    b.setTargetPower(0)                                                 # the distributor's stop for b's car
    after = headroomAmps(ctl)
    record("11 gen3 stop one car", requests_mock, headroomA=after, headroomB=after)


def test_gen3_shared_headroom(clock, requests_mock):
    ctl, (a, b) = gen3Units()
    a.setTargetPower(4800); b.setTargetPower(2400)
    ab = headroomAmps(ctl)
    b.setTargetPower(2400); a.setTargetPower(4800)
    ba = headroomAmps(ctl)
    record("29 gen3 shared headroom", requests_mock, targetAmps=30, drawnAmpsOrderAB=2 * ab, drawnAmpsOrderBA=2 * ba)


def test_gen3_vin(clock, requests_mock):
    ctl, (a, b) = gen3Units()
    record("30 gen3 cloud vin", requests_mock, currentVIN=a.currentVIN)


# Row 12


def test_stop_mode_2(clock, requests_mock):
    from TWCManager.TWCMaster import TWCMaster

    m, vp, api = oldInstall(fleet=True)
    b = oldBle(m, answers=None)
    FleetCar(requests_mock, state="online", charging="Charging")
    m.settings["chargeStopMode"] = "2"
    TWCMaster.stopCarsCharging(m, VIN)
    record("12 stop mode 2", requests_mock, b, respondToSlaves=m.settings["respondToSlaves"])


# Rows 13, 14, 21, 25: main's real TWCSlave heartbeat


def slaveRun(clock, m, vp, mode, offers, vin=VIN, seconds=600):
    tm, s = oldSlave(m, vp)
    m.settings["chargeRateControl"] = str(mode)
    if vin:
        s.currentVIN = s.lastVIN = vin
    for amps, secs in offers:
        tm.setMaxAmpsToDivideAmongSlaves(amps)
        for _ in range(secs):
            clock.t += 1
            beat(s, max(amps, 1))
    return tm, s


def setAmps(requests_mock):
    return [(q.url.split("/")[-3], q.json()["charging_amps"]) for q in requests_mock.request_history if "set_charging_amps" in q.url]


def test_mode_3_below_floor(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online", charging="Charging")
    slaveRun(clock, m, vp, 3, [(4, 60), (10, 600)])
    record("13 mode 3 below floor", requests_mock, amps=setAmps(requests_mock))


def test_mode_1_lift(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online", charging="Charging")
    slaveRun(clock, m, vp, 1, [(10, 3600)])
    record("14 mode 1 lift", requests_mock, amps=setAmps(requests_mock))


def test_mode_2_undeliverable_rate(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online", charging="Charging", script=[(500, None, None)])
    slaveRun(clock, m, vp, 2, [(10, 3600)])
    record("21 mode 2 undeliverable rate", requests_mock, sends=len(setAmps(requests_mock)))


def test_vinless_mode_2_rate(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    api.addVehicle({"id": 2, "vin": VIN2, "display_name": "Two"})
    FleetCar(requests_mock, vin=VIN, state="online", charging="Disconnected")
    FleetCar(requests_mock, vin=VIN2, state="online", charging="Charging")
    slaveRun(clock, m, vp, 2, [(10, 600)], vin=None)
    record("25 vinless mode 2 rate", requests_mock, amps=setAmps(requests_mock))


# Row 15


def test_fleet_401(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online", limit=90, script=[(401, None, None)])
    requests_mock.post(re.compile(r".*/oauth2/v3/token"), status_code=401, json={})
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("15 fleet 401", requests_mock, slotEmpty=api.fleetSlot.empty())


# Row 16


def test_ha_only_stop(clock, requests_mock):
    m, vp, api = oldInstall()
    ha = oldHa(m, requests_mock, (VIN, {"charge_switch": "switch.one", "battery_level_sensor": "sensor.b"}),
               (VIN2, {"charge_switch": "switch.two", "battery_level_sensor": "sensor.b"}))
    every(clock, 600, 10, lambda: vp.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN}))
    viaPriority = counts(requests_mock)["ha"]
    for v in ha.carApiVehicles:
        v.at_home, v.charging = True, True
    ha.refresh_from = None
    m.getTWCbyVIN = Mock(return_value=object())
    with patch("TWCManager.Vehicle.HomeAssistant.HaVehicle.refresh_from_home_assistant"):
        ha.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN})
    direct = [q.json() for q in requests_mock.request_history if "turn_off" in q.url]
    record("16 ha-only stop", requests_mock, viaVehiclePriority=viaPriority, directCall=direct)


# Rows 17a and 17b


def test_departed_ble_only(clock, requests_mock):
    m, vp, api = oldInstall(owner=True, fleet=True, policy="ble_only", held=(90, 90), heldBy="vin")
    car = FleetCar(requests_mock, state="online", limit=90)
    b = oldBle(m)
    every(clock, 60, 30, lambda: vp.applyChargeLimit(limit=50))        # at home: applied
    b.answers, car.at, car.state = None, AWAY, "asleep"                 # gone
    before = len(b.runs)
    vp.applyChargeLimit(limit=50, checkDeparture=True)                  # the power-drop edge
    every(clock, 3 * 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("17a departed, ble_only", requests_mock, b, runsAfter=len(b.runs) - before, saved=m.settings.get("chargeLimits"))


def test_departed_ble_plus_fleet(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True, held=(90, 90))
    car = FleetCar(requests_mock, state="online", limit=90)
    b = oldBle(m)
    every(clock, 60, 30, lambda: vp.applyChargeLimit(limit=50))
    b.answers, car.at, car.state = None, AWAY, "asleep"
    before = len(b.runs)
    vp.applyChargeLimit(limit=50, checkDeparture=True)
    every(clock, 3 * 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("17b departed, ble+fleet", requests_mock, b, runsAfter=len(b.runs) - before, limit=car.charge["charge_limit_soc"])


# Row 19


def test_schedule_pending_start(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    car = FleetCar(requests_mock, state="asleep")
    car.charge["scheduled_charging_pending"] = True
    api.getCarApiVehicles()[0].atHome = True
    every(clock, 3600, 10, lambda: vp.car_api_charge({"cmd": "charge", "charge": True, "vin": VIN}))
    record("19 schedule pending start", requests_mock)


# Row 20 and I2


def test_streaming_408(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    car = FleetCar(requests_mock, state="online", limit=90)
    requests_mock.post(re.compile(re.escape(FLEET + VIN) + r"/command/.*"), status_code=408, json={"response": None})
    requests_mock.get(FLEET + VIN + "/vehicle_data", status_code=408, json={"response": None})
    every(clock, 3600, 30, lambda: vp.applyChargeLimit(limit=50))
    record("20 streaming, fleet 408, limit", requests_mock)


def test_streaming_408_start(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    FleetCar(requests_mock, state="online")
    requests_mock.post(re.compile(re.escape(FLEET + VIN) + r"/command/.*"), status_code=408, json={"response": None})
    requests_mock.get(FLEET + VIN + "/vehicle_data", status_code=408, json={"response": None})
    every(clock, 3600, 10, lambda: vp.car_api_charge({"cmd": "charge", "charge": True, "vin": VIN}))
    record("20b streaming, fleet 408, start", requests_mock)


# Row 23


def test_limit_then_start(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True, held=(90, 90))
    car = FleetCar(requests_mock, state="asleep", limit=90, wakes=False)
    api.getCarApiVehicles()[0].atHome = True
    m.lastChargeLimitApplied = 50
    every(clock, 1800, 30, lambda: vp.applyChargeLimit(limit=50))
    before = len(requests_mock.request_history)
    car.wakes = True
    every(clock, 600, 10, lambda: car.charge["charging_state"] != "Charging" and vp.car_api_charge({"cmd": "charge", "charge": True, "vin": VIN}))
    seq = [q.url.split("?")[0].rsplit("/", 1)[-1] for q in requests_mock.request_history[before:] if "fleet-api" in q.url]
    record("23 limit then start", requests_mock, startSequence=seq, limit=car.charge["charge_limit_soc"])


# Row 24


def test_anonymous_stop(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    api.addVehicle({"id": 2, "vin": VIN2, "display_name": "Two"})
    cars = [FleetCar(requests_mock, vin=v, state="online", charging="Charging") for v in (VIN, VIN2)]
    every(clock, 600, 10, lambda: any(c.charge["charging_state"] == "Charging" for c in cars) and vp.car_api_charge({"cmd": "charge", "charge": False}))
    record("24 anonymous stop", requests_mock, stopped=[q.url.split("/")[-3] for q in requests_mock.request_history if "charge_stop" in q.url])


# Row 26 (the 2026-10-16 restart, run on main)


def test_restart_plugged_asleep(clock, requests_mock):
    m, vp, api = oldInstall(owner=True, fleet=True, policy="ble_only", held=(100, 50), heldBy="vin")
    car = FleetCar(requests_mock, state="asleep", limit=50, soc=51, charging="Complete")
    started = []

    def answer(command, args):
        if command == "charging-start":
            started.append(clock.t)                                     # SOC 51 under 70: the car starts
        return "ok"

    b = oldBle(m, answers=answer)
    tm, s = oldSlave(m, vp)
    m.settings["chargeRateControl"] = "1"
    tm.setMaxAmpsToDivideAmongSlaves(32)
    m.lastChargeLimitApplied = 70

    def tick():
        beat(s, 32.0 if started else 0.0, state=1 if started else 3)
        if int(clock.t) % 30 == 0:
            vp.applyChargeLimit(limit=70)

    vp.applyChargeLimit(limit=70)
    every(clock, 600, 1, tick)
    record("26 restart plugged asleep", requests_mock, b, saved=m.settings.get("chargeLimits"))


# Row 27


def test_mode_2_start(clock, requests_mock):
    from TWCManager.TWCMaster import TWCMaster

    m, vp, api = oldInstall(fleet=True)
    b = oldBle(m)
    m.settings.update(chargeStopMode="2", respondToSlaves=0)
    TWCMaster.startCarsCharging(m, VIN)
    record("27 mode 2 start", requests_mock, b, respondToSlaves=m.settings["respondToSlaves"])


# Row 28


def test_min_charge_level(clock, requests_mock):
    m, vp, api = oldInstall(fleet=True)
    api.minChargeLevel = 30
    car = FleetCar(requests_mock, state="online", charging="Charging", soc=20)
    every(clock, 600, 10, lambda: vp.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN}))
    record("28 min charge level", requests_mock, state=car.charge["charging_state"])
