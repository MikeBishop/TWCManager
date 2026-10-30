### Task 6: Collapse the EVSE scaffolding; sweep, guard, line check, live check (expected lib Δ ≈ −310)

With one distributor, nothing switches on controller type, so:
- the `EVSEController` ABC, the `Gen2TWCs` controller and the `VehicleEndpoints` controller class go;
- the `EVSEInstance` ABC shrinks to the mixin its four users need: `convertAmpsToWatts`, `convertWattsToAmps` and the defaults `currentVIN ""`, `controllers []`, `vehicleKey None` and `occupied None`.

Budgets come from one method. Car endpoints come from one function without the cache: `VehicleEndpoint` holds no state of its own, since a rate lives in `DesiredStore`.

`ChargingPoint` loses the aggregates no caller reads. Expected, but confirm by grep at the task's BASE: `isCharging`, `occupied`, `currentPower`, `currentVIN`, `currentAmps` (:82–87) and `isLocal` (:55–57; callers use the members' `e.isLocal`) (F22). Gen2/Gen3/Vehicle endpoints lose `currentPower`. `getAllEVSEs` and `chargingPoints` (one caller each) are inlined into `distributeEVSEPower` (F22). The stale docstring at `VehicleEndpoint.py:4–5` ("the distributor runs on the serial thread") is corrected.

`TWCMaster`'s class-level `settings` dict (:69–84) **stays**: `test_charging_points.py` and `test_distributor_loop.py` build masters with `TWCMaster.__new__`, which reads it (a class-level reader, F21).

**Files:**
- Delete `lib/TWCManager/EVSEController/EVSEController.py`, `EVSEController/Gen2TWCs.py` and `EVSEController/VehicleEndpoints.py`. Move `_blindTWCs`, `_telemetryPluggedIn` and the listing rule unchanged into `EVSEInstance/VehicleEndpoint.py` as `vehicleEndpoints(master) -> List[VehicleEndpoint]`.
- Modify `EVSEInstance/EVSEInstance.py` (≈ 25 lines), `ChargingPoint.py`, `Gen2TWC.py` (docstring, `controllers`), `Gen3TWC.py` and `VehicleEndpoint.py` (drop `currentPower`), and `EVSEController/Gen3TWCs.py` (plain class; `name`, `maxPower` and `stop` stay; still registered as module type `"EVSEController"` under the name `"Gen3TWCs"`, which `getModuleByName("Gen3TWCs")` callers use).
- Modify `TWCMaster.py`: delete the `Gen2TWCs`/`VehicleEndpoints` registration; the endpoints are `[s for s in getSlaveTWCs() if s.heardFrom] + vehicleEndpoints(self) + (gen3.allEVSEs if gen3 else [])` (the `heardFrom` filter carried over from `Gen2TWCs.allEVSEs`, F19), built inside `distributeEVSEPower`; add `_budgets()`; `distributeEVSEPower` uses it.
- Tests (plumbing): `test_charging_points.py`, `test_distributor_loop.py`, `test_vehicle_endpoint.py`, `test_gen2_idle_minimum.py:10,45`, `test_telemetry_registry.py`, `test_gen3twc_provider.py`, `test_provider_registration.py`, `test_provider_tables.py`, `test_held_limits.py`, `test_reconciler_queues.py` and the others from the Global grep (tests/unit included). Plus the guard and the line check.

**Interfaces:**
- Produces:
  - `TWCMaster._budgets() -> Dict[str, float]`: `{"Gen2TWCs": cfg.get("wiringMaxAmpsAllTWCs", 6) × cfg.get("defaultVoltage", 240) × cfg.get("numberOfPhases", 1), "VehicleEndpoints": inf, "Gen3TWCs": gen3.maxPower}` (the last only when registered). The values and `.get` defaults are BASE `Gen2TWCs.maxPower`'s (`Gen2TWCs.py:38–44`), so `test_distributor_loop.py`'s `__new__` master, which has no `wiringMaxAmpsAllTWCs`, keeps working.
  - `vehicleEndpoints(master) -> List[VehicleEndpoint]`.
  - The `controllers` names on endpoints are unchanged.

