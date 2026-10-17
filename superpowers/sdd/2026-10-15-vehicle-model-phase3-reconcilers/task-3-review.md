# Task 3 review: Lanes (9a44495..43886b9)

Reviewed at 43886b9 in wt-vm3. Step 4 set: 108 passed. Stress probe:
`scratchpad/probe-p3t3/test_probe_lanes.py`, 9 tests, passed on 3 runs. One
assertion was relaxed to record finding M1.

## Verdicts

- **Spec compliance: COMPLIANT.** Every interface in the brief is present: `LANE_PROVIDERS`, `entryKey`, `Lane`, `runAttempt`, `Lanes`, the `Provider` command methods, `PROBE`/`commandMethod`, and `debugCommand`. The brief's tests are verbatim, and the Step 4 set passes. The `_run` deviation is **accepted** (see below).
- **Task quality: APPROVED WITH REQUIRED FIXES.** Fix I1 and I2 before Task 4 starts. Fold M1 into the same pass, because it is cheap. Everything else is a note or a carry-forward.

## Deviation: the lane thread exits only once closed and empty: accepted

`Lanes.drain` closes the lane, and `Lane._finishDrain` sets `_stopping`. The brief's literal `while not self._stopping` would therefore let a started lane's thread exit with its pending stops unrun. That would defeat the purpose of the drain.

The implementation (Lanes.py:446-467) keeps the brief's intent, and every exit still terminates:

- `stop()` sets both flags and empties the queue (Lanes.py:469-477).
- A drain timeout empties the queue, sets `_stopping` and notifies (Lanes.py:522-530).
- An idle thread waits at most `WAIT` = 1.0 s per pass. The probe saw at most 3 waits in 2.5 s idle, with no spin.
- A hung running attempt holds only its own thread. The drain returns False on time, and the late report still arrives exactly once (probe `test_drain_timeout_with_hung_attempt_still_reports_once`).

## Probe results

These hold for started lanes, with 6 submitters x 400 mixed attempts (stops, starts, amps, limits, probes and one-shots across 12 VINs and 5 provider names), 2 cancellers, 3 concurrent drainers, a raising report callback and random provider exceptions or bad returns:

- Every submitted Attempt object was reported exactly once.
- No extra reports.
- Nothing pending and nothing `_running` afterwards.
- Every lane thread joined.
- `threading.active_count()` did not grow.
- No provider ever had two attempts in flight on a started lane.
- The queue never exceeded `MAX_PENDING`.

## Critical

None.

## Important

**I1. An exception after a successful command turns a sent DONE into a retryable ERROR. This is a paid retry. Lanes.py:176-199.**

The stamp (`provider.cost`, `vehicle.noteWrite`) and `hooks.afterWrite` sit in the same `try` as the command. Any raise after `_call` returns is reported as `Outcome(ERROR, <type>)`, which is in `RETRYABLE`. The reconciler will then re-send a command that has already taken effect. For Fleet, that is a second billed command.

`afterWrite` "saves a held limit" (Task 6). It is the realistic raiser, but `noteWrite` and `cost` can raise too. The report's Concern 4 left this path untested, so it does not appear among the concerns.

**Fix:** once `outcome` exists, run the stamp and `afterWrite` in their own `try/except Exception`:

```python
try:
    ...stamp...
    if hooks is not None:
        hooks.afterWrite(vehicle, attempt, outcome)
except Exception as e:
    logger.warning("Lane %s: after-write for %s raised %s", lane.name, attempt.capability, type(e).__name__)
return outcome
```

Add a test in which `noteWrite` raises after a DONE command and the report is still DONE.

**I2. A failed billed wake other than REFUSED or UNREACHABLE still sends the billed command. Lanes.py:165-175.**

Only `REFUSED` and a non-local `UNREACHABLE` abort. Each of these goes on to the command:

