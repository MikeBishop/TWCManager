# restack3 review package: phases 3, 3.5, 4 + fix/disabled-teslable

## fix/disabled-teslable vs main
09c60309 Keep a disabled TeslaBLE module out of the provider order
 lib/TWCManager/Vehicle/TeslaBLE.py       |  8 ++++++++
 tests/unit/test_provider_registration.py | 13 +++++++++++++
 2 files changed, 21 insertions(+)

## phase 3: range-diff (pushed fe9eca64 on 26fc3f3d) vs (new restack3/phase3 on origin/main)
 1:  24562abe !  1:  060fe922 Add the desired-state store and VIN-keyed held charge limits
    @@ Commit message
     
      ## CHANGELOG.md ##
     @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
    - * Architecture
    -     * Remove Tesla Owner API login flow; FleetAPI, TeslaMate token sync, manual token entry and BLE remain the supported paths, with Owner API tokens used for reads, and for commands only to vehicles Tesla reports with `command_signing: off`
    -     * (@MikeBishop) - Saved Tesla tokens migrate to separate Owner and Fleet settings on first start; downgrading afterwards loses the Owner API token (#692)
    +     * (@MikeBishop) - Charging endpoints (a TWC, or a car whose amps BLE, Fleet or HomeAssistant can set) are grouped into charging points by the car they serve, so a car that stops charging on its TWC gets no second power share or Fleet charge-rate commands. The distributor allocates per point, an idle TWC counts nothing against the budget, and a car's amps are queued to the vehicle worker instead of being sent to the Fleet API from the RS-485 loop
    +     * (@MikeBishop) - The power distributor never has the Fleet API set a car's amps where a TWC or BLE can (Charge Rate Control modes 2 and 3 still may). A BLE-paired car on a mobile connector gets its rate over BLE only, with no Fleet fallback. Home Assistant can now set a car's amps; it is treated as billed and tried only after the Fleet API
    +     * (@MikeBishop) - Settings page labels say "vehicle command (BLE or API)" and "local"/"cloud" where they said "Tesla API"; the stored values are unchanged
     +    * (@MikeBishop) - Held charge limits (the limit a car had before TWCManager changed it) migrate from settings `chargeLimits` to `heldLimits`, keyed by VIN, on first start; downgrading afterwards loses them, and upgrading again after a downgrade uses the held limits saved before the downgrade (the older release's `chargeLimits` is kept but ignored, with a warning)
    -     * (@MikeBishop) - TWC abstraction layer with EVSEController/EVSEInstance interface (ported from #483)
    -     * (@ngardiner) - Gen3 TWC support via Neurio Modbus emulation
    -     * (@MikeBishop) - Run vehicle commands on a dedicated worker thread and serialize tesla-control calls, so BLE retries no longer stall the RS485 loop (#668)
    + * Bugfixes
    +     * (@MikeBishop) - When TWCManager shares power with Tesla API cars, the distributor gives an idle TWC a target of 0 and counts nothing against the budget. On the wire the TWC is offered 0 when no car is charging (a Gen2 treats 0 as its hardware minimum), and its hardware minimum (usually 6 A) when another car is charging and there is at least minAmpsPerTWC of power per car, so it still sees a car plug in. Brief overshoot is fine: the configured limit is already the 80% continuous rating and the next cycle rebalances
    +     * (@MikeBishop) - A car read while its TWC held the 6 A pilot it keeps for a sleeping car is no longer capped at 6 A (or offered nothing, when the TWC measured above 240 V), which left it uncharged and unwoken overnight. A car's limit is its own maximum charge current (from BLE, the Tesla API or TeslaMate, else `wiringMaxAmpsPerTWC`), never the pilot it last saw, and a raise to the wiring maximum still reaches a car whose own maximum is lower. A plugged-in car whose charging point refuses power that is there is logged at INFO (`<point>: <VIN> is plugged in, but its limits leave it none of <n> W`), at most hourly
     
      ## lib/TWCManager/Control/HTTPControl.py ##
     @@ lib/TWCManager/Control/HTTPControl.py: def ageText(seconds):
 2:  b83999a1 !  2:  7719490b Run vehicle commands as classified provider outcomes on BLE and cloud workers
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +        while True:
     +            # Built per attempt, so the retry after a refresh sends the new token
     +            url = slot.baseURL + "/" + str(vehicle.VIN) + "/" + path
    ++            sent = slot.accessToken
     +            headers = {
     +                "accept": "application/json",
    -+                "Authorization": "Bearer " + slot.accessToken,
    ++                "Authorization": "Bearer " + sent,
     +            }
     +            try:
     +                req = requests.post(
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +                return Outcome(ERROR, type(e).__name__), None
     +            code = req.status_code
     +            if code == 401:
    -+                if (
    -+                    not refreshed
    -+                    and "expired" in req.text
    -+                    and slot.source != "synced"
    -+                    and slot.refreshToken
    -+                ):
    ++                # Under the slot's lock, so no other thread refreshes, pastes
    ++                # or clears the token between this check and what follows
    ++                with slot.lock:
    ++                    outcome = self._commandUnauthorized(slot, sent, req, refreshed)
    ++                if outcome is None:
     +                    refreshed = True
    -+                    result = self.refreshSlot(slot)
    -+                    if result == "success":
    -+                        continue
    -+                    if result == "unreachable":
    -+                        return Outcome(UNREACHABLE, "token refresh"), None
    -+                    if not slot.empty():
    -+                        # Expired and the refresh failed (a 5xx, no client
    -+                        # ID): the tokens are kept, as refresh() alone
    -+                        # clears on a 401, but no later round pays for
    -+                        # another 401. A successful refresh (setTokens)
    -+                        # lifts the refusal.
    -+                        logger.error(
    -+                            "Tesla %s API token has expired and could not be "
    -+                            "refreshed (%s); not sending commands with it until "
    -+                            "it is refreshed or replaced."
    -+                            % (slot.kind.capitalize(), result)
    -+                        )
    -+                        slot.refuse("command")
    -+                    return Outcome(REFUSED, "401"), None
    -+                self.commandRefused(slot, 401)
    -+                return Outcome(REFUSED, "401"), None
    ++                    continue
    ++                return outcome, None
     +            if code == 403:
     +                slot.reportScopeRefused("command", refused=True)
     +                return Outcome(REFUSED, "403"), None
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +                return Outcome(ERROR, type(e).__name__), None
     +            return None, response
     +
    ++    def _commandUnauthorized(self, slot, sent, req, refreshed):
    ++        # A 401 on a command sent with the access token sent. None: send once
    ++        # more with the slot's token; else the Outcome. Another thread may
    ++        # have refreshed or replaced the token while the request was out: the
    ++        # 401 was for the old one, so the new one is sent once, and a cleared
    ++        # slot sends nothing. An expired token is refreshed once; any other
    ++        # 401 means the token is dead and the slot is cleared.
    ++        if slot.accessToken != sent:
    ++            return (
    ++                None if slot.accessToken and not refreshed else Outcome(REFUSED, "401")
    ++            )
    ++        if (
    ++            not refreshed
    ++            and "expired" in req.text
    ++            and slot.source != "synced"
    ++            and slot.refreshToken
    ++        ):
    ++            result = self.refreshSlot(slot)
    ++            if result == "success":
    ++                return None
    ++            if result == "unreachable":
    ++                return Outcome(UNREACHABLE, "token refresh")
    ++            if not slot.empty():
    ++                # Expired and the refresh failed (a 5xx, no client ID): the
    ++                # tokens are kept, as refresh() alone clears on a 401, but no
    ++                # later round pays for another 401. A successful refresh
    ++                # (setTokens) lifts the refusal.
    ++                logger.error(
    ++                    "Tesla %s API token has expired and could not be "
    ++                    "refreshed (%s); not sending commands with it until "
    ++                    "it is refreshed or replaced." % (slot.kind.capitalize(), result)
    ++                )
    ++                slot.refuse("command")
    ++            return Outcome(REFUSED, "401")
    ++        self.commandRefused(slot, 401)
    ++        return Outcome(REFUSED, "401")
    ++
     +    def commandRefused(self, slot, code):
     +        # Retires a slot Tesla refused a command or wake with: a 401 clears
     +        # it; a 412 retires its command purpose until the token changes.
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +        vehicle.firstChargeNeededTime = 0
     +        vehicle.delayNextWakeAttempt = 0
     +
    -     def setChargeRate(self, charge_rate, vehicle=None, set_again=False):
    +     def setChargeRate(self, charge_rate, vehicle=None, set_again=False, retried=False):
              # As a fallback to allow initial implementation of the charge rate functionality for single car installs,
              # If no vehicle is specified, we take the first returned to us.
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class CarApiVehicle:
    @@ tests/unit/test_provider_outcomes_cloud.py (new)
     +    assert p.stopCharging(VIN) == O.Outcome(O.REFUSED, "401") and len(calls(requests_mock, "charge_stop")) == 4 and refresh.call_count == 2
     +    assert api.fleetSlot.empty()                                                   # refreshed once, refused again: retired
     +
    ++def test_a_401_for_a_token_replaced_meanwhile_sends_the_new_one_once(requests_mock):
    ++    # Another thread pasted a token while the command was out: the 401 was for
    ++    # the old one, which must not clear the new one
    ++    api, reg, p = fleet(requests_mock); pasted = fleet_token(jti="pasted")
    ++    def replacedThen401(request, context):
    ++        api.storeToken(pasted, "", "pasted"); context.status_code = 401; return "invalid bearer token"
    ++    requests_mock.post(re.compile(r".*/command/.*"), [{"text": replacedThen401}, {"json": {"response": {"result": True}}}])
    ++    assert p.stopCharging(VIN).kind == O.DONE and api.fleetSlot.accessToken == pasted
    ++    sent = calls(requests_mock, "charge_stop"); assert len(sent) == 2 and sent[1].headers["Authorization"] == "Bearer " + pasted
    ++    def clearedThen401(request, context):
    ++        api.fleetSlot.clear(); context.status_code = 401; return "invalid bearer token"
    ++    requests_mock.post(re.compile(r".*/command/.*"), text=clearedThen401)
    ++    assert p.stopCharging(VIN) == O.Outcome(O.REFUSED, "401") and len(calls(requests_mock, "charge_stop")) == 3
    ++
     +def test_backoff_429_and_412_send_nothing_more(requests_mock):
     +    api, reg, p = fleet(requests_mock, status=429); car = api.getCarApiVehicles()[0]
     +    assert p.setChargeLimit(VIN, 80) == O.Outcome(O.ERROR, "429")
 3:  35644737 !  3:  d5cfe5e8 Declare provider capabilities, costs and suppressions as tables
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              while True:
                  # Built per attempt, so the retry after a refresh sends the new token
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    -                 self.commandRefused(slot, 401)
    -                 return Outcome(REFUSED, "401"), None
    +                     continue
    +                 return outcome, None
                  if code == 403:
     -                slot.reportScopeRefused("command", refused=True)
     +                slot.reportScopeRefused(purpose, refused=True)
    @@ tests/unit/test_provider_tables.py (new)
     +    assert p.stopCharging(VIN) == O.Outcome(O.REFUSED, "403") and not api.fleetSlot.usable("command") and api.fleetSlot.usable("read")
     
      ## tests/unit/test_vehicle_priority.py ##
    -@@ tests/unit/test_vehicle_priority.py: CMDS = {c: C.Declaration(C.LOCAL) for c in (C.SET_AMPS, C.START_CHARGING, C.STOP
    - class P(Provider):
    -     def __init__(self, name, rank, local, module, ready=True, caps=CMDS, amps=(1, 32)):
    -         self.name, self.rank, self.local, self.module, self._ready, self._caps, self._amps = name, rank, local, module, ready, caps, amps
    -+        if name == "TeslaBLE": self.SUPPRESSED = {"api_only": C.ALL}      # the real provider's table; the others keep the locality rule
    -     def declarations(self): return self._caps
    -     def ready(self, vehicle, cap): return self._ready
    -     def ampsRange(self, vehicle): return self._amps
    +@@ tests/unit/test_vehicle_priority.py: class P(Provider):
    +             self._caps,
    +             self._amps,
    +         ) = (name, rank, local, module, ready, caps, amps)
    ++        if name == "TeslaBLE":
    ++            # The real provider's table; the others keep the locality rule
    ++            self.SUPPRESSED = {"api_only": C.ALL}
    + 
    +     def declarations(self):
    +         return self._caps
     
      ## tests/unit/test_workers.py ##
     @@ tests/unit/test_workers.py: def test_a_failed_wake_is_tagged():                                         # pr
 4:  a973dc41 =  4:  ea9af860 Add the reconciler: charge-limit rules, adoption and one paid fallback
 5:  f5692259 !  5:  2bb42950 Set charge limits through desired state and delete the legacy limit path
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +        # Outside the lock: its other slot's GET never holds it
     +        self.resolveHeldLimits(slot, listed)
     +        return True
    -+
    + 
    +-    def car_api_available(self, charge=None, applyLimit=None, vin=None):
     +    def listPending(self) -> bool:
     +        # The vehicle list is not loaded, or held limits wait on it
     +        held = getattr(self.master, "heldLimits", None)
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +        if req:
     +            logger.log(logging.INFO6, "Response: " + req.text)
     +        return False
    - 
    --    def car_api_available(self, charge=None, applyLimit=None, vin=None):
    ++
     +    def car_api_available(self, charge=None, vin=None):
              now = time.time()
              needSleep = False
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     +                # no error backoff, so the next provider sends at once
     +                return Outcome(REFUSED, "owner refused"), None
                  if code == 401:
    -                 if (
    -                     not refreshed
    +                 # Under the slot's lock, so no other thread refreshes, pastes
    +                 # or clears the token between this check and what follows
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              # online check (vehicles/{vin}, cached 120 s) says it is not online
              # and wakeDue allows it. One wake_up at most.
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class CarApiVehicle:
     -        }
     -        body = {"percent": limit}
     -
    +-        refreshed = False
     -        for _ in range(0, 3):
     -            req = None
     -            try:
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class CarApiVehicle:
     -                self, req
     -            ):
     -                return False
    +-            if getattr(req, "status_code", None) == 401:
    +-                sent = headers["Authorization"].split(" ", 1)[-1]
    +-                if not refreshed and self.carapi.slotCommandFailed(slot, req, sent):
    +-                    refreshed = True
    +-                    headers["Authorization"] = "Bearer " + slot.accessToken
    +-                    continue
    +-                return False
     -
     -            result = False
     -            reason = ""
    @@ tests/unit/test_teslaapi_charge_vin.py: def api(monkeypatch, requests_mock):
              "POST",
              re.compile(r".*/command/charge_(start|stop)"),
     
    + ## tests/unit/test_teslaapi_command_401.py ##
    +@@ tests/unit/test_teslaapi_command_401.py: from unittest.mock import Mock
    + 
    + import pytest
    + 
    ++from TWCManager.Vehicle.Reconcile.Outcome import DONE, SATISFIED, Outcome
    + from tests.unit.teslatokens import FLEET_REFRESH_URL, fleet_token, new_api
    + 
    + OPAQUE_REFRESH = "NA_0123456789abcdef0123456789abcdef"
    +@@ tests/unit/test_teslaapi_command_401.py: def command(api, name):
    +     if name == "wake_up":
    +         return api.wakeVehicle(v)
    +     if name == "set_charge_limit":
    +-        return v.apply_charge_limit(80)
    ++        return api.command(v, "set_charge_limit", {"percent": 80})
    + 
    + 
    + COMMANDS = ["charge_stop", "set_charging_amps", "wake_up", "set_charge_limit"]
    + 
    + 
    ++def failed(result):
    ++    # The legacy paths answer False or "error"; the provider path an Outcome
    ++    if isinstance(result, Outcome):
    ++        return result.kind not in (DONE, SATISFIED)
    ++    return result in (False, "error")
    ++
    ++
    + def url(name):
    +     return re.compile(r".*/" + VIN + "/(command/)?" + name + "$")
    + 
    +@@ tests/unit/test_teslaapi_command_401.py: def test_expired_token_is_refreshed_and_command_retried(api, requests_mock, name
    +     assert refresh.call_count == 1
    +     assert cmd.call_count == 2
    +     assert bearer(cmd.request_history[1]) == new
    +-    assert result not in (False, "error")
    ++    assert not failed(result)
    + 
    + 
    + @pytest.mark.parametrize("name", COMMANDS)
    +@@ tests/unit/test_teslaapi_command_401.py: def test_dead_token_is_cleared(api, requests_mock, name):
    + 
    +     result = command(api, name)
    + 
    +-    assert result in (False, "error")
    ++    assert failed(result)
    +     assert cmd.call_count == 1
    +     assert api.fleetSlot.empty()
    +     assert {"cmd": "saveSettings"} in api.master.tasks
    +@@ tests/unit/test_teslaapi_command_401.py: def test_expired_after_refresh_is_not_retried_again(api, requests_mock, name):
    + 
    +     result = command(api, name)
    + 
    +-    assert result in (False, "error")
    ++    assert failed(result)
    +     assert refresh.call_count == 1
    + 
    + 
    +
      ## tests/unit/test_teslaapi_providers.py ##
     @@ tests/unit/test_teslaapi_providers.py: def test_fleet_commands_resolve_the_car_by_vin():
          api.wakeOutcome.assert_called_once_with(car, now=1000.0)
    @@ tests/unit/test_vehicle_command_queue.py: class TestCancel:
     
      ## tests/unit/test_vehicle_priority.py ##
     @@ tests/unit/test_vehicle_priority.py: def test_ble_only_skips_cloud_commands_but_not_reads():
    -     assert vp.updateChargeAtHome() is True and api.updateChargeAtHome.call_count == 1
      
    - def test_api_only_walks_fleet_without_ble():                      # Review Focus 1
    --    ble = mod(applyChargeLimit=True, updateChargeAtHome=True); api = mod(applyChargeLimit="success", updateChargeAtHome=True)
    -+    ble = mod(car_api_charge=True, updateChargeAtHome=True); api = mod(car_api_charge="success", updateChargeAtHome=True)
    -     m, vp = make({"commandPolicy": "api_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    --    assert vp.applyChargeLimit(limit=80) == "success" and ble.applyChargeLimit.call_count == 0
    -+    assert vp.car_api_charge({"charge": True}) == "success" and ble.car_api_charge.call_count == 0
    -     assert vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0        # reads too: no BLE timeout
    + 
    + def test_api_only_walks_fleet_without_ble():  # Review Focus 1
    +-    ble = mod(applyChargeLimit=True, updateChargeAtHome=True)
    +-    api = mod(applyChargeLimit="success", updateChargeAtHome=True)
    ++    ble = mod(car_api_charge=True, updateChargeAtHome=True)
    ++    api = mod(car_api_charge="success", updateChargeAtHome=True)
    +     m, vp = make(
    +         {"commandPolicy": "api_only"},
    +         P("TeslaBLE", 2, True, ble),
    +         P("FleetAPI", 5, False, api),
    +     )
    +     assert (
    +-        vp.applyChargeLimit(limit=80) == "success"
    +-        and ble.applyChargeLimit.call_count == 0
    ++        vp.car_api_charge({"charge": True}) == "success"
    ++        and ble.car_api_charge.call_count == 0
    +     )
    +     assert (
    +         vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0
    +@@ tests/unit/test_vehicle_priority.py: def test_api_only_walks_fleet_without_ble():  # Review Focus 1
    + 
      
      def test_broadcast_skips_a_provider_that_is_not_available():
    --    api = mod(applyChargeLimit="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    -+    api = mod(car_api_charge="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    +-    api = mod(applyChargeLimit="success")
    ++    api = mod(car_api_charge="success")
    +     f = P("FleetAPI", 5, False, api)
    +     f.available = lambda cap: False  # Owner-only: no command slot
          m, vp = make({}, f)
    --    assert vp.applyChargeLimit(limit=80) is False and api.applyChargeLimit.call_count == 0 and m.stats["moduleFailures"] == {}
    -+    assert vp.car_api_charge({"charge": True}) is False and api.car_api_charge.call_count == 0 and m.stats["moduleFailures"] == {}
    +     assert (
    +-        vp.applyChargeLimit(limit=80) is False
    +-        and api.applyChargeLimit.call_count == 0
    ++        vp.car_api_charge({"charge": True}) is False
    ++        and api.car_api_charge.call_count == 0
    +         and m.stats["moduleFailures"] == {}
    +     )
    + 
      
      def test_targeted_call_skips_providers_not_ready_for_that_car():
    --    ble = mod(applyChargeLimit=True); api = mod(applyChargeLimit="success")
    -+    ble = mod(car_api_charge=True); api = mod(car_api_charge="success")
    -     m, vp = make({}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api))
    +-    ble = mod(applyChargeLimit=True)
    +-    api = mod(applyChargeLimit="success")
    ++    ble = mod(car_api_charge=True)
    ++    api = mod(car_api_charge="success")
    +     m, vp = make(
    +         {}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api)
    +     )
          m.vehicleRegistry.getOrCreate(VIN, "t")
    --    assert vp.applyChargeLimit(limit=80, vin=VIN) == "success" and ble.applyChargeLimit.call_count == 0
    --    assert vp.applyChargeLimit(limit=80) is True and ble.applyChargeLimit.call_count == 1      # broadcast: readiness unknown
    -+    assert vp.car_api_charge({"charge": True, "vin": VIN}) == "success" and ble.car_api_charge.call_count == 0
    -+    assert vp.car_api_charge({"charge": True}) is True and ble.car_api_charge.call_count == 1      # broadcast: readiness unknown
    +     assert (
    +-        vp.applyChargeLimit(limit=80, vin=VIN) == "success"
    +-        and ble.applyChargeLimit.call_count == 0
    ++        vp.car_api_charge({"charge": True, "vin": VIN}) == "success"
    ++        and ble.car_api_charge.call_count == 0
    +     )
    +     assert (
    +-        vp.applyChargeLimit(limit=80) is True and ble.applyChargeLimit.call_count == 1
    ++        vp.car_api_charge({"charge": True}) is True
    ++        and ble.car_api_charge.call_count == 1
    +     )  # broadcast: readiness unknown
    + 
      
    - def test_set_charge_rate_targets_the_car():
    -     twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = mod(setChargeRate=True)
     @@ tests/unit/test_vehicle_priority.py: def _fleetUnloaded(withBle):
    -     from tests.unit.test_carapivehicle_registry import api_with_registry
    -     from tests.unit.teslatokens import fleet_token
    -     api, reg = api_with_registry(); api.storeToken(fleet_token())
    --    api.car_api_charge = Mock(return_value="success"); api.applyChargeLimit = Mock(return_value="success")
    -+    api.car_api_charge = Mock(return_value="success")
    -     m, vp = make(); m.vehicleRegistry = reg
    +     api, reg = api_with_registry()
    +     api.storeToken(fleet_token())
    +     api.car_api_charge = Mock(return_value="success")
    +-    api.applyChargeLimit = Mock(return_value="success")
    +     m, vp = make()
    +     m.vehicleRegistry = reg
     -    ble = mod(car_api_charge=False, applyChargeLimit=False)
     +    ble = mod(car_api_charge=False)
          for p in ([P("TeslaBLE", 2, True, ble)] if withBle else []) + api.providers():
              m.providerOrder.register(p)
          reg.getOrCreate(VIN, "TWC")
    -@@ tests/unit/test_vehicle_priority.py: def test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads():      # C1
    +@@ tests/unit/test_vehicle_priority.py: def test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads():  # C1
          m, vp, api, ble = _fleetUnloaded(withBle=True)
          assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success"
          assert ble.car_api_charge.call_count == 3 and api.car_api_charge.call_count == 1
    --    assert vp.applyChargeLimit(limit=80, vin=VIN) == "success" and api.applyChargeLimit.call_count == 1
    +-    assert (
    +-        vp.applyChargeLimit(limit=80, vin=VIN) == "success"
    +-        and api.applyChargeLimit.call_count == 1
    +-    )
    + 
    + 
    + def test_fleet_only_targeted_commands_work_from_boot():  # C1
    +@@ tests/unit/test_vehicle_priority.py: OTHER = "5YJ3E1EA1KF000009"
      
    - def test_fleet_only_targeted_commands_work_from_boot():                      # C1
    -     m, vp, api, ble = _fleetUnloaded(withBle=False)
    -@@ tests/unit/test_vehicle_priority.py: def test_loaded_list_without_the_car_still_skips_fleet():
    - OTHER = "5YJ3E1EA1KF000009"
      
      def _haCars(*vins, fleet=True):
     -    # HA's real car_api_charge/applyChargeLimit over stand-in HA cars, each
    @@ tests/unit/test_vehicle_priority.py: def _haCars(*vins, fleet=True):
          if fleet:
     -        api = mod(car_api_charge="error", applyChargeLimit="error")
     +        api = mod(car_api_charge="error")
    -         m.providerOrder.register(P("FleetAPI", 5, False, api, caps={c: C.Declaration(C.FLEET_COMMAND) for c in C.COMMANDS}))
    -     return m, vp, ha, api
    - 
    -@@ tests/unit/test_vehicle_priority.py: def test_ha_only_targeted_stop_affects_only_the_target():                   # N1
    - def test_fleet_failure_falls_to_home_assistant_for_the_target_only():       # I1
    -     m, vp, ha, api = _haCars(VIN, OTHER)
    -     assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success" and api.car_api_charge.call_count == 2
    +         m.providerOrder.register(
    +             P(
    +                 "FleetAPI",
    +@@ tests/unit/test_vehicle_priority.py: def test_fleet_failure_falls_to_home_assistant_for_the_target_only():  # I1
    +         vp.car_api_charge({"charge": False, "vin": VIN}) == "success"
    +         and api.car_api_charge.call_count == 2
    +     )
     -    assert vp.applyChargeLimit(limit=80, vin=VIN) == "success"
     -    assert _entities(ha) == ["switch." + VIN, "number." + VIN]
     +    assert _entities(ha) == ["switch." + VIN]
      
    + 
      def test_broadcast_still_reaches_every_home_assistant_car():
          m, vp, ha, _ = _haCars(VIN, OTHER, fleet=False)
          assert vp.car_api_charge({"charge": False}) == "success"
     -    assert vp.applyChargeLimit(limit=80) == "success"
    --    assert _entities(ha) == ["switch." + VIN, "switch." + OTHER, "number." + VIN, "number." + OTHER]
    +-    assert _entities(ha) == [
    +-        "switch." + VIN,
    +-        "switch." + OTHER,
    +-        "number." + VIN,
    +-        "number." + OTHER,
    +-    ]
     +    assert _entities(ha) == ["switch." + VIN, "switch." + OTHER]
      
    + 
      def test_unknown_vin_affects_no_home_assistant_car():
          m, vp, ha, _ = _haCars(VIN, OTHER, fleet=False)
          unknown = "5YJ3E1EA1KF000077"
          assert ha.car_api_charge({"charge": False, "vin": unknown}) == "error"
     -    assert ha.applyChargeLimit(80, vin=unknown) == "error"
          assert ha._call_service.call_count == 0
    -     assert ha.car_api_charge({"charge": False, "vin": VIN.lower()}) == "success"     # not rate limited by the refusal
    +     assert (
    +         ha.car_api_charge({"charge": False, "vin": VIN.lower()}) == "success"
     
      ## tests/unit/test_vehicle_priority_returns.py ##
     @@ tests/unit/test_vehicle_priority_returns.py: def _fleetThenHa(ha):
 6:  4494f222 !  6:  99dbdd6b Start and stop charging as desired state and delete the legacy path
    @@ Commit message
     
         Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
     
    - ## CHANGELOG.md ##
    -@@ CHANGELOG.md: This document logs the changes per release of TWCManager.
    -     * (@MikeBishop) - Fix: Allow Owner API commands per vehicle when Tesla reports `command_signing: off`; other vehicles stay read-only (#659)
    -     * (@MikeBishop) - Fix: Run tesla-control in the host network namespace under Docker, and a BLE command timeout no longer kills TWCManager (#711)
    -     * Fix: Cancel a pending stop-charging command when charging should continue (closes #667)
    --    * Fix: Queue charge start/stop commands per vehicle and send at most one per vehicle per minute, so a refused stop is no longer retried every loop
    - 
    - ## v1.3.4 - 2026-04-24
    - * Features
    -
      ## docs/modules/Vehicle_HomeAssistant.md ##
     @@ docs/modules/Vehicle_HomeAssistant.md: You can generate a long-lived token in Home Assistant under:
      * If the module is enabled but no Tesla vehicles are discovered:
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     -            }
     -
     -            # Retry up to 3 times on certain errors.
    +-            refreshed = False
     -            for _ in range(0, 3):
     -                req = None
     -                try:
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     -                ):
     -                    result = "error"
     -                    break
    +-                if getattr(req, "status_code", None) == 401:
    +-                    sent = headers["Authorization"].split(" ", 1)[-1]
    +-                    if not refreshed and self.slotCommandFailed(slot, req, sent):
    +-                        refreshed = True
    +-                        headers["Authorization"] = "Bearer " + slot.accessToken
    +-                        continue
    +-                    result = "error"
    +-                    break
     -
     -                try:
     -                    logger.log(
    @@ tests/unit/test_teslaapi_charge_vin.py (deleted)
     -        ["5YJ3E1EA1KF000002", "command", "charge_stop"],
     -    ]
     
    + ## tests/unit/test_teslaapi_command_401.py ##
    +@@ tests/unit/test_teslaapi_command_401.py: def bearer(request):
    + def command(api, name):
    +     v = api.getCarApiVehicles()[0]
    +     if name == "charge_stop":
    +-        return api.car_api_charge({"cmd": "charge", "charge": False, "vin": VIN})
    ++        return api.command(v, "charge_stop")
    +     if name == "set_charging_amps":
    +         return api.setChargeRate(16, v)
    +     if name == "wake_up":
    +
      ## tests/unit/test_teslaapi_owner_read.py ##
     @@ tests/unit/test_teslaapi_owner_read.py: def test_owner_token_lists_vehicles_from_products(requests_mock):
          api = new_api()
    @@ tests/unit/test_vehicle_command_queue.py: class TestDrain:
      ## tests/unit/test_vehicle_priority.py ##
     @@ tests/unit/test_vehicle_priority.py: def test_command_policy_properties_delegate():
      
    - def test_no_modules_returns_false():                              # Review Focus 2
    + def test_no_modules_returns_false():  # Review Focus 2
          m, vp = make()
    --    assert vp.startCharging(VIN) is False and vp.car_api_charge({"charge": True}) is False
    +-    assert (
    +-        vp.startCharging(VIN) is False and vp.car_api_charge({"charge": True}) is False
    +-    )
     +    assert vp.wakeVehicle(VIN) is False and vp.setChargeRate(10) is False
      
    + 
      def test_walk_is_order_position_with_local_three_attempts_and_ha_last():
    --    ble = mod(startCharging=False); api = mod(startCharging=False); ha = mod(startCharging=True)
    -+    ble = mod(wakeVehicle=False); api = mod(wakeVehicle=False); ha = mod(wakeVehicle=True)
    -     m, vp = make({}, P("HomeAssistant", 6, False, ha), P("FleetAPI", 5, False, api), P("TeslaBLE", 2, True, ble))
    +-    ble = mod(startCharging=False)
    +-    api = mod(startCharging=False)
    +-    ha = mod(startCharging=True)
    ++    ble = mod(wakeVehicle=False)
    ++    api = mod(wakeVehicle=False)
    ++    ha = mod(wakeVehicle=True)
    +     m, vp = make(
    +         {},
    +         P("HomeAssistant", 6, False, ha),
    +         P("FleetAPI", 5, False, api),
    +         P("TeslaBLE", 2, True, ble),
    +     )
     -    assert vp.startCharging(VIN) is True
    --    assert (ble.startCharging.call_count, api.startCharging.call_count, ha.startCharging.call_count) == (3, 2, 1)
     +    assert vp.wakeVehicle(VIN) is True
    -+    assert (ble.wakeVehicle.call_count, api.wakeVehicle.call_count, ha.wakeVehicle.call_count) == (3, 2, 1)
    -     assert m.stats["moduleFailures"] == {"TeslaBLE": 1, "FleetAPI": 1} and m.stats["moduleSuccess"] == {"HomeAssistant": 1}
    +     assert (
    +-        ble.startCharging.call_count,
    +-        api.startCharging.call_count,
    +-        ha.startCharging.call_count,
    ++        ble.wakeVehicle.call_count,
    ++        api.wakeVehicle.call_count,
    ++        ha.wakeVehicle.call_count,
    +     ) == (3, 2, 1)
    +     assert m.stats["moduleFailures"] == {"TeslaBLE": 1, "FleetAPI": 1} and m.stats[
    +         "moduleSuccess"
    +@@ tests/unit/test_vehicle_priority.py: def test_walk_is_order_position_with_local_three_attempts_and_ha_last():
    + 
      
      def test_ble_only_skips_cloud_commands_but_not_reads():
    --    ble = mod(startCharging=False, updateChargeAtHome=False); api = mod(startCharging=True, updateChargeAtHome=True)
    -+    ble = mod(wakeVehicle=False, updateChargeAtHome=False); api = mod(wakeVehicle=True, updateChargeAtHome=True)
    -     m, vp = make({"commandPolicy": "ble_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    +-    ble = mod(startCharging=False, updateChargeAtHome=False)
    +-    api = mod(startCharging=True, updateChargeAtHome=True)
    ++    ble = mod(wakeVehicle=False, updateChargeAtHome=False)
    ++    api = mod(wakeVehicle=True, updateChargeAtHome=True)
    +     m, vp = make(
    +         {"commandPolicy": "ble_only"},
    +         P("TeslaBLE", 2, True, ble),
    +         P("FleetAPI", 5, False, api),
    +     )
     -    assert vp.startCharging(VIN) is False and api.startCharging.call_count == 0
     +    assert vp.wakeVehicle(VIN) is False and api.wakeVehicle.call_count == 0
          assert vp.updateChargeAtHome() is True and api.updateChargeAtHome.call_count == 1
      
    - def test_api_only_walks_fleet_without_ble():                      # Review Focus 1
    --    ble = mod(car_api_charge=True, updateChargeAtHome=True); api = mod(car_api_charge="success", updateChargeAtHome=True)
    -+    ble = mod(wakeVehicle=True, updateChargeAtHome=True); api = mod(wakeVehicle="success", updateChargeAtHome=True)
    -     m, vp = make({"commandPolicy": "api_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    --    assert vp.car_api_charge({"charge": True}) == "success" and ble.car_api_charge.call_count == 0
    + 
    + def test_api_only_walks_fleet_without_ble():  # Review Focus 1
    +-    ble = mod(car_api_charge=True, updateChargeAtHome=True)
    +-    api = mod(car_api_charge="success", updateChargeAtHome=True)
    ++    ble = mod(wakeVehicle=True, updateChargeAtHome=True)
    ++    api = mod(wakeVehicle="success", updateChargeAtHome=True)
    +     m, vp = make(
    +         {"commandPolicy": "api_only"},
    +         P("TeslaBLE", 2, True, ble),
    +         P("FleetAPI", 5, False, api),
    +     )
    +-    assert (
    +-        vp.car_api_charge({"charge": True}) == "success"
    +-        and ble.car_api_charge.call_count == 0
    +-    )
     +    assert vp.wakeVehicle(None) == "success" and ble.wakeVehicle.call_count == 0
    -     assert vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0        # reads too: no BLE timeout
    +     assert (
    +         vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0
    +     )  # reads too: no BLE timeout
    + 
      
      def test_broadcast_skips_a_provider_that_is_not_available():
    --    api = mod(car_api_charge="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    -+    api = mod(wakeVehicle="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    +-    api = mod(car_api_charge="success")
    ++    api = mod(wakeVehicle="success")
    +     f = P("FleetAPI", 5, False, api)
    +     f.available = lambda cap: False  # Owner-only: no command slot
          m, vp = make({}, f)
    --    assert vp.car_api_charge({"charge": True}) is False and api.car_api_charge.call_count == 0 and m.stats["moduleFailures"] == {}
    -+    assert vp.wakeVehicle(None) is False and api.wakeVehicle.call_count == 0 and m.stats["moduleFailures"] == {}
    +     assert (
    +-        vp.car_api_charge({"charge": True}) is False
    +-        and api.car_api_charge.call_count == 0
    ++        vp.wakeVehicle(None) is False
    ++        and api.wakeVehicle.call_count == 0
    +         and m.stats["moduleFailures"] == {}
    +     )
    + 
      
      def test_targeted_call_skips_providers_not_ready_for_that_car():
    --    ble = mod(car_api_charge=True); api = mod(car_api_charge="success")
    -+    ble = mod(wakeVehicle=True); api = mod(wakeVehicle="success")
    -     m, vp = make({}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api))
    +-    ble = mod(car_api_charge=True)
    +-    api = mod(car_api_charge="success")
    ++    ble = mod(wakeVehicle=True)
    ++    api = mod(wakeVehicle="success")
    +     m, vp = make(
    +         {}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api)
    +     )
          m.vehicleRegistry.getOrCreate(VIN, "t")
    --    assert vp.car_api_charge({"charge": True, "vin": VIN}) == "success" and ble.car_api_charge.call_count == 0
    --    assert vp.car_api_charge({"charge": True}) is True and ble.car_api_charge.call_count == 1      # broadcast: readiness unknown
     +    assert vp.wakeVehicle(VIN) == "success" and ble.wakeVehicle.call_count == 0
    -+    assert vp.wakeVehicle(None) is True and ble.wakeVehicle.call_count == 1      # broadcast: readiness unknown
    +     assert (
    +-        vp.car_api_charge({"charge": True, "vin": VIN}) == "success"
    +-        and ble.car_api_charge.call_count == 0
    +-    )
    +-    assert (
    +-        vp.car_api_charge({"charge": True}) is True
    +-        and ble.car_api_charge.call_count == 1
    ++        vp.wakeVehicle(None) is True and ble.wakeVehicle.call_count == 1
    +     )  # broadcast: readiness unknown
    + 
      
    - def test_set_charge_rate_targets_the_car():
    -     twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = mod(setChargeRate=True)
     @@ tests/unit/test_vehicle_priority.py: def test_set_charge_rate_targets_the_car():
    -     car = Mock(VIN=VIN)
    -     assert vp.setChargeRate(4, car) is True and api.setChargeRate.call_args.args == (4, car)   # below the floor
    -     assert VehiclePriority.targetVIN("setChargeRate", (10, car), {}) == VIN and VehiclePriority.targetVIN("wakeVehicle", (VIN.lower(),), {}) == VIN
    --    assert VehiclePriority.targetVIN("car_api_charge", ({"charge": False, "vin": VIN},), {}) == VIN
    +         VehiclePriority.targetVIN("setChargeRate", (10, car), {}) == VIN
    +         and VehiclePriority.targetVIN("wakeVehicle", (VIN.lower(),), {}) == VIN
    +     )
    +-    assert (
    +-        VehiclePriority.targetVIN(
    +-            "car_api_charge", ({"charge": False, "vin": VIN},), {}
    +-        )
    +-        == VIN
    +-    )
    + 
      
      def test_set_charge_rate_zero_still_reaches_the_vehicle():
    -     # Mode 2 can queue 0 A; TeslaAPI clamps it to 1 A today. The lookup
     @@ tests/unit/test_vehicle_priority.py: def test_same_module_under_two_providers_is_walked_once():
    -     assert m.stats["moduleFailures"] == {"OwnerAPI": 1}
    + 
      
      def test_exceptions_count_as_failures_and_dunder_probes_do_not_walk():
    --    api = Mock(spec=["startCharging"]); api.startCharging = Mock(side_effect=RuntimeError("secret"))
    -+    api = Mock(spec=["wakeVehicle"]); api.wakeVehicle = Mock(side_effect=RuntimeError("secret"))
    +-    api = Mock(spec=["startCharging"])
    +-    api.startCharging = Mock(side_effect=RuntimeError("secret"))
    ++    api = Mock(spec=["wakeVehicle"])
    ++    api.wakeVehicle = Mock(side_effect=RuntimeError("secret"))
          m, vp = make({}, P("FleetAPI", 5, False, api))
     -    assert vp.startCharging(VIN) is False and api.startCharging.call_count == 2
     +    assert vp.wakeVehicle(VIN) is False and api.wakeVehicle.call_count == 2
    @@ tests/unit/test_vehicle_priority.py: def test_same_module_under_two_providers_is
          assert not hasattr(vp, "__deepcopy__") and not hasattr(vp, "_private")
      
     @@ tests/unit/test_vehicle_priority.py: def test_attempts_match_todays_priorities():
    -     from tests.unit.test_carapivehicle_registry import api_with_registry
          from tests.unit.teslatokens import fleet_token
    + 
          m, vp, ha, reg = _haMaster()
     -    ha.car_api_charge = Mock(return_value="error")
    --    api, _ = api_with_registry(); api.storeToken(fleet_token()); api.car_api_charge = Mock(return_value="error")
     +    ha.setChargeRate = Mock(return_value="error")
    -+    api, _ = api_with_registry(); api.storeToken(fleet_token()); api.setChargeRate = Mock(return_value="error")
    +     api, _ = api_with_registry()
    +     api.storeToken(fleet_token())
    +-    api.car_api_charge = Mock(return_value="error")
    ++    api.setChargeRate = Mock(return_value="error")
          for p in api.providers():
              m.providerOrder.register(p)
     -    assert vp.car_api_charge({"charge": True}) is False
    @@ tests/unit/test_vehicle_priority.py: def test_attempts_match_todays_priorities()
     +    assert (api.setChargeRate.call_count, ha.setChargeRate.call_count) == (2, 1)
          assert m.stats["moduleFailures"] == {"FleetAPI": 1, "HomeAssistant": 1}
      
    - def test_home_assistant_gets_its_own_vehicle_for_set_charge_rate():
    + 
     @@ tests/unit/test_vehicle_priority.py: def test_home_assistant_gets_its_own_vehicle_for_set_charge_rate():
      
      def test_disabled_home_assistant_gets_no_broadcast():
          m, vp, ha, reg = _haMaster(enabled=False)
    --    ha.car_api_charge = Mock(return_value="success"); ha.updateChargeAtHome = Mock(return_value=True)
    --    assert vp.car_api_charge({"charge": True}) is False and ha.car_api_charge.call_count == 0
    -+    ha.setChargeRate = Mock(return_value=True); ha.updateChargeAtHome = Mock(return_value=True)
    +-    ha.car_api_charge = Mock(return_value="success")
    ++    ha.setChargeRate = Mock(return_value=True)
    +     ha.updateChargeAtHome = Mock(return_value=True)
    +-    assert (
    +-        vp.car_api_charge({"charge": True}) is False
    +-        and ha.car_api_charge.call_count == 0
    +-    )
     +    assert vp.setChargeRate(10) is False and ha.setChargeRate.call_count == 0
          assert vp.updateChargeAtHome() is False and ha.updateChargeAtHome.call_count == 0
    --
    --
    + 
    + 
     -# Fix round 2
     -
    +-
     -def _fleetUnloaded(withBle):
     -    # TeslaAPI holds a Fleet token but has not listed its vehicles yet; the
     -    # registry vehicle came from the TWC, so it has no TeslaAPI attachment
     -    from tests.unit.test_carapivehicle_registry import api_with_registry
     -    from tests.unit.teslatokens import fleet_token
    --    api, reg = api_with_registry(); api.storeToken(fleet_token())
    +-
    +-    api, reg = api_with_registry()
    +-    api.storeToken(fleet_token())
     -    api.car_api_charge = Mock(return_value="success")
    --    m, vp = make(); m.vehicleRegistry = reg
    +-    m, vp = make()
    +-    m.vehicleRegistry = reg
     -    ble = mod(car_api_charge=False)
     -    for p in ([P("TeslaBLE", 2, True, ble)] if withBle else []) + api.providers():
     -        m.providerOrder.register(p)
    @@ tests/unit/test_vehicle_priority.py: def test_home_assistant_gets_its_own_vehicl
     -    assert api.getVehicleCount() == 0
     -    return m, vp, api, ble
     -
    --def test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads():      # C1
    +-
    +-def test_failed_ble_stop_falls_back_to_fleet_before_the_list_loads():  # C1
     -    m, vp, api, ble = _fleetUnloaded(withBle=True)
     -    assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success"
     -    assert ble.car_api_charge.call_count == 3 and api.car_api_charge.call_count == 1
     -
    --def test_fleet_only_targeted_commands_work_from_boot():                      # C1
    +-
    +-def test_fleet_only_targeted_commands_work_from_boot():  # C1
     -    m, vp, api, ble = _fleetUnloaded(withBle=False)
     -    api.car_api_charge.return_value = "error"
    --    assert vp.car_api_charge({"charge": False, "vin": VIN}) is False and api.car_api_charge.call_count == 2
    +-    assert (
    +-        vp.car_api_charge({"charge": False, "vin": VIN}) is False
    +-        and api.car_api_charge.call_count == 2
    +-    )
     -    assert m.stats["moduleFailures"] == {"FleetAPI": 1}
     -
    +-
     -def test_loaded_list_without_the_car_still_skips_fleet():
     -    m, vp, api, ble = _fleetUnloaded(withBle=False)
     -    api.addVehicle({"id": 2, "vin": "5YJ3E1EA1KF000009", "display_name": "Other"})
    --    assert vp.car_api_charge({"charge": False, "vin": VIN}) is False and api.car_api_charge.call_count == 0
    +-    assert (
    +-        vp.car_api_charge({"charge": False, "vin": VIN}) is False
    +-        and api.car_api_charge.call_count == 0
    +-    )
    +-
     -
     -OTHER = "5YJ3E1EA1KF000009"
     -
    +-
     -def _haCars(*vins, fleet=True):
     -    # HA's real car_api_charge over stand-in HA cars, each
     -    # at home, connected and charging; _call_service records the entities
     -    m, vp, ha, reg = _haMaster()
     -    cars = []
     -    for vin in vins:
    --        hv = Mock(vin=vin, at_home=True, charging=True, charge_limit=None, has_charge_switch=True, has_charge_limit_number=True,
    --                  entity_ids={"charge_switch": "switch." + vin, "charge_limit_number": "number." + vin})
    --        hv.name = vin; cars.append(hv)
    +-        hv = Mock(
    +-            vin=vin,
    +-            at_home=True,
    +-            charging=True,
    +-            charge_limit=None,
    +-            has_charge_switch=True,
    +-            has_charge_limit_number=True,
    +-            entity_ids={
    +-                "charge_switch": "switch." + vin,
    +-                "charge_limit_number": "number." + vin,
    +-            },
    +-        )
    +-        hv.name = vin
    +-        cars.append(hv)
     -        reg.getOrCreate(vin, "t").attach("HomeAssistant", hv)
     -    ha.carApiVehicles = cars
    --    ha.car_api_available = Mock(return_value=True); ha._is_vehicle_connected = Mock(return_value=True)
    +-    ha.car_api_available = Mock(return_value=True)
    +-    ha._is_vehicle_connected = Mock(return_value=True)
     -    ha._call_service = Mock(return_value=True)
     -    api = None
     -    if fleet:
     -        api = mod(car_api_charge="error")
    --        m.providerOrder.register(P("FleetAPI", 5, False, api, caps={c: C.Declaration(C.FLEET_COMMAND) for c in C.COMMANDS}))
    +-        m.providerOrder.register(
    +-            P(
    +-                "FleetAPI",
    +-                5,
    +-                False,
    +-                api,
    +-                caps={c: C.Declaration(C.FLEET_COMMAND) for c in C.COMMANDS},
    +-            )
    +-        )
     -    return m, vp, ha, api
     -
    +-
     -def _entities(ha):
     -    return [c.args[2]["entity_id"] for c in ha._call_service.call_args_list]
     -
    --def test_ha_only_targeted_stop_affects_only_the_target():                   # N1
    +-
    +-def test_ha_only_targeted_stop_affects_only_the_target():  # N1
     -    m, vp, ha, _ = _haCars(VIN, OTHER, fleet=False)
    --    assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success" and _entities(ha) == ["switch." + VIN]
    +-    assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success" and _entities(
    +-        ha
    +-    ) == ["switch." + VIN]
     -
    --def test_fleet_failure_falls_to_home_assistant_for_the_target_only():       # I1
    +-
    +-def test_fleet_failure_falls_to_home_assistant_for_the_target_only():  # I1
     -    m, vp, ha, api = _haCars(VIN, OTHER)
    --    assert vp.car_api_charge({"charge": False, "vin": VIN}) == "success" and api.car_api_charge.call_count == 2
    +-    assert (
    +-        vp.car_api_charge({"charge": False, "vin": VIN}) == "success"
    +-        and api.car_api_charge.call_count == 2
    +-    )
     -    assert _entities(ha) == ["switch." + VIN]
     -
    +-
     -def test_broadcast_still_reaches_every_home_assistant_car():
     -    m, vp, ha, _ = _haCars(VIN, OTHER, fleet=False)
     -    assert vp.car_api_charge({"charge": False}) == "success"
     -    assert _entities(ha) == ["switch." + VIN, "switch." + OTHER]
     -
    +-
     -def test_unknown_vin_affects_no_home_assistant_car():
     -    m, vp, ha, _ = _haCars(VIN, OTHER, fleet=False)
     -    unknown = "5YJ3E1EA1KF000077"
     -    assert ha.car_api_charge({"charge": False, "vin": unknown}) == "error"
     -    assert ha._call_service.call_count == 0
    --    assert ha.car_api_charge({"charge": False, "vin": VIN.lower()}) == "success"     # not rate limited by the refusal
    +-    assert (
    +-        ha.car_api_charge({"charge": False, "vin": VIN.lower()}) == "success"
    +-    )  # not rate limited by the refusal
    +-
    +-
    + def _enabledFacade(*modules):
    +     master = Mock()
    +     master.providerOrder = Mock()
     
      ## tests/unit/test_vehicle_priority_returns.py ##
     @@
 7:  6beceef5 !  7:  dd9540ba Set charge amps through desired state and delete the legacy rate path
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
          refreshClientID = ""
          # FleetAPI OAuth (authorization code) login. Two variants, auto-selected by
          # whether a client secret is configured:
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +             slot.pause()
    +         return False
    + 
    +-    def slotCommandFailed(self, slot, response, token):
    +-        # Reacts to a 401 on a vehicle command sent with this slot's access
    +-        # token (#689). Returns True when the slot now holds a new token,
    +-        # so the caller should retry once. An expired token is refreshed;
    +-        # any other 401 means it is dead, so it is cleared and commands
    +-        # stop using it, letting VehiclePriority move on. Unlike a read, a
    +-        # 403/410/412 here does not pause the slot.
    +-        if getattr(response, "status_code", None) != 401:
    +-            return False
    +-        with slot.lock:
    +-            if slot.accessToken != token:
    +-                # Another thread already refreshed or replaced it.
    +-                return bool(slot.accessToken)
    +-            if (
    +-                "expired" in response.text
    +-                and slot.source != "synced"
    +-                and slot.refreshToken
    +-            ):
    +-                return self.refreshSlot(slot) == "success"
    +-            logger.error(
    +-                "Tesla %s API token was rejected for a vehicle command "
    +-                "(HTTP 401); removing it." % slot.kind.capitalize()
    +-            )
    +-            slot.clear()
    +-        self.master.queue_background_task({"cmd": "saveSettings"})
    +-        return False
    +-
    +     def tokenRoute(self, token):
    +         # (tokenType, baseURL, verifyCert) for an access token: where its
    +         # requests go. Both slots classify their tokens with this.
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              vehicle.firstChargeNeededTime = 0
              vehicle.delayNextWakeAttempt = 0
      
    --    def setChargeRate(self, charge_rate, vehicle=None, set_again=False):
    +-    def setChargeRate(self, charge_rate, vehicle=None, set_again=False, retried=False):
     -        # As a fallback to allow initial implementation of the charge rate functionality for single car installs,
     -        # If no vehicle is specified, we take the first returned to us.
     -
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     -
     -        if slot is self.ownerSlot and self.noteOwnerCommandRefused(vehicle, req):
     -            return False
    +-        if getattr(req, "status_code", None) == 401:
    +-            sent = headers["Authorization"].split(" ", 1)[-1]
    +-            if not retried and self.slotCommandFailed(slot, req, sent):
    +-                return self.setChargeRate(charge_rate, vehicle, set_again, True)
    +-            return False
     -        if apiResponseDict is None:
     -            return False
     -
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
                              car.atHome = True
                      return
      
    --    def wakeVehicle(self, vehicle):
    +-    def wakeVehicle(self, vehicle, retried=False):
     -        if self.refuseCommandFor(vehicle, "wake_up"):
     -            return False
     -        slot = self.commandSlotFor(vehicle)
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     -                pass
     -            elif slot is self.ownerSlot and self.noteOwnerCommandRefused(vehicle, req):
     -                pass
    --            elif req.status_code == 401 and "expired" in req.text:
    --                # If the token is expired, refresh it and try again
    --                if self.refreshSlot(slot) == "success":
    --                    return self.wakeVehicle(vehicle)
    +-            elif req.status_code == 401:
    +-                # Refresh an expired token and try again; clear a dead one.
    +-                sent = headers["Authorization"].split(" ", 1)[-1]
    +-                if not retried and self.slotCommandFailed(slot, req, sent):
    +-                    return self.wakeVehicle(vehicle, True)
     -            elif req.status_code == 429:
     -                # We're explicitly being told to back off
     -                self.errorCount = max(30, self.errorCount)
    @@ lib/TWCManager/Vehicle/VehiclePriority.py (deleted)
     -        # its own, and must not walk the order for this
     -        return []
     -
    +-    def enabled(self):
    +-        # getModuleByName() checks this on every lookup. Answer directly
    +-        # rather than through __getattr__, whose provider walk logs several
    +-        # lines per call and ran many times a second.
    +-        for module in self.master.getModulesByType("Vehicle"):
    +-            ref = module["ref"]
    +-            if ref is self or not module["priority"]:
    +-                continue
    +-            enabled_fn = getattr(ref, "enabled", None)
    +-            if not callable(enabled_fn) or enabled_fn():
    +-                return True
    +-        return False
    +-
     -    @staticmethod
     -    def capabilityFor(name, args, kwargs) -> Optional[str]:
     -        return VehiclePriority.COMMAND_CAPABILITIES.get(name)
    @@ tests/unit/test_teslaapi_chargerate.py (deleted)
     -        assert api.setChargeRate(float("nan"), v) is False
     -    post.assert_not_called()
     
    + ## tests/unit/test_teslaapi_command_401.py ##
    +@@
    + """
    +-A 401 on a vehicle command (#689). An expired token is refreshed and the
    +-command retried once; any other 401 clears the token, so commands stop
    +-using it and VehiclePriority falls back to the next module.
    ++A 401 on a vehicle command or wake. An expired token is refreshed and the
    ++request sent once more; any other 401 clears the token, so commands stop
    ++using it and the next provider carries them. (A 401 for a token another
    ++thread replaced while the request was out: test_provider_outcomes_cloud.)
    + """
    + 
    + import re
    +@@ tests/unit/test_teslaapi_command_401.py: from unittest.mock import Mock
    + 
    + import pytest
    + 
    +-from TWCManager.Vehicle.Reconcile.Outcome import DONE, SATISFIED, Outcome
    ++from TWCManager.Vehicle.Reconcile.Outcome import DONE, REFUSED, SATISFIED, Outcome
    + from tests.unit.teslatokens import FLEET_REFRESH_URL, fleet_token, new_api
    + 
    + OPAQUE_REFRESH = "NA_0123456789abcdef0123456789abcdef"
    +@@ tests/unit/test_teslaapi_command_401.py: VIN = "5YJ3E1EA1KF000001"
    + DEAD = {"status_code": 401, "text": '{"error": "invalid bearer token"}'}
    + 
    + 
    +-class _NoThread:
    +-    daemon = False
    +-
    +-    def start(self):
    +-        pass
    +-
    +-
    + @pytest.fixture
    + def api(monkeypatch):
    +     import TWCManager.Vehicle.TeslaAPI as teslaapi
    + 
    +-    monkeypatch.setattr(teslaapi, "Thread", lambda *a, **k: _NoThread(), raising=False)
    +     monkeypatch.setattr(teslaapi.time, "sleep", lambda s: None)
    +     a = new_api()
    +     a.addVehicle({"id": 1, "vin": VIN, "display_name": "Car1"})
    +-    v = a.getCarApiVehicles()[0]
    +-    v.atHome = True
    +-    v.lastAPIAccessTime = time.time()
    +-    v.chargingState = "Charging"
    +-    v.update_charge = Mock(return_value=True)
    +-    v.update_location = Mock(return_value=True)
    +-    a.applyChargeLimit = Mock()
    ++    a.getCarApiVehicles()[0].lastAPIAccessTime = time.time()
    +     return a
    + 
    + 
    +@@ tests/unit/test_teslaapi_command_401.py: def bearer(request):
    + 
    + def command(api, name):
    +     v = api.getCarApiVehicles()[0]
    +-    if name == "charge_stop":
    +-        return api.command(v, "charge_stop")
    +-    if name == "set_charging_amps":
    +-        return api.setChargeRate(16, v)
    +     if name == "wake_up":
    +-        return api.wakeVehicle(v)
    +-    if name == "set_charge_limit":
    +-        return api.command(v, "set_charge_limit", {"percent": 80})
    ++        outcome, response = api._paidPost(v, api.fleetSlot, "wake_up", purpose="wake")
    ++        return Outcome(DONE) if outcome is None else outcome
    ++    body = {
    ++        "set_charging_amps": {"charging_amps": 16},
    ++        "set_charge_limit": {"percent": 80},
    ++    }.get(name)
    ++    return api.command(v, name, body)
    + 
    + 
    +-COMMANDS = ["charge_stop", "set_charging_amps", "wake_up", "set_charge_limit"]
    ++def failed(result):
    ++    return result.kind not in (DONE, SATISFIED)
    + 
    + 
    +-def failed(result):
    +-    # The legacy paths answer False or "error"; the provider path an Outcome
    +-    if isinstance(result, Outcome):
    +-        return result.kind not in (DONE, SATISFIED)
    +-    return result in (False, "error")
    ++COMMANDS = ["charge_stop", "set_charging_amps", "wake_up", "set_charge_limit"]
    + 
    + 
    + def url(name):
    +@@ tests/unit/test_teslaapi_command_401.py: def test_dead_token_is_cleared(api, requests_mock, name):
    + 
    +     result = command(api, name)
    + 
    +-    assert failed(result)
    ++    assert result == Outcome(REFUSED, "401")
    +     assert cmd.call_count == 1
    +     assert api.fleetSlot.empty()
    +     assert {"cmd": "saveSettings"} in api.master.tasks
    +     # With no command token left, the next command is refused without a
    +-    # request, so VehiclePriority moves on to the next module.
    +-    assert api.readOnlyFor(api.getCarApiVehicles()[0])
    ++    # request, so the next provider carries it
    ++    assert api.slotFor("command") is None
    + 
    + 
    + @pytest.mark.parametrize("name", COMMANDS)
    +@@ tests/unit/test_teslaapi_command_401.py: def test_expired_after_refresh_is_not_retried_again(api, requests_mock, name):
    + 
    +     assert failed(result)
    +     assert refresh.call_count == 1
    +-
    +-
    +-def test_set_charging_amps_401_is_not_success(api, requests_mock):
    +-    # Before #689 the 401 body, a non-empty dict, read as success.
    +-    api.storeToken(fleet_token(), "")
    +-    requests_mock.post(url("set_charging_amps"), [DEAD])
    +-
    +-    assert api.setChargeRate(16, api.getCarApiVehicles()[0]) is False
    +-
    +-
    +-def test_token_replaced_while_command_ran_is_kept(api, requests_mock):
    +-    # A 401 for a token another thread has already replaced must not clear
    +-    # the new one.
    +-    api.storeToken(fleet_token(jti="old"), "")
    +-    sent = api.fleetSlot.accessToken
    +-    api.storeToken(fleet_token(jti="pasted"), "", "pasted")
    +-    response = Mock(status_code=401, text="invalid bearer token")
    +-
    +-    assert api.slotCommandFailed(api.fleetSlot, response, sent) is True
    +-    assert not api.fleetSlot.empty()
    ++    assert cmd.call_count == 2
    + 
    + 
    + def test_command_403_does_not_pause_reads(api, requests_mock):
    +     api.storeToken(fleet_token(), "")
    +     requests_mock.post(url("set_charging_amps"), status_code=403, text="")
    + 
    +-    api.setChargeRate(16, api.getCarApiVehicles()[0])
    ++    assert command(api, "set_charging_amps") == Outcome(REFUSED, "403")
    + 
    +     assert api.fleetSlot.pausedUntil == 0
    +     assert not api.fleetSlot.empty()
    +
      ## tests/unit/test_teslaapi_readonly_gate.py ##
     @@ tests/unit/test_teslaapi_readonly_gate.py: missing, or a value never seen) is read-only, as is every vehicle when no
      token can command: no vehicle command may reach Tesla. The provider order
    @@ tests/unit/test_teslable_pairing_status.py: def test_mac_fallback_lookup_timeout
      
      
      def test_pairing_that_could_not_start_creates_no_vehicle_record():  # M7
    -@@ tests/unit/test_teslable_pairing_status.py: def test_failed_device_lookup_is_range_unknown():  # M3
    -     ):
    -         assert ble.scanForVehicleInRange(VIN) is None
    -     assert ble.rangeStatus(VIN)["inRange"] is None
    +@@ tests/unit/test_teslable_pairing_status.py: def test_pairing_debug_output_alone_is_not_a_sent_request():
    +     ble._run_command_with_timeout = Mock(return_value=(b"", output, 1))
    +     assert ble.peerWithVehicle(VIN) is False
    +     assert ble.bleStatus(VIN)["status"] != "pairing"
     +
     +
     +def test_charge_state_maps_the_cars_own_current_request():   # slim Task 12b
    @@ tests/unit/test_vehicle_endpoint.py: def test_state_from_registry_values_without
      ## tests/unit/test_vehicle_priority.py (deleted) ##
     @@
     -# tests/unit/test_vehicle_priority.py
    --from unittest.mock import Mock
    +-from unittest.mock import Mock, patch
     -from TWCManager.Vehicle.Providers import Capability as C
     -from TWCManager.Vehicle.Providers.Order import ProviderOrder
     -from TWCManager.Vehicle.Providers.Provider import Provider
     -from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry
     -from TWCManager.Vehicle.VehiclePriority import VehiclePriority
    +-
     -VIN = "5YJ3E1EA1KF000001"
    --CMDS = {c: C.Declaration(C.LOCAL) for c in (C.SET_AMPS, C.START_CHARGING, C.STOP_CHARGING, C.SET_CHARGE_LIMIT, C.WAKE)}
    +-CMDS = {
    +-    c: C.Declaration(C.LOCAL)
    +-    for c in (C.SET_AMPS, C.START_CHARGING, C.STOP_CHARGING, C.SET_CHARGE_LIMIT, C.WAKE)
    +-}
    +-
     -
     -class P(Provider):
     -    def __init__(self, name, rank, local, module, ready=True, caps=CMDS, amps=(1, 32)):
    --        self.name, self.rank, self.local, self.module, self._ready, self._caps, self._amps = name, rank, local, module, ready, caps, amps
    --        if name == "TeslaBLE": self.SUPPRESSED = {"api_only": C.ALL}      # the real provider's table; the others keep the locality rule
    --    def declarations(self): return self._caps
    --    def ready(self, vehicle, cap): return self._ready
    --    def ampsRange(self, vehicle): return self._amps
    --    def setAmps(self, vin, amps): return self.module.setAmps(vin, amps)
    +-        (
    +-            self.name,
    +-            self.rank,
    +-            self.local,
    +-            self.module,
    +-            self._ready,
    +-            self._caps,
    +-            self._amps,
    +-        ) = (name, rank, local, module, ready, caps, amps)
    +-        if name == "TeslaBLE":
    +-            # The real provider's table; the others keep the locality rule
    +-            self.SUPPRESSED = {"api_only": C.ALL}
    +-
    +-    def declarations(self):
    +-        return self._caps
    +-
    +-    def ready(self, vehicle, cap):
    +-        return self._ready
    +-
    +-    def ampsRange(self, vehicle):
    +-        return self._amps
    +-
    +-    def setAmps(self, vin, amps):
    +-        return self.module.setAmps(vin, amps)
    +-
     -
     -def make(settings=None, *providers):
    --    m = Mock(); m.settings = settings or {}; m.config = {}; m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    --    m.vehicleRegistry = VehicleRegistry({}); m.providerOrder = ProviderOrder(m)
    --    for p in providers: m.providerOrder.register(p)
    +-    m = Mock()
    +-    m.settings = settings or {}
    +-    m.config = {}
    +-    m.stats = {"moduleSuccess": {}, "moduleFailures": {}, "moduleDispatch": {}}
    +-    m.vehicleRegistry = VehicleRegistry({})
    +-    m.providerOrder = ProviderOrder(m)
    +-    for p in providers:
    +-        m.providerOrder.register(p)
     -    return m, VehiclePriority(m)
     -
    +-
     -def mod(**results):
    --    x = Mock(spec=list(results)); [setattr(x, k, Mock(return_value=v)) for k, v in results.items()]; return x
    +-    x = Mock(spec=list(results))
    +-    [setattr(x, k, Mock(return_value=v)) for k, v in results.items()]
    +-    return x
    +-
     -
     -def test_command_policy_properties_delegate():
     -    m, vp = make({"commandPolicy": "ble_only"})
    --    assert vp.commandPolicy == "ble_only" and vp.commandPolicyOverridden is False and vp.updateSettings() is True
    +-    assert (
    +-        vp.commandPolicy == "ble_only"
    +-        and vp.commandPolicyOverridden is False
    +-        and vp.updateSettings() is True
    +-    )
    +-
     -
    --def test_no_modules_returns_false():                              # Review Focus 2
    +-def test_no_modules_returns_false():  # Review Focus 2
     -    m, vp = make()
     -    assert vp.wakeVehicle(VIN) is False and vp.setChargeRate(10) is False
     -
    +-
     -def test_walk_is_order_position_with_local_three_attempts_and_ha_last():
    --    ble = mod(wakeVehicle=False); api = mod(wakeVehicle=False); ha = mod(wakeVehicle=True)
    --    m, vp = make({}, P("HomeAssistant", 6, False, ha), P("FleetAPI", 5, False, api), P("TeslaBLE", 2, True, ble))
    +-    ble = mod(wakeVehicle=False)
    +-    api = mod(wakeVehicle=False)
    +-    ha = mod(wakeVehicle=True)
    +-    m, vp = make(
    +-        {},
    +-        P("HomeAssistant", 6, False, ha),
    +-        P("FleetAPI", 5, False, api),
    +-        P("TeslaBLE", 2, True, ble),
    +-    )
     -    assert vp.wakeVehicle(VIN) is True
    --    assert (ble.wakeVehicle.call_count, api.wakeVehicle.call_count, ha.wakeVehicle.call_count) == (3, 2, 1)
    --    assert m.stats["moduleFailures"] == {"TeslaBLE": 1, "FleetAPI": 1} and m.stats["moduleSuccess"] == {"HomeAssistant": 1}
    +-    assert (
    +-        ble.wakeVehicle.call_count,
    +-        api.wakeVehicle.call_count,
    +-        ha.wakeVehicle.call_count,
    +-    ) == (3, 2, 1)
    +-    assert m.stats["moduleFailures"] == {"TeslaBLE": 1, "FleetAPI": 1} and m.stats[
    +-        "moduleSuccess"
    +-    ] == {"HomeAssistant": 1}
    +-
     -
     -def test_ble_only_skips_cloud_commands_but_not_reads():
    --    ble = mod(wakeVehicle=False, updateChargeAtHome=False); api = mod(wakeVehicle=True, updateChargeAtHome=True)
    --    m, vp = make({"commandPolicy": "ble_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    +-    ble = mod(wakeVehicle=False, updateChargeAtHome=False)
    +-    api = mod(wakeVehicle=True, updateChargeAtHome=True)
    +-    m, vp = make(
    +-        {"commandPolicy": "ble_only"},
    +-        P("TeslaBLE", 2, True, ble),
    +-        P("FleetAPI", 5, False, api),
    +-    )
     -    assert vp.wakeVehicle(VIN) is False and api.wakeVehicle.call_count == 0
     -    assert vp.updateChargeAtHome() is True and api.updateChargeAtHome.call_count == 1
     -
    --def test_api_only_walks_fleet_without_ble():                      # Review Focus 1
    --    ble = mod(wakeVehicle=True, updateChargeAtHome=True); api = mod(wakeVehicle="success", updateChargeAtHome=True)
    --    m, vp = make({"commandPolicy": "api_only"}, P("TeslaBLE", 2, True, ble), P("FleetAPI", 5, False, api))
    +-
    +-def test_api_only_walks_fleet_without_ble():  # Review Focus 1
    +-    ble = mod(wakeVehicle=True, updateChargeAtHome=True)
    +-    api = mod(wakeVehicle="success", updateChargeAtHome=True)
    +-    m, vp = make(
    +-        {"commandPolicy": "api_only"},
    +-        P("TeslaBLE", 2, True, ble),
    +-        P("FleetAPI", 5, False, api),
    +-    )
     -    assert vp.wakeVehicle(None) == "success" and ble.wakeVehicle.call_count == 0
    --    assert vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0        # reads too: no BLE timeout
    +-    assert (
    +-        vp.updateChargeAtHome() is True and ble.updateChargeAtHome.call_count == 0
    +-    )  # reads too: no BLE timeout
    +-
     -
     -def test_broadcast_skips_a_provider_that_is_not_available():
    --    api = mod(wakeVehicle="success"); f = P("FleetAPI", 5, False, api); f.available = lambda cap: False    # Owner-only: no command slot
    +-    api = mod(wakeVehicle="success")
    +-    f = P("FleetAPI", 5, False, api)
    +-    f.available = lambda cap: False  # Owner-only: no command slot
     -    m, vp = make({}, f)
    --    assert vp.wakeVehicle(None) is False and api.wakeVehicle.call_count == 0 and m.stats["moduleFailures"] == {}
    +-    assert (
    +-        vp.wakeVehicle(None) is False
    +-        and api.wakeVehicle.call_count == 0
    +-        and m.stats["moduleFailures"] == {}
    +-    )
    +-
     -
     -def test_targeted_call_skips_providers_not_ready_for_that_car():
    --    ble = mod(wakeVehicle=True); api = mod(wakeVehicle="success")
    --    m, vp = make({}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api))
    +-    ble = mod(wakeVehicle=True)
    +-    api = mod(wakeVehicle="success")
    +-    m, vp = make(
    +-        {}, P("TeslaBLE", 2, True, ble, ready=False), P("FleetAPI", 5, False, api)
    +-    )
     -    m.vehicleRegistry.getOrCreate(VIN, "t")
     -    assert vp.wakeVehicle(VIN) == "success" and ble.wakeVehicle.call_count == 0
    --    assert vp.wakeVehicle(None) is True and ble.wakeVehicle.call_count == 1      # broadcast: readiness unknown
    +-    assert (
    +-        vp.wakeVehicle(None) is True and ble.wakeVehicle.call_count == 1
    +-    )  # broadcast: readiness unknown
    +-
     -
     -def test_set_charge_rate_targets_the_car():
    --    twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = mod(setChargeRate=True)
    --    m, vp = make({}, twc, P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)})); m.vehicleRegistry.getOrCreate(VIN, "t")
    +-    twc = P("Gen2TWC", 0, True, None, amps=(6, 32))
    +-    api = mod(setChargeRate=True)
    +-    m, vp = make(
    +-        {},
    +-        twc,
    +-        P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)}),
    +-    )
    +-    m.vehicleRegistry.getOrCreate(VIN, "t")
     -    car = Mock(VIN=VIN)
    --    assert vp.setChargeRate(4, car) is True and api.setChargeRate.call_args.args == (4, car)   # below the floor
    --    assert VehiclePriority.targetVIN("setChargeRate", (10, car), {}) == VIN and VehiclePriority.targetVIN("wakeVehicle", (VIN.lower(),), {}) == VIN
    +-    assert vp.setChargeRate(4, car) is True and api.setChargeRate.call_args.args == (
    +-        4,
    +-        car,
    +-    )  # below the floor
    +-    assert (
    +-        VehiclePriority.targetVIN("setChargeRate", (10, car), {}) == VIN
    +-        and VehiclePriority.targetVIN("wakeVehicle", (VIN.lower(),), {}) == VIN
    +-    )
    +-
     -
     -def test_set_charge_rate_zero_still_reaches_the_vehicle():
     -    # Mode 2 can queue 0 A; TeslaAPI clamps it to 1 A today. The lookup
     -    # clamps too, so 0 does not drop every candidate; the module gets 0.
     -    api = mod(setChargeRate=True)
    --    m, vp = make({}, P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)})); m.vehicleRegistry.getOrCreate(VIN, "t")
    +-    m, vp = make(
    +-        {},
    +-        P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)}),
    +-    )
    +-    m.vehicleRegistry.getOrCreate(VIN, "t")
     -    car = Mock(VIN=VIN)
    --    assert vp.setChargeRate(0, car) is True and api.setChargeRate.call_args.args == (0, car)
    +-    assert vp.setChargeRate(0, car) is True and api.setChargeRate.call_args.args == (
    +-        0,
    +-        car,
    +-    )
     -    assert VehiclePriority.targetAmps("setChargeRate", (0, car), {}) == 1.0
     -    assert VehiclePriority.targetAmps("setChargeRate", (), {"charge_rate": "x"}) is None
     -
    +-
     -def test_set_amps_dispatches_through_the_order():
    --    ble = Mock(); ble.setAmps = Mock(return_value=True)
    --    m, vp = make({}, P("TeslaBLE", 2, True, ble)); m.vehicleRegistry.getOrCreate(VIN, "t")
    +-    ble = Mock()
    +-    ble.setAmps = Mock(return_value=True)
    +-    m, vp = make({}, P("TeslaBLE", 2, True, ble))
    +-    m.vehicleRegistry.getOrCreate(VIN, "t")
     -    assert vp.setAmps(VIN, 12) is True and ble.setAmps.call_args.args == (VIN, 12)
     -    assert vp.setAmps("5YJ3E1EA1KF000009", 12) is False
     -
    +-
     -def test_queue_dispatches_set_amps():
     -    from TWCManager.VehicleCommandQueue import VehicleCommandQueue
    --    vp = Mock(); vp.setAmps = Mock(return_value=True); q = VehicleCommandQueue(lambda: vp)
    --    assert q._execute({"cmd": "setAmps", "vin": VIN, "amps": 7}) is True and VehicleCommandQueue._key({"cmd": "setAmps", "vin": VIN}) == ("setAmps", VIN)
    --    assert VehicleCommandQueue(lambda: Mock(spec=[]))._execute({"cmd": "setAmps", "vin": VIN, "amps": 7}) is False   # fallback module without setAmps
    +-
    +-    vp = Mock()
    +-    vp.setAmps = Mock(return_value=True)
    +-    q = VehicleCommandQueue(lambda: vp)
    +-    assert q._execute(
    +-        {"cmd": "setAmps", "vin": VIN, "amps": 7}
    +-    ) is True and VehicleCommandQueue._key({"cmd": "setAmps", "vin": VIN}) == (
    +-        "setAmps",
    +-        VIN,
    +-    )
    +-    assert (
    +-        VehicleCommandQueue(lambda: Mock(spec=[]))._execute(
    +-            {"cmd": "setAmps", "vin": VIN, "amps": 7}
    +-        )
    +-        is False
    +-    )  # fallback module without setAmps
    +-
     -
     -def test_same_module_under_two_providers_is_walked_once():
     -    # Owner and Fleet share the TeslaAPI module: one walk position, two attempts
     -    api = mod(updateChargeAtHome=False)
    --    m, vp = make({}, P("OwnerAPI", 4, False, api, caps={}), P("FleetAPI", 5, False, api))
    +-    m, vp = make(
    +-        {}, P("OwnerAPI", 4, False, api, caps={}), P("FleetAPI", 5, False, api)
    +-    )
     -    assert vp.updateChargeAtHome() is False and api.updateChargeAtHome.call_count == 2
     -    assert m.stats["moduleFailures"] == {"OwnerAPI": 1}
     -
    +-
     -def test_exceptions_count_as_failures_and_dunder_probes_do_not_walk():
    --    api = Mock(spec=["wakeVehicle"]); api.wakeVehicle = Mock(side_effect=RuntimeError("secret"))
    +-    api = Mock(spec=["wakeVehicle"])
    +-    api.wakeVehicle = Mock(side_effect=RuntimeError("secret"))
     -    m, vp = make({}, P("FleetAPI", 5, False, api))
     -    assert vp.wakeVehicle(VIN) is False and api.wakeVehicle.call_count == 2
     -    assert m.stats["moduleFailures"] == {"FleetAPI": 1}
     -    assert not hasattr(vp, "__deepcopy__") and not hasattr(vp, "_private")
     -
    +-
     -def test_registration_finds_no_providers_on_the_facade(caplog):
     -    # registerProviders walks every Vehicle module, VehiclePriority (loaded
     -    # first) included; the facade must not walk the order for "providers"
     -    import logging
     -    from TWCManager.Vehicle.Providers.Order import registerProviders
    --    ble = Mock(); ble.providers = lambda: [P("TeslaBLE", 2, True, Mock())]
    +-
    +-    ble = Mock()
    +-    ble.providers = lambda: [P("TeslaBLE", 2, True, Mock())]
     -    m, vp = make()
    --    m.getModulesByType = Mock(return_value=[{"name": "VehiclePriority", "ref": vp}, {"name": "TeslaBLE", "ref": ble}])
    +-    m.getModulesByType = Mock(
    +-        return_value=[
    +-            {"name": "VehiclePriority", "ref": vp},
    +-            {"name": "TeslaBLE", "ref": ble},
    +-        ]
    +-    )
     -    with caplog.at_level(logging.WARNING):
     -        assert registerProviders(m) == ["TeslaBLE"]
     -    assert "Could not register" not in caplog.text and vp.providers() == []
    @@ tests/unit/test_vehicle_priority.py (deleted)
     -def test_rate_raise_reaches_fleet_on_a_fleet_only_install():
     -    # The TWC cannot lift the car's own current limit (#660): a raise to the
     -    # wiring max must reach Fleet even though the TWC covers that rate
    --    twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = mod(setChargeRate=True)
    --    m, vp = make({}, twc, P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)})); m.vehicleRegistry.getOrCreate(VIN, "t")
    +-    twc = P("Gen2TWC", 0, True, None, amps=(6, 32))
    +-    api = mod(setChargeRate=True)
    +-    m, vp = make(
    +-        {},
    +-        twc,
    +-        P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)}),
    +-    )
    +-    m.vehicleRegistry.getOrCreate(VIN, "t")
     -    car = Mock(VIN=VIN)
    --    assert vp.setChargeRate(32, car) is True and api.setChargeRate.call_args.args == (32, car)
    +-    assert vp.setChargeRate(32, car) is True and api.setChargeRate.call_args.args == (
    +-        32,
    +-        car,
    +-    )
     -    assert vp.setChargeRate(10, car) is True and api.setChargeRate.call_count == 2
     -
    +-
     -def test_set_amps_keeps_the_local_amps_rule():
    --    twc = P("Gen2TWC", 0, True, None, amps=(6, 32)); api = Mock(); api.setAmps = Mock(return_value=True)
    --    m, vp = make({}, twc, P("FleetAPI", 5, False, api, caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)})); m.vehicleRegistry.getOrCreate(VIN, "t")
    --    assert vp.setAmps(VIN, 10) is False and api.setAmps.call_count == 0     # the TWC carries 10 A
    +-    twc = P("Gen2TWC", 0, True, None, amps=(6, 32))
    +-    api = Mock()

