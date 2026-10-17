### Task 5: Read sources and the `read(field, maxAge, allowWake)` cascade

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/ReadSource.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`read`).
- Test: `tests/unit/test_registry_read_cascade.py`.

**Interfaces:**
- Produces:
  - `class ReadSource:` attributes `name: str`, `order: int` (0 local, 1 cloud; lower first — this is only a sequencing hint for Phase 1, not the Phase 2 cost model), `fields: FrozenSet[str]`; methods `canRead(self, vehicle) -> bool` (default True), `fetch(self, vehicle, field: str, allowWake: bool) -> Optional[Dict[str, Any]]` (abstract; returns observations to record keyed by field name, `{}` when the source wrote them itself, `None` on failure; must never wake unless `allowWake`).
  - `cascade(vehicle, sources, field, allowWake) -> Optional[Observation]`: for each source in order with `field in source.fields and source.canRead(vehicle)`: `result = source.fetch(...)` (no registry/vehicle lock held); if not None, `vehicle.observe(k, v, source.name)` for each item and return `vehicle.latest(field)`. Exceptions from `fetch` are logged at DEBUG and count as failure.
  - `Vehicle.read(field, maxAge: Optional[float], allowWake=False) -> Optional[Observation]`: if `maxAge is None` → `latest(field)` only (never fetches); if latest exists and `age <= maxAge` → return it; else `cascade(self, self._registry.readSources(), field, allowWake)`, falling back to `latest(field)` when every source fails (registry `None` → return latest). A `registry` passed to `Vehicle` must expose `readSources() -> List[ReadSource]` and `sourceLiveAt(source, vehicle)` (ruling P2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_read_cascade.py
from TWCManager.Vehicle.Registry.Fields import NOT_TRACKED
from TWCManager.Vehicle.Registry.ReadSource import ReadSource
from TWCManager.Vehicle.Registry.Vehicle import Vehicle

VIN = "5YJ3E1EA1KF000001"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

class Src(ReadSource):
    def __init__(self, name, order, result, fields=("chargeLimit", "batteryLevel")):
        self.name, self.order, self.fields = name, order, frozenset(fields)
        self.result, self.calls = result, []
    def fetch(self, vehicle, field, allowWake):
        self.calls.append((field, allowWake))
        assert not vehicle._fields._lock.locked() and not vehicle._lock.locked()
        return self.result

class Reg:
    def __init__(self, *sources): self.sources = list(sources)
    def readSources(self): return sorted(self.sources, key=lambda s: s.order)
    def sourceLiveAt(self, source, vehicle): return NOT_TRACKED   # polled sources only here

def test_fresh_value_returned_without_fetch():
    c = Clock(); src = Src("BLE", 0, {"chargeLimit": 90})
    v = Vehicle(VIN, VIN, Reg(src), clock=c); v.observe("chargeLimit", 80, "X"); c.t = 1010.0
    assert v.read("chargeLimit", maxAge=30).value == 80 and src.calls == []

def test_stale_value_cascades_in_order_and_stops_at_first_success():
    c = Clock(); ble = Src("BLE", 0, None); api = Src("API", 1, {"chargeLimit": 90, "batteryLevel": 55})
    v = Vehicle(VIN, VIN, Reg(api, ble), clock=c); v.observe("chargeLimit", 80, "X"); c.t = 1100.0
    obs = v.read("chargeLimit", maxAge=30)
    assert (obs.value, obs.source, obs.at) == (90, "API", 1100.0)
    assert v.latest("batteryLevel").value == 55
    assert ble.calls == [("chargeLimit", False)] and api.calls == [("chargeLimit", False)]

def test_allow_wake_is_passed_through_and_defaults_false():
    src = Src("BLE", 0, {"chargeLimit": 1}); v = Vehicle(VIN, VIN, Reg(src))
    v.read("chargeLimit", maxAge=0); v.read("chargeLimit", maxAge=0, allowWake=True)
    assert [w for _, w in src.calls] == [False, True]

def test_max_age_none_never_fetches():
    src = Src("BLE", 0, {"chargeLimit": 1}); v = Vehicle(VIN, VIN, Reg(src))
    assert v.read("chargeLimit", maxAge=None) is None and src.calls == []

def test_source_without_field_or_declining_is_skipped():
    loc = Src("LOC", 0, {"lat": 1.0}, fields=("lat", "lon"))
    shy = Src("SHY", 0, {"chargeLimit": 5}); shy.canRead = lambda vehicle: False
    v = Vehicle(VIN, VIN, Reg(loc, shy))
    assert v.read("chargeLimit", maxAge=0) is None and loc.calls == [] and shy.calls == []

def test_all_sources_fail_returns_stale_latest():
    c = Clock(); src = Src("BLE", 0, None); v = Vehicle(VIN, VIN, Reg(src), clock=c)
    v.observe("chargeLimit", 80, "X"); c.t = 5000.0
    assert v.read("chargeLimit", maxAge=1).value == 80
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `ReadSource`).

- [ ] **Step 3: Implement `ReadSource.py` and `Vehicle.read`** per Interfaces (`FieldStore` exposes its lock as `_lock` for the test's no-lock-across-I/O assertion).

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_read_cascade.py
git commit -m "Add read sources and the freshness-bounded read cascade that never wakes unasked"
```

