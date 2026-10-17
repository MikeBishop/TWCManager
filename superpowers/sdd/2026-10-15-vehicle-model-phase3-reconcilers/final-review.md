# Final whole-branch review: vehicle-model Phase 3 (6a6c14e..fc6eba7)

Reviewer: Opus, read-only. HEAD fc6eba7; the tree was left clean. Probes ran from the scratchpad (`frprobe/`), reused the parity harness (real TWCMaster, TeslaAPI, TeslaBLE and Gen2 heartbeat on a test clock), and were deleted afterwards.

Suite: `1764 passed, 1 xfailed, 1 warning in 83.86s`.

## Verdict

**Ready for the live check: yes.**

I traced the box configuration end to end through the real code and probed it. The box is a Gen2 in mode 1, ble_only, TeslaMate, a BLE-paired Model 3, Owner and Fleet tokens, and Scheduled 70 / non-scheduled 50. Every step goes over BLE with zero HTTP requests:

- After a restart with the car plugged in and asleep, the 00:00 limit raise goes out, then the amps lift, then the start.
- At 05:00 the lower and the stop go out.
- On departure the restore goes out, hourly while the car is out of range.
- On return, nothing is re-sent.

Both Important findings are merge items, not live-check blockers. I1 is in chargeRateControl 2/3, which the box does not use; I2 is size.

**Counts:** Critical 0, Important 2, Minor 13.

## Critical

None.

## Important

### I1. Mode 2 (and mode 3 below the floor): a car rate that failed twice is not re-sent after the transport recovers, while the TWC offers its maximum. This is a sustained overshoot of the distributor's target.

A rate that failed twice waits for the next live reading, which re-arms it only once per desire. A fault that outlasts both pairs of sends leaves the overshoot for good. This is a merge blocker under the wiring rule, not a live blocker: the box runs mode 1.

**Evidence:**
- In `EVSEInstance/ChargingPoint.py:191-196`, when the car carries the rate, the TWC offers `local.maxPower` in mode 2, or the floor in mode 3, and the car's AMPS desire is the only limit.
- `Reconcile/Reconciler.py:318-341` caps paid sends at 2 per arm. It re-arms only on `reachedCar` (a newer live reading, or a changed value), on a charging reading, or on a new desired value.

**Probe (mode 2, Fleet-only):**
- Setup: target 10 A; the Fleet script answers 500, then 500, then 200.
- Result: `amps sent [10, 10]`, then nothing for the rest of the hour. The TWC offers 32 A against a 10 A target.

**Failure scenario:**
- A steady budget (for example, `wiringMaxAmpsAllTWCs` shared by two TWCs, or a fixed grid budget) holds the desired amps at one value.
- A 2-minute Fleet outage or 500 burst fails both sends.
- The car keeps drawing up to the TWC's own max until something changes the desired value or produces a qualifying reading. On a Fleet-only install, that reading is the 30-minute checkCharge, and it re-arms only once per desire.
- Main also overshot during the outage, but it healed within about 21 s of recovery. Phase 3 does not heal.
- The per-TWC circuit is never exceeded, because the offer is bounded by `wiringMaxAmpsPerTWC`. The shared feeder and any total budget can be exceeded.
- The ledger's 12b M3 and Task 14 rulings covered the paid count only, not this wiring consequence.

**Fix (free, and keeps the paid bound):**
- In `ChargingPoint.setTargetPower`'s car-carries branch, have the TWC offer `max(floor, target)` instead of `maxPower` whenever the car's AMPS desire for that key is not settled at the current value (`desired.settled(key, AMPS)` is False, or its record is spent).
- The TWC then carries the rate until the car rate lands. This is the mode-3 layering, extended to the failure case.
- Test: the probe above, asserting that `s._evseTargetAmps == 10` after the second failure.

### I2. Size: lib is 622 lines over the 26,750 target, against the roughly 250 the user accepted (ledger line 116).

**Evidence:**
- Measured by `wc -l` on `lib/**/*.py`: HEAD 27,372, origin/main 23,180. Templates are excluded.
- Tasks 12c and the row-26 fix added 78 lines after the acceptance.

