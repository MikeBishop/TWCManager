# Task 6 review (80a5b03..aff0d37)

### Spec Compliance

- ✅ Spec compliant with the brief as written. `discover` (VehiclePresence.py:804-822) matches the interface. The TeslaBLE apply gate (TeslaBLE.py:~880-905), TeslaAPI apply gate (diff TeslaAPI.py:276-284) and car_api_charge start gate (diff TeslaAPI.py:203-210) are in place. The BLE read reports its plug state (get_charge_state), and so does a "disconnected" start reply (TeslaBLE.py:~1028). `update_vehicle_data` reports plug state and stamps `lastVehicleDataFetch`. Telemetry `_reportPlug` reports the first value as a read and a change as an edge. All three deferred fixes are present: `blePluggedIn` goes through `chargingStatePlugged`, `apiSource` reads only a fresh `lastChargeState`, and `WEAK_PLUG_MAX_AGE` exists. Every restore (limit -1) is ungated, and the tests confirm it.
- The two deviations the report states are both justified. `update_vehicle_data` doesn't report Unknown/SNA. Plug evidence counts only from a read made in this call. They match deferred fix 1/2.
- ⚠️ "Every command path reads before acting" is not fully true. TeslaBLE `car_api_charge` / `startCharging` (TeslaBLE.py:286-360, 1003-1030) does no read and has no gate. The brief only asked for the "disconnected" reply to be reported, so this isn't a brief violation. But the BLE start still wakes the car and sends `charging-start` before it knows whether the car is here, and the VIN-less loop starts every configured car, including NOT_HOME ones. Both behaviors existed before this task. The controller should decide whether this is in scope.
- Check: does any new gate cause a wake? It doesn't. The TeslaAPI gates compare `_readStamps` taken before the existing `update_charge` / `update_location` calls and add no read. `apiSource` returns {} when nothing was fetched. The TeslaBLE gate uses the read (or telemetry lookup) that follows the apply's existing `wakeVehicle`, and that wake was already there to act.

### Strengths

- Fresh-vs-cached evidence is handled carefully. TeslaAPI.py `_discover` uses the `lastVehicleDataFetch` / `lastChargeRead` stamps, and `apiSource` uses `lastChargeState`. That closes the "deferred update_vehicle_data returns True with stale values" hole.
- `chargingStatePlugged` is a single shared mapping, so `blePluggedIn`, `apiSource`, the gates and `_reportPlug` all agree.
- A not-here result is treated as handled, not as a failure: `notHere` makes TeslaAPI return "success", and an all-skipped TeslaBLE apply returns True. That prevents a channel fallthrough to the Fleet API.
- The tests use a real `VehiclePresence` end to end: the BLE apply read as unplugged leads through `runPass` to not_home with `onDeparting` run, and a presumed car on the Fleet path read as away ends up not_home. The weak-age tests cover stale, fresh and live telemetry re-asserting.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **VehiclePresence.py:818-821. `discover` lets weak evidence (api or telemetry) veto when a TWC names the car or a strong plug record is within the hold.** This breaks the spec's evidence order ("A TWC naming the car, or a BLE charge read, decides on its own"; "When they disagree, BLE or the TWC wins"). The brief's literal rule ("False when pluggedIn is False") creates the conflict, so this is a plan-level gap, not only an implementation slip.
   - The tracker already applies the right rule. `_applyUnplugged` (VehiclePresence.py:979-995) ignores a weak unplug when `vin in ctx["twcVins"]` or `_strongWithinHold(vin, True)`. `_here` counts a TWC naming the car. So presence stays HOME while the gate refuses to act.
   - Consequences: a car plugged into a TWC here gets no policy limit. The apply is never settled, so it retries on every policy cycle. On the Fleet path that is one vehicle_data read per 60 s limiter window. On the BLE path it is worse: TeslaBLE wakes the car (`wakeVehicle`, TeslaBLE.py:~843) before the telemetry/BLE read, so each policy cycle wakes the car and then sends nothing.
   - The location check (`inside is False and not bleReachable`) has the same gap: a TWC naming the car should also override an outside fix.
   - Fix: for a source not in STRONG_SOURCES, don't return False on `pluggedIn is False` or `inside is False` when `vin in self._twcVinsNow()` (an in-memory TWC lookup, called without the lock) or `_strongWithinHold(vin, True)` (under the lock). Add tests: TWC names the car + API Disconnected leads to discover True and a limit sent, and likewise for telemetry False on the BLE path.

#### Minor (Nice to Have)

2. **TeslaAPI.py `_discover` (diff 333-345): when `update_charge` takes its BLE branch, plug state comes from `chargingState` alone, and it is recorded as source "api".**
   - A Disconnected state with the latch Engaged (plugged per `blePluggedIn`) is gated as unplugged. Presence stays right because the strong BLE report recorded by get_charge_state wins, but the apply is skipped and retried.
   - Live telemetry values are also recorded as "api", not "telemetry". Both are weak, so the effect is cosmetic.
   - Fix: keep the BLE read's `pluggedIn` on the vehicle and prefer it, and pass the real source.
3. **VehiclePresence.py:960-964: `_applyPlugged` ignores `fastCharger` for strong sources.** A BLE plugged + fastChargerPresent read makes the car HOME while `discover` returns False. This can't happen in practice, since BLE is out of range at a Supercharger, but the two disagree. Fix: check `fastCharger` before the strong branch.
4. **Fail-open/fail-closed asymmetry.**
   - TeslaBLE: if `tracker.discover` raises, the per-vehicle `except` (TeslaBLE.py:~944) leaves `attempted_count` incremented. An apply with no other success then returns False, and VehiclePriority falls through to TeslaAPI.
   - TeslaAPI: `_discover` fails *open* (`except: return True`, diff TeslaAPI.py:350-352) and sends the limit.
   - `discover` is lock + append only, so the chance is negligible; hence Minor. Fix: fail closed in both. TeslaBLE should wrap the call and treat an exception as skipped (handled). TeslaAPI's `_discover` should return False.
5. **Test gaps.** No test covers the TeslaBLE gate's telemetry branch (`source "telemetry"`, `telemetryPluggedIn` False → nothing sent). No test covers TeslaAPI `car_api_charge` for a plain Disconnected or away car (only the fast charger case). No test covers the `_discover` exception path.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The brief is implemented faithfully and carefully, with good fresh-vs-cached handling and good end-to-end tests. But `discover` lets weak API/telemetry evidence override a TWC naming the car (or a strong plug within the hold), which contradicts the spec's evidence order. On the BLE path that turns into a car wake every policy cycle with no command sent.
