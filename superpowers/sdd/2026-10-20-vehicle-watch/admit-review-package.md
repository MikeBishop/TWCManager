d053ddc7 Wake and start a car that would charge, if there is room
 lib/TWCManager/TWCMaster.py                |  32 +++---
 lib/TWCManager/Vehicle/Reconcile/Belief.py |  50 +++++++++-
 tests/unit/test_admission.py               | 151 +++++++++++++++++++++++++++++
 tests/unit/test_charging_reconciler.py     |   6 +-
 tests/unit/test_command_path_parity.py     |  27 +++---
 tests/unit/test_control_tick.py            |  10 --
 tests/unit/test_gen2_unplug.py             |   2 +-
 tests/unit/test_limit_reconciler.py        |  21 ++--
 tests/unit/test_presence.py                |  19 ++--
 tests/unit/test_sleep_pilot_replay.py      |   2 +-
 tests/unit/test_sleeping_car.py            |   6 +-
 11 files changed, 256 insertions(+), 70 deletions(-)
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index 8f11cd25..7e8744ee 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -16,25 +16,26 @@ import time
 import math
 import random
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
+from TWCManager.Vehicle.Reconcile.Belief import admissible, known, newerReading
+from TWCManager.Vehicle.Reconcile.Rules import satisfied
 from TWCManager.Vehicle.Reconcile.Reconciler import VehicleReconciler
 from TWCManager.Vehicle.Reconcile.Targets import applyPolicyLimit, onArrival, targetsFor
 from TWCManager.Vehicle.Reconcile.Targets import UNDECIDED
 from TWCManager.Vehicle import Presence
 from TWCManager.Vehicle.Watch import settingsOf
 from TWCManager.Vehicle.WatchBudget import WatchBudget
 
 logger = LoggerFactory.get_logger("Master", "Master")
 
 
 # A fresh install's settings, and the keys every loaded settings file gets
 DEFAULT_SETTINGS = {
@@ -551,48 +552,62 @@ class TWCMaster:
             },
         )
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
+            v = self.vehicleRegistry.get(key) if gate == "withdraw" else None
+            if v is not None and admissible(self, v):
+                # Its idle TWC is offered nothing until the car draws
+                gate = None
             if gate == "cancelStop":
                 logger.debug(
                     "Don't stop charging TWC: %s yet because: offer changed "
                     "%ds ago (< 60) or actual amps changed %ds ago (< %d)",
                     self.hex_str(slave.TWCID),
                     now - slave.timeLastAmpsOfferedChanged,
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
+        for v in self.vehicleRegistry.vehicles():
+            # The split serves only drawing points, so an admissible car is
+            # started here; a stop or start already wanted stands
+            if (
+                self.desired.get(v.key, CHARGING) is None
+                and v.vin
+                and Presence.pluggedHere(self, v)
+                and not satisfied(CHARGING, True, known(v, CHARGING, True))
+                and admissible(self, v)
+            ):
+                self._wantCharging(v.key, True)
 
     def withdrawOffers(self) -> None:
         # The control pass keeps failing, so stop offering power: a Gen2 TWC
         # gets a 0 offer (its idle minimum) and a Gen3 unit a 0 target. A car
         # that carries its own rate keeps its last commanded rate; only the
         # AMPS desire is cleared. Slaves first, so a failing chargingPoints()
-        # cannot leave them on a stale offer. A car offered 0 is not woken
-        self.offered = dict.fromkeys(self.offered, 0)
+        # cannot leave them on a stale offer
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
@@ -666,35 +681,24 @@ class TWCMaster:
                 pending.remove(point)
 
         # Points that don't want power get a target of 0. For an idle Gen2 TWC
         # that 0 goes out as its hardware minimum (the TWC treats an offer of 0
         # as its minimum), which it needs to see a car plug in. The minimum is
         # deliberately never counted against or gated on any budget: the
         # configured limits are already derated, and the next cycle rebalances.
         for point in points:
             if point in wants_power or point.isReadOnly:
                 continue
             point.setTargetPower(0)
             offers.append((point, 0))
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
 
         if logger.isEnabledFor(logging.DEBUG):
             logger.debug(
                 "distributeEVSEPower: %d W over %s",
                 available_watts,
                 ", ".join("%s=%d W" % (p.ID, watts) for p, watts in offers)
                 or "no points",
             )
         return points
 
     # When each refused point was last logged
     _refusedPointLogged = {}
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 48e0fd6e..95b081ba 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -94,47 +94,87 @@ def handsOff(vehicle, aspect, desired, known, config=None) -> Optional[str]:
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
     stop, pending = desired.get(key, CHARGING), desired.get(key, CHARGE_LIMIT)
     held = master.heldLimits.get(vehicle.vin) if vehicle.vin else None
     limit, battery = known(vehicle, CHARGE_LIMIT), vehicle.value("batteryLevel")
     limit = limit and limit.value
     if pending is not None and not (releases(pending) and not held):
         limit = held.outside if releases(pending) else pending.value
     # Unplugged is known only by a reading
     plugged = pluggedNow(master, vehicle, None)
     if presence(master, vehicle) == NOT_HOME or plugged is False:
         return "not plugged in here"
     if stop is not None and stop.value is False:
         return "stop desired"
-    if plugged is not False and getattr(master, "offered", {}).get(key) == 0:
-        return "nothing offered"
     if limit and battery and limit <= battery:
         return "car won't charge: limit at or below battery"
+    config = (getattr(master, "config", None) or {}).get("config") or {}
+    return _refusesStart(vehicle, known(vehicle, CHARGING), config)
+
+
+def wouldCharge(master, vehicle) -> bool:
+    return _wontCharge(master, vehicle) is None
+
+
+def _room(master, vehicle) -> bool:
+    # The policy's power, less the minimums of the points already drawing
+    # (the split's own test), fits this car's point: a drawing car keeps its
+    # place, and a new car is admitted only into real headroom
+    own, idle = [], [1]
+    free = master.convertAmpsToWatts(master.getMaxAmpsToDivideAmongSlaves())
+    for point in master.chargingPoints():
+        # A TWC still holding the car is its point while it reports no car
+        held = (e.heldKey for e in point.localEndpoints)
+        if vehicle.key in (point.vehicleKey, *held):
+            own.append(point.minPower)
+        elif point.wantsToCharge and not point.isReadOnly:
+            free -= point.minPower
+        else:
+            idle.append(point.minPower)
+    # A car with no point of its own may be on any idle one
+    return free >= max(own or idle)
+
+
+def admissible(master, vehicle) -> bool:
+    # The admission a split that admits before it allocates can share
+    return wouldCharge(master, vehicle) and _room(master, vehicle)
+
+
+def whyQuiet(master, vehicle) -> Optional[str]:
+    # Why the car is expected to quiesce, or None when it will charge
+    reason = _wontCharge(master, vehicle)
+    if reason or not _room(master, vehicle):
+        return reason or "no room to start"
     feeds = map(master.getModuleByName, ("TeslaMateVehicle", "FleetTelemetryMQTT"))
     if any(f and f.registry.now() < f.settleUntil for f in feeds):
         # Its first readings may show a full car
         return "waiting for telemetry after start"
     return None
diff --git a/tests/unit/test_admission.py b/tests/unit/test_admission.py
new file mode 100644
index 00000000..2a4dacc5
--- /dev/null
+++ b/tests/unit/test_admission.py
@@ -0,0 +1,151 @@
+# A plugged-in car is woken and started when it would charge and there is
+# room for it: its point's offer, which serves only cars already drawing,
+# never decides it. Real master, store and reconciler; a scripted BLE.
+from types import SimpleNamespace
+
+from TWCManager.Vehicle.Reconcile import Belief as B
+from TWCManager.Vehicle.Reconcile import Outcome as O
+from TWCManager.Vehicle.Reconcile.Desired import CHARGE_LIMIT, CHARGING
+from tests.unit.test_limit_reconciler import VIN, ble, names, prov, setup
+
+WIRING = dict(wiringMaxAmpsAllTWCs=48, wiringMaxAmpsPerTWC=48, minAmpsPerTWC=6)
+
+
+def finished(*outcomes, battery=70, limit=70, state="Complete"):
+    # The car plugged in at home, asleep, done with its last session
+    m, r, v, c = setup(ble(*(outcomes or [O.Outcome(O.DONE)])), battery=battery)
+    v.observe("chargeLimit", limit, "TeslaBLE")
+    v.observe("chargingState", state, "TeslaBLE")
+    v.observe("state", "asleep", "TeslaBLE")
+    return m, r, v, c, prov(m, "TeslaBLE")
+
+
+def run(m, r, c, seconds=600, step=10):
+    # The control tick and the reconciler, as live
+    for _ in range(seconds // step):
+        m.controlPass(now=c())
+        r.pass_()
+        c.t += step
+
+
+def test_last_nights_raise_wakes_and_starts_the_car():
+    m, r, v, c, p = finished()
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    run(m, r, c, 60)
+    assert names(p) == []  # at its limit: left asleep
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    run(m, r, c)
+    calls = names(p)
+    assert calls[:2] == ["wake", "setChargeLimit"] and p.calls[1][2] == 90
+    assert calls[2:] == ["wake", "startCharging"]
+    v.observe("chargingState", "Charging", "TeslaBLE")  # it draws: rated
+    run(m, r, c, 60)
+    assert "setAmps" in names(p)[4:]
+
+
+def test_a_car_at_its_limit_is_neither_woken_nor_started():
+    m, r, v, c, p = finished()
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    run(m, r, c, 3600, 60)
+    assert names(p) == [] and m.desired.get(VIN, CHARGING) is None
+
+
+def test_a_pending_scheduled_charge_is_neither_woken_nor_started():
+    m, r, v, c, p = finished()
+    v.observe("scheduledChargingPending", True, "TeslaBLE")
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    run(m, r, c, 3600, 60)
+    assert "wake" not in names(p) and "startCharging" not in names(p)
+    assert m.desired.get(VIN, CHARGING) is None
+    assert B.whyQuiet(m, v).startswith("scheduled charging is pending")
+
+
+def test_a_car_wanted_stopped_is_neither_woken_nor_started():
+    m, r, v, c, p = finished()
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    m.desired.set(VIN, CHARGING, False, "distributor")
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    run(m, r, c, 3600, 60)
+    assert "wake" not in names(p) and "startCharging" not in names(p)
+    assert m.desired.get(VIN, CHARGING).value is False
+
+
+def test_no_power_to_share_wakes_nothing():
+    # Track Green Energy at night
+    m, r, v, c, p = finished()
+    m.setMaxAmpsToDivideAmongSlaves(0)
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    run(m, r, c, 3600, 60)
+    assert "wake" not in names(p) and "startCharging" not in names(p)
+    assert B.whyQuiet(m, v) == "no room to start"
+
+
+def point(key, amps, drawing):
+    return SimpleNamespace(
+        vehicleKey=key,
+        localEndpoints=[],
+        minPower=amps * 240,
+        wantsToCharge=drawing,
+        isReadOnly=False,
+    )
+
+
+def test_a_car_is_admitted_only_into_room_left_by_the_drawing_cars():
+    m, r, v, c, p = finished(limit=90)
+    m.convertAmpsToWatts = lambda amps: amps * 240
+    m.chargingPoints = lambda: [point("other", 6, True), point(VIN, 5, False)]
+    m.setMaxAmpsToDivideAmongSlaves(9)
+    assert B.wouldCharge(m, v) and not B.admissible(m, v)
+    m.desired.set(VIN, CHARGE_LIMIT, 95, "policy")
+    r.pass_()
+    assert names(p) == []  # asleep, and no wake
+    m.setMaxAmpsToDivideAmongSlaves(16)
+    assert B.admissible(m, v)
+    c.t += 60
+    m.desired.set(VIN, CHARGE_LIMIT, 100, "policy")
+    r.pass_()
+    assert names(p) == ["wake", "setChargeLimit"]
+
+
+def test_a_car_on_no_point_of_its_own_needs_an_idle_points_minimum():
+    # Behind a TWC that cannot name it
+    m, r, v, c, p = finished(limit=90)
+    m.convertAmpsToWatts = lambda amps: amps * 240
+    m.chargingPoints = lambda: [point("anon:8244", 6, False)]
+    m.setMaxAmpsToDivideAmongSlaves(3)
+    m.desired.set(VIN, CHARGE_LIMIT, 95, "policy")
+    r.pass_()
+    assert B.whyQuiet(m, v) == "no room to start" and names(p) == []
+    m.setMaxAmpsToDivideAmongSlaves(6)
+    assert B.admissible(m, v)
+
+
+def test_a_car_on_a_gen2_echoing_0_is_woken_and_started_for_a_raise():
+    m, r, v, c, p = finished(O.Outcome(O.DONE))
+    m.config["config"].update(WIRING)
+    (s,) = m.getSlaveTWCs()
+    s.protocolVersion, s.minAmpsTWCSupports, s.voltsPhaseA = 2, 6, 243
+    s.heardFrom = True
+    s.config, s.configConfig, s.wiringMaxAmps = m.config, m.config["config"], 48
+    v.observe("twcVin", s.twcid, "TWC")
+    s.reportedState, s.reportedAmpsMax = 0x03, 0.0
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
+    run(m, r, c)
+    assert s.vehicleKey == VIN and s.offer.amps == 0
+    calls = names(p)
+    assert calls[:2] == ["wake", "setChargeLimit"] and "startCharging" in calls
+
+
+def test_a_woken_car_that_refuses_the_start_is_not_woken_again():
+    m, r, v, c, p = finished(battery=70, limit=80, state="Stopped")
+    p.startCharging = lambda vin: p._next("startCharging", vin, None) and O.Outcome(
+        O.REFUSED, "complete"
+    )
+    m.setMaxAmpsToDivideAmongSlaves(32)
+    run(m, r, c, 600, 10)
+    assert names(p).count("startCharging") == 1
+    wakes = names(p).count("wake")
+    run(m, r, c, 3600, 10)
+    assert names(p).count("startCharging") == 1 and names(p).count("wake") == wakes
diff --git a/tests/unit/test_charging_reconciler.py b/tests/unit/test_charging_reconciler.py
index dc7cb4eb..02531217 100644
--- a/tests/unit/test_charging_reconciler.py
+++ b/tests/unit/test_charging_reconciler.py
@@ -37,25 +37,25 @@ def test_heartbeat_stop_is_sent_once_and_a_stale_read_does_not_reassert():
     assert r.pass_() == 1 and b.calls == [("stopCharging", VIN, None)] and v.believed("chargingState").value == "Stopped" and m.desired.state(VIN).lastStopProvider == "TeslaBLE"
     assert r.pass_() == 0
     c.t += 10; v.observe("chargingState", "Charging", "TeslaBLE", at=v.lastWrite("chargingState").at)      # same instant as our write
     for _ in range(5): c.t += 61; assert r.pass_() == 0
     assert m.desired.get(VIN, CHARGING).value is False and len(b.calls) == 1
 
 def test_heartbeat_skips_the_registry_write_for_a_pending_vin():             # S1
     m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = slave(m); s.currentVIN = "5YJ3E1EA1KF000009"                # heard, not yet confirmed: not in the registry
     drive(m, s, amps_actual=12.0); assert m.vehicleRegistry.get("5YJ3E1EA1KF000009") is None                                 # no raise, nothing created
     s.currentVIN = VIN; drive(m, s, amps_actual=12.0); assert v.latest("actualCurrent").value == 12.0 and v.latest("actualCurrent").source == "Gen2TWC"
 
 def test_heartbeat_readings_are_not_evidence_for_a_car_with_vehicle_reads():   # S4, paid counted
-    m, r, v, c = setup(fleet(O.Outcome(O.SATISFIED, "not_charging"))); s = onTwc(m, v); f = m.providerOrder.provider("FleetAPI")
+    m, r, v, c = setup(fleet(O.Outcome(O.SATISFIED, "not_charging"))); s = onTwc(m, v); f = m.providerOrder.provider("FleetAPI"); m.setMaxAmpsToDivideAmongSlaves(0)   # no power to give: no rate
     v.observe("chargingState", "Charging", "FleetAPI"); m.stopCarsCharging(VIN); r.pass_(); assert cmds(f) == ["stopCharging"]
     for _ in range(10): c.t += 61; drive(m, s, amps_actual=12.0); r.pass_()                                                # readings every heartbeat, past RETRY each time
     assert cmds(f) == ["stopCharging"]                                                                                    # no vehicle read arrived: not re-sent
 
 def test_heartbeat_stop_targets_the_anonymous_car():                         # real TWCSlave heartbeat, non-Tesla car
     m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = slave(m); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"
     m.setMaxAmpsToDivideAmongSlaves(0); iface = drive(m, s, amps_actual=12.0); ready_to_stop(s); drive(m, s, amps_actual=12.0)   # offer 0, the car still draws past the gates
     assert m.desired.get(anon.key, CHARGING).value is False and r.pass_() == 1 and [x[:2] + x[4:6] for x in m._outbox] == [b"\xfc\xb2" + s.TWCID]
     iface.send.reset_mock(); assert m.flushRS485() == 1 and iface.send.call_args.args[0][:2] == b"\xfc\xb2"            # sent by the serial loop, on its thread
 
 def test_heartbeat_with_no_vehicle_key_decides_nothing():
     m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = slave(m); v.observe("chargingState", "Stopped", "TeslaBLE")
@@ -84,35 +84,35 @@ def test_stop_falls_to_fleet_after_60s_once():                               # R
 
 def test_disruptive_stop_waits_for_ble_only_when_ble_is_set_up_for_the_car():
     m, r, v, c = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "FleetAPI")
     m.settings["chargeStopMode"] = "2"; m.stopCarsCharging(VIN); r.pass_()
     assert m.settings.get("respondToSlaves", 1) == 1 and len(m.providerOrder.provider("TeslaBLE").calls) == 1   # BLE ready for this car: tried first
     c.t += PAID_AFTER[CHARGING]; r.pass_(); assert m.settings["respondToSlaves"] == 0 and m.providerOrder.provider("FleetAPI").calls == []   # billed stops suppressed under mode 2
     m2, r2, v2, c2 = setup(ble(O.Outcome(O.UNREACHABLE)), fleet(O.Outcome(O.DONE))); onTwc(m2, v2); v2.observe("chargingState", "Charging", "FleetAPI")
     m2.providerOrder.provider("TeslaBLE").ready = lambda vehicle, cap: False                                   # no key, or a refused one
     m2.settings["chargeStopMode"] = "2"; m2.stopCarsCharging(VIN); r2.pass_()
     assert m2.settings["respondToSlaves"] == 0 and m2.providerOrder.provider("TeslaBLE").calls == []           # at once
 
 def test_disruptive_stop_is_sent_once_until_new_evidence_then_reasserted():   # real heartbeat readings
-    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = slave(m); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "2"
+    m, r, v, c = setup(ble(O.Outcome(O.DONE))); s = slave(m); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "2"; m.setMaxAmpsToDivideAmongSlaves(0)   # no power to give: no rate
     drive(m, s, amps_actual=12.0); assert anon.latest("actualCurrent").value == 12.0 and anon.latest("actualCurrent").source == "Gen2TWC"   # the heartbeat records current
     m.stopCarsCharging(anon.key); assert r.pass_() == 1 and m.settings["respondToSlaves"] == 0 and anon.lastWrite("chargingState") is None     # never stamped
     m.settings["respondToSlaves"] = 1
     for _ in range(5): assert r.pass_() == 0                                                                    # no new reading: not re-sent
     c.t += 30; drive(m, s, amps_actual=12.0); assert r.pass_() == 0 and m.settings["respondToSlaves"] == 1         # newer reading, inside RETRY: held
     c.t += 31; drive(m, s, amps_actual=12.0); m.stopCarsCharging(anon.key); assert r.pass_() == 1 and m.settings["respondToSlaves"] == 0   # resumed, past RETRY: re-stopped
     m.settings["respondToSlaves"] = 1; c.t += 61; drive(m, s, amps_actual=0.5); assert r.pass_() == 0 and m.settings["respondToSlaves"] == 1   # quiet bus: satisfied
 
 def test_disruptive_stop_on_the_real_clock_is_sent_once():                    # production clock
-    m, r, v, c = setup(ble(O.Outcome(O.DONE)), clock=False); s = slave(m); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"
+    m, r, v, c = setup(ble(O.Outcome(O.DONE)), clock=False); s = slave(m); anon = m.vehicleRegistry.beginPlugSession("8244"); m.settings["chargeStopMode"] = "3"; m.setMaxAmpsToDivideAmongSlaves(0)   # no power to give: no rate
     drive(m, s, amps_actual=12.0); m.stopCarsCharging(anon.key)
     sent = sum(r.pass_() for _ in range(20)); drive(m, s, amps_actual=12.0)
     assert sent == 1 and m.flushRS485() == 1                                                                         # one relay stop, not one per pass
 
 def test_mode_2_start_after_a_ble_stop_goes_through_ble():
     m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE), O.Outcome(O.DONE))); onTwc(m, v); v.observe("chargingState", "Charging", "TeslaBLE"); m.settings["chargeStopMode"] = "2"
     m.stopCarsCharging(VIN); r.pass_(); assert m.desired.state(VIN).lastStopProvider == "TeslaBLE"
     c.t += 61; m.startCarsCharging(VIN); r.pass_(); assert cmds(m.providerOrder.provider("TeslaBLE")) == ["stopCharging", "startCharging"] and m.settings.get("respondToSlaves", 1) == 1
 
 def test_mode_2_start_after_our_stop_needs_no_slave():                      # ledger L50
     m, r, v, c = setup(fleet(O.Outcome(O.DONE))); s = onTwc(m, v); f = m.providerOrder.provider("FleetAPI"); v.observe("chargingState", "Charging", "FleetAPI"); m.settings["chargeStopMode"] = "2"
     m.stopCarsCharging(VIN); r.pass_(); assert m.settings["respondToSlaves"] == 0 and m.desired.state(VIN).lastStopProvider == "Gen2TWC"
