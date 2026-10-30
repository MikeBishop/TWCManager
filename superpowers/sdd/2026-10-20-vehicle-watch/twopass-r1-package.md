eb19fd4c Admit charging points first, then share power at one water level
d053ddc7 Wake and start a car that would charge, if there is room
 CHANGELOG.md                                   |   4 +-
 lib/TWCManager/TWCMaster.py                    | 194 +++++++++++++------------
 lib/TWCManager/TWCSlave.py                     |  36 +----
 lib/TWCManager/Vehicle/Reconcile/Belief.py     |  26 +---
 lib/TWCManager/Vehicle/Reconcile/Reconciler.py |  13 +-
 tests/unit/reconcile_helpers.py                |   4 +-
 tests/unit/test_admission.py                   | 119 ++++++++++++++-
 tests/unit/test_charging_reconciler.py         |  18 +--
 tests/unit/test_command_path_parity.py         |  40 ++++-
 tests/unit/test_distributor_loop.py            |  12 +-
 tests/unit/test_offer_characterization.py      |  22 +--
 tests/unit/test_presence.py                    |   4 +-
 tests/unit/test_twcslave.py                    |  16 --
 13 files changed, 306 insertions(+), 202 deletions(-)
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index c4c9f7b5..0d94b762 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -18,22 +18,21 @@ import random
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
-from TWCManager.Vehicle.Reconcile.Belief import Admission, NO_ROOM, known
-from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS
+from TWCManager.Vehicle.Reconcile.Belief import POWER_FLOWING_AMPS, known
 from TWCManager.Vehicle.Reconcile.Belief import newerReading, wouldCharge
 from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Reconcile.Reconciler import VehicleReconciler
 from TWCManager.Vehicle.Reconcile.Targets import applyPolicyLimit, onArrival, targetsFor
 from TWCManager.Vehicle.Reconcile.Targets import UNDECIDED
 from TWCManager.Vehicle import Presence
 from TWCManager.Vehicle.Watch import settingsOf
 from TWCManager.Vehicle.WatchBudget import WatchBudget
 
 logger = LoggerFactory.get_logger("Master", "Master")
@@ -183,22 +182,23 @@ class TWCMaster:
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
-        # The control tick's admission, and when each car's point lost it
-        self.admission, self._unadmitted = NO_ROOM, {}
+        # The control tick's admission (the cars with room), the cars that
+        # would charge, and each car's (room, state, draw, since) for the hold
+        self.admission, self._willing, self._held = frozenset(), set(), {}
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
@@ -228,25 +228,26 @@ class TWCMaster:
     def cancelStopCarsCharging(self, vin=None):
         # Drops a stop not yet delivered: the desire and any queued attempt.
         # A start is never cancelled. Returns how many desires were cleared
         cleared = 0
         for v in self._chargeTargets(vin, C.STOP_CHARGING):
             cleared += self.desired.clearIf(v.key, CHARGING, False)
             self.reconciler.cancel(v.key)
         return cleared
 
     def withdrawStartCharging(self, vin):
-        # A start not wanted any more (too little on offer): its desire goes;
-        # its record stays for the next start. An admitted car's idle TWC is
-        # offered nothing until the car draws, so its start stands
+        # A start never sent, with too little on offer, is moot: its desire
+        # goes, its record stays for the next start. Once one has gone, it
+        # waits for room with its paid budget, as does a car with room
         for v in self._chargeTargets(vin, C.START_CHARGING):
