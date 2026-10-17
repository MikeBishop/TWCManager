# Pre-flight 2 — revised Phase 3 plan

Plan (revised in place, 1303 lines): `.superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md`. The spec, the user rulings and base 6a6c14e are unchanged from pre-flight 1.

## What was checked, and how

- **Every one of the 50 findings in `preflight.md`** was re-read against the revised text.
- **The whole revised plan was re-scanned** with the same checks as before: pairs, per-task consistency, references at base, forward dependencies, cost and wiring, threading (no RS-485 off the serial thread; one clock domain).
- **Ran against the base copy** in `scratchpad/preflight3/base`:
  - `make()` from `test_gen2twc_provider` followed by `s.send_master_heartbeat()` raises `IndexError` at TWCSlave.py:598, because no Interface module is registered. It raises with or without a Mock Policy (N5).
  - `tests/unit/test_gen2_idle_minimum.py` has no `drive` helper. Its helpers are `real`, `heartbeat(s, state, maxA, actA)`, `wireAmps`, `offers`, `idleSlave`, `point` and `chargingSlave` (N5).
  - Every test the plan now names was found at base, e.g. `test_commands_call_the_module_by_vin`, `test_provider_commands_go_to_the_unit`, `test_fleet_commands_resolve_the_car_by_vin`, plus `test_registry_fields.py` and `test_telemetry_registry.py`.
- **Grepped `lib/` at base for registry observations.** Only `Gen3TWC.py:232` observes `actualCurrent`; Gen2 (TWCSlave, Gen2TWC, TWCMaster) writes no `actualCurrent` and no `chargingState` (N1).
- **Read `CarApiVehicle.is_awake`** (TeslaAPI.py:2372). It caches the state for 120 s on `time.time()` (`lastVehicleAwakeTime`) and returns nothing new inside that window (N7, F38).
- **Read `getMaxAmpsToDivideAmongSlaves` and `setMaxAmpsToDivideAmongSlaves`.** The value is already clamped to `wiringMaxAmpsAllTWCs` (F37).
- **Walked each new or changed test by hand** at the clock values it sets.

## 1. Status of pre-flight 1 findings