diff --git a/tests/unit/test_command_path_parity.py b/tests/unit/test_command_path_parity.py
index 4db0a719..fdf0c482 100644
--- a/tests/unit/test_command_path_parity.py
+++ b/tests/unit/test_command_path_parity.py
@@ -1876,26 +1876,28 @@ def test_a_drive_inside_the_radius_spends_no_budget_and_the_park_applies(
     car.shift = "P"
     push(v, c, state="online", shiftState="P")
     passes(r, c, 10, each=policy)
     assert car.charge["charge_limit_soc"] == 80 and paid(requests_mock) == (1, 0, 1)
 
 
 # The Gen2 unplug: a 00 whose first heartbeat drops the slave's max amps
 # from above 0 to 0, held a minute, unless live telemetry says plugged in
 
 
 def gen2(monkeypatch, m, c, vin=VIN, maxA=32.0):
     # The serial thread's clock is the test's; the TWC links at 03 with the
-    # car's max amps and, given a vin, names the car by its VIN read
+    # car's max amps and, given a vin, names the car by its VIN read. The
+    # policy offers nothing until the test gives it power
     monkeypatch.setattr(time, "time", c)
+    m.maxAmpsToDivideAmongSlaves = 0
     s = m.getSlaveTWCs()[0]
     heartbeat(m, s, 0.0, state=0x03, amps_max=maxA)
     if vin:
         s.currentVIN = vin
         m.recordVehicleVIN(s)
         s.currentVIN = ""
     return s
 
 
 def followsPlug(s, c):
     # BLE's charge read of a car in range: plugged in at the TWC's max while
     # the TWC shows a car (a state, or a max above 0), else Disconnected. A
@@ -2059,26 +2061,26 @@ def test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_wou
 def test_a_sleeping_car_at_00_with_power_available_is_woken_for_a_raise(
     requests_mock, monkeypatch
 ):
     # 32 A to share; the named car asleep at 00 (max 0 A), its limit at its
     # battery: the policy's raise wakes it over BLE; paid == (0, 0, 0)
     m, r, v, c, api = install(fleet=True)
     b = realBle(
         m, ping=lambda vin: not v.observe("state", "asleep", "TeslaBLE") or True
     )
     FleetCar(requests_mock, state="asleep", limit=50)
     v.observe("chargeLimit", 50, "TeslaBLE")
     v.observe("batteryLevel", 50, "TeslaBLE")
-    m.setMaxAmpsToDivideAmongSlaves(32)
     s = gen2(monkeypatch, m, c, maxA=32.0)
+    m.setMaxAmpsToDivideAmongSlaves(32)
     beats(m, r, c, s, 300, 0x00, 0.0, cycles(m, 50))
     beats(m, r, c, s, 1800, 0x00, 0.0, cycles(m, 80))
     assert bleCommands(b) == ["wake", "charging-set-limit"] and limits(b) == [80]
     assert paid(requests_mock) == (0, 0, 0)
 
 
 def test_no_gps_source_plug_unplug_cycle_end_to_end(requests_mock, monkeypatch):
     # BLE and a VIN-less TWC only: no position, no telemetry, no Tesla API.
     # The unplug departs the only car that may be on it; paid == (0, 0, 0)
     m, r, v, c, api = install(located=False, held=(80, 50))
     b = realBle(m)
     v.observe("chargeLimit", 50, "TeslaBLE")
@@ -2103,24 +2105,25 @@ def test_gen2_steady_00_after_link_does_not_block_startup_charging(
     # BLE once the ping answers; paid == (0, 0, 0)
     m, r, v, c, api = install(fleet=True, located=False, held=(90, 50))
     b = realBle(m)
     FleetCar(requests_mock, state="asleep", limit=50)
     v.observe("chargeLimit", 50, "TeslaBLE")
     policy = cycles(m, 50)
     s = gen2(monkeypatch, m, c, vin=None, maxA=47.0)
     beats(m, r, c, s, 120, 0x03, 47.0, policy)
     beats(m, r, c, s, 900, 0x00, 0.0, policy)
     assert v.markAt("unplug") == Presence.NEVER
     assert Presence.presence(m, v) != Presence.NOT_HOME
     assert limits(b) == [] and b.runs == []
+    m.setMaxAmpsToDivideAmongSlaves(32)
     m.startCarsCharging(VIN)
     beats(m, r, c, s, 60, 0x00, 0.0, policy)
     # The edge's check, and its one follow-up when that check can't tell
     assert b.pings == [VIN, VIN] and Presence.presence(m, v) == Presence.HOME
     assert "charging-start" in bleCommands(b) and limits(b) == []
     assert m.heldLimits.get(VIN) == HeldLimit(90, 50)
     assert paid(requests_mock) == (0, 0, 0)
 
 
 def test_plug_in_on_a_vin_twc_comes_home_with_one_apply(requests_mock, monkeypatch):
     # Away, then plugged in on a TWC that reads its VIN: home, and the policy
     # limit goes once over BLE; paid == (0, 0, 0)
@@ -2193,27 +2196,27 @@ def test_vin_less_single_candidate_plug_one_apply(requests_mock, monkeypatch):
     assert paid(requests_mock) == (0, 0, 0)
 
 
 def test_vin_less_two_candidates_ble_pilot_one_apply(requests_mock, monkeypatch):
     # Scenario 4: two cars at home, each given the policy limit once; BLE
     # reads one charging at the TWC's 32 A pilot and the other unplugged:
     # that one is named and it alone is rated; paid == (0, 0, 0)
     m, r, v, two, c, b = twoCarsHome(requests_mock)
     b._fetch_state_json = chargeRead(
         **{VIN: ("Charging", 32), VIN2: ("Disconnected", 0)}
     )
     m.settings["chargeRateControl"] = "2"
-    m.setMaxAmpsToDivideAmongSlaves(10)
     policy = cycles(m, 50)
     s = gen2(monkeypatch, m, c, vin=None)
+    m.setMaxAmpsToDivideAmongSlaves(10)
     attributeQueued(m)
     assert v.value("twcVin") == "8244" and two.value("twcVin") is None
     beats(m, r, c, s, 600, 0x03, 32.0, policy)
     assert limits(b) == [50] and limits(b, VIN2) == [50]
     rated = {vin for vin, cmd, args in b.runs if cmd == "charging-set-amps"}
     assert rated == {VIN} and paid(requests_mock) == (0, 0, 0)
 
 
 def test_vinless_ambiguous_plug_rates_nobody_and_logs_once(
     requests_mock, monkeypatch, caplog
 ):
     # Scenario 5: two cars at home, BLE answers neither: nobody is named or
@@ -2493,53 +2496,55 @@ def unnamedAt00(requests_mock, monkeypatch):
     b._fetch_state_json = chargeRead()
     s = gen2(monkeypatch, m, c, vin=None)
     s.protocolVersion = 2
     attributeQueued(m)
     assert s.vehicleKey == "anon:8244"
     v.observe("batteryLevel", 50, "FleetAPI")
     v.observe("chargingState", "Stopped", "FleetAPI")
     beats(m, r, c, s, 400, 0x03, 32.0)
     assert s.vehicleKey == "anon:8244"
     c.t += (30 - c.t % 30) % 30
     beats(m, r, c, s, 30, 0x00, 32.0)
     assert m.vehicleRegistry.vehicleAt("8244").isAnonymous
-    assert s.vehicleKey is None and m.offered.get(VIN) == 0
+    assert s.vehicleKey is None
     return m, r, v, c, s, b
 
 
 def test_an_unnamed_plug_at_00_wakes_no_candidate_for_a_raise(
     requests_mock, monkeypatch
 ):
-    # The policy raises the limit to 90 while the unnamed TWC rests at 00:
-    # nothing is offered there, so the raise waits for a free channel.
+    # The policy raises the limit to 90 while the unnamed TWC rests at 00
+    # with no power to share, so the raise waits for a free channel.
     # paid == (0, 0, 0)
     m, r, v, c, s, b = unnamedAt00(requests_mock, monkeypatch)
     beats(m, r, c, s, 600, 0x00, 32.0, cycles(m, 90))
     assert "wake" not in bleCommands(b) and paid(requests_mock) == (0, 0, 0)
 
 
-def test_an_unnamed_plug_at_00_starts_no_candidate_as_the_offer_rises(
+def test_an_unnamed_plug_at_00_starts_only_the_car_plugged_there_as_the_offer_rises(
     requests_mock, monkeypatch
 ):
     # The offer rises while the unnamed TWC rests at 00 with a car not full:
-    # the TWC reports no car there, so no start fans out. The car's own
-    # endpoint still rates it over BLE. paid == (0, 0, 0)
+    # the TWC reports no car there, so no start fans out. The car plugged in
+    # here, by elimination, would charge and has room: it alone is started,
+    # by its VIN, and its own endpoint rates it over BLE. paid == (0, 0, 0)
     m, r, v, c, s, b = unnamedAt00(requests_mock, monkeypatch)
     starts = []
     monkeypatch.setattr(m, "startCarsCharging", starts.append)
     for amps in (6, 12, 24, 32):
         m.setMaxAmpsToDivideAmongSlaves(amps)
         beats(m, r, c, s, 60, 0x00, 32.0)
-    assert starts == [] and m.desired.get(VIN, CHARGING) is None
-    assert "charging-start" not in bleCommands(b)
+    assert starts == [] and m.desired.get(VIN2, CHARGING) is None
+    assert m.desired.get(VIN, CHARGING).value is True
+    assert bleCommands(b).count("charging-start") == 1
     assert paid(requests_mock) == (0, 0, 0)
 
 
 def test_a_car_just_unplugged_is_not_the_next_plug_s(requests_mock, monkeypatch):
     # A swap: car 1 unplugs (its feed says so) and car 2, with no feed and
     # no BLE answer, plugs in. Both are inside and only car 1 answered BLE:
     # car 2 is the match. paid == (0, 0, 0)
     m, r, v, two, c, b = twoCarsHome(requests_mock)
     b._fetch_state_json = chargeRead()
     push(v, c, pluggedIn=True, chargingState="Stopped")
     push(v, c, gap=60, pluggedIn=False, chargingState="Disconnected")
     v.observe("bleReach", True, "TeslaBLE")
diff --git a/tests/unit/test_control_tick.py b/tests/unit/test_control_tick.py
index 9fb16372..cb1d2fc5 100644
--- a/tests/unit/test_control_tick.py
+++ b/tests/unit/test_control_tick.py
@@ -348,34 +348,24 @@ def test_a_withdrawal_targets_gen3_units_and_cars_zero():
     m.withdrawOffers()
     gen3.setUnitTarget.assert_called_once_with(u.ID, 0)
 
     m = real()
     car(m, VIN, "Charging")
     m.getMaxAmpsToDivideAmongSlaves = lambda: 20
     m.controlPass()
     assert setAmps(m) == [{"vin": VIN, "amps": 20}]
     m.withdrawOffers()
     assert setAmps(m) == []
 
 
-def test_a_withdrawal_leaves_no_car_offered_power():
-    m = real()
-    car(m, VIN, "Charging")
-    m.getMaxAmpsToDivideAmongSlaves = lambda: 20
-    m.controlPass()
-    assert m.offered[VIN] > 0
-    m.withdrawOffers()
-    assert m.offered[VIN] == 0 and not any(m.offered.values())
-
-
 def test_a_withdrawal_zeroes_the_slaves_even_if_points_cannot_be_built():
     m = pureGen2(feed=40)
     m.controlPass()
     m.chargingPoints = Mock(side_effect=RuntimeError)
     with pytest.raises(RuntimeError):
         m.withdrawOffers()
     assert [s.offer for s in m.getSlaveTWCs()] == [Offer(0, 0)] * 2
 
 
 def test_housekeeping_runs_ipc_and_expiry_in_every_mode():
     for mode in (1, 2, 3):
         m = pureGen2(feed=40)
diff --git a/tests/unit/test_gen2_unplug.py b/tests/unit/test_gen2_unplug.py
index ed1e8a53..06a3b0df 100644
--- a/tests/unit/test_gen2_unplug.py
+++ b/tests/unit/test_gen2_unplug.py
@@ -193,13 +193,13 @@ def test_an_unnamed_session_with_no_candidate_ends_at_the_check(rig):
 def test_an_anonymous_point_finds_its_cars_once_per_pass(rig, monkeypatch):
     from TWCManager.EVSEInstance import ChargingPoint
 
     m, v, c, s = rig
     beats(m, s, c, 20, 0x03, 32.0)
     assert s.vehicleKey == "anon:8244"
     calls = []
     real = ChargingPoint.candidates
     monkeypatch.setattr(
         ChargingPoint, "candidates", lambda *a: calls.append(a) or real(*a)
     )
     m.controlPass()
-    assert len(calls) == 1 and "anon:8244" in m.offered
+    assert len(calls) == 1
diff --git a/tests/unit/test_limit_reconciler.py b/tests/unit/test_limit_reconciler.py
index 8602491b..35699c7f 100644
--- a/tests/unit/test_limit_reconciler.py
+++ b/tests/unit/test_limit_reconciler.py
@@ -9,24 +9,25 @@ from TWCManager.Vehicle.Reconcile.Reconciler import MIN_SEND_GAP, PAID_AFTER, PR
 from tests.unit.reconcile_helpers import Clock, placeAt, ScriptedProvider, inline, settled
 from tests.unit.test_gen2twc_provider import VIN, make as make_master
 
 def setup(*providers, clock=True, here=True, battery=60, ble=False):
     # ble: the real TeslaBLE module and its provider; tests stub what it runs
     # here: the car is plugged in at home, so every message applies to it
     m, s = make_master(); c = Clock(1000.0) if clock else time.time
     m.config = dict(m.config, config=dict(m.config["config"]))          # never the shared CONFIG
     if clock: m.vehicleRegistry._clock = c
     for p in providers: m.providerOrder.register(p)
     m.desired = DesiredStore(clock=c); m.vehicleRegistry.removed = m.desired.forget; m.heldLimits.load()
     m.reconciler = r = inline(VehicleReconciler(m, clock=c)); v = m.vehicleRegistry.getOrCreate(VIN, "t")
+    m.maxAmpsToDivideAmongSlaves = 32                                        # the policy has room for a car to start
     if ble:
         m.config["config"]["teslaControlPath"] = "/bin/true"
         with patch.object(TeslaBLE, "_start_dbus_session"), patch.object(TeslaBLE, "_cleanup_stale_pipe"): b = TeslaBLE(m)
         b.isDockerCached = False
         for p in b.providers(): m.providerOrder.register(p)
     if here:
         v.observe("pluggedIn", True, "Gen3TWC")
         if battery:
             v.observe("batteryLevel", battery, "TeslaMateVehicle")
     return m, r, v, c
 
 def leave(v):                                                                # unplugged after the plug-in: a restore applies
@@ -669,45 +670,41 @@ def test_a_limit_raise_logs_the_wake_and_its_outcome(caplog):
 def test_a_limit_raise_with_unknown_current_limit_wakes_and_reads_first(caplog):
     # An unknown limit is expected to charge: it wakes, and the read before the write finds the limit
     caplog.set_level("INFO"); m, r, v, c = setup(ble(O.Outcome(O.DONE)).reads(60)); m.desired.set(VIN, CHARGE_LIMIT, 70, "policy"); r.pass_()
     assert "TeslaBLE wake for %s before setChargeLimit: done" % VIN in _info(caplog)
     assert cmds(prov(m, "TeslaBLE")) == ["setChargeLimit"]
 
 def test_a_stop_logs_neither_a_wake_nor_a_skip(caplog):
     caplog.set_level("INFO"); m, r, v, c = setup(ble(O.Outcome(O.DONE))); v.observe("chargingState", "Charging", "TeslaBLE")
     m.desired.set(VIN, CHARGING, False, "distributor"); r.pass_(); assert cmds(prov(m, "TeslaBLE")) == ["stopCharging"]
     assert not any(" wake " in x for x in _info(caplog))
 
 
-def test_a_raise_never_wakes_a_car_its_point_offers_nothing(caplog):
+def test_a_raise_never_wakes_a_car_with_no_room_to_start(caplog):
     caplog.set_level("INFO")
     m, r, v, c = setup(ble(O.Outcome(O.DONE)))
     p = prov(m, "TeslaBLE")
     v.observe("chargeLimit", 50, "TeslaBLE")
-    m.distributeEVSEPower()  # the car's point wants no power: offered 0
-    assert m.offered[VIN] == 0
+    m.setMaxAmpsToDivideAmongSlaves(0)  # no power to share
     m.desired.set(VIN, CHARGE_LIMIT, 80, "policy")
     r.pass_()
     assert names(p) == ["setChargeLimit"]  # sent, but without a wake
-    assert "TeslaBLE no wake for %s before setChargeLimit: nothing offered" % VIN in [
+    assert "TeslaBLE no wake for %s before setChargeLimit: no room to start" % VIN in [
         x.getMessage() for x in caplog.records
     ]
     m.setMaxAmpsToDivideAmongSlaves(32)
-    v.observe("chargingState", "Stopped", "TeslaBLE")  # wants power now
-    m.distributeEVSEPower()
-    assert m.offered[VIN] > 0
     c.t += 60
     m.desired.set(VIN, CHARGE_LIMIT, 90, "policy")
     r.pass_()
-    assert names(p)[1:3] == ["wake", "setChargeLimit"]  # offered: the raise wakes
+    assert names(p)[1:3] == ["wake", "setChargeLimit"]  # room: the raise wakes
 
 
 def quietCar(battery, limit, *wants):
     # A BLE car plugged in with a battery level and limit, and what is wanted
     m, r, v, c = setup(ble(O.Outcome(O.DONE)), battery=battery)
     v.observe("chargeLimit", limit, "TeslaBLE")
     for aspect, value, kw in wants:
         m.desired.set(VIN, aspect, value, "policy", **kw)
     r.pass_()
     return names(prov(m, "TeslaBLE")), m
 
 
@@ -719,36 +716,32 @@ def test_a_car_that_will_not_charge_is_never_woken_to_raise_its_limit(caplog):
         x.getMessage() for x in caplog.records
     )
 
 
 def test_a_car_that_will_not_charge_is_never_woken_to_lower_its_limit():
     assert quietCar(80, 90, (CHARGE_LIMIT, 70, {}))[0] == ["setChargeLimit"]
 
 
 def test_a_car_that_will_still_charge_may_be_woken_to_lower_its_limit():
     assert quietCar(40, 90, (CHARGE_LIMIT, 70, {}))[0] == ["wake", "setChargeLimit"]
 
 
-def test_a_car_wakes_for_a_lower_once_its_point_offers_power():
+def test_a_car_wakes_for_a_lower_once_there_is_room_to_start():
     m, r, v, c = setup(ble(O.Outcome(O.DONE), O.Outcome(O.DONE)), battery=40)
     v.observe("chargeLimit", 90, "TeslaBLE")
-    m.distributeEVSEPower()  # nothing wanted: offered 0
-    assert m.offered[VIN] == 0
+    m.setMaxAmpsToDivideAmongSlaves(0)
     m.desired.set(VIN, CHARGE_LIMIT, 70, "policy")
     r.pass_()
     assert names(prov(m, "TeslaBLE")) == ["setChargeLimit"]
     m.setMaxAmpsToDivideAmongSlaves(32)
-    v.observe("chargingState", "Stopped", "TeslaBLE")
-    m.distributeEVSEPower()
-    assert m.offered[VIN] > 0
     c.t += 60
     m.desired.set(VIN, CHARGE_LIMIT, 60, "policy")
     r.pass_()
     assert names(prov(m, "TeslaBLE"))[1:3] == ["wake", "setChargeLimit"]
 
 
 def test_a_lift_never_wakes_a_car_full_at_its_limit():
     assert quietCar(60, 50, (AMPS, 32, {"lift": True}))[0] == ["setAmps"]
 
 
 def test_a_pending_higher_limit_makes_the_car_expected_to_charge():
     calls, m = quietCar(60, 50, (CHARGE_LIMIT, 70, {}), (AMPS, 32, {"lift": True}))
diff --git a/tests/unit/test_presence.py b/tests/unit/test_presence.py
index e04dc9ad..471c2afa 100644
--- a/tests/unit/test_presence.py
+++ b/tests/unit/test_presence.py
@@ -1094,33 +1094,33 @@ def test_a_feed_report_after_the_edge_keeps_the_car_through_a_max_drop_in_00(
     monkeypatch,
 ):
     m, v, c = placed()
     fed(v)
     s, beat = onGen2(monkeypatch, m, v, c)
     beat(49, 0x00, 47.0, step=7)  # woken by the app
     beat(10, 0x00, 0.0)
     v.observe("pluggedIn", True, TM)
     beat(110, 0x00, 0.0)
     assert v.markAt("unplug") == P.NEVER and v.value("twcVin") == "8244"
 
 
-def test_a_car_its_twc_still_holds_at_00_is_offered_the_twcs_nothing(monkeypatch):
+def test_a_car_its_twc_still_holds_at_00_needs_the_twcs_minimum(monkeypatch):
     from TWCManager.Vehicle.Reconcile import Belief
 
     m, v, c = placed()
     s, beat = onGen2(monkeypatch, m, v, c)
     beat(120, 0x00, 0.0)  # checked: no answer, so the car stays
-    m.distributeEVSEPower()
-    assert s.vehicleKey is None and m.offered[VIN] == 0
-    assert Belief.whyQuiet(m, v) == "nothing offered"
+    m.setMaxAmpsToDivideAmongSlaves(s.minAmps - 1)
+    assert s.vehicleKey is None and s.heldKey == VIN
+    assert Belief.whyQuiet(m, v) == "no room to start"
 
 
 @pytest.mark.parametrize("move", ["driveStart", "outside"])
 def test_a_twc_at_00_stops_holding_a_car_that_moved_since_it_was_named(
     monkeypatch, move
 ):
     m, v, c = placed()
     s, beat = onGen2(monkeypatch, m, v, c)
     beat(120, 0x00, 0.0)
     assert s.heldKey == VIN
     later(c)
     v.mark(move, c.t)
@@ -1282,25 +1282,27 @@ def test_restart_steady_00_with_telemetry_plugged_is_home_and_restores_nothing(
     v.observe("chargeLimit", 50, TM)
     p = scriptedBle(m)
     later(c)
     v.observe("state", "online", TM)
     v.observe("pluggedIn", True, TM)
     monkeypatch.setattr(time, "time", c)
     s = m.getSlaveTWCs()[0]
     for _ in range(30):  # 00 from the first reply after the restart
         beats(m, s, c, 30, 0x00, 0.0)
         m.setPolicyLimit(50, transition=False)
         m.reconciler.pass_()
     assert P.presence(m, v) == P.HOME and v.markAt("unplug") == P.NEVER
-    assert p.calls == [] and m.heldLimits.get(VIN) == HeldLimit(90, 50)
+    assert m.heldLimits.get(VIN) == HeldLimit(90, 50)
+    # Its battery unknown, it would charge, and with room it is started once
+    assert [x[0] for x in p.calls] == ["wake", "startCharging"]
 
 
 def test_a_charging_point_s_own_start_always_applies():
     from TWCManager.Vehicle.Reconcile.Desired import CHARGING
 
     m, v, c = placed(AWAY)  # wherever the car is said to be, the point is here
     point = ScriptedProvider("Gen3TWC", 1, True, [O.Outcome(O.DONE)], module=None)
     m.providerOrder.register(point)
     m.desired.set(VIN, CHARGING, True, "distributor")
     m.reconciler.pass_()
     assert [x[0] for x in point.calls if x[0] != "wake"] == ["startCharging"]
 
@@ -1528,37 +1530,38 @@ def test_an_attributed_gen2_plug_ends_with_the_point_s_00_even_idle(monkeypatch)
     m, v, c = placed()
     scriptedBle(m)
     s, beat = onGen2(monkeypatch, m, v, c, named=False)
     attributeQueued(m)
     beat(60, 0x03, 0.0)  # named, idle at 0 A: no 00 here is an unplug
     assert v.value("twcVin") == "8244" and P.pluggedHere(m, v)
     assert [e.vehicle for e in vehicleEndpoints(m)] == [v]
     beat(120, 0x00, 0.0)
     assert v.markAt("unplug") == P.NEVER and not P.pluggedHere(m, v)
     assert vehicleEndpoints(m) == []
 
 
-def test_an_anonymous_point_s_offer_covers_the_cars_it_fans_out_to(monkeypatch):
+def test_a_car_an_anonymous_point_may_serve_has_no_room_without_power(monkeypatch):
+    from TWCManager.Vehicle.Reconcile import Belief as B
     from tests.unit.test_gen2_unplug import beats
 
     m, v, c = placed()
     scriptedBle(m)
     v.claim("TeslaBLE", True, "paired")
     v.observe("chargingState", "Charging", TM)  # plugged in here, unnamed
     monkeypatch.setattr(time, "time", c)
     s = m.getSlaveTWCs()[0]
     m.setMaxAmpsToDivideAmongSlaves(0)
     beats(m, s, c, 20, 0x03, 32.0)
-    m.distributeEVSEPower()
-    assert s.vehicleKey == "anon:8244" and m.offered[VIN] == 0
+    assert s.vehicleKey == "anon:8244"
+    assert B.whyQuiet(m, v) == "no room to start"
 
 
 def vinReadingGen2(requests_mock, monkeypatch, located=True):
     # The box after a restart: one car, plugged in and asleep, on a Gen2
     # that reads VINs but has read none this session. Unlocated, nothing but
     # its name is known, and the sleep-safe check answers asleep
     from tests.unit.test_command_path_parity import gen2, install, realBle
 
     m, r, v, c, api = install(fleet=True, located=located)
     b = realBle(m, ping=located or (lambda vin: asleepPing(m, vin)))
     b.fetched = []
     b._fetch_state_json = lambda vin, kind: b.fetched.append(vin)
diff --git a/tests/unit/test_sleep_pilot_replay.py b/tests/unit/test_sleep_pilot_replay.py
index 5d8ca9ef..2d36b10b 100644
--- a/tests/unit/test_sleep_pilot_replay.py
+++ b/tests/unit/test_sleep_pilot_replay.py
@@ -32,25 +32,25 @@ def test_a_car_read_under_the_sleep_pilot_is_offered_its_share_and_woken(caplog)
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
     m.controlPass(now=c())
     assert s.pointAmps == pytest.approx(48)
-    assert s.offer.amps == 48 and m.offered[VIN] > 0
+    assert s.offer.amps == 48
     assert m.desired.get(VIN, CHARGING).value is True  # the start
     m.desired.set(VIN, CHARGE_LIMIT, 70, "policy")
     assert B.whyQuiet(m, v) is None  # the raise may wake the car
     r.pass_()
     assert "setChargeLimit" in cmds(prov(m, "TeslaBLE"))
     assert "TeslaBLE wake for %s before setChargeLimit: done" % VIN in [
         x.getMessage() for x in caplog.records
     ]
 
 
 def test_a_car_left_at_a_lowered_request_is_lifted_above_its_own_maximum():
     # A 32 A car on 48 A wiring: the lift to the wiring maximum still goes
diff --git a/tests/unit/test_sleeping_car.py b/tests/unit/test_sleeping_car.py
index 1b873f97..af15b222 100644
--- a/tests/unit/test_sleeping_car.py
+++ b/tests/unit/test_sleeping_car.py
@@ -85,35 +85,35 @@ def test_a_lowering_to_a_sleeping_car_holds_after_one_preflight(requests_mock, c
 
 def test_a_raise_still_wakes_a_sleeping_car(requests_mock):
     m, r, v, c, api = install()
     b = sleepy(m)
     v.observe("chargeLimit", 50, TM)
     v.observe("state", "asleep", TM)
     m.setPolicyLimit(80, transition=True)
     passes(r, c, 60)
     assert bleCommands(b) == ["wake", "charging-set-limit"]
     assert b._tool.call_count == 0 and requests_mock.call_count == 0
 
 
-def test_a_raise_held_at_0_a_wakes_once_offered(requests_mock):
+def test_a_raise_held_at_0_a_wakes_once_there_is_room(requests_mock):
     m, r, v, c, api = install()
     b = sleepy(m)
-    m.offered = {VIN: 0}
+    m.setMaxAmpsToDivideAmongSlaves(0)
     v.observe("chargeLimit", 50, TM)
     m.setPolicyLimit(80, transition=True)
     passes(r, c, 10)
     passes(r, c, 600, each=noise(v, c))
     assert b._tool.call_count == 1 and bleCommands(b) == []
     assert m.desired.record(VIN, CHARGE_LIMIT).lastOutcome.detail == O.HELD + "asleep"
-    m.offered = {VIN: 16}
+    m.setMaxAmpsToDivideAmongSlaves(16)
     passes(r, c, 60, each=noise(v, c))
     assert bleCommands(b) == ["wake", "charging-set-limit"]
 
 
 def test_a_ble_wake_is_a_sign_of_life(requests_mock):
     m, r, v, c, api = install()
     b = sleepy(m)
     v.observe("chargeLimit", 50, TM)
     v.observe("state", "asleep", TM)
     m.setPolicyLimit(80, transition=True)
     passes(r, c, 60)
     assert v.reported("state")["TeslaBLE"].value == "online"
