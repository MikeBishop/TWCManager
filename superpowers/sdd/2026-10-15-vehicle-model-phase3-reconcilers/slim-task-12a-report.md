# Slim Task 12a report: charging on/off as stateless desired state; legacy start/stop path deleted

**Status:** DONE_WITH_CONCERNS
**Worktree:** `scratchpad/wt-vm3`, branch `vehicle-model/phase3`, BASE `d35a95c` (not pushed)

## Commits

| SHA | Subject |
|---|---|
| `f8b20ce` | Start and stop charging as stateless desired state: decided each cycle, sent once per stamp, disruptive stops last, Gen3 per-unit stops via the car |
| `c563d70` | Delete the legacy start/stop path the reconciler replaces |

## Tests

- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1666 passed, 1 xfailed**, the same count as BASE only by coincidence.
  - Added: 32 tests in `tests/unit/test_charging_reconciler.py`.
  - Removed (their subjects were deleted): 32 tests.
    - `test_teslaapi_charge_vin.py` (the whole file).
    - VehiclePriority: the `_fleetUnloaded` tests (3), which covered `_listUnloaded`, and the `_haCars` tests (4), which covered HA `car_api_charge`.
    - `test_vehicle_command_queue.py`: `TestPriority`, `TestKeying`, `TestCancel`, `test_charge` and the drain-of-stop tests.
    - `test_teslaapi_readonly_gate.py`: start/stop charge, and `car_api_available` skipping the wake loop.
    - `TestNoBaseURLLogLine` (2).
    - `test_an_ended_need_gets_a_fresh_grace_on_the_legacy_path`.
    - `test_legacy_fleet_start_sends_no_limit_first`. It asserted the opposite of what this task restores.
    - VehiclePriority-returns: throttled start, failed Fleet start, pre-wake hold.
    - `test_twcmaster`: the two charge-routing tests.
- Retargeted rather than deleted:
  - VehiclePriority walk, policy, cadence and None-return tests now use `wakeVehicle` and `setChargeRate`.
  - Token, owner-read and read-only tests use `loadVehicleList()` and `slotFor(...)` in place of `car_api_available()`.
  - The BLE all-vehicle key tests use `setChargeRate`.
  - The VCQ drain tests use `setChargeRate`.
  - `TestChargeStartStopCancelRules` now asserts desired state.
  - `test_gen2_idle_minimum`, and `test_gen2twc_provider`'s mode-2 helper line.
- TDD: the new file was red at BASE. Failures included the AttributeError on `clearOverride` with no Policy, no desired state from start/stop, no Gen2 `actualCurrent` observation, and the Gen2 start needing a slave. I did not record the exact count. The tests that passed at BASE pin reconciler behaviour that already existed.

### Paid-count rows

| Requirement | Test(s) |
|---|---|
| A start or stop that fails repeatedly is bounded | `test_a_start_that_keeps_failing_is_bounded` (an hour of heartbeat starts, Fleet UNREACHABLE: ≤4 commands, ≤4 wakes); `test_a_stop_that_keeps_failing_is_bounded` (≤4, never a wake); `test_paid_calls_never_exceed_desired_changes` |
| A repeat stop waits for a newer vehicle reading (user decision) | `test_an_app_start_after_our_stop_is_stopped_again_once_per_newer_reading`; `test_heartbeat_readings_are_not_evidence_for_a_car_with_vehicle_reads` (10 heartbeats past RETRY: one Fleet stop); `test_twc_current_alone_never_restops_a_car_with_vehicle_reads` |
| Restores never wake | Already covered in `test_limit_reconciler.py`: `test_no_wake_to_lower_wake_to_raise_never_for_a_restore` and the hourly restore test above `test_stale_free_failure_gets_the_real_command_over_ble_before_paid` (40 × 300 s, no wake). No new test |
| A free online check before any Fleet wake | `test_fleet_wake_comes_after_a_free_online_check` (real TeslaAPI and requests_mock: `GET vehicles/{vin}` before `wake_up`, one wake, no `vehicle_data` on a sleeping car, held across 5 more passes); the GET-first assertion in `test_fleet_start_sends_the_limit_first` |

### Closures

- **Limit before start (Task 11 M2):**
  - `test_fleet_start_sends_the_limit_first` uses real Fleet requests. POSTs are exactly `[set_charge_limit, charge_start]`, the free check comes first, and there is one `vehicle_data`. It monkeypatches `LIMIT_THEN_START_GAP` to 0 because it runs on the real clock.
  - `test_start_waits_five_seconds_after_a_limit_write_and_wakes` covers the same on the fake clock.
