# Task 6 review: VehicleRegistry (7433281..6a3f370)

### Spec Compliance

**Compliant.** Every interface in the brief is present and behaves as specified. The controller rulings hold: `expire()` skips any vehicle with claims, user-asserted vehicles and anonymous vehicles (VehicleRegistry.py:119). `sourceLiveAt` returns `NOT_TRACKED` for an unregistered source (:156-157). `readSources()` sorts by `(order, registration index)` (:139-145). Keys come from upper-cased VINs and each `Vehicle(vin, vin, ...)` is created with matching key and VIN (:63, :68). The `anon:` prefix is reserved (:61). `load()` merges older `firstSeen` with newer `lastSeen` and restores the name as a `"persisted"` observation with `seen=False` (:209-220). A cloud listing counts as a sighting through Task 9's `CarApiVehicle` name observation (plan :801), so this task does not need to handle it.

Tests: tests/unit/test_registry_membership.py has 22 tests, all passing. The full unit suite passes (882). `black --check` reports the three touched files clean.

### Strengths

- Locking is correct. `expire()` holds `_lock` (:116) and reads `v.claims` (Vehicle.py:144-146). That property only copies the dict under the vehicle's leaf lock and never calls `canCommand`. Logging happens after the lock is released (:124). Locks are always taken registry first, then vehicle, which matches the global order. `sourceLiveAt` calls the liveness callable outside the lock (:154-159), and a callable that raises is treated as "not live" without logging the exception text. `Vehicle._liveAt` does not hold the vehicle lock when it calls back into the registry, so the order never inverts.
- `load()` cannot stop startup when the blob is bad. Input that is not a dict is ignored. Each entry gets its own try/except (:187-197). Field types are coerced through `_number()`, which rejects bools, NaN and inf. Persisted times later than now are clamped to now. A config with a malformed `vehicle` key falls back to 30 days. I probed with an overflowing int, a non-string name, NaN and lowercase keys, and none of them raised out of `load()`.
- The `toJSON` -> `load` round trip is tested, both into an empty registry (persisted times kept, not counted as a sighting) and into a populated one (merge).
- `getOrCreate` raising ValueError is acceptable. On the serial thread, `observeTwcVin` (plan :611) checks `isWellFormedVIN` before it ever calls `getOrCreate`. Without the check, `None` would have raised AttributeError anyway, and an empty key or an `anon:` key would have corrupted identity.

### Issues

**Critical:** none.

**Important:** none.

**Minor**

1. **The report's claim about the load key rule is wrong.** The report says `load()` accepts "same rule as getOrCreate, so toJSON output always reloads". That is false: `load` requires `isascii()` (VehicleRegistry.py:191) and `_getOrCreate` does not (:61). In a probe, `getOrCreate("ÿ1")` was accepted, `toJSON` wrote `"Ÿ1"`, and `load` dropped it. The comment at :190 also describes an explicit check that does not exist. Empty and `anon:` keys are rejected only because `_getOrCreate`'s ValueError is caught and logged as a WARNING. Fix: add the `isascii` check to `_getOrCreate`, or remove it from `load`, and fix the comment.
2. **A liveness callable that returns a non-number breaks pages.** If the callable returns, say, `"bad"`, both `Vehicle.age()` and `registry.summaries()` raise TypeError, so one provider bug would make the Vehicles tab fail. `sourceLiveAt` already guards against callables that raise (:158-162). Passing the return value through the existing `_number()` (keeping `None` as `None`) is a one-line fix.
3. **`forgetAfterDays` of 0 or less is accepted.** In a probe, `-1` gave `forgetAfter = -86400` and `0` gave `0`. Either way, every unclaimed vehicle that is not user-asserted would be dropped on the first `expire()`. Recommend treating values of 0 or less as the default and logging a warning (:31-38).
4. **The commit trailer is wrong.** Both commits (8131814, 6a3f370) carry `Co-Authored-By: Claude Sonnet 5.5`. global-constraints.md requires `Claude Opus 5.5` on every commit; the only exception is the Task 1 cherry-picks. This must be amended before the branch is finished.
5. **Note for the plan: callers that hold `Vehicle` objects go stale after `forget()` or `expire()`.** Leaving claims and attachments on the removed object is harmless, since the object is garbage. The real problem is that nothing tells the code still holding that object. Task 11's TeslaMate map ("if mapped -> observe", plan :1028) and Task 9's `CarApiVehicle.vehicle` keep a reference. After an expire, their observations go to an orphan the registry can no longer see. Also, a Forget on a car a provider still lists is undone on that provider's next listing, because `getOrCreate` re-creates the car and logs "added". There is also a narrow race: `getOrCreate` returns an existing stale vehicle, `expire()` removes it, and the caller then claims the orphan. Task 6 does not need to change for this, but the Task 9 and Task 11 briefs (and the Phase 6 Forget work) should do one of these:
   - re-resolve with `registry.get(key)` each time the vehicle is used;
   - add a cheap `removed` flag on `Vehicle` that `observe`/`claim` warn on;
   - have `getOrCreate` bump `lastSeen` under the registry lock, which closes the getOrCreate/expire window.
6. **Note for the plan (Task 8): startup expiry.** `load()` is deliberately not a sighting, and the Task 8 brief sets `lastVehicleExpiry = 0`. The first main-loop tick will therefore run `expireVehicles` before any provider has claimed its cars. A persisted car last seen more than 30 days ago that Fleet still lists gets expired, then re-created, and loses its `firstSeen`. Suggest that Task 8 initialise `lastVehicleExpiry = time.time()`.
7. Polish:
   - `expire()` reads `v.lastSeen` (:121) without `v._lock`, although Vehicle.py:59 says that lock guards it. This is harmless in CPython.
   - `"version"` is written (:180) but never checked in `load`.
   - `load` logs `Vehicle X added (persisted)` at INFO for every vehicle on every boot. Consider DEBUG for the `"persisted"` source.
   - No test checks that `toJSON` omits anonymous vehicles.
   - A persisted entry with a garbage `lastSeen` loads as seen now. That is conservative: it delays forgetting rather than forgetting early.
   - The anonymous-expire test reaches into `r._vehicles`. This is acceptable until Task 7 adds `beginPlugSession`.

### Assessment

**Task quality:** Approved

**Reasoning:** The module matches the brief and every controller ruling. Its locks are true leaves and the lock order is correct. A corrupt settings blob cannot stop startup. Issues 1-4 are small local fixes; the trailer (issue 4) must be amended before the branch is finished. Issues 5-6 concern how later tasks use the registry and belong in those tasks' briefs, not in a rework of this one.
