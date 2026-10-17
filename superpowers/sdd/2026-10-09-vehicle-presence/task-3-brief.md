### Task 3: Vehicle modules become channels (`vin`, `remoteOnly`, `resetChargeLimitState`, no arrival/departure logic)

**Files:**
- Modify: `lib/TWCManager/Vehicle/VehiclePriority.py:88-193` (`__getattr__` → `_dispatch`, new methods)
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py:668-791` (`applyChargeLimit`), add `resetChargeLimitState`
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:716` (`car_api_charge` call), `:889-1055` (`applyChargeLimit`), `:1876-1885` (`CarApiVehicle.update_charge` head), add `resetChargeLimitState` after `vehicleIsDefinitelyHome`
- Modify: `lib/TWCManager/Vehicle/HomeAssistant.py:569` (`applyChargeLimit` signature and loop), add `resetChargeLimitState`
- Modify: `lib/TWCManager/TWCManager.py:321-341` (the `checkArrival`/`checkDeparture` branches call the removed flags; delete them here so every commit stays deployable)
- Test: `tests/unit/test_vehicle_priority.py`, `tests/unit/test_teslable_presence.py` (create), `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_homeassistant_presence.py` (create)

Line numbers in this task are from the branch base; Task 2 added two lines to `TeslaAPI.py` above `applyChargeLimit`, so search by method name rather than trusting the numbers.

**Interfaces:**
- Consumes: `VehicleCommandQueue` dispatch `module.applyChargeLimit(limit=, vin=, [remoteOnly=True])` (Task 1); VIN-keyed `get/save/removeNormalChargeLimit` (Task 2).
- Produces:
  - `VehiclePriority.applyChargeLimit(limit, vin=None, remoteOnly=False)`: priority fallback over modules, skipping `TeslaBLE` when `remoteOnly`; forwards `limit=`, `vin=` and `remoteOnly=` to the module.
  - `VehiclePriority.resetChargeLimitState(vin) -> True`: calls `resetChargeLimitState(vin)` on every `Vehicle`-type module that has it (fan-out, not first-success).
  - `TeslaBLE.applyChargeLimit(limit, vin=None, remoteOnly=False) -> bool` (`remoteOnly` accepted and ignored; BLE is never a remote channel); `TeslaBLE.resetChargeLimitState(vin) -> True`.
  - `TeslaAPI.applyChargeLimit(limit, vin=None, remoteOnly=False) -> "success" | "error"`; with `remoteOnly=True` every read on the path goes straight to the API: `vehicle.update_charge(allowBle=False)`. `TeslaAPI.resetChargeLimitState(vin) -> True`.
  - `CarApiVehicle.update_charge(allowBle=True) -> bool`: `allowBle=False` skips the BLE `get_charge_state` attempt and the `ble.wakeVehicle` fallback.
  - `HomeAssistant.applyChargeLimit(limit, vin=None, *args, **kwargs)`; `HomeAssistant.resetChargeLimitState(vin) -> True` (no-op).

- [ ] **Step 1: Write the failing VehiclePriority tests**

Append to `tests/unit/test_vehicle_priority.py`:

```python
class TestChannelInterface:
    """applyChargeLimit honours remoteOnly; resetChargeLimitState fans out."""

    def make_master(self, policy="prefer_ble"):
        master = Mock()
        master.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
        master.config = {}
        master.settings = {"commandPolicy": policy}
        return master

    def make_modules(self, master):
        ble = Mock()
        ble.applyChargeLimit = Mock(return_value=True)
        api = Mock()
        api.applyChargeLimit = Mock(return_value="success")
        master.getModuleByPriority = Mock(
            side_effect=[("TeslaBLE", ble, 20), ("TeslaAPI", api, 10), ("", None, 0)]
        )
        return ble, api

    def test_remote_only_skips_ble(self):
        from TWCManager.Vehicle.VehiclePriority import VehiclePriority

        master = self.make_master()
        ble, api = self.make_modules(master)
        priority = VehiclePriority(master)

        assert priority.applyChargeLimit(-1, vin="V1", remoteOnly=True) == "success"
        ble.applyChargeLimit.assert_not_called()
        api.applyChargeLimit.assert_called_once_with(limit=-1, vin="V1", remoteOnly=True)

    def test_without_remote_only_ble_is_tried_first(self):
        from TWCManager.Vehicle.VehiclePriority import VehiclePriority

        master = self.make_master()
        ble, api = self.make_modules(master)
        priority = VehiclePriority(master)

        assert priority.applyChargeLimit(70, vin="V1") is True
        ble.applyChargeLimit.assert_called_once_with(limit=70, vin="V1", remoteOnly=False)
        api.applyChargeLimit.assert_not_called()

    def test_reset_charge_limit_state_fans_out_to_every_module(self):
        from TWCManager.Vehicle.VehiclePriority import VehiclePriority

        master = self.make_master()
        priority = VehiclePriority(master)
        ble, api = Mock(), Mock()
        master.getModulesByType = Mock(
            return_value=[
                {"name": "VehiclePriority", "ref": priority, "priority": 0},
                {"name": "TeslaBLE", "ref": ble, "priority": 20},
                {"name": "TeslaAPI", "ref": api, "priority": 10},
            ]
        )

        assert priority.resetChargeLimitState("V1") is True
        ble.resetChargeLimitState.assert_called_once_with("V1")
        api.resetChargeLimitState.assert_called_once_with("V1")
        master.getModulesByType.assert_called_once_with("Vehicle")

    def test_reset_skips_modules_without_the_method_and_survives_errors(self):
        from TWCManager.Vehicle.VehiclePriority import VehiclePriority

        master = self.make_master()
        priority = VehiclePriority(master)
        telemetry = Mock(spec=[])
        ble = Mock()
        ble.resetChargeLimitState = Mock(side_effect=RuntimeError("boom"))
        api = Mock()
        master.getModulesByType = Mock(
            return_value=[
                {"name": "TeslaMateVehicle", "ref": telemetry, "priority": 0},
                {"name": "TeslaBLE", "ref": ble, "priority": 20},
                {"name": "TeslaAPI", "ref": api, "priority": 10},
            ]
        )

        assert priority.resetChargeLimitState("V1") is True
        api.resetChargeLimitState.assert_called_once_with("V1")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_priority.py -q -p no:cacheprovider -k TestChannelInterface`
Expected: 4 failures. `test_remote_only_skips_ble` fails because the proxy calls BLE first; `resetChargeLimitState` tests fail because the `__getattr__` proxy uses `getModuleByPriority`, not `getModulesByType`.

- [ ] **Step 3: Refactor VehiclePriority**

In `lib/TWCManager/Vehicle/VehiclePriority.py`, replace the whole `__getattr__` method (lines 88-193, from `def __getattr__(self, name):` to the end of the file) with:

```python
    def applyChargeLimit(self, limit, vin=None, remoteOnly=False):
        # remoteOnly: the car may have left home, so only a channel that
        # reaches it away from home (the Fleet API) may try. BLE is skipped
        # entirely: if BLE could reach the car it hasn't left, and a BLE
        # restore would just be overwritten by the arrival apply. The flag is
        # forwarded so TeslaAPI also keeps its reads off BLE.
        skip = ("TeslaBLE",) if remoteOnly else ()
        return self._dispatch(
            "applyChargeLimit",
            (),
            {"limit": limit, "vin": vin, "remoteOnly": remoteOnly},
            skip=skip,
        )

    def resetChargeLimitState(self, vin):
        # Fan-out, not first-success: every loaded module forgets what it
        # last applied to this VIN, so the next apply is sent again.
        for module in self.master.getModulesByType("Vehicle"):
            ref = module["ref"]
            if ref is self or not hasattr(ref, "resetChargeLimitState"):
                continue
            try:
                ref.resetChargeLimitState(vin)
            except Exception as e:
                logger.debug(
                    f"VehiclePriority: {module['name']}.resetChargeLimitState({vin}) raised {e}"
                )
        return True

    def __getattr__(self, name):
        def method(*args, **kwargs):
            return self._dispatch(name, args, kwargs)

        return method

    def _dispatch(self, name, args, kwargs, skip=()):
        ret = False
        priority = 100
        module_name = None
        module_ref = None

        logger.debug(f"VehiclePriority: Attempting to call {name} with priority fallback")

        # Try each module in priority order
        while priority > 0:
            module_name, module_ref, priority = self.master.getModuleByPriority(
                "Vehicle", priority
            )

            # If no module found at this priority level, we've exhausted all options
            if not module_ref or not module_name:
                logger.debug(f"VehiclePriority: No more modules available for {name}")
                break

            if self._skip_module_for_command(module_name, name):
                logger.log(
                    logging.INFO2,
                    f"VehiclePriority: commandPolicy {self.commandPolicy} excludes {module_name} for {name}",
                )
                continue

            if module_name in skip:
                logger.debug(
                    f"VehiclePriority: {module_name} skipped for {name} by caller"
                )
                continue

            # Calculate retries for this priority level
            retries = self._calculate_retries(priority)
            max_attempts = retries + 1  # +1 for the initial attempt

            logger.debug(
                f"VehiclePriority: Trying {module_name} for {name} (priority {priority}, {max_attempts} attempts)"
            )

            # Try this module up to max_attempts times
            for attempt in range(max_attempts):
                try:
                    # Check if module has the requested method
                    if hasattr(module_ref, name):
                        if attempt > 0:
                            logger.debug(
                                f"VehiclePriority: Retry {attempt}/{retries} for {module_name}.{name}()"
                            )

                        module_method = getattr(module_ref, name)
                        ret = module_method(*args, **kwargs)

                        # Track success/failure
                        # TeslaAPI returns "success"/"error" strings; treat
                        # "error" as failure so the priority fallback works.
                        if ret and ret != "error":
                            logger.debug(
                                f"VehiclePriority: {module_name}.{name}() succeeded on attempt {attempt + 1}"
                            )
                            self.master.stats["moduleSuccess"][module_name] = (
                                self.master.stats["moduleSuccess"].get(module_name, 0)
                                + 1
                            )
                            return ret  # Success, return immediately
                        else:
                            # Failed, but we might retry
                            if attempt < retries:
                                logger.debug(
                                    f"VehiclePriority: {module_name}.{name}() failed, retrying ({attempt + 1}/{retries})"
                                )
                            else:
                                logger.debug(
                                    f"VehiclePriority: {module_name}.{name}() failed after {max_attempts} attempts, trying next module"
                                )
                                self.master.stats["moduleFailures"][module_name] = (
                                    self.master.stats["moduleFailures"].get(
                                        module_name, 0
                                    )
                                    + 1
                                )
                    else:
                        logger.debug(
                            f"VehiclePriority: {module_name} does not have method {name}"
                        )
                        break  # Method doesn't exist, don't retry
                except Exception as e:
                    # Log failure and continue to next attempt or module
                    if attempt < retries:
                        logger.debug(
                            f"VehiclePriority: Exception in {module_name}.{name}() on attempt {attempt + 1}: {str(e)}, retrying"
                        )
                    else:
                        logger.debug(
                            f"VehiclePriority: Exception in {module_name}.{name}() after {max_attempts} attempts: {str(e)}, trying next module"
                        )
                        self.master.stats["moduleFailures"][module_name] = (
                            self.master.stats["moduleFailures"].get(module_name, 0) + 1
                        )
                    continue

        logger.debug(
            f"VehiclePriority: All modules exhausted for {name}, returning {ret}"
        )
        return ret
```

