# Report: plugged-in cars the power split ignored

Branch `fix/car-side-wants-power` (worktree `.../scratchpad/wt-fix`), based on `origin/vehicle-model/phase6` (1a0b7d67). One commit, not pushed:

- `ef7be20f` Offer power to a plugged-in car that a pending raise would start

## Answer to the wider question

Yes, the problem is wider than the car-side endpoint. Every EVSE kind could leave a plugged-in car that wasn't drawing power without any power budget. For a car asleep at its old limit, that meant the raise never got a wake. The distributor budgets only points with `wantsToCharge` (`TWCMaster.py:610`). Points left out get 0 in `master.offered` (`TWCMaster.py:688`), and `whyQuiet` then returns "nothing offered" (`Belief.py:133`). That blocked the one wake that could have changed the car's state. The fix moves "wants power" to a single car-level rule in `ChargingPoint`, so it covers all kinds at once.

## Audit (line numbers at 1a0b7d67)

| EVSE kind | Signal before | Asleep | "Complete" with a raise | "Stopped" by us | Gen2 at 00 / Gen3 `complete` |
|---|---|---|---|---|---|
| Car-side `VehicleEndpoint` (`VehicleEndpoint.py:46`) | chargingState is Charging (and not asleep) or Stopped | **stuck** if Complete | **stuck**: last night's live bug | not reached: no stop ever targets a car-only point | n/a |
| Gen2 (`Gen2TWC.py:72`) | `reportedAmpsMax > 0 or reportedAmpsActual > 0` | **stuck once the echo is 0** | **stuck once the echo is 0** | **stuck** (see below) | at 00 the TWC doesn't name the car (`Presence.py:291`, `PLUGGED_STATES` `Gen2TWC.py:13`); see below |
| Gen3 (`Gen3TWC.py:296`) | connected and `evse_state` not in `""`/`not_connected`/`complete` | as for Complete | **stuck**: `complete` is excluded | as for Gen2 (no gate) | **stuck** in `complete` |
| `ChargingPoint` (`ChargingPoint.py:46`) | `any(e.wantsToCharge)` over local members, else all members | it only aggregates the members' signals | | | |

**How Gen2 escaped, when it did.** `reportedAmpsMax` is not the car's maximum. The TWC echoes the master's last offer back: see the protocol notes at `TWCSlave.py:417` and the trace at `TWCSlave.py:737` (`M: 05 0000` gets the reply `03 0000`), plus `TWCSlave.py:164`, which learns the last offer from the echo. The tests say the same ("the TWC echoes its offer"). So:

- **The escape.** If the TWC was last offered power (for example, it charged earlier that evening), the echo stays above 0. The point keeps wanting power, gets its share, and `whyQuiet` allows the wake. The parity row "a sleeping car at 00 with power available is woken for a raise" works only because its heartbeat keeps `maxA=32`.
- **The trap.** Once the offer is 0, for example after a budget dip at night or after the car stopped, the echo is 0. `wantsToCharge` then stays false until the car draws power. On the wire, `offerFor` keeps a 0 offer at 0 unless another car is charging (`TWCSlave.py:167`), and `chargeGate` "withdraws" the start (`TWCSlave.py:256`). An awake car that wants to charge can still start on the TWC's hardware-minimum pilot and break out that way. A car asleep at its limit can't, and neither can a car we stopped by command. That second case is the "Stopped by us" deadlock: the gate's stop is cleared only when `offer.amps > 0` (`TWCMaster.py:~557`), and the offer never rose.
- **A Gen2 at 00** doesn't name its car, so its point can't use the car rule. The car can still get its own `VehicleEndpoint` point if a non-telemetry source shows it plugged in here (`_blindTWCs`/`vehicleEndpoints`), and the fix covers that point.

**The other consumers.**

- **`num_cars_charging_now`** (`TWCMaster.py:1338`) counts slaves with `isCharging` (current is flowing). It feeds `offerFor`'s idle probe and the policy's offer floor. It doesn't read `wantsToCharge` and needs no change.
- **`controlPass` / `chargeGate`** react to the offer. With the fix, a Gen2 car that would take power gets a real offer, so the gate clears our earlier stop and asks for the start.
- **The watch** (`Vehicle/Watch.py`) reads neither `wantsToCharge` nor `offered`. It is unaffected.
- **The fair share** splits the budget among the wanting points. A woken car that then won't charge drops out on the next pass after its reading arrives (test 5).

