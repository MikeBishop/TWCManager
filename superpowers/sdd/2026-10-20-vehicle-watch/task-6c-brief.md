# Task 6c: Range scans in Docker, and a warning when no scan is possible

Added by the controller (user, 2026-10-20: "Now, yes." — fix and warn).

## Evidence (verified 2026-10-20 on an Armbian/Ubuntu 24.04 aarch64 host with Docker 29 and BlueZ)

An **unprivileged** container works:
- Setup: no extra capabilities and no host network. The image is ubuntu:24.04 plus the `bluez` package. It has only `-e DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket -v /run/dbus:/run/dbus:ro`, exactly as contrib/docker/docker-compose.yml already sets.
- Result: `bluetoothctl list`, `bluetoothctl --timeout 10 scan on` (24 NEW/CHG lines, the same as the host's 26) and `bluetoothctl devices` all ran against the host's bluetoothd over D-Bus.
- `bluetoothctl` prints "Unable to open mgmt_socket" in the container. It is harmless: the scan goes through D-Bus.

On that host the adapter first came up soft-blocked by rfkill and unpowered: `bluetoothctl show` → `Powered: no`, and `scan on` → `org.bluez.Error.NotReady`. Our scan then gives no answer. That is a real-world case the warning should name.

## Behaviour

1. **Docker scans.**
   - Add `bluez` to the apt install line in contrib/docker/Dockerfile.
   - `TeslaBLE.canScan()` stops excluding Docker. It is True when `bluetoothctl` is installed and its one-time readiness check passes (item 2), in or out of Docker.
   - `bluetoothctl` must NOT be wrapped in `nsenter` (it talks D-Bus over the mounted socket). `tesla-control` keeps its nsenter.
   - Check every other `isDocker()` branch in the scan path (e.g. `use_process_group`) for whether it still applies.
2. **One readiness check, cached, with a reason.**
   - On first use, run `bluetoothctl show` (short timeout) and record the result:
     - `None`: ready.
     - a reason string: `"bluetoothctl not installed (install the bluez package)"`, `"no Bluetooth controller visible to bluetoothd"`, `"Bluetooth adapter is powered off or blocked (rfkill)"`, or, in Docker, `"bluetoothctl cannot reach the host's bluetoothd (mount /run/dbus and set DBUS_SYSTEM_BUS_ADDRESS)"`.
   - Re-check at most every 10 minutes while not ready, so a later `rfkill unblock` or power-on is picked up without a restart.
   - Never run the check on the serial thread or the control tick: it runs where scans run, on the BLE worker. It may also run once at module load on a background thread if that is simpler. Don't block startup.
3. **Warn.**
   - Log one WARNING when the reason first appears or changes, naming the reason and that arrival detection falls back to slower checks.
   - Log INFO once when scanning becomes possible again.
   - Show the reason on the Vehicles page where the "Scan for vehicle" button is: replace the button with the reason when no scan is possible. Reuse the page's existing BLE status area; keep it to a line or two.
   - docs/modules/Vehicle_TeslaBLE.md: one short paragraph on what range scans need (bluez and bluetoothd on the host; in Docker, the image's bluez plus the /run/dbus mount and env from the compose file) and what the warning means.
4. Everything that uses `canScan()` keeps its meaning. The watch's lost-car path and the page's scan state need no other change.

## Tests

- `canScan()` in Docker with `bluetoothctl` present and `show` answering Powered: yes → True; the scan command line has no nsenter.
- Each reason, from fake `shutil.which` / `bluetoothctl show` outputs: not installed, no controller ("No default controller available"), powered off ("Powered: no"), and a D-Bus failure in Docker.
- The warning is logged once per distinct reason; recovery logs INFO once; the re-check happens no more than every 10 minutes.
- The Vehicles page shows the reason instead of the button.
- Each test fails when its rule is removed.

## Constraints

- Python 3.8. Run black on touched files.
- Comment rule: why, not history; no phase, task or ruling IDs.
- Minimise lib growth (target ≤ +30); report lib lines before and after.
- Never bare `git stash`.
- One commit: "Scan for cars from Docker; say why when a range scan isn't possible", ending with the Co-Authored-By trailer.
