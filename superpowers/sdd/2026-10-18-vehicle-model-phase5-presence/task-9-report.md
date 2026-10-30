# Task 9 report: BLE scans and attribution reads run on the BLE worker

Commit **8065c4d6** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent a63e70ac). Not pushed.

## Entry point: `Run.Job` + `VehicleReconciler.submitJob(key, kind, run)`

- `Run.Job(key, kind, run)` is a NamedTuple beside `entryKey`. `submitJob` is one line: `self.ble.put(Run.Job(key, kind, run))`.
- It goes through the BLE lane's own `VehicleCommandQueue.put`, so ordering, coalescing, `close`/drain and the lost path are the queue's, unchanged. The queue itself is untouched. The Job is dispatched in four places:
  1. `Run.entryKey`: a Job keys as `(key, kind)`. A scan is `(vin, "scan")` and an attribution is `(pointId, "attribute")`. Neither can collide with an attempt's `(vin, aspect)`. This key gives one pending job per VIN (or per point).
  2. `Run.isStop`: a Job has no `capability`, so it is never high. It runs in FIFO order behind the commands queued before it, and stops still go first.
  3. `Reconciler._run`: a Job's `run()` is called inside the existing `try/except Exception`, so a failing job never kills the worker.
  4. `Reconciler.report`: a Job returns before `.aspect`/`.capability` are read. `report` is also the `lost` callback ("replaced", or "dropped" at shutdown). A failure outcome is logged at WARNING as `"<kind> <key>: <detail>"`, for example `scan <VIN>: RuntimeError`. "replaced" (the coalescing) and "dropped" (shutdown or overflow, which the queue already logs once) are silent (`_QUIET`). A job's own return value (a scan verdict, a VIN) is ignored.
- `_bleLock` is untouched. `scanForVehicleInRange` is still `@_serialized`, and attribution's `v.read(..., providers=("TeslaBLE",))` takes it inside TeslaBLE. No new lock is held across a run.
- **Rejected alternative:** the debug one-shot (`aspect=None`). It would carry a scan as a provider call with no new run code. But its key is a fresh sequence number, so it cannot coalesce. And it cannot carry `Presence.attribute`, which is not a provider method. One mechanism covers both jobs.
- **Reconciler not running (requirement 4):** a never-started queue accepts the entry and holds it (`_thread is None` is neither dead nor draining). So the request is a no-op until the worker starts. Production starts the reconciler unconditionally (`TWCManager.py:795`, after module load, with no BLE or mode condition), so this case only arises in tests and the startup window. At shutdown, `close()` drops pending jobs through the lost path, silently. The page's "Scanning…" state then times out after `SCAN_PENDING_MAX`.

## Callers

- **`TeslaBLE.requestRangeScan`**: its bookkeeping (VIN check, `SCAN_DEBOUNCE`, `_scanInProgress`, `_scanRequests[vin] = now`) is unchanged. It ends `self.master.reconciler.submitJob(vin, "scan", lambda: self._scanRequested(vin))`.
  - The new `_scanRequested(vin)` is the old drain loop's body for one VIN. Under `_scanLock` it pops the request and adds the VIN to in-progress in one critical section, then scans. In `finally` it discards the VIN, so `scanPending` always clears.
- **`TWCMaster._plugSession`** (serial thread, no lock held): it submits `(twcid, "attribute", attribute)`. `attribute()` reads `reportedAmpsMax`/`reportedAmpsActual` when it runs, as the background handler did, and calls `Presence.attribute(self, twcid, "Gen2TWC", *amps)`. `put` only takes `_cond` briefly, so the serial thread never blocks.
- Gen3's `_correlate` still calls `attribute` with no offer, so `read=False` and there is no BLE I/O. It stays where it was.

## Deletions

- `TWCManager.py`: the `attributePlug` branch, the `bleScan` branch, the post-`doneBackgroundTask` requeue block, and the now-unused `Presence` import (−22).
- `TeslaBLE.py`: `runPendingScans`, `requeueIfRequested`, `SCAN_DRAIN_PASSES` and its comment.
- `TWCMaster._taskKey`: the `attributePlug` half.
- Kept: `_scanRequests`, `_scanInProgress`, `_scanLock`, `SCAN_DEBOUNCE`, `SCAN_PENDING_MAX`, `rangeStatus`, `scanPending`.
- Comments updated per the comment rule: `Presence.attribute` (it no longer says "Background thread"), the `_scanInProgress` comment, and the `requestRangeScan` docstring.
- The grep is clean: `git grep -nwE 'bleScan|requeueIfRequested|runPendingScans|SCAN_DRAIN_PASSES|attributePlug' -- lib html tests/unit tests/integration tests/API docs` returns nothing.

## Where each job runs, and the evidence

