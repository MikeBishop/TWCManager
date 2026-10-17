# Task 3 review: CarApiVehicle dissolves

Reviewed f82744e..7d946ab (424be4b, eebe6df, 7d946ab) in `wt-vm35`. Read-only; mutation checks ran in a scratch copy (`scratchpad/mut`), never the worktree.

**Spec: ✅. Quality: approved.** There are no Critical or Important findings. Three Minor items and three Notes follow; none blocks the task.

## Verification run

- Unit suite (`tests --ignore=tests/API --ignore=tests/integration`): **1780 passed, 1 xfailed**. This matches the report.
- Step 5 greps:
  - The removed-names grep over `lib html tests/integration tests/API docs` gives 0 hits.
  - `git grep "\.forget(" -- lib` gives only `HTTPControl.py:121 forget(vin, ifUnattached=True)`.
- `black --check` passes on all 10 changed lib files.
- Test names, BASE against HEAD: exactly the 4 tests named in the report were removed, and 11 were added. No other test disappeared.
- Mutation checks, run on a copy. Two tests fail in the copy under every mutation and are environmental: `test_sigterm_shutdown` and the git-grep `test_update_vehicle_data_has_a_single_caller`.

| Mutation | Caught by |
|---|---|
| `located()` never asks TeslaAPI | 23 tests (`test_limit_wiring`, `test_command_path_parity`, …) |
| `update_vehicle_data` loses its `statusDeferral` re-check | `test_two_concurrent_reads_pay_one_vehicle_data` |
| `_ready`'s second `is_awake` forced True | `test_vehicle_data_rechecks_online_when_the_cache_expired` |
| `forget(ifUnattached)` check removed | `test_forget_if_unattached_is_atomic`, `test_forget_refuses_a_car_listed_after_the_check` |
| `getOrCreate` attaches after releasing `_lock` | `test_forget_if_unattached_is_atomic` |
| `wakeOutcome` loses the `awake is None` branch | `test_no_wake_without_a_free_answer` |
| A failed GET caches False rather than None | 3 tests, including `test_a_cached_failed_check_stays_unknown` and `test_online_state_…` |
| A wake answering online does not refresh the cache | `test_a_wake_answering_online_refreshes_the_online_cache`, plus 2 parity tests |
| `stopCharging` `is False` → `is not True` | **nothing** (finding m2) |
| `vehicleIsDefinitelyHome` drops the exact-case match | **nothing** (Note n3) |

## Spec compliance

- **`_ready` is today's `ready()` gate for gate** (TeslaAPI.py:1540ff).
  - The per-car backoff and its INFO8 line come first.
  - Then the 2-minute `lastAPIAccessTime` shortcut when `firstWakeAttemptTime == 0`.
  - Then the second `self.is_awake(vehicle)` with slot None and clock `self.now()`.
  - Then the INFO8 line on failure.
  - F6 is pinned.
- **The online state maps exactly.**
  - Telemetry branch: asleep/offline gives False; fresh data gives the bool. Both were Known=True.
  - Cache hit returns `car.online`. Checked=False implied State=False, so this gives None.
  - GET: `online if result else None`.
  - Initial state: `online = None` and `onlineCheckedAt = 0`.
  - `is_awake = bool(onlineState)`, so it is still a bool and False for no answer.
  - Only `wakeOutcome` (:1355) and `FleetAPIProvider.stopCharging` (:167) read the three-state.
  - `stopCharging`'s `onlineState(...) is False` equals the old `not is_awake and lastVehicleAwakeKnown` on every path. That includes a fresh telemetry state outside the active set, which gives False with Known=True.
- **A wake answering online** sets `car.online, car.onlineCheckedAt = True, now`, in that order.
- **`get_car_api(checkReady)`** stands in for the equal pair `checkReady`/`provesOnline` that every lib caller passed. `lastAPIAccessTime` is set only with `checkReady`, matching the lib callers. F12's test-only differences are listed in the report.
- **`update_vehicle_data`** keeps the deferral re-check, with a comment explaining why.
  - `lat` is observed before `lon`, and both are read back through the registry, as the descriptors did.
  - Only keys present in the response are observed.
