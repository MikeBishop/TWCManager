# Slim Task 12b report: amps as stateless desired state; the legacy rate path goes

**Status:** DONE_WITH_CONCERNS
**Worktree:** scratchpad/wt-vm3, branch vehicle-model/phase3, BASE 8b22849 (not pushed)

## Commits
- 11f9222 Observe the car's own charge-current request (`chargeCurrentRequest`), never the charger's pilot
- d2022a3 Amps as stateless desired state with layered actuators: the point owns the car's rate, the TWC holds its floor below range, the lift is one-shot
- 7deb924 Delete the legacy rate path: setChargeRate, VehiclePriority, the legacy queue mode and dispatch
- d960e0c An anonymous TWC's heartbeat rate reaches the cars main's broadcast did
- 9d3fb64 Drop the debug page's module stats table: the facade that counted them is gone

## Tests
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1610 passed, 1 xfailed**. BASE was 1678 passed.
- The count fell because legacy tests were deleted: 99 test functions removed and 35 added or moved (some parametrised).
  - Deleted with the code: `test_vehicle_priority.py`, `test_vehicle_priority_returns.py`, `test_vehicle_command_queue.py`, `test_teslaapi_chargerate.py`, `test_own_write_stamps.py`; the dispatch tests in `test_provider_order.py` and `test_provider_outcomes_local.py`; `TestVehicleCommandRouting` (most of it), the BLE all-vehicle tests, the legacy-wake tests, and `TestRefusalLogging` / `TestVehiclePrioritySkipsReadOnly`.
  - Moved first:
    - per-provider rate stamps on `chargeCurrentRequest`, success only, and no revival of a forgotten car → `test_reconciler_queues.py`;
    - the VCQ generic cases (put never blocks while the worker runs, a raising run spares the worker, an idle drain returns at once) → `test_reconciler_queues.py`;
    - the read-only gate → the Fleet provider (`REFUSED "no command token"`, no HTTP call, no API error) in `test_teslaapi_readonly_gate.py`;
    - checkCharge refreshes each module once and api_only keeps BLE out → `test_teslaapi_readonly_gate.py`;
    - token-slot and classification command cases → `api.command` / `api.wakeOutcome`.
- `tests/unit/test_amps_reconciler.py` (18 tests) holds every test the brief lists, plus:
  - carriers;
  - the mode-3 floor at 6 A when the TWC minimum is 5;
  - a zero offer withdraws the car's rate but not a lift;
  - a session end resets the lift;
  - the anonymous-TWC fan-out (paid counted).
- Paid-counted tests:
  - fluctuating offer: one hour, ≤ 240 `setAmps` and no wake;
  - an unchanged rate is never resent: 120 cycles, 1 send;
  - a failed paid rate gets 1 send plus 1 blind retry, then nothing until a new value;
  - the Fleet lift goes out once;
  - anonymous fan-out: ≤ 240 per hour to the one at-home car, none to an away car or to a car a TWC names.
- Carried N1 test from the 12a re-review: `test_a_start_that_spends_no_cloud_wake_buys_none_for_the_limit[local BLE | non-local without WAKE]` in `test_charging_reconciler.py`. Mutation-checked:
  - dropping `not p.local` fails the BLE case;
  - dropping `declares(WAKE)` fails the HomeAssistant-like case.
- Updated:
  - `test_charging_points.py`: the `ep()` local mock does not layer. Mode 2 on a named TWC now has the car carry the rate. The Gen3 point is parametrised over modes 1, 2 and 3: the unit carries every time and the car gets no rate.
  - `test_vehicle_endpoint.py`: sets desired amps.
  - `test_twcslave.py`: desired, not queued.
  - `test_charging_reconciler.py::test_an_offer_starts...`: the mode-1 heartbeat now also lifts, as main's raise did.

## Lib delta
**−820** non-test `lib/**/*.py` lines: 28,892 → 28,072; 202 insertions, 1,031 deletions. The expected figure was about −800. `Reconciler.py` is at 599 lines (limit 600).

