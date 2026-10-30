ef7be20f Offer power to a plugged-in car that a pending raise would start
 CHANGELOG.md                                   |   1 +
 lib/TWCManager/EVSEInstance/ChargingPoint.py   |  23 +++-
 lib/TWCManager/EVSEInstance/Gen2TWC.py         |   4 +
 lib/TWCManager/EVSEInstance/VehicleEndpoint.py |   8 +-
 lib/TWCManager/Vehicle/Reconcile/Belief.py     |  27 +++-
 tests/unit/test_charging_points.py             |  11 +-
 tests/unit/test_sleep_pilot_replay.py          |   3 +-
 tests/unit/test_wants_power.py                 | 179 +++++++++++++++++++++++++
 8 files changed, 235 insertions(+), 21 deletions(-)
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 1cb54dc4..653c1a6a 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -25,24 +25,25 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - One vehicle registry keyed by VIN holds every per-vehicle field with its source and age; reads cascade BLE then cloud and never wake a car unless asked; a TWC-reported VIN is confirmed by a second query before a vehicle is created; vehicles unseen for 30 days (config vehicle.forgetAfterDays) are forgotten
     * (@MikeBishop) - The debug API `/api/sendTeslaAPICommand` now takes the vehicle's VIN (`vehicleVIN`) instead of the numeric vehicle ID (`vehicleID`); the web UI and debug dump read vehicles from the registry
     * (@MikeBishop) - A providerSuppressions entry for HomeAssistant now also drops Home Assistant vehicle reads, not only its commands
     * (@MikeBishop) - Vehicle channels are providers that declare capabilities with per-operation cost and locality; commands walk a fixed order (TWC, BLE, then cloud; billed last) with per-provider suppressions (settings providerSuppressions); commandPolicy maps onto them; HomeAssistant, when loaded, joins the command order last (after Fleet) and is suppressed under ble_only; the debug API goes through the same order
     * (@MikeBishop) - Charging endpoints (a TWC, or a car whose amps BLE, Fleet or HomeAssistant can set) are grouped into charging points by the car they serve, so a car that stops charging on its TWC gets no second power share or Fleet charge-rate commands. The distributor allocates per point, an idle TWC counts nothing against the budget, and a car's amps are queued to the vehicle worker instead of being sent to the Fleet API from the RS-485 loop
     * (@MikeBishop) - The power distributor never has the Fleet API set a car's amps where a TWC or BLE can (Charge Rate Control modes 2 and 3 still may). A BLE-paired car on a mobile connector gets its rate over BLE only, with no Fleet fallback. Home Assistant can now set a car's amps; it is treated as billed and tried only after the Fleet API
     * (@MikeBishop) - Settings page labels say "vehicle command (BLE or API)" and "local"/"cloud" where they said "Tesla API"; the stored values are unchanged
     * (@MikeBishop) - Held charge limits in settings `chargeLimits` are keyed by VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them. After a downgrade, only 1.3.x's TeslaBLE path reads the VIN-keyed entries; its Tesla API path, keyed by numeric ID, starts over
     * (@MikeBishop) - Vehicle commands are no longer fired at a car: policy, the power distributor and the TWC heartbeat set the charge limit, charging on/off and amps each car should have, and one reconciler delivers them through the provider order with one attempt in flight per car, classified outcomes and backoff; a pending stop is cancelled when charging is wanted again. A paid-tier provider (Fleet API, Home Assistant, the Owner API for a car listed with `command_signing: off`) is used at once when no free one can serve the car, else only after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps). It sends a desired value once, and once more after a failure, or after a reading shows the command reached the car. If no send reached the car, a reading from the car or a pending start allows two more. That is at most four commands per desired value; each may be preceded by a wake and a vehicle_data read. A start waits for that car's limit change unless the limit cannot be delivered. A charge limit changed in the car or the Tesla app is adopted, not undone, until the next policy decision. Removes VehiclePriority, the per-VIN vehicle command dispatch and the per-module charge-limit copies
     * (@MikeBishop) - TeslaBLE no longer retries internally or opens a circuit breaker; `maxRetries`, `retryDelay` and `circuitBreaker*` are ignored. A command that times out or fails to connect is retried once, two seconds later; the reconciler decides any later retry or cloud fallback
     * (@MikeBishop) - Held charge limits saved under a numeric Tesla vehicle ID that no Tesla account lists are dropped with one warning, once a vehicle list has come back
 * Bugfixes
