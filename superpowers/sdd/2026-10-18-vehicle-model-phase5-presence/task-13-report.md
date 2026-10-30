# Task 13 report: arrival on the box, 2026-10-19 15:24–15:54

Two commits on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent c7410df0, which is what the box runs). Not pushed.

| Commit | Issue |
|---|---|
| 05a63b1c Name a plug-in the feed has not reported yet | 1 |
| c8d82ee1 Hold a driving or away car before any BLE run | 2 |

Evidence came from the box journal (INFO), `~/twc-events/teslamate.log`, and the code. I tried to read the car's 15:45–15:52 positions from TeslaMate's database to measure its distance from home. The permission check denied that, so the position claims below are inferred from the code and the logs.

## Issue 1: the only car was not attributed

### Root cause: a stale feed reading, not the BLE charge read

The brief's hypothesis was wrong. No BLE read ran at 15:54:00: the log has no BLE line between 15:52:26 and 15:54:09. `pick` excluded the car before reaching that step.

- `fits(v)` (Presence.py) starts with `if telemetryPlug(v) is False: return False`.
- `telemetryPlug` returns the feed's newest `pluggedIn` reading, however old it is.
- TeslaMate's `plugged_in` had been `false` since **13:21:15** (teslamate.log line 137, the morning's unplug). After the 15:24:06 restart, the broker delivered it as a retained message at 15:24:44, and `Telemetry._observe(retained=True)` stores it (`seen=False`).
- The TWC saw the plug at 15:54:00, and TeslaMate reported `plugged_in=true` only at **15:54:08**. So at attribution the feed still said "unplugged". That excluded the only car, and the reached and inside stages never saw it.
- The `pluggedIn None -> True` line misled. `logChange` tracks only live reports, never retained ones, so "None" means no live report since the restart. It does not mean no value.
- **How often this hits.** It affects any plug-in where the TWC sees the plug before the feed does, and TeslaMate here lags by 8 s. The plugged car's own feed then rules it out, so on a TeslaMate box attribution almost always failed on the first try.

There was also a latent second cause on the same path. Had the read run, BLE would have reported `Complete`. At 15:54:00 the offer was 6 A, and it rose to 47 A at 15:54:02. A pilot read during that rise differs from the 6 A snapshot, and `fits` returned False for any pilot mismatch, whatever the charging state.

### What happened to the session afterwards

- **15:54:08.** TeslaMate's plug-in arrived. `noteObservation` marked `plugIn` and called `onArrival`. The car was HOME and `pluggedNow`, so the anonymous point's fan-out (`_carKeys` → `candidates(SET_AMPS)` ∧ `pluggedHere`) rated it. That gave `setAmps` over BLE at 15:54:10 with no wake ("limit at or below battery"). **Nothing retried attribution.** `attribute` ran once per session (Task 10, concern 3).
- **15:54:15.** At its limit, the car let the Gen2 drop to 00. `unplugStep` said "not an unplug" (max stayed at 47 A). Then `observeChargingSessions` took its raw-00 branch ("00 ends the anonymous session"), which calls `_plugSession(False, depart=False)` → `endPlugSession`. The anonymous car was deleted, which is why the Vehicles list showed no "Unknown car on TWC 8244".
- **Now.** The car has no `twcVin`, so it is **not associated with TWC 8244**. It is HOME and plugged in only through TeslaMate's reading.

### Fix (05a63b1c)

1. **A feed's "unplugged" excludes a car only if it is newer than the plug.**
   - `beginPlugSession` marks `plugIn` on the anonymous car when it creates it.
   - `attribute` passes that time to `pick(since=…)`, and `fits` calls `telemetryPlug(v, since)`.
   - `telemetryPlug` ignores a reading older than `since`. The default is NEVER, so `_plugSession`'s unplug check is unchanged.
   - This covers Gen3 sessions too.
2. **A pilot mismatch excludes a car only while it is `Charging`.** At rest (`Complete`, `Stopped` and the others), the car is neutral (None), because it may not have seen the newest offer yet. A drawing car at another pilot is still excluded, as `test_pilot_mismatch_means_another_charger` checks.
3. **Retry on the feed's plug-in.**
   - In `noteObservation`, a pushed plug-in (TELEMETRY_SOURCES) for a car no point names now calls `master.attributePlugs()`. That queues the attribution job for each Gen2 on the BLE worker.
   - `attribute` already returns None for a point that is no longer anonymous.
   - On the retry, the fresh feed plug-in is decisive through pick's "plugged in just now" stage, without BLE.
   - `_plugSession`'s job submission is folded into `attributePlugs([slave])`.

