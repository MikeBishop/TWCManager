# Vehicle Watch (Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every registry car that no TWC names and no live feed covers, keep "here, plugged, drawing, done" current for the distributor by asking the free sleep-state question on a slow clock and reading the car only when that answer changes, within a paid budget and without ever waking it.

**Architecture:** A leaf `Vehicle/Watch.py` holds a per-car schedule (next-due per ring, last answers, a transition memo) and is ticked by `ControlTick` once a second; it computes each car's situation from `Presence.decide` and `Presence.asleep`, and dispatches jobs to the existing BLE worker and cloud queue (`VehicleReconciler`), never doing I/O on the tick. Ring 1 is `TeslaBLE.ping` (VCSEC, keyless, now also recording the charge-port door) or `TeslaAPI.onlineState` (free); Ring 2 is the registry read cascade with `force=True`; cloud Ring 2 draws from a token bucket in `Vehicle/WatchBudget.py`. An EMS load-step detector in `Watch` turns a consumption step into an event read. The `statusDeferral` ladder, `chargeUpdateInterval` and the battery-level `checkCharge` polling are deleted.

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `pytest` (`tests/unit`), `requests_mock`; `black` on touched files.

**Spec:** `.superpowers/specs/2026-10-20-vehicle-watch-design.md` (approved 2026-10-20). Inputs it builds on: `.superpowers/specs/2026-10-13-vehicle-model-design.md`, `.superpowers/phase5-presence-inventory.md` ("Presence model — final").

**Branch:** `vehicle-model/phase6` from `vehicle-model/phase5` at **06d404bd** (the squashed Phase 5 plus the Fleet Telemetry field task). Line numbers below are at that commit. Worktree: the builder's choice; the phase5 worktree is another session's.

## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `tests --ignore=tests/API --ignore=tests/integration`. BASE: **2190 passed** (06d404bd). The full suite passes after every task.
- **Reads never wake.** Every watch read passes `allowWake=False` (the default of `Vehicle.read`). `_TeslaAPIProvider.fetch` ignores `allowWake` already; `TeslaBLEProvider.fetch` wakes only when asked, and the watch never asks.
- **BLE queue:** no third priority level is added (the spec left it to the builder); the watch submits at most one job per car per ring and never while one is in flight, so a command waits for at most one ping per watched car.
- **No I/O on the control tick.** `Watch.pass_` only computes and submits jobs. BLE jobs go through `VehicleReconciler.submitJob` (the BLE queue); cloud jobs through the cloud queue (Task 4 adds the parameter). No lock is held across a submit.
- **Lock order unchanged:** `TeslaBLE._bleLock → master.settingsLock → registry leaf`. `Watch` has one lock of its own, a leaf below all of these: never call out of the registry or a provider while holding it.
- **Paid prices** (spec): `vehicle_data` $0.002, wake $0.02, command $0.001; `vehicles/{vin}` and the list are free. Owner API reads are free but draw a zero-price token.
- **`tests/unit/test_command_path_parity.py` counts and timings are not edited.** Task 8 deletes the ladder; if any parity count moves, stop and report (the F1 rule). Expected: none move, since every row's reads are inside `READ_MAX_AGE` of each other or forced.
- **Comment rule** (user, 2026-10-17): comments say why the code is what it is; no history, no phase names, PR or issue numbers, no ruling IDs. Short.
- **Line reporting** per task: before and after `git ls-files lib | grep '\.py$' | xargs cat | wc -l`, and `git diff --shortstat <task BASE> -- lib`. Growth is allowed (user, 2026-10-20); minimise it, and fold in the candidates named in Task 8.
- **Behaviour changes allowed** are those each task names with its test. Anything else is a defect. In particular Phase 5's presence decisions (`Presence.decide`, `applicable`, the unplug filters) do not change except where Task 1 says.
- **Config:** a top-level `watch` section in config.json (all keys optional); `config.cloudUpdateInterval` is accepted and ignored with one log line (Task 8). `settings.json` gains `watchBudget` (Task 3).
- **Real objects in cross-module tests:** `tests.unit.test_limit_reconciler.setup` (real `TWCMaster`, registry, `DesiredStore`, inline reconciler on a `Clock`), `tests.unit.reconcile_helpers` (`placeAt`, `bleAnswers`, `runPending`, `ScriptedProvider`), `tests.unit.test_command_path_parity.FleetCar` with `requests_mock` for cloud rows. Never mock a success value the real method never returns.
- Commit trailer per the session's reminder. One commit per task, more where a task says.

## Review Focus

1. **Paid counts after the ladder** (Task 8): a Fleet-only car read twice inside 5 min by two different callers (the reconciler's read before a write, then `checkPlug`'s forced read) must still make the same number of `vehicle_data` requests as at BASE. Test: `test_two_callers_inside_read_max_age_pay_once` (Task 8).
2. **BLE worker starvation** (Task 4): with four watched cars all due, a command submitted after them must run within one ping each, and the watch must never have more than one job in flight per car nor submit while one is pending. Test: `test_one_watch_job_in_flight_per_car_and_commands_are_not_starved` (Task 4).
3. **Restart and the budget** (Task 3): a restart with a persisted bucket must not refill it; a persisted bucket from a previous month refills only to what the elapsed time earns, capped at capacity. Test: `test_restart_keeps_the_bucket_and_elapsed_time_refills_it` (Task 3).
4. **Feed flapping** (Task 4): a feed that disconnects and reconnects within one Ring 1 period must not make the watch ping; the watch resumes only when the feed has been down at the moment a ring is due. Test: `test_a_feed_blip_shorter_than_the_cadence_makes_no_ping` (Task 4).
5. **Asleep after Stopped keeps its share** (Task 2): a plugged car paused by us that falls asleep must still be offered power and be startable; only a car asleep after Charging releases its share. Tests: `test_asleep_after_stopped_still_wants_to_charge`, `test_asleep_after_charging_releases_its_share` (Task 2).

---

## File structure

- **Create**
  - `lib/TWCManager/Vehicle/Watch.py` (~220 lines): `notWatched`, `situation`, `cadence`, class `Watch` (schedule, transitions, dispatch, `readNow`, `loadSample`, `status`), class `LoadStep`.
  - `lib/TWCManager/Vehicle/WatchBudget.py` (~55 lines): class `WatchBudget` (token bucket, two classes, JSON in/out).
  - `tests/unit/test_watch.py`, `tests/unit/test_watch_budget.py`, `tests/unit/test_watch_load_step.py`.
