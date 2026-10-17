# Pre-flight r4: slim plan Tasks 10, 11, 12a, 12b, 13a, 13b, 13c, 13, 14

Reviewed against `vehicle-model/phase3` at **d98d643** (worktree `scratchpad/wt-vm3`), lib total 30,246 lines. Read-only. Line numbers are at d98d643 unless marked "plan:".

Two user decisions (2026-10-15, from the coordinator) override the plan text and are checked here:
- **U1 (Task 11).** A numeric-ID held limit that TeslaAPI's first vehicle list never matches is **dropped after one warning**. It does not stay in `chargeLimits`.
- **U2 (Task 10, c2).** A Fleet Telemetry reading **always** re-arms paid sends, as BLE and TeslaAPI reads do. A HomeAssistant or TeslaMate reading re-arms only when its value changed.

Counts: **Critical 1, Important 10, Minor 11.**

---

## 1. Interface and consistency tables

### Task pairs (shared files or interfaces)

| Pair | Producer gives | Consumer takes | Conflict |
|---|---|---|---|
| 10 → 11 | `VehicleReconciler.submit/cancel/start/stop/drain`, `store.changed`, `registry.removed` | TWCMaster wiring, TWCManager start and shutdown | Stale names only. Task 11 Files still lists TWCMaster `workers`, its test is `test_master_wires_store_workers_and_reconciler...`, and it still calls `followRegistry`, which Task 10 turns into an assignment. Ledger L35 names `..._through_the_master_workers` (plan:948); Task 11 names `..._through_the_master_reconciler` (plan:580). **M3** |
| 10 → 12a | `cancel(key)`: pending stops only (Run.py:365-371). `MIN_SEND_GAP` on `rec.lastSentAt` | `cancelStopCarsCharging`, the start/stop flip | `lastSentAt` is stamped only for current-desire outcomes (Desired.py:367-368). A start that is in flight when the desire flips is never stamped, so the stop goes out at once. **I5** |
| 10 → 12b | `MIN_SEND_GAP = 10 s` per car and aspect | Stateless amps from the heartbeat and the distributor | Main paces Fleet rates at 15 s (TWCSlave.py:885-901). 10 s allows 1.5× the paid `set_charging_amps`. **I6** |
| 10 → 13b | Task 10 deletes `_workerOf`'s indirection | `runAttempt`'s read-before-write filters read sources by worker (Run.py:204-210) until 13b | Task 10 still needs a worker-of-source lookup. **M2** |
| 10 → 13 | Task 10 deletes `VehicleCommandQueue.summary` | Task 13 also lists it | Harmless duplicate |
| 10 → 14 | `InlineQueue`, `inline(r)` in `reconcile_helpers.py` | Task 14's parity tests | None |
| 11 → 12a | `Targets.targetsFor/presentVehicles` | `startCarsCharging/stopCarsCharging` | None in the interface. **The TeslaAPI vehicle list stops loading after 11 + 12a. C1** |
| 11 → 13c | `heldLimits.resolveLegacyIds` is called from TeslaAPI's first successful vehicle list (`loadVehicleList`) | 13c rewrites `loadVehicleList` onto `_request` | 13c must keep that call. Neither task says so. **M6** |
| 12a → 12b | Deletes `TeslaBLE._allVehicleTargets` | `TeslaBLE.setChargeRate` (TeslaBLE.py:772) still calls it until 12b | AttributeError and a red suite. **I1** |
| 12a → 12b/13 | Deletes HA `car_api_charge` and `applyChargeLimit` (the latter in 11) | HA `_vehiclesFor` (HomeAssistant.py:607) has no caller after 12a | Not on any delete list. **M7** |
| 12b → 13 | Deletes `TeslaBLE._stampWrite` and VehiclePriority | Task 13 lists `_stampWrite` again; its grep covers `VehiclePriority` | Duplicate only |
| 13a → 13 | Deletes the BLE helpers dead on main | Task 13's changelog line | None |
| 13b → 13 | Reads walk `ordered(READ_CHARGE)` | Task 13 deletes `READ_LIST/ONLINE/PLUG/VIN/AMPS/LOCATION` and keeps `READ_CHARGE` and `READ_WALL_CONNECTOR_VINS` | None. Gen3 cloud VIN keeps its capability |
| 13c ↔ Gen3 | One classifier | The energy path, where a 403 retires Wall Connector reads only (TeslaAPI.py:1374-1376) | A uniform "403 refuses purpose" is fine only if purpose is `"energy"`. **M6** |

