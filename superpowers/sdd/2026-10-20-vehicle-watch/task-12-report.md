# Task 12 report: one presence rule for cars only the Tesla API can see

Status: DONE. Commit ee65ba2b on vehicle-model/phase6 (worktree wt-vm6), parent b613a784. Not pushed.

## Numbers
- Full suite: 2381 passed, 1 xfailed (BASE 2377 + 1 xfailed; 8 obsolete tests removed, 12 added).
- Parity: `tests/unit/test_command_path_parity.py` is unchanged and passes. No counts moved.
- Watch.py: 407 -> 404 lines.
- lib: 27036 -> 27045 (+9). Watch.py -3, Reconciler.py 0, Policy.py +12 (the new battery predicate).

## Predicates chosen
- **API-only class:** `Watch.cloudOnly(master, v)`. It is true when the car has a TeslaAPI attachment, `_ble(master) is None` (the TeslaBLE provider isn't registered), and `notWatched(...) is None`.
  - Rationale: pings run whenever the module is loaded. The VCSEC body-controller-state check is keyless, and the module unloads itself when the tesla-control binary is missing. So "canScan() False and pings can't run" only happens when the module is not loaded.
  - With BLE loaded but scans blocked, a lost car is pinged on the back-off. That was already the path for a lost car with no API.
- **Battery predicate:** `Policy.readsBattery(vehicle)`.
  - The module names in `modules.<X>.minBatteryLevelAtHome` are found once at `Policy.__init__`, with a regex over `repr(charge_policy)`. That covers match, value, charge_amps and charge_limit in nested lists.
  - It adds `TeslaAPI` while `limitOverride` stands.
  - It is true if the car has an attachment for any of those modules.
  - On the tick it costs one frozenset union and a few dict lookups.
  - Watch reaches it through `master.getModuleByName("Policy")`. If there is no Policy, there are no paid routine reads.

## What changed
- **Watch._visit:**
  - The edge read is now any asleep→awake transition (home or away), and the awake side includes HOME_CHARGING.
  - New courtesy rule: if the car is cloudOnly, in HOME_AWAKE or AWAY_AWAKE, and `now >= max(fixAt, lastRead) + sleepCourtesySecs`, the watch asks one EVENT read (not exempt). The rule runs after the existing away deferral, so the return time is already satisfied. A failed or refused read waits a window through `lastRead`.
  - Deleted: the `locate` kind, the once-per-awake-stretch pop, PARKED/DRIVING, and the driving re-read.
- **_source:** the cloud is asked only when `ble is None`. Two consequences:
  - A lost car in a BLE install gets no cloud status check.
  - The "two misses at home → cloud" switch is gone; the car stays on pings. The existing once-only cloud charge read for an unheard awake car at home is kept.
- **_listen / _scanSecs:** merged into `_listen`, which returns `(how, secs)`. The cloud-awake gating and the "api → scan often" rule are removed, so the back-off depends on last life alone.
- **_read:**
  - The read cadence follows the provider's price: free reads (BLE, Owner) use `chargingReadSecs`, paid reads use `cloudChargingReadSecs`.
  - Routine paid reads require `readsBattery`. This covers the TWC-named path too.
  - `_fetch` had only one caller left, so it is inlined.
- **Reconciler._asleepCheckDue:** the hold check is skipped only when `Watch.cloudOnly(...)`. So in a BLE install, a held Fleet command runs its own online check at the 900/1800 cadence, and only while it is held.
- **Docs:**
  - Settings.md: charge-reads bullet, cadence table, and new subsections "Cars only the Tesla API can see" and "Cars Bluetooth can hear"; TWC-named line.
  - Vehicle_FleetTelemetryMQTT.md: recommended as the cheaper option; API-only works.
  - CHANGELOG: watch entry and sleeping-car entry.
  - Also fixed two sentences that the change made wrong: Vehicle_TeslaBLE.md (hold check) and PolicyCustomization.md (minBatteryLevelAtHome bullet, which described the old checkCharge behaviour).

## Tests (all mutation-checked: each listed mutation fails at least one named test)
- **API-only:**
  - wake at home and wake away, with short asleep cadences so the read lands before the courtesy window could fire (mutation: edge home-only);
  - courtesy reads at 1200/2400/3600 (mutations: no rule; ignore fix);
  - 3-hour fix means no request of any kind for 3 h (mutation: no deferral);
  - awake past its return time, read and found home;
  - departure while awake seen within one window.
- **BLE install:**
  - lost car: zero requests over 100 min (mutation: lost car asks cloud);
  - lost car with a TeslaAPI attachment scans at awayAsleepSecs (mutation: api → often);
  - held Fleet command: no cloud checks before the hold, checks at 1860 and 2760 while held, none after the command is sent (mutation: the old notWatched skip).
- **Charging:**
  - Fleet with no battery policy: no paid reads for 1 h while charging, and HOME_ASLEEP releases it (mutations: battery always; courtesy reads charging);
  - TWC-named Fleet car with no battery policy: plug-in read only;
  - existing Fleet cadence and budget tests now set a battery policy (mutation: battery never);
  - Owner car with unsigned commands reads every chargingReadSecs (mutation: Owner on the cloud cadence);
  - Policy.readsBattery unit test.
- **Removed (paths deleted):** away location read, driving re-read, sleep ends the episode, no location read where a scan can hear, failed location retried, lost car scanned while the cloud says awake, Owner located free, status shows the cloud after the second miss at home.
- **Adjusted:** two retry tests now stop asserting before the next courtesy-window read; "two misses at home" now expects a third ping and still one cloud read.

## Concerns
1. **lib grew +9** (Policy +12 for the battery predicate; Watch only -3). The addendum expected Watch.py to shrink more. The four deleted away-paths were roughly matched by the cloudOnly predicate, the courtesy rule and the paid-read gate. I found no duplication to harvest.
2. **Owner reads move from 900 s to 300 s while charging.** The brief and spec say "Free reads (BLE, Owner) keep chargingReadSecs", but the Owner API previously used cloudChargingReadSecs. I followed the spec, so Owner charging reads are 3x more frequent (still free). Confirm that was intended.
3. **The courtesy rule excludes HOME_CHARGING**, so a Fleet charging car with no battery policy gets no presence reads either. If it is unplugged and driven off while still believed Charging, the watch learns that only on its next wake edge. I chose this because the spec's test wants "no routine charging reads, finish learned from sleep".
4. **The courtesy rule has no restart floor.** After a restart, an API-only car with no fix is read as soon as a status check says it is awake. This matches the old location read's restart behaviour (test_after_a_restart... still passes unchanged), and edges are still seeded. An awake car with a stale fix may get one read soon after a restart.
5. **getScheduledAmpsTimeFlex** reads the last TWC car's battery level, and readsBattery does not count it. The spec named only minBatteryLevelAtHome and the limit override.
6. **The courtesy rule calls cloudOnly**, which re-runs notWatched once per car per pass. It does no I/O; it is the same work `_visit` already does.

## Fix round 1 (amended: ee65ba2b -> ac3e74a1)

### Numbers
- Suite: 2384 passed, 1 xfailed.
- Parity: the test file is unchanged and passes.
- lib: 27047 (+11 vs 27036).
- Watch.py: 404 lines.

### I1: BLE can be loaded but unusable (coordinator's ruling)
- **TeslaBLE:**
  - New `RADIO_DOWN` holds the readiness reasons that sit in the radio itself: no controller, powered off or rfkill, and `SILENT` (bluetoothd not answering, outside Docker).
  - New `radioUp()` calls `canScan()`, so the 10-minute recheck stays scheduled and recovery is noticed, then returns `_scanBlocked not in RADIO_DOWN`.
  - A missing bluetoothctl, or Docker unable to reach bluetoothd, is not "down": pings still run there.
- **Watch:**
  - New `radio(master)` returns the BLE module only while `radioUp()` is true. `cloudOnly`, `_visit` and `status` use it.
  - While the radio is down, every TeslaAPI car is cloudOnly and follows the API rule: cloud status checks, edge reads, courtesy reads and deferral.
  - It reverts automatically when readiness recovers.
  - This is per install, not per car; no per-car "lost → cloud" switching.
  - The reconciler's hold check is skipped for these cars while the radio is down, because the watch's checks serve the hold.
- **Page and log:**
  - The watch line shows via "cloud" while the radio is down and "ble"/"scan" otherwise.
  - The scan-readiness warning now ends "cars watched by the Tesla API" or "cars watched by pings alone". It replaces the inaccurate "falls back to slower checks"; test_teslable_pairing_status is updated to match.
- **Tests:**
  - radio down (no controller): the cloud rule applies, with a courtesy read at 1200, no pings and via cloud. After recovery the car is back on pings with no cloud requests and via ble.
  - bluetoothctl missing: a lost car is pinged on the back-off, with zero requests.
  - Mutations caught: radio-down ignored; any blocker treated as down.

### Other findings
- **I2 (docs):**
  - Vehicle_TeslaBLE.md: the range-scan answer now describes the two cases and the warning's wording; the deleted hand-off is gone.
  - Settings.md: "makes no cloud status checks", and the API-only section now covers a radio that is down.
  - CHANGELOG: updated to match.
- **I3:** new test: a Fleet API-only car away whose reads fail (HTTP 500) is read at 1200, 1500 (retry), 2700 and 3000. Mutating `max(fixAt, lastRead)` to `fixAt` is caught.
- **S1:** `Policy._battery = "minBatteryLevelAtHome" in repr(charge_policy)`, and `readsBattery()` takes no argument. The regex and attachment test are dropped.
- **S2:** the read closure is now a one-line lambda.
- **S3:** not applied. It depended on the reviewer's per-car `_unheard` design, which the ruling replaced. The once-only cloud read for an unheard car at home is a BLE-usable path and has no courtesy-rule equivalent.
- **S4:** tried and reverted. Black splits the folded expression back to three lines, which saves nothing and reads worse.
- **M3:** the comment is now "the radio keeps the car".
- **M1, M2:** accepted, no change.

### Size
TeslaBLE grows by 8 lines for the radio predicate and the log wording. Policy is now +1 instead of +12. Watch.py is 404 (−3 vs base).
