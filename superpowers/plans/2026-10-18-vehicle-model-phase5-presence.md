# Vehicle Model Phase 5: presence port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Is this car home" is computed fresh from **events** whenever it's needed: HOME, PRESUMED or NOT_HOME. Every vehicle message carries one applicability rule, checked on the existing read-before-write. A restore is an ordinary message.
- One home check replaces six: `TeslaAPI.update_location`/`locate`/`atHome`, HA `at_home`, `Targets._present`/`broadcastVehicles`, `Gen3TWC._correlate`'s `atHome`, and `vehicleEndpoints`' `car.atHome`.
- A Gen2 00 counts as an unplug only through two fixed filters.
- A VIN-less plug is attributed by one picker for Gen2 and Gen3.
- First: a mechanical cleanup (Task 0), then the logging the next box analysis needs (Task 1).

**Architecture** (binding: "Presence model — final" and the later bullets in the inventory, plus the pre-flight rulings F1–F20 in `sdd/2026-10-18-vehicle-model-phase5-presence/progress.md`).
- `lib/TWCManager/Vehicle/Presence.py`, a leaf module:
  - `presence(master, vehicle)` compares the times of **events**: plug-ins and unplugs (transitions), drive starts and ends, fixes outside, BLE contact and definitive BLE absence. It also reads the current plug and drive state.
  - Event times that the registry's newest-per-source store can't keep are recorded when the observation arrives, by `Presence.noteObservation` through one observe hook (F1, F2 and the drive marks).
  - There is no presence state, no tick pass and no polling.
- `applicable(master, vehicle, attempt)` is the one rule per message. Every cell is defined in Task 3 (F4, F7, F8).
  - Start and amps need the car plugged in here (or presumed plugged).
  - A charge limit for a HOME, unplugged car follows arriving versus leaving: no departure seen → apply.
  - A restore needs the car gone or leaving.
- **Send sequence for a PRESUMED car:**
  1. A BLE sleep-safe ping (`body-controller-state`). An answer is contact.
  2. Otherwise the existing free-failure wait. Paid only after `PAID_AFTER` of free failures (F20).
  3. The existing read, which also brings location and drive state, decides.
  A held message re-plans on any newer observation. Paid work made for a message that then holds counts against that desire's paid budget of 4 (F3).
- **Restores are ordinary messages from the policy pass** (E2). They never wake (`allowWake`). A plug or a newer arrival cancels them.
- **The Gen2 unplug rule** lives on `TWCSlave`. Filter (a) is strictly the slave's `reportedAmpsMax` going from > 0 on the last non-00 heartbeat to 0 on the first 00 (F6). Filter (b) is the live telemetry veto.
- **Attribution of a VIN-less plug** runs `pickPluggedCar`, ported verbatim. BASE's Gen3 "single car plugged within 120 s" guess stays decisive (F12).

**Tech Stack:** Python 3.8+ (CI 3.8–3.11), `pytest` (`tests/unit`), `requests_mock`.

**Spec:** `.superpowers/specs/2026-10-13-vehicle-model-design.md` (amended 2026-10-17), "Presence on top" and "Threading"; the ported rules are in `.superpowers/specs/2026-10-11-plug-presence-design.md`. The inventory's user decisions (later bullets win), the pre-flight rulings and `.superpowers/phase5-unplug-evidence.md` supersede them where they differ.

**Branch:** `vehicle-model/phase5` from `vehicle-model/phase4` **57dcea94**; planning worktree `scratchpad/wt-vm5`.
- Lib at BASE: **26,490** lines (`git ls-files lib | grep '\.py$' | xargs cat | wc -l`). origin/main: 23,180.
- Phase 5 ends below 26,490 (projection under "Line budget").

## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `tests --ignore=tests/API --ignore=tests/integration`.
  - BASE: **1954 passed, 1 xfailed** (on 57dcea94). The full suite passes after every task.
