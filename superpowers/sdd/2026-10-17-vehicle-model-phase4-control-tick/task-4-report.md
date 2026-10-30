# Task 4 report: offers on the control tick, charging points own car amps, spike and dampening dropped

**Status: DONE_WITH_CONCERNS.** Commit **a84079f4** on `vehicle-model/phase4` (BASE 8c673fc7). Not pushed.
- Full suite: **1928 passed, 1 xfailed, 1 warning** (baseline 1911; the warning was already there).
- Parity: all 51 rows make the same requests, with the same counts, before and after.
- The concern: row 26's BLE order is back to the 1029809b order (first item under Concerns).

## Implementation

**`lib/TWCManager/TWCSlave.py`**
- Deleted:
  - everything in `receive_slave_heartbeat` after `observeChargingSessions()`: the target read, min/probe, the mode branches, the spike, the 5 s hold, dampening and flip tracking, the in-receive stop cancel and the payload build. The `print_status` tail stays.
  - `set_last_amps_offered`
  - the car-amps helpers (`_anonCars`, `_setCarAmps`, `_clearCarAmps`, `_carRateConfirmed`, `_queueChargeRate`, `_requestVehicleRateRaise`, `_resetVehicleRateRaised`), `_ampsKeys`, `APIcontrol`, the `vehicleRateRaised` init, `lastAmpsDesired`, `timeLastAmpsDesiredFlipped`
  - the stale "policy results" comment
  - the imports that became unused: `AMPS`, `known`, `satisfied`, `isAnonKey`
- Kept: `minAmpsToOffer` (F5), and `pluggedCars` with its imports (F22).
- Added:
  - `Offer` and `OfferContext` (NamedTuples, as the brief specifies)
  - class defaults: `pointAmps = 0`, `offer = None`, `plugSessions = 0`, `liftedSession = None`, `_lastKeys = ()`, `_cappedLogged = None`
  - `vehicleRateRaised`: a read-only property, `liftedSession == plugSessions`
  - `offerFor(target, ctx, now)`: the brief's code. It now holds the `lastAmpsOffered < 0` init.
  - `_capped(desired, total)`: the two BASE caps, with BASE's messages and log levels. The all-TWC INFO line logs only when the capped value differs from the last one logged. `_cappedLogged` resets when there is no cap, so a cap that lifts and comes back logs again.
- `send_master_heartbeat`:
  - reads `self.offer` into a local;
  - builds the payload with `bytearray(9)` when there is no offer, else `_amps_heartbeat(offer.amps)`;
  - then applies the override (unchanged), then the gates (unchanged, Task 5), then sends.

**`lib/TWCManager/EVSEInstance/Gen2TWC.py`**
- `setTargetPower` sets `self.pointAmps`.
- Deleted: `_evseTargetAmps`, `pointOwnsAmps` and the `lastAmpsDesired` compat write.
- Comments that named "the heartbeat" now name `offerFor`. `minAmps`, `maxOfferAmps`, `layerFloorAmps` and `_rangeOverride` are kept.

