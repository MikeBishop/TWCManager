# Task 10 review: Vehicle endpoints from the order (acd223f..4aa71a1)

## Verdicts

- **Spec compliance: PASS.** Every Interfaces item is present as specified. There are two deviations, both justified: `Gen3TWC.py:129` was already clean, and `test_not_read_only_without_tesla_api` was dropped (see concern 3). The doc edits beyond the brief (`MergedEVSE.py:5`, `Provider.py:82`) are in scope.
- **Task quality: APPROVED.** There are no Critical or Important findings. The Minor findings below can be done as follow-ups.

## Checks

| Check | Result |
|---|---|
| No vehicle I/O on the serial thread | Holds. `VehicleEndpoint` reads only `vehicle.value()` (registry lock, no I/O). `setTargetPower` only calls `master.queue_vehicle_command` (`VehicleEndpoint.py:149-160`). `isReadOnly`/`provider` walk `order.candidates()`. Every `ready()`/`available()` on that walk is flag-only. `TeslaTokenSlot.usable` → `reportScopeRefused` logs once per token and purpose (`TeslaTokenSlot.py:155-157`). `_blindTWCs` reads `Gen2TWC.vehicleKey` (registry `get`) and `Gen3TWCs.devices()`/`Gen3TWC.occupied`/`vehicleKey` (cached vitals, `Gen3TWC.py:109-111,342-351`). The only caller of `allEVSEs` is `getAllEVSEs` from `distributeEVSEPower` (serial thread), so `_cache` has a single writer. |
| No new paid path beyond concern 1 | Holds for Fleet. The queued `setAmps` goes to `VehiclePriority.setAmps` → `order.dispatch(SET_AMPS, amps=…)` (localRule on) → `FleetAPIProvider.setAmps` → `carapi.setChargeRate`, which keeps its own skip-repeat (records only accepted rates, 10-min resend). Each amps change costs one send, as before. `ble_only` removes Fleet from candidates; tested by `test_read_only_when_no_amps_candidate_and_ble_only_excludes_fleet`. HomeAssistant is a new billed-tier writer, sanctioned by A8 (see m2). |
| Pure-Gen2 / BLE-only unchanged | Holds. Registration is still gated on `getModuleByName("TeslaAPI") is not None` (`TWCManager.py:785`). Without it, `distributeEVSEPower` stays off (`non_gen2` empty). |
| Blind rule keys on vehicleKey; one stopped car doesn't hide others | Holds. `_blindTWCs` (`VehicleEndpoints.py:48-84`) reads `getattr(slave, "vehicleKey")`. Slaves are `Gen2TWC`, because `TWCMaster.py:4` imports Gen2TWC as TWCSlave. `Gen2TWC.vehicleKey` returns `lastVIN` while plugged (`Gen2TWC.py:94-103`). Tested by `test_last_vin_plugged_twc_keeps_other_cars_listed`. A scan failure returns `(True, True)`; I probed it and it returned `[]`. |
| Deleted classes unreferenced | Holds. `git grep TeslaAPIEVSE\|TeslaAPIController\|_twcServedVINs` over the tree finds nothing. |
| No tokens in logs, no I/O under locks | Holds. The new code does not log tokens. The only locks touched are the registry's (pure reads). |
| Tests | Focused run of `test_vehicle_endpoint`, `test_telemetry_registry`, `test_registry_callers`, `test_teslaapi_readonly_gate`, `test_distributor_loop`, `test_provider_order`, `test_vehicle_priority`: 131 passed. |

## Concern rulings

- **Concern 1 (interim double listing).** Already ruled as an accepted intermediate state that Task 11 must close. The section below covers whether Task 11 closes it.
- **Concern 2 (two claims shown per Tesla).** Carried forward, unchanged by this task.
- **Concern 3 (dropped `test_not_read_only_without_tesla_api`): ACCEPTED.** The old assertion is the opposite of A17: with no setAmps candidate the endpoint must be read-only. What the old test protected is better expressed as the positive case, which is untested: a car that only TeslaBLE can serve (Owner-only TeslaAPI, BLE claim) is writable with `provider == "TeslaBLE"`. The report relies on this behaviour. Add that test (m4).
- **Concern 4 (stale `Gen3TWC.py:129` reference): ACCEPTED.** It was a no-op. The grep is clean.
- **Concern 5 (a failed send is not resent at unchanged amps for 600 s): ACCEPT as is, with a follow-up recommended.**
  - Before: `TeslaAPIEVSE.setTargetPower` called `carapi.setChargeRate` on every distributor pass. `_recordChargeRate` runs only when the send is accepted (`TeslaAPI.py:2001-2014`). A failed send was therefore retried on the next pass, about 1 s later. Each retry was a synchronous paid POST with a 10 s timeout on the serial loop. That recovered faster but was much more expensive when failures persisted (car asleep, 408s), and it stalled the RS-485 loop.
  - Now: the endpoint records at queue time. A failure at unchanged amps holds for up to 600 s, though `dispatch` still gives each provider `attempts()` tries within the one queued command. A change in amps still queues at once.
  - Worst case: the car keeps its previous rate for up to 10 minutes. That is a budget overshoot (solar or grid), not a wiring-safety issue, because the car's own charger pilot still enforces the wiring limit. On cost the new behaviour is strictly better.
  - Recommended follow-up: use the existing `queue_vehicle_command(task, callback)` hook. On a falsy result for the same amps, pull `_lastQueuedAt` back so the retry comes after a short backoff (for example 60 s), not 0, because 0 would bring back per-pass paid retries. The callback runs on the worker thread and writes plain attributes that the serial thread reads, which is acceptable. Guard it with `task["amps"] == self._lastAmps` so a stale callback cannot reset a newer record. Note that `dispatch` also returns False with no I/O when the only candidate is a module-less TWC provider, so a 60 s backoff there costs nothing.

