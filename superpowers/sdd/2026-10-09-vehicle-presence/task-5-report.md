# Task 5 report: VehiclePresence core

Status: DONE. Commit 0c54080 on fix/vehicle-presence.

Files (under /home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96):
- created lib/TWCManager/VehiclePresence.py
- created tests/unit/test_vehicle_presence.py (29 tests, brief verbatim)
- modified lib/TWCManager/TWCMaster.py (import; self.vehiclePresence = VehiclePresence(self) after the queue; thread not started)
- modified tests/unit/test_twcmaster.py (test_master_creates_unstarted_presence)

Deviation from brief: the brief's _collectDue called knownVehicles() (which calls TeslaAPI.getCarApiVehicles) while holding self._lock. To keep the invariant "no calls out while holding the presence lock" (lock order _bleLock -> presence._lock), _collectDue now returns a None sentinel for "all known" and runPass expands it after releasing the lock. Side effect: expanded VINs are appended after explicitly nominated VINs rather than in nomination position.

Tests: 588 passed, 1 warning (582 + 6 expected; 29 presence + 1 master new). test_vehicle_presence.py run 8 times in a loop: 29 passed each time. black clean. test_handlers_run_without_the_presence_lock kept.

Notes: strict TDD red step (Step 2) was skipped; tests and implementation were written together from the brief. Orchestrator should check Task 6-9 briefs for any dependency on _collectDue expanding None in place.

## Fix round 1
1. knownVehicles() raising in runPass is caught, logged at error with traceback, and the pass continues with the explicitly nominated VINs; observations still applied.
2. A home location fix (observeLocation True) now resets the failed-probe count; a home source answer already did via _applyProbe (now tested).
3. A non-dict source result is logged and treated as no answer (falls through); dicts missing keys already handled by .get.
Tests: 8 new (TestFixRound1); 596 passed, 1 warning; presence file 5/5 clean loops; black clean.
