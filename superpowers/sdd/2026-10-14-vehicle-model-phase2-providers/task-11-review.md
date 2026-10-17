# Task 11 review: Charging points by generic grouping (4aa71a1..9358db4)

## Verdicts

- **Spec compliance: PASS.**
  - Every item in the brief's Interfaces is present as specified: `ChargingPoint`, `groupEndpoints`, `TWCMaster.chargingPoints`, the per-point `distributeEVSEPower` and the Gen2-only idle-TWC rule.
  - `MergedEVSE.py` is deleted and `getDedupedEVSEs` is removed.
  - All of the Task 10 review's "Task 11 must test" items are present, and they use real objects: a `Gen2TWC` made by `newSlave`, the real `VehicleEndpoints` with registry vehicles, a real `ProviderOrder` and a real `Gen3TWCs`. These cover:
    - the 8 required real-object tests;
    - an occupied Gen3 with key `None` counting as blind (fixed and tested);
    - the Gen2-00 sleeping-car decision (pinned by a test);
    - the BLE-only writable positive test.
  - The CHANGELOG lines match the brief word for word.
  - The `docs/Gen3_Status.md` edit is outside the brief's file list, but it is correct and in scope.
  - Step 6 (the live check) has not been run, as intended.
- **Task quality: NOT APPROVED. Fix in task (1 Important).**
  - **What is wrong:** a stale Gen2 `lastVIN` can put two local endpoints into one point. Each then receives the whole point target, which breaks the wiring budget.
  - **Whose fault:** this follows the brief's own text ("each gets `watts`"). It is a gap in the brief, not an implementer error, but it is a wiring-budget regression and must be fixed.
  - **Everything else is clean.** Each item below was verified against the real distributor:
    - Task 10's interim paid path is closed.
    - The pure-Gen2 path is unchanged.
    - The idle minimum applies to Gen2 only.
    - Gen3 per-unit targets reach `setUnitTarget`.
    - There is no new paid path and no new serial-thread I/O.
  - **Step 6:** the Important finding does not block Step 6 on the user's single-TWC box, so the coordinator can run Step 6 in parallel with the fix.

## Concern rulings

The report numbers 8 concerns; all 8 are ruled here.

1. **Brief prose vs. brief tests (anon keys kept as issued; `currentVIN` upper-cased): ACCEPT both.**
   - Keeping anonymous keys as issued matches `VehicleRegistry._normalise` (`VehicleRegistry.py:66-70`), so grouping keys and registry keys agree.
   - Upper-casing `currentVIN` is harmless.
   - The brief's prose was wrong and its tests were right.
2. **The `chargeRateControl` branch lives in `receive_slave_heartbeat` (`TWCSlave.py:603`, branch at `:864`), not `send_master_heartbeat`: ACCEPT.**
   - The brief has a typo. Carry the correct location into the Step 6 narrative.
   - The `distributeEVSEPower` docstring (`TWCMaster.py:518`) repeats the old name (see m4).
3. **The test sets `_TWCSlave__lastAPIAmpsRequest = 0`: ACCEPT.** This is test plumbing to get past the class-level 30 s hold-off (`TWCSlave.py:15`). Behaviour is unchanged.
4. **Gen2 at state 00 with a sleeping car is pinned as two points: ACCEPT.**
   - The Task 10 review explicitly allowed either "name it out of scope or pin it with a test".
   - The cost, stated plainly: while the TWC reports 00 the car's endpoint stands alone. It can queue one paid Fleet `setAmps` per amps change, or per 600 s refresh, when no free provider can serve it.
   - The fix belongs to Phase 5 presence attribution.
5. **A correlated Gen3 car's endpoint gets no amps command: ACCEPT.** This is decision 11. For a single unit, `h = target` is exact.
6. **The DEBUG line is chatty: ACCEPT.**
   - It logs at level 10 (DEBUG), once per round, so it is silent at INFO. The probe confirmed this.
   - It contains point IDs (VINs) and watts. It contains no token. VINs at DEBUG are consistent with the rest of the codebase.
   - See m3 for the eager formatting.
7. **Baseline was 1267, not 1153: ACCEPT.** The brief's number was out of date.
8. **Step 6 not run: ACCEPT.** This is intentional. The grep string for Step 6 is `distributeEVSEPower: <W> W over Point-<VIN>=<W> W`.

## Probe results

