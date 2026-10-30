# Task 6c review: d94a92ba..baa5ac78

Spec compliance: PASS with one fix recommended (startup gap, item 3).
Quality: APPROVE WITH FIXES (I1, I2; the rest are minor).

Tests were not re-run here (no pytest in this environment); the report states 2328 passed. black --check is clean on the three touched Python files.

## 1. The two extra fixes

(a) nsenter. At base, all three tesla-control sites inserted one argv element (`"nsenter --net=/rootns/net "` at pairing/command, `"nsenter --net=/rootns/net"` in `_tool`). The only exec path is `subprocess.Popen(command_string, ...)` in `_run_command_with_timeout`, with no `shell=True` anywhere in `lib/TWCManager/Vehicle/`. (The one other subprocess call is `dbus-launch --sh-syntax`, which is not tesla-control.) Popen would raise FileNotFoundError for an executable named that whole string. The `except Exception` caught it and returned (None, None, None). So tesla-control could never have run in Docker. Confirmed.

The new wrap is in one place, `_run_command_with_timeout`, and applies only in Docker and only when `argv[0] == self.binaryPath`. It uses separate args `["nsenter", "--net=/rootns/net", ...]`. `grep binaryPath` finds exactly three command builders: add-key-request (pairing), `sendCommand`'s `_sendCommand_internal` (every command), and `_tool`. `_tool` covers ping/body-controller-state and the state reads (`_fetch_state_json`). All three go through `_run_command_with_timeout`. bluetoothctl (`show`, `scan on`, `devices`) has argv[0] `"bluetoothctl"` and is never wrapped. The compose file already mounts `/proc/1/ns/:/rootns` and grants CAP_SYS_ADMIN, and the Dockerfile installs util-linux (nsenter). Complete.

(b) killpg. At base, `preexec_fn = os.setsid` only `if use_process_group and not self.isDocker()`. The timeout path did `os.killpg(os.getpgid(result.pid), SIGTERM/SIGKILL)` whenever `use_process_group` was set. Without setsid, the child inherits TWCManager's pgid, so a timed-out command in Docker would have signalled TWCManager's own group. It was latent only because nothing timed out in Docker: tesla-control failed at exec, and the scan path was excluded. Now setsid runs whenever `use_process_group` is set (the default, which every caller uses). No other `isDocker()` branch remains on the exec path. The remaining uses are the readiness reason text and the nsenter wrap. Confirmed.

## 2. Readiness check

- Cached: `canScan()` takes `_scanLock` and reads `_scanBlocked/_scanCheckAt`. When a check is due, it stamps the time and calls `submitJob("radio","check",...)`, a non-blocking `VehicleCommandQueue.put`. Its key `("radio","check")` is distinct from the scan job's `("radio","scan")`, so they don't coalesce. bluetoothctl never runs on the caller. OK.
- Re-check while not ready: `blocked and elapsed >= 600`. OK, and tested at 599/600.
- A working adapter failing later: SCAN_ERROR_TEXT in a scan clears `_scanCheckAt`, so the next canScan queues a check. OK.
- Reason mapping against real output. "No default controller available" maps to no controller. "Powered: no" maps to off/rfkill; newer BlueZ also prints `PowerState: off-blocked`, and "Powered: no" still matches. Without a reachable bluetoothd, bluetoothctl prints "Waiting to connect to bluetoothd..." and blocks, so the 5 s timeout yields (None, None, None), which maps to the Docker D-Bus reason or the host "bluetoothd is not answering". "Unable to open mgmt_socket" in Docker is ignored, because "Powered: yes" still matches. OK.
- Logging: WARNING when the reason first appears or changes, INFO on recovery only when there was a prior reason (not on the first success). OK and tested.

## 3. Startup gap: matters a little; fix recommended

