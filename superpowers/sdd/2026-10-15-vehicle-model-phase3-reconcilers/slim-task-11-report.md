# Slim Task 11 report: held limits natively, decision-makers write desired state, reconciler wired, legacy limit path deleted

**Status:** DONE_WITH_CONCERNS
**Branch:** `vehicle-model/phase3` (worktree `scratchpad/wt-vm3`), BASE bba7c4f
**Commits:**
- c4d9037: Rules.py is native on HeldLimit (its own commit; the ported table passes unchanged).
- 23cb7e8: everything else, under the brief's Step 5 message plus a body.
- 2ecf54f: in self-review, `load()` no longer warns "Kept the normal limit…" for a car whose entry the store already holds (nothing was migrated). The test is `test_both_keys_present_the_store_wins`, which now uses `[95, 101]`.

## Lib delta

Expected about −450.

`git diff --numstat bba7c4f -- lib` (Targets.py included): 331 insertions, 771 deletions, **net −440**.

| File | + | − |
|---|---|---|
| Vehicle/TeslaAPI.py | 70 | 333 |
| Vehicle/TeslaBLE.py | 0 | 149 |
| Vehicle/HomeAssistant.py | 0 | 67 |
| TWCMaster.py | 18 | 54 |
| Reconcile/HeldLimits.py | 97 | 83 |
| Reconcile/Rules.py | 26 | 36 |
| TWCManager.py | 22 | 18 |
| VehicleCommandQueue.py | 0 | 14 |
| VehiclePriority.py | 1 | 6 |
| Policy/Policy.py | 6 | 5 |
| Vehicle/Telemetry.py (comment) | 3 | 4 |
| Reconcile/Reconciler.py | 2 | 2 |
| Reconcile/Targets.py (new) | 86 | 0 |

HeldLimits grows a little. `storeKey`, `adoptLegacyId` and the separate `_get`/`_set`/`_remove` key layer are gone. In their place are the waiting-ID logic (`load` now handles the stored `id:` keys and an existing store, `waiting`, `resolveLegacyIds`). Nothing is duplicated: the old `id:` plumbing is fully gone.

## What changed

**HeldLimits migration (user decision 3, U1, I9, M9).**
- `load()`:
  - VIN keys in `chargeLimits` move into `heldLimits` at once. A VIN the store already has keeps the store's entry. The old "existing store wins, chargeLimits left alone" rule and its "older release" warning are gone.
  - Numeric IDs, and development builds' `id:*` keys, wait in `self._waiting`. They also stay on disk where they were: `chargeLimits` is rewritten to just the valid numeric entries, and the `id:*` keys stay in the store. So a restart before resolution loses nothing (`test_an_unresolved_id_survives_a_restart`).
  - The malformed, out-of-range and case-collision warnings are unchanged.
- `waiting() -> bool`.
- `resolveLegacyIds({id: vin})`:
  - Does nothing on an empty mapping.
  - Under `settingsLock`, it swaps `_waiting` out, so a concurrent second caller finds nothing to do. Each matched ID moves under its VIN unless the VIN already has an entry. It deletes `chargeLimits` and every `id:*` key.
  - Outside the lock, it logs one WARNING per unmatched ID ("Dropped the saved charge limit of Tesla vehicle ID %s, which no Tesla account lists: its normal limit was %s%%"; no token), then saves.
- `get`/`set`/`remove` take a VIN directly. `storeKey`, `LEGACY_PREFIX`, `adoptLegacyId` and the `CarApiVehicle._bind` call are deleted.

**TeslaAPI (C1, I9, M6, M10).**
- `loadVehicleList` now uses a `_vehicleList(slot)` helper: one free GET that returns the cars, None when the slot refused, or False on any other failure. Error handling is as before. On success it calls `resolveHeldLimits(slot, listed)` (M6: 13c must keep this call).
- `resolveHeldLimits(listedSlot=None, listed=None)` does nothing unless the master's `HeldLimits` has waiting IDs. Otherwise it collects the list from every usable read slot, reusing the one just fetched, and resolves only when every list came back. `resolveLegacyIds` then ignores an empty union.
  - Owner and Fleet as different accounts are covered. A failed second list defers the drop to the next `checkCharge`.
