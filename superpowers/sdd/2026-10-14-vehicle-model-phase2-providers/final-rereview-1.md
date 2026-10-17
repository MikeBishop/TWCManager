# Final re-review 1: Phase 2 fix wave (b72c79c..8bdb9a6, 11 commits)

Scope: the final-review.md findings (C1 plus the audit, I1, M1-M3, the
deferred fix-now items) and the coordinator's four questions. Method: read the
whole lib diff and the fix report; re-read the real `TeslaAPI` return paths;
ran the 16 focused test files (256 passed); ran a new real-object wire sweep
(`scratchpad/final2-scratch/wire_sweep.py`, 14,760 cases, real
`TWCMaster.distributeEVSEPower` + real `TWCSlave.receive_slave_heartbeat` /
`send_master_heartbeat`, 2-3 TWCs, 8 rounds each) on both 8bdb9a6 and an
archived b72c79c, plus a round-by-round trace of the waking-cars case
(`wake_case.py`). Full suite not run here.

## 1. C1 and the two C1-class audit fixes: closed

- `TeslaAPI.applyChargeLimit` now ends with `return "success"`
  (TeslaAPI.py:1258-1260); the 60 s throttle returns `"skipped"`; the
  `car_api_available` False case returns `_unavailableResult()` which is
  `"skipped"` only while a command slot, a read slot and a vehicle list exist
  and no error backoff is running, i.e. exactly the wake holds. I read every
  `return False` in `car_api_available` (406-520): the error backoff is
  covered by `getCarApiRetryRemaining()`, no-token and no-list by the slot
  and count checks, so nothing that is a real failure is mislabelled a skip.
- `car_api_charge`: the once-a-minute throttle returns `"skipped"`, the
  unavailable path `_unavailableResult()`, the success path still
  `return result` (`"success"`, TeslaAPI.py:1058).
- `TeslaAPI.updateChargeAtHome` returns `bool(carApiVehicles)`,
  `HomeAssistant.updateChargeAtHome` returns True.
- The audit table in final-fix-report.md matches my own reading of every
  façade-walked method on TeslaBLE, TeslaAPI and HomeAssistant. The one
  deliberate leave (a rejected `setChargeRate` returns a truthy dict) is
  correct: making it falsy would add a second paid Fleet attempt and then
  reach HA, which is more spend than 8e07669.
- Probe: `tests/unit/test_vehicle_priority_returns.py` drives the real
  `TeslaAPI` module behind the real façade with `requests_mock` asserting no
  HTTP; after a Fleet success, a throttle skip or a wake hold, HA is not
  called for `applyChargeLimit`, `car_api_charge` or `updateChargeAtHome`;
  `setChargeRate` success is a dict/True and ends the walk by construction.
  A real Fleet failure (error backoff) still falls to HA, now held to
  `FALLBACK_INTERVAL` 60 s per (provider, capability, VIN) under a small
  lock with no I/O (VehiclePriority.py:67-76,224-238,285-293). HA-only and
  BLE-then-HA walks never enter fallback mode, so their cadence is unchanged.
- No new paid call versus 8e07669 remains on any install shape I traced.

## 2. Wire-sum check (implementer's concern 4): not Critical

What the sweep shows, identically on b72c79c and 8bdb9a6:

- The sum of **wire offers** can exceed `min(budget, wiringMaxAmpsAllTWCs)`
  on both trees (7,545 of 14,760 cases before the fix, 7,867 after). Every
  excess comes from pre-existing `TWCSlave` rules: the "always offer at least
  `minAmpsTWCSupports`" exception in `set_last_amps_offered`
  (TWCSlave.py:1160-1167), the heartbeat's `numCarsCharging > 0` raise of a
  0 target to 6 A (TWCSlave.py:782-806, Task 11 m2), and the 6 A-limit spike
  (`spikeAmpsToCancel6ALimit`). The legacy per-slave path offered idle TWCs
  their full fair share, so these offers are within what main has always put
  on the wire.
- The per-TWC guard holds on both trees: each offer is clamped so that
  `(total actual draw − this TWC's draw) + this offer ≤ wiringMaxAmpsAllTWCs`.
  In the waking-cars trace (40 A feed, 80 A budget, one car at 32 A, two
  sleeping cars that wake and draw up to 12 A each): targets 32/12/12 → wire
  32/8/8 (clamped to the 8 A of headroom each), the plugged TWCs' echo makes
  them "want", the distributor re-shares to 13.3 each **before** they draw,
  and the **actual draw never exceeds 37 A**, same as b72c79c (where the
  idle targets were 6/6 and the wire 32/6/6). With a 40 A budget the I1 code
  gives the idle TWCs a 0 target (remaining 8 A < 12 A) and the heartbeat
  puts 6 A on the wire, exactly as before.
