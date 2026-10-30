Title: Vehicle model, phase 2: providers, provider order and charging points

This PR makes every vehicle channel a provider with declared capabilities and costs, walks commands in one fixed order, and groups charging endpoints into charging points by the car they serve. Phase 2 of the 1.4.0 vehicle-model rework (the spec runs to Phase 6; this stack opens Phases 1, 2, 3 and 3.5); base `vehicle-model/phase1`; review after Phase 1.

## Where this sits

Stack: Phase 1 registry → **Phase 2 providers** → Phase 3 reconcilers → Phase 3.5 `CarApiVehicle` dissolution and #659 port → *later, not in this stack:* Phase 4 control tick and one distributor, Phase 5 presence port, Phase 6 Vehicles tab.

Phases 1 and 2 add the registry and the providers alongside the legacy paths and are not independently useful improvements. Here `VehiclePriority` becomes a facade over the provider order so legacy callers keep working; Phase 3 deletes it and the other legacy command paths. Merge order is forced by the stack.

## Changes

### User-visible
- **Command order:** cost tier, then locality: TWC, BLE, then cloud, billed last. A full install logs `Providers: Gen2TWC, TeslaBLE, TeslaMateVehicle, OwnerAPI, FleetAPI, HomeAssistant`.
- **`commandPolicy` maps onto suppressions:** `prefer_ble` is the default order; `ble_only` suppresses commands on every cloud provider; `api_only` suppresses TeslaBLE for everything, reads included (as today), with a one-time notice. New `providerSuppressions` setting for finer control.
- **Home Assistant** joins the order last (after Fleet), is treated as billed, is suppressed under `ble_only`, and can now set amps. A targeted HA command affects only the named car.
- **Fleet never sets a car's amps where a TWC or BLE can** (Charge Rate Control modes 2 and 3 still may). Amps are queued to the vehicle worker instead of being sent from the RS-485 loop.
- **Charging points:** a car that stops charging on its TWC gets no second power share and no Fleet rate commands. An idle TWC counts nothing against the budget but still offers its hardware minimum on the wire when another car charges, as `main` does.
- **Gen3:** each Wall Connector gets its own target; units on one bus share the headroom. The car on a Gen3 is named by a free read of the energy site's live status (needs a token with `energy_device_data`).
- `controller.Gen2TWCs.ranges` sets per-TWC `minAmps` and `maxAmps`.

### Architecture
New `Vehicle/Providers/` (Provider, Capability, Order, Suppressions; Gen2, Gen3, BLE, Owner, Fleet, telemetry and HA providers; Owner and Fleet are separate). `ChargingPoint` and `VehicleEndpoint(s)` replace `MergedEVSE`, `TeslaAPIEVSE` and `TeslaAPIController`, which are deleted (−479 lines).

## Evidence

- **Unit tests:** 1338 passed, 1 xfailed (main's placeholder `test_regression_template`, xfail by design). #699's wake tests still pass on the legacy path after the rebase.
- **Live box** (pre-rebase build, 2026-10-15; Gen2, BLE, TeslaMate, Owner and Fleet tokens; no Home Assistant): with the car plugged in and complete, one anonymous charging point; zero Fleet `set_charging_amps`; the rate raise went over BLE; a BLE limit write landed on the first try; the debug page's wake was served by BLE; no tokens in logs. Not exercised live: a VIN-named point while charging, and any Home Assistant path (both covered by tests).

## Size

| | lib lines | vs previous | vs main |
|---|---|---|---|
| `main` | 23,180 | | |
| Phase 1 | 25,443 | +2,263 | +2,263 |
| this PR | 27,530 | +2,087 | +4,350 (+18.8%) |

lib diff +3,001 / −914. Like Phase 1 this mostly adds, because the legacy path still runs beside it. Deletions are back-loaded: Phase 3 removes the legacy command paths, Phase 4 the per-slave allocator, Phase 5 the old presence code. The rework stays larger than `main` at the top of this stack (+18%), and phases 4 and 5 are expected to shrink it further. Some of the growth is new capability (Gen3, providers, the reconciler), so the stack may not get all the way back to `main`'s size; whatever gap remains will be stated and explained.

## Gen3 hardware check

@ngardiner, you added Gen3 support on `main` (6028077a). This phase changes it and is unit-tested only; I have no Gen3 hardware. If you have a unit, or know someone who does, could these be checked before merge?

- Each unit is its own target, with the headroom shared on one bus.
- Whether `live_status` reports the car's VIN, and the DIN format.
- The zero-headroom stop.
- Whether the Owner token can read `live_status`.

Thank you. The Gen3 docs are updated in #707, based on this branch.

## Known limits / not verified

- Mode 3 now hands off below the TWC's own minimum offer, not a literal 6 A. Whether a 3-phase TWC accepts offers below 6 A is untested on hardware.
- The live check ran the pre-rebase build; the rebase changed only `TeslaAPI.py`, the CHANGELOG and tests.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
