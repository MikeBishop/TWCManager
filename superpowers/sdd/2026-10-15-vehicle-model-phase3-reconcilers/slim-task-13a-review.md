# Slim Task 13a review: TeslaBLE sends one classified command with one quick retry

**Range:** 464d83c..9db3f1b (21ed474, 9db3f1b), checked against the code in `scratchpad/wt-vm3`.
**Spec verdict:** COMPLIANT. Everything the brief names is deleted; `sendCommand` runs tesla-control at most twice; `QUICK_RETRY_DELAY = 2.0`; the three named tests exist; `docs/Settings.md` is updated; the retry/refusal setup was removed from the three test files.
**Quality verdict:** APPROVED WITH ONE IMPORTANT. It is not a blocker for tonight.
**Counts:** Critical 0, Important 1, Minor 3.

## How it was checked

- I read the whole diff, plus `TeslaBLE.py` at 9db3f1b, `TeslaBLEProvider.py`, and the consumers `Reconcile/Run.py`, `Reconcile/Outcome.py`, `Reconcile/Desired.py:noteOutcome` and `Reconcile/Reconciler.py`.
- I read the tesla-control source in `~/github/vehicle-command`: `cmd/tesla-control/{main,commands}.go`, `pkg/cli/config.go` and `internal/log/logger.go`.
- On the live box, I read only the BLE keys of `/etc/twcmanager/config.json`: just `teslaControlPath` is set, so `commandTimeout` is the default 5 s and the base build used `maxRetries` 3. I also read today's journal.
- Mutation run: 14 mutants against `tests/unit`. The file was restored byte-for-byte and `git status` is clean.

## Critical

None.

## Important

### I1. The "connection" heuristic matches tesla-control's own progress log, so nearly every failure after the car connects is retried

- **Evidence:**
  - `lib/TWCManager/Vehicle/TeslaBLE.py:507-509` sets `self._failure.transient = "connection" in out or "timeout" in out`, where `out` is the whole stderr.
  - TWCManager always passes `-debug` (`TeslaBLE.py:449`).
  - tesla-control then logs `log.Info("Securing connection...")` to stderr on every run that reaches the car, before `StartSession` (`vehicle-command/pkg/cli/config.go:384`, `internal/log/logger.go:45-50`).
- **Result:** any failure after the session starts is classified transient and gets the quick retry. For example, `Failed to execute command: car could not execute command: not_allowed` gets one retry plus the 2 s sleep. Reproduced against 9db3f1b with a realistic stderr:

  ```
  not_allowed after connect: Outcome(kind='unreachable', detail='no reply') runs=2 sleeps=1
  already charging (satisfied): Outcome(kind='satisfied', detail='is_charging') runs=1 sleeps=0
  key refusal:                  Outcome(kind='refused', detail='key') runs=1 sleeps=0
  ```

- **Why the tests miss it:** `tests/unit/test_teslable_pairing_status.py:174` (`test_a_non_transient_failure_is_not_retried`) feeds a bare `Error: car could not execute command: not_allowed` with no `-debug` preamble, which real tesla-control never produces. The docs line "any other failure is reported straight away" (`docs/Settings.md:73`) is therefore not true in practice.
- **Impact:** bounded and not unsafe.
  - Still at most two runs.
  - Key refusals and already-satisfied replies are checked first, so they are never retried.
  - The cost is one extra 5 s-class run and 2 s on deterministic car errors. That is less than the base build, which retried every failure up to three times.
