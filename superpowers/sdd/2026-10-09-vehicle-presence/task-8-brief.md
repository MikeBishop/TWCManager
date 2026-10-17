### Task 8: Triggers and wiring

**Files:**
- Modify: `lib/TWCManager/TWCSlave.py:561`, `:599-690` (`receive_slave_heartbeat`), `:1067`, add `_presenceVIN`/`_nominatePresence`/`_checkPresenceTriggers` after `_queueChargeRate`
- Modify: `lib/TWCManager/TWCMaster.py` (`recordVehicleVIN`, originally lines 1381-1427; earlier tasks added lines above it, so search by name)
- Modify: `lib/TWCManager/Vehicle/Telemetry.py:147-162` (`applyDataToVehicle`), add `_reportLocation`
- Modify: `lib/TWCManager/TWCManager.py:805` (start), `:1976` (stop); the background branches were already removed in Task 3
- Modify: `lib/TWCManager/Control/HTTPControl.py:591-601`
- Test: `tests/unit/test_twcslave.py`, `tests/unit/test_twcmaster.py`, `tests/unit/test_telemetry_timers.py`, `tests/unit/test_httpcontrol.py`, `tests/unit/test_twcmanager.py`

**Interfaces:**
- Consumes: `master.vehiclePresence.nominate(vin, reason, delays)`, `.observeLocation(vin, atHome)`, `.start()`, `.stop()` (Task 5); `master.cancelStopCarsCharging(vin)` (Task 1); `TeslaAPI.is_location_home(lat, lon)`.
- Produces:
  - `TWCSlave._presenceVIN() -> currentVIN or lastVIN or None`; `TWCSlave._nominatePresence(reason, delays)`; `TWCSlave._checkPresenceTriggers(previousState)`.
  - `TWCMaster.recordVehicleVIN` nominates `(currentVIN, "vin", delays=(0,))`.
  - `TelmetryBase._reportLocation(vehicle)`.
  - `/api/checkArrival` and `/api/checkDeparture` call `nominate(None, "api", delays=(0,))` and return 202.
  - `TWCManager.py` starts presence after the vehicle queue when `fakeMaster == 1` and stops it first in the shutdown block.

- [ ] **Step 1: Write the failing TWCSlave trigger tests**

Append to `tests/unit/test_twcslave.py`:

