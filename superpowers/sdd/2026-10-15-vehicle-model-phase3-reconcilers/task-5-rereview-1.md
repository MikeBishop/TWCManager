# Task 5 re-review 1: fix round 1 (81dc39b..098f7c8)

**Verdict: NOT CLEAN.**
- Fixed: I1, M1's paid leak, M3/c4, M4 and L1–L4.
- One new Important issue: the M1 fix deletes the user's tokens when a token refresh fails transiently (N1).
- M2, M5, M6 and M7 are unchanged, as the coordinator listed.

## Verification

- Focused tests at 098f7c8 pass: 114 tests across these files:
  - `test_provider_outcomes_cloud.py`, `test_teslaapi_token_slots.py`, `test_teslatokenslot.py`
  - `test_targeted_charge_limit.py`, `test_carapivehicle_registry.py`, `test_homeassistant_registry.py`
- `black --check` is clean on the 3 touched lib files.
- `probe-p3t5/probe_new.py`: 84 passed, 4 failed. The 4 failures are exactly the finding tests that asserted the old defects:
  - `test_412_on_a_command_keeps_paying`
  - `test_412_on_wake_with_owner_slot`
  - `test_expired_401_refresh_not_configured_keeps_posting`
  - `test_reason_is_echoed_into_log`

  Each one now fails because its defect is fixed.
- `probe-p3t5/probe_rereview.py` is new and passes 23 tests:
  - **Refused-token sweep.** It covers 32 cases: {plain 401, expired 401 that cannot refresh, 403, 412} × {first refusal on a command, first refusal on a wake} × {Fleet only, Fleet plus Owner}. In each case one paid request reaches Tesla. Then 40 rounds over 4 injected hours, of every Fleet method plus `wake`, send **0** more. `slotFor("command")` is None afterwards. A command 412 leaves `pausedUntil == 0`, so reads are not latched, and with an Owner slot present, Owner still serves reads.
  - The other tests cover N1, the cost of M2, and the 600 s need grace.
- `probe-p3t5/probe_compare.py` has been re-run. Counts are in `counts-base.json`, `counts-81dc39b.json` and `counts-new.json`. Only the 412 rows moved: for 3 dispatches, base sent 3, 81dc39b sent 6, and 098f7c8 sends 1.

**No paid request now reaches a refused token: confirmed.**

## Status of each finding

| Finding | Status | Notes |
|---|---|---|
| I1 | **Fixed** | A 412 on a command or wake calls `commandRefused(slot, 412)`, then `slot.refuse("command")`. Reads are untouched (`TeslaAPI.py` 412 branch of `_paidPost`). A read 412 still latches reads only. Legacy `readOnly` follows, so the legacy paths stop too. |
| M1 | **Fixed for cost; see N1** | `not_configured` and every other failed refresh now go to `commandRefused(slot, 401)`. |
| M3/c4 | **Fixed (backstop)** | `lastChargeNeededTime` and `CHARGE_NEED_IDLE_SECONDS = 600`. A need with no ask for 600 s restarts its `wakeDelayMins` grace. Probe: a one-shot wake held an hour ago, then steady asks, honours the full 180 s grace before the one wake. The legacy cadence is fine: `TWCSlave` calls `startCarsCharging` every heartbeat while it offers ≥ min with no draw. The UX gap remains: the first debug wake comes back "wake held". |
| M4 | **Fixed** | `getCarApiRetryRemaining(vehicle, now)`; `wakeDue`, `wakeOutcome` and `command` pass the injected clock. `updateCarApiLastErrorTime` still stamps the wall clock, which errs toward fewer calls. |
| L1 | **Fixed** | `lastVehicleAwakeChecked` is restored on a cache hit. |
| L2 | **Fixed** | `wakeOutcome` returns `UNREACHABLE "backoff"` before the free check. |
| L3 | **Fixed** | Only a reason matching `[a-z_]{1,40}` is carried; anything else becomes "not accepted". |
| L4 | **Fixed** | An `HTTPError` with no response gives `ERROR "HTTPError"`. |
| M2, M5, M6, M7 | Not fixed (as listed) | M2 is judged below. |

## New findings

### N1 (Important): a transient refresh failure deletes the user's tokens

Location: `TeslaAPI.py`, `_paidPost` 401 branch. The `refreshSlot` result now falls through to `self.commandRefused(slot, 401)`.

`TeslaTokenSlot.refresh()` returns `"rejected"` for any failure that got an HTTP response. That includes an auth-server 500, 502 or 503, a parse error, or an unexpected exception. Only a connection failure returns "unreachable".

So when a command meets an expired token and the refresh then gets a 5xx, the code now calls `slot.clear()`, which wipes the access token **and the refresh token**, and then queues `saveSettings`. Probe `test_transient_refresh_failure_deletes_the_token[500|503|400]` shows the slot empty with `refreshToken == ""`.

The user must log in again before Fleet control returns. Base never cleared on this path: `slotRequestFailed`, legacy `wakeVehicle` and `car_api_charge` all keep the slot when a refresh fails, unless the refresh itself got a 401, which `refresh()` already clears.

This costs no money, but it destroys credentials on a transient Tesla error. It is rare, because `refreshTokenIfNeeded` normally refreshes an hour before expiry, but it can't be undone.

