# Task 5 review: Ring 2 on change (1a1c0586..4d7d1ef2)

**Spec compliance: PASS once the two rulings are applied** (both currently violated, by design of the implementer, before the rulings existed).
**Quality: APPROVE WITH CHANGES.** The logic is sound and the anti-goals hold. Size is the main problem: Watch.py is 271 lines, and about 30 of them can go with no change in behaviour.

(I could not run pytest in this environment because neither python nor pytest is installed in the worktree. The implementer reports 2281 passed + 1 xfailed.)

## Anti-goals (checked against `_read` / `_visit`)

| Anti-goal | Holds? | Where |
|---|---|---|
| Never wakes | Yes | `v.read(..., force=True)` passes no `allowWake`. The cloud `fetch` asks `is_awake` (free) before `vehicle_data`. BLE: an asleep state returns at line 167. UNKNOWN + local + unnamed waits for the ping (line 181). A named car of unknown state is read only for a plug-in, a `readNow` or current flowing, and each of those means the car is awake. |
| Never keeps awake | Yes | A non-exempt ask on a HOME_AWAKE car is dropped inside `sleepCourtesySecs` (171). Routine reads happen only while HOME_CHARGING or while the TWC is drawing current, and charging holds the car awake anyway. A stale HOME_CHARGING costs at most one more read, because that read reports the new state. |
| Never reads a car known asleep | Yes | Line 167 covers both HOME_ASLEEP and AWAY_ASLEEP. The ask stays queued until the wake. |
| Paid reads only through the budget, with the right class | Yes | `spend(price, cls)` runs before any cloud job. The class is the ask's class (EVENT outranks), else ROUTINE. Note: the token is spent even when `fetch` then answers from the deferral or finds the car asleep. That is conservative and acceptable. |
| TWC-named car read only while current flows | Yes, plus the spec's exceptions | A non-exempt ask (arrival, wake) is dropped for a named car. Routine reads need `_drawing`. Exempt asks (plug-in, `readNow`) are allowed, as the spec's arrival paragraph and F11 require. |

## Rulings: what must change

### R1. Watch reads must not zero `statusDeferral`
- **Code:** delete lines 199–206 (`car = ...`, the `run` closure and its comment). Submit `lambda: v.read("chargingState", 0, force=True, providers=providers)` directly. Saves **about 7 lines**.
- **Tests:** three tests passed only because of the reset: the budget/floor test, the slower-cloud-cadence test, and (before R2) the read-only `readNow` test. The fix belongs in the test's time, as the ruling says. Add one helper to `test_watch.py` that moves both clocks together:
  ```python
  def later(m, v, c, secs):
      # the cloud dedupe runs on real time; age it with the test clock
      c.t += secs; car = v.attachment("TeslaAPI"); car.statusDeferral -= secs
  ```
  Use it in place of `c.t += 900` / `c.t = 1000 + ...` in the two cloud cadence tests. A gap under 300 s then still dedupes, as it would in production.
- **New test pinning R1:** a Fleet car at home with `statusDeferral = time.time() + 300`. Call `readNow`, run the pass and the cloud queue, then assert that no paid `vehicle_data` was made and the deferral is unchanged. This fails if the reset comes back.

