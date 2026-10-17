# Final fix pass report

Branch fix/vehicle-presence, 32bd76b..16a4bfd. Model: Opus 5.5. Each commit
has the trailer `Co-Authored-By: Claude Opus 5.5`. The trailer in
global-constraints.md ("Fable 5.1") is stale for this pass.

## Commits

| Commit | Item |
|---|---|
| b4830db | 1 (as revised by the user): `CarApiVehicle.atHome` becomes a property that defers to VehiclePresence |
| 5e84338 | 2: TeslaBLE's vin=None apply skips VINs that presence says are away |
| 473b570 | 3: bound `_observations` and per-VIN due times |
| 89d460e | 8 (added by the user): a TWC-reported VIN is proof of home; geofence repair moves to the presence thread |
| 201ef3a | 4: HOME -> AWAY -> HOME test through the real handlers and a real queue |
| d60071b | 5: arrival with `lastChargeLimitApplied == 0` resets dedupe state but queues nothing |
| 1493c90 | 7: an INFO line for each per-VIN TeslaAPI apply |
| 16a4bfd | 6: `resetChargeLimitState` also clears `stopAskingToStartCharging` |

## Tests

Full suite: 707 passed with 1 pre-existing warning (baseline 669).
`test_vehicle_presence.py` passed 5 out of 5 runs (49 tests each). Black is clean.

## Notes per item

**1 (revised).** On `CarApiVehicle`, `atHome` is now a property.
- **Setter:** stores the raw location answer in `_locationAtHome`. The existing writes are unchanged.
- **Getter:** returns `presence.state(VIN)` when it is home or away. It falls back to the raw value when presence says unknown, is missing, the VIN is empty, or `state()` raises.
- **Raw readers:** these read `_locationAtHome` directly:
  - `PresenceSources.apiSource` and `CarApiVehicle._reportLocation`, so presence is not fed its own state.
  - `reconcileHomeLocation` (formerly `vehicleIsDefinitelyHome`), because it compares the TWC against the GPS fix.
  - The status-deferral branch in `update_vehicle_data`, which acts on the fix it just computed.
- **Audit:** Telemetry's `_reportLocation` and `telemetrySource` compute from the sync coordinates and never read `atHome`.
- **Not in the brief:** the `needToWake` computation in `TeslaAPI.applyChargeLimit` is now gated the same way as the stopTrying reset (`vin is not None or vehicle.atHome`). Without that, a policy-wide apply still asked to wake cars on behalf of an away car it was about to skip.

**2.** Skipped VINs are counted in `skipped_count` and are not counted as attempted. When every VIN is skipped, the method returns True, the same as the dedupe skip, so VehiclePriority does not fall back. A per-VIN apply is never skipped.

**3. Bound, not gate.**
- Observations go into `deque(maxlen=256)`, which keeps the newest.
- Each due-time set keeps the earliest 64.
- Recording still happens before `start()`. Presence is built in `TWCMaster.__init__` but started only after all modules have loaded, and retained TeslaMate messages and the first nominations arrive in that window.
- Without the thread, state stays UNKNOWN and `atHome` falls back to the raw value, as the coordinator asked.
- No existing test changed.

**4.** The queue worker starts only at the end. The test asserts the pending entry after each transition: arrival apply, then the remote-only restore, then the arrival apply again under the same key. The module sees exactly `[(50, VIN, False)]`.

**5.** A policy limit of -1 (policy has no limit) still queues a restore. Only 0 (not yet evaluated) skips. Hand-set adoption still runs before the skip.

**7.** The line reads `Charge limit <N%|restore> for ...<last 6>: <outcome>`. The possible outcomes are: set to / restored to, already at ... nothing sent / nothing to restore, could not read, not ready, already handled, and failed. The policy-wide apply adds no INFO line.

**8.**
- **TWC proof:** `recordVehicleVIN` now only calls `vehiclePresence.observeProof(vin, "twc")`, so it does no I/O on the serial loop. In the presence pass, a proof does three things:
  - It runs the injected `onHomeProof(vin, source)` hook outside the lock. The default hook, `PresenceHandlers.homeProofHandler`, calls `TeslaAPI.reconcileHomeLocation` when TeslaAPI is loaded.
  - It then drops any queued `("location", vin, False)` for that VIN.
  - It then sets HOME and resets the failed-probe count.
- **Why the drop:** the hook's own `update_location` reports the away fix it is repairing. Without the drop, the next pass would declare the car away and queue a departure restore for a car that is plugged in.
- **`reconcileHomeLocation`:** keeps the fetch, the 600 s stale check, `setHomeLat/Lon` and the two background tasks. It no longer sets `atHome`.
- **Nominate dropped:** the proof already gives HOME and the arrival apply. A probe in the same pass could only agree, or, on a bad geofence or stale fix, immediately undo the arrival.

## Concerns

- **BLE wake on the presence thread (item 8).** For a BLE-capable car that is not telemetry-synced, the `update_location(0)` call in `reconcileHomeLocation` can run a BLE `state` read and a `wakeVehicle` on the presence thread. This is a deliberate exception to "presence never wakes over BLE". It is the fetch the user asked to keep, it runs only when the raw fix says away, and the car is provably plugged in.
- **No hand-set adoption on a TWC-proof arrival.** That arrival carries `limit=None`, so a limit set by hand while away is not adopted on this path. A BLE-contact arrival behaves the same way.
- **Raw value stays stale after a home move.** After the home location is moved, `_locationAtHome` stays False until the next fix. Readers see presence HOME. Because `reconcileHomeLocation` gates on the raw value, the car's next TWC proof does one more location fetch, which recomputes the raw value against the new home and fixes it. The cost is one extra Fleet API or BLE read per home move.
  - **Question for you:** do you want `car.atHome = self.is_location_home(car.lat, car.lon)` after `setHomeLon`? It recomputes the location answer from the fix already in hand. That is different from the unconditional `= True` that was removed. I left it out.
- **Lock order.** Reading the `atHome` property now takes `presence._lock` (through `state()`) from any thread, including the main loop, HTTP, and `car_api_charge` under `backgroundTasksLock`. `_lock` is a leaf lock: presence never calls into a vehicle, module or master method while holding it, and `state()` touches only `_state`. So there is no cycle.
- **Geofence repair no longer runs in non-master modes.** The presence thread never starts there. Before this change, `vehicleIsDefinitelyHome` ran on every VIN read. This is consistent with "nothing acts without the thread", but it is a change in behaviour.
- **Item 7 scope.** The INFO line fires only when the per-VIN loop runs. The early `return "error"` paths log nothing at INFO, as before: invalid limit, `car_api_available` False, unknown VIN, and failed wake.
- **Item 8 coverage is split across two tests.** "recordVehicleVIN marks the VIN home" is proven in two halves:
  - test_twcmaster checks that `observeProof` is called and that no module is looked up.
  - test_vehicle_presence checks that a proof leads to HOME and to the hook running.
  There is no single end-to-end test.
- **Test simplification (item 4).** Between arrival and departure, the test clears the pending queue to stand in for the worker sending the first apply.
