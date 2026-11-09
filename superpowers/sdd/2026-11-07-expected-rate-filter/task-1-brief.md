### Task 1: Home amps samples on Vehicle, saved with the registry

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py`
- Modify: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py` (`toJSON`, `_loadOne`)
- Test: `tests/unit/test_registry_vehicle.py`

**Interfaces:**
- Produces:
  - `HOME_AMPS_KEPT = 5` (Vehicle.py).
  - `Vehicle.noteHomeAmps(amps: float, since: float) -> bool`: True if recorded. False when `since <= ` the stored since, or `amps` isn't a positive number.
  - `Vehicle.homeAmps() -> List[float]`: oldest first.
  - Both are guarded by `self._lock`.
  - The registry entry gains `"homeAmps": {"amps": [...], "since": float}` only when there are samples.

- [ ] **Step 1: Write the failing tests**

```python
def test_home_amps_keep_the_last_five_one_per_plug_in():
    r = VehicleRegistry(clock=lambda: 1000.0); v = r.getOrCreate(VIN, "t")
    for i, amps in enumerate((48, 32, 48, 16, 48, 40)):
        assert v.noteHomeAmps(amps, since=100 + i)
    assert v.homeAmps() == [32, 48, 16, 48, 40]
    assert not v.noteHomeAmps(6, since=105)                 # same plug-in
    assert not v.noteHomeAmps(0, since=200)

def test_home_amps_survive_a_save_and_load_and_keep_their_plug_in():
    r = VehicleRegistry(clock=lambda: 1000.0); v = r.getOrCreate(VIN, "t"); v.noteHomeAmps(48, since=500)
    r2 = VehicleRegistry(clock=lambda: 1000.0); r2.load(r.toJSON()); v2 = r2.get(VIN)
    assert v2.homeAmps() == [48] and not v2.noteHomeAmps(6, since=float("-inf"))  # a restart's NEVER

def test_unreadable_saved_home_amps_are_dropped():
    blob = {"version": 1, "vehicles": {VIN: {"homeAmps": {"amps": ["x", -3, 32, 32, 32, 32, 32, 40], "since": "y"}}}}
    r = VehicleRegistry(clock=lambda: 1000.0); r.load(blob)
    assert r.get(VIN).homeAmps() == [32, 32, 32, 32, 40]
```

Use the file's existing `VIN` and constructor style. Adjust the constructor call to match how the file builds registries.

- [ ] **Step 2:** Run `pytest tests/unit/test_registry_vehicle.py -k home_amps -v`. Expected: FAIL, no `noteHomeAmps`.
- [ ] **Step 3:** Implement. On load:
  - keep only positive numbers, the last 5;
  - a non-number `since` becomes NEVER;
  - restore through a private setter, not `noteHomeAmps`, so the loaded since is kept even when it is NEVER.
- [ ] **Step 4:** Run the Step 2 tests plus `pytest tests/unit/test_registry_vehicle.py tests/unit/test_vehicle_appearance.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Keep each car's home plug-in amps with the registry`.

