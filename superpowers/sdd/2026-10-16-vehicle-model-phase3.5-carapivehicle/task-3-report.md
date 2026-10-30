# Task 3 report: CarApiVehicle dissolves

**Status:** DONE. Worktree `wt-vm35`, branch `vehicle-model/phase3.5`, BASE f82744e. Not pushed.

## Commits

| SHA | What |
|---|---|
| 424be4b | Step 1 characterization tests, written against BASE and passing there. Mutation-checked: each one fails when its gate is removed. |
| eebe6df | Registry layer: `getOrCreate(..., attach=)`, `forget(..., ifUnattached=)`, `attached()` returns pairs, `HTTPControl.forgetVehicle`, HomeAssistant uses `registry.attached("HomeAssistant")`. Interface tests included. The full suite was green at this commit (1781 passed). |
| 7d946ab | The dissolution itself: TeslaAPI, the providers, Targets, TWCSlave, VehicleEndpoints, Fields/Reconciler `READ_MAX_AGE`. Also the test rename (`git mv`) and the retargeting. |

## Verification

- Full suite: `tests --ignore=tests/API --ignore=tests/integration` gives **1780 passed, 1 xfailed** (baseline 1773).
  - Arithmetic: +6 characterization tests (the carry-in Targets test is one of them), +2 forget tests, +3 interface tests, −4 deleted tests (below).
  - Recount: 1773 + 6 + 2 + 3 − 4 = 1780.
- `tests/integration --collect-only`: 212 collected.
- `tests/API --collect-only` **hangs**. These files do module-level HTTP calls to <teslamate-host>:8088, so this is pre-existing and not caused by this task. None of them imports anything from `TWCManager`, which I checked with grep.
- Step 5 greps:
  - The removed-names grep over `lib html tests/integration tests/API docs` gives 0 hits.
  - `git grep "\.forget(" -- lib` gives only `HTTPControl.py:121 forget(vin, ifUnattached=True)`.
- Black: all 10 changed lib files are clean.
  - Test files that were black-clean at BASE are clean again: `teslatokens`, `test_registry_membership`, `test_held_limits`, `test_command_path_parity`, `test_teslamate_token_sync`, `test_teslaapi_owner_read`, `test_teslaapi_vehiclelist`, `test_vehicle_detail_page`.
  - Test files that were dirty at BASE were not reformatted.
- **Lib count: 27,138 vs BASE 27,212 = −74** (the brief estimated ≈ −130). Per file:

| File | Δ |
|---|---|
| TeslaAPI | −83 |
| VehicleRegistry | +9 |
| TeslaAPIProviders | +3 |
| Fields | +4 |
| Targets | +2 |
| HTTPControl | +2 |
| VehicleEndpoints | −3 |
| TWCSlave | −4 |
| HomeAssistant | −3 |
| Reconciler | −1 |

The shortfall comes mainly from three places:
- the 17-line `CarApiState` record;
- `addVehicle` now doing the claims and the name observation inline (+9);
- black wrapping the inlined `say()` calls in `vehicleIsDefinitelyHome`.

No duplication is left that I could find. Nothing was loosened to make up the lines.

## Behaviour notes (implementation as briefed)

- `_ready` is today's `ready()` gate for gate:
  - backoff and its INFO8 line;
  - the 2-minute shortcut;
  - the second `is_awake(vehicle)` with slot None and clock `self.now()`;
  - the INFO8 line on failure.

  `test_vehicle_data_rechecks_online_when_the_cache_expired` pins F6.
- `onlineState`, from `is_awake`'s body with the four flags folded:
  - its cache values map exactly;
  - `is_awake` = `bool(onlineState(...))`;
  - only `wakeOutcome` and `FleetAPIProvider.stopCharging` read the three-state;
  - a wake that answers online sets `car.online, car.onlineCheckedAt = True, now`.
