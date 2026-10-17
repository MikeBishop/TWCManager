# Slim Task 12c review: restart presence (bcb4042..4fd7c9d)

Reviewer: independent read-only review. The code was read at `scratchpad/wt-vm3` (4fd7c9d) and the tree was left clean. Mutations ran on a `git archive` copy at `scratchpad/rev12c/src`.

## Verdicts

- **Spec compliance: PASS, with two deviations that need a ruling** (I2, M5). Reqs 1, 2, 4 and 5 are met. Req 3 is met for 03 and the other plugged states, but deliberately not for 00.
- **Quality / cost safety: PASS with fixes.** There is no Critical finding. Presence and the departure sweep make no HTTP request. Paid fan-out stays within the existing caps. Lock order and thread rules hold. One requirement-level path has no test that pins it (I1).

**Counts: Critical 0, Important 2, Minor 7.**

## Live scenario trace (4fd7c9d)

Setup: restart; Gen2 at 03 offering 47–48 A, drawing 0; no TWC VIN (`currentVIN = lastVIN = ""`); TeslaMate lat/lon at home; heldLimits `{VIN: (100, 50)}`; ble_only; BLE paired; SOC 51.

1. **Heartbeat** (serial thread). `TWCSlave.receive_slave_heartbeat` sets `reportedState = 0x03` (`TWCSlave.py:662`), then calls `num_cars_charging_now` (`:753`).
   - Amps are below 1, `isCharging == 0`, and the state is in `PLUGGED_STATES` (`Gen2TWC.py:24`), so `TWCMaster.py:1331-1335` checks the key.
   - `Gen2TWC.vehicleKey` (`Gen2TWC.py:98-112`) is None, so `_plugSession(True)` runs and the key becomes `anon:8244`.
2. **Policy pass.** `Policy.py:321` → `setPolicyLimit(70, True)` (`TWCMaster.py:1851`) → `applyPolicyLimit` (`Targets.py:101`) → `presentVehicles` → `_present` (`Targets.py:29`).
   - There is no twcVin. The TeslaAPI attachment is present, so `_located` → `CarApiVehicle.locate()` (`TeslaAPI.py:1866-1872`) reads `lat` (a RegistryField, the latest from any source, `TeslaAPI.py:1601`). That is TeslaMate's home fix, so it returns True and the car is present.
   - If TeslaMate has not delivered a position yet, `lat == 10000` and the held (100, 50) record makes the car present (`Targets.py:40-42`).
   - If the vehicle list has not loaded yet, the BLE claim makes it present (`:46`).
   - `order.candidates(SET_CHARGE_LIMIT)` gives TeslaBLE, so `desired.set(VIN, CHARGE_LIMIT, 70, "policy", True)`.
   - The sweep (`:111-116`) finds `_located` True, so there is no restore.
   - Later policy ticks repeat this with `decision=False`. An unchanged value is a no-op (`Desired.py:280-289`).
3. **Reconciler.** `plan` (`Reconciler.py:236`): known chargeLimit is TeslaMate's 50, so `allowWake` (`Belief.py:95-97`) is true for 70 > 50 and `wake=True` (`Reconciler.py:384-386`).
   - `decideChargeLimit` with held (100, 50), current 50: not hand-set; it sends 70 and saves `HeldLimit(100, 70)`.
   - The BLE calls are wake, then `setChargeLimit 70`.
4. **Lift and rate.** At heartbeat (`TWCSlave.py:932-936`), chargeRateControl 1 and `vehicleRateRaised` False lead to `_requestVehicleRateRaise` → `_setCarAmps` (`:131`).
   - The key is anon, so `_anonCars` → `broadcastVehicles(SET_AMPS)` reaches the car, and TeslaMate "Complete" is in `_PLUGGED`.
   - The result is an AMPS lift desire at wiringMax. BLE is local, so it wakes and then `setAmps`. This matches main's BLE `setChargeRate` that woke the car at 00:15:09.
   - If the first heartbeats run before the session begins, the key is None, `_setCarAmps` returns False and the lift is retried on the next heartbeat.