- `updateChargeAtHome()`:
  - With cars listed, it calls `resolveHeldLimits()` (a no-op once nothing waits).
  - Otherwise, when `getCarApiRetryRemaining()` is 0, it calls `refreshTokenIfNeeded()`. If `slotFor("read")` is then usable, it calls `loadVehicleList()`.
  - Newly listed cars have `atHome=False`, so no `update_charge` follows. That means no `vehicle_data`.
- Deleted:
  - `applyChargeLimit`, `CarApiVehicle.apply_charge_limit`, `lastLimitAttemptTime`, `stopTryingToApplyLimit`, `lastChargeLimitApplied` and `carApiLastChargeLimitApplyTime`;
  - `car_api_available`'s `applyLimit` parameter and its skip;
  - the `applyChargeLimit(self.lastChargeLimitApplied, checkArrival=True)` call before every legacy Fleet start.

**Rules.py.** `decideChargeLimit` works on `held`/`held.held`/`restore`, with `target = None if restore`. There is no `-1`, no `lastApplied` and no `_held`. The header comment is rewritten as well.

**Targets.py (new).**
- `presentVehicles(master, capability)`, the Phase 5 stand-in. A car counts as present when it is:
  - anonymous (only for start or stop);
  - on a point (`twcVin`);
  - TeslaAPI `atHome`;
  - HA `at_home`;
  - known only to BLE and holding a TeslaBLE claim.

  It is then filtered to cars with a candidate for the capability.
- `targetsFor`.
- `applyPolicyLimit(master, limit, decision) -> int`. A limit sets a `"policy"` desire. None restores `held.outside` while we hold a limit; otherwise it clears the desire.
- `onArrival` applies `master.policyLimit` with `decision=True`.
- `onDeparture`: for each VIN in `holding()` whose registry vehicle is not present, it sets a restore desire (`decision=True`). A VIN with no registry vehicle is skipped, because `pass_()` would never plan it.

**TWCMaster.**
- `self.desired = DesiredStore()`, `self.vehicleRegistry.removed = self.desired.forget`, `self.reconciler = VehicleReconciler(self)`, `self.policyLimit = None`, and `setPolicyLimit(limit, transition)`.
- `VEHICLE_COMMANDS = frozenset(["charge"])`. The lock-order comment is updated.
- Deleted: `lastChargeLimitApplied`, `getNormalChargeLimit`, `saveNormalChargeLimit`, `removeNormalChargeLimit`, `_heldLimitKey`, `_adoptListedHeldLimits` and its `loadSettings` call.

**Policy.enforcePolicy.** `transition = self.active_policy != name`, and it calls `self.master.setPolicyLimit(limit if 50 <= limit <= 100 else None, transition=transition)`. The `limitOverride` arithmetic is unchanged.

**TWCManager.py.**
- `checkArrival` runs `onArrival(master)` and then `vehicleModule.updateChargeAtHome()`. `checkDeparture` runs `onDeparture(master)`.
- `master.reconciler.start()` runs right after `vehicleCommandQueue.start()`, and `checkCharge` is queued once at startup (see Concern 1).
- Shutdown: `reconciler.stop()`, then `vehicleDeadline = shutdownTimeouts(now, shutdownDeadline)`, which is `min(shutdownDeadline - 20, now + 60)`. Then `reconciler.drain(max(0, vehicleDeadline - time.time()))` and the legacy `drain_high_priority(timeout=max(0, vehicleDeadline - time.time()))`.

**Reconciler (c6).** A restore that is already satisfied, while we hold a limit, calls `heldLimits.remove(vin)` (it used to save `(current, None)`) and clears the desire.

**Other deletions.**
- TeslaBLE `applyChargeLimit`, `_stopTryingToApplyLimit` and `_lastAppliedChargeLimit`.
- HA `applyChargeLimit` and `lastChargeLimitApplied`.
- The VCQ `applyChargeLimit` dispatch entry and `_applyChargeLimitKwargs`.
- VehiclePriority's `applyChargeLimit` entries and the now-unused `SET_CHARGE_LIMIT` import.