- `update_vehicle_data` keeps its `statusDeferral` re-check, with a comment explaining why. `test_two_concurrent_reads_pay_one_vehicle_data` pins it and fails if the re-check is removed.
- `get_car_api(vehicle, path, checkReady=True, slot=None)`: `checkReady` replaces `provesOnline`, and `lastAPIAccessTime` is set only when `checkReady` is set.
- Lock order:
  - `getOrCreate(attach=)` attaches under `registry._lock` (registry → vehicle leaf). The "Vehicle added" log stays outside the lock.
  - `forget(ifUnattached=True)` reads `userAsserted`/`attachmentNames()` under the registry lock. Its log and `removed` callback stay outside.
  - `forgetVehicle` calls `canForgetVehicle` first, which takes `settingsLock` and releases it. Then it calls `forget` with no `settingsLock` held. The settings cleanup runs only after a successful forget.
- `Targets.located(master, vehicle)` calls `TeslaAPI.locate(vehicle)`, which is free. `update_location` runs only in `_restoreDeparted(read=True)`.
- Reads that had defaults: `lat`/`lon` 10000, `batteryLevel` 10000 (`minBatteryLevelAtHome`, also `default=10000`), `gpsAsOf` 0, `scheduledChargingPending` False. Logged names use `vehicle.name`, which is "" when unset, as `RegistryField("name", "")` was.
- In `update_vehicle_data`, `lat` is observed before `lon`, as the old two setattrs did. The values are read back through the registry, as the descriptors did.
- `vehicleIsDefinitelyHome` checks that the car is listed (attachment), with an exact-case match on `vin`. The `say()` calls are inlined: same text, INFO2.
- `vehicleScheduledChargingPending(vin)` is attachment-gated. The `vin=None` branch is gone; its only caller is `TeslaBLE.py:189`, which passes a VIN.
- **INTENTIONALLY CHANGED** (from the brief):
  - `json["id"]` is no longer read, so an entry with a VIN but no id no longer raises `KeyError`.
  - `attached()` returns pairs.
  - The "Discovered Tesla" lines and the per-car read order in `updateChargeAtHome` are now sorted by VIN.
  - The display-name fallback is `vehicle.vin`, which is upper-cased; it was the VIN as listed.

## Test mapping

### Deleted (from `test_carapivehicle_registry.py`, now `test_teslaapi_registry.py`)

| Deleted test | Mapping |
|---|---|
| `test_writes_after_forget_land_on_the_live_vehicle` | PLUMBING-ONLY. A listed car's forget is refused atomically: `test_registry_membership::test_forget_if_unattached_is_atomic` and `test_vehicle_detail_page::test_forget_refuses_a_car_listed_after_the_check`. Expiry keeps it: `test_registry_membership::test_a_listed_car_is_never_expired`. |
| `test_writes_after_forget_and_relist_by_another_provider` | PLUMBING-ONLY, same as above. |
| `test_relisting_the_api_attaches_the_new_car` | PLUMBING-ONLY, no replacement (F8). Re-listing after a forget is unreachable. |
| `test_attributes_are_observations_with_source_and_defaults` | Defaults: checked. `test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults` (Task 2) asserts `batteryLevel` 10000 and `chargeLimit` -1, as the API row. The `lat` 10000 default is pinned through its two readers: the new `test_a_listed_car_not_yet_located_is_in_the_broadcast` (`Targets.py:68`), and `locate` returning None for an unlocated car (`test_limit_wiring::test_a_held_car_with_no_known_position_is_present` / `…no_position_or_ble…`). The `pluggedIn` None and `chargingState` "Unknown" defaults are now unpinned, because no lib code reads them any more: Task 2 moved those callers to `v.value(...)` with their own defaults. The source is covered by the kept `test_update_vehicle_data_observes_only_present_keys` (only present keys observed, "TeslaAPI") and `…_the_cars_own_current_request` (`(16, "TeslaAPI")`). |

No other test was deleted.

### Rewritten

All of these are plumbing unless a mapping says otherwise.

