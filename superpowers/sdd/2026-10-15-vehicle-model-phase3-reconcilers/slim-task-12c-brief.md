# Slim Task 12c — Restart presence (added after the 2026-10-16 live failure)

Source of truth: live-fail-20261016.md (same directory). Read it first; it has file:line evidence and the proposed test.

## Problem
After a restart, a car that is plugged into a Gen2 and asleep is never present. `Targets._present` falls back to `api.atHome` (default False), which only plug or power edges set. TeslaMate's free position is never turned into atHome. So no policy limit is ever desired, and the Gen2 point has no vehicleKey (the TWC reports no VIN for a sleeping car), so no rate or start target either. On main/cfd0086 the car charged: limit 70, and a BLE rate command woke it.

## Requirements
1. Presence from free state on every policy pass. Recompute atHome from the latest known position (TeslaMate / telemetry / any free source already in the registry) using the same home geofence as `update_location`.
   - If no position is known, a car we hold a limit on (heldLimits) counts as present, matching the old behaviour.
   - Otherwise fall through to the BLE claim; never return False just because atHome is unset.
   - No new paid reads (vehicle_data $0.002, wake $0.02).
2. Departure by free position. On the policy pass, a held car that a free position places away gets its normal limit restored (the existing onDeparture/restore path; restores never wake). Don't wait for a power-drop edge. Keep the existing departure-check paid read for the case with no free position (as main).
3. A Gen2 with no VIN after a restart behaves as main does: the plugged-but-unidentified point is an anonymous plug session, so the existing anonymous fan-out rules (Task 12a I1, 12b I2/N1 `_anonCars`) reach the BLE car for rate, lift and start. That BLE command must be able to wake the car, as on main.
   - Check main's TWCSlave/TeslaBLE behaviour for status 00 vs 03 with a sleeping car, and match it.
   - No paid fan-out beyond the existing caps.
4. Regression test (the write-up's), and it must fail at BASE:
   - Setup: restart with the car plugged in and asleep; TWC VIN unknown; TeslaMate position at home; heldLimits {VIN: (100, 50)}; commandPolicy ble_only; BLE claim present; SOC 51.
   - Action: switch the policy to Scheduled (limit 70).
   - Expect: a CHARGE_LIMIT 70 desire, delivered over BLE, then the start. Zero vehicle_data, wake or command requests to Fleet/Owner.
   - Add a second test: free position away gives the normal limit restored, with no wake.
   - Add a third: no position plus a held limit counts as present.
5. Remove the tests' habit of setting `atHome = True` by hand wherever a test is about presence. At least one end-to-end test must derive presence from position.

## Constraints
- Lock order `_bleLock -> settingsLock -> registry leaf`, plus `vehicleListLock -> settingsLock`. No I/O under locks. No RS-485 I/O off the serial thread. Use `time.time` only.
- Gen3 must not regress.
- Keep lib growth small; reuse `update_location`'s geofence code rather than duplicating it. Report the lib delta.
- Deleted-test rule: map every deleted or weakened test.
