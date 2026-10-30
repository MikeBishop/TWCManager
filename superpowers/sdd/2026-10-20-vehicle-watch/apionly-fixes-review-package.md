3027a953 Recheck a cloud hold with the online check alone
d770b716 Count current at the car's TWC as the car charging, for a start
01bbedb4 Count a wake as done when the car connects seconds later

 CHANGELOG.md                                   |  4 +-
 docs/Settings.md                               |  2 +-
 docs/modules/Vehicle_TeslaAPI.md               |  2 +-
 docs/modules/Vehicle_TeslaBLE.md               |  2 +-
 lib/TWCManager/Control/HTTPControl.py          |  2 +-
 lib/TWCManager/Vehicle/Reconcile/Belief.py     | 15 ++++--
 lib/TWCManager/Vehicle/Reconcile/Desired.py    |  1 +
 lib/TWCManager/Vehicle/Reconcile/Reconciler.py | 27 +++++++----
 lib/TWCManager/Vehicle/TeslaAPI.py             | 23 +++++++--
 tests/unit/reconcile_helpers.py                | 10 ++--
 tests/unit/test_command_path_parity.py         | 67 +++++++++++++++++++++++++-
 tests/unit/test_sleeping_car.py                | 26 ++++++++++
 tests/unit/test_teslaapi_wake.py               | 59 ++++++++++++++++++++++-
 13 files changed, 207 insertions(+), 33 deletions(-)

diff --git a/CHANGELOG.md b/CHANGELOG.md
index 32cc3574..75da4f9d 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -17,21 +17,21 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - Show each Tesla token slot's status on the Settings page, with a Remove token button (#692)
     * (@MikeBishop) - Gen3 Wall Connectors each get their own target; several units on one bus share the headroom. TWCManager names the car on a Gen3 with a free read of the energy site's live status. This needs the Gen3 registered in the Tesla app and a token that can read energy data (a Fleet API token with the `energy_device_data` scope); a unit's optional `din` key fixes a wrong DIN guess
     * (@MikeBishop) - `controller.Gen2TWCs.ranges` sets a per-TWC `minAmps` (in place of minAmpsPerTWC) and `maxAmps`
     * (@MikeBishop) - TeslaBLE's default command timeout is 15 s (was 5 s); authenticated commands often needed more than 5 s
     * (@MikeBishop) - `atHomeRadius` defaults to 1,000 ft (was 10,560 ft); a configured value still wins. Home is no longer taken from the first car position seen: it is set or moved only from a fresh position (under 10 minutes old, by the fix's own GPS time) when a TWC reads the car's VIN or the position arrives over BLE, and, with no home set yet, also from a fresh position that arrives while a TWC is naming the car; otherwise it is set on the Settings page. A car-only install with no TWC and no BLE must set home on the Settings page: a warning says so once, and until then cars known only through vehicle APIs are not treated as home and get no limit
     * (@MikeBishop) - The Vehicles page shows each car's presence (Home, Probably home, Away), and a vehicle's page lists its pending commands, one line each: in flight, or why not sent. The debug dump no longer carries the per-field summary
     * (@MikeBishop) - A Gen2 TWC's unplug ends its plug session (before, 5 seconds after charging stopped). A Gen2 status change (a 00, the TWC's maximum amps dropping to 0 during one, or a change between plugged and not) only makes TWCManager check the car, about 20 s after the first change, once per event and never waking it: a live telemetry feed's report since the change; else BLE's sleep-safe check (a sleeping car is still plugged in, as unplugging wakes it, and so is one the check cannot tell is awake) and a BLE charge read of an awake one; else the Tesla API, which reads only a car its free online check finds awake (on the Fleet API that read is billed, about once per real plug event when BLE is absent or down). A check that can't tell runs once more two minutes after the change, as the cloud can lag an unplug's wake. A car nothing can check is never unplugged by the TWC alone. The log shows each change and the answer (`TWC <id>: 03 → 00, max ... A: checking <VIN>`, `TWC <id>: plugged in: ...`, `unplugged, <VIN> departs`)
     * (@MikeBishop) - Fleet Telemetry maps the charger fields (`ChargeAmps`, `ChargerVoltage`, `ChargerPhases`, `ChargeCurrentRequest`, and `FastChargerPresent`, `FastChargerType`, `ChargingCableType`, `ACChargingPower`, `ChargeCurrentRequestMax` to tell a home charger from a fast charger nearby) and reads the typed values Tesla sends. The module's doc lists the fields presence needs and suggests a `minimum_delta` for the numeric ones, so the car sends fewer messages without losing anything TWCManager uses
     * (@MikeBishop) - With a Fleet API token, TWCManager reads each car's Fleet Telemetry config (free, never wakes the car) a few minutes after start and daily, and warns once, in the log and on the car's page, when the car has no config, has not applied it, or lacks a needed field. Every car on the Fleet account is checked, so a car you do not stream warns too
     * (@MikeBishop) - INFO log lines for each reconciler outcome, each paid Fleet API request (endpoint and price, never the URL, VIN or token), and each telemetry change of plug state, drive state or geofence
