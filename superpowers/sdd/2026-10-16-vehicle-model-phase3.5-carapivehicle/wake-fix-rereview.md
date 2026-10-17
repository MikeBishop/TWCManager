# Wake fix round 1 re-review (phase3.5 tip a698f753)

Verdict: all rulings applied; one Low residual (R1).
Tests: tests/unit on a698f753 1859 passed, 0 failed (the fixer reports 1868, probably a different collected set; parity, limit and charging files 185 passed).

- Rulings F1-F6, F8 are applied as ruled; the F7 rows (+2400 s, +4000 s, limit+start never online) are added.
- Re-arm cap: it uses the single `rearmed` flag, so it fires at most once per desire. Each arm is capped at 2 paid sends (`paidSends<2`), so at most 4 per desire. The clause needs `wakes`, so it never leads to a send without a wake.
- The stale `wakeCheckBy` after re-arm only widens H2 to 120 s, which is free. `wakeCheckBy` is cleared by the next non-wake paid outcome.
- Free-only: the `wakeCheckBy` follow-up goes only to `paid[0]` with the same name, and its wake is held by the provider (new hold test covers every billed waker, with a mutation check). The 120 s H2 gap applies only to NOT_SENT outcomes.
- No paid resubmit loop: every held attempt is NOT_SENT. `paidSends` does not rise on NOT_SENT.
- Wake spacing: the hold is per car, so consecutive wakes are over 1800 s apart (asserted in the three new tests).
- Parity rows are unchanged. The only changed expectations are the never-online row (2 to 4 wakes, which is the re-arm's second arm) and the `["wake"]*4` / `<=8` unit-test bounds. Both are justified: the scripted provider has no hold, and the bounds are the I2 caps (2 arms x 2 sends, then 4+4 for limit+start).
- F8: `inFlight` is now cleared last. The only early return after the old clear point is the QUEUE_DETAILS one, which clears it itself, so no path leaves it set. `plan` and the ride check read it lock-free, and now see no stale paid fields.

## Findings
R1 Low (Desired.py:360 with Reconciler.py:337): A failed wake that returns ERROR ("state", or an HTTP-level failure from _paidPost) sets `paidReached` (kind != UNREACHABLE), so the F1 re-arm is blocked and the desire is stranded after 2 wakes, as before the fix. Asleep/waking/offline, the realistic cases, are fixed. Optional: `paidReached |= outcome.kind != UNREACHABLE and not failedWake`, which needs a test row. Otherwise document it.