- [ ] **Step 4: Run the VehiclePriority tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_priority.py -q -p no:cacheprovider`
Expected: `41 passed`.

- [ ] **Step 5: Write the failing TeslaBLE channel tests**

Create `tests/unit/test_teslable_presence.py`:

```python
"""
TeslaBLE as a presence channel: per-VIN applyChargeLimit,
resetChargeLimitState, probePresence and contact reporting.
"""

import base64
import json
from unittest.mock import Mock, patch

import pytest

from TWCManager.Vehicle.TeslaBLE import TeslaBLE

VIN1 = "5YJ3E1EA1KF000001"
VIN2 = "5YJ3E1EA1KF000002"


def key_material():
    return {
        "privKey": base64.b64encode(b"private").decode(),
        "pubKeyPEM": base64.b64encode(b"public").decode(),
    }


@pytest.fixture
def ble(tmp_path):
    master = Mock()
    master.config = {"config": {"teslaControlPath": "/fake/tesla-control"}}
    master.settings = {"Vehicles": {VIN1: key_material(), VIN2: key_material()}}
    master.getNormalChargeLimit = Mock(return_value=(False, None, None))
    with patch.object(TeslaBLE, "pipeName", str(tmp_path / "ble_data")), patch(
        "TWCManager.Vehicle.TeslaBLE.shutil.which", return_value=None
    ), patch(
        "TWCManager.Vehicle.TeslaBLE.os.path.isfile", return_value=True
    ), patch(
        "TWCManager.Vehicle.TeslaBLE.os.access", return_value=True
    ):
        instance = TeslaBLE(master)
        instance.isDockerCached = False
        instance.maxRetries = 0
        yield instance


class CommandRecorder:
    """Stand-in for _run_command_with_timeout. Records the tesla-control
    sub-command of each call and answers from `responses`, a list of
    (stdout, stderr, rc) tuples consumed in order (last one repeats)."""

    def __init__(self, responses, ble=None):
        self.responses = list(responses)
        self.commands = []
        self.timeouts = []
        self.locked_during_call = []
        self.ble = ble

    def __call__(self, command_string, timeout, use_process_group=True):
        # command_string: [binary, ("-debug",)? "-ble", "-vin", VIN, "-key-file", path, cmd, (arg)?]
        idx = command_string.index("-key-file") + 2
        self.commands.append(tuple(command_string[idx:]))
        self.timeouts.append(timeout)
        if self.ble is not None:
            self.locked_during_call.append(self.ble._bleLock.locked())
        response = self.responses[0]
        if len(self.responses) > 1:
            self.responses.pop(0)
        return response


