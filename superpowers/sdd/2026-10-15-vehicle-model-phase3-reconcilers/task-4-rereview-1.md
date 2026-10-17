# Task 4 re-review 1: fix round bb512d0..f394844

**Verdict: APPROVED.** I1, I2, I3, M1 and L1 are all fixed. I found no new Important or worse issues.

**Tests:** I ran 11 focused files with the capped command and 291 passed:

- `test_provider_outcomes_local`
- `test_teslable_provider`
- `test_teslable_pairing_status`
- `test_gen2twc_provider`
- `test_gen3twc_provider`
- `test_provider_order`
- `test_vehicle_priority`
- `test_lanes`
- `test_gen2_idle_minimum`
- `test_outcome_desired`
- `test_twcslave`

I also re-ran my first-review probe script (`scratchpad/t4probe/probe_t4.py`), and wrote a new one (`probe_r1.py`).

## Per finding

- **I1: fixed.** `TeslaBLE.py:713-717`
  - The WARNING now carries only the command, the return code and `_errorCategory(output)`, which is a fixed word.
  - The raw output is logged at DEBUG, truncated to `[:200]`.
  - The duplicate WARNING is gone.
  - I swept every logger call at INFO or above in `TeslaBLE.py`. No other call interpolates stdout or stderr:
    - **pair:** INFO logs only success or failure; the output is DEBUG (`:595`).
    - **state reads:** log only the return code, at DEBUG.
    - **exception logs:** carry only `{e}`.
  - Probe evidence:
    - Probe 4, a failing `probe()`, now logs no raw output at INFO or above.
    - `probe_r1.py` drove three paths with a marker string in stdout and stderr: a refusal inside the pairing window, `peerWithVehicle` on a failure, and an undecodable-stderr command (the exception path). None put the marker into an INFO-or-above record.
- **I2: fixed.** `Desired.py:527-530`
  - `peek` takes `_lock` and returns `self._states.get(key)`, so it never inserts.
  - `Gen2TWCProvider.ready` treats `None` as False.
  - In probe 2, `keys()` stays `[]` after `ready()`, and the new test asserts this after `summary()` as well.
- **I3: fixed, per the ruling.** `TeslaBLE.py:522-526`
  - A refusal inside the pairing window returns `ERROR "pairing"`, and the claim is kept.
  - Outside the window the result is still `REFUSED "key"`, and the claim is dropped. Tests cover both a command and a probe.
  - **No retry storm:**
    - The refusal flag makes `_execute_with_retry` return at once. `probe_r1` saw one wire call with the default `maxRetries=3`, no backoff sleep, and no circuit-breaker failure recorded.
    - Above the provider, ERROR is RETRYABLE. Task 6 limits it to one try per `RETRY[aspect]`, at most `attempts()` (3) tries, then a backoff of 600 s or more.
    - The legacy `dispatch` makes 3 calls of one wire attempt each.
- **M1: fixed.** `TeslaBLE.py:512-517`
  - An answered probe that is not REFUSED calls `record_success`.
  - A failed probe, or an in-window `ERROR "pairing"` (whose output is None), records nothing.
  - The test covers all four steps: an open breaker blocks the command, the probe closes it, the command goes out, and repeated failed probes never open the breaker.
- **L1: fixed.** `TWCSlave.stopRequested = False` is now a class attribute, and the heartbeat reads `self.stopRequested`.
- **L2 and L3:** carried forward as ruled.

## Notes (no action needed)

- **Cosmetic:** `test_provider_outcomes_local.py:39` sets `chargeStopMode = "1"` and then immediately `"2"`. It is redundant but harmless.
- **For Task 6:** an `ERROR "pairing"` probe counts as a BLE health failure, so a paid provider may become eligible after `PAID_AFTER`. This is the expected cost of making the refusal retryable. Task 6 may want to skip the paid fallback while `_inPairingWindow` holds, but that is not a Task 4 issue.
