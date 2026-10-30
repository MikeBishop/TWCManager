### Task 1: Every RS-485 write goes through the serial loop's outbox; VIN check digit compacted (expected lib Δ ≈ −50)

Today five paths write to RS-485 from other threads:
- HTTP `sendTWCMsg`, `sendStartCommand` and `sendStopCommand`;
- the background thread's `checkVINEntitlement` stop, `getLifetimekWh` and `getVehicleVIN`.

A write in the middle of a slave's reply corrupts both messages. All of them now enqueue, and the serial loop sends them at the top of a pass, where it already sends its own periodic messages.

`Gen2TWCProvider`'s mode-3 stop uses the same outbox, so the `stopRequested` flag goes. The background tasks stay because they keep their dedupe and delay (`getVehicleVIN` delay=5 for VIN confirmation). Only the send inside them changes.

**Extra saving:** the VIN check digit (≈ 80 lines, one table entry per line) becomes one function in `Registry/VIN.py`.

**Files:**
- Modify `lib/TWCManager/TWCMaster.py`: add `_outbox`, `sendRS485` and `flushRS485`. `getSlaveLifetimekWh` (:713–725), `getVehicleVIN` (:832–847), `sendStartCommand` (:1803–1811) and `sendStopCommand` (:1813–1823) call `self.sendRS485`.
- Modify `lib/TWCManager/TWCManager.py`:
  - call `master.flushRS485()` in the serial loop right after the `time.sleep(0.025)` and stall check (≈ :897);
  - VIN rx (:1488–1570) uses `vinCheckDigitValid`.
- Modify `lib/TWCManager/Control/HTTPControl.py:941–943`: `master.sendRS485(master.getModuleByName("TWCProtocol").createMessage(packet))`.
- Modify `lib/TWCManager/Control/WebIPCControl.py:258`: `self.master.sendRS485(twcMsg)`.
- Modify `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py:111–115`: mode 3 → `self.master.sendStopCommand(slave.TWCID)`; return `Outcome(DONE, "queued")`, unchanged.
- Delete `stopRequested` from `TWCSlave.py:36–38` and `:434–437`, and from `Gen2TWC.py:42–44`.
- Modify `lib/TWCManager/Vehicle/Registry/VIN.py`: add `vinCheckDigitValid`.
- Modify `lib/TWCManager/TWCManager.py` shutdown: a final `master.flushRS485()` right before `master.getInterfaceModule().close()` (≈ :2060), so a mode-3 stop that `reconciler.drain` delivers is sent (F16).
- Tests: `tests/unit/test_rs485_serial_only.py` (new), `test_gen2twc_provider.py:176`, `test_charging_reconciler.py:55,56,107,126` and `test_provider_outcomes_local.py:49,51,98` (they assert `stopRequested` or a heartbeat-sent stop: rewrite to `m._outbox` / `m.flushRS485()`, PLUMBING-ONLY, F11), `test_twcmaster_vin_confirmation.py`, `test_registry_vehicle.py` (or the VIN test home).

**Interfaces:**
- Produces:
  - `TWCMaster.sendRS485(msg: bytes) -> None`: any thread. `collections.deque.append`, no lock.
  - `TWCMaster.flushRS485() -> int`: serial thread only. It pops and sends with `getInterfaceModule().send(msg)` in FIFO order and returns how many it sent.
  - `vinCheckDigitValid(vin: str) -> bool`: upper-cases its input (BASE upper-cased `potentialVIN` first, :1495), then True for a 17-character VIN whose ISO 3779 check digit (position 9; `X` = 10) matches. It is False for any character outside the transliteration table, as at BASE (F20).
  - The caller keeps BASE's branches exactly: a length other than 0 or 17 is invalid; a **length-0** VIN (non-Tesla car or CAN disabled) still stops querying (`lastVINQuery = 0`, `vinQueryAttempt = 0`); only the 17-character check moves into the function.
