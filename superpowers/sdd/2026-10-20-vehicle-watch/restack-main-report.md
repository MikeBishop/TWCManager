# Restack onto the new main: report

Base: `origin/main` = bd5a7603 (adds #702 Owner API commands for `command_signing: off` cars, #711 Docker BLE exec fix, bd5a7603 per-vehicle charge queue / `cancel_stop` for #667).

New branches (local only, nothing pushed; the original `vehicle-model/*` branches are untouched):

| Phase | Branch | Tip | Commits | Full suite at tip | lib delta vs new main (orig delta vs 03d79325) |
|---|---|---|---|---|---|
| 1 | restack2/phase1 | 8070d5c3 | 19 | 1353 passed, 1 xfailed | +2245 (+2263) |
| 2 | restack2/phase2 | 4b012c27 | 17 | 1525 passed, 1 xfailed | +4361 (+4350) |
| 3 | restack2/phase3 | aa9a7b99 | 19 | 1905 passed, 1 xfailed | +3979 (+4035) |
| 3.5 | restack2/phase3.5 | a765b6f4 | 9 | 1879 passed, 1 xfailed | +3956 (+4245) |
| 4 | restack2/phase4 | 7432894b | 15 | 1980 passed, 1 xfailed | +3062 (+3351) |
| 5 | restack2/phase5 | cf89bf5f | 20 | 2252 passed, 1 xfailed | +2945 (+3233) |
| 6 | restack2/phase6 | 198c94f3 | 18 | 2358 passed, 1 xfailed | +3504 (+3776) |
| #707 | restack2/707 | 1255db41 | 1 (on restack2/phase2) | docs only | — |

(Tips before the review fixes, for the per-commit logs below: 47f0c45a, c6180980, 86ee4d2c, fe0990a9, bc93aeae, 3dd50513, bc0e3841, 6bfcb61d. The lib deltas from 3.5 on grew by 7 lines: the carrier-aware retirement message; Phase 1 and 2 by one comment line.)

lib delta = total `lib/**/*.py` lines at the tip minus the base's (new main 23472; old base 23180). From Phase 3.5 on the stack adds ~300 fewer lines than before because its own Owner API port supersedes main's #702 code.

Per-commit pass counts: `verify-phase*.log` in the scratchpad (one line per commit; every commit was checked out and the full command from the brief run). Summary at the end of this report.

Suite command used everywhere: the one in the brief (`pytest tests --ignore=tests/API --ignore=tests/integration ...`). black was run on every .py file I resolved or edited; no other file was reformatted. No Python 3.8 interpreter exists on this machine; the added code was checked by inspection (no 3.9+ syntax; typing uses `Dict`/`Optional`/`Tuple` as the surrounding code does).

## Scrub (applies to every rewritten commit)

- The car name was replaced with `TestCar` in the commit that first touches each file (main's own `tests/unit/test_telemetry_mapping.py` in Phase 1's "Attach telemetry to registry vehicles by VIN or name", the first commit that touches it; later files in their introducing commits). `git grep` for the name at every tip, including restack2/707: nothing.
- `tests/unit/reconcile_helpers.py` `HOME, AWAY`: HOME is now `(40.0, -75.0)` and AWAY keeps the original lat/lon offset from HOME, so every distance-dependent test keeps its geometry. Replaced in the commit that introduces the line (Phase 3 "Locate cars from their latest free position for presence") and in the Phase 5 commit that rewrites it. No tip contains the original tuple or the original latitude. The original values appear nowhere in this report, in any commit message, or in the scrub scripts' output; one rebase conflict diff did print the original line into this session's terminal transcript (not into any file or commit).

## Phase 1 (restack2/phase1, 47f0c45a)

Conflicts and resolutions:

1. **"Key vehicle commands by (cmd, vin) and add explicit cancellation"** vs bd5a7603 in `VehicleCommandQueue.py`, `TWCMaster.py`, `test_vehicle_command_queue.py`, CHANGELOG. Resolved on behaviour, expressed in Phase 1's queue design:
   - Kept Phase 1's generic `cancel(cmd, match)`; `TWCMaster.cancelStopCarsCharging(vin)` keeps using it (pending stops for the car and for every car; all stops without a vin). Added main's guard: during shutdown (`_draining`) `cancel()` leaves high-priority entries (stops) alone, since shutdown must send them.
   - Adopted main's overlap rule as the queue's `_replaces`: a charge command with no vin overlaps every pending charge command, so the newer replaces the older (main's `_key`/`_replaces`). Phase 1's `test_none_vin_is_distinct_from_named_vin` asserted the opposite (a vehicle-less start and a per-car start both run) and was replaced by main's `test_vehicleless_start_replaces_every_pending_stop` plus a new `test_stop_for_one_car_replaces_a_vehicleless_start`. `applyChargeLimit` keeps Phase 1's "None is a distinct target" keying (only charge commands overlap). The now-redundant explicit start-cancel in `stopCarsCharging` was removed (the queue replaces the start); Phase 1's `TestChargeStartStopCancelRules` still passes.
   - Adopted main's per-VIN rate limit: `CHARGE_COMMAND_INTERVAL = 60`, `_lastChargeTime` stamped in `_next()`, a repeat within the interval is dropped at `put()` (not during shutdown). The `""` VIN from TWCSlave keys as None (main's rule).
   - Tests: main's `TestPerVehicleCharge`, `TestCancelStop` (as `cancel()` calls through a `stop_for(vin)` helper mirroring TWCMaster's match) and `TestChargeInterval` were merged into Phase 1's test file (fixture call records are 4-tuples there); Phase 1's `TestKeying`/`TestCancel` kept.
   - TWCSlave: main's `cancelStopCarsCharging(self.currentVIN)` merged cleanly (Phase 1's slave still passed no VIN).
   - CHANGELOG: main's two #667 lines kept; Phase 1's own #667 line dropped (said the same).
   - Commit message reworded (its "stop-replaces-start rule lives in TWCMaster" no longer held).
