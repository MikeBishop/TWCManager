# Task 9 report: VehiclePriority as a façade over the provider order

**Status:** NEEDS_CONTEXT on one point: the vehicle-rate raise is lost on Fleet-only installs (Concern 1). The brief's test conflicts with today's behaviour. Apart from that, the task is done, with the non-blocking concerns listed below.

Worktree `wt-vm2`, branch `vehicle-model/phase2`:
- `9e4e8f9` Refuse an infinite debug charge rate instead of raising OverflowError
- `b6fa18d` Make VehiclePriority a facade over the provider order; route the debug API through it
- `558b967` Give the VehiclePriority facade no providers of its own. `registerProviders` asks every Vehicle module, VehiclePriority included and loaded first. Without this fix the façade walked an empty order, returned False, and logged `Could not register VehiclePriority providers: TypeError` on every boot. The fail-before was exactly that warning in `test_registration_finds_no_providers_on_the_facade`. The same commit makes `VALID_COMMAND_POLICIES` a class attribute aliased to `Suppressions.VALID_COMMAND_POLICIES`, so it works on the class as well as on instances.

## What changed

- **`lib/TWCManager/Vehicle/VehiclePriority.py`** (rewritten). Everything in the brief's Interfaces section is implemented:
  - `COMMAND_CAPABILITIES` and `capabilityFor`. `car_api_charge` resolves to STOP when `charge is False`, otherwise START.
  - `targetVIN` and `targetAmps`. A VIN is accepted only as a non-empty `str`, then upper-cased.
  - `modulesFor`:
    - Command methods use `candidates(vehicle, cap, amps)` when the VIN is in the registry, otherwise `ordered(cap)`.
    - Other methods use `providers()` minus anything suppressed for `READ_CHARGE`.
    - Providers whose module is `None` are skipped.
    - Modules are de-duplicated by `id()`, keeping the first position.
  - `__getattr__` walks in order:
    - It skips a module that lacks the method, with no retry.
    - A result wins when `ret and ret != "error"`.
    - It makes `provider.attempts()` tries.
    - Stats are keyed by provider name. `moduleDispatch` is also counted per provider tried, which keeps the debug page's stat alive.
    - Exceptions are logged by type name only.
    - Names starting with `_` raise `AttributeError`, so dunder probes like `copy`'s never walk the order.
  - Explicit `setAmps(vin, amps)` goes through `order.dispatch`.
  - `commandPolicy`, `commandPolicyOverridden` and `VALID_COMMAND_POLICIES` delegate to `order.suppressions`.
- **`VehicleCommandQueue`**: adds a module-level `_setAmps` and the `"setAmps"` dispatch entry. When the module has no `setAmps`, it logs one DEBUG line and returns False.
- **`Order.debugCommand`**: also catches `OverflowError` ("inf", "-inf", 1e999).
- **`HTTPControl` `/api/sendTeslaAPICommand`**: now calls `master.providerOrder.debugCommand(...)`. It returns 200 when the result `is True`, otherwise 400. The `TeslaAPI is None` check is gone.
- **`TeslaAPI.apiDebugInterface`**: deleted.
- **`settings.html.j2`**: relabelled exactly as specified. That covers `chargeStopMode` option 1, the three `chargeRateControl` options and the three `commandPolicy` options.
- **`docs/Settings.md`**:
  - New "Vehicle Command Policy" section covering the three values and what each suppresses.
  - New "providerSuppressions" subsection with the JSON shape, provider names and capability names.
  - The Stop Charging Method label is updated.
- **`docs/modules/Vehicle_TeslaBLE.md`**: the two `chargeRateControl` labels are updated to match the template. This file was not listed in the brief.
- **`CHANGELOG.md`**: the Architecture line is added verbatim.

## Deviations from the brief

1. **`targetAmps` clamps to at least 1.** The clamp applies only to the candidate lookup; the module still receives the caller's original value. Without it, mode 2's `setChargeRate(0)` would drop every candidate, because the BLE and Fleet ranges are (1, max). Today TeslaAPI clamps 0 to 1 and sends. NaN maps to None. Tested in `test_set_charge_rate_zero_still_reaches_the_vehicle`.
2. **The walk returns `False` when nothing succeeds.** Today it returned the last module's `ret`, which could be `"error"`. This follows the brief. It also makes TWCSlave's `result is not False` raise callback correct.
3. **Extra tests:**
   - de-duplication of one module under two providers (Owner and Fleet);
   - exceptions counted as failures, and dunder probes not walking;
   - three parametrized `debugCommand` infinity cases in `test_provider_order.py`.

