# Task 13 report: TeslaBLE pairing status, proof, refusal, registry claims

Status: DONE
Commit: c938b36 (branch vehicle-model/phase1, on a0e24f4)
Tests: tests/unit 1024 passed, 1 warning (same warning on baseline a0e24f4, 1007 passed). The 7 brief tests were added verbatim and failed first (AttributeError: bleStatus); 10 more were added.

## What changed (lib/TWCManager/Vehicle/TeslaBLE.py)
- `KEY_REFUSED_TEXT` (tesla-control ErrKeyNotPaired text). `self.registry = VehicleRegistry.forMaster(master)` is set first thing in `__init__`; the read-source registration reuses it.
- `bleStatus(vin)` returns a fresh `{"status", "since"}` dict, read under settingsLock. The default is `{"status": "unpaired", "since": None}`.
- `_setBleStatus(vin, status)`: ignores a non-string or empty vin. Under settingsLock it writes `settings["Vehicles"][vin]["ble"]`, creating the `{chargeSessions, startkWh, totalkWh}` record if absent, and queues saveSettings. After the lock is released: for `paired` it calls getOrCreate (ValueError is guarded) and then `claim("TeslaBLE", True, "paired")`; for any other status it calls `registry.get(vin)` and drops the TeslaBLE claim if the vehicle exists.
- `_noteBleProof`: does nothing when the status is already paired. Otherwise it logs INFO "BLE key for <vin> accepted" and sets the status to paired.
- `_noteBleRefusal`: matches the refusal text without regard to case. It writes only when the status is not already `refused`, so the retries record one write and one save. Returns bool.
- `peerWithVehicle`: one `success` flag. The `finally` block writes `pairing` or `pairing_failed`, which covers all exits including exceptions.
- `_sendCommand_internal`: proof is noted on the success path and on the already-satisfied path. Refusal is checked when the return code is non-zero.
- `_fetch_state_json`: successful JSON parse → proof. On the `stdout is None or rc != 0` branch, a refusal check runs on the stderr text (decoded defensively). It does not run on JSON parse errors.
- `updateSettings()` → `scanForVehicles()` and then `_claimKeyedVehicles()`. This takes a snapshot of the `(vin, ble status)` pairs for keyed dict entries under settingsLock, releases the lock, then for each one calls getOrCreate (ValueError is skipped). Status `paired` gives a managed claim, `refused`/`pairing_failed` gives no claim, and anything else gives `claim("TeslaBLE", False, "unproven")`. Seeding writes nothing. Entries without privKey are not seeded.
- Every note call is wrapped in `_safeNote`, which catches exceptions and logs only the type name at DEBUG. If the bookkeeping fails, the command's result is unchanged.
- Carried from Task 2: the three all-vehicles loops (car_api_charge, setChargeRate, applyChargeLimit) now iterate `list(settings["Vehicles"].keys())`.

## Lock order
settingsLock is taken under `_bleLock` (the documented order, TWCMaster.py:116) and released before any registry or vehicle lock is taken. No lock is held across a tesla-control call. Nothing takes settingsLock and then `_bleLock`: `loadSettings` calls `updateSettings` outside the lock, and `updateSettings` never takes `_bleLock`. The read cascade (Vehicle.read → cascade) holds no lock while it calls a source's `fetch`. The new log lines contain only the VIN.

## Tests added beyond the brief
- A refusal is recorded once across the retry cycle (3 attempts, 1 saveSettings).
- A non-refusal failure leaves `paired` and the managed claim in place.
- A refused state read drops the claim.
- An already-satisfied reply counts as proof.
- A pairing exception gives `pairing_failed`.
- A None vin is not written. A non-ASCII vin is refused by the registry without raising.
- A bad registry key is skipped during seeding.
- The status default is correct and `bleStatus` returns a copy.
- A record is created for an unknown VIN.
- End to end: a seeded unproven claim → `Vehicle.read("batteryLevel", maxAge=0)` is answered by TeslaBLE, and the key becomes paired.

## Concerns (per brief; flagged for planner / Task 17)
1. Pairing window vs refusal. `pairing` drops the claim in the running session, so BLE reads pause. Background commands still go out through the `settings["Vehicles"]` loops. If the user has not yet tapped the key card, such a command gets ErrKeyNotPaired, and a fresh "Pairing" flips to "Key refused" before the user finishes. The restart path also seeds a `pairing` entry as unproven, while the live path holds no claim. The two are inconsistent, but this follows the brief. Alternative: make `pairing` an unproven claim, not a drop.
2. Re-pairing a car that is already paired: any `peerWithVehicle` failure writes `pairing_failed` and drops a working claim. That includes a missing binary or a car out of range.
3. `_setBleStatus` creates a `settings["Vehicles"][vin]` record for any non-empty string, including a junk value from the HTTP `/vehicle/localMgmt` form. `scanForVehicles` will then mint a keypair for it. Only None or empty is guarded. The test `test_pairing_with_bad_vin_does_not_raise_or_write` does write a settings record for the non-ASCII VIN, so its name overstates what it checks. The asserts themselves are correct.
4. `sendCommand` still runs the full maxRetries+1 backoff cycle on a refusal. Status is written once, but the caller still waits through the delay. Retries are not short-circuited.
5. `test_teslable_lock.py` uses a `Mock()` master whose settingsLock cannot act as a context manager, so status writes there no-op silently through `_safeNote`. I left that file alone: it was black-dirty at baseline, and a production master always has the RLock.

## Concerns fixed (commit d62e3b1, on c938b36)
I wrote the tests first. 9 new or changed tests failed before the fix. Unit suite: 1033 passed, 1 warning (the same warning as baseline).

