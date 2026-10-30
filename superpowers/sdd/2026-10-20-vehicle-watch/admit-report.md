# Admission check: report

Branch `fix/admit-would-charge` lives in the worktree
`/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-admit`.
I built it on 1a0b7d67 (commit 7f9b426d), then rebased it onto origin/main (d8f036d1) as **d053ddc7**. It is one commit, it is not pushed, and it doesn't touch CHANGELOG.md.

## Design as built

Everything lives in `lib/TWCManager/Vehicle/Reconcile/Belief.py`. That module already held `whyQuiet` and `handsOff`, and these are pure functions of the registry and the master.

- **`_refusesStart(vehicle, known, config)`**
  - Split out of `handsOff`. It holds the Disconnected/NoPower check and the scheduledChargingPending (respectVehicleSchedule) check, so `handsOff` and admission share one copy.
  - `handsOff`'s own battery-at-limit check stays where it was. It reads the believed limit, so for a car with a pending raise it would wrongly say "won't charge".
- **`_wontCharge(master, vehicle)`**
  - This is the old body of `whyQuiet`: the same pending/held/believed limit resolution, plugged-in-here, and stop desired, with `_refusesStart` added.
  - It returns a reason, so `whyQuiet` keeps its log text.
- **`wouldCharge(master, vehicle)`**: `_wontCharge(...) is None`.
- **`_room(master, vehicle)`**
  - Free power is the policy's power (`getMaxAmpsToDivideAmongSlaves`, in watts) minus the `minPower` of every other point that is drawing. "Drawing" uses `wantsToCharge`, the test the split itself uses.
  - The car is admitted if free power is at least its own point's `minPower`.
  - Its own point is the point keyed by the car, or a TWC whose `heldKey` still names it. That keeps `heldKey` meaningful now that `offered` is gone.
  - A car with no point of its own (for example, behind an unnamed TWC) must fit the largest idle point's minimum. The advisor flagged the earlier "any headroom" version, which would have admitted a car at 2–3 A of green power.
- **`admissible(master, vehicle)`**
  - `wouldCharge and _room`.
  - Its one comment says it is the admission a split that admits before it allocates can share.
- **`whyQuiet`**: `_wontCharge`, then "no room to start", then the existing telemetry-settle wait. The per-car "nothing offered" check is gone.

`master.offered` lost its last reader, so I removed it: the `held` map in `distributeEVSEPower` and the zeroing in `withdrawOffers`.

## Start path

- **Before:** only the Gen2 `chargeGate` ever set a start desire, and only once the TWC was offered at least its minimum. A sleeping car's TWC reports 0 A max, so that never happens for it. Car-side points (VehicleEndpoint, Gen3) had no start path at all.
- **Added in `TWCMaster.controlPass`, after the slave loop:** each named car gets a start desire (`_wantCharging(key, True)`) when all of these hold:
  - it has no CHARGING desire (so neither a stop nor a start is pending, and a stop blocks the start);
  - it is `pluggedHere`;
  - it isn't already Charging, Starting or Complete;
  - it is `admissible`.
- **"Complete" counts as satisfied for a start.** So a finished car gets no start until our limit write turns "Complete" into "Stopped" (`uncompleted`). After that the start follows the limit, after LIMIT_THEN_START_GAP.
- **Delivered or refused starts don't repeat:**
  - The desire persists once set, so the loop never sets it again.
  - The reconciler settles a delivered start, and a refusal excludes the provider.
  - Test 8 checks this over an hour.
- **Gen2 `withdraw`:** the gate's "withdraw" is now skipped for an admissible car. Without that, withdraw would clear the start desire every tick, and the loop would set it again. After 60 s that becomes a new desire, so the start (and its wake) would resend every minute.

## Tests (`tests/unit/test_admission.py`)

| # | Test | On base 1a0b7d67 | After |
|---|---|---|---|
| 1 | `test_last_nights_raise_wakes_and_starts_the_car`: Complete 70/70, asleep, 32 A, raise to 90 | fails: no calls | wake, setChargeLimit 90, wake, startCharging; once it reports Charging, setAmps |
| 2 | `test_a_car_at_its_limit_is_neither_woken_nor_started` | passes (guard) | passes |
| 3 | `test_a_pending_scheduled_charge_is_neither_woken_nor_started`, 1 h | fails (reason text) | passes |
| 4 | `test_a_car_wanted_stopped_is_neither_woken_nor_started` | passes (guard) | passes |
| 5 | `test_no_power_to_share_wakes_nothing` | fails (reason was "nothing offered") | passes |
| 6 | `test_a_car_is_admitted_only_into_room_left_by_the_drawing_cars`: 9 A, a 6 A drawing car, own 5 A: no wake; 16 A: admitted | fails (no `wouldCharge`) | passes |
| 6b | `test_a_car_on_no_point_of_its_own_needs_an_idle_points_minimum`: 3 A behind an unnamed 6 A TWC: no wake | n/a (new floor) | passes |
| 7 | `test_a_car_on_a_gen2_echoing_0_is_woken_and_started_for_a_raise`: Gen2 at 03, max 0, offer 0 | fails: no calls | wake, setChargeLimit, wake, startCharging |
| 8 | `test_a_woken_car_that_refuses_the_start_is_not_woken_again` | fails: no start ever | one startCharging; no more wakes over the next hour |

