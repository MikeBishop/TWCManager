### Task 4: The Gen2 unplug rule with two filters, on `TWCSlave` (expected lib Δ ≈ +41)

```python
# TWCSlave class constants (evidence: phase5-unplug-evidence.md)
UNPLUG_DEBOUNCE = 60     # s of steady 00
PLUGGED_RUN = 60         # s of non-00 immediately before the 00 began
LINK_GRACE = 300         # s after the first heartbeat following a (re)link
```

**`TWCSlave.unplugStep(now) -> bool`** reads `reportedState` and `reportedAmpsMax`, and is True once per qualifying 00 run. Serial thread, no I/O.
- **Base rule:** the 00 held `UNPLUG_DEBOUNCE`, began after a non-00 run ≥ `PLUGGED_RUN`, and began ≥ `LINK_GRACE` after the link. `TWCSlave.linkReady()` re-arms the grace.
- **Filter (a), strict (F6):** `_beforeMax` is the slave's `reportedAmpsMax` on the last non-00 heartbeat. The run qualifies only if `_beforeMax > 0` and `reportedAmpsMax == 0` on the **first** 00 heartbeat.
  - An idle car already at 0 A never gives a TWC unplug; only telemetry can depart it.
  - Use the slave's field, never the master heartbeat's.
  - Log at INFO at every onset: `"TWC %s: 00 onset, max %.2f A before, %.2f A now"`, and the run's verdict.

**On True,** `TWCMaster._unplugged(slave)` runs on the serial thread with no I/O:
- **Filter (b):** `Presence.telemetrySaysPlugged(master, v)` (Task 3) → write nothing; log the veto.
- Otherwise `observe("pluggedIn", False, "Gen2TWC")`, which marks `"unplug"` (Task 2), on:
  - `v = registry.vehicleAt(twcid)` (a VIN car), or else
  - the single `candidates(master)` car (T12).
- Then `registry.endPlugSession(twcid)` (g).

**Q2:** delete `_plugSession(slaveTWC, False)` at charge stop (`TWCMaster.py:1340`). `recordVehicleSessionEnd`, `plugSessions += 1`, `lastVIN = currentVIN` and the VIN-query reset stay. The anonymous close at 00 (:1354–1356) stays.

**`Gen2TWC.vehicleKey`:** the `lastVIN` branch (:49–51) → `v = reg.vehicleAt(self.twcid)`; `return v.key if v else None`. F2 bounds the `twcVin` it relies on.

**The loop property** (Review Focus 1):
- Filter (a) is strict, and filter (b) vetoes.
- A restore never wakes.
- An arrival raise after a TWC 00 can only follow a real TWC unplug, which requires the max-amps drop.

**Files:**
- Create `tests/unit/test_gen2_unplug.py` (the rule through a real `Gen2TWC`).
- Modify:
  - `TWCSlave.py` (constants, `unplugStep`, `linkReady`, state in `__init__`, the call in `receive_slave_heartbeat`);
  - `TWCMaster.py` (:1340, `_unplugged`);
  - `EVSEInstance/Gen2TWC.py:37–52`;
  - `TWCManager.py` (linkready → `slaveTWC.linkReady()`).
- Tests: `test_registry_plug_sessions.py`, `test_gen2twc_provider.py`, `test_outcome_desired.py`, the lift tests in `test_amps_reconciler.py`, and `test_twcmaster_vin_confirmation.py` where they expect `twcVin` cleared at charge stop (F17).