| Job | Thread | Evidence |
|---|---|---|
| Range scan (vehicle page "Scan") | `Vehicle-ble` | `test_ble_jobs.py::test_a_scan_runs_on_the_ble_worker_after_the_command_ahead_of_it`. It uses a real reconciler with a started BLE worker and a 0.3 s BLE `setChargeLimit` submitted by `pass_()`, then requests a scan. Both record `threading.current_thread().name == "Vehicle-ble"`, the scan starts after the command ends, `queue_background_task` is never called, and `scanPending` clears |
| Gen2 VIN-less attribution, including its BLE charge read | `Vehicle-ble` | `test_a_vinless_plug_queues_its_attribution_on_the_ble_worker`: two `_plugSession(s, True)` calls leave exactly one `("8244", "attribute")` entry on `r.ble`, and no background task is queued |
| Pre-flight ping and its fallback scan (Task 8) | `Vehicle-ble` (unchanged) | it is already inside `runAttempt` |
| Gen3 attribution | Gen3 vitals (background) thread, unchanged | no offer, so no BLE read |

- Burst: `test_a_burst_of_requests_for_one_car_runs_one_scan`. Five requests give one queue entry and one scan.
- Failure: `test_a_failing_job_is_logged_and_the_worker_runs_the_next`. Job A raises `RuntimeError`, job B still runs on the same started worker, and the log carries `RuntimeError`.
- Nothing on the background thread calls into TeslaBLE's scan or attribution any more: the branches are gone (grep above).

## Tests

- **New:** `tests/unit/test_ble_jobs.py` (4 tests).
- **Helpers (PLUMBING-ONLY):**
  - `reconcile_helpers.runPending(q)` runs a queue's pending entries on the caller's thread.
  - `InlineQueue.put` leaves a Job pending until the test runs it, rather than running it inline. This keeps the old harness semantics, where an attribution or scan ran only when a test drained it. Running jobs inline at the plug moved the parity row `test_no_gps_source_plug_unplug_cycle_end_to_end` and three `test_presence` tests, because harnesses that never drained the background queue suddenly attributed. With the deferral, nothing moves.
- **`test_command_path_parity.py`: PLUMBING-ONLY.** Only the `attributeQueued(m)` helper changed: it now runs `runPending(m.reconciler.ble)` instead of draining `attributePlug` background tasks. One import was added. **No row, count or timing was edited.**
- **`test_gen2_unplug.py::test_an_unnamed_session_outlasts_a_waking_00_and_departs_no_one`: PLUMBING-ONLY.** It spies `m.reconciler.submitJob` instead of `queue_background_task` and asserts one `("8244", "attribute")`. The other assertions are unchanged.
- **`test_teslable_pairing_status.py`:** `scanner()` gives the Mock master a real (unstarted) `VehicleReconciler`. A `jobs(master)` helper lists the pending `(vin, kind)`.

  | Test | Fate |
  |---|---|
  | `test_request_scan_queues_one_task_and_runs_every_pending_vin` | Renamed `..._queues_one_job_per_vin_...`. PLUMBING-ONLY: asserts two scan jobs, not one bleScan task; same scans and pending assertions |
  | `test_request_during_a_scan_is_served_by_the_same_task` | Renamed `test_request_during_a_scan_queues_behind_it`. PLUMBING-ONLY: same `seen == [VIN, VIN2]` |
  | `test_request_rejects_malformed_vin` | PLUMBING-ONLY: no job instead of no task |
  | `test_scan_is_pending_while_it_runs`, `test_pending_cleared_when_a_scan_raises` | PLUMBING-ONLY: `runPending` instead of `runPendingScans` |
  | `test_request_within_ten_seconds_of_a_scan_is_ignored`, `test_request_while_the_vin_is_being_scanned_is_ignored` | PLUMBING-ONLY: job counts instead of task calls; same debounce assertions |
  | `test_mid_scan_request_is_served_without_a_follow_up` | Renamed `..._served_by_the_worker_once`. PLUMBING-ONLY: same `seen`, and no job left behind |
  | `test_drain_is_bounded_and_leaves_one_follow_up` | DELETED: it pinned `SCAN_DRAIN_PASSES` and `requeueIfRequested`, which brief item 2 removes. Its concern (a burst never queues unbounded work) is covered by `test_a_burst_of_requests_for_one_car_runs_one_scan` and per-key coalescing |
  | `test_requeue_after_the_task_when_requests_remain` | DELETED: it pinned `requeueIfRequested`, which is removed. The race it guarded (a request coalesced into a finishing task) cannot happen with a keyed queue entry per VIN |

- **TDD evidence:**
  - RED: before any lib change, the 4 new tests all failed (no `submitJob`, nothing queued on the BLE worker).
  - GREEN after the change.
  - Mutation: `submitJob` replaced by "start a fresh thread and run it" fails all 4.
- **Suites:**
  - `tests/unit` + `tests/EMS`: **2124 passed** (2122 + 4 new − 2 deleted).
  - Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2133 passed, 1 xfailed**.
  - The one warning is the existing Enphase `InsecureRequestWarning`.
- Black is clean on every touched black-style file.

## Lib delta

