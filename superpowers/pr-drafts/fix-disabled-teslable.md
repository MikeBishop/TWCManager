Keep disabled vehicle modules out of the provider order

Turning a vehicle module off in config doesn't stop it reading or commanding on `main` since #704. `registerProviders` asks every Vehicle module for its providers whatever its `enabled()` says. `getModuleByName()` already respects `enabled()`; the provider order doesn't. So:

- **`vehicle.teslaBLE.enabled: false`:** commands and reads still went over BLE. I found this on a live install when switching it to API-only: startup still listed `Providers: Gen2TWC, TeslaBLE, …`, and commands still went "via TeslaBLE".
- **`vehicle.teslaAPI.enabled: false`:** the Owner and Fleet providers stayed registered, so cloud reads and commands still went out.

TeslaMate and Fleet Telemetry weren't affected, because their shared base class releases them when disabled. The module loader's own `enabled` check doesn't cover this case: for the Vehicle category it looks under `Vehicle.<ModuleName>`, which never matches the `vehicle.<key>` sections. Every vehicle module reads its own setting instead.

## Changes

- **`registerProviders` applies `getModuleByName`'s rule.** A module whose `enabled()` is False registers no providers. A module with no providers of its own, such as the VehiclePriority facade, isn't asked.
- **A disabled TeslaBLE module releases itself in `__init__`,** the way it already does when `tesla-control` is missing. It never starts its dbus session or workers. A class-level `_dbus_session_pid = None` keeps `__del__` from raising on the half-built instance.

## Tests

- `test_a_disabled_vehicle_module_registers_no_providers`: a disabled TeslaAPI-like module registers nothing, and an enabled one beside it still does.
- `test_a_disabled_ble_module_registers_no_provider`: no TeslaBLE provider, `getModuleByName` returns None, no dbus session, and a quiet `__del__`.
- `test_default_boot_registers_unconfigured_modules_that_never_command` now expects no HomeAssistant provider when config has no HomeAssistant section. That module reports itself disabled there; before, it registered a provider that could never act.
- Both new tests, and the changed one, fail without the changes.
- Verified live with BLE disabled: startup logs `TeslaBLE disabled in config` and `Providers: Gen2TWC, OwnerAPI, FleetAPI, HomeAssistant`.

Unit suite: 1,585 passed, 1 xfailed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