### Self-consistency per task

| Task | Do its tests, code and files agree? |
|---|---|
| 10 | **No.** (a) The test list names only `test_workers.py` and `reconcile_helpers.py`. `Workers` is also imported at test_carapivehicle_registry.py:135, test_provider_order.py:122 and test_limit_reconciler.py:8. Rate-limit assertions sit in test_wall_connector_vins.py:153/167/216/322, test_provider_tables.py and test_teslaapi_providers.py (**M1**). (b) "`WallConnectorVinReader` … its own `interval()/due()` already paces it" is false. `due()` returns True on every connect edge (WallConnectorVins.py:91-94), and `test_rate_limit_is_respected` (test_wall_connector_vins.py:153) fails without `_allowed` (**I7**). (c) The 600-line stop rule will trip (**I8**). (d) The c2 text does not account for U2 (**I2**) |
| 11 | **No.** Its text keeps unmatched numeric IDs in `chargeLimits` (plan:547), which U1 reverses (**I9**). The c6 carry sits under "Delete". Files list `workers` (**M3**) |
| 12a | **No.** `_allVehicleTargets` (**I1**). Review Focus 1, 3 and 4 and the ledger attribute its tests to Task 11 (plan:45-48, 950, 963) (**M3**). It removes the last vehicle-list loader (**C1**) |
| 12b | Mostly yes. `TeslaAPI.wakeVehicle` is uncalled after 12a, so "if uncalled" holds. `_vehiclesFor` is missed (**M7**) |
| 13a | Mostly yes. The breaker test is in test_provider_outcomes_local.py:102, not in `test_teslable_*`. `maxRetries` and `retryDelay` also appear in test_provider_outcomes_local.py, test_teslable_pairing_status.py and test_teslable_lock.py (**M5**) |
| 13b | Yes |
| 13c | **No.** "Every existing 401/403/410/412/429 test passes unchanged" conflicts with one uniform 4×6 table. The vehicle list deliberately does not retry after a 401 (TeslaAPI.py:407-410), and the energy path's 403 differs (**M6**) |
| 13 | **No.** The grep asserts `"def summary"` == [] while keeping `Vehicle.summary` (Registry/Vehicle.py:249), so the test can never pass. The summary deletions also break test_outcome_desired.py:51/147, test_provider_capabilities.py:51 and test_provider_outcomes_local.py:34, none of which are listed (**I10**) |
| 14 | Yes. Row 18 matches Task 10's rename. Rows 9, 10 and 16 follow c2 and `MIN_SEND_GAP`. Add a row for U2 (Fleet Telemetry streaming while Fleet answers 408) (**I2**) |

---

## 2. Symbols to delete: do they exist, and does anything still call them?

Every named symbol exists at d98d643 except the summaries' callers, all of which are in tests.

Callers left between tasks, in plan order:
- **12a deletes `_allVehicleTargets`**, which TeslaBLE.setChargeRate:772 still calls until 12b (**I1**).
- **`car_api_available`** is called only by `car_api_charge` (TeslaAPI.py:799/802, deleted in 12a) and `applyChargeLimit` (1122/1125/1182/1185, deleted in 11). So 12a takes it, about 261 lines. But it is also the only production caller of `loadVehicleList` (TeslaAPI.py:494), apart from Telemetry's name lookup when `syncTelemetry` is set (Telemetry.py:363-370, whose comment says exactly that) (**C1**).
- `findReason`: its callers 1009/1068/1097 are in `car_api_charge` and 3040 is in `apply_charge_limit`. Safe in 12a.
- `_unavailableResult`: callers 804 (12a) and 1187 (11). Uncalled after 12a, deleted in 12b. Safe.
- `getLastStartOrStopChargeTime`: WebIPCControl.py:320 (the plan says 316/321). The Task 13 grep catches it. Minor drift, not listed separately.
- `Order.debugCommand` reads `master.workers` (Order.py:192). Task 10 must switch it to `master.reconciler`. Until Task 11 wires the reconciler, the route answers False (400), which matches ledger L35.

