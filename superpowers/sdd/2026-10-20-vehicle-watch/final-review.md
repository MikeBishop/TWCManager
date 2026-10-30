# Final whole-branch review: vehicle watch (Phase 6), 52a2652c..fea5cb7c

Reviewer: Fable (read-only). Suite at fea5cb7c: 2337 passed, 1 xfailed (venv python, tests minus API/integration). lib 26413 -> 26930 (+517; Watch.py 374, WatchBudget.py 69). Dead-code scan: every named deletion is gone (`updateChargeAtHome` in TeslaAPI/HomeAssistant, `update_charge`, `is_far_from_home`, `lastChargeCheck`, `chargeUpdateInterval`, HA `battery_level`); no orphaned imports introduced (the unused `math`/`Enum` in TWCManager.py and `hashes` in TeslaBLE.py predate the branch). Lock order holds everywhere I traced (tick -> Watch._lock leaf only; BLE worker `_bleLock` -> settingsLock in `_noteScan`; budget lock under settingsLock in save). No I/O on the tick: `pass_`/`status`/`canScan` only build closures and submit. Python 3.8: the one walrus is pre-existing.

## Verdict: **not ready** (one Critical; its fix is one token plus one test flip, so this is close)

## Critical

### C1. A car that leaves while believed asleep is never seen to leave — Watch.py:125
`_source`: `scan = again and asleep(v) is False`. The second-miss escalation to a range scan is gated on the registry saying the car is awake, but once the car has gone nothing can refresh that reading: the only observer of an unfed, un-named car is this ping. A present asleep car answers VCSEC (spec evidence: ~2 s, keyless), so a second ping miss is never explained by sleep — it is RF or absence, exactly the two-miss case the spec built the scan for.

Failure scenario (the ordinary departure of a mobile-connector car): the car finishes charging overnight and sleeps; pings say asleep every 15 min. At 07:00 the owner unplugs (car wakes) and drives off at 07:02. Pings at 07:10, 07:25, 07:40 ... miss; no scan, no `absent` mark, `bleReach` stays True, `decide` stays HOME all day. Consequences: `numCarsAtHome`/`minBatteryLevelAtHome` count it; the policy's departure limit restore never runs; if its last read was "Stopped" (owner-paused), `wantsToCharge` is True and the distributor offers it power -> start command -> BLE fails -> the cloud start is the one command allowed to wake, so a Fleet wake ($0.02) + start go to a car that is 30 km away. When it returns at 18:00 the ping answers, but `was[1] == HOME` so no arrival read either: the battery level the user's low-battery policy needs stays stale until the next sleep/wake cycle. The same gate strands a car that left while a feed covered it (stale `bleReach` True, feed later drops): pinged forever at the asleep cadence, never lost, the free cloud status never consulted, and each out-of-range ping holds the radio for up to `commandTimeout` (15 s). `test_a_miss_while_asleep_records_nothing` pins this behaviour; it is spec-derived ("two consecutive misses while the car was last known awake"), but the spec's premise "it cannot leave asleep" is about the car, not about our stale belief. The ledger already made the same call for lost cars (ruling: "a lost car with no TeslaAPI status source must not stop on a stale 'asleep' — nothing can refresh it").

Smallest fix: `scan = again` (Watch.py:125). Cost: after two misses of a truly present asleep car with RF trouble, one 8 s scan per 30 min; a scan miss then marks `absent` -> PRESUMED (still counted home by `homeCars`), and the back-off/cloud path brings it back. Flip the test to expect the scan on the second miss (keep "one miss records nothing"). Docs: Settings.md "A car Bluetooth has lost (away, with two misses)" still reads true.

## Important

### I1. The spec's "OPEN door ⇒ one free BLE charge read" is not implemented, but the docs and CHANGELOG say it is — Watch.py (no `chargePortOpen` consumer), CHANGELOG.md +167, docs/modules/Vehicle_TeslaBLE.md:71
`chargePortOpen` is written by `_noteSleep` and read only by Presence (CLOSED = unplug). Nothing turns an OPEN edge into a read (plan line 430 lists the event reads and omits it; no ruling in the ledger). Scenario: car arrives awake, gets its arrival read (Disconnected), owner plugs into the mobile connector two minutes later and the car starts charging on its own. No transition follows (a charging car never sleeps), so without a consumption meter it is never read as Charging and never joins the fair share for the whole session. Fix (~3 lines): add `v.value("chargePortOpen")` to the `seen` memo in `_visit` and on a not-True -> True edge while HOME call `_ask(vin, EVENT, True)` (exempt, as a plug-in is); the read is BLE-local for any car with a BLE claim, cloud against the event class otherwise. Or strike the sentence from both docs and the changelog.

