# Task 1 report: outcome vocabulary and desired-state store

**Status:** DONE
**Commit:** d9939bf on `vehicle-model/phase3` (parent 6a6c14e)

## Files
- `lib/TWCManager/Vehicle/Reconcile/__init__.py`: re-exports.
- `lib/TWCManager/Vehicle/Reconcile/Outcome.py`: kinds, `KINDS`/`SETTLED`/`RETRYABLE`/`EXCLUDING` (all frozensets), `Outcome`, `isOutcome`, `LANE_DETAILS`. The provider return contract is in the module docstring.
- `lib/TWCManager/Vehicle/Reconcile/Desired.py`: aspects, `FIELD_FOR`, `CAPABILITY_FOR`, `Desired`, `Attempt`, `AttemptRecord`, `ChannelHealth`, `SessionBounds`, `ControlState`, `DesiredStore`.
- `tests/unit/reconcile_helpers.py`: `Clock`, `COMMAND_CAPS`, `ScriptedProvider`, `make_order`.
- `tests/unit/test_outcome_desired.py`: the brief's 10 tests verbatim, plus 3 more (a raising onChange callback is dropped and the others still run; ScriptedProvider and make_order behaviour; endSession resets health and records in place).

## TDD
Fail-before, at 6a6c14e with only the test file in place:
`E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile'` (collection error).
After: `tests/unit/test_outcome_desired.py` 13 passed. Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1339 passed, 1 xfailed** (baseline 1326 + 13 new).
`test_default_clock_is_wall_time` uses the production default clock (`time.time`).
Black ran on `Reconcile/` and `reconcile_helpers.py` only.

## Decisions the brief left open (tests do not distinguish these)
1. **"Unchanged" means same value and same `restore`/`lift`/`forced`.** The test forces the flags into the comparison: after `forced=True` and then `endSession`, a non-forced `set(False)` has to return True. A change in `by` alone is **not** a new desire: `by` is not updated, there is no `newDesire()` and no callback. This keeps the heartbeat and the distributor from churning a record when they write the same value in turn. Consequence: `release(value, by)` keys on whichever `by` wrote the value first.
2. **`decision=True` with the same value as an *adopted* desire** takes it over in place (`adopted=False`, `by` updated, `at` kept) and returns False, with no `newDesire()` and no callback. The car already has that value.
3. **`newDesire()` leaves `excluded` alone**, as the brief says. Only `newRound()` clears it, so a provider that returned UNSUPPORTED or REFUSED for one value is still skipped for the new value until the round ends.
4. **`adopt(CHARGING)`**: a value counts as charging-like when `True` or one of "Charging", "Starting", "Complete" (or Task 6's `Reconciler.satisfied(CHARGING, True, v)`, imported lazily with an ImportError fallback). It sets `wantsCharge` and clears `userStopped`. A stopped-like value (`False` or "Stopped") sets `userStopped` and clears `wantsCharge`, so the latest user action wins. Any other value (None, "Disconnected", "NoPower") is not adopted: the call does nothing and logs at DEBUG. `adopt` does **not** check `offering`. The "requires both" rule belongs to the Task 8 caller, as the test shows (`adopt("Stopped")` with no `noteOffering` gives `userStopped`). The docstring says so.
5. **Callbacks.** `onChange` fires outside the lock after a changing `set`, `clear`, `release` or `adopt`; on an `offering` transition in `noteOffering` (aspect `CHARGING`); and for every aspect on `endSession`. Ignored or unchanged `set`s and `decision()` do not fire it. A raising callback is logged at DEBUG by type name and the remaining callbacks still run.
6. **Bounds on growth.** `set`/`get`/`clear`/`release`/`adopt`/`record`/`settled` raise ValueError for an unknown aspect, so the per-aspect maps cannot grow past `ASPECTS`. The per-key maps are bounded by the registry's keys. The interface has no `forget(key)`, so a forgotten car's `ControlState` stays until restart. A later task may want an eviction hook tied to the registry's forget.
7. `endSession` resets each existing record and each ChannelHealth in place (`ChannelHealth.reset()`), so a held reference sees the reset. It leaves `probeInFlight` and `offering`/`offeringSince` alone, since the brief does not list them. Desired values are kept; only their adopted flags are cleared.
8. **Helpers.**
   - `COMMAND_CAPS` lives in the helper: the five `Capability.COMMANDS` at `Declaration(LOCAL)`. `tier=` takes a `Cost` (as later tasks pass `tier=C.FLEET_COMMAND`) and replaces the cost on every declared capability, keeping each rate limit.
   - When the script is empty (`outcomes=[]`), a method returns `Outcome(ERROR, "unscripted")`. Task 3 builds `ScriptedProvider(..., [])` and then overrides the method.
   - `Clock` starts at `t=1000.0`.

## Concerns for later tasks
- **`reset()` clears `inFlight`**, as the brief says. `endSession` resets records while a lane may still hold that attempt. The one-in-flight-per-(car, aspect) invariant then depends on Tasks 3/6: their report path must tolerate a record whose `inFlight` is already None, or one that now holds a different attempt (compare by identity before clearing). Until the report lands, the planner could also submit a second attempt for the same aspect.
- `AttemptRecord` and `ChannelHealth` objects come out of the store and are mutated outside the store's lock (the tests do exactly this). Tasks 3/6 should do those mutations on one thread (the reconciler's report handling), or under the store's lock through store methods.
- `Provider` itself still has only `setAmps`/`wake` raising `NotImplementedError`. `ScriptedProvider` defines all six command methods. Task 3 adds the `Outcome`-returning defaults.