- **Modify**
  - `lib/TWCManager/Vehicle/Registry/Fields.py:15-41` (`FIELDS`): add `chargePortOpen`.
  - `lib/TWCManager/Vehicle/TeslaBLE.py:627-648` (`_runPing`, `_noteSleep`, `ping`): record the door, keyless gate, `scan` parameter.
  - `lib/TWCManager/Vehicle/Presence.py:69-80` (`_plug`), `:120-160` (`noteObservation`), `:170-186` (`pluggedNow`), `:196-212` (`checkPlug`).
  - `lib/TWCManager/EVSEInstance/VehicleEndpoint.py:45-60, 100-106` (`wantsToCharge`, `occupied`; add `isCharging`, `currentAmps`).
  - `lib/TWCManager/Vehicle/Reconcile/Reconciler.py:124-125` (`submitJob`), `lib/TWCManager/Vehicle/Reconcile/Run.py:150-163` (the pre-command ping's `lately`).
  - `lib/TWCManager/Vehicle/TeslaAPI.py:144-145, 206-208, 665, 1629-1646, 1815, 1876-1890` (deletions), `lib/TWCManager/Vehicle/HomeAssistant.py:542-557`.
  - `lib/TWCManager/TWCMaster.py:462-480` (`updateChargeAtHome`), `:1112-1190` (`loadSettings`), `:1672-1700` (`saveSettings`).
  - `lib/TWCManager/TWCManager.py:393-415` (`check_green_energy`), `:795` (wiring), `lib/TWCManager/ControlTick.py:62-70` (`housekeeping`).
  - `lib/TWCManager/Control/HTTPControl.py:388-420` (template globals), `lib/TWCManager/Control/themes/Default/vehicles.html.j2`.
  - `docs/Settings.md`, `docs/PolicyCustomization.md`, `docs/modules/Vehicle_TeslaBLE.md`, `docs/modules/Vehicle_FleetTelemetryMQTT.md`, `CHANGELOG.md`.

---

### Task 1: The charge-port door, and a keyless ping

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Fields.py:15-41`, `lib/TWCManager/Vehicle/TeslaBLE.py:627-648`, `lib/TWCManager/Vehicle/Presence.py:69-80, 120-160, 170-186, 196-212`
- Test: `tests/unit/test_presence.py`, `tests/unit/test_teslable_pairing_status.py`

**Interfaces:**
- Produces: registry field `chargePortOpen` (bool, source `TeslaBLE`); `TeslaBLE.ping(vin, scan=True) -> Optional[bool]` (True answered, False scan ran and missed, None no answer and no scan); `Presence._plug("chargePortOpen", obs)` → False for a False value, None for True.
- Behaviour changes (named): (a) a CLOSED door while awake is strong unplug evidence from `TeslaBLE`; (b) `ping` works for any well-formed VIN while `canScan()` or the tool is present, not only a claimed one; (c) `checkPlug` pings any such car, and an awake answer with the door CLOSED returns False without a charge read.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_presence.py` (helpers `home`, `placed`, `later` exist):

```python
def test_a_closed_charge_port_while_awake_marks_an_unplug():
    m, v, c = placed()
    v.observe("pluggedIn", True, "TeslaBLE")          # plugged, strong
    later(c)
    v.observe("chargePortOpen", False, "TeslaBLE")
    assert v.markAt("unplug") == c.t and P.pluggedNow(m, v) is False

def test_an_open_charge_port_is_not_plug_evidence():
    m, v, c = placed()
    v.observe("chargePortOpen", True, "TeslaBLE")
    assert v.markAt("plugIn") == P.NEVER and P.pluggedNow(m, v, None) is None

def test_check_plug_answers_from_an_awake_closed_door_without_a_read():
    m, r, v, c = home()
    v.observe("pluggedIn", True, "TeslaBLE")
    later(c)
    ble = m.providerOrder.provider("TeslaBLE").module
    def ping(vin, scan=True):
        v.observe("state", "online", "TeslaBLE"); v.observe("chargePortOpen", False, "TeslaBLE"); return True
    ble.ping = ping
    reads = []
    v.read = lambda *a, **k: reads.append(a)
    assert P.checkPlug(m, v, c.t - 1) is False and reads == []
```

In `tests/unit/test_teslable_pairing_status.py` (`scanner()` and the `run` pattern at :523 exist):

```python
AWAKE_OPEN = b'{"closureStatuses":{"chargePort":"CLOSURESTATE_OPEN"},"vehicleSleepStatus":"VEHICLE_SLEEP_STATUS_AWAKE","userPresence":"VEHICLE_USER_PRESENCE_NOT_PRESENT"}'
ASLEEP = b'{"vehicleSleepStatus":"VEHICLE_SLEEP_STATUS_ASLEEP","userPresence":"VEHICLE_USER_PRESENCE_NOT_PRESENT"}'

def test_ping_records_the_door_while_awake_and_nothing_asleep():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")
    ble._tool = lambda vin, *args: (AWAKE_OPEN, b"", 0)
    assert ble.ping(VIN) is True
    assert v.value("state") == "online" and v.value("chargePortOpen") is True
    ble._tool = lambda vin, *args: (ASLEEP, b"", 0)
    assert ble.ping(VIN) is True
    assert v.value("state") == "asleep" and v.latest("chargePortOpen").value is True  # unchanged

def test_ping_runs_for_a_vin_with_no_key_and_no_settings_record():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")       # no TeslaBLE claim, nothing under settings["Vehicles"]
    assert not master.settings.get("Vehicles", {}).get(VIN)
    runs = []
    ble._run_command_with_timeout = lambda cmd, timeout, **k: runs.append(cmd) or (ASLEEP, b"", 0)
    assert ble.ping(VIN) is True and v.value("state") == "asleep"
    assert len(runs) == 1 and runs[0][-1] == "body-controller-state" and "-key-file" not in runs[0]

def test_ping_with_scan_false_returns_none_and_observes_nothing_when_unanswered():
    ble, reg, master = scanner()
    v = reg.getOrCreate(VIN, "t")
    ble._tool = lambda vin, *args: (b"", b"timeout", 1)
    ble.scanForVehicleInRange = lambda vin: pytest.fail("no scan asked")
    assert ble.ping(VIN, scan=False) is None and v.latest("bleReach") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/unit/test_presence.py -k "charge_port or closed_door" tests/unit/test_teslable_pairing_status.py -k ping -q`
Expected: FAIL (`KeyError: 'chargePortOpen'`, `TypeError: ping() got an unexpected keyword argument 'scan'`).

- [ ] **Step 3: Add the field and record the door**

- `Fields.py`: append `"chargePortOpen"` to `FIELDS` with a one-line comment (the VCSEC charge-port door, reported only while the car is awake).
- `TeslaBLE._noteSleep(self, vin, out)`: parse `closureStatuses.chargePort` when present: `"CLOSURESTATE_OPEN"` → observe `chargePortOpen` True, `"CLOSURESTATE_CLOSED"` → False, anything else or absent → no observation. Keep the sleep observation as is.
- `TeslaBLE._tool` (`:588-604`): for `body-controller-state` only, run without `-key-file` and without `sendPrivateKey`, and do not require a `settings["Vehicles"][vin]` record (the command is unauthenticated); every other subcommand keeps the key and the record check.
- `TeslaBLE.ping(self, vin, scan=True) -> Optional[bool]`: `_runPing` takes `scan`; with `scan=False` an unanswered tool run returns None and observes nothing. With `scan=True` behaviour is as today. Drop any claim check on the ping path (there is none in `ping` itself; `checkPlug` and `pick` gate on claims, below).

- [ ] **Step 4: Presence: CLOSED is unplug evidence, OPEN is nothing**

- `Presence._plug(field, obs)`: `if field == "chargePortOpen": return False if obs.value is False else None`.
- `Presence.noteObservation`: add `"chargePortOpen"` to the `("pluggedIn", "chargingState")` branch so a False marks `unplug` (and `lifeAt` when seen) by the same rule; a True never marks `plugIn` (`_plug` returns None, so the existing `plugged is True` branch does not fire).
- `Presence.pluggedNow`: iterate `("pluggedIn", "chargingState", "chargePortOpen")`.
- `Presence.unpluggedAt`: same three fields.
- `Presence.checkPlug`: replace the claim gate with `canPing = ble is not None and ble.module is not None`; after a True ping: `if asleep(v): return True`; else `door = v.reported("chargePortOpen").get("TeslaBLE")`; `if door is not None and door.at >= since and door.value is False: return False`; otherwise fall through to the read as today.
- `Presence.pick` (`fits`): the pre-read ping's `"TeslaBLE" in v.claims` stays for the **charge read** (it needs the key) but the ping itself may run for any car; a CLOSED door excludes the car (`return False`) before any read.

- [ ] **Step 5: Run the tests and the full suite**

Run: the three test files, then the full suite. Expected: all pass; `test_presence.py` rows that count BLE reads in `pick` are unchanged (the door is absent in their fixtures).

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/Vehicle/Registry/Fields.py lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/Vehicle/Presence.py tests/unit/test_presence.py tests/unit/test_teslable_pairing_status.py
git commit -m "Read the charge-port door on the sleep-safe ping; a closed door is an unplug"
```

---

### Task 2: An asleep car draws nothing; after Charging it wants nothing

**Files:**
- Modify: `lib/TWCManager/EVSEInstance/VehicleEndpoint.py:45-60, 100-106`
- Test: `tests/unit/test_vehicle_endpoint.py`

**Interfaces:**
- Produces: `VehicleEndpoint.isCharging -> bool`, `VehicleEndpoint.currentAmps -> float` (both already read by `EVSEInstance` callers; today inherited from `EVSEInstance`: read `lib/TWCManager/EVSEInstance/EVSEInstance.py` for their base definitions and keep the same names), `wantsToCharge` sleep-aware.
- Behaviour changes (named): (d) `Presence.asleep(v) is True` ⇒ `isCharging` False and `currentAmps` 0.0; (e) asleep and `chargingState == "Charging"` ⇒ `wantsToCharge` False; asleep and `"Stopped"` ⇒ True as today.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_vehicle_endpoint.py`; use its existing master/registry fixture and `VehicleEndpoint(v, m.providerOrder, m)`)

