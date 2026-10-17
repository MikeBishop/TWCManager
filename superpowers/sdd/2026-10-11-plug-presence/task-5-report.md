# Task 5 report: departure restore as a reconciler (+ Task 4 review fixes)

Worktree: `scratchpad/wt-plug`, branch `presence/3-plug-presence`, base a0fbb5d.

## Commits
- `9219183` Keep VIN-less TWC attribution in step with the plug session (Task 4 review fixes 1-3)
- `f4d6837` Restore on unplug over BLE, then remotely once BLE has been gone 5 min (Task 5)

## Implemented
### Task 4 fixes (VehiclePresence.py)
1. `_applyUnplug` (named VIN): pops `_twcVin[twc]` once the unplug is accepted (after the live-telemetry ignore), so a wrong pre-VIN attribution ends with the plug session.
2. `_vinLessUnplug` single candidate: records `PlugRecord(False, "twc", at)` before `_leave`, like the named path.
3. `_vinLessUnplug` attributed target: after `_applyUnplug`, if the target is still not NOT_HOME (live telemetry kept it), `_twcVin[twc] = target` is re-inserted.

### Task 5
- `PresenceHandlers.bleApplies(master, vin)` (moved from `VehiclePresence._defaultBleApplies`, which now delegates).
- `departingHandler(master, remoteChannel=None)`: nothing held -> False; `bleApplies` -> localOnly restore; else the remote restore now (`remoteOnly` if `hasRemoteChannel`). Remote body factored into `_remoteRestore(...)`, shared with `departureHandler` (unchanged behaviour, still resets limit state first). The `unambiguous=False` branch is kept, untested as directed.
- `arrivalHandler`: first cancels pending `applyChargeLimit` with `vin == vin and limit == -1` via `master.vehicleCommandQueue.cancel` (guarded), also before the policy-not-evaluated early return.
- `VehicleCommandQueue.queued(cmd, match) -> bool`: pending or *running* entry matches (new `_running` field set in `_next`, cleared in the worker's finally).
- `VehiclePresence`:
  - Constants `DEPARTING_PROBE_INTERVAL=60`, `DEPARTING_PROBE_CAP=1800`, `DEPARTING_SLOW_PROBE_INTERVAL=600`, `BLE_GONE_RESTORE_AFTER=300`.
  - `DepartingRecord(since, viaBle, bleGoneSince=None, fallbackSent=False)`; `_departing` dict.
  - `_restorePending(vin)` (swallows errors -> False, so a bare `Mock()` master creates no records), injectable `restoreQueued` (default: `vehicleCommandQueue.queued(...)`; on error assumes queued).
  - After `onDeparting` runs for a NOT_HOME car, `_startDeparting`: if still held, create the record; a BLE car is probed (BLE only) immediately.
  - Follow-up probes go through `_due` via `nominate(vin, "departing", delays=(d,))`; the due loop probes a departing car BLE-only (while viaBle and no fallback sent) and skips the probe and ends the record if the limit is no longer held. `_reconcileDeparting`: reach True clears `bleGoneSince` and retries the localOnly restore (re-running `onDeparting`) if `restoreQueued` is False; reach not True sets `bleGoneSince`; at `now - bleGoneSince >= 300` sends one `onDeparture(vin, None)` (new `_runDeparture` wrapper) and sets `fallbackSent` (no more probing). Next delay is 60, or 600 once `now - since >= 1800`, capped at the fallback time.
  - `_goHome` pops the record (onArrival cancels the pending restore).
  - Header comment describes the reconciler.

## Tests (TDD)
- RED: Task-4 fix tests (3 failed); handler tests (ImportError `bleApplies`); queue tests (2 failed, no `queued`); tracker tests (ImportError `DepartingRecord`). Then GREEN. A mutation check (disable retry / slow interval) made the retry and cap tests fail.
- Added: handlers `test_departing_ble_car_queues_one_local_restore`, `..._non_ble_car_queues_one_remote_restore_now`, `..._non_ble_car_without_remote_channel_queues_nothing`, `test_departing_with_nothing_held_queues_nothing` (BLE x non-BLE x two saved shapes), `TestBleApplies`, `test_arrival_cancels_a_pending_restore_first`, `test_cancels_even_before_the_first_policy_evaluation`; queue `TestQueued` (pending, running); tracker `TestDepartingRestore` (record created / not, 5-min fallback, fallback needs remote channel with real `departureHandler`, restore done stops probing, replug cancels, reachable resets the gone timer, slow after the cap, non-BLE never probed, failed BLE restore retried, no retry while gone), `TestDiscoveryWithAHeldLimit` (held -> restore; nothing held -> nothing), rewritten `TestDepartAndReturnThroughTheQueue` (real handlers + real queue: unplug -> localOnly restore pending -> TWC proof -> only the 50% apply runs), three Task-4 fix tests, constants.
- Existing `TestDeparting` tests now pass `ble=True` to `make_master` (BLE path needs TeslaBLE + bleProven).
- Advisor review found the 5-min fallback could stall under a real clock: slow (failed) BLE probes drift the cadence so the capped fallback due time lands inside the 60 s PROBE_INTERVAL rate limit, is skipped and consumed, and nothing re-nominates. Added `test_slow_failing_probes_still_reach_the_fallback` (5 s per probe) -> RED; fixed by exempting an active departing (BLE-only) probe from the ordinary rate limit (its own cadence is the limit) and timing the reconcile from just before the probe -> GREEN. Amended into the Task 5 commit.
- Full suite: 1023 passed (was 994).

## Files
- lib/TWCManager/VehiclePresence.py, lib/TWCManager/PresenceHandlers.py, lib/TWCManager/VehicleCommandQueue.py
- tests/unit/test_vehicle_presence.py, tests/unit/test_presence_handlers.py, tests/unit/test_vehicle_command_queue.py
- Black run on touched files except test_vehicle_command_queue.py (was not black-clean; the new hunk is black-style).

## Self-review / concerns
- `VehicleCommandQueue.py` was touched (new read-only `queued()` + `_running`) on branch 3; global constraints say branch 1 stays unchanged, and that is still true (the change is on branch 3), but it's a queue-file edit the user should see.
- Records start only on the home -> not-home transition (after `onDeparting`). A limit that becomes held while the car is already not home (e.g. an arrival apply still running in the worker when the car unplugs and finishing after the unplug check) is not picked up: no sweep re-checks NOT_HOME cars without a record. Probably rare; a per-pass sweep would close it.
- A non-BLE record (`viaBle` False) is never probed or pruned until the car is home again; it holds no timers, so it only costs a dict entry.
- After the fallback the record stays (`fallbackSent`) until the car comes home: no further retries over BLE even if the car later comes back into BLE range without plugging in. A remote restore that failed is not retried (the existing `departureHandler` rule).
- When the departing due fires and the limit is no longer held, the probe is skipped; if another nomination for that VIN coincided in the same pass, its probe is skipped too (rare; NOT_HOME cars are rarely nominated otherwise).
- A leftover departing due time after a replug becomes one ordinary (sleep-safe) probe of the now-HOME car.
- A departing probe whose BLE source returns nothing (`reach` None: TeslaBLE unloaded or the VIN left `Vehicles` mid-departure) counts as BLE gone, so it leads to the remote fallback after 5 min. Deliberate: BLE can't restore then either.
- Slow-mode spacing with BLE gone: the fallback due time is scheduled exactly, so it isn't delayed by the 600 s interval.

## Fix round 1 (review task-5-review.md, I1 + I2) — commit `80a5b03`

- **I1 (retry after the fallback):** `_reconcileDeparting` no longer stops at `fallbackSent`. The fallback fires once (`fallbackSent` stays unconditional, whether or not a remote channel could send it); afterwards a car whose limit is still held keeps BLE-only probes every `DEPARTING_SLOW_PROBE_INTERVAL` (no clamp toward the fallback time), and a reachable probe re-queues the localOnly restore if `restoreQueued` is False. The due loop probes a departing car BLE-only whenever `viaBle` (not only before the fallback).
- **I2 (sweep):** `_sweepHeld(now)` runs at the end of every pass: VINs with `_home[vin] is False` (NOT_HOME on evidence; presumed and home cars are excluded) and no `_departing` record are checked with `_restorePending`. If the limit is held, the pass runs `_runDeparting` and then `_startDeparting`, which starts the normal BLE-now / retry / fallback flow. `_timeUntilNextDue` caps the wait at `DEPARTING_PROBE_INTERVAL` while any car is not home on evidence, so the sweep runs without an event.
- Tests (RED 5, then GREEN):
  - Changed `test_ble_gone_for_five_minutes_sends_one_remote_restore`: probes after the fallback are spaced >= the slow interval.
  - New `test_after_the_fallback_a_reachable_probe_retries_over_ble`: exactly one remote restore, then a BLE retry, with none while that retry is queued.
  - New `test_ble_only_fallback_sends_nothing_then_ble_retries`: real handlers under `ble_only`. Nothing is sent remotely; a later reachable probe re-queues localOnly.
  - New `TestHeldWhileNotHome`:
    - a limit held after the car left gets one restore and a record, and later passes don't re-send it;
    - presumed and home cars with a held limit are untouched;
    - a not-home car with nothing held is untouched;
    - the thread wakes to run the sweep.
- Full suite: 1029 passed. Black is clean on touched files.
- New concern: while any car is not home on evidence (usually the case), the thread runs a pass at least every 60 s. Each pass reads `getNormalChargeLimit` once per not-home car that has no record, which is a settings dict lookup.
