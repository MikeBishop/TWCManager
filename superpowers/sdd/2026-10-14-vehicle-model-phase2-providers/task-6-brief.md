### Task 6: Owner API and Fleet API as separate providers (closes A24)

The two token slots become two providers over the one `TeslaAPI` module. Reads split by slot so their cost is honest: the Owner slot reads for free; the Fleet slot's `vehicle_data` costs $0.002 and is used only when the Owner slot cannot read (today's `slotFor("read")` rule, so no new paid path). Commands and wake exist only on Fleet. The registry claim splits the same way; the attachment name stays `"TeslaAPI"`.

**Files:**
- Create: `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`.
- Modify: `lib/TWCManager/Vehicle/Registry/Sources.py:72-99` (`TeslaAPIReadSource` per slot); `lib/TWCManager/Vehicle/TeslaAPI.py:144` (two read sources), `:2080-2091` (`_registryVehicle` claims), `:2165` (`is_awake(slot=None)`), `:2190` (`get_car_api(..., slot=None)`), `:2330` (`update_vehicle_data(slot=None)`), new `providers()`.
- Test: `tests/unit/test_teslaapi_providers.py`; update `tests/unit/test_carapivehicle_registry.py:161,172` (`"TeslaAPI" in v.claims` → `"FleetAPI" in v.claims`); its `test_vehicle_joins_registry_and_claims_teslaapi` (list first, then `setTokens(fleet_token())` → managed) keeps passing because the Fleet claim's callable is live. `api_with_registry()` starts with both slots empty.

**Interfaces:**
- Consumes: `TeslaTokenSlot.usable(purpose)`, `.empty()`; `TeslaAPI.ownerSlot`, `.fleetSlot`, `.setChargeRate(charge_rate, vehicle=)`, `.wakeVehicle(vehicle)`, `.getVehicleByVIN(vin)`.
- Produces (`Sources.py`): `TeslaAPIReadSource.__init__(self, carapi, kind: str = "owner")`; `name = "TeslaAPI"` (observation source unchanged), `provider = "OwnerAPI"` or `"FleetAPI"`, `order = 1`; `slot()` → `carapi.ownerSlot`/`fleetSlot`; `canRead(vehicle)`: attachment present and `slot().usable("read")`, and for `"fleet"` additionally `not carapi.ownerSlot.usable("read")`; `fetch` as today but `car.is_awake(slot=self.slot())` / `car.update_vehicle_data(slot=self.slot())`.
- Produces (`TeslaAPI`): `self.ownerReadSource = TeslaAPIReadSource(self, "owner")`, `self.fleetReadSource = TeslaAPIReadSource(self, "fleet")`, both registered; `providers()` → `[OwnerAPIProvider(self), FleetAPIProvider(self)]`; `CarApiVehicle.get_car_api(path, checkReady=True, provesOnline=True, slot=None)` (`slot` overrides `slotFor("read")`), `is_awake(slot=None)`, `update_vehicle_data(slot=None)`; `_registryVehicle` always makes both claims at bind, with live callables: `"OwnerAPI"` (`canCommand=False`, status `"listed"`) and `"FleetAPI"` (`canCommand=lambda: carapi.fleetSlot.usable("command")`, status `"listed"`), so a token pasted or synced after the listing makes the car managed without a re-list (the spec's managed rule is live); the `"TeslaAPI"` claim is no longer made. `apiDebugInterface` is deleted in Task 9.
- Produces (`TeslaAPIProviders.py`):
  - `class OwnerAPIProvider(Provider):` `name = "OwnerAPI"`, `rank = 4`, `local = False`; `__init__(self, carapi)`: `module = carapi`, `readSource = carapi.ownerReadSource`; `declarations()`: `READ_LIST`, `READ_ONLINE`, `READ_CHARGE`, `READ_LOCATION` → `Declaration(CLOUD_FREE)`; `ready(vehicle, cap)` → `carapi.ownerSlot.usable("read")` and `vehicle.attachment("TeslaAPI") is not None`.
  - `class FleetAPIProvider(Provider):` `name = "FleetAPI"`, `rank = 5`, `local = False`; `module = carapi`, `readSource = carapi.fleetReadSource`; `declarations()`: `READ_LIST`, `READ_ONLINE` → `CLOUD_FREE`; `READ_CHARGE`, `READ_LOCATION` → `FLEET_DATA`; `SET_CHARGE_LIMIT`, `START_CHARGING`, `STOP_CHARGING`, `SET_AMPS` → `Declaration(FLEET_COMMAND, RateLimit(50, 60))` (Tesla's published per-vehicle command limit; declared, not enforced until Phase 3 lanes); `WAKE` → `FLEET_WAKE`; `ready(vehicle, cap)`: attachment present and, for reads, `fleetSlot.usable("read") and not ownerSlot.usable("read")`; for commands and wake, `fleetSlot.usable("command")`; `available(capability)`: commands and `WAKE` → `fleetSlot.usable("command")`, reads → `fleetSlot.usable("read")` (the broadcast gate: an Owner-only install never sends a vehicle-less command to TeslaAPI, today's read-only skip); `ampsRange(vehicle)` → `(1, vehicleMaxAmps(vehicle, carapi.master.config["config"]))`; `setAmps(vin, amps)` → `carapi.setChargeRate(int(amps), vehicle=carapi.getVehicleByVIN(vin))` (`False` when the VIN is unknown); `wake(vin)` → `carapi.wakeVehicle(car)` likewise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_teslaapi_providers.py
from unittest.mock import Mock
from TWCManager.Vehicle.Providers import Capability as C
from tests.unit.test_carapivehicle_registry import api_with_registry, VIN
from tests.unit.teslatokens import fleet_token, owner_token

def test_two_providers_with_honest_costs():
    api, reg = api_with_registry(); owner, fleet = api.providers()
    assert (owner.name, owner.rank, fleet.name, fleet.rank, owner.local) == ("OwnerAPI", 4, "FleetAPI", 5, False)
    assert owner.cost(C.READ_CHARGE) == C.CLOUD_FREE and owner.cost(C.SET_AMPS) is None
    assert fleet.cost(C.READ_ONLINE) == C.CLOUD_FREE and fleet.cost(C.READ_CHARGE) == C.FLEET_DATA
    assert fleet.cost(C.SET_AMPS) == C.FLEET_COMMAND and fleet.cost(C.WAKE) == C.FLEET_WAKE
    assert fleet.declarations()[C.SET_AMPS].rateLimit == C.RateLimit(50, 60)
    assert fleet.available(C.SET_AMPS) is False and owner.available(C.READ_CHARGE) is True     # no tokens yet
    assert (owner.readSource.provider, fleet.readSource.provider) == ("OwnerAPI", "FleetAPI")

def test_fleet_reads_only_when_owner_cannot():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); v = reg.get(VIN)
    owner, fleet = api.providers()
    api.storeToken(fleet_token())
    assert fleet.ready(v, C.READ_CHARGE) and fleet.readSource.canRead(v) and not owner.ready(v, C.READ_CHARGE)
    api.storeToken(owner_token())
    assert owner.ready(v, C.READ_CHARGE) and not fleet.ready(v, C.READ_CHARGE) and not fleet.readSource.canRead(v)
    assert fleet.ready(v, C.SET_AMPS) and fleet.ready(v, C.WAKE) and fleet.available(C.WAKE)

