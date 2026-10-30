de7162d5 Admit charging points first, then share power at one water level
d053ddc7 Wake and start a car that would charge, if there is room
 CHANGELOG.md                                   |   3 +-
 lib/TWCManager/TWCMaster.py                    | 238 +++++++++++-------
 lib/TWCManager/Vehicle/Reconcile/Belief.py     |  50 +++-
 lib/TWCManager/Vehicle/Reconcile/Reconciler.py |  19 +-
 tests/unit/reconcile_helpers.py                |  16 ++
 tests/unit/test_admission.py                   | 325 +++++++++++++++++++++++++
 tests/unit/test_charging_points.py             |  21 +-
 tests/unit/test_charging_reconciler.py         |   8 +-
 tests/unit/test_command_path_parity.py         |  89 ++++---
 tests/unit/test_control_tick.py                |  15 +-
 tests/unit/test_distributor_loop.py            | 178 ++++++++++----
 tests/unit/test_distributor_voltage.py         |  23 +-
 tests/unit/test_gen2_unplug.py                 |   2 +-
 tests/unit/test_limit_reconciler.py            |  21 +-
 tests/unit/test_presence.py                    |  20 +-
 tests/unit/test_sleep_pilot_replay.py          |   2 +-
 tests/unit/test_sleeping_car.py                |   6 +-
 17 files changed, 808 insertions(+), 228 deletions(-)
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index 8f11cd25..c4c9f7b5 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -1,15 +1,15 @@
 #! /usr/bin/python3
 
 from TWCManager.EVSEInstance.Gen2TWC import Gen2TWC as TWCSlave
 from TWCManager.EVSEInstance.ChargingPoint import groupEndpoints
-from TWCManager.EVSEInstance.VehicleEndpoint import vehicleEndpoints
+from TWCManager.EVSEInstance.VehicleEndpoint import VehicleEndpoint, vehicleEndpoints
 from TWCManager.TWCSlave import Offer, OfferContext
 from collections import deque
 from datetime import datetime, timedelta
 import json
 import logging
 import os.path
 import queue
 from sys import modules
 import threading
 import time
@@ -18,21 +18,24 @@ import random
 import requests
 import bisect
 import itertools
 from TWCManager.Logging.LoggerFactory import LoggerFactory
 from TWCManager.Vehicle.Registry.VehicleRegistry import VehicleRegistry, isAnonKey
 from TWCManager.Vehicle.Providers.Order import ProviderOrder
 from TWCManager.Vehicle.Providers.Gen2TWCProvider import Gen2TWCProvider
 from TWCManager.Vehicle.Providers import Capability as C
 from TWCManager.Vehicle.Reconcile.Desired import CHARGING, DesiredStore
 from TWCManager.Vehicle.Reconcile.HeldLimits import HeldLimits
-from TWCManager.Vehicle.Reconcile.Belief import newerReading
+from TWCManager.Vehicle.Reconcile.Belief import Admission, NO_ROOM, known
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS
+from TWCManager.Vehicle.Reconcile.Belief import newerReading, wouldCharge
+from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Reconcile.Reconciler import VehicleReconciler
 from TWCManager.Vehicle.Reconcile.Targets import applyPolicyLimit, onArrival, targetsFor
 from TWCManager.Vehicle.Reconcile.Targets import UNDECIDED
 from TWCManager.Vehicle import Presence
 from TWCManager.Vehicle.Watch import settingsOf
 from TWCManager.Vehicle.WatchBudget import WatchBudget
 
 logger = LoggerFactory.get_logger("Master", "Master")
 
 
@@ -48,20 +51,64 @@ DEFAULT_SETTINGS = {
     "nonScheduledAmpsMax": 0,
     "respondToSlaves": 1,
     "scheduledAmpsDaysBitmap": 0x7F,
     "scheduledAmpsEndHour": -1,
     "scheduledAmpsMax": 0,
     "scheduledAmpsStartHour": -1,
     "sendServerTime": 0,
 }
 
 