+    * (@MikeBishop) - A plugged-in car asleep at its old charge limit is offered power, woken and started when a policy raises its limit, on a Gen2 or Gen3 TWC or on a charging station TWCManager doesn't control. A car at its limit with no raise pending, or that has finished charging, is no longer given a share of the power other cars could use
     * (@MikeBishop) - When TWCManager shares power with Tesla API cars, the distributor gives an idle TWC a target of 0 and counts nothing against the budget. On the wire the TWC is offered 0 when no car is charging (a Gen2 treats 0 as its hardware minimum), and its hardware minimum (usually 6 A) when another car is charging and there is at least minAmpsPerTWC of power per car, so it still sees a car plug in. Brief overshoot is fine: the configured limit is already the 80% continuous rating and the next cycle rebalances
     * (@MikeBishop) - A car read while its TWC held the 6 A pilot it keeps for a sleeping car is no longer capped at 6 A (or offered nothing, when the TWC measured above 240 V), which left it uncharged and unwoken overnight. A car's limit is its own maximum charge current (from BLE, the Tesla API or TeslaMate, else `wiringMaxAmpsPerTWC`), never the pilot it last saw, and a raise to the wiring maximum still reaches a car whose own maximum is lower. A plugged-in car whose charging point refuses power that is there is logged at INFO (`<point>: <VIN> is plugged in, but its limits leave it none of <n> W`), at most hourly
     * (@MikeBishop) - A targeted start, stop or charge limit sent through Home Assistant now affects only the named car; a command for every car still reaches every Home Assistant car
     * (@MikeBishop) - A Gen2 RS-485 adapter that is missing or can't be opened no longer stops TWCManager from starting: the Gen2 link logs one error and retries every 30 seconds, so a Gen3-only or vehicle-only install needs no interface change, and a late USB adapter is picked up without a restart. The Gen2 link is not opened on the Gen3 controller's port
     * (@MikeBishop) - Presence follows events as they arrive (plug-ins, unplugs, positions, drive starts, BLE contact) and needs no paid read: a car is Home, Away or Probably home, probably-home cars are counted in `numCarsAtHome` and `minBatteryLevelAtHome`, a Home Assistant zone state of home with no coordinates no longer places a car, and a charge limit, start or rate for a car waits until it is plugged in or confirmed home. A TWC's own commands are never held back
     * (@MikeBishop) - A policy with no limit (-1) releases the car to its own limit and is applied like any limit; a departing car's original limit is restored wherever it is. A car is woken only when it is expected to charge once everything wanted is applied (plugged in or arriving, no stop wanted, its TWC or charger offered power, and its limit above its battery level; an unknown limit or battery level counts as charging), and after a start not before TeslaMate or Fleet Telemetry has reported once (or 60 seconds have passed), whatever the direction of the change; a car expected to stay idle gets changes only when it is awake anyway. Restores on departure and stops never wake
     * (@MikeBishop) - A plug-in with no VIN from a Gen2 or Gen3 TWC is matched to the one car that can be there (plugged in just now, BLE-read at that pilot and draw, or BLE-reached) and left unnamed when several could be; on a Gen2 that reads VINs, the VIN read replaces the match; the match never BLE-reads a car known asleep; a Gen2's match runs on the BLE worker, and a Gen3's vitals never read BLE. An unnamed TWC's rate now goes only to cars plugged in here, no longer to the first car; a status 00 alone no longer opens an unnamed session, and a Gen2 plug counts only while the TWC reports one. A car charging away from a TWC with no telemetry feed is not watched for its departure (a separate feature is planned); the 5, 20 and 45 minute reads after a TWC's power drops are gone
     * (@MikeBishop) - Removed the `/api/checkArrival` and `/api/checkDeparture` hint endpoints (they now return 404); presence no longer needs them
     * (@MikeBishop) - A guest car on the same TWC can keep a car that left idle counted as home until that car reports a position outside the radius or starts driving; a VIN a TWC rejected during a charge session stays rejected until the unplug
     * (@MikeBishop) - A Tesla API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
     * (@MikeBishop) - With `subtractChargerLoad`, the charger load taken out of the house's consumption now includes Gen3 Wall Connectors and cars charging at home on chargers no TWC reports (watched, or reported by a telemetry feed), not only Gen2 TWCs; a green policy no longer counts a car's own draw as house load and shrinks its offer
     * (@MikeBishop) - The charge history API (`/api/getHistory`) records the same charger load, so it covers Gen3 Wall Connectors and cars on other chargers and works with no Gen2 TWC; it is sampled once a second on the control tick, not on each Gen2 heartbeat
