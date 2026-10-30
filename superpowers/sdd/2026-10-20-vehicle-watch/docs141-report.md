# Docs refresh for 1.4.1: report

Worktree: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-docs`, branch `docs/1.4.1`, based on d004b603. Not pushed.

Gap list: `docs141-gaps.md` (next to this file).

## Commits

| SHA | Subject |
|-----|---------|
| fea600c5 | Lead the READMEs with what each charger, car path and EMS adds |
| e1d7f5af | Correct the docs where the code has moved on |
| 309c3acf | Document Gen3-only, car-only and Bluetooth installs |
| 85147ab3 | Note the 1.4.1 docs refresh in the changelog |
| 4f06e5c8 | Say only what is known of which cars the Owner API commands |

The last commit is a small correction to the first. Squash it into fea600c5 if you want a clean series.

## Files changed

- README.md: a "How it works" section built around chargers, command paths and telemetry, covering what you lose without each and what each EMS case gives. Badges show stable 1.4.0 and devel 1.4.1. New Charger Controllers table. The vehicle table links every module and adds Fleet Telemetry. Fixed the DSMR link, removed the dead OCPP link, and rewrote the Gen3 limitation.
- docs/README.md: a new "Supported setups" section with tables for chargers, command paths, telemetry sources, "what each part adds" and energy sources. A new "The Vehicles page" section. The Physical install section notes that Gen3-only and car-only installs need no Gen2 wiring. FAQ: stopping a car, "Do I need a Tesla API token?", the spike FAQ removed, and the geofencing forum link removed.
- docs/Settings.md: Non-Scheduled Track Green Energy; `ble_only` also rules out the Owner API; version markers for the BLE rate and retry keys corrected to 1.4.1; the `cloudUpdateInterval` wording. A new "Tesla API tokens" subsection, and the manual-override text rewritten without the username/password notes.
- docs/PolicyCustomization.md, docs/config_examples.md: flex marked removed (1.4.1). Dropped the "does not know which car is on which TWC" note.
- docs/Features.md: a Charger Support section and the vehicle-model features. Finished the dangling EMS sentence.
- docs/Software_Docker.md: serial devices (drop ttyUSB0 when there is no Gen2 adapter; add the Gen3 adapter); Bluetooth needs (host bluetoothd, nsenter and capabilities, the D-Bus mount for range scans); logs through `docker compose logs`.
- docs/Software_Manual.md: Python 3.6, stable v1.4.0, the service-file note, an optional Bluetooth section, and a pointer to Supported setups.
- docs/InstallationGuide.md: an intro saying which wiring each setup needs.
- docs/Troubleshooting.md: logLevel 9 replaces debugLevel 11. New Vehicles section.
- docs/Gen3_Status.md, docs/modules/Controller_Gen3TWCs.md: one adapter is enough for Gen3-only; removed "as before"; the distributor serves every charging point.
- docs/modules/Interface_RS485.md: the `port` key replaces `device`. Added missing-adapter behaviour (1.4.1).
- docs/modules/Control_HTTP.md: removed the stale v1.1.5 and WebIPC text. Added rows for eight undocumented endpoints.
- docs/modules/Vehicle_TeslaAPI.md: new "Owner API and Fleet API" section (costs, what each does, when cars are read).
- docs/modules/Vehicle_TeslaBLE.md: rewrote the introduction, removed the `vx.xx` placeholder, and replaced the "requires API as fallback" FAQ.
- docs/modules/Vehicle_TeslaMate.md: TeslaMate is a free live feed with no commands. Describes how liveness and health work and where the watch takes over, replacing the obsolete staleness section and the IN PROGRESS placeholder. Added a telemetry config example.
- docs/modules/Vehicle_HomeAssistant.md: placeholder VIN. Reads are polled, not a live feed. Its place in the command order, and it cannot wake.
- etc/twcmanager/config.json: the `atHomeRadius` comment now gives the real default of 1000 ft. This is a comment-only change outside docs/, made because installers read that file as documentation.
- CHANGELOG.md: one v1.4.1 line, placed under Bugfixes. The file has no Documentation category, and 1.3.4 filed its Docker docs update under Bugfixes.

## Gaps left unfixed

- No README rows or module docs for the EMS modules Victron and MQTT. Writing them means documenting their config keys, which is out of scope for a vehicle-model refresh.
- docs/Scheduling.md is still the v1.2.1 migration history. Its tail also seems to be Debug.md content pasted in. Left alone because it is unrelated to 1.4.x.
- Vehicle_TeslaMate.md "Docker Installation: To be updated": nothing in the code to fill it from.
- Software_Docker/Software_Manual sample console output (`SHA 1234: 00 00.00/00.00A ...`) is probably an old log format. I did not verify it against the current Logging_Console output.
- Status_MQTT.md covers Gen2 slaves only. Whether Gen3 units publish MQTT status was not checked.
- The `watch` block is documented in Settings.md, but the shipped config.json has no commented example of it. That is a config change, not a doc change.
- The docs/README FAQ "What can I do if my TWC is showing a red light" and the TWC revision history were left as written. They are still correct for Gen2.

## Code and changelog issues found

- setup.py:7 still says `version="1.4.0"` on a 1.4.1 stack. This may be intended until release.
- CHANGELOG v1.4.1 Architecture says "The Docker compose file adds `CAP_SYS_PTRACE`", but `CAP_SYS_PTRACE` is already in the v1.4.0 compose file (27f479b7 is an ancestor of v1.4.0). The docs mark it unversioned. The changelog line should probably be dropped.
- The flex/spike/dampening removal entries are in origin/main's CHANGELOG (51e1e2a4) but not on this branch's base. The docs mark flex removed (1.4.1), which matches main's entry and the code (no flex keys in lib/). That is consistent once the stack lands on main.
- HTTPControl `setPolicy` sets `active_policy` directly. I did not check whether the next policy pass overrides it right away. The endpoint table says only "Selects a policy by name".
- No functional code bugs found.

## Version markers added, with evidence

| Marker | Where | Evidence |
|--------|-------|----------|
| Gen3 Wall Connectors (1.4.0) | README, docs/README, Features, Charger Controllers table | CHANGELOG v1.4.0 Architecture "Gen3 TWC support via Neurio Modbus emulation"; `git show v1.4.0:lib/TWCManager/EVSEController/Gen3TWCs.py` exists |
| Gen3 without a Gen2 TWC / adapter (1.4.1) | README, docs/README, Features, Gen3_Status, Software_Docker, Software_Manual | CHANGELOG v1.4.1 Bugfixes "A Gen2 RS-485 adapter that is missing ... no longer stops TWCManager"; commit "Keep running when the Gen2 RS-485 adapter is absent" is after v1.4.0 (`git log v1.4.0..origin/main`) |
| Gen3 per-unit targets, car named from energy site (1.4.1) | docs/README | CHANGELOG v1.4.1 Features (Gen3 each get their own target ... live status) |
| Vehicle watch (1.4.1) | README, docs/README, Features | CHANGELOG v1.4.1 Features (vehicle watch); lib/TWCManager/Vehicle/Watch.py absent at v1.4.0 (`git ls-tree v1.4.0`) |
| Vehicles page registry list / add by VIN (1.4.1) | docs/README, Features, Troubleshooting, Vehicle_TeslaBLE | CHANGELOG v1.4.1 Features (Vehicles page lists the vehicle registry ... add a vehicle by VIN) |
| Presence and home learning (1.4.1) | Features | CHANGELOG v1.4.1 Features (`atHomeRadius` ... home) and Bugfixes (presence follows events) |
| Home Assistant sets a car's amps (1.4.1) | README, docs/README | CHANGELOG v1.4.1 Architecture "Home Assistant can now set a car's amps" |
| subtractChargerLoad covers Gen3 and other chargers (1.4.1) | README, docs/README | CHANGELOG v1.4.1 Bugfixes ("With `subtractChargerLoad` ... includes Gen3"); TWCMaster.py:967-976 |
| Watch consumption step, meter read every pass (1.4.1) | README, docs/README | CHANGELOG v1.4.1 Features (vehicle watch, consumption step); commits 18f0ffb6, 8596a2cd after v1.4.0 |
| BLE rate for a car on another charger (1.4.1) | Settings.md (was "before v1.4.0") | CHANGELOG v1.4.1 Architecture "The power distributor never has the Fleet API set a car's amps where a TWC or BLE can" |
| TeslaBLE retry keys ignored (1.4.1) | Settings.md (was "removed in v1.4.0") | CHANGELOG v1.4.1 Architecture "TeslaBLE no longer retries internally ... ignored" |
| Flex not supported (1.4.1) | PolicyCustomization | origin/main CHANGELOG v1.4.1 Architecture (51e1e2a4): "Remove flex ... Installs with TeslaAPI enabled have ignored it since 1.4.0"; no flex keys in lib/ |
| `cloudUpdateInterval` does not set read cadence (1.4.1) | Vehicle_TeslaAPI | CHANGELOG v1.4.1 Architecture (the watch replaces the deferral ladder) |
| RS-485 missing adapter retried every 30 s (1.4.1) | Interface_RS485, Software_Docker, Software_Manual | CHANGELOG v1.4.1 Bugfixes; RS485.py:74-75 |
| Docker range scans through bluetoothctl/D-Bus (1.4.1) | Software_Docker | Range scans are 1.4.1 (CHANGELOG v1.4.1 Features: Bluetooth scan; commit 49e7f971 "Scan for cars from Docker" after v1.4.0). The D-Bus mount itself predates 1.4.0 (a7e915e4), so only the scan use is marked |

Items not marked because they predate 1.4.0: TeslaBLE start/stop, Fleet Telemetry, Home Assistant vehicle, TeslaMate (all 1.3.4 or earlier); nsenter/`CAP_SYS_PTRACE` and Owner+Fleet side by side (1.4.0, which is the current stable release, so those are described plainly).

## Review fixes (docs141-review.md)

Folded into the owning commits with `--fixup` and an autosquash rebase onto d004b603. The coordinator had already squashed the Owner API fix and dropped the CAP_SYS_PTRACE clause from the changelog. New series:

| SHA | Subject |
|-----|---------|
| 74e9d3d5 | Lead the READMEs with what each charger, car path and EMS adds |
| b49c2d6e | Correct the docs where the code has moved on |
| 3d7db01c | Document Gen3-only, car-only and Bluetooth installs |
| e940fa19 | Note the 1.4.1 docs refresh in the changelog |

- README.md: removed the OCPP row, since no OCPP module exists. Reworded the README commit message to match.
- docs/README.md: Vehicles page buttons are named as the page shows them ("Pair with Vehicle" or "Re-pair with Vehicle", and "Scan for vehicle" only where a scan can run, otherwise the reason). The config examples blurb no longer mentions Flex Charging.
- docs/Software_Manual.md: removed the OCPP line. Python 3.6 is the minimum; 3.5.3 cannot run TWCManager; upgrade the OS or use pyenv.
- docs/Settings.md: Charge Rate Control modes 2 and 3 are the exception where the Fleet API may carry the rate. The generateTokens link is back, with a note that the service sees your credentials.
- docs/modules/Vehicle_TeslaMate.md: the stale "only requests" paragraph is rewritten (the watch reads a car while the feed is down or unhealthy). The feed is live only while `healthy`, once published, says `true`.
- docs/modules/Vehicle_TeslaBLE.md: the ways a car becomes known now include a Gen3 naming it from the energy site, and Home Assistant listing it.
- docs/modules/Control_HTTP.md: no history phrasing; HTTPControl is the only web interface shipped, and WebIPC is for external scripts.
- docs/modules/Vehicle_TeslaAPI.md: gives the actual read cadence. A charging car at home is read every 5 min over the Owner API, or every 15 min on the Fleet API while a policy reads its battery level. Reads also happen on changes, and status checks are free. Links Settings.md.
- docs/Software_Docker.md: "(1.4.1)" is now only on bluez in the image (absent from the v1.4.0 Dockerfile) and on range scans. The dbus mount, the variable and CAP_SYS_PTRACE are unmarked.
- Flex marker kept, per the ruling: the changelog entry is on main.

Nothing declined.

## Terminology and EVSE group (user review)

New series on d004b603: d8eb0260, 8b2d9564, c37a6943, 61cf0449 (README framing, stale fixes, new sections, changelog).

- Added and edited text says "charging station" (installer prose) or "EVSE" (compact) for the wall unit. Headings are now "EVSE Controllers", "EVSE Support" and "Charging stations (EVSEs)". Identifiers are unchanged. Commit messages and the PR draft use the same terms.
- The README Gen3 bullet now names RS-485: "Gen3 Wall Connectors, over RS-485, by emulating the Neurio energy meter they read (1.4.0)". The Gen3-only note stays at 1.4.1.
- New third bullet and docs/README table row: "Car-side control of unmanaged EVSEs -- Tesla UMC, third-party, etc. (1.4.0)". Evidence: v1.4.0 has EVSEController/TeslaAPIController.py, which lists at-home cars no TWC serves as TeslaAPIEVSE and calls `carapi.setChargeRate`. v1.3.4 has no EVSE controllers. The Bluetooth and Home Assistant rate paths are marked 1.4.1 (Settings.md BLE rate; CHANGELOG v1.4.1 "Home Assistant can now set a car's amps"), and so is the vehicle watch.

## Installer-facing rewrite and Owner API deprecation (user review)

Series: 3d18b5dc, ef8e8ff3, adc00210, 91f238fe.

- README "How it works", docs/README "Supported setups", the Vehicles page section and Features.md are rewritten for installers: what each setup needs, what it gives, and what goes missing without it. Internal terms are gone from that prose.
- Adding a car by VIN is now a docs/README FAQ entry instead of a feature item.
- Gen3_Status "Which car is on a Gen3" now says what a user must set up (the units in the Tesla app, a Fleet API token with `energy_device_data`, and `din` if the log says `no DIN match`). It also says what happens without it: the current is still set; one car that just plugged in is assumed; otherwise the car stays unnamed, and the charge rate of cars on unmanaged EVSEs is not set meanwhile (VehicleEndpoint.py:156-178).
- The Owner API is marked "deprecated by Tesla; may stop working without notice" in the README bullets and vehicle table, the docs/README tables, and the Vehicle_TeslaAPI Owner/Fleet section, each time with an alternative that doesn't depend on it.
- Code issue noted: settings.html.j2:261-262 still tells users home is set "at which your vehicle next parks". The code sets it only from a fresh position at a Wall Connector or over Bluetooth, or from the button. That is template text, not docs.

## Round 3 (user review)

Series: b5488bb6, 9f7bef26, 1cd28262, 6075fb46.

- The EMS framing in the README and docs/README is cut to "Without an EMS" and "With an EMS". The fact that several modules add up moves to the README's EMS Interfaces intro.
- The README Communication Interfaces table is gone. Gen2 is now a row in EVSE Controllers, linking Interface_RS485.md. Dummy and TCP are dropped from the README; their module docs stay.
- FAQ moves:
  - "How many units..." → InstallationGuide.md FAQ, as "How many Gen2 Wall Connectors can one TWCManager control?", plus a Gen3 pointer.
  - Red light → InstallationGuide.md FAQ.
  - TWC revisions → InstallationGuide.md FAQ, as "Which Tesla Wall Connectors work with TWCManager?".
  - VINs → Interface_RS485.md FAQ, plus a Gen3 pointer.
  - "Why is it so hard to just stop a vehicle" → Interface_RS485.md FAQ.
  - The Gen2 parts of "Why doesn't charging stop..." are merged into the RS485 entry. A general version stays in docs/README, with Gen2, Gen3 and unmanaged-EVSE answers.
- All relative links and anchors resolve, apart from the pre-existing `%20` link to the installation PDF.

## Round 4 (user review)

Series: fc8b4917, 880c71e7, fc3b9eb0, 9a214ed5.

- Gen3 needs RS-485: Software_Docker's serial-devices text now lists every adapter (Gen2 and Gen3) and none for car-only. docs/README, README, and Software_Manual say a Gen3-only install still has its own adapter.
- Python: Software_Manual says 3.8, with #723 settling the floor, and that Gen3 needs 3.9 because it needs pymodbus 3.8. pyenv.md and Controller_Gen3TWCs (the pymodbus prerequisite and its troubleshooting entry) are updated, and Logging_Sentry's 3.4 note is dropped. setup.py still says 3.6; see #723.
- Vehicle_TeslaAPI: an aside after the Configuration table. `energy_device_data` is needed for Gen3 naming and Powerwall Storm Watch (TeslaTokenSlot.py:13-24; TeslaPowerwall2.py:238-241). It is missing from the default login scope (TeslaAPI.py:135-138), so the aside says how to add it.
- TeslaBLE FAQ: "No, but…", with the out-of-range gaps and Gen3 naming.
- TeslaMate: "leverage on" fixed. The Owner API caveat is in the TeslaMate doc, the README bullet and table, and the docs/README table, with Fleet Telemetry named as the alternative.
