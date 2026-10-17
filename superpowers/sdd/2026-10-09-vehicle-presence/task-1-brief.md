### Task 1: Vehicle queue `(cmd, vin)` keying, `cancel()`, and TWCMaster start/stop/cancelStop

**Files:**
- Modify: `lib/TWCManager/VehicleCommandQueue.py` (header comment lines 1-11, `_DISPATCH` lines 22-31, `_key` lines 42-50, add `cancel` after `put`)
- Modify: `lib/TWCManager/TWCMaster.py:166-167` (`cancelStopCarsCharging`), `:1860-1893` (`startCarsCharging`, `stopCarsCharging`)
- Test: `tests/unit/test_vehicle_command_queue.py`, `tests/unit/test_twcmaster.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `VehicleCommandQueue._key(task) -> (cmd, vin)` where `vin = task.get("vin")`, or `task["vehicle"].VIN` for `setChargeRate`.
  - `VehicleCommandQueue.cancel(cmd: str, match: Callable[[dict], bool]) -> int` removes pending entries with `task["cmd"] == cmd and match(task)`; never touches the running entry.
  - `applyChargeLimit` dispatch calls `module.applyChargeLimit(limit=task["limit"], vin=task.get("vin"))` and adds `remoteOnly=True` only when `task.get("remoteOnly")` is truthy.
  - `TWCMaster.cancelStopCarsCharging(vin=None) -> int`, `TWCMaster.stopCarsCharging(vin=None)`, `TWCMaster.startCarsCharging(vin=None)`; all normalise `vin = vin or None`.

- [ ] **Step 1: Update the existing queue tests for the new dispatch signature and keying**

Edit `tests/unit/test_vehicle_command_queue.py`:

Replace the `RecordingModule.applyChargeLimit` method (currently `def applyChargeLimit(self, limit): return self._record("applyChargeLimit", limit)`) with:

```python
    def applyChargeLimit(self, limit, vin=None, remoteOnly=False):
        return self._record("applyChargeLimit", limit, vin, remoteOnly)
```

Rewrite every expected `("applyChargeLimit", N)` tuple to carry the two new fields, and give the two inline fakes a `vin` parameter:

```bash
sed -i 's/("applyChargeLimit", \([0-9]*\))/("applyChargeLimit", \1, None, False)/g' tests/unit/test_vehicle_command_queue.py
sed -i 's/def boom(limit):/def boom(limit, vin=None):/; s/def exit_now(limit):/def exit_now(limit, vin=None):/' tests/unit/test_vehicle_command_queue.py
```

Delete these two tests from `TestCoalescing` entirely (their behaviour moves to `TWCMaster` cancel rules in this task): `test_stop_replaces_pending_vehicleless_start` and `test_start_replaces_pending_stop`.

- [ ] **Step 2: Write the failing keying, cancel and dispatch tests**

Append to `tests/unit/test_vehicle_command_queue.py`:

```python
class TestKeying:
    def test_charge_keyed_per_vin(self, q, module):
        block_worker(q, module, {"cmd": "applyChargeLimit", "limit": 80})
        q.put({"cmd": "charge", "charge": True, "vin": "V1"})
        q.put({"cmd": "charge", "charge": True, "vin": "V2"})
        q.put({"cmd": "charge", "charge": False, "vin": "V1"})
        module.gate.set()
        wait_idle(q)
        # V1's start was replaced by V1's stop (same key); V2's start survives.
        assert module.calls == [
            ("applyChargeLimit", 80, None, False),
            ("charge", False, "V1"),
            ("charge", True, "V2"),
        ]

    def test_none_vin_is_distinct_from_named_vin(self, q, module):
        block_worker(q, module, {"cmd": "applyChargeLimit", "limit": 80})
        q.put({"cmd": "charge", "charge": True})
        q.put({"cmd": "charge", "charge": True, "vin": "V1"})
        module.gate.set()
        wait_idle(q)
        assert module.calls == [
            ("applyChargeLimit", 80, None, False),
            ("charge", True, None),
            ("charge", True, "V1"),
        ]

    def test_apply_charge_limit_per_vin_does_not_merge_with_policy_wide(
        self, q, module
    ):
        block_worker(q, module, {"cmd": "setChargeRate", "amps": 6, "vehicle": None})
        q.put({"cmd": "applyChargeLimit", "limit": 70})
        q.put({"cmd": "applyChargeLimit", "limit": 90, "vin": "V1"})
        q.put({"cmd": "applyChargeLimit", "limit": 80})
        module.gate.set()
        wait_idle(q)
        assert module.calls == [
            ("setChargeRate", 6, None),
            ("applyChargeLimit", 80, None, False),
            ("applyChargeLimit", 90, "V1", False),
        ]

    def test_apply_charge_limit_passes_vin_and_remote_only(self, q, module):
        q.put({"cmd": "applyChargeLimit", "limit": -1, "vin": "V1", "remoteOnly": True})
        wait_idle(q)
        assert module.calls == [("applyChargeLimit", -1, "V1", True)]


