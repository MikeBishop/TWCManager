826ca9e0 Note the 1.4.1 docs refresh in the changelog
b5edf710 Document Gen3-only, car-only and Bluetooth installs
55fe3d34 Correct the docs where the code has moved on
d03a409c Lead the READMEs with what each charger, car path and EMS adds
 CHANGELOG.md                          |  3 +-
 README.md                             | 69 +++++++++++++++++++-------
 docs/Features.md                      | 16 ++++--
 docs/Gen3_Status.md                   |  2 +-
 docs/InstallationGuide.md             |  2 +
 docs/PolicyCustomization.md           |  9 ++--
 docs/README.md                        | 93 ++++++++++++++++++++++++++++-------
 docs/Settings.md                      | 22 ++++-----
 docs/Software_Docker.md               | 16 +++++-
 docs/Software_Manual.md               | 14 ++++--
 docs/Troubleshooting.md               | 10 +++-
 docs/config_examples.md               |  2 +-
 docs/modules/Control_HTTP.md          | 15 ++++--
 docs/modules/Controller_Gen3TWCs.md   |  9 ++--
 docs/modules/Interface_RS485.md       | 10 ++--
 docs/modules/Vehicle_HomeAssistant.md |  6 ++-
 docs/modules/Vehicle_TeslaAPI.md      | 15 ++++++
 docs/modules/Vehicle_TeslaBLE.md      | 12 ++---
 docs/modules/Vehicle_TeslaMate.md     | 33 ++++++++++---
 etc/twcmanager/config.json            |  5 +-
 20 files changed, 264 insertions(+), 99 deletions(-)
diff --git a/CHANGELOG.md b/CHANGELOG.md
index dd40b0b5..416f4b98 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -17,13 +17,13 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - With a Fleet API token, TWCManager reads each car's Fleet Telemetry config (free, never wakes the car) a few minutes after start and daily, and warns once, in the log and on the car's page, when the car has no config, has not applied it, or lacks a needed field. Every car on the Fleet account is checked, so a car you do not stream warns too
     * (@MikeBishop) - INFO log lines for each reconciler outcome, each paid Fleet API request (endpoint and price, never the URL, VIN or token), and each telemetry change of plug state, drive state or geofence
     * (@MikeBishop) - A sleeping car is left alone: before a command that may not wake it, TWCManager checks the car without waking it (BLE's sleep-safe check, or the Tesla API's free online check), and if the car is asleep the command waits (logged once) instead of failing and retrying, so no paid Fleet API command goes to a car known asleep. While the car is known asleep nothing is run, until a sign of life (a newer awake state from any source, a plug or unplug, a drive start or end, current drawn, or a successful wake); for a car no live telemetry feed reports on, the vehicle watch's status check for a car only the Tesla API can see (otherwise the Tesla API's free online check, made only while the command is held) looks again every 15 minutes while the car is home and every 30 minutes elsewhere, and only an awake answer sends the command (an asleep one is not logged again). Commands that may wake the car still do, except while its charger is offered 0 A; once the offer rises the car is woken for the raise
     * (@MikeBishop) - The vehicle watch keeps cars that no TWC names and no live telemetry feed covers current, without waking them: a free sleep-state check on a clock (home asleep 15 min, home awake or charging 4 min, away asleep 30 min, away awake 5 min), a charge read only on a change (arrival, wake, plug-in, charge-port door opening) and, while a car charges at home, every 5 minutes over BLE or the Owner API, or every 15 minutes on the Fleet API while a policy reads its battery level (TWC-named cars too), and a Bluetooth scan after two missed checks and for a car that has been lost. A car only the Tesla API can see is also read while it stays awake, once its position is 20 minutes old, so it is seen leaving and arriving; the same holds for every car with a Tesla API connection while the Bluetooth radio itself is down (no controller, powered off or blocked, `bluetoothd` silent); otherwise, with the TeslaBLE module loaded, the cloud's status check is asked only by a command held for a sleeping car. An away car is left alone until it could be back (straight line to home at 120 km/h). Cloud reads draw from a budget, `watch.monthlyBudgetUSD` ($3 by default, saved across restarts); a step in the house's consumption that nothing known explains reads the candidate cars at once (a rise at most once per car per `sleepCourtesySecs`, so a cycling load never keeps a car awake). A power start now reads cars at home only. The `watch` settings, cadences and the Vehicles page's per-car watch line are described in Settings.md
     * (@MikeBishop) - BLE's sleep-safe check needs no pairing and, while the car is awake, reports whether the charge-port door is open: a closed door counts as unplugged, an open one on an awake car at home is confirmed by a charge read
 * Architecture
-    * (@MikeBishop) - The watch sets when cars are read, in place of the Tesla API deferral ladder (300/1800/3600 s of paid `vehicle_data`) and the half-hourly battery refresh of cars at home, both removed; a read stays fresh for 5 minutes for every caller. `cloudUpdateInterval` no longer sets how often cars are read (the Powerwall module uses it as its cloud cache time). The Docker compose file adds `CAP_SYS_PTRACE` so `nsenter` can open the host's network namespace
+    * (@MikeBishop) - The watch sets when cars are read, in place of the Tesla API deferral ladder (300/1800/3600 s of paid `vehicle_data`) and the half-hourly battery refresh of cars at home, both removed; a read stays fresh for 5 minutes for every caller. `cloudUpdateInterval` no longer sets how often cars are read (the Powerwall module uses it as its cloud cache time)
     * (@MikeBishop) - Serialise settings.json saves under a settings lock so a save no longer races writers on other threads
     * (@MikeBishop) - One vehicle registry keyed by VIN holds every per-vehicle field with its source and age; reads cascade BLE then cloud and never wake a car unless asked; a TWC-reported VIN is confirmed by a second query before a vehicle is created; vehicles unseen for 30 days (config vehicle.forgetAfterDays) are forgotten
     * (@MikeBishop) - The debug API `/api/sendTeslaAPICommand` now takes the vehicle's VIN (`vehicleVIN`) instead of the numeric vehicle ID (`vehicleID`); the web UI and debug dump read vehicles from the registry
     * (@MikeBishop) - A providerSuppressions entry for HomeAssistant now also drops Home Assistant vehicle reads, not only its commands
     * (@MikeBishop) - Vehicle channels are providers that declare capabilities with per-operation cost and locality; commands walk a fixed order (TWC, BLE, then cloud; billed last) with per-provider suppressions (settings providerSuppressions); commandPolicy maps onto them; HomeAssistant, when loaded, joins the command order last (after Fleet) and is suppressed under ble_only; the debug API goes through the same order
     * (@MikeBishop) - Charging endpoints (a TWC, or a car whose amps BLE, Fleet or HomeAssistant can set) are grouped into charging points by the car they serve, so a car that stops charging on its TWC gets no second power share or Fleet charge-rate commands. The distributor allocates per point, an idle TWC counts nothing against the budget, and a car's amps are queued to the vehicle worker instead of being sent to the Fleet API from the RS-485 loop