**`lib/TWCManager/EVSEInstance/ChargingPoint.py`**
- New module function `anonymousCars(master, slave)`: `_anonCars` moved here unchanged.
- `_carKeys()` returns the writable car members' keys. With no car member, it returns the Gen2 local member's VIN, or the `anonymousCars` keys for an anonymous key, or `[]`.
- `confirmed()` is BASE's `_carRateConfirmed`, run over `_carKeys()`.
- `setTargetPower`:
  - It layers whenever the local member has `pointAmps`, i.e. is a Gen2. A TWC-only point now takes the layered path. A Gen3 local member still takes the short path (advisor note 3).
  - **Car members** get their rate through `VehicleEndpoint.setTargetPower` (`"distributor"`).
  - **A car only the TWC names** (`mine`) is written by `own()` as `desired.set(k, AMPS, int(amps), "heartbeat")`, as BASE's `_setCarAmps` wrote it.
    - Each `own()` call first withdraws the keys in `_lastKeys` that have left `mine`, but only if `d.by == "heartbeat"` (F13). Then it sets `_lastKeys = mine`.
    - `own()` runs on the same occasions BASE's `_setCarAmps` did: each car-carries pass, and a lift.
  - **Zero target**: the local member and car members get 0. When the car carries (mode 2 or 3), the point withdraws its own `"heartbeat"` rates over `_lastKeys`, as BASE's `_clearCarAmps()` did over `_ampsKeys`.
  - **The TWC carries** (mode 1, or mode 3 at or above `layerFloorAmps`):
    - Car members get 0 (M4).
    - If `not local.vehicleRateRaised`, the point lifts. A car member is lifted unconditionally in mode 1, and in mode 3 only when its known request is below the offer (BASE). A TWC-only key is always lifted (BASE heartbeat). Each lift is `desired.set(..., wiringMaxAmps, "lift", lift=True)`.
    - When anything was lifted, `liftedSession = plugSessions`.
  - **The car carries**:
    - `liftedSession = None` on every such pass, for every point type (F6).
    - The local member holds `max(floor, amps)` with car members. A TWC-only point holds `watts` (BASE: see Deviations).
    - Car members get the rate; `own(amps, "heartbeat")` covers the rest.

**`lib/TWCManager/TWCMaster.py`**
- `controlPass(now, distribute)` takes the points from `distributeEVSEPower()`, or from `chargingPoints()` when `distribute=False`. It builds one `OfferContext`:
  - budget, `num_cars_charging_now()`, `chargeRateControl`, `getTotalAmpsInUse()`;
  - `confirmed`, keyed by `bytes(TWCID)`, for each point's Gen2 local member.
- For each slave in the `getSlaveTWCs()` copy:
  - skip it if `heardFrom` is False (F9);
  - else `slave.offer = slave.offerFor(slave.pointAmps, ctx, now)`;
  - then call `cancelStopCarsCharging(key)` when there is a key, `offer.amps > 0`, and we are not in the silence (`respondToSlaves == 0` and `respondToSlavesExpiry > now`) (F4, F7).
- `self._points` is gone (nothing read it).
- Deleted: `spikeAmpsToCancel6ALimit`, `getSpikeAmps`, `setSpikeAmps`.
- `observeChargingSessions`' session end bumps `plugSessions` in place of the reset call.
- The stale spike comment in `getMaxAmpsForTargetGridUsage` is reworded. The `distributeEVSEPower` docstring names `pointAmps`.

**Other files**
- `TWCManager.py`: the linkready `setSpikeAmps` block is dropped.
- `HTTPControl.py`: the spike checkboxes block is dropped.
- `debug.html.j2`: the "Spike Amps" row is dropped.
- `Gen2TWCProvider.py`: the `:84` comment now names `TWCSlave.offerFor, ChargingPoint`.
- `docs/Debug.md`: the "Spike Amps" section is gone, and so is the "Advanced Settings" heading it left empty.
- `docs/modules/Interface_RS485.md`: now says the offer is made "on every control tick (about once a second)".

## Tests and results

- **Focused:** `test_control_tick.py test_offer_characterization.py test_command_path_parity.py test_amps_reconciler.py test_charging_points.py test_gen2_idle_minimum.py test_twcslave.py test_twcmaster_vin_confirmation.py test_gen2twc_provider.py test_limit_wiring.py`: all pass.
- **Full suite**, `timeout 600 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest tests --ignore=tests/API --ignore=tests/integration --timeout=60 -p no:cacheprovider`: **1928 passed, 1 xfailed, 1 warning in 89.30s** (`scratchpad/t4_full2.txt`).
  - Arithmetic: 1911 + 13 characterization + 10 new tick tests − 5 deleted from test_twcslave − 1 net in test_amps_reconciler (2 replaced by 1).
