# Rebase report: vehicle-model stack onto origin/main (#699)

Date: 2026-10-17. Worktree: `scratchpad/wt-rebase` (on `rebase/phase3.5`). Nothing pushed. The `vehicle-model/*` branches were not changed, and no other worktree was touched.

## Result

| Branch | New tip | Commits | Unit suite | lib lines (orig → new) |
|---|---|---|---|---|
| origin/main | 03d79325 | — | — | 23,180 |
| rebase/phase1 | ec8790ca | 50 | 1165 passed, 1 xfailed (orig 1153 + 12 wake tests) | 25,394 → 25,443 (+49) |
| rebase/phase2 | 31e5d185 | 40 | 1338 passed, 1 xfailed (orig 1326 + 12) | 27,483 → 27,530 (+47) |
| rebase/phase3 | 1455ddba | 91 (90 + 1 new) | 1775 passed, 2 xfailed (orig 1764 + 11 wake tests; +1 xfail = row 4b) | 27,270 → 27,272 (+2) |
| rebase/phase3.5 | 6fcbd4a2 | 17 | 1860 passed, 2 xfailed (orig 1849 + 11; +1 xfail) | 27,376 → 27,377 (+1) |

All four tips are green. The stack is linear, and each tip has origin/main as an ancestor. Black `--check` passes on the only lib file that changed (`TeslaAPI.py`) at every tip. pyflakes reports nothing new compared with the original tips. `test_command_path_parity.py` has no removed or changed lines at phase3 or phase3.5: every existing row keeps its counts, and the only change is the added row 4b.

