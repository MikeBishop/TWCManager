# Vehicle Model Phase 3.5: dissolve CarApiVehicle into the registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove TeslaAPI's second per-car object (`CarApiVehicle`) and shrink the held-limit migration, with **no behaviour change**. After this phase:
- a car's data lives once, as registry fields;
- TeslaAPI's per-car logic is ordinary module methods that take the registry `Vehicle`;
- TeslaAPI's own per-car request bookkeeping (online cache, status deferral, wake hold, 429 backoff, `atHome`) is a plain record attached to the registry `Vehicle`.

**Architecture.** `CarApiVehicle` (TeslaAPI.py:1540–1958, 419 lines) does three jobs today:
1. It views registry fields through 15 `RegistryField` descriptors (TeslaAPI.py:39–57, 1569–1583).
2. It holds request bookkeeping that no other module has.
3. It runs the REST read methods.

Job 1 goes: readers call `vehicle.value(field, <the descriptor's default>)`, and writers call `vehicle.observe(field, value, "TeslaAPI")`. Job 3 moves onto `TeslaAPI` as methods taking the registry `Vehicle`. Job 2 becomes `CarApiState`, a 13-attribute record with no methods, attached as `vehicle.attachment("TeslaAPI")`.

The attachment keeps its current meaning, "the Tesla account lists this car", for every existing reader: `debug.html.j2:74`, `canForgetVehicle`, `TWCSlave._anonCars`, Targets, `VehicleEndpoints`, `Gen3TWC._correlate` and both providers' `ready()`. So the anonymous fan-out targets and the expiry exemption are untouched. The Forget refusal becomes atomic: the check and the removal happen under the registry lock (pre-flight F7).

Held limits keep their two user-decided semantics:
- (a) An unmatched numeric ID is dropped, with one warning, only after every usable slot's list came back and they name at least one car.
- (b) A VIN recorded after load merges as `(legacy.outside, store.held)`.

`settings["chargeLimits"]` itself becomes the waiting list, so the in-memory shadow copy and the dev-build `"id:"` keys go.

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `requests_mock`, `pytest` (`tests/unit`).

**Inputs:**
- Spec: `.superpowers/specs/2026-10-13-vehicle-model-design.md`, Goal 1: "one registry … holding all per-vehicle state".
- Roadmap: Phase 3.5 sits between Phase 3 and Phase 4 (`.superpowers/plans/2026-10-15-vehicle-model-phase3-slim.md` "Later").
- Dedup audit, item 1: `.superpowers/sdd/2026-10-15-vehicle-model-phase3-reconcilers/dedup-audit.md`.
- Final review I2 rows 1 and 7: `final-review.md`. What final-fix already took or skipped: `final-fix-report.md`.
- The Phase 3 ledger's "Ruling:" lines are binding.

**Ledger:** `.superpowers/sdd/2026-10-16-vehicle-model-phase3.5-carapivehicle/progress.md` (new).

**Branch:** `vehicle-model/phase3.5` in `scratchpad/wt-vm35`, BASE **db47522** (Phase 3's end). Lib at BASE is **27,270** lines (`find lib -name '*.py' | xargs cat | wc -l`). Target 26,750; origin/main 23,180.

## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `<targets>` = `tests --ignore=tests/API --ignore=tests/integration`.
  - BASE: 1764 passed, 1 xfailed. The full suite must pass after every task.
- **No behaviour change.** Every request, outcome, log level, persisted byte and HTTP/API field stays as it is at BASE. The few places where the rewrite could drift are named in each task, with the test that pins them.
  - A characterization test added in a task must **pass at BASE and after**. Prove it by running it on a scratch checkout of db47522 and recording the result in the report.
  - Log wording may change only where the task says so.
- **Cost.** Prices: `vehicle_data` $0.002, wake $0.02, command $0.001. `vehicles/{vin}`, lists, `/products` and `live_status` are free.
  - No task may add a paid request.
  - `tests/unit/test_command_path_parity.py` is the paid-call oracle. Its request-count assertions are not edited; only object plumbing (how a test reaches the car) may change.
- **Gen3 stays whole:** the shared fake-Neurio headroom and the cloud VIN via `live_status`. `WallConnectorVins.py`, `TeslaAPI._fetchEnergySites/wallConnectorVins*` and the Gen3 solver are out of scope.
- **Threading.**
  - Lock order: `TeslaBLE._bleLock → master.settingsLock → registry leaf`, and `TeslaAPI.vehicleListLock → settingsLock`.
  - `vehicleListLock → registry/Vehicle leaf` is new in name only: `addVehicle` already ran `getOrCreate`/`attach`/`claim` under `vehicleListLock`.
  - No I/O under any lock. No RS-485 I/O off the serial thread.
  - `Vehicle.attachment()` takes `Vehicle._lock` (a leaf) and is safe on the serial thread, as today.
- **Secrets.** No token, refresh token, client secret or Authorization header in any log at any level. Exceptions are logged by type name.
- **Policy reach.** `Policy.policyValue` returns `getattr(module, name)` uncalled. So `TeslaAPI.numCarsAtHome` and `TeslaAPI.minBatteryLevelAtHome` (properties; `Policy.py:312` uses the latter) and HomeAssistant's pair stay, with the same values.
  - `TeslaAPI.carApiVehicles` (a list of objects, undocumented and useless in a policy comparison) goes. This is called out in Task 3.
- **Grep scope for removed names**, run in every task: `git grep -nwE '<names>' -- lib html tests/integration tests/API docs`. Templates live under `lib/TWCManager/Control/themes`. Expect no hits outside the definitions being removed.
- **Deleted-test rule.** Every deleted test is mapped in the task report to one of:
  - a replacement test;
  - PLUMBING-ONLY, with the reason;
  - INTENTIONALLY CHANGED, with the ruling.

  A rewritten test whose assertion values change is INTENTIONALLY CHANGED. One whose only change is how it reaches the car is "plumbing".
- **Line reporting.** Each task reports its lib delta, `find lib -name '*.py' | xargs cat | wc -l` before and after, plus `git diff --shortstat <task BASE> -- lib`. Task 4 reports the total against 26,750.
- Python 3.8 syntax; `black` on touched files only. Commit trailer per the session's attribution reminder.
- Real objects in cross-module tests: `make()` masters, `TeslaAPI` with `requests_mock`, `teslatokens.new_api`, real `VehicleRegistry`. Never mock a success value the real method never returns.

## Review Focus

1. **Paid calls are unchanged.**
   - All of `test_command_path_parity.py` passes with untouched counts, in particular `test_fleet_only_raise_costs_the_same` (free check, wake, `vehicle_data`, command), `test_fleet_failure_is_retried_once` and `test_streaming_telemetry_with_fleet_408_is_bounded`.
   - New: Task 3's `test_car_backoff_blocks_vehicle_data_but_not_the_free_online_check` and `test_vehicle_data_rechecks_online_when_the_cache_expired` (pre-flight F6: `ready()`'s second online check stays, so no edge pays an extra `vehicle_data`).
2. **The restart with the car plugged in and asleep** still gets the scheduled limit over BLE with zero HTTP. Tests: `test_command_path_parity.py::test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit` and `test_limit_wiring.py::test_a_restart_with_the_car_plugged_in_and_asleep_still_gets_the_policy_limit`, both unchanged in their assertions.
3. **Per-car state stays per car:**
   - a 429 on one car's read backs off that car only (`test_teslaapi_request_errors.py::test_every_path_classifies_status_codes`);
   - the 120 s online cache (`test_provider_outcomes_cloud.py::test_a_cached_failed_check_stays_unknown`, its flag reads retargeted to `onlineState`; values unchanged);
   - the wake hold (`test_wake_checks_the_free_online_state_first_and_holds_between_wakes`, `test_an_ended_need_gets_a_fresh_grace_through_wake_outcome`);
   - departure reads (`test_limit_wiring.py::test_a_fleet_car_that_unplugs_and_leaves_gets_its_normal_limit_back`, `test_live_telemetry_places_a_departing_car_for_free`);
   - free-position presence (`test_a_held_car_a_free_position_places_away_gets_its_normal_limit_back`).
