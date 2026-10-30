# API-only fixes, fix round 1: scoped review

Code: wt-vm5 phase5 b48dd13b. I re-ran test_command_path_parity.py, test_sleeping_car.py and test_teslaapi_wake.py: 168 passed in 10.9 s. I did not re-run the full suite.

## Findings

- **I1: addressed.** Belief.py:65 now requires `twc.at > max(obs.at, vehicle._clock() - FEED_LAG)`, so a frozen reading stops counting after 30 s. Gen3 observes `actualCurrent` on every connected update (Gen3TWC.py:~238) and Gen2 heartbeats about every second, so a live TWC stays inside the window. The registry clock is the same one that stamps `twc.at`. The stale test row exists.
- **M1: addressed.** The loop now has a monotonic deadline of 45 s. The count stays as a backstop, which is reasonable. The test exists.
- **M2: addressed** (`max(now, onlineCheckedAt)`, and the test asserts the stamp).
- **M3: accepted, no change.** Matches the ruling.
- **M4: addressed for the AMPS case, as the report says. The blind-paid-retry variant is left alone.** See the analysis below. The variant is an optional extra and is not a regression.
- **M5, M6: addressed** (comments, CHANGELOG, docs).
- **M7: addressed.** The new test found that the stop behaviour is unchanged and pre-existing. That is a fair outcome.

## M4 stranding analysis (Reconciler.py:336-340)

`mayWake = wakes and (aspect != AMPS or holder.local)`. The hold breaks on a heartbeat only when `mayWake` is true. Otherwise it waits for a sign of life: `Presence.asleep(v, heldAt)` is False, or `lastObservedAt > heldAt`.

- **ASLEEP is produced in only two places.** Run.py:164 is the BLE `quiet` case. It needs `not attempt.wake`, and for a local provider `attempt.wake == wakes` (Reconciler.py:411). So it happens only when `wakes` is False, which was already not `mayWake`. Run.py:194 is the non-local, no-wake case. For AMPS that is the "billed never wakes for amps" rule. For other aspects it needs `wakes` False or a blind paid retry.
- **A BLE amps change to an asleep car is not stranded.** It runs with wake=True and wakes the car. If it holds ASLEEP, it is a non-wake hold anyway. A start or a charge limit that wakes (`wakes` True, non-AMPS) keeps `mayWake` True, so these break exactly as before.
- **An Owner API install is not stranded.** An Owner amps hold is a no-wake ASLEEP hold both before and after the fix, so it cannot wake the car on any pass. Owner start and limit keep `mayWake` True.
- **A cloud-held amps hold gets its sign of life from the free check.** `_asleepCheckDue` runs the free online check every 15 or 30 minutes when no live feed covers the car. An online answer is an observation, so `Presence.asleep` goes False and the desire re-plans. With a feed, the feed reports the car waking.
- **An empty or unknown `lastProvider`** gives `holder=None` and `mayWake` False for AMPS. That happens only if `last == ASLEEP`, which always sets the provider, so it cannot occur.

### Residual (Minor, not a regression)

Reconciler.py:336, a mixed-path amps hold:
1. A car has a BLE path, and the BLE attempt fails (UNREACHABLE, so the provider is excluded for that pass).
2. The attempt falls to an Owner provider that holds the amps change ASLEEP. Owner is the only fallback here: Order.py:96-102 bars billed providers when a local path covers the amps.
3. `lastProvider` is now Owner, so `mayWake` is False. The old code re-planned on every heartbeat and so re-tried BLE. Now BLE is re-tried only on a sign of life: an observation or the 15-minute free check.

If the car is asleep and out of BLE range, a retry would fail anyway. If it comes into range, BLE advertisements or the check should surface it. I could not confirm that BLE adverts count as `lastObservedAt` observations. The worst case is a delay of up to 15 minutes (home) or 30 minutes (away) on an amps change to an asleep car. The report and the earlier review already accept this trade.

## New issues

None blocking. The blind-paid-retry hold (non-AMPS, `wakes` True, ASLEEP) still logs on each heartbeat. The report says so openly.

## Lib growth

+36 against +28 in round 0. The breakdown in the report (I1 +3, M1 +3, M4 +3, M5 -2) is plausible and matches the diffs I read.
