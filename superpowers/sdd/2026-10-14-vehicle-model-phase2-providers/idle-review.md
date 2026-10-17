# Review: c010817 "Do not count the idle TWC minimum against any budget"

Verdict: APPROVE. No Important or higher findings. 3 Minor.

Probe: scratchpad/probe-idle/test_probe.py, run against the real TWCMaster + TWCSlave heartbeat at c010817 (17 cases, all pass). Distributor active, central target set.

## 1. Idle TWC wire offer with another car charging: matches main (6 A)
The idle point's target is 0, but `TWCSlave.receive_slave_heartbeat` still runs the `desiredAmpsOffered < minAmpsToOffer` branch on a centralized target. With numCarsCharging > 0 and getMaxAmpsToDivideAmongSlaves()/numCarsCharging > minAmpsToOffer, it sets minAmpsTWCSupports (6). That is the same branch as main (lines ~770-862). The parity regression the task feared does not exist.

| minAmpsPerTWC | feed | idle target | wire offer, spike off | wire offer, spike on |
|---|---|---|---|---|
| 6 | 40 | 0 | 6 | 6 |
| 12 | 40 | 0 | 6 | 6 |
| 12 | 20 | 0 | 6 | 6 |
| 12 | 13 | 0 | 6 | 6 |
| 12 | 12 (not strictly greater) | 0 | 0 | not run |
| 12 | 10 | 0 | 0 | not run |

The 12 and 10 A rows match main: its `>` is strict and the offer is 0 below the threshold.

## 2. Nothing charging: wire offer 0, matches main
Wire is 0 with spike on and off, via the "no cars charging" branch. The Gen2 TWC reads 0 as its hardware minimum.

## 3. Idle offer never counted or gated on a budget
- `distributeEVSEPower` (TWCMaster.py ~606-617) sets a target of 0 for every non-wanting point after the budget loop. It reads no budget and deducts nothing.
- The 6 A offer comes from TWCSlave, outside the distributor. It is not deducted, which is the permitted overshoot.
- Probe: feed 13, busy TWC gets 13, idle wire 6, so the sum is 19 for one cycle.
- Rebalance: the existing test_next_cycle_rebalances... shows 16/16 once the idle TWC's car wants power. Probe: targets 32.0 / 0.0 with the idle TWC unbudgeted.
- A charging point below minAmpsPerTWC gets 0 (stopped); tested with feed 10 and with two cars at feed 20.

## 4. Implementer's caveat on the paused-car start request: wrong as worded, behaviour matches main
The report says the start request "does not fire from the idle path". It does fire. startCarsCharging runs when lastAmpsOffered >= minAmpsToOffer() and the car draws under 1 A. The idle offer is 6 whenever another car charges, exactly as on main.

| minAmpsPerTWC | another car charging | lastAmpsOffered | startCarsCharging calls |
|---|---|---|---|
| 6 | yes | 6 | fires (2 calls over the two heartbeats the probe ran) |
| 12 | yes | 6 | 0 |
| 6 or 12 | no | 0 | 0 |

- Main uses `minAmpsPerTWC` and this branch uses `minAmpsToOffer()`. They are the same unless a per-TWC range override is set (an earlier ruling), so no regression.
- The caveat should be corrected in the report. It is true only when nothing else is charging.

## 5. `idleMinimum`: recommend removing it
The flag is unread in lib/ (EVSEInstance.py:114, Gen2TWC.py:27, Gen3TWC.py:333). Only tests touch it:
- test_gen2twc_provider.py:72 asserts it.
- test_charging_points.py `idleMin` helper and Gen3 cases.

A dead flag whose comment says "must be offered its minimum" misleads. Delete the attribute, the comment and the test plumbing. Keeping it is harmless but not recommended.

## Minor findings
- M1. The docstring of `distributeEVSEPower` (TWCMaster.py ~528) still says an idle Gen2 TWC "is offered its minimum while the budget allows". Stale; the idle target is 0 and nothing is gated.
- M2. The header comment of tests/unit/test_gen2_idle_minimum.py is stale. It says the budgeted minimum "must be what the real heartbeat sends" and that TWCSlave zeroes sub-minimum offers.
- M3. CHANGELOG and Interface_RS485.md say the idle offer is 0 (Gen2: treated as the hardware minimum). With another car charging, the actual wire offer is 6 A (minAmpsTWCSupports). No test asserts that wire value for the new behaviour (all new tests assert the target 0 or the nothing-charging wire 0). Add a test_idle_twc_offered_6A_on_wire_when_other_car_charges using `chargingSlave` and `offers`, as in the probe, and reword the docs.