```python
def endpoint():
    m, r, v, c = setup(here=False)                    # test_limit_reconciler.setup
    placeAt(m, v, HOME); v.observe("pluggedIn", True, "TeslaBLE")
    return m, v, VehicleEndpoint(v, m.providerOrder, m)

def test_asleep_after_charging_releases_its_share():
    m, v, e = endpoint()
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 24, "TeslaBLE")
    assert e.wantsToCharge and e.isCharging and e.currentAmps == 24
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    assert not e.wantsToCharge and not e.isCharging and e.currentAmps == 0

def test_asleep_after_stopped_still_wants_to_charge():
    m, v, e = endpoint()
    v.observe("chargingState", "Stopped", "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    assert e.wantsToCharge and not e.isCharging and e.currentAmps == 0

def test_a_sign_of_life_after_sleep_restores_the_readings():
    m, v, e = endpoint()
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 24, "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "asleep", "TeslaBLE")
    m.vehicleRegistry._clock.t += 10
    v.observe("state", "online", "TeslaBLE")
    assert e.wantsToCharge and e.isCharging and e.currentAmps == 24
```

- [ ] **Step 2: Run to verify they fail.** Expected: the first two fail on the asleep assertions.

- [ ] **Step 3: Implement** in `VehicleEndpoint`: a private `_asleep(self) -> bool` returning `Presence.asleep(self.vehicle) is True`; `isCharging` = not asleep and `chargingState == "Charging"`; `currentAmps` = 0.0 when asleep else `vehicle.value("actualCurrent", 0) or 0`; `wantsToCharge` = state in ("Charging", "Stopped") and not (asleep and state == "Charging"). One comment on why Stopped keeps wanting (a start is allowed to wake). `occupied` unchanged.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass; the distributor tests (`test_charging_points.py`, `test_distributor_*.py`) unchanged since their cars are never observed asleep.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/EVSEInstance/VehicleEndpoint.py tests/unit/test_vehicle_endpoint.py
git commit -m "An asleep car draws nothing; asleep after Charging, it has finished"
```

---

### Task 3: The paid-read budget

**Files:**
- Create: `lib/TWCManager/Vehicle/WatchBudget.py`
- Modify: `lib/TWCManager/TWCMaster.py:1112-1190` (`loadSettings`), `:1672-1700` (`saveSettings`)
- Test: `tests/unit/test_watch_budget.py`

**Interfaces:**
- Produces:
  ```python
  EVENT, ROUTINE = "event", "routine"
  class WatchBudget:
      def __init__(self, monthlyUSD: float, clock=time.time, floor: float = 0.5): ...
      capacity: float            # monthlyUSD / 30: one day's worth
      def tokens(self, now: Optional[float] = None) -> float
      def spend(self, price: float, cls: str, now: Optional[float] = None) -> bool
      def toJSON(self) -> dict   # {"tokens": float, "at": float}
      def load(self, data) -> None   # None or a malformed dict: start full
  ```
  `master.watchBudget` is the instance; `settings["watchBudget"]` its JSON.
- Rules: fill rate `monthlyUSD / (30 * 86400)` per second, capped at `capacity`; `spend` for `EVENT` succeeds when `tokens >= price`; for `ROUTINE` when `tokens - price >= floor * capacity`; a zero price always succeeds and still refreshes the stamp; `spend` logs INFO once when the bucket first cannot pay and once when it can again (a `_empty` flag).

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_watch_budget.py`, a `Clock` like `reconcile_helpers.Clock`)