**Probe file.** `scratchpad/probe-t11/test_probe_t11.py` runs the real `TWCMaster.distributeEVSEPower` over the real endpoints listed under the verdicts. Only the vehicle command queue, the background queue, the TeslaAPI/Policy lookups and the budget are stubbed.

**How to run it.** Rerun with:
```
cd scratchpad/wt-vm2 && PYTHONPATH=$PWD/lib:$PWD timeout 300 systemd-run --user --scope -q -p MemoryMax=2G \
  scratchpad/venv/bin/python -m pytest scratchpad/probe-t11/test_probe_t11.py -q --timeout=60 -p no:cacheprovider
```
`probe-t11/conftest.py` calls `initialize_logging_levels()`.

**Old-code run.** I extracted the 4aa71a1 tree with `git archive 4aa71a1 lib tests` into `probe-t11/old/`. Its `probe/conftest.py` aliases `TWCMaster.chargingPoints = TWCMaster.getDedupedEVSEs`.

| Probe | 9358db4 | 4aa71a1 |
|---|---|---|
| Stopped car (lastVIN, state 03), mode 1, budget 40 A, 5 rounds: one `Point-<VIN>`, TWC 32 A, no `setAmps` | pass | FAIL: two EVSEs |
| Stopped car, mode 1, budgets 1/3/5/5.9/6/7/12 A: never a `setAmps` | pass | FAIL: `{'cmd': 'setAmps', ..., 'amps': 5}` |
| Stopped car, mode 2, budgets 5/20/40 A: the distributor queues no `setAmps`; one heartbeat queues at most one `setChargeRate` | pass | FAIL: `amps: 5` |
| Stopped car, mode 3, 5 A: no `setAmps` | pass | FAIL: `amps: 5` |
| Two cars on two TWCs (one `currentVIN`, one lower-case `lastVIN` at 03), modes 1 and 2: two points, 20 A each, no `setAmps` | pass | FAIL: not grouped |
| Car on no TWC, beside a named TWC whose car is Complete: car queues `setAmps` 32 A; the idle TWC gets 6 A from the remaining 8 A | pass | FAIL: TWC 0 |
| Car on no TWC beside an unnamed plugged TWC (blind): no endpoints, no `setAmps` | pass | FAIL (ID shape only) |
| Gen3, two units both charging and anonymous: two one-member points; `setUnitTarget` gets 4800 W per unit (never summed); one unit Complete → `{u1: 9600, u2: 0}`; no `setAmps` | pass | FAIL |
| Idle Gen3 beside an idle Gen2: Gen3 gets `setUnitTarget(id, 0)`, Gen2 gets 6 A (Gen2-only idle minimum) | pass | FAIL |
| DEBUG line: `distributeEVSEPower: 9600 W over Point-5YJ3E1EA1KF000001=7680 W`, levelno 10 | pass | n/a |
| **Stale lastVIN** (I1 reproducer, below) | **over-allocates: 32 A + 32 A on a 40 A budget** | separate EVSEs |

Results: on 9358db4 all 10 behaviour probes pass, and the 11th probe reproduces I1. On 4aa71a1 all 10 behaviour probes fail. The `amps: 5` lines are the interim paid path; it is now closed.

## Other checks

- **Pure-Gen2 path is unchanged.** The activation rule (`non_gen2` empty → return) is byte-for-byte the same. `TWCSlave.py` is untouched. `test_pure_gen2_leaves_distributor_off` covers this. The distributor stays off wherever it was off before, because registration of `VehicleEndpoints`/`Gen3TWCs` did not change.
- **The idle minimum applies to Gen2 only.** It is keyed on `idleMinimum is True`: `Gen2TWC.py:27` sets it, and `Gen3TWC.py:335` and `EVSEInstance` default to False. The minimum is drawn from `remaining_watts`, so idle minimums never exceed the budget. That is stricter than the per-slave path.
- **Gen3 per-unit targets reach `setUnitTarget`.** `Gen3TWC.setTargetPower` → `controller.setUnitTarget(self.ID, watts)`. The probe confirmed this with a wraps spy.
- **No new paid path.** The only amps path is the existing queued `setAmps`, reached only from points with no local member. Nothing new runs on the serial thread beyond in-memory grouping:
  - `Gen3TWC.vehicleKey` → `registry.vehicleAt`, which is dict work under the registry lock;
  - `setUnitTarget` → `republish` → `setHouseWatts`, which writes in-memory registers.
  - No I/O happens under locks.
