# Task 8 report: leave a sleeping car alone

Commit **7c503a62** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent 6704fdb0). Not pushed.

## What I built

- **The pre-flight reads the sleep status.**
  - `TeslaBLE._runPing` still runs `body-controller-state` through `_tool`, under `_bleLock` only.
  - On rc 0, the new `_noteSleep(vin, stdout)` parses `vehicleSleepStatus` (see the next section) and observes `state` from source `TeslaBLE`:
    - `VEHICLE_SLEEP_STATUS_ASLEEP` → `"asleep"`;
    - `VEHICLE_SLEEP_STATUS_AWAKE` → `"online"`.
  - The parse runs inside `_safeNote`. Any other answer (UNKNOWN, a missing key, output that is not JSON) observes nothing and changes nothing else: the ping is still True.
  - The observation is made after `_tool` returns, so the lock is already released.
  - `_runPing`'s return values are unchanged: True, the scan's verdict, or None.
- **`Presence.asleep(v)`** is the single "known asleep" predicate. It is True when the newest `state` from any source is `"asleep"` and no sign of life is newer. Signs of life:
  - a newer `state` that is not asleep (this covers TeslaMate, Fleet and BLE AWAKE);
  - a `plugIn` or `unplug` mark;
  - any non-None `shiftState`;
  - `chargingState == "Charging"`;
  - `actualCurrent >= 1` (TWC heartbeats, Gen3 vitals, TeslaMate).
  - A tie counts as asleep.
- **Run** (`runAttempt`):
  - `quiet` = a TeslaBLE attempt with an aspect, not a stop, `wake` False, and presence not NOT_HOME.
  - A quiet attempt runs the ping first, as a PRESUMED one already did. It skips the ping when `asleep(v)` is already True.
  - After the ping, if `asleep(v)` is True, the attempt returns `Outcome(SATISFIED, O.HELD + "asleep")`. No command runs, and the "no wake for …" line is never reached.
  - Attempts that may wake take the path they took before.
- **The hold.** The existing hold handling is reused unchanged: `noteOutcome` stamps `heldAt`, leaves the free channel alone and sets no `settledAt`. `plan`'s held gate is narrowed for this one hold:
  ```python
  if rec.heldAt is not None and (
      vehicle.lastObservedAt <= rec.heldAt
      or rec.lastOutcome.detail == O.HELD + "asleep"
      and Presence.asleep(vehicle)
  ):
  ```
  Repeated asleep readings, Gen2 heartbeats at 0 A and Gen3 vitals all bump `lastObservedAt`, but they do not re-plan while `asleep(v)` holds. One predicate both skips the run and gates the re-plan, so a sign of life always re-plans and the next attempt pre-flights again. It cannot get stuck behind a stale "asleep".
- **Fleet (rule 6).**
  - `TeslaAPI.onlineState` observes the free `vehicles/{vin}` answer's `state` (`asleep`/`online`/`offline`) under the read slot's source name (`FleetAPI`/`OwnerAPI`). Fleet's "asleep" therefore counts as known asleep and suppresses BLE runs.
  - A Fleet wake that answers online observes `state "online"`, so the wake is a sign of life.
  - The cloud command paths are otherwise untouched.
- **Guarding the telemetry sync.** Observing `state` from providers would have flipped `syncSource` away from a live TeslaMate or Fleet Telemetry feed, because `telemetryState` read `latest("state")`. Two changes prevent that:
  - `Vehicle.telemetryState` now uses the newest `state` among `TELEMETRY_SOURCES` (`latestFrom` with the other sources excluded), aged through the same `_ageOf`/`_liveAt` path as before. With no feed reading it still returns `latest("state"), None`, as `test_telemetry_state_ages_only_telemetry` pins.
  - `FleetTelemetryMQTT.mqttMessage` compares the new connectivity state with its own reported `state`, not `latest("state")`. Otherwise a BLE "online" would suppress Fleet's own "online" and leave its stale "offline" in place.
- **Logging.** The once-per-desire line is `report()`'s existing outcome line: `chargeLimit setChargeLimit for <vin> via TeslaBLE: satisfied rules: held: asleep`. An attempt runs only when the desire is first planned or after a sign of life. So that line appears once per hold, plus once more for each sign of life whose pre-flight still finds the car asleep. I added no separate `hold (asleep)` line.

## The JSON field, and how I confirmed it

