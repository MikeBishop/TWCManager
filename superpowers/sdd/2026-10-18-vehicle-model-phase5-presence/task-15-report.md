# Task 15 report

Commits (on vehicle-model/phase5 base 6d6caaef, in wt-vm5):
- 90d0fbb5 Count a successful BLE range scan as seeing the car
- c73175d5 Keep the last BLE range scan across a restart
- (third) Do not read a Gen2's attributed plug as a sign of life

## 1. Scan hit is a sighting
bleReach observed with seen=inRange. Test: a miss leaves lastSeen unchanged; a hit advances it with source TeslaBLE.

## 2. Last scan persisted
`_noteScan(vin, inRange)` (replaces both `_rangeScan` assignments) stores `{"inRange", "at"}` at settings["Vehicles"][key]["ble"]["scan"] under settingsLock, key from vehicleRecordKey, and queues saveSettings (as _setBleStatus does). Written for every scan that runs, including a failed one (inRange None). rangeStatus fills `_rangeScan` lazily from settings on first miss (requestRangeScan's debounce reads through rangeStatus). `_setBleStatus` now copies the old ble dict (`{**old, ...}`) so pairing does not drop the scan.
Never-paired car: persisted if a settings["Vehicles"] record exists (creates the `ble` dict with setdefault; storedBleStatus still reads "unpaired"); with no record at all the scan stays in memory only (no record is created just for a scan).
Tests: restart over same settings gives the same inRange/at; pairing keeps scan; no-record car is memory only.

## 3. Root cause
The brief's suspicion is refuted. Timeline: the BLE setAmps run started 17:09:22 ("no wake ... waiting for telemetry" is logged immediately before the send); 17:09:28 was its first failure and 17:09:37 the quick retry. TeslaMate subscribed at 17:09:35, 13 s later. TeslaMate's last published state was offline (16:53:28, teslamate.log), which asleep() excludes from life anyway.
Real cause: Gen2's first heartbeat after the restart (17:09:15, SHB 03) begins a plug session; Presence.attribute then observed pluggedIn True from Gen2TWC, stamped now. noteObservation marked plugIn, newer than the 17:09:11 asleep reading, and asleep() counts a plugIn mark as life. Reproduced in a harness (asleep True, then beginPlugSession + attribute, asleep False). The fix in asleep(): a plugIn mark whose newest cause is the Gen2TWC reading does not count; a plug the car itself reports later does. The stored reading and the plugIn mark (home evidence) are unchanged.
Test: test_a_gen2_plug_attributed_after_a_restart_is_not_a_sign_of_life (fails without the fix).

## Latent bug found (not fixed)
A retained TeslaMate state "online" or "suspended" (seen=False, stamped now) does end known-asleep today, and so can a retained plug reading (plugIn mark when the car is inside). It did not cause the live incident (the retained state was offline). Fix needs an Observation.seen flag (~5 lines: Fields, Vehicle._store, asleep) plus excluding retained plug marks from life; over the lib budget, so left for a ruling.

## Verification
tests/unit + tests/EMS: 2160 passed (2156 + 4 new). Parity counts unchanged, nothing moved.
Lib lines: 26307 -> 26323 (+16: scan persistence +13, asleep fix +3), over the +10 target.

## Addendum: retained readings (controller ruling)
Commit "A retained telemetry reading is not a sign of life". Observation gains `seen` (default True); Vehicle._store/observe carry it. noteObservation sets one new mark, `lifeAt`, on a seen plug-in (not a Gen2's attributed plug), a seen unplug, or a seen driving change; asleep() counts only `lifeAt` and seen states. This replaces the earlier Gen2-specific clause in asleep(). The plugIn/unplug/driveStart/driveEnd marks (home evidence) are unchanged.
Tests: retained state online, state suspended, and retained pluggedIn True each leave the car asleep with no BLE run, and the same reading live ends it. Full run: 2163 passed. Parity unchanged.
Lib: 26307 -> 26330 (+23 total; this commit +7 over the Gen2 fix).
Note: a seen driving-state change now counts as life even when the old driveStart/driveEnd conditions (inside radius) did not hold; a driving car is awake.

## Fix round 1
Commit "Only a charger that saw the plug counts it as life; tidy the scan record".
I1: a charger plug-in is life only if `obs.seen and (source not a charger or was is False)`; restart plugs (was None) are not life for Gen2 or Gen3; the Gen2 attribution test still passes. The old Gen3-plug param in test_a_sign_of_life_ends_known_asleep became two tests (first-reading not life; replug after observed unplug is life for Gen2 and Gen3).
M1 rangeStatus reads stored scan without caching; M2 saveSettings queued after the lock; M3 non-dict ble guarded; M4 anon merge passes seen; M5 wrong-guess pluggedIn False is seen=False; M6 comments fixed.
Tests: 2165 passed. Lib 26307 -> 26336 (+29 vs 6d6caaef).
