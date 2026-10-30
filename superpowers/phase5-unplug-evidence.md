# Phase 5: evidence on false Gen2 "00" (unplugged) reports

Question: does the Gen2 TWC report status 00 while the car is actually plugged
in, how often and for how long, and would the planned Gen2 unplug rule (00 held
60 s, after a non-00 run of at least 60 s, with the 00 starting at least 300 s
after the TWC linked) have declared a false departure, possibly feeding a
wake/restore loop?

Short answer: yes, it would have misfired, twice in one morning. In this data
the trigger is the **car waking up**, not the car going to sleep. When a
plugged-in car wakes, this TWC tends to report 00 (broken up by brief 09/03
replies) until the car either starts a charge or goes back to sleep, and after
either one it holds a steady 03. It does not report 00 every time the car is
awake: after a 14 s charge at 08:39 the car stayed awake until 08:54 while the
TWC held 03.
A TWCManager BLE wake produced a 00 within 0-2 s in all 3 logged cases. A
debounce on its own cannot separate the false 00s from real unplugs at any
useful latency. One heartbeat field separated them perfectly here: the slave's
reported max amps (`reportedAmpsMax`) was 0.00 A at the onset of both real
unplugs and non-zero at all 34 false onsets. Only 2 real unplugs were observed,
so this needs more data before anyone relies on it alone.

## 1. Data coverage (read this first)

| Source | Window (local time, EDT) | What it gives |
|---|---|---|
| `journalctl -u twcmanager` (volatile, size-capped ~8 MB) | 2026-10-17 05:31 to 2026-10-18 01:00 (~19.5 h) | Every slave-heartbeat status change (`SHB` lines are logged on any change other than a <1 A amps change, and at least every 10 min, at INFO). 351 SHB lines. Three service segments: 05:31 (already running; real link time is before coverage), restart 16:12:21, restart 21:34:37. |
| `~/crash-capture.log` (journal capture) | 2026-09-05 10:29 to 11:44 | A boot/restart loop: 9 service starts, about 4 min apart. 14 00-runs, all within 300 s of a link and all cut short by the next restart. Exercises the post-link path only. |
| `~/twc-events/events.log` (filtered journal follower) | 2026-10-09 to 2026-10-17 | Presence decisions logged by **earlier presence builds** (whose debounce and grace may differ from the planned rule), including TWC-derived unplugs and telemetry vetoes. No SHB lines. |
| `~/twc-debug-20261014.log.gz` | 2026-10-14 11:17 to 2026-10-15 07:13 | Debug capture with TeslaMate MQTT `plugged_in` and `state` events. No SHB lines. |
| TeslaMate Postgres (read-only queries) | full history; used 2026-09-03 to 2026-10-18 | `drives`, `charging_processes`, `states` (only `online`/`offline` here, no `asleep`), `positions.outside_temp`. TeslaMate stores times in UTC; converted to America/New_York. |

Caveats:
- **Status-run data covers about one day** (Oct 17-18) for the main path. One Gen2 TWC, one car (Model 3).
- **Only 2 real unplugs** have SHB data. Every discriminator below rests on n=2 positives.
- Outside temperatures during all episodes were **11-25 °C**. The cold-weather "car unlatches the port" mechanism the user described is **not tested** by this data.
- TeslaMate's `states` lags the car by about 30-50 s: the TWC's 00 shows up before TeslaMate records offline→online.
- Logging verbosity differs between builds. The Oct 14-15 debug capture has no SHB lines, and events.log keeps only presence/limit lines.
- Suggested user action (not done; the box was read-only): add `SHB ` to the `twc-events/follow.sh` grep so the next analysis has weeks of status runs that survive journal rotation.

## 2. Method

1. Parsed `SHB 8244: <status> <actual>/<max>A ... M: <master status> ...` lines plus service start/stop markers into maximal runs of 00 and of non-00, per service segment. "Since link" means time since the first SHB after a service start.
2. Ground truth from TeslaMate. A 00 run is TRUE if a drive starts within 10 min of its onset. It is FALSE if the car stays put (no drive) until the TWC returns to non-00, or until a charge session starts without a drive in between.
3. Simulated the planned rule (a direct port of `TWCSlave._checkPlugState`: 60 s debounce, prior non-00 run ≥60 s, 300 s link grace, replug = 01/03/08 then 60 s non-00) over the step-function status timeline, plus these variants: longer debounce (120/300/600/900 s), and an extra "slave max amps = 0 at the 00 onset" gate.
4. Read the journal around each episode for TWCManager actions (BLE wakes, commands).

