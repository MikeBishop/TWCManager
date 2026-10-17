# Slim Task 12b review: amps as stateless desired state; the legacy rate path goes

Range 8b22849..9d3fb64, worktree `scratchpad/wt-vm3`. Read-only. The tree was left clean; two throw-away probe tests were copied in, run and removed.

Suite at 9d3fb64: **1610 passed, 1 xfailed** (`tests --ignore=tests/API --ignore=tests/integration`), matching the report.

## Verdicts

- **(A) Spec compliance: PASS with deviations from the post-implementation rulings.** Every symbol on the brief's delete list is gone, and no lib or test code calls one. The brief's interfaces and all 13 listed tests are present. Two rulings made after the implementation are not met yet: the VIN-less fan-out shape (I2) and the read-only INFO hint (I3). One brief line is not met: in mode 3 a user's amps change after a lift is undone (I1).
- **(B) Quality and cost safety: NOT YET.** 0 Critical, 3 Important, 8 Minor.
  - Amps never wake through a billed provider.
  - Fleet rates are paced at 15 s per car, and an unchanged rate is never resent.
  - Gen3 does not regress.
  - Lock order and the serial thread are clean.
  - But the mode-3 lift on the ChargingPoint path has no once-per-session memory. It sends a paid command for every newer reading below the offer (I1).

Counts: **Critical 0, Important 3, Minor 8.**

## Checklist results

| Hunt item | Result |
|---|---|
| Deletions | All gone. Grep over lib/ and tests/ finds no caller of any of these: `setChargeRate`, `_chargeRateAccepted`, `_recordChargeRate`, `CHARGE_RATE_RESEND_AFTER`, `lastChargeRateSent*`, `_stampWrite`, `_allVehicleTargets`, `TeslaAPI.wakeVehicle`, `_unavailableResult`, `refuseCommandIfReadOnly`, `VehiclePriority` (module, list entry, tests), `resolve_module`, `_DISPATCH`, `_setAmps`, VCQ `_key`/`_execute`/callbacks/`drain_high_priority`, `vehicleCommandQueue`, `queue_vehicle_command`, `_resolveVehicleCommandModule`, `calculateModulePriority`, `getModuleByPriority`, the `"priority"` key, `stats`, `get_vehicle_module`, `dispatch`, `_succeeded`, `_count`, `attempts()` and HA's override, HA `_vehiclesFor`/`_call_service`/`_is_vehicle_connected`, `REFRESH_SECONDS`/`_lastAmps`/`_lastQueuedAt`, `__lastAPIAmps*`, `_vehicleRateRaiseGen`. The remaining hits are the debug API's command *names* (`"setChargeRate"`, `"wakeVehicle"`, Order.py:138/151), which the brief keeps; `TeslaBLE.wakeVehicle`, which stays; and dead test stubs (M5). |
| Paid rate sends | `MIN_SEND_GAP[AMPS] = 15` (Reconciler.py:71) is checked per car before any plan (Reconciler.py:331); the lift and the distributor share the one AMPS record and so share the gap. A desire is capped at 2 paid sends plus one re-arm. The pins: `test_fluctuating_offer_sends_at_most_one_rate_per_15s` (≤ 240/h), `test_unchanged_rate_is_never_resent` and `test_failed_paid_rate_retries_once_then_waits_for_a_new_value`. Main (TWCSlave.py:870-890 at origin/main) paced at 15 s and resent each value up to 5 more times, so this is cheaper than main in steady state. **Exception:** the mode-3 ChargingPoint lift (I1), and the anonymous fan-out multiplier (I2). |
| Wakes | None for amps on a paid path: `wake = … and (p.local or aspect != AMPS)` (Reconciler.py:459-461). `allowWake` returns True for AMPS, so only BLE (free) may wake. `maxAge None` for AMPS (Reconciler.py:462-466), so no `vehicle_data` read precedes a rate. The Fleet `setAmps` keeps main's < 5 A double send (TeslaAPIProviders.py:157-165). |
| Wiring safety | Mode 1: the TWC carries. Mode 2: the TWC offers max and the car carries, as main did. Mode 3 below the floor: the TWC holds `layerFloorAmps()` (6), not `wiringMaxAmps`, so it is *safer* than main, which offered `wiringMaxAmps` below 6 A. The worst case is 1 A over budget until the car's rate lands, because the distributor never gives a point less than `minPower` (5 A at the lowest). A zero offer stops the TWC and withdraws the car's rate. No sustained overshoot is new. M3 notes the one pre-existing case (mode 2 with no deliverable rate). |
| Gen3 | No regression. `layered = hasattr(local, "pointOwnsAmps")` (ChargingPoint.py:157) is False for a Gen3 unit, so the unit gets the whole target in every mode. No Gen3 file changed. NO_INDIVIDUAL_STOP is still applied (Reconciler.py:385-388). The cloud VIN path is untouched. The parametrised `test_correlated_gen3_car_joins_the_gen3_point_and_queues_no_amps[1,2,3]` pins this. |
| Mode 3 | TWCSlave keeps the literal `< 6` handoff (TWCSlave.py:875-877). The provider floor is `layerFloorAmps() = max(6, minAmpsToOffer())` (Gen2TWC.py:177-180), and `Gen2TWCProvider.ampsRange` uses it (Gen2TWCProvider.py:98). Pinned by `test_mode_3_floor_is_the_heartbeats_handoff_not_a_lower_twc_minimum`. |
| Threading | No lock is held across a call. ChargingPoint and TWCSlave do only store and registry dict work on the serial thread. `broadcastVehicles` → `candidates` → `ready` does no I/O and takes neither `settingsLock` nor `_bleLock` (TeslaBLEProvider.py:50-55, HomeAssistantProvider.py:52-67, TeslaAPIProviders.py:90-100). `master.updateChargeAtHome` runs on the background thread with no lock held (TWCMaster.py:492-510). No RS-485 I/O moved. |
| Size | **Honest: −820** (202 insertions, 1,022 deletions in `lib/**/*.py`; 28,892 → 28,072 by `wc -l` at both commits). Most of it is whole-symbol deletion: VehiclePriority 292, TeslaAPI 172, TeslaBLE 119, VCQ 108 net, HA 80. Reconciler.py at 599/600 is a sign: see M1. |

