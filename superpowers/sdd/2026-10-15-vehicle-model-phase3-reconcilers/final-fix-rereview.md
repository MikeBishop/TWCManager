# Final-fix scoped re-review: vehicle-model Phase 3 (fc6eba7..db47522)

Reviewer: Opus, read-only. HEAD db47522 in `scratchpad/wt-vm3`. A scratch worktree at fc6eba7 was used for the red check, then removed; `wt-vm3` is clean.

- Suite: `1764 passed, 1 xfailed, 1 warning in 83.91s`.
- `black --check lib`: 93 files unchanged.

## Verdict: APPROVED

I1 is closed and safe under the wiring rule. The I2 removals are clean. M1 and M8 are correct. The 4 deleted tests are PLUMBING-ONLY. There are three new Minors, all on chargeRateControl 2 only (none affects the mode-1 box). They are watch items for a live mode-2 install, not blockers.

## 1. I1 (wiring safety)

**The fix works.** At `TWCSlave.py:946-949`, the mode-2 branch (and mode 3 below 6 A) offers `wiringMaxAmps` only when `_carRateConfirmed()` (`:161`) holds. Until then it offers `int(target)`. `_carRateConfirmed` returns False when:
- there is no desire;
- there is no vehicle;
- `known(v, AMPS)` (our delivered write, or a newer `chargeCurrentRequest` reading) does not satisfy the desire;
- the key list is empty.

`ChargingPoint.py:195` hands the TWC `max(floor, amps)`, not `maxPower`.

**Red at BASE.** I copied the HEAD `test_command_path_parity.py` and `test_amps_reconciler.py` into fc6eba7. Five tests fail there, including `test_mode_2_twc_holds_the_target_until_the_car_rate_lands` and `test_mode_2_twc_target_never_drops_below_the_floor`. All pass at HEAD. The probe records `lastAmpsOffered`, which is the value on the wire after the spike and dampening logic, so it tests the right thing.

**Overshoot.**
- When the target drops, the offer falls from 32 to the target on the next heartbeat, before the car command lands. That is better than main, which overshot until the command landed.
- When the target rises, the offer goes to the new target while the car is still at the old one. That is an undershoot.
- No sustained overshoot remains on the failure path. The paid bound is unchanged: `[10, 10]`.

**Can a target be too low?** No. The held value is the distributor's (or the heartbeat's) share, which is exactly what mode 1 offers. `set_last_amps_offered` still caps it. A car that can never be confirmed (Owner-only, ble_only with no key, a guest car with an anonymous session and an empty `_ampsKeys`) is held to its share for good. In effect that is mode 1 on the wire, and it is safe.

Main's mode 2 offered max and relied on the car's own amps. For a car that could not be commanded, the car drew whatever it was last set to, which was a sustained overshoot of a shared budget. The new behaviour is the correct trade under the wiring rule. The idle-minimum and offer-0 path (`desiredAmpsOffered < minAmpsToOffer`) comes before the changed branch and is untouched.

