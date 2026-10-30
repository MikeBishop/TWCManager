# Vehicle Model Phase 0 + 1: Foundations, Registry and Reads — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `VehicleRegistry` of `Vehicle` objects (VIN or anonymous plug-session identity) holding every per-vehicle field as value/source/time, fed by TeslaAPI, TeslaBLE, TeslaMate/Fleet telemetry, HomeAssistant and the Gen2 TWC, read through `read(field, maxAge, allowWake=False)` that never wakes a car unless asked, shown on a read-only Vehicles list; plus the Phase 0 foundations (per-VIN command queue keys, a settings lock).

**Architecture:** A new package `lib/TWCManager/Vehicle/Registry/` (field store, `Vehicle`, read-source cascade, `VehicleRegistry`) owned by `TWCMaster` (`master.vehicleRegistry`), persisted under `settings["vehicleRegistry"]`. Existing modules keep sending commands exactly as today; they only change where they *write and read vehicle state*: `CarApiVehicle` keeps its attribute API but its fields become descriptors over its registry `Vehicle`; Telemetry, HomeAssistant and TeslaBLE write observations and claims into the registry; callers that today reach for `getModuleByName("TeslaAPI").getCarApiVehicles()` ask the registry. No desired state, reconcilers, lanes, provider ordering by cost, or control tick — those are Phases 2–4.

