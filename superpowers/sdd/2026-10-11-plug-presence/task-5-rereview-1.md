# Task 5 re-review 1 (f4d6837..80a5b03)

I1 ADDRESSED - VehiclePresence.py _reconcileDeparting: no early return on fallbackSent; fallbackSent set unconditionally once; afterFallback forces slow interval, no clamp toward fallback; due loop bleOnly = viaBle; reachable + not queued re-queues. Tests cover remote and ble_only (real handlers).
I2 ADDRESSED - _sweepHeld(now) at end of runPass: only _home[vin] is False and no record; presumed/home excluded; _restorePending gate; record exists afterwards so no re-send. Tests cover held-after-leave, presumed/home, nothing-held.

Wake check: _timeUntilNextDue adds now+60 (always > now), so the wait is never 0 from the sweep term; no busy loop. Per pass the sweep costs one settings dict lookup per record-less not-home car, done outside the lock; lock held only briefly twice. No contention concern. (Past-due _due entries could spin only as before the fix.)

New breakage: None.
Out-of-scope: none.
