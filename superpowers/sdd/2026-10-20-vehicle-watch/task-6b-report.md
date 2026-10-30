# Task 6b report

Status: DONE_WITH_CONCERNS (the line target was missed: Watch.py is 314, not ≤ 270)
Commit: 9d6d5084 on vehicle-model/phase6 (base 590db9aa), in scratchpad/wt-vm6. Not pushed.
Tests: full suite 2306 passed, 1 xfailed (BASE 2300 + 6 new). test_watch.py has 46 tests.
Lines: lib 26866 → 26869 (+3). Watch.py 311 → 314. No other lib file touched.

## Behaviour

1. **Return time by distance** (`_backAt`). The earliest return is the latest fix's time plus the straight-line distance from home divided by `watch.returnKph`, with a floor of 300 s. `returnKph` is a new setting, default 120. Distance is an equirectangular approximation (hypot of dlat and dlon·cos(home lat), × 111.2 km/deg). With no fix, or no home set, the run's start counts as the fix time and the distance as 0, so the wait is start + 300.
   - It is now one gate at the top of `_visit`, after the memo and ask bookkeeping and before anything is submitted. For any car with `where != HOME`, nothing runs until that time: no status check, ping, scan, charge read or location read. Asks and memos are still recorded, so nothing is lost.
   - A new fix from any source moves the time, because the gate reads `v.latest("lat"/"lon")`.
   - This replaces the 1800/3600 rule. `TeslaAPI.is_far_from_home` is kept because `update_vehicle_data`'s statusDeferral ladder still calls it (TeslaAPI.py:1888). Task 8 can delete both.
   - **No haversine or distance helper existed.** Presence has only the `_within` box test, and TeslaAPI has the 1.4° box. I wrote the 4-line distance inside `_backAt` using `master.getHomeLatLon()`. I did not turn `_within` into a circle, because that would change the home-radius behaviour.
2. **Owner location read**: the location read now runs if the first cloud READ_CHARGE candidate's price is 0 (Owner, CLOUD_FREE) or no scan is possible. Fleet (0.002) and Home Assistant (price None) keep the "only when no scan" rule. It still runs once per awake stretch (PARKED memo, cleared on sleep), only when AWAY_AWAKE, waits awayAwakeSecs after a failed read, and draws an EVENT token. `_locate` is folded into the tail of `_visit`.
3. **Lost where no scan can run**: in the ping job, when the second miss would have scanned (`again` and awake), the car is away, the ping went unanswered and `canScan()` is False, the job records `bleReach` False with source TeslaBLE and `seen=False`. That is how a scan miss is recorded, and the absent mark follows. Two misses are needed; one miss records nothing, as before. The car then follows the lost path: no pings, cloud status if it has one, otherwise the arrival scan. A no-scan install can't run that scan, so a BLE-only Docker car gets **nothing** after it is lost (see concerns).
4. **status()** takes the lost path into account and gains a `via` key: "ble", "cloud", "scan" or None.
   - A lost car with no cloud reports its scan record and the back-off cadence: scanAwaySecs while lately awake, else awayAsleepSecs.
   - A lost car with a cloud source reports the cloud status check.
   - A lost car on a no-scan install with no cloud reports why = "no status source".
   - For any away car, nextAt also respects the return gate.
   - `why` is now "" rather than None internally. The output keys are unchanged apart from `via`.

## Trim

- DEFAULTS went from 14 lines to 6.
- The four `_last` lookups in `_visit` are now one unpack over `KINDS`.
- The lost block's `settings` temporary and its per-branch `secs` are replaced by `_scanSecs`, which `status()` also uses.
- `_answer` is gone: a job's `done` turns `True` into the sleep state.
- The `claimed` list is gone, both its threading through every helper and the per-kind settle in `pass_`. `_submit` now settles if `submitJob` returns False. `queue.put` already reports dropped and replaced jobs through `done`.
- `pass_` no longer skips anonymous cars, because `notWatched` already says "anonymous".
- `_read` lost its `vin`/`settings`/`worker`/`providers` temporaries.
- `_backAt` no longer needs `api`, so `api` is only a "has TeslaAPI" flag.
- The cloud lost-car scan condition is unchanged: it still scans only once the cloud says the car is awake. Merging it into "not known asleep" would have changed the ruling's behaviour for cloud cars whose state is unknown.