- **Behaviour changes allowed: only these.** Each is named in its task with its test; anything else is a defect. Where none is listed, BASE is kept (F11).
  - (a) **Presence from events** (Task 2): HOME, PRESUMED or NOT_HOME, as defined in Task 2. HA's zone state `"home"` without coordinates is no longer a location.
  - (b) **Send-time applicability** (Task 3, the table). A PRESUMED car with a real message may be woken and read on the paid path, close to main. This reverses phase4, where a car with no position and no hold got nothing.
  - (c) **A plug-in is a decision for that car only** (Task 3). `onArrival(master, vehicle)` is called once per plug-in event, by `noteObservation` or by the TWC paths. BASE's `checkArrival` re-decided every present car.
  - (d) `/api/checkArrival` and `/api/checkDeparture` answer 404 (Q9). The PR notes call it out. The internal 5/20/45-minute `checkDeparture` reads stay (Q6). The power start's `updateChargeAtHome` stays (F11), now queued as `checkCharge`.
  - (e) `atHomeRadius` defaults to 1,000 ft instead of 10,560; explicit values win; changelog line (Task 2).
  - (f) Home is never seeded from a first fix. It moves only from a car a TWC names whose registry fix is under 600 s old (Q5). The paid `update_location(v, 0)` goes (Task 2).
  - (g) A Gen2 plug session (`twcVin`) ends at the filtered unplug, not 5 s after charging stops (Q2, Task 4). `twcVin` is home evidence only while bounded by F2 (Task 2).
  - (h) VIN-less fan-out drops `vehicles[0]` (Q1). Gen3's guess goes through the same attribution, with BASE's single-car guess kept (Task 5).
  - (j) A car HOME and plugged here, with a ready `SET_AMPS` provider, gets a VehicleEndpoint, whichever module knows it (E2, Task 3).
  - (k) **Apply before the plug** (Task 3): a HOME, unplugged car with no departure seen, or with arriving newer than leaving, gets the policy limit. A car that never left, unplugged for hours, is not re-applied.
  - (l) **Near-home false positives narrowed** (Task 2): a fast charger, no cable, or charging power above the car's own AC maximum is not plug evidence.
  - (m) **Logging** (Tasks 1, 3, 4).
  - **Not changed, per F11:**
    - the away-car `statusDeferral` ladder (Q7's single value is withdrawn);
    - `updateChargeAtHome` at power start;
    - the broadcast audience (only cars BASE reached);
    - HA's "at home and on a TWC" broadcast rule;
    - `lastAtHome`, True only for HOME.
  - **Unchanged by design, each pinned by a test:**
    - held limits in settings `chargeLimits {VIN: [outside, held]}`, where absence means nothing is held;
    - never write a limit whose current value is unknown;
    - only the charge limit is adopted;
    - rate before start;
    - Gen3's cloud VIN wins;
    - a restore never wakes;
    - no read is made just to learn presence.
- **Not in scope:**
  - the fingerprint (T13), polling, the `bleSilent` exception (Q3), D2, #709, and the rest of the Vehicles tab (merged field view, per-provider panels);
  - Q7's single `statusDeferral`, which F11 withdraws.
- **Cost.**
  - Prices: `vehicle_data` $0.002, wake $0.02, command $0.001. Lists, `vehicles/{vin}` and `live_status` are free.
  - No task adds a paid request except where (b) resolves a PRESUMED car that phase4 treated as absent. Each such row is new and states its paid tuple.
  - **Existing `tests/unit/test_command_path_parity.py` counts and timings are not edited.** Traced in planning: rows 2, 4, 5, 6, 17a/b, 25 and 26, the pure-Gen2 row, the anonymous fan-out row and the mode-2 rows all keep their counts and timings under the Task 2/3 definitions. The trace is under "Parity rows traced".
    - The only edits are PLUMBING-ONLY:
      - `:1306` `api.locate(v)` → `presence(m, v) == HOME`;
      - the `realBle` ping stub (F5), which records pings in `b.pings`, not `b.runs`.
    - If any count or timing moves, stop and report (F1 rule).
  - Attribution reads never use TeslaAPI and never wake.
- **Gen3 stays whole:** the fake-Neurio solver, `WallConnectorVins`, cloud VIN, vitals `pluggedIn` writes, and the single-car guess (F12).
- **Policies, templates, `/api` fields keep working.**
  - `numCarsAtHome`/`minBatteryLevelAtHome` (TeslaAPI and HA) stay as properties, counting HOME and PRESUMED (R21).
  - `/api/getSlaveTWCs` `lastAtHome` is True only for HOME (F11).
- **Threading.**
  - Lock order unchanged: `TeslaBLE._bleLock → master.settingsLock → registry leaf`, and `TeslaAPI.vehicleListLock → settingsLock`.
  - No I/O under any lock. No RS-485 I/O off the serial thread.
  - `noteObservation` runs on the observing thread, after the store and outside the leaf lock. It reads `master.settings` home lat/lon without a lock (two floats), and writes marks max-merged under the vehicle leaf lock.
  - `noteObservation` uses the incoming observation's own value and time, never the kept one: `FieldStore._store` returns the kept observation when an older stamp arrives.
  - `onArrival` from the MQTT thread takes the Desired lock, then settings; no inversion.
  - The serial thread owns the slave's unplug state.
- **Grep scope for removed names**, every task: `git grep -nwE '<names>' -- lib html tests/unit tests/integration tests/API docs`.
- **Deleted-test rule.** Each task report maps every deleted or rewritten test to a replacement, PLUMBING-ONLY with the reason, or INTENTIONALLY CHANGED with its letter. The per-group fates of the presence-branch tests are in Task 6 (F18).
- **Test plumbing must not move a paid count** (F1). Row 26 (:1206) in particular: stop and report.
- **Line reporting** per task:
  - before and after `git ls-files lib | grep '\.py$' | xargs cat | wc -l`;
  - `git diff --shortstat <task BASE> -- lib`;
  - actual vs expected.
  More than 25 over: stop and report.
- Python 3.8; `black` on touched files only; commit trailer per the session's reminder.
- **Real objects in cross-module tests:** a real `TWCMaster`, `Gen2TWC`, `VehicleRegistry`/`DesiredStore`, `teslatokens.new_api` and `requests_mock`. Never mock a success value the real method never returns.

### Comment rule (user, 2026-10-17; binds every task)
Code must read as if it were designed this way from the start. Comments explain why the code is what it is — not how it used to be, when or why it changed, which review or ruling prompted it, or the many things it isn't. Mention an alternative only where the obvious approach isn't the right one. History goes in commit messages and PR descriptions. Keep comments short.
No phase names, PR/issue numbers, or review/ruling IDs (Q1, R14, (d) …) in code comments.

## Review Focus

1. **The sleep/wake loop can't happen,** including when the re-apply is a raise (F6).
   - Filter (a) is strict: an idle car already at 0 A gives no TWC unplug, so only telemetry can depart it. Filter (b) vetoes.
   - Restores never wake.
   - Tests:
     - `test_a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore`;
     - `test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise`;
     - `test_box_2026_10_17_morning_wake_episodes_declare_no_departure` (Task 4).
2. **A moving car gets nothing until it parks, even with BLE contact** (F7). Box arrival 15:18 driving → hold; 15:21 parked → HOME → BLE confirms and sends for free.
   - Tests: `test_box_2026_10_18_arrival_while_driving_sends_nothing_until_parked_then_ble_free` and `test_ble_contact_while_driving_still_holds` (Task 3).
3. **A missed unplug never pins a car HOME** (F2). `twcVin` counts only while its TWC reports non-00 and it is the newest evidence. A newer drive start or fix outside overrides it, and another VIN on that TWC clears it.
   - Test: `test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix` (Task 2).
4. **No uncapped paid loop from holds** (F3). A held message re-plans on any newer observation, pushed ones included. Paid wakes and reads for a message that then holds count against its paid budget of 4.
   - Tests: `test_a_hold_reads_once_and_waits_for_pushed_evidence` and `test_held_re_plans_stop_paying_after_the_budget` (Task 3).
5. **A car parked unplugged at home is not "departed" by reads** (F1). Departure is the last unplug *event*. A Disconnected reading with no plugged reading before it is not one.
   - Test: `test_repeated_disconnected_reads_are_not_a_departure` (Task 2).

---

## Where every retired piece goes (checked against 57dcea94)

| Piece (file:line) | Callers outside it | Destination | Task |
|---|---|---|---|
| `Targets.located` :19–27, `_present` :30–46, `broadcastVehicles` :60–78, header :1–8 | `TWCSlave.py:9,126,130`; `TWCMaster.py:37,202`; `test_limit_wiring.py` | `Presence.presence/homeForLimits/candidates`; `presentVehicles`/`targetsFor` stay as thin filters | 2 |
| `Targets._restoreDeparted` :126–145 | `applyPolicyLimit`, `onDeparture` | over `presence` and leaving/arriving; stale guard on the last unplug event | 2, 3 |
| `TeslaAPI.is_location_within_radius`/`is_location_home` :656–711 | `update_location`, `locate`, `update_vehicle_data`, HA :162 | `Presence.inside()`. `is_far_from_home` (:713–714) **stays** for the deferral ladder (F11) | 2 |
| `TeslaAPI.vehicleIsDefinitelyHome` :1690–1714; `TWCMaster.vehicleIsDefinitelyHome` :1563–1572, `_taskKey` :364–366; `TWCManager.py:386–387` | `test_twcmaster_vin_confirmation.py:205–256` | `Presence.learnHome(master, vehicle)` from `recordVehicleVIN` | 2 |
| `TeslaAPI.update_location`/`locate` :1901–1925; `CarApiState.atHome` :51; `:1969` | `Targets`, tests | gone. The deferral ladder :1993–2008 stays, keyed on `inside()` in place of `car.atHome` (F11) | 2 |
| `TeslaAPI.updateChargeAtHome`/counts :1675–1681, :1716–1726; `vehicleScheduledChargingPending` :1683–1688 | `TWCMaster.updateChargeAtHome`, `Policy.py:307` | over presence; the scheduled wrapper goes with its only caller (next row) | 2 |
| `TeslaBLE._scheduleBlocksStart` :177–191, `TeslaBLEProvider.startCharging`'s schedule branch :95–98 | `test_provider_outcomes_local.py:28` | **deleted** (F16): `Belief.handsOff` (:99–103) already gates every provider at plan time; the test is re-pointed at `handsOff` | 2 |
| HA `at_home`/`lat`/`lon` :68–73, :152–162; `is_location_home` :557–568; counts :580–593 | `Targets` | `Presence.inside()`/`homeCars()` | 2 |
| `HTTPControl.py:558` `.atHome` | `test_registry_callers.py:257–269` | `presence(...) == HOME` (F11) | 2 |
| `checkArrival` task `TWCManager.py:323–327`, trigger `TWCSlave.py:678`; `/api/checkArrival`, `/api/checkDeparture` `HTTPControl.py:775–786` | `tests/integration/test_api_input_validation_extended.py:89–102` | arrivals from plug-in events; the trigger now queues `checkCharge` (F11); 404 (d) | 3 |
| `checkDeparture` task `TWCManager.py:332–333`, triggers `TWCSlave.py:686–688` | — | **kept** (Q6) | — |
| `vehicleEndpoints` gate/filter `VehicleEndpoint.py:185–198`; `_telemetryPluggedIn` :164–168 | endpoint tests, `test_telemetry_registry.py:262–266` | registry vehicles HOME and plugged here; `_telemetryPluggedIn` → `Presence.telemetrySaysPlugged` (one predicate, F16) | 3 |
| `_plugSession(slave, False)` at charge stop `TWCMaster.py:1340` | `test_registry_plug_sessions.py`, `test_gen2twc_provider.py`, `test_outcome_desired.py`, lift tests | removed (g); the anonymous close at 00 (:1354–1356) stays | 4 |
| `Gen2TWC.vehicleKey`'s `lastVIN` branch :49–51 | `ChargingPoint`, `_blindTWCs`, `controlPass` | `registry.vehicleAt(twcid).key` | 4 |
| `TWCSlave.pluggedCars` :121–141, `_PLUGGED` :15–16, imports :7–9 | `ChargingPoint.anonymousCars`, `TWCMaster.py:1346` | untouched until Task 5, then `Presence.candidates`/`pluggedHere` (F16: no throw-away rewrite) | 5 |
| `ChargingPoint.anonymousCars` :182–190 incl. `vehicles[0]` | `_carKeys` | over `Presence.candidates` (h) | 5 |
| `Gen3TWC._correlate` loop :275–297, `CORRELATE_WINDOW` :68 | `WallConnectorVins.py:168` | `Presence.attribute(...)`, which keeps the single-car guess (F12) | 5 |

**Other callers checked:** docs `PolicyCustomization.md:49–80, 226–228, 277`, `Settings.md:14` and `Vehicle_HomeAssistant.md:88–93` (Task 6, F17); `etc/*.json` already show `"atHomeRadius": 1000`; `settings.html.j2:257,270` read `lat`/`lon`, which are kept; `TeslaAPIProviders.py:61` reads `statusDeferral`, unchanged because the ladder stays.

## File structure

- **Created:** `lib/TWCManager/Vehicle/Presence.py` (T2, T3, T5): ≈ 225 lines at the end; `tests/unit/test_presence.py`, `test_presence_attribution.py`, `test_gen2_unplug.py`, `test_paid_logging.py`.
- **Modified:** as listed per task. Task 0 touches 25 files.

---

### Task 0: Config lookups as one-liners (expected lib Δ ≈ −164; cheap model)

Mechanical. Behaviour is preserved exactly; the rules below say where the forms differ and why the chosen form is exact. No test is added. The full suite is the check.

Pre-flight verified this task as behaviour-identical (F19). black wraps at least 6 replacements (`OpenWeatherMap`, and `HTTPControl` 495/696/1871/1889/1902), so the expected Δ is −160..−168. `TWCMaster.py:1444` now re-assigns `settings["Vehicles"]` outside the lock; it is the same object, so this is benign.

**Rule A — try/except-default → `.get`.** Each listed block is `try: X = <lookup>` / `except KeyError: X = {}` (4 lines). It becomes the one line in the table: each `[k]` becomes `.get(k, {})`, and a two-level lookup becomes two `.get`s.
- Exactness:
  - a missing key gives `{}` either way;
  - a present key gives the same object either way;
  - a present non-dict first level raised an uncaught `TypeError` before and raises an uncaught `AttributeError` now: both crash at the same line.
- The default `{}` is a fresh dict per call in both forms, and nothing is inserted into `master.config`.

| Site (under `lib/TWCManager/`) | Replacement |
|---|---|
| `Control/HTTPControl.py:194-197` | `self.configConfig = master.config.get("config", {})` |
| `Control/HTTPControl.py:198-201` | `self.configHTTP = master.config.get("control", {}).get("HTTP", {})` |
| `Control/MQTTControl.py:23-26` | `self.configConfig = self.config.get("config", {})` |
| `Control/MQTTControl.py:27-30` | `self.configMQTT = self.config.get("control", {}).get("MQTT", {})` |
| `Control/WebIPCControl.py:23-26` | `self.configConfig = master.config.get("config", {})` |
| `Control/WebIPCControl.py:30-33` | `self.configIPC = master.config.get("control", {}).get("IPC", {})` |
| `EMS/DSMRreader.py:28-31` | `self.__configConfig = master.config.get("config", {})` |
| `EMS/DSMRreader.py:32-35` | `self.__configDSMRreader = master.config.get("sources", {}).get("DSMRreader", {})` |
| `EMS/Efergy.py:32-35` | `self.configConfig = master.config.get("config", {})` |
| `EMS/Efergy.py:36-39` | `self.configEfergy = master.config.get("sources", {}).get("Efergy", {})` |
| `EMS/EmonCMS.py:36-39` | `self.configConfig = master.config.get("config", {})` |
| `EMS/EmonCMS.py:40-43` | `self.configEmonCMS = master.config.get("sources", {}).get("EmonCMS", {})` |
| `EMS/Enphase.py:36-39` | `self.configConfig = master.config.get("config", {})` |
| `EMS/Enphase.py:40-43` | `self.configEnphase = master.config.get("sources", {}).get("Enphase", {})` |
| `EMS/Fronius.py:31-34` | `self.configConfig = master.config.get("config", {})` |
| `EMS/Fronius.py:35-38` | `self.configFronius = master.config.get("sources", {}).get("Fronius", {})` |
| `EMS/HASS.py:35-38` | `self.configConfig = master.config.get("config", {})` |
| `EMS/HASS.py:39-42` | `self.configHASS = master.config.get("sources", {}).get("HASS", {})` |
| `EMS/IotaWatt.py:33-36` | `self.configConfig = master.config.get("config", {})` |
| `EMS/IotaWatt.py:37-40` | `self.configIotaWatt = master.config.get("sources", {}).get("IotaWatt", {})` |
| `EMS/MQTT.py:28-31` | `self.__configConfig = master.config.get("config", {})` |
| `EMS/MQTT.py:32-35` | `self.__configMQTT = master.config.get("sources", {}).get("MQTT", {})` |
| `EMS/OpenHab.py:33-36` | `self.configConfig = master.config.get("config", {})` |
| `EMS/OpenHab.py:37-40` | `self.configOpenHab = master.config.get("sources", {}).get("openHAB", {})` |
| `EMS/OpenWeatherMap.py:31-34` | `self.configConfig = master.config.get("config", {})` |
| `EMS/OpenWeatherMap.py:35-40` (6 lines) | `self.configOpenWeatherMap = master.config.get("sources", {}).get("OpenWeatherMap", {})` |
| `EMS/SolarEdge.py:44-47` | `self.configConfig = master.config.get("config", {})` |
| `EMS/SolarEdge.py:48-51` | `self.configSolarEdge = master.config.get("sources", {}).get("SolarEdge", {})` |
| `EMS/TED.py:36-39` | `self.configConfig = self.config.get("config", {})` |
| `EMS/TED.py:40-43` | `self.configTED = self.config.get("sources", {}).get("TED", {})` |
| `EMS/URL.py:32-35` | `self.configConfig = master.config.get("config", {})` |
| `EMS/URL.py:36-39` | `self.configURL = master.config.get("sources", {}).get("URL", {})` |
| `EMS/Victron.py:46-49` | `self.configVictron = master.config.get("sources", {}).get("Victron", {})` |
| `Logging/CSVLogging.py:19-22` | `self.configConfig = master.config.get("config", {})` |
| `Logging/CSVLogging.py:23-26` | `self.configLogging = master.config.get("logging", {}).get("CSV", {})` |
| `Logging/ConsoleLogging.py:33-36` | `self.configConfig = master.config.get("config", {})` |
| `Logging/ConsoleLogging.py:37-40` | `self.configLogging = master.config.get("logging", {}).get("Console", {})` |
| `Logging/FileLogging.py:25-28` | `self.configConfig = master.config.get("config", {})` |
| `Logging/FileLogging.py:29-32` | `self.configLogging = master.config.get("logging", {}).get("FileLogger", {})` |
| `Logging/MySQLLogging.py:226-229` | `self.configConfig = master.config.get("config", {})` |
| `Logging/MySQLLogging.py:230-233` | `self.configLogging = master.config.get("logging", {}).get("MySQL", {})` |
| `Logging/SQLiteLogging.py:190-193` | `self.configConfig = master.config.get("config", {})` |
| `Logging/SQLiteLogging.py:194-197` | `self.configLogging = master.config.get("logging", {}).get("SQLite", {})` |
| `Logging/SentryLogging.py:25-28` | `self.configConfig = master.config.get("config", {})` |
| `Logging/SentryLogging.py:29-32` | `self.configLogging = master.config.get("logging", {}).get("Sentry", {})` |
| `Pricing/aWATTarPricing.py:23-26` | `self.configConfig = master.config.get("config", {})` |
| `Pricing/aWATTarPricing.py:28-31` | `self.configAwattar = master.config.get("pricing", {}).get("aWATTar", {})` |
| `Status/HASSStatus.py:35-38` | `self.configConfig = self.config.get("config", {})` |
| `Status/HASSStatus.py:39-42` | `self.configHASS = self.config.get("status", {}).get("HASS", {})` |
| `Status/MQTTStatus.py:46-49` | `self.__configMQTT = self.__config.get("status", {}).get("MQTT", {})` |
| `Vehicle/Telemetry.py:61-64` | `self.configConfig = self.config.get("config", {})` |
| `EMS/Kostal.py:48-53` (one try, two assigns) | two lines: `self.configConfig = master.config.get("config", {})` and `self.configKostal = master.config.get("sources", {}).get("Kostal", {})`. **Exactness:** at BASE a missing `"config"` also blanked `configKostal`. With the per-key form, `configKostal` keeps a present `sources.Kostal`. `master.config` always has `"config"` (`TWCManager.py` loads it before any module), so the case never arises. State this in the report. |
| `Vehicle/TeslaBLE.py:115-118` | `self.config = self.master.config` (attribute access cannot raise `KeyError`) |

**Left alone (not in the 53):**
- `Vehicle/Telemetry.py:65-69`: two statements, one of which sets `self.status`. A block without `"enabled"` sets `configModule = {}`, which no one-liner reproduces.
- `TWCManager.py:1604-1607` and `:1779-1785`: the except body is `newSlave(...)`, a side effect.
- `Vehicle/TeslaAPI.py:1971-1974`: catches `TypeError`; a `.get` chain on a non-dict raises `AttributeError`.

**Rule B — create-if-missing → one line.** Pick the form per test, so that every value TWCManager can hold at the key (missing, JSON `null`, `{}`, a populated dict) behaves as before:
- `if not d.get(k): d[k] = {}` → `d[k] = d.get(k) or {}`. This is exact: a falsy value is replaced, and a truthy one is re-assigned to itself.
- `if d.get(k, None) == None: d[k] = {}` → `d[k] = d.get(k) or {}`.
  - `null` and missing are replaced, as before.
  - A present `{}` is replaced by a value-equal fresh `{}`. Nothing aliases these settings sub-dicts: each is read through `master.settings[...]` again on the next line.
  - A present `""`/`0` made the next subscript raise at BASE, and now does not. That is the only divergence, and it is one from a crash.
  - `setdefault` would diverge on `null` (it returns `None`, and the next line raises), so it is **not** used here.
- `if not k in d: d[k] = []` → `d.setdefault(k, [])`. This is exact: the test is key-absent.
- Writes into `configLogging["mute"]` land in `master.config` both before and after (when `configLogging` is the real sub-dict), so nothing changes there.

| Site | Replacement |
|---|---|
| `Control/HTTPControl.py:495-496`, `:696-697` | `master.settings["consumptionOffset"] = master.settings.get("consumptionOffset") or {}` |
| `Control/HTTPControl.py:1856-1857` | `master.settings["Schedule"] = master.settings.get("Schedule") or {}` |
| `Control/HTTPControl.py:1871-1872` | `master.settings["Schedule"][day] = master.settings["Schedule"].get(day) or {}` |
| `Control/HTTPControl.py:1889-1894` (6 lines incl. comment) | `day = match.group(2)` then `master.settings["Schedule"][day] = master.settings["Schedule"].get(day) or {}`; the next statement uses `[day]` |
| `Control/HTTPControl.py:1902-1903` | `master.settings["Schedule"]["Settings"] = master.settings["Schedule"].get("Settings") or {}` |
| `Control/HTTPControl.py:2014-2015` | `master.settings["Graphs"] = master.settings.get("Graphs") or {}` |
| `Logging/CSVLogging.py:35-36`, `ConsoleLogging.py:49-50`, `MySQLLogging.py:250-251`, `SQLiteLogging.py:206-207` | `self.configLogging["mute"] = self.configLogging.get("mute") or {}` |
| `TWCMaster.py:1223-1224` | `self.settings["VehicleGroups"] = self.settings.get("VehicleGroups") or {}` |
| `TWCMaster.py:1444-1445`, `:1534-1535` | `self.settings["Vehicles"] = self.settings.get("Vehicles") or {}` |
| `TWCMaster.py:1526-1529` (chain) | `slaves = self.settings["SlaveTWCs"] = self.settings.get("SlaveTWCs") or {}` / `slaves[twcid] = slaves.get(twcid) or {}`; :1530–1531 then use `slaves[twcid]` |
| `TWCMaster.py:1997-1998` | `self.settings.setdefault("history", [])` |

- [ ] **Step 1: Record BASE.** Run the full suite and confirm 1954 passed, 1 xfailed. Record the lib line count (26,490).
- [ ] **Step 2: Apply Rule A** to every row of the first table. Then `black` on the touched files.
- [ ] **Step 3: Apply Rule B** to every row of the second table. Then `black`.
- [ ] **Step 4: Verify.**
  - an AST scan (as in `scratchpad/find_try.py`): no `try` whose only body is a subscript assign and whose only handler assigns `{}` for `KeyError`, except the three left alone.
  - `git grep -nE 'if not .*\.get\(.*\):$|\.get\(.*None\) == None:$' -- lib` shows none of the listed sites.
  - Full suite → PASS (1954 / 1 xfailed).
- [ ] **Step 5: Commit.** `git commit -m "Read config defaults with .get and create settings nodes in one line"`

---


---

### Task 1: Log what the next analysis needs (expected lib Δ ≈ +18)

This is the first change after Task 0, so the box can collect evidence while the rest lands. Logging only: no decision reads anything added here. Task 3's arrival trigger has its own hook (`Presence.noteObservation`) and never uses this one (F14).

**Changes:**
- `Reconciler.report` (:528–537): log every attempt's outcome at INFO (today DEBUG for aspects): aspect, capability, key, provider, `outcome.kind`, `outcome.detail`. The format is unchanged.
- `TeslaAPI._request` (:306): a request is paid by **provider and endpoint**, never by `purpose` (F14). Paid means the **Fleet** slot (`slot is self.fleetSlot`) and a path ending in `/vehicle_data`, `/wake_up` or `/command/<name>`. The Owner API, `vehicles/{vin}` and the vehicle list are free. After each paid request, one INFO line: `"Tesla %s paid request: %s ($%.3f)"` with the slot's token type, the endpoint type (`vehicle_data`, `wake_up` or `command:<name>`) and the price.
  - It never logs the URL, the VIN or a token.
  - A module-level `_PAID = {"vehicle_data": 0.002, "wake_up": 0.02, "command": 0.001}`.
  - The line is logged after the request whatever its status: an answered 408 is still a request.
- Telemetry: `TeslaMateVehicle` and `FleetTelemetryMQTT` log at INFO when `pluggedIn`, `state` or (TeslaMate) the `geofence` topic changes value for a car: `"%s: %s %s -> %s"`. `geofence` is logged only and is not a registry field. `pluggedIn`/`state` are logged in the shared observe path in `Telemetry.py`, behind a 2-name set; `geofence` is logged in `TeslaMateVehicle`.

**Files:**
- Modify: `Vehicle/Reconcile/Reconciler.py`, `Vehicle/TeslaAPI.py`, `Vehicle/Telemetry.py` (and `TeslaMateVehicle.py` for the geofence topic).
- Test: `tests/unit/test_paid_logging.py` (new).

- [ ] **Step 1: Write the failing tests.**

```python
def test_every_paid_request_logs_one_info_line_without_url_or_token(requests_mock, caplog):
    # Fleet vehicle_data, wake_up and a set_charge_limit command: 3 INFO lines naming
    # "vehicle_data", "wake_up", "command:set_charge_limit"; none contains the VIN, "https://" or the token
def test_free_requests_log_nothing(requests_mock, caplog):       # vehicles list, vehicles/{vin}, and Owner API vehicle_data/wake_up/commands
def test_every_attempt_outcome_is_logged_at_info(caplog):        # reconciler pass with a scripted provider
def test_telemetry_plug_state_and_geofence_changes_log_at_info(caplog):   # repeated same value: one line
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; parity unchanged.
- [ ] **Step 5: Full suite** → PASS. **Commit.** `git commit -m "Log reconciler outcomes, paid Tesla requests and telemetry plug changes at INFO"`


---

### Task 2: Presence from events; one home check (expected lib Δ ≈ −88)

**Events and readings** (`Presence.py`). Every time is a float, and a missing one is `-inf` (F4).

**Events recorded when the observation arrives** (`Presence.noteObservation`):
- **The hook.** `VehicleRegistry.onObserve` is set by the master at startup. `Vehicle.observe` calls it for `pluggedIn`, `chargingState`, `shiftState`, `state`, `lat` and `lon`, after the store and outside the leaf lock, with the incoming observation and the same source's prior value.
- **Storage.** `Vehicle.mark(name, at)` / `markAt(name)`: max-merge under the leaf lock, memory-only. Nothing is evaluated later, so a 20 s drive between two policy passes is still seen.
- **The marks:**
  - `"plugIn"` / `"unplug"` (F1): a plug transition, per source, using the mapped plug value (below):
    - plugged → unplugged marks `"unplug"` at `obs.at`;
    - unplugged or none → plugged marks `"plugIn"`.
    - A first unplugged reading with no plugged one before it marks nothing, so repeated Disconnected reads of a car parked unplugged are not a departure.
    - `Gen2TWC` writes only filtered unplugs (Task 4), so it is always a transition.
    - Car sources count only with the newest fix inside.
  - `"driveStart"`: `shiftState` from P/None to D/R/N, or `state` becoming `"driving"`, with the newest fix not outside.
  - `"driveEnd"`: `shiftState` back to P, or `state` leaving `"driving"`, with the newest fix inside.
  - `"outside"`: a fix outside the radius. Both `lat` and `lon` call the hook, and the test runs only once the other coordinate from the same source is at the same `at` (TeslaMate topics arrive in either order).
  - `"contact"`: `bleReach` True. `"absent"`: `bleReach` False. Both are written only by Task 2's BLE paths.
- **Plug-in arrivals (c):** when `noteObservation` marks `"plugIn"` from a pushed source (`TeslaMateVehicle`, `FleetTelemetryMQTT`) or from `Gen3TWC`, it calls `Targets.onArrival(master, vehicle)`. This is its own hook, not Task 1's logging (F14).

**Plug value mapping** (per source):
- `pluggedIn` as is.
- `chargingState`:
  - `"Disconnected"` → unplugged;
  - `""`, `"Unknown"`, `"SNA"`, `"None"` and `None` → nothing;
  - `_PLUGGED = {"Charging","Starting","Stopped","Complete","NoPower"}` → plugged;
  - HomeAssistant: only `"Charging"`.
- **Narrowing (l)** for car sources: a plugged value is not plug evidence when the same source reports, at or after it, any of:
  - `fastChargerPresent` True, or `fastChargerType` not in `HOME_CHARGER_TYPES = {"ACSingleWireCAN","MCSingleWireCAN","<invalid>",""}`;
  - `connChargeCable` `"<invalid>"` or `""`;
  - `chargerPower` × 1000 > `chargeCurrentRequestMax` × max(`voltage`, 240) × 1.1.

**Current state:**
- `pluggedNow(v)`: the newest plug value across qualifying sources (TWC, `Gen3TWC`, `TeslaBLE`, and car sources with the newest fix inside) is plugged. Ties go to the strong source (`Gen2TWC`/`Gen3TWC`/`TeslaBLE`).
- `drivingNow(v)`: the newest drive reading is `state == "driving"` or `shiftState` in D/R/N.
- `parkedNow(v)`: `shiftState == "P"`. With no `shiftState` ever observed, it is `not drivingNow(v)` (F4).

**`twcVin` (F2)** is home evidence only while all hold:
- the point still reports a plug: Gen2 slave `reportedState != 0x00`, or Gen3 `vehicle_connected`;
- no `"driveStart"` or `"outside"` mark is newer than its observation.

`observeTwcVin(point, vin)` also clears `twcVin` on any other car attributed to that point (`VehicleRegistry.py:201–240`, +3). A pushed unplug or an outside fix makes it stale through the rule above.

**`H` (home time)** = the newest of:
- a valid `twcVin` observation;
- `markAt("plugIn")`;
- `markAt("contact")`;
- the newest fix inside while `parkedNow` (its `at`).

**`M` (movement time)** = max of `markAt("driveStart")`, `markAt("absent")` and `markAt("unplug")`.

**`presence(master, v)`**, computed fresh. The first match wins; **ties fall through to PRESUMED, which means hold** (F8):
1. `v.isAnonymous` → HOME.
2. The newest fix is outside, and its `at > H` → NOT_HOME.
3. `drivingNow(v)` → PRESUMED. Contact proves presence, not parked (F7).
4. `H > M` → HOME. This is the stickiness: plugged-in or asleep cars produce no movement.
5. `markAt("unplug") > H` → NOT_HOME (a confirmed departure).
6. Otherwise PRESUMED.

**Derived values:**
- `leaving(v)` = max(`markAt("unplug")`, `markAt("driveStart")`).
- `arriving(v)` = max(`markAt("outside")`, `markAt("driveEnd")`).
- `pluggedHere(master, v)` = HOME and `pluggedNow(v)`.
- `homeForLimits` = HOME or PRESUMED.
- `inside(master, v)`: None when home or the position is unknown; otherwise BASE's box test at `atHomeRadius` feet (default 1,000).

**BLE presence (F9).** `bleReach` True comes from every successful exchange (the `_noteBleProof` sites `TeslaBLE.py:488, 517, 652`) and from scans. `bleReach` False comes **only** from a scan miss (:1103) or a ping that gets no answer from VCSEC (Task 3). A command or state-read failure never writes it.

**`candidates(master, capability=None)`** is one definition, used by Tasks 3–5 (F13). It returns non-anonymous cars with no valid `twcVin`, sorted by key:
- **Without a capability** (attribution, T12): `homeForLimits` or here, where here is inside or `bleReach` True ≤ 300 s.
- **With a capability** (broadcasts; F11: only cars BASE reached): `order.candidates(v, capability)` non-empty, plus one of:
  - HOME or PRESUMED and attached to TeslaAPI;
  - a `TeslaBLE` claim and `homeForLimits`;
  - HA-attached, HOME, and `master.getTWCbyVIN(v.vin)` (BASE's HA rule).

**Callers after this task:**
- `presentVehicles` uses `homeForLimits`, with BASE's anonymous rule.
- `_chargeTargets` (:202) uses `candidates(master, capability)`.
- `_restoreDeparted`:
  - With `read=True` (the 5/20/45 reads), for a held car with no valid `twcVin`, call `vehicle.read("chargingState", READ_MAX_AGE)`. No wake. The away-car deferral ladder stays (F11), so the count matches BASE.
  - Restore cars that are NOT_HOME (Task 3 adds HOME-unplugged-leaving). The stale guard compares `markAt("unplug")` with `lastWrite("chargeLimit")`, keeping the `<=` comment.
- TeslaAPI:
  - `updateChargeAtHome` reads HOME cars only.
  - The counts use `Presence.homeCars(master, "TeslaAPI")` (HOME or PRESUMED; renamed from `atHome`, F17).
  - `update_vehicle_data` keeps the ladder with `inside(...)` in place of `car.atHome`, and observes `shiftState`.
- HA caches only `battery_level`; its counts go through `homeCars(master, "HomeAssistant")`.
- `TeslaBLE._scheduleBlocksStart` and the `TeslaBLEProvider.startCharging` schedule branch are deleted (F16). `Belief.handsOff` covers them.
- `recordVehicleVIN` calls `Presence.learnHome(self, vehicle)`.
- `HTTPControl.py:558`: `lastAtHome = presence(...) == HOME` (F11).
- `TWCSlave.pluggedCars` is untouched until Task 5.

**New fields:** `shiftState`, `fastChargerPresent`, `fastChargerType`, `connChargeCable`, `chargerPower`, `chargeCurrentRequestMax`, added to `FIELDS` and `CHARGE_FIELDS`. They are mapped from:
- TeslaAPI (`drive_state.shift_state` and `charge_state` keys);
- `TeslaBLE.get_charge_state` (plus `pluggedIn`);
- TeslaMate (`shift_state`, `charger_power`, `charge_current_request_max`).

**Files:**
- Create `Vehicle/Presence.py`.
- Modify:
  - `Vehicle/Registry/Vehicle.py` (`mark`, `markAt`, the observe hook call);
  - `Vehicle/Registry/VehicleRegistry.py` (`onObserve`; `observeTwcVin` clears others);
  - `Vehicle/Registry/Fields.py`, `Vehicle/Providers/Capability.py`;
  - `Vehicle/Reconcile/Targets.py`;
  - `Vehicle/TeslaAPI.py` (:51, :656–711, :1675–1726, :1901–1925, :1961–2008);
  - `Vehicle/HomeAssistant.py` (:68–73, :152–162, :553–593);
  - `Vehicle/TeslaBLE.py` (:177–191, :488/:517/:652, :660–680), `Vehicle/Providers/TeslaBLEProvider.py:95–98`;
  - `Vehicle/TeslaMateVehicle.py`;
  - `TWCMaster.py` (:37, :202, :364–366, :1563–1572, `__init__` hook wiring);
  - `TWCManager.py:386–387`;
  - `Control/HTTPControl.py:558`.
- Tests: `tests/unit/test_presence.py` (new); rewrites per the mapping.

**Interfaces:**
- Produces (`Presence.py`):
  - `HOME`, `PRESUMED`, `NOT_HOME`;
  - `HOME_RADIUS_FT = 1000`, `HOME_FIX_MAX_AGE = 600.0`, `REACH_WINDOW = 300.0`, `HOME_CHARGER_TYPES`, `_PLUGGED`;
  - `noteObservation(master, vehicle, obs, previous) -> None`;
  - `presence(master, vehicle) -> str`;
  - `homeForLimits`, `pluggedHere`, `pluggedNow`, `drivingNow`;
  - `leaving(v) -> float`, `arriving(v) -> float`;
  - `inside(master, v) -> Optional[bool]`;
  - `candidates(master, capability=None) -> List[Vehicle]`;
  - `homeCars(master, attachment) -> List[Tuple[Vehicle, Any]]`;
  - `learnHome(master, vehicle) -> bool`;
  - `why(master, v) -> str` (the deciding event, for logs).
- Also: `Vehicle.mark(name, at)`, `Vehicle.markAt(name) -> float` (-inf when unset), `VehicleRegistry.onObserve`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_presence.py`, a real registry on a test clock, distinct times per event, F8).