## What changed
- **Field.**
  - `chargeCurrentRequest` added to `FIELDS` and `CHARGE_FIELDS`.
  - TeslaAPI `update_vehicle_data` observes `charge_current_request` (a `RegistryField`).
  - BLE `get_charge_state` maps `chargeCurrentRequest`.
  - Fleet Telemetry's `ChargeCurrentRequest` was mapped onto `availableCurrent`; it now maps onto `chargeCurrentRequest`. `availableCurrent` stays the pilot, which `vehicleMaxAmps` uses.
- **ChargingPoint.**
  - `carriers()` maps modes 1/2/3 to `(T,F)`, `(F,T)` and `(T,T)`.
  - Layering applies only when the local member is a Gen2 TWC (`hasattr(local, "pointOwnsAmps")`) and the point has a non-read-only car. It sets `pointOwnsAmps = bool(cars)` on every pass.
  - Mode 1: the TWC carries the rate. The lift is `desired.set(key, AMPS, wiringMaxAmps, "lift", lift=True)` while `local.vehicleRateRaised` is False, and the flag is then set.
  - Mode 2: the TWC gets `maxPower` and the car gets the distributor's amps.
  - Mode 3 in range: the TWC carries. It lifts only when the car's `known(AMPS)` is known and below the offer.
  - Mode 3 below `layerFloorAmps()`: the TWC is held at that floor and the car carries.
  - `watts == 0`: the TWC gets 0, and the car's non-lift amps desire is withdrawn.
- **Gen2TWC.**
  - `pointOwnsAmps = False`.
  - `layerFloorAmps() = max(6, minAmpsToOffer())`, which `Gen2TWCProvider.ampsRange` now uses too, so it has one definition. Holding at the floor (6), not `minPower`, keeps the heartbeat's literal `< 6` handoff from flipping the wire to `wiringMaxAmps` when the TWC minimum is 5.
- **VehicleEndpoint.**
  - `setTargetPower` writes `desired.set(key, AMPS, max(1, amps), "distributor")`; 0 clears a non-lift desire.
  - `requestedAmps()` returns `known(vehicle, AMPS)`.
  - `REFRESH_SECONDS`, `_lastAmps`, `_lastQueuedAt` and `clock` are gone.
- **TWCSlave.**
  - `_queueChargeRate` and `_requestVehicleRateRaise` write desired state through `_setCarAmps`, unless `pointOwnsAmps` is set or there is no key.
  - `vehicleRateRaised` is a plain attribute. It is set when the lift desire is written, reset by `_resetVehicleRateRaised` in the mode 2/3 handoff and, new, at session end in `TWCMaster.num_cars_charging_now`.
  - Deleted: the `__lastAPIAmps*` counters and the repeat block, `_vehicleRateRaiseGen`, and the 60 s raise-attempt window.
  - An anonymous key fans out to `broadcastVehicles(SET_AMPS)`, minus cars a TWC names (see concerns).
- **Reconciler.** A lift is cleared once it has settled or is satisfied. That check now runs before the send gap, so the one-shot clears on the next pass, not 15 s later. `MIN_SEND_GAP[AMPS] = 15` already paced rates.
- **Deleted.**
  - `setChargeRate` in TeslaAPI, with `_chargeRateAccepted`, `_recordChargeRate`, `CHARGE_RATE_RESEND_AFTER` and `lastChargeRateSent*`.
  - `setChargeRate` in TeslaBLE, with `_stampWrite` and `_allVehicleTargets` (pre-flight I1).
  - `setChargeRate` in HomeAssistant, with `_call_service` and `_is_vehicle_connected`, which only it used.
  - `TeslaAPI.wakeVehicle`, `refuseCommandIfReadOnly` and `refusalLoggedAt`, which only the deleted paths called.
  - `VehiclePriority.py` and its module-list entry.
  - The VCQ legacy mode: `resolve_module`, `_DISPATCH`, `_setAmps`, `_key`, `_execute`, the per-put callback and `drain_high_priority`. Its constructor now takes keyword arguments only.
  - In TWCMaster: `vehicleCommandQueue`, `queue_vehicle_command`, `_resolveVehicleCommandModule`, `calculateModulePriority`, `getModuleByPriority`, the `"priority"` key and `stats`. The `stats` table on the debug page went with it.
  - In TWCManager.py: `get_vehicle_module`, the VehiclePriority lookup, and the legacy queue's start and drain.
  - `ProviderOrder.dispatch`, `_count` and `_succeeded`; `Provider.attempts()` and HomeAssistant's override.
  - Already gone at BASE: `VEHICLE_COMMANDS`, `cancel(cmd, match)`, `_unavailableResult`, `_vehiclesFor`.