- [ ] **Step 1: Guard test.** Add `test_retired_settings_keys_load_and_are_ignored` (a master loading a config with `greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and settings with `spikeAmpsProactively`/`spikeAmpsReactively` starts and runs `controlPass` with offers equal to a master without them). Extend `test_no_legacy_command_paths.py` with:
  - `test_no_retired_allocator_names_remain`: `git grep -nE "Gen2TWCs\(|VehicleEndpoints\(|\(EVSEController\)" -- lib/TWCManager` is empty (no `-w`: a word match never sees `Gen2TWCs(self)`, F18), and `git grep -nwE "_evseTargetAmps|pointOwnsAmps|spikeAmpsProactively|spikeAmpsReactively|getSpikeAmps|setSpikeAmps|spikeAmpsToCancel6ALimit|set_last_amps_offered|stopRequested|_queueChargeRate|_setCarAmps|APIcontrol" -- lib/TWCManager html tests/integration tests/API docs` is empty;
  - `test_no_flex_or_dampening_code_remains`: `git grep -nwE "allowed_flex|getAllowedFlex|setAllowedFlex|useFlexAmpsToStartCharge|lastAmpsDesired|timeLastAmpsDesiredFlipped|dampenChanges" -- lib/TWCManager` is empty (lib only: the docs keep an "ignored" note, and `tests/API/test_getConfig.py:22` is a commented config dump);
  - `test_one_distributor_entry`: `distributeEVSEPower` is called only from `TWCMaster.controlPass`.

  Run it → FAIL (the scaffolding names).
- [ ] **Step 2: Collapse** as above. Every touched test is PLUMBING-ONLY (construction or import); record each.
- [ ] **Step 3: Orphan sweep.** For every `def` in the files Tasks 1–6 touched, run `git grep -nw <name> -- lib html`. Delete any with no caller, unless policy reach applies (a property or data attribute on a module object). Report each with evidence.
- [ ] **Step 4: Full suite** → PASS. `black --check` on the touched files.
- [ ] **Step 5: Line check** (report; the target is a target, not something to fit):

```bash
git ls-files lib | grep '\.py$' | xargs cat | wc -l                      # BASE 27,425; projected ≈ 26,615
git diff --shortstat 1029809b -- lib; git diff --shortstat origin/main -- lib
git diff --numstat 1029809b -- lib | awk '{a+=$1; d+=$2} END {print "added", a, "removed", d; exit !(d > a)}'
```
  Expected: the awk exits 0 and the total is < 27,425. Record each task's actual vs expected delta in the ledger. Do not pad deletions.
- [ ] **Step 6: PR notes** in the ledger, for the Phase 4 PR body:
  - A short **"Not ported into the rearchitecture"** section. Each item can return as a feature if there's demand:
    - **6 A spike workaround (a).** It briefly offered 16 or 21 A to get past a car-side 6 A limit that a 2017 car firmware imposed after an offer increase. It is known only from code comments and is likely long fixed. `spikeAmpsProactively`/`spikeAmpsReactively` are now ignored and the Debug page row is gone.
    - **Flex (c).** `greenEnergyFlexAmps` / a policy's `allowed_flex` let a car start or keep charging when its share was up to that many amps short of the minimum (`useFlexAmpsToStartCharge` for starting). Main's default path (TeslaAPI enabled) already ignored it since #483; only TeslaAPI-disabled installs lose it.
    - **Track Green dampening (f).** It held a drawing car at the TWC minimum for `startStopDelay` after its share crossed the minimum, to avoid start/stop churn. On main's default path a compatibility write had mostly disabled it since #483. The 60 s start/stop gates still protect the TWC relay.
  - (b), (d) and (e).
  - #690 closed.
  - The RS-485 outbox.
- [ ] **Step 7: Commit.** `git commit -m "Collapse the EVSE scaffolding the second allocator needed; guard the retired names"`
- [ ] **Step 8: Live check on `twcmanager`.** Deploys and restarts are pre-approved. The implementer does not run it; the user schedules it.
  - **Box:** Gen2 protocol 2, mode 1, `commandPolicy: ble_only`, a BLE-paired Model 3, TeslaMate→Owner (read-only), a Fleet slot.
  1. **Prepare.**
     - Record the box HEAD and back up `settings.json`.
     - Set `logLevel` so INFO8 and DEBUG for `Slave`/`Master` reach the journal.
     - Pause the watchdog cron.
  2. **Deploy** (bundle `<box HEAD>..vehicle-model/phase4`) and restart. Expect:
     - `ControlTick` started;
     - no `Main loop stalled` after boot;
     - the first SHB lines show `M: 00 …` until the first tick, then `09 …`.
  3. **Restart with the car charging at 32 A.** The wire offer goes straight from "no change" to 32. It never shows `0000` (Review Focus 1).
  4. **Track Green flicker** (or set Charge Now 10 A, then 4 A, then 16 A):
     - offers follow within ~1 s;
     - a decrease holds 5 s;
     - below the minimum, the BLE stop goes once after 60 s;
     - back above it, a start.
     - Zero `Car API … command/` lines (ble_only).
  5. **Debug page:** "Send TWC message" (`fbeb…`) still gets a reply in "Last TWC response"; the Spike Amps row is gone.
  6. **Tokens:** after 5 min, `Attempting token refresh` (if due) comes from the background thread (`BackgroundTask` in the log context), never during a stall.
  7. **Paid-call count** for the window: `journalctl … | grep "Car API" | grep -oE "wake_up|vehicle_data|command/[a-z_]+" | sort | uniq -c`. Expect 0.
  8. **Roll back** unless kept.

---

## Line budget (lib/ `.py` only, `git ls-files lib | grep '\.py$' | xargs cat | wc -l`)

Fixed points: origin/main 23,180; BASE 1029809b **27,425**.

| Task | Out | In | Expected Δ (range) | Running total |
|---|---|---|---|---|
| 1 outbox; VIN check digit | `stopRequested` 10, check-digit table 80 | outbox 12, `vinCheckDigitValid` 18, flushes 4 | **≈ −50** (−35..−65) | ≈ 27,375 |
| 2 token single-flight; refresh off the loop | loop block 12, `lastTeslaTokenRefreshCheck` 1 | single-flight 20, discard and 401 guard 6, `restore` lock 2, handler with `finally` 9 | **≈ +22** (+15..+30) | ≈ 27,397 |
| 3 tick; one distributor; flex deleted; session split | fair-share branch 50, `non_gen2` gate + docstring 25, registration 21, loop calls 12, flex plumbing (TWCMaster 7, Policy 3, TWCSlave 5) 15 | `ControlTick.py` 47, `controlPass` 5, pure count 5, register 3, `heardFrom` 4 | **≈ −58** (−40..−80) | ≈ 27,339 |
| 4 offers on the tick; points own car amps; spike and dampening gone | 818–1121 ≈ 300, `set_last_amps_offered` 74, car helpers 53 (`minAmpsToOffer` kept), spike plumbing (TWCMaster 7, linkready 11, HTTP 8), Gen2TWC shims 8, attrs (incl. flip tracking) 8, unused imports 4 | `offerFor` + `_capped` 48, `Offer`/`OfferContext` 11, heartbeat send 8, `_carKeys`/`confirmed`/`anonymousCars` + key-only rates with own-label clear 60, lift counter 6, `controlPass` (offers, cancel, silence check) 14 | **≈ −320** (−300..−340, pre-flight F22) | ≈ 27,019 |
| 5 gates on the tick | 541–658 ≈ 117 | `chargeGate` 16, `controlPass` mapping 13 | **≈ −88** (−75..−100) | ≈ 26,931 |
| 6 EVSE scaffolding; sweep | `EVSEInstance` ABC 122, `EVSEController` 50, `Gen2TWCs` 44, `VehicleEndpoints` class/cache/`_get_carapi` 35, point aggregates incl. `currentAmps`/`isLocal` ≈ 48, `currentPower` ×3 9, `getAllEVSEs`/`chargingPoints` inlined 8, sweep ≈ 10 (class-level `settings` kept) | `_budgets` 8, endpoint list 3 | **≈ −315** (−260..−370) | **≈ 26,616** |

- **Projected end: ≈ 26,615** (range ≈ 26,500–26,720), after the pre-flight rulings. That is ≈ −810 from BASE and ≈ 3,435 above main.
- **Size (user, 2026-10-17):** proceed; the parity goal is softened. The ≈ −2,000 stretch is not reachable in Phase 4's scope without further feature cuts; ≈ 3,435 lines separate the projection from main.

## Decisions made in this plan

1. **The tick is its own thread, not the reconciler's.** The reconciler's 1 s `TICK` already exists, but it wakes on every desired-state change (`Desired.changed`), so a distributor pass there would run many times a second under load. A separate 45-line thread keeps the spec's table literal: the tick publishes; the reconciler compares and dispatches. Both are daemon threads, and the tick stops first at shutdown.
2. **Fair share stays the distributor's water-fill (b)** (ruled by the user, 2026-10-17). Every install with TeslaAPI enabled (the default: `TeslaAPI.py:198`, `TWCManager.py:759`) already runs it at BASE. The legacy "share by cars charging" fair share runs only with `vehicle.TeslaAPI.enabled: false`.
   - The one place the default path still divides by cars charging is the idle-TWC probe (`budget / carsCharging > minOffer`). That is ported exactly into `offerFor`.
   - The alternative, porting the legacy formula `min(B/N, B − others' draw)` as the distributor rule, would change allocation on nearly every install, including mixed Gen2+Fleet+Gen3 ones.
3. **Flex is deleted, not ported (c)** (user, 2026-10-17). It was dead on the default path since #483; porting would have re-enabled it for nearly every install. It is listed in the PR's "Not ported" section.
4. **Token single-flight waits without a lock and shares the result.** No lock is held across the POST, and the waiter's own refresh token is never spent. A late answer never overwrites a paste. Rejected: skipping for the second caller (changes `_request`'s 401 retry path), and a lock held across the POST (violates "no I/O under locks").
5. **The wiring cap is re-checked on every offer (e).** BASE capped only when the desired offer changed (`set_last_amps_offered`, `TWCSlave.py:1191`), so another TWC ramping up left this one's offer uncapped: the sustained overshoot the derating rule calls a bug. The cap's floor (`minAmpsTWCSupports`) and log line are BASE's; the log is de-duplicated.
6. **The 5 s decrease hold is kept.** It sits in the spike `if/elif` chain but limits any decrease, spike or not (`TWCSlave.py:1080–1091`).
7. **The outbox is FIFO and unbounded.** Every producer is rate-limited at BASE: the 60 s kWh poll, VIN queries (≤ 6 per session), user actions and the per-heartbeat stop.
8. **The VIN and kWh background tasks stay.** They carry dedupe (`_taskKey`) and the 5 s VIN-confirmation delay. Only their send moved.

9. **Track Green dampening is deleted, not ported (f)** (user, 2026-10-17). A compatibility write had mostly disabled it on the default path since #483; the 60 s start/stop gates (Task 5) remain the relay protection. It is listed in the PR's "Not ported" section.
10. **Token refresh reschedules itself on the background queue (Task 2).** `queue_background_task(delay>0)` inserts into the delayed list without the per-cmd dedupe (`TWCMaster.py:1349–1361`), and the earlier run's key is long cleared when the next one is promoted 300 s later, so the re-queue is never coalesced away (unlike `bleScan`'s immediate requeue). Task 2's `test_refresh_tokens_task_requeues_itself` pins it.

