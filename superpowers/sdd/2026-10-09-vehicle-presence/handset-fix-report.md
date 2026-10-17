# Hand-set charge-limit fix: report

Status: DONE

## Commits
- cfc59d6 TeslaBLE reads the car's charge limit before setting it
- 4efa266 Pushed arrivals carry the telemetry charge limit

## 1. TeslaBLE reads before it writes (cfc59d6)
- New `TeslaBLE._readChargeLimit(vin)`: calls `get_charge_state`, returns a positive int or None (exceptions, missing or non-int values all become None).
- `applyChargeLimit`, after the wake and before `charging-set-limit`:
  - read failed (None): behaviour unchanged (normal = saved outside, or target on first apply).
  - no saved entry, or lastApplied == -1: normal = current.
  - saved, current != lastApplied: hand-set; INFO log, normal = current.
  - restore: send `outside` only if current == lastApplied; otherwise save (current, -1), set dedupe (so a policy-wide restore does not wake it every pass), count it as success, and send nothing.
  - current already at target: no command; same success, save and dedupe path as a sent command.
- Lock: `applyChargeLimit` is not `@_serialized`, and nothing on its call path holds `_bleLock` between commands (wake/sendCommand take it per call). So `get_charge_state` (which takes `_bleLock` through `_fetch_state_json`) is called directly. `_fetch_state_locked` was deliberately not used: it would run without the lock and skip `_reportContact`.
- Tests (test_teslable_presence.py, TestReadsBeforeWriting, plus 3 existing tests updated to expect the `state charge` read): first apply saves the real limit; a hand change is adopted, then the policy limit is set; an unchanged limit keeps the saved normal; already at target sends nothing and dedupes; restore sends when ours is still set; restore skips a hand-set limit (and dedupes); restore when already at normal; a failed read keeps the old apply and restore behaviour; the real-lock thread test shows no deadlock, every call (the read included) runs under the lock, and the lock is free afterwards.

## 2. Pushed arrivals carry the limit (4efa266)
- `PresenceSources.telemetryLimit(master)` -> `lookup(vin)`: uses `_apiVehicle`, needs syncSource != "TeslaAPI" and chargeLimit a positive int (bools rejected). No I/O.
- `VehiclePresence(limitLookup=None)` defaults to `telemetryLimit(master)`. In `_runHandler` (no lock held), when a handler will run and limit is None, the lookup fills it. Exceptions are logged at debug, and the handler still runs with None. A limit from a probe is never replaced.
- Tests: TestTelemetryLimit (sources), plus TestPushedTransitionLimit (presence): location/contact/proof transitions carry the looked-up limit; a probed limit is kept; a failing lookup still runs the handler; the lookup runs without the presence lock; end to end, a TeslaMate arrival through the real lookup and real arrivalHandler adopts the hand-set 80 (save (80, 70)) and queues the policy limit.

## Tests
Full suite: 733 passed, 1 warning (pre-existing). black --check clean.
Baseline when I started was 706, not the 500 in global-constraints.md (the counts there are out of date).

## Concerns
- Every non-deduped BLE apply now runs one more tesla-control call (`state charge`) after the wake, about one command timeout extra in the worst case.
- The BLE read is single-shot. `get_charge_state` is not wrapped in `_execute_with_retry`. One transient failure falls back to the old path, and for that one apply the old bug comes back: the first apply saves the target as outside, or a hand-set limit is overwritten without being adopted. The spec requires that a failed read never blocks, so this is by design, but the fix is best-effort per apply.
- Departure regression risk (the main one). Before this change, a pushed (TeslaMate) departure passed None and the restore was always queued. Now, if TeslaMate's chargeLimit is stale (for example it still shows the old normal and not the limit we set over BLE), `departureHandler` sees currentLimit != lastApplied. It logs "hand-set; keeping it", saves (stale, -1) and skips the restore. The car leaves at the policy limit, and the saved normal is overwritten with the stale value. The missed restore cannot be recovered. Consider applying the lookup to arrivals only. On arrival, a stale value is corrected for BLE cars by the read at apply time.
- The BLE restore removes the saved entry, while the hand-set skip saves (current, -1), matching TeslaAPI. Both are handled on the next apply.
- When a restore finds a hand-set limit, two INFO lines are logged (the adoption, then "not restoring").
- The Co-Authored-By trailer is Claude Opus 5.5, per the dispatch brief, not the Fable line in global-constraints.md.

---

# Follow-ups

## Commits
- b6722c2 Fill in the telemetry charge limit for arrivals only
- 4cb6a43 Evidence the car is present closes TeslaBLE's circuit breaker
- efb8a14 TeslaBLE skips the pre-write read while the circuit breaker is open