- **checkCharge / checkArrival.**
  - `master.updateChargeAtHome()` calls each vehicle module's `updateChargeAtHome()` once, for modules with a provider that is neither suppressed for `READ_CHARGE` nor unavailable. TeslaAPI's call still loads the vehicle list first (C1).
  - `TeslaAPI.updateChargeAtHome` no longer returns a walk-stopping bool.

## Rules check
- **Fleet pricing.** Amps never wake through a billed provider, and there is no read before a rate (`maxAge None`).
- **No new paid path.**
  - The checkCharge change only adds HomeAssistant's free REST reads.
  - The fan-out restores BASE and main behaviour. Each path that adds paid calls has a paid-count test.
- **Locks.**
  - ChargingPoint and TWCSlave do store and registry dict work on the serial thread, with no I/O.
  - `master.updateChargeAtHome` runs on the background thread with no lock held.
  - Only `time.time` is used.

## Concerns
1. **Gen3 never layers.** A Gen3 point keeps BASE behaviour in every mode: the unit carries the whole target, with no lift and no car rate. Pinned by the parametrised Gen3 test. A mode-2 target of maximum on one unit would raise the one shared fake-Neurio headroom, and its siblings would overshoot. Main's MergedEVSE did send mode 2 to the car on a Gen3 point. The coordinator may rule the other way.
2. **Anonymous fan-out sends to more cars than main.** A VIN-less Gen2 in mode 2/3 rates every at-home car on the TeslaAPI list plus every BLE-keyed VIN, except cars a TWC names. Main's Fleet path rated `vehicles[0]` only, so a multi-car Fleet-only household with a VIN-less TWC pays N times. A `None` key still sets nothing; main would have rated `vehicles[0]` even with nothing plugged in. Without the fan-out, the TWC would sit at `wiringMaxAmps` with the car uncapped: a sustained overshoot, and a regression from BASE.
3. **`vehicleRateRaised` resets at session end, not at a literal unplug.** Session end means under 1 A for 5 s. A re-lift costs at most one command per session, and only when a newer reading shows the car below `wiringMaxAmps`; otherwise our own write stamp satisfies it. Main reset it only at the mode-2/3 handoff, so it lifted once per process.
4. **checkCharge now also reaches HomeAssistant.** `updateChargeAtHome` runs for HA even when TeslaAPI has cars. These are free REST reads; the façade's walk used to stop at TeslaAPI's truthy return.
5. **The read-only INFO hint is gone.** "Tesla API is read-only… commands need a Fleet API token" went with `refuseCommandIfReadOnly`. Refusals now surface only through the reconciler's report, at DEBUG. If the user wants the hint back, Task 13 can restore it once per change.
6. **A heartbeat desire lingers.** A TWC-only point's mode-2/3 heartbeat desire is not withdrawn when the offer drops below the minimum; a ChargingPoint's is. It is harmless once satisfied. If it is unsatisfied, a free BLE path retries every 60 s while the car is plugged in.
7. **Reconciler.py is at 599 of 600 lines** after moving the lift clear.
8. **Task 13 leftovers.** The VehiclePriority mention in CHANGELOG is historical. The docs and changelog updates for this task belong to Task 13.

