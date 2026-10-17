# Task 5 review: cloud provider command outcomes (f394844..81dc39b)

Reviewer: independent, no subagents. Checkout: `scratchpad/wt-vm3` at 81dc39b. Base extracted to `scratchpad/probe-p3t5/base` with `git archive f394844`.

## Verdicts

- **Spec compliance: COMPLIANT.** Every interface in the brief is present, with the accepted c1 deviation and the c2 deviations judged below. There is one small gap (M4): `wakeDue` makes its backoff comparison on the wall clock, not on `now`.
- **Task quality: PASS WITH FINDINGS.** There is 1 Important finding (I1): a 412 latch does not stop paid commands or wakes. There are also 7 Minor and 4 Low findings.
- **I1 is a required fix before Task 5 closes.** It fails the hard cost check "the refusal and latch logic doesn't make a refused token keep getting paid requests". The quality verdict is conditional on it.

## Verification run

- Step-4 set plus `test_carapivehicle_registry.py` and `test_lanes.py`: 162 passed.
- `black --check` on the 5 touched lib files: clean.
- Probe `scratchpad/probe-p3t5/probe_new.py` (new code only): 88 passed.
  - Every Fleet method under 13 response kinds sends at most one paid request. The only exception is `setAmps` below 5 A, which sends two on success as the brief requires.
  - After a 401, 403 or 429, five more rounds of every method plus `wake` send nothing.
  - There is no wake without a free answer. The check was tried with a 503, a 500, a ConnectionError, a non-JSON body, a 429, a 401, a 403, a 412, and with no read slot at all.
  - An Owner slot answers the check when Fleet cannot read.
  - The 120 s cache follows `api.now`, not `time.time`. A jump in `time.time` did not refetch.
  - Over an hour on the injected clock, an asleep car gets 2 wakes, and the free checks stay within the 120 s cache.
  - No token or body reached any log at level 1, for Fleet or HA.
  - The probe also includes four finding tests: `test_412_on_a_command_keeps_paying`, `test_412_on_wake_with_owner_slot`, `test_expired_401_refresh_not_configured_keeps_posting` and `test_wake_403_retires_commands`.
- Probe `scratchpad/probe-p3t5/probe_compare.py` runs on both trees. Counts are in `counts-base.json` and `counts-new.json`.

## Judgement of c2 (report deviations 2-10)

| # | Deviation | Ruling |
|---|---|---|
| 2 | `wakeDue` holds only when `delayNextWakeAttempt > 0` | Accept. Same as legacy on a real clock, and correct on a frozen clock. |
| 3a | No wake without a free answer (`lastVehicleAwakeKnown`) | Accept. The cost constraint requires it. There is one edge case on a cache hit (L1). |
| 3b | The free check falls back to `slotFor("read")` | Accept. Owner `vehicles/{vin}` is free, and the probe confirms that it is used. |
| 4 | A 429 sets `errorCount = max(30, …)` | Accept. Matches legacy, and without it a first 429 gives a 0-minute backoff. |
| 5 | Refresh "unreachable" gives UNREACHABLE and keeps the slot; any other failure gives REFUSED | Accept, apart from `not_configured` (M1). |
| 6 | `setAmps` uses `max(1, int(amps))` | Accept. Matches legacy `setChargeRate` and `debugCommand`. |
| 7 | `lastAPIAccessTime` is stamped only on DONE or SATISFIED | Accept. Legacy `ready()` no longer treats a failed post as proof that the car is awake. |
| 8 | Wake details: the offline sleep is dropped, an odd 200 sets the vehicle error time, every failure holds 30 min, the INFO log has no dict | Accept all four. None adds a paid call, and the last one removes a body from the log. |
| 9 | Two unlisted tests edited | Accept. The 412 test now asserts the latch without patching `time.time`, and the debug test mocks `wakeOutcome`. |
| 10 | black run on the touched files only | Accept. `black --check` is clean on all 5. |

## c3 confinement

