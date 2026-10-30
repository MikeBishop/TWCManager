## phase5 commit
commit 6a8275d6933d2e2c15607c125a8fd91e064e5255
Author: Mike Bishop <<email>>
Date:   Fri Oct 23 13:10:55 2026 -0400

    Learn home only from a fix taken after the car reached its TWC
    
    A cloud read that found the car away nine minutes before it was plugged
    in at home was still under the 10-minute fix age when the TWC read its
    VIN, so home moved to it and the car on its own TWC counted as away. A
    fix not read over BLE now has to date from no earlier than five minutes
    before the car reached its TWC: its plug-in mark, or the VIN read, since
    the session's plug-in mark stays on the anonymous session the VIN read
    replaces. BLE answers only within range and keeps the age rule alone.
    
    Presence dates a position the same way, by its GPS time, both for the
    "outside" mark and for the newest fix: an old away fix read after the
    plug-in loses to the newer plug-in and VIN read.
    
    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
---
 CHANGELOG.md                          |  2 +-
 docs/PolicyCustomization.md           |  2 +-
 docs/Settings.md                      |  2 +-
 docs/modules/Vehicle_HomeAssistant.md |  2 +-
 lib/TWCManager/Vehicle/Presence.py    | 32 ++++++++++----
 tests/unit/test_presence.py           | 83 +++++++++++++++++++++++++++++++++++
 6 files changed, 111 insertions(+), 12 deletions(-)