---

## Critical

None.

## Important

### I1. The mode-3 lift on the ChargingPoint path re-fires on every newer reading below the offer: a paid command per reading, and the user's amps are not left alone

**Headline.** With a reading every 15 s, it is **240 paid `set_charging_amps` per hour per car: about $0.24/h**. One example is a Telemetry source restamping an unchanged value (pre-flight I2). Nothing caps it per session; only the reading rate and the 15 s gap bound it.

**Evidence.**
- ChargingPoint.py:176-187 lifts in mode 3 whenever `k is not None and k < int(amps)`. `k` is the car's `chargeCurrentRequest` as believed, and nothing remembers that a lift was already sent this session. `local.vehicleRateRaised` is used only in mode 1 (ChargingPoint.py:183, 188-189).
- A Tesla clamps `charge_current_request` at its own maximum. Take a car whose maximum is below `wiringMaxAmps` (a 32 A car on a 40 or 48 A TWC, which is common), with a mode-3 offer above that maximum (charge-now, or strong surplus):
  1. The lift writes 40. Our stamp satisfies it and it clears.
  2. The next `vehicle_data` read shows 32 < offer, so a new lift desire is created, with a fresh budget (`newDesire`).
  3. Another paid `set_charging_amps` goes out, and the cycle repeats.
- Probe (temporary test, removed):
  - Fleet-only, mode 3, offer 30 A, the car clamps at 24: **12 paid `setAmps` in one hour** with one TeslaAPI reading per 5 min.
  - With a reading every 15 s (a Telemetry source restamping an unchanged value; see pre-flight I2): **240 per hour**.
  - At the default `chargeUpdateInterval = 1800` (TeslaAPI.py:138) it is about 2 per hour per car, for the whole session. BLE installs pay nothing, but the BLE worker churns.
