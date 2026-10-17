### Task 3: Field store with value/source/time and own-write stamps

**Files:**
- Create: `lib/TWCManager/Vehicle/Registry/__init__.py`, `lib/TWCManager/Vehicle/Registry/Fields.py`.
- Test: `tests/unit/test_registry_fields.py`.

**Interfaces:**
- Produces (`Fields.py`):
  - `class Observation(NamedTuple): value: Any; source: str; at: float`
  - `FIELDS = ("name", "batteryLevel", "chargeLimit", "chargingState", "pluggedIn", "state", "lat", "lon", "gpsAsOf", "actualCurrent", "availableCurrent", "voltage", "phases", "timeToFullCharge", "scheduledChargingPending", "twcVin", "bleReach")` (`state` holds the TeslaMate-style strings `asleep|offline|online|charging|updating|driving`).
  - `TELEMETRY_SOURCES = frozenset({"TeslaMateVehicle", "FleetTelemetryMQTT"})` (source names are the module class names; used by `CarApiVehicle.syncSource`/`is_awake`). A source is **report-on-change** (publishes a value only when it changes, so an old value can still be current while the feed is healthy) exactly when it has registered liveness with the registry (Task 6); the field store itself only sees the `liveAt` argument.
  - `FEED_LAG = 30.0` seconds: how long a healthy report-on-change feed is given to report a change after one of our own writes before its silence counts as "the write did not land" (TeslaMate polls an awake car every few seconds; 30 s is a safe margin).
  - `class FieldStore:` `__init__(self, clock: Callable[[], float] = time.time)`; `observe(field, value, source, at=None) -> Observation` (raises `KeyError` for a field not in `FIELDS`; `at` is when the value was reported, i.e. `valueChangedAt` for a report-on-change source); `latest(field) -> Optional[Observation]`; `NOT_TRACKED = object()` sentinel; `age(field, now=None, liveAt=NOT_TRACKED) -> Optional[float]`: `liveAt` is the feed's liveness evidence for the observation's source — `NOT_TRACKED` for a polled source (age is `now - obs.at`), `None` for a report-on-change feed that is unhealthy (also `now - obs.at`), a timestamp for a healthy one (`now - max(obs.at, liveAt)`); `noteWrite(field, value, source, at=None) -> Observation`; `lastWrite(field) -> Optional[Observation]`; `fresherThanWrite(field) -> bool` (True when there is no write, or `latest.at > lastWrite.at` — strictly newer; an observation stamped at the same instant as our write is not trusted over it, ruling P1); `trusted(field, now=None, liveAt=NOT_TRACKED) -> Optional[Observation]`: the latest observation when `fresherThanWrite`, or when its feed is healthy (`liveAt` is a timestamp) and `now - lastWrite.at > FEED_LAG` (the feed had time to report a change and did not); otherwise `None` (an apply must use our written value; a restore forces a live read, Phase 3 rules); `snapshot() -> Dict[str, Observation]`. Internal `threading.Lock` (not reentrant: nothing may call back into the store while it is held).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_registry_fields.py
import pytest
from TWCManager.Vehicle.Registry.Fields import FieldStore, Observation, FIELDS

class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

def test_observe_and_latest_carry_value_source_time():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 80, "TeslaBLE")
    assert s.latest("chargeLimit") == Observation(80, "TeslaBLE", 1000.0)
    assert s.latest("batteryLevel") is None

def test_age_uses_clock():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("batteryLevel", 50, "TeslaAPI"); c.t = 1030.0
    assert s.age("batteryLevel") == 30.0
    assert s.age("lat") is None

def test_unknown_field_rejected():
    with pytest.raises(KeyError):
        FieldStore().observe("notAField", 1, "x")

def test_own_write_stamp_and_freshness():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 80, "TeslaMateVehicle", at=900.0)
    assert s.fresherThanWrite("chargeLimit") is True          # no write yet
    s.noteWrite("chargeLimit", 70, "TeslaBLE")                 # at 1000
    assert s.lastWrite("chargeLimit") == Observation(70, "TeslaBLE", 1000.0)
    assert s.fresherThanWrite("chargeLimit") is False          # stored 900 < write 1000
    s.observe("chargeLimit", 70, "TeslaMateVehicle", at=1000.0)
    assert s.fresherThanWrite("chargeLimit") is False          # same instant: not fresher (P1)
    s.observe("chargeLimit", 70, "TeslaMateVehicle", at=1000.5)
    assert s.fresherThanWrite("chargeLimit") is True

def test_snapshot_is_a_copy():
    s = FieldStore(); s.observe("lat", 1.0, "TeslaAPI")
    snap = s.snapshot(); s.observe("lat", 2.0, "TeslaAPI")
    assert snap["lat"].value == 1.0 and set(snap) == {"lat"}

def test_report_on_change_age_counts_from_feed_liveness():
    c = Clock(); s = FieldStore(clock=c)
    s.observe("chargeLimit", 50, "TeslaMateVehicle", at=100.0)   # old value, still current
    assert s.age("chargeLimit", liveAt=990.0) == 10.0            # healthy feed: age from liveness
    assert s.age("chargeLimit", liveAt=None) == 900.0            # unhealthy feed: age from the change
    s.observe("batteryLevel", 50, "TeslaAPI", at=100.0)
    assert s.age("batteryLevel") == 900.0                        # polled source: NOT_TRACKED

def test_trusted_after_own_write_waits_for_feed_lag():          # the 2026-10-12 09:17 shape
    c = Clock(t=1000.0); s = FieldStore(clock=c)
    s.observe("chargeLimit", 50, "TeslaMateVehicle", at=900.0)
    s.noteWrite("chargeLimit", 100, "TeslaBLE")                  # written at t=1000
    c.t = 1003.0
    assert s.trusted("chargeLimit", liveAt=1003.0) is None       # too soon: use our written 100
    c.t = 1000.0 + FEED_LAG + 1
    assert s.trusted("chargeLimit", liveAt=c.t).value == 50      # feed healthy, no change event: our write did not land
    assert s.trusted("chargeLimit", liveAt=None) is None         # unhealthy feed proves nothing
    s.observe("chargeLimit", 100, "TeslaMateVehicle")            # change event arrives
    assert s.trusted("chargeLimit", liveAt=c.t).value == 100
```
(`FEED_LAG` joins the imports.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_registry_fields.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Registry'`.

- [ ] **Step 3: Implement `Fields.py` and the package `__init__.py`** per the Interfaces block (the `__init__` re-exports grow in later tasks).

- [ ] **Step 4: Run tests** — `python -m pytest tests/unit/test_registry_fields.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/
git add lib/TWCManager/Vehicle/Registry tests/unit/test_registry_fields.py
git commit -m "Add the vehicle field store: value, source and time per field with own-write stamps"
```