### I2. In a no-scan install a HOME car whose pings miss is never handed to the cloud and never read again — Watch.py:124-133, test `test_where_no_scan_can_run_two_misses_at_home_lose_nothing`
With `canScan()` False (Docker without bluez, rfkill, no bluetoothd) the ping closure only writes `bleReach False` when `where != HOME`. At home: miss, miss, miss ... forever; `lost()` stays False so the free cloud status (`onlineState`) is never used and no read is ever made (`_read` runs only on transitions, which the stale state never produces). C1's fix does not help here because no scan can run. Spec: "the cloud status check is for cars BLE cannot reach (no adapter, Docker without bluetoothctl, ...)". Smallest fix: in `_source`, take the cloud branch when `lost(v, where) or (again and not scans(ble))` and the car has a TeslaAPI attachment; and on that second miss `_ask(vin, EVENT, False)` once so a location/charge read (courtesy-bounded) can move the car away. Else document in Vehicle_TeslaBLE.md that without a range scan a departure from a non-TWC charger is not detected.

### I3. The EMS "up" trigger can keep an awake car awake indefinitely — Watch.py:177-185 (anti-goal: "any infotainment read ... more often than the car's own sleep timeout")
A cycling load above the threshold (an HVAC compressor at 1.5-3 kW, an oven or dryer element) produces a held "up" step every cycle; each reads every awake, not-charging HOME/PRESUMED car, debounced per car per direction at 300 s. A read resets the car's idle timer, so with a 10-minute cycle the car never reaches its sleep timeout while the appliance runs. Spec set the 5-minute debounce, so this needs a ruling rather than a silent change. Smallest fix (1 line): for "up", debounce the car by `sleepCourtesySecs` unless the previous triggered read found it Charging: `calm = now >= self._triggered.get(key, NEVER) + (300 if step == "down" else self._settings["sleepCourtesySecs"])`. A car that starts charging after a dryer step is then caught by the next step up to 20 min later, or by its wake transition; the "within about a minute" goal still holds for the first step.

### I4. A TWC-named Fleet-only car charging is read every 300 s through the cloud, not the 900 s cloud pacing — Watch.py:286-287, docs/Settings.md ("A TWC-named car is read every chargingReadSecs ... over BLE or the cloud")
`cloud = not local and not named` makes `secs = chargingReadSecs` for named cars whatever the provider. Gen3-named cars (the majority) with no BLE pay $0.002 every 5 min while current flows: a 6 h charge is 72 reads/day against a 50 reads/day refill, so the routine floor is hit after ~25 reads and the level then updates once per ~29 min as tokens trickle back, and every such ask also spends a token when the 300 s deferral answers for free (parked, accepted). The spec's "HOME, charging" row says cloud routine reads are 15 min; the plan's "chargingReadSecs for a TWC-named car" was written for BLE. Fix: `cloud = not local` (0 lines) and the one doc sentence. If the plan's wording is kept on purpose, say so in Settings.md's budget paragraph (it is the first thing a Gen3 + Fleet user will hit).

## Minor

### M1. A failed event read is dropped, not retried — Watch.py:291-293, 341-348
`_take` removes the ask before `_fetch`; a BLE read that fails (car just out of range) or a cloud read that errors settles as MISS with `lastRead = now`, so an arrival/wake/plug-in read is lost until the next transition. Fix (2 lines): in `done`, when `kind == "read"` and the result is MISS, `_ask(vin, cls, exempt)` again; the courtesy window and the deferral bound the retry.

