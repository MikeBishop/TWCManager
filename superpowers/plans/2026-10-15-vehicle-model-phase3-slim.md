# Vehicle Model Phase 3 (slim): the rest of Desired State and Reconcilers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 3 on the simplified design the user chose on 2026-10-15. The bespoke lanes go back onto the existing vehicle command queue/worker, run as two workers. One fallback rule replaces the backoff and health machinery. Only the charge limit is adopted; charging and amps are stateless. Provider declarations become data. Then the legacy command paths are deleted.

**Architecture:** Tasks 1–5 of `.superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md` stand as built on `vehicle-model/phase3` at 39d7cfb. They provide `Reconcile/Outcome.py`, `Desired.py`, `HeldLimits.py`, `Lanes.py`, the provider outcome methods, `Vehicle.believed/latestFrom/read(sources=, force=)` and `tests/unit/gen2_helpers.drive`.
- Tasks 6–8 rework that base. `VehicleCommandQueue` is generalized and runs as a BLE worker and a cloud worker (`Reconcile/Run.py` replaces `Lanes.py`). `DesiredStore` shrinks to desired values, a small attempt record and one free-channel record per car. Providers declare capabilities, costs and suppressions in class tables.
- Tasks 9–12 add the reconciler and move each decision-maker onto desired state. The limit goes first, then charging, then amps.
- Task 13 deletes the legacy paths. Task 14 pins old-vs-new behaviour and schedules the live check.

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `threading`, `requests_mock`, `pytest` (`tests/unit`).

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (sections "Desired state and reconcilers", "Order, policy and suppressions", "Providers and capabilities", "Fields and reads", "Threading"). The user's 2026-10-15 simplification decisions (ledger line 62) override the spec where they conflict: no fast-aspect session bounds, and no adoption of charging or amps.

**Ledger:** `.superpowers/sdd/2026-10-15-vehicle-model-phase3-reconcilers/progress.md`. Every carry is placed or dropped under "Ledger carries" below.

**Branch:** continue `vehicle-model/phase3` from its current head (39d7cfb or later; record the SHA in the ledger as `Task 6: BASE`). The worktree is `scratchpad/wt-vm3`.

## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <paths> -q --timeout=60 -p no:cacheprovider`
  The full suite is `<paths>` = `tests --ignore=tests/API --ignore=tests/integration`. It must pass after every task.
- **Cost.** Fleet prices: commands $0.001, `vehicle_data` $0.002, wake $0.02; `vehicles/{vin}` and `live_status` are free.
  - A paid provider (tier `TIER_BILLED`) or a disruptive one (`TIER_DISRUPTIVE`) is attempted only in two cases: the car has no ready free candidate, or the car's free channel has failed for the aspect's window (the one fallback rule, Task 9).
  - A Fleet wake comes only after the free `vehicles/{vin}` online check, and only for a limit raise or a charge start. A restore never wakes, a stop never wakes, and amps wake only through a free provider.
  - No new paid path. Every task that can reach TeslaAPI or HomeAssistant has a test that counts `requests_mock` calls per URL, or `ScriptedProvider.calls` for a billed scripted provider.
- **Wiring.** Configured limits are the 80 % continuous derating. A brief excursion is fine if the next allocation cycle rebalances; sustained overshoot is a bug. An idle Gen2 TWC is offered 0, which it treats as its hardware minimum; that minimum is never counted against the budget. `minAmpsPerTWC` governs allocation only. Layered actuators hold the TWC at its floor, not its max, when the car carries a sub-floor target.
- **Threading.**
  - No RS-485 I/O off the serial thread: a Gen2 stop or target is published (`stopRequested`, `_evseTargetAmps`) and `send_master_heartbeat` sends it.
  - Vehicle I/O runs only on the BLE worker or the cloud worker. Local providers (Gen2TWC, Gen3TWC) do no I/O and run inline on the reconciler thread.
  - One clock domain: every stamp in `Reconcile/` is `time.time()`, the registry's clock. `time.monotonic` is used only for durations: the rate-limit windows and the drain deadline.
  - Locks are leaves with no I/O under them. Order: `TeslaBLE._bleLock` → `master.settingsLock` → `VehicleRegistry._lock` → `Vehicle._lock` → `DesiredStore._lock`. Nothing calls `Workers.submit`/`cancel` while holding `DesiredStore._lock`; losers report on the caller's thread (ledger L38).
  - Everything is bounded: each worker holds at most `VehicleCommandQueue.MAX_PENDING = 64` entries; the reconciler runs one pass per wake over a snapshot, with a 1 s bounded wait.
- **Stops under `chargeStopMode` 2/3:** the disruptive stop waits 60 s for BLE only when TeslaBLE is ready for that car. Otherwise it goes at once. Billed stops are suppressed in those modes.
- **No regression** for pure-Gen2, BLE-only, Owner/Fleet, TeslaMate, HomeAssistant and Gen3 installs. `commandPolicy`, `chargeRateControl` 1/2/3, `chargeStopMode` 1/2/3, `providerSuppressions` and `heldLimits` keep working. New keys are optional.
- **Logging** never carries a token, a response body or a BLE key; exceptions are logged by type name.
- Python 3.8 syntax; `black` only on files you touched. Commit trailer per the session's attribution reminder.
- Cross-module tests use real objects. Use the `make()` masters, `TeslaAPI` with `requests_mock`, `TeslaBLE` with tesla-control patched, and real workers with `inline=True`. Never use a mock that returns a success value the real method never returns.

## Review Focus

1. Bluetooth down on a BLE+Fleet install: no Fleet command inside 300 s (limit) or 60 s (start/stop), then exactly one. BLE keeps being retried at its cadence and never causes a second Fleet call for the same desire. Tests: Task 9 `test_fleet_waits_for_ble_to_time_out_and_is_sent_once`, Task 12a `test_stop_falls_to_fleet_after_60s_once`.
2. A Fleet call that fails (HTTP 500) is retried exactly once after the retry gap; a second failure is not repeated until a newer vehicle reading disagrees or the desired value changes (2 paid calls per desire at most, blind). Paid calls are counted. Test: Task 9 `test_failed_paid_call_retries_once_then_waits_for_a_newer_reading_or_a_new_value`.
3. Track Green Energy drops the offer to 0 while the car is stopped: no start and no wake, Fleet or BLE, until the offer returns. Test: Task 12a `test_zero_offer_clears_a_pending_start_and_sends_no_wake`.
4. Preconditioning: the TWC reports 10 A while desired charging is False and the car's last vehicle read says "Stopped": no re-stop and no attempt. Test: Task 12a `test_twc_current_alone_never_restops_a_car_with_vehicle_reads`.
5. SIGTERM with a stop pending on the cloud worker and a limit pending on the BLE worker: the stop is delivered, the limit is dropped and reported, and exit is not held past the timeout. Tests: Task 6 `test_drain_runs_pending_stops_only`, `test_drain_is_not_held_past_its_timeout_by_a_hung_attempt`.

---

## File structure

- Created:
  - `lib/TWCManager/Vehicle/Reconcile/Run.py`: `runAttempt`, `RateLimits`, `Workers`.
  - `Reconcile/Rules.py`: the ported charge-limit rules.
  - `Reconcile/Reconciler.py`: `VehicleReconciler`.
  - `Reconcile/Targets.py`: present vehicles and the policy, arrival and departure hooks.
  - Tests: `tests/unit/test_workers.py` (from `test_lanes.py`), `test_provider_tables.py`, `test_charge_limit_rules.py` (ported), `test_limit_reconciler.py`, `test_limit_wiring.py`, `test_charging_reconciler.py`, `test_amps_reconciler.py`, `test_command_path_parity.py`, `test_no_legacy_command_paths.py`.
- Deleted:
  - Task 6: `Reconcile/Lanes.py`. Task 13b: `Registry/ReadSource.py`, `Registry/Sources.py`.
  - Task 12b: `Vehicle/VehiclePriority.py`, `tests/unit/test_vehicle_command_queue.py`, `tests/unit/test_vehicle_priority.py`, `test_vehicle_priority_returns.py`, `test_targeted_charge_limit.py`, `test_teslaapi_charge_vin.py`, `test_teslaapi_chargerate.py`, `test_own_write_stamps.py`. Their still-valid assertions move as Task 13 lists.
- Modified: named per task.

---

### Task 6: Run attempts on the vehicle command queue: two workers, BLE and cloud

