# Task 3 report: sleep-safe evidence probes and startup discovery

## Implemented
- PresenceSources: telemetry/ble/api sources now return Evidence-key dicts (reach, pluggedIn, inside, pilot, actual, fastChargerType, fastChargerPresent); "limit" and bleProven gating removed. API source returns {} for offline/failed (never queries an offline car).
- VehiclePresence: `_probe(vin, bleOnly=False)` merges sources (reach from ble; pluggedIn ble>telemetry>api with source kept; inside telemetry>api; fastChargerPresent first non-None). API is skipped when ble/telemetry already gave both pluggedIn and inside (spares a request). `_applyEvidence` records contact(probe=True), plugState(edge=False, fastCharger), location, in that order; runPass calls it after `_probe`. `start()` calls `nominate(None, "startup")` once.
- TeslaBLE: module-level `blePluggedIn(cs)`; `get_charge_state` adds pluggedIn, chargePortLatch, connChargeCable, chargeCurrentRequest, fastChargerType, fastChargerPresent.
- TeslaAPI vehicle: new `fastChargerPresent` attribute parsed from `fast_charger_present` (needed by apiSource; not in the brief's file list).
- TWCSlave: removed `_nominatePresence`, `_presenceVIN` and three call sites.

## Fixture shape note
Tests use the real live shape (single-key enum dicts, e.g. `{"Engaged": {}}`, `{"SAE": {}}`) instead of the brief's "ChargePortLatchEngaged" strings; `_enumKey` (module-level; `_extract_enum_value` delegates to it) yields "Engaged"/"SAE"/"Disconnected".

## Tests / TDD
RED: 23 failures before sources/_probe/startup implemented (sources 16, vehicle_presence 7). Caveats: TeslaBLE and TWCSlave changes were made before their tests were run (TWCSlave removal edit first; test_teslable_presence passed on first run), so no RED evidence for those two. Old nomination tests deleted; replaced by test_twc_events_nominate_nothing.
GREEN: full suite 974 passed.
Note: a probe's contact/plug/location observations are applied on the next pass (observers record only), so tests run runPass twice.

## Files
lib/TWCManager/{PresenceSources,VehiclePresence,TWCSlave}.py, lib/TWCManager/Vehicle/{TeslaBLE,TeslaAPI}.py; tests/unit/test_{presence_sources,vehicle_presence,teslable_presence,twcslave}.py. Black applied to touched files that were clean before, plus test_presence_sources (fully rewritten); test_teslable_presence and test_twcslave were not black-clean before and were left unformatted.

## Concerns
- bleOnly is implemented but nothing calls it yet (Task 5).
- Startup nominate(None) probes every known VIN including API-only cars; API source only fires for online cars.
- Telemetry plugged-in is probe-applied as a non-edge weak read, subject to existing weak-vs-strong rules.
