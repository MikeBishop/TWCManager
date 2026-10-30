# Task 3 report: one applicability rule per message; BLE ping; holds; hint endpoints gone

Commit **d5cc8711** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent cb7a8f53). Not pushed.

## What I implemented

- **`Presence.applicable(master, v, attempt) -> str`**
  - Returns `SEND`, `NOT_HERE`, `HOLD` or `HOME_NOW`. The values are `"send"`, `"not here"`, `"hold"`, `"home"`; the last two double as the outcome detail.
  - Implements every cell of the table:
    - start/amps vs apply vs restore;
    - missing times are `NEVER`;
    - a leaving/arriving tie holds.
  - **PRESUMED apply cell.** It is collapsed to `SEND if plugged and not driving else HOLD`. This covers the four listed sub-cells. It also gives `HOLD` for the unlisted "presumed with an older outside fix" case, and `SEND` when that car is plugged.
  - **Presumed plugged (start/amps).** `HeldLimits` holds a value for the VIN, and the car has no `unplug` mark.
- **Where the rule runs.** `Reconciler.inapplicable(vehicle, attempt)` is a new public hook, called first in `beforeWrite`. That is after the attempt's read: after wake+read for a cloud raise or start, and on registry state for AMPS.
  - Stops and debug one-shots are never gated.
  - `NOT_HERE` and `HOME_NOW` `clearIf` the desire and return `SATISFIED "not here"` / `"home"`, tagged `"rules: "`.
  - `HOLD` returns `SATISFIED "rules: held: <why>"`.
  - Each non-SEND verdict logs at INFO: `"<vin> <aspect>: <verdict> (<state>: <why>)"`. A hold logs once per desire (`rec.heldLogged`).
- **Holds.** These are in `DesiredStore.noteOutcome`, with an early branch for `HELD` outcomes. A hold:
  - sets `lastOutcome`, `lastOutcomeAt` and `heldAt = now`;
  - never sets `settledAt`, `lastSentAt` or `lastFreeAt`, and never touches the free channel;
  - adds `paid * (attempt.wake + (attempt.maxAge is not None))` to `rec.paidSpent`.
  - Any other current outcome resets `heldAt = None`.
  - `plan`:
    - returns None while `heldAt is not None and vehicle.lastObservedAt <= heldAt`;
    - skips the NOT_SENT backoff gate for a held desire;
    - skips paid providers while `paidSends + paidSpent >= PAID_BUDGET` (= 4).
  - `newDesire` resets all three record fields.
- **`Vehicle.lastObservedAt`.** Stamped with the registry clock on every `observe`, `seen=False` included.
- **BLE ping.**
  - `TeslaBLE._tool(vin, *args)` is the runner factored out of `_fetch_state_json`. It holds `_bleLock` and closes the key pipe; the notes now run after the lock.
  - `_runPing(vin) -> Optional[bool]` runs `body-controller-state`. It returns True when rc is 0, False on a non-zero rc or a timeout, and None when the binary or key is missing.
  - `ping(vin) -> bool` observes `bleReach` (True as a sighting, False as `seen=False`) unless the run returned None.
  - `Run.runAttempt` pings when all of these hold: the provider is `TeslaBLE`, the attempt has an aspect, it is not a stop, and presence is PRESUMED.
  - No answer gives `Outcome(UNREACHABLE, "no BLE answer")`. That is one free failure; the paid path is unchanged.