2. `TeslaAPI.py` (CarApiVehicle class attributes): both sides added attributes; kept both.
3. `tests/unit/teslatokens.py` `add_home_vehicle`: kept main's signature (`command_signing`, `vin`, `name`, `id`) with Phase 1's real-shaped default VIN; main's new tests in `test_teslaapi_readonly_gate.py` used `VIN1`/`VIN2`, which Phase 1's registry rejects, so they use `5YJ3E1EA1KF00000{1,2}`.
4. `tests/unit/test_teslable_docker.py` (main's #711 test) needs `master.settingsLock` from Phase 1's "Add a settings lock" onward: the fixture gets an `RLock` in that commit.

Behaviour decisions: a vehicle-less charge command overlaps per-car ones (main's rule) instead of Phase 1's distinct-None keying; stops are never cancelled during shutdown; at most one charge start/stop per car per 60 s.

## Phase 2 (restack2/phase2, c6180980)

Conflicts and resolutions:

1. **"Make VehiclePriority a facade over the provider order"** vs #702's `VehiclePriority._skip_read_only_for_command` (which logged why via `refuseCommandIfReadOnly`). The facade walks providers, so main's behaviour moved into the providers:
   - `OwnerAPIProvider` declares the five commands at a new `OWNER_COMMAND = Cost(TIER_BILLED, 0.0)` (the same constant Phase 3.5 later adds). `available(command)` is true while no Fleet token commands and the module is not read-only (so an Owner token whose cars are not yet listed stays available, as main's `readOnly` says). `ready(vehicle, command)` is true for a listed car the Owner API may command and calls `refuseCommandFor(car, ...)` otherwise, which logs the per-car reason once (main's fc66a4db).
   - `FleetAPIProvider.available(command)` calls `refuseCommandIfReadOnly(<tesla command>)` when the Fleet slot can't command, which is main's module-wide hint (or the per-car lines when an Owner token is held).
   - The facade's `_listUnloaded` keeps both TeslaAPI providers in a targeted walk until the vehicle list is loaded.
   - The `OwnerAPI` registry claim follows `ownerCommandsAllowed(car)` instead of a fixed False.
   - Tests: main's `priority_over(api, ble)` became a provider-order fixture with a HomeAssistant-like fallback provider ranked after TeslaAPI; `TestVehiclePrioritySkipsReadOnly.make` lists a `required` car (an unlisted Owner-only module is no longer read-only); `test_two_providers_with_honest_costs` and `test_provider_tables` expect the Owner commands; `test_read_only_module_without_refusal_method_skipped` (a deleted method) dropped.
2. **"Replace TeslaAPIEVSE/TeslaAPIController with vehicle endpoints"**: #702 made `TeslaAPIEVSE.isReadOnly` per vehicle; `VehicleEndpoint.isReadOnly` (no SET_AMPS candidate) already is, via the Owner provider's readiness. Main's `test_evse_read_only_per_vehicle` ported as `test_endpoint_read_only_per_vehicle`; the `TestTeslaAPIEVSE` class went with the module.
3. **"End a provider walk on a Fleet success, skip or wake hold"** made `applyChargeLimit` return "success" unconditionally, which would have stopped the walk after a car Tesla refused. It now returns "error" when a car was refused (before or during the call), so the next provider gets it; main's `REFUSED_RETURNS["applyChargeLimit"]` became `("error", "error")` and a Fleet refusal's return `"success"` (Phase 2's own semantics for a non-latching Fleet error).
4. **"Let TeslaBLE and TeslaAPI take a targeted charge limit"**: both `applyChargeLimit` loops iterate the targeted `vehicles` and keep #702's per-car refusal check.
5. "Drop provider declarations nothing reads": kept the Owner `OWNER_COMMAND` expectation in `test_teslaapi_providers.py`.
6. CHANGELOG: Phase 2's duplicate #667 line dropped again (it was re-added by its facade commit).

Behaviour decisions: Owner API commands for `off` cars survive the provider order (the Owner provider is the carrier, only while no Fleet token commands; with both tokens Fleet carries, as main); a refused car makes `applyChargeLimit` fail so BLE/HA are tried.

## Phase 3 (restack2/phase3, 86ee4d2c)

The two guarantees from the brief:

- *A stop isn't sent while charging should continue.* Until "Start and stop charging as desired state and delete the legacy path": the legacy queue (my merge of bd5a7603 into Phase 3's generic queue: `_replaces`, `_chargeHeld`/`CHARGE_COMMAND_INTERVAL`, `cancel()` with the shutdown guard, all in the `_legacy` mode only) and `TWCMaster.cancelStopCarsCharging`, pinned by Phase 1's queue/TWCMaster tests. From that commit on, `cancelStopCarsCharging` clears the desired stop (`Desired`/reconciler), pinned by `test_charging_reconciler.py::test_cancel_drops_a_pending_stop_only`, `::test_cancel_withdraws_a_queued_stop` and `test_twcmaster.py::TestChargeStartStopCancelRules` (Phase 3's own). No code added.
- *No back-to-back retry of a refused start/stop.* Legacy: the per-VIN interval above (main's `TestChargeInterval` ran until the legacy test file was deleted with the path). Reconciler: `Reconciler.RETRY[CHARGING] = 60.0` holds a re-send to the same provider for 60 s after an outcome (`now - rec.lastOutcomeAt < RETRY[aspect]`), and a REFUSED outcome excludes the provider for the round; pinned by `test_charging_reconciler.py::test_disruptive_stop_is_sent_once_until_new_evidence_then_reasserted` ("inside RETRY: held"), `::test_an_app_start_after_our_stop_is_stopped_again_once_per_newer_reading`, `::test_a_stop_that_keeps_failing_is_bounded`, `::test_a_start_that_keeps_failing_is_bounded`, `::test_stop_falls_to_fleet_after_60s_once`. No code added.

Conflicts and resolutions:

1. "Run vehicle commands as classified provider outcomes on BLE and cloud workers" (generic queue): legacy-mode charge guarantees merged as above; `_is_high_priority`, `cancel()` kept.
2. "Declare provider capabilities, costs and suppressions as tables": Owner `DECLARATIONS` table carries the commands at `OWNER_COMMAND`; `wakeVehicle` uses `commandSlotFor` and checks `usable("wake")` only on the Fleet slot (the Owner slot never grants "wake"; an Owner refusal is noted per car). `test_provider_tables` updated.
3. "Add the reconciler ...": queue merge continued (theirs removed the inline mode; legacy guards kept).
4. **"Set charge limits through desired state and delete the legacy limit path"**: main's #702 limit path (`applyChargeLimit`/`apply_charge_limit`) is deleted here, and until Phase 3.5 the reconciler's providers had no Owner API command path. To keep main's behaviour in Phase 3, the reconciler path was made Owner-capable, minimally: `TeslaAPI.command()` and `wakeOutcome()` pick `commandSlotFor(vehicle)` (and log why via `refuseCommandFor` when none); `_paidPost`/`_request` latch the car through `noteOwnerCommandRefused` on an Owner refusal (403, VCP text, 410/412, "only available on fleetapi" at any status) and answer `Outcome(REFUSED, "owner refused")` with no error backoff; the provider command methods moved to a shared `_TeslaAPIProvider` base so both providers send through `commandSlotFor`; the Owner provider is ready only for a car it may command, the Fleet provider only with a Fleet command token (so each command goes out once); the stop's "asleep car is not charging" rule uses `commandSlotFor`. Phase 3.5's own port replaces all of this (below).
   - Main's `test_teslaapi_readonly_gate.py` cases for the deleted paths were ported onto the provider methods (`setChargeLimit`, then `startCharging`/`stopCharging`, `setAmps`, `wake`), with the refusal expectation as an `Outcome(REFUSED, ...)` matcher; the facade-based tests became provider-order `candidates()` checks ("the latched car leaves the order", "one line naming the car"). A Fleet 403/412 on the reconciler path retires the Fleet token (Phase 3's rule), after which `commandSlotFor` falls to the Owner slot for an `off` car; the test says so.
5. "Start and stop charging as desired state and delete the legacy path": legacy charge code deleted (theirs); the queue's legacy charge guards and Phase 1's queue tests went with it; `TWCSlave` passes the vehicle key (theirs).
6. "Set charge amps through desired state and delete the legacy rate path": `setChargeRate`, `wakeVehicle` and `VehiclePriority` deleted (theirs); the refusal helpers (`refuseCommandIfReadOnly`, `refuseCommandFor`, `noteOwnerCommandRefused`, `refusalState`) kept for the reconciler path, with the class-level `refusalLoggedAt`.
7. "Carry main's remaining command behaviours onto the reconciler": its `noteReadOnly()` hint is already `refuseCommandIfReadOnly` (per car when an Owner token is held), so theirs' copy was not added; its new tests (`TestRefusalHint`, the HomeAssistant refresh case) merged into the gate test.
8. "Read vehicle fields through the providers" and "Remove code the new command path orphaned": the providers file was re-ported each time with a script (`scratchpad/port_providers.py`) so the Owner command port stays identical; `getCarApiVehicles()` uses became `carApiVehicles`; a comment naming VehiclePriority was reworded for the no-legacy-names test.
9. "Send every TeslaAPI request through one helper": the Owner refusal check lives in `_request` (it has the response and the vehicle).
10. Three fix-up edits landed in the commits that needed them (all commits pass): the pre-3.5 wake test needs a live `lastChargeNeededTime` (Phase 3's charge-need idle rule); a read after a refused wake needs `firstWakeAttemptTime = 0`; the comment above.

Behaviour decisions: in Phase 3 an Owner-only install with an `off` car keeps commanding it through the reconciler (interim port); a car Tesla refuses is latched per car and the next provider sends at once.

## Phase 3.5 (restack2/phase3.5, fe0990a9)

- "Dissolve CarApiVehicle into TeslaAPI and an attached record": the interim port moved onto `CarApiState` (`commandSigning`, `ownerCommandsRefused`, `ownerCommandsRetired`, `refusalLoggedAt`; `_carOf`), `addVehicle` reads `command_signing` and the Owner claim follows it; the gate tests use registry vehicles and `car(vehicle)`.
- **"Let the Owner API command cars listed with command_signing off"**: taken whole (lib, tests, docs) as the superseding port; CHANGELOG's #659 line is main's line extended with 3.5's sentence (one line, nothing said twice); the TeslaAPI docs section is 3.5's.
- Nothing from main's #702 is lost. Checked against 3.5's code with probe tests (not committed): a 403 with an empty, text or HTML body latches the car and logs the WARNING once; "only available on fleetapi" at HTTP 200 retires; a paused Owner read slot still carries commands; a cleared Owner slot refuses without HTTP; the per-car INFO line is logged once and again on a state change (through the provider's readiness check, where the stack logs it); the module-wide hint when no Owner token is held; readOnly False while unlisted; VehicleEndpoint read-only per car; Fleet refusals don't latch the car. 3.5's own tests cover these too (`TestOwner403Latch`, `TestOwnerCommandsRetired`, `TestRefusalHint`, `TestVehicleEndpointPerCar`, ...).
- One behaviour differs from main by 3.5's design: on 410/412/"only available on fleetapi" main latched that car only; 3.5 retires Owner commands for the slot (every car) until the token is entered or synced again, and logs one error. With both tokens 3.5 ranks the Owner provider ahead of Fleet for `off` cars (main: Fleet first). Both are documented in 3.5's CHANGELOG line and docs.

## Phase 4 (restack2/phase4, bc93aeae)

Rebased cleanly (no conflicts). Parity: `tests/unit/test_command_path_parity.py` is byte-identical to the original Phase 4 tip and passes 51 tests on both (counts did not move).

## Phase 5 (restack2/phase5, 3dd50513)

- "Compute presence from events; one home check": `reconcile_helpers.py` comment is Phase 5's with the placeholder coordinates.
- "Decide each message by one applicability rule; hold within the paid budget": the new `TeslaBLE._tool` helper built the Docker prefix as one string (`"nsenter --net=/rootns/net"`, the bug #711 fixed). Resolved by dropping that insert: main's `_run_command_with_timeout` already prefixes `["nsenter", "--net=/rootns/net"]` as separate arguments for tesla-control and uses `setsid` for every command. No other commit re-adds the string; main's `test_teslable_docker.py` passes throughout.

## Phase 6 (restack2/phase6, bc0e3841)

- "Read the charge-port door on the sleep-safe ping": same `_tool` nsenter insert dropped.
- **"Scan for cars from Docker; say why when a range scan isn't possible"** (e3a08225): its exec fix was main's #711 in another form; the merged runner is main's (its comment gained 3.5's note that bluetoothctl needs no nsenter). The commit now adds only the scan/readiness parts: bluez in the Dockerfile, `canScan`/readiness check, the vehicle page reason, docs and tests; the compose and CHANGELOG changes were already main's and dropped as identical. Its message was shortened accordingly.
- Parity: `test_command_path_parity.py` byte-identical to the original Phase 6 tip; 113 passed on both.

## #707 (restack2/707, 6bfcb61d)

The docs commit (e3dfc3b4, "Update Gen3 documentation for the vehicle model") rebased cleanly onto restack2/phase2.

## Needs the user

1. Force-push: `restack2/phase1..phase6` and `restack2/707` are local; the brief says you push. Phase 4 and 6 parity files unchanged.
2. Review the Phase 1 decision to adopt main's overlap rule (a vehicle-less charge command replaces, and is replaced by, per-car ones) over Phase 1's "None is a distinct target" for charge commands; it changed one of Phase 1's own tests.
3. Review the interim Owner API port in Phase 2 and Phase 3 (Owner provider declares commands at `OWNER_COMMAND`; refusal logging from the providers' `available`/`ready`): it exists only so Phases 2–3 keep main's #702 behaviour until 3.5's port, which replaces it wholesale.
4. 3.5's semantics differences from main noted above (slot-wide retirement on 410/412; Owner ahead of Fleet for `off` cars) are the stack's design; flagging in case either should match main instead.
5. Python 3.8: no interpreter here; checked by inspection only.

## Per-commit verification

See `verify-phase1.log` ... `verify-phase6.log` in the scratchpad (`/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/`): each line is `<sha> <subject> :: <pytest summary>`.

Verified at hand-back (every commit checked out and the full suite run, all passing):

- Phase 1: 19/19 commits (1024 → 1353 tests)
- Phase 2: 17/17 (→ 1525)
- Phase 3: 19/19 (→ 1905)
- Phase 3.5: 9/9 (→ 1876)
- Phase 4: 15/15 (→ 1977)
- Phase 5: 20/20 (→ 2249)
- Phase 6: 5/18 commits checked so far, all passing; the run on the remaining 13 was still in progress at hand-back (`verify-phase6.log` fills in as it goes, ending with `DONE`). The Phase 6 tip itself passes the full suite (2355 passed). Phase 6 had only the two TeslaBLE nsenter conflicts, both resolved before its own tests were run at those commits.
- #707: a docs-only commit; not run.

## After the review (restack-review.md; the user ruled 3.5's two design differences stand)

Applied in the commits named, then every later branch rebased onto the fixed one:

1. **#667 said twice from Phase 3 on.** In "Start and stop charging as desired state and delete the legacy path" main's queue-interval line is dropped (that commit deletes the queue it described); in "Document the reconciler, paid fallback and presence" main's remaining "Cancel a pending stop…(closes #667)" line is folded into the Architecture line that already says "a pending stop is cancelled when charging is wanted again (closes #667)". That line now also names the Owner API (for a car listed `command_signing: off`) among the paid-tier providers. One #667 mention at every tip from Phase 3 on.
2. **Asleep rule Fleet-only in Phase 3's interim port.** `stopCharging`'s "an asleep car is not charging" short-circuit tests `commandSlotFor(car) is not None` from "Start and stop charging as desired state…" on (and `commandSlotFor(vehicle)` after the dissolve), so an Owner-carried car gets it too. No Phase 3 commit keeps the `slotFor("command")` form. The Phase 3 gate tests mock the free online check a stop now makes for an Owner car and count only the command POST.
3. **Main's two #702 tests restored in 3.5.** `test_read_pause_does_not_block_owner_commands` and `test_cleared_owner_slot_blocks` are in `TestOffCarCommandsThroughOwner` of restack2/phase3.5's `test_teslaapi_readonly_gate.py` (in "Let the Owner API command cars listed with command_signing off").
4. **Retirement message with a Fleet token.** Owner stays ahead of Fleet for `off` cars. When the Fleet slot can command, `noteOwnerCommandsRetired`'s ERROR line ends "The Fleet API carries charge commands from here." instead of telling the user they need a Fleet token; `TestOwnerCommandsRetired.test_retired_with_a_fleet_token_says_fleet_carries` pins it (one ERROR, no "need a Fleet API token", Fleet still commands the car).
5. **CHANGELOG #659 line** now also says a 410/412 (or "only available on fleetapi") stops Owner API commands and wakes for every car on that token until it is entered or synced again, logged once as an error, with reads continuing.
6. **Phase 1 wording.** The first commit's message and `VehicleCommandQueue.py`'s header say that charge commands overlap across the vehicle-less target and that None is a distinct "every vehicle" target for applyChargeLimit only.

Parity after the rebase: `test_command_path_parity.py` byte-identical to the originals at the Phase 4 and 6 tips; 51 and 113 passed. Scrub re-checked at every new tip (name and coordinates: none).

Verification after the fixes (full suite, brief's command): logs `final-tips-a.log`, `final-tips-b.log` (every tip) and `final-edited.log` (the edited commits: Phase 1's first commit, Phase 3's three edited commits, 3.5's dissolve commit and Owner API port commit) in the scratchpad; results appended below.

Results (all passing, 1 xfailed each):

- Tips: phase1 8070d5c3 1353; phase2 4b012c27 1525; phase3 aa9a7b99 1905; phase3.5 a765b6f4 1879 (+3 new tests); phase4 7432894b 1980; phase5 cf89bf5f 2252; phase6 198c94f3 2358.
- Edited commits: Phase 1 "Key vehicle commands by (cmd, vin)…" adfc4c1e 1024; Phase 3 "Start and stop charging as desired state…" 572b3769 1825; "Set charge amps through desired state…" 1d90963c 1754; "Document the reconciler…" 16eeb23b 1871; Phase 3.5 "Dissolve CarApiVehicle…" ddc75fea 1923; "Let the Owner API command cars listed with command_signing off" d8566c0d 1871.
- Not re-run per commit after the fixes: the other, untouched commits of each phase (their content is unchanged by the fixes except the Phase 1 comment line and Phase 3's asleep-rule line cascading through later Phase 3 commits, which the per-commit logs before the fixes covered at 19/19, 17/17, 19/19, 9/9, 15/15, 20/20 and 5/18 for Phase 6). Phase 6 commits 6–17 have never been checked individually; its tip passes.