@@ -49,12 +49,13 @@ This document logs the changes per release of TWCManager.
     * (@MikeBishop) - A failed BLE command no longer falls through to a billed Fleet API command at once (#698 for lowering); Home Assistant is used only when the Fleet API is unavailable or has refused, never after a plain Fleet failure, so one change is never billed twice; Home Assistant can now restore a car's normal limit; charge limit lowers never wake the car over BLE (#698)
     * (@MikeBishop) - Tesla API vehicle reads time out after 10 seconds, and a read sends at most three vehicle_data requests, counting the resend after a token refresh. A Fleet API token refused again right after a refresh is removed, as any rejected token is (#689); an HTTP 412 on a command stops commands with that token until it changes, without stopping reads
     * (@MikeBishop) - Storm Watch's Tesla API requests time out after 10 seconds, and their errors log only the exception type, never its text
     * (@MikeBishop) - Under Charge Rate Control mode 2 (and mode 3 below 6 A), the TWC offers the car's share until the car's rate is confirmed, then its maximum; a rate command that keeps failing no longer leaves the TWC at its maximum while the car draws more than its share. A car no provider can set the rate for is held to its share by the TWC
     * (@MikeBishop) - A charge limit is only changed when its current value is known (from any source); TeslaBLE no longer sets a limit it could not read
     * (@MikeBishop) - Owner API commands for a `command_signing: off` vehicle sit just ahead of the Fleet API in the command order, so with both tokens such a vehicle's commands go to the free Owner API, and to the Fleet API once Tesla refuses them. A 410 or 412 (or "only available on fleetapi") stops Owner API commands and wakes for every car on that token until it is entered or synced again, logged once as an error; reads continue (#659)
+    * (@MikeBishop) - The READMEs open with the setups TWCManager supports (chargers, command paths to the car, telemetry sources and energy sources, and what each adds), and the docs are brought in line with 1.4.1: Gen3-only and car-only installs, Bluetooth under Docker, the Vehicles page, the Owner and Fleet APIs, and settings and behaviour that have changed or gone
 
 ## v1.4.0 - 2026-10-26
 
 * Features
     * (@MikeBishop) - Apply charge limit over BLE
     * (@MikeBishop) - Fetch charge and location state over BLE, falling back to Fleet API when BLE is unavailable
diff --git a/README.md b/README.md
index 6911399e..3dacee78 100644
--- a/README.md
+++ b/README.md
@@ -1,31 +1,53 @@
 # TWCManager
 
-[![Stable Release](https://img.shields.io/badge/Stable_Release-1.3.2-blue)](https://github.com/ngardiner/TWCManager/releases/tag/v1.3.2)
-[![Development Release](https://img.shields.io/badge/Devel_Release-1.4.0-green.svg)](https://github.com/ngardiner/TWCManager/tree/main)
+[![Stable Release](https://img.shields.io/badge/Stable_Release-1.4.0-blue)](https://github.com/ngardiner/TWCManager/releases/tag/v1.4.0)
+[![Development Release](https://img.shields.io/badge/Devel_Release-1.4.1-green.svg)](https://github.com/ngardiner/TWCManager/tree/main)
 ![Build Status](https://github.com/ngardiner/TWCManager/actions/workflows/test_suite.yml/badge.svg)
 ![GitHub commits](https://img.shields.io/github/commit-activity/m/ngardiner/TWCManager)
 ![Docker Pulls](https://img.shields.io/docker/pulls/twcmanager/twcmanager.svg)
 ![Contributors](https://img.shields.io/github/contributors/ngardiner/TWCManager)
 
 ## Screenshots
 ![Screenshot](docs/screenshot.png)
 ![Screenshot](docs/screenshot4.png)
 
 ## How it works
 
-* In order to allow multiple Tesla Wall Connector (TWC) units to operate on a single power circuit, Tesla provides a Load-Sharing protocol to interconnect the Tesla Wall Connector units together, and to direct those units to charge at a specific rate based on the number of cars charging simtultaneously.
-* This script (TWCManager) pretends to be a Tesla Wall Charger (TWC) set to master mode.
-* When wired to the IN or OUT pins of real TWC units set to slave mode (rotary switch position F), TWCManager can limit car charging based on information from inverters and panels.
-* This allows us to:
-    * Track the real-time availability of green energy sources (including PV Inverters, Battery Systems and Weather APIs) and direct the slave TWCs to use near the exact amount of energy available for the current conditions.
-    * Send on-demand commands to TWC devices to charge at specified rates and times.
-    * Schedule charging to occur at regular intervals.
-    * Control which vehicles can and cannot use a TWC device based on VIN (for supported vehicles and TWCs).
+TWCManager decides how much power your cars may charge with, from your solar generation, your house's consumption, your schedule and your wiring limits, and then makes the chargers and cars follow that decision.
 
-Would you like a full list of features available in TWCManager? Click [here](docs/Features.md)
+It works with any combination of chargers and car connections. Any one of them is enough to start with, and each one you add makes it work better. We recommend at least one **command path** to each car and one **telemetry source** for it.
+
+* **Chargers TWCManager controls**
+    * Gen2 Tesla Wall Connectors, over their RS-485 load-sharing bus. TWCManager acts as the master TWC and sets each slave's current.
+    * Gen3 Tesla Wall Connectors (1.4.0), by emulating the Neurio energy meter they read over RS-485. A Gen3-only install, with no Gen2 TWC or RS-485 adapter for one, also works (1.4.1).
+* **Command paths to the car** (start and stop charging, charge rate, charge limit, wake)
+    * Bluetooth (TeslaBLE): free and local, for cars in range.
+    * Tesla Owner API: free, but it commands only the cars Tesla lists with `command_signing: off`; it reads every car.
+    * Tesla Fleet API: Tesla bills each command, and needs the Vehicle Command proxy.
+    * Home Assistant's Tesla Fleet integration, also billed.
+* **Telemetry sources** (where the car is, whether it is plugged in, asleep or charging)
+    * TeslaMate and Fleet Telemetry: live feeds that report each change.
+    * Home Assistant, the Tesla API (free on the Owner API, billed on the Fleet API) and Bluetooth: read when TWCManager asks.
+
+What each part adds, and what you go without:
+
+* **No charger:** a car on a mobile connector or another brand of charger gets its charge rate set through its command path (Bluetooth, the Owner API or the Fleet API; Home Assistant from 1.4.1), and the vehicle watch (1.4.1) notices it arriving, plugging in, charging and leaving. Without a TWC or Bluetooth, set the home location on the Settings page.
+* **No telemetry feed:** the vehicle watch (1.4.1) keeps track of each car with free sleep-state checks, and reads it only when something changes.
+* **No command path:** TWCManager can only set the current a TWC offers. It cannot set a charge limit, and it can stop a car only through the charger; on a Gen2 that means methods a Tesla tolerates only a few times per session (see [Stop Charging Method](docs/Settings.md#stop-charging-method)).
+
+[Supported setups](docs/README.md#supported-setups) describes these combinations in more detail.
+
+Energy sources (EMS modules) work the same way: none is required, and each one adds something.
+
+* **No EMS:** scheduled charging, Charge Now and the non-scheduled rate all work, but there is no green-energy charging.
+* **Generation:** Track Green Energy charges with the power your panels produce.
+* **Consumption:** charging uses only the surplus your house does not use itself, and `maxAmpsAllowedFromGrid` caps how much charging may draw from the grid. With `subtractChargerLoad` set, the chargers' own draw (Gen2, Gen3, and from 1.4.1 cars charging on other chargers) is taken out of a meter that counts it. The vehicle watch also uses a step in consumption to notice a car starting or stopping on a charger TWCManager does not control (1.4.1).
+* **Several EMS modules:** their generation figures are added together, and so are their consumption figures, so each module should measure something different.
+
+Read the full [list of features](docs/Features.md).
 
 ## Installation and Configuration
 
 All installation and configuration documentation (Physical and Software) is contained in the documentation repository [here](docs/README.md)
 
 ## Interfaces
@@ -33,32 +55,38 @@ All installation and configuration documentation (Physical and Software) is cont
 To enable TWCManager to gather the solar generation information that it requires to adjust the charging rate, we provide Interfaces to allow information to be retrieved (EMS Interfaces) and Interfaces to allow us to provide information to external systems to inform them of current charging output and number of cars currently charging.
 
 ### Communication Interfaces
 | Platform                                 | Details                 |
 | ---------------------------------------- | ----------------------- |
 | [Dummy](docs/modules/Interface_Dummy.md) | Interface to simulate a TWC device for testing   |
-| [RS485](docs/modules/Interface_RS485.md) | Communicate over RS485 Serial or basic TCP communications |
+| [RS485](docs/modules/Interface_RS485.md) | Communicate with Gen2 TWCs over RS485 Serial or basic TCP communications |
 | [TCP](docs/modules/Interface_TCP.md)     | Communicate over more complex TCP network channels (In Development) |
 
+### Charger Controllers
+
+| Platform                                 | Details                 |
+| ---------------------------------------- | ----------------------- |
+| [Gen3TWCs](docs/modules/Controller_Gen3TWCs.md) | Controls Gen3 Wall Connectors through Neurio meter emulation (1.4.0) |
+
 ### Control Interfaces
 
 | Platform                            | Details                 |
 | ----------------------------------- | ----------------------- |
 | [HTTPControl](docs/modules/Control_HTTP.md) | Allows control via embedded HTTP server (with RESTful API interface) |
 | [MQTTControl](docs/modules/Control_MQTT.md) | Allows control via MQTT |
-| [OCPPControl](docs/modules/Control_OCPP.md) | Allows integration with [OCPP](https://pypi.org/project/ocpp/) |
+| OCPPControl | Allows integration with [OCPP](https://pypi.org/project/ocpp/) |
 | [WebIPCControl](docs/modules/Control_WebIPC.md) | Allows control via external scripts (sysv IPC) |
 
 ### EMS Interfaces
 
 EMS Interfaces read solar generation and/or consumption values from an external system. Current EMS interfaces are:
 
 | Platform                      | Status        | Details                 |
 | ----------------------------- | ------------- | ----------------------- |
 | Dutch SmartMeter | In Development | Supports DSMR Serial Protocol |
-| [DSMReader](docs/modules/DMS_DSMReader.md)      | Available | Supports DSM Reader via MQTT |
+| [DSMR-reader](docs/modules/EMS_DSMRreader.md)      | Available | Supports DSM Reader via MQTT |
 | [Efergy](docs/modules/EMS_Efergy.md)            | Available | Supports Efergy Pro Sensors |
 | [Enphase](docs/modules/EMS_Enphase.md)          | Available | Supports Enphase Enlighten API |
 | [Fronius Inverter](docs/modules/EMS_Fronius.md) | Available | Supports Fronius Inverter API |
 | [Growatt](docs/modules/EMS_Growatt.md)          | Available | Support for Growatt Battery systems |
 | [HomeAssistant](docs/modules/EMS_HASS.md)       | Available | Supports HomeAssistant sensors |
 | [IoTaWatt](docs/modules/EMS_Iotawatt.md)       | Available | Supports Iotawatt outputs |
@@ -101,16 +129,19 @@ Status interfaces publish TWCManager status information to external systems. Cur
 | [MQTT](docs/modules/Status_MQTT.md)          | Publishes MQTT topics to monitor TWCManager State |
 
 ### Vehicle Interfaces
 
 | Platform    | Details                                  |
 | ----------- | ---------------------------------------- |
-| TeslaAPI    | Allows start/stop charging via Tesla API |
-| [TeslaBLE](docs/modules/Vehicle_TeslaBLE.md) | Allows start/stop charging via Bluetooth Low Energy |
-| [TeslaMate](docs/modules/Vehicle_TeslaMate.md) | TeslaMate integration (Tesla API Tokens) |
-| [Home Assistant](docs/modules/Vehicle_HomeAssistant.md) | Tesla Fleet via Home Assistant |
+| [TeslaAPI](docs/modules/Vehicle_TeslaAPI.md) | Commands and reads through the Tesla Owner API and Fleet API |
+| [TeslaBLE](docs/modules/Vehicle_TeslaBLE.md) | Commands and reads over Bluetooth Low Energy, free and local |
+| [TeslaMate](docs/modules/Vehicle_TeslaMate.md) | Live telemetry from TeslaMate, and Tesla API token sync |
+| [Fleet Telemetry](docs/modules/Vehicle_FleetTelemetryMQTT.md) | Live telemetry from a Tesla Fleet Telemetry server over MQTT |
+| [Home Assistant](docs/modules/Vehicle_HomeAssistant.md) | Commands and reads through Home Assistant's Tesla Fleet integration |
+
+The [Vehicles page](docs/README.md#the-vehicles-page) and the [vehicle watch](docs/Settings.md#vehicle-watch) show and track every car TWCManager knows.
 
 ## Warnings
 
 It is important to read and understand the following warnings before using this tool:
 
 * Misuse of the protocol described in this software can direct a Tesla Wall Charger to supply more current to a car than the charger wiring was designed for.
@@ -118,13 +149,13 @@ It is important to read and understand the following warnings before using this
 * This software was not written or designed with the benefit of information from Tesla and there is always a small possibility that some unforeseen aspect of its operation could damage a Tesla vehicle or a Tesla Wall Charger.
 * All efforts have been made to avoid such damage and this software is in active use on the author's own vehicle and TWC.
 * In short, USE THIS SOFTWARE AT YOUR OWN RISK.
 
 ## Limitations
 * Due to hardware limitations, TWCManager will not work with Tesla's older High Power Wall Connectors (HPWCs) that were discontinued around April 2016.
-* We do not currently have enough information about the new 2020 Tesla Wall Connector devices with WiFi to understand if they will be compatible in any way (wired or wireless) with TWCManager.
+* Gen3 Wall Connector support has been tested in software but not yet on real Gen3 hardware. See [Gen3 status](docs/Gen3_Status.md#limitations).
 
 ## Attribution
 * Original TWCManager distribution by [cdragon](https://github.com/cdragon/TWCManager)
    * The effort by @cdragon cannot be understated, if you would like to read more about the intense hardware hacking that was done to make this project a reality, read this [thread](https://teslamotorsclub.com/tmc/threads/new-wall-connector-load-sharing-protocol.72830).
 * Integrated improvements from [flodom's](https://github.com/flodorn/TWCManager) TWCManager fork. 
     * Support for multiple vehicles on multiple chargers
diff --git a/docs/Features.md b/docs/Features.md
index 219faf30..50897ac0 100644
--- a/docs/Features.md
+++ b/docs/Features.md
@@ -1,24 +1,34 @@
 # TWCManager Features
 
 ## Introduction
 
 If you're new to the TWCManager project, or if you're not new but want to know what we've been busy working on, here's a long list of features that TWCManager provides today
 
+## Charger Support
+
+   * Gen2 Tesla Wall Connectors, controlled over their RS-485 load-sharing bus, up to three per TWCManager.
+   * Gen3 Tesla Wall Connectors (1.4.0), controlled by emulating the Neurio energy meter they read, with or without Gen2 units (Gen3 without Gen2, 1.4.1).
+   * Cars on a mobile connector or another charger, through their own charge rate command.
+
 ## Vehicle Support
 
-   * Full support for Tesla vehicles including the ability to Start/Stop charging via API, and to recognize vehicle VINs.
-   * Ability to track vehicles which have used Sub-TWC devices to charge, and to specify whether the vehicle has permissions to charge
+   * Full support for Tesla vehicles: start and stop charging, set the charge rate and charge limit, and wake the car, over Bluetooth (TeslaBLE), the Tesla Owner API or Fleet API, or Home Assistant. Free local paths are always tried before billed cloud ones.
+   * Live telemetry from TeslaMate or Fleet Telemetry, and reads over Bluetooth, the Tesla API or Home Assistant.
+   * Presence from events: each car is Home, Probably home or Away, and the home location is learned from a car's fresh position (1.4.1).
+   * The vehicle watch keeps track of cars no TWC or live feed reports on, without waking them, within a monthly budget for billed reads (1.4.1).
+   * The Vehicles page lists every known car with its providers, presence and watch status, and can add a car by VIN (1.4.1).
+   * Recognition of vehicle VINs reported by TWCs, tracking of the vehicles that have charged, and per-vehicle permission to charge.
    * Limited support for other vehicles through generic interactions
 
 ## Green Power Support
 
    * Support for a large array of Solar Inverters, allowing tracking of Generation and Consumption values (where supported) and the ability to charge your vehicle using the delta between the Generated and Consumed power, essentially charging your vehicle for free from the sun
    * Support for a number of Battery systems including Growatt and Tesla Powerwall, where charging can be controlled via appropriate SOC, Generation and Consumption values.
    * Integration with other projects including openWB for control of charging
-   * Unable to find a module which works for your inverter or have an inverter which
+   * Unable to find a module which works for your inverter? The URL and MQTT modules read values from any system that can publish them.
 
 ## Control of TWC Devices
 
    * Support for controlling your TWC devices through a number of interfaces including an in-built Web UI, RESTful API, HomeAssistant and MQTT interfaces.
 
 ## Technical Features
diff --git a/docs/Gen3_Status.md b/docs/Gen3_Status.md
index 8c88d103..637a677c 100644
--- a/docs/Gen3_Status.md
+++ b/docs/Gen3_Status.md
@@ -45,13 +45,13 @@ which returns `vehicle_connected`, `vehicle_current_a`, `grid_v`,
 ---
 
 ## Hardware requirements
 
 | Component | Detail |
 |-----------|--------|
-| RS485 adapter | A **second** USB-to-RS485 adapter, separate from the one used for Gen2 slaves.  Connected to the Gen3's Neurio meter terminals. |
+| RS485 adapter | A USB-to-RS485 adapter connected to the Gen3's Neurio meter terminals.  With Gen2 TWCs as well, this is a **second** adapter, separate from the one used for Gen2 slaves; a Gen3-only install needs only this one (1.4.1). |
 | Serial wiring | 2-wire RS485 between the adapter and the Gen3's Neurio header |
 | Network | The Gen3 must be reachable by IP for vitals readback |
 | Tesla account (optional) | To name the car on each Gen3, the Gen3 must be registered in the Tesla app, and TWCManager needs a token that can read energy data (a Fleet API token with the `energy_device_data` scope) |
 
 > **Note:** The Gen3 has a single RS485 header (vs the pair on the Gen2).
 > This header is used for the Neurio meter, not for TWC load-sharing.
diff --git a/docs/InstallationGuide.md b/docs/InstallationGuide.md
index 2377f494..d83b5e8a 100644
--- a/docs/InstallationGuide.md
+++ b/docs/InstallationGuide.md
@@ -1,8 +1,10 @@
 # Installation Guide
 
+This guide covers wiring a Gen2 Tesla Wall Connector to TWCManager over RS-485. A Gen3 Wall Connector is wired to its Neurio meter terminals instead; see [Gen3TWCs](modules/Controller_Gen3TWCs.md). A car-only install, where TWCManager controls cars over Bluetooth or the Tesla API, needs no wiring at all (see [Supported setups](README.md#supported-setups)).
+
 ## Before You Begin
 
 The following steps will involve opening your Tesla Wall Charger (TWC) chassis cover for the purpose of connecting RS-485 wires to a number of terminals on the TWC. These terminals are adjacent to live components within the Tesla Wall Charger, and the risk of electrocution if appropriate safety steps are not taken is **high**.
 
 The installation does not require a great amount of electrical skill or competence, but it does involve serious voltages and currents, and for that reason, the guide will stress repeatedly the proper implementation of safety process throughout. The last thing I would want is for anyone to harm following this tutorial and for that reason I would stress that **if you are not confident that you understand the risks involved and could take the necessary steps throughout this process to protect yourself from electrocution, please do not attempt this, please ask your electrician for assistance**.
 
diff --git a/docs/PolicyCustomization.md b/docs/PolicyCustomization.md
index 66111855..adf0cfe1 100644
--- a/docs/PolicyCustomization.md
+++ b/docs/PolicyCustomization.md
@@ -143,27 +143,26 @@ To handle these cases, policies support latching.  When a policy is defined to
 latch, the conditions are treated as continuing to be true for a specified
 number of minutes after they last evaluated true.
 
 Note:
 : This does not prevent a policy change if an earlier policy's conditions become
   true.  It also does not prevent the Track Green Energy policy from deciding
-  there is insufficient power to charge, but see Flex below.
+  there is insufficient power to charge.
 
 Caution:
 : Exercise care with latching.  If a policy is restricted to apply only when the
   grid is online, but latches, it will continue operating during the beginning
   of a grid outage.
 
 The Track Green Energy policy can be latched using the `greenEnergyLatch` value.
 Custom policies can be latched using the `latch_period` attribute.
 
 ## Flexibility
 
 Flex current (`greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and a policy's
-`allowed_flex` attribute) is not supported from 1.4.0. The keys are still
-accepted, but ignored.
+`allowed_flex` attribute) is not supported (1.4.1). The keys are ignored.
 
 ## Webhooks
 
 If you want to trigger external actions based on TWCManager state changes
 (home automation, IFTTT, etc.), you can define a set of webhooks on each
 policy.  The URL you supply will receive a POST with the TWCManager status
@@ -264,14 +263,14 @@ The values in a policy definition are:
       at home, including those that are only probably home
     - `minBatteryLevelAtHome`:  The lowest battery level (0-100) of any Tesla
       currently believed to be at home (probably-home cars included); `10000` if
       unknown / no cars are home.
 - Sub-lists
 
-(Note that TWCManager does not know which vehicle is connected to which TWC, so
-only aggregate properties of all vehicles at home can be accessed.)
+(Policies see only these aggregate properties of all vehicles at home, not
+the car on a particular TWC.)
 
 ### Comparisons
 
 The comparisons which can be employed are:
 
 - `gt`: Match must be greater than value
diff --git a/docs/README.md b/docs/README.md
index 270707ec..83cd58db 100644
--- a/docs/README.md
+++ b/docs/README.md
@@ -1,15 +1,80 @@
 # TWCManager Documentation
 
 ## Having Trouble?
 
 If you're having trouble getting TWCManager working, check out our [Troubleshooting Guide](Troubleshooting.md) to see if any of our tips help you out!
 
+## Supported setups
+
+TWCManager works with any combination of chargers and car connections. Any one of them is enough to start with, and each one you add makes it work better. We recommend at least one **command path** to each car and one **telemetry source** for it.
+
+### Chargers TWCManager controls
+
+| Charger | How TWCManager controls it | Guide |
+| ------- | -------------------------- | ----- |
+| Gen2 Tesla Wall Connector | Acts as the master on its RS-485 load-sharing bus and sets each TWC's current. Gen2 units with firmware 4.5.3 or later also report the VIN of the car plugged in. | [Installation Guide](InstallationGuide.md), [RS485](modules/Interface_RS485.md) |
+| Gen3 Tesla Wall Connector (1.4.0) | Emulates the Neurio energy meter the Gen3 reads over RS-485, and reads the unit's state from its local HTTP API. Each unit gets its own target, and the car on it is named from the Tesla energy site (1.4.1). | [Gen3 status](Gen3_Status.md), [Gen3TWCs](modules/Controller_Gen3TWCs.md) |
+
+You can run Gen2 and Gen3 units together (on separate RS-485 adapters), either one alone, or neither. A Gen3-only or car-only install needs no Gen2 adapter and no change to the `interface` settings: the Gen2 link logs one error and keeps looking for an adapter (1.4.1).
+
+### Command paths to the car
+
+These start and stop charging, set the charge rate and the charge limit, and wake the car. TWCManager tries them in a fixed order, free and local first: the charger itself, then Bluetooth, then the cloud. Billed paths come last. The [Vehicle Command Policy](Settings.md#vehicle-command-policy) can rule paths out.
+
+| Path | Cost | Notes | Guide |
+| ---- | ---- | ----- | ----- |
+| Bluetooth (TeslaBLE) | Free, local | Needs the car in Bluetooth range and a key paired with it. Needs no Tesla account. | [TeslaBLE](modules/Vehicle_TeslaBLE.md) |
+| Tesla Owner API | Free | Commands only cars Tesla lists with `command_signing: off` (seen on older Model S and X). It reads every car. | [Owner API tokens](modules/Vehicle_TeslaAPI.md#owner-api-tokens) |
+| Tesla Fleet API | Billed per command and wake | Needs your own registered app and the Vehicle Command proxy. | [Tesla Fleet API](modules/Vehicle_TeslaAPI.md) |
+| Home Assistant | Treated as billed; used after the Fleet API | Through Home Assistant's Tesla Fleet integration. It cannot wake the car. | [Home Assistant](modules/Vehicle_HomeAssistant.md) |
+
+### Telemetry sources
+
+These tell TWCManager where each car is, and whether it is plugged in, charging, awake or asleep.
+
+| Source | Kind | Cost | Guide |
+| ------ | ---- | ---- | ----- |
+| TeslaMate | Live feed over MQTT: reports each change | Free | [TeslaMate](modules/Vehicle_TeslaMate.md) |
+| Fleet Telemetry | Live feed over MQTT: reports each change | Tesla bills the values the car sends | [Fleet Telemetry](modules/Vehicle_FleetTelemetryMQTT.md) |
+| Home Assistant | Read when TWCManager asks | Free to TWCManager | [Home Assistant](modules/Vehicle_HomeAssistant.md) |
+| Tesla API reads | Read when TWCManager asks | Free on the Owner API, billed on the Fleet API | [Tesla Fleet API](modules/Vehicle_TeslaAPI.md) |
+| Bluetooth reads | Read when TWCManager asks; a car in range also answers a free sleep-state check | Free, local | [TeslaBLE](modules/Vehicle_TeslaBLE.md) |
+
+### What each part adds
+
+| Without | What still works | What you lose |
+| ------- | ---------------- | ------------- |
+| A charger TWCManager controls | A car on a mobile connector or another charger gets its charge rate set through its command path (Home Assistant can do this from 1.4.1), and the [vehicle watch](Settings.md#vehicle-watch) (1.4.1) notices it arriving, plugging in, charging and leaving. | Control of cars no command path can reach. Without a TWC or Bluetooth, TWCManager cannot learn your home location: set it on the Settings page, or cars are never treated as home. |
+| A telemetry feed | The vehicle watch (1.4.1) keeps track of each car with free sleep-state checks, and reads a car only when something changes. A TWC reports its own car's plug-ins and charging. | Instant news of a car's changes away from a TWC; on the Fleet API, some billed reads (about $0.01 a day per car, within the watch's budget). |
+| A command path | The TWC offers the current TWCManager decides. | Charge limits, waking a car, and a clean stop. A car can be stopped only through its charger; on a Gen2 the methods a Tesla tolerates only a few times per session (see [Stop Charging Method](Settings.md#stop-charging-method)). |
+| Bluetooth | Cloud commands and reads. | Free local commands, and knowing a car is home because it is in range. Billed Fleet API commands carry what Bluetooth would have. |
+
+### Energy sources (EMS)
+
+EMS modules read your solar generation and your house's consumption. None is required.
+
+* **No EMS:** Scheduled Charging, Charge Now and the Non-Scheduled charge rate all work, but there is no green-energy charging.
+* **Generation only:** Track Green Energy charges with what your panels produce.
+* **Generation and consumption:** Track Green Energy charges with only the surplus your house does not use. A consumption meter also enables:
+   * `maxAmpsAllowedFromGrid`, which caps what charging may draw from the grid outside green charging;
+   * `subtractChargerLoad`, for a meter that counts the chargers' own draw. TWCManager takes out what the Gen2 TWCs, the Gen3 units and cars charging on other chargers draw (Gen3 units and other chargers from 1.4.1);
+   * the vehicle watch's consumption step (1.4.1), which reads candidate cars when the house's load rises or falls by at least a car's minimum draw. While a car is watched, the meter is read on every policy pass, not only under a green policy. See [Settings](Settings.md#consumption-step).
+* **Several EMS modules:** their generation figures are added together, and so are their consumption figures, so each module should measure something different. [Consumption Offsets](Settings.md#consumption-offsets) can stand in for a meter you do not have.
+
+The EMS modules are listed in the [main README](../README.md#ems-interfaces).
+
+## The Vehicles page
+
+The web interface's Vehicles page lists every car TWCManager knows (1.4.1): its name and VIN, the providers that reach it, its presence (Home, Probably home or Away), what the vehicle watch is doing for it, when it was last seen and its own charge limit. You can add a car by VIN there, which lets a car known only over Bluetooth be paired and controlled. Each car's page shows its Bluetooth pairing status with a Pair and a Scan for vehicle button, its pending commands (in flight, or why not sent), and any Fleet Telemetry configuration warning. A car you added by VIN that nothing else has seen can be forgotten from its page.
+
+How TWCManager decides where a car is, and learns your home location, is described under Charge Limits in [Policy Customization](PolicyCustomization.md#charge-limits) and Home Location in [Settings](Settings.md#home-location).
+
 ## Physical (RS-485) Installation
 
-Please see the [Installation Guide](InstallationGuide.md) for detailed information on the installation of the Tesla Wall Connector interface to TWCManager.
+Please see the [Installation Guide](InstallationGuide.md) for detailed information on wiring a Gen2 Tesla Wall Connector to TWCManager. For a Gen3, see [Gen3TWCs](modules/Controller_Gen3TWCs.md). A car-only install needs no wiring.
 
 ## Software Installation
 
 The following options exist for installing TWCManager:
 
    * [Docker](Software_Docker.md) - Docker uses containers to run applications in their own isolated environment. The benefits of docker include simple upgrading easy portability, with significantly less worries about Python versions or permissions in a Dockere environment than a Manual environment.
@@ -21,13 +86,13 @@ The following options exist for installing TWCManager:
 The TWCManager configuration file at ```/etc/twcmanager/config.json``` has lots of information about each of the configuration parameters and their effect on your installation. We highly recommend reading through the file carefully as you configure your installation, as this resolves the majority of issues.
 
    * In addition, we have a set of [Configuration Examples](config_examples.md) intended to help with more complex setups such as those utilizing Flex Charging. These examples help to share information that has been discussed previously when setting up more complex charging policy.
 
 ## Gen3 Wall Connector
 
-TWCManager supports Tesla Wall Connector Generation 3 units as of v1.4.0 via Neurio Modbus emulation.
+TWCManager supports Tesla Wall Connector Generation 3 units (1.4.0) via Neurio Modbus emulation, with or without Gen2 units (Gen3 without Gen2, 1.4.1).
 
    * [Gen3 Status and Architecture](Gen3_Status.md) - how Gen3 control works and its limitations
    * [Controller_Gen3TWCs module reference](modules/Controller_Gen3TWCs.md) - configuration guide
 
 ## Developing for TWCManager
 
@@ -85,48 +150,42 @@ There are a few reasons why you might see your car charging only at 6 amps:
 The first revision of TWC chargers were able to stop charging by setting the maxAmps value to 0 amps. This is not effective for newer TWC chargers, however.
 
       * Stop communicating with the Slave TWCs. 
       
 This is effective, in that stopping communications with a Slave TWC will stop the car from charging. Unfortunately the byproduct of this is that this can sometimes result in the car going into an error state, where charging can only be restarted by unplugging and replugging the TWC.
 
-In an upcoming release, this will be offered as a switchable option to replace the use of Tesla API keys for those who are not comfortable with providing their credentials to the script.
-      
-      * Use the Tesla API to connect to the car, sending a command to stop/start charging.
-
-This requires a Tesla API token, which is stored locally within a settings file. Tesla retired the legacy Owner API login, so cloud control now requires a registered FleetAPI app (see the [Tesla FleetAPI setup guide](modules/Vehicle_TeslaAPI.md)), TeslaMate token sync, or pasting a token into the Settings page. An Owner API token commands only vehicles Tesla reports with `command_signing: off`, and reads the others (see [Owner API tokens](modules/Vehicle_TeslaAPI.md#owner-api-tokens)). Local BLE control (TeslaBLE) is also available and needs no cloud token.
-
-If you have multiple cars, TWCManager will attempt to identify which cars are home using geofencing. The following page of the TMC forums thread explains it better than I could: https://teslamotorsclub.com/tmc/threads/new-wall-connector-load-sharing-protocol.72830/page-16
+This is available as the "Stop Responding to Slaves" [Stop Charging Method](Settings.md#stop-charging-method), for installs with no command path to the car.
 
-### Why do I need a Tesla API token?
+      * Send the car a stop command over one of its command paths.
 
-   * TWCManager uses a Tesla API token to talk to your vehicle(s).
-   * When the available charger capacity falls below minAmpsPerTWC, the TWCManager script will contact the Tesla API to tell the vehicle to stop charging. If this is not configured, your vehicle will continue to charge at 6A even when the charging policy dictates that we stop charging.
+This is the default Stop Charging Method. TWCManager sends the command over Bluetooth (TeslaBLE) where it can, and otherwise through the Tesla Owner API, the Fleet API or Home Assistant (see [Supported setups](#supported-setups)). Tesla retired the legacy Owner API login, so cloud commands need a registered Fleet API app (see the [Tesla Fleet API setup guide](modules/Vehicle_TeslaAPI.md)), TeslaMate token sync, or a token pasted into the Settings page. An Owner API token commands only vehicles Tesla reports with `command_signing: off`, and reads the others (see [Owner API tokens](modules/Vehicle_TeslaAPI.md#owner-api-tokens)). Bluetooth needs no cloud token.
 
-### Why does my TWC increase charging momentarily to 21A or 17A around the time that it changes charging rates?
+The stop goes only to cars that are home. How TWCManager decides that is described under Charge Limits in [Policy Customization](PolicyCustomization.md#charge-limits).
 
-There are a number of reasons for this:
+### Do I need a Tesla API token?
 
-   * In the 2017.44 firmware version Tesla released around October 2017, a bug was introduced which led to vehicle charging rates falling to 6A when charging rates were raised. This is resolved by spiking the amps.
+   * Not necessarily. TWCManager needs a command path to a car to stop it cleanly, set its charge limit or wake it. Bluetooth (TeslaBLE) is one, and needs no token; a Tesla API token or Home Assistant gives another.
+   * With no command path, when the available charger capacity falls below minAmpsPerTWC, a Gen2 TWC keeps offering the car its minimum (usually 6A) unless you choose a Stop Charging Method that stops the TWC itself.
 
 ### Why is it so hard to just stop a vehicle from charging?
 
 Good question:
 
    * Version 1 of the TWC protocol (for TWCs produced prior to and during early 2017) has a command which will cleanly stop charging Tesla vehicles.
 
    * For Version 2 TWCs produced after this time, there is no single approach which cleanly stops a Tesla vehicle from charging, without the vehicle itself wanting to stop charging. The options that exist are:
 
-      * Ask the vehicle to stop charging by sending a message via the Tesla vehicle API (obviously a Tesla-only approach)
+      * Ask the vehicle to stop charging with a command over Bluetooth or the Tesla API (obviously a Tesla-only approach)
 
       * Stop communicating with the TWC for 30 seconds or more. This method stops the connected vehicle from charging, and will resume charging once the communications resume, however doing this a number of times will cause the vehicle to give up and the only way to resume charging is to unplug and replug the vehicle.
 
       * Sending the Stop message to Slave TWCs. This method will cause charging to cease immediately by instructing the TWC to open its relay, causing the charger to de-energise. A lack of CAN bus communication with the vehicle means that whilst the vehicle will stop charging immediately, it will log a number of errors and refuse to re-start charging again until it is unplugged and re-plugged (and will show a red LED ring around the charger port).
 
          * This method does work however if the DIP 2 switch is set in the **Down** position, which represents the use of legacy charge mode, which does not use CAN bus communication with Tesla vehicles. The usefulness of this configuration is equivalent to the "Stop communicating with slaves" behaviour above - it allows a number of stops and starts before the vehicle marks the charger as bad and refuses to charge until it is unplugged and re-plugged.
 
-So in summary, the lack of a reasonable approach to stopping charging from the TWC side necessitates an API based solution.
+So in summary, the lack of a reasonable approach to stopping charging from the TWC side makes a command path to the car (Bluetooth or the Tesla API) the clean way to stop it.
 
 ### Why do only some people see vehicle VINs in the TWCManager interface?
 
 This feature was only introduced in firmware version 4.5.3, which is found on TWCs manufactured from March 2018 until the end of 2019.
 
 TWCs prior to this version will not respond to queries from TWCManager regarding the VIN of the vehicle connected. Unfortunately there is no sign that newer TWC firmwares are being installed by Tesla vehicles, and the TWCs themselves do not have internet access to upgrade themselves.
diff --git a/docs/Settings.md b/docs/Settings.md
index c47dfa4e..ef48b6d6 100644
--- a/docs/Settings.md
+++ b/docs/Settings.md
@@ -41,13 +41,13 @@ This option will allow vehicles to charge outside of Scheduled and Track Green E
       * Do not Charge
 
 The Do not Charge action states that outside of scheduled or Track Green Energy hours, the TWCManager should set the available amps to 0 for Non-Scheduled Charging.
 
       * Track Green Energy
 
-This is an option that currently does not operate (and will only set Non-Scheduled Charging rate to 0). In future, this will allow continuing of Track Green Energy behaviour outside of the hard-coded daylight hours (6am - 8pm).
+This option continues Track Green Energy outside its usual hours, which run from sunrise to sunset (6am to 8pm until TWCManager has looked up sunrise and sunset for your home location). With it, charging follows your generation and consumption at any hour.
 
 ### Charge Authorization Mode
 
 The Charge Authorization Mode determines how we determine if a vehicle that starts to charge from a TWC should be allowed to do so. There are two options available:
 
    * Vehicles can charge unless explicitly blocked
@@ -60,24 +60,24 @@ This setting specifies that any vehicle which requests to start charging will be
 
 ### Vehicle Command Policy
 
 Vehicle commands (start and stop charging, set the charge rate, set the charge limit, wake) go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Owner API, which Tesla does not bill but which is paced like a billed provider, for a car Tesla lists with `command_signing: off`; then the Fleet API, then Home Assistant) last. Free providers are always tried first. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times. A start is done while the TWC the car is plugged into measures at least 1 A, in the last 30 seconds and since the car last reported, so no start or retry goes to a car already charging. The Vehicle Command Policy suppresses providers in that order:
 
    * `prefer_ble` - Prefer local (BLE), fall back to cloud after a delay. Nothing is suppressed. This is the default.
-   * `ble_only` - Local only - never send billed cloud commands. Every non-local provider (the Fleet API and Home Assistant) is suppressed for commands; cloud reads still run.
+   * `ble_only` - Local only - never send billed cloud commands. Every non-local provider (the Owner API, the Fleet API and Home Assistant) is suppressed for commands; cloud reads still run.
    * `api_only` - Cloud only - never use BLE. TeslaBLE is suppressed for every operation, reads as well as commands.
 
 Setting `commandPolicy` under `vehicle` in config.json hard-sets the policy and disables this control.
 
 #### Who sets a car's charge rate
 
-Every Fleet API command is billed, so the Fleet API never sets a car's charge rate where a local path can: the TWC the car is plugged into, or BLE for a paired car. A car on a TWC gets its rate from the TWC. A BLE-paired car on a mobile connector (or any charger TWCManager does not control) gets its rate over BLE only; before v1.4.0 it got it from the Fleet API. If the BLE command fails, the Fleet API does not step in. To let the Fleet API carry the rate for such a car, use `api_only`. Under Charge Rate Control mode 2 (and mode 3 below 6 A), the TWC offers the car's share, not its maximum, until the car's rate is confirmed by a delivered command or a reading; a rate that cannot be delivered leaves the TWC enforcing the share.
+Every Fleet API command is billed, so the Fleet API never sets a car's charge rate where a local path can: the TWC the car is plugged into, or BLE for a paired car. A car on a TWC gets its rate from the TWC. A BLE-paired car on a mobile connector (or any charger TWCManager does not control) gets its rate over BLE only (1.4.1). If the BLE command fails, the Fleet API does not step in. To let the Fleet API carry the rate for such a car, use `api_only`. Under Charge Rate Control mode 2 (and mode 3 below 6 A), the TWC offers the car's share, not its maximum, until the car's rate is confirmed by a delivered command or a reading; a rate that cannot be delivered leaves the TWC enforcing the share.
 
 #### BLE retries
 
-A BLE command that times out or fails to connect is retried once, two seconds later; any other failure is reported straight away. The vehicle command order then decides when to try again and whether to fall back to the cloud. The `maxRetries`, `retryDelay`, `circuitBreakerThreshold` and `circuitBreakerTimeout` keys under `config.moduleConfiguration.TeslaBLE` were removed in v1.4.0 and are ignored if present.
+A BLE command that times out or fails to connect is retried once, two seconds later; any other failure is reported straight away. The vehicle command order then decides when to try again and whether to fall back to the cloud. The `maxRetries`, `retryDelay`, `circuitBreakerThreshold` and `circuitBreakerTimeout` keys under `config.moduleConfiguration.TeslaBLE` are ignored (1.4.1).
 
 #### providerSuppressions
 
 For finer control than the policy, the `providerSuppressions` setting (in settings.json, or under `vehicle` in config.json, which wins for a provider named in both) lists, per provider, the operations it may not perform:
 
 ```json
@@ -168,13 +168,13 @@ All keys are optional. The `watch` block goes at the top level of `config.json`,
     "emsNoiseWatts": 300
 }
 ```
 
 `enabled` turns the whole watch off. `emsTrigger` turns off the consumption step alone. While it is on, an energy source is configured and a car is watched, the source is read on every policy pass, as `policy.alwaysPollEMS` does, not only under a green policy; the step needs a fresh reading to see a car start or stop on another charger.
 
-The `cloudUpdateInterval` setting is the Powerwall module's cloud cache time. It no longer sets how often cars are read.
+The `cloudUpdateInterval` setting is the Powerwall module's cloud cache time. It does not set how often cars are read; the watch does.
 
 The Vehicles page shows, for each car, whether it is watched (and if not, why), the last check and its answer, and when the next one is due.
 
 ### Consumption Offsets
 
 Consumption Offsets are values which are applied to the Consumption value retrieved from EMS modules. Consumption Offsets can be either positive or negative values, and are often used to control the behaviour of TWCManager by making it appear as though the consumption is higher or lower than it is, or allows specifying an average consumption value for installations where it is not possible to query consumption data.
@@ -198,17 +198,15 @@ If it says you're using 0.67kW, that means you could either:
    * Add an offset for 670W, which would universally treat that 0.67kW as consumption regardless of grid voltage.
 
 In other words, during car charging, you want your utility meter to show a value close to 0kW meaning no energy is being sent to or from the grid.
 
 If you are able to obtain consumption details from an energy management system, don't add consumption offsets (unless you need them for other purposes), as TWCManager will query your EMS to determine the power being consumed.
 
-### Manual Tesla API key override
-
-In some instances, you may prefer to obtain the Tesla API keys yourself. The main benefit of this approach is that you do not need to provide your Tesla username or password to TWCManager.
+### Tesla API tokens
 
-Another reason to use this feature might be as a temporary workaround if the Tesla authentication flow is changed or the TWCManager authentication function is faulty.
+The Settings page shows a slot for an Owner API token and one for a Fleet API token, each with its status and a Remove token button. TWCManager can hold both: reads use the free Owner API, and commands go through the [vehicle command order](#vehicle-command-policy). See [Tesla Fleet API](modules/Vehicle_TeslaAPI.md) for logging in, and [TeslaMate](modules/Vehicle_TeslaMate.md) for syncing a token from TeslaMate.
 
-Note: Providing your Tesla username and password to TWCManager to automatically fetch your Tesla API access and refresh tokens does not put your credentials at significant risk as they are only used once to fetch the token before being destroyed, however there may nonetheless be a preference not to provide these credentials at all.
+### Manual Tesla API key override
 
-To obtain the key, you will need some knowledge of the Tesla API authentication flow. To assist with this, a <a href="http://registration.teslatasks.com/generateTokens">link</a> to a service which can assist you with this process is provided, however this does therefore require you to provide your credentials to that service. Otherwise, you may want to research the Tesla authentication flow and obtain the tokens yourself, or to obtain them from another application that you have previously authenticated to.
+If you already hold Tesla API tokens from another application, you can paste them here instead of logging in. A pasted access token goes into the Owner API or the Fleet API slot according to its type, with the refresh token if you paste one too. A refresh token pasted on its own replaces the tokens in the slot of its type and is refreshed at once; if Tesla rejects it, the previous tokens are kept.
 
-Providing any value for the Access or Refresh tokens will result in the current stored tokens being overridden with the value you supply. We don't perform any validation of the tokens and the previous values are lost. Back up your settings.json file prior to entering your token manually if you need to revert your settings.
+Pasting a token replaces the tokens stored in that slot. Back up your settings.json file before entering a token manually if you may need to revert.
diff --git a/docs/Software_Docker.md b/docs/Software_Docker.md
index be3724de..14973d77 100644
--- a/docs/Software_Docker.md
+++ b/docs/Software_Docker.md
@@ -53,12 +53,26 @@ You may need to perform some configuration of TWCManager in your environment.
    * docker-compose.yml
 
 The default ```docker-compose.yml``` file assumes that you will be using Serial interface ```/dev/ttyUSB0``` on the host machine as the serial port to communicate with the TWCs you are managing. If this is not the case, you will need to edit the file and specify the correct interface.
 
 The default  ```docker-compose.yml``` file also contains a default timezone Environment variable, commented out. Some systems will not require this to be set, however if you find the graphs and schedules are operating in a different timezone to your location (such as UTC/GMT), then you can specify the TZ attribute here with the linux value for timezone definitions. Uncomment this line to have it take effect.
 
+   * Serial devices
+
+The ```devices``` list passes ```/dev/ttyUSB0``` into the container for a Gen2 TWC's RS-485 adapter. Docker will not start the container if a listed device does not exist on the host, so on a host with no Gen2 adapter (a Gen3-only or car-only install), remove that line. TWCManager itself starts without the adapter and needs no change to its ```interface``` settings (1.4.1). For a Gen3 Wall Connector, add a line for its own adapter, for example ```"/dev/ttyUSB1:/dev/ttyUSB1"```, to match the ```port``` in [Gen3TWCs](modules/Controller_Gen3TWCs.md).
+
+   * Bluetooth (TeslaBLE)
+
+The image includes ```tesla-control``` and ```bluez```, and the default ```docker-compose.yml``` gives the container what [TeslaBLE](modules/Vehicle_TeslaBLE.md) needs:
+
+* The host must run ```bluetoothd``` with a powered, unblocked Bluetooth adapter. The container does not run its own.
+* ```tesla-control``` runs in the host's network namespace, through ```nsenter``` and the ```/proc/1/ns/:/rootns``` mount. ```nsenter``` needs the ```CAP_SYS_PTRACE``` capability; ```CAP_NET_ADMIN```, ```CAP_NET_RAW``` and ```CAP_SYS_ADMIN``` give it the Bluetooth adapter.
+* Range scans run ```bluetoothctl```, which reaches the host's ```bluetoothd``` through the ```/run/dbus``` mount and the ```DBUS_SYSTEM_BUS_ADDRESS``` setting (1.4.1).
+
+If one of these is missing, TWCManager logs why no range scan can run and shows the reason on the vehicle's page. If you will not use Bluetooth, you can remove the ```cap_add``` list and the ```/rootns``` and ```/run/dbus``` mounts.
+
    * /etc/twcmanager/config.json
 
 On your first start of the TWCManager docker container, a directory on the host will be created if it does not currently exist, and the default configuration file will be copied there. The location of this volume is ```/etc/twcmanager```. If you need to edit the configuration file, run the Docker container in interactive mode (instructions below), exit with Ctrl+C and then edit the ```/etc/twcmanager/config.json``` file that was created.
 
 ## Starting TWCManager
 
@@ -73,13 +87,13 @@ To start up TWCManager in background mode, run the following command:
 ```
 sudo docker compose -f docker-compose.yml up -d
 ```
 
 ## Monitoring the container operation
 
-After starting TWCManager, the script will run in the foreground and will regularly update with the current status. If you specified detach mode (with the ```-d``` parameter), the information can be viewed by using the ```docker logs docker_twcmanager_1 -f``` command.
+After starting TWCManager, the script will run in the foreground and will regularly update with the current status. If you specified detach mode (with the ```-d``` parameter), the information can be viewed by running ```sudo docker compose -f docker-compose.yml logs -f``` in the directory holding your ```docker-compose.yml```.
 
 An example output is as follows:
 
 <pre>
 twcmanager_1  | 11:57:49: <b>SHA 1234</b>: 00 <b>00.00/00.00A</b> 0000 0000  <b>M</b>: 09 <b>00.00/17.00A</b> 0000 0000
 twcmanager_1  | 11:57:49: Green energy generates <b>4956W</b>, Consumption <b>726W</b>, Charger Load <b>0W</b>
diff --git a/docs/Software_Manual.md b/docs/Software_Manual.md
index 31678cdc..19a6854c 100644
--- a/docs/Software_Manual.md
+++ b/docs/Software_Manual.md
@@ -32,13 +32,13 @@ sudo make venv-install
 ```
 
 This installs TWCManager into `/home/twcmanager/venv`. After running it, update the systemd service to use the venv interpreter (see [Running TWCManager as a Service](#running-twcmanager-as-a-service) below).
 
 ## Default to Python3
 
-TWCManager requires a minimum of python 3.4 to work correctly. To attempt to support Raspberry Pi OS versions going back to 2019, TWCManager is regularly tested against Python 3.4 and above to ensure that support is retained. As of TWCManager v1.2.2, a number of features are beginning to diverge based on minimum Python versions being higher than those required by TWCManager, so the following features may be unavailable if your Python version is below the minimum:
+TWCManager requires a minimum of Python 3.6 to work correctly. The following features may be unavailable if your Python version is below their own minimum:
 
    * Support for OCPP control module requires a minimum Python 3.6.1 version
 
 Raspberry Pi OS version 9 (stretch) from 2019 ships with Python 3.5.3. If you are running Raspberry Pi OS version 9 or earlier, you may not have access to a Python interpreter which supports the above features. You may want to consider the use of [pyenv](pyenv.md) to support installation of a newer Python interpreter.
 
 Python versions below 3.6 may show the following error when running ```setup.py```:
@@ -85,33 +85,37 @@ sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.5 2
 You can check that this command has been successful by running ```python --version``` and checking that the version is python3.
 
 ## Clone GIT Repository and copy files
 
 During this step, the source code and all related files will be cloned from the GitHub repository and installed into the appropriate location on your system.
 
-We have two versions of the codebase that you may want to check out. The stable version is **v1.3.2**, which will only change for stability or urgent fixes. To check out **v1.3.2**, follow these steps:
+We have two versions of the codebase that you may want to check out. The stable version is **v1.4.0**, which will only change for stability or urgent fixes. To check out **v1.4.0**, follow these steps:
 
 
 ```
 git clone https://github.com/ngardiner/TWCManager
 cd TWCManager
-git checkout v1.3.2
+git checkout v1.4.0
 sudo make install
 ```
 
 Alternatively, the **main** branch is the development branch, where all of the new ideas and features are tested prior to becoming the stable branch. This version has more features, but we can't guarantee stability.
 
 ```
 git clone https://github.com/ngardiner/TWCManager
 cd TWCManager
 git checkout main
 make install
 ```
 
+## Optional: Bluetooth (TeslaBLE)
+
+To control cars over Bluetooth, build ```tesla-control``` with ```make tesla-control``` and install the ```bluez``` package (```sudo apt-get install -y bluez```) for range scans. See [TeslaBLE](modules/Vehicle_TeslaBLE.md).
+
 ## Configure TWCManager
-After performing the installation tasks above, edit the /etc/twcmanager/config.json file and customize to suit your environment.
+After performing the installation tasks above, edit the /etc/twcmanager/config.json file and customize to suit your environment. See [Supported setups](README.md#supported-setups) for the chargers, car connections and energy sources you can combine. A Gen3-only or car-only install needs no Gen2 RS-485 adapter and no change to the ```interface``` settings (1.4.1).
 
 The following documents provide detail on specific areas of configuration:
 
    * [Policy Customization](PolicyCustomization.md)
 
 ## Running TWCManager
@@ -149,13 +153,13 @@ Enable the service. The --now flag also makes it start immediately. This will pe
 
 ```
 sudo cp contrib/twcmanager.service /etc/systemd/system/twcmanager.service
 sudo systemctl enable twcmanager.service --now
 ```
 
-   * Note: The ```systemd``` service file assumes that your TWCManager installation is in ```/home/pi/TWCManager```. If this is not the case, edit ```/etc/systemd/system/twcmanager.service``` and update the ```WorkingDirectory``` parameter to suit.
+   * Note: The ```systemd``` service file runs the installed TWCManager package as the ```twcmanager``` user with ```/usr/bin/python3```, so it does not depend on where you cloned the source.
 
 ### Using the venv-based install with systemd
 
 If you installed via `sudo make venv-install`, update the `ExecStart` line in the service file to use the venv interpreter before enabling it:
 
 ```
diff --git a/docs/Troubleshooting.md b/docs/Troubleshooting.md
index b69d8b02..5d89446a 100644
--- a/docs/Troubleshooting.md
+++ b/docs/Troubleshooting.md
@@ -1,24 +1,30 @@
 # Troubleshooting
 
 ## First Steps
 
 ### Debug Level
 
-Before undertaking any troubleshooting, the number one most useful piece of informaton to have on hand is a lot with the debugLevel turned up high. 
+Before undertaking any troubleshooting, the number one most useful piece of informaton to have on hand is a log with the logLevel turned down low. 
 
-To make sure you capture everything, set debugLevel to 11 in ```/etc/twcmanager/config.json``` and run TWCManager in the following way to log the output:
+To make sure you capture everything, set ```logLevel``` to 9 in ```/etc/twcmanager/config.json``` and run TWCManager in the following way to log the output:
 
 ```python -u -m TWCManager | tee debug.log```
 
 Please provide the log output when you [raise an issue on GitHub](https://github.com/ngardiner/TWCManager/issues/)! This information is most useful in diagnosing a problem.
 
 ### TWCManager Version
 
 Are you using the development version of TWCManager? If so, and if you are having issues, please switch to the Stable version and see if it is working. If so, you've found a bug! Please [raise an issue on GitHub](https://github.com/ngardiner/TWCManager/issues/) and let us know.
 
+## Vehicles
+
+For a problem with a car (it is not charging, is charging when it should not, or is not seen arriving or leaving), start with the web interface's Vehicles page (1.4.1). It shows each car's presence (Home, Probably home or Away), the providers that reach it, and the vehicle watch's last check and next one. A car's own page lists its pending commands, each one in flight or with the reason it has not been sent, its Bluetooth pairing status, and any Fleet Telemetry configuration warning. See [The Vehicles page](README.md#the-vehicles-page) and Vehicle watch in [Settings](Settings.md#vehicle-watch).
+
+The log also has an INFO line for each command outcome, each billed Fleet API request, and each telemetry change of plug state, drive state or geofence.
+
 ## Adapter
 
    * The required adaptor for this communication is an **RS485** adaptor. Be careful that you are not using an RS232 adaptor which is more common, but which uses a different duplexing system and uses more pins to communicate.
 
    * If you did happen to use an RS232 adaptor, you may decode the communications correctly, but you will likely have issues with transmissions (due to the lack of RTS/CTS signalling and half-duplex operation)
 
diff --git a/docs/config_examples.md b/docs/config_examples.md
index bbf69e52..4e4cbd10 100644
--- a/docs/config_examples.md
+++ b/docs/config_examples.md
@@ -18,13 +18,13 @@ In some cases, solar installations may be limited in export tariffs by an electr
 
    * Via the web interface, set a Consumption Offset in watts of 5000W
 
 This will have the following effect:
 
    * Charging will not *start* until the generated energy is at least 20A (```minAmpsPerTWC``` being 6A and after the 5kW of consumption offset that we have configured).
-   * Flex current is not supported from 1.4.0 (```greenEnergyFlexAmps``` is accepted but ignored), so charging stops once generation drops below the start threshold.
+   * Flex current is not supported (```greenEnergyFlexAmps``` is ignored), so charging stops once generation drops below the start threshold.
 
 The below shows an illustration of how this configuration improves the effeciency of this setup, by starting charging after the orange band (which is 5kW of generation) and stopping it at the same point at the end of the day. This results in avoiding the loss of exports between the orange (5kW) and green (5kW + 6A minAmpsPerTWC) bands.
 
 [Illustration of Charge Curve](charge_curve.png)
 
 ## Multiple USB Serial Devices
diff --git a/docs/modules/Control_HTTP.md b/docs/modules/Control_HTTP.md
index 4f27a53c..1d3d0ca6 100644
--- a/docs/modules/Control_HTTP.md
+++ b/docs/modules/Control_HTTP.md
@@ -1,20 +1,17 @@
 # HTTP Control Module
 
 ## Introduction
 
 The HTTP Control module allows control of the TWCManager Tesla Wall Charger controller via an in-built HTTP web server.
 
-The web-server is multi-threaded (ie, it can be managed by multiple clients simultaneously), but does not support HTTPS encryption. It listens on Port 8080. As of release v1.1.5, it does not currently have any configurable options (but will in the future).
+The web-server is multi-threaded (ie, it can be managed by multiple clients simultaneously), but does not support HTTPS encryption. It listens on Port 8080 by default; see Configuration below.
 
 ### HTTP Control Module vs IPC Web Interface
 
-There are two separate interfaces for managing TWCManager via web browser. These are:
-
-   * WebIPC - The original web interface bundled with TWCManager
-   * HTTPControl - The new in-built web interface
+HTTPControl is TWCManager's built-in web interface. The WebIPC module served the original PHP web interface, which TWCManager no longer ships (see [WebIPC](Control_WebIPC.md)).
    
 **Benefits of HTTPControl**
 
    * Tightly integrated with the TWCManager controller. Less development lead-time to add functions.
 
 **Drawbacks of HTTPControl**
@@ -67,17 +64,25 @@ The following API endpoints exist:
 | Endpoint                    | Method | Description                                       |
 | --------------------------- | ------ | ------------------------------------------------- |
 | [addConsumptionOffset](control_HTTP_API/addConsumptionOffset.md) | POST | Add or Edit a Consumption Offset value | 
 | [cancelChargeNow](control_HTTP_API/cancelChargeNow.md) | POST | Cancels active chargeNow configuration        |
 | [chargeNow](control_HTTP_API/chargeNow.md)             | POST  | Instructs charger to start charging at specified rate |
 | [deleteConsumptionOffset](control_HTTP_API/deleteConsumptionOffset.md) | POST | Delete a Consumption Offset value |
+| getActivePolicyAction    | GET    | Provides the active policy's action: 1 charge at a fixed rate, 2 do not charge, 3 track green energy |
 | getConfig                | GET    | Provides the current configuration                |
 | [getConsumptionOffsets](control_HTTP_API/getConsumptionOffsets.md) | GET | List configured offsets               |
+| getHistory               | GET  | Provides the charging history of the last two days, in 5 minute steps |
+| getLastTWCResponse       | GET  | Provides the last response to a debug command      |
 | getPolicy                | GET  | Provides the policy configuration                 |
 | getSlaveTWCs             | GET  | Provides a list of connected Slave TWCs and their state |
 | getStatus                | GET  | Provides the current status (Charge Rate, Policy) |
 | getUUID                  | GET  | Provides a unique ID for this particular master, based on the physical MAC address |
 | [saveSettings](control_HTTP_API/saveSettings.md)         | POST | Saves settings to settings file |
+| sendDebugCommand         | POST | Sends a debug command to the TWCs (used by the Debug page) |
 | [sendStartCommand](control_HTTP_API/sendStartCommand.md) | POST | Sends the Start command to all Slave TWCs    |
+| sendTeslaAPICommand      | POST | Sends a vehicle command through the command order, for the car named by `vehicleVIN` (used by the Debug page) |
+| setConsumptionOffset     | POST | Sets the green energy offset in amps (`offset`)    |
+| setLatLon                | POST | Sets the home location (`lat`, `lon`)              |
+| setPolicy                | POST | Selects a policy by name (`policy`)                |
 | [setSetting](control_HTTP_API/setSetting.md)             | POST | Set settings directly via API |
 | [sendStopCommand](control_HTTP_API/sendStopCommand.md)   | POST | Sends the Stop command to all Slave TWCs     |
 | [setScheduledChargingSettings](control_HTTP_API/setScheduledChargingSettings.md)  | POST | Saves Scheduled Charging settings --> can be retrieved with getStatus |
diff --git a/docs/modules/Controller_Gen3TWCs.md b/docs/modules/Controller_Gen3TWCs.md
index b433d729..62a0677e 100644
--- a/docs/modules/Controller_Gen3TWCs.md
+++ b/docs/modules/Controller_Gen3TWCs.md
@@ -82,13 +82,13 @@ Add the following to `config.json` and set `"enabled": true`:
 Each Gen3 unit gets its own target, as a Gen2 TWC does.  Every unit on
 the bus reads the same fake Neurio value, so TWCManager turns all the
 targets into one synthetic house load:
 
 1. It picks the house load (in amps per phase) at which the units with a
    target together draw the sum of their targets.  With one unit, the
-   headroom is exactly that unit's target, as before.  With several units
+   headroom is exactly that unit's target.  With several units
    and equal fuses, each gets the average of the targets.  If a car is
    drawing less than its headroom (for example, a full battery), its
    unused share goes to the other units.
 2. The house load is encoded as IEEE 754 FP32 values and written into
    the fake Neurio holding registers (total power at 0x90, per-phase at
    0x88/0x8A/0x8C, and corresponding current registers).
@@ -226,15 +226,16 @@ independently.  Configure both:
     "port": "/dev/ttyUSB1",
     "baudrate": 115200,
     "devices": [ ... ]
 }
 ```
 
-TWCManager's centralized power distributor allocates watts across all
-EVSE types (Gen2 slaves, Gen3 units, and Tesla API vehicles) using the
-same fair-share algorithm.
+TWCManager's centralized power distributor allocates watts across every
+charging point (Gen2 slaves, Gen3 units, and cars whose charge rate
+Bluetooth, the Tesla API or Home Assistant can set) using the same
+fair-share algorithm.
 
 ## Limitations
 
 - **No local VIN** - The Gen3 vitals API does not report a vehicle VIN.
   A car is identified by the rules in [Which car is
   connected](#which-car-is-connected).  The plug-in rule can mistake one
diff --git a/docs/modules/Interface_RS485.md b/docs/modules/Interface_RS485.md
index 7a308ed0..96320aa8 100644
--- a/docs/modules/Interface_RS485.md
+++ b/docs/modules/Interface_RS485.md
@@ -12,29 +12,31 @@ You should use this module if:
 ## Serial
 
 Serial communications with TWC is established through the use of a Serial Device, such as the default setting of ```/dev/ttyUSB0``` which represents the first USB to Serial device connected to a machine.
 
 Some examples of Serial configuration include:
 
-```"device": "/dev/ttyUSB0"``` - Connection to a USB to RS485 adaptor
-```"device": "/dev/ttyS0"```   - Connection to an onboard Serial interface
+```"port": "/dev/ttyUSB0"``` - Connection to a USB to RS485 adaptor
+```"port": "/dev/ttyS0"```   - Connection to an onboard Serial interface
+
+If the adapter is missing or cannot be opened, TWCManager logs one error and tries again every 30 seconds, so an adapter plugged in late is picked up without a restart (1.4.1). A Gen3-only or car-only install can leave the RS485 settings as shipped. The RS485 interface stands down if its port is the one the Gen3 controller uses.
 
 ## Network Communications
 
 There are two different network protocols which are supported by the RS485 module. These are less configurable than the alternate planned TCP module, however the TCP module is not yet available for use.
 
    * rfc2217 - Telnet to Serial
    * socket  - Raw network to Serial
 
 Generally, a device will provide documentation which describes the network encoding used. 
 
 Examples of the configuration of these protocols:
 
-```"device": "rfc2217://192.168.1.2:4000/"```
+```"port": "rfc2217://192.168.1.2:4000/"```
 
-```"device": "socket://192.168.1.2:4000/"```
+```"port": "socket://192.168.1.2:4000/"```
 
 ## Per-TWC amps range
 
 By default every slave TWC is offered between minAmpsPerTWC (never less than the TWC itself supports) and its wiring maximum. The distributor gives an idle TWC a target of 0 and counts nothing against the budget. On every control tick (about once a second) the TWC is offered 0 when no car is charging (a Gen2 treats 0 as its hardware minimum); when another car is charging and there is at least minAmpsPerTWC of power per car, it is offered its hardware minimum (usually 6 A), so it can see a car plug in. Brief overshoot is fine: the configured limit is already the 80% continuous rating and the next cycle rebalances. A charging TWC whose share would fall below its minimum is stopped (offered 0). To set a different range for one TWC, add `controller.Gen2TWCs` to config.json:
 
 ```json
diff --git a/docs/modules/Vehicle_HomeAssistant.md b/docs/modules/Vehicle_HomeAssistant.md
index 6c41d14e..e2b315ea 100644
--- a/docs/modules/Vehicle_HomeAssistant.md
+++ b/docs/modules/Vehicle_HomeAssistant.md
@@ -27,13 +27,13 @@ You need:
 
 1. A working **Home Assistant** instance.
 2. The **Tesla Fleet (`tesla_fleet`) integration** configured in Home Assistant, with:
    * Each Tesla exposed as a device with:
      * manufacturer `Tesla`
      * model like `Model 3`, `Model Y`, `Model X`, `Model S`
-     * a **serial number** equal to the VIN (e.g. `<VIN>`)
+     * a **serial number** equal to the VIN (e.g. `5YJ3E1EA1KF000000`)
    * Entities such as:
      * `sensor.<car>_battery_level`
      * `sensor.<car>_charging`
      * `switch.<car>_charge`
      * `number.<car>_charge_current`
      * `number.<car>_charge_limit`
@@ -147,12 +147,16 @@ You can generate a long-lived token in Home Assistant under:
   * It logs a warning and exposes no cars to TWCManager.
 * If Home Assistant is temporarily unreachable:
   * Its service calls fail, and TWCManager falls back to its other vehicle providers (or retries later) until connectivity is restored.
 * If a specific entity is missing (e.g. `number.<slug>_charge_current`):
   * That feature (e.g. setting amps) is skipped, but other features (start/stop, limit, SOC) can still work if their entities exist.
 
+Home Assistant reads are made when TWCManager asks for a car's state, at most once every 30 seconds per car; Home Assistant is not a live feed, so the [vehicle watch](../Settings.md#vehicle-watch) still looks after a car that only Home Assistant reports on.
+
+In the vehicle command order, Home Assistant comes last, after the Fleet API, and is treated as billed: like the Fleet API, it waits for the free paths (a TWC or Bluetooth) unless none can serve the car, and it is used only when the Fleet API is unavailable or has refused. It cannot wake a car. The `ble_only` Vehicle Command Policy, or a `providerSuppressions` entry for `HomeAssistant`, rules it out (see [Settings](../Settings.md#vehicle-command-policy)).
+
 The model is deliberately conservative: it won't try to use or guess entities that it did not positively match based on the slug and the `tesla_fleet` platform.
 
 ## When to Use This Integration
 
 Use the **Home Assistant Tesla Vehicle Integration** when:
 
diff --git a/docs/modules/Vehicle_TeslaAPI.md b/docs/modules/Vehicle_TeslaAPI.md
index 9f160d91..b40bf7d6 100644
--- a/docs/modules/Vehicle_TeslaAPI.md
+++ b/docs/modules/Vehicle_TeslaAPI.md
@@ -19,12 +19,27 @@ Tesla retired the legacy Owner API login, so cloud access now generally requires
 to register your own application with Tesla and complete an OAuth login. An Owner API
 token from another tool (such as TeslaMate) still reads vehicle state, and commands
 only some vehicles; see [Owner API tokens](#owner-api-tokens). If you would rather not
 register an application at all, TeslaBLE controls charging locally over Bluetooth and
 needs no Tesla account.
 
+## Owner API and Fleet API
+
+TWCManager can hold an Owner API token and a Fleet API token side by side, and uses each for what it does best:
+
+| | Owner API | Fleet API |
+|-|-|-|
+| Getting a token | Pasted, or synced from [TeslaMate](Vehicle_TeslaMate.md) | Your own registered app and the login below, or synced |
+| Reads (charge state, location) | Free | Billed (about $0.002 a read) |
+| Commands | Free, but only for cars Tesla lists with `command_signing: off` (see [Owner API tokens](#owner-api-tokens)) | Billed (about $0.001 a command, $0.02 a wake), through the Vehicle Command proxy |
+| Free online check (asleep or awake) | Yes | Yes |
+
+Reads go to the free Owner API when you have both. Both APIs come after Bluetooth (TeslaBLE) in the command order, and a billed command is sent only when no free path can serve the car, or after the free ones have failed for a while (see Vehicle Command Policy in [Settings](../Settings.md#vehicle-command-policy)).
+
+TWCManager does not read cars on a fixed clock. A read happens when something needs it (a command, a TWC's plug event, a policy that reads the battery level) and when the [vehicle watch](../Settings.md#vehicle-watch) asks, and stays fresh for 5 minutes for every caller. The watch's billed Fleet API reads draw from its monthly budget. `cloudUpdateInterval` does not set how often cars are read (1.4.1).
+
 ## Prerequisites
 
 - A Tesla account that owns the vehicle(s).
 - An application registered at https://developer.tesla.com with the **Authorization
   Code (Third-Party Tokens)** grant type (provides a client ID; a client secret is also
   issued but the default PKCE login does not use it).
diff --git a/docs/modules/Vehicle_TeslaBLE.md b/docs/modules/Vehicle_TeslaBLE.md
index 482ad228..1b8ed74b 100644
--- a/docs/modules/Vehicle_TeslaBLE.md
+++ b/docs/modules/Vehicle_TeslaBLE.md
@@ -1,22 +1,22 @@
 Tesla Bluetooth Low Energy (BLE)
 ================================
 
 ## Introduction
 
-This module provides experimental support for the Tesla BLE (Bluetooth Low Energy) interface to Tesla vehicles.
+This module talks to Tesla vehicles over Bluetooth Low Energy (BLE), using Tesla's `tesla-control` tool. It is free and local: it needs no Tesla account and no internet connection, only the car in Bluetooth range of the TWCManager host.
 
-It is currently capable of starting and stopping charging, and controlling the charge rate in line with the configurable charge rate options (Settings > Charge Rate Control).
+Over BLE, TWCManager starts and stops charging, sets the charge rate and the charge limit, wakes the car, and reads its charge state and location. BLE is the first command path TWCManager tries after the charger itself, ahead of every cloud path (see Vehicle Command Policy in [Settings](../Settings.md#vehicle-command-policy)). A car in range also answers a free sleep-state check, which tells TWCManager the car is home.
 
 ## Installation of tesla-control binary
 
 The tesla-control binary can be built for you via the TWCManager Makefile.
 
 ### Installation Steps
 
-  * Update twcmanager to at least vx.xx (update after release) to introduce Tesla BLE support (you could alternatively do this via the web-based update option)
+  * Install TWCManager, if you have not already
 
 ```make install```
 
   * Install golang and the tesla-command BLE proxy
 
 ```make tesla-control```
@@ -55,17 +55,15 @@ By default, TWCManager uses the TWC to control charge rate. This behaviour is co
    * Select either of the following options:
       * Use a vehicle command (BLE or API) exclusively to control charge rate
       * Use TWC >= 6A + vehicle command (BLE or API) < 6A
 
 ## FAQs
 
-* *Why does BLE currently require API as a fallback?*
+* *Do I need the Tesla API as well as BLE?*
 
-TWCManager was written with an explicit dependency on the API. BLE replaces some but not all of the API's functionality. For example, we cannot discover all vehicles on an account with BLE.
-
-The approach taken is to replace the API calls where an appropriate BLE replacement exists. This has the benefit of using API only as a fallback when BLE fails, which improves reliability.
+No. BLE cannot list the cars on a Tesla account, so a car is known to TWCManager when a Gen2 TWC reads its VIN, a Tesla API token or telemetry feed lists it, or you add it by VIN on the Vehicles page (1.4.1). After that, BLE alone can control it. With a Tesla API connection as well, TWCManager falls back to the cloud when BLE fails, subject to the Vehicle Command Policy.
 
 * *Why does TWCManager sometimes not send a command to a sleeping car?*
 
 Lowering a charge limit never wakes the car. Before a BLE command that may not wake the car, TWCManager runs a sleep-safe check (the car's answer says whether it is asleep); before such a Tesla API command, the free online check. If the car is asleep, the command waits, and this is logged once. While the car is known to be asleep, TWCManager runs nothing at all, so it does not retry every few minutes. The one exception is a car no live telemetry feed reports on: the vehicle watch's status check looks again every 15 minutes while the car is home, and every 30 minutes elsewhere. A held Tesla API command makes the free online check on the same clock, while it is held, unless the watch already asks the cloud (for a car only the Tesla API can see). An asleep answer changes nothing and is not logged again; an awake one sends the command.
 
 The sleep-safe check needs no pairing: it works for any car in range, with no key. While the car is awake it also reports whether the charge-port door is open. A closed door counts as unplugged. An open door is only a hint, and a BLE charge read confirms whether the car is plugged in.
diff --git a/docs/modules/Vehicle_TeslaMate.md b/docs/modules/Vehicle_TeslaMate.md
index 4a024f4f..4fbc77e2 100644
--- a/docs/modules/Vehicle_TeslaMate.md
+++ b/docs/modules/Vehicle_TeslaMate.md
@@ -5,12 +5,14 @@
 <a href="https://github.com/adriankumpf/teslamate">TeslaMate</a> is a self-hosted Tesla datalogger.
 
 The purpose of this integration is to allow users of TWCManager who also use <a href="https://github.com/adriankumpf/teslamate">TeslaMate</a> to leverage on the work already performed by TeslaMate to fetch vehicle status, significantly reducing the number of Tesla API calls that TWCManager needs to make.
 
 With both the API Token and Telemetry options enabled, we're effectively using TeslaMate to manage our API login credentials and fetch all of our vehicle status updates. The only requests that TWCManager would need to send are the initial API call to list all vehicles in your account, and commands (such as wake_up, charge, etc).
 
+TeslaMate is a free, live telemetry source: it reports each change as it happens. It sends no commands; for those, TWCManager needs a command path such as [TeslaBLE](Vehicle_TeslaBLE.md) or the [Tesla API](Vehicle_TeslaAPI.md).
+
 There is no requirement to use both sync functions when integrating with TeslaMate. You can sync only tokens, or only telemetry.
 
 ## Integrations
 
 ### Tesla API Tokens
 
@@ -72,23 +74,38 @@ To be updated - I am not using this configuration, I welcome feedback if you do.
 ### Telemetry Information
 
 TWCManager can use the MQTT topics advertised by TeslaMate to recieve charge state and SoC information from your vehicle
 
 #### Confirming Telemetry Flow
 
-Once you have MQTT connectivity set up for TeslaMate telemetry, you should see the following log entry appear for each of the vehicles tracked by TeslaMate, as long as they are within your Tesla API credential account, which indicates that we have detected Telemetry information for this vehicle:
+Once you have MQTT connectivity set up for TeslaMate telemetry, you should see the following log entry appear for each of the vehicles tracked by TeslaMate that TWCManager can match to a VIN (from the TeslaMate database when the database settings are configured, otherwise by the car's name), which indicates that we have detected Telemetry information for this vehicle:
 
-00:06:58 🚗 TeslaMat 20 Vehicle R*display_name* telemetry being provided by TeslaMate
+```
+00:06:58 🚗 TeslaMat 20 Vehicle *display_name* telemetry being provided by TeslaMateVehicle
+```
 
-This indicates that we have internally switched off telemetry polling to the Tesla API for this vehicle, to instead obtain the information from TeslaMate.
+While TeslaMate's feed is live for a car, TWCManager takes that car's changes (plug-ins, drives, position, sleep) from the feed, and the [vehicle watch](../Settings.md#vehicle-watch) leaves the car alone.
 
-Note however that TeslaMate has a health indicator which indicates whether there is an issue with a TeslaMate vehicle's tracking or connectivity. If we see that the health indicator indicates an issue, we will stop tracking the telemetry via TeslaMate until it shows healthy again, and the following message will appear:
+The feed counts as live for a car while TWCManager is connected to the MQTT broker and TeslaMate's `healthy` topic for that car is not `false`. When TeslaMate reports a car unhealthy (it has stopped tracking the car), TWCManager logs:
 
-IN PROGRESS
+```
+TeslaMate reports car <id> unhealthy
+```
 
-It is possible for TeslaMate to lose connection to the MQTT server and for the data served to become stale. If this occurs, TWCManager will detect it within 1 hour of the data going stale if the vehicle was online at the time. Currently, if the vehicle was offline at the time it will not be detected. 
+and the vehicle watch looks after the car, at its next due check, until TeslaMate reports it healthy again. The same happens for every car while the broker connection is down; TWCManager logs `Telemetry from TeslaMateVehicle has resumed` once it reconnects.
 
-Once this is detected, TWCManager will print an error message similar to the below, and revert to API polling again:
+#### Configuration
 
 ```
-18:03:25 🚗 TeslaAPI 40 Data from TeslaMateVehicle for *display_name* is stale. Switching back to TeslaAPI
+   "vehicle": {
+       "TeslaMate": {
+           "enabled": true,
+           "syncTelemetry": true,
+           "mqtt_host": "192.168.1.1",
+           "mqtt_user": "teslamate",
+           "mqtt_pass": "teslamate",
+           "mqtt_prefix": "teslamate"
+       }
+   }
 ```
+
+To sync tokens as well, add the database settings shown under Tesla API Tokens above.
diff --git a/etc/twcmanager/config.json b/etc/twcmanager/config.json
index 65d70fef..e32a8a88 100644
--- a/etc/twcmanager/config.json
+++ b/etc/twcmanager/config.json
@@ -77,15 +77,14 @@
         # for this many seconds.
         #"startStopDelay": 60,
 
         # Depending on your environment and experience with GPS location quality, you
         # may want to choose how close a car needs to be to your home location to be
         # considered "at home". Value is given in feet, one foot is about 0.3 meters.
-        # The default value is 10560 feet (2 miles), as cars in the past had quite some
-        # issues with location accuracy. Do not set this too low, but about 1000 feet
-        # should be safe usually.
+        # The default value is 1000 feet. Do not set this much lower, as a car's GPS
+        # position can drift.
         # Note the covered area is actually not a circle, but a square with a side length
         # of 2 * atHomeRadius (measured east-west & south-north).
         # "atHomeRadius": 1000,
 
         # Newer TWCs can report actual voltages.  For older TWCs, you can specify
         # what voltage should be assumed and whether the power is single (1) or
