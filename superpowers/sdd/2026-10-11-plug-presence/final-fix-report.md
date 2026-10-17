# Final-review fix round (plug presence): report

Worktree: `scratchpad/wt-plug`. Nothing pushed, no `git stash`, no other branches touched. Interpreter: `<PY>` from the global constraints.

## Branch tips

| Branch | Before | After | Full suite |
|---|---|---|---|
| presence/3-plug-presence | 3e20776 | **6c61310** | 1125 passed |
| presence/4-fleet-rate-queue (rebased onto the new presence/3) | 14ae080 | **8f47928** | 1183 passed |
| deploy/presence-3 | cce331f | **1d4258b** (second merge; first was b637a6e) | 1353 passed |

## presence/3-plug-presence commits

1. **8c11dea Carried back the cce331f test edits.**
   - `test_teslable_presence`: the car is ready, readable and at 80%. Uses `carApiBearerToken = "token"`; `readOnly` defaults to False on this branch, so commands can be sent.
   - `test_teslaapi_presence`: added `test_presumed_car_with_no_location_fix_is_woken`.
   - `test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing`: the policy moves to 60% while the car holds 50%.
   - **Mutation check.** I changed `TeslaAPI.applyChargeLimit`'s `if vin is None and not vehicle.atHome:` to `if False:`.
     - The scenario test and the teslable test now fail.
     - Their pre-change versions still **pass** under the same mutation, so before this commit they did not catch it.
     - Three older tests also fail under the mutation.

2. **0c0369a M1.** `_startDeparting` no longer probes inline; it nominates the first BLE-only probe at +`DEPARTING_PROBE_INTERVAL`.
   - Fail-before: `test_unplug_with_a_held_limit_starts_a_departing_record` (now `probes == []`, then `[60]`) failed with `[0.0] == []`.
   - Side effect: BLE is first found gone at +60, so the BLE window closes at about 360 s after unplug instead of 300 s. The timing tests moved with it. I did not backdate `bleGoneSince`.

3. **d5ef369 I1, built to the user's reconciliation design (not a retry counter).**
   - **The state is the saved limits.** A car not home on evidence with `lastApplied != -1` needs a restore. A failed restore leaves the limit held, so the next pass finds it again.
   - **BLE window.** A `DepartingRecord` now exists only for BLE cars and only covers the BLE-first window. `viaBle` is removed; `fallbackSent` became `bleWindowOver`. During the window the car is restored over BLE, probed, and retried while in range. When BLE has been gone 300 s the window closes. It sends nothing itself; slow BLE probes and BLE retries continue after that.
   - **Remote route.** `_sweepHeld` owns every remote restore (one code path). It runs at the end of every pass, so a non-BLE car is tried in its unplug pass. `onDeparting` therefore no longer queues a remote restore for a non-BLE car; it returns False.
   - **When a remote attempt happens.** `_remoteRestoreIfDue` skips if a restore is already queued or running (same queue key, never queued twice), and skips until the backoff time has passed. Then it calls `onDeparture` → `_remoteRestore`, the normal path, where `hasRemoteChannel`/commandPolicy decide whether anything is sent.
   - **Backoff.** Per VIN, in memory: 600 → 1200 → 2400 → 3600 s cap (`REMOTE_RESTORE_MAX_DELAY`). Only an attempt moves it. It is dropped when the limit is no longer held, and in `_goHome` (arrival or plug-in).
   - No zero-delay loop: every attempt sets the next time at least 600 s ahead, and the sweep runs once per pass (the thread wakes every 60 s while a car is NOT_HOME).
   - **Tests: new `TestRemoteRestoreBackoff`.**
     - Non-BLE schedule: `[0, 600, 1800, 4200, 7800, 11400]`.
     - BLE car: `[360, 960, 2160, 4560]`.
     - A success stops the retries.
     - A queued restore is not re-queued, and a skip does not advance the backoff.
     - Arrival cancels the retry and resets the backoff.
     - A held limit at startup for a car not home is tried on the first pass (non-BLE car; a BLE car gets the BLE restore on pass 1, as before).
     - Inside the BLE window there is no remote attempt.
     - Under ble_only, the real `departureHandler` is asked at 0/600/1800 and nothing is ever queued.
     - New scenario: `test_fleet_only_failed_remote_restore_is_retried_after_600_s` (FakeFleet got a `failCommands` 500 knob).
   - Fail-before: 8 of these tests fail on the pre-I1 code; the window-guard test passes on both versions.
   - The header comment, the `departingHandler` and `departureHandler` comments, and the `_remoteRestore` "dropped, not replayed" comment are rewritten.