## TDD evidence (fail before)

New `test_vehicle_priority.py` against the old VehiclePriority: 12 of 13 failed.
- 11 failed with `TypeError: cannot unpack non-iterable Mock object`. The old loop unpacks `master.getModuleByPriority`, which is a Mock in the new fixture, so the failure is a TypeError rather than the brief's predicted `AttributeError ... 'order'`.
- `test_queue_dispatches_set_amps` failed with `assert (False is True)`, since the queue had no `setAmps`.

New infinity tests against the old Order: 3 failed with `OverflowError: cannot convert float infinity to integer` at `Order.py:167`.

The debug-route test failed before the HTTPControl change: `Expected 'debugCommand' to be called once. Called 0 times.`

The rebuilt `test_carapivehicle_registry` debug test passed at once, because `debugCommand` already existed from earlier tasks. Rebuilding it on the order was the point.

## Tests

- Full suite (capped): **1263 passed, 1 xfailed**.
- Arithmetic against 1283 at eee9425: minus the old file's 37 tests, plus 14 new façade tests, plus 3 new order tests, gives 1263.

## Cost check (retries and paid calls)

| Path | Today (`_calculate_retries`) | Façade |
|---|---|---|
| TeslaBLE | priority 20, 3 attempts | `attempts()` local = 3 |
| TeslaAPI | priority 10, 2 attempts | Fleet `attempts()` = 2 |

So retries do not multiply for TeslaAPI. Owner and Fleet share one module: it is walked once, at the first position, with OwnerAPI's attempts (2) for reads. For commands only FleetAPI declares the capability, so its attempts (2) apply.

## Concerns

1. **NEEDS_CONTEXT: the vehicle-rate raise is lost on Fleet-only installs.**
   - **What happens today:** `TWCSlave._requestVehicleRateRaise` queues `setChargeRate(wiringMaxAmps, car)`. This happens in mode 1 (the default) once per session, and in mode 3 when the TWC takes back control at ≥ 6 A.
   - **Why the façade drops it:**
     - `Gen2TWCProvider.ready(SET_AMPS)` holds whenever a slave's `vehicleKey` (from `currentVIN`) matches the car.
     - Its range is `(minAmps or 6, maxOfferAmps)`, and `maxOfferAmps = min(wiringMaxAmps, maxAmps)`, so wiringMaxAmps is covered.
     - The local-path rule in `candidates` therefore drops FleetAPI.
   - **Effect:** on a Fleet-only (no BLE) install the raise never reaches the car. The `done()` callback sees False and retries every 60 s at no cost, but in mode 3 a car previously throttled below 6 A through Fleet stays capped.
   - **Why it needs a decision:** this changes today's behaviour and changes when paid calls happen (one per session in mode 1 today). Both cut against the task's rules, but the brief's verbatim test (`setChargeRate(10, car)` with TWC covering 10 A, then Fleet not called) mandates it.
   - **What I did:** implemented the brief as written.
   - **One-line alternative if the caller decides otherwise:** pass `amps=None` to `candidates` for `setChargeRate` (or for raises only) and drop that test's first assertion.
2. **The debug path can now make two paid calls where today there is one.** `debugCommand` goes through `dispatch`, so Fleet gets `attempts()` = 2. Today `apiDebugInterface` made exactly one `setChargeRate` or `wakeVehicle` call. A failed Fleet wake ($0.02) or `set_charging_amps` can now be sent twice. The trigger is user-initiated and debug-only, but it is a multiplied paid call.
3. **HomeAssistant in the walk:**
   - HA now gets 2 attempts per command. Today it got 1 call, and only as the fallback when VehiclePriority was not loaded.
   - `HomeAssistant.setChargeRate` expects an `HaVehicle`, but the queue passes a `CarApiVehicle`. The result is an `AttributeError`, counted as an HA failure, so HA cannot actually help with `setChargeRate` through this path.
   - HA also joins the non-command (read) walk last.
   - `HomeAssistantProvider.available()` is the default True and `registerProviders` does not check `enabled()`. A loaded-but-disabled HA therefore receives broadcast commands (it returns "error" from `car_api_available`). Today `getModuleByName` filtered on `enabled()`.
