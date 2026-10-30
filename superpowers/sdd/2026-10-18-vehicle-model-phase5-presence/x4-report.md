# X4 report (A7, A8, A9)

Status: DONE. Base a0ff25ca. Lib: 26345 -> 26310 lines; `git diff --shortstat a0ff25ca -- lib`: 6 files, +53/-88 (net -35, estimate -36).

## A7
- Removed `_readFresh` (only caller was `update_charge`; grep of lib/html/tests found no other reference). `update_charge` now reads `batteryLevel` via `vehicle.read(maxAge=READ_MAX_AGE)` and keeps the BLE-proves-awake stamp (new BLE observation, by identity). It returns None. Only lib caller, `updateChargeAtHome`, ignores the value.
- Tests rewritten (test_reads_no_wake.py, plus the same `is True/False` asserts in test_teslaapi_providers.py x3 and test_telemetry_registry.py x1):
  the return-value asserts are gone; each test keeps its existing observable asserts (value stored/source, `update_vehicle_data` call counts, `is_awake`, `wakeVehicle.assert_not_called`, `lastAPIAccessTime`).
  Where the return value was the only proof, added effect asserts: asleep case -> `latest("batteryLevel") is None`, no vehicle_data, no wake; deferral -> stale value 40 kept, no is_awake, no vehicle_data, no wake; all-sources-failing (renamed) -> value stays 40, vehicle_data attempted once, no wake; providers param test "unusable/asleep" -> no observation + call counts. Nothing loosened: every prior observable assert remains, and the dropped `is False`/`is True` were proxies for these effects.
- Behaviour note: a stale value after every source failed was "False" before; nothing in lib consumed it.

## A8
- New `vehicleRecordKey(vehicles, vin)` in Registry/VIN.py (exact key first, then case-insensitive; None if absent; caller holds settingsLock). Removed `HTTPControl._vehicleRecordKey` and the inline `any(k.upper()==vin)`; `TeslaBLE._settingsKey` now uses it (still takes settingsLock, falls back to `vin.upper()`).
- `canForgetVehicle` now asks `master.getModuleByName("TeslaBLE").bleStatus(vin)["status"] == "paired"`; the settings read happens inside the BLE module under settingsLock as before.
- Verified callers: _vehicleRecordKey used in canForgetVehicle and forgetVehicle only; _settingsKey callers unchanged.

## A9
- `Telemetry._attach(vehicle_id, vehicle, label)` replaces the two attach/un-orphan/un-warn/log blocks.
- `TeslaMateVehicle.loadCarVINs`: one try with `contextlib.closing` for connection and cursor; one except (same log, returns {}).

## Tests
`tests/unit + tests/EMS`: 2035 passed, 1 warning (same as baseline). black run on touched lib files and test_vehicle_detail_page.py (other touched test files were not black-clean before; not reformatted to keep the diff small).

## Concerns
- `canForgetVehicle` with no TeslaBLE module loaded now allows Forget even if settings record a paired key (before: refused from settings alone). Test `test_forget_refuses_listed_paired_and_unknown_vehicles` was adjusted to supply a module whose `bleStatus` reports paired. Edge case: BLE disabled after pairing.
- `bleStatus` does a little more than `_storedStatus` (range status, `shutil.which`), harmless on the HTTP thread.

## Fix round 1
1. Added `storedBleStatus(vehicles, vin)` in Registry/VIN.py (via `vehicleRecordKey`; returns `{"status","since"}`, "unpaired"/None when none, so `_storedStatus` keeps `since`; caller holds settingsLock). `TeslaBLE._storedStatus` uses it under its settingsLock; `canForgetVehicle` is back to a `settingsLock` block checking `!= "paired"`, no module lookup. Reverted the `m2.getModuleByName` stub, so the test proves the settings-only refusal. `_storedStatus` no longer calls `_settingsKey`; the helper does the lookup.
2. test_telemetry_registry.py: added `batteryLevel == 61` assert.
3. Noted: duplicate-case key order is now exact, then first case-insensitive match (was exact, upper, first scan).
Tests: tests/unit + tests/EMS 2035 passed, 1 warning. Lib delta vs a0ff25ca (cumulative, both commits): +71/-92 = net -21 (round 1 cost +14 lines against the -35 of the first commit).
Commit: "Refuse Forget on a paired record without the BLE module".