diff --git a/lib/TWCManager/EVSEInstance/ChargingPoint.py b/lib/TWCManager/EVSEInstance/ChargingPoint.py
index 87946620..4c2a022b 100644
--- a/lib/TWCManager/EVSEInstance/ChargingPoint.py
+++ b/lib/TWCManager/EVSEInstance/ChargingPoint.py
@@ -2,25 +2,25 @@
 A charging point: the endpoints that serve one car, grouped by vehicle key,
 so the distributor budgets the car once however many endpoints see it. A
 Gen2 TWC splits the rate with its car by chargeRateControl; any other local
 member (a Gen3 unit, whose target feeds one shared headroom) carries the
 whole target.
 """
 
 from typing import List, Tuple
 
 from TWCManager.EVSEInstance.EVSEInstance import EVSEInstance
 from TWCManager.Vehicle.Presence import candidates, pluggedHere
 from TWCManager.Vehicle.Providers.Capability import SET_AMPS
-from TWCManager.Vehicle.Reconcile.Belief import known
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known, whyQuiet
 from TWCManager.Vehicle.Reconcile.Desired import AMPS
 from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Registry.VehicleRegistry import canonicalKey, isAnonKey
 
 
 class ChargingPoint(EVSEInstance):
     # The cars setTargetPower rated this pass; finding them may scan them all
     carKeys = None
 
     def __init__(self, master, key: str, endpoints: List[EVSEInstance]):
         self.master = master
         self.key = key
@@ -35,27 +35,34 @@ class ChargingPoint(EVSEInstance):
         return [e for e in self.endpoints if not e.isLocal]
 
     @property
     def ID(self) -> str:
         return "Point-" + self.key
 
     @property
     def isReadOnly(self) -> bool:
         return all(e.isReadOnly for e in self.endpoints)
 
     @property
     def wantsToCharge(self) -> bool:
-        # The TWC's own report decides when there is one: the registry's
-        # chargingState can be stale for a car that has finished
-        return any(e.wantsToCharge for e in self.localEndpoints or self.endpoints)
+        # Power flowing, or a car that would take it once the desires being
+        # applied land: asleep at its old limit, a raise wakes it only if
+        # power is offered. A point that can't name its car has its members'
+        members = self.localEndpoints or self.endpoints
+        if any(_drawing(e) for e in members):
+            return True
+        v = self.master.vehicleRegistry.get(self.key)
+        if v is None or v.isAnonymous:
+            return any(e.wantsToCharge for e in members)
+        return whyQuiet(self.master, v, budgeting=True) is None
 
     @property
     def currentVoltage(self) -> list:
         consider = self.localEndpoints or self.endpoints
         columns = list(zip(*[e.currentVoltage for e in consider]))
         if not columns:
             return [0, 0, 0]
         return [sum(col) / len(col) for col in columns]
 
     def _atPointVoltage(self, limit, pick) -> float:
         # Members are compared in amps and priced at the point's voltage.
         # Each prices itself at its own: a TWC at what it measures, a car
@@ -185,24 +192,32 @@ class ChargingPoint(EVSEInstance):
         )
         for e in cars:
             e.setTargetPower(watts)
         own(amps, "heartbeat")
 
     @staticmethod
     def _caps(member, amps) -> bool:
         # The car's own request is known to sit below the offer
         k = member.requestedAmps()
         return k is not None and k < int(amps)
 
 
+def _drawing(member) -> bool:
+    # A TWC's measured current; a car member has only its charging state
+    amps = getattr(member, "currentAmps", None)
+    if amps is None:
+        return member.wantsToCharge
+    return amps >= POWER_FLOWING_AMPS
+
+
 def groupEndpoints(master, endpoints: List[EVSEInstance]) -> List[ChargingPoint]:
     """Group endpoints that serve the same car into one charging point.
 
     Endpoints sharing a vehicleKey form one point keyed by it; an endpoint
     with no vehicleKey is its own point keyed by its ID. Points keep the
     order of their first endpoint.
 
     A point holds at most one local endpoint: every local member gets the
     whole target, so a second TWC claiming the same car (a stale VIN read)
     is its own point keyed by its ID and budgeted separately.
     """
     groups = {}
diff --git a/lib/TWCManager/EVSEInstance/Gen2TWC.py b/lib/TWCManager/EVSEInstance/Gen2TWC.py
index 7466d542..d11dc90d 100644
--- a/lib/TWCManager/EVSEInstance/Gen2TWC.py
+++ b/lib/TWCManager/EVSEInstance/Gen2TWC.py
@@ -68,24 +68,28 @@ class Gen2TWC(EVSEInstance, TWCSlave):
         # A Gen2 reports 00 for a sleeping plugged car, so 00 is not "empty"
         return None
 
     @property
     def wantsToCharge(self) -> bool:
         """True when a vehicle is plugged in and willing to accept power.
 
         TWC heartbeat: reportedAmpsMax is non-zero once the vehicle has
         communicated its maximum charge rate (i.e. it's plugged in and awake).
         """
         return self.reportedAmpsMax > 0 or self.reportedAmpsActual > 0
 
+    @property
+    def currentAmps(self) -> float:
+        return self.reportedAmpsActual
+
     @property
     def currentVoltage(self) -> list:
         """Per-phase voltages [A, B, C].  Falls back to configured default when
         the TWC has not yet reported voltage measurements."""
         phases = [self.voltsPhaseA, self.voltsPhaseB, self.voltsPhaseC]
         if not any(phases):
             default_v = self.configConfig.get("defaultVoltage", 240)
             count = self.configConfig.get("numberOfPhases", 1)
             phases = [default_v if i < count else 0 for i in range(3)]
         return phases
 
     def _rangeOverride(self, key):
diff --git a/lib/TWCManager/EVSEInstance/VehicleEndpoint.py b/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
index 90ab3437..494b4eb5 100644
--- a/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
+++ b/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
@@ -1,27 +1,27 @@
 """
 A registry vehicle whose charge rate a vehicle provider sets, as a charging
 endpoint. It reads only the registry's latest values and never calls a
 provider: the distributor runs on the control tick, which must not wait on a
 car, so a rate is desired state that the reconciler delivers.
 """
 
 from typing import List, Tuple
 
 from TWCManager.EVSEInstance.EVSEInstance import EVSEInstance
-from TWCManager.Vehicle.Presence import asleep, pluggedHere, telemetryPlug
+from TWCManager.Vehicle.Presence import pluggedHere, telemetryPlug
 from TWCManager.Vehicle.Providers.Capability import SET_AMPS
 from TWCManager.Vehicle.Providers.Provider import vehicleMaxAmps
 from TWCManager.Vehicle.Reconcile.Desired import AMPS
-from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, finished, known
 from TWCManager.Vehicle.Registry.VehicleRegistry import isAnonKey
 
 
 class VehicleEndpoint(EVSEInstance):
     # Tesla vehicles accept as low as 5 A (car-side minimum)
     MIN_AMPS = 5
     isLocal = False
     controllers = ["VehicleEndpoints"]
 
     def __init__(self, vehicle, order, master):
         self.vehicle = vehicle
         self.order = order
@@ -38,27 +38,25 @@ class VehicleEndpoint(EVSEInstance):
     @property
     def isReadOnly(self) -> bool:
         # No provider can set this car's amps (an Owner-only token on a car
         # that needs signed commands, ble_only without BLE), so the
         # distributor must not budget power for it
         return not self._candidates()
 
     @property
     def wantsToCharge(self) -> bool:
         # "Stopped" is a paused session: the car takes power if offered, and a
         # start is allowed to wake it. Asleep after "Charging" it has finished
         state = self.vehicle.value("chargingState")
-        return state in ("Charging", "Stopped") and not (
-            state == "Charging" and asleep(self.vehicle) is True
-        )
+        return state in ("Charging", "Stopped") and not finished(self.vehicle)
 
     @property
     def currentVoltage(self) -> list:
         """Per-phase voltage [A, B, C].
 
         Falls back to the configured default when the car reports an
         implausibly low value (< 90 V), as it does asleep or before its first
         charge-state read.
         """
         voltage = self.vehicle.value("voltage", 0) or 0
         if voltage < 90:
             voltage = self.configConfig.get("defaultVoltage", 240)
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 48e0fd6e..01dcd791 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -1,19 +1,19 @@
 # What the reconciler believes about a car, and the per-aspect rules it
 # plans by: pure functions of the registry, no reconciler state. The EVSE
 # layer reads known() from here without the reconciler thread.
 from typing import Optional
 
 from ..Registry.Fields import FEED_LAG
-from ..Presence import NOT_HOME, pluggedNow, presence
+from ..Presence import NOT_HOME, asleep, pluggedNow, presence
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
 from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
 
 # Sources whose every reading came from the car itself. Exact source
 # names; Fleet Telemetry always counts
 LIVE_READ_SOURCES = frozenset(
     {"TeslaBLE", "OwnerAPI", "FleetAPI", "FleetTelemetryMQTT"}
 )
 # TWC current at or above this means the car is drawing power
 POWER_FLOWING_AMPS = 1.0
 
 
@@ -104,37 +104,50 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
         # The car would refuse the start
         return "battery at its charge limit"
     if known is not None and known.value in ("Disconnected", "NoPower"):
         return "the car cannot charge (%s)" % known.value
     if vehicle.value("scheduledChargingPending") is True and config.get(
         "respectVehicleSchedule", True
     ):
         # A start would override the car's own schedule
         return "scheduled charging is pending (respectVehicleSchedule)"
     return None
 
 
-def whyQuiet(master, vehicle) -> Optional[str]:
+def finished(vehicle) -> bool:
+    # The session ended at the limit believed: "Complete", or asleep after
+    # "Charging"
+    state = known(vehicle, CHARGING)
+    state = state and state.value
+    return state == "Complete" or state == "Charging" and asleep(vehicle) is True
+
+
+def whyQuiet(master, vehicle, budgeting=False) -> Optional[str]:
     # Why the car is expected to quiesce once every pending desire is applied,
-    # or None when it will charge (unknown limit or battery: it will)
+    # or None when it will charge (unknown limit or battery: it will).
+    # budgeting: the distributor asks whether the car would take power, so
+    # its own offer and the stop its gate answered that offer with don't count
     key, desired = vehicle.key, master.desired
     stop, pending = desired.get(key, CHARGING), desired.get(key, CHARGE_LIMIT)
     held = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
-    limit, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
-    limit = limit and limit.value
+    believed, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
+    limit = believed = believed and believed.value
     if pending is not None and not (releases(pending) and not held):
         limit = held.outside if releases(pending) else pending.value
     # Unplugged is known only by a reading
     plugged = pluggedNow(master, vehicle, None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
         return "not plugged in here"
-    if stop is not None and stop.value is False:
+    if not budgeting and stop is not None and stop.value is False:
         return "stop desired"
-    if plugged is not False and getattr(master, "offered", {}).get(key) == 0:
+    if not budgeting and getattr(master, "offered", {}).get(key) == 0:
         return "nothing offered"
     if limit and battery and limit <= battery:
         return "car won't charge: limit at or below battery"
+    if finished(vehicle) and not (limit and (believed is None or limit > believed)):
+        # Only a raise above the limit it finished at starts it again
+        return "car finished charging"
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
     if any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
diff --git a/tests/unit/test_charging_points.py b/tests/unit/test_charging_points.py
index fbdf80b5..1bfe4c6c 100644
--- a/tests/unit/test_charging_points.py
+++ b/tests/unit/test_charging_points.py
@@ -152,29 +152,32 @@ def endpoint(monkeypatch, vin):
     monkeypatch.setattr(VehicleEndpoint, "setTargetPower", spy); return calls
 
 def setAmps(m):
     # The distributor's amps desires (a lift is not a rate)
     return [{"vin": k, "amps": d.value} for k in m.desired.keys() for d in [m.desired.get(k, AMPS)] if d is not None and not d.lift]
 
 def test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum():
     m = real(); s = stoppedTwc(m); car(m, VIN, "Stopped"); budget(m, 40)
     (pt,) = m.chargingPoints()
     assert pt.ID == "Point-" + VIN and [e.ID for e in pt.endpoints] == ["Gen2TWC-8244", "Vehicle-" + VIN]
     assert pt.minPower == s.minPower == 6 * 240
     m.distributeEVSEPower()
-    # The TWC decides: reporting no demand, it gets its idle offer, 0 (the TWC's hardware minimum)...
-    assert s.pointAmps == 0 and setAmps(m) == []
-    s.reportedAmpsActual = 5.5                                                   # ...the paused car takes it...
+    # A paused car with no limit known would take power: the TWC carries the full share
+    assert s.pointAmps == 32 and setAmps(m) == []
+    v = m.vehicleRegistry.get(VIN); v.observe("chargeLimit", 80, "OwnerAPI"); v.observe("batteryLevel", 80, "OwnerAPI")
+    m.distributeEVSEPower()
+    assert s.pointAmps == 0 and setAmps(m) == []                          # at its limit: the idle offer, 0 (the TWC's hardware minimum)...
+    s.reportedAmpsActual = 5.5                                                   # ...yet a car drawing takes the full share
     m.distributeEVSEPower()
-    assert s.pointAmps == 32 and setAmps(m) == []                         # ...and the full share follows
+    assert s.pointAmps == 32 and setAmps(m) == []
 
 def test_lower_case_vin_on_the_twc_groups_with_the_endpoint():
     m = real(); s = stoppedTwc(m, VIN.lower()); car(m, VIN, "Stopped")
     assert [p.ID for p in m.chargingPoints()] == ["Point-" + VIN]
     m.vehicleRegistry.endPlugSession("8244")                                      # the unplug
     s.currentVIN = VIN.lower()
     assert [p.ID for p in m.chargingPoints()] == ["Point-" + VIN]
 
 def test_mode_1_budget_below_the_twc_floor_offers_zero_and_no_fleet_send():
     m = real(mode=1); s = stoppedTwc(m); car(m, VIN, "Stopped"); budget(m, 5)   # 1200 W: the car's 5 A, under the TWC's 6 A
     m.distributeEVSEPower()
     assert s.pointAmps == 0 and setAmps(m) == []
diff --git a/tests/unit/test_sleep_pilot_replay.py b/tests/unit/test_sleep_pilot_replay.py
index 5d8ca9ef..1cbf7f8e 100644
--- a/tests/unit/test_sleep_pilot_replay.py
+++ b/tests/unit/test_sleep_pilot_replay.py
@@ -30,29 +30,30 @@ def test_a_car_read_under_the_sleep_pilot_is_offered_its_share_and_woken(caplog)
         ("chargingState", "Stopped"),
         ("chargeLimit", 50),
         ("batteryLevel", 50),
         ("pluggedIn", True),
     ):
         v.observe(field, value, "TeslaBLE")
     # The car goes back to sleep and the TWC names it at 03 with 6 A
     v.observe("state", "asleep", "TeslaBLE")
     v.observe("twcVin", s.twcid, "TWC")
     s.reportedState, s.reportedAmpsMax = 0x03, 6.0
     # Midnight: Scheduled Charging's 48 A and its 70 % limit
     m.setMaxAmpsToDivideAmongSlaves(48)
+    m.desired.set(VIN, CHARGE_LIMIT, 70, "policy")
     m.controlPass(now=c())
+    # At its old limit, only the raise makes it want power
     assert s.pointAmps == pytest.approx(48)
     assert s.offer.amps == 48 and m.offered[VIN] > 0
     assert m.desired.get(VIN, CHARGING).value is True  # the start
-    m.desired.set(VIN, CHARGE_LIMIT, 70, "policy")
     assert B.whyQuiet(m, v) is None  # the raise may wake the car
     r.pass_()
     assert "setChargeLimit" in cmds(prov(m, "TeslaBLE"))
     assert "TeslaBLE wake for %s before setChargeLimit: done" % VIN in [
         x.getMessage() for x in caplog.records
     ]
 
 
 def test_a_car_left_at_a_lowered_request_is_lifted_above_its_own_maximum():
     # A 32 A car on 48 A wiring: the lift to the wiring maximum still goes
     # to the car, which clamps it to its own 32 A
     m, r, v, c = setup(ble(O.Outcome(O.DONE)), here=False)
diff --git a/tests/unit/test_wants_power.py b/tests/unit/test_wants_power.py
new file mode 100644
index 00000000..10178cd6
--- /dev/null
+++ b/tests/unit/test_wants_power.py
@@ -0,0 +1,179 @@
+# A plugged-in car wants power when it would take it once the desires
+# being applied land, not only while it charges: a car asleep at its old
+# limit is offered power for a raise, so the raise may wake it
+import pytest
+
+from TWCManager.Vehicle.Reconcile import Belief as B
+from TWCManager.Vehicle.Reconcile import Outcome as O
+from TWCManager.Vehicle.Reconcile.Desired import AMPS, CHARGE_LIMIT, CHARGING
+from tests.unit.reconcile_helpers import placeAt
+from tests.unit.test_limit_reconciler import VIN, ble, names, prov, setup
+
+TM = "TeslaMateVehicle"
+
+
+def asleepAtItsLimit(limit=70, twc=False):
+    # The live box: TeslaMate's last word on a car that finished at its
+    # limit and slept, BLE able to set its amps; no TWC unless asked
+    m, r, v, c = setup(*[ble(O.Outcome(O.DONE)) for _ in range(4)], here=False)
+    if not twc:
+        m.slaveTWCs.clear()
+    placeAt(m, v)
+    for field, value in (
+        ("pluggedIn", True),
+        ("chargingState", "Complete"),
+        ("batteryLevel", 70),
+        ("chargeLimit", limit),
+    ):
+        v.observe(field, value, TM)
+    c.t += 10
+    v.observe("state", "asleep", "TeslaBLE")
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    return m, r, v, c
+
+
+def wokeFor(m, r, c, caplog):
+    c.t += 10
+    m.controlPass(now=c())
+    r.pass_()
+    return [
+        x.getMessage().split(" before ")[1].split(":")[0]
+        for x in caplog.records
+        if x.getMessage().startswith("TeslaBLE wake for %s before" % VIN)
+    ]
+
+
+def test_a_car_asleep_at_its_limit_is_offered_power_and_woken_for_a_raise(caplog):
+    caplog.set_level("INFO")
+    m, r, v, c = asleepAtItsLimit()
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    m.controlPass(now=c())
+    assert m.offered[VIN] > 0 and B.whyQuiet(m, v) is None
+    assert m.desired.get(VIN, AMPS) is not None  # its rate, for the start
+    assert wokeFor(m, r, c, caplog)[:1] == ["setChargeLimit"]
+    for _ in range(30):
+        c.t += 10
+        m.controlPass(now=c())
+        r.pass_()
+    # The raise starts a car at its old limit; its rate follows
+    assert names(prov(m, "TeslaBLE")) == ["wake", "setChargeLimit", "wake", "setAmps"]
+    assert prov(m, "TeslaBLE").calls[1][2] == 90
+
+
+def test_a_car_asleep_at_its_limit_with_no_raise_is_offered_nothing():
+    m, r, v, c = asleepAtItsLimit()
+    m.desired.set(VIN, CHARGE_LIMIT, 70, "policy")
+    m.controlPass(now=c())
+    r.pass_()
+    assert m.offered.get(VIN, 0) == 0 and B.whyQuiet(m, v) is not None
+    assert "wake" not in names(prov(m, "TeslaBLE"))
+
+
+def test_a_car_wanted_stopped_is_never_woken(caplog):
+    caplog.set_level("INFO")
+    m, r, v, c = asleepAtItsLimit()
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    m.desired.set(VIN, CHARGING, False, "distributor")
+    assert wokeFor(m, r, c, caplog) == []
+    assert B.whyQuiet(m, v) == "stop desired"
+    assert "wake" not in names(prov(m, "TeslaBLE"))
+
+
+# A Gen2 TWC echoes its last offer: once it was offered nothing it reports
+# no demand until its car draws, which a car asleep at its limit never does
+
+
+def onGen2(m, v, echo=0.0):
+    (s,) = m.getSlaveTWCs()
+    s.protocolVersion, s.heardFrom = 2, True
+    v.observe("twcVin", s.twcid, "TWC")
+    s.reportedState, s.reportedAmpsMax = 0x03, echo
+    return s
+
+
+def test_a_gen2_car_asleep_at_its_limit_is_offered_power_and_woken_for_a_raise(
+    caplog,
+):
+    caplog.set_level("INFO")
+    m, r, v, c = asleepAtItsLimit(twc=True)
+    s = onGen2(m, v)
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    m.controlPass(now=c())
+    assert s.pointAmps > 0 and m.offered[VIN] > 0 and B.whyQuiet(m, v) is None
+    assert m.desired.get(VIN, CHARGING).value is True  # the start
+    assert wokeFor(m, r, c, caplog)[:1] == ["setChargeLimit"]
+
+
+def test_a_gen2_car_at_its_limit_with_no_raise_is_offered_nothing_whatever_the_echo():
+    m, r, v, c = asleepAtItsLimit(twc=True)
+    s = onGen2(m, v, echo=32.0)  # its last offer, from before it finished
+    m.controlPass(now=c())
+    assert s.pointAmps == 0 and m.offered[VIN] == 0
+
+
+def test_a_gen2_car_we_stopped_is_offered_power_again_and_started():
+    m, r, v, c = asleepAtItsLimit(twc=True)
+    v.observe("chargingState", "Stopped", TM)
+    v.observe("chargeLimit", 80, TM)
+    v.observe("state", "online", "TeslaBLE")
+    s = onGen2(m, v)
+    m.desired.set(VIN, CHARGING, False, "distributor")  # when there was no power
+    m.controlPass(now=c())
+    assert s.pointAmps > 0 and s.offer.amps > 0
+    assert m.desired.get(VIN, CHARGING).value is True
+
+
+# A Gen3 unit reports "complete" for a car at its limit
+
+
+def test_a_gen3_car_at_its_limit_is_offered_power_for_a_raise():
+    from tests.unit.test_charging_points import budget, car, real
+    from tests.unit.test_gen3twc_provider import vitals
+
+    m = real(gen3=True)
+    v = car(m, VIN, "Complete")
+    for field, value in (
+        ("pluggedIn", True),
+        ("batteryLevel", 70),
+        ("chargeLimit", 70),
+    ):
+        v.observe(field, value, TM)
+    (u,) = m.modules["Gen3TWCs"]["ref"].devices()
+    vitals(u, True, 0.0, state="complete")
+    assert u.vehicleKey == VIN and not u.wantsToCharge
+    budget(m, 32)
+    m.distributeEVSEPower()
+    assert m.offered[VIN] == 0  # nothing to raise: it won't take power
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    m.distributeEVSEPower()
+    assert m.offered[VIN] > 0 and u.lastTarget > 0 and B.whyQuiet(m, v) is None
+
+
+# A car offered power for a raise shares the budget with a charging car
+# until it is found quiet
+
+
+def test_a_raise_shares_the_budget_until_the_car_is_found_quiet():
+    from tests.unit.test_charging_points import VIN2, budget, car, real, setAmps
+
+    m = real()
+    m.slaveTWCs.clear()
+    a = car(m, VIN, "Charging")
+    b = car(m, VIN2, "Complete")
+    for v, battery, limit in ((a, 50, 90), (b, 70, 70)):
+        for field, value in (
+            ("pluggedIn", True),
+            ("batteryLevel", battery),
+            ("chargeLimit", limit),
+        ):
+            v.observe(field, value, "OwnerAPI")
+    budget(m, 32)
+    m.distributeEVSEPower()
+    assert setAmps(m) == [{"vin": VIN, "amps": 32}]
+    m.desired.set(VIN2, CHARGE_LIMIT, 90, "policy")
+    m.distributeEVSEPower()
+    assert sorted((x["vin"], x["amps"]) for x in setAmps(m)) == [(VIN, 16), (VIN2, 16)]
+    b.observe("chargeLimit", 90, "OwnerAPI")  # the raise landed...
+    b.observe("batteryLevel", 90, "OwnerAPI")  # ...on a car already there
+    m.distributeEVSEPower()
+    assert setAmps(m) == [{"vin": VIN, "amps": 32}]
