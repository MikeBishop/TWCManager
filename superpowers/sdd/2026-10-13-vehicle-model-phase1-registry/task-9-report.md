# Task 9 report: CarApiVehicle backed by the registry

**Status:** DONE
**Commits:** 985990d (main change), 290f7d1 (reads made side-effect-free; follow-up from the advisor's done-check). Branch vehicle-model/phase1, base 055e286.
**Tests:** 928 passed (912 before, plus 16 in tests/unit/test_carapivehicle_registry.py). TDD: 13 of the new tests failed before implementation. The 1 warning is pre-existing (enphase InsecureRequestWarning).

## What changed

- `lib/TWCManager/Vehicle/TeslaAPI.py`
  - New `RegistryField(field, default, source="TeslaAPI")` descriptor. `__get__(None, owner)` returns the descriptor. Reads return the latest observation or the default. Writes call `instance.vehicle.observe(field, value, source)`.
  - `TeslaAPI.__init__`: `self.registry = VehicleRegistry.forMaster(master)`.
  - `addVehicle` skips a listed entry whose VIN the registry refuses (ValueError: None, empty, non-ASCII), with a debug log.
  - `apiDebugInterface(command, vin, parameters)` resolves the car with the new `getVehicleByVIN` and returns False for an unknown VIN. `getVehicleByID` was removed (it had no other callers). `debug.html.j2` now posts `vehicle.VIN` as `vehicleID` (debug.js and HTTPControl are unchanged).
  - `CarApiVehicle`:
    - Descriptors for the 13 brief fields, with the brief's defaults, plus `_actualCurrent = RegistryField("actualCurrent", 0)` behind the `actualCurrent` property. That property observes every write and updates `lastCurrentChangeTime` only when the value changes.
    - `__init__`: `getOrCreate(VIN, "TeslaAPI")`, then attach and claim (`lambda: not carapi.readOnly`, status "listed"). The name is observed (`seen=True`), so a listing counts as a sighting.
    - No thread. `checkSyncNotStale` and the `Thread` import are gone.
    - **Stale-reference ruling:** the `vehicle` property calls `registry.get(VIN)` on every use. When that returns a different object (re-created by another provider), it rebinds: it re-claims, and attaches only if the attachment is empty, so a stale CarApiVehicle never displaces a newer one. When it returns None (forgotten), a *write* does `getOrCreate(VIN, "TeslaAPI")` and rebinds. The account still lists the car, which matches the accepted "undone on next listing" behaviour. *Reads* (`_liveVehicle`) are a plain `registry.get`: no create, no claim, no attach. They return defaults while the car is forgotten.
    - `syncSource` getter: the source of `latest("state")` if it is in `TELEMETRY_SOURCES` and `age("state") <= syncTimeout`, else "TeslaAPI". The setter stores `_legacySyncSource`. `syncTimestamp` getter: `latest("state").at` or 0; the setter is a no-op. `syncState`/`syncLat`/`syncLon` setters observe "state"/"lat"/"lon" with `_legacySyncSource or "TeslaAPI"`. Their getters read the fields with legacy defaults ("asleep", 10000, 10000), so `FleetTelemetryMQTT.mqttMessage` reading `.syncState` never raises.
    - `is_awake()` follows the brief. A telemetry asleep/offline returns False; fresh telemetry (age at most syncTimeout/4) is trusted; otherwise it falls through to the 2-minute-cached API check, which does not write "state".
    - `update_location` sync branch now only computes `atHome` from `lat`/`lon`.
    - `update_vehicle_data` (P15) observes only keys present in the response: the 9 charge_state keys go through one `if key in charge` loop. `gps_as_of` is observed only when present; gpsAge uses the response-local value. `vehicle_name` is observed only when present and non-empty. The BLE location path likewise observes `gpsAsOf` only when it is truthy.
- `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py`: `forMaster` passes `{}` when `master.config` is not a dict. A Mock master's Mock config otherwise logged the forgetAfterDays warning on every TeslaAPI construction.
- Tests: the `teslaapi.Thread` monkeypatches were dropped from `teslatokens.py` and `test_teslaapi_charge_vin.py`. `no_threads` remains as a no-op fixture so the ~25 tests that request it don't change. `test_twcmanager.py` never patched teslaapi.
- The new tests cover all of the brief's tests, plus:
  - listing as a sighting
  - `lastCurrentChangeTime` only moving on change
  - no-VIN listings skipped
  - legacy sync defaults
  - P15 checks for gpsAsOf and name
  - forget, then a write rejoins the live vehicle with attachment and claim
  - forget, then another provider re-creates, then the write lands on the new object
  - API re-listing attaches the new CarApiVehicle while the old one is not re-attached
  - an end-to-end check of a `TelmetryBase` subclass named TeslaMateVehicle driving a real CarApiVehicle: state and lat land with source TeslaMateVehicle; syncSource and pluggedIn are correct.

Black: TeslaAPI.py, VehicleRegistry.py, teslatokens.py and test_teslaapi_charge_vin.py were all black-clean before the change. Black was run only on the touched files.

## Concerns (for Tasks 10/11 and Phase 6)

Checked: `TWCMaster.__init__` creates `master.vehicleRegistry` (TWCMaster.py:118) before TWCManager.py loads modules, so `forMaster` returns the shared registry in production.


1. **Source misattribution until Tasks 10/11.** Three writers go through the RegistryField descriptors and get stamped "TeslaAPI":
   - Telemetry's `setattr` for the non-sync fields (batteryLevel, chargeLimit, name, pluggedIn, actualCurrent, phases, voltage, chargingState, timeToFullCharge, availableCurrent)
   - Telemetry's `vehicle.name = vehicle_name` on remap
   - the BLE paths in `update_location`/`update_charge`

   Nothing in Phase 1 branches on those fields' source: `syncSource`/`is_awake` read only "state". So the effect is cosmetic in `summary()`. Using `_legacySyncSource` in `__set__` was rejected because it would stamp TeslaAPI polls as telemetry.
2. **Cost regression between Tasks 9 and 11. Do not deploy Task 9 alone to the live box.** This follows the brief's getter spec as written.
   - `syncSource` is now derived from the age of the latest telemetry "state" observation. Both TeslaMate and FleetTelemetryMQTT change `state` only on transitions. So a car that has been charging or online for more than an hour without a state transition gets `syncSource == "TeslaAPI"`.
   - `update_charge`/`update_location` then take the API branch. `ready()` calls `is_awake()`, and once the state observation is older than 15 minutes, `is_awake()` falls through to a **paid** `get_car_api` call.
   - The old any-message `syncTimestamp` heartbeat prevented this. Task 11's liveness registration for the telemetry sources fixes it.
   - Before the first state observation, `syncSource` is also "TeslaAPI". The old code flipped it at mapping time. TeslaMate's retained `state` makes that window short.
3. **BLE wakes of sleeping cars (Task 11 / controller decision).**
   - The old `checkSyncNotStale` reverted only when `is_awake()` was true, so a sleeping car stayed on the telemetry branch.
   - Now a car asleep with a state observation more than an hour old routes through the BLE-first branch of `update_location`/`update_charge`. That branch calls `ble.wakeVehicle(VIN)` when the BLE state read returns None and `lastAPIAccessTime` is more than 2 minutes old.
   - `is_awake()` still blocks the paid API call, but not the BLE wake. Liveness alone won't fix this if TeslaMate is quiet while the car sleeps.
   - Decision needed: should `syncSource` hold while the latest telemetry state is asleep/offline?
4. **Log noise until Task 11.** Telemetry.py's "telemetry has resumed" INFO log fires on every message while there is no fresh telemetry state observation, because the derived `syncSource` doesn't match the module name.
5. **Forget does not stick for a cloud-listed car.** The CarApiVehicle stays in `carApiVehicles`, and its next write re-creates the registry vehicle. Phase 6's Forget must also drop the CarApiVehicle, or suppress the rejoin.
6. The web debug page now sends the VIN. Any external script that posted a numeric ID to `/api/sendTeslaAPICommand` now gets a 400.
