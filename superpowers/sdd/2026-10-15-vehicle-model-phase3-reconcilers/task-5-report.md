# Task 5 report: cloud provider command methods return Outcomes

**Status:** DONE. One brief-vs-code conflict was resolved in place rather than returned as NEEDS_CONTEXT (deviation 1 below), so the controller can overrule it.

**Commit:** `81dc39b` on `vehicle-model/phase3`, worktree `scratchpad/wt-vm3`, parent f394844.

**Tests:**
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1440 passed, 1 xfailed, 1 warning. That is 1428 + 12 new.
- Step 4 set (7 files): all pass.

## Fail-before

The brief's 7 tests were run against f394844 with the test file in place:

```
E   AssertionError: assert ('unsupported' == 'done'
E   AttributeError: 'bool' object has no attribute 'kind'
E   AssertionError: assert Outcome(kind=... implemented') == Outcome(kind=...disconnected')
E   AssertionError: assert True is False   (ownerSlot.usable('read') after a 412, an hour later)
E   requests_mock.exceptions.NoMockAddress: No mock address: POST .../5YJ3E1EA1KF000001/wake_up
FAILED test_fleet_command_outcomes_and_one_request_each
FAILED test_fleet_401_retires_the_slot_and_403_refuses_the_scope
FAILED test_start_on_a_disconnected_car_is_unsupported
FAILED test_owner_412_is_latched_until_the_token_changes
FAILED test_low_amps_are_sent_twice_and_counted
FAILED test_wake_checks_the_free_online_state_first_and_holds_between_wakes
FAILED test_ha_outcomes_and_per_car_rate_limit
```

The brief predicted `AttributeError: 'TeslaAPI' object has no attribute 'command'`. The real failures differ because the base `Provider` methods already return `UNSUPPORTED`.

## What was built

**`TeslaTokenSlot`**
- `refusedPurposes`: cleared by `setTokens`, `clear` and `restore`. `usable(purpose)` is False for a refused purpose.
- `pause(now=None, latch=False)`: `latch=True` sets `pausedUntil = inf`, and `status()["paused"]` is True for it.

**`TeslaAPI`**
- `self.now = time.time` is set in `__init__`.
- `slotRequestFailed`: a 412 now calls `pause(latch=True)`. The log says the token is not used for reads until it is replaced. A 403 or 410 keeps the one-hour pause.
- `command(vehicle, name, body)` classifies its result as the brief specifies.
- `_paidPost` is a shared single POST with `timeout=10`. It retries only an expired 401, once, and only after a successful refresh.
- `commandRefused(slot, 401)`: clears the slot, queues `saveSettings` and writes one ERROR log.
- `wakeDue(vehicle, now)` and `wakeOutcome(vehicle, now)` are added.
- `_wakeSettled` resets the wake counters.
- `CarApiVehicle.is_awake(slot=None, now=None)` measures its 120 s cache on `now`, which defaults to `carapi.now()`. It also records `lastVehicleAwakeKnown`.
- The legacy `setChargeRate`, `wakeVehicle`, `car_api_available` and `car_api_charge` are untouched.

**`FleetAPIProvider`**
- Adds `clock`, `_car`, `setChargeLimit`, `startCharging`, `stopCharging`, `setAmps` and `wake`.
- `startCharging` maps a `disconnected` result to `UNSUPPORTED`.
- `setAmps` below 5 A sends a second identical post 5 s later, but only if the first post settled.
- `OwnerAPIProvider` declares no commands, so its inherited methods return `UNSUPPORTED`.

**`HomeAssistant`**
- `_post_service` returns an Outcome:
  - A 401 or 403 gives `REFUSED`. The ERROR log is written once, and the flag resets on a success.
  - A timeout gives `UNREACHABLE`.
  - Anything else gives `ERROR` with the status or the exception type name.
- The `[:200]` body log is gone, and exceptions are logged by type name only.
- `_call_service` now returns `_post_service(...).kind == DONE`.

