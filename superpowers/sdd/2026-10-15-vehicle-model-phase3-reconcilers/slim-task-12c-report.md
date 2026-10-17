# Slim Task 12c report: restart presence

Branch `vehicle-model/phase3` in `scratchpad/wt-vm3`. BASE bcb4042. Not pushed.

## Commits

- `3ff40e2` Locate a car from its latest free position on every policy pass (reqs 1, 2, 4)
- `14e0b53` A VIN-less Gen2 in a plugged state is an anonymous plug session (req 3)
- `717dbff` Presence tests locate cars by position, not a hand-set atHome (req 5, plus a departure test)
- `4fd7c9d` A car its TWC names is home without relocating it (keeps `vehicleIsDefinitelyHome`'s forced `atHome`; found in self-review)

## What changed

**`CarApiVehicle.locate()`** (`Vehicle/TeslaAPI.py`, next to `update_location`). This helper does no I/O. It recomputes `atHome` from the latest `lat`/`lon` that any source observed (TeslaMate, BLE, an earlier read), using the same geofence, `carapi.is_location_home`. It returns None when the position is unknown (`lat == 10000`) or home is unset. When home is unset it never seeds home, because seeding from a possibly stale TeslaMate fix on every policy pass, with a `saveSettings` queued each time, is unsafe. The seeding path stays in `update_location`.

**`Targets._present(master, vehicle)`** checks, in order:
1. anonymous
2. `twcVin`
3. For a Tesla API car:
   - A known position decides: home means present, away means absent, with no fall-through.
   - With no position, the car is present if we hold a limit on it (`heldLimits.get(vin).held is not None`, main's `wasAtHome`) or if `api.atHome` is already True (set by a home-unset seeding read).
   - Otherwise presence falls through.
4. Home Assistant `at_home`
5. the BLE claim

`_present` never returns False just because `atHome` is unset.

**`broadcastVehicles.reached`** uses the same position check, so a car TeslaMate places at home is reached by the anonymous fan-out without an edge.

`_located` treats a car on a TWC (`twcVin`) as home and never calls `locate()` for it. Otherwise a stale fix would flip the `atHome = True` that `vehicleIsDefinitelyHome` forces, and VehicleEndpoints (the Gen3 layered path) and the at-home counts would drop the car. Pinned by `test_a_car_its_twc_names_stays_at_home_whatever_its_stale_fix_says`, which fails without the guard (`car.atHome` False). One side effect: an on-TWC car whose `atHome` is still False is now reached by the fan-out. Main reached every car.

**Departure without an edge** (req 2). After its present loop, `applyPolicyLimit` sweeps `heldLimits.holding()`. A held car that is not on a TWC and that its free position places away gets `_restore(..., decision=True)`, which is the same path as `onDeparture`. A restore never wakes (`allowWake` returns False for a restore). Repeat passes keep the same desire, because `Desired.set` with an unchanged value is a no-op.

**`onDeparture`** still makes the paid `update_location(0)` read, but only when `api.syncSource == "TeslaAPI"`. While telemetry is live, the free position is current, as in main's telemetry branch of `update_location` (cfd0086 `TeslaAPI.py:2149-2164`).

**Gen2 identity** (req 3, `TWCMaster.num_cars_charging_now`, on the serial heartbeat path). While no power flows (`isCharging == 0`):
- A Gen2 in `PLUGGED_STATES` (01/03/04/05/08/09) with `vehicleKey is None` begins the anonymous plug session.
- State 00 ends a session that is still anonymous.

`Gen2TWC.vehicleKey` then returns `anon:<twcid>`, so the existing fan-out applies with no new fan-out code:
- `_setCarAmps` reaches `_anonCars` for the heartbeat rate and the lift.
- `_chargeTargets` reaches `broadcastVehicles` for a mode-1/3 start or a mode-1 stop.

Charge history (`recordVehicleSessionStart`) and the VIN query still start only when power flows.

## Requirement 3: comparison with main for status 00 and 03

Main (`git show main:lib/TWCManager/TWCSlave.py`):
- **Rate raise** (`:902-910`): `setChargeRate(wiringMaxAmps, getLastVehicle())` runs whenever `vehicleRateRaised` is False, with **no state check at all**. After a restart `getLastVehicle()` is None, so the raise goes to every car. The API-control rate (`:886-892`) works the same way.
- **Start** (`:566-572`): `startCarsCharging(currentVIN="")` is sent to every car whenever the offer is at least `minAmpsPerTWC`, amps are below 1 and the state is not 02.
- **Wake**: main's TeslaBLE `setChargeRate` and `startCharging` wake first (`TeslaBLE.py:577-579, 610-612, 775-777`).

So main treated 00 and 03 alike, and an empty TWC as well.

This branch:
- **03** (and the other plugged states) matches main. The point is an anonymous session, and the lift, rate and start reach the BLE car within the existing caps (`_anonCars`: positively plugged-in cars, else `vehicles[0]`; the start goes to at-home cars plus BLE VINs).
- **The BLE command can wake the car.** The reconciler gives an AMPS attempt a wake when the provider is local (`Reconciler.plan`: `wake=(allowWake(...)) and (p.local or aspect != AMPS)`). The test shows `("wake", VIN), ("setAmps", VIN, 32)`.
- **00** deliberately differs from main: no session begins and no fan-out happens. 00 is ambiguous: it means "asleep and plugged in", but an empty TWC reports it too. Fanning a start out from an empty TWC would wake every at-home car.
- The limit still reaches a sleeping car at 00 through req 1. Presence comes from the position or the held limit, and BLE `setChargeLimit` 70 > 50 is a raise, so it wakes. Once the car is awake the TWC moves to 03/04/08 and the session begins. The live box was at 03 (03 → 08 → 09), so 03 is the case that failed.
- The TWCSlave comment "with no vehicle key, nothing (never every car)" (from f8b20ce) still holds: a plugged point now has an anonymous key, not None.

## Tests

New tests, in `tests/unit/test_limit_wiring.py`:

| Test | Covers |
|---|---|
| `test_a_restart_with_the_car_plugged_in_and_asleep_still_gets_the_policy_limit` | req 4, the write-up's test |
| `test_a_held_car_with_no_known_position_is_present` | variants (a) and (c) |
| `test_a_held_car_a_free_position_places_away_gets_its_normal_limit_back` | variant (b) |
| `test_a_vinless_gen2_after_a_restart_is_an_anonymous_plug_session` | variant (d), req 3 |
| `test_live_telemetry_places_a_departing_car_for_free` | `onDeparture` with telemetry live |
| `test_a_car_its_twc_names_stays_at_home_whatever_its_stale_fix_says` | the on-TWC guard |

Setup for the main test (helper `restarted()`):
- commandPolicy `ble_only`
- a real `TeslaAPI` with Owner and Fleet tokens, its providers registered, and the car listed
- a BLE claim
- `heldLimits {VIN: (100, 50)}`
- TeslaMate `lat`/`lon` at home, `chargeLimit` 50, `chargingState` "Complete", `batteryLevel` 51
- a catch-all `requests_mock`, so any HTTP request is counted
- `atHome` is never set

### Red at BASE

The new and converted test files were run against BASE's lib in a temporary worktree, which was then removed:

```
test_limit_wiring.py:202 test_live_telemetry_places_a_departing_car_for_free
E   AttributeError: 'NoneType' object has no attribute 'restore'
test_limit_wiring.py:252 test_a_restart_with_the_car_plugged_in_and_asleep_still_gets_the_policy_limit
E   AttributeError: 'NoneType' object has no attribute 'value'        (no CHARGE_LIMIT desire: the live failure)
test_limit_wiring.py:261 test_a_held_car_with_no_known_position_is_present
E   AssertionError: assert (('setChargeLimit', '5YJ3E1EA1KF000001', 70) in [])
test_limit_wiring.py:270 test_a_held_car_a_free_position_places_away_gets_its_normal_limit_back
E   AttributeError: 'NoneType' object has no attribute 'restore'
test_limit_wiring.py:279 test_a_vinless_gen2_after_a_restart_is_an_anonymous_plug_session
E   AssertionError: assert (None == 'anon:8244')
```

At BASE, 5 of the converted tests also fail, because BASE cannot derive presence from position:
- `test_an_anonymous_point_fans_out_as_main_did`
- `test_the_fan_out_stop_sends_nothing_to_an_asleep_car`
- the three `anonTwc` amps tests

In total, BASE gives 10 failed and 93 passed across the three files.

Before the `syncSource` gate was in place, the telemetry departure test failed because the paid read went out and placed the car at home. It also failed with the gate reverted.

### Paid counts (Fleet/Owner)

| Test | Requests |
|---|---|
| Restart limit 70 (BLE: wake, then `setChargeLimit` 70; `HeldLimit(100, 70)`) | 0 HTTP requests of any kind: 0 vehicle_data, 0 wake, 0 command |
| No position + held (BLE `setChargeLimit` 70) | 0 HTTP |
| Free position away (restore 100; BLE `[setChargeLimit 100]`, no wake) | 0 HTTP |
| Gen2 anonymous session (BLE: wake, limit 70, wake, setAmps 32; start satisfied by "Complete") | 0 HTTP |
| Telemetry live, departure (restore desired) | 0 HTTP |
| Unchanged: `fleetCarOffItsPoint` departure (no telemetry) | `["vehicle_data", "set_charge_limit"]` / `["vehicle_data"]`, as at BASE |

### Suite

`tests --ignore=tests/API --ignore=tests/integration`: **1723 passed, 1 xfailed**. That is BASE's 1717 plus the 6 new tests.

## Lib delta

`git diff --shortstat bcb4042..HEAD -- lib`: 3 files changed, 56 insertions(+), 11 deletions(-), so **+45 net**.

| File | Lines |
|---|---|
| Targets.py | +37/-9 |
| TWCMaster.py | +11 |
| TeslaAPI.py | +8 |

The geofence is reused: `is_location_home` is not duplicated.

## Deleted and weakened tests

No test was deleted.

| Test | Change | Why it is not weaker |
|---|---|---|
| `test_charging_reconciler::test_heartbeat_with_no_vehicle_key_decides_nothing` | Its heartbeat now drives state **00** instead of the helper's default 04. | Req 3 intentionally reverses the 04 case ("never a broadcast start" for a plugged, VIN-less point). The reversed behaviour is pinned by `test_a_vinless_gen2_after_a_restart_is_an_anonymous_plug_session`. The 00 case keeps the original assertion: no key, and no broadcast start or cancel. |
| `test_limit_wiring::cars()` (used by `test_present_rule_until_phase_5`, `test_policy_limit_sets_desired...`, `test_departure_restores_a_held_limit_for_an_absent_car_once`) | VIN2's `SimpleNamespace(atHome=False, update_location=lambda: True)` is now a real listed `CarApiVehicle` that TeslaMate's position places away. | Same assertions. |
| `test_limit_wiring::fleetCarOffItsPoint` | `Mock`ed `is_location_home`/`is_far_from_home` and `car.atHome = True` are removed. Home is set, and the paid read returns a home or away lat/lon that the real geofence judges. | Same assertions and paid counts. |
| `test_charging_reconciler::fanOutCars`, `fleetOnTwc(listed=True)`, and the VIN2 car in `test_the_fan_out_stop_sends_nothing_to_an_asleep_car` / `test_a_fleet_command_for_one_car_sends_nothing_for_another_listed_car` | `atHome = True` and fakes are replaced by `placeAt(m, vehicle, HOME/AWAY)` on real listed cars. | Same assertions. |
| `test_amps_reconciler::anonTwc` | The four `SimpleNamespace(atHome=True, lat=1.0)` cars are now real listed cars placed at home. | Same assertions. |

Some hand-set `atHome` remains in tests that are not about `Targets` presence:
- `teslatokens.add_home_vehicle`, used by TeslaAPI request, token and readonly tests for `ready()`.
- The `SimpleNamespace(atHome=...)` fakes in `test_vehicle_endpoint`, `test_charging_points` and `test_gen2_idle_minimum`, which feed `VehicleEndpoints`/Gen3, whose lib reads `atHome` directly.

## Concerns

1. **Free position age is not gated.** Presence and the departure sweep trust the latest position from any source, at any age. Main trusted only a live telemetry position and otherwise paid for a read.
   - A stale "home" makes a held car present, which matches main's `wasAtHome`.
   - A stale "away" restores the normal limit, never with a wake.
   - Only `onDeparture`'s paid read is gated on live telemetry.
2. **`locate()` now writes `atHome`**, so `updateChargeAtHome` (the checkCharge tick) refreshes a car TeslaMate places at home after a restart. That is main's behaviour, but new against BASE. It can cost a vehicle_data ($0.002) only when the car is awake, TeslaMate's battery reading is older than 300 s, and BLE fails to read. Presence itself makes no request.
3. **A new session after an anonymous charge.** After an anonymous (never-VIN'd) charge ends with the car still plugged in (03), a new anonymous session begins at once. Its once-per-session lift can send one BLE `setAmps`, with a wake, unless `chargeCurrentRequest` already shows at least `wiringMaxAmps`.
4. **Sessions can begin and end off the serial thread.** `num_cars_charging_now` also runs from `getStatus` (the HTTP status path), so the state-begun session can begin or end there as well. This is the same as the existing amps-flow `_plugSession`: registry dict work only, no RS-485 I/O.
5. **`onDeparture` follows main's gate, not the brief's literal wording.** It reads only when `syncSource == "TeslaAPI"`. If telemetry is live but has not yet sent a position, nothing is read and nothing is restored, although the brief's literal wording would read. Live telemetry reports position whenever the car moves, so this case should be rare.
6. **`locate()` never seeds home.** A fresh box with only TeslaMate and BLE, and no home set, relies on the held limit or the BLE claim for presence until a paid read seeds home. Main's telemetry branch would have seeded it.
7. **`Targets._located` uses `getattr(api, "locate", ...)`** to tolerate attachments without `locate`: the remaining test fakes, and VehicleEndpoint/Gen3 fakes.

## Fix round 1

Commit `6c75533`, one commit so that every commit bisects; the round's parts share `Targets.located`.

### Changes

| Item | Change |
|---|---|
| I2 | At 00, a Gen2 begins an anonymous session only when `TWCSlave.pluggedCars()` is non-empty. That set is `_anonCars`' existing plugged-in set: an unnamed car the fan-out reaches whose latest free vehicle-source `chargingState` is plugged (HA only "Charging"). It now also skips a car its position places away. 00 with no such car ends the session. |
| One sweep | `onDeparture` and the policy pass share `_restoreDeparted(master, read)`. A held car that is no longer `_present` gets its normal limit back. Only the edge (`read=True`) pays for the location read, and only when telemetry is not live (M4: gate unchanged). The policy sweep now also restores a held HA car that HA says is not at home. That is `onDeparture`'s existing rule. |
| Age guard | A position no newer than `vehicle.lastWrite("chargeLimit")` cannot show a departure. |
| Fakes | `locate()` is called directly, and the `getattr` is gone. `locate=lambda: None` is added to the fakes in `test_vehicle_endpoint`, `test_charging_points` and `test_gen2_idle_minimum`. The last one now reaches `located()` through the 00 heartbeat. |
| Minor | `_present`'s held check is `vin in heldLimits.holding()`. `_located` is renamed `located`, because `TWCSlave` uses it. |

### Tests

**Red before the fix**, at 4fd7c9d with the new tests:

```
test_an_away_fix_older_than_our_last_limit_write_is_no_departure
E   AssertionError: assert Desired(value=100, by='restore', ...) is None
test_at_00_a_plugged_car_a_free_source_shows_at_home_begins_the_session
E   AssertionError: assert (None == 'anon:8244')
```

**Mutation checks.** Each mutation was applied to the fixed code, and in every case the test failed:

| Test | Mutation |
|---|---|
| `test_a_held_car_with_no_position_or_ble_is_present_for_a_cloud_provider` (I1: prefer_ble, Fleet the only candidate, no position, no BLE claim; 0 HTTP) | held clause dropped |
| `test_a_restart_…` (M2: now asserts on the first `setPolicyLimit(70)`) | `_present` reverted to `bool(api.atHome)` |
| `test_an_empty_twc_at_00_begins_no_session` (at home and "Disconnected"; away and "Complete") | 00 begins unconditionally |
| `test_an_empty_twc_at_00_begins_no_session` | the away filter in `pluggedCars` removed |
| `test_at_00_a_plugged_car_a_free_source_shows_at_home_begins_the_session` | the 00 begin removed |
| `test_an_away_fix_older_than_our_last_limit_write_is_no_departure` | the age guard removed |

`test_an_empty_twc_at_00_begins_no_session` passed before the fix because BASE never begins a session at 00. It guards the new rule.

**Changed test.** In `test_a_vinless_gen2_…`, TeslaMate now reports "Disconnected" before the 00 heartbeat, so the session ends. With "Complete" still reported, 00 keeps the session by design (I2).

**Paid counts.** Every new test asserts 0 HTTP requests, except the empty-TWC test, which makes no requests and sets no desire.

### Suite and lib delta

The suite gives 1727 passed and 1 xfailed.

| Range | Insertions | Deletions | Net |
|---|---|---|---|
| This round | 41 | 26 | +15 |
| 12c total, from BASE bcb4042 | 78 | 18 | **+60** |

This round by file:

| File | Lines |
|---|---|
| Targets.py | +21/-20 |
| TWCSlave.py | +12/-4 |
| TWCMaster.py | +6/-4 |

### Still open

- With two VIN-less Gen2s, one at 03 and one at 00, a single plugged-in car evidenced by TeslaMate can make both points anonymous. Both then fan out to that car, because `named` holds only the anonymous keys. The caps per desire still bound it.
- No-home-set behaviour: the Task 13 docs, per the ruling.

## Row-26 fix

Commit `fc6eba7` (on bef82f0). After a restart with the car plugged in and asleep, Phase 3 raised the limit 50 → 70 over BLE but never sent a start. Main's BLE start followed the limit write (parity row 26). Row 26 now matches main.

### Changes

**`Belief.uncompleted(vehicle, obs)`** decides when a "Complete" reading still counts. It reads as "Stopped" when both of these hold:
- the reading is no newer than our last chargeLimit write;
- the battery level is below that write.

`known(CHARGING)` (planning) and `Run.py`'s pre-send check both apply it. A fresh "Complete" read after the raise still satisfies the start.

**`handsOff`'s #591 check** ("battery at its charge limit") now compares the battery with the believed limit: our own write until a newer reading arrives. It used to compare with the latest reading, which was TeslaMate's stale 50. Without this change the start stayed blocked even after the "Complete" fix.

**Caps are unchanged:**
- no paid start in mode 2 (row 27 is still green);
- once per desire;
- no wake for a stop. A stop is satisfied by "Stopped" just as it was by "Complete".

### Tests

| Test | What it checks | Result before the fix |
|---|---|---|
| `test_a_restart_…` (extended: a VIN-less Gen2 heartbeat at 03 and passes past the limit-then-start gap) | Exactly one BLE `startCharging`, preceded by its wake and after `setChargeLimit` 70; 0 HTTP | Failed: `[] == [('startCharging', …)]` |
| `test_a_complete_read_after_the_raise_still_satisfies_the_start` (new) | A TeslaMate "Complete" observed after the write still satisfies the start: no `startCharging`, 0 HTTP | — |
| Parity row 26 (`test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit`) | Now pins wake, limit 70, wake, amps 32, wake, `charging-start`; 0 HTTP | Pinned the old count, so it was updated |

Mutation checks:

| Mutation | Tests that fail |
|---|---|
| `uncompleted` never rewrites | restart, parity row 26 |
| The age check is dropped | the fresh-Complete test |

### Suite and lib delta

The suite gives 1764 passed and 1 xfailed (BASE 1763 + 1 new test).

| Range | Insertions | Deletions | Net |
|---|---|---|---|
| This fix | 19 | 1 | **+18** |

| File | Lines |
|---|---|
| Belief.py | +16/-1 |
| Run.py | +3 |
