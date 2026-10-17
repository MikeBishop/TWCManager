### Task 4: TeslaBLE `probePresence` and contact reporting

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py:115` (`__init__`, probe timeout), `:488-585` (`_sendCommand_internal`), `:935-972` (`_fetch_state_json`), add `probePresence` after `wakeVehicle` (line 917) and `_reportContact` after `_scheduleBlocksStart` (line 199)
- Test: `tests/unit/test_teslable_presence.py`

Line numbers in this task are from the branch base; Task 3 changed `applyChargeLimit` (line 668 onwards), so everything after it has moved by a few lines. Search by method name.

**Interfaces:**
- Consumes: `master.vehiclePresence.observeContact(vin, reachable, probe=False)` (Task 5 defines it; until then `getattr(master, "vehiclePresence", None)` guards the call).
- Produces:
  - `TeslaBLE.probePresence(vin) -> {"reachable": bool, "awake": bool}`: runs `tesla-control -ble body-controller-state` once under `_bleLock` with `self.presenceProbeTimeout` (config `moduleConfiguration.TeslaBLE.presenceProbeTimeout`, default 15 s), no retry, never `wake`/`state`/`ping`. `awake` is `True` only when the JSON `vehicleSleepStatus` is present and not `VEHICLE_SLEEP_STATUS_ASLEEP`; unparseable output gives `awake=False`.
  - Every `_sendCommand_internal` and `_fetch_state_json` call reports `observeContact(vin, ok, probe=False)`; `probePresence` reports `observeContact(vin, reachable, probe=True)`.

- [ ] **Step 1: Write the failing probe and reporting tests**

Append to `tests/unit/test_teslable_presence.py`:

```python
def body_state(sleep_status):
    return json.dumps(
        {
            "vehicleLockState": "VEHICLELOCKSTATE_UNLOCKED",
            "vehicleSleepStatus": sleep_status,
            "userPresence": "VEHICLE_USER_PRESENCE_NOT_PRESENT",
        }
    ).encode("utf-8")


ASLEEP = body_state("VEHICLE_SLEEP_STATUS_ASLEEP")
AWAKE = body_state("VEHICLE_SLEEP_STATUS_AWAKE")


class TestProbePresence:
    def test_asleep_car_is_reachable_but_not_awake(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(ASLEEP, b"", 0)])
        assert ble.probePresence(VIN1) == {"reachable": True, "awake": False}

    def test_awake_car(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(AWAKE, b"", 0)])
        assert ble.probePresence(VIN1) == {"reachable": True, "awake": True}

    def test_any_status_other_than_asleep_is_awake(self, ble):
        ble._run_command_with_timeout = CommandRecorder(
            [(body_state("VEHICLE_SLEEP_STATUS_UNKNOWN"), b"", 0)]
        )
        assert ble.probePresence(VIN1) == {"reachable": True, "awake": True}

    def test_unreachable_on_timeout_and_on_nonzero_exit(self, ble):
        ble._run_command_with_timeout = CommandRecorder(
            [(None, None, None), (b"", b"connection failed", 1)]
        )
        assert ble.probePresence(VIN1) == {"reachable": False, "awake": False}
        assert ble.probePresence(VIN1) == {"reachable": False, "awake": False}

    def test_unparseable_output_is_reachable_but_not_awake(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(b"not json at all", b"", 0)])
        assert ble.probePresence(VIN1) == {"reachable": True, "awake": False}

    def test_probe_runs_only_body_controller_state_and_is_not_retried(self, ble):
        ble.maxRetries = 3
        recorder = CommandRecorder([(None, None, None)])
        ble._run_command_with_timeout = recorder
        ble.probePresence(VIN1)
        assert recorder.commands == [("body-controller-state",)]
        # Its own timeout: the probe took 4.2 s live, so the 5 s command
        # timeout would turn a slow answer into a false "unreachable".
        assert recorder.timeouts == [15]

    def test_probe_runs_under_the_ble_lock(self, ble):
        recorder = CommandRecorder([(ASLEEP, b"", 0)], ble=ble)
        ble._run_command_with_timeout = recorder
        ble.probePresence(VIN1)
        assert recorder.locked_during_call == [True]
        assert not ble._bleLock.locked()

    def test_unknown_vin_runs_nothing(self, ble):
        recorder = CommandRecorder([(ASLEEP, b"", 0)])
        ble._run_command_with_timeout = recorder
        assert ble.probePresence("NOPE") == {"reachable": False, "awake": False}
        assert recorder.commands == []