## phase 3.5: range-diff (pushed 87a9eff1 on fe9eca64) vs (new restack3/phase3.5 on restack3/phase3)
 1:  6c77c102 =  1:  02d6aaa2 Pin the held-limit migration's edge cases
 2:  1b736365 =  2:  fad67898 Answer sync state from the registry vehicle
 3:  f7b7af86 =  3:  d7c40246 Make Forget atomic with a listing
 4:  c7beac1f !  4:  7b7e8d95 Dissolve CarApiVehicle into TeslaAPI and an attached record
    @@ lib/TWCManager/Vehicle/Registry/VehicleRegistry.py: class VehicleRegistry:
      ## lib/TWCManager/Vehicle/TeslaAPI.py ##
     @@
      import base64
    + from contextlib import nullcontext
     +import functools
      import hashlib
      import json
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
              # One request with slot's token to path under the API root (where
              # .../api/1/vehicles lives), bounded by timeout. Returns (response,
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    -                 # no error backoff, so the next provider sends at once
    -                 return req, Outcome(REFUSED, "owner refused")
    -             outcome = self._classify(
    --                slot, req.status_code, purpose, req.text, vehicle, tries > 0
    -+                slot, req.status_code, purpose, req.text, car, tries > 0
    -             )
    +                     )
    +                 else:
    +                     outcome = self._classify(
    +-                        slot, status, purpose, req.text, vehicle, tries > 0
    ++                        slot, status, purpose, req.text, car, tries > 0
    +                     )
                  if outcome is not _REFRESHED:
                      return req, outcome
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    @@ tests/unit/test_provider_outcomes_cloud.py: def test_low_amps_are_sent_twice_and
          monkeypatch.setattr(T.time, "sleep", Mock()); api.now = clk                                                    # TeslaAPI's own clock hook follows the test clock; time.time itself is untouched
          requests_mock.get(re.compile(r".*/api/1/vehicles/%s$" % VIN), json={"response": {"state": "online"}})
          assert p.wake(VIN) == O.Outcome(O.SATISFIED, "online") and calls(requests_mock, "wake_up") == [] and len(calls(requests_mock, "/vehicles/" + VIN)) == 1   # free check, no $0.02
    -@@ tests/unit/test_provider_outcomes_cloud.py: def test_an_expired_token_is_refreshed_and_the_command_sent_once_more(requests_m
    -     assert api.fleetSlot.empty()                                                   # refreshed once, refused again: retired
    +@@ tests/unit/test_provider_outcomes_cloud.py: def test_a_401_for_a_token_replaced_meanwhile_sends_the_new_one_once(requests_mo
    +     assert p.stopCharging(VIN) == O.Outcome(O.REFUSED, "401") and len(calls(requests_mock, "charge_stop")) == 3
      
      def test_backoff_429_and_412_send_nothing_more(requests_mock):
     -    api, reg, p = fleet(requests_mock, status=429); car = api.carApiVehicles[0]
    @@ tests/unit/test_telemetry_registry.py: def test_healthy_topic_is_routed(teslamat
          msg = Mock(topic="teslamate/home/cars/7/charge_limit_soc", payload=b"77")
          tm.mqttMessage(None, None, msg)
     
    + ## tests/unit/test_teslaapi_command_401.py ##
    +@@ tests/unit/test_teslaapi_command_401.py: thread replaced while the request was out: test_provider_outcomes_cloud.)
    + """
    + 
    + import re
    +-import time
    + from unittest.mock import Mock
    + 
    + import pytest
    + 
    + from TWCManager.Vehicle.Reconcile.Outcome import DONE, REFUSED, SATISFIED, Outcome
    +-from tests.unit.teslatokens import FLEET_REFRESH_URL, fleet_token, new_api
    ++from tests.unit.teslatokens import (
    ++    FLEET_REFRESH_URL,
    ++    add_home_vehicle,
    ++    fleet_token,
    ++    new_api,
    ++)
    + 
    + OPAQUE_REFRESH = "NA_0123456789abcdef0123456789abcdef"
    + OK = {"json": {"response": {"result": True, "reason": ""}}}
    +@@ tests/unit/test_teslaapi_command_401.py: def api(monkeypatch):
    + 
    +     monkeypatch.setattr(teslaapi.time, "sleep", lambda s: None)
    +     a = new_api()
    +-    a.addVehicle({"id": 1, "vin": VIN, "display_name": "Car1"})
    +-    a.carApiVehicles[0].lastAPIAccessTime = time.time()
    ++    add_home_vehicle(a, vin=VIN)
    +     return a
    + 
    + 
    +@@ tests/unit/test_teslaapi_command_401.py: def bearer(request):
    + 
    + 
    + def command(api, name):
    +-    v = api.carApiVehicles[0]
    ++    v = api.registry.get(VIN)
    +     if name == "wake_up":
    +         outcome, response = api._paidPost(v, api.fleetSlot, "wake_up", purpose="wake")
    +         return Outcome(DONE) if outcome is None else outcome
    +
      ## tests/unit/test_teslaapi_owner_read.py ##
     @@ tests/unit/test_teslaapi_owner_read.py: def test_owner_token_lists_vehicles_from_products(requests_mock):
          api = new_api()
    @@ tests/unit/test_teslaapi_registry.py: def test_two_concurrent_reads_pay_one_vehi
     +
     +def test_an_incomplete_vehicle_data_answer_logs_what_is_missing(caplog):
     +    import logging
    ++    from TWCManager.Vehicle.TeslaAPI import logger
     +
     +    api, reg = api_with_registry()
     +    api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
    @@ tests/unit/test_teslaapi_registry.py: def test_two_concurrent_reads_pay_one_vehi
     +        api.get_car_api = Mock(return_value=(True, response))
     +        caplog.clear()
     +        assert api.update_vehicle_data(v) is False
    -+        assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
    -+            (logging.ERROR, "update_vehicle_data: %s for %s" % (missing, VIN))
    -+        ]
    ++        # Another test's background thread may still be logging; only this
    ++        # module's records are under test.
    ++        assert [
    ++            (r.levelno, r.getMessage()) for r in caplog.records if r.name == logger.name
    ++        ] == [(logging.ERROR, "update_vehicle_data: %s for %s" % (missing, VIN))]
     +    assert v.value("lat") == 1.0 and v.latest("lon") is None  # lat first
     
      ## tests/unit/test_teslaapi_request_errors.py ##
 5:  cfed053d !  5:  1eb33621 Let the Owner API command cars listed with command_signing off
    @@ Commit message
     
      ## CHANGELOG.md ##
     @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
    -     * (@MikeBishop) - Fix: A rejected pasted refresh token keeps the previous tokens, and a 401 on refresh clears the token type (#687)
    -     * (@MikeBishop) - Fix: Check for a car coming online after a Fleet API wake_up instead of waking it again 30 minutes later (#699)
    -     * (@MikeBishop) - Fix: Stale TeslaMate asleep state no longer stops the free vehicle state check (#699)
    --    * (@MikeBishop) - Fix: Allow Owner API commands per vehicle when Tesla reports `command_signing: off`; other vehicles stay read-only (#659)
    -+    * (@MikeBishop) - Fix: Allow Owner API commands per vehicle when Tesla reports `command_signing: off`; other vehicles stay read-only. They sit just ahead of the Fleet API in the command order, so with both tokens such a vehicle's commands go to the free Owner API, and to the Fleet API once Tesla refuses them. A 410 or 412 (or "only available on fleetapi") stops Owner API commands and wakes for every car on that token until it is entered or synced again, logged once as an error; reads continue (#659)
    -     * (@MikeBishop) - Fix: Run tesla-control in the host network namespace under Docker, and a BLE command timeout no longer kills TWCManager (#711)
    - 
    - ## v1.3.4 - 2026-04-24
    +     * (@MikeBishop) - Held charge limits saved under a numeric Tesla vehicle ID that no Tesla account lists are dropped with one warning, once a vehicle list has come back
    +     * (@MikeBishop) - Settings page labels say "vehicle command (BLE or API)" and "local"/"cloud" where they said "Tesla API"; the stored values are unchanged
    +     * (@MikeBishop) - Held charge limits in settings `chargeLimits` are keyed by VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them. After a downgrade, only 1.3.x's TeslaBLE path reads the VIN-keyed entries; its Tesla API path, keyed by numeric ID, starts over
    ++    * (@MikeBishop) - A vehicle Tesla lists with `command_signing: off` sends its commands through the free Owner API just ahead of the Fleet API in the command order, so with both tokens its commands go to the Owner API, and to the Fleet API once Tesla refuses them. A 410 or 412 (or "only available on fleetapi") stops Owner API commands and wakes for every car on that token until it is entered or synced again, logged once as an error; reads continue (#659)
    + * Bugfixes
    +     * (@MikeBishop) - Whether a car is at home is re-checked on every policy pass from its latest position from any source, including the free TeslaMate and Fleet Telemetry feeds, so no paid read is needed to place a car; a car leaves when a newer position places it away, not only when its TWC's power drops, and a position no newer than TWCManager's last limit write to the car does not count as leaving (see Policy Customization, Charge Limits, which also covers running with no home location set)
    +     * (@MikeBishop) - A failed BLE command no longer falls through to a billed Fleet API command at once (#698 for lowering, the 2026-10-11 stray command); Home Assistant is used only when the Fleet API is unavailable or has refused, never after a plain Fleet failure, so one change is never billed twice; Home Assistant can now restore a car's normal limit; charge limit lowers never wake the car over BLE (#698)
     
      ## docs/Settings.md ##
     @@ docs/Settings.md: This setting specifies that any vehicle which requests to start charging will be
    @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
     -                # Tesla refused the Owner API for this car (logged, latched):
     -                # no error backoff, so the next provider sends at once
     -                return req, Outcome(REFUSED, "owner refused")
    -             outcome = self._classify(
    --                slot, req.status_code, purpose, req.text, car, tries > 0
    -+                slot, req.status_code, purpose, req.text, vehicle, tries > 0
    -             )
    +             status = req.status_code
    +             # A 401 is handled under the slot's lock, so no other thread
    +             # refreshes, pastes or clears the token in between
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +                     )
    +                 else:
    +                     outcome = self._classify(
    +-                        slot, status, purpose, req.text, car, tries > 0
    ++                        slot, status, purpose, req.text, vehicle, tries > 0
    +                     )
                  if outcome is not _REFRESHED:
                      return req, outcome
     @@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    @@ tests/unit/test_provider_tables.py: def test_tables_match_the_declarations_they_
              C.SET_CHARGE_LIMIT: D(C.FLEET_COMMAND), C.START_CHARGING: D(C.FLEET_COMMAND), C.STOP_CHARGING: D(C.FLEET_COMMAND), C.SET_AMPS: D(C.FLEET_COMMAND),
              C.WAKE: D(C.FLEET_WAKE), C.READ_WALL_CONNECTOR_VINS: wcv}
     
    + ## tests/unit/test_teslaapi_command_401.py ##
    +@@ tests/unit/test_teslaapi_command_401.py: def command(api, name):
    +         "set_charging_amps": {"charging_amps": 16},
    +         "set_charge_limit": {"percent": 80},
    +     }.get(name)
    +-    return api.command(v, name, body)
    ++    return api.command(v, name, body, slot=api.fleetSlot)
    + 
    + 
    + def failed(result):
    +
      ## tests/unit/test_teslaapi_providers.py ##
     @@ tests/unit/test_teslaapi_providers.py: def test_two_providers_with_honest_costs():
              5,
 6:  6870f226 =  6:  0a48894e Log vehicle wake decisions at INFO
 7:  d58b68ce !  7:  94b7bfa2 Raise TeslaBLE's default command timeout to 15 s
    @@ Commit message
     
      ## CHANGELOG.md ##
     @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
    -     * (@MikeBishop) - Show each Tesla token slot's status on the Settings page, with a Remove token button (#692)
    +     * (@MikeBishop) - The Vehicles page lists the vehicle registry (tier, providers, last seen, held limit) and can add a vehicle by VIN so a VIN-less TWC with BLE only can be set up; a vehicle added by VIN that nothing else has seen can be forgotten from its page
          * (@MikeBishop) - Gen3 Wall Connectors each get their own target; several units on one bus share the headroom. TWCManager names the car on a Gen3 with a free read of the energy site's live status. This needs the Gen3 registered in the Tesla app and a token that can read energy data (a Fleet API token with the `energy_device_data` scope); a unit's optional `din` key fixes a wrong DIN guess
          * (@MikeBishop) - `controller.Gen2TWCs.ranges` sets a per-TWC `minAmps` (in place of minAmpsPerTWC) and `maxAmps`
     +    * (@MikeBishop) - TeslaBLE's default command timeout is 15 s (was 5 s); authenticated commands often needed more than 5 s
      * Architecture
    -     * Remove Tesla Owner API login flow; FleetAPI, TeslaMate token sync, manual token entry and BLE remain the supported paths, with Owner API tokens used for reads, and for commands only to vehicles Tesla reports with `command_signing: off`
    -     * (@MikeBishop) - Saved Tesla tokens migrate to separate Owner and Fleet settings on first start; downgrading afterwards loses the Owner API token (#692)
    +     * (@MikeBishop) - Serialise settings.json saves under a settings lock so a save no longer races writers on other threads
    +     * (@MikeBishop) - One vehicle registry keyed by VIN holds every per-vehicle field with its source and age; reads cascade BLE then cloud and never wake a car unless asked; a TWC-reported VIN is confirmed by a second query before a vehicle is created; vehicles unseen for 30 days (config vehicle.forgetAfterDays) are forgotten
     
      ## docs/modules/Vehicle_TeslaBLE.md ##
     @@ docs/modules/Vehicle_TeslaBLE.md: BLE being a local wireless technology introduces a number of considerations. The
 8:  7ed45b74 !  8:  01eba6c2 Make the Vehicles page readable and drop Vehicle.tier
    @@ tests/unit/test_teslable_pairing_status.py: import threading
     +from tests.unit.vehicle_helpers import commands
      
      VIN = "5YJ3E1EA1KF000001"
    - 
    + # What tesla-control prints once the car has taken an add-key request
     @@ tests/unit/test_teslable_pairing_status.py: def test_pairing_then_proof_makes_paired_and_managed():
    -     ble._run_command_with_timeout = Mock(return_value=(b"", b"ok", 0))
    +     ble._run_command_with_timeout = Mock(return_value=(b"", SENT, 0))
          assert ble.peerWithVehicle(VIN) is True
          assert ble.bleStatus(VIN)["status"] == "pairing"
     -    assert reg.get(VIN) is None or reg.get(VIN).tier == "observed"
 9:  4c00d9a6 !  9:  0167cdd2 Record Tesla API observations under the slot that made them
    @@ tests/unit/test_teslaapi_registry.py: def test_update_vehicle_data_observes_the_
          assert api.update_vehicle_data(reg.get(VIN)) is True
          obs = reg.get(VIN).latest("chargeCurrentRequest")
     -    assert (obs.value, obs.source) == (16, "TeslaAPI")
    --    assert reg.get(VIN).value("availableCurrent") == 32  # the pilot stays the pilot
     +    assert (obs.value, obs.source) == (16, "OwnerAPI")
    -+    assert reg.get(VIN).value("availableCurrent") == 32   # the pilot stays the pilot
    -+
    -+
    +     assert reg.get(VIN).value("availableCurrent") == 32  # the pilot stays the pilot
    + 
    + 
     +@pytest.mark.parametrize("kind, source", [("owner", "OwnerAPI"), ("fleet", "FleetAPI")])
     +def test_each_slot_records_its_own_source(kind, source):
     +    # Never "TeslaAPI": the listing and each read name the slot that made it
    @@ tests/unit/test_teslaapi_registry.py: def test_update_vehicle_data_observes_the_
     +    assert api.update_vehicle_data(v, slot=slot) is True
     +    assert api.get_car_api.call_args.kwargs["slot"] is slot
     +    assert {v.latest(f).source for f in ("lat", "lon", "batteryLevel")} == {source}
    - 
    - 
    ++
    ++
      def test_update_vehicle_data_records_the_cars_own_ac_maximum():
    +     api, reg = api_with_registry()
    +     api.addVehicle({"id": 1, "vin": VIN, "display_name": "C"})
     @@ tests/unit/test_teslaapi_registry.py: def test_listing_attaches_state_and_both_claims():
          assert fleet.commands is False  # no Fleet token yet
          api.storeToken(fleet_token())
10:  87a9eff1 <  -:  -------- Check only TeslaAPI's records in the incomplete vehicle_data test

## phase 4: range-diff (pushed f1e98620 on 87a9eff1) vs (new restack3/phase4 on restack3/phase3.5)
 1:  d5928f0e =  1:  67ba1795 Send every RS-485 message from the serial loop
 2:  99be9c8f !  2:  72344f2c Refresh Tesla tokens off the serial loop, one refresh per slot at a time
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
          lastTWCResponseMsg = None
          lastUpdateCheck = 0
     
    + ## lib/TWCManager/Vehicle/TeslaAPI.py ##
    +@@
    + import base64
    +-from contextlib import nullcontext
    + import functools
    + import hashlib
    + import json
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         # slot holds no refresh token, so it never refreshes.
    +         for slot in (self.ownerSlot, self.fleetSlot):
    +             if slot.needsRefresh():
    +-                self.refreshSlot(slot, ifNeeded=True)
    ++                logger.log(logging.INFO8, "Attempting token refresh")
    ++                self.refreshSlot(slot)
    + 
    +-    def refreshSlot(self, slot, saveOnFailure=True, ifNeeded=False):
    ++    def refreshSlot(self, slot, saveOnFailure=True):
    +         # Refreshes one slot's tokens. Returns slot.refresh()'s result:
    +         # "success", "rejected", "unreachable" or "not_configured".
    +         # saveOnFailure=False leaves saving a failure's state to the caller.
    +-        # ifNeeded=True skips the refresh unless the token is due for one.
    +-        spending = slot.refreshToken
    +-        with slot.lock:
    +-            if slot.refreshToken != spending:
    +-                # Another thread refreshed, pasted or cleared the token while
    +-                # this one waited; spending the old one again would fail.
    +-                return "success" if slot.accessToken else "not_configured"
    +-            if ifNeeded and not slot.needsRefresh():
    +-                return "success"
    +-            if ifNeeded:
    +-                logger.log(logging.INFO8, "Attempting token refresh")
    +-            return self._refreshSlotLocked(slot, saveOnFailure)
    +-
    +-    def _refreshSlotLocked(self, slot, saveOnFailure):
    ++        # The slot runs one refresh at a time and shares its result, so a
    ++        # single-use refresh token is spent once.
    +         result = slot.refresh()
    +         if result == "success":
    +             self.master.queue_background_task({"cmd": "saveSettings"})
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         # slot). A transport error is logged and carried by its type alone,
    +         # never its text (it can hold the header).
    +         while True:
    +-            sent = slot.accessToken
    ++            sent = slot.changes
    +             try:
    +                 req = getattr(requests, method)(
    +                     slot.baseURL[: -len("vehicles")] + path,
    +                     headers={
    +                         "accept": "application/json",
    +-                        "Authorization": "Bearer " + sent,
    ++                        "Authorization": "Bearer " + slot.accessToken,
    +                     },
    +                     json=body,
    +                     verify=slot.verifyCert,
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +                 logging.INFO8,
    +                 "Car API %s %s: HTTP %s" % (method, path, req.status_code),
    +             )
    +-            status = req.status_code
    +-            # A 401 is handled under the slot's lock, so no other thread
    +-            # refreshes, pastes or clears the token in between
    +-            with slot.lock if status == 401 else nullcontext():
    +-                if status == 401 and slot.accessToken != sent:
    +-                    # Another thread refreshed or replaced the token while
    +-                    # this request was out: the 401 was for the old one, so
    +-                    # the new one is sent once, and a cleared slot sends
    +-                    # nothing
    +-                    outcome = (
    +-                        _REFRESHED if slot.accessToken else Outcome(REFUSED, "401")
    +-                    )
    +-                else:
    +-                    outcome = self._classify(
    +-                        slot, status, purpose, req.text, vehicle, tries > 0
    +-                    )
    ++            outcome = self._classify(
    ++                slot, req.status_code, purpose, req.text, vehicle, tries > 0, sent
    ++            )
    +             if outcome is not _REFRESHED:
    +                 return req, outcome
    +             tries = min(tries - 1, 1)
    +             if tries < 1:
    +                 return req, Outcome(REFUSED, "401")
    + 
    +-    def _classify(self, slot, status, purpose, body, vehicle=None, refresh=True):
    ++    def _classify(
    ++        self, slot, status, purpose, body, vehicle=None, refresh=True, sent=None
    ++    ):
    +         # What an answer means, acted on: None for an HTTP 200 (unless it is
    +         # an Owner command's refusal), else an Outcome. purpose is "read",
    +         # "list" (the vehicle list), "command", "wake" or "energy" (the Wall
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +             self._refuseWallConnectors(slot, status)
    +             return Outcome(REFUSED, str(status))
    +         label = slot.kind.capitalize()
    ++        if status == 401 and sent is not None and slot.changes != sent:
    ++            # Another thread refreshed, replaced or cleared the token (sent:
    ++            # slot.changes when the request went out) while the request was
    ++            # out: the 401 was for the old one, so the new one is sent once,
    ++            # and a cleared slot sends nothing
    ++            return _REFRESHED if slot.accessToken else Outcome(REFUSED, "401")
    +         if status == 401:
    +             if (
    +                 refresh
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +             # Retrying a bad token might make Tesla block remote access to
    +             # the car: nothing more is sent with it until the user supplies
    +             # fresh tokens
    ++            if not slot.clear(sent):
    ++                # Changed since the check above: not the token refused
    ++                return _REFRESHED if slot.accessToken else Outcome(REFUSED, "401")
    +             logger.error(
    +                 "Tesla %s API token was rejected (HTTP 401); removing it." % label
    +             )
    +-            slot.clear()
    +             self.master.queue_background_task({"cmd": "saveSettings"})
    +             return Outcome(REFUSED, "401")
    +         if owner:
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         if self.syncedSlotLocked(slot):
    +             self.logSyncedSlotLocked(slot)
    +             return "token_sync"
    +-        with slot.lock:
    +-            return self._pasteRefreshTokenLocked(slot, token)
    +-
    +-    def _pasteRefreshTokenLocked(self, slot, token):
    +         previous = slot.snapshot()
    +         previousErrors = (self.carApiLastErrorTime, self.errorCount)
    +         slot.clear()
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         slot = self.slotOfType(kind)
    +         if slot is None:
    +             return False
    +-        with slot.lock:
    +-            slot.clear()
    ++        slot.clear()
    +         self.master.queue_background_task({"cmd": "saveSettings"})
    +         return True
    + 
    +@@ lib/TWCManager/Vehicle/TeslaAPI.py: class TeslaAPI:
    +         if source != "synced" and self.syncedSlotLocked(slot):
    +             self.logSyncedSlotLocked(slot)
    +             return "token_sync"
    +-        with slot.lock:
    +-            slot.setTokens(accessToken, refreshToken, expireTime, source)
    ++        slot.setTokens(accessToken, refreshToken, expireTime, source)
    +         return "success"
    + 
    +     def migrateSavedTokens(self, settings, syncConfigured):
    +
      ## lib/TWCManager/Vehicle/TeslaTokenSlot.py ##
     @@
      import json
      import logging
     +import threading
      import time
    +-from threading import RLock
      
      import jwt
    + import requests
     @@ lib/TWCManager/Vehicle/TeslaTokenSlot.py: class TeslaTokenSlot:
              self.source = ""
              self.pausedUntil = 0
              self.changes = 0
    +-        # Tesla refresh tokens are single-use. Held across a refresh and any
    +-        # other change to the tokens, so two threads never spend the same
    +-        # refresh token (#690).
    +-        self.lock = RLock()
     +        # A leaf: setTokens, clear and restore write the slot under it and a
     +        # refresh claims the slot under it, so one refresh token is spent once
     +        self._cond = threading.Condition()
 3:  624e8efb !  3:  1bf6d440 Run the one distributor on a 1 s control tick for every install
    @@ tests/unit/test_control_tick.py (new)
     +    )
     
      ## tests/unit/test_distributor_loop.py ##
    +@@ tests/unit/test_distributor_loop.py: def _evse(max_power, min_power=1200):
    +     e.maxPower = max_power
    +     e.minPower = min_power
    +     e.controllers = ["Gen2TWCs"]
    ++    # Listed as slaves too: no voltage measured, so defaultVoltage applies
    ++    e.voltsPhaseA = e.voltsPhaseB = e.voltsPhaseC = 0
    +     return e
    + 
    + 
     @@ tests/unit/test_distributor_loop.py: def _master(evses, amps):
          m.config = {"config": {"defaultVoltage": 240, "numberOfPhases": 1}}
          ctrl = MagicMock()
 4:  6be7c368 !  4:  fc769e57 Compute TWC offers on the control tick; charging points own car amps
    @@ Commit message
         computes each heard slave's offer (TWCSlave.offerFor) from the
         distributor's target (pointAmps), and send_master_heartbeat sends it, or
         "no change" before the first pass. The positive-offer stop cancel runs
    -    in controlPass, skipped during the chargeStopMode-2 silence.
    +    in controlPass. During the chargeStopMode-2 silence no reply arrives, so
    +    the offers, their change times and the status they publish hold, and no
    +    stop is cancelled.
     
         ChargingPoint writes car amps for every Gen2 point: car members through
         their endpoints; else the TWC's named car or its anonymous fan-out,
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
     -            self._points = self.distributeEVSEPower()
     +        now = time.time() if now is None else now
     +        points = self.distributeEVSEPower() if distribute else self.chargingPoints()
    ++        # chargeStopMode 2 silences the heartbeat, and with it the replies:
    ++        # the offers hold and no stop is cancelled
    ++        if (
    ++            self.settings.get("respondToSlaves", 1) == 0
    ++            and self.settings.get("respondToSlavesExpiry", now) > now
    ++        ):
    ++            return
     +        ctx = OfferContext(
     +            self.getMaxAmpsToDivideAmongSlaves(),
     +            self.num_cars_charging_now(),
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
     +                if hasattr(e, "pointAmps")
     +            },
     +        )
    -+        # chargeStopMode 2 silences the heartbeat, and with it the replies
    -+        silent = (
    -+            self.settings.get("respondToSlaves", 1) == 0
    -+            and self.settings.get("respondToSlavesExpiry", now) > now
    -+        )
     +        for slave in self.getSlaveTWCs():
     +            if not slave.heardFrom:
     +                # Not heard from yet: no offer, so its heartbeat says nothing
     +                continue
     +            slave.offer = slave.offerFor(slave.pointAmps, ctx, now)
     +            key = slave.vehicleKey
    -+            if key is not None and slave.offer.amps > 0 and not silent:
    ++            if key is not None and slave.offer.amps > 0:
     +                # Power is on offer: a stop not yet delivered is moot
     +                self.cancelStopCarsCharging(key)
      
    @@ tests/unit/test_control_tick.py: def test_the_serial_loop_no_longer_distributes_
     +    m.settings["respondToSlaves"] = 0
     +    m.settings["respondToSlavesExpiry"] = time.time() + 60
     +    m.controlPass()
    -+    assert s.offer.amps == 32 and not m.cancelStopCarsCharging.called
    ++    assert s.offer is None and not m.cancelStopCarsCharging.called
     +    m.settings["respondToSlavesExpiry"] = time.time() - 1
     +    m.controlPass()
    ++    assert s.offer.amps == 32
     +    m.cancelStopCarsCharging.assert_called_once_with(VIN)
     +
     +
    ++def test_offers_and_their_status_hold_during_the_mode_2_silence():
    ++    m = pureGen2(feed=40, slaves=1)
    ++    status = Mock()
    ++    m.registerModule({"name": "Status", "ref": status, "type": "Status"})
    ++    (s,) = m.getSlaveTWCs()
    ++    m.controlPass(now=1000)
    ++    held = (s.offer, s.lastAmpsOffered, s.timeLastAmpsOfferedChanged)
    ++    status.reset_mock()
    ++    m.settings["respondToSlaves"] = 0
    ++    m.settings["respondToSlavesExpiry"] = 2000
    ++    m.getMaxAmpsToDivideAmongSlaves = lambda: 10
    ++    m.controlPass(now=1010)
    ++    assert (s.offer, s.lastAmpsOffered, s.timeLastAmpsOfferedChanged) == held
    ++    assert not status.setStatus.called
    ++
    ++
     +def test_wiring_cap_is_rechecked_when_others_draw_more():  # (e)
     +    m = pureGen2(feed=40, config={"wiringMaxAmpsAllTWCs": 48})
     +    s, other = m.getSlaveTWCs()
    @@ tests/unit/test_control_tick.py: def test_the_serial_loop_no_longer_distributes_
     +        m.controlPass()
     +        assert s.offer.amps > 0 and m.desired.keys() == [] and not s.vehicleRateRaised
     
    + ## tests/unit/test_distributor_voltage.py ##
    +@@ tests/unit/test_distributor_voltage.py: def test_policy_amps_reach_the_twc_unchanged():
    +     e = _evse()
    +     e.setTargetPower.side_effect = twc.setTargetPower
    +     _master([e], 16, [twc], THREE_PHASE_400).distributeEVSEPower()
    +-    assert twc._evseTargetAmps == 16
    ++    assert twc.pointAmps == 16
    +
      ## tests/unit/test_gen2_idle_minimum.py ##
     @@ tests/unit/test_gen2_idle_minimum.py: def real(minAmps, ranges=None, feed=40):
      
 5:  3b9cfddc =  5:  19a4c217 Plan a car's charge rate before its start command
 6:  10132681 !  6:  d68fe513 Decide TWC start and stop on the control tick
    @@ Commit message
     
      ## lib/TWCManager/TWCMaster.py ##
     @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
    -                 if hasattr(e, "pointAmps")
    -             },
    -         )
    --        # chargeStopMode 2 silences the heartbeat, and with it the replies
    -+        # chargeStopMode 2 silences the heartbeat, and with it the replies:
    -+        # no stop is cancelled and no gate runs then
    -         silent = (
    +         now = time.time() if now is None else now
    +         points = self.distributeEVSEPower() if distribute else self.chargingPoints()
    +         # chargeStopMode 2 silences the heartbeat, and with it the replies:
    +-        # the offers hold and no stop is cancelled
    ++        # the offers hold, no stop is cancelled and no gate runs
    +         if (
                  self.settings.get("respondToSlaves", 1) == 0
                  and self.settings.get("respondToSlavesExpiry", now) > now
     @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
    -                 continue
    -             slave.offer = slave.offerFor(slave.pointAmps, ctx, now)
    -             key = slave.vehicleKey
    --            if key is not None and slave.offer.amps > 0 and not silent:
    -+            if silent:
    -+                continue
    -+            if key is not None and slave.offer.amps > 0:
    +             if key is not None and slave.offer.amps > 0:
                      # Power is on offer: a stop not yet delivered is moot
                      self.cancelStopCarsCharging(key)
     +            gate = slave.chargeGate(now)
    @@ tests/unit/test_offer_characterization.py: def test_a_twc_point_never_clears_a_v
     +def test_no_gate_runs_during_the_mode_2_silence():
     +    m = master(feed=3)
     +    s = gated(m, actual=10.0)
    ++    beat(m, s)
    ++    assert calls(m) == [("cancelStopCarsCharging", VIN)]  # the offer just changed
     +    m.settings["respondToSlaves"] = 0
     +    m.settings["respondToSlavesExpiry"] = time.time() + 60
    -+    tickThenBeat(m, s, 0x01, 40, 10.0)
     +    age(s, offered=61, amps=61)
     +    tickThenBeat(m, s, 0x01, 40, 10.0)
     +    assert calls(m) == []  # silent TWCs are not started or stopped
 7:  fa4571de !  7:  1c5beef8 Collapse the EVSE scaffolding the second allocator needed; guard the retired names
    @@ lib/TWCManager/EVSEInstance/Gen2TWC.py: class Gen2TWC(EVSEInstance, TWCSlave):
          def currentVoltage(self) -> list:
              """Per-phase voltages [A, B, C].  Falls back to configured default when
     @@ lib/TWCManager/EVSEInstance/Gen2TWC.py: class Gen2TWC(EVSEInstance, TWCSlave):
    -             phases[0] = default_v
    +             phases = [default_v if i < count else 0 for i in range(3)]
              return phases
      
     -    @property
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
          def chargingPoints(self) -> list:
     -        """Every endpoint grouped into charging points by the car it serves."""
     -        from TWCManager.EVSEInstance.ChargingPoint import groupEndpoints
    +-
    +-        return groupEndpoints(self, self.getAllEVSEs())
     +        # Every endpoint, grouped by the car it serves. A slave that has not
     +        # replied yet reports nothing (00, 0 A), so it is offered nothing
     +        gen3 = self.getModuleByName("Gen3TWCs")
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
     +            + (gen3.allEVSEs if gen3 else [])
     +        )
     +        return groupEndpoints(self, endpoints)
    - 
    --        return groupEndpoints(self, self.getAllEVSEs())
    ++
     +    def _budgets(self) -> dict:
     +        # Watts each group of endpoints may draw in all: the wiring for the
     +        # Gen2 slaves, the fuses for the Gen3 units; each car limits itself
    ++        # The wiring's amps convert at the voltage the TWCs measure, as the
    ++        # policy's amps do, so the two caps never disagree
     +        cfg = self.config["config"]
     +        budgets = {
    -+            "Gen2TWCs": cfg.get("wiringMaxAmpsAllTWCs", 6)
    -+            * cfg.get("defaultVoltage", 240)
    -+            * cfg.get("numberOfPhases", 1),
    ++            "Gen2TWCs": self.convertAmpsToWatts(cfg.get("wiringMaxAmpsAllTWCs", 6)),
     +            "VehicleEndpoints": float("inf"),
     +        }
     +        gen3 = self.getModuleByName("Gen3TWCs")
    @@ tests/unit/test_charging_points.py: def test_correlated_gen3_car_joins_the_gen3_
          m = real(); s = m.newSlave(b"\x82\x44", 80); car(m, VIN, "Stopped"); budget(m, 40)
          assert s.vehicleKey is None and [p.ID for p in m.chargingPoints()] == ["Point-Gen2TWC-8244", "Point-" + VIN]
          m.distributeEVSEPower()
    +@@ tests/unit/test_charging_points.py: def asleepUnderSixAmps(m, twcVolts, carMax=None):
    + 
    + def test_a_car_read_under_the_sleep_pilot_still_gets_the_share():
    +     m = real(); s = asleepUnderSixAmps(m, 243)
    +-    m.distributeEVSEPower(); assert s.pointAmps == pytest.approx(48 * 240 / 243)
    ++    m.distributeEVSEPower(); assert s.pointAmps == pytest.approx(48)
    +     m.vehicleRegistry.get(VIN).observe("chargeCurrentRequestMax", 32, "TeslaBLE")    # the car's own maximum binds
    +     m.distributeEVSEPower(); assert s.pointAmps == pytest.approx(32)
    + 
     
      ## tests/unit/test_control_tick.py ##
     @@
    @@ tests/unit/test_control_tick.py: def test_no_gate_acts_before_the_first_offer():
     
      ## tests/unit/test_distributor_loop.py ##
     @@ tests/unit/test_distributor_loop.py: def _evse(max_power, min_power=1200):
    +     e.maxPower = max_power
    +     e.minPower = min_power
    +     e.controllers = ["Gen2TWCs"]
    +-    # Listed as slaves too: no voltage measured, so defaultVoltage applies
    +-    e.voltsPhaseA = e.voltsPhaseB = e.voltsPhaseC = 0
    +     return e
    + 
      
      def _master(evses, amps):
          m = TWCMaster.__new__(TWCMaster)
    @@ tests/unit/test_distributor_loop.py: def _evse(max_power, min_power=1200):
          m.getMaxAmpsToDivideAmongSlaves = lambda: amps
          return m
     
    + ## tests/unit/test_distributor_voltage.py ##
    +@@ tests/unit/test_distributor_voltage.py: def _twc(volts):
    + 
    + def _master(evses, amps, slaves, config):
    +     m = TWCMaster.__new__(TWCMaster)
    +-    m.config = {"config": config}
    ++    m.config = {"config": dict(config, wiringMaxAmpsAllTWCs=80)}
    +     ctrl = MagicMock()
    +     ctrl.maxPower = 100000
    +     # A non-Gen2 controller makes the distributor run.
    +
      ## tests/unit/test_gen2_idle_minimum.py ##
     @@
      from types import SimpleNamespace
    @@ tests/unit/test_telemetry_registry.py: def test_sleeping_car_on_healthy_feed_sta
          tm.mqttDisconnect(None, None, None, 7)  # broker gone
          assert v.syncSource == "TeslaAPI"
     
    + ## tests/unit/test_teslaapi_evse_unplugged.py ##
    +@@ tests/unit/test_teslaapi_evse_unplugged.py: def test_null_voltage_falls_back_to_default():
    +     assert endpoint().currentVoltage == [230, 230, 230]
    + 
    + 
    +-def test_null_actual_current_reads_as_zero():
    +-    e = endpoint()
    +-    assert e.currentAmps == 0
    +-    assert e.currentPower == 0
    ++def test_null_actual_current_is_no_reading():
    ++    from TWCManager.Vehicle.Reconcile.Belief import _newer
    ++
    ++    assert _newer(endpoint().vehicle, "actualCurrent", float("-inf")) == []
    + 
    + 
    + def test_power_limits_for_unplugged_car():
    +@@ tests/unit/test_teslaapi_evse_unplugged.py: def test_implausibly_low_voltage_still_falls_back(voltage):
    + def test_reported_voltage_is_used_while_charging():
    +     e = endpoint(chargingState="Charging", voltage=240, phases=1, actualCurrent=10)
    +     assert e.currentVoltage == [240, 0, 0]
    +-    assert e.currentPower == 10 * 240
    +
      ## tests/unit/test_teslaapi_readonly_gate.py ##
     @@ tests/unit/test_teslaapi_readonly_gate.py: class TestVehicleEndpointPerCar:
              master.config = {"config": {}}
 8:  b8d9fbcd =  8:  ac021326 Keep one copy of the settings defaults
 9:  e3f63f99 !  9:  b54a2dee Make comments say why, not where they came from
    @@ lib/TWCManager/Control/HTTPControl.py: def _vehicleRecordKey(vehicles, vin):
          if not isinstance(vin, str) or not isWellFormedVIN(vin):
              return False
          vehicle = master.vehicleRegistry.get(vin)
    +@@ lib/TWCManager/Control/HTTPControl.py: class ThreadingSimpleServerIPv4(ThreadingMixIn, HTTPServer):
    + 
    + def createServer(port, handler):
    +     # Listen on IPv6 (which also accepts IPv4 on a dual-stack host), falling
    +-    # back to IPv4 only on a host with IPv6 disabled (#721). Any other error,
    ++    # back to IPv4 only on a host with IPv6 disabled. Any other error,
    +     # such as the port being in use, is raised to the caller.
    +     try:
    +         return ThreadingSimpleServer(("::", port), handler)
     @@ lib/TWCManager/Control/HTTPControl.py: def CreateHTTPHandlerClass(master):
                                  self.getFieldValue(key)
                              )