- I ran `~/tesla-control -ble -vin "$VIN" body-controller-state` on the live box (`ssh twcmanager`). The VIN came from `/etc/twcmanager/settings.json` inside the remote shell and was masked with `sed` in the output. I passed no key; the command needs none.
- Answer (rc 0; the car was asleep):
  ```
  {
  	"vehicleLockState": "VEHICLELOCKSTATE_UNLOCKED",
  	"vehicleSleepStatus": "VEHICLE_SLEEP_STATUS_ASLEEP",
  	"userPresence": "VEHICLE_USER_PRESENCE_NOT_PRESENT"
  }
  ```
- The awake value is the protobuf enum's sibling, `VEHICLE_SLEEP_STATUS_AWAKE`. I could not observe it live, because the car was asleep and waking it was not allowed. UNKNOWN, or a missing field, observes nothing.
- Nothing in the repo parsed this output before; `_runPing` used only the return code.

## Tests and TDD evidence

New file `tests/unit/test_sleeping_car.py` (18 tests). It uses the parity harness: a real master, TeslaBLE and TeslaAPI, with `requests_mock`. Only `_tool` is scripted, and it returns the live box's JSON.

| Test | Pins |
|---|---|
| `test_a_lowering_to_a_sleeping_car_holds_after_one_preflight` | Over an hour with 0 A heartbeats and repeated TeslaMate "asleep": one pre-flight, no command, no HTTP, one `held: asleep` line, no "no wake for" line, the desire kept. Then TeslaMate `state online` → the plan re-runs, a second pre-flight answers AWAKE, and the limit is sent |
| `test_a_raise_still_wakes_a_sleeping_car` | Known asleep, a raise: BLE `wake` then `charging-set-limit`, with no pre-flight |
| `test_a_fleet_online_check_that_finds_it_asleep_suppresses_ble` | A Fleet "asleep" → `Presence.asleep`; a BLE lowering then runs nothing; paid (0, 0, 0) |
| `test_a_fleet_wake_is_a_sign_of_life` | Row-4 shape: after the wake, `FleetAPI` state is online and `asleep` is False; paid (1, 1, 1) |
| `test_another_sources_sleep_reading_keeps_the_feed_in_sync` | TeslaMate stays `syncSource` after a newer BLE "asleep" |
| `test_a_sign_of_life_ends_known_asleep` ×7 | Each sign of life ends `asleep`; the non-life readings (TeslaMate asleep, 0 A, Stopped, a None shift) do not |
| `test_an_unplug_is_a_sign_of_life` | The unplug mark |
| `test_the_ping_reads_the_sleep_status` ×4 | ASLEEP → asleep, AWAKE → online, `{}` and non-JSON → nothing; the ping is True every time |
| `test_the_fleet_feed_compares_with_its_own_state_not_a_sleep_check` | Fleet DISCONNECTED, then BLE online, then Fleet CONNECTED → Fleet's own state is online |

TDD evidence:
- **RED** before any lib change: 13 failed, 3 passed. The raise row and two parametrized non-sleep cases passed already, as characterization.
- **GREEN** after the change: all pass.
- **Mutations:**
  - Replacing the plan gate's `Presence.asleep(vehicle)` with `False` gave 361 `held: asleep` lines instead of 1, so the narrowed gate is pinned.
  - Removing the wake's `observe` failed the Fleet-wake test.
  - Reverting the `FleetTelemetryMQTT` line failed the feed test (`'offline' == 'online'`).
- **Suites:**
  - `tests/unit` + `tests/EMS`: **2119 passed** (baseline 2101, plus 18 new).
  - Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2128 passed, 1 xfailed**.
- Black is clean on every touched file.

### Existing tests touched (deleted-test rule: none deleted)

| Test | Change | Class |
|---|---|---|
| parity `test_ble_silent_umc_car_with_telemetry_inside_radius_is_home` (scenario 13) | `b.pings == []` → `b.pings == [VIN]`: the BLE lowering's pre-flight is its one ping. Commands, paid (0, 0, 1) and timing are unchanged | INTENTIONALLY CHANGED (this task) |
| `reconcile_helpers.ScriptedProvider` default `module` | `object()` → `SimpleNamespace(ping=lambda vin: True)`. A scripted provider named TeslaBLE is now pinged before a no-wake attempt; 24 reconciler tests would otherwise raise AttributeError. It answers True, with no sleep status | PLUMBING-ONLY |

