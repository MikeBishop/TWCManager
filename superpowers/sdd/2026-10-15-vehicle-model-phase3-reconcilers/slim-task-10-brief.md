### Task 10: Consolidate the command stack; one minimum send gap; close c2 and c4 (expected lib Δ ≈ −200)

The reconciler is not wired yet, so this is the cheapest moment to restructure it. Audit items 4, 6 and 10 apply here.

**Files:**
- Modify: `Reconcile/Reconciler.py`, `Reconcile/Desired.py`, `Registry/VehicleRegistry.py`, `VehicleCommandQueue.py`, `Providers/Capability.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `WallConnectorVins.py`, `Providers/Order.py` (`debugCommand` reads `master.reconciler`; it answers False until Task 11 wires it, per ledger L35).
- Slim, not delete: `Reconcile/Run.py` (pre-flight I8). It keeps a module-level `runAttempt(reconciler, attempt) -> Outcome` plus `checked`, `_tagged`, `writtenValue`, `entryKey`, `isStop` and `_call`. It calls `reconciler.beforeWrite/afterWrite` directly: no hook lookup, no lazy import, no `isinstance`. `Workers`, `RateLimits` and `_reconcilerParts` go. `_workerOf(master, name)` stays until Task 13b, because the read-before-write still filters read sources by worker (pre-flight M2). The 600-line stop rule stays and applies to each file.
- Test (pre-flight M1): `test_workers.py` becomes `test_reconciler_queues.py`. `reconcile_helpers.py` gains `InlineQueue` (the test-only synchronous queue) and `inline(reconciler)`, which swaps the reconciler's two queues for `InlineQueue`s. Also update:
  - for `Workers`: `test_carapivehicle_registry.py` (≈135–145), `test_provider_order.py` (≈122), `test_limit_reconciler.py` (≈8/18);
  - for rate limits and callbacks: `test_outcome_desired.py`, `test_protocol.py`, `test_provider_tables.py`, `test_teslaapi_providers.py`, `test_twcmaster.py`, `test_wall_connector_vins.py`.

**Interfaces:**
- `VehicleReconciler`:
  - owns `self.ble` and `self.cloud` (`VehicleCommandQueue(run=self._run, key=entryKey, isHigh=isStop, report=self.report, lost=...)`);
  - `submit(attempt) -> bool` (local providers run inline), `cancel(key) -> int`, `start()` (both queues, then the thread) and `drain(timeout) -> bool`;
  - `_run(attempt) -> Outcome` calls `Run.runAttempt(self, attempt)`. The stale-desire guard reads `self.master.desired` directly.
- `DesiredStore.onChange` and `VehicleRegistry.onRemove` become single callable attributes (`store.changed = reconciler.wake`; `registry.removed = desired.forget`). Called outside the lock; no list, no per-callback lock. `Workers.setReport` goes, and `followRegistry` becomes that one assignment.
- `VehicleCommandQueue` loses `inline`, `_entries` and `summary` (test-only; moved to `InlineQueue` in the tests).
- **Rate limits (audit item 10).** Delete `RateLimit`, `Declaration.rateLimit`, `FLEET_COMMAND_LIMIT`, `CHARGE_SWITCH_LIMIT`, `WALL_CONNECTOR_VINS`'s limit and `WallConnectorVinReader._allowed/_calls`.
  - `WallConnectorVinReader.due()` counts a connect edge only when `clock() - lastQuery >= EDGE_MIN_GAP = 30.0` (pre-flight I7). `test_rate_limit_is_respected` keeps passing. `test_the_declared_rate_limit_bites…` is rewritten against the gap.
  - In their place, `plan()` gets one rule: `MIN_SEND_GAP = {CHARGE_LIMIT: 10.0, CHARGING: 10.0, AMPS: 15.0}`. AMPS uses 15 s, main's heartbeat rate pacing (pre-flight I6). No attempt goes out while `now - rec.lastSentAt < MIN_SEND_GAP[aspect]`.
  - `lastSentAt` survives `newDesire()`. It is stamped for every outcome not in `NOT_SENT`, including a late outcome of a replaced desire (an in-flight start when the desire flips to stop; pre-flight I5).
  - This replaces HA's 10 s start/stop gate (audit item 6) for every provider.
- **c2: only a reading that reached the car re-arms a paid send.**
  - `reachedCar(vehicle, field, since, beliefAtSend) -> bool` scans every source's report of `field` (as `latestFrom` does internally), not just the newest (pre-flight I3). It is True when either holds:
    - any observation newer than `since` comes from a source in `LIVE_READ_SOURCES = {"TeslaBLE", "TeslaAPI", "FleetTelemetryMQTT"}`. These are exact source names; Fleet Telemetry always counts, per the user's decision;
    - any vehicle-source observation newer than `since` has a value ≠ `beliefAtSend`.
  - The "re-arm on any newer reading" rule (d98d643, for paid sends that got only `UNREACHABLE`) and the I2 reopen rule both use it. HA or TeslaMate republishing an unchanged value with fresh stamps re-arms nothing. A live read of the *same* value now re-opens too; that stays bounded by the caps below.
  - **Once-per-desire re-arm cap** (pre-flight I2, I4, M4). A new `AttemptRecord.rearmed` flag, reset in `newDesire()`, allows one re-arm per desire, so a desire gets at most 4 paid sends. Three triggers share the flag:
    - the reached-car re-arm above;
    - the existing `ride` re-arm (a limit riding our start's wake; it survives c2);
    - **a charging re-arm**: for a `CHARGE_LIMIT` desire whose paid sends never reached the car, a vehicle-source `chargingState` newer than `paidAt` that is charging-like means the car is awake, so a lowered limit gets one more send.
- **c4: a refused limit counts as spent.** Limit-before-start treats the car's `CHARGE_LIMIT` desire as spent (it no longer blocks the start) when the limit cannot be delivered. That is the case when:
  - every candidate that *declares* `SET_CHARGE_LIMIT` (readiness ignored, so a briefly down BLE radio does not count) is excluded (REFUSED or UNSUPPORTED; pre-flight M11);
  - its paid sends are exhausted and none reached the car (`paidReached` stays in this test); or
  - it is held as NOT_SENT for a refusal (`"wake refused"`, `"no command token"`).

- [ ] **Step 1: Write the failing tests.**
  - Port the `test_workers.py` tests onto `reconciler.submit/cancel/drain` with `inline(r)` where they were inline. The two drain tests keep real threads.
  - Delete the `RateLimits` tests (`test_rate_slot_is_used_only_when_a_command_is_sent`, `test_ha_start_and_stop_share_one_window_per_car`, `test_rate_limited_provider_is_skipped_at_plan_time`).
  - Add:

```python
def test_min_send_gap_spaces_a_start_stop_flip_on_any_provider():          # replaces HA's 10 s gate
    ...; m.desired.set(VIN, CHARGING, True, "heartbeat"); r.pass_(); m.desired.set(VIN, CHARGING, False, "heartbeat")
    c.t += 9; assert r.pass_() == 0; c.t += 1; assert r.pass_() == 1

