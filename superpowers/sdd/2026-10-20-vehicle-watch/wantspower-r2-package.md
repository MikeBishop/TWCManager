833d6a44 Admit a car to the budget only on positive evidence it will charge
ef7be20f Offer power to a plugged-in car that a pending raise would start
 CHANGELOG.md                                   |  2 +-
 lib/TWCManager/EVSEInstance/ChargingPoint.py   | 21 ++++------
 lib/TWCManager/EVSEInstance/Gen2TWC.py         |  5 ++-
 lib/TWCManager/EVSEInstance/Gen3TWC.py         |  5 +++
 lib/TWCManager/EVSEInstance/VehicleEndpoint.py |  9 ++--
 lib/TWCManager/TWCMaster.py                    | 14 +++----
 lib/TWCManager/Vehicle/Presence.py             |  6 ++-
 lib/TWCManager/Vehicle/Providers/Provider.py   |  4 +-
 lib/TWCManager/Vehicle/Reconcile/Belief.py     | 57 ++++++++++----------------
 lib/TWCManager/Vehicle/Reconcile/Reconciler.py |  2 +-
 tests/unit/test_charging_points.py             |  2 +-
 tests/unit/test_wants_power.py                 | 38 +++++++++++++++++
 12 files changed, 96 insertions(+), 69 deletions(-)
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 11d63103..aadb6b45 100644
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
-    * (@MikeBishop) - A plugged-in car asleep at its old charge limit is offered power, woken and started when a policy raises its limit, on a Gen2 or Gen3 TWC or on a charging station TWCManager doesn't control. A car at its limit with no raise pending, one that has finished charging, or one waiting on its own schedule is no longer given a share of the power other cars could use, and a car already charging keeps power too scarce to share
+    * (@MikeBishop) - A plugged-in car asleep at its old charge limit is offered power, woken and started when a policy raises its limit, on a Gen2 or Gen3 TWC or on a charging station TWCManager doesn't control. A car at its limit with no raise pending, one that has finished charging, or one waiting on its own schedule is no longer given a share of the power other cars could use. When there is too little power to share, a car already charging keeps it
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
index 1509b789..baec2f45 100644
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
-from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known, wantsPower
+from TWCManager.Vehicle.Reconcile.Belief import known, whyQuiet
 from TWCManager.Vehicle.Reconcile.Desired import AMPS
 from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Registry.VehicleRegistry import canonicalKey, isAnonKey
 
 
 class ChargingPoint(EVSEInstance):
     # The cars setTargetPower rated this pass; finding them may scan them all
     carKeys = None
 
     def __init__(self, master, key: str, endpoints: List[EVSEInstance]):
         self.master = master
         self.key = key
@@ -35,41 +35,38 @@ class ChargingPoint(EVSEInstance):
         return [e for e in self.endpoints if not e.isLocal]
 
     @property
     def ID(self) -> str:
         return "Point-" + self.key
 
     @property
     def isReadOnly(self) -> bool:
         return all(e.isReadOnly for e in self.endpoints)
 
     @property
     def drawing(self) -> bool:
-        # Power flowing: a TWC's measured current, or a car member charging
-        members = self.localEndpoints or self.endpoints
-        return any(e.currentAmps >= POWER_FLOWING_AMPS for e in members)
+        return any(e.drawing for e in self.localEndpoints or self.endpoints)
 
     @property
     def wantsToCharge(self) -> bool:
-        # Power flowing, or the car would take it once the desires being
-        # applied land: asleep at its old limit, a raise wakes it only if
-        # power is offered. Where the registry can't say, or the point can't
-        # name its car, this falls back to its members' own reports
+        # Power flowing, or the car takes it once the desires land (asleep at
+        # its old limit, a raise wakes it only if power is offered). Where the
+        # registry can't say, its members' own reports decide
         if self.drawing:
             return True
         v = self.master.vehicleRegistry.get(self.key)