All other parity counts and timings are unchanged. That includes row 2 (`test_ble_only_limits_never_wake_to_lower`): its pings stub answers True and reports no sleep status, so both lowers still go.

## Lib delta

- Before: 26,217. After: **26,250** (**+33**, against a target of ≤ +20; 13 over, under the 25-over stop line).
- `git diff --shortstat 6704fdb0 -- lib`: 7 files changed, 48 insertions(+), 15 deletions(-).

| File | +/− | What it buys |
|---|---|---|
| Presence.py | +14/−0 | `_LIFE` (the sign-of-life readings) and `asleep()` |
| TeslaBLE.py | +10/−3 | `_noteSleep` and the `_runPing` rewrite |
| Run.py | +8/−4 | `quiet`, the ping condition, the hold |
| Reconciler.py | +6/−2 | the narrowed held gate |
| TeslaAPI.py | +4/−0 | the online check's `state` (rule 6) and wake-is-life |
| Vehicle.py | +5/−5 | `telemetryState` from feeds only (net 0) |
| FleetTelemetryMQTT.py | +1/−1 | its own state for the comparison (net 0) |

- **Trims already taken:**
  - `_runPing` folded to `return ran and (rc == 0 or scan)`;
  - the docstring kept at two lines;
  - one-line comments on the gate and `telemetryState`;
  - `asleep`'s loop as a comprehension.
- **Duplication search:** a scan for defs in the touched Vehicle files referenced at most once in `lib`/`html` found nothing to delete.
- The `telemetryState`/MQTT guard costs no net lines but is required for correctness.
- Further cuts would mean dropping a listed sign of life or the wake-is-life line. I did not trim further.

## Concerns

1. **A pre-flight can now mark a HOME car absent.** Before this task only PRESUMED cars were pinged. Now a HOME car with a no-wake BLE message is pinged too.
   - If `body-controller-state` fails and the range scan runs and misses, `ping` observes `bleReach False` (the F9 rule), which sets an `absent` mark. In `decide`, an `absent` newer than all home evidence demotes HOME to PRESUMED, or to NOT_HOME when an unplug is newer still.
   - For a plugged car beside the radio this should be rare, and it recovers: a TWC naming, a plug-in or contact re-establishes HOME, and a PRESUMED plugged car still gets SEND for a limit.
   - It is still a new path. If you want it closed, a scan miss on a car a TWC is naming now could be ignored for absence.
2. **A restore to a car marked away is not pre-flighted.** `quiet` excludes NOT_HOME, and most restores go to departed cars.
   - The reason: the parity stub's ping answers True for a departed car. Pinging there marked contact and flipped presence to HOME, which moved `test_no_gps_source_plug_unplug_cycle_end_to_end` and the paid count of `test_ble_plus_fleet_car_leaving_a_umc_is_restored_after_the_departure_read`.
   - Consequence: a restore to a car that is marked away but actually asleep in range still runs and fails. That repeats on the hourly `RESTORE_RETRY`, not the 5-minute pattern.
   - A HOME car's no-wake restore (`policy → no limit` while home) is pre-flighted.
3. **`drivingNow` masking.** A non-telemetry `state` ("online" from TeslaBLE or FleetAPI) newer than a telemetry `"driving"` makes `drivingNow` False when no `shiftState` exists. `decide` reads the gear directly when it is known, so only a feed that reports no gear is exposed. TeslaMate and Fleet Telemetry both report gear.
4. **On a BLE-only install, an awake but idle car shows no life.** With no TeslaMate, a car woken from the app that doesn't charge produces no sign of life. A held lowering waits for a plug event, current ≥ 1 A, or a message that may wake. This is the intended trade (no polling), and the car is likely asleep again within minutes anyway.
5. **A BLE wake is not observed as life.** Only a Fleet wake is. After a BLE raise wakes the car, a later lowering still sees the older "asleep" unless charging or current follows. Usually it does, because a start or raise leads to charging. If not, the lowering waits for the next sign of life.
6. **Stops are not pre-flighted.** They are excluded as the existing ping excludes them, and the brief's list does not name them. A BLE stop to a sleeping car still runs. A sleeping car is not charging, so the TWC-side state already stops the draw.
7. **The hold is logged through `report()`'s generic outcome line.** `inapplicable` holds use a dedicated `"<vin> <aspect>: hold (why)"` line; this hold has no such line.
8. **Only the asleep value was verified live.** `VEHICLE_SLEEP_STATUS_AWAKE` comes from the enum (the car was asleep). If the tool printed a different spelling, an awake car would observe nothing and the command would go ahead as before. That fails safe.

