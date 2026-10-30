Title: [1.3.4] Run tesla-control in Docker's host network namespace; don't kill TWCManager on a timeout

Fixes two Docker-only bugs in `TeslaBLE` on release/1.3.4. The same change against main is #711.

### Problem
- **tesla-control never runs in Docker.** In Docker, tesla-control is meant to run in the host's network namespace through `nsenter --net=/rootns/net`. Pairing and commands each inserted that prefix as one argv element: `command_string.insert(0, "nsenter --net=/rootns/net ")`. `subprocess.Popen` gets no shell, so it looked for an executable literally named `nsenter --net=/rootns/net `. That raised, `_run_command_with_timeout` logged it and returned `(None, None, None)`, and the caller saw a failed command. No tesla-control call could succeed in Docker.
- **A timeout in Docker kills TWCManager.** `_run_command_with_timeout` skipped `preexec_fn=os.setsid` in Docker, but its timeout path still kills the child's process group (`os.killpg(os.getpgid(pid), ...)`). Without `setsid`, the child shares TWCManager's process group, so a timed-out command sent SIGTERM, then SIGKILL, to TWCManager itself. With the first bug in place no command started, so this one stayed hidden. Fixing the first bug alone would expose it.

### Change
- **One place adds nsenter.** `_run_command_with_timeout` prefixes `["nsenter", "--net=/rootns/net"]` as separate arguments when running in Docker and the command is the tesla-control binary. The call-site inserts in `peerWithVehicle` and `_sendCommand_internal` are removed.
- **The compose file adds `CAP_SYS_PTRACE`.** nsenter opens the host's network namespace through the `/proc/1/ns` mount, which needs ptrace access to PID 1. Without it, nsenter fails with `nsenter: cannot open /rootns/net: Permission denied`, even with AppArmor unconfined. Existing installs need this line added to their own `docker-compose.yml`.
- **Every command gets its own process group.** `use_process_group` now always means `os.setsid`, in Docker or not, so the timeout kills only the command.

### Verified on a real Docker host
On Ubuntu 24.04 arm64 with Docker 29, in an ubuntu:24.04 container with the compose file's capabilities and the `/proc/1/ns:/rootns` mount:
- With `CAP_SYS_ADMIN`, `CAP_NET_ADMIN` and `CAP_NET_RAW` only, `nsenter --net=/rootns/net` fails with `Permission denied`. The result is the same with `apparmor=unconfined` and with `--pid=host`.
- With `CAP_SYS_PTRACE` added, the same argv form this change uses reaches the host's network namespace: inside nsenter, `/proc/net/dev` lists the host's interfaces (`end1`, `wlan0`, `docker0`).

### Not verified
tesla-control itself has not yet been run through nsenter on a Docker host, and the timeout path has not been exercised there. Both are covered by unit tests only.

### Differences from the main branch
release/1.3.4 has no BLE state reads (`_fetch_state_json`), so there is one fewer call site and one fewer test case. Everything else is the same, including the runner change.

### Tests
New `tests/unit/test_teslable_docker.py` (release/1.3.4 has no TeslaBLE test file yet):
- In Docker, the Popen argv for pairing and commands starts with `"nsenter", "--net=/rootns/net"`, then the binary, as separate elements.
- Outside Docker, the argv starts with the binary.
- A real `sleep` that times out, in and out of Docker, is killed by process group, and that group is never the test runner's own (`os.killpg` is guarded so a regression can't kill pytest).

Without the fix, the two Docker argv cases and the Docker timeout case fail. The outside-Docker cases guard existing behaviour.

Full unit suite: 651 passed, 62 failed. The same 62 tests fail on untouched release/1.3.4 (645 passed), so this branch adds no new failures. `black` is clean on the changed files.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
