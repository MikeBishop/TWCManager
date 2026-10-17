# Pre-flight conflict scan: slim Phase 3 plan, Tasks 6–14

- Plan: `.superpowers/plans/2026-10-15-vehicle-model-phase3-slim.md`
- Spec: `.superpowers/specs/2026-10-13-vehicle-model-design.md`
- Rulings: `progress.md` (simplification line 62, Q1–Q4 line 66)
- Code: `scratchpad/wt-vm3` at 39d7cfb (`vehicle-model/phase3`), read only. An exported copy of 39d7cfb is in `scratchpad/preflight-slim/base`, and the probes are in `base/tests/unit/test_preflight_slim_probe.py`.
- Probe run (the required pytest command): `test_preflight_slim_probe.py`, `test_vehicle_command_queue.py`, `test_lanes.py` and `test_provider_outcomes_local.py` gave **83 passed**. All 8 probes confirm the facts they assert (P1–P8 below).

Result: **3 High, 10 Medium, 12 Low.**

---

## 1. Shared files and interfaces (producer → consumer)

| # | Producer | Consumer | Checked | Result |
|---|---|---|---|---|
| 1 | T6 `VehicleCommandQueue(run=, key=, isHigh=, report=, lost=, inline=)` | T6 `Workers`, `test_vehicle_command_queue.py` (unchanged) | ctor signature; `resolve_module` positional; private attrs the legacy test reads | OK, with a constraint: the test reads `_cond/_high/_low/_busy/_draining/_thread` (P6), which pins the internals → **L1** |
| 2 | T6 `VCQ.drain_high_priority` | T6 `Workers.drain`, T10 shutdown | close+wait fused in one call; drains run in sequence | **M6**: BLE stays open while cloud drains |
| 3 | T6 `VCQ.remove(match)` | T6 `Workers.cancel`, legacy `cancel` shim, T11 `cancelStopCarsCharging` | stops only | OK. The gap is in what T11 needs (**M7**) |
| 4 | T6 `runAttempt(master, attempt, rateLimits)` | T6 `Workers`, T9 tests | signature change from `(master, lane, attempt)`; probe branch gone | OK. `test_lanes` calls `runAttempt(m, lane, …)`, retargeted by the T6 test port |
| 5 | T6 `RateLimits.allows/note(…, aspect)` | T9 `plan()` (`workers.allows(p, cap, vin, aspect)`) | key `(name, aspect or cap, vin)` | OK |
| 6 | T6 `Provider.worker` | T6 `runAttempt` read filter, `Workers.submit`; `reconcile_helpers.ScriptedProvider` | default `"cloud"`; the plan says only "ScriptedProvider gets `worker`" | Under-specified: `ScriptedProvider("TeslaBLE"/"Gen2TWC")` needs `ble`/`local` derived from its name or passed in → folded into **L5** |
| 7 | T6 `Workers._report` → callback | T9 `VehicleReconciler.report` → T7 `noteOutcome(key, aspect, …)` | one-shots have `aspect=None` | **L2**: `_checkAspect(None)` raises |
| 8 | T7 `DesiredStore.noteOutcome/clearIf/free/adopt`, `FreeChannel`, `AttemptRecord` fields | T9 `plan()`/`report()`, T11 heartbeat, T12 lift | names: `lastFreeAt/paidAt/paidRetryDue/settledAt/lastSentAt`, `failingSince/lastAttemptAt` | Names consistent. `failure()` has a semantic bug → **M1** |
| 9 | T7 `NOT_SENT` | T7 `noteOutcome`, T9 fallback rule | which outcomes are "no request" | `"online check failed"` and rules/read details are missing (**L3**). NOT_SENT outcomes have no re-plan gate → **H2** |
| 10 | T7 `ControlState.lastStopProvider` | `Gen2TWCProvider.ready` (built), T9 `afterWrite`, T11 | kept | OK |
| 11 | T8 `Provider.DECLARATIONS/SUPPRESSED`, `Suppressions.conditions()` | `ProviderOrder.ordered/candidates`, `orderReadSources`, test doubles | providers without a table | **M5**: fails open |
| 12 | T8 deletes `Provider.attempts()` | `Order.dispatch:151`, `VehiclePriority:294` (live until T13) | P4 | **H1** |
| 13 | T8 `slot.usable("wake")`, `reportScopeRefused("wake")` | `TeslaTokenSlot.SCOPES/SCOPE_LABELS` | P3 | **M4**: KeyError |
| 14 | T9 `VehicleReconciler(master)` registers `desired.onChange`, `workers.setReport` | T10 `TWCMaster.__init__` (desired → workers → reconciler) | construction order; tests replace all three | OK |
| 15 | T9 `known/newerReading/satisfied` + `FIELD_FOR[AMPS] = "chargeCurrentRequest"` | T6 test, T12 | field registered only in T12 | **M2**: forward dependency (P1) |
| 16 | T10 `Targets.targetsFor/presentVehicles` | T11 `start/stop/cancelStopCarsCharging` | `targetsFor(master, vin, capability)` | OK |
| 17 | T11 `TWCSlave.vehicleKey` | heartbeat start/stop/cancel | `vehicleKey` lives on `EVSEInstance/Gen2TWC.py:94` (the subclass `newSlave` builds), not on `TWCSlave` | OK for production and `make()`. A bare `TWCSlave` in a test has no `vehicleKey` |
| 18 | T12 `desired.set(key, AMPS, …, lift=True)` | T9 `plan()` lift branch (`clearIf(key, AMPS, d.value)`) | lift cleared once satisfied | OK |
| 19 | T6/T10 `Workers.drain(timeout)` | T10 shutdown, T14 row 18 | row 18 says `drain(60)`; T10 gives it the remaining time | **M9** |