class TestCancel:
    def test_cancel_removes_matching_pending_entries(self, q, module):
        block_worker(q, module, {"cmd": "setChargeRate", "amps": 6, "vehicle": None})
        q.put({"cmd": "charge", "charge": False, "vin": "V1"})
        q.put({"cmd": "charge", "charge": False, "vin": "V2"})
        q.put({"cmd": "charge", "charge": True, "vin": "V3"})
        removed = q.cancel("charge", lambda task: not task.get("charge"))
        assert removed == 2
        module.gate.set()
        wait_idle(q)
        assert module.calls == [("setChargeRate", 6, None), ("charge", True, "V3")]

    def test_cancel_leaves_running_entry_alone(self, q, module):
        block_worker(q, module, {"cmd": "charge", "charge": False, "vin": "V1"})
        assert q.cancel("charge", lambda task: True) == 0
        module.gate.set()
        wait_idle(q)
        assert module.calls == [("charge", False, "V1")]

    def test_cancel_matches_command_name(self, q, module):
        block_worker(q, module, {"cmd": "applyChargeLimit", "limit": 80})
        q.put({"cmd": "setChargeRate", "amps": 10, "vehicle": None})
        assert q.cancel("charge", lambda task: True) == 0
        module.gate.set()
        wait_idle(q)
        assert module.calls == [
            ("applyChargeLimit", 80, None, False),
            ("setChargeRate", 10, None),
        ]
```

- [ ] **Step 3: Run the queue tests to verify the new ones fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_command_queue.py -q -p no:cacheprovider`
Expected: 7 failures (`TestKeying` x4, `TestCancel` x3). `test_charge_keyed_per_vin` fails because the stop replaced both starts; `test_cancel_*` fail with `AttributeError: 'VehicleCommandQueue' object has no attribute 'cancel'`; `test_apply_charge_limit_passes_vin_and_remote_only` fails because dispatch passes only `limit`.

- [ ] **Step 4: Implement keying, cancel and dispatch in the queue**

In `lib/TWCManager/VehicleCommandQueue.py`, replace the header comment lines 9-11 (`# Pending commands coalesce: ...` through `# Stop-charging commands run before anything else.`) with:

```python
# Pending commands coalesce per (cmd, vin): a later command for the same
# vehicle (or the same vehicle-less "all cars" target) replaces the pending
# one. Stop-charging commands run before anything else. cancel() lets the
# master drop pending entries that a newer decision has made moot.
```

Replace `_DISPATCH` (lines 22-31) with:

```python
    _DISPATCH = {
        "charge": lambda module, task: module.car_api_charge(task),
        "applyChargeLimit": lambda module, task: module.applyChargeLimit(
            **_applyChargeLimitKwargs(task)
        ),
        "setChargeRate": lambda module, task: module.setChargeRate(
            task["amps"], task.get("vehicle")
        ),
    }
```

Add this module-level function above `class VehicleCommandQueue:` (after the `logger = ...` line):

