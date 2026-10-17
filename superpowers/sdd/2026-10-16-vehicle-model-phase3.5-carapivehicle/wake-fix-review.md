# Review: wake follow-up fix (2a973cc0 on rebase/phase3, 58c43197 on rebase/phase3.5)

Date: 2026-10-17. Read-only review. Temporary worktrees for both tips and the probe files are removed; `wt-rebase` is untouched and clean.

**Verdict: approve.** The root cause is correct and the fix is small and correct within its scope. One Medium residual needs a human decision (F1). It is not a regression: before the fix the limit was stranded in every case, not only the late ones. Q3's one-line change is recommended (F2).

Tests I ran on tips without changes, `tests/unit`: phase3 1769 passed, phase3.5 1855 passed, 0 failed. These counts differ from the report's 1778/1864 + 1 xfail, probably because the two runs collected different test sets. That needs no action.

## Findings

| # | Sev | Where | Finding |
|---|---|---|---|
| F1 | Medium | Reconciler.py:349-361 (3.5) | A Fleet-only car that comes online *after the second wake* is stranded again. With a limit only, online at +2400 s or +4000 s: two wakes (t=2, t=1922), `paidSends=2`, and no command in 4 h. Nothing plans another attempt because `paidSends<2` is false, there is no reading to re-arm, and nothing else polls. main delivers it, because it re-wakes every 30 min indefinitely. Cars that answer within about 30 min are fixed. This is the I2 cap working as designed, but it is the same symptom as the original bug. Decide: (a) accept it and document it in the parity table, with a row pinning it, or (b) let a spent arm whose last send was a failed wake use the desire's one re-arm (`... or rec.wakeCheckBy` in the re-arm condition). That costs at most 2 more wakes (I2's 4-per-desire still holds) and moves the stranding out to about 93 min. |
| F2 | Low | Reconciler.py:262 | H2 spaces the later free checks for a limit 300 s apart. Measured latency from the car coming online to the command is 120 to 220 s. main polls every 60 s, but only for the first 10 min. See Q3. |
| F3 | Low | Provider.py:84-85 | The hold contract is documented, not enforced. A test-only guard is cheap: for every registered provider declaring WAKE at TIER_BILLED, a second `wake()` within WAKE_CHECK after a failed one returns NOT_SENT `"wake held"`. This adds no lib lines. |
| F4 | Low | Desired.py:362-364 (3.5) | The name `woke = not detail.startswith("wake ")` reads inverted: it means "not a failed wake". Rename it, e.g. `failedWake = retry and outcome.detail.startswith("wake ")`. Then `paidRetryDue = paidSends == 0 and retry and not failedWake` and `wakeCheckBy = attempt.provider if failedWake else None`. Same line count, clearer. |
| F5 | Low | Reconciler.py:359 | `bool(paid)` is redundant. Only truthiness is used (`if paid and freeFailed and paidAgain`), so `and paid and paid[0].name == rec.wakeCheckBy` is enough. |
| F6 | Low | Reconciler.py:6-10, 72-75, 354-356; Provider.py:84-85; Desired.py:115-117 | The comments say "the provider holds its wake, so this is a free online check" four times. Keep the contract on `Provider.wake` and the `WAKE_CHECK` constant comment. Revert the header back to its original sentence plus "or, after a wake the car did not answer, one follow-up through the same provider (WAKE_CHECK)", and cut the clause comment to one line. That is about -5 lib lines, so the net is roughly +14/+12. |
| F7 | Low | test gap | There is no Gen3-without-BLE row. By reading the code, its limit takes the same Fleet-only path (Gen3TWCProvider declares no WAKE or limit) and its start is local, so it is unaffected. There is also no row for "car online after the 2nd wake" (F1). Add one either way, as an xfail if F1 is accepted. |
| F8 | Info (pre-existing) | Desired.py:332 vs Reconciler.py:247 | `noteOutcome` clears `inFlight` first, then writes `lastSentAt` and the paid fields under the store lock. `plan` reads `inFlight`, then the fields, without the lock. So a planner pass racing a cloud report can see `inFlight=None` together with stale `paidSends`, `lastSentAt` or `wakeCheckBy`. The fix adds one more field to that window. It does not widen the window or create it. Out of scope, but cheap to fix: clear `inFlight` last. |

## Q1: root cause and minimality

The root cause is confirmed by reading the code. A failed paid wake comes back as RETRYABLE `"wake …"`, and `noteOutcome` sets `paidSends=1` and deliberately leaves `paidRetryDue=False` (M8). `plan` then needs `paidRetryDue` or `reached`, and the re-arm needs a reading, a ride or charging. With `free == []` and no telemetry, nothing produces any of these.

Can an existing mechanism express it?

- **paidRetryDue:** no. It makes the attempt blind (`wake=False`, `maxAge=None`), which is exactly the blind write M8 forbids.
- **H2:** no. It only suppresses attempts and never plans one.
- **Re-arm:** possible, but it spends the desire's single re-arm on the first failure. It resets the arm to 2 more paid sends, so a car that never answers gets 3 wakes per desire before stranding instead of 2. It also needs a new trigger anyway.
- **Deriving instead of storing:** `rec.lastOutcome` plus `rec.lastProvider` could stand in for `wakeCheckBy` (`"wake held"` also starts with `"wake "`). But a free provider's outcome overwrites `lastOutcome` in the BLE-down case, so the follow-up would be lost. The field is the robust choice.

The provider-name match matters. It keeps the follow-up from going to a different billed provider (HA) that cannot wake, which would otherwise make a blind write. The `wakes` guard matters for the same reason. **The fix is the smallest correct one.**