- **No new paid calls.** The online cache, the per-car backoff, the wake hold, the status deferral (both checks) and the 2-minute shortcut all key on the same record and the same clocks.
  - `Targets.located` → `TeslaAPI.locate` is free.
  - `update_location` runs only in `_restoreDeparted(read=True)` (background) and in `vehicleIsDefinitelyHome` (background), as before.
- **Registry:**
  - `getOrCreate(attach=)` attaches under `_lock`, giving registry → vehicle leaf order. That is the same order `expire` already uses.
  - `forget(ifUnattached)` reads `userAsserted`/`attachmentNames()` under `_lock`. Its log and `removed` callback stay outside the lock.
  - `forgetVehicle` calls `canForgetVehicle`, which takes `settingsLock` and releases it, then calls `forget` with no `settingsLock` held. The settings cleanup runs only after a successful forget.
  - Every `attach` in lib now goes through `getOrCreate` (`VehicleRegistry.py:91` is the only `.attach(` call), so Forget is atomic with every provider's attach, not only TeslaAPI's.
- **Attachment consumers outside the diff still work against `CarApiState`:**
  - `Gen3TWC.py:281` (`getattr(api, "atHome", False)`);
  - `HTTPControl.py:514` (`.atHome`);
  - `TWCSlave.getLastVehicle`;
  - `debug.html.j2:74` (the truthiness of the attachment; `CarApiState` defines no `__bool__`/`__len__`).

  Gen3 correlation is unaffected.
- **Defaults** on former descriptor reads:
  - `lat`/`lon` 10000, `batteryLevel` 10000, `gpsAsOf` 0, `scheduledChargingPending` False;
  - `name` is `""` through `Vehicle.name`.

  All match the old `RegistryField` defaults.
- **The INTENTIONALLY CHANGED edges** (`json["id"]`, the pair return of `attached`, sorted-VIN order, the display-name fallback upper-cased) are all listed in the brief or the report.

## Findings

### Minor

**m1. The expiry window between the attach and the keep-alive claims is no longer recovered.** (`TeslaAPI.py:236–241`; `VehicleRegistry.py:153–166`)
- The problem:
  - `addVehicle` attaches under `_lock` but claims afterwards, outside it.
  - `expire` skips only `keepsAlive` claims, not attachments.
  - So a persisted, unasserted car already past `forgetAfter` that is first listed while `expire` runs on another thread can be expired after the attach and before the claim.
- Where it can happen: `Telemetry.updateVehicles` (:365) calls `loadVehicleList` on the paho MQTT thread, while `expireVehicles` runs on the background thread.
- Why it matters now:
  - At BASE the same window existed, but the old `_liveVehicle`/`vehicle` rejoin re-created the car on the next write.
  - Now the car silently drops out of `attached("TeslaAPI")` until a restart, unless it was the only listed car, in which case the next `loadList` re-lists it.
  - This is the one hole in the brief's F7 argument ("expire skips any vehicle with a keepsAlive claim").
- Likelihood: tiny. It needs a stale persisted car at the first listing, and the hourly expire racing an MQTT-thread listing.
- Fix: in `expire` (:162), also skip `v.attachmentNames()`. That is one token and makes "attached ⇒ never expired" true by construction.

**m2. The None leg of `stopCharging`'s three-state is unpinned.** (`TeslaAPIProviders.py:167`)
- Changing `is False` to `is not True` passes the whole suite. With that change, a failed online check would settle a stop as "asleep, not charging" without sending it.
- This is pre-existing: deleting `and car.lastVehicleAwakeKnown` at BASE also passed the suite (checked on a BASE copy).
- The brief's review focus names this site as one of only two readers of the three-state, so it deserves a pin.
- Suggested test: a GET 500 on the online check, then `p.stopCharging(VIN)` sends the stop command (1 POST) rather than returning SATISFIED.