- **`test_teslaapi_registry.py`**: renamed with `git mv`. All 8 importers were updated by the rename sed, plus the `test_registry_callers` import and comment.
  - `test_vehicle_joins…` asserts `attached == [(v, state)]` instead of `is carApiVehicles[0]`.
  - `test_master_without_registry…` and `test_listing_without_usable_vin…` read `attached("TeslaAPI")`.
  - The `is_awake`/`update_vehicle_data`/`get_car_api` patches move to `api.*`.
  - `car.lat == 1.5` becomes `value("lat") == 1.5`.
  - `test_debug_interface…` expects `wakeOutcome(reg.get(VIN), now=ANY)`.
- **`test_registry_membership::test_find_by_name_and_attached`**: expects `[(v, "obj")]`. INTENTIONALLY CHANGED: the return type is this task's interface.
- **`test_reads_no_wake.py`**: `setup()` returns `(api, ble, reg)`.
  - Patches move to `api.is_awake` / `api.update_vehicle_data` with a `(vehicle, slot=None)` signature, and `del api.update_vehicle_data`.
  - Field reads use `reg.get(VIN).value(...)`; bookkeeping uses `state(reg).*`.
  - `test_status_deferral_counts_as_success_without_fetch` and `test_status_deferral_skips_the_online_check` are retargeted only.
- **`test_teslaapi_providers.py`**:
  - `assert_called_once_with(slot=slot)` becomes `(v, slot=slot)`.
  - Command/wake mocks expect the registry vehicle.
  - `lastVehicleAwakeTime = 0` becomes `onlineCheckedAt = 0`.
  - Request counts are unchanged.
- **`test_provider_outcomes_cloud.py::test_a_cached_failed_check_stays_unknown`**:
  - `is_awake(...) is False` is kept at both steps, and the `lastVehicleAwakeKnown is False` reads become `onlineState(...) is None`.
  - The ":207 telemetry step" is now a real telemetry answer: a fresh TeslaMate "online" gives `onlineState` True. That observation is then aged by setting `v._clock` past `SYNC_TIMEOUT`, so the next call falls to the cache and gives None.
  - It also asserts exactly one GET.
  - Other tests in the file only change `carApiVehicles[0]` to the attachment.
- **`test_teslaapi_request_errors.py`**:
  - The `vehicle` fixture uses `addVehicle`.
  - `backoff_of` reads the attachment.
  - The "list" path of `run_path` replaces `api.carApiVehicles = []` with `api.registry = VehicleRegistry({})`, a fresh registry so the list is fetched again. This is plumbing.
- **`test_teslaapi_token_slots`, `_token_classification`, `_readonly_gate`, `_vehiclelist`, `_owner_read`, `test_teslamate_token_sync`, `test_wall_connector_vins`, `test_held_limits` (`Mock(carApiVehicles=[])` becomes `Mock()`), `test_provider_tables`, `test_charging_reconciler`, `test_amps_reconciler`, `test_telemetry_registry`**: mechanical retargeting.
  - `test_telemetry_registry::test_task9_legacy_sync_names_are_gone` checks `CarApiState`.
  - In `test_teslaapi_token_slots.py:173` and `test_teslaapi_token_classification.py:127`, the `is_awake(...) is False` values are untouched.
- **`test_limit_wiring.py`**:
  - `restarted()` returns the attachment.
  - `:115` re-list (F5): sets `m.vehicleRegistry = VehicleRegistry({})`, then `new_api(master=m)` and re-stores both tokens. `(2, 1)` is reached.
  - `:220–221` use `len(api.registry.attached("TeslaAPI"))`.
- **`teslatokens.py`**:
  - `new_api` drops the `carApiVehicles` reset.
  - For a real `TWCMaster` it registers a module record `{"ref": api, "type": "Vehicle"}` and removes `make()`'s `getModuleByName` Mock stub, so the real lookup finds the module.
  - Because of that, the four `del m.modules["TeslaAPI"]` lines are gone: `test_limit_wiring`, `test_charging_reconciler`, `test_amps_reconciler` and `test_command_path_parity` (parity is plumbing only; counts untouched).
  - `add_home_vehicle` returns the registry vehicle.
