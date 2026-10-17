### Task 7: Wall Connector VIN from the energy site (G7–G11)

The Fleet API's `GET /api/1/energy_sites/{id}/live_status` is **free** (user's price list) and returns `wall_connectors: [{din, vin?, wall_connector_state, wall_connector_fault_state, wall_connector_power, ocpp_status}]` with `vin` present while a car is connected (source: the tesla-fleet-api npm types; **unverified on hardware**). Energy sites come from `GET /api/1/products` (entries with `energy_site_id`, as `EMS/TeslaPowerwall2.py:257-292` already reads them); the token needs the `energy_device_data` scope (`TeslaTokenSlot.SCOPES["energy"]`); whether the Owner API serves the same path is unconfirmed, so the Owner slot is tried first and a refusal falls to Fleet. The local Gen3 `/api/1/version` gives `part_number` and `serial_number`; the DIN is assumed to be `<part_number>--<serial_number>` (unconfirmed; overridable). Gen2 TWCs never use this path (G11): their RS-485 VIN stays the source, and with no local Gen3 units nothing is queried. Unit tests only (G6).

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/WallConnectorVins.py`.
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`energySites`, `wallConnectorVins`, refusal state), `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py` (declaration, readiness, `wallConnectorVins()`), `lib/TWCManager/EVSEInstance/Gen3TWC.py` (`din`, `refreshVersion`, `cloudVin`), `lib/TWCManager/EVSEController/Gen3TWCs.py` (`noteVitals` extended with the VIN reader), `docs/modules/Controller_Gen3TWCs.md` (the `din` device key and the cloud-VIN behaviour).
- Test: `tests/unit/test_wall_connector_vins.py`.

**Interfaces:**
- Consumes: `TeslaAPI.slotFor("energy")`, `TeslaTokenSlot.usable("energy")`, `.reportScopeRefused("energy", refused=True)`, `.changes`, `.baseURL`; `ProviderOrder.candidates`; `VehicleRegistry.observeTwcVin` (an unknown VIN is `pending` on the first report and confirmed by the next one, exactly as a Gen2 TWC VIN is by its re-query; a known VIN confirms at once).
- Produces (`TeslaAPI`): `ENERGY_SITES_TTL = 3600`; `energySites(slot=None) -> List[dict]` (`/products` entries with `energy_site_id`, via `slotFor("energy")` unless given; cached per slot kind for an hour; `[]` on failure, never raises); `wallConnectorVins(slot) -> Optional[Dict[str, str]]` (`{din: vin}` over every site's `live_status.wall_connectors` with a `vin`; sites whose `live_status` carries no `wall_connectors` key are dropped from later polls; `None` on a transport error; a 401/403 → `slot.reportScopeRefused("energy", refused=True)`, `self._wallConnectorsRefused[slot.kind] = slot.changes`, one INFO `Wall Connector VINs: <slot kind> token refused energy data; not asking again until the token changes`, returns `None`); `wallConnectorVinsReady(slot) -> bool` → slot `usable("energy")`, `_wallConnectorsRefused.get(slot.kind) != slot.changes`, and the slot's sites are not *known* to be empty (`_energySitesEmpty.get(slot.kind) is not True`) — cache reads only, no I/O (Task 1's `ready` contract): products discovery happens inside `wallConnectorVins()` on the background thread, which is the only caller of `energySites()` and sets `_energySitesEmpty[slot.kind]` from its result. No call here ever wakes a car or requests `vehicle_data` (G8).
- Produces (`TeslaAPIProviders.py`): both providers declare `READ_WALL_CONNECTOR_VINS → Declaration(CLOUD_FREE, RateLimit(2, 60))` (one edge query plus one poll per minute, G9); `ready(vehicle, READ_WALL_CONNECTOR_VINS)` (`vehicle` may be `None`): Owner → `carapi.wallConnectorVinsReady(ownerSlot)`; Fleet → `carapi.wallConnectorVinsReady(fleetSlot) and not carapi.wallConnectorVinsReady(ownerSlot)` (the read-slot rule; free either way); `wallConnectorVins()` → `carapi.wallConnectorVins(<its slot>)`.
- Produces (`WallConnectorVins.py`) `class WallConnectorVinReader:` `POLL_SECONDS = 60.0`; `__init__(self, master, order, clock=time.time)` (`self.clock` is the only clock it reads, for `lastQuery` and the rate window alike); `due(self, units) -> bool`: some unit has `occupied is True` and an anonymous `vehicleKey`, and (a connect edge was flagged by `noteConnect()` or `clock() - lastQuery >= POLL_SECONDS`); `query(self, units) -> Dict[str, str]`: for the first provider in `order.candidates(None, READ_WALL_CONNECTOR_VINS)` whose `wallConnectorVins()` is not `None`, honouring its declared `RateLimit` (skip when the limit would be exceeded), return the map (`{}` otherwise); `match(self, units, vins) -> Dict[str, str]` (G10): `unit.din in vins` → that VIN; a unit whose `din` is `None` (no override, version unknown or without a part number) takes the single cloud entry when exactly one unit is local and `vins` has exactly one entry; a known DIN that matches nothing is evidence of a different connector and is skipped; otherwise one INFO `Wall Connector VINs: no DIN match for <ID> (<n> cloud connectors)` and nothing. `apply(self, units)`: `if due: vins = query(); for unit, vin in match().items(): unit.cloudVin = vin; unit._correlate()`; a unit whose `vehicleKey` is a VIN is skipped (polling stops once the session has a VIN, G9).
- Produces (`Gen3TWC`): `_version: Optional[dict] = None` (the `/api/1/version` cache; `{}` once fetched without a part number); `din -> Optional[str]` (config `devices[].din`, else `"<part_number>--<serial_number>"` from `_version`, else `None`); `refreshVersion() -> bool` (one `GET /api/1/version` into `_version`, background thread, retried on the next refresh until it succeeds); `cloudVin` cleared on the disconnect edge.
- Produces (`Gen3TWCs`): `self.vinReader = WallConnectorVinReader(master, master.providerOrder)`; `noteVitals(unit, rising)` (Task 4) additionally calls `unit.refreshVersion()` while `unit._version is None`, `vinReader.noteConnect()` when `rising`, then `vinReader.apply(self.devices())` — so a unit-level `refreshVitals()` (what the tests drive) reaches the reader. Products discovery runs on the first query and then at most hourly (the `TeslaAPI` cache). Nothing here runs on the serial thread or under a lock.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_wall_connector_vins.py
import re, threading
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Providers.Order import ProviderOrder
from TWCManager.Vehicle.Providers.WallConnectorVins import WallConnectorVinReader
from tests.unit.test_carapivehicle_registry import VIN
from tests.unit.test_gen3twc_provider import Clock, make as make_gen3, vitals
from tests.unit.teslatokens import new_api, owner_token
DIN = "1457768-02-G--TG123"
PRODUCTS = {"response": [{"energy_site_id": 7, "site_name": "Home"}]}
def live(vin=VIN, din=DIN): return {"response": {"wall_connectors": [{"din": din, "vin": vin, "wall_connector_state": 2}]}}

def setup(requests_mock, status=200, vin=VIN, din=DIN):
    m, ctl, p = make_gen3(); m.config["vehicle"] = {"teslaAPI": {"enabled": True}}; m.tokenSyncEnabled.return_value = False
    m.modules = {}; m.settings = {}; m.settingsLock = threading.RLock(); m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    api = new_api(master=m); api.carApiVehicles = []; api.storeToken(owner_token()); reg = m.vehicleRegistry
    requests_mock.get(re.compile(r".*/api/1/products$"), json=PRODUCTS)
    requests_mock.get(re.compile(r".*/energy_sites/7/live_status$"), status_code=status, json=live(vin, din) if status == 200 else {})
    m.providerOrder = ProviderOrder(m); [m.providerOrder.register(x) for x in api.providers()]
    ctl.vinReader = WallConnectorVinReader(m, m.providerOrder, clock=Clock()); (u,) = ctl.devices(); u.device_cfg["din"] = din
    return api, reg, ctl, u

def liveCalls(requests_mock): return [r for r in requests_mock.request_history if "live_status" in r.url]

def test_vin_from_live_status_confirms_the_session(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    vitals(u, True)                                  # connect edge: pending (first report of an unknown VIN)
    assert reg.get(VIN) is None and len(liveCalls(requests_mock)) == 1
    ctl.vinReader.clock.t += 60; vitals(u, True)     # next poll confirms, as a Gen2 re-query would
    assert u.vehicleKey == VIN and reg.get(VIN).value("twcVin") == u.ID and reg.get("anon:" + u.ID) is None

def test_known_vin_confirms_at_once_and_polling_stops(requests_mock):
    api, reg, ctl, u = setup(requests_mock); reg.getOrCreate(VIN, "TeslaMateVehicle")
    vitals(u, True); assert u.vehicleKey == VIN
    ctl.vinReader.clock.t += 600; vitals(u, True); vitals(u, True)
    assert len(liveCalls(requests_mock)) == 1

def test_din_mismatch_falls_to_single_candidate(requests_mock):
    api, reg, ctl, u = setup(requests_mock, din="other--din"); u.device_cfg["din"] = DIN
    car = reg.getOrCreate(VIN, "t"); car.observe("pluggedIn", True, "TeslaMateVehicle")
    vitals(u, True)
    assert u.cloudVin is None and u.vehicleKey == VIN            # a known, mismatching DIN: G3 did it, not the cloud

def test_single_local_single_cloud_matches_without_din(requests_mock):
    api, reg, ctl, u = setup(requests_mock, din="whatever"); u.device_cfg.pop("din", None); u._version = {}
    vitals(u, True); ctl.vinReader.clock.t += 60; vitals(u, True)
    assert u.cloudVin == VIN

def test_403_marks_the_capability_not_ready_once(requests_mock):
    api, reg, ctl, u = setup(requests_mock, status=403)
    vitals(u, True); ctl.vinReader.clock.t += 60; vitals(u, True)
    assert len(liveCalls(requests_mock)) == 1
    assert not api.providers()[0].ready(None, C.READ_WALL_CONNECTOR_VINS)
    api.storeToken(owner_token()); assert api.providers()[0].ready(None, C.READ_WALL_CONNECTOR_VINS)   # token change re-arms

def test_no_query_without_an_occupied_gen3_and_no_vehicle_calls(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    ctl.vinReader.apply(ctl.devices()); assert liveCalls(requests_mock) == []
    vitals(u, True)
    assert all(not re.search(r"wake_up|vehicle_data", r.url) for r in requests_mock.request_history)

def test_rate_limit_is_respected(requests_mock):
    api, reg, ctl, u = setup(requests_mock)
    for _ in range(4): ctl.vinReader.noteConnect(); ctl.vinReader.apply(ctl.devices()); vitals(u, True)   # one clock, no time passes
    assert len(liveCalls(requests_mock)) <= 2
```
(`api.storeToken` bumps `slot.changes`; if `tests.unit.teslatokens.owner_token` lacks the energy scope, pass `scp=` with `energy_device_data` as `fleet_token` allows.)

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `WallConnectorVins`).

- [ ] **Step 3: Implement** per Interfaces; document the `din` key and the cloud-VIN order (cloud VIN, single candidate, anonymous) in `docs/modules/Controller_Gen3TWCs.md`, marked unverified on hardware.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_wall_connector_vins.py tests/unit/test_gen3twc_provider.py tests/unit/test_teslaapi_providers.py tests/unit/test_teslapowerwall2_ems.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle lib/TWCManager/EVSEInstance/Gen3TWC.py lib/TWCManager/EVSEController/Gen3TWCs.py
git add lib/TWCManager tests/unit/test_wall_connector_vins.py docs/modules/Controller_Gen3TWCs.md
git commit -m "Identify the car on a Gen3 TWC from the energy site's free live_status before falling back to a single candidate"
```

