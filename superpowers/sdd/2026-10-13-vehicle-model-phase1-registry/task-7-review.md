### Spec Compliance

**Compliant.** All `VehicleRegistry` interfaces in the brief are there with the specified semantics: `beginPlugSession`/`endPlugSession`/`observeTwcVin`/`pointFor`/`vehicleAt`/`CONFIRM_ATTEMPTS`. `TWCMaster.__init__` creates the registry, `num_cars_charging_now` calls begin/end at the `isCharging` flips, and `recordVehicleVIN` branches on pending/rejected/confirmed as the brief says, with `.get("chargeSessions", 0) + 1` / `.setdefault("totalkWh", 0)` under `settingsLock`. The test files match the brief verbatim (after black). Spec identity/phantom rules (spec lines 56, 61) checked by probe:
- An unknown VIN is pending on the first read and creates a vehicle on the second matching read. `getVehicleVIN` is re-queued with `delay=5`.
- A mis-heard VIN creates nothing (pending, pending, rejected, and it stays rejected). The INFO line is logged once, on the transition.
- A known VIN confirms on one read. That includes a VIN that became known while pending (probe 7).
- The anonymous vehicle `anon:<point>` is created at session start and merged on attribution: observations are copied with their original stamps, then the anon vehicle is removed. It is removed again at session end, and session end clears `twcVin` on the attributed car only. A car since re-attributed to another point is untouched (probe 5).

Focused run: `test_registry_plug_sessions.py`, `test_twcmaster_vin_confirmation.py` and `test_twcmaster.py` give 69 passed.

### Strengths

- Every registry decision is made under `_lock` with dict work only. `getOrCreate`, the merge observes and the INFO log all run after the lock is released (`VehicleRegistry.py:170-215`). Lock order holds: in `recordVehicleVIN` the registry call completes before `settingsLock` is taken (`TWCMaster.py:1445-1483`), so the two locks are never nested.
- Both serial-thread entry points wrap the registry call in `try/except Exception` with a warning (`TWCMaster.py:1429-1439`, `:1445-1449`). Verified by probe: if `observeTwcVin` raises, it does not propagate.
- A malformed VIN is rejected without consuming an attempt. The rejected state is sticky for the session and cleared by `endPlugSession`, so a new session counts afresh.
- `endPlugSession` deletes only a still-anonymous `anon:` entry. `_attributedTo` keys on the *latest* `twcVin`, so a car that moved TWCs is not detached by the old TWC's session end.
- Pure-Gen2 import safety checked:
  - `lib/TWCManager/Vehicle/` has no `__init__.py`.
  - `Vehicle/Registry/__init__.py` imports only `.VehicleRegistry` and `.Fields`.
  - Every Registry module imports only stdlib (`logging`, `math`, `re`, `threading`, `time`, `typing`) plus relative modules.
  - So the new module-level import in `TWCMaster.py:19` pulls in no provider or optional dependency.
- `settingsLock` on the serial thread is not new. The brief mandates it here, and the serial thread already takes it elsewhere (e.g. `TWCMaster.py:1532-1592`). Its holders do dict work; the longest is `saveSettings` serialising JSON. Nothing is nested under it on this path. The wait is bounded and acceptable.
- `recordVehicleSessionEnd` (`TWCMaster.py:1385-1396`) already guards `settings["Vehicles"].get(lastVIN)`, so a pending or rejected VIN that never got a history entry cannot KeyError at session close.

### Issues

**Critical:** none.

**Important:** none.

**Minor:**