| # | Status | Evidence in the revised plan / remaining gap |
|---|---|---|
| F1 | RESOLVED | `dispatch` stays until Task 10. Task 4 has it read outcomes by `kind in SETTLED`. `test_vehicle_priority.py` is in the Task 3 and Task 4 runs. |
| F2 | RESOLVED | Step 3 adopts only when `latest.at > max(write.at, d.at)` and the read disagrees with **the write**. New tests: `test_a_confirming_read_is_not_adopted…` and the restore case. (For CHARGING, see N2.) |
| F3 | PARTIAL, **acceptable** | A failing free provider is retried at `RETRY` cadence, up to `attempts()`, then backs off; the paid pick takes the slot once paid is eligible. With no paid candidate, the free retry is the ping, so a probe would add nothing, and nothing paid is at stake. The user's ruling is honoured where money is involved. Remaining gap: N12. |
| F4 | RESOLVED (charge limit) | Step 4b clears at plan time; `beforeWrite` clears a settled restore and adopts a settled apply. `test_a_rules_settled_restore…` runs on the real clock. The same loop class still exists for CHARGING (N1); the adopt-on-apply choice has its own issue (N8). |
| F5 | RESOLVED | `time.time` everywhere; monotonic only inside the lane's rate-limit window. `test_default_clocks_share_one_domain`. |
| F6 | RESOLVED | `wakeOutcome` checks the free online state first; `allowWake` is never true for a restore; Global Constraint and Decision 13. |
| F7 | RESOLVED | New field `chargeCurrentRequest` wired through Fields, Sources, TeslaAPI, BLE and Fleet Telemetry. `test_amps_use_the_cars_request_not_the_pilot`. |
| F8 | RESOLVED | `pointOwnsAmps` gives each car one AMPS writer per cycle; a TWC-only point keeps the Phase 2 path. Two new tests (one has a fixture problem, N5). |
| F9 | RESOLVED | `policy and policy.clearOverride()`; `overrideLimit` guarded the same way. |
| F10 | RESOLVED | The heartbeat passes `vehicleKey`; `targetsFor` resolves `anon:` keys. Test via a real heartbeat (fixture problem, N5). |
| F11 | PARTIAL | A disruptive stop is no longer stamped, and adoption after our own disruptive stop is skipped. But the re-assert relies on TWC-sourced `actualCurrent` observations that Gen2 never writes, and an unstamped DONE re-plans at once: see N1. |
| F12 | RESOLVED | Every entry reports once; `cancel(key)` removes stops only. Tests cover cancel, drop and replace. The report handling still has a gap (N4). |
| F13 | RESOLVED | `stopRequested` is published and the heartbeat sends it. The Task 4 test fixture cannot run (N5). |
| F14 | RESOLVED | `lastStopProvider` gates the Gen2 start. `test_mode_2_start_after_a_ble_stop_goes_through_ble`. |
| F15 | RESOLVED | DEBUG for zero-candidate rounds; candidate filter on present lists. The filter contradicts a Task 7 test (N9). |
| F16 | RESOLVED | `ScriptedProvider.ready = bool(vehicle.vin)` plus `readyFor`; the Task 7 test overrides `ready`. |
| F17 | RESOLVED | `del m.reconciler`, plus an `isinstance` check in `runAttempt`. |
| F18 | RESOLVED | `drain` works on an unstarted lane; the test no longer calls `start()`. |
| F19 | RESOLVED | Module-less providers skipped; `since` set. The other debug tests still break (N6). |
| F20 | RESOLVED | Step 4b. |
| F21 | RESOLVED | `>=`. |
| F22 | RESOLVED | Rules ported verbatim with the mapping; the test table is unchanged. |
| F23 | RESOLVED | `believed(exclude=)` and `latestFrom` (a minor identity gap: N10). |
| F24 | RESOLVED | `report` checks probes first. |
| F25 | RESOLVED | `adopt` classifies through `satisfied`; `userStopped` added. Side effects: N2, N3. |
| F26 | PARTIAL | A `cmds()` filter was added, but `test_a_free_success_puts_ble_first_again` still asserts `len(f.calls) == 1`, and the Fleet start's lane wake makes it 2. |
| F27 | RESOLVED | `refusedPurposes`; the test also checks that reads still work and a new token clears the refusal. |
| F28 | RESOLVED | The test now advances `LIMIT_THEN_START_GAP + 1`. |
| F29 | RESOLVED | `_post_service -> Outcome`; `_call_service` wraps it; the body log is removed. |
| F30 | RESOLVED | `monkeypatch`. |
| F31 | RESOLVED | `commandOutcome` never touches claims; probe uses `noteProof=False`; tests cover the pairing window and the unproven status. |
| F32 | RESOLVED | `id:<n>` entries are persisted; the wrappers resolve IDs (N11: `holding()` scope). |
| F33 | RESOLVED | Constraint reworded to `attempts()` per round plus backoff. |
| F34 | RESOLVED | AMPS `maxAge=None`. |
| F35 | RESOLVED | `read(force=True)` and `Attempt.force`; test with a live feed. |
| F36 | RESOLVED | Session end on a vehicle-sourced `pluggedIn` False, or on the endpoint's own session end. |
| F37 | PARTIAL | `forced` exists, but `_stopIsForced()` tests `getMaxAmpsToDivideAmongSlaves() / max(1, numCarsCharging) >= minAmpsToOffer()`. That budget is already clamped to `wiringMaxAmpsAllTWCs`, so the shared-wiring case F37 described (say 16 A for 3 cars: 5.3 < 6) still reads as "not forced", and a user-started car's wiring stop is still ignored. Ruling: test the *unclamped* policy budget (`maxAmpsToDivideAmongSlaves` before the `limitAmpsToDivideAmongSlaves`/wiring clamp) against the minimum; forced when the clamp, not the policy, is binding. |
| F38 | PARTIAL | `wakeOutcome(now=)` and `FleetAPIProvider.clock` were added, but `is_awake` caches state for 120 s on real `time.time()`. In the row-4 sample, the second pass reuses the cached "asleep" state and posts a second `wake_up`, against the expected 1. `TeslaAPIReadSource.fetch` returns None for an asleep car, so `vehicle_data: 1` on the first pass cannot happen. Ruling: pass `now` into `is_awake`, or reset `lastVehicleAwakeTime` in the helper, and fix the expected counts. |
| F39 | RESOLVED | Tests are named, not line-numbered; all names exist at base. |
| F40 | RESOLVED | 1326 passed + 1 xfailed. |
| F41–F50 | RESOLVED | `readSource` sentence dropped; `KEY_REFUSED_TEXT`; questions removed and decisions renumbered 1–31; comment edits listed; `checkCharge` honours `api_only`; Fleet start `disconnected` → UNSUPPORTED and no stamp; BLE wake failure proceeds (CHANGELOG); Gen2 "mode 1" in Interfaces; quiet-queue window stated; "(restored)" kept. |

