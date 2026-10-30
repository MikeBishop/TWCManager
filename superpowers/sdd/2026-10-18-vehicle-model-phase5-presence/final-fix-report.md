# Phase 5 final review: fix report

Worktree `scratchpad/wt-vm5`, branch `vehicle-model/phase5`, from 207f98c5. Not pushed.

## Commits

| Commit | Subject |
|---|---|
| 06f192b7 | Never attribute a plug to a car its live feed reads unplugged (Important 1) |
| 7a18ff63 | Date a home fix by its GPS time; correct the home and placement docs (Important 2, Minor 8) |
| 37cc9094 | Attribute a VIN-less plug once across a waking car's 00 flicker (Minor 3) |
| 6ab5fc52 | Re-arm the link grace when a known TWC links again (Minor 4) |
| 2f6113b0 | Count paid requests under the vehicle lock (Minor 6) |
| 12031c9a | Find a charging point's cars once per control pass (Minor 7) |
| fc751c59 | Inline the one-line homeForLimits alias (Minor 10, a deletion to offset the delta) |
| 6704fdb0 | Say which threads scan under the BLE lock (Minor 5, comment only) |

## Verification

- `tests/unit tests/EMS`: **2101 passed**, 1 warning. The baseline was 2093; the 8 new tests are listed below. Minor 4 adds a row to an existing test.
- `black --check lib`: clean. The lib diff adds no 3.9+ syntax.
- I ran black on every touched file except `tests/unit/test_telemetry_registry.py`. That file was not black-clean before, and black would have reformatted unrelated lines, so its three renamed lines were edited by hand.
- `tests/unit/test_command_path_parity.py` is not edited, and no parity count or timing moved.
- Lib: 26,198 → **26,217 (+19)**. `git diff --shortstat 207f98c5 -- lib`: 9 files, +63/−44 (the last commit only changes a comment).

## Findings

### Important 1: attribution ignores a live feed that says unplugged (fixed)
- `Presence.telemetrySaysPlugged(master, v)` is now `telemetryPlug(v) -> Optional[bool]`. It returns the live feed's own `pluggedIn` reading, `v.reported("pluggedIn").get(v.syncSource)`, and only while `syncSource` is a telemetry source.
  - It no longer uses `v.value("pluggedIn")`, the newest reading from any source. That value could be the Gen2TWC `False` from an earlier unplug, or our own attribution's `True`.
  - `pick.fits` returns False when `telemetryPlug(v) is False`.
  - `_plugSession`'s veto and `vehicleEndpoints`' guard now use the same helper, so their meaning narrows in the same way: the feed's own word, not the newest reading from any source. No test moved.
  - One edge widens. Take a TeslaMate-synced car named by a VIN-reading Gen2 whose TeslaMate feed still shows a stale `pluggedIn False`, while another TWC is unknown at 00. Before, `v.value` saw the Gen2's newer `True` and withheld the car's endpoint; now `telemetryPlug` sees `False` and grants it. This is benign: the car is grouped under its Gen2's charging point, and attribution can no longer produce this case.
- `pluggedNow` now checks the plug readings before the naming. A charging point naming the car still says plugged, unless a newer unplugged reading from a source other than Gen2TWC came after the naming.
  - Gen2TWC is excluded on purpose. A Gen2 re-plugged before its VIN is read again keeps its old naming, and its earlier `False` must not override it.
- Test: `test_presence.py::test_live_telemetry_unplugged_is_never_attributed_and_outranks_a_naming`. Before the fix it failed: `attribute` returned the VIN. After the fix it passes, and the second half shows a newer TeslaMate `False` beats the naming.

### Important 2: learnHome stale-fix guard and the TWC move
**(a) Stale fix: fixed.**
- `learnHome` now dates the fix as `min(lat.at, gpsAsOf.value)`, using the `gpsAsOf` that the fix's own source reported. With no `gpsAsOf`, it uses the reading's time.
- For this to work, both providers now observe `gpsAsOf` before the position. TeslaAPI moves the `gps_as_of` observe ahead of lat/lon, and `TeslaBLEProvider._get` puts `gpsAsOf` first in its dict.
  - Before this change, the hook on the lon store could not yet see the same read's GPS time.
  - A stale `gpsAsOf` left over from an older read makes a fresh fix look stale. That fails safe: home does not move.
- In `update_vehicle_data`, the `except` now also catches `AttributeError`. `drive.get` on a non-dict raises that, where `drive["latitude"]` used to raise `TypeError`.
- Tests:
  - `test_a_ble_fix_moves_home_only_while_its_gps_time_is_fresh`, through `TeslaBLEProvider.fetch`.
  - `test_a_fleet_fix_with_a_stale_gps_time_never_seeds_home[18000-False / 5-True]`, through `update_vehicle_data` with `requests_mock`.
  - With the lib changes stashed, the BLE test and the stale Fleet case both failed: home moved. Both pass with the fix.

**(b) TWC-named move once home is set: not changed in code; the docs are fixed instead.**
- The review's proposal was to call learnHome before the `outside` mark. I tried it, and it breaks `test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix`, which pins Ruling F2: an outside fix overrides the naming.
  - The two cannot both hold. A Gen2 that reads no VIN keeps a stale `twcVin` while a guest car is plugged in, so moving home on any outside fix of a named car would move home to wherever the old car is.
  - The review's own "Declined to judge" list rules this case by F2.