- **C1 (a Fleet-only car can still be stopped):** `test_a_fleet_only_car_is_stopped_once_the_list_loads`.
  - The car is not listed, so there is no candidate and no request.
  - `updateChargeAtHome()` makes one free `GET /vehicles`.
  - The next pass sends one `charge_stop` and no `wake_up`.
  - The token is still refreshed by the 5-minute Tesla tick (TWCManager.py:1039), which also queues `loadVehicleList` while the list is pending.
- **Pre-flight M7:** `test_a_queued_start_is_withdrawn_when_the_offer_drops` uses the threaded cloud queue. A Fleet start waits behind a blocking attempt, the desire is cleared, and no `wake_up`, `charge_start` or `vehicle_data` is sent.
- **Pre-flight H3:** `test_fleet_only_car_with_a_pending_schedule_gets_no_start_or_wake`.
- **Ledger L50:** `test_mode_2_start_after_our_stop_needs_no_slave`.

## What changed (lib)

- **TWCMaster**
  - `startCarsCharging(vin)` and `stopCarsCharging(vin)` call `desired.set(key, CHARGING, True/False, "distributor")` for each `targetsFor(vin, START/STOP_CHARGING)`.
  - In mode 1, start keeps `clearOverride()` and stop keeps `stopTimeout` and `overrideLimit()`. Both are guarded for a missing Policy.
  - Modes 2 and 3 no longer touch the bus here.
  - `cancelStopCarsCharging(vin)` calls `clearIf(key, CHARGING, False)` and `reconciler.cancel(key)` for each target, and returns the number cleared.
  - `VEHICLE_COMMANDS` routing is gone.
- **TWCSlave**
  - The class default is `vehicleKey = None`. Gen2TWC's property overrides it.
  - `receive_slave_heartbeat` calls `observe("actualCurrent", …, "Gen2TWC", seen=False)` only when `registry.get(vehicleKey)` is not None (S1).
  - The protocol-2 decision block runs only when `vehicleKey` is not None, and passes the key to stop, start and cancel.
  - A new branch handles an offer below `minAmpsToOffer()` with the car not drawing: `desired.clearIf(key, CHARGING, True)`. It sits in `send_master_heartbeat`, per the brief.
  - The heartbeat's other `cancelStopCarsCharging` now passes its own key.
  - Every `stopAskingToStartCharging` use is deleted.
- **Gen2TWCProvider.ready(START_CHARGING):** `stopMode() == 2`, `respondToSlaves == 0` and `lastStopProvider == "Gen2TWC"`. The slave is no longer required.
- **Policy:** the `stopAskingToStartCharging` loop is deleted.
- **Deleted**
  - TeslaAPI: `car_api_available`, `car_api_charge`, `findReason`, `_unavailableResult`, `get/updateLastStartOrStopChargeTime` and their attribute, and `CarApiVehicle.stopAskingToStartCharging`.
  - TeslaBLE: `car_api_charge`, `startCharging`, `stopCharging` and `_stopAskingToStartCharging`. `_allVehicleTargets` stays for 12b, per I1.
  - HomeAssistant: `car_api_available`, `car_api_charge`, `_vehiclesFor` and the start/stop timestamp.
  - VehiclePriority: the `car_api_charge`, `startCharging` and `stopCharging` entries, and `_listUnloaded`.
  - VCQ: the `charge` dispatch, the legacy stop priority and the legacy `cancel`.
  - WebIPCControl: the start/stop timestamp debug line.
  - Docs: the HA `car_api_available` sentence.
- **Lib delta:** `git diff --numstat d35a95c -- lib` gives +82/−1059, **net −977** against about −850 expected.
  - The extra −130 is deletions that were not on the brief's list but have no caller after this task: `_unavailableResult` (pre-flight had it in 12b), `_listUnloaded` (its premise, "TeslaAPI's own command methods load the list", is false now), the start/stop-time getter, setter, attribute and WebIPC line, the VehiclePriority start/stop entries, and the VCQ legacy cancel and stop priority.
  - **12b's delete list should drop these items.**

Locks: the heartbeat's only new registry write is `observe`, a leaf-lock dict update on the serial thread, the same as the TWC VIN write. No I/O runs under a lock, and no RS-485 I/O runs off the serial thread: the mode-3 stop is still `stopRequested`, which the heartbeat sends. Every stamp uses `time.time`.