- Main lifted once per mode-3 in-range entry: `vehicleRateRaised` was reset only at the `< 6` handoff (origin/main TWCSlave.py:862-905). The TWC-only heartbeat path in this branch still does that (TWCSlave.py:886-896). So the two paths now differ.
- The brief's Interfaces say: "as on main, an amps change the user makes after the lift is not undone". In mode 3 in range, a user's lowered amps is overridden at the next reading. `test_user_changed_amps_after_a_lift_are_left_alone` covers mode 1 only.
- Related (concern 3): mode 1 re-arms the lift at every *charging*-session end (TWCMaster.py:1326; the session ends after 5 s under 1 A, which includes a green-mode pause). With a clamping car, that is one more paid lift per session end that a reading separates from the last lift. It is bounded by reads, but it is more than main's once per process.

**Fix.**
- Mode 3 in range uses the same once-per-session flag as mode 1: `lift = not local.vehicleRateRaised and k is not None and k < int(amps)`, and set `local.vehicleRateRaised = True` when a lift is written in either mode.
- **The reset in ChargingPoint's below-floor branch is required, not optional** (`local._resetVehicleRateRaised()` where the car carries, ChargingPoint.py:192-195).
  - On the ChargingPoint path, the heartbeat's `< 6` handoff never fires. The point holds the TWC at `layerFloorAmps() ≥ 6`, so the heartbeat takes the TWC-controls branch and never calls `_resetVehicleRateRaised()`. `test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member` shows the heartbeat landing in the lift branch at a 6 A target.
  - Without this reset, a car rated to 5 A at the floor is never lifted again when the offer returns to range. That is a sustained undershoot.
  - Keep the session-end reset as well. The fix is about 4 lines in ChargingPoint.py:176-195.
- Optionally, gate mode 1 the same way (`k is None or k < int(amps)`), so a green-mode pause does not re-lift a car whose request already covers the offer.
- Tests (paid counted):
  - `test_mode_3_lift_goes_once_per_range_entry_even_when_the_car_clamps_it`: Fleet, mode 3, offer 30, a reading of 24 every 15 s for 1 h → `len(f.calls) == 1`. Then one below-floor pass (the car is rated to 5) and back in range → exactly one more lift, to `wiringMaxAmps`.
  - `test_user_changed_amps_after_a_lift_are_left_alone[mode3]`: parametrise the existing test over modes 1 and 3.

### I2. The VIN-less Gen2 fan-out does not follow the ruling: every at-home Fleet car is rated, N times paid

**Evidence.**
- TWCSlave.py:95-113 rates, in mode 2/3 for an anonymous key, every car `broadcastVehicles(master, SET_AMPS)` returns, minus cars a TWC names.
- Targets.py:44-57: that is every TeslaAPI car `atHome` (or still unlocated, `lat == 10000`) plus every BLE-claimed VIN, whether present or not.
- Each car has its own 15 s gap, so a household with N at-home Fleet cars pays up to N × 240 `set_charging_amps` per hour under a fluctuating offer. `test_an_anonymous_twc_rates_the_cars_main_s_broadcast_reached` passes only because it has one at-home car.
- **Mode 1 is affected too.**
  - `_requestVehicleRateRaise` goes through the same `_setCarAmps` (TWCSlave.py:118-121), so an anonymous Gen2 in mode 1 fans the paid lift out to every unnamed at-home Fleet car once per plug session.
  - Main paid for one lift, to `vehicles[0]`. Main's mode-1 raise was `_queueChargeRate(wiringMaxAmps)` with `getLastVehicle() == None`, through the same `setChargeRate(None)` path.
  - The existing test's last line checks only that VIN got the lift. The ruling text says "mode 2/3", but the N× cost is the same here, so it belongs to this finding and is not accepted.

