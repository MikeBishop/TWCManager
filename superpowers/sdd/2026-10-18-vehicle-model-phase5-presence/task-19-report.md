# Task 19 report: a Gen2 status change means "check the car"

Commit **c4636385** "Check the car on a Gen2 status change instead of filtering unplugs" on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent f5c6a769). Not pushed. The box was only read (journal), never changed.

## Ruling requests (read first)

1. **Lib delta is +2 against a target of ≤ −20. This is a miss.**
   - Cut: `unplugStep` with its 3 constants and 5 state fields, the anonymous idle/grace/short-run fallback, the `anonEndedAt` flicker guard, the `newSlave` re-link reset, and the telemetry veto.
   - Compressed: the edge log, the verdict log (one dict line), the next-check stamp, and the comments.
   - One deletion would reach the target: the 5/20/45-minute `checkDeparture` chain, about 15 lines. That is the `TWCSlave` queue ×3, the `TWCManager` dispatch and import, `Targets.onDeparture`, and the `read=True` block in `_restoreDeparted`.
     - It is a time-based departure heuristic, and for Gen2 points the check now covers it.
     - But global constraint (d)/Q6 keeps it, and the UMC parity row (`test_ble_plus_fleet_car_leaving_a_umc_is_restored_after_the_departure_read`) calls `onDeparture` directly.
     - **Not taken. Your call.**
2. **The feed branch departs from the brief's literal text.**
   - The brief says: "wait for it … if the feed says nothing new within a short window, fall through."
   - As built, the check trusts the feed's newest `pluggedIn` report whenever it is a live one (`seen`, not a retained MQTT copy), however old it is. The wait (`CHECK_WAIT` = 20 s) gives the feed time to report a change.
   - Why: under the literal reading, test (b)'s wake edge (00@47, no plug change from the feed) would fall through to a BLE ping and read. The brief says "(b) no BLE read", so I picked the reading that test requires.
   - Rejected alternative: "a feed reading newer than the session start". It fails because TeslaMate reports the plug before the TWC names the car (by VIN read or attribution).
   - Consequence: if the feed's False arrives after the check has run, the check keeps the session.
     - The feed's False still marks the unplug through `noteObservation`, so the car is NOT_HOME and the restore happens.
     - But `twcVin` is not cleared until the next edge. On a VIN-less TWC, the next car's attribution waits for that.

## Design as built

### Where the edge is detected: `TWCSlave.plugCheckDue(now) -> Optional[float]` (serial thread)
- **State:**
  - `status`: the last heartbeat's `(state, max amps)`. `None` until the first heartbeat, so a restart is never an edge.
  - `edgeAt`: the first edge not yet checked.
  - `nextCheck`: the earliest time the next check may run.
  - Constants: `CHECK_WAIT, CHECK_GAP = 20, 30`.
- **Edges** (per the brief):
  - non-00 → 00;
  - at 00, a max going from > 0 to 0;
  - a change between plugged (`PLUGGED_STATES`) and not.
- **Each edge logs one INFO line:** `TWC 8244: 03 → 00, max 47.00 → 47.00 A: checking <key>`. The key comes from `vehicleAt(twcid)`: the VIN, `anon:8244`, or `None`.
- **No check for an empty point.** An edge sets `edgeAt` only when a car is at the point. An empty TWC's 00→03 is handled by the plug-in branch, as before.
- **Due when** `now >= max(edgeAt + CHECK_WAIT, nextCheck)`. It returns `since = edgeAt`, clears `edgeAt`, and sets `nextCheck = now + CHECK_GAP`.
- The gate **defers a check; it never drops one.** Edges that arrive while one is waiting share it. Box check: wake at 12:45:23 is checked at 12:45:43; the max drops at 12:46:12; that is checked at 12:46:32, before the 12:46:48 re-plug.
  - A drop-on-repeat rule (60 s) would have checked only the wake and missed the unplug.
  - That is also why the gap is 30 s, not 60.

### The queue: `TWCMaster.observeChargingSessions`
- It calls `plugCheckDue`. When a check is due, it calls `reconciler.submitJob(twcid, "plugCheck", lambda: self._plugSession(s, False, since))`.
- So the check runs on the BLE lane, like attribution.
- The queue coalesces per `(twcid, "plugCheck")`, so at most one check is pending per point.
- The serial thread does no I/O and holds no lock.
- `now` is now `vehicleRegistry.now()`. That is the same clock in production; `since` is then compared with observation stamps on one clock.

