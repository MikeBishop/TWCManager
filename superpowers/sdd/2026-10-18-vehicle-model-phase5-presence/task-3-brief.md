### Task 3: One applicability rule per message; the BLE ping; holds; hint endpoints gone (expected lib Δ ≈ +77)

**`Presence.applicable(master, vehicle, attempt) -> str`** returns `SEND`, `NOT_HERE`, `HOLD` or `HOME_NOW`. Stops are never gated.
- **Where it runs:**
  - The reconciler calls it in `beforeWrite` (`Reconciler.py:485`, extended past CHARGE_LIMIT to CHARGING and AMPS), after the attempt's read.
  - For AMPS, which never reads (`maxAge` None), it runs on registry state.
  - For a cloud raise or start, `wakeFirst` runs before the read. The verdict is taken after the wake and read; the wake counts against the paid budget (F3).
- **Inputs:** `plugged` = `pluggedNow(v)` after the read. `L` = `leaving(v)` and `A` = `arriving(v)`, each `-inf` when unset.

**Cells (F4).** Every cell is defined; ties → `HOLD` (F8).

| Message | HOME, plugged | HOME, not plugged | PRESUMED | NOT_HOME |
|---|---|---|---|---|
| start, amps | `SEND` | `NOT_HERE` | plugged → `SEND`; presumed plugged (a held car with no `unplug` mark; F20) → `SEND`; else `HOLD` | `NOT_HERE` |
| apply (non-restore limit) | `SEND` | `L == -inf` (no departure seen) → `SEND`; `A > L` → `SEND`; `L > A` → `NOT_HERE`; tie → `HOLD` | driving → `HOLD`; inside and parked is HOME by now; no usable location → plugged → `SEND`, else `HOLD` (logged once per desire); inside, not driving, not parked, no plug → `HOLD` | `NOT_HERE` |
| restore | `HOME_NOW` (clear the restore desire, `SATISFIED "home"`) | `L > A` → `SEND`; else `HOME_NOW` | `HOLD` | `SEND` |

`NOT_HERE` clears the desire and returns `SATISFIED "not here"`.

**Holds (F3):**
- `HOLD` returns `Outcome(SATISFIED, "held: <why>")` and keeps the desire.
- It sets `rec.heldAt = now` and **not** `settledAt`, so the `settledAt` gate (`Reconciler.py:294–299`) never applies to a held desire.
- `plan` re-plans a held desire only when `vehicle.lastObservedAt > rec.heldAt`, or when the desire changes. `Vehicle.lastObservedAt` is a new float, stamped by every `observe`, `seen=False` included (+2).
- **Paid budget:** any paid wake or paid read made for an attempt that then holds increments `rec.paidSpent`. Paid providers are skipped while `rec.paidSends + rec.paidSpent >= PAID_BUDGET = 4`.
- The "logged once per desire" flag is `rec.heldLogged`.

**Home from BLE (user, 2026-10-18: "BLE contact is definitely home just as TWC plug-in is").** In `noteObservation`'s lat/lon branch, call `learnHome` when the fix's source is `TeslaBLE` as well as when a TWC names the car (one condition). A BLE location read answers only within range, so its fix is home. Test: a BLE-sourced fix with no home set teaches home; a Fleet fix alone does not.

**The BLE ping (send sequence, step 1).**
- `Run.py` calls it before the provider call when the provider is `TeslaBLE`, the attempt is not a stop, and `presence == PRESUMED`.
- `TeslaBLE.ping(vin) -> bool` runs `tesla-control -ble … body-controller-state` through a new seam `_runPing(vin) -> Optional[bool]`, factored from `_fetch_state_json`'s runner.
- An answer observes `bleReach` True. No answer from VCSEC observes `bleReach` False (F9: definitive absence) and returns `Outcome(UNREACHABLE, "no BLE answer")`.
- **Paid path (step 2):** unchanged (F20). `freeFailed` opens it after `PAID_AFTER` of free failures since the first; a missed ping is one free failure.

**Parity harness (F5, PLUMBING-ONLY):** `realBle(m, answers=…, ping=True)` stubs `b._runPing = lambda vin: b.pings.append(vin) or ping`, where `ping` is True, False or a callable. Pings go to `b.pings`, so `b.runs` and `bleCommands` keep today's lists. PRESUMED BLE rows then match today's counts and timings; see "Parity rows traced".