-    * (@MikeBishop) - A sleeping car is left alone: before a command that may not wake it, TWCManager checks the car without waking it (BLE's sleep-safe check, or the Tesla API's free online check), and if the car is asleep the command waits (logged once) instead of failing and retrying, so no paid Fleet API command goes to a car known asleep. While the car is known asleep nothing is run, until a sign of life (a newer awake state from any source, a plug or unplug, a drive start or end, current drawn, or a successful wake); for a car no live telemetry feed reports on, the Tesla API's free online check looks again every 15 minutes while the car is home and every 30 minutes elsewhere. Commands that may wake the car still do, except while its charger is offered 0 A; once the offer rises the car is woken for the raise
+    * (@MikeBishop) - A sleeping car is left alone: before a command that may not wake it, TWCManager checks the car without waking it (BLE's sleep-safe check, or the Tesla API's free online check), and if the car is asleep the command waits (logged once) instead of failing and retrying, so no paid Fleet API command goes to a car known asleep. While the car is known asleep nothing is run, until a sign of life (a newer awake state from any source, a plug or unplug, a drive start or end, current drawn, or a successful wake); for a car no live telemetry feed reports on, the Tesla API's free online check looks again every 15 minutes while the car is home and every 30 minutes elsewhere, and only an awake answer sends the command (an asleep one is not logged again). Commands that may wake the car still do, except while its charger is offered 0 A; once the offer rises the car is woken for the raise
 * Architecture
     * Remove Tesla Owner API login flow; FleetAPI, TeslaMate token sync, manual token entry and BLE remain the supported paths, with Owner API tokens used for reads, and for commands only to vehicles Tesla reports with `command_signing: off`
     * (@MikeBishop) - Saved Tesla tokens migrate to separate Owner and Fleet settings on first start; downgrading afterwards loses the Owner API token (#692)
     * (@MikeBishop) - Held charge limits in settings `chargeLimits` are keyed by VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them. After a downgrade, only 1.3.x's TeslaBLE path reads the VIN-keyed entries; its Tesla API path, keyed by numeric ID, starts over
     * (@MikeBishop) - TWC abstraction layer with EVSEController/EVSEInstance interface (ported from #483)
     * (@ngardiner) - Gen3 TWC support via Neurio Modbus emulation
     * (@MikeBishop) - Run vehicle commands on a dedicated worker thread and serialize tesla-control calls, so BLE retries no longer stall the RS485 loop (#668)
     * (@MikeBishop) - Shut down gracefully on SIGTERM, saving settings and sending pending stop-charging commands before exit (#668)
     * (@MikeBishop) - Serialise settings.json saves under a settings lock so a save no longer races writers on other threads
     * (@MikeBishop) - Evaluate charging policy on its own thread instead of the RS485 loop, only when acting as master (#670)
@@ -56,20 +56,22 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - A car whose drive's end was never reported (no live feed) stayed "driving" after it plugged in, so its charge limit was held until it left. A car that plugs in, is named by a TWC, or reports charging or drawing current after its last driving report is no longer driving
     * (@MikeBishop) - Under Charge Rate Control mode 2 (and mode 3 below 6 A), the TWC offers the car's share until the car's rate is confirmed, then its maximum; a rate command that keeps failing no longer leaves the TWC at its maximum while the car draws more than its share. A car no provider can set the rate for is held to its share by the TWC
     * (@MikeBishop) - A charge limit is only changed when its current value is known (from any source); TeslaBLE no longer sets a limit it could not read
     * (@MikeBishop) - A targeted start, stop or charge limit sent through Home Assistant now affects only the named car; a command for every car still reaches every Home Assistant car
     * (@MikeBishop) - A Gen2 RS-485 adapter that is missing or can't be opened no longer stops TWCManager from starting: the Gen2 link logs one error and retries every 30 seconds, so a Gen3-only or vehicle-only install needs no interface change, and a late USB adapter is picked up without a restart. The Gen2 link is not opened on the Gen3 controller's port
     * (@MikeBishop) - Presence follows events as they arrive (plug-ins, unplugs, positions, drive starts, BLE contact) and needs no paid read: a car is Home, Away or Probably home, probably-home cars are counted in `numCarsAtHome` and `minBatteryLevelAtHome`, a Home Assistant zone state of home with no coordinates no longer places a car, and a charge limit, start or rate for a car waits until it is plugged in or confirmed home. A TWC's own commands are never held back
     * (@MikeBishop) - A policy with no limit (-1) releases the car to its own limit and is applied like any limit; a departing car's original limit is restored wherever it is. A car is woken only when it is expected to charge once everything wanted is applied (plugged in or arriving, no stop wanted, its TWC or charger offered power, and its limit above its battery level; an unknown limit or battery level counts as charging), and after a start not before TeslaMate or Fleet Telemetry has reported once (or 60 seconds have passed), whatever the direction of the change; a car expected to stay idle gets changes only when it is awake anyway. Restores on departure and stops never wake
     * (@MikeBishop) - A plug-in with no VIN from a Gen2 or Gen3 TWC is matched to the one car that can be there (plugged in just now, BLE-read at that pilot and draw, or BLE-reached) and left unnamed when several could be; on a Gen2 that reads VINs, the VIN read replaces the match; the match never BLE-reads a car known asleep; a Gen2's match runs on the BLE worker, and a Gen3's vitals never read BLE. An unnamed TWC's rate now goes only to cars plugged in here, no longer to the first car; a status 00 alone no longer opens an unnamed session, and a Gen2 plug counts only while the TWC reports one. A car charging away from a TWC with no telemetry feed is not watched for its departure (a separate feature is planned); the 5, 20 and 45 minute reads after a TWC's power drops are gone
     * (@MikeBishop) - Removed the `/api/checkArrival` and `/api/checkDeparture` hint endpoints (they now return 404); presence no longer needs them
     * (@MikeBishop) - A guest car on the same TWC can keep a car that left idle counted as home until that car reports a position outside the radius or starts driving; a VIN a TWC rejected during a charge session stays rejected until the unplug
+    * (@MikeBishop) - A Fleet API wake_up that answers asleep, offline or waking is no longer a failed wake: the car connects seconds later, so TWCManager checks for it with the free online check every 5 seconds for up to 45 seconds, then sends the command at once. Only a car still not online after that waits 30 minutes for the next wake_up
+    * (@MikeBishop) - A car whose TWC (Gen2 or Gen3) measures at least 1 A since the car's last report is charging, whatever that report said: no start command and no billed start retry goes to it. Without a live feed the car's report can be stale, and a car that started by itself when its limit rose was sent a start, refused, and retried
     * Fix: Add missing module-level time import in HASS, EmonCMS, Growatt, IotaWatt, SmartMe and TCP modules, which crashed EMS polling and caused charge current oscillation (closes #644)
     * Fix: Restore minInterval parameter on update_location, fixing TypeError that broke API start/stop charging and home location correction
     * Fix: Correct invalid logging level in update_vehicle_data error handler which crashed when logging a failed API response
     * Fix: Do not seed or reset home location from a stale GPS fix; check gps_as_of age and force a fresh fetch when a TWC-connected VIN corrects home (closes #423)
     * Fix: Skip start-charge commands (API and BLE) when the car is waiting on its own Scheduled Charging/Departure timer; disable via respectVehicleSchedule (closes #493)
     * Fix: Remove post-command ping from TeslaBLE charge control; command success is sufficient proof of BLE connectivity (closes #650)
     * Fix: Treat Tesla BLE idempotent-success responses as success in parseCommandOutput (closes #649)
     * Fix: Remove cryptography<3.4 upper bound; modern versions ship binary wheels and the Rust build requirement is no longer a concern (closes #647)
     * Fix: RS485 read returns empty bytes after reconnect instead of None, preventing crash on socket disconnect (closes #461)
     * Fix: Stop flooding VIN queries when non-Tesla vehicle or CAN-disabled TWC returns all-zero VIN data (closes #296)
diff --git a/docs/Settings.md b/docs/Settings.md
index 9921cfe8..b1e59e88 100644
--- a/docs/Settings.md
+++ b/docs/Settings.md
@@ -53,21 +53,21 @@ The Charge Authorization Mode determines how we determine if a vehicle that star
    * Vehicles can charge unless explicitly blocked
 
 This setting is the default, and specifies that any vehicle which requests to start charging can do so, unless it is explicitly added to the Deny Charging group.
 
    * Vehicles can only charge if explicitly allowed
 
 This setting specifies that any vehicle which requests to start charging will be blocked, unless it has been added to the Allow Charging group.
 
 ### Vehicle Command Policy
 
-Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. The Vehicle Command Policy suppresses providers in that order:
+Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. A start is done once the TWC the car is plugged into measures at least 1 A since the car last reported, so no start or retry goes to a car already charging. The Vehicle Command Policy suppresses providers in that order:
 
    * `prefer_ble` - Prefer local (BLE), fall back to cloud after a delay. Nothing is suppressed. This is the default.
    * `ble_only` - Local only - never send billed cloud commands. Every non-local provider (the Fleet API and Home Assistant) is suppressed for commands; cloud reads still run.
    * `api_only` - Cloud only - never use BLE. TeslaBLE is suppressed for every operation, reads as well as commands.
 
 Setting `commandPolicy` under `vehicle` in config.json hard-sets the policy and disables this control.
 
 #### Who sets a car's charge rate
 
 Every Fleet API command is billed, so the Fleet API never sets a car's charge rate where a local path can: the TWC the car is plugged into, or BLE for a paired car. A car on a TWC gets its rate from the TWC. A BLE-paired car on a mobile connector (or any charger TWCManager does not control) gets its rate over BLE only; before v1.4.0 it got it from the Fleet API. If the BLE command fails, the Fleet API does not step in. To let the Fleet API carry the rate for such a car, use `api_only`. Under Charge Rate Control mode 2 (and mode 3 below 6 A), the TWC offers the car's share, not its maximum, until the car's rate is confirmed by a delivered command or a reading; a rate that cannot be delivered leaves the TWC enforcing the share.
diff --git a/docs/modules/Vehicle_TeslaAPI.md b/docs/modules/Vehicle_TeslaAPI.md
index 54bf618f..f9e20d2f 100644
--- a/docs/modules/Vehicle_TeslaAPI.md
+++ b/docs/modules/Vehicle_TeslaAPI.md
@@ -86,21 +86,21 @@ based on whether you configure a client secret:
 
 Set the following in the `config` section of `config.json`:
 
 | Key | Required | Description |
 |-----|----------|-------------|
 | `teslaApiClientID` | Yes | Client ID of your registered application |
 | `teslaApiRedirectUri` | Yes | Redirect URI, exactly matching one registered on the app (under your public domain - not TWCManager's address) |
 | `teslaApiClientSecret` | No | Only to force the client-secret exchange instead of PKCE (advanced) |
 | `teslaApiRegion` | No | Only used with `teslaApiClientSecret`: `NA` (default), `EU` or `CN` |
 | `teslaApiScope` | No | Override the requested OAuth scopes |
-| `wakeDelayMins` | No | Minutes to wait before sending a Fleet API wake command (default: 3). During the delay the car may self-start from the TWC power offer. Set to 0 to wake immediately. |
+| `wakeDelayMins` | No | Minutes to wait before sending a Fleet API wake command (default: 3). During the delay the car may self-start from the TWC power offer. Set to 0 to wake immediately. After a wake that answers asleep or offline, the free online check looks every 5 s for up to 45 s; a car still not online then waits 30 minutes for the next wake. |
 
 If you do set `teslaApiClientSecret`, keep `config.json` readable only by the
 `twcmanager` user.
 
 ## Logging in
 
 1. Open the TWCManager web UI. When no token is stored, the home page shows a Tesla
    login section.
 2. Click **Log in to Tesla** (with PKCE there is no region to choose; the client-secret
    method shows a region selector first).
diff --git a/docs/modules/Vehicle_TeslaBLE.md b/docs/modules/Vehicle_TeslaBLE.md
index 12522700..f3e85e2d 100644
--- a/docs/modules/Vehicle_TeslaBLE.md
+++ b/docs/modules/Vehicle_TeslaBLE.md
@@ -59,21 +59,21 @@ By default, TWCManager uses the TWC to control charge rate. This behaviour is co
 ## FAQs
 
 * *Why does BLE currently require API as a fallback?*
 
 TWCManager was written with an explicit dependency on the API. BLE replaces some but not all of the API's functionality. For example, we cannot discover all vehicles on an account with BLE.
 
 The approach taken is to replace the API calls where an appropriate BLE replacement exists. This has the benefit of using API only as a fallback when BLE fails, which improves reliability.
 
 * *Why does TWCManager sometimes not send a command to a sleeping car?*
 
-Lowering a charge limit never wakes the car. Before a BLE command that may not wake the car, TWCManager runs a sleep-safe check (the car's answer says whether it is asleep); before such a Tesla API command, the free online check. If the car is asleep, the command waits, and this is logged once. While the car is known to be asleep, TWCManager runs nothing at all, so it does not retry every few minutes. The one exception is the Tesla API's free online check for a car no live telemetry feed reports on: it looks again every 15 minutes while the car is home, and every 30 minutes elsewhere.
+Lowering a charge limit never wakes the car. Before a BLE command that may not wake the car, TWCManager runs a sleep-safe check (the car's answer says whether it is asleep); before such a Tesla API command, the free online check. If the car is asleep, the command waits, and this is logged once. While the car is known to be asleep, TWCManager runs nothing at all, so it does not retry every few minutes. The one exception is the Tesla API's free online check for a car no live telemetry feed reports on: it looks again every 15 minutes while the car is home, and every 30 minutes elsewhere. An asleep answer changes nothing and is not logged again; an awake one sends the command.
 
 The car counts as awake again on a sign of life: a newer awake state from any source, a plug or unplug, a drive start or end, current drawn, or a successful wake. The waiting command is then tried again. Commands that may wake the car still wake it, except while the car's charger is offered 0 A; once the offer rises, the car is woken for the raise.
 
 * *What are the BLE-specific considerations that need to be taken into account?*
 
 BLE being a local wireless technology introduces a number of considerations. The distance between the TWC and the vehicle is important to consider, as weak signals can contribute to instability. If distance is a challenge, there are potential solutions such as an ESP-based tesla-control interface, however support for this does not exist yet.
 
 * *I tried to use the ```teslaControlPath``` setting to call a script which then goes on to call tesla-control. After a period of time, TWCManager background tasks seem to get stuck. Why?
 
 The tesla-control CLI interface has a number of failure cases in which it will hang indefinitely. We work around this by terminating the process after 15 seconds of inactivity (the `commandTimeout` setting), however this does not kill the entire process tree. If you are running the command through some sort of wrapper, it will become zombified whilst the tesla-control command will remain.
diff --git a/lib/TWCManager/Control/HTTPControl.py b/lib/TWCManager/Control/HTTPControl.py
index fa1a798e..a621b222 100644
--- a/lib/TWCManager/Control/HTTPControl.py
+++ b/lib/TWCManager/Control/HTTPControl.py
@@ -103,21 +103,21 @@ def pendingCommands(master, vehicle):
         rec = state.records.get(aspect)
         if rec is None:
             continue
         sent, last = rec.inFlight, rec.lastOutcome
         why = master.reconciler.said(vehicle.key, aspect)
         if sent:
             why = "sending via %s, started %s" % (
                 sourceName(sent.provider),
                 ageText(now - sent.since),
             )
-        elif satisfied(aspect, d.value, known(vehicle, aspect)) or (
+        elif satisfied(aspect, d.value, known(vehicle, aspect, d.value)) or (
             # Settled, the reconciler waits for a reading saying otherwise
             rec.settledAt is not None
             and not newerReading(vehicle, aspect, rec.settledAt)
         ):
             continue
         elif last and not why:
             why = "%s via %s, %s" % (
                 last.detail.replace(RULES, "") or last.kind,
                 sourceName(rec.lastProvider),
                 ageText(now - rec.lastOutcomeAt),
diff --git a/lib/TWCManager/Vehicle/Reconcile/Belief.py b/lib/TWCManager/Vehicle/Reconcile/Belief.py
index 3d9f007f..59daa6bb 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Belief.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Belief.py
@@ -42,28 +42,33 @@ def uncompleted(vehicle, obs):
     # "Complete" read before our last limit write above the battery level
     # is no longer true: the car can charge again
     write = vehicle.lastWrite(FIELD_FOR[CHARGE_LIMIT])
     soc = vehicle.latest("batteryLevel")
     if obs is None or obs.value != "Complete" or write is None or soc is None:
         return obs
     raised = obs.at <= write.at and soc.value < write.value
     return obs._replace(value="Stopped") if raised else obs
 
 
-def known(vehicle, aspect):
+def known(vehicle, aspect, desired=None):
     obs = vehicle.believed(FIELD_FOR[aspect], exclude=VEHICLE_SOURCES_EXCLUDED)
-    if aspect == CHARGING:
-        obs = uncompleted(vehicle, obs)
-    if obs is None and aspect == CHARGING:
+    if aspect != CHARGING:
+        return obs
+    obs, twc = uncompleted(vehicle, obs), _standIn(vehicle)
+    if obs is None:
         # A car no vehicle source describes (anonymous, non-Tesla): the TWC
         # current stands in. It never adopts
-        return _standIn(vehicle)
+        return twc
+    if desired is True and twc and twc.value == "Charging" and twc.at > obs.at:
+        # For a start, current at the car's TWC since its last reading is
+        # the car charging: without a live feed that reading may be stale
+        return twc
     return obs
 
 
 def newerReading(vehicle, aspect, since) -> bool:
     field = FIELD_FOR[aspect]
     if aspect == CHARGING and vehicle.believed(field, VEHICLE_SOURCES_EXCLUDED) is None:
         # Only while known uses the stand-in: for a car a vehicle source
         # describes, the heartbeat's readings are never evidence
         obs = _standIn(vehicle)
         return obs is not None and obs.at > since
diff --git a/lib/TWCManager/Vehicle/Reconcile/Desired.py b/lib/TWCManager/Vehicle/Reconcile/Desired.py
index 636faaeb..4827ae95 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Desired.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Desired.py
@@ -86,20 +86,21 @@ class AttemptRecord:
         paidReached=False,  # one of them got an answer other than UNREACHABLE
         paidAt=None,
         paidSaw=None,
         paidRetryDue=False,  # that request failed and its one blind retry is unused
         rearmed=False,  # the desire's one re-arm of its paid sends is used
         # The provider whose wake the car did not answer on the last paid
         # send: the command never went (Reconciler's WAKE_CHECK)
         wakeCheckBy=None,
         settledAt=None,
         heldAt=None,  # a hold: when, and the paid requests attempts that held made
+        checkedAt=0,  # a cloud hold's last free online check
         paidSpent=0,
         unread=0,  # sends that found the current value unreadable (a limit's backstop)
         clearedValue=None,  # the value a clearIf withdrew; set() may take the record back
     )
 
     def __init__(self):
         # What spans desires: the send gap and the attempt in flight
         self.inFlight: Optional[Attempt] = None
         self.lastProvider: str = ""
         # Provider -> the EXCLUDING kind that excluded it
diff --git a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
index f9e0e2b9..8f2f5362 100644
--- a/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
+++ b/lib/TWCManager/Vehicle/Reconcile/Reconciler.py
@@ -114,22 +114,22 @@ class VehicleReconciler(threading.Thread):
         return all([q.waitDrained(deadline) for q in (self.cloud, self.ble)])
 
     def submit(self, attempt) -> bool:
         worker = Run.workerOf(self.master.providerOrder.provider(attempt.provider))
         if worker == "local":
             # No I/O: only a request the heartbeat sends
             self.report(attempt, self._run(attempt))
             return True
         return (self.ble if worker == "ble" else self.cloud).put(attempt)
 
-    def submitJob(self, key, kind, run) -> bool:
-        return self.ble.put(Run.Job(key, kind, run))
+    def submitJob(self, key, kind, run, worker="ble") -> bool:
+        return getattr(self, worker).put(Run.Job(key, kind, run))
 
     def cancel(self, key) -> int:
         # Pending stops for key only; a running attempt is left alone
         return sum(
             q.remove(lambda a: a.key == key and Run.isStop(a))
             for q in (self.ble, self.cloud)
         )
 
     def _run(self, attempt) -> O.Outcome:
         if isinstance(attempt, Run.Job):
@@ -220,26 +220,33 @@ class VehicleReconciler(threading.Thread):
 
     def plan(self, vehicle, aspect, now) -> Optional[Attempt]:
         key = vehicle.key
         d = self.desired.get(key, aspect)
         rec = self.desired.record(key, aspect)
         if d is None or rec.inFlight is not None:
             return None
         # A drive's hold can change only once the car stops
         driving = rec.lastOutcome == (O.SATISFIED, O.HELD + "driving")
         driving = driving and Presence.decide(self.master, vehicle)[1] == "driving"
-        recheck = self._asleepCheckDue(vehicle, rec, now)
-        waiting = rec.heldAt is not None and not recheck
+        if self._asleepCheckDue(vehicle, rec, now):
+            # The free online check alone: its answer is an observation, so
+            # an awake car is a sign of life that plans this again, and an
+            # asleep one is no news
+            p = self.master.providerOrder.provider(rec.lastProvider)
+            rec.checkedAt = now
+            self.submitJob(key, "onlineCheck", lambda: p.online(vehicle), "cloud")
+            return None
+        waiting = rec.heldAt is not None
         if waiting and (vehicle.lastObservedAt <= rec.heldAt or driving):
             # Held: only newer evidence (or a new desire) plans it again
             return None
-        k = B.known(vehicle, aspect)
+        k = B.known(vehicle, aspect, d.value)
         if d.lift and (rec.settledAt is not None or R.satisfied(AMPS, d.value, k)):
             # A lift is a one-shot desire: done once it settles
             self.desired.clearIf(key, AMPS, d.value)
             return None
         if now - rec.lastSentAt < MIN_SEND_GAP[aspect]:
             return None
         last = rec.lastOutcome
         if (
             last is not None
             and rec.heldAt is None
@@ -317,23 +324,23 @@ class VehicleReconciler(threading.Thread):
         )
         # At most two paid sends per arm, and two arms per desire: one send,
         # then one more after a failure or a reading that reached the car
         # A start goes with the limit first: its wake carries the limit
         ride = aspect == CHARGE_LIMIT and self._startWanted(vehicle, config)
         field = FIELD_FOR[aspect]
         # Only a car expected to charge is woken; a restore or stop never is
         quiet = B.whyQuiet(self.master, vehicle)
         wakes = quiet is None and not d.restore and d.value is not False
         asleep = Presence.asleep(vehicle, rec.heldAt or 0) is not False
-        if not (wakes or recheck) and last == O.ASLEEP and asleep:
-            # Asleep (or offline): only a sign of life since the hold, a
-            # message that may wake, or the cloud's next check
+        if not wakes and last == O.ASLEEP and asleep:
+            # Asleep (or offline): only a sign of life since the hold (the
+            # cloud's next check may find one), or a message that may wake
             return None
         reached = rec.paidSends and B.reachedCar(
             vehicle, field, rec.paidAt, rec.paidSaw
         )
         if (
             rec.paidSends
             and not rec.paidReached
             and not rec.rearmed
             and now - rec.paidAt >= RETRY[aspect]
             and (
@@ -425,21 +432,21 @@ class VehicleReconciler(threading.Thread):
     @staticmethod
     def _whyNoWake(d, p, quiet, blind) -> str:
         if blind:
             return "blind paid retry"
         if d.restore or d.value is False:
             return "restore or stop never wakes"
         return quiet or "billed provider never wakes for amps"
 
     def _startWanted(self, vehicle, config) -> bool:
         start = self.desired.get(vehicle.key, CHARGING)
-        k = B.known(vehicle, CHARGING)
+        k = B.known(vehicle, CHARGING, True)
         return (
             start is not None
             and start.value is True
             and not R.satisfied(CHARGING, True, k)
             and B.handsOff(vehicle, CHARGING, True, k, config) is None
             # A start that would itself spend a cloud wake (not mode 2's)
             and any(
                 not p.local and p.declares(C.WAKE)
                 for p in self.master.providerOrder.candidates(vehicle, C.START_CHARGING)
             )
@@ -476,21 +483,21 @@ class VehicleReconciler(threading.Thread):
         )
 
     def _asleepCheckDue(self, vehicle, rec, now) -> bool:
         # A cloud hold's free online check runs again on the asleep cadence,
         # unless a live feed will report the car waking
         p = self.master.providerOrder.provider(rec.lastProvider)
         if rec.lastOutcome != O.ASLEEP or getattr(p, "local", True):
             return False
         home = Presence.presence(self.master, vehicle) == Presence.HOME
         gap = Presence.HOME_ASLEEP_SECS if home else Presence.AWAY_ASLEEP_SECS
-        due = now - rec.lastOutcomeAt >= gap
+        due = now - max(rec.lastOutcomeAt, rec.checkedAt) >= gap
         return due and not Presence.covered(self.master, vehicle)
 
     def _held(self, vehicle):
         return self.master.heldLimits.get(vehicle.vin) if vehicle.vin else None
 
     def _save(self, vehicle, outside, held) -> None:
         # HeldLimits.set rounds floats (80.0 from Home Assistant)
         if vehicle.vin:
             self.master.heldLimits.set(vehicle.vin, outside=outside, held=held)
 
diff --git a/lib/TWCManager/Vehicle/TeslaAPI.py b/lib/TWCManager/Vehicle/TeslaAPI.py
index a5598a08..311d0e5e 100644
--- a/lib/TWCManager/Vehicle/TeslaAPI.py
+++ b/lib/TWCManager/Vehicle/TeslaAPI.py
@@ -86,20 +86,24 @@ class TeslaAPI:
         "is_charging",
         "not_charging",
         "complete",
         "disconnected",
         "requested",
     )
     # A command refused for one of these reasons did not reach the car
     COMMAND_UNREACHABLE_REASONS = ("could_not_wake_buses", "vehicle_unavailable")
     # Seconds between failed wake_up attempts on one car (a wake is $0.02)
     WAKE_RETRY_SECONDS = 30 * 60
+    # After a wake_up that answered asleep/offline/waking, the free online
+    # check every WAKE_POLL_SECONDS, WAKE_POLLS times, before it has failed
+    WAKE_POLL_SECONDS = 5
+    WAKE_POLLS = 9
     regionURL = {
         "NA": "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
         "EU": "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles",
         "CN": "https://fleet-api.prd.cn.vn.cloud.tesla.cn/api/1/vehicles",
         # Not a Fleet region: the Owner API used by TeslaMate tokens. It reads,
         # and commands only a car that takes unsigned commands.
         # fleetRegions() leaves it out of every region list and lookup.
         "OwnerAPI": "https://owner-api.teslamotors.com/api/1/vehicles",
     }
     # teslaProxy base URL and certificate from config.json, used for Fleet
@@ -1556,20 +1560,28 @@ class TeslaAPI:
             O.Outcome(O.UNREACHABLE, "wake refused"),
             _SIGNING_REQUIRED,
             _OWNER_RETIRED,
         ):
             return outcome
         state = "error"
         if outcome is None:
             state = response.get("state", "")
             if not isinstance(state, str):
                 state = "error"
+        if state in ("asleep", "waking", "offline"):
+            # wake_up answers the state at that moment; the car connects
+            # seconds later. Blocking ~45 s is fine: this is the cloud worker
+            for _ in range(self.WAKE_POLLS):
+                time.sleep(self.WAKE_POLL_SECONDS)
+                if self.onlineState(vehicle, slot=checkSlot, maxAge=0):
+                    state = "online"
+                    break
         if state == "online":
             self.resetCarApiLastErrorTime()
             self._wakeSettled(car)
             # The wake's answer replaces the cached "asleep": the read that
             # follows it goes out
             car.online, car.onlineCheckedAt = True, now
             # A command sent at once after a wake can fail with
             # could_not_wake_buses; let the car settle
             time.sleep(5)
             return O.Outcome(O.DONE)
@@ -1692,42 +1704,45 @@ class TeslaAPI:
         if self.is_awake(vehicle):
             car.firstWakeAttemptTime = 0
             return True
 
         logger.log(
             logging.INFO8,
             vehicle.name + " not ready because it wasn't woken in the last 2 minutes.",
         )
         return False
 
-    def onlineState(self, vehicle, slot=None, now=None) -> Optional[bool]:
+    def onlineState(self, vehicle, slot=None, now=None, maxAge=120) -> Optional[bool]:
         # True or False when an answer (a sync source or the free
         # vehicles/{vin}) says so; None when nothing answered. Free sources
         # only, never vehicle_data. The newest observation wins: telemetry
         # (any state) is trusted only while fresh and newer than our own last
         # state GET; otherwise use that GET's cached result or GET again.
         # Fresh is the registry's age, so a live feed keeps an old reading
         # fresh; it still loses to a state GET made after it. now (default:
-        # the module's clock) measures the 120 s cache, so a caller on a
-        # test clock drives it
+        # the module's clock) measures the maxAge-second cache, so a caller
+        # on a test clock drives it
         car = vehicle.attachment("TeslaAPI")
         now = self.now() if now is None else now
         obs, age = vehicle.telemetryState()
         if (
             age is not None
             and age <= vehicle.SYNC_TIMEOUT / 4
             and obs.at >= max(car.onlineCheckedAt, car.staleBefore)
         ):
             return obs.value in ("online", "charging", "updating", "driving")
 
         # Don't check more often than every 2 minutes
-        if now - car.onlineCheckedAt < 120 and car.onlineCheckedAt >= car.staleBefore:
+        if (
+            now - car.onlineCheckedAt < maxAge
+            and car.onlineCheckedAt >= car.staleBefore
+        ):
             return car.online
         result, response = self.get_car_api(
             vehicle, vehicle.vin, checkReady=False, slot=slot
         )
         car.online = response.get("state", "") == "online" if result else None
         car.onlineCheckedAt = now
         if result:
             source = self.sourceOf(slot or self.slotFor("read"))
             vehicle.observe("state", response.get("state"), source)
         return car.online
diff --git a/tests/unit/reconcile_helpers.py b/tests/unit/reconcile_helpers.py
index 2c6cfaee..8762c1e5 100644
--- a/tests/unit/reconcile_helpers.py
+++ b/tests/unit/reconcile_helpers.py
@@ -152,29 +152,29 @@ def make_order(settings=None, *providers):
     # No reconciler until a test makes one: a plain Mock would take the debug
     # page's one-shots
     del m.reconciler
     o = m.vehicleRegistry.providerOrder = ProviderOrder(m)
     for p in providers:
         o.register(p)
     return m, o
 
 
 class InlineQueue(VehicleCommandQueue):
-    # Test-only: runs each attempt and plug check at once on the caller's
-    # thread, reporting it as a started queue would. Closed, it takes stops
-    # only. Another job waits until the test runs it (runPending), as a busy
-    # worker would leave it
+    # Test-only: runs each attempt, plug check and online check at once on
+    # the caller's thread, reporting it as a started queue would. Closed, it
+    # takes stops only. Another job waits until the test runs it
+    # (runPending), as a busy worker would leave it
     def start(self):
         pass
 
     def put(self, entry) -> bool:
-        if isinstance(entry, Job) and entry.kind != "plugCheck":
+        if isinstance(entry, Job) and entry.kind not in ("plugCheck", "onlineCheck"):
             return super().put(entry)
         if self._draining and not self._isHigh(entry):
             self._lose([(entry, "dropped")])
             return False
         with self._cond:
             self._busy = True
         self._runOne(entry)
         return True
 
     def waitDrained(self, deadline) -> bool:
diff --git a/tests/unit/test_command_path_parity.py b/tests/unit/test_command_path_parity.py
index bbfb2484..c2e732b4 100644
--- a/tests/unit/test_command_path_parity.py
+++ b/tests/unit/test_command_path_parity.py
@@ -345,20 +345,50 @@ def test_fleet_only_car_online_after_an_offline_wake_gets_the_limit(requests_moc
     v.observe("chargeLimit", 50, "OwnerAPI", at=c() - 600)
     m.setPolicyLimit(80, transition=True)
     car, seen = offlineWake(requests_mock, m, r, c, lambda: None, seconds=3600)
     assert seen["sent"] - seen["online"] <= 150  # the free check noticed it
     assert paid(requests_mock) == (1, 1, 1)  # one wake in the hour: none again
     assert commands(requests_mock) == ["set_charge_limit"]
     assert car.charge["charge_limit_soc"] == 80 and dollars(requests_mock) == 0.023
     assert m.desired.record(VIN, CHARGE_LIMIT).paidSends == 2  # the wake, the send
 
 
+def test_fleet_only_car_online_seconds_after_an_offline_wake_gets_the_limit(
+    requests_mock, monkeypatch
+):
+    # wake_up answers offline and the car connects seconds later: the polls
+    # after the wake find it, and the limit goes out in the same pass
+    import TWCManager.Vehicle.TeslaAPI as teslaapi
+
+    m, r, v, c, api = install(fleet=True, held=(90, 50))
+    v.observe("chargeLimit", 50, "OwnerAPI", at=c() - 600)
+    m.setPolicyLimit(80, transition=True)
+    car = FleetCar(requests_mock, limit=50)
+    requests_mock.post(
+        FLEET + VIN + "/wake_up", json={"response": {"state": "offline"}}
+    )
+    sleeps = []
+
+    def sleep(secs):
+        sleeps.append(secs)
+        if len(sleeps) == 2:
+            car.state = "online"
+
+    monkeypatch.setattr(teslaapi.time, "sleep", sleep)
+    r.pass_()
+    assert wakeUps(requests_mock) == 1
+    assert commands(requests_mock) == ["set_charge_limit"]
+    passes(r, c, 3600)
+    assert paid(requests_mock) == (0, 1, 1)  # one wake, no second
+    assert car.charge["charge_limit_soc"] == 80
+
+
 def wakeTimes(requests_mock, c, also=lambda: None):
     # A want() for offlineWake that records when each wake_up went out
     times = []
 
     def want():
         also()
         times.extend([c()] * (wakeUps(requests_mock) - len(times)))
 
     return times, want
 
@@ -424,22 +454,23 @@ def test_fleet_only_car_never_online_after_an_offline_wake(requests_mock, start,
         ("batteryLevel", 40),
     ):
         v.observe(field, value, "OwnerAPI", at=c() - 600)
     m.setPolicyLimit(80, transition=True)
     also = (lambda: m.startCarsCharging(VIN)) if start else (lambda: None)
     times, want = wakeTimes(requests_mock, c, also)
     offlineWake(requests_mock, m, r, c, want, seconds=4 * 3600, online=10**9)
     assert paid(requests_mock) == (0, wakes, 0) and counts(requests_mock)["other"] == 0
     assert all(b - a > 1800 for a, b in zip(times, times[1:]))
     # Only free checks between: one per WAKE_CHECK while a follow-up is due
-    # (47 and 94 measured)
-    assert counts(requests_mock)["free"] <= (50 if not start else 100)
+    # (47 and 94 measured), and the polls after each wake
+    free = counts(requests_mock)["free"]
+    assert free <= (50 if not start else 100) + wakes * api.WAKE_POLLS
 
 
 def test_every_billed_wake_holds_the_next(requests_mock):
     # Provider.wake's contract, which the reconciler's WAKE_CHECK follow-ups
     # rely on: a failed wake by any billed provider that can wake the car
     # makes the next one, inside WAKE_CHECK, a free "wake held", no wake_up
     from TWCManager.Vehicle.Reconcile.Reconciler import WAKE_CHECK
 
     m, r, v, c, api = install(fleet=True, owner=True, signing="off")
     wakers = [
@@ -1083,20 +1114,52 @@ def test_telemetry_rearm_on_a_start_is_once_per_desire(requests_mock):  # Task 1
             v.observe("chargingState", "Stopped", "FleetTelemetryMQTT"),
             m.startCarsCharging(VIN),
         ),
     )
     assert (
         paid(requests_mock) == (0, 0, 3)
         and commands(requests_mock) == ["charge_start"] * 3
     )  # within the cap of 4
 
 
+@pytest.mark.parametrize("drawing", [True, False])
+def test_fleet_only_start_no_retry_while_the_twc_draws(requests_mock, drawing):
+    # Fleet-only, no feed: the car's last chargingState is a stale read. The
+    # start is not accepted (the car started itself when its limit rose),
+    # and the car's TWC then measures 48 A: that is the car charging, so no
+    # retry goes out. Without current the retry goes as before
+    m, r, v, c, api = install(fleet=True)
+    FleetCar(requests_mock, state="online", script=[(200, False, "")])
+    for field, value in (
+        ("chargingState", "Stopped"),
+        ("chargeLimit", 80),
+        ("batteryLevel", 40),
+    ):
+        v.observe(field, value, "FleetAPI", at=c() - 600)
+
+    def each():
+        m.startCarsCharging(VIN)
+        if drawing and commands(requests_mock):
+            v.observe("actualCurrent", 48, "Gen2TWC", seen=False)
+
+    m.startCarsCharging(VIN)
+    passes(r, c, 3600, step=5, each=each)
+    starts = commands(requests_mock).count("charge_start")
+    assert starts == (1 if drawing else 2) and paid(requests_mock) == (1, 0, starts)
+    # A stop still sees the car's own reading
+    from TWCManager.Vehicle.Reconcile import Belief
+
+    assert Belief.known(v, CHARGING).value == "Stopped"
+    want = "Charging" if drawing else "Stopped"
+    assert Belief.known(v, CHARGING, True).value == want
+
+
 # Row 21 (slim Task 12b M3): chargeRateControl 2, a rate Fleet cannot deliver
 
 
 def test_mode_2_undeliverable_rate_pays_twice(requests_mock):
     m, r, v, c, pt, s = fleetPoint(requests_mock, 2, script=[(500, None, None)])
     pt.setTargetPower(10 * 240)
     passes(r, c, 3600, each=lambda: pt.setTargetPower(10 * 240))
     assert (
         amps(requests_mock) == [10, 10] and s.pointAmps == 10
     )  # one send, one blind retry; the TWC keeps the target (final review I1)
diff --git a/tests/unit/test_sleeping_car.py b/tests/unit/test_sleeping_car.py
index d4afc153..bf1663c5 100644
--- a/tests/unit/test_sleeping_car.py
+++ b/tests/unit/test_sleeping_car.py
@@ -392,10 +392,36 @@ def test_the_fleet_feed_compares_with_its_own_state_not_a_sleep_check():
     assert v.reported("state")["FleetTelemetryMQTT"].value == "online"
     assert v.telemetryState()[0].source == "FleetTelemetryMQTT"
 
 
 def test_a_newer_offline_is_not_a_sign_of_life():
     m, r, v, c = setup(here=False)
     v.observe("state", "asleep", "TeslaBLE")
     c.t += 1
     v.observe("state", "offline", "FleetTelemetryMQTT")
     assert Presence.asleep(v)
+
+
+def test_a_fleet_restore_held_asleep_logs_once_and_rechecks_without_replanning(
+    requests_mock, caplog
+):
+    # Fleet-only, no feed: the restore finds the car asleep and holds. Each
+    # free recheck that finds it still asleep neither plans the restore again
+    # nor logs the hold again; the car next seen online gets the limit once
+    caplog.set_level(logging.INFO)
+    m, r, v, c, api = install(fleet=True, held=(90, 50))
+    car = FleetCar(requests_mock, state="asleep", limit=50)
+    v.observe("chargeLimit", 50, "FleetAPI", at=c() - 600)
+    v.observe("batteryLevel", 95, "FleetAPI", at=c() - 600)  # it won't charge
+    m.setPolicyLimit(-1, transition=True)
+    idle = lambda: v.observe("actualCurrent", 0, "Gen2TWC", seen=False)  # noqa: E731
+    passes(r, c, 4 * 3600, step=60, each=idle)
+    rec = m.desired.record(VIN, CHARGE_LIMIT)
+    assert rec.lastOutcome == O.ASLEEP and paid(requests_mock) == (0, 0, 0)
+    attempts = [r for r in caplog.records if "setChargeLimit for" in r.getMessage()]
+    assert len(helds(caplog)) == 1 and len(attempts) == 1
+    # The free check still looks, at home every 15 minutes
+    assert 4 * 3600 // 900 <= onlineChecks(requests_mock) <= 4 * 3600 // 900 + 2
+    car.state = "online"
+    passes(r, c, 900, step=60, each=idle)
+    assert commands(requests_mock) == ["set_charge_limit"]
+    assert car.charge["charge_limit_soc"] == 90
diff --git a/tests/unit/test_teslaapi_wake.py b/tests/unit/test_teslaapi_wake.py
index 585c27b1..08cfb2bb 100644
--- a/tests/unit/test_teslaapi_wake.py
+++ b/tests/unit/test_teslaapi_wake.py
@@ -223,23 +223,24 @@ def test_state_check_with_both_tokens_is_a_state_get(clock, requests_mock):
     a = _api(clock, fleet_token(), owner_token())
     p = a.providers()[1]
     p.clock = clock
     requests_mock.get(OWNER_API_URL + "/" + VIN, json={"response": {"state": "asleep"}})
     requests_mock.get(STATE_URL, json={"response": {"state": "asleep"}})
     requests_mock.post(WAKE_URL, json={"response": {"state": "offline"}})
     _send_first_wake(a, p, clock)
     clock.advance(120)
     assert p.wake(VIN) == HELD
 
-    # Only the free state GET (on either account), never vehicle_data.
+    # Only the free state GET (on either account), never vehicle_data: two
+    # checks, and the polls after the wake
     gets = [r for r in requests_mock.request_history if r.method == "GET"]
-    assert len(gets) == 3
+    assert len(gets) == 3 + a.WAKE_POLLS
     assert all(r.url in (STATE_URL, OWNER_API_URL + "/" + VIN) for r in gets)
 
 
 def test_telemetry_from_before_wake_is_not_trusted(
     api, fleet, clock, car_state, requests_mock
 ):
     woke = _send_first_wake(api, fleet, clock)
     car = _car(api)
     # TeslaMate's last word is 'asleep', from before the wake we sent: it
     # can't tell us whether the wake worked.
@@ -303,10 +304,64 @@ def test_our_get_newer_than_telemetry_wins(api, clock, car_state, requests_mock)
 
 def test_stale_telemetry_asleep_falls_through_to_get(
     api, clock, car_state, requests_mock
 ):
     # An hour-old 'asleep' with no GET of our own yet: telemetry is stale,
     # so check the car (free state GET) instead of trusting it.
     _teslamate(api, "asleep", clock.now - 3600)
     car_state.value = "online"
     assert _awake(api) is True
     assert _gets(requests_mock) == 1
+
+
+def _poll_sleeps(monkeypatch, clock, car_state, online_after=None):
+    # time.sleep advances the test clock; the car connects during the
+    # online_after-th sleep. Returns the list of sleeps taken
+    import TWCManager.Vehicle.TeslaAPI as teslaapi
+
+    sleeps = []
+
+    def sleep(secs):
+        sleeps.append(secs)
+        clock.advance(secs)
+        if online_after is not None and len(sleeps) >= online_after:
+            car_state.value = "online"
+
+    monkeypatch.setattr(teslaapi.time, "sleep", sleep)
+    return sleeps
+
+
+def test_offline_wake_answer_then_online_is_done(
+    api, fleet, clock, car_state, requests_mock, monkeypatch
+):
+    # wake_up answers the state at that moment ('offline'); the car connects
+    # seconds later, and the free check after it finds the car online
+    assert fleet.wake(VIN) == HELD
+    clock.advance(api.wakeDelayMins * 60)
+    gets = _gets(requests_mock)
+    _poll_sleeps(monkeypatch, clock, car_state, online_after=2)
+    assert fleet.wake(VIN) == O.Outcome(O.DONE)
+    assert _wakes(requests_mock) == 1
+    assert _gets(requests_mock) - gets == 1 + 2  # the pre-wake check, two polls
+    car = _car(api)
+    assert car.delayNextWakeAttempt == 0 and car.firstWakeAttemptTime == 0
+    assert car.online is True
+    assert _no_vehicle_data(requests_mock)
+
+
+def test_wake_that_never_comes_online_fails_after_bounded_polls(
+    api, fleet, clock, car_state, requests_mock, monkeypatch
+):
+    assert fleet.wake(VIN) == HELD
+    clock.advance(api.wakeDelayMins * 60)
+    gets = _gets(requests_mock)
+    sleeps = _poll_sleeps(monkeypatch, clock, car_state)
+    assert fleet.wake(VIN) == O.Outcome(O.UNREACHABLE, "offline")
+    assert _wakes(requests_mock) == 1
+    polls = _gets(requests_mock) - gets - 1
+    assert polls == len(sleeps) and 0 < sum(sleeps) <= 60
+    assert _car(api).delayNextWakeAttempt == 30 * 60
+    # The back-off holds the next wake_up
+    clock.advance(60)
+    assert fleet.wake(VIN) == HELD
+    assert _wakes(requests_mock) == 1
+    assert _no_vehicle_data(requests_mock)