## Tests

New tests:
- nothing runs before a car could be back: a 3-hour fix, boundary on each side, and a new fix inside the window moving the time
- the 300 s floor, boundary on each side
- an Owner car is located for free with a scan possible
- on a no-scan install, two unanswered pings lose the car, the miss is unseen, and the pings stop
- a known-asleep lost car with no cloud is not scanned
- `status()` for a lost BLE-only car (via "scan", nextAt = scan + scanAwaySecs)

The Fleet "no read while a scan is possible" case was already covered by `test_no_location_read_where_a_scan_can_hear_the_return`.

Mutation checks (each run against test_watch.py; every mutation caught):
- gate removed: 7 tests fail
- floor set to 0: 2
- distance replaced by a constant: 2
- Owner exemption removed: 1
- Fleet rule ignoring scans: 2
- no-scan observe removed: 1
- asleep return removed: 1
- status() scan branch removed: 1
- cloud-awake condition removed: 1

Existing tests adapted to the new rules:
- Away fixes are now old (`awayLong`) so the gate is open.
- `awayFleetCar`'s home is AWAY+0.5° (1668 s).
- Location-read tests take one more pass, because a gated car's first status check has to say awake before the read.
- The asleep window in the sleep test was lengthened so a status check runs after the gate.
- The restart test is now "waits the floor (300 s) from the start".
- test_watch.py was not black-formatted at base (house one-liner style) and I left it that way. Watch.py is black-clean.

## Concerns

