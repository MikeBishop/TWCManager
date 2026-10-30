# API-only soak fixes: review

Range a7f11121..3027a953 on vehicle-model/phase5 (wt-vm5). I read the diff and the code around it: TeslaAPI.wakeOutcome/onlineState/get_car_api, Belief, the Reconciler's plan/_asleepCheckDue/report, Run.runAttempt, Presence.asleep, Vehicle.observe, and the Gen2/Gen3 actualCurrent producers. I re-ran test_command_path_parity.py, test_sleeping_car.py and test_teslaapi_wake.py: 163 passed in 10.6 s. I did not re-run the full suite or the mutation checks.

## Verdicts

- **Spec compliance: PASS.** All three fixes do what the brief asks. The constants sit next to WAKE_RETRY_SECONDS, the cloud-worker comment is there, there is one commit per fix, the docs and CHANGELOG are updated, and every moved parity row is reported. No paid count moved.
- **Quality: APPROVE WITH FIXES.** One Important finding (fix 2 trusts a TWC current reading of any age). The rest are Minor.

## Questions asked

**Fix 1.**
- It runs on the cloud worker: Provider.wake → Run._wake → runAttempt is on the queue's thread. It is never on the tick or the serial thread.
- It is bounded by count: 9 polls of 5 s each. It is not bounded by time (see M1).
- There is no second wake_up and no vehicle_data. The poll goes only through onlineState, then get_car_api(vin, checkReady=False).
- `maxAge=0` does bypass the 120 s cache. With equal clocks, `now - onlineCheckedAt < 0` is never true.

**Fix 2.**
- A stop is unaffected. plan() passes `d.value`, which is False for a stop. ChargingPoint and VehicleEndpoint read AMPS, and CHARGE_LIMIT callers pass no desire.
- Another car on the same TWC: a wrong attribution can now override a real car reading (M3). It used to stand in only for an anonymous car.
- A stale reading is the real risk (I1).

**Fix 3.**
- An online answer re-plans once. The `state=online` observation makes Presence.asleep(v, heldAt) False. The next pass is not due, because checkedAt was just stamped, so it plans one attempt, and inFlight gates the rest.
- An asleep answer is quiet. report() returns early for a Job, and the `not wakes and last == ASLEEP and asleep` gate holds.
- The cadence holds only while lastOutcome is ASLEEP via a non-local provider. It uses HOME_ASLEEP_SECS or AWAY_ASLEEP_SECS, and it is measured from max(lastOutcomeAt, checkedAt).
- Lock order is fine. plan() does no I/O and only enqueues. The job's I/O runs on the cloud worker and takes only the registry leaf (observe). checkedAt is read and written only on the reconciler thread.

**The implementer's concern (BLE not retried at each recheck; the vanished-car row's free count 3 → 6): acceptable.**
- The hold rule is "re-plan only on a sign of life", and the old re-try of BLE was a side effect of the same bug.
- A cloud hold's BLE has already failed. Away from home, BLE cannot reach the car. At home, a car that wakes is seen by the free check or by a BLE advertisement, which is a sign of life.
- The new count is the documented 30-min away cadence over 3 h. The old count was lower only because each recheck re-ran the whole attempt.

## Critical

None.

## Important

**I1. A TWC current reading of any age can satisfy a start indefinitely.**
Where: lib/TWCManager/Vehicle/Reconcile/Belief.py:61 (`known`) and :31 (`_standIn` reads from `float("-inf")`).

Scenario:
1. A Fleet-only car with no feed charges on a Gen3. The Gen3's last vitals read 32 A at 21:00. Then its Wi-Fi drops: `_vitals_ok` goes false, and Gen3TWC.py:235 stops observing.
2. At 21:30 the owner stops the charge in the app. TWCManager's policy wants a start.
3. The car's last chargingState read (paid vehicle_data) was 20:00. The TWC's 32 A at 21:00 is newer, so `known(..., True)` returns "Charging".
4. `plan()` returns at `R.satisfied`. No start goes out until some car read newer than 21:00 arrives, and Fleet-only takes no read without a paid trigger. A Gen2 slave that stops heartbeating mid-charge, or a restart that restores registry observations, leaves the same frozen ≥1 A reading.

The only guard is "newer than the car's reading". That is weak exactly in the case this fix targets: no feed, so the car's reading is stale.

Fix: also require the TWC reading to be current. For example, `twc.at > max(obs.at, vehicle._clock() - TWC_FRESH)` with TWC_FRESH set to a few heartbeat or vitals periods (30–60 s), or reuse an existing freshness constant. Costs about +1 line. Add a test: a 48 A TWC reading, the clock advanced past the window with no new TWC reading, and the start goes.

## Minor

**M1. Fix 1 is bounded by count, not by time.**
Where: lib/TWCManager/Vehicle/TeslaAPI.py:1573-1577, with get_car_api at TeslaAPI.py:1790-1828.