```python
def test_event_reads_may_spend_the_whole_bucket_but_routine_stops_at_the_floor():
    c = Clock(0.0); b = WatchBudget(3.0, clock=c)      # capacity 0.1
    assert b.capacity == pytest.approx(0.1)
    assert b.spend(0.002, ROUTINE) and b.tokens() == pytest.approx(0.098)
    while b.spend(0.002, ROUTINE): pass
    assert b.tokens() == pytest.approx(0.05, abs=0.002)   # the floor holds
    assert b.spend(0.002, EVENT) and not b.spend(0.2, EVENT)

def test_tokens_refill_at_the_monthly_rate_and_cap_at_a_day():
    c = Clock(0.0); b = WatchBudget(3.0, clock=c)
    while b.spend(0.002, EVENT): pass
    c.t += 86400 / 2
    assert b.tokens() == pytest.approx(0.05, abs=0.001)
    c.t += 86400 * 10
    assert b.tokens() == pytest.approx(0.1)

def test_restart_keeps_the_bucket_and_elapsed_time_refills_it():
    c = Clock(1000.0); b = WatchBudget(3.0, clock=c)
    while b.spend(0.002, EVENT): pass
    saved = b.toJSON()
    c.t += 3600
    b2 = WatchBudget(3.0, clock=c); b2.load(saved)
    assert b2.tokens() == pytest.approx(0.1 / 24, abs=0.001)
    b3 = WatchBudget(3.0, clock=c); b3.load({"tokens": "junk"})
    assert b3.tokens() == pytest.approx(0.1)

def test_a_zero_price_always_spends_and_settings_round_trip(tmp_path):
    # master.loadSettings/saveSettings carry settings["watchBudget"]
    m, s = make_master()                                  # tests/unit/test_limit_reconciler.make_master
    m.config["config"]["settingsPath"] = str(tmp_path)
    while m.watchBudget.spend(0.002, EVENT): pass
    assert m.watchBudget.spend(0.0, ROUTINE)
    m.saveSettings(); m.settings.clear(); m.loadSettings()
    assert m.watchBudget.tokens() < 0.01
```

- [ ] **Step 2: Run to verify they fail.** Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `WatchBudget`** as specified; `toJSON` stores tokens and the stamp; `load` accepts the two numbers, else starts full. In `TWCMaster.__init__` create `self.watchBudget = WatchBudget(float(config.get("watch", {}).get("monthlyBudgetUSD", 3.0)))`; `loadSettings` calls `self.watchBudget.load(self.settings.get("watchBudget"))` next to the registry blob (`:1182`); `saveSettings` writes `self.settings["watchBudget"] = self.watchBudget.toJSON()` under `settingsLock` next to `vehicleRegistry` (`:1690`).

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/WatchBudget.py lib/TWCManager/TWCMaster.py tests/unit/test_watch_budget.py
git commit -m "A monthly budget for the watch's paid reads, kept across restarts"
```

---

### Task 4: The watch: who, what situation, Ring 1 on a clock

**Files:**
- Create: `lib/TWCManager/Vehicle/Watch.py`
- Modify: `lib/TWCManager/Vehicle/Reconcile/Reconciler.py:124-125`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Consumes: `Presence.decide/presence/asleep/drivingNow/twcVinAt`, `Vehicle.syncSource`, `TeslaBLE.ping(vin, scan)`, `TeslaBLE.canScan()`, `TeslaAPI.onlineState(vehicle)`, `HomeAssistant` attachment's `refresh_from_home_assistant(api)`, `VehicleReconciler.submitJob`.
- Produces:
  ```python
  # Watch.py
  HOME_ASLEEP, HOME_AWAKE, HOME_CHARGING, AWAY_ASLEEP, AWAY_AWAKE, UNKNOWN = (
      "homeAsleep", "homeAwake", "homeCharging", "awayAsleep", "awayAwake", "unknown")
  DEFAULTS = dict(enabled=True, homeAsleepSecs=900, homeAwakeSecs=240, awayAsleepSecs=1800,
      awayAwakeSecs=300, chargingReadSecs=300, cloudChargingReadSecs=900,
      sleepCourtesySecs=1200, scanAwaySecs=150, monthlyBudgetUSD=3.0, emsTrigger=True,
      emsNoiseWatts=300)
  def notWatched(master, v) -> Optional[str]   # None = watched; else "anonymous" | "named by TWC <id>" | "covered by <feed>" | "disabled"
  def situation(master, v) -> str
  class Watch:
      def __init__(self, master, clock=time.time): ...
      def settings(self) -> dict                 # DEFAULTS overlaid with config["watch"]
      def pass_(self, now: Optional[float] = None) -> None   # the control tick
      def status(self, v) -> dict                # {"watched": bool, "why": str, "last": str, "lastAt": float, "nextAt": float}
  ```
  `VehicleReconciler.submitJob(self, key, kind, run, worker="ble") -> bool`: `worker="cloud"` puts on the cloud queue.
- `situation`: `UNKNOWN` when `asleep(v)` is None and no state is known; `HOME_*` when `presence == HOME`; `AWAY_*` for NOT_HOME and PRESUMED; `*_ASLEEP` when `asleep(v) is True` or the feed's/cloud's last state is `offline`; `HOME_CHARGING` when HOME, not asleep and `chargingState == "Charging"`.
- Ring 1 source per car, in order: the BLE ping when `TeslaBLE` is loaded and `canScan()` or the tool binary is present; else `TeslaAPI.onlineState` when the car has a `TeslaAPI` attachment; else the HA refresh when it has a `HomeAssistant` attachment; else nothing (the car is watched but has no status source; `status()["why"]` says so).
- Scheduling: per car, `_due[vin]["status"]` is the next time; a job is submitted when `now >= due` and `vin not in _inflight`; the job's completion (the queue's report, or the job's own `finally`) clears `_inflight` and sets the next due from `cadence(situation)`. The memo `_seen[vin]` (situation, presence, `markAt("plugIn")`, `chargingState`) is refreshed every pass and compared; Task 5 uses the comparison.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_watch.py`; `setup()` from `test_limit_reconciler` gives an inline reconciler whose BLE/cloud queues run on `runPending`)

