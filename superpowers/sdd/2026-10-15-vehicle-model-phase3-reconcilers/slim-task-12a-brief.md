### Task 12a: Charging on/off as stateless desired state; the legacy charge path goes (expected lib Δ ≈ −850)

Each cycle the Gen2 heartbeat decides what the car on it should be doing. Points with only a vehicle member (a Fleet-only UMC car) have no start/stop decision-maker today: the distributor gives them `setTargetPower` only, and `ChargingPoint.start/stopCharging` has no caller (final-review M3). That stays so, and Phase 4's distributor owns it. Those cars never get a CHARGING desire, so no start or wake.
- Start: True while the point offers at least its minimum and the car draws nothing.
- Stop: False while the car draws against an offer below its minimum (today's 60 s heartbeat gates still apply).
- Neither: a pending start is cleared.

A send is gated only by the own-write stamp. When the car stamped "Stopped" later reads "Charging" from the app, the next eligible pass sends the stop again, as on main. There are no bounds, no adoption and no `offering`.

**Files:**
- Modify:
  - `TWCMaster.py` (`startCarsCharging`, `stopCarsCharging`, `cancelStopCarsCharging`);
  - `TWCSlave.py` (`receive_slave_heartbeat` observes `actualCurrent`; the start/stop/cancel calls pass `self.vehicleKey`; the zero-offer clear; delete the `stopAskingToStartCharging` uses);
  - `Policy/Policy.py` (delete the `stopAskingToStartCharging` loop);
  - `Vehicle/Providers/Gen2TWCProvider.py` (mode-2 start readiness).
- Delete (replaced in this task):
  - `car_api_charge` in TeslaAPI, TeslaBLE and HomeAssistant;
  - `TeslaBLE.startCharging/stopCharging/_stopAskingToStartCharging` (`_allVehicleTargets` waits for 12b: `setChargeRate` still calls it; pre-flight I1);
  - `HomeAssistant._vehiclesFor` (orphaned once `car_api_charge` goes; pre-flight M7);
  - `CarApiVehicle.stopAskingToStartCharging`, `TeslaAPI.findReason`;
  - the `charge` entries in the VCQ dispatch and `VEHICLE_COMMANDS`, and `VehiclePriority.car_api_charge`;
  - `car_api_available` in TeslaAPI and HA (no caller left after this task). Task 11's `updateChargeAtHome` loader replaces the vehicle-list load it did (C1).
- Test: `tests/unit/test_charging_reconciler.py`. Convert `test_twcslave.py`/`test_twcmaster.py` `queue_background_task({"cmd": "charge"...})` assertions to desired-state assertions.

**Interfaces:**
- Produces (`TWCMaster`):
  - `startCarsCharging(self, vin=None)`: `desired.set(v.key, CHARGING, True, "distributor")` for each `targetsFor(self, vin, START_CHARGING)`. Under mode 1 it keeps `Policy.clearOverride()`.
  - `stopCarsCharging(self, vin=None)`: the same with False. Under mode 1 it keeps the `stopTimeout`/`overrideLimit` logic; modes 2/3 no longer touch the bus here.
  - `cancelStopCarsCharging(self, vin=None) -> int`: `desired.clearIf(v.key, CHARGING, False)` plus `reconciler.cancel(v.key)` per target. It returns the count cleared.
- Produces (`TWCSlave`):
  - `receive_slave_heartbeat`: `v.observe("actualCurrent", self.reportedAmpsActual, "Gen2TWC", seen=False)` only when `registry.get(self.vehicleKey)` is not None (S1).
  - `send_master_heartbeat`: passes `self.vehicleKey` to stop, start and cancel, and sends nothing when the key is None. When it offers less than `minAmpsToOffer()` and the car is not drawing, it calls `master.desired.clearIf(self.vehicleKey, CHARGING, True)`.
- Produces (`Gen2TWCProvider.ready(vehicle, START_CHARGING)`): `stopMode() == 2 and settings.get("respondToSlaves", 1) == 0 and peek(key).lastStopProvider == "Gen2TWC"`. The slave is not required: it ages out about 26 s after a mode-2 stop (ledger L50).

- [ ] **Step 1: Write the failing tests.** These carry over from the original Task 8 with the same bodies minus bounds and `forced`:
  - `test_heartbeat_stop_is_sent_once_and_a_stale_read_does_not_reassert`
  - `test_heartbeat_skips_the_registry_write_for_a_pending_vin`
  - `test_heartbeat_readings_are_not_evidence_for_a_car_with_vehicle_reads` (paid counted)
  - `test_start_waits_five_seconds_after_a_limit_write_and_wakes`
  - `test_complete_or_disconnected_car_is_left_alone`
  - `test_stop_falls_to_fleet_after_60s_once` (Review Focus 1)
  - `test_disruptive_stop_waits_for_ble_only_when_ble_is_set_up_for_the_car`
  - `test_disruptive_stop_is_sent_once_until_new_evidence_then_reasserted`
  - `test_disruptive_stop_on_the_real_clock_is_sent_once`
  - `test_mode_2_start_after_a_ble_stop_goes_through_ble`
  - `test_heartbeat_stop_targets_the_anonymous_car`
  - `test_non_tesla_car_on_a_twc_gets_the_disruptive_stop_at_once`
  - `test_gen3_multi_unit_stop_uses_the_car_not_the_bus`
  - `test_a_free_success_puts_ble_first_again` (the success now comes from a BLE `DONE`, not `bleReach`)
  - `test_paid_calls_never_exceed_desired_changes`

  `shared_channel_health` becomes `free_channel` in these two: `test_shared_free_failure_lets_a_later_aspect_go_paid_at_once`, `test_free_failure_windows_run_concurrently_not_summed`. New or changed:

```python
def test_an_app_start_after_our_stop_is_stopped_again_once_per_newer_reading():
    ...; m.stopCarsCharging(VIN); r.pass_(); c.t += 30; v.observe("chargingState", "Charging", "TeslaMateVehicle")
    assert r.pass_() == 0                                                    # inside RETRY: a lagging report, not resent
    c.t += 31; assert r.pass_() == 1 and cmds(b) == ["stopCharging", "stopCharging"]
    for _ in range(5): c.t += 61; r.pass_()
    assert len(cmds(b)) == 2                                                 # no newer reading: our stamp holds

def test_zero_offer_clears_a_pending_start_and_sends_no_wake():             # Review Focus 3, paid counted
    from tests.unit.gen2_helpers import drive
    m, r, v, c = setup(fleet(O.Outcome(O.DONE))); s = onTwc(m, v); v.observe("chargingState", "Stopped", "TeslaAPI")
    m.startCarsCharging(VIN); m.setMaxAmpsToDivideAmongSlaves(0); drive(m, s, amps_actual=0.0)
    assert m.desired.get(VIN, CHARGING) is None
    for _ in range(5): c.t += 61; drive(m, s, amps_actual=0.0); r.pass_()
    assert f.calls == []

def test_twc_current_alone_never_restops_a_car_with_vehicle_reads():        # Review Focus 4
    ...; c.t += 30; v.observe("actualCurrent", 10.0, "Gen2TWC"); assert r.pass_() == 0 and len(b.calls) == 1

def test_cancel_drops_a_pending_stop_only(): ...                            # clearIf False + reconciler.cancel; a start untouched

def test_a_queued_start_is_withdrawn_when_the_offer_drops():                # pre-flight M7, threaded, paid counted
    ...; block_cloud_worker(); m.startCarsCharging(VIN); r.pass_()           # Fleet start queued behind a blocking attempt
    m.desired.clearIf(VIN, CHARGING, True); release_cloud_worker()
    assert calls(requests_mock, "wake_up") == [] and calls(requests_mock, "charge_start") == []

def test_fleet_only_car_with_a_pending_schedule_gets_no_start_or_wake():    # pre-flight H3, paid counted
    ...; v.observe("scheduledChargingPending", True, "TeslaAPI"); m.startCarsCharging(VIN)
    for _ in range(5): c.t += 61; r.pass_()
    assert calls(requests_mock, "wake_up") == [] and calls(requests_mock, "charge_start") == []

def test_mode_2_start_after_our_stop_needs_no_slave():                      # ledger L50
    ...; m.slaveTWCs.pop(s.TWCID); m.slaveTWCRoundRobin.remove(s); m.startCarsCharging(VIN); r.pass_()   # gone from getSlaveTWCs() too (pre-flight L6)
    assert m.settings["respondToSlaves"] == 1 and f.calls == []
```

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run the full suite** → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Start and stop charging as stateless desired state: decided each cycle, sent once per stamp, disruptive stops last, Gen3 per-unit stops via the car"`