**Restores and applies on the policy pass (E2):**
- `_restoreDeparted` restores held cars that are NOT_HOME, or HOME, not plugged, and `L > A`.
- `applyPolicyLimit` sets the policy desire for every `homeForLimits` car; `applicable` decides at send.
- There is no direct trigger from the unplug. The restore-reply exclusion is not built (F10).

**Arrivals (c):** `Targets.onArrival(master, vehicle)` sets that car's CHARGE_LIMIT desire to `policyLimit` as a decision (else `_restore`), when `presence == HOME`. Exactly one call per plug-in event (F20 dedupe):
- `recordVehicleVIN` (confirmed);
- `noteObservation`'s `"plugIn"` from a pushed source or `Gen3TWC`;
- Task 5's attribution winner. Gen3's rising edge no longer calls it: its `pluggedIn` True goes through `noteObservation`.

**Removed (d):**
- the `checkArrival` handler (`TWCManager.py:323–327`), with `TWCSlave.py:678` now queuing `{"cmd": "checkCharge"}` (F11; the webhook stays);
- `/api/checkArrival` and `/api/checkDeparture` (`HTTPControl.py:775–786`) → 404.

**Endpoints (j):**

    [VehicleEndpoint(v, order, master) for v in registry.vehicles()
     if not v.isAnonymous and pluggedHere(master, v)
     and order.candidates(v, SET_AMPS) and not (unknown and telemetrySaysPlugged(master, v))]

This comes after the unchanged `blind` check. `_telemetryPluggedIn` is replaced by `Presence.telemetrySaysPlugged`, which Task 4 also uses (F16).

**Logging (m):** each non-`SEND` verdict logs at INFO with `why(master, v)`.

**Files:**
- Modify:
  - `Vehicle/Presence.py`;
  - `Vehicle/Reconcile/Reconciler.py` (`beforeWrite`, `plan`, the record fields `heldAt`/`paidSpent`/`heldLogged`, `PAID_BUDGET`);
  - `Vehicle/Reconcile/Desired.py` (the record fields);
  - `Vehicle/Reconcile/Run.py`;
  - `Vehicle/Reconcile/Targets.py`;
  - `Vehicle/TeslaBLE.py` (`ping`, `_runPing`);
  - `Vehicle/Registry/Vehicle.py` (`lastObservedAt`);
  - `TWCMaster.py` (`recordVehicleVIN`);
  - `TWCManager.py:45, 323–327`;
  - `TWCSlave.py:673–679`;
  - `Control/HTTPControl.py:775–786`;
  - `EVSEInstance/VehicleEndpoint.py:164–198`.
- Tests:
  - `test_presence.py`;
  - `test_command_path_parity.py` (the `realBle` ping stub; new rows);
  - `test_limit_wiring.py:44–52`;
  - `test_vehicle_endpoint.py` (the helper `car(m, vin, home=True)`), `test_charging_points.py:116,132`, `test_gen2_idle_minimum.py:38,149,191,236`;
  - `test_telemetry_registry.py:262–266` (`telemetrySaysPlugged`);
  - `tests/integration/test_api_input_validation_extended.py:89–102` (deleted).

**Interfaces:**
- Produces:
  - `Presence.applicable(...) -> str`, `Presence.telemetrySaysPlugged(master, v) -> bool`;
  - `TeslaBLE.ping(vin) -> bool`, `TeslaBLE._runPing(vin) -> Optional[bool]`;
  - `Targets.onArrival(master, vehicle) -> None`;
  - `Vehicle.lastObservedAt: float`;
  - `PAID_BUDGET = 4`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_presence.py
def test_applicability_every_cell():                              # incl. ties -> HOLD and -inf
def test_a_presumed_car_is_pinged_first_and_an_answer_sends_free(requests_mock):
def test_one_missed_ping_does_not_open_the_paid_path(requests_mock):
def test_a_hold_reads_once_and_waits_for_pushed_evidence(requests_mock):     # Review Focus 4; seen=False push re-plans
def test_held_re_plans_stop_paying_after_the_budget(requests_mock):          # F3: <= 4 paid wakes+reads+sends per desire
def test_a_held_desire_is_not_blocked_by_settled_at():
def test_start_and_amps_need_a_plug_here():
def test_a_restores_own_ble_reply_re_applies_nothing():                       # L > A stands after contact
def test_a_plug_or_a_newer_arrival_cancels_a_pending_restore():
def test_arrival_is_one_decision_for_the_plugged_car_only():                 # (c), once per event
def test_power_start_still_queues_check_charge():                             # F11
def test_endpoints_list_cars_plugged_here_whatever_module_knows_them():      # (j)
def test_anonymous_00_edge_car_is_never_also_an_endpoint():                   # E3

