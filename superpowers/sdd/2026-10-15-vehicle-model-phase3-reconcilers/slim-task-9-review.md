# Slim Task 9 review: charge-limit rules and the reconciler with the one fallback rule

**Range:** cf63e52..3fbb5e4 (c4cbc50, 1b69ec0, fd3f25f, 3fbb5e4), checkout `scratchpad/wt-vm3`.
**Probe:** `scratchpad/probe-slim9/test_probe_slim9.py` (results in `probe-slim9/results.json`). It drives the real `VehicleReconciler` and real `Workers`, inline and threaded. The providers are the real `TeslaBLEProvider` (a real `TeslaBLE` module with `sendCommand`/`get_charge_state` scripted) and the real `FleetAPIProvider` (a real `TeslaAPI` with a Fleet token; HTTP through `requests_mock`). Every request to the Fleet host is counted: POST `command/*`, POST `wake_up` and GET `vehicle_data` are paid; GET `vehicles/{vin}` is free.
**Own tests:** the brief's four files plus `test_provider_tables.py` give 236 passed. Every test the brief names exists.

## Verdicts

- **Spec compliance: PASS.**
  - `Rules.py` matches `presence/2-charge-limits:lib/TWCManager/ChargeLimitRules.py` line for line. The only differences are the HeldLimit mapping, the `held` → `isHeld` rename and the 50–100 clamp on `desired`/`held.outside`. Every branch and every reason string is unchanged.
  - `plan()` follows the brief's pseudo-code step by step.
  - The deviations are benign and declared: `handsOff(..., config)`, the explicit `_ORDER`, and pairing counted as free-channel success (L52).
  - Carries (a)–(d) are done as stated.