- **The deleted classes are fully gone.** `git grep MergedEVSE|getDedupedEVSEs|TeslaAPIEVSE|TeslaAPIController` over the whole tree matches only the grep test's own string.
- **The CHANGELOG is accurate**, with two notes:
  - It names HomeAssistant as an amps writer, which covers Task 10's m2.
  - "An idle TWC keeps its minimum" is true for Gen2 only (see m5).
- **Tests.** I ran the focused files `test_charging_points`, `test_distributor_loop`, `test_vehicle_endpoint`, `test_gen3twc_provider`, `test_gen2twc_provider`, `test_provider_order` and `test_twcslave`: 94 passed.

## Findings

### Critical
None.

### Important

**I1. A stale Gen2 `lastVIN` puts two TWCs in one point, and each gets the whole target.**
- **Where:** `ChargingPoint.py:145-149` (`setTargetPower`: every local member gets `watts`), together with `groupEndpoints` (`ChargingPoint.py:173-185`).
- **How it happens:** `Gen2TWC.vehicleKey` returns `lastVIN` while the TWC reports any plugged state (`Gen2TWC.py:100`). `lastVIN` is never cleared on state 00: it is set only at `TWCMaster.py:1304`. The sequence is:
  1. Car A charges on TWC1, then is moved to TWC2, where it charges with `currentVIN = A`.
  2. Anything is plugged into TWC1.
  3. From plug-in until ≥1 A flows and the anonymous session opens, TWC1's key is A.
  4. Both TWCs and A's endpoint form `Point-A`, and each TWC gets `_evseTargetAmps = 32`.
- **Probe result:** 64 A offered against a 40 A budget.
- **Why the distributor matters here:** with `_centralized_target` set, `TWCSlave.py:711-716` skips the per-slave subtraction of the other slaves' draw. The distributor is therefore the only wiring guard on this path.
- **Why it is a regression:** the per-slave path would offer TWC1 the remaining 8 A, and 4aa71a1 kept a VIN-less TWC separate.
- **Scope:** the same shape arises when a Gen2's stale `lastVIN` matches a VIN correlated to a Gen3.
- **Fix:** in `groupEndpoints`, a local endpoint never joins a group that already has a local member. It starts its own point keyed by its `ID`. Each TWC is then budgeted separately. The car's endpoint still gets no amps, because its point keeps a local member. Add a real-object test from probe 11: two `newSlave`s, one with a stale `lastVIN` at 0x01, the other with `currentVIN`, budget 40 A; assert two TWC points and `sum(_evseTargetAmps) <= 40`.
- **Root cause, for Phase 5:** when another TWC reports a `lastVIN` as its `currentVIN`, that is unplug evidence. Record it as a `Gen2TWC.vehicleKey` refinement.

### Minor

- **m1. Lost coverage from Task 10's m4 is still missing.** These cases have no test: a failed scan fails closed (Gen3 walk included), the 0.99 A boundary, `carapi.enabled()` False → `[]`, and a cached endpoint dropped once hidden. The Task 11 brief did not require them, so this is a carry-forward, not a compliance miss. Fix: add one test each to `tests/unit/test_vehicle_endpoint.py`.
- **m2. A 0 W offer is not 0 A on the wire when another Gen2 charges (pre-existing).** `TWCSlave.py:~772-800` raises a centralized target of 0 to `minAmpsTWCSupports` when `numCarsCharging > 0` and `max/numCars > minAmpsToOffer`. Step 6 readers should not read `Point-...=0 W` in the DEBUG line as the TWC's actual offer. Fix: none in this task; note it in the Step 6 instructions. Phase 3 owns the reconciler.
- **m3. The DEBUG line is formatted eagerly.** `TWCMaster.py:621-625` builds the `", ".join(...)` string every round even when DEBUG is off. The cost is trivial. Fix (optional): wrap it in `if logger.isEnabledFor(logging.DEBUG):`.
- **m4. Stale docstrings.**
  - `TWCMaster.py:518` says `send_master_heartbeat`; the code is in `receive_slave_heartbeat` (concern 2).
  - `VehicleEndpoints.py:56` is a docstring line over 88 columns.
  - Fix: reword and rewrap.
- **m5. The CHANGELOG's "an idle TWC keeps its minimum" is true for Gen2 only.** An idle Gen3 gets 0. Fix (optional): "an idle Gen2 TWC keeps its minimum".
- **m6. The Bugfixes entry describes an unreleased bug.** `MergedEVSE`/`TeslaAPIEVSE` (6f075db) are in no release tag. The entry is the brief's verbatim text, so there is no action unless the user prefers it folded into the Architecture line.