## 2. Each task's internal consistency

| Task | Checked | Result |
|---|---|---|
| 6 | 25 retained tests vs the VCQ interface | Retained tests use `lane.stop()`, `lane._peek()`, `lane._entries()` and `summary()["running"]`, none of which are in the VCQ interface (**L1**). The drain tests need the worker gated (**M6**). `test_rate_slot_…` needs `chargeCurrentRequest` (**M2**). Files lists 1 probe test to delete in `test_provider_outcomes_local.py`, but 5 use `probe` (**M3**, P7) |
| 7 | test `test_note_outcome_bookkeeping` traced line by line against the `noteOutcome` spec | Consistent. Helpers `attempt()` and `VIN2` are not in `test_outcome_desired.py` (**L5**) |
| 8 | the three tests vs Interfaces | `providers_of_every_kind()`/`master()` are undefined (**L5**). The wake 403 path needs a `SCOPES` entry (**M4**). Removing `attempts()` breaks 5+ tests outside the two listed (**H1**) |
| 9 | each named test traced through the `plan()` pseudo-code | RF1, RF2, `ble_only…`, `restore…hourly`, `pairing…` and `unknown…` all trace as written. `test_stale_free_failure…` fails with `failingSince or at` and a 0.0 seed (**M1**, P2) |
| 10 | Interfaces vs tests | Sound. Shutdown time split (**M9**). The interim legacy start path (**M10**) |
| 11 | tests vs Interfaces | RF3 holds only inline (**M7**). `del m.slaveTWCs[...]` does not touch `slaveTWCRoundRobin` (**L6**). `respectVehicleSchedule` is missing (**H3**) |
| 12 | Interfaces vs tests | Consistent. Test source naming (**L11**) |
| 13 | grep test vs the deletion list | Leftover `VehiclePriority` mentions and the `getLastStartOrStopChargeTime` getter (**L7**). The line check is defined but weak (**L8**) |
| 14 | helpers named | `test_gen2twc_provider.make`, `api_with_registry` (test_carapivehicle_registry:11), `test_teslable_pairing_status.make`, `make_ha` (test_homeassistant_registry:8) all exist. Rows 17 and 18 (**L4**, **M9**) |

## 3. Global Constraints, spec and user decisions

| Item | Plan | Result |
|---|---|---|
| Lanes on the existing queue, two workers | T6: VCQ generalized; `ble`/`cloud` instances plus the legacy one until T13; local inline | Complies |
| One fallback rule | T9 `freeFailed`/`paidAgain`; one `FreeChannel` per car; stale (> `PROBE_AFTER`) → a real BLE try first | Complies (Q2 reading). The NOT_SENT hole is **H2** |
| Adoption for the charge limit only | T7 `adopt` raises `ValueError` otherwise; T9 `adoptable` CHARGE_LIMIT only | Complies |
| Provider declarations as data | T8 class tables; `ready()` stays code | Complies. Table-less providers fail open (**M5**) |
| Q1: one retry after a failed paid call | `paidRetryDue` | Logic complies. The cost premise "≤ $0.001 extra" is wrong on the wake path (**M8**) |
| Q3 hourly restore; Q4 re-shun waits for a newer vehicle reading | `RESTORE_RETRY`; `newerReading` stand-in only without vehicle sources | Complies |
| No regression | — | **H3** (`respectVehicleSchedule`), **H1** (legacy retry counts) |
| Spec "lanes report outcomes, never decide fallback" | `Workers` only report | Complies |
| Spec fast-aspect bounds and backoff ladder | dropped by user decision (line 62) | Intended |
| "Everything bounded" | — | **H2** |

## 4. References to code at 39d7cfb (spot-checked)