**Fix:** in that branch, for any result other than `"success"` or `"unreachable"`:
- call `slot.refuse("command")` (log once) instead of `commandRefused(slot, 401)`;
- leave the slot to `refresh()`'s own 401 clear;
- leave `refreshSlot`'s backoff in place.

A later successful background refresh calls `setTokens`, which lifts the refusal. `not_configured` stays refused until the token changes, so M1's cost fix still holds. Add a test: a 503 from the refresh leaves the refresh token in place, sends no further command, and a later `setTokens` re-enables commands.

### N2 (Low): a long gap restarts the grace

Location: the `_askChargeNeed` call in `car_api_available`.

A global backoff lasts at most 600 s. If the next ask comes just over 600 s after the last one, the need counts as ended and the `wakeDelayMins` grace restarts. This only delays a wake by `wakeDelayMins`, so it is cost-safe. Note it for Task 8.

## Paid-call changes vs f394844: 23

This is the 20 from the first review, updated, plus 3 new (marked **NEW**).
- **Increases (8):** 4, 6, 7, 8, 13, 14, 15, 20. All except 4, 15 and 20 are on the c3 dispatch path. 20 is now narrowed.
- **Decreases (15):** 1–3, 5, 9, 10–12, 16–19, 21–23.

**Debug path**
1. A wake on an online car goes from 1 per click to 0. *Decrease.*
2. A wake on an asleep car with the default `wakeDelayMins`: the first click is held. *Decrease.*
3. No blind wake when the check fails. *Decrease.*
4. The same rate within 600 s goes from 0 to 1 per click. *Increase (accepted).*
5. A failed debug wake arms the 30-min hold. *Decrease.*

**`VehiclePriority.setAmps` dispatch (c3)**

6. The same rate within 600 s is resent. On the live path `VehicleEndpoint` throttles it. *Increase.*
7. `could_not_wake_buses` goes from 1 to 2. *Increase.*
8. A 500 with a JSON body goes from 1 to 2. *Increase.*
9. **CHANGED:** 3 dispatches that each get a 412 now send 1 post, against 3 at base and 6 at 81dc39b. *Now a decrease.*
10. A plain 401: 1 post in total. *Decrease.*
11. A 403: 1 post in total. *Decrease.*
12. A 429: 1 post, then backoff. *Decrease.*
13. Below 5 A, where the first post succeeds and the second fails: 2 posts become 3. *Increase (mixed).*
14. HA `setAmps` always posts. *Increase.*

**Policy paths (shared state)**

15. An Owner read 412 latches Owner reads until the token changes, so reads stay on paid Fleet. *Possible increase, by design.* Unchanged.
16. A 403 on the new path makes the legacy paths read-only. *Decrease.*
17. A 401 on the new path clears the slot. *Decrease.*
18. A 429 on the new path backs off the legacy paths too. *Decrease.*
19. A failed `wakeOutcome` holds legacy wakes for 30 min. *Decrease.*
20. **NARROWED:** a held one-shot wake leaves `firstChargeNeededTime` set for at most 600 s, down from indefinitely. A legacy need that arrives inside that window can still wake up to `wakeDelayMins` earlier than at base. *Small increase.*
21. **NEW:** a need with no ask for 600 s restarts its grace on both the legacy and new paths (N2). *Decrease: wakes come later.*
22. **NEW:** a 412 on a command or wake on the new path retires `command`. `readOnly` becomes True, so legacy `car_api_available`, `car_api_charge`, `setChargeRate` and `applyChargeLimit` stop too. *Decrease.*
23. **NEW:** an expired 401 whose refresh fails other than by being unreachable clears the slot (the M1 fix). Every paid path stops until the user logs in again. *Decrease, but see N1.*

## M2: does a 403 on wake_up retiring `command` cost the user anything real?

**Money: no.** A refusal only stops requests. `test_wake_403_cost` shows the next `setAmps` returns `REFUSED "no command token"` with 0 posts, and `readOnly` becomes True.

**Function: yes, but only in a narrow configuration.** For the 403 to happen at all, the free check must have answered. If the Fleet token cannot read, that needs an Owner slot: with Fleet alone, the check fails first and no wake is sent. So the case is:
- a TeslaMate or Owner token for reads; and
- a Fleet token that can command but that Tesla refuses `wake_up` for. If Tesla files `wake_up` under `vehicle_device_data` (verify this), that means a Fleet token granted charging commands without device data.

In that case, one 403 on a wake stops every Fleet charge command (`set_charging_amps`, start, stop, limit) until the token changes or the process restarts. That is commands the token could have sent, and the user loses Fleet charge control. The ERROR log also points the user at the wrong scope: `reportScopeRefused("command")` says "lacks the vehicle_charging_cmds scope".

A 403 on a wake for any other reason, such as an unsigned command or an unpaired key, would refuse commands anyway, so retiring them there costs nothing.

**Ruling: keep M2 Minor and defer it. It costs no money, and the functional loss needs an unusual scope grant.** A cheap partial fix when Task 6 touches `ready(WAKE)`:
- give `wake_up` its own refused purpose, and let `FleetAPIProvider.ready(WAKE)` check it; or
- skip the wake when the command slot's `missingScope("read")` is set, since the scope is known locally from the token's `scp` claim.
