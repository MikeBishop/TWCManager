# Task 5 report: Ring 2 on change

Status: DONE_WITH_CONCERNS. Commit `4d7d1ef2` on `vehicle-model/phase6` in wt-vm6, based on 1a1c0586. Not pushed.

## Numbers

- Full suite: **2281 passed, 1 xfailed**. BASE was 2269 + 1 xfailed; this task adds 12 tests.
- Lib lines: **26717 → 26817 (+100)**. `git diff --shortstat 1a1c0586 -- lib`: 1 file, +134/−34.
- Watch.py: **171 → 271 lines**. The first draft was 288; it was then trimmed.

## What was built (lib/TWCManager/Vehicle/Watch.py)

**Shape**
- **In-flight tracking is per (vin, kind).** Matching the plan's "one job per car per ring", `_inflight` holds `(vin, kind)` pairs; the queue already keys jobs by `(key, kind)`. A status job in flight therefore no longer blocks a read. The wake test needs this: a ping is still pending when the car wakes.
- **`_last` is keyed by `(vin, kind)`.** It holds `(answer, at)`, so the last read's time sits beside the status `lastAt` in the same dict instead of a separate `_lastRead`. `_settle(vin, kind, at, answer)` covers both kinds with no branch.
- **`_want[vin] = (cls, exempt)`** is the pending ask. `readNow` and transitions merge into it under the lock, and an event outranks a routine ask. `_take` drops only the exact ask that was acted on, so a concurrent `readNow` is not lost.

**Events.** Each pass compares the memo with what it saw last time:
- **Arrival:** presence becomes HOME. A car seen for the first time counts too, so each home car gets one read at startup.
- **Wake:** HOME_ASLEEP → HOME_AWAKE.
- **Plug-in:** `markAt("plugIn")` grows. This is the only event the courtesy window yields to, besides `readNow`.
- An event no newer than the last read is ignored: an arrival uses `decide()`'s deciding time, a plug-in uses its mark time. Without this, a read that reports `chargingState=Stopped` marks plugIn, and the watch would read the car again because of its own read.

**Read rules (`_read`)**
- An asleep car is never read. Its ask waits for the wake.
- An ask that is not exempt is dropped for a TWC-named car, and for a HOME_AWAKE car within `sleepCourtesySecs` of its last read.
- **Routine reads** happen only while HOME_CHARGING, or while a TWC-named car's TWC reports current (`_drawing`: Gen2 `reportedAmpsActual >= 1` or Gen3 `currentAmps >= 1` on the unit naming the car). The cadence is `chargingReadSecs`, or `cloudChargingReadSecs` for a cloud read of a car no TWC names. A car with no `SET_AMPS` candidate gets no routine reads.
- **Source:** the BLE worker with every ready local provider; otherwise the cloud queue with exactly the first ready cloud provider. Its `cost(READ_CHARGE).price or 0.0` is spent first. A refused spend logs DEBUG, stamps the read time (so the next try is one routine cadence later) and drops the ask.
- **Extra rule:** a non-named car of UNKNOWN sleep state is not read over BLE until a ping has answered. A cloud read asks the free online question itself. This guards the "never a wake" anti-goal, since I could not confirm that a BLE `state charge` never wakes a car.
- **The read job** runs `v.read("chargingState", 0, force=True, providers=...)`. For a cloud read it first sets `car.statusDeferral = 0`, as `Presence.checkPlug` already does.

**`readNow(vin, reason, cls=EVENT)`** is thread-safe. It logs DEBUG and the next pass submits the read.

## Tests

The 6 brief tests are in, with their assertions kept. Plumbing changes:
- `bleReads` now claims TeslaBLE on every registry car. `TeslaBLEProvider.ready` needs a claim, which means a paired key.
- `bleAnswers(m, answer=None)` is added to the BLE tests that ran an unstubbed ping, so they don't call the real `tesla-control` ping.
- `placeAt(m, v, HOME)` is added to the two cloud tests. Without a home location, presence is never HOME.
- The budget test also asserts `paid > 20`. Because of the real-time deferral (see concerns), it could otherwise pass while making no reads at all.

Added tests:
- the courtesy window yields to a plug-in and to `readNow`
- an asleep car is never read, and its arrival read waits for the wake
- a read-only car gets no routine reads
- a TWC-named car is not read for a wake
- an UNKNOWN car is pinged before a BLE read
- the cloud charging cadence is 900 s, not 300 s

I ran a mutation check on each rule: courtesy, spend, read-only, drawing, deferral reset, plug-in vs. last read, asleep, UNKNOWN+BLE, the cloud cadence and the named-car drop. Breaking any one of them fails at least one test.

## Concerns / deviations

