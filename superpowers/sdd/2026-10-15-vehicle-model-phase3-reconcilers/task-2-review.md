# Task 2 review: registry support and the held-limit store (7d5b87e..6e600dc)

Spec compliance: **PASS**
Task quality: **PASS WITH FINDINGS** (0 Critical, 2 Important, 4 Minor)

Spec is judged against the brief as amended by the coordinator rulings (concerns 1, 3, 4, 5 and 7 accepted; concern 2 keeps `(outside, None)`; concern 6 warns on a case collision). Every name in the Interfaces block exists as written:
- `Vehicle.latestFrom`, `believed`, `trusted(field, exclude=())`, `read(field, maxAge, allowWake=False, sources=None, force=False)`.
- `HeldLimit(outside, held)`.
- `HeldLimits.KEY`, `LEGACY_KEY`, `__init__(master)`, `load`, `get`, `set`, `remove`, `adoptLegacyId`, `vins`, `holding`.
- `TWCMaster.heldLimits`, and the wrappers, which resolve a numeric ID.
- `_bind` adoption.
- `heldLimitText` reads the store.

Both rulings are applied and tested. black reports the lib files clean. The brief's five test files pass (125). `tests/unit` passes (1364).

## Verified (the brief's hard checks)

The probe is in `scratchpad/probe-p3t2/` (`test_probe_migration.py`, `test_probe_float.py`). Its fixture is a realistic old `settings.json`:
- VIN keys, plus a lower-case VIN;
- numeric IDs;
- `[o, -1]`, `[o, 0]`, `[o, None]` and bare-int entries;
- a case-colliding pair;
- `[100, 100]`;
- held values out of range (30 and 101);
- malformed entries;
- float entries.

The probe ran it through the real `loadSettings`/`saveSettings` twice. Results:

- **One-time and idempotent.** The first load migrates and queues one save. The second load, from the saved file, gives the same `heldLimits`, makes no change and does not save. Every legacy entry with a usable int outside keeps its outside value. For the colliding pair, the later key wins and a WARNING names both keys.
- **Numeric IDs** persist as `id:<n>`. A real `TeslaAPI.addVehicle` after the load moves the entry under the VIN, and it survives a restart. The exception is in I2.
- **A partial run is safe.** If a crash happens before the queued save, the same deterministic migration re-runs. If a `.tmp` was written but not renamed, the main file is read. If the main file is corrupt, the `.backup` copy (legacy format) migrates to the same result.
- **Lock.** The swap happens under `settingsLock`. Neither the save queueing nor any of the warnings ran while the lock was held.
- **Lock order.**
  - `TeslaBLE.applyChargeLimit` (under `_bleLock`) calls the wrappers, which reach `adoptLegacyId` and take `settingsLock`. That order is allowed.
  - `loadVehicleList` (under `vehicleListLock`) calls `addVehicle`, then `_bind`, then `adoptLegacyId`, which takes `settingsLock`. Nothing takes `vehicleListLock` while holding `settingsLock`, and `_heldLimitKey` copies `carApiVehicles` without a lock.
  - Registry and vehicle locks are released before `adoptLegacyId` runs.
- **Downgrade** matches the planned CHANGELOG line ("downgrading afterwards loses them"). An old release finds no `chargeLimits`, keeps `heldLimits` as an unknown key, and writes a fresh `chargeLimits`. The re-upgrade case is in m1.
- **Concern 3 (wake comparison): correct and cost-safe.** The probe compared the old and new `needToWake` for every legacy shape and every limit from 50 to 100 and -1.
  - Migrated `[o, 0]`, `[o, None]` and bare-int entries now compare against `outside` instead of 0. The old `limit > 0` woke for every limit, so the new code wakes strictly less often.
  - The only new wake is the impossible `[80, 101]` entry.
  - The restore is cheaper too. `limit != lastApplied` is now `-1 != -1`, so a restore of an entry that holds nothing no longer re-enters the second loop and its `update_charge()` read. It used to.
  - This is the right comparison because such an entry holds nothing: the car sits at `outside`.
- **`read(force=)`: no new paid read.** No caller in `lib` passes `force` or `sources`. The only caller is `TeslaAPI.py:2517 vehicle.read(field, maxAge=)`. With the defaults, `read` and `trusted` behave exactly as at 7d5b87e. Note for Task 6: `force=True` without `sources` would cascade through the Fleet API (a paid read). The caller must pass the lane's `sources=` and force only when `needsLiveRead` holds.

## Important

**I1. A float charge limit is stored but cannot be read back, so a held car is never restored.** Locations: `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py:33` (`_isInt`), `:66-72` (`_storedEntry`), `:153` (`_set`) and `:47-63` (`_legacyEntry`).

How a float gets in:
- `HomeAssistant.py:138` observes `chargeLimit` as `float(state)`, and `:128` does the same for `batteryLevel`.
- On this branch the registry hands those floats to `CarApiVehicle.chargeLimit` and `batteryLevel` (`RegistryField`).
- So `TeslaAPI.applyChargeLimit`'s `outside = vehicle.chargeLimit` can be `80.0`. `Policy`'s `limitOverride` limit, `minBatteryLevelAtHome - 1`, can be `66.0`.