-            if v.key not in self.admission.cars:
+            sent = self.desired.record(v.key, CHARGING).lastSentAt
+            if not sent and v.key not in self.admission:
                 self.desired.clearIf(v.key, CHARGING, True)
 
     def _chargeTargets(self, vin, capability):
         # A named car; for an anonymous point, a mode-1 start or
         # stop and a mode-3 start went unaddressed (Presence.candidates)
         targets = targetsFor(self, vin or None, capability)
         mode = int(self.settings.get("chargeStopMode", 1))
         if (
             len(targets) == 1
             and targets[0].isAnonymous
@@ -604,72 +605,80 @@ class TWCMaster:
         for slave in self.getSlaveTWCs():
             if not slave.heardFrom:
                 # Not heard from yet: no offer, so its heartbeat says nothing
                 continue
             slave.offer = slave.offerFor(slave.pointAmps, ctx, now)
             key = slave.vehicleKey
             if key is not None and slave.offer.amps > 0:
                 # Power is on offer: a stop not yet delivered is moot
                 self.cancelStopCarsCharging(key)
             gate = slave.chargeGate(now, key)
-            if gate == "cancelStop":
-                logger.debug(
-                    "Don't stop charging TWC: %s yet because: offer changed "
-                    "%ds ago (< 60) or actual amps changed %ds ago (< %d)",
-                    self.hex_str(slave.TWCID),
-                    now - slave.timeLastAmpsOfferedChanged,
-                    now - slave.timeReportedAmpsActualChangedSignificantly,
-                    slave.startStopDelay,
-                )
             if gate:
                 {
-                    "stop": self.stopCarsCharging,
-                    "cancelStop": self.cancelStopCarsCharging,
                     "start": self.startCarsCharging,
                     "withdraw": self.withdrawStartCharging,
                 }[gate](key)
         for point in points:
-            self._followAdmission(point, now)
-
-    def _followAdmission(self, point, now) -> None:
-        # An admitted car that would charge is wanted charging, over a stop.
-        # Where no Gen2 TWC gates the point from its offer, a car not
-        # admitted is wanted stopped once it has drawn so for 60 s (as the
-        # gate holds a stop: power at the edge must not toggle a paid
-        # command each pass), and loses a start
-        gated = any(hasattr(e, "pointAmps") for e in point.localEndpoints)
-        for v in filter(None, map(self.vehicleRegistry.get, _carsAt(point))):
-            if not v.vin:
-                # An anonymous car's start or stop would fan out to others
+            self._followAdmission(_carsAt(point), point, now)
+        # A car on no point with room on what is left is started; once it
+        # draws, its point is allocated like any other
+        unplaced = self.admission.difference(*map(_carsAt, points))
+        self._followAdmission(unplaced, None, now)
+
+    def _followAdmission(self, keys, point, now) -> None:
+        # Wanted charging follows admission, each change once it has held
+        # startStopDelay with the draw steady: a cut mid-negotiation could
+        # strand a car, and power at the edge must not toggle a command each
+        # pass. Only a first start, or a Gen2's (its offer drops our stop),
+        # goes at once. At a Gen2 only protocol 2 stops; an anonymous car is
+        # left to its Gen2, as elsewhere its start or stop would fan out
+        hold = self.config["config"].get("startStopDelay", 60)
+        ends = getattr(point, "localEndpoints", ())
+        gen2 = [e for e in ends if hasattr(e, "pointAmps")]
+        for v in filter(None, map(self.vehicleRegistry.get, keys)):
+            if not (v.vin or gen2):
                 continue
+            # The car's own readings, the same at each point it may be on
+            room = v.key in self.admission
+            seen = (room, v.value("chargingState"), v.value("actualCurrent") or 0)
+            last = self._held.get(v.key)
+            if not last or last[:2] != seen[:2] or abs(last[2] - seen[2]) > 0.8:
+                last = self._held[v.key] = (*seen, now)
+            held = now - last[3] >= hold
             want = getattr(self.desired.get(v.key, CHARGING), "value", None)
-            k = known(v, CHARGING, True)
-            since = self._unadmitted.setdefault(v.key, now)
-            if v.key in self.admission.cars:
-                del self._unadmitted[v.key]
-                if want is not True and not satisfied(CHARGING, True, k):
-                    if wouldCharge(self, v):
-                        self.cancelStopCarsCharging(v.key)
-                        self._wantCharging(v.key, True)
-            elif not gated and getattr(k, "value", None) == "Charging":
-                if want is not False and now - since >= 60:
-                    self._wantCharging(v.key, False)
-            elif not gated and want is True:
-                self.withdrawStartCharging(v.key)
+            if (
+                room
+                and v.key in self._willing
+                and (want is None or want is False and held)
+            ):
+                if not satisfied(CHARGING, True, known(v, CHARGING, True)):
+                    self.cancelStopCarsCharging(v.key)
+                    self._wantCharging(v.key, True)
+            elif (
+                not room
+                and _drawing(point)
+                and all(e.protocolVersion == 2 for e in gen2)
+            ):
+                # Each pass: in mode 1 a stop that has not taken lowers the
+                # limit. Until then the stop waits, and one undelivered is moot
+                if held:
+                    self.stopCarsCharging(v.key)
+                else:
+                    self.cancelStopCarsCharging(v.key)
 
     def withdrawOffers(self) -> None:
         # The control pass keeps failing, so stop offering power: a Gen2 TWC
         # gets a 0 offer (its idle minimum) and a Gen3 unit a 0 target. A car
         # that carries its own rate keeps its last commanded rate; only the
         # AMPS desire is cleared. Slaves first, so a failing chargingPoints()
         # cannot leave them on a stale offer. Nor is a car woken or started
-        self.admission = NO_ROOM
+        self.admission = frozenset()
         for slave in self.getSlaveTWCs():
             if slave.heardFrom:
                 slave.offer = Offer(0, 0)
         for point in self.chargingPoints():
             if not point.isReadOnly:
                 point.setTargetPower(0)
 
     def distributeEVSEPower(self) -> list:
         """Watt-based power distribution across charging points.
 
@@ -683,90 +692,92 @@ class TWCMaster:
           chargeRateControl and owns the car's amps. A slave not yet heard
           from is no endpoint (chargingPoints) and gets no target.
         - Each Gen3 unit's own target is handed to Gen3TWCs.setUnitTarget.
         - A car on no TWC has desired amps (VehicleEndpoint.setTargetPower).
 
         Returns the charging points it built.
         """
         try:
             points = self.chargingPoints()
             seated, budgets = self._admit(points)
+            # The admitted points share the power at one water level. Where
+            # a budget would be exceeded, its points share it alone, the rest
+            # what remains
+            left, given, pool = dict(budgets), {}, seated
+            while pool:
+                share = waterLevel(pool, left["all"])
+                spent = {
+                    c: sum(w for p, w in share.items() if c in _draws(p, left))
+                    for c in left
+                }
+                over = next((c for c in left if spent[c] > left[c]), None)
+                group = [p for p in pool if over in _draws(p, left)] if over else pool
+                share = waterLevel(group, left[over]) if over else share
+                for p in group:
+                    given[p] = share[p]
+                    for c in _draws(p, left):
+                        left[c] -= share[p]
+                pool = [p for p in pool if p not in group]
+            # Points not admitted get a target of 0. For an idle Gen2 TWC that
+            # 0 goes out as its hardware minimum (the TWC treats an offer of 0
+            # as its minimum), which it needs to see a car plug in. The
+            # minimum is deliberately never counted against or gated on any
+            # budget: the configured limits are already derated, and the next
+            # cycle rebalances.
+            offers = [(p, given.get(p, 0)) for p in points if not p.isReadOnly]
+            for point, watts in offers:
+                point.setTargetPower(watts)
         except Exception:
-            self.admission = NO_ROOM
+            # Nothing is woken or started on an admission not acted on
+            self.admission = frozenset()
             raise
-        # The admitted points share the power at one water level. Where a
-        # budget would be exceeded, its points share it alone, the rest what
-        # remains
-        left, given, pool = dict(budgets), {}, seated
-        while pool:
-            share = waterLevel(pool, left["all"])
-
-            def spent(c):
-                return sum(w for p, w in share.items() if c in _draws(p, left))
-
-            over = next((c for c in left if spent(c) > left[c]), None)
-            group = [p for p in pool if over in _draws(p, left)] if over else pool
-            share = waterLevel(group, left[over]) if over else share
-            for p in group:
-                given[p] = share[p]
-                for c in _draws(p, left):
-                    left[c] -= share[p]
-            pool = [p for p in pool if p not in group]
-        # Points not admitted get a target of 0. For an idle Gen2 TWC that 0
-        # goes out as its hardware minimum (the TWC treats an offer of 0 as
-        # its minimum), which it needs to see a car plug in. The minimum is
-        # deliberately never counted against or gated on any budget: the
-        # configured limits are already derated, and the next cycle rebalances.
-        offers = [(p, given.get(p, 0)) for p in points if not p.isReadOnly]
-        for point, watts in offers:
-            point.setTargetPower(watts)
         if logger.isEnabledFor(logging.DEBUG):
             logger.debug(
                 "distributeEVSEPower: %d W over %s",
                 budgets["all"],
                 ", ".join("%s=%d W" % (p.ID, watts) for p, watts in offers)
                 or "no points",
             )
         return points
 
     def _admit(self, points) -> tuple:
         # Drawing points first, so a charging car keeps its seat; then, in
         # point order, those that want power or whose car would charge, each
         # while its minimum fits what is left in every budget it draws from.
-        # self.admission names their cars, and those at any other point whose
-        # minimum still fits: the room a start would find. The policy's amps
-        # convert at the voltage the TWCs measure, as they convert back
+        # self.admission names their cars, then in turn those at other points
+        # whose minimum fits what is left (two never share it): the room a
+        # start would find. The policy's amps convert at the voltage the TWCs
+        # measure, as they convert back
         available = self.convertAmpsToWatts(self.getMaxAmpsToDivideAmongSlaves())
         budgets = dict(self._budgets(), all=available)
         cars = self.vehicleRegistry.vehicles()
         willing = {v.key for v in cars if v.vin and wouldCharge(self, v)}
-        left, seated = dict(budgets), []
+        left, seated, room, self._willing = dict(budgets), [], [], willing
 
-        def fits(p):
-            need = p.minPower
-            return need <= p.maxPower and all(need <= left[c] for c in _draws(p, left))
+        def wanted(p):
+            return p.wantsToCharge or _carsAt(p) & willing
 
-        for p in sorted(points, key=lambda p: not _drawing(p)):
-            if p.isReadOnly or not (p.wantsToCharge or _carsAt(p) & willing):
+        for p in sorted(points, key=lambda p: (not wanted(p), not _drawing(p))):
+            if p.isReadOnly:
                 continue
-            if p.maxPower < p.minPower <= left["all"]:
+            need = p.minPower
+            if p.maxPower < need <= left["all"] and wanted(p):
                 self._noteRefusedPoint(p, left["all"])
-            if fits(p):
-                seated.append(p)
+            elif need <= p.maxPower and all(need <= left[c] for c in _draws(p, left)):
+                (seated if wanted(p) else room).append(p)
                 for c in _draws(p, left):
-                    left[c] -= p.minPower
-        room = [p for p in points if p in seated or not p.isReadOnly and fits(p)]
-        self.admission = Admission(
-            frozenset().union(*map(_carsAt, room)),
-            frozenset().union(*map(_carsAt, points)),
-            left["all"] >= self.convertAmpsToWatts(VehicleEndpoint.MIN_AMPS),
-        )
+                    left[c] -= need
+        admission = set().union(*map(_carsAt, room + seated))
+        if left["all"] >= self.convertAmpsToWatts(VehicleEndpoint.MIN_AMPS):
+            # A car on no point of ours may start on what is left
+            admission |= {v.key for v in cars}.difference(*map(_carsAt, points))
+        self.admission = frozenset(admission)
         return seated, budgets
 
     # When each refused point was last logged
     _refusedPointLogged = {}
 
     def _noteRefusedPoint(self, point, available: float) -> None:
         # Power was there for the point's minimum, but its own members' limits
         # left it nothing. With a plugged, named car that is a missed charge,
         # so it is said at INFO, at most hourly per point.
         now = time.time()
@@ -1782,20 +1793,21 @@ class TWCMaster:
     def _vinPending(self, slaveTWC):
         try:
             twcid = "%02X%02X" % (slaveTWC.TWCID[0], slaveTWC.TWCID[1])
             return self.vehicleRegistry.isPending(twcid)
         except Exception as e:
             logger.warning("Vehicle registry pending check failed: %s", e)
             return False
 
     def _vehicleRemoved(self, key):
         # Forgotten means forgotten: its desired state and held limit go
+        self._held.pop(key, None)
         self.desired.forget(key)
         self.heldLimits.remove(key)
 
     def expireVehicles(self):
         # Forget unclaimed, unasserted vehicles unseen past the forget window
         expired = self.vehicleRegistry.expire()
         if expired:
             self.queue_background_task({"cmd": "saveSettings"})
         return expired
 
diff --git a/lib/TWCManager/TWCSlave.py b/lib/TWCManager/TWCSlave.py
index 61214589..0985fccc 100644
--- a/lib/TWCManager/TWCSlave.py
+++ b/lib/TWCManager/TWCSlave.py
@@ -46,38 +46,28 @@ class TWCSlave:
     reportedAmpsMax = 0
     reportedAmpsActual = 0
     reportedState = 0
     # Set by the first reply: a slave not yet heard from is offered nothing
     heardFrom = False
 
     # history* vars are used to track power usage over time
     historyAvgAmps = 0
     historyNumSamples = 0
 
-    # reportedAmpsActual frequently changes by small amounts, like 5.14A may
-    # frequently change to 5.23A and back.
-    # reportedAmpsActualSignificantChangeMonitor is set to reportedAmpsActual
-    # whenever reportedAmpsActual is at least 0.8A different than
-    # reportedAmpsActualSignificantChangeMonitor. Whenever
-    # reportedAmpsActualSignificantChangeMonitor is changed,
-    # timeReportedAmpsActualChangedSignificantly is set to the time of the
-    # change. The value of reportedAmpsActualSignificantChangeMonitor should not
-    # be used for any other purpose. timeReportedAmpsActualChangedSignificantly
-    # is used for things like preventing start and stop charge on a car more
-    # than once per minute.
+    # reportedAmpsActual as last changed by over 0.8A: it wanders by small
+    # amounts (5.14A to 5.23A and back), and power starting or stopping
+    # fires the policy's webhooks
     reportedAmpsActualSignificantChangeMonitor = -1
-    timeReportedAmpsActualChangedSignificantly = time.time()
 
     lastAmpsOffered = -1
     timeLastAmpsOfferedChanged = 0
     lastHeartbeatDebugOutput = ""
-    startStopDelay = 0
     timeLastHeartbeatDebugOutput = 0
     wiringMaxAmps = 0
     lifetimekWh = 0
     voltsPhaseA = 0
     voltsPhaseB = 0
     voltsPhaseC = 0
     isCharging = 0
     lastChargingStart = 0
     chargingDroppedBelowThresholdTime = 0
     VINData = ["", "", ""]
@@ -110,21 +100,20 @@ class TWCSlave:
     _cappedLogged = None
 
     def __init__(self, TWCID, maxAmps, config, master):
         self.config = config
         self.configConfig = self.config.get("config", {})
         self.master = master
         self.TWCID = TWCID
         self.maxAmps = maxAmps
 
         self.wiringMaxAmps = self.configConfig.get("wiringMaxAmpsPerTWC", 6)
-        self.startStopDelay = self.configConfig.get("startStopDelay", 60)
 
     def plugCheckDue(self, now) -> Optional[float]:
         # Serial thread: an edge's time once its check is due. The codes are
         # the car's talk with the TWC, not the plug: a 00, a max dropping to 0
         # in one, or a plug state change only says to ask the car. A car awake
         # at its limit flickers 00/09 at its max; an unplug leaves 00 at 0 A
         was, self.status = self.status, (self.reportedState, self.reportedAmpsMax)
         (state, amps), plugged = self.status, self.PLUGGED_STATES
         empty = not state and not amps
         edge = was is not None and (
@@ -223,35 +212,25 @@ class TWCSlave:
                     self.TWCID[1],
                     self.wiringMaxAmps,
                     desired,
                     self.wiringMaxAmps,
                 )
             )
             amps = self.wiringMaxAmps
         return amps
 
     def chargeGate(self, now, key) -> Optional[str]:
