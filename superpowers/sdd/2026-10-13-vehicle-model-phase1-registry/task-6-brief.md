### Task 6: `VehicleRegistry`: membership, forgetting, persistence, manual add

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/__init__.py`.
- Test: `tests/unit/test_registry_membership.py`.

**Interfaces:**
- Consumes: `Vehicle`, `isWellFormedVIN`, `ReadSource`.
- Produces `class VehicleRegistry:`
  - `DEFAULT_FORGET_DAYS = 30`; `__init__(self, config: dict, clock=time.time)`; `self.forgetAfter = config.get("vehicle", {}).get("forgetAfterDays", 30) * 86400`; `_lock = threading.RLock()`.
  - `@classmethod forMaster(cls, master) -> VehicleRegistry`: `master.vehicleRegistry` when it is a `VehicleRegistry`, else a private `VehicleRegistry(getattr(master, "config", {}) or {})` (so tests with `Mock()` masters keep working).
  - `getOrCreate(vin: str, source: str) -> Vehicle` (upper-cases; no format check: provider lists are trusted; creation logs INFO `Vehicle <vin> added (<source>)`); `get(key) -> Optional[Vehicle]`; `vehicles() -> List[Vehicle]` sorted by key; `findByName(name) -> Optional[Vehicle]`; `attached(name) -> List[Any]` (attachments of that name over `vehicles()`); `addUserAsserted(vin) -> Vehicle` (raises `ValueError("VIN must be 17 characters without I, O or Q")` when not well-formed; existing vehicle → returned with `userAsserted=True`); `forget(key) -> bool`; `expire(now=None) -> List[str]` (removes non-anonymous vehicles with no claims at all — a provider that still lists the car keeps it, ruling 4 — `not userAsserted` (ruling 5), and `now - lastSeen > forgetAfter`; logs INFO per removal); `registerReadSource(source)`, `readSources()` (sorted by `(order, registration index)`); `registerLiveness(source: str, liveAt: Callable[[Vehicle], Optional[float]])` and `sourceLiveAt(source, vehicle)` (calls the registered callable with the vehicle — a timestamp when that car's feed is healthy, `None` when not — and returns `Fields.NOT_TRACKED` for an unregistered source, so registering liveness is what makes a source report-on-change). Vehicles are created with the registry's `clock`. `load()` records persisted names as observations with source `"persisted"`, `seen=False`.
  - Persistence: `toJSON() -> dict` = `{"version": 1, "vehicles": {vin: {"name", "firstSeen", "lastSeen", "lastSeenSource", "userAsserted"}}}` (anonymous vehicles omitted); `load(data) -> None` merges (keeps existing vehicles, takes the older `firstSeen` and newer `lastSeen`); ignores non-dict input and malformed entries without raising.
  - `summaries() -> List[dict]` = `[v.summary() for v in vehicles()]`.
  - Plug sessions and TWC confirmation: Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_membership.py
import pytest
from unittest.mock import Mock
from TWCManager.Vehicle.Registry.Fields import NOT_TRACKED
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry

VIN = "5YJ3E1EA1KF000001"; VIN2 = "5YJ3E1EA1KF000002"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_get_or_create_is_idempotent_and_uppercases():
    r = VehicleRegistry({})
    a = r.getOrCreate(VIN.lower(), "TeslaAPI"); b = r.getOrCreate(VIN, "TeslaBLE")
    assert a is b and a.vin == VIN and [v.key for v in r.vehicles()] == [VIN]

def test_for_master_prefers_real_registry_else_private():
    real = VehicleRegistry({}); m = Mock(); m.vehicleRegistry = real
    assert VehicleRegistry.forMaster(m) is real
    m2 = Mock(); m2.config = {"config": {}}
    assert isinstance(VehicleRegistry.forMaster(m2), VehicleRegistry)

def test_user_asserted_add_validates_format():
    r = VehicleRegistry({})
    with pytest.raises(ValueError):
        r.addUserAsserted("5YJ3E1EA1KF00000I")
    v = r.addUserAsserted(VIN)
    assert v.userAsserted and v.tier == "observed"
    assert r.addUserAsserted(VIN) is v

def test_expire_forgets_unclaimed_after_default_30_days_but_not_claimed_or_asserted():
    c = Clock(); r = VehicleRegistry({}, clock=c)
    r.getOrCreate(VIN, "TWC"); r.getOrCreate(VIN2, "TeslaBLE").claim("TeslaBLE", True)
    r.addUserAsserted("5YJ3E1EA1KF000003")
    r.getOrCreate("5YJ3E1EA1KF000004", "TeslaAPI").claim("TeslaAPI", False, "listed")   # read-only cloud listing
    c.t = 1000.0 + 29 * 86400
    assert r.expire() == []
    c.t = 1000.0 + 31 * 86400
    assert r.expire() == [VIN]
    assert [v.key for v in r.vehicles()] == [VIN2, "5YJ3E1EA1KF000003", "5YJ3E1EA1KF000004"]
    r.get("5YJ3E1EA1KF000004").dropClaim("TeslaAPI"); c.t += 31 * 86400
    assert r.expire() == ["5YJ3E1EA1KF000004"]                                           # lost its last listing

def test_forget_days_configurable():
    c = Clock(); r = VehicleRegistry({"vehicle": {"forgetAfterDays": 1}}, clock=c)
    r.getOrCreate(VIN, "TWC"); c.t = 1000.0 + 2 * 86400
    assert r.expire() == [VIN]

def test_persistence_round_trip_and_merge():
    c = Clock(); r = VehicleRegistry({}, clock=c)
    v = r.getOrCreate(VIN, "TWC"); v.observe("name", "Car", "TeslaAPI"); c.t = 2000.0
    v.observe("chargeLimit", 80, "TeslaBLE")
    data = r.toJSON()
    assert data["vehicles"][VIN] == {"name": "Car", "firstSeen": 1000.0, "lastSeen": 2000.0,
                                     "lastSeenSource": "TeslaBLE", "userAsserted": False}
    r2 = VehicleRegistry({}, clock=Clock(3000.0)); r2.getOrCreate(VIN, "TeslaAPI"); r2.load(data)
    w = r2.get(VIN)
    assert (w.firstSeen, w.lastSeen, w.name) == (1000.0, 3000.0, "Car")

@pytest.mark.parametrize("bad", [None, "x", 3, {"vehicles": "nope"}, {"vehicles": {VIN: "str"}}])
def test_load_ignores_garbage(bad):
    r = VehicleRegistry({}); r.load(bad)
    assert r.vehicles() == []

def test_liveness_feeds_vehicle_age_and_trust():
    c = Clock(); r = VehicleRegistry({}, clock=c); live = {"at": 990.0}
    r.registerLiveness("TeslaMateVehicle", lambda vehicle: live["at"] if vehicle.vin == VIN else None)
    v = r.getOrCreate(VIN, "TeslaMateVehicle"); v.observe("chargeLimit", 50, "TeslaMateVehicle", at=100.0)
    assert v.age("chargeLimit") == 10.0
    live["at"] = None
    assert v.age("chargeLimit") == 900.0 and r.sourceLiveAt("TeslaAPI", v) is NOT_TRACKED

def test_find_by_name_and_attached():
    r = VehicleRegistry({}); v = r.getOrCreate(VIN, "TeslaAPI"); v.observe("name", "TestCar", "TeslaAPI")
    v.attach("TeslaAPI", "obj")
    assert r.findByName("TestCar") is v and r.findByName("x") is None
    assert r.attached("TeslaAPI") == ["obj"] and r.attached("HomeAssistant") == []
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `VehicleRegistry.py`** per Interfaces; export from `__init__.py`.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_membership.py
git commit -m "Add VehicleRegistry with forgetting, persistence and user-asserted vehicles"
```

