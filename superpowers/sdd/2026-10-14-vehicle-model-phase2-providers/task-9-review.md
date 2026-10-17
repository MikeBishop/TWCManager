# Task 9 review: VehiclePriority façade over the provider order (eee9425..edf61bf)

## Verdicts

- **Spec compliance (brief as amended by the Task 9 rulings): PASS.**
  - Every Interfaces item is present.
  - All four rulings are implemented and tested:
    - the raise keeps reaching Fleet (readiness-only walk for `setChargeRate`);
    - per-provider attempts are BLE 3, Fleet 2, HA 1;
    - `debugCommand` uses `attempts=1`;
    - HA gets its own vehicle, and HA `available()` is `enabled()`.
  - CHANGELOG line verbatim. Labels exact. Docs sections present.
- **Task quality: FAIL (fix required).**
  - One Critical regression: the BLE-to-Fleet fallback for targeted commands is lost while TeslaAPI's vehicle list is unloaded.
  - One Important regression: a targeted command that falls to HA acts on every HA car.
  - Both come from the brief's readiness design meeting legacy modules that resolve vehicles themselves. Neither the brief nor the rulings foresaw them.

**Regressions: 2** (C1, I1). Suite: 1269 passed, 1 xfailed (tests minus API/integration, capped run, reproduced).

## Method

I built a throwaway harness (`scratchpad/probe-t9/harness.py`) that runs the same scenarios against a detached eee9425 worktree and against wt-vm2:
- **Install shapes:** BLE-only, Fleet-only, Owner-only, BLE+Fleet, HA-only, HA + unconfigured TeslaAPI, and pure Gen2. Variants: BLE claim on/off; TeslaAPI vehicle list loaded/unloaded.
- **Policies:** prefer_ble, ble_only, api_only.
- **Results:** every module call failing, or every call succeeding.
- **Calls, made as the callers make them:**
  - `car_api_charge` start/stop, with and without a VIN;
  - `setChargeRate(32|4, car)`;
  - `applyChargeLimit(-1)` broadcast and `applyChargeLimit(80, vin=)`;
  - `updateChargeAtHome`.
- **Command module:** resolved with `_resolveVehicleCommandModule`'s rule.

The harness used:
- real `TeslaAPI` token slots;
- real `TeslaBLEProvider`, `Gen2TWCProvider` and `HomeAssistantProvider`;
- a TWC-reported registry vehicle.

The harness recorded per-module call counts and the return value. 189 differing cells, grouped below.

## Behaviour-difference table

