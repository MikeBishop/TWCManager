# Task 4 review: Gen3 TWC provider (33dc48a..7e2019b)

Checkout reviewed: wt-vm2 at 7e2019b. Tests run: `tests/unit/test_gen3twc_provider.py tests/unit/test_twcmanager.py`, 52 passed. Two throwaway probes, kept out of the checkout, confirmed C1 and C2 below.

## Verdicts

- **Spec compliance: PASS.** Every interface the brief names exists with the brief's name and shape. Later tasks consume `noteVitals(unit, rising)`, `cloudVin`, `setUnitTarget(unitId, watts)` and `idleMinimum`. The provider attributes, declarations, background branch and registration placement all match. The deviations (report items 1-3) are defensible. Both Criticals come from the brief: C1 from its literal publish formula, C2 from a case it leaves unspecified. They are brief errata, not implementer drift.
- **Task quality: FAIL until a fix round.** It does not meet the requirement that a single unit behaves as today: three-phase units get the wrong headroom and cannot be stopped (C1), and one unit whose car is ramping gets the full fuse (C2). The docs also now describe the wrong model (I1).

## Concern rulings

The dispatch said 7 concerns, but the report lists 9. All 9 are ruled on here. The dispatch's "concern 6, docs" is the report's item 8.

1. **pluggedIn=False on the falling edge: accept.** It goes through `registry.vehicleAt` (`_attributedTo` / `get`) and never `getOrCreate`, so it cannot create or revive a vehicle. That meets the Phase 1 rule. The test `test_an_unplugged_occupant_is_not_a_candidate_for_the_next_car` covers it.
2. **`vitalsStale()` drops `and self._vitals`: accept.** Without the change, the failure backoff would never apply to a unit that has never answered.
3. **`ready()` also checks that the capability is declared: accept.** It makes no difference for any declared capability.
4. **Correlation only on the rising edge: accept.** This is what the brief says. Task 7's `noteVitals` hook is the natural place for a retry.
5. **All units fetched when any is stale: accept as specified, but see M1.**
6. **Any change to a non-zero target republishes: accept.** Today every `setTargetPower` published, so this keeps that behaviour.
7. **One voltage, taken from the first device: accept.** It is today's behaviour, and the brief specifies the first device.
8. **Docs not updated: change.** The docs now describe wrong behaviour. See I1.
9. **Unit tests only: accept** (G6).

## Findings

### Critical

**C1. Three-phase units get the wrong headroom, and their stop does not stop.** `lib/TWCManager/EVSEController/Gen3TWCs.py:378`

The publish call is `setHouseWatts(watts=load * voltage, phases=phases, voltage=voltage)`. `setHouseWatts` divides `watts` by `phases` to get per-phase amps, so a 3-phase unit sees a house load of `H/3` per phase.

Probe: fuse 16 A, 3-phase, 230 V, target 10 A/phase. The unit got 14 A of headroom; today it gets 10 A. With every target at 0, it gets about 10.7 A of headroom, where today it gets 0, so a stop does not stop.

The brief's formula (`setHouseWatts(watts=H * V, ...)`) is what is wrong. It conflicts with the brief's own requirement that one unit behaves as today. Every test uses `phases: 1`, which is why nothing caught it.

- Fix: publish `watts=load * voltage * phases`.
- Add 3-phase tests for a target and for the all-zero stop, comparing against today's `fuse*V*phases - target`.
- Correct the formula in the plan.

**C2. One unit whose car is ramping gets the full fuse.** `Gen3TWCs.py:349-356` (solve), with `demandAmps` at `:306`

This happens whenever `served(0) < wanted`: every targeted unit reports a finite measured demand that sums below the targets. The bisection is then skipped, `lo` stays 0, and `H = 0` is published, which gives the full fuse to every unit.

- Probe: one unit, target 20 A, car ramping and measured at 5 A with `evse_state` "charging". `h` goes to 48 A (published watts 0). The car keeps ramping toward 48 A until a vitals fetch shows it at or above `h - 1`. That breaks "single unit unchanged" and can overrun a solar or wiring target by the whole fuse for several vitals cycles.
- The same happens with several units when every car is ramping or tapering at once.
- The brief does not cover this case.
- Fix: when `served(0) < wanted`, the demand estimates are not a binding cap. Re-solve with every `d_i = inf`, which is the brief's unconstrained case. One unit then gets `h = A_1` (today's behaviour), and two ramping units with targets 20 A and 10 A get 15 A each. Once a car really caps below `h - 1`, the feasible water-fill takes over as now.
- Add tests: one unit ramping, so `h == A`; two units both ramping, so `h == mean`.

### Important

**I1. `docs/modules/Controller_Gen3TWCs.md` now describes the wrong behaviour.** Concern 8. Passages to update:

- `:78-92` (per-unit `house = fuse - target`, and a stop writes the full fuse): replace with per-unit targets water-filled into one `H`. A stop presents the full fuse only when no sibling holds a target.
- `:111-113` (dropped "for that polling cycle"): vitals are now fetched on the background thread (`gen3Vitals`) and every property reads the cache. An unreachable unit is left out until a fetch succeeds.
- `:116-119` (equal sharing): describe the water-fill. A car-limited unit frees its share for its siblings. A zero-target unit cannot be stopped while a sibling charges (`NO_INDIVIDUAL_STOP`).
- `:155-162` (Limitations, "No VIN", "per-unit allocation not currently possible"): describe anonymous plug sessions and correlation (cloud VIN, else exactly one candidate within 120 s, else anonymous). Per-unit targets are now supported, subject to the shared-value limit.


### Minor

**M1. `Gen3TWCs.refreshVitals` (`Gen3TWCs.py:486`) fetches every unit, even fresh ones.** Each unreachable unit costs a 3 s timeout on the shared background thread, so N dead units block it for 3N s every 10 s. Fix: `if device.vitalsStale(): device.refreshVitals()`.

The fetch cannot storm: the task coalesces on `cmd` until `doneBackgroundTask`, so at most one is queued or running, and there is no growing loop.

**M2. Overshoot while a car ramps (inherent to the G2 design, documented here).** Example: a unit's car is ramping at 2 A beside an unconstrained sibling, with targets 20 A and 10 A. The ramping unit is treated as car-limited, so `h` rises to 28 A and the net can reach about 56 A against 30 A for a vitals cycle or two. The C2 fix does not cover this.

Suggestion, for Task 7 or later: count a unit as car-limited only when two consecutive vitals readings agree within `DAMP_AMPS`.

**M3. Two kinds of exposure in the single-candidate rule (G3, per the brief).**

- **Away from home.** A car with no `TeslaAPI` attachment (TeslaMate only) has no `atHome` check, and the registry carries no home or geofence field. Such a car plugging in anywhere within 120 s of an unknown car connecting to the Gen3 is attached to the Gen3.
- **Gen2 race.** A car that plugs into a Gen2 TWC at the same moment is excluded only once that Gen2 confirms its VIN (`twcVin`). Until then it is a candidate.

Both are residual risks in the brief's design (VIN-less fingerprinting is A27). No change for this task; note them in the docs' Limitations.

**M4. Units with different fuses track their targets only as a sum.** The water-fill matches the net. Each unit's own draw can still differ from its target: with 48 A and 32 A units both targeting 30 A, the draws are 38 A and 22 A. This is per the brief, but no test has units with different fuses. Add one asserting that the net equals the sum of the targets and that `h_i >= 6` holds for the smaller fuse.

**M5. A race between `ready()` and `ampsRange()`.** `Gen3TWCProvider.py:51-58` can see a falling edge between the two calls, because the background thread ends the session. `Order.candidates` then treats a `None` range as unconstrained, and `setAmps` returns False. That is harmless, but the "ampsRange never None while ready" guarantee only holds within one thread's snapshot. The ready/range constraint itself holds, and a test covers it.

**M6. Dedup is still by `currentVIN` until the charging-points task lands.** `Gen3TWC.currentVIN` is still `""`, so `getDedupedEVSEs` (TWCMaster.py:509) does not group a correlated Gen3 car with its vehicle endpoint. This predates the task. The plan's later `groupEndpoints` by `vehicleKey` replaces it, so it is a dependency to track, not a fix for this task.

**M7. A provider registration failure is logged misleadingly.** `TWCManager.py:815`: if `providerOrder.register` raises, the module is already registered but the log says "Could not register Gen3TWCs". Log the provider failure separately.

**M8. A failed registry update loses the plug edge for good.** `Gen3TWC.py`, `refreshVitals` near `:108`: `self._connected = connected` is set before `_plugEdges` runs, and `_plugEdges` sits inside a try/except that only logs. If `beginPlugSession` or `_correlate` raises once, the rising edge is spent: the car has no session until it is unplugged and plugged in again. Fix: set `_connected` only after `_plugEdges` returns, so the next fetch sees the edge again.

## Checks that passed

- **Threading.**
  - No HTTP runs outside `Gen3TWC.refreshVitals`, which only the `gen3Vitals` background branch reaches.
  - `solve`, `republish` and `demandAmps` read only the cache.
  - The lock order is `_targetLock` (RLock), then `_lock`, and is never reversed.
  - Registry calls happen outside our locks, and the registry uses its own RLock.
  - The cache dict is replaced whole, never mutated in place.
- **Water-fill basics.**
  - The bisection always runs exactly 20 steps, so it terminates.
  - `H` is clamped to `[0, min active fuse - MIN_AMPS]`, so every targeted unit has `h_i` in `[6, F_i]`.
  - Zero-target units are left out.
  - With every target at 0, `H` is the max fuse.
  - Damping holds the error to at most `DAMP_AMPS` of `h`, and it does not stall: a car-limited unit going unconstrained moves `h` by more than 1 A and republishes.
- **Disabled path.** With Gen3 disabled nothing changes: provider registration sits inside the `enabled` block.
- **Identity.**
  - `cloudVin` is checked first.
  - Candidates are filtered on recency, `twcVin is None` and `atHome`.
  - `endPlugSession` clears `twcVin` for attributed cars, so a car that has been correlated before can be a candidate again.