This is not a live-check blocker; it is a merge-readiness item under the "rearchitecture must shrink" rule. Concrete duplication left, about 300 lines in total:

| # | Where | What | Est. |
|---|---|---|---|
| 1 | `Reconcile/HeldLimits.py:51-72, 100-236`; `TeslaAPI.py:498-504, 530-546` | The one-shot legacy migration: `_legacyEntry`, `_waiting`/`_loadedVins`/`resolveLegacyIds`, the dev-build `"id:"` keys, and `listPending`/`resolveHeldLimits`. The `"id:"` handling (never released) can go with no decision. The rest needs a user decision: resolve once at the first list and drop the deferral | 120-150 (10 free) |
| 2 | `TeslaAPI.py:1840-1860` (`update_location` vs `locate`), `:1913`, `:1499-1537`; `HomeAssistant.py:168-172`; `Targets.py:120-145, 163-170`; `Gen3TWC.py:282`; `VehicleEndpoints.py:120` | "Is this car home" is computed about six ways. Make it one `atHome(vehicle)` in Targets, with `locate()` as its only TeslaAPI input. Partly Phase 5 work | ~40 |
| 3 | `EVSEInstance.py:120-127`, `Gen2TWC.py:232-236`, `VehicleEndpoint.py:156-160`, `ChargingPoint.py:198-212` | `startCharging`/`stopCharging` on EVSEInstance have no caller since Phase 3. Only `Gen3TWCProvider` calls the Gen3 unit's pair; inline those as `setUnitTarget` | ~35-40 |
| 4 | `TWCMaster.checkModuleCapability` (:276), `TWCMaster.time_now` (:2042), `TWCManager.time_now` (:250), `TeslaAPI.numCarsAtHome` (:1540), `HomeAssistant.numCarsAtHome`/`minBatteryLevelAtHome` (:585-598), `getSetting`/`setSetting` (test-only) | Dead or test-only. The ledger kept `numCarsAtHome`/`minBatteryLevelAtHome` for user policies (`modules.X.Y`): keep TeslaAPI's and drop HA's only if Policy never reaches it | ~40-60 |
| 5 | `VehicleRegistry.py:70-73`, `VehicleEndpoints.py:16-18`, `WallConnectorVins.py:25-26`, `ChargingPoint.py:212-216`, `Gen2TWCProvider.py:43-48`, `TWCSlave.py:145`, `TWCMaster.py:1326` | The anon-key and canonical-key tests are written seven times. Add `isAnonKey`/`canonicalKey` to `Registry/VIN.py` | ~15 |
| 6 | `int(settings.get("chargeStopMode"/"chargeRateControl", 1))` at `Gen2TWCProvider.py:54,57`, `ChargingPoint.py:150,204`, `Suppressions.py:91`, `TWCMaster.py:209,2017,2028` | Replace with one accessor pair on the master | ~10 |
| 7 | `Reconciler.py:67` and `:73` vs `CarApiVehicle.READ_MAX_AGE`; `Provider.commandMethod` (identity function); `Gen3TWCProvider.py:61-81` (the unit-is-None guard written three times); `TeslaAPI` `getVehicleCount`/`getCarApiVehicles`/`updateSettings`/`lastVehicleStatusTime` | Small duplicates and stubs | ~25 |
| 8 | `HomeAssistant.py:121-145` | Three copies of the float-parse try/except | ~10 |

Even all of these leaves about 27,070 (+320). The rest is structural: Reconcile, Providers, Registry, and the `CarApiVehicle` bridge (`RegistryField`, `_bind`, `_readFresh`). Phase 3.5 (dissolve `CarApiVehicle`) is the planned closer.

**Fix:** do items 3, 4 (non-policy), 5, 6, 7, 8 and the free part of item 1 now, about 140 lines with no behaviour change. Take the rest of item 1 to the user.

## Minor

