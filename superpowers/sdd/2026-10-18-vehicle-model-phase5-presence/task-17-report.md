# Task 17: close an unmatched session on a clear unplug the filter cannot confirm

Commit: 3b853066 on vehicle-model/phase5 (base 3b28a9e6). Not pushed.

## Change (lib/TWCManager/TWCMaster.py, +1 line net)
- observeChargingSessions: the fallback is now `zeroSince == now and not (reportedAmpsMax or ampsMaxBefore)`, read after unplugStep.
  - zeroSince == now is true only on the step that began a 00 run (state 0), which replaces both `idle` and the reportedState test.
  - After unplugStep at an onset, ampsMaxBefore is 0 exactly when the car was idle (max 0 before) or the grace/short run/max>0 blocked the filter. If it is still > 0, the filtered unplug is pending and the fallback stays out. So the pre-step value is not needed.
  - A waking 00 (max stays up) is excluded by reportedAmpsMax.
- _plugSession: the existing fallback (depart=False) did NOT apply the veto, since it passed no candidates. Now candidates are always computed for an anonymous point; the veto applies to both paths, and `depart` only gates the departure observe/log. Both closes now behave the same.

## Tests (4 new, each failing first where it applies)
test_gen2_unplug.py: unplug inside grace closes (fails before); unplug after 30 s plugged run closes (fails before); waking 00 inside grace stays open (passes before, pins).
test_presence.py: live TeslaMate pluggedIn True vetoes the grace close (fails without the _plugSession change).
Existing idle-at-0-A test, the 10:14 box replay row and the idle-at-0 parity row pass unchanged.

## Results
tests/unit + tests/EMS: 2175 passed (baseline 2171 + 4). Parity counts: no moves. Lib: 26338 lines after; +1.
