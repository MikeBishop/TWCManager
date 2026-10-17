# Policy Evaluation Thread Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move TWCManager's policy evaluation off the serial main loop onto a dedicated daemon thread, so that module I/O triggered by policy conditions can no longer stall serial servicing.

**Architecture:** `Policy` owns a daemon thread. The thread evaluates once at start, then every `policyCheckInterval`, or sooner when `applyPolicyImmediately()` wakes it. `setChargingPerPolicy()` becomes the evaluation body: no rate limit, serialized by a lock. `stop()` ends the thread at shutdown. The main loop stops calling the policy engine and keeps reading its results, as it does today.

**Tech Stack:** Python 3 (3.13 on the live box), `threading`, pytest, black.

**Spec:** `.superpowers/specs/2026-10-08-policy-thread-design.md` (uncommitted, same worktree)

## Global Constraints

- **Working directory.** Use `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96` (branch `fix/policy-evaluation-thread`, based on `main` at 0b7d143). Run every command there and never cd to another checkout.
- **Untracked files.** Never commit anything under `.superpowers/`, and never edit any tracked `.gitignore`.
- **Tools.**
  - `VENV=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv` has the requirements, the test requirements and black.
  - Run the tests with `$VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider`. Baseline on this branch is "451 passed, 1 warning"; that warning is pre-existing.
  - Format with `$VENV/bin/black lib/` before every commit that touches lib/. CI runs `black --exclude="setup.py|tests/*" --check .`
- **Commit trailer.** End every commit message with `Co-Authored-By: Claude <the model you actually are> <noreply@anthropic.com>`.
- **Loggers.** Use the existing module `logger` (`LoggerFactory.get_logger("Policy", "Policy")`).
- **No semantics changes.** Do not change policy matching, latching, enforcement, or values.

## File Structure

| File | Change |
|---|---|
| `lib/TWCManager/Policy/Policy.py` | Thread lifecycle (`start`, `stop`, `_run`). `applyPolicyImmediately` wakes the thread. `setChargingPerPolicy` drops its rate limit and gains a lock and a stop check. |
| `lib/TWCManager/TWCSlave.py` | Remove the per-heartbeat `setChargingPerPolicy()` call. |
| `lib/TWCManager/TWCManager.py` | Start the policy thread after the background thread starts, and stop it first in the shutdown block. |
| `tests/unit/test_policy.py` | New `TestPolicyThread` class. |
| `tests/unit/test_twcslave.py` | Guard test that TWCSlave never calls `setChargingPerPolicy`. |

---

### Task 1: Policy evaluation thread

**Files:**
- Modify: `lib/TWCManager/Policy/Policy.py` (imports at lines 1-4; `__init__` at ~line 90; `applyPolicyImmediately` and `setChargingPerPolicy` at ~lines 134-184)
- Test: `tests/unit/test_policy.py` (append a class)

**Interfaces:**
- Produces:
  - `Policy.start() -> None`: starts a daemon thread named `"PolicyEvaluation"`. Idempotent.
  - `Policy.stop() -> None`: returns immediately; no evaluation starts afterwards.
  - `Policy.applyPolicyImmediately() -> None`: wakes the thread and returns immediately. It is a no-op after `stop()`.
  - `Policy.setChargingPerPolicy() -> None`: evaluates now, with no rate limit. It holds `_evalLock` and does nothing after `stop()`.
  - `Policy._thread`: the `threading.Thread`, or `None` before `start()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_policy.py`:

```python
class TestPolicyThread:
    """Policy evaluation runs on its own thread, never the serial main loop."""

    WAIT = 2.0

    @pytest.fixture
    def mock_master(self):
        master = Mock()
        master.config = {"config": {}, "policy": {}}
        master.settings = {}
        master.getModuleByName = Mock(return_value=Mock())
        master.getModulesByType = Mock(return_value=[])
        return master

    @pytest.fixture
    def policy(self, mock_master):
        from TWCManager.Policy.Policy import Policy

        p = Policy(mock_master)
        p.policyCheckInterval = 3600
        yield p
        p.stop()

    @staticmethod
    def wait_until(predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return predicate()

    def recorder(self, policy, gate=None):
        """Replace the evaluation with a recorder; optionally block on `gate`."""
        import threading

        calls = []
        entered = threading.Event()

        def fake():
            calls.append(time.monotonic())
            entered.set()
            if gate is not None:
                gate.wait(self.WAIT)

        policy.setChargingPerPolicy = fake
        return calls, entered

    def test_start_evaluates_immediately(self, policy):
        calls, _ = self.recorder(policy)
        policy.start()
        assert self.wait_until(lambda: len(calls) >= 1)

    def test_apply_immediately_wakes_thread(self, policy):
        calls, _ = self.recorder(policy)
        policy.start()
        assert self.wait_until(lambda: len(calls) >= 1)
        policy.applyPolicyImmediately()
        assert self.wait_until(lambda: len(calls) >= 2, timeout=1.0)

    def test_apply_immediately_does_not_block_on_running_evaluation(self, policy):
        import threading

        gate = threading.Event()
        calls, entered = self.recorder(policy, gate)
        policy.start()
        assert entered.wait(self.WAIT)
        start = time.monotonic()
        policy.applyPolicyImmediately()
        assert time.monotonic() - start < 0.5
        gate.set()
        assert self.wait_until(lambda: len(calls) >= 2)

    def test_periodic_evaluation_without_wake(self, policy):
        policy.policyCheckInterval = 0.05
        calls, _ = self.recorder(policy)
        policy.start()
        assert self.wait_until(lambda: len(calls) >= 3)

    def test_exception_is_logged_and_thread_survives(self, policy):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("powerwall unreachable")

        policy.setChargingPerPolicy = flaky
        with patch("TWCManager.Policy.Policy.logger") as log:
            policy.start()
            assert self.wait_until(lambda: len(calls) >= 1)
            policy.applyPolicyImmediately()
            assert self.wait_until(lambda: len(calls) >= 2)
            assert log.error.called

    def test_start_is_idempotent(self, policy):
        self.recorder(policy)
        policy.start()
        first = policy._thread
        policy.start()
        assert policy._thread is first

    def test_stop_ends_thread_and_blocks_further_wakes(self, policy):
        calls, _ = self.recorder(policy)
        policy.start()
        assert self.wait_until(lambda: len(calls) >= 1)
        policy.stop()
        policy._thread.join(1.0)
        assert not policy._thread.is_alive()
        count = len(calls)
        policy.applyPolicyImmediately()
        time.sleep(0.2)
        assert len(calls) == count

    def test_stop_lets_running_evaluation_finish(self, policy):
        import threading

        gate = threading.Event()
        finished = []
        calls, entered = self.recorder(policy, gate)
        inner = policy.setChargingPerPolicy

        def wrapped():
            inner()
            finished.append(True)

        policy.setChargingPerPolicy = wrapped
        policy.start()
        assert entered.wait(self.WAIT)
        policy.stop()
        gate.set()
        policy._thread.join(self.WAIT)
        assert finished == [True]
        assert len(calls) == 1

    def test_direct_evaluation_has_no_rate_limit_and_respects_stop(self, policy):
        policy.checkConditions = Mock(return_value=False)
        policy.enforcePolicy = Mock()
        policy.setChargingPerPolicy()
        policy.setChargingPerPolicy()
        assert policy.enforcePolicy.call_count == 2
        policy.stop()
        policy.setChargingPerPolicy()
        assert policy.enforcePolicy.call_count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$VENV/bin/python -m pytest tests/unit/test_policy.py -q -p no:cacheprovider -k TestPolicyThread 2>&1 | tail -5`
Expected:
- Failures with `AttributeError: 'Policy' object has no attribute 'stop'`, which is raised by the fixture teardown or the tests.
- `test_direct_evaluation_has_no_rate_limit...` fails with `assert 1 == 2`, because today's 30 s gate skips the second call.

- [ ] **Step 3: Implement**

In `lib/TWCManager/Policy/Policy.py`:

1. Imports. Add these after `import time`:

```python
import threading
import traceback
```

2. `__init__`. Add these as the first lines of the body, directly after `def __init__(self, master):`:

```python
        # Policy evaluation runs on its own thread (see start()) so module
        # I/O done by policy conditions never stalls the serial main loop.
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._evalLock = threading.Lock()
        self._thread = None
```