The wake outcomes that set `wakeCheckBy` were checked in `TeslaAPI.wakeOutcome` (3.5 TeslaAPI.py:1522-1600):

- `asleep`, `waking`, `offline` (UNREACHABLE), `state` (ERROR) and HTTP-level failures from `_paidPost` all set `delayNextWakeAttempt=1800` before returning.
- The three early returns (`wake refused`, `signing required`, `owner commands retired`) are NOT_SENT, so they never set the field.

The hold is per car (`car.delayNextWakeAttempt`), so Fleet and Owner share it.

## Q2: paid-spend bounds

The existing parity rows are unchanged; only row 4b's expectation changed, from xfail to pass. Probes on 58c43197 (4 h runs, step 1 s, t relative to the policy change):

| Scenario | Wakes | Paid (vd, wake, cmd) | Result |
|---|---|---|---|
| Fleet-only limit, online +59 s | 1 | (1,1,1) $0.023 | sent 61 s after online |
| online +300 s / +600 s / +1700 s | 1 | (1,1,1) | sent 120 / 120 / 220 s after online |
| online +2400 s / +4000 s | 2 (t=2, 1922) | (0,2,0) | **never sent (F1)** |
| never online, limit | 2 | (0,2,0) | stops; 8 free GETs |
| never online, limit + start | 5 (t=2, 1922, 3723, 5583, 7442) | (0,5,0) | stops |
| limit + start, online +600 s | 1 | (1,1,2) | limit then start |
| limit + start, online +2400 s | 2 | (1,2,2) | start first (limit spent, c4), then limit via the charging re-arm |
| prefer_ble, BLE down (radio silent), online +59 s | 1 | (1,1,1) | 8 BLE runs; Fleet path identical |
| prefer_ble, BLE down, online +2400 s / never | 2 | (0,2,0) | same strand as F1; 180 BLE runs (free, pre-existing cadence) |
| Fleet + HA, online +59 s / never | 1 / 2 | (1,1,1) / (0,2,0) | HA never called (`ha=0`): `wakeCheckBy` pins Fleet |
| Owner "off" (3.5 row) | 1 Owner wake_up | (0,0,0) | passes; Owner wakes are free but TIER_BILLED and use the same hold |
| Gen3 without BLE | by reading | — | start is local and free (no wake). Limit is identical to the Fleet-only rows |

- **Caps:** at most 2 paid sends per arm. The limit's desire took 4 wakes over its 2 arms (ride re-arm) and the start took 1 (5 in total), inside I2.
- **No paid resubmit loop:** during the hold every follow-up is NOT_SENT `"wake held"`, spaced by H2.
- **Worst case wakes/hour:** at most 2/h per car, because the provider's 1800 s hold applies whatever the desire churn is. The peak was 3 in the first 62 min (t=2, 1922, 3723). main's steady state is also 2/h, but main never stops, while here the total is bounded (5 in about 2.1 h, then 0).

## Q3: H2 cadence

Yes. It is a one-line, safe change at Reconciler.py:262:

```python
and now - rec.lastOutcomeAt < (WAKE_CHECK if rec.wakeCheckBy else RETRY[aspect])
```

Measured with it applied: latency from online to command dropped to 60 to 120 s (+300 s case: 120 → 60 s; +1700 s case: 220 → 100 s). All of `tests/unit` passes except the free-GET bound in `test_fleet_only_car_never_online_after_an_offline_wake_is_woken_twice` (`< 10`), which becomes 17 in 4 h. Raise it to about `< 20`.

It is safe because:

- Only free checks are added. Wakes stay bounded by the provider hold and by `paidSends`.
- Once `paidSends == 2` the planner returns before anything is sent.
- For CHARGING it lengthens 60 → 120 s, which costs nothing because the online check is cached for 120 s. Use `min(WAKE_CHECK, RETRY[aspect])` to keep 60 s if preferred.

## Q4: hold contract and HomeAssistant

The contract is documented only (Provider.py:84-85), not enforced (F3). Today it holds for every provider that can set `wakeCheckBy`. Only OwnerAPI and FleetAPI declare WAKE at a billed tier, and both go through `wakeOutcome`. TeslaBLE is local and free, so its outcome never takes the paid branch.

HomeAssistant is unaffected. It does not declare WAKE (HomeAssistantProvider.py:1-3, DECLARATIONS), so `Run._wake` never runs for it and it can never be named in `wakeCheckBy`. Any wake HA's own integration makes as part of a service call is invisible here and is counted as an ordinary paid send. If Fleet's wake failed, the provider-name match keeps the follow-up off HA (probe: `ha=0`).

## Q5: rewritten M8 test

The new expectation is right. The scripted Fleet stub has no hold, so it shows the worst case of concern 1: 2 paid wakes, `paidSends == 2`, never a blind `setChargeLimit`, and nothing more over 6000 s. The test name and the M8 property (no blind retry after a failed wake) still hold. Optional: assert that the second wake is at least WAKE_CHECK after the first.

## Q6: threads and locks

- No new locks.
- `wakeCheckBy` is written only in `noteOutcome` under the store's leaf lock. It is reset in `newDesire()`, which is called under the same lock, and read lock-free in `plan`, the same as `paidRetryDue`. The worst outcome of a stale read is a follow-up one pass late. It can never add a paid send, because `paidSends < 2` and the provider hold still bound it.
- No I/O under any lock.
- The lock order (`_bleLock` → settingsLock → registry leaf; vehicleListLock → settingsLock) is untouched.
- There is one pre-existing race window (F8).

## Q7: lib size

The logic itself is minimal: the field, its reset, its assignment, the hoisted `wakes` and the clause. The cuts are F6's comment consolidation (about -5) and F5 (style only, no lines). F4 is neutral. I found no other duplication.