- **Task quality: CHANGES REQUIRED.** There is one Critical finding (a superseded attempt's outcome settles the new desire, so a stop is never sent) and three Important findings, all about cost or delayed commands. Two of the Important findings come from the brief's own pseudo-code and conflict with the hard cost constraint, so they need a coordinator ruling and not just an implementer fix.

## Scenario table (paid = Fleet command + wake_up + vehicle_data)

| Scenario | Paid cmd | Paid wake | Paid data | Free GET | BLE cmd | Result |
|---|---|---|---|---|---|---|
| BLE ok (limit 90→50, 1 h) | 0 | 0 | 0 | 0 | 1 | OK; HeldLimit(90,50) |
| BLE down 60 s (< window), back before +300 | 1 | 0 | 0 | 1 | 1 | 0 paid before +300. At +300 the paid window and BLE's next try fall due together, and Fleet wins (Minor M3) |
| BLE down > window (6 h) | 1 | 0 | 0 | 0 | 1 | OK: none before +300, 1 at +300, never again |
| BLE fails slowly (20 s), Fleet fallback (1 h) | 1 | 0 | **1** | 1 | 1 | The fallback pays a `vehicle_data` too (I3) |
| BLE stale (>600 s), BLE ok | 0 | 0 | 0 | 0 | 1 | OK: real command over BLE first |
| BLE stale (>600 s), BLE fails | 1 | 0 | 0 | 0 | 1 | OK: paid on the next pass |
| Fleet-only, limit DONE (6 h) | 1 | 0 | 0 | 0 | 0 | OK |
| Fleet-only, stale limit (1 h) | 1 | 0 | 1 | 1 | 0 | Pre-write read is a paid `vehicle_data` (I3) |
| Fleet 500 then 500 (12 h) | **2** | 0 | **1** | 1 | 0 | Exactly 2 commands, but the retry's pre-write read adds a paid `vehicle_data` (I3) |
| Fleet 500 ×2 on a raise (12 h) | 2 | 1 | 0 | 2 | 0 | OK: `wake_up, set_charge_limit, set_charge_limit`; the retry never wakes |
| Wake held 30 min (Fleet start, wakeDelayMins 30) | 1 | 0 | 1 | 16 | 0 | OK: 30 submits, 0 paid and 15 free GETs during the hold; then a read and the start |
| Restore to an absent car (BLE down, Fleet 408, 6 h) | 2 | 0 | 0 | 2 | 6 | OK: no wake; Fleet 2 (one blind retry); BLE hourly |
| Restore to an absent car (BLE only, 6 h) | 0 | 0 | 0 | 0 | 7 | OK: hourly, never a wake |
| Pairing window open (30 min) | 0 | 0 | 0 | 0 | 6 | OK: ERROR "pairing" holds paid |
| respectVehicleSchedule pending (start, 1 h) | 0 | 0 | 0 | 0 | 0 | OK: hands off for every provider |
| User sets 80 in the app, policy repeats 50 ×5, then a decision | 0 | 0 | 0 | 0 | 2 | OK: adopted, HeldLimit(80,None), 1 BLE command before the decision and 1 after |
| Desire changes while queued (50→60) | 1 | 0 | 0 | 0 | 0 | OK: 50 cancelled unsent, only 60 sent |
| **Desire changes while in flight (limit 50→60)** | 1 | 0 | 0 | 0 | 0 | **60 never sent** (C1) |
| **Stop while a start is in flight (no feed, 1 h)** | 1 | 0 | 0 | 1 | 0 | **Stop never sent in 1 h** (C1). With the fix candidate it is sent on the next pass |
| New stop after a start's "wake held" | 1 | 0 | 0 | 1 | 0 | **Stop delayed 56 s** (I1). With the hold scoped per desire it goes on the first pass |
| Fleet 500 forever + a 1-min poll of the same value (1 h) | **12** | 0 | 0 | 0 | 0 | Cap of 1 + 1 broken (I2) |
| Stop SATISFIED `not_charging` + a feed still saying Charging (1 h) | **50** | 0 | 0 | 0 | 0 | Cap of 1 + 1 broken (I2) |
| Reconciler thread | – | – | – | – | – | OK: 3 idle passes in 3.2 s, 200 wakes coalesce into 1 pass, stops and joins |

### Hard constraints

- **At most one paid call per desire, plus one retry after a failed send:** FAILS in two cases.
  - A newer reading re-arms the paid budget without limit (I2).
  - The pre-write read adds paid `vehicle_data` calls on top of the commands (I3).
- **The retry never wakes:** holds (`wake_up, set_charge_limit, set_charge_limit`). A failed wake gets no blind retry.
- **Free before paid:** holds. Paid goes only when there is no free candidate, the free channel has failed for PAID_AFTER, or the stale-probe BLE try has just failed. Pairing holds paid.
- **No paid call before the window:** holds (0 paid at +299 s and at +60…+299 s).
- **Reconciler thread bounded and stops:** holds. The wait is bounded by TICK; `stop()` exits within one wait; repeated wakes coalesce.
- **No submit or cancel under the DesiredStore lock:** holds. The probe wraps `submit`, `cancel`, every Fleet HTTP handler and BLE `sendCommand` with a `desired._lock.locked()` check, and found 0 violations in every scenario. By inspection, `report()` takes only `noteOutcome`'s leaf lock and calls `wake()`.

## Findings

### Critical

**C1. The outcome of an attempt made for a superseded desire settles, and spends the paid budget of, the new desire.**
- Where: `lib/TWCManager/Vehicle/Reconcile/Desired.py:337-360` (`noteOutcome`), which feeds the settled gate at `Reconciler.py:276-281` and `paidAgain` at `Reconciler.py:312-315`.
- What happens:
  1. `set()` calls `record.newDesire()`, which resets `settledAt`/`paidAt`/`lastFreeAt` while the old attempt is still `inFlight`.
  2. When the old attempt reports, `noteOutcome` accepts it, because the `inFlight is attempt` check passes, and writes `settledAt = now`, `paidAt = now` and `lastFreeAt = now` onto the new desire's record.
  3. `plan()` then hits the settled gate: `settledAt` is set and no newer reading has arrived, so it returns None.
  4. `DesiredStore.settled()` also reports the new desire as settled, because `settledAt >= d.at`.
- Probe:
  - A Fleet start in flight, then the distributor sets a stop. The start reports DONE 2 s later. **No `charge_stop` is sent in the following hour.**
  - A limit 50 in flight, then a decision for 60: **60 is never sent.**
  - The stop goes out only after a newer reading and `RETRY`. A car with no feed keeps charging against the decision.
- Fix: in `noteOutcome`, an attempt whose desire has been superseded (`attempt.since < state.desired[aspect].at`, or the desire is gone or its value differs) does three things only:
  - clears `inFlight`;
  - updates the free channel and `excluded` (they do not depend on the value);
  - returns without touching `settledAt`, `paidAt`, `paidRetryDue`, `lastFreeAt`, `lastSentAt`, `lastOutcome` or `lastOutcomeAt`.
- The probe's `test_fix_check_stop_while_start_in_flight` monkeypatches exactly this, and the stop then goes on the next pass.
- Add a reconciler test: a threaded start is gated, a stop is set, the start is released, and the stop must be sent on the next pass. Add a second test for limit 50→60 with the new value sent.

### Important

**I1. The NOT_SENT hold (H2) spans desires, so a new value, including a stop, waits up to RETRY. This is the coordinator's ruling on the hold; the report numbers it concern 2.**
- Where: `Reconciler.py:242-250`.
- Probe: a Fleet start gets "wake held"; 5 s later the car is charging and the distributor sets a stop. **The stop is sent 56 s later.**
- Fix: apply the hold only to the desire whose attempt produced the outcome. Record the attempt's `since` on the record in `noteOutcome` (`record.lastAttemptSince = attempt.since`), and hold only while `rec.lastAttemptSince >= d.at`.
  - Do not compare `lastOutcomeAt >= d.at`. A late report of the old desire's attempt lands after `d.at` and would wrongly hold the new value. That is the same mechanism as C1.
- Verified: with the hold scoped per desire, the stop goes on the first pass (`test_fix_check_hold_per_desire`).
- Update `test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car`, which advances RETRY only to work around this. Add a test that a stop set right after a start's "wake held" is sent on the next pass.

**I2. Any newer reading re-arms paid sends without limit, which breaks the "one paid + one retry per desire" cap.**
- Where: `Reconciler.py:312-315` (`paidAgain … or newerReading(...)`) and `Reconciler.py:276-281` (the settled gate N1).
- What happens: `newerReading` is true for any re-observation, including one of the same value. A polled source (the legacy Owner poll, HA, a feed's periodic republish) therefore reopens the paid path every RETRY for as long as the car disagrees.
- Probe:
  - Fleet keeps returning 500 and a 1-minute poll re-observes limit 90: **12 paid commands/hour** for one desire.
  - A Fleet stop answers SATISFIED `not_charging` while a stale feed keeps saying Charging: **50 paid stops/hour** (bounded only by `RETRY[CHARGING] = 60`).
- This is the brief's pseudo-code, so it is spec-compliant, but it conflicts with the hard cost constraint. **Coordinator ruling needed.**
- Suggested fix: a reading counts as new evidence only when its value differs from the value believed when the paid request was sent. Store `rec.paidSaw = k.value` when a paid attempt is planned, and the same for `settledSaw` on the settled gate. A re-observation of the same value then never pays. Alternatively, cap paid requests per desire at 2 and let only a new desire reset the budget.

**I3. The pre-write read age equals the paid window, so on installs whose only read token is Fleet (or with no live feed), the paid fallback and its blind retry nearly always buy a `vehicle_data` first.**
- Where: `Reconciler.py:47` (`READ_MAX_AGE = 300.0`) and `:340`, with `PAID_AFTER[CHARGE_LIMIT] = RETRY[CHARGE_LIMIT] = 300.0`.
- Probe:
  - "Fleet 500 then 500" sends exactly 2 commands **plus 1 paid `vehicle_data`**, from the retry's pre-write read at about +310 s.
  - "BLE fails slowly (20 s)": the Fleet fallback at failingSince+300 finds the reading 320 s old and pays `vehicle_data` + command.
- At Tesla's prices a data request costs about twice a command, so the fallback costs roughly three commands, not one.
- This is also the brief's constant (spec-level), so it needs a coordinator ruling.
- Suggested fix: for a paid attempt, accept a reading up to `PAID_AFTER[aspect] + READ_MAX_AGE` old, or pass `maxAge=None` on the blind retry (the first attempt already read). Keep READ_MAX_AGE for free providers. Add a probe-style test that counts `vehicle_data` on Fleet-only installs.

### Minor

- **M1 (report concern 4, agree, Low).**
  - Where: `Reconciler.py:261-265`.
  - Problem: a restore already satisfied in `plan()` never reaches the rules. HeldLimit stays (90, 50), `holding()` keeps listing the VIN, and the restore desire stays.
  - Fix: on a satisfied restore, `_save(vehicle, k.value, None)` and `desired.clear(key, CHARGE_LIMIT)`. Task 10 consumes `holding()`.
- **M2 (report concern 5: `inFlight`/`pendingSave` outside the lock).**
  - Where: `Reconciler.py:346` and `:382`.
  - Assessment: correct as written. There is a single writer, the assignment is atomic, and `noteOutcome` reads `inFlight` under the lock.
  - Suggestion: for clarity, add `DesiredStore.begin(key, aspect, attempt)` that sets it under the lock and refuses when something is already in flight. Not required.
- **M3 (spec-level).**
  - Problem: `RETRY[CHARGE_LIMIT] == PAID_AFTER[CHARGE_LIMIT]`, so BLE's next try and the paid window fall due on the same pass, and `plan()` picks paid. A BLE outage of one sample (60 s in the probe) still costs one Fleet call, with no free retry inside the window.
  - Suggestion: prefer a due free try over paid when the channel has only one failure on record. The brief's `test_fleet_waits_for_ble_to_time_out_and_is_sent_once` asserts the current behaviour, so this is the coordinator's call.
- **M4 (report concern 3, agree).** The settled gate's `RETRY` clause is not redundant in every case. In I2's stale-feed case it is the only bound (60 s). Keep it.
- **M5 (report concern 1, line budget).**
  - `Reconciler.py` is 425 lines against the ~360 estimate, under the 550 stop line. The fixes for C1 and I1 add about 10 lines.
  - Places to trim if needed: `_sayOnce` with the `_said` pruning (~12 lines), and the separate `_save`/`_held` wrappers.
  - The re-forecast is the coordinator's.
- **M6 (report concern 6).** AMPS (lift-clear and the stand-in) is untested here. Carried to Task 10 as ruled.