- `test_no_legacy_command_paths.py` passes: there is no `targetAmps` in lib.
- Black: all 7 changed lib `.py` files are clean (`black --check`). Test files were not run through black (their dense one-line style is deliberate).

### TDD evidence

- **RED, before the lib change** (`scratchpad/t4_red.txt`): 25 failures across `test_control_tick.py` and `test_offer_characterization.py`.
  - 7: `'Gen2TWC' object has no attribute 'offer'`
  - 3: no `pointAmps`
  - `_setCarAmps` still present
  - `offer` text found in receive
  - lifts missing
  - At 8c673fc7 the characterization set fails only on the Task 3 one-beat lag: the first beat sends `00`.
- **BASE+after characterization**: 13 tests in `tests/unit/test_offer_characterization.py`, all using `tickThenBeat`, a real `TWCMaster`/`Gen2TWC`/registry/`DesiredStore`, `VehicleEndpoints` with TeslaAPI enabled, and spike settings 0.
  - **At 1029809b**: 13/13 passed (`scratchpad/t4_base_char.txt`). Method: a scratch detached worktree, with this file and Task 3's `gen2_helpers.py` copied in. The worktree was removed afterwards.
  - **After**: 13/13 passed.
  - The tests: `test_idle_twc_nobody_charging_sends_zero`, `..._probe_when_budget_per_car_exceeds_min`, `..._probe_zero_when_it_does_not`, `test_charging_twc_gets_whole_amps_of_its_share`, `test_a_decrease_within_5s_is_held_then_applied`, `test_all_twc_wiring_cap_uses_others_actual_draw_and_floors_at_twc_minimum`, `test_per_twc_wiring_cap`, `test_mode_2_offers_the_twc_max_once_the_car_rate_is_confirmed`, `test_mode_3_below_six_layers_the_car_and_holds_the_twc_floor`, `test_mode_1_lift_goes_once_per_session_for_a_twc_only_point`, `test_a_mode_2_to_1_switch_mid_session_lifts_again[False|True]` (F6, both point types), `test_a_twc_point_never_clears_a_vehicle_endpoints_rate` (F13).
  - `test_per_twc_wiring_cap` has its slave report 20 A max. At 1029809b an offer equal to `lastAmpsOffered` was never capped: that is the (e) bug, which with 40 A reported left a 40 A offer on a 16 A TWC.
- **New behaviour** (in `test_control_tick.py`; all failed before and pass after):
  - `test_heartbeat_before_the_first_tick_sends_no_change`
  - the rewritten `test_restart_with_a_car_charging_never_offers_zero`
  - `test_the_lift_survives_a_session_end_racing_the_tick`
  - `test_no_offer_or_cancel_for_an_unheard_slave` (F9)
  - `test_no_stop_cancel_during_the_mode_2_silence` (F7)
  - `test_wiring_cap_is_rechecked_when_others_draw_more` (e): 20 then 8, on 48 A
  - `test_green_policy_does_not_hold_a_car_below_the_minimum` (f)
  - `test_spike_settings_are_ignored` (a)
  - `test_no_car_amps_code_left_in_the_slave`
  - `test_receive_writes_no_offer`
  - `test_a_twc_with_no_car_key_rates_and_lifts_nothing`
- **Mutation checks** (sensitivity; reverted afterwards):
  - Withdrawing any non-lift rate (dropping the `"heartbeat"` label check) fails F13.
  - Removing both `liftedSession = None` sites fails F6 ×2 and `test_mode_3_lift_goes_once_per_range_entry_even_when_the_car_clamps_it`.

## Parity counts

- Request lists were recorded per test with `scratchpad/plug/paritycounts.py`: at 8c673fc7 (scratch worktree, since removed) and after. Files: `scratchpad/t4_parity_before.jsonl`, `scratchpad/t4_parity_after.jsonl`.
- **All 51 rows have identical request lists and counts** (`diff` is empty). No count moved.
- Row 26's BLE order did change (no HTTP is involved; see Concerns 1).