## 3. Timeline of status runs, 2026-10-17/18

P = non-00. Codes are the statuses seen within the run. "Truth" comes from TeslaMate drives.

| # | Run | Start | End | Dur (s) | Codes | Since link (s) | Truth / context |
|---|---|---|---|---|---|---|---|
| | P | 05:33:27 | 07:58:28 | 8701 | 03 | (≥8701) | asleep (TM offline) |
| 1 | 00 | 07:58:28 | 08:06:35 | 487 | | 8701 | **FALSE**. Car woke (TM online 07:58:57). No TWCManager wake logged. |
| | P | 08:06:35 | 08:06:48 | 13 | 09 | | echo of master 09 |
| 2 | 00 | 08:06:48 | 08:07:37 | 49 | | | FALSE |
| | P | 08:07:37 | 08:07:49 | 12 | 09 | | |
| 3 | 00 | 08:07:49 | 08:13:59 | 370 | | | FALSE |
| | P | 08:13:59 | 08:14:14 | 15 | 03,09 | | |
| 4 | 00 | 08:14:14 | 08:16:23 | 129 | | | FALSE |
| | P | 08:16:23 | 08:16:37 | 14 | 03,09 | | |
| 5 | 00 | 08:16:37 | 08:18:40 | 123 | | | FALSE |
| | P | 08:18:40 | 08:24:55 | 375 | 03,04 | | |
| 6 | 00 | 08:24:55 | 08:34:53 | 598 | | 10288 | **FALSE** |
| | P | 08:34:53 | 08:34:57 | 4 | 03 | | |
| 7 | 00 | 08:34:57 | 08:39:01 | 244 | | | FALSE. Car started a 14 s charge at 08:39 (still plugged). |
| | P | 08:39:01 | 11:12:17 | 9196 | 01,03,08,09 | | car back asleep 08:54 |
| 8 | 00 | 11:12:17 | 12:25:35 | 4398 | | 20330 | **TRUE**: drive starts +73 s |
| | P | 12:25:35 | 12:25:51 | 16 | 09 | | car home 12:23:51; plug-in (slave max resets to 6 A) |
| 9 | 00 | 12:25:51 | 12:26:08 | 17 | | | FALSE (just plugged in, awake) |
| 10 | 00 | 12:26:20 | 12:35:20 | 540 | | | FALSE |
| 11 | 00 | 12:35:32 | 12:36:22 | 50 | | | FALSE |
| 12 | 00 | 12:36:34 | 12:36:36 | 2 | | | FALSE. 03 at 12:36:36; TM offline 12:36:22. |
| | P | 12:36:36 | 13:08:44 | 1928 | 03 | | asleep |
| 13 | 00 | 13:08:44 | 15:00:51 | 6727 | | 27317 | **TRUE**: drive starts +394 s |
| | P | 15:00:51 | 16:12:20 | 4289 | 03,09 | | home 14:59:25; asleep 15:11 |
| | restart 16:12:21 | | | | | | |
| 14 | 00 | 16:12:48 | 16:17:53 | 305 | | 7 | FALSE. TWCManager BLE wake (setAmps) at 16:12:46. |
| 15 | 00 | 16:18:05 | 16:18:54 | 49 | | 324 | FALSE |
| 16 | 00 | 16:19:06 | 16:25:05 | 359 | | 385 | FALSE. 03 at 16:25:05; TM offline 16:24:51. |
| | restart 21:34:37 | | | | | | |
| 17 | 00 | 21:35:04 | 21:35:59 | 55 | | 8 | FALSE. TWCManager BLE wake (setAmps) at 21:35:04. |
| 18 | 00 | 21:36:11 | 21:37:00 | 49 | | 75 | FALSE |
| 19 | 00 | 21:37:11 | 21:42:06 | 295 | | 135 | FALSE |
| 20 | 00 | 21:42:18 | 21:43:07 | 49 | | 442 | FALSE |
| 21 | 00 | 21:43:19 | 21:47:46 | 267 | | 503 | FALSE. 03 at 21:47:46; TM offline 21:47:33. |
| | P | 21:47:46 | 00:00:19 | 7953 | 03 | | asleep |
| 22 | 00 | 00:00:19 | 00:00:33 | 14 | | 8723 | FALSE. TWCManager BLE wake (setChargeLimit) at 00:00:18, then the scheduled charge starts (08 at 00:00:33). |
| | P | 00:00:33 | (open) | | 01,03,08,09 | | charging to 00:35, asleep 00:46 |

