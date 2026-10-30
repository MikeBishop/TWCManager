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

