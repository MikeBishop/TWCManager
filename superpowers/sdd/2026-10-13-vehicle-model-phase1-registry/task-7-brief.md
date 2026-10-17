### Task 7: Anonymous plug-session vehicles and TWC VIN confirmation

On main a Gen2 "plug session" is the `isCharging` session in `TWCMaster.num_cars_charging_now` (≥ 1 A, 5 s debounce); plug detection proper arrives with Phase 5. The registry's plug-session API is keyed by a point id (the TWC id hex string) so Phase 2 charging points can reuse it.

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`; `lib/TWCManager/TWCMaster.py:1201-1262` (`num_cars_charging_now`), `:1405-1451` (`recordVehicleVIN`).
- Test: `tests/unit/test_registry_plug_sessions.py`, `tests/unit/test_twcmaster_vin_confirmation.py`.

**Interfaces:**
- Produces (`VehicleRegistry`):
  - `beginPlugSession(pointId: str) -> Vehicle`: creates/returns the anonymous vehicle `key="anon:<pointId>"` (`vin=None`); idempotent.
  - `endPlugSession(pointId) -> None`: removes the anonymous vehicle if still anonymous, clears any pending confirmation for the point, and for a VIN vehicle attributed to the point observes `twcVin=None` (source `"TWC"`, `seen=False`).
  - `observeTwcVin(pointId: str, vin: str) -> str`: returns `"rejected"` when `not isWellFormedVIN(vin)`; `"confirmed"` when `get(vin)` exists (known vehicle: one read suffices) or when the point's pending candidate equals `vin` — on confirmation the anonymous vehicle for the point is merged (its observations copied into `getOrCreate(vin, "TWC")`, then removed) and `twcVin=pointId` is observed (source `"TWC"`); `"pending"` on the first sighting of an unknown VIN (or a different candidate, which replaces the pending one) with attempts counted; `"rejected"` after `CONFIRM_ATTEMPTS = 3` reads without two consecutive matches (INFO log `TWC <point> VIN <vin> not confirmed; ignoring`).
  - `CONFIRM_ATTEMPTS = 3`; `pointFor(vin) -> Optional[str]` (latest `twcVin` value); `vehicleAt(pointId) -> Optional[Vehicle]` (the VIN vehicle attributed to the point, else the anonymous one, else None).
- Produces (`TWCMaster`): `recordVehicleVIN(slaveTWC)` now: `status = self.vehicleRegistry.observeTwcVin(twcid, slaveTWC.currentVIN)`; on `"pending"` → `self.queue_background_task({"cmd": "getVehicleVIN", "slaveTWC": slaveTWC.TWCID, "vinPart": 0}, delay=5)` and return; on `"rejected"` → return; on `"confirmed"` → the existing `SlaveTWCs.supportsVINQuery` and `settings["Vehicles"]` session bookkeeping (under `with self.settingsLock:`; the `else` branch uses `.get("chargeSessions", 0) + 1` and `.setdefault("totalkWh", 0)` because Tasks 13 and 16 may create an entry without session counters), log, and `vehicleIsDefinitelyHome` exactly as today. `num_cars_charging_now`: `self.vehicleRegistry.beginPlugSession(twcid)` where `isCharging` flips to 1 and `endPlugSession(twcid)` where it flips to 0 (`twcid = "%02X%02X" % (slaveTWC.TWCID[0], slaveTWC.TWCID[1])`). `slaveTWC.currentVIN` is still set by the RX loop on the first valid parse (entitlement, `getTWCbyVIN`, status and `_twcServedVINs` are unchanged); only registry creation and history bookkeeping wait for confirmation. `TWCMaster.__init__` gains `self.vehicleRegistry = VehicleRegistry(config)` (Task 8 adds persistence).

- [ ] **Step 1: Write the failing registry tests**

```python
# tests/unit/test_registry_plug_sessions.py
from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
VIN = "5YJ3E1EA1KF000001"; BAD = "5YJ3E1EA1KF00000I"; OTHER = "5YJ3E1EA1KF000002"

def test_anonymous_vehicle_lives_with_the_session():
    r = VehicleRegistry({})
    a = r.beginPlugSession("8244")
    assert a.key == "anon:8244" and a.isAnonymous and r.beginPlugSession("8244") is a
    assert r.vehicleAt("8244") is a
    r.endPlugSession("8244")
    assert r.vehicles() == [] and r.vehicleAt("8244") is None

def test_unknown_vin_needs_two_matching_reads_then_merges_anonymous():
    r = VehicleRegistry({}); a = r.beginPlugSession("8244"); a.observe("actualCurrent", 12, "TWC")
    assert r.observeTwcVin("8244", VIN) == "pending" and r.get(VIN) is None
    assert r.observeTwcVin("8244", VIN) == "confirmed"
    v = r.get(VIN)
    assert v is not None and r.get("anon:8244") is None
    assert v.latest("twcVin").value == "8244" and v.latest("actualCurrent").value == 12
    assert r.pointFor(VIN) == "8244" and r.vehicleAt("8244") is v

def test_known_vin_confirms_at_once():
    r = VehicleRegistry({}); r.getOrCreate(VIN, "TeslaAPI"); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "confirmed"

def test_misheard_vin_creates_nothing_and_is_bounded():   # Review Focus 1
    r = VehicleRegistry({}); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "pending"
    assert r.observeTwcVin("8244", OTHER) == "pending"     # differs: candidate replaced
    assert r.observeTwcVin("8244", VIN) == "rejected"      # third read, no two in a row
    assert r.get(VIN) is None and r.get(OTHER) is None
    assert r.observeTwcVin("8244", VIN) == "rejected"      # stays rejected this session

def test_malformed_vin_rejected_and_session_end_clears_pending():
    r = VehicleRegistry({}); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", BAD) == "rejected"
    assert r.observeTwcVin("8244", VIN) == "pending"
    r.endPlugSession("8244"); r.beginPlugSession("8244")
    assert r.observeTwcVin("8244", VIN) == "pending"       # fresh session, fresh count

def test_session_end_clears_twc_vin_on_the_car():
    r = VehicleRegistry({}); r.getOrCreate(VIN, "TeslaAPI"); r.beginPlugSession("8244")
    r.observeTwcVin("8244", VIN); r.endPlugSession("8244")
    assert r.get(VIN).latest("twcVin").value is None and r.pointFor(VIN) is None
```

- [ ] **Step 2: Write the failing TWCMaster tests**

```python
# tests/unit/test_twcmaster_vin_confirmation.py
from unittest.mock import Mock
import pytest
from TWCManager.TWCMaster import TWCMaster
VIN = "5YJ3E1EA1KF000001"
CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False,
          "treatGenerationAsGridDelivery": False, "wiringMaxAmpsAllTWCs": 80, "maxAmpsAllowedFromGrid": None}}

@pytest.fixture
def master():
    m = TWCMaster("AB", CONFIG); m.getModuleByName = Mock(return_value=None)
    m.queue_background_task = Mock(); m.getModulesByType = Mock(return_value=[])
    return m

def slave(vin):
    s = Mock(); s.TWCID = bytearray(b"\x82\x44"); s.currentVIN = vin; s.lifetimekWh = 100; return s

def test_first_sighting_requeries_and_records_nothing(master):
    master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN))
    master.queue_background_task.assert_called_once_with(
        {"cmd": "getVehicleVIN", "slaveTWC": bytearray(b"\x82\x44"), "vinPart": 0}, delay=5)
    assert "Vehicles" not in master.settings or VIN not in master.settings["Vehicles"]

def test_second_matching_sighting_records_one_session(master):
    master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN)); master.recordVehicleVIN(slave(VIN))
    assert master.settings["Vehicles"][VIN]["chargeSessions"] == 1
    assert master.settings["SlaveTWCs"]["8244"]["supportsVINQuery"] == 1
    assert master.vehicleRegistry.get(VIN).latest("twcVin").value == "8244"

def test_known_vehicle_records_on_first_sighting(master):
    master.vehicleRegistry.getOrCreate(VIN, "TeslaAPI"); master.vehicleRegistry.beginPlugSession("8244")
    master.recordVehicleVIN(slave(VIN))
    assert master.settings["Vehicles"][VIN]["chargeSessions"] == 1
    assert not any(c.args[0]["cmd"] == "getVehicleVIN" for c in master.queue_background_task.call_args_list)

def test_charging_session_begins_and_ends_anonymous_vehicle(master):
    s = slave(""); s.reportedAmpsActual = 5.0; s.isCharging = 0; s.chargingDroppedBelowThresholdTime = 0
    master.getSlaveTWCs = Mock(return_value=[s])
    master.num_cars_charging_now()
    assert master.vehicleRegistry.get("anon:8244") is not None
    s.reportedAmpsActual = 0.0; s.chargingDroppedBelowThresholdTime = 1  # long ago
    master.num_cars_charging_now()
    assert master.vehicleRegistry.get("anon:8244") is None
```

- [ ] **Step 3: Run to verify failure** — both files → FAIL (`AttributeError: beginPlugSession` / `vehicleRegistry`).

- [ ] **Step 4: Implement** the registry methods, `TWCMaster.__init__` registry creation, and the `recordVehicleVIN`/`num_cars_charging_now` hooks per Interfaces. The confirmation state per point: `{"candidate": vin, "attempts": int, "rejected": bool}` under `_lock`.

- [ ] **Step 5: Run tests** — `python -m pytest tests/unit/test_registry_plug_sessions.py tests/unit/test_twcmaster_vin_confirmation.py tests/unit/test_twcmaster.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
black lib/TWCManager/Vehicle/Registry/ lib/TWCManager/TWCMaster.py
git add lib/TWCManager/Vehicle/Registry lib/TWCManager/TWCMaster.py tests/unit/test_registry_plug_sessions.py tests/unit/test_twcmaster_vin_confirmation.py
git commit -m "Confirm TWC-reported VINs by re-query and track anonymous plug-session vehicles"
```

