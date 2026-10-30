# Task 6b: Distance-scaled return time, Owner location read, and a trim pass over Watch.py

Added by the controller after Task 6 (user decisions 2026-10-20). Base: 590db9aa. Watch.py is 311 lines; the plan budgeted ~220 for the whole module including Task 7 (the consumption step, still to come).

## Behaviour (user decisions)

1. **Return time scales with distance.** Earliest return = the latest fix's time + straight-line distance from home ÷ an assumed speed, with a floor of 300 s. The speed is a `watch` setting, default 120 km/h (75 mph). The user's reasoning: real roads aren't straight, so straight-line distance at that speed is an early estimate even for fast drivers.
   - Until that time, nothing runs for that car from any source: no ping, scan, status check or read.
   - A new fix from any source, a feed included, moves the time.
   - With no fix, the run's start counts as the fix time (the existing restart rule).
   - This replaces the 1800/3600 s `is_far_from_home` rule in `_backAt`. Keep `is_far_from_home` only if something else still calls it (grep); Task 8 may delete it.
   - The home location and the haversine/distance helper already exist (TeslaAPI or Presence). Reuse them; don't add a second one.
2. **Owner API is a free source for the away location read.** A car whose cloud read path for `lat` is the Owner API gets the location read even where a scan is possible. The Owner read draws a zero-price token, so it is paced but free. Fleet's paid read keeps the "only when no scan is possible" rule. Everything else is unchanged: once per awake stretch, never while asleep, after the return time.
3. **A car is lost even where no scan is possible.** Today a BLE install with `canScan()` False (Docker, no bluetoothctl) can never mark an away car lost, so it pings that car every awayAwakeSecs with a 15 s timeout forever. Make two consecutive unanswered pings of an away car count as lost, the same rule as two scan misses. Recording `bleReach` False the way the scan does is acceptable if that is the existing meaning; check Presence's rules for one miss vs two. The car then follows the lost-car path: cloud status if it has one, otherwise the back-off.
4. **`status()` reports the lost path.** A lost car shows the cadence and source actually in use, not a ping cadence.

## Trim pass (the main point; target Watch.py ≤ 270 lines after 1–4)

- Merge the four `self._last.get` lookups in `_visit` into one (≈ −2).
- In the lost block, drop the `settings` temporary and set `secs` per branch (≈ −2).
- Re-check `status()`, the `_visit` lock block and DEFAULTS for duplication.
- Look for helpers with one caller, comments that restate the code, and branches that 1–3 make redundant. The distance rule should replace code, not add beside it.
- Don't move complexity into other modules to shrink Watch.py; report the whole lib Δ.

## Tests

- Return time by distance, at the boundary on each side. Include a 3-hour fix: nothing runs for 3 h, and a new fix inside that window moves the time.
- Owner: the location read runs even with a scan possible. Fleet: no location read while a scan is possible.
- Docker/no-scan: two unanswered pings mark the car lost, and the pings stop.
- A known-asleep lost car with no cloud source gets no scans (the gate on `seen[0] != AWAY_ASLEEP` is untested today).
- `status()` for a lost BLE-only car.
- Each new test must fail when its rule is removed. Check by mutating the code.

## Constraints

- Python 3.8. Run black on touched files.
- Comment rule: comments say why the code is what it is. No history, and no phase, task or ruling IDs.
- Never bare `git stash`.
- One commit: "Wait for a car's earliest possible return; read an away car's position free over the Owner API". End the message with the Co-Authored-By trailer.
- Report lib lines before and after (BASE 26866) and Watch.py lines.