class TestContactReporting:
    def test_send_command_reports_success(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(b"", b"ok", 0)])
        ble._sendCommand_internal(VIN1, "wake")
        ble.master.vehiclePresence.observeContact.assert_called_once_with(
            VIN1, True, probe=False
        )

    def test_send_command_reports_failure(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(None, None, None)])
        ble._sendCommand_internal(VIN1, "wake")
        ble.master.vehiclePresence.observeContact.assert_called_once_with(
            VIN1, False, probe=False
        )

    def test_state_read_reports_contact(self, ble):
        ble._run_command_with_timeout = CommandRecorder([(b"{}", b"", 0)])
        ble._fetch_state_json(VIN1, "charge")
        ble.master.vehiclePresence.observeContact.assert_called_once_with(
            VIN1, True, probe=False
        )

    def test_probe_reports_with_probe_flag(self, ble):
        ble._run_command_with_timeout = CommandRecorder(
            [(ASLEEP, b"", 0), (None, None, None)]
        )
        ble.probePresence(VIN1)
        ble.probePresence(VIN1)
        assert ble.master.vehiclePresence.observeContact.call_args_list == [
            ((VIN1, True), {"probe": True}),
            ((VIN1, False), {"probe": True}),
        ]

    def test_missing_presence_component_is_tolerated(self, ble):
        ble.master = Mock(spec=["settings"])
        ble.master.settings = {"Vehicles": {VIN1: key_material()}}
        ble._run_command_with_timeout = CommandRecorder([(b"", b"ok", 0)])
        assert ble._sendCommand_internal(VIN1, "wake") == "ok"
        assert ble.probePresence(VIN1) == {"reachable": True, "awake": False}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslable_presence.py -q -p no:cacheprovider -k "Probe or Contact"`
Expected: 13 failures (`AttributeError: 'TeslaBLE' object has no attribute 'probePresence'`; `observeContact` never called).

- [ ] **Step 3: Implement `_reportContact`, the reporting wrappers and `probePresence`**

In `lib/TWCManager/Vehicle/TeslaBLE.py`, in `__init__` after `self.commandTimeout = ble_config.get("commandTimeout", 5)` (line 115) add:

```python
        # body-controller-state took 4.2 s on the live box; give the presence
        # probe more room than a command so a slow answer isn't read as
        # "unreachable" (two of those would be a false departure).
        self.presenceProbeTimeout = ble_config.get("presenceProbeTimeout", 15)
```

Add after `_scheduleBlocksStart` (after line 199):

```python
    def _reportContact(self, vin, reachable, probe=False):
        # Tell VehiclePresence whether the car answered. It only records and
        # sets an event, so calling it while holding _bleLock is safe.
        presence = getattr(self.master, "vehiclePresence", None)
        if presence is None:
            return
        try:
            presence.observeContact(vin, reachable, probe=probe)
        except Exception as e:
            logger.debug(f"observeContact({vin}, {reachable}) failed: {e}")
