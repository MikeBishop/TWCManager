# Task 3 report
Status: DONE. Commit: see `git log -1` on feat/fleet-charge-backfill ("feat: count a car at its commanded rate until a reading confirms it").
Files: lib/TWCManager/Vehicle/Watch.py (believedAmps, chargingAmps(ledgered)), tests/unit/test_watch_load_step.py, tests/unit/test_charging_points.py.
RED (Watch.py reverted): FAILED start-counts-at-commanded, start-with-no-rate-uses-max, raised-rate-counts-at-once, ledgered-cloudOnly. The lowered-rate/stop tests and the allocation pin PASS at RED (old behavior already keeps the reading; spec claim about `taken` holds).
GREEN: tests/unit/test_watch*.py test_twcmaster.py test_charging_points.py: 175 passed. Full suite: 2608 passed, 1 xfailed.
ledgered=False uses cloudOnly(master, v) (Task 4 swaps in fleetOnly).
Concerns: chargingAmps now iterates all vehicles via believedAmps (same filters as before: not anonymous, not TWC-named, at home). A commanded start counts for HOME_AWAKE or HOME_CHARGING cars; a rate write counts only when the car is (or was just commanded) Charging.
