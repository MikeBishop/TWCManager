# Task 2 review (opus), f29c370f — Needs fixes

## Issues

### Important
- **I1** TeslaAPI.py:1905 `if not inside(self.master, vehicle):` treats home-unknown (inside None, Presence.py:31) as away → is_far_from_home vs the 10000 placeholder → statusDeferral = now + 3600. BASE seeded home and took the 300 s branch. Fresh install with no home: every TeslaAPI read blocks the next for an hour, including a HOME-by-twcVin charging car. Fix: `if inside(self.master, vehicle) is False:`.
- **I2** No home set: learnHome runs only at VIN confirmation (TWCMaster.py:1555-1557); a fix is rarely <600 s old then, so home is learned only by coincidence. Vehicle-only Fleet install with no home: car never HOME (car-source plug needs here True; inside None; no twcVin) → vehicleEndpoints (VehicleEndpoint.py:228) lists nothing → rate never set. Suggested: in noteObservation's lat/lon branch call learnHome when twcVinAt > NEVER; WARNING once when a vehicle module needs home and it is unset; CHANGELOG note.

### Minor
- **M1** Observe hook swallows exceptions at DEBUG (Vehicle.py hook try/except). Use logger.exception/WARNING; `mine is not None` redundant right after a store.
- **M2** TeslaMate narrowing blind at plug-in: charger_power arrives after plugged_in; since() sees only at >= obs.at → a DC plug-in inside the radius marks plugIn. Presence unaffected (HOME by rule 4); Task 3's onArrival must check pluggedNow at decision time or debounce.
- **M3** Lat/lon window (Presence.py:104-111): pairing the source's latest lat and lon with no window is smaller (−3) and covers a one-coordinate on-change update; same adjacent-fix mixing.
- **M4** `_fix` (:38-43) takes field-level latest lat/lon possibly from different sources. Low impact.
- **M5** tests/unit/test_presence.py fails black --check (`;` joins, >88 cols, `__import__("time")`); test_command_path_parity.py now fails black at :1306.
- **M6** test_a_fast_charger_inside_the_radius_is_not_home (test_presence.py:166) asserts only the plug mark; the car is still HOME by position.
- **M7** TeslaAPI.vehicleScheduledChargingPending (TeslaAPI.py:1639-1644) is dead (caller _scheduleBlocksStart deleted).

## Size cut list
| Location | Change | Saved | Behaviour preserved? |
|---|---|---|---|
| TeslaAPI.py:1639-1644 | delete vehicleScheduledChargingPending | −7 | yes |
| TeslaBLE.py:661-665 | drop the five charger fields from get_charge_state (TeslaBLE in _STRONG, never narrowed) | −5 | yes |
| Capability.py:23-28 | drop the six CHARGE_FIELDS additions (only let them through TeslaBLEProvider.py:83; nobody reads them; TeslaAPI observes directly) | −6 | yes |
| Presence.py:153-156 | drop Gen3 branch of _pointPlugged (Gen3 falling edge runs endPlugSession → clears twcVin, Gen3TWC.py:232, VehicleRegistry.py:201-202) | −4 | yes up to one vitals tick; adjust Gen3 half of test_twc_vin_counts_only_while… |
| Presence.py:236-238 | `near = max(v.markAt("absent"), registry.now() - REACH_WINDOW) < v.markAt("contact")` instead of re-reading bleReach | −2 | yes |
| Presence.py:205-206 (+2 blank) | drop `why`; tests use decide(...)[1] | −4 | yes |
| Presence.py:1-5 | module header to 2 lines | −3 | yes |
| Presence.py:69-73 | `power, amps = since("chargerPower"), since("chargeCurrentRequestMax")`; inline kind | −3 | yes |
| Presence.py:83-89 | `if obs.source in _STRONG or here is True and not (value and _awayCharger(v, obs)): return value` / `return None` | −2 | yes |
| Presence.py:257-268 | one-line log message; two-line comment | −3 | yes |
| Fields.py:44-48 + Vehicle.py:9 | move OBSERVED_EVENTS into noteObservation; one guard on the plug branch | −4 | yes |
| Vehicle.py hook | one logger.exception line; drop `mine is not None` | −3 | louder logging (M1) |
| Vehicle.py:4 | float("-inf") / Presence.NEVER instead of import math | −1 | yes |
| VehicleRegistry.py:66-68 | one-line comment | −1 | yes |
| TeslaMateVehicle.py +6 | one shared _optNum for charger_power and charge_current_request_max; no int() | −2 | yes |
| **Total** | | **≈ −50** | |

Remaining duplicates for later tasks: TWCSlave.pluggedCars' plug mapping (≈ −8, `_plug` exists), VehicleEndpoint._telemetryPluggedIn, Gen3's guess loop (F15/F16 → Tasks 3 and 5).
