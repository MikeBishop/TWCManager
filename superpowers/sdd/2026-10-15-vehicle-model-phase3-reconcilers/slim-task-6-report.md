# Slim Task 6 report: attempts on the vehicle command queue as two workers (BLE and cloud)

**Status:** DONE
**Base:** 39d7cfb. **Commit:** ff84ff3 on `vehicle-model/phase3` (worktree `scratchpad/wt-vm3`). Git status is clean, nothing pushed or stashed.

## What changed

- `lib/TWCManager/VehicleCommandQueue.py` is now generic:
  - `MAX_PENDING = 64`.
  - The keyword-only constructor takes `name/run/key/isHigh/report/lost/inline`.
  - `put` returns a bool. It replaces in place, so a replacement keeps its position (the legacy coalescing order depends on this). It drops the oldest low entry when full, with one WARNING per backlog. A queue full of high entries rejects the newcomer. While draining it rejects non-high entries, and also high entries when no worker can run them. With `inline=True` it runs the entry on the caller's thread.
  - New methods: `remove(match)`; `cancel(cmd, match)`, a legacy wrapper over `remove`; `close()`; `waitDrained(monotonicDeadline)`; `drain_high_priority = close + waitDrained`; `pending()`, `busy`, `_entries()`, `summary()`.
  - The callback, then `report`, run outside `_cond` and before `busy` clears. On a BaseException, `report` is still called and `busy` cleared, then the exception is re-raised.
  - The worker thread exits once it is closed and empty.
  - The legacy `_DISPATCH`, `_key` and `_is_high_priority` are kept for `run=None`.
- New `lib/TWCManager/Vehicle/Reconcile/Run.py`:
  - `entryKey`, `isStop`, `writtenValue` and `checked` (warn once per (provider, method)).
  - `RateLimits`: window key is `(provider, aspect or capability, vin)`, the clock is `time.monotonic` behind the patchable `_monotonic`, and the lock is a leaf.
  - `runAttempt(master, attempt, rateLimits)`:
    - stale-desire guard, which applies only to a real `DesiredStore`;
    - read sources chosen by the provider's `worker` (an unregistered provider counts as `cloud`);
    - `"rules: "` and `"wake "` detail tags;
    - `note()` only immediately before the command method;
    - no probe branch;
    - the I1/I2 guarantees and the lazy Reconciler-import fallback are unchanged.
  - `Workers`:
    - `ble` and `cloud` are `VehicleCommandQueue`s; `local` runs inline.
    - Public methods: `submit`, `cancel` (pending stops only), `allows`, `start`, `drain` (closes both, then one shared monotonic deadline, cloud then BLE), `pending`, `summary` and `setReport`.
- Deleted `Reconcile/Lanes.py`, `Provider.PROBE`, `Provider.probe`, `TeslaBLEProvider.probe`, `TeslaBLE.probe` and the `noteProof` parameter of `_sendCommand_internal`. `TeslaBLE` now notes key proof on every answered command.
- `Provider.worker = "cloud"`. TeslaBLE is `"ble"`; Gen2TWC and Gen3TWC are `"local"`. `Order.debugCommand` submits to `master.workers` and returns False when there are none. The Outcome.py comment no longer mentions the probe.
- Tests:
  - `git mv test_lanes.py test_workers.py` (33 tests): the 25 listed ports, the two renames and the six new tests.
  - `reconcile_helpers.ScriptedProvider` gets a `worker` derived from its name, with a `worker=` override; `probe` is removed.
  - Updated `test_provider_order.py`, `test_carapivehicle_registry.py` and `test_provider_outcomes_local.py`:
    - the probe test is deleted;
    - the probe assertions are dropped from three tests;
    - the breaker test is replaced by `test_an_open_breaker_half_opens_after_recovery_and_a_successful_command_closes_it`;
    - `test_a_failing_command_or_probe_logs_...` is renamed `test_a_failing_command_logs_...`.
  - `test_vehicle_command_queue.py` is unchanged and passes.

## TDD

Fail-before (Step 2), `tests/unit/test_workers.py`:
`E   ImportError: cannot import name 'Run' from 'TWCManager.Vehicle.Reconcile'`
This is an ImportError, not the brief's `ModuleNotFoundError`, because the test imports `Run` as a name from the package.

## Tests

- Step 4 list (9 files): **162 passed**.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1455 passed, 1 xfailed, 1 warning**. The baseline was 1454 passed at 39d7cfb.
  - The warning's summary is suppressed by the pytest config. It is not a thread exception from the touched files: `test_workers.py` and `test_vehicle_command_queue.py` passed 5 times out of 5 with `-W error::pytest.PytestUnhandledThreadExceptionWarning`.
  - I presume the warning was already there before this task.
- Every thread test joins with a 5 s timeout and asserts the thread is dead.

## Lib line delta

`git diff --stat 39d7cfb -- lib | tail -1` → `10 files changed, 664 insertions(+), 800 deletions(-)` (net −136).

## Deviations from the brief

