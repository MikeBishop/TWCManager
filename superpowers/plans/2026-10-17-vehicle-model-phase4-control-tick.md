# Vehicle Model Phase 4: the control tick — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every install runs one distributor on a ~1 s control tick, and the RS-485 loop does protocol work only.
- The per-slave allocation inside `TWCSlave` is retired. Its rules become distributor rules, each with a test.
- Every RS-485 write happens on the serial thread.
- Token refresh leaves the loop and is single-flight per slot (#690).

**Architecture.** One new thread, `ControlTick`, calls `master.controlPass()` about once a second. The pass:
1. groups endpoints into charging points;
2. runs the water-fill distributor;
3. turns each Gen2 TWC's target into a wire offer (`TWCSlave.offerFor`, the ported heartbeat rules);
4. publishes the offer as one immutable `Offer` per slave;
5. runs the start/stop gates (`TWCSlave.chargeGate`), which write charging desired state.

The heartbeat on the serial thread sends `slave.offer` and records observations. That is all it does.

A charging point owns its car's amps in every case: named car member, the TWC's own VIN, or the anonymous fan-out. `TWCSlave` keeps no car-amps code.

Other threads never write to RS-485 directly. They put messages in `master`'s outbox, and the serial loop drains it between heartbeats.

The EVSE scaffolding that existed only to switch between the two allocators goes: the `EVSEInstance`/`EVSEController` ABCs, `Gen2TWCs`, the `VehicleEndpoints` controller class and its cache.

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `pytest` (`tests/unit`), `requests_mock`.

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (amended 2026-10-17). It is binding in these sections:
- "Threading" (the table);
- "Everyone moves to the new cycle";
- "Charging points";
- "Idle TWCs keep their minimum";
- "Layered actuators";
- "A hand-set charge limit is adopted / Charging on/off and amps are never adopted".

**Inputs:**
- Roadmap Phase 4 row: `.superpowers/plans/2026-10-13-vehicle-model-roadmap.md`.
- Inventory: `.superpowers/gut-inventory.md`. This phase closes **A22 (#690)** and **A37** (RS-485 off-thread writes). It also lays the groundwork that **A15** (two-pass admission, now ngardiner/TWCManager#709, not in scope) needs.
- House style: the Phase 3 slim and Phase 3.5 plans.

**Ledger:** `.superpowers/sdd/2026-10-17-vehicle-model-phase4-control-tick/progress.md` (exists).

**Branch:** `vehicle-model/phase4` in `scratchpad/wt-vm4`, BASE **1029809b** (phase3.5 tip, PR #706).
- Lib at BASE is **27,425** lines (`git ls-files lib | grep '\.py$' | xargs cat | wc -l`); origin/main is 23,180.
- Phase 4 must end below 27,425. The projection is in "Line budget".

## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `tests --ignore=tests/API --ignore=tests/integration`.
  - BASE: **1868 passed, 1 xfailed** (run during planning). The full suite passes after every task.
- **Behaviour changes allowed: only these.** Each is named in the task that makes it, with its test. Anything else that changes is a defect.
  - (a) The 6 A spike workaround is dropped (user, 2026-10-17). The Phase 4 PR body must call this out for the maintainer, who may disagree. The `spikeAmpsProactively`/`spikeAmpsReactively` settings are then ignored.
  - (b) Installs with `vehicle.TeslaAPI.enabled: false` move from the legacy per-slave fair share to the one distributor (Decision 2). Every other install already runs the distributor at BASE, because TeslaAPI is enabled by default (`TeslaAPI.py:198`) and that registers `VehicleEndpoints`.
  - (c) **Flex is not ported** (user, 2026-10-17). `greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and a policy's `allowed_flex` are still read without error but ignored. On the default path flex was already zeroed whenever the distributor set a target (`TWCSlave.py:776`, since #483), so only TeslaAPI-disabled installs lose it (Decision 3).
  - (d) Gen2 target lag of up to one tick (~1 s), and the distributor runs once a second instead of once per full heartbeat round (≈ N × 1.1 s). The spec accepts it. As at BASE, nothing is distributed while no Gen2 slave is known (`countSlaveTWC() > 0`, `TWCManager.py:923`; ruling F2): Gen3-only and vehicle-only installs keep BASE's behaviour.
  - (e) The wiring cap is re-checked on every offer, not only when the offer changes (Decision 5).
  - (f) **Track Green dampening is not ported** (user, 2026-10-17). It held a drawing car at `minAmpsTWCSupports` for `startStopDelay` after its share crossed the minimum. On the default path it was mostly defeated at BASE: `Gen2TWC.setTargetPower` writes `lastAmpsDesired = target` every pass (`Gen2TWC.py:225`), so the flip check mostly compared the target with itself. The flip tracking (`lastAmpsDesired`, `timeLastAmpsDesiredFlipped`), the dampen rule and that compat write all go (Task 4). `startStopDelay` stays: the start/stop gates use it (Task 5) (Decision 9).
  - (a), (c) and (f) form the PR body's **"Not ported into the rearchitecture"** section (Task 6, Step 6).
  - Charging on/off and amps are never adopted from manual changes (spec amended). Nothing in this phase adds adoption.
- **Not in scope:** two-pass admission (#709), presence (Phase 5), the Vehicles tab (Phase 6) and any RS-485 protocol change (spec non-goal).
- **Cost.**
  - Prices: `vehicle_data` $0.002, wake $0.02, command $0.001. Lists, `vehicles/{vin}` and `live_status` are free.
  - No task may add a paid request.
  - `tests/unit/test_command_path_parity.py` request counts are not edited. Its three `s._evseTargetAmps` assertions (lines 892, 897, 1082) become `s.offer.amps` (PLUMBING-ONLY; the values 6, 10, 10 stay).
- **Gen3 stays whole:** the fake-Neurio solver, `WallConnectorVins`, `_correlate` and cloud VIN. Gen3 changes only its base class (Task 6).
- **Policies, templates, `/api` fields keep working.**
  - `Policy.policyValue` reaches module attributes by name. `master.allowed_flex`/`getAllowedFlex`/`setAllowedFlex` go with flex (c): no shipped policy, template or doc reads them through `policyValue`, and a policy dict's `allowed_flex` key is simply no longer read.
  - Old `config.json`/`settings.json` keys (`greenEnergyFlexAmps`, `useFlexAmpsToStartCharge`, `spikeAmpsProactively`, `spikeAmpsReactively`) load without error and are ignored; Task 6's `test_retired_settings_keys_load_and_are_ignored` pins it.
  - `/api/getSlaveTWCs` keeps `lastAmpsOffered` and `lastChargingStart`.
  - The status keys `amps_offered`, `amps_desired` and `cars_charging` keep publishing.
  - `WebIPCControl` keeps `lastAmpsOffered`.
- **Threading.**
  - Lock order: `TeslaBLE._bleLock → master.settingsLock → registry leaf`, and `TeslaAPI.vehicleListLock → settingsLock`.
  - New: `TeslaTokenSlot._cond` is a leaf. Nothing is acquired under it and no I/O runs under it.
  - No I/O under any lock. One exception is pre-existing and out of scope: `loadVehicleList` holds `vehicleListLock` across its list GET and refresh at BASE (`TeslaAPI.py:561`). Phase 4 does not widen it.
  - No RS-485 I/O off the serial thread.
  - Ownership after Task 4 (one writer each):
    - the **serial thread** writes `reported*`, `heardFrom`, `timeReportedAmpsActualChangedSignificantly`, `isCharging`/sessions/VIN state, `plugSessions` (a counter bumped at each session end), `historyAvg*` and `masterHeartbeatData`;
    - the **tick** writes `offer`, `pointAmps`, `lastAmpsOffered`, `timeLastAmpsOfferedChanged`, `liftedSession` and `_lastKeys`.
    - Exception (ruling F14): `Gen2TWCProvider.setAmps` (a reconciler lane thread) also writes `pointAmps` through `setTargetPower`. It is benign: the next pass overwrites it, and the offer is computed on the tick only.
    - `stopTimeout` already has two writers at BASE (getStatus/policy and the serial thread); after Task 5 they are the serial thread and the tick. No new exposure.
    - The once-per-session lift is `liftedSession == plugSessions`: the serial thread only counts sessions and the tick only records which session it lifted, so neither overwrites the other (replaces the two-writer `vehicleRateRaised` bool; Task 4).
  - `master.getSlaveTWCs()` returns a copy (Task 3). The tick never iterates the live round-robin list; Task 3 also points `WebIPCControl.processIPC`'s `getSlaveTWCID(i)`/`slaveTWCRoundRobin[i]` reads (:179–193) at that copy (ruling F15).
- **Grep scope for removed names**, run in every task: `git grep -nwE '<names>' -- lib html tests/unit tests/integration tests/API docs` (tests/unit included: ruling F11). Templates live under `lib/TWCManager/Control/themes`. Expect hits only in the definitions being removed.
- **Deleted-test rule.** Each task report maps every deleted or rewritten test to one of:
  - a replacement test;
  - PLUMBING-ONLY, with the reason;
  - INTENTIONALLY CHANGED, naming one of (a)–(f).
- **Test plumbing must not move a paid count** (ruling F1). If a plumbing change to a helper moves any request count in `test_command_path_parity.py` (row 26, `test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit` at :1206, in particular), stop and report; never re-tag it.
- **Characterization tests** marked "BASE+after" must pass on a scratch checkout of 1029809b **and** after the task. The report records both runs.
  - They pin the default (distributor) path: a master with `VehicleEndpoints` registered, spike settings `0` at BASE.
  - They reproduce BASE's observable order (ruling F8). At BASE the distributor ran at the start of a round, before the slave's heartbeat and reply: **distribute → receive → send**. After the task the reply is recorded, then the tick computes, then the heartbeat sends: **receive → controlPass → send**.
  - The helper `tickThenBeat(m, s, state, maxA, actA)` encodes both orders: `if hasattr(m, "controlPass")` it runs receive → `m.controlPass()` → send, else `m.distributeEVSEPower()` → receive → send. Task 3 adds it to `tests/unit/gen2_helpers.py`.
  - The helper `offersThenBeat(m, s, state, maxA, actA)` is the **offers-only** beat (ruling F1): receive → `m.controlPass(distribute=False)` → send, so a target a test set by hand (`pt.setTargetPower`) is not overwritten. At Task 3 (offers still in `receive`), `controlPass(distribute=False)` does nothing.
- **Line reporting.** Each task reports:
  - `git ls-files lib | grep '\.py$' | xargs cat | wc -l` before and after;
  - `git diff --shortstat <task BASE> -- lib`;
  - actual vs expected Δ.
- Python 3.8 syntax; `black` on touched files only. Commit trailer per the session's attribution reminder.
- **Real objects in cross-module tests:** a real `TWCMaster`, a real `Gen2TWC`, a real `VehicleRegistry`/`DesiredStore`, `teslatokens.new_api` and `requests_mock`. Never mock a success value the real method never returns.

## Review Focus

1. **Restart with a car charging: the first heartbeat before the first tick.** A slave linkready calls `send_master_heartbeat` at once (`TWCManager.py:1313`).
   - With `offer is None`, the heartbeat must send the idle `00` payload (no change), exactly as BASE's class-default `masterHeartbeatData`. It must never send `0` A, which would drop a charging car to the TWC minimum.
   - A slave not yet heard from (`heardFrom` False: linkready seen, no heartbeat reply yet) is skipped by the distributor, and `offerFor` is never called for it, so a tick landing between linkready and the first reply cannot publish 0 from the still-zero `reported*` fields. `heardFrom` is set in `receive_slave_heartbeat`; do not reuse `historyNumSamples` (`snapHistoryData` resets it) or `timeLastRx` (linkready sets it).
   - From Task 3 on, a `None` target means "keep the payload", never 0.
   - Tests: `test_restart_with_a_car_charging_never_offers_zero` (Task 3, re-run in Task 4) drives the real sequence: linkready → `controlPass` → first reply (state 0x01, amps_max 40, actual 32) → heartbeat sends `00` (not 0, not 6) → `controlPass` → `offer.amps == 32` (asserted on the offer: a matching amps_max makes `_amps_heartbeat` send "no change", ruling F17) and the wire byte pair is 32 A. Plus `test_heartbeat_before_the_first_tick_sends_no_change` (Task 4).
   - Pre-existing and not covered (F17): a slave heard before the Policy thread's first evaluation sets the budget (class default 0) gets offer 0 on its first pass, exactly as BASE's first round did.
2. **Sustained overshoot.** Two TWCs, a third car plugs in, a fourth draws more than its offer while ramping down.
   - Offers plus other TWCs' actual draw must never exceed `wiringMaxAmpsAllTWCs` beyond one tick. The only exception is the idle probe minimum, which is not counted (memory: derating).
   - Tests (Task 4):
     - `test_wiring_cap_is_rechecked_when_others_draw_more` (Decision 5);
     - `test_twc_offers_never_exceed_the_budget_or_wiring_across_point_shapes` (exists; kept).
3. **The tick and the serial thread share slaves.**
   - A slave deleted mid-pass (`deleteSlaveTWC` after 26 s silence) must not raise in the tick.
   - A raising pass must not kill the tick.
   - Tests (Task 3): `test_a_slave_deleted_mid_pass_does_not_break_the_pass` and `test_a_raising_pass_is_logged_and_the_tick_continues`.
4. **The anonymous TWC still rates the right cars.** Car-amps moves from `TWCSlave._setCarAmps` to `ChargingPoint`, so the fan-out (plugged-in cars, else `vehicles[0]`) and the "a car that leaves the set loses its rate" rule must survive.
   - Tests: `test_amps_reconciler.py::test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0`, `test_a_car_that_leaves_the_anonymous_set_loses_the_heartbeat_rate` and `test_an_anonymous_mode_1_lift_goes_to_the_plugged_in_car_only`.
   - Their assertions are unchanged. Only the setup goes through `controlPass()`.
5. **Paid calls under mode 1 while the TWC carries.** Fleet never gets a rate the TWC covers. A lift goes once per session.
   - Tests: `test_amps_reconciler.py::test_fleet_never_sets_a_rate_the_twc_covers_but_carries_a_lift` and all of `test_command_path_parity.py`, counts untouched.

---

## Where every retired piece goes (checked against 1029809b)

| Piece (file:line at BASE) | Callers outside it at BASE | Destination | Task |
|---|---|---|---|
| Legacy fair share and flex, `TWCSlave.receive_slave_heartbeat` 767–816 (`numCarsCharging`, `_centralized_target is None` branch, debug log) | none | Fair share: the distributor's water-fill, every install (b). Flex: deleted (c) | 3 |
| Flex plumbing: `TWCMaster.allowed_flex` :42, `getAllowedFlex` :394, `setAllowedFlex` :1830; `Policy.py:59,82` (`"allowed_flex"` in the two Track Green defaults), `:286–287` (`setAllowedFlex`); `TWCSlave.useFlexAmpsToStartCharge` (:66, :99–101) | `test_twcmaster.py::test_set_allowed_flex`, `test_policy.py` (4 `setAllowedFlex = Mock()` setups), `test_twcslave.py::test_slave_use_flex_amps_to_start_charge` | Deleted (c) | 3 |
| `non_gen2` gate, `TWCMaster.distributeEVSEPower` 554–562 | `test_charging_points.py::test_pure_gen2_leaves_distributor_off`; `test_distributor_loop.py` (its "a non-Gen2 controller makes the distributor run" comment) | Deleted; the distributor runs whenever a Gen2 slave is known (the BASE `countSlaveTWC() > 0` gate moves into `controlPass`, F2) | 3 |
| `VehicleEndpoints` registration, `TWCManager.py:756–776` | none | `TWCMaster.__init__` registers it next to `Gen2TWCs` (it lists nothing without TeslaAPI, `VehicleEndpoints.py:105`); Task 6 replaces both with `vehicleEndpoints(master)` | 3, 6 |
| Distributor call on the serial loop, `TWCManager.py:923–930` (inside `if master.countSlaveTWC() > 0`) | — | `ControlTick` → `master.controlPass()`, which keeps the slave-count gate (F2) | 3 |
| `processIPC` (`TWCManager.py:983–985`), expiry queueing (`:1000–1004`) on the serial loop | — | `ControlTick.housekeeping()` | 3 |
| Token refresh on the serial loop, `TWCManager.py:1006–1017`; `TWCMaster.lastTeslaTokenRefreshCheck` (:57) | `test_limit_wiring.py:236–239` (indexes the loop source on that string) | Self-rescheduling background task `refreshTokens` (300 s) | 2 |
| `num_cars_charging_now` session side effects (`TWCMaster.py:1262–1346`); called from `getStatus` (HTTP thread, :734) and `getMaxAmpsForTargetGridUsage` (policy/background, :970) | `test_amps_reconciler.py:107`, `test_twcmaster_vin_confirmation.py:72,76` | Split: `observeChargingSessions()` (serial, from `receive_slave_heartbeat`) and a pure `num_cars_charging_now()` count | 3 |
| Min/probe, `chargeRateControl` branches, 5 s decrease hold (`TWCSlave.py:818–1112`); `set_last_amps_offered` (1180–1253) | `test_gen2_idle_minimum.py` (offers via heartbeats), `test_twcslave.py` attributes | `TWCSlave.offerFor(target, ctx, now) -> Offer`, run by the tick | 4 |
| Dampening and flip tracking (inside 818–1112: `dampenChanges`, `lastAmpsDesired`, `timeLastAmpsDesiredFlipped`; class attrs :65, :68) | `test_twcslave.py::test_slave_last_amps_desired` | Deleted (f) | 4 |
| 6 A spike: `TWCSlave.py` 966–1079, `TWCMaster.spikeAmpsToCancel6ALimit` :91, `getSpikeAmps` :819, `setSpikeAmps` :1954, linkready `setSpikeAmps` (`TWCManager.py:1232–1242`), HTTP checkboxes (`HTTPControl.py:2005–2012`), `debug.html.j2:113–116`, `docs/Debug.md` "Spike Amps" | `test_gen2_idle_minimum.py::offers(spike=)` (on by default at BASE) | Deleted (a). `test_twcmaster.py:600–670` (`test_returns_positive_when_charger_spiked` etc.) are `subtractChargerLoad` regressions, not spike tests: kept (F12) | 4 |
| Car amps in the heartbeat: `_anonCars`, `_setCarAmps`, `_clearCarAmps`, `_carRateConfirmed`, `_queueChargeRate`, `_requestVehicleRateRaise` (`TWCSlave.py:126–174`) and `_resetVehicleRateRaised` (:181–183); **not** `minAmpsToOffer` (:175–179, kept, F5); `_ampsKeys` (:86); `APIcontrol` (:94); `Gen2TWC.pointOwnsAmps` | `ChargingPoint.py:156–191`, `TWCMaster.py:1317`, `test_amps_reconciler.py` (:30, :68–89, :100, :102, :105, :107, :157–187, :198), `test_limit_wiring.py:308`, `test_twcslave.py::TestVehicleChargeRateDesired` | `ChargingPoint.setTargetPower` owns car amps for every point (`_carKeys()`); `anonymousCars(master, slave)` moves to `ChargingPoint.py`; a per-slave session counter keys the lift (`plugSessions`/`liftedSession`) | 4 |
| `Gen2TWC._evseTargetAmps`, `lastAmpsDesired` compat write (`Gen2TWC.py:40, 224–225`) | `test_amps_reconciler.py`, `test_gen2_idle_minimum.py`, `test_charging_points.py`, `test_gen2twc_provider.py:184`, parity :892/897/1082 | `pointAmps` (the raw target) and `offer` (what goes on the wire) | 4 |
| `cancelStopCarsCharging` on a positive offer, `TWCSlave.py:1114–1116` | — | `TWCMaster.controlPass`, from Task 4 (no gap, F4) | 4 |
| Start/stop gates, `send_master_heartbeat` 541–658 | `test_charging_reconciler.py` heartbeat rows (through `drive`) | `TWCSlave.chargeGate(now) -> Optional[str]`, applied by `TWCMaster.controlPass` | 5 |
| Off-thread RS-485 writes: `HTTPControl.py:941–943` (sendTWCMsg), `:950` (sendStartCommand), `:955` (sendStopCommand); background `checkVINEntitlement` stop (`TWCManager.py:344`), `getLifetimekWh` (:346–347), `getVehicleVIN` (:348–349); `WebIPCControl.py:258` (moves off the loop in Task 3); `Gen2TWCProvider` mode-3 `stopRequested` (`Gen2TWCProvider.py:114`, `TWCSlave.py:36–38, 434–437`, `Gen2TWC.py:42–44`) | `test_gen2twc_provider.py:176`, `test_charging_reconciler.py:55,56,107,126`, `test_provider_outcomes_local.py:49,51,98` (F11), `tests/integration/*` (HTTP API only, unchanged) | `master.sendRS485(msg)` (any thread) → `master.flushRS485()` (serial loop) | 1 |
| VIN check digit, `TWCManager.py:1491–1570` (weights and transliteration table, one entry per line) | none | `Registry/VIN.py: vinCheckDigitValid(vin) -> bool` | 1 |
| `EVSEInstance` ABC (147), `EVSEController` ABC (50), `Gen2TWCs` (44), `VehicleEndpoints` class and `_cache`; unused point aggregates | many tests (plumbing), including `test_distributor_loop.py`, `test_telemetry_registry.py`, `test_vehicle_endpoint.py`, `test_gen3twc_provider.py`, `test_provider_registration.py` | `EVSEInstance` becomes a 25-line mixin (the two converters and four defaults); budgets come from `TWCMaster._budgets()`; listing is `vehicleEndpoints(master)` | 6 |

**Other callers checked:**
- `Policy.py:286–287` (`setAllowedFlex`) and `:59,82` (`allowed_flex`): deleted with flex (Task 3).
- `HTTPControl.py:520–578, 634`: reads `lastAmpsOffered`, `lastChargingStart` and `historyAvgAmps`, all kept.
- `WebIPCControl.py:192`: kept.
- `showStatus.html.j2:89,110`, `Modern/main.html.j2:228`, `Modern/jsrefresh.html.j2:160`: `lastAmpsOffered`, kept.
- `docs/modules/Interface_RS485.md:38`: describes the distributor's idle rule. It is reworded in Task 4 (no rule changes).
- `docs/PolicyCustomization.md:135,213` (`allowed_flex`) and `docs/config_examples.md:18,26` (`greenEnergyFlexAmps`): reworded in Task 3 to say the key is ignored.
- `etc/twcmanager/config.json:107–111`, `demo.json:99–103`, `.testconfig.json:112–116` (`greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and their comments): removed from the shipped examples in Task 3 (old configs keep loading).
- `etc/twcmanager/config.json:78` (`startStopDelay`): kept (gates).

---

## File structure

- **Created:**
  - `lib/TWCManager/ControlTick.py` (T3): the thread, ≈ 45 lines.
  - `tests/unit/test_control_tick.py` (T3–T5).
  - `tests/unit/test_rs485_serial_only.py` (T1).
- **Modified:**
  - `TWCMaster.py` (T1, T3–T6);
  - `TWCSlave.py` (T1, T3–T5);
  - `EVSEInstance/Gen2TWC.py` (T1, T4, T6);
  - `EVSEInstance/ChargingPoint.py` (T4, T6);
  - `TWCManager.py` (T1–T4);
  - `Control/HTTPControl.py` (T1, T4);
  - `Control/WebIPCControl.py` (T1);
  - `Vehicle/Providers/Gen2TWCProvider.py` (T1, T4);
  - `Vehicle/TeslaTokenSlot.py` (T2);
  - `Vehicle/Registry/VIN.py` (T1);
  - `EVSEInstance/EVSEInstance.py`, `EVSEInstance/VehicleEndpoint.py`, `EVSEInstance/Gen3TWC.py`, `EVSEController/Gen3TWCs.py` (T6);
  - `Control/themes/Default/debug.html.j2` (T4);
  - `docs/Debug.md`, `docs/modules/Interface_RS485.md` (T4).
- **Deleted:** `EVSEController/EVSEController.py`, `EVSEController/Gen2TWCs.py`, `EVSEController/VehicleEndpoints.py` (T6).
- **Tests:** `tests/unit/gen2_helpers.py` (T3: `drive()` and `tickThenBeat()` call `controlPass`), plus the files named per task.

---

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

### Task 2: Token refresh off the serial loop; one refresh per slot at a time (#690) (expected lib Δ ≈ +22)

Today `TWCManager.py:1006–1017` refreshes tokens on the serial thread, which is a POST of up to 10 s. Nothing stops two threads spending one single-use refresh token, since the worker, HTTP, Storm Watch and the background thread all refresh.

**Single-flight:**
- The first caller claims `_refreshing` under `_cond` and POSTs **without** the lock.
- A concurrent caller waits on `_cond` (the wait releases it) up to `REFRESH_TIMEOUT + 5` s and returns the first caller's result.
- An answer arriving after the slot's tokens changed (`changes` moved: a paste, a sync, a clear) is discarded. The refresh then returns `"success"` when the slot holds a token, else `"rejected"`. A late answer never overwrites a pasted token.
- **The 401 path too** (ruling F10): BASE `refresh` calls `self.clear()` on a 401 (TeslaTokenSlot.py:236–241). That clear also runs only if `changes` is unchanged since the claim, so a 401 for the old refresh token never wipes a token pasted during the POST.
- `setTokens`, `clear` and `restore` (:279) take `_cond` (a leaf, no I/O) so a reader on another thread never sees a half-written slot (F10).

**Files:**
- Modify `lib/TWCManager/Vehicle/TeslaTokenSlot.py` (`__init__`, `setTokens` :77, `clear` :109, `refresh` :204).
- Modify `lib/TWCManager/TWCManager.py`:
  - delete :1006–1017;
  - add a background handler `refreshTokens`, which calls `carapi.refreshTokenIfNeeded()`, then `carapi.loadList()` if `carapi.listPending()`, and re-queues itself with `delay=300` in a `finally`, so a raising refresh never ends the schedule (F10);
  - queue it once at startup with `delay=300`, next to `checkCharge`.
- Delete the now-unused `TWCMaster.lastTeslaTokenRefreshCheck` (:57).
- Tests: `tests/unit/test_teslatokenslot.py`, `tests/unit/test_twcmanager.py` (static), `test_limit_wiring.py:236–239` (it indexes the loop source on `lastTeslaTokenRefreshCheck`; point it at the `refreshTokens` handler's text, asserting the same `listPending()` → `loadList()` order: PLUMBING-ONLY, F11).

**Interfaces:**
- Produces:
  - `TeslaTokenSlot._cond: threading.Condition` (leaf);
  - `TeslaTokenSlot._refreshing: bool`;
  - `TeslaTokenSlot._lastRefresh: Optional[str]`.
- `refresh(now=None) -> str` keeps its four results and its signature.

- [ ] **Step 1: Write the failing tests.**

```python
def test_concurrent_refreshes_spend_the_refresh_token_once(requests_mock):
    gate = threading.Event()
    def slow(request, context): gate.wait(2); return {"access_token": tok(), "refresh_token": "r2", "expires_in": 28800}
    hit = requests_mock.post(URL, json=slow)
    s = slot(refreshToken="r1")
    results = []
    ts = [threading.Thread(target=lambda: results.append(s.refresh())) for _ in range(3)]
    [t.start() for t in ts]; time.sleep(0.2); gate.set(); [t.join(5) for t in ts]
    assert hit.call_count == 1 and results == ["success"] * 3 and s.refreshToken == "r2"

def test_a_refresh_answer_after_a_paste_is_discarded(requests_mock):
    # the POST callback calls s.setTokens(pasted, "rp") before answering
    assert s.refresh() == "success" and s.accessToken == pasted and s.refreshToken == "rp"

def test_a_401_after_a_paste_does_not_clear_the_pasted_token(requests_mock):   # F10
    # the POST callback pastes, then answers 401: s.accessToken == pasted afterwards
def test_restore_takes_the_slot_lock():                                        # F10
def test_no_lock_is_held_during_the_post(requests_mock):
    # inside the POST callback: s._cond.acquire(blocking=False) is True (then released)

def test_refresh_tokens_task_requeues_itself():
    # run the handler once with queue_background_task spied: it re-queues {"cmd": "refreshTokens"} with delay=300,
    # also when refreshTokenIfNeeded raises (F10)
def test_the_serial_loop_never_refreshes_tokens():
    src = loopSource()   # TWCManager.py text from "while True:" (the outer loop) to the shutdown
    assert "refreshTokenIfNeeded" not in src and "lastTeslaTokenRefreshCheck" not in src
```

- [ ] **Step 2: Run** → FAIL: the first test makes 3 POSTs; the static test finds `:1013`.
- [ ] **Step 3: Implement** as above. Keep `refresh`'s body as `_refreshOnce(now)` (BASE lines 204–264 unchanged), wrapped by the single-flight. **Discard rule:** read `changes` at the claim; apply `setTokens` only if `changes` is unchanged, under `_cond`.
- [ ] **Step 4: Run** `test_teslatokenslot.py test_teslaapi_refresh.py test_teslaapi_token_slots.py test_teslaapi_token_migration.py test_teslamate_token_sync.py` → PASS, unchanged.
- [ ] **Step 5: Full suite** → PASS.
- [ ] **Step 6: Commit.** `git commit -m "Refresh Tesla tokens off the serial loop, one refresh per slot at a time (#690)"`

---

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

### Task 4: The heartbeat is protocol-only: offers are computed on the tick; charging points own car amps; the 6 A spike workaround and dampening are dropped (expected lib Δ ≈ −320)

After Task 3, `receive_slave_heartbeat` still turns the distributor's target into the wire offer: min/probe, `chargeRateControl` branches, the spike, the 5 s decrease hold, dampening, flip tracking and `set_last_amps_offered`'s caps. The spike and dampening (with its flip tracking) are deleted, not ported (a, f). It also writes car amps for a point with no car member.

All of that moves to the tick:
- `TWCSlave.offerFor` is the ported rule set, minus the spike.
- `ChargingPoint.setTargetPower` writes car amps for **every** point: car members' keys; else the TWC's named car; else the anonymous fan-out.

The heartbeat sends `self.offer`. Before the first tick it sends the idle `00` payload (Review Focus 1).

**Files:**
- Modify `lib/TWCManager/TWCSlave.py`:
  - delete 818–1121 (everything after the Task 3 cut, up to and including the `masterHeartbeatData =` line). The positive-offer `cancelStopCarsCharging` inside it (:1114–1116) moves to `controlPass` in this task (F4);
  - delete `set_last_amps_offered` (1180–1253);
  - delete the car-amps helpers 126–174 and 181–183, keeping `minAmpsToOffer` (:175–179, F5); `_ampsKeys` (:86); `APIcontrol` (:94); the imports that become unused (`AMPS`, `known`, `satisfied`, `isAnonKey`, :7–11; `broadcastVehicles`/`located` stay for `pluggedCars`, F22);
  - add `Offer`, `OfferContext`, `offerFor`, `heardFrom` (T3), `plugSessions`, `liftedSession`;
  - `send_master_heartbeat` builds `masterHeartbeatData` from `self.offer`, then the override (:538–539, unchanged), then sends;
  - move the `lastAmpsOffered < 0` init (BASE :721–722) into `offerFor`.
- Modify `lib/TWCManager/EVSEInstance/Gen2TWC.py`:
  - `setTargetPower` stores `self.pointAmps`;
  - delete `_evseTargetAmps`, `pointOwnsAmps` and the `lastAmpsDesired` compat write;
  - keep `minAmps`, `maxOfferAmps`, `layerFloorAmps` and `_rangeOverride`.
- Modify `lib/TWCManager/EVSEInstance/ChargingPoint.py`: add `anonymousCars(master, slave)` (moved from `TWCSlave._anonCars`) and `ChargingPoint._carKeys()`; `setTargetPower` handles a TWC-only point the way it handles a point with car members; add `confirmed()`.
- Modify `lib/TWCManager/TWCMaster.py`:
  - `controlPass` builds one `OfferContext` and sets `slave.offer = slave.offerFor(slave.pointAmps, ctx, now)` for every slave **with `heardFrom` True** (F9; an unheard slave keeps `offer is None`, so its heartbeat sends `00`). With `distribute=False` it uses `self.chargingPoints()` for `ctx.confirmed`;
  - then, for each such slave with a key and `offer.amps > 0`, `cancelStopCarsCharging(key)` (BASE :1114–1116, any protocol), **skipped during the chargeStopMode-2 silence** (`respondToSlaves == 0` and `respondToSlavesExpiry` in the future: BASE returned from `send_master_heartbeat` and got no replies, so neither ran, F7);
  - delete `spikeAmpsToCancel6ALimit`, `getSpikeAmps` and `setSpikeAmps`;
  - `observeChargingSessions`'s session end (:1317) bumps `slaveTWC.plugSessions`;
  - fix the stale spike comment in `getMaxAmpsForTargetGridUsage` (:951–955).
- Modify `lib/TWCManager/TWCManager.py:1232–1242`: drop `setSpikeAmps`.
- Modify `lib/TWCManager/Control/HTTPControl.py:2005–2012`: drop the spike checkboxes block.
- Modify `lib/TWCManager/Control/themes/Default/debug.html.j2:112–117`: drop the "Spike Amps" row.
- Modify `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py`: fix the `:84` comment naming `send_master_heartbeat`; `setAmps` is unchanged (it calls `setTargetPower`).
- Modify `docs/Debug.md` (delete "Spike Amps") and `docs/modules/Interface_RS485.md:38` (same rules, "the control tick" for "the heartbeat").
- Tests: `test_gen2_idle_minimum.py`, `test_amps_reconciler.py` (:30, :68–89, :100, :102, :105, :157–187, :198), `test_limit_wiring.py:308`, `test_charging_points.py`, `test_twcslave.py`, `test_gen2twc_provider.py:184`, `test_command_path_parity.py:892,897,1082` (plumbing), and `test_control_tick.py`. `test_twcmaster.py` is untouched (F12). `test_twcslave.py:176` `test_slave_heartbeat_data_default` keeps passing (class default).

**Interfaces:**
- Consumes: `controlPass`, `tickThenBeat` (Task 3).
- Produces:
  - `TWCSlave.Offer = NamedTuple("Offer", [("amps", float), ("desired", float)])`, immutable, written by the tick only. `TWCSlave.offer: Optional[Offer] = None`.
  - `TWCSlave.pointAmps: float = 0`: the distributor's raw target (watts → amps), written by `Gen2TWC.setTargetPower`. Named so that `test_no_legacy_command_paths.py:19`, which bans the string `targetAmps` in `lib`, stays meaningful (F3).
  - `OfferContext = NamedTuple(...)` with fields `budgetAmps: float` (`getMaxAmpsToDivideAmongSlaves()`), `carsCharging: int` (`num_cars_charging_now()`), `mode: int` (`chargeRateControl`), `totalAmpsInUse: float`, `confirmed: Dict[bytes, bool]` (TWCID → car rate confirmed, from `ChargingPoint.confirmed()`).
  - `TWCSlave.offerFor(target: float, ctx: OfferContext, now: float) -> Offer`. It updates `lastAmpsOffered`/`timeLastAmpsOfferedChanged` and publishes `amps_offered`/`amps_desired`.
  - `TWCSlave.plugSessions: int = 0` (serial; `observeChargingSessions` bumps it at each session end, replacing the `_resetVehicleRateRaised()` call at `TWCMaster.py:1317`) and `TWCSlave.liftedSession: Optional[int] = None` (tick). `TWCSlave.vehicleRateRaised` becomes a read-only property `liftedSession == plugSessions`. `ChargingPoint` sets `local.liftedSession = local.plugSessions` after a lift, and `None` where BASE called `_resetVehicleRateRaised()`: mode 3 below the floor (`ChargingPoint.py:191`) **and** every pass in which the car carries, i.e. mode 2 or mode 3 below 6 A, for every point type (BASE `TWCSlave.py:934`, F6). So a runtime switch from mode 2 to mode 1 mid-session lifts again, as at BASE. `test_amps_reconciler.py:105`, which assigns `s.vehicleRateRaised = True`, sets `s.liftedSession = s.plugSessions` instead (PLUMBING-ONLY).
  - `ChargingPoint._carKeys() -> List[str]`, `ChargingPoint.confirmed() -> bool`, and `anonymousCars(master, slave) -> List[Vehicle]`, with `_anonCars`'s semantics exactly.

**`offerFor`: the ported rules, in BASE order, spike and dampening removed.** It is written out here because the tests do not fix the order.

```python
def offerFor(self, target, ctx, now):
    if self.lastAmpsOffered < 0:
        self.lastAmpsOffered = self.reportedAmpsMax         # BASE receive :721
    minOffer, n = self.minAmpsToOffer(), ctx.carsCharging
    desired = target
    if desired < minOffer:
        # idle-TWC probe (not counted against the budget) or a stop
        desired = self.minAmpsTWCSupports if n and ctx.budgetAmps / n > minOffer else 0
    elif ctx.mode == 2 or (ctx.mode == 3 and desired < 6):
        self.liftedSession = None                             # BASE :934, every pass (F6)
        desired = self.wiringMaxAmps if ctx.confirmed.get(bytes(self.TWCID)) else int(desired)
    else:
        desired = int(desired)
        if desired < self.lastAmpsOffered and now - self.timeLastAmpsOfferedChanged < 5:
            desired = self.lastAmpsOffered                   # BASE :1080-1091, kept (not spike)
    amps = self._capped(desired, ctx.totalAmpsInUse)        # BASE set_last_amps_offered caps, every pass (e)
    if amps != self.lastAmpsOffered:
        self.lastAmpsOffered, self.timeLastAmpsOfferedChanged = amps, now
    self._publishStatus("amps_offered", "ampsOffered", amps, "A")
    self._publishStatus("amps_desired", "ampsDesired", desired, "A")
    return Offer(amps, desired)
```

`_capped(desired, total)` applies two caps, keeping BASE's messages and levels:
- If `total - reportedAmpsActual + desired > wiringMaxAmpsAllTWCs`, use `int(wiringMaxAmpsAllTWCs - (total - reportedAmpsActual))`, never below `minAmpsTWCSupports`, and log the BASE INFO "WARNING: Offering slave TWC …" line. Log it only when the capped value differs from the last one logged (`_cappedLogged`), so a sustained cap does not log every second.
- Then cap at `wiringMaxAmps`, with the BASE DEBUG line.

The `cancelStopCarsCharging` on `offer.amps > 0` (BASE :1114–1116) moves into `controlPass` in this task, so no task leaves it out (F4).

**`ChargingPoint.setTargetPower`, generalised.** BASE (`:153–198`) runs the layered branch only when the point has car members (`cars`). From now on the car side is `keys = self._carKeys()`:
- car members' `vehicleKey`s;
- else, when the local member is a Gen2 with a `vehicleKey`, `[that key]` for a VIN, or `[v.key for v in anonymousCars(master, local)]` for an anonymous key;
- else `[]`.

Rates keep BASE's labels (F13): a car member's rate goes through `VehicleEndpoint.setTargetPower` (`by="distributor"`), and a rate for a key with no `VehicleEndpoint` (the TWC's own VIN, or the anonymous fan-out) is written as `desired.set(k, AMPS, amps, "heartbeat")`, as BASE's heartbeat path wrote it. Lifts stay `desired.set(k, AMPS, wiringMaxAmps, "lift", lift=True)` once per session (`local.vehicleRateRaised`). A key that left the set since the last pass gets its rate cleared **only if `d.by == "heartbeat"`** (BASE `_clearCarAmps` :150–155), so a TWC point never clears a `VehicleEndpoint`'s rate for the same car. The point keeps `_lastKeys` on the local member, written only by the tick.

`confirmed()` is BASE `_carRateConfirmed` over `keys`.

The modes follow BASE `carriers()`:
- **mode 1 (TWC carries):** no car rate, plus the lift. The lift is unconditional for a TWC-only point (BASE heartbeat `TWCSlave.py:953–954`). For a point with car members it applies only when the member's request is below the offer (BASE `ChargingPoint.py:181–182`).
- **mode 2:** the car carries.
- **mode 3:** layered at `layerFloorAmps()`.

- [ ] **Step 1: Write the failing tests.**
  - Characterization (BASE+after, with `tickThenBeat`, spike settings 0 at BASE):
    - `test_idle_twc_nobody_charging_sends_zero`
    - `test_idle_twc_probe_when_budget_per_car_exceeds_min` / `..._zero_when_it_does_not`
    - `test_charging_twc_gets_whole_amps_of_its_share`
    - `test_a_decrease_within_5s_is_held_then_applied`
    - `test_all_twc_wiring_cap_uses_others_actual_draw_and_floors_at_twc_minimum`
    - `test_per_twc_wiring_cap`
    - `test_mode_2_offers_the_twc_max_once_the_car_rate_is_confirmed`
    - `test_mode_3_below_six_layers_the_car_and_holds_the_twc_floor`
    - `test_mode_1_lift_goes_once_per_session_for_a_twc_only_point` (BASE: heartbeat path; after: point path; same desired value, `lift=True`)
  - New behaviour:
    - `test_heartbeat_before_the_first_tick_sends_no_change` (Review Focus 1): a new slave, `offer is None`, so `send_master_heartbeat` sends bytes 6..14 == `bytes(9)`. Re-run Task 3's `test_restart_with_a_car_charging_never_offers_zero` against the `offer` path.
    - `test_the_lift_survives_a_session_end_racing_the_tick`: `liftedSession` set for session 3, the serial thread bumps `plugSessions` to 4, the next pass lifts again.
    - Characterization (BASE+after): `test_a_mode_2_to_1_switch_mid_session_lifts_again` (F6).
    - Characterization (BASE+after): `test_a_twc_point_never_clears_a_vehicle_endpoints_rate` (F13): an anonymous point whose fan-out (`vehicles[0]`) drops the car while its `VehicleEndpoint` holds a `"distributor"` rate leaves that rate in place.
    - `test_no_offer_or_cancel_for_an_unheard_slave` (F9) and `test_no_stop_cancel_during_the_mode_2_silence` (F7).
    - `test_wiring_cap_is_rechecked_when_others_draw_more` (e): the offer is unchanged at 20 while another TWC ramps from 20 to 40 on an 48 A circuit, so the next pass offers 8.
    - `test_green_policy_does_not_hold_a_car_below_the_minimum` (f): Track Green, share falls from 10 to 3 while drawing, so the next offer is the probe/stop rule's value at once, not a held `minAmpsTWCSupports`.
    - `test_spike_settings_are_ignored` (a): `spikeAmpsProactively=1` with a car at 6 A offered 12 A sends 12, never 16/21.
    - `test_no_car_amps_code_left_in_the_slave`: `TWCSlave` has none of `_setCarAmps`, `_clearCarAmps`, `_carRateConfirmed`, `_queueChargeRate`, `_requestVehicleRateRaise`, `_anonCars` or `APIcontrol`.
    - `test_receive_writes_no_offer` (static): `receive_slave_heartbeat` source has no `offer`, `lastAmpsOffered =` or `desired.`.
- [ ] **Step 2: Run** them at BASE (scratch checkout of 1029809b; the characterization set must PASS) and on the branch (the new-behaviour set must FAIL). Record both.
- [ ] **Step 3: Implement** as above.
  - `controlPass` uses the points `distributeEVSEPower` returned for `ctx.confirmed`.
  - `test_amps_reconciler.py` rows that call `s._queueChargeRate(x)` or the other removed helpers (:30, :100, :102, :157–187, :198) become `pt.setTargetPower(convertAmpsToWatts(x))` on the slave's point followed by `offersThenBeat`, or `tickThenBeat`. That is PLUMBING-ONLY when the desired value is unchanged. Rows asserting `d.by == "heartbeat"` keep that assertion: the label is unchanged (F13).
  - `test_twc_only_point_keeps_the_heartbeat_path_under_mode_2` and `test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member` are replaced by `test_a_twc_only_point_writes_the_cars_amps_under_mode_2` (same desired values).
  - `test_gen2_idle_minimum.py::offers(spike=...)`: drop the parameter. Rows asserting the same values with spike on and off keep the spike-off assertion (PLUMBING-ONLY). Any row asserting a spike value is INTENTIONALLY CHANGED (a).
  - `test_twcmaster.py:600–670` (`subtractChargerLoad` regressions with "spike" in their names) are kept unchanged; only a stale comment, if any, is reworded (F12).
  - `test_twcslave.py`: `test_slave_api_control_default` is deleted (no replacement: the attribute is gone); `test_slave_last_amps_desired` is deleted, INTENTIONALLY CHANGED (f); `TestVehicleChargeRateDesired` maps to the point-path tests above; `test_heartbeat_code_never_calls_set_charge_rate_inline` is kept (still true).
- [ ] **Step 4: Run** the characterization and new tests, `test_command_path_parity.py`, `test_amps_reconciler.py`, `test_charging_points.py` and `test_gen2_idle_minimum.py` → PASS. Parity counts are untouched.
- [ ] **Step 5: Full suite** → PASS. Grep (Global scope, tests/unit included) for `spikeAmps|getSpikeAmps|setSpikeAmps|_evseTargetAmps|pointOwnsAmps|_setCarAmps|_clearCarAmps|_carRateConfirmed|_queueChargeRate|_requestVehicleRateRaise|_resetVehicleRateRaised|_anonCars|APIcontrol|set_last_amps_offered`. Expect no hits apart from `test_twcmaster.py`'s kept `*_spiked` test names; `docs/Debug.md` is gone from the hits too. `test_no_legacy_command_paths.py` still passes (no `targetAmps` in lib).
- [ ] **Step 6: Commit.** `git commit -m "Compute TWC offers on the control tick; charging points own car amps; drop the 6 A spike workaround"`. The body names (a) for the PR.

---

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

### Task 6: Collapse the EVSE scaffolding; sweep, guard, line check, live check (expected lib Δ ≈ −310)

With one distributor, nothing switches on controller type, so:
- the `EVSEController` ABC, the `Gen2TWCs` controller and the `VehicleEndpoints` controller class go;
- the `EVSEInstance` ABC shrinks to the mixin its four users need: `convertAmpsToWatts`, `convertWattsToAmps` and the defaults `currentVIN ""`, `controllers []`, `vehicleKey None` and `occupied None`.

Budgets come from one method. Car endpoints come from one function without the cache: `VehicleEndpoint` holds no state of its own, since a rate lives in `DesiredStore`.

`ChargingPoint` loses the aggregates no caller reads. Expected, but confirm by grep at the task's BASE: `isCharging`, `occupied`, `currentPower`, `currentVIN`, `currentAmps` (:82–87) and `isLocal` (:55–57; callers use the members' `e.isLocal`) (F22). Gen2/Gen3/Vehicle endpoints lose `currentPower`. `getAllEVSEs` and `chargingPoints` (one caller each) are inlined into `distributeEVSEPower` (F22). The stale docstring at `VehicleEndpoint.py:4–5` ("the distributor runs on the serial thread") is corrected.

`TWCMaster`'s class-level `settings` dict (:69–84) **stays**: `test_charging_points.py` and `test_distributor_loop.py` build masters with `TWCMaster.__new__`, which reads it (a class-level reader, F21).

**Files:**
- Delete `lib/TWCManager/EVSEController/EVSEController.py`, `EVSEController/Gen2TWCs.py` and `EVSEController/VehicleEndpoints.py`. Move `_blindTWCs`, `_telemetryPluggedIn` and the listing rule unchanged into `EVSEInstance/VehicleEndpoint.py` as `vehicleEndpoints(master) -> List[VehicleEndpoint]`.
- Modify `EVSEInstance/EVSEInstance.py` (≈ 25 lines), `ChargingPoint.py`, `Gen2TWC.py` (docstring, `controllers`), `Gen3TWC.py` and `VehicleEndpoint.py` (drop `currentPower`), and `EVSEController/Gen3TWCs.py` (plain class; `name`, `maxPower` and `stop` stay; still registered as module type `"EVSEController"` under the name `"Gen3TWCs"`, which `getModuleByName("Gen3TWCs")` callers use).
- Modify `TWCMaster.py`: delete the `Gen2TWCs`/`VehicleEndpoints` registration; the endpoints are `[s for s in getSlaveTWCs() if s.heardFrom] + vehicleEndpoints(self) + (gen3.allEVSEs if gen3 else [])` (the `heardFrom` filter carried over from `Gen2TWCs.allEVSEs`, F19), built inside `distributeEVSEPower`; add `_budgets()`; `distributeEVSEPower` uses it.
- Tests (plumbing): `test_charging_points.py`, `test_distributor_loop.py`, `test_vehicle_endpoint.py`, `test_gen2_idle_minimum.py:10,45`, `test_telemetry_registry.py`, `test_gen3twc_provider.py`, `test_provider_registration.py`, `test_provider_tables.py`, `test_held_limits.py`, `test_reconciler_queues.py` and the others from the Global grep (tests/unit included). Plus the guard and the line check.

**Interfaces:**
- Produces:
  - `TWCMaster._budgets() -> Dict[str, float]`: `{"Gen2TWCs": cfg.get("wiringMaxAmpsAllTWCs", 6) × cfg.get("defaultVoltage", 240) × cfg.get("numberOfPhases", 1), "VehicleEndpoints": inf, "Gen3TWCs": gen3.maxPower}` (the last only when registered). The values and `.get` defaults are BASE `Gen2TWCs.maxPower`'s (`Gen2TWCs.py:38–44`), so `test_distributor_loop.py`'s `__new__` master, which has no `wiringMaxAmpsAllTWCs`, keeps working.
  - `vehicleEndpoints(master) -> List[VehicleEndpoint]`.
  - The `controllers` names on endpoints are unchanged.

- [ ] **Step 1: Guard test.** Add `test_retired_settings_keys_load_and_are_ignored` (a master loading a config with `greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and settings with `spikeAmpsProactively`/`spikeAmpsReactively` starts and runs `controlPass` with offers equal to a master without them). Extend `test_no_legacy_command_paths.py` with:
  - `test_no_retired_allocator_names_remain`: `git grep -nE "Gen2TWCs\(|VehicleEndpoints\(|\(EVSEController\)" -- lib/TWCManager` is empty (no `-w`: a word match never sees `Gen2TWCs(self)`, F18), and `git grep -nwE "_evseTargetAmps|pointOwnsAmps|spikeAmpsProactively|spikeAmpsReactively|getSpikeAmps|setSpikeAmps|spikeAmpsToCancel6ALimit|set_last_amps_offered|stopRequested|_queueChargeRate|_setCarAmps|APIcontrol" -- lib/TWCManager html tests/integration tests/API docs` is empty;
  - `test_no_flex_or_dampening_code_remains`: `git grep -nwE "allowed_flex|getAllowedFlex|setAllowedFlex|useFlexAmpsToStartCharge|lastAmpsDesired|timeLastAmpsDesiredFlipped|dampenChanges" -- lib/TWCManager` is empty (lib only: the docs keep an "ignored" note, and `tests/API/test_getConfig.py:22` is a commented config dump);
  - `test_one_distributor_entry`: `distributeEVSEPower` is called only from `TWCMaster.controlPass`.

  Run it → FAIL (the scaffolding names).
- [ ] **Step 2: Collapse** as above. Every touched test is PLUMBING-ONLY (construction or import); record each.
- [ ] **Step 3: Orphan sweep.** For every `def` in the files Tasks 1–6 touched, run `git grep -nw <name> -- lib html`. Delete any with no caller, unless policy reach applies (a property or data attribute on a module object). Report each with evidence.
- [ ] **Step 4: Full suite** → PASS. `black --check` on the touched files.
- [ ] **Step 5: Line check** (report; the target is a target, not something to fit):

```bash
git ls-files lib | grep '\.py$' | xargs cat | wc -l                      # BASE 27,425; projected ≈ 26,615
git diff --shortstat 1029809b -- lib; git diff --shortstat origin/main -- lib
git diff --numstat 1029809b -- lib | awk '{a+=$1; d+=$2} END {print "added", a, "removed", d; exit !(d > a)}'
```
  Expected: the awk exits 0 and the total is < 27,425. Record each task's actual vs expected delta in the ledger. Do not pad deletions.
- [ ] **Step 6: PR notes** in the ledger, for the Phase 4 PR body:
  - A short **"Not ported into the rearchitecture"** section. Each item can return as a feature if there's demand:
    - **6 A spike workaround (a).** It briefly offered 16 or 21 A to get past a car-side 6 A limit that a 2017 car firmware imposed after an offer increase. It is known only from code comments and is likely long fixed. `spikeAmpsProactively`/`spikeAmpsReactively` are now ignored and the Debug page row is gone.
    - **Flex (c).** `greenEnergyFlexAmps` / a policy's `allowed_flex` let a car start or keep charging when its share was up to that many amps short of the minimum (`useFlexAmpsToStartCharge` for starting). Main's default path (TeslaAPI enabled) already ignored it since #483; only TeslaAPI-disabled installs lose it.
    - **Track Green dampening (f).** It held a drawing car at the TWC minimum for `startStopDelay` after its share crossed the minimum, to avoid start/stop churn. On main's default path a compatibility write had mostly disabled it since #483. The 60 s start/stop gates still protect the TWC relay.
  - (b), (d) and (e).
  - #690 closed.
  - The RS-485 outbox.
- [ ] **Step 7: Commit.** `git commit -m "Collapse the EVSE scaffolding the second allocator needed; guard the retired names"`
- [ ] **Step 8: Live check on `twcmanager`.** Deploys and restarts are pre-approved. The implementer does not run it; the user schedules it.
  - **Box:** Gen2 protocol 2, mode 1, `commandPolicy: ble_only`, a BLE-paired Model 3, TeslaMate→Owner (read-only), a Fleet slot.
  1. **Prepare.**
     - Record the box HEAD and back up `settings.json`.
     - Set `logLevel` so INFO8 and DEBUG for `Slave`/`Master` reach the journal.
     - Pause the watchdog cron.
  2. **Deploy** (bundle `<box HEAD>..vehicle-model/phase4`) and restart. Expect:
     - `ControlTick` started;
     - no `Main loop stalled` after boot;
     - the first SHB lines show `M: 00 …` until the first tick, then `09 …`.
  3. **Restart with the car charging at 32 A.** The wire offer goes straight from "no change" to 32. It never shows `0000` (Review Focus 1).
  4. **Track Green flicker** (or set Charge Now 10 A, then 4 A, then 16 A):
     - offers follow within ~1 s;
     - a decrease holds 5 s;
     - below the minimum, the BLE stop goes once after 60 s;
     - back above it, a start.
     - Zero `Car API … command/` lines (ble_only).
  5. **Debug page:** "Send TWC message" (`fbeb…`) still gets a reply in "Last TWC response"; the Spike Amps row is gone.
  6. **Tokens:** after 5 min, `Attempting token refresh` (if due) comes from the background thread (`BackgroundTask` in the log context), never during a stall.
  7. **Paid-call count** for the window: `journalctl … | grep "Car API" | grep -oE "wake_up|vehicle_data|command/[a-z_]+" | sort | uniq -c`. Expect 0.
  8. **Roll back** unless kept.

---

## Line budget (lib/ `.py` only, `git ls-files lib | grep '\.py$' | xargs cat | wc -l`)

Fixed points: origin/main 23,180; BASE 1029809b **27,425**.

| Task | Out | In | Expected Δ (range) | Running total |
|---|---|---|---|---|
| 1 outbox; VIN check digit | `stopRequested` 10, check-digit table 80 | outbox 12, `vinCheckDigitValid` 18, flushes 4 | **≈ −50** (−35..−65) | ≈ 27,375 |
| 2 token single-flight; refresh off the loop | loop block 12, `lastTeslaTokenRefreshCheck` 1 | single-flight 20, discard and 401 guard 6, `restore` lock 2, handler with `finally` 9 | **≈ +22** (+15..+30) | ≈ 27,397 |
| 3 tick; one distributor; flex deleted; session split | fair-share branch 50, `non_gen2` gate + docstring 25, registration 21, loop calls 12, flex plumbing (TWCMaster 7, Policy 3, TWCSlave 5) 15 | `ControlTick.py` 47, `controlPass` 5, pure count 5, register 3, `heardFrom` 4 | **≈ −58** (−40..−80) | ≈ 27,339 |
| 4 offers on the tick; points own car amps; spike and dampening gone | 818–1121 ≈ 300, `set_last_amps_offered` 74, car helpers 53 (`minAmpsToOffer` kept), spike plumbing (TWCMaster 7, linkready 11, HTTP 8), Gen2TWC shims 8, attrs (incl. flip tracking) 8, unused imports 4 | `offerFor` + `_capped` 48, `Offer`/`OfferContext` 11, heartbeat send 8, `_carKeys`/`confirmed`/`anonymousCars` + key-only rates with own-label clear 60, lift counter 6, `controlPass` (offers, cancel, silence check) 14 | **≈ −320** (−300..−340, pre-flight F22) | ≈ 27,019 |
| 5 gates on the tick | 541–658 ≈ 117 | `chargeGate` 16, `controlPass` mapping 13 | **≈ −88** (−75..−100) | ≈ 26,931 |
| 6 EVSE scaffolding; sweep | `EVSEInstance` ABC 122, `EVSEController` 50, `Gen2TWCs` 44, `VehicleEndpoints` class/cache/`_get_carapi` 35, point aggregates incl. `currentAmps`/`isLocal` ≈ 48, `currentPower` ×3 9, `getAllEVSEs`/`chargingPoints` inlined 8, sweep ≈ 10 (class-level `settings` kept) | `_budgets` 8, endpoint list 3 | **≈ −315** (−260..−370) | **≈ 26,616** |

- **Projected end: ≈ 26,615** (range ≈ 26,500–26,720), after the pre-flight rulings. That is ≈ −810 from BASE and ≈ 3,435 above main.
- **Size (user, 2026-10-17):** proceed; the parity goal is softened. The ≈ −2,000 stretch is not reachable in Phase 4's scope without further feature cuts; ≈ 3,435 lines separate the projection from main.

## Decisions made in this plan

1. **The tick is its own thread, not the reconciler's.** The reconciler's 1 s `TICK` already exists, but it wakes on every desired-state change (`Desired.changed`), so a distributor pass there would run many times a second under load. A separate 45-line thread keeps the spec's table literal: the tick publishes; the reconciler compares and dispatches. Both are daemon threads, and the tick stops first at shutdown.
2. **Fair share stays the distributor's water-fill (b)** (ruled by the user, 2026-10-17). Every install with TeslaAPI enabled (the default: `TeslaAPI.py:198`, `TWCManager.py:759`) already runs it at BASE. The legacy "share by cars charging" fair share runs only with `vehicle.TeslaAPI.enabled: false`.
   - The one place the default path still divides by cars charging is the idle-TWC probe (`budget / carsCharging > minOffer`). That is ported exactly into `offerFor`.
   - The alternative, porting the legacy formula `min(B/N, B − others' draw)` as the distributor rule, would change allocation on nearly every install, including mixed Gen2+Fleet+Gen3 ones.
3. **Flex is deleted, not ported (c)** (user, 2026-10-17). It was dead on the default path since #483; porting would have re-enabled it for nearly every install. It is listed in the PR's "Not ported" section.
4. **Token single-flight waits without a lock and shares the result.** No lock is held across the POST, and the waiter's own refresh token is never spent. A late answer never overwrites a paste. Rejected: skipping for the second caller (changes `_request`'s 401 retry path), and a lock held across the POST (violates "no I/O under locks").
5. **The wiring cap is re-checked on every offer (e).** BASE capped only when the desired offer changed (`set_last_amps_offered`, `TWCSlave.py:1191`), so another TWC ramping up left this one's offer uncapped: the sustained overshoot the derating rule calls a bug. The cap's floor (`minAmpsTWCSupports`) and log line are BASE's; the log is de-duplicated.
6. **The 5 s decrease hold is kept.** It sits in the spike `if/elif` chain but limits any decrease, spike or not (`TWCSlave.py:1080–1091`).
7. **The outbox is FIFO and unbounded.** Every producer is rate-limited at BASE: the 60 s kWh poll, VIN queries (≤ 6 per session), user actions and the per-heartbeat stop.
8. **The VIN and kWh background tasks stay.** They carry dedupe (`_taskKey`) and the 5 s VIN-confirmation delay. Only their send moved.

9. **Track Green dampening is deleted, not ported (f)** (user, 2026-10-17). A compatibility write had mostly disabled it on the default path since #483; the 60 s start/stop gates (Task 5) remain the relay protection. It is listed in the PR's "Not ported" section.
10. **Token refresh reschedules itself on the background queue (Task 2).** `queue_background_task(delay>0)` inserts into the delayed list without the per-cmd dedupe (`TWCMaster.py:1349–1361`), and the earlier run's key is long cleared when the next one is promoted 300 s later, so the re-queue is never coalesced away (unlike `bleScan`'s immediate requeue). Task 2's `test_refresh_tokens_task_requeues_itself` pins it.

## Considered and rejected (the coordinator's "biggest candidates")

| Candidate (lines at BASE) | Why not in Phase 4 |
|---|---|
| `TWCManager.py` RX parser (≈ 900) with the duplicate `Protocol/TWCProtocol.parseMessage` (≈ 130) | RS-485 protocol handling: a spec non-goal, and the highest-risk code on a live charger. A parser unification is its own design, with a hardware test matrix. |
| Fake-slave mode (`fakeMaster` 0/2): `TWCManager.py` slave branch ≈ 360 + `TWCSlave.send_slave_heartbeat` ≈ 145 | A feature (#482), and protocol handling. |
| `WebIPCControl` (410) + `html/index.php` | A live legacy web UI (it reads `lastAmpsOffered` and sends TWC messages): a feature cut. |
| `Interface/Dummy` (405) + `TWCProtocol.createMessage` | The test and debug surface (`/api/sendTWCMsg` uses `createMessage`). |
| `Vehicle/Reconcile/*` (≈ 1,900) and `VehicleCommandQueue` (250) | They are Phase 3's design (lanes, attempt records), not duplicated by anything Phase 4 builds. Shrinking them is a Phase 3 follow-up with its own behaviour pins (paid-call oracle). |
| `Targets.py` presence (146) and `_blindTWCs`/`_telemetryPluggedIn` (≈ 60) | Presence: Phase 5. They move files in Task 6 unchanged. |
| Gen3 solver, `WallConnectorVins`, `_correlate` (≈ 940) | Gen3 is the majority of deployed WCs (memory); no feature may go. |
| Folding `TWCSlave` and `Gen2TWC` into one class (≈ −40 more) | Touches ≈ 20 test files for ≈ 40 lines. Task 6 removes the shims only. |
| The protocol comment blocks in `send_master_heartbeat` (≈ 90) and `_amps_heartbeat` (≈ 30) | They are the only documentation of Gen2 heartbeat bytes. |
| Moving the Policy thread onto the tick (≈ −40) | The spec keeps Policy as its own tier with its own interval. |

**Pre-existing, not changed:** the distributor's `0 < offer < point.minPower → 0` rule uses the point's minimum, which for a TWC point is the TWC's own minimum. So mode-3 layering below the TWC floor is never reached through the distributor in production; `test_amps_reconciler.py::test_mode_3_layers_below_the_floor_and_holds_the_twc_at_its_floor` reaches it by calling `setTargetPower` directly. Phase 4 keeps this as it is; two-pass admission (#709) is where point minima are revisited.

## Self-review (against 1029809b)

- **Every symbol planned for deletion exists** (line numbers checked at 1029809b):
  - TWCSlave: `stopRequested` :38/:434; `_anonCars` :126; `_setCarAmps` :136; `_clearCarAmps` :150; `_carRateConfirmed` :157; `_queueChargeRate` :167; `_requestVehicleRateRaise` :170; `_resetVehicleRateRaised` :181; `_ampsKeys` :87; `APIcontrol` :95; `set_last_amps_offered` :1180; the gate block :541–658; the allocation :767–1121.
  - TWCMaster: `spikeAmpsToCancel6ALimit` :91; `getSpikeAmps` :819; `setSpikeAmps` :1954; `lastTeslaTokenRefreshCheck` :55; the `non_gen2` gate :561; `Gen2TWCs` registration :168–172; `num_cars_charging_now` :1262.
  - Gen2TWC: `pointOwnsAmps` :28; `_evseTargetAmps` :40; `stopRequested` :44; the compat write :225.
  - EVSEController.py, Gen2TWCs.py, VehicleEndpoints.py and EVSEInstance.py as files.
  - TWCManager.py: spike :1232–1242; registration :756–776; distribute :925–930; IPC :983–985; expiry :1000–1004; token :1006–1017; check digit :1491–1570.
  - HTTPControl :941–955 and :2005–2012; WebIPCControl :258; `debug.html.j2:113–116`; `docs/Debug.md` "Spike Amps".
- **Every caller is listed** in the table and "Other callers checked":
  - templates: debug, showStatus, Modern main and jsrefresh;
  - `html/index.php` (via WebIPC, unchanged);
  - `tests/integration` (HTTP `sendStartCommand`/`sendStopCommand` only: the status code and body are unchanged, the send is deferred);
  - docs: Debug, Interface_RS485, PolicyCustomization, Gen3 docs (wording "EVSEController" kept, still true of Gen3TWCs' module type).
- **Green after every task.**
  - Task 3 keeps `_evseTargetAmps` until Task 4.
  - Task 4 keeps `Gen2TWCs`/`VehicleEndpoints` until Task 6.
  - `drive()` changes once (Task 3), and every later task reuses it.
- **Spec coverage:**
  - "Threading" rows: RS-485 protocol-only (T1, T3, T4, T5); tick (T3–T5); token off the loop and per-slot (T2).
  - "Everyone moves" (T3, T4, T5).
  - Idle minimum (T4 `offerFor` + characterization).
  - Layered actuators (T4 `ChargingPoint`).
  - 6 A dropped and called out (T4, T6).
  - `settings` lock: already in place since Phase 1; `settingsLock` is unchanged.

## Rulings (user, 2026-10-17)

Pre-flight (`.superpowers/sdd/2026-10-17-vehicle-model-phase4-control-tick/preflight.md`, GO-WITH-FIXES) rulings F1–F22 are applied in the task text:
- F1, F8: `tickThenBeat` and `offersThenBeat`; the `amps_max` plumbing rows; parity counts never move.
- F2: the `countSlaveTWC() > 0` gate stays.
- F3: `pointAmps`.
- F4: the stop cancel moves in Task 4.
- F5: `minAmpsToOffer` kept.
- F6: the mode-2 lift reset.
- F7: the silence skip.
- F9, F19: `heardFrom` in `Gen2TWCs.allEVSEs`, and then in `distributeEVSEPower`.
- F10: Task 2's 401 guard, `restore` lock and `finally`.
- F11, F12, F21: mapping and line references.
- F13: own-label clear.
- F14: ownership note.
- F15: IPC copy and rate.
- F16: shutdown flush and join.
- F17: restart test.
- F18: guard regex.
- F20: VIN case and the len-0 branch.
- F22: the extra deletions.

1. **Size:** proceed with the honest projection (≈ 26,615, after the pre-flight rulings); the parity goal is softened.
2. **Fair share:** the distributor's water-fill stays (Decision 2).
3. **Flex and dampening:** not ported; deleted like the spike workaround, settings keys ignored, all three listed in the PR body's "Not ported into the rearchitecture" section (Decisions 3 and 9).
