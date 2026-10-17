# Task 5 report: TeslaBLE provider

Status: DONE_WITH_CONCERNS (the concern is a gap between this task and Task 8; this task's code is complete)

Commit: 607e6d1 "Add the TeslaBLE provider: local, free, ready for claimed VINs" (on vehicle-model/phase2, parent 84eb6fb)

## What changed

- New `lib/TWCManager/Vehicle/Providers/TeslaBLEProvider.py`:
  - `TeslaBLEProvider(Provider)` with `name = "TeslaBLE"`, `rank = 2` and `local = True`.
  - `__init__(ble, master)` sets `module = ble` and `readSource = ble.readSource`.
  - `declarations()` gives the nine brief capabilities, each as `Declaration(LOCAL)`. Reads are active, not passive.
  - `ready()` also returns False for a capability outside the nine. That guard goes beyond the brief and cannot change behaviour, because `ordered()` and `summary()` only ask about declared capabilities.
  - `ready()` is `vehicle is not None`, the capability is declared, `vehicle.vin` is set, and `"TeslaBLE" in vehicle.claims`. It reads only the claim, under the Vehicle's leaf lock. It takes no `settingsLock`, no `_bleLock`, and does no I/O.
  - `ampsRange()` is `(1, vehicleMaxAmps(vehicle, master.config["config"]))`. `master.config` is read at call time. A missing `config` falls back to `{}`, so the range is still `(1, 32)`. It returns None only for `vehicle is None`, where `ready()` is also False.
  - `setAmps(vin, amps)` calls `bool(ble.setChargeRate(int(amps), vin))`, passing the VIN positionally as the brief's test asserts.
  - `wake(vin)` calls `bool(ble.wakeVehicle(vin))`.
- `lib/TWCManager/Vehicle/TeslaBLE.py`:
  - `self.readSource = None` is set early in `__init__`, so a module that releases itself on the binary check still has the attribute.
  - Where the module registers its read source, it now keeps the source as `self.readSource = TeslaBLEReadSource(self, master)` and registers that object with the registry.
  - New `providers()` returns `[TeslaBLEProvider(self, self.master)]`. The provider is imported at module top. The provider package does not import TeslaBLE, so there is no cycle.
- `lib/TWCManager/Vehicle/Registry/Sources.py`:
  - `TeslaBLEReadSource.provider = "TeslaBLE"`.
  - `canRead` is now only `bool(vehicle.vin) and "TeslaBLE" in vehicle.claims`. The VehiclePriority/`api_only` lookup is gone.
- New test file `tests/unit/test_teslable_provider.py`: the brief's four tests plus two more.
  - `test_amps_range_is_never_none_while_ready` covers the Task 2 constraint. For a claimed VIN that is ready for SET_AMPS, the range is `(1, 32)` in three cases: with no wiring max, with `availableCurrent` observed as 0 (which falls through to the wiring max, never `(1, 0)`), and with `master.config = {}`. It also checks `covers(v, 1)`.
  - `test_read_source_orders_at_the_local_tier` uses a real `TeslaBLE` provider in `ProviderOrder` and checks that `ble.readSource` sorts ahead of an unowned source.
- `tests/unit/test_reads_no_wake.py` is unchanged. It never asserted an `api_only` skip; its setup only stubs `VehiclePriority` with `commandPolicy="prefer_ble"`. The `api_only` case is covered by Task 2's `test_api_only_suppresses_ble_for_everything`.
- black was run on the three lib files only.

## Unproven and refused claims

An unproven claim (seeded on the upgrade boot) makes the provider ready, and the tests check this through `_claimUnproven`. A refused key drops its claim, so it is not ready, and the tests check this through `dropClaim`.

`ready()` does not look at `settings["Vehicles"]` for a privKey: doing so would take `settingsLock` on the distributor thread. Claims are only made for keyed VINs (`_claimKeyedVehicles` or pairing), so this matches the Phase 1 `_allVehicleTargets` rule.

## Fail-before

Running `tests/unit/test_teslable_provider.py` before the implementation: 6 failed.

```
E   AttributeError: 'TeslaBLE' object has no attribute 'providers'   (x5)
E   AttributeError: 'TeslaBLE' object has no attribute 'readSource'  (test_read_source_no_longer_consults_command_policy)
```

## Tests

- Targeted: `test_teslable_provider.py`, `test_reads_no_wake.py` and `test_teslable_pairing_status.py` gave 107 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1216 passed, 1 xfailed. That is the 1210 baseline plus 6 new tests. All runs used the capped systemd-run command.

## Concerns

1. Transitional `api_only` gap until Task 8. `registerProviders(master)` is still not called from TWCManager.py; Task 8 wires it. Until then, the TeslaBLE provider is not in `master.providerOrder`. `orderReadSources` therefore treats the BLE read source as unowned and never suppresses it. Today every read source is unowned, so the sources still sort by their `order` hint, with BLE first; order is not affected. Because `canRead` no longer checks `commandPolicy`, a user with `api_only` would get BLE reads at intermediate commits on this branch. Task 8 closes this once it calls `registerProviders`. Do not ship or deploy between Task 5 and Task 8.
2. `ampsRange` returns `(1, value)` whenever `availableCurrent` is truthy. If a car ever reports `availableCurrent` below 1 (but not 0), the range is inverted. This follows today's `vehicleMaxAmps` rule and is not new behaviour.
