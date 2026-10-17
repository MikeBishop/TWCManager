### Task 7: Arrival and departure handlers

**Files:**
- Create: `lib/TWCManager/PresenceHandlers.py`
- Modify: `lib/TWCManager/VehiclePresence.py` (`__init__` defaults for `onArrival`/`onDeparture`)
- Test: `tests/unit/test_presence_handlers.py` (create), `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Consumes: `VehiclePriority.resetChargeLimitState(vin)` and `.commandPolicy` (Task 3), `master.getNormalChargeLimit(vin)`, `master.saveNormalChargeLimit(vin, outside, lastApplied)`, `master.lastChargeLimitApplied`, `master.queue_vehicle_command(task)`, queue dispatch of `remoteOnly` (Task 1).
- Produces (`lib/TWCManager/PresenceHandlers.py`):
  - `hasRemoteChannel(master) -> bool`: TeslaAPI loaded and `commandPolicy != "ble_only"` (missing VehiclePriority counts as `prefer_ble`).
  - `arrivalHandler(master) -> callable(vin, currentLimit)`.
  - `departureHandler(master, remoteChannel=None) -> callable(vin, currentLimit)`; `remoteChannel` is a zero-arg callable, default `lambda: hasRemoteChannel(master)`.
  - `VehiclePresence(master)` with `onArrival=None` / `onDeparture=None` uses these.

- [ ] **Step 1: Write the failing handler tests**

Create `tests/unit/test_presence_handlers.py`:

```python
"""
Arrival/departure handlers. They run on the presence thread and only reset
dedupe state, adopt hand-set limits as the new normal, and queue commands.
"""

from unittest.mock import Mock, patch

import pytest

from TWCManager.PresenceHandlers import (
    arrivalHandler,
    departureHandler,
    hasRemoteChannel,
)

VIN = "5YJ3E1EA1KF000001"


def make_master(saved=(False, None, None), policyLimit=50, api=True, policy="prefer_ble"):
    master = Mock()
    master.lastChargeLimitApplied = policyLimit
    master.getNormalChargeLimit = Mock(return_value=saved)
    vp = Mock()
    vp.commandPolicy = policy
    modules = {"VehiclePriority": vp, "TeslaAPI": Mock() if api else None}
    master.getModuleByName = Mock(side_effect=lambda name: modules.get(name))
    master.vp = vp
    return master


class TestArrival:
    def test_resets_that_vin_and_queues_the_policy_limit_with_vin(self):
        master = make_master()
        arrivalHandler(master)(VIN, None)
        master.vp.resetChargeLimitState.assert_called_once_with(VIN)
        master.queue_vehicle_command.assert_called_once_with(
            {"cmd": "applyChargeLimit", "limit": 50, "vin": VIN}
        )
        master.saveNormalChargeLimit.assert_not_called()

    def test_without_a_policy_limit_queues_a_restore(self):
        master = make_master(policyLimit=0)
        arrivalHandler(master)(VIN, None)
        master.queue_vehicle_command.assert_called_once_with(
            {"cmd": "applyChargeLimit", "limit": -1, "vin": VIN}
        )

    def test_hand_set_limit_becomes_the_new_normal(self):
        master = make_master(saved=(True, 80, 50))
        arrivalHandler(master)(VIN, 100)
        master.saveNormalChargeLimit.assert_called_once_with(VIN, 100, 50)
        master.queue_vehicle_command.assert_called_once_with(
            {"cmd": "applyChargeLimit", "limit": 50, "vin": VIN}
        )

    def test_no_adoption_when_the_current_limit_is_what_we_applied(self):
        master = make_master(saved=(True, 80, 50))
        arrivalHandler(master)(VIN, 50)
        master.saveNormalChargeLimit.assert_not_called()

    def test_no_adoption_when_not_holding_a_limit(self):
        master = make_master(saved=(True, 80, -1))
        arrivalHandler(master)(VIN, 100)
        master.saveNormalChargeLimit.assert_not_called()

    def test_no_adoption_without_a_current_limit(self):
        master = make_master(saved=(True, 80, 50))
        arrivalHandler(master)(VIN, None)
        master.saveNormalChargeLimit.assert_not_called()

    def test_reset_falls_back_to_the_modules_without_vehicle_priority(self):
        master = make_master()
        ble, telemetry = Mock(), Mock(spec=[])
        modules = {"VehiclePriority": None, "TeslaAPI": Mock()}
        master.getModuleByName = Mock(side_effect=lambda name: modules.get(name))
        master.getModulesByType = Mock(
            return_value=[
                {"name": "TeslaBLE", "ref": ble, "priority": 20},
                {"name": "TeslaMateVehicle", "ref": telemetry, "priority": 0},
            ]
        )
        arrivalHandler(master)(VIN, None)
        ble.resetChargeLimitState.assert_called_once_with(VIN)