**Tech Stack:** Python 3.8+ (CI matrix 3.8–3.11), `threading` locks, `jinja2` templates, `pytest` (`tests/unit`), `bluetoothctl` (BlueZ 5.82 on the user's box) for the BLE range scan, `tesla-control` for BLE.

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (sections "Registry and vehicle lifecycle", "Fields and reads", "Threading", "Vehicles tab"). Roadmap: `.superpowers/plans/2026-10-13-vehicle-model-roadmap.md` (Phase 0 and Phase 1 rows). Inventory: `.superpowers/gut-inventory.md`.

**Branch:** new branch off `origin/main` (`eb457dc`), e.g. `git switch -c vehicle-model/1-registry origin/main`. Target repo: `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`.

## Global Constraints

- Nothing blocks or delays the RS-485 heartbeat loop: registry calls made from the serial thread (`TWCMaster.num_cars_charging_now`, `recordVehicleVIN`, `TWCSlave`) are dict operations under short locks; `Vehicle.read()` (which may do I/O) is never called from the serial thread or an MQTT callback thread.
- Lock order: `TeslaBLE._bleLock` → `master.settingsLock` → `VehicleRegistry._lock` → `Vehicle._lock`. Registry and vehicle locks are leaves: never call a module, take `_bleLock`, or do I/O while holding one. No lock is held across I/O (the read cascade releases locks before calling a source; `saveSettings` serialises under the lock and writes outside it).
- `config.json` and `settings.json` stay backward compatible: no existing key changes meaning; new keys are optional (`vehicle.forgetAfterDays`, `settings["vehicleRegistry"]`, `settings["Vehicles"][vin]["ble"]`); an old `settings.json` without them loads unchanged.
- Python 3.8 syntax floor: no `X | Y` unions, no `dataclass(slots=True)`, no `match`; use `typing.Optional/Dict/List`.
- `black` only on files you touched (`black <file>`); the repo venv's black reformats untouched files, so never run `black .`.
- Tests: `python -m pytest tests/unit -q` must pass after every task.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (the two cherry-picked commits in Task 1 keep their original trailer; do not amend them).
- No log line may contain a token (access, refresh, HA long-lived, BLE private key).
- `settings["Vehicles"]` (charge sessions, kWh, BLE keys) is session history / key storage, never registry membership: session stats never create or keep a vehicle. The one reader is TeslaBLE's `updateSettings` (Task 13), which turns stored BLE keys into claims (ruling P9).
- Docker `:latest` tracks main: every task leaves a pure-Gen2 install working (no Vehicle module loaded).

## Review Focus

1. A TWC VIN mis-heard by one character between the two confirmation queries (`5YJ...001` then `5YJ...00I`): no vehicle is created, no `settings["Vehicles"]` history entry is added, the re-query is bounded (3 attempts) and the TWC's `currentVIN`/entitlement path keeps working. Test in Task 7.
2. The TeslaAPI module absent or disabled (BLE-only / pure-Gen2 install): every web page still renders (today `HTTPControl` does `master.getModuleByName("TeslaAPI").getCarApiVehicles` → `AttributeError` on `None`), the registry still fills from the TWC. Tests in Task 15 (no caller outside TeslaAPI's own consumers reaches for its list) and Task 7 (`TWCMaster` with no modules).
3. An old `settings.json` with no `vehicleRegistry` key, or a corrupt one (not a dict): the registry starts empty, nothing raises, the next save writes a valid key. Test in Task 8.
4. A telemetry message for a car the registry does not hold and cannot identify (TeslaMate without DB credentials, no cloud list): events are parked in `unknownVehicles`, retried, and never raise on the MQTT thread. Test in Task 11.
5. The per-car page for a VIN with no `settings["Vehicles"]` history (manually added, or seen only by telemetry) renders; today `vehicleDetail.html.j2` indexes `settings["Vehicles"][vin]["chargeSessions"]` unguarded. Test in Task 17.

---

## File structure

Created:
- `lib/TWCManager/Vehicle/Registry/__init__.py` — re-exports `Observation`, `FIELDS`, `Vehicle`, `VehicleRegistry`, `ReadSource`, `isWellFormedVIN`.
- `lib/TWCManager/Vehicle/Registry/Fields.py` — `Observation`, `FIELDS`, `TELEMETRY_SOURCES`, `FieldStore` (per-vehicle value/source/time store with own-write stamps).
- `lib/TWCManager/Vehicle/Registry/VIN.py` — `isWellFormedVIN`.
- `lib/TWCManager/Vehicle/Registry/Vehicle.py` — `Claim`, `Vehicle` (identity, tier, claims, attachments, `read`).
- `lib/TWCManager/Vehicle/Registry/ReadSource.py` — `ReadSource` base class and `cascade()`.
- `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py` — `VehicleRegistry` (membership, plug sessions, TWC VIN confirmation, forgetting, persistence, summaries).
- `lib/TWCManager/Vehicle/Registry/Sources.py` — `TeslaBLEReadSource`, `TeslaAPIReadSource`, `HomeAssistantReadSource` (thin adapters over existing module methods).
- Tests: `tests/unit/test_registry_fields.py`, `test_registry_vehicle.py`, `test_registry_read_cascade.py`, `test_registry_membership.py`, `test_registry_plug_sessions.py`, `test_twcmaster_vin_confirmation.py`, `test_twcmaster_registry.py`, `test_settings_lock.py`, `test_carapivehicle_registry.py`, `test_reads_no_wake.py`, `test_telemetry_registry.py`, `test_homeassistant_registry.py`, `test_teslable_pairing_status.py`, `test_own_write_stamps.py`, `test_registry_callers.py`, `test_vehicles_page.py`, `test_vehicle_detail_page.py`.

Modified:
- `lib/TWCManager/VehicleCommandQueue.py`, `lib/TWCManager/TWCMaster.py` (Task 1 cherry-pick; Task 2 lock; Tasks 7–8 registry hooks).
- `lib/TWCManager/TWCManager.py` (background task handlers `expireVehicles`, `bleScan`; hourly `expireVehicles` queue). Not touched by this phase (deferred): TWC-observed `actualCurrent` into the registry (charging points, Phase 2), the Forget action and provider panels (Phase 6), presence (Phase 5).
- `lib/TWCManager/Vehicle/TeslaAPI.py` (`CarApiVehicle` descriptors, no wake-on-read, read sources, stamps).
- `lib/TWCManager/Vehicle/Telemetry.py`, `TeslaMateVehicle.py`, `FleetTelemetryMQTT.py` (registry attach, field names, DB VIN lookup).
- `lib/TWCManager/Vehicle/HomeAssistant.py` (registry attach/claim/observe, stamps).
- `lib/TWCManager/Vehicle/TeslaBLE.py` (pairing status, proof/refusal, range scan, claims, stamps).
- `lib/TWCManager/Policy/Policy.py`, `lib/TWCManager/TWCSlave.py`, `lib/TWCManager/Control/WebIPCControl.py`, `lib/TWCManager/Control/HTTPControl.py` (callers → registry; `/vehicle/add`; `/vehicle/localMgmt` scan op).
- `lib/TWCManager/Control/themes/Default/vehicles.html.j2`, `vehicleDetail.html.j2`, `settings.html.j2`, `debug.html.j2`.
- `CHANGELOG.md`.

---

## Phase 0

### Task 1: Cherry-pick the per-VIN command queue (`presence/1-command-queue`)

**Files:**
- Modify (by cherry-pick): `lib/TWCManager/VehicleCommandQueue.py`, `lib/TWCManager/TWCMaster.py:166-168` (`cancelStopCarsCharging`), `:1889-1925` (`startCarsCharging`/`stopCarsCharging`), `tests/unit/test_vehicle_command_queue.py`, `tests/unit/test_twcmaster.py`.
- Modify: `CHANGELOG.md` (v1.4.0 Bugfixes).

**Interfaces:**
- Produces: `VehicleCommandQueue.cancel(cmd: str, match: Callable[[dict], bool]) -> int`; queue keys `(cmd, task.get("vin"))` for `charge`/`applyChargeLimit`, `(cmd, vehicle.VIN)` for `setChargeRate`; `TWCMaster.cancelStopCarsCharging(vin=None) -> int`; `startCarsCharging(vin)` now passes `vin` into the `charge` task in stop mode 1 (TeslaAPI.car_api_charge already honours `task["vin"]`).

- [ ] **Step 1: Confirm the picks are conflict-free against main**

Run (read-only simulations; both must print only a tree id, no `CONFLICT` lines):
```bash
git merge-tree --write-tree --merge-base=cbd5952^ origin/main cbd5952
C=$(git commit-tree $(git merge-tree --write-tree --merge-base=cbd5952^ origin/main cbd5952) -p origin/main -m sim)
git merge-tree --write-tree --merge-base=cbd5952 $C ce9df78
```
Expected conflicts: none (verified 2026-10-13: trees `a1a8107…` and `545831c…`). `origin/main:lib/TWCManager/VehicleCommandQueue.py` is byte-identical to the first commit's parent (`1d41869`).

- [ ] **Step 2: Cherry-pick**

```bash
git cherry-pick -x cbd5952 ce9df78
```

- [ ] **Step 3: Run the suite**

Run: `python -m pytest tests/unit -q`
Expected: all pass (the picked commits replace `test_stop_replaces_pending_vehicleless_start`/`test_start_replaces_pending_stop` with `TestKeying`/`TestCancel`).

- [ ] **Step 4: Changelog and commit**

Add under `## v1.4.0 - Upcoming` → `* Bugfixes`:
`    * (@MikeBishop) - Queue vehicle commands per VIN and really cancel pending stop-charging commands when charging resumes (closes #667)`

```bash
git add CHANGELOG.md
git commit -m "Add changelog entry for per-VIN vehicle command queue (#667)"
```

### Task 2: A lock for `settings`

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py:93-110` (`__init__`), `:1010-1125` (`loadSettings`), `:1521-1580` (`saveSettings`), `:1582-1601` (`getSetting`/`setSetting`), and every `TWCMaster` method that assigns into `self.settings` and is called off the serial thread: `saveNormalChargeLimit`, `removeNormalChargeLimit`, `setChargeNowAmps`, `resetChargeNowAmps`, `setChargeNowTimeEnd`, `setHomeLat`, `setHomeLon`, `setHourResumeTrackGreenEnergy`, `setkWhDelivered`, `setNonScheduledAmpsMax`, `setSendServerTime`, `setScheduledAmps*`, `snapHistoryData`, `setConsumptionOffset`-style helpers if any; `lib/TWCManager/Control/HTTPControl.py` direct writes at `:316, :513-514, :624, :809, :884-885, :923, :1318-1325, :1452-1470, :1611-1612, :1640-1710, :1763-1804`; `lib/TWCManager/Control/MQTTControl.py:178` (`nonScheduledAction`, MQTT thread); `lib/TWCManager/TWCManager.py:585-631` (`update_sunrise_sunset`); `lib/TWCManager/Vehicle/TeslaBLE.py:851-896` (`scanForVehicles` key generation). (Line numbers are `origin/main`'s; after Task 1, `TWCMaster.py` lines from `:166` on sit about 9 lines lower.)
- Test: `tests/unit/test_settings_lock.py`.

**Interfaces:**
- Produces: `TWCMaster.settingsLock: threading.RLock` (created in `__init__` before `self.settings`). Coverage rule (ruling 3): every writer that mutates `master.settings` from a non-serial thread (HTTP request threads, the background thread, the vehicle command worker, BLE/MQTT callbacks) wraps its mutation in `with master.settingsLock:`; single-key reads stay unlocked; serial-thread writers (`num_cars_charging_now`, `recordVehicleSessionEnd`, `stopCarsCharging`'s `respondToSlaves`) are left as they are. `saveSettings` serialises under the lock and writes the file outside it; `loadSettings` reads and parses the file outside the lock and assigns/merges under it (ruling P5). Acceptance: `git grep -n "settings\[" lib/TWCManager/Control/HTTPControl.py lib/TWCManager/Control/MQTTControl.py lib/TWCManager/TWCManager.py lib/TWCManager/Vehicle/TeslaBLE.py` shows each assignment or `del` inside a `with master.settingsLock:` block.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_settings_lock.py
import json, threading
from unittest.mock import Mock, patch
from TWCManager.TWCMaster import TWCMaster

CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False,
          "treatGenerationAsGridDelivery": False, "wiringMaxAmpsAllTWCs": 80,
          "maxAmpsAllowedFromGrid": None, "settingsPath": None}}

class CountingLock:
    """A real RLock that counts context-manager entries (Mock cannot be used with `with`)."""
    def __init__(self): self._lock = threading.RLock(); self.enters = 0
    def __enter__(self): self.enters += 1; return self._lock.__enter__()
    def __exit__(self, *exc): return self._lock.__exit__(*exc)
    def _is_owned(self): return self._lock._is_owned()

def make(tmp_path):
    cfg = {"config": dict(CONFIG["config"], settingsPath=str(tmp_path))}
    m = TWCMaster("AB", cfg)
    api = Mock(); api.fleetSlot = Mock(accessToken="", refreshToken="", expireTime=0, source="pasted")
    api.ownerSlot = Mock(accessToken="", refreshToken="", expireTime=0, source="pasted")
    m.getModuleByName = Mock(side_effect=lambda n: api if n == "TeslaAPI" else None)
    return m

def test_settings_lock_is_reentrant(tmp_path):
    m = make(tmp_path)
    with m.settingsLock:
        with m.settingsLock:
            m.setSetting("x", 1)
    assert m.getSetting("x") == 1

def test_save_serialises_under_lock_and_writes_outside(tmp_path):
    m = make(tmp_path)
    seen = {}
    real_dumps = json.dumps
    def dumps(obj, *a, **k):
        seen["dumps_locked"] = m.settingsLock._is_owned()
        return real_dumps(obj, *a, **k)
    real_open = open
    def opener(path, *a, **k):
        if str(path).endswith(".tmp"):
            seen["write_locked"] = m.settingsLock._is_owned()
        return real_open(path, *a, **k)
    with patch("TWCManager.TWCMaster.json.dumps", dumps), patch("builtins.open", opener):
        m.saveSettings()
    assert seen == {"dumps_locked": True, "write_locked": False}
    assert json.load(open(tmp_path / "settings.json"))["chargeStopMode"] == "1"

def test_set_setting_takes_the_lock_and_get_does_not(tmp_path):
    m = make(tmp_path); m.settingsLock = CountingLock()
    m.setSetting("k", 2); assert m.getSetting("k") == 2
    assert m.settingsLock.enters == 1                      # reads stay unlocked (ruling 3 / P4)

def test_off_thread_master_writers_take_the_lock(tmp_path):
    m = make(tmp_path); m.queue_background_task = Mock(); m.settingsLock = CountingLock()
    m.saveNormalChargeLimit("V", 90, 80); m.removeNormalChargeLimit("V"); m.setChargeNowAmps(10); m.setHomeLat(1.0)
    assert m.settingsLock.enters == 4

def test_load_reads_file_outside_lock_and_assigns_under_it(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"chargeStopMode": "2"}))
    m = make(tmp_path); seen = {}
    real_open = open
    def opener(path, *a, **k):
        if str(path).endswith("settings.json"): seen["open_locked"] = m.settingsLock._is_owned()
        return real_open(path, *a, **k)
    with patch("builtins.open", opener):
        m.loadSettings()
    assert seen == {"open_locked": False} and m.settings["chargeStopMode"] == "2"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/unit/test_settings_lock.py -v`
Expected: FAIL with `AttributeError: 'TWCMaster' object has no attribute 'settingsLock'`.

- [ ] **Step 3: Implement**

In `TWCMaster.__init__`: `self.settingsLock = threading.RLock()` before `self.settings = {...}`. `saveSettings`: under `with self.settingsLock:` do step 1 (token merge) and `payload = json.dumps(self.settings)`; then outside the lock write `payload` to the temp file, fsync, backup, replace (keep the existing error handling). `loadSettings`: read and `json.load` the file (and the backup fallback) into a local outside the lock, then assign `self.settings` and merge defaults under `with self.settingsLock:`; step 2 (module fan-out) stays outside. `setSetting` and the `TWCMaster` writers listed in Files: `with self.settingsLock:`; `getSetting` stays unlocked. HTTPControl, MQTTControl, `update_sunrise_sunset` and `scanForVehicles`: wrap each listed assignment block in `with master.settingsLock:` (never around a call into another module).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_settings_lock.py tests/unit/test_twcmaster.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Add to CHANGELOG `* Architecture`: `    * (@MikeBishop) - Serialise settings.json saves under a settings lock so a save no longer races writers on other threads`.
```bash
black lib/TWCManager/TWCMaster.py lib/TWCManager/TWCManager.py lib/TWCManager/Control/HTTPControl.py lib/TWCManager/Control/MQTTControl.py lib/TWCManager/Vehicle/TeslaBLE.py
git add lib/TWCManager tests/unit/test_settings_lock.py CHANGELOG.md
git commit -m "Add a settings lock: off-thread writers take it, saves snapshot under it"
```

---

## Phase 1

### Task 3: Field store with value/source/time and own-write stamps

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/__init__.py`, `lib/TWCManager/Vehicle/Registry/Fields.py`.
- Test: `tests/unit/test_registry_fields.py`.

**Interfaces:**
- Produces (`Fields.py`):
  - `class Observation(NamedTuple): value: Any; source: str; at: float`
  - `FIELDS = ("name", "batteryLevel", "chargeLimit", "chargingState", "pluggedIn", "state", "lat", "lon", "gpsAsOf", "actualCurrent", "availableCurrent", "voltage", "phases", "timeToFullCharge", "scheduledChargingPending", "twcVin", "bleReach")` (`state` holds the TeslaMate-style strings `asleep|offline|online|charging|updating|driving`).
  - `TELEMETRY_SOURCES = frozenset({"TeslaMateVehicle", "FleetTelemetryMQTT"})` (source names are the module class names; used by `CarApiVehicle.syncSource`/`is_awake`). A source is **report-on-change** (publishes a value only when it changes, so an old value can still be current while the feed is healthy) exactly when it has registered liveness with the registry (Task 6); the field store itself only sees the `liveAt` argument.
  - `FEED_LAG = 30.0` seconds: how long a healthy report-on-change feed is given to report a change after one of our own writes before its silence counts as "the write did not land" (TeslaMate polls an awake car every few seconds; 30 s is a safe margin).
  - `class FieldStore:` `__init__(self, clock: Callable[[], float] = time.time)`; `observe(field, value, source, at=None) -> Observation` (raises `KeyError` for a field not in `FIELDS`; `at` is when the value was reported, i.e. `valueChangedAt` for a report-on-change source); `latest(field) -> Optional[Observation]`; `NOT_TRACKED = object()` sentinel; `age(field, now=None, liveAt=NOT_TRACKED) -> Optional[float]`: `liveAt` is the feed's liveness evidence for the observation's source — `NOT_TRACKED` for a polled source (age is `now - obs.at`), `None` for a report-on-change feed that is unhealthy (also `now - obs.at`), a timestamp for a healthy one (`now - max(obs.at, liveAt)`); `noteWrite(field, value, source, at=None) -> Observation`; `lastWrite(field) -> Optional[Observation]`; `fresherThanWrite(field) -> bool` (True when there is no write, or `latest.at > lastWrite.at` — strictly newer; an observation stamped at the same instant as our write is not trusted over it, ruling P1); `trusted(field, now=None, liveAt=NOT_TRACKED) -> Optional[Observation]`: the latest observation when `fresherThanWrite`, or when its feed is healthy (`liveAt` is a timestamp) and `now - lastWrite.at > FEED_LAG` (the feed had time to report a change and did not); otherwise `None` (an apply must use our written value; a restore forces a live read, Phase 3 rules); `snapshot() -> Dict[str, Observation]`. Internal `threading.Lock` (not reentrant: nothing may call back into the store while it is held).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_fields.py
import pytest
from TWCManager.Vehicle.Registry.Fields import FieldStore, Observation, FIELDS

class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_observe_and_latest_carry_value_source_time():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 80, "TeslaBLE")
    assert s.latest("chargeLimit") == Observation(80, "TeslaBLE", 1000.0)
    assert s.latest("batteryLevel") is None

def test_age_uses_clock():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("batteryLevel", 50, "TeslaAPI"); c.t = 1030.0
    assert s.age("batteryLevel") == 30.0
    assert s.age("lat") is None

def test_unknown_field_rejected():
    with pytest.raises(KeyError):
        FieldStore().observe("notAField", 1, "x")

def test_own_write_stamp_and_freshness():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 80, "TeslaMateVehicle", at=900.0)
    assert s.fresherThanWrite("chargeLimit") is True          # no write yet
    s.noteWrite("chargeLimit", 70, "TeslaBLE")                 # at 1000
    assert s.lastWrite("chargeLimit") == Observation(70, "TeslaBLE", 1000.0)
    assert s.fresherThanWrite("chargeLimit") is False          # stored 900 < write 1000
    s.observe("chargeLimit", 70, "TeslaMateVehicle", at=1000.0)
    assert s.fresherThanWrite("chargeLimit") is False          # same instant: not fresher (P1)
    s.observe("chargeLimit", 70, "TeslaMateVehicle", at=1000.5)
    assert s.fresherThanWrite("chargeLimit") is True

def test_snapshot_is_a_copy():
    s = FieldStore(); s.observe("lat", 1.0, "TeslaAPI")
    snap = s.snapshot(); s.observe("lat", 2.0, "TeslaAPI")
    assert snap["lat"].value == 1.0 and set(snap) == {"lat"}

def test_report_on_change_age_counts_from_feed_liveness():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 50, "TeslaMateVehicle", at=100.0)   # old value, still current
    assert s.age("chargeLimit", liveAt=990.0) == 10.0            # healthy feed: age from liveness
    assert s.age("chargeLimit", liveAt=None) == 900.0            # unhealthy feed: age from the change
    s.observe("batteryLevel", 50, "TeslaAPI", at=100.0)
    assert s.age("batteryLevel") == 900.0                        # polled source: NOT_TRACKED

def test_trusted_after_own_write_waits_for_feed_lag():          # the 2026-10-12 09:17 shape
    c = Clock(t=1000.0); s = FieldStore(clock=c)
    s.observe("chargeLimit", 50, "TeslaMateVehicle", at=900.0)
    s.noteWrite("chargeLimit", 100, "TeslaBLE")                  # written at t=1000
    c.t = 1003.0
    assert s.trusted("chargeLimit", liveAt=1003.0) is None       # too soon: use our written 100
    c.t = 1000.0 + FEED_LAG + 1
    assert s.trusted("chargeLimit", liveAt=c.t).value == 50      # feed healthy, no change event: our write did not land
    assert s.trusted("chargeLimit", liveAt=None) is None         # unhealthy feed proves nothing
    s.observe("chargeLimit", 100, "TeslaMateVehicle")            # change event arrives
    assert s.trusted("chargeLimit", liveAt=c.t).value == 100
```
(`FEED_LAG` joins the imports.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_registry_fields.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Registry'`.

- [ ] **Step 3: Implement `Fields.py` and the package `__init__.py`** per the Interfaces block (the `__init__` re-exports grow in later tasks).

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_registry_fields.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_fields.py
git commit -m "Add the vehicle field store: value, source and time per field with own-write stamps"
```

### Task 4: `Vehicle`: identity, claims, tier, attachments, summary

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/VIN.py`, `lib/TWCManager/Vehicle/Registry/Vehicle.py`.
- Test: `tests/unit/test_registry_vehicle.py`.

**Interfaces:**
- Consumes: `FieldStore`, `Observation`, `FIELDS` (Task 3).
- Produces:
  - `VIN.py`: `WELL_FORMED = re.compile(r"[A-HJ-NPR-Z0-9]{17}")`; `isWellFormedVIN(vin: str) -> bool` (upper-cases first).
  - `Vehicle.py`:
    - `class Claim:` fields `provider: str`, `canCommand: Union[bool, Callable[[], bool]]`, `status: str`, `since: float`; property `commands -> bool` (calls the callable).
    - `class Vehicle:` `__init__(self, key: str, vin: Optional[str], registry, clock=time.time, userAsserted=False)`; attributes `key`, `vin`, `isAnonymous` (`vin is None`), `userAsserted`, `firstSeen`, `lastSeen`, `lastSeenSource` (floats/str, set on creation to clock()/`"created"`), `_fields: FieldStore`; methods `observe(field, value, source, at=None, seen=True) -> Observation` (updates `lastSeen`/`lastSeenSource` when `seen`), `latest(field)`, `age(field)` and `trusted(field)` (both pass `liveAt=self._registry.sourceLiveAt(obs.source, self)` when a registry is attached, else `NOT_TRACKED`), `value(field, default=None)` (latest value or default; template-friendly, never fetches), `noteWrite(field, value, source)`, `fresherThanWrite(field)`, `read(field, maxAge, allowWake=False)` (Task 5), `claim(provider, canCommand, status="") -> Claim`, `dropClaim(provider) -> bool`, `claims -> Dict[str, Claim]` (copy), property `tier -> str` (`"managed"` if any claim `.commands` and not anonymous, else `"observed"`), `attach(name, obj)`, `attachment(name) -> Optional[Any]`, property `name -> str` (latest `"name"` value or `""`), `summary() -> dict` with keys `key, vin, name, anonymous, userAsserted, tier, claims` (list of `{provider, status, commands}`), `point` (anonymous: `key[5:]`; else latest `twcVin` value or `None`), `lastSeen, lastSeenAge` (`clock() - lastSeen`), `lastSeenSource, fields` (`{field: {"value", "source", "age"}}`).
    - Its own `threading.Lock` (`_lock`) for claims/attachments/lastSeen; the `FieldStore` keeps its own (`_lock`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_vehicle.py
from TWCManager.Vehicle.Registry.VIN import isWellFormedVIN
from TWCManager.Vehicle.Registry.Vehicle import Vehicle

VIN = "5YJ3E1EA1KF000001"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_vin_format():
    assert isWellFormedVIN(VIN) and isWellFormedVIN(VIN.lower())
    assert not isWellFormedVIN("5YJ3E1EA1KF00000I")   # I
    assert not isWellFormedVIN("5YJ3E1EA1KF0000011")  # 18 chars
    assert not isWellFormedVIN("")

def test_identity_and_tier_default_observed():
    v = Vehicle(VIN, VIN, registry=None)
    assert (v.key, v.vin, v.isAnonymous, v.tier) == (VIN, VIN, False, "observed")
    a = Vehicle("anon:1234", None, registry=None)
    assert a.isAnonymous and a.tier == "observed"

def test_commanding_claim_makes_managed_and_callable_is_live():
    flag = {"ro": True}
    v = Vehicle(VIN, VIN, registry=None)
    v.claim("TeslaAPI", lambda: not flag["ro"], "listed")
    assert v.tier == "observed"
    flag["ro"] = False
    assert v.tier == "managed"
    assert v.dropClaim("TeslaAPI") is True and v.tier == "observed"
    assert v.dropClaim("TeslaAPI") is False

def test_anonymous_never_managed():
    a = Vehicle("anon:1234", None, registry=None)
    a.claim("TeslaBLE", True)
    assert a.tier == "observed"

def test_observe_bumps_last_seen_unless_told_not_to():
    c = Clock(); v = Vehicle(VIN, VIN, registry=None, clock=c)
    c.t = 2000.0; v.observe("chargeLimit", 80, "TeslaMateVehicle")
    assert (v.lastSeen, v.lastSeenSource) == (2000.0, "TeslaMateVehicle")
    c.t = 3000.0; v.observe("name", "Car", "TeslaAPI", seen=False)
    assert v.lastSeen == 2000.0 and v.name == "Car"

def test_attachments_and_summary():
    c = Clock(); v = Vehicle(VIN, VIN, registry=None, clock=c)
    obj = object(); v.attach("TeslaAPI", obj)
    assert v.attachment("TeslaAPI") is obj and v.attachment("HomeAssistant") is None
    v.claim("TeslaBLE", True, "paired"); v.observe("batteryLevel", 42, "TeslaBLE"); c.t = 1010.0
    s = v.summary()
    assert s["tier"] == "managed" and s["claims"] == [{"provider": "TeslaBLE", "status": "paired", "commands": True}]
    assert s["fields"]["batteryLevel"] == {"value": 42, "source": "TeslaBLE", "age": 10.0}
    assert s["lastSeenAge"] == 10.0 and s["point"] is None and Vehicle("anon:8244", None, registry=None).summary()["point"] == "8244"
    assert v.value("batteryLevel") == 42 and v.value("lon", 0) == 0
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/unit/test_registry_vehicle.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `VIN.py` and `Vehicle.py`** per Interfaces; `read()` is a stub raising `NotImplementedError` until Task 5.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_vehicle.py
git commit -m "Add registry Vehicle with VIN or anonymous identity, claims and tiers"
```

### Task 5: Read sources and the `read(field, maxAge, allowWake)` cascade

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/ReadSource.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`read`).
- Test: `tests/unit/test_registry_read_cascade.py`.

**Interfaces:**
- Produces:
  - `class ReadSource:` attributes `name: str`, `order: int` (0 local, 1 cloud; lower first — this is only a sequencing hint for Phase 1, not the Phase 2 cost model), `fields: FrozenSet[str]`; methods `canRead(self, vehicle) -> bool` (default True), `fetch(self, vehicle, field: str, allowWake: bool) -> Optional[Dict[str, Any]]` (abstract; returns observations to record keyed by field name, `{}` when the source wrote them itself, `None` on failure; must never wake unless `allowWake`).
  - `cascade(vehicle, sources, field, allowWake) -> Optional[Observation]`: for each source in order with `field in source.fields and source.canRead(vehicle)`: `result = source.fetch(...)` (no registry/vehicle lock held); if not None, `vehicle.observe(k, v, source.name)` for each item and return `vehicle.latest(field)`. Exceptions from `fetch` are logged at DEBUG and count as failure.
  - `Vehicle.read(field, maxAge: Optional[float], allowWake=False) -> Optional[Observation]`: if `maxAge is None` → `latest(field)` only (never fetches); if latest exists and `age <= maxAge` → return it; else `cascade(self, self._registry.readSources(), field, allowWake)`, falling back to `latest(field)` when every source fails (registry `None` → return latest). A `registry` passed to `Vehicle` must expose `readSources() -> List[ReadSource]` and `sourceLiveAt(source, vehicle)` (ruling P2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_read_cascade.py
from TWCManager.Vehicle.Registry.Fields import NOT_TRACKED
from TWCManager.Vehicle.Registry.ReadSource import ReadSource
from TWCManager.Vehicle.Registry.Vehicle import Vehicle

VIN = "5YJ3E1EA1KF000001"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

class Src(ReadSource):
    def __init__(self, name, order, result, fields=("chargeLimit", "batteryLevel")):
        self.name, self.order, self.fields = name, order, frozenset(fields)
        self.result, self.calls = result, []
    def fetch(self, vehicle, field, allowWake):
        self.calls.append((field, allowWake))
        assert not vehicle._fields._lock.locked() and not vehicle._lock.locked()
        return self.result

class Reg:
    def __init__(self, *sources): self.sources = list(sources)
    def readSources(self): return sorted(self.sources, key=lambda s: s.order)
    def sourceLiveAt(self, source, vehicle): return NOT_TRACKED   # polled sources only here

def test_fresh_value_returned_without_fetch():
    c = Clock(); src = Src("BLE", 0, {"chargeLimit": 90})
    v = Vehicle(VIN, VIN, Reg(src), clock=c); v.observe("chargeLimit", 80, "X"); c.t = 1010.0
    assert v.read("chargeLimit", maxAge=30).value == 80 and src.calls == []

def test_stale_value_cascades_in_order_and_stops_at_first_success():
    c = Clock(); ble = Src("BLE", 0, None); api = Src("API", 1, {"chargeLimit": 90, "batteryLevel": 55})
    v = Vehicle(VIN, VIN, Reg(api, ble), clock=c); v.observe("chargeLimit", 80, "X"); c.t = 1100.0
    obs = v.read("chargeLimit", maxAge=30)
    assert (obs.value, obs.source, obs.at) == (90, "API", 1100.0)
    assert v.latest("batteryLevel").value == 55
    assert ble.calls == [("chargeLimit", False)] and api.calls == [("chargeLimit", False)]

def test_allow_wake_is_passed_through_and_defaults_false():
    src = Src("BLE", 0, {"chargeLimit": 1}); v = Vehicle(VIN, VIN, Reg(src))
    v.read("chargeLimit", maxAge=0); v.read("chargeLimit", maxAge=0, allowWake=True)
    assert [w for _, w in src.calls] == [False, True]

def test_max_age_none_never_fetches():
    src = Src("BLE", 0, {"chargeLimit": 1}); v = Vehicle(VIN, VIN, Reg(src))
    assert v.read("chargeLimit", maxAge=None) is None and src.calls == []

def test_source_without_field_or_declining_is_skipped():
    loc = Src("LOC", 0, {"lat": 1.0}, fields=("lat", "lon"))
    shy = Src("SHY", 0, {"chargeLimit": 5}); shy.canRead = lambda vehicle: False
    v = Vehicle(VIN, VIN, Reg(loc, shy))
    assert v.read("chargeLimit", maxAge=0) is None and loc.calls == [] and shy.calls == []

def test_all_sources_fail_returns_stale_latest():
    c = Clock(); src = Src("BLE", 0, None); v = Vehicle(VIN, VIN, Reg(src), clock=c)
    v.observe("chargeLimit", 80, "X"); c.t = 5000.0
    assert v.read("chargeLimit", maxAge=1).value == 80
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `ReadSource`).

- [ ] **Step 3: Implement `ReadSource.py` and `Vehicle.read`** per Interfaces (`FieldStore` exposes its lock as `_lock` for the test's no-lock-across-I/O assertion).

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_read_cascade.py
git commit -m "Add read sources and the freshness-bounded read cascade that never wakes unasked"
```

### Task 6: `VehicleRegistry`: membership, forgetting, persistence, manual add

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/__init__.py`.
- Test: `tests/unit/test_registry_membership.py`.

**Interfaces:**
- Consumes: `Vehicle`, `isWellFormedVIN`, `ReadSource`.
- Produces `class VehicleRegistry:`
  - `DEFAULT_FORGET_DAYS = 30`; `__init__(self, config: dict, clock=time.time)`; `self.forgetAfter = config.get("vehicle", {}).get("forgetAfterDays", 30) * 86400`; `_lock = threading.RLock()`.
  - `@classmethod forMaster(cls, master) -> VehicleRegistry`: `master.vehicleRegistry` when it is a `VehicleRegistry`, else a private `VehicleRegistry(getattr(master, "config", {}) or {})` (so tests with `Mock()` masters keep working).
  - `getOrCreate(vin: str, source: str) -> Vehicle` (upper-cases; no format check: provider lists are trusted; creation logs INFO `Vehicle <vin> added (<source>)`); `get(key) -> Optional[Vehicle]`; `vehicles() -> List[Vehicle]` sorted by key; `findByName(name) -> Optional[Vehicle]`; `attached(name) -> List[Any]` (attachments of that name over `vehicles()`); `addUserAsserted(vin) -> Vehicle` (raises `ValueError("VIN must be 17 characters without I, O or Q")` when not well-formed; existing vehicle → returned with `userAsserted=True`); `forget(key) -> bool`; `expire(now=None) -> List[str]` (removes non-anonymous vehicles with no claims at all — a provider that still lists the car keeps it, ruling 4 — `not userAsserted` (ruling 5), and `now - lastSeen > forgetAfter`; logs INFO per removal); `registerReadSource(source)`, `readSources()` (sorted by `(order, registration index)`); `registerLiveness(source: str, liveAt: Callable[[Vehicle], Optional[float]])` and `sourceLiveAt(source, vehicle)` (calls the registered callable with the vehicle — a timestamp when that car's feed is healthy, `None` when not — and returns `Fields.NOT_TRACKED` for an unregistered source, so registering liveness is what makes a source report-on-change). Vehicles are created with the registry's `clock`. `load()` records persisted names as observations with source `"persisted"`, `seen=False`.
  - Persistence: `toJSON() -> dict` = `{"version": 1, "vehicles": {vin: {"name", "firstSeen", "lastSeen", "lastSeenSource", "userAsserted"}}}` (anonymous vehicles omitted); `load(data) -> None` merges (keeps existing vehicles, takes the older `firstSeen` and newer `lastSeen`); ignores non-dict input and malformed entries without raising.
  - `summaries() -> List[dict]` = `[v.summary() for v in vehicles()]`.
  - Plug sessions and TWC confirmation: Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_membership.py
import pytest
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.Fields import NOT_TRACKED
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry

VIN = "5YJ3E1EA1KF000001"; VIN2 = "5YJ3E1EA1KF000002"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_get_or_create_is_idempotent_and_uppercases():
    r = VehicleRegistry({})
    a = r.getOrCreate(VIN.lower(), "TeslaAPI"); b = r.getOrCreate(VIN, "TeslaBLE")
    assert a is b and a.vin == VIN and [v.key for v in r.vehicles()] == [VIN]

def test_for_master_prefers_real_registry_else_private():
    real = VehicleRegistry({}); m = Mock(); m.vehicleRegistry = real
    assert VehicleRegistry.forMaster(m) is real
    m2 = Mock(); m2.config = {"config": {}}
    assert isinstance(VehicleRegistry.forMaster(m2), VehicleRegistry)

def test_user_asserted_add_validates_format():
    r = VehicleRegistry({})
    with pytest.raises(ValueError):
        r.addUserAsserted("5YJ3E1EA1KF00000I")
    v = r.addUserAsserted(VIN)
    assert v.userAsserted and v.tier == "observed"
    assert r.addUserAsserted(VIN) is v

def test_expire_forgets_unclaimed_after_default_30_days_but_not_claimed_or_asserted():
    c = Clock(); r = VehicleRegistry({}, clock=c)
    r.getOrCreate(VIN, "TWC"); r.getOrCreate(VIN2, "TeslaBLE").claim("TeslaBLE", True)
    r.addUserAsserted("5YJ3E1EA1KF000003")
    r.getOrCreate("5YJ3E1EA1KF000004", "TeslaAPI").claim("TeslaAPI", False, "listed")   # read-only cloud listing
    c.t = 1000.0 + 29 * 86400
    assert r.expire() == []
    c.t = 1000.0 + 31 * 86400
    assert r.expire() == [VIN]
    assert [v.key for v in r.vehicles()] == [VIN2, "5YJ3E1EA1KF000003", "5YJ3E1EA1KF000004"]
    r.get("5YJ3E1EA1KF000004").dropClaim("TeslaAPI"); c.t += 31 * 86400
    assert r.expire() == ["5YJ3E1EA1KF000004"]                                           # lost its last listing

def test_forget_days_configurable():
    c = Clock(); r = VehicleRegistry({"vehicle": {"forgetAfterDays": 1}}, clock=c)
    r.getOrCreate(VIN, "TWC"); c.t = 1000.0 + 2 * 86400
    assert r.expire() == [VIN]

def test_persistence_round_trip_and_merge():
    c = Clock(); r = VehicleRegistry({}, clock=c)
    v = r.getOrCreate(VIN, "TWC"); v.observe("name", "Car", "TeslaAPI"); c.t = 2000.0
    v.observe("chargeLimit", 80, "TeslaBLE")
    data = r.toJSON()
    assert data["vehicles"][VIN] == {"name": "Car", "firstSeen": 1000.0, "lastSeen": 2000.0,
                                     "lastSeenSource": "TeslaBLE", "userAsserted": False}
    r2 = VehicleRegistry({}, clock=Clock(3000.0)); r2.getOrCreate(VIN, "TeslaAPI"); r2.load(data)
    w = r2.get(VIN)
    assert (w.firstSeen, w.lastSeen, w.name) == (1000.0, 3000.0, "Car")

@pytest.mark.parametrize("bad", [None, "x", 3, {"vehicles": "nope"}, {"vehicles": {VIN: "str"}}])
def test_load_ignores_garbage(bad):
    r = VehicleRegistry({}); r.load(bad)
    assert r.vehicles() == []

def test_liveness_feeds_vehicle_age_and_trust():
    c = Clock(); r = VehicleRegistry({}, clock=c); live = {"at": 990.0}
    r.registerLiveness("TeslaMateVehicle", lambda vehicle: live["at"] if vehicle.vin == VIN else None)
    v = r.getOrCreate(VIN, "TeslaMateVehicle"); v.observe("chargeLimit", 50, "TeslaMateVehicle", at=100.0)
    assert v.age("chargeLimit") == 10.0
    live["at"] = None
    assert v.age("chargeLimit") == 900.0 and r.sourceLiveAt("TeslaAPI", v) is NOT_TRACKED

def test_find_by_name_and_attached():
    r = VehicleRegistry({}); v = r.getOrCreate(VIN, "TeslaAPI"); v.observe("name", "<car>", "TeslaAPI")
    v.attach("TeslaAPI", "obj")
    assert r.findByName("<car>") is v and r.findByName("x") is None
    assert r.attached("TeslaAPI") == ["obj"] and r.attached("HomeAssistant") == []
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `VehicleRegistry.py`** per Interfaces; export from `__init__.py`.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_membership.py
git commit -m "Add VehicleRegistry with forgetting, persistence and user-asserted vehicles"
```

### Task 7: Anonymous plug-session vehicles and TWC VIN confirmation

On main a Gen2 "plug session" is the `isCharging` session in `TWCMaster.num_cars_charging_now` (≥ 1 A, 5 s debounce); plug detection proper arrives with Phase 5. The registry's plug-session API is keyed by a point id (the TWC id hex string) so Phase 2 charging points can reuse it.

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`; `lib/TWCManager/TWCMaster.py:1201-1262` (`num_cars_charging_now`), `:1405-1451` (`recordVehicleVIN`).
- Test: `tests/unit/test_registry_plug_sessions.py`, `tests/unit/test_twcmaster_vin_confirmation.py`.

**Interfaces:**
- Produces (`VehicleRegistry`):
  - `beginPlugSession(pointId: str) -> Vehicle`: creates/returns the anonymous vehicle `key="anon:<pointId>"` (`vin=None`); idempotent.
  - `endPlugSession(pointId) -> None`: removes the anonymous vehicle if still anonymous, clears any pending confirmation for the point, and for a VIN vehicle attributed to the point observes `twcVin=None` (source `"TWC"`, `seen=False`).
  - `observeTwcVin(pointId: str, vin: str) -> str`: returns `"rejected"` when `not isWellFormedVIN(vin)`; `"confirmed"` when `get(vin)` exists (known vehicle: one read suffices) or when the point's pending candidate equals `vin` — on confirmation the anonymous vehicle for the point is merged (its observations copied into `getOrCreate(vin, "TWC")`, then removed) and `twcVin=pointId` is observed (source `"TWC"`); `"pending"` on the first sighting of an unknown VIN (or a different candidate, which replaces the pending one) with attempts counted; `"rejected"` after `CONFIRM_ATTEMPTS = 3` reads without two consecutive matches (INFO log `TWC <point> VIN <vin> not confirmed; ignoring`).
  - `CONFIRM_ATTEMPTS = 3`; `pointFor(vin) -> Optional[str]` (latest `twcVin` value); `vehicleAt(pointId) -> Optional[Vehicle]` (the VIN vehicle attributed to the point, else the anonymous one, else None).
- Produces (`TWCMaster`): `recordVehicleVIN(slaveTWC)` now: `status = self.vehicleRegistry.observeTwcVin(twcid, slaveTWC.currentVIN)`; on `"pending"` → `self.queue_background_task({"cmd": "getVehicleVIN", "slaveTWC": slaveTWC.TWCID, "vinPart": 0}, delay=5)` and return; on `"rejected"` → return; on `"confirmed"` → the existing `SlaveTWCs.supportsVINQuery` and `settings["Vehicles"]` session bookkeeping (under `with self.settingsLock:`; the `else` branch uses `.get("chargeSessions", 0) + 1` and `.setdefault("totalkWh", 0)` because Tasks 13 and 16 may create an entry without session counters), log, and `vehicleIsDefinitelyHome` exactly as today. `num_cars_charging_now`: `self.vehicleRegistry.beginPlugSession(twcid)` where `isCharging` flips to 1 and `endPlugSession(twcid)` where it flips to 0 (`twcid = "%02X%02X" % (slaveTWC.TWCID[0], slaveTWC.TWCID[1])`). `slaveTWC.currentVIN` is still set by the RX loop on the first valid parse (entitlement, `getTWCbyVIN`, status and `_twcServedVINs` are unchanged); only registry creation and history bookkeeping wait for confirmation. `TWCMaster.__init__` gains `self.vehicleRegistry = VehicleRegistry(config)` (Task 8 adds persistence).

- [ ] **Step 1: Write the failing registry tests**

```python
# tests/unit/test_registry_plug_sessions.py
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"; BAD = "5YJ3E1EA1KF00000I"; OTHER = "5YJ3E1EA1KF000002"

def test_anonymous_vehicle_lives_with_the_session():
    r = VehicleRegistry({})
    a = r.beginPlugSession("8244")
    assert a.key == "anon:8244" and a.isAnonymous and r.beginPlugSession("8244") is a
    assert r.vehicleAt("8244") is a
    r.endPlugSession("8244")
    assert r.vehicles() == [] and r.vehicleAt("8244") is None

def test_unknown_vin_needs_two_matching_reads_then_merges_anonymous():
    r = VehicleRegistry({}); a = r.beginPlugSession("8244"); a.observe("actualCurrent", 12, "TWC")
    assert r.observeTwcVin("8244", VIN) == "pending" and r.get(VIN) is None
    assert r.observeTwcVin("8244", VIN) == "confirmed"
    v = r.get(VIN)
    assert v is not None and r.get("anon:8244") is None
    assert v.latest("twcVin").value == "8244" and v.latest("actualCurrent").value == 12
    assert r.pointFor(VIN) == "8244" and r.vehicleAt("8244") is v

def test_known_vin_confirms_at_once():
    r = VehicleRegistry({}); r.getOrCreate(VIN, "TeslaAPI"); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "confirmed"

def test_misheard_vin_creates_nothing_and_is_bounded():   # Review Focus 1
    r = VehicleRegistry({}); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "pending"
    assert r.observeTwcVin("8244", OTHER) == "pending"     # differs: candidate replaced
    assert r.observeTwcVin("8244", VIN) == "rejected"      # third read, no two in a row
    assert r.get(VIN) is None and r.get(OTHER) is None
    assert r.observeTwcVin("8244", VIN) == "rejected"      # stays rejected this session

def test_malformed_vin_rejected_and_session_end_clears_pending():
    r = VehicleRegistry({}); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", BAD) == "rejected"
    assert r.observeTwcVin("8244", VIN) == "pending"
    r.endPlugSession("8244"); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "pending"       # fresh session, fresh count

def test_session_end_clears_twc_vin_on_the_car():
    r = VehicleRegistry({}); r.getOrCreate(VIN, "TeslaAPI"); r.beginPlugSession("8244")
    r.observeTwcVin("8244", VIN); r.endPlugSession("8244")
    assert r.get(VIN).latest("twcVin").value is None and r.pointFor(VIN) is None
```

- [ ] **Step 2: Write the failing TWCMaster tests**

```python
# tests/unit/test_twcmaster_vin_confirmation.py
from unittest.mock import Mock
import pytest
from TWCManager.TWCMaster import TWCMaster
VIN = "5YJ3E1EA1KF000001"
CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False,
          "treatGenerationAsGridDelivery": False, "wiringMaxAmpsAllTWCs": 80, "maxAmpsAllowedFromGrid": None}}

@pytest.fixture
def master():
    m = TWCMaster("AB", CONFIG); m.getModuleByName = Mock(return_value=None)
    m.queue_background_task = Mock(); m.getModulesByType = Mock(return_value=[])
    return m

def slave(vin):
    s = Mock(); s.TWCID = bytearray(b"\x82\x44"); s.currentVIN = vin; s.lifetimekWh = 100; return s

def test_first_sighting_requeries_and_records_nothing(master):
    master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN))
    master.queue_background_task.assert_called_once_with(
        {"cmd": "getVehicleVIN", "slaveTWC": bytearray(b"\x82\x44"), "vinPart": 0}, delay=5)
    assert "Vehicles" not in master.settings or VIN not in master.settings["Vehicles"]