**`HomeAssistantProvider`**
- Adds `_entity`, `setChargeLimit`, `startCharging`/`stopCharging`, and `setAmps` (clamped to 1..32 as float).
- A missing entity gives `UNSUPPORTED "no <kind> entity"`, and an unattached car gives `"not listed"`.
- Start and stop declare `RateLimit(1, 10)`.
- No wake.

**Tests**
- `tests/unit/test_provider_outcomes_cloud.py` holds the brief's 7 tests verbatim plus 5 more. The extra tests cover:
  - An expired 401: refreshes, then sends exactly 2 posts. A second expired 401 after the refresh retires the slot.
  - A 429 causes a backoff, and the next call sends no request.
  - A 412 on a command latches the slot.
  - A failed free online check never wakes the car.
  - A failed wake request (500) is held for 30 minutes.
  - HA never logs `response.text` (checked through caplog, which does capture these loggers).
- The two listed tests were rewritten: `test_fleet_commands_resolve_the_car_by_vin` and `test_home_assistant_provider_follows_entities`.

**Paid-request counts (asserted with `requests_mock` per URL):**

| Call | Paid posts |
|---|---|
| Each command | 1 |
| Low-amps `setAmps` | 2; a 10 A call adds 1 |
| `could_not_wake_buses` | 1, no retry |
| 401 | 1 |
| Expired 401 | 2, with a refresh between |
| Wake when the free check says online | 0, and the 120 s cache saves even the free call |
| Wake while held | 0 |
| Wake allowed after a failed wake | 1, then held until 1800 s pass on the injected clock |

## Deviations from the brief

1. **Brief-vs-code conflict (resolved here; the controller may overrule).** The brief has `reportScopeRefused(purpose, refused=True)` record any purpose. Storm Watch (`TeslaPowerwall2`) and `_energyRefused` already call `reportScopeRefused("energy", refused=True)`. Recording that purpose broke Phase 2's `test_storm_watch_403_does_not_pause_slot`, which expects energy to keep being asked after a 403. So I added `TeslaTokenSlot.RETIRED_ON_REFUSAL = {"command"}`: only a refused command is recorded, and the energy refusal behaviour is unchanged.
2. **`wakeDue` holds only when `delayNextWakeAttempt > 0`.** Taken literally, the brief's `now - lastAPIAccessTime <= delayNextWakeAttempt` fails step 4 of its own wake test: delay 0 on a frozen clock gives `0 <= 0`, which holds. With real `time.time` the change makes no difference. The `wakeDelayMins` check keeps the strict `<`.
3. **Two guards in `wakeOutcome` that the brief does not have:**
   - **No wake without an answer.** `lastVehicleAwakeKnown` means a failed free check (no read token, a network error, a 5xx) returns `UNREACHABLE "online check failed"` instead of sending a blind $0.02 wake. Legacy would wake blind here.
   - **Read-slot fallback.** When the command slot cannot read (a Fleet token without `vehicle_device_data`), the free check uses `slotFor("read")`, which can be the Owner slot. The brief said `slot=slotFor("command")`.
4. **429 backoff.** A 429 also sets `errorCount = max(30, errorCount)`, as legacy `get_car_api` and `wakeVehicle` do. On a clean count, `updateCarApiLastErrorTime` alone gives a 0-minute backoff.
5. **Failed refresh on an expired 401.** If the refresh returns `"unreachable"`, the outcome is `UNREACHABLE "token refresh"` and the slot is kept. Any other refresh failure gives `REFUSED "401"`; a refresh-token 401 has already cleared the slot inside `refresh()`. The brief does not cover this case.
6. **Amps clamp.** `setAmps` sends `max(1, int(amps))`, as legacy `setChargeRate` did, because 0 would stop charging. The brief said `int(amps)`.
7. **Access stamp.** `command` stamps `lastAPIAccessTime = self.now()` only on `DONE` or `SATISFIED`, meaning the car answered. Legacy stamped it before every post.
8. **Wake result details:**
   - The legacy 5 s sleep on an `offline` wake result is dropped.
   - An HTTP 200 with an unexpected state gives `ERROR "state"` and the vehicle-scoped error time; legacy set the global one.
   - Every failed wake, HTTP errors included, sets `delayNextWakeAttempt = 1800` and `firstWakeAttemptTime`.
   - The hour-long "please report" INFO no longer includes the response dict.
