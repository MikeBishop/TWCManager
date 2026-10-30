05ca8c4d Admit a car to the budget only on positive evidence it will charge
 CHANGELOG.md                                   |  2 +-
 lib/TWCManager/EVSEInstance/ChargingPoint.py   | 31 +++++----
 lib/TWCManager/EVSEInstance/VehicleEndpoint.py | 18 ++++--
 lib/TWCManager/TWCMaster.py                    | 12 +++-
 lib/TWCManager/Vehicle/Reconcile/Belief.py     | 52 ++++++++++++---
 tests/unit/test_charging_points.py             | 11 ++--
 tests/unit/test_wants_power.py                 | 87 +++++++++++++++++++++++++-
 7 files changed, 169 insertions(+), 44 deletions(-)
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 653c1a6a..11d63103 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -25,25 +25,25 @@ This document logs the changes per release of TWCManager.
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
-    * (@MikeBishop) - A plugged-in car asleep at its old charge limit is offered power, woken and started when a policy raises its limit, on a Gen2 or Gen3 TWC or on a charging station TWCManager doesn't control. A car at its limit with no raise pending, or that has finished charging, is no longer given a share of the power other cars could use
+    * (@MikeBishop) - A plugged-in car asleep at its old charge limit is offered power, woken and started when a policy raises its limit, on a Gen2 or Gen3 TWC or on a charging station TWCManager doesn't control. A car at its limit with no raise pending, one that has finished charging, or one waiting on its own schedule is no longer given a share of the power other cars could use, and a car already charging keeps power too scarce to share
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
index 4c2a022b..1509b789 100644
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
-from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known, whyQuiet
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known, wantsPower
 from TWCManager.Vehicle.Reconcile.Desired import AMPS
 from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Registry.VehicleRegistry import canonicalKey, isAnonKey
 
 
 class ChargingPoint(EVSEInstance):
     # The cars setTargetPower rated this pass; finding them may scan them all
     carKeys = None
 
     def __init__(self, master, key: str, endpoints: List[EVSEInstance]):
         self.master = master
         self.key = key
@@ -33,36 +33,43 @@ class ChargingPoint(EVSEInstance):
     @property
     def vehicleEndpoints(self) -> list:
         return [e for e in self.endpoints if not e.isLocal]
 
     @property
     def ID(self) -> str:
         return "Point-" + self.key
 
     @property
     def isReadOnly(self) -> bool:
         return all(e.isReadOnly for e in self.endpoints)
 
+    @property
+    def drawing(self) -> bool:
+        # Power flowing: a TWC's measured current, or a car member charging
+        members = self.localEndpoints or self.endpoints
+        return any(e.currentAmps >= POWER_FLOWING_AMPS for e in members)
+
     @property
     def wantsToCharge(self) -> bool:
-        # Power flowing, or a car that would take it once the desires being
+        # Power flowing, or the car would take it once the desires being
         # applied land: asleep at its old limit, a raise wakes it only if
-        # power is offered. A point that can't name its car has its members'
-        members = self.localEndpoints or self.endpoints
-        if any(_drawing(e) for e in members):
+        # power is offered. Where the registry can't say, or the point can't
+        # name its car, this falls back to its members' own reports
+        if self.drawing:
             return True
         v = self.master.vehicleRegistry.get(self.key)
-        if v is None or v.isAnonymous:
-            return any(e.wantsToCharge for e in members)
-        return whyQuiet(self.master, v, budgeting=True) is None
+        wants = None if v is None or v.isAnonymous else wantsPower(self.master, v)
+        if wants is not None:
+            return wants
+        return any(e.wantsToCharge for e in self.localEndpoints or self.endpoints)
 
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
@@ -192,32 +199,24 @@ class ChargingPoint(EVSEInstance):
         )
         for e in cars:
             e.setTargetPower(watts)
         own(amps, "heartbeat")
 
     @staticmethod
     def _caps(member, amps) -> bool:
         # The car's own request is known to sit below the offer
         k = member.requestedAmps()
         return k is not None and k < int(amps)
 
 
