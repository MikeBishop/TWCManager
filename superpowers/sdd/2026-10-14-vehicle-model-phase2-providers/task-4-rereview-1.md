# Task 4 re-review 1: Gen3 TWC provider fix round (7e2019b..84eb6fb)

**Verdict: APPROVED.** C1, C2 and I1 are addressed, and so are the fix-now minors (M1, M4, M7, M8). The minors left open are acceptable. The fix introduces no Critical or Important breakage. It adds one new Minor (N1).

Checkout: wt-vm2 at 84eb6fb. Focused tests: `tests/unit/test_gen3twc_provider.py tests/unit/test_twcmanager.py`, 58 passed. My own probe is `scratchpad/probe-t4/probe.py` (plus `m8.py`), outside the checkout. Every probe check passed: 0 failures.

## Findings

| ID | Status | Evidence |
|----|--------|----------|
| C1 | ADDRESSED | `republish` now publishes `watts=load*voltage*phases`. The probe compared against the pre-Phase-2 value `max(0, fuse*V*ph - W)` on 16/3/230, 32/3/230, 48/1/240 and 40/1/208, for targets of 6, 7.5, 10, fuse-1 and fuse A. Watts matched within 1 W in every case, and the derived headroom `fuse - watts/(V*ph)` equals the target. The all-zero stop publishes `fuse*V*ph` (zero headroom), both before and after vitals arrive. An over-fuse target publishes 0, as before. A 3-phase pair (16 A, 12 and 8 A targets, ramping) gets h=10 and publishes 6*230*3, and stops at the full fuse. |
| C2 | ADDRESSED | In `solve`, when `served(0) < wanted`, every demand is set to inf. One unit ramping at 1, 3, 5, 9, 12, 15 or 18.5 A under a 20 A target keeps h == 20, on 1-phase and 3-phase, and h stays within 1 A of 20 over later ramp cycles. A single unit whose car is really capped (8 A under 20 A) also gets h=20, which matches today. Two ramping units (20/10 A targets, at 5/4 A and then 12/9 A) get h=15. A capped unit beside an unconstrained one still frees its share (h=25). The fix has a known cost: when every targeted unit reports a finite demand, the car-limited reallocation is dropped. The result undershoots the net, which is the safe direction, and it is acceptable. |
| I1 | ADDRESSED | `Controller_Gen3TWCs.md` is updated on all four passages. Rate control now describes the water-fill, the 6 A floor, the 1 A damping, and a stop only when no sibling holds a target. State readback describes background, cache-only vitals; an unreachable unit is left out until a fetch succeeds; and a new section explains anonymous sessions and correlation. Multiple units: the total follows the sum of the targets, a zero-target unit cannot be stopped alone, and the limitation is reported when more than one unit is occupied, which matches `Gen3TWCProvider.limitations`. Limitations covers no VIN, the M3 exposures, shared headroom, and that nothing is verified on hardware. |
| M1 | ADDRESSED | `refreshVitals` skips fresh units. Covered by `test_refresh_skips_fresh_units`. |
| M4 | ADDRESSED (test-only) | 48 A and 32 A units, 30 A each: the net is 60 A and the 32 A unit keeps at least 6 A. |
| M7 | ADDRESSED | Provider registration has its own try block and log message. |
| M8 | ADDRESSED, with one new Minor (N1) | `_connected` is set only after `_plugEdges` returns. Covered by `test_a_failed_registry_update_retries_the_plug_edge`. |
| M2 | Left open: acceptable | This is inherent to the G2 design: a transient overshoot while a ramping car sits beside an unconstrained sibling. It should be tracked as a Task 7 item: count a unit as car-limited only after two readings agree. |
| M3 | Left open: acceptable | This is the brief's design (A27). It is now documented in Limitations. |
| M5 | Left open: acceptable | It is harmless: `setAmps` returns False, and `ready`/`ampsRange` agree within one snapshot. |
| M6 | Left open: acceptable | It predates this task. The charging-points `groupEndpoints` work replaces it, so it should be tracked as a dependency. |

## New breakage

**N1 (Minor). A partial success on the rising edge leaves an orphan anonymous vehicle.** `Gen3TWC.refreshVitals` / `_plugEdges`

Sequence:

1. The rising edge correlates the car: `observeTwcVin` succeeds, so the anon session is folded into the VIN.
2. An `observe` in the trailing `if connected:` block (`actualCurrent` or `voltage`) raises.
3. The next fetch replays the rising edge. `beginPlugSession` creates a new `anon:<point>` vehicle, and `_correlate` then finds no candidate, because the car already has `twcVin`.

Probe (`m8.py`):

- After the retry, `reg.vehicles()` is `[VIN, 'anon:Gen3TWC-10.0.0.1']`.
- `vehicleAt` and `vehicleKey` still return the VIN, because the attributed vehicle wins.
- Unplugging clears the orphan.

Impact: a phantom anonymous vehicle exists for the rest of the plug session. It is inert for control: `Gen3TWCProvider.ready` and `ampsRange` resolve through `_unitForKey`, which compares against `unit.vehicleKey`, and that key is the VIN, so the orphan is never ready and gets no range. It also needs a registry `observe` to raise after a successful correlation, which is unlikely. This makes the fix a nit, not a must.

Fix, for Task 7 or as a nit: on a replayed rising edge, skip `beginPlugSession` and `_correlate` when `registry.vehicleAt(pointId)` is already set. Alternatively, move the trailing observes out of the retry scope.

No other breakage:

- The solve's 20-step bisection is unchanged. A fuzz of 3000 random configurations (1-4 units, mixed fuses and phases, NaN/inf/negative/huge targets and readings, random states) always terminated in under 0.5 s. The load was always finite and within `[0, max fuse]`.
- Lock order is unchanged.

## Not code

- **`rising` can repeat.** After a failed edge, `noteVitals(self, rising=True)` is still called, and the retry calls it with `rising=True` again. That is harmless today, because `noteVitals` only republishes. Task 7 hooks its VIN reader here and must tolerate a repeated `rising`.
- **Release scope of the cloud VIN.** The docs say "A later release will also use the VIN reported by Tesla's cloud", but `_correlate` already checks `cloudVin` first. If Task 7 fills in `cloudVin` in this same release, that sentence is wrong when it ships. The coordinator should check this.
- **Brief erratum.** The brief and plan still say `setHouseWatts(watts=H * V, ...)` (task-4-brief.md:18). The coordinator should correct it to `H * V * phases`. The brief also says `refreshVitals()` fetches every device; M1 now deliberately deviates from that.
