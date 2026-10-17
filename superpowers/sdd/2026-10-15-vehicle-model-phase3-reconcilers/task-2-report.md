# Task 2 report: registry support and the held-limit store

Status: DONE
Commits: 0fd13a1, 2588587 (`HeldLimits.set` stores -1 as None) (branch vehicle-model/phase3, on 7d5b87e)
Tests: full suite 1370 passed, 1 xfailed (1347 at 7d5b87e; 23 new tests)

## Fail-before

- `tests/unit/test_held_limits.py`: collection error
  `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile.HeldLimits'`
- `tests/unit/test_registry_read_cascade.py`: 4 failed, 13 passed:
  `TypeError: Vehicle.read() got an unexpected keyword argument 'sources'` (2 tests)
  `TypeError: Vehicle.read() got an unexpected keyword argument 'force'` (2 tests)
- `test_teslaapi_listing_adopts_the_legacy_id_once` (added after HeldLimits existed):
  `AssertionError: assert None == HeldLimit(outside=75, held=60)` before `_bind` adopted.
- `test_vehicles_page.py`, 3 tests: `AttributeError: 'types.SimpleNamespace' object has no attribute 'heldLimits'` once `heldLimitText` read the store, before the fixture was moved to it.

## What changed

- `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py` (new): `HeldLimit(outside, held)`, `HeldLimits` with `KEY`/`LEGACY_KEY`, `load`, `get`, `set`, `remove`, `adoptLegacyId`, `vins`, `holding`, and a module helper `storeKey(ident)` (well-formed VIN, upper-cased; otherwise `"id:<ident>"`).
- `Registry/Vehicle.py`: `latestFrom(field, exclude)`, `believed(field, exclude)`, `trusted(field, exclude)`, `read(..., sources=None, force=False)`. With an empty `exclude`, `latestFrom` returns `latest()`, so `trusted(field)` behaves exactly as before. When every source is excluded, `trusted` returns None and does not fall back to the store's latest. Excluded sources also cannot vouch through `_liveAt`.
- `Registry/Fields.py`: `FieldStore.trusted` takes an optional `obs` to judge in place of the latest.
- `TWCMaster.py`: `self.heldLimits = HeldLimits(self)`. `loadSettings` calls `heldLimits.load()` after the settings are assigned. `getNormalChargeLimit`, `saveNormalChargeLimit` and `removeNormalChargeLimit` are thin wrappers. `_heldLimitKey(ID)` resolves a numeric ID through `TeslaAPI.carApiVehicles`, adopting first, and otherwise uses the `id:` entry. `saveNormalChargeLimit` maps `lastApplied` -1/0/None to `held=None`, so the sentinel is never stored. Each wrapper takes the lock once, so `test_settings_lock` counts are unchanged.
- `TeslaAPI.CarApiVehicle._bind`: inside the new-binding branch, calls `master.heldLimits.adoptLegacyId(self.ID, self.VIN)`. It is guarded with `getattr` for a master with no store (FakeMaster, or `master` None).
- `HTTPControl.heldLimitText`: reads `master.heldLimits.get(vehicle.vin)`. It shows "N% (restored)" when `held` is None and "N% (holding M%)" otherwise.

## Migration safety

- Under `settingsLock`, `load()` only does dict work: it builds the complete new store, then assigns `settings["heldLimits"]` and deletes `chargeLimits` in one step. It does no I/O; warnings are logged and the save is queued after the lock is released. A save therefore sees either the old key or the new one, never neither.
- `load()` migrates only when `heldLimits` is absent and `chargeLimits` is a dict. When `heldLimits` exists, it leaves `chargeLimits` alone and does not save, so nothing is deleted without being migrated (for example after a downgrade and re-upgrade). When neither key exists it does nothing and does not save.
- The migration is idempotent. A second `load()` does nothing. A restart from the migrated file does nothing. A crash before the queued save re-runs the same deterministic migration from the unchanged file.
- Entries are mapped as follows:
  - an int `n` becomes `(n, None)`;
  - `(o, -1)`, `(o, None)` and `(o, 0)` become `(o, None)`;
  - `(o, n)` with 50 <= n <= 100 becomes `(o, n)`;
  - lists and tuples are both accepted (JSON turns tuples into lists);
  - a bool is not counted as an int.
  
  Anything else is dropped, with one WARNING per key.
