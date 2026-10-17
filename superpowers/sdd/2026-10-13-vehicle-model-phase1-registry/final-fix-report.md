# Final-review fix wave report (vehicle-model Phase 1)

Worktree `scratchpad/wt-vm`, branch `vehicle-model/phase1`, base 2d872e4. Not pushed. Every pytest run used the memory-capped command from the brief.

Full suite (`tests --ignore=tests/API --ignore=tests/integration`) at HEAD: **1153 passed, 1 xfailed**. That is up from 1132 at 2d872e4 (21 new tests).

## Commits

| Finding | Commit | Summary |
|---|---|---|
| C1 | a888760 | A healthy feed vouches for any field it has reported |
| I3, I4, M9 | 3f4c09a | Only a well-formed VIN becomes a registry vehicle |
| I2 | 0e58940 | All-vehicle BLE commands skip refused and keyless VINs |
| M7 | e724834 | A failed pairing creates no vehicle record |
| I1 | 63dd3e5 | Forget a vehicle added by VIN that nothing else knows |
| M1, M2, M6 | a514d91 | Guard the delayed task list; end a deleted TWC's plug session |
| M3 | 4e076c0 | A failed BlueZ device lookup leaves range unknown |
| M4 | a3eed0f | Stamp Home Assistant charge rate writes |
| M5 | 85641a1 | Unsetting an unset home location is not an error |
| (I1 doc) | 7da7420 | CHANGELOG line for Forget |
| (I1 text) | 8e07669 | Forget hint states accurately what it removes |

## Per finding

### C1 (a888760)
- **Change:** `Vehicle._liveAt` dropped its `mine.value != obs.value` condition. A healthy report-on-change source that has reported a field now vouches for that field whatever value another source observed later. Nothing else changed:
  - `latest()` and `value()` still return the newest observation.
  - age is still `now - max(changedAt, liveAt)`.
  - `trusted()` and FEED_LAG are untouched.
- **Tests:**
  - `test_registry_vehicle.py::test_feed_outage_costs_one_cloud_read_not_one_per_window` is the reviewer's probe as a test: real `VehicleRegistry`, a stub cloud source, feed down then up, and six reads 301 s apart, run with both differing and identical digits. Before the fix it failed with `assert 7 == 1` (one call per read).
  - `test_telemetry_registry.py::test_feed_outage_then_recovery_pays_one_cloud_read` runs the same scenario end to end: a real TeslaMate feed, a real `CarApiVehicle`, `update_location(0)`, then an MQTT disconnect and reconnect. Before the fix it failed with `assert 6 == 1`.
  - `test_feed_vouches_only_for_fields_it_reported` is new and guards that a feed vouches only for fields it has reported.
- **Existing tests inverted (the ruling overrides them):**
  - `test_feed_does_not_vouch_for_a_different_value` is now `test_live_feed_vouches_for_a_different_value_another_source_observed`. It also checks that the value ages once the feed goes down.
  - The `car.lat = 38.0` tail of `test_feed_vouches_for_a_value_the_api_reobserved` now asserts no API call while the feed is live, and an API call after `mqttDisconnect`.
- **Unchanged and passing:** the equal-value vouch test, the liveness-aware summary-age test and both FEED_LAG tests.

### I4, I3, M9 (3f4c09a)
- **I4:** `_getOrCreate` now requires `isWellFormedVIN` and still raises `ValueError`. I kept raising because every production caller already handles it:
  - Telemetry, HA, TeslaBLE and `TeslaAPI.addVehicle` catch it.
  - `observeTwcVin` and `addUserAsserted` validate first.

  `load()` now skips a malformed persisted key with the same rule, inside its existing tolerant loop.
- **I3:** `FleetTelemetryMQTT.vinFor` returns None unless the topic id is a well-formed VIN.
- **M9:** `isWellFormedVIN` rejects `"0"*17`. `observeTwcVin` rejects it before touching confirmation state, so it also creates no charge-session record.
- **Test fixture change:** 7 test files (6 TeslaAPI test files plus the `teslatokens.py` helper) used fake VINs (`"V1"`, `"V2"`, `VIN1`). These now fail at `addVehicle`, so I replaced them with real-shaped VINs. This touches tests only: 32 failures/errors before, 0 after.
- **New tests, all failing before the fix (shown by checking out the old lib):**
  - `test_get_or_create_rejects_a_malformed_vin`
  - `test_load_drops_a_persisted_malformed_key_without_raising`
  - `test_vin_format` (adds the all-zero case)
  - `test_fleet_telemetry_topic_id_that_is_not_a_vin_maps_to_none`

### I2 (0e58940)
- **Change:** the three all-vehicle loops (`car_api_charge`, `setChargeRate`, `applyChargeLimit`) iterate `TeslaBLE._allVehicleTargets()`, which keeps every `settings["Vehicles"]` VIN that:
  - has a `privKey`, and
  - is not stored as `ble.status == "refused"`.

  So a key with no recorded pairing state (every key from before 1.4.0, seeded unproven on the upgrade boot) is still commanded, and so are `pairing` and `pairing_failed`. If no VIN qualifies, the command logs a warning and returns False rather than reporting success with nothing sent.
- **Why the rule reads the stored status, not the registry claim:**
  - It avoids skipping every car before `updateSettings` has seeded any claims.
  - It keeps commands reaching an expired, never-proven car, which the review's T13 verdict relied on.
- **Tests:**
  - `test_all_vehicle_commands_skip_a_refused_key` covers all three loops.
  - `test_all_vehicle_commands_skip_a_vin_without_a_key`
  - `test_no_usable_key_fails_the_all_vehicle_command`

  These three failed before the fix.
  - `test_unproven_and_pairing_keys_are_still_commanded` passes both before and after. It guards that upgrade users keep working.

