# Task 3 re-review 1: fix round 1 (43886b9..97377b8)

**Verdict: APPROVED.** I1, I2, M1, M3, M5, M7 and M8 are all addressed. Nothing new at Important or above.

The coordinator has deferred M2, M4 and M6 and folded M9 into Task 6, so they are not raised here.

## Evidence

Run at 97377b8, three times with the capped command: `probe-p3t3/test_probe_lanes.py`, `tests/unit/test_lanes.py` and `tests/unit/test_provider_order.py`. All three runs gave 68 passed.

The probe ran with its strict assertions on:
- concurrent drains of a never-started lane give `res == [True]*3`;
- `maxInflight <= 1` for BLE and Fleet;
- report-once and nothing pending or `_running`;
- threads joined.

I added two probes for this round:
- `test_never_started_slow_concurrent_drains_one_runner`: four drainers on slow providers. All returned True, there was one runner and every attempt was reported once.
- `test_never_started_drain_timeouts_while_another_runs_report_once`: three drainers time out at 0.3 s while a fourth is the runner on a stop that hangs. The short drains return False within 3 s, and the stops they drop are reported once. The runner's attempts are also reported once, and nothing is left pending.

## Findings

**I1: addressed.** Lanes.py:189-237. The command runs inside the main `try`. The stamp and `afterWrite` each have their own `try`, log by type name at WARNING, and leave `outcome` unchanged. The tests cover a raising `noteWrite`, a raising `cost` and a raising `afterWrite`. The last one is the first test of the hooks path. Each gives DONE with a single call.

**I2: addressed.** Lanes.py:172-186 and `_WAKE_PROCEEDS`. A non-local provider sends the command only after a DONE, SATISFIED or UNSUPPORTED wake. REFUSED aborts for every provider. A local provider still sends after any other failed wake. Tests cover a Fleet wake that returns `ERROR "500"`, one that returns a bare `True`, the three proceeding kinds, and a BLE wake that returns ERROR.

**M1: addressed.** In the never-started `_finishDrain`, a drainer waits while `_running` is set and the runner calls `notify_all`. A drainer that times out pops the remaining stops under the lock and reports each one. The runner then finds the queue empty and stops, so nothing is reported twice. The wait's timeout can be at or below 0 near the deadline, which `Condition.wait` handles as a non-blocking acquire, so the loop does not spin.

**M3: addressed.** An inline submit sets `_running` and clears it only if it is still that attempt.

**M5: addressed.** The join is now `min(WAIT, max(0.1, remaining))`.

**M7: addressed.** `_monotonic` is an alias, and the test patches the alias.

**M8: addressed.** The asserts are out of `finally`, the Timer is joined, and the I1 and I2 tests exist.

## New Minor (no action needed)

- **N1. The inline submit's `finally` clears `_running` without `notify_all`.** Lanes.py, inline `submit`. The only waiter this could affect is a drain of a `Lanes(inline=True)` lane during an inline run, which happens only in tests. That drainer waits at most `WAIT` (1 s) longer. Fix if wanted: call `self._cond.notify_all()` beside the clear.
- **N2. `busy` can read False while an overlapping inline call is still running.** With two overlapping inline callers, the one that finishes first may clear `_running` while the other is still running. This is documented ("the latest one") and cosmetic.