**Is the suite green at every task?** Not as written. It goes red at 12a (I1), and at 10 unless the extra test files in M1 are touched. At 13 the grep test cannot pass (I10).

---

## 3. Cost safety and missed commands

### Critical

**C1: After Tasks 11 and 12a nothing loads the TeslaAPI vehicle list, so Fleet and Owner can never deliver a stop, start or limit.**
- **Evidence.**
  - `loadVehicleList` is called only from `car_api_available` (TeslaAPI.py:494) and from Telemetry's name lookup when `syncTelemetry` is set (Telemetry.py:363-370: "The API vehicle list is otherwise only loaded when a command needs the API").
  - `car_api_available` is reached only through `car_api_charge` and `applyChargeLimit`. Task 11 deletes `applyChargeLimit` and the `checkArrival`/`checkDeparture` calls to it (TWCManager.py:324-342). Task 12a deletes `car_api_charge` and `car_api_available`.
  - Without the list, `CarApiVehicle._bind` never runs. So `vehicle.attachment("TeslaAPI")` is None, and both `OwnerAPIProvider.ready` and `FleetAPIProvider.ready` return False (TeslaAPIProviders.py:63-66, 99-100).
- **Effect.**
  - On a Fleet-only install, and for the Fleet fallback on BLE+Fleet, no stop, start or limit is ever delivered. That is a missed stop and a missed limit.
  - `resolveLegacyIds` (Task 11, and U1's drop) never fires.
  - `CarApiVehicle.atHome` stops updating for cars a Gen2 TWC does not report (it was set at TeslaAPI.py:542/826/1176/1216), so `Policy` `minBatteryLevelAtHome` (Policy.py:316, TeslaAPI.py:2516-2520) and `updateChargeAtHome` go blind.
- **Plan fix.**
  - Task 11, or at the latest 12a, adds one free maintenance call: `TeslaAPI.updateChargeAtHome()` (run by the existing `checkCharge` task) first loads the vehicle list when `getVehicleCount() < 1`, `slotFor("read")` is usable and `getCarApiRetryRemaining()` is 0. That is about 6 lines, and it calls `refreshTokenIfNeeded` the same way.
  - Add the test `test_vehicle_list_loads_without_any_legacy_command` (requests_mock: one `GET /vehicles`, no `vehicle_data` or `wake_up`), and assert that `FleetAPIProvider.ready(v, STOP_CHARGING)` becomes True.
  - Say in the plan where `atHome` is refreshed until Phase 5. `update_vehicle_data` already sets it when the reconciler's read-before-write runs (TeslaAPI.py:2928). State that this is the accepted interim, and that no new paid `update_location` is added.

### Important

**I1: Task 12a deletes `TeslaBLE._allVehicleTargets` while `TeslaBLE.setChargeRate` still calls it.**
- **Evidence.** TeslaBLE.py:772 (setChargeRate's all-vehicle branch) and :857 (applyChargeLimit, which goes in 11). setChargeRate is deleted only in 12b.
- **Fix.** Move `_allVehicleTargets` to Task 12b's delete list.

**I2: Under U2, Fleet Telemetry re-arms the "no paid send reached the car" rule on every reading, so paid sends are bounded per `RETRY` window, not per desire.**
- **Evidence.**
  - The rule 1 re-arm (Reconciler.py:319-327) resets `paidSends = 0` whenever `!paidReached` and a qualifying reading is newer than `paidAt + RETRY`.
  - Fleet Telemetry restamps every live (non-retained) publish (Telemetry.py:257-261).
  - Suppose Fleet keeps answering 408/UNREACHABLE while Telemetry streams: the car's connectivity flickers, or Telemetry buffers and delivers late. Then the cycle repeats every `RETRY`: send, blind retry, re-arm, send. For a limit that is about 12 commands an hour ($0.012/h). For start/stop or amps it is about 60 an hour ($0.06/h), plus a wake ($0.02) per cycle wherever a wake is allowed, limited only by `WAKE_RETRY_SECONDS`.
  - The I2 rule (`paidSends < 2`) stays bounded at 2 once a send has reached the car.
  - A retained redelivery with a different value is also restamped to now (Telemetry.py:271-277). So a broker reconnect counts as "the car is awake".
- **Plan fix.**
  - Set `LIVE_READ_SOURCES = {"TeslaBLE", "TeslaAPI", "FleetTelemetryMQTT"}`. That is the exact source string, the class name (Telemetry.py:258).
  - Allow the rule 1 re-arm **once per desire**: a new `AttemptRecord.rearmed` flag, reset in `newDesire()`. That caps a desire at 4 paid commands. The `ride` re-arm counts against the same flag.
  - Add the U2 test `test_streaming_telemetry_with_fleet_408_is_bounded_per_desire` (1 h of Telemetry every 30 s; Fleet scripted UNREACHABLE; `len(cmds(f)) <= 4`; `wake_up` ≤ 1), and a Task 14 row.
  - Optionally, do not count a retained redelivery: observe it with `seen=False` and skip it in `reachedCar` through `vehicle.lastSeenSource`. Or accept it and document why.

**I3: `reachedCar` built on `latestFrom` misses a live read when Home Assistant republishes after it.**
- **Evidence.** `newerReading` uses `vehicle.latestFrom(field, exclude=...)` (Reconciler.py:99), which returns only the newest observation. HA republishes every update. A TeslaAPI or Telemetry read followed seconds later by an HA republish of the same value leaves `latest.source == "HomeAssistant"`, so `reachedCar` is False and the limit is never re-sent. Task 10's test observes HA first and TeslaAPI last, so it cannot see this.
- **Fix.** `reachedCar(vehicle, field, since, beliefAtSend)` scans `vehicle._fields.reported(field)` (as `latestFrom` already does at Vehicle.py:106). It is True when any live-source observation is newer than `since`, or any vehicle-source observation newer than `since` has a value different from `beliefAtSend`. Add a test that observes TeslaAPI and then HA with the same value, and expects a re-arm.

**I4: c2 can leave a lowered limit undelivered on Fleet + TeslaMate or HA installs.**
- **Evidence.**
  - A lowered limit (90 → 50) is never woken for (Reconciler.py:120-130). On an asleep Fleet car the paid send is UNREACHABLE, twice.
  - Afterwards only TeslaMate or HA report, and the value is unchanged (90). Under c2 nothing re-arms.
  - The car then wakes on its own schedule and charges toward 90. No TeslaAPI read happens: the reconciler plans nothing, so no read-before-write runs, and `updateChargeAtHome` skips cars whose `atHome` is False (C1).
  - Main re-sent the limit at each policy pass. The `ride` re-arm covers only a start *we* want (Reconciler.py:318, 386-394).
- **Fix.** Also re-arm when a vehicle-source `chargingState` newer than `paidAt` is charging-like. A car drawing power is awake, and one command is the cost. Or re-arm on a free `vehicles/{vin}` online reading from the wake check. Add `test_lowered_limit_reaches_a_car_that_wakes_to_charge_on_teslamate` (paid counted: at most 3 commands, no wake).

**I5: `MIN_SEND_GAP` misses the case it replaces: a start in flight when the desire flips to stop.**
- **Evidence.** `noteOutcome` stamps `lastSentAt` only when the outcome is `current` (Desired.py:358-368). A start still running when the stop desire arrives is not current at report time, so `lastSentAt` keeps its old value and the stop plans immediately. HA's `CHARGE_SWITCH_LIMIT` window (Run.py:247, `note` before the call) did cover that case.
- **Fix.** Stamp `lastSentAt` for every outcome that is not `NOT_SENT`, current or not. Or stamp it in `_run` just before the provider call. Add a variant of `test_min_send_gap...` where the flip happens while the start is in flight.

**I6: A 10 s `MIN_SEND_GAP` lets Fleet amps go out faster than main.**
- **Evidence.** Main's mode 2/3 heartbeat sends a new rate at most once per 15 s (TWCSlave.py:885-901: `__lastAPIAmpsRequest > time.time() - 15`). After 12b every change of the stateless AMPS desire is a new desire with `paidSends = 0`, so only `MIN_SEND_GAP` paces it. Under a fluctuating green offer that is up to 360 paid sends an hour, against 240 on main. That breaks "no new paid path" in the worst case.
- **Fix.** Use `MIN_SEND_GAP = {CHARGE_LIMIT: 10, CHARGING: 10, AMPS: 15}`, or 15 s everywhere, and pin it with a paid-counted test in 12b (`test_fluctuating_offer_sends_at_most_one_rate_per_15s`).

**I7: Removing `WallConnectorVinReader._allowed` un-paces Gen3 cloud-VIN polling on connect edges.**
- **Evidence.** `due()` returns True on any connect edge, whatever the interval (WallConnectorVins.py:91-94). A flapping `occupied` flag queries `live_status` on every vitals poll. The calls are free, but 429s put the slot into backoff and delay Gen3 cloud VIN. `test_rate_limit_is_respected` and `test_the_declared_rate_limit_bites...` (test_wall_connector_vins.py:153/167) fail.
- **Fix.** In `due()`, an edge counts only when `clock() - lastQuery >= EDGE_MIN_GAP` (30 s). That is one line, and it keeps Gen3 intact. Rewrite those two tests against the gap, not the declaration.

**I8: The reconciler file passes the 600-line stop rule at Task 10 by construction.**
- **Evidence.** Reconciler.py is 472 lines. Moving `runAttempt`, `checked`, `_tagged`, `writtenValue`, `entryKey`, `isStop` and `_call` (Run.py:73-130, 181-290; about 210 lines with the constants) adds that much. The queue plumbing (`submit`, `cancel`, `start`, `drain`, the debug-report logging; about 60) and the c2, c4 and gap code (about 25) bring it to **about 740-770**. The plan's line 931 then halts execution.
- **Fix.** Set the threshold at 800 for Task 10, with Task 13's summary removal as the follow-up. Or keep `runAttempt` as a module function in a slim `Reconcile/Attempt.py` that takes the reconciler, with no hooks and no `isinstance`, and set the threshold for that file.

**I9: U1 needs plan edits, and dropping on the first list is risky.**
- **Edits.** Task 11 plan:547 currently says the call "warns once for the unmatched ones and keeps them in chargeLimits, so nothing is lost". Replace that with: "warns once per unmatched ID, naming the ID and its outside limit, then drops it. `chargeLimits` is deleted after the call." Update `test_legacy_ids_resolve_once_from_the_first_vehicle_list` to "unmatched dropped + one warning each + `chargeLimits` gone".
- **Risk.** The first successful list may come from one slot only. Owner and Fleet can be different accounts, or a car can be shared or temporarily off the account. Then a car's normal limit is lost for good, and after departure it stays at the policy limit.
- **Fix.**
  - Resolve against the union of every usable slot's list in that cycle.
  - Drop only after a list that named at least one vehicle.
  - Log the dropped `outside` value so the user can restore it by hand.
  - All of this depends on C1: the list must load at all.

**I10: Task 13's grep test cannot pass, and its test scope is incomplete.**
- **Evidence.** The test asserts `grep("…\\|def summary") == []` while the comment keeps `Vehicle.summary` (Registry/Vehicle.py:249). The summary deletions also break test_outcome_desired.py:51/147, test_provider_capabilities.py:51 and test_provider_outcomes_local.py:34.
- **Fix.** Grep the specific names (`AttemptRecord.summary`, `def _desiredSummary`, `def _attemptSummary`, the summaries in `Reconciler` and `Provider`), or exclude `Registry/Vehicle.py`. Add the four test files to Task 13's Files.

### c2 and c4 as specified, otherwise

- **c2 (Task 10).**
  - Narrowing rule 1 to "live read or changed value" fixes the HA, TeslaMate and Telemetry republish storm for those sources.
  - It also loosens the I2 rule: a live read of the *same* value now counts, where I2 previously required `value != paidSaw`. That stays bounded by `paidSends < 2` per desire. Acceptable, but say so in Decision 15.
  - The `or ride` re-arm (Reconciler.py:323) is not mentioned. State that it stays, and that it counts against I2's once-per-desire flag (**M4**).
- **c4 (Task 10).**
  - The test (plan:525-528) passes with the three listed cases, and no extra paid call results: the start was going to be sent anyway.
  - Specify that "every candidate is excluded" is computed over candidates that *declare* `SET_CHARGE_LIMIT`, ignoring readiness. Otherwise a BLE radio that is down for a moment, plus an excluded HA, counts as "spent", and the start goes before a limit BLE could deliver a minute later (**M11**).
  - Keep `paidReached` in "paid sends exhausted" (Reconciler.py:355). Dropping it would let an asleep car's unreached limit unblock the start before the limit can ride the start's wake.

---

## 4. Projected per-task deltas

Method structure was measured at d98d643: each method's span to the next `def`, from the listings in this review.

| Task | Plan | Measured deletions → net estimate | Verdict |
|---|---|---|---|
| 10 | −250 | Run.py 393 − about 210 moved; −25 VCQ (`inline`, `_entries`, `summary`); −20 callback lists; −35 RateLimit, declarations and `_allowed`; +40 for queues, c2, c4 and the gap → **≈ −200** | Plausible, slightly optimistic |
| 11 | −550 | TeslaAPI `applyChargeLimit` 196 + `apply_charge_limit` 71 + TeslaBLE `applyChargeLimit` 144 + HA 66 + VCQ 12 + VehiclePriority about 15 + TWCMaster shims about 48 + HeldLimits and Rules about 45 + attributes about 25 ≈ 620 removed; Targets about 100 + wiring about 95 added → **≈ −430..−480** | About 100 optimistic |
| 12a | −600 | TeslaAPI `car_api_available` 261 + `car_api_charge` 333 + `findReason` 7; TeslaBLE `car_api_charge` 132 + start 35 + stop 23; HA `car_api_charge` 64 + `car_api_available` 10; VehiclePriority about 15; Policy and TWCSlave about 15 ≈ 895; the C1 loader +6 and heartbeat wiring about 30 → **≈ −850** | **Understated by about 250** (`car_api_available` is gone here) |
| 12b | −900 | `setChargeRate` 84+91+69, `_chargeRateAccepted`/`_recordChargeRate` 17, `wakeVehicle` 44, `_unavailableResult` 15, `_stampWrite` 11, `_allVehicleTargets` 17 (I1), VehiclePriority about 300, VCQ legacy about 60, TWCMaster queue and priority about 85, TWCManager about 25, Order `dispatch`/`_succeeded`/`_count`/`attempts` about 50, VehicleEndpoint and TWCSlave throttles about 35 ≈ 900; carriers, layering and `chargeCurrentRequest` about 100 → **≈ −800** | About 100 optimistic. With 12a, 12a+12b ≈ −1,650 against the plan's −1,500 |
| 13a | −260 | `_execute_with_retry` 90, breaker about 46, stats/backoff/transient about 57, `_kill_process_group` 49, `_is_transient_error` 30, `closeFile` 4, config about 10 ≈ 286; quick retry +15 → **≈ −270** | Plausible |
| 13b | −150 | ReadSource.py 58 + Sources.py 143 + registry plumbing about 30 + `orderReadSources` 16 + attributes about 10 ≈ 257; `Provider.fetch` ×3 + `FIELDS` about 75 → **≈ −180** | Plausible |
| 13c | −120 | The four paths ≈ 347 (107+84+18+61+39+21+7+10); helper and classifier about 90; callers keep their parsing → **≈ −100..−150** | Plausible |
| 13 | −450 | Of the §3 misses, about 120 were already taken by 11–12b (`car_api_available`, `findReason`, `_stampWrite`, `_count`, HA `car_api_available`). What is left: about 115 misses + 128 dead-on-main + about 170 declarations and summaries ≈ **−400** | Plausible |

The end total is unchanged within noise: about 27,000, as the plan says. Per-task attribution moves: 12a deletes more, and 11 and 12b less (**M8**). That matters only for the ledger's "actual vs expected" lines.

---

## 5. Minor

- **M1.** Task 10's test scope is incomplete. Also touch: test_carapivehicle_registry.py:135-145, test_provider_order.py:122-123, test_limit_reconciler.py:8/18 (`Workers`); test_outcome_desired.py, test_protocol.py, test_provider_tables.py, test_teslaapi_providers.py, test_twcmaster.py and test_wall_connector_vins.py (rate limits and callbacks). List them.
- **M2.** Task 10 deletes `_workerOf`, but the read-before-write still filters `readSources()` by the worker of each source's provider (Run.py:204-210) until 13b. Keep `self._workerOf(name)` as a method in the reconciler until 13b, or say that the read uses only the attempt provider's own sources.
- **M3.** Fix the stale cross-references:
  - Review Focus 1, 3 and 4 say Task 11; the tests are in 12a.
  - The ledger's L50 "Task 11" should be 12a.
  - The ledger's S6/N3 "(Task 11, Review Focus 3)" should be 12a.
  - The ledger's L35 test name.
  - Task 11 Files lists `workers`.
  - The Self-review "Types" still names `Workers.*` and `allows` (plan:1016).
  - `followRegistry` is a method in Task 11 but an assignment in Task 10.
- **M4.** State that the `ride` re-arm (Reconciler.py:318-327) survives c2, and how it counts against I2's cap.
- **M5.** Task 13a: the breaker test is test_provider_outcomes_local.py:102-111. `maxRetries` and `retryDelay` are also used in test_provider_outcomes_local.py, test_teslable_pairing_status.py and test_teslable_lock.py.
- **M6.** Task 13c:
  - Name the per-path differences the classifier keeps. The vehicle list does not retry after a 401 and starts no API backoff (TeslaAPI.py:407-410). The energy path's 403 retires only Wall Connector reads (`reportScopeRefused("energy")`, TeslaAPI.py:1374-1376); Gen3 cloud VIN depends on it.
  - Make the 4×6 test table-driven with those expectations.
  - Keep Task 11's `resolveLegacyIds` call in `loadVehicleList`.
  - No new paid call: a command after a 401 already retries once after a refresh (TeslaAPI.py:2075-2083).
- **M7.** HA `_vehiclesFor` (HomeAssistant.py:607, callers 629/697) is orphaned after 12a and is on no list. Add it to 12a.
- **M8.** Re-baseline the expected deltas (§4): 11 ≈ −450, 12a ≈ −850, 12b ≈ −800.
- **M9.** Development installs of this branch may hold `heldLimits` entries with `id:` keys. Deleting `LEGACY_PREFIX` orphans them silently. Handle `id:*` keys at `load()` the same way as numeric `chargeLimits` keys, or drop them with the U1 warning.
- **M10.** Task 13 line references drift: `getLastStartOrStopChargeTime` is at WebIPCControl.py:320 now. Grep by name, not by line.
- **M11.** For c4's "every candidate excluded", use declared candidates, not ready ones (see §3).
