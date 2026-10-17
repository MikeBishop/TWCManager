# Pre-flight conflict scan: vehicle-model Phase 0 + 1 (registry)

Plan: `.superpowers/plans/2026-10-13-vehicle-model-phase1-registry.md`
Spec: `.superpowers/specs/2026-10-13-vehicle-model-design.md`
Code base checked: `origin/main` `eb457dc` (scratchpad `wt-vm`). Scanned 2026-10-14.

Legend: OK = consistent; MISMATCH = the two sides disagree (detail given); GAP = one side leaves undefined something the other needs; NOTE = minor.

## 1. Task pairs that share a file or an interface

| Tasks | Producer side | Consumer side | Finding |
|---|---|---|---|
| T1 / T2, T7, T8 | T1 cherry-pick adds 9 lines to `cancelStopCarsCharging` (TWCMaster.py:166) and 9 more in `startCarsCharging`/`stopCarsCharging` | T2, T7, T8 cite TWCMaster line numbers (`:1010-1125`, `:1201-1262`, `:1405-1451`, `:1521-1580`) | NOTE: the line numbers are origin/main's, before T1. After T1 they are about 9 lines later. The method names are right. |
| T1 / T2 | `stopCarsCharging` writes `respondToSlaves` (stop mode 2) | T2 leaves the serial-thread writers unlocked, including `stopCarsCharging`'s `respondToSlaves` | OK |
| T2 / T7 | `master.settingsLock` (RLock) | `recordVehicleVIN` does the confirmed-path bookkeeping under `with self.settingsLock:` on the serial thread | OK on lock order (registry call first, settings lock after). NOTE: T2 says serial-thread writers stay unlocked, but T7 deliberately locks one. The serial loop can now wait behind a `saveSettings` `json.dumps`. That wait is short but new. |
| T2 / T8 | T2 `make()` fixture in `test_settings_lock.py` sets `m.vehicleRegistry = Mock(toJSON=...)` | T8 imports `make` and says to delete that line | OK. NOTE: from T2 to T8 the line sets an attribute that no code reads (dead code). |
| T2 / T8 | `saveSettings` step 1 runs under the lock; `payload = json.dumps(...)` | T8 adds `settings["vehicleRegistry"] = toJSON()` inside the locked step 1 | OK. Lock order settings → registry → vehicle matches the Global Constraints. |
| T2 / T13 | `master.settingsLock` | `_setBleStatus` takes it from inside `_sendCommand_internal`/`_fetch_state_json`, which hold `_bleLock` | OK (order `_bleLock` → settings → registry). The T13 test master supplies a real RLock. |
| T2 / T17 | T2 wraps `TeslaBLE.scanForVehicles` key generation and HTTPControl writes | T17 edits TeslaBLE and the HTTPControl `/vehicle/localMgmt` route | OK. No overlap in the regions touched. |
| T3 / T4 | `FieldStore(clock)`, `observe/latest/age(liveAt)/noteWrite/lastWrite/fresherThanWrite/trusted(liveAt)/snapshot`, `_lock` | `Vehicle` wraps them; `age`/`trusted` pass `liveAt` from the registry | OK |
| T3 / T5 | `FieldStore._lock` (a `threading.Lock`, so it has `.locked()`) | The T5 test asserts `vehicle._fields._lock.locked()` is False during `fetch` | OK |
| T3 / T6 | `Fields.NOT_TRACKED` | `VehicleRegistry.sourceLiveAt` returns it for unregistered sources; the T6 test imports it | OK |
| T3 / T6 | `REPORT_ON_CHANGE_SOURCES = TELEMETRY_SOURCES` (a static set) | T6: "registering liveness is what makes a source report-on-change" | NOTE: two definitions of "report-on-change" exist, and nothing consumes `REPORT_ON_CHANGE_SOURCES`. |
| T3 / T9 | `TELEMETRY_SOURCES = {"TeslaMateVehicle","FleetTelemetryMQTT"}` | `CarApiVehicle.syncSource` / `is_awake` | OK. The names equal `self.__class__.__name__` used in T11. |
| **T3 / T11** | `fresherThanWrite`: "equal counts as fresher" (`latest.at >= lastWrite.at`, asserted in the T3 test) | T11 `test_own_write_then_silent_healthy_feed_is_trusted_after_feed_lag`: with the clock at 1000, `applyDataToVehicle(... "50")` observes at 1000; `noteWrite(...100)` also stamps 1000; at t=1003 the test expects `trusted() is None` | **MISMATCH.** The equal timestamps make `fresherThanWrite` True, so `trusted()` returns the 50 observation and the T11 assertion fails. Either the tie rule or the test has to change. |
| **T4 / T5** | `Vehicle.age()/trusted()` call `self._registry.sourceLiveAt(obs.source)` whenever a registry is attached | The T5 test's `Reg` stub has only `readSources()`. The T5 Interfaces line says a registry "must expose `readSources()`" | **MISMATCH.** If `read()` uses `self.age()`, every T5 test with a stale-or-fresh check raises `AttributeError`. The registry protocol has to include `sourceLiveAt`, or `Vehicle` has to tolerate its absence. |
| T4 / T6 | `Vehicle(key, vin, registry, clock, userAsserted)`, `lastSeen`, `claims`, `isAnonymous` | `getOrCreate`, `addUserAsserted` (sets `userAsserted=True` on an existing vehicle), `expire` | OK |
| T4 / T7 | key `"anon:<point>"`; `summary()["point"] = key[5:]`, else the latest `twcVin` | Plug sessions and `vehicleAt` use `twcVin` | OK |
| T4 / T16 | `summary()` keys `key, vin, name, anonymous, userAsserted, tier, claims[{provider,status,commands}], point, lastSeen, lastSeenAge, lastSeenSource, fields` | `vehicles.html.j2` columns (tier, `provider (status)`, `ageText(lastSeenAge) via lastSeenSource`, `Unknown car on TWC <point>`) | OK |
| T5 / T10 | `ReadSource.fetch` returns `{field: value}` to record, `{}` when the source wrote the values itself, or `None` | `TeslaBLEReadSource` maps `get_charge_state`/`get_location_state` output | GAP: `get_charge_state` returns `cs.get(...)` for every key, so absent keys come back as `None`. Today `update_charge` skips `None` values (TeslaAPI.py:2384-2405); T10 does not say to filter them, so the cascade would record `None` over good values. |
| T5 / T10 | `cascade()` returns `vehicle.latest(field)` after the first source that does not fail | `TeslaAPIReadSource.fetch` → `update_vehicle_data()`, which returns True **without fetching** while `statusDeferral` is in force (TeslaAPI.py:2286-2287) | GAP: during a deferral (300/1800/3600 s), `fetch` reports success and the cascade hands back the stale value. `update_charge` then returns False (age > 300). Today it returns True, so `car_api_charge`/`applyChargeLimit` will now mark "error" and skip these cars. |
| T5 / T12 | `ReadSource` base | `HomeAssistantReadSource(order=1)` | OK |
| T6 / T7 | `VehicleRegistry` file, `_lock` (RLock), `expire` skips anonymous vehicles | T7 adds plug-session and confirmation state under `_lock` | OK |
| T6 / T8 | `toJSON()`, `load(data)` (ignores garbage), `expire()` | `saveSettings`/`loadSettings`/`expireVehicles` | OK |
| T6 / T9 | `forMaster(master)`, `getOrCreate`, `claim` | `TeslaAPI.registry`, `CarApiVehicle.__init__` | OK. NOTE: `forMaster` must use `getattr`, because `FakeMaster` has no `vehicleRegistry` (T9 `test_master_without_registry_gets_a_private_one`). |
| T6 / T11 | `registerLiveness`, `sourceLiveAt`, `findByName`, `getOrCreate` | `TelmetryBase.__init__`, `updateVehicles` | OK at the interface level; see T11 / main below. |
| T6 / T13 | `getOrCreate`, `claim`, `dropClaim` | `_setBleStatus`, `updateSettings` seed | OK |
| T6 / T15 | `attached(name)`, `get`, `summaries` | Policy, TWCSlave, WebIPCControl | OK |
| T6 / T16 | `addUserAsserted` → `ValueError("VIN must be 17 characters without I, O or Q")` | The T16 test expects `"without+I%2C+O+or+Q"` after `quote_plus` | OK |
| T7 / T15 | Registry holds a VIN only after confirmation | `TWCSlave.getLastVehicle` looks up `currentVIN` and `lastVIN` in the registry | OK. An unconfirmed VIN gives `None`, the same as today's "no API car". |
| T8 / T17 | T8 adds `elif cmd == "expireVehicles"` to `background_tasks_thread` | T17 adds `elif cmd == "bleScan"` | OK |
| T9 / T10 | T9 interim `update_location` else-branch and `RegistryField` descriptors | T10 rewrites `update_location`/`update_charge` | OK |
| **T9 / T11** | T9 makes `CarApiVehicle.syncSource` and `syncTimestamp` **read-only properties** and drops `syncLat/syncLon/syncState` | Until T11, `Telemetry.applyDataToVehicle` assigns `vehicle.syncTimestamp = ...` and `vehicle.syncSource = ...` (Telemetry.py:165-169), and `updateVehicles` assigns `apiVehicle.syncSource` (:236) | **MISMATCH (intermediate state).** Between T9 and T11, every TeslaMate or Fleet Telemetry event for a mapped car raises `AttributeError` on the MQTT thread, and TeslaMate "asleep" is ignored by `is_awake`. The unit tests don't catch it (the telemetry tests use fakes). This breaks the "every task leaves an install working" constraint. |
| T9 / T14 | `CarApiVehicle.vehicle` | `_recordChargeRate` stamps through `getattr(vehicle, "vehicle", None)` | OK. `test_teslaapi_chargerate`'s fake is a `SimpleNamespace`, so the stamp is skipped. |
| T9 / T15 | `apiDebugInterface(command, vin, parameters)`; returns False for an unknown VIN | `/api/sendTeslaAPICommand` passes `vehicleVIN` | OK |
| T10 / T13 | `TeslaBLEReadSource.canRead` requires a `"TeslaBLE"` claim | Claims are created only by T13 (proof, or the `updateSettings` seed) | NOTE on ordering: between T10 and T13 no BLE claims exist, so every read goes to the cloud. On final state, see the seed finding (§3). |
| T10 / T13 | T10 registers the BLE source in `TeslaBLE.__init__` via `VehicleRegistry.forMaster(master)` | T13 sets `self.registry = forMaster(master)` "first thing" in `__init__` | NOTE: two lookups; harmless. |
| T11 / T15 | T11 rewrites `updateVehicles` (it no longer iterates `carapi.getCarApiVehicles()`) | T15 Step 2 expects the grep test to list Telemetry among the failing files | NOTE: stale expectation. Telemetry.py won't match after T11. |
| T12 / T14 | `HomeAssistant.registry` | `applyChargeLimit` stamp via `registry.get(vin)` | OK |
| T13 / T14 | `make()` in `test_teslable_pairing_status.py`; `TeslaBLE.registry` | T14 imports `make as make_ble`; the BLE stamp uses `self.registry.get(vin)` | OK |
| T13 / T17 | `bleStatus(vin) -> {"status","since"}`, default `"unpaired"` | T17 extends it with `label/inRange/scannedAt/scanPending/canScan` | OK |
| T13 / T17 | `test_teslable_pairing_status.py` imports `Mock, patch, threading` | T17 appends `@pytest.mark.parametrize` tests to the same file | MISMATCH (minor): `import pytest` is never added, so the file fails with a NameError at collection. |
| T15 / T16 | Template global `vehicles=lambda: master.vehicleRegistry.vehicles()` | T16 adds the `ageText` and `registry` globals; the T16 test env passes `vehicles=` as a bound method | OK |
| T16 / T17 | `ageText(seconds)`; `env`/`master`/`VIN` helpers | T17 page shows "Last scan: `<ageText>`", but `bleStatus` gives `scannedAt` (an epoch time) | GAP (minor): the template has no `now`/time global to turn `scannedAt` into an age, and the T17 test env has none either. |
| T16 / T13 | `addVehicleByVIN` adds a registry vehicle only | The spec flow is "Add by VIN, then pair from its page". `peerWithVehicle` → `sendPublicKey` needs `settings["Vehicles"][vin]["pubKeyPEM"]`, and keys are generated only for existing `settings["Vehicles"]` entries (`scanForVehicles`, TeslaBLE.py:851-896) | **GAP.** Pairing a manually added VIN fails ("Vehicle not found in settings", so `pairing_failed`). No task generates BLE keys for a user-asserted VIN. |

