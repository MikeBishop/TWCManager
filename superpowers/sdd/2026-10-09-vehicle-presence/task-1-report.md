# Task 1 report

Status: DONE. Commit: see `git log -1` on fix/vehicle-presence (message "Key vehicle commands by (cmd, vin) and add explicit cancellation").

## What
Implemented brief verbatim: queue (cmd, vin) keying, cancel(), applyChargeLimit kwargs dispatch; TWCMaster start/stop/cancelStop with vin normalisation and cancel rules; tests updated/added.

## RED
- Queue tests: 7 failed / 24 passed (TestKeying x4, TestCancel x3), as predicted.
- TWCMaster TestChargeStartStopCancelRules: 5 failed / 1 passed (brief predicted 6 failed). test_stop_for_all_cancels_every_pending_start passed pre-implementation because the old queue key (cmd, None) collapsed all charge commands; the assertion is true either way. Not a defect.

## GREEN
- Queue tests: 31 passed.
- Full suite: 511 passed, 1 warning (matches brief). black check clean.

## Files
lib/TWCManager/VehicleCommandQueue.py, lib/TWCManager/TWCMaster.py, tests/unit/test_vehicle_command_queue.py, tests/unit/test_twcmaster.py

## Deviations
None to brief code. Only the sed/regex deletion of two tests left stray blank lines, which I tidied.

## Concerns
None.

## Fix round 1
`_applyChargeLimitKwargs` (lib/TWCManager/VehicleCommandQueue.py) now adds `vin` only when it is not None (remoteOnly unchanged), so modules without a `vin` parameter are not broken by plain applies. Added `test_apply_charge_limit_without_vin_omits_vin_kwarg` using a fake `legacy(limit)`. Full suite 512 passed, black clean. Committed separately.
