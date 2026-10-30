# Task 0 report
Status: DONE. Commit: see `git log` on vehicle-model/phase5 (message "Read config defaults with .get and create settings nodes in one line").

Rule A: 53 blocks converted (50 via regex, plus Kostal split into two lines, TeslaBLE `self.config = self.master.config`, Telemetry:61, Sentry configLogging by hand). Per file: two sites each in HTTPControl, MQTTControl, WebIPCControl, DSMRreader, Efergy, EmonCMS, Enphase, Fronius, HASS (EMS), IotaWatt, MQTT (EMS), OpenHab, OpenWeatherMap, SolarEdge, TED, URL, CSV/Console/File/MySQL/SQLite/Sentry logging, aWATTarPricing, HASSStatus; one each in Victron, Kostal (one try, two lines out), MQTTStatus, Telemetry, TeslaBLE.
Kostal: at BASE a missing "config" also blanked configKostal; now configKostal keeps a present sources.Kostal. master.config always has "config" (loaded before any module), so it never arises.
Rule B: HTTPControl 8 sites (consumptionOffset x2, Schedule, day, match day, Settings, Graphs), mute x4 logging files, TWCMaster 5 (VehicleGroups, Vehicles x2, SlaveTWCs chain with slaves[twcid] on the two following lines, history setdefault).
Skipped: none. Left alone per brief: Telemetry:65-69, TWCManager.py newSlave sites, TeslaAPI TypeError site.
Tests: full suite 1954 passed, 1 xfailed. AST scan finds no remaining try/KeyError-{} blocks; grep shows none of the listed sites.
Lib lines: 26,490 -> 26,320 (-170; expected -160..-168, 2 lower than range: more deletions, not growth). Shortstat: 30 files, 88 insertions, 258 deletions.