4. **Stats keys change:** `moduleSuccess` and `moduleFailures` are now keyed by provider name (`FleetAPI`, `OwnerAPI`) rather than module name (`TeslaAPI`). The only consumer is `debug.html.j2`, which renders the dicts generically.
5. **`api_only` now keeps BLE out of reads walked through the façade.** This is intended by the brief, but it changes today's behaviour, where api_only applied only to commands in VehiclePriority.
6. **BLE-only wake from the debug page is not reachable yet.** The debug page's vehicle `<select>` still lists only vehicles with a TeslaAPI attachment (`debug.html.j2:74`, and a test pins that BLE-only VINs are absent). The brief's rationale for dropping the `TeslaAPI is None` check therefore needs a template change, which is outside this task's file list.
7. **`TestTeslaAPIEVSE`** is left unchanged; the brief says it moves to Task 10.
8. **`enabled` goes through the read walk.** `getModuleByName("VehiclePriority")` calls `enabled()`, and the façade answers it by walking BLE, then TeslaAPI, now HA as well. This was true before for BLE and TeslaAPI. What is new is that an enabled HA alone now makes VehiclePriority count as enabled. On an HA-only install, `_resolveVehicleCommandModule` therefore picks the façade (HA with 2 attempts) instead of the HA module directly (1 attempt).

## Fix round 1

**Status:** DONE. Commit `edf61bf` sits on top of `558b967`.

### 1. Vehicle-rate raise: today's behaviour kept

Passing `amps=None` to `candidates` would not have been enough. The SET_AMPS local-path rule in `candidates` treats `amps is None` as "any local provider", so a ready Gen2 TWC would still drop Fleet.

What `modulesFor` does instead for a targeted `setChargeRate`:
- It uses `ordered(SET_AMPS)` filtered by readiness only (`order._ready`), with neither the amps rule nor the local-path rule.
- `setAmps` (the queue command) still goes through `dispatch`/`candidates`, so the local-amps rule applies there unchanged.
- `targetAmps` stays as the brief's interface, but selection no longer uses it. A comment in the code says so.

Test changes:
- The brief's test is renamed `test_set_charge_rate_targets_the_car`, with its first assertion dropped.
- New `test_rate_raise_reaches_fleet_on_a_fleet_only_install`: with a TWC covering 6–32 A plus Fleet and no BLE, both a raise to 32 A and a 10 A rate reach Fleet.
- New `test_set_amps_keeps_the_local_amps_rule`: 10 A goes to the TWC only, while 4 A goes to Fleet.

### 2. Attempts equal today's

Today's priorities come from `TWCMaster.calculateModulePriority`:

| Module | Priority | Attempts today | Façade |
|---|---|---|---|
| TeslaBLE | 20 | 3 | local provider = 3 |
| TeslaAPI | 10 | 2 | Owner/Fleet = 2 |
| HomeAssistant | None | 1 (never in the priority walk; called once directly when it was the command module) | 1 |

- `HomeAssistantProvider.attempts()` now returns 1. This applies to both the façade and `dispatch`.
- `test_attempts_match_todays_priorities` uses a real `TeslaAPI` with a Fleet token and a real HA provider. A failing `car_api_charge` is called 2 times on TeslaAPI and once on HA.
- `ProviderOrder.dispatch` gains `attempts: Optional[int] = None`, which overrides each provider's own count. `debugCommand` passes `attempts=1` for both `setChargeRate` and `wakeVehicle`.
- `test_debug_command_tries_each_provider_once`: a failing wake is sent exactly once to BLE and once to Fleet, and a failing set-amps exactly once.

### 3. HomeAssistant

- **Own vehicle for `setChargeRate`:**
  - New `Provider.vehicleAttachment` (default None). `HomeAssistantProvider` sets it to `"HomeAssistant"`.
  - For `setChargeRate`, the façade's `_argsFor` replaces the vehicle argument (positional or kwarg) with the registry vehicle's own attachment, found by `targetVIN`.
  - If there is no HA attachment (unknown VIN, or no HA vehicle), HA is skipped. It is never handed the TeslaAPI vehicle.
  - A `None` vehicle passes through unchanged, as today.
  - Test: `test_home_assistant_gets_its_own_vehicle_for_set_charge_rate`.