`Lanes.py` (674 lines) re-implements what `VehicleCommandQueue` already does: a keyed, coalescing queue with stops first, a worker thread and a drain at shutdown. The queue still serves the legacy `charge`/`applyChargeLimit`/`setChargeRate` path until Task 13. So it is generalized, not repurposed: one legacy instance plus two attempt instances, `ble` and `cloud`. `runAttempt` moves almost verbatim from `Lanes.py` into `Run.py`. The non-waking BLE probe is removed (user decision 2: no separate probe).

**Files:**
- Modify: `lib/TWCManager/VehicleCommandQueue.py`.
- Create: `lib/TWCManager/Vehicle/Reconcile/Run.py`.
- Delete: `lib/TWCManager/Vehicle/Reconcile/Lanes.py`.
- Modify: `Vehicle/Providers/Provider.py` (`worker` attribute; delete `PROBE` and `probe`), `TeslaBLEProvider.py` (`worker = "ble"`; delete `probe`), `Gen2TWCProvider.py`/`Gen3TWCProvider.py` (`worker = "local"`), `Vehicle/TeslaBLE.py` (delete `probe` and the `noteProof` parameter), `Providers/Order.py` (`debugCommand` submits to `master.workers`).
- Test: `git mv tests/unit/test_lanes.py tests/unit/test_workers.py` and adapt. Update `tests/unit/test_provider_outcomes_local.py` (pre-flight M3):
  - delete `test_ble_probe_is_one_non_waking_body_controller_query_that_proves_nothing`;
  - drop the `probe` assertions from `test_a_failing_command_or_probe_logs_no_raw_output_at_info_or_above`, `test_key_refusal_inside_the_pairing_window_is_a_retryable_error_and_keeps_the_claim` and `test_key_refusal_outside_the_pairing_window_is_refused_and_drops_the_claim`;
  - replace `test_an_answered_probe_closes_an_open_circuit_breaker` with `test_an_open_breaker_half_opens_after_recovery_and_a_successful_command_closes_it`.

  Also update `test_provider_order.py`, `test_registry_callers.py`, `test_carapivehicle_registry.py` (`master.lanes` → `master.workers`), `reconcile_helpers.py` (`ScriptedProvider.worker` is derived from `name` — `Gen2TWC`/`Gen3TWC` → `local`, `TeslaBLE` → `ble`, else `cloud` — with a `worker=` override; `probe` goes; pre-flight L5). `test_vehicle_command_queue.py` must pass unchanged.

**Interfaces:**
- Produces (`VehicleCommandQueue`):
  - `MAX_PENDING = 64`.
  - `__init__(self, resolve_module=None, *, name="VehicleCommandQueue", run=None, key=None, isHigh=None, report=None, lost=None, inline=False)`. With `run=None` the legacy `_DISPATCH` path is used, along with the legacy `_key`/`_is_high_priority`.
  - `put(self, entry, callback=None) -> bool`:
    - A pending entry with the same key is replaced and goes to `lost(old, "replaced")`.
    - High entries go first.
    - At `MAX_PENDING` the oldest non-high entry is dropped (`lost(e, "dropped")`), with one WARNING per backlog. A queue full of high entries rejects the newcomer (`lost(new, "dropped")`, returns False).
    - While draining, a non-high entry is rejected as `dropped`.
    - `inline=True` runs the entry on the caller's thread and reports before returning.
  - After a run: the legacy `callback(result)`, then `report(entry, result)`.
  - `remove(self, match: Callable[[Any], bool]) -> int`: removes matching pending entries (never the running one), each to `lost(e, "cancelled")`. The legacy `cancel(cmd, match)` becomes `remove(lambda t: t["cmd"] == cmd and match(t))` until Task 13.
  - `close(self) -> None`: sets draining and drops every pending non-high entry (`lost(e, "dropped")`, one INFO with the count).
  - `waitDrained(self, deadline) -> bool`: waits on a `time.monotonic` deadline for the high entries and the running one (ledger M4).
  - `drain_high_priority(self, timeout) -> bool` is `close()` then `waitDrained(monotonic() + timeout)` (pre-flight M6). The legacy test keeps passing. On timeout the remaining high entries go to `lost(e, "dropped")` when `lost` is set (the legacy instance keeps them, so `test_drain_times_out` is unchanged). On a queue whose thread never started (startup died first), it drops everything through `lost` and returns False at once, without waiting.
  - `pending() -> int`; `busy -> bool`; a test-only `_entries()` (high then low) and `summary()` (pending, busy, running, started, closed). The ported tests' `lane.stop()` becomes `close()` (pre-flight L1).
  - Internals stay as `test_vehicle_command_queue.py` reads them: `_cond`, `_high`/`_low` (two OrderedDicts), `_busy`, `_draining`, `_thread` (pre-flight L1).
  - `report`, `lost` and `callback` are always called after `_cond` is released (ledger L38, pre-flight L9).
  - The worker loop clears `busy` and reports on `BaseException` (ledger M6).
  - Every entry the attempt instances accept is reported exactly once, through `report` or `lost`. With `lost=None` (the legacy instance), losers stay silent as today (`test_replaced_callback_not_called`).
- Produces (`Provider`): `worker: str = "cloud"`. TeslaBLE is `"ble"`; Gen2TWC and Gen3TWC are `"local"`. `commandMethod(capability)` stays.
- Produces (`Run.py`):
  - `entryKey(attempt) -> tuple`: `(key, aspect)` for an aspect attempt, or `(key, "debug", n)` with a fresh `n` for a one-shot (`aspect is None`).
  - `isStop(attempt) -> bool` (`capability == STOP_CHARGING`).
  - `writtenValue(aspect, value)`: `"Charging"`/`"Stopped"` for `CHARGING`, else the value.
  - `checked(provider, method, result) -> Outcome`: a non-`Outcome` result becomes `Outcome(ERROR, "bad return <type>")`, with a WARNING once per `(provider, method)`.
  - `class RateLimits`:
    - `allows(self, provider, capability, vin, aspect=None) -> bool` and `note(self, provider, capability, vin, aspect=None) -> None`.
    - The window key is `(provider.name, aspect or capability, vin)`, so HA's start and stop share one `CHARGING` window (ledger Task 5 M6). Windows use `time.monotonic`, are pruned on `note`, and live under a leaf lock.
  - `runAttempt(master, attempt, rateLimits) -> Outcome` keeps the `Lanes.runAttempt` contract with three changes:
    - Read-before-write uses the sources whose provider shares the attempt provider's `worker`. A read source whose provider name is not registered counts as `"cloud"`.
    - `rateLimits.note(...)` runs only immediately before the provider's command method (ledger Task 3 M2: a read-satisfied or rules-settled attempt uses no slot).
    - There is no probe branch.
    - **Stale-desire guard** (pre-flight M7). At the top, before any read, for an aspect attempt that is not a stop, when `isinstance(getattr(master, "desired", None), DesiredStore)`: if `master.desired.get(key, aspect)` is None or its value ≠ `attempt.value`, return `Outcome(ERROR, "cancelled")`, a lane loser with no read and no request. Mock masters skip the guard.
    - **Wake failures are tagged** (pre-flight M8). A failed wake's outcome is returned with its detail prefixed `"wake "` (e.g. `"wake asleep"`); `"wake held"` and `"wake refused"` already carry it.
    - **Rules outcomes are tagged** (pre-flight L3). An early outcome from `beforeWrite` gets a `"rules: "` detail prefix; the read-satisfied outcome keeps detail `"read"`.
    The Task 3 guarantees stay: a REFUSED or failed wake on a non-local provider aborts the billed command (I2); a stamp or `afterWrite` that raises after the command ran never changes its outcome (I1); a disruptive stop and a SATISFIED start/stop are not stamped. Hooks come from `master.reconciler` when it is a `VehicleReconciler` (lazy import; a missing `Reconciler` module falls back to the placeholders, any other import error propagates).
  - `class Workers`:
    - `__init__(self, master, report=None, inline=False)` builds `self.ble` and `self.cloud` as `VehicleCommandQueue(name="Vehicle-ble"|"Vehicle-cloud", run=lambda a: runAttempt(master, a, self.rateLimits), key=entryKey, isHigh=isStop, report=self._report, lost=lambda a, d: self._report(a, Outcome(ERROR, d)), inline=inline)`, plus `self.rateLimits = RateLimits()`.
    - `_report` logs one-shots at INFO (`Debug <capability> for <vin> via <provider>: <kind> <detail>`), then calls the callback. A raising callback is logged by type name.
    - `setReport(cb)`.
    - `submit(self, attempt) -> bool`: a `"local"` provider runs `runAttempt` inline and reports; `"ble"`/`"cloud"` go through `put`.
    - `cancel(self, key) -> int`: removes pending stops for `key` on both queues.
    - `allows(provider, capability, vin, aspect=None)`.
    - `start()`.
    - `drain(self, timeout) -> bool`: `close()` on both queues first, then `waitDrained` on one shared monotonic deadline, cloud then BLE (pre-flight M6).
    - `pending() -> int`; `summary() -> dict`.