| Reference | Found | Note |
|---|---|---|
| `VehicleCommandQueue.py` (194 lines), `_DISPATCH`, `_key`, `_is_high_priority`, `cancel`, `drain_high_priority`, `_applyChargeLimitKwargs`, `_setAmps` | yes | |
| `Reconcile/Lanes.py` 674 lines; `runAttempt`, `entryKey`, `writtenValue`, `_reconcilerParts`, `LANE_PROVIDERS` | yes | |
| `Provider.PROBE`, `Provider.probe`, `Provider.attempts`, HA `attempts` override | yes | `attempts` callers: Order.py:151, VehiclePriority.py:294 |
| `TeslaBLEProvider.probe`, `TeslaBLE.probe`, `_sendCommand_internal(noteProof=)` | yes | only `probe` passes `noteProof=False` (TeslaBLE.py:510) |
| `Order.debugCommand` (uses `master.lanes`) | yes | |
| `Desired.py` (567): `SessionBounds`, `ChannelHealth`, `release`, `endSession`, `noteOffering`, `probeInFlight`, `offering*`, `_chargingLike`, `CHARGING_LIKE`, `newRound`, `forced` | yes | |
| `Suppressions.suppressed/_localStops/commandPolicy` | yes | current rule is generic on `provider.local` |
| `TeslaAPI.wakeOutcome`, `wakeDue`, `command`, `_paidPost` 403 → `reportScopeRefused("command")`, `WAKE_RETRY_SECONDS = 1800` | yes | |
| `TeslaTokenSlot.RETIRED_ON_REFUSAL = {"command"}`, `SCOPES`, `SCOPE_LABELS`, `usable`, `refuse` | yes | no `"wake"` key |
| `TWCMaster`: `vehicleCommandQueue`, `VEHICLE_COMMANDS`, `queue_vehicle_command`, `_resolveVehicleCommandModule`, `calculateModulePriority`, `getModuleByPriority`, `get/save/removeNormalChargeLimit`, `lastChargeLimitApplied`, `start/stop/cancelStopCarsCharging`, `stopRespondingToSlaves`, `heldLimits`, `providerOrder` | yes | |
| `TWCManager.py`: `vehicleCommandQueue.start()` :845, `shutdownDeadline` :2047, `drain_high_priority(60)` :2055, `checkArrival/checkDeparture` :320–342, `get_vehicle_module` | yes | module list `"Vehicle.VehiclePriority"` at :85 is not in T13's Files |
| `Policy.py` :326 `lastChargeLimitApplied` + queued `applyChargeLimit`; :271 `stopAskingToStartCharging` loop | yes | |
| `TWCSlave`: `_queueChargeRate`, `_requestVehicleRateRaise`, `_resetVehicleRateRaised`, `vehicleRateRaised`, `__lastAPIAmps*`, `minAmpsToOffer`, `reportedAmpsActual`, `stopRequested`, `_evseTargetAmps`, start/stop/cancel calls :575/582/592/1077 | yes | |
| `EVSEInstance/ChargingPoint.py`, `Gen2TWC.py` (`vehicleKey` :94), `VehicleEndpoint.py` (`REFRESH_SECONDS`, `_lastAmps`, `_lastQueuedAt`, `setTargetPower`) | yes | |
| `Registry/Fields.py` `FIELDS` | yes | no `chargeCurrentRequest`; `scheduledChargingPending` present |
| `Registry/Sources.py`, `FleetTelemetryMQTT.py`, `HomeAssistant.py` | yes | |
| T13 TeslaAPI deletions: `car_api_charge`, `applyChargeLimit`, `_unavailableResult`, `setChargeRate`, `_chargeRateAccepted`, `_recordChargeRate`, `CHARGE_RATE_RESEND_AFTER`, `wakeVehicle`, `apply_charge_limit`, `stopAskingToStartCharging`, `lastLimitAttemptTime`, `lastChargeRateSent*`, `carApiLastStartOrStopChargeTime` | yes | `WebIPCControl.py:321` calls `carapi.getLastStartOrStopChargeTime()` |
| T13 TeslaBLE: `car_api_charge`, `applyChargeLimit`, `setChargeRate`, `startCharging`, `stopCharging`, `_stopAskingToStartCharging`, `_allVehicleTargets`; HA: `car_api_charge`, `applyChargeLimit`, `setChargeRate`, `_vehiclesFor` | yes | |
| `Control/HTTPControl.py` "any VehiclePriority reference" | none exist | no-op |
| `targetAmps` | VehiclePriority.py only | goes with the file |
| `presence/2-charge-limits:lib/TWCManager/ChargeLimitRules.py` (`decideChargeLimit(limit, current, saved, sendWhenUnknown)`, `needsLiveRead(limit, telemetryCurrent, saved)`) and its test file | yes | port is feasible |
| `tests/unit/gen2_helpers.drive(master, slave, amps_actual, …)` | yes | |
| Line-budget row "6a6c14e..39d7cfb +2,486 / −162" | `git diff --shortstat` gives exactly this | |

## 5. Forward dependencies and a green suite at each boundary (three queues until T13)