class TestApplyChargeLimitPerVin:
    def test_vin_targets_only_that_vehicle(self, ble):
        recorder = CommandRecorder([(b"", b"ok", 0)])
        ble._run_command_with_timeout = recorder
        assert ble.applyChargeLimit(70, vin=VIN2) is True
        # wake then charging-set-limit, both for VIN2 only
        assert recorder.commands == [("wake",), ("charging-set-limit", "70")]
        assert ble._lastAppliedChargeLimit == {VIN2: 70}
        ble.master.saveNormalChargeLimit.assert_called_once_with(VIN2, 70, 70)

    def test_unknown_vin_is_rejected(self, ble):
        recorder = CommandRecorder([(b"", b"ok", 0)])
        ble._run_command_with_timeout = recorder
        assert ble.applyChargeLimit(70, vin="NOPE") is False
        assert recorder.commands == []

    def test_no_vin_applies_to_every_vehicle(self, ble):
        recorder = CommandRecorder([(b"", b"ok", 0)])
        ble._run_command_with_timeout = recorder
        assert ble.applyChargeLimit(70) is True
        assert sorted(ble._lastAppliedChargeLimit) == [VIN1, VIN2]


class TestResetChargeLimitState:
    def test_resets_only_that_vin(self, ble):
        ble._stopTryingToApplyLimit = {VIN1: True, VIN2: True}
        ble._lastAppliedChargeLimit = {VIN1: 70, VIN2: 70}
        assert ble.resetChargeLimitState(VIN1) is True
        assert ble._stopTryingToApplyLimit == {VIN2: True}
        assert ble._lastAppliedChargeLimit == {VIN2: 70}

    def test_reset_makes_the_next_apply_send_again(self, ble):
        recorder = CommandRecorder([(b"", b"ok", 0)])
        ble._run_command_with_timeout = recorder
        ble.applyChargeLimit(70, vin=VIN1)
        ble.applyChargeLimit(70, vin=VIN1)  # deduped: nothing sent
        assert recorder.commands.count(("charging-set-limit", "70")) == 1
        ble.resetChargeLimitState(VIN1)
        ble.applyChargeLimit(70, vin=VIN1)
        assert recorder.commands.count(("charging-set-limit", "70")) == 2
```

- [ ] **Step 6: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslable_presence.py -q -p no:cacheprovider`
Expected: 5 failures (`TypeError: applyChargeLimit() got an unexpected keyword argument 'vin'`; `AttributeError: ... no attribute 'resetChargeLimitState'`).

- [ ] **Step 7: Implement the TeslaBLE channel methods**

In `lib/TWCManager/Vehicle/TeslaBLE.py`, replace the signature, docstring and vehicle-selection prologue of `applyChargeLimit` (lines 668-697, from `def applyChargeLimit(self, limit, checkArrival=False, checkDeparture=False):` through `for vehicle_vin in self.master.settings["Vehicles"].keys():`) with:

```python
    def applyChargeLimit(self, limit, vin=None, remoteOnly=False):
        """
        Apply charge limit via BLE to one vehicle (vin given) or to every
        vehicle in settings (vin None: the policy-wide apply).
        Args:
            limit: Charge limit percentage (50-100), or -1 to restore to pre-TWCManager default
            vin: Target one vehicle only. Presence (arrival/departure) is the
                 caller's decision; this method just sends.
            remoteOnly: Accepted for interface symmetry and ignored; BLE is
                 never a remote channel (VehiclePriority skips this module
                 when it is set).
        Returns True on success, False on failure.
        """
        try:
            if limit != -1 and (limit < 50 or limit > 100):
                logger.error(
                    f"Invalid charge limit {limit}%; must be 50-100 or -1 to restore"
                )
                return False

            vehicles = self.master.settings.get("Vehicles") or {}
            if vin is not None:
                if vin not in vehicles:
                    logger.error(f"Vehicle {vin} not found in settings; cannot apply charge limit")
                    return False
                targets = [vin]
            else:
                if not vehicles:
                    logger.error("No vehicles configured for charge limit")
                    return False
                targets = list(vehicles.keys())

            logger.debug(
                f"Applying charge limit {limit}{'%' if limit != -1 else ' (restore default)'} to {', '.join(targets)}"
            )

            success_count = 0
            attempted_count = 0
            skipped_count = 0

            for vehicle_vin in targets:
```

The loop body and the summary logging after it are unchanged. Then add after `applyChargeLimit` (before `def startCharging`):