4. **952b1e3 M2.**
   - `observeProof(vin, source, twc=None)`. `recordVehicleVIN` passes `slaveTWC._presenceKey()`.
   - `_applyProof` **drops** (does not replace) that TWC's `_twcVin` entry when it names a different VIN.
   - Tests: `test_proof_drops_a_wrong_attribution_on_the_same_twc` and `test_proof_keeps_a_matching_attribution_and_other_twcs`. `test_twcmaster` now asserts `twc="1234"`.
   - Fail-before: TypeError on the unknown keyword, and the twcmaster call did not match.

5. **6c61310 M7.** Rewrote the TeslaBLE comment that still said "DEPARTING or NOT_HOME". The PresenceHandlers "once" comment was already rewritten in the I1 commit. Comment-only, no test.

## presence/4-fleet-rate-queue

I rebased it with `git rebase --onto presence/3-plug-presence 3e20776`; there were no conflicts, and the suite passed (1172) before the new commits.

6. **cabdafb I2.**
   - **bleSilent rule.** It now needs at least 2 failed probes since the last success, at least `PROBE_INTERVAL` apart. The existing "no success within `BLE_REACH_MAX_AGE`" condition still applies. New state: `_reachFail[vin] = (first, count)`, reset on success.
   - **Recheck.** When a failed probe is applied for a HOME car that BLE applies to and that is not TWC-named or attributed, a **BLE-only** recheck is scheduled:
     - +60 s after the first failure (to confirm), then every 600 s while it stays silent;
     - counted from the failed probe's time;
     - written straight into `_due` under the lock, so it can be dropped with its due time;
     - one pending at a time;
     - dropped on a success, when the car leaves, or when it is attributed to a TWC.
   - The due loop runs that probe with `bleOnly=True` (`body-controller-state`, no wake, no telemetry or API).
   - `bleReachable` and `broadcastVINs` are unchanged.
   - **Tests.** The controller tests now record two spaced failures (`ble_silent()` helper).
     - New controller tests: `test_one_failed_probe_on_arrival_lists_no_fleet_evse` (one failure: no EVSE; the second: EVSE; a later success: gone), close-together failures are not silent, and a success between failures restarts the count.
     - New `TestBleSilentRecheck`: probes at `[60, 660, 1260, 1860]`, BLE only; a success ends the rechecks; none without BLE; none for an attributed car; they stop on leave; one chain.
   - Fail-before: 7 tests failed before the change. The two "no recheck" tests are guards and pass on both versions.

7. **64b7d58 commandPolicy gate (see the finding below).** `TeslaAPIEVSE.setTargetPower` queues nothing under `ble_only`; the policy is read the way `update_charge` reads it, falling back to `prefer_ble`.
   - Test: `test_ble_only_command_policy_queues_no_fleet_rate` (ble_only: nothing queued; prefer_ble: queued). It failed before the change.

