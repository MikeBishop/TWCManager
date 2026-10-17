# Task 6 report
Status: DONE. Commit 83e92da. 619 passed, 1 warning (596 + 23 new).
Implemented per brief verbatim (PresenceSources.py, VehiclePresence default, TeslaAPI.vehicleOnlineStates/_reportLocation, config.json docs). black clean. config.json validated with the app's loader (comment-strip + yaml.safe_load); it is not strict JSON, before or after.
Concern: _reportLocation is called only at the two brief sites (BLE branch, update_vehicle_data), not the syncSource telemetry branch (that is read by telemetrySource directly).

## Fix round 1
- vehicleOnlineStates: requests.get now has timeout=30; test asserts timeout and Authorization header.
- bleSource: returns None when VIN not in master.settings["Vehicles"] (same dict applyChargeLimit iterates); probePresence not called.
- telemetry/api sources: return no-answer when master.getHomeLatLon()[0] == 10000 (home unset). Telemetry checks before is_location_home (no seeding); api checks after the fetch.
- 622 passed, 1 warning; black clean.

## Fix round 2
- TeslaBLE._markBLEProven (called from _reportContact on any successful contact, including reachable probes) sets settings["Vehicles"][vin]["bleProven"]; creates a missing entry with chargeSessions/startkWh/totalkWh = 0 so recordVehicleVIN's `+= 1` and the web UI keep working. No save queued.
- bleSource: VIN not in settings["Vehicles"] -> None; always probes otherwise; unreachable returns no-answer only if bleProven, else None.
- 628 passed, 1 warning; black clean.
