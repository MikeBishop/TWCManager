# Review: fix/fleet-evse-zero-stop (4 commits on origin/main 8040bd5)

Verdict: **split it.** The loop fix (0a1e237) is correct and is the intended algorithm, so ship it alone. The vin-honouring change (3e03a13) is fine and can also stand alone. The stop/resume state machine (cdeafb8 + 5880b25) is **not ready** as a standalone PR on main. Its one-shot latch flips when the command is queued, not when it runs. Three paths I confirmed by running them lose the command, and a lost start leaves a car stopped indefinitely.

Focused tests pass (15). I ran probes against real `TeslaAPI` / `VehicleCommandQueue` to check the findings below (scratchpad/probe/test_probe.py).

---

## Critical

### C1. `_stopRequested` latches when the command is queued, not when it runs; lost commands are never retried
`lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py:147-157, 160-170`

The flag is set or cleared at queue time. `_queueCharge` goes through `queue_background_task`, which has no callback, so the EVSE never learns whether the command ran. After that it never re-sends: the stop is gated by `not _stopRequested` and the start by `_stopRequested`. Every one of these drops the command silently:

1. **Start lost to TeslaAPI's global 60 s gate** (`TeslaAPI.py:650`). Probe: stop V1 returns `success`, then start V1 returns `error` and nothing is POSTed. Scenario: the EMS dips below the 5 A minimum for one pass, then recovers. The stop goes out, the start comes less than 60 s later and is rejected, and the flag is already False. Every later pass only calls `setChargeRate`. For a Fleet-only car (no TWC) **no other code path ever sends a start**. Grep check: the only producers of `{"cmd": "charge"}` are `TWCMaster.start/stopCarsCharging` (TWCMaster.py:1871-1890) and the new `_queueCharge`. `startCarsCharging` is called only from `TWCSlave.py:576` and `TeslaAPIEVSE.startCharging`, and `EVSEController.startAllCharging` has no callers. The car stays "Stopped" until the user steps in. VehiclePriority's retry for TeslaAPI (priority 10, so 2 attempts) runs at once and hits the same gate.
2. **Second car's stop lost to the same gate.** Probe: stop V1 returns `success`, then stop V2 returns `error`. Two Fleet cars both offered 0 W in one pass: V2's flag stays True, so it is never re-stopped and keeps charging at its last rate. The distributor's accounting assumes it is not drawing, which risks grid import or breaker overload.
3. **Coalescing in `VehicleCommandQueue`** (`VehicleCommandQueue.py:44-50, 74-77`). `_key` is `("charge", None)` for every charge task. Probe: put stop V1, then put stop V2, and only `{vin: V2}` is left in `_high`. Also `put()` does `other.pop(key)`, so a start for V2 removes a pending stop for V1 and vice versa. Whenever the worker is busy (a BLE command can take minutes), cross-car commands overwrite each other.
4. Also lost: `car_api_available()` returning False during `carApiErrorRetryMins`; `update_charge()` failing; the `minChargeLevel` skip on stop. In each case the latch is already flipped.

The report treats 3 as "pre-existing, pairs with the #667 per-VIN keying fix". That fix is in the presence stack, not on main, so on its own this branch is exposed. Even with per-VIN keying, cases 1, 2 and 4 remain.

The two ways out are a design choice for the user:
- **(a) Outcome-driven latch.** Use `master.queue_vehicle_command(task, callback)`, which already supports callbacks, and re-arm the flag on a falsy or `"error"` result. This still depends on per-VIN queue keying landing first.
- **(b) No latch.** Drive stop and start from observed state on every pass, the way `TWCSlave.py:568-576` does: stop while `isCharging` and offered 0, start while offered ≥ min and the car is Stopped. This relies on the existing dedup: the 60 s gate, `stopAskingToStartCharging`, the respectVehicleSchedule check, and queue coalescing. The open problem with (b) is telling "Stopped by us" apart from "Stopped by the user or schedule". (b) also fixes I1. A small "we stopped it" record kept on the `CarApiVehicle` (not the EVSE) could be the tiebreak.

---

## Important

### I1. The flag lives on a cached EVSE instance that can be evicted
`TeslaAPIController.py` `allEVSEs` (eviction on `not v.atHome`); `TeslaAPIEVSE.py:34`

