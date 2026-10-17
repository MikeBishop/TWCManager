# Slim Task 10 report: consolidate the command stack

**Status:** DONE_WITH_CONCERNS
**Branch:** `vehicle-model/phase3` (worktree `scratchpad/wt-vm3`), BASE d98d643
**Commits:**
- 44c4ddb: the main change, with the brief's Step 5 message plus a body.
- 846349b: a fix for a start-stall, found in self-review, that the c4 clause had missed.

## Lib delta

`git diff --shortstat d98d643 -- lib`: 13 files changed, 292 insertions(+), 431 deletions(-). **Net −139** (expected about −200).
Tests: 11 files changed, 411 insertions(+), 240 deletions(-).

| File | Net |
|---|---|
| Reconcile/Run.py | −188 (393 → 205) |
| VehicleCommandQueue.py | −37 |
| Providers/WallConnectorVins.py | −12 |
| Registry/VehicleRegistry.py | −7 |
| Providers/Capability.py | −6 |
| Reconcile/Desired.py | −6 |
| Providers/HomeAssistantProvider.py | −5 |
| Providers/TeslaAPIProviders.py | −3 |
| Order.py, Vehicle.py, Telemetry.py | 0 |
| Reconcile/Rules.py | +20 (`satisfied` and its sets moved here from Reconciler) |
| Reconcile/Reconciler.py | +114 (472 → 577 lines; under the 600 stop rule) |

