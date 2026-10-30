# Docs gap list for 1.4.1

Audited against `docs/1.4.1` at d004b603 (`vehicle-model/phase6`). Paths without a prefix are relative to the repo root. S = stale, O = omitted.

## README.md

- S: badges say Stable 1.3.2 / Devel 1.4.0; v1.4.0 is tagged (`git tag -l 'v1.4*'`, CHANGELOG.md v1.4.0 dated) and setup.py:7 is 1.4.0.
- S: "How it works" describes only the Gen2 RS-485 fake-master path; Gen3 (lib/TWCManager/EVSEController/Gen3TWCs.py) and car-commanded rates (lib/TWCManager/EVSEInstance/VehicleEndpoint.py:1-6) are not mentioned.
- S: Limitations says nothing is known about the 2020 Wall Connector (Gen3); Gen3 is supported (lib/TWCManager/EVSEController/Gen3TWCs.py, CHANGELOG v1.4.0 Architecture).
- S: EMS table links `docs/modules/DMS_DSMReader.md` (file is `docs/modules/EMS_DSMRreader.md`).
- S: Control table links `docs/modules/Control_OCPP.md`, which does not exist (no OCPP doc in docs/modules/).
- S: Vehicle table "TeslaAPI: start/stop charging via Tesla API" has no link and omits reads, Owner vs Fleet (lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:123-181).
- S: Home Assistant row says "Tesla Fleet via Home Assistant" only; it also sets amps and reads (lib/TWCManager/Vehicle/Providers/HomeAssistantProvider.py:20).
- O: no "any combination of chargers, command paths, telemetry" framing (Providers/Order.py:1-4, Watch.py:1-7).
- O: Fleet Telemetry missing from the Vehicle table (lib/TWCManager/Vehicle/FleetTelemetryMQTT.py; docs/modules/Vehicle_FleetTelemetryMQTT.md exists).
- O: Gen3 controller missing (docs/modules/Controller_Gen3TWCs.md).
- O: EMS framing: what no EMS / generation / consumption / several modules give (TWCMaster.py:979-1020 sums every module; TWCManager.py:395-410; Policy.py:292-298; Watch.py:188-198; TWCMaster.py:967-976).
- O: EMS modules without a row: Victron (lib/TWCManager/EMS/Victron.py), MQTT (lib/TWCManager/EMS/MQTT.py). (No module docs exist for them; rows left out, see report.)

## docs/README.md

