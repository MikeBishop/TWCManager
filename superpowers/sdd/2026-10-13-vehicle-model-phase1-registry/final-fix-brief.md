# Final-review fix wave (vehicle-model Phase 1)

Read `final-review.md` in this directory in full first: each finding below has its file:line, failure scenario and suggested fix there. The spec (.superpowers/specs/2026-10-13-vehicle-model-design.md) is binding where this brief is silent.

Fix each, test first (show the test failing before the fix), one commit per finding or per small group:

- C1 (Critical, cost): a healthy report-on-change source (TeslaMate) must vouch for a field it has reported even when another source (Fleet cloud read) later observed a different value. Required regression test: the reviewer's probe scenario (feed outage -> one Fleet read; feed healthy again -> N further reads past maxAge make ZERO more paid calls while the feed is live). Keep the freshness rule age = now - max(changedAt, liveAt) and FEED_LAG after our own writes intact (existing tests must still pass).
- I1: Forget for a user-asserted (Add-by-VIN) vehicle that no provider has attached to. Scope it narrowly: a POST action on the vehicle page / vehicles list, available only for such vehicles; removes the registry entry and the settings["Vehicles"] record it created (and the BLE key material only if the record was created by Add-by-VIN and never paired). Full Forget is Phase 6; do not build it.
- I2: all-vehicle BLE loops (TeslaBLE.py ~323/713/783) skip VINs whose TeslaBLE claim was dropped or refused (Key refused / pairing failed with no key). Unproven claims (seeded on the upgrade boot) must still be included — existing BLE-only users must keep working. Test both.
- I3: FleetTelemetryMQTT.vinFor returns None unless isWellFormedVIN.
- I4: VehicleRegistry.getOrCreate rejects a non-well-formed VIN (anon:<twc> ids stay valid through their own path). Decide raise vs None by what callers handle; test.
- M1: extend the settingsLock comment (TWCMaster.py ~113) with "including on the serial thread: never I/O under it".
- M2: guard queue_background_task and getBackgroundTask list access with backgroundTasksLock (or the existing lock if one exists).
- M3: _bluezAddresses returns None (unknown) on nonzero exit.
- M4: HomeAssistant.setChargeRate stamps availableCurrent as TeslaAPI/TeslaBLE do.
- M5: process_home_location unset uses pop(..., None).
- M6: deleteSlaveTWC ends the point's plug session.
- M7: _setBleStatus must not create a settings["Vehicles"] record when pairing could not start (key preparation failed).
- M9: isWellFormedVIN rejects the all-zero placeholder 00000000000000000.

Not in scope: I5, M8, M10 (ruled).

## Rules
- Worktree: /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-vm, branch vehicle-model/phase1 (HEAD 2d872e4). Commit there. Never push. Never git stash.
- EVERY pytest run, no exceptions (an uncapped run crashed the host):
  timeout 300 systemd-run --user --scope -q -p MemoryMax=2G <scratchpad>/venv/bin/python -m pytest <paths> -q --timeout=60 -p no:cacheprovider
  Full suite = `tests --ignore=tests/API --ignore=tests/integration` (those need a live server). Baseline at 2d872e4: 1132 passed with only tests/API ignored; integration errors are environmental.
- black only the lib files you touch. No log line may contain a token. Match surrounding code style and comment density.
- No unbounded loops; any test mocks finite.

## Report
Write final-fix-report.md in this directory: per finding, commit SHA, change, test + fail-before evidence; full-suite count. Return only status, commits, one-line test summary, concerns.