9. **Two tests edited that the brief did not list:**
   - `test_teslaapi_token_slots.py::test_owner_412_pauses_for_an_hour_then_returns` is now `test_owner_412_pauses_until_the_token_changes`. The latch contradicts the old test, and the new one no longer patches `time.time`.
   - `test_carapivehicle_registry.py::test_debug_interface_resolves_by_vin`: the Fleet wake is now `wakeOutcome`, so the test mocks that instead of `wakeVehicle`.
10. **black scope.** black was run only on the 5 lib files I touched, not on the `lib/TWCManager/Vehicle/` directory the brief's Step 5 names.

## Concerns to carry forward

- **Interim Fleet retries (paid).** `Order.dispatch` retries Fleet `attempts()=2` times on `UNREACHABLE` or `ERROR`. Legacy `setChargeRate` returned a truthy dict for HTTP-error bodies and `could_not_wake_buses`, so it did not retry. Each method still makes one paid call. But on the live `VehicleEndpoint → queue → VehiclePriority.setAmps → dispatch` path, a failed Fleet `setAmps` can now cost 2 posts per dispatch. The 600 s skip-repeat in `setChargeRate` is also no longer on this path; `VehicleEndpoint.REFRESH_SECONDS = 600` still limits how often a rate is queued. This lasts until Task 9/10. I did not widen into `Order` because it is outside this brief.
- **Interim HA `setAmps`.** It now posts unconditionally on the same path. Legacy `HomeAssistant.setChargeRate` skipped the post when the value already matched or the car was not connected.
- **Stale `firstChargeNeededTime`.** Nothing in Task 5 resets it when a need ends without the car coming online; legacy `car_api_charge` did. A second need then skips the `wakeDelayMins` grace. This is a Task 8 carry.
- **`wakeDue` before the first `wakeOutcome`.** `wakeDue` returns True before the first `wakeOutcome` of a need, because the need is not recorded yet. A reconciler that gates on `wakeDue` will therefore submit one attempt that comes back `"wake held"`. That is harmless and costs nothing, but Tasks 6 and 8 should know.
- **412 on a command.** Per the brief, it latches the slot for reads only. `usable("command")` ignores `pausedUntil`, so commands on that token are excluded only for the round, through `REFUSED`.
- **Process-wide `time.sleep` patch.** The brief's tests patch `T.time.sleep`, which patches `time.sleep` for the whole process. That is not `time.time`, and it is kept verbatim from the brief.

## Fix round 1

**Commit:** `098f7c8`, on top of 81dc39b.
**Tests:** full suite 1451 passed, 1 xfailed. That is 1440 plus 11 new tests in `test_provider_outcomes_cloud.py`.

**Reviewer's probe:** `probe-p3t5/probe_new.py` now shows 84 passed and 4 failed. All 4 failures are its finding tests, which asserted the old behaviour and now fail because the defects are fixed:
- `test_412_on_a_command_keeps_paying`
- `test_412_on_wake_with_owner_slot`
- `test_expired_401_refresh_not_configured_keeps_posting`
- `test_reason_is_echoed_into_log`

### Fail-before (tests written first, run against 81dc39b)