5. **Start.** Offered ≥ min, amps < 1 and not 02 lead to `startCarsCharging("anon:8244")` (`TWCSlave.py:629-637`) → `_chargeTargets` → `broadcastVehicles(START)` (mode 1 or 3), which sets a CHARGING desire on the car.
   - TeslaMate's "Complete" satisfies it, so nothing is sent. The car starts on its own once 70 > SOC 51, as main's log showed at 00:17:06.
   - If it reports "Stopped" instead, the start is sent over BLE with a wake (`allowWake` CHARGING True). The limit goes first (`Reconciler.py:358-371`).
6. **Charging.** Amps flow, so `isCharging = 1` and a VIN query runs. `observeTwcVin` merges the anonymous session into the VIN car, which gets twcVin, and the normal path resumes.

Fleet/Owner requests: none. TeslaBLE is the only candidate under ble_only, presence and the sweep do no I/O, and `test_a_restart_…` and `test_a_vinless_gen2_…` assert `requests_mock.call_count == 0` under a catch-all mock. I confirmed that the mock counts HTTP: with an injected `update_vehicle_data()` in `_present`, 4 of the 5 restart tests fail on `call_count` (see Tests).

**The live scenario works.** At 00 it also works, because the raise from 50 to 70 wakes the car over BLE through presence alone. 00 matters only when no limit raise is pending (I2).

## Important

### I1. The held-limit presence (main's `wasAtHome`) is not pinned; the BLE claim masks it
- **Evidence:** `Targets.py:40-42`. The "no position" test `test_limit_wiring.py:258-262` uses `restarted(position=None)` with the default `claim=True`, so `_present` reaches `"TeslaBLE" in vehicle.claims` (`Targets.py:46`) whether or not the held clause exists.
- **Mutation:** changing `if api.atHome or held is not None and held.held is not None:` to `if api.atHome:` leaves all 104 tests in the three files passing.
- **Impact:** req 1's sub-bullet and req 4's third test ("no position plus a held limit counts as present") have no test. A Fleet-only or Owner+Fleet car with no BLE and no position would silently lose presence after a restart if this regressed. That is the live failure again, minus BLE.
- **Fix:** add a case with `restarted(position=None, claim=False)` under a policy whose candidates exist without BLE (for example `prefer_ble` with the Fleet slot). Assert `presentVehicles(m, C.SET_CHARGE_LIMIT) == [v]` and that a desire of 70 is set (no `r.pass_()` is needed). Then check that `held=False` makes it absent. Mutation-check it against the clause above.

### I2. Status 00 deliberately does not match main (the brief says "match it"); this needs a ruling
- **Evidence:** `TWCMaster.py:1336-1340`. 00 ends an anonymous session and never begins one. `Gen2TWC.py:123` itself says "A Gen2 reports 00 for a sleeping plugged car". Main fans out the rate raise with no state check (`main:TWCSlave.py:902-910`) and starts on any state other than 02 (`:566-572`). The report's §"Requirement 3" documents the deviation.
- **Impact:** a car asleep at 00 with no limit raise pending gets no lift and no start, so nothing wakes it. For example, a green-energy policy stopped the car, it slept, and the Gen2 later shows 00. It charges only when it wakes on its own. Main would have woken it. Fanning out from every 00 (main) would also wake at-home cars from an empty TWC. The live failure was at 03, so this does not block the live test.
- **Fix:** get the user's ruling. A cheap middle ground with no paid reads: at 00, begin the anonymous session only when a free source shows an at-home car plugged in (`pluggedIn` True, or `chargingState` in `_PLUGGED` from TeslaMate or BLE, and `_located` not False). `_anonCars` already filters on the same evidence. That keeps an empty TWC silent and matches main for the sleeping-at-00 car.

## Minor

