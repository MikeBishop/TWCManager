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

