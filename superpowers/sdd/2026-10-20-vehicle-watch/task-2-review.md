# Task 2 review (3af56479..356c1d15)

Spec compliance: PASS with a caveat (the properties are enforced nowhere; wantsToCharge is the live rule).
Quality: PASS with minor findings.

## Findings, ranked
1. isCharging/currentAmps on VehicleEndpoint have no reader in lib. EVSEInstance.py defines neither (brief's "already read by callers" was wrong). Only Gen3TWC.py:235,307 uses its own currentAmps; TWCMaster.py:1286+ isCharging is TWCSlave state; ChargingPoint.py reads only wantsToCharge (:49). Spec text asks for them ("asleep => isCharging False, currentAmps 0"), so compliant, but they are dead code (+~8 lib lines) today.
2. The distributor does not read a vehicle endpoint's draw at all. TWCMaster.py:598 selects `p.wantsToCharge and not p.isReadOnly`; budgets (_budgets :501) are static (VehicleEndpoints = inf); offers are fair share by maxPower/minPower. Draw/charging state is never consulted for allocation, so the real enforcement of "asleep after Charging releases its share" is wantsToCharge (TWCMaster.py:598, :667 else-branch sets target 0, clearing desired AMPS). That part is correct and sufficient; the sleep rule need NOT move elsewhere. getTotalAmpsInUse (TWCMaster.py:1056) is Gen2-only by spec decision (EMS section, separate issue).
3. Likely future consumer: EMS detector (spec "EMS trigger") subtracts "each watched car's last known actualCurrent while known Charging". If it reads vehicle.value directly it will bypass the asleep zeroing; it should use endpoint.currentAmps or Presence.asleep. Note for the detector task; keep the properties only if that task uses them, else drop them (rearchitecture-must-shrink).
4. Tests: meaningful (red/green on asleep, Stopped-stays-wanting, sign-of-life restore via asleep()'s life ordering). Gaps: no test asleep with chargingState None/Complete; no distributor-level test that the asleep-Charging car gets target 0 / no desired AMPS (the only place the rule has effect). Red step not shown for wantsToCharge (test 1 would fail on it; fine). Cross-file import of setup from test_limit_reconciler is existing pattern.
5. wantsToCharge expression is correct: asleep+Charging False, asleep+Stopped True, unknown sleep (None) unchanged since `asleep(...) is True`. occupied unchanged and still True via pluggedIn.
6. Comments obey the rule (why: Stopped may wake on start; asleep after Charging finished). isCharging/currentAmps lack a one-line why for zeroing asleep; acceptable per brief's "one comment".
7. Lib growth +15 matches report (spec budget concern only if finding 1 dead code persists).