## Concerns

1. **A mode-1 Tesla that is anonymous on a Gen2 TWC (firmware that never answers the VIN query) gets no start or stop at all.**
   - On main, `currentVIN == ""` broadcast `car_api_charge` to every at-home car.
   - Now the heartbeat passes the `anon:` key, and an anonymous car has no START/STOP candidate in mode 1, as `test_present_rule_until_phase_5` pins.
   - This is by plan design, but it is not "as on main" for that install. The Gen3 path has single-candidate correlation; Gen2 has none.
2. **Mode 2 has a new paid start path.**
   - `CLOUD_SUPPRESSED["localStops"]` suppresses only STOP_CHARGING.
   - On main, a mode-2 start was only `respondToSlaves = 1`.
   - Now a car that is not drawing gets a reconciler start: BLE first, then a Fleet wake and `charge_start` after 60 s. That is bounded per desire (≤4 commands), but main spent nothing here.
   - The brief's `test_mode_2_start_after_a_ble_stop_goes_through_ble` shows BLE starts are intended in mode 2. Fleet and HA starts in mode 2 were never ruled on.
3. **The wake-hold reset on a stop is gone.** `car_api_charge(False)` zeroed `firstChargeNeededTime`, `firstWakeAttemptTime` and `delayNextWakeAttempt`. Only the 600 s `_chargeNeedEnded` backstop resets them now. The reconciler-side explicit end, which the TeslaAPI comment says belongs to the reconciler, is not wired. The effect is minor and can only delay a wake.
4. **A diagnostic log line is lost.** The INFO8 "no Tesla API token yet" vs "token type unknown" line lived in `car_api_available`. `storeToken` still logs an ERROR for an unknown type, but "no token yet" now has no line.
5. **A start waits behind a limit that cannot be read.** Seen while building the Fleet test: with a malformed `vehicle_data`, the limit attempt was NOT_SENT ("could not read the current limit"), and the start then waits behind it, because `_limitSpent` does not count that outcome, until the limit's 300 s retry. This comes from Task 10 c4 and is not changed here. Worth a look in 12b or 13.

## Fix round 1

**Commit:** `5a42a6d`. **Suite:** 1675 passed, 1 xfailed.

**Lib delta:**
- This round: +125.
- Task total against `d35a95c`: +244/−1096, **net −852**. The expected figure was about −850.

The round grows because it restores main behaviour: the fan-out, the wake-first path, the keep logic, the token log and the `handsOff` rules. No duplicated code was found.

All new tests are in `test_charging_reconciler.py` under "Fix round 1". Each one failed before its fix. The I4 flap test also fails with only `keep` disabled: it sends 30 `charge_start`.

| Item | Fix | Test |
|---|---|---|
| C1 | `Run.runAttempt` runs the attempt's wake before the read-before-write for a non-local provider. It runs only when the attempt may wake, so restores never do. `wakeOutcome` now refreshes the `is_awake` cache when the car answers "online"; without that, the read after the wake still saw the cached "asleep" and read nothing. Backstop: `AttemptRecord.unread` counts "rules: could not read" outcomes, and `_limitSpent` counts the limit as spent at 2 (RETRY apart). | `test_an_asleep_fleet_car_with_an_unknown_limit_is_woken_then_limited_then_started` (real TeslaAPI and requests_mock: a free GET first, then POSTs `[wake_up, set_charge_limit, charge_start]`, ≤1 `vehicle_data`); `test_a_limit_that_stays_unreadable_stops_holding_the_start` |
| I1 | `Targets.broadcastVehicles` returns every at-home car on TeslaAPI's list (or one never located, as main's `lat == 10000`) plus every BLE-claimed VIN, with no exclusion of other points. `TWCMaster._chargeTargets` replaces an anonymous target with that list for a mode-1 start or stop and for a mode-3 start. Start, stop, `cancelStopCarsCharging` and the new `withdrawStartCharging` (the zero-offer clear, called by TWCSlave) all use it. A named car stays addressed. | `test_an_anonymous_point_fans_out_as_main_did` |
| I2 | `Suppressions` adds the condition `silentStops` in mode 2. `CLOUD_SUPPRESSED["silentStops"] = {START_CHARGING}`. | `test_mode_2_starts_no_paid_provider` (mode 3 still starts through Fleet); the table oracle and the local-outcomes test were updated |
| I3 | `handsOff` skips a stop while `batteryLevel < minChargeLevel`. The dead `minChargeLevel` attributes in TeslaAPI and HA are removed. | `test_a_car_below_min_charge_level_is_not_stopped` |
| I4 | `clearIf` records `clearedValue`. `set(..., keep=True)` brings the same value back on its old record without `newDesire()`. TWCMaster passes `keep` when the record has sent and no newer vehicle reading has arrived since `lastSentAt`. This applies to starts and stops. | `test_offer_flaps_do_not_multiply_paid_starts` (30 flaps an hour: 1 `charge_start`; a newer reading: one more) |
| M1 | The comment now says the wake need ends at the free online check (`_wakeSettled`) and at the 600 s backstop. | n/a |
| M2 | `TeslaAPI.loadList` logs "No usable Tesla API token (reason)" at INFO8, once per change of reason. | `test_load_list_logs_why_no_token_is_usable_once_per_reason` |
| M3 (done, 5 lines) | `Gen2TWC.vehicleKey` falls back to the anonymous session when `currentVIN` is not a registry car, is not pending, and an anonymous session exists. | `test_a_rejected_twc_vin_falls_back_to_the_anonymous_session` |
| M4 / #591 (done, 3 lines) | `handsOff` skips a start while `batteryLevel >= chargeLimit`, both known and non-zero. | `test_a_car_at_its_limit_is_not_started` |