The car is attributed with paid (0, 0, 0) and no wake. Its limit is already the policy's, so the arrival changes nothing.

### Tests (all red at c7410df0)

- **Parity row `test_box_2026_10_19_plug_in_at_the_limit_names_the_only_car`.** One car with TeslaMate, BLE and Fleet. TeslaMate has said unplugged for 9,000 s, the limit is 50 and the battery 60, BLE contact came 90 s before, and the Gen2 reads VINs but reads none at 6 A. BLE reads `Complete` at a 48 A pilot.
  - Result: named at 8244, `vehicleKey == VIN`. TeslaMate then reports the plug-in, and the TWC goes to 00 at 47 A for 600 s, idle at the limit as on the box.
  - After that the car is still named at 8244 and `pluggedHere`, no limit is sent and the held limit is unchanged (no restore). No BLE wake; paid (0, 0, 0).
  - Red at `twcVin None`. Each half of the fix alone also leaves it red: with the time bound reverted it fails, and with the pilot rule reverted it fails.
- **Parity row `test_a_plug_left_anonymous_is_named_by_the_feed_s_plug_in`.** Two cars home, neither answering BLE, so the plug is left anonymous. Then TeslaMate reports car 1 plugged in.
  - Result: the retry names car 1 only; paid (0, 0, 0).
  - Red: `anon:8244`.
- **`test_presence_attribution.py::test_a_car_at_rest_at_another_pilot_is_still_a_candidate`.**

## Issue 2: BLE runs for a car that was away

Both runs are `Run.runAttempt`'s pre-flight **ping** (`"no BLE answer"` comes only from Run.py:158). It timed out after 15 s, and the range scan then missed. The desire both times was the **policy apply (50)**, set by the 30 s policy pass: `presentVehicles` → `applyPolicyLimit`. The ping runs only when `presence != NOT_HOME` (`check = state == PRESUMED or quiet…`, where `quiet` requires `state != NOT_HOME`). So at neither moment was the car NOT_HOME to TWCManager.

### 15:24:33: after a restart, nothing was known (not changed)

- The service restarted at 15:24:06, and the first policy pass at 15:24:18 set the apply.
- TeslaMate's MQTT client starts 30 s after module init (`Telemetry.__init__`: `Timer(30, self.doMQTT)` when `syncTelemetry`). Its retained topics arrived at 15:24:44.
- At 15:24:18 the car had no evidence, so it was PRESUMED "no newer evidence".
- The PRESUMED ping is the designed presence probe: contact makes the car HOME, and then the message sends. It is what Task 12's variant relies on. Applicability could not have stopped it, because nothing said the car was away.
- This matches Task 12's 14:28:44 case. It is left as is; see Concerns.

### 15:50:07: the car was driving inside the radius (fixed)

- **The ping started at 15:49:52**, the policy pass (15:50:07 − 15 s). The car was still in D: shift P arrived at 15:49:59.
- **Why the car was PRESUMED "driving".** It had an apply desire, and `presentVehicles` skips NOT_HOME, so `decide` did not say NOT_HOME. A driving car with TeslaMate fixes is NOT_HOME only when its newest fix is outside the radius. So it was PRESUMED "driving", with its newest fix inside the 1,000 ft box.
  - This fits the route: it reached the Home geofence after 21 s of driving.
  - The car was "outside any geofence" only by TeslaMate's smaller geofence.
  - At 15:49:22 it was not yet in the radius, so no desire was set then.
- **The order problem.** `runAttempt` pinged a PRESUMED car before asking applicability, which is in `beforeWrite`, after the read. The verdict for a driving car is HOLD "driving" whatever the ping finds: `decide` puts `drivingNow` ahead of contact. So the ping could only waste the BLE worker, about 25 s.
- **15:29:43 Fleet, by contrast.** By then the retained fix had made the car NOT_HOME, and `inapplicable` cleared the desire ("not here (away)") before any wake or command.
  - The INFO log can't show whether that attempt was quiet. If it was, a Fleet read (a paid `vehicle_data`) could have run before `inapplicable`.
  - The new early check prevents that read for any NOT_HOME car. No parity row exercised it, so no count moved.

### Fix (c8d82ee1)

- At the top of `runAttempt`, for a provider with a module (charging points are never gated), when the car is NOT_HOME or `drivingNow`, `reconciler.inapplicable` runs first. A HOLD or NOT_HERE returns before any ping, read or wake.
- No answer can change those verdicts:
  - NOT_HOME cars were never pinged, but could still be read;
  - driving holds whatever the contact.
