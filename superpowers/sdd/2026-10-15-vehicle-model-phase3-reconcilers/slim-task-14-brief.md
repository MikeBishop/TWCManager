### Task 14: Old-vs-new behaviour table with paid-call counts; live check

**Files:**
- Test: `tests/unit/test_command_path_parity.py`.
- Modify: this plan (the table gains a "Measured" column from the passing tests).

**Interfaces:**
- Consumes: real `TWCMaster` (`test_gen2twc_provider.make`); real `TeslaAPI` (`api_with_registry` + `requests_mock` on `/command/`, `/wake_up`, `/vehicle_data`, `/vehicles`); real `TeslaBLE` (`test_teslable_pairing_status.make`, with `sendCommand` patched: `None` = radio down); real `HomeAssistant` (`make_ha`); the real reconciler with `inline(r)` (its queues swapped for test `InlineQueue`s); a real `VehicleReconciler` driven by `pass_()` on a `Clock`.
- Produces: one test per row. Each asserts the provider calls and the paid-request counts (`vehicle_data`, `wake_up`, `/command/`). The "Phase 2" column is measured at 6a6c14e (main's behaviour). Tasks 1–5 interim paths (ledger c3, M5) do not count. No row may show more paid calls than Phase 2 unless the row says why.

| # | Install / setting | Trigger | Phase 2 | Phase 3 slim | Paid 2 → 3 | Test |
|---|---|---|---|---|---|---|
| 1 | Pure Gen2 | heartbeat stop/start | façade, no modules → nothing | desired set, no candidate, DEBUG | 0 → 0 | `test_pure_gen2_sets_desired_and_attempts_nothing` |
| 2 | BLE-only | limit 50 then 40 | BLE to every keyed VIN, wake each time | BLE to present claimed cars; no wake on a lower | 0 → 0 | `test_ble_only_limits_never_wake_to_lower` |
| 3 | Owner-only | limit, stop | nothing | no candidate | 0 → 0 | `test_owner_only_never_commands` |
| 4 | Fleet-only, asleep | limit raise 50→80 | free check, wake, `vehicle_data`, command | same | 3 → 3 | `test_fleet_only_raise_costs_the_same` |
| 5 | BLE + Fleet, radio down | limit | 3 BLE then Fleet at once | Fleet after 300 s, once | 1 → 1 | `test_ble_plus_fleet_waits_five_minutes` |
| 6 | BLE + Fleet, radio down | heartbeat stop | 3 BLE then Fleet at once | Fleet after 60 s, once | 1 → 1 | `test_ble_plus_fleet_stop_waits_a_minute` |
| 7 | TeslaMate + BLE | app sets 80 while we hold 50 | BLE re-sends 50 next policy pass | adopted; outside 80; nothing sent | 0 → 0 | `test_telemetry_limit_change_is_adopted` |
| 8 | BLE + Fleet | app starts a car we stopped | re-stopped by the heartbeat | re-stopped once per newer reading (BLE) | 0 → 0 | `test_app_start_is_overridden_over_ble` |
| 9 | Fleet-only | Fleet 500 on a limit, twice | 2 attempts | 2 (one blind retry after 300 s); next only on a newer reading or new value | 2 → 2 | `test_fleet_failure_is_retried_once` |
| 10 | Fleet + HA | limit, Fleet fails | Fleet, then HA after 60 s | Fleet once; HA never in the same desire unless a newer reading | ≤3 → ≤2 | `test_fleet_then_ha_never_in_one_pass` |
| 11 | Gen3 two units | stop one car | no caller | `NO_INDIVIDUAL_STOP` → BLE/Fleet | 0 → 0 | `test_gen3_stop_routes` |
| 12 | `chargeStopMode` 2 + BLE + Fleet | heartbeat stop | shun at once; re-shun on the heartbeat's 60 s gates | BLE car: BLE then shun at 60 s; keyless car: shun at once; Fleet never. Re-shun of a car with vehicle sources waits for a newer vehicle reading (Question 4) | 0 → 0 | `test_stop_mode_2_ble_then_disruptive` |
| 13 | `chargeRateControl` 3, Fleet-only on a TWC | 4 A then 10 A | Fleet ×2 (low amps), then TWC | same | 2 → 2 | `test_mode_3_fleet_only_below_floor` |
| 14 | `chargeRateControl` 1, Fleet-only on a TWC | plug-in | lift over Fleet once per session | lift once, only if `chargeCurrentRequest` unknown or below | 1 → ≤1 | `test_mode_1_lift_once_per_session` |
| 15 | Fleet, token 401 | limit | 401 counted as success, chosen again | REFUSED; slot cleared | n → 1 | `test_fleet_401_retires` |
| 16 | HA-only, two cars | heartbeat stop for one | HA stops that car | same; `MIN_SEND_GAP` 10 s per car and aspect | 1 → 1 | `test_ha_only_targeted_stop` |
| 17a | BLE-only, held limit, car gone | departure | restore loop 600 s doubling to 1 h | BLE hourly, never a wake | 0 → 0 | `test_vanished_car_restore_is_hourly_and_free` |
| 17b | BLE + Fleet, held limit, car gone | departure | measured at 6a6c14e | BLE hourly; Fleet (no wake) after 300 s of BLE failure, at most 2 per desire (Q1 retry) | measured → ≤ 2 | `test_vanished_car_restore_with_fleet_is_bounded` |
| 18 | Any | SIGTERM with a stop pending | `drain_high_priority(60)` | `reconciler.drain` gets `min(shutdownDeadline - 20, now + 60)` | — | `test_reconciler_queues.py::test_drain_runs_pending_stops_only` |
| 19 | Fleet-only, schedule pending | heartbeat start | skipped (`respectVehicleSchedule`) | skipped (`handsOff`) | 0 → 0 | `test_scheduled_charge_skips_the_start` |
| 20 | Fleet + Fleet Telemetry, Fleet answering 408 | limit lowered on a sleeping car, Telemetry streaming for 1 h | re-sent each policy pass | ≤ 4 commands per desire (one re-arm), ≤ 1 wake | measured → ≤ 4 | `test_streaming_telemetry_with_fleet_408_is_bounded` |

- [ ] **Step 1: Write the failing tests:** one function per row, counting `requests_mock.request_history` by URL fragment. Row 4's script is the original plan's `test_fleet_only_raise_costs_the_same`, with `inline(r)` in place of `m.lanes`.
- [ ] **Step 2: Run to verify failure** → FAIL (`NameError`/`ImportError` for the helpers).
- [ ] **Step 3: Implement the helpers and tests.** Fill the "Measured" column.
- [ ] **Step 4: Run the full suite** → PASS. Record the test count in the ledger.
- [ ] **Step 5: Commit.** `git commit -m "Pin the old-vs-new command behaviour per install type with real objects and paid-call counts"`
- [ ] **Step 6: Live check on `twcmanager`.** It is approved, including the rfkill window, but the user schedules it; the implementer does not run it. When the user gives the go-ahead:
  1. Deploy `vehicle-model/phase3` and restart.
  2. Over at least one policy transition and one plug cycle, confirm:
     - no `Main loop stalled` past boot;
     - a policy limit change gives exactly one `setChargeLimit` via TeslaBLE and no Fleet request;
     - an app-set limit logs `set elsewhere ... adopted` and is not undone;
     - `rfkill block bluetooth` gives BLE `unreachable` outcomes for 5 min, then one Fleet `set_charge_limit`; then `rfkill unblock`;
     - unplug restores the held limit;
     - there are no `wake_up` requests except for raises.
  3. Record the findings in the PR description and roll back per the ledger.

---

## Line budget (lib/ only; tests are not counted; total non-test `lib/**/*.py` lines)

Fixed points: origin/main 23,180; 6a6c14e (Phase 2) 27,483; d98d643 (Tasks 6–9 built) 30,246.

| Task | Expected lib Δ | Running total |
|---|---|---|
| 10 consolidate stack, min send gap, c2/c4 | ≈ −200 | ≈ 30,046 |
| 11 held limits native + limit wiring + vehicle-list loader; legacy limit path deleted | ≈ −450 | ≈ 29,596 |
| 12a charging stateless; legacy charge path and `car_api_available` deleted | ≈ −850 | ≈ 28,746 |
| 12b amps stateless; façade, legacy queue mode, `dispatch` deleted | ≈ −800 | ≈ 27,946 |
| 13a TeslaBLE one retry (+ BLE helpers dead on main) | ≈ −260 | ≈ 27,686 |
| 13b reads through providers | ≈ −150 | ≈ 27,536 |
| 13c one TeslaAPI request helper | ≈ −120 | ≈ 27,416 |
| 13 orphans, dead-on-main, dead declarations and summaries | ≈ −400 | **≈ 27,016** |
| 14 parity tests | 0 | ≈ 26,965 |

- **Projected end of Phase 3: ≈ 27,000** (range 26,800..27,300). That is ≈ 16 % above main and ≈ 500 below Phase 2 (6a6c14e).
- The audit's 26,750 target includes item 1, the CarApiVehicle phase (≈ −300, below). Phase 3 alone lands ≈ 250 above it.
- Every task is net-negative. Task 13 reports actual against expected per task; the target is a target, not something to fit.
- If `Reconciler.py` or `Run.py` passes 600 lines after Task 10, stop and report (the rule is not raised; pre-flight I8).

## Later (not in this phase)

- **Dissolve `CarApiVehicle` into the registry Vehicle** (audit item 1, user-approved). This is its own small phase after Phase 3 and before Phase 5, ≈ −300: the REST reads become TeslaAPI methods taking a VIN, the wake and backoff state folds into the record, and `HaVehicle` shrinks to its entity map.

---

## Ledger carries

| Ledger item | Where it lands / why dropped |
|---|---|
| L16/L38: report clears `inFlight` by identity; records mutated only via store methods; never `submit`/`cancel` under the store lock | Task 7 (`noteOutcome`), Task 9 (`report`), Global Constraints |
| L19: registry removal forgets desired state; `AttemptRecord.exclude(provider, kind)` | Task 10 (`registry.removed = desired.forget`), wired in Task 11; Task 7 keeps `exclude` |
| L21: desired on an anon key dropped at merge, re-set for the VIN | **Dropped**: CHARGING and AMPS are re-set for the VIN on the next cycle, and a limit is never set for an anonymous car |
| L26: adoption saves registry floats via int coercion | Task 9 `test_adopted_float_is_saved_as_an_int` |
| L28: `decideChargeLimit` clamps held values to 50–100 | Task 9 |
| L35: debug route 400 until wiring | Task 11 `test_debug_route_submits_through_the_master_reconciler` |
| L36: report thread; one-shot `aspect=None` in `beforeWrite`; `_chargingLike` signature | Task 9 (`beforeWrite` passes one-shots through); `_chargingLike` deleted in Task 7 |
| L40/L42: Task 3 M2 (rate slot only on send), M4 (monotonic drain), M6 (BaseException) | Task 6 |
| L47 c1, L56 c3, L58 M5: interim legacy dispatch (BLE `setAmps`, paid increase, lost stamp) | Task 13 deletes it; Task 14 measures Phase 2 at 6a6c14e so the interim never counts |
| L50: Gen2 mode-2 start without the slave | Task 12a |
| L50: rc 0 with unknown output = retryable ERROR | Task 9 `test_unknown_ble_output_is_a_retryable_failure` |
| L50: Phase 4 off-serial-thread RS-485 writes (`HTTPControl.py:906`, `TWCManager.py:370`) | **Out of scope**: Phase 4 (threading split) |
| L52: ERROR "pairing" not a free failure | Task 7 `noteOutcome`, Task 9 test |
| L56 c4: `firstChargeNeededTime` reset; `wakeDue` before the first `wakeOutcome` | Reset fixed in Task 5 round 1. **Dropped** for `wakeDue`: the reconciler never calls `wakeDue`; a wake only goes through `wakeOutcome`, which applies the hold |
| L58 M2: a 403 on `wake_up` retires commands | Task 8 (a `wake` purpose) |
| L58 M6: Task 6 must call `allows`; the HA window is per capability | Task 9 (plan-time `allows`); Task 6 (window per aspect) |
| L58 M7: a 403 refusal is account-wide | **Phase 6** (status/UI); cost-safe |
| L60 N2: a long gap restarts the wake grace | **Dropped**: cost-safe (it only delays a wake) |
| Pre-flight S2 (`forced` stops, `policyAmpsRequested`) | **Dropped**: there is no user-start bound left to override |
| Pre-flight S3, N12 (which backoff a new desire resets) | **Dropped**: there is no backoff ladder; a new desire resets `lastFreeAt`/`paidAt` |
| Pre-flight S6, N3 (`offering`, zero-offer hands-off) | Replaced by the heartbeat clearing a pending start at zero offer (Task 12a, Review Focus 3) |
| Pre-flight N1 (unstamped settled outcome re-sent every pass) | Task 9 settled gate; Task 11 disruptive-stop tests |
| Phase 1/2 carries in the original plan's table (layered actuators, `NO_INDIVIDUAL_STOP`, Gen3 G4, Gen2 disruptive stop caller, rate-limit enforcement, `targetAmps`, HA m-2, 09:17 rules, M3/M5, #660 lift, `apiDebugInterface`) | Same landing as the original, renumbered: actuators/lift → Task 12; stops → Task 11; rate limits → Tasks 6/9; `targetAmps` → Task 13; debug → Task 6. One change: final-review M3 (`ChargingPoint.start/stopCharging` uncalled) moves to Phase 4's distributor (Task 11 intro). The Phase 5/6 carries are unchanged |
| Phase 2 "60 s retry for a failed queued `setAmps` (was 600 s)" | **Replaced** by the user's Q1 answer: a failed paid rate gets one retry after `RETRY[AMPS]` (60 s); after that a new value or a newer reading sends it |

## Decisions made in this plan

1. **Workers on the existing queue.** `VehicleCommandQueue` is generalized (`run`, `key`, `isHigh`, `report`, `lost`, `inline`, `MAX_PENDING`) and runs three instances until Task 13: legacy, `ble` and `cloud`. Local providers run inline. Each provider's `worker` attribute decides its queue.
2. **Kept from Task 3.** Read-before-write, wake-first, the own-write stamp, the billed-wake abort, the post-success guard, report-once, the bounded queue, the drain, rate limits and the debug one-shot are all kept. `runAttempt` moves verbatim apart from the slot timing (M2) and the removed probe.
3. **Never-started drain dropped.** A drain on a never-started queue no longer runs stops on the caller's thread; production always starts the workers. The concurrency test for it is dropped.
4. **One fallback rule, per car.** The free channel is one record shared by every aspect. Paid is eligible in two cases:
   - the car has no ready free candidate; or
   - the channel has been failing for at least `PAID_AFTER[aspect]` (300 s limit, 60 s start/stop/amps) and its last free attempt is under `PROBE_AFTER` (600 s) old.

   Otherwise the real command goes over the free provider first. That free try is the user's "BLE ping when stale"; there is no separate probe. Spec-binding reading: "failed within the window" means failing for the whole window, never a single recent failure, which was the 2026-10-11 fall-through (Question 2).
5. **At most one paid request per desire, plus one retry after a failure.** A paid request that actually went out and failed (`ERROR` or `UNREACHABLE`, e.g. HTTP 5xx or a timeout) gets exactly one blind retry after `RETRY[aspect]` (user answer, Q1). Further repeats, and any repeat after a success or a `REFUSED`, happen only when a newer vehicle-sourced reading disagrees or the desire changes, and no sooner than `RETRY[aspect]`. The blind retry never includes a wake, and a failed wake gets no blind retry, so the extra cost is ≤ $0.001 per desire (plus at most one $0.002 read on a Fleet-only car). Outcomes in `NOT_SENT` (wake held, wake refused, API backoff, no token, not listed, online check failed, read-satisfied, rules outcomes, queue losers) are not paid requests, and an aspect whose last outcome was one of them (other than a queue loser) is not re-planned inside `RETRY[aspect]`. Under a polling reader, a persistently failing paid command is re-sent once per `RETRY` per newer disagreeing reading, which is main's cadence (pre-flight L12a). Disruptive stops follow the same rule; for a car no vehicle source describes, the TWC's current is its reading.
6. **Free retry cadence.** Free providers are retried every `RETRY[aspect]`. A restore desire's retries after the first go hourly (`RESTORE_RETRY`), matching the spec's "a vanished car backs off to hourly, never wakes". There is no other backoff or round counting; the reconciler never calls `attempts()`.
7. **A settled outcome waits for a reading.** A settled outcome without a stamp (a disruptive stop, a SATISFIED start/stop) is re-planned only when a newer reading arrives, past `RETRY`. Stamped outcomes are settled by `believed` alone.
8. **Adoption is for `CHARGE_LIMIT` only.** It holds until a `decision=True` set (policy transition, arrival, departure) and saves the outside limit. CHARGING and AMPS are stateless: decided each cycle, sent when `believed` (our stamp, or a newer vehicle reading) disagrees. An app start, stop or amps change is overridden at the next eligible pass, as on main. A start is left alone while the car's own schedule is pending and `respectVehicleSchedule` is on, as on main. A queued attempt whose desire changed or cleared before it ran is withdrawn without a read. In mode 2, after two failed paid rates on a stable target the car keeps its old rate (TWC at max) until a newer reading; main stops after about 5. This goes to Phase 4's distributor (pre-flight L12b).
9. **Zero offer clears a pending start.** The heartbeat clears a pending start when it offers less than the minimum and the car draws nothing. This replaces `offering`: no start or wake is ever planned for a car with nothing to draw.
10. **The lift is a one-shot desire.** It is cleared once satisfied, and `TWCSlave.vehicleRateRaised` stays main's once-per-session flag, so a user's later amps change is not undone after a lift. That matches main.
11. **No `endSession`.** With no bounds or ladder, nothing needs a session reset. `lastStopProvider` persisting across a plug cycle only re-enables a harmless `respondToSlaves = 1`. A stale free-channel failure is retried for free first (Decision 4). `forget` still follows the registry.
12. **Provider tables.** `DECLARATIONS` and `SUPPRESSED` are class tables; `Suppressions` evaluates the active conditions against them. `ready()` stays code. A provider without a table falls back to the locality rule (fails closed). `attempts()` stays until Task 13 deletes it with `dispatch`.
13. **A refused Fleet wake retires wakes only** (`"wake"` purpose), not commands.
14. **The original plan's other decisions stand where nothing here contradicts them:** 1, 2, 4, 5, 6, 7, 9, 13, 14, 15, 16, 17, 18, 20, 21, 22 (lane read as queue), 23, 24, 25, 26, 28, 30, 31, 33, 34 and 35. Decision 27 stands with rate windows keyed by aspect (Task 6). Decisions 3, 8, 10, 11, 12, 19, 29 and 32 are replaced by 1–11 above.

15. **Revision after the dedup audit (2026-10-15).** These replace parts of Decisions 1, 2 and 12 from Task 10 on:
    - The reconciler owns the two queues; `Workers` and the hook lookup go; the runner stays a slim `Run.py` calling the reconciler directly.
    - Callbacks with one subscriber are direct attributes. Test-only queue modes live in the tests.
    - Declared rate limits go; one `MIN_SEND_GAP` (10 s) per car and aspect replaces them.
    - Only a reading that reached the car re-arms a paid send: a live BLE, `vehicle_data` or Fleet Telemetry read (the user's decision), or a changed value, scanned across every source. A live read of the same value now counts too. One re-arm per desire (reached-car, `ride` or charging-reading), so at most 4 paid sends per desire.
    - `MIN_SEND_GAP` is 10 s for the limit and charging and 15 s for amps; Wall Connector edges get a 30 s gap.
    - Unmatched numeric-ID held limits are dropped with a warning after the first non-empty list across all token slots (user).
    - `updateChargeAtHome` loads the vehicle list when it is empty (free).
    - The runner stays its own slimmed module (`Run.py`).
    - A limit that cannot be delivered counts as spent for limit-before-start.
    - Held limits migrate once and the rules work natively on `HeldLimit`.
    - TeslaBLE does one quick retry and no breaker.
    - Reads go through the providers. TeslaAPI has one request helper.
    - Unread summaries and declarations go; Phase 6 re-adds what the tab needs.
    - Gen3 cloud VIN and the headroom solver stay (user).

## Self-review

- **Spec coverage.** Each spec point in "Desired state and reconcilers" has a task:
  - desired per aspect: Tasks 9–12;
  - one attempt in flight: Task 9;
  - lanes split BLE/cloud: Task 6;
  - classified outcomes: Tasks 4–5 and 6;
  - time rules: Task 9;
  - read before write: Task 6;
  - re-assert/adopt/hands-off: Task 9 (adopt for the limit only, by user decision);
  - one shared limit rule (#698): Task 9 `allowWake`;
  - replacements: Tasks 10 and 13;
  - `apiDebugInterface`: Tasks 6/10.

  The spec's fast-aspect session bounds are intentionally not built (user decision 3). Presence and the Vehicles tab remain Phases 5 and 6.
- **Types.** From Task 10, `VehicleReconciler.submit/cancel/start/drain` and `Run.runAttempt(reconciler, attempt)` replace `Workers.*`; `allows` and `followRegistry` are gone (`store.changed`, `registry.removed`). Earlier tasks used `DesiredStore.noteOutcome/clearIf/free`, `FreeChannel.failingSince/lastAttemptAt` and `AttemptRecord.lastFreeAt/paidAt/settledAt/lastSentAt` are used with the same names in Tasks 7, 9, 11 and 12. `Provider.worker` (Task 6) is used by `runAttempt` and `Workers`.
- **Proportion.** The plan carries signatures, test names and key assertions. Bodies appear only for the fallback algorithm (Task 9) and the line check (Task 13). It is under half the original plan's length.
- **Review Focus.** All five lines have a named test in their owning task.

## Questions for the user

All four answered by the user on 2026-10-15: Q1 changed Decision 5; Q2–Q4 confirmed as written.

1. **Answered (2026-10-15): one blind retry after the retry gap (Decision 5).** Under "one paid call per desired change", a Fleet call that fails before reaching the car (HTTP 500, timeout) is not retried until a newer reading disagrees or the value changes. On a Fleet-only car that can mean a limit is not applied until the next poll shows the old value. Default as written: strict. The alternative is one retry after `RETRY[aspect]` for `ERROR`/`UNREACHABLE` outcomes, which costs at most one extra $0.001 per desire.
2. **The paid window.** Decision 4 reads "use paid only if a free attempt failed within the last window" as "the free channel has been failing for the whole window (300 s / 60 s), with a fresh failure". That reading is what prevents the 2026-10-11 immediate fall-through. Please confirm. The other reading, "any free failure in the last 300 s / 60 s", would send Fleet right after the first BLE failure.
3. **Restores to an absent car** retry hourly from the second attempt (Decision 6). Main's schedule is 600 s doubling to an hour. Is the fixed hour acceptable?
4. **Re-shun under `chargeStopMode` 2/3 for a Tesla with vehicle sources.** Main re-shuns on the heartbeat's own 60 s gates. Here a repeat of the disruptive stop waits for a vehicle reading (BLE, Fleet, TeslaMate) newer than the last stop, because the TWC's own current is never evidence for a car a vehicle source describes. That keeps preconditioning from triggering a re-shun. The original plan had the same rule. Default: keep it. The alternative is to count TWC current as evidence for the disruptive stop only.
