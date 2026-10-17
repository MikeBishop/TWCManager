# Task 8 report: Telemetry and HomeAssistant providers, startup registration, read order by cost

Status: DONE_WITH_CONCERNS
Branch: vehicle-model/phase2 (worktree wt-vm2)
Commit: f0b6f27 "Add telemetry and HomeAssistant providers and register every module's providers at startup"

## Changes

- `lib/TWCManager/Vehicle/Providers/TelemetryProvider.py` (new): `rank = 3`, `local = False`, `module`/`readSource` None (inherited). `name` is the telemetry module's class name. Declares READ_CHARGE/LOCATION/PLUG/ONLINE as `Declaration(CLOUD_FREE, passive=True)`. `ready()` returns True when `feedLiveAt(vehicle)` is a number.
- `lib/TWCManager/Vehicle/Providers/HomeAssistantProvider.py` (new): `name = "HomeAssistant"`, `rank = 6`, `local = False`, `module = ha`, `readSource = ha.readSource`. Declares READ_CHARGE, READ_LOCATION, SET_CHARGE_LIMIT, START/STOP_CHARGING and SET_AMPS as `HA_BILLED`, with no WAKE. `ready()` requires `ha.enabled()` and an attached HaVehicle, then checks the per-capability entity flag (it reads flags only, with no I/O, and is guarded for `vehicle is None`). `ampsRange` is `(1, vehicleMaxAmps(...))` and is read on every call. `setAmps` goes registry, then attachment, then `bool(ha.setChargeRate(amps, vehicle=hv))`.
- `HomeAssistant.py`: added a class-level `readSource = None`, so a disabled or unreachable HA, which returns early before the read source exists, can still build its provider. Also `self.readSource = HomeAssistantReadSource(self)` (still registered) and `providers()`.
- `Registry/Sources.py`: `HomeAssistantReadSource.provider = "HomeAssistant"`.
- `Telemetry.py`: `TelmetryBase.providers()` returns `[TelemetryProvider(self)]`.
- `TWCManager.py`:
  - imports `registerProviders`.
  - calls `registerProviders(master)` once, after the module-load loop and its summary log, and before the `if master.getModuleByName("TeslaAPI") is not None:` block.
  - calls `master.providerOrder.suppressions.noticeOnce()` as the statement right after `master.loadSettings()`.
  - Nothing new is defined there.
- black reported every touched lib file clean, including TWCManager.py, which was already clean at HEAD.

## Tests (tests/unit/test_provider_registration.py, 15 tests)

- The brief's 4 tests, verbatim.
- HA ordering:
  - With BLE, Owner/Fleet and the real HA registered through `registerProviders`, `ordered(SET_AMPS)` is `[TeslaBLE, FleetAPI, HomeAssistant]`. HA comes last, after the free providers and Fleet.
  - Under `ble_only`, HA is absent from `ordered()` for every command, but its read source is kept, which is today's read behaviour.
  - The HA read source still sorts after the Owner and Fleet read sources. Its key moved from (9, 999) to (2, 6), still after Fleet's (1, 5); Fleet declares free READ_LIST and READ_ONLINE, and the key takes the minimum read tier (corrected in fix round 1). Reads are not reordered and there is no new paid path.
- Task 5 carry-forward. These use a real `TWCMaster`, a real `TeslaBLE` (with the dbus and pipe calls patched, as in test_teslable_pairing_status) registered as a Vehicle module, a claimed vehicle, and `vehicle.read("batteryLevel", maxAge=0)`:
  - `api_only` without `registerProviders`: BLE `get_charge_state` IS called. This pins the gap the ruling describes.
  - `api_only` after `registerProviders(master)`: the BLE read source is not in `readSources()` and `get_charge_state` is never called.
  - Default (unset), `prefer_ble` and `ble_only` after `registerProviders`: BLE is the first read source and is read once (value 50).
- Pure Gen2: on a real `TWCMaster` with no vehicle modules, `registerProviders` returns `["Gen2TWC"]`, and the only EVSEController is Gen2TWCs, so the distributor stays off.
- Startup wiring (read from source, never imported):
  - `registerProviders(master)` appears exactly once, between `for module in modules_available:` and the TeslaAPI `if`.
  - The top-level statement after `master.loadSettings()` is `noticeOnce()`, and it appears exactly once.

### Fail-before

1. Whole file, before any lib change:
   `E   ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers.HomeAssistantProvider'` (collection error).
