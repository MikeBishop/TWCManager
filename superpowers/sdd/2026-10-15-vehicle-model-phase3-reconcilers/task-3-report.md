# Task 3 report: Lanes

**Status:** DONE_WITH_CONCERNS (none of the concerns blocks the task)

**Branch:** vehicle-model/phase3 (worktree scratchpad/wt-vm3), on top of 9a44495.

**Commits:**
- 3f40b3d Add per-channel lanes that run attempts with read-before-write, wake-first, rate limits and classified outcomes
- 43886b9 Warn about a full lane once per backlog, not once per entry run

**Tests:** full suite `tests --ignore=tests/API --ignore=tests/integration` gives 1410 passed, 1 xfailed at 43886b9. The baseline was 1383; the difference is 26 tests in `test_lanes.py` and one new test in `test_provider_order.py`. The Step 4 set gives 108 passed. `test_lanes.py` passed on 3 runs in a row.

**Fail-before:** `tests/unit/test_lanes.py` failed at collection with `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Reconcile.Lanes'`.

## Files
- New: `lib/TWCManager/Vehicle/Reconcile/Lanes.py`. It holds `LANE_PROVIDERS`, `entryKey`, `writtenValue`, `runAttempt`, `Lane` and `Lanes`.
- `lib/TWCManager/Vehicle/Providers/Provider.py`:
  - Adds `PROBE = "probe"` and `commandMethod(capability)`. Capability names are already the method names.
  - Adds the six command methods: `setChargeLimit`, `startCharging`, `stopCharging`, `setAmps`, `wake` and `probe`. Each defaults to `Outcome(UNSUPPORTED, "not implemented")`. They used to raise `NotImplementedError`.
- `lib/TWCManager/Vehicle/Providers/Order.py`:
  - `debugCommand` now picks the first candidate with `module is not None`, using `localRule=False`.
  - It builds a one-shot `Attempt` and returns `master.lanes.submit(attempt)`. There is one provider per command and no fall-through; the docstring says so.
  - `Attempt` is imported lazily. A top-level import would be circular on a cold `import TWCManager.Vehicle.Reconcile`, because `Desired` is still initialising when `Providers/__init__` loads `Order`.
  - `dispatch` is unchanged.
- Tests:
  - `tests/unit/test_lanes.py`: I kept the earlier draft and fixed two of its tests (see "Draft disposition").
  - `test_provider_order.py`: the three debug tests are rewritten on a master with `Lanes(m, inline=True)`. M1 keeps its final `dispatch` assertion. "Tries each provider once" now checks that BLE is called once and Fleet not at all. The new test `test_debug_command_without_lanes_submits_nothing` covers a master with no lanes.
  - `test_carapivehicle_registry.py`: the debug test sets `master.lanes = Lanes(master, inline=True)`.
  - `test_registry_callers.py`: comments only. `debugCommand` returning True now means an attempt was submitted.
- black was run only on `Lanes.py`, `Order.py` and `Provider.py`.

## Decisions to record
- **Who mutates AttemptRecord and ChannelHealth: store methods.**
  - Lanes mutate neither. They only deliver `(attempt, outcome)` to the report callback, passing the same `Attempt` object that was submitted, so a match by identity works.
  - That callback runs on a lane thread, or on the submitter's thread for an inline lane. There is no single mutating thread, so Task 6's report handler must change records and health through `DesiredStore` methods under its lock.
  - Task 6 must also clear `inFlight` only when it `is` the reported attempt, and ignore a late report after `endSession`.
- **Threading and the queue.**
  - Each lane has one `threading.Condition` guarding the pending list (at most 64 entries), the running attempt, the stopping/closed flags, the rate windows and the set of providers already warned about a bad return.
  - Losing entries (replaced, dropped, cancelled or drained) are collected under the lock and reported after it is released.
  - No lock is held during `runAttempt` or the report callback.
  - `_run` loops `while not self._stopping`, with `Condition.wait(timeout=1.0)` when there is nothing to do.
- **Deviation from the brief's `_run` wording.** The thread exits only when the lane is closed *and* nothing is pending. It sets `_stopping` itself at that point. This lets a started lane's own thread run the pending stops during a drain. Taken literally, `while not self._stopping` would exit before running them.
- **How drain works.**
  - `Lanes.drain` first closes cloud and ble and drops their non-stop entries. Each drop is reported, with one INFO line per lane giving the count.
  - It then waits for, or runs, the stops, using one `time.time` deadline shared by both lanes.
  - A lane that was never started runs its stops on the caller's thread.
  - On timeout, stops that have not started are reported `dropped`. The hung running attempt still reports when it returns.
  - Submitting to a closed lane, inline or threaded, reports `dropped` and returns False.