```python
def _applyChargeLimitKwargs(task):
    kwargs = {"limit": task["limit"], "vin": task.get("vin")}
    if task.get("remoteOnly"):
        # Pass remoteOnly only when set, so a plain apply is unchanged for
        # any module that still has the old signature.
        kwargs["remoteOnly"] = True
    return kwargs
```

Replace `_key` (lines 42-50) with:

```python
    @staticmethod
    def _key(task):
        cmd = task["cmd"]
        if cmd == "setChargeRate":
            vehicle = task.get("vehicle")
            return (cmd, getattr(vehicle, "VIN", vehicle))
        # None is a distinct target meaning "every vehicle".
        return (cmd, task.get("vin"))
```

Add `cancel` directly after `put`:

```python
    def cancel(self, cmd, match):
        # Drop pending (not running) entries for `cmd` whose task satisfies
        # `match`. Returns how many were removed. The running entry is left
        # alone: it may already be talking to the car.
        removed = 0
        with self._cond:
            for table in (self._high, self._low):
                doomed = [
                    key
                    for key, (task, _) in table.items()
                    if task["cmd"] == cmd and match(task)
                ]
                for key in doomed:
                    del table[key]
                    removed += 1
        if removed:
            logger.debug("Cancelled %d pending %s command(s)", removed, cmd)
        return removed
```

- [ ] **Step 5: Run the queue tests to verify they pass**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_command_queue.py -q -p no:cacheprovider`
Expected: `31 passed`.

- [ ] **Step 6: Write the failing TWCMaster cancel-rule tests**

Append to `tests/unit/test_twcmaster.py`:

```python
class TestChargeStartStopCancelRules:
    """startCarsCharging / stopCarsCharging / cancelStopCarsCharging keep the
    vehicle queue consistent: a stop cancels pending starts for that car, and
    cancelStopCarsCharging really removes pending stops (#667)."""

    @pytest.fixture
    def master(self):
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
        # Policy.clearOverride()/overrideLimit() are called; a Mock is enough.
        m.getModuleByName = Mock(return_value=Mock())
        m.settings["chargeStopMode"] = "1"
        # The queue is never started, so put() only records entries.
        return m

    @staticmethod
    def pending(master):
        q = master.vehicleCommandQueue
        return [task for task, _ in list(q._high.values()) + list(q._low.values())]

    def test_start_passes_vin_in_stop_mode_1(self, master):
        master.startCarsCharging("V1")
        assert self.pending(master) == [{"cmd": "charge", "charge": True, "vin": "V1"}]

    def test_stop_cancels_pending_start_for_that_vin_and_vehicleless(self, master):
        master.startCarsCharging("V1")
        master.startCarsCharging(None)
        master.startCarsCharging("V2")
        master.stopCarsCharging("V1")
        assert self.pending(master) == [
            {"cmd": "charge", "charge": False, "vin": "V1"},
            {"cmd": "charge", "charge": True, "vin": "V2"},
        ]

    def test_stop_for_all_cancels_every_pending_start(self, master):
        master.startCarsCharging("V1")
        master.startCarsCharging("V2")
        master.stopCarsCharging(None)
        assert self.pending(master) == [{"cmd": "charge", "charge": False, "vin": None}]

    def test_cancel_stop_for_vin_leaves_other_stops(self, master):
        master.stopCarsCharging("V1")
        master.stopCarsCharging("V2")
        assert master.cancelStopCarsCharging("V1") == 1
        assert self.pending(master) == [{"cmd": "charge", "charge": False, "vin": "V2"}]

    def test_cancel_stop_for_all(self, master):
        master.stopCarsCharging("V1")
        master.stopCarsCharging("V2")
        assert master.cancelStopCarsCharging() == 2
        assert self.pending(master) == []

    def test_empty_vin_is_treated_as_none(self, master):
        master.startCarsCharging("")
        assert self.pending(master) == [{"cmd": "charge", "charge": True, "vin": None}]
        master.stopCarsCharging("")
        assert self.pending(master) == [{"cmd": "charge", "charge": False, "vin": None}]
        assert master.cancelStopCarsCharging("") == 1
        assert self.pending(master) == []