- **Fix:** classify only on tesla-control's final error line, not on its log lines.
  - Drop lines that match its log prefix (`^\S+ \[(debug|info|warning)\] `) and test what remains, or test only the last non-empty line.
  - Optionally add `"deadline exceeded"` (Go's timeout text, which contains neither keyword).
  - Add a test case whose stderr carries the real `-debug` preamble (`… [info] Connecting to car...`, `… [info] Securing connection...`) followed by `Failed to execute command: car could not execute command: not_allowed`, and expect one run.

## Minor

### M1. The stored "refused" branch of `_classify` is not pinned by any test

- **Evidence:** I replaced `TeslaBLE.py:306` `if self._storedStatus(vin)["status"] == "refused":` with `if False:` and all 1655 tests in `tests/unit` still passed.
- **Context:** this predates the task (`_classify` is unchanged and no deleted test covered it). It decides that a run which timed out against a key already known to be refused reports `REFUSED "key"`, which excludes the provider, rather than `UNREACHABLE`, which retries it. That consumer distinction is exactly what the reconciler relies on.
- **Fix:** add a test that calls `_setBleStatus(VIN, "refused")`, wires `(None, None, None)`, and asserts `Outcome(REFUSED, "key")`.

### M2. The `refused` reset at the top of `_sendCommand_internal` is redundant

- **Evidence:** deleting it (`TeslaBLE.py:418`) leaves no failing test, and the mutant is equivalent:
  - `commandOutcome` already resets `refused` (`:292`);
  - a refused first run is never retried, so the second run never inherits a stale `True`;
  - `wakeVehicle` never reads `refused`.
- **Fix:** delete the line (−1), or keep it as a defensive reset and accept that it is untested.

### M3. The quick retry is logged only at DEBUG

- **Evidence:** `TeslaBLE.py:409`. The base build logged every retry at INFO (`retrying in 2s (attempt 1/4)`). At INFO, an operator now sees two `Command timed out after 5s` warnings and cannot tell they belong to one call.
- **Fix:** log the retry at INFO with only the command name and VIN, which keeps it secret-free. Optional.

## Checks that passed

### Wake behaviour

- **Invocation:** the command line is unchanged (`TeslaBLE.py:442-455`): `tesla-control -debug -ble -vin VIN -key-file /tmp/ble_data wake`, with the `nsenter` prefix in Docker. With `-ble`, `wake` handshakes only with VCSEC (`commands.go:145-157`), the same as before.
- **Timeout:** `commandTimeout` is unchanged (default 5 s; `_run_command_with_timeout` is untouched).
- **Sequence:** `Run._wake` is unchanged. A BLE wake that fails still lets the command go out (`Run.py` `_wake`, local branch). `TeslaBLEProvider.wake` still calls `commandOutcome(vin, "wake")`.
- **Retry budget (intended change):**
  - Base build: up to 4 runs with 2/4/8 s backoff, on any failure.
  - Now: up to 2 runs with 2 s between, only on a transient failure.
  - A timed-out run (tesla-control's connect timeout is 20 s, so TWCManager's 5 s kill always fires first) returns `(None, None, None)` and is retried.
- **Live log:** this morning's journal (07:14–07:15) shows two full 4-run sequences, all `timed out after 5s`. The old budget did not rescue that window either.

### Outcome classification (consumers checked in `Desired.py:386-423`)

- **Pairing window:** a key refusal inside the window gives `ERROR "pairing"`, and `noteOutcome` counts it as `free.success`. Mutating it to `REFUSED` fails 2 tests.
- **Refusals:** a refusal outside the window, or a stored refused status, gives `REFUSED`, which is in `EXCLUDING` and so excludes the provider. `UNSUPPORTED` is never produced by BLE.
- **NOT_SENT:** produced only by the reconciler and Run (`rules:` details, `cancelled`, and so on). Unchanged.
- **Transient failures:** a run timeout or launch failure gives `(None, None, None)`; rc −9, `"connection"` and `"timeout"` in the output are also transient. Each gets one retry and then `UNREACHABLE "no reply"`, which is retryable. A refusal on the second run is still classified `REFUSED`, because `commandOutcome` reads the thread-local after `sendCommand` returns.

### Retry bounds

- At most 2 tesla-control runs per `sendCommand`: the mutant that allows a third run fails 5 tests.
- Per attempt, the worst case is wake (2) plus command (2) plus one state read (`_fetch_state_json`, never retried), which is 5 runs. The base build allowed 9 or more.
- Reconciler gaps still apply: `RETRY` 300/60/60 s and `MIN_SEND_GAP`. The H2 hold covers `NOT_SENT`, and a start is held until the limit settles or is spent (`Reconciler.py:347-361`). There is no retry storm.

### Locks

- The diff adds no lock acquisitions.
- The sleep runs outside `_bleLock`, because only `_sendCommand_internal` is `@_serialized`. Moving the sleep inside the lock fails `test_quick_retry_sleeps_outside_lock`.
- The order `_bleLock -> settingsLock -> registry leaf` is unchanged (`TeslaBLE.py:952-953`). No I/O was added under `settingsLock` or the registry locks.

### Secrets

- The only new log line names the command and nothing else.
- The removed INFO/WARNING lines that interpolated exception text are gone.
- `test_a_failing_command_logs_no_raw_output_at_info_or_above` now covers two runs and passes.

### Size

- `git diff --numstat` shows `TeslaBLE.py` +34/−316, which is −282.
- Total non-test `lib/**/*.py` went from 28,161 to 27,879, which is −282.
- Removed: 243 code, 25 comment and 48 blank lines. Added: 27 code, 6 comment and 1 blank line.
- The figure is honest: almost all of it is deleted code, not reformatting. It beats the −260 estimate.
- No leftover references to the removed keys or symbols in `lib`, `docs`, `etc` or the templates. v1.3.3 shipped the keys, so "removed in v1.4.0" is correct.

## Mutation results (`tests/unit`, 1655 tests)

| Mutant | Failures |
|---|---|
| pairing-window refusal gives `REFUSED` | 2 |
| never retry | 7 |
| retry on any failure | 4 |
| third run allowed | 5 |
| "connection" not transient | 1 |
| "timeout" output not transient | 1 |
| rc −9 not transient | 1 |
| no-result run not transient | 4 |
| refusal marked transient (retried) | 1 |
| `None` gives `ERROR` instead of `UNREACHABLE` | 9 |
| sleep inside `_bleLock` | 1 |
| `QUICK_RETRY_DELAY = 0` | 5 |
| stored-refused branch disabled | **0** (M1) |
| `refused` reset removed from `_sendCommand_internal` | **0** (M2, equivalent) |

### Deleted-test mapping

- **Breaker test:** its replacement, `test_removed_retry_config_keys_are_ignored`, would catch a reintroduced breaker that reads the old keys (threshold 1, six runs expected).
- **`test_other_failures_are_still_retried`:** replaced by the `[timeout-output]` case, which the "timeout output" mutant fails.
- **`fast_retries`:** plumbing only.

The mapping holds. Of the requested rows, no test is unable to fail.

## Tonight's BLE-only scheduled charge

The scenario: the car is asleep; at midnight the limit goes 50→70, then a start goes over BLE.

- **Expected flow per attempt:**
  - **Limit:** a BLE state read, then a wake (VCSEC, at most 2 runs), then `charging-set-limit 70` (at most 2 runs).
  - **Start:** held until the limit settles, then 5 s after the limit write, a wake and `charging-start` (at most 2 runs each).
- **If infotainment is still booting:**
  - The set-limit run times out and is retried once, 2 s later.
  - If that also fails, the next limit attempt comes 300 s later, while the car is still awake from the wake.
  - The start comes about 60 s after a failure.
- **Latency:** worse than the base build's 4-run burst, but delivery still happens.
- **What to watch:** `Command timed out after 5s` pairs, and the reconciler's DEBUG `Charge limit … via TeslaBLE: …` lines.
