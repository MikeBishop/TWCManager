# Slim Task 12a review: charging on/off as stateless desired state

Reviewed: `d35a95c..c563d70` (f8b20ce, c563d70) in `scratchpad/wt-vm3`. Read-only. Line numbers are at c563d70 unless they say `main:`.

## Verdicts

- **(A) Spec compliance: PASS, with the two ruled gaps (concerns 1 and 2) still to fix.**
  - Every interface in the brief is implemented as written: `TWCMaster.py:196-203, 2027-2051`, `TWCSlave.py:491-604, 625-631, 1074-1076` and `Gen2TWCProvider.py:76-86`.
  - Every listed deletion happened, and nothing in lib, tests or docs still calls a deleted name. I grepped for `car_api_charge`, `car_api_available`, `stopAskingToStartCharging`, `findReason`, `_vehiclesFor`, `LastStartOrStopChargeTime`, `_unavailableResult`, `_listUnloaded`, `VEHICLE_COMMANDS` and the `"charge"` dispatch: the only hits are two CHANGELOG history lines.
  - `_allVehicleTargets` stays for 12b, per I1. It still has its one caller, `TeslaBLE.py:632`.
  - The full suite passes: **1666 passed, 1 xfailed**, which I re-ran.
- **(B) Quality and cost safety: NOT YET.**
  - 1 Critical: a start that never goes, and never wakes the car. This is concern 5, and it is worse than reported.
  - 4 Important: the two ruled concerns, plus two new ones (`minChargeLevel` silently lost, and paid starts repeated on every offer flap).
  - 5 Minor.

**Counts: Critical 1, Important 4, Minor 5.**

Every behaviour claim below was checked with a throwaway probe test, created and deleted inside the session. The tree is clean.

---

## Critical

### C1: an asleep Fleet car whose limit is not yet known never gets its limit, its start or a wake (concern 5, understated)

- **Evidence.**
  - `Run.runAttempt` reads before it writes (`Run.py:128-147`) with `allowWake=False`, and only then calls `beforeWrite` (`:148`). The wake comes after that (`:151`).
  - For a paid provider, an unknown current limit makes `decideChargeLimit` return `"could not read the current limit; nothing sent"` (`Rules.py:77-80`). `_tagged(..., "rules: ")` turns that into NOT_SENT.
  - So the `ride` wake that the limit attempt carries (`Reconciler.py:451`) is never reached.
  - Because the outcome is NOT_SENT, `paidSends` stays 0. `_limitSpent` (`Reconciler.py:482-503`) is therefore never True: nothing is excluded, there is no paid send or re-arm, and the detail is not in `_REFUSALS`.
  - The start gate (`Reconciler.py:426-436`) then holds the start for as long as the limit stays unread, which can be indefinitely.
- **Probes.**
  - Real TeslaAPI with requests_mock. The car is asleep and the wake hold is over. `setPolicyLimit(50)`, then a start, then 10 passes with `RETRY` and `MIN_SEND_GAP` set to 0. Result: one free `GET vehicles/{vin}`, no `wake_up`, no `vehicle_data`, no `set_charge_limit`, no `charge_start`. The limit's `lastOutcome` is `unreachable "rules: could not read the current limit; nothing sent"`.
  - Scripted Fleet, 2 h of heartbeat starts: 0 calls.
- **When it happens.** After any restart, a sleeping Fleet-only car with a policy charge limit has no `chargeLimit` reading. `updateChargeAtHome` does not wake the car. So that car is never woken to charge until it wakes by itself.
- **Main.** `car_api_available` woke the car, `applyChargeLimit` ran, and the start went.
- **Why the report missed it.** It describes a 300 s hold. In fact the hold re-arms after every 300 s retry.
- **BLE.** BLE is unaffected: a free provider sends when the limit is unknown.
- **Fix (preferred).** In `runAttempt`, when `attempt.wake` is set and the provider is paid, run the wake step before the read-before-write. The wake already does the free online check first, and it is the same wake the start would spend. A car that is still asleep then fails as `wake …`, which the existing bounds cover.
- **Backstop.** In `_limitSpent`, count a repeated `rules: could not read` as spent once its 300 s retry has also failed. c4's intent is that an undeliverable limit never blocks the start.
- **Test.** Add a paid-counted test with this exact requests_mock setup. It should assert one GET before `wake_up`, at most one `wake_up` and one `vehicle_data`, and POSTs equal to `[set_charge_limit, charge_start]`.

