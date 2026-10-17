# Branch review and merge order, 2026-10-16

Read-only review of every local branch against `origin/main` (03d7932, 107 commits past the stale local `main` at 0b7d143; fast-forward local main). Live box: `vehicle-model/phase3` db47522 since 09:45, watchdog armed, midnight Scheduled-charge run pending. Full unit suite on `vehicle-model/phase3.5` 40f77ca run here: 1829 passed, 1 xfailed, black clean.

## The three rearchitectures and how they relate

| Line | Where it lives | Status |
|---|---|---|
| **A. EVSE abstraction (#483)** | On `main` since 2026-04-16 (Nathan's port: `EVSEController`, `EVSEInstance`, `MergedEVSE`, `TeslaAPIEVSE`, `TeslaAPIController`, watt-based `distributeEVSEPower`) | Incomplete. `distributeEVSEPower` returns early unless a non-Gen2 controller is registered, so pure-Gen2 installs still run the per-slave allocation inside `TWCSlave.send_master_heartbeat`. Two allocators, one of them untested. The class zoo knows about each other's types. |
| **B. Unified integrations + presence stack** (Oct 9–12) | `presence/1..4`, `presence/rebased`, `presence/5-fleet-rate-queue`, `presence/3-plug-presence`, `presence/4-fleet-rate-queue`, `deploy/presence-2/3`; proposal `unified-integrations-proposal.md` | Proposal PRs 1–3 are merged (#679, #687, #692). PR 4 (IntegrationOrder) and PR 6 (VehicleRegistry) were redesigned as vehicle-model Phases 2 and 1. The spec (2026-10-13) rules the presence stack is *not* landed as-is; its rules and tests port in Phase 5. Only 5 of 82 presence commits are patch-equivalent in phase3.5 (the per-VIN command-queue keys). |
| **C. Vehicle model** (Oct 13+) | `vehicle-model/phase1` → `phase2` → `phase3` → `phase3.5` (a linear stack, each an ancestor of the next); spec `2026-10-13-vehicle-model-design.md`; roadmap Phases 0–6 | Phases 1–3 complete with reviews; Phase 3 soaking on the box; Phase 3.5 Tasks 1–5 implemented, Task 5 (#659 port) **not yet reviewed**. Phase 2 already replaced A's `MergedEVSE`/`TeslaAPIEVSE`/`TeslaAPIController` with `ChargingPoint`/`VehicleEndpoint(s)`. Phase 4 is where A's per-slave allocator is deleted. |

So there is one live line (C). B is a feeder whose remaining value is the plug-presence rules and ~6,800 lines of presence tests to port in Phase 5. A is finished by C's Phase 4, not by separate work.

## Merge order

Gate everything on tonight's midnight run of phase3 on the box (the exact scenario that failed on 464d83c: restart with the car plugged in and asleep, Scheduled limit raise at 00:00 over BLE, zero HTTP).

**If PASS:**

1. Rebase the stack onto `origin/main` (6 commits behind: #699). Only `TeslaAPI.py` and `CHANGELOG.md` conflict. Resolve by taking Phase 3's wake path (see Finding 1) and porting the intents of `tests/unit/test_teslaapi_wake.py` as parity rows.
2. Review Phase 3.5 Task 5 (the #659 port, +260 lib) the same way every other task was reviewed. Decide the open question in its report: drop `_signingState` (~7 lines).
3. Deploy phase3.5 to the box for its own soak and midnight run. Phase 3.5 is "no behaviour change" by contract, but Task 5 is a feature and it dissolved `CarApiVehicle`, which every HTTP page and the policy properties touched.
4. Open stacked PRs upstream in order: `vehicle-model/phase1` → main, `phase2` → phase1, `phase3` → phase2, `phase3.5` → phase3. Each description carries its box-soak evidence and the parity table. Say in each that phases 1 and 2 are not independently shippable improvements (they add the registry and providers alongside the legacy paths; Phase 3 deletes the legacy command paths). The alternative is one PR of 192 commits, +8,760/−4,457 lib. Given Nathan reviews on volunteer time and the user won't self-merge, stacked is the reviewable shape; merge order is forced by the stack anyway.
5. Keep small fixes flowing to main independently and rebase the stack as they land, as the no-self-merge rule already implies.

**If FAIL:** roll back to cfd0086 (settings backup `~/twcmanager-settings.json.bak-20261015-phase3`; heldLimits migration is one-way), diagnose on phase3 as a Task 12d, re-soak. Phase 3.5 and the PRs wait. Do not start Phase 4 on top of an unverified Phase 3.

## Drop list (verified by `git cherry origin/main <branch>`: 0 unmerged patches unless noted)

Delete now:
- `fix/distributor-skips-evses` (#696), `fix/car-api-charge-vin` (#697), `fix/672-fleet-evse` (#694), `fix/teslamate-vehicle-mapping` (#671; the current checkout), `feat/token-slots` (#692), `fix/fleet-wake-poll` (#699): all merged.
- `claude/wizardly-robinson-f4deba`, `worktree-agent-a0c797f8c4e495de0`: scratch worktrees for #699/#700, both merged. Remove the worktrees too.
- `vehicle-model/phase3-owner-commands` (185 unmerged, all superseded): the #659 work on top of phase3, ported into phase3.5 as Task 5 per the ledger. Keep its review file (`wt-p3/review-659-p3.md`) until the Task 5 review is done, then delete the branch and the `wt-p3` worktree.
- `presence/1-command-queue` (cherry-picked into Phase 1 Task 1), `presence/2-charge-limits` (its `ChargeLimitRules` became `Reconcile/Rules.py`), `presence/3-presence-tracker`, `presence/4-arrive-depart`, `presence/rebased`, `presence/5-fleet-rate-queue`: superseded by the plug-presence revision (spec 2026-10-11) and then by the vehicle model.
- `deploy/presence-2`: superseded deploy build.
- `fix/fleet-evse-zero-stop` (4 unmerged; 2 of its 4 commits merged as #696/#697): the zero-share stop/resume was shelved pending the "broader charge/limit pass", which Phase 3 delivered as stateless CHARGING desired state. Nothing left to harvest.

Keep for now:
- `presence/3-plug-presence` and `presence/4-fleet-rate-queue`: reference for the Phase 5 port (the plug-presence rules, attribution, and the test files `test_plug_presence_scenarios.py`, `test_vehicle_presence.py`, `test_teslaapi_presence.py`, `test_teslable_presence.py`, `test_presence_*.py`). Delete after Phase 5.
- `deploy/presence-3` (1535e71): the pre-rework fallback build named in the memory notes. Delete once phase3 or 3.5 has survived a week on the box.
- `deploy/phase3-live` (= phase3 db47522): the current box build. Retarget to 3.5 when it deploys.
- `port-fleet-wake-poll-1.3.4`, `port-owner-commands-unsigned-1.3.4`: 1.3.4 line; #700 merged (branch can go), #701 open (keep until merged).
- `fix/659-owner-commands-unsigned` (7 commits on main, PR never opened although #701's body promises it): decision below.

## #659 exists three times

1. `port-owner-commands-unsigned-1.3.4` → PR #701, open on release/1.3.4.
2. `fix/659-owner-commands-unsigned` on main: 7 commits, +280 lib, PR not opened.
3. Phase 3.5 Task 5: the port onto the registry model (canonical for the rework).

Recommendation: open (2) on main now. Docker `:latest` tracks main, so #659's reporter and anyone with a `command_signing: off` car is blocked until something lands, and the rework PRs will take weeks to review. Cost: when the stack rebases over it, `VehiclePriority.py` (deleted in Phase 3) and `TeslaAPI.py` conflict as delete/modify; resolve "take 3.5" and re-run Task 5's gate tests (`test_teslaapi_readonly_gate.py` classes `TestOffCarCommandsThroughOwner` etc.). Not opening it delays #659 on main until the rework lands. User's call.

## Finding 1: the stack lacks #699 (Fleet wake-poll), and its wake path differs

phase3 and phase3.5 are both exactly the 6 commits of #699 behind `origin/main`: post-wake 10-minute window, a free `vehicles/{vin}` GET every 60 s, `lastWakeSentTime` anchor, newest-observation-wins `is_awake`. That fix stopped 9 paid wakes in one night and was verified live on 2026-10-15.

Phase 3's `TeslaAPI.wakeOutcome` has a different shape, and on reading it the paid-wake bound holds: every attempt first runs the free online check (`onlineState`, cached 120 s, with the telemetry newest-wins rule), and a failed `wake_up` sets `delayNextWakeAttempt = WAKE_RETRY_SECONDS = 1800`. The hold is longer than the cache, so during the hold the reconciler's retries keep answering the free check until the car reports online, then the command goes out with no second wake. The parity tests bound it ("at most 1 wake per desire", `test_a_spent_rearm_lets_the_start_go_without_the_limit` has the car wake late). Differences from #699 to accept or tune: the free poll is every 120 s not 60 s (up to a minute slower to notice the car), and the wake hold is 30 min not 10 (one wake per half hour if the car never comes up).

Action at rebase: take Phase 3's path; add one explicit parity row (Fleet-only, asleep, `wake_up` answers offline, car online at +59 s; expect exactly one `wake_up`, the limit within ~2.5 min, no second wake inside 30 min). The box is `ble_only`, so no live run exercises this; only a test can.

## Finding 2: lib size, stated plainly

| Ref | lib lines | vs origin/main |
|---|---|---|
| origin/main | 23,180 | — |
| phase1 | 25,394 | +2,214 |
| phase2 | 27,483 | +4,303 |
| phase3 | 27,270 | +4,090 |
| phase3.5 (before Task 5) | 27,098 | +3,918 |
| phase3.5 (40f77ca) | 27,358 | +4,178 (+18%) |

Deleted so far: `VehiclePriority` (−210), `MergedEVSE` (−181), `TeslaAPIEVSE` (−151), `TeslaAPIController` (−147), `TeslaAPI` −493, `HomeAssistant` −140, `TeslaBLE` −125. Added: `Reconcile/` ~1,930, `Providers/` ~1,345, `Registry/` ~860, `ChargingPoint`+`VehicleEndpoint(s)` ~510, Gen3 ~500, HTTPControl ~400.

Not yet deleted, and the reason to continue rather than stop: the per-slave allocator in `TWCSlave.send_master_heartbeat` plus its `chargeRateControl` branches, the 6 A spike workaround and the start/stop gates (Phase 4), and the old GPS/`atHome` presence in `TeslaAPI`/`HomeAssistant` (Phase 5). Those are the duplicates the new abstractions replace. Phases 1–3 built the replacement first; the deletions are back-loaded.

Rule to attach to Phases 4 and 5: each must end with lib below where it started, and if lib is still above 23,180 after Phase 5, stop and audit the design before Phase 6. The "rearchitecture must shrink" rule is being carried, not met, and the write-up should say so to Nathan too.

## Forward work, in order

1. Tonight: phase3 midnight run (gate).
2. Rebase onto origin/main; Finding 1 parity row; Task 5 review; phase3.5 soak.
3. Open the stacked PRs. Update the release tracker rows (not done here).
4. **Phase 4 (control tick, one distributor)**: this is what finishes rearchitecture A. Everyone moves onto `distributeEVSEPower` per charging point; the per-slave path in `TWCSlave` is retired with its behaviours ported as distributor rules with tests (fair share, flex, dampening, 6 A spike, 60 s gates, re-stop ≥ 4 A, idle-TWC minimum for plug detection). RS-485 loop becomes protocol-only; token refresh off the loop with the per-slot lock (#690). The two-pass admission distributor (inventory A15) follows in the same distributor. Expected lib delta: negative.
5. **Phase 5 (presence port)**: plug-presence rules from `presence/3-plug-presence` onto the registry (TWC/BLE outrank telemetry; BLE reach is presence, silence isn't absence; 1000 ft GPS fallback; presumed-present at startup; VIN-less attribution). Port the test files, then delete the presence branches. Deletes the old `atHome` computations (final review I2 row 2 counted six). Closes #698 fully.
6. **Phase 6 (Vehicles tab)** and the remaining 1.4.0 issues (#689 handled by Phase 3's refusal retirement, #667 by Phase 0, #690 by Phase 4; #691 and #666 are small standalone fixes for main now).
7. 1.3.4 line: #701 waits on Nathan; tag after. Nothing in the rework targets 1.3.4.

## Open PRs upstream (as of 2026-10-16)

| PR | What | Verdict |
|---|---|---|
| #702 (main) `fix/659-owner-commands-unsigned` | #659 fix on main, CI green | Fine. Conflicts with phase3.5 in 8 files (two modify/delete: `VehiclePriority.py`, `TeslaAPIEVSE.py`). Resolve once, after it merges, by taking 3.5 everywhere (Task 5 is the port). |
| #701 (release/1.3.4) | #659 backport | Nathan's call; no interaction with the rework. |
| #636 Nathan, pricing modules (+5,597) | Open since April | Clean against main; against phase3.5 one file, `TWCMaster.py`, two trivial attribute hunks. His hunk re-adds `lastChargeLimitApplied = 0` and `stats["moduleDispatch"]`, both deleted by Phase 3: drop them at rebase. Ask whether he wants it in before 1.4.0. |
| #633 ozbenh, RaspiOS Trixie (draft) | Makefile, venv service | Orthogonal packaging; already conflicts with main. Leave. |
| #609 normanu, Victron CerboGX | add/add conflict on `EMS/Victron.py` | A Victron module landed since; probably dead. Nathan to close or ask for a rebase. |
| #515 RichieB2B, sub-amp rounding in `TWCSlave` | Conflicts with main and 3.5 in the per-slave allocator | Don't rebase it. Carry the intent (round vs truncate, finer granularity) as a distributor rule in the Phase 4 plan; close #515 with a pointer when Phase 4 lands. |
| #185 → v1.2.1 | 2020 | Dead; close. |

## Open issues: which rearchitecture PR closes each

"PR" below means the stacked PR for that phase. A phase's PR description should say `Fixes #n` for its rows, and the rows marked "standalone" should get their own small PR on main now (each under about 30 lines) so milestone 1.4.0 has nothing left outside the stack.

| Issue | Milestone | Closed by | Evidence / note |
|---|---|---|---|
| #698 TeslaBLE wakes a sleeping car to lower its limit | 1.4.0 | **Phase 3 PR** | `Reconcile/Rules.py` never wakes to lower; parity `test_ble_only_limits_never_wake_to_lower`. |
| #689 Commands keep using a dead Fleet token (401) | 1.4.0 | **Phase 3 PR** | A refused Fleet command retires its slot; `test_fleet_401_retires`, `test_fleet_401_retires_the_slot_and_403_refuses_the_scope`. |
| #667 `cancelStopCarsCharging` never cancels | 1.4.0 | **Phase 1 PR** (per-VIN queue keys, Phase 0 Task 1); fully by **Phase 3 PR** | On 3.5 it clears the CHARGING desire and the queued attempt per VIN (`TWCMaster.py:190`); the exact-match legacy path is deleted in Phase 3. Say `Fixes` on Phase 3, `Refs` on Phase 1. |
| #659 EU Model X 2018, Owner commands | — | **#702** (main), **#701** (1.3.4); **Phase 3.5 PR** carries the port (Task 5) | Phase 3.5's description should say it supersedes #702's implementation. |
| #690 Concurrent refreshes spend a single-use refresh token twice | 1.4.0 | **Standalone now** (one `RLock` around `TeslaTokenSlot.refresh`); otherwise Phase 4 (refresh off the serial loop) | No lock on 3.5 (`TeslaTokenSlot.py:204`). `TeslaTokenSlot.py` barely changes in the stack, so a standalone fix cherry-picks cleanly. |
| #666 POST without Content-Length crashes the handler | 1.4.0 | **Standalone now** | Still `int(self.headers.get("content-length"))` at `HTTPControl.py:1523` on 3.5. |
| #691 `TeslaPowerwall2.lastFetch` class-level dict | — | **Standalone now** | Unchanged on 3.5 (`TeslaPowerwall2.py:21`). |
| #374 API support for charge rate (UMC, Gen3) | — | Already on main (`TeslaAPIEVSE`); **Phase 2 PR** replaces it with `VehicleEndpoint` | Close now with a note, or `Fixes` on Phase 2. |
| #498 Tesla API "hiccup" prevents the car sleeping | — | **Phase 3 PR**, pending reporter confirmation | Reads never wake; the only unsolicited cloud call is the free online check. Say `Refs`, ask the reporter. |
| #480 Two cars fighting for low solar | — | **Phase 4 PR** (two-pass admission distributor, inventory A15) | Admission order is the "which car first" the issue asks for. |
| #457 Mobile Connector car stopped after a few minutes | — | **Phase 4 PR** (idle/UMC minimum per charging point); partly Phase 3 (stop at zero offer rules) | Add a parity row: UMC-only car, zero offer, no stop unless the budget says so. |
| #458 Non-Tesla car on a Gen2 | — | **Phase 1 PR** (anonymous plug-session vehicle) + **Phase 4 PR** (allocation to the anonymous point) | `Refs` on Phase 1, `Fixes` on Phase 4. |
| #460 "At home" wrong when charging 35 km away | — | **Phase 5 PR** (plug presence: charging elsewhere is never HOME) | |
| #614 BLE status "Not Implemented" after pairing | — | **Phase 6 PR** (Vehicles tab BLE states: Not in range / In range / Pairing / Paired / Key refused) | Spec names this. |
| #515 (PR) sub-amp rounding | — | **Phase 4 PR** as a distributor rule | See PR table. |
| #482 Why keep `fakeMaster = 0` | — | **Phase 4 PR** (serial loop becomes protocol-only) or leave | Decide in the Phase 4 plan. |
| #588 Teslemetry as a provider | — | After 1.4.0; a Phase 2-shaped provider add-on | `Refs` on Phase 2. |
| #552 / #475 External start/stop/policy over MQTT/API | — | After 1.4.0; desired state makes it a small feature | Not rework. |
| #471 Schedule reverts the policy | — | Not rework | Config/policy question. |
| #516, #645, #613, #534, #518, #472, and older | — | Unrelated or stale | |

## Target state check against the user's goals

- One registry, one provider order, one reconciler, one distributor: Phases 1–3 deliver the first three; Phase 4 the fourth. Per-method duplicates removed so far: command dispatch (`VehiclePriority`), the three `lastChargeLimitApplied`, the `-1` sentinel, per-channel dedupe flags, the type-specific EVSE classes.
- Any subset of Gen2/Gen3/UMC × Owner/Fleet/TeslaMate/BLE/HA: the provider tables and `commandSlotFor` already make Owner, Fleet, BLE, HA, TeslaMate, Gen2 and Gen3 peers; a UMC car is a `VehicleEndpoint` with no TWC member. The parity table has 31 rows across install types. What is still missing for "works with only 1–2": Gen3 is unit-tested only (no tester), and HA-only commands are new behaviour (user accepted).
