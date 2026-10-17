# Slim Task 9, re-review after fix round 1 (3fbb5e4..d2a7a57)

**Verdict: CHANGES REQUIRED.** One new Important finding: N1, a regression caused by the I2 cap. It came in through the fix I suggested myself. C1, I1, I3 and M1–M5 are resolved, and I2's cost cap holds.

## How this was checked

- **Own tests:** at d2a7a57 the brief's four files plus `test_provider_tables.py` give 244 passed.
- **Probe:** `scratchpad/probe-slim9`, run against d2a7a57. The results are in `results-d2a7a57.json`, with the earlier run kept as `results-3fbb5e4.json`.
  - Two new rows were added.
  - The conftest now takes `PROBE_W`, so the same probe also ran against a `git archive` of 3fbb5e4 at `scratchpad/src-3fbb5e4` for comparison.
- **Off-by-one in my probe:** `test_new_stop_held_behind_a_start_wake_held` was off by one, as the coordinator suspected. The loop now checks after each pass, and a first-pass send reports `waited == 0`.
  - `test_stop_while_start_in_flight` has the same off-by-one: its "after 10 s" is the first pass.

## Findings from the first review

| Finding | Status | Evidence |
|---|---|---|
| C1: a superseded attempt settles the new desire | **Resolved** | `Desired.py:354-360`: `current` requires the desire present, the same value, and `since >= at`. Only a current attempt writes `lastOutcome`, `lastSentAt`, `lastFreeAt`, `paidSends`/`paidAt`/`paidRetryDue` or `settledAt`. Probe: 50→60 in flight sends bodies [50, 60]; a stop while a start is in flight is sent on the next pass. |
| I1: the NOT_SENT hold spans desires | **Resolved** (deviation accepted) | `newDesire()` clears `lastOutcome`/`lastOutcomeAt` (`Desired.py:130`). Probe: the new stop after a start's "wake held" goes on the first pass. |
| I2: newer readings re-arm paid sends without limit | **Resolved for cost; introduces N1** | `paidSends < 2` cap plus `unlike=paidSaw` (`Reconciler.py:317-328`). Probe: 500 plus a 1-minute poll gives 2 paid/h (was 12); a stale-feed stop gives 1/h (was 50). |
| I3: pre-write read age equals the paid window | **Resolved** | The blind retry has `maxAge=None`; a paid attempt uses `READ_MAX_AGE + PAID_AFTER` (`Reconciler.py:344-352`). Probe: 500 then 500 gives 2 commands and 0 data; the slow-BLE fallback gives 1 command and 0 data. |
| M1: a satisfied restore leaves the held record | **Resolved** | It saves `HeldLimit(current, None)` and clears the desire. |
| M2, M3, M4 | Unchanged, as ruled | — |
| M5: line budget | Noted | `Reconciler.py` is 441 lines. |

### Is the I1 deviation equivalent to storing `attempt.since`?

Yes, given C1. A report writes `lastOutcome` only when the attempt is current: the same value and `attempt.since >= desire.at`. Every case where a new desire follows an attempt:

| Case | Result |
|---|---|
| A late report of the old desire's attempt | `newDesire()` has already cleared the hold, and the report is not current, so it cannot write the hold again. |
| A→B→A | The second A has a newer `at` than the first A's attempt `since`, so that attempt is not current either. |
| Adoption | `adopt()` does not call `newDesire()`. It needs no reset: adoption happens only in `plan()` with nothing in flight, and the adopted value is satisfied. |

So a late report can never re-hold a new desire.

### Do `paidSends` and `paidSaw` reset on a new desire?

Yes. `newDesire()` zeroes `paidSends` and clears `paidSaw`, `paidAt` and `paidRetryDue`. `test_a_new_desire_resets_the_per_desire_stamps` covers it, and the probe's 50→60 row sends the second value as paid send 1 of the new desire.

## Probe at d2a7a57: every row

Rows are paid command / paid wake / paid data, then BLE commands.

