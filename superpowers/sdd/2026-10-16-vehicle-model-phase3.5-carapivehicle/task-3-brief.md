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

