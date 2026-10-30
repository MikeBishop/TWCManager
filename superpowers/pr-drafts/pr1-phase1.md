Title: Vehicle model, phase 1: one vehicle registry keyed by VIN

This PR adds a vehicle registry: one `Vehicle` per car, keyed by VIN, holding every per-vehicle field with its source and age. Phase 1 of the 1.4.0 vehicle-model rework (the spec runs to Phase 6; this stack opens Phases 1, 2, 3 and 3.5); base `main`; review it first.

## Where this sits

Stack: **Phase 1 registry** → Phase 2 providers and charging points → Phase 3 reconcilers (deletes the legacy command paths) → Phase 3.5 `CarApiVehicle` dissolution and #659 port → *later, not in this stack:* Phase 4 control tick and one distributor, Phase 5 presence port, Phase 6 Vehicles tab.

Phases 1 and 2 add the registry and the providers alongside the legacy paths and are not independently useful improvements: they are what Phase 3 switches onto before deleting the old command paths. Merge order is forced by the stack. The alternative was one PR of about 200 commits.

## Changes

### User-visible
- **Vehicles page** lists the registry (tier, providers, last seen, held limit). A vehicle can be added by VIN, so a VIN-less TWC with BLE only can be set up. A vehicle added by VIN that nothing else has seen can be forgotten from its page.
- **Vehicle page BLE status**: not in range, in range, pairing, paired, pairing failed, key refused, with a Bluetooth scan for the car.
- **API change:** the debug endpoint `/api/sendTeslaAPICommand` now takes the vehicle's VIN (`vehicleVIN`) instead of the numeric vehicle ID (`vehicleID`). The web UI and the debug dump read vehicles from the registry.
- Vehicles unseen for 30 days are forgotten (config `vehicle.forgetAfterDays`).
- `settings.json` saves are serialised under a lock, so a save no longer races writers on other threads.
- Vehicle commands are queued per VIN, and a pending stop is cancelled when charging resumes. Refs #667 (Phase 3 closes it, after the exact-match legacy path is deleted).

### Architecture
- `Vehicle/Registry/`: `VehicleRegistry`, `Vehicle`, a field store with value/source/time, VIN validation, and read sources.
- Reads cascade BLE first, then cloud, and never wake a car unless the caller asks. A healthy report-on-change feed (TeslaMate, Fleet Telemetry) vouches for the values it has reported, so a sleeping car on a live feed needs no paid read.
- A TWC-reported VIN is confirmed by a second query before a vehicle is created. Only well-formed VINs become vehicles. Retained MQTT messages never create or revive a vehicle.
- A Gen2 plug session without a VIN gets an anonymous plug-session vehicle (Refs #458).
- `TeslaAPI`, `TeslaBLE`, `TeslaMateVehicle`, `FleetTelemetryMQTT` and `HomeAssistant` feed the registry. `CarApiVehicle` keeps its fields but backs them with the registry; it is dissolved in Phase 3.5.

## Evidence

- **Unit tests at this tip:** 1165 passed, 1 xfailed (main's placeholder `test_regression_template`, xfail by design) (`tests/` excluding `tests/API` and `tests/integration`).
- **Rebase onto #699:** the stack was rebased onto current `main`, which includes #699 (Fleet wake-poll). #699's 12 wake tests run and pass here on the legacy path. The conflicts were all in `TeslaAPI.py`; #699's newest-observation-wins rule is kept, reading registry observations.
- **Live box (pre-rebase build of this phase, 2026-10-14):** Gen2 TWC, BLE, TeslaMate, Owner and Fleet tokens. Soaked about 6 hours including a departure and return. Boot clean; the registry added the car via BLE; the page scan round trip worked; zero Tesla API calls of any kind after boot, including while the car was away (TeslaMate kept the registry fresh). Held limit not restored on departure: that is `main`'s behaviour, unchanged here, and is addressed in Phase 5.

## Size

| | lib lines | vs main |
|---|---|---|
| `main` | 23,180 | |
| this PR | 25,443 | +2,263 (+9.8%) |

lib diff: +2,943 / −595 across 26 files. This phase mostly adds. The rework stays larger than `main` through the whole stack (+18% after Phase 3.5). Deletions are back-loaded: Phase 3 removes the legacy command paths, Phase 4 the per-slave allocator in `TWCSlave`, Phase 5 the old GPS/`atHome` presence code. Phases 4 and 5 are expected to shrink it further. Some of the growth is new capability (Gen3, providers, the reconciler), so the stack may not get all the way back to `main`'s size; whatever gap remains will be stated and explained.

## Known limits / not verified

- The live soak ran the pre-rebase build; the rebase changed only `TeslaAPI.py`, the CHANGELOG and tests.
- Forget is offered only for user-asserted vehicles with no provider attachment; full Forget is Phase 6.
- Gen3 is not touched here.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