## Fix round 1

**Commit:** 7d5b87e (on top of d9939bf)

**Fail-before:** I wrote 8 new tests first. Against d9939bf, 5 of them failed:
- `forget` and `followRegistry` missing (AttributeError)
- `AttemptRecord.exclude` missing
- `adopt(AMPS, None)` cleared desired (`'NoneType' object has no attribute 'value'`)
- the broken-Reconciler test: `DID NOT RAISE ImportError`

The other 3 tests (by-only no-op, in-place decision takeover, newRound keeping `paid` plus the offeringSince restamp) pinned behaviour that already existed and passed.

**After:** `test_outcome_desired.py` 21 passed. Full suite: **1347 passed, 1 xfailed** (1326 + 21).

- **I1.**
  - `DesiredStore.forget(key)` drops the key's whole `ControlState` under the lock, with no callback.
  - `VehicleRegistry.onRemove(callback)` is called with the key, outside the registry lock, from all four removal paths: `forget`, `expire`, `endPlugSession` (the anonymous vehicle), and `observeTwcVin`'s merge of `anon:<point>` into the VIN. A raising callback is logged at DEBUG by type name.
  - `DesiredStore.followRegistry(registry)` subscribes `forget`, so the registry never imports Reconcile.
  - Test: 50 anonymous sessions churned, plus the anon merge, forget and expiry, leave `keys() == []`.
  - Wiring is still open: nothing calls `followRegistry` yet because `master.desired` doesn't exist. Whichever task creates `master.desired` must call `master.desired.followRegistry(master.vehicleRegistry)`.
  - Desired state on an `anon:` key is forgotten at the merge, not moved to the VIN.
- **I2.**
  - New `AttemptRecord.exclude(provider, kind)` adds the provider to `excluded`, and also to a new `refused` set when the kind is REFUSED.
  - `newDesire()` keeps only the refused exclusions. `newRound()` and `reset()` clear `refused` too, and `summary()` shows it.
  - A name added to `excluded` directly counts as UNSUPPORTED, so Task 6 should call `exclude()`.
- **Minors.**
  - Each concern-4 behaviour now has a test, and so does the offeringSince restamp.
  - `adopt` classifies a CHARGING value before taking the lock. The import stays lazy because Reconciler will import Desired, so an eager import would be a cycle.
  - Only `ModuleNotFoundError` whose `name` is `...Reconcile.Reconciler` falls back. Any other import failure propagates: a test puts a Reconciler module with no `satisfied` in `sys.modules` and expects ImportError.
  - `adopt(..., None)` is now ignored for every aspect: an unread value is never the user's.
- Black ran on `Reconcile/` and `VehicleRegistry.py`; it reformatted only my own new line.