| # | Shape / policy | Command(s) | eee9425 | edf61bf | Class |
|---|---|---|---|---|---|
| D1 | any with BLE, api_only | reads (`updateChargeAtHome`, `enabled`) | BLE walked first | BLE skipped | intended (ruling "api_only keeps BLE out of reads") |
| D2 | BLE / BLE+Fleet, VIN without a TeslaBLE claim | targeted start/stop/limit/rate | BLE tried 3x first | BLE skipped; Fleet (if any) first | intended (ledger: accepted, keyless VIN would time out) |
| D3 | **Fleet-only and BLE+Fleet, TeslaAPI vehicle list not loaded** (registry vehicle from the TWC, no `TeslaAPI` attachment) | targeted `car_api_charge` start/**stop**, `applyChargeLimit(vin=)` | TeslaAPI called (2x); its `car_api_available` loads the list and sends | FleetAPI not ready, so TeslaAPI is never called; returns False | **REGRESSION, Critical (C1)** |
| D4 | all | nothing succeeds | last module's ret (`"error"`) | `False` | intended (brief; ruling) |
| D5 | HA enabled + TeslaAPI/BLE loaded (incl. unconfigured TeslaAPI), prefer_ble/api_only | every command, broadcast and targeted | HA never reached (façade chosen; TeslaAPI read-only skipped) | HA reached last, 1 attempt | intended (brief, A10) |
| D6 | HA enabled + TeslaAPI | `updateChargeAtHome` (read walk) | TeslaAPI only | TeslaAPI 2x then HA 1x | intended (brief: reads walk every unsuppressed provider) |
| D7 | HA-only (TeslaAPI/BLE not loaded) | command module | HA module directly | façade (HA enabled makes it enabled); prefer_ble/api_only call counts identical | intended |
| D7b | HA-only, ble_only | all commands | HA executes (policy ignored on the direct path) | HA suppressed; nothing sent | intended (brief/CHANGELOG: "suppressed under ble_only") |
| D8 | HA, targeted call for a VIN without an HA attachment/entity | start/stop/limit | HA direct, acted on its own cars | HA not ready, skipped | intended (readiness) |
| D9 | **Fleet+HA (two HA cars)**: targeted stop/start/limit where Fleet fails | `car_api_charge({"vin": A})`, `applyChargeLimit(vin=A)` | HA never reached | HA's legacy methods ignore the VIN and act on **every** HA car at home and connected | **REGRESSION, Important (I1)** |
| D10 | all | stats | keyed by module (`TeslaAPI`) | keyed by provider (`FleetAPI`/`OwnerAPI`); `moduleDispatch` per provider tried | intended (ruling) |
| D11 | debug API | wake / setChargeRate | TeslaAPI only; 200 whether or not the call worked; 400 when TeslaAPI missing | BLE then Fleet, 1 attempt each; 200 only on success | intended (brief, Decision 21, ruling) |
| D12 | debug API, car on a Gen2 TWC covering the rate, no BLE | setChargeRate | sent via Fleet, 200 | local-amps rule drops Fleet; Gen2 skipped in `dispatch`; nothing sent, 400 | intended by design (debugCommand from Task 2 uses `dispatch(amps=)`), user-visible (M1) |
| — | Owner-only, every policy | all commands | none sent (readOnly skip) | none sent (`available()` False) | no difference |
| — | Fleet-only / BLE+Fleet, list loaded | all incl. raise `setChargeRate(32, car)` with TWC covering 32 A | Fleet reached | Fleet reached (raise preserved, #660) | no difference |
| — | pure Gen2 (TeslaAPI unconfigured, HA disabled) | all commands | nothing sent | nothing sent (HA unavailable) | no difference (only D4 return type) |
| — | BLE-only with claim | all commands | BLE 3x | BLE 3x | no difference |

## Check-list results

1. **Behaviour by policy and shape:** see the table. Two regressions (D3, D9).
2. **Cost:**
   - **New paid Fleet calls:** the harness found no case where Fleet calls increased, except D2, which is accepted. Fleet calls decrease under D3.
   - **HomeAssistant:** HA's new calls (D5, D9) are billed at an unknown price. The brief makes HA join the walk, so this is intended.
   - **Attempts:** BLE 3, Fleet 2, HA 1, which equals `_calculate_retries` (test `test_attempts_match_todays_priorities`).
   - **Raise:** one `set_charging_amps` per session. `TeslaAPI.setChargeRate`'s skip-repeat is unchanged, and the façade passes no amps rule.
   - **Debug:** `dispatch(..., attempts=1)` for both commands (`test_debug_command_tries_each_provider_once`).
3. **Broadcast gating:**
   - Owner-only: `FleetAPIProvider.available(cmd)` is `fleetSlot.usable("command")`, which is equivalent to `not readOnly` because the Owner slot never grants commands. Nothing is sent.
   - Disabled HA: `available()` is `enabled()`, so a disabled HA gets nothing. The read walk also applies `available(READ_CHARGE)`.
4. **Local-amps rule on the queue:** `VehiclePriority.setAmps` calls `dispatch(..., amps=amps)`, so `candidates` applies the rule (`test_set_amps_keeps_the_local_amps_rule`).
5. **Logging and locks:**
   - The façade logs exception type names only. `debugCommand` never logs its parameters. HTTPControl adds no logging.
   - The façade holds no lock. `ready()` and `available()` read claims (brief vehicle lock), `getSlaveTWCs()` (no lock) and the token slots (no I/O).
6. **Deleted `apiDebugInterface`:** no remaining reference anywhere in the tree (lib, tests, docs, templates).
7. **Names Task 10/11 consume:** `ProviderOrder.candidates`, `vehicleMaxAmps`, `queue_vehicle_command`, the `{"cmd": "setAmps", "vin", "amps"}` queue command keyed `("setAmps", vin)`, `VehiclePriority.setAmps`, `dispatch(attempts=)` and `debugCommand` all exist. Task 11 consumes nothing from Task 9.

## Findings

### Critical

**C1: the targeted BLE-to-Fleet fallback (start/stop/limit) is dead until TeslaAPI's vehicle list happens to load** (`lib/TWCManager/Vehicle/VehiclePriority.py:145-146` with `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:100`).

- **Why it happens:**
  - The `TeslaAPI` registry attachment exists only after `loadVehicleList()`.
  - Nothing calls that except `TeslaAPI.car_api_available()`, which runs from `car_api_charge` and `applyChargeLimit`, and Telemetry's `loadList` path. `Telemetry.py:363` says as much: "otherwise only loaded when a command needs the API".
  - Today a targeted `car_api_charge({"vin": V})` that BLE fails reaches `TeslaAPI.car_api_charge`, which loads the list and sends.
  - Now `candidates(vehicle, START/STOP)` drops FleetAPI: the TWC-created registry vehicle has no attachment. TeslaAPI is never called, so the list never loads.
- **BLE+Fleet:**
  - The only routine broadcast is the policy loop's `applyChargeLimit(-1)`.
  - `TeslaBLE.applyChargeLimit(-1)` returns True with no I/O when no limit is saved (`TeslaBLE.py:883-891`). The broadcast never reaches TeslaAPI, so the list stays unloaded indefinitely.
  - A BLE stop that fails (car out of range) therefore no longer falls back to Fleet, and the car keeps charging against policy.
- **Fleet-only:** the same gap lasts until the first broadcast `applyChargeLimit` loads the list. That is a boot window, and it lasts longer if that load fails. Stops run before everything else in the queue.
- **Harness evidence:** rows `Fleet{listLoaded False}` and `BLE+Fleet{listLoaded False}`, start(vin)/stop(vin)/limit80(vin): OLD `TeslaAPI:2`, NEW `-`.
- **Fix (primary, inside VehiclePriority.py only):** in `modulesFor`, for a targeted command, also keep a non-local provider whose legacy module is TeslaAPI when `module.getVehicleCount() == 0` (the list was never loaded) and `available(capability)` holds. The legacy module then loads the list and resolves the car itself, as today. This leaves the order's own semantics unchanged: `dispatch`, `candidates`, Task 10's `isReadOnly` and `provider`, and `summary()`.
- **Fix (alternative, wider reach):** in `FleetAPIProvider.ready`, return `available(cap)` for COMMANDS while the list is unloaded. This also changes `dispatch`, `candidates` and the debug summary.
- **Test:** registry vehicle via `getOrCreate(VIN, "TWC")`, Fleet token, empty list, BLE failing. `vp.car_api_charge({"charge": False, "vin": VIN})` must call `TeslaAPI.car_api_charge` 2x.
- **Task 10 check:** confirm the change does not make `VehicleEndpoint.isReadOnly` wrong (endpoints come from listed cars, so it should not).

### Important

**I1: a targeted command that falls through to HomeAssistant acts on every HA car** (`VehiclePriority.py:176-193`; `HomeAssistant.py:581-637` `car_api_charge`, `:639-698` `applyChargeLimit`).

- HA's legacy `car_api_charge` and `applyChargeLimit` ignore `task["vin"]` and `vin=`. They loop over `self.carApiVehicles`.
- With Fleet+HA and two cars, a `stop(vin=A)` that Fleet fails twice now reaches HA. HA is ready because car A has an HA attachment. HA then stops car B as well, if B is at home, connected and charging. The same applies to the charge limit.
- Today on that shape HA never received commands. The Task 9 HA ruling fixed only the analogous `setChargeRate` vehicle-type problem.
- **Fix (either):**
  - **Within the file list, needs no ruling:** `_argsFor` returns None for a `vehicleAttachment` provider on targeted `car_api_charge`/`applyChargeLimit` until Phase 3, plus a test.
  - **Needs a coordinator ruling:** make HA's two methods honour the VIN when one is given (skip `v` where `vin and v.vin.upper() != vin.upper()`), plus a test. `HomeAssistant.py` is outside the brief's file list.
- The coordinator may instead rule HA's stop-all acceptable, as on HA-only today, but that should be a decision.

### Minor

- **M1** (`Order.py:164-184`, `HTTPControl.py:925-933`): the debug page's setChargeRate for a car on a Gen2 TWC that covers the rate now sends nothing and returns 400 (D12). Today it sent via Fleet. Either ask the coordinator to rule that this is intended, or pass `amps=None` for the debug command. The debug command is user-initiated and a single attempt, the same reasoning as the #660 ruling.
- **M2** (`VehiclePriority.py:112-129`): `targetAmps` and its 0→1 clamp no longer affect selection. They are kept only as the brief's interface. Mark them for Phase 3 removal, or drop them along with `test_set_charge_rate_zero_still_reaches_the_vehicle`'s dependence on them.
- **M3** (`VehiclePriority.py:143`): the façade calls the private `self.order._ready`. Prefer a public `ProviderOrder.ready(...)` or a `candidates(..., localRule=False)` flag.
- **M4** (`docs/Settings.md`, providerSuppressions paragraph): the provider-name list omits `Gen3TWC` and the telemetry providers (named after their module classes, e.g. `TeslaMateVehicle`). The list matches the brief but not the code.
- **M5** (`HTTPControl.py:925`): the comment says BLE-only installs can wake from the debug page, but the page's VIN dropdown still lists only TeslaAPI cars. This is already deferred to Phase 6.

## Implementer's remaining concerns, judged

- **BLE tried only with a claim:** accepted (D2, ledger).
- **`targetAmps` unused:** see M2.
- **Original concerns 1-3 (raise, debug double-bill, HA):** resolved by the fix round.
- **Concern 4 (stats keys):** intended.
- **Concern 5 (api_only reads):** intended.
- **Concern 6 (debug dropdown):** see M5.
- **Concern 7 (`TestTeslaAPIEVSE`):** correct.
- **Concern 8 (HA-only resolves to the façade):** verified harmless under prefer_ble/api_only (identical calls, HA 1 attempt). It changes ble_only (D7b), as the brief intends.
- **Deviations 1-3:** acceptable.
