# Task 2 report: settings lock

Status: DONE. Commit: see `git log` on branch vehicle-model/phase1 in wt-vm (one commit on top of ef9288a). Tests: 820 passed (815 + 5 new).

Changes
- TWCMaster: `settingsLock = RLock()` created before `self.settings`. `setSetting` and all listed setters (chargeNow*, homeLat/Lon, hourResume, kWhDelivered, nonScheduledAmpsMax, sendServerTime, scheduledAmps*, saveNormal/removeNormalChargeLimit, snapHistoryData) take it. `getSetting` unlocked.
- saveSettings: token merge + `json.dumps` under the lock (TypeError on dumps handled like before: log, lastSaveFailed=1, return); temp write/fsync/backup/replace outside it.
- loadSettings: file and backup parsed into a local with no lock; assignment, default merge, missing-file defaults, and the trailing VehicleGroups/sunrise/sunset fill-ins done under the lock; module fan-out outside.
- HTTPControl (all listed write sites), MQTTControl nonScheduledAction, update_sunrise_sunset, TeslaBLE.scanForVehicles key writes: wrapped. In scanForVehicles key generation stays outside the lock, iteration over a list() snapshot, queue_background_task outside.
- tests/unit/teslatokens.py FakeMaster gained `settingsLock` (10 tests used it via HTTPControl).
- CHANGELOG entry added under Architecture.

Concerns
- Commit trailer is Opus 5.5 per global-constraints.md line 9; the harness reminder said Sonnet 5.5. Parent may amend.
- HTTPControl deleteGroup and consumption-offset delete: `del` became `.pop(key, None)` under the lock, membership check left outside (lock not held across send_response). A concurrent double delete is now silent instead of KeyError.
- Left unlocked deliberately: `addkWhDelivered` (called from the serial loop, TWCManager.py:1711), serial-thread writers per ruling, and `carapi.migrateSavedTokens(self.settings, ...)` / `Vehicle.updateSettings` in loadSettings step 2 (startup fan-out, outside lock per ruling).
- Schedule save in HTTPControl holds the lock across ~80 lines of dict edits and `getFieldValue` (pure, no I/O); send_response/queue_background_task are outside.
- Other TeslaBLE readers of settings["Vehicles"] (iteration at :271, :628, :695) remain unlocked reads per ruling 3.