- O: no framing / overview of chargers, command paths and telemetry sources, or of EMS (same refs as README).
- S: "Physical (RS-485) Installation" is presented as required; a Gen3-only or car-only install needs no Gen2 adapter (lib/TWCManager/Interface/RS485.py:74-75 retries every 30 s; CHANGELOG v1.4.1 Bugfixes).
- S: Gen3 section mentions only Neurio emulation, not the 1.4.1 per-unit targets and car naming (CHANGELOG v1.4.1 Features).
- S: FAQ "Stop communicating ... In an upcoming release, this will be offered as a switchable option" - Stop Charging Method exists (docs/Settings.md:13; settings stopChargeMode).
- S: FAQ "Use the Tesla API ... This requires a Tesla API token" - BLE, Owner API, Fleet API and Home Assistant are all command paths (Providers/*.py DECLARATIONS).
- S: FAQ "TWCManager will attempt to identify which cars are home using geofencing" + forum link - presence from events (lib/TWCManager/Vehicle/Presence.py).
- S: FAQ "Why do I need a Tesla API token?" - a command path (BLE needs no token) is what stops a car (Providers/TeslaBLEProvider.py:16).
- S: FAQ "Why does my TWC increase charging momentarily to 21A or 17A" - spike workaround removed (`spikeAmps*` absent from lib/, `grep -rn spikeAmps lib` empty; origin/main CHANGELOG v1.4.1 Architecture).
- S: FAQ "TWC Gen 3 ... connects to WiFi. As of v1.4.0 ..." - fine but says nothing of Gen3-only installs.
- O: Vehicles page, presence and home learning, vehicle watch: no pointer (Settings.md:92-176, PolicyCustomization.md:42-121).

## docs/Settings.md

- S:47 Non-Scheduled "Track Green Energy ... currently does not operate ... hard-coded daylight hours (6am - 8pm)" - it runs (Policy.py:72-81); hours are settings sunrise/sunset, default 6/20 (TWCManager.py:579-580).
- S:66 `ble_only` suppresses "the Fleet API and Home Assistant" - it suppresses commands on every cloud provider including the Owner API (Providers/Provider.py:10-14; TeslaAPIProviders.py:136,181).
- S:73 "before v1.4.0 it got it from the Fleet API" - the change is in v1.4.1 (CHANGELOG v1.4.1 Architecture "The power distributor never has the Fleet API set a car's amps where a TWC or BLE can"); also history phrasing.
- S:77 BLE retry keys "removed in v1.4.0" - removed in v1.4.1 (CHANGELOG v1.4.1 Architecture, TeslaBLE retries entry).
- S:174 "It no longer sets how often cars are read" - history phrasing; config.json:202-205.
- S:204-214 Manual Tesla API key override talks about giving TWCManager your Tesla username/password - login with credentials was removed in 1.4.0 (CHANGELOG v1.4.0 Architecture "Remove Tesla Owner API login flow"); settings.html.j2:189-216 shows Owner and Fleet slots and the manual override.
- O: Vehicles page description is one line (Settings.md:176); add-by-VIN, presence column, forget (vehicles.html.j2:15-16,48; vehicleDetail.html.j2:32,37,136; HTTPControl.py:1763,1771).

## docs/PolicyCustomization.md

- S:149 "but see Flex below" - flex removed (no flex keys in lib/).
- S:161-163 "Flex ... is not supported from 1.4.0. The keys are still accepted" - flex code is gone in 1.4.1 (`grep -rn -i flexamps lib` empty; origin/main CHANGELOG v1.4.1 Architecture).
- S:270-271 "TWCManager does not know which vehicle is connected to which TWC" - the registry names cars per TWC (Gen2 VIN, Gen3 live_status, VIN-less attribution; CHANGELOG v1.4.1). Aggregates remain the only policy values (Policy.py match values).

## docs/config_examples.md

- S:24 "Flex current is not supported from 1.4.0 (`greenEnergyFlexAmps` is accepted but ignored)" - removed (as above).

## docs/Software_Docker.md

- O: a host with no Gen2 RS-485 adapter must drop `/dev/ttyUSB0` from `devices` or Compose refuses to start (contrib/docker/docker-compose.yml:12); a Gen3 bus needs its own device line (Controller_Gen3TWCs.md port `/dev/ttyUSB1`).
- O: BLE needs in Docker: host `bluetoothd`, `/run/dbus` mount, `DBUS_SYSTEM_BUS_ADDRESS`, `/proc/1/ns` mount for nsenter, `CAP_NET_ADMIN/NET_RAW/SYS_ADMIN/SYS_PTRACE` (docker-compose.yml:18-30; Dockerfile:2 bluez, :10 PATH; TeslaBLE.py:789 nsenter).
- O: `stop_grace_period: 90s` reason (docker-compose.yml:7-9) - minor, covered by comment in file; left.
- S: `docker logs docker_twcmanager_1` - Compose v2 names containers `<project>-twcmanager-1`; `docker compose logs -f` works regardless.

## docs/Software_Manual.md

- S:36 "minimum of python 3.4" - setup.py:10 `python_requires=">= 3.6"`.
- S:91-97 stable version v1.3.2 - v1.4.0 tagged.
- S:155 service file "assumes /home/pi/TWCManager ... WorkingDirectory" - contrib/twcmanager.service has `WorkingDirectory=/tmp` and runs the installed package.
- O: BLE install (`make tesla-control`, `bluez` for range scans) only in Vehicle_TeslaBLE.md; no pointer (Makefile:56-67; TeslaBLE.py:1077-1078).
- O: Gen3-only / car-only installs need no Gen2 adapter (RS485.py:74-75).

## docs/InstallationGuide.md

- O: Gen2-only guide with no note that Gen3 wiring (Neurio header) is in Controller_Gen3TWCs.md, and that no RS-485 wiring at all is needed for a car-only install.

## docs/Troubleshooting.md

- S:232 "set debugLevel to 11" - debugLevel deprecated in favour of logLevel (config.json:225-251, "Deprecated, use logLevel instead"; DEBUG2 = 9).
- O: no pointer to the Vehicles page (presence, watch line, pending commands) for vehicle problems (vehicles.html.j2:15-16; vehicleDetail.html.j2:37).

## docs/Features.md

- S: "Start/Stop charging via API" only; no BLE, Gen3, charge limits, presence, watch.
- S:18 dangling sentence "Unable to find a module which works for your inverter or have an inverter which".

## docs/Gen3_Status.md

- S:51 hardware table "A second USB-to-RS485 adapter, separate from the one used for Gen2" - only when Gen2 TWCs are also present (RS485.py:74-75; Controller_Gen3TWCs.md:21-26).

## docs/modules/Controller_Gen3TWCs.md

- S:88 "as before" - history phrasing.
- S:232-234 distributor "Gen2 slaves, Gen3 units, and Tesla API vehicles" - cars whose amps BLE, Fleet, Owner API (command_signing off) or Home Assistant can set (VehicleEndpoint.py:35-42).

## docs/modules/Interface_RS485.md

- S:163-164,177-179 config key shown as `"device"` - the key is `"port"` (RS485.py:44-49; config.json:299).
- O: a missing or unopenable adapter logs one error and retries every 30 s (RS485.py:74-75; CHANGELOG v1.4.1 Bugfixes); no interface change needed for Gen3-only or car-only.

## docs/modules/Control_HTTP.md

- S:7 "As of release v1.1.5, it does not currently have any configurable options" - listenPort exists (table below it).
- S:13 "WebIPC - The original web interface bundled with TWCManager" - the PHP interface was removed in 1.4.0 (Control_WebIPC.md:9-11).
- O: endpoints not listed: getActivePolicyAction, getHistory, getLastTWCResponse, setPolicy, setLatLon, setConsumptionOffset, sendDebugCommand, sendTeslaAPICommand (HTTPControl.py:546-1158). `/api/checkArrival` and `/api/checkDeparture` are correctly absent.

## docs/modules/Vehicle_TeslaAPI.md

- O: Owner API vs Fleet API cost and what each adds (reads free on Owner, $0.002 on Fleet; commands $0.001, wake $0.02) - Capability.py:51-60.
- O: reads are on demand and by the vehicle watch, not a fixed poll; `cloudUpdateInterval` does not set read cadence (Watch.py:27-29; config.json:202-205).
- S:96 `wakeDelayMins` row fine; no stale deferral-ladder text found.

## docs/modules/Vehicle_TeslaBLE.md

- S:219 "experimental", capable of "starting and stopping charging" and rate - BLE also sets charge limits, wakes and reads charge state and location (TeslaBLEProvider.py:16-19).
- S:229 "Update twcmanager to at least vx.xx (update after release)" placeholder - BLE shipped in 1.3.4 (CHANGELOG v1.3.4).
- S:274-278 FAQ "Why does BLE currently require API as a fallback?" - a BLE-only car can be added by VIN on the Vehicles page (HTTPControl.py:1771; vehicles.html.j2:48; CHANGELOG v1.4.1 Features).
- O: BLE is free and local; it is first in the command order (TeslaBLEProvider.py:13-16, Order.py:49-50).
- O: Docker needs (pointer to Software_Docker.md).

## docs/modules/Vehicle_TeslaMate.md

- S:80-82 "we have internally switched off telemetry polling to the Tesla API" - while the feed is live the vehicle watch leaves the car to it (Watch.py:46-57; Presence.py:263-265).
- S:84-94 health "IN PROGRESS" placeholder and stale-data detection "within 1 hour ... Switching back to TeslaAPI" - no such message in lib/; liveness is MQTT connected and TeslaMate's per-car `healthy` topic (Telemetry.py:176-181; TeslaMateVehicle.py:152-174), logged as "TeslaMate reports car N unhealthy".
- O: telemetry config keys (`syncTelemetry`, `mqtt_*`) not shown (config.json TeslaMate block).
- O: "Docker Installation - To be updated" placeholder (left, no code fact to fill it).

## docs/modules/Vehicle_HomeAssistant.md

- S:127 example serial number `<VIN>` looks like a real VIN - use placeholder.
- O: Home Assistant reads are polled per request (at most every 30 s per car, HomeAssistant.py:156), not a live feed: the watch still covers such a car (registry liveness only from Telemetry.py:84).
- O: its commands are billed tier, after the Fleet API; it cannot wake (HomeAssistantProvider.py:18-21).

## docs/modules/Vehicle_FleetTelemetryMQTT.md

- No gaps found.

## Files checked with no gaps (or only out-of-scope history)

docs/Scheduling.md (v1.2.1 migration notes, history; left), docs/Debug.md, docs/DevelopmentGuide.md, docs/pyenv.md, docs/SlaveProtocol.md, docs/modules/EMS_*.md, docs/modules/Logging_*.md, docs/modules/Status_MQTT.md, docs/modules/Control_MQTT.md, docs/modules/Control_WebIPC.md, docs/modules/Interface_Dummy.md, docs/modules/Interface_TCP.md, docs/modules/control_HTTP_API/*.md.

## Outside docs/

- S: etc/twcmanager/config.json:83-85 says the `atHomeRadius` default is 10560 feet; the code default is 1000 (Presence.py:15, CHANGELOG v1.4.1).
