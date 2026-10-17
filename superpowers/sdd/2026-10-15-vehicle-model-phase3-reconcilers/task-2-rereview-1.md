# Task 2 re-review 1: fix round 1 (6e600dc..2d87ed8)

Verdict: **PASS.** I1, I2 and m1–m3 are addressed. The round introduces no new Important or Critical issue. Two new Minor issues are listed below.

## Evidence

I re-ran the probe at 2d87ed8 (`scratchpad/probe-p3t2/`, which now includes `test_probe_round1.py`).

- **The old I1 reproducer now fails, as it should.** `test_probe_float.py::test_float_outside_saved_by_wrapper_is_invisible` now finds `saveNormalChargeLimit(1, 80.0, 60)` stored as `{'outside': 80, 'held': 60}`, and a read returns `(True, 80, 60)`. In the realistic-file migration, `[80.0, 50]` and `[80, 50.0]` both migrate to `(80, 50)`; neither is dropped any more.
- **The old I2 reproducer now adopts.** In `test_listing_before_load_misses_adoption`, after the load and a rebind the result is `HeldLimit(75, 60)`, the `id:` entry is gone, and the page shows "75% (holding 60%)".
- **The other migration probes are unchanged:** two runs give a stable result, an interrupted save is safe, nothing is queued or logged under the lock, the wake comparison is cost-safe (the only new wake is the impossible `[80, 101]` entry), and adoption after the load works.
- **Focused repo tests pass (129):** `test_held_limits`, `test_carapivehicle_registry`, `test_vehicles_page`, `test_twcmaster` and `test_registry_read_cascade`.

## The coordinator's two questions

- **Can `set` refusing a non-VIN key silently drop a held limit? No.**
  - No code in `lib` calls `heldLimits.set`.
  - The interim wrappers call `_set`/`_get`/`_remove`, which do not check the key. `saveNormalChargeLimit(<ID>)` still writes `id:<ID>`.
  - `test_wrappers_by_numeric_id_still_store` covers the TeslaAPI.py:1226 and :1243 paths, with int and string IDs, plus a remove. It passes.
- **Does the sweep do I/O under the lock or invert the lock order? No.**
  - `TWCMaster.py:1001` `_adoptListedHeldLimits` runs after `heldLimits.load()` with no lock held.
  - It copies `carApiVehicles` without taking `vehicleListLock`.
  - Each `adoptLegacyId` takes `settingsLock` only for the dict move, and queues the save after releasing it.
  - `test_sweep_no_lock_held_for_io_and_adopts` checks this: the car is adopted, and every save was queued with the lock not held.
  - The new `_bind` call on every bind runs from `CarApiVehicle.vehicle`. Its callers are TeslaAPI.py:46, :2517 and :2541, all on TeslaAPI threads, none holding a registry or vehicle lock. So there is no leaf-to-`settingsLock` inversion.
  - The `vehicleListLock -> settingsLock` edge is now documented (`TWCMaster.py:117-123`).

## New Minor findings

- **n1. A non-integral held limit is now refused, so it is never recorded.** Location: `HeldLimits.py` `_set`, the `_isInt` guard. A non-integral HA `batteryLevel` (66.3) can make `limitOverride` produce 65.3. `saveNormalChargeLimit(1, 80, 65.3)` then logs "Refused a non-integral held limit" and stores nothing (probe `test_non_integral_held_is_dropped_by_wrapper`). If the TeslaAPI applied the limit, the car stays held with no record, so it is never restored. The code before Task 2 stored the value. At 6e600dc it was stored but could not be read back, so this round is no worse.
  - The trigger is narrow: Home Assistant and TeslaAPI on the same car, a non-integral battery reading, and `limitOverride`.
  - Fix: in `_set` (and `_legacyEntry`), store `int(round(x))` for a finite number, and refuse only non-numbers. That is also what Tesla can actually hold.
- **n2. Every bind takes `settingsLock` when the VIN and an `id:` entry both exist.** Location: `HeldLimits.py:205-208` (the fast path). A BLE+Fleet install migrates to both a VIN entry (BLE's) and `id:<n>` (Fleet's). Under concern 1's ruling, adoption leaves the `id:` entry in place. The fast path checks only `legacy not in store`, so every `CarApiVehicle.vehicle` call takes the lock. That includes every `RegistryField` write: the probe counted 100 acquisitions for 100 writes. It is correct but needless, since it contends with `saveSettings`' `json.dumps`. Fix: also return early when `vin in store`.

## Notes

- m1's WARNING fires on every start for as long as the old release's `chargeLimits` stays in the file. That follows from the "never delete without migrating" rule, so it is acceptable. Task 10's sweep could remove `chargeLimits` once it is known to be stale.
- The CHANGELOG line matches what the code does on downgrade and re-upgrade.