### Concerns (fix round 1)

- **Wake-first can spend a wake for nothing.** A cloud attempt that may wake now wakes before its read. If the read then shows the aspect already satisfied, that wake bought nothing. It is bounded: the wake is still gated by the free online check and the wake hold, and it is the same wake the start would spend.
- **Competing desires from the fan-out, as on main.** It can set a desire on a car that another TWC (with a known VIN) is deciding the other way. Main had the same conflict, and the ruling excludes nothing.

## Fix round 2

**Commit:** `8b22849`. **Suite:** 1678 passed, 1 xfailed.

**Lib delta:**
- This round: +19.
- Task total against `d35a95c`: **net −833**.

| Item | Fix | Test |
|---|---|---|
| N1 | `_startWanted` also requires a start candidate that is not local and declares WAKE. In mode 2 the limit then rides no start that the cloud cannot send. | `test_mode_2_limit_buys_no_wake_for_a_start_the_cloud_cannot_send` uses the real TeslaAPI: an asleep car in mode 2 with a policy limit and a start sends no POST at all. It was red before the fix, with one `wake_up`. |
| N2 | `FleetAPIProvider.stopCharging` runs the free online check first, but only when a command slot is usable; otherwise the "no command token" refusal comes first with no request. When the check knows the car is asleep, it returns `SATISFIED "asleep, not charging"` with no request. That detail is in `NOT_SENT`, so it costs no paid budget and stamps no send gap, and SATISFIED settles it until a newer reading. This matches main's `if not vehicle.ready(): continue`. I could not use the detail "asleep" because it collided with the wake's UNREACHABLE "asleep", which would then no longer be tagged "wake asleep". | `test_the_fan_out_stop_sends_nothing_to_an_asleep_car` (a second listed, at-home, unread car); `test_a_stale_charging_reading_on_a_car_now_asleep_sends_no_stop` (one free check, no `charge_stop`). Both were red before. |
| N3 | `keep` also requires `now - lastSentAt < 60` (main's gate). | `test_offer_flaps_do_not_multiply_paid_starts` is reworked: 30 flaps 22 s apart give at most one start per 60 s (there were 30 without `keep`), a withdrawn start comes back fresh after 61 s, and a start that is still wanted does not repeat. It is red with the age line removed. |
| N4 | Parked, per the ruling. | n/a |

Test support:
- Every direct Fleet `stopCharging` now makes one free GET first, so `test_provider_outcomes_cloud.py` and `test_provider_tables.py` gained an autouse fixture that answers it "online".
- Tests that register their own GET keep it, because requests_mock matches the newest registration first.

### Concerns (fix round 2)

- **The N1 test does not catch a weakened N1 filter.** If the WAKE filter alone is weakened, the N1 test still passes: in mode 2 the start has no candidate at all. Only removing the whole clause shows the difference, and that is what happened at 5a42a6d.
- **Every Fleet stop now costs one free GET first.** It is cached for 120 s. A stop to an awake car therefore makes one extra free request.
