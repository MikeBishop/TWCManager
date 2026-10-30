### Task 3: The control tick runs one distributor for every install; flex goes (expected lib Δ ≈ −58)

`ControlTick` is a daemon thread. Every `TICK` (1.0 s) it:
- calls `master.controlPass()`, when `fakeMaster == 1`. `controlPass` does nothing while `countSlaveTWC() == 0`, as BASE never distributed without a Gen2 slave (F2);
- then calls `housekeeping()`, in every mode: `WebIPCControl.processIPC()` (its RS-485 send is already queued, Task 1) and the hourly `expireVehicles` queueing.

The serial loop loses the distributor call, `processIPC` and expiry.

**The distributor runs for every install that has a Gen2 slave (as at BASE, F2).**
- `Gen2TWCs` and `VehicleEndpoints` are both registered in `TWCMaster.__init__`. `VehicleEndpoints.allEVSEs` is `[]` without an enabled TeslaAPI (`:105`).
- `Gen2TWCs.allEVSEs` lists only slaves with `heardFrom` True (F9, F19). This is the one place the filter lives; Task 6 carries it into `getAllEVSEs`. `VehicleEndpoints._blindTWCs` still scans every slave (an unheard slave reads 00 / 0 A, not blind, as at BASE).
- The `non_gen2` gate goes.
- The legacy fair-share branch in `receive_slave_heartbeat` (767–816) is now dead and goes. It ran only when `_evseTargetAmps is None`, i.e. TeslaAPI disabled, or before the first round.

**Flex is deleted, not ported (c).** It lived only in the legacy branch this task removes; the default path already zeroed it. Its plumbing goes with it: `TWCMaster.allowed_flex`/`getAllowedFlex`/`setAllowedFlex`, the two `"allowed_flex"` entries in `Policy.default_policy`, `Policy`'s `setAllowedFlex` call, and `TWCSlave.useFlexAmpsToStartCharge`. The keys stay readable: nothing reads them.

**Charging-session tracking stays on the serial thread.** `observeChargingSessions()` (the old `num_cars_charging_now` body) runs from `receive_slave_heartbeat`. `num_cars_charging_now()` becomes a pure count, safe from HTTP and the policy thread.

**Files:**
- Create `lib/TWCManager/ControlTick.py`.
- Modify `lib/TWCManager/TWCMaster.py`:
  - `__init__` (register `VehicleEndpoints`);
  - `distributeEVSEPower` (:529–641: drop the gate, rewrite the docstring);
    - delete `allowed_flex` (:42), `getAllowedFlex` (:394–395) and `setAllowedFlex` (:1830–1831);
  - add `controlPass(now=None, distribute=True)`: `if self.countSlaveTWC() == 0: return`; then, when `distribute`, `self._points = self.distributeEVSEPower()`. Tasks 4 and 5 add offers and gates after it (F1, F2);
  - `num_cars_charging_now` (:1262) split;
  - `getSlaveTWCs` (:991) returns `list(...)`.
- Modify `lib/TWCManager/TWCManager.py`:
  - delete the registration block :759–776, the distributor call :923–930 (keeping the heartbeat send and round-robin), `processIPC` :983–985 and expiry :1000–1004;
  - start `ControlTick` after `master.reconciler.start()`;
  - on shutdown, `master.controlTick.stop()` right after `Policy.stop()`; `stop()` joins with a 2 s timeout, so the tick is gone before `reconciler.stop()` (F16).