```
FAILED test_backoff_429_and_412_send_nothing_more        (assertion updated: a command 412 no longer latches reads)
FAILED test_a_command_412_retires_commands_and_wakes_until_the_token_changes   (usable('command') True after 412)
FAILED test_a_wake_412_retires_wakes_too                  (usable('read') False: the latch hit reads)
FAILED test_an_unrefreshable_expired_token_is_retired     (3 == 1 posts)
FAILED test_an_ended_need_gets_a_fresh_grace_through_wake_outcome   (Outcome 'asleep' != 'wake held': a wake was posted)
FAILED test_an_ended_need_gets_a_fresh_grace_on_the_legacy_path     (car_api_available True: grace skipped)
FAILED test_wake_due_reads_the_backoff_on_its_clock       (wakeDue True at now=5000 during the backoff)
FAILED test_no_free_check_during_the_backoff              ('wake held' != 'backoff')
FAILED test_a_cached_failed_check_stays_unknown           (lastVehicleAwakeKnown True on a cache hit)
FAILED test_odd_reasons_are_not_carried                   (300-char reason carried)
FAILED test_ha_http_error_without_a_response              (detail 'None')
```

`test_a_read_412_still_latches_reads_only` passed before the fix as well. It is a guard against regressing read 412s.

### Fixed

**I1: a 412 on a command now stops all further paid requests on that token.**
- What happens on a 412: in `_paidPost`, a 412 on `command/*` or `wake_up` calls `commandRefused(slot, 412)`. That logs one ERROR line and calls the new `TeslaTokenSlot.refuse("command")`, which `reportScopeRefused` now also uses.
- What no longer happens: it does not latch reads. A read 412 still latches reads only, through `slotRequestFailed`, and the command purpose stays usable.
- After a command 412, `slotFor("command")` is None, so the Fleet provider stops at `REFUSED "no command token"`.
- Measured after a command 412, with an Owner slot present:
  - 40 rounds of every command plus `wake` over 40 injected minutes sent 0 further requests (not even the free check);
  - a wake 412 driven every 10 s for an hour sent exactly 1 `wake_up`;
  - a new token clears the refusal.

**M1 (listed as Minor, fixed because it leaked paid requests; it is a one-line change in the branch I1 already touches).** An expired 401 whose refresh fails for any reason except "unreachable" now goes to `commandRefused(slot, 401)`, which retires the slot. Before, a `not_configured` refresh sent one 401 post every round. Now 3 rounds send 1 post.

**M3/c4: the charge-need lifetime.**
- New field `CarApiVehicle.lastChargeNeededTime`. `TeslaAPI._askChargeNeed(vehicle, now)` stamps it on every wake ask. It is called at the top of `wakeOutcome` (after the backoff check) and in legacy `car_api_available`'s per-vehicle need block, before the `firstChargeNeededTime == 0` check, so a need held in its 30-minute post-wake hold keeps getting stamped.
- If no wake has been asked for `CHARGE_NEED_IDLE_SECONDS = 600`, the need has ended: `firstChargeNeededTime` is cleared and the next ask starts a fresh `wakeDelayMins` grace.
- `wakeDue` treats a stale marker as absent and does not modify it.
- Why it is cost-safe:
  - Ending a need can only delay a wake, never bring one forward.
  - 600 s is well above the gap between asks during a live need: legacy `car_api_charge` is called at least once a minute, and the lane retry for CHARGING is 60 s.
- This is a backstop. The explicit end of a need (desired charging turned off, or a departure) belongs to Task 8's reconciler.
- It also covers M3's lingering marker: a one-shot debug wake's marker expires after 600 s. The first debug wake with the default `wakeDelayMins` still comes back "wake held" (a UX issue, not a cost one).
- One legacy test, `test_targeted_charge_limit.py::test_teslaapi_targeted_limit_never_wakes_another_car`, now also sets `lastChargeNeededTime` so that it still models a continuing need whose grace is over.

**M4: the wake backoff is read on the injected clock.** `getCarApiRetryRemaining(vehicle=None, now=None)` takes the clock: `wakeDue` and `wakeOutcome` pass `now`, `command` passes `self.now()`, and other callers keep the wall clock. `updateCarApiLastErrorTime` still stamps the wall clock. On a frozen test clock a real 429 backoff therefore never expires; that errs toward fewer paid calls, and in production both are the same clock.