+def _carsAt(point) -> set:
+    # The cars a point serves: the one it names, and any its TWC still holds
+    return {point.vehicleKey, *(e.heldKey for e in point.localEndpoints)} - {None}
+
+
+def _drawing(point) -> bool:
+    # Current flows there now, by its TWC's report or else its car's state
+    amps = [
+        getattr(e, "reportedAmpsActual", getattr(e, "currentAmps", 0))
+        for e in point.localEndpoints
+    ]
+    if amps:
+        return max(amps) >= POWER_FLOWING_AMPS
+    states = [e.vehicle.value("chargingState") for e in point.vehicleEndpoints]
+    return point.wantsToCharge and "Charging" in states
+
+
+def _draws(point, budgets) -> set:
+    return budgets.keys() & {"all", *point.controllers}
+
+
+def waterLevel(points, watts) -> dict:
+    # Each point at clamp(L, min, max) amps at its own voltage, L such that
+    # the watts sum to watts, or all at maximum: one pass up the sorted
+    # limits, the sum climbing at the slope of the points between theirs
+    span = {
+        p: [p.convertWattsToAmps(w) for w in (p.minPower, p.maxPower)] for p in points
+    }
+    marks = sorted(
+        (a, p.convertAmpsToWatts(sign))
+        for p in points
+        for a, sign in zip(span[p], (1, -1))
+    )
+    level, used, slope = marks[0][0], sum(p.minPower for p in points), 0
+    for amps, change in marks:
+        if used + slope * (amps - level) >= watts:
+            level += (watts - used) / slope if slope else 0
+            break
+        used, level, slope = used + slope * (amps - level), amps, slope + change
+    return {
+        p: p.convertAmpsToWatts(min(max(level, lo), hi)) for p, (lo, hi) in span.items()
+    }
+
+
 class TWCMaster:
     backgroundTasksQueue = queue.Queue()
     backgroundTasksCmds = {}
     backgroundTasksLock = threading.Lock()
     backgroundTasksDelayed = []
     # Tie-breaker for delayed tasks due at the same instant: entries never
     # fall through to comparing task dicts.
     _delaySeq = itertools.count()
     config = None
     consumptionValues = {}
@@ -136,20 +183,22 @@ class TWCMaster:
         self.heldLimits = HeldLimits(self)
         self.providerOrder = ProviderOrder(self)
         self.providerOrder.register(Gen2TWCProvider(self))
         self.vehicleRegistry.providerOrder = self.providerOrder
         self.vehicleRegistry.onObserve = lambda *a: Presence.noteObservation(self, *a)
         # Desired vehicle state, and the reconciler that converges cars on
         # it; all on the registry's time.time clock
         self.desired = DesiredStore()
         self.vehicleRegistry.removed = self._vehicleRemoved
         self.reconciler = VehicleReconciler(self)
+        # The control tick's admission, and when each car's point lost it
+        self.admission, self._unadmitted = NO_ROOM, {}
         # The policy's charge limit: None while it sets none, UNDECIDED before
         # its first pass
         self.policyLimit = UNDECIDED
         # Start of the forgetting interval: the first expiry pass runs an
         # hour after startup, once providers have reclaimed their cars, so a
         # persisted car Fleet still lists is not expired and re-created.
         self.lastVehicleExpiry = time.time()
         self.settings = dict(DEFAULT_SETTINGS)
         self.advanceHistorySnap()
         if config["config"].get("maxAmpsAllowedFromGrid", None) is None:
@@ -180,23 +229,25 @@ class TWCMaster:
         # Drops a stop not yet delivered: the desire and any queued attempt.
         # A start is never cancelled. Returns how many desires were cleared
         cleared = 0
         for v in self._chargeTargets(vin, C.STOP_CHARGING):
             cleared += self.desired.clearIf(v.key, CHARGING, False)
             self.reconciler.cancel(v.key)
         return cleared
 
     def withdrawStartCharging(self, vin):
         # A start not wanted any more (too little on offer): its desire goes;
