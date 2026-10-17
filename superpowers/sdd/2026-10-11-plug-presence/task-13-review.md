# Task 13 review: deploy/presence-3 (a8ef9cb merge, 3b7fdd0 port)

Spec verdict: **Compliant.** The merge resolutions match deploy/presence-2 items 1 to 4. The port maps exactly as the brief says. The wake gate is driven by presence, so a car that starts asleep with no location fix is still woken (verified below). There are two test-strength gaps and one wording fix. None of them blocks deploy.

All line numbers are for the wt-plug checkout at 3b7fdd0. Tree, index and HEAD were not touched. Mutations ran in a `git archive` copy in scratchpad/mut13.

### Spec Compliance

**1. Wake gate (highest priority): OK.**
- The merged loop gates on `if not vehicle.atHome:` (`lib/TWCManager/Vehicle/TeslaAPI.py:485`). It drops fe764ff's `and vehicle.lat != 10000`, as presence/4 (14ae080:412) already had.
- `atHome` is a property (`TeslaAPI.py:2284-2297`). When `master.vehiclePresence` exists and the VIN is set, it returns `presence.isHome(VIN)`.
- `isHome` is `state in (HOME, PRESUMED)` (`VehiclePresence.py:406-409`). `_stateLocked` returns PRESUMED when there is no entry (`VehiclePresence.py:395-399`).
- `TWCMaster.__init__` always builds `self.vehiclePresence` (`TWCMaster.py:112`).
- So a car with no fix and no evidence gets `atHome` True and is woken. A location read only feeds presence through `_reportLocation` after a real read (`TeslaAPI.py:2530-2545`, `2600`). A car that has never been read leaves no location evidence.
- Probe: a real `CarApiVehicle` with lat=10000 and `_locationAtHome=False`, over a real tracker with no evidence. Running `car_api_available(charge=True)` calls `wakeVehicle`. Passed (scratchpad/probe13/test_probe_nofix_wake.py).
- On coverage: `test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it` and `test_startup_wake_finds_the_car_plugged_and_starts_charging` (`tests/unit/test_plug_presence_scenarios.py:936`, `973`) wake over **BLE**. They never exercise the Fleet wake loop with no fix. Fleet coverage comes in two separate pieces:
  - `TestWakeOnlyForAHomeCar::test_asleep_plugged_car_is_woken_to_charge` (`tests/unit/test_teslaapi_presence.py`): a FakeVehicle with atHome=True and lat=10000.
  - `TestAtHomeFollowsPresence`: presumed gives True.
  - Nothing pins the two together (see Minor 2).

**2. Auth per purpose: OK.**
- Reads use `slotFor("read")`:
  - `loadVehicleList` (`TeslaAPI.py:327`, timeout=30, 401/403/410/412 → `slotRequestFailed`);
  - `vehicleOnlineStates` (`:1418-1431`, timeout=30, same codes → `slotRequestFailed`, no retry);
  - `get_car_api` (`:2397-2433`; headers rebuilt per attempt; one retry after a refresh);
  - `car_api_available` gate (`:414`).
- Commands and wakes use `slotFor("command")`:
  - `car_api_charge` (`:908`);
  - `setChargeRate` (`:1941`, timeout=10);
  - `wakeVehicle` (`:2123`);
  - apply_charge_limit (`:2741`).
- `hasRemoteChannel` is `api.slotFor("command") is None → False` (`PresenceHandlers.py:17`). `apiSource` is `slotFor("read")` (`PresenceSources.py:126`).
- The refresh path is untouched: `git diff fe764ff HEAD -- TeslaTokenSlot.py` is empty, and `REFRESH_TIMEOUT = 30` (`TeslaTokenSlot.py:27`, used at `:199`).
- The refresh lock is preserved. `vehicleListLock = RLock()` (`TeslaAPI.py:91`) is held across `loadVehicleList` and its refresh (`:324`), as the comment at `TeslaTokenSlot.py:197` describes. The remerge-diff has no hunk in `refreshSlot` or `loadVehicleList`.
- The wake loop's dedent and order match fe764ff, plus presence's vin/vins skips (remerge-diff checked).

**3. Tokens in logs: OK.**
- `git diff presence/4-fleet-rate-queue HEAD -- lib` adds no log line that interpolates a token, header or `accessToken`.
- No `logger` line in TeslaAPI.py, Presence*.py or TeslaTokenSlot.py references `headers`, `accessToken`, `refreshToken` or `Bearer`.
- The one exception-text debug line in `vehicleOnlineStates` (`TeslaAPI.py:1442`) is pre-existing (14ae080:1377), and the port doesn't touch it. A requests exception carries the URL, not the headers.

**4. Presence targeting: OK.**
- `car_api_charge` reads `task.get("vin")` and calls `_chargeTargetVINs` and `_chargeTargets`. It passes `vin`, or `vins` for a broadcast, to `car_api_available` (`TeslaAPI.py:732-772`).
- The wake loop's first checks are the per-VIN and candidate skips (`:437-443`). `applyChargeLimit` passes `vin=vin` (`:1158`).
- `startCarsCharging` and `stopCarsCharging` in TWCMaster still queue `"vin"` (`TWCMaster.py:1926`, `1952`).