- **Disabled HA gets nothing:**
  - `HomeAssistantProvider.available()` now returns `ha.enabled()`, so `ordered()` keeps a disabled HA out of broadcasts.
  - The façade's non-command (read) walk now also skips providers that are not `available(READ_CHARGE)`, guarded against exceptions. HA is the only provider this can drop. TeslaAPI's module is always kept through OwnerAPI, whose `available` defaults to True.
  - Test: `test_disabled_home_assistant_gets_no_broadcast` covers both a command and a read.

### Fail-before (new tests against 558b967)

Five failed:
- **raise:** `assert (False is True)` from `vp.setChargeRate(32, car)`.
- **attempts:** `assert (2, 2) == (2, 1)`, since HA was making 2 attempts.
- **HA vehicle:** `(10, <Mock …475824>) != (10, <Mock …803888>)`, since HA was given the TeslaAPI car.
- **disabled HA:** `assert ('success' is False)`, since the broadcast reached the disabled HA.
- **debug once:** the BLE wake list held 3 calls instead of 1.

`test_set_amps_keeps_the_local_amps_rule` passed already; it pins existing behaviour.

### Tests

The capped full suite gives **1269 passed, 1 xfailed** (1263 + 6 new).

### Remaining concerns

- Through the façade, BLE is tried for a targeted `setChargeRate` only when it holds a claim on the VIN (`TeslaBLEProvider.ready`). Today BLE was always tried first. This is the brief's readiness design, noted here because it is a change.
- `targetAmps`, including its 0→1 clamp, is now unused for selection.

## Fix round 2

**Status:** DONE. Commit `006818f` sits on top of `edf61bf`.

### C1: Fleet fallback while TeslaAPI's vehicle list is unloaded

Change in `VehiclePriority.modulesFor`. For a targeted command, the walk is now `ordered(cap)` filtered to providers that are either:
- in `candidates(vehicle, cap, localRule=…)`, or
- `_listUnloaded(p)`.

`_listUnloaded(p)` is true only for the provider named `FleetAPI` whose module's `getVehicleCount() == 0`; the call is guarded against exceptions.

`ordered()` has already applied suppressions and `available(cap)`, meaning the Fleet command slot is usable. So:
- Owner-only installs still get no commands.
- `ble_only` still blocks Fleet.
- TeslaAPI's own method loads the list and resolves the car, as at eee9425.

Once the list is loaded, a car that is not on it is skipped as before (`test_loaded_list_without_the_car_still_skips_fleet`). The fix lives in the façade only, so `dispatch`, `candidates` and `FleetAPIProvider.ready` are unchanged, and Task 10's `isReadOnly` is unaffected.

Tests:
- `test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads`: BLE fails 3 times, then TeslaAPI gets the stop; the targeted limit also reaches it.
- `test_fleet_only_targeted_commands_work_from_boot`: a failing stop is tried on TeslaAPI twice, and `moduleFailures` is `{"FleetAPI": 1}`.

### I1: targeted commands kept off a multi-car HomeAssistant

`_argsFor` → `_ownVehicleOnly`. For a provider with `vehicleAttachment` set, on a targeted `car_api_charge` or `applyChargeLimit`, HA is skipped unless both of these hold:
- the target has an HA attachment;
- HA's `getVehicleCount() == 1`.

The attachment is HA's own vehicle, so with one car that car is the target. Broadcasts are unchanged and still reach HA, which acts on every car as before. `HomeAssistant.py` is not touched.

Deliberate narrowing of the ruling: I kept the single-car case passing rather than skipping HA for every targeted call. Otherwise an HA-only install (TeslaAPI disabled in config, review row D7) would lose targeted start and stop entirely; at eee9425 those reached HA directly. With one HA car, acting on "every HA car" is acting on the target.

Tests:
- `test_targeted_command_never_reaches_home_assistant_holding_other_cars`: Fleet plus HA with two cars. Fleet fails a targeted stop, HA is not called, the targeted limit is not called, and a broadcast does reach HA.
- `test_targeted_command_reaches_home_assistant_holding_only_that_car`.

