### Task 5: Start/stop gates run on the tick (expected lib Δ ≈ −88)

`send_master_heartbeat` 541–658 decides the charging aspect for a protocol-2 TWC with a vehicle key:
- **stop** a car drawing > 4 A while offered 0, held for 60 s after an offer change and `startStopDelay` after a significant amps change;
- **start** when offered ≥ the minimum, drawing < 1 A and not in error (0x02);
- **withdraw** a start when offered below the minimum and not drawing.

All of that becomes one pure function on the slave, applied by `controlPass` after the offers and the positive-offer cancel (which Task 4 already moved). Like that cancel, the gates are **skipped during the chargeStopMode-2 silence** (`respondToSlaves == 0` with the expiry in the future), because BASE's `send_master_heartbeat` returned before the gate block then (:439–451, F7). The function reads `self.offer.amps` where BASE read `lastAmpsOffered` just set by `receive`, which is the same value BASE used. The 116-line comment block (the 2017 rationale) is cut to its one-paragraph rule.

**Files:**
- Modify `lib/TWCManager/TWCSlave.py`: delete 541–658; add `chargeGate`.
- Modify `lib/TWCManager/TWCMaster.py` (`controlPass`).
- Tests: `test_control_tick.py`, `test_charging_reconciler.py` (through `drive`, PLUMBING-ONLY).

**Interfaces:**
- Consumes: `Offer`, `controlPass` (Task 4).
- Produces: `TWCSlave.chargeGate(now: float) -> Optional[str]`, returning one of `"stop"`, `"cancelStop"`, `"start"`, `"withdraw"` or None. `controlPass` maps them to `stopCarsCharging(key)`, `cancelStopCarsCharging(key)`, `startCarsCharging(key)` and `withdrawStartCharging(key)`, for heard-from slaves only and not during the mode-2 silence.

```python
def chargeGate(self, now):
    key = self.vehicleKey
    if self.protocolVersion != 2 or key is None or self.offer is None:
        return None
    offered, actual = self.offer.amps, self.reportedAmpsActual
    if offered == 0 and actual > 4.0:
        hold = (now - self.timeLastAmpsOfferedChanged < 60
                or now - self.timeReportedAmpsActualChangedSignificantly < self.startStopDelay)
        return "cancelStop" if hold else "stop"
    if offered >= self.minAmpsToOffer() and actual < 1.0 and self.reportedState != 0x02:
        return "start"
    if offered < self.minAmpsToOffer() and actual < 1.0:
        return "withdraw"
    return None
```
  BASE's `or self.reportedAmpsActual < 4.0` inside the hold is unreachable under `> 4.0`, so it is dropped. Keep BASE's DEBUG "Don't stop charging TWC …" line in `controlPass` on `"cancelStop"`.

- [ ] **Step 1: Write the failing tests** (BASE+after characterization via `tickThenBeat`):
  - `test_a_car_drawing_over_4a_offered_zero_is_stopped_after_60s`
  - `test_the_stop_waits_start_stop_delay_after_a_significant_amps_change`
  - `test_offered_at_least_the_minimum_and_not_drawing_starts_the_car`
  - `test_an_error_state_is_not_started`
  - `test_offered_below_the_minimum_withdraws_a_pending_start`
  - `test_protocol_1_and_keyless_twcs_decide_nothing`
  - `test_no_gate_runs_during_the_mode_2_silence` (F7): BASE sends no heartbeat then, so no gate; after, `controlPass` skips them.

  New: `test_the_heartbeat_decides_no_charging` (static: `send_master_heartbeat` source has no `CarsCharging`/`StartCharging`).
- [ ] **Step 2: Run** → the characterization set passes at BASE; the static test fails on the branch.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_control_tick.py test_charging_reconciler.py test_command_path_parity.py` → PASS.
- [ ] **Step 5: Full suite** → PASS.
- [ ] **Step 6: Commit.** `git commit -m "Decide TWC start and stop on the control tick"`

---

