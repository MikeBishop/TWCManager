# Pre-flight conflict scan: Vehicle Model Phase 2 (providers and charging points)

Plan: `.superpowers/plans/2026-10-14-vehicle-model-phase2-providers.md` (11 tasks)
Spec (binding): `.superpowers/specs/2026-10-13-vehicle-model-design.md`
Base checked: `scratchpad/wt-vm2` at 8e07669 (read-only). Some fixture claims were checked by running them against the base: `TWCMaster("AB", CONFIG).newSlave(bytearray(...))`, the `api_with_registry()` token state, `Mock()[k] = v`, and whether `requests_mock` is installed (it is).

What I checked: each task's Interfaces block against its own tests and steps; each cited file:line and class/method against the base; each pair of tasks that share a file or name; the plan's Global Constraints and Review Focus against the tasks; and the spec sections the plan cites (Charging points, Providers, Order/suppressions, Layered actuators, Threading, Constraints, Anti-goals).

## 1. Pair table (tasks that share a file or an interface)

| Pair | Producer gives → consumer uses | Match? |
|---|---|---|
| T1→T2 | `Provider`, `Declaration`, `Cost`, `RateLimit`, capability names, `TIER_BILLED` → `ProviderOrder.orderKey/candidates`, `Suppressions` | Yes |
| T1→T3 | `Provider`, `LOCAL`, `DISRUPTIVE`, `Declaration(passive=True)` → `Gen2TWCProvider` | Yes |
| T1→T4 | `sharedControl`, `limitations()`, `NO_INDIVIDUAL_STOP` → `Gen3TWCProvider` | Yes |
| T1→T5/T6/T8 | `vehicleMaxAmps(vehicle, configConfig)` → BLE/Fleet/HA `ampsRange` | Yes. T8 HA writes `vehicleMaxAmps(...)` without naming the config source, and the HA provider holds only `ha` (F23). |
| T1→T7 | `READ_WALL_CONNECTOR_VINS`, `RateLimit` (defined in T1) → T6/T7 declarations | Yes, no forward dependency |
| T1→T9 | `Provider.module`, `attempts()` (3 local / 2 remote), `local` → façade walk | Yes (matches today's 20→3, 10→2 attempts) |
| T2→T3 | `ProviderOrder(master)`, `register`, `orderReadSources`; `VehicleRegistry.useReadOrder` → `TWCMaster.__init__` | Yes. Settings are read lazily, so building the order before `self.settings` exists is fine. |
| T2→T5 | api_only suppression in `orderReadSources` → replaces the `VehiclePriority` lookup in `TeslaBLEReadSource.canRead` (Sources.py:34-39) | Yes. The order is installed in T3, before T5 removes the check. |
| T2→T6 | `ReadSource.provider` → `"OwnerAPI"`/`"FleetAPI"`; tier sort | Yes. Fleet's minimum READ tier is 1 (READ_LIST is free), so rank (5 after 4) puts it after Owner. That is correct, but it is rank that decides, not cost. |
| T2→T7 | `candidates(None, READ_WALL_CONNECTOR_VINS)` → `WallConnectorVinReader.query` | The interface matches, but T7's `ready()` does HTTP (F10) |
| T2→T8 | `register`, `ordered()` drops passive providers, `suppressions.noticeOnce()` → `registerProviders` | The interface matches. The call timing is wrong (F7). |
| T2→T9 | `ordered/candidates/dispatch/debugCommand`, `Suppressions.commandPolicy/…Overridden/VALID_COMMAND_POLICIES` → `VehiclePriority` | Names match. The `candidates` coverage semantics differ between T2's Interfaces and the T2 and T9 tests (F2, F3). Broadcasts lose the read-only gate (F11). |
| T2→T10 | `candidates(vehicle, SET_AMPS)` → `VehicleEndpoint.isReadOnly/provider` | Yes |
| T3→T4 | `EVSEInstance.vehicleKey/occupied/provider/idleMinimum` defaults → Gen3 overrides | Yes |
| T3→T9 | `Gen2TWCProvider.setAmps` (module `None`) → reached by `dispatch` from `VehiclePriority.setAmps` and `debugCommand` | Mismatch: it mutates TWC state off the serial thread and latches `_evseTargetAmps` (F13) |
| T3→T10 | Gen2 `vehicleKey` (currentVIN → anon → lastVIN while plugged) → `VehicleEndpoints._blindTWCs` | Mismatch: the blind rule still keys on `currentVIN`, so T3's I5 rule never takes effect (F14) |
| T3→T11 | `vehicleKey`, `occupied`, `idleMinimum=True`, `minAmps` → `minPower` → `groupEndpoints`, idle-TWC rule | Yes |
| T3/T9→T11 | Gen2 `ampsRange` = `(minAmps, maxOfferAmps)` → default paid-amps rule ↔ `TWCSlave` mode-3 handoff below a hard-coded 6 A | Mismatch for protocol-1 TWCs (minAmps 5) and 3-phase TWCs (minAmps 1) (F1) |
| T4→T7 | `Gen3TWC.cloudVin`, `_correlate()`, `refreshVitals()`, `device_cfg`; test helpers `make`, `vitals` → reader and tests | Mismatch: the tests drive the unit-level refresh, but the republish and the reader hang off the controller-level refresh (F8). T7's `setup` breaks on T4's `Mock` master (F9). |
| T4→T8 | Both edit TWCManager.py: Gen3 provider registered in the Gen3 block; `registerProviders` after the module loop | Yes (sorting by rank makes registration order irrelevant). Line refs drift (F18). |
| T4→T10 | `Gen3TWCs.devices()`, `.occupied`, `.vehicleKey` (`anon:` prefix) → `_blindTWCs` | Yes |
| T4→T11 | Gen3 `isLocal=True`, `idleMinimum=False`, `setTargetPower` → `setUnitTarget`, `vehicleKey` → grouping | Yes |
| T5↔T6↔T8 | All three edit Sources.py (BLE `canRead`/`provider`; `TeslaAPIReadSource` per slot; HA `provider`) | Yes, the edits don't overlap |
| T6→T7 | `TeslaAPIProviders.py`, `TeslaAPI.slotFor("energy")`, slot `.changes`, `.reportScopeRefused(purpose, refused)` | Yes (all exist at base) |
| T6→T9 | `apiDebugInterface` is deleted in T9; Owner and Fleet share one module, deduped in `modulesFor`; carapivehicle debug tests are rewritten | The rewritten tests need a Fleet token the fixture doesn't have (F5, F17) |
| T6→T10 | `FleetAPIProvider.ready` → `VehicleEndpoint.isReadOnly`; `TestTeslaAPIEVSE` moves | Yes |
| T8→T9 | HA provider with `module=ha` → joins the façade walk last | Yes. The billed-path wording conflicts with the Global Constraints (F15). |
| T9→T10 | `VehicleCommandQueue._DISPATCH["setAmps"]` → `module.setAmps(vin, amps)`, consumed by `VehicleEndpoint.setTargetPower` | Yes when `VehiclePriority` is loaded; the fallback modules lack `setAmps` (F24) |
| T9↔T10 | Both touch `test_registry_callers.py`, `test_teslaapi_readonly_gate.py` | Consistent split (T9 rebuilds the VehiclePriority cases, T10 moves `TestTeslaAPIEVSE`) |
| T10→T11 | `VehicleEndpoint` (non-local), `controllers=["VehicleEndpoints"]`; T10 updates docstrings so T11's grep test passes | Yes. A docstring/inventory wording point is in F19. |
| T3↔T11 | Both edit TWCMaster.py (`__init__` 110-117; 504-620) | Different regions, OK |
| T9↔T11 | Both edit CHANGELOG `* Architecture` | OK |

## 2. Per-task table (is each task consistent with itself?)

| Task | Tests vs Interfaces vs steps | Verdict |
|---|---|---|
| T1 | The tests exercise every listed member. The base has no `startCharging`/`stopCharging`/`setChargeLimit` defaults, although those capabilities are named; Gen2/Gen3 providers add them ad hoc. | OK (minor) |
| T2 | `test_default_fleet_amps_rule_uses_target_and_range` expects `amps=4` → `["FleetAPI"]`. The Interfaces never drop a local candidate that doesn't cover the amps, so the result would be `["Gen2TWC","FleetAPI"]` (F2). "once per process" for `noticeOnce` is fragile (F7). | Conflict |
| T3 | `make()` calls `newSlave(bytearray(...))`, which raises TypeError at base (F4). The rest matches. | Conflict |
| T4 | `test_car_limited_unit_raises_h…` expects a republish after `unit.refreshVitals()`, but the Interfaces put `republish()` only in `Gen3TWCs.refreshVitals()` (F8). Line refs drift (F18). | Conflict |
| T5 | Consistent. `test_reads_no_wake.py` has no api_only assertion, so it needs no change. | OK |
| T6 | `test_claims_split_by_slot` assumes "the fixture starts with a Fleet token"; it doesn't (both slots are empty at base). The claim rule (`not slot.empty()` at bind) also breaks the existing `test_vehicle_joins_registry_and_claims_teslaapi`, which the plan misdescribes (F5). | Conflict |
| T7 | `setup()` → `new_api(master=Mock)` → `master.modules[...] = api` raises TypeError (F9). The tests need a controller-level hook (F8). `ready()` does I/O (F10). Files say `identifyCloudVins`, Interfaces say `vinReader.apply`; the test uses an undeclared `u._version`; one test mixes clocks (F20). | Conflict |
| T8 | The test imports `registerProviders` from `TWCManager.TWCManager`, which starts the app on import (F6). `noticeOnce` runs before `loadSettings` (F7). Two test names promise assertions they don't make (F22). | Conflict |
| T9 | `test_set_charge_rate_target_and_amps…` builds Fleet with LOCAL-tier caps, so the paid rule can't drop it (F3). Broadcasts lose the read-only skip that the rebuilt readonly-gate tests rely on (F11). Non-command methods ignore suppressions (F12). `test_send_teslaapi_command_without_teslaapi_is_400` isn't listed (F17). | Conflict |
| T10 | Self-consistent. `isLocal=False` contradicts the inventory line "isLocal derived from candidates" (F19). The blind rule makes T3's I5 work moot (F14). | OK with F14 and F19 |
| T11 | The tests match the Interfaces. `test_stopped_car_stays_one_point` passes with hand-made endpoints, but production never builds the car's endpoint in that state (F14). | OK |

## 3. Plan references checked against base 8e07669

| Reference | Status |
|---|---|
| ReadSource.py:11-13; VehicleRegistry.py:246-257 (`registerReadSource`/`readSources`); `beginPlugSession/endPlugSession/vehicleAt/observeTwcVin/now`; `ANON_PREFIX="anon:"` | Exist |
| TWCSlave.py:25 `minAmpsTWCSupports=6`; TWCManager.py:1270-1278 (5/6 by protocol), :1424-1426 (1 A for 3-phase) | Exist (1271-1278, 1424-1426) |
| `TWCSlave.maxAmps`, `.wiringMaxAmps`, `.currentVIN`, `.lastVIN`, `.reportedState`, `.reportedAmpsActual`; `Gen2TWC._evseTargetAmps` | Exist |
| EVSEInstance.py:92-100; Gen2TWC.py:108-114; TWCMaster.py:110-117, 504-532, 534-620; `sendStopCommand(subTWC)`, `stopCarsCharging`, `queue_background_task` (coalesces by key), `queue_vehicle_command` | Exist |
| Gen3TWC.py:80-108, 122-130, 136-199, 205-254, :129 comment; Gen3TWCs.py:186-227, 320-337; `_VITALS_*_TTL` | Exist |
| TWCManager.py:376-392 (background-task chain) | Approximately (the chain runs 320-405) |
| TWCManager.py:812-822 (T4 Gen3 block) | Drift: actual 793-810 (F18) |
| TWCManager.py:800-810 (T8 after module load) / 800-812 (T10 TeslaAPIController registration) | Drift: the module loop ends at 773; TeslaAPIController is registered at 775-791 (F18) |
| TeslaBLE.py:233; `setChargeRate(charge_rate, vehicle=None,…)`, `wakeVehicle(vin)`, `_claimUnproven` | Exist |
| Sources.py:34-39, 72-99, 106-110 | Exist |
| TeslaAPI.py:144, 200-225 (`apiDebugInterface`), 2080-2091 (`_bind` claim at 2089), 2165 `is_awake`, 2190 `get_car_api`, 2330 `update_vehicle_data`; `getVehicleByVIN` (returns False when unknown); `wakeVehicle(vehicle)`; `slotFor`, `readOnly` | Exist |
| HomeAssistant.py:264; `HaVehicle.has_charge_*`; `setChargeRate(amps, vehicle=)`; `enabled()`; `registry` | Exist |
| `TelmetryBase.feedLiveAt(vehicle)` (Telemetry.py:169) | Exists |
| VehicleCommandQueue.py:33-40 (`_DISPATCH` at 34-42), `_execute`, `_key` | Exist |
| HTTPControl.py:915-937 | Exists |
| settings.html.j2:116-150 | chargeRateControl and commandPolicy are there; the chargeStopMode label is at 42-56 (F18) |
| EMS/TeslaPowerwall2.py:257-292 (`/products`, `live_status`) | Exists |
| TeslaTokenSlot: `usable(purpose)`, `empty()`, `changes`, `baseURL`, `reportScopeRefused(purpose, refused=False)`, `SCOPES["energy"]` | Exist |
| test_carapivehicle_registry.py:130-140, 161, 172; test_teslaapi_readonly_gate.py:170-210, 212-230; test_telemetry_registry.py:9, 254, 258; test_registry_callers.py:20-25; test_distributor_loop.py:27 (actually 28) | Exist |
| test_registry_callers.py:155-175 (debug route) | Drift: the route tests are at 163-185, and the `…without_teslaapi_is_400` test isn't listed (F17) |
| EVSEController.py:17-18; EVSEInstance.py:13-16 | Exist |
| Test helpers: `test_teslable_pairing_status.make/VIN`, `test_homeassistant_registry.make_ha`, `teslatokens.owner_token/fleet_token/new_api`, `test_carapivehicle_registry.api_with_registry/VIN` | Exist (but see F5 and F9 for what they actually provide) |
| `requests_mock` fixture | Installed in venv |

## 4. Forward dependencies

- T1 `__init__` re-exports `ProviderOrder` "(Task 2)". The plan says so and T1's step adds it in T2. OK.
- T4 declares `cloudVin` as a plain `None` attribute that T7 fills. OK.
- T8 places `registerProviders` "before the VehicleEndpoints registration of Task 10". When T8 runs, that registration is still `TeslaAPIController`. This is placement wording only (covered with F18).
- No task uses a symbol created by a later task. T6 notes that `apiDebugInterface` survives until T9, and existing callers keep working until then.

## 5. Findings

1. **High: the mode-3 handoff threshold and Gen2 coverage disagree, so the car can overshoot.** Plan: T2 "a local candidate counts as 'a local amps path' when `amps is None or provider.covers(vehicle, amps)`"; T3 "`ampsRange(vehicle)` → `(slave.minAmps, slave.maxOfferAmps)`"; T11 "`TWCSlave.send_master_heartbeat` applies `chargeRateControl` exactly as today (mode 2 / mode 3 below 6 A queue the car's rate through the façade and offer the wiring maximum)". At base, TWCSlave.py:860 hands off below a hard-coded 6 A and then offers `wiringMaxAmps`. A protocol-1 TWC (minAmps 5) or a 3-phase TWC (minAmps 1) "covers" 5 A or 4 A. The default rule therefore drops Fleet, and `setChargeRate` reaches only BLE. A Fleet-only car on such a TWC is never limited while the TWC offers the wiring maximum. This breaks Review Focus 3 for those TWCs and the spec's layered-actuator rule (the next provider must carry a T outside the preferred provider's range). **Ruling:** in Phase 2, `Gen2TWCProvider.ampsRange` returns `(6, maxOfferAmps)` when `chargeRateControl == 3`, matching the threshold TWCSlave actually uses. (Changing TWCSlave would change behaviour, which belongs to Phase 3.) Add a T3 test: minAmps 5 + mode 3 + 5 A → Fleet stays a candidate.

