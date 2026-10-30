Title: Vehicle model, phase 3: desired state and reconcilers; delete legacy paths

This PR replaces fire-and-forget vehicle commands with desired state per car, delivered by one reconciler through the provider order, and deletes the legacy command paths. Phase 3 of the 1.4.0 vehicle-model rework (the spec runs to Phase 6; this stack opens Phases 1, 2, 3 and 3.5); base `vehicle-model/phase2`; review after Phase 2.

## Where this sits

Stack: Phase 1 registry → Phase 2 providers → **Phase 3 reconcilers** → Phase 3.5 `CarApiVehicle` dissolution and #659 port → *later, not in this stack:* Phase 4 control tick and one distributor, Phase 5 presence port, Phase 6 Vehicles tab.

Phases 1 and 2 added the registry and the providers alongside the legacy paths and are not independently useful improvements. This phase deletes `VehiclePriority`, the per-VIN command dispatch, the per-module charge-limit copies and the `-1` restore sentinel. Phase 3.5 dissolves `CarApiVehicle` and ports #659. Merge order is forced by the stack.

## Changes

### User-visible
- **Held limits stay in `chargeLimits`**, `main`'s `(outside, held)` pair, now keyed by VIN; numeric-ID entries are re-keyed when a vehicle list names the car. An entry exists only while TWCManager holds a limit; Forget and the 30-day expiry drop it, and old entries holding nothing are dropped on load. After a downgrade, 1.3.x's TeslaBLE path still reads VIN-keyed entries; its Tesla API path looks up numeric IDs and starts over.
- **A charge limit is never written while no source knows the car's current limit**, for any provider. A reading from any channel counts (a TeslaMate reading lets BLE write). TeslaBLE no longer sets a limit it could not read, as `main`'s BLE path did.
- **Commands become desired state.** Policy, the distributor and the heartbeat set each car's limit, charging on/off and amps; one attempt in flight per car, at most four sends per value. A pending stop is cancelled when charging is wanted again.
- **Paid fallback is timed.** Fleet or HA is used at once only when no free provider can serve the car; otherwise after free ones have failed for 5 min (limit) or 60 s (start/stop, amps). Fleet and HA never both send for the same desired value. Limit lowers never wake the car.
- A charge limit changed in the car or app is adopted, not undone, until the next policy decision (as on `main`). Charging on/off and amps are never adopted.
- **HA-only installs now get commands.** Measured, `main` never reached HA (no `VehiclePriority` entry). New behaviour, accepted.
- **Wake handling:** reads never wake. After a Fleet wake the car doesn't answer, a free online check runs every 120 s for 30 minutes (#699: 60 s for 10).
- **TeslaBLE** no longer retries internally or trips a circuit breaker (`maxRetries`, `retryDelay`, `circuitBreaker*` ignored); one quick retry, then the reconciler decides.
- **Presence** is re-checked every pass from the newest position from any source, TeslaMate and Fleet Telemetry included.
- **Mode 2:** the TWC offers the car's share until the car confirms its rate. A Fleet token refused right after a refresh is removed (#689).
- Fixes #667, Fixes #689, Refs #698 (lowering never wakes; Phase 5 finishes it), Refs #498.

### Architecture
New `Vehicle/Reconcile/`. Against `main`: `TeslaAPI` −587, `HomeAssistant` −137, `TeslaBLE` −122 lines.

## Evidence

**Unit tests:** 1778 passed, 1 xfailed (main's placeholder `test_regression_template`, xfail by design).

**Parity vs `main`:** `tests/unit/test_command_path_parity.py` drives real modules on both sides with a scripted car and counts every request. 31 scenarios: 12 cheaper, 16 equal, 3 cost more (each ruled); the unknown-limit rule changed no row. Selected rows:

| Scenario | main | this PR |
|---|---|---|
| Fleet-only, asleep, raise limit | $0.045 | $0.023 |
| BLE+Fleet, BLE down, lower limit | $0.025, 176 BLE runs | $0.001, 2 BLE runs |
| Telemetry + Fleet 408, start, 1 h | $1.44 | $0.003 |
| Mode 3 below floor | $0.001 | $0.003 |
| Restore after car left | never | $0.002 |

**Rebase onto #699, and a regression found before opening.** The rebase kept #699's newest-observation-wins rule and wake tests. A new parity row caught a Fleet-only car whose `wake_up` answered offline, then came online, never getting its limit. Fixed: a failed wake schedules the free online check, with one re-arm ($0.023). A car that never answers gets at most 7 wakes in 4 hours; `main` wakes every 30 minutes.

**Live box** (Gen2, BLE, TeslaMate; `commandPolicy` temporarily `ble_only`): on 2026-10-16 an earlier build never placed a sleeping, plugged-in car after a restart, so the Scheduled limit never went out; now fixed. On 2026-10-17 a pre-rebase Phase 3.5 build's BLE limit landed at 00:05 after two timeouts (car asleep); charging at 00:05:52; zero paid calls.

## Gen3 hardware

@ngardiner: Gen3 is still unit-tested only. The hardware checks asked for in #704 (per-unit targets on a shared bus, `live_status` VIN and DIN format, the zero-headroom stop, Owner token access to `live_status`) apply here too. Thank you for any help.

## Size

lib: 27,215, down 315 from Phase 2 (+3,905 / −4,220). Still +4,035 (+17.4%) over `main`'s 23,180. Deletions are back-loaded: Phase 4 removes the per-slave allocator, Phase 5 the old presence code. Phases 4 and 5 are expected to shrink it further. Some of the growth is new capability (Gen3, providers, the reconciler), so the stack may not get all the way back to `main`'s size; whatever gap remains will be stated and explained.

## Known limits / not verified

- This tip has not run on the box, so neither the `chargeLimits` keying nor the unknown-limit rule has run live. Live runs so far used `ble_only`, so none has exercised Fleet wakes or fallback; the box returns to `prefer_ble` next.
- BLE's 5 s default command timeout proved tight on hardware; Phase 3.5 raises it to 15 s.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
