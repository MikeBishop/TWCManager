### Task 10: The spec's end-to-end scenarios, then the branch gate

**Files:**
- Test: `tests/unit/test_plug_presence_scenarios.py` (new). It wires a real `VehiclePresence` (FakeClock, `runPass` driven by the test), the real `PresenceHandlers`, a real `VehicleCommandQueue` drained synchronously, `VehiclePriority`, and a real `TeslaBLE` with `sendCommand`/`probePresence`/`_fetch_state_json` stubbed. It also wires a real `TeslaAPI` with `requests` stubbed, recording every POST URL.

**Interfaces:**
- Consumes everything above. It adds no library code. A failure here goes back to the task that owns the code.

- [ ] **Step 1: Write the scenario tests**

```python
def test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing():
    # HOME via BLE read, limit 50 held; TWC unplug -> DEPARTING; BLE restore fails (no reach);
    # location inside radius; 10 policy cycles of applyChargeLimit(50) (vin None) with prefer_ble and a Fleet token:
    assert ble_commands("charging-set-limit") == [] and fleet_posts("set_charge_limit") == []
    # BLE gone 5 min -> exactly one remote restore (limit -1), nothing else:
    assert fleet_posts("set_charge_limit") == [restore_of(V1)]
def test_plug_in_on_a_vin_twc_comes_home_with_one_apply():
def test_vin_less_single_candidate_plug_one_apply():
def test_vin_less_two_candidates_ble_pilot_one_apply():
def test_vin_less_ambiguous_plug_applies_to_nobody():
def test_supercharger_telemetry_plugged_is_not_home():
def test_unplug_restores_over_ble_at_once():
def test_replug_cancels_the_pending_remote_restore():
def test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it():
def test_startup_wake_finds_the_car_unplugged_and_sends_nothing():
def test_startup_wake_finds_the_car_plugged_and_starts_charging():
def test_gen2_steady_00_after_link_does_not_block_startup_charging():
def test_ble_silent_umc_car_with_telemetry_inside_radius_is_home():
def test_no_gps_source_plug_unplug_cycle_end_to_end():     # BLE + VIN-less TWC only; no telemetry, no API module
def test_fleet_only_unplug_one_remote_restore_plug_one_remote_apply():
def test_departing_car_is_never_presumed_present():
```

- [ ] **Step 2: Run them**

Run: `<PY> -m pytest tests/unit/test_plug_presence_scenarios.py -q`. Expected: PASS. Fix any failure in the owning task's code, with that task's commit style.

- [ ] **Step 3: Branch gate**

Run: `<PY> -m pytest tests/unit -q` → all passed, 0 failed.
Run: `<PY> -m black --check <every lib file changed since presence/2-charge-limits>` → clean.
Run: `git diff presence/2-charge-limits -- lib | grep -nE '^\+.*log.*(oken|Bearer)'` → review every hit. No hit may interpolate a token value.
Run: `git grep -nE 'ARRIVING|AWAY_AFTER_FAILED_PROBES|_failedProbes|_timeoutHome|presenceSources' presence/3-plug-presence -- lib` → no output (except the one warning string that names `presenceSources`).

- [ ] **Step 4: Commit**

Subject: `Test the plug-presence scenarios end to end, including 2026-10-11`.

---

## Branch `presence/4-fleet-rate-queue`