Every non-00 gap inside a false episode is a 2-16 s reply (09, or 03/09) to a
master "09" (set amps) command. With those blips merged, the false
**episodes** were:

| Episode | Span | Length | Cause visible in logs |
|---|---|---|---|
| A | 07:58:28-08:18:40 | 1212 s | car woke (cause unknown) |
| B | 08:24:55-08:39:01 | 846 s | car still awake |
| C | 12:25:51-12:36:36 | 645 s | just plugged in after a drive, awake until it slept |
| D | 16:12:48-16:25:05 | 737 s | service restart plus TWCManager BLE wake |
| E | 21:35:04-21:47:46 | 762 s | service restart plus TWCManager BLE wake |
| F | 00:00:19-00:00:33 | 14 s | TWCManager BLE wake; charging began |

### Observed mechanism

- **03 = plugged in and the car asleep** (the long steady runs 05:33-07:58, 12:36-13:08, 16:25-21:34, 21:47-00:00 all sit inside TeslaMate `offline`).
- **00 shows up when the car wakes, and in some awake states.** It lasts until the car sleeps or a charge starts. The TWC went back to 03 within about 15 s of TeslaMate recording the car asleep (12:36:22→12:36:36, 16:24:51→16:25:05, 21:47:33→21:47:46, 00:46:15→00:46:28). A charge start, even a 14 s one, also brought it back to 03: from 08:39:23 the TWC held 03 although the car stayed online until 08:54:29. So "awake" is not the same as "00".
- **TWCManager's own wakes produce 00 immediately**: `wake … before setAmps: done` 16:12:46 → 00 at 16:12:48; 21:35:04 → 00 at 21:35:04; `wake … before setChargeLimit: done` 00:00:18 → 00 at 00:00:19 (the clean case, no relink involved).
- So the loop driver is **anything that wakes the car**, not "the car sleeps → 00". This is the reverse of the hypothesis. A long sleep with port unlatching in the cold may behave differently, but nothing like it appears in this data.

## 4. Counts and durations

**Oct 17-18 (journal): 22 runs of 00. 2 TRUE, 20 FALSE.**

False run durations (s), sorted: 2, 14, 17, 49, 49, 49, 49, 50, 55, 123, 129,
244, 267, 295, 305, 359, 370, 487, 540, 598. Median about 89 s, max 598 s.

| False runs (n=20) | > 60 s | > 120 s | > 300 s | > 600 s |
|---|---|---|---|---|
| count | 11 | 11 | 6 | 0 |

Merged episodes (n=6): 14, 645, 737, 762, 846, 1212 s. Five of six exceeded 600 s.

True runs: 4398 s and 6727 s. Drives started +73 s and +394 s after the 00 onset.

**Sep 5 (crash capture): 14 runs of 00, all FALSE** (car plugged in at home and
started charging at 11:37, first drive 13:24). Lengths 0-129 s, all cut short by
the next restart, and all within 300 s of link.

**Oct 9-12 (events.log, earlier builds; no status runs):**

