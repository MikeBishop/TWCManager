### Task 11: Held limits natively; charge-limit decision-makers write desired state; wire the reconciler; the legacy limit path goes (expected lib Δ ≈ −450)

User decision 3: migrate once at load, keep the `heldLimits` key, and write `Rules` natively on `HeldLimit`.

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/Targets.py`.
- Modify: `Reconcile/HeldLimits.py`, which migrates once at `load()`:
  - VIN keys from `chargeLimits` move to `heldLimits` at once.
  - Numeric-ID entries, and any `id:*` keys already in `heldLimits` from development builds of this branch (pre-flight M9), wait in memory. They resolve the first time `loadVehicleList` succeeds with at least one vehicle. That call is `heldLimits.resolveLegacyIds({id: vin})`, over the union of the lists from every usable token slot in that cycle (Owner and Fleet may be different accounts).
  - Matched entries move under the VIN. **Unmatched entries are dropped** (user decision; pre-flight I9): one WARNING per dropped entry names the numeric ID and its outside limit (no tokens), so the user can restore it by hand. Then `chargeLimits` and the `id:*` keys are deleted and the settings saved.
  - An empty list never triggers the drop.
  - Delete `storeKey`'s `id:` handling, `LEGACY_PREFIX`, `adoptLegacyId` and the `CarApiVehicle._bind` call to it.
- Modify: `Vehicle/TeslaAPI.py` (pre-flight C1). `updateChargeAtHome()`, run by the existing `checkCharge` task, first calls `loadVehicleList()` (a free `GET /vehicles`) when `getVehicleCount() < 1`, `slotFor("read")` is usable and `getCarApiRetryRemaining()` is 0. It refreshes the token the same way `car_api_available` did.
  - Without this, nothing loads the list once `applyChargeLimit` (here) and `car_api_available` (12a) are gone, and Fleet and Owner never become ready.
  - `atHome` is refreshed only by the reads that already run: `update_vehicle_data` during read-before-write, and `updateChargeAtHome`. That is the accepted interim until Phase 5; no new paid `update_location` is added.
- Modify: `Reconcile/Rules.py`. `decideChargeLimit(desired: int, restore: bool, current: Optional[int], held: Optional[HeldLimit], sendWhenUnknown: bool)` is written natively: `held.held is None` means we hold none, and a restore puts `held.outside` back. There is no `-1`, no `lastApplied` and no `limit = -1` translation. The ported test table stays the oracle, unchanged in meaning.
- Delete (the new path replaces them in this task):
  - `TeslaAPI.applyChargeLimit` and `CarApiVehicle.apply_charge_limit`, plus `.lastLimitAttemptTime`;
  - `TeslaBLE.applyChargeLimit`, `HomeAssistant.applyChargeLimit`;
  - the VCQ `applyChargeLimit` dispatch entry and `_applyChargeLimitKwargs`;
  - `VehiclePriority.applyChargeLimit`;
  - `TWCMaster.getNormalChargeLimit/saveNormalChargeLimit/removeNormalChargeLimit`, `_heldLimitKey` and `_adoptListedHeldLimits` (and its `loadSettings` call);
  - the `applyChargeLimit` route in `queue_background_task`/`VEHICLE_COMMANDS`;
- Behaviour (ledger c6 carry): a satisfied restore removes the held record.
- Modify: `TWCMaster.py` (`desired`, `reconciler`, `policyLimit`, `setPolicyLimit`; `lastChargeLimitApplied` deleted), `Policy/Policy.py` (`enforcePolicy`), `TWCManager.py` (the `checkArrival`/`checkDeparture` tasks; start and shutdown), `Vehicle/TeslaAPI.py`, `HomeAssistant.py`, `TeslaBLE.py` (the limit copies and dedupe flags with their uses).
- Test: `tests/unit/test_limit_wiring.py`; `test_policy.py`, `test_sigterm_shutdown.py`.

**Interfaces:**
- Produces (`Targets.py`): `presentVehicles(master, capability)`, `targetsFor(master, vin, capability=STOP_CHARGING)`, `applyPolicyLimit(master, limit, decision) -> int`, `onArrival(master)` and `onDeparture(master)`, as the original plan's Task 7.
- Produces (`TWCMaster.__init__`, after `providerOrder`):
  - `self.desired = DesiredStore()` and `self.vehicleRegistry.removed = self.desired.forget` (ledger L19; Task 10 made it one assignment).
  - `self.reconciler = VehicleReconciler(self)` (it owns its two queues; Task 10).
  - `policyLimit: Optional[int] = None`; `setPolicyLimit(self, limit, transition)`.
- Produces (`TWCManager.py`):
  - `master.reconciler.start()`. The legacy `vehicleCommandQueue.start()` stays: start, stop and rate commands keep flowing on it until Tasks 12a–12b rewire them. The original plan's "silent queue between Tasks 7 and 9" no longer arises.
  - Shutdown: `master.reconciler.stop()`, then both vehicle drains share `vehicleDeadline = min(shutdownDeadline - 20, now + 60)`: `master.reconciler.drain(...)` then the legacy `drain_high_priority(...)`, each given `max(0, vehicleDeadline - now)`. At least 20 s stays for `saveSettings` (which persists `heldLimits`). A small helper `shutdownTimeouts(now, shutdownDeadline) -> float` in `TWCManager.py`'s importable code computes it and gets a unit test, `test_vehicle_drains_leave_twenty_seconds_for_settings`; `test_sigterm_shutdown.py` cannot observe it (pre-flight M9).
- Delete `master.lastChargeLimitApplied`, `TeslaAPI.lastChargeLimitApplied`, `HomeAssistant.lastChargeLimitApplied`, `CarApiVehicle.stopTryingToApplyLimit` and TeslaBLE's `_stopTryingToApplyLimit`/`_lastAppliedChargeLimit`. Also delete the `applyChargeLimit(self.lastChargeLimitApplied, checkArrival=True)` call before every Fleet start in `TeslaAPI.car_api_charge` (TeslaAPI.py:926–927; the reconciler owns the limit, and `LIMIT_THEN_START_GAP` replaces limit-before-start from Task 11) and the `applyLimit and stopTryingToApplyLimit` skip in `car_api_available` (TeslaAPI.py:517), so the interim start path neither raises nor sends an undeduped paid limit (pre-flight M10). Test: `test_legacy_fleet_start_sends_no_limit_first` (paid counted: one `charge_start`, no `set_charge_limit`).

- [ ] **Step 1: Write the failing tests.** Carry over from the original Task 7 unchanged: `test_present_rule_until_phase_5`, `test_policy_limit_sets_desired_for_present_cars_and_none_restores`, `test_periodic_reenforce_does_not_undo_an_adopted_limit`, `test_departure_restores_a_held_limit_for_an_absent_car_once`, `test_policy_thread_calls_set_policy_limit`, `test_no_module_holds_a_copy_of_the_policy_limit`. Add:

```python
def test_master_wires_store_and_reconciler_on_one_clock():
    m, s = make(); assert m.reconciler.master is m and m.desired._clock is time.time and m.desired.changed == m.reconciler.wake
    m.vehicleRegistry.getOrCreate(VIN, "t"); m.desired.set(VIN, CHARGE_LIMIT, 50, "policy"); m.vehicleRegistry.forget(VIN)
    assert m.desired.peek(VIN) is None                                     # registry.removed wired

def test_debug_route_submits_through_the_master_reconciler(): ...           # ledger L35: /api/sendTeslaAPICommand returns 200

def test_legacy_ids_resolve_once_from_the_first_vehicle_list(): ...         # VIN keys at load; ID and id:* keys on the first non-empty list (all slots); unmatched dropped, one WARNING each naming ID and limit; chargeLimits gone
def test_an_empty_vehicle_list_drops_nothing(): ...                          # I9
def test_vehicle_list_loads_without_any_legacy_command(requests_mock): ...  # C1: checkCharge -> one GET /vehicles, no vehicle_data, no wake_up; FleetAPIProvider.ready(v, STOP_CHARGING) becomes True
def test_rules_need_no_sentinel(): ...                                       # grep Rules.py for "-1"/"lastApplied" == []; the ported table passes
def test_a_satisfied_restore_removes_the_held_record(): ...                  # ledger c6
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: Targets`).
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run the full suite** → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Held limits migrate once and the rules work on HeldLimit; policy, arrival and departure set desired limits; the legacy limit path goes"`

