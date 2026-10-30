# Task 9: BLE jobs run on the BLE worker, not the background-task thread (user, 2026-10-19)

User: "task['cmd']=='bleScan' is made a background task because it can take seconds. But why put it on the background
task thread rather than the BLE thread? It's going to hold the BLE lock, so it will couple the two threads by blocking
both until it completes." Approved: move it.

## Today
- `TeslaBLE.requestScan` (~TeslaBLE.py:1140-1152) queues `{"cmd": "bleScan"}` on the background-task queue;
  `TWCManager.py` (~:381-384) runs `ble.runPendingScans()`, and after `doneBackgroundTask` (~:407-415) calls
  `ble.requeueIfRequested()`. `runPendingScans` drains `_scanRequests` up to `SCAN_DRAIN_PASSES` (~:77) because the
  background queue coalesces one bleScan task. `scanForVehicleInRange` is `@_serialized` (holds `_bleLock` ~8 s + kill margin).
- Gen2 VIN-less attribution (`Presence.attribute` via an `attributePlug` background task queued from TWCMaster) makes forced
  BLE reads on the background thread too.
- The reconciler owns per-lane `VehicleCommandQueue` workers (Reconciler.py ~:83); the BLE lane is the BLE worker.

## Required
1. Range scans and Gen2 attribution's BLE work run on the BLE worker thread, queued behind BLE commands; nothing BLE runs
   on the background-task thread any more.
2. Delete what only existed to fit the background queue: the `bleScan` background branch and its requeue hook, `requeueIfRequested`,
   `SCAN_DRAIN_PASSES` and the drain loop (keep the in-progress/debounce bookkeeping the vehicle page shows: "Scanning…",
   `scanPending`, SCAN_DEBOUNCE, SCAN_PENDING_MAX). Same for the attribution background task if it moves wholly.
3. Smallest entry point onto the BLE worker for a non-attempt job (e.g. a `submitJob(callable)` on the queue or reconciler,
   or a lane-keyed job the worker runs in order). It must not bypass the queue's ordering or `_bleLock`; a failing job is
   logged and never kills the worker; jobs coalesce per VIN (one pending scan per VIN), so a burst of page clicks or
   attribution requests queues once.
4. If the reconciler (and so the BLE worker) isn't running (e.g. BLE disabled, tests with no reconciler), the request is a
   no-op or runs where it ran before — choose the simpler and say which.
5. Behaviour unchanged otherwise: scan result semantics (definitive miss vs unknown), the page's auto-refresh while pending,
   attribution's outcomes, Gen3 never reading BLE.

## Constraints
- Net lib ≤ 0 (expect ≈ −20..−30). Comment rule; black; Python 3.8.
- Tests: scans run on the BLE worker thread (assert the thread / the queue used); a scan and a BLE command never overlap;
  a burst of requests for one VIN runs one scan; background-task thread never calls into TeslaBLE scan/attribution; the
  vehicle page pending state still clears; existing scan/attribution tests keep their assertions (rewrite only plumbing).
- Parity counts unchanged.
- Commit: "Run BLE scans and attribution reads on the BLE worker" + Co-Authored-By trailer.
