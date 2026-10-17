# Task 4 report: Gen3 TWC provider

**Status:** DONE_WITH_CONCERNS

**Branch:** vehicle-model/phase2 (worktree wt-vm2). Commits on top of 33dc48a:
- `1c71d67` Add the Gen3 TWC provider: anonymous plug sessions from vitals, one shared headroom, fetches off the serial loop
- `7e2019b` Record a Gen3 unplug on the departing car so it cannot correlate with the next one

## What changed
- `lib/TWCManager/Vehicle/Providers/Gen3TWCProvider.py` (new): name `Gen3TWC`, rank 1, local, sharedControl. It declares READ_PLUG and READ_AMPS as LOCAL passive, and SET_AMPS, START_CHARGING and STOP_CHARGING as LOCAL. It also adds `unitFor`, `ready`, `ampsRange` = `(6, fuseAmps)`, `limitations` (NO_INDIVIDUAL_STOP when more than one unit is `occupied is True`), and `setAmps`/`stopCharging`/`startCharging` by registry key.
- `lib/TWCManager/EVSEInstance/Gen3TWC.py`:
  - `_fetch_vitals` is replaced by `refreshVitals()`, which runs on the background thread only. It assigns a new dict, then handles the plug edges and observations outside any lock, then calls `controller.noteVitals(self, rising)`.
  - New members: `vitals` (cache only), `vitalsStale()`, `pointId`, `fuseAmps`, `phases`, `lastTarget`, `cloudVin`, `CORRELATE_WINDOW = 120.0` and `_correlate()` (cloudVin first, then exactly one candidate, else anonymous with the INFO line).
  - Property changes: `isLocal` is now True and `idleMinimum` is False. `occupied` and `vehicleKey` follow the brief, and every state property reads the cache.
  - `setTargetPower`, `startCharging` and `stopCharging` now go through `controller.setUnitTarget`.
- `lib/TWCManager/EVSEController/Gen3TWCs.py`:
  - New members: `sharedControl`, `DAMP_AMPS`, `MIN_AMPS`, `devices()`, `unitTargets`, `setUnitTarget`, `headroom()`, `demandAmps()`, `solve()`, `republish()`, `noteVitals()` and `refreshVitals()`.
  - `solve()` water-fills by 20-step bisection, rounds to 0.01 A, then clamps to MIN_AMPS. When every target is 0 it returns the max fuse.
  - `allEVSEs` lists only reachable units and queues `{"cmd": "gen3Vitals"}` when any unit is stale.
  - The module docstring is updated. The Modbus server code is untouched.
- `lib/TWCManager/TWCManager.py`: adds a `gen3Vitals` branch to the background-task chain. Inside the existing `_gen3_cfg` enabled block, it now binds `gen3 = Gen3TWCs(master)`, registers that module and then calls `master.providerOrder.register(Gen3TWCProvider(gen3, master))`.
- `tests/unit/test_gen3twc_provider.py`: the brief's 11 tests verbatim, plus 4 more:
  - `ampsRange` is never None while `ready(SET_AMPS)` is True. This is the Task 2 constraint, checked for an anonymous key and for an unplugged unit.
  - A failed fetch backs off.
  - The controller's `refreshVitals` reaches every unit, and the background branch and provider registration are present in the source.
  - An unplugged occupant does not correlate with the next car.

## Threading
- HTTP happens only inside `Gen3TWC.refreshVitals`, which is reached only from the `gen3Vitals` background task. No property fetches.
- The registry calls in `refreshVitals` hold none of our locks.
- The controller adds `_targetLock` (an RLock) around solve and publish, so two threads never publish out of order. The lock order is always `_targetLock` then `_lock` (inside `setHouseWatts`). `_lock` never takes `_targetLock`, and nothing under `_targetLock` touches the registry or does I/O.
- Units are built once in `Gen3TWCs.__init__`, so every thread sees the same instances.
- There is no new loop. Vitals are fetched on demand when `allEVSEs` sees a stale cache, using today's TTLs (5 s after success, 10 s after failure). `queue_background_task` coalesces on `cmd` (`TWCMaster._taskKey`).

## TDD evidence
Fail-before, at 33dc48a with the new test file:
```
E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers.Gen3TWCProvider'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```
The unplug-occupant test failed before the fix in 7e2019b:
```
E   AssertionError: assert True is False
E    +  where True = value('pluggedIn')
```
After: `tests/unit/test_gen3twc_provider.py` passes 15 of 15. The full suite (`tests --ignore=tests/API --ignore=tests/integration`) gives **1204 passed, 1 xfailed** (1189 before, plus 15 new). Black was run on the four lib files only.