- The wake path's separate NOT_HOME check is folded into it.
- PRESUMED cars that are not driving still get the probe ping.

### Tests

- **Parity row `test_box_2026_10_19_no_ble_run_for_a_car_driving_or_away`.**
  - The car drives inside the radius with BLE out of range, and policy passes run for 60 s. Result: held with no ping, run or read.
  - Red at c7410df0: `pings == [VIN]`.
  - The second half is characterization and passes before the fix. A desire set while home and run once the car is placed away is cleared with no BLE activity.
  - Paid (0, 0, 0).

### Parity moves (pings only; commands and paid counts unchanged)

| Test | Was | Now |
|---|---|---|
| `test_ble_contact_while_driving_still_holds` | 1 ping (its contact source) | 0 pings; contact is observed directly, so F7 (contact while driving still holds) is still pinned |
| `test_box_2026_10_18_arrival_while_driving_sends_nothing_until_parked_then_ble_free` | ≥ 1 ping while driving ("pings allowed") | 0; BLE `wake, charging-set-limit` at park unchanged |
| `test_presence.py::test_a_held_car_driving_in_ble_range_is_pinged_once` | 1 | renamed `…_is_never_pinged`, 0 |
| `test_box_2026_10_19_return_and_leave_unplugged_goes_over_ble` | first miss with state driving; one more miss while driving in | first miss now at restart before any state (the box's 14:28:44 shape), then driving; no ping while driving in (`== pings`); BLE apply at park, restore at D, paid (0, 0, 0) unchanged |

## Results

- `tests/unit` + `tests/EMS`: **2148 passed** (baseline 2144, plus 4 new tests).
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2157 passed, 1 xfailed**.
- `black --check` is clean on the touched files.

## Lib delta

- `.py` lines: 26,272 → **26,287 (+15)**.
- `git diff --shortstat c7410df0 -- lib`: 4 files, +35/−20.
- Per issue:
  - Issue 1, +12. `attributePlugs` +8 and `_plugSession` −4 in TWCMaster; Presence +7; registry +1.
  - Issue 2, +3. Early check +5; wake-path check −2.

## Concerns

1. **The restart ping (15:24:33) remains.** Each restart with the car away costs one about 25 s BLE miss, because the policy pass runs about 26 s before TeslaMate's retained topics arrive (the 30 s `syncTelemetry` delay). Two ways to avoid it:
   - hold a PRESUMED car's non-plug message until every configured feed has connected once;
   - or shorten the delay.

   Either is a design choice for the user.
2. **The car is home by radius but out of BLE range.** At 15:49:59 the car parked inside the 1,000 ft box. That made it HOME ("parked inside the radius"), and a BLE send can still time out there. The radius check is a square: ±1,000 ft of latitude, and the same number of degrees of longitude, which is about 770 ft east–west at 39°. The fix covers the driving case only.
3. **Task 12's row no longer covers a miss while driving in.** That miss can't happen any more for a driving car. Task 12's `returned()` free-failure gate is now defensive for that path, and it still applies to PRESUMED misses that aren't driving.
4. **The retry covers Gen2 only.** Gen3 still has the cloud VIN as its correction. `attributePlugs()` queues one cheap job per Gen2 on each pushed plug-in by an unnamed car, whether or not that Gen2 is anonymous; `attribute` returns quietly.
5. **The pilot rule is looser.** A car at rest on another charger, at a different pilot, is now neutral rather than excluded. With two reached cars this can turn a correct attribution into "ambiguous". That is the safe direction: the feed's plug-in retry then names the car.
6. **The box's actual BLE pilot at `Complete` is unknown.** The row assumes a mismatch (48 A against 6 A) to pin the rule.
7. **A restore is still not gated.** A restore to a NOT_HOME car skips applicability, by ruling (a restore sends everywhere). Over BLE it still runs its read, about 15 s with the car out of range. This is the one intended exception to "no BLE run before a NOT_HOME car's verdict".
8. **The retry has a short window.** For a car at its limit, the Gen2 session lasts about 15 s (03, then 00 at 15:54:15). If the BLE worker is busy, the retry job runs after `endPlugSession`, and `attribute` returns None quietly. Issue 2's fix narrows that window but doesn't close it. The first attempt, now fixed, is the main path.

---

# Fix round 1

Commit **23ea9d27** "Keep a just-unplugged or other-charger car out of a plug's match" (parent c8d82ee1). Not pushed.

## Findings and fixes

- **Important 1: a just-unplugged car could win the plug.**
  - `fits` now returns False when `v.markAt("unplug") > since - REACH_WINDOW > NEVER`, that is, an unplug event less than 300 s before the plug, or any time after it. The chained `> NEVER` keeps direct `pick` callers, which have no `since`, unchanged.
  - The box case is unaffected: a retained reading after a restart makes no unplug mark.
  - **Test:** `test_a_car_just_unplugged_is_not_the_next_plug_s` (parity). Car 1's feed reports a plug and then an unplug, and car 1 keeps BLE contact. Car 2 is silent on BLE and plugs in 30 s later. Car 2 is named, not car 1.
  - **Red before:** car 1 got `twcVin 8244` through the reached stage.
- **Important 2: the at-rest pilot rule let a car on a mobile connector win.**
  - "Pilot mismatch excludes" is restored for every state.
  - `pick`'s `offered` may now be a callable that gives the point's offer as it is now. `attributePlugs` passes `lambda: s.reportedAmpsMax`.
  - The pilot is matched against both the offer when `pick` started and the offer after the read, so a match against either counts.
  - **The box row now uses a rising offer.** The plug is at 6 A, the BLE read raises the slave to 47 A (as the TWC did at 15:54:02), and the car reads `Complete` at 47. It is named.
  - With the post-read offer removed, the row is red.
  - **UMC test:** `test_presence_attribution.py::test_a_car_resting_on_a_mobile_connector_is_not_the_twc_s`. Car A is `Complete` at a 32 A pilot with BLE contact; car B is inside; the offer is 47. B wins. It was red under the round-0 rule (A won).
  - The round-0 unit test `test_a_car_at_rest_at_another_pilot_is_still_a_candidate` is **deleted**, because it pinned the rule that was withdrawn. It is replaced by the UMC test and the rising-offer row.
- **Minor 1: an old anonymous point could take a car plugged in elsewhere.**
  - `attributePlugs` now queues a job only for points that are still anonymous and whose `plugIn` mark is no older than `PLUGGED_JUST_NOW` (120 s). The first attempt always qualifies.
  - **Test:** `test_a_plug_unnamed_for_long_does_not_take_a_car_plugged_in_elsewhere`. The point has been anonymous for 3,600 s when the feed reports a plug-in, and the car is not named.
  - **Red before:** the car was named at 8244.
- **Minor 2: a driving hold outlived the car going away.**
  - `plan`'s gate is now `decide(...)[1] == "driving"` instead of `drivingNow`. Once a fix outside the radius makes the car NOT_HOME, the gate passes on that newer observation. The attempt then meets the early NOT_HOME check in `runAttempt` and is cleared, with no I/O.
  - **Test:** `test_presence.py::test_a_driving_hold_clears_once_the_car_is_seen_away`. The car is held driving inside the radius, then placed away while still driving. The desire is cleared, with no ping and no run.
  - **Red before:** the desire stayed at 50.
  - Row :2231 keeps its restart-first order. The driving-first order is covered by this test.
- **Minor 3: report correction.** A PRESUMED car that is driving, holds a limit and has never unplugged still gets a start or rate attempt: `applicable` SENDs it as "plugged in" through the held presumption, so it passes the early check and is pinged. That is pre-existing behaviour. The early check stops only the verdicts that are not SEND.
- **Minor 4: Gen3 retry.** Noted only. A Gen3 plug left anonymous is not retried on the feed's plug-in; its cloud VIN remains its correction.
- **Cuts taken:**
  - the `noteObservation` retry comment;
  - the `runAttempt` early-check comment;
  - the `attributePlugs` comment, shortened to one line;
  - the walrus in `attribute`, which black keeps on one line.

## Results

- The covering files (`test_command_path_parity.py`, `test_presence.py`, `test_presence_attribution.py`) all pass.
- `tests/unit` + `tests/EMS`: **2151 passed**.
- `black --check` is clean on the touched files.
- No existing parity row's counts moved in this round.

## Lib delta vs c7410df0

- `.py` lines: 26,272 → **26,298 (+26)**. This round added +11 to round 0's +15.
- `git diff --shortstat c7410df0 -- lib`: 5 files, +47/−21.
- This round by item:
  - the unplug exclusion, +2;
  - the either-offer match, +4;
  - the gated retry with the offer callable, +7;
  - the gate change, 0;
  - cuts, −3;
  - the `pick` comment, +1.