- Modify `lib/TWCManager/Control/WebIPCControl.py:179–193`: index the `slaveTWCRoundRobin = getSlaveTWCs()` copy taken at :131 instead of `getSlaveTWCID(i)`/the live list (F15).
- Modify `lib/TWCManager/Policy/Policy.py`: delete the `"allowed_flex"` lines (:59, :82) and the flex call (:286–287).
- Modify `docs/PolicyCustomization.md:135,213`, `docs/config_examples.md:18,26` (the key is ignored) and `etc/twcmanager/{config,demo,.testconfig}.json` (drop the two flex keys and their comment).
- Modify `lib/TWCManager/TWCSlave.py`: delete 767–816 (fair share, flex, `numCarsCharging` and its debug log) and `useFlexAmpsToStartCharge` (:66, :99–101). `receive_slave_heartbeat` calls `self.master.observeChargingSessions()` where it called `num_cars_charging_now()`.
- Tests: `tests/unit/test_control_tick.py` (new); `gen2_helpers.py` (`drive()`, `tickThenBeat`, `offersThenBeat`; see Step 3); `test_charging_points.py`; `test_distributor_loop.py` (comment, and its `__new__` master gets `countSlaveTWC`-visible slaves); `test_amps_reconciler.py:107` and its `heartbeat` import of `drive`; `test_limit_wiring.py` (imports `drive` as `heartbeat`); `test_twcmaster_vin_confirmation.py:72,76`.

**Interfaces:**
- Produces:
  - `ControlTick(master, interval: float = 1.0)` (a `threading.Thread`, daemon, name `"ControlTick"`), with:
    - `pass_() -> None`: `controlPass` when `fakeMaster == 1`, then `housekeeping`. Each is wrapped in `try`, and a raise is logged at WARNING by type name;
    - `housekeeping() -> None`: one `processIPC()` call per tick. That is one IPC message a second instead of one per 25 ms; the PHP UI waits up to 5 s per query (`index.php:603`), so multi-query pages get slower but nothing breaks (accepted, F15);
    - `stop() -> None`: sets the stop flag and joins with a 2 s timeout.
  - `TWCMaster.controlPass(now: Optional[float] = None, distribute: bool = True) -> None`: gated on `countSlaveTWC() > 0`; in Task 3 it is the distributor only. Tasks 4 and 5 extend it.
  - `gen2_helpers.offersThenBeat(m, s, state, maxA, actA)` (see Global Constraints).
  - `TWCMaster.distributeEVSEPower() -> List[ChargingPoint]` (was `None`).
  - `TWCSlave.heardFrom: bool = False`.
  - `TWCMaster.observeChargingSessions() -> None` (serial thread only).
  - `TWCMaster.num_cars_charging_now() -> int`: `sum(s.isCharging for s in getSlaveTWCs())`, no side effects.
  - `TWCMaster.controlTick`, set by `TWCManager.py` (absent in unit tests).
  - `gen2_helpers.tickThenBeat(m, s, state, maxA, actA)`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_control_tick.py`).

```python
def test_teslaapi_disabled_install_uses_the_one_distributor():          # (b)
    m = pureGen2(feed=40)          # real TWCMaster, no TeslaAPI module, two charging slaves
    m.controlPass()
    assert [target(s) for s in m.getSlaveTWCs()] == [20, 20]   # target(s): _evseTargetAmps (T3), pointAmps (T4 on)
def test_flex_settings_are_read_but_ignored():                           # (c)
    m = pureGen2(feed=4, config={"greenEnergyFlexAmps": 3, "useFlexAmpsToStartCharge": True})
    s = charging(m, actual=2.0); m.controlPass(); assert target(s) == 0   # minAmpsPerTWC 6: below it is a stop
def test_a_policy_with_allowed_flex_evaluates_without_error():          # (c)
    # Policy with a custom Track Green entry carrying "allowed_flex": 5 applies; no master flex attribute exists
def test_num_cars_charging_now_has_no_side_effects():
    m.queue_background_task = Mock(); s.reportedAmpsActual = 10; m.num_cars_charging_now()
    assert s.isCharging == 0 and not m.queue_background_task.called
def test_get_status_does_not_start_a_session():                         # HTTP thread
def test_restart_with_a_car_charging_never_offers_zero():               # Review Focus 1
    # linkready (newSlave + send_master_heartbeat) -> controlPass -> first reply
    # (state 0x01, amps_max 40, actual 32) -> heartbeat payload == bytes(9)
    # -> controlPass -> heartbeat's amps bytes == 32 (T4: also s.offer.amps == 32)
def test_no_distribution_without_a_gen2_slave():                        # F2
    # a master with Gen3TWCs and VehicleEndpoints registered, a Fleet car at home, no slave:
    # controlPass sets no Gen3 unit target and no AMPS desire (no paid call)