| Scenario | d2a7a57 | Notes |
|---|---|---|
| BLE ok | 0/0/0, BLE 1 | Unchanged |
| BLE down 60 s (< window) | 1/0/0, BLE 1 | Unchanged (M3) |
| BLE down > window | 1/0/0 | Unchanged |
| BLE fails slowly (20 s), Fleet fallback | 1/0/**0** | Was 1/0/1 |
| BLE stale, BLE ok / BLE fails | 0 / 1 | Unchanged |
| Fleet-only DONE | 1/0/0 | Unchanged |
| Fleet-only, limit an hour stale | 1/0/1 | A genuinely stale reading; read once |
| Fleet 500 then 500 (12 h) | **2/0/0** | Was 2/0/1 |
| Fleet 500 ×2 on a raise | 2/1/0 | The retry never wakes |
| Wake held 30 min | 1/0/1 | 0 paid during the hold; 30 submits |
| Restore to an absent car, BLE+Fleet | 2/0/0, BLE 6 | No wake, BLE hourly |
| Restore to an absent car, BLE only | 0, BLE 7 | Hourly |
| Pairing window open | 0 | — |
| respectVehicleSchedule pending | 0 | — |
| User sets limit in the app | 0, BLE 2 | — |
| Desire changes while queued | 1/0/0 | 50 cancelled unsent |
| Desire changes while in flight | 2/0/1 | [50, 60]. The data read is the accepted $0.002 |
| Stop while a start is in flight | 2/0/1 | Stop on the next pass. Accepted read |
| New stop after a start's wake held | 1/0/0 | First pass |
| Fleet 500 plus 1-minute poll (1 h) | **2** | Was 12 |
| SATISFIED stop plus stale "Charging" feed (1 h) | **1** | Was 50 |
| Reconciler thread | — | 3 idle passes in 3.2 s; wakes coalesce; stops |
| **NEW:** Fleet-only lower to a sleeping car (408 ×2), the car wakes 2 h later to charge | **limit never sent; start sent** | At 3fbb5e4 the limit was sent again before the start (N1) |
| **NEW:** desire set during a pass (pass `now` < `d.at`), Fleet 500 | **3 paid sends** | N2 |

- **At most 2 paid sends per desire:** holds in every original row. It fails only in N2's race. The wake on a raise is the attempt's own wake, not a third send.
- **No lost command when a desire changes in flight:** holds (both in-flight rows). N1 is a different way to lose a command.
- **No lock violations** in any row.

## New findings

### Important

**N1. On a Fleet-only install, a limit whose two paid sends found the car asleep is never applied for that desire, so the car charges past the policy limit.**
- Where: `Reconciler.py:317-328`.
- What happens:
  1. A lower needs no wake, so with the car asleep both paid sends fail (408, UNREACHABLE) and `paidSends` reaches 2.
  2. The cap then stops every later paid send. The policy re-setting the same value is not a new desire.
  3. `unlike=paidSaw` blocks it as well: the woken car still reads 90, which is what the failed sends saw.
  4. When the heartbeat later starts charging, the start wakes the car and goes out. `LIMIT_THEN_START_GAP` only waits while a limit is in flight or was just written.
- Probe: the POSTs are `set_charge_limit 50, set_charge_limit 50, charge_start`. At 3fbb5e4 they were `…50, …50, set_charge_limit 50, charge_start`.
- This came from the I2 fix I suggested in the first review. Either of my two options (the value-change rule or the hard cap) causes it.
- Fix: let paid sends that only found the car unreachable (UNREACHABLE: asleep or 408) re-arm once the car is known to be reachable. The cap and `unlike` keep governing failures from a car that answered (ERROR, SATISFIED).
  - Concretely: record `rec.paidUnreachable` (every paid send of this desire was UNREACHABLE).
  - While that is set, any reading of the field newer than `paidAt`, of any value, resets `paidSends` to 0, once per reading.
  - A sleeping car produces no readings, so this pays nothing while it sleeps, and at most 2 more sends after each wake.
- Pin it with a test of this shape: the limit 50 is sent before `charge_start`.

### Minor

**N2. A desire set during a pass, after that pass sampled `now`, gets an attempt that is never "current".**
- Where: `Reconciler.py:358` (`since=now`) and `Desired.py:354-360`.
- What happens: `plan()` reads the new desire but stamps `since=now`, and that is less than `d.at`. The outcome is then dropped: no `paidSends`, no hold, no settle. The next pass gives the desire a full budget again.
- Probe: forcing the pass's `now` just before the set gives 3 paid sends over 12 h.
- The race window is the time between the start of a pass and planning that key, which is milliseconds. It costs at most one extra paid send.
- Fix: `since=max(now, d.at)`, or carry `d.at` in the Attempt and test `attempt.desiredAt == want.at` instead of `since >= at`.