**M1. Mode-2 stop can be silently undone.**
- Evidence: `TWCMaster.py:2036-2040` writes `respondToSlaves=0` before `respondToSlavesExpiry` under settingsLock. `TWCSlave.py:433-444` reads both without the lock on the serial thread.
- This is new on this branch: the stop now runs on the reconciler thread, not the serial thread.
- Scenario: the heartbeat runs between the two writes, sees 0 with the old (past) expiry, and resets `respondToSlaves=1`. The stop is reported as DONE "respond", the record settles, and nothing re-sends until a newer reading and 60 s.
- Fix: write the expiry first (two lines swapped).

**M2. A stop can escape `cancelStopCarsCharging` between plan and submit.**
- Evidence: `Reconciler.py:389` sets `inFlight` in `plan()`, and the submit comes later at `:199`. `Run.py:133` exempts stops from the stale-desire check.
- Scenario: the serial thread's cancel (`TWCSlave.py:629`/`:1106` → `TWCMaster.py:195-196`) lands in the gap. There is no queue entry yet to cancel, so the stop goes out anyway: an unwanted stop, possibly paid ($0.001), or 60 s of silence in mode 2.
- Fix: in `runAttempt`, drop a stop whose CHARGING desire is no longer False and was cleared after `attempt.since`.

**M3. A dead queue worker makes the reconciler spin hot.**
- Evidence: `VehicleCommandQueue.py:95-99` → `Reconciler.py:115` → `report()` → `wake()`. "dropped" is in QUEUE_DETAILS and sets no hold (`Desired.py:327-329`).
- Scenario: a BaseException in a provider. No vehicle path raises one today; the only `sys.exit` in lib is `EMS/DSMR.py:38`. From then on there is a 100% CPU plan/submit/drop loop that competes with the serial thread. Pending entries at the time of death keep `inFlight` set until shutdown.
- Also: `Reconciler.run` (`:169-172`) catches only Exception, so the default excepthook would print a BaseException's text.
- Fix:
  - report a dead-worker loss with a held NOT_SENT detail outside QUEUE_DETAILS;
  - `_lose` the pending entries in `_run`'s `finally`;
  - catch BaseException in `Reconciler.run` and log the type only.

**M4. Arrival races the policy.**
- Evidence: `onArrival` (`Targets.py:215-217`, background thread) reads `master.policyLimit`, then sets a desire as a decision. `setPolicyLimit` runs on the policy thread.
- Scenario: a stale limit lands after a newer one. It is corrected at the next policy pass, but a paid send can happen in between.
- Fix: route the arrival through the policy thread, or read `policyLimit` and set it under one small lock.

**M5. A stop that is desired but held by MIN_SEND_GAP/RETRY at SIGTERM is never queued.**
- Evidence: `reconciler.stop()` runs before `drain()` (`TWCManager.py:2043-2045`).
- Fix: run one final `pass_()` before `drain()`.

**M6. Unlocked record writes in `plan()` race `newDesire()`.**
- Evidence: `plan()` writes `rearmed`, `paidSends`, `paidRetryDue` and `paidSaw` at `Reconciler.py:334-345` without the store lock. `DesiredStore.set` can call `newDesire()` concurrently from the serial or policy thread.
- Effect: a new desire can inherit `rearmed=True`, so it gets one fewer paid retry. The error is toward fewer paid calls, never more.
- Fix: move the re-arm into a DesiredStore method, or document it.

**M7. BLE raw output is logged at DEBUG.**
- Evidence: `TeslaBLE.py:381`, `:499` and `:515-519` log `output[:200]` from tesla-control, which runs with `-debug` and `-key-file`.
- No key material appears in that output today. A future tesla-control version that prints session or key diagnostics would put them in the log.
- Fix: log `_errorCategory(output)` and the output length only.

**M8. BLE and HA exception text in logs.**
- Evidence: `TeslaBLE.py:387, 524, 596, 839, 909, 936` log `{e}` near private-key handling. They are theoretically safe: today's exceptions carry no key bytes.
- `HomeAssistant.py:229, 239, 257, 264, 335, 339, 511, 514` log the URL and `str(e)`. A user-configured URL with userinfo or a query token would be logged at INFO or ERROR.
- Fix: type names, plus `urlsplit(url).hostname`.