- Unresolved keys are persisted as `heldLimits["id:<key>"]`. `vins()` and `holding()` never return `id:` keys.
- The tests use a realistic old `settings.json` written to disk. It has VIN keys, numeric-ID keys, a lower-case VIN, list pairs, a bare int, -1/0/None entries and four malformed entries. The tests check the on-disk round trip through the real `saveSettings`, idempotence, a crash before the save, existing-store precedence, the swap happening under the lock, and adoption through the real `TeslaAPI.addVehicle`.

## Concerns / decisions for the reviewer

1. **`adoptLegacyId` when the VIN already has an entry.** The brief does not say what happens here. The VIN entry wins, and the `id:` entry is kept (not deleted) and not saved, so nothing is discarded. Task 10 can sweep stale `id:` entries.
2. **`(o, n)` with n outside 50..100 (for example `[80, 30]`) is dropped, as the brief's mapping says.** The outside value is lost for that key. The alternative would have been to keep `(o, None)`.
3. **Two legacy keys can collide after upper-casing,** for example a VIN in both cases. When that happens the later entry wins, silently. This is rare.
4. **Behaviour change for migrated bare-int entries.** The old `getNormalChargeLimit` returned `lastApplied=0` for them; it now returns -1, as the brief's test requires. In `TeslaAPI.applyChargeLimit` the wake test `limit > (lastApplied if lastApplied != -1 else outside)` now compares against `outside` instead of 0, which is more correct. The restore paths behave the same.
5. **`heldLimitText` reads only by VIN.** A legacy `id:` entry shows "—" until TeslaAPI lists the car and adopts it. In practice the listing happens after `loadSettings`.
6. **The interim wrappers call `HeldLimits._get/_set/_remove` (private) for `id:` keys.** Task 10 deletes the wrappers.
7. **`read(sources=)` accepts ReadSource objects or source names.**
8. **The store itself refuses the sentinel.** `HeldLimits.set(vin, o, -1)` stores `held=None`; fail-before: `assert {'outside': 80, 'held': -1} == {'outside': 80, 'held': None}`. The value 0 is mapped to None only by the interim wrapper.
9. **`chargeLimits` appears nowhere else in `lib`.** A grep with no file filter finds no template or JS reading it.

## Rulings

The coordinator accepted concerns 1, 3, 4, 5 and 7 as built. Two changes were made, both test-first, in commit 6e600dc on top of 2588587. Full suite after: 1373 passed, 1 xfailed.

- **Concern 2: the user's normal limit is never lost.**
  - If the held value is outside 50–100 but the outside value is a valid int, the entry now migrates as `(outside, None)` with one WARNING. For example, `[80, 30]` becomes `{"outside": 80, "held": None}`.
  - An entry is dropped only when the outside value itself is invalid: a non-int, a bool, None, or a wrong shape.
  - Fail-before: `test_out_of_range_held_keeps_the_outside_limit` failed with `assert None == HeldLimit(outside=80, held=None)`. `test_realistic_settings_file_migrates` failed because the store lacked `id:999`.
  - `test_invalid_outside_is_dropped` passed before the change. It pins behaviour that already existed.
- **Concern 6: a case collision is now logged.** When two old keys name the same VIN, a WARNING names both keys and says which one was kept (the later key wins).
  - Fail-before: `test_case_collision_warns_naming_both_keys` failed with `assert 0 == 1` (no warning was logged).

## Fix round 1

Commit 2d87ed8, on top of 6e600dc. Full suite after: 1380 passed, 1 xfailed (7 new tests). Every item was done test-first; the fail-before output is quoted with each one.

