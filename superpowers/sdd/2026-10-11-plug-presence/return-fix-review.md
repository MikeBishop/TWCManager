**Deploy to box now?** Yes. Fix 1 and Fix 2 close the 09:17 race, and I reproduced both the fail-before and the mutation kills myself. Check 3 is correct. The deploy merge is lossless and keeps the slot API form. One Important follow-up (the restore's live read) can go after the deploy, because its exposure is a window only as long as TeslaMate's lag.

Reviewed: presence/3 6c61310..8233d6b, the presence/4 rebase (8f47928 → e987d0a), and the deploy merge 8da7e41. Line numbers are at 8233d6b.

### Findings

**Critical:** none.

**Important**

1. **A restore now skips the live read that used to catch a hand-set limit.**
   - Where: `TeslaBLE.py:891`, through `telemetryChargeLimit` → `latestChargeLimit`, and `TeslaAPI.py:1154`. Fix belongs on **presence/3**.
   - Whenever we hold a limit, our last write *is* `lastApplied`. So for a restore, `latestChargeLimit` returns `lastApplied` whenever the write is newer than the telemetry stamp. `needsLiveRead` is then always False.
   - Before this change, stale telemetry (≠ lastApplied) forced a BLE or API live read. That read already gave the right answer for a restore.
   - So on the restore side, Fix 1 brings no correctness gain. It only saves one read.
   - What it costs: a limit set by hand after our apply but before TeslaMate publishes it is overwritten by the restore. The old code lost a hand-set in the next lag-sized window too (telemetry had caught up to our value but not yet to the hand-set one). So this widens the exposure by one TeslaMate lag; it is not a new class of bug.
   - Not a blocker: it needs an unplug within seconds of a hand change.
   - Suggested follow-up: in the restore path only (`limit == -1`), when `chargeLimitWritten` is newer than `chargeLimitReadAt`, force the live read. In TeslaBLE set `current = None`, so it does the BLE read (cheap, and the car is already woken). In TeslaAPI, `needsLiveRead`/forceLive. Applies keep the written value, which is what fixes the incident.

**Minor**

2. **Telemetry stamps a read only when the value changes** (`Telemetry.py:169`).
   - A hand-set back to the value telemetry last showed, inside TeslaMate's lag, never gets a stamp. The written value then wins until the next live read.
   - On an apply this only causes a redundant send. A restore then sends `outside`, which in practice equals that value.
   - Accept. The replay guard on retained messages is worth keeping.
3. **TeslaBLE's own live read doesn't stamp the CarApiVehicle.** `_readChargeState` (`TeslaBLE.py:1021`) returns a dict and never updates `vehicle.chargeLimit`. That apply uses the fresh read directly, so it is correct; only the next telemetry-path apply could fall back to the written value. Accept, or have `_readChargeState` stamp. presence/3. (`CarApiVehicle.update_charge`'s BLE branch does write the attribute and stamp it.)
4. **A telemetry or API response sampled before our write but received after it is stamped as newer**, because stamps are receipt time, not sample time. This is inherent: TeslaMate gives no sample time. The change-only stamping mostly masks it. Accept.
5. **Test gap: no channel-level test of a restore where a hand-set arrives after our write.** Telemetry changes after the write, so the read should win and give "set by hand; nothing to restore". The rule-level `test_read_after_the_write_wins` covers the logic.
   - Related: the channel tests stamp through their own `TelemetryVehicle.publish()` and bypass `Telemetry.applyDataToVehicle`. So mutation A (dropping the real telemetry stamp) is caught only by the mapping unit test.
   - A channel test that publishes through `applyDataToVehicle` after the write would cover both gaps. presence/3, optional.
6. **The brief's "one pass" is really two back-to-back passes.**
   - `_applyEvidence` → `_record` sets `_wake`, so the plug observation is applied in an immediate second pass (`VehiclePresence.py:524-527`).
   - The 09:17:35 log (restore queued, then the arrival, in the same second) matches that.
   - The fix's comment "on the next pass" is accurate, and the arrival is not delayed in the live thread.
   - The scenario test's `step()` and the unit test's explicit second `runPass()` model this correctly.

### Check-by-check

**1. Fix 1**
- **One shared rule.** `ChargeLimitRules.latestChargeLimit` (`:171`) is the only rule. TeslaBLE reaches it through `telemetryChargeLimit`; TeslaAPI calls it directly.
- **Read-before-write sites.** There is one per channel, shared by apply and restore:
  - TeslaBLE `:891`
  - TeslaAPI `:1149-1154`
- **Write sites.** The only charge-limit writes in `lib/` are TeslaBLE `charging-set-limit` (`:973`) and `CarApiVehicle.apply_charge_limit` (TeslaAPI `:1210`). Each records the write only on success. A failed write records nothing (verified in code). TeslaAPI's forceLive re-read is used raw, which is correct because it is a newer stamped read.
- **Read stamps.** Reads are stamped in three places: Telemetry (on change), `update_vehicle_data` (only when `charge_limit_soc` is present), and the BLE branch of `update_charge`.
- **Hand change after our write.** Newer telemetry wins (`readAt >= writtenAt`).
- **Restart.** The records are in memory, so after a restart the old behaviour returns. That is acceptable: the exposure needs a restart between a restore and the next apply.
- **Thread safety.** Each attribute is a single atomic assignment, made by a different thread: `chargeLimitWritten` by the command worker, `chargeLimitReadAt` by MQTT/API. The only interleaving lets a just-arrived read win, which is the right result.

**2.** See Important #1 above and the concern adjudication below.

**3. Fix 2**
- `_reconcileDeparting` (`:1322`) and `_sweepHeld` both skip a car this pass's probe read plugged in from a strong source.
- The next pass applies the plug observation *before* the sweep, so the car is HOME and the sweep ignores it.
- `_goHome` drops `_departing`. `onArrival` calls `_cancelRestore` (`PresenceHandlers.py:37,68`), which runs `queue.cancel` and drops a pending restore but not a running one (`VehicleCommandQueue.py:cancel`). The arrival apply shares the key `(applyChargeLimit, vin)`, so `put` would also overwrite a pending restore. A running task is out of the table, so the apply queues behind it.
- A running restore completes, and then the arrival apply reads through Fix 1. The second scenario covers this by running the worker by hand.
- **Replay fidelity.** It is faithful: ble_only, a VIN-reading TWC, TeslaMate live, the BLE restore failing, BLE gone more than 300 s, no remote route, and a single departing probe returning reach plus a BLE plug. On the old code it reproduces the live log exactly: `bleLimits == ['80']`, then "already at 50; nothing sent". Its outside limit is 80 where the box's was 100, which doesn't matter.

**4. Check 3**
- **The car the TWC names now gets the rate.** `_chargeRateVehicle` (`TWCSlave.py:313`) returns the CarApiVehicle, or else the bare VIN.
- **The bare VIN works on every path:**
  - The queue's `_key` uses `getattr(vehicle,"VIN",vehicle)`, so an object and a VIN coalesce.
  - `TeslaBLE.sendCommand` accepts either.
  - `TeslaAPI.setChargeRate` resolves the VIN, or returns False with no POST.
- **On the box.** ble_only skips TeslaAPI for `setChargeRate`, so BLE receives the VIN.
- **No broadcast widening.** `_broadcastTargets` and `broadcastVINs` are untouched; the fix moves this case off the broadcast path entirely.
- **plugVIN/attributed ahead of lastVIN.** This is correct. When a different car is plugged in and hasn't started charging, the old code sent the rate to the previous session's car.

**5. Deploy merge 8da7e41**
- Every conflict hunk keeps the slot form: the `urllib3` import, no `jwt` (now used only in TeslaTokenSlot), no `baseURL`, `slot.verifyCert`, and `fleet_token()` in the test.
- The new ChargeLimitRules import list is taken.
- The `+/-` lines of `git diff 1d4258b 8da7e41` are byte-identical to `git diff 6c61310 8233d6b`.
- `git range-diff` shows all 13 presence/4 commits as `=` after the rebase. Nothing was lost from either side.

### Concern adjudication (implementer's 1–5)

1. **Restore trusts our write.**
   - It is a real but narrow regression. It adds one TeslaMate lag of exposure to a hand-set made right before an unplug.
   - Not a deploy blocker. Fix it as a follow-up by forcing the live read on restores when our write is newer than the read (Important #1); BLE makes that read cheap.
2. **In-memory records.** Acceptable. A restart falls back to the old behaviour.
3. **A changed replay counts as new.** It is pre-existing and not widened. TeslaBLE's own `_readChargeState` doesn't write `vehicle.chargeLimit`. Only `update_charge`'s BLE branch and API reads do, so the trigger is rare. Accept.
4. **`pluggedHere` covers only this pass.** Acceptable: arrival cancels a pending restore, and Fix 1 makes a running one safe.
5. **Check 3 behaviour change.** Correct and intended (see check 4).

### Mutation checks

Each was run on a `git archive` copy of 8da7e41, using only the focused test files.

**Fix 1, mutation A:** removed `noteChargeLimitRead(vehicle)` in `Telemetry.applyDataToVehicle`.
- Killed by `test_telemetry_mapping.py::test_a_new_charge_limit_is_stamped_as_read_and_a_replay_is_not`.
- 1 failed / 383 passed. Only that unit test catches it: the channel tests stamp through their own fake.

**Fix 1, mutation B:** removed `noteChargeLimitWriteFor(...)` in TeslaBLE. Killed by:
- `test_teslable_presence.py::TestOwnWriteSupersedesOlderTelemetry::test_apply_after_our_restore_sends_despite_older_telemetry`
- `test_plug_presence_scenarios.py::test_2026_10_12_arrival_during_a_running_restore_ends_at_the_policy_limit`

**Fix 2:** replaced the `elif reachable and self._pluggedHereEvidence(evidence)` branch in `_reconcileDeparting` with `elif False`, keeping the sweep skip. Killed by:
- `test_2026_10_12_return_plugged_in_keeps_the_policy_limit`
- `TestReturnPluggedInWinsOverTheRestore::test_a_plugged_in_probe_queues_no_restore_and_the_arrival_follows`

**Fix 2, fail-before:** the 8233d6b test files on the 6c61310 lib.
- Both 2026-10-12 scenarios and the unit test fail (3 failed, 1 passed). The fast-charger test passes, as expected.
- The replay fails with `assert '80' not in ['80']`.

**Focused green run on 8da7e41:** 491 passed, across the scenarios, charge_limit_rules, teslable/teslaapi presence, twcslave, vehicle_presence, telemetry_mapping and teslaapi_chargerate.
