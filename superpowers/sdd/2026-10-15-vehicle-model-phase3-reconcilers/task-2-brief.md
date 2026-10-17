### Task 2: Registry support (`believed`, restricted reads) and the held-limit store (removes the `-1` sentinel's storage)

`settings["chargeLimits"][ID] = (outside, lastApplied)` with `lastApplied == -1` meaning "we hold none" (`TWCMaster.getNormalChargeLimit`, `saveNormalChargeLimit`, `removeNormalChargeLimit`; keyed by VIN from BLE and by numeric API ID from TeslaAPI; `HTTPControl.heldLimitText` tries both). The new store is VIN-keyed, `held` is `None` when nothing is held, and the old key is migrated on load.

**Files:**
- Create: `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py` (`read(sources=, force=)`, new `believed`, `latestFrom`); `lib/TWCManager/TWCMaster.py` (`self.heldLimits = HeldLimits(self)` in `__init__`; `loadSettings` calls `self.heldLimits.load()` after the settings dict is assigned; `getNormalChargeLimit`/`saveNormalChargeLimit`/`removeNormalChargeLimit` become thin wrappers over it until Task 10 deletes them); `lib/TWCManager/Vehicle/TeslaAPI.py` `CarApiVehicle._bind` (calls `carapi.master.heldLimits.adoptLegacyId(self.ID, self.VIN)`); `lib/TWCManager/Control/HTTPControl.py` (`heldLimitText` reads `master.heldLimits.get(vehicle.vin)`, keeping today's "N% (restored)" text when `held` is `None`).
- Test: `tests/unit/test_held_limits.py`; `tests/unit/test_registry_read_cascade.py` gains the `sources=` and `force=` cases; `tests/unit/test_vehicles_page.py` held-limit assertions adjusted to the new store.

**Interfaces:**
- Produces (`Vehicle`): `latestFrom(self, field, exclude=()) -> Optional[Observation]`: the newest observation of `field` whose source is not in `exclude` (over `reportedBy` per source). `believed(self, field, exclude=()) -> Optional[Observation]`: `latestFrom(field, exclude)` when it is strictly newer than `lastWrite(field)`, else the last own write, else that observation, else `None` — the value we act on (`presence/2`'s `latestChargeLimit` rule on the registry; `exclude` lets the reconciler leave TWC-sourced observations out of a car's own state). `trusted(self, field, exclude=()) -> Optional[Observation]`: as the Phase 1 `trusted`, computed over `latestFrom(field, exclude)` (so an excluded source that wrote the field last does not hide a trusted vehicle read). `read(self, field, maxAge, allowWake=False, sources=None, force=False)`: when `sources` is given the cascade runs over `[s for s in sources if s in self._registry.readSources()]` in registry order instead of every source; `force=True` skips the freshness check and cascades even when the stored value is fresh (a live report-on-change feed makes `age()` 0, which a restore must not trust).
- Produces (`HeldLimits.py`): `class HeldLimit(NamedTuple): outside: int; held: Optional[int]`. `class HeldLimits:` `KEY = "heldLimits"`, `LEGACY_KEY = "chargeLimits"`; `__init__(self, master)`; `load(self) -> None` (under `settingsLock`: reads `settings["heldLimits"]` (`{VIN: {"outside": int, "held": int|null}}`); when absent and `chargeLimits` exists, migrates each entry: an int `n` → `HeldLimit(n, None)`; `(o, -1)`/`(o, None)`/`(o, 0)` → `HeldLimit(o, None)`; `(o, n)` with `50 <= n <= 100` → `HeldLimit(o, n)`; a well-formed VIN key goes into the store under the VIN, any other key is **persisted** under `"id:<key>"` (never memory-only: an install whose TeslaAPI does not bind the car this run keeps its held limit); then deletes `chargeLimits`, writes `heldLimits` and queues `saveSettings`; malformed entries are dropped with one WARNING per key); `get(self, vin) -> Optional[HeldLimit]`; `set(self, vin, outside, held) -> None` (under `settingsLock`, then `saveSettings`); `remove(self, vin) -> None`; `adoptLegacyId(self, legacyId, vin) -> None` (moves an `id:` entry under the VIN unless the VIN already has one, and saves); `vins() -> List[str]` and `holding() -> List[str]` (VINs with `held is not None`) return well-formed VIN keys only, never `id:` entries. All VINs upper-cased. The interim `TWCMaster` wrappers accept a numeric ID as well: they resolve it to a VIN through TeslaAPI's vehicle list when loaded, else read or write the `id:` entry.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_held_limits.py
from TWCManager.Vehicle.Reconcile.HeldLimits import HeldLimit, HeldLimits
from tests.unit.test_gen2twc_provider import make, VIN
VIN2 = "5YJ3E1EA1KF000002"

def test_legacy_charge_limits_migrate():                                   # Review Focus 3
    m, s = make(); m.settings["chargeLimits"] = {VIN: (80, -1), VIN2.lower(): [90, 50], "12345": 85, "bad": "x"}
    m.heldLimits.load()
    assert m.heldLimits.get(VIN) == HeldLimit(80, None) and m.heldLimits.get(VIN2) == HeldLimit(90, 50)
    assert "chargeLimits" not in m.settings and m.settings["heldLimits"][VIN2] == {"outside": 90, "held": 50} and m.settings["heldLimits"]["id:12345"] == {"outside": 85, "held": None}
    assert m.getNormalChargeLimit(12345) == (True, 85, -1)                                       # the interim wrapper still answers by ID
    m.heldLimits.adoptLegacyId(12345, "5YJ3E1EA1KF000003"); assert m.heldLimits.get("5YJ3E1EA1KF000003") == HeldLimit(85, None) and "id:12345" not in m.settings["heldLimits"]
    assert m.heldLimits.holding() == [VIN2]

def test_set_remove_and_wrappers_keep_working():
    m, s = make(); m.heldLimits.load(); m.heldLimits.set(VIN, 80, 50)
    assert m.getNormalChargeLimit(VIN) == (True, 80, 50)
    m.heldLimits.set(VIN, 80, None); assert m.getNormalChargeLimit(VIN) == (True, 80, -1)      # wrapper keeps the old tuple until Task 10
    m.heldLimits.remove(VIN); assert m.heldLimits.get(VIN) is None and m.getNormalChargeLimit(VIN) == (False, None, None)

def test_believed_prefers_a_newer_read_over_our_write():
    m, s = make(); v = m.vehicleRegistry.getOrCreate(VIN, "t"); c = m.vehicleRegistry._clock
    v.observe("chargeLimit", 90, "TeslaAPI"); assert v.believed("chargeLimit").value == 90
    v.noteWrite("chargeLimit", 50, "TeslaBLE"); assert v.believed("chargeLimit").value == 50          # our write is newer than the read
    v.observe("chargeLimit", 80, "TeslaMateVehicle", at=v.lastWrite("chargeLimit").at + 1); assert v.believed("chargeLimit").value == 80
    v.observe("chargingState", "Charging", "Gen2TWC", at=v.lastWrite("chargeLimit").at + 2)
    assert v.believed("chargingState", exclude={"Gen2TWC"}) is None and v.latestFrom("chargingState").source == "Gen2TWC"
```
Add to `tests/unit/test_registry_read_cascade.py`: `test_read_with_sources_skips_other_sources` (two registered sources; `read(field, 0, sources=[second])` calls only the second's `fetch`) and `test_force_reads_past_a_live_feed` (a `TeslaMateVehicle` observation with `registerLiveness` returning now: `read(field, 300)` fetches nothing, `read(field, 300, force=True)` calls the source's `fetch` once).

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `HeldLimits`; `AttributeError: believed`).

- [ ] **Step 3: Implement** per Interfaces; `heldLimitText` shows `held` as the applied limit and keeps today's "N% (restored)" wording when `held` is `None`.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_held_limits.py tests/unit/test_registry_read_cascade.py tests/unit/test_registry_vehicle.py tests/unit/test_vehicles_page.py tests/unit/test_twcmaster.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Reconcile/ lib/TWCManager/Vehicle/Registry/Vehicle.py lib/TWCManager/TWCMaster.py lib/TWCManager/Control/HTTPControl.py
git add lib/TWCManager tests/unit
git commit -m "Store held charge limits by VIN without the -1 sentinel and let a vehicle report the value it believes"
```

