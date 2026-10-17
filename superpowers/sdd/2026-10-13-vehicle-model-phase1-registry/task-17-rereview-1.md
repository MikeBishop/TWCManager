# Task 17 re-review 1 (fix aba5fff..2d872e4)

### Finding Verdicts

- **Important #1: a failed scan reads as "Not in range". ADDRESSED.** `TeslaBLE.py:1712-1740`.
  - A timeout (`stdout is None`, :1713) gives `failure`.
  - With no match, known error text in stdout or stderr gives `failure` (:1716-1718).
  - With no match, a nonzero exit gives `failure` (:1719-1722).
  - On failure the code stores `{"inRange": None, "at": now}`, logs a WARNING, returns None, and records no `bleReach`.
  - A match wins over any exit code or error text, because the error checks are gated on `not inRange`.
  - My probe confirmed: timeout gives None and "Range unknown"; exit 1 with no match gives None; a name match with exit 1 plus "No default controller" gives True.
- **Important #2: "Scanning…" is never shown. ADDRESSED.**
  - `_scanInProgress` is filled in the same `_scanLock` section as the snapshot-and-clear (:1821-1825) and discarded in a per-VIN `finally` (:1832-1835).
  - `pending` is in-progress OR requested within `SCAN_PENDING_MAX` (:1789-1790).
  - The 10 s debounce is at :113 and :1806-1811. Unknown results also set `at`, so they debounce too.
  - Tests cover pending being True during the mocked subprocess call and False after, including when the scan raises.
  - I checked the body of `test_scan_is_pending_while_it_runs` (test file :730-743). It records `rangeStatus(VIN)["pending"]` inside the mocked `_run_command_with_timeout`, when `_scanRequests` has already been cleared. The pre-fix code would fail it.
- **Minor #4: MAC fallback. ADDRESSED.**
  - `_HEARD_RE` (:1754) accepts only `[NEW] Device <MAC>` lines and `[CHG] Device <MAC> RSSI: <-?digits | 0xhex>` lines.
  - `RSSI is nil`, `Connected: no`, `ServicesResolved: no`, `TxPower` and a bare `Device` line are tested negatives.
  - Comparison is case-insensitive (both sides upper-cased).
  - `bluetoothctl devices` now runs only when something was heard.
- **Minor #6: label. ADDRESSED.** `vehicleDetail.html.j2:118` reads "(scanning unavailable)", and the test is updated.
- **Minor #9: re-queue. ADDRESSED.**
  - `TWCManager.py:410-418` calls `requeueIfRequested` (`TeslaBLE.py:1837`) after `doneBackgroundTask`, only for a `bleScan` task, wrapped in try/except. It queues at most one task, and only when `_scanRequests` is non-empty.
  - The implementer's reason it cannot live inside the drain is correct. Until `doneBackgroundTask` deletes the `backgroundTasksCmds` key, `queue_background_task` merges the task into the still-registered entry and never calls `put` (`TWCMaster.py:1330-1336`).
  - The glue is placed outside the dispatch try, at the same level as `doneBackgroundTask`, so it runs even if the scan task raised.
- **Minor #5: comment on the unlocked `_rangeScan` read. ADDRESSED.** :1784-1785, with a cross-reference at :1805.

**Safety fix: VERIFIED BOUNDED.** `runPendingScans` is now `for _ in range(SCAN_DRAIN_PASSES)` (:1820), so the whole drain is at most 3 passes over the snapshot taken in each pass. I checked the production paths:

- **Same VIN re-requested from another thread on every scan.** While the VIN is being scanned, the request is dropped (:1808). Once the scan finishes, it has set `_rangeScan[vin]["at"]`, so the debounce drops it for 10 s.
  - Probe: a thread calling `requestRangeScan(VIN)` in a tight loop against the real `scanForVehicleInRange` (subprocess mocked) produced exactly one subprocess call, and `requeueIfRequested` queued nothing.
- **Same VIN hammered when the scan fails fast and leaves no `_rangeScan` entry** (it raises, or `canScan` is False). There is no debounce on this path, but the pass cap holds.
  - Probe: no more than `SCAN_DRAIN_PASSES` scans per task.
- **Across tasks.** `requeueIfRequested` adds at most one coalesced task, and only when a request exists, so further cycles happen only while new requests keep arriving.
  - The only production caller of `requestRangeScan` is `HTTPControl.py:66`, which runs on a user's click. No timer, poller or background task calls it.
  - Even on the fast-fail path, where there is no debounce, the number of cycles is therefore bounded by user clicks, not by code.
  - Memory cannot grow: `_scanRequests` is keyed by VIN, `_scanInProgress` is a set, and the queue coalesces the `bleScan` key.
- **Other loops in the area.** I found no `while` loop in the scan, range or requeue code. `background_tasks_thread`'s `while True` blocks on `getBackgroundTask`, as it did before. `_run_command_with_timeout` is bounded by `communicate(timeout=)`.

Tests: the 3 focused files gave 90 passed in 1.08 s, under `MemoryMax=2G`, `timeout 300` and `--timeout=60`. A scratch probe outside the tree (`scratchpad/probe17`) gave 3 passed. The tree is clean and HEAD is 2d872e4.

**A full-suite run was stopped by its timeout.** I also tried an optional run of all of `tests/` under the same wrapper. The 300 s `timeout` killed it (exit 143), and the output was only "Terminated", so I cannot tell whether a test hung or the run was just slow. Afterwards no pytest process was left and memory was normal (about 2 GB used out of 16 GB), so the cap worked. As the brief requires, I stopped there and did not rerun it. The implementer reports 1123 passed. The controller may want a full run with `-x --durations` or split by directory to confirm that nothing hangs. The verdict below rests on the focused files and the probe.

**The implementer's call: a `bluetoothctl devices` timeout after candidates were heard gives "unknown". AGREE.** Addresses were heard, but whether one of them is this car cannot be decided. "Not in range" would be a false negative of the same kind as Important #1. It is tested.

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
1. **The healthy exit code of `bluetoothctl --timeout 8 scan on` is still unconfirmed** (the implementer flags this too). If a clean run exits nonzero, every miss reads "Range unknown" instead of "Not in range"; a match is unaffected. Check this in the Step 6 live check.
2. **A nonzero exit from `_bluezAddresses` with non-None stdout gives an empty set**, so the result is "Not in range" rather than unknown. This is a narrow case: candidates were heard, but `devices` failed without timing out. Low priority.
3. **A scan that raises, or a `canScan` False return, sets no `_rangeScan` entry**, so the debounce does not apply. Repeated clicks re-queue cheap no-op tasks, which is harmless.
4. **The unlocked `last` read in `requestRangeScan` can admit one extra scan.** If the scan finishes between that read and the lock, the request is accepted. This is benign.
5. **No unit test covers the `TWCManager.py` glue**, as the implementer disclosed. The glue is two lines and inspection shows it is correct.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage
