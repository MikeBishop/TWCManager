### Task 3: Gen2 TWC provider with per-device ranges and the disruptive stop

`minAmpsTWCSupports` lives on `TWCSlave` (class default 6, `lib/TWCManager/TWCSlave.py:25`); `TWCManager.py:1270-1278` sets it to 5 for a protocol-1 TWC (14-byte linkready) and 6 for protocol 2, and `:1424-1426` sets it to 1 A when all three phases report ≥ 200 V. The reported maximum is `TWCSlave.maxAmps` (80 US / 32 EU from linkready) and the wiring limit is `wiringMaxAmps` (config `wiringMaxAmpsPerTWC`).

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py`.
- Modify: `lib/TWCManager/EVSEInstance/EVSEInstance.py:92-100` (defaults), `lib/TWCManager/EVSEInstance/Gen2TWC.py:108-114` (ranges), new properties; `lib/TWCManager/TWCMaster.py` `__init__` (`providerOrder`, registration, after `self.vehicleRegistry = VehicleRegistry(config)`) and `stopCarsCharging` (`stopRespondingToSlaves`).
- Test: `tests/unit/test_gen2twc_provider.py`.

**Interfaces:**
- Consumes: `Provider`, `ProviderOrder`, capability names; `TWCSlave.minAmpsTWCSupports`, `.maxAmps`, `.wiringMaxAmps`, `.currentVIN`, `.lastVIN`, `.reportedState`, `.reportedAmpsActual`; `VehicleRegistry.get("anon:<id>")`.
- Produces (`EVSEInstance`): `vehicleKey -> Optional[str]` (default `None`: the registry key of the vehicle this endpoint serves), `occupied -> Optional[bool]` (default `None`: `True` a car is connected, `False` none, `None` unknown), `provider: str = ""`, `idleMinimum: bool = False` (`True` when an idle endpoint must be offered its minimum to detect a plug-in; `Gen2TWC` sets it `True`, Gen3 leaves it `False`).
- Produces (`Gen2TWC`):
  - `twcid -> str` (`"%02X%02X"`), `PLUGGED_STATES = (0x01, 0x03, 0x04, 0x05, 0x08, 0x09)`.
  - `minAmps -> float`: config override `master.config.get("controller.Gen2TWCs", {}).get("ranges", {}).get(twcid, {}).get("minAmps")` when a positive number, else `minAmpsTWCSupports`. `maxOfferAmps -> float` (named so because `TWCSlave.maxAmps` is already the linkready value): the override's `maxAmps` key when a positive number, else `min(wiringMaxAmps, self.maxAmps or wiringMaxAmps)`. `minPower`/`maxPower` use these (today `minAmpsTWCSupports` / `wiringMaxAmps`).
  - `vehicleKey`: `currentVIN.upper()` when set; else the anonymous plug-session key `"anon:" + twcid` when `master.vehicleRegistry.get(...)` holds it; else `lastVIN.upper()` while `reportedState in PLUGGED_STATES` (the car that was last confirmed here has shown no unplug evidence; ledger I5: not the charging session); else `None`.
  - `occupied`: `True` when `currentVIN` or `reportedAmpsActual >= 1.0` or `reportedState in PLUGGED_STATES`; otherwise `None` (a Gen2 reports 00 for a sleeping plugged car, so 00 is not "empty").
  - `provider = "Gen2TWC"`, `idleMinimum = True`.
- Produces (`Gen2TWCProvider.py`) `class Gen2TWCProvider(Provider):` `name = "Gen2TWC"`, `rank = 0`, `local = True`, `module = None`; `__init__(self, master)`; `declarations()`: `READ_PLUG`, `READ_VIN`, `READ_AMPS` → `Declaration(LOCAL, passive=True)`; `SET_AMPS` → `Declaration(LOCAL)`; `STOP_CHARGING` → `Declaration(DISRUPTIVE)`. `slaveFor(self, vehicle) -> Optional[TWCSlave]` (the slave in `master.getSlaveTWCs()` whose `vehicleKey == vehicle.key`); `stopMode(self) -> int` (`int(settings.get("chargeStopMode", 1))`); `ready(vehicle, cap)`: reads and `SET_AMPS` → `slaveFor` is not None, and for `SET_AMPS` additionally `int(settings.get("chargeRateControl", 1)) != 2` (mode 2 hands the rate to the vehicle); `STOP_CHARGING` → `slaveFor` is not None and `stopMode() in (2, 3)` (off by default; a disruptive stop is only ever selected by `chargeStopMode`). `ampsRange(vehicle)` → `(slave.minAmps, slave.maxOfferAmps)`, except under `chargeRateControl == 3` where the floor is the hard-coded 6 A at which `TWCSlave.send_master_heartbeat` hands the rate to the vehicle (`(6, slave.maxOfferAmps)`): a protocol-1 TWC (`minAmps` 5) or a 3-phase one (`minAmps` 1) would otherwise 'cover' a target the TWC never carries, Fleet would be dropped, and a Fleet-only car would run at the wiring maximum; `setAmps(vin, amps)` → `slave.setTargetPower(slave.convertAmpsToWatts(amps))`, `True` (publishing a target the serial loop sends on the next heartbeat; never reached by `dispatch`, Task 2); `stopCharging(self, vin) -> bool`: mode 2 → `master.stopRespondingToSlaves()`; mode 3 → `master.sendStopCommand(slave.TWCID)`; else `False`. **No Phase 2 caller uses `stopCharging`**: `TWCMaster.stopCarsCharging` is unchanged; the Phase 3 reconciler is the caller.
- Produces (`TWCMaster`): `stopRespondingToSlaves(self) -> None` (under `settingsLock`: `respondToSlaves = 0`, `respondToSlavesExpiry = time.time() + 60`), factored out of `stopCarsCharging`'s mode-2 branch, which now calls it. `__init__`: `self.providerOrder = ProviderOrder(self)` after `self.vehicleRegistry`, then `self.providerOrder.register(Gen2TWCProvider(self))` and `self.vehicleRegistry.useReadOrder(self.providerOrder.orderReadSources)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_gen2twc_provider.py
from unittest.mock import Mock
from TWCManager.TWCMaster import TWCMaster
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Gen2TWCProvider import Gen2TWCProvider
VIN = "5YJ3E1EA1KF000001"
CONFIG = {"config": {"debugOutputToFile": False, "subtractChargerLoad": False, "treatGenerationAsGridDelivery": False,
          "wiringMaxAmpsAllTWCs": 80, "wiringMaxAmpsPerTWC": 32, "maxAmpsAllowedFromGrid": None}}