2. **High: T2 Interfaces vs T2 test on non-covering local providers.** Plan: `test_default_fleet_amps_rule_uses_target_and_range` asserts `candidates(None, SET_AMPS, amps=4) == ["FleetAPI"]`, but the Interfaces only *add* the Fleet-drop rule; nothing removes a ready TWC that doesn't cover 4 A. **Ruling:** follow the spec (Layered actuators: outside the preferred provider's range, "the next provider carries T"). Add to the `candidates` Interfaces: when `amps` is given, drop any candidate whose `ampsRange` is known and doesn't cover `amps`. Also clamp `debugCommand`'s amps to ≥1, because the spec says vehicle amps are "never 0", and a 0 would otherwise drop every candidate.

3. **High: a T9 test builds Fleet at the wrong tier.** Plan: `test_set_charge_rate_target_and_amps_apply_the_default_fleet_rule` uses `P("FleetAPI", 5, False, api)` with the default `caps=CMDS` (all `C.LOCAL`). The paid rule drops only `tier >= TIER_BILLED`, so Fleet stays and `vp.setChargeRate(10, car) is False` fails. **Ruling:** give that Fleet `caps={C.SET_AMPS: C.Declaration(C.FLEET_COMMAND)}`.

4. **High: the T3 fixture raises TypeError.** Plan: `s = m.newSlave(bytearray(b"\x82\x44"), 80)`. `TWCMaster.slaveTWCs` is a dict keyed by `bytes`, and at base a bytearray raises `TypeError: unhashable type`. **Ruling:** use `b"\x82\x44"`.