-def _drawing(member) -> bool:
-    # A TWC's measured current; a car member has only its charging state
-    amps = getattr(member, "currentAmps", None)
-    if amps is None:
-        return member.wantsToCharge
-    return amps >= POWER_FLOWING_AMPS
-
-
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
diff --git a/lib/TWCManager/EVSEInstance/VehicleEndpoint.py b/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
index 494b4eb5..10bdd5d2 100644
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
-from TWCManager.Vehicle.Presence import pluggedHere, telemetryPlug
+from TWCManager.Vehicle.Presence import asleep, pluggedHere, telemetryPlug
 from TWCManager.Vehicle.Providers.Capability import SET_AMPS
 from TWCManager.Vehicle.Providers.Provider import vehicleMaxAmps
 from TWCManager.Vehicle.Reconcile.Desired import AMPS
-from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, finished, known
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known
 from TWCManager.Vehicle.Registry.VehicleRegistry import isAnonKey
 
 
 class VehicleEndpoint(EVSEInstance):
     # Tesla vehicles accept as low as 5 A (car-side minimum)
     MIN_AMPS = 5
     isLocal = False
     controllers = ["VehicleEndpoints"]
 
     def __init__(self, vehicle, order, master):
         self.vehicle = vehicle
         self.order = order
@@ -36,27 +36,35 @@ class VehicleEndpoint(EVSEInstance):
         return self.order.candidates(self.vehicle, SET_AMPS)
 
     @property
     def isReadOnly(self) -> bool:
         # No provider can set this car's amps (an Owner-only token on a car
         # that needs signed commands, ble_only without BLE), so the
         # distributor must not budget power for it
         return not self._candidates()
 
     @property
     def wantsToCharge(self) -> bool:
         # "Stopped" is a paused session: the car takes power if offered, and a
-        # start is allowed to wake it. Asleep after "Charging" it has finished
-        state = self.vehicle.value("chargingState")
-        return state in ("Charging", "Stopped") and not finished(self.vehicle)
+        # start is allowed to wake it
+        return self.currentAmps > 0 or self.vehicle.value("chargingState") == "Stopped"
+
+    @property
+    def currentAmps(self) -> float:
+        # A car charging draws power, whatever current it last reported.
+        # Asleep after "Charging" it has finished
+        charging = self.vehicle.value("chargingState") == "Charging"
+        return (
+            POWER_FLOWING_AMPS if charging and asleep(self.vehicle) is not True else 0.0
+        )
 
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
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index 552af0db..b134c0d1 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -617,32 +617,38 @@ class TWCMaster:
         remaining_watts = available_watts
         offers = []
 
         if wants_power:
             # Per-controller remaining power budgets and point counts
             controller_budgets = self._budgets()
             controller_counts: dict = {}
             for name in controller_budgets:
                 controller_counts[name] = sum(
                     1 for p in wants_power if name in p.controllers
                 )
 
-            # Fair-share distribution — sort ascending by maxPower so the most
-            # constrained points are served first, reducing wasted capacity.
-            pending = sorted(wants_power, key=lambda p: p.maxPower)
+            # Fair-share distribution: points drawing power first, so a car
+            # newly woken gets only what is left; then ascending by maxPower
+            # so the most constrained points are served first, reducing
+            # wasted capacity.
+            drawing = {p for p in wants_power if p.drawing}
+            pending = sorted(wants_power, key=lambda p: (p not in drawing, p.maxPower))
 
             # Iterate a copy: pending.remove() below would otherwise make the
             # loop skip every other point, leaving it with no target at all.
             for point in list(pending):
                 fair_share = remaining_watts / len(pending)