**M9. Pre-existing catch-alls log the full text.**
- Evidence: `TWCManager.py:388` and `:2016-2017`, and `Policy.py:195`/`:202`, log `format_exc()` and `{e}`.
- Nothing token-bearing raises through them today; they are a latent route.
- Fix: frame-only traces for background tasks.

**M10. Anonymous-session fan-out reaches BLE-keyed cars wherever they are (main parity, ruled 12a I1).**
- Since 12c an anonymous session also begins at status 03 with no current (`TWCMaster.py:1315-1323`).
- So a guest car (or a non-Tesla) plugged in, not drawing, fans the heartbeat start out to every BLE-keyed car (`Targets.py:159-177`; `reached` accepts a BLE claim regardless of position). Main did this too, through its unaddressed `car_api_charge`.
- Cost: BLE wake+start to a car that is away, every 60 s until a reading puts it hands-off; this occupies the single BLE worker. On a Fleet install, it costs one wake+read+start (about $0.023) per guest session before "Disconnected" puts it hands-off.
- Fix (optional, after the live check): in `reached`, require `located(v) is not False` for BLE-only cars too.

**M11. Adoption window.**
- `_adoptable` (`Reconciler.py:224-234`) adopts any vehicle reading newer than our write that disagrees with it.
- Retained MQTT redeliveries are already stamped at or before our write (`Telemetry.py:253-273`), which is good.
- A TeslaMate poll that read the old 50 just before a BLE `charging-set-limit 70` and published it just after would be adopted. That would cancel the overnight raise until the next decision.
- TeslaMate publishes on change only, so it would not republish an unchanged 50. Unlikely; watch for "charge limit set elsewhere … adopted" at 00:00 in the live log.
- Fix if seen: require the disagreeing reading to be at least N seconds after the write (TeslaMate's poll period).

**M12. Restore retries over BLE while the car is away (scenario c).**
- Each hourly restore over BLE is a wake-less `charging-set-limit` plus its quick retry: 2 runs per hour, each holding the BLE worker for up to the command timeout.
- Free, and by design (Q3). Noted because the timeouts delay any other BLE work queued behind them.
- Fix: none needed. Optionally skip a BLE attempt while BLE's own presence (an RSSI scan) says the car is not in range.

**M13. Wording in the ledger and docs.**
- `Reconciler.py:67` says "one table, two names" (`PAID_AFTER = RETRY`), while the rulings talk about them as separate knobs. Pick one name.

## Cross-task interactions checked

- **12c presence vs 11 held limits vs 10 re-arm.**
  - `_present` (`Targets.py:129-145`) prefers the free position (`locate()`), then "held or atHome" when no position is known, then HA, then the BLE claim.
  - A held car with no position therefore stays present forever. This matches main's wasAtHome and is ruled.
  - Departure is detected on every policy pass (`applyPolicyLimit` → `_restoreDeparted(read=False)`) and is age-guarded against our own write.
  - The re-arm rules see only newer per-source readings (`Belief._newer`), so a TeslaMate position republish never re-arms a limit. Consistent.
  - Probe: departure → restore desire → BLE hourly; return → the policy's 50 replaces the restore; the car is still at 50, so nothing is sent. The held record stays (100, 50). Correct.
- **12a/12b fan-out vs 12c anonymous sessions.**
  - The fan-out is unchanged. 12c only widens when an anonymous session exists (status 03 or 00 plus a free plugged-in reading).
  - The anonymous key's own desires are dropped at the VIN merge, and the fan-out wrote its desires on the VIN key, so nothing is lost at the merge.
  - In the probe the session stays anonymous for an hour of 32 A charging (no VIN task in the harness). The start, lift and 05:00 stop still route to the VIN.
  - See M10 for the guest-car case.
- **13b read cascade vs reachedCar.**
  - The TeslaAPI status deferral returns True without an observation (`TeslaAPIProviders.py:157-160`), so it never re-arms.
  - Owner and Fleet reads both observe as "TeslaAPI", which `LIVE_READ_SOURCES` counts. So a free Owner read of an awake car can re-arm a paid limit once per desire. That is correct, because the car is awake.
  - Attempt reads are restricted to the attempt's own worker (`Run.py:155-167`), so a BLE attempt never triggers a cloud read.
- **13c request helper vs outcome classes.**
  - A transport error gives ERROR with the type name; it is counted as a paid send, which is conservative.
  - A failed refresh gives UNREACHABLE "token refresh", also counted.
  - A 403 wake gives UNREACHABLE "wake refused" (NOT_SENT), and the slot then refuses wakes, so it cannot repeat.
  - 429 sets the backoff, and the next command returns "backoff" (NOT_SENT and held for RETRY).
  - 408 gives UNREACHABLE, which allows one blind retry.
  - No class lets a paid request repeat without bound. `get_car_api` sends up to 3 GETs per read, so one Fleet read costs at most $0.006.
- **Row 26 (fc6eba7) vs the battery-at-limit hands-off vs minChargeLevel.**
  - `uncompleted()` turns "Complete" into "Stopped" only when the reading is no newer than our last limit write and the SoC is below that write. A lowering write therefore never re-opens a start (51 < 50 is false).
  - A fresh "Complete" after the raise still satisfies the start.
  - The hands-off check now compares SoC with the believed limit (our write until a newer reading). After the 05:00 lower to 50 at SoC 69, the start is hands-off, which is correct.
  - minChargeLevel gates only stops (`Belief.py:84-88`) and is untouched by the change.
  - If the car does not start after the BLE start, the own-write stamp ("Charging") settles it, and it is re-tried only on a newer reading. That is bounded, BLE-only and free.

## Concurrency

The documented order is `_bleLock → settingsLock → registry leaf` and `vehicleListLock → settingsLock`. No path inverts it.

- DesiredStore, VehicleCommandQueue `_cond`, the registry and FieldStore locks are leaves. Callbacks (`changed`, `report`, `lost`, `removed`) run outside them.
- The branch adds no RS-485 I/O off the serial thread. It removes two: mode-2 and mode-3 stops are now published, as `respondToSlaves` and `stopRequested`.
- `vehicleListLock` is held across HTTP (up to about 20-40 s), but only on the background and telemetry threads, never on the main loop or HTTP threads.
- Shutdown has one monotonic deadline and no joins; it cannot hang.
- See M1-M6 for the races found.

## Security

No token, refresh token, client secret, Authorization header or HA token reaches any log at any level on the new paths.

- `_request` and `_classify` log status, method, path and kind only.
- Exceptions on the new paths are logged by type name.
- Tracebacks are logged as frames only.

M7-M9 are latent or pre-existing.

## End-to-end traces and paid-call bounds

Prices: vehicle_data $0.002, wake $0.02, command $0.001. "Measured" figures come from the probe on the real stack.

**(a) Box overnight, after a restart with the car plugged in and asleep.**
- Trace:
  - The Gen2 reports 03 with no VIN, so `num_cars_charging_now` begins `anon:8244`.
  - At 00:00, `setPolicyLimit(70, True)` → `presentVehicles` (TeslaMate position home, via `locate()`) → desire 70.
  - The plan picks BLE (Fleet commands are suppressed under ble_only) with a wake, because 70 > 50. The read is BLE-only and `decideChargeLimit` gives send 70, saving (100, 70).
  - The heartbeat lift goes to the VIN through `_anonCars` (TeslaMate shows it plugged in): BLE `charging-set-amps 32`.
  - The heartbeat start goes to the VIN through the mode-1 fan-out. `uncompleted` turns the stale "Complete" into "Stopped", and the start waits for the limit write, then goes out as BLE wake+start.
  - At 05:00, limit 50 (no wake) and the heartbeat stop go out over BLE.
- Measured: BLE `wake, set-limit 70, wake, set-amps 32, wake, start` to start; then `set-limit 50, stop` at 05:00; 0 HTTP.
- **Bound: $0/h.** Worst case is about $0.012/h, and only if the Owner slot becomes unusable: reads fall back to Fleet through the 30-minute checkCharge, at up to 3 GETs each, and only for an awake car.

**(b) Evening arrival and plug-in.**
- Trace:
  - The power edge queues checkArrival → `onArrival` → `applyPolicyLimit(policyLimit, decision)`. The TeslaMate position makes the car present. The car is already at the held 50, so the limit is satisfied and nothing is sent.
  - `updateChargeAtHome` reads through Owner, which is free.
  - In mode 1 the lift goes out once per session over BLE.
  - The start or stop follows the policy offer over BLE.
- **Bound: $0/h.** Worst case is about $0.006 per arrival, if the Owner slot is unusable (one Fleet read of an awake car).

**(c) Departure and restore.**
- Trace:
  - The unplug ends the session (twcVin cleared).
  - The policy pass, or checkDeparture at 5/20/45 min, sees a TeslaMate fix that is away and newer than our write, and sets the restore desire 100. No reads happen, because syncSource is TeslaMate.
  - BLE `charging-set-limit 100` without a wake; out of range, it is retried hourly.
  - On return, the policy's 50 replaces the restore. The car is still at 50, so nothing is sent.
- Measured: 0 HTTP; 6 BLE runs in 3 hours.
- **Bound: $0/h** on the box.
- Under prefer_ble with Fleet: at most 2 commands, never a wake, $0.002 per departure.
- Fleet-only without telemetry: plus 3 checkDeparture reads, at most about $0.02 per departure.

**(d) BLE down for 10 minutes under prefer_ble (Owner and Fleet, car awake).**
- Trace:
  - BLE fails, with its quick retry, and the free channel starts failing.
  - Fleet takes the stop at 60 s, the limit at 300 s and the start, each once. There is no wake, because the free online check says the car is online. Reads go through Owner, which is free.
- Measured: `charge_stop, set_charge_limit, charge_start`, $0.003.
- **Bound: $0.003/h** expected.
- Worst case, with the car asleep, a raise plus a start, and every send failing with a re-arm: about $0.09/h (at most 4 wakes and about 12 commands). Each desire is capped at 4 sends, and wakes go only with a raise or a start.

**(e) Green-energy fluctuation for 1 hour (mode 1).**
- The amps stay on the TWC, which is free. Start and stop follow the offer, at most one flip per `startStopDelay` (60 s).
- Measured with BLE up (15 flips): 22 BLE runs, $0.
- **Bound with BLE: $0/h.**
- Fleet-only measured: $0.016/h with the car awake, and $0.156/h when the car sleeps after each stop (7 wakes).
- Fleet-only bound: at most 30 starts of (wake + read + command) plus 30 stops, about $0.72/h. This is main parity: main woke for starts too.

**(f) Fleet-only install, steady state.**
- A raise costs $0.023 per desire (row 4: free check, wake, vehicle_data, command). A lower costs $0.001-$0.003.
- checkCharge adds at most 2 vehicle_data reads per hour, only while the car is awake.
- **Bound: about $0.03/h plus about $0.023 per raise**, plus (e) if green tracking flips.
- I1 applies only if mode 2/3 is used.

**(g) Gen3 install with 2 units.**
- Amps go through the headroom solver (row 29, no overshoot). Start is local. The cloud VIN uses products and live_status, which are free.
- With both units occupied, a stop is NO_INDIVIDUAL_STOP, so it goes over BLE (free) or Fleet: at most 2 commands, no wake, and a free "asleep, not charging" check first.
- **Bound: $0/h with BLE.** Without BLE, at most $0.002 per stop desire, so at most about $0.06/h with 60 s flips.

**(h) HA-only install.**
- There are no Tesla Fleet requests from TWCManager. HA is billed tier with an unknown price, has no free channel and cannot wake.
- Each desire gets at most 2 service calls, plus 2 after a changed-value reading, so at most 4. Green flips cost 1 call each.
- **Bound: typically 1-2 HA calls/h; at most about 60 HA calls/h** with 60 s flips.
- This is a behaviour change from main, which never reached HA (row 16, ruled; flag it to the user).

## Notes for the live check

- Watch for `adopted` lines around 00:00 (M11), and for `hands off:` lines on the start.
- The start should follow the limit within about 5-65 s.
- The box is mode 1, so I1 does not bear on it. Confirm `chargeRateControl` is 1 before deploying.
