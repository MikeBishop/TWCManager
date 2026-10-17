# Vehicle Presence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track each vehicle's presence (home / away / unknown) by VIN as a client of the vehicle modules, re-apply the policy charge limit on arrival and restore the normal limit on departure through whichever channel can reach the car, without ever waking a sleeping car.

**Architecture:** A new `VehiclePresence` component (owned by `TWCMaster`, one daemon thread) records observations and nominations from any thread, probes due VINs through an ordered list of source adapters (telemetry, BLE `body-controller-state`, Fleet API online check + location), applies the decision rules under its lock, and runs arrival/departure handlers that only queue `applyChargeLimit` commands (now per-VIN and `remoteOnly`-aware) on the vehicle command queue. The vehicle modules lose their arrival/departure logic and become plain channels with `applyChargeLimit(limit, vin=None)` and `resetChargeLimitState(vin)`; normal limits move to VIN keys.

**Tech Stack:** Python 3.12, `threading` (Lock/Event/Condition), `tesla-control` subprocess over BLE, Tesla Fleet API via `requests`, pytest with `unittest.mock`, black 26.10.0.

**Spec:** `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/specs/2026-10-09-vehicle-presence-design.md` (read it fully before starting any task).

## Decisions made while planning

Each of these fills a gap or resolves a conflict in the spec. The choice follows the spec's goals (never wake, presence is the caller's decision, keep I/O off the main loop).

