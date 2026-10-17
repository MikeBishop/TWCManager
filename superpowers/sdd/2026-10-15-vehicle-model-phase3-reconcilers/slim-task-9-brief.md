### Task 9: Charge-limit rules and the reconciler with the one fallback rule

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Rules.py`, `Reconcile/Reconciler.py`.
- Modify: `Reconcile/Run.py` (drop the placeholder `satisfied`/exclusions).
- Test: `tests/unit/test_charge_limit_rules.py`, `tests/unit/test_limit_reconciler.py`.

**Interfaces:**
- Produces (`Rules.py`): as the original plan's Task 6 states, with `decideChargeLimit` and `needsLiveRead` ported verbatim from `presence/2-charge-limits:lib/TWCManager/ChargeLimitRules.py`. Mappings:
  - `held is None` ⇔ nothing saved;
  - `held.held is None` ⇔ `-1`;
  - `restore` ⇔ `limit == -1`.

  The one addition (ledger L28): `decideChargeLimit` clamps `desired` and `held.outside` to 50–100 before deciding.
- Produces (`Reconciler.py`):
  - Constants: `TICK = 1.0`; `PAID_AFTER = RETRY = {CHARGE_LIMIT: 300.0, CHARGING: 60.0, AMPS: 60.0}` (two names, one table); `RESTORE_RETRY = 3600.0`; `PROBE_AFTER = 600.0`; `READ_MAX_AGE = 300.0`; `LIMIT_THEN_START_GAP = 5.0`; `VEHICLE_SOURCES_EXCLUDED = frozenset({"TWC", "Gen2TWC", "Gen3TWC"})`; `POWER_FLOWING_AMPS = 1.0`.
  - `satisfied(aspect, desired, believed)`, `known(vehicle, aspect)` (with the TWC `actualCurrent` stand-in for `CHARGING` only on a car no vehicle source describes), `handsOff(vehicle, aspect, desired, known)` (start vs "Disconnected"/"NoPower"; and, matching main's `car_api_charge`, a start while `vehicle.value("scheduledChargingPending")` is True and `config["config"].get("respectVehicleSchedule", True)`, for every provider; BLE's own `"scheduled"` check stays; pre-flight H3) and `allowWake(aspect, desired, known)` (raise only; never a restore; start yes; amps yes, but only through a free provider). All as the original plan's Task 6.
  - `newerReading(vehicle, aspect, since) -> bool`: an observation of `FIELD_FOR[aspect]` from a source not in `VEHICLE_SOURCES_EXCLUDED` with `at > since`. For `CHARGING`, while `known` uses the stand-in, a TWC `actualCurrent` observation also counts.
  - `class VehicleReconciler(threading.Thread)`:
    - `__init__(self, master, clock=time.time)`: a daemon named `"VehicleReconciler"`. It registers `desired.onChange(self.wake)` and `master.workers.setReport(self.report)`.
    - `wake(*a)`; `stop()`; `run()` (bounded wait `TICK`; exceptions logged by type name).
    - `pass_(self, now=None) -> int`: snapshot the keys; skip a key the registry no longer holds; plan every aspect, then submit (planning and submitting are kept apart, because local and inline runs report before `submit` returns). Each submit is in its own `try`; on an exception the attempt is cleared through `noteOutcome(..., Outcome(ERROR, "dropped"), ...)` so the aspect never stays in flight (pre-flight L10).
    - `plan(self, vehicle, aspect, now) -> Optional[Attempt]` (algorithm below).
    - `beforeWrite`/`afterWrite`: as the original Task 6, with two changes. `afterWrite` sets `lastStopProvider` on a settled `CHARGING` False (a satisfied lift is cleared in `plan`, not here). Adoption saves `heldLimits.set(vin, outside=value, held=None)`, which rounds floats (ledger L26).
    - `report(self, attempt, outcome)`: returns at once for a one-shot (`attempt.aspect is None`; `Workers._report` already logged it; pre-flight L2). Otherwise it resolves the provider's tier, calls `desired.noteOutcome(..., paid=tier >= TIER_BILLED, freeProvider=tier < TIER_BILLED)`, then `wake()`. It never calls `submit`/`cancel`.
    - `summary(key)`.
  - The one fallback rule. This is the algorithm the signatures do not determine:

```
plan(vehicle, aspect, now):
  d = desired.get(key, aspect); rec = desired.record(key, aspect)
  if d is None or rec.inFlight: return None
  if rec.lastOutcome and isNotSent(rec.lastOutcome) and rec.lastOutcome.detail not in LANE_DETAILS \
     and now - rec.lastOutcomeAt < RETRY[aspect]: return None      # wake held / backoff / wake refused: no resubmit loop (pre-flight H2)
  k = known(vehicle, aspect)
  if aspect == CHARGE_LIMIT and adoptable(vehicle, d, rec):        # vehicle read newer than our write and d.at, disagreeing with our write,
      adopt; return None                                            # trusted (original Task 6 step 3, CHARGE_LIMIT branch only)
  if satisfied(aspect, d.value, k):
      if d.lift: desired.clearIf(key, AMPS, d.value)               # a lift is a one-shot desire
      return None
  if d.restore and nothing held: desired.clear(key, aspect); return None
  if handsOff(vehicle, aspect, d.value, k): log once; return None
  if rec.settledAt and not (newerReading(vehicle, aspect, rec.settledAt) and now - rec.lastSentAt >= RETRY[aspect]):
      return None                                                   # settled without a stamp: wait for a reading (N1)
  cands = order.candidates(vehicle, cap, amps=..., localRule=(aspect == AMPS and not d.lift))
          minus rec.excluded, minus module-less for AMPS, minus NO_INDIVIDUAL_STOP for a stop,
          minus not workers.allows(p, cap, vin, aspect)
  if not cands: debug once; return None
  free = [p for p in cands if tier(p) < TIER_BILLED]; paid = [p for p in cands if tier(p) >= TIER_BILLED]
  ch = desired.free(key)
  freeFailed = (not free) or (ch.failingSince is not None and now - ch.failingSince >= PAID_AFTER[aspect]
                              and now - ch.lastAttemptAt < PROBE_AFTER)      # stale -> the real command over BLE first
  paidAgain = rec.paidAt is None or (now - rec.paidAt >= RETRY[aspect]
              and (rec.paidRetryDue or newerReading(vehicle, aspect, rec.paidAt)))   # one blind retry after a failure
  if paid and freeFailed and paidAgain: p = paid[0]
  elif free and now - rec.lastFreeAt >= (RESTORE_RETRY if d.restore and rec.lastFreeAt else RETRY[aspect]): p = free[0]
  else: return None
  if aspect == CHARGING and d.value is True and (limit attempt in flight or planned this pass
                                                 or now - lastWrite(chargeLimit).at < LIMIT_THEN_START_GAP): return None
  attempt = Attempt(key, aspect, cap, d.value, p.name, wake=allowWake(...) and (p.local or aspect != AMPS)
                    and not (p in paid and rec.paidRetryDue),            # the Q1 blind retry never wakes (pre-flight M8)
                    maxAge=None if aspect == AMPS else READ_MAX_AGE, restore=d.restore, since=now,
                    force=aspect == CHARGE_LIMIT and needsLiveRead(...))
  rec.inFlight = attempt; return attempt
