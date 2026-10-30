 lib/TWCManager/TWCMaster.py  | 17 +++++++++++++++--
 tests/unit/test_admission.py | 15 +++++++++++++--
 2 files changed, 28 insertions(+), 4 deletions(-)
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index 6749fdd5..5a9be4d3 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -621,28 +621,32 @@ class TWCMaster:
         # only a draw over 4 A (one ramping or finishing is left alone); an
         # anonymous car is left to its Gen2, as elsewhere it would fan out
         policy = self.getModuleByName("Policy")
         green = policy is None or policy.policyIsGreen()
         hold = self.config["config"].get("startStopDelay", 60) if green else -1
         ends = getattr(point, "localEndpoints", ())
         gen2 = [e for e in ends if hasattr(e, "pointAmps")]
         drawing = point is not None and _drawing(point)
         for v in filter(None, map(self.vehicleRegistry.get, keys)):
             if not (v.vin or gen2):
+                # Never stopped, so never held back on the way up either
+                self._cut -= {v.key}
                 continue
             # The car's own readings, the same at each point it may be on
             room = v.key in self.admission
             seen = (room, v.value("chargingState"), v.value("actualCurrent") or 0)
             last = self._held.get(v.key)
             if not last or last[:2] != seen[:2] or abs(last[2] - seen[2]) > 0.8:
                 last = self._held[v.key] = (*seen, now)
             held = now - last[3] > hold
+            if room and held:
+                self._cut -= {v.key}
             want = getattr(self.desired.get(v.key, CHARGING), "value", None)
             if (
                 room
                 and v.key in self._willing
                 and (want is None or want is False and held)
             ):
                 if not satisfied(CHARGING, True, known(v, CHARGING, True)):
                     self.cancelStopCarsCharging(v.key)
                     self._wantCharging(v.key, True)
             elif (
@@ -753,34 +757,42 @@ class TWCMaster:
         def wanted(p):
             return p.wantsToCharge or _carsAt(p) & willing
 
         for p in sorted(points, key=lambda p: (not wanted(p), not _drawing(p))):
             if p.isReadOnly:
                 continue
             need = p.minPower
             if p.maxPower < need <= left["all"] and wanted(p):
                 self._noteRefusedPoint(p, left["all"])
             elif need <= p.maxPower and all(need <= left[c] for c in _draws(p, left)):
-                (seated if wanted(p) else room).append(p)
+                # One cut to its minimum stays there until room has held, or
+                # power at the edge would re-rate it each pass
+                cut = _carsAt(p) & self._cut
+                (seated if wanted(p) and not cut else room).append(p)
+                held.update({p: need} if cut else {})
                 for c in _draws(p, left):
                     left[c] -= need
+                    shared[c] -= need if cut else 0
             elif need <= p.maxPower and _drawing(p) and "Gen2TWCs" not in p.controllers:
-                held[p] = need
+                held[p], self._cut = need, self._cut | _carsAt(p)
                 for c in _draws(p, left):
                     left[c], shared[c] = left[c] - need, shared[c] - need
         admission = set().union(*map(_carsAt, room + seated))
         if left["all"] >= self.convertAmpsToWatts(VehicleEndpoint.MIN_AMPS):
             # A car on no point of ours may start on what is left
             admission |= {v.key for v in cars}.difference(*map(_carsAt, points))
         self.admission = frozenset(admission)
         return seated, held, shared, budgets
 
+    # The cars cut to their minimum for want of room, swapped whole
+    _cut = frozenset()
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
@@ -1795,20 +1807,21 @@ class TWCMaster:
         try:
             twcid = "%02X%02X" % (slaveTWC.TWCID[0], slaveTWC.TWCID[1])
             return self.vehicleRegistry.isPending(twcid)
         except Exception as e:
             logger.warning("Vehicle registry pending check failed: %s", e)
             return False
 
     def _vehicleRemoved(self, key):
         # Forgotten means forgotten: its desired state and held limit go
         self._held.pop(key, None)
+        self._cut -= {key}
         self.desired.forget(key)
         self.heldLimits.remove(key)
 
     def expireVehicles(self):
         # Forget unclaimed, unasserted vehicles unseen past the forget window
         expired = self.vehicleRegistry.expire()
         if expired:
             self.queue_background_task({"cmd": "saveSettings"})
         return expired
 
diff --git a/tests/unit/test_admission.py b/tests/unit/test_admission.py
index 433e7b2b..39158124 100644
--- a/tests/unit/test_admission.py
+++ b/tests/unit/test_admission.py
@@ -392,25 +392,36 @@ def test_a_start_without_room_waits_and_keeps_its_budget(requests_mock, period):
     # A car that accepts starts but stays Stopped, for an hour: power at the
     # edge costs no more paid starts than steady power (None) does
     m, r, v, c, car = carSide(requests_mock, StaysStopped)
     amps = (6, 4) if period else (32, 32)
     swing(m, r, v, c, car, 3600, period or 3600, amps)
     assert commands(requests_mock).count("charge_start") == 2
 
 
 def test_power_across_the_minimum_every_4_minutes_for_2_hours(requests_mock):
     # Clouds: each 4 minutes in or out of room outlasts startStopDelay, so
-    # every swing costs a stop and a start
+    # every swing costs a stop and a start, and the rate a cut to the
+    # minimum and a restore
     m, r, v, c, car = carSide(requests_mock)
     swing(m, r, v, c, car, 7200, 240, every=30)
     cmds = commands(requests_mock)
-    assert (cmds.count("charge_stop"), cmds.count("charge_start")) == (15, 15)
+    counts = [cmds.count(k) for k in ("charge_stop", "charge_start")]
+    assert counts + [cmds.count("set_charging_amps")] == [15, 15, 30]
+
+
+@pytest.mark.parametrize("period", [10, 30])
+def test_power_flapping_at_the_minimum_cuts_the_rate_once(requests_mock, period):
+    # 6 A and 4 A by turns around a 5 A minimum for an hour: cut once to the
+    # minimum, the car stays there until room has held, so never stops
+    m, r, v, c, car = carSide(requests_mock, charging="Charging")
+    swing(m, r, v, c, car, 3600, period, every=30)
+    assert commands(requests_mock) == ["set_charging_amps"] * 2
 
 
 def test_a_car_stopped_for_room_restarts_once_room_has_held(requests_mock):
     m, r, v, c, car = carSide(requests_mock, charging="Charging")
     swing(m, r, v, c, car, 120, 120, amps=(4, 4), every=10)
     assert commands(requests_mock)[-1:] == ["charge_stop"]
     swing(m, r, v, c, car, 60, 120, amps=(6, 6), every=10)
     assert "charge_start" not in commands(requests_mock)
     swing(m, r, v, c, car, 20, 120, amps=(6, 6), every=10)
     assert commands(requests_mock).count("charge_start") == 1