## Fix round 1 (commit cc97f3f7)

**Changes**

- **Critical 1: a raise held at 0 A now wakes once it is offered current.** In `plan`, the generic `lastObservedAt <= heldAt` gate stays at the top. The asleep gate moved below `wakes = wakes and not idle` and is now `if not wakes and last == O.ASLEEP and Presence.asleep(vehicle): return None`. `O.ASLEEP` is the new shared `Outcome(SATISFIED, HELD + "asleep")`, which Run also returns.
- **Important 2: any successful wake observes the car online.** `Run._wake(provider, vehicle, capability)` observes `state "online"` under the provider's name when the wake returns DONE. TeslaAPI's own wake observe is gone. The free online check still observes its answer (rule 6).
- **Important 3: a provider's state never hides a drive.** `drivingNow` reads `v.telemetryState()[0]`, the feed's own state, falling back to the newest state. A TeslaBLE or Fleet "online" therefore no longer masks a feed's "driving".
- **Important 4: a car seen awake lately skips the pre-flight.** `Presence.asleep(v, lately=NEVER)` now has three results:
  - True: the newest asleep reading is at least as new as every sign of life.
  - False: a sign of life is newer than that reading and newer than `lately`.
  - None: unknown.
  Run passes `lately = registry.now() - REACH_WINDOW` (300 s), and a quiet attempt pings only when the result is None. The bound matters: without it, a car seen awake once and never read asleep since would never be checked again, and that is exactly the original 5-minute spam case. PRESUMED cars are pinged as before, unless they are known asleep for a quiet message.
- **Minor 7: "offline" is ignored.** It counts as neither asleep nor life.
- **Minor 8: no KeyError.** `_noteSleep` uses `.get` and observes nothing for an unknown status.
- **Cuts taken.**
  - The signs of life are now: a state other than asleep or offline, the plugIn, unplug, driveStart and driveEnd marks, and actualCurrent >= 1. `_LIFE` is gone.
  - The `_noteSleep` comment is folded to one line.

**Tests**

- Adjusted:
  - The sign-of-life parametrization drops `("shiftState", "P")` and `("chargingState", "Charging")`, which are no longer signs of life.
  - The first test's second pre-flight count changes from 2 to 1: after TeslaMate says "online" the car is known awake, so no check runs.
- New tests:
  - `test_a_raise_held_at_0_a_wakes_once_offered`
  - `test_a_ble_wake_is_a_sign_of_life`
  - `test_a_charging_cars_lowering_needs_no_check`. A BLE amps message for a plugged car already may wake (`allowWake` is True for AMPS), so it is never quiet. This test therefore uses a limit lowering while a Gen2 reports 16 A.
  - `test_ble_contact_never_masks_a_feeds_drive`
  - `test_a_newer_offline_is_not_a_sign_of_life`
- The file now imports the parity module's autouse `quiet` fixture, so no test sleeps for real.
- RED/GREEN: against cc97f3f7's parent lib, 6 of the new or changed tests fail; with the fix, all 21 pass.
- Parity: scenario 13 is back to BASE (`b.pings == []`). TeslaMate's charging push is a plug-in, a fresh sign of life, so no pre-flight runs, and the round-0 edit to that row is reverted. **No parity row changes now.** `reconcile_helpers` still has the plumbing-only `ping` default.
- Covering tests: sleeping-car, parity, presence and limit-reconciler give 268 passed. `tests/unit` + `tests/EMS`: **2122 passed**. Black is clean.

**Lib delta against 6704fdb0**

- 26,217 → **26,259 (+42)**. `--shortstat`: 8 files, +59/−17.
- That is 12 over the accepted ~+30. The overrun comes from:
  - the three-way `asleep` and its recency bound (Important 4);
  - the shared `O.ASLEEP` constant (+3);
  - Run's `_wake` taking the vehicle.
- Cuts taken after the fixes:
  - comments trimmed;
  - `sleep()` merged into `asleep()`;
  - the plan gate down to one line.

**Remaining concerns**

- The two Minors you said to leave stand: a scan miss demoting HOME to PRESUMED (5), and stops and NOT_HOME restores not being pre-flighted (6).
- Signs of life are now narrower. A car that wakes only for a Gen3 or TeslaMate reading with no current, no state change and no gear change does not count as awake.