+                if point in drawing and fair_share < point.minPower:
+                    # Too little to share: cars charging keep it from idle ones
+                    fair_share = remaining_watts / len(drawing.intersection(pending))
 
                 # Constrain by point capacity
                 offer = min(fair_share, point.maxPower)
 
                 # Constrain by controller budgets
                 for ctrl_name in point.controllers:
                     count = controller_counts.get(ctrl_name, 0)
                     if count > 0 and ctrl_name in controller_budgets:
                         offer = min(offer, controller_budgets[ctrl_name] / count)
 
                 # Enforce minimum: offer nothing rather than an unusably small
                 # amount
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 01dcd791..51f41866 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -94,60 +94,92 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
     battery = vehicle.value("batteryLevel")
     if desired is False:
         if battery is not None and battery < config.get("minChargeLevel", -1):
             # A car below the minimum is never stopped
             return "battery below minChargeLevel"
         return None
     # Our own write counts until a newer reading
     limit = vehicle.believed("chargeLimit", VEHICLE_SOURCES_EXCLUDED)
     limit = limit.value if limit is not None else None
     if battery and limit and battery >= limit:
         # The car would refuse the start
         return "battery at its charge limit"
+    return refusesStart(vehicle, known, config)
+
+
+def refusesStart(vehicle, known, config=None) -> Optional[str]:
+    # Why the car takes no power whatever its limit
     if known is not None and known.value in ("Disconnected", "NoPower"):
         return "the car cannot charge (%s)" % known.value