```python
def test_nothing_known_is_presumed():
def test_inside_and_parked_is_home_with_no_shift_state_meaning_not_driving():   # F4
def test_driving_inside_is_presumed_even_with_ble_contact():                   # F7
def test_home_is_sticky_while_plugged_or_asleep():                            # 6 h, no movement
def test_repeated_disconnected_reads_are_not_a_departure():                   # F1, Review Focus 5
def test_an_unplug_event_newer_than_home_evidence_is_a_departure():
def test_twc_vin_is_overridden_by_a_newer_drive_start_or_outside_fix():       # F2, Review Focus 3
def test_twc_vin_counts_only_while_the_twc_reports_a_plug():
def test_another_vin_at_the_point_clears_the_old_cars_twc_vin():
def test_marks_record_events_when_observed_not_when_evaluated():             # incl. a 20 s drive with no evaluation between
def test_lat_and_lon_in_either_order_mark_outside_once():
def test_ble_absence_only_from_a_scan_miss_or_unanswered_ping():             # F9: a command failure writes nothing
def test_ties_resolve_to_presumed():                                          # F8
def test_dc_power_above_the_cars_ac_max_is_not_plug_evidence():
def test_a_fast_charger_inside_the_radius_is_not_home():
def test_a_plugged_report_with_no_cable_is_not_home():
def test_charging_state_maps_to_plug_values():
def test_home_radius_defaults_to_1000_ft_and_config_overrides():
def test_candidates_for_a_broadcast_are_only_cars_base_reached():            # F11, incl. HA at home and on a TWC
def test_counts_include_presumed_cars():
def test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix():
def test_update_charge_at_home_reads_only_home_cars(requests_mock):
def test_away_cars_keep_the_status_deferral_ladder():                         # F11
def test_last_at_home_is_true_only_for_home():                                # F11
def test_policy_wide_apply_skips_a_departed_car_on_every_channel(requests_mock):   # R24
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** and delete the retired names.
- [ ] **Step 4: Rewrite the pinned tests** (mapping) → PASS.
- [ ] **Step 5: Parity** → PASS with no edit beyond `:1306`. Row 26: TeslaMate `Complete` with a fix inside → `plugIn` mark → HOME.
- [ ] **Step 6: Grep** `-w` for `located|_present|broadcastVehicles|update_location|locate|is_location_home|is_location_within_radius|vehicleIsDefinitelyHome|atHome|at_home|_scheduleBlocksStart`. Expected hits:
  - docs (Task 6);
  - `numCarsAtHome`/`minBatteryLevelAtHome`;
  - `TWCMaster.py:1167` (the word "locate" in a log string);
  - parity's `install(located=…)` keyword (`:181, 205, 497, 785, 808`; a test parameter, kept).
- [ ] **Step 7: Full suite** → PASS. **Commit.** `git commit -m "Compute presence from plug, drive, position and BLE events; one home check for every module"`

**Test mapping (Task 2):**

| Test | Fate |
|---|---|
| `test_limit_wiring.py::test_present_rule_until_phase_5` | Renamed `test_present_rule`; assertions unchanged (`[VIN, VIN3]`) (PLUMBING-ONLY) |
| `::test_a_fleet_car_that_unplugs_and_leaves_gets_its_normal_limit_back`, `::test_an_unplug_at_home_is_not_a_departure`, `::test_live_telemetry_places_a_departing_car_for_free` | Kept; `atHome` asserts become `presence`; paid lists unchanged |
| `::test_a_restart_with_the_car_plugged_in_and_asleep_still_gets_the_policy_limit` | `presence == HOME` (PLUMBING-ONLY) |
| `::test_a_held_car_with_no_known_position_is_present` | First half kept; second half INTENTIONALLY CHANGED (a): PRESUMED, but no claim → no desire, no request |
| `::test_a_held_car_with_no_position_or_ble_is_present_for_a_cloud_provider` | Second half INTENTIONALLY CHANGED (b); send sequence pinned in Task 3 |
| `::test_a_car_its_twc_names_stays_at_home_whatever_its_stale_fix_says` | Rewritten: `twcVin` with the TWC at 03 and no newer drive start → HOME (no `car.atHome`) |
| `::test_a_listed_car_not_yet_located_is_in_the_broadcast` | On `candidates(m, START_CHARGING)`: listed and unlocated → PRESUMED → in (as BASE); AWAY → out |
| `::test_an_away_fix_older_than_our_last_limit_write_is_no_departure` | On the `unplug`-mark stale guard |
| `test_twcmaster_vin_confirmation.py:205–256` | `test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix` plus a static check that `recordVehicleVIN` calls `learnHome`. INTENTIONALLY CHANGED (f) |
| `test_reads_no_wake.py`, `test_telemetry_registry.py:214–251` | `vehicle.read("lat", 0)` in place of `update_location`; counts unchanged (PLUMBING-ONLY) |
| `test_teslaapi_providers.py`, `test_teslaapi_registry.py` location Mocks; `:308` | `is_location_home` Mocks deleted; `is_far_from_home` Mocks kept (ladder); `atHome` leaves the tuple (PLUMBING-ONLY) |
| `teslatokens.py:146`, `test_teslaapi_wake.py:79` (`car.atHome = True`) | Lines deleted; the car is placed at HOME through `placeAt` (PLUMBING-ONLY) |
| `reconcile_helpers.py:20` | Comment reworded: presence from events |
| `test_registry_callers.py:257–269` | `lastAtHome` True only for HOME (PLUMBING-ONLY) |
| `test_homeassistant_registry.py:96` | Mock removed; HA coordinates |
| `test_charging_reconciler.py:440–452` (`test_an_anonymous_point_reaches_at_home_connected_home_assistant_cars`) | Kept: the HA car is placed HOME instead of `at_home=True`; the audience is unchanged (F11 HA rule) (PLUMBING-ONLY) |
| `test_provider_outcomes_local.py:28` (`_scheduleBlocksStart`) | Re-pointed at `Belief.handsOff`: the same scheduled car gets no start attempt (PLUMBING-ONLY, F16) |

---

### Task 3: One applicability rule per message; the BLE ping; holds; hint endpoints gone (expected lib Δ ≈ +77)

**`Presence.applicable(master, vehicle, attempt) -> str`** returns `SEND`, `NOT_HERE`, `HOLD` or `HOME_NOW`. Stops are never gated.
- **Where it runs:**
  - The reconciler calls it in `beforeWrite` (`Reconciler.py:485`, extended past CHARGE_LIMIT to CHARGING and AMPS), after the attempt's read.
  - For AMPS, which never reads (`maxAge` None), it runs on registry state.
  - For a cloud raise or start, `wakeFirst` runs before the read. The verdict is taken after the wake and read; the wake counts against the paid budget (F3).
- **Inputs:** `plugged` = `pluggedNow(v)` after the read. `L` = `leaving(v)` and `A` = `arriving(v)`, each `-inf` when unset.

**Cells (F4).** Every cell is defined; ties → `HOLD` (F8).

| Message | HOME, plugged | HOME, not plugged | PRESUMED | NOT_HOME |
|---|---|---|---|---|
| start, amps | `SEND` | `NOT_HERE` | plugged → `SEND`; presumed plugged (a held car with no `unplug` mark; F20) → `SEND`; else `HOLD` | `NOT_HERE` |
| apply (non-restore limit) | `SEND` | `L == -inf` (no departure seen) → `SEND`; `A > L` → `SEND`; `L > A` → `NOT_HERE`; tie → `HOLD` | driving → `HOLD`; inside and parked is HOME by now; no usable location → plugged → `SEND`, else `HOLD` (logged once per desire); inside, not driving, not parked, no plug → `HOLD` | `NOT_HERE` |
| restore | `HOME_NOW` (clear the restore desire, `SATISFIED "home"`) | `L > A` → `SEND`; else `HOME_NOW` | `HOLD` | `SEND` |

`NOT_HERE` clears the desire and returns `SATISFIED "not here"`.

**Holds (F3):**
- `HOLD` returns `Outcome(SATISFIED, "held: <why>")` and keeps the desire.
- It sets `rec.heldAt = now` and **not** `settledAt`, so the `settledAt` gate (`Reconciler.py:294–299`) never applies to a held desire.
- `plan` re-plans a held desire only when `vehicle.lastObservedAt > rec.heldAt`, or when the desire changes. `Vehicle.lastObservedAt` is a new float, stamped by every `observe`, `seen=False` included (+2).
- **Paid budget:** any paid wake or paid read made for an attempt that then holds increments `rec.paidSpent`. Paid providers are skipped while `rec.paidSends + rec.paidSpent >= PAID_BUDGET = 4`.
- The "logged once per desire" flag is `rec.heldLogged`.

**Home from BLE (user, 2026-10-18: "BLE contact is definitely home just as TWC plug-in is").** In `noteObservation`'s lat/lon branch, call `learnHome` when the fix's source is `TeslaBLE` as well as when a TWC names the car (one condition). A BLE location read answers only within range, so its fix is home. Test: a BLE-sourced fix with no home set teaches home; a Fleet fix alone does not.

**The BLE ping (send sequence, step 1).**
- `Run.py` calls it before the provider call when the provider is `TeslaBLE`, the attempt is not a stop, and `presence == PRESUMED`.
- `TeslaBLE.ping(vin) -> bool` runs `tesla-control -ble … body-controller-state` through a new seam `_runPing(vin) -> Optional[bool]`, factored from `_fetch_state_json`'s runner.
- An answer observes `bleReach` True. No answer from VCSEC observes `bleReach` False (F9: definitive absence) and returns `Outcome(UNREACHABLE, "no BLE answer")`.
- **Paid path (step 2):** unchanged (F20). `freeFailed` opens it after `PAID_AFTER` of free failures since the first; a missed ping is one free failure.

**Parity harness (F5, PLUMBING-ONLY):** `realBle(m, answers=…, ping=True)` stubs `b._runPing = lambda vin: b.pings.append(vin) or ping`, where `ping` is True, False or a callable. Pings go to `b.pings`, so `b.runs` and `bleCommands` keep today's lists. PRESUMED BLE rows then match today's counts and timings; see "Parity rows traced".

**Restores and applies on the policy pass (E2):**
- `_restoreDeparted` restores held cars that are NOT_HOME, or HOME, not plugged, and `L > A`.
- `applyPolicyLimit` sets the policy desire for every `homeForLimits` car; `applicable` decides at send.
- There is no direct trigger from the unplug. The restore-reply exclusion is not built (F10).

**Arrivals (c):** `Targets.onArrival(master, vehicle)` sets that car's CHARGE_LIMIT desire to `policyLimit` as a decision (else `_restore`), when `presence == HOME`. Exactly one call per plug-in event (F20 dedupe):
- `recordVehicleVIN` (confirmed);
- `noteObservation`'s `"plugIn"` from a pushed source or `Gen3TWC`;
- Task 5's attribution winner. Gen3's rising edge no longer calls it: its `pluggedIn` True goes through `noteObservation`.

**Removed (d):**
- the `checkArrival` handler (`TWCManager.py:323–327`), with `TWCSlave.py:678` now queuing `{"cmd": "checkCharge"}` (F11; the webhook stays);
- `/api/checkArrival` and `/api/checkDeparture` (`HTTPControl.py:775–786`) → 404.

**Endpoints (j):**

    [VehicleEndpoint(v, order, master) for v in registry.vehicles()
     if not v.isAnonymous and pluggedHere(master, v)
     and order.candidates(v, SET_AMPS) and not (unknown and telemetrySaysPlugged(master, v))]

This comes after the unchanged `blind` check. `_telemetryPluggedIn` is replaced by `Presence.telemetrySaysPlugged`, which Task 4 also uses (F16).

**Logging (m):** each non-`SEND` verdict logs at INFO with `why(master, v)`.

**Files:**
- Modify:
  - `Vehicle/Presence.py`;
  - `Vehicle/Reconcile/Reconciler.py` (`beforeWrite`, `plan`, the record fields `heldAt`/`paidSpent`/`heldLogged`, `PAID_BUDGET`);
  - `Vehicle/Reconcile/Desired.py` (the record fields);
  - `Vehicle/Reconcile/Run.py`;
  - `Vehicle/Reconcile/Targets.py`;
  - `Vehicle/TeslaBLE.py` (`ping`, `_runPing`);
  - `Vehicle/Registry/Vehicle.py` (`lastObservedAt`);
  - `TWCMaster.py` (`recordVehicleVIN`);
  - `TWCManager.py:45, 323–327`;
  - `TWCSlave.py:673–679`;
  - `Control/HTTPControl.py:775–786`;
  - `EVSEInstance/VehicleEndpoint.py:164–198`.
- Tests:
  - `test_presence.py`;
  - `test_command_path_parity.py` (the `realBle` ping stub; new rows);
  - `test_limit_wiring.py:44–52`;
  - `test_vehicle_endpoint.py` (the helper `car(m, vin, home=True)`), `test_charging_points.py:116,132`, `test_gen2_idle_minimum.py:38,149,191,236`;
  - `test_telemetry_registry.py:262–266` (`telemetrySaysPlugged`);
  - `tests/integration/test_api_input_validation_extended.py:89–102` (deleted).

**Interfaces:**
- Produces:
  - `Presence.applicable(...) -> str`, `Presence.telemetrySaysPlugged(master, v) -> bool`;
  - `TeslaBLE.ping(vin) -> bool`, `TeslaBLE._runPing(vin) -> Optional[bool]`;
  - `Targets.onArrival(master, vehicle) -> None`;
  - `Vehicle.lastObservedAt: float`;
  - `PAID_BUDGET = 4`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_presence.py
def test_applicability_every_cell():                              # incl. ties -> HOLD and -inf
def test_a_presumed_car_is_pinged_first_and_an_answer_sends_free(requests_mock):
def test_one_missed_ping_does_not_open_the_paid_path(requests_mock):
def test_a_hold_reads_once_and_waits_for_pushed_evidence(requests_mock):     # Review Focus 4; seen=False push re-plans
def test_held_re_plans_stop_paying_after_the_budget(requests_mock):          # F3: <= 4 paid wakes+reads+sends per desire
def test_a_held_desire_is_not_blocked_by_settled_at():
def test_start_and_amps_need_a_plug_here():
def test_a_restores_own_ble_reply_re_applies_nothing():                       # L > A stands after contact
def test_a_plug_or_a_newer_arrival_cancels_a_pending_restore():
def test_arrival_is_one_decision_for_the_plugged_car_only():                 # (c), once per event
def test_power_start_still_queues_check_charge():                             # F11
def test_endpoints_list_cars_plugged_here_whatever_module_knows_them():      # (j)
def test_anonymous_00_edge_car_is_never_also_an_endpoint():                   # E3

# test_command_path_parity.py — new rows; each comment states its paid tuple
def test_box_2026_10_18_arrival_while_driving_sends_nothing_until_parked_then_ble_free(requests_mock):
    # NOT_HOME; 15:18 TeslaMate fix inside + state driving -> PRESUMED/HOLD (pings allowed, no command, no HTTP);
    # 15:21 state online + shift P -> HOME, A > L -> BLE charging-set-limit; paid == (0, 0, 0)
def test_ble_contact_while_driving_still_holds(requests_mock):               # F7
def test_arrive_park_ble_sets_the_limit_before_the_plug(requests_mock):      # (k)
def test_a_20_s_drive_inside_the_radius_between_policy_passes_is_seen(requests_mock):
    # HOME unplugged after an unplug at t0; pushed shift D at t+5, P at t+25 (inside); policy pass at t+30:
    # driveEnd t+25 > leaving -> apply over BLE; paid 0
def test_arrive_limit_set_then_shift_to_d_in_the_driveway_restores_over_ble(requests_mock):   # no Fleet request
def test_a_car_that_never_left_unplugged_for_hours_is_not_re_applied(requests_mock)
def test_leave_without_plugging_is_restored_by_fleet_once_the_fix_is_outside(requests_mock)  # 1 command, no wake
def test_presumed_fleet_only_car_gets_the_limit_through_the_paid_sequence(requests_mock)       # (b): states its tuple
def test_presumed_fleet_only_car_read_outside_is_sent_nothing(requests_mock)
def test_unplug_restores_over_ble_at_once(requests_mock)                      # scenario 7
def test_ble_gone_five_minutes_then_one_remote_restore(requests_mock)
def test_ble_only_departure_never_pays(requests_mock)
def test_replug_before_the_remote_restore_sends_none(requests_mock)          # scenario 8
def test_fleet_only_unplug_one_remote_restore_plug_one_remote_apply(requests_mock)   # scenario 17
def test_fleet_only_failed_remote_restore_is_retried_per_restore_retry(requests_mock)  # scenario 18 (Q8)
def test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing(requests_mock)   # scenario 1
def test_departing_car_is_never_presumed_present(requests_mock)               # scenario 19
def test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it(requests_mock)    # 9
def test_startup_wake_finds_the_car_unplugged_and_sends_nothing(requests_mock)   # 10
def test_startup_wake_finds_the_car_plugged_and_starts_charging(requests_mock)   # 11
def test_ble_silent_umc_car_with_telemetry_inside_radius_is_home(requests_mock)  # 13
def test_ble_plus_fleet_car_leaving_a_umc_is_restored_after_the_departure_read(requests_mock)
def test_2026_10_12_return_plugged_in_keeps_the_policy_limit(requests_mock)       # only if no row covers it
def test_2026_10_12_arrival_during_a_running_restore_ends_at_the_policy_limit(requests_mock)
def test_wake_only_a_home_car(requests_mock)                                   # x4
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `test_presence.py test_command_path_parity.py test_vehicle_endpoint.py test_charging_points.py test_gen2_idle_minimum.py test_limit_wiring.py test_telemetry_registry.py` → PASS. **No existing parity count or timing moves.** If one does, stop and report it with old, new and why.
- [ ] **Step 5: Grep** `checkArrival|_telemetryPluggedIn` → none. **Step 6: Full suite** → PASS. **Commit.** `git commit -m "One applicability rule per message; BLE ping for a presumed car; holds wait for evidence within the paid budget"`

**Test mapping (Task 3):**
- `test_periodic_reenforce_does_not_undo_an_adopted_limit`: `onArrival(m, v)` (PLUMBING-ONLY).
- The endpoint tests: attachments become HOME-plugged evidence (PLUMBING-ONLY).
- `test_telemetry_registry.py:262–266`: `telemetrySaysPlugged` (PLUMBING-ONLY).
- The two integration tests: INTENTIONALLY CHANGED (d).

---

### Cleanup and rebuild order (user, 2026-10-19)

The design audit (`sdd/2026-10-18-vehicle-model-phase5-presence/audit-report.md`) found Phase 5 heading to about +170 against its base. The order is now:
1. **X1–X4:** the audit's Tier A cuts (A1; A2+A4+A10; A3; A7–A9).
2. **Tasks 4–6, built per audit §4:**
   - Task 4 ≤ +10;
   - Task 5 is a filter over `candidates()` instead of porting PresenceAttribution verbatim, with a net of −17 or better;
   - Task 6 nets 0 or less, and takes A5.
3. **X5:** Tier B imports and Tier C comments.
4. **Task 7:** docs.

**Target:** Phase 5 ends at 26,140 lines or fewer.

### Task 4: The Gen2 unplug rule with two filters, on `TWCSlave` (expected lib Δ ≈ +41)

```python
# TWCSlave class constants (evidence: phase5-unplug-evidence.md)
UNPLUG_DEBOUNCE = 60     # s of steady 00
PLUGGED_RUN = 60         # s of non-00 immediately before the 00 began
LINK_GRACE = 300         # s after the first heartbeat following a (re)link
```

**`TWCSlave.unplugStep(now) -> bool`** reads `reportedState` and `reportedAmpsMax`, and is True once per qualifying 00 run. Serial thread, no I/O.
- **Base rule:** the 00 held `UNPLUG_DEBOUNCE`, began after a non-00 run ≥ `PLUGGED_RUN`, and began ≥ `LINK_GRACE` after the link. `TWCSlave.linkReady()` re-arms the grace.
- **Filter (a), strict (F6):** `_beforeMax` is the slave's `reportedAmpsMax` on the last non-00 heartbeat. The run qualifies only if `_beforeMax > 0` and `reportedAmpsMax == 0` on the **first** 00 heartbeat.
  - An idle car already at 0 A never gives a TWC unplug; only telemetry can depart it.
  - Use the slave's field, never the master heartbeat's.
  - Log at INFO at every onset: `"TWC %s: 00 onset, max %.2f A before, %.2f A now"`, and the run's verdict.

**On True,** `TWCMaster._unplugged(slave)` runs on the serial thread with no I/O:
- **Filter (b):** `Presence.telemetrySaysPlugged(master, v)` (Task 3) → write nothing; log the veto.
- Otherwise `observe("pluggedIn", False, "Gen2TWC")`, which marks `"unplug"` (Task 2), on:
  - `v = registry.vehicleAt(twcid)` (a VIN car), or else
  - the single `candidates(master)` car (T12).
- Then `registry.endPlugSession(twcid)` (g).

**Q2:** delete `_plugSession(slaveTWC, False)` at charge stop (`TWCMaster.py:1340`). `recordVehicleSessionEnd`, `plugSessions += 1`, `lastVIN = currentVIN` and the VIN-query reset stay. The anonymous close at 00 (:1354–1356) stays.

**`Gen2TWC.vehicleKey`:** the `lastVIN` branch (:49–51) → `v = reg.vehicleAt(self.twcid)`; `return v.key if v else None`. F2 bounds the `twcVin` it relies on.

**The loop property** (Review Focus 1):
- Filter (a) is strict, and filter (b) vetoes.
- A restore never wakes.
- An arrival raise after a TWC 00 can only follow a real TWC unplug, which requires the max-amps drop.

**Files:**
- Create `tests/unit/test_gen2_unplug.py` (the rule through a real `Gen2TWC`).
- Modify:
  - `TWCSlave.py` (constants, `unplugStep`, `linkReady`, state in `__init__`, the call in `receive_slave_heartbeat`);
  - `TWCMaster.py` (:1340, `_unplugged`);
  - `EVSEInstance/Gen2TWC.py:37–52`;
  - `TWCManager.py` (linkready → `slaveTWC.linkReady()`).
- Tests: `test_registry_plug_sessions.py`, `test_gen2twc_provider.py`, `test_outcome_desired.py`, the lift tests in `test_amps_reconciler.py`, and `test_twcmaster_vin_confirmation.py` where they expect `twcVin` cleared at charge stop (F17).

**Interfaces:**
- Produces: `TWCSlave.unplugStep(now) -> bool`, `TWCSlave.linkReady()`, `TWCMaster._unplugged(slave) -> None`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_gen2_unplug.py
def test_00_with_the_max_amps_drop_after_a_plugged_run_is_one_unplug():
def test_00_without_the_drop_on_the_first_00_heartbeat_is_never_an_unplug():   # 47 A; and a drop on the 2nd heartbeat
def test_an_idle_car_already_at_0_a_never_gives_a_twc_unplug():                 # F6
def test_00_inside_link_grace_or_without_a_plugged_run_is_never_an_unplug():
def test_onset_logs_the_slave_max_amps(caplog):
def test_reported_once_per_00_run():
# test_presence.py (real master, drive())
def test_live_telemetry_plugged_vetoes_a_twc_unplug():
def test_charge_stop_keeps_twc_vin_until_the_unplug():                          # (g)
def test_vehicle_key_names_the_car_after_a_charge_stop_and_nobody_after_an_unplug():   # E5
def test_a_vinless_unplug_departs_the_only_candidate():                          # T12
def test_a_non_tesla_plug_departs_nobody():
def test_restart_steady_00_with_telemetry_plugged_is_home_and_restores_nothing():
# test_command_path_parity.py
def test_box_2026_10_18_departure_restores_over_ble_within_a_minute(requests_mock):
    # 13:08: VIN TWC at 03 with max 32 A, held (90, 50), BLE claimed, Fleet asleep, no telemetry; 00 with max 0.00 A on the
    # first 00; policy passes every 30 s: BLE charging-set-limit 90 at <= onset + 120 s; no wake; paid == (0, 0, 0); no re-apply
def test_box_2026_10_18_false_00_at_47_a_with_telemetry_plugged_is_no_departure(requests_mock):
    # 15:25:58-15:36:27: 00 at 47 A, TeslaMate live plugged_in true: no unplug mark, HOME, no command, paid 0
def test_box_2026_10_17_morning_wake_episodes_declare_no_departure(requests_mock):   # the 07:58:28-08:39:01 run table
def test_a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore(requests_mock):
    # 3 cycles 03 -> 00 (real drop) -> 03, BLE answers None while asleep, Fleet asleep: no wake on any channel; paid[1] == 0
def test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise(requests_mock):   # F6
    # car at 03 with max 0 A (offer 0), policy limit above the car's limit, no telemetry: 3 cycles 03 -> 00 -> 03:
    # no unplug, no attribution arrival, no BLE wake, paid 0
def test_no_gps_source_plug_unplug_cycle_end_to_end(requests_mock)            # scenario 15
def test_gen2_steady_00_after_link_does_not_block_startup_charging(requests_mock)   # scenario 12
def test_plug_in_on_a_vin_twc_comes_home_with_one_apply(requests_mock)             # scenario 2
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `test_gen2_unplug.py test_presence.py test_registry_plug_sessions.py test_gen2twc_provider.py test_outcome_desired.py test_amps_reconciler.py test_command_path_parity.py` → PASS. No existing parity count moves.
- [ ] **Step 5: Full suite** → PASS. **Commit.** `git commit -m "Gen2 unplug: a debounced 00 whose first heartbeat drops the slave's max amps from above 0 to 0, unless live telemetry says plugged in"`

**Test mapping (Task 4):**
- `twcVin` cleared at charge stop (`test_registry_plug_sessions.py`, `test_gen2twc_provider.py`, `test_outcome_desired.py`, lift tests): INTENTIONALLY CHANGED (g), replaced by `test_charge_stop_keeps_twc_vin_until_the_unplug`.
- `vehicleKey == lastVIN` while plugged: rewritten on a confirmed `twcVin` (PLUMBING-ONLY).

---

### Task 5: One attribution for VIN-less plugs; the fan-out over candidates (expected lib Δ ≈ +50)

**Ported verbatim** from `presence/3-plug-presence:lib/TWCManager/PresenceAttribution.py` (71 lines with comments) into `Presence.py`: `pickPluggedCar`, `Candidate` (with `fastChargerPresent`) and `PILOT_MATCH_TOLERANCE`.

**`Presence.attribute(master, pointId, offeredAmps, actualAmps, read=True) -> Optional[str]`:**
1. **BASE's single-car guess, decisive (F12):** if exactly one non-anonymous car without a valid `twcVin`, not NOT_HOME, has a plugged reading within `PLUGGED_JUST_NOW = 120` s (any source), it wins. That is BASE's `_correlate`, with the away test now `presence != NOT_HOME`.
2. Otherwise `pool = candidates(master)` (Task 2's one definition).
3. When `read`, for each `TeslaBLE`-claimed pool car: `v.read("availableCurrent", READ_MAX_AGE, providers=[local providers only])`. Never a wake, never TeslaAPI.
4. Build each `Candidate` from the registry:
   - `reach`, `inside`;
   - `pluggedIn`: False when NOT_HOME, else the `TeslaBLE` value ≤ 300 s old, else None;
   - `pilot`/`actual`/`fastCharger*`: `TeslaBLE` values ≤ 300 s old.
5. `pickPluggedCar`. A winner (from step 1 or step 5) → `registry.observeTwcVin(pointId, vin)` → `Targets.onArrival(master, winner)` (the one arrival for this plug-in). Ambiguity logs at INFO once per plug session.

**Callers:**
- Gen2: `_plugSession(slave, True)` queues `{"cmd": "attributePlug", …}`, deduped per point.
- Gen3: `_correlate`'s guess (:275–297) → `attribute(...)`. The cloud-VIN half is unchanged.
- Fan-out (h): `anonymousCars = [v for v in candidates(master, SET_AMPS) if pluggedHere(master, v)]`.
- The 00 session open (:1346) uses `pluggedHere` over `candidates`.
- `TWCSlave.pluggedCars` goes.

**Files:**
- Modify: `Vehicle/Presence.py`; `TWCMaster.py` (`_plugSession`, `_taskKey`, :1346); `TWCManager.py` (handler); `EVSEInstance/Gen3TWC.py:68, 239–297`; `EVSEInstance/ChargingPoint.py:182–190`; `TWCSlave.py:7–16, 121–141`.
- Tests:
  - `test_presence_attribution.py` (10 ported, only the import changes);
  - `test_presence.py`;
  - `test_amps_reconciler.py:8,157–187`;
  - the Gen3 `_correlate` tests: `test_charging_points.py` (2), `test_gen3twc_provider.py`, `test_vehicle_endpoint.py` (F17);
  - parity.

**Interfaces:**
- Produces: `Presence.Candidate`, `pickPluggedCar(...)`, `PILOT_MATCH_TOLERANCE = 1`, `PLUGGED_JUST_NOW = 120.0`, `attribute(...) -> Optional[str]`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_attribution_reads_only_local_providers(requests_mock):
def test_gen3_single_car_plugged_within_120_s_is_still_guessed_without_home_or_ble():   # F12
def test_a_single_candidate_inside_is_attributed_merges_the_session_and_arrives_once():
def test_two_candidates_attributed_by_ble_pilot():
def test_gen3_cloud_vin_still_corrects_a_guess():
def test_vin_less_single_candidate_plug_one_apply(requests_mock)             # scenario 3
def test_vin_less_two_candidates_ble_pilot_one_apply(requests_mock)          # scenario 4
def test_vinless_ambiguous_plug_rates_nobody_and_logs_once(requests_mock, caplog)   # scenario 5
def test_vinless_rate_never_falls_back_to_vehicles_0(requests_mock)          # (h)
def test_supercharger_telemetry_plugged_is_not_home(requests_mock)           # scenario 6
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (row 25 unchanged).
- [ ] **Step 5: Grep** `pluggedCars|CORRELATE_WINDOW|_PLUGGED` → hits only in `Presence.py`. **Step 6: Full suite** → PASS. **Commit.** `git commit -m "Attribute a VIN-less plug with one picker for Gen2 and Gen3; fan out only to cars plugged in here"`

**Test mapping (Task 5):**
- `test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0`: INTENTIONALLY CHANGED (h).
- The Gen3 `_correlate` tests: rewritten through `attribute` (PLUMBING-ONLY; F12 keeps their outcomes).

---

### Task 6: Vehicles page: presence and pending commands (expected lib Δ ≈ +40)

User, 2026-10-18: fold presence into the Vehicles page; of the spec's per-car diagnostics, show only pending commands — what is in flight and/or why it is not being sent. The merged field view and per-provider panels are dropped from the spec.

- **List page** (`vehicles.html.j2`): a **Presence** column from `Presence.presence(v)` at render: HOME → "Home", PRESUMED → "Probably home", NOT_HOME → "Away".
- **Per-car page** (`vehicleDetail.html.j2`): a **Pending commands** section, one row per open desire in the reconciler's `DesiredStore` for that VIN (none → "Nothing pending"):
  - what: the aspect and desired value in words ("Charge limit → 50%", "Charging → start", "Charge rate → 16 A");
  - state, first that applies:
    - in flight (`rec.inFlight`): "Sending via <source name> (<age>)";
    - held (`rec.heldAt` set, last outcome `held: <why>`): "Waiting: <why>";
    - backing off / waiting for a free channel / paid budget spent / no provider can command: the reason the reconciler already computes for its log lines (`_whyNoWake`, the `excluded` map, `paidRetryDue`), in words, with when it retries if known;
    - otherwise the last outcome and its age ("Last try via BLE: unreachable, 2 min ago").
- One helper `pendingCommands(master, vin) -> list[dict]` in `HTTPControl.py` next to `providerLines`, reading registry/reconciler state under their locks at render; no HTTP, no reads, no new provider work. Source names through the existing `sourceName` mapping.
- Tests: `tests/unit/test_vehicles_page.py` rows: presence column for each state; pending section for in-flight, held, excluded/backoff, last-outcome, and empty.

### Task 7: Docs, changelog, PR notes; whole-branch check (expected lib Δ 0)

- [ ] **Step 1: Docs (F17).**
  - `docs/PolicyCustomization.md:49–80`: the at-home rules and first-fix seeding.
  - `PolicyCustomization.md:226–228, 277`: the counts.
  - `docs/Settings.md:14`: home is set from a car at a VIN-reporting TWC, or here.
  - `docs/modules/Vehicle_HomeAssistant.md:88–93`.
- [ ] **Step 2: CHANGELOG.** The radius default; how home is set; the removed hint endpoints; the Gen2 plug-session end; the new INFO lines.
- [ ] **Step 3: PR notes:** (a)–(m), one sentence each.
  - Call out (d): the 5/20/45 reads stay.
  - Call out (h): the reversed Phase 3 ruling.
  - Call out (b): presumed cars resolved on the paid path, close to main.
  - Call out the Gen2 filters: the evidence and its n=2 caveat.
- [ ] **Step 4: Whole-branch checks.**
  - Run every grep and the full suite.
  - `git diff 57dcea94 -- tests/unit/test_command_path_parity.py` shows only new rows, `:1306` and the `realBle` ping stub.
  - Record the lib total.
- [ ] **Step 5: Commit.** `git commit -m "Document event-based presence"`

**Per-group fates of the presence-branch tests (F18):**

| Branch file / group | Fate |
|---|---|
| `test_plug_presence_scenarios.py` (19) | All ported as parity rows (Tasks 3–5) |
| `test_presence_attribution.py` (10) | Ported as is (Task 5) |
| `test_vehicle_presence.py` TestStates 6, TestPlugEvidence 15, TestLocation 2, TestRecords 1, TestHomeProof 1 | → `test_presence.py` Task 2 rows (states, plug mapping, radius, marks, `twcVin`) |
| TestProbes 2 | → `test_a_presumed_car_is_pinged_first…` and `test_driving_inside_is_presumed_even_with_ble_contact` |
| TestVinLessAttribution 10 | → Task 5 rows (single, pilot, ambiguous, T12 only-candidate, non-Tesla) |
| TestDepartingRestore 3, TestRemoteRestoreBackoff 2 | → parity `test_unplug_restores_over_ble_at_once`, `test_ble_gone_five_minutes…`, `test_ble_only_departure_never_pays`, `test_fleet_only_failed_remote_restore…` |
| TestReturnPluggedIn 2, TestDepartAndReturn 1 | → `test_2026_10_12_*`, `test_a_plug_or_a_newer_arrival_cancels…` |
| TestDiscoveryWithAHeldLimit 2, TestDiscover 3, TestDiscoverEvidenceOrder 2 | → `test_applicability_every_cell` and the startup parity rows 9–11 |
| TestHeldWhileNotHome 3 | → `test_policy_wide_apply_skips_a_departed_car…` and the vanished-car rows (kept) |
| TestWeakPlugMaxAge 3 | **Dropped**: superseded by stickiness (final model); `test_home_is_sticky_while_plugged_or_asleep` |
| TestBroadcastVINs 4 | → `test_candidates_for_a_broadcast_are_only_cars_base_reached` |
| `test_teslaapi_presence.py`: DiscoveryOnWake 5, DiscoveryEvidenceOrder 2 | → the startup rows and `test_presumed_fleet_only_car_*` |
| ChargeTargets 4 | → `test_start_and_amps_need_a_plug_here` |
| ReconcileHomeLocation 2 | → `test_home_is_learned_only_from_a_twc_named_car…` (Q5) |
| CountsFollowPresence 3, HomeRadius 2 | → `test_counts_include_presumed_cars`, `test_home_radius…` |
| WakeOnlyForAHomeCar 4 | → `test_wake_only_a_home_car` (x4) |
| AtHomeFollowsPresence 3 | → `test_last_at_home_is_true_only_for_home` |
| `test_teslable_presence.py`: ContactReporting 2 | → `test_ble_absence_only_from…` |
| SkipsAwayVehicles 2, ChargeTargets 3 | → `test_applicability_every_cell` |
| plug derivation 2 | → `test_charging_state_maps_to_plug_values` |
| DiscoveryOnWake 5 | → startup rows |
| every-channel departing regression 1 | → `test_policy_wide_apply_skips…` |
| `test_twcslave.py`: TestPlugDebounce 9, TestUnplugNeedsAPluggedRun 7 | → `test_gen2_unplug.py` |
| TestPlugVIN 5 | `plugEnded` cases dropped (`vehicleAt` replaces `plugVIN`); non-Tesla → `test_a_non_tesla_plug_departs_nobody`; stale `lastVIN` → `test_vehicle_key_names_the_car_after…` |
| TestPresenceTriggers 2 | → `test_power_start_still_queues_check_charge` and the 5/20/45 reads (kept) |
| TestChargeVIN 3 | → `vehicleKey` tests (Task 4) |
| `test_presence_handlers.py` 3 | → `test_arrival_is_one_decision…`, `test_ble_only_departure_never_pays`, the departing-with-nothing-held case in `test_applicability_every_cell` |
| `test_presence_sources.py` 7 | → Task 2 mapping, radius and plug-with-fix rows |
| `test_homeassistant_presence.py` 5 | → `test_policy_wide_apply_skips…`, the HA-coordinates rows, `test_counts_include_presumed_cars`, `test_home_radius…` (default and override) |
| `test_teslaapi_controller_presence.py` 1, `test_teslaapi_controller.py` 2 | → `test_endpoints_list_cars_plugged_here…` and E3 |
| `test_twcmaster.py` 2 | → `test_charge_stop_keeps_twc_vin…`; the per-VIN cancel already exists |
| TeslaMate/telemetry 2 | → `test_charging_state_maps_to_plug_values` (odd payload is unknown) and `test_marks_record_events_when_observed…` (a retained value is a read, not an event when unchanged) |

---

## Parity rows traced (F4), under the Task 2/3 definitions

| Row | Car evidence | Presence → cell | Count/timing |
|---|---|---|---|
| 2 `test_ble_only_limits_never_wake_to_lower` | fix inside, no `shiftState`, no driving | HOME (inside and parked), not plugged, `L == -inf` → apply `SEND`; HOME, so no ping | unchanged |
| 4 `test_fleet_only_raise_costs_the_same` | fix inside; Fleet asleep | HOME, `L == -inf` → wake (a raise, `allowWake`) → read (Stopped, inside) → `SEND` | (1,1,1) unchanged |
| 5 `test_ble_plus_fleet_waits_five_minutes` | fix inside; BLE answers None | HOME → BLE ×2 fail (command failures write no `bleReach`, F9) → paid after `PAID_AFTER` | (0,0,1); `len(b.runs) == 2`; timing unchanged |
| 6 `test_ble_plus_fleet_stop_waits_a_minute` | stop | never gated | unchanged |
| 17a/b vanished car | fix outside newer than H | NOT_HOME → restore `SEND` | unchanged |
| 25 `test_vinless_rate_goes_to_the_plugged_in_car_only` | VIN Disconnected (no prior plugged: no unplug mark), VIN2 Charging | VIN HOME not plugged (not in the fan-out); VIN2 `pluggedHere` | `[VIN2]`, `[10]` unchanged |
| 26 restart, asleep | TeslaMate Complete, fix inside | `plugIn` → HOME plugged | BLE run list unchanged; 0 requests |
| pure Gen2 (:496) | no attachments | broadcast audience empty (F11) | unchanged |
| `test_anonymous_stop_fans_out_as_main` | two Fleet cars Charging inside | HOME plugged; broadcast reaches both (TeslaAPI-attached) | unchanged |
| mode-2 rows (`onTwc`) | `twcVin` with the TWC at 0x00 in setup → `twcVin` not counted (F2); fix inside → HOME | start needs plugged: TeslaMate Charging inside | unchanged |

**No existing row is expected to move.**

---

## Line budget

| Task | Out | In | Expected Δ (range) | Running total |
|---|---|---|---|---|
| 0 config one-liners | 53 blocks, 17 if-pairs | (black re-wraps ≥ 6) | **≈ −164** (−160..−168) | ≈ 26,326 |
| 1 logging | — | paid classifier + line 10, telemetry log 6, report level 1 | **≈ +18** (+15..+22) | ≈ 26,344 |
| 2 presence from events | TeslaAPI home/radius 56, `vehicleIsDefinitelyHome` 36, `update_location`/`locate` 25, `atHome` 3, helpers 25, HA 52, Targets presence half 66, `_scheduleBlocksStart` + provider branch 19 (≈ 282) | `Presence.py` ≈ 125 (`noteObservation` + marks 30, mapping/narrowing 18, current state 12, `presence` 12, `twcVin` bound 6, `leaving`/`arriving` 4, `inside` 10, `candidates` 14, `homeCars`/`learnHome` 14, `why` 5), `Vehicle` mark/hook 9, registry hook + `observeTwcVin` clear 4, fields + mappings ≈ 21, Targets filters ≈ 15, delegations + ladder on `inside` ≈ 20 | **≈ −88** (−70..−110) | ≈ 26,256 |
| 3 applicability; ping; holds; hints gone | HTTP hints 12, `checkArrival` 5, endpoint gate 5, `_telemetryPluggedIn` 5 | `applicable` 32, `ping` + `_runPing` 14, `Run.py` 6, `beforeWrite` past limits 8, hold + budget + `settledAt` 14, record fields 4, `lastObservedAt` 2, `_restoreDeparted`/`applyPolicyLimit` 6, `onArrival` + calls 8, `telemetrySaysPlugged` 5, logs 4, `checkCharge` 1 | **≈ +77** (+65..+90) | ≈ 26,333 |
| 4 Gen2 unplug (on `TWCSlave`) | charge-stop end 1, `vehicleKey` branch 3 | `unplugStep`/`linkReady` + constants ≈ 30, `_unplugged` + T12 ≈ 12, wiring 3 | **≈ +41** (+35..+50) | ≈ 26,374 |
| 5 attribution; fan-out | `pluggedCars` + imports 26, `anonymousCars` 6, Gen3 loop 22, `CORRELATE_WINDOW` 2 | verbatim module 71, single-car guess 8, `attribute` 22, task/queue 6 | **≈ +51** (+45..+60) | ≈ 26,425 |
| 6 docs | — | — | 0 | **≈ 26,425** |

- **Projected end ≈ 26,425** (range ≈ 26,330–26,520): ≈ −65 from BASE. Task 0 is −164, logging +18, and **the presence work (Tasks 2–5) nets ≈ +81**.
- The pre-flight estimated 26,380–26,410. This is higher because of the F11 keeps (the deferral ladder, broadcast audience and HA rule stay), the F2/F3 bounds, and filling every cell. The F16 deletions take back ≈ 24.
- **The gap to main is ≈ 3,245 lines.** Biggest contributors: `Vehicle/Reconcile/` +1,946 (+30 here), `Vehicle/Providers/` +1,346, `Vehicle/Registry/` +870 (+15 here), `HTTPControl.py` +213, `ChargingPoint.py` +211, `VehicleEndpoint.py` +198, `Gen3TWCs.py` +157, `Telemetry.py` +137, `Gen3TWC.py` +124, `TWCMaster.py` +118, `VehicleCommandQueue.py` +96, `TeslaMateVehicle.py` +90, `ControlTick.py` +75, `TeslaTokenSlot.py` +74, and `Presence.py` ≈ +225 after this phase.
- Per the roadmap, still above 23,180 means: stop and audit the design (Reconcile, Providers, Registry first) before Phase 6.

## Decisions made in this plan

1. **Presence from events, computed fresh.** The only remembered data is event times (marks), recorded when the observation arrives. Event times beat readings: a repeated Disconnected read is not a departure (F1).
2. **`twcVin` is bounded** (F2): valid only while the point reports a plug, and not after a newer drive start or outside fix. Another VIN at the point clears it.
3. **Holds re-plan on any newer observation, within a paid budget of 4 per desire** (F3). `heldAt` is separate from `settledAt`.
4. **Ties hold** (F8); missing times are `-inf`; no `shiftState` means parked unless driving (F4). Contact never overrides driving (F7).
5. **`bleReach` False only from definitive absence** (F9).
6. **Restores and applies ride the policy pass** (E2), and nothing excludes the restore's own reply (F10).
7. **BASE kept where F11 lists it:** the ladder, `updateChargeAtHome` at power start, the broadcast audience and HA rule, `lastAtHome` for HOME only. Q7's single deferral is withdrawn.
8. **One `candidates()`** (F13). **One arrival per plug-in event** (F20). **One telemetry-plugged predicate** (F16).
9. **BASE Gen3's single-car guess stays decisive** (F12).
10. **The Gen2 rule lives on `TWCSlave` with a strict filter (a)** (F6).
11. **The paid path is BASE's rule** (F20), and held ⇒ presumed plugged for starts (F20).
12. **Task 0 uses `d.get(k) or {}` at the falsy/`None` tests**, which is exact for JSON `null`.

## Pending user decisions

None. All pre-flight findings are applied per the rulings in `sdd/2026-10-18-vehicle-model-phase5-presence/progress.md`.

## Self-review (against 57dcea94)

- **Symbols and hooks.** Every symbol planned for deletion or kept exists at the cited lines.
  - Hooks:
    - `Reconciler.report` :523–537, `beforeWrite` :485, the `settledAt` gate :294–299, `freeFailed` :323–328;
    - `Run.py` `wakeFirst`;
    - `Belief.allowWake` :107–117, `Belief.handsOff` :99–103;
    - `TeslaAPI._request` :306, `is_awake` :1794;
    - `TeslaBLE._fetch_state_json` :613 (the ping seam), scan :1103;
    - `FieldStore._store` (returns the kept observation);
    - `Telemetry.py:277` (`seen=False`, hence `lastObservedAt`).
- **Pre-flight F1–F20**, each applied:
  - F1 unplug event mark;
  - F2 the `twcVin` bound and clear;
  - F3 holds and budget;
  - F4 cells, `-inf`, parked;
  - F5 the ping stub;
  - F6 strict filter (a) and the raise-loop row;
  - F7 driving holds;
  - F8 ties;
  - F9 `bleReach` sources;
  - F10 no exclusion;
  - F11 BASE kept;
  - F12 Gen3 guess;
  - F13 one `candidates`;
  - F14 the paid classifier and a separate arrival hook;
  - F15 deltas;
  - F16 the three deletions;
  - F17 rename, mapping and docs;
  - F18 per-group fates;
  - F19 Task 0;
  - F20 the paid rule, held ⇒ plugged, and one arrival.
- **User decisions:** Q1–Q9, the final model, E1/E2 and the paid fallback are all mapped in Global Constraints and Tasks 2–4.
- **Box rows:** 13:08, 15:18 → 15:21, 15:25:58–15:36:27, the 07:58–08:40 sequence, the 20 s drive and the loop rows (lowering and raise).
- **Interfaces line up:**
  - `noteObservation`, `presence`, `pluggedNow`, `drivingNow`, `leaving`, `arriving`, `candidates`, `homeCars` and `why` are defined in Task 2.
  - `applicable`, `telemetrySaysPlugged`, `ping`, `onArrival` and `lastObservedAt` are defined in Task 3.
  - `unplugStep`/`_unplugged` are in Task 4. `attribute` is in Task 5 and calls `onArrival` once.