### M1. Position age is never checked; a stale "away" fix can restore a car that is actually home
- **Evidence:** `TeslaAPI.py:1866-1872` (no age) and the sweep `Targets.py:111-116`.
- **Stale home:** a departed held car stays present and gets raise desires with a wake. Under ble_only that costs nothing (out of BLE range, BLE fails). Under a Fleet policy each desire is capped at 2+2 paid sends. Main's telemetry branch did the same, and BASE's stale `atHome` too, so this is not new exposure.
- **Stale away:** for a car actually home, it gives a restore desire, which never wakes (`Belief.py:93`). The car's normal limit returns, and the policy limit is not re-applied until a TWC VIN or a newer position. This happens only when no source has seen the car since it came home. With TeslaMate live, arrival always posts a home fix. `vehicleIsDefinitelyHome` refreshes the fix when a TWC names the car.
- **Fix (cheap, optional):** in the sweep, restore only when the away fix is newer than our last limit write: `v.latest("lat").at > (v.lastWrite("chargeLimit").at or 0)`. A fix older than the hold cannot show a departure. Note that TeslaMate's retained messages are stamped on receipt, so a plain age gate would not help for TeslaMate.

### M2. The main regression test still passes with the `_present` change reverted
- **Evidence:** the `test_a_restart_…` test (`test_limit_wiring.py:249`). `_located()` has a side effect: `locate()` writes `atHome`. Applying `_present` → `return bool(api.atHome)` leaves it green, because `setPolicyLimit(50)`'s sweep calls `locate()` and sets `atHome = True` before `setPolicyLimit(70)` reads it. Only the no-position and vinless tests fail under that mutation.
- The behaviour is robust, because the sweep runs on every tick. But the test does not pin req 1 on its own, and the predicate's side effect is a smell: `broadcastVehicles` → `_located` writes `atHome` from the serial thread.
- **Fix:** in that test, drop the first `setPolicyLimit(50)` (assert on the first pass). Alternatively, make `locate()` pure (return the judgement) and assign `atHome` only in the sweep or `_present`.

### M3. The `getattr(api, "locate", lambda: None)` tolerance is for test fakes only
- **Evidence:** `Targets.py:26`. The only production TeslaAPI attachment is `CarApiVehicle` (`TeslaAPI.py:1635`). The fakes without `locate` are `test_vehicle_endpoint.py:22` and `test_charging_points.py:136` (SimpleNamespace).
- **Fix:** add `locate=lambda: None` to those two helpers and call `api.locate()` directly. This removes the `getattr` and hides no AttributeError in production. It saves nothing in size, but one less defensive branch is good.

### M4. `onDeparture`'s gate keys on telemetry liveness, not on "no free position"
- **Evidence:** `Targets.py:135-137`.
- With telemetry live but no fix yet, nothing is read and the car stays present on the held clause. The next policy sweep restores once a fix arrives, so this delays the restore and does not lose it.
- With telemetry not live and an older free fix, it still pays for the read (the same as BASE and main), which is prudent because that fix is stale.
- This is acceptable, but it differs from the brief's wording. Record it as a ruling.

