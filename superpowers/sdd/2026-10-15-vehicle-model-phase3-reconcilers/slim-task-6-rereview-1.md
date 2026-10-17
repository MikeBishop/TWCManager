# Slim Task 6 re-review 1: fix round 1 (ff84ff3..163d8c1)

**Verdict: APPROVED.** I1 is fixed, as are M2, M3 and M4. Nothing new at Important or above.

## Evidence

Run at 163d8c1 in `scratchpad/wt-vm3`, with the capped pytest command throughout.

**Probe:** `scratchpad/probe-slim6/test_probe_workers.py`.
- All 14 original tests pass on each of 3 runs (14 passed per run). This includes both exit-window probes, which failed at ff84ff3.
- The exit-window probes now print:
  - put first: `accepted False drain True took 0.0 reports 1 sent []`;
  - put after drain: `accepted False reports 1 pending 0`.
- The dead-worker probe now prints `accepted 0 drain True took 0.0`. Every entry is still reported once.

**New probe for this round:** `test_idle_healthy_worker_never_reads_as_dead`.
- A started worker goes through repeated idle gaps of 50 ms while a noise thread calls `notify_all` on its condition every 0.2 ms to force spurious wake-ups.
- All 200 puts are accepted and `_live` stays True throughout.
- The drain returns True, and every entry is reported once.
- With it, the probe file is 15 passed on each of 3 runs.

**Repo tests:** `test_workers.py`, `test_vehicle_command_queue.py` and `test_sigterm_shutdown.py`: 70 passed.

## Findings

**I1: addressed.** VehicleCommandQueue.py, `_next`.
- `_live = False` is now set under `_cond` in the same critical section that finds the closed queue empty. `put` reads `_live` under the same lock.
- So any put is ordered one of two ways:
  - before that check: `_next`'s `wait_for` predicate sees the entry and runs it;
  - after it: `dead` is True, and the put is rejected and reported `dropped` once.
- Both orderings are covered by the new parametrized test and by the probe.

**No deadlock from `notify_all`.** `notify_all` must be called with the condition's lock held, and `_cond` is a leaf: no other lock is taken and no callback runs under it. The drain waiters in `waitDrained` re-check `not _high and not _busy`, which is already true at that point, so they return.

**The dead-worker reject cannot misfire on a healthy, idle worker.** `_live` is cleared in only two places:
- `_next`, which can only get past its `wait_for` with an empty queue when `_draining` is set, that is, after `close()`. A spurious wake-up re-tests the predicate.
- `_run`'s `finally`, when the thread exits.

`start()` sets `_live` True under the lock before the thread exists. A healthy idle worker that has not been closed therefore always has `_live` True; the noise probe confirms this. `inline` instances are excluded explicitly.

**M2: addressed.** `put` rejects an entry when the worker has died or exited. `waitDrained` on a worker that is not live returns at once and drops whatever is pending. When nothing is pending, it returns True.
- The `BaseException` ordering is safe. `_runOne`'s `finally` clears `busy` before the exception reaches `_run`'s `finally`. Until then `_live` is still True, so a concurrent `waitDrained` takes the waiting branch, whose predicate is already satisfied.

**M3: addressed.** The Run.py header now states which reports run on the caller's thread, including the whole of `runAttempt` for inline and local attempts, `DesiredStore.get` included. It also states the rule: never call `submit` or `cancel` while holding the DesiredStore lock. `submit` and `cancel` each point to the header.

**M4: addressed.** `_logFailure` logs the type name at WARNING and the traceback at DEBUG. The DEBUG line for a legacy task dropped while draining no longer shows the task (`%r`). The report says so explicitly, and I accept that.

## New Minor (no action needed)

**N1. A failed `Thread.start()` leaves a dead queue that looks live. `start()`.**
- `_live` is set True before `self._thread.start()`, which runs outside the lock. If `start()` raises (`RuntimeError: can't start new thread`), the queue has `_thread` set and `_live` True but no running thread.
- Puts are then accepted, and the drain waits its full deadline before dropping and reporting them. Report-once still holds.
- This predates this round and needs resource exhaustion at startup.

**Fix if wanted:** wrap `self._thread.start()` in a `try` that clears `_live` under the lock and re-raises.

**N2. A dead legacy worker's drain drops its pending stops instead of keeping them.** `waitDrained` now drops pending stops when `not self._live`, on the legacy instance too.
- Before, it logged a WARNING listing the stops it kept. Now it logs an INFO count, and each dropped stop at DEBUG.
- This is only at shutdown, behind a worker that has already died, so nothing could have run them anyway. It is cosmetic.
