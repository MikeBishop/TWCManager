# Task 9 review: CarApiVehicle backed by the registry (055e286..290f7d1)

### Spec Compliance
**Compliant.** Every Interfaces item in the brief is implemented as written:
- `TeslaAPI.__init__` sets `self.registry = VehicleRegistry.forMaster(master)` (TeslaAPI.py:142).
- `RegistryField` (TeslaAPI.py:23-41) is in place, and the 13 listed descriptors carry the brief's defaults (TeslaAPI.py:2033-2046). `actualCurrent` keeps its property, backed by `RegistryField("actualCurrent", 0)`, and `lastCurrentChangeTime` moves only when the value changes (TeslaAPI.py:2523-2533).
- `__init__` calls getOrCreate, attach and claim (`not carapi.readOnly`, "listed"). The name is observed with seen=True, and no thread is started (TeslaAPI.py:2063-2082).
- The sync properties match the brief: `syncSource` is derived, its setter stores `_legacySyncSource`, the `syncTimestamp` setter does nothing, and the `syncState`/`syncLat`/`syncLon` setters observe with the legacy source (TeslaAPI.py:2099-2159).
- `is_awake` matches the brief, and its fall-through does not write "state" (TeslaAPI.py:2194-2217).
- `update_vehicle_data` observes only keys present in the response, satisfying P15 (TeslaAPI.py:2423-2450).
- `getVehicleByVIN` and the VIN-keyed `apiDebugInterface` are in place. `getVehicleByID` is removed, and it has no remaining callers in lib/ or the templates. debug.html.j2 now posts the VIN.
- `checkSyncNotStale` and the `Thread` import are gone. The `Thread` monkeypatches are dropped, and `no_threads` remains as a no-op fixture (tests/unit/teslatokens.py:121-124).
- The brief's eight tests are all present, plus eight more. I counted 16 `def test_` in tests/unit/test_carapivehicle_registry.py:18-198, and the brief's eight names match.

### Strengths
- **Caller semantics are kept.** I checked every attribute read in TWCMaster:660-670, TWCSlave:671-672/1243, HTTPControl:376-381, TeslaAPIEVSE:63-112, TeslaAPIController:87-94/124, Policy:273, settings.html.j2:257/269, FleetTelemetryMQTT:50-51 (the `syncState` getter defaults to "asleep" as before), Telemetry.py:162-169/236, and the TeslaMate/FleetTLM `events` setattr targets. Each one gets the same type and default as before: lat/lon 10000, batteryLevel 10000, chargeLimit -1, chargingState "Unknown", pluggedIn None, phases 0. Every descriptor field is in `Fields.FIELDS`, so no write raises KeyError.
- **Thread safety.** Reads take only `registry._lock` and then the FieldStore lock. Writes add getOrCreate, attach and claim, each a short leaf-lock section. No I/O and no module call happens under a lock, and the claim callable runs outside the lock (Vehicle.tier). That is safe on the serial and MQTT threads.
- **Forgotten vehicles are handled carefully.** Reads have no side effects (`_liveVehicle`). A write after a forget rejoins the vehicle. A rebind attaches only into an empty attachment, so a stale object never displaces a newer CarApiVehicle (TeslaAPI.py:2072-2097). Tests cover all three cases.
- P15 is applied to the BLE location path too: gpsAsOf is observed only when truthy.
- The end-to-end test drives a real `TelmetryBase` subclass into a real CarApiVehicle. It proves that P7's interim telemetry path stamps "state" and lat with source TeslaMateVehicle.
- The tests pass: 238 focused (`test_carapivehicle_registry`, `test_teslaapi_*`) plus 90 (telemetry, teslamate_plugged_in, vehicle_priority, command_queue, registry_vehicle). black --check is clean on all five touched .py files. I did not rerun the whole suite (my instructions were focused tests only); the 928 is the implementer's figure.
- **No test lost its meaning.** The only direct `sync*` assignments outside the new file are on the `FakeVehicle` stub in test_telemetry_mapping.py:13-17, which is not a CarApiVehicle, so no existing test now passes vacuously. That is also why Step 4's predicted test edits weren't needed.

### Issues

**Critical:** none.

**Important:** none. The behaviour shifts listed below come from the brief's own getter spec, and the controller has ruled them accepted within the phase (Task 11 adds the liveness-aware age).

**Minor:**
1. **One more caller of the interim `syncSource` shift** (TeslaAPIController.py:87-94, `_telemetryPluggedIn`). It reads `syncSource`, so once the latest telemetry "state" observation is more than an hour old, it stops treating TeslaMate's `pluggedIn=True` as live. Before, it was sticky while the car slept. Then, while an unnamed TWC is present (the `unknown` case), a plugged-in car that has slept for more than an hour can be listed as a TeslaAPIEVSE. That EVSE could then receive Fleet charge-rate commands. This is the same root cause as the implementer's concerns 2 and 3, and it is covered by the ruling. Add it to the Task 11 checklist, especially concern 3's open question: liveness alone may not hold `syncSource` while TeslaMate is quiet and the car is asleep.
2. **WebIPC debug dump loses the fields** (WebIPCControl.py:348). `str(vehicle.__dict__)` no longer shows batteryLevel, chargeLimit, lat/lon, chargingState and so on: they live in the registry, not the instance dict. The dump now shows `_vehicle` as a bare object repr. This affects debug output only; consider adding `carapi.registry.get(vehicle.VIN)` (None-guarded) and its `.summary()` to the dump. Do not use `vehicle.vehicle`: that write-path accessor re-creates a forgotten vehicle.
3. **A null `gps_as_of` is observed as 0** (TeslaAPI.py:~2425). When the response has `"gps_as_of": null`, `gpsAsOf` is observed as 0 with source TeslaAPI. The value is the same as before ("no fix time"), and the key is present, so P15 is satisfied in letter. Observing only when the value is truthy, as the BLE path does, would be more consistent.
4. **`apiDebugInterface` gets the string "None"** (HTTPControl.py:784). It passes `str(data.get("vehicleID", None))`, so a missing ID arrives as "None", fails to match, and returns 400. That is correct, but the API contract change (numeric ID to VIN, concern 6) should go in the CHANGELOG or release notes.
5. **The interim "telemetry has resumed" log fires on every message** (concern 4). It is INFO-level noise until Task 11. It is accepted, but do not deploy Task 9 alone to the live box: concern 2 also leaves the paid-call regression open.

### Assessment
**Task quality:** Approved

**Reasoning:** The implementation matches the brief item by item. Every caller I traced gets the same type and default semantics. Observations are recorded only for keys present in the response. Descriptor get and set take only leaf locks and do no I/O. The sync thread, `getVehicleByID` and the `Thread` patches are gone, and `no_threads` remains as a no-op. The open behaviour changes (the `syncSource` age, the BLE wake, `_telemetryPluggedIn`) come from the spec'd interim getter and fall under the controller's Task 10/11 rulings. The remaining items are polish.
