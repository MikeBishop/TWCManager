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