Diff of each new tip against its original tip: `CHANGELOG.md` (+2, #699's entries) and `TeslaAPI.py`. phase1/2 also add #699's `test_teslaapi_wake.py` (adapted). phase3/3.5 add the ported `test_teslaapi_wake.py` and parity row 4b. From phase3 on, the lib diff is only #699's telemetry rule inside the stack's `is_awake`/`onlineState` (about 30 lines changed, net +1/+2).

Method: `git rebase --update-refs --exec <check>` onto origin/main. After every commit the exec ran the wake, telemetry, registry, reads, provider, parity and reconciler-wake tests, plus any test file the commit touched. When an applied commit broke a #699 test without a textual conflict (1e02481e, 8bca9197, 098f7c80, 508d22ce), I amended the test fix into the commit that caused the break. The brief says to amend only to resolve a conflict; I treated these semantic breaks as conflicts so that every commit after them stays green. Commit messages are the originals. One new commit was added (row 4b).

`--update-refs` had also queued `refs/heads/deploy/phase35-live` (it pointed at the old 5c133bef). I removed it from the todo, so it is unchanged.

## Per-phase conflicts and resolutions

### Phase 1
- **985990d0** (back CarApiVehicle fields with the registry): content conflict in `is_awake`.
  - Kept #699's signature `(minInterval, telemetryNotBefore)` and its newest-observation-wins rule, written with the stack's `_telemetryState()` (registry `obs.at`, liveness-aware `age`) instead of `syncSource`/`syncTimestamp`.
  - Tie rule: `obs.at >= lastVehicleAwakeTime` (#699 used `>`). With this, telemetry wins when no GET has been made yet. The stack's "ruling 2" test (`test_sleeping_car_on_healthy_feed_stays_telemetry_sourced`, obs at 0.0) needs this.
  - Amended into the test: the fixture builds `VehicleRegistry(clock=test clock)`, and telemetry is seeded with `vehicle.observe("state", …, "TeslaMateVehicle", at=stamp)`, because this commit turns the `syncTimestamp` setter into a no-op.
- **1e02481e** (read through the registry cascade): no textual conflict. `update_location` now reads through the read cascade, so the fake BLE in `test_ble_read_does_not_move_wake_window` was never consulted. Amended: the test registers the fake as a `TeslaBLEReadSource` and claims the car.
- **ac202a1b** (attach telemetry by VIN): content conflict. The commit deletes the legacy sync setters right next to #699's `ready()` signature. Took the deletion and kept the signature.
- **8bca9197** (only a well-formed VIN becomes a registry vehicle): no textual conflict. #699's tests used `"VIN1"`, which the registry now refuses. Amended: the tests use `5YJ3E1EA1KF000001`.

### Phase 2
- **3f89dea3** (Owner/Fleet providers): `is_awake` conflict. The stack added `slot=`. Merged signature: `is_awake(minInterval=120, telemetryNotBefore=0, slot=None)`. The only caller that passes a slot does so by keyword.

### Phase 3
- **81dc39ba** (cloud provider commands): `is_awake` conflict. The stack re-plumbed `is_awake` (injected clock `now=`, `lastVehicleAwakeKnown`) but kept the **pre-#699** telemetry rule word for word. Merged result: the stack's plumbing plus #699's gate. See decision D1.
- **098f7c80** (412 retires commands; end an unasked charge need): two changes.
  - `is_awake` conflict: added the stack's `lastVehicleAwakeKnown = lastVehicleAwakeChecked` on the cache branch.
  - Semantic break: `_askChargeNeed` ends a charge need that nobody asked about for 600 s, so the BLE test's jump from +700 s to +1801 s started a fresh 3-minute hold. Amended: the test asks every minute through the hold and asserts no wake before +1800 s.
- **c563d703** (delete the legacy start/stop path): this is where `car_api_available`, the legacy wake path #699 patched, is deleted.
  - Took the deletion.
  - Removed the #699 pieces left with no callers: `POST_WAKE_CHECK_SECS`, `POST_WAKE_POLL_SECS`, `lastWakeSentTime`, and the `ready`/`is_awake` window parameters.
  - After this, `TeslaAPI.py` differs from the original commit only by #699's telemetry rule (16+/14−).
  - Rewrote `test_teslaapi_wake.py` against the Fleet provider's `wake()` → `wakeOutcome` (map below).
- **508d22ce** (remove test-only helpers): no textual conflict. It removed `getCarApiVehicles()`. Amended: the tests read `carApiVehicles[0]`.
- **New commit at the tip, 1455ddba**: parity row 4b (see below).

### Phase 3.5
- **f82744eb** (registry vehicle answers sync state): `is_awake` conflict. Kept the #699 gate, read through `vehicle.telemetryState()` and `Vehicle.SYNC_TIMEOUT`. The `TELEMETRY_SOURCES` import became unused and was removed.
- **7d946abd** (dissolve CarApiVehicle):
  - Import conflict: kept `READ_MAX_AGE` only.
  - `is_awake` became `TeslaAPI.onlineState(vehicle)`, again with the pre-#699 rule. Kept #699's gate, with newest-wins compared against `car.onlineCheckedAt`.
  - Wake tests adapted to the dissolved names.
- **6c4ba546** (trim after the dissolution): import conflict and the `onlineState` block again. Took the trimmed import and `vehicle.SYNC_TIMEOUT`, and kept the gate.
- **40f77cae**, **2facd2f7** (#659 changelog): CHANGELOG conflicts at the same insertion point. Kept #699's two entries and the stack's #659 entry, using the 2facd2f7 rewording that the commit intends.

Mutation check: with the stack's original `is_awake` (c563d703) or `onlineState` (7d946abd) restored, 4 of the 11 ported wake tests fail. Those four are the pre-wake telemetry test, the stale-telemetry rewake test, our-GET-wins, and stale-asleep falls through to the GET.

## Test-intent map: #699's `tests/unit/test_teslaapi_wake.py`

Phases 1–2 keep all 12 original tests passing on the legacy path. Phase 3 (c563d703) deletes the legacy path. From there the file is rewritten against the Fleet provider's `wake()` (`wakeOutcome`) and `is_awake`/`onlineState`. The original tests are deleted, and the file keeps its name.

| #699 test (intent) | Phase 3 / 3.5 test |
|---|---|
| `test_pre_wake_hold_unchanged`: first ask does one state check and holds without a wake; one wake after `wakeDelayMins` | `test_pre_wake_hold`. One difference: during the hold, free GETs run every 120 s (cache) instead of "no calls at all". Still free, and still no wake until the hold ends. |
| `test_car_online_after_offline_wake_is_noticed`: wake answers offline, car online at +2 min, noticed without a second wake, hold state reset | `test_car_online_after_offline_wake_is_noticed`: `wake()` returns SATISFIED "online" at +120 s, one `wake_up`, and `firstWakeAttemptTime`, `firstChargeNeededTime` and `delayNextWakeAttempt` back to 0 |
| `test_car_never_online_polls_in_window_then_waits`: free GETs only in the window, then exactly one more wake at +30 min | `test_car_never_online_checks_free_then_wakes_once_per_hold`. One free GET per 120 s for the whole 30-minute hold (15), no second wake until +1801 s, no `vehicle_data`. Accepted difference (Finding 1): 120 s instead of 60 s, for the whole hold instead of 10 minutes. |
| `test_fresh_telemetry_online_needs_no_request` | Same name: SATISFIED with no request, and the hold is cleared |
| `test_fresh_telemetry_asleep_needs_no_request` | Same name: "wake held" for 10 minutes with no request |
| `test_state_check_uses_owner_slot_when_present` | **Superseded** by `test_state_check_with_both_tokens_is_a_state_get`. `wakeOutcome` deliberately runs the free check on the command slot's account (Fleet) when that slot can read (its comment says so); both endpoints are unbilled. The port pins what matters: only the state GET, never `vehicle_data`. |
| `test_telemetry_from_before_wake_is_not_trusted` | Same name: TeslaMate "asleep" stamped before the wake loses to the GET; SATISFIED at +120 s with one wake. `telemetryNotBefore` is gone, and newest-wins against the GET made at wake time covers it. |
| `test_ble_read_does_not_move_wake_window` | **Superseded, flagged (D3).** The stack's wake hold is anchored on `lastAPIAccessTime`, which a BLE read moves (`_readFresh`). A BLE read inside the hold therefore extends it: fewer wakes, not more. #699's `lastWakeSentTime` anchor was not ported (no behaviour change beyond #699 on the legacy path). |
| `test_stale_telemetry_asleep_does_not_cause_rewakes`: hour-old "asleep", one wake in an hour | Same name, through `wake()`. Fails with the stack's original rule (2 wakes). |
| `test_fresh_telemetry_newer_than_our_get_is_trusted` | Same name, on `is_awake` |
| `test_our_get_newer_than_telemetry_wins` | Same name. Reformulated without `telemetryNotBefore`: the GET first, then older telemetry; the GET wins, and after the 120 s cache it GETs again |
| `test_stale_telemetry_asleep_falls_through_to_get` | Same name |

## New parity row (Finding 1): row 4b, `test_fleet_only_car_online_after_an_offline_wake_gets_the_limit`

Scenario: Fleet-only, car asleep, policy raise 50 → 80, `wake_up` answers offline, car reports online at +59 s. Assertions, as the brief wrote them: one `wake_up` in 30 minutes, `set_charge_limit` within 150 s of the wake, limit 80.

**It fails, so it is committed as `xfail(strict=True)`.** It will report XPASS and fail once the cause is fixed.

- Probe over 4 h: 1 free GET, 1 `wake_up`, **0 commands**.
- The desire record afterwards: `paidSends=1`, `paidReached=False`, `paidRetryDue=False`, `rearmed=False`, `lastOutcome=(unreachable, "wake offline")`.
- The result is identical on the original db475224, so the rebase did not cause it.
- Cause: the free online check only runs inside `wakeOutcome`, and the planner never plans another attempt.
  - `paidAgain` needs a reading that reached the car or a pending retry.
  - Fleet-only has no free provider to fall back to.
  - The blind retry never wakes.
- A same-value `setPolicyLimit` is not a new desire (`Desired.set`: "Unchanged"). In production the limit therefore stays stranded until something produces a reading that reaches the car.
- On main, #699's `car_api_available` reports the car available at +60–120 s (its `test_car_online_after_offline_wake_is_noticed`), so the limit goes out on the next `car_api_charge`.

## Needs a human decision

- **D1. Finding 1 misdescribes Phase 3's telemetry rule.** The merge plan says Phase 3's online check has "newest-observation-wins telemetry". It does not: phase3 and phase3.5 still trusted telemetry "asleep"/"offline" unconditionally, however stale. That is the bug #699's second CHANGELOG line fixes. Taking the stack's side would have quietly reverted that fix while the CHANGELOG still claims it. I treated it as "#699 code the stack didn't replace": I kept #699's rule inside the stack's plumbing (`is_awake` in phase3, `onlineState` in phase3.5).
  - Effect: with a dead or stale feed whose last word is "asleep", the reconciler's online check now makes the free state GET instead of answering asleep. That also reaches the Fleet stop's "asleep, not charging" shortcut.
  - Live and fresh feeds are unaffected, because registry age is liveness-aware. No parity row changed.
  - Tie choice: `obs.at >= lastGET`, so telemetry wins on equal stamps or when no GET has been made.
  - If you want the stack's original rule instead, drop the gate in `is_awake`/`onlineState`. 4 wake tests would then need to be deleted or inverted.
- **D2. Row 4b: a Fleet-only car that comes online after an offline wake never gets its limit at phase3 or 3.5.** This is a regression against main for exactly #699's live scenario. It is worse than main's pre-#699 behaviour: main used to re-wake after 30 minutes, and the stack never sends. The paid bound holds (one wake).
  - Fixing it means the planner has to plan a free-check-only attempt during the hold after a wake answers unreachable. That interacts with the I2/N1/M8 budget rules other rows pin, so it is outside this rebase's "no behaviour change" scope.
  - Options: fix it before the phase3 PR (row 4b turns XPASS → remove the xfail), or accept it and qualify the first #699 CHANGELOG entry ("Check for a car coming online after a Fleet API wake_up…"), which overclaims at the phase3/3.5 tips.
  - Note: the box is `ble_only`, so no live run will show this.
- **D3. A BLE read extends the post-wake hold** (wake test #8 superseded). This is the safe direction. Porting #699's `lastWakeSentTime` anchor into `wakeDue` and `wakeOutcome` would take about 3 lines if you want it.
- **D4. Accepted differences from #699**, as Finding 1 already listed: free check every 120 s instead of 60 s, polled through the whole 30-minute hold instead of 10 minutes, and a 30-minute wake hold. These only matter once D2 is fixed. Until then the check does not run again after the wake.
- **D5. `deploy/phase35-live`** still points at the old 5c133bef. Retarget it when you deploy the rebased 3.5.

## Left for the controller
- Branches `rebase/phase1..phase3.5` (tips above). The worktree `scratchpad/wt-rebase` is clean, on `rebase/phase3.5`. My temporary `wt-check` worktree has been removed. No background processes are running.
- Working notes: `scratchpad/rebase-notes.txt`. Per-commit check log: `scratchpad/rbtools/check.log`.
