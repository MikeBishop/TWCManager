# Task 13 re-review, fix round 1 (d62e3b1..b113e90)

Focused tests (`test_teslable_pairing_status`, `test_teslable_lock`, `test_registry_membership`): 71 passed at b113e90. All 10 new tests are present.

### Finding Verdicts

- **Minor 1 (unproven claims never expire): Fixed.**
  - `Claim.keepsAlive` is added (Vehicle.py:21-29, :161-163). `expire()` now skips a vehicle only if one of its claims has `keepsAlive` set (VehicleRegistry.py:139-142).
  - TeslaBLE sets `keepsAlive=False` only through `_claimUnproven` (TeslaBLE.py:1633-1636). Paired claims keep the default True.
  - Seeding scope: when the registry blob is missing or invalid, every keyed, well-formed VIN is seeded. On later boots a paired car is getOrCreate'd and claimed; an unproven car is claimed only if `registry.get` already holds it (:1694-1724).
  - Tests: `test_unproven_only_car_ages_out_but_paired_does_not`, `test_later_boot_does_not_recreate_expired_or_forgotten_car`, `test_later_boot_claims_held_and_paired_vins`.
- **Minor 2 (seed skips malformed VINs): Fixed.** `isWellFormedVIN` filter at :1704-1705; test `test_seed_skips_malformed_vins`.
- **Minor 3 (VIN case): Fixed.**
  - `_settingsKey` (:1553-1569) returns the existing key, matched without regard to case, or an upper-case key for a new VIN.
  - It is applied in `peerWithVehicle`, `_sendCommand_internal`, `_fetch_state_json`, `bleStatus`, `_setBleStatus` and `_inPairingWindow`. `_pairingAttempts` is keyed by the upper-case VIN.
  - The registry side normalises in `get`/`getOrCreate` (VehicleRegistry.py:81, :98), so lower-case calls resolve to the same Vehicle.
  - Tests: `test_lowercase_form_vin_uses_the_stored_record`, `test_legacy_lowercase_record_is_found_by_upper_vin`.
- **Minor 4 (circuit breaker on refusal):** deferred by ruling. It is not a blocker.
- **Minor 5 (`pairing_failed` drops an unproven claim): Fixed.**
  - `_setBleStatus` now drops the claim only for `refused` (:1626-1631). `pairing_failed` leaves any claim alone.
  - On restart a held car with `pairing_failed` is re-claimed as unproven (:1722-1724).
  - Test: `test_pairing_failure_keeps_an_unproven_claim`.
- **Minor 6 (misleading test name): Fixed.** The test is renamed `test_update_settings_ignores_hand_edited_entries_without_a_key`, and the companion `test_upgrade_boot_real_scan_keys_and_seeds_every_entry` runs the real `scanForVehicles`.

**Coordinator checks:**
- **(a) Other claims still keep cars alive: Verified.** `keepsAlive` defaults to True in both `Claim.__init__` and `Vehicle.claim`. The only other `claim()` callers are TeslaAPI.py:2083 (the "listed" claim) and HomeAssistant.py:411. Neither passes `keepsAlive`, so both keep cars alive as before. The TWC path makes no claims; it relies on `lastSeen`. Nothing constructs `Claim(...)` directly outside Vehicle.py. The other readers of `.claims` (`tier`, `summary`, `TeslaBLEReadSource.canRead`) don't look at `keepsAlive`.
- **(b) Upgrade-boot misfire: acceptable.** `saveSettings` always writes `settings["vehicleRegistry"] = registry.toJSON()`, which is `{"version": 1, "vehicles": {...}}` even when the registry is empty (TWCMaster.py:1647; VehicleRegistry.py:282-296). After the first save on this release, a normal boot always finds a valid blob. A misfire needs the blob to be hand-deleted or corrupted. In that case `registry.load` has already discarded it, so the registry is rebuilt from nothing and re-seeding is the right recovery. The seeded claims have `keepsAlive=False`, so cars that are not seen age out after `forgetAfterDays`. Worst case: a forgotten guest car comes back for one forget window. Acceptable.
- **(c) Upper-casing vs records keyed lower-case on main: no breakage.** `_settingsKey` returns an existing key exactly as stored. A legacy lower-case record is reused, never duplicated or renamed. The settings-keyed loops (`car_api_charge`/`setChargeRate`/`applyChargeLimit`) pass stored keys, which `_settingsKey` returns unchanged. `vehicleDetail.html.j2`/`vehicles.html.j2` index `settings["Vehicles"]` by the URL or iterated key. The `/vehicle/localMgmt` form posts the VIN from that page, which is the stored key, so its redirect (HTTPControl.py:1508) points at a key that exists. The only change from d62e3b1 is for a hand-typed VIN whose case differs from the stored key. That case now updates the stored record instead of creating a second one in different case, and main behaved the same way.

### New Breakage

None found. Lock order is unchanged: `_settingsKey` takes `settingsLock`, which is an RLock, and releases it before `_setBleStatus` takes it again. Its callers run either under `_bleLock` or with no lock held.

Minor, no action needed: a keyed, never-proven car that expires and later reappears at a TWC is re-created by the TWC observation, but its unproven BLE claim comes back only on the next boot. Until then BLE reads skip it. BLE commands still reach it through the settings-keyed loops, and the first success re-claims it as paired, so it recovers on its own.

### Out-of-Scope

- Minor 4 (refusal never trips the circuit breaker) remains, deferred by ruling.
- `vehicleDetail.html.j2:98-106` still reads the old `BLEPeeringStatus`; Task 17 replaces it, as planned.

### Verdict

**Approved.** Minors 1, 2, 3, 5 and 6 are fixed as ruled and covered by tests. Checks (a), (b) and (c) hold, and nothing new is broken.
