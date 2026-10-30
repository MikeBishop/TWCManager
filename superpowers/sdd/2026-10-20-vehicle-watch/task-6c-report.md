# Task 6c report: range scans from Docker, and why none is possible

Status: DONE. Commit baa5ac78 on vehicle-model/phase6 (wt-vm6), base d94a92ba. Not pushed.

## Tests
Full suite: 2328 passed, 1 xfailed (BASE 2319 passed, 1 xfailed; +9 new test cases).
Lib (*.py under lib/): 26932 -> 26963 (+31; target <= +30).

## What changed
- contrib/docker/Dockerfile: `bluez` added to the apt install.
- TeslaBLE.canScan(): reads a cached result only (`_scanBlocked`, `_scanCheckAt`, under `_scanLock`). When a check is due (never run, or failed >= SCAN_RECHECK=600 s ago) it queues `("radio", "check")` on the BLE worker via reconciler.submitJob and returns the cached answer. It never runs bluetoothctl on the caller, so the control tick (Watch.scans) stays cheap. Before the first check it says False (reason "" = not checked yet; nothing shown on the page, nothing logged).
- TeslaBLE._checkScan() (BLE worker): `bluetoothctl show`, 5 s timeout, no nsenter. Reasons: not installed; "No default controller" -> no controller; "Powered: yes" -> ready; "Powered: no" -> powered off/rfkill; otherwise in Docker -> the /run/dbus + DBUS_SYSTEM_BUS_ADDRESS reason, outside Docker -> "bluetoothd is not answering" (a fifth reason the brief didn't list, for a host where bluetoothd is down). WARNING once per new or changed reason ("...; arrival detection falls back to slower checks"); INFO "BLE range scans available again" once on recovery (not on a first-run success).
- A ready adapter isn't re-checked on a timer. Instead, a scan that hits SCAN_ERROR_TEXT (no controller, bluetoothd down, discovery refused) clears `_scanCheckAt`, so the next canScan() queues a fresh check. That covers an adapter that goes away after startup.
- bleStatus() adds `scanBlocked`. vehicleDetail.html.j2: when no scan is possible, the Scan button is replaced with `<small>No range scan: {reason}</small>` in the existing BLE Control Action cell.
- docs/modules/Vehicle_TeslaBLE.md: a FAQ paragraph on what range scans need (host and Docker) and what the warning and page reason mean.

## isDocker() branches on the scan path (reviewed as the brief asked)
1. **Pre-existing bug, fixed:** all three tesla-control call sites did `insert(0, "nsenter --net=/rootns/net ")`, which is a single argv element. Popen would look for an executable literally named that, raise FileNotFoundError, and get swallowed as (None, None, None). So tesla-control could not have run in Docker at all. The nsenter wrap now happens once, in _run_command_with_timeout, as separate args, and only when argv[0] is binaryPath. bluetoothctl is never wrapped. This also removed the three duplicated inserts (part of how lib growth stayed near +30).
2. **Pre-existing bug, fixed:** in Docker, setsid was skipped, but the timeout path still called `os.killpg(os.getpgid(child))` when use_process_group was set. Without setsid, that group is TWCManager's own, so a timed-out command in Docker would SIGTERM/SIGKILL TWCManager itself. setsid works fine in containers (it's an unprivileged syscall), so the Docker exclusion is gone and every child gets its own group, killed as a whole on timeout.
- The verbose _run_command_with_timeout docstring was cut to two lines, and a redundant `use_process_group=True` (the default) was dropped from the scan call.

## Tests added (tests/unit/test_teslable_pairing_status.py, test_vehicle_detail_page.py)
- Docker + bluetoothctl + "Powered: yes" -> canScan True; the check's argv is exactly ["bluetoothctl","show"]; the scan runs bluetoothctl directly.
- Parametrized over each reason (not installed, no controller, powered off in Docker, D-Bus silence in Docker, bluetoothd silent on the host): canScan False, bleStatus.scanBlocked == reason, scanForVehicleInRange returns None without running anything. Each case also asserts the check is only queued by canScan and runs when the worker drains.
- Logging sequence off, off, gone, gone, ready, ready, off -> exactly WARNING(off), WARNING(gone), INFO, WARNING(off).
- Re-check: not queued at +599 s, queued once at +600 s even when asked twice.
- Ready check not re-run by time alone; a scan reporting "No default controller" makes the next canScan queue one.
- Docker Popen argv: tesla-control under ["nsenter","--net=/rootns/net",...], bluetoothctl bare, preexec_fn set for both.
- Page: the reason replaces the Scan button; no reason -> button shown.
- scanner() helper now seeds a passed readiness check (existing scan tests unchanged otherwise). The old test_scan_unavailable_in_docker (which asserted the opposite rule) and test_scan_unavailable_without_bluetoothctl were replaced by the above.
- Mutation-checked: dropping the dedupe, the recovery guard, the 600 s gate, the in-flight stamp, the scan-error reset, the binaryPath condition on nsenter, or a reason's match text each fails at least one test.

## Concerns
- Lib +31, one over the +30 target.
- canScan() is False for the short time between startup and the first check finishing on the worker. During that window, Watch takes its slower non-scan path for a tick or two, and the page shows neither the button nor a reason.
- The nsenter and killpg fixes change tesla-control behaviour in Docker (it was broken before). Neither has been tried on a real Docker host; worth a run on the Armbian Docker box where the evidence came from.
- canScan() calls master.reconciler.submitJob from whatever thread asks (tick, HTTP). That is a non-blocking queue put, at most once per due check.

## Fix round 1 (review I1, I2, M1); amended into a single commit
- I1: the end of TeslaBLE.__init__ calls canScan(), which queues the readiness check as early as possible on the BLE worker. scanForVehicleInRange already runs on the worker. When the result is still unchecked (`_scanBlocked == ""`) and a VIN was asked for, it runs `_checkScan()` inline before deciding. So a scan or ping never answers None just because the check hasn't run yet.
- I2: `due = at is None or blocked is not None and elapsed >= SCAN_RECHECK`. A dropped or raised first check is now retried after 10 minutes instead of never.
- M1: both "timed out" and "bluetoothctl reported an error" now clear `_scanCheckAt`, so the next canScan queues a check.
- New tests: test_startup_queues_the_check, test_a_scan_before_the_check_ran_checks_first, test_an_unchecked_result_is_retried_after_ten_minutes, and test_a_passed_check_is_not_rerun_until_a_scan_fails (now parametrized over no-adapter and timed-out). Mutation-checked: removing each of the four rules fails one test.
- tests/unit/test_reads_no_wake.py: its FakeMaster gets `reconciler = Mock()`, because TeslaBLE init now queues the check. A production TWCMaster creates its reconciler before modules load. That file was already not black-clean, so only the added line is formatted; black's unrelated reformatting was left out.
- Full suite: 2332 passed, 1 xfailed. Lib 26932 -> 26971 (+39).
- M2 (a live Docker smoke test of tesla-control's nsenter and killpg paths) is still to do.