**Cheap Lows:**
- **L1:** `lastVehicleAwakeChecked` caches whether the API check answered. A cache hit restores `lastVehicleAwakeKnown` from it, so a stale telemetry Known=True cannot release a blind wake.
- **L2:** `wakeOutcome` returns `UNREACHABLE "backoff"` before the free check.
- **L3:** a reason is carried only if it matches `[a-z_]{1,40}`; anything else becomes `"not accepted"`.
- **L4:** an HA `HTTPError` with no response gives `ERROR "HTTPError"`.

### Listed, not fixed

- **M2:** a 403 on `wake_up` retires `command`. Tesla may file `wake_up` under the `vehicle_device_data` scope, which would make this the wrong purpose to retire. It errs toward fewer paid calls. A `wake` purpose checked by `ready(WAKE)` would fix it.
- **M5:** `VehiclePriority.setAmps` (dispatch) no longer stamps the own-write `availableCurrent` or `lastChargeRateSent`. Carried to Task 10/11 with c3.
- **M6:** HA's `RateLimit(1, 10)` is keyed per capability, so a start and a stop each get their own window. It is enforced only once the reconciler calls `Lanes.allows` before submitting; nothing in `lib/` calls it yet. Task 6 must, or the lane window should be keyed by aspect.
- **M7:** a 403 refusal applies to the whole account, so one car's unpaired key stops commands to every car on that token. It errs toward fewer paid calls; carried to Task 11 for status and UI, or a refusal keyed by VIN.
- **c3:** the interim retries in `Order.dispatch` (Fleet `attempts()=2`) are unchanged. Task 10 deletes that path.

## Fix round 2

**Commit:** `39d7cfb`, on top of 098f7c8. Tests: the full suite has 1454 passed and 1 xfailed, which is 1451 plus 3 new tests. I also updated the M1 test.

**N1 fix.** This is in the 401-expired branch of `_paidPost`. When the refresh returns something other than "success" or "unreachable", and `refresh()` has not already cleared the slot, the code now does three things:
- logs one ERROR line ("has expired and could not be refreshed (<result>)");
- calls `slot.refuse("command")`;
- returns `REFUSED "401"`.

It never calls `slot.clear()` or `commandRefused` for a failed refresh. A refresh that the auth server answers with 401 is unchanged: `refresh()` clears the slot, as in base. A successful refresh calls `setTokens`, which lifts the refusal; that covers both the background `refreshTokenIfNeeded` cycle and a token change. M1's cost property still holds: 3 rounds send 1 post. A slot with `not_configured` (no client ID) stays refused until its token changes.

**Fail-before** (tests written first, run against 098f7c8):
```
FAILED test_an_unrefreshable_expired_token_is_retired        (refreshToken '' == 'rt': cleared)
FAILED test_a_503_refresh_keeps_the_tokens_and_stops_paying  (refreshToken '' == 'refresh-me')
FAILED test_a_later_successful_refresh_restores_commands     ('not_configured' == 'success': no refresh token left)
FAILED test_an_invalid_grant_clears_the_slot_as_base_did     (a 400 invalid_grant cleared the slot; base kept it)
```

**Tests:**
- **A 503 refresh:** the access and refresh tokens are kept. The next 3 rounds of stop and wake send 0 paid posts and make no second refresh.
- **A later successful refresh:** a 502 refresh gets the command refused. Then a successful `refreshSlot` restores `usable("command")`, and the next stop returns DONE.
- **invalid_grant, matching base:**
  - A refresh 401 clears the slot, including the refresh token, and every later round sends nothing.
  - A refresh 400 keeps the slot, as base did, and refuses commands.

**Probes:**
- `probe_rereview.py`: 20 passed, 3 failed. The 3 failures are its N1 finding tests (`test_transient_refresh_failure_deletes_the_token[500|503|400]`), which asserted that the tokens get deleted, so they now fail by design. Its refused-token sweep still passes, including the expired-and-cannot-refresh cases: 0 posts after the first.
- `probe_new.py`: unchanged at 84 passed, 4 failed. The failures are the finding tests that were already flipped.

**Not changed:** M2 is deferred to Task 6. N2 (a gap over 600 s restarts the grace, which is cost-safe) is noted for Task 8.
