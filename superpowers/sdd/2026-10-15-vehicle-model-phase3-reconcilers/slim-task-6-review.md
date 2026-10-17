# Slim Task 6 review: attempts on the vehicle command queue (39d7cfb..ff84ff3)

Reviewed at ff84ff3 in `scratchpad/wt-vm3`.

- Step 4 set: 162 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1455 passed, 1 xfailed.
- `test_vehicle_command_queue.py` and `test_registry_callers.py` are unchanged in the diff.

Stress probe: `scratchpad/probe-slim6/test_probe_workers.py`, 14 tests. It was adapted from `probe-p3t3` as follows:

- `Lanes` became `Workers`.
- The probe one-shot became a one-shot stop.
- The never-started tests now expect drop-at-once and `False`.
- The idle test now expects no timed waits.
- Four new probes were added:
  - a hung BLE command against cloud traffic;
  - a `BaseException` on a threaded worker;
  - the worker exit window, in two orderings;
  - a storm on the legacy queue.

The 12 tests other than the exit-window probes passed on all 3 runs. Both exit-window probes fail deterministically, and they record I1.

## Verdicts

- **Spec compliance: COMPLIANT.** Every interface in the brief is present:
  - `VehicleCommandQueue`: the keyword constructor, `put -> bool`, `remove`, `close`, `waitDrained`, `drain_high_priority`, `pending`, `busy`, `_entries` and `summary`;
  - `Provider.worker`;
  - `Run.py`: `entryKey`, `isStop`, `writtenValue`, `checked`, `RateLimits`, `runAttempt` and `Workers`;
  - `Order.debugCommand` on `master.workers`.

  All 25 listed tests were ported, both renames were made, the 3 named tests were deleted and the 6 new tests were added. All six deviations are **accepted**:
  1. `_run` as a method is needed because the queue does not know about `Outcome`.
  2. `clear` replaces `clearIf`, which does not exist yet.
  3. Registering TeslaBLE is required by the brief's own rule that an unregistered provider counts as cloud.
  4. A test was folded in with its assertions kept.
  5. There was nothing to change in `test_registry_callers.py`.
  6. Gating the drains with a one-shot wake is what the brief asked for.
- **Task quality: APPROVED WITH REQUIRED FIX.** Fix I1 before Task 7 starts, because Task 7 wires the shutdown drain. The fix is two lines plus a test. The Minor findings are optional, apart from M3's sentence, which Task 7 needs. The rest are notes or carry-forwards.

## Behaviour changes on the legacy instance

None of these can lose a live command in production, or change what a current user sees. Production sequence: `start()` at TWCManager.py:845; puts from the main loop, the web threads and the background thread; one `drain_high_priority(60)` at TWCManager.py:2055, after the main loop has exited.

- **`put` returns bool.** The only caller, TWCMaster.py:1414 `queue_vehicle_command`, discards it. No effect.
- **The 64-entry cap.** No legacy caller blocks on its callback. The callers are TWCSlave.py:99 (`done` only sets `vehicleRateRaised`), TWCMaster.py:1388 and VehicleEndpoint.py:155, the last two with no callback. So a dropped entry cannot hang anything.
  - Legacy keys are `(cmd, vin)` over 4 commands. Reaching 64 distinct pending keys would take about 16 or more cars with a stalled worker.
  - At the cap the oldest non-stop entry is dropped, and its callback is not called. That is the same fate as a replaced entry today, so callers already tolerate it.
  - Stops are never evicted by non-stops.
  - Before this change the queue was unbounded. Without the cap, a dead worker would leak memory, so this is an improvement.
- **The thread exits once it is closed and empty.** `close()` happens only inside `drain_high_priority` at shutdown.
  - A stop put afterwards is now rejected: `put` returns False and logs at DEBUG.
  - Before, it was queued on a thread the process was about to abandon. In practice the old code would almost never have sent it either, because `drain_high_priority` had already returned and the process was exiting.
  - Accepted. I1 covers the narrow window in which such a stop is accepted but never run.
- **An unstarted drain drops pending entries.** This happens only when startup died before `start()` at TWCManager.py:845. Nothing could ever have run them.
  - The old code waited the full 60 s and then returned False.
  - The new code returns False at once. This is an improvement: shutdown no longer burns 60 of systemd's 90 s.
  - Returning False when nothing was pending is cosmetic, because the caller ignores the value.
- **Callback errors are logged by type name.** Legacy callbacks lose their traceback (VehicleCommandQueue.py:137), and `put`'s key failure also logs only the type (line 148). This is a debuggability regression only; behaviour is unchanged. `_execute`'s own traceback, the common failure, is kept (line 316).

