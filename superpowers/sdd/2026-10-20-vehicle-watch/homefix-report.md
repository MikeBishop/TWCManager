# Home fix: learn home only from a fix taken after the car reached its TWC

Status: DONE_WITH_CONCERNS (see Concerns)

## Commit and tips

- phase5: **8042dc94** "Learn home only from a fix taken after the car reached its TWC", on b48dd13b.
- phase6: rebased onto it; new tip **f49422e2**.
  - Rebase conflict: tests/unit/test_presence.py, where both sides appended tests at the end. Resolved by keeping both.

Lib lines:
- phase5: 26600 -> 26609 (+9: a constant and its reason, a 3-line comment, 3 lines of code).
- phase6: 27173 -> 27182 (+9).

## The change (`Presence.learnHome`)

- New constant beside `HOME_FIX_MAX_AGE`: `PARKING_SLACK = 300.0`, with the comment "A parked car's last fix is from when it stopped, before the plug went in".
- A fix not from TeslaBLE must have `fixAt >= arrived - PARKING_SLACK`:
  - `fixAt` is the fix's GPS time if its source gave one, else its reading time (unchanged).
  - `arrived = max(vehicle.markAt("plugIn"), vehicle.latest("twcVin").at)`.
- A BLE fix is exempt and keeps only the existing age rule.
- Both call paths go through `learnHome`, so both follow the rule:
  - the TWC VIN read in `TWCMaster.recordVehicleVIN`;
  - `Presence.noteObservation`'s lat/lon branch while `twcVinAt > NEVER`.

### Order of events and the reference time used

At the VIN-read call the named car's own `plugIn` mark is **not** set for this session:
- A Gen2 plug-in opens an anonymous session vehicle (`beginPlugSession`), and that vehicle carries the `plugIn` mark.
- `observeTwcVin` merges only the anonymous vehicle's observations (`snapshot()`) into the named car. Marks do not move, so the session's start is gone from the registry by the time `learnHome` runs.

What the code does have is the `twcVin` observation, stamped at the VIN read: a few seconds after the plug-in, or later if the VIN read is delayed. The reference is therefore `max(plugIn mark, twcVin time)`:
- the `twcVin` time at a VIN read;
- the car's own `plugIn` mark when a newer one exists, for example a re-plug that keeps its old naming.

Using the VIN time is slightly stricter than the true plug-in time. Its only cost is that a fix from more than 5 minutes before a late VIN read is refused, and such a fix is usually past `HOME_FIX_MAX_AGE` anyway.

## Tests (tests/unit/test_presence.py)

