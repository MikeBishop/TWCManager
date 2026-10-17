# Task 7: wake decisions at INFO
Commit 5c133bef on vehicle-model/phase3.5. Suite: 1849 passed, 1 xfailed. Lib delta +35 (27341 -> 27376; over the +20 target, mostly Black expansion).
Log lines (logger TWCManager.Vehicle.Reconcile, INFO):
- "<provider> wake for <vin> before <capability>: <kind>[ <detail>]"  e.g. "TeslaBLE wake for 5YJ... before setChargeLimit: done"
- "<provider> no wake for <vin> before <capability>: <reason>"  reasons: current limit unknown | lower never wakes | blind paid retry | billed provider never wakes for amps
- Stops and restores: no skip line. Reads and one-shots (wakeSkipped None): none.
Mechanism: Attempt.wakeSkipped (Desired.py), VehicleReconciler._whyNoWake (Reconciler.py), Run._wake(provider, vin, capability).
Debug "sending anyway" line kept.
