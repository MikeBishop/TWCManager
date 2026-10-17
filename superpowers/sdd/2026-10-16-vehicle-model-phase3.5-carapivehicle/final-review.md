# Phase 3.5 final whole-branch review (db47522..e7973a3)

Verdict: **ready**. No Critical or Important findings. There are three Minors: one needs a ledger ruling, and two are orphans the sweep missed. The extra savings at the end are optional.

## Evidence run

- **Unit suite at HEAD:** 1782 passed, 1 xfailed (BASE: 1764 passed, 1 xfailed).
- **Integration (`tests/integration`):** I started a local TWCManager from `etc/twcmanager/.testconfig.json`, the CI recipe, on :8088.
  - 209 passed, 2 skipped, 1 failed.
  - The failure is `test_stress_scenarios.py::TestContinuousOperation::test_60_second_continuous_operation`. It runs about 80 s by design, so the mandated `--timeout=60` kills it. Rerun alone with `--timeout=120`, it passes.
  - The temporary `config.json` is removed and the server is stopped; the worktree is clean.
- **Paid-call oracle (`test_command_path_parity.py`):** 31/31 pass at HEAD with their count assertions untouched.
  - The only edit is plumbing: `del m.modules["TeslaAPI"]` is gone, because `new_api()` now registers a real module record on a `TWCMaster`.
  - That edit is not neutral by construction. At BASE, simply dropping the `del` breaks 3 parity tests (a raw object in `m.modules`).
  - So I gave BASE the same environment: HEAD's `new_api` record registration with the real `getModuleByName`. BASE then passes 31/31, so the richer environment does not hide a count change.
- **Request-log differential (strongest evidence).** A pytest plugin wrapped `requests_mock.adapter.Adapter.send` and counted every mocked request per test, keyed by method plus `vehicle_data` / `wake_up` / `command/<name>` or the path.
  - I ran it over the whole unit suite at BASE (with the module-record shim above) and at HEAD.
  - All **211 tests common to both** issue identical request multisets: **0 diffs**, paid or free.
  - The 6 tests that exist only at HEAD are the new characterization and interface tests.
  - This covers the parity scenarios (box ble_only overnight, prefer_ble with BLE down, Fleet-only, Gen3 without BLE, HA-only, TeslaMate telemetry), the per-car 429 backoff, the 120 s cache, the wake hold, status deferral, departure reads and restores, and the restart-asleep tests.
- **Lines:** lib is 27,123: −147 from BASE (27,270), still 373 over the 26,750 target. `git diff --shortstat db47522 -- lib`: 13 files, +459 / −606. Matches the ledger.
- **pyflakes on the 13 changed lib files:** nothing new versus BASE.

## Cross-task and whole-system checks (passed)

1. **Paid calls.**
   - `_ready` is BASE `ready()` gate for gate: per-car backoff with its INFO8 line, then the 2-minute `lastAPIAccessTime` shortcut, then the second `is_awake(vehicle)` with the default slot and clock (F6).
   - `update_vehicle_data` keeps its deferral re-check (TeslaAPI.py:1734).
   - `fetch` keeps its deferral, then the free check, then `vehicle_data` (TeslaAPIProviders.py:46–59).
   - No new caller of `get_car_api` / `update_vehicle_data` / `wakeOutcome` / `command`. `git grep` shows one provider caller each.
2. **Online cache (F3).** BASE `(State, Known)` maps to HEAD `online` on every path:
   - The telemetry asleep path returns False without touching the cache, as at BASE.
   - The fresh-telemetry path returns early.
   - A cache hit returns `online`. BASE gave Known=Checked, and Checked False implies State False, so this matches.
   - A GET sets `online` to True/False when it answered, else None.
   - A wake answering online sets `(True, now)`.
   - `is_awake` is `bool(onlineState)`, so False for no answer.
   - Only `wakeOutcome` (TeslaAPI.py:1356) and `stopCharging` (TeslaAPIProviders.py:167, `is False`) see the three-state. The new test `test_a_failed_online_check_still_sends_the_stop` pins the "no answer is not asleep" leg.
3. **Per-car state stays per car.**
   - The 429 branch writes `car or self` (TeslaAPI.py:426).
   - Every backoff, wake-hold and charge-need helper now takes the `CarApiState`.
   - Every caller passes `vehicle.attachment("TeslaAPI")` (grep of all 30 call sites).
   - No caller passes a registry `Vehicle` where a record is expected. `Vehicle` has no `lastErrorTime`, so such a call would raise rather than silently share state.