The interim increases ruled as c3 all sit on `Order.dispatch` (`VehiclePriority.setAmps`, reached through VehicleEndpoint and then VehicleCommandQueue): changes 6-9, 13 and 14 below. Task 10 deletes that path. The cloud lane is the only other route into the new provider methods. Three changes fall outside the c3 path:
- change 4, on the debug path, which I accept as intended;
- change 15, on the read path, which is the latch the ledger asked for;
- change 20, on the legacy wake path, which is M3 and related to c4.

## Changes in when or how often paid calls happen, vs f394844 (20)

Counts are paid POSTs from `probe_compare.py`, shown as base → new. The probe used realistic JSON error bodies; with an empty `{}` body, base already retried and sent 2.

**Debug API** (`/api/sendTeslaAPICommand` → `debugCommand` → one-shot lane)

1. Wake on an online car: 3 clicks went from 3 wakes to 0, because the free check answers first. **Decrease.**
2. Wake on an asleep car with `wakeDelayMins = 3` (the default): 3 clicks went from 3 to 0. The first click arms `firstChargeNeededTime` and is held. **Decrease**, with a UX change (M3).
3. Wake when the free check gets no answer: base woke blind, new sends nothing. **Decrease.**
4. `setChargeRate` with the same rate twice within 600 s: 1 → 2. The base skip-repeat in `setChargeRate` is no longer on this path. **Increase**, one per user click. I accept it, since base silently swallowed a repeated debug command.
5. A failed debug wake now arms the 30-min hold, which is shared with `car_api_available`. **Decrease.**

**VehiclePriority.setAmps** (`Order.dispatch`, 2 attempts for Fleet; the c3 path)

6. The same rate within 600 s now posts every time. Base skipped it. On the live path, `VehicleEndpoint.REFRESH_SECONDS = 600` throttles this the same way, so there is little real effect. **Increase (c3).**
7. `could_not_wake_buses`: 1 → 2 per dispatch. **Increase (c3).**
8. A 500 or other HTTP error with a JSON body: 1 → 2 per dispatch. **Increase (c3).**
9. A 412: 1 → 2 per dispatch, on every dispatch, for 3 dispatches going from 3 to 6. **Increase (c3, made worse by I1).**
10. A plain 401: base sent up to 2 per dispatch forever. New sends 1 in total, because the slot is cleared. **Decrease.**
11. A 403: base sent 1-2 per dispatch forever. New sends 1 in total, because the command purpose is retired. **Decrease.**
12. A 429: base sent 1-2 per dispatch each time. New sends 1, then 10 minutes of backoff. **Decrease.**
13. Below 5 A, where the first post succeeds and the second fails: base sent 2 (4 with an empty body), new sends 3. **Mixed (c3).**
14. HA `setAmps` now posts on every dispatch. Base skipped the post when the value already matched or the car was not connected. **Increase (c3; HA_BILLED).**

**TeslaAPI policy paths** (code untouched; the changes come through shared state)

15. A 412 on an Owner read now latches the Owner slot until the token changes, instead of pausing it for an hour. Reads stay on the Fleet slot, where `vehicle_data` costs $0.002, and the hourly free retry of the Owner slot is gone. If the 412 is permanent, as for the `/vehicles` list, this costs the same as base. If it is transient or endpoint-specific, paid Fleet reads continue until the token changes or the process restarts. The latch also holds `energy` reads on that slot indefinitely, since `usable()` applies `pausedUntil` to both. **Possible increase, by design (ledger).**
16. A 403 on a command or wake from the new path retires `command`, so `readOnly` becomes True. `car_api_available` then stops waking cars, and the legacy `car_api_charge`, `setChargeRate` and `applyChargeLimit` stop sending. **Decrease.**
17. A plain 401 from the new path clears the Fleet slot, and the legacy paths stop. **Decrease.**
18. A 429 from the new path sets the vehicle backoff with `errorCount` 30, and the legacy paths honour it. **Decrease.**
19. A failed `wakeOutcome` sets `delayNextWakeAttempt` and `firstWakeAttemptTime`, which `car_api_available` shares, so legacy wakes are held for 30 min. **Decrease.**
20. If a `wakeOutcome` is held or fails, as with a debug wake, it leaves `firstChargeNeededTime` set. The next charge need in `car_api_available` then skips the `wakeDelayMins` grace and can send its $0.02 wake about 3 minutes earlier, before the car has had the chance to start on the TWC's offer. **Increase (M3; same root as c4).**