- Produces (`Order.debugCommand`): unchanged, except that it submits to `master.workers` (`False` when absent).

- [ ] **Step 1: Write the failing tests.** In `test_workers.py`, `setup()` builds `m.workers = Workers(m, report=..., inline=inline)`. Keep these tests with their assertions retargeted from `Lane`/`Lanes` to `VehicleCommandQueue`/`Workers`:
  - `test_inline_lane_runs_reports_and_stamps_the_write`
  - `test_bad_return_and_exception_become_error_outcomes_without_a_stamp`
  - `test_wake_first_refused_aborts_and_a_failed_local_wake_still_sends`
  - `test_read_before_write_satisfied_skips_the_command`
  - `test_disruptive_stop_and_satisfied_start_are_not_stamped`
  - `test_queue_coalesces_per_key_aspect_stops_first_and_is_bounded_and_reports_the_losers`
  - `test_cancel_removes_only_stops_and_reports_them`
  - `test_drain_runs_pending_stops_only` (start the queue and gate its worker with a blocking first attempt, as `test_drain_on_a_started_lane_lets_its_thread_run_the_pending_stop` does; then submit the limit and the stop, then drain; pre-flight M6)
  - `test_debug_command_submits_a_one_shot_past_a_twc`
  - `test_started_lane_runs_on_its_own_thread_and_drain_joins_it`
  - `test_drain_is_not_held_past_its_timeout_by_a_hung_attempt`
  - `test_drain_on_a_started_lane_lets_its_thread_run_the_pending_stop`
  - `test_replaced_and_dropped_report_the_losing_attempt_object`
  - `test_overflow_warns_once_and_a_full_lane_of_stops_rejects_the_newcomer`
  - `test_cancel_leaves_a_running_stop_alone`
  - `test_a_raising_report_is_logged_by_type_name`
  - `test_errors_log_type_names_only_and_warn_once`
  - `test_read_before_write_uses_only_the_lane_s_own_sources`
  - `test_satisfied_limit_from_the_provider_is_stamped_and_no_vehicle_is_an_error`
  - `test_one_shot_outcome_is_logged_at_info`
  - `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit` (both workers gated as above, so the BLE limit is still pending when `drain` closes both)
  - `test_a_raising_after_write_keeps_the_sent_command_done`
  - `test_a_raising_after_write_hook_keeps_the_sent_command_done`
  - `test_a_failed_billed_wake_never_sends_the_billed_command`
  - `test_an_inline_lane_is_busy_while_it_runs`

  Delete these, which test removed design: `test_probe_and_one_shot_do_not_replace_each_other`, `test_probe_runs_alone_without_read_wake_or_stamp`, `test_concurrent_drains_of_a_never_started_lane_share_one_runner`. Rename `test_lane_membership_and_unknown_provider_goes_to_cloud` → `test_worker_follows_the_provider_s_worker_attribute` and `test_local_lane_is_always_inline` → `test_local_providers_run_inline_even_when_workers_are_threaded`. Add:

```python
def test_rate_slot_is_used_only_when_a_command_is_sent(monkeypatch):      # ledger Task 3 M2
    # a scripted Fleet table with SET_CHARGE_LIMIT RateLimit(2, 60); chargeCurrentRequest is not a field until Task 12 (pre-flight M2)
    ...; assert m.workers.allows(p, C.SET_CHARGE_LIMIT, VIN, CHARGE_LIMIT) and p.calls == []

def test_an_attempt_whose_desire_changed_is_cancelled_before_any_read():   # pre-flight M7
    ...; m.desired.clearIf(VIN, CHARGING, True); release_worker()
    assert reports[-1][2] == "cancelled" and f.calls == [] and reads == 0

def test_a_failed_wake_is_tagged():                                         # pre-flight M8
    ...; assert reports[-1][1:] == (O.UNREACHABLE, "wake asleep")

def test_ha_start_and_stop_share_one_window_per_car(monkeypatch):           # ledger Task 5 M6
    ...; m.workers.submit(stop); assert not m.workers.allows(ha, C.START_CHARGING, VIN, CHARGING)
    assert m.workers.allows(ha, C.START_CHARGING, VIN2, CHARGING)

def test_one_shots_never_replace_each_other():
    ...; q.put(one_shot(C.WAKE)); q.put(one_shot(C.WAKE)); assert q.pending() == 2

def test_base_exception_in_a_run_still_reports_and_clears_busy():            # ledger Task 3 M6
    ...; assert reports[-1][1] == O.ERROR and not q.busy
```

- [ ] **Step 2: Run to verify failure.** `$PYTEST tests/unit/test_workers.py ...` → FAIL with `ModuleNotFoundError: TWCManager.Vehicle.Reconcile.Run`.
- [ ] **Step 3: Implement** per Interfaces. Delete `Lanes.py`, `PROBE`, `Provider.probe`, `TeslaBLEProvider.probe`, `TeslaBLE.probe` and `noteProof`.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_workers.py tests/unit/test_vehicle_command_queue.py tests/unit/test_provider_order.py tests/unit/test_registry_callers.py tests/unit/test_carapivehicle_registry.py tests/unit/test_provider_outcomes_local.py tests/unit/test_provider_outcomes_cloud.py tests/unit/test_teslable_provider.py tests/unit/test_sigterm_shutdown.py -q --timeout=60 -p no:cacheprovider` → PASS, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Run vehicle attempts on the command queue as two workers, BLE and cloud; drop the separate lanes and the BLE probe"`

### Task 7: Slim the desired-state store

Under the user's decisions the store needs:
- desired values, with adoption for `CHARGE_LIMIT` only;
- a small per-aspect attempt record;
- one free-channel record per car;
- `lastStopProvider`.

Session bounds, per-provider channel health, the backoff ladder, the probe slot, `offering` and the charging adoption logic go.

**Files:**
- Modify: `lib/TWCManager/Vehicle/Reconcile/Desired.py`, `Reconcile/__init__.py`, `Reconcile/Outcome.py` (add `NOT_SENT`).
- Test: rewrite `tests/unit/test_outcome_desired.py`.

**Interfaces:**
- Produces (`Outcome.py`): `NOT_SENT = LANE_DETAILS | {"backoff", "wake held", "wake refused", "no command token", "not listed", "online check failed", "read"}`, plus any detail starting `"rules: "` (`isNotSent(outcome) -> bool` covers both; pre-flight L3). An outcome with one of these details made no request, so it is neither a paid call nor a sent command.
- Produces (`Desired.py`). Aspects, `FIELD_FOR`, `CAPABILITY_FOR` and `Attempt` are unchanged. `Desired(value, by, at, adopted=False, restore=False, lift=False)` (`forced` is gone).
- `class AttemptRecord`:
  - `inFlight`, `lastOutcome`, `lastOutcomeAt`, `lastProvider` as now.
  - `excluded: Dict[str, str]` (provider → kind).
  - `lastSentAt: float = 0` (any provider) and `lastFreeAt: float = 0` (a free provider).
  - `paidAt: Optional[float]`: the paid or disruptive request for the current desire.
  - `paidRetryDue: bool = False`: the last paid request failed (`ERROR`/`UNREACHABLE`, detail not in `NOT_SENT`) and its one blind retry is unused.
  - `settledAt: Optional[float]`.
  - `pendingSave: Any`.
  - `newDesire()`: drops UNSUPPORTED exclusions and keeps REFUSED ones (ledger L17 ruling); resets `lastFreeAt`, `paidAt`, `paidRetryDue` and `settledAt`.
  - `exclude(provider, kind)`; `summary()`.