| Time | Earlier build logged | Truth (TeslaMate) |
|---|---|---|
| 10-09 19:18:32 | TWC unplug → departing, BLE restore issued; cancelled by TWC proof 19:29 | FALSE. 87 s after a restart, about 1 min after an arrival BLE command (19:17:37); car went online 19:18:02; no drive until the next day. Not vetoed: that build may have lacked the telemetry gate (the veto message first appears Oct 10, and the build was crashing in VehiclePresence at 19:15 and 19:29), or telemetry was not yet subscribed about 70 s after a restart. |
| 10-10 08:30:01 | "TWC unplugged; live telemetry says plugged in, so not departing" | FALSE (car woke 08:29:11; no drive for 11 h). Telemetry gate caught it. |
| 10-11 08:09:00 | same veto | FALSE (car woke 08:08:25; no drive for 9.5 h). Telemetry gate caught it. |
| 10-12 09:01:05 | TWC unplug → not_home | TRUE (drive started 09:00:56) |
| 10-10 19:34, 10-11 17:41, 10-12 07:45 | telemetry `plugged_in` false → departing | TRUE (drives started 1-2 min later) |

Again, every false 00 coincides with the car waking. Most are in the
07:58-08:35 window or just after a restart.

## 5. Would the planned rule have misfired?

Simulation of `_checkPlugState` (60 s / prior run ≥60 s / 300 s grace) over Oct 17-18 and Sep 5:

| Event | Time | Truth |
|---|---|---|
| UNPLUG | 07:59:28 (00 from 07:58:28) | **false** |
| REPLUG | 08:19:40 | (car never left) |
| UNPLUG | 08:25:55 (00 from 08:24:55) | **false** |
| REPLUG | 08:40:01 | |
| UNPLUG | 11:13:17 | true (drive 11:13:29) |
| REPLUG | 12:37:36 | true (home 12:23:51; delayed because 09 is not a PLUGGED_STATE) |
| UNPLUG | 13:09:44 | true (drive 13:15:17) |
| REPLUG | 15:02:06 | true |

**2 false unplugs out of 4 declared (and 2 false replug/arrivals), all in a 40-minute window on a mild morning.** Nothing misfired on Sep 5.

Which mechanism blocked the other false runs:
- **An unplug was already reported** (`_unplugReported` stays set until a replug: PLUGGED_STATE plus 60 s non-00), so later 00s were never evaluated. This covered runs 2-5 (after the false 07:59:28 unplug; replug 08:19:40) and runs 9-12, including the 540 s run 10 (after the true 11:13:17 unplug; replug 12:37:36). **The prior-run condition did not protect these runs.** Had the first unplug not fired, run 3 (370 s) and run 10 (540 s) would still have been blocked by the prior-run rule only because their 09 blips were short.
- The **prior ≥60 s non-00 run** condition blocked runs 15, 16, 19, 21 (after restarts; each preceded only by a 12 s 09 reply), plus runs 18 and 20, which were under 60 s anyway.
- **Link grace** blocked runs 14 and 17, and all of Sep 5.
- **Debounce** blocked run 22 (14 s; it qualified otherwise).
- So the misfires came from the **first** 00 run of an awake episode after the car had slept on 03 for a long time (runs 1 and 6). Any wake while the car is plugged in, more than 5 min after link, sets up this condition.

Trace of the planned build through 07:58-08:40, as a loop:
1. 07:59:28 departure → restore the normal limit (a raise, so BLE wakes if needed; the car was already awake).
2. 08:19:40 replug → HOME → arrival applies the held limit (a lower; logs show "lower never wakes").
3. 08:25:55 departure → restore again (raise).
4. 08:40:01 arrival → apply again.

That is 4 BLE limit commands and two departure/arrival cycles in 41 min. A
restore that raises the limit on a plugged-in car can also start an unplanned
charge. The loop stopped only because the car went back to sleep (→ 03). Any
handler that wakes the car would restart it: an arrival or restore that needs a
wake, a setAmps wake, or a probe that wakes.

### Debounce alone does not work

| Variant | False unplugs | True detection after 00 onset |
|---|---|---|
| D=60 (planned) | 2 | 60 s |
| D=120 | 2 | 120 s |
| D=300 | 2 | 300 s |
| D=600 | 0 | 600 s (drives started at +73 s and +394 s) |
| D=900 | 0 | 900 s |

D=600 is the first value with no misfires. But the longest false run was 598 s
(2 s margin), and run 1 (487 s) ended only because a 13 s 09 blip interrupted a
1212 s awake episode. At D=600 the car is miles away before the unplug is seen,
so the BLE in-range restore is lost. Rejected.

## 6. Discriminators

