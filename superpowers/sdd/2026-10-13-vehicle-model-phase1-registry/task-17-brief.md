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