class TestDeparture:
    def test_restore_is_remote_only_and_carries_vin(self):
        master = make_master(saved=(True, 80, 50))
        departureHandler(master)(VIN, 50)
        master.vp.resetChargeLimitState.assert_called_once_with(VIN)
        master.queue_vehicle_command.assert_called_once_with(
            {"cmd": "applyChargeLimit", "limit": -1, "vin": VIN, "remoteOnly": True}
        )

    def test_restore_when_the_current_limit_is_unknown(self):
        master = make_master(saved=(True, 80, 50))
        departureHandler(master)(VIN, None)
        master.queue_vehicle_command.assert_called_once()

    def test_suppressed_when_the_limit_was_changed_by_hand(self):
        master = make_master(saved=(True, 80, 50))
        departureHandler(master)(VIN, 100)
        master.saveNormalChargeLimit.assert_called_once_with(VIN, 100, -1)
        master.queue_vehicle_command.assert_not_called()

    def test_nothing_queued_without_a_remote_channel(self):
        master = make_master(saved=(True, 80, 50), api=False)
        with patch("TWCManager.PresenceHandlers.logger") as log:
            departureHandler(master)(VIN, 50)
        master.vp.resetChargeLimitState.assert_called_once_with(VIN)
        master.queue_vehicle_command.assert_not_called()
        log.info.assert_called_once()

    @pytest.mark.parametrize("saved", [(False, None, None), (True, 80, -1)])
    def test_nothing_to_restore_when_not_holding_a_limit(self, saved):
        master = make_master(saved=saved)
        departureHandler(master)(VIN, 50)
        master.queue_vehicle_command.assert_not_called()

    def test_remote_channel_check_is_injectable(self):
        master = make_master(saved=(True, 80, 50))
        departureHandler(master, remoteChannel=lambda: False)(VIN, 50)
        master.queue_vehicle_command.assert_not_called()


class TestHasRemoteChannel:
    @pytest.mark.parametrize(
        "api, policy, expected",
        [
            (False, "prefer_ble", False),
            (True, "ble_only", False),
            (True, "prefer_ble", True),
            (True, "api_only", True),
        ],
    )
    def test_requires_tesla_api_and_a_policy_that_allows_it(self, api, policy, expected):
        assert hasRemoteChannel(make_master(api=api, policy=policy)) is expected

    def test_missing_vehicle_priority_counts_as_prefer_ble(self):
        master = make_master()
        modules = {"VehiclePriority": None, "TeslaAPI": Mock()}
        master.getModuleByName = Mock(side_effect=lambda name: modules.get(name))
        assert hasRemoteChannel(master) is True
```

Append to `class TestDefaults` in `tests/unit/test_vehicle_presence.py`:

```python
    def test_default_handlers_are_the_presence_handlers(self):
        master = Mock()
        master.config = {"config": {}}
        presence = VehiclePresence(master, knownVehicles=lambda: [])
        assert callable(presence._onArrival)
        assert callable(presence._onDeparture)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_presence_handlers.py -q -p no:cacheprovider; $VENV/bin/python -m pytest tests/unit/test_vehicle_presence.py -q -p no:cacheprovider -k default_handlers`
Expected: collection error (`No module named 'TWCManager.PresenceHandlers'`), then 1 failure (`_onArrival` is `None`).

- [ ] **Step 3: Implement the handlers**

Create `lib/TWCManager/PresenceHandlers.py`:

```python
# What happens when a vehicle arrives or departs. These run on the
# VehiclePresence thread and only do bookkeeping and queue commands; the
# vehicle command worker talks to the car.
from TWCManager.Logging.LoggerFactory import LoggerFactory