## Deviations from the brief, and concerns
1. **Falling edge (addition).** Before `endPlugSession`, the falling edge now observes `pluggedIn=False` (source `Gen3TWC`) on the vehicle at the point. Without it, the unit's own repeated `pluggedIn=True` re-stamps (`Fields.observe` re-stamps every call) left the departing car a fresh candidate for 120 s. A different car plugging in during that window would have been attributed to it.
2. **`vitalsStale()` drops today's `and self._vitals` clause.** Today, a unit that has never answered re-fetches on every call, ignoring the backoff. Now the 10 s failure TTL applies from boot. Otherwise an unreachable unit would get an HTTP attempt on every `allEVSEs` pass.
3. **`ready()` also requires the capability to be declared.** The brief says only `unitFor is not None`. This makes no difference for any declared capability.
4. **Correlation runs only on the rising edge.** If TeslaMate's `pluggedIn` arrives after the Gen3 sees the plug, the session stays anonymous until the car is re-plugged. This is as the brief specifies. Task 7's hook in `noteVitals` (or a retry there) could cover it.
5. **`Gen3TWCs.refreshVitals()` fetches every unit when any one is stale.** This is what the brief says. All units share the same TTLs, so in practice they go stale together.
6. **"Target set changed" means any change to a unit's non-zero target.** Distributor commands therefore always republish, and only drift driven by vitals is damped (by `DAMP_AMPS`).
7. **One voltage for every unit.** `solve()` converts targets with the first device's voltage, and `setHouseWatts` uses the first device's phases and voltage, as before.
8. **Docs not updated.** `docs/modules/Controller_Gen3TWCs.md` still describes `isLocal=False` and the old "allocate the total" model. It is not in the brief's file list, so I left it alone.
9. **Unit tests only.** There is no Gen3 hardware. The zero-headroom stop and multi-unit sharing are unverified on hardware.

## Fix round 1

**Status:** DONE. Commits on top of 7e2019b:
- `f6b1517` Publish the Gen3 house load per phase times phases, and treat ramping cars as unconstrained (C1, C2, M1, M4 test, M7, M8)
- `84eb6fb` Describe the shared Gen3 headroom, background vitals and anonymous sessions (I1, plus M3 in Limitations)

### Fixes
- **C1:** `republish` now publishes `watts=load * voltage * phases`. The new test `test_three_phase_unit_matches_today_for_a_target_and_a_stop` uses a 16 A, 3-phase, 230 V unit. A 10 A/phase target gives `fuse*V*3 - 6900`, which matches today, and headroom 10. An all-zero target gives the full `fuse*V*3`. The existing single-phase tests still cover parity with today for one unit.
- **C2:** in `solve`, when `served(0) < wanted` under the measured demands, every demand is treated as unlimited and the solve is redone. One ramping unit then gets `h = A_1`, and several get the mean. A full fuse is published only when the targets exceed every fuse.
  - New test: one unit, a car at 5 A under a 20 A target, keeps h = 20.
  - New test: two cars ramping (5 A and 4 A under 20 A and 10 A targets) give h = 15.
- **I1:** `docs/modules/Controller_Gen3TWCs.md` is rewritten in these sections:
  - how rate control works: per-unit targets water-filled into one load, at least 6 A per targeted unit, 1 A damping, and a stop only when no sibling holds a target;
  - state readback: vitals fetched in the background, cache-only reads, an unreachable unit left out until a fetch succeeds, and a new "Which car is connected" section on anonymous sessions and the correlation rule, with the cloud VIN coming in a later release;
  - multiple units: the total follows the sum of the targets, and a unit cannot be stopped individually, so another stop path is used;
  - Limitations: the M3 exposures, and that nothing is verified on hardware.
- **M1:** `Gen3TWCs.refreshVitals` fetches only units whose cache is stale. Test: `test_refresh_skips_fresh_units`.
- **M4:** new test for units with different fuses (48 A and 32 A, 30 A each). The net equals 60 A, and the smaller unit keeps at least 6 A. This passed before the fix as well; it adds coverage only.
- **M7:** the Gen3 provider is registered in its own try block, which logs "Could not register the Gen3TWC provider".
- **M8:** `_connected` is updated only after `_plugEdges` returns, so a failed registry update retries the edge on the next fetch. Test: `test_a_failed_registry_update_retries_the_plug_edge`.

### Fail-before, at 7e2019b with the new tests
```
FAILED test_three_phase_unit_matches_today_for_a_target_and_a_stop
  Expected: mock(watts=4140, phases=3, voltage=230)
    Actual: mock(watts=1380.0, phases=3, voltage=230.0)
FAILED test_one_ramping_car_keeps_its_target_headroom   assert (48.0 == 20)
FAILED test_two_ramping_cars_share_the_mean             assert (48.0 == 15)
FAILED test_refresh_skips_fresh_units                   Left contains one more item
FAILED test_a_failed_registry_update_retries_the_plug_edge
  AssertionError: assert None == ('anon:' + 'Gen3TWC-10.0.0.1')
```
After: `test_gen3twc_provider.py` passes 21 of 21. The full suite gives **1210 passed, 1 xfailed** (1204 before, plus 6 new tests).

### Minors left, not marked fix-now
- **M2:** overshoot while a car ramps beside an unconstrained sibling is inherent to the design. The suggestion (two agreeing readings before a unit counts as car-limited) is left for Task 7 or later.
- **M3:** no code change. It is documented in Limitations.
- **M5:** the race between `ready` and `ampsRange` across threads is harmless; `setAmps` returns False.
- **M6:** dedup still goes by `currentVIN` until the charging-points task's `groupEndpoints` lands.

The plan still has the brief's `H * V` publish formula. The brief file is not in the worktree, and I did not edit it. Correcting it to `H * V * phases` is left to the coordinator.
