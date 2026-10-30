# Task 6 review: 46adfe70..dba72feb (Watch.py 255 -> 294)

**Spec compliance: FAIL**, on two items: the driving ruling is not applied, and a failed location read is counted as PARKED. The scan rule and the never-asleep, event-class, and return-time rules pass.
**Quality: CHANGES REQUESTED.**

test_watch.py passes (31 tests). Mutations: removing the asleep guard, scanning on the first miss, or ignoring PARKED each fail one test. These mutations all still pass: removing the episode reset, removing the scanAway cadence, allowing a locate when a scan is possible, and treating a failed read as answered.

## Findings, ranked

1. **Important: the driving ruling is not applied (Watch.py:227-229).** After any non-PARKED answer, the next read comes `awayAwakeSecs` (300 s) later. The ruling says a DRIVING answer waits for the return time from the new fix (1800 or 3600 s). The fix also shortens the method. Apply the fix rule to every read, and keep `awayAwakeSecs` only as a retry floor after a failure or a budget refusal. Without that floor, a refusal would call `spend` and log on every 1 s pass:
   ```python
   if answer == PARKED or now < at + self._settings["awayAwakeSecs"]:
       return
   lat, lon = v.latest("lat"), v.latest("lon")
   if lat and lon and now < max(lat.at, lon.at) + (3600 if api.is_far_from_home(lat.value, lon.value) else 1800):
       return
   ```
   (`at` is NEVER before the first read, so the floor passes.) After a DRIVING read, the read's own lat/lon set the new fixAt. `lat.at` is dated by `gpsAsOf`, which is the true fix time. Saves about 2 lines. Rewrite the `_locate` comment to state the rule ("…again after a drive, from the new fix"). Add a test for it (see 5).
2. **Important: a failed read counts as answered (Watch.py:249-250).** `Vehicle.read` returns `self.latest(field)` when the provider read fails (Registry/Vehicle.py:303). Once a fix exists, which is the case whenever the return-time gate has run, `got` is the old observation, so it is truthy. A failed read is then recorded as PARKED (or as DRIVING if the stored shiftState is stale), and that ends the episode. The report says a failure re-reads. That is true only when there was no fix at all. Fix: call `self.master.providerOrder.read(v, field, False, providers)` directly. It returns None on failure, which is exactly what `Vehicle.read(force=True)` calls internally. This is 0 net lines. The test "failed read treated as answered" passes today. Add one (see 5).
3. **Important, needs a ruling: an away car on a BLE install is never seen asleep.** `_source` always prefers BLE. For an away car out of range, every ping misses, so the last `state=online` stands and `asleep(v)` stays False (Presence.py:245). The car is then AWAY_AWAKE for as long as it is away, all day at work. Every 150 s the watch runs a ping, which times out at `commandTimeout`=15 s, and then an 8-12 s scan. That is about 18% of the shared adapter for each away car. The spec (§Rings, line 80) handles this: the cloud status check covers "two consecutive scan misses while the car is awake, which is the departure case". The plan's Task 4 source order dropped it. The scan-in-status-job design also stops Ring 1 and Ring 0 from being split. Options for the controller:
   - (a) For a departed car with a TeslaAPI attachment, Ring 1 is cloud `onlineState` at `awayAwakeSecs`, and the scan is its own `"scan"` job kind every `scanAwaySecs` while the car is awake. That costs about 6-8 lines and makes the scan coalesce with TeslaBLE's `(vin, "scan")`.
   - (b) Accept it and document that a BLE-only install cannot learn that an away car is asleep. Even then, skip the ping once the previous one missed and the car is away, and run the scan alone, since a scan hit gives contact and a ping follows. That halves the adapter time.

   Either way, the current Ring 1 cadence of 150 s for an away awake car is twice the spec's 5 min.