def test_second_matching_sighting_records_one_session(master):
    master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN)); master.recordVehicleVIN(slave(VIN))
    assert master.settings["Vehicles"][VIN]["chargeSessions"] == 1
    assert master.settings["SlaveTWCs"]["8244"]["supportsVINQuery"] == 1
    assert master.vehicleRegistry.get(VIN).latest("twcVin").value == "8244"

def test_known_vehicle_records_on_first_sighting(master):
    master.vehicleRegistry.getOrCreate(VIN, "TeslaAPI"); master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN))
    assert master.settings["Vehicles"][VIN]["chargeSessions"] == 1
    assert not any(c.args[0]["cmd"] == "getVehicleVIN" for c in master.queue_background_task.call_args_list)

def test_charging_session_begins_and_ends_anonymous_vehicle(master):
    s = slave(""); s.reportedAmpsActual = 5.0; s.isCharging = 0; s.chargingDroppedBelowThresholdTime = 0
    master.getSlaveTWCs = Mock(return_value=[s])
    master.num_cars_charging_now()
    assert master.vehicleRegistry.get("anon:8244") is not None
    s.reportedAmpsActual = 0.0; s.chargingDroppedBelowThresholdTime = 1  # long ago
    master.num_cars_charging_now()
    assert master.vehicleRegistry.get("anon:8244") is None