1. **Pairing is an unproven claim.** `_setBleStatus(vin, "pairing")` now calls getOrCreate and `claim("TeslaBLE", False, "unproven")`, the same as the restart seed, so BLE is still tried. A successful pairing request stores `ble.pairingSent` (epoch). For `PAIRING_WINDOW = 600` s after that, `_noteBleRefusal` recognises a refusal (returns True and stops retries) but leaves the status and claim unchanged, with a DEBUG log only. After the window, a refusal sets `refused` and drops the claim. Proof inside the window moves the status to `paired`. `pairingSent` is a new optional key inside the new `ble` record. `since` is kept when the status does not change.
2. **A failed re-pair keeps Paired.** `peerWithVehicle` now reports through `_notePairingResult(vin, ok, reason)`. When the car is `paired`, a failure (timeout or out of range, tesla-control missing, public-key prep failure, the car rejecting the request, an exception) leaves the status and claim alone. A successful re-pair keeps `paired` and opens the window. Either outcome is recorded in a transient per-run `blePairingAttempt(vin) -> {"ok", "at", "message"} | None`. For example, the message is "Pairing request timed out; is the car in range?" or "tesla-control is not available". Task 17 can show it. When the car is not `paired`, a failure still sets `pairing_failed`. Only a key refusal after the window changes a paired car's status.
3. **Only well-formed VINs are accepted.** `peerWithVehicle` returns False before any I/O or write when the VIN fails `Registry.VIN.isWellFormedVIN`, so the `/vehicle/localMgmt` form goes through this check. `_setBleStatus` returns early for such VINs too. No settings record is created, so `scanForVehicles` makes no keypair, nothing is saved and nothing is added to the registry. The test is renamed `test_malformed_vin_is_rejected_without_writing` and asserts these points for None, "", "not-a-vin", a non-ASCII value and a value containing I.
4. **A key refusal is not retried.** `_sendCommand_internal` sets a thread-local `_keyRefusal.refused` when it sees ErrKeyNotPaired. `_execute_with_retry` clears the flag before each attempt and returns None at once when it is set. It does not record a circuit-breaker failure. Other failures are still retried (covered by a test).
5. **The lock tests now exercise status writes.** The `test_teslable_lock.py` fixture gives the master a real `threading.RLock()` settingsLock. The three overlap tests assert that the status ends `paired`, and the pairing test asserts that `blePairingAttempt` is ok. The status writes run under `_bleLock` without deadlocking. Only new hunks were added; the rest of the file was not reformatted.

Remaining notes:
- A status that stays `pairing` after the window does not expire on its own. The next BLE read or command (the claim keeps them coming) either proves the key or refuses it, and that resolves the status.
- `blePairingAttempt` lives in memory only and is lost on restart.

## Fix round 1 (commit after d62e3b1)
I wrote the tests first: 7 new tests failed before the fix. Two more passed already and now guard behaviour that must not change: the upgrade boot runs the real scanForVehicles and seeds the car, and a later boot claims held and paired VINs. Unit suite: 1042 passed, 1 warning (the same warning as baseline).

1. **Unproven claims no longer keep a car alive.** `Claim`/`Vehicle.claim` gain `keepsAlive=True`. `VehicleRegistry.expire()` now skips a vehicle only if one of its claims has `keepsAlive` set. TeslaBLE's unproven claims (seeded, or from a pairing in progress) use `keepsAlive=False`; paired claims and other providers' claims keep the default. The registry test `test_claim_that_does_not_keep_alive_does_not_block_expiry` covers this.
   **Seeding scope.** `_claimKeyedVehicles` treats a boot with no valid `settings["vehicleRegistry"]` blob (no dict with a `vehicles` dict) as the upgrade boot, and seeds every keyed, well-formed entry. On later boots: `paired` → getOrCreate and a managed claim; any other non-refused status → an unproven claim, but only if `registry.get(vin)` already holds the car; `refused` → no claim. On the upgrade boot, a refused entry is still created (the brief's test), but it gets no claim and expires normally.
   Tests: an unproven-only car ages out while a paired one stays; a later boot does not re-create an expired car; a later boot claims held and paired cars and not refused ones; the upgrade boot with the real scan seeds every entry.
2. **Malformed VINs are skipped.** `_claimKeyedVehicles` skips any VIN that fails `isWellFormedVIN` (test `test_seed_skips_malformed_vins`).
3. **VIN case.** A new `_settingsKey(vin)` returns the existing `settings["Vehicles"]` key, matched without regard to case. It returns an upper-case key for a VIN that isn't stored yet. It is used in `peerWithVehicle` (after the well-formed check), `_sendCommand_internal`, `_fetch_state_json`, `bleStatus`, `_setBleStatus` and `_inPairingWindow`. `blePairingAttempt` is keyed by the upper-case VIN. A lowercase form VIN now updates the stored upper-case record and shows its real status. A legacy lowercase record is found by the upper-case VIN, both for reads and for status, without creating a duplicate record.
4. **`pairing_failed` leaves claims as they were.** An unproven claim stays, so BLE is still tried. A refused car still has no claim. On restart, the car is re-claimed as unproven if the registry still holds it (test `test_pairing_failure_keeps_an_unproven_claim`).
5. **Renamed test.** It is now `test_update_settings_ignores_hand_edited_entries_without_a_key`, with a comment saying `scanForVehicles` is mocked. The companion test `test_upgrade_boot_real_scan_keys_and_seeds_every_entry` runs the real scan.

Not addressed (reviewer Minor 4, not ruled in): a key refusal still returns before `circuit_breaker.record_failure`.