- **Queue order and overflow.**
  - Stops go to the front, first-in-first-out among the stops.
  - A pending entry with the same `entryKey` is replaced, and that includes stops.
  - When the lane is full, the oldest non-stop is dropped. If the lane holds only stops, the newcomer is rejected and reported `dropped`.
  - The overflow WARNING fires once per backlog. It re-arms when the thread empties the queue.
- **`entryKey` for a one-shot** takes a fresh `itertools.count` number on each call. The lane computes the key once, at submit, and stores it with the entry. One-shots therefore never replace each other, and never replace probes.
- **Wake first.** Only `REFUSED`, and `UNREACHABLE` from a non-local provider, abort the attempt, as the brief says. An `ERROR` or `UNSUPPORTED` wake goes on to the command.
- **Bad return.** The outcome is `Outcome(ERROR, "bad return <type name>")`, with a WARNING once per (provider, method) per lane.
- **Exceptions.** `runAttempt` turns them into `Outcome(ERROR, <type name>)`. `_runOne` adds a second guard, so a raising `runAttempt` can never kill the thread and leave an entry unreported. A raising report callback is logged at WARNING by type name only.
- **One-shot log line.** It is `Debug <capability> for <vin> via <provider>: <kind> <detail>`. `<command>` is the capability name, for example `wake` rather than `wakeVehicle`, because the Attempt does not carry the route name.
- **Rate window.**
  - The window is a `deque(maxlen=calls)` of `time.monotonic()` stamps per `(provider.name, capability, vin)`. `time.monotonic` is reached through the module attribute, so tests can monkeypatch it.
  - Windows that no longer constrain anything are swept on each `note`, so the map stays bounded.
  - `lane.note` runs before the read and satisfied check (brief order), so an attempt satisfied by the read still uses a slot.
- **Placeholders until Task 6.**
  - `Lanes.py` imports `VehicleReconciler`, `satisfied` and `VEHICLE_SOURCES_EXCLUDED` lazily, with the same `ModuleNotFoundError`/`e.name` guard that `Desired.py` uses.
  - Until then it falls back to the minimal `satisfied`, an empty exclusion set and `hooks=None`.
- **Held limits** are not touched or clamped here.
- **Clock.** The drain deadline uses `time.time`, following the one-clock rule. A wall-clock step during shutdown would shift it. The threaded tests run on the default production clock.

## Draft disposition
- I kept all of the brief's tests verbatim, plus the "beyond the brief" tests: threading, identity, drain timeout, a started-lane drain, overflow with a lane full of stops, cancel leaving a running stop alone, logging by type name, and the local lane always running inline.
- Two draft tests were fixed:
  - `test_read_before_write_uses_only_the_lane_s_own_sources` never fetched from either source. Its `Src` had a 3-argument `canRead` and no `fields`, but `cascade` calls `canRead(vehicle)` and skips sources whose `fields` lack the field.
  - `test_probe_runs_alone_without_read_wake_or_stamp` registered a source with no `fields`, so it proved nothing. It now counts fetches and shows that a normal attempt does reach that source.
- Added `test_drain_delivers_a_cloud_stop_and_drops_a_ble_limit`, which covers Review Focus 5 across both lanes.

## Concerns (none blocks)
1. **Debug route is down until Task 7.** Production `TWCMaster` has no `lanes` until Task 7. Until then `debugCommand` returns False through its `getattr` guard, so the route answers 400. Without the guard it would raise.
2. **Real providers still return bools.** They do until Tasks 4 and 5. A debug one-shot on them is reported `ERROR "bad return bool"`, with one WARNING per provider and method, although the command did go out. `test_debug_interface_resolves_by_vin` therefore asserts that the attempt was submitted, not its outcome.
3. **`dispatch` is unchanged; the `Outcome.kind in SETTLED` carry-forward is deferred to Task 4.**
   - The only live `dispatch` caller is `VehiclePriority.setAmps`.
   - Every provider that declares `SET_AMPS` overrides `setAmps`.
   - So the base class's new truthy `Outcome(UNSUPPORTED)` cannot reach `dispatch` today. Task 4 must add the check before any provider returns an Outcome through `dispatch`.
4. **The hooks path is untested.** That is the `isinstance(master.reconciler, VehicleReconciler)` check plus `beforeWrite`/`afterWrite`. It cannot be tested until Task 6 provides the class; only the pass-through path has coverage.
5. **Two points for Task 6.**
   - `beforeWrite` will receive one-shot attempts with `aspect=None` and must pass them through as `(attempt.value, None)`.
   - `Desired._chargingLike` calls `satisfied(CHARGING, True, value)` with a raw value, while the plan's `satisfied` takes an `Observation`. Task 6 has to settle on one signature.