-        # its record stays for the next start
+        # its record stays for the next start. An admitted car's idle TWC is
+        # offered nothing until the car draws, so its start stands
         for v in self._chargeTargets(vin, C.START_CHARGING):
-            self.desired.clearIf(v.key, CHARGING, True)
+            if v.key not in self.admission.cars:
+                self.desired.clearIf(v.key, CHARGING, True)
 
     def _chargeTargets(self, vin, capability):
         # A named car; for an anonymous point, a mode-1 start or
         # stop and a mode-3 start went unaddressed (Presence.candidates)
         targets = targetsFor(self, vin or None, capability)
         mode = int(self.settings.get("chargeStopMode", 1))
         if (
             len(targets) == 1
             and targets[0].isAnonymous
             and (mode == 1 or mode == 3 and capability == C.START_CHARGING)
@@ -569,140 +620,155 @@ class TWCMaster:
                     now - slave.timeReportedAmpsActualChangedSignificantly,
                     slave.startStopDelay,
                 )
             if gate:
                 {
                     "stop": self.stopCarsCharging,
                     "cancelStop": self.cancelStopCarsCharging,
                     "start": self.startCarsCharging,
                     "withdraw": self.withdrawStartCharging,
                 }[gate](key)
+        for point in points:
+            self._followAdmission(point, now)
+
+    def _followAdmission(self, point, now) -> None:
+        # An admitted car that would charge is wanted charging, over a stop.
+        # Where no Gen2 TWC gates the point from its offer, a car not
+        # admitted is wanted stopped once it has drawn so for 60 s (as the
+        # gate holds a stop: power at the edge must not toggle a paid
+        # command each pass), and loses a start
+        gated = any(hasattr(e, "pointAmps") for e in point.localEndpoints)
+        for v in filter(None, map(self.vehicleRegistry.get, _carsAt(point))):
+            if not v.vin:
+                # An anonymous car's start or stop would fan out to others
+                continue
+            want = getattr(self.desired.get(v.key, CHARGING), "value", None)
+            k = known(v, CHARGING, True)
+            since = self._unadmitted.setdefault(v.key, now)
+            if v.key in self.admission.cars:
+                del self._unadmitted[v.key]
+                if want is not True and not satisfied(CHARGING, True, k):
+                    if wouldCharge(self, v):
+                        self.cancelStopCarsCharging(v.key)
+                        self._wantCharging(v.key, True)
+            elif not gated and getattr(k, "value", None) == "Charging":
+                if want is not False and now - since >= 60:
+                    self._wantCharging(v.key, False)
+            elif not gated and want is True:
+                self.withdrawStartCharging(v.key)
 
     def withdrawOffers(self) -> None:
         # The control pass keeps failing, so stop offering power: a Gen2 TWC
         # gets a 0 offer (its idle minimum) and a Gen3 unit a 0 target. A car
         # that carries its own rate keeps its last commanded rate; only the
         # AMPS desire is cleared. Slaves first, so a failing chargingPoints()
-        # cannot leave them on a stale offer. A car offered 0 is not woken
-        self.offered = dict.fromkeys(self.offered, 0)
+        # cannot leave them on a stale offer. Nor is a car woken or started
+        self.admission = NO_ROOM
         for slave in self.getSlaveTWCs():
             if slave.heardFrom:
                 slave.offer = Offer(0, 0)
         for point in self.chargingPoints():
             if not point.isReadOnly:
                 point.setTargetPower(0)
 
     def distributeEVSEPower(self) -> list:
         """Watt-based power distribution across charging points.
 
         The one distributor for every install. It allocates per charging
         point: a TWC and the car it serves are one point, budgeted once.
+        Points are admitted while their minimums fit (_admit), then the
+        admitted share the power at one water level.
         After this method runs:
         - Gen2TWC.pointAmps is set; controlPass makes the offer from it and
           the RS485 heartbeat sends that. ChargingPoint splits the rate by
           chargeRateControl and owns the car's amps. A slave not yet heard
           from is no endpoint (chargingPoints) and gets no target.
         - Each Gen3 unit's own target is handed to Gen3TWCs.setUnitTarget.
         - A car on no TWC has desired amps (VehicleEndpoint.setTargetPower).
 
         Returns the charging points it built.
         """