## 1. Telemetry limit for arrivals only (b6722c2)
`VehiclePresence._runHandler` runs `limitLookup` only when `new == HOME` and the limit is None. Departures keep None, as before this branch. Tests:
- a pushed departure passes None and never calls the lookup, even when telemetry has a limit;
- end to end with the real lookup and the real departureHandler, a TeslaMate departure with a stale limit (90 while we hold 70) still queues the remoteOnly restore and does not overwrite the normal.

## 2. Presence evidence closes the BLE circuit breaker (4cb6a43)
- `BLECircuitBreaker.reset(vin)` pops the `failures` and `failure_times` entries. `TeslaBLE.resetCircuitBreaker(vin)` is the public wrapper.
- (a) `TeslaBLE._reportContact(vin, True)` (a probe, state read or command the car answered) calls `circuit_breaker.record_success(vin)`. It runs under `_bleLock`. That is fine, since the breaker is plain dicts.
- (b) `PresenceHandlers.homeProofHandler` with `source == "twc"` calls `TeslaBLE.resetCircuitBreaker(vin)` before the TeslaAPI reconcile. It is guarded for TeslaBLE not being loaded, and any exception is caught (debug log), so the reconcile still runs. It runs on the presence thread, outside the presence lock. **It takes no BLE lock: the breaker is plain dicts.** That is a benign race with a BLE command recording a failure at the same moment (in the worst case one failure is counted against the cleared state).
- Tests:
  - a successful probe or state read closes an open breaker;
  - a failed contact leaves it open;
  - contact for one VIN leaves others alone;
  - reset clears only that VIN (the status becomes "closed"), and an unknown VIN is harmless;
  - reset completes while another thread holds `_bleLock`;
  - the handler resets on a twc proof, not on other sources, does nothing without TeslaBLE, and still reconciles when the reset raises.

## 3. Why about 3 "Apply charge limit 50% result" lines per 30 s tick (investigation only)
Cause: **the VehiclePriority retry**, not several queued commands and not a policy re-queue.
- `Policy.py:255` queues one `{"cmd": "applyChargeLimit", "limit": limit}` per policy check (`policyCheckInterval = 30`, Policy.py:88). `TWCMaster.queue_background_task` (TWCMaster.py:1285) routes it to `VehicleCommandQueue.put`. That coalesces per key `("applyChargeLimit", None)` (VehicleCommandQueue.py:55-61, 89-90), so it is at most one pending policy-wide apply. A single task.
- The worker calls `VehiclePriority.applyChargeLimit` (VehiclePriority.py:85) → `_dispatch`. TeslaBLE has priority 20 (`TWCMaster.calculateModulePriority`, TWCMaster.py:163-164). `_calculate_retries` gives `20 // 10 = 2` (VehiclePriority.py:83), so `max_attempts = 3`. `_dispatch` calls `TeslaBLE.applyChargeLimit` up to 3 times while it returns False (VehiclePriority.py:156 `max_attempts = retries + 1`, VehiclePriority.py:163 `for attempt in range(max_attempts)`). Then it falls to TeslaAPI (priority 10, 2 attempts) unless commandPolicy is ble_only.
- Each TeslaBLE attempt goes as follows. The breaker is open, so `_execute_with_retry` returns None at once for wake and for charging-set-limit (TeslaBLE.py:1336-1339, "Circuit breaker OPEN" warning). The attempt logs "Apply charge limit 50% result: 0/1 attempted vehicles succeeded" (TeslaBLE.py:902) and returns False. There are 3 attempts, so 3 lines per tick, all near-instant. The dedupe (`_stopTryingToApplyLimit`) never latches because nothing succeeds.
- Possible fixes (not done): VehiclePriority could stop retrying a module whose failure is a breaker-open fast-fail. Or TeslaBLE.applyChargeLimit could skip a VIN whose breaker is open, without counting an attempt, and return False once without logging the result line. Or retries could be skipped for the policy-wide apply.
- **Side effect of my first commit, relevant here:** the new pre-write read (`get_charge_state` → `_fetch_state_json`) is not breaker-gated, because it does not go through `_execute_with_retry`. So while the breaker is open, each of the 3 attempts now runs a real `state charge` call. That can cost up to `commandTimeout` (5 s) each when the car is out of range. On the plus side, if the car answers, 4cb6a43 makes that read close the breaker. Fixed in efb8a14: `_readChargeLimit` returns None while the breaker is open for that VIN (the pre-read behaviour). It is a regression fix for cfc59d6, not a change to the retry count. Tests: with an open breaker no tesla-control call runs at all; the gating is per VIN.

## Tests
Full suite: 748 passed, 1 warning (pre-existing). black --check clean.
