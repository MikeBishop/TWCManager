# Task 6 report
Status: DONE. Commit: feat: add Fleet-only charge sessions to the charge history.

## Construction order
master.loadSettings() (TWCManager.py:773) runs before master.watch = Watch(master) (:790). So: Watch.__init__ loads master.settings.get("chargeLedger") into its ledger; loadSettings also loads into an existing watch.ledger. Added ChargeLedger.load(data) (swaps state under its lock; fromJSON now uses it) so the live instance is never replaced.

## Changes
- TWCMaster: getChargerLoad(ledgered=True) passes through; sampleHistory uses ledgered=False; saveSettings prunes and writes settings["chargeLedger"] inside the settingsLock block; loadSettings restores into an existing watch.
- HTTPControl /api/getHistory: bucket + ledger.wattsBetween(slot, slot+300, liveWatts); current slot = historyWatts() + ledger over [slot, now) (mean over elapsed time, like its bucket). No watch: unchanged.
- Tests: test_twcmaster (buckets leave out fleet-only; save/load survives, prune at save, same instance), test_charge_ledger (load), test_watch_load_step (Watch made after load restores), test_registry_callers (segments in slots with partial ends; current slot; backfilled session replaces belief). _master helper now sets watch=None.

## TDD
RED: `PYTHONPATH=lib .venv/bin/python -m pytest -q <4 files>` -> 7 failed, 95 passed (all 7 new tests).
GREEN: same -> 102 passed. Full suite: 2642 passed, 1 xfailed.

## Concerns
None blocking. The mean for the current slot divides by elapsed time, not 300s, per the brief.