3. Replace `applyPolicyImmediately` (currently it sets `self.lastPolicyCheck = 0` and then calls `self.setChargingPerPolicy()`) with these four methods:

```python
    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="PolicyEvaluation", daemon=True
        )
        self._thread.start()

    def stop(self):
        # Shutdown: start no further evaluations. An evaluation already in
        # progress finishes; the thread is not joined.
        self._stopping.set()
        self._wake.set()

    def applyPolicyImmediately(self):
        # Wake the policy thread; evaluation happens there, not on the caller.
        if not self._stopping.is_set():
            self._wake.set()

    def _run(self):
        while not self._stopping.is_set():
            try:
                self.setChargingPerPolicy()
            except Exception as e:
                logger.error(
                    f"PolicyError: {traceback.format_exc()}, occurred when evaluating policy: {e}",
                    extra={"colored": "red"},
                )
            self._wake.wait(timeout=self.policyCheckInterval)
            self._wake.clear()
```

4. In `setChargingPerPolicy`, replace everything from the start of the method body through the rate-limit gate:

```python
        # This function is called for the purpose of evaluating the charging
        # policy and matching the first rule which matches our scenario.

        # Once we have determined the maximum number of amps for all slaves to
        # share based on the policy, we call setMaxAmpsToDivideAmongSlaves to
        # distribute the designated power amongst slaves.

        # First, determine if it has been less than 30 seconds since the last
        # policy check. If so, skip for now
        if (self.lastPolicyCheck + self.policyCheckInterval) > time.time():
            return
        else:
            # Update last policy check time
            self.lastPolicyCheck = time.time()

        for policy in self.charge_policy:
```

with:

```python
        # This function is called for the purpose of evaluating the charging
        # policy and matching the first rule which matches our scenario.

        # Once we have determined the maximum number of amps for all slaves to
        # share based on the policy, we call setMaxAmpsToDivideAmongSlaves to
        # distribute the designated power amongst slaves.

        # Cadence is owned by the policy thread (see start()); this evaluates
        # now. The lock keeps evaluations from overlapping.
        if self._stopping.is_set():
            return
        with self._evalLock:
            self.lastPolicyCheck = time.time()
            self._evaluate()

    def _evaluate(self):
        for policy in self.charge_policy:
```

Leave the rest of the original method body unchanged: the `for` loop and the trailing `self.enforcePolicy(self.getPolicyByName(self.active_policy))`. It now forms the body of `_evaluate`, at the same indentation it already has, so no re-indenting is needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$VENV/bin/python -m pytest tests/unit/test_policy.py -q -p no:cacheprovider 2>&1 | tail -2`
Expected: all pass, with no failures in the existing policy tests.

Then run the thread tests 20 times to check for flakiness:

```bash
for i in $(seq 20); do $VENV/bin/python -m pytest tests/unit/test_policy.py -q -p no:cacheprovider -k TestPolicyThread 2>&1 | tail -1; done | sort | uniq -c
```

Expected: a single line reporting 20 runs of "9 passed".

- [ ] **Step 5: Format, run the full suite, and commit**

Run: `$VENV/bin/black lib/ && $VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider 2>&1 | tail -1`
Expected: `460 passed, 1 warning`

```bash
git add lib/TWCManager/Policy/Policy.py tests/unit/test_policy.py
git commit -m "Evaluate charging policy on its own thread

Policy conditions can read module properties that do network I/O
(Powerwall gridStatus/batteryLevel, stormWatch with a Fleet API token
refresh). Give Policy a daemon thread that owns evaluation cadence;
applyPolicyImmediately() now just wakes it, and stop() ends it at
shutdown.

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
```

---

### Task 2: Take policy evaluation off the main loop

**Files:**
- Modify: `lib/TWCManager/TWCSlave.py` (~lines 693-697)
- Modify: `lib/TWCManager/TWCManager.py` (after `backgroundTasksThread.start()`, ~line 803; shutdown block after the main loop, ~line 1947)
- Test: `tests/unit/test_twcslave.py` (append a class)

**Interfaces:**
- Consumes: `Policy.start()` and `Policy.stop()` from Task 1.

- [ ] **Step 1: Write the failing guard test**

Append to `tests/unit/test_twcslave.py`:

```python
class TestPolicyNotOnMainLoop:
    """The serial main loop must not evaluate charging policy inline."""

    def test_twcslave_never_calls_set_charging_per_policy(self):
        import inspect
        from TWCManager.TWCSlave import TWCSlave

        assert "setChargingPerPolicy" not in inspect.getsource(TWCSlave)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `$VENV/bin/python -m pytest tests/unit/test_twcslave.py -q -p no:cacheprovider -k TestPolicyNotOnMainLoop 2>&1 | tail -3`