## Existing tests changed

- **The `setup()` fixture now gives the policy 32 A.**
  - Base ran every reconciler test at the class default of 0 A. Those tests relied on "no `offered` entry means no refusal".
  - Under the new design, 0 A means "no room", and about 70 wake tests failed.
- **Parity's `gen2()` pins 0 A.** Its scenarios were written with no policy power and stay on base's footing. Two tests that set power before calling `gen2()` now set it after.
- **`test_gen2_steady_00_...`** gives 32 A just before its explicit `startCarsCharging`. In production a gate start comes only with power on offer.
- **The withdrawal's `offered` test is deleted.** The feature it tested is gone.
- **Five tests asserted on `master.offered`.** I rewrote them as room checks or dropped the clause.
- **`test_charging_reconciler`:** three stop tests pin 0 A. With power, the distributor would add a setAmps they didn't expect.

## Suite, parity, size

- **Suite, base tip 7f9b426d:** 2466 passed, 1 xfailed, exit 0. That is the 2459 baseline, plus 8 new tests, minus 1 deleted.
- **Suite, rebased tip d053ddc7:** 2472 passed, 1 xfailed, exit 0. origin/main alone gives 2464 passed and 1 xfailed, so the difference is the same +9 −1.
- **Parity paid counts:** no paid expectation changed, and all pass.
- **Parity free-count moves:**
  - **`test_an_unnamed_plug_at_00_starts_only_the_car_plugged_there_as_the_offer_rises`** (renamed from `..._starts_no_candidate_...`). The car plugged in there by elimination is now started by VIN, with no fan-out. That is one extra free BLE wake and one charging-start; the set-amps calls were there before.
  - **`test_restart_steady_00_with_telemetry_plugged_...`** (in test_presence, not parity). With its battery unknown, the car is woken and started once on restart; nothing is restored.
- **Parity no longer covers the new start path with power.** With `gen2()` at 0 A, parity proves that base's scenarios didn't move. The start path with power available is covered only by `test_admission.py` and the two tests above.
- **Lib delta against 1a0b7d67:** +63 −19, **+44 net**.
  - Belief: +45 −5. Of the new lines, about 12 are the moved `whyQuiet` body under a new name, and about 10 are comments.
  - TWCMaster: +18 −14. The start loop and the withdraw skip add about 18; removing `offered` saves 12.

## Concerns

1. **The size is not "a small fraction" of +70.** At +44 net it is about 60%. Most of it is real work:
   - the start path (about 15 lines with its comment), which the brief allowed;
   - the Gen2 withdraw skip (4 lines);
   - splitting `_refusesStart` out of `handsOff`;
   - `wouldCharge` and `admissible` as named entry points.

   Removing `offered` paid back 12 lines.
2. **Unknown battery now means a wake and a start.** A plugged-in car at home, not charging, with unknown battery or limit, gets one start (with its wake) whenever there is room. Examples are a restart, or a car at a Gen2 00. This follows the brief ("unknown counts as would charge"), but base never did it.
   - Fleet-only cost, measured with a scripted Fleet:
     - last night's replay is wake, setChargeLimit, wake, startCharging;
     - an unknown-battery Stopped car is wake, startCharging, once.
   - The start never rides the limit's wake. Its desire appears only once the limit write turns "Complete" into "Stopped", so it costs a second wake.
3. **A user's pause in the app will be undone.** A car-side car the user paused there ("Stopped", limit above battery, room available) is now started. On car-side points that is new; the Gen2 gate already did it.
4. **A start desire is never withdrawn for car-side points.** If room disappears before the start is sent, the start still goes, but without a wake, since `whyQuiet` says "no room".
5. **`chargingPoints()` now runs on the reconciler thread** (through `whyQuiet`), and once per car on the control tick. HTTPControl already calls it off the tick. If it raises, the reconciler's pass for that car fails.
6. **`withdrawOffers` no longer stops wakes.** Its old "a car offered 0 is not woken" protection is gone: while the control pass keeps failing, an admissible car may still be woken.