4. **Minor: the periodic arrival scan is miss-triggered only, but effectively periodic.** An away car's pings always miss, so after the first miss every 150 s cadence scans. The first scan comes one cadence after departure is noticed (up to 300 s). The brief literally asks for "a scan job every scanAwaySecs". The behaviour is acceptable once 3 is ruled. Name it in Task 10's docs.
5. **Minor: test gaps.** Each of these is about 2-4 lines, reusing the location test's setup:
   - (a) A DRIVING read re-reads at the fix plus 1800 s, not at 300 s. This needs the Fleet stub to report `shift_state:"D"`.
   - (b) An asleep pass resets the episode, and the next wake reads again.
   - (c) With `bleScans` stubbed (scan possible), no location read is paid.
   - (d) A failed cloud read is retried after `awayAwakeSecs`.
   - Optional: `status()['nextAt']` uses 150 s for an away awake car that can be scanned.
6. **Minor: an away awake car with no fix pays a read on the first pass.** The `elif lat and lon` branch is skipped. lat and lon are not persisted, so after every restart each awake car presumed away pays one EVENT read as soon as Ring 1 says online. This is defensible because nothing is known, but it conflicts with the spirit of ruling R2. With the fix in 1 this stays true. The controller should accept it or gate it on the first pass after start (`self._started`).
7. **Minor: a job that never ran settles as MISS** (`done(result)` with a result that is not a string). A dropped status job therefore counts as one of the two consecutive misses. A reconciler drop is rare, so accept it, but note it.
8. **Nit: `_scans()` runs `shutil.which("bluetoothctl")` up to twice per car per 1 s pass, plus on every status() call.** It is cheap but uncached. Optionally cache it per pass, or accept it.
9. **Answered: the episode-reset gap does not matter.** A sleep and a wake between two passes leave no trace in the registry anyway, because a later `online` from the same source overwrites the `asleep`. The watch only learns sleep at Ring 1 cadence, so pass frequency is irrelevant. Keep the pop. Item 5b covers it.
10. **Answered: the HOME departure case is covered and not double-scanned.** The watch pings with `scan=False`, so `_runPing`'s own fallback never runs. The first miss at home records nothing. The second miss while awake runs one scan, which marks `absent`, and `decide` leaves HOME. Ping False vs None: `ping(scan=False)` returns only True or None, so `_answer` scans only on None. A cloud False never carries the scan argument. After a restart `_last` is empty, so the first miss is a first miss. A miss while asleep or UNKNOWN (`asleep` not False) scans nothing. All of this is correct.

## Size (Watch.py 294; the plan allows about 220 including Task 7)

- **`_locate` with finding 1's shape: -2.** Also make the cloud pick one line, `cloud = [p for p in order.candidates(v, READ_CHARGE) if not p.local][:1]`: -1. With the comment tightened, `_locate` drops from 18 to about 14 lines.
- **Fold the scan into the ping: -2.** Use `lambda: _answer(v, ble.ping(v.vin, scan=again and asleep(v) is False))`, where `asleep` is evaluated on the worker. `_runPing` then scans on the miss, and `ping` records `bleReach` (a duplicate of the scan's own write, which is harmless). `_answer` loses its `scan` parameter, the `if`, and one comment line. Black may wrap the lambda, so the net is about -2.
- **Do not fold `_locate` into `_read`.** A Fleet `vehicle_data` charge read does carry the location, but `_read` prefers local providers. On an install with no scan, a loaded TeslaBLE would take the read and fail for an away car. The courtesy, want and lastRead bookkeeping would also tangle with the episode stamp. `_fetch` is already the shared tail, so there is nothing more to fold there.
- **Total from this task: about -5 lines (to ~289).** Reaching 220 needs a trim pass across Tasks 4-5 code (`status()`, the `_visit` lock block, DEFAULTS). That is outside this diff and should be flagged to the controller before Task 7.

## Comments

The comments follow the as-designed rule: none describes past behaviour. `_locate`'s "again while it drives" must change with finding 1. The test comments ("the fix within an hour's drive of home", "under 1800 s since the fix") are fine.