**Main's exact behaviour** (origin/main):
- `_queueChargeRate` passed `getLastVehicle()` (TWCSlave.py:1240-1252). That is the TeslaAPI car matching `currentVIN`, else `lastVIN`, else `None`.
- VehiclePriority walked TeslaBLE (priority 20), then TeslaAPI (priority 10), stopping at the first success.
- `TeslaBLE.setChargeRate(None)` woke and rated **every VIN in `settings["Vehicles"]`** (free), and succeeded if any answered.
- `TeslaAPI.setChargeRate(None)` rated **`getCarApiVehicles()[0]` only**, at home or not (TeslaAPI.py:1787-1792), and only when BLE failed or was absent.
- So main paid at most once per send.

**Fix: the ruling's concrete shape.** It is about 15 lines in TWCSlave, replacing the `keys = [...]` comprehension at :106-111:

```python
def _anonCars(self):
    named = {s.vehicleKey for s in self.master.getSlaveTWCs()}
    cands = [v for v in broadcastVehicles(self.master, SET_AMPS) if v.key not in named]
    # Plugged in or charging by the latest vehicle-source reading
    # ("NoPower" and "Stopped" are plugged; "Disconnected" or unknown is not)
    plugged = [v for v in cands
               if (o := v.latestFrom("chargingState", VEHICLE_SOURCES_EXCLUDED)) is not None
               and o.value not in (None, "Disconnected")]
    if plugged:
        return plugged
    # None known: main's vehicles[0] (TeslaAPI's list order), one car at most
    api = self.master.getModuleByName("TeslaAPI")
    first = (api.getCarApiVehicles() or [None])[0] if api else None
    v = first and self.master.vehicleRegistry.get(first.VIN)
    return [v] if v is not None and v.key not in named and self.master.providerOrder.candidates(v, SET_AMPS) else []
```

- Use `_anonCars()` inside `_setCarAmps` for **every** `by` (heartbeat rate and lift alike), so mode 1's lift goes to one car.
- When the set shrinks, also withdraw the heartbeat desire on keys that drop out of it (`clearIf(k, AMPS, value)` for a non-lift desire `by == "heartbeat"`). Otherwise a departed car keeps a stale rate desire (see M2).
- Test `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0` (paid counted). Three at-home Fleet cars, one reading `chargingState == "Charging"`; 1 h of a fluctuating offer.
  - Only that car is rated, ≤ 240 sends, no wake.
  - With no car plugged, only `carApiVehicles[0]` is rated.
  - A named car is never rated.
  - A mode-1 leg: two unnamed at-home Fleet cars, one plugged in, and `_requestVehicleRateRaise()` followed by passes → exactly one lift `setAmps`, to the plugged car.

### I3. The read-only INFO hint is not restored (ruling: restore it now)

**Evidence.**
- `refuseCommandIfReadOnly` (8b22849 TeslaAPI.py:1227-1242) logged "Tesla API is read-only (no usable Fleet API token)… Commands need a Fleet API token or the TeslaBLE module" at INFO, once per Fleet slot change. It was deleted.
- An Owner-only install now has no SET_AMPS, START or STOP candidate: `FleetAPIProvider.available` is False (TeslaAPIProviders.py:103-109). The reconciler then says only "no provider can deliver" at **DEBUG** (Reconciler.py:390-392).
- The deleted `TestRefusalLogging::test_logged_once_per_state_change` and `test_resync_of_owner_token_does_not_log_again` pinned it.

**Fix.** Restore a 10-line `TeslaAPI.noteReadOnly(command)`: the deleted body without the return value, keyed on `fleetSlot.changes` via `self.refusalLoggedAt`.
- Call it from `FleetAPIProvider.available()` when `capability in COMMANDS`, the command slot is not usable and `self.carapi.readOnly`.
- `available()` is called on every broadcast and readiness check, so the slot-change key keeps it to one line per change. It costs no HTTP and no API error.
- Restore the two logging tests against `available()`:
  - `test_read_only_hint_is_logged_once_per_slot_change`: two `available(SET_AMPS)` calls give one INFO record; a Fleet slot change and another call give a second.
  - `test_resync_of_owner_token_does_not_log_again`.