1. **Risk (b) / concern 1: the premise is wrong, and the risk is negligible.** This is not the first serial-thread user of the delayed path. `TWCSlave.py:663-665` already queues `checkDeparture` with 300/1200/2700 s delays from the RX handler, and `TWCManager.py:820` queues `sunrise` with 30. A tie needs a new `now()+5s` to equal an existing entry's stamp to the microsecond. In practice that means a departure check queued exactly 295 s earlier to the µs, or two pending VINs in the same µs on a single sequential thread, so it is practically unreachable. If it did happen: `queue_background_task` at `TWCMaster.py:1451-1454` sits outside the try. The `TypeError` would leave `recordVehicleVIN` and reach the RX loop at `TWCManager.py:1561`, and be caught by the main-loop `except Exception` at `TWCManager.py:1981`. That costs a traceback and a 5 s `time.sleep`, which stalls heartbeats. It also skips that parse's `updateVINStatus` and `checkVINEntitlement` (`TWCManager.py:1564-1574`), and nothing re-queries afterwards. Cheap hardening, best done as a follow-up to `queue_background_task`, not this task: add a monotonic counter as the tuple's second element, e.g. `(when, next(self._delaySeq), task)`, with `pop(0)[2]` at `:358`. Alternatively, move the `queue_background_task` call inside the existing try.
2. **The confirmation read gets one shot.** On pending, `slaveTWC.currentVIN` is already set (`TWCManager.py:1553`), so `retryVINQuery` (`TWCMaster.py:1552-1570`, guarded by `not slaveTWC.currentVIN`) never re-queries. The re-query fails silently in three cases: the delayed `getVehicleVIN` is lost, one of its three part responses is lost, or the queue's per-cmd dedupe (`TWCMaster.py:1309-1315`) overwrites its `slaveTWC` with another TWC's in-flight `getVehicleVIN`. In each case the unknown VIN stays pending for the whole session. Effects: no registry vehicle, no `settings["Vehicles"]` session record, and no `vehicleIsDefinitelyHome` call (`TWCMaster.py:1500-1502`). A garbled response is still re-requested by the RX path (`TWCManager.py:1577-1585`), so only a *missing* response triggers this. The first read gets up to 6 retries at 60 s, so the confirmation read is weaker than the first. Phase 1 consequence: one session's history and home hint are lost. Later phases will care more, because an anonymous vehicle gets no vehicle commands. Fix options: let `retryVINQuery` also retry while the registry says the point is pending (e.g. a `registry.isPending(point)` check), or re-queue the delayed query on pending with a bounded count. Worth tracking for Phase 5 at least.
3. **Pure-Gen2 timing change (risk e).** The registry has no persistence until Task 8, so after every restart each VIN is "unknown" and its first session records 5-30 s later. The delayed list only drains when `getBackgroundTask` loops, so the gap is up to the 30 s `get` timeout (`TWCMaster.py:348-363`). That session also depends on item 2. Session counts per plug-in are otherwise unchanged from main: a known VIN is counted once per parse, as before, and an unknown VIN once on confirmation. Entitlement (`checkVINEntitlement`), `getTWCbyVIN` and VIN status still act on the first parse, as the brief requires. Acceptable as designed; noted for the Task 8 reviewer.
4. **For a first-seen VIN, `checkVINEntitlement` and `updateVINStatus` now run twice per session**, once per parse (`TWCManager.py:1564-1574`). Idempotent, so harmless. Noted only.
5. **Not serial-thread-only.** `num_cars_charging_now` is also called from `getStatus` (`TWCMaster.py:696`, reached from HTTP `/api/getStatus` via `HTTPControl.py:411`) and from `:926`. So `_plugSession` can run on an HTTP thread at the same time as the serial thread's `observeTwcVin`. The registry `_lock`, `Fields._lock` and `Vehicle._lock` keep this memory-safe. Begin and end are idempotent.

   There is one benign interleaving. An off-thread `endPlugSession` can run between `observeTwcVin`'s decision and its `twcVin=pointId` observe. The car is then left attributed to a point whose session has ended, until the next session end there. The race on `slaveTWC.isCharging` itself is pre-existing, so this is not a task defect. A whole-branch reviewer should know the registry has an off-serial caller.
6. **The anonymous vehicle leaks if a TWC disappears while charging.** `deleteSlaveTWC` (`TWCMaster.py:810`) never reaches `endPlugSession`. This is bounded by the number of TWCs, and real plug detection is Phase 5. Noted only.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation matches the brief and the spec's identity and phantom rules, and the serial-thread contract holds. Pure-Gen2 imports are verified stdlib-only.
- Registry work is lock-leaf dict operations, with no nested locks and no I/O.
- Both registry call sites are exception-guarded.
- Nothing waits. The re-query is a delayed enqueue, not a sleep.

The `bisect` tie (concern 1) is a pre-existing, practically unreachable hazard on an already-used path. The one real behavioural weakness is item 2: a lost confirmation response leaves the session unconfirmed. In Phase 1 that costs one session's history entry at most and nothing affects charging, so it is a follow-up rather than a blocker.
