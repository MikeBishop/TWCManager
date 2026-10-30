# Task 6 report: Ring 0 for away cars, the away location read

**Status:** DONE_WITH_CONCERNS (only concern: 4 lines over the +35 target)
**Commit:** dba72feb on vehicle-model/phase6 (base 46adfe70), in wt-vm6. Not pushed.
**Tests:** full suite 2290 passed, 1 xfailed (base 2287 + 3 new). test_watch.py: 31 passed.
**Lines:** lib 26801 -> 26840 (+39). Watch.py 255 -> 294.

## What changed (Watch.py)

- **Scan on the second miss.** There is no new scheduling path and no miss counter. The previous status answer in `_last` already holds the miss state: `last == MISS` ("no answer") means the previous ping went unanswered. `_source(v, again)` passes the TeslaBLE module into `_answer` as `scan` when the previous ping missed. On the worker, if the ping also goes unanswered and `asleep(v) is False`, it runs `ble.scanForVehicleInRange(vin)`. The scan records `bleReach` itself. A miss while asleep (or of unknown sleep state) runs no scan and records nothing.
- **Scan cadence.** `_cadence(AWAY_AWAKE)` uses `scanAwaySecs` when `_scans()` (TeslaBLE loaded and `canScan()`). So an away, awake car gets its ping-then-scan every 150 s, and `status()['nextAt']` shows the same cadence.
- **Location read (`_locate`, kind "locate", through `_submit`).** It runs only when the situation is AWAY_AWAKE, the car is watched, no scan is possible, TeslaAPI is loaded and attached, and a non-local READ_CHARGE provider exists. Timing:
  - The first read of an episode waits until `max(lat.at, lon.at) + (3600 if api.is_far_from_home(lat, lon) else 1800)`.
  - After that, it reads again only if the last answer was not `PARKED`, and then after `awayAwakeSecs`. Non-parked answers are a `DRIVING` answer (shiftState D/R/N), a failed read (`MISS`), and a budget refusal.
  - The episode ends when a pass sees the car in an asleep situation. That pass pops the `(vin, "locate")` stamp, so no state-history scan is needed.
  - The read is EVENT class and is charged against the budget. It uses `v.read("lat", 0, force=True, providers=[cloud])`, so it honours statusDeferral and never resets it.
- **Shared read path.** The charge read's tail (price, budget spend, refusal settle, submit) is now `_fetch(v, kind, field, providers, cls, now, claimed)`, which `_read` and `_locate` both use. The job returns DRIVING/PARKED, or None when nothing was read. The charge read's answer is unused, as before.

## Tests

- The three brief tests were added verbatim in their assertions.
- `test_a_miss_while_asleep_records_nothing` passed before the change. It guards against a regression and was not a red test.
- Plumbing changes in the location test:
  1. Home is set 1 degree north of the fix (`m.settings.update(homeLat=AWAY[0] + 1, homeLon=AWAY[1])`). With no home, `is_far_from_home` measures against (10000, 10000), and with `placeAt`'s HOME, AWAY is 1.6 degrees of longitude away. Both give 3600 s, not the 1800 the brief's assertion expects.
  2. `later(m, v, c, 300)` is used in place of `c.t += 300`. Otherwise TeslaAPI's real-time statusDeferral dedupe makes a second read cost nothing, and the "once per episode" assertion could not fail. I confirmed this by mutation: with plain `c.t`, removing the episode rule still passed. With `later`, removing either the episode rule or the return-time rule fails the test.
- `reconcile_helpers.bleScans` also stubs `canScan` to return True. This box has no bluetoothctl, so the real `canScan()` would return False.

## Concerns / deviations

1. **+39 against the ≤+35 target.** Over half of the added lines are `_locate` (about 20). I folded what I could: `_fetch` is shared, the scan is folded into `_answer`, the miss state reuses the status answer, and the episode reuses the `_last` stamp.
2. **The scan is not its own job kind.** It runs inside the status job, right after the missed ping, on the BLE worker. So it does not go through `_submit` as kind "scan" and does not coalesce with TeslaBLE's own `(vin, "scan")` jobs. A separate kind would need a second record of the miss (or a two-step answer) to know that the miss was the second in a row. That costs more lines and adds a second scheduling decision. Each away, awake miss therefore holds the BLE worker for a ping timeout plus SCAN_SECONDS.
3. **A driving answer re-reads after `awayAwakeSecs` without waiting for the return time again** (brief taken literally). A long drive away can cost a paid read every 5 min until the car parks or sleeps, capped by the budget. If that is unwanted, the alternative is to wait `max(at + awayAwakeSecs, fixAt + return time)`.
4. **The episode reset depends on a pass seeing an asleep situation.** A sleep and wake that both land between two passes would not reset it. Passes run every few seconds, so this is negligible.
5. `_scans()` uses `getattr(module, "canScan", bool)()`, so a missing module, or a scripted stand-in without `canScan`, counts as "no scan".