**Firmware risk (drop then raise).** The cycle happens on every distinct integer target change: the offer drops from max to T on the next heartbeat, then rises from T back to `wiringMaxAmps` once the car's rate is confirmed.
- The distributor runs once per round-robin, but its input (the policy's green amps) moves at most once per `policyCheckInterval`, which defaults to 30 s.
- So there are at most about 120 cycles an hour. I estimate 5-15 an hour on a clear-sky ramp and 20-60 an hour on a partly cloudy day.
- On the multi-TWC heartbeat-only path, the target subtracts the other TWCs' `reportedAmpsActual`. It can jitter by 1 A at an integer boundary and cycle more often.

Mitigation: the code's own 2017 notes (`TWCSlave.py`, the spike comments) say the 6 A drop is triggered by raises below `spikeAmpsToCancel6ALimit` (default 16), and that "the car should have no problem increasing max amps to any whole value over spikeAmpsToCancel6ALimit". The raise in the confirmed cycle goes to `wiringMaxAmps`, which is 16 or more on typical installs. Per those notes, the per-change cycle is not itself a trigger. The residual risk is in N1 and N2.

**Mode 1, mode 3 at or above the floor, and Gen3 are unchanged.**
- **Mode 1:** `carriers()` returns (True, False), so the first `ChargingPoint` branch is always taken. The heartbeat's `else` branch is byte-identical.
- **Mode 3 at or above the floor:** the first branch again, then the heartbeat's `else`.
- **Mode 3 below the floor:** `max(floor, amps) == floor`, the same as BASE. The heartbeat sees `floor >= 6` and so takes the `else` branch, which is unchanged. The changed branch is reached in mode 3 only on the heartbeat-only path, and only when `minAmpsToOffer < 6`.
- **Gen3:** no `pointOwnsAmps`, so it is untouched. `test_gen3_shared_headroom_meets_the_budget` and the Gen3 point tests pass.

## 2. I2 removals

**Spot-checks.** I ran `git grep -nw` over lib (which includes `Control/themes` templates), html, tests/integration, tests/API, docs, contrib and etc.

| Removed | Hits outside its own definition |
|---|---|
| `getSetting` | 0 |
| `setSetting` | Only the HTTP route string `/api/setSetting` and its docs and API tests. The route writes `settings` directly under the lock. |
| `time_now` | 0 |
| `lastVehicleStatusTime` | 0 |
| `getVehicleCount`, `getCarApiVehicles` | 0 |
| `commandMethod` | 0 |
| `_normalise`, `_groupKey`, `_anonymous` | 0 |
| `is_location_within_radius` | Only TeslaAPI's own method, which is kept. |
| `.startCharging()`, `.stopCharging()` call syntax | 0 |
| `updateSettings` | Only TeslaBLE's real definition, plus the guarded call in TWCMaster. |

`checkModuleCapability` was correctly kept: `graphs.html.j2:10` calls it. Templates can call methods.

**Gen3.** The `_onUnit` inlining in `Gen3TWCProvider` matches the removed `Gen3TWC.start/stopCharging` exactly: `setUnitTarget(ID, 0)` and `setUnitTarget(ID, lastTarget or minPower)`.

**Policy reach.** The implementer is right. `Policy.py:413-417` returns `getattr(module, pieces[2], value)` and never calls it, so a removed method was never usable from a policy. The kept `numCarsAtHome` and `minBatteryLevelAtHome` are `@property` on both TeslaAPI and HomeAssistant, so they really are reachable.

## 3. M1 and M8

**M1 is correct.** `TWCMaster.py:2019-2020` now writes the expiry, then the 0, and a test pins the order.

A residual race remains: the serial thread reads, checks and writes 1 without the lock. It needs the old state to be "0 with a past expiry", which persists for at most one heartbeat after an expiry. The race is negligible.

**M8 is correct.**
- In `HomeAssistant.py`, every log site uses `urlsplit(...).hostname`, the HTTP status, or `type(e).__name__`.
- No `logger.exception`, `exc_info`, `{e}`, URL or token text remains.
- The `RuntimeError(f"... {msg}")` in discovery is logged by type only.
- The token appears only in the session header and the WebSocket auth frame, never in a log.
- In `TeslaBLE.py`, the six listed catch-alls log the type only.

The remaining `{e}` sites in TeslaBLE are at `:658`, `:741`, `:834`, `:849`, `:859`, `:867` and `:881`. They log JSON decode positions, D-Bus errors and pipe-file `OSError`s, which carry a path and no key bytes. That matches the scope of the finding.

## 4. Deleted tests

All four are PLUMBING-ONLY: each tested only the deleted `getSetting`/`setSetting` wrapper.
- `test_get_setting`, `test_get_setting_default` and `test_set_setting` tested a `dict.get` or a dict write.
- `test_set_setting_takes_the_lock_and_get_does_not`: there are no reader or writer wrappers left. Off-thread writers taking the lock is still pinned by `test_off_thread_master_writers_take_the_lock`.

## New issues (all Minor, mode 2 only)

**N1. The held path has no 6 A spike handling.** `TWCSlave.py:948-949`.
- While a rate is unconfirmed, a rising target (T1 to T2 below 16 A) is offered raw. The `else` branch's proactive and reactive spike logic does not run.
- For a car that can never be confirmed, this is mode 1 without the 6 A workaround. If the 2017 firmware bug still exists, the car can sit at about 5.2 A until the next drop. A confirmable car hits this only when the target rises twice within one unconfirmed window (seconds to about 15 s).
- This is undercharging, not a safety problem.
- Fix if seen: when unconfirmed, take the `else` branch's offer logic, minus the lift.

**N2. `wiringMaxAmps` below `spikeAmpsToCancel6ALimit`.** `TWCSlave.py:947`.
- On a small circuit (for example a 12-15 A `wiringMaxAmps` with the default spike of 16), the confirmed raise from T to `wiringMaxAmps` is a raise below the spike, on every target change.
- That is the firmware trigger the notes describe.
- Watch item only.

**N3. Confirmation can be self-referential if `charge_current_request` is capped by the pilot.** `TWCSlave.py:166` (and `known`).
- A reading equal to the desire confirms the rate. If a car reports `chargeCurrentRequest` as min(its setting, the EVSE pilot), a reading taken while the TWC holds T reads T, even if the car is set higher.
- One path: the send failed, or was skipped because the reading already "satisfies" the desire. Then the TWC goes to max and the car draws its real setting until the next reading. That reopens I1 for one reading period: up to 30 minutes on a Fleet-only install.
- The codebase already assumes the reading is not capped: it maps `charger_pilot_current` separately, and mode 3's lift compares against `requestedAmps()`.
- Unverified on hardware. Check it on the live box, which runs mode 1, so the pilot is often below the lifted setting of 32: compare `chargeCurrentRequest` with `charger_pilot_current` in TeslaMate or BLE state.
- If it is capped, confirm only on our delivered write, or on a reading taken while the offer was `wiringMaxAmps`.

**Nit.** The registry guard regex `[^f]\.carApiVehicles` (`test_registry_callers.py:18`) would miss a caller whose receiver name ends in `f`. This is cosmetic.

## I1 risk judgement for a live mode-2 install

Low to moderate. It is safer than BASE and main on wiring, since there is no sustained overshoot. Expect a drop-and-raise to `wiringMaxAmps` on each green target change (up to about 120 an hour, typically 5-60). Per the code's notes this is benign when `wiringMaxAmps >= 16`. Watch for a car stuck near 6 A (N1, N2) and confirm that `chargeCurrentRequest` is not capped by the pilot (N3).
