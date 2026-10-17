# Task 8 report: charge commands go to the car the plug names

Branch `presence/3-plug-presence` (worktree wt-plug). Commit `4f6cda9` on top of `02c040a`.
Subject: `Charge commands go to the car the plug names, broadcasts to candidates`.

## What I implemented
- `VehiclePresence.broadcastVINs()`: returns the known VINs, sorted, that are `isHome` (HOME or PRESUMED) or here (`_inside` True, or `bleReachable`). It reads `known` and `twcVins` outside the lock and decides under the lock. It excludes a car plugged in elsewhere:
  - attributed to a VIN-less TWC (`_twcVin` values). The caller has no attribution of its own, because `_chargeVIN` would have used it.
  - home (`state == HOME`) whose latest `_reach` record is a failed probe (`(False, t)`): the interim rule standing in for `bleSilent`. A reach that merely aged past 300 s is not a failure, so that car stays a candidate.
  - **named by a TWC (`twcVins()`).** This goes beyond the brief's literal list; see Concerns.
  - A purely presumed car with no records stays included.
- `TWCSlave._chargeVIN()`: returns `currentVIN`, else `plugVIN` (if it isn't None or NON_TESLA), else `master.vehiclePresence.vinForTwc(self._presenceKey())`, else None. Exceptions are logged at debug level and give None. It replaces `self.currentVIN` in all 4 start/stop/cancel calls.
- `TeslaAPI.car_api_charge`: `vin = task.get("vin")`, and the new `_chargeTargets(vin)` picks the targets. The stop reset uses them as computed up front; the main loop computes them again after `car_api_available`, which may have just loaded the vehicle list (that keeps the first command after startup working). Targets: that vehicle alone; for a VIN-less command, the vehicles in `broadcastVINs()`; with no presence, or when presence raises (logged at WARNING), every vehicle. The stop-reset loop and the main loop cover only the targets. It calls `car_api_available(charge=charge, vin=vin)`.
- `TeslaBLE.car_api_charge` with vin None: the new `_broadcastTargets()` gives `settings["Vehicles"]` ∩ `broadcastVINs()`, keeping config order. With no presence, or when presence raises, it uses every configured car. With an empty target set it returns False, so VehiclePriority falls through to another channel. The targeted path was already single-car and is unchanged; a test now covers it.
- `HomeAssistant.car_api_charge` honours `task["vin"]`: when it's set, other vehicles are skipped before `refresh_from_home_assistant`. The VIN-less path keeps its `_atHome` (presence `isHome`) gate.

## Tests
New tests:
- test_vehicle_presence.py `TestBroadcastVINs`: `test_broadcast_vins_never_include_an_away_unplugged_car`, `test_a_ble_reachable_car_not_home_is_a_candidate`, `test_vin_less_broadcast_skips_a_car_plugged_in_elsewhere`, `test_a_home_car_with_no_ble_failure_stays_a_candidate`, `test_a_ble_reachable_home_car_after_a_failure_is_a_candidate`.
- test_twcslave.py `TestChargeVIN`: `test_start_goes_to_the_vin_the_twc_reads` and `test_start_on_a_vin_less_twc_goes_to_its_attributed_car` drive the real `send_master_heartbeat` start path. Also `test_current_vin_comes_first`, `test_a_non_tesla_plug_falls_through_to_the_attribution`, `test_no_evidence_is_none`.
- test_teslaapi_presence.py `TestChargeTargets`: `test_unattributed_vin_less_start_broadcasts_to_candidates_only` and `test_api_charge_with_a_vin_touches_no_other_car` use a real tracker and patch `requests.post`; they assert the POST URLs and that V2's `update_charge` is not called. Also `test_a_stop_resets_only_the_targets` and `test_without_presence_a_broadcast_goes_to_every_car`.
- test_teslable_presence.py `TestChargeTargets`: `test_ble_broadcast_skips_a_car_away_and_unplugged` (start and stop), `test_targeted_start_touches_only_that_car`, `test_no_candidate_fails_so_another_channel_can_try`.
- test_homeassistant_presence.py: `test_ha_charge_with_a_vin_touches_no_other_car`.

Changed existing tests:
- `test_cancel_stop_passes_the_current_vin` is renamed `..._charge_vin`. It now asserts `cancelStopCarsCharging(self._chargeVIN())` and that no `CarsCharging(self.currentVIN)` remains.
- `TestDiscoveryOnWake::test_api_charge_start_skips_a_car_at_a_supercharger` now passes `"vin": VIN1`. Its tracker knows no VINs, so as a broadcast it would have passed vacuously with no targets.

## TDD
- RED: 17 failed, 2 passed. The 2 that passed were the BLE targeted-start test (that path was already per-VIN) and the TeslaAPI no-presence fallback (old behaviour kept). The failures had the right reasons: HA, BLE and TeslaAPI commanded both cars; the stop reset touched V2; `broadcastVINs` and `_chargeVIN` didn't exist; the source assertion failed.
- One test-fixture fix was needed, unrelated to targeting: the TWCSlave heartbeat test needed `getModulesByType` and `getFakeTWCID` on the master mock.
- I confirmed the TWCSlave start tests go RED for the right reason by reverting only TWCSlave.py: `assert ('',) == ('VIN1',)` / `('VIN2',)`.
- GREEN: full suite `1088 passed, 1 warning`; the warning comes from test_enphase_ems.py, which this change doesn't touch (checked with -W error). The baseline was 1070.

## Files
lib/TWCManager/{VehiclePresence.py, TWCSlave.py, Vehicle/TeslaAPI.py, Vehicle/TeslaBLE.py, Vehicle/HomeAssistant.py}. Tests: test_vehicle_presence.py, test_twcslave.py, test_teslaapi_presence.py, test_teslable_presence.py, test_homeassistant_presence.py.

Black was run on the 5 lib files and on the two test files that were already clean (test_vehicle_presence.py, test_homeassistant_presence.py). test_twcslave.py, test_teslaapi_presence.py and test_teslable_presence.py were not black-clean before, so they were not reformatted; the new hunks are written in black style.

## Self-review
- Lock discipline: `_knownNow` and `_twcVinsNow` are called without the lock, matching the file's convention.
- A broadcast happens only from a VIN-less TWC with no attribution, because every TWCSlave call now goes through `_chargeVIN`. TeslaAPIEVSE always passes a VIN. So excluding cars attributed to "any" TWC is the same as excluding cars attributed to "another" TWC.
- No log line holds a token. The new WARNING lines log only the exception text from presence.

## Concerns
1. **twcVins exclusion beyond the brief's literal list.** `broadcastVINs` also leaves out cars that a VIN-reading TWC names right now. The spec says a broadcast goes "only to the candidates", and the existing candidate set in `_vinLessPlug` already leaves out `twcVins` and attributed cars. A car another TWC names is the strongest evidence that it's plugged in elsewhere. Reviewer: confirm, or drop the `vin in twcVins` check (the third case of `test_vin_less_broadcast_skips_a_car_plugged_in_elsewhere` covers it).
2. **TeslaAPI's broadcast wake isn't narrowed.** `car_api_available(charge, vin=None)` still wakes every `atHome` (isHome) car. That set includes cars that are HOME but attributed or named elsewhere, which the command loop then leaves out. I didn't widen `car_api_available`'s signature. A follow-up could pass the target set to it.
3. **TeslaAPI's targeted start still runs a policy-wide apply.** It calls `applyChargeLimit(self.lastChargeLimitApplied)` across every car before the POST, which can read other at-home cars. The behaviour is unchanged; the tests mock it.
4. **A stop broadcast with no candidates.** TeslaBLE returns False, VehiclePriority falls through to TeslaAPI, and TeslaAPI has no targets, so nothing is stopped. That is intended: there's no car to stop.
5. **Fallback when presence raises.** TeslaAPI and TeslaBLE then go to every car, with TeslaAPI's atHome gate still applied per car. This keeps charging working, but it is the old broadcast-to-all behaviour, logged at WARNING. The alternative is to fail closed.

## Fix round 1 (commit 0fe75a8; a new commit, not an amend)
1. **TeslaAPI broadcast wake.** `car_api_available` now takes `vins=` (a collection; `vin=` is unchanged), and its wake loop skips any vehicle whose VIN isn't in that set. `car_api_charge` now builds its targets in two steps: `_chargeTargetVINs(vin)` gives `{vin}` for a named car, the `broadcastVINs()` set for a broadcast, or None when there's no presence or presence fails. `_chargeTargets(targetVINs)` filters the vehicle list by that set. A broadcast passes `vins=<candidates>`, so an empty candidate set wakes nothing; a targeted command still passes `vin=`; with no presence the wake behaviour is unchanged. Test: `test_broadcast_wakes_only_candidates` runs the real `car_api_available` with V2 HOME but attributed to another TWC, and checks that `wakeVehicle` is called for V1 only. RED before the fix: it was called for both.
2. **Test for the re-pick.** `test_targets_are_picked_after_the_vehicle_list_loads` starts with `carApiVehicles = []`, and the mocked `car_api_available` loads both cars; it asserts exactly one charge_start, to V1. It passed against the existing fix. I confirmed it guards that fix: with the re-pick line removed it fails, and passes again once the line is restored.
3. **TeslaBLE.setChargeRate(vehicle=None).** It now goes to `_broadcastTargets()`: configured cars ∩ `broadcastVINs()`, all configured cars when there's no presence, and fail-open when presence raises. With no candidates it logs at INFO and returns False without waking any car. Tests: `test_vin_less_charge_rate_goes_only_to_candidates` (RED before the fix: both cars were woken), `..._without_presence_goes_to_every_car`, `..._with_no_candidate_sends_nothing` (RED before the fix: returned True).
- Full suite: 1093 passed, 1 warning (the existing enphase warning). Black run on TeslaAPI.py and TeslaBLE.py. The minor findings stay deferred, as the coordinator directed.