## Task 11 must test (concern 1)

Task 11's grouping does close all three parts of concern 1 for a car on a **named** TWC:
- (a) `Gen2TWC.vehicleKey` (`lastVIN.upper()` at a plugged state) equals `VehicleEndpoint.vehicleKey` (`vehicle.key`, upper-cased by the registry, `VehicleRegistry.py:78`). The stopped car therefore becomes one point.
- (b) `point.minPower` is the maximum over the members, so the TWC's floor (normally 6 A) replaces the endpoint's 5 A. The point never makes a below-floor offer that would let Fleet through.
- (c) Inside a point with a local member, only the TWC gets `setTargetPower`. The endpoint never queues `setAmps`, so in mode 2 only `TWCSlave`'s heartbeat `setChargeRate` reaches the car.

Grouping also absorbs the case where the only candidate is a module-less Gen2TWC provider, which makes the endpoint "writable" but leaves `dispatch` with nothing to run.

Task 11 does **not** close one gap, which predates this task (the old `_twcServedVINs` behaved the same way once `plugVIN` was removed). A Gen2 at state 00 with a sleeping plugged car has `vehicleKey None`: unknown, not blind. The car's endpoint then stands alone and can queue Fleet amps unless live telemetry says the car is plugged in. Name it as out of scope for Task 11, or pin it with a test.

The plan's Task 11 tests use MagicMock endpoints, so they do not prove that real keys match. Task 11 must add tests that use a real `Gen2TWC` and a real `VehicleEndpoint` (registry vehicle) through `TWCMaster.chargingPoints()` and `distributeEVSEPower()`:
1. Stopped car (`currentVIN` empty, `lastVIN` set, state 0x03) plus its endpoint: one point. `master.queue_vehicle_command` gets no `setAmps`. `point.minPower` equals the TWC's `minAmps` in watts.
2. A lower-case `lastVIN`/`currentVIN` on the TWC groups with the upper-case endpoint.
3. Mode 1 with a budget below the TWC floor: the point is offered 0, and no 5 A `setAmps` is queued (no Fleet).
4. `chargeRateControl=2`, car on a named TWC: the distributor queues no `setAmps`. Only the heartbeat's `setChargeRate` path runs (no alternating values).
5. Inside a TWC point, `_evseTargetAmps` is set on the Gen2TWC and the endpoint's `setTargetPower` is never called (I3), including in the zero-out loop and the `not wants_power` branch.
6. A car on no TWC is its own point and queues `setAmps` (the endpoint path still works).
7. A correlated Gen3 car joins its Gen3 point and queues no `setAmps`.
8. `test_no_type_knowledge_left` passes for `TeslaAPIEVSE`/`TeslaAPIController`, which this task has already made true.

## Findings

### Critical
None.

### Important
None.

### Minor

- **m1. Gen3 blind rule is narrower than the Gen2 rule.** `VehicleEndpoints.py:71-79` blinds only on an `anon:` key, so a Gen3 with `occupied is True` and `vehicleKey None` lists every car. I probed this: the car was listed. It can happen when the plug edge's session open raised (`Gen3TWC.py:206-213`). It matches the brief, but it is inconsistent with the Gen2 rule. A Gen3 unknown also never sets `unknown`, so the telemetry-plugged exclusion ignores Gen3. Fix: use `_unknownKey(unit.vehicleKey)` for occupied Gen3 units and set `unknown = True` for them. The brief author should confirm.
- **m2. HomeAssistant is a new billed-tier amps writer.** An Owner-only TeslaAPI with an HA-attached car (`has_charge_current_number`) was read-only before. It is now budgeted, and its amps go through HA. On any install, a failed Fleet `setAmps` now falls through to HA within one `dispatch`. Both behaviours are what A8 and plan decision 4 intend. No code change is needed, but note it in the Task 11 CHANGELOG line ("a car's amps are queued…") so it is visible.
- **m3. Endpoint amps depend on VehiclePriority.** `VehicleCommandQueue._setAmps` (`VehicleCommandQueue.py:33-39`) drops `setAmps` at debug level when the resolved module has no `setAmps`. That happens if `Vehicle.VehiclePriority.enabled` is false (an undocumented key, on by default). The old `TeslaAPIEVSE` called `carapi.setChargeRate` directly and did not need VehiclePriority. Fix: log at warning once, or gate `VehicleEndpoints` registration (`TWCManager.py:785`) on VehiclePriority being loaded as well.
- **m4. Lost coverage from the deleted `test_teslaapi_controller.py`.** These cases are no longer covered:
  - a failed slave scan fails closed (the Gen3 walk inside the same `try` included);
  - the boundary just below `POWER_FLOWING_AMPS` (0.99 A is not blind; probed and confirmed);
  - `carapi.enabled()` False gives `[]`;
  - a cached endpoint is dropped once hidden.

  The BLE-writable case from concern 3 is also untested. Fix: add these to `tests/unit/test_vehicle_endpoint.py`, about five lines each, using the existing `master`/`slave` helpers.
- **m5. A blind pass drops `_lastAmps`.** `VehicleEndpoints.py:117-118` (`_keep({})`) clears the cache, so on unblind each endpoint is rebuilt and re-queues the same amps at once. Fleet is covered by `setChargeRate`'s skip-repeat; BLE resends once (free). This matches the old cache behaviour, so no action is needed unless blind flaps in practice. If it does, keep the hidden endpoints' records, for example in a VIN → `(amps, at)` side map.
- **m6. Concern 5 follow-up.** Add the callback-driven short backoff described above at `VehicleEndpoint.py:149-160`.