Scenario: each poll's get_car_api makes up to 3 requests. It sleeps 5 s on `could_not_wake_buses` or on a transient error such as "vehicle unavailable" or "operation_timedout", which are plausible while a car is connecting. Nine polls can then take 9 × (5 + 10 + request time), which is minutes rather than about 45 s, and up to 27 GETs. Meanwhile the cloud worker is blocked: pending stops and rates for every car wait behind it. At shutdown, drain's ≤60 s deadline (TWCManager.py:296) can pass while a poll runs, and a pending Fleet stop is dropped.

Fix: replace the count with a deadline, e.g. `deadline = time.monotonic() + WAKE_POLL_SECONDS * WAKE_POLLS`, and stop when it passes. This is the same line count.

**M2. After a successful poll, onlineCheckedAt is stamped with the pre-wake time.**
Where: TeslaAPI.py:1584. `car.online, car.onlineCheckedAt = True, now` uses the `now` from before the wake. That overwrites the newer stamp the successful poll just set (`self.now()`, up to 45 s later). The cache then expires up to 45 s early, costing one extra free GET at most.

Fix: when a poll answered, skip the overwrite. For example, set `state = "online"` and leave the stamp, or stamp `self.now()`. Low value: take it only if it costs no lines.

**M3. A wrong attribution now overrides a real car reading, not only an anonymous one.**
Where: Belief.py:61.

The Gen3 vehicleKey is `registry.vehicleAt(pointId)` (Gen3TWC.py:290-293), which can be the correlation guess until the cloud VIN confirms it. All Gen2 units share the source name "Gen2TWC", so `reported("actualCurrent")` keeps one reading per source name, not one per unit.

Scenario: two cars and two Gen3s, with the attribution guess swapped. Car B draws 32 A on the point guessed to be car A's, so car A's start is "satisfied" and it never gets a start while B charges.

A preconditioning or Sentry draw of 1 A or more from shore power (chargingState not Charging) also suppresses a wanted start until the draw ends. That is likely, but I did not verify it on hardware.

Both cases only delay a start, and only for a start. Fix: accept it, but say in the comment that the reading must be the car's own TWC. Or skip the override while the point's attribution is unconfirmed (no twcVin observation), if that is cheap.

**M4. Pre-existing: a "wakes" desire held ASLEEP still re-plans and logs at each recheck.**
Where: Reconciler.py:334 (`if not wakes and last == O.ASLEEP and asleep`), together with Vehicle.observe bumping lastObservedAt on every observation (Vehicle.py:128).

Run.runAttempt (Run.py:190-194) also produces O.ASLEEP for a no-wake cloud attempt whose desire does wake:
- AMPS through Fleet ("billed provider never wakes for amps");
- a blind paid retry.

For these, `wakes` is True, so the gate does not apply. The onlineCheck's asleep observation, or any Gen2 heartbeat (`seen=False` still bumps lastObservedAt), passes the `waiting` gate, and the attempt re-runs and logs "held: asleep" again. Fix 3 neither causes nor worsens this; the old recheck did the same. I traced it in the code and did not reproduce it.

Fix (separate task): gate on `asleep` for any ASLEEP hold whose attempt could not wake, or gate `waiting` on a sign of life (`Presence.asleep(...) is False`) instead of on lastObservedAt.

**M5. Stale comments.**
- Run.py:39-41 (phase5 only): "BLE work ... in turn on the BLE worker" is now false, because onlineCheck runs on the cloud worker. Phase6 already rewrote this comment, so it resolves after the rebase.
- TeslaAPI.py:1734 still says "Don't check more often than every 2 minutes" above a maxAge-driven test. Suggested: "Not more often than maxAge (120 s by default)".

**M6. Docs and CHANGELOG are slightly narrow.**
- The CHANGELOG fix-1 line says "A Fleet API wake_up", but the polling also follows an Owner API wake (see the "2 free Owner wakes" parity rows).
- docs/modules/Vehicle_TeslaAPI.md says "asleep or offline" and leaves out "waking".

Fix: "A Tesla API wake_up"; add "waking".

**M7. A test gap for "a stop is unaffected".**
test_fleet_only_start_no_retry_while_the_twc_draws checks only `known(v, CHARGING)` with no desire. Nothing runs a stop desire while the TWC draws 48 A and the car's reading is stale "Stopped" to show that the stop still goes out. Fix: add a stop step to that test, or a short separate one.

## Lib growth (+28)

Each piece is roughly the minimum. Possible trims:
- onlineState's cache test grew from 1 line to 4 because black wrapped it (TeslaAPI.py:1735-1738). Naming the age, e.g. `age = now - car.onlineCheckedAt`, puts it back on one line or two (-2).
- The M1 deadline costs nothing extra if it replaces the `range` loop.
- `checkedAt` (one Desired field) and the `worker=` argument of submitJob both earn their place; phase6 already had the argument.
- The I1 fix should cost about one line.

Expect +26 to +29 net with I1 fixed.

## Count

Critical 0, Important 1, Minor 7.
