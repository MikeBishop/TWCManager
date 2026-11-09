# Task 4 report: suspicion and the free poll

Status: DONE_WITH_CONCERNS (all tests pass; concerns below are about scope and definitions, not failures)

Commit: 24e56de3 `feat: poll the free snapshot while a Fleet-only car may be charging` (BASE 00a9c0f4)

## What was done

lib/TWCManager/Vehicle/Watch.py (+~110 lines, -3):
- `DEFAULTS`: `pollSecs=60`, `pollGiveUpSecs=600`. `KINDS` gains `"poll"`. Constants `CACHED`, `ASLEEP`, `STEP_SECS=600`.
- `fleetOnly(master, v, deaf=False)` (module function): `cloudOnly`, or with `deaf=True` (the watch's last status answer was `TWICE`, the `_read` deaf path) a watched car with a TeslaAPI attachment. **In both cases it also requires the car's first cloud charge read (not local, not the cached provider) to have a price.** See concern 1.
- `snapshot(v, cutoff)` (module function): builds a `Snapshot` from the `FleetAPICached` source's own registry readings when its `chargingState` stamp is >= cutoff; a field whose stamp differs from the snapshot's counts as missing (None). watts = actualCurrent * voltage * (phases or 1).
- `Watch.__init__`: `self._suspect = {}` (vin -> (since, why)), `self.ledger = ChargeLedger(clock)`.
- `Watch.suspect(vin, at, why)`: logs DEBUG `"Suspect %s since %s: %s"`, keeps the earliest T (and that T's why).
- `Watch.liveWatts(vin)`: `master.convertAmpsToWatts(believedAmps(v))`.
- `Watch._deaf(vin)`; `chargingAmps(ledgered=False)` now filters with `fleetOnly(master, v, self._deaf(vin))`.
- `_visit`: unpacks `polled` from `_last[(vin, "poll")]`; for a `fleetOnly` car, `_poll(...)` runs before the away-car early return (so the Review Focus 1 path is reachable).
- `_poll`: drops the suspicion when asleep or at `since + pollGiveUpSecs`; asleep also `ledger.end(vin)`. Otherwise cutoff = suspicion T, else `ledger.lastStamp(vin)` (session-only); none -> nothing. Every `pollSecs` it submits a `"poll"` job on the cloud worker: one `providerOrder.read(v, "chargingState", False, ["FleetAPICached"], cutoff=cutoff)` (no wait), then `snapshot(v, cutoff)`. A snapshot closes the suspicion (if its T <= stamp); it is fed to `ledger.observe` unless it is `Charging`, no session is open, and `presence != HOME`. startHint = T when why starts with "load step" and stamp - T <= 600. Any ledger change queues `{"cmd": "saveSettings"}`. A fetch failure settles as a miss; cadence is by settle time.
- `_read`: for a `fleetOnly` car, after the retry/courtesy-drop logic, returns unless `want and (fix or deaf or tried in RETRY)`; when it proceeds, `fix = True` (pays directly; no snapshot-first). So the event pay-if-stale branch and the routine `cloudChargingReadSecs` read no longer run for Fleet-only cars. Both remain live for TWC-named cars read through the cloud, so no code was dead to delete.
- Reused `ASLEEP` for the two existing `(HOME_ASLEEP, AWAY_ASLEEP)` tuples.

lib/TWCManager/Vehicle/ChargeLedger.py (+6): `lastStamp(vin)` = the open session's newest snapshot stamp, None with none open.

## Tests

New: tests/unit/test_watch_poll.py (10 tests: the 9 in the brief plus `test_a_suspicion_keeps_its_earliest_time`); tests/unit/test_charge_ledger.py `test_last_stamp_is_the_open_sessions_newest_snapshot`.

RED:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_poll.py tests/unit/test_charge_ledger.py
FAILED tests/unit/test_watch_poll.py::test_a_suspicion_polls_until_a_newer_snapshot_and_pays_nothing
FAILED tests/unit/test_watch_poll.py::test_the_poll_gives_up_without_paying
FAILED tests/unit/test_watch_poll.py::test_a_suspicion_keeps_its_earliest_time
FAILED tests/unit/test_watch_poll.py::test_a_session_polls_each_minute_and_ends_on_a_closing_snapshot
FAILED tests/unit/test_watch_poll.py::test_an_asleep_car_is_never_polled_and_its_session_ends
FAILED tests/unit/test_watch_poll.py::test_no_routine_paid_read_while_a_fleet_only_car_charges
FAILED tests/unit/test_watch_poll.py::test_a_snapshot_charging_away_opens_no_session
FAILED tests/unit/test_watch_poll.py::test_fetch_errors_keep_the_cadence_and_never_pause_the_slot
FAILED tests/unit/test_watch_poll.py::test_a_snapshot_stamped_just_before_the_suspicion_is_not_taken
FAILED tests/unit/test_watch_poll.py::test_a_ble_car_in_range_is_unchanged - ...
FAILED tests/unit/test_charge_ledger.py::test_last_stamp_is_the_open_sessions_newest_snapshot
======================== 11 failed, 12 passed in 1.47s =========================
errors: 10x AttributeError: 'Watch' object has no attribute 'suspect'; 1x AttributeError: 'ChargeLedger' object has no attribute 'lastStamp'
```

GREEN (new tests): `23 passed in 1.45s`.

After implementing, all watch tests (first run, before fleetOnly excluded free reads):
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch*.py
13 failed, 99 passed  (incl. Owner-API free-read tests -> led to concern 1)
```
After the paid-read condition in fleetOnly: 10 failed (the retired paid reads + Task 3's patch of cloudOnly). After changing those tests:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch*.py
============================= 112 passed in 2.66s ==============================
```
Full suite:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration
============ 2619 passed, 1 xfailed, 1 warning in 305.98s (0:05:05) ============
```

Review Focus coverage: 1 `test_a_snapshot_charging_away_opens_no_session`; 4 `test_fetch_errors_keep_the_cadence_and_never_pause_the_slot` (429, 404, ConnectTimeout, then a good answer on the 4th minute; asserts `fleetSlot.usable("read")` and `pausedUntil == 0`; 412 not tested: it latches `cachedRefused`, after which the provider is not ready and polls settle as misses); 5 `test_a_snapshot_stamped_just_before_the_suspicion_is_not_taken` (stamp T-2, polling continues, T+150 taken).

## Existing tests changed (none deleted)

- test_watch.py: new helpers `namedFleetCar` (chargingFleetCar + a Gen2 TWC naming it with 24 A flowing) and `twcNames`.
  - `test_cloud_reads_draw_from_the_budget_and_stop_at_the_floor`, `test_a_refused_read_waits_the_routine_cadence`: now on `namedFleetCar`. Their intent (budget floor / refusal on routine paid reads) is preserved where routine paid cloud reads still exist: TWC-named cars read through the cloud.
  - `test_cloud_reads_while_charging_run_on_the_slower_cadence` -> renamed `test_a_fleet_only_car_charging_is_polled_instead_of_read_on_the_cloud_cadence`: same car and timeline, `suspect` instead of `readNow`, expects 0 paid and 2 cached polls (404 snapshot, given up at 600 s). The named-car cadence is already covered by `test_a_twc_named_car_read_through_the_cloud_waits_the_cloud_cadence`.
  - `test_a_failed_read_asked_for_is_tried_once_more_a_cadence_later`: the car is now TWC-named (a Fleet-only car's `readNow` no longer pays, so retry mechanics are tested on the car class that still has them).
- test_watch_cached.py: `firstRead` and `test_watch_cadence_ignores_the_cached_provider` use `namedFleetCar`. The snapshot-first-then-pay logic still lives in `_read` for named cars, so those five tests keep their intent unchanged otherwise.
- test_watch_load_step.py: Task 3's `test_without_the_ledger_a_cloud_only_car_is_left_out...` -> `..._a_fleet_only_car_...`, patching `fleetOnly` instead of `cloudOnly`.

## Concerns

1. **fleetOnly excludes free-read (Owner API) cars.** `cloudOnly` includes Owner-token cars; their charge read is free and live, and the cached endpoint answers 412 to Owner. Without the price condition, `test_read_now_is_an_event_read_even_for_a_read_only_car`, `test_a_read_only_car_gets_no_routine_reads`, `test_an_owner_api_car_charging_is_read_on_the_free_cadence` and `test_watch_reads_a_free_owner_car_live_without_the_cached_provider` failed. Their intent could not be kept by switching them to polls, so I narrowed the definition: Fleet-only = cloud-read *and paid*. Consequence for Task 6: `chargingAmps(ledgered=False)` keeps Owner-only cars in the buckets (live reads), which seems right but differs from Task 3's `cloudOnly` filter. fleetOnly calls `providerOrder.candidates` per car; while the Fleet slot is unusable (paused) a car drops out of fleetOnly.
2. **deaf is watch state, not vehicle state.** `fleetOnly(master, v)` cannot see the `TWICE` answer, so it takes `deaf=False` by default; the watch passes `last == TWICE` (in `_visit`/`_read`) and `self._deaf(vin)` (in `chargingAmps`). Task 5 callers outside the watch (e.g. `afterWrite`) should use the watch's view if they need deaf BLE cars; a `Watch.fleetOnly(v)` method would be one line if wanted. A BLE car `lost` (bleReach False, away) is not counted Fleet-only: its reads go over the radio, not the cloud.
3. **Until Task 5, today's triggers for Fleet-only cars do nothing**: load-step / arrival / plug-in / door / power-start asks reach `_read` and return early (no `fix`), and their want stays in `_want` until the next wake or courtesy read takes it. Exception: a deaf BLE car's wants still pay (the deaf condition lets any want through, which is what keeps the "two unanswered pings" location read).
4. **Fleet-only car believed charging with no session and no suspicion** (e.g. after a restart before Task 6 restores the ledger, or a deaf BLE car) is neither polled nor read until it sleeps or a trigger suspects it. For a cloudOnly car the free status check ends it at sleep; for a deaf BLE car the BLE ping cannot see sleep, so it can stay HOME_CHARGING until Task 5's staleness check or another trigger. Polling while `state == HOME_CHARGING` would close this; I kept to the brief.
5. The suspicion keeps the earliest T and *that* T's why: a wake followed by a load step keeps the wake, so no startHint; the session then starts by energy/power instead.
6. A poll counts a cached snapshot already in the registry (fetched by e.g. the reconciler's pre-write read) even when its own fetch fails; intended, noted for review.

---

## Fix round 1 (commit 2c94fc75 `fix: keep paid reads out of Fleet-only detection and sessions from orphaning`)

Changes (lib/TWCManager/Vehicle/Watch.py, +33 -17):
- Important 1: new `self._locate` set, filled beside `_unheard` when the "two unanswered pings" ask is made and cleared when the car answers. The Fleet-only gate in `_read` is now `want and (fix or locate or tried in RETRY)`; `locate` is consumed when it passes. A deaf car's load-step, plug-in or door asks no longer pay.
- Important 2a: `fleetOnly` prices by the tokens held: `TeslaAPI.fleetTokenHeld() and not ownerTokenHeld()`, not by ready candidates. A read pause no longer changes the car's class. (`ownerTokenHeld` already ignores read pauses.)
- Important 2b: in `_visit`, a car that is not `fleetOnly` has its suspicion dropped and any open ledger session ended (save queued if it changed). Covers a deaf BLE car heard again and a car becoming covered or named.
- Ruling: `_poll` takes `where`; a poll is submitted only when `where == HOME` or a ledger session is open. The apply-time presence check stays, and its comment now says the car may have left after the poll was asked.
- Comment on the deaf ping ask updated ("charging, its charge is read or polled").

Tests (tests/unit/test_watch_poll.py, now 14):
- `test_an_away_car_is_not_polled` (new; ruling).
- `test_a_snapshot_charging_away_opens_no_session` rewritten for the apply-time check: suspected at home, the poll is submitted, the car is moved away before the job runs, and no session opens.
- `test_a_paused_fleet_slot_keeps_the_car_fleet_only_and_its_session`: Fleet slot paused mid-session. `fleetOnly` stays True, the session stays open and is left out of `chargingAmps(ledgered=False)`. After the pause lifts and the car sleeps, the session ends.
- `test_a_deaf_car_pays_nothing_for_a_detection_ask`: a deaf BLE car gets its one location read (paid 1). Then a load-step ask and a plug-in-style (non-exempt) ask follow, and paid stays 1.
- `test_a_deaf_car_heard_again_ends_its_session`: a deaf car's session is opened by a poll. The ping answers again and the session is ended.

RED (new tests against the previous lib; lib-only revert, then restored from a saved patch):
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_poll.py
E   assert (1 == 0)
E   assert (False)
E    +  where False = fleetOnly(<TWCMaster ...>, <Vehicle ...>)
E   assert 2 == 1
E   AssertionError: assert not True
E    +  where True = isOpen('5YJ3E1EA1KF000001')
FAILED tests/unit/test_watch_poll.py::test_an_away_car_is_not_polled - assert...
FAILED tests/unit/test_watch_poll.py::test_a_paused_fleet_slot_keeps_the_car_fleet_only_and_its_session
FAILED tests/unit/test_watch_poll.py::test_a_deaf_car_pays_nothing_for_a_detection_ask
FAILED tests/unit/test_watch_poll.py::test_a_deaf_car_heard_again_ends_its_session
========================= 4 failed, 10 passed in 1.41s =========================
```
(The rewritten apply-time test passes on both: the presence check already existed.)

GREEN:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch*.py tests/unit/test_charge_ledger.py
============================= 129 passed in 2.68s ==============================
$ PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration
============ 2623 passed, 1 xfailed, 1 warning in 305.09s (0:05:05) ============
```

Remaining notes:
- Concerns 1 (the fleetOnly class is now decided by the tokens held), 2 and 3 to 6 from the first round still stand.
- A car whose Fleet token is gone (not merely paused) leaves the Fleet-only class, and its session ends at its last snapshot.
- An in-flight poll that completes after its car left the class could reopen a session for one pass; the next visit ends it.