4. **Held-limit semantics (a) and (b)** hold: `test_limit_wiring.py::test_legacy_ids_resolve_once_from_the_first_vehicle_list`, `test_a_failed_second_list_defers_the_drop`, `test_an_empty_vehicle_list_drops_nothing` and `test_a_limit_recorded_while_an_id_waits_keeps_the_legacy_normal`.
5. **Surfaces are unchanged:**
   - `/api/getSlaveTWCs` keeps `lastAtHome`/`lastBatterySOC`/`lastChargeLimit`/`lastTimeToFullCharge`, with the legacy defaults 10000 / -1 / 0.0 when unread (Task 2's new characterization test);
   - `debug.html.j2`'s TeslaAPI vehicle list;
   - the policy properties;
   - `canForgetVehicle` refusing a listed car, now with the refusal re-checked atomically inside `VehicleRegistry.forget(..., ifUnattached=True)` (pre-flight F7).

---

## Where every CarApiVehicle member goes (checked against db47522)

| Member (TeslaAPI.py line) | Readers outside the class at BASE | Destination | Task |
|---|---|---|---|
| `RegistryField` (39–57) and the 15 descriptors `name, batteryLevel, chargeLimit, chargingState, availableCurrent, chargeCurrentRequest, voltage, phases, timeToFullCharge, scheduledChargingPending, lat, lon, gpsAsOf, pluggedIn, _actualCurrent` (1569–1583) | `HTTPControl.py:511–514` and `TWCMaster.py:679–692` (via `getLastVehicle`); `Targets.py:66` (`getattr(api,"lat",0)`); `VehicleEndpoints.py:87–89` (`pluggedIn`) | Registry fields. Reads become `vehicle.value(f, D)`, with D the descriptor default below; writes become `vehicle.observe(f, v, "TeslaAPI")` | external readers: 2; internal and deletion: 3 |
| `actualCurrent` property and setter, `lastCurrentChangeTime` (1586, 1939–1958) | none (only `test_carapivehicle_registry.py:50–62`) | deleted; `update_charge` no longer times changes | 2 |
| `syncTimeout`, `_telemetryState`, `syncSource` (1592, 1639–1653) | `Targets.py:136`, `VehicleEndpoints.py:87` | `Vehicle.SYNC_TIMEOUT`, `Vehicle.telemetryState()`, `Vehicle.syncSource` (Registry/Vehicle.py) | 2 |
| `firstWakeAttemptTime, firstChargeNeededTime, lastAPIAccessTime, delayNextWakeAttempt, lastChargeNeededTime, errorCount, lastErrorTime, statusDeferral, atHome` | `TeslaAPIProviders.py:49` (`statusDeferral`); `atHome`: `Targets.py:40,66`, `VehicleEndpoints.py:120`, `EVSEInstance/Gen3TWC.py:281`, `HTTPControl.py:511` | `CarApiState` attributes, same names, same defaults | 3 |
| `lastVehicleAwakeTime/State/Known/Checked` | `TeslaAPIProviders.py:164` (`Known`) | `CarApiState.onlineCheckedAt` and `CarApiState.online` (True/False/None). The three-state is internal: `TeslaAPI.onlineState()` returns it to the two callers that read `Known` today; `is_awake()` still returns a bool (False for no answer), as today (pre-flight F3) | 3 |
| `READ_MAX_AGE = 300` (1565) | — (duplicated as `Reconciler.READ_MAX_AGE = 300.0`, final review I2 row 7) | `Registry/Fields.READ_MAX_AGE = 300.0`, imported by both | 3 |
| `carapi, __config, debuglevel, ID, VIN, _vehicle` | none | deleted (`vehicle.vin` replaces `VIN`; `ID` and `__config` have no reader) | 3 |
| `__init__`, `_bind`, `_liveVehicle`, `vehicle` property (1595–1637) | none | `TeslaAPI.addVehicle` attaches the record and claims once, through `registry.getOrCreate(..., attach=)` under the registry lock. The rejoin-after-forget path goes because Forget becomes atomic (pre-flight F7); see Task 3 | 3 |
| `ready()` (1655–1686) | none (only `get_car_api`) | `TeslaAPI._ready(vehicle, car)`, same three gates in the same order, including the second `is_awake()` (pre-flight F6); called by `get_car_api(checkReady=True)` | 3 |
| `is_awake, get_car_api, _readFresh, update_location, locate, update_vehicle_data, update_charge` | `TeslaAPIProviders.py:55,163`; `Targets.py:26,137`; TeslaAPI's own `wakeOutcome`, `vehicleIsDefinitelyHome`, `updateChargeAtHome` | `TeslaAPI` methods, same names, first parameter the registry `vehicle` | 3 |
| `TeslaAPI.carApiVehicles` (139), `getVehicleByVIN` (779) | `TeslaAPIProviders.py:140`; tests | `registry.attached("TeslaAPI")` (now pairs); `FleetAPIProvider._listed(vin)` | 3 |

**Descriptor defaults:** `name ""`, `batteryLevel 10000`, `chargeLimit -1`, `chargingState "Unknown"`, `availableCurrent 0`, `chargeCurrentRequest None`, `voltage 0`, `phases 0`, `timeToFullCharge 0.0`, `scheduledChargingPending False`, `lat 10000`, `lon 10000`, `gpsAsOf 0`, `pluggedIn None`, `actualCurrent 0`. `Vehicle.value(f, D)` returns `obs.value` whenever an observation exists, even a falsy one, exactly as `RegistryField.__get__` did.

**Other callers checked:**
- `debug.html.j2:74`: the attachment is still truthy.
- `TWCSlave.py:131–137` (`_anonCars`): loops over `attached("TeslaAPI")` pairs (extra saving, Task 3).
- `TWCSlave.py:113`: `located` now takes `master`.
- `TWCSlave.py:1295` (`getLastVehicle`).
- `TeslaBLE.py:185–189`: `vehicleScheduledChargingPending(vin)`.
- `Telemetry.py:363–365`: `getCarApiRetryRemaining()`/`loadVehicleList()` with no car argument, unchanged.
- `TWCManager.py:312–314, 1011–1017`: `loadList`/`listPending`, unchanged.
- `TWCMaster.py:1542–1546`: `vehicleIsDefinitelyHome(vin)`, unchanged.
- `WebIPCControl.py:320`: `getCarApiLastErrorTime()`, unchanged.
- `Policy.py:312`: unchanged.
- `HTTPControl.py:104`, `:117–120`: `canForgetVehicle` keeps its checks; `forgetVehicle` calls `registry.forget(vin, ifUnattached=True)` and redirects to the car page when it refuses (Task 3, F7).
- `TeslaAPI.py:172` (a comment naming `CarApiVehicle.is_awake`): reworded in Task 3; its Step 5 grep forces it (F18).

---

## File structure

- Modified:
  - `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py` (T1);
  - `Vehicle/Registry/Vehicle.py` (T2);
  - `EVSEController/VehicleEndpoints.py`, `TWCSlave.py`, `Control/HTTPControl.py`, `TWCMaster.py`, `Vehicle/Reconcile/Targets.py` (T2, T3);
  - `Vehicle/TeslaAPI.py` (T2, T3);
  - `Vehicle/Providers/TeslaAPIProviders.py`, `Vehicle/Registry/VehicleRegistry.py` (`attached` returns pairs), `Vehicle/Registry/Fields.py` (`READ_MAX_AGE`), `Vehicle/Reconcile/Reconciler.py` (import `READ_MAX_AGE`; comments) (T3).
- Tests:
  - `git mv tests/unit/test_carapivehicle_registry.py tests/unit/test_teslaapi_registry.py` (T3);
  - `teslatokens.py` helpers (T3);
  - the files listed per task.
- Created or deleted lib files: none.

---

### Task 1: Held limits migrate in one pass; `chargeLimits` is the waiting list (expected lib Δ ≈ −48)

Final review I2 row 1. `HeldLimits.load()` (77 lines) and `resolveLegacyIds()` (55) are two versions of one merge. On top of that, `_waiting` is an in-memory copy of exactly what `load()` leaves in `settings["chargeLimits"]` (the well-formed numeric-ID entries), and the `"id:"` store keys were written only by unreleased development builds (Phase 3 Tasks 2–10; only `deploy/phase3-live` = db47522 carries the writer, and it also carries the cleaner. The controller has checked the box: its `heldLimits` holds no `"id:"` keys). One `_migrate(listed, final)` does both passes. The TeslaAPI side (`listPending`, `loadList`, `resolveHeldLimits`, which lists every usable slot) is unchanged: it is what implements semantics (a).

**Files:**
- Modify: `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py`.
  - Delete `_waiting` and the `"id:"` handling (lines 118–123 and 214–215).
  - Delete the test-only `vins()` (lines 281–282; no lib caller; also reword the comment at :247 that names it).
  - Inline `_snapshot` (:275–279) into `holding()`, its only caller once `vins()` is gone (extra saving, ≈ −3).
  - `load()` and `resolveLegacyIds()` become thin callers of `_migrate`.
  - Trim the header comment to describe the one-pass rule.
- Test: `tests/unit/test_held_limits.py`, `tests/unit/test_limit_wiring.py`.

**Interfaces (all callers unchanged):**
- `HeldLimits._loadedVins: Optional[FrozenSet[str]] = None`. None means `load()` has not run, so nothing waits. Otherwise it is the VIN-shaped keys the store held **at the end of** `load()`, including the VINs `load()` itself migrated. This is today's line 154, computed after the loop. A resolve therefore keeps a load-migrated VIN's entry rather than merging into it.
- `HeldLimits.waiting() -> bool`: `legacy = self.master.settings.get(self.LEGACY_KEY)`; `return self._loadedVins is not None and isinstance(legacy, dict) and bool(legacy)`. The dict check is pre-flight F9: a truthy non-dict `chargeLimits` (hand-edited) must not leave `listPending()` True forever, which would list every 5 minutes. At BASE such a value is never waiting either.
- `HeldLimits.load() -> None`: `self._migrate({}, final=False)`.
- `HeldLimits.resolveLegacyIds(listed) -> None`:
  - `listed = {str(k): str(v).upper() for k, v in listed.items() if v}`;
  - `if listed and self.waiting(): self._migrate(listed, final=True)`.
- `HeldLimits._migrate(self, listed: Dict[str, str], final: bool) -> None`. One pass under `settingsLock`; logs and the save happen after it is released. The order of checks per legacy entry reproduces both of today's passes exactly:

```python
with self.master.settingsLock:
    settings = self.master.settings
    legacy, store = settings.get(self.LEGACY_KEY), settings.get(self.KEY)
    store = store if isinstance(store, dict) else {}
    # load: the store's own VINs before this pass (today's `vin in store`
    # with `vin not in origin`); resolve: the VINs held when load() ended
    loaded = self._loadedVins if final else frozenset(k for k in store if isWellFormedVIN(str(k)))
    if not isinstance(legacy, dict):
        if not final:
            self._loadedVins = loaded
        return
    keep, written = {}, {}
    for key, value in legacy.items():
        limit, discarded = _legacyEntry(value)
        if limit is None:                                   # load pass only: malformed
            warn("Dropped a malformed chargeLimits entry for %s while migrating", key); continue
        isVin = isWellFormedVIN(str(key))
        vin = str(key).upper() if isVin else listed.get(str(key))
        own = _storedEntry(store.get(vin)) if vin else None
        if vin in loaded and vin not in written and (isVin or own is not None):
            if not isVin:                                   # resolve pass: the store keeps its own
                info("Tesla vehicle ID %s is %s: kept normal limit %s%%, discarded %s%%",
                     key, vin, own.outside, limit.outside)
            continue                                        # a VIN key: silently, no "unheld" warning
        if discarded and not final:
            warn("Kept the normal limit but not the out-of-range held limit of the "
                 "chargeLimits entry for %s while migrating", key)
        if vin is None or not isWellFormedVIN(vin):
            if final:
                warn("Dropped the saved charge limit of Tesla vehicle ID %s, which no "
                     "Tesla account lists: its normal limit was %s%%", key, limit.outside)
            else:
                keep[key] = value                           # waits, on disk where it was
            continue
        if isVin and vin in written:                        # keys differing only in case
            warn("chargeLimits entries %s and %s name the same car; kept %s while "
                 "migrating", written[vin], key, key)
            store[vin] = _encode(limit)
        elif own is None:                                   # absent or malformed: legacy takes it
            store[vin] = _encode(limit)
        else:                                               # recorded since load: keep the hold
            store[vin] = _encode(HeldLimit(limit.outside, own.held))
            info("Tesla vehicle ID %s is %s: kept normal limit %s%%, discarded %s%%",
                 key, vin, limit.outside, own.outside)
        written[vin] = key
    settings[self.KEY] = store
    if keep:
        settings[self.LEGACY_KEY] = keep
    else:
        del settings[self.LEGACY_KEY]
    changed = keep != legacy
    if not final:
        self._loadedVins = frozenset(k for k in store if isWellFormedVIN(str(k)))
# outside the lock: the collected warnings, then the infos
if changed and not final:
    logger.info("Migrated chargeLimits to heldLimits")
if changed:
    self._save()
```

Note on exactness:
- The `(isVin or own is not None)` clause keeps two things as they are today:
  - At load, a VIN key whose store entry exists but is malformed is skipped (today's `vin in store`).
  - At resolve, an ID whose VIN entry is malformed is replaced (`test_resolving_replaces_a_malformed_vin_entry`).
- The collision rule applies only to VIN keys, as today. Two numeric IDs naming one VIN merge as `resolveLegacyIds` does today.
- **INTENTIONALLY CHANGED edge (pre-flight F10, accepted):** two numeric IDs naming one VIN whose entry was **loaded malformed**. BASE keeps the first ID's value: the second sees `kept` through `_loadedVins`. The plan merges the second as `(limit2.outside, own.held)`, because `vin not in written` blocks the skip. It has never been seen in practice: Tesla gives each car one ID. No test pins it, and none is added.
- At `final` every ID is either moved or dropped, so `keep == {}` and the save always runs, as `resolveLegacyIds` does today.
- Messages and levels are today's. Within one pass they come out as all warnings first, then the infos, in key order. Today's order was dropped, unheld, collided, then the infos (I2 merges before I2 drops). This is the only log difference; no test depends on interleaving.

- [ ] **Step 1: Characterization tests (must pass at BASE, then after).** Add to `test_held_limits.py`:
  - `test_waiting_is_false_before_load`: a bare `SimpleNamespace` master (as in `test_store_works_before_load_and_on_a_bare_master`; `load()` never runs) with `settings["chargeLimits"] = {"11": 80}`. `waiting()` is False, and `resolveLegacyIds({11: VIN})` changes nothing. Production has no writer of `chargeLimits` but the settings file, which `loadSettings` reads just before `load()`.
  - `test_an_id_naming_a_vin_load_migrated_keeps_that_entry`: legacy `{VIN: 70, "11": [90, 50]}` → `load()` → `resolveLegacyIds({11: VIN})`. Expect `get(VIN) == HeldLimit(70, None)` and the "kept normal limit 70%, discarded 90%" INFO line. This pins `_loadedVins` being taken after the load pass.
  - `test_an_id_keys_out_of_range_hold_warns_at_load_not_at_resolve`: `{"11": [80, 30]}`. One "Kept the normal limit" warning at `load()`; at `resolveLegacyIds({11: VIN})` no warning, and `get(VIN) == HeldLimit(80, None)`.
  - `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load`: store `{VIN: {"outside": "x"}}`, legacy `{VIN: 80}`. After `load()`, the store entry is unchanged and `chargeLimits` is gone.
  - `test_a_resolve_saves_once_and_logs_no_migrated_line`: after `load()` of `{"11": 80}`, `resolveLegacyIds({11: VIN})` queues exactly one `saveSettings` and logs no "Migrated chargeLimits" line.
- [ ] **Step 2: Retarget the `"id:"` fixture and `vins()` readers.**
  - `test_limit_wiring.py::test_legacy_ids_resolve_once_from_the_first_vehicle_list` (fixture plumbing): the unmatched entry moves from the dev-build store key `"id:44": {"outside": 75, …}` to `chargeLimits["44"]: 75`. **One expected value follows the fixture (pre-flight F4):** l.99's expected `chargeLimits` after load gains `"44": 75`. All other assertions stay: one warning naming 44 and 75%, the final `heldLimits` dict, and 1+1 list GETs. (Task 3 rewrites the same test's re-list at l.115.)
  - `test_held_limits.py` lines 142, 207, 252: `vins()` becomes `sorted(m.settings.get("heldLimits", {}))` or `holding()` (plumbing).
- [ ] **Step 3: Run Step 1 + `test_held_limits.py test_limit_wiring.py test_vehicles_page.py` at BASE** (scratch checkout) → PASS. Record it.
- [ ] **Step 4: Implement** the interfaces above; delete what they replace in the same commit.
- [ ] **Step 5: Full suite** → PASS. Grep `-w` for `_waiting|vins` in HeldLimits callers and `'"id:'` in lib: 0.
- [ ] **Step 6: Commit.** `git commit -m "Migrate held limits in one pass; chargeLimits is the waiting list"`

**Review focus (Task 1):**
- Semantics (a) and (b), and the four Review Focus 4 tests, are unchanged in assertion.
- The lock covers the whole read-modify-write.
- The save still lands in every case today's code saves.
- No `"id:"` handling is left in lib.
- `waiting()` requires a dict (F9).

---

### Task 2: The registry answers sync state; nothing outside TeslaAPI reads CarApiVehicle's data (expected lib Δ ≈ −20)

Callers outside TeslaAPI stop reading `CarApiVehicle` data attributes. The sync-source rule moves to the registry `Vehicle`, where Task 3's `is_awake` also needs it. Two dead members go: `actualCurrent`'s change timing, which nothing in lib reads. `RegistryField` stays until Task 3, because `CarApiVehicle`'s own methods still use it.

**Files:**
- Modify `lib/TWCManager/Vehicle/Registry/Vehicle.py`: add `SYNC_TIMEOUT`, `telemetryState()` and `syncSource`, and import `TELEMETRY_SOURCES` from `.Fields`.
- Modify `Vehicle/TeslaAPI.py`:
  - Delete `CarApiVehicle.syncTimeout/_telemetryState/syncSource`, the `actualCurrent` property and setter, and `lastCurrentChangeTime`.
  - The descriptor `_actualCurrent` becomes `actualCurrent = RegistryField("actualCurrent", 0)`.
  - `update_charge` loses its change timing.
  - `is_awake` calls `vehicle.telemetryState()` on `self._liveVehicle()`, returning `(None, None)` when that is None: the same no-create read as today. Its `self.syncTimeout / 4` becomes `Vehicle.SYNC_TIMEOUT / 4`.
- Modify `TWCSlave.py` (`getLastVehicle`), `Control/HTTPControl.py:509–514`, `TWCMaster.py:679–692`, `EVSEController/VehicleEndpoints.py:81–90,122`, and `Vehicle/Reconcile/Targets.py:66,136`.

**Interfaces:**
- `Vehicle.SYNC_TIMEOUT = 60 * 60`. The comment moves verbatim from `CarApiVehicle.syncTimeout`.
- `Vehicle.telemetryState(self) -> Tuple[Optional[Observation], Optional[float]]`: `(latest "state", None)` unless its source is in `TELEMETRY_SOURCES`, when it is `(obs, self.age("state"))`. This is `_telemetryState` verbatim.
- `Vehicle.syncSource` (property, str): `obs.source` when the age is not None and is ≤ `SYNC_TIMEOUT`, else `"TeslaAPI"`.
- `TWCSlave.getLastVehicle() -> Optional[Vehicle]`: the registry `Vehicle` for `currentVIN`, then `lastVIN`, that has a `"TeslaAPI"` attachment. It is still a lookup only: it never creates a vehicle.
- `/api/getSlaveTWCs` reads, for a non-None `vehicle`:
  - `lastAtHome = vehicle.attachment("TeslaAPI").atHome`;
  - `lastBatterySOC = vehicle.value("batteryLevel", 10000)`;
  - `lastChargeLimit = vehicle.value("chargeLimit", -1)`;
  - `lastTimeToFullCharge = vehicle.value("timeToFullCharge", 0.0)`.
- `TWCMaster.getScheduledAmpsTimeFlex` reads `vehicle.value("chargeLimit", -1)` and `vehicle.value("batteryLevel", 10000)` at each of its three reads.
- `VehicleEndpoints._telemetryPluggedIn(vehicle)` takes the registry vehicle and returns `vehicle.syncSource != "TeslaAPI" and vehicle.value("pluggedIn") is True`. Its caller at :122 passes `vehicle`, not `car`.
- `Targets.broadcastVehicles.reached` checks `v.value("lat", 10000) == 10000` in place of `getattr(api, "lat", 0) == 10000`.
- `Targets._restoreDeparted` checks `vehicle.syncSource == "TeslaAPI"`.

- [ ] **Step 1: Characterization tests (pass at BASE and after).**
  - `tests/unit/test_registry_callers.py::test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults`. A listed car with no observations gives `lastAtHome False`, `lastBatterySOC 10000`, `lastChargeLimit -1`, `lastTimeToFullCharge 0.0`. After observing 61 / 80 / 1.5 and setting `atHome`, the endpoint reports those values. Use the `_handler(master)` helper already in that file.
  - `tests/unit/test_registry_callers.py::test_flex_start_reads_the_listed_cars_limit_and_battery`. No test covers `TWCMaster.getScheduledAmpsTimeFlex` at BASE. One TWC whose `lastVIN` is a listed car, with `scheduledAmpsFlexStart` on, `scheduledAmpsMax` > 0 (else `TWCMaster.py:682` divides by zero; pre-flight F17), limit 80 and battery 40, gives the same `startHour` at BASE and after. A second case, with no observations, uses the -1 / 10000 defaults; record today's value and pin it.
- [ ] **Step 2: Interface tests (fail first).** In `tests/unit/test_registry_vehicle.py`:
  - `test_sync_source_is_a_fresh_telemetry_state_else_teslaapi`: no state gives `"TeslaAPI"`; TeslaMate "online" just now gives `"TeslaMateVehicle"`; a TeslaMate state 3,601 s old on an untracked feed gives `"TeslaAPI"`; a `"TeslaAPI"`-sourced state gives `"TeslaAPI"`.
  - `test_telemetry_state_ages_only_telemetry`.
- [ ] **Step 3: Retarget existing tests** (plumbing unless noted):
  - `test_registry_callers.py::test_get_last_vehicle_uses_registry_attachment`: `getLastVehicle() is car` becomes `is reg.get(VIN)` (**INTENTIONALLY CHANGED**: the return type is the registry Vehicle; Task 2 interface).
  - `test_carapivehicle_registry.py`:
    - `car.syncSource` becomes `reg.get(VIN).syncSource` in `test_is_awake_trusts_fresh_telemetry_and_asleep_without_api_call`, `test_sync_getters_have_legacy_defaults_before_any_state`, `test_stale_telemetry_falls_back_to_api_check` and `test_telemetry_feed_drives_a_real_car`;
    - `car.pluggedIn` becomes `reg.get(VIN).value("pluggedIn")`.
  - The other `syncSource` readers (pre-flight F1; this is the complete list at BASE):
    - `test_limit_wiring.py:202` (`car.syncSource`);
    - `test_telemetry_registry.py:264–272`.
    - `test_teslaapi_providers.py`, `test_teslaapi_readonly_gate.py` and `test_reads_no_wake.py` have **no** `syncSource` reader; leave them to Task 3.
  - **Stub-driven test (F1):** `test_vehicle_endpoint.py::test_controller_lists_at_home_api_cars_and_keeps_blind_rules` (l.64) attaches a `SimpleNamespace(syncSource=…, pluggedIn=…)` as "TeslaAPI". `_telemetryPluggedIn` now reads the registry, so the stub fields stop driving it. Instead, observe `state` from `"TeslaMateVehicle"` and `pluggedIn=True` on the registry vehicle (plumbing; assertions unchanged). Check `test_charging_points.py` and `test_gen2_idle_minimum.py` for the same stub shape and treat them the same way.
  - Deleted, mapped (F2):
    - `test_carapivehicle_registry.py::test_actual_current_change_time_only_moves_on_change`, **PLUMBING-ONLY**: `lastCurrentChangeTime` has no reader in lib at BASE (`git grep -n lastCurrentChangeTime -- lib` shows only TeslaAPI's own writes).
    - `test_reads_no_wake.py::test_ble_actual_current_change_is_timed` (l.158–163), **PLUMBING-ONLY** for the same reason. Its other half, `latest("actualCurrent").source == "TeslaBLE"`, is covered by `test_ble_read_fills_fields_and_api_untouched`.
  - `test_attributes_are_observations_with_source_and_defaults` drops its two `actualCurrent`/`lastCurrentChangeTime` lines (plumbing). Its `latest("actualCurrent")` assertion stays, now written through the `actualCurrent` descriptor.
- [ ] **Step 4: Implement**, deleting the replaced members in the same commit.
- [ ] **Step 5: Full suite** → PASS. Grep: `git grep -nE '\.syncSource|_telemetryState|syncTimeout|lastCurrentChangeTime' -- lib html tests/integration tests/API` shows only `Vehicle.py`, `TeslaAPI.is_awake`'s registry call, Targets and VehicleEndpoints.
- [ ] **Step 6: Commit.** `git commit -m "The registry vehicle answers sync state; callers read registry fields, not CarApiVehicle"`

**Review focus (Task 2):**
- Every new `value(field, D)` uses the descriptor default from the table above.
- `getLastVehicle` still returns None for an unlisted car and never creates one.
- `VehicleEndpoints.allEVSEs` lists exactly the same cars (its `atHome` read is untouched).

---

### Task 3: CarApiVehicle dissolves: TeslaAPI methods take the registry Vehicle; its bookkeeping is an attached `CarApiState`; Forget becomes atomic (expected lib Δ ≈ −130)

The rest of the class goes:
- The REST methods move onto `TeslaAPI`, unchanged in logic.
- `RegistryField` goes, and the class becomes a record.
- `carApiVehicles` and `getVehicleByVIN` go.

Three things are re-expressed, not removed. Each has its argument below and a pinning test.
- `ready()` moves verbatim to `TeslaAPI._ready`, **including its second online check**, so no edge pays an extra `vehicle_data` (pre-flight F6).
- The online cache's four fields become one internal three-state value. Callers keep today's booleans (F3).
- Forget becomes one atomic registry operation. That is why the rejoin-after-forget path can go (F7).

Extra behaviour-neutral savings taken here, using the new pairs from `attached()`:
- `TWCSlave._anonCars` (≈ −3);
- `VehicleEndpoints.allEVSEs` (≈ −3);
- inlining the `say()` helper in `vehicleIsDefinitelyHome` (≈ −3);
- HomeAssistant's own `carApiVehicles` list becoming `registry.attached("HomeAssistant")` (≈ −3).

**Files:**
- Modify `lib/TWCManager/Vehicle/TeslaAPI.py`:
  - Delete `RegistryField`, `CarApiVehicle`, the `carApiVehicles` class attribute and `getVehicleByVIN`.
  - Add `CarApiState`.
  - Re-home the methods (below).
  - `wakeOutcome`, `command`, `_paidPost`, `wakeDue`, `_askChargeNeed`, `_chargeNeedEnded`, `_wakeSettled`, the backoff family, `_request`/`_classify`, `loadVehicleList`, `listPending`, `loadList`, `updateChargeAtHome`, `vehicleScheduledChargingPending`, `vehicleIsDefinitelyHome`, `numCarsAtHome` and `minBatteryLevelAtHome` are retargeted.
  - Reword the comment at :172 that names `CarApiVehicle.is_awake` (F18).
  - `TELEMETRY_SOURCES` stays imported (for `onlineState`).
- Modify:
  - `Vehicle/Providers/TeslaAPIProviders.py` (`fetch`, `_car` becomes `_listed`, `stopCharging`, `wake`; the comment at :139);
  - `Vehicle/Reconcile/Targets.py` (`located(master, vehicle)`; `_restoreDeparted` calls the module);
  - `TWCSlave.py:113` (`located(self.master, v)`) and `:131–137` (`_anonCars`);
  - `EVSEController/VehicleEndpoints.py:115–123` (`allEVSEs` loops over the pairs);
  - `Vehicle/Registry/VehicleRegistry.py` (`attached` returns pairs; `getOrCreate(..., attach=)`; `forget(..., ifUnattached=)`);
  - `Control/HTTPControl.py:117–120` (`forgetVehicle`);
  - `Vehicle/HomeAssistant.py:216, 263–268, 403–405, 578–596` (its list becomes `registry.attached("HomeAssistant")`; it attaches through `getOrCreate(..., attach=)`);
  - `Vehicle/Registry/Fields.py` (`READ_MAX_AGE = 300.0`);
  - `Vehicle/Reconcile/Reconciler.py` (imports `READ_MAX_AGE` from `..Registry.Fields`, deletes its own; the comments at :64 and :74 drop "CarApiVehicle").
- Test: `git mv tests/unit/test_carapivehicle_registry.py tests/unit/test_teslaapi_registry.py`. Fix its **8 importers** (F14): `test_held_limits.py:260,380`, `test_provider_outcomes_cloud.py:8`, `test_provider_tables.py:15`, `test_teslaapi_providers.py:10`, `test_teslaapi_readonly_gate.py:152`, `test_vehicle_endpoint.py:10`, `test_wall_connector_vins.py:8`. Plus the files listed in Step 3.

**Interfaces:**

```python
class CarApiState:
    """TeslaAPI's own bookkeeping for one car the account lists, attached to
    the car's registry Vehicle as "TeslaAPI": the attachment is the listing.
    The car's data is registry fields, never kept here."""

    atHome = False              # home by the latest position (locate, a read)
    statusDeferral = 0          # until then a read reports stored values
    errorCount = 0              # the per-car API error backoff
    lastErrorTime = 0
    lastAPIAccessTime = 0       # the last answer that proved it awake
    firstWakeAttemptTime = 0    # the wake hold (wakeOutcome, wakeDue)
    firstChargeNeededTime = 0
    lastChargeNeededTime = 0
    delayNextWakeAttempt = 0
    online = None               # the free online check: True, False, None (no answer)
    onlineCheckedAt = 0         # ... reused for 120 s from here
```

- **Registry: atomic listing and atomic Forget** (F7). The registry→vehicle lock order already exists: `expire` reads `v.claims` under `_lock`.
  - `VehicleRegistry.getOrCreate(self, vin, source, attach: Optional[Tuple[str, Any]] = None) -> Vehicle`. With `attach=(name, obj)`, the vehicle is found or created **and** `obj` attached while `self._lock` is held. A concurrent `forget` therefore sees either no vehicle or an attached one.
  - `VehicleRegistry.forget(self, key, ifUnattached=False) -> bool`. With `ifUnattached`, under `self._lock` it pops the vehicle only if it exists, `v.userAsserted` is true and `v.attachmentNames()` is empty; otherwise it returns False and changes nothing. Logging and the `removed` callback stay outside the lock, as today.
  - `HTTPControl.forgetVehicle`: keeps `canForgetVehicle` first (its BLE-paired check reads settings under `settingsLock`, which must not nest inside the registry lock). Then `if not master.vehicleRegistry.forget(vin, ifUnattached=True): return "/vehicleDetail/" + vin`. The settings-record cleanup runs only after a successful forget, as today.
  - `HomeAssistant`'s discovery attaches with `getOrCreate(vin, "HomeAssistant", attach=("HomeAssistant", hv))`.
- `VehicleRegistry.attached(name) -> List[Tuple[Vehicle, Any]]`: `(vehicle, attachment)` for each vehicle with one, in registry order. "The account lists something" is `bool(self.registry.attached("TeslaAPI"))`, which replaces `len(self.carApiVehicles) > 0` in `loadVehicleList`, `listPending` and `loadList`.
- `TeslaAPI.addVehicle(self, json) -> None`. It does what `CarApiVehicle.__init__` + `_bind(listed=True)` did:
  - `if "vin" not in json: return`;
  - `vehicle = self.registry.getOrCreate(json["vin"], "TeslaAPI", attach=("TeslaAPI", CarApiState()))`; a `ValueError` gives today's DEBUG skip;
  - `vehicle.claim("OwnerAPI", False, "listed")`;
  - `vehicle.claim("FleetAPI", lambda: self.fleetSlot.usable("command"), "listed")`;
  - `vehicle.observe("name", json["display_name"] or vehicle.vin, "TeslaAPI")`. The listing is a sighting.
  - `json["id"]` is no longer read. **INTENTIONALLY CHANGED edge:** today a list entry with a `vin` but no `id` raised `KeyError` out of `loadVehicleList`; Tesla always sends `id`.
- **Online state:** the three-state is internal. Callers keep today's values (F3).
  - `onlineState(self, vehicle, slot=None, now=None) -> Optional[bool]`. Today's `is_awake` body with the four flags folded. It returns True or False when an answer (telemetry or `vehicles/{vin}`) says so, and None when nothing answered. The telemetry branch is as today, through `vehicle.telemetryState()` and `vehicle.SYNC_TIMEOUT / 4`. Then:
    ```python
    now = self.now() if now is None else now
    if now - car.onlineCheckedAt < 120:
        return car.online
    result, response = self.get_car_api(vehicle, vehicle.vin, checkReady=False, slot=slot)
    car.online = response.get("state", "") == "online" if result else None
    car.onlineCheckedAt = now
    return car.online
    ```
  - `is_awake(self, vehicle, slot=None, now=None) -> bool`: `return bool(self.onlineState(vehicle, slot, now))`. This is today's return value: False for asleep **and** for no answer.
  - The two readers of today's `lastVehicleAwakeKnown` use `onlineState`:
    - `wakeOutcome`: `awake = self.onlineState(vehicle, slot=checkSlot, now=now)`; `if awake: …SATISFIED "online"`; `if awake is None: …UNREACHABLE "online check failed"`.
    - `FleetAPIProvider.stopCharging`: `self.carapi.onlineState(vehicle, now=self.clock()) is False`.
  - A wake answering online sets `car.online, car.onlineCheckedAt = True, now`.

  Mapping (exact on every path): today's `(State, Known)` is `None` when Known is False, else `State`.
  - The telemetry branch sets Known True.
  - A cache hit sets Known = Checked, and Checked False implies State False.
  - A GET sets Known = `bool(result)`.
  - The initial `(False, False)` is `online = None`, including on a test clock below 120 s.
- **`ready()` moves, not folds** (F6): `_ready(self, vehicle, car) -> bool` is today's `ready()` body with `self.` → `car.`/`vehicle.`:
  - the per-car backoff gate and its INFO8 line;
  - the 2-minute `lastAPIAccessTime` shortcut when `firstWakeAttemptTime == 0`;
  - then `if self.is_awake(vehicle): car.firstWakeAttemptTime = 0; return True`;
  - else the "wasn't woken in the last 2 minutes" INFO8 line, and False.

  The second `is_awake` call keeps today's slot (None) and clock (`self.now()`). At the 120 s cache boundary, or on a TeslaMate "asleep" landing between the two checks, it re-checks for free and skips `vehicle_data`, exactly as today.
- `get_car_api(self, vehicle, path, checkReady=True, slot=None) -> Tuple[bool, Optional[dict]]`. Today's body, with today's slot resolution first, then `if checkReady and not self._ready(vehicle, car): return False, None`.
  - `checkReady` replaces both `checkReady` and `provesOnline`, which every lib caller passed equal (`is_awake` False/False; `update_vehicle_data` True/True). On success with `checkReady` it sets `car.lastAPIAccessTime = time.time()`.
  - **Note (F12):** the 14 direct test calls of `get_car_api(..., checkReady=False)` with the default `provesOnline=True` (`test_teslaapi_request_errors.py:78,99,181,304,340,380`; `test_teslaapi_token_slots.py:241,263,280,419,432`; `test_teslaapi_providers.py:109`) no longer set `lastAPIAccessTime`. No assertion reads it; the report lists them.
  - The `vehicle=` passed to `_request` becomes `car=car`.
- `_readFresh(self, vehicle, field, maxAge)`, `update_location(self, vehicle, minInterval=0)`, `locate(self, vehicle)`, `update_vehicle_data(self, vehicle, slot=None)`, `update_charge(self, vehicle)`. Today's bodies, with:
  - `self.<field>` reads becoming `vehicle.value(field, D)`;
  - writes becoming `vehicle.observe(field, v, "TeslaAPI")`;
  - `self.<bookkeeping>` becoming `car.<bookkeeping>`.

  `update_vehicle_data` **keeps** its opening `if now < car.statusDeferral: return True`. It is not redundant with `fetch`'s check: two threads (the cloud worker's read-before-write and the background `updateChargeAtHome`/`update_location`) can both pass `fetch`'s check, and the second must find the deferral the first just set rather than pay a second `vehicle_data`.

  `update_charge` is `return self._readFresh(vehicle, "batteryLevel", READ_MAX_AGE) is not None`.
- Bookkeeping-only methods take the record. The parameter is renamed from `vehicle` to `car`:
  - `wakeDue(car, now=None)`, `_chargeNeedEnded(car, now)`, `_askChargeNeed(car, now)`, `_wakeSettled(car)`;
  - `getCarApiErrorRetryMins(car=None)`, `getCarApiRetryRemaining(car=None, now=None)`, `resetCarApiLastErrorTime(car=None)`, `updateCarApiLastErrorTime(car=None)`;
  - `_request(..., car=None)`, `_classify(..., car=None)`.

  The 429 branch reads `target = car or self`.
- `command(vehicle, name, body)`, `_paidPost(vehicle, slot, path, body, purpose)` and `wakeOutcome(vehicle, now)` take the registry vehicle (`vehicle.vin`, `vehicle.name`) and write `car.*`.
- Module loops:
  - `updateChargeAtHome`: `for vehicle, car in self.registry.attached("TeslaAPI"): if car.atHome: self.update_charge(vehicle)`.
  - `numCarsAtHome` and `minBatteryLevelAtHome`: properties, same values. The battery default is 10000 per car, with `default=10000`.
  - Iteration is now in sorted-VIN order, not list order (F16). Counts and minimums are unchanged; only the order of per-car reads differs.
  - `vehicleScheduledChargingPending(self, vin)`:
    ```python
    v = self.registry.get(vin) if isinstance(vin, str) else None
    return bool(v is not None and v.vin == vin and v.attachment("TeslaAPI") and v.value("scheduledChargingPending", False))
    ```
    The `vin=None` "any car at home" branch goes: its only caller, `TeslaBLE._scheduleBlocksStart`, always passes a registry key. `v.vin == vin` keeps today's exact-case match.
  - `vehicleIsDefinitelyHome(self, vin)` (F15):
    ```python
    v = self.registry.get(vin) if isinstance(vin, str) else None
    car = v.attachment("TeslaAPI") if v is not None and v.vin == vin else None
    if car is None:
        return
    ```
    An unlisted car (TWC- or BLE-created) also lives in the registry, so the attachment check is required. The rest is today's body with registry reads and `car.*`. The nested `say()` becomes direct `logger.log(logging.INFO2, …)` calls: same text, same level.
- Providers:
  - `_TeslaAPIProvider.fetch`: `car = vehicle.attachment("TeslaAPI")` (None gives False); `if time.time() < car.statusDeferral: return True`; then `bool(self.carapi.is_awake(vehicle, slot=slot) and self.carapi.update_vehicle_data(vehicle, slot=slot))`.
  - `FleetAPIProvider._listed(vin) -> Optional[Vehicle]`: `registry.get(vin)` when it has a `"TeslaAPI"` attachment. This replaces `_car`/`getVehicleByVIN`, and is case-insensitive, as `getVehicleByVIN` was.
  - `wake`: `self.carapi.wakeOutcome(vehicle, now=self.clock())`.
- Targets:
  - `located(master, vehicle) -> Optional[bool]`: True on a point. Otherwise, when the vehicle has a `"TeslaAPI"` attachment, `api.locate(vehicle)` with `api = master.getModuleByName("TeslaAPI")`; else None.
  - `_present` and `broadcastVehicles` pass `master`. Their `api.atHome` reads are unchanged (the record).
  - `_restoreDeparted(read=True)`: `master.getModuleByName("TeslaAPI").update_location(vehicle, 0)`, under the same conditions as today.
- Extra savings:
  - `TWCSlave._anonCars`: `listed = [v for v, _ in self.master.vehicleRegistry.attached("TeslaAPI")]`. Same registry order.
  - `VehicleEndpoints.allEVSEs`: loop over `attached("TeslaAPI")` pairs. The `isAnonymous` skip goes, since an anonymous vehicle never has the attachment.
  - HomeAssistant: drop `self.carApiVehicles`. The discovery log, `updateChargeAtHome`, `numCarsAtHome` and `minBatteryLevelAtHome` iterate `hv for _, hv in self.registry.attached("HomeAssistant")`. Discovery runs once, at init. The only visible difference is the order of the "Discovered Tesla" INFO lines (sorted VIN, not discovery order). HA's policy properties keep their values.

**Rejoin after forget goes, and why (F7).** `_liveVehicle`/`vehicle`/`_bind(listed=False)` re-created and re-attached a forgotten registry vehicle on the next write. After this task nothing can forget a listed car:
- `forget(..., ifUnattached=True)` checks for attachments under the registry lock, and listing attaches under the same lock. So the `canForgetVehicle` → `forget` race the pre-flight found (a first listing landing between the check and the forget) is closed at its source.
- `VehicleRegistry.expire` skips any vehicle with a `keepsAlive` claim, and the OwnerAPI/FleetAPI claims are `keepsAlive=True`.
- `forgetVehicle` is the only production caller of `registry.forget`.

So `registry.attached("TeslaAPI")` is the list `carApiVehicles` was.

- [ ] **Step 1: Characterization tests (pass at BASE, then after).** At BASE, reach the car through `api.carApiVehicles[0]`; after, through `reg.get(VIN)`. Put them in `test_teslaapi_registry.py` unless noted. Count requests per URL with `requests_mock`.
  - `test_car_backoff_blocks_vehicle_data_but_not_the_free_online_check`: a Fleet-only car with per-car `lastErrorTime = now` and `errorCount = 2`. A registry read of `batteryLevel` (`vehicle.read(..., maxAge=0)`) sends **1** `GET vehicles/<VIN>` and **0** `vehicle_data`, and logs the "not ready because of recent lastErrorTime" INFO8 line.
  - `test_vehicle_data_rechecks_online_when_the_cache_expired` (F6). On a test clock, `fetch`'s online check answers "online" at t. Patch the module clock so that `_ready`'s second check runs at t + 121 s, with `lastAPIAccessTime` older than 2 min and `firstWakeAttemptTime` non-zero; the second `vehicles/{vin}` answers "asleep". Expect 2 free GETs and **0** `vehicle_data`.
  - `test_a_vehicle_data_read_after_a_failed_wake_clears_the_first_wake_attempt`: `firstWakeAttemptTime = 100`, and the online check answers online. A successful read leaves it 0 and sets `lastAPIAccessTime`.
  - `test_two_concurrent_reads_pay_one_vehicle_data`: two `fetch` calls for one Fleet-only car, the second entering `update_vehicle_data` after the first set `statusDeferral`. Drive the interleaving by patching `is_awake` to run the first read's `update_vehicle_data` before returning True for the second. Expect exactly **1** `vehicle_data`.
  - `test_reads_no_wake.py::test_status_deferral_counts_as_success_without_fetch` and `::test_status_deferral_skips_the_online_check` stay, retargeted only.
  - `test_a_listed_car_is_never_expired` (`test_registry_membership.py`, F8): a listed car that is **not** user-asserted survives `registry.expire(now + 10**9)`. This pins the `keepsAlive` claims.
  - `test_get_slave_twcs_…` (Task 2) and the parity file stay green.
- [ ] **Step 2: Interface tests (fail first).**
  - `test_listing_attaches_state_and_both_claims`:
    - the attachment is a `CarApiState` with the defaults above;
    - the claims are OwnerAPI (never commands) and FleetAPI (follows the slot);
    - the name is observed as `"TeslaAPI"`;
    - `registry.attached("TeslaAPI") == [(v, state)]`.
  - `test_online_state_is_true_false_or_none_and_is_awake_stays_a_bool`:
    - telemetry asleep gives False/False, with no GET;
    - fresh telemetry online gives True/True;
    - a GET 500 gives `onlineState` None while `is_awake` stays False, cached for 120 s (no second GET at +119 s, one at +121 s);
    - a GET online gives True.
  - `test_forget_if_unattached_is_atomic` (`test_registry_membership.py`):
    - `forget(VIN, ifUnattached=True)` returns False for a vehicle that is attached, or not user-asserted, and the vehicle stays;
    - it returns True, and the vehicle is removed, for a user-asserted, unattached vehicle;
    - while a thread holds `registry._lock` inside `getOrCreate(..., attach=)` (patch `Vehicle.attach` to block on an event), a concurrent `forget(..., ifUnattached=True)` blocks until the attach lands and then returns False.
  - `test_vehicle_detail_page.py::test_forget_refuses_a_car_listed_after_the_check`: patch `canForgetVehicle` to return True for a user-asserted car that is then listed (`api.addVehicle`). `forgetVehicle` redirects to the car page and the car stays, with its `CarApiState`.
  - `test_update_vehicle_data_has_a_single_caller` (a grep over lib): `git grep -n "update_vehicle_data(" -- lib` shows only `def update_vehicle_data` and `TeslaAPIProviders.py`.
- [ ] **Step 3: Retarget tests (plumbing unless noted).** In every file:
  - `api.carApiVehicles[i]` becomes `reg.get(VIN)` (or `api.registry.attached("TeslaAPI")[i][0]`);
  - `car.<bookkeeping>` becomes `reg.get(VIN).attachment("TeslaAPI").<bookkeeping>`;
  - `car.<field> = x` becomes `reg.get(VIN).observe("<field>", x, "TeslaAPI")`;
  - `car.is_awake(...)` becomes `api.is_awake(v, ...)`, and likewise for `update_*`, `locate`, `get_car_api` and `ready` (now `api._ready(v, car)`). The `test_reads_no_wake.py` setup patches (`car.is_awake`, `car.update_vehicle_data`, `del car.update_vehicle_data` at l.200) move to `api.*` with a `(vehicle, slot=None)` signature;
  - `car.lastVehicleAwakeKnown` reads become `api.onlineState(v, …) is not None`, and `car.lastVehicleAwakeState` reads become `car.online` with the mapping above. **`is_awake(...) is False` assertions are not touched** (F3): `test_provider_outcomes_cloud.py:206–208` (`test_a_cached_failed_check_stays_unknown`), `test_teslaapi_token_slots.py:173` and `test_teslaapi_token_classification.py:127` keep their values. The `:207` telemetry step in the first stays, read through `onlineState`;
  - `api.getVehicleByVIN(VIN)` becomes `reg.get(VIN)`;
  - `api.carApiVehicles = []` resets are deleted (the list was a class attribute shared across instances; the registry is per master), and `ha.carApiVehicles == []` (`test_homeassistant_registry.py:213`) becomes `ha.registry.attached("HomeAssistant") == []`;
  - **Re-list in `test_limit_wiring.py:115` (F5):** a fresh `api_with_registry()` would lose the master's `heldLimits`, and `new_api(master=m)` reuses `m.vehicleRegistry` through `forMaster`, so nothing re-lists. Set `m.vehicleRegistry = VehicleRegistry({})` and then build `new_api(master=m)` (re-storing its tokens), so `(owner, fleet)` counts reach `(2, 1)`. `:220–221` `len(api.carApiVehicles)` becomes `len(api.registry.attached("TeslaAPI"))`;
  - **Mock masters (F13):** `test_vehicle_endpoint.py`, `test_charging_points.py` and `test_gen2_idle_minimum.py` return a `Mock` TeslaAPI from `getModuleByName`. After this task `located()` would get a truthy `Mock` from `Mock.locate(v)`, where today the stub gave None. Set `carapi.locate.return_value = None`, or use a real `TeslaAPI`, so no test passes for the wrong reason.

  **Direct `update_vehicle_data` / `get_car_api` calls in tests.** Since `_ready` is kept, a direct call behaves as today. Keep any request-count assertion as it is.

  Files: `teslatokens.py` (`new_api`; `add_home_vehicle` returns the registry vehicle), `test_teslaapi_registry.py`, `test_reads_no_wake.py`, `test_teslaapi_providers.py`, `test_provider_outcomes_cloud.py`, `test_telemetry_registry.py`, `test_limit_wiring.py`, `test_charging_reconciler.py`, `test_teslaapi_*` (`token_slots`, `request_errors`, `readonly_gate`, `token_classification`, `vehiclelist`, `owner_read`), `test_teslamate_token_sync.py`, `test_wall_connector_vins.py`, `test_held_limits.py`, `test_homeassistant_registry.py`, `test_provider_tables.py`, `test_registry_callers.py`, `test_vehicle_endpoint.py`, `test_gen2_idle_minimum.py`, `test_charging_points.py`, `test_amps_reconciler.py`, `test_vehicle_detail_page.py`, `test_command_path_parity.py` (plumbing only; counts untouched), and `test_registry_membership.py::test_find_by_name_and_attached`.

  `test_find_by_name_and_attached` expects pairs (**INTENTIONALLY CHANGED**: `attached`'s return type is this task's interface).

  Deleted, mapped:

  | Deleted test | Mapping |
  |---|---|
  | `test_carapivehicle_registry.py::test_writes_after_forget_land_on_the_live_vehicle` | PLUMBING-ONLY: forget of a listed car is refused atomically (`test_forget_if_unattached_is_atomic`, `test_forget_refuses_a_car_listed_after_the_check`), and expiry keeps it (`test_a_listed_car_is_never_expired`) |
  | `…::test_writes_after_forget_and_relist_by_another_provider` | PLUMBING-ONLY, same |
  | `…::test_relisting_the_api_attaches_the_new_car` | PLUMBING-ONLY, no replacement (F8): re-listing after a forget is unreachable, because a listed car cannot be forgotten |
  | `…::test_attributes_are_observations_with_source_and_defaults` | Defaults: `test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults` (Task 2). Source: `test_update_vehicle_data_observes_only_present_keys` and `…_the_cars_own_current_request` (kept) |
  | any other deletion | report it with its mapping |

- [ ] **Step 4: Implement**, deleting `RegistryField`, `CarApiVehicle`, `carApiVehicles` (both modules), `getVehicleByVIN` and `Reconciler.READ_MAX_AGE` in the same commit.
- [ ] **Step 5: Full suite** → PASS. Then two greps:
  - `git grep -nwE 'CarApiVehicle|RegistryField|getVehicleByVIN|lastVehicleAwakeTime|lastVehicleAwakeState|lastVehicleAwakeKnown|lastVehicleAwakeChecked|_liveVehicle|provesOnline|carApiVehicles' -- lib html tests/integration tests/API docs` → 0.
  - `git grep -n "\.forget(" -- lib` → only `forgetVehicle`'s `ifUnattached=True` call.
- [ ] **Step 6: Commit.** `git commit -m "Dissolve CarApiVehicle: TeslaAPI methods take the registry vehicle; its bookkeeping is an attached record; Forget is atomic"`

**Review focus (Task 3):**
- `_ready` is today's `ready()` gate for gate, including the second online check (F6).
- `is_awake` still returns False for no answer (F3).
- Only `wakeOutcome` and `stopCharging` see the three-state.
- `update_vehicle_data` keeps its deferral re-check.
- Lock nesting: `forget(ifUnattached)` and `getOrCreate(attach=)` take only the registry lock and then the vehicle leaf lock. `forgetVehicle` never holds `settingsLock` while calling `forget`.
- Every former `self.<field>` read uses the right default.
- The registry vehicle is passed where a VIN or a name is needed, and the record where only bookkeeping is.
- `Targets.located` never fetches: `locate` is free, and `update_location` runs only in `_restoreDeparted(read=True)` on the background thread.
- HomeAssistant's policy properties return the same values.

---

### Task 4: Sweep, guard, line check and live check (expected lib Δ ≈ −5)

**Files:**
- Modify:
  - comments and docstrings Task 3's grep did not force: the `EVSEController/VehicleEndpoints.py:84–86` docstring, the `Reconcile/Targets.py` header and `TWCSlave.py:132`'s "registry order is list order". That last one was already false at BASE (`vehicles()` sorts by key); Task 3 rewrote the code beneath it, so reword it to say "registry (sorted VIN) order". `TeslaAPI.py:172`, `TeslaAPIProviders.py:139` and `Reconciler.py:64,74` are Task 3's (F18);
  - any orphan the sweep finds, deleted with its grep evidence;
  - `CHANGELOG.md:23` (not lib; F20). It says the older `chargeLimits` key is "kept but ignored, with a warning". At BASE and after, it is deleted silently when the store already holds the car (`test_both_keys_present_the_store_wins`). Correct the sentence.
- Test: `tests/unit/test_registry_callers.py::test_no_caller_outside_teslaapi_reaches_for_its_list` is extended rather than duplicated.

- [ ] **Step 1: Guard (fails if any name is reintroduced).** The test's patterns over `lib/TWCManager`, `html`, `tests/integration` and `tests/API`:

```python
["git", "grep", "-lE",
 r"carApiVehicles|getCarApiVehicles|CarApiVehicle|RegistryField|getVehicleByVIN"
 r"|lastVehicleAwake|_liveVehicle|startswith\(\"id:\"\)",
 "--", "lib/TWCManager", "html", "tests/integration", "tests/API"]
```
  Since Task 3, HomeAssistant has no `carApiVehicles` list either, so the BASE regex's `[^f]` exclusion goes.
  Add one more assertion: `git grep -n "\.forget(" -- lib/TWCManager` shows only the `ifUnattached=True` call in `forgetVehicle`.
- [ ] **Step 2: Orphan sweep.** For every `def` in the files Tasks 1–3 touched, `git grep -nw <name> -- lib html` (the templates are under lib). Delete any with no caller, unless policy reach applies (a property or data attribute on a module object). Report each with evidence. Expected: none or a handful.
- [ ] **Step 3: Full suite** → PASS. `black --check lib` passes.
- [ ] **Step 4: Line check (report; the target is a target, not something to fit).**

```bash
find lib -name '*.py' | xargs cat | wc -l                   # target ≤ 26,750; BASE 27,270
git diff --shortstat db47522 -- lib; git diff --shortstat origin/main -- lib
git diff --numstat db47522 -- lib | awk '{a+=$1; d+=$2} END {print "added", a, "removed", d; exit !(d > a)}'
```
  Expected: the awk exits 0. Record the total, the two shortstats, and each task's actual vs expected delta in the ledger and the commit message. If the total is over 26,750, report by how much and where (see "Line budget"). Do not pad deletions.
- [ ] **Step 5: Commit.** `git commit -m "Guard the dissolved CarApiVehicle names; sweep comments and orphans"`
- [ ] **Step 6: Live check on `twcmanager`.** Deploys and restarts are pre-approved. The implementer does not run it; the user schedules it. Box: Gen2 in mode 1, `commandPolicy: ble_only`, a BLE-paired Model 3, a TeslaMate token synced to the Owner slot (read-only), a Fleet slot, and the Scheduled 70 / non-scheduled 50 policies.
  1. **Prepare.**
     - Record the box HEAD (the rollback target) and run `cp /etc/twcmanager/settings.json ~/twcmanager-settings.json.bak-phase3.5`.
     - Check the settings: `jq '{c: .chargeLimits, r: .chargeRateControl}' /etc/twcmanager/settings.json`. Expect no `chargeLimits` and `chargeRateControl` 1. **Done before Task 1:** the controller confirmed that the box's `heldLimits` holds no `"id:"` keys.
     - Set `logLevel` so INFO8 reaches the journal (every TeslaAPI request then logs `Car API <METHOD> <path>: HTTP <status>`).
     - Run `git -C ~/TWCManager diff` (must be empty) and `grep -rn "request.headers" ~/TWCManager/lib` (no log line).
     - Pause the watchdog cron if it is active.
  2. **Deploy.** Bundle `<box HEAD>..vehicle-model/phase3.5`, scp it, `git fetch <bundle> HEAD && git checkout --detach FETCH_HEAD`, then `sudo systemctl restart twcmanager`. Expect a `Providers: ...` boot line, no `Main loop stalled` after boot, and at most one free `Car API get products: HTTP 200` (the Owner list).
  3. **Restart with the car plugged in and asleep** (the 2026-10-16 regression).
     - Setup: the car plugged into the Gen2, asleep, held at 50, TeslaMate showing it at home and asleep.
     - Restart, then switch to Scheduled 70 (or wait for 00:00).
     - Expect:
       - an `anon:` plug session (TWC `lastVIN` empty);
       - BLE `wake`, `charging-set-limit 70`, then the BLE amps lift (`charging-set-amps 32`), then the start;
       - **zero** `Car API` lines for `vehicles/<VIN>`, `vehicle_data`, `wake_up` or `command/`. TeslaMate's fresh "asleep" answers `is_awake` without a GET;
       - the held limit 100/70 on the car's Vehicles page.
  4. **Surfaces.**
     - `curl -s localhost:8080/api/getSlaveTWCs | jq` shows `lastAtHome`, `lastBatterySOC`, `lastChargeLimit` and `lastTimeToFullCharge` with real values (once a read or TeslaMate has them).
     - The Vehicles tab and the car page render. Debug → "Send Tesla API Command" still lists the car. The listed car's page offers no Forget.
     - The policy page shows the same active policy as before deploying (it reads `minBatteryLevelAtHome`).
  5. **00:00 / 05:00 cycle.** Expect one BLE limit write each way, the BLE stop at 05:00, and no Fleet request.
  6. **Depart and return.**
     - Unplug and drive away: the held limit is restored over BLE in range, otherwise hourly, never a `wake_up`, and no Fleet request (ble_only).
     - Return and plug in: the policy limit is desired again, and nothing is sent while the car already sits at it.
  7. **Restart again with the car away**, then return. `heldLimits` is unchanged across the restart (`jq .heldLimits`), and no `chargeLimits` reappears.
  8. **Count paid calls** for the whole window: `journalctl -u twcmanager --since "<start>" | grep "Car API" | grep -oE "wake_up|vehicle_data|command/[a-z_]+" | sort | uniq -c`. Expect 0 under ble_only with BLE up. Price anything found at $0.02 / $0.002 / $0.001 and report it.
  9. **Record and roll back** (unless the user keeps it):
     - `git -C ~/TWCManager checkout --detach <box HEAD>`;
     - `sudo cp ~/twcmanager-settings.json.bak-phase3.5 /etc/twcmanager/settings.json`;
     - revert `logLevel`;
     - `sudo systemctl restart twcmanager`;
     - re-enable the watchdog;
     - confirm the boot log and one heartbeat.

**Review focus (Task 4):**
- The guard covers every removed name.
- The CHANGELOG correction matches what `HeldLimits` does.
- The line figures are exact.
- No deletion in the sweep is a module property or data attribute a policy could reach.

---

## Line budget (lib/ only; non-test `lib/**/*.py`)

Fixed points: origin/main 23,180; BASE db47522 27,270; target 26,750.

| Task | Expected lib Δ | Running total |
|---|---|---|
| 1 held limits in one pass (+ `_snapshot` inlined) | ≈ −48 (−40..−55) | ≈ 27,222 |
| 2 sync state on the registry; external readers | ≈ −20 (−10..−30) | ≈ 27,202 |
| 3 dissolve CarApiVehicle; atomic Forget; extra savings | ≈ −130 (−115..−145) | ≈ 27,072 |
| 4 sweep and guard | ≈ −5 (0..−15) | **≈ 27,067** |

- **Projected end: ≈ 27,065** (range ≈ 27,020–27,110). That is ≈ 315 over 26,750 and ≈ 17 % above main. These are the pre-flight's realistic figures (F11).
- **Task 1:** today's log messages cost about the same lines when collected for after the lock. Only the logic shrinks: about 70 lines become about 40, plus about 3 for the inlined `_snapshot`.
- **Task 3** was itemised as follows.
  - Removed: `CarApiVehicle` after Task 2 ≈ 384, `RegistryField` 21, `addVehicle` 9, `getVehicleByVIN` 9.
  - Re-homed: the record ≈ 23, `addVehicle` ≈ 12, `onlineState` + `is_awake` ≈ 30, `_ready` ≈ 25 (kept per F6), `get_car_api` ≈ 72, `_readFresh` 21, `update_location` 12, `locate` 7, `update_vehicle_data` ≈ 81, `update_charge` 2, one `car = …` line in about 8 methods, `_listed` ≈ 4, and the Targets plumbing ≈ 2.
  - Added for F7: `getOrCreate(attach=)` and `forget(ifUnattached=)` ≈ +8.
  - Extra savings: `_anonCars`, `allEVSEs`, `say()` and the HA list together ≈ −12.
- **Why not −300 + −135 as the audit and the final review projected:**
  - The audit's −300 assumed folding the wake hold and backoff into the reconciler's attempt record and moving `atHome` to Phase 5 presence. Both change behaviour (the wake hold and 429 backoff are per car and span reads, commands and wakes; presence is Phase 5's).
  - The final review's 120–150 for held limits assumed dropping the deferral (resolve once at the first list). The user kept semantics (a), so the deferral, the multi-slot listing in `resolveHeldLimits`, `_loadedVins` and `listPending` stay. What goes is the duplicated second pass, the shadow copy, `"id:"` and `vins()`.
- The rest of the gap is structural: Reconcile ≈ 1.9k, Providers, Registry; plus the user's kept Gen3 work (≈ 530) and Phase 4's distributor/heartbeat duplication (≈ 240, spec-mandated there).

## Decisions made in this plan

1. **The per-car bookkeeping is an attached record (`CarApiState`), not registry fields and not a TeslaAPI-side dict.**
   - Registry fields would make the online cache, backoff and wake hold observations: they would show in `Vehicle.summary()` (the Vehicles tab), and `observe()` bumps `lastSeen`, a forget-window change.
   - A TeslaAPI dict keyed by VIN would be a second per-car map beside the registry, the thing the spec's Goal 1 removes, and every listing check (`attachment("TeslaAPI")` in seven places and one template) would need rewiring.
   - The record keeps all of them, and `canForgetVehicle`'s refusal, unchanged.
2. **Method names stay** (`is_awake`, `update_vehicle_data`, …) with the registry vehicle as the first argument. Renaming would add churn and no lines.
3. **Nothing on a paid path is folded.**
   - `ready()` moves whole, keeping its second online check (F6). Folding it would pay one `vehicle_data` at the 120 s cache edge.
   - `update_vehicle_data` keeps its deferral re-check: under two concurrent reads it saves a paid `vehicle_data`.
   - Only the online cache's four flags become one internal three-state. That mapping is exact on every path, and callers still see today's booleans (F3).
4. **`_scheduleBlocksStart` stays** (it is not a duplicate of `Belief.handsOff`): it re-reads after the read-before-write, at run time, while `handsOff` runs at plan time. Only its `vin=None` dead branch goes.
5. **`TeslaAPI.carApiVehicles` goes** although a policy could name it: it is an undocumented list of internal objects that no comparison operator can use. `numCarsAtHome` and `minBatteryLevelAtHome` keep their values.
6. **The dev-build `"id:"` store keys go without migration code.** No release wrote them. The only deploy branch with the writer (`deploy/phase3-live` = db47522) also carries the cleaner, and the controller checked the box: it has no `"id:"` keys.
7. **Forget is one atomic registry operation** (F7, ruling): `forget(ifUnattached=True)` re-checks "user-asserted and unattached" under the registry lock, and listing attaches under the same lock. That replaces the rejoin-after-forget path rather than keeping it. HomeAssistant's attach uses the same call, so the same race closes for HA cars.
8. **INTENTIONALLY CHANGED edges, all accepted:**
   - F10: two IDs for one VIN whose entry was loaded malformed (Task 1).
   - A Tesla list entry with no `id` no longer raises (Task 3).
   - Per-car reads and HA's discovery log lines now come in sorted-VIN order (Task 3).

## Not taken (and why)

- **`HaVehicle`'s cached `battery_level`/`lat`/`lon`** (≈ −3 net): outside this phase's scope (not final review I2, not CarApiVehicle). `at_home` must stay: HA's home rule differs from TeslaAPI's (final-fix-report item 2).
- **One "is this car home" helper** (I2 row 2): the remaining copies differ in behaviour (home seeding, GPS age, the sunrise task). This is Phase 5.
- **`chargeStopMode`/`chargeRateControl` accessors** (I2 row 6): no saving (final-fix-report).
- **Compacting verbose log formatting** in the backoff helpers: cosmetic, not deduplication.

## Self-review (against db47522)

- **Every symbol planned for deletion exists:**
  - TeslaAPI.py: `RegistryField` :39, `CarApiVehicle` :1540, `carApiVehicles` :139, `getVehicleByVIN` :779;
  - `CarApiVehicle` members: `syncTimeout` :1592, `_telemetryState` :1639, `syncSource` :1649, `ready` :1655, `_bind` :1604, `_liveVehicle` :1622, `actualCurrent` :1949/1953, `lastCurrentChangeTime` :1586, `READ_MAX_AGE` :1565;
  - `Reconciler.READ_MAX_AGE` :75;
  - HeldLimits: `_waiting` :91, `"id:"` handling :118–123/:214–215, `vins` :281.
- **Every external caller is listed** in the member table and "Other callers checked":
  - `attachment("TeslaAPI")`: VehicleEndpoints:119, EVSEInstance/Gen3TWC:281, TWCSlave:136/1300, TeslaAPIProviders:46/77/108, Targets:25/35/64/134, debug.html.j2:74;
  - car methods: TeslaAPIProviders:55/163, Targets:26/137;
  - data reads: HTTPControl:511–514, TWCMaster:679–692, Targets:66, VehicleEndpoints:87–89;
  - `syncSource`: Targets:136, VehicleEndpoints:87;
  - `getLastVehicle`: HTTPControl:509, TWCMaster:679;
  - `located`: Targets, TWCSlave:113;
  - `getVehicleByVIN`: TeslaAPIProviders:140;
  - `vehicleScheduledChargingPending`: TeslaBLE:189;
  - `resolveLegacyIds`: TeslaAPI:544, tests.
  - `registry.forget`: HTTPControl:120 only (now `ifUnattached=True`). `getOrCreate` + `attach` pairs: TeslaAPI `addVehicle`, HomeAssistant:403–405. Both now go through `getOrCreate(attach=)`.
  - HomeAssistant `carApiVehicles`: :216, :263–268, :404, :579–596 and `test_homeassistant_registry.py:213`.
  - The 8 importers of `test_carapivehicle_registry.py` are listed in Task 3.
- **Surfaces.** `lib/TWCManager/Control/themes`, `html/`, `tests/integration`, `tests/API` and `docs/` reference none of the removed names at BASE (grep run during planning). The `attachment("TeslaAPI")` template use keeps working.
- **Green after every task.** Task 2 leaves `RegistryField` in place for `CarApiVehicle`'s own methods. Task 3 removes it together with every remaining user.

## Questions for the user

1. **The projection is ≈ 27,065, about 315 over 26,750, with no behaviour change.** This uses the pre-flight's realistic deltas and keeps `ready()`'s second check (F6). Accept it, or name a lever. The only one inside this phase is dropping the held-limit deferral (≈ −35: resolve and drop at the first non-empty list), which reverses your semantics (a). The other levers are behaviour changes for Phase 4/5 or the Gen3 work you kept.
2. **Decision 1 (an attached `CarApiState` record).** Confirm, or prefer the alternatives above. Default as written.