```

- [ ] **Step 1: Write the failing tests.** Port `test_charge_limit_rules.py` (`test_rules`, `test_invariants`, `test_reasons`, `test_needs_live_read`), rows rewritten to `HeldLimit`. Add `test_held_values_are_clamped_to_50_100`. Then, in `test_limit_reconciler.py`, `setup()` is the original's, assigning `m.desired`, then `m.workers = Workers(m, inline=True)`, then `m.reconciler = r = VehicleReconciler(m, clock=c)`, in that order. `runAttempt` resolves its hooks from `m.reconciler`, and the reconciler registers its report on `m.workers`. From Task 10 the master builds defaults in `__init__`; replacing all three in this order must be safe, and the stale default reconciler is never started:

```python
def test_limit_is_sent_once_and_recorded_as_held(): ...                    # 1 call; HeldLimit(90, 50); next pass 0
def test_default_clocks_share_one_domain(): ...                             # real clocks: limit then start gap holds
def test_app_set_limit_is_adopted_and_becomes_outside(): ...                # adopted 80, HeldLimit(80, None), 1 call; decision re-applies
def test_adopted_float_is_saved_as_an_int(): ...                            # observe 80.0 -> heldLimits outside == 80 (int)
def test_a_confirming_read_is_not_adopted_when_desired_changes(): ...
def test_a_read_not_newer_than_our_write_is_reasserted_not_adopted(): ...
def test_no_wake_to_lower_wake_to_raise_never_for_a_restore(): ...
def test_fleet_waits_for_ble_to_time_out_and_is_sent_once():                # Review Focus 1
    ...; c.t += PAID_AFTER[CHARGE_LIMIT] - 1; r.pass_(); assert f.calls == []
    c.t += 1; r.pass_(); assert len(f.calls) == 1
    for _ in range(12): c.t += 300; r.pass_()
    assert len(f.calls) == 1                                                # our stamp settles it: neither BLE nor Fleet again