4. **atHome from free positions, and the restart with the car plugged in and asleep.**
   - `located(master, v)` returns before the module lookup when there is no attachment.
   - Otherwise `locate(vehicle)` is free: it reads registry lat/lon and sets `car.atHome`.
   - The record is created at listing, as `CarApiVehicle` was, so a TeslaMate position that lands before the list behaves as at BASE.
   - Both restart tests (parity and limit_wiring) pass, and both make zero requests in the differential.
5. **Anonymous Gen2 fan-out.**
   - `_anonCars` iterates `attached("TeslaAPI")`, which is `vehicles()` order (sorted VIN). BASE iterated the same `vehicles()`, so there is no order change. The old "list order" comment was already wrong at BASE and is now corrected.
   - `allEVSEs` dropping the `isAnonymous` skip is neutral: only `getOrCreate`, with a well-formed VIN, attaches.
6. **Held limits (Task 1 against BASE, case by case).**
   - At load, a VIN key whose store entry exists (even malformed) is skipped. HEAD gets this from `vin in loaded and (isVin or …)`, since `loaded` is the store's VIN keys before the pass.
   - At resolve, an ID whose VIN is in `_loadedVins` with a good entry is kept, with the info line `(own, legacy)`.
   - An ID whose VIN is in `_loadedVins` but with a malformed or absent entry is replaced by the legacy value. This includes a VIN `remove()`d after load: BASE `_storedEntry(...) is None` and HEAD `own is None` both write the legacy entry.
   - An ID whose VIN was recorded since load merges as `(legacy.outside, own.held)` with info `(legacy, own)`. That is semantics (b).
   - Two IDs naming one unloaded VIN merge as at BASE. The F10 malformed-loaded edge is accepted.
   - Semantics (a) lives in `TeslaAPI.resolveHeldLimits`, which is unchanged (every usable slot's list must be a list, and the union must be non-empty). `waiting()` is False before `load()` and requires a dict (F9).
   - Concurrent resolves are idempotent. `waiting()` is read unlocked, but a second `_migrate(final=True)` finds `chargeLimits` gone (not a dict) and returns without saving.
   - `settings["chargeLimits"]` has no other writer in lib. `loadSettings` runs once (TWCManager.py:805), so the in-memory `_waiting` copy carried nothing the settings key does not.
   - Upgrade from 1.3.x (`chargeLimits` only) and from phase3 (`heldLimits` present) are both covered by `test_held_limits.py`. The box's phase3 settings have no `"id:"` keys (controller check).
7. **Atomic forget.**
   - `forget(ifUnattached=True)` re-checks `userAsserted` and `attachmentNames()` under `registry._lock`.
   - `_getOrCreate(attach=)` attaches under the same lock.
   - `canForgetVehicle` already refused any attachment at BASE, so HA-attached cars are not newly refused.
   - `forgetVehicle` releases `settingsLock` (inside `canForgetVehicle`) before `forget` and takes it again only after a successful forget.
   - The guard test pins the single `.forget(` call site.
8. **Lock order.**
   - `registry._lock → Vehicle._lock` (attach, `attachmentNames`, `userAsserted`) is the existing direction (`expire` already read claims there).
   - `vehicleListLock → registry → Vehicle` happens in `loadVehicleList` and `addVehicle`. Nothing takes `vehicleListLock` under a registry or vehicle lock.
   - `_migrate` does dict work only under `settingsLock`; logs and the save come after.
   - `located()` on the serial thread does no I/O: `getModuleByName` plus `locate`, both pure. `update_location` stays on `_restoreDeparted(read=True)` (background) and `vehicleIsDefinitelyHome`, as at BASE.
9. **`getModuleByName("TeslaAPI")` returning None** (Targets.py:28, :139). This is reached only for a car with a TeslaAPI attachment, which needs the module to have listed. A disabled TeslaAPI already crashes at BASE in `loadSettings` (TWCMaster.py:1169–1175). The n1 ruling holds.
10. **Surfaces.**
    - `/api/getSlaveTWCs` reads the same values with the same defaults (10000 / -1 / 0.0; `atHome` from the record), pinned by the Task 2 characterization test.
    - `debug.html.j2:74` still keys on the attachment.
    - The policy properties `numCarsAtHome` / `minBatteryLevelAtHome` (TeslaAPI and HA) keep their values. `min(levels or [10000])` equals `min(..., default=10000)`.
    - `carApiVehicles` is gone (Decision 5).
11. **Gen3.** `Gen3TWC._correlate` reads `getattr(api, "atHome", False)` from the record. `WallConnectorVins` and the `live_status` paths are untouched, and their tests show identical request logs.

## Findings

- **Minor:** `VehicleRegistry.expire` now skips any attached vehicle (lib/TWCManager/Vehicle/Registry/VehicleRegistry.py:158–160).
  - Fix round m1 added this, and it is not in the plan's INTENTIONALLY CHANGED list.
  - It is behaviour-neutral in steady state. Only two attach sites exist (TeslaAPI.py:238 and HomeAssistant.py:398), each followed at once by a `keepsAlive=True` claim, and nothing detaches. So the only difference is closing the attach-to-claim window.
  - It still needs an explicit ledger "Ruling:" line, so a future non-claiming attacher does not inherit unexpirable cars silently.
- **Minor:** dead CarApiVehicle-era branch at lib/TWCManager/Vehicle/TeslaBLE.py:401–403 (`if hasattr(vin, "VIN"): vin = vin.VIN`).
  - No class has `.VIN` after this phase, and all three `sendCommand` callers (TeslaBLE.py:291, :293, :586) pass a string.
  - The Task 4 sweep missed it because it scanned only `def`s in the files Tasks 1–3 touched.
  - Delete it (−3) and add `\.VIN\b` to the guard regex in `test_no_caller_outside_teslaapi_reaches_for_its_list`.
- **Minor:** `from TWCManager.Vehicle.Registry.Vehicle import Vehicle` (lib/TWCManager/Vehicle/TeslaAPI.py:31) exists only for `Vehicle.SYNC_TIMEOUT` at :1571.
  - `vehicle.SYNC_TIMEOUT` reads the same class constant through the instance, and the import goes (−1).
- Nit, no action: `addVehicle` observes the name `json["display_name"] or vehicle.vin`. At BASE the fallback was the raw `json["vin"]`, so a lowercase VIN with no display name would now show uppercased. Tesla sends uppercase, so this is unreachable in practice.

## Remaining behaviour-neutral duplication and savings (optional; −10 to −20 total)

| Where | Copies | Saving | Note |
|---|---|---|---|
| TeslaBLE.py:401–403 `.VIN` object branch | 1 dead | −3 | Minor above |
| TeslaAPI.py:31 `Vehicle` import | 1 | −1 | Minor above |
| TeslaAPI.py:139 `enabled = True`, shadowed by `def enabled` at :226 | 1 dead (pre-existing; pyflakes) | −1 | Policy `getattr` resolves the method either way |
| TeslaAPI.py:1481–1482 and :1486–1487, identical exact-case "listed car by VIN" lookup | 2 | about −2 | One `_listedCar(vin) -> (v, car)` helper |
| TeslaAPI.py:1706, :1718, :1776, `atHome = is_location_home(lat, lon[, gpsAge])`, each re-reading `value("lat"/"lon", 10000)` | 3 | about −3 | A `_placeAt(vehicle, car, gpsAge=None)` helper; `locate`'s home-unknown guard stays at its call site |
| TeslaAPI.py:1740–1765, three try/except blocks with near-identical `logger.error` and return | 3 | about −6 to −8 | One loop keeping the three exact messages, and the lat-before-lon observe order |
| HeldLimits.py:149 and :193–195, `frozenset(k for k in store if isWellFormedVIN(str(k)))` | 2 | about −2 | A module-level `_vins(store)` |
| TeslaAPI.py class attrs `__email`, `__password`, `__resp` | 3 dead (pre-existing) | −3 | Name-mangled, so no policy can reach them; outside this phase. `maxLoginRetries` is policy-reachable: leave it |
| `FleetAPIProvider._listed` (case-insensitive, TeslaAPIProviders.py:141–144) vs the two exact-case TeslaAPI lookups | 3 lookups, 2 case rules | — | Unifying changes a (practically unreachable) case edge: **do not take** without a ruling |
| `car = vehicle.attachment("TeslaAPI")` | 8 in TeslaAPI.py | 0 | A helper saves nothing; listed only so nobody counts it |

Even taking every row, lib stays about 355 over 26,750. The remaining gap is structural, as the plan's Line budget says.
