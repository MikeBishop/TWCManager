# Review: learn home only from a fix taken after the car reached its TWC

Reviewed: phase5 6a8275d6 (on b48dd13b) and phase6 dbd91043 (rebased onto it). Line numbers are phase5's `lib/TWCManager/Vehicle/Presence.py` unless a file is named; Watch.py is phase6's.

## Verdicts

- **Spec compliance: PASS.** All of these are in place:
  - `PARKING_SLACK = 300.0` beside `HOME_FIX_MAX_AGE`, with a one-line reason.
  - BLE is exempt from the plug rule.
  - Both call paths go through `learnHome`.
  - The order of events was checked, and the reference used (`max(plugIn mark, twcVin time)`) is stated.
  - The ruling is applied: the `outside` mark is dated by the fix's GPS time, and so is `_fix()`, which was needed for the ruling's test to pass.
  - Docs and CHANGELOG are updated, the commit subject and trailer are right, and phase6 is rebased.
  - Two of the brief's tests (the legitimate case and BLE) can't fail without the fix. The implementer covered them with targeted mutants, which is the right substitute.
- **Quality: CHANGES NEEDED.** The `learnHome` gate itself is correct and errs only toward refusing a fix. The new problems come from extending GPS-time dating to `_fix()`:
  - Phase6's watch now reads a far-away awake car more often than before (paid reads).
  - A fix with no GPS time borrows the time of an older read.

Verified:
- `test_presence.py` passes on phase5 (101).
- presence and watch tests pass on phase6 (187).
- Lib growth is +16 in `Presence.py` (497 to 513).
- I confirmed findings I1 and I2, and the first scenario in M1, with throwaway probes, since deleted. Each probe ran against b48dd13b and 6a8275d6, or against dbd91043 for the watch.

---

## Critical

None.

## Important

### I1. The watch now times an away car's return and its courtesy window from GPS time. Both need the time the position was last read.

`lib/TWCManager/Vehicle/Watch.py:334-343` (`_backAt`) and `Watch.py:263-264` (`late`), through `Presence.py:61`.

Phase6's watch code did not change in the rebase, but `_fix()[1]` now means "when the car was there", not "when we last learned where it is". A cloud read that returns an unchanged, GPS-stale position comes from an awake car that has had no fix since. That is a car still in a garage, so it is evidence the car was there at the time of the read. Counting from the GPS time throws that evidence away.

- **`_backAt`, failure scenario.** API-only. The car is awake all day in a parking garage 111 km from home: sentry mode, cabin overheat protection or dog mode. GPS has been frozen since it entered at 09:00.
  - Before: a watch read at 12:00 put `backAt` at about 12:56 (12:00 plus 55 minutes at 120 km/h). The away car was left alone until then, and read about once an hour.
  - Now: `backAt` = 09:00 plus 55 minutes = 09:56, already past. The early return at `Watch.py:258` never fires. `late` reads the car every `sleepCourtesySecs` (1200 s), about 3 paid Fleet reads an hour instead of 1, for as long as it stays awake.
  - Probe: with GPS 3 h old and 111 km away, `_backAt(v, now) - now` is -7467 s. It should be about +3333 s.
- **`late`, failure scenario.** API-only, with the car garaged at home and GPS frozen since it parked. At 08:00 a Gen2 status edge runs `checkPlug`, which makes a paid cloud read. That read does not touch the watch's `lastRead`, which was last set yesterday.
  - Before: that read's fix arrived at 08:00:05, so `late` stayed false until 08:20.
  - Now: `fixAt` is yesterday's GPS time and `lastRead` is yesterday, so on the next pass the watch makes a second paid read seconds after the first.
  - The comment at `Watch.py:261-262` ("it is read once its fix is a courtesy window old") depends on any read's fix resetting the window, and that no longer holds once GPS is frozen.

Neither case loops (both are bounded by `lastRead + wait`), and neither wakes a car (`_read` returns for asleep states). But each repeats paid reads, which is what this watch's design exists to prevent.

**Fix:** keep `decide()` on GPS time, but give the watch the read's time. For example, `_fix` could return both times, or `_backAt` and `late` could use `max(v.latest("lat").at, v.latest("lon").at)`. Add a watch test with a GPS-stale away fix.

### I2. A fix with no GPS time is dated by an older read's GPS time

`Presence.py:482-486` (`_fixAt`), now used by `_fix` (`:61`) and by the `outside` mark (`:126`).

`_fixAt` takes the source's latest `gpsAsOf`, however old it is. The comment says it was "observed before the position", but nothing checks that it came from the same read:
- `TeslaAPI.py:1865` observes it only `if drive.get("gps_as_of")`;
- `TeslaBLEProvider._get` drops a `None` (`gpsAsOf` missing, or `seconds: 0`).

So a read without a GPS time keeps the previous read's, and `min(obs.at, gps.value)` dates the new fix to then. Before this commit that only made `learnHome` refuse a fix, which errs on the safe side. Now it decides presence.

