# Task 6 report

**Status:** DONE_WITH_CONCERNS. Branch `vehicle-model/phase4`, BASE dc2609f5. Not pushed.

Commits:
- `6dd84437` Collapse the EVSE scaffolding the second allocator needed; guard the retired names. This commit also has `chargeGate(now, key)` (Addition 3) and the new vacuous-test check (Addition 4).
- `159070c0` Keep one copy of the settings defaults.
- `02bfb49d` Make the stack's comments say why, not where they came from. This is the comment sweep plus the Phase/#NNN guard.
- `f506104d` Drop review tags from the endpoint and charging-point tests. Both files were already heavily changed, so their `# A17` / `# review I1` / `(M1)` tags went too. Tests only; the suite is green.

## Implementation

### Collapse (`6dd84437`)

**Deleted**
- `EVSEController/EVSEController.py`, `EVSEController/Gen2TWCs.py` and `EVSEController/VehicleEndpoints.py`.
- Both package `__init__.py` files. They only re-exported the deleted ABC. The tree uses namespace packages (`setup.py`: `find_namespace_packages`), and other packages such as `Interface` already have no `__init__`.

**`EVSEInstance.py`** is now a 27-line mixin:
- `convertAmpsToWatts` and `convertWattsToAmps`;
- `currentVIN ""`, `vehicleKey None`, `occupied None` and `controllers []`, as class attributes.

**`VehicleEndpoint.py`**
- Gains `vehicleEndpoints(master) -> List[VehicleEndpoint]`. `_blindTWCs`, `_telemetryPluggedIn`, `_unknownKey` and `POWER_FLOWING_AMPS` are moved unchanged, with `master` passed in.
- The listing rule is unchanged, including the TeslaAPI enabled check. That check was in `_get_carapi` and is part of the rule.
- No cache: a fresh endpoint is built per call.
- The stale "distributor runs on the serial thread" docstring is corrected to say the control tick.
- `isLocal` and `controllers` are class attributes.

**`ChargingPoint`**
- Loses `isLocal`, `isCharging`, `occupied`, `currentAmps`, `currentPower`, `currentVIN` and `_preferLocal`, plus the section dividers.
- Grep confirmed no lib reader at BASE. Points are read only by `controlPass` (`confirmed`, `localEndpoints`) and `distributeEVSEPower` (`wantsToCharge`, `isReadOnly`, `min/maxPower`, `controllers`, `ID`, `setTargetPower`).

**`Gen2TWC`**
- New docstring; `isReadOnly`, `isLocal` and `controllers` are class attributes.
- The `currentVIN` property shim, the `__init__` and its ordering comment are gone.
- `currentPower` and `currentAmps` (an orphan) are gone.
- The `isCharging` bool property is **kept** (concern 2).

**`Gen3TWC`**
- `currentPower`, `currentVIN` (the default covers it) and `isCharging` (an orphan) are gone.
- `isReadOnly`, `isLocal` and `controllers` are class attributes.

**`Gen3TWCs`** is a plain class. `name`, `maxPower` and `stop` stay, and it is still registered as type `"EVSEController"` named `"Gen3TWCs"`.