### The job: `TWCMaster._plugSession(slave, False, since)` (BLE worker)
- Steps:
  1. `at = vehicleAt(twcid)`. Return if it is None.
  2. Return if `at` is anonymous while the TWC still shows a non-00 state. That is a car no check can name, and attribution handles it.
  3. `cars` is the candidates for an anonymous session, else `[at]`.
  4. `plugged = {key: Presence.checkPlug(...)}`. It logs `TWC 8244: plugged in: {'<VIN>': False}`, one line per check.
  5. If any car reads True or unknown, it stops: the session stays.
  6. If every car reads False:
     - a single car (named, or the only candidate) logs `unplugged, <VIN> departs` and is observed `pluggedIn False` from `Gen2TWC`. The unplug mark is made in `noteObservation`, then departure and restore follow as before.
     - in every case, `endPlugSession` ends the session.
- With no candidates (a car no account knows), the session ends.
- Several candidates that all read Disconnected end the session, and none of them is departed (the old single-car rule).

### The per-car check: `Presence.checkPlug(master, v, since) -> Optional[bool]` (never wakes)
1. **Live feed:** if the `syncSource` is a telemetry source and its `pluggedIn` report is `seen`, return that value.
2. **BLE:** for a BLE-claimed car, if `ping` answers and `asleep(v)`, return True. An unplug wakes the car, so it is still plugged in. No read.
3. **Otherwise:** `v.read("chargingState", 0, force=True)`, the registry cascade in provider order.
   - BLE's charge read is free.
   - Owner reads for free.
   - Fleet's `fetch` runs `is_awake`, the free `vehicles/{vin}` check, and runs the paid `vehicle_data` only when the car is awake.
4. **Verdict:** `pluggedNow(master, v, None, since)`, the newest plug reading after the edge. None means nothing answered, so nothing changes.

### Plug-in side
Unchanged: the plugged-state branch begins the session, and `attributePlugs` runs as before.

## Deleted
- **`TWCSlave`:** `unplugStep`; `UNPLUG_DEBOUNCE`, `PLUGGED_RUN`, `LINK_GRACE`; `pluggedSince`, `ampsMaxBefore`, `zeroSince`, `zeroMax`, `anonEndedAt`. With them go the plugged-run guard, link grace, 60 s debounce, mid-run drop logic, own-offer guard and the `zeroMax`/`ampsMaxBefore` decisions.
- **`TWCMaster.observeChargingSessions`:** the anonymous idle/grace/short-run fallback close.
- **`TWCMaster._plugSession`:** the `depart` flag, the flicker guard, and the telemetry veto (the feed branch replaces it).
- **`TWCMaster.newSlave`:** the re-link `pluggedSince`/`heardFrom = 0` reset, back to a plain return. `heardFrom` is only read for truthiness.
- **Grep:** `git grep -nwE 'unplugStep|zeroMax|ampsMaxBefore|zeroSince|pluggedSince|UNPLUG_DEBOUNCE|PLUGGED_RUN|LINK_GRACE|anonEndedAt' -- lib html tests/unit tests/integration tests/API docs` finds nothing (rc 1).
- **Docs:** the `docs/PolicyCustomization.md` paragraph and the CHANGELOG line now describe the check.

## Tests