```python
    def resetChargeLimitState(self, vin):
        """Forget the dedupe state for one VIN so the next applyChargeLimit sends again."""
        self._stopTryingToApplyLimit.pop(vin, None)
        self._lastAppliedChargeLimit.pop(vin, None)
        return True
```

- [ ] **Step 8: Run the TeslaBLE tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslable_presence.py tests/unit/test_teslable_lock.py -q -p no:cacheprovider`
Expected: `10 passed`.

- [ ] **Step 9: Write the failing TeslaAPI channel tests**

Append to `tests/unit/test_teslaapi_presence.py`:

```python
class FakeVehicle:
    """Minimal CarApiVehicle stand-in for applyChargeLimit."""

    def __init__(self, vin, ID, atHome=True, chargeLimit=80):
        self.VIN = vin
        self.ID = ID
        self.name = vin
        self.atHome = atHome
        self.chargeLimit = chargeLimit
        self.stopTryingToApplyLimit = False
        self.stopAskingToStartCharging = False
        self.applied = []
        self.allowBle = []

    def ready(self):
        return True

    def update_charge(self, allowBle=True):
        self.allowBle.append(allowBle)
        return True

    def apply_charge_limit(self, limit):
        self.applied.append(limit)
        self.chargeLimit = limit
        return True


@pytest.fixture
def api_with_vehicles():
    api = make_api()
    v1 = FakeVehicle(VIN1, 1, atHome=True)
    v2 = FakeVehicle(VIN2, 2, atHome=False)
    api.carApiVehicles = [v1, v2]
    with patch("TWCManager.Vehicle.TeslaAPI.time.sleep"):
        yield api, v1, v2