## Considered and rejected (the coordinator's "biggest candidates")

| Candidate (lines at BASE) | Why not in Phase 4 |
|---|---|
| `TWCManager.py` RX parser (≈ 900) with the duplicate `Protocol/TWCProtocol.parseMessage` (≈ 130) | RS-485 protocol handling: a spec non-goal, and the highest-risk code on a live charger. A parser unification is its own design, with a hardware test matrix. |
| Fake-slave mode (`fakeMaster` 0/2): `TWCManager.py` slave branch ≈ 360 + `TWCSlave.send_slave_heartbeat` ≈ 145 | A feature (#482), and protocol handling. |
| `WebIPCControl` (410) + `html/index.php` | A live legacy web UI (it reads `lastAmpsOffered` and sends TWC messages): a feature cut. |
| `Interface/Dummy` (405) + `TWCProtocol.createMessage` | The test and debug surface (`/api/sendTWCMsg` uses `createMessage`). |
| `Vehicle/Reconcile/*` (≈ 1,900) and `VehicleCommandQueue` (250) | They are Phase 3's design (lanes, attempt records), not duplicated by anything Phase 4 builds. Shrinking them is a Phase 3 follow-up with its own behaviour pins (paid-call oracle). |
| `Targets.py` presence (146) and `_blindTWCs`/`_telemetryPluggedIn` (≈ 60) | Presence: Phase 5. They move files in Task 6 unchanged. |
| Gen3 solver, `WallConnectorVins`, `_correlate` (≈ 940) | Gen3 is the majority of deployed WCs (memory); no feature may go. |
| Folding `TWCSlave` and `Gen2TWC` into one class (≈ −40 more) | Touches ≈ 20 test files for ≈ 40 lines. Task 6 removes the shims only. |
| The protocol comment blocks in `send_master_heartbeat` (≈ 90) and `_amps_heartbeat` (≈ 30) | They are the only documentation of Gen2 heartbeat bytes. |
| Moving the Policy thread onto the tick (≈ −40) | The spec keeps Policy as its own tier with its own interval. |

**Pre-existing, not changed:** the distributor's `0 < offer < point.minPower → 0` rule uses the point's minimum, which for a TWC point is the TWC's own minimum. So mode-3 layering below the TWC floor is never reached through the distributor in production; `test_amps_reconciler.py::test_mode_3_layers_below_the_floor_and_holds_the_twc_at_its_floor` reaches it by calling `setTargetPower` directly. Phase 4 keeps this as it is; two-pass admission (#709) is where point minima are revisited.

## Self-review (against 1029809b)

- **Every symbol planned for deletion exists** (line numbers checked at 1029809b):
  - TWCSlave: `stopRequested` :38/:434; `_anonCars` :126; `_setCarAmps` :136; `_clearCarAmps` :150; `_carRateConfirmed` :157; `_queueChargeRate` :167; `_requestVehicleRateRaise` :170; `_resetVehicleRateRaised` :181; `_ampsKeys` :87; `APIcontrol` :95; `set_last_amps_offered` :1180; the gate block :541–658; the allocation :767–1121.
  - TWCMaster: `spikeAmpsToCancel6ALimit` :91; `getSpikeAmps` :819; `setSpikeAmps` :1954; `lastTeslaTokenRefreshCheck` :55; the `non_gen2` gate :561; `Gen2TWCs` registration :168–172; `num_cars_charging_now` :1262.
  - Gen2TWC: `pointOwnsAmps` :28; `_evseTargetAmps` :40; `stopRequested` :44; the compat write :225.
  - EVSEController.py, Gen2TWCs.py, VehicleEndpoints.py and EVSEInstance.py as files.
  - TWCManager.py: spike :1232–1242; registration :756–776; distribute :925–930; IPC :983–985; expiry :1000–1004; token :1006–1017; check digit :1491–1570.
  - HTTPControl :941–955 and :2005–2012; WebIPCControl :258; `debug.html.j2:113–116`; `docs/Debug.md` "Spike Amps".
- **Every caller is listed** in the table and "Other callers checked":
  - templates: debug, showStatus, Modern main and jsrefresh;
  - `html/index.php` (via WebIPC, unchanged);
  - `tests/integration` (HTTP `sendStartCommand`/`sendStopCommand` only: the status code and body are unchanged, the send is deferred);
  - docs: Debug, Interface_RS485, PolicyCustomization, Gen3 docs (wording "EVSEController" kept, still true of Gen3TWCs' module type).
- **Green after every task.**
  - Task 3 keeps `_evseTargetAmps` until Task 4.
  - Task 4 keeps `Gen2TWCs`/`VehicleEndpoints` until Task 6.
  - `drive()` changes once (Task 3), and every later task reuses it.
- **Spec coverage:**
  - "Threading" rows: RS-485 protocol-only (T1, T3, T4, T5); tick (T3–T5); token off the loop and per-slot (T2).
  - "Everyone moves" (T3, T4, T5).
  - Idle minimum (T4 `offerFor` + characterization).
  - Layered actuators (T4 `ChargingPoint`).
  - 6 A dropped and called out (T4, T6).
  - `settings` lock: already in place since Phase 1; `settingsLock` is unchanged.

## Rulings (user, 2026-10-17)

Pre-flight (`.superpowers/sdd/2026-10-17-vehicle-model-phase4-control-tick/preflight.md`, GO-WITH-FIXES) rulings F1–F22 are applied in the task text:
- F1, F8: `tickThenBeat` and `offersThenBeat`; the `amps_max` plumbing rows; parity counts never move.
- F2: the `countSlaveTWC() > 0` gate stays.
- F3: `pointAmps`.
- F4: the stop cancel moves in Task 4.
- F5: `minAmpsToOffer` kept.
- F6: the mode-2 lift reset.
- F7: the silence skip.
- F9, F19: `heardFrom` in `Gen2TWCs.allEVSEs`, and then in `distributeEVSEPower`.
- F10: Task 2's 401 guard, `restore` lock and `finally`.
- F11, F12, F21: mapping and line references.
- F13: own-label clear.
- F14: ownership note.
- F15: IPC copy and rate.
- F16: shutdown flush and join.
- F17: restart test.
- F18: guard regex.
- F20: VIN case and the len-0 branch.
- F22: the extra deletions.

1. **Size:** proceed with the honest projection (≈ 26,615, after the pre-flight rulings); the parity goal is softened.
2. **Fair share:** the distributor's water-fill stays (Decision 2).
3. **Flex and dampening:** not ported; deleted like the spike workaround, settings keys ignored, all three listed in the PR body's "Not ported into the rearchitecture" section (Decisions 3 and 9).

## Additions from the controller (user decisions and carried findings, 2026-10-17)
1. **Comment sweep (user rule; see global-constraints.md "Comment rule").** Across every lib file the vehicle-model stack changed versus origin/main (`git diff --name-only origin/main...HEAD -- lib`), rewrite or delete comments that narrate history (how it used to be, when/why it changed, which review/ruling prompted it, lists of rejected alternatives) so the code reads as designed. Remove phase names, PR/issue numbers and review/ruling IDs from code comments. Keep comments that explain why the current design is what it is, and alternatives only where the obvious approach is wrong. Test files: same rule for comments you touch; don't churn test files only for this. Report the comment-line delta separately (lib comment lines before/after).
2. **Guard test:** lib code comments contain no `Phase \d` and no `#\d{3,}` issue/PR references (allowlist anything that is genuinely not a reference, with a reason).
3. **chargeGate takes the key:** `chargeGate(now, key)` (or returns the key it decided for), so controlPass applies the decision to the key it was computed for (Task 5 review minor 1).
4. **Vacuous test assertion:** replace the send_master_heartbeat part of `test_no_gate_acts_before_the_first_offer` (test_control_tick.py:413–414) with a controlPass on a slave not yet heard from.
5. **PR notes** must list, besides the plan's items: "Not ported into the rearchitecture" (6 A spike workaround, flex, Track Green dampening — what each did, main's default path already had flex/dampening mostly disabled, can return on demand); (g) Gen3-only installs are controlled; (h) vehicle-only installs are controlled (BLE-only: no paid calls; Fleet-only: one $0.001 command per hour at 16 A in the parity row) and need the RS-485 interface disabled; a car only BLE/HA knows waits for the presence work; the first periodic token refresh runs 300 s after start; rate-before-start ordering.
