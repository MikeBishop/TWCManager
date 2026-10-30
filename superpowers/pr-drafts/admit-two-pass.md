Wake and start a car that would charge; share power in two passes

A follow-up to the 1.4.1 vehicle-model work, which is already merged. Closes #709.

## The bug

A car was plugged in at home, asleep, and finished at its old charge limit ("Complete"). At midnight a Scheduled Charging policy raised its limit, and nothing woke it. The car started only when woken by hand. This was found on a test install where the car is controlled from the car side (BLE), and the Gen2 TWC is held at 48 A by a separate master.

The wake check refused to wake any car the power split had offered 0 A. The split offered power only to points already drawing. So a car that wasn't charging could never get the wake that would start it. The same pattern also affected a Gen2 TWC echoing a 0 A offer, and a Gen3 unit reporting `complete`. 1.4.0 didn't have this bug.

## What changes

**Admission, then allocation (#709).** Every control tick now shares power in two passes:
1. **Admission.** Candidates are the points already drawing, first, followed by points whose car *would charge*. A car would charge when it is plugged in at home, its limit (pending or actual) is above its battery level, it isn't waiting on its own schedule (`respectVehicleSchedule`), and it is able to charge. A candidate is admitted while the sum of admitted minimums fits the total and each controller's budget. Points already drawing keep their places.
2. **Allocation.** Admitted points share the power at one water level, `clamp(L, min, max)`. Power a capped point can't use goes to the others, and a point whose minimum doesn't fit no longer wastes the share set aside for it (#709's example).

**Desired charging follows admission.**
- An admitted car that isn't charging is woken and started.
- A drawing car that isn't admitted is turned down to its minimum. It is stopped only if that lasts `startStopDelay`, and it is restarted only once room has lasted `startStopDelay`. This is Gen2's existing hold, applied to every EVSE kind and governed by the existing setting.
- Under a non-green policy, the stop is immediate.
- A start whose room goes away is held, not withdrawn, so its paid budget isn't reset.

**Wake check.** "Nothing offered" becomes "no room to start", read from an admission snapshot computed once per tick. Stops, restores and limits don't depend on it, and if computing admission fails, the answer is "no room". A raise that will start the car wakes it once: on the Fleet API, the start's own wake step sees the car online through the free online check and sends no second `wake_up`.

**A car whose state is unknown after a restart** (a Fleet-only install with no live feed) is woken at most once per restart to learn its state.

`master.offered` and the old fair-share loop are removed, along with the Gen2 gate's stop branch and withdraw path, which admission now covers.

**Docs:**
- `startStopDelay` (the hold and when to raise it; a delay of several minutes may help Track Green Energy ride out an oven or dryer cycling).
- Use one scheduler, TWCManager's or the car's, not both.

## Evidence

- **Unit tests:** 2,471 passed, 1 xfailed, on current `main` (after #731–#733). New tests:
  - #709's 25 A example;
  - the water-level splits (Gen3 16 A minimum beside 5 A cars, a capped car, total above the sum of maximums);
  - no eviction at 11 A vs 10 A;
  - hysteresis across 20 passes;
  - last night's replay (exactly one `wake_up` on a scripted Fleet car);
  - a dusk stop followed by a midnight start;
  - a car on its own schedule;
  - stops when admission fails;
  - one wake per restart;
  - no start/stop loop at a Gen2 gate;
  - the hold at the minimum;
  - a single low EMS reading at 30 s and 60 s not stopping anything.
- **Paid commands** (scripted Fleet car):
  - a car that accepts starts but stays "Stopped" costs 2 paid starts an hour whether power is steady or flapping at the edge every 10, 90 or 150 s (60, 40 and 24 before the hold);
  - power flapping 6/4 A around a 5 A minimum costs 2 `set_charging_amps` an hour (120 without the return hold);
  - power swinging across the minimum every 4 minutes costs 15 stops, 15 starts and 30 rate commands over 2 hours. That cost is what turning a car down to its minimum and later restoring it means; the test pins it.
- **Parity:** the command-path rows now run with power on, and every paid count is asserted. The only paid moves are the restart learning for a Fleet-only car whose charging state is unknown. Each row's comment explains its move.
- **Live box, overnight 2026-10-27 to 28** (with charge history, now #732, alongside): BLE, TeslaMate, car-side control, and the TWC held at 48 A by a fake master. At 00:00 Scheduled Charging raised the limit. TWCManager woke the car once and set the limit and the amps. The car started by itself, and the start was skipped as already satisfied. It charged until 00:58. At 05:00 a lower limit was held for the asleep car, which was at or above it, and went out when the car woke at 08:53. There were no tracebacks or restarts.

## Size

| | lib lines |
|---|---|
| `main` (4ff9e36e) | baseline |
| this PR | +98 (+264 −166) |

Removing the fair-share loop, `master.offered` and the gate's stop and withdraw paths pays for part of the new logic. The rest is the admission pass, the water level, per-controller budget groups, the hold in both directions, the shared admission snapshot, and the once-per-restart wake.

## Known limits

- Cars on no point (no TWC names them, and they have no car-side point) share the leftover room non-exclusively. Two of them may both start on room for one, and the next tick rebalances.
- Power swinging across a minimum more slowly than `startStopDelay` stops and restarts the car each swing. Raise `startStopDelay` where loads cycle.
- A car that never answers a wake gets the limit desire's existing retries: up to 4 wakes over 3 hours.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