## Tests

The new file is `tests/unit/test_limit_wiring.py` (16 tests). All were confirmed red at bba7c4f in a throwaway worktree, with the Targets import made lazy so the module collects.

| Test | What it pins |
|---|---|
| test_present_rule_until_phase_5, test_policy_limit_sets_desired_for_present_cars_and_none_restores, test_periodic_reenforce_does_not_undo_an_adopted_limit, test_departure_restores_a_held_limit_for_an_absent_car_once, test_policy_thread_calls_set_policy_limit, test_no_module_holds_a_copy_of_the_policy_limit | Carried from original Task 7. The departure test also checks that a second `onDeparture` makes no new desire. The grep also covers `applyChargeLimit`, `NormalChargeLimit` and `adoptLegacyId`. |
| test_master_wires_store_and_reconciler_on_one_clock | Production clocks; `registry.removed` forgets desired state. |
| test_debug_route_submits_through_the_master_reconciler | L35: a real `TWCMaster` and its own reconciler (inlined). The route returns 200 and the wake reaches BLE. |
| **test_legacy_ids_resolve_once_from_the_first_vehicle_list** | Migration, I9 and M9. Owner `/products` lists IDs 11 and 33; Fleet lists 22 (different accounts). Stored `id:44` is unmatched. `chargeLimits` VIN keys migrate at load. After the list: 11 → VIN2, 22 → VIN3, 33 → VIN4 is not overwritten (the store's entry wins), and 44 is dropped with exactly one WARNING naming "44" and "75%". `chargeLimits` and `id:*` are gone, one save is queued, and no token appears in the log. A second load does not refetch the Fleet list. |
| **test_an_empty_vehicle_list_drops_nothing** | I9 |
| **test_a_failed_second_list_defers_the_drop** | A Fleet 500 defers the drop; the next `updateChargeAtHome` resolves it. Only GETs are made (4). |
| test_an_unresolved_id_survives_a_restart | Settings round-trip keeps a waiting ID. |
| **test_vehicle_list_loads_without_any_legacy_command** | C1, paid counted. Two `updateChargeAtHome()` calls make exactly one `GET /vehicles`, with no `vehicle_data` and no `wake_up`. `FleetAPIProvider.ready(v, STOP_CHARGING)` becomes True. |
| **test_legacy_fleet_start_sends_no_limit_first** | M10, paid counted: the requests are exactly `[charge_start]`. At BASE it failed inside `applyChargeLimit`. |
| test_rules_need_no_sentinel | Regex `-1(?!\d)\|lastApplied` on Rules.py returns nothing (a plain `-1` search would match "50-100"). Every case in the ported table passes. |
| test_a_satisfied_restore_removes_the_held_record | c6 |

Also:
- `test_sigterm_shutdown.py::test_vehicle_drains_leave_twenty_seconds_for_settings`. It compiles `shutdownTimeouts` from the TWCManager.py source with `ast`, because the module runs at import. It checks the 60 s cap and the 20 s floor, that stop comes before both drains, and that the reconciler starts after the legacy queue.
- `test_policy.py::test_enforce_sets_the_policy_limit_on_the_master`: a transition, the override (battery 70 → 69, no transition) and an out-of-range limit → None.
- `test_held_limits.py::test_listing_before_load_is_resolved_on_the_next_check`: a list loaded before `loadSettings` is resolved by the next `checkCharge`, with only GETs.

**Rewritten or deleted with the removed features:**
- test_held_limits: the wrapper, adopt and bind tests are deleted; the migration tests are rewritten for waiting IDs and the existing-store merge.
- test_targeted_charge_limit.py is deleted.
- test_own_write_stamps: the 7 apply-limit tests are deleted.
- test_vehicle_command_queue: the generic command becomes `setAmps`; the 3 limit-only keying tests are deleted.
- test_vehicle_priority and test_vehicle_priority_returns: the walk tests now use `car_api_charge` and `wakeVehicle`; the 3 TeslaAPI apply-limit tests are deleted.
- Edited for the removed calls: test_teslaapi_readonly_gate, test_teslaapi_token_slots, test_teslable_pairing_status, test_twcmaster, test_settings_lock and test_vehicles_page.
- test_limit_reconciler: `setup()` wires `registry.removed`. Its M1 satisfied-restore test is replaced by the c6 test.

## Suite

`tests --ignore=tests/API --ignore=tests/integration`: **1661 passed, 1 xfailed** at 2ecf54f (BASE: 1671 passed, 1 xfailed). The count drops because of the legacy tests deleted with their features. One pytest warning is reported, as at BASE.

`test_sigterm_shutdown.py::test_sigterm_exits_promptly_despite_non_daemon_thread` ran (no skips). It boots the real `TWCManager.py` through `reconciler.start()`, the startup `checkCharge`, `reconciler.stop()`/`drain()` and the legacy drain, then SIGTERMs it. That is end-to-end evidence that the start and shutdown wiring works.

`tests/integration` and `tests/API` have no references to the deleted names; their only hits were the unchanged `/api/checkArrival` and `/api/checkDeparture` routes.

## Concerns

1. **C1's trigger is not periodic on a default install.**
   - `checkCharge` was queued only by `TeslaAPI.minBatteryLevelAtHome`, which reads it only under `limitOverride` or a policy condition that names it.
   - So I queue `checkCharge` once at startup and run `updateChargeAtHome()` after `onArrival` in `checkArrival`. BASE already did this, at the end of `applyChargeLimit(checkArrival=True)`.
   - Both are free list loads. For cars already `atHome`, `update_charge` may read `vehicle_data` (paid) on arrival, as BASE did.
   - If the startup load fails (network down), the next load comes only on the next arrival, or from `car_api_charge` until 12a. **12a should decide** whether a periodic `checkCharge` is needed once `car_api_charge` goes.
   - The `checkCharge` handler calls the VehiclePriority facade. VehiclePriority is in `modules_available` and is the background thread's first choice, so the startup task always has a module, as the existing `checkCharge` already assumed.
2. **The I9 drop is stricter than the ruling.** Resolution happens only when *every* usable read slot's list came back, with a non-empty union. If one slot fails, everything is deferred to the next `checkCharge` instead of being dropped on the other slot's list. The resolution also refetches the other slot's list, a free GET, only while IDs wait.
3. **The existing-store case changed.**
   - When `heldLimits` and `chargeLimits` both exist, `chargeLimits` VIN keys the store lacks are now merged in. Before, `chargeLimits` was left alone with an "older release" warning.
   - That warning is gone: a numeric-only `chargeLimits` next to `heldLimits` is now the normal waiting state.
4. **c6 asymmetry.** A satisfied restore found at plan time removes the record. A restore that needed a send still saves `(outside, None)` on success (`saveOnSuccess`), and a restore settled in `beforeWrite` (hand-set) saves `(current, None)`. The two forms are equivalent to the rules (no record is the same as held None), so I left the Rules table untouched.
5. **The reconciler is live from this task.**
   - Policy, arrival and departure limits now go only through it: legacy `applyChargeLimit` is gone on every module.
   - Start, stop and rate still use the legacy queue until 12a and 12b.
   - The policy thread calls `setPolicyLimit` every pass. Unchanged desires are no-ops, and `None` clears desires on present cars that hold nothing.
6. **`atHome`** is refreshed only by the existing reads (read-before-write `update_vehicle_data`, and `updateChargeAtHome` for cars already at home), as the brief accepts until Phase 5. A Fleet-only car is therefore present for the policy limit only once something has marked it `atHome` or it is on a point.
7. `test_legacy_fleet_start_sends_no_limit_first` counts cleanly at HEAD: the requests are exactly `["charge_start"]`. Only the red-at-BASE evidence is indirect. At BASE the test failed inside the deleted `applyChargeLimit` (the FakeMaster has no `getNormalChargeLimit`), which shows that BASE entered the limit path before the start.

## Fix round 1 (d35a95c)

These fixes answer slim-task-11-review.md under the coordinator's rulings. Every new test was confirmed red at 2ecf54f, in a throwaway worktree with only the new test file copied in.

- **C1 (paid option, as ruled).** `Targets.onDeparture` now runs on the background `checkDeparture` task. For each car in `heldLimits.holding()` that has a TeslaAPI attachment and no `twcVin`, it first calls `update_location(0)`: one `vehicle_data` through the read cascade, which never wakes. The departure restore then uses the fresh `atHome`. Once the limit is restored, `holding()` drops the car, so the 20 and 45 min re-checks read nothing.
  - `test_a_fleet_car_that_unplugs_and_leaves_gets_its_normal_limit_back` (paid counted). The Fleet calls are exactly `vehicle_data` then `set_charge_limit {"percent": 90}`, with no `wake_up`.
  - `test_an_unplug_at_home_is_not_a_departure`: one `vehicle_data`, no desire.
  - `test_a_policy_change_while_the_car_is_away_sends_nothing`: after the departure, `setPolicyLimit(60, transition=True)` changes no desire and sends no request.
- **I1.** `HeldLimits.load()` records `_loadedVins`. In `resolveLegacyIds`:
  - A matched VIN that was stored at load keeps its entry.
  - A VIN stored since then becomes `HeldLimit(legacy.outside, store.held)`.
  - Both cases log one INFO line naming the ID and VIN, with the normal limit kept and the one discarded. This also covers M5.
  - `test_a_limit_recorded_while_an_id_waits_keeps_the_legacy_normal` is the probe: it ends at `(90, 60)` and the log names 50% and 90%.
  - M5 is asserted in the two-account test: ID 33's discarded 70% is logged with VIN4.
- **I2.**
  - `TeslaAPI.listPending()` is True while the list is empty or IDs wait. `TeslaAPI.loadList()` holds the free load-or-resolve step that `updateChargeAtHome` now calls first.
  - The main loop's existing 5-minute Tesla token tick queues a `loadVehicleList` background task while `listPending()`. The task runs `carapi.loadList()`, which costs only free GETs: no `update_charge`, no `vehicle_data`. The existing API error backoff still applies.
  - `test_a_failed_boot_list_load_recovers_without_an_arrival`: a GET that fails at boot is recovered by `loadList()` with exactly 2 GETs. A source check pins the tick and the handler.
- **M1.** `loadVehicleList` releases `vehicleListLock` before `resolveHeldLimits`, so the other slot's GET never holds it.
- **M3.** The `applyChargeLimit` mock is gone from test_teslaapi_charge_vin.py, and docs/modules/Vehicle_HomeAssistant.md is reworded.
- **M4.** The token-leak test captures at level 1 on the root and TeslaAPI loggers. It also asserts that the INFO8 and DEBUG list lines were captured.
- **M2** is by design (limit-before-start until 12a), per the ruling. No change.

**Lib delta after fix round 1:** `git diff --numstat bba7c4f -- lib` gives +384/−771, **net −387** (Task 11 total). The fix round alone is +68/−15, net +53: HeldLimits +26 (merge and logging), TeslaAPI +11 (`listPending`/`loadList` and the moved resolve), TWCManager +8 (tick and handler), Targets +8 (departure read).

**Suite:** 1666 passed, 1 xfailed.

**Concerns:**
- **The departure read can cost three `vehicle_data` calls.** A car we hold a limit on that stays unplugged at home is read at each of the 5, 20 and 45 min checks, the same as before this task. A car that was restored is read once.
- **The `loadVehicleList` tick also runs on installs whose TeslaAPI holds no token.** There it makes no HTTP call: `slotFor("read")` is None.
- **A legacy ID that never appears in any list keeps getting refetched.** While all lists come back empty (count 0), the waiting IDs are refetched every 5 minutes. These are free GETs, and the fetching ends after the first non-empty list.