def test_claims_are_live_and_follow_the_slots():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); v = reg.get(VIN)   # both slots empty
    assert set(v.claims) == {"OwnerAPI", "FleetAPI"} and v.tier == "observed"
    assert v.claims["OwnerAPI"].status == "listed" and v.claims["OwnerAPI"].commands is False
    api.storeToken(fleet_token()); assert v.tier == "managed"                 # pasted after the listing: no re-list needed
    api.fleetSlot.clear(); assert v.tier == "observed"
    api.storeToken(owner_token()); assert v.tier == "observed"

def test_fleet_commands_resolve_the_car_by_vin():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); car = api.getCarApiVehicles()[0]
    owner, fleet = api.providers(); api.setChargeRate = Mock(return_value=True); api.wakeVehicle = Mock(return_value=True)
    assert fleet.setAmps(VIN, 10) is True; api.setChargeRate.assert_called_once_with(10, vehicle=car)
    assert fleet.wake(VIN) is True; api.wakeVehicle.assert_called_once_with(car)
    assert fleet.setAmps("5YJ3E1EA1KF000009", 10) is False

def test_read_source_passes_its_slot_to_the_car():
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); car = api.getCarApiVehicles()[0]
    api.storeToken(owner_token()); v = reg.get(VIN); car.statusDeferral = 0
    car.is_awake = Mock(return_value=True); car.update_vehicle_data = Mock(return_value=True)
    assert api.ownerReadSource.fetch(v, "chargeLimit", False) == {}
    car.is_awake.assert_called_once_with(slot=api.ownerSlot); car.update_vehicle_data.assert_called_once_with(slot=api.ownerSlot)
```
(`owner_token` exists in `tests/unit/teslatokens.py` beside `fleet_token`; if it is named differently there, use that name.)

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: providers`).

- [ ] **Step 3: Implement** per Interfaces; update the two `test_carapivehicle_registry.py` assertions.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_teslaapi_providers.py tests/unit/test_carapivehicle_registry.py tests/unit/test_reads_no_wake.py tests/unit/test_teslaapi_readonly_gate.py tests/unit/test_teslaapi_owner_read.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Split the Tesla API into Owner and Fleet providers with per-slot read sources and claims"
```