Expected: FAIL (`assert 'setChargingPerPolicy' not in ...`).

- [ ] **Step 3: Remove the call in TWCSlave**

In `lib/TWCManager/TWCSlave.py`, `receive_slave_heartbeat`, delete these lines:

```python
        # Determine our charging policy. This is the policy engine of the
        # TWCManager application. Using defined rules, we can determine how
        # we charge.
        self.master.getModuleByName("Policy").setChargingPerPolicy()

```

Put this comment in their place:

```python
        # Charging policy is evaluated on the Policy module's own thread;
        # here we only read its results (getMaxAmpsToDivideAmongSlaves etc.).

```

- [ ] **Step 4: Start and stop the thread in TWCManager.py**

After these lines:

```python
backgroundTasksThread = threading.Thread(target=background_tasks_thread, args=(master,))
backgroundTasksThread.daemon = True
backgroundTasksThread.start()
```

add:

```python

# Charging policy is evaluated on its own thread so module I/O done by
# policy conditions never stalls serial servicing. The first evaluation
# runs now, usually before the first slave heartbeat.
master.getModuleByName("Policy").start()
```

In the shutdown block after the main loop, insert this directly before `# Make sure any volatile data is written to disk before exiting`:

```python
# Stop policy evaluation first so it doesn't queue new work while we drain.
master.getModuleByName("Policy").stop()

```

- [ ] **Step 5: Verify**

Run:

```bash
$VENV/bin/python -c "import ast; ast.parse(open('lib/TWCManager/TWCManager.py').read())"
$VENV/bin/black lib/
$VENV/bin/python -m pytest tests/unit -q -p no:cacheprovider 2>&1 | tail -1
grep -rn "setChargingPerPolicy" lib/
```

Expected:
- The parse succeeds.
- `461 passed, 1 warning`.
- grep shows `setChargingPerPolicy` only inside `lib/TWCManager/Policy/Policy.py`.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/TWCSlave.py lib/TWCManager/TWCManager.py tests/unit/test_twcslave.py
git commit -m "Stop evaluating policy on the serial main loop

receive_slave_heartbeat evaluated policy inline every heartbeat; a
Powerwall login during a gridStatus condition held the serial thread for
2.9s on a live install. Start the Policy thread at startup, stop it
first at shutdown, and only read policy results from the heartbeat.

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
```

---

### Task 3: Live verification (controller)

The controller runs this directly; there is no subagent.

1. **Build and test.** Build a local deploy branch by merging `deploy/ble-plus-state08` (#668 + #669) and `diag/stall-stacks` (the faulthandler diagnostic) with `fix/policy-evaluation-thread`. Resolve the expected conflicts in the `TWCManager.py` startup and shutdown blocks: keep #668's order and add the policy `stop()` first. Run the full suite and the black check.
2. **Deploy to the box.** Bundle against `a7c84f4`, then fetch and do a detached checkout on the box. Restart, and confirm "Shutdown complete" followed by "Starting main event loop".
3. **Startup check.** In the startup log, the policy is chosen ("New policy selected") at or before the first slave heartbeat.
4. **Watch for at least 12 hours.**
   - Count `Main loop stalled` warnings and inspect each faulthandler dump. Expect no main-thread frames in `Policy` or `TeslaPowerwall2`.
   - Compare against the baseline of 6 non-startup stalls in about 14 hours, all lined up with policy ticks, with one confirmed in `doPowerwallLogin`.
5. **Report.** Give the counts and any new stall stacks as they are. If stalls remain, report their stacks; do not fix further in this branch.