**Totals: 45 resolved, 5 partial (F3 accepted, F11, F26, F37, F38), 0 not resolved.**

## 2. Pair and per-task re-check (changes only)

| Pair / task | Result |
|---|---|
| T1 → T6 (`adopt` uses `satisfied`) | **Type gap.** Step 3 calls `satisfied(CHARGING, write.value, latest)` with the stamped string ("Charging"/"Stopped") where `satisfied` expects True/False (N2). |
| T3 → T6 (`report` branch b) | Clears `inFlight` without checking it is the same attempt (N4). |
| T3 / T6 → T8 (unstamped settled outcomes) | A settled outcome resets `tried`; with nothing stamped, `known` still disagrees, so the next pass re-plans at once (N1). |
| T4 → T8 (Gen2 `known()` fallback) | Relies on `actualCurrent` observations that no Gen2 code writes (N1). |
| T5 → T11 (`wakeOutcome`, `is_awake`) | The real-time 120 s cache defeats the provider clock (N7, F38). |
| T7 (`presentVehicles` candidate filter vs `targetsFor` test) | Contradicts itself (N9, N13). |
| T3 (debug tests) | Other existing debug tests break (N6). |
| T4, T8, T9 tests that drive the heartbeat | Fixture missing (N5). |
| Threading | No RS-485 write off the serial thread remains. The Gen2 mode-2 stop and start only touch settings under `settingsLock`. |
| Clock | One domain, apart from TeslaAPI's own `is_awake` cache (N7). |
| Forward dependencies | Gen2 `ready(START)` reads `master.desired` (Task 4) before Task 7 adds it; `ProviderOrder._ready` catches the AttributeError, so it is harmless. The `adopt` → `satisfied` lazy import comes in Task 6, with a stand-in in Task 1. OK. |

## 3. New findings

### High

**N1 — Unstamped settled outcomes are re-planned immediately: a busy loop, and a paid one on Fleet (Tasks 3, 6, 8).**
Plan text: runAttempt stamps "on `DONE` … and on `SATISFIED` for `CHARGE_LIMIT`/`AMPS` only … a disruptive stop is never stamped"; `report` → "`SETTLED` → `rec.reset()`"; step 8 makes a provider with `tried == 0` eligible with no gap.
After an unstamped settled outcome, `known` still shows the old state, so the very next pass (woken by `report`) plans the same attempt again:
- **(a) Gen2 disruptive stop.** `known()` falls back to TWC-sourced `actualCurrent`, but at base only Gen3 observes it (Gen3TWC.py:232); nothing in Gen2 does, and the plan adds no producer (its tests fabricate the observations). For a non-Tesla or anonymous car `known` stays None. The stop is re-attempted every pass on the inline local lane: a CPU busy loop on the reconciler thread. Mode 3 re-sets `stopRequested`, sending a relay stop every heartbeat; mode 2 keeps pushing `respondToSlavesExpiry` forward.
  - Even with observations, the bus is quiet after a mode-2 stop, so the last observation (still "Charging") stands, and the loop runs until a new one arrives.