## The fix and why it lives where it does

- **`Belief.whyQuiet(master, vehicle, budgeting=False)`** is the one rule. With `budgeting=True` it skips the distributor's own inputs, its offer and the stop its gate sent in answer to a 0 offer, and asks only whether the car would take power once the pending desires land:
  - the car is plugged in here;
  - the effective limit (pending, then held, then believed: the same resolution as before) is above the battery level, or either is unknown;
  - there is no telemetry settle window.

  A new `finished(vehicle)` covers a car that is "Complete", or asleep after "Charging". Such a car counts as at its believed limit, so only a raise above that limit brings it back. The same rule now governs the wake: a finished car with no raise is quiet in the wake path as well.
- **`ChargingPoint.wantsToCharge`** wants power when either:
  - a member is drawing current. That is `currentAmps >= 1 A`; I added `Gen2TWC.currentAmps` as an alias of `reportedAmpsActual`. A car member is judged by its own `wantsToCharge`. A drawing car is never starved because of stale beliefs.
  - its named, non-anonymous car passes `whyQuiet(..., budgeting=True)`.

  A point that can't name its car (unnamed or anonymous TWC) keeps its members' reports, as before. This is the single place the distributor asks, so it covers every EVSE kind without a separate patch per class.
- **`VehicleEndpoint.wantsToCharge`** now uses `finished()` instead of repeating the asleep-after-Charging test.

**How the offered check and the raise wake fit together now.** "Nothing offered" still keeps asleep a car that can't get power: with no budget, or a point refused by its limits, `offered` is 0. The distributor's offer no longer depends on the car already charging, though. A car whose pending raise would start it passes the budgeting rule, so it gets its share. `offered[car]` is then above 0 and `whyQuiet` returns None, which lets the raise's wake through. After the wake, the limit is set, the rate follows, and the car starts. The order is limit first, then the start, then the rate (Gen2 also gets a start desire from the gate). With no raise pending, the car at its limit passes neither rule, so it gets no offer and no wake.

**Kept behaviours.**

- An idle Gen2 still gets target 0, which goes out as its hardware minimum.
- A car asleep after "Charging" is not counted unless a raise is pending.
- A read-only car gets no budget: the distributor still filters on `isReadOnly`, and `vehicleEndpoints` lists only cars with a set-amps provider.

**Deliberate departure from the brief: a stop desire doesn't remove a car from the budget.** The only producer of a `CHARGING False` desire is the Gen2 `chargeGate` (`stopCarsCharging` is called only from `controlPass`). The gate stops a car only because it was offered 0. If that stop also kept the car out of the budget, the "Stopped by us" deadlock would become permanent. A stop desire still blocks the wake (`whyQuiet` without `budgeting`, test 3). When power returns, the offer rises, `controlPass` clears the stop, and the gate asks for the start.

## Tests (`tests/unit/test_wants_power.py`, new)

Fail before was run against the base lib, pass after against the fix.

| # | Test | Before | After |
|---|---|---|---|
| 1 | Replay of last night: car-side, asleep, Complete, battery 70, limit 70, raise to 90, 32 A: offered > 0, `whyQuiet` None; BLE runs wake → setChargeLimit 90 → wake → setAmps 32 | FAIL (offered 0) | pass |
| 2 | Same car, no raise (70): offered 0, no wake | pass (guard) | pass |
| 3 | Same car, stop desired: no wake, `whyQuiet` "stop desired" | pass (guard) | pass |
| 4a | Gen2, echo 0, asleep Complete at 70, raise to 90: point budgeted, start desired, wake before setChargeLimit | FAIL | pass |
| 4b | Gen2, echo 32, at its limit, no raise: offered 0 (no longer holds a share) | FAIL (32 A) | pass |
| 4c | Gen2, car we stopped (Stopped, 70 of 80), echo 0, power back: offered, stop replaced by a start | FAIL | pass |
| 4d | Gen3 `complete`, car at 70: offered 0, then raise to 90: offered > 0, unit target > 0, `whyQuiet` None | FAIL | pass |
| 5 | Charging car (50 of 90) and Complete car (70) with raise to 90 on 32 A: 16 A each; once the second reads 90 of 90, the first gets 32 A again | FAIL | pass |