```python
def test_a_twc_named_car_and_a_feed_covered_car_are_not_watched():
    m, r, v, c = setup(here=False)
    assert notWatched(m, v) is None
    m.vehicleRegistry.observeTwcVin("8244", VIN); slave = gen2Slave(m, "8244", state=0x03)   # tests/unit/gen2_helpers
    assert notWatched(m, v).startswith("named by")
    m2, r2, v2, c2 = setup(here=False)
    v2.observe("state", "online", "TeslaMateVehicle"); liveFeed(m2, "TeslaMateVehicle")     # registers liveness returning now
    assert notWatched(m2, v2) == "covered by TeslaMateVehicle"

def test_situations():
    m, r, v, c = setup(here=False)
    assert situation(m, v) == UNKNOWN
    placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    assert situation(m, v) == HOME_ASLEEP
    c.t += 10; v.observe("state", "online", "TeslaBLE")
    assert situation(m, v) == HOME_AWAKE
    v.observe("chargingState", "Charging", "TeslaBLE")
    assert situation(m, v) == HOME_CHARGING
    placeAt(m, v, AWAY); v.observe("state", "offline", "FleetTelemetryMQTT")
    assert situation(m, v) == AWAY_ASLEEP

def test_ring_one_pings_on_the_cadence_and_not_before():
    m, r, v, c = setup(here=False, ble=True)             # a TeslaBLE module with ping stubbed to answer asleep
    placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); pings = bleAnswers(m, asleep=True)
    w.pass_(); runPending(r.ble)
    assert pings.count == 1
    c.t += 899; w.pass_(); runPending(r.ble); assert pings.count == 1
    c.t += 1;   w.pass_(); runPending(r.ble); assert pings.count == 2

def test_cloud_status_check_for_a_car_ble_cannot_reach(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="asleep", at=AWAY)   # test_command_path_parity.FleetCar
    attachFleet(m, v, car)                                # the parity file's way of listing the car on the Fleet slot
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud)
    assert counts(requests_mock)["free"] == 1 and paid(requests_mock) == (0, 0, 0)
    assert v.value("state") == "asleep"

def test_one_watch_job_in_flight_per_car_and_commands_are_not_starved():
    m, r, v, c = setup(here=False, ble=True); cars = [v] + [m.vehicleRegistry.getOrCreate(x, "t") for x in (VIN2, VIN3, VIN4)]
    for x in cars: placeAt(m, x, HOME); x.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); w.pass_(); w.pass_()
    assert len(entries(r.ble)) == 4                       # one per car, not eight
    m.desired.set(VIN, CHARGE_LIMIT, 80, "policy"); r.pass_()
    order = [e.kind if hasattr(e, "kind") else "attempt" for e in entries(r.ble)]
    assert order.count("attempt") == 1 and order.index("attempt") <= 4

def test_a_feed_blip_shorter_than_the_cadence_makes_no_ping():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME)
    v.observe("state", "online", "TeslaMateVehicle"); feed = liveFeed(m, "TeslaMateVehicle")
    w = Watch(m, clock=c); pings = bleAnswers(m, asleep=True)
    w.pass_(); runPending(r.ble); assert pings.count == 0
    feed.down = True; c.t += 30; w.pass_(); runPending(r.ble)          # not yet due: covered when last checked
    feed.down = False; c.t += 30; w.pass_(); runPending(r.ble)
    assert pings.count == 0
    feed.down = True; c.t += 240; w.pass_(); runPending(r.ble)
    assert pings.count == 1
```

Test helpers this task adds (later tasks use them; exact names):
- `tests/unit/test_limit_reconciler.setup(*providers, clock=True, here=True, battery=60, ble=False)`: `ble=True` loads a real `TeslaBLE` on the master (as `test_teslable_pairing_status.scanner()` does, `isDockerCached = False`), registers its provider, and leaves `_tool` to the stubs below.
- `reconcile_helpers.bleAnswers(master, asleep=None, answer=True, charging=None)` → an object with `.count`; replaces `TeslaBLE.ping` with a stub that counts, returns `answer` (True/False/None), and when `answer` is True observes `state` ("asleep" if `asleep` else "online") from `TeslaBLE`. (Extend the existing `bleAnswers(master, ok=True)`; keep `ok` working.)
- `reconcile_helpers.bleReads(master, soc=50, charging="Stopped", amps=0, limit=80)` → an object with `.count` and settable `.charging`/`.amps`/`.soc`; replaces `TeslaBLE.get_charge_state` with a stub that counts and returns the normalized dict (`batteryLevel`, `chargeLimit`, `chargingState`, `actualCurrent`, `availableCurrent`, `voltage` 240, `phases` 1).
- `reconcile_helpers.bleScans(master, inRange=False)` → `.count`; replaces `TeslaBLE.scanForVehicleInRange` with a stub that counts, observes `bleReach` as the real one does, and returns `inRange`.
- `reconcile_helpers.liveFeed(master, source)` → an object with `.down` (False); registers `master.vehicleRegistry.registerLiveness(source, lambda v: None if feed.down else registry.now())`.
- `reconcile_helpers.gen2Slave(master, twcid, state=0x03, amps=0.0)`: use the Gen2 slave factory already in `tests/unit/gen2_helpers.py` if one exists (read it first); else add one that creates and links a slave with `reportedState` and `reportedAmpsActual` set.
- `attachFleet(master, vehicle, car)` / `attachOwner(master, vehicle, car)`: the parity file's way of listing a `FleetCar` on the Fleet or Owner slot (read `test_command_path_parity.py` for the listing helper it uses and re-export it from `reconcile_helpers`).

- [ ] **Step 2: Run to verify they fail.** Expected: `ModuleNotFoundError: Watch`.

- [ ] **Step 3: Implement `Watch.py`** per the Interfaces block. `pass_` walks `master.vehicleRegistry.vehicles()`, skips `notWatched`, computes `situation`, submits one status job per due car. A BLE status job is `lambda: ble.ping(vin, scan=False)`; a cloud one `lambda: carapi.onlineState(vehicle)`; an HA one `lambda: hv.refresh_from_home_assistant(ha)`. Each job runs under a `try/finally` that clears `_inflight` and reschedules. The watch's own lock guards `_due`, `_inflight`, `_seen` only. `settings()` reads `master.config.get("watch", {})` over `DEFAULTS` once at construction. The "feed covers it" check happens at the moment a ring is due, which gives Review Focus 4 for free.
- `Reconciler.submitJob(self, key, kind, run, worker="ble")`: `(self.cloud if worker == "cloud" else self.ble).put(Run.Job(key, kind, run))`.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py lib/TWCManager/Vehicle/Reconcile/Reconciler.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Watch cars no TWC or feed covers: the free sleep question on a slow clock"
```

---

### Task 5: Ring 2 on change: arrivals, wakes, charging, the courtesy window

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Produces: `Watch.readNow(self, vin: str, reason: str, cls: str = EVENT) -> None` (thread-safe; the next pass submits the read); `Watch.status()["last"]` names the last job (`"ping"`, `"status"`, `"read"`, `"scan"`).
- Read classes: an **event read** on (i) the memo's `presence` becoming HOME, (ii) `markAt("plugIn")` growing, (iii) `HOME_ASLEEP`→`HOME_AWAKE`, (iv) `readNow`; a **routine read** every `chargingReadSecs` (BLE) or `cloudChargingReadSecs` (cloud) while `HOME_CHARGING`, and every `chargingReadSecs` for a TWC-named car whose slave reports `reportedAmpsActual >= 1` or whose Gen3 unit's `currentAmps >= 1` (the one case a TWC-named car is touched).
- Courtesy: in `HOME_AWAKE` no read is made within `sleepCourtesySecs` of the last read of that car, except an event read for a plug-in or `readNow`.
- The read itself: `vehicle.read("chargingState", 0, force=True, providers=<local providers>)` on the BLE worker when a local provider is ready for `READ_CHARGE`; else on the cloud queue, after `master.watchBudget.spend(price, cls)` where `price` is the first non-local ordered provider's `cost(READ_CHARGE).price` (0.0 for Owner); a refused spend logs DEBUG and reschedules at the routine cadence. A read-only car (`VehicleEndpoint.isReadOnly`, i.e. no `SET_AMPS` candidate) gets event reads only.
- Behaviour change (named): (f) a car arriving by any route gets a read; a car waking at home gets a read; a charging car is read on the cadence.

- [ ] **Step 1: Write the failing tests**

```python
def test_arrival_by_twc_plug_in_reads_the_battery_once():
    m, r, v, c = setup(here=False, ble=True); w = Watch(m, clock=c); reads = bleReads(m, soc=18)   # helper: BLE charge read stub counting calls
    m.vehicleRegistry.observeTwcVin("8244", VIN); gen2Slave(m, "8244", state=0x03)
    v.observe("pluggedIn", True, "Gen2TWC")
    w.pass_(); runPending(r.ble)
    assert reads.count == 1 and v.value("batteryLevel") == 18
    c.t += 60; w.pass_(); runPending(r.ble); assert reads.count == 1