```

- [ ] **Step 3: Run to verify failure** — both files → FAIL (`AttributeError: beginPlugSession` / `vehicleRegistry`).

- [ ] **Step 4: Implement** the registry methods, `TWCMaster.__init__` registry creation, and the `recordVehicleVIN`/`num_cars_charging_now` hooks per Interfaces. The confirmation state per point: `{"candidate": vin, "attempts": int, "rejected": bool}` under `_lock`.

- [ ] **Step 5: Run tests** — `python -m pytest tests/unit/test_registry_plug_sessions.py tests/unit/test_twcmaster_vin_confirmation.py tests/unit/test_twcmaster.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/ lib/TWCManager/TWCMaster.py
git add lib/TWCManager/Vehicle/Registry lib/TWCManager/TWCMaster.py tests/unit/test_registry_plug_sessions.py tests/unit/test_twcmaster_vin_confirmation.py
git commit -m "Confirm TWC-reported VINs by re-query and track anonymous plug-session vehicles"
```

### Task 8: Persist the registry in settings and forget on a timer

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py` (`loadSettings` step 2 area `:1125-1162`, `saveSettings` step 1, new `expireVehicles`); `lib/TWCManager/TWCManager.py:376-392` (`background_tasks_thread` `elif` chain), `:969-981` (hourly queue placed *after* the `fakeMaster == 1` `getLifetimekWh` block, next to `retryVINQuery`, so expiry is not gated on `fakeMaster`; ruling P16).
- Test: `tests/unit/test_twcmaster_registry.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.toJSON/load/expire` (Task 6), `master.settingsLock` (Task 2).
- Produces: `settings["vehicleRegistry"]` written by `saveSettings` (`self.settings["vehicleRegistry"] = self.vehicleRegistry.toJSON()` inside the locked step 1); `loadSettings` calls `self.vehicleRegistry.load(self.settings.get("vehicleRegistry"))` after the defaults merge, before module `updateSettings()`; `TWCMaster.expireVehicles() -> List[str]` = `self.vehicleRegistry.expire()` and, when non-empty, `queue_background_task({"cmd": "saveSettings"})`; `TWCManager.py` gets `elif task["cmd"] == "expireVehicles": master.expireVehicles()` (one line, untested like its siblings) and `TWCMaster.lastVehicleExpiry: float = 0` with the main loop queuing `{"cmd": "expireVehicles"}` when `time.time() - master.lastVehicleExpiry > 3600` (ungated by `fakeMaster`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_twcmaster_registry.py
import json
from unittest.mock import Mock
from TWCManager.TWCMaster import TWCMaster
from tests.unit.test_settings_lock import make   # fixture builder from Task 2
VIN = "5YJ3E1EA1KF000001"

def test_registry_round_trips_through_settings_file(tmp_path):   # Review Focus 3 (happy path)
    m = make(tmp_path); m.vehicleRegistry.getOrCreate(VIN, "TWC")
    m.saveSettings()
    assert VIN in json.load(open(tmp_path / "settings.json"))["vehicleRegistry"]["vehicles"]
    m2 = make(tmp_path); m2.loadSettings()
    assert m2.vehicleRegistry.get(VIN) is not None

def test_old_settings_without_registry_key_loads_empty(tmp_path):   # Review Focus 3
    (tmp_path / "settings.json").write_text(json.dumps({"chargeStopMode": "1"}))
    m = make(tmp_path); m.loadSettings()
    assert m.vehicleRegistry.vehicles() == []
    (tmp_path / "settings.json").write_text(json.dumps({"vehicleRegistry": "corrupt"}))
    m = make(tmp_path); m.loadSettings()
    assert m.vehicleRegistry.vehicles() == []

def test_expire_vehicles_saves_only_when_something_expired(tmp_path):
    m = make(tmp_path); m.queue_background_task = Mock()
    assert m.expireVehicles() == []
    m.queue_background_task.assert_not_called()
    m.vehicleRegistry.expire = Mock(return_value=[VIN])
    assert m.expireVehicles() == [VIN]
    m.queue_background_task.assert_called_once_with({"cmd": "saveSettings"})
```

- [ ] **Step 2: Run to verify failure** → FAIL (`KeyError: 'vehicleRegistry'` / `AttributeError: expireVehicles`).

- [ ] **Step 3: Implement** per Interfaces (`TWCManager.py` is a script that runs on import, so its two one-line changes are not unit-tested; keep every testable line in `TWCMaster`).

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_twcmaster_registry.py tests/unit/test_settings_lock.py tests/unit/test_twcmanager.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/TWCMaster.py lib/TWCManager/TWCManager.py
git add lib/TWCManager tests/unit/test_twcmaster_registry.py tests/unit/test_settings_lock.py
git commit -m "Persist the vehicle registry in settings.json and forget unseen vehicles hourly"
```

### Task 9: `CarApiVehicle` backed by the registry

Migration approach for `CarApiVehicle`: the class stays, every caller keeps `vehicle.batteryLevel`, `vehicle.VIN`, `vehicle.name` etc., but the per-vehicle *field* attributes become descriptors over `self.vehicle` (the registry `Vehicle`). Reads return the latest observation's value (or the legacy default); writes record an observation with source `"TeslaAPI"`. The per-vehicle `checkSyncNotStale` thread goes: "sync" is now "the latest observation's source and age". The `syncSource`/`syncTimestamp`/`syncState`/`syncLat`/`syncLon` names stay **assignable** in this task (their setters map onto observations, ruling P7) so that `Telemetry.py`, which still assigns them until Task 11, keeps working between the two tasks; Task 11 deletes the five. Command-dedupe flags (`stopAskingToStartCharging`, `stopTryingToApplyLimit`, `lastChargeRateSent`, wake timers, `atHome`, `statusDeferral`) stay plain attributes (Phase 3/5 remove them).

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:116-165` (`__init__`, `addVehicle`), `:1975-2120` (`CarApiVehicle` class attrs, `__init__`, `checkSyncNotStale`, `is_awake`), `:2424-2431` (`actualCurrent`).
- Modify tests that monkeypatch `teslaapi.Thread` (`tests/unit/test_teslaapi_charge_vin.py`, `tests/unit/teslatokens.py` `no_threads`, any other `grep -l '"Thread"' tests/unit`): drop the patch lines (the thread no longer exists).
- Test: `tests/unit/test_carapivehicle_registry.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.forMaster`, `Vehicle.observe/latest/age/claim/attach`, `TELEMETRY_SOURCES`.
- Produces:
  - `TeslaAPI.__init__`: `self.registry = VehicleRegistry.forMaster(master)`.
  - `class RegistryField:` descriptor in `TeslaAPI.py`: `RegistryField(field: str, default: Any, source="TeslaAPI")`; `__get__` → `instance.vehicle.latest(field).value` or `default`; `__set__` → `instance.vehicle.observe(field, value, source)`.
  - `CarApiVehicle` descriptors: `name ("")`, `batteryLevel (10000)`, `chargeLimit (-1)`, `chargingState ("Unknown")`, `availableCurrent (0)`, `voltage (0)`, `phases (0)`, `timeToFullCharge (0.0)`, `scheduledChargingPending (False)`, `lat (10000)`, `lon (10000)`, `gpsAsOf (0)`, `pluggedIn (None)`; `actualCurrent` keeps its property (backing field `"actualCurrent"`, `lastCurrentChangeTime` updated on change).
  - `CarApiVehicle.__init__(json, carapi, config)`: `self.vehicle = carapi.registry.getOrCreate(json["vin"], "TeslaAPI")`; `self.vehicle.attach("TeslaAPI", self)`; `self.vehicle.claim("TeslaAPI", lambda: not carapi.readOnly, "listed")`; `self.name = json["display_name"] or VIN or str(ID) or "unknown"` (an observation with `seen=True`: a cloud listing is a sighting, ruling 4). No thread.
  - `TeslaAPI.getVehicleByVIN(vin) -> CarApiVehicle | False`; `apiDebugInterface(command, vin, parameters)` resolves the car by VIN (ruling 2; the Fleet API paths already use the VIN, so the numeric `ID` is no longer needed by any command).
  - `CarApiVehicle.syncSource` → property: getter returns the source of `latest("state")` when it is in `TELEMETRY_SOURCES` and `age("state") <= syncTimeout` (3600), else `"TeslaAPI"`; setter stores `self._legacySyncSource = value` (the source the legacy telemetry code will write with next). `syncTimestamp` → getter `latest("state").at` or 0; setter is a no-op (observation times come from `observe`). `syncState`, `syncLat`, `syncLon` → properties whose setters call `self.vehicle.observe("state"|"lat"|"lon", value, source=self._legacySyncSource or "TeslaAPI")` and whose getters read the fields. (`TeslaAPIController._telemetryPluggedIn` keeps working unchanged.)
  - `update_vehicle_data()` observes only keys present in the response: `if "charge_limit_soc" in charge: self.chargeLimit = charge["charge_limit_soc"]` etc., never `charge.get(key, self.x)` (ruling P15: a carried-over or default value must not become a fresh `"TeslaAPI"` observation).
  - `is_awake()`: `obs = self.vehicle.latest("state")`; if `obs and obs.source in TELEMETRY_SOURCES`: `asleep|offline` → False; fresh (`age <= syncTimeout/4`) → `obs.value in ("online","charging","updating","driving")`; otherwise fall through to the existing 2-minute-cached API check (which does **not** write `state`, so a telemetry "asleep" keeps suppressing paid calls as today).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_carapivehicle_registry.py
from unittest.mock import Mock
from tests.unit.teslatokens import FakeMaster, fleet_token, new_api
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

def api_with_registry():
    master = FakeMaster(); master.vehicleRegistry = VehicleRegistry({})
    api = new_api(master=master); api.carApiVehicles = []
    return api, master.vehicleRegistry

def test_vehicle_joins_registry_and_claims_teslaapi():
    api, reg = api_with_registry()
    api.addVehicle({"id": 1, "vin": VIN, "display_name": "<car>"})
    v = reg.get(VIN)
    assert v.attachment("TeslaAPI") is api.getCarApiVehicles()[0] and v.name == "<car>"
    api.fleetSlot.clear()
    assert v.tier == "observed"            # no command slot: read-only
    api.fleetSlot.setTokens(fleet_token())
    assert v.tier == "managed"

def test_attributes_are_observations_with_source_and_defaults():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]
    assert car.batteryLevel == 10000 and car.chargeLimit == -1 and car.lat == 10000
    car.chargeLimit = 80
    obs = reg.get(VIN).latest("chargeLimit")
    assert (obs.value, obs.source) == (80, "TeslaAPI") and car.chargeLimit == 80
    car.actualCurrent = 12; assert car.lastCurrentChangeTime > 0 and car.actualCurrent == 12

def test_master_without_registry_gets_a_private_one():
    api = new_api(); api.carApiVehicles = []
    api.addVehicle({"id": 1, "vin": "V1", "display_name": "x"})
    assert api.getCarApiVehicles()[0].VIN == "V1" and isinstance(api.registry, VehicleRegistry)

def test_is_awake_trusts_fresh_telemetry_and_asleep_without_api_call():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.get_car_api = Mock(side_effect=AssertionError("no API call"))
    reg.get(VIN).observe("state", "asleep", "TeslaMateVehicle")
    assert car.is_awake() is False and car.syncSource == "TeslaMateVehicle"
    reg.get(VIN).observe("state", "online", "TeslaMateVehicle")
    assert car.is_awake() is True

def test_legacy_sync_setters_still_feed_the_registry():          # P7: Telemetry assigns these until Task 11
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.get_car_api = Mock(side_effect=AssertionError("no API call"))
    car.syncTimestamp = 123.0; car.syncSource = "TeslaMateVehicle"; car.syncState = "asleep"; car.syncLat = 1.5
    obs = reg.get(VIN).latest("state")
    assert (obs.value, obs.source) == ("asleep", "TeslaMateVehicle") and reg.get(VIN).latest("lat").value == 1.5
    assert car.is_awake() is False and car.syncSource == "TeslaMateVehicle" and car.syncTimestamp == obs.at

def test_update_vehicle_data_observes_only_present_keys():        # P15
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; reg.get(VIN).observe("phases", 3, "TeslaBLE", at=5.0)
    car.get_car_api = Mock(return_value=(True, {"drive_state": {"latitude": 1.0, "longitude": 2.0},
                                                "charge_state": {"battery_level": 61}, "vehicle_state": {}}))
    car.carapi.is_location_home = Mock(return_value=False); car.carapi.is_far_from_home = Mock(return_value=False)
    assert car.update_vehicle_data() is True
    phases = reg.get(VIN).latest("phases")
    assert car.batteryLevel == 61 and (phases.value, phases.source, phases.at) == (3, "TeslaBLE", 5.0)   # untouched
    assert reg.get(VIN).latest("chargeLimit") is None                                                   # no default observed

def test_debug_interface_resolves_by_vin():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    api.wakeVehicle = Mock()
    assert api.apiDebugInterface("wakeVehicle", VIN, "{}") is True
    api.wakeVehicle.assert_called_once_with(api.getCarApiVehicles()[0])
    assert api.apiDebugInterface("wakeVehicle", "5YJ3E1EA1KF000009", "{}") is False

def test_stale_telemetry_falls_back_to_api_check():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]
    reg.get(VIN).observe("state", "online", "TeslaMateVehicle", at=0.0)
    car.get_car_api = Mock(return_value=(True, {"state": "asleep"}))
    assert car.is_awake() is False and car.get_car_api.called and car.syncSource == "TeslaAPI"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TeslaAPI' object has no attribute 'registry'`).