| Boundary | Risk | Result |
|---|---|---|
| after T6 | legacy VCQ test unchanged; Lanes users (`test_provider_order.py:120`, `test_carapivehicle_registry.py:135`) are listed | 4 extra probe tests (**M3**); `chargeCurrentRequest` (**M2**) |
| after T7 | Desired importers: `Gen2TWCProvider.ready` only; `Run.py` uses `FIELD_FOR`/`Attempt` | OK |
| after T8 | `attempts()` removed while dispatch and VehiclePriority still walk it; `test_vehicle_priority.py:36,98,150`, `test_provider_outcomes_local::test_dispatch_reads_outcomes…` (asserts `len(a.calls) == 3`), `test_provider_order::test_dispatch_walks…`, `test_provider_capabilities:43` | **H1**: red. Suppression doubles (`test_provider_order.py:66–77`, `test_vehicle_priority.py:43–51`, `test_provider_outcomes_local.py:49` with a `Mock` provider) → **M5** |
| after T9 | reconciler not wired; tests build their own store, workers and reconciler | OK |
| after T10 | legacy start path still live; `TeslaAPI.py:926–927` reads the deleted `lastChargeLimitApplied` | **M10** |
| T10–T11 | legacy queue serves `charge` and `setChargeRate`; workers serve limits; both reach TeslaBLE through `_bleLock` | OK (serialized) |
| T11–T12 | start/stop on the workers; rates on the legacy queue | OK |
| T13 | legacy queue and VCQ legacy mode deleted; `test_vehicle_command_queue.py` tests are moved first | OK, plus the **L7** leftovers |

## 6. Cost, wiring and threading

| Check | Result |
|---|---|
| A paid call without a free failure | Only when no free candidate exists (including free providers excluded by REFUSED/UNSUPPORTED). Per the rule |
| Paid multiplied by retries | Blind: at most 1 extra per desire (command). The wake path breaks the "$0.001" premise (**M8**). Non-blind repeats are one per `RETRY` per newer disagreeing reading; under a polling reader that is open-ended but at main's cadence (**L12**) |
| NOT_SENT outcomes (`wake held`, `backoff`, `wake refused`) | No time gate → spin (**H2**) |
| Wake rules | `allowWake`: raise only, never a restore, start yes, amps only through a local provider. Fleet wake only via `wakeOutcome` (free online check first). OK |
| Fleet start vs in-car schedule | **H3** |
| Pending attempt after its desire changes | a queued start with a wake still runs (**M7**) |
| Wiring | Mode 3 holds the floor (6 A bound, spec). Mode 2 keeps the TWC at its max: after two failed paid rates on a stable target the car keeps its old rate until a newer reading; main also stops repeating after about 5 (**L12**). Disruptive stop: a 60 s BLE-first excursion at the TWC minimum (Q1 user answer) |
| RS-485 off the serial thread | Gen2 provider publishes `stopRequested`/`settings`; Gen3 `setUnitTarget` does no I/O. OK |
| One clock | `Reconcile/` uses `time.time`; `RateLimits` and drain use monotonic (durations). `TeslaAPIReadSource.fetch` uses `time.time`. OK |
| No I/O under locks | `report` → `noteOutcome` (leaf lock) → `wake()`. VCQ must deliver `lost`/`report` outside `_cond` (**L9**) |
| Bounded | `MAX_PENDING = 64` per worker; one pass per wake; TICK 1 s. **H2** breaks this; a `plan()`→submit exception wedges `inFlight` (**L10**) |
| Shutdown | **M9** |

## 7. Line budget

| Item | Plan | Measured / assessed |
|---|---|---|
| Phase 3 so far | +2,486 / −162 | exact |
| Legacy deletions (T13) | ≈ −2,150 | function sizes at 39d7cfb: TeslaAPI candidates 1,007 (`car_api_charge` 332, `car_api_available` 260 of which only the wake loop goes, `applyChargeLimit` 195, `setChargeRate` 82, `apply_charge_limit` 71, …), TeslaBLE 436, HA 201, VehiclePriority 333, TWCMaster 77 (+constants), Order 34, VCQ legacy 60 → about 2,050–2,250. Plausible |
| Lanes −674 / Run +260 / VCQ +100 net | — | plausible (`runAttempt` ≈ 120, Workers ≈ 80, RateLimits ≈ 40) |
| Desired −250 | — | optimistic: removable functions and classes measure 124, plus fields and `adopt` branches; FreeChannel, `noteOutcome` and `clearIf` add about 80 back → ≈ −100..−150 |
| Reconciler ~360 | tripwire at 450 | optimistic for this codebase's comment density (`satisfied/known/handsOff/allowWake/newerReading/plan/beforeWrite/afterWrite/report/pass_/run/summary`). Expect 400–550; the tripwire may fire |
| Task 13 check | `git diff --numstat 39d7cfb -- lib`, `exit !(d >= a)` | Well-defined (working tree vs 39d7cfb, tracked files; T13 adds no lib file; `origin/main` resolves in wt-vm3). It enforces only removed ≥ added, which is very likely (≈3,000 vs ≈1,400). The stated budget (added ≤ 1,400, removed ≥ 3,000) is not enforced (**L8**) |

## Probes (base 39d7cfb, `test_preflight_slim_probe.py`, all pass)