```python
class TestPresenceTriggers:
    """TWC events nominate presence checks; they never do I/O themselves."""

    DEPARTURE_DELAYS = (300, 1200, 2700)

    @pytest.fixture
    def slave(self):
        from TWCManager.TWCSlave import TWCSlave

        master = Mock()
        master.getModuleByName = Mock(return_value=None)
        config = {
            "config": {
                "wiringMaxAmpsPerTWC": 32,
                "useFlexAmpsToStartCharge": False,
                "startStopDelay": 60,
                "fakeMaster": 1,
            }
        }
        s = TWCSlave(bytearray(b"AB"), 80, config, master)
        s.currentVIN = "VIN1"
        s.lastVIN = "VIN0"
        return s

    def set_heartbeat(self, slave, monitor, actual, state):
        slave.reportedAmpsActualSignificantChangeMonitor = monitor
        slave.reportedAmpsActual = actual
        slave.reportedState = state

    def test_power_start_nominates_current_vin_now(self, slave):
        self.set_heartbeat(slave, monitor=0, actual=10, state=0x01)
        slave._checkPresenceTriggers(previousState=0x01)
        slave.master.vehiclePresence.nominate.assert_called_once_with(
            "VIN1", "power-start", delays=(0,)
        )

    def test_power_drop_nominates_with_departure_delays(self, slave):
        self.set_heartbeat(slave, monitor=10, actual=0, state=0x01)
        slave._checkPresenceTriggers(previousState=0x01)
        slave.master.vehiclePresence.nominate.assert_called_once_with(
            "VIN1", "power-drop", delays=self.DEPARTURE_DELAYS
        )

    def test_unplug_without_a_power_drop_still_nominates(self, slave):
        self.set_heartbeat(slave, monitor=0, actual=0, state=0x00)
        slave._checkPresenceTriggers(previousState=0x03)
        slave.master.vehiclePresence.nominate.assert_called_once_with(
            "VIN1", "unplug", delays=self.DEPARTURE_DELAYS
        )

    def test_steady_unplugged_state_does_not_nominate(self, slave):
        self.set_heartbeat(slave, monitor=0, actual=0, state=0x00)
        slave._checkPresenceTriggers(previousState=0x00)
        slave.master.vehiclePresence.nominate.assert_not_called()

    def test_vin_falls_back_to_last_vin_then_none(self, slave):
        slave.currentVIN = ""
        assert slave._presenceVIN() == "VIN0"
        slave.lastVIN = ""
        assert slave._presenceVIN() is None
        self.set_heartbeat(slave, monitor=0, actual=10, state=0x01)
        slave._checkPresenceTriggers(previousState=0x01)
        slave.master.vehiclePresence.nominate.assert_called_once_with(
            None, "power-start", delays=(0,)
        )

    def test_heartbeat_uses_triggers_and_no_longer_queues_background_checks(self):
        import inspect
        from TWCManager.TWCSlave import TWCSlave

        source = inspect.getsource(TWCSlave.receive_slave_heartbeat)
        assert "self._checkPresenceTriggers(previousState)" in source
        assert "checkArrival" not in source
        assert "checkDeparture" not in source

    def test_cancel_stop_passes_the_current_vin(self):
        import inspect
        from TWCManager.TWCSlave import TWCSlave

        source = inspect.getsource(TWCSlave)
        assert "cancelStopCarsCharging()" not in source
        assert "cancelStopCarsCharging(self.currentVIN)" in source
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcslave.py -q -p no:cacheprovider -k TestPresenceTriggers`
Expected: 7 failures (`AttributeError: 'TWCSlave' object has no attribute '_checkPresenceTriggers'`, source assertions).

- [ ] **Step 3: Implement the TWCSlave triggers**

In `lib/TWCManager/TWCSlave.py`, add after `_queueChargeRate` (after line 101):

```python
    def _presenceVIN(self):
        # The car this TWC most likely refers to: the current session's VIN,
        # else the last one we saw, else unknown (None = every known car).
        return self.currentVIN or self.lastVIN or None

    def _nominatePresence(self, reason, delays):
        # Runs on the main (serial) thread: record only, VehiclePresence does
        # the I/O on its own thread.
        self.master.vehiclePresence.nominate(self._presenceVIN(), reason, delays=delays)

    def _checkPresenceTriggers(self, previousState):
        # Called from receive_slave_heartbeat before the significant-change
        # monitor is updated for this heartbeat.
        monitor = self.reportedAmpsActualSignificantChangeMonitor
        if monitor < 3 and self.reportedAmpsActual > 3:
            # Power started flowing: a car may have arrived.
            self._nominatePresence("power-start", (0,))
        if monitor > 2 and self.reportedAmpsActual < 2:
            # Power dropped: a departure may follow in the next while.
            self._nominatePresence("power-drop", (300, 1200, 2700))
        if previousState != 0x00 and self.reportedState == 0x00:
            # Unplugged, even while idle at the limit. State 00 is briefly
            # reported while plugged in just before a scheduled start; a
            # false unplug only costs the delayed probes.
            self._nominatePresence("unplug", (300, 1200, 2700))
```

In `receive_slave_heartbeat`, insert before `self.reportedAmpsMax = ...` (line 607):

```python
        previousState = self.reportedState
```

Replace the two trigger blocks (lines 645-665, from `# If power starts flowing, check whether a car has arrived` through the third `checkDeparture` queueing line) with:

```python
        # TWC power/plug events nominate presence checks; VehiclePresence
        # decides arrival and departure and sends the commands.
        self._checkPresenceTriggers(previousState)

        if (
            self.reportedAmpsActualSignificantChangeMonitor < 3
            and self.reportedAmpsActual > 3
        ):
            self.master.getModuleByName("Policy").fireWebhook("start")

        if (
            self.reportedAmpsActualSignificantChangeMonitor > 2
            and self.reportedAmpsActual < 2
        ):
            self.master.getModuleByName("Policy").fireWebhook("stop")
```

The `# If the drop-off was an expected completion, don't restart` block that followed stays inside the second `if`, unchanged.

Change both `self.master.cancelStopCarsCharging()` calls (lines 561 and 1067) to:

```python
                    self.master.cancelStopCarsCharging(self.currentVIN)
```
and
```python
            self.master.cancelStopCarsCharging(self.currentVIN)
```
(keeping each line's existing indentation).

- [ ] **Step 4: Run the TWCSlave tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcslave.py -q -p no:cacheprovider`
Expected: `43 passed`.

- [ ] **Step 5: Write the failing `recordVehicleVIN`, Telemetry, HTTP and launcher tests**

Append to `tests/unit/test_twcmaster.py`:

```python
class TestRecordVehicleVINNominates:
    def test_record_vehicle_vin_nominates_presence_check(self):
        from TWCManager.TWCMaster import TWCMaster

        m = TWCMaster(
            "AB",
            {
                "config": {
                    "debugOutputToFile": False,
                    "subtractChargerLoad": False,
                    "treatGenerationAsGridDelivery": False,
                    "wiringMaxAmpsAllTWCs": 80,
                    "maxAmpsAllowedFromGrid": None,
                }
            },
        )
        m.queue_background_task = Mock()
        m.getModuleByName = Mock(return_value=None)
        m.vehiclePresence = Mock()
        slave = Mock()
        slave.TWCID = bytearray(b"\x12\x34")
        slave.currentVIN = "5YJ3E1EA1KF000001"
        slave.lifetimekWh = 100

        m.recordVehicleVIN(slave)

        m.vehiclePresence.nominate.assert_called_once_with(
            "5YJ3E1EA1KF000001", "vin", delays=(0,)
        )
```

Append to `tests/unit/test_telemetry_timers.py`:

```python
def test_location_update_observes_presence_once_both_coordinates_are_valid():
    timer_cls, _ = _recording_timer()
    with patch.object(Telemetry.threading, "Timer", timer_cls):
        obj = _Sub(_master())
    teslaapi = obj.master.getModuleByName.return_value
    teslaapi.is_location_home.return_value = True
    vehicle = MagicMock()
    vehicle.VIN = "5YJ3E1EA1KF000001"
    vehicle.syncLat = 10000
    vehicle.syncLon = 10000
    vehicle.syncSource = "Sub"
    obj.vehicles = {"1": vehicle}
    obj.events = {
        "latitude": ["syncLat", lambda a: float(a)],
        "longitude": ["syncLon", lambda a: float(a)],
    }

    obj.applyDataToVehicle("1", "latitude", "1.5")
    obj.master.vehiclePresence.observeLocation.assert_not_called()

    obj.applyDataToVehicle("1", "longitude", "2.5")
    teslaapi.is_location_home.assert_called_once_with(1.5, 2.5)
    obj.master.vehiclePresence.observeLocation.assert_called_once_with(
        "5YJ3E1EA1KF000001", True
    )


def test_non_location_events_do_not_observe_presence():
    timer_cls, _ = _recording_timer()
    with patch.object(Telemetry.threading, "Timer", timer_cls):
        obj = _Sub(_master())
    vehicle = MagicMock()
    vehicle.syncLat = 1.5
    vehicle.syncLon = 2.5
    obj.vehicles = {"1": vehicle}
    obj.events = {"battery_level": ["batteryLevel", lambda a: int(a)]}

    obj.applyDataToVehicle("1", "battery_level", "71")

    assert vehicle.batteryLevel == 71
    obj.master.vehiclePresence.observeLocation.assert_not_called()
```

Append to `tests/unit/test_httpcontrol.py`:

```python
class TestPresenceEndpoints:
    """/api/checkArrival and /api/checkDeparture nominate a presence check
    for every known vehicle and keep answering 202."""

    @pytest.fixture
    def handler(self):
        import io
        from TWCManager.Control.HTTPControl import CreateHTTPHandlerClass

        master = Mock()
        cls = CreateHTTPHandlerClass(master)
        h = cls.__new__(cls)  # skip BaseHTTPRequestHandler's socket setup
        h.debugLogAPI = Mock()
        h.send_response = Mock()
        h.send_header = Mock()
        h.end_headers = Mock()
        h.wfile = io.BytesIO()
        h.post_data = b""
        return master, h

    @pytest.mark.parametrize("path", ["/api/checkArrival", "/api/checkDeparture"])
    def test_endpoint_nominates_all_vehicles(self, handler, path):
        import urllib.parse

        master, h = handler
        h.url = urllib.parse.urlparse(path)
        h.do_API_POST()
        master.vehiclePresence.nominate.assert_called_once_with(
            None, "api", delays=(0,)
        )
        master.queue_background_task.assert_not_called()
        h.send_response.assert_called_once_with(202)
```

Append to `tests/unit/test_twcmanager.py`:

```python
def _launcher_source():
    with open(os.path.join(_LIB_DIR, "TWCManager", "TWCManager.py")) as f:
        return f.read()


class TestPresenceLifecycle:
    """TWCManager.py starts presence as a real master and stops it first at
    shutdown; the checkArrival/checkDeparture background tasks are gone."""

    def test_check_arrival_and_departure_branches_are_gone(self):
        source = _launcher_source()
        assert '"checkArrival"' not in source
        assert '"checkDeparture"' not in source
        assert '"checkCharge"' in source  # unrelated and kept

    def test_presence_starts_after_the_vehicle_queue_gated_on_fake_master(self):
        lines = _launcher_source().splitlines()
        queue = next(
            i for i, l in enumerate(lines) if "master.vehicleCommandQueue.start()" in l
        )
        start = next(
            i for i, l in enumerate(lines) if "master.vehiclePresence.start()" in l
        )
        assert queue < start
        gate = [l for l in lines[queue:start] if 'fakeMaster"] == 1' in l]
        assert gate, "vehiclePresence.start() must sit under a fakeMaster == 1 gate"
        assert lines[start].startswith("    "), "start() must be inside the gate"

    def test_presence_stops_before_shutdown_draining(self):
        lines = _launcher_source().splitlines()
        deadline = next(i for i, l in enumerate(lines) if "shutdownDeadline = " in l)
        stop = next(
            i for i, l in enumerate(lines) if "master.vehiclePresence.stop()" in l
        )
        drain = next(i for i, l in enumerate(lines) if "drain_high_priority" in l and "master." in l)
        assert deadline < stop < drain
```

- [ ] **Step 6: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcmaster.py tests/unit/test_telemetry_timers.py tests/unit/test_httpcontrol.py tests/unit/test_twcmanager.py -q -p no:cacheprovider -k "Nominates or presence or Presence"`
Expected: 7 failures (`nominate` not called; `observeLocation` not called; endpoints still call `queue_background_task`; launcher source has no `vehiclePresence.start()`/`.stop()`). `test_check_arrival_and_departure_branches_are_gone` already passes because Task 3 removed the branches.

- [ ] **Step 7: Wire `recordVehicleVIN`, Telemetry, HTTPControl and the launcher**

In `lib/TWCManager/TWCMaster.py`, at the end of `recordVehicleVIN` (after the `tesla_api.vehicleIsDefinitelyHome(slaveTWC.currentVIN)` block, line 1427) add:

```python

        # A car with a session on a TWC is here; let presence confirm it and
        # apply the policy limit if it hadn't already.
        self.vehiclePresence.nominate(slaveTWC.currentVIN, "vin", delays=(0,))
```

In `lib/TWCManager/Vehicle/Telemetry.py`, inside `applyDataToVehicle`, after the `if vehicle.syncSource != self.__class__.__name__:` block (after the `logger.info(... telemetry has resumed ...)` call, line 162) add, at the same indentation as that `if`:

```python
                if property_name in ("syncLat", "syncLon"):
                    self._reportLocation(vehicle)
```

and add this method after `applyDataToVehicle` (before `mqttSubscribe`):

```python
    def _reportLocation(self, vehicle):
        # Runs on the MQTT thread. VehiclePresence only records, so no I/O.
        if vehicle.syncLat == 10000 or vehicle.syncLon == 10000:
            return
        teslaapi = self.master.getModuleByName("TeslaAPI")
        presence = getattr(self.master, "vehiclePresence", None)
        if not teslaapi or presence is None:
            return
        atHome = teslaapi.is_location_home(vehicle.syncLat, vehicle.syncLon)
        presence.observeLocation(vehicle.VIN, bool(atHome))
```

In `lib/TWCManager/Control/HTTPControl.py`, replace lines 591-601 with:

```python
            elif self.url.path == "/api/checkArrival":
                master.vehiclePresence.nominate(None, "api", delays=(0,))
                self.send_response(202)
                self.end_headers()
                self.wfile.write("".encode("utf-8"))

            elif self.url.path == "/api/checkDeparture":
                master.vehiclePresence.nominate(None, "api", delays=(0,))
                self.send_response(202)
                self.end_headers()
                self.wfile.write("".encode("utf-8"))
```

In `lib/TWCManager/TWCManager.py` (the `checkArrival`/`checkDeparture` branches are already gone since Task 3; line numbers below are from the branch base, so they have moved up by about 20 lines), after `master.vehicleCommandQueue.start()` (line 805) add:

```python

if config["config"]["fakeMaster"] == 1:
    # Presence probes lead to charge-limit commands on arrival and
    # departure; only a real master should send those (same reasoning as
    # #670). In the other modes observers still record but nothing acts.
    master.vehiclePresence.start()
```

After `shutdownDeadline = time.time() + 80` (line 1976) add:

```python

# No new presence probes or arrival/departure commands from here on. A probe
# already running finishes; anything its handler queues is dropped by the
# vehicle queue drain below unless it is a stop.
master.vehiclePresence.stop()
```

- [ ] **Step 8: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `640 passed, 1 warning`. (`test_sigterm_shutdown.py` boots the real launcher; it must still pass.)

- [ ] **Step 9: Confirm nothing else references the removed tasks**

Run: `grep -rn "checkArrival\|checkDeparture" lib/ tests/unit/`
Expected: only the two `HTTPControl.py` endpoint path strings (`/api/checkArrival`, `/api/checkDeparture`) and the assertions in `tests/unit/test_twcslave.py` and `tests/unit/test_twcmanager.py`. (`tests/integration/test_api_input_validation_extended.py` posts to the endpoints and expects 202; unchanged.)

- [ ] **Step 10: Commit**

```bash
git add lib/TWCManager/TWCSlave.py lib/TWCManager/TWCMaster.py lib/TWCManager/Vehicle/Telemetry.py lib/TWCManager/TWCManager.py lib/TWCManager/Control/HTTPControl.py tests/unit/test_twcslave.py tests/unit/test_twcmaster.py tests/unit/test_telemetry_timers.py tests/unit/test_httpcontrol.py tests/unit/test_twcmanager.py
git commit -m "$(cat <<'EOF'
Drive VehiclePresence from TWC events, telemetry and the API

TWC power starts, power drops, unplugs and recorded VINs nominate
presence checks; telemetry position updates are observed as they
arrive. The checkArrival/checkDeparture background tasks are gone and
the HTTP endpoints nominate instead. The presence thread starts after
the vehicle queue as a real master and stops first at shutdown.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