1. **Line target missed.** Watch.py is 314; the target was ≤ 270. The trims above saved about 25 lines. The features cost about 28: the distance maths, the no-scan ping rule, the Owner exemption, and the lost path and `via` in status(). The file is now 222 code lines, 57 comment lines and 35 blank. Reaching 270 would need about 45 more lines cut, which means removing behaviour (the HA status source, the once-per-stretch memo, the cloud-awake scan rule) or gutting why-comments. I didn't do either without a ruling. lib Δ is +3 overall.
2. **The gate covers PRESUMED cars too** (`where != HOME`, the codebase's existing meaning of away). After a restart, a PRESUMED car with no fix gets its first check at start + 300 s, even if it is in fact home. A PRESUMED car driving inside the home radius waits 300 s from its fix. This follows the brief's restart rule, but it is a 5-minute startup delay for every car with no position.
3. **A lost BLE-only car on a no-scan install is never checked again by the watch.** It is found again only through other evidence: a TWC naming it, attribution pings when an unnamed TWC draws current, or a plug report. That is what "the pings stop" asked for. If a slow back-off ping is wanted instead (for example every awayAsleepSecs), it is about 3 lines.
4. A location read now comes one cadence after the gate opens for a car whose sleep state is unknown, because the status check has to say awake first. I kept the AWAY_AWAKE requirement so the watch never spends a token on a car it hasn't seen awake.
5. `status()["via"]` names the source that would run even for a covered or named car (watched False). This is harmless, but Task 9 should show `via` only when watched.

## Ruling on concern 4: a back-off ping for a lost car nothing else can hear

This was amended into the commit. The new SHA is in the reply.

- The lost block in `_visit` is shared. When a lost car is due on the back-off (`_scanSecs`: scanAwaySecs within awayAsleepSecs of lastLife, then awayAsleepSecs) and is past the return gate, it scans if a scan can run.
- If no scan can run, it has no status source (no cloud), and TeslaBLE is loaded, the same branch instead submits `ble.ping(vin, scan=False)` as job kind "scan". The job is stamped in the same "scan" record, and "scan" in busy blocks a second one.
- An answered ping records `bleReach` True, so the car is home again on BLE contact.
- `status()` now shows via "ble" for this path, with the back-off nextAt. It shows "scan" where a scan can run.
- Tests:
  - New: `test_a_lost_car_nothing_else_can_hear_is_pinged_on_the_scan_back_off`.
  - Updated: the no-scan lost test now checks that the 300 s status ping gives way to the back-off pings (2 + 4 + 3 over two hours).
  - Mutation check: removing the ping branch fails both tests.
- Full suite: 2307 passed, 1 xfailed.
- lib: 26873 (+7 vs 26866). Watch.py: 318.

## Review fix round 1 (task-6b-review.md)

Amended into the commit; the new SHA is in the reply.

- **F1, three test gaps closed.** Each test fails under the matching mutation:
  - `test_where_no_scan_can_run_two_misses_at_home_lose_nothing` fails when `where != HOME` is dropped from the ping closure.
  - `test_status_next_check_waits_for_the_return_time` fails when the gate is dropped from `status()`.
  - `test_a_lost_car_home_assistant_can_ask_is_not_pinged_on_the_back_off` fails when the back-off ping ignores the cloud.
- **F2, a fix moves the time even with no home set.** The time comes from the fix whenever one exists; only the distance needs a home. New test `test_with_no_home_a_new_fix_still_moves_the_return_time` fails without the change.
- **F3, Presence reused.** `_backAt` takes the fix time from Presence `_fix` and converts degrees with `_FT_PER_DEGREE / 3280.84`. The private 111.2 is gone, and the test helper `northOfHome` uses the same constant.
- **F4, nothing due for a lost car known asleep.** `status()` reports `nextAt` None for a lost car on the radio back-off (scan or ping) while it is known asleep, because nothing runs for it then. New test `test_status_shows_nothing_due_for_a_lost_car_known_asleep` fails without it.
- **F5, DEFAULTS left as `dict` + `.update` lines.** A plain literal is not shorter: black puts one entry per line, which comes to 15 lines against 6.
- **F6, test comment rephrased:** "the gate opens at 1668 s; the first status check says awake".
- **Size cuts:**
  - `Watch.settings()` is dropped, and its test uses `settingsOf`.
  - `_ble` is looked up once per visit and once per `status()`. The new module function `scans(ble)` replaces `_scans`.
  - "Has a cloud" is decided once in the lost block (`cloud = lost and _source(...)`), with no second `_source` call. The location read checks the TeslaAPI attachment directly.
  - `status()` works from a single `_source` result.
- **Behaviour note:** a lost car whose only cloud is Home Assistant now counts as having a cloud for the scan back-off. It scans every scanAwaySecs, but only while known awake, as a TeslaAPI car does. Before, it was treated as having no cloud. This follows "cloud status if it has one".
- **Results:** full suite 2312 passed, 1 xfailed. lib 26872 (+6 vs 26866). Watch.py 317.

## Review fix round 2 (HA-only lost car)

The new SHA is in the reply.

- **The fix:** in the scan/ping back-off, "has a cloud" now means a TeslaAPI attachment, the source that can report asleep or awake. The lost block decides it once, as `api = v.attachment("TeslaAPI") is not None`, which also gates the location read.
- **Effect on an HA-only lost car:** it follows the no-cloud back-off:
  - it scans where a scan can run, otherwise it gets the back-off ping;
  - it does so every scanAwaySecs while lately awake, then every awayAsleepSecs;
  - it isn't held to "known awake".

  Its status check still goes to Home Assistant.
- **Test:** `test_a_lost_car_only_home_assistant_can_ask_is_scanned_on_the_back_off` replaces the round 1 HA test. It sets up a lost car with no state reading: HA never reports state, so the car is never AWAY_AWAKE. The car is scanned at once, then again 1800 s later, and `status()` via is "cloud". The test fails on af892728: no scans.
- **Results:** full suite 2312 passed, 1 xfailed. lib 26871 (+5 vs 26866). Watch.py 316.