**Interfaces:**
- Produces: `TWCSlave.unplugStep(now) -> bool`, `TWCSlave.linkReady()`, `TWCMaster._unplugged(slave) -> None`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_gen2_unplug.py
def test_00_with_the_max_amps_drop_after_a_plugged_run_is_one_unplug():
def test_00_without_the_drop_on_the_first_00_heartbeat_is_never_an_unplug():   # 47 A; and a drop on the 2nd heartbeat
def test_an_idle_car_already_at_0_a_never_gives_a_twc_unplug():                 # F6
def test_00_inside_link_grace_or_without_a_plugged_run_is_never_an_unplug():
def test_onset_logs_the_slave_max_amps(caplog):
def test_reported_once_per_00_run():
# test_presence.py (real master, drive())
def test_live_telemetry_plugged_vetoes_a_twc_unplug():
def test_charge_stop_keeps_twc_vin_until_the_unplug():                          # (g)
def test_vehicle_key_names_the_car_after_a_charge_stop_and_nobody_after_an_unplug():   # E5
def test_a_vinless_unplug_departs_the_only_candidate():                          # T12
def test_a_non_tesla_plug_departs_nobody():
def test_restart_steady_00_with_telemetry_plugged_is_home_and_restores_nothing():
# test_command_path_parity.py
def test_box_2026_10_18_departure_restores_over_ble_within_a_minute(requests_mock):
    # 13:08: VIN TWC at 03 with max 32 A, held (90, 50), BLE claimed, Fleet asleep, no telemetry; 00 with max 0.00 A on the
    # first 00; policy passes every 30 s: BLE charging-set-limit 90 at <= onset + 120 s; no wake; paid == (0, 0, 0); no re-apply
def test_box_2026_10_18_false_00_at_47_a_with_telemetry_plugged_is_no_departure(requests_mock):
    # 15:25:58-15:36:27: 00 at 47 A, TeslaMate live plugged_in true: no unplug mark, HOME, no command, paid 0
def test_box_2026_10_17_morning_wake_episodes_declare_no_departure(requests_mock):   # the 07:58:28-08:39:01 run table
def test_a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore(requests_mock):
    # 3 cycles 03 -> 00 (real drop) -> 03, BLE answers None while asleep, Fleet asleep: no wake on any channel; paid[1] == 0
def test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise(requests_mock):   # F6
    # car at 03 with max 0 A (offer 0), policy limit above the car's limit, no telemetry: 3 cycles 03 -> 00 -> 03:
    # no unplug, no attribution arrival, no BLE wake, paid 0
def test_no_gps_source_plug_unplug_cycle_end_to_end(requests_mock)            # scenario 15
def test_gen2_steady_00_after_link_does_not_block_startup_charging(requests_mock)   # scenario 12
def test_plug_in_on_a_vin_twc_comes_home_with_one_apply(requests_mock)             # scenario 2
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `test_gen2_unplug.py test_presence.py test_registry_plug_sessions.py test_gen2twc_provider.py test_outcome_desired.py test_amps_reconciler.py test_command_path_parity.py` → PASS. No existing parity count moves.
- [ ] **Step 5: Full suite** → PASS. **Commit.** `git commit -m "Gen2 unplug: a debounced 00 whose first heartbeat drops the slave's max amps from above 0 to 0, unless live telemetry says plugged in"`

**Test mapping (Task 4):**
- `twcVin` cleared at charge stop (`test_registry_plug_sessions.py`, `test_gen2twc_provider.py`, `test_outcome_desired.py`, lift tests): INTENTIONALLY CHANGED (g), replaced by `test_charge_stop_keeps_twc_vin_until_the_unplug`.
- `vehicleKey == lastVIN` while plugged: rewritten on a confirmed `twcVin` (PLUMBING-ONLY).

---


---
## Controller addendum (user approved the audit plan, 2026-10-19): build at ≤ +10 net lib
Read section "§4 Building Tasks 4–6 at ≤ 0 net → Task 4" of audit-report.md (same directory) and follow it where it differs from the text above:
- no parallel 00-run state machine on TWCSlave: put the 00-run onset, the max-amps-before capture and the 60 s debounce in `TWCMaster.observeChargingSessions`' existing per-slave loop, reusing one onset stamp;
- delete the charge-stop `_plugSession(slave, False)`, the `isAnonKey` 00 close if the filtered unplug subsumes it, and `Gen2TWC.vehicleKey`'s `lastVIN` branch — verify each first;
- filter (b) is `Presence.telemetrySaysPlugged`; the unplug write is `observe("pluggedIn", False, "Gen2TWC")` — noteObservation already marks `unplug` for Gen2TWC;
- LINK_GRACE reuses the slave's existing heard-from / first-reply time.
The filters themselves are unchanged from the plan (user rulings): (a) reportedAmpsMax > 0 on the last non-00 heartbeat and 0 on the first 00; (b) live telemetry pluggedIn=true vetoes.