def test_a_wake_at_home_reads_once_then_waits_the_courtesy_window():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m, charging="Stopped")
    w.pass_(); c.t += 10; v.observe("state", "online", "TeslaBLE"); w.pass_(); runPending(r.ble)
    assert reads.count == 1
    for _ in range(4): c.t += 240; w.pass_(); runPending(r.ble)
    assert reads.count == 1                                          # inside sleepCourtesy (1200 s)
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 1  # still no routine read while not charging

def test_a_charging_car_is_read_on_the_cadence_and_released_when_it_sleeps():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m, charging="Charging", amps=24)
    w.pass_(); runPending(r.ble); assert reads.count == 1 and situation(m, v) == HOME_CHARGING
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2
    c.t += 10; v.observe("state", "asleep", "TeslaBLE")
    e = VehicleEndpoint(v, m.providerOrder, m); assert not e.wantsToCharge
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2

def test_cloud_reads_draw_from_the_budget_and_stop_at_the_floor(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", charging="Charging", at=HOME); attachFleet(m, v, car)
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud)              # status then the wake-at-home event read
    paidBefore = paid(requests_mock)[0]; assert paidBefore == 1
    for _ in range(40): c.t += 900; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] <= 26                               # routine reads stop at half the day's tokens
    assert m.watchBudget.tokens() >= 0.05 - 0.002

def test_read_now_is_an_event_read_even_for_a_read_only_car(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=HOME, api=OWNER); attachOwner(m, v, car)  # Owner-only: read-only
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud); n = counts(requests_mock)["free"]
    w.readNow(VIN, "test"); w.pass_(); runPending(r.cloud)
    assert counts(requests_mock)["free"] == n + 1 and paid(requests_mock) == (0, 0, 0)

def test_a_twc_named_car_is_read_only_while_current_flows():
    m, r, v, c = setup(here=False, ble=True); w = Watch(m, clock=c); reads = bleReads(m, soc=50)
    m.vehicleRegistry.observeTwcVin("8244", VIN); s = gen2Slave(m, "8244", state=0x03); v.observe("pluggedIn", True, "Gen2TWC")
    w.pass_(); runPending(r.ble); assert reads.count == 1            # the arrival read
    s.reportedAmpsActual = 0; c.t += 600; w.pass_(); runPending(r.ble); assert reads.count == 1
    s.reportedAmpsActual = 24; c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2
```

- [ ] **Step 2: Run to verify they fail.** Expected: `AttributeError: readNow`, read counts 0.

- [ ] **Step 3: Implement** the transition memo comparison, `readNow`, the two read classes, the courtesy window, the TWC-named current rule and the budget call, per the Interfaces block. The read job observes nothing itself: the cascade's providers do. After a read, `_lastRead[vin] = now`.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Read a watched car when something changes: arrival, wake, charging, on request"
```

---

### Task 6: Ring 0 for away cars, and the away location read

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Away and awake with `canScan()`: a `scanForVehicleInRange(vin)` job every `scanAwaySecs`; two consecutive unanswered pings while awake count as one miss each, and the second runs the scan whose result the scan itself records (`bleReach`). A miss while `asleep(v) is True` records nothing.
- Away and awake with no scan possible and a `TeslaAPI` attachment: one **event-class** location read (`vehicle.read("lat", 0, force=True)`, cloud) not before `fixAt + (3600 if carapi.is_far_from_home(lat, lon) else 1800)` where `fixAt` is `max(v.latest("lat").at, v.latest("lon").at)`; never while asleep; never twice inside the same awake episode unless the read showed driving (`shiftState` in D/R/N), in which case again after `awayAwakeSecs`.
- Behaviour change (named): (g) away cars are polled for position only as above; the ladder's unconditional re-reads go (Task 8 deletes them).

- [ ] **Step 1: Write the failing tests**

```python
def test_an_away_awake_car_is_scanned_and_two_misses_record_absence():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, AWAY); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); pings = bleAnswers(m, answer=None); scans = bleScans(m, inRange=False)
    w.pass_(); runPending(r.ble); assert scans.count == 0 and v.latest("bleReach") is None
    c.t += 300; w.pass_(); runPending(r.ble)
    assert scans.count == 1 and v.latest("bleReach").value is False

def test_a_miss_while_asleep_records_nothing():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); bleAnswers(m, answer=None); scans = bleScans(m, inRange=False)
    for _ in range(3): c.t += 900; w.pass_(); runPending(r.ble)
    assert scans.count == 0 and v.latest("bleReach") is None and P.presence(m, v) == P.HOME

def test_away_location_is_read_once_per_awake_episode_after_the_return_time(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=AWAY); attachFleet(m, v, car)
    v.observe("lat", AWAY[0], "FleetAPI"); v.observe("lon", AWAY[1], "FleetAPI")
    w = Watch(m, clock=c)
    for _ in range(5): c.t += 300; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] == 0                                 # under 1800 s since the fix
    c.t += 300; w.pass_(); runPending(r.cloud); assert paid(requests_mock)[0] == 1
    for _ in range(6): c.t += 300; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] == 1
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** the miss counter, the scan job, and the location rule. The away ETA uses `carapi.is_far_from_home` (kept) at the last fix.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Scan for an away car's return; read its position no sooner than it could be back"
```

---

