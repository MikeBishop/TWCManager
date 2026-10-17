### Task 12b: Amps as stateless desired state with layered actuators; the façade and the legacy queue mode go (expected lib Δ ≈ −800)

`setChargeRate`/`setAmps` were the last users of the façade, so everything legacy on the command path goes here.

**Files:**
- Modify:
  - `Vehicle/Registry/Fields.py`, `Sources.py` (`chargeCurrentRequest`);
  - `Vehicle/TeslaAPI.py` (`update_vehicle_data` observes `charge_current_request`), `TeslaBLE.py` (`state charge` → `chargeCurrentRequest`), `FleetTelemetryMQTT.py` (`ChargeCurrentRequest`);
  - `EVSEInstance/ChargingPoint.py` (`carriers`, layered `setTargetPower`), `Gen2TWC.py` (`pointOwnsAmps`), `VehicleEndpoint.py` (`setTargetPower` → desired; `REFRESH_SECONDS`, `_lastAmps`, `_lastQueuedAt` deleted);
  - `TWCSlave.py` (`_queueChargeRate`, `_requestVehicleRateRaise`, `_resetVehicleRateRaised`; the `__lastAPIAmps*` counters go).
- Delete (replaced in this task):
  - `setChargeRate` (+ `_chargeRateAccepted`, `_recordChargeRate`, `CHARGE_RATE_RESEND_AFTER`, `lastChargeRateSent*`) in TeslaAPI, TeslaBLE (+ `_stampWrite`, `_allVehicleTargets`) and HomeAssistant;
  - `TeslaAPI.wakeVehicle` and `_unavailableResult`;
  - `Vehicle/VehiclePriority.py`, its module-list entry (`TWCManager.py:85`) and its tests;
  - VCQ legacy mode (`resolve_module`, `_DISPATCH`, `_setAmps`, legacy `_key`/`_is_high_priority`, per-put `callback`, `cancel(cmd, match)`) and `test_vehicle_command_queue.py`, whose generic cases move first;
  - `TWCMaster.vehicleCommandQueue`, `VEHICLE_COMMANDS`, `queue_vehicle_command`, `_resolveVehicleCommandModule`, `calculateModulePriority`, `getModuleByPriority` and the `"priority"` key;
  - `TWCManager.py`'s legacy queue start/drain and `get_vehicle_module` (`checkCharge` calls each unsuppressed module's `updateChargeAtHome()` once);
  - `ProviderOrder.dispatch/_succeeded/_count`, `Provider.attempts()` and HA's override.
  - Move the still-valid assertions of `test_own_write_stamps.py`, `test_targeted_charge_limit.py` and `test_teslaapi_charge_vin.py` first, as before.
- Test: `tests/unit/test_amps_reconciler.py`; `test_charging_points.py`, `test_vehicle_endpoint.py`, `test_twcslave.py`, `test_registry_fields.py`, `test_carapivehicle_registry.py`, `test_telemetry_registry.py`.

**Interfaces:**
- As the original plan's Task 9, minus bounds. In detail:
  - `carriers()` maps `chargeRateControl` 1/2/3 to `(True, False)`, `(False, True)` and `(True, True)`.
  - `pointOwnsAmps` makes one writer per cycle.
  - In mode 3 the TWC holds its floor below range.
  - `VehicleEndpoint.setTargetPower` writes `desired.set(key, AMPS, max(1, amps), "distributor")`.
  - `_queueChargeRate(amps)` writes `desired.set(self.vehicleKey, AMPS, int(amps), "heartbeat")` unless `pointOwnsAmps`.
- The lift is a one-shot desire: `desired.set(key, AMPS, liftMax, "lift", lift=True)`, cleared by the reconciler once satisfied (Task 9).
  - `TWCSlave.vehicleRateRaised` stays a plain attribute, as on main. It is set when `_requestVehicleRateRaise` sets the desire and reset by `_resetVehicleRateRaised` on unplug.
  - On the `ChargingPoint` path (where `pointOwnsAmps` blocks `_requestVehicleRateRaise`), `ChargingPoint.setTargetPower` writes the lift desire itself. It also sets `local.vehicleRateRaised = True` and skips the lift while that flag is set: the mode-1 once-per-session lift. The kept test asserts `s.vehicleRateRaised`, not `bounds.lifted`.
  - So, as on main, an amps change the user makes after the lift is not undone. A distributor amps desire, as in mode 2 or mode 3 below the floor, is re-sent when a newer `chargeCurrentRequest` reading disagrees.
- `maxAge None` for `AMPS`: there is no read before a rate, so no `vehicle_data` precedes a Fleet rate.

- [ ] **Step 1: Write the failing tests.** These carry over from the original Task 9 with bounds assertions removed:
  - `test_mode_1_twc_carries_and_the_car_is_lifted_once_per_session` (plus: after the lift settles, `m.desired.get(VIN, AMPS) is None`)
  - `test_amps_use_the_cars_request_not_the_pilot` (the reading only causes a resend, never a bound)
  - `test_mode_3_layers_below_the_floor_and_holds_the_twc_at_its_floor`
  - `test_mode_2_car_carries_and_the_twc_offers_its_max`
  - `test_twc_only_point_keeps_the_heartbeat_path_under_mode_2`
  - `test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member`
  - `test_fleet_never_sets_a_rate_the_twc_covers_but_carries_a_lift`
  - `test_legacy_heartbeat_path_sets_desired_and_the_lift_once`

  New:

```python
def test_user_changed_amps_are_resent_on_the_next_reading_under_mode_2():   # as main: overridden
    ...; c.t += 61; v.observe("chargeCurrentRequest", 16, "TeslaAPI"); assert r.pass_() == 1 and b.calls[-1] == ("setAmps", VIN, 20)

def test_user_changed_amps_after_a_lift_are_left_alone():                  # main's once-per-session raise
    ...; c.t += 61; v.observe("chargeCurrentRequest", 16, "TeslaAPI"); assert r.pass_() == 0                # TeslaMate never publishes it (pre-flight L11)

def test_failed_paid_rate_retries_once_then_waits_for_a_new_value_or_a_newer_reading():   # paid counted
    ...; e.setTargetPower(10 * 240); r.pass_(); c.t += RETRY[AMPS]; r.pass_(); assert len(f.calls) == 2
    c.t += 3600; r.pass_(); assert len(f.calls) == 2
    e.setTargetPower(11 * 240); r.pass_(); assert len(f.calls) == 3

def test_unchanged_rate_is_never_resent(): ...                              # replaces the 600 s refresh; paid counted
def test_fluctuating_offer_sends_at_most_one_rate_per_15s(): ...            # pre-flight I6: 1 h of changing targets <= 240 set_charging_amps, as main
```

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: carriers` / `KeyError: chargeCurrentRequest`).
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run the full suite** → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Amps as stateless desired state with layered actuators: the point owns the car's rate, the TWC holds its floor below range, the lift is one-shot"`