## 2. Each task checked against itself

| Task | Tests vs code | Files created vs touched later | Interfaces vs steps | Finding |
|---|---|---|---|---|
| T1 | Suite only | — | — | OK. `merge-tree` reproduced exactly (`a1a8107…`, `545831c…`, no conflicts). The picks change `cancelStopCarsCharging(vin=None)`, `startCarsCharging` passes `vin`, and `stopCarsCharging` cancels pending starts. This matches the Interfaces line. |
| **T2** | `test_set_and_get_take_the_lock` and `test_off_thread_master_writers_take_the_lock` set `m.settingsLock = Mock(wraps=threading.RLock())` | — | Interfaces: "single-key reads stay unlocked". Step 3: "`getSetting`/`setSetting` ... `with self.settingsLock:`" | **MISMATCH ×3.** (a) `Mock` does not support `with` (verified: `TypeError: 'Mock' object does not support the context manager protocol`; `.__enter__` raises `AttributeError`), so both tests error out instead of failing for the right reason. `MagicMock(wraps=...)` counts the calls but never really acquires the lock. (b) The test requires `getSetting` (a single-key read) to take the lock, which contradicts ruling 3 and the Interfaces line. (c) Step 3 puts the `loadSettings` file load under the lock, which contradicts the Global Constraint "No lock is held across I/O". |
| T2 | — | Files lists HTTPControl writes `:316, :513-514, :809, :884-885, :923, :1318-1325, :1452-1470, :1640-1710, :1763-1804` | Ruling 3: every non-serial-thread writer | GAP: the list misses HTTPControl `:624` (`del consumptionOffset[...]`) and `:1611-1612` (`del homeLat/homeLon`). It also misses `Control/MQTTControl.py:178` (`settings["nonScheduledAction"] = action` on the MQTT thread). The grep acceptance covers only three files. |
| T3 | The tests import `FEED_LAG` per the note | — | OK | OK |
| T4 | OK | — | OK | OK |
| T5 | `test_all_sources_fail_returns_stale_latest` expects `read()` to return the stale latest | — | Interfaces: `read` → `cascade(...)`; `cascade` returns `Optional[Observation]` with no fallback stated | NOTE: the fallback to `latest` on total failure is defined only by the test. See also T4/T5 above. |
| T6 | OK | — | `load` must set `name`, but the observation source is unspecified | NOTE |
| T7 | OK. The TWCMaster tests line up with `num_cars_charging_now` on main (the 5 s debounce uses `chargingDroppedBelowThresholdTime=1`) | — | OK | OK. NOTE: `queue_background_task(..., delay=5)` is the first real use of the delayed queue. `bisect.insort` on `(datetime, dict)` raises `TypeError` on equal datetimes, and `backgroundTasksDelayed` is an unlocked class-level list shared by the serial and background threads. |
| T8 | OK | — | Files: "`TWCManager.py:962-967` (hourly queue next to `getLifetimekWh`)" | MISMATCH (minor): that block is at `:969-976` and sits inside `if config["config"]["fakeMaster"] == 1`. "Same block" would gate expiry on `fakeMaster == 1`. |
| T9 | OK | Drops the `Thread` patch from `teslatokens.no_threads` (which would otherwise fail because `monkeypatch.setattr` raises on a missing attribute) | `RegistryField.__set__` always observes | GAP: `update_vehicle_data` writes `self.x = charge.get(key, self.x)` (TeslaAPI.py:2322-2342). With descriptors, a missing key re-observes the previous value, or the legacy default (`10000`, `-1`, `"Unknown"`), as a fresh `"TeslaAPI"` reading. That gives the wrong source and time, and turns sentinels into real values. |
| T10 | OK | — | `update_location(minInterval=0)` → `maxAge = minInterval or READ_MAX_AGE` | MISMATCH: `0 or 300` is 300. `vehicleIsDefinitelyHome` (TeslaAPI.py:1885) calls `update_location(0)` and clears `statusDeferral` specifically to force a real fetch, so a lat under 300 s old will now skip the forced read. |
| **T11** | The tests exercise `TelmetryBase.mqttConnect` through `Probe` | — | Interfaces: `connected=True` set in `TelmetryBase.mqttConnect` | **MISMATCH with main:** `TeslaMateVehicle.mqttConnect` (:302) and `FleetTelemetryMQTT.mqttConnect` (:32) override it without calling `super()`. So `connected` is never True for the real modules, liveness is always `None`, and the report-on-change rule never activates in production. `syncSource` then falls back to `"TeslaAPI"` an hour after the last state change. Also, "`mqttMessage` reads the previous state via `latest("state")`" needs `.value` and a None guard. |
| T12 | OK | — | `refresh_from_home_assistant` does `api.registry.get(self.vin).observe(...)` | NOTE: unguarded `None` if the vehicle isn't in the registry. |
| T13 | OK | — | `_setBleStatus` creates `settings["Vehicles"][vin]` if it is absent, without `chargeSessions` | NOTE: if a VIN's entry is created this way, a later `recordVehicleVIN` `else` branch does `["chargeSessions"] += 1` and raises `KeyError` on the serial thread. |
| T14 | Two of the five tests are described in prose only ("Plus one test each ...") | — | OK | NOTE |
| T15 | The grep test asserts an exact file list | — | Step 2's expected failure list includes Telemetry | NOTE: stale (see T11/T15). |
| T16 | OK | — | "Held limit (from `master.getNormalChargeLimit(vin)`)" | MISMATCH with main: TeslaAPI keys `chargeLimits` by numeric `vehicle.ID` (TeslaAPI.py:1067, 1115, 1165, 1167, 1184); only TeslaBLE keys by VIN. Limits held by the API show "—". |
| T17 | Appended tests use `pytest` without importing it | — | `requestRangeScan` → `queue_background_task({"cmd":"bleScan","vin":vin})` | MISMATCH (minor): `queue_background_task` coalesces by `cmd` (TWCMaster.py:1282-1288), so a second scan request for another VIN overwrites the first and leaves the first VIN's `pending` stuck at "Scanning…". |

