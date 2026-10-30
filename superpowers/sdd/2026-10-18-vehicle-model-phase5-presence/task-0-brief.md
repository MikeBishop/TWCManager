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