```

- [ ] **Step 7: Run the TWCMaster tests to verify the new ones fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcmaster.py -q -p no:cacheprovider -k TestChargeStartStopCancelRules`
Expected: 6 failures. `test_start_passes_vin_in_stop_mode_1` fails because the task has no `vin`; `cancelStopCarsCharging` tests fail with `TypeError: cancelStopCarsCharging() takes 1 positional argument` or return `None`.

- [ ] **Step 8: Implement the TWCMaster cancel rules**

In `lib/TWCManager/TWCMaster.py`, replace `cancelStopCarsCharging` (lines 166-167) with:

```python
    def cancelStopCarsCharging(self, vin=None):
        # Drop pending stop-charging commands for this VIN (or every VIN when
        # vin is None). A vehicle-less stop applies to every car, so it is
        # cancelled too. Returns how many were removed. Closes #667 for the
        # vehicle queue path.
        vin = vin or None
        return self.vehicleCommandQueue.cancel(
            "charge",
            lambda task: not task.get("charge")
            and (vin is None or task.get("vin") in (vin, None)),
        )
```

Replace `startCarsCharging` and `stopCarsCharging` (lines 1860-1893) with:

```python
    def startCarsCharging(self, vin=None):
        # This function is the opposite functionality to the stopCarsCharging function
        # below
        vin = vin or None
        stopMode = int(self.settings.get("chargeStopMode", 1))
        if stopMode == 1:
            self.queue_background_task({"cmd": "charge", "charge": True, "vin": vin})
            self.getModuleByName("Policy").clearOverride()
        elif stopMode == 2:
            self.settings["respondToSlaves"] = 1
        elif stopMode == 3:
            self.queue_background_task({"cmd": "charge", "charge": True, "vin": vin})

    def stopCarsCharging(self, vin=None):
        # This is called by components (mainly TWCSlave) who want to signal to us to
        # call our configured routine for stopping vehicles from charging.
        # The default setting is to use the Tesla API. Some people may not want to do
        # this, as it only works for Tesla vehicles and requires logging in with your
        # Tesla credentials. The alternate option is to stop responding to slaves

        # 1 = Stop the car(s) charging via the Tesla API
        # 2 = Stop the car(s) charging by refusing to respond to slave TWCs
        # 3 = Send TWC Stop command to each slave
        vin = vin or None
        stopMode = int(self.settings.get("chargeStopMode", 1))
        if stopMode == 1:
            # A pending start for this car (or for every car) is now moot.
            self.vehicleCommandQueue.cancel(
                "charge",
                lambda task: bool(task.get("charge"))
                and (vin is None or task.get("vin") in (vin, None)),
            )
            self.queue_background_task({"cmd": "charge", "charge": False, "vin": vin})
            if self.stopTimeout == datetime.max:
                self.stopTimeout = datetime.now() + timedelta(seconds=10)
            elif datetime.now() > self.stopTimeout:
                self.getModuleByName("Policy").overrideLimit()
        if stopMode == 2:
            self.settings["respondToSlaves"] = 0
            self.settings["respondToSlavesExpiry"] = time.time() + 60
        if stopMode == 3:
            self.sendStopCommand()
```

- [ ] **Step 9: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `All done!` from black, then `511 passed, 1 warning`.

- [ ] **Step 10: Commit**

```bash
git add lib/TWCManager/VehicleCommandQueue.py lib/TWCManager/TWCMaster.py tests/unit/test_vehicle_command_queue.py tests/unit/test_twcmaster.py
git commit -m "$(cat <<'EOF'
Key vehicle commands by (cmd, vin) and add explicit cancellation

Every queued command now coalesces per vehicle, with None as the
distinct "all vehicles" target. The stop-replaces-start rule moves out
of the queue into TWCMaster, which cancels pending starts before
queuing a stop and really removes pending stops in
cancelStopCarsCharging (closes #667 for the queue path).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

