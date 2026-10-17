# Task 13 review: TeslaBLE pairing status, proof, refusal, registry claims (a0e24f4..d62e3b1)

### Spec Compliance

**Verdict: Compliant** with the brief as amended by the controller rulings. Every ruling is implemented and has a test.

- **The upgrade seed works, but the "no key → not seeded" ruling has no effect in production.** `updateSettings` (TeslaBLE.py:1528-1532) runs `scanForVehicles()` before `_claimKeyedVehicles()`, and `scanForVehicles` (:887-933) mints a key for every `settings["Vehicles"]` entry. So when the seed runs, every VIN ever seen at a TWC has a key and gets an unproven BLE claim. The ruling is met only because no unkeyed entries are left by then. `test_update_settings_ignores_entries_without_a_key` (tests/unit/test_teslable_pairing_status.py:101) passes only because it mocks `scanForVehicles`, so it describes a hand-edited-file case. This matches the brief's text and keeps main's behaviour of trying BLE for every known VIN, so it is not a defect. The planner should still know about it.
- **Risk (a), upgrade: OK.** Load order:
  1. `TWCMaster.__init__` creates `vehicleRegistry` (TWCMaster.py:118).
  2. `TeslaBLE.__init__` binds `self.registry` and registers the read source.
  3. `loadSettings` loads the settings, then `vehicleRegistry.load(blob)` (TWCMaster.py:1137-1145).
  4. `updateSettings` (TWCMaster.py:1181) runs scan and then seed.

  Claims are not persisted (`toJSON`, VehicleRegistry.py:282-296), so each start rebuilds them from settings. A box that paired on main has a key and no `ble` record, so it gets `claim("TeslaBLE", False, "unproven")`. That passes `TeslaBLEReadSource.canRead` (Sources.py:34-39), so BLE reads go first. Commands are unaffected because the `settings["Vehicles"]` loops are not gated on status. The first successful command or read moves the car to `paired`/managed. The end-to-end test `test_claimed_vin_reads_from_ble_first` (:220) covers this path.
- **Rulings:**
  - Pairing is an unproven claim (:1590-1600).
  - A refusal inside the 600 s window keeps "pairing" (`_noteBleRefusal`, :1637-1649).
  - A failed re-pair of a Paired car keeps Paired, and the transient attempt message goes to `blePairingAttempt` (`_notePairingResult`, :1608-1625).
  - Only well-formed VINs get a record, via guards at :433 and :1569.
  - ErrKeyNotPaired is not retried (:1165-1171).
  - Lock tests use a real RLock (test_teslable_lock.py:26-27).
  - The brief's `pairing`→drop and `pairing_failed`-on-any-failure rules are correctly superseded.

### Strengths

- **Lock order (b) is clean.** The status writes take `settingsLock` under `_bleLock`, then release it before any registry or vehicle lock (`_setBleStatus`, :1568-1604; `_claimKeyedVehicles` snapshots under the lock and claims outside it). This is the first time `settingsLock` is taken under `_bleLock`, so I scanned the reverse direction:
  - Every caller of `sendCommand`/`car_api_charge`/`setChargeRate`/`applyChargeLimit`/`wakeVehicle`/`get_charge_state` is reached from the vehicle command queue, the background task thread, or the read cascade. None of them is inside a `with settingsLock`.
  - The one nearby hit, MQTTControl.py:178-180, calls `applyPolicyImmediately()` after the `with` block, and that call only sets an Event (Policy.py:183-186).
  - The HTTP `/vehicle/localMgmt` handler (HTTPControl.py:1501-1505) calls `peerWithVehicle` with no lock held.
  - `saveSettings` takes `settingsLock` and then the registry (TWCMaster.py:1638-1647), which follows the documented order.
  - `_bleLock` is a plain Lock, and nothing reachable from the note helpers takes it again.
  - The lock tests now run real status writes under `_bleLock` (test_teslable_lock.py:102-135).