-        points = self.chargingPoints()
-        wants_power = [p for p in points if p.wantsToCharge and not p.isReadOnly]
-
-        # Total watts available from EMS/policy. Convert with the voltage the
-        # TWCs measure (defaultVoltage only when none report it): the policy
-        # derived these amps from watts with it, and Gen2TWC.setTargetPower()
-        # converts back with it, so the TWC is offered the amps the policy chose.
-        available_watts = self.convertAmpsToWatts(self.getMaxAmpsToDivideAmongSlaves())
-        remaining_watts = available_watts
-        offers = []
-
-        if wants_power:
-            # Per-controller remaining power budgets and point counts
-            controller_budgets = self._budgets()
-            controller_counts: dict = {}
-            for name in controller_budgets:
-                controller_counts[name] = sum(
-                    1 for p in wants_power if name in p.controllers
-                )
-
-            # Fair-share distribution — sort ascending by maxPower so the most
-            # constrained points are served first, reducing wasted capacity.
-            pending = sorted(wants_power, key=lambda p: p.maxPower)
-
-            # Iterate a copy: pending.remove() below would otherwise make the
-            # loop skip every other point, leaving it with no target at all.
-            for point in list(pending):
-                fair_share = remaining_watts / len(pending)
-
-                # Constrain by point capacity
-                offer = min(fair_share, point.maxPower)
-
-                # Constrain by controller budgets
-                for ctrl_name in point.controllers:
-                    count = controller_counts.get(ctrl_name, 0)
-                    if count > 0 and ctrl_name in controller_budgets:
-                        offer = min(offer, controller_budgets[ctrl_name] / count)
-
-                # Enforce minimum: offer nothing rather than an unusably small
-                # amount
-                if 0 < offer < point.minPower:
-                    offer = 0
-                if point.maxPower < point.minPower <= fair_share:
-                    self._noteRefusedPoint(point, fair_share)
-
-                point.setTargetPower(offer)
-                offers.append((point, offer))
-
-                # Update accounting
-                remaining_watts -= offer
-                for ctrl_name in point.controllers:
-                    if ctrl_name in controller_budgets:
-                        controller_budgets[ctrl_name] -= offer
-                    if ctrl_name in controller_counts:
-                        controller_counts[ctrl_name] = max(
-                            0, controller_counts[ctrl_name] - 1
-                        )
-                pending.remove(point)
-
-        # Points that don't want power get a target of 0. For an idle Gen2 TWC
-        # that 0 goes out as its hardware minimum (the TWC treats an offer of 0
-        # as its minimum), which it needs to see a car plug in. The minimum is
+        try:
+            points = self.chargingPoints()
+            seated, budgets = self._admit(points)
+        except Exception:
+            self.admission = NO_ROOM
+            raise
+        # The admitted points share the power at one water level. Where a
+        # budget would be exceeded, its points share it alone, the rest what
+        # remains
+        left, given, pool = dict(budgets), {}, seated
+        while pool:
+            share = waterLevel(pool, left["all"])
+
+            def spent(c):
+                return sum(w for p, w in share.items() if c in _draws(p, left))
+
+            over = next((c for c in left if spent(c) > left[c]), None)
+            group = [p for p in pool if over in _draws(p, left)] if over else pool
+            share = waterLevel(group, left[over]) if over else share
+            for p in group:
+                given[p] = share[p]
+                for c in _draws(p, left):
+                    left[c] -= share[p]
+            pool = [p for p in pool if p not in group]
+        # Points not admitted get a target of 0. For an idle Gen2 TWC that 0
+        # goes out as its hardware minimum (the TWC treats an offer of 0 as
+        # its minimum), which it needs to see a car plug in. The minimum is
         # deliberately never counted against or gated on any budget: the
         # configured limits are already derated, and the next cycle rebalances.
