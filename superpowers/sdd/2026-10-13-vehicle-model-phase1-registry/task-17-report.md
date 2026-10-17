# Task 17 report: BLE status on the per-car page with a range scan

**Status:** DONE (one commit; full live-deploy check not run, see Concerns)
**Commits:** b0d3d00, aba5fff on vehicle-model/phase1 (parent 2b91330)
**Tests:** 1099 passed (was 1075; +24). All the brief's tests are in, verbatim apart from black formatting and a `scanner()` helper that pins `isDockerCached = False`.

## What changed

- `TeslaBLE`
  - `bleLocalName(vin)` (static): `"S" + sha1(vin.upper())[:16 hex] + "C"`.
  - `SCAN_SECONDS = 8` and `canScan()`: false in Docker or when `shutil.which("bluetoothctl")` finds nothing (ruling 7).
  - `scanForVehicleInRange(vin)` is `@_serialized`. It runs `bluetoothctl --timeout 8 scan on` (timeout 12, process group), stores `_rangeScan[VIN] = {inRange, at}` and logs `BLE scan for <vin>: in range|not in range` at INFO. If the vehicle is already in the registry, it observes `bleReach` (source TeslaBLE, `seen=False`). It never creates a vehicle. Unavailable or malformed VIN gives None.
  - **Live-box finding (beyond the brief):** BlueZ prints a device's name only the first time it learns it. A car BlueZ already knows (from an earlier scan, or from tesla-control) shows up in later scans by MAC only, as `[CHG] Device <MAC> RSSI` lines. So when the name is missing from the output, the scan runs `bluetoothctl devices` (still under `_bleLock`) and checks whether the car's MAC appears in the scan output. On the box I ran this five times in a row with the 8 s scan while the car was plugged in. Results: name match once, MAC match four times. Without the fallback, the last four would have read "Not in range". bluetoothctl does not reprint cached devices when it starts, so the cache gives no false positives. Covered by `test_scan_finds_a_car_bluez_already_knows_by_address`.
  - `rangeStatus(vin)` → `{inRange, at, pending}`. `pending` comes from the request map, not from the scan itself, and stops showing after `SCAN_PENDING_MAX` = 120 s, so a lost request can't disable the button forever.
  - `requestRangeScan(vin)` checks the VIN and records it in `_scanRequests` (a dict of VIN → request time under its own `_scanLock`, never held while `_bleLock` is taken). It then queues `{"cmd": "bleScan"}`.
  - `runPendingScans()` loops until the request map is empty: snapshot and clear under `_scanLock`, then scan each VIN. A request that arrives mid-run, which the queue coalesces away, is still served (tested).
  - `bleStatus(vin)` now returns `status`, `since`, `label`, `sinceAge`, `inRange`, `scannedAt`, `lastScanAge`, `scanPending`, `canScan`, and `attempt` (the `blePairingAttempt` result with an `age` added). Ages are computed server-side. Internal callers now use the new `_storedStatus()`, which holds the old two-key behaviour. `test_status_default_and_copy` was changed to check only those two keys.
  - aba5fff (advisor finding): before matching, the scan strips ANSI colour codes and drops `[DEL]` lines. BlueZ prints `[DEL] Device <MAC> <name>` when it forgets a device, so a car that just left would otherwise match by name or MAC and read as in range. Tested.
- `TWCManager.background_tasks_thread`: a `bleScan` branch calls `ble.runPendingScans()`.
- `HTTPControl`:
  - New module function `vehicleLocalMgmt(master, op, vin)`, which the `/vehicle/localMgmt` handler now calls. It returns a redirect location. A malformed VIN redirects to `/vehicles` without calling the module (this closes a CRLF-in-`Location` path). `pair` calls `peerWithVehicle`, `scan` calls `requestRangeScan`, and both cope with no TeslaBLE module.
  - New template global `bleStatus`.
- `vehicleDetail.html.j2`:
  - A registry row (name, tier, providers, last seen) whenever the registry holds the VIN.
  - Charge Sessions is read with `.get` chains, so a car with no history renders.
  - The BLE panel shows: Status label (plus "(bluetoothctl not found)" when Range unknown and no scan is possible), "since <age>", the last pairing attempt's message and age, Last scan age, a "Scan for vehicle" button (disabled "Scanning…" while pending, hidden when no scan is possible), and Pair or Re-pair (Re-pair for `paired`/`refused`).
  - `BLEPeeringStatus` lookups, "Not Implemented", the stray `</b>` and the stray `</form>` are gone.
  - Everything goes through autoescape, and a test checks that the attempt message is escaped.
- CHANGELOG Features line as specified.
- Black ran only on touched .py files; all were black-clean at HEAD.

## Concerns

