# Final fix wave re-review 1 (2d872e4..8e07669)

The checkout `scratchpad/wt-vm` is at 8e07669 and its tree is clean. I read the fix diff once and checked callers in the final files. The focused tests were run under the memory cap: `test_registry_vehicle`, `test_telemetry_registry`, `test_teslable_pairing_status`, `test_vehicle_detail_page`, `test_vehicles_page`, `test_twcmaster_vin_confirmation`, `test_registry_membership`, `test_registry_callers`, `test_own_write_stamps` and `test_carapivehicle_registry`. All 255 passed.

## Per-finding verdicts

### C1: ADDRESSED
- **Mechanism.** `Vehicle._liveAt` (Vehicle.py:98-115) now lets any source that has reported the field vouch for it while that source's `sourceLiveAt` is finite. The value no longer has to match.
  - The reviewer's case: TeslaMate reported `lat`, then a cloud read observed a slightly different `lat`, then the feed came back healthy. `liveAt` is now "now", so age is 0 and `read()` returns without a cascade.
  - `test_feed_outage_costs_one_cloud_read_not_one_per_window` is the probe as a test: real registry, both differing and identical digits, six reads 301 s apart. It asserts exactly one paid call.
  - `test_feed_outage_then_recovery_pays_one_cloud_read` covers the same path end to end: real TeslaMate feed, `CarApiVehicle.update_location(0)`, then an MQTT disconnect and reconnect.
- **Stale value once the feed is unhealthy.** `feedLiveAt` (Telemetry.py:169-174) returns None when the feed is disconnected or the car is unhealthy. `_liveAt` skips None, so the cloud observation ages from its own stamp. Both rewritten tests now assert this: `reg.live=False` gives age 4100, and `mqttDisconnect` makes the next `update_location(0)` call the API.
- **Freshness rule.** Age is still `now - max(obs.at, liveAt)`; `Fields.age` and `trusted` are untouched.
- **FEED_LAG after our own write.** `read()` still requires `trusted()`. An observation that is not newer than our write is trusted only after `now - write.at > FEED_LAG` with a live vouch. `test_feed_vouch_resolves_own_write_after_feed_lag` and the second FEED_LAG test pass unchanged.
  - Behaviour change: after FEED_LAG, a live feed now also vouches for a pre-write *differing* polled value. This is consistent with the ruling.
- **The two rewritten tests.**
  - `test_feed_does_not_vouch_for_a_different_value` asserted the exact rule the ruling removed (a different value is not vouched for). Inverting it is correct.
  - The `car.lat = 38.0` tail of `test_feed_vouches_for_a_value_the_api_reobserved` likewise asserted the removed rule.
  - The one real guard inside them was that an unvouched value ages and gets re-fetched. Both rewrites keep it, now triggered by the feed going down, which is the only remaining way to lose the vouch.
  - Nothing of value was lost. `latest()` and `value()` still return the newer polled value, so the vouch only suppresses a re-fetch; it never hides a newer reading.

### I1: ADDRESSED
The new code is `HTTPControl.py:91-130` (`_vehicleRecordKey`, `canForgetVehicle`, `forgetVehicle`), the POST route at :1659-1665 and the template form in `vehicleDetail.html.j2:26-31`.
- **Input validation.** The VIN is stripped and upper-cased, then checked with `isWellFormedVIN` before any registry or settings access. The Location header is built only from a validated VIN, and the test covers `\r\n` injection. A malformed VIN redirects to `/vehicles`.
- **Paired or attached cars.**
  - `canForgetVehicle` requires `userAsserted`, no attachments (`attachmentNames()` under the vehicle lock) and a stored BLE status that is not `paired`. The POST handler re-checks.
  - The record and key are deleted only if the record carries `addedByVIN` and has no `chargeSessions` or `totalkWh`.
  - A car a TWC confirmed always has `chargeSessions >= 1` (TWCMaster.py:1521-1531), so its record and key survive even if a user-asserted registry entry is forgotten.
- **HTML injection.** Jinja autoescape is on, and the hidden input's `vin` is escaped.
- Residual nits are listed below (minor, not blocking).

### I2: ADDRESSED
`TeslaBLE._allVehicleTargets` (TeslaBLE.py:1983-1998) is used by all three loops (:308, :641, :673).
- **Who is commanded.** It keeps every record that has a `privKey` and is not stored as `refused`.
  - Upgrade users' unproven seeds have no stored status, so they are still commanded.
  - So are `pairing` and `pairing_failed`.
  - `test_unproven_and_pairing_keys_are_still_commanded` asserts that all three receive commands.
- **Who is skipped.** Refused keys and keyless VINs (history-only, or pairing that failed before a key existed) are skipped. Tests cover all three loops.
- **Where the keys live.** I confirmed that keys are stored in `settings["Vehicles"][vin]["privKey"]` (TeslaBLE.py:958-969, :1570-1580), so the `privKey` filter does not skip real keyed cars.
- **Removed code.** The `total_vehicles` local is removed only where it was unused; the `setChargeRate` summary still has it (:720/:755).
- Lock order `_bleLock -> settingsLock` holds.
- **Residual (as the implementer flagged).** An Add-by-VIN typo has a key and no status, so it is still commanded until it is forgotten. This is accepted: I1 is the remedy, and the ruling forbids skipping unstatused keys.

