# Task 12 review: b613a784..ee65ba2b

Reviewer: opus, read-only. Mutations were run in a scratch copy (scratchpad/rv12). Two git-dependent tests fail there only because the copy is not a git repo, and are excluded.

## Verdicts

- **Spec compliance: ISSUES.** One spec gap (I1) and one stale doc (I2). Everything else matches the addendum: the edge, the courtesy rule, the deferral, never waking, the event class, the hold check, the charging split and the deletions.
- **Quality: APPROVED once I1–I3 are fixed.** The code is clean and the deletions are complete. One rule guard has no test (I3), and about 8–10 lines can come out (S1–S3).

## Findings (ranked)

### I1 (Important, spec): "BLE module loaded" is treated as "BLE can see the car". A dead radio leaves the car unwatched

`Watch.py:60-64` (cloudOnly), `Watch.py:135-137` (`_source`: `api ... and ble is None`), `Watch.py:349` (`_listen`).

The addendum's table puts "BLE unusable" in the API-only row, and the brief says "canScan() is False and pings can't run". The report argues that pings always run when the module is loaded. They do *run*, but they fail when the radio is unusable. `_runPing` calls `tesla-control -ble`, which needs the same adapter. If the adapter is powered off, blocked by rfkill, missing, or bluetoothd is not answering, `canScan()` returns False *and* every ping fails.

What happens in that case:
- **A car at home:** two deaf misses → TWICE → one cloud charge read, if it was last seen awake (`_unheard`) → pings forever, never answered.
  - Its situation freezes at the last reading. A car frozen HOME_ASLEEP that wakes, leaves, returns and plugs into a non-TWC charger is never seen.
  - The old `last == TWICE and api` switch to the cloud covered this. It is deleted.
- **An away car:** bleReach False → `_listen` pings on the back-off forever. The cloud is never asked, so its return is never seen.
- **What the user sees:** the page says "via ble". The log says once that scans are unavailable and that "arrival detection falls back to slower checks" (`TeslaBLE.py:1081`), but nothing falls back. This is a silent gap.

The reconciler's hold check still runs for these cars (not cloudOnly), so Phase 5 is unaffected.

**Smallest fix** (about +3 net, possibly ≤0): treat a car the radio has given up on, where no scan can run, as cloudOnly.
- Widen `_unheard` to "cars the radio stopped hearing where no scan can run". Add on every deaf TWICE, home or away. Discard when a ping answers, as now.
- Change cloudOnly to `api and watched and (ble is None or v.vin in master.watch._unheard)`, or make it a Watch method.
- In `_source`, take the cloud when cloudOnly.
- In `_listen`, keep a back-off ping for those cars too (`lost(v, where) or vin in _unheard`), so the radio reclaims them when it answers.
- The deaf-at-home once-only read (`Watch.py:143-152`) is then served by the courtesy rule and can go. That removes about 5 lines and offsets the fix.
- Tests:
  - noScan with pings unanswered at home and away. The cloud status cadence starts after the second miss, and the courtesy reads apply.
  - A ping that answers returns the car to the radio, and the cloud stops.

This re-introduces cloud polling into a BLE-loaded install, but only where the radio is dead for that car, which is what the addendum's table says. Confirm with the user if in doubt.

### I2 (Important, docs): Vehicle_TeslaBLE.md still describes the deleted cloud hand-off

`docs/modules/Vehicle_TeslaBLE.md:77`: "A car at home that misses two checks in a row is handed to the Tesla API's status check". That path is deleted, and the code now keeps the radio (`test_where_no_scan_can_run_two_misses_at_home_keep_the_radio_and_read_once`). If I1 is fixed, reword it to the new rule. If not, it must say no fallback exists.

`docs/Settings.md:130`: "the watch asks the cloud nothing" contradicts line 132's one cloud charge read. Say "asks the cloud no status" or similar.

### I3 (Important, tests): the lastRead term of the courtesy rule is untested