1. **`status()["last"]` still holds the Ring 1 answer** ("asleep", "online", "no answer"). The brief says it should name the last job ("ping"/"status"/"read"/"scan"). I kept the answer because Task 4's tests assert `last == "asleep"` and `== ""`, and the spec's Vehicles tab shows the "last Ring 1 answer". Task 9 should decide.
2. **The deferral reset will clash with Task 8.** The watch's cloud read zeroes `car.statusDeferral` because `_TeslaAPIProvider.fetch` checks it on real `time.time()`; without the reset, `readNow` within 300 s of the arrival read returns stored values (brief test 5 fails). Task 8's planned `test_two_callers_inside_read_max_age_pay_once` expects a forced read inside 300 s to be deduplicated. Task 8 has to choose one of two things:
   - the watch keeps bypassing the dedupe, which could mean a double `vehicle_data` when a power-start `readNow` follows an arrival read;
   - `readNow` within 300 s is satisfied by the stored read.
3. **First sight counts as an arrival.** After a restart, every HOME car that is awake (or cloud-readable) gets one event read. For Fleet cars this is $0.002 per car per restart, from the event class.
4. **A covered or disabled car is never read, even on `readNow`.** A feed-covered car's feed already reports. Task 8's power-start `readNow` will therefore not read a feed-covered car.
5. **No read for a car with no ready read provider.** Its ask stays pending (harmless). An unclaimed BLE car with no cloud slot is never read.
6. Watch.py is 271 lines against the plan's ~220 for the whole module (Tasks 6, 7 and 9 still add to it). The growth here is the read rules themselves. I found no duplication to fold in beyond merging `_lastRead` into `_last`.

## Fix round 1 (amended: see SHA below)

Suite: 2287 passed, 1 xfailed. Lib: 26717 -> 26801 (+84; was +100). Watch.py: 255 lines (was 271).

- **R1:** the watch no longer touches `statusDeferral`; the read job is `v.read("chargingState", 0, force=True, providers=...)` with keywords. The cloud tests move both clocks through a `later(m, v, c, secs)` helper. New `test_a_forced_read_inside_the_cloud_dedupe_pays_nothing`: no paid request, deferral unchanged.
- **R2, refined:** `_started` is set after the first `pass_`; on that pass a car's memo is seeded with what it is now, so nothing is news. A car first seen later is compared with `(None, None, NEVER)` and gets its arrival read. New tests:
  - `test_a_restart_is_no_arrival` (BLE car, home, awake, plugged)
  - `test_a_restart_buys_no_cloud_read` (Fleet car, paid (0,0,0))
  - `test_a_car_first_seen_after_the_start_gets_its_arrival_read` (VIN2 named by a TWC mid-run, exactly one read)
- **Tests that relied on the first-sight read** got plumbing only:
  - a seeding `w.pass_()` before the TWC naming in the TWC tests
  - the courtesy test starts asleep and wakes
  - the charging test pre-observes Charging
  - the cloud tests start with `w.readNow(VIN, "start")`
  - the UNKNOWN test is driven by `readNow`
- **4:** `_drawing` is gone. A named car's routine read uses `Belief.standIn(v)`, renamed from `_standIn` (3 sites) because Watch now imports it. That is the newest TWC `actualCurrent` against `POWER_FLOWING_AMPS`. The test sets current with `v.observe("actualCurrent", n, "Gen2TWC", seen=False)`, as the heartbeat does.
- **5:** one `_submit(v, kind, run, worker, claimed)` handles both rings: it claims the job, submits it, and its `done` settles with the answer or "no answer". `_done`, `_check` and `_claim` are gone; the status branch in `_visit` is "source, else settle now, else `_submit`".
- **6:** chargingState is dropped from the memo.
- **7:** the restating comment is dropped. The price line is kept: inlining it into the spend condition costs as many lines after black.
- **8:** an ask is cleared for a car that is covered or disabled, but not for one a TWC names. New `test_a_covered_car_keeps_no_ask_for_later`: a `readNow` made while a feed covers the car does not fire once the feed drops.
- **9:** the coverage comment now sits on the status branch, where "only when due" holds.
- **13:**
  - The cloud tests give the budget a frozen clock, `WatchBudget(3.0, clock=lambda: 1000.0)`, so the `<= 26` bound is exact rather than an accident of real time.
  - New `test_a_refused_read_waits_the_routine_cadence`: once refused, it logs DEBUG "No budget", is not asked again on the next three passes (60 s apart), and is asked again after one cloud cadence.
- **Skipped:** 10, per the ruling.
- The mutation sweep was rerun on all rules, including the new ones (ask clearing, first-pass seeding, mid-run arrival, standIn, refusal stamp). Each one fails at least one test.
