# Task 7 review: the consumption step (e450d355..e3427248)

Reviewer: opus, read-only. Tests were not re-run here (no pytest in the system python); the 6 passing tests and the mutation results are taken from the implementer's report.

## Verdicts

- **Spec compliance: PASS with one Important gap.** The trigger is not inert without a meter (finding 2). Everything else matches the spec's "EMS trigger" section and the brief. That covers the step held for two samples, the threshold, subtraction only when `subtractChargerLoad` is set, HOME-before-PRESUMED order, stopping at the first car that reports Charging, the step down reading charging cars, the 5-minute debounce, the EVENT class, and never waking a car.
- **Quality: CHANGES REQUESTED.** Size is the headline: lib grew +79 against a +40 target, and Watch.py is now 390 lines. A ≤+40 design that keeps the spec's behaviour does not exist. About −17 to −22 is available (to roughly +57..+62), and two of those cuts also fix bugs. Re-baselining needs a controller ruling, as in Task 6b.

## Ranked findings

### 1. Size: the cuts available (Important)
These are concrete estimates against the current code. Black-formatted line counts are approximate.

| # | Change | Lines |
|---|---|---|
| A | Drop the chain's wait on `_want`/`_inflight` (the 3-line `with self._lock` block and the `done` computation). The brief says the next car is "checked on the following pass", which means the next sample 30 s later, not when the read completes. The wait is also a bug: a candidate whose ask is never taken stalls the chain until the next "up" step. That happens to an UNKNOWN car on BLE, which `_read` holds until a ping says awake, and to a PRESUMED car before its return time, whose `_visit` returns early (finding 3). Replace it with: on each sample, if the head of `_chain` is now HOME_CHARGING, clear the chain; otherwise pop it and ask the next. A slow read costs at most one extra read, which the debounce bounds. | −4 |
| B | Merge the up/down/chain branches of `loadSample` into one `due` list (sketch below). | −3 |
| C | `unexplainedWatts`: sum the amps, not per-endpoint watts. `amps = Σ gen3 u.currentAmps + Σ actualCurrent of watched HOME_CHARGING cars`; `return cons − getChargerLoad() − m.convertAmpsToWatts(amps)`. This drops the `VehicleEndpoint` import and the throwaway `VehicleEndpoint(v, None, m)` objects. The master's voltage (measured Gen2 voltage, else the config default) is accurate enough for a ≥1.2 kW step detector. The brief named per-unit voltage, so the controller must accept this deviation. | −6 |
| D | Threshold from `m.getVoltageMeasurement()`, which already falls back to `defaultVoltage`/`numberOfPhases`, instead of reading `cfg` by hand. Trim the 3-line state comment to 1 line; it also names the wrong thread (finding 6). | −2 |
| E | Hook: `if getattr(master, "watch", None):` / `master.watch.loadSample()` plus the comment. | −1 |
| F | `LoadStep`: it is already tight. Folding the step expression saves about 1 line, and black will rewrap it. | −1 |
| **Total, spec kept** | | **≈ −17 → about +62** |
| G (needs a spec ruling) | Drop the step-up chain: on "up", read every candidate at once, exactly as "down" does. This removes `_chain`, the head check and one test. Cost: one extra read per additional awake HOME/PRESUMED candidate per step. Those reads are free over BLE and draw EVENT tokens over the cloud, under the 5-minute debounce. Multi-car households with several awake cars at home are the only case where it matters. | −5 more → about +57 |

Not worth pursuing:
- **Reusing `_last[(vin, "read")]` for the debounce.** The brief's own test fails with it: the wake read happens right before the step, and the step-down read comes 30 s after the step-up read. The per-(vin, direction) `_triggered` dict costs 2 lines and is the cheapest correct form.
- **"Let the next step pick the next car".** A held step moves `LoadStep`'s base to the new level, so a persisting unexplained load never fires again. The second car would never be read. It is either the chain (A) or read-all (G).
- **`master.chargingPoints()`.** It would group Gen2, Gen3 and car endpoints and de-duplicate them, but endpoints expose no common amps accessor (`currentAmps` on VehicleEndpoint was dropped in Task 2), and `vehicleEndpoints` excludes read-only cars.

Sketch of `loadSample` after A+B (about 18 lines against 30):
```python
if not (self._settings["emsTrigger"] and m.consumptionValues):   # finding 2
    return
now = ...; step = self._step.sample(self.unexplainedWatts(), now)
cars = sorted((w != HOME, v.vin, s) for v, w, s in self._watched()
              if w == HOME or w != NOT_HOME and now >= self._backAt(v, now))  # finding 3
charging = {vin for _, vin, s in cars if s == HOME_CHARGING}
maybe = (HOME_AWAKE, AWAY_AWAKE, UNKNOWN) if step == "up" else (HOME_CHARGING,)
calm = [vin for _, vin, s in cars if step and s in maybe
        and now >= self._triggered.get((vin, step), NEVER) + 300]
if step == "up":
    self._chain, due = calm[1:], calm[:1]
elif step == "down":
    due = calm
else:
    stop = not self._chain or self._last_asked in charging   # or keep the head in _chain[0]
    due, self._chain = ([], []) if stop else (self._chain[:1], self._chain[1:])
for vin in due: stamp; readNow(vin, "load step " + (step or "up"))
```