**Two existing tests changed on purpose:**

- **`test_charging_points.py::test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum`.** A paused car on its TWC with an unknown limit is now offered the share. It used to get 0 until it drew power, which is the Gen2 trap above. At its limit it gets 0, and a car drawing power still gets the full share.
- **`test_sleep_pilot_replay.py::test_a_car_read_under_the_sleep_pilot...`.** The car is at its limit (50 of 50), so it is budgeted once the 70 raise is pending. The test now sets the raise before the control pass instead of after it. Before, the echo let the car hold a share it wouldn't use.

## Counts

- **Full suite.** 2,467 passed and 1 xfailed, exit 0. That is the 2,459 baseline plus 8 new tests.
- **Parity.** `tests/unit/test_command_path_parity.py`: 120 passed, exit 0, and the file is unedited. No paid count and no free count moved.
- **Lib line delta.** +46 / −16, net **+30**, across `ChargingPoint.py` (+19), `Belief.py` (+13), `Gen2TWC.py` (+4) and `VehicleEndpoint.py` (−2).
- **Formatting.** Every touched lib file was black-clean before the change and still is. The new test file is black-formatted.
- **CHANGELOG.** One line added under v1.4.1 Bugfixes.

## Concerns

1. **Gen2 echo semantics come from code comments and test fixtures, not hardware.** I couldn't check them here: the live box has no TWC under TWCManager's control. If a protocol-2 TWC echoes its hardware minimum instead of 0, the Gen2 trap is narrower than described, but the fix still holds.
2. **A car-side member reporting "Stopped" still counts as drawing**, which keeps the old behaviour. A stale "Stopped" at the car's limit, or a car waiting on its own schedule (`scheduledChargingPending`), can hold a share it won't use until the next reading. `handsOff` already refuses the start in the schedule case. This is not new, but the rule doesn't cover it.
3. **`whyQuiet` now also returns "car finished charging"** in the wake path: a Complete car, or one asleep after Charging, whose pending limit is not above its believed limit. No parity row moved, but the new reason string is visible in logs.
4. **The stop-desire departure** described above.

## Round 1 (review fixes)

New commit `05ca8c4d` "Admit a car to the budget only on positive evidence it will charge", on top of `ef7be20f`. Not pushed. I kept it as a separate commit so the round-1 changes can be reviewed on their own.

### What changed

**1. A charging car can't be starved** (`TWCMaster.distributeEVSEPower`).
- Points that are drawing power are sorted first (`ChargingPoint.drawing`).
- If a drawing point's fair share falls below its minimum, its share comes only from the drawing points still pending, so an idle point can't push it under.
- Example on a 9 A budget: the charging car keeps all 9 A and the car waiting on a raise gets 0, in either registration order.
- When the budget is large enough, the shares are unchanged: test 5 still splits 16/16 on 32 A.
- Two charging cars with too little to share behave as before: one is stopped and the other gets the rest.

**2. The car's own schedule, and "cannot charge".**
- `handsOff`'s Disconnected/NoPower and `scheduledChargingPending`/`respectVehicleSchedule` refusals moved into a new `refusesStart()`. `handsOff` calls it after its limit check.
- `whyQuiet(budgeting=True)` calls the same function, so the code is shared, not copied.

**3. Unknown state no longer overrides the hardware.** `Belief.wantsPower()` returns one of three values:
- False when `whyQuiet(budgeting=True)` gives a reason the car won't charge.
- True only when the registry shows the car will take power, with a known battery and a known limit above it: a pending limit desire, or a start desire or a paused ("Stopped") session.
- None otherwise.

`ChargingPoint.wantsToCharge` then decides:
- a point that is drawing wants power;
- otherwise it follows `wantsPower` when that is not None;
- otherwise it falls back to the members' own reports.

Consequences:
- A car known only to be plugged in gets 0.
- A Gen3 unit reporting "complete" for a car the registry knows nothing about gets 0.
- A Gen2 echo can no longer keep a car that is at its limit in the budget.

**4. "Stopped" car-side points.** A car member now counts as drawing only while it is charging and awake (`VehicleEndpoint.currentAmps`; `wantsToCharge` is built on it). A Stopped car therefore goes through the same rule: at or above its limit, or under its own schedule, it gets no share. The stop-desire behaviour is unchanged: a stop desire doesn't remove a car from the budget, but it still blocks the wake.