### Task 7: The consumption step

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`, `lib/TWCManager/TWCManager.py:393-415` (`check_green_energy`)
- Test: `tests/unit/test_watch_load_step.py`

**Interfaces:**
- Produces:
  ```python
  class LoadStep:
      def __init__(self, thresholdWatts: float): ...
      def sample(self, watts: float, now: float) -> Optional[str]   # "up" | "down" | None, after a step held for two samples
  Watch.loadSample(self, now: Optional[float] = None) -> None       # computes unexplained watts, feeds LoadStep, calls readNow
  Watch.unexplainedWatts(self) -> float
  ```
- `unexplainedWatts` = `master.getConsumption()` minus, only when `master.subtractChargerLoad`, the known draw: `master.getChargerLoad()` (Gen2), each Gen3 unit's `currentAmps` × its voltage, and each watched car's `actualCurrent` × `VehicleEndpoint.currentVoltage` while `situation == HOME_CHARGING`.
- Threshold watts = `max(emsNoiseWatts, carMinAmps × V × phases)` with `carMinAmps = 5 if phases < 3 else 1`, `V = config.defaultVoltage` (240), `phases = config.numberOfPhases` (1).
- On `"up"`: candidates are watched cars in `HOME_AWAKE`, `UNKNOWN` or whose presence is PRESUMED with `asleep(v)` not True, ordered HOME first; `readNow(vin, "load step up")` for the first, then the next only if the first's read did not report Charging (checked on the following pass). On `"down"`: `readNow` for each car in `HOME_CHARGING`. Debounce: no triggered read for a car within 300 s of its last triggered read.
- `check_green_energy()` calls `master.watch.loadSample()` after the EMS loop when `master.watch.settings()["emsTrigger"]`.
- Behaviour change (named): (h) a consumption step makes a read.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_step_held_for_two_samples_is_reported_once():
    s = LoadStep(1200.0)
    assert [s.sample(w, t) for t, w in enumerate([500, 500, 2000, 2000, 2000, 700, 700])] == [None, None, None, "up", None, None, "down"]

def test_a_dryer_with_no_awake_watched_car_triggers_no_read():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m); m.setConsumption("t", 500); w.loadSample()
    m.setConsumption("t", 2500); w.loadSample(); c.t += 30; w.loadSample(); w.pass_(); runPending(r.ble)
    assert reads.count == 0

def test_a_step_up_reads_the_awake_home_car_and_a_step_down_reads_the_charging_one():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); w.pass_(); runPending(r.ble)                # the wake event read
    reads = bleReads(m, charging="Charging", amps=20)
    m.setConsumption("t", 500); w.loadSample(); m.setConsumption("t", 5300); w.loadSample(); c.t += 30; w.loadSample()
    w.pass_(); runPending(r.ble); assert reads.count == 1 and situation(m, v) == HOME_CHARGING
    reads.charging = "Complete"
    m.setConsumption("t", 500); w.loadSample(); c.t += 30; w.loadSample(); w.pass_(); runPending(r.ble)
    assert reads.count == 2 and v.value("chargingState") == "Complete"

def test_known_draw_is_subtracted_only_when_configured():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 20, "TeslaBLE")
    w = Watch(m, clock=c); m.setConsumption("t", 6000)
    m.subtractChargerLoad = False; assert w.unexplainedWatts() == 6000
    m.subtractChargerLoad = True;  assert w.unexplainedWatts() == pytest.approx(6000 - 20 * 240)
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** `LoadStep`, `unexplainedWatts`, `loadSample`, and the `check_green_energy` call (guarded: `getattr(master, "watch", None)`).

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py lib/TWCManager/TWCManager.py tests/unit/test_watch_load_step.py
git commit -m "A consumption step makes the watch read the car that may have caused it"
```

---

### Task 8: Delete the polling the watch replaces; fold in the pre-command ping

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:144-145, 206-208, 1629-1646, 1815, 1876-1890`; `lib/TWCManager/Vehicle/HomeAssistant.py:542-557`; `lib/TWCManager/TWCMaster.py:462-480`; `lib/TWCManager/Vehicle/Reconcile/Run.py:150-163`; `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:35-50`; `lib/TWCManager/Vehicle/Watch.py` (`freshFor`)
- Test: `tests/unit/test_teslaapi_providers.py`, `tests/unit/test_teslaapi_registry.py`, `tests/unit/test_policy.py`, `tests/unit/test_watch.py`, `tests/unit/test_command_path_parity.py` (run, not edited)

**Interfaces:**
- `TeslaAPI`: `chargeUpdateInterval`, `lastChargeCheck`, `updateChargeAtHome` removed; `minBatteryLevelAtHome` and `numCarsAtHome` are pure registry reads; `update_vehicle_data` sets `car.statusDeferral = now + READ_MAX_AGE` after every successful read (one value) and `_TeslaAPIProvider.fetch` honours it as today; `is_far_from_home` stays (Task 6 uses it). `config.cloudUpdateInterval`, when present, logs once at INFO that it is ignored.
- `HomeAssistant`: `numCarsAtHome`/`minBatteryLevelAtHome` no longer call `updateChargeAtHome`; `updateChargeAtHome` stays as the watch's HA status job target (Task 4 calls `refresh_from_home_assistant` directly; delete `updateChargeAtHome` if nothing else calls it after this task: grep).
- `TWCMaster.updateChargeAtHome(self)` (the `checkCharge` task from `TWCSlave.py:678`, a power start): `for v in vehicles: if presence(self, v) == HOME: self.watch.readNow(v.vin, "power start")`; the TWC-named car on that slave included (it is drawing).
- `Run.runAttempt`: the pre-command ping's `known = asleep(vehicle, now - REACH_WINDOW)` becomes `asleep(vehicle, now - master.watch.freshFor(vehicle))` where `Watch.freshFor(v) -> float` returns the car's current Ring 1 cadence when the watch pinged it inside that window, else `REACH_WINDOW`. So a car the watch pinged 8 minutes ago on a 15-minute cadence is not pinged again before a command.
- Behaviour changes (named): (i) no 1800 s battery refresh; (j) one deferral value; (k) the pre-command ping defers to the watch's fresher answer.

- [ ] **Step 1: Write the failing tests**

```python
# test_teslaapi_registry.py
def test_min_battery_level_at_home_reads_the_registry_and_queues_nothing():
    m, api, v = listed()                                   # the file's fixture: a listed car at home
    v.observe("batteryLevel", 33, "TeslaBLE")
    m.queue_background_task = lambda *a, **k: pytest.fail("no checkCharge")
    assert api.minBatteryLevelAtHome == 33

def test_cloud_update_interval_is_ignored_with_one_log_line(caplog):
    m, api = apiWith(config={"cloudUpdateInterval": 600})
    assert "cloudUpdateInterval" in caplog.text and not hasattr(api, "chargeUpdateInterval")

# test_teslaapi_providers.py
def test_two_callers_inside_read_max_age_pay_once(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=HOME); attachFleet(m, v, car)
    v.read("batteryLevel", maxAge=READ_MAX_AGE); c.t += 100; v.read("chargingState", 0, force=True)
    assert paid(requests_mock)[0] == 1                      # the deferral dedupes the forced read inside 300 s
    c.t += 300; v.read("chargingState", 0, force=True); assert paid(requests_mock)[0] == 2

# test_watch.py
def test_a_power_start_asks_the_watch_to_read_every_home_car():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = m.watch = Watch(m, clock=c); w.pass_(); runPending(r.ble); reads = bleReads(m)
    m.updateChargeAtHome(); w.pass_(); runPending(r.ble); assert reads.count == 1

