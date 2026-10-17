# Task 8 review: Telemetry and HomeAssistant providers, startup registration, read order by cost

Range: 61ca7ea..f0b6f27 (one commit). Checkout: wt-vm2 at f0b6f27.

## Verdicts

- **Spec compliance: PASS.** Every interface in the brief is present with the specified names, ranks, costs and wiring. The deviations from the brief are all small and justified:
  - a class-level `HomeAssistant.readSource = None`, so a disabled HA can still build its provider;
  - `ampsRange(None)` returns None, and config is read defensively;
  - `TelemetryProvider.ready` does not count a bool as a number;
  - `HomeAssistantProvider.ready` returns False for an undeclared capability or a None vehicle.
- **Task quality: PASS WITH FIXES.** Two Important items should be fixed in this task: the per-module registration guard (concern 4) and the pure-Gen2 test, which does not test what its name says. The rest is Minor.

Focused run: `test_provider_registration`, `test_homeassistant_registry`, `test_telemetry_registry`, `test_twcmanager` and `test_provider_order` gave 124 passed.

## Concern rulings

1. **Unconfigured HA (and TeslaAPI) register never-ready providers: accept as designed.** The module loop loads any module whose config section is missing (`TWCManager.py:742-746`, `.get("enabled", 1)`). HomeAssistant returns early without releasing itself (`HomeAssistant.py:204-206`), and TeslaAPI does the same. So a real default-config Gen2 boot registers OwnerAPI, FleetAPI and HomeAssistant as well as Gen2TWC. This is safe, for three reasons:
   - HA `ready()` is False because `enabled()` is False.
   - The Owner and Fleet slots are built at `TeslaAPI.py:200-203` before the early return. `wallConnectorVinsReady(None/unusable)` is False, and `FleetAPI.available()` is gated by the slot.
   - The distributor still depends only on EVSEControllers. `TeslaAPIController` registers only when `getModuleByName("TeslaAPI")` is not None, which checks `enabled()`; that is unchanged.

   No lib change is needed. The test, however, does not model this case (see I-2).
2. **`providerSuppressions {"HomeAssistant": [...]}` now really drops HA reads: accept.** The setting used to do nothing for HA reads because no provider matched the read source. Now it does what it says. This is a behavior change and is worth one line in the release notes.
3. **The Gen3TWC provider registers after `registerProviders`, so the "Providers:" log line omits it: accept (cosmetic).** `ordered()` and `orderReadSources()` key on `(tier, rank, index)`, so Gen3 at rank 1 sorts correctly whenever it registers. If wanted, add a second "Providers:" log line after the Gen3 block. Not required.
4. **`registerProviders` is unguarded at startup: rule YES, guard it, with a test (Important, fix in this task).** See I-1. The constructors are safe today: every attribute they read exists, including on an early-returned HA or TeslaAPI. But this is new code on every install's startup path. The provider layer adds selection and suppression on top of modules that already work, and one buggy `providers()` should not stop charging control. The Gen3 block right below it already guards its own provider registration (`TWCManager.py:819-823`). The precedent in the module loop (re-raise) covers module construction, not this optional layer.

## Findings

### Critical

None.

### Important

**I-1. One raising `providers()` or `register()` aborts startup.** At `lib/TWCManager/Vehicle/Providers/Order.py:180-186` (`registerProviders`), called unguarded at `lib/TWCManager/TWCManager.py:784`.

Fix: put the guard per module inside `registerProviders`, not around the call in `TWCManager.py`. The brief keeps `TWCManager.py` to the two calls, and per-module isolation means one bad module does not drop the others:

```python
for mod in master.getModulesByType("Vehicle"):
    try:
        for provider in getattr(mod["ref"], "providers", lambda: [])():
            master.providerOrder.register(provider)
    except Exception as e:
        logger.warning("Could not register %s providers: %s", mod["name"], e)
```

- Log at warning (or error), not debug. If TeslaBLE's provider were skipped under `api_only`, the BLE read source would have no provider. `orderReadSources` would then sort it as unknown and never suppress it, which reopens exactly the gap that `test_api_only_without_registered_providers_still_reads_over_ble` pins. The skip must be visible.
- Test: add a Mock Vehicle module whose `providers()` raises, next to a working BLE stub and `make_ha()`. Assert that the returned names still contain `TeslaBLE` and `HomeAssistant`, and that `caplog` has the warning.

**I-2. `test_pure_gen2_registers_nothing_new` does not model a real pure-Gen2 boot.** At `tests/unit/test_provider_registration.py:113-117`.

- What it tests: a `TWCMaster` with no Vehicle modules at all.
- What a real default-config install does: it loads unconfigured TeslaAPI and HomeAssistant modules (ruling 1) and so registers OwnerAPI, FleetAPI and HomeAssistant.
- Why it matters: the name makes a claim the test does not check, and the safety it implies is unpinned.
- This is a test-fidelity issue, not a lib bug; tracing the code shows the behaviour is safe.