## Test map (deleted or rewritten)

| Test | Mapping |
|---|---|
| test_twcslave `test_slave_api_control_default` | Deleted, no replacement: the attribute is gone. `test_no_car_amps_code_left_in_the_slave` pins its absence |
| test_twcslave `test_slave_last_amps_desired` | Deleted. INTENTIONALLY CHANGED (f) |
| test_twcslave `TestVehicleChargeRateDesired::test_queue_charge_rate_sets_desired` | → `test_amps_reconciler::test_a_twc_only_point_sets_desired_and_the_lift_once` (7.9 → 7, `"heartbeat"`, no lift) |
| `…::test_raise_sets_a_lift_and_the_flag_at_once` | → the same test (32, `"lift"`, raised; a new session clears it) plus `test_the_lift_survives_a_session_end_racing_the_tick` |
| `…::test_no_car_key_sets_nothing_and_raises_no_flag` | → `test_control_tick::test_a_twc_with_no_car_key_rates_and_lifts_nothing` |
| `…::test_heartbeat_code_never_calls_set_charge_rate_inline` | Kept, unchanged |
| test_amps_reconciler `test_twc_only_point_keeps_the_heartbeat_path_under_mode_2` and `test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member` | → `test_a_twc_only_point_writes_the_cars_amps_under_mode_2` (same desired values: 10 `"heartbeat"`, then hold 10, then max; mode 3 4 A `"distributor"`) |
| `test_legacy_heartbeat_path_sets_desired_and_the_lift_once` | → `test_a_twc_only_point_sets_desired_and_the_lift_once`, through the point. PLUMBING-ONLY (same values) |
| `test_mode_1_twc_carries…` (:30, :34) | PLUMBING-ONLY: `_evseTargetAmps`/`pointOwnsAmps` → `pointAmps`; `_resetVehicleRateRaised()` → `plugSessions += 1` (a session end) |
| `:48, :50, :59, :63, :67, :76` | PLUMBING-ONLY: `_evseTargetAmps` → `pointAmps`, `pointOwnsAmps` dropped |
| `test_a_session_end_resets_the_once_per_session_lift` (:105) | PLUMBING-ONLY: `s.liftedSession = s.plugSessions` |
| `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0` (:157, :160, :165, :170) | PLUMBING-ONLY: `pt.setTargetPower((10 + i % 2) * 240)` on the anon point; `anonymousCars(m, s)`. `anonTwc` also returns the point |
| `test_an_anonymous_mode_1_lift_goes_to_the_plugged_in_car_only` (:175, :177) | PLUMBING-ONLY: `pt.setTargetPower` in mode 1 lifts. Same calls |
| `test_a_car_that_leaves_the_anonymous_set_loses_the_heartbeat_rate` (:181, :183) | PLUMBING-ONLY: `pt.setTargetPower` |
| `test_heartbeat_withdraws_its_rate_when_the_offer_drops_below_the_minimum` (:188) | PLUMBING-ONLY: the rate comes from a real beat at a 10 A budget (`amps_max=32`), not `_queueChargeRate`. Same values (10 → None → the lift survives) |
| `test_mode_3_lift_goes_once_per_range_entry…` (:199) | Unchanged (reads the property) |
| test_charging_points `ep()` | PLUMBING-ONLY: `del e.pointAmps` (was `pointOwnsAmps`) so a Mock local member does not layer |
| test_charging_points `_evseTargetAmps` asserts (×14), `s.pointOwnsAmps` (:177) | PLUMBING-ONLY: → `pointAmps`; `pointOwnsAmps` dropped |
| test_gen2_idle_minimum `heartbeat()`, `offers(spike=…)` | PLUMBING-ONLY: the beat ticks offers only between receive and send. `spike` is dropped; the two rows that asserted the same value spike on and off keep one assertion. No row asserted a spike value |
| test_gen2_idle_minimum `_evseTargetAmps` asserts | PLUMBING-ONLY → `pointAmps` |
| test_gen2twc_provider:192 | PLUMBING-ONLY → `pointAmps` |
| test_command_path_parity :897/:902/:1087 | PLUMBING-ONLY → `s.pointAmps` (values 6, 10, 10). See Deviations |
| parity `test_mode_2_twc_holds_the_target_until_the_car_rate_lands` | PLUMBING-ONLY: `offersThenBeat` (it sets the target by hand; preflight finding 1). Counts unchanged |
| parity row 26 | Order restored to 1029809b's; the Task 3 `(d)` annotation and timing assertion are removed. See Concerns 1. Counts unchanged |
| parity Row 25 comment | "_anonCars" → "anonymous fan-out" (grep hygiene) |
| test_control_tick `target()` | → `pointAmps`; `test_an_unheard_slave_gets_no_offer` asserts `offer` |
| test_control_tick `test_restart_with_a_car_charging_never_offers_zero` | Rewritten for the `offer` path. The synchronous helper now sends 32 on the first reply's beat (no one-beat lag in-helper). The pre-tick `00` case moved to `test_heartbeat_before_the_first_tick_sends_no_change`. Both of its invariants (never 0 A; `00` before any offer) are kept |
| test_twcmaster_vin_confirmation `test_charging_session_begins_and_ends_anonymous_vehicle` | PLUMBING-ONLY: `s.plugSessions = 0` on its Mock slave; now also asserts the bump |
| test_limit_wiring:308 | Unchanged (reads the property) |
| test_twcmaster:600–670 | Unchanged (F12) |