def test_min_send_gap_holds_when_the_flip_lands_while_the_start_is_in_flight(): ...   # I5: start reported after the flip still stamps lastSentAt
def test_amps_gap_is_fifteen_seconds(): ...                                  # I6
def test_wall_connector_edges_are_spaced_thirty_seconds(): ...               # I7, live_status requests counted

def test_ha_republishing_the_limit_every_minute_does_not_rearm_paid_sends(): # c2, paid counted
    ...; fleet scripted UNREACHABLE("408"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(60): c.t += 60; v.observe("chargeLimit", 90, "HomeAssistant"); r.pass_()
    assert len(cmds(f)) <= 2                                                 # 1 h of republishing: at most one send + one retry
    v.observe("chargeLimit", 90, "TeslaAPI"); c.t += RETRY[CHARGE_LIMIT]; r.pass_(); assert len(cmds(f)) == 3   # a live read re-arms

def test_a_live_read_followed_by_an_ha_republish_still_rearms(): ...        # I3: TeslaAPI then HA, same value -> re-arm

def test_streaming_telemetry_with_fleet_408_is_bounded_per_desire():        # I2, user decision U2, paid counted
    ...; fleet scripted UNREACHABLE("408"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(120): c.t += 30; v.observe("chargeLimit", 90, "FleetTelemetryMQTT"); r.pass_()
    assert len(cmds(f)) <= 4 and len(calls_named(f, "wake")) <= 1

def test_lowered_limit_reaches_a_car_that_wakes_to_charge_on_teslamate():  # I4, paid counted
    ...; fleet UNREACHABLE twice then DONE; lowered 90 -> 50; c.t += 3600; v.observe("chargingState", "Charging", "TeslaMateVehicle"); r.pass_()
    assert len(cmds(f)) == 3 and calls_named(f, "wake") == []
    for _ in range(10): c.t += 600; v.observe("chargingState", "Charging", "TeslaMateVehicle"); r.pass_()
    assert len(cmds(f)) == 3                                                 # once per desire

def test_a_refused_limit_does_not_block_the_start_forever():                # c4, paid counted
    ...; ha refuses setChargeLimit (REFUSED "403"); m.desired.set(VIN, CHARGE_LIMIT, 80, "policy"); m.desired.set(VIN, CHARGING, True, "heartbeat")
    for _ in range(5): c.t += 61; r.pass_()
    assert cmds(ha).count("setChargeLimit") == 1 and cmds(ha).count("startCharging") == 1

def test_no_callback_lists_or_test_modes_in_lib():
    assert not hasattr(VehicleCommandQueue, "_entries") and "inline" not in inspect.signature(VehicleCommandQueue).parameters

def test_a_refused_limit_with_a_declared_but_unready_ble_still_blocks_the_start(): ...   # M11
```

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** per Interfaces. Slim `Run.py` as described.
- [ ] **Step 4: Run the full suite** → PASS. Record the lib delta (`git diff --shortstat HEAD~ -- lib`) in the ledger.
- [ ] **Step 5: Commit.** `git commit -m "The reconciler owns the attempt runner's queues; the runner calls it directly; one minimum send gap replaces declared rate limits; only a reading that reached the car re-arms a paid send"`

