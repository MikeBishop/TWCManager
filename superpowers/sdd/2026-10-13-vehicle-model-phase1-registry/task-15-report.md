# Task 15 report: callers read vehicles from the registry

**Status:** done. Commit `f1d11a2` on `vehicle-model/phase1` (parent cfb39fd), not pushed.

**Tests:** 1057 -> 1064 passed (`python -m pytest tests/unit -q`). 7 new tests in `tests/unit/test_registry_callers.py`:
- the brief's two (acceptance git-grep; `getLastVehicle` via registry attachment, plus a check that lookup creates nothing)
- the HTTP handler builds with no TeslaAPI module, and its `vehicles` global is `registry.vehicles()`
- the debug.html.j2 and settings.html.j2 vehicle loops, rendered through the real theme loader against a real registry (named VIN, unnamed VIN, anonymous `anon:AB`)
- `/api/sendTeslaAPICommand` passes `vehicleVIN` to `apiDebugInterface`, and answers 400 when TeslaAPI is absent

All of them failed before the change.

**Acceptance grep:** `git grep -l getCarApiVehicles -- lib/TWCManager` returns exactly TeslaAPIController.py, HomeAssistant.py and TeslaAPI.py.

## Changes
- `Policy.py` and `TWCSlave.py` (heartbeat path): `for vehicle in self.master.vehicleRegistry.attached("TeslaAPI")`.
- `TWCSlave.getLastVehicle`: `registry.get(vin)` then `.attachment("TeslaAPI")`, current VIN first, then last VIN. No `getOrCreate` and no `read()`.
- `WebIPCControl` dumpState: prints `str(s)` for each entry in `vehicleRegistry.summaries()`, not `vehicle.__dict__`. This is the carry-over: field values are back, and nothing goes through `vehicle.vehicle`.
- `HTTPControl`: the template global is `vehicles=lambda: master.vehicleRegistry.vehicles()`. `/api/sendTeslaAPICommand` reads `data.get("vehicleVIN")`, returns 400 when TeslaAPI is absent, and otherwise calls `apiDebugInterface(command, vin, params)`.
- `debug.js` posts `vehicleVIN`.
- `debug.html.j2`: the loop is `vehicles() if vehicle.vin` (anonymous vehicles skipped), with `value="{{ vehicle.vin }}"` and label `vehicle.name or vehicle.key`.
- `settings.html.j2`: both loops (map marker and home-location `<select>`) are filtered to vehicles whose `value("lat")` and `value("lon")` are not none. The option value keeps the `lon,lat` order that the HTTPControl homeLocation handler splits.
- `test_policy.py`: three fixtures now set `master.vehicleRegistry.attached = Mock(return_value=[])`.
- CHANGELOG v1.4.0 Architecture: `/api/sendTeslaAPICommand` now takes `vehicleVIN` instead of the numeric `vehicleID`.

## Constraints
- Thread safety: `attached()` is `vehicles()` under the registry lock, then `attachment()` on each vehicle under its own leaf lock, with locks released between steps. `getLastVehicle` is `get()` followed by `attachment()`. The serial path does no I/O and never calls `read()`. The templates call only `.vin`, `.key`, `.name` and `.value()`, all of which read stored fields; they never call `read()`.
- Black: the four lib files were clean beforehand and running black on them changed nothing. `test_policy.py` was already failing `black --check`, so I edited only its three fixture lines and did not run black on it. The new test file is blacked.
- The Modern theme has no vehicle templates (I grepped it), so changing the global's type does not affect it.

## Concerns
1. `WebIPCControl` dumpState still calls `carapi.getLastStartOrStopChargeTime()` and similar without a guard, above my change. That code already existed and crashes on a Gen2 install with no TeslaAPI. It is out of scope, so I flagged it and did not fix it.
2. The WebIPC change has no test, because `processIPC` is a sysv_ipc loop. It is two lines, and `summaries()` is tested elsewhere.
3. `vehicleVIN` reaches `apiDebugInterface` without validation. A missing or unknown VIN makes it return False, which gives a 400. No test sends an unknown VIN.
4. `HomeAssistant.getCarApiVehicles` is still defined. That is intended: the acceptance list expects it.

## Fix round 1

**Commit:** `d29e01a`. **Tests:** 1067 passed, up from 1064.

0. Home location
   - `process_home_location` now reads `str(self.getFieldValue("vehicle") or "")`. When nothing is selected it logs "No vehicle selected; home location unchanged" and does nothing else, still answering with the 302. The existing invalid-format warning still covers malformed input.
   - A new template global, `locatedVehicles()`, lists registry vehicles that have both `lat` and `lon`. The settings map markers and the select now use it.
   - The "Make Vehicle Location Home Location" button and the `<select name=vehicle>` are wrapped in `{% if locatedVehicles() %}`, so they disappear when no vehicle has a location. "Unset" always stays.
   - Tests: the learn button and select are hidden when no vehicle is located; an empty selection is a no-op that still answers 302; a valid selection sets lon and lat.
   - `render_settings` in `test_teslaapi_token_paste.py` stubs every handler global, so it now stubs `locatedVehicles` as well. That file was clean under black and still is.
1. The debug dropdown loop is now `vehicles() if vehicle.vin and vehicle.attachment("TeslaAPI")`. The test adds a VIN known only through BLE, which is excluded.
4. The acceptance grep in `test_registry_callers` now runs with `cwd=REPO`, where `REPO` is `pathlib.Path(__file__).resolve().parents[2]`. It passes when pytest is run from `/tmp`.
5. In `test_policy.py`, I removed `mock_tesla_api` from the three fixtures. `getModuleByName` still returns `Mock()`, as the file's other fixtures do, because `Policy.py:316` still reads `getModuleByName("TeslaAPI").minBatteryLevelAtHome`.
