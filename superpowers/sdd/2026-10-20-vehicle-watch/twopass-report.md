# Two-pass power split (#709): report

Branch `fix/admit-would-charge` lives in the worktree `.../scratchpad/wt-admit`. The work is a second commit, **de7162d5**, on top of d053ddc7. It is not pushed and not squashed: the two commits read as "fix the wake", then "build #709 on it".

## Design as built

### Pass 1: admission (`TWCMaster._admit`, once per tick from `distributeEVSEPower`)

**Budgets.** The budgets are `_budgets()` plus `all`, which is the policy's watts at the voltage the TWCs measure.

**Willing cars.** The willing set is every named car for which `wouldCharge` holds.

**Order.** Points are sorted by `_drawing(point)`, with the existing point order as a stable tie-break.
- `_drawing` means real current flow. For a point with a local member, that is its TWC's `reportedAmpsActual`, or a Gen3 unit's `currentAmps`, at or above 1 A.
- For a car-side point, it means `wantsToCharge` and "Charging".
- It is not `wantsToCharge`. That counted a "Stopped" car-side car as drawing, which would let it take a Gen3's seat.

**Admission.**
- **Candidates:** points that are not read-only and either want power (`wantsToCharge`, which keeps today's Gen2/Gen3 behaviour for anonymous cars) or serve a willing car.
- **The test:** a candidate is admitted when its `minPower <= maxPower`, and its minimum fits what is left in `all` and in each of its controllers' budgets.
- **Refusals:** a refused point (its maximum is under its minimum, and the power was there) is still logged by `_noteRefusedPoint`.

**Which car is a point's.** `_carsAt(point)` returns the point's `vehicleKey`, plus any `heldKey` of its TWC. The `idle=[1]` guess is gone.

### Snapshot (`Belief.Admission`, published as `master.admission`)

The snapshot is an immutable NamedTuple that is swapped by reference. `NO_ROOM` is the empty value. It has three fields:

| Field | Meaning |
|---|---|
| `cars` | Cars at admitted points, plus cars at any other point whose minimum fits what admission left over. This "room a start would find" covers a raise that reaches the reconciler before the next tick (test below). |
| `placed` | Every car some point serves. |
| `spare` | What is left fits the car-side minimum (`VehicleEndpoint.MIN_AMPS`). Applies to a car on no point. |

**When it is `NO_ROOM`:**
- if `chargingPoints()` or `_admit` raises (`distributeEVSEPower` catches the error, sets it and re-raises);
- in `withdrawOffers`;
- in `__init__`.

### Pass 2: allocation (`waterLevel`, plus the budget loop in `distributeEVSEPower`)

**`waterLevel(points, watts)`** gives each point `clamp(L, min, max)`.
- It works in amps at each point's own voltage (`point.convertWattsToAmps`) and prices the result back in watts.
- It sorts the breakpoints (each `min` adds slope, each `max` removes it) and walks them once.
- If every point fits, everyone gets their maximum.

**Budgets.**
- First, the water level runs over all admitted points.
- If any budget would be exceeded, that budget's points get a water level of their own within it, and are fixed.
- The rest share what remains.
- Points that were not admitted get 0, as before, so an idle Gen2 still gets its hardware minimum.

The fair-share loop is deleted.

### Desire rules (`TWCMaster._followAdmission`, per point, after the slave loop in `controlPass`)

**Named cars only.** Anonymous cars are skipped: in mode 1, an anonymous car's stop fans out to every candidate, including named cars on other points.

**Admitted car.** A car in `admission.cars` that isn't charging and `wouldCharge` gets `cancelStopCarsCharging` followed by `_wantCharging(True)`. A stale stop is therefore replaced, never left blocking.

**Car not admitted, on a point with no Gen2 TWC.** This means car-side points and Gen3 points.
- If the car has been "Charging" with no admission for 60 s, it gets `_wantCharging(False)`.
- The 60 s mirrors the gate's hold. Without it, power swinging across the minimum sent a start or stop on every pass: 19 starts and 20 stops over 40 passes on Fleet, which is paid.
- A pending start is withdrawn.

**Gen2.** This stays with the chargeGate: a 0 offer leads to the gate's stop.

**Gen2 "withdraw".** `withdrawStartCharging` skips a car that is in `admission.cars`. The skip moved there from `controlPass`, as the review suggested.

### Wake check

**`whyQuiet`:**
1. `_wontCharge` runs first.
2. Then "no room to start", unless the car is in `cars`, or it is unplaced and `spare` is set.
3. Then the telemetry settle wait.

**`_wontCharge`:**
- no longer checks for a stop desire;
- gains one rule (see deviations): "Complete" with no limit change pending means won't charge.

**`Reconciler.plan`** calls `whyQuiet` only when `not d.restore and d.value is not False`. Stops and restores never run the check.

**Unknown state after a restart.**
- A CHARGING attempt for a car whose `known(CHARGING)` is None may wake it once per reconciler lifetime.
- The car is recorded in `report()` only when the wake was actually sent (`not O.isNotSent`).
- To switch this off, set `Reconciler.WAKE_UNREAD_ONCE = False`.

### Deviations and judgment calls (please review)

1. **Limit lowers still run the wake check.** The brief said they shouldn't. Two existing tests encode the opposite on purpose:
   - `test_a_car_that_will_still_charge_may_be_woken_to_lower_its_limit`;
   - `test_a_car_wakes_for_a_lower_once_there_is_room_to_start`.

   A car still below its new limit can start on its own schedule. With the snapshot, the check can no longer raise from points.
2. **`wouldCharge` gains "Complete at its limit" (+2 lines).** Without it, a "Complete" car with an unknown battery level held a seat and half the power. A pending limit that differs from the believed limit still counts as would-charge, which covers last night's raise.
3. **Cars on no point.**
   - No admission, so no start and no budget, as the brief says.
   - The wake check gives them room when the leftover covers the car-side minimum, which replaces `idle=[1]` (review finding 5).
   - Without this, every Fleet-only or presumed-home car with no plug reading lost its limit raises entirely: about 30 parity rows went to `commands == []`.
4. **Gen3 counts as car-side for stops.** Before this change, a Gen3 car with no room kept charging at the unit's minimum. Now it is stopped after 60 s out. The brief did not cover Gen3.
5. **With power on, the rate goes before the start.** An admitted car that is not yet charging gets an AMPS desire, and the reconciler plans the rate before the start. The Fleet replay is limit, `set_charging_amps`, start, with one wake. d053ddc7 sent limit then start in the same window, so this is one more paid command there; on d053ddc7 the rate would follow later, once the car read as charging.
6. **Hysteresis is by drawing, not seniority.** When both cars draw and the power drops so only one fits, point order decides. A car that has stopped is no longer "drawing", so the choice holds after that.

## Tests

Two test files hold the new tests. `tests/unit/test_distributor_loop.py` (rewritten) holds the pure arithmetic, on EVSEInstance-based points. `tests/unit/test_admission.py` (rewritten) uses a real master, store and reconciler, a scripted BLE, or the real TeslaAPI with `FleetCar`.

"On d053ddc7" separates real behaviour failures from AttributeError and monkeypatch failures, which are marked "API".

| # | Test | On d053ddc7 | After |
|---|---|---|---|
| 1 | `test_a_minimum_that_does_not_fit_wastes_no_share`: 25 A, A 6–32, B 20–32, both orders | API; old split: B dropped and its share wasted | the first in order gets 25 |
| 1 | `test_the_drawing_point_keeps_its_seat`: A or B drawing | API | the drawing one gets 25 |
| 1 | `test_with_no_car_that_would_charge_nothing_is_admitted` | API | 0 / 0; both have room |
| 2 | `test_a_gen3_and_a_car_share_at_one_level`: 30 A | fails, [0, 15] | 16 / 14 |
| 2 | `test_a_gen3_and_two_cars_share_at_one_level`: 40 A | fails, [0, 13.3, 13.3] | 16 / 12 / 12 |
| 2 | `test_a_capped_point_leaves_the_rest_to_the_other`: 48 A | passes | 16 / 32 |
| 2 | `test_each_point_at_its_maximum_when_the_total_is_more_than_enough` | passes | maximums |
| 2 | `test_a_gen3_budget_binds_its_units_as_a_group`: two units on 32 A plus a car, at 60 A | fails, [16, 16, 20] | 16 / 16 / 28 |
| 2 | `test_a_budget_that_fits_only_one_minimum_admits_one` | fails, [0, 10] | 10 / 0 |
| 3 | `test_a_car_side_arrival_never_evicts_a_drawing_gen2_car`: both point orders | API | 11 A gives 6 / 5; 10 A gives 10 / 0 |
| 4 | `test_the_drawing_car_keeps_its_seat_as_power_wavers_at_the_edge`: 20 passes; B drawing, A first in order | API | B keeps its seat on every pass |
| 5 | `test_last_nights_raise_wakes_and_starts_the_car` (BLE) | fails (no setAmps) | wake, limit, wake, setAmps, wake, start |
| 5 | `test_last_nights_raise_on_fleet_costs_one_wake`: real TeslaAPI, `FleetCar` | fails: no `set_charging_amps` | limit, amps, start; exactly 1 `wake_up` |
| 6 | `test_a_dusk_stop_does_not_block_a_midnight_start`: Gen2, 0 offer at dusk, stop, sleeps at 00, then 32 A and a raise | fails (the stop desire stays) | stop replaced; wake, limit, start |
| 7 | `test_a_car_on_its_own_schedule_is_never_admitted`: 1 h | passes | no wake, no start, no AMPS desire |
| 8 | `test_stops_still_go_out_when_admission_raises` | API | admission is `NO_ROOM`; limit and stop go out unwoken |
| 8 | `test_a_withdrawn_pass_wakes_nothing` | fails | "no room to start" |
| 9 | `test_a_fleet_only_restart_wakes_a_car_of_unknown_state_once`: car never wakes, 2 h, then a "restart" | fails, 4 wakes | 1 wake, then 2 after the restart |
| 9 | `test_the_restart_wake_switches_off` | API | 0 |
| 10 | `test_the_gen2_gate_and_admission_never_loop`: 4 × 20 passes | passes (guard) | one stop, one start |
| — | `test_a_car_held_at_00_waits_for_room_beside_a_drawing_twc`: real Gen2 holding the car (`heldKey`) beside a drawing Gen2 | fails | 11 A: no room; 12 A: room, 6 A, start |
| — | `test_a_car_side_car_at_the_edge_is_stopped_only_after_a_minute_out` | — | 0 commands over 40 swings; stops after 60 s out |
| — | `test_an_anonymous_car_is_neither_started_nor_stopped_by_admission` | — | fails without the `vin` guard |
| — | `test_a_raise_set_between_ticks_finds_the_room_kept_for_it`: unwrapped `VehicleReconciler.pass_` | — | wake, limit |
| — | kept from d053ddc7: at its limit, no power, Gen2 echo 0, refusal not re-woken | — | pass |

**The `inline()` test helper.** It now refreshes admission before each reconciler pass (`m._admit(m.chargingPoints())`), since the tick does this live. Without it, every reconciler test would need a `controlPass`.

**Tests that don't rely on the helper.** Two tests use only `controlPass`, and one uses the unwrapped `VehicleReconciler.pass_`:
- `test_presence::..._held_at_00_needs_the_twcs_minimum` shows the snapshot stays stale until the next tick;
- `test_a_car_held_at_00...` uses `controlPass` alone;
- the race test is the one on the unwrapped `pass_`.

## Review findings (admit-review.md)

| Finding | Severity | Status |
|---|---|---|
| `whyQuiet` raises for every aspect when `chargingPoints` raises | important | **Fixed.** The check runs only where a wake is possible. It reads the snapshot, and a failure makes the snapshot `NO_ROOM`. Test 8. |
| Fair-share eviction when minimums differ | important | **Moot.** Admission is by minimums and allocation by water level. Test 3. |
| A stale satisfied stop blocks a midnight start | important | **Fixed.** A stop no longer counts in `wouldCharge`, and admission replaces the stop with a start. Test 6. |
| Parity pinned at 0 A hides paid moves | important | **Fixed.** The `gen2()` pin is gone and the rows run at the setup's 32 A. Paid counts are asserted; moves are below. |
| `idle=[1]` | minor | **Fixed.** No admission for an unplaced car; the wake check uses the car-side minimum. |
| Car-side endpoint on an unnamed Gen2 at 00 under-admits | minor | **Unchanged.** The two are still separate points. This is within the accepted one-cycle overshoot. |
| CHANGELOG | minor | **Superseded by the brief.** There is no bug line. A v1.4.1 Features line covers #709. The existing wake line ("its TWC or charger offered power, no stop wanted") is corrected to "with room for it in the power on offer". |
| `gen2()` overwrites earlier power | minor | **Fixed** (pin removed). Rows that need no power set 0 explicitly: `unnamedAt00`. |
| Fake points in tests 6 and 6b | minor | **Fixed.** A real Gen2 holds the car (`heldKey`) beside a second drawing Gen2. Fake points remain only for allocation arithmetic. |
| Withdraw skip in `controlPass` | minor | **Moved** into `withdrawStartCharging`. |
| `_room` could be shorter | minor | **Moot.** Deleted. |
| `chargingPoints()` rebuilt per car | minor | **Fixed.** Once per tick, then the snapshot. |

## Suite, parity, size

**Suite.** 2488 passed, 1 xfailed, exit 0. The d053ddc7 baseline was 2472 passed and 1 xfailed.

### Other existing tests changed

**`test_charging_points`:**
- A "Stopped" car with an unknown battery level would charge, so it is now admitted: its TWC gets 32 A, where it used to get the idle 0.
- An asleep "Charging" car with an unknown battery level keeps its seat and rate until its level is known to be at its limit (test renamed).
- The fixtures gained a registry and `reportedAmpsActual`.

**Other files:**
- `test_control_tick` retired-settings test: two equal drawing cars at 10 A. The first in point order now gets the 10, where the old loop gave it to the second.
- `test_distributor_voltage`: real points.
- `test_presence` restart-at-00 row: no start any more, which is back to the base's empty call list. The car is on no point while an unnamed TWC is plugged in.
- `test_charging_reconciler`, two rows: a car at its limit, or 0 A, keeps the rows' original intent.

### Parity, run with power on

The `gen2()` pin is removed. Against d8f036d1 with the same 32 A, the base already fails 10 rows. These moves were measured and are explained in each row.

**Paid moves.** Each one is the restart's learning start for a Fleet-only car at a Gen2 whose charging state is unknown:

| Row | d8f036d1 with power | Now |
|---|---|---|
| `fleet_only_checks_a_car_awake_with_one_read`, online | (1, 0, 1) | (2, 0, 1): +1 read, the start's read, which learns "Complete" |
| `fleet_only_checks_a_car_awake_with_one_read`, asleep | (0, 0, 0) | (2, 1, 0), and the unplug is now seen: +1 wake and +1 read for the start; the car is then awake, so the unplug's check reads it (+1) |
| `fleet_only_checks_past_its_stored_reading` | (2, 0, 1) | (3, 0, 1) |
| `fleet_only_checks_past_its_cached_asleep` | (1, 0, 0) | (3, 1, 0) |

The 0-power expectations were (1,0,0), (0,0,0), (2,0,0) and (1,0,0). The base's own +1 command, `set_charging_amps`, appears once power is on.

**Free moves (BLE).**
- Several Gen2 rows now show `wake` with `charging-start` and `charging-set-amps`. With power, the car is started and rated, which the base also did for the rate.
- The morning-wake row re-sends the BLE start on each read that shows "Stopped". The scripted car never draws.
- Two rows show one more BLE read: the start's read. These are `each_unplug_departs` (3 reads → 4) and `03_00_flicker` (0 → 1).
- The idle-car row's raise now wakes over BLE, which is this fix's purpose with room.

**Rows made explicit.**
- `never_woken_by_a_restore` gets a car at its limit (battery 50), so it still tests "restore never wakes" with power on. Otherwise a car that would charge was rightly started over Fleet, at (7, 1, 1).
- `unnamedAt00` sets 0 A explicitly ("no power to share").
- `a_sleeping_car_at_00_with_power` now also starts the car: two free BLE calls.

### Lib delta

| Against | Added | Removed | Net |
|---|---|---|---|
| d8f036d1 | 208 | 99 | **+109** |
| d053ddc7 | 184 | 119 | **+65** |

This misses the near-zero target.

**What was deleted:**
- the fair-share loop, about 50 lines, with no part of it surviving;
- `_room` and `admissible`;
- `master.offered`, removed in d053ddc7.

There are no helpers left without callers.

**What remains:**

| Block | Lines | Why |
|---|---|---|
| `waterLevel` | ~19 | The breakpoint pass |
| `_admit` | ~36 | Ordering, `fits`, the `Admission` construction (`cars`, `placed`, `spare`), and the voltage comment moved here |
| Budget-group loop | ~18 | Includes the `spent` helper |
| `_followAdmission` | ~29 | Start, stop, withdraw; the vin guard; the 60 s hold |
| `_drawing`, `_carsAt`, `_draws` | ~16 | |
| `Admission` and `NO_ROOM` | ~10 | |
| `_refusesStart` split, Complete rule, `wouldCharge` | ~15 | |
| Reconciler: once-per-restart wake and the gated check | +13 | |

**Possible duplication.** `fits` and the allocation's `spent` both walk `_draws` and decrement. A shared helper saves no lines. The two "is drawing" tests differ on purpose: one works at point level, the other on the car's state.

## Concerns

1. **Size.** +109 net against d8f036d1, against a target of about zero.
2. **Fleet's restart learning costs more than one wake.** It costs the wake plus a read, and once the car is awake, later presence checks read it too (the parity moves above). An awake car still costs one read.
3. **The start re-sends while the car stays "Stopped".** A start the car accepts but doesn't act on is re-sent on each newer reading that shows it stopped (seen over BLE in the morning-wake row). This is the reconciler's existing retry rule, but admission now creates starts more often.
4. **Car-side and Gen3 stops are new.** Before, a car offered 0 just kept charging. They are held 60 s, and minChargeLevel still protects a car below it.
5. **Waking for a lower** is kept, against the brief (see deviation 1).

## Round 1

The review fixes and the user's rulings are folded into the second commit. The branch is now d053ddc7, then **eb19fd4c** (it replaces de7162d5). Nothing is pushed.

### What changed

**A start is never withdrawn once it has gone (ruling 1, finding 1).**
- `_followAdmission` has no withdraw branch.
- `Reconciler.plan` returns None for a CHARGING desire when `whyQuiet` is "no room to start". The desire and its paid budget stay, and the start is sent when there is room again, if it is still unsatisfied.
- The Gen2 gate's withdraw (`withdrawStartCharging`) now clears only a start that has never been sent (`lastSentAt == 0`), for a car without room. On a protocol-2 Gen2 it used to clear the desire on every dip, and the next offer made a new desire with a fresh budget. The new parity row measured 41 paid `charge_start` in an hour at a 90 s swing; it is now 2. A queued start that has not run is still withdrawn (`test_a_queued_start_is_withdrawn_when_the_offer_drops`).

**One hold for both directions, on `config.startStopDelay` (ruling 2, findings 3 and 5).**
- `_followAdmission` times every stop. A car without room whose point draws is stopped once its (room, chargingState, draw) has held for startStopDelay, where a draw change over 0.8 A restarts the hold. This uses the Gen2 gate's steady-draw rule, now for every kind of EVSE. A protocol-1 Gen2 is never stopped, as before.
- The record is the car's own readings, so it reads the same at each point the car may be on: a car-side point plus an unnamed TWC still holding the car. A per-point "drawing" flag would flip between those two points and reset the hold on every pass.
- The record starts when the car's state changes, so a car that starts on its own after 10 minutes without room gets the full hold (finding 5). There is a test.
- `stopCarsCharging` is called on each held pass, as the gate did, so the mode-1 policy override still runs.
- `chargeGate` now returns only start and withdraw. Removed: the stop and cancelStop branch, the cancelStop debug line in `controlPass`, and `TWCSlave.startStopDelay` and `timeReportedAmpsActualChangedSignificantly`, which had no readers left. The 0.8 A monitor stays for the policy webhooks.
- Restart: if we stopped the car (its desire is False), it is started again only once room has held for startStopDelay. A first start, with no desire, goes at once.
- A Gen2 behaves as before: when its offer rises, `controlPass` drops our stop and the gate starts the car at once.
- One Gen2 difference: the base held the stop at least 60 s after the offer changed, even with startStopDelay set below 60. Now the one setting governs.

**Retries after an unanswered wake (ruling 3): unchanged.** **Limit lowers (ruling 4): unchanged.**

**A car on no point (ruling 5) is now also started.**
- `controlPass` runs `_followAdmission` on `admission − placed`, once what is left covers the car-side minimum. Once the car draws, its point is allocated like any other.
- Two existing rows had asserted that no BLE call was made. They are updated, and the moves are free:
  - `test_gen2_steady_00_after_link_does_not_block_startup_charging`: wake and charging-start over BLE, plus one more ping (the start's ping for a car only presumed home). Paid is still (0, 0, 0).
  - `test_presence::test_restart_steady_00_with_telemetry_plugged_is_home_and_restores_nothing`: wake and startCharging, with nothing restored.

### Minor findings

| Finding | Status |
|---|---|
| Belief "Complete at its limit" vs our own write | **Fixed in `uncompleted`.** A Complete read before our last limit write no longer counts when the battery level is unknown (an unknown battery already counts as "would charge"). The extra rule in `_wontCharge` is reverted. `known()` is fixed too, so the start is no longer "satisfied" by the stale Complete. Test: `test_a_raise_to_a_complete_car_of_unknown_battery_starts_it`; before the fix it went wake, limit, wake, setAmps with no start. |
| `since` recorded before the car drew | **Fixed** (above). |
| Room not exclusive | **Fixed.** Points with no wanting car take room in point order after the seated ones, from what is left. `test_with_no_car_that_would_charge_nothing_is_admitted` is now `{A}`. Cars on no point still all get the leftover room; the next tick rebalances. |
| `try` too narrow | **Fixed.** The whole split is inside it. Test: `test_a_failed_split_leaves_no_room_and_a_forgotten_car_no_hold`. |
| `_unadmitted` never pruned | **Fixed.** `_held` is popped in `_vehicleRemoved` (same test). |
| `wouldCharge` recomputed per car | **Fixed.** `_admit` keeps `self._willing`. |
| Admission's three fields | **Fixed.** It is a frozenset: the unplaced cars are added when what is left covers the car-side minimum. `NO_ROOM` and the NamedTuple are gone. |
| `spent` closure | **Fixed.** It is a dict comprehension. The suggested one-line `next(...)` comes out longer under black. |
| `WAKE_UNREAD_ONCE` | **Fixed.** It is now the class attribute `VehicleReconciler.wakeUnreadOnce`. |
| Withdraw skip reads room cars | **Moot.** The withdraw now skips any start that has gone. |
| CHANGELOG sleeping-car line | **Fixed:** "except while there is no place for it in the power on offer". The #709 line now describes the startStopDelay hold both ways, and the start that waits for a place. |
| Parity Gen2 is protocol 1 | **Fixed.** New row `test_a_protocol_2_gen2_with_power_at_its_minimum_keeps_one_start_budget`: Fleet only, the car stays Stopped, the power swings across 6 A every 90 s for 1 h. Asserted: `set_charging_amps` plus 2 `charge_start`, paid (0, 0, 3). |
| Refusal check re-derives fits | **Folded** into the admission loop's two branches. |

### Rulings' tests (`test_admission.py`)

**`test_a_start_without_room_waits_and_keeps_its_budget[10|90|150|None]`.**
- Setup: a Fleet car on its own point that accepts starts but stays Stopped, with a feed every 60 s. The power swings across 5 A for an hour at each period; `None` means steady power.
- Each period sends exactly 2 paid `charge_start`. The review measured 60, 40 and 24.

**`test_power_across_the_minimum_every_4_minutes_for_2_hours`.**
- This is the review's scenario: 4 minutes in, 4 minutes out, for 2 h, with a car that follows commands.
- Result: **15 stops and 15 starts**, the same as before this round. Each 4-minute phase outlasts the 60 s hold, so a hold of startStopDelay cannot remove these. What the start-side hold changes is that each restart now waits 60 s of room.

**Other tests.**
- `test_a_car_stopped_for_room_restarts_once_room_has_held`: no start in the first 50 s of room, one by 70 s. It fails without the start-side hold.
- `test_a_car_side_stop_waits_start_stop_delay_with_the_draw_steady`: startStopDelay is 120. The car starts itself after 10 minutes without room, and its draw changes at 100 s; it is stopped only 120 s after that. It fails if the hold ignores the state change.

### Suite, parity, size

**Suite:** 2496 passed, 1 xfailed, exit 0. That is 8 more than before this round: 10 new tests, minus 2 TWCSlave attribute tests deleted with the attributes.

**Parity:** no existing paid count moved. The new protocol-2 row asserts (0, 0, 3). The two free moves are listed under ruling 5.

**Lib delta** against d8f036d1: +232 −146 = **+86**, down from +109.

| Change | Lines (approximate) |
|---|---|
| Admission as a frozenset | −10 |
| The gate's stop and cancelStop, and their log line | −14 |
| The dead TWCSlave attributes and comment | −12 |
| The `uncompleted` route in place of a second Complete rule | −3 |
| The folded refusal check | −3 |
| Added: unified hold, start-side hold, unplaced-car start, plan() hold, withdraw-once-sent | about +17 |

Black is clean on the touched lib files and the black-formatted tests. `test_charging_reconciler.py` is not black-formatted and was left as it is.

## Round 2

This round fixes the re-review's findings and applies the coordinator's rulings, folded into the second commit. The branch is now d053ddc7, then **f880a464** (it replaces eb19fd4c). Nothing is pushed.

### Fixes

**1. While the hold runs, a car is cut to its minimum (important).**
- In `_admit`, a point that is drawing but doesn't fit is held at its minimum, and that minimum is counted against every budget it draws from. This uses the same `left`, so a later point can't be seated on that power. The admitted points' water level runs on a copy of the budgets with the held points' minimums taken out (`shared`).
- Gen2 points are left out of this, because a Gen2 TWC's 0 offer is already its minimum. Counting it would also make `controlPass` drop our stop each pass while the offer is above 0.
- What this means per EVSE kind:
  - car-side: a paid `set_charging_amps` down to 5 A;
  - Gen3: the unit's target is its minimum, which keeps it in the controller's active set.
- The stop still comes from `_followAdmission` after the hold. The hold record restarts whenever the car's reported draw moves by more than 0.8 A, so the drop to the minimum restarts it too, where a draw is read.

**2. Under a fixed policy, the stop is immediate (ruling).**
- If `Policy.policyIsGreen()` is False, the hold is −1, so any time held counts as enough. This applies to the start-side hold as well: with no EMS noise there is nothing to wait out in either direction.
- With no Policy module, the hold applies.
- The Gen2 test stub in `tests/unit/gen2_helpers.py` now reports a green policy, so the existing heartbeat tests keep their hold. Nothing else reads that stub's answer except the status page.

**3. A Gen2 stop needs more than 4 A of draw (ruling).** The stop branch requires every Gen2 member to be protocol 2 and drawing over 4 A, as the old gate did.

**4. The gate's withdraw is deleted (ruling).**
- Removed: `withdrawStartCharging`, the withdraw branch in the gate, and the dispatch dict. `chargeGate(key)` now just returns whether to start.
- Removed with them: `test_a_queued_start_is_withdrawn_when_the_offer_drops`.
- Updated: the fan-out test and `test_zero_offer_holds_a_pending_start_and_sends_no_wake`. The start desire now stays, held for room, and nothing is sent.

### Minors

- **Only an undelivered stop is cancelled.** The not-held arm cancels unless the stop desire has already been sent (`lastSentAt >= desire.at`).
  - `test_disruptive_stop_is_sent_once_until_new_evidence_then_reasserted` relied on the old cancel to clear a delivered stop. Its reassert step now cancels explicitly, so it is a new desire as before.
  - With this change, a delivered stop that hasn't taken is no longer reasserted when the draw changes during a stretch without room. That is the same as base's steady case.
- **`_drawing(point)` can no longer see None.** It is computed once per call as `point is not None and _drawing(point)`.
- **Held means strictly more than startStopDelay** (`>`). A control pass that lands on the same second as the end of a 60 s low reading doesn't stop the car. No test catches the `>=` boundary: the tests' 10 s passes never land on it.
- **Cars on no point** still share the leftover non-exclusively (ruling: leave it).

### Tests

| Test | Shows |
|---|---|
| `test_a_car_side_car_without_room_runs_at_its_minimum_then_stops` | rate 16, then 5 during the hold, then a stop after startStopDelay |
| `test_a_gen3_unit_without_room_is_held_at_its_minimum` | the unit's target is its `minPower` during the hold, then `charge_stop` |
| `test_one_low_ems_reading_stops_nothing[car-side\|Gen2\|Gen3 × 30\|60]` | 300 s with power, then one low reading for 30 s or 60 s, then 300 s: no stop |
| `test_under_a_fixed_policy_a_car_without_room_stops_at_once` | a stop on the first pass |
| `test_a_gen2_car_drawing_4_a_or_less_is_not_stopped_for_room` | 300 s at 3 A without room: no stop; at 16 A: one stop |
| `test_distributor_loop::test_a_budget_that_fits_only_one_minimum_admits_one` | the second unit not drawing gives 10 / 0, as before; both drawing gives 6 / 6, the second held at its minimum |

Checked by breaking the code:
- Without the held minimum, the car-side and Gen3 minimum tests fail.
- Forcing a green policy fails the fixed-policy test.
- Dropping the 4 A threshold fails the Gen2 trickle test.

The one-low-reading tests also pass on eb19fd4c (60 s at 10 s passes never reaches the hold), so they stand as guards rather than as proof of a fix.

### Suite, parity, size

- **Suite:** 2505 passed, 1 xfailed, exit 0. That is 10 new tests, minus the deleted queued-start test.
- **Parity:** no paid count moved. The protocol-2 Gen2 row is still (0, 0, 3) without the withdraw.
- **Black:** clean on every touched file that was black-formatted on base. `test_charging_reconciler.py` was not and is left as it was.
- **CHANGELOG (#709 line):** now covers the cut to the EVSE's minimum during the hold, the immediate stop under a fixed rate, and the Gen2 rule for 4 A or less.
- **Lib delta** against d8f036d1: +247 −166 = **+81**, down from +86. Deleting the withdraw path freed more lines than the held-minimum seat and the policy check added.

## Round 3

This round fixes the final check's important finding, folded into the second commit. The branch is now d053ddc7, then **b2cd5920** (it replaces f880a464). Nothing is pushed.

### The fix: a point cut to its minimum stays there until room has held

`TWCMaster._cut` is a frozenset of the cars cut to their minimum for want of room. It is swapped whole, like admission.

| When | What happens |
|---|---|
| `_admit` holds a drawing point at its minimum | its cars are added to `_cut` |
| A later pass finds room for the point | while one of its cars is in `_cut`, the point is put in the room list (so the car is admitted and not stopped), but it is held at its minimum, counted in the budget, rather than seated for a share |
| `_followAdmission` sees the car's room has held past startStopDelay | the car leaves `_cut` |

Other details:
- Under a fixed policy the hold is −1, so a car leaves `_cut` on its first pass with room.
- An anonymous car that is never stopped (no VIN, no Gen2) leaves `_cut` at once. Otherwise a Gen3 unit with an unnamed car would stay at its minimum.
- A forgotten car is removed from `_cut`.
- Gen2 points are never cut, because their 0 offer is already their minimum.

The final check's minor note (held minimums are subtracted with no fit check) is left as the accepted brief overshoot.

### Numbers (car-side Fleet car, scripted FleetCar, feed every 30 s)

| Scenario | f880a464 | Now |
|---|---|---|
| 6 A / 4 A flap at a 10 s period, 1 h | 120 `set_charging_amps` | **2** (its first share, then one cut to 5 A); no stop, no start |
| 6 A / 4 A flap at a 30 s period, 1 h | 120 | **2** |
| 4-minute oscillation, 2 h | 15 stops, 15 starts, 30 rates | **15 stops, 15 starts, 30 rates** (unchanged) |

**Why the oscillation keeps its 30 rate commands.** Each 4-minute phase outlasts the hold, so every cycle has four commands:
1. cut to the minimum when room goes;
2. stop 60 s later;
3. start once room has held 60 s;
4. restore to the share on the next pass.

The hysteresis cannot remove step 4. The car was cut to its minimum, and the share has to be sent again for it to use the power. The only way to remove that pair is not to cut a car during the hold, which reverses the round-2 ruling. eb19fd4c sent no rates here because it never cut. The test asserts [15, 15, 30] so the cost is on record.

**Tests (`test_admission.py`):**
- `test_power_flapping_at_the_minimum_cuts_the_rate_once[10|30]`: exactly two `set_charging_amps`. It fails on f880a464, at 120.
- `test_power_across_the_minimum_every_4_minutes_for_2_hours`: now asserts stops, starts and rates.

### Suite, parity, size

- **Suite:** 2507 passed, 1 xfailed, exit 0.
- **Parity:** no paid count moved.
- **Black:** clean on the touched files.
- **Lib delta** against d8f036d1: +260 −166 = **+94**, up from +81. The +13 is the hysteresis in `_admit`, its release in `_followAdmission`, and the anonymous-car release, with their comments.

## Round 4

This round fixes the three minor findings from the round-3 check. The fix is folded into the second commit, and the docs commit is replayed on top, so there are still three commits: d053ddc7, **86ba4c18** (replaces b2cd5920) and **900e9d73** (the docs commit, replacing 20c35275). Nothing is pushed.

1. **The cut now ends on room alone.**
   - Each car's hold record is now (room, state, draw, roomSince, since).
   - `roomSince` resets only when room changes. `since` still resets on any change of state or of draw over 0.8 A, which drives the stop's steadiness check.
   - A cut car is released once `now - roomSince > startStopDelay`.
   - Test: `test_a_cut_car_is_released_once_room_has_held_however_its_draw_wanders`. The car's draw reading alternates 5 A and 6 A every pass. It is still at 5 A after 60 s of room and back at 16 A within 10 minutes. It fails on b2cd5920.
2. **Anonymous keys are never cut.**
   - `_admit` adds only cars with a VIN to `_cut` (`isAnonKey`), and the three-line undo in `_followAdmission` is gone.
   - An anonymous Gen3 car is never stopped, so it is never held back either.
3. **A car that leaves is released.**
   - At the end of `controlPass`, `_cut` keeps only cars some point serves.
   - The hold records keep only cars some point serves, plus admitted cars on no point.
   - So a car that unplugs, or is forgotten, comes back with no hold and no cut. The two pops in `_vehicleRemoved` are therefore gone.
   - The cost: a car that drops off every point for one pass loses its hold, which only delays a stop or releases a cut early.
   - Test: `test_a_car_that_unplugs_while_cut_comes_back_with_its_share`. A car cut to 5 A unplugs, and its records are gone on the next pass. Plugged in again 10 minutes later, it gets 16 A at once. It fails on b2cd5920.
   - `test_a_failed_split_leaves_no_room` lost its forgotten-car half, which the unplug test now covers.

**Suite:** 2509 passed, 1 xfailed, exit 0. No parity count moved.

**Black:** clean on the touched lib file and on `test_admission.py`.

**Lib delta** against d8f036d1: +264 −166 = **+98**, up from +94.
- Added: the roomSince field and release (+2), the leaving-car pruning (+4), and the VIN filter and its comment (+2).
- Removed: the anonymous undo (−3) and the `_vehicleRemoved` pops (−2).
- Adding them up gives about +3; the exact count also includes black's line wrapping.
