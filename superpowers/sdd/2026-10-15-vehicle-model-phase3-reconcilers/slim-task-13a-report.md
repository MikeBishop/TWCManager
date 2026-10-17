# Slim Task 13a report: TeslaBLE sends one classified command with one quick retry

**Status:** DONE
**Branch / worktree:** `vehicle-model/phase3` in `scratchpad/wt-vm3`. BASE is 464d83c. Not pushed.
**Commit:** `21ed474` TeslaBLE sends one classified command with one quick retry; the reconciler owns retry

## What changed

`lib/TWCManager/Vehicle/TeslaBLE.py`:

- **Deleted:**
  - `BLECircuitBreaker`, including `get_status`;
  - `_execute_with_retry`, `_init_retry_stats`, `_record_retry_attempt`, `_calculate_backoff` and `_is_transient_exception`;
  - `retry_stats` and `circuit_breaker`;
  - the `maxRetries`, `retryDelay`, `circuitBreakerThreshold` and `circuitBreakerTimeout` reads, and also `statsReporting`, which is unread and was the retry-stats toggle;
  - the helpers already dead on main: `_kill_process_group`, `_is_transient_error` and `closeFile`.
- **`sendCommand(vin, command, args=None)`:**
  - It calls `_sendCommand_internal` once.
  - It retries once, after `QUICK_RETRY_DELAY = 2.0` s, only when that run recorded a transient failure:
    - the run timed out or failed to launch, so `_run_command_with_timeout` returned `(None, None, None)`;
    - or tesla-control was killed (rc −9);
    - or a non-zero exit with "connection" in its output, case-insensitive.
  - There is no backoff and no breaker.
  - The sleep runs outside `_bleLock`, because only `_sendCommand_internal` is `@_serialized`. The lock scope is not widened.
- **Thread-local:** the per-thread `_keyRefusal` became `_failure`, with `.refused` (unchanged meaning) and `.transient` (new). A key refusal is never transient, so it is never retried.
- **Unchanged:**
  - Classification (`commandOutcome` / `_classify`). Inside the pairing window a key refusal gives `ERROR "pairing"`; outside it gives `REFUSED "key"`. A stored refused status gives `REFUSED`. `None` gives `UNREACHABLE "no reply"`. Then `SATISFIED`, `DONE` and `ERROR <category>`.
  - The pairing-window and refusal recording.
  - `NOT_SENT` is assigned by the reconciler (Run.py/Outcome.py), not by TeslaBLE, so it is unaffected.

`docs/Settings.md` has a new "BLE retries" subsection. It describes the one quick retry and says the four removed keys are ignored if present.

## Size

Non-test lib delta for `TeslaBLE.py`: **+33 / −314 = −281.** The expected figure was about −260.

## Tests

- **Full suite** (`tests --ignore=tests/API --ignore=tests/integration`): **1664 passed, 1 xfailed.** BASE was 1657 passed and 1 xfailed. The change is −2 deleted tests and +9 new test cases.
- **Mutation checks** on the new and adjusted tests; every mutant was caught:
  - M1: the "connection" output is never transient. 1 failure.
  - M2: retry on any failure. 5 failures.
  - M3: a timeout is not transient. 4 failures.
  - M4: a pairing-window refusal gives `REFUSED`. 2 failures.
  - M5: `QUICK_RETRY_DELAY = 0`. 4 failures.

### New tests (`tests/unit/test_teslable_pairing_status.py`)

- `test_a_transient_failure_is_retried_once_then_reported[timeout|killed|connection]`: two runs, then `UNREACHABLE "no reply"`, with one `sleep(2.0)`.
- `test_a_transient_failure_then_success_is_done`: a timeout followed by success gives `DONE`.
- `test_a_non_transient_failure_is_not_retried[ble: timeout | car could not execute: not_allowed | empty]`: one run, no sleep.
- `test_a_command_rejected_before_running_is_not_retried`: a VIN not in settings means no run and no sleep. The old wrapper retried this case with backoff.
- `test_removed_retry_config_keys_are_ignored`:
  - the keys are set (threshold 1);
  - the module builds and has no `maxRetries`, `retryDelay`, `circuit_breaker` or `retry_stats`;
  - three failing commands give six runs, so no breaker opens.

### Adjusted tests

- `test_key_refusal_stops_retrying_and_records_once`: drops `fast_retries` and now also asserts no sleep.
- `test_provider_outcomes_local.py::_wire`: `maxRetries = 0` became `QUICK_RETRY_DELAY = 0`. The "SECRET-MARKER connection failed" logging test now runs twice and still logs nothing raw at INFO or above.
- `test_ble_key_refusal_is_refused_...`: `_keyRefusal` became `_failure`.
- `test_teslable_lock.py::test_retry_backoff_sleeps_outside_lock` is renamed `test_quick_retry_sleeps_outside_lock`. It drops `retryDelay = 0`; the assertion is the same (the lock is not held during the sleep).