10:  761b86d6 = 10:  94a32ab3 Run the serial loop and shutdown only when an interface is loaded
11:  0c060f13 ! 11:  fc4d6110 Withdraw offers when the control pass keeps failing
    @@ tests/unit/test_control_tick.py: def test_no_offer_or_cancel_for_an_unheard_slav
          m = pureGen2(feed=40, slaves=0)
          m.cancelStopCarsCharging = Mock()
          s = charging(m, actual=10.0)
    -@@ tests/unit/test_control_tick.py: def test_no_stop_cancel_during_the_mode_2_silence():  # F7
    -     m.cancelStopCarsCharging.assert_called_once_with(VIN)
    +@@ tests/unit/test_control_tick.py: def test_offers_and_their_status_hold_during_the_mode_2_silence():
    +     assert not status.setStatus.called
      
      
     -def test_wiring_cap_is_rechecked_when_others_draw_more():  # (e)
12:  9cd4ec10 = 12:  a887b6e5 Drop the empty Advanced Settings section from the debug page
13:  d91c1a31 = 13:  803f787c Stop the solar export example recommending flex charging
14:  38867464 <  -:  -------- Hold the offers during the chargeStopMode 2 silence
15:  f1e98620 ! 14:  8566063a Keep running when the Gen2 RS-485 adapter is absent
    @@ CHANGELOG.md: This document logs the changes per release of TWCManager.
          * (@MikeBishop) - A charge limit is only changed when its current value is known (from any source); TeslaBLE no longer sets a limit it could not read
          * (@MikeBishop) - A targeted start, stop or charge limit sent through Home Assistant now affects only the named car; a command for every car still reaches every Home Assistant car
     +    * (@MikeBishop) - A Gen2 RS-485 adapter that is missing or can't be opened no longer stops TWCManager from starting: the Gen2 link logs one error and retries every 30 seconds, so a Gen3-only or vehicle-only install needs no interface change, and a late USB adapter is picked up without a restart. The Gen2 link is not opened on the Gen3 controller's port
    -     * Fix: Add missing module-level time import in HASS, EmonCMS, Growatt, IotaWatt, SmartMe and TCP modules, which crashed EMS polling and caused charge current oscillation (closes #644)
    -     * Fix: Restore minInterval parameter on update_location, fixing TypeError that broke API start/stop charging and home location correction
    -     * Fix: Correct invalid logging level in update_vehicle_data error handler which crashed when logging a failed API response
    + 
    + ## v1.4.0 - 2026-10-26
    + 
     
      ## docs/modules/Controller_Gen3TWCs.md ##
     @@ docs/modules/Controller_Gen3TWCs.md: For background on the Gen3 and why this approach is necessary, see