-        for point in points:
-            if point in wants_power or point.isReadOnly:
-                continue
-            point.setTargetPower(0)
-            offers.append((point, 0))
-        # The targets just set, by each car a point serves or fans out to, or
-        # a TWC still holds (offered power, or none was left for it)
-        held = {
-            e.heldKey: w
-            for p, w in offers
-            for e in p.localEndpoints
-            if w or remaining_watts < p.minPower
-        }
-        held.update({k: w for p, w in offers for k in (p.vehicleKey, *p.carKeys)})
-        held.pop(None, None)
-        self.offered = held
-
+        offers = [(p, given.get(p, 0)) for p in points if not p.isReadOnly]
+        for point, watts in offers:
+            point.setTargetPower(watts)
         if logger.isEnabledFor(logging.DEBUG):
             logger.debug(
                 "distributeEVSEPower: %d W over %s",
-                available_watts,
+                budgets["all"],
                 ", ".join("%s=%d W" % (p.ID, watts) for p, watts in offers)
                 or "no points",
             )
         return points
 
+    def _admit(self, points) -> tuple:
+        # Drawing points first, so a charging car keeps its seat; then, in
+        # point order, those that want power or whose car would charge, each
+        # while its minimum fits what is left in every budget it draws from.
+        # self.admission names their cars, and those at any other point whose
+        # minimum still fits: the room a start would find. The policy's amps
+        # convert at the voltage the TWCs measure, as they convert back
+        available = self.convertAmpsToWatts(self.getMaxAmpsToDivideAmongSlaves())
+        budgets = dict(self._budgets(), all=available)
+        cars = self.vehicleRegistry.vehicles()
+        willing = {v.key for v in cars if v.vin and wouldCharge(self, v)}
+        left, seated = dict(budgets), []
+
+        def fits(p):
+            need = p.minPower
+            return need <= p.maxPower and all(need <= left[c] for c in _draws(p, left))
+
+        for p in sorted(points, key=lambda p: not _drawing(p)):
+            if p.isReadOnly or not (p.wantsToCharge or _carsAt(p) & willing):
+                continue
+            if p.maxPower < p.minPower <= left["all"]:
+                self._noteRefusedPoint(p, left["all"])
+            if fits(p):
+                seated.append(p)
+                for c in _draws(p, left):
+                    left[c] -= p.minPower
+        room = [p for p in points if p in seated or not p.isReadOnly and fits(p)]
+        self.admission = Admission(
+            frozenset().union(*map(_carsAt, room)),
+            frozenset().union(*map(_carsAt, points)),
+            left["all"] >= self.convertAmpsToWatts(VehicleEndpoint.MIN_AMPS),
+        )
+        return seated, budgets
+
     # When each refused point was last logged
     _refusedPointLogged = {}
 
     def _noteRefusedPoint(self, point, available: float) -> None:
         # Power was there for the point's minimum, but its own members' limits
         # left it nothing. With a plugged, named car that is a missed charge,
         # so it is said at INFO, at most hourly per point.
         now = time.time()
         vins = [
             e.vehicleKey
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 48e0fd6e..c30a57c0 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -1,14 +1,14 @@
 # What the reconciler believes about a car, and the per-aspect rules it
 # plans by: pure functions of the registry, no reconciler state. The EVSE
 # layer reads known() from here without the reconciler thread.
-from typing import Optional
+from typing import NamedTuple, Optional
 
 from ..Registry.Fields import FEED_LAG
 from ..Presence import NOT_HOME, pluggedNow, presence
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
 from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
 
 # Sources whose every reading came from the car itself. Exact source
 # names; Fleet Telemetry always counts
 LIVE_READ_SOURCES = frozenset(
     {"TeslaBLE", "OwnerAPI", "FleetAPI", "FleetTelemetryMQTT"}
@@ -96,45 +96,75 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
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
+    return _refusesStart(vehicle, known, config)
+
+
+def _refusesStart(vehicle, known, config) -> Optional[str]:
+    # Whatever its limit, the car cannot take a start, or must not get one
     if known is not None and known.value in ("Disconnected", "NoPower"):
         return "the car cannot charge (%s)" % known.value
     if vehicle.value("scheduledChargingPending") is True and config.get(
         "respectVehicleSchedule", True
     ):
         # A start would override the car's own schedule
         return "scheduled charging is pending (respectVehicleSchedule)"
     return None
 
 
-def whyQuiet(master, vehicle) -> Optional[str]:
-    # Why the car is expected to quiesce once every pending desire is applied,
-    # or None when it will charge (unknown limit or battery: it will)
+def _wontCharge(master, vehicle) -> Optional[str]:
+    # Why the car would not charge if started now, once every pending desire
+    # is applied; None when it would (unknown limit or battery: it would)
     key, desired = vehicle.key, master.desired
-    stop, pending = desired.get(key, CHARGING), desired.get(key, CHARGE_LIMIT)
+    pending = desired.get(key, CHARGE_LIMIT)
     held = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
     limit, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
-    limit = limit and limit.value
+    limit = believed = limit and limit.value
+    state = known(vehicle, CHARGING)
     if pending is not None and not (releases(pending) and not held):
         limit = held.outside if releases(pending) else pending.value
     # Unplugged is known only by a reading
     plugged = pluggedNow(master, vehicle, None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
         return "not plugged in here"
-    if stop is not None and stop.value is False:
-        return "stop desired"
-    if plugged is not False and getattr(master, "offered", {}).get(key) == 0:
-        return "nothing offered"
     if limit and battery and limit <= battery:
         return "car won't charge: limit at or below battery"
+    if getattr(state, "value", None) == "Complete" and limit == believed:
+        return "car won't charge: complete at its limit"
+    config = (getattr(master, "config", None) or {}).get("config") or {}
+    return _refusesStart(vehicle, state, config)
+
+
+def wouldCharge(master, vehicle) -> bool:
+    return _wontCharge(master, vehicle) is None
+
+
+class Admission(NamedTuple):
+    # The control tick's, swapped whole for the reconciler's thread. cars:
+    # with a seat, or room for one; placed: at a point; spare: room for a car
+    # at none. Its default is room for nothing
+    cars: frozenset = frozenset()
+    placed: frozenset = frozenset()
+    spare: bool = False
+
+
+NO_ROOM = Admission()
+
+
+def whyQuiet(master, vehicle) -> Optional[str]:
+    # Why the car is expected to quiesce, or None when it will charge
+    reason = _wontCharge(master, vehicle)
+    a, key = getattr(master, "admission", NO_ROOM), vehicle.key
+    if reason or not (key in a.cars or key not in a.placed and a.spare):
+        return reason or "no room to start"
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
     if any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index 3753a9c8..457b9045 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -48,20 +48,24 @@ PROBE_AFTER = 600.0
 # A start waits this long after a limit write
 LIMIT_THEN_START_GAP = 5.0
 # The least time between two sends of one aspect to one car, whichever
 # providers carry them: it spaces start/stop toggles and rate changes
 MIN_SEND_GAP = {CHARGE_LIMIT: 10.0, CHARGING: 10.0, AMPS: 15.0}
 # The most paid sends, and wakes and reads for held attempts, per desire
 PAID_BUDGET = 4
 # A limit held unsent for one of these (both NOT_SENT) cannot be delivered
 _REFUSALS = frozenset({"wake refused", "no command token"})
 
+# A car whose charging state nothing has given (after a restart) may be
+# woken for a start once a run, which learns it; False: never
+WAKE_UNREAD_ONCE = True
+
 # A car reporting one of these is drawing power, so awake
 _DRAWING = frozenset({"Charging", "Starting"})
 # The plan order: a limit, then the rate before a start (less overshoot);
 # a stop never waits behind a rate
 _ORDER, _STOP_ORDER = (CHARGE_LIMIT, AMPS, CHARGING), (CHARGE_LIMIT, CHARGING, AMPS)
 
 
 def _tier(provider, capability) -> int:
     # An unknown provider or cost counts as paid: it fails closed
     cost = provider.cost(capability) if provider is not None else None
@@ -72,20 +76,22 @@ class VehicleReconciler(threading.Thread):
     def __init__(self, master, clock=time.time):
         super().__init__(daemon=True, name="VehicleReconciler")
         self.master = master
         self._clock = clock
         self.desired = master.desired
         self._event = threading.Event()
         self._stopping = False
         # (key, aspect) -> the last hands-off or no-candidate message, so
         # each is logged once; pruned to the store's keys every pass
         self._said: Dict[Tuple[str, str], str] = {}
+        # The cars a start has woken, once its wake was sent
+        self._wokeUnread = set()
         self.ble, self.cloud = (
             VehicleCommandQueue(
                 name="Vehicle-" + name,
                 run=self._run,
                 key=Run.entryKey,
                 isHigh=Run.isStop,
                 # Late-bound, so a replaced report is the one called
                 report=lambda a, outcome: self.report(a, outcome),
                 lost=lambda a, detail: self.report(a, O.Outcome(O.ERROR, detail)),
             )
@@ -321,23 +327,28 @@ class VehicleReconciler(threading.Thread):
             ch.failingSince is not None
             and ch.lastAttemptAt >= back
             and now - max(ch.failingSince, back) >= PAID_AFTER[aspect]
             and now - ch.lastAttemptAt < PROBE_AFTER
         )
         # At most two paid sends per arm, and two arms per desire: one send,
         # then one more after a failure or a reading that reached the car
         # A start goes with the limit first: its wake carries the limit
         ride = aspect == CHARGE_LIMIT and self._startWanted(vehicle, config)
         field = FIELD_FOR[aspect]
-        # Only a car expected to charge is woken; a restore or stop never is
-        quiet = B.whyQuiet(self.master, vehicle)
-        wakes = quiet is None and not d.restore and d.value is not False
+        # Only a car expected to charge is woken; a restore or stop never is,
+        # nor waits on the question
+        wakes = not d.restore and d.value is not False
+        quiet = B.whyQuiet(self.master, vehicle) if wakes else None
+        if aspect == CHARGING and B.known(vehicle, CHARGING) is None:
+            if key in self._wokeUnread or not WAKE_UNREAD_ONCE:
+                quiet = quiet or "its charging state is unknown"
+        wakes = wakes and quiet is None
         asleep = Presence.asleep(vehicle, rec.heldAt or 0) is not False
         # A billed provider never wakes for amps
         holder = self.master.providerOrder.provider(rec.lastProvider)
         mayWake = wakes and (aspect != AMPS or getattr(holder, "local", False))
         if not mayWake and last == O.ASLEEP and asleep:
             # Asleep (or offline): only a sign of life since the hold (the
             # cloud's next check may find one), or a message that may wake
             return None
         reached = rec.paidSends and B.reachedCar(
             vehicle, field, rec.paidAt, rec.paidSaw
@@ -579,20 +590,22 @@ class VehicleReconciler(threading.Thread):
             attempt.aspect or "Debug",
             attempt.capability,
             attempt.key,
             attempt.provider,
             outcome.kind,
             outcome.detail,
         )
         if attempt.aspect is None:
             # A debug one-shot changes no record
             return
+        if attempt.aspect == CHARGING and attempt.wake and not O.isNotSent(outcome):
+            self._wokeUnread.add(attempt.key)
         provider = self.master.providerOrder.provider(attempt.provider)
         vehicle = self.master.vehicleRegistry.get(attempt.key)
         self.desired.noteOutcome(
             attempt.key,
             attempt.aspect,
             attempt,
             outcome,
             self._clock(),
             paid=_tier(provider, attempt.capability) >= C.TIER_BILLED,
             spent=vehicle.paidRequests - attempt.paidBefore if vehicle else 0,