---

## Minor

**M1. Reconciler.py is at 599/600. Move the pure belief and rule helpers into Rules.py.**
- `handsOff` and `allowWake` (Reconciler.py:137-171, about 35 lines) are rules.
- `_newer`, `_standIn`, `known`, `newerReading` and `reachedCar` (:87-134, about 48 lines) are belief helpers with no reconciler state.
- `VehicleEndpoint` (EVSE layer) imports `known` from Reconciler.py (VehicleEndpoint.py:15). That drags the reconciler thread, VehicleCommandQueue and threading into the EVSE layer. Moving `known` and its helpers to Rules.py, or to a small `Belief.py`, fixes that layering and frees about 80 lines.
- Do not raise the 600-line rule (I8 ruling).

**M2. The heartbeat's mode-2/3 amps desire is not withdrawn when the offer drops below the minimum (concern 6).**
- *Judgement:* a real but bounded inconsistency. It is harmless while the desire is satisfied.
- If the user then changes amps in the app, or the anonymous fan-out set changes, the desire lingers on a car that is not charging.
  - Paid, it is capped at 2 sends + 1 re-arm per desire.
  - Free over BLE, an unsatisfied desire is retried every `RETRY[AMPS] = 60 s`, with a BLE wake (`allowWake` AMPS on a local provider). That can keep an idle car awake overnight in green mode.
- The ChargingPoint path withdraws (VehicleEndpoint.py:143-150), and the heartbeat path should match.
- **Fix:** in the `desiredAmpsOffered < minAmpsToOffer` branch (TWCSlave.py:782-873), when `chargeRateControl in (2, 3)` and not `pointOwnsAmps`, clear the non-lift desire on the keys `_setCarAmps` would write. A `_clearCarAmps()` helper of about 6 lines, sharing the key resolution with `_setCarAmps`.
- **Test:** `test_heartbeat_withdraws_its_rate_when_the_offer_drops_below_the_minimum`: mode 2, TWC-only, `_queueChargeRate(10)`, then a heartbeat with the offer below the minimum → `desired.get(VIN, AMPS) is None`; a lift survives.

**M3. Mode 2 with a car member but no deliverable rate (pre-existing, for the record).**
- Under mode 2 the TWC offers `maxPower`, and only the car's rate caps the draw (ChargingPoint.py:192-195), as on main.
- If the car has a ready SET_AMPS candidate that keeps failing, the desire stops after 2 paid sends + 1 re-arm while the offer is steady. The car then draws its last setting: a sustained overshoot, as on main, which resent at most 5 times per value.
- Not new. Worth a Task-14 row ("mode 2 with an undeliverable rate is main parity, not safer").

**M4. In mode 3, an amps desire left by the below-floor branch survives a return to range when no lift is written.**
- ChargingPoint.py:174-190 never clears a non-lift desire on the TWC-carries path.
- If the floor-time rate was never delivered and `k` is stale but ≥ the offer, the reconciler keeps trying to set the car to the old floor amps. That is undershoot, so safe, but wrong.
- The same applies to a mode-3 → mode-1 switch while `vehicleRateRaised` is set.
- **Fix:** on the TWC-carries path, `clearIf` a non-lift AMPS desire before deciding on the lift (2 lines).

**M5. Dead legacy stubs in tests.**
- `m.stats = {...}`: teslatokens.py:93, test_wall_connector_vins.py:17, test_provider_tables.py:23, test_provider_registration.py:47.
- `m.queue_vehicle_command = Mock()`: test_gen2_idle_minimum.py:36, test_charging_points.py:122.
- `{"VehiclePriority": Mock(commandPolicy=...)}`: test_reads_no_wake.py:17.
- `{"name": "VehiclePriority", ...}`: test_provider_registration.py:55.
- They pass vacuously and mislead readers. Delete them in Task 13.