logger = LoggerFactory.get_logger("PresenceHandlers", "Vehicle")


def hasRemoteChannel(master):
    # A restore has to reach a car that has left home. Only the Fleet API
    # can, and only when commandPolicy lets it send commands.
    if not master.getModuleByName("TeslaAPI"):
        return False
    vp = master.getModuleByName("VehiclePriority")
    policy = vp.commandPolicy if vp else "prefer_ble"
    return policy != "ble_only"


def _resetLimitState(master, vin):
    # Every loaded module forgets what it last applied to this VIN only.
    vp = master.getModuleByName("VehiclePriority")
    if vp:
        vp.resetChargeLimitState(vin)
        return
    for module in master.getModulesByType("Vehicle"):
        ref = module["ref"]
        if hasattr(ref, "resetChargeLimitState"):
            ref.resetChargeLimitState(vin)


def arrivalHandler(master):
    def onArrival(vin, currentLimit):
        _resetLimitState(master, vin)
        hasSaved, outside, lastApplied = master.getNormalChargeLimit(vin)
        if (
            currentLimit is not None
            and hasSaved
            and lastApplied != -1
            and currentLimit != lastApplied
        ):
            # The limit was changed by hand while we weren't looking; that is
            # the new normal to restore to later.
            logger.info(
                "Vehicle %s charge limit was set to %s%% by hand; adopting it as the normal limit",
                vin,
                currentLimit,
            )
            master.saveNormalChargeLimit(vin, currentLimit, lastApplied)
        limit = master.lastChargeLimitApplied or -1
        logger.info("Vehicle %s arrived; applying charge limit %s", vin, limit)
        master.queue_vehicle_command(
            {"cmd": "applyChargeLimit", "limit": limit, "vin": vin}
        )

    return onArrival


def departureHandler(master, remoteChannel=None):
    if remoteChannel is None:
        remoteChannel = lambda: hasRemoteChannel(master)

    def onDeparture(vin, currentLimit):
        _resetLimitState(master, vin)
        hasSaved, outside, lastApplied = master.getNormalChargeLimit(vin)
        if not hasSaved or lastApplied == -1:
            logger.debug("Vehicle %s departed; no held charge limit to restore", vin)
            return
        if currentLimit is not None and currentLimit != lastApplied:
            # The user changed it; that is the new normal, nothing to restore.
            logger.info(
                "Vehicle %s departed with a hand-set limit of %s%%; keeping it",
                vin,
                currentLimit,
            )
            master.saveNormalChargeLimit(vin, currentLimit, -1)
            return
        if not remoteChannel():
            logger.info(
                "Vehicle %s departed, but no remote command channel can restore its normal charge limit of %s%%; it keeps %s%% until it returns",
                vin,
                outside,
                lastApplied,
            )
            return
        # Never over BLE: if BLE could reach the car it hasn't left. A failed
        # restore is dropped, not replayed; the next arrival applies the
        # policy limit and replaces any still-pending restore (same key).
        logger.info("Vehicle %s departed; restoring its normal charge limit", vin)
        master.queue_vehicle_command(
            {"cmd": "applyChargeLimit", "limit": -1, "vin": vin, "remoteOnly": True}
        )

    return onDeparture
```

In `lib/TWCManager/VehiclePresence.py`, add the import after `from TWCManager.PresenceSources import buildSources`:

```python
from TWCManager.PresenceHandlers import arrivalHandler, departureHandler
```

and change the two handler lines in `__init__` to:

```python
        self._onArrival = arrivalHandler(master) if onArrival is None else onArrival
        self._onDeparture = (
            departureHandler(master) if onDeparture is None else onDeparture
        )
```

- [ ] **Step 4: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `625 passed, 1 warning`.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/PresenceHandlers.py lib/TWCManager/VehiclePresence.py tests/unit/test_presence_handlers.py tests/unit/test_vehicle_presence.py
git commit -m "$(cat <<'EOF'
Add arrival and departure handlers for VehiclePresence

Arrival resets the vehicle's dedupe state, adopts a hand-set limit as
its new normal, and queues the policy limit for that VIN. Departure
queues a remote-only restore when the Fleet API can deliver it, and
otherwise logs once; failed restores are dropped, never replayed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