- Before: 26,259. After: **26,243** (**−16**). The target was ≤ 0 (expected −20..−30).
- `git diff --shortstat a63e70ac -- lib`: 6 files changed, 48 insertions(+), 64 deletions(-).
- `git diff --numstat` (+/−): TWCManager.py 0/22, TeslaBLE.py 14/36, TWCMaster.py 8/4, Run.py 12/1, Reconciler.py 12/0, Presence.py 2/1.
- It falls 4 short of the expected range. The new entry point (Job, `submitJob`, the four dispatch points and `_QUIET`) costs 24 lines; the deleted drain, requeue and background branches saved 58.

## Concerns

1. (Resolved after the advisor's review: "dropped" is silent, like "replaced".)
2. **The request is a no-op until the reconciler starts.** A request made before `master.reconciler.start()` (startup) sits until the worker starts. Production starts the reconciler unconditionally, so that is only a short window.
3. **Attribution now waits behind BLE commands.** With a backlog (retries take minutes), naming a VIN-less plug waits longer than it did on the background thread. That is the intended trade (the user's point about lock coupling). The fan-out over `pluggedHere` still rates in the meantime.
4. **`isStop` uses `getattr(attempt, "capability", None)`.** That is the cheapest way to type a Job as not high, but it would also silently accept any other foreign entry.

## Fix round 1 (commit a298c10f)

### 1. The 80→50 flap: root cause and fix

- **Cause:** `master.policyLimit` started as `None`, and `None` also means "the policy sets no limit". An arrival before the policy's first pass was therefore read as "no limit", and for a held car that is a release.
  - In the no-GPS cycle, with jobs drained at the plug, attribution names the car at t=1000. Its `pluggedIn` observation triggers `onArrival` → `_apply(policyLimit=None)` → `RELEASE (-1)`. A release of a held car (80, 50) restores 80.
  - The first policy pass (t=1020, limit 50) then re-applies 50. The result is `[80, 50]` to a car that already read 50.
  - Confirmed with a scratch run: when the policy passes once before the plug, the same scenario sends nothing.
  - So this is not specific to attribution. Any arrival before the first policy evaluation does it, attribution being the earliest. Live, the policy's first pass usually precedes the first heartbeat, but nothing orders it before the attribution job.
- **Fix:**
  - `Targets.UNDECIDED` is a sentinel, and `TWCMaster.policyLimit` starts as it.
  - `onArrival` returns while the policy is UNDECIDED. The policy's first pass is a transition (`active_policy` changes), so it decides for every present car anyway.
  - `None` keeps meaning "no limit".
- **New parity row:** `test_a_plug_attributed_before_the_policy_pass_sends_a_held_car_nothing`. It runs the same scenario with attribution drained at the plug and after every beat. While plugged, `limits(b) == []`; the unplug gives `[80]`; held is cleared; paid is `(0, 0, 0)`.
  - With `policyLimit` initialised to `None` again, it fails with exactly `[80, 50] == []`.
  - The existing row is unchanged.
- **Test touched:** `test_limit_wiring.py::test_master_wires_store_and_reconciler_on_one_clock` now asserts `policyLimit is UNDECIDED` instead of `None`. INTENTIONALLY CHANGED by this fix.
- **Side effect:** in modes where the policy thread never runs (fakeMaster ≠ 1), `onArrival` now writes nothing. Before, a release was applied, which for a held car meant a restore. Those modes run no heartbeat-driven attribution.

### 2–5. Review items

2. The `HTTPControl.vehicleLocalMgmt` docstring now says the scan runs on the BLE worker.
3. When `submitJob` returns False, `requestRangeScan` pops the request, so `scanPending` clears at once, and logs one WARNING per refused request: "BLE scan for <VIN> not queued: the BLE worker has stopped". There is no retry.
   - New test: `test_a_scan_the_stopped_worker_refuses_is_not_shown_pending`.
4. Cuts:
   - `_QUIET` and the Job branch's logging are gone. `_run` returns `job.run()` outside its try, so a raising job is logged by the queue (`Vehicle-ble: run raised RuntimeError`), and the worker survives.
   - `report` returns first for a Job.
   - `Job` is `collections.namedtuple("Job", "key kind run")` with a two-line comment.
   - The attribution closure is a lambda.
5. The unrelated black hunk in `test_teslable_pairing_status.py` (`test_the_quick_retry_is_logged_at_info_once`) is reverted.

### Tests and size

- Covering files (ble_jobs, parity, presence, gen2_unplug, pairing_status, presence_attribution, limit_wiring, reconciler_queues, vehicle_detail_page): 379 passed.
- `tests/unit` + `tests/EMS`: **2126 passed** (2124 + the new parity row + the refused-scan test).
- Lib vs a63e70ac: 26,259 → **26,249 (−10)**. `git diff --shortstat a63e70ac -- lib`: 8 files changed, 56 insertions(+), 66 deletions(-). The flap fix costs +6 (the sentinel, its import and the check) and the refused-scan handling +5; the cuts gave back about 9.