Fix: rename the test to what it checks (for example `test_no_vehicle_modules_registers_only_gen2`), and add the honest version:
1. Build a real `TWCMaster(CONFIG)`.
2. Construct `TeslaAPI(m)` and `HomeAssistant(m)` with no config sections, and register both as Vehicle modules.
3. Run `registerProviders(m)`.
4. For a registry vehicle `v`, assert that `candidates(v, C.SET_AMPS)`, `candidates(v, C.START_CHARGING)` and `candidates(None, C.READ_WALL_CONNECTOR_VINS)` contain only local providers or are empty.
5. Assert that the EVSEControllers are still only `["Gen2TWCs"]`, so the distributor stays off.

### Minor

**M-1. The report misstates the read-source keys.** `task-8-report.md`, "HA ordering" bullet 3. The report says Fleet's read-source key is (2, 5). In fact `orderReadSources` (`Order.py:115-120`) takes the minimum tier over every declared READ, and Fleet declares READ_LIST and READ_ONLINE as CLOUD_FREE, so its key is (1, 5). HA's is (2, 6). The conclusion still holds: the order is Gen2 (0,0), Gen3 (0,1), TeslaBLE (0,2), OwnerAPI (1,4), FleetAPI (1,5), HomeAssistant (2,6). Before this commit, BLE, API and HA were all unknown (9,999) and sorted by `order` 0/1/2, behind Gen2 and Gen3. Owner now sorts deterministically before Fleet by rank, which is a move toward the free source. Nothing newly reaches a paid or slower source before a free or local one. No code fix; correct the report.

**M-2. The HA provider snapshots `ha.readSource` at construction.** At `HomeAssistantProvider.py:37`. This is correct today, because `readSource` is only set inside `HomeAssistant.__init__`, before registration. A later reconnect path that rebuilt the read source would leave the provider stale. Fix (optional): make `readSource` a property that returns `self.ha.readSource`.

**M-3. No behavioural test that the `api_only` notice fires at startup.** The wiring test (`test_provider_registration.py:137-143`) pins placement only. That is acceptable, since `Suppressions.noticeOnce` is unit-tested in Task 2 and `TWCManager.py` must not be imported. No action needed.

**M-4. The test file is not black-formatted.** It uses semicolon one-liners copied from the brief. CI's autoblack excludes `tests/*` (`.github/workflows/autoblack.yml:35`), so this is style only.

## Checks performed

- **Startup on each install shape:**
  - pure-Gen2: Gen2TWC only, or never-ready Owner/Fleet/HA providers when those modules load unconfigured.
  - BLE-only: TeslaBLE is first among the vehicle read sources and is the local SET_AMPS path.
  - Owner/Fleet: Owner ranks before Fleet. The paid-SET_AMPS filter still applies.
  - TeslaMate and FleetTelemetryMQTT: the passive provider never enters `ordered()`, and a disabled module releases itself (`Telemetry.py:73-75`; `registerModule` skips released modules).
  - HA: rank 6, tier billed, after Fleet for every capability.
  - Gen3 enabled: its provider registers in its own guarded block, and `ordered()` sorts it by rank.
- **Serial thread and the distributor:**
  - `registerProviders` runs once on the main thread before the threads start, and does no I/O.
  - The only live consumer it newly feeds is Gen3's `WallConnectorVinReader`, which runs on the Gen3 vitals background thread (`Gen3TWCs.noteVitals`).
  - Nothing new runs on the serial thread, and EVSEController registration is unchanged.
- **HA position and `ble_only`:** HA is last, and `ble_only` suppresses only COMMANDS for non-local providers (`Suppressions.py:96-97`), so HA reads survive. Both are tested.
- **`api_only` test:** it uses a real `TWCMaster`, a real `TeslaBLE` (with dbus and pipe patched), real `registerProviders` and a real `vehicle.read`.
- **No import of `TWCManager.py`:** the wiring tests read the source as text or through `ast`.
- **Locks:**
  - `ProviderOrder` holds no lock, and `register` replaces the list rather than mutating it.
  - `VehicleRegistry.readSources()` releases `_lock` before calling the order function.
  - HA and Telemetry `ready()` read flags only.
  - `has_charge_*` are `@property` (`HomeAssistant.py:76-87`), so `bool(...)` is meaningful.
  - `TeslaMateVehicle.carHealthy(None)` returns True.
- **Names later tasks consume:** all exist.
  - `TelemetryProvider` (`name` taken from the module class)
  - `HomeAssistantProvider`
  - `TelmetryBase.providers()` and `HomeAssistant.providers()`
  - `HomeAssistant.readSource`
  - `HomeAssistantReadSource.provider`
  - `registerProviders`
  - `suppressions.noticeOnce`
