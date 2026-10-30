Title: Vehicle model, phase 3.5: dissolve CarApiVehicle; Owner API commands (#659)

This PR removes `CarApiVehicle` so the registry `Vehicle` is the only per-car object, and ports #659 (Owner API commands for cars Tesla lists with `command_signing: off`) onto the provider model. Phase 3.5 of the 1.4.0 vehicle-model rework (the spec runs to Phase 6; this stack opens Phases 1, 2, 3 and 3.5); base `vehicle-model/phase3`; review after Phase 3.

## Where this sits

Stack: Phase 1 registry → Phase 2 providers → Phase 3 reconcilers (deletes the legacy command paths) → **Phase 3.5 (this PR)** → *later, not in this stack:* Phase 4 control tick and one distributor, Phase 5 presence port, Phase 6 Vehicles tab.

Phases 1 and 2 added the registry and providers alongside the legacy paths and were not independently useful improvements; Phase 3 deleted the legacy command paths. Merge order is forced by the stack.

## Changes

### User-visible
- **#659, Owner API commands for unsigned cars.** A car Tesla lists with `command_signing: off` can be commanded through the Owner API; other cars stay read-only on Owner tokens. Owner sits just ahead of Fleet in the provider order, so with both tokens such a car's commands go to the free Owner API, and to Fleet once Tesla refuses them. Its wakes also go through the Owner API, which is free.
  - #702 (on `main`) and #701 (1.3.4) solve the same issue independently and keep Fleet first. If this PR merges first, #702 can be closed. If #702 merges first, this PR replaces its implementation; the conflict resolves by taking this branch.
  - `ble_only` suppresses Owner commands, like every cloud command.
- **Vehicles page:** easier to read, and it says which channels can command the car; see [Vehicles page](#vehicles-page) below.
- **Logging:** vehicle wake decisions log at INFO.
- Refs #659.

### Architecture
- `CarApiVehicle` is gone. `TeslaAPI`'s per-car bookkeeping (online cache, status deferral, wake hold, 429 backoff, `atHome`) lives on the registry `Vehicle` as its `TeslaAPI` attachment. The registry answers sync state directly.
- "Can forget" and "forget" are one atomic registry operation, removing a listing/expiry race the old rejoin path used to heal.

## Vehicles page

The Vehicles page arrived in Phase 1; this phase makes it readable and accurate about what each channel can do.

| | Providers | Last seen | Limit column |
|---|---|---|---|
| Before | `TeslaBLE (paired), OwnerAPI (listed)` (and a Tier column: `managed`) | `0 s ago via TeslaAPI` | `90% (holding 80%)` |
| After | BLE: paired<br>Owner API: read-only (car requires signed commands)<br>TeslaMate: reports, read-only | `0 s ago via Owner API` | Charge limit set by TWCManager: `80% (car's own limit: 90%, restored when released)` |

- The Tier column is gone: the provider list already says who can command the car.
- One provider per line, by source name (TeslaBLE shows as "BLE"), each saying whether it commands or only reads, and why.
- TeslaMate and Fleet Telemetry are listed as read-only reporters.
- Data sources record "Owner API" or "Fleet API", by the token that made the read, instead of a generic Tesla API.
- After Scan, the vehicle page refreshes itself while the scan is pending, so the button comes back with the result.

## Evidence

- **Unit tests:** 1868 passed, 1 xfailed (main's placeholder `test_regression_template`, xfail by design).
- **The dissolution is held to no behaviour change:** when it landed, a paid-call differential over the 211 tests common to Phase 3 and this branch showed zero request differences. The parity scenarios pass unchanged at this tip.
- **#659 tests:** an "off" car commands and wakes through Owner; other cars are refused without HTTP; with both tokens only the "off" car uses Owner, and an Owner 403 latches it over to Fleet. Paid records per desire for an Owner-only "off" car match a Fleet-only car. A new parity row covers an Owner-off car whose wake answers offline and then comes online: one Owner wake, limit within 150 s, nothing billed.
- **Rebase and wake fix:** this tip carries Phase 3's #699 rebase, wake-regression fix and held-limit rules. The full suite passes at the tip, and the parity, reconciler and wake tests pass at each commit through the held-limit rework.
- **Live box, midnight 2026-10-17** (pre-rebase build of this branch, before the Owner-first order, wake logging and page changes; Gen2, BLE, TeslaMate, Owner and Fleet tokens; `commandPolicy` temporarily `ble_only`). At midnight the Scheduled policy raised the limit to 70 %. The BLE write timed out twice with the car asleep and landed at 00:05; charging started at 00:05:52 at 48.6 A; zero paid calls; no tracebacks; still charging at 00:30.

## Size

| | lib lines | vs previous | vs main |
|---|---|---|---|
| `main` | 23,180 | | |
| Phase 3 | 27,215 | | +4,035 |
| this PR | 27,425 | +210 | +4,245 (+18.3%) |

This phase grows by 210 lines, and that is worth saying plainly: the refactor itself (dissolving `CarApiVehicle`) shrank lib by 131 lines, and the rest is features — #659 and the Vehicles page fixes. Breakdown: the dissolution and its cleanup −131, the #659 port +249, Owner-first order −6, wake logging +33, Vehicles page readability +54, Owner/Fleet source names +11. The stack is still 18% larger than `main`; deletions are back-loaded. Phase 4 deletes the per-slave allocator in `TWCSlave` (one distributor for every install), Phase 5 the old GPS/`atHome` presence code. Both are expected to shrink it further. Some of the growth is new capability (Gen3, providers, the reconciler), so the stack may not get all the way back to `main`'s size; whatever gap remains will be stated and explained.

## Known limits / not verified

- **The #659 path is not exercised live**: the box's car requires signed commands, so its Owner token never commands. Unit and parity tests only.
- The rebased tip has not run on the box.
- An Owner 429 backs off the whole car, including its Fleet commands.
- After an Owner refusal (or a "not listed" refusal from Home Assistant or the Tesla providers) the next provider goes at once; the refusing one stays excluded, so nothing loops.
- **BLE command timeout default is now 15 s** (was 5 s): on real hardware authenticated `tesla-control` commands often needed more than 5 s, even awake. Configurable as `moduleConfiguration.TeslaBLE.commandTimeout`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