## Fix round 1

**Commits:**
- 3ba16dc Move the belief helpers and per-aspect rules out of Reconciler.py into Belief.py (M1)
- b5021d3 Lift once per range entry in mode 3 too, and withdraw a floor rate when the TWC carries again (I1, M4)
- fb39c73 A VIN-less Gen2's rate and lift go to the plugged-in cars, else vehicles[0]; the heartbeat withdraws its rate (I2, M2)
- d2c0783 Restore the INFO read-only hint, once per Fleet slot change (I3)
- 55f4b77 An unaddressed start or stop also reaches Home Assistant cars at home and on a TWC, as main's did (audit row 61)
- 827302f The vehicle command queues log no exception text at any level (R9)
- 889e510 Pin the deleted tests' GAPs and PARTIALs, Fleet-then-HA, and drop dead legacy stubs (M5, M6, M8, all remaining rows)

**Suite:** 1657 passed, 1 xfailed.

**Lib delta:**
- This round: +78 lines, 28,072 → 28,150.
- Task total: −742 against BASE 8b22849.
- `Reconciler.py` is at 515 lines; the new `Belief.py` has 100.

### Code fixes
- **I1.**
  - The mode-3 lift now uses `vehicleRateRaised`, as mode 1 does. The flag is set when a lift is written.
  - ChargingPoint's below-floor branch calls `_resetVehicleRateRaised()`, so the next return to range may lift again.
  - The optional "gate mode 1 on `k < amps`" was **not** done. It would break the brief's mode-1 lift for a car whose request is above a low offer (`test_mode_1_…` lifts a car at 16 A when the offer is 10 A).
- **M4.** On the TWC-carries path each car member gets `setTargetPower(0)`, which withdraws a non-lift rate.
- **I2.**
  - `TWCSlave._anonCars()` follows the reviewer's shape:
    - candidates: `broadcastVehicles(SET_AMPS)` minus cars a TWC names;
    - keep those whose latest vehicle-source `chargingState` is neither None nor "Disconnected";
    - if none qualify, use the first registry car with a TeslaAPI attachment. Registry order is TeslaAPI list order, which is `vehicles[0]`. `getCarApiVehicles` stays private to TeslaAPI, as `test_registry_callers` requires.
  - The heartbeat rate and the lift both go through `_setCarAmps`.
  - Keys that leave the set lose the heartbeat's rate (`_ampsKeys`).
- **M2.** In mode 2/3, when the offer drops below the minimum, the heartbeat withdraws its own rate (`by == "heartbeat"`). Lifts and distributor rates are untouched.
- **I3.**
  - `TeslaAPI.noteReadOnly()` logs the INFO hint once per `fleetSlot.changes`. It makes no HTTP call and records no API error.
  - `FleetAPIProvider.available()` calls it for a command capability when there is no command token.
- **Row 61.**
  - `broadcastVehicles` also reaches HA cars with `at_home` set that a TWC reports by VIN (`getTWCbyVIN`). This is main's `car_api_charge` with its `_is_vehicle_connected` check.
  - On main, an HA car on no TWC (or on an anonymous TWC) was skipped. That is pinned explicitly; the audit's wording ("every at-home HA car") is broader than main.
- **R9.**
  - VehicleCommandQueue logs failures by type name with a traceback of locations only: file, line and function, with no message and no source text.
  - A dying worker is logged and not re-raised, so the thread excepthook cannot print the exception text.
- **M5.** The dead `stats`, `queue_vehicle_command` and `VehiclePriority` stubs are gone from the tests.
- **M3 and M7.** Recorded, no code change:
  - M3, Task 14 row: mode 2 with an undeliverable rate behaves as on main; it is not safer.
  - M7: the lift resets at session end because Gen2 has no unplug event.
- **M8.** The design is kept and pinned:
  - Fleet and HA share one paid budget per desire.
  - HA is reached only when Fleet is unavailable, or for the next desire after Fleet REFUSED.