### R2. First sight after a restart is not an arrival
- **Code:** in `_visit`, line 141 becomes `was = self._seen.get(vin, seen)`. A first sight then equals itself: no wake, no arrival and no plug-in growth. This is net 0 lines, and the `(None, None, NEVER, None)` default goes away.
- **Open question for the controller (Important):** as written, R2 also suppresses the arrival read for a car that **first appears mid-run**. Examples are a new VIN that a TWC names (a visitor's car) and a car newly listed on the account. When such a car's first sight already has its plug-in mark, it never gets the read that the spec's "Arrival read" paragraph requires. If the ruling is meant only for restarts, seed only on the first pass after start:
  ```python
  # __init__: self._started = False ; end of pass_: self._started = True
  was = self._seen.get(vin) or (seen if not self._started else (None, None, NEVER, None))
  ```
  This costs +2 lines. Add a test for it: a second car is added to the registry after the first pass, a TWC names it and reports a plug, and it gets exactly one read.
- **Tests that relied on the first-sight read** (each needs plumbing only, with assertions kept):
  - TWC plug-in arrival, TWC-named while current flows, TWC-named not read for a wake: add one `w.pass_()` before `observeTwcVin` / plug-in, so the plug-in is a change.
  - Courtesy yields to plug-in/readNow: start the car asleep, seed, then wake it, so the "arrival read" becomes the wake read.
  - Charging car on the cadence: `v.observe("chargingState", "Charging", "TeslaBLE")` before the first pass. The first read is then routine, which also pins that a restart keeps reading a charging car.
  - Budget/floor and slower cloud cadence: seed first, then `w.readNow(VIN, "start")`, or pre-observe `chargingState` Charging, so the first paid read has a cause.
  - UNKNOWN pinged before a radio read: drive it with `w.readNow` on an UNKNOWN car. This is the realistic case, matching Task 7's EMS read of an "unknown sleep state" car.
  - The read-only `readNow` test works unchanged, because the first pass now makes no read.
- **New test pinning R2:** a BLE car that is HOME, awake and plugged (persisted mark), and a Fleet car at HOME. The first pass of a fresh `Watch` makes 0 BLE reads and paid `(0,0,0)`.

## Ranked findings

1. **[Ruling R1] The deferral reset must go.** See above: −7 lines, two tests move to `later()`, and one new test.
2. **[Ruling R2] First-sight seeding** needs `self._seen.get(vin, seen)`. Six tests need a seeding pass or a cause, and one new test pins the ruling.
3. **[Important] R2 as written also drops the arrival read of a car first seen mid-run.** This contradicts the spec's arrival paragraph. Seed only on the first pass (+2 lines) unless the controller says otherwise.
4. **[Size] `_drawing` duplicates the TWC current that the TWCs already put in the registry** (`TWCSlave` line 638 for Gen2, `Gen3TWC` line 235: `actualCurrent` from Gen2TWC/Gen3TWC). `Belief._standIn(v)` already turns the newest TWC current into Charging/Stopped against `POWER_FLOWING_AMPS`. Replace the 12-line method with `flow = _standIn(v); flow is not None and flow.value == "Charging"` (make it public if preferred). The test then sets current with `v.observe("actualCurrent", 24, "Gen2TWC")` instead of poking `s.reportedAmpsActual`. **About −10 lines**, and it uses one threshold for "current flowing".
5. **[Size] The two rings duplicate the claim → submit → settle-on-done path.** Add one `_submit(vin, kind, run, worker, claimed, want=None)` that claims, submits and settles in `done` with `answer = r if isinstance(r, str) else "no answer"`. `_done` is deleted (5 lines). `_check` becomes "source or settle-now, else `_submit`", and the read's submit block shrinks. **About −8 lines.**
6. **[Size/dead] `seen[3]` (chargingState) is never read.** `situation` already reflects it. Drop line 139's second element and fold the line in: **−1**.
7. **[Size] `price` is computed on the BLE path too, and the comment at 176–177 restates line 185.** Compute the price inside the cloud spend condition and drop the comment: **about −3**.
8. **[Minor/behaviour] Asks pile up for a feed-covered or disabled car.** `_visit` records arrival and plug-in asks before `notWatched`, so a covered car's ask from days ago fires a paid EVENT read when its feed drops. Clear `_want[vin]` when `why` is set and the car is not named, or compute `why` before the asks. About +1 line.
9. **[Comment] Lines 154–155 ("acted on only when a job is due") no longer hold.** `_read` acts on `why` every pass. Reword or drop it (−2).
10. **[Size, optional] `_inflight` could fold into `_last`** (`at=None` meaning in flight), which removes a structure and the `busy` comprehension. About −3. Weigh this against clarity for Task 6's third kind ("scan").
11. **[Rule check] The implementer's rule is correct and needed (UNKNOWN + local + unnamed → ping before a BLE read).** A car with no answered ping is either out of range, where a BLE read costs the command timeout, or of unknown sleep state, and nothing verifies that `state charge` never wakes a car. The rule holds the ask rather than dropping it, so the read follows the next answered ping. Named cars are rightly excluded: a plug-in or current flow proves the car is awake. The one cost is up to one UNKNOWN cadence (300 s) of delay for a Task 7 EMS read of an unpinged BLE car. If that matters, Task 7 can make the status check due immediately on such an ask.
12. **[Rule check] In-flight tracking per (vin, kind) is correct.** It is the plan's "one job per car per ring" (ring = job kind), it matches the queue's (key, kind) dedupe, and it generalizes to Task 6's scan. Both kinds share the one BLE worker, so they still run one after the other.
13. **[Tests] The tests are meaningful.** The per-rule mutation sweep in the report is credible: each rule has a test that fails without it. Two weaknesses:
    - The budget test depends on `WatchBudget` running on real time (no refill during the test). Comment that, or pass a test clock, so the `<= 26` bound is not an accident of real time.
    - There is no test that an event ask refused by the budget is dropped and not retried. Either pin that behaviour or note it as intended ("reschedules at the routine cadence").
14. **[Comment rule] No history comments found.** The test comments are fine.

**Size total:** findings 4–7, 9 and 10 save about −27 to −30 lines. With R1's −7 and finding 3's +2, Watch.py lands at about 240 before Tasks 6–7. That is still above the plan's ~220 for the whole module, so the controller should expect Tasks 6–7 to need equal discipline, or should re-baseline.