**M6. A brief test was renamed and narrowed.**
- The brief's `test_failed_paid_rate_retries_once_then_waits_for_a_new_value_or_a_newer_reading` is implemented as `…_waits_for_a_new_value` (test_amps_reconciler.py:107-113), with no newer-reading leg.
- Add: after the 2 sends, `c.t += RETRY[AMPS]; v.observe("chargeCurrentRequest", 9, "TeslaAPI"); r.pass_(); assert len(f.calls) == 3`, then a second such reading gives no 4th send (the once-per-desire re-arm).

**M7. `vehicleRateRaised` is reset at charging-session end, not at unplug (concern 3).**
- The brief says "on unplug". This codebase has no separate unplug event on Gen2: session end clears `currentVIN` and ends the registry plug session (TWCMaster.py:1310-1328), so the implementer's choice is defensible.
- Its cost consequence is folded into I1's fix: gating mode 1 on `k < amps` makes a green-mode pause free.
- Record the deviation in the plan.

**M8. Home Assistant is never tried for amps while Fleet keeps failing. This needs a ruling.**
- The reconciler takes `paid[0]` (Reconciler.py:427-429). Fleet gets 1 send plus 1 blind retry per value, then waits. A new value goes to Fleet again.
- BASE (VehiclePriority) walked on to HA after a Fleet failure.
- The deleted-test audit's probe found:
  - Fleet failing with 500: 2 Fleet sends and 0 HA in an hour.
  - Fleet refusing with 403: 1 Fleet send and 0 HA until the value changes.
- This is cheaper, but a Fleet outage with a working HA leaves the car's rate stale. In mode 2 the car then draws its last setting.
- **Proposal:** fall through to the next paid candidate once the first paid candidate has spent its 2 sends with no `paidReached`. Otherwise record it as intended.
- **Test:** `test_amps_fall_back_to_ha_after_fleet_spends_its_budget`, paid counted: Fleet answers 500 → ≤ 2 Fleet sends, then exactly 1 HA `setAmps`.

---

## Concern rulings check

| Concern | Status |
|---|---|
| 1. Gen3 never layers | Matches the ruling. Pinned for modes 1-3. |
| 2. The anonymous fan-out sends N× | **Deviation.** I2 gives the concrete shape. |
| 3. The lift resets at session end | M7, with its cost under I1. |
| 4. checkCharge reaches HomeAssistant | Fine. These are free REST reads. TeslaBLE has no `updateChargeAtHome`, so the BASE walk also reached TeslaAPI when BLE was first. Pinned by `TestCheckChargeRefreshesEachModuleOnce`. |
| 5. Read-only hint | **Deviation from the ruling.** I3. |
| 6. A heartbeat desire lingers | M2. Withdraw it. |
| 7. Reconciler.py at 599 lines | M1. Move helpers to Rules.py. |
| 8. Task 13 leftovers | Agreed. Add M5 to Task 13. |

## Deleted tests

The full mapping is in `slim-task-12b-deleted-tests.md`. It covers 100 deleted test functions: 99 deletions plus one class move, `TestVehicleChargeRateQueueing::test_heartbeat_code_never_calls_set_charge_rate_inline` → `TestVehicleChargeRateDesired::…`.

**Counts:** COVERED 56, PARTIAL 8, GAP 7, INTENTIONALLY CHANGED 10, PLUMBING-ONLY 19. Two of the GAPs are lost behaviour: the read-only hint, which is I3.

I spot-checked the replacement tests the audit relies on. All four exist at 9d3fb64:
- `test_low_amps_are_sent_twice_and_counted` (test_provider_outcomes_cloud.py)
- `test_amps_gap_is_fifteen_seconds` (test_limit_reconciler.py)
- `test_a_403_on_wake_refuses_wakes_only` (test_provider_tables.py)
- `test_update_settings_ignores_hand_edited_entries_without_a_key` (test_teslable_pairing_status.py)

Each GAP and PARTIAL has a proposed test with an assertion in that file.
