# Task 1 fix round 1 re-review (d9939bf..7d5b87e)

Verdict: PASS. I1, I2 and the minors are fixed, and no regressions or new Important findings. 21 focused tests pass, and 200 pass with the registry tests.

- I1: DesiredStore.forget/followRegistry (Desired.py) and VehicleRegistry.onRemove/_removed. The hook fires from all four removal paths (the only four places that delete from `_vehicles`, VehicleRegistry.py:143, 161, 190, 230): forget, expire, endPlugSession (anon), and the anon merge into a VIN. The test covers all four, plus 50 churned anon sessions.
- No Reconcile import in Registry/ (grep clean); the hook is a plain callback.
- Lock order: every _removed call is after the `with self._lock` block closes. _removed takes the RLock only to copy the callbacks, then calls them outside it. The store's forget takes only its own leaf lock and notifies nothing. Callers (TWCMaster, Gen3TWC, HTTPControl) do not hold the registry lock. No inversion.
- I2: exclude() records REFUSED in `refused`; newDesire keeps only the refused exclusions; newRound/reset clear `refused`; the summary shows it. Tested.
- Minors: by-only, in-place takeover, adopt-ignores, paid and offeringSince restamp are all tested. adopt classifies before the lock. The fallback now catches only a ModuleNotFoundError whose name is the Reconciler module, and there is a test. adopt(None) is ignored.

Notes, not blocking:
- Wiring is open: nothing calls followRegistry yet (report says so). Whichever task creates master.desired must call it.
- Desired state on an anon key is dropped at merge rather than moved to the VIN. Task 8 must re-set it for the VIN.
- Task 6 must use AttemptRecord.exclude(), not excluded.add().