## 3. Cross-cutting findings

### 3a. Tasks contradicting each other or the Global Constraints

1. T3 tie rule vs the T11 test (equal timestamps): one of the two must change.
2. T4 (`age`/`trusted` need `registry.sourceLiveAt`) vs the T5 registry protocol and test stub (only `readSources`).
3. T9 vs T11 ordering: the read-only `syncSource`/`syncTimestamp` break telemetry between T9 and T11. This violates "every task leaves an install working".
4. T2 Step 3 (`loadSettings` file I/O under `settingsLock`) vs the Global Constraint "No lock is held across I/O".
5. T2's test (`getSetting` takes the lock) vs ruling 3 and T2's own Interfaces ("single-key reads stay unlocked").
6. T13 `updateSettings` scans `settings["Vehicles"]` and calls `registry.getOrCreate`. This contradicts the literal Global Constraint "the registry never scans it to create vehicles". It is covered by ruling 6 (key storage, not history), so it is listed for completeness only.
7. T7 locks a serial-thread writer (`recordVehicleVIN`), although T2 says serial-thread writers stay as they are. This is intentional and the lock is short; noted only.

### 3b. Plan-mandated items a reviewer would flag

1. T2: two tests built on `Mock(wraps=RLock())` cannot run (`TypeError` at `with`). As `MagicMock` they would count `__enter__` calls without exercising a real lock.
2. T15 `test_no_caller_outside_teslaapi_reaches_for_its_list` asserts on a `git grep` of the source text, not on behaviour. It is brittle, and it depends on the cwd and on the files being tracked.
3. T17 test additions: missing `import pytest`.
4. T3 `REPORT_ON_CHANGE_SOURCES` is defined and never used; T6's `registerLiveness` is the real definition.
5. T2 `make()` carries a dead `vehicleRegistry` Mock from T2 until T8 removes it.