### I3: ADDRESSED
`FleetTelemetryMQTT.vinFor` returns None unless the id is a str and `isWellFormedVIN`. The test shows that a `status` topic creates nothing. TeslaMate rows also go through `getOrCreate`, now gated by I4.

### I4: ADDRESSED (raise; every production caller handles it)
`_getOrCreate` (VehicleRegistry.py:75) raises `ValueError` unless the VIN is well-formed. Production callers:
- `Telemetry.py:338-343` (MQTT callback thread): wrapped in `except ValueError`.
- `TeslaAPI.CarApiVehicle.__init__` (:2077): its only constructor, `addVehicle` (:190-197), catches the error. The `vehicle` property (:2105) re-uses a VIN that already passed construction.
- `TeslaBLE.py:1903` (`_setBleStatus`; also gated at :1873) and `:2013/:2018` (`_claimKeyedVehicles`; also gated at :2005): both inside `try/except ValueError`.
- `HomeAssistant.py:404`: `except ValueError` logs and skips.
- `addUserAsserted`: validates first and raises, and its HTTP caller catches the error and redirects with the message.
- `observeTwcVin` (serial thread): validates first and returns "rejected" without raising. Its caller `recordVehicleVIN` also wraps it in `except Exception`.
- `load()` checks first and skips malformed keys, inside the tolerant per-entry try.

There is no new crash path on the serial thread, the MQTT callbacks or the HTTP handlers.

### M1: ADDRESSED
The comment at TWCMaster.py:117-118 now says so.

### M2: ADDRESSED
- The insert is done under `backgroundTasksLock`. The pop is done under the lock, and due tasks are queued after it is released, so the non-reentrant lock is not re-taken.
- I checked every other holder (`setLimitAmpsToDivideAmongSlaves`, `setMaxAmpsToDivideAmongSlaves`, the immediate path in `queue_background_task`). None calls `queue_background_task(delay>0)` while holding the lock, so there is no deadlock.

### M3: ADDRESSED
`_bluezAddresses` returns None on a non-zero exit, so the result is "range unknown". The test covers it.

### M4: ADDRESSED
`HomeAssistant.setChargeRate` stamps `availableCurrent` on success using `registry.get`, so it never creates a vehicle. Tests cover both the success and failure paths.

### M5: ADDRESSED
Unset now uses `pop(..., None)`.

### M6: ADDRESSED
`deleteSlaveTWC` calls `endPlugSession` with the same `%02X%02X` id and the same guard as `_plugSession`. This is dict-only work, so it is safe on the serial thread.

### M7: ADDRESSED
`_setBleStatus` returns before creating a record on `pairing_failed` when no record exists. This is broader than the brief, but it is equivalent in practice: `sendPublicKey` only reads settings, so key preparation always fails for a VIN with no record. A known car still records the failure (tested).

### M9: ADDRESSED
`isWellFormedVIN` rejects `"0"*17`. This gates the registry, `_claimKeyedVehicles`, `observeTwcVin`, `vinFor` and the HTTP handlers.

## New breakage in the fix diff

No Critical or Important issues. Minor items:

1. **Minor, HTTPControl.py:109 and vehicleDetail.html.j2:29.** `addUserAsserted` sets `userAsserted=True` on an *existing* vehicle, for example one a TWC confirmed or one fed only by TeslaMate or Fleet Telemetry. Such a vehicle shows Forget, although the hint says "not seen by any provider".
   - Forgetting it removes only the registry entry. Its record and key are kept because they have charge history or lack `addedByVIN`, except for a telemetry-only car added by VIN with no sessions.
   - In every case the next sighting re-creates the vehicle.
   - The implementer's report says the tests refuse a "TWC-seen car", but the test only covers a car that is not user-asserted. A user-asserted car later confirmed by a TWC is still forgettable.
   - Harmless and self-healing; the wording is inaccurate.
2. **Minor, HTTPControl.py:121-136.** Check-then-act: `forgetVehicle` re-checks `addedByVIN` and history under the second `settingsLock`, but not `ble.status == "paired"`. A pairing proof that lands between the two lock sections could see a just-paired key deleted. The window is microseconds and needs a concurrent user Forget click; the implementer noted a similar attach race.
3. **Minor, TeslaBLE.py:1983-1998.** `_allVehicleTargets` does not apply `isWellFormedVIN`. An old all-zero placeholder record that holds a `privKey` is still sent all-vehicle commands. This is the same as main and outside M9's stated scope, but it is the same phantom-cost class as I2.

## Out-of-scope observations

- `sendPrivateKey` (TeslaBLE.py:1566-1580) indexes `settings["Vehicles"][vin]` without the lock. A concurrent Forget turns this into a caught `KeyError`, so there is no crash; this is pre-existing.
- C1 trade-off, as the implementer stated: a value that a polled source saw and that differs from the feed's last report is treated as current for as long as the feed stays healthy. This is the ruled behaviour.

## Verdict

**Verdict: All in-scope findings ADDRESSED (C1, I1-I4, M1-M7, M9); no new Critical or Important issues; ready to merge with three minor notes.**