## Fix round 1 (amended: bbaf8105)

**Lines:** lib 26801 -> 26845 (+44). Watch.py 299.
**Tests:** full suite 2296 passed, 1 xfailed, 1 warning. The warning is transient: it showed up in one earlier run and was gone on the rerun. test_watch.py: 37 passed.

### Findings

- **F1, driving ruling.** The rule is now the same for every location read: no read before the return time from the newest fix (1800 or 3600 s), counted from `max(lat.at, lon.at)`, so a driving read's own fix sets the next one. `awayAwakeSecs` is now only a retry floor after a failed read (MISS) or a budget refusal (""). A PARKED answer ends the episode.
- **F2, failed reads.** `_fetch`'s job calls `master.providerOrder.read(v, field, False, providers)`. That returns None when the read fails, so a failure counts as MISS and is retried after `awayAwakeSecs`. The charge read uses the same call.
- **F3, ruling on a lost car.** A car counts as lost when `where != HOME and v.value("bleReach") is False`.
  - **Status check:** for a lost car, `_source(v, again, lost)` skips the BLE ping. It uses the cloud status check when TeslaAPI is attached. With no cloud there is no source, and the status check settles empty.
  - **Arrival scan:** a lost car that is not AWAY_ASLEEP and that a scan can reach gets a `"scan"` job every `scanAwaySecs`. The job is `ble.scanForVehicleInRange(vin)`, sent through `_submit`, so it coalesces with TeslaBLE's own `(vin, "scan")` job. I run this scan job whether or not the car has a cloud status check. Without it, a car with a cloud attachment where a scan is possible would have no arrival detection at all, because the location read is gated off whenever a scan is possible.
  - **Cadence:** the scanAway cadence override is gone, so an away, awake car's status check runs every `awayAwakeSecs` (300).
  - **Second miss:** this now uses the reviewer's fold. The ping is called with `scan=again and asleep(v) is False`, evaluated when the pass decides, and `_runPing` runs the scan on a miss. `_answer` is back to its original form.
- **F5, tests.** Added (a) a driving read re-reads at the fix plus 1800 s, not after 300 s; (b) sleep ends the episode, and the next wake reads again; (c) no location read is paid when a scan is possible, and a BLE-lost car's status check moves to the cloud; (d) a failed read is retried after `awayAwakeSecs`. Also added: a BLE-only lost car gets scans, not pings, every `scanAwaySecs`; and the restart rule from F6.
  - Each new test was checked by mutation and fails on its mutation. The mutations: skip the fix rule for DRIVING; remove the episode pop; drop `self._scans()` in `_locate`; use `v.read` instead of `providerOrder.read`; drop `not lost`; set the no-fix fallback to NEVER.
  - The location tests share two helpers, `awayFleetCar` and `passes`.
- **F6, ruling.** `self._started` now stores the time of the first pass (None before it). A car with no fix uses `self._started or now` as its fix time, with `far=False`, so the first read waits 1800 s from the start of the run.
- **F8.** Not done: caching `canScan` was not free in lines. After the rework, `_scans()` runs only inside `_locate` (after its cheaper gates) and for lost cars.
- **Size cuts.** `_locate` takes the reviewer's shape, including the one-line cloud pick. The scan is folded into the ping. Despite these, the ruling's lost-car path, at about 8 lines, outweighs the cuts: the net is +5 against the first version.

### Test plumbing

`bleAnswers`' scripted ping now behaves like the real one: when there is no answer and a scan was asked for, it runs a scan, but only a scripted one. It finds that scan through `vars(module)`, which only sees a stub added by `bleScans`, so a test can never start bluetoothctl. In that case it returns `scan is True`. Without a scripted scan it returns `answer` as before.

### Concern