8. **8f47928 I2 follow-up (from the advisor's done-check).** `_reachFail` was never cleared on departure. A car that was BLE-silent on its last visit therefore came back already counted silent and got a Fleet EVSE before any new probe ran. `_setHome(False)` now drops it.
   - Test: `test_failures_from_an_earlier_visit_do_not_count_after_a_return`. It failed before the fix (`bleSilent` True straight after the return).

## commandPolicy / Fleet EVSE finding

**Before this round, the Fleet EVSE rate path bypassed `commandPolicy: ble_only`.**
- `TeslaAPIEVSE.setTargetPower` queues `fleetSetChargeRate`.
- `VehicleCommandQueue._DISPATCH["fleetSetChargeRate"]` calls `task["module"].setChargeRate` directly (it is in `_OWN_MODULE` and never goes through VehiclePriority).
- `TeslaAPI.setChargeRate` checks only `refuseCommandIfReadOnly`.
- With a Fleet command slot and `ble_only` (the live box), any listed TeslaAPIEVSE would therefore have sent billed `set_charging_amps`.
- Fixed with the one-conditional gate in commit 64b7d58.
- Not changed: under ble_only the EVSE is still listed and still takes a distributor power share; that share just isn't sent.

## deploy/presence-3 merge (b637a6e)

**Why the merge conflicted.** deploy/presence-3 already contained the pre-rebase presence/4 (14ae080). `git merge --no-ff presence/4-fleet-rate-queue` therefore produced add/add and content conflicts in TeslaAPI.py, VehiclePresence.py and four test files.

**How I resolved it.** I set the tree to the deploy side, then applied the net change `14ae080..presence/4-fleet-rate-queue` with `git apply --3way`. The one conflict, the `test_teslable_presence` token line, kept the slot-API form (`api.storeToken(fleet_token())`).

**Checks.**
- `git diff 14ae080 cce331f -- lib` and `git diff presence/4 b637a6e -- lib` match apart from hunk line numbers, so the deploy-only delta (token slots) is unchanged on top of the fixed presence code.
- Black: the 5 touched lib files are clean. Test files that weren't black-clean before (test_twcmaster, test_teslaapi_presence, test_teslable_presence) were not reformatted.
- Token-in-log: `git diff presence/4-fleet-rate-queue -- lib | grep -nE '^\+.*log.*(oken|Bearer)'` gives the same 8 token-slot hits Task 13 recorded, none of which interpolates a token. The fix round's own lib diff gives 0.

**Second merge (1d4258b).** After the follow-up commit 8f47928, a second `git merge --no-ff presence/4-fleet-rate-queue` went in cleanly as a one-commit merge. The suite gives 1353 passed, and the token grep still shows the same 8 hits.

Black-before check: test_teslaapi_controller, test_teslaapi_evse and test_vehicle_presence were black-clean at 8152165, so running black on them was within the constraint.

## Concerns

- **ble_only log noise (the live box).** For a BLE car not home with a held limit, once its BLE window closes the remote route asks `departureHandler` on the backoff (about 6 min, 16 min, 36 min, then hourly). Each time `_remoteRestore` logs one INFO line, "no remote command channel can restore its normal charge limit…". That is one line an hour per away car with a held limit; the sweep's own retry line is DEBUG. If that is too loud, demote repeats in `_remoteRestore`.
- **A remote restore to an asleep car still fails.** `needToWake` is False for `limit == -1`, so `update_charge` fails and nothing is sent. The backoff now retries until the car wakes on its own (driving or at a stop), but it never wakes the car. That is by design (no wake just to restore), but it means "retried" is not "guaranteed while asleep".
- **BLE retry and remote in the same pass.** After the window closes, a reachable probe's BLE retry queues first and the sweep sees it queued and skips. If the worker drains and fails that BLE restore between the due loop and the sweep, both can be queued. They share the queue key `(applyChargeLimit, vin)`, so they coalesce and nothing is sent twice.
- **Box-visible timing changes.** The first departing probe is at +60 s (M1), so the BLE window closes at about 360 s. A non-BLE car's remote restore now comes from the sweep in the same pass as the unplug, not from `onDeparting`.
- **The bleSilent recheck holds the BLE lock.** It is a BLE probe every 10 minutes for a HOME car that BLE can't reach (for example on a UMC out of range), and each one can hold `_bleLock` for up to `presenceProbeTimeout`.
- **`_resetLimitState` now runs on every backoff attempt.** `_remoteRestore` calls it before the `remoteChannel()` check, so under ble_only each attempt resets the per-VIN dedupe flags of a NOT_HOME car. That used to happen once and now happens on the backoff schedule. It is harmless: both policy-wide applies skip NOT_HOME cars, and `onArrival` resets again.
- The fix-round commits are separate; the review expects them to be squashed into their tasks before PRs.