### M5. With no home set, there is no presence from position
- **Evidence:** `TeslaAPI.py:1869`. A fresh box relies on the held limit or the BLE claim until a paid read seeds home. Main's telemetry branch seeded home from TeslaMate.
- Refusing to seed from a possibly stale fix on every policy pass is defensible, and it never queues `saveSettings` per pass. No fix is needed. Document it in the setup notes (set home, or let the first VIN'd charge seed it).

### M6. Anonymous re-sessions are bounded
- After an anonymous charge ends, the debounce path (`TWCMaster.py:1305-1330`) resets `vehicleRateRaised`, and the next heartbeat at 03 begins a new anonymous session and sets a new lift.
- A probe (scratch, deleted) showed the second session's lift sends nothing. The reconciler stamps the first lift's write (`Run.py:202`), the new lift is satisfied by it and cleared (`Reconciler.py:243-246`), and there is no wake.
- A 03↔00 flap does not reset `vehicleRateRaised`, so it never re-lifts.
- A Gen2 that never reads a VIN (old firmware) gets at most one lift per charge cycle, and only after something else has lowered the car's request. That is main's once-per-session rule.
- The start fan-out at idle 03 now runs (new against BASE, narrower than main): cars that are hands-off ("Disconnected") or already satisfied get nothing. Paid starts under a Fleet policy stay within the existing caps. No fix is needed.

### M7. Size: +45 lib, about 8 lines could go
- `Targets.py` is +28 net, `TWCMaster.py` +11 and `TeslaAPI.py` +8. That is proportionate for a live-failure fix. The geofence is reused rather than duplicated.
- **Savings:**
  - The sweep and `onDeparture` share a loop body. The sweep could be `onDeparture` without the read, using `not _present(...)`. That is equivalent for API cars, and for HA/BLE cars it matches `onDeparture`'s existing rule. It saves about 5 lines.
  - M3 removes the `getattr`.
  - The repeated `held is not None and held.held is not None` (`Targets.py:41`, `:92`) could become a `HeldLimits.holds(vin)` helper, if one does not already exist.

## Checked, no finding

- **Paid reads from `locate()` setting `atHome`.** `updateChargeAtHome` (`TeslaAPI.py:1484-1490`) runs only:
  - at boot (`TWCManager.py:829`)
  - on `checkArrival`
  - at most every `chargeUpdateInterval` (1800 s), through `minBatteryLevelAtHome`, which only the `limitOverride and chargeAmps == 0` path calls (`Policy.py:310-312`)

  Each run makes one `_readFresh("batteryLevel", 300)`: BLE first, then the cloud, never a wake. The cloud read checks the state first, so an asleep car gets no vehicle_data (the injected-read probe saw only `GET /vehicles/<vin>`). This is the same rate as main, whose `atHome` also came from TeslaMate. At worst it is 48 reads a day for an awake car whose BLE read fails and with no Owner fallback.
- **Gen3.** The `_located` twcVin guard keeps `vehicleIsDefinitelyHome`'s forced `atHome`. `VehicleEndpoints.allEVSEs` (`:120`) and the Gen3 correlation (`Gen3TWC.py:282`) now see `atHome` from the latest fix after a restart, which is an improvement and main parity. `num_cars_charging_now` iterates Gen2 slaves only. The full suite passes: 1723 passed, 1 xfailed.
- **Locks and threads.**
  - `locate()` makes no I/O and takes no lock, apart from the registry leaf inside `RegistryField`. Its home-unset early return avoids `is_location_home`'s seeding path (`TeslaAPI.py:575-598`), which would queue `saveSettings`.
  - The sweep takes settingsLock through `heldLimits.holding()` under Policy's private `_evalLock`. That pattern already existed (`_restore`).
  - The new `_plugSession` calls do dict work under the registry leaf only. They can also run from `getStatus` (HTTP) and `getMaxAmpsForTargetGridUsage`, as the amps-flow `_plugSession` already does, and `beginPlugSession` is idempotent. There is no RS-485 I/O off the serial thread, and the code uses `time.time` only.
- **Tests.** The 6 new tests and the suite are green: 104 tests in the three files, and the full unit suite at 1723 passed and 1 xfailed.

  | Mutation | Failing tests |
  |---|---|
  | Revert `_present` to `bool(api.atHome)` | no-position, vinless (restart survives: M2) |
  | Drop the held clause | **none** (I1) |
  | Drop the departure sweep | free-position-away |
  | Drop the 03 begin | vinless |
  | Drop the 00 end | vinless |
  | Drop the `syncSource` gate | live-telemetry departure |
  | Drop the twcVin guard in `_located` | stale-fix |
  | Drop `_located` in `broadcastVehicles` | 5 converted fan-out tests |
  | `locate()` returns None | 11 tests, including restart |

  Paid counts are real. The catch-all `requests_mock.register_uri(ANY, ANY)` together with `call_count == 0` fails with an injected `update_vehicle_data()` in 4 of the 5 restart tests. The stale-fix test does not count calls.