The flag is lost if `atHome` flaps once (a GPS glitch or a stale `update_location`) or the process restarts. After that, a car we stopped is "Stopped" with `wantsToCharge` True. It gets a fresh EVSE with `_stopRequested=False`, receives only `setChargeRate`, and is never started. This is the same failure as C1.1 and is more evidence that "we sent it" is the wrong state to hold on this object.

### I2. On main, a car served by a TWC can still have a separate Fleet EVSE, so this branch now API-stops it whatever chargeStopMode says
`TeslaAPIController.allEVSEs` on origin/main creates an EVSE for every at-home car. A Gen2 reads the VIN only once the car draws ≥ 1 A. While it cannot name the car (idle or scheduled, or a TWC that never reads the VIN), the car shows up both as a no-VIN Gen2TWC and as a TeslaAPIEVSE. Power is double-counted, which makes a 0 W share more likely. Before this branch, 0 W to the Fleet EVSE did nothing. Now it sends `charge_stop` over BLE or the Fleet API even when the user chose chargeStopMode 2/3 so that API stops would not happen. The presence stack fixes this (b48f3af "No Fleet API EVSE for a car a TWC serves or may serve" and 5851cf8), but that is not on main. **The stop/resume part should land after those, or depend on them explicitly.**

### I3. MergedEVSE with chargeRateControl=2 can fight the Gen2 slave (traced, not run)
`MergedEVSE.py` `setTargetPower`; `TWCSlave.py:707-710, 568-576`

With crc=2, only the TeslaAPIEVSE receives `setTargetPower`. The Gen2 slave's `_evseTargetAmps` keeps whatever was last set, for example from when it was a no-VIN EVSE before the VIN read merged it. The sequence: an API stop at 0 W; the slave still offers that stale value ≥ min; `reportedAmpsActual < 1`; so `TWCSlave.py:576` calls `startCarsCharging`. In mode 1 that is an untargeted start for every car. Before this branch, 0 W to the API side was a no-op, so this fight is new. Under crc=1 (the default) the API EVSE is never targeted, so the branch has no effect there. That is correct, and the report says so.

### I4. A manual user start while we hold a stop is never re-stopped
`TeslaAPIEVSE.py:147`

Sequence: we stop the car at 0 W, the user starts it from the app, and the share stays 0. `_stopRequested` is still True, so no new stop goes out and the car charges at its last commanded rate, which may be high. Then power returns, our start finds the car already charging, and TeslaAPI sets `stopAskingToStartCharging=True` for it. Respecting the user's override may be what we want. But the Gen2 path re-stops a car whenever it sees ≥ 4 A while it cannot offer the minimum. **The user should decide whether this difference is acceptable.** Either way, it should be documented in the code comment.

### I5. No hysteresis
A share that oscillates around `minPower` (5 A × voltage) produces a stop/start pair each time it crosses. The Gen2 path waits for the car to have taken current for 60 s before stopping it (`TWCSlave.py` ~500-565) and dampens changes with `startStopDelay`. Here every flap costs Fleet API calls, which are billed, and, because of the 60 s gate, turns into the lost-start case in C1.1. A minimum dwell before stop and before resume is needed whichever of (a) or (b) is chosen.

---

## Minor

