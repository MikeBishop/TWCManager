# Task 10 report: Vehicle endpoints from the order

**Status:** DONE_WITH_CONCERNS
**Commit:** 4aa71a1 on vehicle-model/phase2 (parent acd223f)

## What changed
- New `lib/TWCManager/EVSEInstance/VehicleEndpoint.py`. It follows the brief's Interfaces. `ID` is `Vehicle-<vin>`. `provider` and `isReadOnly` come from `order.candidates(vehicle, SET_AMPS)`. State is read only through `vehicle.value(...)`, with no `read()`. `currentVoltage` follows TeslaAPIEVSE's rule: below 90 V it falls back to `defaultVoltage`, and phases fall back to `numberOfPhases`. `maxPower` uses `vehicleMaxAmps`. `occupied` is True or None.
- `setTargetPower(0)` returns without doing anything. For any other value it computes `amps = max(1, int(...))` and calls `master.queue_vehicle_command({"cmd": "setAmps", "vin", "amps"})`, but only when the amps changed or at least `REFRESH_SECONDS = 600` have passed. `_lastAmps` and `_lastQueuedAt` are recorded each time it queues. It never calls a provider. `startCharging`/`stopCharging` call `master.start/stopCarsCharging(vin)`.
- New `lib/TWCManager/EVSEController/VehicleEndpoints.py`:
  - `_blindTWCs()` returns `(blind, unknown)`. A slave counts as unknown when its `vehicleKey` is None or starts with `anon:`. An unknown slave makes the result blind when its state is not 00 or it draws at least 1 A.
  - A Gen3 unit with `occupied is True` and an `anon:` key also makes it blind. The Gen3 walk is inside the same try, so a failed scan returns `(True, True)`.
  - `_telemetryPluggedIn` is unchanged.
  - `allEVSEs` walks `vehicleRegistry.vehicles()`, skipping anonymous cars. It keeps a car when it has a `TeslaAPI` attachment with `atHome` set, unless `unknown` is set and telemetry says it is plugged in. It returns `[]` when TeslaAPI is absent or disabled, or when the result is blind.
  - The cache is keyed by VIN. It is rebuilt on every pass, so cars no longer listed drop out. An entry is also rebuilt if the registry's Vehicle object for that VIN was replaced.
  - The served-VIN exclusion is gone, as the brief says.
- `TWCManager.py` registers `VehicleEndpoints` under the same condition as before (TeslaAPI loaded).
- Deleted `TeslaAPIEVSE.py`, `TeslaAPIController.py` and `tests/unit/test_teslaapi_controller.py` with `git rm`.
- Docstrings and comments naming the old classes are updated in `EVSEInstance.py`, `EVSEController.py` and `TWCMaster.py` (distributeEVSEPower docstring and comment). I also updated `MergedEVSE.py:5` and `Provider.py:82`, which the brief did not list. `Gen3TWC.py:129` had no reference to the old classes, so it is unchanged. `grep -rn "TeslaAPIEVSE\|TeslaAPIController" lib tests` now finds nothing.
- Test updates:
  - `test_telemetry_registry.py` now uses `VehicleEndpoints._telemetryPluggedIn`.
  - The `getCarApiVehicles` list in `test_registry_callers.py` drops `TeslaAPIController.py`. VehicleEndpoints does not call `getCarApiVehicles`.
  - `test_distributor_loop.py`'s controller-name label is now `"VehicleEndpoints"`.
  - `TestTeslaAPIEVSE` is removed from `test_teslaapi_readonly_gate.py`.
- New `tests/unit/test_vehicle_endpoint.py` holds the brief's 7 tests verbatim. It adds `test_read_only_follows_fleet_slot`, which uses the real `FleetAPIProvider` through `api_with_registry`: with an Owner-only token the endpoint is read-only with provider `""`, and after `storeToken(fleet_token())` it is writable with provider `FleetAPI`.
- Black reports all touched lib files clean. They were all clean before the edits.

## TDD
Fail-before (with the new test file written, before implementation):
```
ImportError while importing test module '.../tests/unit/test_vehicle_endpoint.py'.
E   ModuleNotFoundError: No module named 'TWCManager.EVSEController.VehicleEndpoints'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```
After:
- Targeted run (`test_vehicle_endpoint`, `test_telemetry_registry`, `test_registry_callers`, `test_teslaapi_readonly_gate`, `test_distributor_loop`): 81 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1267 passed, 1 xfailed**. The count works out as 1277 − 16 (deleted controller tests) − 2 (removed TestTeslaAPIEVSE cases) + 8 (new).

## Behaviour notes
- The old `test_not_read_only_without_tesla_api` was dropped, not moved. Under `isReadOnly = not candidates(...)`, an order with no setAmps candidate is read-only by definition (A17). The old behaviour was "not read-only when TeslaAPI is absent".
- `isReadOnly` follows the whole order, not just TeslaAPI. A car that a ready TeslaBLE can serve is writable even with an Owner-only TeslaAPI, and its amps go over BLE (free).
- The cost path is unchanged. Queued `setAmps` goes to `VehiclePriority.setAmps` and then `order.dispatch(..., localRule=True)`. `ble_only` suppresses FleetAPI, and Fleet's `setAmps` still goes through `carapi.setChargeRate`, which keeps its own skip-repeat check and 10-minute resend.
- The endpoint records a send when it queues it, not when it succeeds. If a command fails, the same amps are not queued again until 600 s have passed. A change in amps still queues at once.

## Concerns (for Task 11)
1. **Interim double-listing before Task 11's grouping.**
   - `getDedupedEVSEs` still merges by `currentVIN`. A Gen2TWC with `currentVIN` cleared whose `vehicleKey` is still that car's `lastVIN` (a stopped car, state 03) does not merge with that car's new VehicleEndpoint, so the distributor budgets the car twice.
   - In chargeRateControl mode 1, the cost is safe only when the TWC covers the offer. The endpoint's queued setAmps finds the slave by `vehicleKey` (`Gen2TWCProvider.ready`), and the local rule drops Fleet. But the unmerged endpoint's `minPower` is 5 A, below the TWC floor (`slave.minAmps`, usually 6). A 5 A offer is outside the TWC's range, so Fleet stays a candidate (see `test_default_fleet_amps_rule_uses_target_and_range`), and a narrow new paid path exists until Task 11.
   - In mode 2, `Gen2TWCProvider.ready(SET_AMPS)` is False. On a named TWC (merged or not), the endpoint's `setAmps` can reach Fleet while `TWCSlave`'s heartbeat also queues `setChargeRate`. The two use different queue keys and do not coalesce. `carapi.setChargeRate`'s skip-repeat dedupes them when the amps match. When the amps differ, two values can alternate.
   - Today's served-VIN exclusion prevented this. The brief removes it on purpose and leaves the fix to Task 11's grouping.
2. **Carry-forward m2 (Task 6):** not touched. This task does not change how claims are displayed. Every listed Tesla still shows two claims (OwnerAPI and FleetAPI) on the Vehicles list and vehicle detail page. This is left for Task 11 or later.
3. **Dropped test (deviation from the brief):** the brief said to move both TestTeslaAPIEVSE cases. Only `test_read_only_follows_fleet_slot` was moved. `test_not_read_only_without_tesla_api` was dropped because the endpoint now has the opposite behaviour: with no setAmps candidate it is read-only (A17).
4. The brief's `Gen3TWC.py:129` line reference is stale: there was nothing there to change.
