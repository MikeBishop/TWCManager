# Phase 6 rebase onto fixed Phase 5, and the watch/hold follow-up

- Backup: `backup/phase6-pre-p5fix` = 198c94f3.
- `git rebase --onto 36e69be6 cf89bf5f vehicle-model/phase6`: 18 commits, rebased tip f9270375.
- Follow-up commit: b613a784 "Let the watch's status checks wake a held command". **New tip: b613a784.**

## Conflicts (each resolved on behaviour: both sides' rules kept)

1. ecca0092 (door ping), `Presence.checkPlug`: kept P5's `telemetryPlug(v, since, seen=True)` feed test and its "asleep, or not seen awake within REACH_WINDOW → plugged" rule, inside P6's `_ble(master)` + `ping(scan=...)` call, followed by P6's door-closed → unplugged.
2. ecca0092, `Presence.pick`: kept P6's `_ble` ping and door-closed check; the BLE charge read keeps P5's gate `asleep(v, now - REACH_WINDOW) is False` (P6 had `not asleep(v)`).
3. ecca0092, parity `realBle`: kept P5's `_ping` helper (observes "online" when ping is True) with P6's `scan=True` parameter.
4. 65bdc048 (away scan), Presence: kept P5's `covered()` next to P6's new `lastLife()` split of `asleep()`.
5. e202554c (watch replaces deferral ladder), `TeslaAPI.update_charge`: P6 deletes it, P5 only reworded its comment. Took the deletion; nothing calls it.
6. b8d3b828 / f3780011 (docs), CHANGELOG: P5's "A sleeping car is left alone" line (cloud online check, 15/30 min) replaces P6's BLE-only wording; P6's watch and door lines kept, each in its later version.

`git diff 198c94f3 f9270375` matches `git diff cf89bf5f 36e69be6`. The only extra changes are the merge points above.

## Follow-up (b613a784)

- `Reconciler._asleepCheckDue`: returns False when `master.watch` is set and `Watch.notWatched(master, v) is None`. In that case the watch's Ring 1 status checks refresh the car's sleep. A fresh awake reading counts as a sign of life after the hold, so the held command is planned again. A fresh asleep reading leaves it held. A car the watch leaves alone keeps P5's behaviour: a TWC-named car, the watch disabled, or an anonymous car still gets its own online check, and a feed-covered car still gets no checks.
- Single source: Watch `DEFAULTS` homeAsleepSecs/awayAsleepSecs now come from `Presence.HOME_ASLEEP_SECS` / `AWAY_ASLEEP_SECS`. `notWatched` now uses `Presence.covered()` instead of its own copy of the liveness check.
- New test `test_sleeping_car.py::test_a_watched_fleet_car_held_asleep_is_checked_only_by_the_watch`. It runs a Fleet-only watched car with the watch and reconciler together and holds the command 420 s off the watch's clock. Online GETs land at +60, +480 (the hold's own pre-flight check), +960, +1860, +2760, so one per 900 s. After the car wakes, the next watch check sends `set_charge_limit`. With the reconciler change reverted, the test fails because checks double (1380, 2280...).
- Docs: CHANGELOG sleeping-car line, Vehicle_TeslaBLE.md, and the Presence constant comment now say that the watch does the re-check, and that the online check is used only for cars the watch leaves alone.

## Verification

- Full suite at b613a784: 2377 passed, 1 xfailed.
- Full suite at the rebased tip f9270375 (before the follow-up): 2376 passed, 1 xfailed.
- Commits with resolved conflicts: ecca0092 2277 passed; 65bdc048 2329 passed; e202554c 2362 passed; b8d3b828 2367 passed; f3780011 2372 passed (all 1 xfailed).
- black: clean.

## Parity

The parity file is Phase 5's file plus Phase 6's additions. The only difference from Phase 5's own diff is the `scan=True` parameter on the `realBle` ping stub. The follow-up does not touch the parity file, and no parity count moved. Phase 5's sleeping-car tests keep their counts (4 checks at home, 2 away) because those tests run no watch (`master.watch` is None).

## Lib lines (.py under lib)

- cf89bf5f 26417, old P6 tip 198c94f3 26976 (+559).
- 36e69be6 26471, rebased f9270375 27032 (+561). The extra 2 lines are the `now` binding in checkPlug and its comment placement.
- b613a784 27036: the follow-up adds 4 lines (Reconciler +3, Watch +1).

## Concerns

- The watch skips every check for an away car until it could be back (`_backAt`). For a held command to an away, asleep, watched car, the re-check therefore waits up to the drive-time from the car's last fix. Phase 5 re-checked every 30 min. A sign of life from any other source still plans the command again.
- The watch's status check on a watched car prefers BLE (the sleep-safe ping) over the cloud. Either refreshes sleep, so a held Fleet command to a car in BLE range is woken by a BLE answer and gets no cloud GET.
- The watch's cadence can be configured (`watch.homeAsleepSecs`). A configured value now also sets how often a watched held command is re-checked. A car the watch leaves alone always uses the Presence constants.