-        # The tick's start/stop for key, this protocol-2 TWC's car, once
-        # offered. A drawing car offered 0 stops once the offer is 60 s old
-        # and its draw startStopDelay steady: a cut mid-negotiation could
-        # strand it, the offer may rise meanwhile, and fewer cycles spare
-        # the relay
+        # The tick's start for key, this protocol-2 TWC's car, once offered
+        # (its stop is the master's, by admission)
         if self.protocolVersion != 2 or key is None or self.offer is None:
             return None
         offered, actual = self.offer.amps, self.reportedAmpsActual
-        if offered == 0 and actual > 4.0:
-            hold = (
-                now - self.timeLastAmpsOfferedChanged < 60
-                or now - self.timeReportedAmpsActualChangedSignificantly
-                < self.startStopDelay
-            )
-            return "cancelStop" if hold else "stop"
         if (
             offered >= self.minAmpsToOffer()
             and actual < 1.0
             and self.reportedState != 0x02
         ):
             return "start"
         if offered < self.minAmpsToOffer() and actual < 1.0:
             # A start not yet sent is moot, and never wakes the car
             return "withdraw"
         return None
@@ -684,33 +663,28 @@ class TWCSlave:
             self.master.getModuleByName("Policy").fireWebhook("start")
             self.master.queue_background_task({"cmd": "checkCharge"})
 
         # If power drops off, tell the policy's webhook
         if (
             self.reportedAmpsActualSignificantChangeMonitor > 2
             and self.reportedAmpsActual < 2
         ):
             self.master.getModuleByName("Policy").fireWebhook("stop")
 