What happens: `_set` stores the float, and `_storedEntry` then rejects the whole entry. `getNormalChargeLimit` returns `(False, None, None)`, so the code treats the car as not at home and never restores it. The probe's `test_float_outside_saved_by_wrapper_is_invisible` shows this:
- `saveNormalChargeLimit(1, 80.0, 60)` stores `{'id:1': {'outside': 80.0, 'held': 60}}`, but a read of it returns not-found;
- `heldLimits.set(VIN, 80, 66.0)` followed by `get` returns `None`.

The old tuple store returned floats unchanged, so this is a regression from 7d5b87e. It is not in any release: on `main`, `chargeLimit` is not a registry field. It is reachable on this branch for an install where Home Assistant and TeslaAPI serve the same car. The migration also drops `[80.0, 50]` entirely, and drops the held value of `[80, 50.0]`.

Fix: normalise at the store boundary. Accept an integral number in `_isInt`, i.e. `isinstance(x, (int, float)) and not isinstance(x, bool) and float(x).is_integer()`. Store `int(x)` in `_set` and `_legacyEntry`, and read it back the same way in `_storedEntry`. For a non-integral value, round it, or refuse it with a WARNING.

Fixing it in the store matters more than fixing Home Assistant's parsing. In Task 6 the reconciler's adoption calls `heldLimits.set(vin, outside=latest.value, ...)` with the same registry values.

Tests:
- a wrapper round trip with `80.0`;
- `set(VIN, 80, 66.0)` followed by `get`;
- migration of `[80.0, 50]` and `[80, 50.0]`;
- a stored `{"outside": 80.0, "held": null}`.

**I2. A numeric-ID held limit is not adopted when TeslaAPI lists the car before `loadSettings`.** Location: `lib/TWCManager/Vehicle/TeslaAPI.py:2289-2302`.

`_bind` adopts only inside `if vehicle is not self._vehicle`. `VehicleRegistry._loadOne` merges into the existing vehicle, so the later rebind sees the same vehicle and never adopts. Until something else moves it, the entry stays under `id:<n>`, and the Vehicles page shows "—".

The trigger is realistic. TeslaMate token sync gives TeslaAPI a token before `TWCManager.py:831 master.loadSettings()`. A retained telemetry message then reaches `Telemetry.py:370 carapi.loadVehicleList()` first. The probe's `test_listing_before_load_misses_adoption` reproduces this: after the load and a rebind, `get(VIN)` is `None` and `id:` is still present.

In this task the interim wrapper repairs it on the next `TeslaAPI.applyChargeLimit`. After Task 10 deletes the wrappers, nothing will. `holding()` excludes `id:` keys, so the reconciler would never restore that car.

Fix (cheap), either of:
- call `adoptLegacyId` from `_bind` on every call, outside the identity guard. Its unlocked fast path is a single dict lookup.
- have `TWCMaster.loadSettings`, after `heldLimits.load()`, call `adoptLegacyId(car.ID, car.VIN)` for each car in `TeslaAPI.carApiVehicles`.

Add a test that lists the car before `loadSettings`. Carry to Task 10 either way.

## Minor

- **m1. Re-upgrade after a downgrade restores the earlier held limits.** Location: `HeldLimits.py:104` (the `KEY not in settings` guard). If `heldLimits` exists, the `chargeLimits` an old release wrote during the downgrade is ignored and kept forever. The probe shows this: after a re-upgrade, `get(V2) == (90, 50)` and the newer `[95, 55]` is unused. The rule is safe, since it deletes nothing, but it is silent. Fix: log one WARNING when both keys exist. Task 10's CHANGELOG or sweep should also say that a re-upgrade uses the held limits from before the downgrade.
- **m2. `HeldLimits.set` accepts any key.** Location: `HeldLimits.py:174`. `set("anon:8244", ...)` would persist an entry that `vins()` hides forever, and `set(vin, o, 0)` stores 0, which the migration treats as "none". Fix: refuse a key that is not a well-formed VIN, with a WARNING, and map `held` 0 to None in `_set` as -1 already is.
- **m3. Undocumented lock-order edge.** Location: `TWCMaster.py:117-121`. The lock-order comment does not mention the new `TeslaAPI.vehicleListLock -> settingsLock` edge (`addVehicle` → `_bind` → `adoptLegacyId`). Fix: add it to the comment, so that no one later takes `vehicleListLock` while holding `settingsLock`.
- **m4. Concern 2's ruling creates a new wake on an impossible entry.** For `[80, 101]` (`held` above 100), the migrated `(80, None)` wakes for limits 81 to 100, which the old code compared against 101. Tesla never accepts 101, so this cannot happen in practice. No action needed.

## Test quality

The tests are strong:
- the real `loadSettings`/`saveSettings` on disk;
- a crash before the save;
- the existing store winning;
- the swap under the lock;
- adoption through the real `addVehicle`;
- both `sources=` cases;
- the forced read past a live feed, whose `c.t = 5000` makes the non-forced assertion depend on liveness.

Gaps: the float cases (I1) and listing before load (I2).
