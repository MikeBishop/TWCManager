# Task 3 report: control tick, one distributor, flex removed

**Status: DONE.** Commit **87c48973** on `vehicle-model/phase4` (BASE 984f889e); it replaces WIP commit a5560c20. Not pushed.
- Full suite: **1910 passed, 1 xfailed, 1 warning**.
- The original block (row 26) is resolved by the coordinator's ruling (d). See "Resolution" below.

## Row 26: the reorder (now accepted under (d))

Paid and HTTP counts are unchanged: 0 requests before, 0 after. The BLE command list has the same items, but two of them swap places:

- BASE: wake, set-limit 70, wake, **set-amps 32**, wake, **charging-start**
- After: wake, set-limit 70, wake, **charging-start**, wake, **set-amps 32**

Cause: the designed one-beat lag ((d) and F9) meets the reconciler's ordering.
- **BASE.** The legacy fair share computed the offer on the first reply, so the lift (`_requestVehicleRateRaise`) and the start (`send_master_heartbeat`'s gate) were both desired on beat 1 (t=1010).
  - The limit went in pass 1010.
  - The start was held back by `LIMIT_THEN_START_GAP = 5.0` (Reconciler.py:83, check at :384). The amps were not held back, so amps went out before the start.
- **After.** The first reply only sets `heardFrom`; the slave has no target yet, so the heartbeat keeps its payload (Review Focus 1). The tick then targets the slave.
  - The lift and the start are both desired on beat 2 (t=1020). By then the limit gap has passed.
  - With both eligible in one pass, `_ORDER = (CHARGE_LIMIT, CHARGING, AMPS)` (Reconciler.py:94) sends the start first.
- The test's beats are 10 s apart, so here the one-tick lag is a whole beat. In production it is about 1 s, but the same pass would still order start before amps.

Two heartbeat-side changes did not affect it:
- a realistic `amps_max=32`, which is applied (see the test map);
- moving the `lastAmpsOffered` init after the not-yet-targeted return. That change was reverted.

### Resolution (coordinator ruling)

The reorder is accepted under (d). The reconciler's aspect order is unchanged.
- Row 26 now expects wake, set-limit 70, wake, charging-start, wake, set-amps 32.
- It carries an INTENTIONALLY CHANGED (d) comment.
- It also asserts that set-amps 32 follows the start within one send gap: `0 <= t(set-amps) − t(start) < MIN_SEND_GAP[AMPS]` (15 s). Both are sent in the same pass.
- HTTP count is still 0.

## Rulings applied mid-task

1. **F2 is replaced.** The `countSlaveTWC() > 0` gate is gone (second coordinator message). `controlPass` always distributes; with no charging endpoint the distributor finds nothing to do.
   - **(g) Gen3-only installs are controlled.** Test: `test_a_gen3_only_install_is_controlled`. The unit gets 20 A × 240 V and no car amps are set.
   - **(h) Vehicle-only installs are controlled.**
     - `test_a_vehicle_only_install_is_controlled`
     - `test_a_pass_with_nothing_to_distribute_to_does_nothing`
     - new parity rows 29 and 30 (below)
   - Both belong in the PR body.
2. The earlier "vehicle-only carve-out" message was superseded and is not implemented.

### New parity rows (h)

Setup: a car charging at home, no wall connector, a 16 A budget, one `controlPass` per 10 s step for 3600 s.

| Row | Install | vehicle_data | wake | command | $ | Requests |
|---|---|---|---|---|---|---|
| 29 `test_fleet_only_vehicle_install_gets_its_rate` | Fleet token only | 0 | 0 | 1 | 0.001 | one `set_charging_amps` (16) |
| 30 `test_ble_only_vehicle_install_gets_its_rate_with_nothing_paid` | Owner token (free presence), `commandPolicy: ble_only`, BLE paired | 0 | 0 | 0 | 0 | none; BLE `charging-set-amps 16` |

**Caveat for (h), accepted by the coordinator; the PR should note it:** a car that only BLE or HA knows (no TeslaAPI presence) still gets no VehicleEndpoint. Presence is Phase 5's job.
- `VehicleEndpoints.allEVSEs` returns `[]` without an enabled TeslaAPI (`_get_carapi`), and it lists only cars that TeslaAPI places `atHome`.
- So "BLE-only" works only where a TeslaAPI listing (an Owner or Fleet token, both free here) supplies presence.
- Rows 29 and 30 call `api.locate(v)` once (free) to set `atHome` from TeslaMate's position. In production, `atHome` is set by the free `locate` and `updateChargeAtHome` paths.
- Presence is Phase 5.

## Implementation

- **`lib/TWCManager/ControlTick.py`** (new)
  - `ControlTick(master, interval=1.0)` is a daemon thread named `"ControlTick"`.
  - `pass_()` runs `controlPass` when fakeMaster is 1, then `housekeeping`. Each runs in its own try and logs a WARNING with the exception type name.
  - `housekeeping()` makes one `WebIPCControl.processIPC()` call and does the hourly `expireVehicles` queueing.
  - `stop()` sets the event and joins with a 2 s timeout.
- **TWCMaster**
  - `__init__` registers `Gen2TWCs` and `VehicleEndpoints`.
  - `controlPass(now=None, distribute=True)` sets `self._points = self.distributeEVSEPower()`, with no gate (per the rulings above).
  - `distributeEVSEPower` loses the `non_gen2` gate, gets a new docstring and returns the points it built (`[]` without controllers).
  - Removed: `allowed_flex`, `getAllowedFlex`, `setAllowedFlex`.
  - `num_cars_charging_now()` is now a pure count. `observeChargingSessions()` is the old body, minus its return value; it runs on the serial thread only.
  - `getSlaveTWCs()` returns a copy.
- **Gen2TWCs.allEVSEs**: lists only slaves with `heardFrom` (F9, F19). `_blindTWCs` still scans every slave.
- **TWCSlave**
  - Adds `heardFrom = False`, set to True on the first reply.
  - `receive_slave_heartbeat` calls `observeChargingSessions()` then `num_cars_charging_now()`. When `_evseTargetAmps is None` it returns before the amps computation, leaving `masterHeartbeatData` as it was.
  - Deleted: the legacy fair-share branch, all flex (min-branch clause and debug text), `useFlexAmpsToStartCharge`, and dead locals (`ltNow`/`hourNow`/`yesterday`).
- **TWCManager.py**
  - Deleted: the VehicleEndpoints registration block, the per-round `distributeEVSEPower` call, `processIPC` and expiry from the loop.
  - `master.controlTick = ControlTick(master); start()` runs right after `reconciler.start()`.
  - On shutdown, `master.controlTick.stop()` runs right after `Policy.stop()`, before `reconciler.stop()` (F16).
- **WebIPCControl**: `getStatus` iterates the `getSlaveTWCs()` copy (IDs from `slaveTWC.TWCID`, count from `len(copy)`). The send-length check uses the copy too (F15).
- **Policy**: removed the two `"allowed_flex"` entries and the `setAllowedFlex` call.
- **Docs and configs**
  - `docs/PolicyCustomization.md`: the Flexibility section now says flex is not supported from 1.4.0 and the keys are accepted but ignored; the `allowed_flex` bullet is gone.
  - `docs/config_examples.md`: the flex key is out of the example; a note says it is ignored.
  - `etc/twcmanager/{config,demo,.testconfig}.json`: the two flex keys and their comments are removed. `.testconfig` was verified to parse equal minus the keys.

## Tests and results

- Focused: `test_control_tick.py test_charging_points.py test_gen2_idle_minimum.py test_amps_reconciler.py test_charging_reconciler.py test_command_path_parity.py`. All pass except row 26.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`, verbatim command), after the row 26 ruling, on 87c48973's tree: **1910 passed, 1 xfailed, 1 warning** (89 s).
  - Baseline was 1896 passed.
  - Delta: 3 tests deleted, 15 added in `test_control_tick.py`, 2 parity rows added.

### TDD evidence

- RED: `test_control_tick.py` failed to collect with `ModuleNotFoundError: No module named 'TWCManager.ControlTick'`. `controlPass`, `observeChargingSessions` and `tickThenBeat` did not exist yet either.
- GREEN: 15/15 pass.
- The gate tests check their own sensitivity: the vehicle-only test asserts that `distributeEVSEPower` does set amps.

### Parity counts before and after

- Recorded per test with a scratch pytest plugin (every request URL plus `counts()`), at 984f889e and after the change.
- **All 49 existing rows have identical request lists and counts.** Row 26 makes no HTTP requests; its only difference is the BLE order above, accepted under (d).
- Rows 29 and 30 are new (h), in the table above. (g) is pinned by `test_control_tick.py::test_a_gen3_only_install_is_controlled`, which makes no HTTP requests.

| Row | vehicle_data | wake | command | $ |
|---|---|---|---|---|
| 1–28 (49 tests, existing) | unchanged | unchanged | unchanged | unchanged |
| 26 restart, plugged in and asleep | 0 | 0 | 0 | 0 (BLE order changed, (d)) |
| 29 Fleet-only vehicle install, 1 h at 16 A (h) | 0 | 0 | 1 | 0.001 |
| 30 BLE-only vehicle install, 1 h at 16 A (h) | 0 | 0 | 0 | 0 |

## Test map (deleted or rewritten)

| Test | Mapping |
|---|---|
| `test_charging_points.py::test_pure_gen2_leaves_distributor_off` | Deleted. INTENTIONALLY CHANGED (b); replaced by `test_teslaapi_disabled_install_uses_the_one_distributor` |
| `test_twcmaster.py::test_set_allowed_flex` | Deleted. INTENTIONALLY CHANGED (c); replaced by `test_flex_settings_are_read_but_ignored` and `test_a_policy_with_allowed_flex_evaluates_without_error` |
| `test_twcslave.py::test_slave_use_flex_amps_to_start_charge` | Deleted. INTENTIONALLY CHANGED (c); same replacements |
| `test_policy.py` four `master.setAllowedFlex = Mock()` lines | PLUMBING-ONLY: the method is gone |
| `test_charging_points.py::real()` | PLUMBING-ONLY: `newSlave` marks hand-built slaves `heardFrom`, because they report as if they had replied (F9 filter) |
| `test_gen2_idle_minimum.py` `idleSlave`, `chargingSlave`, `busy` | PLUMBING-ONLY: same `heardFrom` reason |
| `test_distributor_loop.py::_master` | PLUMBING-ONLY: comment updated; `slaveTWCRoundRobin` is visible to `countSlaveTWC` |
| `test_amps_reconciler.py` `test_mode_2_car_carries…`, `test_twc_only_point…`, `test_heartbeat_does_not_write_amps…` | PLUMBING-ONLY: these set targets by hand, so they use `offersThenBeat` |
| `test_amps_reconciler.py::test_a_session_end_resets…` | PLUMBING-ONLY: calls `observeChargingSessions()` |
| `test_amps_reconciler.py::test_heartbeat_withdraws_its_rate…` | PLUMBING-ONLY: a priming beat first (heard from), then `controlPass()` before the beat, because of the (d)/F9 one-tick lag. Values unchanged |
| `test_charging_reconciler.py::test_an_offer_starts_the_car_from_the_heartbeat` | PLUMBING-ONLY: `amps_max=32` because a real TWC echoes its offer. Command order unchanged |
| `test_limit_wiring.py` `startAfterRaise` (used by `test_a_restart…still_gets_the_policy_limit`) and `test_a_vinless_gen2_after_a_restart…` | PLUMBING-ONLY: `amps_max=32` (the TWC echoes its offer) |
| `test_limit_wiring.py::test_at_00_a_plugged_car…begins_the_session` | PLUMBING-ONLY: `amps_max=32` and two beats (targeted from the second, (d) lag). At BASE the lift came only from the legacy path; on BASE's default (VehicleEndpoints) path an idle 00/0 A TWC got target 0 and no lift |
| `test_twcmaster_vin_confirmation.py:72,76` | PLUMBING-ONLY: calls `observeChargingSessions()` |
| `test_provider_registration.py::test_startup_registers_providers_after_the_module_loop` | PLUMBING-ONLY: the TeslaAPI-gated registration block moved into `TWCMaster.__init__` (`loop < call` kept) |
| `test_provider_registration.py::test_no_vehicle_modules_registers_only_gen2` and `test_default_boot_registers_unconfigured_modules_that_never_command` | INTENTIONALLY CHANGED (b): every install registers `["Gen2TWCs", "VehicleEndpoints"]`; without TeslaAPI it lists no endpoint (asserted) |
| `test_command_path_parity.py` row 26 | `amps_max=32` (PLUMBING-ONLY per the brief). The expected BLE order (start before set-amps 32) is INTENTIONALLY CHANGED (d) per the coordinator's ruling, with a within-one-send-gap assertion. Counts unchanged (0) |
| `gen2_helpers.drive` | Now receive → `controlPass()` → send; `tickThenBeat` and `offersThenBeat` added |
| New tests | `test_control_tick.py` (15): the brief's list, plus (g) Gen3-only, (h) vehicle-only, nothing-to-distribute, getSlaveTWCs copy, unheard slave gets no offer. Parity rows 29 and 30 (h) |

`useFlexAmpsToStartCharge: False` entries remain in the config dicts in `test_twcslave.py` and `test_registry_callers.py`. They stand for old configs that must still load (c). The grep over lib, html and docs finds only the "not supported" doc notes.

## Lib delta

- Before: 27,416. After: **27,378** (−38). Expected about −58.
- `git diff --shortstat 984f889e -- lib`: 7 files changed, 115 insertions(+), 153 deletions(-).
- Part of the shortfall is the new ControlTick (≈47 lines) and the docstrings for the gate rulings.

## Self-review

- Lock order: no new locks. The tick calls `controlPass` with no lock held, and `processIPC` sends through the queued `sendRS485` outbox.
- Shutdown: the tick is joined (2 s) before the reconciler drains.
- `pass_` guards each step on its own, so a raising `controlPass` does not skip housekeeping.
- `_points` is written by the tick only and nobody reads it yet (Task 4 will).
- The pre-existing `setMasterHeartbeatData` path in WebIPC still indexes `[0]` with no slaves (an IndexError that predates this task). Left alone.

## Concerns

1. **Row 26:** reordered under (d) by ruling; the PR may mention it.
2. **(h) is partial, accepted:** a car only BLE or HA knows gets no VehicleEndpoint until Phase 5 presence. The PR should note it.
3. Lib shrank by −38, against an expected −58.
4. **PR body:**
   - (g) Gen3-only installs are now controlled.
   - (h) Vehicle-only installs are now controlled. Paid spend is bounded by the reconciler: free providers first, ≤4 paid sends per desired value, no wake for amps. Over one hour the Fleet-only install paid $0.001.
   - Flex (c) is removed.

---

## Fix round 1 (review Important 1)

**Finding.** With the gate gone, a Gen2 install with no slave linked looked like a vehicle-only install. That happens in three windows:
- at startup, before the first linkready reply;
- after a slaveTimeout drop, until the slave re-links;
- while the adapter is dead.

In those windows every car TeslaAPI places at home got its own endpoint and AMPS desire, which is paid on Fleet. BASE sent nothing then.

**Ruling applied.** While an RS-485 interface is loaded and no slave is linked, `_blindTWCs` reports blind (and unknown), so those cars get no VehicleEndpoint. Vehicle-only installs, with no interface module loaded, keep the (h) behaviour.

**Commit:** 8c673fc7 (on top of 87c48973).

**Changes**
- `lib/TWCManager/EVSEController/VehicleEndpoints.py` (`_blindTWCs`): `if not slaves and self.master.getModulesByType("Interface"): blind = unknown = True`. Docstring updated.
  - "Interface loaded" means the RS485, TCP or Dummy module is registered. A disabled interface module releases itself at load.
- `tests/unit/test_control_tick.py`
  - New `test_a_gen2_install_with_no_slave_linked_sends_no_amps`: an interface is loaded, there is no slave, and a car is charging at home. Three `controlPass` calls set no AMPS desire and list no endpoint. Once a slave links, the car is listed again as its own point beside the 00/0 A slave, as at BASE.
  - `test_a_vehicle_only_install_is_controlled` now also asserts that no interface is loaded.
- `tests/unit/test_vehicle_endpoint.py::master()`: `getModulesByType = lambda t: []`. PLUMBING-ONLY: a Mock's auto attribute is truthy and would read as "interface loaded". These tests model the vehicle side with no RS-485 interface.

**TDD**
- RED: with VehicleEndpoints.py reverted, the new test fails with `assert [{'vin': '5YJ3E1EA1KF000001', 'amps': 20}] == []`.
- GREEN: with the fix, it passes.

**Covering tests:**
`timeout 600 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest tests/unit/test_control_tick.py tests/unit/test_command_path_parity.py tests/unit/test_vehicle_endpoint*.py -q --timeout=60 -p no:cacheprovider` → `81 passed in 4.66s`

**Full suite:** `1911 passed, 1 xfailed, 1 warning in 89.01s`

**Parity:** all 51 rows have identical request lists and counts compared with the previous after-run. That includes rows 29 and 30: those masters load no interface module, so they are vehicle-only.

**Lib:** 27,378 → 27,383 (+5). Total for Task 3: 27,416 → 27,383 (−33; −58 expected).