### 2. Not inert without a meter (Important, spec)
Spec: "Needs a consumption value … with none it is inert"; `emsTrigger` is "default true when a consumption source exists". `DEFAULTS` sets `emsTrigger=True` unconditionally. `getConsumption()` with no EMS values returns 0. With `subtractChargerLoad` set (a config that only makes sense with a meter, but is legal without one), `unexplainedWatts` = `0 − chargerLoad − gen3 − cars`. Every charger start or stop then becomes a "down" or "up" step, and so a spurious read. That needs Track Green Energy or `maxAmpsAllowedFromGrid`/`alwaysPollEMS`, since only those queue `checkGreenEnergy`. **Fix:** fold `m.consumptionValues` into the guard (0 lines). Pin it with a test: no EMS value, subtractChargerLoad True, a Gen3 or charging-car step → no ask.

### 3. A PRESUMED car before its return time gets a stale, possibly paid read (Important)
`presence` returns PRESUMED for a **driving** car whose last fix is inside the radius, and situation AWAY_AWAKE makes it a candidate. `readNow` on it is held, because `_visit` returns before `_read` while `now < _backAt`. The ask then fires at the return time as an EVENT read, cloud and paid, long after the step. It also stalls the current chain (A). The Task 6b ruling already gates PRESUMED by the return time, and the progress note says "readNow on an away car waits for the return time (Tasks 7/9)". **Fix:** include a non-HOME candidate only when `now >= self._backAt(v, now)` (0–1 line). Test: a driving PRESUMED car is not asked.

### 4. The asleep filter is not pinned (Important, tests)
As reported, adding HOME_ASLEEP or AWAY_ASLEEP to `maybe` keeps every test green, because `readNow` never reads an asleep car. The rule still matters: the held ask fires a read at the next wake, a wake the dryer did not cause. Before fix A it also stalls the chain. **Fix:** in the dryer test, assert that the watch holds no ask for the car (`vin not in w._want`) or that the "Read of … asked" debug line is absent. The 6-car test already uses caplog this way. 0 lib lines.

### 5. `TWCMaster.consumptionValues` is shared (Minor, lib)
Confirmed. `consumptionValues`, `consumptionAmpsValues` and `generationValues` are mutable class-level dicts (TWCMaster.py:67–70) that `setConsumption` and friends mutate in place. Every instance shares them. Production builds one master, so this only bites tests, but it is a real latent bug. `__init__` already has an "Instance-level mutable state" block (TWCMaster.py:114). **Smallest fix:** one line there, `self.consumptionValues, self.consumptionAmpsValues, self.generationValues = {}, {}, {}` (+1 lib). Then delete the test's `ownMeter` autouse fixture (−4 test lines).

### 6. Thread named wrongly in the comments (Minor)
`check_green_energy` runs on the **background-tasks thread** (`background_tasks_thread` → `"checkGreenEnergy"`, queued by `Policy`), not on "the policy thread". The safety claim still holds. `_step`, `_chain` and `_triggered` are touched only there. `_want` and `_inflight` are read under the leaf lock. `readNow` takes the lock itself. There is no I/O: `gen3.allEVSEs` only queues a fetch. That thread already catches and logs exceptions, so the "last, so a fault … never costs the offer" placement holds. Fix the `__init__` comment's wording (folded into D).

### 7. Double count on a TWC that cannot name its car (Minor)
Confirmed and bounded. A watched car charging on a blind Gen2 or Gen3 TWC is subtracted twice: once as the TWC's amps and once as its own `actualCurrent` once a read says Charging. The effect: the read that sets Charging causes a fake "down" step and a re-read of that car. At the end of the session, the TWC drops while the car is still HOME_CHARGING, so a "down" read follows, and once the car reads Complete a fake "up" step reads the awake candidates again. That is at most about 2 extra reads per session, under the debounce, and usually free over BLE. Options: accept it, or skip the car terms while `_blindTWCs(m)[0]` is non-empty (+0–1 line, reusing the existing VehicleEndpoint helper). Recommend accepting it, with a one-line docs or controller note, unless C is taken, in which case fold the guard in.

### 8. Stale baseline across polling gaps (Minor, accept)
`checkGreenEnergy` runs only under green policies, `maxAmpsAllowedFromGrid` or `alwaysPollEMS`. When polling resumes, say the next morning, the first sample is compared with the last baseline from hours earlier. If both differ by the threshold and agree, that is one spurious step and one read. `now` is accepted but unused. Resetting `_base` when `now − lastSample > 2 × policyCheckInterval` costs +2. Recommend accepting the cost (at most one read per resume) and not adding lines.

### 9. Hook placement and the untested hook (accept)
The brief says "after the EMS loop"; the implementer put the hook after the offer. That is better, since the offer is computed first and nothing between the loop and the hook changes consumption, and it is equivalent for detection. The hook is untested because TWCManager.py is a script module, and inert until `master.watch` is wired. The wiring task must add an end-to-end check.

### 10. Comment rule (pass)
No comment describes history. All of them explain why. The one wrong fact is the thread name (finding 6).
