Docs for 1.4.1: any combination of EVSEs, car paths, telemetry and energy sources

A doc-only refresh for 1.4.1, based on `vehicle-model/phase6` (#726); review it after the vehicle-model stack. 1.4.1 changes which setups work and how TWCManager keeps track of cars, and several docs were already out of date. The docs now describe the code at the tip of that stack, written for someone installing TWCManager: what they can do, what they need to set up, and what they'll see.

## What a reader gets

The README and docs/README.md open with what TWCManager works with. Any combination works, any one piece is enough to start with, and each one added makes it better. We recommend at least one way to command each car and one way to hear from it.

- **Charging stations (EVSEs):**
  - Gen2 Wall Connectors over RS-485;
  - Gen3 Wall Connectors over RS-485, by emulating the Neurio meter they read (1.4.0), with or without Gen2 (1.4.1);
  - car-side control of unmanaged EVSEs -- Tesla UMC, third-party, etc. (1.4.0).
- **Ways to command the car:** Bluetooth (free, local), the Fleet API (billed), the Owner API (free, but deprecated by Tesla and may stop working without notice), and Home Assistant.
- **Ways to hear from the car:** TeslaMate or Fleet Telemetry, which report each change; or Bluetooth, Home Assistant and the Tesla API, which TWCManager asks when it needs to.
- **What you go without if you leave one out:**
  - No Wall Connector: TWCManager sets the car's own charge rate, and notices it arriving, plugging in and leaving (1.4.1). Without Bluetooth either, you set home on the Settings page.
  - No TeslaMate or Fleet Telemetry: TWCManager checks on cars without waking them, at about $0.01 a day per car on the Fleet API.
  - No way to command the car: TWCManager can only set a Wall Connector's current.
- **Energy sources:** without an EMS, scheduled and Charge Now charging still work; with one, solar charging, and a consumption reading adds surplus-only charging, `maxAmpsAllowedFromGrid`, `subtractChargerLoad`, and noticing a car on another charging station start or stop (1.4.1).

The Owner API is marked as deprecated by Tesla wherever it is offered, next to a path that doesn't depend on it: Bluetooth or the Fleet API for commands, Fleet Telemetry for updates. TeslaMate carries the same caveat, since it normally reads cars through the Owner API.

With Gen3 Wall Connectors, the docs say what a user must set up for TWCManager to know which car is on which unit (the units in the Tesla app, a Fleet API token with `energy_device_data`), and what happens without it.

docs/README.md describes the Vehicles page as a user sees it. Its FAQ keeps the questions every install has. The Gen2-only questions move where a Gen2 owner looks: the installation guide (how many units per bus, the blinking red light, which Wall Connectors work) and the RS485 doc (why only some see VINs, why a Gen2 can't stop a car cleanly), with a Gen3 note where one applies. A new FAQ entry covers adding a car by VIN, for when it doesn't show up (for example, a Bluetooth-only car on a Wall Connector that doesn't report VINs). Features.md lists what users can do, not how it works inside.

**Version markers** go only on capabilities that are new to users: "(1.4.0)" for Gen3 and car-side control of unmanaged EVSEs, "(1.4.1)" for the rest. Each comes from the CHANGELOG and from whether the code exists at the `v1.4.0` tag. Better internals that do an existing job (for example, how TWCManager decides a car is home) get no marker.

## Stale statements fixed

- **README:**
  - The OCPPControl row is removed; no such module exists.
  - The DSMR-reader link is fixed.
  - The badges show stable 1.4.0 and devel 1.4.1.
  - An EVSE Controllers table lists Gen2 (RS-485) and Gen3 Wall Connectors. The developer-only Dummy and TCP interfaces are no longer in the user README; their docs stay.
  - The EMS table notes that several EMS modules add up.
  - Every vehicle module is linked, with a Fleet Telemetry row.
- **Software_Manual, pyenv, Controller_Gen3TWCs:** Python 3.8 is the minimum, with a note that the exact floor is being settled in #723 (`setup.py` still says 3.6). Gen3 support needs Python 3.9 and pymodbus 3.8. The OCPP note is removed.
- **Settings.md:**
  - `ble_only` also rules out the Owner API.
  - The BLE rate and retry-key notes are corrected to 1.4.1.
  - What `cloudUpdateInterval` still does (the Powerwall cache time).
  - A Tesla API tokens subsection.
- **Vehicle_TeslaAPI:** a note that naming the car on a Gen3 and Powerwall Storm Watch need the `energy_device_data` scope, which the default login doesn't request, and how to add it. An "Owner API and Fleet API" section covering the Owner API's deprecation, costs, what each can command, and when cars are read (a charging car every 5 minutes, or 15 on the Fleet API while a policy reads its battery).
- **Vehicle_TeslaMate:** it is a free live feed with no commands. How liveness and health work, and where the watch takes over. This replaces the old staleness section and the in-progress placeholder.
- **Vehicle_TeslaBLE:** the intro is rewritten. "Do I need the Tesla API as well as BLE?" says no, but with the trade-off: BLE only works in range, so it can't read, locate, wake or command a car that is away, and naming the car on a Gen3 needs the API.
- **Vehicle_HomeAssistant:** reads are polled, not a live feed. Its place in the command order, and that it cannot wake a car.
- **Interface_RS485:** the key is `port`, not `device`. A missing adapter is retried every 30 s (1.4.1).
- **Control_HTTP:** stale v1.1.5 text is removed, and rows are added for eight undocumented endpoints.
- **Troubleshooting:** `logLevel` 9 replaces `debugLevel` 11. A Vehicles section.
- **PolicyCustomization, config_examples:** flex is marked as removed (1.4.1).
- **`etc/twcmanager/config.json`:** a comment only. The `atHomeRadius` default is 1000 ft, not 10560.
- **CHANGELOG:** one v1.4.1 line for the refresh.

## New sections

- **Gen3-only and car-only installs:** which wiring each setup needs (InstallationGuide, Gen3_Status, Controller_Gen3TWCs, Software_Manual).
- **Docker:** pass through every RS-485 adapter you have, Gen2 or Gen3 (a Gen3 needs one too), and none for a car-only install. For Bluetooth: host `bluetoothd`, `nsenter` and capabilities, and the D-Bus mount for range scans. Logs come through `docker compose logs`.

## Left for later

- No docs for the Victron and MQTT EMS modules.
- `Scheduling.md` is still the v1.2.1 migration history.
- The TeslaMate Docker section is still a placeholder.
- The sample console output in the install docs isn't checked against the current log format.
- The shipped `config.json` has no commented `watch` example.
- The Settings page's own home-location text still says home is set where the car next parks. That is template code, outside this doc-only PR; the docs describe what the code does.

## Terminology

"Charger" is the car's onboard component. The docs this PR adds or edits say "charging station" for the wall unit in installer prose and "EVSE" where compact or technical. Identifiers such as `subtractChargerLoad` are unchanged.

## Checks

- An independent fact-check of every changed claim against the code at this tip found 2 wrong, 1 misleading and 11 minor claims, and all are fixed. The two wrong ones were the OCPP row and the OCPP Python note.
- Every link and anchor added or edited resolves.
- No code under `lib/` or `tests/` changes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
