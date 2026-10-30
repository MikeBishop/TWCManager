# Task 7 report: the consumption step

Status: DONE_WITH_CONCERNS (line budget overrun)
Commit: e3427248 on vehicle-model/phase6 (base e450d355), in scratchpad/wt-vm6. Not pushed.

## Tests
- tests/unit/test_watch_load_step.py: 6 passed. These are the 4 brief tests, verbatim, plus 2 new ones:
  - `test_a_step_up_reads_home_first_and_the_next_car_only_if_the_first_is_not_charging`. It runs once with the first read reporting Charging (1 read) and once with Stopped (2 reads). The HOME car is read before the PRESUMED one. The next car waits while the first's read is still in flight. An awake NOT_HOME car is never asked (checked through the debug log).
  - `test_a_flapping_load_reads_a_car_once_in_five_minutes`.
- Full suite: 2318 passed, 1 xfailed (BASE 2312 + 6).
- I mutated each rule and checked that a test fails: chain stop on Charging, HOME-first order, debounce, step-down read, subtract-only-when-configured, NOT_HOME exclusion, and waiting for the in-flight read. One exception is below.

## Size
- lib: 26871 -> 26950 (+79). The target was <= +40.
- Watch.py: 316 -> 390 (+74). TWCManager.py: +5.
- Breakdown: LoadStep 16; Watch.__init__ threshold/state 7; `_watched` 6; `unexplainedWatts` 12; `loadSample` 30; 1 import line; hook 5.
- I compacted it twice; the first draft was +88. What remains is mostly the step-up chain (about 9 lines) and the per-car, per-direction debounce (about 4 lines), both required by the brief. I found nothing in Watch.py the new code duplicates.

## What was built
- `LoadStep(threshold).sample(watts, now)` reports "up" or "down" once, when the sample after a step holds it. A spike that falls back says nothing. The baseline follows the load between steps. `now` is accepted for the interface but not used.
- Threshold: `max(emsNoiseWatts, (5 if phases<3 else 1) * defaultVoltage * phases)`, computed once in `__init__` from `config["config"]`.
- `unexplainedWatts()`: consumption, minus the following only when `subtractChargerLoad` is set:
  - `getChargerLoad()` (Gen2)
  - each reachable Gen3 unit's `convertAmpsToWatts(currentAmps)`
  - each watched HOME_CHARGING car's `actualCurrent`, converted through `VehicleEndpoint.currentVoltage`. The endpoint is built with `order=None`, since voltage does not use it.
- `loadSample()`: inert when `emsTrigger` is False. It is single-threaded (policy thread), and its chain and debounce state are touched only there. It reads `_want`/`_inflight` under the leaf lock. All reads go through `readNow(vin, "load step up|down")`.
  - Candidates: watched cars, HOME or PRESUMED, in HOME_AWAKE, AWAY_AWAKE (i.e. PRESUMED awake) or UNKNOWN. They are sorted HOME first, then by VIN.
  - On "up", the first candidate is asked. On a later sample, once its ask is taken and its read is no longer in flight: if it is HOME_CHARGING the chain stops, otherwise the next candidate is asked.
  - On "down", every HOME_CHARGING watched car is asked.
- `check_green_energy()` ends with `getattr(master, "watch", None)` -> `loadSample()`. I put it last rather than right after the EMS loop, so a fault in the watch never skips the offer. The `emsTrigger` check sits in `loadSample`, not in the hook, so no `settings()` accessor was added.