-        # Keep track of the amps the slave is actually using and the last time it
-        # changed by more than 0.8A.
-        # Also update self.reportedAmpsActualSignificantChangeMonitor if it's
-        # still set to its initial value of -1.
         if (
             self.reportedAmpsActualSignificantChangeMonitor < 0
             or abs(
                 self.reportedAmpsActual
                 - self.reportedAmpsActualSignificantChangeMonitor
             )
             > 0.8
         ):
-            self.timeReportedAmpsActualChangedSignificantly = now
             self.reportedAmpsActualSignificantChangeMonitor = self.reportedAmpsActual
 
         # Charging sessions start and end here, on the serial thread. The
         # control tick sets the amps this TWC is sent
         self.master.observeChargingSessions()
 
         if logger.getEffectiveLevel() <= logging.INFO:
             self.print_status(heartbeatData)
 
     def _amps_heartbeat(self, desiredAmpsOffered):
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index c30a57c0..77659335 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -1,14 +1,14 @@
 # What the reconciler believes about a car, and the per-aspect rules it
 # plans by: pure functions of the registry, no reconciler state. The EVSE
 # layer reads known() from here without the reconciler thread.
-from typing import NamedTuple, Optional
+from typing import Optional
 
 from ..Registry.Fields import FEED_LAG
 from ..Presence import NOT_HOME, pluggedNow, presence
 from .Desired import AMPS, CHARGE_LIMIT, CHARGING, FIELD_FOR
 from .Rules import releases, VEHICLE_SOURCES_EXCLUDED
 
 # Sources whose every reading came from the car itself. Exact source
 # names; Fleet Telemetry always counts
 LIVE_READ_SOURCES = frozenset(
     {"TeslaBLE", "OwnerAPI", "FleetAPI", "FleetTelemetryMQTT"}
@@ -34,26 +34,26 @@ def standIn(vehicle):
     reads = _newer(vehicle, "actualCurrent", float("-inf"), twc=True)
     if not reads:
         return None
     obs = max(reads, key=lambda r: r.at)
     flowing = obs.value >= POWER_FLOWING_AMPS
     return obs._replace(value="Charging" if flowing else "Stopped")
 
 
 def uncompleted(vehicle, obs):
     # "Complete" read before our last limit write above the battery level
-    # is no longer true: the car can charge again
+    # (or with the level unknown) is no longer true: the car can charge again
     write = vehicle.lastWrite(FIELD_FOR[CHARGE_LIMIT])
     soc = vehicle.latest("batteryLevel")
-    if obs is None or obs.value != "Complete" or write is None or soc is None:
+    if obs is None or obs.value != "Complete" or write is None:
         return obs
-    raised = obs.at <= write.at and soc.value < write.value
+    raised = obs.at <= write.at and (soc is None or soc.value < write.value)
     return obs._replace(value="Stopped") if raised else obs
 
 
 def known(vehicle, aspect, desired=None):
     obs = vehicle.believed(FIELD_FOR[aspect], exclude=VEHICLE_SOURCES_EXCLUDED)
     if aspect != CHARGING:
         return obs
     obs, twc = uncompleted(vehicle, obs), standIn(vehicle)
     if obs is None:
         # A car no vehicle source describes (anonymous, non-Tesla): the TWC
@@ -138,33 +138,21 @@ def _wontCharge(master, vehicle) -> Optional[str]:
     if getattr(state, "value", None) == "Complete" and limit == believed:
         return "car won't charge: complete at its limit"
     config = (getattr(master, "config", None) or {}).get("config") or {}
     return _refusesStart(vehicle, state, config)
 
 
 def wouldCharge(master, vehicle) -> bool:
     return _wontCharge(master, vehicle) is None
 
 
-class Admission(NamedTuple):
-    # The control tick's, swapped whole for the reconciler's thread. cars:
-    # with a seat, or room for one; placed: at a point; spare: room for a car
-    # at none. Its default is room for nothing
-    cars: frozenset = frozenset()
-    placed: frozenset = frozenset()
-    spare: bool = False
-
-
-NO_ROOM = Admission()
-
-
 def whyQuiet(master, vehicle) -> Optional[str]:
-    # Why the car is expected to quiesce, or None when it will charge
+    # Why the car is expected to quiesce, or None when it will charge. Room
+    # is the control tick's admission, a set swapped whole
     reason = _wontCharge(master, vehicle)
-    a, key = getattr(master, "admission", NO_ROOM), vehicle.key
-    if reason or not (key in a.cars or key not in a.placed and a.spare):
+    if reason or vehicle.key not in getattr(master, "admission", ()):
         return reason or "no room to start"
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
     if any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index 457b9045..7c515c5e 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -48,38 +48,38 @@ PROBE_AFTER = 600.0
 # A start waits this long after a limit write
 LIMIT_THEN_START_GAP = 5.0
 # The least time between two sends of one aspect to one car, whichever
 # providers carry them: it spaces start/stop toggles and rate changes
 MIN_SEND_GAP = {CHARGE_LIMIT: 10.0, CHARGING: 10.0, AMPS: 15.0}
 # The most paid sends, and wakes and reads for held attempts, per desire
 PAID_BUDGET = 4
 # A limit held unsent for one of these (both NOT_SENT) cannot be delivered
 _REFUSALS = frozenset({"wake refused", "no command token"})
 
-# A car whose charging state nothing has given (after a restart) may be
-# woken for a start once a run, which learns it; False: never
-WAKE_UNREAD_ONCE = True
-
 # A car reporting one of these is drawing power, so awake
 _DRAWING = frozenset({"Charging", "Starting"})
 # The plan order: a limit, then the rate before a start (less overshoot);
 # a stop never waits behind a rate
 _ORDER, _STOP_ORDER = (CHARGE_LIMIT, AMPS, CHARGING), (CHARGE_LIMIT, CHARGING, AMPS)
 
 
 def _tier(provider, capability) -> int:
     # An unknown provider or cost counts as paid: it fails closed
     cost = provider.cost(capability) if provider is not None else None
     return C.TIER_BILLED if cost is None else cost.tier
 
 
 class VehicleReconciler(threading.Thread):
+    # A car whose charging state nothing has given (after a restart) may be
+    # woken for a start once a run, which learns it; False: never
+    wakeUnreadOnce = True
+
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
@@ -332,22 +332,25 @@ class VehicleReconciler(threading.Thread):
         # At most two paid sends per arm, and two arms per desire: one send,
         # then one more after a failure or a reading that reached the car
         # A start goes with the limit first: its wake carries the limit
         ride = aspect == CHARGE_LIMIT and self._startWanted(vehicle, config)
         field = FIELD_FOR[aspect]
         # Only a car expected to charge is woken; a restore or stop never is,
         # nor waits on the question
         wakes = not d.restore and d.value is not False
         quiet = B.whyQuiet(self.master, vehicle) if wakes else None
         if aspect == CHARGING and B.known(vehicle, CHARGING) is None:
-            if key in self._wokeUnread or not WAKE_UNREAD_ONCE:
+            if key in self._wokeUnread or not self.wakeUnreadOnce:
                 quiet = quiet or "its charging state is unknown"
+        if aspect == CHARGING and quiet == "no room to start":
+            # The start waits for room, keeping its desire and its budget
+            return None
         wakes = wakes and quiet is None
         asleep = Presence.asleep(vehicle, rec.heldAt or 0) is not False
         # A billed provider never wakes for amps
         holder = self.master.providerOrder.provider(rec.lastProvider)
         mayWake = wakes and (aspect != AMPS or getattr(holder, "local", False))
         if not mayWake and last == O.ASLEEP and asleep:
             # Asleep (or offline): only a sign of life since the hold (the
             # cloud's next check may find one), or a message that may wake
             return None
         reached = rec.paidSends and B.reachedCar(