| Test | What it checks | Without the fix |
|---|---|---|
| `test_an_away_fix_from_before_the_plug_in_never_moves_home` | The bug: an away cloud fix 540 s before a Gen2 plug-in, then a VIN read 13 s later. Home is unchanged and the car is HOME. | fails (home moves) |
| `test_a_fix_read_after_the_vin_dated_before_the_plug_in_never_moves_home` | The observe path, with no home yet: a cloud read after the VIN read whose GPS time is 8 min before the plug-in does not set home. A fix taken here then does. | fails (home set) |
| `test_a_fix_just_before_the_plug_in_teaches_home[None]` and `[elsewhere]` | The legitimate case: a fix 60 s before the plug-in, with no home or with home elsewhere. Home is learned and the car is HOME. | passes (it can't fail without the fix) |
| `test_a_ble_fix_from_before_the_plug_in_still_teaches_home` | A BLE fix with an 8-minute-old GPS time, after the VIN read, still moves home. | passes (it can't fail without the fix) |

The two "can't fail" rows are checked against wrong fixes instead:

| Mutant | Fails |
|---|---|
| No fix | the bug test and the observe-path test |
| BLE not exempt | the BLE test |
| No slack (`fixAt < arrived`) | both legitimate-case rows |
| `plugIn` mark only, without the twcVin time | the bug test, which confirms the mark is not set at the VIN read |

## Parity

test_command_path_parity.py and test_sleeping_car.py counts are identical to the previous tip's, row for row. No paid count moved.

## Suites

| Branch | Before | After |
|---|---|---|
| phase5 | 2298 | 2303 passed, 1 xfailed |
| phase6 | 2414 | 2419 passed, 1 xfailed |

## Docs

The sentence on how home is learned now says: "a position not read over BLE must also date from no more than 5 minutes before the car reached its TWC (its plug-in or the VIN read), so a fix from before the drive home never moves home". Updated in:
- CHANGELOG (the `atHomeRadius` / home line);
- docs/Settings.md;
- docs/PolicyCustomization.md;
- docs/modules/Vehicle_HomeAssistant.md.

## Concerns

1. **A late-arriving stale cloud fix marks the car away.** A cloud position whose GPS time is old but which arrives after the VIN read marks `outside` at its arrival time if it falls outside the radius. `twcVinAt` then treats that as movement since the naming, and the car counts as away. The new observe-path test met this with home set, so it runs with no home instead. The fix keeps such a fix from moving home but does not change the `outside` mark. Dating `outside` by the fix's GPS time would close the gap. That is outside this brief and not done.
2. **With a home already set, the observe path never moves home.** The `lon` observation marks `outside` before `learnHome` runs, and `twcVinAt` then returns NEVER. Only the no-home case learns on that path. The VIN-read call is unaffected. This is unchanged behaviour, noted because the brief lists the observe path as a mover.

## Round 2: concern 1 fixed, concern 2 parked

New tips: phase5 **6a8275d6**, phase6 **dbd91043**.
- The change was folded into the home-fix commit with `--fixup` and `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash`. I amended the message to cover the presence dating.
- Phase6 was rebased with `--onto 6a8275d6 8042dc94`. The one conflict was in test_presence.py, where both sides appended tests; I kept both.

Lib lines:
- phase5: 26600 -> 26616 (+16 for the whole commit; round 1 was +9).
- phase6: 27173 -> 27189 (+16).

### The change

There is a new helper, `Presence._fixAt(vehicle, obs)`. It dates a fix the way `learnHome` always did: the source's GPS time (`gpsAsOf`) if it gave one, else the reading's time. Three places now use it:
- `learnHome`, which replaces its two inline lines.
- The lat/lon branch of `noteObservation`: the `outside` mark is dated by the fix, not by arrival. This is what the ruling asked for.
- `_fix()`: the newest position's time, which `decide()` compares with the plug-in and VIN-read evidence.

Dating only the `outside` mark was not enough. `decide()` also returns NOT_HOME when the newest fix is outside the radius and newer than the home evidence, and `_fix()` dated that fix by arrival. The test stayed NOT_HOME until `_fix()` used the fix time too; the mutation checks below show that each half is needed.

On phase6, `Watch` uses `_fix()`'s time in two places:
- `late = now >= max(fixAt, lastRead) + wait`. This is still bounded by `lastRead`, so an old GPS time cannot cause repeated reads.
- `_backAt`, the soonest an away car could be home. It now counts from when the car was actually at that place: earlier, and correct for a straight-line return estimate.

### Test

`test_a_stale_away_fix_arriving_after_the_plug_in_keeps_the_car_home`:
1. The car is plugged in on a Gen2 and named by the VIN read.
2. 30 s later, a cloud away fix arrives whose GPS time is 9 minutes before the plug-in.
3. Expected: the car is HOME, home is unchanged, and `applicable(SET_CHARGE_LIMIT)` is SEND, so the limit is not held "not here".

Mutation checks:
- The `outside` mark dated by arrival time: fails (NOT_HOME).
- `_fix()` dated by arrival time: fails (NOT_HOME).
- Without either change it failed as written (NOT_HOME).

### Concern 2 (parked)

No doc claims that the observation path moves an existing home. Settings.md, PolicyCustomization.md, Vehicle_HomeAssistant.md and the CHANGELOG all limit the "while a TWC is naming the car" case to "with no home set yet".

Two doc edits this round:
- Vehicle_HomeAssistant.md's parenthetical applied the 5-minute rule to BLE. It now reads "unless read over BLE".
- The CHANGELOG home line adds that a position counts from its own GPS time, so a fix like this, read after the car is plugged in, never makes it away.

### Suites and parity

- phase5: 2304 passed, 1 xfailed (2303 before this round).
- phase6: 2420 passed, 1 xfailed (2419 before this round).
- The parity and sleeping-car request counts are identical to the previous tip, row for row. No paid count moved.

## Round 3: the user's rule (supersedes rounds 1 and 2 and the review's fixes)

New tips: phase5 **d370287b**, phase6 **004f2235**. The change was folded with `--fixup` and autosquash, and the commit message was rewritten to the new rule.

### Lib delta for the whole home-fix commit

- phase5: 26600 -> 26606 (+6).
- phase6: 27173 -> 27179 (+6).

Against the pre-home-fix phase6 tip (e976d6d0), phase6's lib differs only in `Presence.learnHome`. Watch.py, `_fix()`, the `outside` mark and `decide()` are byte-identical to before this commit.

### Rule

`learnHome` now refuses a fix not read over BLE when `lat.at < max(plugIn mark, twcVin time)`, that is, when the read came before the car reached its TWC.
- It uses the observation's own time, with no slack; `PARKING_SLACK` is gone.
- BLE is exempt.
- The `HOME_FIX_MAX_AGE` check (by GPS time) is unchanged.
- Reverted: `_fixAt`, GPS-dated `_fix()` and `outside`, and the `_fix(gps=)` split. The review's I1, I2, M1 and M3 no longer apply; M2 does not apply to code.
- The planned phase6 watch test was dropped, because the watch is unchanged.

### Tests (test_presence.py)

| Test | Without the fix |
|---|---|
| `test_an_away_fix_from_before_the_plug_in_never_moves_home`: the 12:39 -> 12:48 bug. Home does not move and the car is HOME. | fails |
| `test_a_read_after_the_plug_in_teaches_home_whatever_its_gps_time`: no home yet; a read 30 s after the plug-in, GPS 3 min before it, outside. Home is learned. | passes |
| `test_a_ble_fix_from_before_the_plug_in_still_teaches_home`: kept unchanged. | passes |
| `test_a_ble_fix_read_before_the_vin_read_still_moves_home_at_it`: new; a BLE fix read before the VIN read moves a wrong home at the VIN read. | passes |

The second test passes without the fix because the old code also learned from that read; that case must keep working, not start working. The two passing BLE tests are the same kind of guard, so all three are checked by the wrong-fix mutations instead.

Mutation checks:
- No rule: the bug test fails.
- GPS time used instead of the read's time: the read-after-plug-in test fails.
- BLE not exempt: the new BLE test fails. The old BLE test does not catch this, because its fix is read after the VIN.

Dropped as reverted behaviour:
- the 60 s-before-plug-in test (now refused);
- the observe-path GPS-dated test;
- the stale-away-fix-after-plug-in test;
- the own-read GPS-time test.

### Changed existing test

`test_twcmaster_vin_confirmation.py::test_a_confirmed_vin_learns_home_from_the_cars_fresh_fix_without_io` learned home at the VIN read from a TeslaMate fix read before it, which the rule now refuses. It now uses a BLE fix, which keeps its point: learning without I/O on the RS-485 thread.

### Docs

The CHANGELOG, Settings.md and PolicyCustomization.md are restored to the pre-commit text, plus one sentence: "A position not read over BLE must also have been read after the car reached its TWC (its plug-in or the VIN read), so a read from before the drive home never moves home." Vehicle_HomeAssistant.md's parenthetical says "and, unless it came over BLE, read after the car reached its TWC".

### Suites and parity

- phase5: 2302 passed, 1 xfailed.
- phase6: 2418 passed, 1 xfailed.
- Parity and sleeping-car request counts are identical to the previous tip; no paid count moved.

### Concern: an existing home can now move only over BLE (or by hand)

- **At the VIN read,** the reference time is the VIN read itself, so no earlier non-BLE read qualifies.
- **After the VIN read,** a cloud read outside the old radius marks `outside` before `learnHome` runs, and `twcVinAt` then returns NEVER. This is the parked concern 2.

So a cloud fix teaches home only when no home is set. With a home set, the user's case "a read 30 s after the plug-in ... home moves" does not happen. I tried calling `learnHome` before the `outside` mark, and that made it work. But it broke `test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix`: a deliberate rule that an outside fix after the naming is a departure, not a new home. I left that unchanged, and the new test covers the no-home case only. Deciding between "an outside fix while named moves home" and "it is a departure" needs a ruling.
