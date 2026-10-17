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