- **(b) A start or stop that comes back SATISFIED** (Fleet `not_charging`/`complete`; BLE "already in state"). With a `chargingState` read under 300 s old that now disagrees, every pass sends another command. On Fleet that is a paid `charge_stop` repeated up to the 50-per-minute lane limit until the read ages past `READ_MAX_AGE` (about 160 calls). On BLE it hogs the radio.

Ruling:
1. Step 1 also returns None while `settled(key, aspect)` holds and no observation newer than `settledAt` exists, so a settled desire is re-planned only on new evidence. For disruptive stops, add an explicit RETRY floor.
2. Gen2 must publish its readings: `receive_slave_heartbeat` observes `actualCurrent` (source `"Gen2TWC"`, `seen=False`) for its `vehicleKey`. Add that to Task 8's Files, with a test that uses the real heartbeat rather than a fabricated observation.

### Medium

**N2 — CHARGING adoption compares a string write against a boolean rule (Tasks 1 and 6).** Step 3's `not satisfied(aspect, write.value, latest)` passes "Charging"/"Stopped" where `satisfied`'s CHARGING branch is defined on `desired True`/`False`. `test_user_started_car…` (write "Stopped") needs "Stopped" read as False, and `test_user_stop_in_the_app…` (write "Charging") needs "Charging" read as True. Only an explicit mapping passes both; a literal `is True` or truthiness reading fails one of them. If implemented wrong, confirming reads are adopted, giving `wantsCharge` or `userStopped` for the session. Ruling: compare in the stamp domain — map the write through `satisfied(CHARGING, True, write)` (charging-like) before comparing — and state it in step 3.

**N3 — A car that stops because the TWC stopped offering power is adopted as a user stop (Tasks 1, 6, 8).** Plan text: "adoption … of a vehicle-sourced stopped-like state newer than our start stamp → `bounds.userStopped = True`".
- Under Track Green Energy the TWC offer drops, and the car reports "Stopped" with no stop command from us.
- That read is newer than our "Charging" start stamp and differs from it, so it becomes `userStopped`.
- From then on every distributor start is ignored for the session, and `VehicleEndpoint.wantsToCharge` goes False, so the point gets no allocation.

Spec "hands off": a divergence our own offer explains is not a user change. Ruling: adopt `userStopped` only while the point was offering at least its minimum (or while the car was drawing) when the stopped read arrived; otherwise hands off.

**N4 — A lane-detail report clears `inFlight` without an identity check (Tasks 3 and 6).** Plan text: report (b) → "`rec.inFlight = None` and nothing else". A late `replaced`/`dropped`/`cancelled` report for an older entry (for example after `endSession` reset the record and a new attempt was submitted) clears the *new* attempt's `inFlight`. The next pass then submits a duplicate, which replaces the pending one, whose report clears `inFlight` again: churn while the lane is busy. Ruling: clear only when `rec.inFlight is attempt` (and `probeInFlight` likewise).

