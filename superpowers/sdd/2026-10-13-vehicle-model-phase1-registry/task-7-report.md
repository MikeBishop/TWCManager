# Task 7 report: anonymous plug-session vehicles and TWC VIN confirmation

Status: DONE. Commit `dca0d13` on `vehicle-model/phase1` (parent b7ced59).

## Changes
- `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`
  - `CONFIRM_ATTEMPTS = 3`; `_pending: Dict[str, dict]` per point (`candidate`, `attempts`, `rejected`) under `_lock`.
  - `beginPlugSession(pointId)`: creates/returns `anon:<pointId>` directly (bypasses `getOrCreate`, which rejects `anon:` keys). Idempotent.
  - `endPlugSession(pointId)`: removes the anon vehicle, pops pending state, then (outside the lock) observes `twcVin=None` (source `TWC`, `seen=False`) on every VIN vehicle attributed to the point.
  - `observeTwcVin(pointId, vin)`: order is non-str/malformed -> `rejected` (state untouched, so it does not count as an attempt); known VIN -> `confirmed`; sticky `rejected` for the session; else `attempts += 1`, match of candidate -> `confirmed`, `attempts >= 3` -> `rejected` (INFO `TWC <point> VIN <vin> not confirmed; ignoring` logged once, at the transition), else candidate replaced -> `pending`. Decision is made under `_lock`; `getOrCreate`, the merge, observes and logging happen outside it. Merge copies `anon._fields.snapshot()` into the VIN vehicle with original stamps (older stamps never displace newer), then pops the anon vehicle and observes `twcVin=pointId`.
  - `pointFor(vin)`, `vehicleAt(pointId)` (VIN vehicle whose latest `twcVin == pointId`, newest first; else the anon vehicle; else None).
- `lib/TWCManager/TWCMaster.py`
  - `__init__`: `self.vehicleRegistry = VehicleRegistry(config)`.
  - `num_cars_charging_now`: `_plugSession(slaveTWC, True/False)` where `isCharging` flips 1/0; helper wraps the registry call in try/except (warning log) so nothing escapes onto the serial loop.
  - `recordVehicleVIN`: `observeTwcVin` first (try/except -> log + return); `pending` -> `queue_background_task({"cmd": "getVehicleVIN", "slaveTWC": TWCID, "vinPart": 0}, delay=5)` and return; `rejected` -> return; `confirmed` -> the existing SlaveTWCs / Vehicles bookkeeping under `with self.settingsLock:` with `.get("chargeSessions", 0) + 1` and `.setdefault("totalkWh", 0)`; `saveSettings` queued once, after the lock is released (the original queued it twice; the queue dedupes `saveSettings` anyway). Log and `vehicleIsDefinitelyHome` unchanged.
- Tests: `tests/unit/test_registry_plug_sessions.py`, `tests/unit/test_twcmaster_vin_confirmation.py` verbatim from the brief (black-formatted). Both failed first (10 failed), now pass.

## Verification
`python -m pytest tests/unit -q` -> 901 passed (was 891; +10), 1 warning, pre-existing: it is absent from the 69-test run of the touched files plus test_twcmaster.py. Black run only on the four touched files.

Pure-Gen2: `TWCMaster` now imports `TWCManager.Vehicle.Registry` at module level. `lib/TWCManager/Vehicle` has no `__init__.py` (namespace package), so no provider module (TeslaAPI, TeslaBLE, ...) is imported; the Registry modules import only stdlib. `setup.py` uses `find_namespace_packages(where="lib")`, so the Registry package is installed.

## Concerns / notes
1. `queue_background_task(..., delay=5)` uses `bisect.insort` on `(datetime, task)` tuples; two delayed tasks with an identical `datetime` would compare dicts and raise `TypeError`. Pre-existing, but this is the first serial-thread caller of the delayed path. In practice `datetime.now()` has microsecond resolution, so a collision is very unlikely; a tie-breaking counter in the tuple would remove it.
2. A known VIN confirms on every read. Main recorded a session on every valid parse too, and after confirmation nothing re-queries (retryVINQuery skips once `currentVIN` is set), so the session count per plug-in is unchanged from main. An unknown VIN is now recorded once (on the second read), not twice.
3. The known-VIN check precedes the sticky `rejected` flag, so a session rejected for an unknown VIN still confirms if a later read is a VIN the registry already knows. This is a deliberate reading of "known vehicle: one read suffices".
4. `slaveTWC.currentVIN` stays set even when the registry rejects it, as the brief specifies (entitlement, `getTWCbyVIN`, status unchanged). A misheard VIN therefore still reaches entitlement checks as on main; only registry creation and history wait for confirmation.
5. The merge copies observations only, not `noteWrite` records. Nothing writes to anonymous vehicles in Phase 1.
6. If the delayed re-query fires after the session ended, the next parse starts a fresh pending count (state cleared by `endPlugSession`), which is harmless.

## Fix round 1

Commit `e162463` (on top of dca0d13). The new tests were written first and 6 failed: no `isPending`, no retry timer set on pending, no bounded retries, TypeError escaped, VIN queries deduped across TWCs, dict comparison on a tie. The confirmed-no-retry test is a guard and passed from the start. All pass now; full suite 908 passed. The 1 warning is the same pre-existing one.

1. **Lost confirmation reads (review item 2).**
   - The registry has a new `isPending(pointId)`. It is true when the point has a candidate VIN that is neither confirmed nor rejected. It is reset by confirmation and by `endPlugSession`.
   - On `pending`, `recordVehicleVIN` queues the delayed re-query as before. It also sets `slaveTWC.lastVINQuery = now` and `vinQueryAttempt = 1`.
   - `retryVINQuery` now retries while `not currentVIN or registry.isPending(point)`. The pending check is in `_vinPending`, which is exception-guarded. Retries reuse the first read's budget: 60 s spacing and `< 6`, so 6 queries per candidate in all.
   - Once the VIN is confirmed or rejected, the RX loop has already zeroed the timer and `isPending` is false, so retries stop.
   - The overall bound is 3 candidates × 6 queries, because the registry rejects after 3 reads.
2. **Per-TWC dedupe.**
   - The new `_taskKey(task)` returns `("getVehicleVIN", bytes(slaveTWC))` for VIN queries, and `cmd` for every other task.
   - `queue_background_task`, `delete_background_task` and `doneBackgroundTask` all use it.
   - One TWC's query no longer replaces another's. Part requests for the same TWC still merge as before. `bytes` and `bytearray` ids give the same key.
   - Nothing outside `TWCMaster.py` touches `backgroundTasksCmds`.
3. **Delayed-queue tie (review item 1).**
   - Delayed entries are now `(due, next(_delaySeq), task)`. `_delaySeq` is a class-level `itertools.count()`, matching the class-level list.
   - The drain uses `pop(0)[-1]`, so the existing test that injects a 2-tuple still works.
   - Equal due times keep FIFO order and never compare dicts.
   - The pending-path `queue_background_task` call is now inside `recordVehicleVIN`'s try.

Tests added:
- `test_registry_plug_sessions.py::test_is_pending_tracks_the_unconfirmed_candidate`
- In `test_twcmaster_vin_confirmation.py`:
  - lost response → re-queried → confirmed
  - retries bounded at 6, VIN stays pending, no vehicle created
  - no retry once confirmed
  - queue failure on pending does not escape
  - VIN queries for different TWCs both queued, same TWC still deduped, done-bookkeeping clears
  - equal delayed due times stay FIFO with no TypeError