`Watch.py:258`, `max(fixAt, lastRead)`. Mutation `late = now >= fixAt + wait` passes the whole suite.

Without it, a failed or refused read leaves fixAt unchanged. The same happens with a read that returns no position, such as a car with no GPS fix in a garage. In either case `late` stays True.
- **Away (AWAY_AWAKE):** nothing drops a non-exempt ask, so a paid Fleet read would be asked on every pass until the event budget is gone.
- **Home:** the `recent` check in `_read` saves it.

Add a test: an API-only awake car away, past its return time, whose read fails with a 500. It gets one read, plus one retry at chargingReadSecs, and the next read only after a window.

### M1 (Minor): restart

The courtesy rule has no first-pass floor. A car restored as awake with a fix older than 20 min is read on the first pass after a restart. That is at most one read, and the read path makes its free online check first. This is consistent with the old location read, so accept it. The report's concern 4 covers it.

### M2 (Minor): readsBattery coverage

- `getScheduledAmpsTimeFlex` (`TWCMaster.py:747-764`) reads the TWC car's batteryLevel. It is computed before the scheduled start, so the plug-in read's level stands. It is not a gap.
- Flex *current* (`greenEnergyFlexAmps`, `allowed_flex`) is gone from lib. Confirmed: no code reads it, and docs/PolicyCustomization.md:147 and config_examples.md:24 say so.
- The limit override is included, and `charge_policy` is never reassigned after `__init__`, so the cache is sound.

### M3 (Minor, comment)

`tests/unit/test_watch.py:409`: "# a third ping, not the cloud" contrasts with the deleted behaviour. Use "# the radio keeps the car".

## Confirmed correct

- **Edge read anywhere** (`Watch.py:243`). The mutation that makes it home-only is caught.
- **Courtesy rule:** awake (not charging), and `now >= max(fix + return, max(fix, lastRead) + window)`, since the deferral runs first. Home has a return time of 0. It is an EVENT ask and not exempt, so the courtesy wait holds at home.
- **Deferral:** status checks, reads and scans are all silent (mutation caught). The 3 h test checks for zero requests of any kind.
- **Never wakes:** status checks are the free online check, and reads pass wake=False.
- **Deletions are complete:** locate, PARKED/DRIVING/DRIVES, `shiftState`, the per-stretch pop, `_scanSecs`, `_fetch`, the TWICE→cloud switch and the lost-car cloud gate. No remnant was found in lib, docs or tests.
- **Hold check:** the reconciler skips its check only for cloudOnly cars (mutation caught). A BLE install checks at 1860/2760 only while the command is held, with none before or after. There is no doubling.
- **Charging split:** the cadence follows the provider's price (Owner at 300 s, as the user accepted). A paid routine read needs readsBattery, and this covers the TWC-named path too. HOME_CHARGING is excluded from the courtesy rule (mutation caught). readsBattery is cached at init: one set union and an attachment lookup per call.
- **Parity:** unchanged.

## Size (lib +9, Watch.py −3): cuts

| | Change | Saves |
|---|---|---|
| S1 | `Policy.py:142-146, 496-500`. Paid routine reads only ever go to TeslaAPI-attached cars, so the per-module regex and the attachment test buy nothing. Use `self._battery = "minBatteryLevelAtHome" in repr(self.charge_policy)` with no `import re`, and `def readsBattery(self): return self._battery or self.limitOverride`. Watch then calls `policy.readsBattery()`. | ~6 lines (Policy +12 → +6) |
| S2 | `Watch.py:327-332`. The `read()` closure and its comment become a lambda passed to `_submit` (`... is not None`). | ~2–3 lines |
| S3 | With I1 fixed: the `_unheard` once-only read block (`Watch.py:143-152`) folds into the courtesy rule. | ~5 lines (offsets I1) |
| S4 | `Watch.py:259-260` folds into the `late` expression. | 1 line |

Net with S1–S4 and I1: lib about +1 to +3 instead of +9, and Watch.py about −8.