- P1: `observe`/`noteWrite("chargeCurrentRequest")` raise `KeyError`.
- P2: `failingSince or at` loses a 0.0 seed: `Clock(1000)() - PROBE_AFTER - 400 == 0.0`.
- P3: `"wake"` is in neither `SCOPES` nor `SCOPE_LABELS`.
- P4: `Order.dispatch` and `VehiclePriority` call `attempts()`.
- P5: a Fleet attempt reporting `UNREACHABLE "wake held"` is re-runnable at once; nothing in the lane gates it, and the slim `plan()` adds no gate.
- P6: `test_vehicle_command_queue.py` reads `_cond/_high/_low/_busy/_draining/_thread`.
- P7: five `test_provider_outcomes_local.py` tests call `probe(`.
- P8: today's `localStops` suppresses a table-less non-local provider (`ScriptedProvider("FleetAPI")`).

---

## Findings

### High

**H1. Task 8 deletes `attempts()` while the legacy dispatch still walks it (Tasks 8–12).**
- `Order.dispatch` (Order.py:151, `range(attempts or p.attempts())`) and `VehiclePriority.__getattr__` (VehiclePriority.py:294) call it. Both serve live paths until Task 13: `setAmps`/`setChargeRate` until T12, `charge` until T11. The call sits outside their `try`, so every legacy walk raises `AttributeError`.
- The suite goes red at the Task 8 boundary: `test_vehicle_priority.py` (:36, :98, :150), `test_provider_outcomes_local.py::test_dispatch_reads_outcomes_until_the_facade_goes` (asserts 3 BLE calls), `test_provider_order.py::test_dispatch_walks_candidates_with_attempts_and_stats`, `test_provider_capabilities.py:43`.
- The plan gives no count for the interim, and the count decides paid retries (Fleet 2, HA 1).
- **Ruling:** keep `attempts()` (and HA's override) until Task 13, which deletes it along with `dispatch`. Move `assert not hasattr(Provider, "attempts")` to `test_no_legacy_command_paths.py`. Alternative: Task 8 inlines a private legacy count (3 local / 1 HA / 2 other) in `dispatch` and `VehiclePriority`, with the listed tests kept.

**H2. NOT_SENT paid outcomes have no re-plan gate: reconciler and cloud worker spin for the whole hold.**
- Trace: Task 7 `noteOutcome` leaves `paidAt`, `lastSentAt` and `settledAt` untouched for a NOT_SENT detail (`"wake held"`, `"backoff"`, `"wake refused"`). Task 9 then computes `paidAgain = paidAt is None` → True, `freeFailed` is True (Fleet-only, or BLE failing), and `report()` calls `wake()`. The next pass re-plans and re-submits the same Fleet attempt at once.
- `"wake held"` lasts `WAKE_RETRY_SECONDS = 1800` (or `wakeDelayMins`). `"backoff"` lasts the API error backoff. `"wake refused"` (Task 8) lasts until the token changes, so the loop is effectively permanent while a start or raise is desired.
- Cost: on an asleep car each loop costs only the cached free `vehicles/{vin}` check (120 s cache). `TeslaAPIReadSource.fetch` gates `vehicle_data` behind `is_awake`. On an awake car under `"backoff"`, read-before-write may pay one `vehicle_data` ($0.002) per `READ_MAX_AGE` (300 s) while the loop runs on a Fleet-only car.
- Mainly it breaks "everything bounded": a continuous loop on two threads, with log churn.
- `test_a_wake_held_outcome_is_not_counted_as_the_paid_call` and `test_a_refused_fleet_wake_does_not_exclude_fleet…` would pass while the loop runs, because they count POSTs.
- **Ruling:** hold only NOT_SENT outcomes. `noteOutcome` already stamps `lastOutcome/lastOutcomeAt` for them. `plan()` returns None for a `(key, aspect)` whose `rec.lastOutcome.detail in NOT_SENT` while `now - rec.lastOutcomeAt < RETRY[aspect]`.
  - Do not gate every non-SETTLED outcome. That would break `test_stale_free_failure_gets_the_real_command_over_ble_before_paid`, whose second pass, at the same instant as the BLE `UNREACHABLE`, must send Fleet at once.
  - LANE_DETAILS losers stay exempt; they never ran.
  - Add `test_a_not_sent_outcome_is_not_replanned_inside_retry`: Fleet-only, `wake` scripted to `"wake held"`, 10 passes at one instant → 1 wake call; one more after `RETRY`.

**H3. `respectVehicleSchedule` regresses: a Fleet start overrides the car's own charging schedule (from Task 11; permanent after Task 13).**
- Main's `TeslaAPI.car_api_charge` (TeslaAPI.py:899–917) skips `charge_start` while `scheduledChargingPending` and `respectVehicleSchedule` (default True). The comment there explains why: a start overrides the in-car schedule and charges at full rate at once.
- `FleetAPIProvider.startCharging` (Task 5, built) has no such check. `TeslaBLEProvider.startCharging` keeps it (`SATISFIED "scheduled"`). HA never had it.
- Once Task 11 routes starts through the reconciler, a Fleet-only or BLE-down car gets a paid wake ($0.02) plus `charge_start` ($0.001) against the user's schedule. Each newer "Stopped" reading re-sends it every `RETRY[CHARGING]`.
- Neither plan mentions it, and the Task 14 table has no row for it.
- **Ruling:** Task 9 `handsOff(CHARGING, True, …)` also returns a reason when `vehicle.value("scheduledChargingPending")` is True and `config.respectVehicleSchedule` (default True). The field is already in `FIELDS`. This covers every provider; BLE's provider check stays. Add a Task 11 test (Fleet-only, schedule pending → no `wake_up`, no `charge_start`) and a Task 14 row "Fleet-only, schedule pending, heartbeat start: skipped → skipped, 0 → 0".

### Medium

**M1. `FreeChannel.failure` as specified (`failingSince = failingSince or at`) breaks `test_stale_free_failure_gets_the_real_command_over_ble_before_paid`.**
- The test seeds `failure(c() - PROBE_AFTER - 400)`, which is 0.0 on `Clock(1000)`. The next BLE failure at 1000 then replaces the falsy 0.0, so the "fresh failure lets paid go at once" pass sees `now - failingSince == 0 < 300` and sends nothing (P2).
- The current `ChannelHealth.failure` has the same idiom.
- **Ruling:** `if self.failingSince is None: self.failingSince = at`. Optionally also seed the test away from 0.0.

**M2. Forward dependency: Task 6 `test_rate_slot_is_used_only_when_a_command_is_sent` is an AMPS read-satisfied case, but `chargeCurrentRequest` joins `FIELDS` only in Task 12.**
- `observe`/`noteWrite` of that field raise `KeyError` at the base (P1).
- **Ruling:** write the test with `SET_CHARGE_LIMIT` and a Fleet `RateLimit(2, 60)` table on the scripted provider, or move the `Fields.py` addition into Task 6. AMPS stamps also fail (caught and logged) until Task 12; that is harmless because no AMPS desire exists before then.

**M3. The probe removal in Task 6 touches four more tests than the plan lists.**
- In `test_provider_outcomes_local.py` these also call `p.probe` (P7):
  - `test_a_failing_command_or_probe_logs_no_raw_output_at_info_or_above`
  - `test_key_refusal_inside_the_pairing_window_is_a_retryable_error_and_keeps_the_claim`
  - `test_key_refusal_outside_the_pairing_window_is_refused_and_drops_the_claim`
  - `test_an_answered_probe_closes_an_open_circuit_breaker`
- The last one pins a Task 4 fix, "an answered probe closes the breaker". Without the probe, the breaker's own 60 s half-open recovery (`BLECircuitBreaker.recovery_timeout`) is the only way out, and BLE retries at `RETRY` (≥ 60 s) already meet it.
- **Ruling:** list these four in Task 6. Drop the `probe` assertions from the first three. Replace the fourth with "an open breaker half-opens after `recovery_timeout` and a successful command closes it".

**M4. A Task 8 `"wake"` purpose crashes the slot.**
- `TeslaTokenSlot.usable("wake")` → `grants` → `missingScope` → `SCOPES["wake"]` → `KeyError` for any Fleet token with a `scp` claim. `reportScopeRefused("wake", refused=True)` → `SCOPE_LABELS["wake"]` → `KeyError` (P3).
- **Ruling:** Task 8 Files gains `SCOPES["wake"] = ("vehicle_charging_cmds", "vehicle_cmds")` and `SCOPE_LABELS["wake"] = "waking the car"`, besides `RETIRED_ON_REFUSAL |= {"wake"}`. `wakeOutcome` checks `slot.usable("wake")` before the free online check; the probe in `test_a_403_on_wake…` counts `wake_up`. `slotFor("command")` stays the slot chooser.

**M5. Table-based suppressions fail open for providers that declare no table.**
- Today `Suppressions.suppressed` applies `ble_only` and `localStops` to any `not provider.local` provider (P8). Under Task 8 a provider without `SUPPRESSED` is never suppressed, which can let a paid command through under `ble_only`.
- Test doubles break: `test_provider_order.py:66–77` (`P("FleetAPI")` under `ble_only`/`api_only`), `test_vehicle_priority.py:43–51`, and `test_provider_outcomes_local.py:49`, where a `Mock(local=False)` provider makes `capability in Mock()` raise `TypeError`.
- **Ruling:** `Provider.SUPPRESSED` defaults by locality: `CLOUD_SUPPRESSED` when `local` is False, else `{}`, as a class-level property or a `suppressedFor(condition)` helper that reads `getattr(type(p), "SUPPRESSED", None)` and falls back to the locality rule. Task 8 lists the doubles to adjust.

**M6. Drain: `drain_high_priority` fuses "close and drop" with "wait", so `Workers.drain` (cloud, then BLE) leaves BLE open during the cloud wait. The retained Review Focus 5 tests cannot be set up as described.**
- While the cloud stop runs (up to the 10 s Fleet timeout), the BLE worker finishes its current attempt and starts the pending limit. Review Focus 5 says that limit is dropped. The started BLE limit then holds BLE's own drain until the deadline.
- With the never-started runner gone, `test_drain_runs_pending_stops_only` and `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit` cannot work as written. A never-started queue drops everything and returns False. A started idle worker runs the limit before `drain` is called. "The test starts the queue first" does not resolve this.
- **Ruling:** split VCQ into `close()` (sets draining, drops non-high through `lost`, one INFO) and `waitDrained(deadline)`. `drain_high_priority(timeout)` is the two in sequence, keeping the legacy test. `Workers.drain` closes both queues first, then waits on one monotonic deadline. Both RF5 tests gate the worker with a blocking first attempt, as `test_drain_on_a_started_lane_lets_its_thread_run_the_pending_stop` does, then submit the limit and the stop, then drain.

**M7. A queued attempt is not withdrawn when its desire changes or is cleared. Review Focus 3 holds only inline.**
- `Workers.cancel` removes stops only, and `runAttempt` never re-reads the desire. So a start that was planned and is still pending on a busy cloud or BLE worker runs after the heartbeat's zero-offer `clearIf(CHARGING, True)`: a Fleet wake ($0.02) and `charge_start`.
- The same happens after a start→stop flip. The reconciler cannot plan the stop while `rec.inFlight` is the queued start, so the start runs and the stop follows. Main cancelled pending starts on stop (`stopCarsCharging` → `cancel("charge", start)`).
- **Ruling:** at the top of `runAttempt`, before the read, for an aspect attempt that is not a stop: when `isinstance(getattr(master, "desired", None), DesiredStore)`, read `d = master.desired.get(key, aspect)`. If `d is None or d.value != attempt.value`, return `Outcome(ERROR, "cancelled")`, a LANE_DETAILS loser with no request and no read.
  - The `isinstance` guard matters: the Mock masters in `reconcile_helpers.make_order` and `test_provider_order.lanes_master` would otherwise answer `.get()` with a Mock and cancel every attempt in the Task 6 tests.
  - The alternative is the same check in `VehicleReconciler.beforeWrite`, which only runs for a real reconciler. It sits after read-before-write, so one stale, possibly paid, read can still happen. The `runAttempt` guard is preferred.
  - Add a threaded Task 11 test: block the cloud worker, plan a Fleet start, set zero offer, release → no `wake_up` and no `charge_start` POST.

**M8. Q1's cost premise does not hold on the wake path; the user approved "≤ $0.001 extra per desire".**
- If the desire's first paid request is the wake itself, the bound fails. A sent `wake_up` that returns asleep/offline gives `UNREACHABLE "asleep"`, which is not in NOT_SENT, so `paidRetryDue = True`.
- The blind retry 300 s later meets `"wake held"` (the 30-min `delayNextWakeAttempt`). That outcome loops (H2), and a second `wake_up` ($0.02) goes out when the hold lifts.
- The retry may also repeat a `vehicle_data` read ($0.002) on a Fleet-only car once the stored value is older than `READ_MAX_AGE`.
- **Ruling:** the blind retry is planned with `wake=False`; a woken car is still awake, and a sleeping one stays held anyway. If the first failure was the wake, `paidRetryDue` stays False: `runAttempt` tags wake failures with a `"wake "` detail prefix that `noteOutcome` reads. Then the extra cost is ≤ $0.001 (+ $0.002 read on Fleet-only). Restate that number to the user.

**M9. The shutdown time budget leaves nothing for `saveSettings`, and the stated test cannot assert it.**
- Task 10 gives `workers.drain` and then the legacy drain "the remaining time" of the 80 s `shutdownDeadline`. A hung BLE or cloud attempt can use all 80 s, so the background-task wait (`saveSettings`, which persists `heldLimits`) exits at once.
- Today the vehicle drain is capped at 60 s, leaving at least 20 s.
- `test_sigterm_shutdown.py` runs the real process in a subprocess and cannot observe drain timeouts.
- Task 14 row 18 says `workers.drain(60)`, which contradicts Task 10.
- **Ruling:** `vehicleDeadline = min(shutdownDeadline - 20, now + 60)`; both drains share it. Pin it with a unit test of a small helper (`shutdownTimeouts(now, deadline)`), not `test_sigterm_shutdown`. Fix row 18.

**M10. The Task 10 interim breaks or bills the legacy start path.**
- `TeslaAPI.car_api_charge` calls `self.applyChargeLimit(self.lastChargeLimitApplied, checkArrival=True)` before every Fleet start (TeslaAPI.py:926–927). Task 10 deletes `TeslaAPI.lastChargeLimitApplied` and `stopTryingToApplyLimit` "with their uses" and says the legacy bodies "send unconditionally".
- Between T10 and T11 (start/stop still legacy), each Fleet start then either raises `AttributeError` or sends a paid `set_charge_limit` with no dedupe.
- The original plan named this call explicitly; the slim plan dropped the name.
- **Ruling:** Task 10 deletes lines 926–927. The reconciler owns the limit, and `LIMIT_THEN_START_GAP` replaces the limit-before-start from Task 11. It also deletes the `applyLimit and stopTryingToApplyLimit` skip in `car_api_available` (TeslaAPI.py:517), making `applyLimit` a no-op skip.

### Low

**L1. VCQ internals are pinned by the unchanged legacy test, and the ported tests use API the VCQ lacks.**
- `test_vehicle_command_queue.py` reads `_cond`, `_high`, `_low`, `_busy`, `_draining`, `_thread` (P6), so the generalized queue must keep two OrderedDicts and these names.
- The ported tests use `lane.stop()`, `_peek()`, `_entries()` and `summary()["running"]`.
- **Ruling:** state the internals in Task 6 Interfaces. Add a test-only `_entries()` (high then low) and a `summary()`. Retarget `stop()` uses to `close()` (M6).

**L2. `report()` must ignore one-shots.**
- A debug one-shot (`aspect=None`) reaches `noteOutcome(key, None, …)` → `_checkAspect` → `ValueError`, logged as a raising callback on every debug command.
- **Ruling:** `VehicleReconciler.report` returns early when `attempt.aspect is None`; `Workers._report` has already logged it at INFO.

**L3. NOT_SENT misses some "no request" outcomes.**
- Missing: `wakeOutcome`'s `UNREACHABLE "online check failed"` and runAttempt's own `SATISFIED "read"` and rules outcomes (`beforeWrite` `UNREACHABLE <reason>`, `SATISFIED <reason>`).
- They count as paid requests. That is cost-safe but spends the desire's paid budget, and a rules UNREACHABLE marks BLE failing.
- **Ruling:** add `"online check failed"` and `"read"`. Give rules outcomes a `"rules: "` prefix that `noteOutcome` treats as NOT_SENT.

**L4. Task 14 row 17 ("Any, held limit, car gone") hides a paid path.**
- With Fleet configured, the restore goes paid (no wake) after 300 s of BLE failure, up to 2 calls per desire. "0 → 0" holds only without Fleet.
- **Ruling:** split the row into BLE-only (0 → 0) and BLE + Fleet (Phase 2 measured → ≤ 2).

**L5. Test helpers are under-specified.**
- Task 7 uses `attempt()` and `VIN2`, which are absent from `test_outcome_desired.py`. Task 8 uses `providers_of_every_kind()` and `master()`.
- `ScriptedProvider.worker` is unspecified: it must be derived (`Gen2TWC`/`Gen3TWC` → `local`, `TeslaBLE` → `ble`) or passed, or `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit` routes BLE to cloud.
- **Ruling:** name them in the briefs. `ScriptedProvider.worker` is derived from `name` with a `worker=` override.

**L6. Task 11 `test_mode_2_start_after_our_stop_needs_no_slave` does not remove the slave.**
- `del m.slaveTWCs[...]` leaves the slave in `slaveTWCRoundRobin`, which `getSlaveTWCs()` (and so `Gen2TWCProvider._slaveForKey`) returns. The test would pass without exercising the change.
- **Ruling:** remove it from both.

**L7. Task 13 leftovers.**
- The module list `"Vehicle.VehiclePriority"` (TWCManager.py:85) is not in Files.
- Comments name VehiclePriority in Provider.py, TeslaAPI.py:1296/2397, HomeAssistantProvider.py:51 and VehicleCommandQueue.py; the grep test fails if it covers comments.
- `WebIPCControl.py:321` calls `carapi.getLastStartOrStopChargeTime()`, whose attribute T13 deletes.
- HTTPControl has no VehiclePriority reference.
- **Ruling:** add these to Task 13 Files and define the grep's scope (`lib/` code and comments).

**L8. The Task 13 line check is well-defined but weak.**
- It enforces only removed ≥ added (very likely: ≈3,000 vs ≈1,400). The headline budget (added ≤ 1,400, removed ≥ 3,000) is not checked.
- Desired −250 and Reconciler ~360 look optimistic (§7), so the 450-line tripwire may fire at Task 9.
- **Ruling:** add `exit !(a <= 1400 && d >= 3000)` as a second, report-only line. Set the Task 9 tripwire to 550, or accept a stop-and-report there.

**L9. `lost`/`report` must run outside the queue lock.** The VCQ interface does not say that `lost` and `report` are called after `_cond` is released, as Lanes did (ledger L38).
- **Ruling:** state it in Task 6.

**L10. A raise between `plan()` and `submit` wedges the aspect.** `plan()` sets `rec.inFlight` before `submit`. If `pass_` raises between them, the aspect stays in flight forever.
- **Ruling:** submit each planned attempt in its own `try`. On an exception, clear `inFlight` through a store method (`noteOutcome` with `Outcome(ERROR, "dropped")`).

**L11. A Task 12 test uses the wrong reading source.**
- `test_user_changed_amps_…` reads `chargeCurrentRequest` from `"TeslaMateVehicle"`, which never publishes it (original plan line 1104).
- **Ruling:** use `TeslaAPI` or `FleetTelemetryMQTT`.

**L12. Two notes accepted for this phase.**
- (a) Under a polling reader, a persistently failing paid command is re-sent once per `RETRY` per newer disagreeing reading. That is main's cadence, and Decision 5's "2 per desire" covers blind retries only.
- (b) In mode 2, after two failed paid rates on a stable target, the car keeps its old rate with the TWC at its max until a newer reading. Main stops repeating after about 5.
- **Ruling:** note both in Decisions 5/8 and as a Phase 4 distributor item; no change now.