1. **`Policy.stop()` does not exist.** `lib/TWCManager/Policy/Policy.py` has no `stop()`/`start()` (grep confirmed). `master.vehiclePresence.stop()` is placed as the first statement of the shutdown block in `TWCManager.py`, immediately after `shutdownDeadline` is computed and before `saveSettings` is queued. Same intent (no new probes before draining).
2. **The normal-limit migration cannot run in `loadSettings`.** API vehicle IDs are only known after `TeslaAPI.car_api_available()` fetches the vehicle list, long after settings load. The migration runs in `TeslaAPI.addVehicle` through a new `TWCMaster.migrateNormalChargeLimit(oldKey, vin)`: when `chargeLimits[str(ID)]` exists it is moved to `chargeLimits[VIN]`; if the VIN key already exists the stale ID key is deleted instead (it can never be read again), and `saveSettings` is queued.
3. **`observeContact` gains a `probe=False` keyword.** The spec's Triggers section needs a probe flag the public interface lacks. `probePresence` reports `observeContact(vin, reachable, probe=True)` so the "reported from probes" test can exist, but the presence core counts failed probes only in its own probe pass (which gets the result directly from the source); `observeContact(vin, False, ...)` is ignored for every caller. This keeps each failed probe counted exactly once.
4. **`""` is normalised to `None` as a VIN.** `TWCSlave.currentVIN` defaults to `""` and is passed to `startCarsCharging`/`stopCarsCharging`/`cancelStopCarsCharging`. With `(cmd, vin)` keying, `""` would be a third distinct key. The three `TWCMaster` methods apply `vin = vin or None` before building the task or predicate.
5. **Cancel predicates include the vehicle-less entry.** `stopCarsCharging(vin)` cancels pending starts whose `vin` is this VIN or `None` (a vehicle-less start applies to every car, so #668's "stop replaces vehicle-less start" behaviour is kept, explicitly). `cancelStopCarsCharging(vin)` cancels pending stops whose `vin` is this VIN or `None`, matching the old single-task cancel; `vin=None` cancels every pending stop/start.
6. **The API source uses `update_vehicle_data()`, not `update_location()`.** `CarApiVehicle.update_location()` tries BLE and then `ble.wakeVehicle()` when the API hasn't been used for 2 minutes, which violates "never wake". The adapter sets `vehicle.statusDeferral = 0` (otherwise `update_vehicle_data` returns `True` without fetching) and calls `update_vehicle_data()` directly, which reads location and charge state in one call. The online check is a new `TeslaAPI.vehicleOnlineStates()` that GETs the vehicle list endpoint once and returns `{VIN: state}`.
7. **TeslaAPI's per-VIN apply skips two gates.** With `vin` given, `applyChargeLimit` ignores the 60 s `carApiLastChargeLimitApplyTime` throttle (the old `checkArrival`/`checkDeparture` flags did the same) and the `vehicle.atHome` filter (the caller has decided presence; the `remoteOnly` restore is sent precisely because the car is away). The policy-wide `vin=None` apply keeps both.
8. **When TWCManager is not holding a limit, the car's current limit is its normal.** In TeslaAPI's apply path, if there is no saved normal or `lastApplied == -1`, `outside` is taken from `vehicle.chargeLimit` before applying. This closes a stale-`outside` hole the old code had after a restore. TeslaBLE does not read the limit before applying and is unchanged.
9. **Departure adoption saves `(current, -1)`.** When the departure handler adopts a hand-set limit, it saves `saveNormalChargeLimit(vin, current, -1)`: nothing is being held any more. (Arrival adoption keeps `lastApplied`, as the spec says, because the apply that follows overwrites it anyway.) The departure handler also queues nothing when there is no saved normal or `lastApplied == -1`, because there is nothing to restore.
10. **A definite answer from any source resets the BLE failure count.** The spec says "a successful probe resets the count"; the count only matters when no source answers, so any definite answer resets it.
11. **`presenceSources` is read from `config.json` `vehicle.presenceSources`.** Like `commandPolicy`'s config override. Unknown names log a warning once at construction; known names whose module is not loaded are silently non-answers at probe time.
12. **`VehiclePriority.applyChargeLimit` and `resetChargeLimitState` are real methods.** The `__getattr__` proxy is refactored into `_dispatch(name, args, kwargs, skip=())`; `applyChargeLimit` strips `remoteOnly` (TeslaBLE/TeslaAPI don't accept it) and skips `TeslaBLE` when it is set; `resetChargeLimitState` fans out over `getModulesByType("Vehicle")`.
13. **TeslaAPI `applyChargeLimit` returns `"success"`/`"error"`.** It previously returned `None`, which `VehiclePriority` counted as failure. It now returns `"success"` when at least one targeted vehicle ends in the desired state (`stopTryingToApplyLimit` set), else `"error"`.
14. **TWCSlave trigger logic lives in `_checkPresenceTriggers(previousState)`.** `receive_slave_heartbeat` is too entangled with the master to unit-test end to end with a `Mock` master; the triggers are a small method called from the heartbeat before the significant-change monitor updates, and tested directly.
15. **TeslaAPI's `observeLocation` reporting lands in Task 6**, not Task 8, because the API source adapter and the report share `update_vehicle_data`. Task 8 covers the remaining wiring.
16. **A per-VIN apply never touches TeslaAPI's policy-wide state.** `TeslaAPI.lastChargeLimitApplied` and `carApiLastChargeLimitApplyTime` are only updated when `vin is None`. Otherwise a departure restore (`-1`) would become TeslaAPI's idea of the policy limit (`car_api_charge` re-applies `self.lastChargeLimitApplied` on every start) and an arrival apply would block the next policy-wide apply for 60 s.
17. **`stop()` also suppresses handlers of a pass already in progress.** The spec allows a running probe's handler to still queue commands; `runPass` checks the stop flag before each probe and each handler instead, which is stricter and avoids queueing anything during shutdown.
18. **The BLE probe has its own timeout.** `body-controller-state` took 4.2 s live; with the 5 s `commandTimeout` a slow answer would read as "unreachable" and two of those would be a false departure. `moduleConfiguration.TeslaBLE.presenceProbeTimeout` (default 15 s) applies to the probe only.
19. **`remoteOnly` keeps TeslaAPI's reads off BLE too.** `TeslaAPI.applyChargeLimit(limit, vin, remoteOnly=False)` passes `allowBle=not remoteOnly` to a new explicit `CarApiVehicle.update_charge(allowBle=True)` parameter; `allowBle=False` skips the BLE `get_charge_state` attempt and the `ble.wakeVehicle` fallback and goes straight to the API. VehiclePriority forwards `remoteOnly` to every module (TeslaBLE accepts and ignores it; HomeAssistant already takes `**kwargs`). No global toggle.
20. **The launcher's `checkArrival`/`checkDeparture` branches are removed in Task 3**, not Task 8, because Task 3 removes the flags they pass; leaving them until Task 8 would make the intermediate commits log a `TypeError` on every power event.

## Global Constraints

- Branch `fix/vehicle-presence`, stacked on `origin/ble-command-worker` (PR #668) at 3574692. Never commit anything under `.superpowers/`; never edit a tracked `.gitignore`.
- Tests: `$VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider` with `VENV=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv`. Baseline: `500 passed, 1 warning`. The warning is pre-existing.
- Formatting: `$VENV/bin/black --exclude="setup.py|tests/*" --check .` must pass before every commit (CI runs it). Run `$VENV/bin/black lib/` to fix.
- Run every command from `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`.
- Observers (`nominate`, `observeContact`, `observeLocation`) do no I/O and take only the presence lock. They are called from under `TeslaBLE._bleLock` and from the MQTT thread, so they must never call back into a vehicle module.
- The presence thread never holds the presence lock while running a source or a handler.
- Presence never runs `wake`, `state` (without a preceding awake probe) or `ping` over BLE, and never calls `wake_up` over the API.
- Concurrency tests use `threading.Event` / gates for positive assertions, never `time.sleep`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Expected test counts are cumulative: 500 → 511 → 516 → 539 → 552 → 582 → 605 → 625 → 640.

---

## File Structure

| File | Action | Responsibility |
| --- | --- | --- |
| `lib/TWCManager/VehicleCommandQueue.py` | Modify | `(cmd, vin)` keying for every command; `cancel(cmd, match)`; `applyChargeLimit` dispatch passes `vin` and `remoteOnly`. |
| `lib/TWCManager/TWCMaster.py` | Modify | `start/stop/cancelStopCarsCharging` cancel rules; `migrateNormalChargeLimit`; owns `vehiclePresence`; `recordVehicleVIN` nominates. |
| `lib/TWCManager/VehiclePresence.py` | Create | Presence core: per-VIN state, scheduling, rate limit, decision rules, thread, handler dispatch. Sources/handlers injected. |
| `lib/TWCManager/PresenceSources.py` | Create | Source adapters (`telemetry`, `ble`, `api`) and `buildSources(master)`. |
| `lib/TWCManager/PresenceHandlers.py` | Create | Arrival/departure handlers and `hasRemoteChannel(master)`. |
| `lib/TWCManager/Vehicle/VehiclePriority.py` | Modify | `_dispatch` refactor; `applyChargeLimit(limit, vin, remoteOnly)`; `resetChargeLimitState` fan-out. |
| `lib/TWCManager/Vehicle/TeslaBLE.py` | Modify | `applyChargeLimit(limit, vin=None)`; `resetChargeLimitState`; `probePresence`; contact reporting. |
| `lib/TWCManager/Vehicle/TeslaAPI.py` | Modify | `applyChargeLimit(limit, vin=None)` without departure logic; VIN-keyed limits; migration call; `resetChargeLimitState`; `vehicleOnlineStates`; location reporting. |
| `lib/TWCManager/Vehicle/HomeAssistant.py` | Modify | `vin` parameter; `resetChargeLimitState` no-op. |
| `lib/TWCManager/Vehicle/Telemetry.py` | Modify | `observeLocation` after a lat/lon update. |
| `lib/TWCManager/TWCSlave.py` | Modify | Presence triggers; `cancelStopCarsCharging(self.currentVIN)`; no `checkArrival`/`checkDeparture` tasks. |
| `lib/TWCManager/TWCManager.py` | Modify | Remove `checkArrival`/`checkDeparture` branches; start/stop presence. |
| `lib/TWCManager/Control/HTTPControl.py` | Modify | `/api/checkArrival`, `/api/checkDeparture` nominate. |
| `etc/twcmanager/config.json` | Modify | Document `presenceSources`. |
| `tests/unit/test_vehicle_command_queue.py` | Modify | Keying, cancel, dispatch. |
| `tests/unit/test_twcmaster.py` | Modify | Cancel rules, migration, presence ownership, `recordVehicleVIN`. |
| `tests/unit/test_vehicle_priority.py` | Modify | Fan-out and `remoteOnly`. |
| `tests/unit/test_teslable_presence.py` | Create | TeslaBLE per-VIN apply, reset, probe, contact reporting. |
| `tests/unit/test_teslaapi_presence.py` | Create | TeslaAPI apply rewrite, migration, online states, location reporting. |
| `tests/unit/test_homeassistant_presence.py` | Create | HomeAssistant `resetChargeLimitState`. |
| `tests/unit/test_vehicle_presence.py` | Create | Presence core. |
| `tests/unit/test_presence_sources.py` | Create | Source adapters. |
| `tests/unit/test_presence_handlers.py` | Create | Handlers. |
| `tests/unit/test_twcslave.py` | Modify | Triggers. |
| `tests/unit/test_telemetry_timers.py` | Modify | Location observation. |
| `tests/unit/test_httpcontrol.py` | Modify | Endpoints nominate. |
| `tests/unit/test_twcmanager.py` | Modify | Launcher source checks. |

---

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

### Task 2: VIN-keyed normal limits and the one-time migration

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py` (add `migrateNormalChargeLimit` after `getNormalChargeLimit`, line 933)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:113-115` (`addVehicle`), `:889-1055` (`applyChargeLimit` keys)
- Test: `tests/unit/test_twcmaster.py`, `tests/unit/test_teslaapi_presence.py` (create)

**Interfaces:**
- Consumes: `TWCMaster.getNormalChargeLimit(ID)`, `saveNormalChargeLimit(ID, outside, lastApplied)`, `removeNormalChargeLimit(ID)` (unchanged; keys are `str(ID)`).
- Produces:
  - `TWCMaster.migrateNormalChargeLimit(oldKey, vin) -> bool`: moves `settings["chargeLimits"][str(oldKey)]` to `[str(vin)]` (deleting the old key if the VIN key already exists); queues `saveSettings`; returns `True` when anything changed.
  - `TeslaAPI.addVehicle(json)` calls `master.migrateNormalChargeLimit(vehicle.ID, vehicle.VIN)`.
  - Every `get/save/removeNormalChargeLimit` call in `TeslaAPI.applyChargeLimit` uses `vehicle.VIN`.

- [ ] **Step 1: Write the failing migration tests**

Append to `tests/unit/test_twcmaster.py`:

```python
class TestNormalChargeLimitMigration:
    """chargeLimits used to be keyed by Tesla API vehicle ID; they are now
    keyed by VIN. Old keys are moved once, when the API vehicle list arrives."""

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
        m.queue_background_task = Mock()
        return m

    def test_moves_id_key_to_vin(self, master):
        master.settings["chargeLimits"] = {"12345": [80, 50]}
        assert master.migrateNormalChargeLimit(12345, "VIN1") is True
        assert master.settings["chargeLimits"] == {"VIN1": [80, 50]}
        master.queue_background_task.assert_called_once_with({"cmd": "saveSettings"})

    def test_existing_vin_key_wins_and_stale_id_key_is_dropped(self, master):
        master.settings["chargeLimits"] = {"12345": [80, 50], "VIN1": [90, 60]}
        assert master.migrateNormalChargeLimit(12345, "VIN1") is True
        assert master.settings["chargeLimits"] == {"VIN1": [90, 60]}

    def test_noop_without_id_key(self, master):
        master.settings["chargeLimits"] = {"VIN1": [90, 60]}
        assert master.migrateNormalChargeLimit(12345, "VIN1") is False
        assert master.settings["chargeLimits"] == {"VIN1": [90, 60]}
        master.queue_background_task.assert_not_called()
        # No chargeLimits at all is also fine.
        del master.settings["chargeLimits"]
        assert master.migrateNormalChargeLimit(12345, "VIN1") is False
```

Create `tests/unit/test_teslaapi_presence.py`:

```python
"""
TeslaAPI as a presence channel: VIN-keyed normal limits, per-VIN apply
without arrival/departure logic, online check and location reporting.
"""

import inspect
import time
from unittest.mock import Mock, patch

import pytest

from TWCManager.Vehicle.TeslaAPI import TeslaAPI

VIN1 = "5YJ3E1EA1KF000001"
VIN2 = "5YJ3E1EA1KF000002"


def make_master():
    master = Mock()
    master.config = {"config": {}, "vehicle": {"teslaAPI": {"enabled": True}}}
    master.tokenSyncEnabled.return_value = False
    master.getNormalChargeLimit = Mock(return_value=(False, None, None))
    return master


def make_api():
    api = TeslaAPI(make_master())
    # These are class-level in TeslaAPI; isolate them per test.
    api.carApiVehicles = []
    api.carApiBearerToken = "token"
    api.carApiLastChargeLimitApplyTime = 0
    api.lastChargeLimitApplied = 0
    api.car_api_available = Mock(return_value=True)
    return api


class TestMigrationOnAddVehicle:
    def test_add_vehicle_migrates_limit_key(self):
        api = make_api()
        api.addVehicle({"id": 12345, "vin": VIN1, "display_name": "Car"})
        api.master.migrateNormalChargeLimit.assert_called_once_with(12345, VIN1)
        assert [v.VIN for v in api.carApiVehicles] == [VIN1]

    def test_apply_charge_limit_uses_vin_keys(self):
        source = inspect.getsource(TeslaAPI.applyChargeLimit)
        assert "vehicle.ID" not in source
        assert "vehicle.VIN" in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcmaster.py tests/unit/test_teslaapi_presence.py -q -p no:cacheprovider -k "Migration or uses_vin_keys"`
Expected: 5 failures (`AttributeError: 'TWCMaster' object has no attribute 'migrateNormalChargeLimit'`; `migrateNormalChargeLimit` not called by `addVehicle`; `"vehicle.ID"` still in source).

- [ ] **Step 3: Implement the migration and switch TeslaAPI to VIN keys**

Switch every normal-limit key inside `applyChargeLimit` (lines 889-1055: the `getNormalChargeLimit(vehicle.ID)` calls at 924-926 and 972-974, `removeNormalChargeLimit(vehicle.ID)` at 1022, `saveNormalChargeLimit(vehicle.ID, ...)` at 1024 and 1041) from `vehicle.ID` to `vehicle.VIN`:

```bash
sed -i '889,1055s/vehicle\.ID/vehicle.VIN/g' lib/TWCManager/Vehicle/TeslaAPI.py
grep -n "vehicle\.ID" lib/TWCManager/Vehicle/TeslaAPI.py
```

The `grep` must print only the `getVehicleByID` comparison (`if vehicle.ID == vehicleID:`); nothing inside `applyChargeLimit`. Do this **before** the `addVehicle` edit below, which shifts the file by two lines.

In `lib/TWCManager/TWCMaster.py`, add after `getNormalChargeLimit` (after line 933):

```python
    def migrateNormalChargeLimit(self, oldKey, vin):
        # chargeLimits were once keyed by Tesla API vehicle ID; they are now
        # keyed by VIN. Called when the API vehicle list is loaded, which is
        # the first moment both keys are known. Returns True if anything moved.
        limits = self.settings.get("chargeLimits")
        oldKey, vin = str(oldKey), str(vin)
        if not limits or oldKey not in limits or oldKey == vin:
            return False
        if vin in limits:
            # The VIN entry is newer; the ID entry can never be read again.
            del limits[oldKey]
        else:
            limits[vin] = limits.pop(oldKey)
        logger.info("Migrated normal charge limit for vehicle %s to its VIN", vin)
        self.queue_background_task({"cmd": "saveSettings"})
        return True
```

In `lib/TWCManager/Vehicle/TeslaAPI.py`, replace `addVehicle` (lines 113-115) with:

```python
    def addVehicle(self, json):
        if "vin" in json:
            vehicle = CarApiVehicle(json, self, self.config)
            self.carApiVehicles.append(vehicle)
            # Normal charge limits are keyed by VIN; move any old ID-keyed entry.
            self.master.migrateNormalChargeLimit(vehicle.ID, vehicle.VIN)
```


- [ ] **Step 4: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `516 passed, 1 warning`.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/TWCMaster.py lib/TWCManager/Vehicle/TeslaAPI.py tests/unit/test_twcmaster.py tests/unit/test_teslaapi_presence.py
git commit -m "$(cat <<'EOF'
Key normal charge limits by VIN

TeslaAPI saved them under the API vehicle ID while TeslaBLE used the
VIN, so the two modules could not see each other's saved limits. Old
ID-keyed entries are moved to the VIN once, when the API vehicle list
arrives.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

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

### Task 5: VehiclePresence core (state, rules, scheduling, thread)

**Files:**
- Create: `lib/TWCManager/VehiclePresence.py`
- Modify: `lib/TWCManager/TWCMaster.py:18` (import), `:106-108` (construct after the vehicle queue)
- Test: `tests/unit/test_vehicle_presence.py` (create), `tests/unit/test_twcmaster.py`

**Interfaces:**
- Consumes: `master.config["vehicle"]["presenceSources"]` (optional), `master.settings["Vehicles"]`, `master.getModuleByName("TeslaAPI").getCarApiVehicles()`.
- Produces (`lib/TWCManager/VehiclePresence.py`):
  - constants `HOME = "home"`, `AWAY = "away"`, `UNKNOWN = "unknown"`, `DEFAULT_SOURCE_ORDER = ["telemetry", "ble", "api"]`.
  - `VehiclePresence(master, sources=None, onArrival=None, onDeparture=None, knownVehicles=None, sourceOrder=None, clock=time.monotonic)`.
    - `sources`: `{name: callable(vin) -> None | {"atHome": bool|None, "limit": int|None}}`. `None` = source does not apply; `atHome=None` = no answer. Default `{}` (Task 6 changes it to `buildSources(master)`).
    - `onArrival(vin, currentLimit)`, `onDeparture(vin, currentLimit)`: default `None` (Task 7 supplies defaults).
    - `knownVehicles() -> list[str]`: default = union of `settings["Vehicles"]` and API VINs.
  - `start()`, `stop()`, `state(vin)`, `nominate(vin, reason, delays=(0,))`, `observeContact(vin, reachable, probe=False)`, `observeLocation(vin, atHome)`, and `runPass()` (one synchronous pass; tests drive it directly).
  - Class attributes `PROBE_INTERVAL = 60`, `AWAY_AFTER_FAILED_PROBES = 2`.
  - `TWCMaster.vehiclePresence` is constructed in `__init__` with no thread started.

- [ ] **Step 1: Write the failing core tests**

Create `tests/unit/test_vehicle_presence.py`:

```python
"""
VehiclePresence core: decision rules, source fallback, scheduling, rate
limit, and the thread. Sources and handlers are injected callables; a fake
clock drives due times, so nothing here sleeps.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from TWCManager.VehiclePresence import AWAY, HOME, UNKNOWN, VehiclePresence

WAIT = 2.0
V1 = "5YJ3E1EA1KF000001"
V2 = "5YJ3E1EA1KF000002"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Recorder:
    def __init__(self):
        self.arrivals = []
        self.departures = []

    def onArrival(self, vin, limit):
        self.arrivals.append((vin, limit))

    def onDeparture(self, vin, limit):
        self.departures.append((vin, limit))


def answer(atHome, limit=None):
    """A source that always gives this answer. atHome="n/a" means the source
    does not apply (returns None); None means "no answer"."""
    calls = []

    def source(vin):
        calls.append(vin)
        if atHome == "n/a":
            return None
        return {"atHome": atHome, "limit": limit}

    source.calls = calls
    return source


def make(sources, order=None, known=(V1, V2), clock=None, master=None):
    rec = Recorder()
    clock = clock or FakeClock()
    presence = VehiclePresence(
        master or Mock(),
        sources=sources,
        onArrival=rec.onArrival,
        onDeparture=rec.onDeparture,
        knownVehicles=lambda: list(known),
        sourceOrder=list(sources) if order is None else order,
        clock=clock,
    )
    return presence, rec, clock


def probe(presence, clock, vin=V1):
    """Nominate vin, step the clock past the rate limit, and run one pass."""
    clock.now += VehiclePresence.PROBE_INTERVAL + 1
    presence.nominate(vin, "test")
    presence.runPass()


class TestDecisionRules:
    def test_every_vin_starts_unknown(self):
        presence, rec, clock = make({})
        assert presence.state(V1) == UNKNOWN

    def test_unknown_to_home_runs_arrival(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]
        assert rec.departures == []

    def test_unknown_to_away_runs_nothing(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, False)
        presence.runPass()
        assert presence.state(V1) == AWAY
        assert rec.arrivals == [] and rec.departures == []

    def test_home_to_away_runs_departure(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        presence.observeLocation(V1, False)
        presence.runPass()
        assert presence.state(V1) == AWAY
        assert rec.departures == [(V1, None)]

    def test_contact_success_sets_home(self):
        presence, rec, clock = make({})
        presence.observeContact(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]

    def test_contact_failure_is_ignored_probe_or_not(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.runPass()
        presence.observeContact(V1, False)
        presence.observeContact(V1, False, probe=True)
        presence.observeContact(V1, False, probe=True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.departures == []

    def test_contact_success_counts_even_when_location_said_away(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, False)
        presence.runPass()
        presence.observeContact(V1, True)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, None)]

    def test_ble_probe_success_sets_home_with_limit(self):
        presence, rec, clock = make({"ble": answer(True, limit=80)})
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert rec.arrivals == [(V1, 80)]

    def test_two_consecutive_failed_ble_probes_make_away(self):
        presence, rec, clock = make({"ble": answer(None)})
        presence.observeLocation(V1, True)
        presence.runPass()
        probe(presence, clock)
        assert presence.state(V1) == HOME
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert rec.departures == [(V1, None)]

    def test_successful_probe_resets_the_failure_count(self):
        answers = iter([None, True, None, None])
        source = lambda vin: {"atHome": next(answers), "limit": None}
        presence, rec, clock = make({"ble": source})
        probe(presence, clock)  # fail 1
        probe(presence, clock)  # success: count back to 0
        probe(presence, clock)  # fail 1
        assert presence.state(V1) == HOME
        probe(presence, clock)  # fail 2
        assert presence.state(V1) == AWAY

    def test_ble_failures_do_not_count_when_telemetry_is_live(self):
        presence, rec, clock = make(
            {"telemetry": answer(None), "ble": answer(None)},
            order=["telemetry", "ble"],
        )
        presence.observeLocation(V1, True)
        presence.runPass()
        for _ in range(3):
            probe(presence, clock)
        assert presence.state(V1) == HOME

    def test_ble_failures_do_not_count_when_a_later_source_answers(self):
        presence, rec, clock = make(
            {"ble": answer(None), "api": answer(True)}, order=["ble", "api"]
        )
        probe(presence, clock)
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert presence._failedProbes[V1] == 0


class TestSourceFallback:
    def test_first_definite_answer_wins(self):
        telemetry, ble = answer(False), answer(True)
        presence, rec, clock = make(
            {"telemetry": telemetry, "ble": ble}, order=["telemetry", "ble"]
        )
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert ble.calls == []

    def test_inapplicable_source_is_skipped(self):
        telemetry, ble = answer("n/a"), answer(True)
        presence, rec, clock = make(
            {"telemetry": telemetry, "ble": ble}, order=["telemetry", "ble"]
        )
        probe(presence, clock)
        assert presence.state(V1) == HOME
        assert telemetry.calls == [V1]

    def test_order_follows_the_setting_and_skips_removed_entries(self):
        presence, rec, clock = make(
            {"telemetry": answer(True), "ble": answer(True), "api": answer(False)},
            order=["api"],
        )
        probe(presence, clock)
        assert presence.state(V1) == AWAY
        assert presence._order == ["api"]

    def test_unknown_source_name_is_ignored_with_a_warning(self):
        with patch("TWCManager.VehiclePresence.logger") as log:
            presence, rec, clock = make({"ble": answer(True)}, order=["bogus", "ble"])
        assert presence._order == ["ble"]
        log.warning.assert_called_once()

    def test_order_is_read_from_master_config(self):
        master = Mock()
        master.config = {"vehicle": {"presenceSources": ["api", "ble"]}}
        presence = VehiclePresence(
            master,
            sources={"telemetry": answer(True), "ble": answer(True), "api": answer(True)},
            knownVehicles=lambda: [],
        )
        assert presence._order == ["api", "ble"]

    def test_source_exception_counts_as_no_answer(self):
        def boom(vin):
            raise RuntimeError("adapter on fire")

        presence, rec, clock = make({"ble": boom, "api": answer(True)}, order=["ble", "api"])
        probe(presence, clock)
        assert presence.state(V1) == HOME

    def test_limit_comes_from_the_first_source_that_reports_one(self):
        presence, rec, clock = make(
            {
                "telemetry": lambda vin: {"atHome": None, "limit": 90},
                "api": answer(True, limit=70),
            },
            order=["telemetry", "api"],
        )
        probe(presence, clock)
        assert rec.arrivals == [(V1, 90)]


class TestScheduling:
    def test_nominate_none_expands_to_known_vins_when_due(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source}, known=(V1, V2))
        presence.nominate(None, "api")
        presence.runPass()
        assert source.calls == [V1, V2]
        assert [v for v, _ in rec.arrivals] == [V1, V2]

    def test_due_time_batching(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "unplug", delays=(100,))
        presence.nominate(V2, "power-start", delays=(0,))
        presence.runPass()
        assert source.calls == [V2]
        clock.now += 99
        presence.runPass()
        assert source.calls == [V2]
        clock.now += 1
        presence.runPass()
        assert source.calls == [V2, V1]

    def test_rate_limit_one_probe_per_vin_per_60s(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "a")
        presence.runPass()
        clock.now += 30
        presence.nominate(V1, "b")
        presence.runPass()
        assert source.calls == [V1]
        clock.now += 31
        presence.nominate(V1, "c")
        presence.runPass()
        assert source.calls == [V1, V1]

    def test_events_only_affect_the_vin_concerned(self):
        presence, rec, clock = make({})
        presence.observeLocation(V1, True)
        presence.observeLocation(V2, False)
        presence.runPass()
        assert presence.state(V1) == HOME
        assert presence.state(V2) == AWAY
        assert rec.arrivals == [(V1, None)]
        presence.observeLocation(V2, True)
        presence.runPass()
        assert rec.arrivals == [(V1, None), (V2, None)]
        assert presence.state(V1) == HOME

    def test_observers_record_only(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source})
        presence.nominate(V1, "a")
        presence.observeLocation(V2, True)
        presence.observeContact(V2, True)
        assert source.calls == []
        assert rec.arrivals == []
        assert presence.state(V2) == UNKNOWN

    def test_handlers_run_without_the_presence_lock(self):
        seen = []
        presence = VehiclePresence(
            Mock(),
            sources={},
            onArrival=lambda vin, limit: seen.append(presence._lock.locked()),
            knownVehicles=lambda: [],
            sourceOrder=[],
            clock=FakeClock(),
        )
        presence.observeLocation(V1, True)
        presence.runPass()
        assert seen == [False]


class TestThread:
    def test_start_is_idempotent(self):
        presence, rec, clock = make({}, clock=time.monotonic)
        presence.start()
        thread = presence._thread
        presence.start()
        assert presence._thread is thread
        assert thread.daemon and thread.name == "VehiclePresence"
        presence.stop()
        thread.join(WAIT)
        assert not thread.is_alive()

    def test_thread_runs_a_pass_when_nominated(self):
        arrived = threading.Event()
        presence = VehiclePresence(
            Mock(),
            sources={"ble": answer(True)},
            onArrival=lambda vin, limit: arrived.set(),
            knownVehicles=lambda: [],
            sourceOrder=["ble"],
        )
        presence.start()
        presence.nominate(V1, "power-start")
        assert arrived.wait(WAIT)
        assert presence.state(V1) == HOME
        presence.stop()
        presence._thread.join(WAIT)

    def test_stop_prevents_new_passes(self):
        source = answer(True)
        presence, rec, clock = make({"ble": source}, clock=time.monotonic)
        presence.start()
        presence.stop()
        presence._thread.join(WAIT)
        assert not presence._thread.is_alive()
        presence.nominate(V1, "late")
        assert source.calls == []
        assert presence.state(V1) == UNKNOWN

    def test_thread_survives_an_exception_in_a_pass(self):
        raised = threading.Event()
        arrived = threading.Event()

        def known():
            raised.set()
            raise RuntimeError("settings on fire")

        presence = VehiclePresence(
            Mock(),
            sources={"ble": answer(True)},
            onArrival=lambda vin, limit: arrived.set(),
            knownVehicles=known,
            sourceOrder=["ble"],
        )
        presence.start()
        presence.nominate(None, "api")
        assert raised.wait(WAIT)
        presence.nominate(V1, "power-start")
        assert arrived.wait(WAIT)
        presence.stop()
        presence._thread.join(WAIT)
```

Append to `tests/unit/test_twcmaster.py`, inside `class TestVehicleCommandRouting` (after `test_master_creates_unstarted_queue`):

```python
    def test_master_creates_unstarted_presence(self):
        from TWCManager.TWCMaster import TWCMaster
        from TWCManager.VehiclePresence import VehiclePresence

        m = TWCMaster(
            "AB",
            {
                "config": {
                    "wiringMaxAmpsAllTWCs": 80,
                    "maxAmpsAllowedFromGrid": None,
                }
            },
        )
        assert isinstance(m.vehiclePresence, VehiclePresence)
        assert m.vehiclePresence.master is m
        assert m.vehiclePresence._thread is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py -q -p no:cacheprovider -k "presence or Presence"`
Expected: collection error `ModuleNotFoundError: No module named 'TWCManager.VehiclePresence'`.

- [ ] **Step 3: Implement the core**

Create `lib/TWCManager/VehiclePresence.py`:

```python
# Tracks where each vehicle is (home / away / unknown), keyed by VIN.
#
# VehiclePresence is a client of the vehicle modules rather than part of any
# one of them. Observers (nominate, observeContact, observeLocation) may be
# called from any thread: they only record under the presence lock and set
# the wake event. One daemon thread does all the I/O: it probes due VINs
# through the configured sources, applies the decision rules, and runs the
# arrival/departure handlers, which only queue vehicle commands.
#
# Sources are callables vin -> None (source does not apply to this VIN) or
# {"atHome": True | False | None, "limit": int | None}, where atHome None
# means "no answer". Handlers are callables (vin, currentLimit).
import threading
import time
import traceback

from TWCManager.Logging.LoggerFactory import LoggerFactory

logger = LoggerFactory.get_logger("VehiclePresence", "Vehicle")

HOME = "home"
AWAY = "away"
UNKNOWN = "unknown"

DEFAULT_SOURCE_ORDER = ["telemetry", "ble", "api"]


class VehiclePresence:
    # No VIN is probed more often than this; a due time inside the window is
    # satisfied by the recent result.
    PROBE_INTERVAL = 60
    # BLE-only away rule: consecutive failed probes with no other answer.
    AWAY_AFTER_FAILED_PROBES = 2

    def __init__(
        self,
        master,
        sources=None,
        onArrival=None,
        onDeparture=None,
        knownVehicles=None,
        sourceOrder=None,
        clock=time.monotonic,
    ):
        self.master = master
        self._sources = {} if sources is None else dict(sources)
        self._onArrival = onArrival
        self._onDeparture = onDeparture
        self._knownVehicles = knownVehicles or self._defaultKnownVehicles
        self._clock = clock
        self._order = self._resolveOrder(sourceOrder)

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self._stopped = False
        self._state = {}  # vin -> HOME | AWAY | UNKNOWN
        self._failedProbes = {}  # vin -> consecutive BLE-only probe failures
        self._lastProbe = {}  # vin -> clock time of the last probe
        self._due = {}  # vin (None = all known) -> set of due clock times
        self._observations = []  # (kind, vin, value) awaiting the thread

    def _resolveOrder(self, sourceOrder):
        if sourceOrder is None:
            config = getattr(self.master, "config", None)
            vehicle = config.get("vehicle") if isinstance(config, dict) else None
            sourceOrder = (vehicle or {}).get("presenceSources", DEFAULT_SOURCE_ORDER)
        order = []
        for name in sourceOrder:
            if name not in DEFAULT_SOURCE_ORDER:
                logger.warning(
                    "Ignoring unknown presence source %r in vehicle.presenceSources",
                    name,
                )
            elif name in self._sources:
                order.append(name)
        return order

    def _defaultKnownVehicles(self):
        # Union of the VINs in settings["Vehicles"] and the API vehicle list.
        vins = []
        settings = getattr(self.master, "settings", None)
        if isinstance(settings, dict):
            vins.extend((settings.get("Vehicles") or {}).keys())
        api = self.master.getModuleByName("TeslaAPI")
        if api:
            try:
                for vehicle in api.getCarApiVehicles():
                    if vehicle.VIN and vehicle.VIN not in vins:
                        vins.append(vehicle.VIN)
            except Exception as e:
                logger.debug("Could not list API vehicles: %s", e)
        return vins

    # -- public interface: observers record only, no I/O -------------------

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped = False
            self._thread = threading.Thread(
                target=self._run, name="VehiclePresence", daemon=True
            )
            thread = self._thread
        thread.start()

    def stop(self):
        # No new probes or handler commands after this. A pass already in
        # progress finishes. Returns immediately.
        with self._lock:
            self._stopped = True
        self._wake.set()

    def state(self, vin):
        with self._lock:
            return self._state.get(vin, UNKNOWN)

    def nominate(self, vin, reason, delays=(0,)):
        # Schedule a presence check for vin (None = every known vehicle) at
        # now + d for each d in delays.
        now = self._clock()
        with self._lock:
            self._due.setdefault(vin, set()).update(now + d for d in delays)
        logger.debug(
            "Presence check for %s nominated (%s) at +%s s",
            vin or "all vehicles",
            reason,
            ",".join(str(d) for d in delays),
        )
        self._wake.set()

    def observeContact(self, vin, reachable, probe=False):
        # A car that answered over BLE is home. A failed contact proves
        # nothing by itself (a command can fail for other reasons), and failed
        # probes are counted by the probe pass, which sees the result
        # directly; so only success is recorded here.
        if not reachable:
            return
        with self._lock:
            self._observations.append(("contact", vin, True))
        self._wake.set()

    def observeLocation(self, vin, atHome):
        # A location fix from telemetry or the API.
        with self._lock:
            self._observations.append(("location", vin, bool(atHome)))
        self._wake.set()

    # -- the thread --------------------------------------------------------

    def _run(self):
        try:
            while True:
                with self._lock:
                    if self._stopped:
                        return
                    timeout = self._timeUntilNextDue()
                self._wake.wait(timeout)
                self._wake.clear()
                with self._lock:
                    if self._stopped:
                        return
                try:
                    self.runPass()
                except Exception:
                    logger.error(
                        "VehiclePresence pass failed: %s", traceback.format_exc()
                    )
        except BaseException:
            logger.error(
                "VehiclePresence thread %s exiting: %s",
                threading.current_thread().name,
                traceback.format_exc(),
            )
            raise

    def _timeUntilNextDue(self):
        # Caller holds the lock. None means nothing is scheduled: wait for
        # an event.
        times = [t for due in self._due.values() for t in due]
        if not times:
            return None
        return max(0.0, min(times) - self._clock())

    def runPass(self):
        # One pass: apply recorded observations, probe due VINs, then run the
        # handlers for the VINs whose state changed. Public so tests can
        # drive it synchronously; the thread calls it on every wake.
        now = self._clock()
        with self._lock:
            observations, self._observations = self._observations, []
            dueVins = self._collectDue(now)

        transitions = []
        for kind, vin, value in observations:
            with self._lock:
                if kind == "contact":
                    transition = self._applyHome(vin)
                else:
                    transition = self._applyLocation(vin, value)
            if transition:
                transitions.append(transition)

        for vin in dueVins:
            with self._lock:
                if self._stopped:
                    break
                last = self._lastProbe.get(vin)
                if last is not None and now - last < self.PROBE_INTERVAL:
                    logger.debug(
                        "Presence probe for %s skipped: probed %.0f s ago",
                        vin,
                        now - last,
                    )
                    continue
                self._lastProbe[vin] = now
            outcome = self._probe(vin)  # I/O; the lock is not held
            with self._lock:
                transition = self._applyProbe(vin, outcome)
            if transition:
                transitions.append(transition)

        for vin, old, new, limit in transitions:
            with self._lock:
                stopped = self._stopped
            if stopped:
                return
            self._runHandler(vin, old, new, limit)

    def _collectDue(self, now):
        # Caller holds the lock. Pops every due time <= now and returns the
        # VINs to probe, in nomination order, without duplicates. None
        # expands to the known vehicles as of now.
        vins = []
        for key in list(self._due):
            ready = {t for t in self._due[key] if t <= now}
            if not ready:
                continue
            self._due[key] -= ready
            if not self._due[key]:
                del self._due[key]
            if key is None:
                vins.extend(self._knownVehicles())
            else:
                vins.append(key)
        return list(dict.fromkeys(vins))

    def _probe(self, vin):
        # Try the sources in order; the first definite answer decides.
        outcome = {
            "atHome": None,
            "limit": None,
            "bleFailed": False,
            "telemetryLive": False,
        }
        for name in self._order:
            try:
                result = self._sources[name](vin)
            except Exception as e:
                logger.debug("Presence source %s failed for %s: %s", name, vin, e)
                result = None
            if result is None:
                continue  # the source does not apply to this VIN
            if name == "telemetry":
                outcome["telemetryLive"] = True
            if outcome["limit"] is None and result.get("limit") is not None:
                outcome["limit"] = result["limit"]
            atHome = result.get("atHome")
            if atHome is None:
                if name == "ble":
                    outcome["bleFailed"] = True
                continue
            outcome["atHome"] = bool(atHome)
            logger.debug(
                "Presence source %s says %s is %s",
                name,
                vin,
                "home" if atHome else "away",
            )
            break
        return outcome

    # -- decision rules; callers hold the lock -----------------------------

    def _applyProbe(self, vin, outcome):
        if outcome["atHome"] is not None:
            self._failedProbes[vin] = 0
            return self._setState(
                vin, HOME if outcome["atHome"] else AWAY, outcome["limit"]
            )
        if outcome["bleFailed"] and not outcome["telemetryLive"]:
            # BLE-only away rule: nothing else can see the car, and BLE
            # couldn't reach it twice in a row.
            self._failedProbes[vin] = self._failedProbes.get(vin, 0) + 1
            if self._failedProbes[vin] >= self.AWAY_AFTER_FAILED_PROBES:
                return self._setState(vin, AWAY, outcome["limit"])
        return None

    def _applyHome(self, vin):
        self._failedProbes[vin] = 0
        return self._setState(vin, HOME, None)

    def _applyLocation(self, vin, atHome):
        return self._setState(vin, HOME if atHome else AWAY, None)

    def _setState(self, vin, new, limit):
        # Returns a (vin, old, new, limit) transition, or None if unchanged.
        old = self._state.get(vin, UNKNOWN)
        self._state[vin] = new
        if old == new:
            return None
        logger.info("Vehicle %s presence: %s -> %s", vin, old, new)
        return (vin, old, new, limit)

    # -- handlers; run without the lock ------------------------------------

    def _runHandler(self, vin, old, new, limit):
        if new == HOME:
            handler = self._onArrival
        elif new == AWAY and old == HOME:
            handler = self._onDeparture
        else:
            # unknown -> away: there is no evidence the car was ever home.
            handler = None
        if handler is None:
            return
        try:
            handler(vin, limit)
        except Exception:
            logger.error(
                "Presence handler for %s (%s -> %s) failed: %s",
                vin,
                old,
                new,
                traceback.format_exc(),
            )
```

In `lib/TWCManager/TWCMaster.py`, after line 18 (`from TWCManager.VehicleCommandQueue import VehicleCommandQueue`) add:

```python
from TWCManager.VehiclePresence import VehiclePresence
```

and after the `self.vehicleCommandQueue = VehicleCommandQueue(...)` statement in `__init__` (lines 106-108) add:

```python
        # Per-VIN presence tracking. Its thread is started by TWCManager.py
        # (only as a real master); until then observers record and nothing acts.
        self.vehiclePresence = VehiclePresence(self)
```

- [ ] **Step 4: Run the presence tests**

Run: `$VENV/bin/python -m pytest tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py -q -p no:cacheprovider`
Expected: `92 passed` (`29` from `test_vehicle_presence.py`, `63` from `test_twcmaster.py`).

- [ ] **Step 5: Run the full unit suite and black**

Run: `$VENV/bin/black lib/ && $VENV/bin/black --exclude="setup.py|tests/*" --check . && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`
Expected: `582 passed, 1 warning`.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/VehiclePresence.py lib/TWCManager/TWCMaster.py tests/unit/test_vehicle_presence.py tests/unit/test_twcmaster.py
git commit -m "$(cat <<'EOF'
Add VehiclePresence: per-VIN home/away tracking on its own thread

Observers record from any thread; one daemon thread probes due VINs
through injected sources, applies the decision rules under a lock, and
runs the arrival/departure handlers without it. Sources and handlers
are wired in the next tasks.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

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

### Task 9: Live verification (controller runs this)

**Files:** none changed. This task is run by the controller on the live box (`ssh twcmanager`; deploys and restarts are pre-approved per the memory note), with #669 and #670 in place.

**Interfaces:**
- Consumes: the whole branch.
- Produces: a pass/fail report against the spec's "Live testing" section.

- [ ] **Step 1: Deploy the branch and restart**

Run on the box: deploy `fix/vehicle-presence`, `systemctl restart twcmanager`, then `journalctl -u twcmanager -f`.
Expected: startup logs include `BLE module initialized`, no `VehiclePresence` errors, and one `Presence check for ... nominated` line within a few minutes of the first TWC heartbeat with power.

- [ ] **Step 2: No wakes while parked and asleep**

With the car parked at home and TeslaMate showing `asleep`, from a shell on the box run `curl -X POST http://127.0.0.1:8088/api/checkArrival` and watch the journal.
Expected: `BLE presence probe: <VIN> reachable, status VEHICLE_SLEEP_STATUS_ASLEEP` within ~5 s; no `state charge` read (`BLE charge state fetch` absent); no `wake` command; TeslaMate still shows `asleep` five minutes later. Response code 202.

- [ ] **Step 3: Depart and return**

Unplug, drive out of the geofence, return and plug in.
Expected in the journal:
- within a minute of unplugging: `Presence check for <VIN> nominated (unplug) at +300,1200,2700 s`;
- departure detected by TeslaMate (`Vehicle <VIN> presence: home -> away`) or, without telemetry, after two failed BLE probes at +5/+20 min;
- `Vehicle <VIN> departed; restoring its normal charge limit` when the Fleet API is allowed, or the single INFO line `no remote command channel can restore` with `commandPolicy: ble_only`;
- on return: `Vehicle <VIN> presence: away -> home` and `Vehicle <VIN> arrived; applying charge limit <policy limit>` within about a minute of geofence entry or first BLE contact, followed by `Set <VIN> to charge limit <policy limit>%` from TeslaBLE (or TeslaAPI).

- [ ] **Step 4: The incident case**

While away, raise the charge limit by hand in the Tesla app, then return.
Expected: on arrival `Vehicle <VIN> charge limit was set to <hand value>% by hand; adopting it as the normal limit`, then the policy limit is applied. `settings.json` `chargeLimits[<VIN>]` reads `[<hand value>, <policy limit>]`.

- [ ] **Step 5: No new stalls**

Run: `journalctl -u twcmanager --since "-2h" | grep -c "Main loop stalled"`
Expected: no higher than before the deploy (compare with the same window on the previous day).

- [ ] **Step 6: Report**

Record the outcome of Steps 2-5 in the PR description for `fix/vehicle-presence`, including the relevant journal lines. Anything that fails goes back to the task that owns it.
