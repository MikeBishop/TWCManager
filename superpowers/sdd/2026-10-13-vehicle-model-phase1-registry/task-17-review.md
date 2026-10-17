# Task 17 review: BLE status on the vehicle page with a range scan (2b91330..aba5fff)

### Spec Compliance

**Mostly compliant, with two deviations.** The brief's interfaces are all present: `bleLocalName` (the test vector matches), `SCAN_SECONDS`, `scanForVehicleInRange` (`@_serialized`, argument list, timeout 12, process group, INFO log, `bleReach` observed with `seen=False`), `rangeStatus`, `requestRangeScan`/`runPendingScans` with coalescing per VIN, the extended `bleStatus` keys and labels, the `bleScan` background branch, the `/vehicle/localMgmt` `pair`/`scan` ops, the `bleStatus` template global, the template changes (registry row, `.get` chain for Charge Sessions, `BLEPeeringStatus` gone, Scan/Pair/Re-pair buttons, "(bluetoothctl not found)"), and the CHANGELOG line. The controller's extra requirements are also met: the `since` age and the last pairing attempt's message are shown, user text is autoescaped (tested), the scan runs only on the background thread under `_bleLock`, and "proven" never appears.

The two deviations:
1. The brief says `pending` is "cleared by the scan". The code clears it when the request is *dequeued*, before the scan starts (Important #2).
2. "Range unknown" should cover the cases where no scan is possible or none has run. A scan that *failed* (timed out, or no adapter) is reported as "Not in range" instead (Important #1).

Step 6 (the live check) was only partly done. The implementer gave a reason (the box is busy testing 1.3.4), and the controller should decide whether to run it later.

Focused tests: 66 passed (`test_teslable_pairing_status.py`, `test_vehicle_detail_page.py`, `test_vehicles_page.py`). I also ran a scratch probe outside the tree to check #1 and #2. The tree was not modified.

### Strengths

- The HTTP handler validates the VIN before using it (`HTTPControl.py:55`, `isWellFormedVIN` uses `fullmatch` on `[A-HJ-NPR-Z0-9]{17}`). That closes the CRLF-in-`Location` path, and the CRLF case is tested. The handler logic was moved into a testable module function.
- Coalescing is right. `runPendingScans` loops until the request map is empty, so a request that arrives mid-run, which the queue coalesces away, is still served (tested). `_scanLock` is never held while `_bleLock` is taken.
- The `[DEL]` filter and ANSI stripping (aba5fff) cover the obvious stale-cache line types. The MAC fallback is grounded in an observation from the live box.
- The scan never creates a registry vehicle (tested). The `bleReach` observation is not counted as a sighting.
- Internal callers moved to `_storedStatus`, so the richer `bleStatus` (which calls `canScan`, `shutil.which`, and reads the attempt) is not on the command path.
- Subprocess calls are argument lists with no shell. The VIN never reaches argv: the scan argv is constant, and only the SHA-1-derived local name is compared in Python.
- Log lines contain only the VIN and exception class names. No key material is logged.

### Issues

#### Critical
None.

#### Important

1. **A failed scan reads as "Not in range" and records `bleReach=False`.** `TeslaBLE.py:1682-1708`. On a timeout, `_run_command_with_timeout` returns `(None, None, None)`. The code turns that into `output = ""` and then `inRange = False`. The return code is ignored, so a nonzero exit or error output ("No default controller available", bluetoothd down, adapter powered off) is also treated as a clean miss. My probe confirmed both cases:
   - Timeout gives `False`, label "Not in range", `bleReach False`.
   - Exit 1 with "No default controller" gives "Not in range".

   This answers named risk (c). The scan did not happen, so the result should be unknown, as the controller's "Range unknown" requirement says. Nothing consumes `bleReach` yet (`Fields.py:32` is its only other reference). Still, a false negative recorded as an observation will mislead whatever transport selection reads it later, and today it misleads the user while they troubleshoot pairing.

   Fix:
   - **Timeout (`stdout is None`):** definitely unknown. Store `{"inRange": None, "at": now}` (or keep the previous result), return `None`, skip the `bleReach` observation, and log at WARNING.
   - **Nonzero exit:** first check on the box what a *healthy* `bluetoothctl --timeout 8 scan on` exits with. If a scan cut off by its own timer exits nonzero, gating on `code != 0` would turn every good scan into "Range unknown". Until that is confirmed, gate on nonzero code *and* no match, or detect the error text.

   Add a test for each case.

2. **"Scanning…" is effectively never shown.** `TeslaBLE.py:1744-1750` together with `rangeStatus` at `:1722`. `pending` comes only from `_scanRequests`, which `runPendingScans` clears before it scans. The background thread blocks in `Queue.get` (`TWCMaster.py:379`), so it usually takes the request within milliseconds, before the browser has followed the 302. The page that follows the redirect therefore shows the old label (often "Range unknown") with the Scan button enabled, for the whole 8 s scan. My probe saw `pending` as `False` *during* the scan.

   The brief says pending is "cleared by the scan", and the controller asked for the disabled "Scanning…" state. As built, the user gets no feedback and is likely to click again, which queues another 8 s scan that holds `_bleLock` (see #3).

   Fix: keep an in-progress set under `_scanLock`. Add the VINs to it *inside the same `_scanLock` critical section* as the snapshot-and-clear of `_scanRequests`. Otherwise there is a window in which the VIN is in neither map and `pending` reads False. Remove each VIN in a `finally` after its scan. Report `pending` when the VIN is requested or in progress. The 120 s expiry can stay as a safety net. Add a test in which the mocked scan asserts `rangeStatus(vin)["pending"]` is True.

#### Minor

3. **Lock hold and starvation, named risk (b).** One scan holds `_bleLock` for about 8 s, plus up to 5 s for `bluetoothctl devices` on the fallback path. The worst case is 12 + 5 s when both time out. Vehicle commands (charge start/stop/amps) run on the vehicle-command worker (`VehicleCommandQueue.py`), not the serial thread, so the RS-485 loop is unaffected. Charge commands and presence probes wait up to one scan. The lock is released between VINs, but Python's `Lock` is not fair, so a worker waiting during a multi-VIN or repeated-click run may lose the race repeatedly.

   This is acceptable for a scan that only a user starts and that is rare. Fixing #2 removes the main cause of repeated clicks. Optionally, skip a VIN whose last scan is under about 10 s old.

4. **MAC fallback attribution and staleness, named risk (a).** A MAC is tied to a VIN only through `bluetoothctl devices` listing that MAC with the exact alias `bleLocalName(vin)`. That alias is a 64-bit SHA-1 prefix of the VIN, so attributing another car's MAC requires a hash collision, which is negligible.

   Staleness: the MAC only has to appear *somewhere* in the scan output that is not on a `[DEL]` line (`TeslaBLE.py:1702`). On 5.82 the evidence (one name match, four MAC-only matches) shows that cached devices are not reprinted at startup. But a `[CHG] Device <MAC> RSSI is nil`, `Connected: no`, or `ServicesResolved: no` line could mention a car that is not advertising. Such lines come, for example, from another discovery client stopping or from tesla-control's connection teardown arriving late. Older BlueZ releases that print `[NEW] Device` for cached devices at startup would make both the name match and the MAC match false positives. That risk applies to the brief's name match too, not only the fallback.

   Tightening: match only `[NEW] Device <MAC>` lines, and `[CHG] Device <MAC> RSSI:` lines that carry a numeric value. Low priority.

5. **`TeslaBLE.py:1724`: `_rangeScan` is read without a lock.** Individual dict operations are atomic in CPython, and the values are replaced whole rather than mutated, so this is fine. A one-line comment would help.

6. **`vehicleDetail.html.j2:118`: "(bluetoothctl not found)" is also shown under Docker**, where `canScan` is False even though bluetoothctl may be installed. Something like "(scanning unavailable)", or deciding the reason from `isDocker()`, would be more accurate.

7. **The background thread is blocked for the length of the scan.** Other background tasks (saveSettings, webhook, updateStatus, `vehicleIsDefinitelyHome`) wait about 8 s per VIN. Background tasks are already best-effort, so this is noted only.

8. **Named risk (d), second half.** "Pair" still calls `peerWithVehicle` synchronously on the HTTP thread, which holds the thread and `_bleLock` for up to 30 s. This is pre-existing and the brief keeps it. It should be tracked for a later phase: the pair op could be queued like scan.

9. **Concern 4 from the report (the race between the last empty check and `doneBackgroundTask`) is real but bounded.** The pending marker expires after 120 s and a re-click recovers. If #2 is fixed with an in-progress set, re-check `_scanRequests` after `doneBackgroundTask`, or simply re-queue when the map is non-empty after the loop. Optional.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The structure is sound. The threading model (HTTP only queues; the scan runs on the background thread under `_bleLock`; `_scanLock` is a leaf), the VIN validation that closes the header-injection path, the use of argument lists only, and the clean logs all check out against the named risks.

Two fixes are needed before this can be trusted:
- A scan that failed or timed out is reported and recorded as "Not in range" / `bleReach=False`, which contradicts the "Range unknown" rule and puts false negatives into the registry.
- The "Scanning…" pending state is cleared before the scan runs, so the page almost never shows it, against the brief's "cleared by the scan".

Both are small, local changes to `scanForVehicleInRange`/`runPendingScans`, each with one test. The live check (Step 6) is still owed.