-    if vehicle.value("scheduledChargingPending") is True and config.get(
+    if vehicle.value("scheduledChargingPending") is True and (config or {}).get(
         "respectVehicleSchedule", True
     ):
         # A start would override the car's own schedule
         return "scheduled charging is pending (respectVehicleSchedule)"
     return None
 
 
+# A car asleep after "Charging" this close to its limit has finished
+FINISHED_MARGIN = 2
+
+
 def finished(vehicle) -> bool:
     # The session ended at the limit believed: "Complete", or asleep after
-    # "Charging"
-    state = known(vehicle, CHARGING)
-    state = state and state.value
-    return state == "Complete" or state == "Charging" and asleep(vehicle) is True
+    # "Charging" with its battery at that limit, or not known
+    state, limit = known(vehicle, CHARGING), known(vehicle, CHARGE_LIMIT)
+    battery = vehicle.value("batteryLevel")
+    if state is None or state.value != "Charging" or asleep(vehicle) is not True:
+        return state is not None and state.value == "Complete"
+    return not (limit and battery) or battery >= limit.value - FINISHED_MARGIN
 
 
 def whyQuiet(master, vehicle, budgeting=False) -> Optional[str]:
     # Why the car is expected to quiesce once every pending desire is applied,
     # or None when it will charge (unknown limit or battery: it will).
-    # budgeting: the distributor asks whether the car would take power, so
-    # its own offer and the stop its gate answered that offer with don't count
+    # budgeting: whether the car would take power, so the distributor's own
+    # offer and the stop its gate answered a 0 offer with don't count
     key, desired = vehicle.key, master.desired
     stop, pending = desired.get(key, CHARGING), desired.get(key, CHARGE_LIMIT)
     held = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
     believed, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
     limit = believed = believed and believed.value
     if pending is not None and not (releases(pending) and not held):
         limit = held.outside if releases(pending) else pending.value
     # Unplugged is known only by a reading
     plugged = pluggedNow(master, vehicle, None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
         return "not plugged in here"
-    if not budgeting and stop is not None and stop.value is False:
+    if budgeting:
+        config = (getattr(master, "config", None) or {}).get("config")
+        why = refusesStart(vehicle, known(vehicle, CHARGING, True), config)
+        if why:
+            return why
+    elif stop is not None and stop.value is False:
         return "stop desired"
-    if not budgeting and getattr(master, "offered", {}).get(key) == 0:
+    elif getattr(master, "offered", {}).get(key) == 0:
         return "nothing offered"
     if limit and battery and limit <= battery:
         return "car won't charge: limit at or below battery"
     if finished(vehicle) and not (limit and (believed is None or limit > believed)):
         # Only a raise above the limit it finished at starts it again
         return "car finished charging"
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
-    if any(f and f.registry.now() < f.settleUntil for f in feeds):
+    if not budgeting and any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
+
+
+def wantsPower(master, vehicle) -> Optional[bool]:
+    # Whether the car takes power once the pending desires land: False when
+    # it won't, True when the registry shows it will (a raise pending, or a
+    # start or a paused session with its limit known), else None. Not
+    # quiet, a known limit is above a known battery
+    if whyQuiet(master, vehicle, budgeting=True):
+        return False
+    key, desired = vehicle.key, master.desired
+    start = getattr(desired.get(key, CHARGING), "value", None) is True
+    paused = getattr(known(vehicle, CHARGING), "value", None) == "Stopped"
+    limit = desired.get(key, CHARGE_LIMIT) is not None or (
+        (start or paused) and known(vehicle, CHARGE_LIMIT) is not None
+    )
+    return True if limit and vehicle.value("batteryLevel") is not None else None
diff --git a/tests/unit/test_charging_points.py b/tests/unit/test_charging_points.py
index 1bfe4c6c..fbdf80b5 100644
--- a/tests/unit/test_charging_points.py
+++ b/tests/unit/test_charging_points.py
@@ -152,32 +152,29 @@ def endpoint(monkeypatch, vin):
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
-    # A paused car with no limit known would take power: the TWC carries the full share
-    assert s.pointAmps == 32 and setAmps(m) == []
-    v = m.vehicleRegistry.get(VIN); v.observe("chargeLimit", 80, "OwnerAPI"); v.observe("batteryLevel", 80, "OwnerAPI")
-    m.distributeEVSEPower()
-    assert s.pointAmps == 0 and setAmps(m) == []                          # at its limit: the idle offer, 0 (the TWC's hardware minimum)...
-    s.reportedAmpsActual = 5.5                                                   # ...yet a car drawing takes the full share
+    # The TWC decides: reporting no demand, it gets its idle offer, 0 (the TWC's hardware minimum)...
+    assert s.pointAmps == 0 and setAmps(m) == []
+    s.reportedAmpsActual = 5.5                                                   # ...the paused car takes it...
     m.distributeEVSEPower()
-    assert s.pointAmps == 32 and setAmps(m) == []
+    assert s.pointAmps == 32 and setAmps(m) == []                         # ...and the full share follows
 
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
diff --git a/tests/unit/test_wants_power.py b/tests/unit/test_wants_power.py
index 10178cd6..63395401 100644
--- a/tests/unit/test_wants_power.py
+++ b/tests/unit/test_wants_power.py
@@ -4,26 +4,26 @@
 import pytest
 
 from TWCManager.Vehicle.Reconcile import Belief as B
 from TWCManager.Vehicle.Reconcile import Outcome as O
 from TWCManager.Vehicle.Reconcile.Desired import AMPS, CHARGE_LIMIT, CHARGING
 from tests.unit.reconcile_helpers import placeAt
 from tests.unit.test_limit_reconciler import VIN, ble, names, prov, setup
 
 TM = "TeslaMateVehicle"
 
 
 def asleepAtItsLimit(limit=70, twc=False):
-    # The live box: TeslaMate's last word on a car that finished at its
-    # limit and slept, BLE able to set its amps; no TWC unless asked
+    # A car that finished at its limit and slept, as TeslaMate last saw
+    # it; BLE can set its amps; no TWC unless asked
     m, r, v, c = setup(*[ble(O.Outcome(O.DONE)) for _ in range(4)], here=False)
     if not twc:
         m.slaveTWCs.clear()
     placeAt(m, v)
     for field, value in (
         ("pluggedIn", True),
         ("chargingState", "Complete"),
         ("batteryLevel", 70),
         ("chargeLimit", limit),
     ):
         v.observe(field, value, TM)
     c.t += 10
@@ -168,12 +168,95 @@ def test_a_raise_shares_the_budget_until_the_car_is_found_quiet():
         ):
             v.observe(field, value, "OwnerAPI")
     budget(m, 32)
     m.distributeEVSEPower()
     assert setAmps(m) == [{"vin": VIN, "amps": 32}]
     m.desired.set(VIN2, CHARGE_LIMIT, 90, "policy")
     m.distributeEVSEPower()
     assert sorted((x["vin"], x["amps"]) for x in setAmps(m)) == [(VIN, 16), (VIN2, 16)]
     b.observe("chargeLimit", 90, "OwnerAPI")  # the raise landed...
     b.observe("batteryLevel", 90, "OwnerAPI")  # ...on a car already there
     m.distributeEVSEPower()
     assert setAmps(m) == [{"vin": VIN, "amps": 32}]
+
+
+# What the registry can't show the car will take, the members' own reports
+# decide; a car it shows won't take power gets none, however its members
+# report
+
+
+def carSide(*cars, amps=32):
+    # Cars on no TWC: (vin, chargingState, battery, limit), None for unknown
+    from tests.unit.test_charging_points import budget, car, real
+
+    m = real()
+    m.slaveTWCs.clear()
+    for vin, state, battery, limit in cars:
+        v = car(m, vin, state)
+        for field, value in (
+            ("pluggedIn", True),
+            ("batteryLevel", battery),
+            ("chargeLimit", limit),
+        ):
+            if value is not None:
+                v.observe(field, value, "OwnerAPI")
+    budget(m, amps)
+    return m
+
+
+@pytest.mark.parametrize("idleFirst", [False, True])
+def test_a_charging_car_keeps_a_budget_too_small_to_share(idleFirst):
+    from tests.unit.test_charging_points import VIN2, setAmps
+
+    charging, idle = (VIN, "Charging", 50, 90), (VIN2, "Complete", 70, 70)
+    m = carSide(*([idle, charging] if idleFirst else [charging, idle]), amps=9)
+    m.desired.set(VIN2, CHARGE_LIMIT, 90, "policy")
+    m.distributeEVSEPower()
+    assert setAmps(m) == [{"vin": VIN, "amps": 9}] and m.offered[VIN2] == 0
+
+
+def test_a_car_known_only_to_be_plugged_in_gets_no_share():
+    from tests.unit.test_charging_points import VIN2, setAmps
+
+    m = carSide((VIN, "Charging", 50, 90), (VIN2, None, None, None))
+    m.distributeEVSEPower()
+    assert setAmps(m) == [{"vin": VIN, "amps": 32}]
+
+
+@pytest.mark.parametrize("battery", [80, 85])
+def test_a_stopped_car_at_its_limit_gets_no_share(battery):
+    from tests.unit.test_charging_points import VIN2, setAmps
+
+    m = carSide((VIN, "Charging", 50, 90), (VIN2, "Stopped", battery, 80))
+    m.distributeEVSEPower()
+    assert setAmps(m) == [{"vin": VIN, "amps": 32}]
+
+
+def test_a_gen3_unit_reporting_complete_for_a_car_it_knows_nothing_of_gets_nothing():
+    from tests.unit.test_charging_points import budget, car, real
+    from tests.unit.test_gen3twc_provider import vitals
+
+    m = real(gen3=True)
+    car(m, VIN, None).observe("pluggedIn", True, TM)
+    (u,) = m.modules["Gen3TWCs"]["ref"].devices()
+    vitals(u, True, 0.0, state="complete")
+    assert u.vehicleKey == VIN
+    budget(m, 32)
+    m.distributeEVSEPower()
+    assert m.offered[VIN] == 0 and not u.lastTarget
+
+
+@pytest.mark.parametrize("twc", [False, True])
+def test_a_car_on_its_own_schedule_gets_no_share_and_no_wake(twc):
+    m, r, v, c = asleepAtItsLimit(twc=twc)
+    v.observe("chargingState", "Stopped", TM)
+    v.observe("chargeLimit", 80, TM)
+    v.observe("scheduledChargingPending", True, TM)
+    s = onGen2(m, v) if twc else None
+    for i in range(30):
+        c.t += 10
+        v.observe("state", "asleep", "TeslaBLE")
+        m.setMaxAmpsToDivideAmongSlaves(20 + i % 3)
+        m.controlPass(now=c())
+        r.pass_()
+        assert m.offered.get(VIN, 0) == 0 and (s is None or s.pointAmps == 0)
+    assert "wake" not in names(prov(m, "TeslaBLE"))