**5. Scenario assertions: OK.**
- `git diff 14ae080 HEAD -- tests/unit/test_plug_presence_scenarios.py` removes no `assert` line.
- The changes are World/FakeFleet fixture setup: `storeToken`, and `/products` routing for Owner.
- The new line `assert api.readOnly is (slots == "owner_read_only")` is an added fixture guard.
- `test_policy_wide_apply_skips_departing_on_every_channel` now stores a real Fleet token instead of relying on a stale attribute. That is legitimate, but see Minor 1: it still doesn't exercise TeslaAPI's away-skip.

**6. TestDeployRegression20261011 non-vacuity: partly.**
- `test_fleet_fallback_restore_needs_a_command_slot` is non-vacuous. Mutating `hasRemoteChannel` to `slotFor("read")` makes it fail (reproduced).
- `test_departing_car_inside_radius_gets_nothing_on_any_channel[both]`: the BLE half is non-vacuous. Disabling TeslaBLE's `not presence.isHome` skip (`TeslaBLE.py:843`) fails both parametrizations, and fails the original test_2026_10_11.
- The Fleet half is **not** sensitive to TeslaAPI's policy-wide away-skip. With `if vin is None and not vehicle.atHome: continue` (`TeslaAPI.py:1204`) replaced by `if False:`, all 3 tests still pass, even after clearing `stopTryingToApplyLimit` every loop.
  - Reason: the car already holds 50%, from BLE before departure, and TeslaMate answers `update_charge` live. A policy apply of 50 is a no-op with or without the skip.
  - This is inherited from the test_2026_10_11 shape that the brief told it to copy.

Other brief items:
- Leftover-accessor grep (Step 3), run by me with the implementer's filter (`grep -vE 'slot\.baseURL|baseURLs|settings\.html'`): it prints only `api.fleetSlot.baseURL` / `api.ownerSlot.baseURL` assertions in the token-slots tests. These are legitimate slot attributes. No removed accessor is left in lib/ or tests/.
- Merge commit subject is correct, and its parents are 14ae080 and fe764ff.
- Conflict list matches presence-2 items 1 to 4. `jwt` was dropped, `baseURL` dropped, `CHARGE_RATE_RESEND_AFTER` kept, and `setChargeRate` uses `slot.verifyCert` with timeout=10.
- Port commit subject is correct.
- Focused run: 265 passed across the 6 touched test files.

### Strengths
- The merge resolution is minimal and faithful. The remerge-diff shows only the expected hunks, and the wake loop takes fe764ff's structure plus presence's vin/vins skips and its own gate.
- `vehicleOnlineStates` now handles 401/403/410/412 through `slotRequestFailed`, as `loadVehicleList` does. A dead token found by a presence probe clears or pauses the slot instead of being retried quietly.
- The Owner-only token case (`readOnly`, no remote restore) is now a first-class scenario parameter, and `World` asserts `readOnly` against it.
- The implementer ran a mutation on `hasRemoteChannel` and caught that the old teslable test passed for the wrong reason.

### Issues

**Critical:** none.

**Important:** none.

**Minor**
1. **The TeslaAPI policy-wide away-skip (`TeslaAPI.py:1204`) is guarded by no test on this branch.**
   - Disabling it passes all 3 TestDeployRegression tests and `test_teslable_presence.py::test_policy_wide_apply_skips_departing_on_every_channel`.
   - The teslable test stays vacuous for TeslaAPI because the fresh `CarApiVehicle.ready()` is False, so it records "vehicle not ready; nothing sent" before reaching the skip.
   - Adding `car.ready = lambda: True; car.update_charge = Mock(return_value=True); car.chargeLimit = 80` makes it discriminating: it passes unmutated and fails with the skip removed (verified).
   - The commit message's claim ("so TeslaAPI's skip is exercised") is therefore inaccurate. Fix the test, or the claim, in the whole-branch pass.
   - Behaviour is correct today. Only the guard is missing.
2. **No test pins the Fleet wake of a presumed car with no fix end to end.** The coverage is split between a FakeVehicle with atHome=True and lat=10000, and `TestAtHomeFollowsPresence`. The probe in scratchpad/probe13 (a real `CarApiVehicle` and tracker, lat=10000, `wakeVehicle` called) would be a cheap regression test for the user's explicit requirement.
3. **Wording.** Two documents say the wake gate "no longer exempts a car with no location fix" and "a car presence hasn't marked home is not woken":
   - the merge report's watch item (`.superpowers/deploy-presence-3-merge-report.md:158-161`);
   - the implementer report.

   That reads as if a presumed car is not woken. It is woken. Only DEPARTING or NOT_HOME cars are skipped, and the location fallback applies only if `vehiclePresence` is missing or raises. Reword it so the person watching the box doesn't chase a non-issue.
4. **(Pre-existing, FYI.)** If `presence.isHome` raises, `atHome` falls back to `_locationAtHome`, which is False before any fix (`TeslaAPI.py:2294-2297`). In that failure mode a no-fix car is not woken. This comes from presence/4, not this task.
5. **(Pre-existing, FYI.)** `car_api_charge` (`TeslaAPI.py:922`) and `wakeVehicle` (`:2138`) POST without a timeout. This is token-slots code, already listed in the box watch items.

### Assessment
**Task quality:** Approved

**Reasoning:**
- The highest-risk item, the wake gate, was verified. `atHome` is driven by presence, PRESUMED counts as home, and a real CarApiVehicle with no fix is woken through the Fleet wake loop.
- The auth paths use the right slot per purpose, with 401/403/410/412 handling and the 30 s refresh timeout. No token reaches a log.
- Presence targeting and the scenario assertions are intact.
- The remaining items are test-strength gaps and a wording fix for the whole-branch review. None affects runtime behaviour on the box.
