# Task 6b review: 590db9aa..fd210aa8

Reviewed: the brief, the report including the appended ruling round, the diff, and the Task 6/6b rulings in progress.md. I read Watch.py at fd210aa8 and compared it with 590db9aa. I also read the code it relies on: Presence.decide/_fix/_within/asleep/lastLife, TeslaBLE.ping and its scan path, Reconciler.submitJob, VehicleCommandQueue.put and WatchBudget.spend. I did not re-run the suite because this shell has no pytest. Watch.py is black-clean.

## Verdicts

- **Spec compliance: PASS.** One minor gap: with no home set, a fix does not move the time (F2).
- **Quality: APPROVE with minor changes.** There is one test gap worth closing (F1). The rest are nits and notes.

## Focus checks

1. **Return time.** `_backAt` = the fix time + the equirectangular km ÷ returnKph × 3600, with a floor of 300 s. The units are right. Equirectangular at 111.2 km/deg with cos(home lat) is fine at these scales. The home comes from `master.getHomeLatLon()`, with the sentinel 10000 checked. The gate sits at the top of `_visit`, after the ask and memo bookkeeping and before every submit: status, read, scan, back-off ping and locate are all behind it. `v.latest` is the newest reading across sources, so a fix from any source moves the time. The 3-hour test proves this: at 10800 it would fire on the old fix but asserts 0. With no fix, the time is the run's start. With no home, the time is the run's start + 300, even when a fix exists (F2). `is_far_from_home` is kept for TeslaAPI.py:1888, which is correct.
2. **Owner read.** It runs when the first non-local READ_CHARGE candidate's price is 0 (Owner), or when no scan can run. Fleet (0.002) and HA (None) keep the no-scan rule. It runs once per awake stretch: the PARKED memo is popped on sleep. It never runs asleep, because it requires AWAY_AWAKE, and it is behind the gate. It is class EVENT, and `spend(0, EVENT)` passes without drawing. The Fleet no-read-while-scannable test goes well past the gate (12 passes against 1668 s) with `scans.count > 1`, so it is not vacuous.
3. **No-scan lost rule.** The ping closure records `bleReach` False (unseen, as a scan miss is recorded) only when all of these hold: the previous status answer was MISS, `asleep(v) is False`, the car is away, the ping went unanswered, and `canScan()` is False. So one miss records nothing, asleep or unknown-sleep misses don't count, and HOME is excluded. Once lost, `_source` skips BLE, so the status check goes to TeslaAPI or HA if present. Otherwise the shared lost block sends a `ping(scan=False)` of kind "scan" on `_scanSecs`, the same back-off as the no-cloud scan. Its key (vin, "scan") does not collide with TeslaBLE's own scan job, which is keyed "radio". An answered back-off ping records `bleReach` True, which marks contact, so the car is HOME again.
4. **Regressions from the trim.** None found.
   - HOME rows: the gate, lost block and locate need an away car, and the status condition is the same (`at` now defaults to NEVER rather than None).
   - Charging reads: `_read` is unchanged apart from the temporaries, and the worker and provider choice is the same.
   - Courtesy: unchanged.
   - TWC-named reads: a named car is always HOME by `decide`, because twcVinAt is cleared by a newer driveStart or outside mark, so the gate never applies to it.
   - readNow on an away car is now deferred to the return time. That follows the rule, and readNow has no callers yet (F7).
   - Anonymous cars now enter `_visit`. `decide` returns HOME for them, `notWatched` returns "anonymous", and only a status settle results, which is harmless.
   - Dropping `claimed` is safe: `queue.put` catches key errors and returns False, a dropped entry reaches `done` through `_lose`, and the double settle is harmless.
   - Folding `_answer` into `done` is equivalent.
5. **Changed tests.** All the changes are legitimate consequences of the new rules, and none weakens an assertion except as noted:
   - `awayLong` gives old fixes so the gate is open.
   - The home is 0.5° away, so the time is 1668 s rather than 12 passes at 1°.
   - The extra pass is needed because a gated car of unknown state needs one status answer before it is AWAY_AWAKE (ruling accepted).
   - The longer asleep window is needed because the read's own fix moves the gate.
   - The restart test now covers the floor.
   - The one loosening is the location-read tests, which no longer pin the boundary. The new BLE boundary tests cover it.
6. **Size.** Watch.py is 318 (base 311), and lib is +7. The ≤270 target was re-baselined by ruling. Remaining cuts are listed below. Comment rule: Watch.py has no history and no IDs, and its comments say why. One test comment is phrased as a question (F6).

## Findings (ranked)

1. **[Important, test gap]** Nothing tests that a HOME car on a no-scan install is not lost after two awake misses. Removing `where != HOME` from the ping closure (Watch.py:110) would probably survive the suite, and then a home car would get an "absent" mark and drop to PRESUMED. Add a test (about 4 lines): home, awake, `canScan` False, two missed pings → `bleReach` None and presence HOME. Two smaller gaps:
   - nothing tests that `status()["nextAt"]` respects the gate;
   - nothing tests that a lost car with HA as its only cloud is not back-off pinged.
2. **[Minor, spec]** With no home set, `_backAt` ignores the fix and uses the run's start (line 243). After start + 300 the gate is open for good, so a new fix no longer moves the time. Spec: "a new fix (any source) moves it". Fix at no line cost: take `fixAt` from the fix whenever lat and lon exist, and make only `km` depend on the home.
3. **[Minor, duplication]** `_backAt` repeats Presence `_fix`'s lookup of `latest("lat"/"lon")` and `max(at)`, and adds 111.2 km/deg beside Presence's `_FT_PER_DEGREE`. The brief asked for reuse. Use `_fix(master, v)[1]` for the time, or share one degree-length constant.
4. **[Minor]** For a lost no-cloud car known asleep, `status()` reports the back-off `nextAt`, but `_visit` never scans or pings that car while it is AWAY_ASLEEP. The brief says status should show the cadence actually in use.
5. **[Nit]** DEFAULTS is now a `dict(...)` plus three `.update(...)` calls, which a reader has to merge in their head. That is line golf rather than simplification. It is acceptable, but a plain literal would be the honest form if lines allow.
6. **[Nit]** The test comment "1668 s from the fix, then awake?" (test_watch.py ~294) is a question. Suggested wording: "the gate opens at 1668 s; the first status check says awake".
7. **[Note]** `readNow` on an away car now waits for the return time. This is spec-consistent, but the Task 7 and Task 9 callers should know.
8. **[Note]** A non-live source that re-reports a fix more often than every 300 s keeps an away car gated indefinitely. This is consistent with the rule, since the fix stream is itself the observation.
9. **[Note]** On a no-scan install, `ping(scan=True)` returns a bool, so a ping tool fault on an away car counts as a miss and can mark the car lost. The back-off ping recovers it.
10. **[Nit]** The equirectangular distance doesn't wrap at ±180° longitude, which affects only homes near the date line.

## Remaining cuts (Watch.py)

- `Watch.settings()` has only a test caller. Drop it unless Task 9 needs it (−3).
- `_backAt`: reuse `_fix` (−1, F3).
- `_visit` decides "has a cloud" twice: `api` at line 185 and `self._source(v, where) is None` at line 195. One local saves a line and a second `_source` call.
- `_ble(self.master)` is looked up in `_scans`, `_source`, `_visit` and `status`. Hoisting it per visit saves 1–2 lines.
- `status()`: `scan`/`via`/`why` can derive from a single `_source` result plus `lost`. Small savings.
