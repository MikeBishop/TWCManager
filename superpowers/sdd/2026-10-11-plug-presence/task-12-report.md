# Task 12 report

Status: DONE. Commit on presence/4-fleet-rate-queue (see git log -1 in wt-plug). Full suite: 1159 passed (baseline 1151).

Changes
- VehiclePresence.bleSilent(vin): bleApplies (evaluated outside the lock) and the existing `_reach` record's last contact is a failure. `_reach` holds only the latest contact, so "no success within BLE_REACH_MAX_AGE" is implied. No parallel record added.
- VehiclePresence.isTwcAttributed(vin): vin in `_twcVin.values()` under `_lock`.
- TeslaAPIController.allEVSEs: per-vehicle filter; the blind and unknown+telemetry rules are waived by `_umcCar` (presence exists, isPluggedHome, bleSilent, not TWC-attributed). `served` (a TWC naming the car) still excludes. No presence: same behaviour as #694. getCarApiVehicles() is a plain accessor, so no longer short-circuiting on blind costs nothing.
- Scan failure still fails closed: `_twcServedVINs` sets `_scanFailed`, which `_umcCar` honours (advisor-flagged regression; test added).

Aging question: yes. An old failed probe with no probes since keeps bleSilent True indefinitely (no age check on failures, same as broadcastVINs' `not reach[0]`). Mostly benign here: an unplug drops isPluggedHome; a VIN-less plug attribution makes isTwcAttributed True; any later success overwrites the record. A car that stays on a UMC is correctly silent, so indefinite is right for this consumer. Residual: a car that moves from UMC to the TWC with no unplug seen would stay listed until attribution/contact.

Tests: 8 added in tests/unit/test_teslaapi_controller.py using a real VehiclePresence (telemetry plug + inside radius -> HOME, failed probe -> bleSilent).

## Fix round 1
bleSilent now also requires no success within BLE_REACH_MAX_AGE of now. A `_reachOk` dict (vin -> last success time, set beside `_reach` in the contact handler, read under `_lock`) tracks it; bleReachable/broadcastVINs unchanged. Docstring corrected. New test: success, failure at +10 s -> not silent and no EVSE; at +MAX_AGE+1 -> silent and listed. Confirmed failing before the fix. Full suite 1160 passed.