---

## Important

### I1 (concern 1, ruled): an anonymous Gen2 point gets no start or stop in mode 1, and no start in mode 3

- **Evidence.**
  - The heartbeat passes `anon:<twcid>` (`TWCSlave.py:493, 587, 597`, through `Gen2TWC.py:94-103`).
  - `targetsFor` returns only the anonymous car (`Targets.py:44-49`), and that car has no START/STOP candidate in mode 1.
  - Probe: "anon:8244 charging: no provider can deliver", and 0 Fleet calls for a stop.
- **What main targeted.** I checked `main:TWCMaster.py:1889-1922`, `main:TeslaAPI.py:728-868` and `main:TeslaBLE.py:201-261`.
  - **Mode 1 start:** `{"cmd":"charge","charge":True}` **with no VIN at all**, even when the TWC knew it. That reaches every car on TeslaAPI's list that is at home and passes the start checks: not Disconnected or Complete, below its limit, no pending schedule, and `stopAskingToStartCharging` not set. It also reaches every BLE-known VIN, through `_allVehicleTargets`.
  - **Mode 1 stop:** `vin=currentVIN`. When that is `""`, it broadcasts to the same set.
  - **Mode 3 start:** `vin=currentVIN`. When that is `""`, it also broadcasts.
  - **Modes 2 and 3 stop:** the bus, so all TWCs.
  - Main never excluded cars that another TWC was serving. The ruling's "no other point claims" is narrower than main, which is deliberate and an improvement. Main's mode-1 start broadcast for a *known* VIN is not restored here, which is also deliberate.
- **Fix.**
  - In `TWCMaster.startCarsCharging`/`stopCarsCharging` (`TWCMaster.py:2027-2051`): when the key is anonymous, fan out to `presentVehicles(self, cap)` minus anonymous cars and minus cars with a `twcVin` (cars claimed by a point). Do this for stops in mode 1, and for starts in modes 1 and 3.
  - Apply the same fan-out in `cancelStopCarsCharging` (`TWCMaster.py:196-203`) and in the zero-offer clear (`TWCSlave.py:599-604`). Otherwise the fanned-out cars keep a stale stop or start desire.
  - A single helper (`_decisionTargets(key, cap)`) keeps this at about 10 lines.
- **Test.** An anonymous Gen2 point in mode 1 with one Fleet car at home and one car claimed by another TWC. Exactly the at-home, unclaimed car gets one `charge_stop`.

### I2 (concern 2, ruled): mode 2 adds paid starts

- **Evidence.**
  - `CLOUD_SUPPRESSED = {..., "localStops": frozenset({STOP_CHARGING})}` (`Provider.py:9`) suppresses only stops. The `localStops` condition is set for modes 2 and 3 alike (`Suppressions.py:95-96`).
  - Probe: Fleet-only, `chargeStopMode=2`, then a start, sends `wake` and `startCharging` to Fleet.
  - On main, a mode-2 start was only `respondToSlaves = 1` (`main:TWCMaster.py:1896-1897`), which costs nothing.
  - Mode 3 on main did send `car_api_charge(True)`, so paid starts in mode 3 are main parity and must stay.
- **Fix.**
  - Add a mode-2-only condition in `Suppressions.conditions()` (for example `"silentStops"` when the mode is 2).
  - Map it in `CLOUD_SUPPRESSED` to `{START_CHARGING, STOP_CHARGING}`. HA and Fleet both use that table. BLE and Gen2 are local and unaffected, so a free BLE start stays allowed.