| Signal | TRUE (n=2) | FALSE (n=34 onsets, Oct 17 + Sep 5) | Notes |
|---|---|---|---|
| Slave `reportedAmpsMax` at the first 00 heartbeat | **0.00 A both** (`00 00.00/00.00A`; the master then re-sends 09) | **6-48 A in all 34** (`00 00.00/46-48.00A`, or 06.00A just after link) | Field = heartbeat bytes 1-2 (`TWCSlave.reportedAmpsMax`, line 808; "amps requested/allowed" in SlaveProtocol.md). With `+60 s` added to the planned rule it fired on exactly the two true unplugs. |
| TeslaMate `plugged_in` (telemetry gate) | n/a Oct 17 (not logged). Oct 10-12: telemetry unplug arrived 1-2 min before each drive; Oct 14: `plugged_in=false` at 18:40:57, `driving` at 18:43:02 | Vetoed both earlier-build false unplugs that reached the gate (Oct 10, 11); the Oct 9 one was not vetoed (that build may have lacked the gate) | Every false 00 here happens while the car is awake, so TeslaMate is polling and its value is fresh. |
| Drive starts | +73 s, +394 s | never | Reliable confirmation, but too late for an in-range BLE restore. |
| TeslaMate `state` at the 00 onset | offline (it lags) | offline or online | Not discriminating: both kinds of 00 begin with the car waking. |
| Preceded by a TWCManager BLE wake within a few seconds | no | 3 of 3 TWCManager wakes in the window | Self-wake suppression would cover D, E, F. |

Guard on the amps signal: phrase it as a **drop in the slave's own field**.
`reportedAmpsMax` was more than 0 on the last non-00 heartbeat and 0 on the
first 00 heartbeat. Do not compare against the master heartbeat shown in the
SHB line: at every false onset the master field reads `M 00 00.00/00.00A` (an
idle heartbeat carries 0 A), so that comparison would invert the guard. If
TWCManager had already told the slave to allow 0 A (charging stopped by policy),
a plugged-in car would already be at `/00.00A` and no drop could happen. That
case does not appear in this data, so treat the amps signal as unknown there.

## 7. Recommended rule

Keep everything the planned rule has (60 s debounce, prior non-00 run ≥60 s, 300 s link grace) and add gates. Each gate below would have prevented both Oct 17 misfires; together they give some redundancy:

1. **Amps gate (strongest signal in this data):** a Gen2 00 counts as an unplug only if the slave's own `reportedAmpsMax` was more than 0 on the last non-00 heartbeat and is 0 on the first 00 heartbeat (or within a few seconds). If it was already 0 before the 00 (allowed amps set to 0 by policy; untested), treat the amps signal as unknown and fall back to gates 2-3. In this data it separates 2/2 true from 34/34 false and keeps the 60 s latency. Caveat: n=2 positives, one TWC. Log `reportedAmpsMax` at every 00 onset so this can be confirmed over weeks before relying on it alone.
2. **Telemetry gate (already in VehiclePresence):** while live telemetry says `plugged_in=true`, ignore a TWC unplug; telemetry `plugged_in=false` stays an unplug in its own right. False 00s happen while the car is awake, so the telemetry value is fresh exactly when it matters.
3. **Self-wake suppression:** ignore a 00 onset within a window after TWCManager itself woke or commanded the car over BLE (or Fleet). For example, until the TWC next reports 03, capped at 15 min. All three logged TWCManager wakes produced 00 within 0-2 s, and those awake-00 episodes lasted 12-13 min.
4. **Do not wake the car on TWC-only evidence:** if a departure rests on a TWC 00 alone, with no telemetry unplug, no drive and no BLE loss, defer any restore that would need a wake until the departure is confirmed. That breaks the wake → 00 → departure → wake chain even if gates 1-3 miss.

A longer debounce is **not** recommended. No value avoids the false runs and
still catches real unplugs while the car is in BLE range.

Side effect outside the unplug question: a TWC-only **arrival** on a Gen2 waits
until the car sleeps or charges. After the 12:23 return, the plug-in showed only
00/09 while the car was awake, and 09 is not a PLUGGED_STATE, so the replug
landed at 12:37:36. Separately, 05:31-07:53 on Oct 17 shows a BLE
limit command to the sleeping car ("lower never wakes") failing every 5 min.