- **Failure scenario.** Yesterday at 18:00 the car parked at home (a cloud read with `gps_as_of`), then plugged in (plug-in mark at 18:01). Today it leaves, and the unplug goes unseen, as at 12:19 in the box log. A 18:00 cloud read finds it 4 km away, and that response lacks `gps_as_of`.
  - The `outside` mark and `_fix` date the departure fix to yesterday at 18:00, which is older than the plug-in mark.
  - `decide()` returns HOME, "plugged in", instead of NOT_HOME, and the car's limit messages go out as if it were home, for as long as reads keep omitting the GPS time.
  - Probe: on b48dd13b this is NOT_HOME, "a fix outside the radius"; on 6a8275d6 it is HOME, "plugged in".

How often a read lacks the GPS time is unknown (probably rare for Fleet). The cost when it happens is a wrong presence that never corrects itself, so it should be closed. Ways to close it:
- pair the GPS time with the fix only when `gps.at` is within the same read (e.g. `gps.at >= obs.at - 1`); or
- have the providers stamp `lat`/`lon` with `at=gps_as_of`, which would also remove `_fixAt` and the `gpsAsOf` lookups.

Add a test with a later fix that has no GPS time.

## Minor

### M1. Fixes are dated by GPS time while the leaving marks are dated by arrival, so a garaged car can lose its "parked inside the radius" evidence

`Presence.py:287-305` (`decide`), with `:61` and `:126`.

`driveStart`, `unplug` and `absent` are stamped on arrival. The fix they are compared against is now stamped by GPS time.

- **Failure scenario.** API-only. The car has been parked in the garage since 18:00, with GPS frozen there (inside the radius). It is unplugged at 19:00 without driving (to free the TWC, or the night before a trip), then read awake at 19:10.
  - Before: the 19:10 fix outranked the unplug, so the car was HOME.
  - Now: the fix counts as 18:00, so the car is NOT_HOME, "unplug". It stays that way until it drives under the sky or is plugged in again. Probe confirmed.
  - The charge-limit outcome is the same, since the base already said NOT_HERE "leaving" for an unplugged car. But the car drops out of `homeCars`/`numCarsAtHome`, and the watch treats it as away.
- **Second scenario.** A read inside the radius showing `D`, a few seconds before the car loses GPS in the garage, stamps `driveStart` after the last GPS time. The car stays PRESUMED, not HOME, until it is plugged in.
- **Related.** `_fix` picks the newest position by arrival but dates it by GPS. A cloud read with GPS lag that arrives after a fresher Fleet Telemetry/TeslaMate/Home Assistant fix (which carry no GPS time and are dated on arrival) replaces it with an older-dated position.

Low impact. Note it, or compare like with like (I2's per-read stamping would at least make the choice of fix consistent).

### M2. The VIN-read time used as "reached the TWC" is the Gen2's charge start, not its plug-in

`Presence.py:497-498`; `TWCMaster.py:1340-1350`.

The Gen2 VIN query is queued when current starts flowing (`lastChargingStart`), and every charge restart re-stamps `twcVin`. The report says "a few seconds after the plug-in", which holds only when charging starts at once.

- **Failure scenario.** No home set yet, or home wrong. The car parks and plugs in at 18:00, the fix is from 17:59, and the Gen2 doesn't start charging until 18:07 (green-energy surplus or a scheduled start). `arrived` = 18:07, so the 17:59 fix is refused (the old rule allowed 10 minutes from the fix). Home is not learned from this session.

The same narrowing applies to Home Assistant and TeslaMate, which push a position only when it changes: their last fix arrived when the car parked. This errs only toward refusing, which is safe, and it is no worse once a fix passes `HOME_FIX_MAX_AGE`. Correct the report's wording. No code change needed.

### M3. A comment overstates when the plug-in mark stays on the anonymous session

`Presence.py:493-494`.

"The session's plug-in mark stays on the anonymous session the VIN read replaces" is true for a Gen2, whose anonymous session carries only the mark. A Gen3's anonymous session receives `pluggedIn True "Gen3TWC"`, and `observeTwcVin`'s merge replays it into the named car, which marks `plugIn` at its original time. With `max()` this does no harm. Suggested wording: "...or the VIN read: a Gen2's plug-in mark stays on the anonymous session it replaces".

The other new comments explain why the code is as it is, and contain no history or phase/task IDs.

## Lib growth (+16)

Reasonable for what it does:
- the constant and its reason;
- the `_fixAt` helper, which replaced two inline lines;
- 4 lines of gate;
- the `_fix`/outside call sites and comments.

I found no duplication to remove at the current design. The one material shrink is I2's alternative: stamp `lat`/`lon` with the GPS time at the provider, which drops `_fixAt` (about 7 lines) and fixes I2. That would also change `obs.at` everywhere, which I1 cares about, so weigh it together with I1's fix.