def make(config=CONFIG):
    m = TWCMaster("AB", config); m.getModuleByName = Mock(return_value=None)
    s = m.newSlave(b"\x82\x44", 80); return m, s          # slaveTWCs is keyed by bytes

def test_master_registers_gen2_provider_and_read_order():
    m, s = make()
    assert [p.name for p in m.providerOrder.providers()] == ["Gen2TWC"]
    assert m.vehicleRegistry._readOrder is not None

def test_ranges_follow_the_device_and_wiring():
    m, s = make(); s.minAmpsTWCSupports = 5
    assert (s.minAmps, s.maxOfferAmps) == (5, 32)
    s.maxAmps = 24; assert s.maxOfferAmps == 24
    m2, s2 = make(dict(CONFIG, **{"controller.Gen2TWCs": {"ranges": {"8244": {"minAmps": 6, "maxAmps": 16}}}}))
    assert (s2.minAmps, s2.maxOfferAmps) == (6, 16) and s2.minPower == 6 * 240

def test_vehicle_key_keeps_last_vin_while_plugged_state():       # Review Focus 5 / ledger I5
    m, s = make(); reg = m.vehicleRegistry
    assert s.vehicleKey is None and s.occupied is None
    s.currentVIN = VIN.lower(); assert s.vehicleKey == VIN and s.occupied is True
    s.currentVIN = ""; s.lastVIN = VIN; s.reportedState = 0x03
    assert s.vehicleKey == VIN and s.occupied is True
    s.reportedState = 0x00; assert s.vehicleKey is None and s.occupied is None
    reg.beginPlugSession("8244"); assert s.vehicleKey == "anon:8244" and s.idleMinimum is True

def test_provider_readiness_and_range_per_vehicle():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t")
    assert p.ready(v, C.SET_AMPS) is False and p.ampsRange(v) is None
    s.currentVIN = VIN
    assert p.ready(v, C.SET_AMPS) and p.ampsRange(v) == (6, 32) and p.covers(v, 6) and not p.covers(v, 4)
    s.minAmpsTWCSupports = 5; assert p.ampsRange(v) == (5, 32) and p.covers(v, 5)
    m.settings["chargeRateControl"] = "3"; assert p.ampsRange(v) == (6, 32) and not p.covers(v, 5)   # mode 3 hands off below 6 A: Fleet stays a candidate
    m.settings["chargeRateControl"] = "2"; assert p.ready(v, C.SET_AMPS) is False
    assert p.ready(v, C.READ_VIN) and p.declarations()[C.READ_VIN].passive

def test_disruptive_stop_declared_very_high_cost_and_off_by_default():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); v = m.vehicleRegistry.getOrCreate(VIN, "t"); s.currentVIN = VIN
    assert p.cost(C.STOP_CHARGING) == C.DISRUPTIVE and p.ready(v, C.STOP_CHARGING) is False
    assert p.stopCharging(VIN) is False
    m.settings["chargeStopMode"] = "2"
    assert p.ready(v, C.STOP_CHARGING) and p.stopCharging(VIN) is True and m.settings["respondToSlaves"] == 0
    m.settings["respondToSlaves"] = 1; m.stopCarsCharging(VIN); assert m.settings["respondToSlaves"] == 0         # same helper
    m.settings["chargeStopMode"] = "3"; m.sendStopCommand = Mock()
    assert p.stopCharging(VIN) is True; m.sendStopCommand.assert_called_once_with(s.TWCID)

def test_set_amps_publishes_a_target_for_the_heartbeat():
    m, s = make(); p = m.providerOrder.provider("Gen2TWC"); s.currentVIN = VIN
    assert p.setAmps(VIN, 16) is True and s._evseTargetAmps == 16
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `Gen2TWCProvider`).

- [ ] **Step 3: Implement** per Interfaces. `TWCMaster` imports `ProviderOrder` and `Gen2TWCProvider` at module top (the Providers package imports nothing from `TWCMaster`).

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_gen2twc_provider.py tests/unit/test_twcmaster.py tests/unit/test_twcslave.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/Providers/ lib/TWCManager/EVSEInstance/ lib/TWCManager/TWCMaster.py
git add lib/TWCManager tests/unit/test_gen2twc_provider.py
git commit -m "Add the Gen2 TWC provider with per-device amps ranges and a very-high-cost disruptive stop"
```

