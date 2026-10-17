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

