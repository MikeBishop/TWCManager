# Task 8 review (02c040a..4f6cda9)

### Spec Compliance

- ✅ Spec compliant for everything the brief names: `broadcastVINs` (VehiclePresence.py:369-398), `_chargeVIN` and all 4 start/stop/cancel call sites (TWCSlave.py:35-50, 74, 82, 91, 114), TeslaAPI targets plus `car_api_available(charge, vin=vin)` plus the target-only stop reset (TeslaAPI.py:189-205, 221-254), the TeslaBLE VIN-less loop limited to configured ∩ candidates (TeslaBLE.py:281-296, 330-343), and HA honouring `task["vin"]` (HomeAssistant.py:142, 161-162). All 7 named tests are present.
- Extra, accepted: the `twcVins` exclusion (VehiclePresence.py:384) goes beyond the brief's literal list. It is right: the caller is a VIN-less TWC with no attribution, so a car another TWC names is the strongest "plugged in elsewhere" evidence. The brief's own UMC clause already treats `twcVins` membership as being plugged at a TWC, and `_vinLessPlug` uses the same candidate exclusions. Keep it, and mention it to the user because it is wider than the approved wording.
- ⚠️ Cannot verify from the diff: `TeslaBLE.setChargeRate(vehicle=None)` (TeslaBLE.py:~733-745) still loops over every configured car, waking each one over BLE. It is a rate command, not a charge command, so it is outside Task 8's file list, but it breaks the same "never to every car" principle. The controller should check whether a later task covers it.

### Strengths

- `_chargeVIN` puts the evidence in the right order (currentVIN, then plugVIN except NON_TESLA, then the attribution), and it is exercised through the real `send_master_heartbeat` start path, not only unit calls (test_twcslave.py:717-726).
- The source-level guard `"CarsCharging(self.currentVIN)" not in source` keeps the old call from coming back.
- The TeslaAPI tests use a real `VehiclePresence` and assert the actual POST URLs, and that V2's `update_charge` was not called (test_teslaapi_presence.py:535-559).
- The BLE "failed probe" interim rule correctly separates a reach record that aged out from a failed one, and both cases are tested (test_vehicle_presence.py:804-823).
- Changing `TestDiscoveryOnWake` to pass a VIN was correct. As a broadcast it would have passed vacuously.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **plan-mandated. TeslaAPI.py:241 (with TeslaAPI.py:357-395)**: a VIN-less broadcast still wakes non-candidates (implementer concern 2). The brief specifies `car_api_available(charge=charge, vin=vin)` word for word. `car_api_available(charge=True, vin=None)` wakes every `atHome` car (`isHome`: HOME or PRESUMED) that isn't ready. That includes the HOME cars `broadcastVINs` excludes because they are attributed to another TWC, named by a TWC, or on a UMC with a failed probe. The command loop then skips them, so they get a billed Fleet `wake_up` and lose battery with no command after it, again each time they fall asleep. This breaks "broadcast only to candidates". It is worst in exactly the case concern 5 describes: when BLE finds no candidate and returns False, VehiclePriority falls through to TeslaAPI (under `prefer_ble`/`api_only`), which wakes the excluded HOME cars and then sends nothing. Fix: compute `targets` before `car_api_available` and pass the target VIN set (e.g. `vins=`), or skip non-targets in the wake loop. Passing the VIN set doesn't bring back the vehicle-list regression, because `broadcastVINs()` gets its VINs from presence, not from `carApiVehicles`. Add a test where V2 is HOME but attributed elsewhere and assert V2 is never woken. The live box (`ble_only`) is not affected, because TeslaAPI is skipped for commands there.

2. **TeslaAPI.py:253-254**: the advisor-found regression fix (choosing the targets again after `car_api_available` loads the vehicle list) has no test. Every TeslaAPI test mocks `car_api_available` and sets `carApiVehicles` in advance, so deleting line 254 leaves the suite green. I checked the fix with a scratch probe (`car_api_available` side effect loading `[V1, V2]` into an empty list, then a targeted start to V1): it sends exactly one `charge_start` to V1, so the fix works today. The risk is a future regression, not a current bug. It needs a regression test in `TestChargeTargets` with `carApiVehicles = []` and `car_api_available.side_effect` loading the cars.

#### Minor (Nice to Have)

3. **TeslaAPI.py:200-204, TeslaBLE.py:290-295**: fail-open when `broadcastVINs` raises (concern 4). Fail-open is acceptable for a start or stop. BLE only reaches cars in range anyway, and TeslaAPI still applies the per-car `atHome` gate, which falls back to the last location fix when presence is broken. Failing closed would turn a presence bug into "charging never starts". `broadcastVINs` can only raise from a bug, because `_knownNow` and `_twcVinsNow` already catch their errors. Keep fail-open with the WARNING. Optionally rate-limit the WARNING, since it fires on every command.

4. **TeslaAPI.py:818**: a targeted start still runs the policy-wide `applyChargeLimit(self.lastChargeLimitApplied)` (concern 3). It is pre-existing, rate-limited to once every 60 s, only touches `atHome` cars, and only wakes when a limit was raised. That fits the "policy applies to HOME/presumed" constraint, so it doesn't break Task 8. Follow-up: pass `vin=vehicle.VIN` so a targeted start reads and wakes only its own car.

5. **TeslaBLE.py:~329-330**: a stop, even a targeted one, still clears `_stopAskingToStartCharging` for every car, while TeslaAPI now resets only the targets. This only resets state and sends nothing, but the two modules now disagree. To make them match, clear `vin` alone when one is given.

6. **Concern 5 confirmed**: with no candidates, BLE returns False (TeslaBLE.py:331-335). TeslaAPI's command loop then has no targets and returns "success", sending no command, so VehiclePriority stops there. The only side effect is the wake in Important 1. HA's VIN-less path keeps its `_atHome` gate. The behaviour is correct apart from #1.

7. **VehiclePresence.py:388-390**: the failed-probe exclusion never ages out until a later successful contact. This follows the brief ("when a BLE contact failure is recorded"), and Task 12's `bleSilent` replaces it. One edge case: a HOME car on this VIN-less TWC that is out of BLE range and was left unattributed (an ambiguous multi-TWC case) gets no broadcast from any channel. Add a note at `bleSilent` (Task 12).

9. **HomeAssistant.py:577-581**: a targeted VIN that HA doesn't hold returns "success" with nothing processed. I checked whether that could block a fallthrough: `calculateModulePriority` (TWCMaster.py:160-168) gives HA no priority, so VehiclePriority never dispatches to it and nothing is blocked. No change needed.

10. **Implementer's test output**: `1088 passed, 1 warning`. The warning comes from test_enphase_ems.py. The implementer says it was there before this change (checked with -W error) and this diff doesn't cause it, but the output is not clean. Track it separately.

8. **test_twcslave.py:739-742**: `test_no_evidence_is_none` doesn't cover `vinForTwc` raising (the except branch at TWCSlave.py:48-49). Coverage nit.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Targeting is correct and well tested for commands, but the TeslaAPI broadcast wake still reaches HOME cars that `broadcastVINs` excludes. That is a non-candidate wake with no command after it, and it shows up in the BLE-no-candidate fallthrough. The vehicle-list re-pick fix also needs its regression test.