## Findings

### Critical

None.

### Important

**I1. A 412 latch stops reads but not paid commands or wakes.** Locations:
- `lib/TWCManager/Vehicle/TeslaAPI.py:2091-2093`, the 412 branch of `_paidPost`;
- `lib/TWCManager/Vehicle/TeslaTokenSlot.py:136`, where `usable()` honours `pausedUntil` for `read` and `energy` only.

After a 412 on `command/*` or `wake_up`, `usable("command")` stays True, so every later round posts again. Examples:
- `test_412_on_a_command_keeps_paying`: 5 calls send 5 posts.
- On the dispatch path, each dispatch sends 2 posts, against 1 at base (change 9).

The latch also lands on the wrong purpose. A 412 on a command latches the Fleet slot's **reads** (`vehicle_data` and the free online check) forever, while `command`, the purpose that failed, stays usable.

Exposure differs by request:
- **Commands are unbounded:** one post per round, and 2 per dispatch on the legacy path.
- **Wakes are held:**
  - With a Fleet token only, the latched read leaves no free check, so no wake is sent. That is safe only by accident.
  - With an Owner slot present, the check runs on Owner and the wake posts again. `delayNextWakeAttempt = 1800` bounds this to one $0.02 wake every 30 min, indefinitely: 2 per hour in `test_412_on_wake_with_owner_slot`.

A Fleet 412 such as "registration required in region" persists until the account is fixed. The constraint "the refusal and latch logic doesn't make a refused token keep getting paid requests" is therefore not met for 412, and the `REFUSED` contract in `Outcome.py` ("the provider has retired its slot") does not hold either. The report flagged this, but it was not ruled on.

**Fix:** in the 412 branch, also retire the command purpose. Either:
- add `slot.refusedPurposes.add("command")` next to `slot.pause(latch=True)`; or
- give `pause(latch=True)` a `purposes` argument; or
- have `usable()` refuse every purpose while `pausedUntil == inf`.

Also decide whether a 412 on a command should touch the slot's reads at all. Base never latched Fleet reads on a command.

`setTokens`, `clear` and `restore` already reset it. Add a test: after a 412 on a command, a second `setChargeLimit` sends no request, and `dispatch` for 412 ×3 sends 1 post.

### Minor

**M1. An expired 401 whose refresh returns `not_configured` keeps paying.** Location: `TeslaAPI.py:2079-2087`. "Not configured" means a refresh token with no `teslaApiClientID`. In that case `_paidPost` returns `REFUSED "401"`, keeps the slot and sets no backoff (`refreshSlot` skips `updateCarApiLastErrorTime` for that result). Every round sends one more 401 post (`test_expired_401_refresh_not_configured_keeps_posting`: 3 calls send 3 posts). **Fix:** treat any refresh result other than "success" or "unreachable" as a plain 401, by calling `self.commandRefused(slot, 401)`, or record `refusedPurposes.add("command")`.

**M2. A 403 on `wake_up` retires charge commands.** Location: `TeslaAPI.py:2089`, reached from `wakeOutcome` at line 2172. Tesla's Fleet API docs list `wake_up` under the `vehicle_device_data` scope; verify this. If so, a 403 on a wake means the read scope is missing, but the code retires `command`, and with it `set_charging_amps`, which the token's `vehicle_charging_cmds` scope would allow. The brief mandates "as for command", and the error is in the cost-safe direction, so this is Minor. **Fix:** pass the purpose into `_paidPost`, and for `wake_up` record a `wake` refusal, either through `RETIRED_ON_REFUSAL` or a new purpose that `FleetAPIProvider.ready(WAKE)` checks, or record nothing and rely on the 30-min hold.

**M3. A one-shot (debug) wake arms the need grace and leaves it armed.** Location: `TeslaAPI.py:2158-2166`.
- The first debug "wake" with the default `wakeDelayMins = 3` always comes back "wake held".
- `firstChargeNeededTime` stays set until the car is next seen online, so the legacy `car_api_available` later skips its grace (change 20).