- a Fleet wake that returns `ERROR` (for example a 5xx, or anything Task 5's `wakeOutcome` classifies as an error);
- a wake with a bad return (which today covers every real provider: `ERROR "bad return bool"`).

The car is probably still asleep, so the command fails and is billed. The brief lists only the two kinds, so this is spec-compliant. It still breaks the cost rule that a failed billed wake aborts the command.

**Fix:** for a non-local provider, abort on any wake outcome outside `SETTLED | {UNSUPPORTED}`, that is, `if not provider.local and woke.kind not in (DONE, SATISFIED, UNSUPPORTED): return woke`. Keep today's local behaviour, where only REFUSED aborts. Add a test: a Fleet wake that returns `ERROR` gives `calls == ["wake"]`.

## Minor

**M1. Concurrent drains of a never-started lane. Lanes.py:501-514, 522-523. The probe reproduced this on 4 of 6 runs.**

- (a) Drainer B finds the queue empty while drainer A is still running the last stop. B breaks, sees `_running` set, and returns **False** although nothing was dropped.
- (b) Several drainers pop and run stops on their own threads at the same time. The probe measured `maxInflight` = 3 for TeslaBLE and FleetAPI, which breaks the one-runner-per-lane rule.

Report-once still held. This is not a production path: there is one drain, at shutdown, on a started lane.

**Fix:** in the never-started loop, when `_running is not None`, `wait` on the condition until the deadline instead of popping. Before computing `finished`, wait for `_running` to clear until the deadline, as the started branch already does.

**M2. The read-satisfied path uses a rate slot. Lanes.py:130.** `lane.note` runs before the read and the satisfied check, and before a `beforeWrite` early return. An attempt that sends no command still uses a `(provider, capability, VIN)` slot. Under Track Green Energy with Fleet's 50-per-minute amps limit, satisfied attempts can throttle real ones.

This follows the order in the brief, and the report records it.

**Fix (needs a plan ruling):** call `note` immediately before the wake or command.

**M3. Inline lanes always report `busy` False.** `Lane.submit`'s inline path (Lanes.py:298-305) never sets `_running`, so `busy` is False and `summary()["running"]` is None during an inline run. **Fix:** set and clear `_running` around the inline `_runOne`, or document that `busy` covers threaded lanes only.

**M4. A backward wall-clock step during a drain. Lanes.py:518, 543, 616.** The drain deadline is on `time.time`, as the one-clock rule requires. If the clock steps backwards while a running attempt is hung, `remaining` grows and SIGTERM is held until the attempt returns. The report already flags this. Leave the decision to whoever owns the clock rule.

**M5. A finished drain can return before its thread has exited. Lanes.py:539.** The join is bounded by the time left. When the drain finishes at its deadline it joins for 0 s, so the thread may still be exiting when `drain` returns True. The threads are joinable but not always joined. **Fix (optional):** join for `min(WAIT, max(0.1, remaining))`.

**M6. `BaseException` on a lane thread. Lanes.py:288.** `_runOne` catches only `Exception`. A `SystemExit` or `KeyboardInterrupt` raised inside a provider kills the thread with the entry unreported. A later drain still drops and reports the queued entries. The threads are daemon threads, so this is academic. Note it only.

**M7. Fragile test patching. test_lanes.py:56.** `monkeypatch.setattr(L.time, "monotonic", ...)` patches the global `time` module for the whole process. It is safe only because that test is inline. **Fix:** add a `_monotonic = time.monotonic` alias in `Lanes.py`, call it from `allows`/`note`, and patch the alias.

**M8. Test hygiene in test_lanes.py.**
- The asserts at lines 126-127 sit in a `finally`, so a failure there masks the body's own failure.
- The `threading.Timer` at line 153 is never joined.
- No test covers a Fleet wake that returns `ERROR` (see I2) or a raising after-write (see I1).

**M9. The placeholder `_satisfied` can never satisfy CHARGING. Lanes.py:88-89.** It compares `believed.value == desired`, which for CHARGING compares `"Charging"` with `True`. A CHARGING attempt is never satisfied by the read until Task 6's `satisfied` lands. This is acceptable for a placeholder, but Task 6 must replace it (see Concern 5).

## Carry-forwards (beyond the report's Concerns 3-5)

- **Task 6/7:** `submit` and `cancel` deliver the replaced, dropped and cancelled reports synchronously on the *caller's* thread. The reconciler must never call `submit` or `cancel` while holding the DesiredStore lock if its report handler takes that lock. Otherwise it self-deadlocks, unless the lock is an RLock. State this rule in Task 6.
- **Task 6:** the lane does not enforce `allows`; it only records calls. Checking `allows` and then calling `submit` is not atomic, so the reconciler is the rate-limit gate.
- **Task 6:** a report callback that calls `drain` from the lane thread waits on its own `_running` until the timeout. This is benign, but do not do it.
- **Task 7:** until `Lanes.start()` runs, a production lane only queues: up to 64 entries, then the oldest is dropped. Task 7 must start the lanes before the first submit, and drain on SIGTERM from a non-serial thread.

## Checked and fine

- **Report-once.** It holds on every path: run, replaced, dropped (overflow, closed, drain, stop, drain timeout), cancelled, and exceptions (including a raising report callback). Losers are delivered outside the lock.
- **Queue.** It is bounded at 64. Stops go to the front, first-in-first-out among the stops. The oldest non-stop is the victim. A lane full of stops rejects the newcomer and reports it.
- **Lock.** The lane `Condition` is a leaf. Nothing else is acquired under it, and no I/O, `declarations()`, `runAttempt` or report runs under it.
- **Serial thread.** The local lane's read uses `sources` filtered to the TWC providers. No real `ReadSource` has `provider` Gen2TWC or Gen3TWC, so it fetches nothing. TWC providers only publish requests. `debugCommand` excludes providers with `module is None`, as `dispatch` did (Order.py:146). All real non-TWC providers set `module`.
- **Clock.** Attempts and stamps use `time.time`. Only the rate window uses `time.monotonic`. A production-clock threaded test exists (test_lanes.py:103-127).
- **Cost rules.**
  - There is no retry inside a lane.
  - The rate window is keyed by `(provider.name, capability, vin)`.
  - A REFUSED wake, or an UNREACHABLE wake from a billed provider, aborts. A failed local wake proceeds.
  - A disruptive stop is not stamped. A SATISFIED start or stop is not stamped.
- **`cancel(key)`** removes pending stops only, and leaves a running attempt alone.
- **Debug path.** One provider, `wake=False`, `maxAge=None` and a unique `entryKey`, so it makes a single attempt with no read and no fall-through.
- **Logging.** Exceptions and a raising report are logged by type name only. A bad-return WARNING appears once per provider and method. No tokens appear in the logs; the tests assert this.
- **Tests.** The threaded tests gate on Events, not sleeps. Every join has a timeout.
