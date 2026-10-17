# Task 11 report

Branch presence/4-fleet-rate-queue, tip 8cb9dee (8 commits on presence/3-plug-presence). presence/5-fleet-rate-queue untouched (b7e1623).

## Conflicts (all in lib/TWCManager/EVSEController/TeslaAPIController.py, allEVSEs)
1. ace0fef (-> 170adee): docstring merged (plugged in here + no TWC serves); list comprehension uses presence.isPluggedHome(v.VIN) if presence is not None else v.atHome, AND v.VIN not in served; blind -> [].
2. e5478df (-> ca9f5d5): `served, blind, unknown = self._twcServedVINs()`, comprehension adds `and not (unknown and self._telemetryPluggedIn(v))`.
No conflicts in TeslaAPI.py/TeslaBLE.py/TWCSlave.py. Queued rate task (fleetSetChargeRate) calls setChargeRate(amps, vehicle) directly on the Fleet API for that vehicle (not via car_api_charge), so it is already per-vehicle; nothing to add.

## Test fixups (folded into 170adee via autosquash)
- test_teslaapi_controller.py make_controller: master.vehiclePresence = None (Mock auto-attr made isPluggedHome truthy; no-presence fallback keeps v.atHome).
- test_teslaapi_controller_presence.py make_controller: master.getSlaveTWCs.return_value = [] (Mock iteration failed closed to "blind").
- black applied to TeslaAPIController.py (collapsed the comprehension condition).

## Tests
Full suite 1151 passed; test_plug_presence_scenarios.py 16 passed.
