# Task 2 report: the registry vehicle answers sync state

Status: DONE_WITH_CONCERNS (one small deviation from the brief's deleted-test map; see Concerns)

## Commits
- `f82744e` The registry vehicle answers sync state; callers read registry fields, not CarApiVehicle (on b44ea1e, branch vehicle-model/phase3.5, worktree wt-vm35; not pushed)

## Test results
- Characterization tests (Step 1) written first and passing at BASE before any lib change: `test_get_slave_twcs_reports_the_listed_cars_fields_and_legacy_defaults`, `test_flex_start_reads_the_listed_cars_limit_and_battery`. Both use a real `CarApiVehicle` listed by a real TeslaAPI, so they exercise the BASE attribute reads and the new registry reads alike.
  - Flex pinned values: no observations gives `(1308.96, 7, 0x7F)` (recorded at BASE: the -1 / 10000 defaults); limit 80 / battery 40 gives `(1.54, 7, 0x7F)`. Settings: start 20, end 7, flex on, scheduledAmpsMax 32, battery 100, 240 V x 1 phase, pf 1.
  - getSlaveTWCs is driven through `do_API_GET` (do_GET only dispatches to it), with the `_handler(master)` helper.
- Interface tests (Step 2) failed first with `AttributeError` (no `syncSource` / `telemetryState`), then passed: `test_sync_source_is_a_fresh_telemetry_state_else_teslaapi` (also pins the `<=` boundary at exactly 3,600 s), `test_telemetry_state_ages_only_telemetry`.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1773 passed, 1 xfailed** (baseline 1770: +2 characterization, +2 interface, -1 deleted).
- `black --check lib/TWCManager`: clean. test_registry_vehicle.py and test_registry_callers.py were black-clean at BASE and still are. `git grep getLastVehicle` across the repo finds only the HTTPControl and TWCMaster callers and tests; the templates consume only the JSON field names, which are unchanged. Test files that were not black-clean at BASE were edited in place without reformatting.
- Step 5 grep `git grep -nE '\.syncSource|_telemetryState|syncTimeout|lastCurrentChangeTime' -- lib html tests/integration tests/API`: only `VehicleEndpoints.py:85`, `Targets.py:136`, plus `Vehicle.py` (`telemetryState`/`syncSource`) and `TeslaAPI.is_awake`'s `vehicle.telemetryState()` call.

## Lib delta
27,230 -> 27,212 (**-18**; brief expected about -20). HTTPControl grew by 3 lines because black wraps the `timeToFullCharge` read.

## Changes
- `Registry/Vehicle.py`: `SYNC_TIMEOUT = 60 * 60` with the comment moved verbatim; `telemetryState()` (the old `_telemetryState` minus the live-vehicle lookup); `syncSource` property; imports `TELEMETRY_SOURCES` and `Tuple`.
- `TeslaAPI.py`: deleted `syncTimeout`, `_telemetryState`, `syncSource`, the `actualCurrent` property and setter, and `lastCurrentChangeTime`; `_actualCurrent` became `actualCurrent = RegistryField("actualCurrent", 0)`; `update_charge` is now a single `_readFresh` call; `is_awake` reads `self._liveVehicle()` (no create): `(None, None) if vehicle is None else vehicle.telemetryState()`, with `Vehicle.SYNC_TIMEOUT / 4`. `TELEMETRY_SOURCES` is still imported because `is_awake` uses it.
- `TWCSlave.getLastVehicle`: returns the registry `Vehicle` that has a `"TeslaAPI"` attachment, for currentVIN then lastVIN. It only looks vehicles up and never creates one.
- `HTTPControl /api/getSlaveTWCs`: `attachment("TeslaAPI").atHome`, `value("batteryLevel", 10000)`, `value("chargeLimit", -1)`, `value("timeToFullCharge", 0.0)`. The field names are unchanged.
- `TWCMaster.getScheduledAmpsTimeFlex`: `value("chargeLimit", -1)` / `value("batteryLevel", 10000)` at all three reads.
- `VehicleEndpoints._telemetryPluggedIn(vehicle)`: `vehicle.syncSource != "TeslaAPI" and vehicle.value("pluggedIn") is True`; `allEVSEs` passes `vehicle`. Its `atHome` read is untouched.
- `Targets.broadcastVehicles.reached`: `v.value("lat", 10000) == 10000`; `_restoreDeparted`: `vehicle.syncSource == "TeslaAPI"`.

## Deleted / rewritten test map
- `test_registry_callers.py::test_get_last_vehicle_uses_registry_attachment`: `is car` became `is reg.get(VIN)`. **INTENTIONALLY CHANGED**: the return type is now the registry Vehicle. The None-for-unlisted and never-creates assertions are kept.
- `test_carapivehicle_registry.py`:
  - `car.syncSource` became `reg.get(VIN).syncSource` in `test_is_awake_trusts_fresh_telemetry_and_asleep_without_api_call`, `test_sync_getters_have_legacy_defaults_before_any_state`, `test_stale_telemetry_falls_back_to_api_check` and `test_telemetry_feed_drives_a_real_car`. Plumbing.
  - `car.pluggedIn` became `reg.get(VIN).value("pluggedIn")`. Plumbing.
- `test_carapivehicle_registry.py::test_actual_current_change_time_only_moves_on_change`: deleted, **PLUMBING-ONLY**. `lastCurrentChangeTime` has no reader in lib. It still passed after the change, but only vacuously, because it set a plain attribute.
- `test_carapivehicle_registry.py::test_attributes_are_observations_with_source_and_defaults`: dropped the `lastCurrentChangeTime`/`actualCurrent` assertion line. Plumbing. `car.actualCurrent = 12` now writes through the descriptor, and the `latest("actualCurrent").value == 12` assertion stays.
- `test_reads_no_wake.py::test_ble_actual_current_change_is_timed`: the timing half was removed (**PLUMBING-ONLY**, same reason). The test was **renamed** `test_ble_read_observes_actual_current` and kept with `car.actualCurrent == 16` and `latest("actualCurrent").source == "TeslaBLE"`. This deviates from the brief: see Concerns.
- `test_limit_wiring.py:202`: `car.syncSource` became `v.syncSource`. Plumbing.
- `test_telemetry_registry.py::test_sleeping_car_on_healthy_feed_stays_telemetry_sourced`: `car.syncSource` became `v.syncSource` (x3) and `_telemetryPluggedIn(car)` became `_telemetryPluggedIn(v)` (x2). Plumbing; the assertions are unchanged.
- `test_vehicle_endpoint.py`: the `car()` helper lost its `syncSource`/`pluggedIn` stub fields and parameters. In `test_controller_lists_at_home_api_cars_and_keeps_blind_rules`, the car now observes `state` "online" and `pluggedIn` True from `"TeslaMateVehicle"` on the registry vehicle. Plumbing; the assertions are unchanged.
- `test_charging_points.py` `car()` helper and the three `SimpleNamespace` stubs in `test_gen2_idle_minimum.py`: removed the dead `syncSource="TeslaAPI", pluggedIn=None` stub fields (plumbing; they held default-equivalent values, and the code now reads the registry). The unused `pluggedIn` parameter of `test_charging_points.car` was removed; no caller passed it.

## Self-review
- Every new `value(field, D)` uses the descriptor default: batteryLevel 10000, chargeLimit -1, timeToFullCharge 0.0, lat 10000, pluggedIn None.
- `getLastVehicle`: it uses only `reg.get` (no create), returns None when no listed car is found, and returns the vehicle only if it has a TeslaAPI attachment. The old `if car:` truthiness is equivalent to `is not None`, because CarApiVehicle defines no `__bool__` or `__len__`.
- HTTPControl `attachment("TeslaAPI").atHome` cannot be None.atHome: `getLastVehicle` checked the attachment, and the registry `Vehicle` has no detach.
- `allEVSEs` lists the same cars. The plug check reads the same registry data that the old descriptors read through `_liveVehicle()` (`registry.get(VIN)`), which is the vehicle being iterated.
- `Targets.reached` on a real CarApiVehicle is identical, since `api.lat` read the same registry vehicle with default 10000. It differs only for stub attachments without `lat` (old 0, new 10000); no test depended on that.
- `is_awake` keeps the no-create read. `Vehicle.SYNC_TIMEOUT / 4` equals the old value. No new I/O and no new locks: `telemetryState` uses only FieldStore and registry liveness, as before.
- No new paid Fleet calls.

## Concerns
1. The brief says `test_ble_actual_current_change_is_timed`'s `latest("actualCurrent").source == "TeslaBLE"` half is covered by `test_ble_read_fills_fields_and_api_untouched`. It is not: that test's BLE dict has no `actualCurrent`. Rather than lose that coverage, I kept the test under a new name, `test_ble_read_observes_actual_current`, with the timing removed. The controller may delete it instead if it prefers the brief's map exactly.
2. The lib delta is -18, against about -20 expected. Black wrapped the HTTPControl reads and the flex `realChargeFactor`.
3. Pre-existing and not from this task: pyflakes reports `TeslaAPI.py:229 redefinition of unused 'enabled'`.