- `sendStopCommand(subTWC=None)` and `sendStartCommand()` keep their signatures; they now enqueue.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/unit/test_rs485_serial_only.py
def test_http_start_and_stop_are_queued_not_sent():
    m, iface = masterWithTwoSlaves()            # real TWCMaster, Mock Interface
    m.sendStartCommand(); m.sendStopCommand(b"\x82\x44")
    assert iface.send.call_count == 0
    assert m.flushRS485() == 3
    sent = [c.args[0][:2] for c in iface.send.call_args_list]
    assert sent == [b"\xfc\xb1", b"\xfc\xb1", b"\xfc\xb2"]

def test_vin_query_and_kwh_poll_are_queued():
    m, iface = masterWithTwoSlaves()
    m.getVehicleVIN(b"\x82\x44", 0); m.lastkWhPoll = 0; m.getSlaveLifetimekWh()
    assert iface.send.call_count == 0 and m.flushRS485() == 3

def test_only_serial_thread_code_writes_rs485():
    # AST scan of lib/TWCManager: a call to .send( whose receiver is
    # getInterfaceModule(), getModulesByType("Interface")[0]["ref"] or
    # getModuleByName("RS485") appears only inside TWCMaster.flushRS485,
    # send_master_linkready1/2, send_slave_linkready, TWCSlave.send_master_heartbeat,
    # TWCSlave.send_slave_heartbeat, or TWCManager.py module level (the loop)
    assert offenders() == []

# test_gen2twc_provider.py (rewrite of :176)
def test_mode_3_stop_is_queued_for_the_serial_loop():
    ...; assert p.stopCharging(VIN) == O.Outcome(O.DONE, "queued")
    assert [msg[:2] for msg in m._outbox] == [b"\xfc\xb2"]

# VIN
@pytest.mark.parametrize("vin,ok", [("5YJ3E1EA1KF000001", <BASE answer>), ("1M8GDM9AXKP042788", True),
                                    ("1M8GDM9A1KP042788", False), ("5YJ3E1EAIKF000001", False)])
def test_check_digit_matches_the_old_inline_rule(vin, ok):
    assert vinCheckDigitValid(vin) is ok and vinCheckDigitValid(vin.lower()) is ok
def test_an_all_empty_vin_still_stops_querying():   # BASE len-0 branch, through the real rx path
def test_shutdown_flushes_the_outbox():             # static: flushRS485() precedes getInterfaceModule().close()
```
  Fill `<BASE answer>` by running the BASE inline rule (copy it into the test as `_baseRule` for the parametrized cross-check, then delete the copy in Step 3). Add `test_check_digit_agrees_with_the_base_rule_on_10k_random_vins` (seeded `random`), which compares `vinCheckDigitValid` against `_baseRule`. Keep that test.

- [ ] **Step 2: Run to verify they fail.** `$PY -m pytest tests/unit/test_rs485_serial_only.py tests/unit/test_gen2twc_provider.py -q`. Expected: FAIL (`sendRS485`/`flushRS485` do not exist; `offenders()` lists HTTPControl:941, :950 via `sendStartCommand`, and others).
- [ ] **Step 3: Implement.** As in Interfaces. In `TWCManager.py` the flush goes before the `fakeMaster == 1` block, so every mode drains it.
  - **Ordering note:** `sendTWCMsg` clears `master.lastTWCResponseMsg` before enqueuing (unchanged). The reply is captured as before, once the loop sends.
  - **Small fix:** HTTP `sendTWCMsg` used `getModuleByName("RS485").send`. The outbox uses the active interface, so a TCP-interface install no longer fails there. Note it in the report.
- [ ] **Step 4: Run** the new tests and `test_twcmaster_vin_confirmation.py` → PASS. In the VIN-confirmation tests, assertions on `queue_background_task(... "getVehicleVIN" ...)` stay as they are: the task still exists, so no edits are expected.
- [ ] **Step 5: Full suite** → PASS. Grep `stopRequested` → no hits.
- [ ] **Step 6: Commit.** `git commit -m "Send every RS-485 message from the serial loop; compact the VIN check digit"`

---