**Minor findings:**
- The telemetry settle window is now skipped when budgeting.
- `finished()` treats a car asleep after "Charging" as finished only when its battery or limit is unknown, or its battery is within `FINISHED_MARGIN` (2 %) of its limit.
  - `VehicleEndpoint` keeps its own asleep-after-Charging rule for its report. Without it, a car whose battery reading went stale mid-session would count as drawing while asleep (`test_watch` guards this).
- The `ChargingPoint` comments are reworded.
- The test fixture comment now describes the car's state, not the box.
- `test_charging_points.py::test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum` is back to its original form. With the members as the default it passes unchanged, so its guard is back.
- The sleep-pilot reorder from round 0 stays: the car there is at 50 of 50.

### How the offered check and the raise wake fit together now

"Nothing offered" still keeps asleep any car that can't get power. A pending raise above a known battery makes `wantsPower` true, so the car is budgeted, `offered` is above 0 and the wake goes through. If power is too scarce to share and a car is already charging, the raised car gets nothing. That car is then not woken until power frees up.

### Tests added (`tests/unit/test_wants_power.py`)

Each test failed on `ef7be20f` (the lib stashed back to it) and passes now.

| Test | On `ef7be20f` | Now |
|---|---|---|
| Charging car plus a raise-pending idle car on 9 A, both orders: the charging car gets 9 A, the idle car 0 | FAIL ×2 | pass |
| Car-side car known only to be plugged in, next to a charging car: no share | FAIL | pass |
| "Stopped" car at its limit (80/80 and 85/80): no share | FAIL ×2 | pass |
| Gen3 "complete" with a car the registry knows nothing about: offered 0, unit target 0 | FAIL | pass |
| Car on its own schedule (Stopped 70/80), car-side and on Gen2 with echo 0, over 30 passes with a varying budget: offered 0 every pass, no wake | FAIL ×2 | pass |

### Counts

- **Suite:** 2,475 passed and 1 xfailed, exit 0 (the 2,459 baseline plus 16 new tests).
- **Parity:** the file is unedited and every row passes.
- **Lib line delta against base `1a0b7d67`:** +94 / −19, net **+75**.

| File | Net lines |
|---|---|
| `Belief.py` | +45 |
| `ChargingPoint.py` | +14 |
| `VehicleEndpoint.py` | +6 |
| `TWCMaster.py` | +6 |
| `Gen2TWC.py` | +4 |

- **Formatting:** every touched lib file passes black.

### Declined or adjusted

- **Apply the schedule refusal to the wake path too ("arguably").** Declined, following ruling 2. A car on its own schedule still gets 0 offered, so it isn't woken.
- **The margin for asleep-after-Charging.** Applied in `finished()`, which the wake and budgeting rules share. Not applied to `VehicleEndpoint`'s own report, for the stale-battery reason given above.

## Round 2 (re-review fixes)

I amended `05ca8c4d` into `833d6a44`, which keeps two commits:
- `ef7be20f`
- `833d6a44` "Admit a car to the budget only on positive evidence it will charge"

Nothing is pushed.

### Changes

**1. A limit desire counts as evidence only when it raises the limit.** In budgeting, `whyQuiet` counts a pending limit desire only if the limit it resolves to is above the believed limit, or the believed limit is unknown. Held and RELEASE desires resolve the same way they do for the wake. A start desire or a paused session counts when its limit is known. Every case also needs a known battery.

"Paused" means the car's own `chargingState` is "Stopped". `known(CHARGING)` would let a TWC's stand-in for idle current count as paused: a Gen3 unit at 0 A reads as "Stopped". The new Gen3 test caught exactly that.

Last night's replay still passes: a raise from 70 to 90 gets wake → limit → wake → setAmps 32.

**2. Serving order.** The plain maxPower sort is back. If a point's fair share is below its minimum while any drawing point is still pending, the power goes to the drawing points:
- an idle point gets 0;
- a drawing point gets an even split among the drawing points still pending.

That is one list built per iteration (`charging`), and the drawing-first sort and the intersection set are gone. At 40 A, a charging car capped at 48 A and a woken car capped at 16 A get 24 + 16 A.