def test_ble_only_install_keeps_retrying_ble_at_the_retry_cadence():
    ...; for _ in range(4): r.pass_(); c.t += RETRY[CHARGE_LIMIT]
    assert len(b.calls) == 4                                                # no ladder, no give-up
def test_restore_to_an_absent_car_retries_hourly_and_never_wakes():
    ...; assert [x[0] for x in b.calls] == ["setChargeLimit"]; c.t += 3599; r.pass_(); assert len(b.calls) == 1
    c.t += 1; r.pass_(); assert len(b.calls) == 2 and not any(x[0] == "wake" for x in b.calls)
def test_stale_free_failure_gets_the_real_command_over_ble_before_paid():
    ...; m.desired.free(VIN).failure(c() - PROBE_AFTER - 300)               # failing long enough, but untried for > PROBE_AFTER (seed ≠ 0.0; pre-flight M1)
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert cmds(b) == ["setChargeLimit"] and f.calls == []
    r.pass_(); assert len(cmds(f)) == 1                                     # the fresh failure lets paid go at once
def test_a_recent_free_failure_goes_paid_without_a_new_ble_try(): ...
def test_pairing_error_does_not_open_the_paid_window():                     # ledger L52
    ...; ble(O.Outcome(O.ERROR, "pairing")); c.t += 600; r.pass_(); assert f.calls == []
def test_unknown_ble_output_is_a_retryable_failure():                       # ledger L50 (rc 0, unknown output)
    ...; ble(O.Outcome(O.ERROR, "unknown")); r.pass_(); assert m.desired.free(VIN).failingSince == c()
def test_failed_paid_call_retries_once_then_waits_for_a_newer_reading_or_a_new_value():   # Review Focus 2, paid counted
    m, r, v, c = setup(fleet(O.Outcome(O.ERROR, "500"))); f = ...; v.observe("chargeLimit", 90, "TeslaAPI")
    m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); r.pass_(); assert len(f.calls) == 1
    c.t += RETRY[CHARGE_LIMIT] - 1; r.pass_(); assert len(f.calls) == 1                      # not before the gap
    c.t += 1; r.pass_(); assert len(f.calls) == 2                                            # the one blind retry, fails again
    for _ in range(10): c.t += 600; r.pass_()
    assert len(f.calls) == 2                                                                 # exactly 2 paid calls for this desire
    v.observe("chargeLimit", 90, "TeslaAPI"); c.t += 1; r.pass_(); assert len(f.calls) == 3       # a newer reading disagrees
    m.desired.set(VIN, CHARGE_LIMIT, 60, "policy", decision=True); r.pass_(); assert len(f.calls) == 4
