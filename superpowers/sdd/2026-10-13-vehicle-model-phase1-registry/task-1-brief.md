### Task 1: Cherry-pick the per-VIN command queue (`presence/1-command-queue`)

**Files:**
- Modify (by cherry-pick): `lib/TWCManager/VehicleCommandQueue.py`, `lib/TWCManager/TWCMaster.py:166-168` (`cancelStopCarsCharging`), `:1889-1925` (`startCarsCharging`/`stopCarsCharging`), `tests/unit/test_vehicle_command_queue.py`, `tests/unit/test_twcmaster.py`.
- Modify: `CHANGELOG.md` (v1.4.0 Bugfixes).

**Interfaces:**
- Produces: `VehicleCommandQueue.cancel(cmd: str, match: Callable[[dict], bool]) -> int`; queue keys `(cmd, task.get("vin"))` for `charge`/`applyChargeLimit`, `(cmd, vehicle.VIN)` for `setChargeRate`; `TWCMaster.cancelStopCarsCharging(vin=None) -> int`; `startCarsCharging(vin)` now passes `vin` into the `charge` task in stop mode 1 (TeslaAPI.car_api_charge already honours `task["vin"]`).

- [ ] **Step 1: Confirm the picks are conflict-free against main**

Run (read-only simulations; both must print only a tree id, no `CONFLICT` lines):
```bash
git merge-tree --write-tree --merge-base=cbd5952^ origin/main cbd5952
C=$(git commit-tree $(git merge-tree --write-tree --merge-base=cbd5952^ origin/main cbd5952) -p origin/main -m sim)
git merge-tree --write-tree --merge-base=cbd5952 $C ce9df78
```
Expected conflicts: none (verified 2026-10-13: trees `a1a8107…` and `545831c…`). `origin/main:lib/TWCManager/VehicleCommandQueue.py` is byte-identical to the first commit's parent (`1d41869`).

- [ ] **Step 2: Cherry-pick**

```bash
git cherry-pick -x cbd5952 ce9df78
```

- [ ] **Step 3: Run the suite**

Run: `python -m pytest tests/unit -q`
Expected: all pass (the picked commits replace `test_stop_replaces_pending_vehicleless_start`/`test_start_replaces_pending_stop` with `TestKeying`/`TestCancel`).

- [ ] **Step 4: Changelog and commit**

Add under `## v1.4.0 - Upcoming` → `* Bugfixes`:
`    * (@MikeBishop) - Queue vehicle commands per VIN and really cancel pending stop-charging commands when charging resumes (closes #667)`

```bash
git add CHANGELOG.md
git commit -m "Add changelog entry for per-VIN vehicle command queue (#667)"
```