class TestApplyChargeLimitChannel:
    def test_flags_are_gone(self):
        params = list(inspect.signature(TeslaAPI.applyChargeLimit).parameters)
        assert params == ["self", "limit", "vin", "remoteOnly"]
        source = inspect.getsource(TeslaAPI.applyChargeLimit)
        assert "update_location" not in source
        assert "has departed" not in source

    def test_policy_wide_apply_targets_at_home_vehicles_only(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        assert api.applyChargeLimit(70) == "success"
        assert v1.applied == [70]
        assert v2.applied == []
        api.master.saveNormalChargeLimit.assert_called_once_with(VIN1, 80, 70)

    def test_per_vin_apply_targets_only_that_vehicle(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        v2.atHome = True
        assert api.applyChargeLimit(70, vin=VIN1) == "success"
        assert v1.applied == [70]
        assert v2.applied == []

    def test_per_vin_apply_ignores_at_home(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        assert api.applyChargeLimit(70, vin=VIN2) == "success"
        assert v2.applied == [70]

    def test_per_vin_apply_bypasses_rate_limit(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        api.carApiLastChargeLimitApplyTime = time.time()
        assert api.applyChargeLimit(70) == "error"
        assert api.applyChargeLimit(70, vin=VIN1) == "success"
        assert v1.applied == [70]

    def test_restore_sends_saved_normal_and_saves_by_vin(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        v2.chargeLimit = 70
        api.master.getNormalChargeLimit = Mock(return_value=(True, 90, 70))
        assert api.applyChargeLimit(-1, vin=VIN2) == "success"
        assert v2.applied == [90]
        api.master.saveNormalChargeLimit.assert_called_once_with(VIN2, 90, -1)

    def test_restore_leaves_hand_changed_limit_alone(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        v2.chargeLimit = 100  # user raised it after we applied 70
        api.master.getNormalChargeLimit = Mock(return_value=(True, 90, 70))
        assert api.applyChargeLimit(-1, vin=VIN2) == "success"
        assert v2.applied == []
        api.master.saveNormalChargeLimit.assert_called_once_with(VIN2, 100, -1)

    def test_unknown_vin_is_an_error(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        assert api.applyChargeLimit(70, vin="NOPE") == "error"

    def test_remote_only_restore_reads_without_ble(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        v2.chargeLimit = 70
        api.master.getNormalChargeLimit = Mock(return_value=(True, 90, 70))
        assert api.applyChargeLimit(-1, vin=VIN2, remoteOnly=True) == "success"
        assert v2.allowBle == [False]
        assert v2.applied == [90]
        # The default path keeps today's behaviour.
        v1.chargeLimit = 70
        assert api.applyChargeLimit(-1, vin=VIN1) == "success"
        assert v1.allowBle == [True]

    def test_update_charge_without_ble_never_calls_tesla_ble(self):
        from TWCManager.Vehicle.TeslaAPI import CarApiVehicle

        carapi = Mock()
        vp, ble = Mock(), Mock()
        vp.commandPolicy = "prefer_ble"
        modules = {"VehiclePriority": vp, "TeslaBLE": ble}
        carapi.master.getModuleByName = Mock(side_effect=lambda name: modules.get(name))
        vehicle = CarApiVehicle({"id": 1, "vin": VIN1, "display_name": "Car"}, carapi, {"config": {}})
        vehicle.lastAPIAccessTime = 0  # old enough that the wake fallback would fire
        vehicle.update_vehicle_data = Mock(return_value=True)

        assert vehicle.update_charge(allowBle=False) is True
        ble.get_charge_state.assert_not_called()
        ble.wakeVehicle.assert_not_called()
        vehicle.update_vehicle_data.assert_called_once()

        ble.get_charge_state = Mock(return_value={"chargeLimit": 80})
        assert vehicle.update_charge() is True
        ble.get_charge_state.assert_called_once_with(VIN1)
        assert vehicle.chargeLimit == 80

    def test_per_vin_apply_leaves_policy_wide_state_alone(self, api_with_vehicles):
        # A departure restore must not become TeslaAPI's idea of the policy
        # limit (car_api_charge re-applies lastChargeLimitApplied), and an
        # arrival apply must not block the next policy-wide apply for 60 s.
        api, v1, v2 = api_with_vehicles
        api.lastChargeLimitApplied = 70
        api.master.getNormalChargeLimit = Mock(return_value=(True, 90, 70))
        v2.chargeLimit = 70
        assert api.applyChargeLimit(-1, vin=VIN2) == "success"
        assert api.lastChargeLimitApplied == 70
        assert api.carApiLastChargeLimitApplyTime == 0

    def test_reset_charge_limit_state_only_that_vin(self, api_with_vehicles):
        api, v1, v2 = api_with_vehicles
        v1.stopTryingToApplyLimit = True
        v2.stopTryingToApplyLimit = True
        assert api.resetChargeLimitState(VIN1) is True
        assert v1.stopTryingToApplyLimit is False
        assert v2.stopTryingToApplyLimit is True
```

- [ ] **Step 10: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslaapi_presence.py -q -p no:cacheprovider`
Expected: 12 failures in `TestApplyChargeLimitChannel` (signature still has the flags; `vin`/`remoteOnly`/`allowBle` kwargs rejected; no `resetChargeLimitState`), 2 passes from Task 2.

- [ ] **Step 11: Rewrite TeslaAPI.applyChargeLimit and add resetChargeLimitState**

In `lib/TWCManager/Vehicle/TeslaAPI.py`, line 716 in `car_api_charge`, change:

```python
                self.applyChargeLimit(self.lastChargeLimitApplied, checkArrival=True)
```
to
```python
                self.applyChargeLimit(self.lastChargeLimitApplied)
```

Replace the whole `applyChargeLimit` method (lines 889-1055, from `def applyChargeLimit(self, limit, checkArrival=False, checkDeparture=False):` through the final `if checkArrival:` / `self.updateChargeAtHome()` lines) with:

```python
    def applyChargeLimit(self, limit, vin=None, remoteOnly=False):
        # Apply `limit` (or restore the saved normal limit when -1) through
        # the Fleet API.
        #
        # vin=None is the policy-wide apply: it targets the vehicles we
        # believe are at home and is rate limited to once a minute.
        # With a vin, the caller (VehiclePresence) has already decided that
        # this vehicle needs the command, so neither gate applies. Presence
        # (arrival/departure) is no longer decided here.
        #
        # remoteOnly (the departure restore): the car has left, so nothing
        # on this path may touch BLE, reads included; update_charge goes
        # straight to the API instead of trying BLE and then a BLE wake.
        if limit != -1 and (limit < 50 or limit > 100):
            logger.log(logging.INFO8, "applyChargeLimit skipped")
            return "error"

        if not self.car_api_available():
            logger.log(
                logging.INFO8,
                "applyChargeLimit return because car_api_available() == False",
            )
            return "error"

        now = time.time()
        if vin is None and now - self.carApiLastChargeLimitApplyTime < 60:
            # Don't change limits more often than once a minute
            logger.log(
                logging.DEBUG2,
                "applyChargeLimit return because under 60 sec since last carApiLastChargeLimitApplyTime",
            )
            return "error"

        vehicles = [v for v in self.carApiVehicles if vin is None or v.VIN == vin]
        if vin is not None and not vehicles:
            logger.log(logging.INFO2, "applyChargeLimit: no API vehicle with VIN " + str(vin))
            return "error"

        needToWake = False
        for vehicle in vehicles:
            hasSaved, outside, lastApplied = self.master.getNormalChargeLimit(
                vehicle.VIN
            )
            if limit != lastApplied:
                vehicle.stopTryingToApplyLimit = False
            # Don't wake cars to tell them about reduced limits;
            # only wake if they might be able to charge further now
            if hasSaved and limit > (lastApplied if lastApplied != -1 else outside):
                needToWake = True
                vehicle.stopAskingToStartCharging = False

        if needToWake and self.car_api_available(applyLimit=True) is False:
            logger.log(
                logging.INFO8,
                "applyChargeLimit return because car_api_available() == False",
            )
            return "error"

        if self.lastChargeLimitApplied != limit:
            if limit != -1:
                logger.log(
                    logging.INFO2,
                    "Attempting to apply limit of "
                    + str(limit)
                    + "% to "
                    + ("all vehicles at home" if vin is None else str(vin)),
                )
            else:
                logger.log(
                    logging.INFO2,
                    "Attempting to restore charge limits for "
                    + ("all vehicles at home" if vin is None else str(vin)),
                )
            if vin is None:
                self.lastChargeLimitApplied = limit

        if vin is None:
            # Only the policy-wide apply owns the policy state and the rate
            # limiter; a per-VIN arrival or departure must not disturb them.
            self.carApiLastChargeLimitApplyTime = now

        needSleep = False
        for vehicle in vehicles:
            if vehicle.stopTryingToApplyLimit or not vehicle.ready():
                continue

            if not vehicle.update_charge(allowBle=not remoteOnly):
                # We failed to read the current limit; don't risk changing it.
                continue

            if vin is None and not vehicle.atHome:
                continue

            hasSaved, outside, lastApplied = self.master.getNormalChargeLimit(
                vehicle.VIN
            )
            if not hasSaved or lastApplied == -1:
                # We're not holding a limit on this car, so whatever it has
                # now is its normal limit.
                outside = vehicle.chargeLimit

            if limit == -1:
                if not hasSaved:
                    vehicle.stopTryingToApplyLimit = True
                    continue
                if vehicle.chargeLimit == lastApplied and vehicle.chargeLimit != outside:
                    if vehicle.apply_charge_limit(outside):
                        logger.log(
                            logging.INFO2,
                            "Restoring "
                            + vehicle.name
                            + " to charge limit "
                            + str(outside)
                            + "%",
                        )
                        vehicle.stopTryingToApplyLimit = True
                else:
                    # The limit was changed by hand since we applied it;
                    # user action overrides the saved limit. Leave it alone.
                    vehicle.stopTryingToApplyLimit = True
                    outside = vehicle.chargeLimit

                if vehicle.stopTryingToApplyLimit:
                    self.master.saveNormalChargeLimit(vehicle.VIN, outside, -1)
            else:
                if vehicle.chargeLimit != limit:
                    if vehicle.apply_charge_limit(limit):
                        logger.log(
                            logging.INFO2,
                            "Set "
                            + vehicle.name
                            + " to charge limit of "
                            + str(limit)
                            + "%",
                        )
                        vehicle.stopTryingToApplyLimit = True
                else:
                    vehicle.stopTryingToApplyLimit = True

                if vehicle.stopTryingToApplyLimit:
                    self.master.saveNormalChargeLimit(vehicle.VIN, outside, limit)

            if vehicle.stopTryingToApplyLimit:
                needSleep = True

        if needSleep:
            # If you start charging too quickly after setting the charge limit,
            # the vehicle sometimes refuses the start command because it's
            # "fully charged" under the old limit, but then continues to say
            # charging was stopped once the new limit is in place.
            time.sleep(5)

        if any(vehicle.stopTryingToApplyLimit for vehicle in vehicles):
            return "success"
        return "error"
```

In `class CarApiVehicle`, change the head of `update_charge` (lines 1876-1885, from `def update_charge(self):` through `if policy != "api_only":`) to:

```python
    def update_charge(self, allowBle=True):
        # allowBle=False (a remote-only restore for a car that has left)
        # skips the BLE read and its wake fallback and goes to the API.
        if self.syncSource == "TeslaAPI":
            # Try BLE first if policy allows
            try:
                vp = self.carapi.master.getModuleByName("VehiclePriority")
                policy = vp.commandPolicy if vp else "prefer_ble"
            except Exception:
                policy = "prefer_ble"

            if allowBle and policy != "api_only":
```

The rest of the method (`ble = self.carapi.master.getModuleByName("TeslaBLE")` onwards) is unchanged.

Add after `vehicleIsDefinitelyHome` (before `def wakeVehicle`):

```python
    def resetChargeLimitState(self, vin):
        # Forget the dedupe flag for one vehicle so the next applyChargeLimit
        # sends to it again.
        for vehicle in self.carApiVehicles:
            if vehicle.VIN == vin:
                vehicle.stopTryingToApplyLimit = False
        return True
```

- [ ] **Step 12: Run the TeslaAPI tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_teslaapi_presence.py tests/unit/test_teslaapi_fleetlogin.py -q -p no:cacheprovider`
Expected: `24 passed`.

- [ ] **Step 13: Write the failing HomeAssistant tests**

Create `tests/unit/test_homeassistant_presence.py`:

```python
"""HomeAssistant as a presence channel: vin parameter and a no-op reset."""

from unittest.mock import Mock, patch

from TWCManager.Vehicle.HomeAssistant import HaVehicle, HomeAssistant

VIN1 = "5YJ3E1EA1KF000001"
VIN2 = "5YJ3E1EA1KF000002"


def make_ha():
    master = Mock()
    # Disabled: __init__ returns before any network access.
    master.config = {"vehicle": {"HomeAssistant": {"enabled": False}}}
    ha = HomeAssistant(master)
    ha.car_api_available = Mock(return_value=True)
    ha._is_vehicle_connected = Mock(return_value=True)
    ha._call_service = Mock(return_value=True)
    ha.carApiVehicles = [
        HaVehicle("One", VIN1, "dev1", {"charge_limit_number": "number.one_limit"}),
        HaVehicle("Two", VIN2, "dev2", {"charge_limit_number": "number.two_limit"}),
    ]
    for v in ha.carApiVehicles:
        v.at_home = True
    return ha


def test_apply_charge_limit_with_vin_targets_only_that_vehicle():
    ha = make_ha()
    with patch.object(HaVehicle, "refresh_from_home_assistant", return_value=True):
        assert ha.applyChargeLimit(70, vin=VIN2) == "success"
    ha._call_service.assert_called_once_with(
        "number", "set_value", {"entity_id": "number.two_limit", "value": 70}
    )


def test_reset_charge_limit_state_is_a_noop():
    ha = make_ha()
    assert ha.resetChargeLimitState(VIN1) is True
```

- [ ] **Step 14: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_homeassistant_presence.py -q -p no:cacheprovider`
Expected: 2 failures (`_call_service` called twice; no `resetChargeLimitState`).

- [ ] **Step 15: Implement the HomeAssistant changes**

In `lib/TWCManager/Vehicle/HomeAssistant.py`, change the `applyChargeLimit` signature (line 569) from `def applyChargeLimit(self, limit: int, *args, **kwargs):` to:

```python
    def applyChargeLimit(
        self, limit: int, vin: Optional[str] = None, *args, **kwargs
    ):
```

and insert at the top of the `for v in self.carApiVehicles:` loop body (before `v.refresh_from_home_assistant(self)`):

```python
            if vin is not None and v.vin != vin:
                continue
```

Add after `applyChargeLimit` (before `def setChargeRate`):

```python
    def resetChargeLimitState(self, vin: str) -> bool:
        # Home Assistant keeps no per-vehicle dedupe state; nothing to reset.
        return True
```

- [ ] **Step 16: Remove the launcher's `checkArrival`/`checkDeparture` branches**

They called `applyChargeLimit(limit=..., checkArrival=True)` / `checkDeparture=True`, which no longer exists. In `lib/TWCManager/TWCManager.py`, delete lines 321-332 and 335-341 (the two branches and their comment) so the `if "cmd" in task:` block begins:

```python
            if "cmd" in task:
                if task["cmd"] == "checkCharge":
                    vehicleModule.updateChargeAtHome()
                elif task["cmd"] == "checkGreenEnergy":
                    check_green_energy()
```

Until Task 8 rewires them, `TWCSlave` and `HTTPControl` still queue `checkArrival`/`checkDeparture` tasks; `background_tasks_thread` now ignores them (no branch matches), which is harmless.

Run: `grep -n "checkArrival\|checkDeparture" lib/TWCManager/TWCManager.py`
Expected: no output.

- [ ] **Step 17: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `539 passed, 1 warning`.

- [ ] **Step 18: Commit**

```bash
git add lib/TWCManager/Vehicle/VehiclePriority.py lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/HomeAssistant.py lib/TWCManager/TWCManager.py tests/unit/test_vehicle_priority.py tests/unit/test_teslable_presence.py tests/unit/test_teslaapi_presence.py tests/unit/test_homeassistant_presence.py
git commit -m "$(cat <<'EOF'
Turn the vehicle modules into charge-limit channels

applyChargeLimit takes a vin instead of checkArrival/checkDeparture
flags, and TeslaAPI no longer decides arrival or departure itself.
resetChargeLimitState(vin) clears one vehicle's dedupe state, fanned
out through VehiclePriority, which also honours remoteOnly by skipping
BLE.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