-        wants = None if v is None or v.isAnonymous else wantsPower(self.master, v)
-        if wants is not None:
-            return wants
-        return any(e.wantsToCharge for e in self.localEndpoints or self.endpoints)
+        why = "" if v is None or v.isAnonymous else whyQuiet(self.master, v, True)
+        if why == "":
+            return any(e.wantsToCharge for e in self.localEndpoints or self.endpoints)
+        return why is None
 
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
diff --git a/lib/TWCManager/EVSEInstance/Gen2TWC.py b/lib/TWCManager/EVSEInstance/Gen2TWC.py
index d11dc90d..8e65904b 100644
--- a/lib/TWCManager/EVSEInstance/Gen2TWC.py
+++ b/lib/TWCManager/EVSEInstance/Gen2TWC.py
@@ -1,19 +1,20 @@
 """
 A Gen2 TWC slave on RS-485 as a charging endpoint: TWCSlave's protocol
 state, read as the distributor's endpoint.
 """
 
 from TWCManager.EVSEInstance.EVSEInstance import EVSEInstance
 from TWCManager.TWCSlave import TWCSlave
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS
 from TWCManager.Vehicle.Registry.VehicleRegistry import ANON_PREFIX
 
 
 class Gen2TWC(EVSEInstance, TWCSlave):
     # Heartbeat states in which a car is plugged in
     PLUGGED_STATES = (0x01, 0x03, 0x04, 0x05, 0x08, 0x09)
     isReadOnly = False
     isLocal = True
     controllers = ["Gen2TWCs"]
     _isCharging = 0
 
     @property
@@ -69,26 +70,26 @@ class Gen2TWC(EVSEInstance, TWCSlave):
         return None
 
     @property
     def wantsToCharge(self) -> bool:
         """True when a vehicle is plugged in and willing to accept power.
 
         TWC heartbeat: reportedAmpsMax is non-zero once the vehicle has
         communicated its maximum charge rate (i.e. it's plugged in and awake).
         """
         return self.reportedAmpsMax > 0 or self.reportedAmpsActual > 0
 
     @property
-    def currentAmps(self) -> float:
-        return self.reportedAmpsActual
+    def drawing(self) -> bool:
+        return self.reportedAmpsActual >= POWER_FLOWING_AMPS
 
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
 