- **Mock masters (F13)**: `test_vehicle_endpoint`, `test_charging_points` and `test_gen2_idle_minimum` set `carapi.locate.return_value = None` and drop the dead `locate=lambda: None` from their attachment stubs.
- **`test_registry_callers::test_no_caller_outside_teslaapi_reaches_for_its_list`**: tightened to "no `carApiVehicles` anywhere in lib".

### Added

Step 1:
- `test_teslaapi_registry`:
  - `test_car_backoff_blocks_vehicle_data_but_not_the_free_online_check`
  - `test_vehicle_data_rechecks_online_when_the_cache_expired`
  - `test_a_vehicle_data_read_after_a_failed_wake_clears_the_first_wake_attempt`
  - `test_two_concurrent_reads_pay_one_vehicle_data`
- `test_registry_membership::test_a_listed_car_is_never_expired`
- Carry-in: `test_limit_wiring::test_a_listed_car_not_yet_located_is_in_the_broadcast`. It pins `Targets.py:66` and fails if the clause is removed.

Step 2:
- `test_listing_attaches_state_and_both_claims`
- `test_online_state_is_true_false_or_none_and_is_awake_stays_a_bool`
- `test_update_vehicle_data_has_a_single_caller`
- `test_forget_if_unattached_is_atomic`
- `test_forget_refuses_a_car_listed_after_the_check`

### F12: direct `get_car_api(..., checkReady=False)` test calls

These no longer set `lastAPIAccessTime`, and no assertion reads it:
- `test_teslaapi_request_errors.py`: the two in `TestGetCarApi`, `run_path`, and the three at ~304/340/380.
- `test_teslaapi_token_slots.py:241,263,280,419,432`.
- `test_teslaapi_providers.py`: `test_a_paused_slot_sends_nothing`.

## Concerns

1. **`located()` and `_restoreDeparted` now depend on `getModuleByName("TeslaAPI")`**, which returns None when the module's `enabled()` is False.
   - Today, a disabled TeslaAPI never gets tokens: `loadSettings` would itself crash on a None module, and TeslaMate sync checks for None. So it cannot list cars, and no attached car exists with a None module.
   - Per the controller's guidance, I did not add a None guard.
   - The cost: if a disabled TeslaAPI ever lists, `located` raises on the serial thread (TWCSlave).
2. **Lib delta is −74, not ≈ −130.** No shrink was left on the table that I could find without restructuring past the brief.
3. **`tests/API --collect-only` cannot complete** in this environment, because of module-level network calls. This is pre-existing. A grep shows these files import no `TWCManager` names.
4. **`new_api` now pops `make()`'s `getModuleByName` stub on real masters.** Every other module lookup on those masters still returns None, because their `modules` dicts are empty, so behaviour matches the old stub. It is still test-helper magic.

## Fix round 1

Commit c02e333.

- **m1:** `VehicleRegistry.expire` also skips any vehicle with an attachment.
  - Test-first: `test_registry_membership::test_an_attached_car_is_never_expired`. It covers a stale persisted car attached via `getOrCreate(attach=)` before any claim exists.
  - The test failed before the fix and passes after it.
- **m2:** `test_provider_outcomes_cloud::test_a_failed_online_check_still_sends_the_stop`. The online check answers HTTP 500, and the stop is then sent: DONE, 1 GET, 1 charge_stop POST.
  - It passes as written.
  - It fails with `is False` mutated to `is not True`.
- **Savings** (behaviour-neutral, black-clean):
  - `vehicleIsDefinitelyHome`: `say = functools.partial(logger.log, logging.INFO2)`, with `updated` folded into the if.
  - `minBatteryLevelAtHome`: `min(levels or [10000])`.
  - `getOrCreate` signature on one line (the `attach=None` annotation is dropped).
- **m3:** parked; no change.
- **Full suite:** 1782 passed, 1 xfailed. tests/integration collects 212.
- **Lib count:** 27,123, which is −89 vs BASE 27,212.