## Fix round 1

**Commit:** 97377b8, on top of 43886b9.

**Tests:** full suite 1415 passed, 1 xfailed. That is 5 new tests in `test_lanes.py`. `test_lanes.py` passed on 3 runs in a row. The reviewer's probe, with the strict assertions restored, passed 9/9 on 6 runs.

**Fail-before:** I wrote the tests first and ran them against the 43886b9 `Lanes.py`. Six failed:
- `test_a_raising_after_write_keeps_the_sent_command_done`: `('FleetAPI', 'error', 'RuntimeError') != ('FleetAPI', 'done', '')`
- `test_a_raising_after_write_hook_keeps_the_sent_command_done`: `('FleetAPI', 'error', 'ValueError')`
- `test_a_failed_billed_wake_never_sends_the_billed_command`: `['wake', 'setChargeLimit'] == ['wake']`
- `test_concurrent_drains_of_a_never_started_lane_share_one_runner`: more than one stop ran at once. The first draft of this test used keys that are not in the registry, so it never reached the provider. I fixed that before relying on it.
- `test_an_inline_lane_is_busy_while_it_runs`
- `test_rate_limit_per_provider_capability_and_vin`: there is no `_monotonic` attribute yet (M7).

**Probe on the old code:** the strict probe failed with `maxInflight` 2 and 3, and with drain results `[True, True, False]` and `[False, True, True]`.

### What changed
- **I1.** `runAttempt` now has two stages:
  - The command runs inside the main `try`.
  - Once an outcome exists, the stamp (`provider.cost` and `noteWrite`) and `hooks.afterWrite` each run in their own `try/except`. A failure there is logged at WARNING by type name only, and the provider's original outcome is returned.
  - A command that took effect is therefore never reported as a retryable ERROR.
  - Tests:
    - a raising `noteWrite` and a raising `cost` both still give DONE with a single call;
    - a raising `afterWrite` through a stubbed reconciler type gives DONE, keeps the stamp and makes one call. The stub is `_reconcilerParts` monkeypatched; this is the first test of the hooks path.
- **I2.** A non-local provider's command goes out only when the wake outcome is in `_WAKE_PROCEEDS = {DONE, SATISFIED, UNSUPPORTED}`.
  - REFUSED still aborts for every provider.
  - A local provider still sends the command after any other failed wake.
  - Test: a Fleet wake that returns `ERROR "500"` or a bare `True` (bad return) yields `calls == ["wake"]` and an ERROR report. DONE, SATISFIED and UNSUPPORTED wakes proceed. A BLE wake ERROR still sends the command.
- **M1.** In a never-started lane's drain loop, a drainer that finds `_running` set waits on the condition until its deadline, so there is one runner.
  - The runner notifies when it finishes.
  - A concurrent drain therefore returns True whenever nothing was dropped.
  - The probe's strict `res == [True]*3` and `maxInflight <= 1` (all providers except Gen2TWC) are restored in `scratchpad/probe-p3t3/test_probe_lanes.py`.
- **M3.** An inline submit sets `_running` around `_runOne`, and clears it only if it is still that attempt. `busy` and `summary()["running"]` are now correct while it runs. Overlapping inline callers show the latest one.
- **M5.** A finished drain joins its thread for `min(WAIT, max(0.1, remaining))`.
- **M7.** `Lanes._monotonic = time.monotonic` is now an alias, and `allows`/`note` call it. The test patches the alias, not the global `time` module.
- **M8.**
  - The started-lane test's asserts are moved out of `finally`.
  - The `threading.Timer` is joined.
  - The I1 and I2 tests listed above are added.

### Not fixed
- **M2:** `note` before the read uses a rate slot. This follows the brief's order; moving `note` to just before the wake or command needs a plan ruling.
- **M4:** a backward wall-clock step during a drain. This is the one-clock rule's trade-off, and its owner decides.
- **M6:** `BaseException` on a daemon lane thread. Noted only.
- **M9:** the placeholder `_satisfied` cannot satisfy CHARGING. Task 6 replaces it.
- The review's carry-forwards for Tasks 6 and 7 still apply:
  - Losers are reported on the caller's thread, so the reconciler must not call `submit` or `cancel` while it holds the DesiredStore lock.
  - The reconciler is the rate-limit gate.
  - Do not call `drain` from a report callback.
  - Task 7 must start the lanes before the first submit.