diff --git a/CHANGELOG.md b/CHANGELOG.md
index 60a41942..294d0679 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -11,21 +11,21 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - Fetch charge and location state over BLE, falling back to Fleet API when BLE is unavailable
     * (@ngardiner) - FleetAPI Authorization Code web login (PKCE by default, optional client-secret flow), with auto-capture callback and paste-back, ported from v1.3.4 (closes #639)
     * Add vehicle commandPolicy (prefer_ble/ble_only/api_only) to restrict state-changing commands to BLE or API, capping billed Fleet API command spend; configurable from the Settings page, with optional hard override in config.json (closes #651)
     * Add MQTT control topics for nonScheduledAmpsMax and nonScheduledAction to allow policy control via MQTT (closes #475)
     * (@MikeBishop) - Accept a bare access or refresh token on the Tesla login paste-back (#687)
     * (@MikeBishop) - Hold an Owner API token and a Fleet API token side by side: reads use the free Owner API, commands use Fleet, and TeslaMate sync can stay on beside a Fleet login (#692)
     * (@MikeBishop) - Show each Tesla token slot's status on the Settings page, with a Remove token button (#692)
     * (@MikeBishop) - Gen3 Wall Connectors each get their own target; several units on one bus share the headroom. TWCManager names the car on a Gen3 with a free read of the energy site's live status. This needs the Gen3 registered in the Tesla app and a token that can read energy data (a Fleet API token with the `energy_device_data` scope); a unit's optional `din` key fixes a wrong DIN guess
     * (@MikeBishop) - `controller.Gen2TWCs.ranges` sets a per-TWC `minAmps` (in place of minAmpsPerTWC) and `maxAmps`
     * (@MikeBishop) - TeslaBLE's default command timeout is 15 s (was 5 s); authenticated commands often needed more than 5 s
-    * (@MikeBishop) - `atHomeRadius` defaults to 1,000 ft (was 10,560 ft); a configured value still wins. Home is no longer taken from the first car position seen: it is set or moved only from a fresh position (under 10 minutes old, by the fix's own GPS time) when a TWC reads the car's VIN or the position arrives over BLE, and, with no home set yet, also from a fresh position that arrives while a TWC is naming the car; otherwise it is set on the Settings page. A car-only install with no TWC and no BLE must set home on the Settings page: a warning says so once, and until then cars known only through vehicle APIs are not treated as home and get no limit
+    * (@MikeBishop) - `atHomeRadius` defaults to 1,000 ft (was 10,560 ft); a configured value still wins. Home is no longer taken from the first car position seen: it is set or moved only from a fresh position (under 10 minutes old, by the fix's own GPS time) when a TWC reads the car's VIN or the position arrives over BLE, and, with no home set yet, also from a fresh position that arrives while a TWC is naming the car; a position not read over BLE must also date from no more than 5 minutes before the car reached its TWC (its plug-in or the VIN read), so a fix from before the drive home never moves home, and a position counts from its own GPS time, so such a fix read after the car is plugged in never makes it away; otherwise it is set on the Settings page. A car-only install with no TWC and no BLE must set home on the Settings page: a warning says so once, and until then cars known only through vehicle APIs are not treated as home and get no limit
     * (@MikeBishop) - The Vehicles page shows each car's presence (Home, Probably home, Away), and a vehicle's page lists its pending commands, one line each: in flight, or why not sent. The debug dump no longer carries the per-field summary
     * (@MikeBishop) - A Gen2 TWC's unplug ends its plug session (before, 5 seconds after charging stopped). A Gen2 status change (a 00, the TWC's maximum amps dropping to 0 during one, or a change between plugged and not) only makes TWCManager check the car, about 20 s after the first change, once per event and never waking it: a live telemetry feed's report since the change; else BLE's sleep-safe check (a sleeping car is still plugged in, as unplugging wakes it, and so is one the check cannot tell is awake) and a BLE charge read of an awake one; else the Tesla API, which reads only a car its free online check finds awake (on the Fleet API that read is billed, about once per real plug event when BLE is absent or down). A check that can't tell runs once more two minutes after the change, as the cloud can lag an unplug's wake. A car nothing can check is never unplugged by the TWC alone. The log shows each change and the answer (`TWC <id>: 03 → 00, max ... A: checking <VIN>`, `TWC <id>: plugged in: ...`, `unplugged, <VIN> departs`)
     * (@MikeBishop) - Fleet Telemetry maps the charger fields (`ChargeAmps`, `ChargerVoltage`, `ChargerPhases`, `ChargeCurrentRequest`, and `FastChargerPresent`, `FastChargerType`, `ChargingCableType`, `ACChargingPower`, `ChargeCurrentRequestMax` to tell a home charger from a fast charger nearby) and reads the typed values Tesla sends. The module's doc lists the fields presence needs and suggests a `minimum_delta` for the numeric ones, so the car sends fewer messages without losing anything TWCManager uses
     * (@MikeBishop) - With a Fleet API token, TWCManager reads each car's Fleet Telemetry config (free, never wakes the car) a few minutes after start and daily, and warns once, in the log and on the car's page, when the car has no config, has not applied it, or lacks a needed field. Every car on the Fleet account is checked, so a car you do not stream warns too
     * (@MikeBishop) - INFO log lines for each reconciler outcome, each paid Fleet API request (endpoint and price, never the URL, VIN or token), and each telemetry change of plug state, drive state or geofence
     * (@MikeBishop) - A sleeping car is left alone: before a command that may not wake it, TWCManager checks the car without waking it (BLE's sleep-safe check, or the Tesla API's free online check), and if the car is asleep the command waits (logged once) instead of failing and retrying, so no paid Fleet API command goes to a car known asleep. While the car is known asleep nothing is run, until a sign of life (a newer awake state from any source, a plug or unplug, a drive start or end, current drawn, or a successful wake); for a car no live telemetry feed reports on, the Tesla API's free online check looks again every 15 minutes while the car is home and every 30 minutes elsewhere, and only an awake answer sends the command (an asleep one is not logged again). Commands that may wake the car still do, except while its charger is offered 0 A; once the offer rises the car is woken for the raise
 * Architecture
     * Remove Tesla Owner API login flow; FleetAPI, TeslaMate token sync, manual token entry and BLE remain the supported paths, with Owner API tokens used for reads, and for commands only to vehicles Tesla reports with `command_signing: off`
     * (@MikeBishop) - Saved Tesla tokens migrate to separate Owner and Fleet settings on first start; downgrading afterwards loses the Owner API token (#692)
     * (@MikeBishop) - Held charge limits in settings `chargeLimits` are keyed by VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them. After a downgrade, only 1.3.x's TeslaBLE path reads the VIN-keyed entries; its Tesla API path, keyed by numeric ID, starts over
diff --git a/docs/PolicyCustomization.md b/docs/PolicyCustomization.md
index 2c77ef92..651a336b 100644
--- a/docs/PolicyCustomization.md
+++ b/docs/PolicyCustomization.md
@@ -93,21 +93,21 @@ checking <VIN>`, `TWC <id>: plugged in: ...`, `unplugged, <VIN> departs`).
 A Gen2 TWC that reads no VIN names the car another way: the one car that
 reported plugging in just now, else the one whose BLE charge read matches the
 TWC's pilot and draw, else the one car in BLE range or parked inside the
 radius.  When no car can be home (it left BLE range while away and has not
 been heard since), the plug-in itself is the evidence that a car arrived:
 one BLE range scan listens for every car, never waking any, and a car it
 hears is home and can be named.  While the plug stays unnamed and draws
 current, news of a car (BLE contact, or a plug report) tries again.  The log
 says `<id>: no single car plugged in; left anonymous` once per plug-in.
 
-Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time, that the car actually reported (a feed's retained copy, redelivered at a restart or reconnect, never counts). That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
+Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time, that the car actually reported (a feed's retained copy, redelivered at a restart or reconnect, never counts). That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. A position not read over BLE must also date from no more than 5 minutes before the car reached its TWC (its plug-in or the VIN read), so a fix from before the drive home never moves home. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
 
 A car's start and charge rate commands also need the car to be plugged in
 here.  A TWC's own commands (start, stop, amps) are never held back by where a
 car is.  Raising a car's limit may wake it, but lowering one never does, and
 nothing wakes a car for a raise while its TWC or charger is offered 0 A.
 When a car leaves, its original limit is sent wherever it is, without waking
 it.
 
 Known limits: a guest car that later plugs in to the same TWC can keep a car
 that left idle counted as home until that car reports a position outside the
diff --git a/docs/Settings.md b/docs/Settings.md
index e9f6efc5..fc82d04c 100644
--- a/docs/Settings.md
+++ b/docs/Settings.md
@@ -1,21 +1,21 @@
 # Settings
 
 The following settings (outside of the configuration file) are available via the inbuilt Web Interface:
 
 ## Web Interface Theme
 
 Allows you to select which theme you'd like to use for the TWCManager interface.
 
 ## Home Location
 
-Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time. That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
+Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time. That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. A position not read over BLE must also date from no more than 5 minutes before the car reached its TWC (its plug-in or the VIN read), so a fix from before the drive home never moves home. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
 
 ## Stop Charging Method
 
 This option, which defaults to a vehicle command, allows you to specify how you would like TWCManager to stop a car from charging. The following options exist, and each has some information to help you decide on which approach to use:
 
    * Vehicle command (BLE or API)
       * This method sends a stop charging command to vehicles which are detected as being "at home" (see Charge Limits in Policy Customization for how that is decided), over BLE where available and the Tesla API otherwise (see Vehicle Command Policy below).
       * This method is only effective for Tesla vehicles. Any non-Tesla vehicles are not visible via the Tesla API and will not be stopped, even if the available power falls below the minimum power per TWC.
       * For those vehicles, they will continue to charge, but at the minimum power per TWC rate.
    * Stop Responding to Slaves
diff --git a/docs/modules/Vehicle_HomeAssistant.md b/docs/modules/Vehicle_HomeAssistant.md
index 03902bd5..7f3a6103 100644
--- a/docs/modules/Vehicle_HomeAssistant.md
+++ b/docs/modules/Vehicle_HomeAssistant.md
@@ -83,21 +83,21 @@ After discovery, **ongoing interaction uses the Home Assistant REST API only**:
 
 The module uses this data to:
 
 * report each vehicle's battery level, charge limit, charge current setting,
   charging state and location to TWCManager's vehicle registry
 * keep each vehicle's `battery_level`
 * expose aggregate properties to TWCManager such as:
   * `numCarsAtHome`
   * `minBatteryLevelAtHome`
 
-Where a car is comes from TWCManager's presence rules (see Charge Limits in [Policy Customization](../PolicyCustomization.md)), using the car's Home Assistant location along with its other evidence. Home is set or moved only from a fresh position read of a car (under 10 minutes old, by the fix's own GPS time): when a TWC reads the car's VIN, or when the position arrives over BLE, or, with no home set yet, when a fresh position arrives while a TWC is naming the car. It is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page. A zone state of `home` with no coordinates no longer places a car at home. `atHomeRadius` (in feet) defaults to 1,000.
+Where a car is comes from TWCManager's presence rules (see Charge Limits in [Policy Customization](../PolicyCustomization.md)), using the car's Home Assistant location along with its other evidence. Home is set or moved only from a fresh position read of a car (under 10 minutes old, by the fix's own GPS time, and, unless read over BLE, no more than 5 minutes before the car reached its TWC): when a TWC reads the car's VIN, or when the position arrives over BLE, or, with no home set yet, when a fresh position arrives while a TWC is naming the car. It is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page. A zone state of `home` with no coordinates no longer places a car at home. `atHomeRadius` (in feet) defaults to 1,000.
 
 ### Charging Control
 
 To control charging, the module calls **Home Assistant services**:
 
 * **Start charging**
   → `POST /api/services/switch/turn_on` with `{"entity_id": "switch.<slug>_charge"}`
 * **Stop charging**
   → `POST /api/services/switch/turn_off` with `{"entity_id": "switch.<slug>_charge"}`
 * **Set charge limit (%)**
diff --git a/lib/TWCManager/Vehicle/Presence.py b/lib/TWCManager/Vehicle/Presence.py
index 10dd638b..cff6d9ae 100644
--- a/lib/TWCManager/Vehicle/Presence.py
+++ b/lib/TWCManager/Vehicle/Presence.py
@@ -7,20 +7,22 @@ from typing import Any, List, Optional, Tuple
 from .Providers.Capability import SET_CHARGE_LIMIT
 from .Registry.Fields import TELEMETRY_SOURCES
 
 logger = logging.getLogger(__name__.split(".")[0] + ".Vehicle.Presence")
 
 HOME, PRESUMED, NOT_HOME = "home", "presumed", "notHome"
 # applicable's verdicts on one message
 SEND, NOT_HERE, HOLD = "send", "not here", "hold"
 HOME_RADIUS_FT = 1000
 HOME_FIX_MAX_AGE = 600.0
+# A parked car's last fix is from when it stopped, before the plug went in
+PARKING_SLACK = 300.0
 REACH_WINDOW = 300.0
 # The least time between status checks of a car known asleep that no live
 # feed reports on: at home, and anywhere else
 HOME_ASLEEP_SECS, AWAY_ASLEEP_SECS = 900.0, 1800.0
 PILOT_MATCH_TOLERANCE, PLUGGED_JUST_NOW = 1, 120.0
 _BLE_CHARGE = ("chargingState", "availableCurrent", "actualCurrent")
 # A fast charger type other than these is not a home charger
 HOME_CHARGER_TYPES = frozenset({"ACSingleWireCAN", "MCSingleWireCAN", "<invalid>", ""})
 _PLUGGED = frozenset({"Charging", "Starting", "Stopped", "Complete", "NoPower"})
 # A plug report from these needs no position: the charger or the radio is here
@@ -44,25 +46,26 @@ def _within(master, lat, lon) -> Optional[bool]:
     home = master.getHomeLatLon()
     if home[0] == 10000:
         _warnNoHome()
         return None
     config = (getattr(master, "config", None) or {}).get("config", {})
     deg = float(config.get("atHomeRadius", HOME_RADIUS_FT)) / _FT_PER_DEGREE
     return abs(home[0] - lat) <= deg and abs(home[1] - lon) <= deg
 
 
 def _fix(master, v) -> Tuple[Optional[bool], float]:
-    # The newest position: inside the radius (None if unknown) and its time
+    # The newest position: inside the radius (None if unknown) and when the
+    # car was there
     lat, lon = v.latest("lat"), v.latest("lon")
     if lat is None or lon is None:
         return None, NEVER
-    return _within(master, lat.value, lon.value), max(lat.at, lon.at)
+    return _within(master, lat.value, lon.value), max(_fixAt(v, lat), _fixAt(v, lon))
 
 
 def inside(master, v) -> Optional[bool]:
     return _fix(master, v)[0]
 
 
 def _plug(field, obs) -> Optional[bool]:
     # True plugged, False unplugged, None says nothing
     if field == "pluggedIn":
         return obs.value if isinstance(obs.value, bool) else None
@@ -112,21 +115,22 @@ def noteObservation(master, vehicle, field, obs, previous) -> None:
             back = obs.value and not _reached(master, vehicle)
             vehicle.mark("contact" if obs.value else "absent", at)
             # A car heard again may be the one on an unnamed plug
             if back and not vehicle.value("twcVin"):
                 master.attributePlugs()
     elif field in ("lat", "lon"):
         # With the same source's other coordinate: one may change alone
         other = vehicle.reported("lon" if field == "lat" else "lat").get(obs.source)
         lat, lon = (obs, other) if field == "lat" else (other, obs)
         if other is not None and _within(master, lat.value, lon.value) is False:
-            vehicle.mark("outside", at)
+            # Where the car was then: a stale fix loses to newer evidence
+            vehicle.mark("outside", _fixAt(vehicle, obs))
         # A BLE location read answers only within range
         if obs.source == "TeslaBLE" or twcVinAt(master, vehicle) > NEVER:
             learnHome(master, vehicle, lat, lon)
     elif field in ("shiftState", "state"):
         here = inside(master, vehicle)
         moving, wasMoving = _driving(field, obs.value), _driving(field, before)
         if obs.seen and moving != wasMoving:
             vehicle.mark("lifeAt", at)
         if moving and not wasMoving and here is not False:
             vehicle.mark("driveStart", at)
@@ -468,30 +472,42 @@ def attribute(master, pointId, source, offered=None, actual=0) -> Optional[str]:
     master.vehicleRegistry.observeTwcVin(pointId, v.vin)
     v.observe("pluggedIn", True, source)
     return v.vin
 
 
 def homeCars(master, attachment) -> List[Tuple[Any, Any]]:
     pairs = master.vehicleRegistry.attached(attachment)
     return [(v, a) for v, a in pairs if presence(master, v) != NOT_HOME]
 
 
+def _fixAt(vehicle, obs) -> float:
+    # A fix is dated by the GPS time its source gave (observed before the
+    # position), else by its reading's time
+    gps = vehicle.reported("gpsAsOf").get(obs.source)
+    return obs.at if gps is None else min(obs.at, gps.value)
+
+
 def learnHome(master, vehicle, lat, lon) -> bool:
     # A car a TWC names, or BLE reads, is here: a fresh fix outside the
     # radius, or with no home yet, moves home to it. A stale fix may be
-    # wherever the car last had reception: the GPS time its source gave
-    # (observed before the position) dates it, else its reading's time. A
-    # retained or redelivered copy is never a fix, whatever its stamp.
+    # wherever the car last had reception. A retained or redelivered copy
+    # is never a fix, whatever its stamp. A cloud fix may predate the drive
+    # home, so it must be from after the car reached its TWC: its plug-in,
+    # or the VIN read (the session's plug-in mark stays on the anonymous
+    # session the VIN read replaces).
     if lat is None or lon is None or not (lat.seen and lon.seen):
         return False
-    gps = vehicle.reported("gpsAsOf").get(lat.source)
-    fixAt = lat.at if gps is None else min(lat.at, gps.value)
+    fixAt = _fixAt(vehicle, lat)
+    named = getattr(vehicle.latest("twcVin"), "at", NEVER)
+    arrived = max(vehicle.markAt("plugIn"), named)
+    if lat.source != "TeslaBLE" and fixAt < arrived - PARKING_SLACK:
+        return False
     if master.vehicleRegistry.now() - fixAt > HOME_FIX_MAX_AGE:
         return False
     if _within(master, lat.value, lon.value):
         return False
     logger.info("Home set to %s's position on a TWC", vehicle.key)
     master.setHomeLat(lat.value)
     master.setHomeLon(lon.value)
     master.queue_background_task({"cmd": "sunrise"})
     master.queue_background_task({"cmd": "saveSettings"})
     return True
diff --git a/tests/unit/test_presence.py b/tests/unit/test_presence.py
index 668c3e61..a2129290 100644
--- a/tests/unit/test_presence.py
+++ b/tests/unit/test_presence.py
@@ -1683,10 +1683,93 @@ def test_a_car_seen_outside_while_still_driving_has_departed(requests_mock):
     push(v, c, shiftState="P")
     assert v.markAt("driveEnd") == c.t
     c.t += 600
     placed_at = c.t
     placeAt(m, v, AWAY)
     push(v, c, shiftState="D")
     assert P.decide(m, v)[0] == P.NOT_HOME and P.drivingNow(v)
     assert P.departed(m, v) == placed_at
     m.setPolicyLimit(50, transition=False)
     assert m.desired.get(VIN, CHARGE_LIMIT).restore
+
+
+def cloudFix(v, at, source="FleetAPI", gpsAsOf=None):
+    if gpsAsOf is not None:
+        v.observe("gpsAsOf", gpsAsOf, source)
+    v.observe("lat", at[0], source)
+    v.observe("lon", at[1], source)
+
+
+def plugAndName(m, v, c, monkeypatch, seconds=13):
+    # A Gen2 plug-in, its session, and its VIN read seconds later
+    monkeypatch.setattr(time, "time", c)
+    s = m.getSlaveTWCs()[0]
+    s.reportedState, s.currentVIN = 0x03, VIN
+    m.vehicleRegistry.beginPlugSession("8244")
+    later(c, seconds)
+    m.recordVehicleVIN(s)
+    return s
+
+
+def test_an_away_fix_from_before_the_plug_in_never_moves_home(monkeypatch):
+    # The read that found the car away, 9 minutes before it was plugged in
+    # at home: still under HOME_FIX_MAX_AGE, but not where the TWC is
+    m, r, v, c = home()
+    m.queue_background_task = Mock()
+    cloudFix(v, AWAY)
+    later(c, 540)
+    plugAndName(m, v, c, monkeypatch)
+    assert m.getHomeLatLon() == list(HOME) and P.presence(m, v) == P.HOME
+
+
+@pytest.mark.parametrize("homeAt", [None, "elsewhere"])
+def test_a_fix_just_before_the_plug_in_teaches_home(monkeypatch, homeAt):
+    # A parked car's last fix is from when it stopped, a minute before the plug
+    m, r, v, c = setup(here=False)
+    m.queue_background_task = Mock()
+    if homeAt:
+        m.settings.update(homeLat=HOME[0], homeLon=HOME[1])
+    cloudFix(v, AWAY)
+    later(c, 60)
+    plugAndName(m, v, c, monkeypatch)
+    assert m.getHomeLatLon() == list(AWAY) and P.presence(m, v) == P.HOME
+
+
+def test_a_fix_read_after_the_vin_dated_before_the_plug_in_never_moves_home(
+    monkeypatch,
+):
+    # No home yet. A cloud read while the TWC names the car, whose GPS time
+    # is 8 minutes before the plug-in
+    m, r, v, c = setup(here=False)
+    m.queue_background_task = Mock()
+    plugAndName(m, v, c, monkeypatch)
+    later(c, 30)
+    cloudFix(v, AWAY, gpsAsOf=c.t - 30 - 13 - 480)
+    assert m.getHomeLatLon()[0] == 10000
+    later(c)
+    cloudFix(v, AWAY, gpsAsOf=c.t - 1)  # a fix taken here teaches it
+    assert m.getHomeLatLon() == list(AWAY)
+
+
+def test_a_ble_fix_from_before_the_plug_in_still_teaches_home(monkeypatch):
+    # BLE answers only in range: its fix keeps the age rule alone
+    m, r, v, c = home()
+    m.queue_background_task = Mock()
+    plugAndName(m, v, c, monkeypatch)
+    later(c)
+    assert bleFix(m, v, AWAY, c.t - 480)
+    assert m.getHomeLatLon() == list(AWAY)
+
+
+def test_a_stale_away_fix_arriving_after_the_plug_in_keeps_the_car_home(
+    monkeypatch,
+):
+    # A cloud read after the VIN read, whose GPS time is 9 minutes before the
+    # plug-in: the newer plug-in and VIN read outrank where it was then
+    m, r, v, c = home()
+    m.queue_background_task = Mock()
+    plugged = c.t
+    plugAndName(m, v, c, monkeypatch)
+    later(c, 30)
+    cloudFix(v, AWAY, gpsAsOf=plugged - 540)
+    assert P.presence(m, v) == P.HOME and m.getHomeLatLon() == list(HOME)
+    assert P.applicable(m, v, C.SET_CHARGE_LIMIT)[0] == P.SEND

## phase6: rebase differences (old range vs new)
 1:  01bbedb4 <  -:  -------- Count a wake as done when the car connects seconds later
 2:  d770b716 <  -:  -------- Count current at the car's TWC as the car charging, for a start
 3:  3027a953 <  -:  -------- Recheck a cloud hold with the online check alone
 4:  f3ebd426 !  1:  abca0e94 Read the charge-port door on the sleep-safe ping; a closed door is an unplug
    @@ tests/unit/test_command_path_parity.py: def test_a_car_just_unplugged_is_not_the
          attributeQueued(m)
     
      ## tests/unit/test_presence.py ##
    -@@ tests/unit/test_presence.py: def test_a_car_seen_outside_while_still_driving_has_departed(requests_mock):
    -     assert P.departed(m, v) == placed_at
    -     m.setPolicyLimit(50, transition=False)
    -     assert m.desired.get(VIN, CHARGE_LIMIT).restore
    +@@ tests/unit/test_presence.py: def test_a_stale_away_fix_arriving_after_the_plug_in_keeps_the_car_home(
    +     cloudFix(v, AWAY, gpsAsOf=plugged - 540)
    +     assert P.presence(m, v) == P.HOME and m.getHomeLatLon() == list(HOME)
    +     assert P.applicable(m, v, C.SET_CHARGE_LIMIT)[0] == P.SEND
     +
     +
     +def test_a_closed_charge_port_while_awake_marks_an_unplug():
 5:  5cd05170 =  2:  d45b858d An asleep car draws nothing; asleep after Charging, it has finished
 6:  79543c9a =  3:  01f69b9c Add a monthly budget for paid vehicle reads, kept across restarts
 7:  ec820bce !  4:  9c878c42 Watch cars no TWC or live feed covers; read one when something changes
    @@ lib/TWCManager/TWCMaster.py: class TWCMaster:
              self.providerOrder.register(Gen2TWCProvider(self))
     
      ## lib/TWCManager/Vehicle/Presence.py ##
    -@@ lib/TWCManager/Vehicle/Presence.py: HOME_RADIUS_FT = 1000
    - HOME_FIX_MAX_AGE = 600.0
    +@@ lib/TWCManager/Vehicle/Presence.py: HOME_FIX_MAX_AGE = 600.0
    + PARKING_SLACK = 300.0
      REACH_WINDOW = 300.0
      # The least time between status checks of a car known asleep that no live
     -# feed reports on: at home, and anywhere else
    @@ lib/TWCManager/Vehicle/Reconcile/Run.py: _badReturns = set()
      _badLock = threading.Lock()
      
      
    --# BLE work that is no command (a scan, an attribution): one pending per
    --# (key, kind), in turn on the BLE worker
    +-# Work that is no command (a scan, an attribution, an online check): one
    +-# pending per (key, kind), in turn on its worker
     -Job = collections.namedtuple("Job", "key kind run")
    -+# Work that is no command (a scan, an attribution, a status check): one
    -+# pending per (key, kind), in turn on its worker. done, if given, has the
    -+# result or why it never ran, once
    ++# Work that is no command (a scan, an attribution, a status or online
    ++# check): one pending per (key, kind), in turn on its worker. done, if
    ++# given, has the result or why it never ran, once
     +Job = collections.namedtuple("Job", "key kind run done", defaults=(None,))
      
      
 8:  4e72af0f =  5:  d3fccf68 Hear an away car come back; read a car only the cloud sees on a clock
 9:  465fe143 =  6:  a25f7826 Read the watched car a consumption step may come from
10:  72339e56 =  7:  fa81f8d2 Scan for cars from Docker; say why when no range scan can run
11:  6332b50c =  8:  b1f6a2cb Run the watch on the control tick; show it on the Vehicles page
12:  12192993 =  9:  b48d5860 Let the watch replace the deferral ladder and the half-hourly battery refresh
13:  c7c14fac = 10:  c7899570 Document the vehicle watch
14:  8e2afe2f = 11:  dbd91043 Replay the missed overnight charge under a 6 A sleep pilot