5. **High: T6's claim rule is fixed at bind time, and its test premise is false.** Plan: "`_registryVehicle` claims `"OwnerAPI"` … when `not carapi.ownerSlot.empty()` and `"FleetAPI"` … when `not carapi.fleetSlot.empty()`", and the test comment "the fixture starts with a Fleet token". At base, `api_with_registry()` starts with both slots empty. So `test_claims_split_by_slot`'s api2 gets only `{"OwnerAPI"}`, and the existing `test_vehicle_joins_registry_and_claims_teslaapi` (list first, then `setTokens(fleet_token())` → "managed") breaks. The plan describes that test as needing only a `"TeslaAPI" in v.claims` edit, but it contains no such line. The same thing happens in production when a token is pasted or synced (TeslaMate) after the listing: the car never becomes managed. **Ruling:** always make both claims at bind, with live callables (`OwnerAPI` canCommand False; `FleetAPI` canCommand `fleetSlot.usable("command")`) and a status that reflects the slot (e.g. "listed" vs "no token"). Rewrite the T6 tests to assert tier and status, not claim membership, and give api2 a `fleet_token()`. This keeps tier live, as the spec's managed rule requires ("a Fleet slot listing it with command scope").

6. **High: the T8 test imports the application entry point.** Plan: `from TWCManager.TWCManager import registerProviders`. TWCManager.py starts the app at import time (test_twcmanager.py's docstring: "cannot be imported here"). **Ruling:** define `registerProviders(master)` in the Providers package (e.g. `Providers/Order.py` or a new `Providers/Registration.py`), and call it from TWCManager.py.

7. **Medium: the api_only startup notice fires before settings are loaded.** Plan: T8 "after the module-load loop … then `master.providerOrder.suppressions.noticeOnce()`"; Review Focus 1 "one INFO notice at startup". At base, `master.loadSettings()` runs at TWCManager.py:815, after module and controller registration, so a settings-based `api_only` is still the default `prefer_ble` when the notice runs. **Ruling:** call `noticeOnce()` right after `master.loadSettings()`, and make "once" a per-`Suppressions`-instance flag rather than per process, so tests stay order-independent.

8. **High: the Gen3 tests drive the unit refresh, but the republish and the VIN reader are wired to the controller refresh.** Plan: T4 "`refreshVitals()` → `refreshVitals()` on every device, then one `republish()`" (Gen3TWCs) and T7 "`Gen3TWCs.refreshVitals()` … flags `vinReader.noteConnect()` … then `vinReader.apply(...)`". But the T4 (`test_car_limited_unit_raises_h…`) and T7 tests call `unit.refreshVitals()` through the `vitals()` helper and expect a republish or a `live_status` query. **Ruling:** `Gen3TWC.refreshVitals()` ends by calling `controller.noteVitals(self, rising)`. That method does the damped `republish()` and, on a rising edge or a due poll, `vinReader.apply(...)`. `Gen3TWCs.refreshVitals()` then only loops over the devices. Update both Interfaces blocks accordingly.

9. **High: T7's `setup()` builds TeslaAPI on a `Mock` master.** Plan: `m, ctl, p = make_gen3(); … api = new_api(master=m)`. `new_api` does `master.modules["TeslaAPI"] = api`, and a plain `Mock` raises TypeError on item assignment (confirmed). **Ruling:** in `setup`, set `m.modules = {}`, `m.settings = {}`, `m.settingsLock = threading.RLock()` and `m.stats = {...}` before `new_api`, or build the API on a `FakeMaster` that shares `m.vehicleRegistry`.

10. **Medium: T7's `ready()` does I/O.** Plan: "`wallConnectorVinsReady(slot)` → slot `usable("energy")`, `energySites(slot)` non-empty", where `energySites` fetches `/products` on a cache miss. This breaks T1's contract ("`ready` … never does I/O") and the Global Constraint ("readiness checks are single-key settings reads and claim lookups"), and `Provider.summary()` (Phase 6 UI) would make HTTP calls. **Ruling:** readiness = slot usable for energy, not refused since the last token change, and sites not *known* to be empty (cache only). Product discovery runs inside `query()`/`wallConnectorVins()` on the background thread.

11. **Medium: the façade drops today's read-only skip for broadcasts.** Plan: T9 "`modulesFor` … `candidates(...)` when `targetVIN` resolves to a registry vehicle, else `ordered(cap)`". Vehicle-less calls (`car_api_charge` with `vin` None, `applyChargeLimit(limit=…)`, `setChargeRate(amps, None)`) now reach an Owner-only `TeslaAPI`. Today `_skip_read_only_for_command` prevents that. The plan's rebuilt `TestVehiclePrioritySkipsReadOnly` cases (all broadcasts, asserting "TeslaAPI not in moduleFailures") can't pass as described. **Ruling:** add `Provider.available(capability) -> bool` (default True, no vehicle) and filter broadcasts with it. `FleetAPIProvider.available` is `fleetSlot.usable("command")` for commands and wake.

12. **Medium: façade read methods ignore suppressions.** Plan: T9 "for any other method, `self.order.providers()`" against Review Focus 1, "TeslaBLE is suppressed for every operation … no BLE timeout is paid". Under api_only, `updateChargeAtHome` still walks BLE. **Ruling:** for non-command methods, skip providers where `suppressions.suppressed(p, READ_CHARGE)`, matching `orderReadSources`.

13. **Medium: `Gen2TWCProvider.setAmps` can be dispatched off the serial thread and latches the TWC target.** Plan: T2 `debugCommand` → `dispatch(vehicle, SET_AMPS, …)`; T9 `VehiclePriority.setAmps` → `dispatch(...)`; T3 `setAmps` → `slave.setTargetPower(...)`. For a car on a TWC, Gen2 is the first candidate. A debug-page `setChargeRate` (HTTP thread) or a queued `setAmps` (vehicle worker) then writes `_evseTargetAmps`. On installs where the distributor is off (no TeslaAPI or Gen3), `TWCSlave` uses that value forever (TWCSlave.py:705), overriding policy. That is new cross-thread mutation, which the spec forbids. **Ruling:** in Phase 2, `dispatch` callers that act on a vehicle (`debugCommand`, `VehiclePriority.setAmps`) skip providers with `module is None` (TWC providers). Those providers still count as the local amps path for the Fleet rule. The TWC target stays the distributor's alone until Phase 3's reconciler.

14. **Medium: T10's blind rule makes T3's I5 work moot, and it hides other cars.** Plan: T10 "`_blindTWCs` … today's `_twcServedVINs` without the served set" (keyed on `currentVIN`); T3 "`vehicleKey` … `lastVIN.upper()` while `reportedState in PLUGGED_STATES`"; Review Focus 5. At base, a stopped car clears `currentVIN` (TWCMaster.py:1302-1304) while the TWC reports 03/04. The blind rule then fires and lists **no** vehicle endpoints for any at-home car (a second car on a UMC loses its Fleet path), and the "stays one point" grouping is never reached in production. **Ruling:** `_blindTWCs` counts a slave as naming its car when its `vehicleKey` is a VIN. It is unknown only when `vehicleKey` is None or `anon:`, and blind when such an unknown slave is plugged or drawing. Add a T10 test where a lastVIN-plugged TWC keeps other cars listed. Keep T11's grouping test.

15. **Low: HA in the command walk vs "No new paid call path".** Plan: Global Constraints "No new paid call path"; T9/Decisions 4 and 7: HomeAssistant (classed billed, `HA_BILLED`) joins the command walk last. At base it was never reached (no priority). The spec lists HA in the fixed order, and the spec is binding. **Ruling:** keep HA last and reword the constraint to "no new Fleet paid path; HomeAssistant, a user-loaded billed-tier provider, joins the order last". Say so in the CHANGELOG line.

16. **Low: api_only deviates from the spec's default mapping.** Plan: Decision 6 / T2 "`api_only` and `provider.name == "TeslaBLE"` (every capability)". The spec says "`api_only` … maps to default with a log notice (builder may keep it as 'local suppressed' if a reason surfaces)". **Ruling:** accept. A reason is given (no working Bluetooth means a BLE timeout per command), and narrowing "local" to BLE (TWCs stay usable) is the only sensible reading. Keep the notice.

17. **Low: T9 omits tests it will break.** Plan: T9's test list. `test_registry_callers.py::test_send_teslaapi_command_without_teslaapi_is_400` breaks once "the `TeslaAPI is None → 400` check goes". The rewritten carapivehicle `debugCommand` tests need a `fleet_token()`, because `FleetAPIProvider.ready(WAKE)` needs a command slot and the fixture has none. **Ruling:** list both in T9's Files and state the token setup.

18. **Low: line references drift.** Plan: T4 "TWCManager.py:812-822" (actual 793-810); T8 "TWCManager.py:800-810" (module loop ends at 773, insert before 775); T10 "TWCManager.py:800-812" (actual 775-791); T9 "settings.html.j2:116-150" (the chargeStopMode label is at 42-56); T9 "test_registry_callers.py:155-175" (actual 163-185). **Ruling:** correct them. Anchor on code (the Gen3 `_gen3_cfg` block, the TeslaAPIController block, `master.loadSettings()`) rather than line numbers.

19. **Low: `VehicleEndpoint.isLocal` contradicts the inventory text.** Plan: T10 "`isLocal` `False`" vs "Inventory rows … A8 (… `isReadOnly`/`isLocal` derived from candidates)". **Ruling:** keep `isLocal=False`, because T11's "local member carries the target" rule depends on it. Fix the A8 line to say only `isReadOnly` and `provider` are derived from candidates.

20. **Low: loose ends in T7.** Plan: Files "`identifyCloudVins` from `refreshVitals`" vs Interfaces `vinReader.apply`. `test_single_local_single_cloud_matches_without_din` sets an undeclared `u._version`, and `test_rate_limit_is_respected` mixes `apply(…, 100.0)` with the controller's `time.time()`, so the rate window compares across clocks. **Ruling:** drop the `identifyCloudVins` name. Declare the version cache (`_version: dict`) in the Gen3TWC Interfaces. Give `WallConnectorVinReader` an injectable `clock`, used both for `due`/`lastQuery` and for the rate window, and use it in the test.

21. **Low: duplicated logic.** Plan: T3 "`stopCharging(self, vin)`: mode 2 → under `master.settingsLock` set `respondToSlaves = 0`, `respondToSlavesExpiry = time.time() + 60` (as `stopCarsCharging`); mode 3 → `master.sendStopCommand(...)`". That copies `TWCMaster.stopCarsCharging`'s branches, with a lock the original lacks. **Ruling:** factor `TWCMaster.stopRespondingToSlaves()` (taking `settingsLock`) and call it from both places.

22. **Low: two T8 tests assert less than their names say.** Plan: `test_register_providers_collects_every_vehicle_module_in_rank_order` registers one provider; `test_passive_providers_never_enter_the_walk_and_reads_order_by_cost` asserts nothing about read order. **Ruling:** register two providers out of rank order and assert the order, and either assert `orderReadSources` or rename the test.

23. **Low: the HA provider can't reach config.** Plan: T8 "`ampsRange` → `(1, vehicleMaxAmps(...))`" with `__init__(self, ha)` only. **Ruling:** spell it as `vehicleMaxAmps(vehicle, ha.master.config["config"])`, read on every call (the T5 test changes config after construction).

24. **Low: the queue fallback has no `setAmps`.** Plan: T9 `_DISPATCH["setAmps"]` → `module.setAmps(...)`, where `module` comes from `_resolveVehicleCommandModule`. If `VehiclePriority` is disabled in config, the fallback (HA, BLE, TeslaAPI) has no `setAmps`, and an AttributeError is logged on every refresh. **Ruling:** the dispatch entry uses `getattr(module, "setAmps", None)` and returns False with one DEBUG line when it is missing (or calls `master.providerOrder.dispatch` directly).