- Actual draw exceeding wiring never happened in the sweep except in cases
  I seeded above wiring (three cars already drawing 32 A each), which the
  code then reduces; those are artefacts of the seed, not of the change.

What I1 changes: the distributor's idle reservation is 12 A instead of 6 A
per idle TWC under the default config when the **policy** budget has room.
That reservation ignores the controller (wiring) budget: the idle loop
(TWCMaster.py:613-625) checks `remaining_watts` only, so distributor targets
can sum to 56 A on a 40 A feed (new) where they summed to 44 A (old). The
wire guard turns that into 32/8/8 offers and the draw stays inside wiring, so
this is accounting, not an overload. Minor, worth a one-line tidy: give an
idle point its minimum only when both the remaining budget and its
controller's remaining budget allow it (`controller_budgets[name] >=
point.minPower`), which would make the DEBUG line truthful and keep the
distributor's own sum inside wiring.

Verdict on the coordinator's question: wire offers can and could sum above
budget/wiring by the legacy minimum/spike rules; the fix wave does not add a
new mechanism, the per-TWC actual-draw guard bounds every offer the same way
on both trees, and the simulated draw never exceeded the wiring max. Not
Critical.

## 3. I1 and M1 behaviour changes: acceptable

- I1: an idle Gen2 TWC now reserves `minAmpsToOffer()` (12 A default, or the
  per-TWC override, never below `minAmpsTWCSupports`) and that is what the
  heartbeat sends (`test_gen2_idle_minimum.py`, real heartbeat, wire read from
  the interface). That is the spec rule ("an empty TWC endpoint must be
  offered its minimum so a plug-in can be detected") and strictly less than
  the legacy path offered an idle slave. When the budget cannot cover it the
  TWC gets 0 (and the legacy 6 A on the wire while another car charges), as
  before.
- M1: a merged point's `wantsToCharge` follows the TWC when one is present.
  A paused car on a TWC that reports max 0 (old firmware) resumes through the
  idle minimum and gets its share one pass later; on firmware that echoes the
  offer there is no delay. Matches "when it's plugged in, the distributor
  reallocates". Gen3 is unaffected.
- `TWCSlave.py:577` start gate on `minAmpsToOffer()`: consistent with I1 and
  the override; without an override it only differs when `minAmpsPerTWC` is
  below the TWC's minimum, where the heartbeat zeroes such offers anyway.

## 4. No new breakage

- Focused files (16, including every file the wave touched and the
  distributor/readonly/no-wake suites): 256 passed.
- Removed declarations (`orderKey`, `Provider.readSource` and its four
  copies, `EVSEInstance.provider` and the Gen2/Gen3 copies): no remaining
  reader in lib; `VehicleEndpoint.provider` (a property) stays.
- `TeslaBLE.applyChargeLimit(vin=, remoteOnly=)` and
  `TeslaAPI.applyChargeLimit(vin=, remoteOnly=)` accept what
  `VehicleCommandQueue._applyChargeLimitKwargs` and the façade pass; no
  producer sets `remoteOnly` today, and BLE declining it is a reasonable
  reading of the flag.
- Docs/CHANGELOG additions are accurate against the code (Gen3 line,
  `controller.Gen2TWCs.ranges`, the distributor-scoped Fleet-amps rule with
  the BLE-on-UMC effect, relabels, m5/m6 folded).

## Findings not addressed or new

- **New, Minor: a targeted `applyChargeLimit(vin=X)` can wake other cars.**
  TeslaAPI.py:1144 calls `self.car_api_available(applyLimit=True)` without
  `vin=target`, so the wake loop in `car_api_available` (458-520) walks every
  car; any other at-home car with `stopTryingToApplyLimit` False may be sent
  a $0.02 wake. Latent today (nothing queues a `vin`; Task 9 ruled targeted
  limits are HA-only in practice), but the method now advertises `vin`. Fix:
  pass `vin=target` (the function already filters on it).
- **Minor (from §2): the idle reservation ignores the controller budget**
  (TWCMaster.py:613-625). One-line fix as above; no safety impact because of
  the wire guard.
- Carried, unchanged and still fine: M4 (suppressions re-parse), M5
  (`_slaveForKey` case), Task 11 m2 (0 W target goes out as 6 A beside a
  charging car), Task 11 Step 6 live check.

## Assessment

Ready to merge: **Yes** (the two Minors above are optional tidy-ups; the
Critical and Important findings of the final review are closed with
real-method tests, and the wire-sum concern is pre-existing behaviour that
the per-TWC guard bounds identically before and after the wave).