diff --git a/lib/TWCManager/EVSEInstance/Gen3TWC.py b/lib/TWCManager/EVSEInstance/Gen3TWC.py
index 7d6710d5..85fc19c9 100644
--- a/lib/TWCManager/EVSEInstance/Gen3TWC.py
+++ b/lib/TWCManager/EVSEInstance/Gen3TWC.py
@@ -34,24 +34,25 @@ Protocol references (no code copied):
   - Klangen82/tesla-wall-connector-control (vitals API format)
   - LucaTNT Gist 4adf01a7252386559070023612efa117 (Neurio control approach)
 """
 
 from __future__ import annotations
 
 import logging
 import time
 from typing import TYPE_CHECKING, Optional
 
 from TWCManager.EVSEInstance.EVSEInstance import EVSEInstance
 from TWCManager.Vehicle.Presence import attribute
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS
 
 if TYPE_CHECKING:
     from TWCManager.EVSEController.Gen3TWCs import Gen3TWCs
 
 logger = logging.getLogger(__name__.rpartition(".")[2])
 
 # How many seconds a failed vitals fetch is cached before retry
 _VITALS_CACHE_TTL = 10.0
 # How many seconds a successful vitals response is cached
 _VITALS_SUCCESS_TTL = 5.0
 # How many seconds a failed /api/1/version fetch waits before a retry
 _VERSION_RETRY_SECONDS = 600.0
@@ -294,24 +295,28 @@ class Gen3TWC(EVSEInstance):
 
     @property
     def wantsToCharge(self) -> bool:
         """True when a vehicle is plugged in (connected) and not fully charged."""
         v = self.vitals
         connected = v.get("vehicle_connected", False)
         state = str(v.get("evse_state", "")).lower()
         # "not_charging" can mean plugged-in-but-waiting; "charging" = active.
         # Exclude states that indicate completed / unplugged.
         not_done = state not in ("", "not_connected", "complete")
         return bool(connected) and not_done
 
+    @property
+    def drawing(self) -> bool:
+        return self.currentAmps >= POWER_FLOWING_AMPS
+
     @property
     def currentAmps(self) -> float:
         v = self.vitals
         return float(v.get("vehicle_current_a", 0.0))
 
     @property
     def currentVoltage(self) -> list:
         """Per-phase voltages [A, B, C]."""
         v = self.vitals
         voltage = float(v.get("grid_v", 0.0))
         if voltage < 90:
             voltage = float(self.configConfig.get("defaultVoltage", 240))
diff --git a/lib/TWCManager/EVSEInstance/VehicleEndpoint.py b/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
index 10bdd5d2..6a204cf6 100644
--- a/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
+++ b/lib/TWCManager/EVSEInstance/VehicleEndpoint.py
@@ -37,34 +37,31 @@ class VehicleEndpoint(EVSEInstance):
 
     @property
     def isReadOnly(self) -> bool:
         # No provider can set this car's amps (an Owner-only token on a car
         # that needs signed commands, ble_only without BLE), so the
         # distributor must not budget power for it
         return not self._candidates()
 
     @property
     def wantsToCharge(self) -> bool:
         # "Stopped" is a paused session: the car takes power if offered, and a
         # start is allowed to wake it
-        return self.currentAmps > 0 or self.vehicle.value("chargingState") == "Stopped"
+        return self.drawing or self.vehicle.value("chargingState") == "Stopped"
 
     @property
-    def currentAmps(self) -> float:
-        # A car charging draws power, whatever current it last reported.
+    def drawing(self) -> bool:
         # Asleep after "Charging" it has finished
         charging = self.vehicle.value("chargingState") == "Charging"
-        return (
-            POWER_FLOWING_AMPS if charging and asleep(self.vehicle) is not True else 0.0
-        )
+        return charging and asleep(self.vehicle) is not True
 
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
index b134c0d1..b6fb1383 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -617,38 +617,36 @@ class TWCMaster:
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
 
-            # Fair-share distribution: points drawing power first, so a car
-            # newly woken gets only what is left; then ascending by maxPower
-            # so the most constrained points are served first, reducing
-            # wasted capacity.
-            drawing = {p for p in wants_power if p.drawing}
-            pending = sorted(wants_power, key=lambda p: (p not in drawing, p.maxPower))
+            # Fair-share distribution — sort ascending by maxPower so the most
+            # constrained points are served first, reducing wasted capacity.
+            pending = sorted(wants_power, key=lambda p: p.maxPower)
 
             # Iterate a copy: pending.remove() below would otherwise make the
             # loop skip every other point, leaving it with no target at all.
             for point in list(pending):
                 fair_share = remaining_watts / len(pending)
-                if point in drawing and fair_share < point.minPower:
+                charging = [p for p in pending if p.drawing]
+                if fair_share < point.minPower and charging:
                     # Too little to share: cars charging keep it from idle ones
-                    fair_share = remaining_watts / len(drawing.intersection(pending))
+                    fair_share = remaining_watts / len(charging) * (point in charging)
 
                 # Constrain by point capacity
                 offer = min(fair_share, point.maxPower)
 
                 # Constrain by controller budgets
                 for ctrl_name in point.controllers:
                     count = controller_counts.get(ctrl_name, 0)
                     if count > 0 and ctrl_name in controller_budgets:
                         offer = min(offer, controller_budgets[ctrl_name] / count)
 
                 # Enforce minimum: offer nothing rather than an unusably small
                 # amount
diff --git a/lib/TWCManager/Vehicle/Presence.py b/lib/TWCManager/Vehicle/Presence.py
index 973ff0bb..6903b326 100644
--- a/lib/TWCManager/Vehicle/Presence.py
+++ b/lib/TWCManager/Vehicle/Presence.py
@@ -26,38 +26,42 @@ HOME_CHARGER_TYPES = frozenset({"ACSingleWireCAN", "MCSingleWireCAN", "<invalid>
 _PLUGGED = frozenset({"Charging", "Starting", "Stopped", "Complete", "NoPower"})
 # The fields whose readings may say plugged or unplugged
 _PLUGS = ("pluggedIn", "chargingState", "chargePortOpen")
 # A plug report from these needs no position: the charger or the radio is here
 _STRONG = frozenset({"TWC", "Gen2TWC", "Gen3TWC", "TeslaBLE"})
 _CHARGERS = frozenset({"Gen2TWC", "Gen3TWC"})
 _MOVING = frozenset({"D", "R", "N"})
 # Feet per degree of latitude; the box test uses it for longitude too
 _FT_PER_DEGREE = 364488.888
 NEVER = float("-inf")
 
 
+def masterConfig(master) -> dict:
+    return (getattr(master, "config", None) or {}).get("config") or {}
+
+
 @functools.lru_cache(maxsize=None)
 def _warnNoHome():
     logger.warning(
         "No home location set: cars reached only through vehicle APIs are "
         "not treated as home (set it on the Settings page)"
     )
 
 
 def _within(master, lat, lon) -> Optional[bool]:
     home = master.getHomeLatLon()
     if home[0] == 10000:
         _warnNoHome()
         return None
-    config = (getattr(master, "config", None) or {}).get("config", {})
+    config = masterConfig(master)
     deg = float(config.get("atHomeRadius", HOME_RADIUS_FT)) / _FT_PER_DEGREE
     return abs(home[0] - lat) <= deg and abs(home[1] - lon) <= deg
 
 
 def _fix(master, v) -> Tuple[Optional[bool], float]:
     # The newest position: inside the radius (None if unknown) and its time
     lat, lon = v.latest("lat"), v.latest("lon")
     if lat is None or lon is None:
         return None, NEVER
     return _within(master, lat.value, lon.value), max(lat.at, lon.at)
 
 
diff --git a/lib/TWCManager/Vehicle/Providers/Provider.py b/lib/TWCManager/Vehicle/Providers/Provider.py
index d43df1a6..9bd8b133 100644
--- a/lib/TWCManager/Vehicle/Providers/Provider.py
+++ b/lib/TWCManager/Vehicle/Providers/Provider.py
@@ -1,14 +1,15 @@
 from typing import Dict, FrozenSet, Optional, Tuple
 
+from ..Presence import masterConfig
 from ..Reconcile.Outcome import UNSUPPORTED, Outcome
 from .Capability import COMMANDS, START_CHARGING, STOP_CHARGING, Cost
 
 # What a cloud provider may not do under each suppression condition: no
 # command under ble_only, no stop when the user chose a disruptive local
 # stop (chargeStopMode 2/3), which pays nothing, and under mode 2 no start
 # either: mode 2 starts by answering the slaves again
 CLOUD_SUPPRESSED = {
     "ble_only": COMMANDS,
     "localStops": frozenset({STOP_CHARGING}),
     "silentStops": frozenset({START_CHARGING}),
 }
@@ -111,14 +112,13 @@ def vehicleMaxAmps(vehicle, configConfig: dict) -> float:
     # charger's pilot: on our own TWC the pilot is our last offer, so a car
     # read under a low offer would hold its charging point there for good.
     return vehicle.value("chargeCurrentRequestMax") or configConfig.get(
         "wiringMaxAmpsPerTWC", 32
     )
 
 
 def carAmpsRange(vehicle, master) -> Optional[Tuple[float, float]]:
     # What a provider that commands the car itself offers: amps run 1..max,
     # never 0 (a 0 would stop the charge)
     if vehicle is None:
         return None
-    config = (getattr(master, "config", None) or {}).get("config")
-    return (1, vehicleMaxAmps(vehicle, config or {}))
+    return (1, vehicleMaxAmps(vehicle, masterConfig(master)))
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 51f41866..868c5cee 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -1,19 +1,19 @@
 # What the reconciler believes about a car, and the per-aspect rules it
 # plans by: pure functions of the registry, no reconciler state. The EVSE
 # layer reads known() from here without the reconciler thread.
 from typing import Optional
 
 from ..Registry.Fields import FEED_LAG
-from ..Presence import NOT_HOME, asleep, pluggedNow, presence
+from ..Presence import NOT_HOME, asleep, masterConfig, pluggedNow, presence
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
 from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
 
 # Sources whose every reading came from the car itself. Exact source
 # names; Fleet Telemetry always counts
 LIVE_READ_SOURCES = frozenset(
     {"TeslaBLE", "OwnerAPI", "FleetAPI", "FleetTelemetryMQTT"}
 )
 # TWC current at or above this means the car is drawing power
 POWER_FLOWING_AMPS = 1.0
 
 
@@ -97,89 +97,76 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
             # A car below the minimum is never stopped
             return "battery below minChargeLevel"
         return None
     # Our own write counts until a newer reading
     limit = vehicle.believed("chargeLimit", VEHICLE_SOURCES_EXCLUDED)
     limit = limit.value if limit is not None else None
     if battery and limit and battery >= limit:
         # The car would refuse the start
         return "battery at its charge limit"
     return refusesStart(vehicle, known, config)
 
 
-def refusesStart(vehicle, known, config=None) -> Optional[str]:
+def refusesStart(vehicle, known, config) -> Optional[str]:
     # Why the car takes no power whatever its limit
     if known is not None and known.value in ("Disconnected", "NoPower"):
         return "the car cannot charge (%s)" % known.value
-    if vehicle.value("scheduledChargingPending") is True and (config or {}).get(
+    if vehicle.value("scheduledChargingPending") is True and config.get(
         "respectVehicleSchedule", True
     ):
         # A start would override the car's own schedule
         return "scheduled charging is pending (respectVehicleSchedule)"
     return None
 
 
-# A car asleep after "Charging" this close to its limit has finished
-FINISHED_MARGIN = 2
-
-
 def finished(vehicle) -> bool:
     # The session ended at the limit believed: "Complete", or asleep after
     # "Charging" with its battery at that limit, or not known
     state, limit = known(vehicle, CHARGING), known(vehicle, CHARGE_LIMIT)
     battery = vehicle.value("batteryLevel")
     if state is None or state.value != "Charging" or asleep(vehicle) is not True:
         return state is not None and state.value == "Complete"
-    return not (limit and battery) or battery >= limit.value - FINISHED_MARGIN
+    # Within 2 % of its limit it has finished, not stopped short
+    return not (limit and battery) or battery >= limit.value - 2
 
 
 def whyQuiet(master, vehicle, budgeting=False) -> Optional[str]:
     # Why the car is expected to quiesce once every pending desire is applied,
     # or None when it will charge (unknown limit or battery: it will).
-    # budgeting: whether the car would take power, so the distributor's own
-    # offer and the stop its gate answered a 0 offer with don't count
+    # budgeting: whether to offer it power, so neither our offer nor our gate's
+    # stop counts, and None needs evidence: a raise pending, or a start or a
+    # paused session below a known limit; "" where the registry can't say
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
-    if budgeting:
-        config = (getattr(master, "config", None) or {}).get("config")
-        why = refusesStart(vehicle, known(vehicle, CHARGING, True), config)
-        if why:
-            return why
-    elif stop is not None and stop.value is False:
+    config, now = masterConfig(master), known(vehicle, CHARGING, True)
+    if budgeting and refusesStart(vehicle, now, config):
+        return refusesStart(vehicle, now, config)
+    if not budgeting and stop is not None and stop.value is False:
         return "stop desired"
-    elif getattr(master, "offered", {}).get(key) == 0:
+    if not budgeting and getattr(master, "offered", {}).get(key) == 0:
         return "nothing offered"
     if limit and battery and limit <= battery:
         return "car won't charge: limit at or below battery"
-    if finished(vehicle) and not (limit and (believed is None or limit > believed)):
+    raised = limit and (believed is None or limit > believed)
+    if finished(vehicle) and not raised:
         # Only a raise above the limit it finished at starts it again
         return "car finished charging"
+    if budgeting:
+        # Paused as the car reported, not a TWC's idle current standing in
+        paused = vehicle.value("chargingState") == "Stopped"
+        start = getattr(stop, "value", None) is True
+        evidence = pending is not None and raised or limit and (start or paused)
+        return None if evidence and battery is not None else ""
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
-    if not budgeting and any(f and f.registry.now() < f.settleUntil for f in feeds):
+    if any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
-
-
-def wantsPower(master, vehicle) -> Optional[bool]:
-    # Whether the car takes power once the pending desires land: False when
-    # it won't, True when the registry shows it will (a raise pending, or a
-    # start or a paused session with its limit known), else None. Not
-    # quiet, a known limit is above a known battery
-    if whyQuiet(master, vehicle, budgeting=True):
-        return False
-    key, desired = vehicle.key, master.desired
-    start = getattr(desired.get(key, CHARGING), "value", None) is True
-    paused = getattr(known(vehicle, CHARGING), "value", None) == "Stopped"
-    limit = desired.get(key, CHARGE_LIMIT) is not None or (
-        (start or paused) and known(vehicle, CHARGE_LIMIT) is not None
-    )
-    return True if limit and vehicle.value("batteryLevel") is not None else None
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index 3753a9c8..e63f3dec 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -271,25 +271,25 @@ class VehicleReconciler(threading.Thread):
                 return None
         held = self._held(vehicle)
         if R.satisfied(aspect, d.value, k):
             if d.restore and held is not None and held.held is not None:
                 # Already back at the outside limit: nothing is held
                 self.master.heldLimits.remove(vehicle.vin)
                 self.desired.clear(key, aspect)
             return None
         if d.restore and (held is None or held.held is None):
             # Nothing to restore
             self.desired.clear(key, aspect)
             return None
-        config = (getattr(self.master, "config", None) or {}).get("config")
+        config = Presence.masterConfig(self.master)
         reason = B.handsOff(vehicle, aspect, d.value, k, config)
         if reason is not None:
             self._sayOnce(key, aspect, "hands off: " + reason, logging.INFO)
             return None
         if rec.settledAt is not None and not (
             B.newerReading(vehicle, aspect, rec.settledAt)
             and now - rec.lastSentAt >= RETRY[aspect]
         ):
             # Settled without a stamp: wait for a newer reading
             return None
         capability = CAPABILITY_FOR(aspect, d.value)
         cands = [
diff --git a/tests/unit/test_charging_points.py b/tests/unit/test_charging_points.py
index fbdf80b5..7c73341f 100644
--- a/tests/unit/test_charging_points.py
+++ b/tests/unit/test_charging_points.py
@@ -9,25 +9,25 @@ from TWCManager.EVSEController.Gen3TWCs import Gen3TWCs
 from TWCManager.EVSEInstance.VehicleEndpoint import VehicleEndpoint, vehicleEndpoints
 from TWCManager.EVSEInstance.ChargingPoint import ChargingPoint, groupEndpoints
 from TWCManager.TWCMaster import TWCMaster
 from tests.unit.reconcile_helpers import placeAt
 from tests.unit.test_gen2twc_provider import CONFIG
 from tests.unit.test_gen3twc_provider import vitals
 from tests.unit.test_provider_order import fleet
 from tests.unit.test_vehicle_endpoint import provider
 VIN = "5YJ3E1EA1KF000001"; VIN2 = "5YJ3E1EA1KF000002"
 
 def ep(ID, key=None, local=False, minW=1200, maxW=7680, wants=True, ro=False, occupied=None, amps=0.0):
     e = MagicMock(); e.ID = ID; e.vehicleKey = key; e.isLocal = local; e.minPower = minW; e.maxPower = maxW
-    e.wantsToCharge = wants; e.isReadOnly = ro; e.occupied = occupied; e.currentAmps = amps; e.currentVoltage = [240, 0, 0]
+    e.wantsToCharge = wants; e.isReadOnly = ro; e.occupied = occupied; e.currentAmps = amps; e.drawing = amps >= 1; e.currentVoltage = [240, 0, 0]
     e.currentVIN = key if key and not key.startswith("anon:") else ""; e.controllers = ["Gen2TWCs" if local else "VehicleEndpoints"]
     if local: del e.pointAmps                                                      # a local member that does not layer (as a Gen3 unit)
     return e
 
 def test_grouping_is_by_vehicle_key_and_merge_count_may_be_one():
     twc = ep("Gen2TWC-8244", VIN.lower(), local=True); car = ep("Vehicle-" + VIN, VIN); idle = ep("Gen2TWC-8245", None, local=True); anon = ep("Gen2TWC-8246", "anon:8246", local=True)
     pts = groupEndpoints(Mock(), [twc, car, idle, anon])
     assert [p.ID for p in pts] == ["Point-" + VIN, "Point-Gen2TWC-8245", "Point-anon:8246"]
     assert pts[0].endpoints == [twc, car] and pts[0].localEndpoints == [twc] and pts[0].vehicleKey == VIN
     assert pts[1].endpoints == [idle] and pts[1].vehicleKey == "Gen2TWC-8245"
 
 def test_a_point_holds_at_most_one_local_endpoint():
diff --git a/tests/unit/test_wants_power.py b/tests/unit/test_wants_power.py
index 63395401..e83d292c 100644
--- a/tests/unit/test_wants_power.py
+++ b/tests/unit/test_wants_power.py
@@ -251,12 +251,50 @@ def test_a_car_on_its_own_schedule_gets_no_share_and_no_wake(twc):
     v.observe("chargingState", "Stopped", TM)
     v.observe("chargeLimit", 80, TM)
     v.observe("scheduledChargingPending", True, TM)
     s = onGen2(m, v) if twc else None
     for i in range(30):
         c.t += 10
         v.observe("state", "asleep", "TeslaBLE")
         m.setMaxAmpsToDivideAmongSlaves(20 + i % 3)
         m.controlPass(now=c())
         r.pass_()
         assert m.offered.get(VIN, 0) == 0 and (s is None or s.pointAmps == 0)
     assert "wake" not in names(prov(m, "TeslaBLE"))
+
+
+def test_a_woken_car_capped_low_leaves_the_rest_to_a_charging_car():
+    from tests.unit.test_charging_points import VIN2, setAmps
+
+    m = carSide((VIN, "Charging", 50, 90), (VIN2, "Complete", 70, 70), amps=40)
+    m.config["config"]["wiringMaxAmpsPerTWC"] = 48
+    m.vehicleRegistry.get(VIN2).observe("chargeCurrentRequestMax", 16, "OwnerAPI")
+    m.desired.set(VIN2, CHARGE_LIMIT, 90, "policy")
+    m.distributeEVSEPower()
+    assert sorted((x["vin"], x["amps"]) for x in setAmps(m)) == [(VIN, 24), (VIN2, 16)]
+
+
+@pytest.mark.parametrize("gen3", [False, True])
+def test_a_policy_limit_that_is_no_raise_is_no_evidence(gen3):
+    # State unknown at 78 of 80, the policy's limit also 80
+    from tests.unit.test_charging_points import VIN2, setAmps
+    from tests.unit.test_gen3twc_provider import vitals
+
+    if gen3:
+        from tests.unit.test_charging_points import budget, car, real
+
+        m = real(gen3=True)
+        v = car(m, VIN, None)
+        v.observe("pluggedIn", True, TM)
+        (u,) = m.modules["Gen3TWCs"]["ref"].devices()
+        vitals(u, True, 0.0, state="complete")
+        budget(m, 32)
+    else:
+        m = carSide((VIN2, "Charging", 50, 90), (VIN, None, None, None))
+        v = m.vehicleRegistry.get(VIN)
+    v.observe("batteryLevel", 78, "OwnerAPI")
+    v.observe("chargeLimit", 80, "OwnerAPI")
+    m.desired.set(VIN, CHARGE_LIMIT, 80, "policy")
+    m.distributeEVSEPower()
+    assert m.offered[VIN] == 0
+    if not gen3:
+        assert setAmps(m) == [{"vin": VIN2, "amps": 32}]
