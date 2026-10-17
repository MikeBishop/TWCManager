# Task 2 review: registry vehicle answers sync state (b44ea1e..f82744e)

**Spec compliance: ✅**
**Code quality: approved** (two Minor findings, neither blocking)

## Verification performed

- Full unit suite at f82744e: **1773 passed, 1 xfailed** (matches the report).
- Characterization tests at BASE: the new `test_registry_callers.py` was run against a scratch checkout of b44ea1e. Both `test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults` and `test_flex_start_reads_the_listed_cars_limit_and_battery` **pass at BASE**. The only failure there is `test_get_last_vehicle_uses_registry_attachment`, which is expected because it is marked INTENTIONALLY CHANGED (the return type is now the registry Vehicle).
- Step 5 grep (`\.syncSource|_telemetryState|syncTimeout|lastCurrentChangeTime` over lib, html, tests/integration and tests/API) matches only `Registry/Vehicle.py`, `TeslaAPI.is_awake` (`Vehicle.SYNC_TIMEOUT / 4`), `VehicleEndpoints.py:85` and `Targets.py:136`. This is what the brief requires.
- Lib Δ: `git diff --stat b44ea1e f82744e -- lib` gives +48/−66, so **−18**. Lib shrinks.
- pyflakes on the touched lib files finds no new warnings. All the warnings it reports existed before this change (TeslaAPI.py:229 `enabled`, HTTPControl unused locals, TWCSlave `datetime`/`hourNow`).
- Mutation checks:
  - `_telemetryPluggedIn` forced to `False`: `test_vehicle_endpoint.py::test_controller_lists_at_home_api_cars_and_keeps_blind_rules` fails. The rewritten stub test still drives the code.
  - HTTPControl `timeToFullCharge` default mutated: the getSlaveTWCs characterization test fails.
  - Targets `v.value("lat", 10000) == 10000` replaced with `False`: the **full suite still passes** (see M1).

## Staleness / default equivalence

`RegistryField.__get__` reads `instance._liveVehicle().latest(field)`, where `_liveVehicle()` is `registry.get(self.VIN)`. If there is no observation, it returns the descriptor default. `Vehicle.value(field, D)` reads `self._fields.latest(field)` with default D. `Vehicle.latest` is the same `_fields.latest` call, so both paths read the same observation. The vehicle is the same object too:

- In `getLastVehicle` it is `reg.get(vin)`.
- In `allEVSEs` and `Targets` it comes from `registry.vehicles()`.
- `_bind` attaches a car only to `getOrCreate(self.VIN)`.

The descriptor default and the new `value()` default match for each field:

| Field | Descriptor default | New `value()` default |
|---|---|---|
| batteryLevel | 10000 | 10000 |
| chargeLimit | -1 | -1 |
| timeToFullCharge | 0.0 | 0.0 |
| lat | 10000 | 10000 |
| pluggedIn | None | None (implicit) |

None/0 handling and units are unchanged.

The only theoretical difference is in getSlaveTWCs. If the vehicle is forgotten between `getLastVehicle()` and the field reads, the old code returned defaults (`_liveVehicle()` was None) and the new code returns the forgotten object's last values. This is a sub-millisecond race with display-only impact, so it is not a finding.

`lastAtHome` still reads the attachment's `atHome`. The attachment cannot be None at that point: `getLastVehicle` checked it, and there is no detach in lib (`git grep` finds none).

## Interface checks

- `Vehicle.SYNC_TIMEOUT = 3600`. Its comment moved verbatim. `telemetryState()` is `_telemetryState` verbatim, minus the live lookup. `syncSource` keeps the `<=` boundary, and the new test pins it at exactly 3,600 s.
- `is_awake` keeps the no-create read: `_liveVehicle()` returns `(None, None)` when the vehicle is gone, and `Vehicle.SYNC_TIMEOUT / 4` equals the old `self.syncTimeout / 4`.
- `getLastVehicle`:
  - It is a lookup only (`reg.get`) and never creates a vehicle.
  - It tries currentVIN, then lastVIN.
  - It returns None when the car is unlisted, and the test asserts both None and no-create.
  - The old `if car:` check is equivalent to `is not None` for the only lib attacher, CarApiVehicle, which has no `__bool__`.
- `getScheduledAmpsTimeFlex`: all three reads use the right defaults and the arithmetic is unchanged. The characterization test pins the no-observation defaults `(1308.96, 7, 0x7F)` and the 80/40 case `(1.54, 7, 0x7F)`.
- `VehicleEndpoints.allEVSEs` lists the same cars:
  - The `atHome` gate is untouched.
  - `_telemetryPluggedIn` now reads the iterated vehicle, which is the same vehicle the descriptors resolved to.
  - The old `getattr` guards existed only for stubs. CarApiVehicle is the sole lib attacher of "TeslaAPI" (`TeslaAPI.py:1607`).
- `Targets.broadcastVehicles.reached` and `_restoreDeparted` give identical results for a real CarApiVehicle.
- Locks / I/O: nothing new. `telemetryState` takes the same FieldStore and registry-liveness path the old code took through the car. There are no new paid calls.
- Remaining attachment reads outside TeslaAPI are `atHome` (Gen3TWC:282, Targets:41, VehicleEndpoints:117) and `locate()`. The brief keeps both of these on the attachment.

## Test mapping (holds)

| Test | Change | Holds? |
|---|---|---|
| `test_get_last_vehicle_uses_registry_attachment` | `is reg.get(VIN)` (INTENTIONALLY CHANGED) | Yes; None and no-create assertions kept |
| `test_carapivehicle_registry` ×4 `syncSource`, `pluggedIn` | retargeted to registry | Yes, plumbing |
| `test_actual_current_change_time_only_moves_on_change` | deleted | Yes: `lastCurrentChangeTime` has no lib reader at BASE |
| `test_attributes_are_observations…` | dropped timing line | Yes; `latest("actualCurrent").value == 12` remains, written through the descriptor |
| `test_ble_actual_current_change_is_timed` → `test_ble_read_observes_actual_current` | timing removed, kept | Yes (controller ruling accepted) |
| `test_limit_wiring.py:202`, `test_telemetry_registry.py:264–272` | `car.` → `v.` | Yes, plumbing |
| `test_vehicle_endpoint` stub | TeslaMate `state`/`pluggedIn` observed on registry | Yes, and the mutation check confirms it still drives the code |
| `test_charging_points` / `test_gen2_idle_minimum` stubs | dead `syncSource`/`pluggedIn` fields removed | Yes: those vehicles never observe `state`, so `syncSource` is "TeslaAPI" and the plug check is False, as with the old stub values |

## Findings

- **M1 (Minor), `lib/TWCManager/Vehicle/Reconcile/Targets.py:66`**: no test covers the `v.value("lat", 10000) == 10000` "not yet located" clause. Replacing it with `False` leaves the full suite green. The gap existed before this task. However, this task made the default literal load-bearing: before, the descriptor supplied 10000; now the call site does. A single test with a listed, unlocated, not-at-home car in `broadcastVehicles` would pin it. This is optional for this task and could be done in Task 3.
- **M2 (Minor/Nit), `tests/unit/test_carapivehicle_registry.py:238`**: the rewritten assertion is about 100 characters long. The file was not black-clean at BASE either, so this adds no new debt category. Cosmetic only.
- Note, not a finding: lib Δ is −18 against the brief's ≈ −20, because black wraps the HTTPControl and flex reads. The `row = data[TWCID]` alias saves wraps on three of the four lines, so this is acceptable.