def test_the_pre_command_ping_trusts_a_watch_ping_inside_its_cadence():
    m, r, v, c = setup(ble=True); placeAt(m, v, HOME); w = m.watch = Watch(m, clock=c); pings = bleAnswers(m, asleep=False)
    w.pass_(); runPending(r.ble); assert pings.count == 1
    c.t += 480; m.desired.set(VIN, CHARGE_LIMIT, 70, "policy"); r.pass_(); runPending(r.ble)
    assert pings.count == 1                                  # no second ping before the command
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Delete and rewire** as the Interfaces block says. Grep scope for removed names, verbatim: `git grep -nwE 'chargeUpdateInterval|lastChargeCheck|cloudUpdateInterval' -- lib html tests/unit tests/integration tests/API docs`. Every hit is removed, rewritten, or (docs) updated in Task 10.

- [ ] **Step 4: Run the full suite, then the parity file alone and compare its paid counts with BASE.** Expected: all pass; **no parity count moves**. If one does, stop and report with the row.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/HomeAssistant.py lib/TWCManager/TWCMaster.py lib/TWCManager/Vehicle/Reconcile/Run.py lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py lib/TWCManager/Vehicle/Watch.py tests/unit
git commit -m "The watch replaces the deferral ladder and the half-hourly battery refresh"
```

---

### Task 9: Wiring: the tick, config, the Vehicles page

**Files:**
- Modify: `lib/TWCManager/TWCManager.py:795`, `lib/TWCManager/ControlTick.py:62-70`, `lib/TWCManager/Control/HTTPControl.py:388-420`, `lib/TWCManager/Control/themes/Default/vehicles.html.j2`
- Test: `tests/unit/test_control_tick.py` (exists: check; else create), `tests/unit/test_http_vehicles.py` (the Vehicles page tests from Phase 5; find by `grep -l "vehicles.html" tests/unit`)

**Interfaces:**
- `master.watch = Watch(master)` created in `TWCManager.py` right after `master.controlTick = ControlTick(master)` (`:795`), before the tick starts; `ControlTick.housekeeping` calls `self.master.watch.pass_()` under `_guarded("watch", ...)`; `watch.enabled` False (config) makes `pass_` a no-op and `notWatched` return `"disabled"`.
- Template global `watchLine(v) -> str`: `"Not watched: <why>"` or `"Watched: <last> <ageText(lastAt)>, next in <n> min; budget $<tokens>"`; one `<td>` on the Vehicles list after presence.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_tick_runs_the_watch_each_pass_and_a_watch_error_does_not_stop_distribution():
    m, s = make_master(); m.watch = Mock(); m.watch.pass_.side_effect = RuntimeError("boom")
    tick = ControlTick(m); m.config["config"]["fakeMaster"] = 1; m.controlPass = Mock()
    tick.pass_(); tick.pass_()
    assert m.controlPass.call_count == 2 and m.watch.pass_.call_count == 2

def test_the_vehicles_page_shows_the_watch_line(client):     # the Phase 5 page fixture
    m = client.master; v = m.vehicleRegistry.getOrCreate(VIN, "t")
    html = client.get("/vehicles")
    assert "Watched" in html or "Not watched" in html
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** the wiring, the template global and the cell. Settings: `config["watch"]` parsed once in `Watch.settings()` (Task 4); unknown keys ignored.

- [ ] **Step 4: Run the test files and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/TWCManager.py lib/TWCManager/ControlTick.py lib/TWCManager/Control/HTTPControl.py lib/TWCManager/Control/themes/Default/vehicles.html.j2 tests/unit
git commit -m "Run the watch on the control tick; show it on the Vehicles page"
```

---

### Task 10: Docs and changelog

**Files:**
- Modify: `docs/Settings.md`, `docs/PolicyCustomization.md`, `docs/modules/Vehicle_TeslaBLE.md`, `docs/modules/Vehicle_FleetTelemetryMQTT.md`, `CHANGELOG.md`

- [ ] **Step 1: `docs/Settings.md`:** a `### Vehicle watch` section after Vehicle Command Policy: who is watched (every car no TWC names and no live feed covers), the three rings in one paragraph each, the cadence table from the spec with the defaults from `DEFAULTS`, the budget (`monthlyBudgetUSD`, default $3 of the $10 credit that also covers commands, wakes and Fleet Telemetry), the EMS trigger, and the `watch` config keys. Note `cloudUpdateInterval` is ignored.
- [ ] **Step 2: `docs/PolicyCustomization.md`:** in the Charge Limits presence text, replace "no Tesla API read is made just to place a car" and the "a car charging away from a TWC ... is not watched ... a separate feature ... is planned" sentences with: status checks are free and never wake; reads happen on change; a car a feed or a TWC covers is not watched; see Settings.
- [ ] **Step 3: `docs/modules/Vehicle_TeslaBLE.md`:** the sleep-safe check paragraph gains: it needs no pairing, and while the car is awake it also reports whether the charge-port door is open; a closed door counts as unplugged, an open one is confirmed by a charge read.
- [ ] **Step 4: `docs/modules/Vehicle_FleetTelemetryMQTT.md`:** one paragraph recommending `minimum_delta` for `ChargerVoltage`, `ACChargingPower` and `BatteryLevel` (values whose small changes nothing needs), with the Fleet Telemetry price ($1 per 150k values) and a note that the watch covers the car while the feed is down.
- [ ] **Step 5: `CHANGELOG.md`** under v1.4.0 Features (or the next version if 1.4.0 is tagged; ask): one entry for the watch (what it does, cadences, budget, EMS trigger), one for the charge-port door and keyless ping, one under Architecture for the removal of `cloudUpdateInterval`, the deferral ladder and the half-hourly battery refresh.
- [ ] **Step 6: Commit**

```bash
git add docs CHANGELOG.md
git commit -m "Document the vehicle watch"
```

---

### Task 11: Live run on the box

- [ ] **Step 1:** Deploy branch `deploy/phase6-live` to the box per the memory notes (bundle, `git checkout --detach`, restart; record the rollback commit). Config: `watch` absent (defaults).
- [ ] **Step 2:** Watch `journalctl -u twcmanager` and `~/twc-events/events.log` for: one ping per 15 min while the car sleeps at the TWC (the car is TWC-named: expect **no** pings, only the Vehicles page "Not watched: named by TWC 8244"); after an unplug and a drive off, pings/scans at the away cadence; on return, a scan hit, a ping, the arrival read; the midnight scheduled charge (TWC-named: a read while current flows every 5 min, zero paid calls).
- [ ] **Step 3:** Stop `teslamate-tunnel.service` for an hour with the car home and unplugged: the watch must take over (pings at the home-awake or home-asleep cadence), then stop when the tunnel returns.
- [ ] **Step 4:** Report counts: pings, scans, reads, paid requests (the INFO lines log each paid request), and any traceback. Zero paid requests is the expected result on this box (BLE and TeslaMate).