# test_command_path_parity.py — new rows; each comment states its paid tuple
def test_box_2026_10_18_arrival_while_driving_sends_nothing_until_parked_then_ble_free(requests_mock):
    # NOT_HOME; 15:18 TeslaMate fix inside + state driving -> PRESUMED/HOLD (pings allowed, no command, no HTTP);
    # 15:21 state online + shift P -> HOME, A > L -> BLE charging-set-limit; paid == (0, 0, 0)
def test_ble_contact_while_driving_still_holds(requests_mock):               # F7
def test_arrive_park_ble_sets_the_limit_before_the_plug(requests_mock):      # (k)
def test_a_20_s_drive_inside_the_radius_between_policy_passes_is_seen(requests_mock):
    # HOME unplugged after an unplug at t0; pushed shift D at t+5, P at t+25 (inside); policy pass at t+30:
    # driveEnd t+25 > leaving -> apply over BLE; paid 0
def test_arrive_limit_set_then_shift_to_d_in_the_driveway_restores_over_ble(requests_mock):   # no Fleet request
def test_a_car_that_never_left_unplugged_for_hours_is_not_re_applied(requests_mock)
def test_leave_without_plugging_is_restored_by_fleet_once_the_fix_is_outside(requests_mock)  # 1 command, no wake
def test_presumed_fleet_only_car_gets_the_limit_through_the_paid_sequence(requests_mock)       # (b): states its tuple
def test_presumed_fleet_only_car_read_outside_is_sent_nothing(requests_mock)
def test_unplug_restores_over_ble_at_once(requests_mock)                      # scenario 7
def test_ble_gone_five_minutes_then_one_remote_restore(requests_mock)
def test_ble_only_departure_never_pays(requests_mock)
def test_replug_before_the_remote_restore_sends_none(requests_mock)          # scenario 8
def test_fleet_only_unplug_one_remote_restore_plug_one_remote_apply(requests_mock)   # scenario 17
def test_fleet_only_failed_remote_restore_is_retried_per_restore_retry(requests_mock)  # scenario 18 (Q8)
def test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing(requests_mock)   # scenario 1
def test_departing_car_is_never_presumed_present(requests_mock)               # scenario 19
def test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it(requests_mock)    # 9
def test_startup_wake_finds_the_car_unplugged_and_sends_nothing(requests_mock)   # 10
def test_startup_wake_finds_the_car_plugged_and_starts_charging(requests_mock)   # 11
def test_ble_silent_umc_car_with_telemetry_inside_radius_is_home(requests_mock)  # 13
def test_ble_plus_fleet_car_leaving_a_umc_is_restored_after_the_departure_read(requests_mock)
def test_2026_10_12_return_plugged_in_keeps_the_policy_limit(requests_mock)       # only if no row covers it
def test_2026_10_12_arrival_during_a_running_restore_ends_at_the_policy_limit(requests_mock)
def test_wake_only_a_home_car(requests_mock)                                   # x4
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `test_presence.py test_command_path_parity.py test_vehicle_endpoint.py test_charging_points.py test_gen2_idle_minimum.py test_limit_wiring.py test_telemetry_registry.py` → PASS. **No existing parity count or timing moves.** If one does, stop and report it with old, new and why.
- [ ] **Step 5: Grep** `checkArrival|_telemetryPluggedIn` → none. **Step 6: Full suite** → PASS. **Commit.** `git commit -m "One applicability rule per message; BLE ping for a presumed car; holds wait for evidence within the paid budget"`

**Test mapping (Task 3):**
- `test_periodic_reenforce_does_not_undo_an_adopted_limit`: `onArrival(m, v)` (PLUMBING-ONLY).
- The endpoint tests: attachments become HOME-plugged evidence (PLUMBING-ONLY).
- `test_telemetry_registry.py:262–266`: `telemetrySaysPlugged` (PLUMBING-ONLY).
- The two integration tests: INTENTIONALLY CHANGED (d).

---

