### Spec Compliance

- ✅ Spec compliant. Every file in the brief has its hunk (PresenceSources.py, VehiclePresence default, TeslaAPI vehicleOnlineStates/_reportLocation + both call sites, config.json, three test files). Code matches the brief.
- ⚠️ Test count: report says 619 (596 + 23 new). Brief/global-constraints expect 605 at this task. The 23 new tests match the brief; the 14 difference comes from earlier tasks. Controller should confirm the ledger.
- ⚠️ Telemetry-branch location push is intentionally deferred to Task 8.

### Strengths
- Named risk (a) no wake: PASS. apiSource calls update_vehicle_data only when vehicleOnlineStates()[vin] == "online" (PresenceSources.py:79). update_vehicle_data -> get_car_api / ready / is_awake (TeslaAPI.py ~1638-1693, 1695-1760) issue only GETs (vehicle list, vehicle_data), plus token refresh. No wakeVehicle, ble.wakeVehicle, or car_api_available is reachable. The BLE wake fallbacks live in update_location/update_charge, which are not called. bleSource reads get_charge_state only after probePresence reports awake; _fetch_state_locked runs `tesla-control state charge`, with no wake or ping.
- (b) PASS for the contract: unreachable returns {"atHome": None,...}, which sets bleFailed in VehiclePresence._probe (VehiclePresence.py:288-289). Reachable returns atHome True with the limit. Telemetry applicable sets telemetryLive.
- (c) PASS: observeLocation takes the lock, appends and sets an Event (VehiclePresence.py:145-149). The presence lock is not held during _probe (:231). The observation is drained on the next pass and applied after the probe, as an unchanged HOME state. The arrival limit from the probe is not lost, and nothing recurses. _reportLocation swallows exceptions.
- (d) partial: token absent or URL empty returns {} before any request; exceptions return {}; car_api_available is untouched. Timeout: see Important #1.

### Issues

#### Critical
None.

#### Important
1. TeslaAPI.py vehicleOnlineStates (`requests.get(url, headers=headers, verify=self.verifyCert)`, no `timeout=`). requests has no default timeout. A stalled connection blocks the presence thread forever inside a source. That stops all probing, and the thread never holds the lock, so nothing else detects it. Named risk (d) requires a timeout. The brief's code omits it (plan-mandated), but it is still a defect. Fix: add `timeout=` (e.g. 10-15 s) and a test asserting the kwarg.
2. PresenceSources.py:46-61 bleSource treats "VIN not BLE-enrolled" the same as "car out of range". probePresence returns reachable False when the binary is missing or `settings["Vehicles"][vin]` is absent (TeslaBLE.py probePresence). bleSource then returns the no-answer shape, so bleFailed is set. If the API is also no-answer (car asleep) and telemetry is absent, _applyProbe (VehiclePresence.py:309-314) declares AWAY after 2 failed probes. A sleeping, home, API-only car on an install with BLE enabled for another car would then get a spurious departure. Fix: have bleSource return None for a VIN BLE is not configured for (e.g. via a ble helper or settings check), and add a test.

#### Minor
1. PresenceSources.py:82 apiSource sets `vehicle.statusDeferral = 0` before the call. If the fetch fails, deferral stays 0, so other callers of update_vehicle_data lose their throttle until the next success. Restore the previous value on failure.
2. apiSource: vehicle_data goes through ready() -> is_awake(), which can issue a second GET after vehicleOnlineStates just did one. It is cached for 120 s and never wakes, but it is a duplicate API cost. A stale cached lastVehicleAwakeState=False can also silently yield no answer.
3. _reportLocation reports `bool(self.atHome)`. is_location_home returns False when home is unset and the GPS is stale (TeslaAPI.py:520-530), so presence can see a spurious AWAY in that narrow case.
4. telemetrySource calls is_location_home without gpsAge. If home is unset it can seed home from a telemetry fix (side effect on a read path).
5. The tests for vehicleOnlineStates assert neither a timeout kwarg nor the Authorization header. A source raising (instead of returning no-answer) is treated by _probe as "not applicable" rather than bleFailed. This is acceptable, but note it.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Wake safety, the presence-thread/lock contract and re-entrancy are sound. The missing request timeout on the presence thread (named risk d) and the BLE "not enrolled" -> spurious AWAY path need fixing before this can be trusted.
