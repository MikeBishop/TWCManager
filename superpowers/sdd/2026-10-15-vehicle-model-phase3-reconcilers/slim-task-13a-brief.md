### Task 13a: TeslaBLE: one classified command, one quick retry (expected lib Δ ≈ −260)

Audit item 2, user decision: the reconciler owns retry.

**Files:**
- Modify: `Vehicle/TeslaBLE.py`. Delete `_execute_with_retry`, `BLECircuitBreaker`, `_init_retry_stats`, `_record_retry_attempt`, `_calculate_backoff`, `_is_transient_exception`, `retry_stats` and the `maxRetries`/`retryDelay`/`circuitBreaker*` config reads.
- Also delete the BLE helpers already dead on main: `_kill_process_group`, `_is_transient_error`, `BLECircuitBreaker.get_status` and `closeFile` (audit §5, ≈89).
- Update `docs/Settings.md` (the removed keys are ignored if present).
- Test (pre-flight M5): retry and breaker cases are deleted or replaced, including `test_provider_outcomes_local.py::test_an_open_breaker_half_opens_after_recovery_and_a_successful_command_closes_it` (≈102–111). Also remove the `maxRetries`/`retryDelay` setup in `test_provider_outcomes_local.py`, `test_teslable_pairing_status.py` and `test_teslable_lock.py`.

**Interfaces:**
- `sendCommand(vin, command, args=None)` runs tesla-control at most twice: once, then one quick retry (`QUICK_RETRY_DELAY = 2.0` s) only on a transient failure (timeout, or "connection" in the output). There is no backoff and no breaker.
- The pairing window and refusal handling are unchanged.

- [ ] **Step 1: Tests.**
  - `test_a_transient_failure_is_retried_once_then_reported`: two calls, then `UNREACHABLE`.
  - `test_a_non_transient_failure_is_not_retried`: one call.
  - `test_removed_retry_config_keys_are_ignored`.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "TeslaBLE sends one classified command with one quick retry; the reconciler owns retry"`