- **Refusal matching (c) fails safe.** It matches the `ErrKeyNotPaired` constant string from vehicle-command, ignoring case (:1564-1565). If tesla-control changes the wording, the refusal goes undetected and the key keeps being tried, as on main. It does not drop a working claim. The phrase is specific enough that a false positive is not realistic. The "already satisfied" check (:347-364) runs first, and the two cannot overlap.
- **Proof and refusal checks are atomic in practice.** `_noteBleProof` and `_noteBleRefusal` are only called from `@_serialized` methods, so their check-then-set runs under `_bleLock`.
- **Bookkeeping can't change a command's result.** `_safeNote` (:1543-1548) means a status-write failure never turns a successful command into a failure, and it logs only the exception type.
- **Logging (d) is clean.** The new log lines contain the VIN at most. No key, token or command output was added to logs. The existing `BLE command full error output` warning is unchanged.
- **`peerWithVehicle` records every exit.** It records its result from `finally` with one `success`/`reason` pair (:436-503), so timeout, missing binary, key preparation failure, rejection and exception all leave a status.
- **Refusals stop retries without touching other failures.** The thread-local `_keyRefusal` flag stops retries only for a refusal; `test_other_failures_are_still_retried` (:138) pins that. A refusal is written once per retry cycle.
- **Tests are broad.** There are 26 focused tests: brief tests verbatim, plus window, re-pair, malformed VIN, seed-order and end-to-end cascade cases. Focused run: 31 passed (pairing_status + lock). The BLE/registry subset: 278 passed.

### Issues

**Critical:** none.

**Important:** none.

**Minor:**

1. **Seeded unproven claims never expire** (TeslaBLE.py:1651-1680, VehicleRegistry.py:139). `expire()` skips any vehicle that holds a claim. Because every TWC-seen VIN has a key (see Spec Compliance), a guest car from years ago becomes a permanent registry vehicle. The only way out is a refusal, which a car that never comes back cannot produce. This follows the ruling, so it is for the planner, not a defect here. Options: expire unproven-only claims with `vehicle.forgetAfterDays`, or seed only VINs whose `ble` record isn't absent once Task 17 has a pairing UI.
2. **`_claimKeyedVehicles` does not check `isWellFormedVIN`** (:1670-1674). `getOrCreate` accepts any non-empty ASCII string. A junk key written by main's unvalidated `/vehicle/localMgmt` form, or by a hand edit, becomes a permanent claimed registry vehicle. `canRead` would then send BLE reads to it, and each one costs the command timeout. A one-line filter would match the "only well-formed VINs" ruling.
3. **VIN case is not normalised.** `isWellFormedVIN` accepts lowercase (VIN.py), and the registry upper-cases VINs (VehicleRegistry.py:81), but `settings["Vehicles"]` keys, `bleStatus` and `_fetch_state_json` (:978) do not. A lowercase VIN from the form gets a lowercase settings record and an uppercase registry vehicle. `canRead`→`get_charge_state(UPPER)` then misses the settings record and returns None without any error. Task 17 calling `bleStatus(vehicle.vin)` would show "unpaired". Suggest upper-casing in `peerWithVehicle`/`_setBleStatus`, or have Task 17 look up case-insensitively.
4. **A refused car never trips the circuit breaker** (:1167-1171). The short-circuit returns before `circuit_breaker.record_failure`. The settings-keyed command loops therefore try a refused car once every cycle with no limit, where main would eventually have opened the breaker. Each attempt is one tesla-control run, not a retry storm, so the cost is small. Consider recording one failure on refusal.
5. **`pairing_failed` drops an unproven claim** (:1622-1624, :1601-1604). An upgraded car whose key may still work loses its BLE-reads-first claim if the user tries to pair and the attempt times out because the car is out of range. On restart it is not re-seeded (:1676). It recovers on the next successful command, since the command loops are not gated. The ruling only protects Paired, so this is consistent with it. Flagging so the planner can decide whether a non-refusal failure should keep an existing unproven claim.
6. **Test name overstates.** As noted above, `test_update_settings_ignores_entries_without_a_key` (:101) passes only because it mocks `scanForVehicles`. Rename it to say it covers a hand-edited file, or add a companion test that runs the real `scanForVehicles` and asserts that the unkeyed entry gets a key and is seeded.

**Named risks (e) and (f):**
- **(e) Stale "pairing" after the window: acceptable.** The unproven claim keeps BLE reads and commands going, and the first one after the window turns the status into paired or refused. Suggest Task 17 show `since`, or "requested N minutes ago", so a stale Pairing is visible.
- **(f) `blePairingAttempt` in memory only: acceptable.** The persisted `ble.status` is the durable record. The attempt is correctly limited to a "last attempt this run" UI hint, and losing it on restart loses nothing a user relies on.

### Assessment

**Task quality:** Approved

**Reasoning:** The upgrade path is sound. A box paired on main keeps sending BLE commands, because the settings loops are not gated, and gets BLE reads first through the unproven seed, which runs after the registry load. Proof promotes the car to managed. Lock order holds in both directions: no settingsLock holder reaches `_bleLock`. Refusal detection fails safe, logs carry no secrets, and every controller ruling is implemented and tested. The remaining items are planner-level policy questions (claim expiry, unproven claims on pairing failure) and small hardening (VIN filter and case on seed, the breaker on refusal), none of which makes this task untrustworthy.