- **Test.** Mode 2 with a Fleet-only car stopped: a start makes no paid call. Mode 2 with BLE: the start goes through BLE.

### I3 (new): `minChargeLevel` is silently dropped, so a low-battery car is now stopped

- **Evidence.**
  - Main skipped stopping a car whose `batteryLevel < minChargeLevel` (`main:TeslaAPI.py:793`, and `d35a95c:TeslaAPI.py:857`).
  - This is a documented setting (`etc/twcmanager/config.json:134-139`: "the car will not be stopped from charging").
  - Its only use was in `car_api_charge`, which this task deletes. `TeslaAPI.minChargeLevel` (`TeslaAPI.py:149, 213`) and `HomeAssistant.minChargeLevel` (`:192`) are now dead attributes.
  - The plan, the brief and the report never mention it.
  - Probe: `minChargeLevel=50` and `batteryLevel=20`, then a stop, sends a Fleet `stopCharging`.
- **Main parity.** On main it applied wherever TeslaAPI carried the stop, which on a Fleet-only install is every time.
- **Fix.** About 4 lines in `handsOff` (`Reconciler.py:135-146`): for `CHARGING`/`False`, when `vehicle.value("batteryLevel")` is known and below `config.get("minChargeLevel", -1)`, return `"battery below minChargeLevel"`. This makes no new read. Delete the two dead attributes.
- **Test.** The probe above, inverted.

### I4 (new): the zero-offer clear resets the paid budget, so each offer flap buys another paid start

- **Evidence.**
  - `TWCSlave.py:599-604` calls `clearIf(key, CHARGING, True)` whenever the offer is below the minimum and the car is not drawing. It does this even when the start was **already delivered**. The brief says "a *pending* start is cleared".
  - The next heartbeat with the offer at or above the minimum calls `set(True)`, which is a new desire. `newDesire()` (`Desired.py:129-143`) zeroes `paidSends`, `settledAt` and `rearmed`.
  - So the per-desire bound (at most 4) restarts on every flap, and only `MIN_SEND_GAP` (10 s) spaces the sends.
- **Probe.** Fleet answers `SATISFIED "requested"` and the car stays Stopped. Over 30 offer flaps in an hour, the result is **30 `charge_start` and 30 wake steps**.
  - With the real Fleet, the wake is mostly the free check.
  - Each read-before-write older than 360 s adds a `vehicle_data`.
  - That is roughly $0.03/h in commands, plus reads, for as long as the offer hovers at the minimum.
- **Main.** Main sent at most one start a minute (the global 60 s gate). It stopped asking altogether after a `requested`, `charging` or `complete` answer, until a stop, a policy change or the car drew power.
- **Fix.**
  - Clear only a start not yet delivered: `rec.lastOutcome is None and rec.inFlight is None` (a `clearPending` on DesiredStore).
  - Or let `set()` keep the record when the same value is re-desired and no car reading is newer than its `settledAt`.
- **Test.** 30 flaps an hour with the car staying Stopped: at most one paid start per newer vehicle reading.

---

## Minor

- **M1 (concern 3): accept, and fix the comment.** A stop no longer resets `firstChargeNeededTime`, `firstWakeAttemptTime` and `delayNextWakeAttempt`.
  - The reconciler stops only a car that is drawing power, so that car is awake. The next wake request's free online check then calls `_wakeSettled` (`TeslaAPI.py:1415`), which resets all three. The 600 s backstop covers the rest.
  - The remaining effect is a delay. A failed wake's 30-minute hold can outlive a stop and a restart, which only saves money.
  - The comment at `TeslaAPI.py:1481-1486` ("The explicit end … belongs to the reconciler") describes wiring that does not exist. Reword it to say the free online check and the 600 s backstop are the ends.
