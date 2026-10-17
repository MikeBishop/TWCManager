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