2. With the providers added but before TWCManager.py was edited, the two wiring tests (the real fail-before for the carry-forward, since the Order/TeslaBLEProvider machinery has existed since Task 5):
   - `test_startup_registers_providers_after_the_module_loop`: `ValueError: substring not found`
   - `test_startup_notice_runs_right_after_load_settings`:
     `AssertionError: assert 'backgroundTa...gs=(master,))' == 'master.provi....noticeOnce()'`
   (At that point, two of my own new tests also failed because their fixtures were wrong: the Owner read source had no registered provider, and TWCMaster always registers Gen2TWCs. I fixed the tests, not the lib.)

### Runs

- Brief step 4 set (test_provider_registration, test_homeassistant_registry, test_telemetry_registry, test_twcmanager): 105 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1281 passed, 1 xfailed (1266 at 61ca7ea + 15 new).

## Concerns

1. Pure Gen2 versus an unconfigured HA. The module loop loads any module whose config section is missing (`.get("enabled", 1)`). HomeAssistant does not release itself when disabled, so an install with no `vehicle.HomeAssistant` section registers a never-ready HomeAssistant provider. That provider has no read source, `ready()` is always False, and it never enters a walk, but it appears in the startup "Providers:" log line. A TeslaAPI with no config already behaves the same way on this branch. I kept `providers()` unconditional, as the brief specifies, rather than gating it. A strictly pure-Gen2 install, with no Vehicle modules loaded, registers nothing new (tested).
2. `providerSuppressions {"HomeAssistant": [...]}` now really drops HA reads (via READ_CHARGE in `orderReadSources`). Before, no provider matched the source, so the setting had no effect on HA reads.
3. Gen3TWCProvider still registers in the Gen3 block, after `registerProviders`, so the startup "Providers:" log line omits Gen3TWC. This is cosmetic. I left it where the brief puts it.
4. `registerProviders(master)` at startup is not wrapped in try/except, unlike the Gen3 block. A provider constructor that raises would stop startup, in the same way the module loop re-raises unexpected exceptions. The class-level `HomeAssistant.readSource = None` covers the known case.

## Fix round 1

Commit: eee9425 "Guard provider registration per module and pin the default boot's providers" (on top of f0b6f27).

- **I-1 (registration guard).** `registerProviders` in `Order.py` now wraps each module's `providers()` call and its registrations in try/except. On a failure it logs a WARNING, "Could not register <module> providers: <ExceptionType>", and skips that module; the other modules still register. Only the exception type is logged, never its message, following the codebase's no-tokens-in-logs convention. `TWCManager.py` is unchanged.
  - Test: `test_one_failing_module_does_not_stop_the_others` uses a Mock module whose `providers()` raises, alongside a BLE stub and the real `make_ha()`. The result is still `["TeslaBLE", "HomeAssistant"]`, and exactly one WARNING comes from the providers logger, naming the module.
  - Fail-before: `E   RuntimeError: boom`.
- **I-2 (pure-Gen2 test).**
  - Renamed the old test to `test_no_vehicle_modules_registers_only_gen2`.
  - Added `test_default_boot_registers_unconfigured_modules_that_never_command`. It uses a real `TWCMaster(CONFIG)` (no vehicle config sections) with a real `TeslaAPI(m)` and `HomeAssistant(m)` registered as Vehicle modules. It asserts:
    - registration gives `["Gen2TWC", "OwnerAPI", "FleetAPI", "HomeAssistant"]`, which documents ruling 1;
    - no command capability in `COMMANDS` has a non-local candidate for a registry vehicle;
    - `candidates(None, READ_WALL_CONNECTOR_VINS) == []`;
    - the EVSEControllers are still exactly `["Gen2TWCs"]`.
  - It passed on first run, as expected: it pins behaviour that was already safe, not a fix.
- **Concern 2.** Added a CHANGELOG line (v1.4.0, Architecture): "A providerSuppressions entry for HomeAssistant now also drops Home Assistant vehicle reads, not only its commands".
- **M-1.** Corrected the read-key statement above: Fleet's key is (1, 5), not (2, 5).
- **M-2 (optional; done).** `HomeAssistantProvider.readSource` is now a property that reads `ha.readSource` through, rather than a snapshot taken at construction. One assertion was added to `test_home_assistant_provider_follows_entities`.
- **Not actioned, as the review ruled:**
  - M-3: no behavioural startup-notice test. TWCManager.py can't be imported, and noticeOnce is unit-tested in Task 2.
  - M-4: the test file keeps the brief's one-liner style, and autoblack excludes tests.
- **Runs.** The full suite (`tests --ignore=tests/API --ignore=tests/integration`) gives 1283 passed, 1 xfailed. black reports both touched lib files unchanged.
- **Test-only fix while making the new test green.** `make_ha()` logs its own HA warning ("No Tesla vehicles discovered"). The warning count is therefore filtered to the providers logger, after `caplog.clear()`.