### TDD evidence
- **RED:** the new tests (written before any lib change, run on f5c6a769's lib) gave **14 failed, 14 passed**:
  - `test_gen2_unplug.py`: edge-after-wait, edges ×3, flicker, nothing-can-check, unnamed-stays, no-candidate-ends;
  - parity: (a), (b), (c), (d)×2, (f).
  - The passes were the edge cases that also hold on f5c6a769 (no edge for both-plugged states or a restart), plus the unchanged tests.
- **GREEN:** all pass after the change.

### New tests: `test_gen2_unplug.py`, rewritten
The rig is a real Gen2TWC and master. The car has no provider.
- `test_a_status_edge_asks_for_one_check_after_the_wait`: one check, at edge + 20.
- `test_which_heartbeats_are_edges` ×5: a 00; its max dropping; a re-plug; both-plugged states (0); a restart at 00 with the max rising (0).
- `test_a_flicker_while_charging_checks_at_most_once_per_gap` **(g)**: 10 min of 00/09 at 2 s gives at most 600/30 + 1 checks, each at least 30 s apart.
- `test_an_edge_on_an_empty_twc_checks_nothing`.
- `test_nothing_can_check_the_car_so_it_stays` **(e)**: no unplug, `twcVin` kept, and both log lines.
- `test_an_unnamed_session_nothing_can_check_stays`.
- `test_an_unnamed_session_with_no_candidate_ends_at_the_check`.
- `test_an_anonymous_point_finds_its_cars_once_per_pass`: kept.

### New parity rows (`test_command_path_parity.py`, appended)
They use the real TeslaBLE and TeslaAPI with `requests_mock`. In each, BLE's charge read follows the TWC (`followsPlug`).
- **(a)** `test_box_2026_10_20_each_unplug_departs_once_ble_reads_it_disconnected`
  - The 12:45–12:47 box sequence: 00@47 for 49 s; 00@0 (unplug); 09@6/47 and 03@6 for 28 s, re-named by VIN; then 00@0.
  - The wake check reads it plugged in. Each unplug departs once BLE reads Disconnected.
  - 3 pings, 3 reads, no wake, paid (0,0,0). Fleet is online and never read.
- **(b)** `test_box_2026_10_20_with_teslamate_live_the_feed_departs_the_car`
  - The same sequence. TeslaMate reports `pluggedIn` False 13 s after each unplug, and True 8 s after the re-plug.
  - Both unplugs depart; no ping and no read; paid (0,0,0).
- **(c)** `test_a_sleeping_car_on_a_03_00_flicker_stays_plugged_in`: one ping (asleep), no read, no unplug, paid (0,0,0).
- **(d)** `test_fleet_only_checks_a_car_awake_with_one_read[online-1 | asleep-0]`
  - Online: one `vehicle_data`, Disconnected, departs; paid (1,0,0).
  - Asleep: no read, no unplug; paid (0,0,0).
- **(f)** `test_an_unnamed_session_ends_when_its_only_candidate_reads_disconnected`: the session ends and the car departs; paid (0,0,0).

### Results
- `tests/unit` + `tests/EMS`: **2180 passed** (baseline 2179).
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2189 passed, 1 xfailed**.
- Black is clean on all 8 touched `.py` files.

### Plumbing (PLUMBING-ONLY unless noted)
- **`reconcile_helpers.InlineQueue`** runs `plugCheck` jobs inline at `put`, as the BLE worker would run them promptly. Attribution and scan jobs stay deferred: running them would re-trigger the row moves Task 9 found.
- **Parity `beats`** uses `int(c.t) % 30` and `% 10`.
- **`followsPlug(s, c)`** advances the clock 0.01 s per BLE read.
  - The reason is real, not cosmetic. On a frozen clock, the check's ping (the BLE contact mark) and the unplug mark tie, which gives PRESUMED and no restore.
  - In production, the BLE read's seconds separate the two marks. **The design depends on wall-clock order here:** the contact from the check's own ping must be older than the unplug the check finds. See Concerns.
  - Its plugged answer is `Stopped`, not `Complete`, so `returning_car`'s start still goes.
- **`test_twcmaster_vin_confirmation`:** the Mock slave's `unplugStep` stub becomes `plugCheckDue`; the check job is run with `runPending`.

### Deleted or rewritten tests

`test_gen2_unplug.py` (17 old tests):

| Old | Fate |
|---|---|
| `00_with_the_max_amps_drop_after_a_plugged_run_is_one_unplug` | Replaced by parity (a) and (d): an unplug departs once the check reads it |
| `a_waking_00_that_keeps_its_max_and_sleeps_again_is_never_an_unplug` | Replaced by (a)'s wake check, and (c) |
| `a_max_that_drops_to_0_inside_a_waking_00_is_an_unplug` | Replaced by (a) (box sequence) |
| `an_unnamed_session_ends_at_a_max_that_drops_inside_a_waking_00` | Replaced by (f), and edges[runs1] |
| `a_max_following_our_own_0_offer_inside_a_00_is_never_an_unplug` | DELETED: own-offer guard removed. A plugged car reads plugged |
| `an_idle_car_already_at_0_a_never_gives_a_twc_unplug` | DELETED: the filter is gone. Covered by `nothing_can_check` |
| `00_inside_link_grace_or_without_a_plugged_run_is_never_an_unplug` | DELETED: link grace and plugged-run guard removed |
| `onset_logs_the_slave_max_amps` | Replaced by `nothing_can_check`, which pins the edge and verdict lines |
| `reported_once_per_00_run` | Replaced by `flicker…once_per_gap` and `a_status_edge_asks_for_one_check` |
| `a_re_link_starts_a_new_plugged_run` | DELETED: re-link reset removed |
| `an_unnamed_session_outlasts_a_waking_00_and_departs_no_one` | Replaced by `an_unnamed_session_nothing_can_check_stays` |
| `an_unnamed_car_idle_at_0_a_ends_its_session_at_the_first_00` | INTENTIONALLY CHANGED (Task 19): nothing can check, so it stays. `…nothing_can_check_stays` |
| `an_unnamed_car_unplugged_inside_the_link_grace_ends_at_the_first_00` | DELETED: grace fallback removed; covered by (f) |
| `an_unnamed_car_unplugged_after_a_short_plugged_run_ends_at_the_first_00` | DELETED: short-run fallback removed; covered by (f) |
| `an_unnamed_car_waking_inside_the_link_grace_keeps_its_session` | DELETED: grace removed; covered by `…nothing_can_check_stays` |
| `an_unnamed_car_s_unplug_holds_a_minute_then_departs_the_only_car` | Replaced by parity (f) (the rig car has no provider) |
| `an_anonymous_point_finds_its_cars_once_per_pass` | Kept |

`test_presence.py`:
- `live_telemetry_plugged_vetoes_a_twc_unplug` → `a_live_feed_saying_plugged_in_keeps_the_car_through_a_twc_00`. INTENTIONALLY CHANGED (Task 19): the log line is now the check's verdict.
- `…vetoes_a_max_that_drops_inside_a_waking_00` → `…keeps_the_car_through_a_max_drop_in_00`. PLUMBING-ONLY: the beats are inlined, because the imported helper was deleted.
- `…keeps_an_unnamed_session_through_an_unplug` → `a_live_feed_saying_plugged_in_keeps_an_unnamed_session`. Same change as the first.
- `…vetoes_the_close_of_an_unnamed_session_in_the_grace`: DELETED (grace removed). Covered by the previous test.
- `charge_stop_keeps_twc_vin_until_the_unplug`, `vehicle_key_names_the_car_after_a_charge_stop_and_nobody_after_an_unplug` and `a_vinless_unplug_departs_the_only_candidate`: INTENTIONALLY CHANGED (Task 19). The car now has a live TeslaMate feed whose `pluggedIn False` answers the check. Without a way to check the car, there is no unplug.
- New: `a_retained_feed_reading_is_no_answer`.

`test_limit_wiring.py`:
- `a_vinless_gen2_after_a_restart_is_an_anonymous_plug_session` and `only_a_plugged_state_begins_the_session_and_a_checked_unplug_ends_it` (renamed from `…a_held_unplug…`) are INTENTIONALLY CHANGED (Task 19).
- The session now ends at the check, once TeslaMate's Disconnected arrives after the edge and the wait has passed (`edgeAt -= CHECK_WAIT`).

## Parity moves (old → new, with reason)

The "original stub" is the row's BLE stub with no charge-read answer. `followsPlug` is the box-faithful stub, where BLE in range answers the read. The rows keep `followsPlug`.

| Row | Old | Original stub under Task 19 | With `followsPlug` (kept) | Reason |
|---|---|---|---|---|
| `box_2026_10_18_departure_restores_over_ble_within_a_minute` | restore 90 at onset+60..+120 | no departure, no restore | restore at **onset+40**, bound now `onset+CHECK_WAIT..onset+60`; paid (0,0,0) | The check at edge+20 replaces the 60 s debounce, and the restore goes at the next policy pass. Timing INTENTIONALLY CHANGED; the read answer is PLUMBING (the box had BLE in range) |
| `box_2026_10_17_morning_wake_episodes_declare_no_departure` | (0,0,0), no departure | **paid (5,0,0)**: BLE ping answers, the read is silent, the cascade reaches Fleet (online), 5 `vehicle_data` | (0,0,0), no departure | The (5,0,0) is the Fleet branch working as specified, on a stub the box never shows (a ping that answers with a read that doesn't). Kept box-faithful |
| `no_gps_source_plug_unplug_cycle_end_to_end` | departure at the 60 s debounce, restore [80] | no departure (nothing can check) | departure at the check (edge+20 s), restore [80], 0 requests | as above |
| `a_returning_car_on_an_unnamed_gen2_asleep_starts_over_ble` | departure, then start over BLE | no departure | departure at edge+20 s; start over BLE; (0,0,0) | as above |
| `a_plug_attributed_before_the_policy_pass_sends_a_held_car_nothing` | departure, restore [80] | no departure | departure at edge+20 s, [80], (0,0,0) | as above |
| `a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore` | unplug marked; paid (0,0,1) (one blind Fleet restore) | — | **no unplug; paid (0,0,0)**; no wake | INTENTIONALLY CHANGED by the brief's second quote. BLE never answers and Fleet says asleep, so nothing can check the car and the TWC alone departs nothing |

Six rows moved. All other parity rows are unchanged, including the box rows from Tasks 13, 16 and 17 (the 00@47 waking rows) and scenario 12.

## Lib delta
- `git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 26,342 before, **26,344** after (**+2**). The target was ≤ −20: **22 over target, a miss.** See ruling request 1.
- `git diff --shortstat f5c6a769 -- lib`: 3 files changed, 60 insertions(+), 58 deletions(−).
  - Presence +15 (`checkPlug`).
  - TWCSlave about −1 (`plugCheckDue` replaces `unplugStep`).
  - TWCMaster about −12.

## Concerns
1. **Lib +2.** See ruling request 1.
2. **Feed semantics.** See ruling request 2, including the late-feed `twcVin` lag.
3. **Wall-clock ordering.** The check's own BLE ping marks contact. The unplug it then finds must be newer, or `decide` ties to PRESUMED and gives no restore.
   - In production, the BLE read's duration separates them.
   - A coarser clock, or a read that returns within the same timestamp, would hold a BLE car PRESUMED after an unplug.
   - A fix would stamp the departure strictly after the ping. Not done; it needs a ruling on tie handling (F8).
4. **A stale "asleep" can stand.** A ping that answers through the range scan (VCSEC rc ≠ 0), or with an UNKNOWN sleep status, observes no state. An older "asleep" then returns True with no read. The result is a missed unplug, never a false one.
5. **Fleet's cached online check.** `onlineState` caches for 120 s. A cached "asleep" from just before the unplug skips the paid read, even though the unplug woke the car. Again, a miss, not a false unplug.
6. **The departure mark is at check time.** That is edge+20..50 s, not the edge itself. The restore follows at the next policy pass. This is the timing move the brief anticipated.
7. **Fleet cost under a flicker.** On a Fleet-only car under a long 00/09 flicker, each check pays one `vehicle_data` while the car is awake. The box showed 39 00-onsets in the 14:xx hour on Oct 20, about one every 18 s. The 30 s gap bounds this to about 2 paid reads a minute ($0.004/min). It is bounded, but it is per gap window, not per edge. A live feed or BLE makes it free.
8. **A cloud read on the BLE lane.** A cloud read in the cascade (Owner or Fleet) runs on the BLE worker, so BLE commands wait for it.
9. **A no-op check on a surviving session.** An anonymous session's 00→03 re-plug edge queues a check that does nothing (the guard), but it uses up the 30 s gap.
10. **A pending check takes the newest `since`.** If a check is still queued when a newer edge comes due, the queue replaces it, and readings between the two edges no longer count.
11. **A failed ping costs a second timeout.** A BLE car whose ping does not answer still gets a BLE read in the cascade, which is a second timeout, before Owner or Fleet.
12. **Cosmetic:** an edge on an empty point logs "checking None".
13. **Non-00, non-plugged states** (02, 06, 07) going to 00 are edges, as the brief lists. 06 and 07 to a plugged state are plugged-state changes.

---

# Fix round 1 (commit 8f76957d, parent c4636385)

## Changes, by ruling
1. **Critical 1: Fleet past the read cache.**
   - Before its cascade read, `Presence.checkPlug` clears the car's `TeslaAPI` attachment `statusDeferral` and `onlineCheckedAt`. Fleet then asks the free online check again, and reads `vehicle_data` only if the car is awake.
   - I did not pass `force` down through the providers: that would touch every `fetch` signature.
   - New tests:
     - `test_fleet_only_checks_past_its_stored_reading`: the wake's paid read, then Disconnected at 00@0 49 s later → departs; paid (2,0,0).
     - `test_fleet_only_checks_past_its_cached_asleep`: asleep at the wake, then online and Disconnected inside the 120 s cache → departs; paid (1,0,0).
2. **Important 2: the feed answers only with news.**
   - `checkPlug` now uses `telemetryPlug(v, since)`: the feed's report counts only if made at or after the edge. Otherwise the check falls through to BLE, then the cascade. (This also takes Minor 8.)
   - Test (b) changed: the wake's 00, which the feed said nothing about, gets one BLE ping and read. Both unplugs, which the feed reports within the wait, get no BLE read.
   - New: `test_box_2026_10_20_a_late_feed_neither_holds_an_unplug_nor_departs_a_replug`.
     - 07:41:59: feed False 44 s late; the check reads BLE Disconnected and departs.
     - 10:13:59: re-plug, named.
     - 10:14:16: 00@47. The old False is no news, BLE reads the car plugged in, and it stays: no new unplug mark, `twcVin` kept, paid (0,0,0).
3. **Important 3: rate rule** (serial thread only, slave state).
   - `armed`: an edge with the max above 0 is checked once.
   - It re-arms when the TWC shows 03 or 00@0.
   - Every 00@0 edge (onset or max drop) is checked.
   - `CHECK_GAP`/`nextCheck` are gone; `CHECK_WAIT` = 20 s stays.
   - Disarming happens only when a check was queued, so an edge on an empty point doesn't disarm.
   - Tests:
     - `test_a_car_awake_at_its_limit_flickering_00_09_is_checked_once`: 09@47 ↔ 00@46 every 18 s for 14 min at 0 A gives 1 check (the old rule gave many). After 03@6 then 00@47, the second event is checked: 2 in total.
     - `test_every_00_at_0_a_is_checked`.
   - The (g) gap test is replaced by these.
4. **Added rule (user):** no check for an edge while the point reports current drawn (`reportedAmpsActual >= 1`).
   - Test: `test_edges_while_the_car_draws_current_run_no_check` (01/00@32/00@0 at 16 A, 10 cycles → no check). It failed with the rule removed and passes with it.
5. **`checkDeparture` kept.**
6. **Minor 5:** the Gen2TWC `pluggedIn False` is stamped at the newest plug reading's own `at`, the one that decided. This removes the ping-contact/unplug ordering dependency in production. `followsPlug`'s 0.01 s clock step stays: it makes the read newer than the ping, as in life.
7. **Minor 9:** the edge line is logged only when a check is queued for a car, so there is no "checking None".
8. **Minor 10:** the sleeping-car row's comment now says why Fleet answers asleep: it stands in for a car no provider can read. Assertions unchanged.
9. **Docs:**
   - "About 20 seconds after the first such change".
   - A flicker is checked once; every 00 at 0 A is checked.
   - The feed counts only for a report since the change.
   - A Fleet-only install, or one with BLE down, pays for a read when a check finds the car awake: about one per real plug event.
   - The CHANGELOG line is updated to match.

## Parity move (one more)
- `box_2026_10_18_false_00_at_47_a_with_telemetry_plugged_is_no_departure`.
  - With its original BLE stub (the read is silent): TeslaMate's True predates the 00, so it is no answer now. The check falls to Fleet (online), giving **paid (1,0,0)**.
  - With box-faithful `followsPlug`: BLE reads it plugged in, paid (0,0,0). That stub is kept, as in the other five rows.
  - Reason: ruling 2.
  - Assertions unchanged.

## Tests changed in this round
In `test_presence.py`, three tests are INTENTIONALLY CHANGED (ruling 2): the feed now reports after the edge.
- `…keeps_the_car_through_a_twc_00` → `a_feed_report_after_the_edge_keeps_the_car_through_a_twc_00`;
- `…through_a_max_drop_in_00` → `a_feed_report_after_the_edge_keeps_the_car_through_a_max_drop_in_00`;
- `…keeps_an_unnamed_session` → `a_feed_report_after_the_edge_keeps_an_unnamed_session`.

`a_retained_feed_reading_is_no_answer` → `a_feed_reading_older_than_the_edge_is_no_answer`. The feed's False comes before the edge, so the verdict is None.

## TDD evidence
With c4636385's lib and this round's tests, 7 failed: flicker-once, every-00@0, (b), both Fleet probes, the late-feed row, and the older-feed presence test. The current-drawn test failed with only its rule removed. All pass now.

## Results
- Covering files (gen2_unplug, parity, presence, limit_wiring, vin_confirmation, sleeping_car): 276 passed, before the current rule.
- `tests/unit` + `tests/EMS`: **2185 passed**.
- Black is clean.

## Lib delta
- vs f5c6a769: 26,342 → **26,358 (+16)**.
- `git diff --shortstat f5c6a769 -- lib`: 3 files, +73/−57.
- This round is +14 on top of c4636385's +2:
  - arm rule and current guard about +6;
  - cache bypass +3;
  - departure stamp +4;
  - comments;
  - offset by dropping `CHECK_GAP` and the duplicated feed lines.
- The ≤ −20 target is still missed. `checkDeparture`, the one deletion that would reach it, is kept by ruling 4.

## Concerns
- The cache bypass writes two `TeslaAPI` attachment fields from the BLE worker. They are plain attribute writes, and the module's own threads write them the same way.
- A disarmed edge waits for 03 or 00@0. An unplug that leaves the max above 0 during a disarmed burst would not be checked; none was seen on the box (every real unplug was 00@0).
- The departure stamp is the newest plug reading of any source. A newer reading that `pluggedNow` set aside (a non-strong source while the car's position is unknown) could stamp it later.

---

# Fix round 2 (commit a5239e0c, parent 8f76957d)

## Changes
1. **Retained feed readings (Important).** The `seen` guard now lives in `checkPlug` only. The feed answers only when its newest `pluggedIn` is a live (`seen`) report and `telemetryPlug(v, since)` is not None, meaning the report came since the edge.
   - `telemetryPlug` itself is unchanged, for two callers:
     - `VehicleEndpoint` (:173) uses it to keep a feed-plugged car's endpoint under an unknown TWC. A retained True there still means the car is plugged.
     - Attribution's `fits` uses a retained False after the plug to rule a car out. That is still the feed's last word.
   - New test: `test_presence.py::test_a_retained_redelivery_inside_the_wait_is_no_answer`. A retained False inside the wait gives verdict None and `twcVin` is kept. It was red on 8f76957d.
2. **Departure stamp (Minor 1).** The new `Presence.unpluggedAt(v)` returns the time of the newest reading that says unplugged, from `pluggedIn` or `chargingState`, where `_plug` is False. The Gen2TWC observe uses that time. A newer plug-in reading can no longer lend its time.
   - Test (b) now asserts that each departure mark equals the feed report's time. This also held on 8f76957d, where that report was the newest reading of any kind.
3. **Fleet online cache (Minor 2).**
   - `CarApiState.staleBefore` is new, default 0.
   - `checkPlug` sets `statusDeferral = 0` and `staleBefore = since`; it no longer zeroes `onlineCheckedAt`.
   - In `onlineState`:
     - the telemetry shortcut needs `obs.at >= max(onlineCheckedAt, staleBefore)`;
     - the 120 s reuse needs `onlineCheckedAt >= staleBefore`.
   - So a feed "asleep" from before the edge can't answer, and the shortcut is never opened wider than before. Once the check has made its own online check, both work as before.
   - Both Fleet probes still pass.
4. **Current when the check runs (Minor 3).** `_plugSession` returns early if `reportedAmpsActual >= 1` when the job runs.
   - New test: `test_gen2_unplug.py::test_a_check_due_while_the_car_draws_current_is_skipped`. The edge comes at 0 A and 16 A is flowing by the time the check runs: no verdict line. It was red on 8f76957d.
5. **Docs (Minor 4).** The PolicyCustomization paragraph is rewrapped to under 80 columns, and the log text now says "each checked change".

## Results
- Covering files (gen2_unplug, parity, presence, limit_wiring, vin_confirmation, sleeping_car): 279 passed.
- `tests/unit` + `tests/EMS`: **2187 passed**.
- Black is clean.
- No parity count or timing moved this round.

## Lib delta
- vs f5c6a769: 26,342 → **26,365 (+23)**.
- `git diff --shortstat f5c6a769 -- lib`: 4 files, +82/−59.
- This round is +7:
  - `unpluggedAt` +5;
  - `staleBefore` field and conditions +2;
  - the current re-check +2;
  - the `seen` guard +0;
  - offset by removing the inline max.

## Concerns
- `noteObservation` still marks an `unplug` from a retained False whose previous reading from that source was True. That is existing behaviour, not this check's. The new test asserts only that the check does not depart the car or end the session.
- `staleBefore` stays set after the check. It has no effect once a newer online check exists.

---

# Fix round 3: two commits

## a4ee8ca0 "A retained feed reading marks no plug event"
- **Change:** in `noteObservation`, a `pluggedIn` or `chargingState` reading from a telemetry source (TeslaMate, Fleet Telemetry) with `seen=False` (a retained redelivery) is no plug evidence. It marks neither `unplug` nor `plugIn`.
- **Scope:** I limited the gate to telemetry sources. The registry's own inferred reading (`VehicleRegistry` :250, a VIN read moving the other car off its point) is also `seen=False`. Gating every `seen=False` reading broke `test_the_twcs_vin_read_overrides_an_attribution`, which still needs that unplug mark.
- **Test:** `test_presence.py::test_a_retained_unplugged_redelivery_marks_no_unplug_and_restores_nothing`. A live True, then a retained False, then a policy pass: no unplug mark, `departed` is None, no restore desire. It was red on a5239e0c.
- **Note:** after a retained False, the source's previous reading is that False. A later live False then marks no unplug, because it is no change.
- **Results:** tests/unit + tests/EMS: 2188 passed. No parity move.

## 873b83d3 "Drop the timed departure reads" (user ruling)
### Deleted
- `TWCSlave`: the three `checkDeparture` queue calls at power drop. The stop webhook stays, and its comment now says only that.
- `TWCManager`: the `checkDeparture` dispatch and the `onDeparture` import.
- `Targets`: `onDeparture`, plus `_restoreDeparted`'s `read` parameter and its read block. The `READ_MAX_AGE` import was then unused and is gone.
- Both callers now call `_restoreDeparted(master)`.
- Grep: `git grep -nwE 'checkDeparture|onDeparture' -- lib html tests/unit tests/integration tests/API docs` finds only `test_presence.py:888`. That line pins the `/api/checkDeparture` 404, which is unrelated.

### Docs
- **CHANGELOG:** "The 5, 20 and 45 minute reads after power drops stay" is replaced. A car charging away from a TWC with no telemetry feed is not watched for its departure, and a separate feature is planned. The timed reads are gone.
- **PolicyCustomization:** a known-limits sentence says the same.

### Tests
- `test_limit_wiring.py`, 2 DELETED (they pinned the departure read):
  - `test_a_fleet_car_that_unplugs_and_leaves_gets_its_normal_limit_back`;
  - `test_an_unplug_at_home_is_not_a_departure`.
- `test_limit_wiring.py`, PLUMBING-ONLY: `test_departure_restores_a_held_limit_for_an_absent_car_once` and `test_live_telemetry_places_a_departing_car_for_free` call `_restoreDeparted(m)`. Neither made a read.
- `test_limit_wiring.py`, INTENTIONALLY CHANGED (ruling): `test_a_policy_change_while_the_car_is_away_sends_nothing` places the car away by a free fix, where the departure read used to.
- Results: tests/unit + tests/EMS: **2186 passed** (2188 − 2 deleted).

### Parity move
`test_ble_plus_fleet_car_leaving_a_umc_is_restored_after_the_departure_read` → `test_ble_plus_fleet_car_leaving_a_umc_is_not_watched`.

| | Before | After |
|---|---|---|
| Departure read | one paid read finds the car away | none |
| Presence | NOT_HOME | HOME (from the install's last fix) |
| Restore | 90 sent over Fleet | none; the car keeps 50 |
| Paid | (1, 0, 1) | (0, 0, 0) |

Reason: the user's ruling. A car charging away from a TWC with no feed isn't watched for departure.

## Lib delta vs f5c6a769
- 26,342 → **26,350 (+8)**.
- `git diff --shortstat f5c6a769 -- lib`: 6 files, +90/−82.
- These two commits: the retained gate +2; dropping the departure reads −17 (4 files, +6/−23).
- The ≤ −20 target is still missed by 28.

---

# Fix round 4 (adb6a215 "Compare a feed's plug change with its last live reading")

## Problem
The registry keeps only a source's newest reading. When a retained copy arrives, its plug value replaces the feed's last live one. In `noteObservation`, the next live report from that feed was then compared with the retained value, so a live unplug after a retained unplugged copy looked like no change and marked nothing.

## Change
When a telemetry source's previous reading is a retained copy (`seen` False), `was` comes from the car's plug events instead: `markAt("plugIn") > markAt("unplug")`.
- I chose this because it is the smallest form: no new per-source state. The registry keeps no history, so the feed's last live value isn't stored anywhere else.
- It uses the car's events, not one source's. If another source has marked an unplug since, the live False is no change.

## Test
`test_presence.py::test_a_live_unplug_after_a_retained_copy_is_marked_once_at_the_report`.
- Sequence: live True, then a retained False, then a live False, then the live False again.
- Expected: the unplug is marked once, at the first live False's time.
- Red on 873b83d3.

## Results
- tests/unit + tests/EMS: **2187 passed**. Black clean.
- No parity move.

## Lib delta
- vs f5c6a769: 26,342 → **26,354 (+12)**.
- `git diff --shortstat f5c6a769 -- lib`: 6 files, +94/−82.
- This commit adds 4 lines.

---

# Fix round 5 (4f2a3275 "Fall back to the feed's last reading when no plug event is known")

## Change
In `noteObservation`, when a telemetry source's previous reading is a retained copy:
- If no plug event is known (the plugIn and unplug marks are equal, i.e. both NEVER after a restart), `was` stays the retained copy's own value (`_plug(field, previous)`).
- Otherwise `was` is "plugIn newer than unplug".
- A comment says that no previous reading counts as seen, which is why `getattr(previous, "seen", True)` guards for None.

**The "only a Gen2TWC plugIn mark" case.** After a restart the retained copy is False, then the TWC attribution marks plugIn, then the feed reports live:
- live False: `was` is True, so the unplug is marked. That is a real change since the car was attributed.
- live True: `was` is True, so no second plugIn.

## Tests
New, both red on adb6a215:
- `test_after_a_restart_a_live_unplug_after_a_retained_plugged_copy_is_marked` (probe A).
- `test_after_a_restart_a_live_plugged_report_after_a_retained_copy_is_no_event` (probe B): no plugIn mark, no lifeAt, no `onArrival`, no `attributePlugs`.

**NEEDS_CONTEXT: "an unplug at home alone doesn't restore" is not added.**
- I wrote it as: held 90/50, live True, then live False at home, then a newer fix parked inside the radius, then a policy pass.
- Current design (ruling F1: departure is the last unplug event) gives `departed` = the unplug time, and the restore goes.
- Parity row `test_box_2026_10_18_departure_restores_over_ble_within_a_minute` asserts exactly that restore after an unplug at home.
- The reviewer's minor contradicts F1 and that row. Please say which should hold.

## Results
- tests/unit + tests/EMS: **2189 passed**. Black clean.
- No parity move.

## Lib delta
- vs f5c6a769: 26,342 → **26,356 (+14)**.
- `git diff --shortstat f5c6a769 -- lib`: 6 files, +96/−82.
