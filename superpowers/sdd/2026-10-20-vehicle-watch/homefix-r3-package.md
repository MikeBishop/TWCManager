commit d370287b8a057e7c8a0451cda09bf0d40222efc4
Author: Mike Bishop <<email>>
Date:   Fri Oct 23 13:10:55 2026 -0400

    Learn home only from a fix taken after the car reached its TWC
    
    A cloud read that found the car away nine minutes before it was plugged
    in at home was still under the 10-minute fix age when the TWC read its
    VIN, so home moved to it and the car on its own TWC counted as away. A
    position not read over BLE now moves or sets home only if it was read at
    or after the car reached its TWC: the later of its plug-in mark and the
    VIN read, since a Gen2's plug-in mark stays on the anonymous session the
    VIN read replaces. A read made after that shows where the car is now,
    even when its GPS time is older. BLE answers only within range and keeps
    the age rule alone.
    
    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
---
 CHANGELOG.md                                  |  2 +-
 docs/PolicyCustomization.md                   |  2 +-
 docs/Settings.md                              |  2 +-
 docs/modules/Vehicle_HomeAssistant.md         |  2 +-
 lib/TWCManager/Vehicle/Presence.py            |  8 +++-
 tests/unit/test_presence.py                   | 63 +++++++++++++++++++++++++++
 tests/unit/test_twcmaster_vin_confirmation.py |  9 ++--
 7 files changed, 80 insertions(+), 8 deletions(-)