def test_a_slave_deleted_mid_pass_does_not_break_the_pass():            # Review Focus 3
    # a ChargingPoint.setTargetPower spy calls m.deleteSlaveTWC(other) mid-pass; controlPass returns normally
def test_a_raising_pass_is_logged_and_the_tick_continues(caplog):       # Review Focus 3
    t = ControlTick(m, interval=0.01); m.controlPass = Mock(side_effect=[RuntimeError, None, None])
    t.start(); waitFor(lambda: m.controlPass.call_count >= 3); t.stop()
    assert "RuntimeError" in caplog.text
def test_housekeeping_runs_ipc_and_expiry_in_every_mode():
def test_the_serial_loop_no_longer_distributes_or_processes_ipc():      # static, TWCManager.py loop source
```

- [ ] **Step 2: Run** → FAIL (`controlPass`, `ControlTick` and `observeChargingSessions` do not exist; the pure-Gen2 test gets no target).
- [ ] **Step 3: Implement** as above.
  - In `receive_slave_heartbeat`, set `self.heardFrom = True`, call `self.master.observeChargingSessions()`, then keep `numCarsCharging = self.master.num_cars_charging_now()` (the min branch still reads it until Task 4).
  - The remaining `_centralized_target` read: when `_evseTargetAmps is None` (no pass has targeted this slave yet), skip the amps computation and leave `masterHeartbeatData` as it is (Review Focus 1); otherwise `desiredAmpsOffered = self._evseTargetAmps`. Never `or 0`. The min branch's flex clause (`desiredAmpsOffered + flex >= minAmpsToOffer and (useFlexAmpsToStartCharge or …)`, BASE `:820–825`) goes with flex; on the default path `flex` was already 0, so the branch's result is unchanged there.
  - `distributeEVSEPower` returns the points it built (`List[ChargingPoint]`), so later tasks never regroup; the `heardFrom` filter is in `Gen2TWCs.allEVSEs`.
  - **Test helpers (F1, F8).** At BASE, the test masters `drive()` serves have no `VehicleEndpoints`, so their beats ran the legacy fair share. After this task every beat in `drive()` redistributes, so `drive()` is **not** plumbing-only for every caller:
    - `drive()` becomes receive → `master.controlPass()` → send (the after-order of `tickThenBeat`).
    - Rows whose beats report `amps_max=0` with 0 A get a realistic `amps_max` (a real TWC echoes its last offer), PLUMBING-ONLY with that reason: `test_charging_reconciler.py:195` (`test_an_offer_starts_the_car_from_the_heartbeat`), `test_limit_wiring.py:304–320`, and parity :1206 (`test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit`, row 26). Row 26's command list and counts must come out identical; if they do not, stop and report (Global Constraints).
    - Rows that set a point's target by hand (`test_amps_reconciler.py:68–89`, parity :1089 `test_mode_2_twc_holds_the_target_until_the_car_rate_lands`) switch to `offersThenBeat`, PLUMBING-ONLY.
    - Any other row whose values move is INTENTIONALLY CHANGED (b) only if it is a TeslaAPI-disabled-install scenario; otherwise it is a defect.
- [ ] **Step 4: Run** `test_control_tick.py test_charging_points.py test_gen2_idle_minimum.py test_amps_reconciler.py test_charging_reconciler.py test_command_path_parity.py` → PASS.
  - `test_charging_points.py::test_pure_gen2_leaves_distributor_off` is INTENTIONALLY CHANGED (b). It is replaced by `test_teslaapi_disabled_install_uses_the_one_distributor`.
  - `test_twcmaster.py::test_set_allowed_flex` and `test_twcslave.py::test_slave_use_flex_amps_to_start_charge`: deleted, INTENTIONALLY CHANGED (c), replaced by `test_flex_settings_are_read_but_ignored`. The four `master.setAllowedFlex = Mock()` setups in `test_policy.py` (:273, :436, :532, :610) go: PLUMBING-ONLY.
- [ ] **Step 5: Full suite** → PASS. Map every touched test in the report.
- [ ] **Step 6: Commit.** `git commit -m "Run the one distributor on a 1 s control tick for every install"`

---

