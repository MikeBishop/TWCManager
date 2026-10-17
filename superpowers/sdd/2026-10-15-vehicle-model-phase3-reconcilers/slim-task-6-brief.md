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