diff --git a/CHANGELOG.md b/CHANGELOG.md
index 60a41942..9155e538 100644
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
+    * (@MikeBishop) - `atHomeRadius` defaults to 1,000 ft (was 10,560 ft); a configured value still wins. Home is no longer taken from the first car position seen: it is set or moved only from a fresh position (under 10 minutes old, by the fix's own GPS time) when a TWC reads the car's VIN or the position arrives over BLE, and, with no home set yet, also from a fresh position that arrives while a TWC is naming the car; a position not read over BLE must also have been read after the car reached its TWC (its plug-in or the VIN read), so a read from before the drive home never moves home; otherwise it is set on the Settings page. A car-only install with no TWC and no BLE must set home on the Settings page: a warning says so once, and until then cars known only through vehicle APIs are not treated as home and get no limit
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
index 2c77ef92..ac05f755 100644
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
+Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time, that the car actually reported (a feed's retained copy, redelivered at a restart or reconnect, never counts). That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. A position not read over BLE must also have been read after the car reached its TWC (its plug-in or the VIN read), so a read from before the drive home never moves home. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
 
 A car's start and charge rate commands also need the car to be plugged in
 here.  A TWC's own commands (start, stop, amps) are never held back by where a
 car is.  Raising a car's limit may wake it, but lowering one never does, and
 nothing wakes a car for a raise while its TWC or charger is offered 0 A.
 When a car leaves, its original limit is sent wherever it is, without waking
 it.
 
 Known limits: a guest car that later plugs in to the same TWC can keep a car
 that left idle counted as home until that car reports a position outside the
diff --git a/docs/Settings.md b/docs/Settings.md
index e9f6efc5..d8eaf3a7 100644
--- a/docs/Settings.md
+++ b/docs/Settings.md
@@ -1,21 +1,21 @@
 # Settings
 
 The following settings (outside of the configuration file) are available via the inbuilt Web Interface:
 
 ## Web Interface Theme
 
 Allows you to select which theme you'd like to use for the TWCManager interface.
 
 ## Home Location
 
-Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time. That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
+Home is set or moved only from a fresh position read of a car: a position under 10 minutes old, by the fix's own GPS time. That happens when a TWC reads the car's VIN, or when the car's position arrives over BLE. When no home is set yet, a fresh position that arrives while a TWC is naming the car sets it too. A position not read over BLE must also have been read after the car reached its TWC (its plug-in or the VIN read), so a read from before the drive home never moves home. Home is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page (use the vehicle location button), or with `homeLat` and `homeLon` through the [setSetting API](modules/control_HTTP_API/setSetting.md). Until then TWCManager logs a warning once, and a car known only through vehicle APIs is never treated as home and gets no limit. `atHomeRadius` defaults to 1,000 feet.
 
 ## Stop Charging Method
 
 This option, which defaults to a vehicle command, allows you to specify how you would like TWCManager to stop a car from charging. The following options exist, and each has some information to help you decide on which approach to use:
 
    * Vehicle command (BLE or API)
       * This method sends a stop charging command to vehicles which are detected as being "at home" (see Charge Limits in Policy Customization for how that is decided), over BLE where available and the Tesla API otherwise (see Vehicle Command Policy below).
       * This method is only effective for Tesla vehicles. Any non-Tesla vehicles are not visible via the Tesla API and will not be stopped, even if the available power falls below the minimum power per TWC.
       * For those vehicles, they will continue to charge, but at the minimum power per TWC rate.
    * Stop Responding to Slaves
diff --git a/docs/modules/Vehicle_HomeAssistant.md b/docs/modules/Vehicle_HomeAssistant.md
index 03902bd5..25dfa691 100644
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
+Where a car is comes from TWCManager's presence rules (see Charge Limits in [Policy Customization](../PolicyCustomization.md)), using the car's Home Assistant location along with its other evidence. Home is set or moved only from a fresh position read of a car (under 10 minutes old, by the fix's own GPS time, and, unless it came over BLE, read after the car reached its TWC): when a TWC reads the car's VIN, or when the position arrives over BLE, or, with no home set yet, when a fresh position arrives while a TWC is naming the car. It is never set from a car's first position otherwise. A car-only install with no TWC and no BLE must set home on the Settings page. A zone state of `home` with no coordinates no longer places a car at home. `atHomeRadius` (in feet) defaults to 1,000.
 
 ### Charging Control
 
 To control charging, the module calls **Home Assistant services**:
 
 * **Start charging**
   → `POST /api/services/switch/turn_on` with `{"entity_id": "switch.<slug>_charge"}`
 * **Stop charging**
   → `POST /api/services/switch/turn_off` with `{"entity_id": "switch.<slug>_charge"}`
 * **Set charge limit (%)**
diff --git a/lib/TWCManager/Vehicle/Presence.py b/lib/TWCManager/Vehicle/Presence.py
index 10dd638b..b9579a2f 100644
--- a/lib/TWCManager/Vehicle/Presence.py
+++ b/lib/TWCManager/Vehicle/Presence.py
@@ -473,23 +473,29 @@ def attribute(master, pointId, source, offered=None, actual=0) -> Optional[str]:
 def homeCars(master, attachment) -> List[Tuple[Any, Any]]:
     pairs = master.vehicleRegistry.attached(attachment)
     return [(v, a) for v, a in pairs if presence(master, v) != NOT_HOME]
 
 
 def learnHome(master, vehicle, lat, lon) -> bool:
     # A car a TWC names, or BLE reads, is here: a fresh fix outside the
     # radius, or with no home yet, moves home to it. A stale fix may be
     # wherever the car last had reception: the GPS time its source gave
     # (observed before the position) dates it, else its reading's time. A
-    # retained or redelivered copy is never a fix, whatever its stamp.
+    # retained or redelivered copy is never a fix, whatever its stamp. A
+    # cloud read made before the car reached its TWC may be from before the
+    # drive home: its plug-in, or the VIN read (a Gen2's plug-in mark stays
+    # on the anonymous session the VIN read replaces)
     if lat is None or lon is None or not (lat.seen and lon.seen):
         return False
+    named = getattr(vehicle.latest("twcVin"), "at", NEVER)
+    if lat.source != "TeslaBLE" and lat.at < max(vehicle.markAt("plugIn"), named):
+        return False
     gps = vehicle.reported("gpsAsOf").get(lat.source)
     fixAt = lat.at if gps is None else min(lat.at, gps.value)
     if master.vehicleRegistry.now() - fixAt > HOME_FIX_MAX_AGE:
         return False
     if _within(master, lat.value, lon.value):
         return False
     logger.info("Home set to %s's position on a TWC", vehicle.key)
     master.setHomeLat(lat.value)
     master.setHomeLon(lon.value)
     master.queue_background_task({"cmd": "sunrise"})
diff --git a/tests/unit/test_presence.py b/tests/unit/test_presence.py
index 668c3e61..1f4fc6ef 100644
--- a/tests/unit/test_presence.py
+++ b/tests/unit/test_presence.py
@@ -1683,10 +1683,73 @@ def test_a_car_seen_outside_while_still_driving_has_departed(requests_mock):
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
+def test_a_read_after_the_plug_in_teaches_home_whatever_its_gps_time(monkeypatch):
+    # No home yet. Read 30 s after the plug-in, its GPS time 3 minutes
+    # before it: the read shows where the car is now
+    m, r, v, c = setup(here=False)
+    m.queue_background_task = Mock()
+    plugged = c.t
+    plugAndName(m, v, c, monkeypatch)
+    later(c, 30 - 13)
+    cloudFix(v, AWAY, gpsAsOf=plugged - 180)
+    assert m.getHomeLatLon() == list(AWAY) and P.presence(m, v) == P.HOME
+
+
+def test_a_ble_fix_read_before_the_vin_read_still_moves_home_at_it(monkeypatch):
+    # BLE answers only within range, so its fix needs no read after the
+    # plug-in: a wrong home moves to it when the TWC reads the VIN
+    m, r, v, c = home()
+    m.queue_background_task = Mock()
+    assert bleFix(m, v, HOME, c.t - 5)
+    m.settings.update(homeLat=AWAY[0], homeLon=AWAY[1])
+    later(c, 60)
+    plugAndName(m, v, c, monkeypatch)
+    assert m.getHomeLatLon() == list(HOME) and P.presence(m, v) == P.HOME
diff --git a/tests/unit/test_twcmaster_vin_confirmation.py b/tests/unit/test_twcmaster_vin_confirmation.py
index 306f8dd3..0edff0e2 100644
--- a/tests/unit/test_twcmaster_vin_confirmation.py
+++ b/tests/unit/test_twcmaster_vin_confirmation.py
@@ -199,28 +199,31 @@ def test_delayed_tasks_with_equal_due_times_do_not_compare_dicts(queued):
     fixed = datetime(2026, 10, 14, 12, 0, 0)
     with patch("TWCManager.TWCMaster.datetime") as dt:
         dt.now.return_value = fixed
         queued.queue_background_task({"cmd": "first"}, delay=5)
         queued.queue_background_task({"cmd": "second"}, delay=5)
     assert [e[-1]["cmd"] for e in queued.backgroundTasksDelayed] == ["first", "second"]
 
 
 def test_a_confirmed_vin_learns_home_from_the_cars_fresh_fix_without_io(master):
     # recordVehicleVIN runs on the RS-485 thread: home is learned from the
-    # registry alone, never by reading the car
+    # registry alone, never by reading the car. A BLE fix: one from the cloud
+    # read before the VIN read may predate the drive home
     api = Mock()
     master.getModuleByName = Mock(
         side_effect=lambda n: api if n == "TeslaAPI" else None
     )
     v = master.vehicleRegistry.getOrCreate(VIN, "OwnerAPI")
-    v.observe("lat", 39.0, "TeslaMateVehicle")
-    v.observe("lon", -84.0, "TeslaMateVehicle")
+    master.settings.update(homeLat=39.0, homeLon=-84.0)
+    v.observe("lat", 39.0, "TeslaBLE")
+    v.observe("lon", -84.0, "TeslaBLE")
+    master.settings.update(homeLat=10000, homeLon=10000)
     master.recordVehicleVIN(slave(VIN))
     assert master.getHomeLatLon() == [39.0, -84.0] and api.mock_calls == []
     master.queue_background_task.assert_any_call({"cmd": "saveSettings"})
 
 
 def test_delayed_task_list_is_only_touched_under_the_tasks_lock(queued):  # M2
     # The serial thread inserts (VIN confirmation reads) while the
     # background thread pops.
     lock = queued.backgroundTasksLock = threading.Lock()
 

## phase6 home-fix commit vs phase5 (should match)
004f2235 Replay the missed overnight charge under a 6 A sleep pilot
822e8705 Document the vehicle watch
b34caf7d Let the watch replace the deferral ladder and the half-hourly battery refresh
152e3048 Run the watch on the control tick; show it on the Vehicles page
70bd4345 Scan for cars from Docker; say why when no range scan can run
b695ed1a Read the watched car a consumption step may come from
97d1eed0 Hear an away car come back; read a car only the cloud sees on a clock
3b7bd52f Watch cars no TWC or live feed covers; read one when something changes
beb7fa6e Add a monthly budget for paid vehicle reads, kept across restarts
1dc50112 An asleep car draws nothing; asleep after Charging, it has finished
367ecdff Read the charge-port door on the sleep-safe ping; a closed door is an unplug
d370287b Learn home only from a fix taken after the car reached its TWC