## Thread ownership (TWCSlave fields touched)

| Field | Writer | Readers |
|---|---|---|
| `offer` (immutable `Offer`) | tick (`controlPass`) | serial (`send_master_heartbeat`, one local read) |
| `pointAmps` | tick (`Gen2TWC.setTargetPower` from the distributor); also a reconciler lane via `Gen2TWCProvider.setAmps` (F14, benign: the next pass overwrites it) | tick |
| `lastAmpsOffered`, `timeLastAmpsOfferedChanged` | tick (`offerFor`, which includes the −1 init) | serial (the Task 5 gates), `/api`, WebIPC |
| `liftedSession` | tick (`offerFor`, `ChargingPoint`) | tick |
| `plugSessions` | serial (`observeChargingSessions`) | tick (`vehicleRateRaised`) |
| `_lastKeys` | tick (`ChargingPoint.own()` only) | tick |
| `_cappedLogged` | tick | tick |
| `masterHeartbeatData` | serial (`send_master_heartbeat`) | serial (`print_status`) |
| `reported*`, `heardFrom`, `isCharging`, sessions | serial | tick (reads only) |

- `cancelStopCarsCharging` now runs on the tick, not the serial thread. It was already cross-thread into `reconciler.cancel` at BASE, so there is no new exposure.
- No new locks. No I/O under a lock.

## Lib delta

- `git ls-files lib | grep '\.py$' | xargs cat | wc -l`: **27,383 → 27,090 (−293)**. Expected ≈ −320.
- `git diff --shortstat 8c673fc7 -- lib`: 8 files changed, 251 insertions(+), 550 deletions(-).
- The shortfall comes from the generalized `ChargingPoint` (≈ +118 gross: own-rate bookkeeping, `_carKeys`, `confirmed`, `anonymousCars`), the two NamedTuples and `_capped`.

## Self-review

- **Each brief item is done.** The only remaining grep hits are tests that assert absence (`test_control_tick`) and the spike settings tests write on purpose: the (a) test, and the characterization fixture, which sets them to 0 so the 1029809b run is spike-free. `docs/Debug.md` is out of the hits.
- **Equivalence with BASE.** Checked branch by branch, case by case:
  - the TWC-only zero, mode-1, mode-2 and mode-3 handoffs;
  - car-member lifts (mode 1 unconditional, mode 3 gated on the request);
  - the mode-2 → 1 switch;
  - the session-end re-lift;
  - the leave-the-set withdrawal (own label only).