- **Pre-wake check (beyond the brief's wording; see Concerns).** A cloud attempt that would wake first a car already `NOT_HOME` gets the verdict before the wake, so it ends `NOT_HERE` with no wake and no read. This is what `test_wake_only_a_home_car` requires. PRESUMED and HOME cars are still woken and read (b).
- **Targets.**
  - `onArrival(master, vehicle)`. With the plug checked at decision time, a `pluggedHere` car with a `SET_CHARGE_LIMIT` candidate gets `policyLimit` as a decision. With no policy limit, it gets `_restore` instead.
  - `applyPolicyLimit` sets the policy desire for every `presentVehicles` car except one `_left` reports leaving.
  - `_restoreDeparted` restores held cars where `_left` is not None and the deciding time is newer than our last write.
  - `_left(master, v) -> Optional[float]`:
    - for NOT_HOME, the deciding time;
    - for HOME, not plugged and `leaving > arriving`, the leaving time;
    - otherwise None.
- **Arrival calls.** Exactly one per plug-in event:
  - `noteObservation`'s `plugIn` branch, for `TELEMETRY_SOURCES` or `Gen3TWC`, through a lazy import (Presence stays a leaf at import time);
  - `TWCMaster.recordVehicleVIN` (confirmed), after `learnHome`.
- **Home from BLE.** In `noteObservation`'s lat/lon branch, `learnHome` now runs when `obs.source == "TeslaBLE" or twcVinAt(...) > NEVER`.
- **`pluggedNow` counts a charging point naming the car** (`twcVinAt > NEVER`) (deviation; see Concerns).
- **Removed:**
  - the `checkArrival` handler and the `onArrival` import in `TWCManager.py`;
  - `TWCSlave`'s power start, which now queues `{"cmd": "checkCharge"}` (the webhook stays);
  - `/api/checkArrival` and `/api/checkDeparture`, which now fall through to HTTPControl's 404;
  - `VehicleEndpoint._telemetryPluggedIn` and the TeslaAPI-enabled gate.
- **Endpoints.** These follow the brief's list comprehension over `registry.vehicles()`: `pluggedHere`, a `SET_AMPS` candidate, and `not (unknown and telemetrySaysPlugged)`, after the unchanged `blind` check.
- **`Presence.telemetrySaysPlugged(master, v)`** is the BASE predicate: `syncSource in TELEMETRY_SOURCES and pluggedIn is True`. `master` is unused, but the signature is kept for Task 4.

## Interfaces Tasks 4–6 consume (exact)

- `Presence`:
  - `SEND, NOT_HERE, HOLD, HOME_NOW` (`"send"`, `"not here"`, `"hold"`, `"home"`)
  - `applicable(master, v, attempt) -> str`, which reads only `attempt.restore` and `attempt.capability`
  - `telemetrySaysPlugged(master, v) -> bool`
  - `pluggedNow(master, v)`, which is now also True while `twcVinAt(master, v) > NEVER`
- `Targets`:
  - `onArrival(master, vehicle) -> None`. Task 5's attribution winner calls it once.
  - `_left(master, vehicle) -> Optional[float]`
- `TeslaBLE`:
  - `ping(vin) -> bool`
  - `_runPing(vin) -> Optional[bool]`
  - `_tool(vin, *args) -> Optional[(stdout, stderr, rc)]`
- `Reconciler`:
  - `PAID_BUDGET = 4`
  - `VehicleReconciler.inapplicable(vehicle, attempt) -> Optional[Outcome]`
- `Outcome.HELD = "rules: held: "`
- `Vehicle.lastObservedAt: float`
- **For Task 6 (per-desire held / in flight / why).** Read `desired.record(key, aspect)`:
  - held is `rec.heldAt is not None`;
  - the reason is `rec.lastOutcome.detail`, which starts with `Outcome.HELD`. Strip that prefix for "Waiting: <why>"; the why is `decide()`'s reason, e.g. "driving" or "no newer evidence";
  - in flight is `rec.inFlight`;
  - `heldAt` resets to None on the next non-held outcome for the current desire, and on any new desire;
  - `rec.paidSpent` and `rec.heldLogged` are also there.
- **Parity harness.** `realBle(m, answers=…, vins=…, ping=True)`, where `ping` is True, False or `callable(vin)`. Pings go to `b.pings`.
- **Test helpers.**
  - `reconcile_helpers.bleAnswers(master, ok=True)` gives a scripted TeslaBLE a ping that observes `bleReach` as the real one does.
  - `test_limit_reconciler.setup(..., here=True)`: by default the car is plugged in at home (a `Gen2TWC` `pluggedIn` True). Pass `here=False` for a blank car.
  - `test_limit_reconciler.leave(v)` marks an unplug after the plug-in.

## Tests and results

- **Baseline** (cb7a8f53), `tests/unit tests/EMS`: **1989 passed, 1 warning**.
- **After** (d5cc8711), same scope: **2030 passed, 1 warning**. That is +42 new tests (14 presence, and 28 parity rows: 24 functions plus the ×4 parametrization) and −1 removed `test_disabled_tesla_api_lists_nothing`. One endpoint test is rewritten.
- Black is clean on every touched lib file and on `test_presence.py`, `test_command_path_parity.py` and `reconcile_helpers.py`.
  - The other touched tests are the legacy `;`-joined files. My added lines there avoid `;` joins; split fragments of pre-existing lines keep their style.
  - There is no `__import__`.
- **Grep** `git grep -nwE 'checkArrival|_telemetryPluggedIn' -- lib html tests/unit tests/integration tests/API docs` finds only `tests/unit/test_presence.py:735`, the 404 assertion's path string.
  - `checkDeparture` stays in lib: these are the internal 5/20/45-minute reads (Q6).
- **TDD evidence.**
  - I drafted the lib before the new tests, so test-first was not literal.
  - On a detached worktree at cb7a8f53, with the new test files copied in, **all 14 new presence tests fail** and **7 of the 28 new parity rows fail**:
    - box arrival while driving;
    - contact while driving;
    - never-left;
    - presumed read outside;
    - departing never presumed;
    - startup unplugged;
    - `wake_only_a_home_car[away]`.
  - The other 21 parity rows already hold on the pre-task lib. They are characterization rows for behaviour the task must keep (for example scenario 7, BLE gone five minutes, ble_only never pays, and the presumed Fleet paid sequence (b), which Task 2's presence already reached).
  - Tests that moved lib code while I iterated:
    - the PRESUMED blast radius (146 failures) led to `pluggedNow` counting `twcVin`;
    - the hold backoff collision led to the `heldAt is None` gate;
    - `test_wake_only_a_home_car` led to the pre-wake NOT_HOME check;
    - the restore/apply overlap led to `_left`;
    - the debug one-shot test led to "no ping without an aspect".
- **Parity.**
  - **No existing count or timing moved.**
  - Edits to existing parity code:
    - `install()` calls `setup(here=False)`;
    - the `realBle` ping stub;
    - `fleetPoint` gains one `chargingState "Charging"` TeslaMate observation (see the mapping).

## Test mapping (existing tests touched)

| Test / helper | Fate |
|---|---|
| `test_limit_reconciler.setup` | New `here=True` default: the car is plugged in at home, because PRESUMED cars now hold. Presence-centric callers pass `here=False`: `test_presence` ×5, parity `install`, and `test_limit_wiring.restarted` (PLUMBING-ONLY) |
| `test_limit_reconciler`: `test_restore_to_an_absent_car_retries_hourly…`, `test_a_restore_falls_to_fleet…`, `test_a_rules_settled_restore…`, `test_a_restore_stamps_the_outside_value` | `leave(v)` before the restore, so the car is departed (PLUMBING-ONLY: the restore's subject must be gone) |
| `test_limit_reconciler::test_no_wake_to_lower_wake_to_raise_never_for_a_restore` | `leave(v)` before the restore. **INTENTIONALLY CHANGED (b, the restore row)**: a restore to a car HOME and plugged is `HOME_NOW` (cleared, nothing sent). See Concern 1 |
| `test_reconciler_queues.reconciler()` | The car gets a `Gen2TWC` plug and a `plugIn` mark (Mock master, no hook) (PLUMBING-ONLY) |
| `test_amps_reconciler::test_the_paid_budget_is_per_car`, `test_teslaapi_readonly_gate::TestThroughTheWalk.make` | The second car gets a `Gen2TWC` plug (PLUMBING-ONLY) |
| `test_charging_reconciler.fleetOnTwc` | The `vehicle_data` fixture's position goes from (1.0, 2.0), far away, to HOME. Otherwise the read places the car away and every start/limit is `NOT_HERE` (PLUMBING-ONLY) |
| `test_charging_reconciler::test_a_fleet_only_car_is_stopped_once_the_list_loads` | The car is now HOME, so `updateChargeAtHome` reads it. The fixture's read answers `Charging` for this test, so the stop still has something to stop (PLUMBING-ONLY) |
| `test_limit_wiring::test_periodic_reenforce…` | `onArrival(m, v)`; uses the default (plugged) setup (PLUMBING-ONLY, per the brief) |
| `test_limit_wiring::test_a_held_car_with_no_known_position_is_present` | `bleAnswers(m)`: the presumed car is pinged first (F5 equivalent for the scripted provider) (PLUMBING-ONLY) |
| `test_limit_wiring::test_an_unplug_older_than_our_last_limit_write_is_no_departure` | `r.pass_()` after `restarted`. TeslaMate's retained `Complete` is now a plug-in event, so `onArrival` (no policy yet) sets a restore, which `HOME_NOW` clears with nothing sent. The rest is unchanged (PLUMBING-ONLY, consequence of (c)) |
| `test_vehicle_endpoint.car()` | New `plugged=True` (an `OwnerAPI` `pluggedIn`). `test_state_from_registry_values…` passes `plugged=False` (PLUMBING-ONLY) |
| `test_vehicle_endpoint::test_empty_without_tesla_api` | Rewritten as `test_a_car_plugged_here_is_listed_whichever_module_knows_it` (**INTENTIONALLY CHANGED (j)**) |
| `test_vehicle_endpoint::test_disabled_tesla_api_lists_nothing` | Deleted (**INTENTIONALLY CHANGED (j)**: endpoints no longer depend on the TeslaAPI module); covered by the rewritten test above |
| `test_telemetry_registry.py:262–266` | `telemetrySaysPlugged(None, v)` (PLUMBING-ONLY) |
| parity `fleetPoint` (rows 13, 14 and both mode-2 `fleetPoint` rows) | One `chargingState "Charging"` TeslaMate observation, so the car on the point is plugged here. The plan's trace covered only the `onTwc` rows; these four had no plug evidence. **Counts and timings unchanged** (PLUMBING-ONLY) |
| parity `realBle` | The `ping=` stub (F5) |
| `tests/integration/test_api_input_validation_extended.py` `test_check_arrival_extra_fields`, `test_check_departure_extra_fields` | Deleted (**INTENTIONALLY CHANGED (d)**). Replaced by the 404 assertions in `test_presence::test_power_start_still_queues_check_charge` |
| `test_charging_points.py`, `test_gen2_idle_minimum.py` | No edit needed |

## Files changed

- **lib:**
  - `Control/HTTPControl.py`
  - `EVSEInstance/VehicleEndpoint.py`
  - `TWCManager.py`, `TWCMaster.py`, `TWCSlave.py`
  - `Vehicle/Presence.py`
  - `Vehicle/Reconcile/{Desired,Outcome,Reconciler,Run,Targets}.py`
  - `Vehicle/Registry/Vehicle.py`
  - `Vehicle/TeslaBLE.py`
- **tests:**
  - `tests/unit/{reconcile_helpers,test_amps_reconciler,test_charging_reconciler,test_command_path_parity,test_limit_reconciler,test_limit_wiring,test_presence,test_reconciler_queues,test_telemetry_registry,test_teslaapi_readonly_gate,test_vehicle_endpoint}.py`
  - `tests/integration/test_api_input_validation_extended.py`

## Deletions taken

- HTTP hints: −12.
- The `checkArrival` handler and import: −5.
- `_telemetryPluggedIn`: −5.
- The endpoint's TeslaAPI gate and attached-only walk: −6 net.
- Targets' old `onArrival` and the policy-wide arrival.

There was nothing else outside Presence that the rule subsumes:
- Gen3's `_correlate` `atHome` and `updateChargeAtHome`'s HOME filter are F11 keeps.
- `pluggedCars` is ruled out (F15/F16).

## Lib delta

- Before: **26,463**. After: **26,563**. **Δ +100**, against an expected +77 (range +65..+90). That is 23 over the target: inside the 25 stop line, and over the range.
- `git diff --shortstat cb7a8f53 -- lib`: 13 files changed, 194 insertions(+), 94 deletions(-).

| File | net | note |
|---|---|---|
| Presence.py | +46 | `applicable` ≈26 with blank lines, `telemetrySaysPlugged` 5, arrival call 5, `pluggedNow`'s `twcVin` 3, BLE `learnHome` 1, constants and imports 5 |
| Reconciler.py | +29 | the `inapplicable` hook 18, the hold gate 3, the backoff skip 1, the budget 3, imports 3 |
| Targets.py | +17 | `_left` 10, `_apply` shared by `applyPolicyLimit` and `onArrival` |
| Desired.py | +14 | record fields and reset 3, held branch 8, `heldAt` reset 1, import 1 |
| Run.py | +11 | ping 5, pre-wake NOT_HOME check 3, imports 2 |
| TeslaBLE.py | +7 | `_tool` factored out; `_runPing` and `ping` 13 |
| Vehicle.py | +3 | `lastObservedAt` |
| Outcome.py | +2 | `HELD` |
| HTTPControl / VehicleEndpoint / TWCManager | −28 | deletions |

- **Where it went over:**
  - the pre-wake check (+3, not in the plan);
  - `pluggedNow`'s `twcVin` (+3);
  - `_left` (the plan budgeted 6 for both Targets functions);
  - black's wrapping of the `inapplicable` log line.
- I cut what I could: shorter docstrings and comments, verdict strings reused as outcome details, the record fields on one line, and the ping condition compacted.
- Tasks 2 and 3 together add about +170 (Task 2's +70 plus this +100). The phase still depends on Tasks 4–5's planned deletions to shrink.

## Self-review

- **Completeness.** Every brief item is done, including the BLE home rule and its test. The parity rows exist under the brief's names and each states its paid tuple.
  - `test_arrive_limit_set_then_shift_to_d_in_the_driveway_restores_over_ble` cannot happen literally under the table: a restore to a driving (PRESUMED) car is `HOLD`. The row restores over BLE once the fix is outside, with no Fleet request.
- **YAGNI and patterns.**
  - The hook goes on the reconciler (as `beforeWrite` does), and the record fields sit on `AttemptRecord`.
  - The `_tool` seam is shared with `_fetch_state_json`, and nothing new is polled.
- **The tests check behaviour.** They run on real master, registry, store, TeslaAPI and TeslaBLE objects, with `requests_mock` counts.
- **Pristine output.** The suite prints only BASE's one warning.
- **Comment rule.** I checked the new lib comments: none carry history, phase, ruling or PR ids.
- **Threading.**
  - `ping` observes outside `_bleLock`, and `_tool` holds it for the run only.
  - `onArrival` from the MQTT or Gen3 thread takes the Desired lock, then the HeldLimits read (settings). This is unchanged in order.
  - `rec.heldLogged` is written by the worker thread while the attempt is in flight, as `pendingSave` is.
  - I checked `observeTwcVin`'s anonymous-session merge loop: it re-observes fields outside the registry lock. A merged `Gen3TWC` `pluggedIn` that reaches `onArrival` and the Desired lock therefore holds no registry lock.

## Concerns

1. **Intended by the plan, but one consequence may be unforeseen. Ask the user.** The plan's Architecture bullet says restores are ordinary messages from the policy pass (E2), and "a restore needs the car gone or leaving". So HOME and plugged → `HOME_NOW` is the stated design. The consequence: policy → None while the car is home and plugged (for example, the night policy ending in the morning) no longer releases the hold until the car unplugs or leaves. BASE restored it at once. `test_no_wake_to_lower_wake_to_raise_never_for_a_restore` pinned the BASE behaviour; I kept its assertion by departing the car first, and map it as INTENTIONALLY CHANGED.
2. **Unplanned blast radius.** Making PRESUMED cars hold broke 146 reconciler tests built on blank cars. I fixed them by plumbing: the `setup(here=True)` default, plus per-test plug or departure evidence (mapping above). That is a wide test edit the brief did not list. No assertion was loosened.
3. **Deviations from the brief, with reasons:**
   - `pluggedNow` counts `twcVinAt > NEVER`. A Gen2 never observes `pluggedIn`, so without this a TWC-named car with no car-side feed is never "plugged here". Starts and rates would then be `NOT_HERE`, and `recordVehicleVIN`'s `onArrival` would never fire.
   - `applyPolicyLimit` skips `_left` cars. Otherwise a held car that is HOME, unplugged and leaving gets the policy desire and then the restore on every policy pass. Each is a `newDesire`, which resets the paid budget.
   - The pre-wake NOT_HOME check. Without it, a targeted start to a car known away pays a wake and a read before `NOT_HERE`, and `test_wake_only_a_home_car` requires that it does not.
4. **`paidSpent` counts a held paid attempt's read even when the cache answered it.** This is conservative (fails closed). In `test_held_re_plans…` the budget stopped after 3 actual paid requests (1 read, 2 wakes) with `paidSpent` = 4.
5. **A held PRESUMED BLE car re-plans on every pushed field.** `lastObservedAt` is stamped for all fields. A BLE car driving in range is therefore pinged on each TeslaMate message ("pings allowed" in the box row), with no `MIN_SEND_GAP` between pings.
6. **`_runPing` treats any non-zero rc as absence (F9).** A local adapter failure would read as "out of range". `body-controller-state` needs no key and answers on a sleeping car, so a command-on-sleeping-car failure cannot produce it.
7. **TeslaMate plug narrowing is still blind at plug-in.** `onArrival` checks `pluggedHere` at call time, but `charger_power` arrives after `plugged_in`. A DC charger inside the radius can still get the arrival apply. `test_arrival_is_one_decision…` covers only the case where the fast-charger field lands first.
8. **Parity edits beyond the two listed:** `install(here=False)` and `fleetPoint`'s plug observation, both plumbing. No count or timing moved.
9. **Lib Δ is +100**, against +77 expected, above the +90 range (table above).
10. **Scenario 18** (`test_fleet_only_failed_remote_restore_is_retried_per_restore_retry`) pins BASE's paid bound: one send plus one blind retry, the same as row 17b. It does not pin an hourly paid retry. It passes on the pre-task lib, so it is characterization. The brief's "(Q8)" tag may have expected an hourly retry; please confirm Q8's intent.

---

## Fix round 1 (commit 2e6070f9)

**Critical 1: the budget counts requests, not flags.**
- `Vehicle.paidRequests` is a new counter. `TeslaAPI._request` increments it for every Fleet-slot paid path (wake_up, vehicle_data, command) that reaches the network for that car. A cache answer, a free online check, and the Owner API add nothing.
- `Attempt.paidBefore` is stamped from it at plan time. When an attempt ends held, `Reconciler.inapplicable` adds `vehicle.paidRequests - attempt.paidBefore` to `rec.paidSpent`.
- The budget gate in `plan` reads `spent = paidSends + paidSpent >= PAID_BUDGET and applicable(...) != SEND`, judged on registry state. So once the car's state says the message would go, earlier holds never block a paid send. The existing per-arm send bound (`paidAgain`) still caps sends.
- New parity row `test_a_drive_inside_the_radius_spends_no_budget_and_the_park_applies` (the reviewer's scenario):
  - setup: TeslaMate + Fleet, no BLE, state=driving pushed every 5 s for 20 min, policy 80;
  - `paidSpent` equals the paid wakes plus reads actually made, which is 0;
  - parked: the limit goes. **Paid tuple (1, 0, 1)**: one read at the park, no wake (online), one command.
  - On d5cc8711 this row fails: `paidSpent` = 4 with no paid request made.
  - For this row, the parity `FleetCar` fixture gained a `shift` attribute, None by default, so `vehicle_data` reports the gear (D while driving). Other rows are unchanged.

**Minor 3.**
- `test_limit_reconciler.setup(here=True)`, `leave(v)`, the queues reconciler, the amps budget row, the read-only gate and `test_presence.car()` now plug with `Gen3TWC` `pluggedIn` (an observation lib emits) instead of `Gen2TWC`.
- New real PRESUMED + plugged apply row: a plug-in, then a newer `absent` mark, gives SEND "plugged in". The test also asserts that this state is PRESUMED and plugged.

**Minor 4.**
- `_runPing` returns True on rc 0, and None when nothing could run (no binary or key).
- Any other result (timeout, launch or tool failure, non-zero rc) defers to `scanForVehicleInRange`. That is True/False/None under the scan's own rules: False only when the scan ran cleanly and missed the car, and the scan's own `bleReach` observation is kept.
- Test: `test_an_unanswered_ping_is_absence_only_when_the_range_scan_misses`.

**Minor 5.**
- `Presence.applicable(master, v, capability, restore) -> (verdict, why)`. **The signature changed** from `(master, v, attempt)` so plan's budget gate can call it without an attempt.
- The whys: "plugged in", "not plugged in", "presumed" (via "plugged in"), "home", "leaving", "tie", "driving", "not known here", "away".
- The held detail is `"rules: held: <why>"`. The cell table test now asserts each row's why.

**Minor 6.** `fleetPoint` observes `chargingState "Charging"` from `FleetAPI` (rows 13/14 stay Fleet-only). No count or timing moved.

**Minor 7.**
- `learnHome(master, vehicle, lat, lon)` takes the fix pair. `noteObservation` passes the triggering source's own pair; `recordVehicleVIN` passes the newest lat/lon.
- Test: `test_home_is_learned_from_the_triggering_sources_own_fix` (half a BLE fix plus another source's lon never sets home).

**Minor 9.** The pre-wake check only returns when `inapplicable` gives an outcome.

**Size cuts taken:**
- `TWCSlave.pluggedCars` uses `Presence._plug` (−7 in that file);
- `Presence.departed` replaces Targets' `_left` and serves applicable's HOME cells;
- the held branch is folded into `noteOutcome`'s `if current:` (a hold also leaves the free channel untouched);
- the start cell reads `heldLimits.holding()` lazily;
- `heldLogged` is dropped (a hold logs when `heldAt` is None, once per hold episode);
- `_settingsKey` is computed once in `_fetch_state_json`.

**Not done (as instructed):** Important 2, the restore churn for a car home and plugged.

**Interface changes for Tasks 4–6:**
- `Presence.applicable(master, v, capability, restore) -> (str, str)`
- `Presence.departed(master, v) -> Optional[float]` (Targets' `_left` is gone)
- `Presence.learnHome(master, vehicle, lat, lon)`
- `Vehicle.paidRequests: int`
- `Attempt.paidBefore: int`
- `AttemptRecord.heldLogged` is removed.
- Task 6 still reads held as `rec.heldAt is not None`, with the reason in `rec.lastOutcome.detail` after `Outcome.HELD`. That reason is now the cell's.

**Tests:** covering tests pass. `tests/unit` + `tests/EMS`: **2033 passed, 1 warning** (+3: the drive row, the ping/scan test and the learnHome pair test). No existing parity count or timing moved. Black is clean on the touched lib files, `test_presence.py`, `test_command_path_parity.py` and `reconcile_helpers.py`.

**Lib delta vs cb7a8f53:**
- Lines: 26,463 → 26,568, **Δ +105**. That is +5 on round 0's +100, and 28 over the +77 target, so past the 25 stop line.
- `git diff --shortstat cb7a8f53 -- lib`: 14 files changed, 221 insertions(+), 116 deletions(-).
- The cut list saved about 14. The Critical fix added about 13: the request counter in Vehicle/TeslaAPI 4, `paidBefore` 3, and the applicable-aware budget gate 5. The why tuples, the fix-pair `learnHome` and the scan fallback added about 6.

**Concern:** a held re-plan runs on every pushed observation. In the drive row (240 pushes over 20 min) this made no HTTP request at all: counts are vehicle_data 1, command 1, free 0, because live telemetry vouches for the awake state and the cached limit. A car without live telemetry would make TeslaAPI's online check, which is cached for 120 s.

---

## Fix round 2 (commit after 2e6070f9: "Restore the car's limit whenever the policy has none")

**User ruling ("restore the limit when the new policy has no chosen value").**
- A restore now goes in every presence cell. `Reconciler.inapplicable` returns None for restores, as it does for stops. Restores still never wake, and the BLE ping still runs first for a PRESUMED car on BLE.
- Removed as dead:
  - `Presence.HOME_NOW` and its handling;
  - the `restore` parameter and restore branch of `applicable`, whose signature is now **`applicable(master, v, capability) -> (verdict, why)`**.
- `departed()` stays: applicable's HOME apply cell ("leaving") uses it, and so do Targets' `applyPolicyLimit` and `_restoreDeparted`.
- Nothing else in Targets or Presence became dead:
  - `_restore` serves `onArrival` (no policy), `applyPolicyLimit(None)` and departures;
  - `leaving`/`arriving` serve `departed` and the tie cell.
- `test_no_wake_to_lower_wake_to_raise_never_for_a_restore` is back to BASE's form (no `leave(v)`) and passes, so it is no longer INTENTIONALLY CHANGED.
- New row `test_policy_none_while_home_and_plugged_restores_once`: five policy passes with no limit on a car home and plugged give exactly one restore, after which the hold is gone and no desire is left (no churn).
- New `test_a_restore_goes_wherever_the_car_is`: `inapplicable` passes a restore for a car that is HOME and plugged, HOME and leaving, PRESUMED, driving, or NOT_HOME.
- The cell table drops its restore rows.
- `test_a_plug_or_a_newer_arrival_cancels_a_pending_restore`: the "arrival" half now asserts that the next policy pass replaces the pending restore with the policy limit, since restores themselves are no longer cancelled at send.
- `test_limit_wiring::test_an_unplug_older…`: the restart's plug-in restore would now really be sent and would drop the hold the test needs. It is cleared explicitly instead of run (PLUMBING-ONLY; that restore is not the subject).

**Re-review minors:**
- `rec.paidSpent` is added in `DesiredStore.noteOutcome` under the store lock, only for the current desire's held outcome. `Reconciler.report` passes `spent = vehicle.paidRequests - attempt.paidBefore` (new `noteOutcome(..., spent=0)` keyword).
- Run's pre-wake check is one line inside the `if wakeFirst:` block: `early = state == NOT_HOME and reconciler.inapplicable(vehicle, attempt)`, then `early or _wake(...)`. `inapplicable` now returns already-tagged details (`"rules: not here"`, `"rules: held: …"`), so Run passes them through unchanged. Run imports `NOT_HOME, PRESUMED, presence` directly.
- The why for a presumed car inside the radius with a gear other than P is now "not parked". Other presumed holds read "not known here".

**Tests:** covering tests pass. `tests/unit` + `tests/EMS`: **2035 passed, 1 warning**. No existing parity count or timing moved. Black is clean on the touched lib files and the two new-style test files. `HOME_NOW` and `heldLogged` no longer appear in lib or tests.

**Lib delta vs cb7a8f53:** 26,463 → 26,564, **Δ +101**. `git diff --shortstat cb7a8f53 -- lib`: 14 files changed, 218 insertions(+), 117 deletions(-). That is −4 on round 1's +105, and still 24 over the +77 target.

### Fix round 2, continued (commits d4addd19 and dee7d4e2)

**The refined ruling replaces item 1 of the section above (d4addd19).** A policy with no limit is an apply whose target is a release.
- `Desired.RELEASE = -1`.
- `Targets._apply` is now the single path for a policy's limit and for RELEASE:
  - with no limit and nothing held, it clears the desire;
  - otherwise it sets `RELEASE` (by "policy", `restore=False`), or the policy's limit.
- Departures keep their own desire, set through `_apply(..., restore=True)`: the outside limit, by "restore", `restore=True`. The old `_restore` is gone.
- A RELEASE desire goes through the apply cells and the apply wake rule:
  - `plan` computes the wake on the outside limit it aims at, so a release that raises may wake and one that lowers never does;
  - `Rules.releases(d)` (restore or RELEASE) feeds `needsLiveRead`;
  - `decideChargeLimit` treats RELEASE like a restore for the held-limit record (send the outside limit only while ours is still set, then drop the hold).
- A departure restore still goes in every cell and never wakes.
- Tests:
  - `test_policy_limit_sets_desired_for_present_cars_and_none_restores` now expects `(RELEASE, restore False, "policy")`. **INTENTIONALLY CHANGED** by the ruling.
  - The no-churn row is now `test_a_policy_with_no_limit_is_an_apply_of_the_cars_own_once`. A car home and plugged at the held 50 (outside 90) gets a wake and one 90 send over five policy passes, then has no hold and no desire. A held 80 releasing to 60 is sent with no wake.
- The round-2 minors stand:
  - `paidSpent` is added in `noteOutcome` under the lock;
  - the pre-wake check is a single line in the `if wakeFirst:` block;
  - the reason reads "not parked".

**No wake when the car's point is offered nothing (dee7d4e2).**
- `distributeEVSEPower` records `master.offered = {point.vehicleKey: target watts}` from the targets it just set. Nothing is recomputed.
- In `plan`, a limit raise (a RELEASE that raises included) or an amps raise for a car whose point is offered 0 gets `wakes = False`. The message still goes the way a lowering does: without a wake over the free channel, retried on the normal schedule. Run logs it as `"<provider> no wake for <vin> before <capability>: nothing offered"`.
- A car on no charging point (no entry) is not affected.
- Starts are left alone. I found no path where a start is desired with no offer, but I did not trace it exhaustively.
- Test: `test_limit_reconciler::test_a_raise_never_wakes_a_car_its_point_offers_nothing` uses the real distributor:
  - point at 0: the raise is sent without a wake, and the log line appears;
  - offered more than 0: the next raise wakes first.
- **Parity:** no existing row has a zero-offer point at the time of a raise. A log scan of parity, wiring, charging and amps found no "nothing offered", so no parity row was added and **no count moved**.

**Tests:** `tests/unit` + `tests/EMS`: **2036 passed, 1 warning**. Black is clean on the touched lib files and `test_presence.py`.

**Lib delta vs cb7a8f53:** 26,463 → 26,579, **Δ +116**. `git diff --shortstat cb7a8f53 -- lib`: 15 files changed, 252 insertions(+), 136 deletions(-). That is 39 over the +77 target and past the 25-line stop line. Round 2 added 15 lines:
- the release path: `RELEASE`, `releases()`, the `aim` wake computation, the Rules line, and departures sharing `_apply`;
- the offered map and the idle wake gate: about 6.