**m3. `new_api` pops the master's instance `getModuleByName`.** (`teslatokens.py:121`)
- It strips whatever instance-level `getModuleByName` the master carries, not only `make()`'s Mock.
- If a test ever called `gen2_helpers.drive()` before `new_api(master=m)`, the drive stubs (Policy, Dummy) would vanish, and the cached `_driveStubs` would stop them being re-installed.
- No current test does this: a scripted check found no function that does both, and the helpers that call `new_api` (`fanOutCars`, amps :146, parity :182) run before any drive.
- The change is otherwise sound (see Q5). A narrower form would pop only when the attribute is a `Mock`, or would have `make()` stub through `modules.get`.

### Notes

**n1. No None guard is needed in `Targets.located` / `_restoreDeparted`.** This is Q1, answered: unreachable in every supported configuration.
- `Vehicle.TeslaAPI` is always in `modules_available` (TWCManager.py:86).
- Its config-skip check looks at `config["Vehicle"]["TeslaAPI"]`, because `translateModuleNameToConfig` passes `Vehicle.*` through unchanged. So `vehicle.teslaAPI.enabled` never skips the load.
- HA-only, BLE-only and TeslaMate-only installs therefore load an enabled TeslaAPI. `getModuleByName` returns it, and with no tokens nothing lists, so `located()` returns None at the attachment check, before any lookup.
- With `vehicle.teslaAPI.enabled: false` (documented in `etc/twcmanager/config.json:828`), or `Vehicle.TeslaAPI.enabled: false`, or a failed import, `getModuleByName("TeslaAPI")` is None, and **startup already crashes at BASE**:
  - `master.loadSettings()` (TWCManager.py:805) calls `carapi.migrateSavedTokens` on None (TWCMaster.py:1169/1175);
  - `saveSettings` (:1631) does the same.

  Both happen before the serial loop or the background thread starts.
- `_enabled` is set once, in `__init__`, and never changes. The only way to attach "TeslaAPI" is `addVehicle` on the one module instance.
- So no configuration has an attached car and a None module. A raise is impossible today.
- If "TeslaAPI disabled" is ever made to work, `loadSettings`/`saveSettings` must change first. `located` should then gain `api = …; if api is None: return None`.

**n2. The `statusDeferral` double-read guard is the same check-then-act as BASE.** Two threads that both pass `update_vehicle_data`'s check before either sets the deferral can still both pay. That interleaving is narrower than the one the new test pins, and it was not made worse here.

**n3. `vehicleIsDefinitelyHome` / `vehicleScheduledChargingPending` keep an exact-case match that no test pins.** Every caller passes an upper-case registry key, so this is harmless.

## Q2: line count (−74 against an estimated ≈ −130)

No parallel structure was found.
- `CarApiState`'s fields are API-only bookkeeping:
  - `atHome` has no registry counterpart;
  - `lastAPIAccessTime` is "proven awake by the API", not `Vehicle.lastSeen`, which any observation bumps;
  - `online`/`onlineCheckedAt` are the free-check cache, not `telemetryState()`.
- `addVehicle` does only what `CarApiVehicle.__init__` + `_bind` did. `getOrCreate` does the find-or-create and the attach; `addVehicle` adds only the claims and the name.
- The shortfall is the 15-line record plus black wrapping, not leftover duplication.

Behaviour-neutral savings remain. Each was black-checked in a scratch file.