**Adjusted: the reviewer's exact fix.** The suggested version gives a non-drawing point 0 and leaves the drawing point unchanged. I implemented it, and it failed the 9 A starvation test in both registration orders. When the charging point comes first in maxPower order, its own fair share (budget ÷ 2) is already below its minimum, so it gets 0, and the idle point then takes everything. The drawing point's share therefore has to be split among the drawing points only. Two charging cars on too little power still behave as on the base: one is stopped and the other gets the rest.

**3. Size.**
- `wantsPower` is gone. `whyQuiet(budgeting=True)` now returns one of:
  - a reason when the car won't charge;
  - None on evidence that it will;
  - `""` when the registry can't say, and then the members' reports decide.

  `ChargingPoint.wantsToCharge` is its only caller in budgeting mode.
- There is one config lookup, `Presence.masterConfig()`. It is used in Presence, Belief, the Reconciler and Provider.
- `refusesStart` no longer re-guards `config`.
- The margin is inlined, with its comment.
- Each endpoint now has a `drawing` bool:

  | Endpoint | `drawing` is true when |
  |---|---|
  | Gen2 | `reportedAmpsActual` ≥ 1 A |
  | Gen3 | `currentAmps` ≥ 1 A |
  | Car-side | the car is "Charging" and not asleep |

  `ChargingPoint.drawing` is `any(e.drawing)`. This replaces the fake 1 A `VehicleEndpoint.currentAmps` and the `Gen2TWC.currentAmps` alias. The mock endpoints in `test_charging_points.py` now set `drawing`.

**4. Other minor findings.** The `whyQuiet` budgeting comment is reworded, so the garbled `wantsPower` comment is gone with that function. The CHANGELOG now reads "When there is too little power to share, a car already charging keeps it".

### New tests

Each failed on `05ca8c4d` and passes now:

| Test | Result on `05ca8c4d` |
|---|---|
| `test_a_woken_car_capped_low_leaves_the_rest_to_a_charging_car` (40 A: 24 + 16) | FAIL |
| `test_a_policy_limit_that_is_no_raise_is_no_evidence`, car-side (78 of 80, policy 80, next to a charging car: 0, and the charging car gets 32 A) | FAIL |
| `test_a_policy_limit_that_is_no_raise_is_no_evidence`, Gen3 "complete" (78 of 80, policy 80: 0) | FAIL |

### Counts

- **Suite:** 2,478 passed and 1 xfailed, exit 0.
- **Parity:** the file is unedited and every row passes.
- **Formatting:** every touched lib file was black-clean before and still is.
- **Lib line delta against `1a0b7d67`:** +84 / −20, net **+64** (round 1 was +75). By file:
  - Belief +33
  - ChargingPoint +12
  - Gen2 +5
  - Gen3 +5
  - TWCMaster +4
  - Presence +4
  - VehicleEndpoint +3
  - Provider and Reconciler 0

  The shared config helper costs about 3 lines more than the copies it replaces.

## Round 3 (final-check minors)

I amended these into the second commit, which is now `920c6505` (it was `833d6a44`). The branch is still two commits, `ef7be20f` and `920c6505`.

1. **A charging car keeps its minimum when the minimums differ.**
   - An idle point now gets 0 if its offer would leave the pending charging points below the sum of their minimums.
   - A charging point whose fair share is below its minimum splits the remaining power among the charging points still pending.
   - Idle points no longer get a blanket 0. The minimum check zeroes a share that is too small, and the new floor check covers the rest.
   - The new test `test_a_charging_car_keeps_its_minimum_when_minimums_differ` runs at 11 A: a Gen2 car charging with a 6 A minimum, and a woken car-side car with a 5 A minimum. In both serving orders, the Gen2 point gets 11 A and the idle car gets 0.
   - On the previous commit, the idle-first order failed and the charging-first order already passed.
   - The 9 A and 40 A tests still pass.
2. **Readability in `Belief.whyQuiet`.**
   - The local that holds the charging state is now named `state`.
   - `refusesStart` is called once.
   - Both values are computed only on the budgeting path.
   - `handsOff` already normalises `config`, so `refusesStart` takes it as given.

**Counts**

- Suite: 2,480 passed and 1 xfailed, exit 0.
- Parity file: unedited, and every row passes.
- Black: clean on every touched file.
- Lib delta against `1a0b7d67`: +90 / −20, net **+70**.