**Fix:** give `wakeOutcome` a `grace=True` argument that the debug or one-shot path turns off, or clear `firstChargeNeededTime` when a one-shot ends unsettled. At minimum, fold this into the c4 carry for Tasks 6 and 8.

**M4. `wakeDue` makes its backoff comparison on the wall clock.** Location: `TeslaAPI.py:2127`, through `getCarApiRetryRemaining` at line 1502, which uses `time.time()`. The brief says every comparison inside `wakeDue` uses `now`. In production the two are the same clock, but a test on a frozen clock cannot drive the backoff. **Fix:** add an optional `now` to `getCarApiRetryRemaining`, and pass it from `wakeDue` and `command`.

**M5. The dispatch path loses the own-write stamp.** Locations: `Providers/TeslaAPIProviders.py:152` and `Providers/HomeAssistantProvider.py:114`, reached through `Order.py:151-161`. Base `setChargeRate` called `noteWrite("availableCurrent", …)` and set `lastChargeRateSent`, and HA did the same. Providers never stamp, and only lanes stamp, so `VehiclePriority.setAmps` now leaves no own-write. Telemetry's retained-value backdating (`Telemetry.py:273`) loses its anchor for `availableCurrent`. This is interim until Task 10. **Fix:** stamp in `VehiclePriority.setAmps` on a settled Outcome, or record it as a c3 carry.

**M6. HA's 10 s limit has separate windows for start and stop.** Locations: `Providers/HomeAssistantProvider.py:47-52` and `Reconcile/Lanes.py:441-471`, where windows are keyed by (provider, capability, vin). Within one car, a start and a stop inside 10 s are both sent. The legacy gate was one timer across start and stop. Per car, the window logic is correct, as the probe `test_ha_per_car_limit` shows. Enforcement is another matter: at 81dc39b, nothing in `lib/` calls `Lanes.allows` (only `test_lanes.py` does), while `runAttempt` calls `note`. The limit is declared and recorded, but it is enforced only once the Task 6 reconciler checks `allows` before it submits. Task 6 must do so. **Fix:** accept and document, or have the lane key the window by aspect, so that `START_CHARGING` and `STOP_CHARGING` share the `CHARGING` window.

**M7. A 403 refusal is account-wide.** Location: `TeslaTokenSlot.py:143-144`. Tesla can 403 a single car, for example when the car's virtual key is not paired behind the proxy. The 403 then stops commands to every car on that token until the token changes or the process restarts. The error is cost-safe, but it is invisible except for one ERROR log. **Fix:** carry to Task 11 (status/UI), or key the refusal by VIN when the 403 body says the key is unpaired.

### Low

**L1. A cache hit keeps a stale `lastVehicleAwakeKnown`.** Location: `TeslaAPI.py:2649-2650`. The telemetry branch can leave Known=True while the cached API state came from a failed check. A stale "online" telemetry value then falls through to that cache and allows one blind wake. **Fix:** cache the known flag next to `lastVehicleAwakeState`, and restore it on a cache hit.

**L2. The free online check runs during a 429 backoff.** Location: `TeslaAPI.py:2152` runs before 2127. The check is free, but it is still a request during an explicit back-off. **Fix:** in `wakeOutcome`, check `getCarApiRetryRemaining` before `is_awake`.

**L3. Tesla's `reason` string goes into `Outcome.detail` and the INFO8 log without a bound.** Locations: `TeslaAPI.py:2037` and 2043. The probe passed a 300-character reason, and it was logged whole. **Fix:** keep the reason only if it matches `^[a-z_]{1,40}$`, otherwise use "not accepted".

**L4. An `HTTPError` without a response is reported as `ERROR "None"`.** Location: `HomeAssistant.py:550`. **Fix:** fall back to the type name.

## Carry forward

- I1 and M1 change refusal semantics that Task 6 relies on: whether a REFUSED outcome is excluded for the round or for good.
- M3 is the same root as c4: `firstChargeNeededTime` lifetime.
- M5 joins c3 for Task 10 and Task 11 parity: the own-write stamp, plus paid parity on the dispatch path.