- [ ] **Step 3: Implement** per Interfaces. Remove `checkSyncNotStale` and the `Thread` import; replace the sync class attributes with the properties above; `update_location`'s `else` branch (sync path) becomes: compute `atHome` from `lat/lon` (Task 10 rewrites the method anyway). Drop the `Thread` monkeypatches in tests.

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests/unit -q` → PASS (expect to touch assertions in `test_teslaapi_*` only where they set `syncSource`/`syncLat` directly: replace with `vehicle.vehicle.observe(...)`).

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/TeslaAPI.py
git add lib/TWCManager/Vehicle/TeslaAPI.py tests/unit
git commit -m "Back CarApiVehicle fields with the registry and derive sync state from observation source and age"
```

### Task 10: Reads cascade BLE then API and never wake (closes A6)

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/Sources.py`.
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:2223-2273` (`update_location`), `:2371-2422` (`update_charge`), `__init__` (register sources); `lib/TWCManager/Vehicle/TeslaBLE.py:98-185` (`__init__`: register the BLE source).
- Test: `tests/unit/test_reads_no_wake.py`.

**Interfaces:**
- Consumes: `ReadSource`, `Vehicle.read`, `TeslaBLE.get_charge_state/get_location_state/wakeVehicle`, `CarApiVehicle.update_vehicle_data`.
- Produces (`Sources.py`):
  - `CHARGE_FIELDS = frozenset({"batteryLevel","chargeLimit","chargingState","availableCurrent","actualCurrent","voltage","phases","scheduledChargingPending","timeToFullCharge"})`, `LOCATION_FIELDS = frozenset({"lat","lon","gpsAsOf"})`.
  - `class TeslaBLEReadSource(ReadSource)`: `__init__(ble, master)`, `name="TeslaBLE"`, `order=0`, `fields=CHARGE_FIELDS|LOCATION_FIELDS`; `canRead(vehicle)` = `vehicle.vin` and `"TeslaBLE" in vehicle.claims` (unpaired keys are never tried: each miss costs the BLE timeout) and the `VehiclePriority.commandPolicy` (via `master.getModuleByName`) is not `"api_only"` (today's behaviour, kept until Phase 2 maps the policy to suppressions); `fetch(vehicle, field, allowWake)`: charge field → `ble.get_charge_state(vin)`, location field → `ble.get_location_state(vin)` mapped to `lat/lon/gpsAsOf`; keys whose value is `None` are dropped from the returned dict (ruling P14, today's behaviour); when the read returns `None` and `allowWake` → `ble.wakeVehicle(vin)` then one retry; never wakes otherwise.
  - `class TeslaAPIReadSource(ReadSource)`: `__init__(carapi)`, `name="TeslaAPI"`, `order=1`, same fields; `canRead(vehicle)` = `vehicle.attachment("TeslaAPI") is not None`; `fetch`: first the **free** online check `car.is_awake()` (`vehicles/{vin}`, cached 2 min, trusts fresh telemetry; Fleet prices: `vehicles/{vin}` free, `vehicle_data` $0.002, wake $0.02) — `False` → return `None` without spending on `vehicle_data`; `True` → `car.update_vehicle_data()` (writes through descriptors) and return `{}` on success, `None` on failure. Never wakes, whatever `allowWake` says (a cloud wake is never worth a read).
  - `class HomeAssistantReadSource` is Task 12.
  - `TeslaAPI.__init__`: `self.registry.registerReadSource(TeslaAPIReadSource(self))`; `TeslaBLE.__init__` (after the binary check passes): `VehicleRegistry.forMaster(master).registerReadSource(TeslaBLEReadSource(self, master))`.
  - `CarApiVehicle.READ_MAX_AGE = 300`; `update_charge()` → `maxAge = READ_MAX_AGE; obs = self.vehicle.read("batteryLevel", maxAge=maxAge)`; returns `obs is not None and (self.vehicle.age("batteryLevel") <= maxAge or time.time() < self.statusDeferral)` (the cascade hands back a stale value when every source fails, which is a failure as today — except during an API `statusDeferral`, when today's code also reports success without fetching; ruling P13); `update_location(minInterval=0)` → same with field `"lat"` and `maxAge = minInterval` (`0` means force a fresh read, as `vehicleIsDefinitelyHome` relies on; ruling P12); on success recompute `self.atHome = carapi.is_location_home(lat, lon, gpsAge)` and `lastAPIAccessTime = now`. No `wakeVehicle` anywhere in either method.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_reads_no_wake.py
import time
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.Registry.Sources import TeslaBLEReadSource, TeslaAPIReadSource
from tests.unit.teslatokens import FakeMaster, new_api
VIN = "5YJ3E1EA1KF000001"

def setup(ble_result):
    master = FakeMaster(); reg = master.vehicleRegistry = VehicleRegistry({})
    ble = Mock(); ble.get_charge_state.return_value = ble_result; ble.get_location_state.return_value = None
    master.modules.update({"VehiclePriority": Mock(commandPolicy="prefer_ble"), "TeslaBLE": ble})
    api = new_api(master=master); api.carApiVehicles = []
    reg.registerReadSource(TeslaBLEReadSource(ble, master)); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    car = api.getCarApiVehicles()[0]; car.is_awake = Mock(return_value=True)
    # The API source writes through descriptors; the stand-in must too.
    car.update_vehicle_data = Mock(side_effect=lambda: car.vehicle.observe("batteryLevel", 50, "TeslaAPI") and True)
    reg.get(VIN).claim("TeslaBLE", True, "paired")
    return car, ble, reg

def test_ble_read_fills_fields_and_api_untouched():
    car, ble, reg = setup({"batteryLevel": 61, "chargeLimit": 80, "chargingState": "Charging", "phases": None})
    assert car.update_charge() is True
    assert (car.batteryLevel, reg.get(VIN).latest("chargeLimit").source) == (61, "TeslaBLE")
    assert reg.get(VIN).latest("phases") is None                                   # P14: None dropped
    car.update_vehicle_data.assert_not_called(); ble.wakeVehicle.assert_not_called()

def test_api_source_checks_free_online_state_before_paid_vehicle_data():
    car, ble, reg = setup(None); car.is_awake = Mock(return_value=False)
    assert car.update_charge() is False
    car.update_vehicle_data.assert_not_called(); ble.wakeVehicle.assert_not_called()

def test_status_deferral_counts_as_success_without_fetch():      # P13
    car, ble, reg = setup(None); car.update_vehicle_data = Mock(return_value=True)   # deferral path: no observe
    reg.get(VIN).observe("batteryLevel", 40, "TeslaAPI", at=0.0); car.statusDeferral = time.time() + 1800
    assert car.update_charge() is True

def test_update_location_zero_forces_a_fresh_read():            # P12
    car, ble, reg = setup(None); reg.get(VIN).observe("lat", 1.0, "TeslaAPI"); reg.get(VIN).observe("lon", 2.0, "TeslaAPI")
    ble.get_location_state.return_value = {"latitude": 3.0, "longitude": 4.0, "heading": 0, "gpsAsOf": 5}
    car.carapi.is_location_home = Mock(return_value=True)
    assert car.update_location(0) is True and car.lat == 3.0
    ble.get_location_state.assert_called_once()

def test_ble_failure_falls_to_api_without_waking():     # A6
    car, ble, reg = setup(None)
    assert car.update_charge() is True and car.batteryLevel == 50
    car.update_vehicle_data.assert_called_once(); ble.wakeVehicle.assert_not_called()

def test_all_sources_failing_reports_failure_even_with_stale_value():
    car, ble, reg = setup(None); car.update_vehicle_data = Mock(return_value=False)
    reg.get(VIN).observe("batteryLevel", 40, "TeslaAPI", at=0.0)
    assert car.update_charge() is False and car.batteryLevel == 40

def test_unpaired_vin_skips_ble():
    car, ble, reg = setup({"batteryLevel": 1}); reg.get(VIN).dropClaim("TeslaBLE")
    car.update_charge(); ble.get_charge_state.assert_not_called(); car.update_vehicle_data.assert_called_once()

def test_fresh_observation_skips_both():
    car, ble, reg = setup({"batteryLevel": 1}); reg.get(VIN).observe("batteryLevel", 50, "TeslaMateVehicle")
    assert car.update_charge() is True
    ble.get_charge_state.assert_not_called(); car.update_vehicle_data.assert_not_called()

def test_allow_wake_wakes_once_then_retries():
    car, ble, reg = setup(None); ble.wakeVehicle.return_value = True
    ble.get_charge_state.side_effect = [None, {"batteryLevel": 9}]
    assert reg.get(VIN).read("batteryLevel", maxAge=0, allowWake=True).value == 9
    ble.wakeVehicle.assert_called_once_with(VIN)

def test_location_read_recomputes_at_home():
    car, ble, reg = setup(None)
    ble.get_location_state.return_value = {"latitude": 1.0, "longitude": 2.0, "heading": 0, "gpsAsOf": 5}
    car.carapi.is_location_home = Mock(return_value=True)
    assert car.update_location() is True and car.atHome is True and (car.lat, car.lon) == (1.0, 2.0)
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: Sources`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_reads_no_wake.py tests/unit/test_teslaapi_charge_vin.py tests/unit/test_teslable_lock.py -q` → PASS; then the full suite.

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Architecture`: `    * (@MikeBishop) - One vehicle registry keyed by VIN holds every per-vehicle field with its source and age; reads cascade BLE then cloud and never wake a car unless asked; a TWC-reported VIN is confirmed by a second query before a vehicle is created; vehicles unseen for 30 days (config vehicle.forgetAfterDays) are forgotten`
```bash
black lib/TWCManager/Vehicle/Registry/Sources.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaBLE.py
git add lib/TWCManager/Vehicle tests/unit/test_reads_no_wake.py CHANGELOG.md
git commit -m "Read vehicle state through the registry cascade and stop waking cars on reads"
```

### Task 11: Telemetry attaches to registry vehicles (closes A34)

**Files:**
- Modify: `lib/TWCManager/Vehicle/Telemetry.py` (`applyDataToVehicle`, `updateVehicles`, new `vinFor`), `lib/TWCManager/Vehicle/TeslaMateVehicle.py:62-100` (events, `__init__`, new `loadCarVINs`), `lib/TWCManager/Vehicle/FleetTelemetryMQTT.py:17-30,38-110` (events, `mqttMessage`).
- Modify tests: `tests/unit/test_telemetry_mapping.py` (rewrite against the registry), `tests/unit/test_teslamate_plugged_in.py` (unchanged assertions still hold).
- Test: `tests/unit/test_telemetry_registry.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.forMaster/getOrCreate/findByName`, `Vehicle.observe/latest`.
- Produces:
  - `TelmetryBase.registry` = `VehicleRegistry.forMaster(master)` (set in `__init__` before the enabled check returns).
  - Feed liveness (spec "Report-on-change sources"): the concrete detection is **MQTT connection state, plus TeslaMate's per-car `healthy` topic** (ruling P8) — `TelmetryBase.connected: bool`, set True in `TelmetryBase.mqttConnect`, False in `mqttDisconnect` and at the start of `resetMQTT`; both subclasses' `mqttConnect` overrides call `super().mqttConnect(...)` first (today neither does). `TelmetryBase.feedLiveAt(vehicle) -> Optional[float]` = `time.time()` when `self.connected and self.carHealthy(vehicle)` else `None`; base `carHealthy` returns True. `TeslaMateVehicle` subscribes to `teslamate/cars/+/healthy` as well, routes it in `mqttMessage` to `noteHealthy(car_id, payload)` (`self.healthy[car_id] = payload.strip().lower() == "true"`), and `carHealthy(vehicle)` returns `self.healthy.get(id, True)` for the car id mapped to that vehicle (unpublished → assume healthy; "fresh only if TeslaMate is healthy and still polling"). `__init__` registers `self.registry.registerLiveness(self.__class__.__name__, self.feedLiveAt)`. (Per-car "last message" was rejected: a sleeping car legitimately sends nothing for hours on a healthy feed; paho's keepalive already proves the broker link.) So a connected, healthy feed makes telemetry fields age 0 and lets `trusted()` resolve the own-write case after `FEED_LAG`; a disconnected or unhealthy feed makes them age from the last change and never overrides our write.
  - `FleetTelemetryMQTT.mqttMessage` reads the previous state as `obs = self.vehicles[vin].latest("state") if self.vehicles.get(vin) else None; syncState = obs.value if obs else None`.
  - `TelmetryBase.vinFor(self, vehicle_id) -> Optional[str]`: base returns `None`; `FleetTelemetryMQTT.vinFor` returns `vehicle_id` (its topic id is the VIN); `TeslaMateVehicle.vinFor` returns `self.carVINs.get(str(vehicle_id))`.
  - `TeslaMateVehicle.loadCarVINs() -> Dict[str, str]`: when `db_host/db_name/db_user/db_pass` are all set, `SELECT id, vin FROM cars` via `psycopg2` (connection errors logged at INFO, returns `{}`); called once in `__init__` (independent of `syncTokens`); stored in `self.carVINs`.
  - `TelmetryBase.vehicles: Dict[str, Vehicle]` now maps telemetry id → registry `Vehicle`.
  - `updateVehicles(vehicle_id, vehicle_name, loadList=True) -> bool`: if mapped → observe `name` and return True; `vin = self.vinFor(vehicle_id)` → `registry.getOrCreate(vin, self.__class__.__name__)`, observe `name`, map, log INFO, return True; else `registry.findByName(vehicle_name)`; else (as today) when `loadList` and TeslaAPI is present and `not carapi.getCarApiRetryRemaining()`: `carapi.loadVehicleList()` then `findByName` again; else warn and return False.
  - `applyDataToVehicle(id, event, payload)`: for a mapped vehicle `vehicle.observe(field, converter(payload), source=self.__class__.__name__)`; unmapped → park in `unknownVehicles` (unchanged); no `syncSource`/`syncTimestamp` writes.
  - Event tables map to registry field names: TeslaMate `latitude→lat`, `longitude→lon`, `state→state`; FleetTelemetry `latitude→lat`, `longitude→lon`, `syncState→state`. With no assigner left, delete the transitional `syncSource` setter, `syncTimestamp` setter, `syncState`, `syncLat`, `syncLon` and `_legacySyncSource` from `CarApiVehicle` (the `syncSource`/`syncTimestamp` getters stay for `_telemetryPluggedIn`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_telemetry_registry.py
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.Telemetry import TelmetryBase
from TWCManager.Vehicle.TeslaMateVehicle import TeslaMateVehicle
from TWCManager.Vehicle.FleetTelemetryMQTT import FleetTelemetryMQTT
VIN = "5YJ3E1EA1KF000001"

class Probe(TelmetryBase):
    configName = "Probe"; unmappedRetrySecs = 3600
    events = {"charge_limit_soc": ["chargeLimit", int], "latitude": ["lat", float]}
    def scheduleUnmappedRetry(self, delay=None): self.scheduled = True

def make(cls=Probe, carapi=None, vins=None, clock=None):
    reg = VehicleRegistry({}, **({"clock": clock} if clock else {})); master = Mock(); master.vehicleRegistry = reg
    master.config = {"config": {}, "vehicle": {cls.configName: {"enabled": True}}}
    master.getModuleByName = Mock(return_value=carapi)
    t = cls(master)
    if vins is not None: t.carVINs = vins
    return t, reg

def test_vin_keyed_telemetry_creates_registry_vehicle_and_observes_with_source():
    t, reg = make(); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "charge_limit_soc", "80")      # before the name: parked
    assert reg.vehicles() == [] and t.unknownVehicles["1"] == [["charge_limit_soc", "80"]]
    t.applyDataToVehicle("1", "display_name", "<car>")   # maps and replays at once
    v = reg.get(VIN)
    assert v.name == "<car>" and t.vehicles["1"] is v
    assert (v.latest("chargeLimit").value, v.latest("chargeLimit").source) == (80, "Probe")

def test_name_match_against_registry_without_cloud_list():
    t, reg = make(); reg.getOrCreate(VIN, "TeslaBLE").observe("name", "<car>", "TeslaAPI")
    assert t.updateVehicles("1", "<car>", loadList=False) is True
    assert t.vehicles["1"] is reg.get(VIN)

def test_unidentifiable_car_is_parked_and_never_raises():   # Review Focus 4
    t, reg = make()
    t.applyDataToVehicle("1", "charge_limit_soc", "80"); t.applyDataToVehicle("1", "display_name", "Ghost")
    assert "1" not in t.vehicles and t.unknownVehicles["1"] == [["charge_limit_soc", "80"]] and t.scheduled
    assert reg.vehicles() == []

def test_task9_legacy_sync_names_are_gone():
    from TWCManager.Vehicle.TeslaAPI import CarApiVehicle
    assert not any(hasattr(CarApiVehicle, n) for n in ("syncState", "syncLat", "syncLon", "_legacySyncSource"))

def test_connection_state_is_the_feed_liveness():
    t, reg = make(); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "display_name", "<car>"); v = reg.get(VIN)
    v.observe("chargeLimit", 50, "Probe", at=0.0)
    assert reg.sourceLiveAt("Probe") is None and v.age("chargeLimit") > 1e6     # not connected yet
    t.mqttConnect(None, None, None, 0)
    assert v.age("chargeLimit") < 1.0                                          # healthy feed: value is current
    t.mqttDisconnect(None, None, None, 7)
    assert reg.sourceLiveAt("Probe", v) is None

def test_subclass_connects_set_liveness_and_teslamate_healthy_gates_it(monkeypatch):   # P8
    monkeypatch.setattr(TeslaMateVehicle, "loadCarVINs", lambda self: {"7": VIN})
    monkeypatch.setattr(TeslaMateVehicle, "doSyncTokens", lambda self, firstrun=False: None)
    t, reg = make(TeslaMateVehicle); client = Mock()
    t.mqttConnect(client, None, None, 0)
    assert t.connected and any("healthy" in c.args[0] for c in client.subscribe.call_args_list)
    t.applyDataToVehicle("7", "display_name", "C"); v = reg.get(VIN)
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is not None
    t.noteHealthy("7", "false")
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is None
    t.noteHealthy("7", "true")
    assert reg.sourceLiveAt("TeslaMateVehicle", v) is not None
    f, _ = make(FleetTelemetryMQTT); f.mqtt_prefix = "telemetry"; f.client = Mock()
    f.mqttConnect(f.client, None, None, 0)
    assert f.connected

def test_own_write_then_silent_healthy_feed_is_trusted_after_feed_lag():   # 09:17 shape, end to end
    from TWCManager.Vehicle.Registry.Fields import FEED_LAG
    now = {"t": 1000.0}
    t, reg = make(clock=lambda: now["t"]); t.vinFor = lambda vid: VIN
    t.applyDataToVehicle("1", "display_name", "C"); v = reg.get(VIN); t.mqttConnect(None, None, None, 0)
    t.applyDataToVehicle("1", "charge_limit_soc", "50")          # TeslaMate value from before our write
    v.noteWrite("chargeLimit", 100, "TeslaBLE")                  # we write 100 at t
    now["t"] = 1003.0
    assert v.trusted("chargeLimit") is None                      # t+3 s: not trusted, apply uses 100
    now["t"] = 1000.0 + FEED_LAG + 1
    assert v.trusted("chargeLimit").value == 50                  # healthy feed, no change event: write did not land
    t.mqttDisconnect(None, None, None, 7)
    assert v.trusted("chargeLimit") is None                      # feed down: silence proves nothing

def test_teslamate_maps_by_db_vin(monkeypatch):
    monkeypatch.setattr(TeslaMateVehicle, "loadCarVINs", lambda self: {"7": VIN})
    monkeypatch.setattr(TeslaMateVehicle, "doSyncTokens", lambda self, firstrun=False: None)
    t, reg = make(TeslaMateVehicle)
    assert t.vinFor("7") == VIN and t.vinFor("8") is None
    assert TeslaMateVehicle.events["latitude"][0] == "lat" and TeslaMateVehicle.events["state"][0] == "state"

def test_fleet_telemetry_topic_id_is_the_vin():
    t, reg = make(FleetTelemetryMQTT)
    assert t.vinFor(VIN) == VIN and FleetTelemetryMQTT.events["syncState"][0] == "state"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: vinFor`).