- The review missed one path. `recordVehicleVIN` calls `learnHome` directly at the moment a TWC reads the VIN, and that does move an already-set home to a fresh outside fix. It is also the one moment the naming is known to be fresh.
- Docs now say exactly that: home moves "when a TWC reads the car's VIN, or over BLE", for a fix under 10 minutes old by the car's GPS time. The edited files are CHANGELOG, `docs/Settings.md` and `docs/PolicyCustomization.md`.
- Pin test: `test_a_fresh_fix_outside_moves_home_when_a_twc_reads_the_cars_vin`. It passes both before and after the change, so it is not TDD evidence.

### Minor 3: anonymous-session flap (fixed, without changing when a session ends)
- My first try ended the anonymous session only after a held 00. It broke tests that pin "00 ends the anonymous session" (`test_limit_wiring` ×2, `test_offer_characterization`, and at first the parity row `test_no_gps_source_plug_unplug_cycle_end_to_end`), so I reverted it.
- What landed:
  - The bare-00 end records `slave.anonEndedAt` and ends the session with `depart=False`. That means no "anon:… departs" log line, no `pluggedIn False` on the anonymous vehicle, and no candidate departure.
  - A session that begins less than `UNPLUG_DEBOUNCE` (60 s) after the last anonymous end does not queue `attributePlug` again. That attribution already ran for this plug.
  - The filtered unplug, `unplugStep`, still departs the only possible car when the 00 holds. That is unchanged, because the anonymous session has already ended by then. `_plugSession` treats an anonymous occupant like none.
- Test: `test_gen2_unplug.py::test_an_unnamed_session_outlasts_a_waking_00_and_departs_no_one`. Before the fix, `attributePlug` was queued twice; after, once.
- Residual risk: a different car plugged in within 60 s of a flicker-ended anonymous session is not attributed. That needs an unplug and re-plug inside a minute.

### Minor 4: link grace not re-armed on re-link (fixed)
- `newSlave`'s re-link branch now sets `heardFrom = 0`, so the next heartbeat re-arms `LINK_GRACE`.
- Side effect: until the slave's next reply, `chargingPoints` and `controlPass` skip that slave and keep its last offer. That is the same as a slave not yet heard from.
- Test: a row added to `test_a_re_link_starts_a_new_plugged_run`. It is a second re-link followed by 2 minutes at 03 and then a 00 with the amps drop. Before the fix it failed with an unplug mark at 2230; after, there is no unplug.

### Minor 5: the ping's range scan outside `_bleLock` (not a defect; no change)
- `scanForVehicleInRange` is decorated `@_serialized` (`TeslaBLE.py:1019`). So the scan, and both `_rangeScan` writes (`:1067`, `:1070`), already run under `_bleLock` whichever thread calls them.
- Two scans cannot overlap.
- Making `_runPing` `@_serialized` would deadlock. `_bleLock` is a plain `threading.Lock`, and both `_tool` and the scan take it.
- The only gap is that another tesla-control run may slip in between the ping's `body-controller-state` and its scan. That is harmless.
- The section comment (`TeslaBLE.py:1004-1008`) said scans run on the background-task thread. It now says the ping's scan runs under the lock too. Comment only.

### Minor 6: unsynchronised `paidRequests` (fixed)
- `TeslaAPI._request` now increments `paidRequests` under `vehicle._lock`, the leaf lock. No I/O happens under it.
- Test: `test_paid_logging.py::test_a_paid_request_is_counted_under_the_vehicle_lock`. It uses a spy lock and a property that records whether the lock was held at the increment. Before the fix it saw `[False]`; after, `[True]`.

### Minor 7: presence computed twice per tick for anonymous points (fixed)
- `ChargingPoint.setTargetPower` now stores `self.carKeys = self._carKeys()`.
- `distributeEVSEPower`'s `offered` reads `p.carKeys` instead of calling the private method from another class.
- `confirmed()` reuses `carKeys` when set. It was a third scan in the same `controlPass`, and still falls back for points built without a target.
- Test: `test_an_anonymous_point_finds_its_cars_once_per_pass`. It counts `candidates` calls in one `controlPass`: 3 before the fix, 1 after.

### Minor 8: two doc inaccuracies (fixed)
- `PolicyCustomization.md`: no Tesla API read is made just to place a car. A "probably home" car with a waiting limit or charge command may be woken and read over the paid Fleet API to deliver it.
- `Vehicle_HomeAssistant.md`: only `battery_level` is kept.
- No tests (docs only).

### Minor 9: the RELEASE/NOT_HERE churn residual (left documented)
- The review did not pin down a cause, so per the brief the sentence in `PolicyCustomization.md` stays.

### Minor 10: size (partly taken)
- The one-line `homeForLimits` alias is inlined at its two lib call sites, saving 4 lines.
- The duplicated single-candidate rule is left as is.

## Concerns
- Lib is +19 net (26,217), not zero. Important 1 accounts for +8, `learnHome` for +3 and Minor 3 for +5. Nothing else obvious was left to delete.
- `pluggedNow`'s new precedence (a newer non-Gen2 unplugged reading beats a naming) runs in a hot path. Parity and the full suite pass, but it should be watched on the box: for example, a Gen3 naming plus a late TeslaMate `pluggedIn False` now reads as unplugged.
- Important 2(b) is resolved by Ruling F2 plus the doc changes, not by code. The user may want to confirm that "home moves when a TWC reads the VIN" is the intended promise.
- Minor 3's 60 s re-attribution suppression is a new heuristic. It has no tuning evidence beyond the waking-flicker pattern in the evidence table.