**`TWCMaster`**
- The `Gen2TWCs`/`VehicleEndpoints` registration and imports are gone.
- `getAllEVSEs` is inlined into `chargingPoints()`, which builds `[s for s in getSlaveTWCs() if s.heardFrom] + vehicleEndpoints(self) + (gen3.allEVSEs if gen3 else [])`. The order matches BASE's module registration order.
- New `_budgets()` (BASE's values and `.get` defaults).
- `distributeEVSEPower` uses `_budgets()`. Its `if not controllers: return []` early exit is gone: after the collapse it would have stopped every non-Gen3 install from distributing.
- **`chargingPoints` stays a method** (concern 1).

**`chargeGate(now, key)`**: `controlPass` passes the key it read, so the decision is applied to the car it was computed for. The `key is not None` guard in `controlPass` is gone, because `chargeGate` returns None for a None key.

**The class-level `settings` dict stays**, as F21 requires.

### Settings defaults (`159070c0`)

`TWCMaster` spelled the same 14 defaults out four times: the class dict, `__init__`, `loadSettings`' no-file branch and its merge. One module constant, `DEFAULT_SETTINGS`, now feeds all four (`dict(...)` copies). The class-level `settings` is kept for the `__new__` test masters. This is real duplication in a touched file (−42 lines). It was found during the sweep and is not in the brief.

### Comment sweep (`02bfb49d`)

I reviewed every comment and docstring line the stack added versus origin/main (1,720 lines; script `scratchpad/t6/added_comments.py`), plus a marker grep across every lib file.

**Removed or restated**
- Issue/PR numbers: `#659` ×7, `#660` ×3, `#690`, `#591`, and upstream's own `(closes #377/#442/#586)`.
- Review/ruling IDs: I1–I9, C1, M1/M4/M6/M8/M11, N1/N2, H2, c2/c4/c6, U2, L26, L28.
- Phase references: "Phase 1's narrow Forget … Phase 6", Targets "until Phase 5 replaces it", and HTTPControl's upstream "During Phase 1 (backwards compatibility)", now restated.
- History narration: "As main"/"main's"/"on main", "BASE's heartbeat rules, without the 6 A spike or Track Green dampening", "today's 5 s sleep", "HA's former start/stop gate, and main's 15 s Fleet rate pacing", "from presence/2's ChargeLimitRules", "as update_vehicle_data always has", "no longer read", "any more".
- The stale `Gen2TWCProvider.setAmps` "serial loop sends on the next heartbeat" comment (a Task 4 minor).
- `distributeEVSEPower`'s docstring paragraph that repeated the idle-TWC comment below it.

**Kept:** comments that give the reason for compatibility behaviour, such as "older releases stored form VINs as typed", "Releases before 1.4.0 never recorded pairing" and the held-limit migration. Also kept: `Vehicle.py`'s "requiring equal values made a parked car … cost a paid read", where the obvious approach is wrong.

**Yield:** almost every comment the stack added is a why-comment, so the honest yield was small: −11 comment lines in this commit. The bigger comment drop came with the collapse (−215 comment lines, mostly the ABC docstrings). A few hundred lines from the sweep alone was not available without deleting design explanations.

## Guards

- `tests/unit/test_no_legacy_command_paths.py`:
  - `test_no_retired_allocator_names_remain`: the brief's two `git grep`s, verbatim. No `-w` on the first.
  - `test_no_flex_or_dampening_code_remains`: lib only.
  - `test_one_distributor_entry`: an AST walk. Only `("TWCMaster.py", "controlPass")` calls `distributeEVSEPower`.
  - `test_code_comments_name_no_phase_or_issue`: tokenize COMMENT tokens plus AST docstrings across `lib/**/*.py`, against `Phase \d|#\d{3,}`. Victron's `# Output Power Phase A` does not match, and CSS `#666` lives in strings, so no allowlist was needed.
- `tests/unit/test_control_tick.py::test_retired_settings_keys_load_and_are_ignored`:
  - It runs two real `pureGen2` masters. One has `greenEnergyFlexAmps`/`useFlexAmpsToStartCharge` in config and loads a `settings.json` holding `spikeAmpsProactively`/`spikeAmpsReactively` through `loadSettings()`. The other has neither.
  - In both, `controlPass` gives `[(0, 0), (10, 10)]` for 10 A over two charging cars. 5 A each is below the minimum, where flex used to let both charge.
- `test_no_gate_acts_before_the_first_offer` (Addition 4): the vacuous `send_master_heartbeat` assertion is replaced by `controlPass` on a slave not yet heard from. The test asserts the offer stays None and no `withdrawStartCharging` happens.

## TDD evidence

- **RED, step 1.** The new legacy-guard tests before the collapse: 1 failed (`test_no_retired_allocator_names_remain`: `Gen2TWCs.py:13`, `Gen3TWCs.py:156`, `VehicleEndpoints.py:21`, `TWCMaster.py:173`), 4 passed. The flex/dampening and one-entry guards were already green, because Tasks 3–5 had removed those names.
- **RED, other tests.** `test_no_gate_acts_before_the_first_offer` failed with `chargeGate() takes 2 positional arguments`. `test_retired_settings_keys_load_and_are_ignored` first failed on test plumbing (`loadSettings` needs a TeslaAPI module), and was then pinned at `[(0, 0), (10, 10)]`.
- **RED, comment guard.** Run against the lib at `159070c0` in a temporary detached worktree (removed and pruned afterwards): 1 failed with 19 hits, the first `HTTPControl.py:1912`. After the sweep: passes.

## Tests and results

- **Full suite** (`tests --ignore=tests/API --ignore=tests/integration`): **1947 passed, 1 xfailed, 1 warning**. That is the 1942 baseline plus 5 new tests. It was green before each of the four commits: 1946 at the first two commits, 1947 at the third and fourth. The warning is the pre-existing urllib3 `InsecureRequestWarning` in `test_enphase_ems` (checked with `-o addopts="" -rw`).
- **`tests/integration --collect-only -q`:** 212 collected.
- **Black:** `--check` clean on every changed lib file.

## Parity

The `test_command_path_parity.py` per-test request lists were recorded with `scratchpad/plug/paritycounts.py`:
- before Task 6 (dc2609f5): `scratchpad/t6/parity_before.jsonl`, identical to Task 5's after;
- after the collapse and orphan sweep: `scratchpad/t6/parity_after.jsonl`.

Both have 51 rows and are identical. No count or order moved, and the test file is not edited.

## Orphan sweep (step 3)

For every `def` in the lib files Tasks 1–6 touched (`git diff --name-only 1029809b -- lib`), I ran `git grep -nw <name> -- lib html`.
- **Zero callers:** only `do_GET`/`do_POST`/`log_message`, which are `BaseHTTPRequestHandler` callbacks. `startCarsCharging`/`withdrawStartCharging` showed zero only because my filter dropped their dict-literal uses in `controlPass`.
- **Readers lost with the point aggregates, all deleted:**
  - `VehicleEndpoint.isCharging`, `currentAmps` and `provider`. The only readers of `provider` were tests, which now use `_candidates()` through a test helper.
  - `Gen2TWC.currentAmps`.
  - `Gen3TWC.isCharging`.
- **Kept:**
  - `Gen3TWC.currentAmps`, which `_plugEdges` reads.
  - `Gen2TWC.isCharging`, which the serial loop writes, `HTTPControl` reads and `num_cars_charging_now` sums.
  - The class-level `TWCMaster.settings` (F21).

## Files changed

- **lib:**
  - `EVSEController/{EVSEController,Gen2TWCs,VehicleEndpoints,__init__}.py` (deleted), `EVSEController/Gen3TWCs.py`;
  - `EVSEInstance/{EVSEInstance,ChargingPoint,Gen2TWC,Gen3TWC,VehicleEndpoint}.py`, `EVSEInstance/__init__.py` (deleted);
  - `TWCMaster.py`, `TWCSlave.py`;
  - the comment sweep in `TWCManager.py`, `Policy/Policy.py`, `Control/HTTPControl.py`, `Vehicle/{TeslaAPI,TeslaBLE,TeslaTokenSlot,HomeAssistant}.py`, `Vehicle/Providers/{Capability,Gen2TWCProvider,Order,Provider,TeslaAPIProviders,TeslaBLEProvider,WallConnectorVins}.py` and `Vehicle/Reconcile/{Belief,Desired,Reconciler,Rules,Run,Targets}.py`.
- **tests:** `test_no_legacy_command_paths.py`, `test_control_tick.py`, `test_charging_points.py`, `test_distributor_loop.py`, `test_vehicle_endpoint.py`, `test_gen2_idle_minimum.py`, `test_provider_registration.py`, `test_telemetry_registry.py`, `test_teslaapi_readonly_gate.py`.
- **Outside the repo, in the sdd directory:** `pr-notes.md`, `live-check.sh` and this report.

## Lib delta

Counts are by `scratchpad/t6/count.py`: comment lines are `#`-only lines plus docstring lines.

| | total | code | comment | blank |
|---|---|---|---|---|
| origin/main | 23,180 | 16,293 | 3,925 | 2,962 |
| 1029809b (Phase 4 BASE) | 27,425 | 19,504 | 4,682 | 3,239 |
| dc2609f5 (Task 6 BASE) | 27,026 | 19,339 | 4,482 | 3,205 |
| 6dd84437 collapse | 26,504 | 19,158 | 4,267 | 3,079 |
| 159070c0 settings | 26,462 | 19,113 | 4,268 | 3,081 |
| 02bfb49d sweep | **26,450** | 19,114 | 4,256 | 3,080 |

- **Task 6:** −576 against the expected ≈ −315 (range −260..−370), split as code −225, comment −226, blank −125. It is larger than planned because the whole ABC files went, along with the package inits, the orphans, the four-copy settings defaults and the Gen2TWC `currentVIN` shim.
- **Phase 4:** 27,425 → 26,450 = **−975**, against a projection of ≈ −810. That is below 27,425.
- **Step 5 commands:**
  - `git diff --shortstat 1029809b -- lib`: 37 files, +841 −1822.
  - The awk check prints `added 841 removed 1822` and exits 0.
  - `git diff --shortstat origin/main -- lib`: 64 files, +9056 −5718.
  - `git diff --shortstat dc2609f5 -- lib`: 33 files, +295 −871.
- **Per task, actual (expected):** T1 −48 (−50), T2 +39 (+22), T3 −33 (−58), T4 −293 (−320), T4b +2 (none planned), T5 −66 (−88), T6 −576 (−315).

## Test map (every deleted or rewritten test)

| Test | Mapping |
|---|---|
| `test_charging_points::test_grouping_is_by_vehicle_key…` | PLUMBING-ONLY. It asserted `pts[0].isLocal and pts[0].currentVIN == VIN`, two aggregates that are deleted and have no lib reader. It now asserts `localEndpoints == [twc]`. `vehicleKey == VIN` still pins the canonical key. |
| `test_charging_points::test_point_limits_and_occupancy` → `test_point_limits` | DELETED SURFACE (F22). The point-level `occupied` aggregate had no lib reader and is gone. Min/max/read-only are still asserted. Endpoint `occupied` stays pinned by `test_vehicle_endpoint::test_state_from_registry_values_without_reads`, `test_gen3twc_provider` and the blind-rule tests. |
| `test_charging_points.distributor()` helper | PLUMBING-ONLY. Budgets come from `_budgets()`, so the master gets `wiringMaxAmpsAllTWCs: 400`, which leaves the feed as the binding limit as the mocked 100,000 W did. `getModuleByName → None`. The `controllers` parameter was unused and is dropped. |
| `test_charging_points.real()` | PLUMBING-ONLY. The `VehicleEndpoints` registration is gone, because the master lists cars itself. |
| `test_charging_points.endpoint()` and `test_twc_point_sets_the_twc_target_and_never_the_endpoint` | PLUMBING-ONLY. Without the cache, the helper spies on `VehicleEndpoint.setTargetPower` for the VIN (monkeypatch) instead of wrapping one cached instance. Same assertion. |
| `test_charging_points::test_mode_2_named_twc…` | PLUMBING-ONLY. `vehicleEndpoints(m)[0]` and the `provider()` test helper replace the controller and the deleted `.provider`. |
| `test_charging_points::test_gen2_at_00_…_as_before_task_10` | Renamed (`…_is_two_points`) to drop the task reference. Body unchanged. |
| `test_distributor_loop._master` | PLUMBING-ONLY. Same change as `distributor()`. The unused `slaveTWCRoundRobin` setup is gone. |
| `test_vehicle_endpoint` (11 tests) | PLUMBING-ONLY. `VehicleEndpoints(m).allEVSEs` → `vehicleEndpoints(m)`, `VehicleEndpoints(m)._blindTWCs()` → `_blindTWCs(m)`, `.provider` → `provider(e)`. Two names are cleaned (`test_controller_…` → `test_…`). |
| `test_vehicle_endpoint::test_controller_lists_…` (`allEVSEs[0] is allEVSEs[0]`) | DELETED ASSERTION. It pinned the cache, which the brief removes. |
| `test_vehicle_endpoint::test_a_cached_endpoint_is_dropped_once_hidden` → `test_a_hidden_car_is_listed_again_once_visible` | REWRITTEN. The cache assertions (`_cache == {}`, `again is not first`) are gone. The behaviour stays pinned: listed, hidden by a drawing unnamed TWC, then listed again. |
| `test_vehicle_endpoint::test_state_from_registry_values_without_reads` (`not e.isCharging`) | DELETED ASSERTION. `VehicleEndpoint.isCharging` was an orphan and is deleted. |
| `test_gen2_idle_minimum.real()` | PLUMBING-ONLY. The registration and import are gone. |
| `test_provider_registration` (2 tests) | PLUMBING-ONLY. "Both controllers registered" → `getModulesByType("EVSEController") == []`, plus `vehicleEndpoints(m) == []` where it checked the empty listing. |
| `test_telemetry_registry::test_sleeping_car_on_healthy_feed…` | PLUMBING-ONLY: the import path. |
| `test_control_tick::test_a_gen2_install_with_no_slave_linked…` | PLUMBING-ONLY. `vehicleEndpoints(m) == []`. |
| `test_control_tick::test_the_serial_loop_no_longer_distributes…` | DELETED ASSERTION. `"VehicleEndpoints" not in src` referred to a class that no longer exists. `test_no_retired_allocator_names_remain` covers it. |
| `test_control_tick::test_no_gate_acts_before_the_first_offer` | REWRITTEN (Addition 4). See Guards. |
| `test_teslaapi_readonly_gate` (`.provider == "OwnerAPI"`) | PLUMBING-ONLY: `_candidates()[0].name`. |

No test was deleted outright.

## PR notes

`.superpowers/sdd/2026-10-17-vehicle-model-phase4-control-tick/pr-notes.md` covers:
- "Not ported into the rearchitecture": (a), (c) and (f);
- the behaviour changes (b), (d), (e), (g) and (h), with the vehicle-only RS-485 note and the BLE/HA-only car waiting for presence;
- #690 closed;
- the RS-485 outbox;
- the first token refresh at +300 s;
- rate before start;
- the size table and the per-task ledger.

The brief says "in the ledger", but `progress.md` is the controller's, so the notes are a separate file for the controller to link.

## Live check

`.superpowers/sdd/2026-10-17-vehicle-model-phase4-control-tick/live-check.sh` (syntax-checked, not run).
- `scp` uses a home-relative path, because SFTP-mode scp may not expand `~`.
- The start stamp is `%Y-%m-%d %H:%M:%S`, which any `journalctl --since` accepts.
- The header notes that `rollback` restores the settings backup, which discards kWh and held-limit changes made during the window. Subcommands: `prepare`, `deploy`, `boot`, `watch`, `tokens`, `paid`, `rollback`. State is kept on the box in `~/phase4-live/`.

## Self-review

- **Brief items:**
  - Steps 1–6 and 8 are done. Step 7's commit message is used for commit 1.
  - Additions 1–5 are done: the sweep, the guard, `chargeGate(now, key)`, the vacuous assertion and the PR-note items.
- **YAGNI:** nothing new beyond `_budgets`, `vehicleEndpoints` and the guards.
- No Python 3.9+ syntax in new code. The guard uses `ast.get_docstring`, not `ast.unparse`.
- Parity is identical. The suite is green at every commit. No background processes are left, and the temporary worktree was removed.

## Concerns

1. **`chargingPoints()` is kept, not inlined into `distributeEVSEPower`.** It has two lib callers now: `controlPass(distribute=False)`, the offers-only beat added after the brief was written, and `distributeEVSEPower`. Three test modules also use it as their seam. `getAllEVSEs` is inlined into it, as the brief asks. `test_one_distributor_entry` is unaffected.
2. **The `Gen2TWC.isCharging` bool property is kept.** Removing it would change `/api/getSlaveTWCs` `carsCharging` from `true`/`false` to `1`/`0` (`HTTPControl.py:528`), and main publishes the bool. Only the `currentVIN` shim went.
3. **The live-check strings in the brief don't all exist.**
   - No "ControlTick started" line: the tick logs only `Control tick: <step> raised …` on failure, so the script checks that this line is absent.
   - No "Attempting token refresh" line, and the log format has no thread name, so "`BackgroundTask` in the log context" is not observable. The script checks the refresh lines (`Car API request` at INFO2, `Car API auth response received` at INFO4) against `Main loop stalled`.
4. **The box's commandPolicy.** Memory says the box was set back to `prefer_ble` (2026-10-17 16:12). The brief assumes `ble_only` for step 4's "zero Car API command lines". The script prints the policy at `prepare` and does not change it. The user should decide whether to set `ble_only` for the window.
5. **The comment sweep's honest yield is small** (−11 lines in its own commit). Most stack comments are why-comments. The comment drop that does show (−226 for Task 6) came mostly with the deleted ABCs.
6. **`159070c0` (settings-defaults dedupe) is outside the brief's list.** It is behaviour-neutral duplication removal in a touched file, so it is easy to drop if unwanted.