At +44, this is 9 over the +35 target. Watch.py is 299 lines. The trim pass the coordinator has already ruled for status(), the `_visit` lock block and DEFAULTS is needed before Task 7. One candidate for it: in `_visit`, the four `self._last.get` lookups (read, status, locate, scan) could become a single lookup.

## Fix round 2 (amended: 590db9aa)

**Lines:** lib 26801 -> 26866 (+65 for the task; +21 this round against bbaf8105's 26845, over the ≤+15 target). Per file this round: TeslaBLE about +7, Presence +5, Watch about +9. Watch.py: 311 lines.
**Tests:** full suite 2300 passed, 1 xfailed, 1 warning (the same transient warning as before). test_watch.py: 40 passed. test_teslable_pairing_status.py: 98 passed.

### Back-off (ruling plus clarification)

- **Lost car with a cloud status source (TeslaAPI attached).** The cloud status check decides awake or asleep. While asleep there are no scans. While awake there are no scans before `_backAt`, then one every `scanAwaySecs`.
  - `_backAt(v, api, now)` is the one helper that both this path and `_locate` use for the return time: the latest fix + 1800 s, or + 3600 s when `is_far_from_home`. With no fix, it counts from the run's start.
- **Lost car with no cloud.** It is scanned every `scanAwaySecs` while `now < lastLife(v) + awayAsleepSecs`, and every `awayAsleepSecs` after that. The 1800 s window comes from `awayAsleepSecs`, so there is no new setting. A car known asleep (AWAY_ASLEEP) is not scanned.
- **`Presence.lastLife(v)`.** This is the sign-of-life max that `asleep()` already computed: a seen state that is not asleep or offline, the `lifeAt` mark, and current drawn. It is now a function that `asleep()` uses, and the watch uses it too.
  - The `absent` mark is deliberately not counted. Every asked miss re-marks it, so the window would never close.
- **Location read.** It now runs only with a cloud source, through the same `api` the scan path uses. It is still off whenever a scan is possible.

### Shared scan (TeslaBLE)

- **`scanForVehicleInRange(vins)`** takes one VIN or several. One bluetoothctl run matches by local name every asked VIN and every registry car with a well-formed VIN.
  - Address lookup: `_bluezAddresses()` now returns {name: macs} from a single `bluetoothctl devices` call. It runs only if some car was not matched by name and something was heard.
  - Asked VINs get the existing hit, miss or unknown recording. Other cars are recorded only on a hit (`_noteScan` and `bleReach` True), never as a miss.
  - Return value: True if any asked car is in range, None on failure, False otherwise. A single VIN behaves as before.
- **`requestRangeScan`** now queues one job per radio (key "radio", kind "scan"). A request already pending is replaced, never dropped. `_scanRequested()` scans every VIN requested up to the moment it runs, and keeps the page's pending/in-progress bookkeeping.
- **The watch** calls `ble.requestRangeScan(vin)` for each due car and stamps `(vin, "scan")` at request time. Every due car in a pass therefore shares one bluetoothctl run, coalescing with the page's Scan button and with other cars' requests.
  - Deviation: the watch's scan stamp is the request time, not the completion. Nothing is in flight on the watch's side, and TeslaBLE's own pending guard and 10 s debounce prevent double requests.
- **Existing tests updated for the new semantics:**
  - P17 is renamed `test_requests_share_one_scan_of_every_pending_vin`: one job, one scan of {VIN, VIN2}.
  - The mid-scan tests now expect a set per run.
  - The debounce test now expects the job key ("radio", "scan").

### New tests

Each was checked by mutation (gates removed, back-off removed or forced slow):

- `test_a_car_not_asked_for_is_recorded_only_when_heard` (TeslaBLE, real parser): a sighting is recorded for the other car, and a miss never is.
- `test_one_scan_answers_for_every_car_due_one`: two lost cars give one scan of {VIN, VIN2}, and both are settled.
- `test_a_lost_car_with_no_cloud_scans_often_only_while_lately_awake`: fast scanning to 1800 s after life, then one scan per 1800 s, then fast again after a new sign of life.
- `test_a_lost_car_with_a_cloud_source_is_scanned_awake_once_it_could_be_back`: no scan while asleep, even though the old fix's return time had already passed. No scan while awake before the new fix's return time. Scans after it, and no paid read.

### Concern

Lib is +21 this round, over the target of 15. The cloud-versus-no-cloud split adds about 8 lines in `_visit`, and `lastLife` costs 5 in Presence. Watch.py at 311 makes the trim pass before Task 7 a necessity.