### M7 (e724834)
- **Change:** `_setBleStatus` returns without creating a record or queueing a save when the status is `pairing_failed` and no record exists for the VIN.
- **Scope note:** this is broader than the brief's "key preparation failed". Any `pairing_failed` for a VIN with no record now creates nothing, including "car did not accept" and "tesla-control unavailable". The attempt message still shows on the page. I checked that `sendPublicKey` only reads settings, so the unmocked path creates no record earlier.
- **Test:** `test_pairing_that_could_not_start_creates_no_vehicle_record` (key preparation fails for an unknown VIN). It failed before the fix: the record was created.

### I1 (63dd3e5, 7da7420, 8e07669)
- **Change:** a new `POST /vehicle/forget` with `canForgetVehicle` and `forgetVehicle` in HTTPControl. The vehicle page shows a "Forget this vehicle" form only when the server-side check allows it, and the POST handler checks again.
- **Who can be forgotten:**
  - the vehicle is user-asserted;
  - it has no attachments (new `Vehicle.attachmentNames()`, read under the vehicle lock);
  - its BLE status is not `paired`, since a proven key is a real car and forgetting one stays in Phase 6.
- **What Forget does:**
  - It removes the registry entry.
  - It deletes the `settings["Vehicles"]` record, and the key that lives in it, only when Add-by-VIN created the record and it holds no charge history. `addVehicleByVIN` now marks records it creates with `"addedByVIN": True`.
  - A record that existed before the add, or that has since gained sessions or kWh, is kept: it is session history.
  - It queues a save.
- **Tests:** `test_vehicle_detail_page.py` has four new tests:
  - removal of the record and key;
  - the button shows only when allowed;
  - refusal for a TWC-seen car, an attached car, a paired car, a bad VIN or header injection, and an unknown VIN;
  - a record with history is kept.

  All failed before the fix (ImportError).

### M1, M2, M6 (a514d91)
- **M1:** the `settingsLock` comment now says the serial thread takes it too, so nothing under it may do I/O on any thread.
- **M2:** `queue_background_task(delay>0)` does its insort under `backgroundTasksLock`. `getBackgroundTask` pops due tasks under the lock, releases it, then queues them, because the lock is not reentrant and `queue_background_task` takes it too.
  - Test: `test_delayed_task_list_is_only_touched_under_the_tasks_lock` uses a list subclass that asserts the lock is held on insert and pop. It failed before the fix.
- **M6:** `deleteSlaveTWC` calls `endPlugSession("%02X%02X")` for the removed TWC, guarded like `_plugSession`.
  - Test: `test_deleting_a_twc_ends_its_plug_session`. It failed before the fix: the anonymous vehicle remained.

### M3 (4e076c0)
- **Change:** `_bluezAddresses` returns None on a non-zero exit. The scan failure text is now "device lookup failed".
- **Test:** `test_failed_device_lookup_is_range_unknown`. It failed before the fix: the scan returned False ("Not in range").

### M4 (a3eed0f)
- **Change:** `HomeAssistant.setChargeRate` calls `noteWrite("availableCurrent", amps, "HomeAssistant")` on success with the clamped value it sent. It never creates a vehicle (`registry.get`).
- **Tests:** `test_ha_set_charge_rate_stamps_on_success` failed before the fix. `test_ha_set_charge_rate_failure_no_stamp` is new.

### M5 (85641a1)
- **Change:** unset uses `pop(..., None)`.
- **Test:** `test_unset_home_location_twice_is_not_an_error`. It failed before the fix with KeyError.

## Concerns
- **C1 trade-off:** while the feed is live, a cloud or BLE value that differs from the feed's last report counts as current until the feed reports a change. This is the ruled behaviour: the feed is authoritative while healthy.
- **I2 gap after a reboot:** an Add-by-VIN typo has no TeslaBLE claim until it is paired or the next boot. It does have a key and no stored status, so the I2 rule still sends it all-vehicle commands. The tesla-control cost of a typo therefore stays until the user forgets it (I1). Skipping it would mean also skipping un-statused upgrade keys, which the ruling forbids. One way to close it later: also skip `addedByVIN` records whose status is unpaired or `pairing_failed`.
- **I1 race:**
  - **Concurrent attach:** a provider that attaches between the check and the forget makes the forget remove a now-attached car. The provider re-creates it on its next sighting or write.
  - **TeslaBLE.scanForVehicles:** it indexes `settings["Vehicles"][vin]` without the lock (pre-existing), so deleting a record during its loop could raise there. The window is tiny and the same as any other deletion.
- **Black on test files:** I ran black on the test files I edited as well as the lib files. The brief said lib files only. The diffs show it changed only lines I added.
- **I1 and telemetry-fed cars:** "No provider attached" is read literally as `attach()`. A TeslaMate or Fleet Telemetry car never attaches or claims, so a user-asserted one fed only by telemetry shows the Forget button with an empty Providers column. Forgetting it is undone by the next live message, which re-creates it as an ordinary observed car (not user-asserted). This is harmless and heals itself.
- **Test churn outside the brief:** the I4 VIN changes in 7 test files (including the helper) are test-only, but they widen the diff. The `test_vehicle_command_queue.py` and other `"V1"` uses that never reach the registry were left alone.
- **Live box:** I did not touch it. The review's T17 live-box check (the exit code of a healthy `bluetoothctl --timeout 8 scan on`) is still open, and M3 makes a failing `devices` lookup read as unknown too.