- **M2 (concern 4): restore the token-state line cheaply.**
  - In `TeslaAPI.loadList` (`TeslaAPI.py:418-426`), when `slotFor("read")` is None, log the old INFO8 reason ("no Tesla API token yet", "token type unknown" or "paused") once per change of reason. That is about 8 lines, and it runs every 5 min through the `listPending` tick.
- **M3: a rejected TWC VIN blocks start and stop for the whole plug session.**
  - `Gen2TWC.vehicleKey` (`Gen2TWC.py:95-96`) returns `currentVIN` even when the registry rejected it (`observeTwcVin` "rejected"). `targetsFor` then returns `[]`, while the anonymous key, which is still registered, is never used.
  - Main sent BLE directly to that VIN.
  - Fix: fall through to the anonymous key when `registry.get(currentVIN)` is None and the pending state is rejected. Then I1's fan-out applies.
- **M4: a start to a car at or above its limit is no longer skipped** (`main:TeslaAPI.py:836-853`, #591). The car answers `complete`, which maps to SATISFIED, so this costs one $0.001 command per desire. A one-line `handsOff` check (`batteryLevel >= chargeLimit`, both known) would restore it.
- **M5: lib delta and orphans.**
  - `+82/−1059` (net −977) is honest. Nearly all of it is the deleted bodies: `car_api_available` 252, `car_api_charge`/`findReason`/`_unavailableResult` 352, TeslaBLE about 190, HA about 85.
  - Running a defs-without-callers scan over the touched modules found nothing newly orphaned except the `minChargeLevel` attributes (I3).
  - 12b's delete list must drop the extra items the report names.

---

## Checks that passed

- **C1 from pre-flight (the vehicle list loads).** The checks:
  - `checkCharge` at boot (`TWCManager.py:848`) runs `updateChargeAtHome`, which runs `loadList`.
  - The 5-minute tick queues `loadVehicleList` while `listPending()` (`TWCManager.py:1039-1043`).
  - `test_a_fleet_only_car_is_stopped_once_the_list_loads` passes: one free GET, then one `charge_stop` and no wake.
  - A Fleet-only car on a TWC is named by VIN, so `atHome` is not needed for it.
- **A free online check before any wake:** `wakeOutcome` (`TeslaAPI.py:1393-1421`), pinned by `test_fleet_wake_comes_after_a_free_online_check`.
- **A repeat stop waits for a newer reading, and stops are bounded and never wake.** Pinned by `test_an_app_start_after_our_stop_is_stopped_again_once_per_newer_reading`, `test_a_stop_that_keeps_failing_is_bounded` and `test_twc_current_alone_never_restops_a_car_with_vehicle_reads`.
- **respectVehicleSchedule:** `handsOff` (`Reconciler.py:141-145`). `test_fleet_only_car_with_a_pending_schedule_gets_no_start_or_wake` shows no wake and no start.
- **An app start or stop overridden each cycle.** Overriding at most once per newer reading matches main, where start or stop could repeat each minute. The flap case (I4) is the exception.
- **Mode 1 Policy hooks.** `clearOverride` and `stopTimeout`/`overrideLimit` are kept, and are now guarded for a missing Policy.
- **Modes 2 and 3 stops** go through Gen2TWCProvider (disruptive, after free BLE), as the plan intends.
  - Mode 3 sets `stopRequested`, and the heartbeat sends it on the serial thread (`TWCSlave.py:380-383`).
  - Mode 2's `stopRespondingToSlaves` writes under `settingsLock`.
- **Threading.**
  - The heartbeat adds only `registry.get` + `observe` (leaf lock), `desired.set/clearIf` (the store lock, with the notify outside it) and `queue.remove` (the queue's condition). None of these runs I/O, and none nests inside another lock.
  - `Gen2TWCProvider.startCharging` takes `settingsLock` alone, on the reconciler thread.
  - No new `vehicleListLock` or `_bleLock` path.
  - `loadVehicleList` still holds `vehicleListLock` across its GET. That predates this task and is unchanged.
- **No RS-485 I/O off the serial thread.**