A first version used `getCarApiVehicles()` and tripped the existing guard `test_no_caller_outside_teslaapi_reaches_for_its_list`. It now uses `getVehicleCount()`.

### M1: debug page setChargeRate

- `ProviderOrder.candidates` and `dispatch` gain `localRule: bool = True`.
- `debugCommand("setChargeRate")` now calls `dispatch(..., attempts=1, localRule=False)` with no amps, which is readiness only and matches the façade's `setChargeRate`.
- `setAmps` and the queue keep the rule.

Test: `test_debug_set_charge_rate_reaches_fleet_past_a_covering_twc`. A Gen2 provider (module None) covers 16 A, and Fleet still gets exactly one call. The test also checks that `dispatch(amps=16)` keeps the rule.

### Other minors

- **M3 fixed:** the façade no longer calls `order._ready`. The `setChargeRate` path uses `candidates(..., localRule=False)`.
- **M2 fixed:** `targetAmps` is marked "Remove with the facade in Phase 3".
- **M4 fixed:** `docs/Settings.md` now names `Gen3TWC` and the telemetry feeds `TeslaMateVehicle` and `FleetTelemetryMQTT`, noting that the feeds only report.
- **M5 left:** the debug dropdown lists only TeslaAPI cars; deferred to Phase 6 by ruling.

### Fail-before (new tests against edf61bf)

- **C1, BLE plus Fleet:** `assert False == 'success'` (BLE 3x, then nothing).
- **C1, Fleet-only:** `assert (False is False and 0 == 2)` (TeslaAPI never called).
- **I1:** `assert ('success' is False)` (HA stopped every car).
- **M1:** `[] == [('setAmps', VIN, 16)]` (Fleet dropped).
- Two tests passed from the start because they pin existing behaviour: the loaded-list-skips test and the single-car HA test.

### Tests

The capped full suite gives **1275 passed, 1 xfailed** (1269 + 6 new).

## Fix round 3

**Status:** DONE. Commit `acd223f` sits on top of `006818f`.

### N1, ruling (b): HomeAssistant honours the VIN

`HomeAssistant.py` gains `_vehiclesFor(vin)`:
- With no VIN, it returns every HA car, so a broadcast behaves exactly as before.
- With a VIN, it looks the car up as `HomeAssistantProvider` does (`self.registry.get(VIN.upper()).attachment("HomeAssistant")`) and returns `[hv]`.
- When the VIN is not one of HA's cars, it returns `None`.

Both `car_api_charge` (VIN from `task["vin"]`) and `applyChargeLimit` (`vin=` kwarg) now loop over that list:
- An unknown VIN returns `"error"`. That is the value each method returns today when there is no vehicle: `car_api_available()` fails on an empty list.
- That check comes after the availability check and before `car_api_charge` stamps its 10 s rate-limit time, so a refusal neither acts on any car nor rate-limits the next command.

In the façade, `_ownVehicleOnly` and its single-car rule are removed. HA joins targeted walks again: last, with 1 attempt, and only when ready. `_argsFor` substitutes HA's own vehicle only for `setChargeRate`.

The CHANGELOG has a new Bugfixes line: "A targeted start, stop or charge limit sent through Home Assistant now affects only the named car; a command for every car still reaches every Home Assistant car".

### m-1

In `test_debug_command_tries_each_provider_once`, the stale comment is gone. The test now asserts `f.calls[1:] == [("setAmps", VIN, 3)]`: with readiness only, Fleet follows BLE, once.

### Tests

The tests use HA's real methods with `_call_service` recorded:

| Test | Fail-before against 006818f |
|---|---|
| `test_ha_only_targeted_stop_affects_only_the_target` (HA-only, two cars) | `assert (False == 'success')`: nothing sent |
| `test_fleet_failure_falls_to_home_assistant_for_the_target_only` (Fleet+HA, two cars, Fleet fails 2x) | `assert (False == 'success')` |
| `test_broadcast_still_reaches_every_home_assistant_car` | passed before; pins today's behaviour |
| `test_unknown_vin_affects_no_home_assistant_car` | `assert 'success' == 'error'`: before, the method looped over every car |

The two round-2 HA tests are replaced by these four. The m-1 assertion passed before; it pins M1.

The capped full suite gives **1277 passed, 1 xfailed** (1275 − 2 replaced + 4 new).