- `class FreeChannel` (one per car, shared by every aspect; replaces `ChannelHealth`):
  - `failingSince: Optional[float]` and `lastAttemptAt: float = 0`.
  - `success(at)` sets `lastAttemptAt` and clears `failingSince`.
  - `failure(at)`: `if failingSince is None: failingSince = at`; `lastAttemptAt = at` (never `or`: a 0.0 stamp is a valid time; pre-flight M1).
  - `summary()`.
- `class ControlState`: `desired`, `records`, `free: FreeChannel`, `lastStopProvider: Optional[str]`.
- `class DesiredStore`:
  - Kept as is: `__init__(clock=time.time)`; `get`; `clear`; `decision`; `forget`; `followRegistry`; `record`; `state`; `peek`; `settled`; `keys`; `onChange`; `summary`.
  - `set(key, aspect, value, by, decision=False, restore=False, lift=False) -> bool`: an adopted desire holds unless `decision`; an unchanged value is a no-op.
  - `clearIf(key, aspect, value) -> bool`: clears when the desired value equals `value`. It replaces `release`.
  - `adopt(key, aspect, value)`: `CHARGE_LIMIT` only (`ValueError` otherwise). It sets `Desired(value, "user", now, adopted=True)`.
  - `free(key) -> FreeChannel`.
  - `noteOutcome(self, key, aspect, attempt, outcome, now, paid: bool, freeProvider: bool) -> bool` is the only mutation of a record after submit, under the lock (ledger L16). It returns False and changes nothing when `record.inFlight is not attempt`. Otherwise:
    - `inFlight = None`.
    - Detail in `LANE_DETAILS`: stop here (the attempt never ran).
    - `lastOutcome/At/Provider`.
    - Not `isNotSent(outcome)`: `lastSentAt = now`; `lastFreeAt = now` when `freeProvider`; when `paid`: `paidRetryDue = (paidAt is None and kind in RETRYABLE and not detail.startswith("wake "))`, evaluated before `paidAt = now` (a failed wake gets no blind retry; pre-flight M8). It is True only after the desire's first paid request failed, and False after the retry's outcome, whatever that is.
    - `SETTLED`: `settledAt = now`; `free.success(now)` when `freeProvider`.
    - `RETRYABLE` with detail ≠ `"pairing"` (ledger L52), or `REFUSED`, on a free provider: `free.failure(now)`.
    - `EXCLUDING`: `exclude(provider, kind)`.
- Removed: `SessionBounds`, `ChannelHealth`, `bounds()`, `health()`, `release`, `endSession`, `noteOffering`, `probeInFlight`, `offering`/`offeringSince`, `_chargingLike`/`_stoppedLike`/`CHARGING_LIKE`/`STOPPED_LIKE`, and the record's `tried/paid/backoff/backoffUntil/notBefore/newRound`.

- [ ] **Step 1: Write the failing tests.**
  - Keep, adjusted: `test_outcome_vocabulary` (plus `"wake held" in O.NOT_SENT`), `test_set_get_clear_and_change_signal`, `test_default_clock_is_wall_time`, `test_adopted_slow_aspect_holds_until_a_decision`, `test_a_by_only_change_is_a_no_op`, `test_a_decision_on_the_adopted_value_takes_it_over_in_place`, `test_a_raising_change_callback_is_dropped_and_others_still_run`, `test_scripted_provider_and_order_helpers`, `test_forget_drops_every_trace_of_a_key`, `test_registry_removals_forget_desired_state`, `test_a_new_desire_drops_unsupported_exclusions_and_keeps_refused`.
  - Delete the bounds, health, round, offering and broken-reconciler tests.
  - Add:

```python
def test_adopt_is_for_the_charge_limit_only():
    s = DesiredStore(); s.adopt(VIN, CHARGE_LIMIT, 80); assert s.get(VIN, CHARGE_LIMIT).adopted
    with pytest.raises(ValueError): s.adopt(VIN, CHARGING, "Charging")

def test_clear_if_drops_only_a_matching_value():
    s = DesiredStore(); s.set(VIN, CHARGING, True, "heartbeat")
    assert s.clearIf(VIN, CHARGING, False) is False and s.clearIf(VIN, CHARGING, True) is True and s.get(VIN, CHARGING) is None

def test_free_channel_is_per_car_and_shared_by_aspects():
    s = DesiredStore(); f = s.free(VIN); f.failure(0.0); f.failure(70.0)
    assert (f.failingSince, f.lastAttemptAt) == (0.0, 70.0) and s.free(VIN) is f and s.free(VIN2) is not f
    f.success(80.0); assert f.failingSince is None and f.lastAttemptAt == 80.0

def test_note_outcome_bookkeeping():
    c = Clock(); s = DesiredStore(clock=c); s.set(VIN, CHARGE_LIMIT, 50, "policy"); r = s.record(VIN, CHARGE_LIMIT)
    a = attempt("FleetAPI"); r.inFlight = a
    assert s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.ERROR, "500"), 100.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0 and r.lastSentAt == 100.0 and r.inFlight is None and s.free(VIN).failingSince is None
    b = attempt("TeslaBLE"); r.inFlight = b
    s.noteOutcome(VIN, CHARGE_LIMIT, b, O.Outcome(O.ERROR, "pairing"), 110.0, paid=False, freeProvider=True)
    assert s.free(VIN).failingSince is None and r.lastFreeAt == 110.0                        # pairing window: not a failure
    r.inFlight = b; s.noteOutcome(VIN, CHARGE_LIMIT, b, O.Outcome(O.UNREACHABLE, "no reply"), 120.0, paid=False, freeProvider=True)
    assert s.free(VIN).failingSince == 120.0
    assert s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.DONE), 130.0, paid=True, freeProvider=False) is False   # stale report
    r.inFlight = a; s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.UNREACHABLE, "wake held"), 140.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0                                                                  # nothing was sent
    r.inFlight = a; s.noteOutcome(VIN, CHARGE_LIMIT, a, O.Outcome(O.UNREACHABLE, "rules: limit unknown"), 150.0, paid=True, freeProvider=False)
    assert r.paidAt == 100.0                                                                  # rules outcome: no request
```

  The helpers `attempt(provider, aspect=CHARGE_LIMIT)` and `VIN2` are defined at the top of `test_outcome_desired.py` (pre-flight L5); add `test_a_failed_paid_wake_sets_no_retry` (`UNREACHABLE "wake asleep"` → `paidRetryDue` False).

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: clearIf`).
- [ ] **Step 3: Implement** per Interfaces. Fix the importers: `Gen2TWCProvider.ready` still reads `peek(key).lastStopProvider`.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_outcome_desired.py tests/unit/test_workers.py tests/unit/test_provider_outcomes_local.py -q --timeout=60 -p no:cacheprovider`, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Slim the desired-state store: charge-limit adoption only, one free-channel record per car, no session bounds or backoff ladder"`

### Task 8: Provider declarations as data