### Deleted-test mapping

| Deleted test | Now pinned by / disposition |
|---|---|
| `test_provider_outcomes_local.py::test_an_open_breaker_half_opens_after_recovery_and_a_successful_command_closes_it` | **INTENTIONALLY CHANGED**: Task 13a brief and dedup-audit §2 (the reconciler owns retry; no breaker). `test_removed_retry_config_keys_are_ignored` pins the absence of a breaker: repeated failures never stop later sends. A successful command classified `DONE` is still pinned by `test_ble_outcomes_follow_tesla_control_output` and `test_a_transient_failure_then_success_is_done`. |
| `test_teslable_pairing_status.py::test_other_failures_are_still_retried` (`"ble: timeout"` rc=1 gave 3 runs) | **INTENTIONALLY CHANGED** (Task 13a brief: at most two runs, retry only on transient). Pinned by `test_a_transient_failure_is_retried_once_then_reported[*]` (2 runs) and `test_a_non_transient_failure_is_not_retried[ble: timeout]` (1 run). |
| `test_teslable_pairing_status.py::fast_retries` (helper) | **PLUMBING-ONLY** |

## Concerns

1. **How "timeout" is read.** I took the brief's "timeout" to mean that the tesla-control run itself timed out: no result, or SIGKILL. A completed run whose stderr contains the word "timeout" (for example `ble: timeout`) is not retried. Only "connection" is matched in the output text, as the brief says. If "timeout" in the output should also count, it is a one-word change.
2. **Two dead config reads remain.** `processGroupManagement` and `dockerCompatibility` are still read and never used. The brief did not name them; they would save 2 lines.
3. **Rename.** `_keyRefusal` was renamed `_failure`. The only external reference was one test, which I updated.

## Follow-up (coordinator request)

**Commit:** `9db3f1b` Retry a "timeout" BLE output once; drop unused BLE config reads

1. **"timeout" in the output now counts as transient.** A finished run with a non-zero exit whose output contains "timeout" (for example `ble: timeout`) gets the one quick retry, the same as a run that timed out or a "connection" error. This resolves concern 1.
   - Test: `test_a_transient_failure_is_retried_once_then_reported[timeout-output]` expects two runs, then `UNREACHABLE`.
   - The `ble: timeout` case was removed from `test_a_non_transient_failure_is_not_retried`.
2. **Unused config reads deleted.** The `processGroupManagement` and `dockerCompatibility` reads are gone. This resolves concern 2.

**Suite:** 1664 passed, 1 xfailed. One parametrized case moved between tests, so the count is unchanged.

**Lib delta:**
- this commit: +2/−3 = −1;
- Task 13a in total since 464d83c: `TeslaBLE.py` +34/−316 = **−282**.

## Fix round 1 (slim-task-13a-review.md)

**Commit:** `f0327e5` Classify a BLE failure as transient on tesla-control's final error line

### I1: classify on the final error line

- **Change:** `_sendCommand_internal` drops tesla-control's log lines and tests only the last line that remains.
  - A log line matches `LOG_LINE = ^\S+ \[\w+ ?\] `, which covers `[debug]`, `[info ]`, `[warn ]` and `[error]` per `internal/log/logger.go`.
  - A failure is transient when that line contains `"connection"`, `"timeout"` or `"deadline exceeded"` (`TRANSIENT_TEXT`).
- **Test:** `test_only_the_final_error_line_decides_a_quick_retry[not_allowed|deadline|connection|timeout]` feeds realistic `-debug` stderr. The preamble contains "Securing connection..." and a `[warn ]` line containing "timeout".
  - `not_allowed`: 1 run.
  - `deadline exceeded`, `connection lost` and `timeout`: 2 runs.
- **Red before the fix:** `[not_allowed]` failed against 9db3f1b. `[deadline]` passed there only because the preamble's warn line said "timeout". After the fix it depends on `"deadline exceeded"`: removing that text from `TRANSIENT_TEXT` fails exactly that case (checked).

### M1: stored-refused branch

- **Test:** `test_a_stored_refused_key_is_refused_even_when_the_run_times_out`. With a stored status of "refused" and a timed-out run, the result is `Outcome(REFUSED, "key")`.
- **Not red before the fix:** the branch was already correct and only unpinned. A test that disables the branch now fails.

### M2: redundant reset

- **Change:** the `refused` reset at the top of `_sendCommand_internal` is dropped. `commandOutcome` still resets it.

### M3: retry logged at INFO

- **Change:** the quick retry is logged at INFO once per retry, with only the command and VIN.
- **Test:** `test_the_quick_retry_is_logged_at_info_once`. It was red before the fix.

### Results

**Suite:** 1670 passed, 1 xfailed.

**Lib delta:**
- this commit: +14/−4 = +10;
- Task 13a in total since 464d83c: `TeslaBLE.py` +44/−316 = **−272**.