## Concerns / rulings made
1. **Debounce is per car and per direction**, not per car. The brief's own test reads the car on a step up and again on a step down 30 s later, which a plain per-car 5-minute debounce would block. Keying by (vin, "up"/"down") passes that test and still stops a flapping dryer: the up reads only non-charging cars and the down reads only charging ones.
2. **The dryer test does not depend on the asleep exclusion.** Adding HOME_ASLEEP to the candidates still passes, because `readNow` never reads an asleep car anyway. Without the filter, the held ask would fire at wake, and it would also stall the step-up chain. I kept the filter but have no test that pins it.
3. **The check_green_energy hook is untested.** No test imports TWCManager.py; it is a script module with globals. Also, nothing sets `master.watch` yet (no wiring exists on this base), so the hook is inert until that lands.
4. **Test isolation fix.** `TWCMaster.consumptionValues` is a class attribute shared across instances. In the full suite another test left 2691 W in it, which broke `test_known_draw_...`. I added an autouse fixture in the new file that monkeypatches a fresh dict. This is test plumbing only; the shared class dict is a latent lib bug for any multi-master test.
5. **Possible double count.** A watched car charging on a TWC that does not report its VIN is counted twice when subtracting. That is the TWC's amps plus the car's `actualCurrent`, a minor over-subtraction. TWC-named cars are not watched, so they are never double counted.

## Fix round 1 (amended into ef261dda)

- Size: lib 26871 -> 26932 (+61, was +79). Watch.py 371 (was 390).
- Full suite: 2319 passed, 1 xfailed. There are 7 tests in test_watch_load_step.py.

Applied:
- **1A + 1G: the chain is gone.** A step up now asks every candidate at once, the same way a step down does: watched cars in HOME_AWAKE, AWAY_AWAKE or UNKNOWN, all through `readNow`. The `_chain` field, the `_want`/`_inflight` wait and the HOME-first sort are removed. The brief's step-up test is unchanged and still passes: the awake home car is read on the step up, and the charging car is read on the step down.
- **1B: one loop.** `loadSample` is now a single loop over the watched cars, filtered by direction, presence, return time and debounce.
- **1C: one voltage for the whole sum.** `unexplainedWatts` adds up the known amps first: Gen3 `currentAmps`, plus `actualCurrent` for each watched HOME_CHARGING car. It then subtracts `getChargerLoad()` and `m.convertAmpsToWatts(amps)`. The VehicleEndpoint import and the throwaway endpoints are gone.
- **1D: threshold from the master's voltage.** The threshold now uses `master.getVoltageMeasurement()`, which falls back to `defaultVoltage`/`numberOfPhases`. The state comment is now 2 lines and names the background-tasks thread.
- **1E: shorter hook.** It is now `if getattr(master, "watch", None): master.watch.loadSample()`.
- **1F: tighter LoadStep.** The step is computed from a single `moved` value, saving one line.
- **2: inert without a meter.** The guard is `emsTrigger and master.consumptionValues`.
  - Test: `test_with_no_meter_the_known_draw_alone_makes_no_step`. It has subtractChargerLoad set and a charging car whose current goes from 0 to 20 A, and asserts that no read is asked.
- **3: a car not home waits for its return time.** A candidate not at HOME is asked only when `now >= _backAt(v, now)`, and a NOT_HOME car is never asked.
  - Test: `test_a_car_not_home_is_asked_only_once_it_could_be_back`. Within its return time, the PRESUMED car is not asked and the home car is. After 300 s the PRESUMED car is asked. The NOT_HOME car is never asked, even after its return time has passed.
- **4: the asleep filter is pinned.** The dryer test now also asserts that no "asked" line appears in the log.
- **5: the meter dicts are per instance.** `TWCMaster.__init__` now creates its own `consumptionValues`, `generationValues` and `consumptionAmpsValues`. The class-level defaults stay for `__new__`-built test masters. The test fixture is removed.

Mutation checks; each mutation fails at least one test:
- asleep added to the candidates
- the consumptionValues guard removed
- the `_backAt` gate removed
- the NOT_HOME filter removed
- the debounce removed
- `subtractChargerLoad` ignored
- the shared dicts restored (fails in combination with the other unit tests)

Accepted as is, per ruling: 7 (double count on a TWC that cannot name its car) and 8 (stale baseline across polling gaps). `LoadStep.sample`'s `now` stays unused.