### M2. Budget spend is never saved — WatchBudget.spend, TWCMaster.saveSettings
`spend` does not queue a settings save, so a restart reloads the last saved `(tokens, at)` and regains whatever was spent since (bounded by one day's capacity, $0.10 at the default). Spec: "a restart must not refill the month"; at most a day is refilled. Fix: queue `saveSettings` when `spend` succeeds for a price > 0 (1 line in `_fetch`), or note the bound in Settings.md.

### M3. Anonymous cars are visited every tick — Watch.py:191-193, 198-238
`_visit` runs `decide`/`situation`/`notWatched` for each anonymous car each second and writes `_seen[None]` and `_last[(None, "status")]` on every cadence. Harmless, but wasted work and a shared `None` key for all of them. Fix: `if v.isAnonymous: continue` in `pass_` (+1); `status()` keeps its "anonymous" row.

### M4. `bluetoothctl devices` now follows almost every scan — TeslaBLE.py:1110-1119
`heard = ... if found != set(names)` is true whenever any registry car is out of range (nearly always in a multi-car home), so `_bluezAddresses` runs after each scan where before it ran only when the asked car was missing. One more 5 s-bounded subprocess under `_bleLock` per scan. Fix: gate on `heard and (asked - found)`; sightings by address of unasked cars are then lost, which is acceptable (a name hit still records them), or accept as is.

### M5. `status()` shows the wrong next-scan time for a lost car with a cloud — Watch.py:368
`self._scanSecs(v, False, now)` ignores the TeslaAPI attachment that `_visit` passes, so a lost cloud car shows the back-off (1800 s) where `_visit` will scan at `scanAwaySecs`; and a cloud-lost car the cloud says asleep shows a `nextAt` though nothing is due (watchLine's comment expects None). Fix: pass `v.attachment("TeslaAPI") is not None` and return `nextAt=None` when `scan and api and seen[0] != AWAY_AWAKE`.

### M6. Duplicate branch — HTTPControl.py:16-19
`if not s["watched"]` and `if s["via"] is None` return the same string. Merge (−2).

### M7. Watch state is never pruned — Watch.py:112
`_seen`, `_last`, `_want`, `_triggered` keep entries for VINs `expireVehicles` forgets. Bounded by VINs ever seen; fine for a home. If wanted, drop keys not in the registry at the end of `pass_` (+2).

### M8. Docs wording — docs/Settings.md cadence table, "Away, awake" row
"a location read while it is driving" — the code reads once per awake episode whatever the gear (to learn it is parked), then again at each return time only while driving. Say "one location read per awake stretch; repeated at the return time while it is driving".

### M9. Note only (settled by the Task 1 review): `checkPlug`/`pick` now ping every candidate car, claimed or not — Presence.py:225, 430
Each absent candidate costs up to `commandTimeout` (15 s) of radio per Gen2 plug edge; a three-car home with two cars away spends 30 s on the BLE worker before the attribution read. Acceptable per the ruling; mentioned because it compounds with C1's stale-`bleReach` pings on the same worker.

## Checked and found sound (so the next reviewer need not)
- Every path to a paid Fleet request: `_fetch` (budget first, EVENT/ROUTINE), `_read` (asleep never, UNKNOWN-on-BLE never, read-only cars never routinely), `locate` (Owner free; Fleet only without a scan; return-time gated; one per awake stretch, repeated only while driving), `readNow`/power start (HOME cars only, each dedup'd by the 300 s deferral), cloud status (`onlineState`, free, 120 s cache under every cadence). No read passes `allowWake`. Restart seeds the memo: no paid read on boot.
- Feed flapping: `notWatched` is evaluated when a check is due, `_seen` is refreshed while covered (no spurious arrival on a drop), the ask is popped while covered.
- Concurrency: `_inflight` guards one job per (vin, kind); the queue's coalescing can only replace a TeslaBLE "radio" job, whose `done` is None; a replaced/dropped Job settles the car via `report`; `done` runs on the worker outside locks; `loadSample` state is touched only on the background thread; HTTP `status()` takes the leaf lock only.
- Shared radio scan: one job for every asked VIN, hits recorded for all registry cars, misses only for asked ones; `_noteScan` under `_bleLock` -> settingsLock is the right order.
- Docker: nsenter is now argv-split and only wraps tesla-control; `setsid` everywhere so the timeout kills the group; compose adds `CAP_SYS_PTRACE`; the readiness check runs on the worker and re-checks every 10 min or after a failed scan; `canScan()` on the tick is lock-only.
- Multi-car: `updateChargeAtHome` asks every HOME car (named included), each a separate (vin, "read") job; the load step reads candidates in one pass (ruling G).
- HA-only cars: status via `refresh_from_home_assistant` every 300 s (UNKNOWN cadence) replaces the per-policy-pass refresh; `minBatteryLevelAtHome` reads the registry; lost HA-only cars follow the no-cloud back-off (ruling).
- Gen3 named cars: `standIn` sees Gen3TWC `actualCurrent`, so the flowing read applies (subject to I4).
- Docs/CHANGELOG otherwise match the code: cadences, budget semantics, restart rule, lost-car rules, `cloudUpdateInterval` note, FT price, compose capability.

## Size cuts (estimates; lib +517 this phase)
1. HTTPControl `watchLine` duplicate branch: −2.
2. `TeslaAPI.minBatteryLevelAtHome` and `HomeAssistant.minBatteryLevelAtHome` are now the same three lines over `homeCars`: one `Presence.minBatteryAtHome(master, attachment)` and two one-line properties: −3.
3. `Watch.status()` recomputes the lost/scan "via" decision that `_visit` makes at 246-253: a `_listen(v, where, ble, api) -> "scan" | "ble" | None` used by both: −3 to −4 (and fixes M5).
4. TWCMaster: the two identical "plug session update failed" warnings (now 4 lines each with `exc_info`): an `_endPlugSession(twcid)` wrapper around `endPlugSession` with the one warning: −4.
5. `Watch._fetch`'s `read` closure is the only reason `_fetch` is a separate method from `_submit`'s call sites; folding the budget check into `_read`/the locate branch and passing a `read` method saves little (−1 to −2) at a readability cost; skip unless the line budget forces it.
Total realistic: about −12. The feature additions after Task 6 (distance return time, Owner location read, back-off, Docker readiness) explain the overrun; I found no duplicated logic larger than the items above.