Why it falls short of −200: the pre-flight estimate counted about 210 lines as moved out of Run.py. Under the ruling, `runAttempt` stays in Run.py, so Run.py keeps about 205 lines. Reconciler.py takes the queue plumbing from `Workers` (about 50 lines: the two queues, start, drain, submit, cancel, `_run`, and report's BaseException normalization and log line). The c2, c4, I4 and gap rules add about 55 lines, comments included. Duplication found and removed along the way:
- `noteOutcome(paid, freeProvider)`: every caller passed complementary values, so `freeProvider` is gone.
- `_standIn` and the new reachedCar scan share one `_newer` helper.
- `Vehicle.reportedBy` is replaced by `Vehicle.reported(field)`, which now has 3 callers.
- `VehicleCommandQueue._running`, `pending()` and `busy` were test-only and are gone.
- `VehicleReconciler.summary` was dead (no caller).

## What changed

- **The reconciler owns the queues.** `VehicleReconciler.__init__` builds `self.ble` and `self.cloud` as `VehicleCommandQueue(run=self._run, key=Run.entryKey, isHigh=Run.isStop, report=..., lost=...)`. The report lambda is late-bound, so a test can replace `r.report`.
  - `submit(attempt)`: local providers run inline and report on the caller's thread.
  - `cancel(key)`: pending stops only.
  - `start()`: both queues, then the thread.
  - `drain(timeout)`: closes both queues, then waits on one deadline.
  - `_run`: wraps `Run.runAttempt(self, attempt)`.
  - `report`: absorbs `Workers._report`. It normalizes a raw BaseException, logs a debug one-shot at INFO and anything else at DEBUG, then calls `noteOutcome` and `wake`.
- **Run.py slimmed.** What remains: `runAttempt(reconciler, attempt)`, `checked`, `_tagged`, `writtenValue`, `entryKey`, `isStop`, `_call`, and `workerOf` (renamed from `_workerOf` because Reconciler uses it; it stays until 13b per M2).
  - `runAttempt` calls `reconciler.beforeWrite/afterWrite` directly, with no hook lookup, no lazy import and no `isinstance`.
  - The stale-desire guard reads `reconciler.desired`.
  - `satisfied` and `VEHICLE_SOURCES_EXCLUDED` now come from Rules.py. Reconciler still re-exports them, so `from ...Reconciler import satisfied` works.
- **Callbacks.**
  - `DesiredStore.changed` is a single callable attribute, called outside the lock, with a raise caught. The reconciler sets `desired.changed = self.wake`.
  - `VehicleRegistry.removed` works the same way. Task 11 wires `registry.removed = desired.forget`.
  - `onChange`, `followRegistry`, `onRemove` and `Workers.setReport` are deleted.
- **VehicleCommandQueue** loses `inline`, `_entries`, `summary`, `pending`, `busy` and `_running`. Legacy mode is untouched.
- **Rate limits deleted:** `RateLimit`, `Declaration.rateLimit`, `FLEET_COMMAND_LIMIT`, `CHARGE_SWITCH_LIMIT`, `WALL_CONNECTOR_VINS`'s limit, and `WallConnectorVinReader._allowed/_calls`.
  - `WallConnectorVinReader.due()` counts a connect edge only once `clock() - lastQuery >= EDGE_MIN_GAP = 30.0`. An edge inside the gap is held, not lost, and fires once 30 s have passed (I7).
- **MIN_SEND_GAP** `= {CHARGE_LIMIT: 10, CHARGING: 10, AMPS: 15}` is enforced in `plan()` against `rec.lastSentAt`.
  - `lastSentAt` survives `newDesire()`.
  - `noteOutcome` now stamps it for every sent outcome (not in NOT_SENT), including a late outcome of a replaced desire (I5).
  - This replaces HA's 10 s start/stop gate.
- **c2.** `reachedCar(vehicle, field, since, beliefAtSend)` scans every non-TWC source's own latest report, as I3 requires. It returns True when any report newer than `since` either comes from `LIVE_READ_SOURCES = {"TeslaBLE", "TeslaAPI", "FleetTelemetryMQTT"}` or has a value different from the one believed at the send. Both the "never reached the car" re-arm and the I2 reopen use it. `newerReading` stays only for the settledAt reopen (it keeps the TWC stand-in).
- **Re-arm cap (I2, I4, M4).** `AttemptRecord.rearmed` is reset in `newDesire()`. It allows one re-arm per desire, triggered by any of:
  - a reading that reached the car;
  - `ride`;
  - for a CHARGE_LIMIT, a charging-like vehicle-source `chargingState` newer than `paidAt`.
- **c4.** `_limitSpent(limit)` means the limit no longer blocks the start. It is True when any of these holds:
  - every provider in `providerOrder.ordered(SET_CHARGE_LIMIT)` (declared, available, unsuppressed, readiness ignored; M11) is excluded. `TeslaBLEProvider.available` is the default True and HA's reads only `enabled()`, so a down radio never counts;
  - `paidSends >= 2 and paidReached`, as at BASE;
  - `paidSends and rearmed and not paidRetryDue`: the one re-arm is used and no blind retry is left (846349b);
  - `lastOutcome.detail` is `"wake refused"` or `"no command token"`.
- **Order.debugCommand** reads `master.reconciler`. It answers False until Task 11 wires it (L35).

## Tests

`test_workers.py` was renamed to `test_reconciler_queues.py` and ported onto `r.submit/cancel/drain` with `inline(r)`. The drain and thread tests keep real (started) queues. `reconcile_helpers.py` gains `InlineQueue`, `inline(reconciler)` and `entries(q)`. The three RateLimits tests are deleted.

Other test files updated: test_limit_reconciler (setup, the rate-limited test deleted, gap and cap updates), test_carapivehicle_registry, test_provider_order, test_outcome_desired, test_provider_tables, test_teslaapi_providers, test_provider_capabilities, test_provider_outcomes_cloud and test_wall_connector_vins.

Behaviour changes in existing tests:
- `test_a_stop_set_while_a_start_is_in_flight...` now asserts that the stop waits the gap (I5).
- `test_paid_sends_that_never_reached_the_car_rearm...` now asserts the once-per-desire cap: no fifth send on the same desire; a new value sends.
- Three tests advance the clock by `MIN_SEND_GAP` between back-to-back sends.

New tests. The paid-count tests are marked "paid". "Red at BASE" was checked by running the block against d98d643 in a throwaway worktree.

| Test | What it pins | Red at BASE |
|---|---|---|
| test_min_send_gap_spaces_a_start_stop_flip_on_any_provider (HA and BLE) | 9 s → 0, 10 s → 1 | yes |
| test_min_send_gap_holds_when_the_flip_lands_while_the_start_is_in_flight | I5 | yes |
| test_amps_gap_is_fifteen_seconds | I6 | yes |
| test_wall_connector_edges_are_spaced_thirty_seconds | I7; live_status counted, only free calls | rewritten |
| **test_ha_republishing_the_limit_every_minute_does_not_rearm_paid_sends** | c2, paid: ≤2 commands over 1 h of HA republish; a TeslaAPI read makes 3; no wake | yes |
| test_a_live_read_followed_by_an_ha_republish_still_rearms | I3 | passes at BASE too (the old rule re-armed on anything) |
| test_a_changed_value_from_a_republishing_source_rearms | c2: a changed TeslaMate value re-arms | passes at BASE too |
| **test_streaming_telemetry_with_fleet_408_is_bounded_per_desire** | I2/U2, paid: ≤4 commands and ≤1 wake over 1 h of Telemetry every 30 s | yes |
| **test_streaming_telemetry_with_fleet_408_on_a_start_is_bounded_per_desire** | I2 for a start, paid: ≤4 paid calls (failed wakes) per desire | yes |
| **test_lowered_limit_reaches_a_car_that_wakes_to_charge_on_teslamate** | I4, paid: 3 commands, no wake, still 3 after 10 more charging readings | yes |
| **test_a_charging_reading_rearms_a_never_reached_limit_once_per_desire** | I4 with Fleet still failing, paid: exactly 4, no wake | yes |
| **test_a_refused_limit_does_not_block_the_start_forever** | c4, paid: 1 setChargeLimit and 1 startCharging over 5 passes | yes |
| test_a_refused_limit_with_a_declared_but_unready_ble_still_blocks_the_start | M11 | passes at BASE (BASE always blocked) |
| test_a_limit_held_unsent_by_a_refusal_does_not_block_the_start | c4: NOT_SENT refusals; "wake held" does not count | new API |
| test_an_unreached_limit_whose_one_rearm_is_spent_no_longer_blocks_the_start | c4 with the cap (see Concern 1) | new API |
| test_no_callback_lists_or_test_modes_in_lib | lib shape | new |
| test_the_store_and_the_registry_each_call_one_callable_outside_their_locks | callbacks | new |
| test_start_starts_both_queues_then_the_thread | start/stop/drain | new |
| test_report_turns_a_raw_base_exception_into_an_error | report normalization | new |
| **test_a_limit_whose_ride_wake_failed_does_not_block_the_start_forever** | c4 with the cap, paid: Fleet-only, asleep. A lower and its retry, then the ride wake fails ("wake 408"), then 1 h of TeslaMate republishing. The start goes with its own wake, ≤6 Fleet calls in all | red before 846349b (stall: 3 calls, no start) |

The I2 streaming test asserts `<= 4` as the brief does. The actual count is 3. The re-arm condition still fires after the first paid send, as at BASE (`rec.paidSends` is truthy at 1), so the one re-arm replaces the blind retry: 1 send, re-arm, 2 sends.

## Suite

`tests --ignore=tests/API --ignore=tests/integration`: **1666 passed, 1 xfailed** (BASE: 1650 passed, 1 xfailed). One pytest warning is reported. It does not come from any touched test file: those run clean under `-W error`.

## Concerns

1. **c4 "exhausted" reading.** The brief says the limit is spent when "its paid sends are exhausted and none reached the car (`paidReached` stays in this test)". BASE's condition is `paidSends >= 2 and paidReached`, and pre-flight says to keep `paidReached` so an unreached limit can still ride the start's wake. I kept that clause and added `paidSends and rearmed and not paidRetryDue`.
   - **Why.** Once the one re-arm is used, nothing but a reached-car reading can revive the limit. On a Fleet+TeslaMate install where the ride wake failed, that reading never comes, so the start would be blocked forever. The cap itself introduces this deadlock.
   - **Test.** The stall was pinned with a failing test before the fix (846349b).
   - **Edge case.** In the rearmed case, a BLE that is declared but unready no longer holds the start (M11 still holds for the unrearmed case).
   - Please confirm this reading.
2. **The re-arm leaves `paidRetryDue` as it was (as at BASE).** A ride re-arm that fires while the blind retry is still pending sends blind, without the start's wake. The ride's wake happens only after the blind retry is spent. I left this alone.
3. **Re-arm timing.** The re-arm can fire after the first paid send (unchanged from BASE). With the cap, it then consumes the flag in place of the blind retry. A desire therefore gets 3 paid sends in that path and 4 in the others, so it never exceeds 4. If the intent is "the re-arm only after both sends", make the condition `rec.paidSends >= 2`. That changes how `ride` wakes after one unreached send (the blind retry never wakes).
4. **The gap stamps any sent outcome, UNSUPPORTED and REFUSED included**, as the brief says. A BLE "no claim" UNSUPPORTED therefore delays the Fleet fallthrough by 10 s. This is harmless, but it is a behaviour change.
5. **Retained Telemetry redelivery** with a different value is still restamped to now (Telemetry.py). Since `FleetTelemetryMQTT` always counts as a live read (U2), a broker reconnect can trigger the one re-arm. It is bounded by the cap, and I did not add a `seen=False` exclusion.
6. **Report normalization in tests.** Tests that replace `r.report` mirror its BaseException normalization in their capture function. `test_report_turns_a_raw_base_exception_into_an_error` covers the real one. A raising `report` is now logged by VehicleCommandQueue's `_logFailure`: the type name at WARNING and the traceback at DEBUG. The ported test asserts only that the WARNING lines carry no secret.
7. **Lib delta −139 against the expected −200.** The reasons are in the table above. Task 13's summary removals (`AttemptRecord.summary`, `DesiredStore.summary` and the rest) are the next lever. They were left for Task 13 as planned.
8. **Task 11 wiring.** TWCMaster must set `registry.removed = desired.forget`, create `VehicleReconciler(master)` (which sets `desired.changed`), call `reconciler.start()` and `reconciler.drain(timeout)`, and give `master.reconciler` to `debugCommand`. There is no `followRegistry` and no `master.workers`.

## Fix round 1 (bba7c4f)

These fixes answer slim-task-10-review.md. Each comes with a regression test, and each test was confirmed red before its fix. The exception is the cap test, which pins a bound that already held.

- **I1: the re-arm clears `paidRetryDue`.** Sends after a re-arm now get the normal wake and read before the write.
  - `test_a_lowered_limit_that_failed_once_rides_the_start_s_wake` (paid counted; the review's sleepy car). Calls: `setChargeLimit, wake, setChargeLimit, wake, startCharging`. The limit ends at 50 before the start.
  - `test_a_rearm_resets_the_blind_retry_and_keeps_the_cap`: still at most 4 commands, and no wake for a lower.
- **I2: c4's "all excluded" now uses `providerOrder.candidates(vehicle, SET_CHARGE_LIMIT)`.** Readiness is the pairing claim. `_limitSpent(vehicle, limit)` takes the vehicle.
  - `test_an_unpaired_ble_does_not_hold_the_start_of_a_car_ha_refused` (paid: one setChargeLimit, one startCharging).
  - The M11 test is rewritten as `test_a_refused_limit_with_a_paired_ble_whose_radio_is_down_still_blocks_the_start`. BLE is paired and answers UNREACHABLE; after 1 h the start is still held.
- **M1: the gap is stamped only when the outcome was sent and `outcome.kind not in EXCLUDING`.** This overrides the brief. I5 is kept.
  - `test_an_unsupported_free_provider_falls_through_without_the_gap`.
  - `test_refused_excludes_the_provider_and_unsupported_falls_through` goes back to "paid at once".
- **M3: the I4 trigger uses `_DRAWING = {"Charging", "Starting"}`.** `CHARGING_LIKE` is private to Rules.py again.
  - `test_a_complete_reading_does_not_rearm_a_lowered_limit` (paid: 2, not re-armed).
- **M4 and M6:**
  - M4: the comments now say "two per arm, two arms per desire" and "at most two more".
  - M6: the VehicleCommandQueue header comment is reflowed.
- **M5: the table arithmetic is corrected.**
  - At 846349b, Reconciler.py was +105 (472 → 577), not +114.
  - Now Reconciler.py is +108 (580 lines), Desired.py is −5 and VehicleCommandQueue.py is −36.
- **M2** is accepted as-is, per the coordinator: a re-arm spent before a start is wanted lets that start charge on the old limit. Record it in the ledger and in Decision 15.

**Lib delta after fix round 1:** `git diff --shortstat d98d643 -- lib`: 299 insertions, 433 deletions, **net −134**. The fix round itself is 23 insertions and 18 deletions, net +5.

**Suite:** 1671 passed, 1 xfailed.

**Remaining concern:** the residual in the M11 rearmed case. Once its one re-arm is used with no blind retry left, the limit no longer holds the start, even when a paired BLE with its radio down could still deliver it later. As the review notes, this is harmless, because BLE sends are free and keep retrying.