- **M1. `test_start_precedes_rate` checks the wrong order** (`tests/unit/test_distributor_zero_share.py:335-346`). It checks the order of *calls*. But `setChargeRate` here is a synchronous call on the main thread, while the start runs later on the worker, so the commands actually *execute* in the reverse order. Setting the rate while stopped is harmless, but the test name overstates what it checks. Either rename it, or route the rate through the queue as the presence stack does (3ea8622).
- **M2. Tests miss the failing paths.** No test drives stop then start through a real `TeslaAPI` (that would have caught the 60 s gate), and none puts two Fleet EVSEs at 0 W in one pass through a real `VehicleCommandQueue` (that would have caught coalescing). `test_zero_share_stop_is_vin_only_in_every_stop_mode` mocks `queue_background_task`, so it shows the EVSE avoids `start/stopCarsCharging`. It does not show the stop reaches only one car. `test_teslaapi_charge_vin.py` mocks `applyChargeLimit`, so the start path through it (M3) is untested.
- **M3. A targeted start can still wake other cars through `applyChargeLimit`.** A targeted start calls `applyChargeLimit(lastChargeLimitApplied, checkArrival=True)` (`TeslaAPI.py` ~791). Its `car_api_available(applyLimit=True)` call takes no vin, so if `needToWake` is set (a raised limit) it wakes every car. Rare, because the limit is usually unchanged, but intent 3 says "wake only that vehicle".
- **M4. A targeted BLE stop clears every car's dedupe state.** `TeslaBLE.car_api_charge` honours `vin` but runs `self._stopAskingToStartCharging.clear()` for every VIN on any stop (`TeslaBLE.py` ~227). A targeted stop therefore resets other cars' start dedupe. This predates the branch, but the branch is what makes targeted stops common. The effect is harmless extra starts.
- **M5. The resume start ignores state.** If the car finished (Complete) and was later unplugged while the flag was True, the cache eviction clears the flag. But if it stays plugged and Complete and a raised limit later turns it "Stopped", our stale flag sends a start. This is benign, since the car would charge anyway.
- **M6.** `import pytest` sits in the middle of `test_distributor_zero_share.py` (line ~425). Move it to the top.
- **M7.** `setTargetPower` touches the same lines as fix/vehicle-presence 3ea8622 (queued Fleet rate). Expect a merge conflict whichever lands second.
- `isReadOnly` is fine: read-only EVSEs are left out of both `wants_power` and the zero-out loop, and `car_api_charge` refuses them anyway. - **M8.** `HomeAssistant.car_api_charge` ignores `vin` and acts on every connected at-home car (`HomeAssistant.py:511`). It has no Vehicle priority, so when VehiclePriority is loaded (the normal case) it never receives charge commands. If VehiclePriority is not loaded, `_resolveVehicleCommandModule` falls back to HomeAssistant second, and a targeted stop would stop every HA car.
- Checked and fine: **a car that stops on its own** (the user pauses it from the app while we are offering power and `_stopRequested` is False). `isCharging` is False and the flag stays False, so the resume path never runs. Only `setChargeRate` continues, and the user's stop is respected.

---

## Loop fix (0a1e237): correct, and should be its own PR

`TWCMaster.py:546-548`. Before the fix, `for evse in pending` combined with `pending.remove(evse)` visited items 0, 2, 4, and so on. The odd-indexed EVSEs **never got `setTargetPower`**: Gen2 slaves kept a stale `_evseTargetAmps` (or fell back to the legacy per-slave calculation), and Fleet cars got no rate. The shares of the visited ones were also wrong, because `len(pending)` still counted the skipped EVSEs.

After the fix, `fair_share = remaining / len(pending)` with `pending` shrinking each step is standard progressive filling, in ascending `maxPower` order. Each EVSE's capacity is capped, and what it leaves unused flows to the larger ones. That matches the docstring ("most constrained first, reducing wasted capacity"), so **this is the intended algorithm**, not a change to it. One consequence that follows from the design: when power is below the sum of minimums, the smaller-`maxPower` EVSEs get 0 and the last one gets everything ("one charges rather than none"). This is not a bug.

This does change behaviour for Gen2 slaves in mixed installs: slaves that were skipped now get distributor targets. That is a correct change, but it should be called out in the PR, because it affects every install with more than one EVSE and TeslaAPIController loaded.

**Split it**: one line plus `test_distributor_visits_every_evse`. That test fails on the old code (it skips the middle EVSE). It could also assert the filled values, for example 3 EVSEs with ample power each get `maxPower`, and a tight budget gives `[r/3, (r - r/3)/2, ...]`. `test_distributor_stops_fleet_and_leaves_gen2_alone` depends on this fix, because the Fleet car sorts second, so the split PR has to merge first.

## vin honouring (3e03a13): fine to land on its own
It skips other cars in the reset loop, the wake loop and the command loop. With `vin=None` the behaviour is unchanged, and the tests show both cases and that they fail without the fix. M3 remains. It is useful independently of the stop/resume work, for example for TWCSlave's mode-3 `startCarsCharging(vin)`.