Before the first check completes, `canScan()` is False with reason "". The window lasts until the check reaches the front of the BLE worker queue. That can be minutes, not "a tick or two", if commands with retries are queued ahead of it. The first canScan call often comes from inside a worker job, and the job queues the check behind itself. Effects:
- `Watch._source` ping closure: on a second miss while away, if `not scans(ble)` the car is marked `bleReach False` (lost) without a scan, because `scanForVehicleInRange` returned None for "unchecked". The car is declared lost one round early. Mild: the lost path is the designed fallback, and a scan later finds the car.
- `Watch._visit` locate. `located` starts at NEVER, so `late` is true on the first passes. For an away-awake car whose cloud READ_CHARGE price is > 0, `not scans(ble)` buys one **paid** location read per restart that a working scanner would have avoided. This is the one with real cost.
- `Watch._visit` scan-due path: submits a ping instead of requesting a scan. Harmless.
- Page: neither button nor reason. Harmless.

Smallest fix (about 2-3 lines): queue the check eagerly so it is the worker's first job. Do this by calling `self.canScan()` at the end of `TeslaBLE.__init__`; `master.reconciler` exists from TWCMaster init, and the queue accepts before `start()`. Also, in `scanForVehicleInRange` (already on the worker under `_bleLock`), run `self._checkScan()` inline when `self._scanBlocked == ""`. That closes the ping path entirely and narrows the locate window to the first seconds after start. An alternative, a tri-state where `scans()` treats unchecked as "can scan", is wider and changes `canScan`'s meaning.

## 4. Dockerfile, docs, page

- Dockerfile: `bluez` added to the apt line. OK.
- Docs: one paragraph covering host needs, the Docker image/mount/env, and the warning, page reason, and 10-minute re-check. Accurate. OK.
- Page: `{% elif status.get("scanBlocked") %}<small>No range scan: …</small>` in the existing BLE action cell. Jinja autoescape applies as for the other status fields. "" (unchecked) shows nothing. OK and tested both ways.

## 5. Tests, comments, size

- Each rule has a test that fails when it is removed. Tests cover: each reason (parametrized), the check not run on the caller, warn-once, INFO-once, the 600 s gate with a single submit, a passed check not re-run by time, a scan error triggering a re-check, Docker argv with nsenter only for tesla-control, setsid in Docker, and the page. The mutation list in the report matches what the asserts pin.
- Comments: why-not-history throughout, with no task or ruling IDs added. ("# Task 17" in the tests is pre-existing.) The trimmed `_run_command_with_timeout` docstring is fine.
- Lib +31 against ≤ +30, and the duplicate inserts were removed. Acceptable. Fix I1 adds about 1 line.

## Findings, ranked

- **I1 (Important): startup gap.** It costs a paid cloud locate per away-awake car per restart, and can mark a car lost without a scan. Fix: queue the check from `__init__`, and run `_checkScan()` inline in `scanForVehicleInRange` when the result is unchecked (`""`).
- **I2 (Important): a lost first check is permanent.** If the queued check is dropped, `canScan` stays False forever with no reason, logs nothing, and the page is silent. This happens when `put` returns False, when an overflow at MAX_PENDING=64 drops the oldest low entry, or when `_checkScan` raises. The cause is that `due` requires a truthy `blocked`. Fix: `due = at is None or blocked is not None and time.time() - at >= self.SCAN_RECHECK`, so "unchecked" also retries after 10 min. Optionally, clear `_scanCheckAt` when `submitJob` returns False.
- M1 (Minor): a scan that times out (stdout None) doesn't trigger a re-check. Only SCAN_ERROR_TEXT does. If bluetoothd dies so that `scan on` hangs past `--timeout`, a "ready" adapter is never re-checked. Consider also clearing `_scanCheckAt` on `failure == "timed out"`.
- M2 (Minor): the nsenter and killpg changes alter tesla-control in Docker (it was dead before). They have not been run on real Docker. Smoke-test pairing, a command, and a forced timeout on the Armbian box before release.
- M3 (Minor): lib +31, one over target. Acceptable given the duplicate removal.