- [ ] **Step 3: Implement** per Interfaces; rewrite `tests/unit/test_telemetry_mapping.py` so `FakeCarApi.loadVehicleList` populates the registry (`registry.getOrCreate(...).observe("name", ...)`) and assertions check `t.vehicles["1"] is registry.get(VIN)` and observation sources instead of `syncSource`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_telemetry_registry.py tests/unit/test_telemetry_mapping.py tests/unit/test_teslamate_plugged_in.py tests/unit/test_telemetry_timers.py tests/unit/test_teslamate_token_sync.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Telemetry.py lib/TWCManager/Vehicle/TeslaMateVehicle.py lib/TWCManager/Vehicle/FleetTelemetryMQTT.py
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Attach telemetry to registry vehicles by VIN (TeslaMate DB, Fleet topic) or name"
```

### Task 12: HomeAssistant vehicles in the registry

**Files:**
- Modify: `lib/TWCManager/Vehicle/HomeAssistant.py:88-140` (`refresh_from_home_assistant`), `:151-235` (`__init__`), `:308-360` (`_build_vehicles_from_registry`); `lib/TWCManager/Vehicle/Registry/Sources.py` (`HomeAssistantReadSource`).
- Test: `tests/unit/test_homeassistant_registry.py`.

**Interfaces:**
- Produces:
  - `HomeAssistant.registry = VehicleRegistry.forMaster(master)` (before the enabled check).
  - `_build_vehicles_from_registry` (HA's device registry; unrelated name): for each `HaVehicle` built: `v = self.registry.getOrCreate(vin, "HomeAssistant")`, `v.attach("HomeAssistant", hv)`, `v.observe("name", name, "HomeAssistant")`, `v.claim("HomeAssistant", hv.has_charge_switch or hv.has_charge_limit_number or hv.has_charge_current_number, "entities")`.
  - `HaVehicle.refresh_from_home_assistant(api)`: after each successful parse also `v = api.registry.get(self.vin)` and, when `v` is not None, `v.observe(field, value, "HomeAssistant")` for `batteryLevel`, `chargeLimit`, `availableCurrent`, `lat`, `lon`, and `chargingState` (`"Charging"` when `charging` else `"Stopped"`).
  - `class HomeAssistantReadSource(ReadSource)`: `name="HomeAssistant"`, `order=1`, fields `CHARGE_FIELDS|LOCATION_FIELDS`; `canRead` = attachment present; `fetch` → `hv.refresh_from_home_assistant(ha)` and `{}`; registered in `HomeAssistant.__init__` once enabled.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_homeassistant_registry.py
from unittest.mock import Mock, patch
from TWCManager.Vehicle.HomeAssistant import HomeAssistant, HaVehicle
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"

def make_ha():
    reg = VehicleRegistry({}); master = Mock(); master.vehicleRegistry = reg
    master.config = {"config": {}, "vehicle": {"HomeAssistant": {"enabled": True, "url": "http://ha", "longLivedToken": "x" * 40}}}
    with patch("TWCManager.Vehicle.HomeAssistant.requests.Session") as S:
        S.return_value.get.return_value = Mock(raise_for_status=Mock())
        with patch.object(HomeAssistant, "_discover_vehicles"):
            ha = HomeAssistant(master)
    return ha, reg

def test_discovered_vehicle_is_attached_and_claimed():
    ha, reg = make_ha()
    devices = [{"id": "d1", "name": "Car", "manufacturer": "Tesla", "identifiers": [["teslemetry", VIN]]}]
    with patch.object(ha, "_map_tesla_entities", return_value={"charge_switch": "switch.car_charge", "battery_level_sensor": "sensor.b"}):
        ha._build_vehicles_from_registry(devices, [])
    v = reg.get(VIN)
    assert isinstance(v.attachment("HomeAssistant"), HaVehicle) and v.tier == "managed" and v.name == "Car"

def test_refresh_observes_with_source():
    ha, reg = make_ha(); hv = HaVehicle("Car", VIN, "d1", {"battery_level_sensor": "sensor.b", "charge_limit_number": "number.l"})
    reg.getOrCreate(VIN, "HomeAssistant").attach("HomeAssistant", hv)
    ha._get_state = Mock(side_effect=lambda ent: {"sensor.b": {"state": "73"}, "number.l": {"state": "90"}}.get(ent))
    hv.refresh_from_home_assistant(ha)
    v = reg.get(VIN)
    assert (v.latest("batteryLevel").value, v.latest("batteryLevel").source) == (73.0, "HomeAssistant")
    assert v.latest("chargeLimit").value == 90.0

def test_read_source_registered():
    ha, reg = make_ha()
    assert [s.name for s in reg.readSources()] == ["HomeAssistant"]
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: registry`).

- [ ] **Step 3: Implement** per Interfaces (`_build_vehicles_from_registry` requires `manufacturer` containing "tesla" and both `battery_level_sensor` and `charge_switch` entities; the fixture above satisfies that).

- [ ] **Step 4: Run tests** → PASS; full suite.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/HomeAssistant.py lib/TWCManager/Vehicle/Registry/Sources.py
git add lib/TWCManager/Vehicle tests/unit/test_homeassistant_registry.py
git commit -m "Register HomeAssistant vehicles, claims and reads in the vehicle registry"
```

### Task 13: TeslaBLE pairing status, proof, refusal and registry claims

Storage: `settings["Vehicles"][vin]["ble"] = {"status": <"pairing"|"paired"|"pairing_failed"|"refused">, "since": <epoch>}`. "Proven" is internal: a successful command or state read moves `pairing` (or absent) to `paired`. The refusal text is tesla-control's `ErrKeyNotPaired`: `"your public key has not been paired with the vehicle"` (vehicle-command `pkg/protocol/error.go:48`).

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py:410-478` (`peerWithVehicle`), `:489-585` (`_sendCommand_internal`), `:936-972` (`_fetch_state_json`), `:1474-1480` (`updateSettings`), new helpers.
- Test: `tests/unit/test_teslable_pairing_status.py`.

