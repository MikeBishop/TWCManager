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