**N5 — Mandated heartbeat tests cannot run as written (confirmed at base).**
- (a) `from tests.unit.test_gen2_idle_minimum import drive` (Task 8 `test_heartbeat_stop_targets_the_anonymous_car`, Task 9 `test_heartbeat_does_not_write_amps…`): no `drive` exists, so ImportError. The parenthetical "expose its driver as `drive(...)` if it is inline there" does not match the file's `heartbeat(s, state, maxA, actA)`, which also needs an Interface module.
- (b) Task 4 `test_mode_3_stop_is_sent_by_the_heartbeat_not_the_caller` calls `s.send_master_heartbeat()` on the `make()` master. Confirmed: IndexError at TWCSlave.py:598, because no Interface module is registered (the plan's note mentions only the Policy mock).

Ruling: add a shared helper (for example `tests/unit/gen2_helpers.drive(master, slave, amps_actual)`) that registers a Mock Interface and a Mock Policy and feeds `receive_slave_heartbeat`, and use it in all three tests.

**N6 — Task 3 rewrites one debug test, but two more break.** `test_provider_order.py::test_debug_command_tries_each_provider_once` asserts fall-through from BLE to Fleet, which Decision 28 now forbids. `test_debug_set_charge_rate_reaches_fleet_past_a_covering_twc` uses `master()` with no `lanes`, so the Mock's `submit` returns a truthy Mock and the `is False` and `f.calls` assertions fail. Ruling: list both in Task 3's Files (rewrite the first to one provider; give the second a `Lanes(inline=True)`).

**N7 — The Task 5 wake test is defeated by `is_awake`'s real-time cache.** In `test_wake_checks_the_free_online_state_first…`, the first `p.wake` caches "online" for 120 s of real time, so the second call (matcher switched to asleep) still returns `SATISFIED "online"`, not `"wake held"`. Ruling: `wakeOutcome` passes `now` into `is_awake`, or bypasses the cache (`lastVehicleAwakeTime = 0`) before its own online check; the test then drives it with `p.clock`.

**N8 — Adopting a settled apply sets `adopted=True` (Task 6).** Plan text: `beforeWrite` → "an apply → `desired.adopt(key, CHARGE_LIMIT, believed.value)`". An apply settles only as "already at N%" (current == desired), so the plan-time `satisfied` check would end it anyway. Marking it adopted means later non-decision `set`s are ignored until a decision, which includes Policy's `limitOverride` lowering, the stop-by-limit path. Ruling: an apply that settles leaves desired unadopted (it is already satisfied by the read); only restores need the `clear`.

**N9 — Task 7 test contradicts the candidate filter.**
- Plan text: "Every present list is further filtered to vehicles that have at least one candidate for the capability in question."
- `test_present_rule_until_phase_5` expects `targetsFor(m, None, aspect=CHARGING)` to include `anon:8245`.
- That anonymous car has no candidate: mode 1, BLE needs a VIN, and no slave serves 8245.

Ruling: either the expected list drops `anon.key`, or the test sets mode 2 with a slave on 8245. Also give `presentVehicles` a `capability` parameter (N13).

**N12 — A free-only backoff blocks new desires for up to an hour without a BLE ping (Task 6; F3 follow-up).** After `attempts()` failures, `backoffUntil` grows to 3600 s and survives a desired change, because `set` does not reset the record. On a BLE-only install, a new stop or limit then waits out the backoff with no attempt and no ping. The spec says backoff resets "on success/arrival/plug-in", and the user's ruling says ping before assuming BLE is down. For a stop the TWC's minimum keeps drawing meanwhile. Ruling: a changed desired value (or `decision=True`) starts a new round for that aspect, or a probe runs once `PROBE_AFTER` has passed even without a paid candidate.

### Low

**N10 — The adoption step's identity check can miss.** Plan text: `vehicle.trusted(field) is latest`, with `latest = latestFrom(field, exclude=…)`. `trusted()` looks at the overall latest observation, so when an excluded source wrote the field last, adoption is silently skipped. Harmless today (TWC sources do not write these three fields). Use a `trusted(field, exclude=)` variant.

**N11 — `HeldLimits.holding()` may return `id:` keys.** If it does, `onDeparture` sets a desire for `"id:…"`, and `pass_` then calls `endSession` on it every pass. State that `holding()` and `vins()` return VIN keys only.

**N13 — `presentVehicles(master)` takes no capability, yet must filter "for the capability in question".** Make it `presentVehicles(master, capability)` and have `targetsFor` and `applyPolicyLimit` pass theirs.

## Counts

Pre-flight 1: 45 resolved, 5 partial (F3 accepted; F11, F26, F37, F38 open), 0 not resolved.
New: High 1 (N1), Medium 9 (N2–N9, N12), Low 3 (N10, N11, N13).