### Deleted-test GAP and PARTIAL rows → new tests

| Source | Row | New test |
|---|---|---|
| 12b GAP 1 | test_post_has_timeout | `test_provider_outcomes_cloud::test_paid_posts_time_out_after_ten_seconds` |
| 12b GAP 2 | TestRefusalLogging::test_logged_once_per_state_change | `test_teslaapi_readonly_gate::TestRefusalHint::test_logged_once_per_state_change` |
| 12b GAP 3 | TestRefusalLogging::test_resync_of_owner_token_does_not_log_again | `TestRefusalHint::test_resync_of_owner_token_does_not_log_again` |
| 12b GAP 4, 5 | TestWakeNeverSent / TestWake::test_request_never_sent | `test_provider_outcomes_cloud::test_a_wake_or_command_that_never_left_is_an_error_and_refreshes_nothing[wake_up, command]` |
| 12b GAP 6 | test_disabled_home_assistant_gets_no_broadcast | `test_charging_reconciler::test_disabled_home_assistant_gets_no_broadcast` (no broadcast, no send, no candidate, no charge refresh) |
| 12b GAP 7 | test_update_charge_at_home_reaches_ha_… | `test_teslaapi_readonly_gate::TestCheckChargeRefreshesEachModuleOnce::test_home_assistant_refreshes_once_alongside_teslaapi` |
| 12b PARTIAL 1 | test_garbage_rate_is_rejected | `test_provider_order::test_debug_command_refuses_an_infinite_rate` (adds "lots", null, NaN) |
| 12b PARTIAL 2, 3 | low rate resend fails / rejected | `test_provider_outcomes_cloud::test_a_low_rate_is_done_only_when_both_sends_land` |
| 12b PARTIAL 4 | TestTeslaAPIRefusesCommands::test_set_charge_rate | `TestFleetProviderRefusesCommands::test_no_command_token_sends_nothing` (adds `lastAPIAccessTime` unchanged) |
| 12b PARTIAL 5 | test_wake_401_refreshes_a_fleet_token_at_fleet_auth | `test_provider_outcomes_cloud::test_an_expired_token_on_wake_is_refreshed_at_fleet_auth_once` |
| 12b PARTIAL 6 | test_unproven_and_pairing_keys_are_still_commanded | `test_teslable_pairing_status::test_pairing_and_pairing_failed_keys_are_claimed_and_commandable` |
| 12b PARTIAL 7 | test_ha_after_a_fleet_failure_is_held_to_fleets_cadence | `test_amps_reconciler::test_home_assistant_after_a_failed_fleet_rate_spends_from_the_same_paid_budget[500, 403]` |
| 12b PARTIAL 8 | test_the_hold_is_per_car_and_per_command | `test_amps_reconciler::test_the_paid_budget_is_per_car`, plus the per-aspect Fleet/HA tests below |
| Audit GAP | 61 | `test_charging_reconciler::test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars` |
| Audit PARTIAL | 16 | `test_limit_reconciler::test_a_restore_stamps_the_outside_value` |
| Audit PARTIAL | 28, 29, 31, 32 | `test_charging_reconciler::test_a_fleet_command_for_one_car_sends_nothing_for_another_listed_car` (real requests; a start, a raise and a stop for A; no URL carries B's VIN; B's wake hold unchanged) |
| Audit PARTIAL | 56 | `test_reconciler_queues::test_a_stop_submitted_during_a_live_drain_is_still_sent` |
| Audit PARTIAL | 63, 68, 69, 71 | `test_limit_reconciler::test_fleet_then_ha_never_in_one_pass[limit/start/amps × 500/408/wake held/DONE]` and `test_ha_is_reached_only_once_fleet_has_refused_or_is_unavailable[limit/start/amps]` |
| Audit PARTIAL | 77 | `test_outcome_desired::test_read_and_rules_outcomes_spend_no_send_gap[read, rules: limit unknown, rules: could not read]` |
| Audit PARTIAL | R9 | `test_reconciler_queues::test_a_raising_report_is_logged_by_type_name` (now `"secret-token" not in caplog.text` at DEBUG) and `test_a_worker_that_dies_logs_no_exception_text_at_any_level` |