```

Replace the decorator, signature and docstring of `_sendCommand_internal` (lines 488-493, from `@_serialized` through the closing `"""` of its docstring) with:

```python
    @_serialized
    def _sendCommand_internal(self, vin, command, args=None):
        """
        Internal sendCommand implementation (called by retry wrapper).
        Returns command output string or None on failure, and reports to
        VehiclePresence whether the car answered.
        """
        output = self._sendCommand_locked(vin, command, args)
        self._reportContact(vin, output is not None)
        return output

    def _sendCommand_locked(self, vin, command, args=None):
        # The old _sendCommand_internal body. Only called with _bleLock held.
```

The rest of the old body (from `try:` / `# Validate inputs` through the `finally: self._ensure_pipe_closed()`) stays exactly as it was, now inside `_sendCommand_locked`.

Replace the decorator, signature and docstring of `_fetch_state_json` (lines 935-937) with:

```python
    @_serialized
    def _fetch_state_json(self, vin, state_type):
        """Run `tesla-control state STATE_TYPE` and return parsed JSON dict, or None.
        Reports to VehiclePresence whether the car answered."""
        raw = self._fetch_state_locked(vin, state_type)
        self._reportContact(vin, raw is not None)
        return raw

    def _fetch_state_locked(self, vin, state_type):
        # The old _fetch_state_json body. Only called with _bleLock held.
```

The rest of the old body (from `if not self.binaryPath ...` through `finally: self._ensure_pipe_closed()`) stays as it was, now inside `_fetch_state_locked`.

Add after `wakeVehicle` (after line 917, before `_extract_enum_value`):

```python
    @_serialized
    def probePresence(self, vin):
        """
        Ask the body controller (VCSEC) whether this car is in BLE range,
        without waking it. `tesla-control body-controller-state` talks to
        VCSEC only and answers while infotainment is asleep.

        Returns {"reachable": bool, "awake": bool}. Runs once, with no retry:
        a presence probe is cheap to repeat and a failure is an answer.
        Never runs wake, state or ping.
        """
        result = {"reachable": False, "awake": False}
        if not self.binaryPath or not os.path.isfile(self.binaryPath):
            return result
        if not self.master.settings.get("Vehicles", {}).get(vin):
            return result

        self.sendPrivateKey(vin)

        command_string = [
            self.binaryPath,
            "-ble",
            "-vin",
            vin,
            "-key-file",
            self.pipeName,
            "body-controller-state",
        ]
        if self.isDocker():
            command_string.insert(0, "nsenter --net=/rootns/net")

        try:
            stdout, stderr, return_code = self._run_command_with_timeout(
                command_string, timeout=self.presenceProbeTimeout
            )
            if stdout is None or return_code != 0:
                logger.debug(f"BLE presence probe: {vin} not reachable (rc={return_code})")
                return result
            result["reachable"] = True
            status = None
            try:
                status = json.loads(stdout.decode("utf-8")).get("vehicleSleepStatus")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError) as e:
                logger.debug(f"BLE presence probe output for {vin} not parseable: {e}")
            # Any explicit status other than ASLEEP counts as awake. Missing
            # or unparseable output counts as asleep, so a sleeping car is
            # never read (and woken) on the strength of bad output.
            result["awake"] = (
                status is not None and status != "VEHICLE_SLEEP_STATUS_ASLEEP"
            )
            logger.debug(f"BLE presence probe: {vin} reachable, status {status}")
            return result
        except Exception as e:
            logger.debug(f"BLE presence probe exception for {vin}: {e}")
            return result
        finally:
            self._ensure_pipe_closed()
            self._reportContact(vin, result["reachable"], probe=True)
```

- [ ] **Step 4: Run the TeslaBLE tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslable_presence.py tests/unit/test_teslable_lock.py -q -p no:cacheprovider`
Expected: `23 passed`.

- [ ] **Step 5: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `552 passed, 1 warning`.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/Vehicle/TeslaBLE.py tests/unit/test_teslable_presence.py
git commit -m "$(cat <<'EOF'
Add a BLE presence probe that never wakes the car

probePresence runs body-controller-state once under the BLE lock; it
talks to VCSEC only, so it answers while infotainment sleeps. Every
BLE command, state read and probe now reports whether the car answered
to VehiclePresence.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