- **I1. Integral floats.**
  - `_isInt` now accepts integral floats such as 80.0, so Home Assistant's float limits are no longer rejected. `_set`, `_legacyEntry` and `_storedEntry` store and return `int(x)`.
  - A non-integral value follows the invalid-value rule:
    - during migration, an invalid outside value drops the entry, and an invalid held value keeps the outside value with `held` None;
    - a stored non-integral entry reads back as None;
    - `_set` refuses it with a WARNING and leaves the store unchanged.
  - Tests:
    - `test_integral_floats_round_trip_as_ints` covers a wrapper call with 80.0, a held value of 66.0 (as `limitOverride` produces from a float `batteryLevel`), and a stored 80.0;
    - `test_integral_floats_migrate`;
    - `test_non_integral_floats_are_invalid`.
  - Fail-before: `assert (False, None, None) == (True, 80, 60)`.
- **I2. Adoption when the car is listed before settings load.** Both fixes are in:
  - `_bind` now calls `adoptLegacyId` on every bind, outside the identity guard. Its unlocked fast path is a single dict lookup, and it saves only when it moves an entry.
  - `loadSettings` calls `_adoptListedHeldLimits()` after `heldLimits.load()`. This sweeps `TeslaAPI.carApiVehicles` without taking `vehicleListLock`.
  
  Tests: `test_listing_before_load_is_adopted` (fail-before: `assert None == HeldLimit(outside=75, held=60)`) and `test_rebind_adopts_an_entry_that_appeared_later` (fail-before: `assert None == HeldLimit(outside=80, held=None)`).
- **m1. Downgrade and re-upgrade.**
  - When `heldLimits` and `chargeLimits` both exist, `load()` logs one WARNING outside the lock, and `chargeLimits` is kept but ignored.
  - CHANGELOG (Architecture) has a new line. It says the store migrates on first start and that downgrading loses the held limits. It also says that upgrading again uses the held limits saved before the downgrade, with a warning.
  - Test: `test_both_keys_present_warns_once`, which failed before with `assert 0 == 1`.
- **m2. Bad input to `set`.**
  - `HeldLimits.set` refuses a key that is not a well-formed VIN, with a WARNING.
  - `_set` maps a held value of 0 to None, as it already did for -1.
  - Test: `test_set_refuses_a_non_vin_and_maps_zero_to_none`.
- **m3. Lock order.** The lock-order comment in `TWCMaster.__init__` now records the `TeslaAPI.vehicleListLock -> settingsLock` edge.
- **m4.** No action, as the review says.

## Re-review follow-ups (n1, n2)

Commit 9a44495, on top of 2d87ed8. Full suite after: 1383 passed, 1 xfailed.

- **n1. `_set` and `set` now round instead of refusing.**
  - They store `int(round(x))` for any finite number, for both `outside` and `held`.
  - They refuse only values that are not numbers (strings, None as an outside value, bools), or that are NaN or ±inf. A refusal logs a WARNING and leaves the store unchanged.
  - A held value of -1 or 0 after rounding is still stored as None.
  - I read "between 50 and 100 after rounding" as describing the expected values, not as a range check or a clamp, so out-of-range numbers are stored rounded and unchanged. Say if you wanted a clamp.
  - Python's `round` uses banker's rounding, so 80.5 becomes 80.
  - Migration (`_legacyEntry`) and stored-entry reads (`_storedEntry`) are unchanged: they still require integral values.
  - Tests:
    - `test_set_rounds_finite_numbers`: a held 65.3 round-trips as 65, through both `set` and the wrapper. Fail-before: `assert None == HeldLimit(outside=80, held=65)`.
    - `test_set_refuses_what_is_not_a_finite_number`: 8 refusals, each with a warning. It replaces the earlier assertions that `set` refuses a non-integral value.
- **n2. The `adoptLegacyId` fast path returns early when the VIN already has an entry.** It now returns as soon as it sees a VIN entry, without taking the lock.
  - Test: `test_bind_skips_the_lock_when_the_vin_already_has_an_entry`. It counts `settingsLock` acquisitions as the probe does, over 100 `CarApiVehicle.vehicle` calls with both a VIN entry and an `id:` entry present.
  - Fail-before: `assert 100 == 0`. After the fix the count is 0.