1. **`Workers` passes a `_run` method as the queue's `run=`**, not the bare lambda. The queue does not import `Outcome`, so `_run` turns an Exception into `Outcome(ERROR, <type>)`. `_report` turns a BaseException, or any non-Outcome result, into an ERROR outcome.
2. **`DesiredStore.clearIf` does not exist at 39d7cfb.** The M7 test uses `clear(VIN, CHARGING)` instead. It also has a positive control: once the desire is set again, the start runs and reads once.
3. **`test_read_before_write_uses_only_the_lane_s_own_sources` now registers a TeslaBLE provider.** Under the new rule a source from an unregistered provider counts as cloud, so with only Fleet registered the BLE source would have been read. The test also asserts that an unregistered source is used by the cloud worker.
4. **`test_rate_limit_per_provider_capability_and_vin` was on neither list.** Its per-VIN and 61 s expiry assertions are folded into `test_rate_slot_is_used_only_when_a_command_is_sent`. That test checks that a read-satisfied attempt and a rules-settled attempt (detail `"rules: held"`) use no slot.
5. **`test_registry_callers.py` had no lanes reference**, so it is unchanged.
6. **The two drain tests now gate a started worker** with a one-shot wake that blocks and records no call. Their report assertions therefore include that wake's DONE.

## Behaviour changes on the legacy instance

`test_vehicle_command_queue.py` still passes unchanged, but these are observable:

- `put` returns a bool instead of None. Callers ignore it.
- `MAX_PENDING` now bounds the legacy queue too. Losers stay silent (`lost=None`); they are logged at DEBUG only.
- The worker thread exits after `close()` once the queue is empty. Nothing is put after the shutdown drain.
- `drain_high_priority` on a queue whose thread never started drops what is pending and returns False at once. It no longer waits out the 60 s. Following the brief literally, it returns False even when nothing was pending.
- Callback failures are logged by exception type name instead of a traceback. The legacy `_execute` still logs its traceback, on the `run=None` path only.

## Concerns

- **Line budget.**
  - Run.py is 398 lines against the plan's +260 estimate: `runAttempt` is ported almost verbatim at about 130 lines, RateLimits is about 50 and Workers about 110.
  - VehicleCommandQueue is +244/−76 against the +100 net estimate.
  - Task 6 used 664 of the 1,400 lines added that Tasks 6–14 are allowed. The remaining tasks need re-forecasting.
- **`ControlState.probeInFlight`** in Desired.py is dead now, along with its summary key. I left it because Desired.py is not on this task's file list and Task 7 rewrites that file.
- **A few comments still say "lane"** (HomeAssistantProvider, TeslaAPIProviders, and the `LANE_DETAILS` name in Outcome). They are cosmetic and left for Task 13's sweep.
- **The warn-once set in `checked` is module-level**, as the module-level signature implies. `test_workers.setup()` clears `Run._badReturns` so the tests do not depend on order.

## Fix round 1

**Commit:** 163d8c1, on top of ff84ff3.

### Fixed

- **I1 (worker exit window).** When the queue is closed and empty, `_next` now sets `_live = False` and calls `notify_all` under `_cond` before returning None. A stop put in the exit window is therefore rejected (`put` returns False) and reported once as `dropped`. It is no longer accepted and then orphaned.
  - New test: `test_a_stop_put_as_the_worker_exits_is_dropped_and_reported_once`, parametrized over two orderings: the put lands before `waitDrained`, or after `waitDrained` has returned True. The test wraps `_next` to hold the worker inside the exit gap.
  - Fail-before: `AssertionError: assert (True is False)`, where `True = submit(Attempt(...stopCharging...))`. That is, the stop was accepted. Both orderings failed this way.
  - The reviewer's probe `scratchpad/probe-slim6/test_probe_workers.py` passed 14 of 14 on each of 5 runs, including both exit-window probes.
- **M2 (dead worker).**
  - `put` rejects an entry when the worker has died or exited (`_thread` set and `_live` False). It returns False and reports `lost(e, "dropped")`.
  - `waitDrained` no longer waits on a worker that is not live, and drops what is pending.
  - New test: `test_a_dead_worker_rejects_new_entries_and_its_drain_does_not_wait`. It failed before the fix with `put(...) is True`.
  - The legacy `test_base_exception_in_dispatch_clears_busy` still passes. The dead legacy worker's drain returns True because nothing is pending.
- **M3 (caller-thread rule).**
  - The Run.py header now states which reports run on the caller's thread:
    - replaced, dropped and cancelled reports;
    - every inline or local attempt, where the whole of `runAttempt` runs (`DesiredStore.get` and `beforeWrite` included).
  - It also states the rule: never call `Workers.submit` or `cancel` while holding DesiredStore's lock or any lock the report handler takes. `submit` and `cancel` each carry a one-line pointer to it.
- **M4 (lost tracebacks).** Callback, `lost` and key failures now go through `_logFailure`: the type name at WARNING and the traceback at DEBUG. This applies to both the legacy instance and the attempt instances.

### Left as carry-forwards

These are the review's notes, not fixed here:
- **Task 7:** stale-desire value equality; `start()` before the first submit; removing `probeInFlight`.
- **Task 13:** the "lane" wording and `LANE_DETAILS`.
- **Not restored:** the `%r` of a legacy task in the DEBUG line for an entry dropped while draining. The line now logs the detail only, and the traceback path covers debugging.

### Tests

- Step 4 list: 165 passed.
- Full suite: **1458 passed, 1 xfailed, 1 warning**. The warning is the same one as before.
- `test_workers.py` with `test_vehicle_command_queue.py`: 68 passed on each of 3 runs.

### Lib delta

- This round (`git diff --stat ff84ff3 -- lib`): `2 files changed, 29 insertions(+), 10 deletions(-)`.
- Task 6 total (`git diff --stat 39d7cfb -- lib`): `10 files changed, 683 insertions(+), 800 deletions(-)`, net −117.
