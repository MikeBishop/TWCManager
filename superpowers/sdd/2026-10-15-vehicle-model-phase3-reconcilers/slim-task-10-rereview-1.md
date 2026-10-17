# Slim Task 10 re-review, fix round 1 (846349b..bba7c4f)

Read-only. Code at scratchpad/wt-vm3 (bba7c4f). Mutations were run in a copy (scratchpad/rr1), never in wt-vm3.

Suite: `tests --ignore=tests/API --ignore=tests/integration`: 1671 passed, 1 xfailed.

## Findings

- I1 (re-arm clears paidRetryDue): ADDRESSED. Reconciler.py:405. Removing the line fails `test_a_lowered_limit_that_failed_once_rides_the_start_s_wake` (the limit is sent 3 times, then the start, never a wake). The first review's sleepy-car scratch now gives `[set, wake, set, wake, start]`, limit 50. `test_a_rearm_resets_the_blind_retry_and_keeps_the_cap` passes without the fix too; it pins the cap only.
- I2 (c4 over candidates): ADDRESSED. Reconciler.py:487-496. Reverting to `ordered()` fails `test_an_unpaired_ble_does_not_hold_the_start_of_a_car_ha_refused`. The review's 24 h unpaired-BLE scratch now gives `[setChargeLimit, startCharging]`. The rewritten M11 test (paired BLE answering UNREACHABLE) still holds the start for 1 h.
- M1 (gap not stamped for EXCLUDING): ADDRESSED. Desired.py:367. Reverting fails both `test_an_unsupported_free_provider_falls_through_without_the_gap` and `test_refused_excludes_the_provider_and_unsupported_falls_through`. The scratch run shows the Fleet stop at t+1, not t+10. I5 is kept (a DONE or UNREACHABLE start still stamps).
- M3 (Complete does not re-arm): ADDRESSED. Reconciler.py `_DRAWING`. Adding "Complete" back fails `test_a_complete_reading_does_not_rearm_a_lowered_limit`.
- M4, M6: ADDRESSED (comments corrected; the header is reflowed).
- M5: ADDRESSED in the report. 299+/433- = net -134 is consistent with the stated fix-round delta of +5 on -139.
- M2: accepted as-is (the ledger record is the coordinator's). Scratch `test_rearm_consumed_before_start_then_start_skips_limit` is unchanged, as expected.

## Regression hunt

- Extra paid calls: none beyond the cap. Re-arm still sets `rearmed` once per desire, and `paidSends < 2` bounds each arm, so at most 4 sends per desire. The always-408 scratch gave `[set, wake, wake]` and stayed bounded over 40 passes, and the 60-pass and 80-pass tests are bounded. One cost shift: re-armed sends now carry the normal wake and read when they are raises or starts. This is the intent of I1. A lower still sends no wake, and the cap test confirms it.
- 4-send cap: holds (`test_a_rearm_resets_the_blind_retry_and_keeps_the_cap`: <=4 commands, no wake).
- Start held forever: no. The unpaired-BLE case is fixed and the ride-wake-failed test passes. The M11 hold on a paired BLE with a down radio is unbounded in time, but it is the intended, free-BLE hold: BLE sends are free and keep retrying.
- Limit skipped: no new skip. I1 removes the old skip. One theoretical edge, not a defect: `able` is empty when no provider is ready for the car, so `all([])` is true and the limit counts as spent. In that state `plan` has no candidate for the start either, and the `lastOutcome is not None` guard means it only applies after a send.

## New issues

None.

## Verdict: APPROVED