def test_a_paid_retry_that_succeeds_is_not_repeated(): ...                    # ERROR then DONE: 2 calls, stamp settles it
def test_a_refused_or_not_sent_paid_outcome_gets_no_blind_retry(): ...       # REFUSED / "wake held": paid calls stay at 1 / 0
def test_a_wake_held_outcome_is_not_counted_as_the_paid_call(): ...
def test_a_not_sent_outcome_is_not_replanned_inside_retry():                # pre-flight H2
    ...; f.outcomes = [O.Outcome(O.UNREACHABLE, "wake held")]                # Fleet-only start; wake scripted to the hold
    for _ in range(10): r.pass_()
    assert [x[0] for x in f.calls] == ["wake"]; c.t += RETRY[CHARGING]; r.pass_(); assert [x[0] for x in f.calls] == ["wake", "wake"]
def test_no_resubmit_loop_during_a_30_minute_wake_hold():                   # pre-flight H2, paid counted
    ...; submitted = 0
    for _ in range(1800): c.t += 1; submitted += r.pass_()
    assert submitted == 30 and [x[0] for x in f.calls] == ["wake"] * 30 and cmds(f) == []      # one per RETRY[CHARGING]; 0 paid requests
def test_paid_retry_never_wakes_and_a_failed_wake_gets_no_blind_retry():  # pre-flight M8, paid counted (user-approved ≤ $0.001 extra)
    ...; f.outcomes = [O.Outcome(O.ERROR, "500")]; m.desired.set(VIN, CHARGE_LIMIT, 80, "policy"); r.pass_()   # a raise: wake + command
    c.t += RETRY[CHARGE_LIMIT]; r.pass_(); assert [x[0] for x in f.calls] == ["wake", "setChargeLimit", "setChargeLimit"]   # retry: no wake
    # second car: the wake itself fails (UNREACHABLE "wake asleep") -> no blind retry at all
    ...; for _ in range(10): c.t += 600; r.pass_()
    assert [x[0] for x in f2.calls] == ["wake"]
def test_a_scheduled_charge_is_left_alone():                                # pre-flight H3
    ...; v.observe("scheduledChargingPending", True, "TeslaAPI"); m.desired.set(VIN, CHARGING, True, "heartbeat")
    assert r.pass_() == 0 and f.calls == []
    m.config["config"]["respectVehicleSchedule"] = False; assert r.pass_() == 1
def test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car(): ...    # Task 8; paid counted
def test_refused_excludes_the_provider_and_unsupported_falls_through(): ...
def test_restore_with_telemetry_showing_a_limit_not_ours_forces_a_live_read(): ...
def test_restore_with_nothing_held_clears_the_desire_and_unknown_limit_on_cloud_reads_first(): ...
def test_a_rules_settled_restore_clears_the_desire_and_does_not_loop(): ...
def test_a_satisfied_outcome_without_a_stamp_is_not_resent_until_new_evidence(): ...   # paid counted
def test_rate_limited_provider_is_skipped_at_plan_time(): ...                         # ledger Task 5 M6 (allows is called)
def test_a_late_report_for_a_replaced_attempt_does_not_clear_a_newer_one(): ...       # ledger L16
def test_pass_is_bounded_and_survives_a_raising_provider(): ...
```

  The `...` bodies follow the original plan's same-named tests, minus the backoff and probe assertions.
- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: Rules`).
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_charge_limit_rules.py tests/unit/test_limit_reconciler.py tests/unit/test_workers.py tests/unit/test_outcome_desired.py -q --timeout=60 -p no:cacheprovider`, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Add the reconciler: ported charge-limit rules, adoption for the limit, and one fallback rule (free first, paid once per desire after the free channel fails for the aspect's window)"`