| Where | Change | Δ |
|---|---|---|
| `TeslaAPI.py:1483–1516` `vehicleIsDefinitelyHome` | `say = functools.partial(logger.log, logging.INFO2)` (+1 for `import functools`). The three log calls then fit on one line each. Fold `updated = …` into the `if`. The brief's "inline `say()`" estimate of −3 went the other way, to +1, because black wraps `logger.log(logging.INFO2, …)` to 5 lines. | ≈ −8 |
| `TeslaAPI.py:1525–1533` `minBatteryLevelAtHome` | `cars = self.registry.attached("TeslaAPI")`, then `return min([... for v, c in cars if c.atHome] or [10000])`. Black gives 4 lines in place of 7. The value is the same, including the 10000 default. | ≈ −3 |
| `VehicleRegistry.py:98–101` `getOrCreate` | `def getOrCreate(self, vin: str, source: str, attach=None) -> Vehicle:` fits on one line. This drops the `Optional[Tuple[str, Any]]` annotation the brief wrote. | −2 (optional) |

That totals about −13, for a lib Δ of about −87. Nothing else is worth taking without going past the brief. One small option: `command`/`_paidPost` each re-fetch `vehicle.attachment("TeslaAPI")`, and `_paidPost` could take `car` from `command`/`wakeOutcome`, saving about 0–1 lines. It is not worth the signature churn.

## Q3: thread safety of `CarApiState`

The fields are plain attributes with no lock, which is exactly as they were on `CarApiVehicle`. Every single assignment is atomic under the GIL.

| Field | Written by | Read by |
|---|---|---|
| `atHome` | `locate` (serial thread via `located`; policy and broadcast); `update_location`/`update_vehicle_data` (background, cloud worker); `vehicleIsDefinitelyHome` (background) | `VehicleEndpoints`, `Targets`, `Gen3TWC`, `HTTPControl` |
| `online`/`onlineCheckedAt` | Written as a pair, in the order `online` → `onlineCheckedAt`. A racing reader that sees the new timestamp therefore sees the new value. One that sees the old timestamp pays only a free GET. | |
| backoff, wake-hold and deferral fields | the same threads as at BASE | |

- **Improvement:** the old `lastVehicleAwakeKnown` was a side-channel that one thread's `is_awake` could overwrite before another thread's `wakeOutcome`/`stopCharging` read it. `onlineState` returns the value directly, so that cross-thread race is gone.
- `attached()` takes a snapshot under `_lock` and then reads each attachment under its leaf lock. The old code iterated a shared class-level list without a lock.
- No I/O happens under any lock in the new code. `addVehicle` runs under `vehicleListLock` → registry → leaf, as `CarApiVehicle.__init__` did.

## Q4: deleted and rewritten tests

- The deleted tests are exactly the 4 in the report's table; the name diff confirms this.
- The three forget/relist tests are covered by the two atomic-forget tests and `test_a_listed_car_is_never_expired`. Mutations confirm both pins.
- On the `pluggedIn None` / `chargingState "Unknown"` defaults, the implementer's claim is **verified**. At BASE no lib or template code read `.pluggedIn`/`.chargingState` as attributes (`git grep` on f82744e found 0). Every current reader goes through `v.value(...)`/`latest(...)` with its own default: `VehicleEndpoints.py:85`, `VehicleEndpoint.py:63,68,126`, `Gen3TWC.py:274`, `TWCSlave.py:115`. Leaving those two defaults unpinned is correct.
- `test_a_cached_failed_check_stays_unknown` keeps `is_awake(...) is False`. Its known/unknown reads became `onlineState(...) is None`, and the M7 mutation shows it still bites.

## Q5: `new_api` module-record plumbing

The tests do not pass for the wrong reason.
- At BASE, `new_api` stored the raw `api` in `m.modules`. That is not a module record, so four tests had to `del` it, and `make()`'s Mock stub hid the lookup.
- Registering `{"ref": api, "type": "Vehicle"}` is what production does (`registerModule`), and is needed now that `located()` resolves the module.
- The "`located()` never asks TeslaAPI" mutation fails 23 tests, including the 3 parity tests and 9 `test_limit_wiring` tests that use this plumbing. So these tests really exercise the module lookup and do not slip past it.
- The affected masters register no other modules (grepped for `registerModule`/`.modules[`), so the real lookup returns None for everything else, as the stub did.
- See m3 for the one fragility.
