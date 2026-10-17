### Task 5: Cloud provider command methods return outcomes (Fleet, Owner, HomeAssistant); refused retires the slot (closes A21, #689)

Today `CarApiVehicle.apply_charge_limit` posts `set_charge_limit` three times on `could_not_wake_buses`, `setChargeRate` returns the raw response dict (a 401 body is truthy), `car_api_charge` and `wakeVehicle` treat 401 by refreshing once; `slotRequestFailed` clears a 401 slot and pauses a 403/410/412 slot for reads only; `TeslaTokenSlot.reportScopeRefused` only logs, so `usable("command")` stays True after a 403. `car_api_available` checks `vehicle.ready()` (the free `vehicles/{vin}` online state) before every wake; the wake hold lives there too (`firstWakeAttemptTime`, `delayNextWakeAttempt` = 30 min after a failed wake, the hour-long "please report" notice, `wakeDelayMins` before the first wake after a charge need). HA's `_call_service` returns a bool, swallows `Timeout`/`HTTPError`, logs `response.text[:200]`, and `car_api_charge` gates all cars on one 10 s timer (ledger m-2).

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (new `command`, `wakeDue`, `wakeOutcome`, `commandRefused`, `now`; `CarApiVehicle.is_awake(slot=None, now=None)`), `lib/TWCManager/Vehicle/TeslaTokenSlot.py` (412 latch, refused purposes), `lib/TWCManager/Vehicle/HomeAssistant.py` (new `_post_service`), `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `tests/unit/test_teslaapi_providers.py` (`test_fleet_commands_resolve_the_car_by_vin`), `tests/unit/test_provider_registration.py` (`test_home_assistant_provider_follows_entities`) — outcomes.
- Test: `tests/unit/test_provider_outcomes_cloud.py`.

**Interfaces:**
- Produces (`TeslaTokenSlot`): `pause(self, now=None, latch=False) -> None`: `latch=True` sets `pausedUntil = float("inf")` so the slot is not retried for reads until `setTokens`/`clear` bump `changes` (ledger "stop retrying an Owner token Tesla keeps refusing (412)"); `status()` reports `"paused": True` for it. `refusedPurposes: Set[str]` recorded by `reportScopeRefused(purpose, refused=True)` and cleared by `setTokens`/`clear`; `usable(purpose)` is `False` for a refused purpose. `TeslaAPI.slotRequestFailed` passes `latch=True` for 412 ("only available on fleetapi": a token kind Tesla will keep refusing), plain `pause()` for 403/410 as today.
- Produces (`TeslaAPI`): `command(self, vehicle, name: str, body: Optional[dict] = None) -> Outcome`: one `requests.post(slot.baseURL + "/" + VIN + "/command/" + name, json=body, timeout=10)` on `slotFor("command")` (`None` → `Outcome(REFUSED, "no command token")`); HTTP 200 with `response.result` True → `DONE`; `result` False with reason in `("already_set", "charging", "is_charging", "not_charging", "complete", "disconnected", "requested")` → `Outcome(SATISFIED, reason)`; reason `could_not_wake_buses`, `vehicle_unavailable`, or HTTP 408 → `Outcome(UNREACHABLE, reason or "408")`; HTTP 401 with "expired" and a refreshable slot → `refreshSlot` once and retry once, otherwise `commandRefused(slot, 401)` → `REFUSED`; 403 → `slot.reportScopeRefused("command", refused=True)` → `REFUSED`; 412 → `slot.pause(latch=True)` → `REFUSED`; 429 → `updateCarApiLastErrorTime(vehicle)` → `Outcome(ERROR, "429")`; other statuses, `RequestException`, JSON errors → `ERROR` with the status or type name. `commandRefused(slot, code)`: 401 → `slot.clear()` + `saveSettings` + one ERROR log (`Tesla Fleet API token was rejected (HTTP 401); removing it.`). `getCarApiRetryRemaining(vehicle)` holds → `Outcome(UNREACHABLE, "backoff")` before any request. `TeslaAPI.now = time.time` (an instance attribute: the module's one clock hook, which a test replaces instead of patching the process-wide `time.time`; `wakeDue`, `wakeOutcome` and `is_awake` default to it). `wakeDue(self, vehicle, now=None) -> bool` (`now` defaults to `self.now()`; every comparison inside uses it, so a caller may drive it with a test clock): today's hold — `False` while `now - vehicle.lastAPIAccessTime <= vehicle.delayNextWakeAttempt`, or while `wakeDelayMins * 60` has not passed since `vehicle.firstChargeNeededTime` (set on the first `wakeOutcome` call for a need), or during `getCarApiRetryRemaining`. `CarApiVehicle.is_awake(self, slot=None, now=None)` (signature change; its existing callers pass nothing): its 120 s cache (`lastVehicleAwakeTime`) is measured against `now` (default `self.carapi.now()`), so a caller on a test clock drives it. `wakeOutcome(self, vehicle, now=None) -> Outcome`: **free online check first** — `vehicle.is_awake(slot=self.slotFor("command"), now=now)` (`GET vehicles/{vin}`, free; cached 120 s) → online → `Outcome(SATISFIED, "online")` with no `wake_up` posted and the counters reset; then not due → `Outcome(UNREACHABLE, "wake held")`; then posts `wake_up` (timeout 10); state `online` → `DONE` and the counters reset as `car_api_available` resets them, plus the 5 s settle sleep; `asleep`/`waking`/`offline` → `delayNextWakeAttempt = 1800`, `firstWakeAttemptTime` set, → `UNREACHABLE`; the hour-long failure INFO stays; 401/403/412/429 as for `command`.
- Produces (`FleetAPIProvider`): `_car(vin)` → `carapi.getVehicleByVIN(vin)` (`None` → `Outcome(UNSUPPORTED, "not listed")`); `clock = time.time` (an attribute a test may replace; passed as `now=` to `wakeOutcome`/`wakeDue`); `setChargeLimit(vin, limit)` → `command(car, "set_charge_limit", {"percent": int(limit)})`; `startCharging` → `"charge_start"`, except that a `disconnected` reason on a start is `Outcome(UNSUPPORTED, "disconnected")` (nothing to start; the lane must not record a start); `stopCharging` → `"charge_stop"`; `setAmps(vin, amps)` → `"set_charging_amps"` `{"charging_amps": int(amps)}`, and for `amps < 5` a second identical post 5 s later (TeslaPy #42; both must be `DONE`/`SATISFIED`); `wake(vin)` → `wakeOutcome(car, now=self.clock())`. `OwnerAPIProvider` declares no commands; its inherited defaults return `UNSUPPORTED`.
- Produces (`HomeAssistant`): `_post_service(self, domain, service, data) -> Outcome` (the one place the REST call is made, under `_rest_lock`): `200` → `DONE`; `Timeout` → `UNREACHABLE`; `HTTPError` 401/403 → `Outcome(REFUSED, str(status))` (logged once at ERROR: `Home Assistant refused a service call (HTTP <code>); check the long-lived token`); other `HTTPError` → `ERROR` with the status; other exceptions → `ERROR` by type name. Nothing here logs `response.text` (today's `[:200]` body log goes). `_call_service(domain, service, data) -> bool` becomes `self._post_service(...).kind == DONE` for its remaining legacy callers.
- Produces (`HomeAssistantProvider`): `_entity(vin, kind) -> Tuple[Optional[HaVehicle], Optional[str]]`; `setChargeLimit(vin, limit)` → `number.set_value` on `charge_limit_number`; `startCharging`/`stopCharging` → `switch.turn_on`/`turn_off` on `charge_switch`; `setAmps(vin, amps)` → `number.set_value` on `charge_current_number` with `amps` clamped to `[1, 32]` as today — all through `ha._post_service`; a missing entity → `Outcome(UNSUPPORTED, "no <kind> entity")`; `declarations()` add `RateLimit(1, 10)` on `START_CHARGING`/`STOP_CHARGING` (today's 10 s gate, now per car through the lane; closes ledger m-2); no `wake`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_provider_outcomes_cloud.py
import re
from unittest.mock import Mock
import requests_mock as rm
from TWCManager.Vehicle.Providers import Capability as C
from TWCManager.Vehicle.Reconcile import Outcome as O
from tests.unit.test_carapivehicle_registry import api_with_registry, VIN
from tests.unit.teslatokens import fleet_token, owner_token
from tests.unit.test_homeassistant_registry import make_ha

def fleet(requests_mock, status=200, result=True, reason=""):
    api, reg = api_with_registry(); api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"}); api.storeToken(fleet_token())
    requests_mock.post(re.compile(r".*/command/.*"), status_code=status, json={"response": {"result": result, "reason": reason}})
    return api, reg, api.providers()[1]

def calls(requests_mock, part): return [r for r in requests_mock.request_history if part in r.url]

def test_fleet_command_outcomes_and_one_request_each(requests_mock):
    api, reg, p = fleet(requests_mock); assert p.setChargeLimit(VIN, 80).kind == O.DONE and len(calls(requests_mock, "set_charge_limit")) == 1
    assert calls(requests_mock, "set_charge_limit")[0].json() == {"percent": 80}
    api, reg, p = fleet(requests_mock, result=False, reason="already_set"); assert p.setChargeLimit(VIN, 80) == O.Outcome(O.SATISFIED, "already_set")
    api, reg, p = fleet(requests_mock, result=False, reason="could_not_wake_buses"); assert p.startCharging(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "charge_start")) == 1
    api, reg, p = fleet(requests_mock, status=500); assert p.stopCharging(VIN) == O.Outcome(O.ERROR, "500")
    assert p.setChargeLimit("5YJ3E1EA1KF000009", 80) == O.Outcome(O.UNSUPPORTED, "not listed")

def test_fleet_401_retires_the_slot_and_403_refuses_the_scope(requests_mock):
    api, reg, p = fleet(requests_mock, status=401); assert p.setAmps(VIN, 10).kind == O.REFUSED
    assert api.fleetSlot.empty() and p.ready(reg.get(VIN), C.SET_AMPS) is False and len(calls(requests_mock, "set_charging_amps")) == 1
    api, reg, p = fleet(requests_mock, status=403); assert p.setAmps(VIN, 10).kind == O.REFUSED and not api.fleetSlot.usable("command") and api.fleetSlot.usable("read")
    assert p.ready(reg.get(VIN), C.SET_AMPS) is False; api.storeToken(fleet_token()); assert api.fleetSlot.usable("command")     # a new token clears the refusal

def test_start_on_a_disconnected_car_is_unsupported(requests_mock):
    api, reg, p = fleet(requests_mock, result=False, reason="disconnected"); assert p.startCharging(VIN) == O.Outcome(O.UNSUPPORTED, "disconnected")

def test_owner_412_is_latched_until_the_token_changes(requests_mock):
    api, reg = api_with_registry(); api.storeToken(owner_token())
    requests_mock.get(re.compile(r".*/api/1/(vehicles|products).*"), status_code=412, json={})
    assert api.loadVehicleList() is False and api.ownerSlot.usable("read") is False
    api.ownerSlot.pausedUntil -= 7200; assert api.ownerSlot.usable("read") is False             # an hour later: still paused
    api.storeToken(owner_token()); assert api.ownerSlot.usable("read") is True

def test_low_amps_are_sent_twice_and_counted(requests_mock, monkeypatch):
    import TWCManager.Vehicle.TeslaAPI as T
    api, reg, p = fleet(requests_mock); api.master.config = {"config": {}}; monkeypatch.setattr(T.time, "sleep", Mock())
    assert p.setAmps(VIN, 4).kind == O.DONE and len(calls(requests_mock, "set_charging_amps")) == 2
    assert p.setAmps(VIN, 10).kind == O.DONE and len(calls(requests_mock, "set_charging_amps")) == 3

def test_wake_checks_the_free_online_state_first_and_holds_between_wakes(requests_mock, monkeypatch):
    import TWCManager.Vehicle.TeslaAPI as T
    from tests.unit.reconcile_helpers import Clock
    clk = Clock(1000.0); api, reg, p = fleet(requests_mock); car = api.getCarApiVehicles()[0]; p.clock = clk
    monkeypatch.setattr(T.time, "sleep", Mock()); api.now = clk                                                    # TeslaAPI's own clock hook follows the test clock; time.time itself is untouched
    requests_mock.get(re.compile(r".*/api/1/vehicles/%s$" % VIN), json={"response": {"state": "online"}})
    assert p.wake(VIN) == O.Outcome(O.SATISFIED, "online") and calls(requests_mock, "wake_up") == [] and len(calls(requests_mock, "/vehicles/" + VIN)) == 1   # free check, no $0.02
    assert p.wake(VIN) == O.Outcome(O.SATISFIED, "online") and len(calls(requests_mock, "/vehicles/" + VIN)) == 1   # 120 s cache: not even the free call
    clk.t += 121; requests_mock.get(re.compile(r".*/api/1/vehicles/%s$" % VIN), json={"response": {"state": "asleep"}})
    requests_mock.post(re.compile(r".*/wake_up$"), json={"response": {"state": "asleep"}})
    car.delayNextWakeAttempt = 1800; car.lastAPIAccessTime = clk()
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake held") and calls(requests_mock, "wake_up") == [] and len(calls(requests_mock, "/vehicles/" + VIN)) == 2
    car.delayNextWakeAttempt = 0; api.wakeDelayMins = 0
    assert p.wake(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "wake_up")) == 1 and car.delayNextWakeAttempt == 1800
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake held") and len(calls(requests_mock, "wake_up")) == 1   # not twice
    clk.t += 1801; assert p.wake(VIN).kind == O.UNREACHABLE and len(calls(requests_mock, "wake_up")) == 2        # the hold expired on the same clock

def test_ha_outcomes_and_per_car_rate_limit():
    ha, reg = make_ha(); (p,) = ha.providers(); v = reg.getOrCreate(VIN, "t")
    hv = Mock(entity_ids={"charge_switch": "switch.c", "charge_limit_number": None, "charge_current_number": "number.a"}, has_charge_switch=True, has_charge_limit_number=False, has_charge_current_number=True)
    v.attach("HomeAssistant", hv); ha._post_service = Mock(return_value=O.Outcome(O.DONE))
    assert p.stopCharging(VIN).kind == O.DONE and ha._post_service.call_args.args == ("switch", "turn_off", {"entity_id": "switch.c"})
    assert p.setChargeLimit(VIN, 80) == O.Outcome(O.UNSUPPORTED, "no charge_limit_number entity")
    assert p.setAmps(VIN, 40).kind == O.DONE and ha._post_service.call_args.args[2]["value"] == 32.0
    assert p.declarations()[C.STOP_CHARGING].rateLimit == C.RateLimit(1, 10) and not p.declares(C.WAKE)
    ha._post_service = ha.__class__._post_service.__get__(ha); import requests
    ha._session.post = Mock(side_effect=requests.exceptions.Timeout()); assert p.startCharging(VIN).kind == O.UNREACHABLE
    resp = Mock(status_code=403, text="secret-token"); ha._session.post = Mock(return_value=resp); resp.raise_for_status = Mock(side_effect=requests.exceptions.HTTPError(response=resp))
    assert p.startCharging(VIN) == O.Outcome(O.REFUSED, "403") and ha._call_service("switch", "turn_on", {}) is False
```
(`test_homeassistant_registry.make_ha` gives a real `HomeAssistant` with a mock session; if `_session` is named differently there, use that name. `fleet()` resets `requests_mock` matchers per call; keep `api.master.config["config"]` present as `api_with_registry` builds it.)

- [ ] **Step 2: Run to verify failure** → FAIL (`AttributeError: 'TeslaAPI' object has no attribute 'command'`).

- [ ] **Step 3: Implement** per Interfaces. The legacy methods stay untouched until Task 10; `command` is new code beside them.

- [ ] **Step 4: Run tests** — `$PYTEST tests/unit/test_provider_outcomes_cloud.py tests/unit/test_teslaapi_providers.py tests/unit/test_provider_registration.py tests/unit/test_teslaapi_token_slots.py tests/unit/test_teslatokenslot.py tests/unit/test_teslaapi_request_errors.py tests/unit/test_homeassistant_registry.py -q --timeout=60 -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit**

```bash
black lib/TWCManager/Vehicle/
git add lib/TWCManager/Vehicle tests/unit
git commit -m "Give the cloud providers command methods with classified outcomes; a refused Fleet command retires its slot"
```