**Review tests:**
- I1:
  - `test_mode_3_lift_goes_once_per_range_entry_even_when_the_car_clamps_it`: 240 readings in an hour give one lift, then exactly one more after a below-floor pass.
  - `test_user_changed_amps_after_a_lift_are_left_alone[1, 3]`.
- M4: `test_a_floor_rate_is_withdrawn_when_the_twc_carries_again`.
- I2:
  - `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0`: an hour, at most 240 sends, one car only.
  - `test_an_anonymous_mode_1_lift_goes_to_the_plugged_in_car_only`.
  - `test_a_car_that_leaves_the_anonymous_set_loses_the_heartbeat_rate`.
- M2: `test_heartbeat_withdraws_its_rate_when_the_offer_drops_below_the_minimum`.
- M6: `test_failed_paid_rate_waits_for_a_newer_reading_once_per_desire[408 → 4, 500 → 2]`.
  - This pins the design's cap of 4 per desire. A newer live reading re-arms only a send that never reached the car, and then adds a send *and* its blind retry.
  - The reviewer's sketch expected 3, with no 4th.

### Not covered, and concerns
- **M6 numbers.** For an unreached send (408) the re-arm allows 2 more paid sends, a send and its blind retry, for 4 per desire. That is the Task 10 I2 ruling; the reviewer's sketch assumed one. An ERROR 500 that reached the car is never re-armed by a reading.
- **HA start after a Fleet REFUSED wake.** The refused wake spends the desire's one paid send, so HA starts the car only on the next desire. The 403 also makes Fleet unavailable for commands, so every later desire goes straight to HA. This is pinned.
- **Row 61 follows main literally.** The "connected" check requires a TWC to report the car's VIN, so an HA-only install with a VIN-less TWC still sends no unaddressed HA stop, as on main. If the coordinator wants every at-home HA car, it is a one-line change (drop `getTWCbyVIN`), but that goes beyond main.
- **Other DEBUG tracebacks.** `WallConnectorVins.py:152` still logs `exc_info=True` at DEBUG. That is the read path, not the reconciler's report path, so it was left alone; it could go into Task 13's grep.

## Fix round 2

**Commits:**
- 841eadd A VIN-less Gen2 counts a car plugged in only by a positive charging state (N1)
- 464d83c The never-sent wake/command test stores a refresh token, so a refresh would really go out (N2)

**Suite:** 1657 passed, 1 xfailed.

**Lib delta:**
- This round: +11 lines.
- Task total: −731 against BASE 8b22849.

### N1
`TWCSlave._anonCars` counts a car as plugged in only when its latest vehicle-source `chargingState` is in `_PLUGGED` = {Charging, Starting, Stopped, Complete, NoPower}. A Home Assistant reading counts only when it is "Charging". BLE "Unknown" and TeslaMate's "None" do not count.

`test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0` gains two legs:
- **Probe case.** Three unplugged at-home Fleet cars (VIN, VIN2 and VIN4) each have TeslaAPI "Disconnected" and then HA "Stopped". An hour of fluctuating rates goes only to the `vehicles[0]` fallback (VIN), with at most 240 sends. The leg failed before the fix: VIN2 and VIN4 were rated too.
- **Direct `_anonCars()` check.** BLE "Unknown" and TeslaMate "None" are excluded, and HA "Charging" is included.

### N2
`test_a_wake_or_command_that_never_left_is_an_error_and_refreshes_nothing` now calls `api.storeToken(fleet_token(), "refresh-me")`. I made the call in that test, not in the shared `fleet()` fixture, because the fixture's no-refresh-token slot is what the 401 tests rely on.

Mutation check: adding `self.refreshSlot(slot)` to `_paidPost`'s `RequestException` branch now fails both parametrisations. The mutation was reverted.