No test was found that asserts nothing, and no verbatim duplicated logic is mandated.

### 3c. Spec requirements for Phase 0-1 with no task

1. **Manual add, then pair** (spec "Bootstrap / manual add": "The user then pairs BLE from its page, which makes it managed"). No task generates BLE keys for a user-asserted VIN, so pairing fails (see T16/T13).
2. The **`bleReach` field** is in `FIELDS`, but nothing writes it. The T17 scan result stays in `TeslaBLE._rangeScan`. Spec: "BLE reach" is a field, and "presence probes, command replies and TWC heartbeats all write to the same fields". The TWC heartbeat (`actualCurrent`) is explicitly deferred to Phase 2. Command replies are not written to fields (only own-write stamps).
3. Forgetting: the spec says "a managed vehicle that loses its last command path drops to observed and ages out". Ruling 4 instead keeps any car with any claim, including a non-commanding Owner listing, so an Owner-listed car never ages out. This is already ruled and listed for traceability.
4. The Vehicles list omits presence and the attempt/backoff columns, and the Forget action. The plan and roadmap defer these to Phases 3, 5 and 6, so this is consistent.

### 3d. Plan claims about origin/main checked

| Claim | Result |
|---|---|
| T1 `merge-tree` trees `a1a8107…` / `545831c…`, conflict-free | Correct (reproduced) |
| TWCMaster `__init__ :93`, `loadSettings :1010`, `num_cars_charging_now :1201`, `recordVehicleVIN :1405`, `saveSettings :1521`, `getSetting/setSetting :1582-1601`, `startCarsCharging :1889`, `stopCarsCharging :1901` | Correct on main (before the T1 shift) |
| `recordVehicleVIN` is called on every completed VIN parse, so a re-query yields a second call | Correct (TWCManager.py:1550-1559, no change-only guard) |
| TWCManager.py `:376-392` background `elif` chain | Correct (~:371-391) |
| TWCManager.py `:962-967` getLifetimekWh hourly block | **Wrong**: it is `:969-976`, inside `fakeMaster == 1` |
| TWCManager.py `:585-631` `update_sunrise_sunset` | Correct |
| TeslaAPI `__init__ :116`, `addVehicle :163`, `CarApiVehicle :1975`, `is_awake :2096`, `update_location :2223`, `update_charge :2371`, `actualCurrent :2424`, `apply_charge_limit :2433`, `setChargeRate :1743`, `_recordChargeRate` (static) `:1834` | Correct |
| `TeslaAPI.readOnly` usable as an attribute in `lambda: not carapi.readOnly` | Correct (`@property`, :305) |
| `TeslaAPIController._telemetryPluggedIn` keeps working through `syncSource` | Correct (it uses `getattr(vehicle, "syncSource", ...)`, :89-92) |
| TeslaBLE `__init__ :98-185`, `peerWithVehicle :410`, `_sendCommand_internal :489` (`@_serialized`), `setChargeRate(charge_rate, vehicle=None, ...)` `:587`, `applyChargeLimit :668`, `scanForVehicles :851`, `_fetch_state_json :936` (`@_serialized`), `updateSettings :1477` | Correct. NOTE: the second argument of `setChargeRate` is `vehicle`, and the T14 test passes the VIN positionally, which works. |
| `_run_command_with_timeout(command_string, timeout, use_process_group=True)` | Correct |
| BLE local name `5YJ3E1EA1KF000001` → `Sa3b631dfdbc5cf49C` | Correct (recomputed) |
| Ruling 6 seed: `BLEPeeringStatus == "peered"` or `bleProven` | **Never true on main.** `BLEPeeringStatus` has only ever been *read* (template, since 6d3d16b) and never written. `bleProven` exists only on the presence branches (`deploy/presence-3`). An install upgrading from main gets no BLE claims until its first successful BLE command, so T10's BLE read source is skipped and every read goes to the cloud until then. |
| Telemetry `mqttConnect` sets the liveness flag | **Wrong for the real modules** (both subclasses override `mqttConnect` without `super()`) |
| HomeAssistant `refresh_from_home_assistant :88`, `__init__ :151`, `_build_vehicles_from_registry :308` (needs a tesla manufacturer, `battery_level_sensor` and `charge_switch`); `has_*` are properties | Correct |
| HomeAssistant.py contains `getCarApiVehicles` (expected in the T15 grep list) | Correct (`def getCarApiVehicles`, :495) |
| HTTPControl `:208-210` globals, `:774-793` sendTeslaAPICommand, `/vehicle/localMgmt :1490` | Correct |
| Policy `:273`, TWCSlave `:586-592`, `:1240` `getLastVehicle`, `TWCSlave(TWCID, maxAmps, config, master)`, WebIPCControl `:347`, debug.js `:42`, debug.html.j2 `:74-76`, settings.html.j2 `:256,268` | Correct |
| `vehicleDetail.html.j2 :79` indexes `settings["Vehicles"][vin]["chargeSessions"]` unguarded | Correct (Review Focus 5 is real) |
| Held limits looked up by VIN | **Partly wrong** (TeslaAPI keys them by numeric ID) |
| Packaging picks up `Vehicle/Registry/` | Correct (`find_namespace_packages(where="lib")`) |