1. **Step 6 live check was only partly done.** The box is in the middle of 1.3.4 pre-tag testing (`port-fleet-wake-poll-1.3.4`), so I did not deploy phase 1 there. What I did on the box: ran bluetoothctl scans directly (BlueZ 5.82; car S2ed7c182378b75f6C). That led to the address-fallback fix above, and the journal showed no BLE errors during the scans. Still to check: a page round trip, no RS-485 stall during a queued scan, and pair → Paired through the page.
2. **8 s is mostly enough.** The car advertises weakly (RSSI −81 to −98). The first 8 s scan of the session missed it; every later 8 s scan found it (five out of five, four of them via the cached-address fallback). A first scan after BlueZ has forgotten the car can still miss; no need to investigate further unless users report it.
3. **A hung bluetoothctl reads as "Not in range".** On timeout, `_run_command_with_timeout` returns `(None, None, None)`, which the scan treats as not in range.
4. **Leftover queue race.** A request that arrives in the microseconds between `runPendingScans`'s last empty check and `doneBackgroundTask` gets coalesced and is not served. The pending marker expires after 120 s, and clicking again recovers.
5. **Pairing still blocks the HTTP thread.** `pair` still calls `peerWithVehicle` synchronously on the HTTP thread (up to 30 s under `_bleLock`). That is pre-existing and the brief keeps it.
6. **`rangeStatus` is in memory only.** It is lost on restart, so the page shows "Range unknown" until the next scan.

7. `registry.get()` returns None for a garbage VIN in the URL, so the new registry row cannot crash the page.

## Fix round 1

**Commit:** 2d872e4 (on aba5fff). **Tests:** 1123 passed (+24); the one warning is the existing urllib3 InsecureRequestWarning in `test_enphase_ems.py`. The first red run was uncapped and hung. I stopped it at 120 s and confirmed no pytest process survived and memory was normal. Every run after that used `systemd-run --user --scope -p MemoryMax=2G`, `timeout 300` and `--timeout=30/60`.

**OOM root cause, reproduced once and stopped:** a test that re-requests the same VIN from inside the mocked scan makes the old `runPendingScans` (`while True` until the map is empty) loop forever, and the test's list grows with every pass. My first red run (uncapped) did exactly this. This is almost certainly what crashed the VM last time. Fixes:
- The drain is now bounded to `SCAN_DRAIN_PASSES = 3`.
- Debounce makes a re-request of a VIN in progress a no-op.
- Each test mock that re-requests has a cap that raises a `BaseException` subclass (`Runaway`), so `runPendingScans`' per-VIN `except Exception` cannot swallow it.

Rulings:
1. **Unknown results.** `scanForVehicleInRange` returns None, stores `{"inRange": None, "at": now}` (this overwrites an earlier result, so the label flips to "Range unknown"), logs a WARNING and records no `bleReach` in these cases:
   - stdout is None (timeout);
   - no match and a nonzero exit;
   - no match and known error text in stdout or stderr: `no default controller`, `waiting to connect to bluetoothd`, `failed to start discovery`.
   A name or MAC match wins whatever the exit code.
   Judgement call: if the fallback's `bluetoothctl devices` times out while the scan heard candidate addresses, that is unknown too.
2. **Pending and debounce.** A `_scanInProgress` set is filled in the same `_scanLock` section that snapshots and clears `_scanRequests`, and each VIN is removed in a per-VIN `finally`. `pending` = in progress, or requested within `SCAN_PENDING_MAX`. `requestRangeScan` ignores a VIN that is in progress or was scanned in the last `SCAN_DEBOUNCE = 10` s; unknown results count as scanned. Tested: pending is True inside the mocked subprocess call and False after, including when the scan raises.
3. **MAC fallback.** It now uses only addresses from `[NEW] Device <MAC>` lines and `[CHG] Device <MAC> RSSI: <number>` lines (`-60` or `0xffffffb2 (-78)`), compared case-insensitively. Tested negatives: `RSSI is nil`, `Connected: no`, `ServicesResolved: no`, `TxPower: -4`, and a bare `Device <MAC>`. The name match is unchanged (any non-`[DEL]` line).
4. The label now reads "(scanning unavailable)".
5. **Re-queue.** It cannot live inside `runPendingScans`: until `doneBackgroundTask` runs, `queue_background_task` coalesces into the still-registered `bleScan` entry, and delayed tasks wait for the 30 s `get` timeout on an idle queue. `TWCManager.background_tasks_thread` now calls `ble.requeueIfRequested()` right after `doneBackgroundTask` for a `bleScan` task, wrapped in try/except. It queues at most one task per call, and only when `_scanRequests` is non-empty. Tested on the method: a drain with a request arriving during every scan stops after 3 passes and the post-task check queues exactly one follow-up; a single mid-scan request is served in the same drain and queues nothing. The two-line glue in `TWCManager.py` has no unit test (no background-thread harness).
6. A comment on the unlocked `_rangeScan` reads (in `rangeStatus` and `requestRangeScan`).

Remaining concerns:
- I did not confirm on the box what a healthy `bluetoothctl --timeout 8 scan on` exits with (the box is off-limits this round). If a clean run exits nonzero, every scan that does not hear the car reads "Range unknown" instead of "Not in range"; a match is unaffected. This should be checked during the Step 6 live check.
- Step 6 (the live check) is still owed.