**Files:**
- Modify: `Vehicle/Providers/Provider.py`, `Suppressions.py`, `Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `TelemetryProvider.py`, `Vehicle/TeslaAPI.py` (`wakeOutcome` and the `wake_up` 403), `Vehicle/TeslaTokenSlot.py` (`RETIRED_ON_REFUSAL` gains `"wake"`; `SCOPES["wake"] = ("vehicle_charging_cmds", "vehicle_cmds")` and `SCOPE_LABELS["wake"] = "waking the car"`, without which `usable("wake")` raises `KeyError`; pre-flight M4).
- Test: `tests/unit/test_provider_tables.py`. Adjust the suppression doubles: `test_provider_order.py:66–77`, `test_vehicle_priority.py:43–51`, `test_provider_outcomes_local.py:49` (a `Mock(local=False)` provider; pre-flight M5).

**Interfaces:**
- Produces (`Provider`):
  - `DECLARATIONS: Dict[str, Declaration] = {}`; `declarations()` returns `self.DECLARATIONS`. Each provider's table equals its current `declarations()` output: Gen2, Gen3, TeslaBLE, Owner, Fleet, HA, telemetry.
  - `SUPPRESSED: Optional[Dict[str, FrozenSet[str]]] = None`: condition → capabilities. A provider with no table (`None`, including test doubles and `Mock`s) falls back to the locality rule: `CLOUD_SUPPRESSED` when `not provider.local`, else `{}` (`suppressedFor(provider, condition)` helper; fails closed, as today; pre-flight M5). Conditions are `"ble_only"`, `"api_only"` and `"localStops"` (`chargeStopMode` 2/3).
  - `CLOUD_SUPPRESSED = {"ble_only": COMMANDS, "localStops": frozenset({STOP_CHARGING})}` is used by Owner, Fleet, HA and telemetry. TeslaBLE uses `{"api_only": ALL}`.
  - `ready()` stays a method on each provider.
  - `attempts()` and HA's override stay until Task 13, which deletes them with `dispatch` and `VehiclePriority` (both still walk them; pre-flight H1). The reconciler never calls `attempts()`.
- Produces (`Suppressions`):
  - `conditions(self) -> FrozenSet[str]`: `{commandPolicy}`, plus `"localStops"` when `chargeStopMode` ∈ (2, 3).
  - `suppressed(provider, capability)`: the explicit setting, then `any(capability in suppressedFor(provider, c) for c in conditions())`.
- Produces (`TeslaAPI`), ledger Task 5 M2:
  - A 403 on `wake_up` records `reportScopeRefused("wake", refused=True)`, not `"command"`.
  - That 403, and every later wake while `not slot.usable("wake")` (which sends no request), returns `Outcome(UNREACHABLE, "wake refused")`, not `REFUSED`. A REFUSED would exclude FleetAPI from every command for the desire (Task 7 `noteOutcome`); UNREACHABLE only aborts this billed command (I2 guard) and is `NOT_SENT`. A command that needs no wake (stop, amps, a lower) still goes over Fleet. BLE's REFUSED wake (key refused) is unchanged.
  - `wakeOutcome` checks `slot.usable("wake")` before the free online check. `slotFor("command")` stays the slot chooser.
  - `setTokens` lifts it.

- [ ] **Step 1: Write the failing tests.**

```python
# helpers in this file: providers_of_every_kind() (one real instance per provider class, as test_provider_registration builds them) and master(settings) (a Mock master with .settings and .config; pre-flight L5)
def test_tables_match_the_declarations_they_replace():
    for p in providers_of_every_kind(): assert p.declarations() is type(p).DECLARATIONS
    assert FleetAPIProvider.DECLARATIONS[C.SET_AMPS] == C.Declaration(C.FLEET_COMMAND, C.RateLimit(50, 60))
    assert HomeAssistantProvider.DECLARATIONS[C.STOP_CHARGING].rateLimit == C.RateLimit(1, 10)

def test_a_provider_without_a_table_is_suppressed_by_locality():          # pre-flight M5
    m = master({"commandPolicy": "ble_only"}); assert Suppressions(m).suppressed(Mock(local=False, SUPPRESSED=None, name="X"), C.SET_AMPS)

def test_suppressions_come_from_the_tables():
    m = master({"commandPolicy": "ble_only"}); s = Suppressions(m)
    assert s.suppressed(fleet, C.SET_AMPS) and not s.suppressed(ble, C.SET_AMPS)
    m.settings.update(commandPolicy="api_only"); assert s.suppressed(ble, C.READ_CHARGE) and not s.suppressed(fleet, C.SET_AMPS)
    m.settings.update(commandPolicy="prefer_ble", chargeStopMode="3"); assert s.suppressed(fleet, C.STOP_CHARGING) and s.suppressed(ha, C.STOP_CHARGING) and not s.suppressed(gen2, C.STOP_CHARGING)

def test_a_403_on_wake_refuses_wakes_only(requests_mock):                    # paid calls counted
    ...; assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake refused") and len(calls(requests_mock, "wake_up")) == 1
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake refused") and len(calls(requests_mock, "wake_up")) == 1
    assert p.setAmps(VIN, 10).kind == O.DONE and api.fleetSlot.usable("command")
```

  Task 9 adds the reconciler-level counterpart: `test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car`. A 403 wake on a start, then a stop for the same car, gives one `charge_stop` POST and 1 `wake_up` in total.

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_provider_tables.py tests/unit/test_provider_order.py tests/unit/test_provider_capabilities.py tests/unit/test_provider_outcomes_cloud.py tests/unit/test_provider_outcomes_local.py -q --timeout=60 -p no:cacheprovider`, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Declare provider capabilities, costs and suppressions as tables; a refused Fleet wake retires wakes only"`

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

> **Revision 2026-10-15 (after the dedup audit, `sdd/.../dedup-audit.md`; Tasks 6–9 built, head d98d643, lib 30,246 lines).** The user's direction is that the rearchitecture must simplify and deduplicate. Growth in non-test lib code is a red flag, and line budgets are targets.
> - Each task below deletes what its new code replaces, in the same task, and states its expected lib delta.
> - The suite stays green at every boundary.
> - Order: 10 (consolidate) → 11 (limit) → 12a (charging) → 12b (amps; the façade goes) → 13a/13b/13c (independent) → 13 (cleanup and line check) → 14 (parity).

### Task 10: Consolidate the command stack; one minimum send gap; close c2 and c4 (expected lib Δ ≈ −200)

The reconciler is not wired yet, so this is the cheapest moment to restructure it. Audit items 4, 6 and 10 apply here.

**Files:**
- Modify: `Reconcile/Reconciler.py`, `Reconcile/Desired.py`, `Registry/VehicleRegistry.py`, `VehicleCommandQueue.py`, `Providers/Capability.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `WallConnectorVins.py`, `Providers/Order.py` (`debugCommand` reads `master.reconciler`; it answers False until Task 11 wires it, per ledger L35).
- Slim, not delete: `Reconcile/Run.py` (pre-flight I8). It keeps a module-level `runAttempt(reconciler, attempt) -> Outcome` plus `checked`, `_tagged`, `writtenValue`, `entryKey`, `isStop` and `_call`. It calls `reconciler.beforeWrite/afterWrite` directly: no hook lookup, no lazy import, no `isinstance`. `Workers`, `RateLimits` and `_reconcilerParts` go. `_workerOf(master, name)` stays until Task 13b, because the read-before-write still filters read sources by worker (pre-flight M2). The 600-line stop rule stays and applies to each file.
- Test (pre-flight M1): `test_workers.py` becomes `test_reconciler_queues.py`. `reconcile_helpers.py` gains `InlineQueue` (the test-only synchronous queue) and `inline(reconciler)`, which swaps the reconciler's two queues for `InlineQueue`s. Also update:
  - for `Workers`: `test_carapivehicle_registry.py` (≈135–145), `test_provider_order.py` (≈122), `test_limit_reconciler.py` (≈8/18);
  - for rate limits and callbacks: `test_outcome_desired.py`, `test_protocol.py`, `test_provider_tables.py`, `test_teslaapi_providers.py`, `test_twcmaster.py`, `test_wall_connector_vins.py`.

**Interfaces:**
- `VehicleReconciler`:
  - owns `self.ble` and `self.cloud` (`VehicleCommandQueue(run=self._run, key=entryKey, isHigh=isStop, report=self.report, lost=...)`);
  - `submit(attempt) -> bool` (local providers run inline), `cancel(key) -> int`, `start()` (both queues, then the thread) and `drain(timeout) -> bool`;
  - `_run(attempt) -> Outcome` calls `Run.runAttempt(self, attempt)`. The stale-desire guard reads `self.master.desired` directly.
- `DesiredStore.onChange` and `VehicleRegistry.onRemove` become single callable attributes (`store.changed = reconciler.wake`; `registry.removed = desired.forget`). Called outside the lock; no list, no per-callback lock. `Workers.setReport` goes, and `followRegistry` becomes that one assignment.
- `VehicleCommandQueue` loses `inline`, `_entries` and `summary` (test-only; moved to `InlineQueue` in the tests).
- **Rate limits (audit item 10).** Delete `RateLimit`, `Declaration.rateLimit`, `FLEET_COMMAND_LIMIT`, `CHARGE_SWITCH_LIMIT`, `WALL_CONNECTOR_VINS`'s limit and `WallConnectorVinReader._allowed/_calls`.
  - `WallConnectorVinReader.due()` counts a connect edge only when `clock() - lastQuery >= EDGE_MIN_GAP = 30.0` (pre-flight I7). `test_rate_limit_is_respected` keeps passing. `test_the_declared_rate_limit_bites…` is rewritten against the gap.
  - In their place, `plan()` gets one rule: `MIN_SEND_GAP = {CHARGE_LIMIT: 10.0, CHARGING: 10.0, AMPS: 15.0}`. AMPS uses 15 s, main's heartbeat rate pacing (pre-flight I6). No attempt goes out while `now - rec.lastSentAt < MIN_SEND_GAP[aspect]`.
  - `lastSentAt` survives `newDesire()`. It is stamped for every outcome not in `NOT_SENT`, including a late outcome of a replaced desire (an in-flight start when the desire flips to stop; pre-flight I5).
  - This replaces HA's 10 s start/stop gate (audit item 6) for every provider.
- **c2: only a reading that reached the car re-arms a paid send.**
  - `reachedCar(vehicle, field, since, beliefAtSend) -> bool` scans every source's report of `field` (as `latestFrom` does internally), not just the newest (pre-flight I3). It is True when either holds:
    - any observation newer than `since` comes from a source in `LIVE_READ_SOURCES = {"TeslaBLE", "TeslaAPI", "FleetTelemetryMQTT"}`. These are exact source names; Fleet Telemetry always counts, per the user's decision;
    - any vehicle-source observation newer than `since` has a value ≠ `beliefAtSend`.
  - The "re-arm on any newer reading" rule (d98d643, for paid sends that got only `UNREACHABLE`) and the I2 reopen rule both use it. HA or TeslaMate republishing an unchanged value with fresh stamps re-arms nothing. A live read of the *same* value now re-opens too; that stays bounded by the caps below.
  - **Once-per-desire re-arm cap** (pre-flight I2, I4, M4). A new `AttemptRecord.rearmed` flag, reset in `newDesire()`, allows one re-arm per desire, so a desire gets at most 4 paid sends. Three triggers share the flag:
    - the reached-car re-arm above;
    - the existing `ride` re-arm (a limit riding our start's wake; it survives c2);
    - **a charging re-arm**: for a `CHARGE_LIMIT` desire whose paid sends never reached the car, a vehicle-source `chargingState` newer than `paidAt` that is charging-like means the car is awake, so a lowered limit gets one more send.
- **c4: a refused limit counts as spent.** Limit-before-start treats the car's `CHARGE_LIMIT` desire as spent (it no longer blocks the start) when the limit cannot be delivered. That is the case when:
  - every candidate that *declares* `SET_CHARGE_LIMIT` (readiness ignored, so a briefly down BLE radio does not count) is excluded (REFUSED or UNSUPPORTED; pre-flight M11);
  - its paid sends are exhausted and none reached the car (`paidReached` stays in this test); or
  - it is held as NOT_SENT for a refusal (`"wake refused"`, `"no command token"`).

- [ ] **Step 1: Write the failing tests.**
  - Port the `test_workers.py` tests onto `reconciler.submit/cancel/drain` with `inline(r)` where they were inline. The two drain tests keep real threads.
  - Delete the `RateLimits` tests (`test_rate_slot_is_used_only_when_a_command_is_sent`, `test_ha_start_and_stop_share_one_window_per_car`, `test_rate_limited_provider_is_skipped_at_plan_time`).
  - Add:

```python
def test_min_send_gap_spaces_a_start_stop_flip_on_any_provider():          # replaces HA's 10 s gate
    ...; m.desired.set(VIN, CHARGING, True, "heartbeat"); r.pass_(); m.desired.set(VIN, CHARGING, False, "heartbeat")
    c.t += 9; assert r.pass_() == 0; c.t += 1; assert r.pass_() == 1

def test_min_send_gap_holds_when_the_flip_lands_while_the_start_is_in_flight(): ...   # I5: start reported after the flip still stamps lastSentAt
def test_amps_gap_is_fifteen_seconds(): ...                                  # I6
def test_wall_connector_edges_are_spaced_thirty_seconds(): ...               # I7, live_status requests counted

def test_ha_republishing_the_limit_every_minute_does_not_rearm_paid_sends(): # c2, paid counted
    ...; fleet scripted UNREACHABLE("408"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(60): c.t += 60; v.observe("chargeLimit", 90, "HomeAssistant"); r.pass_()
    assert len(cmds(f)) <= 2                                                 # 1 h of republishing: at most one send + one retry
    v.observe("chargeLimit", 90, "TeslaAPI"); c.t += RETRY[CHARGE_LIMIT]; r.pass_(); assert len(cmds(f)) == 3   # a live read re-arms

def test_a_live_read_followed_by_an_ha_republish_still_rearms(): ...        # I3: TeslaAPI then HA, same value -> re-arm

def test_streaming_telemetry_with_fleet_408_is_bounded_per_desire():        # I2, user decision U2, paid counted
    ...; fleet scripted UNREACHABLE("408"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy")
    for _ in range(120): c.t += 30; v.observe("chargeLimit", 90, "FleetTelemetryMQTT"); r.pass_()
    assert len(cmds(f)) <= 4 and len(calls_named(f, "wake")) <= 1

def test_lowered_limit_reaches_a_car_that_wakes_to_charge_on_teslamate():  # I4, paid counted
    ...; fleet UNREACHABLE twice then DONE; lowered 90 -> 50; c.t += 3600; v.observe("chargingState", "Charging", "TeslaMateVehicle"); r.pass_()
    assert len(cmds(f)) == 3 and calls_named(f, "wake") == []
    for _ in range(10): c.t += 600; v.observe("chargingState", "Charging", "TeslaMateVehicle"); r.pass_()
    assert len(cmds(f)) == 3                                                 # once per desire

def test_a_refused_limit_does_not_block_the_start_forever():                # c4, paid counted
    ...; ha refuses setChargeLimit (REFUSED "403"); m.desired.set(VIN, CHARGE_LIMIT, 80, "policy"); m.desired.set(VIN, CHARGING, True, "heartbeat")
    for _ in range(5): c.t += 61; r.pass_()
    assert cmds(ha).count("setChargeLimit") == 1 and cmds(ha).count("startCharging") == 1

def test_no_callback_lists_or_test_modes_in_lib():
    assert not hasattr(VehicleCommandQueue, "_entries") and "inline" not in inspect.signature(VehicleCommandQueue).parameters

def test_a_refused_limit_with_a_declared_but_unready_ble_still_blocks_the_start(): ...   # M11
```

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** per Interfaces. Slim `Run.py` as described.
- [ ] **Step 4: Run the full suite** → PASS. Record the lib delta (`git diff --shortstat HEAD~ -- lib`) in the ledger.
- [ ] **Step 5: Commit.** `git commit -m "The reconciler owns the attempt runner's queues; the runner calls it directly; one minimum send gap replaces declared rate limits; only a reading that reached the car re-arms a paid send"`

### Task 11: Held limits natively; charge-limit decision-makers write desired state; wire the reconciler; the legacy limit path goes (expected lib Δ ≈ −450)

User decision 3: migrate once at load, keep the `heldLimits` key, and write `Rules` natively on `HeldLimit`.

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Targets.py`.
- Modify: `Reconcile/HeldLimits.py`, which migrates once at `load()`:
  - VIN keys from `chargeLimits` move to `heldLimits` at once.
  - Numeric-ID entries, and any `id:*` keys already in `heldLimits` from development builds of this branch (pre-flight M9), wait in memory. They resolve the first time `loadVehicleList` succeeds with at least one vehicle. That call is `heldLimits.resolveLegacyIds({id: vin})`, over the union of the lists from every usable token slot in that cycle (Owner and Fleet may be different accounts).
  - Matched entries move under the VIN. **Unmatched entries are dropped** (user decision; pre-flight I9): one WARNING per dropped entry names the numeric ID and its outside limit (no tokens), so the user can restore it by hand. Then `chargeLimits` and the `id:*` keys are deleted and the settings saved.
  - An empty list never triggers the drop.
  - Delete `storeKey`'s `id:` handling, `LEGACY_PREFIX`, `adoptLegacyId` and the `CarApiVehicle._bind` call to it.
- Modify: `Vehicle/TeslaAPI.py` (pre-flight C1). `updateChargeAtHome()`, run by the existing `checkCharge` task, first calls `loadVehicleList()` (a free `GET /vehicles`) when `getVehicleCount() < 1`, `slotFor("read")` is usable and `getCarApiRetryRemaining()` is 0. It refreshes the token the same way `car_api_available` did.
  - Without this, nothing loads the list once `applyChargeLimit` (here) and `car_api_available` (12a) are gone, and Fleet and Owner never become ready.
  - `atHome` is refreshed only by the reads that already run: `update_vehicle_data` during read-before-write, and `updateChargeAtHome`. That is the accepted interim until Phase 5; no new paid `update_location` is added.
- Modify: `Reconcile/Rules.py`. `decideChargeLimit(desired: int, restore: bool, current: Optional[int], held: Optional[HeldLimit], sendWhenUnknown: bool)` is written natively: `held.held is None` means we hold none, and a restore puts `held.outside` back. There is no `-1`, no `lastApplied` and no `limit = -1` translation. The ported test table stays the oracle, unchanged in meaning.
- Delete (the new path replaces them in this task):
  - `TeslaAPI.applyChargeLimit` and `CarApiVehicle.apply_charge_limit`, plus `.lastLimitAttemptTime`;
  - `TeslaBLE.applyChargeLimit`, `HomeAssistant.applyChargeLimit`;
  - the VCQ `applyChargeLimit` dispatch entry and `_applyChargeLimitKwargs`;
  - `VehiclePriority.applyChargeLimit`;
  - `TWCMaster.getNormalChargeLimit/saveNormalChargeLimit/removeNormalChargeLimit`, `_heldLimitKey` and `_adoptListedHeldLimits` (and its `loadSettings` call);
  - the `applyChargeLimit` route in `queue_background_task`/`VEHICLE_COMMANDS`;
- Behaviour (ledger c6 carry): a satisfied restore removes the held record.
- Modify: `TWCMaster.py` (`desired`, `reconciler`, `policyLimit`, `setPolicyLimit`; `lastChargeLimitApplied` deleted), `Policy/Policy.py` (`enforcePolicy`), `TWCManager.py` (the `checkArrival`/`checkDeparture` tasks; start and shutdown), `Vehicle/TeslaAPI.py`, `HomeAssistant.py`, `TeslaBLE.py` (the limit copies and dedupe flags with their uses).
- Test: `tests/unit/test_limit_wiring.py`; `test_policy.py`, `test_sigterm_shutdown.py`.

**Interfaces:**
- Produces (`Targets.py`): `presentVehicles(master, capability)`, `targetsFor(master, vin, capability=STOP_CHARGING)`, `applyPolicyLimit(master, limit, decision) -> int`, `onArrival(master)` and `onDeparture(master)`, as the original plan's Task 7.
- Produces (`TWCMaster.__init__`, after `providerOrder`):
  - `self.desired = DesiredStore()` and `self.vehicleRegistry.removed = self.desired.forget` (ledger L19; Task 10 made it one assignment).
  - `self.reconciler = VehicleReconciler(self)` (it owns its two queues; Task 10).
  - `policyLimit: Optional[int] = None`; `setPolicyLimit(self, limit, transition)`.
- Produces (`TWCManager.py`):
  - `master.reconciler.start()`. The legacy `vehicleCommandQueue.start()` stays: start, stop and rate commands keep flowing on it until Tasks 12a–12b rewire them. The original plan's "silent queue between Tasks 7 and 9" no longer arises.
  - Shutdown: `master.reconciler.stop()`, then both vehicle drains share `vehicleDeadline = min(shutdownDeadline - 20, now + 60)`: `master.reconciler.drain(...)` then the legacy `drain_high_priority(...)`, each given `max(0, vehicleDeadline - now)`. At least 20 s stays for `saveSettings` (which persists `heldLimits`). A small helper `shutdownTimeouts(now, shutdownDeadline) -> float` in `TWCManager.py`'s importable code computes it and gets a unit test, `test_vehicle_drains_leave_twenty_seconds_for_settings`; `test_sigterm_shutdown.py` cannot observe it (pre-flight M9).
- Delete `master.lastChargeLimitApplied`, `TeslaAPI.lastChargeLimitApplied`, `HomeAssistant.lastChargeLimitApplied`, `CarApiVehicle.stopTryingToApplyLimit` and TeslaBLE's `_stopTryingToApplyLimit`/`_lastAppliedChargeLimit`. Also delete the `applyChargeLimit(self.lastChargeLimitApplied, checkArrival=True)` call before every Fleet start in `TeslaAPI.car_api_charge` (TeslaAPI.py:926–927; the reconciler owns the limit, and `LIMIT_THEN_START_GAP` replaces limit-before-start from Task 11) and the `applyLimit and stopTryingToApplyLimit` skip in `car_api_available` (TeslaAPI.py:517), so the interim start path neither raises nor sends an undeduped paid limit (pre-flight M10). Test: `test_legacy_fleet_start_sends_no_limit_first` (paid counted: one `charge_start`, no `set_charge_limit`).

- [ ] **Step 1: Write the failing tests.** Carry over from the original Task 7 unchanged: `test_present_rule_until_phase_5`, `test_policy_limit_sets_desired_for_present_cars_and_none_restores`, `test_periodic_reenforce_does_not_undo_an_adopted_limit`, `test_departure_restores_a_held_limit_for_an_absent_car_once`, `test_policy_thread_calls_set_policy_limit`, `test_no_module_holds_a_copy_of_the_policy_limit`. Add:

```python
def test_master_wires_store_and_reconciler_on_one_clock():
    m, s = make(); assert m.reconciler.master is m and m.desired._clock is time.time and m.desired.changed == m.reconciler.wake
    m.vehicleRegistry.getOrCreate(VIN, "t"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.vehicleRegistry.forget(VIN)
    assert m.desired.peek(VIN) is None                                     # registry.removed wired

def test_debug_route_submits_through_the_master_reconciler(): ...           # ledger L35: /api/sendTeslaAPICommand returns 200

def test_legacy_ids_resolve_once_from_the_first_vehicle_list(): ...         # VIN keys at load; ID and id:* keys on the first non-empty list (all slots); unmatched dropped, one WARNING each naming ID and limit; chargeLimits gone
def test_an_empty_vehicle_list_drops_nothing(): ...                          # I9
def test_vehicle_list_loads_without_any_legacy_command(requests_mock): ...  # C1: checkCharge -> one GET /vehicles, no vehicle_data, no wake_up; FleetAPIProvider.ready(v, STOP_CHARGING) becomes True
def test_rules_need_no_sentinel(): ...                                       # grep Rules.py for "-1"/"lastApplied" == []; the ported table passes
def test_a_satisfied_restore_removes_the_held_record(): ...                  # ledger c6
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: Targets`).
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run the full suite** → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Held limits migrate once and the rules work on HeldLimit; policy, arrival and departure set desired limits; the legacy limit path goes"`

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

### Task 13a: TeslaBLE: one classified command, one quick retry (expected lib Δ ≈ −260)

Audit item 2, user decision: the reconciler owns retry.

**Files:**
- Modify: `Vehicle/TeslaBLE.py`. Delete `_execute_with_retry`, `BLECircuitBreaker`, `_init_retry_stats`, `_record_retry_attempt`, `_calculate_backoff`, `_is_transient_exception`, `retry_stats` and the `maxRetries`/`retryDelay`/`circuitBreaker*` config reads.
- Also delete the BLE helpers already dead on main: `_kill_process_group`, `_is_transient_error`, `BLECircuitBreaker.get_status` and `closeFile` (audit §5, ≈89).
- Update `docs/Settings.md` (the removed keys are ignored if present).
- Test (pre-flight M5): retry and breaker cases are deleted or replaced, including `test_provider_outcomes_local.py::test_an_open_breaker_half_opens_after_recovery_and_a_successful_command_closes_it` (≈102–111). Also remove the `maxRetries`/`retryDelay` setup in `test_provider_outcomes_local.py`, `test_teslable_pairing_status.py` and `test_teslable_lock.py`.

**Interfaces:**
- `sendCommand(vin, command, args=None)` runs tesla-control at most twice: once, then one quick retry (`QUICK_RETRY_DELAY = 2.0` s) only on a transient failure (timeout, or "connection" in the output). There is no backoff and no breaker.
- The pairing window and refusal handling are unchanged.

- [ ] **Step 1: Tests.**
  - `test_a_transient_failure_is_retried_once_then_reported`: two calls, then `UNREACHABLE`.
  - `test_a_non_transient_failure_is_not_retried`: one call.
  - `test_removed_retry_config_keys_are_ignored`.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "TeslaBLE sends one classified command with one quick retry; the reconciler owns retry"`

### Task 13b: Registry reads through the providers (expected lib Δ ≈ −150)

Audit item 7.

**Files:**
- Modify: `Registry/VehicleRegistry.py` (`cascade` walks `providerOrder.ordered(READ_CHARGE)`), `Registry/Vehicle.py`, `Providers/Provider.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `Providers/Order.py`, `Reconcile/Reconciler.py` (read-before-write filter), and the `readSource` attributes on TeslaBLE/TeslaAPI/HomeAssistant.
- Delete: `Registry/ReadSource.py`, `Registry/Sources.py`, `VehicleRegistry.registerReadSource/useReadOrder/readSources` and `ProviderOrder.orderReadSources`.
- Test: `test_registry_read_cascade.py` is retargeted to providers; read-source registration tests are deleted.

**Interfaces:**
- `Provider.FIELDS: FrozenSet[str] = frozenset()` and `Provider.fetch(self, vehicle, field, allowWake=False) -> bool` (what `ReadSource.fetch` did).
- Readiness for a read is the provider's own `ready(vehicle, READ_CHARGE)`. Suppression and cost order come from `ProviderOrder`, as for commands.
- `Vehicle.read(field, maxAge, allowWake=False, providers=None, force=False)`: `providers` replaces `sources`.
- The reconciler's read-before-write passes the providers on the attempt provider's `worker`.

- [ ] **Step 1: Tests.** Retarget the cascade tests: free first, never wakes unless asked, `force` past a live feed, restricted to the given providers, `api_only` skips BLE.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "Read vehicle fields through the providers; the parallel read-source classes go"`

### Task 13c: One TeslaAPI request helper (expected lib Δ ≈ −120)

Audit item 9.

**Files:**
- Modify: `Vehicle/TeslaAPI.py`. `CarApiVehicle.get_car_api`, `_paidPost` + `commandRefused`, `loadVehicleList` + `slotRequestFailed`, and `_energyGet` + `_energyRefused` + `_refuseWallConnectors` all go through one helper.
- Test: `test_teslaapi_request_errors.py` is extended. Existing status tests pass; the classifier keeps the per-path differences they pin (pre-flight M6):
  - the vehicle list does not retry after a 401 and starts no API backoff;
  - the energy path's 403 refuses purpose `"energy"` (Wall Connector reads only; Gen3 cloud VIN depends on it);
  - a command after a 401 retries once after a refresh, as today (no new paid call).
- `loadVehicleList` keeps Task 11's `heldLimits.resolveLegacyIds` call and Task 11's `updateChargeAtHome` loader.

**Interfaces:**
- `TeslaAPI._request(self, slot, method, path, purpose, body=None, timeout=10) -> Tuple[Optional[requests.Response], Optional[Outcome]]`. It builds the headers and makes one request.
- One status classifier, `_classify(slot, status, purpose, body) -> Optional[Outcome]`:
  - 401 refreshes once and retries once, else retires the slot;
  - 403 refuses `purpose`;
  - 410 pauses the slot;
  - 412 pauses it with `latch=True`;
  - 429 sets the backoff;
  - 408 is `UNREACHABLE`.
- Callers keep their own success parsing.

- [ ] **Step 1: Tests.** A table-driven `test_every_path_classifies_status_codes(path, status, expected)` over the 4 paths × 6 statuses, with the per-path expectations above, counting requests per URL.
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit.** `git commit -m "One TeslaAPI request helper and status classifier for reads, commands, the vehicle list and energy sites"`

### Task 13: Final cleanup, docs and the line check (expected lib Δ ≈ −400)

By now Tasks 11–12b have deleted the façade, the legacy queue mode and every module command method. This task removes what remains orphaned, plus code that is already dead on main.

**Files:**
- Delete or modify, all from the audit:
  - **Task 13 misses (audit §3)**, whatever Tasks 11–12b did not already take:
    - `HomeAssistant.car_api_available`, `minBatteryLevelAtHome`, `numCarsAtHome`, `getCarApiVehicles`, `getVehicleCount`, `_is_vehicle_connected`, `_call_service`;
    - `HaVehicle`'s cached fields and `at_home` writes (it keeps its entity map);
    - `TeslaAPI.numCarsAtHome`, `findReason`, `refuseCommandIfReadOnly`, `updateLastStartOrStopChargeTime` and `carApiLastStartOrStopChargeTime` (both modules, plus their reads and call in `WebIPCControl.py`, found by name; pre-flight M10);
    - `Suppressions.commandPolicyOverridden`, `Provider.vehicleAttachment` (+ HA's), `HeldLimits.holding` (`_stampWrite` and `_count` already went in 12b).
  - **Code dead on main (audit §5):**
    - `Control/APIValidator` `validate_required_fields`, `validate_integer`, `validate_string`, `validate_choice`, `is_safe_string`;
    - `EVSEController.startAllCharging/stopAllCharging`;
    - `TWCMaster.getSendServerTime/setSendServerTime/getMasterSign/setkWhDelivered/delete_background_task`.
  - **Dead declarations and summaries (audit §5; user decision 7: Phase 6 re-adds what the tab needs):**
    - `READ_LIST/READ_ONLINE/READ_PLUG/READ_VIN/READ_AMPS/READ_LOCATION` and their table entries;
    - `TelemetryProvider` and `TelemetryBase.providers()`;
    - `sharedControl` (Provider, Gen3TWCProvider, Gen3TWCs) and `Declaration.passive`;
    - `Provider.summary`, `Desired`/`AttemptRecord`/`FreeChannel`/`DesiredStore` summaries, `VehicleReconciler.summary` (`VehicleCommandQueue.summary` already went in Task 10);
    - the orphans `VehicleRegistry.pointFor`, `fresherThanWrite` (both), `CarApiVehicle.syncTimestamp`, `TeslaAPI.energySites`, `Gen3TWCs.unitTargets/headroom` (only the unused accessors; the solver stays, per the user) and `ChargingPoint.vehicleEndpoints`.
    - `Cost.price` stays as a field (the spec requires it); only its reader goes.
  - Reword the remaining "lane"/VehiclePriority comments; `LANE_DETAILS` becomes `QUEUE_DETAILS`.
  - `docs/Settings.md` and `CHANGELOG.md`: the text from the earlier revision of this task. The changelog adds "TeslaBLE no longer retries internally or opens a circuit breaker; `maxRetries`, `retryDelay` and `circuitBreaker*` are ignored".
- Test: `tests/unit/test_no_legacy_command_paths.py`. The summary deletions also touch `test_outcome_desired.py` (≈51/147), `test_provider_capabilities.py` (≈51), `test_provider_outcomes_local.py` (≈34) and `test_provider_tables.py` (pre-flight I10).

- [ ] **Step 1: Write the failing test.** The grep covers every tracked file under `lib/`, code and comments:

```python
# grep(pattern, exclude=()) runs `git grep -l` over lib/ and drops the excluded paths
def test_legacy_paths_and_dead_code_are_gone():
    assert grep("VehiclePriority\\|queue_vehicle_command\\|calculateModulePriority\\|getModuleByPriority\\|targetAmps\\|_DISPATCH\\|def attempts") == []
    assert grep("def car_api_charge\\|def applyChargeLimit\\|def setChargeRate\\|def apply_charge_limit\\|def car_api_available\\|stopAskingToStartCharging\\|NormalChargeLimit\\|_heldLimitKey") == []
    assert grep("def dispatch\\|lastChargeLimitApplied\\|stopTryingToApplyLimit\\|getLastStartOrStopChargeTime\\|_execute_with_retry\\|BLECircuitBreaker\\|class RateLimits\\|ReadSource") == []
    assert grep("_attemptSummary\\|_desiredSummary\\|def summary", exclude=["lib/TWCManager/Vehicle/Registry/Vehicle.py", "lib/TWCManager/Vehicle/Registry/VehicleRegistry.py"]) == []   # Vehicle.summary/summaries feed a template (pre-flight I10)
```

- [ ] **Step 2–4:** FAIL → delete → full suite PASS.
- [ ] **Step 5: Line check (report; the target is a target, not something to fit).**

```bash
git ls-files 'lib/*.py' | xargs cat | wc -l                                  # target ≤ 26,750 (audit projection, including the later CarApiVehicle phase)
git diff --shortstat origin/main -- lib; git diff --shortstat 6a6c14e -- lib; git diff --shortstat 39d7cfb -- lib
git diff --numstat 39d7cfb -- lib | awk '{a+=$1; d+=$2} END {print "added", a, "removed", d; exit !(d >= a)}'
```

  Expected: the awk exits 0 (removed ≥ added since 39d7cfb). Record the total and the three shortstats, with per-task actual vs expected deltas, in the ledger and the commit message. If the total is over the target, report by how much and where; do not pad deletions.
- [ ] **Step 6: Commit.** `git commit -m "Remove code the new command path orphaned or that was already dead; drop unread summaries and declarations"`

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
