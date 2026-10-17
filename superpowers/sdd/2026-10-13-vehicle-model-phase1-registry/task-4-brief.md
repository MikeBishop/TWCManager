### Task 4: `Vehicle`: identity, claims, tier, attachments, summary

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/VIN.py`, `lib/TWCManager/Vehicle/Registry/Vehicle.py`.
- Test: `tests/unit/test_registry_vehicle.py`.

**Interfaces:**
- Consumes: `FieldStore`, `Observation`, `FIELDS` (Task 3).
- Produces:
  - `VIN.py`: `WELL_FORMED = re.compile(r"[A-HJ-NPR-Z0-9]{17}")`; `isWellFormedVIN(vin: str) -> bool` (upper-cases first).
  - `Vehicle.py`:
    - `class Claim:` fields `provider: str`, `canCommand: Union[bool, Callable[[], bool]]`, `status: str`, `since: float`; property `commands -> bool` (calls the callable).
    - `class Vehicle:` `__init__(self, key: str, vin: Optional[str], registry, clock=time.time, userAsserted=False)`; attributes `key`, `vin`, `isAnonymous` (`vin is None`), `userAsserted`, `firstSeen`, `lastSeen`, `lastSeenSource` (floats/str, set on creation to clock()/`"created"`), `_fields: FieldStore`; methods `observe(field, value, source, at=None, seen=True) -> Observation` (updates `lastSeen`/`lastSeenSource` when `seen`), `latest(field)`, `age(field)` and `trusted(field)` (both pass `liveAt=self._registry.sourceLiveAt(obs.source, self)` when a registry is attached, else `NOT_TRACKED`), `value(field, default=None)` (latest value or default; template-friendly, never fetches), `noteWrite(field, value, source)`, `fresherThanWrite(field)`, `read(field, maxAge, allowWake=False)` (Task 5), `claim(provider, canCommand, status="") -> Claim`, `dropClaim(provider) -> bool`, `claims -> Dict[str, Claim]` (copy), property `tier -> str` (`"managed"` if any claim `.commands` and not anonymous, else `"observed"`), `attach(name, obj)`, `attachment(name) -> Optional[Any]`, property `name -> str` (latest `"name"` value or `""`), `summary() -> dict` with keys `key, vin, name, anonymous, userAsserted, tier, claims` (list of `{provider, status, commands}`), `point` (anonymous: `key[5:]`; else latest `twcVin` value or `None`), `lastSeen, lastSeenAge` (`clock() - lastSeen`), `lastSeenSource, fields` (`{field: {"value", "source", "age"}}`).
    - Its own `threading.Lock` (`_lock`) for claims/attachments/lastSeen; the `FieldStore` keeps its own (`_lock`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_vehicle.py
from TWCManager.Vehicle.Registry.VIN import isWellFormedVIN
from TWCManager.Vehicle.Registry.Vehicle import Vehicle

VIN = "5YJ3E1EA1KF000001"
class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_vin_format():
    assert isWellFormedVIN(VIN) and isWellFormedVIN(VIN.lower())
    assert not isWellFormedVIN("5YJ3E1EA1KF00000I")   # I
    assert not isWellFormedVIN("5YJ3E1EA1KF0000011")  # 18 chars
    assert not isWellFormedVIN("")

def test_identity_and_tier_default_observed():
    v = Vehicle(VIN, VIN, registry=None)
    assert (v.key, v.vin, v.isAnonymous, v.tier) == (VIN, VIN, False, "observed")
    a = Vehicle("anon:1234", None, registry=None)
    assert a.isAnonymous and a.tier == "observed"

def test_commanding_claim_makes_managed_and_callable_is_live():
    flag = {"ro": True}
    v = Vehicle(VIN, VIN, registry=None)
    v.claim("TeslaAPI", lambda: not flag["ro"], "listed")
    assert v.tier == "observed"
    flag["ro"] = False
    assert v.tier == "managed"
    assert v.dropClaim("TeslaAPI") is True and v.tier == "observed"
    assert v.dropClaim("TeslaAPI") is False

def test_anonymous_never_managed():
    a = Vehicle("anon:1234", None, registry=None)
    a.claim("TeslaBLE", True)
    assert a.tier == "observed"

def test_observe_bumps_last_seen_unless_told_not_to():
    c = Clock(); v = Vehicle(VIN, VIN, registry=None, clock=c)
    c.t = 2000.0; v.observe("chargeLimit", 80, "TeslaMateVehicle")
    assert (v.lastSeen, v.lastSeenSource) == (2000.0, "TeslaMateVehicle")
    c.t = 3000.0; v.observe("name", "Car", "TeslaAPI", seen=False)
    assert v.lastSeen == 2000.0 and v.name == "Car"

def test_attachments_and_summary():
    c = Clock(); v = Vehicle(VIN, VIN, registry=None, clock=c)
    obj = object(); v.attach("TeslaAPI", obj)
    assert v.attachment("TeslaAPI") is obj and v.attachment("HomeAssistant") is None
    v.claim("TeslaBLE", True, "paired"); v.observe("batteryLevel", 42, "TeslaBLE"); c.t = 1010.0
    s = v.summary()
    assert s["tier"] == "managed" and s["claims"] == [{"provider": "TeslaBLE", "status": "paired", "commands": True}]
    assert s["fields"]["batteryLevel"] == {"value": 42, "source": "TeslaBLE", "age": 10.0}
    assert s["lastSeenAge"] == 10.0 and s["point"] is None and Vehicle("anon:8244", None, registry=None).summary()["point"] == "8244"
    assert v.value("batteryLevel") == 42 and v.value("lon", 0) == 0
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/unit/test_registry_vehicle.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `VIN.py` and `Vehicle.py`** per Interfaces; `read()` is a stub raising `NotImplementedError` until Task 5.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_vehicle.py
git commit -m "Add registry Vehicle with VIN or anonymous identity, claims and tiers"
```