**Interfaces:**
- Produces (`TeslaBLE`):
  - `KEY_REFUSED_TEXT = "your public key has not been paired with the vehicle"`.
  - `registry = VehicleRegistry.forMaster(master)` (set in `__init__` first thing).
  - `bleStatus(vin) -> dict`: `{"status": str, "since": Optional[float]}` from `settings["Vehicles"][vin]["ble"]`, default `{"status": "unpaired", "since": None}` (the page merges this with the range scan, Task 17).
  - `_setBleStatus(vin, status)`: under `master.settingsLock` writes the record (creating `settings["Vehicles"][vin] = {"chargeSessions": 0, "startkWh": 0, "totalkWh": 0}` if absent) and queues `saveSettings`; then (outside the settings lock) `paired` → `registry.getOrCreate(vin, "TeslaBLE").claim("TeslaBLE", True, "paired")`; `refused`/`pairing_failed`/`pairing` → `dropClaim("TeslaBLE")` on the vehicle if present.
  - `_noteBleProof(vin)`: status not `paired` → `_setBleStatus(vin, "paired")` (INFO `BLE key for <vin> accepted`).
  - `_noteBleRefusal(vin, output)`: when `KEY_REFUSED_TEXT in output.lower()` → `_setBleStatus(vin, "refused")` (INFO `BLE key for <vin> refused; re-pair from the vehicle page`); returns bool.
  - `peerWithVehicle(vin)`: success → `_setBleStatus(vin, "pairing")`; failure → `"pairing_failed"`.
  - `_sendCommand_internal`: on success path (`return output or "ok"` and the already-satisfied path) call `_noteBleProof(vin)`; on `return_code != 0` call `_noteBleRefusal(vin, output)` before returning None. `_fetch_state_json`: success → `_noteBleProof(vin)`; failure → `_noteBleRefusal(vin, stderr text)`.
  - `updateSettings()`: after `scanForVehicles()`, for each `vin, rec` in `settings["Vehicles"]` with `"privKey" in rec` (ruling P9: main never wrote `BLEPeeringStatus`/`bleProven`, and `scanForVehicles` makes a key for every known VIN, so a key is the only evidence there is): `v = registry.getOrCreate(vin, "TeslaBLE")`; `rec.get("ble", {}).get("status") == "paired"` → `v.claim("TeslaBLE", True, "paired")`; status `refused`/`pairing_failed` → no claim; otherwise → `v.claim("TeslaBLE", False, "unproven")` — an unproven claim keeps BLE reads/commands being tried for that VIN (today's behaviour, and what `TeslaBLEReadSource.canRead` keys on) without making it managed; proof moves it to `paired`, a refusal drops it. Entries without a `privKey` (none exist once `scanForVehicles` has run, but a hand-edited file may have them) are not seeded. This is the one place the registry reads `settings["Vehicles"]`: it is the BLE key store, not session history.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_teslable_pairing_status.py
from unittest.mock import Mock, patch
import threading
import pytest
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.TeslaBLE import TeslaBLE
VIN = "5YJ3E1EA1KF000001"

def make():
    reg = VehicleRegistry({}); master = Mock(); master.vehicleRegistry = reg
    master.settings = {"Vehicles": {VIN: {"privKey": "x"}}}; master.settingsLock = threading.RLock()
    master.config = {"config": {"teslaControlPath": "/bin/true"}, "vehicle": {"teslaBLE": {"enabled": True}}}
    with patch.object(TeslaBLE, "_start_dbus_session"), patch.object(TeslaBLE, "_cleanup_stale_pipe"):
        ble = TeslaBLE(master)
    ble.sendPrivateKey = Mock(return_value=True); ble._ensure_pipe_closed = Mock()
    return ble, reg, master

def test_pairing_then_proof_makes_paired_and_managed():
    ble, reg, master = make()
    ble.sendPublicKey = Mock(return_value=True); ble.parseCommandOutput = Mock(return_value=True)
    ble._run_command_with_timeout = Mock(return_value=(b"", b"ok", 0))
    assert ble.peerWithVehicle(VIN) is True
    assert ble.bleStatus(VIN)["status"] == "pairing"
    assert reg.get(VIN) is None or reg.get(VIN).tier == "observed"
    ble._run_command_with_timeout = Mock(return_value=(b"", b"done", 0))
    assert ble._sendCommand_internal(VIN, "ping") == "done"
    assert ble.bleStatus(VIN)["status"] == "paired" and reg.get(VIN).tier == "managed"
    master.queue_background_task.assert_any_call({"cmd": "saveSettings"})

def test_refusal_drops_claim():
    ble, reg, master = make(); ble._setBleStatus(VIN, "paired")
    ble._run_command_with_timeout = Mock(return_value=(b"", b"Error: vehicle rejected request: your public key has not been paired with the vehicle", 1))
    assert ble._sendCommand_internal(VIN, "ping") is None
    assert ble.bleStatus(VIN)["status"] == "refused" and reg.get(VIN).tier == "observed"

def test_state_read_success_proves_key():
    ble, reg, master = make()
    ble._run_command_with_timeout = Mock(return_value=(b'{"chargeState": {"batteryLevel": 5}}', b"", 0))
    assert ble.get_charge_state(VIN)["batteryLevel"] == 5 and ble.bleStatus(VIN)["status"] == "paired"

def test_update_settings_reclaims_paired_vins():
    ble, reg, master = make(); master.settings["Vehicles"][VIN]["ble"] = {"status": "paired", "since": 1.0}
    ble.scanForVehicles = Mock(); ble.updateSettings()
    assert reg.get(VIN).tier == "managed"

def test_update_settings_seeds_keyed_entries_as_unproven_and_paired_as_managed():   # ruling 6 / P9
    ble, reg, master = make()
    master.settings["Vehicles"] = {VIN: {"privKey": "x", "chargeSessions": 4},
                                   "5YJ3E1EA1KF000002": {"privKey": "y", "ble": {"status": "paired", "since": 1.0}},
                                   "5YJ3E1EA1KF000003": {"privKey": "z", "ble": {"status": "refused", "since": 1.0}}}
    ble.scanForVehicles = Mock(); ble.updateSettings()
    assert reg.get(VIN).tier == "observed" and reg.get(VIN).claims["TeslaBLE"].status == "unproven"
    assert reg.get("5YJ3E1EA1KF000002").tier == "managed"
    assert "TeslaBLE" not in reg.get("5YJ3E1EA1KF000003").claims
    assert "ble" not in master.settings["Vehicles"][VIN]            # seeding writes nothing

def test_update_settings_ignores_entries_without_a_key():          # ruling 6 / P9
    ble, reg, master = make()
    master.settings["Vehicles"] = {VIN: {"chargeSessions": 4, "totalkWh": 12}}
    ble.scanForVehicles = Mock(); ble.updateSettings()
    assert reg.vehicles() == []

def test_pairing_failure_status():
    ble, reg, master = make(); ble.sendPublicKey = Mock(return_value=False)
    assert ble.peerWithVehicle(VIN) is False and ble.bleStatus(VIN)["status"] == "pairing_failed"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: bleStatus`).

- [ ] **Step 3: Implement** per Interfaces. The template's dead `BLEPeeringStatus` reads are replaced in Task 17, not here.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_teslable_pairing_status.py tests/unit/test_teslable_lock.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/TeslaBLE.py
git add lib/TWCManager/Vehicle/TeslaBLE.py tests/unit/test_teslable_pairing_status.py
git commit -m "Track BLE pairing status per VIN: pairing, paired on first proof, refused on key rejection"
```

### Task 14: Own-write stamps on charge limit and charge rate (A33 home)

Records only; no decision uses the stamps until Phase 3 ports `ChargeLimitRules`.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:2433-2500` (`apply_charge_limit` success), `:1743-1836` (`setChargeRate` → `_recordChargeRate`); `lib/TWCManager/Vehicle/TeslaBLE.py:587-668` (`setChargeRate` per-vehicle success), `:736-760` (`applyChargeLimit` success); `lib/TWCManager/Vehicle/HomeAssistant.py:569-626` (`applyChargeLimit` after `_call_service` ok).
- Test: `tests/unit/test_own_write_stamps.py`.

**Interfaces:**
- Consumes: `Vehicle.noteWrite(field, value, source)`.
- Produces: on each successful send: `vehicle.noteWrite("chargeLimit", limit, "<module>")` (TeslaAPI, TeslaBLE, HomeAssistant; for BLE `-1` restore the stamped value is `target_limit`), `vehicle.noteWrite("availableCurrent", amps, "<module>")` for charge rate (TeslaAPI `_recordChargeRate` via `getattr(vehicle, "vehicle", None)` so `test_teslaapi_chargerate.py`'s attribute-only fake keeps working; TeslaBLE per-vehicle branch). Registry vehicle located via `registry.get(vin)`; a missing vehicle is skipped silently.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_own_write_stamps.py
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Vehicle.TeslaAPI import TeslaAPI
from tests.unit.test_teslable_pairing_status import make as make_ble
VIN = "5YJ3E1EA1KF000001"

def test_api_charge_rate_stamps_available_current():
    reg = VehicleRegistry({}); v = reg.getOrCreate(VIN, "TeslaAPI"); car = Mock(VIN=VIN, vehicle=v)
    TeslaAPI._recordChargeRate(car, 16)
    assert v.lastWrite("availableCurrent").value == 16 and v.lastWrite("availableCurrent").source == "TeslaAPI"

def test_ble_set_charge_rate_stamps_on_success():
    ble, reg, master = make_ble(); reg.getOrCreate(VIN, "TeslaBLE")
    ble.wakeVehicle = Mock(return_value=True); ble.sendCommand = Mock(return_value="ok"); ble.parseCommandOutput = Mock(return_value=True)
    assert ble.setChargeRate(12, VIN) is True
    assert reg.get(VIN).lastWrite("availableCurrent").value == 12

def test_ble_set_charge_rate_no_stamp_on_failure():
    ble, reg, master = make_ble(); reg.getOrCreate(VIN, "TeslaBLE")
    ble.wakeVehicle = Mock(return_value=True); ble.sendCommand = Mock(return_value=None)
    assert ble.setChargeRate(12, VIN) is False and reg.get(VIN).lastWrite("availableCurrent") is None
```
Plus one test each for `TeslaAPI.CarApiVehicle.apply_charge_limit` (requests_mock `set_charge_limit` → `{"response": {"result": true}}`; assert `lastWrite("chargeLimit") == 80`) and `TeslaBLE.applyChargeLimit` (single VIN in settings, `sendCommand` mocked to `"ok"`; assert `lastWrite("chargeLimit").value == 80`), following the fixture styles of `test_teslaapi_readonly_gate.py` and the BLE `make()` above.

- [ ] **Step 2: Run to verify failure** → FAIL (`lastWrite(...) is None`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/Vehicle/HomeAssistant.py
git add lib/TWCManager/Vehicle tests/unit/test_own_write_stamps.py
git commit -m "Stamp the registry with our own successful charge-limit and charge-rate writes"
```

### Task 15: Callers read vehicles from the registry (closes A4, A7)

`TeslaAPI.getCarApiVehicles()` keeps meaning "cloud-listed vehicles" (TeslaAPIController needs exactly that for Fleet EVSEs). Every other caller moves to the registry; the debug page keys its vehicle by VIN (ruling 2).

**Files:**
- Modify: `lib/TWCManager/Policy/Policy.py:273`; `lib/TWCManager/TWCSlave.py:586-592`, `:1240-1252` (`getLastVehicle`); `lib/TWCManager/Control/WebIPCControl.py:347-348`; `lib/TWCManager/Control/HTTPControl.py:208-210` (template globals), `:774-793` (`/api/sendTeslaAPICommand`); `lib/TWCManager/Control/static/js/debug.js:42`; `lib/TWCManager/Control/themes/Default/debug.html.j2:74-76`, `settings.html.j2:256,268`.
- Test: `tests/unit/test_registry_callers.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.attached("TeslaAPI")`, `get(vin)`, `summaries()`, `TeslaAPI.apiDebugInterface(command, vin, parameters)` (Task 9).
- Produces:
  - `HTTPControl` template global `vehicles=lambda: master.vehicleRegistry.vehicles()` replaces the `getModuleByName("TeslaAPI").getCarApiVehicles` global (so the handler no longer touches TeslaAPI at construction: Review Focus 2). `debug.html.j2` renders `<option value="{{ vehicle.vin }}">{{ vehicle.name or vehicle.key }}</option>` over `vehicles()` (anonymous vehicles skipped); `debug.js` posts `vehicleVIN`; `/api/sendTeslaAPICommand` reads `data.get("vehicleVIN")` and passes it to `apiDebugInterface`, returning 400 when TeslaAPI is absent. `settings.html.j2` iterates registry vehicles that have a location (`vehicle.value("lat")`/`vehicle.value("lon")`, label `vehicle.name or vehicle.key`).
  - `Policy.py:273` → `for vehicle in self.master.vehicleRegistry.attached("TeslaAPI")`.
  - `TWCSlave.py:589` → same; `getLastVehicle()` → `reg = self.master.vehicleRegistry; for vin in (self.currentVIN, self.lastVIN): v = reg.get(vin) if vin else None; car = v.attachment("TeslaAPI") if v else None; if car: return car; return None`.
  - `WebIPCControl.py:347` → `for s in self.master.vehicleRegistry.summaries(): webResponseMsg += str(s) + "\n"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_callers.py
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.TWCSlave import TWCSlave
VIN = "5YJ3E1EA1KF000001"

def test_no_caller_outside_teslaapi_reaches_for_its_list():   # Review Focus 2
    import subprocess
    out = subprocess.run(["git", "grep", "-l", "getCarApiVehicles", "--", "lib/TWCManager"], capture_output=True, text=True).stdout.split()
    assert sorted(out) == ["lib/TWCManager/EVSEController/TeslaAPIController.py", "lib/TWCManager/Vehicle/HomeAssistant.py", "lib/TWCManager/Vehicle/TeslaAPI.py"]

def test_get_last_vehicle_uses_registry_attachment():
    reg = VehicleRegistry({}); car = object(); reg.getOrCreate(VIN, "TeslaAPI").attach("TeslaAPI", car)
    m = Mock(); m.vehicleRegistry = reg; m.getModuleByName = Mock(return_value=None)
    s = TWCSlave(bytearray(b"AB"), 80, {"config": {"wiringMaxAmpsPerTWC": 6, "useFlexAmpsToStartCharge": False, "startStopDelay": 60, "fakeMaster": False}}, m)
    s.currentVIN = ""; s.lastVIN = VIN
    assert s.getLastVehicle() is car
    s.lastVIN = "5YJ3E1EA1KF000009"
    assert s.getLastVehicle() is None

```

- [ ] **Step 2: Run to verify failure** → FAIL (the grep test lists Policy, TWCSlave, WebIPCControl and HTTPControl too; Telemetry already moved in Task 11).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite** → PASS (`test_policy.py` uses `Mock()` masters: `master.vehicleRegistry.attached(...)` returns a Mock, which is iterable? No — set `master.vehicleRegistry.attached = Mock(return_value=[])` in its fixtures where `getModuleByName("TeslaAPI").getCarApiVehicles()` was previously mocked).

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Policy/Policy.py lib/TWCManager/TWCSlave.py lib/TWCManager/Control/WebIPCControl.py lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager tests/unit
git commit -m "Read vehicles from the registry in Policy, TWCSlave and the web UI; key debug commands by VIN"
```

### Task 16: Vehicles tab: registry list and "Add vehicle by VIN"

**Files:**
- Modify: `lib/TWCManager/Control/themes/Default/vehicles.html.j2:10-30`; `lib/TWCManager/Control/HTTPControl.py` (POST route `/vehicle/add` next to `/vehicle/localMgmt` at `:1488`).
- Modify: `CHANGELOG.md`.
- Test: `tests/unit/test_vehicles_page.py`.

**Interfaces:**
- Consumes: `VehicleRegistry.summaries()`, `addUserAsserted(vin)`, `master.getNormalChargeLimit(vin)`.
- Produces:
  - Template section "Vehicles" (registry, from `registry.summaries()`): columns VIN (link to `/vehicleDetail/<vin>`; anonymous rows show `Unknown car on TWC <point>` unlinked), Name, Tier, Providers (`provider (status)` joined with `, `), Last seen (`ageText(row.lastSeenAge) + " via " + row.lastSeenSource`), Held limit via module-level `heldLimitText(master, vehicle) -> str`: `master.getNormalChargeLimit(vehicle.vin)`, and when not found and `vehicle.attachment("TeslaAPI")` exists, `master.getNormalChargeLimit(car.ID)` (TeslaAPI keys `chargeLimits` by numeric ID on main, TeslaBLE by VIN; ruling P11); result `(found, outside, applied)` → `"<outside>% (holding <applied>%)"` when found and `applied` not in `(-1, 0, None)`; `"<outside>% (restored)"` when found otherwise; `"—"` when not found. Below it the existing `settings["Vehicles"]` table retitled "Charge history", and "Vehicle Groups" unchanged. A form `POST /vehicle/add` with field `vin` and submit "Add vehicle"; `{{ addVehicleError }}` renders in red above the form when non-empty. The Forget action is Phase 6.
  - `HTTPControl` module-level `ageText(seconds: Optional[float]) -> str`: `None` → `"never"`; `< 60` → `"<n> s ago"`; `< 3600` → `"<n> min ago"`; `< 86400` → `"<n> h ago"`; else `"<n> d ago"` (integers).
  - `HTTPControl` module-level `addVehicleByVIN(master, vin) -> str` (returns the redirect location): `master.vehicleRegistry.addUserAsserted(vin)`; then under `master.settingsLock` `settings.setdefault("Vehicles", {}).setdefault(VIN, {"chargeSessions": 0, "startkWh": 0, "totalkWh": 0})` and, when `master.getModuleByName("TeslaBLE")` is present, `ble.scanForVehicles()` so the VIN gets its BLE keypair and pairing from its page works (ruling P10; `peerWithVehicle` needs `pubKeyPEM`); then `master.queue_background_task({"cmd": "saveSettings"})` → `"/vehicleDetail/<VIN upper>"`; `ValueError` → `"/vehicles?error=" + urllib.parse.quote_plus(str(e))`. POST route `/vehicle/add` calls it and 302s to the result.
  - Handler attribute `self.addVehicleError = urllib.parse.parse_qs(self.url.query).get("error", [""])[0]` set before the webroutes loop (templates render `vars(self)`, so it is visible as `addVehicleError`). Template globals: `ageText`, `heldLimitText`, `registry=master.vehicleRegistry`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_vehicles_page.py
from pathlib import Path
from types import SimpleNamespace
import jinja2, pytest
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
from TWCManager.Control.HTTPControl import ageText
VIN = "5YJ3E1EA1KF000001"
THEME = Path(__file__).resolve().parents[2] / "lib/TWCManager/Control/themes/Default"

def env(master):
    e = jinja2.Environment(loader=jinja2.FileSystemLoader(str(THEME)), autoescape=True)
    e.globals.update(navbarItem=lambda *a: "", checkForUpdates=lambda: False, ageText=ageText,
                     heldLimitText=lambda v: heldLimitText(master, v),
                     registry=master.vehicleRegistry, vehicles=master.vehicleRegistry.vehicles)
    return e

def master():
    reg = VehicleRegistry({}); v = reg.getOrCreate(VIN, "TWC"); v.observe("name", "<car>", "TeslaAPI"); v.claim("TeslaBLE", True, "paired")
    reg.beginPlugSession("8244")
    return SimpleNamespace(vehicleRegistry=reg, version="1.4.0", modules={}, settingsLock=threading.RLock(),
        getModuleByName=lambda name: None,
        settings={"Vehicles": {VIN: {"chargeSessions": 3, "totalkWh": 12}}, "VehicleGroups": {}},
        getNormalChargeLimit=lambda key: (True, 90, 80) if key == VIN else (False, None, None))

def test_held_limit_falls_back_to_api_numeric_id():                 # P11
    m = master(); v2 = m.vehicleRegistry.getOrCreate("5YJ3E1EA1KF000002", "TeslaAPI"); v2.attach("TeslaAPI", SimpleNamespace(ID=42))
    m.getNormalChargeLimit = lambda key: (True, 85, -1) if key == 42 else (False, None, None)
    assert heldLimitText(m, v2) == "85% (restored)" and heldLimitText(m, m.vehicleRegistry.get(VIN)) == "—"

def test_list_renders_registry_rows():
    m = master()
    html = env(m).get_template("vehicles.html.j2").render(master=m, url=SimpleNamespace(path="/vehicles", query=""), addVehicleError="")
    assert f"/vehicleDetail/{VIN}" in html and "<car>" in html and "managed" in html
    assert "TeslaBLE (paired)" in html and "90% (holding 80%)" in html
    assert "Unknown car on TWC 8244" in html and "Charge history" in html and 'action="/vehicle/add"' in html

def test_age_text():
    assert ageText(None) == "never" and ageText(30) == "30 s ago" and ageText(3600 * 5) == "5 h ago"

def test_add_vehicle_by_vin():
    m = master(); m.queue_background_task = Mock(); ble = Mock(); m.getModuleByName = lambda n: ble if n == "TeslaBLE" else None
    assert addVehicleByVIN(m, "5yj3e1ea1kf000002") == "/vehicleDetail/5YJ3E1EA1KF000002"
    m.queue_background_task.assert_called_once_with({"cmd": "saveSettings"})
    assert m.settings["Vehicles"]["5YJ3E1EA1KF000002"]["chargeSessions"] == 0
    ble.scanForVehicles.assert_called_once()                     # P10: keys exist, so pairing can work
    assert addVehicleByVIN(m, "5YJ3E1EA1KF00000I").startswith("/vehicles?error=") and "without+I%2C+O+or+Q" in addVehicleByVIN(m, "5YJ3E1EA1KF00000I")
    addVehicleByVIN(m, "5YJ3E1EA1KF000002")
    assert len([v for v in m.vehicleRegistry.vehicles() if v.vin == "5YJ3E1EA1KF000002"]) == 1
```
(`import threading`, `from unittest.mock import Mock` and `from TWCManager.Control.HTTPControl import addVehicleByVIN, heldLimitText` join the imports.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ImportError: ageText`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_vehicles_page.py tests/unit/test_httpcontrol.py -q` → PASS.

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Features`: `    * (@MikeBishop) - The Vehicles page lists the vehicle registry (tier, providers, last seen, held limit) and can add a vehicle by VIN so a VIN-less TWC with BLE only can be set up`
```bash
black lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager/Control tests/unit/test_vehicles_page.py CHANGELOG.md
git commit -m "List the vehicle registry on the Vehicles page and add vehicles by VIN"
```

### Task 17: BLE status on the per-car page with a range scan

Local name scheme, verified against vehicle-command `pkg/connector/ble/ble.go:133` (`VehicleLocalName`): `"S" + hex(sha1(vin)[:8]) + "C"`, i.e. `"S"` + first 16 hex chars of SHA-1 of the ASCII VIN + `"C"`; `5YJ3E1EA1KF000001` → `Sa3b631dfdbc5cf49C`. `tesla-control` has no scan subcommand, so the scan uses BlueZ: `bluetoothctl --timeout 8 scan on` (BlueZ 5.82 on the box supports `--timeout`) and looks for the local name in its output. The scan runs on the background-task thread under `_bleLock` (same adapter as tesla-control), never on the serial or HTTP thread; the page shows the cached result.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaBLE.py` (`bleLocalName`, `scanForVehicleInRange`, `rangeStatus`, `bleStatus` merge); `lib/TWCManager/TWCManager.py:376-392` (`bleScan` branch); `lib/TWCManager/Control/HTTPControl.py:1488-1500` (`/vehicle/localMgmt` ops `pair` and `scan`), template globals; `lib/TWCManager/Control/themes/Default/vehicleDetail.html.j2:78-80` (guard history), `:95-125` (BLE panel).
- Modify: `CHANGELOG.md`.
- Test: `tests/unit/test_vehicle_detail_page.py`, additions to `tests/unit/test_teslable_pairing_status.py`.

**Interfaces:**
- Produces (`TeslaBLE`):
  - `@staticmethod bleLocalName(vin: str) -> str`.
  - `SCAN_SECONDS = 8`; `scanForVehicleInRange(vin) -> Optional[bool]` decorated `@_serialized`: returns `None` when `shutil.which("bluetoothctl")` is None; runs `["bluetoothctl", "--timeout", "8", "scan", "on"]` through `_run_command_with_timeout(cmd, timeout=SCAN_SECONDS + 4, use_process_group=True)`; result = `bleLocalName(vin) in (stdout or b"").decode("utf-8", "replace")`; stores `self._rangeScan[vin] = {"inRange": bool, "at": time.time()}`; INFO log `BLE scan for <vin>: in range|not in range`.
  - `rangeStatus(vin) -> dict`: `{"inRange": Optional[bool], "at": Optional[float], "pending": bool}` (`pending` set by `requestRangeScan(vin)` and cleared by the scan).
  - `requestRangeScan(vin)`: adds `vin` to `self._scanRequests` (a set under `_bleLock`-free `threading.Lock`) and `master.queue_background_task({"cmd": "bleScan"})`; `runPendingScans()` pops every requested VIN and calls `scanForVehicleInRange` for each (the background queue coalesces by `cmd`, so one task serves all pending VINs; ruling P17). Each scan also observes `bleReach` (`True`/`False`, source `"TeslaBLE"`, `seen=False`) on the registry vehicle when it exists.
  - `bleStatus(vin)` (extends Task 13) → adds `"label"`, `"inRange"`, `"scannedAt"`, `"lastScanAge"` (seconds since `scannedAt`, or `None`), `"scanPending"`, `"canScan"`; labels: stored status `pairing` → `"Pairing (tap your key card in the car)"`, `paired` → `"Paired"`, `pairing_failed` → `"Pairing failed"`, `refused` → `"Key refused (re-pair)"`; otherwise from the scan: `inRange True` → `"In range (not paired)"`, `False` → `"Not in range"`, `None` (never scanned, or `canScan` False: Docker / no `bluetoothctl`, ruling 7) → `"Range unknown"`; the page adds "(bluetoothctl not found)" after it when `canScan` is False.
- Produces (`TWCManager.background_tasks_thread`): `elif task["cmd"] == "bleScan": ble = master.getModuleByName("TeslaBLE"); ble and ble.runPendingScans()` (runs on the background thread, so the 8 s scans never touch the serial loop).
- Produces (`HTTPControl`): `/vehicle/localMgmt` reads `operation`: `"pair"` → existing `peerWithVehicle`; `"scan"` → `ble.requestRangeScan(vin)`; both redirect to `/vehicleDetail/<vin>`. Template global `bleStatus=lambda vin: ble.bleStatus(vin) if ble else None`.
- Template: "Charge Sessions" row uses `master.settings.get("Vehicles", {}).get(vin, {}).get("chargeSessions", 0)`; BLE panel shows `Status: <label>`, `Last scan: {{ ageText(status.lastScanAge) }}`, a "Scan for vehicle" button (disabled text "Scanning…" when pending), and "Pair with Vehicle"/"Re-pair with Vehicle" (re-pair when status is `paired` or `refused`). A registry row (tier, providers, last seen) at the top of the page for any vehicle the registry holds.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_teslable_pairing_status.py`:
```python
def test_local_name_matches_tesla_control():
    assert TeslaBLE.bleLocalName("5YJ3E1EA1KF000001") == "Sa3b631dfdbc5cf49C"

def test_scan_parses_bluetoothctl_output_under_ble_lock():
    ble, reg, master = make()
    def run(cmd, timeout, use_process_group=True):
        assert cmd[:4] == ["bluetoothctl", "--timeout", "8", "scan"] and ble._bleLock.locked()
        return (b"[NEW] Device AA:BB:CC:DD:EE:FF Sa3b631dfdbc5cf49C\n", b"", 0)
    ble._run_command_with_timeout = run
    with patch("TWCManager.Vehicle.TeslaBLE.shutil.which", return_value="/usr/bin/bluetoothctl"):
        assert ble.scanForVehicleInRange(VIN) is True
        assert ble.rangeStatus(VIN)["inRange"] is True and ble.bleStatus(VIN)["label"] == "In range (not paired)"
        ble._run_command_with_timeout = lambda *a, **k: (b"[NEW] Device 11:22:33:44:55:66 Other\n", b"", 0)
        assert ble.scanForVehicleInRange(VIN) is False and ble.bleStatus(VIN)["label"] == "Not in range"

def test_scan_unavailable_without_bluetoothctl():
    ble, reg, master = make()
    with patch("TWCManager.Vehicle.TeslaBLE.shutil.which", return_value=None):
        assert ble.scanForVehicleInRange(VIN) is None
        assert ble.bleStatus(VIN)["canScan"] is False and ble.bleStatus(VIN)["label"] == "Range unknown"

def test_request_scan_queues_one_task_and_runs_every_pending_vin():     # P17
    ble, reg, master = make(); ble.requestRangeScan(VIN); ble.requestRangeScan("5YJ3E1EA1KF000002")
    master.queue_background_task.assert_called_with({"cmd": "bleScan"})
    assert ble.bleStatus(VIN)["scanPending"] is True
    ble.scanForVehicleInRange = Mock(return_value=False); ble.runPendingScans()
    assert sorted(c.args[0] for c in ble.scanForVehicleInRange.call_args_list) == ["5YJ3E1EA1KF000002", VIN]
    assert ble.bleStatus(VIN)["scanPending"] is False

def test_scan_observes_ble_reach_on_registry_vehicle():
    ble, reg, master = make(); reg.getOrCreate(VIN, "TeslaBLE")
    ble._run_command_with_timeout = lambda *a, **k: (b"", b"", 0)
    with patch("TWCManager.Vehicle.TeslaBLE.shutil.which", return_value="/usr/bin/bluetoothctl"):
        ble.scanForVehicleInRange(VIN)
    assert reg.get(VIN).latest("bleReach").value is False and ble.bleStatus(VIN)["lastScanAge"] < 1.0

@pytest.mark.parametrize("status,label", [("pairing", "Pairing (tap your key card in the car)"), ("paired", "Paired"),
                                          ("pairing_failed", "Pairing failed"), ("refused", "Key refused (re-pair)")])
def test_stored_status_labels(status, label):
    ble, reg, master = make(); ble._setBleStatus(VIN, status)
    assert ble.bleStatus(VIN)["label"] == label
```
```python
# tests/unit/test_vehicle_detail_page.py
from types import SimpleNamespace
from tests.unit.test_vehicles_page import env, master, VIN

def test_detail_renders_without_history_and_shows_ble_status():   # Review Focus 5
    m = master(); m.settings["Vehicles"] = {}; m.modules = {"TeslaBLE": object()}
    e = env(m); e.globals["bleStatus"] = lambda vin: {"status": "unpaired", "label": "In range (not paired)", "inRange": True,
                                                      "scannedAt": 1.0, "lastScanAge": 42.0, "scanPending": False, "canScan": True}
    html = e.get_template("vehicleDetail.html.j2").render(master=m, url=SimpleNamespace(path=f"/vehicleDetail/{VIN}"))
    assert "In range (not paired)" in html and "Not Implemented" not in html
    assert 'value="scan"' in html and 'value="pair"' in html and "managed" in html
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: bleLocalName`).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run tests** → PASS; full suite.

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Features`: `    * (@MikeBishop) - The vehicle page shows BLE status (not in range, in range, pairing, paired, pairing failed, key refused) with a Bluetooth scan for the car`
```bash
black lib/TWCManager/Vehicle/TeslaBLE.py lib/TWCManager/TWCManager.py lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager tests/unit CHANGELOG.md
git commit -m "Show BLE pairing status and a range scan on the vehicle page"
```

- [ ] **Step 6: Live check on the user's box (deploy branch, pre-approved)**

Deploy the branch to `twcmanager`, restart, and confirm: the Vehicles page lists the registry; a charge session on a VIN-reading TWC creates the car after the confirmation re-query (INFO log, one `chargeSessions` increment); "Scan for vehicle" returns a result within ~10 s with no RS-485 stall warning in the log; BLE state reads still succeed and move the status to Paired. Record findings in the PR description.

---

## Inventory rows this phase closes

- Phase 0: **A20** (charge task queue key, #667) and the **B5** settings-save race (lock + snapshot; full writer coverage is an open question below).
- Phase 1: **A4** (reads dispatched through the registry cascade, callers off `getCarApiVehicles()`), **A6** (no wake on read), **A7** (VehicleRegistry; `carApiVehicles` is now a view of registry attachments), **A34** (telemetry attaches by VIN via the TeslaMate DB or Fleet topic, by name otherwise), **B2** split ownership (one object per car). **A33** only in the sense that own-write stamps now live on the registry `Vehicle` for every install; the rule that consumes them lands with `ChargeLimitRules` in Phase 3.

## Resolved questions (controller rulings, 2026-10-13)

1. TeslaMate identity: VIN from the `cars` table when DB credentials are configured, else today's display-name match (Task 11, as planned).
2. Debug page keys vehicles by VIN; `apiDebugInterface(command, vin, parameters)` resolves the car by VIN (Tasks 9, 15).
3. Settings lock covers every writer that mutates settings from a non-serial thread (worker, HTTP, BLE, background); single-key reads stay unlocked; writers listed in Task 2.
4. A cloud account listing is a sighting and a provider claim keeps a car: `expire()` only removes vehicles with no claims (Task 6, Task 9).
5. User-asserted vehicles never expire; only Forget (Phase 6) removes them (Task 6).
6. Upgrade seed (amended by P9: main never wrote `BLEPeeringStatus`/`bleProven`): every `settings["Vehicles"]` entry with a `privKey` gets an unproven BLE claim (observed; BLE still tried, as today), a stored `paired` status gets a commanding claim (managed), a refusal drops it; entries without a key are not seeded (Task 13, two tests).
7. BLE scan unavailable (Docker / no `bluetoothctl`): status "Range unknown" (Task 17).
8. Owner-only installs show cloud cars as observed: correct per the spec; no change.

Pre-flight rulings P1–P17 (`.superpowers/sdd/2026-10-13-vehicle-model-phase1-registry/progress.md`) are folded into Tasks 2, 3, 5, 6, 7, 8, 9, 10, 11, 13, 16 and 17 where marked. Fleet per-operation prices (spec): `vehicles/{vin}` free, commands $0.001, `vehicle_data` $0.002, wake $0.02 — Task 10's API read source checks the free online state first and never wakes to read.