- **YAGNI.** `self._points` was removed because nothing read it.
- **Pristine output.** The full-suite output contains only the existing warning.

## Deviations from the brief's literal text

1. **Parity :897/:902/:1087 assert `s.pointAmps`, not `s.offer.amps`.** Those tests only call `pt.setTargetPower` and reconciler passes; no tick runs, so `offer` is `None`. `pointAmps` is the exact rename of `_evseTargetAmps` (same writer, values 6/10/10).
2. **A TWC-only point holds `watts` in the car-carries branch**, not `max(floor, amps)`. This keeps BASE's heartbeat value in the one case where they differ: a protocol-1 TWC (minimum 5) with `minAmpsPerTWC=5` in mode 3 below 6 A, which offers 5, not 6. A point with car members keeps the floor.
3. **On a zero target, "heartbeat" rates are withdrawn only when the car carries (mode 2 or 3), and only over `_lastKeys`**, as BASE's `_clearCarAmps()` did over `_ampsKeys`.
   - `_lastKeys` means "the keys this point wrote", not "the current keys".
   - Reason: with two anonymous TWCs fanning out to the same car, an idle one must not withdraw the other's rate. My first version did; the F13 characterization caught it.
4. **`_cappedLogged` resets to `None` when there is no cap**, so a cap that lifts and comes back logs again.
5. **`docs/Debug.md` also lost the empty "Advanced Settings" heading.** `debug.html.j2` keeps its "Advanced Settings" heading and table header, now with no rows, because the brief says to drop only the row. A follow-up could drop the section.

## Concerns

1. **Row 26's BLE order is back to the 1029809b order, and I removed Task 3's `(d)` annotation.**
   - The coordinator should rule on this. Counts are identical (0 HTTP).
   - Before (8c673fc7): wake, set-limit 70, wake, **charging-start**, wake, **set-amps 32**.
   - After (= 1029809b): wake, set-limit 70, wake, **set-amps 32**, wake, **charging-start**.
   - Cause: the offer is now computed by `controlPass` after the reply in the same beat (receive → controlPass → send). So the anonymous lift is desired on the first reply's beat, as at BASE, and goes out before the start, which the limit gap holds back.
   - The test's expectation and comment are BASE's again. Task 3's "PR may mention row 26" item is moot.
2. **Behaviour notes, all benign:**
   - Between the first reply and the first tick (≤ ~1 s), `lastAmpsOffered` stays −1, because the init moved into `offerFor` per the brief. In that window the protocol-2 gates in `send_master_heartbeat` see −1. The only branch that can fire is `withdrawStartCharging`, which does nothing for a fresh slave. Task 5 moves the gates.
   - `print_status` now logs the previous beat's payload (send builds it after receive) and runs before the first tick too. Cosmetic.
   - `getTotalAmpsInUse()` now logs at DEBUG once per tick.
3. **Edge, not exercised by any test.** An anonymous TWC at 00 that still wants power (it echoes an offer), in mode 2, whose fan-out car also has a VehicleEndpoint that does not want power:
   - **BASE:** the distributor cleared the car's rate, then the heartbeat rewrote it. The desire flickered and was present between rounds.
   - **Now:** the TWC point writes the rate and the car's own point withdraws it in the same pass, so it is never present.
   - This is a consequence of the order change (d), and it errs toward not sending a rate. The PR may note it.
4. Lib −293 against an expected ≈ −320 (see Lib delta).
5. **PR body, "Not ported" section:**
   - (a) The 6 A spike workaround: settings ignored, debug checkboxes removed.
   - (f) Track Green dampening.
   - (e) The wiring caps are re-checked on every offer.
