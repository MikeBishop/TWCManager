# Task 11 re-review 1 (9358db4..b72c79c): I1, m3, m4

## Verdict

**APPROVED.** I1 is fixed. m3 and m4 are done. There is no new Critical or Important issue.

## Checks

| Item | Result |
|---|---|
| **I1** | **Fixed.** In `groupEndpoints` (`ChargingPoint.py:187-188`), a local endpoint whose key already holds a local member becomes its own point, keyed by its `ID`. A point therefore holds at most one TWC, so `setTargetPower`'s "each local member gets `watts`" can no longer double-count. |
| **m3** | **Done.** The DEBUG line is built only under `logger.isEnabledFor(logging.DEBUG)`. `logging` is already imported (`TWCMaster.py:7`). |
| **m4** | **Done.** The docstring now names `receive_slave_heartbeat`, and the long line in `_blindTWCs` is rewrapped. |
| Scope | The diff touches only the files listed above plus tests. `TWCSlave.py` is untouched. The activation rule is unchanged. |
| Tests | The focused files (`test_charging_points`, `test_distributor_loop`, `test_vehicle_endpoint`, `test_gen3twc_provider`, `test_gen2twc_provider`, `test_provider_order`, `test_twcslave`) give 134 passed. |

## Probe results on b72c79c (`scratchpad/probe-t11/test_probe_t11.py`, 14 passed)

**The original 10 probes still pass.** These are the stopped-car and paid-path guarantees:
- stopped car in modes 1, 2 and 3 across budgets of 1 to 40 A: no `setAmps`;
- two cars on two TWCs;
- a car on no TWC, on its own and beside a TWC that is blind;
- two Gen3 units, each target reaching `setUnitTarget`;
- the idle minimum applying to Gen2 only;
- the DEBUG line.

**The I1 reproducer is inverted.** It now asserts:
- the sum of the two TWC offers is ≤ 40 A (got 32 + 6);
- exactly one point holds the car's endpoint;
- no `setAmps` is queued.

It passes.

**New: exhaustive three-TWC sweep.** Each of the 3 slaves is assigned one of 7 kinds:
- serving A, stale-lastVIN A, stopped A, stale B, serving B, idle, or lastVIN A at state 00.

That gives 343 shapes, run across budgets 0/5/6/11/12/13/18/20/40/80 A, in modes 1 and 2, for 2 rounds each: 6,860 cases. Three things are checked:
- the sum of TWC offers is ≤ min(budget, `wiringMaxAmpsAllTWCs` = 80);
- every point has at most one local member;
- no `setAmps` is queued for a car that any TWC claims.

Violations: **0**.

**New: endpoint-order permutations (all 6).** Each order is checked for two things:
- each of the two TWCs is in a different point;
- the car's endpoint is in exactly one point, and that point has a local member.

**New: a stale Gen2 `lastVIN` beside a Gen3 correlated to the same VIN.** The result is two points. Gen2 watts plus the Gen3 target stay within the 40 A budget, with no `setAmps`.

## Ruling: "endpoint order decides which TWC keeps the car"

**Wiring-safe, and acceptable until Phase 5.**

**Why it is safe.**
- Every TWC is in exactly one point, and the water-fill and idle rule never hand out more than `available_watts` in total. The sweep confirms this over every shape and order.
- Whichever point holds the car's endpoint also holds a local member, so the endpoint never gets an amps command. No paid path opens, whichever TWC wins.

**What it costs in behaviour.** If the stale TWC comes first, the TWC really serving the car becomes a point on its own.
- That point still wants power, because `wantsToCharge` comes from `reportedAmpsMax`, and it is budgeted normally.
- Its `maxPower` no longer takes the car's own maximum into account. The TWC's own maximum still caps it, and the car's on-board charger limits the actual draw, so this is only a slightly worse offer for one round.

**How long it lasts.** The window closes when the stale TWC starts its anonymous session (≥1 A drawn) or reads the new car's VIN. Preferring the `currentVIN` holder is the right Phase 5 attribution refinement. The report's reason for not clearing `lastVIN` inside a property getter is sound.

## Remaining (not in this round's scope; unchanged)

- **m1:** Task 10's lost coverage is still missing. Carry forward.
- **m2:** a 0 W offer can still go out as `minAmpsTWCSupports` while another Gen2 charges. This is pre-existing; mention it in the Step 6 notes.
- **m5 / m6:** CHANGELOG wording. Left to the coordinator or the user, because the brief's text was meant to be used word for word.
- **Observation (pre-existing, not from this task):** in `chargeRateControl` 2, `TWCSlave._queueChargeRate` targets `getLastVehicle()`, which falls back to `lastVIN` (`TWCSlave.py:1242-1250`). A stale TWC's heartbeat can therefore send a rate meant for its own target to the car that left it. This is the per-slave heartbeat path and the same as before Phase 2; give it to Phase 5 attribution with the rest of the `lastVIN` rule.
