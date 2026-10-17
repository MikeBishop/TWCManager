# Review 3: a78fe3d..8e04ca8 (unplug false positive + EVSE Fleet API cost)

Verdict: **ready with fixes**

Unit suite: 955 passed, 1 warning (3.8 s).

## Important

**I1. The Fleet EVSE exclusion has a reachable gap.** TeslaAPIController.py:50, :72-76
`_twcServedVINs` goes blind only when a VIN-less TWC has `reportedAmpsActual > 3`. Two cases get past it:
- The VIN is queried only after `isCharging` flips at `>= 1.0` A (TWCMaster.py:1210-1228). So `plugVIN` is None for a car that is plugged in but idle, after a restart or after any reported or suppressed unplug.
- `TeslaAPIEVSE.wantsToCharge` includes `"Stopped"` (TeslaAPIEVSE.py:70).

So a car plugged into a TWC that has no VIN yet still gets an EVSE, a power share, and a synchronous `setChargeRate` POST from `distributeEVSEPower` on the serial loop. This happens when the car is idle and Stopped (waiting on a schedule, solar or policy, at 0 A) and during the 1-3 A ramp at charge start. The dedupe only collapses an identical rate within 600 s. A fair share that keeps moving sends one POST per change. The live incident missed this only because the car was `Complete`.
Fix: go blind on `slave.isCharging` (the flag that triggers the VIN query), or on `reportedAmpsActual >= 1`, and on a VIN-less TWC whose `reportedState in PLUGGED_STATES`. One residual remains: the Gen2 steady 00 for an idle plugged car. Only telemetry `pluggedIn` covers it (for example, exclude a car telemetry says is plugged in while any VIN-less TWC exists). Add a test for each case.

**I2. The gated path is still synchronous on the serial loop, and the new timeout is longer than the slave timeout.** TeslaAPI.py:1438 (`timeout=30`), TeslaAPIEVSE.py:142, TWCManager.py:889
`distributeEVSEPower` runs on the RS485 main loop. It calls `TeslaAPIEVSE.setTargetPower`, then `requests.post(timeout=30)`, plus `time.sleep(5)` and a second POST for rates under 5 A. The slave timeout is 26 s (TWCManager.py:893). One slow POST can therefore get every TWC dropped and re-linked. The re-link runs `noteLinkReady`, which opens a 300 s window in which no unplug counts. progress.md already records a main-loop stall at charge start followed about 10 s later by a mid-run re-link. The blocking predates this batch, but the bound is new and it is too long.
Fix: set a timeout well under 26 s (for example 10 s). Better, hand the call to the vehicle worker as `TWCSlave._queueChargeRate` does (TWCSlave.py:293), since the queue's per-VIN key already coalesces repeats.

## Minor

- **M1** TeslaAPIController.py:78-80: a failed slave scan returns `(set(), False)`, so the cost guard fails open and every atHome car gets an EVSE. Returning `blind=True` would fail closed.
- **M2** TeslaAPI.py:1451-1460: on a rate under 5 A, the first send records the rate. If the `set_again` resend then fails, the TeslaPy#42 double send is skipped for 600 s.
- **M3** TeslaAPI.py:1407 (`int(charge_rate)`): the web debug path (TeslaAPI.py:137) passes the JSON `charge_rate` through. A string such as "16.5" now raises ValueError on that thread, where before it was sent.
- **M4** TeslaAPI.py:1416-1421: the window uses `time.time()`. A wall-clock step backwards extends the skip. `time.monotonic()` would be safer.
- **M5** TWCSlave.py:223-228 with VehiclePresence.py:732: when telemetry suppresses an unplug, the TWC side has already set `_unplugReported` and cleared `plugVIN`. Three consequences follow:
  - The car (still plugged in) loses its served-VIN exclusion. This feeds I1.
  - A later genuine 00 on that TWC, without a 60 s plugged hold first, is never reported.
  - The replug that follows can fire the I2 single-DEPARTING rule.
  The report lists these as accepted concerns, but the link to the EVSE exclusion is new.
- **M6** tests/unit/test_twcslave.py:796: `test_linkready_rearms_the_grace_in_the_master_loop` is a source grep, not a behaviour test. It is acceptable given the size of TWCManager.py's loop.
- **M7** MergedEVSE.py:145-160: a car a TWC serves no longer forms a MergedEVSE, so its `chargeRateControl == 2` API routing is dead code. TWCSlave.py:1063 still handles that mode, so this is a design consequence and not a bug. Worth a line in the PR text.

## Checks that hold

1. **TWCSlave** (TWCSlave.py:186-255): `_checkPlugState` adds only bookkeeping, no I/O.
   - The incident sequence (03 for 6 s after link, then 00) is unqualified at the 00's onset and is never reported.
   - The grace is judged at the onset, so a false unplug is not merely delayed until the grace ends.
   - A long 03 followed by 00 is still reported.
   - `noteLinkReady` during a 00 in progress sets `_unplugQualified=False` and so cancels that 00. This is conservative and correct.
   - `_unplugQualified` is recomputed at every 00 onset, so no state stays stuck.
   - The replug hold and the clearing of `plugVIN` on a second unplug are not gated, as intended.
   - The power-start evidence window (`_pluggedInAt`) is unchanged.
   - `reportedState` defaults to 0, so a fresh slave's first 00 heartbeat never starts an unplug. The test seeding matches.
   - Only the master-mode linkready branch needs the hook. The other `newSlave` sites (TWCManager.py:1665, 1816, 1843) are fake-slave paths that never call `receive_slave_heartbeat`.
2. **Telemetry plug path**:
   - `_reportPlug` is record-only on the MQTT thread and fires only on a bool-to-bool change.
   - `observeTelemetryPlug` takes the lock only to append.
   - `_pluggedInFor` runs outside the lock.
   - `_applyTelemetryUnplug` gates on `== HOME`, which correctly excludes ARRIVING and UNKNOWN cars.
   - It goes through `_applyUnplug`, which drops the car from `_timeoutHome` exactly as the TWC path does.
   - The replug only affects DEPARTING cars, and `_setState` clears every `_departing` set.
   - A stale but live `pluggedIn` True is an accepted concern (see unplug-fix-report.md).
3. **Other Fleet callers on the serial loop**:
   - `TWCSlave._queueChargeRate` goes through the vehicle worker.
   - `startCarsCharging` and `stopCarsCharging` queue background tasks.
   - `startAllCharging` and `stopAllCharging` have no callers.
   - `distributeEVSEPower` is the only synchronous path (see I1 and I2).
4. **setChargeRate dedupe**:
   - `int()` runs before the clamp.
   - A rate is recorded only when `result == True`, together with its time.
   - `set_again` bypasses the dedupe.
   - The window restarts on each resend.
   - The tests cover all of these.
5. **Tests**: they are meaningful. The run and grace tests fail on the old code, `test_a_relink_rearms_the_grace` would report without the hook, and the end-to-end tests drive a real TWCSlave into a real VehiclePresence. Gaps: there are no tests for I1's idle and ramp cases or for the fail-open scan.