The probe's legacy storm confirmed this. Four submitters put 1,600 mixed commands with callbacks, one of which raised, while a canceller ran; this was followed by `drain_high_priority(20)`. The results:

- each callback ran at most once;
- the drain returned True;
- the thread joined;
- nothing was left pending;
- a stop put after the drain was rejected.

## Checked and fine

- **Report-once, except I1.** The storm probes (6 submitters × 400 attempts across 12 VINs, 2 cancellers, 3 concurrent drainers, a raising report, and random provider exceptions and bad returns) passed on all 3 runs. Every Attempt was reported exactly once, nothing extra was reported, nothing was left pending or running, every thread joined and the thread count did not grow. This covers:
  - replace (VehicleCommandQueue.py:162-166);
  - overflow drop (173-178);
  - cancel (194-205);
  - one-shot coalescing (`entryKey` gives each one-shot a fresh `n`);
  - drain: low on close (240-253), high on timeout (269-271);
  - an exception (`Workers._run` at Run.py:319-324; the queue's `BaseException` path at VehicleCommandQueue.py:328-332);
  - the stale-desire cancel (Run.py:192-197, a normal run result).
- **Never-started drain.** Three concurrent drains return False in under 2 s. Every entry is reported once as dropped, and no provider is called.
- **Nothing in flight / bounded / terminates / joins / no spin.**
  - The queue is capped at 64 per worker.
  - `waitDrained` waits on one monotonic deadline, and `Workers.drain` shares it across both workers (Run.py:385-392).
  - A drain with a hung attempt returns False in about 0.5 s, and the late report still arrives once.
  - The idle worker blocks in `wait_for` with no timeout, so the probe saw at most 1 wait in 2.5 s.
- **BLE cannot block cloud.** With a BLE stop hung, 11 cloud stops all ran and were reported within the poll window. `drain(0.5)` then returned False on time. `RateLimits` only calls `declarations()`, which is a pure dict for every real provider. `providerOrder.provider()` takes no lock.
- **The serial thread.**
  - A `local` attempt runs inline, and its read sources are filtered to `local`-worker providers. No real `ReadSource` belongs to Gen2TWC/Gen3TWC.
  - `Vehicle.read` with `sources=[]` cascades over an empty order (Vehicle.py:191-195), so no I/O happens.
  - No RS-485 I/O is added.
- **Locks.**
  - `_cond` is a leaf. `report`, `lost` and `callback` all run after it is released (`_lose` and `_deliver`).
  - The legacy `remove(match)` calls `match` under `_cond`, as `cancel` did before.
  - `RateLimits._lock` is a leaf, and `declarations()` is called outside it.
- **Cost.**
  - A failed wake on a non-local provider aborts (Run.py:242-246).
  - REFUSED aborts for every provider.
  - The stamp and `afterWrite` each have their own `try` after the command, so the outcome stands (271-296).
  - `note()` is called only immediately before `_call` (254). Read-satisfied and rules-settled attempts use no slot, which is tested.
  - A worker makes one provider call per attempt and never retries.
  - The read is `allowWake=False`.
- **Task 3 guarantees kept.** Task 3's I1 and I2 hold (see Cost above). Its M1 is moot, since there is no longer a concurrent runner. Its M3 (inline busy), M5/M7 (the `_monotonic` alias) and M6 (`BaseException`) are now handled. Its M2 is resolved by the note placement, and its M4 by monotonic drain deadlines.
- **Probe removal.**
  - No `probe`, `PROBE`, `noteProof` or `lanes` references remain in `lib` or `tests`.
  - TeslaBLE now notes key proof on every answered command, which is correct now that every command is signed.
  - The replacement breaker test drives the real breaker's recovery timeout, not a mock. That timeout is now the only way an open BLE breaker reopens.

## Critical

None.

## Important

**I1. A stop put in the worker's exit window is accepted, never runs and, depending on ordering, is never reported. This breaks report-once. VehicleCommandQueue.py:290-295, 345-362, 152.**

When a closed queue empties, `_next` returns None and releases `_cond`. `_live` is cleared later, in `_run`'s `finally`. A high `put` in that gap sees `_draining and _live`, so it is accepted (`put` returns True) into a queue whose thread is exiting. Both orderings were reproduced deterministically by widening the gap with a sleep:

- **The put lands before `waitDrained`** (probe `test_exit_window_put_of_a_stop_is_not_orphaned`).
  - `waitDrained(1.0)` holds for the full 1.0 s, returns False, and drops the stop as `dropped`.
  - There is one report, but nothing is sent, and the drain is held to its deadline.
- **The put lands after `waitDrained` has returned True** (probe `test_exit_window_put_after_drain_returned_is_reported_once`).
  - The stop is accepted and the thread exits. `pending()` stays at 1, and the stop is **never reported** (0 reports).
  - In `Workers.drain` (Run.py:391-392), this happens to any cloud stop submitted while `ble.waitDrained` is still waiting.

The real window is microseconds, and only at shutdown. On the legacy instance there is no report contract (`lost=None`), and the process is exiting anyway, so legacy users are unaffected. The finding is Important because it breaks the brief's "every entry the attempt instances accept is reported exactly once". By the Task 3 bar, an invariant break means fix before the next task, and Task 7 wires this drain.

**Fix:** in `_next`, when returning None, clear `_live` under the same lock (`self._live = False; self._cond.notify_all(); return None`). A racing put is then rejected and reported as `dropped`. Keep the `finally` for the exception path. Add a test that patches `_next` to sleep in the gap and asserts that a stop put there gives `put` False and one `dropped` report.

## Minor

**M2. A dead worker keeps accepting entries. VehicleCommandQueue.py:152-182, 345-362.**

- After a `BaseException` kills the thread (`_live` False, `_thread` set), `put` still accepts entries and returns True.
- They wait until the shutdown drain, which holds for its full timeout on any pending stop.
- The probe accepted 15 entries this way, and `drain(0.5)` took 0.5 s and returned False. Report-once held.

This is a daemon-thread corner case; Task 3 M6 called it academic.

**Fix (optional):** in `put`, treat `self._thread is not None and not self._live` like a closed queue (`lost(entry, "dropped")`, return False). Also, in `waitDrained`, skip the wait when the worker is not live.

**M3. The caller-thread rule from Task 3's carry-forward is not written down, and it now covers the DesiredStore lock. Run.py:9-12, 192-197, 363-376.**

The header says the report runs "on the worker's thread (or the submitter's, inline)". It does not say what else runs on the caller's thread:

- `replaced` and `dropped` reports from `submit`, and `cancelled` reports from `cancel`, run synchronously on the caller's thread.
- A `local` submit runs the whole of `runAttempt` on the caller's thread. That includes the new stale-desire guard's `master.desired.get()` and `beforeWrite`.

`DesiredStore._lock` is a plain `threading.Lock` (Desired.py:284). Calling `Workers.submit` or `Workers.cancel` while holding it is therefore an immediate self-deadlock. For a Gen2/Gen3 TWC, that deadlock is on the serial thread. The Task 3 review asked for this rule to be stated in Task 6.

**Fix:** state it in the Run.py header and the `submit`/`cancel` docstrings: never call either while holding the DesiredStore lock or any lock that the report handler takes. Task 7 must follow it.

**M4. Tracebacks are lost on legacy callback and key failures. VehicleCommandQueue.py:137, 148, 121.** Before, these logged `traceback.format_exc()`; now they log the type name only. Also, the legacy drop-while-draining DEBUG line no longer prints the task (`%r`). This is consistent with the new rule, but the legacy path's tasks and callbacks carry no tokens.

**Fix (optional):** for `self._legacy`, also log the traceback at DEBUG.

## Notes and carry-forwards

- **Task 7 (stale-desire guard).** Run.py:196 compares `want.value != attempt.value`. Task 7 must build every aspect attempt with `value` equal to the stored `Desired.value` (unclamped, unconverted). Otherwise every such attempt cancels itself. Adjust the value in `beforeWrite`, as now, not in the Attempt.
- **Task 7 (start before submit).** `Workers.start()` must run before the first submit. A never-started worker only queues, and a drain then drops everything with `False`.
- **Task 7 (`probeInFlight`).** `ControlState.probeInFlight` (Desired.py:256, 563) is dead and appears in the summary. Remove it in Task 7's rewrite, as the report says.
- **Task 13 (lane wording).** Rename the "lane" wording and `LANE_DETAILS`.
- **Budget.** The report's line-budget concern (664 of 1,400 lines added) is for the coordinator to re-forecast. It is not a quality issue: Run.py is a near-verbatim port plus the requested additions.
- **Deviation 1.** `Workers._run` makes `_report`'s `BaseException` branch (Run.py:327-328) reachable only through the queue's `BaseException` path. It is correct and tested both inline (`test_base_exception_in_a_run_still_reports_and_clears_busy`) and threaded (probe).
