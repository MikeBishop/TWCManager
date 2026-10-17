# Vehicle-model dedup audit (Phase 1–3, read-only)

Date: 2026-10-15. Auditor: Opus, read-only. No checkout was edited; the Task 13 simulation ran on a `git archive` copy in the scratchpad.

**Refs.** `origin/main` 03d7932. Merge base eb457dc: main has since gained 47 lines in TeslaAPI from #699, so "vs main" figures below include that drift. The per-file tables are pinned at **3fbb5e4**. **d2a7a57** landed during the audit: it adds 35 lines to Reconciler.py and Desired.py, which are in flux, so HEAD is now 30,210 lines. The simulation uses d2a7a57.

**Counting rule.** Non-test `lib/**/*.py` lines (`wc -l`). Templates and JS are excluded. `Workers` and `VehicleReconciler` are not built anywhere in lib yet; Task 10 wires them, so Run.py, Reconciler.py and Desired.py are all unreachable code in production today.

---

## 1. Where the growth is

| Ref | lib .py lines | blank | comment | docstring | code |
|---|---|---|---|---|---|
| origin/main | 23,180 | 2,962 | 3,230 | 695 | 16,293 |
| phase1 8e07669 | 25,394 | | | | |
| phase2 6a6c14e | 27,483 | | | | |
| phase3 3fbb5e4 | 30,175 | 3,666 | 4,238 | 799 | 21,472 |
| phase3 d2a7a57 | 30,210 | | | | |

The +6,995 lines break down as +5,179 code, +1,008 comments, +704 blank lines and +104 docstrings. The comment growth is noted here only; it is not offered as a deletion target.

### Per directory (main → 3fbb5e4)

| Dir / file | main | HEAD | Δ |
|---|---|---|---|
| Vehicle/ (all) | 5,924 | 11,799 | **+5,875** |
| — Vehicle/Reconcile/ (new) | 0 | 1,756 | +1,756 |
| — Vehicle/Providers/ (new) | 0 | 1,279 | +1,279 |
| — Vehicle/Registry/ (new) | 0 | 1,071 | +1,071 |
| — legacy Vehicle modules | 5,924 | 7,693 | +1,769 |
| EVSEInstance/ | 882 | 1,171 | +289 |
| VehicleCommandQueue.py | 154 | 374 | +220 |
| TWCMaster.py | 2,022 | 2,222 | +200 |
| Control/ | 2,637 | 2,818 | +181 |
| EVSEController/ | 612 | 788 | +176 |
| TWCManager.py | 2,039 | 2,085 | +46 |
| TWCSlave.py | 1,252 | 1,260 | +8 |

### Per file, largest first (main → 3fbb5e4; Δcode is code lines only)

| Δ | main | HEAD | Δcode | file |
|---|---|---|---|---|
| +617 | 1,493 | 2,110 | +454 | Vehicle/TeslaBLE.py |
| +514 | 2,547 | 3,061 | +363 | Vehicle/TeslaAPI.py |
| +453 | 0 | 453 | +340 | Reconcile/Desired.py (472 at d2a7a57) |
| +425 | 0 | 425 | +334 | Reconcile/Reconciler.py (441 at d2a7a57) |
| +393 | 0 | 393 | +293 | Reconcile/Run.py |
| +377 | 0 | 377 | +308 | Registry/VehicleRegistry.py |
| +284 | 0 | 284 | +221 | Registry/Vehicle.py |
| +250 | 0 | 250 | +177 | Reconcile/HeldLimits.py |
| +248 | 0 | 248 | +194 | Providers/Order.py |
| +220 | 154 | 374 | +165 | VehicleCommandQueue.py |
| +200 | 2,022 | 2,222 | +137 | TWCMaster.py |
| +193 | 0 | 193 | +107 | EVSEInstance/ChargingPoint.py |
| +182 | 0 | 182 | +134 | Providers/WallConnectorVins.py |
| +180 | 254 | 434 | +127 | EVSEInstance/Gen3TWC.py |
| +180 | 354 | 534 | +117 | EVSEController/Gen3TWCs.py |
| +180 | 1,880 | 2,060 | +146 | Control/HTTPControl.py |
| +175 | 0 | 175 | +127 | Registry/Fields.py |
| +168 | 0 | 168 | +124 | Providers/TeslaAPIProviders.py |
| +165 | 0 | 165 | +91 | EVSEInstance/VehicleEndpoint.py |
| +143 | 0 | 143 | +96 | Registry/Sources.py |
| +143 | 0 | 143 | +78 | EVSEController/VehicleEndpoints.py |
| +141 | 250 | 391 | +98 | Vehicle/Telemetry.py |
| +137 | 0 | 137 | +74 | Reconcile/Rules.py |
| +126 | 0 | 126 | +93 | Providers/Gen2TWCProvider.py |
| +126 | 733 | 859 | +101 | Vehicle/HomeAssistant.py |
| +125 | 0 | 125 | +68 | Providers/Provider.py |
| +123 | 210 | 333 | +103 | Vehicle/VehiclePriority.py |
| +122 | 0 | 122 | +92 | Providers/HomeAssistantProvider.py |
| +113 | 0 | 113 | +89 | Providers/Suppressions.py |
| +90 | 325 | 415 | +73 | Vehicle/TeslaMateVehicle.py |
| +87 | 0 | 87 | +68 | Providers/Gen3TWCProvider.py |
| +86 | 0 | 86 | +60 | Providers/TeslaBLEProvider.py |
| +74 | 0 | 74 | +50 | Providers/Capability.py |
| +73 | 148 | 221 | +48 | EVSEInstance/Gen2TWC.py |
| +64 | 0 | 64 | +31 | Reconcile/Outcome.py |
| +58 | 0 | 58 | +38 | Registry/ReadSource.py |
| +34 / +34 / +30 / +28 | | | | Reconcile/__init__, TelemetryProvider, FleetTelemetryMQTT, TeslaTokenSlot |
| −147 / −151 / −181 | | | | TeslaAPIController, TeslaAPIEVSE, MergedEVSE (deleted) |

### What Task 13 leaves (simulated)

I deleted every symbol Task 13 names (VehiclePriority.py; the legacy VCQ dispatch; TWCMaster's queue and priority helpers and the NormalChargeLimit wrappers; Order.dispatch/_succeeded; `attempts()`; the TeslaAPI, TeslaBLE and HomeAssistant command methods) from a copy of d2a7a57. That removes 1,871 lines and leaves **28,339**. The plan also removes the car_api_available wake loop (≈185). Tasks 10–12 add about 350 (Targets ≈100, wiring ≈220, chargeCurrentRequest ≈30). That gives a **post-Task-13 forecast of ≈28,500, 23% above main**, which matches the ledger.

Per-file position after Task 13, against main:

| File | main | after T13 | Δ |
|---|---|---|---|
| TeslaAPI.py | 2,547 | ≈2,120 (≈2,050 if all of car_api_available goes) | **−430 to −500** |
| HomeAssistant.py | 733 | 658 | −75 |
| VehiclePriority.py | 210 | 0 | −210 |
| TeslaBLE.py | 1,493 | 1,674 | +181 |
| VehicleCommandQueue.py | 154 | 324 | +170 |
| TWCMaster.py | 2,022 | 2,166 | +144 |
| Registry + Providers + Reconcile (+Targets) | 0 | ≈4,200 | +4,200 |
| Gen3 (Gen3TWC, Gen3TWCs, provider, WC VINs, TeslaAPI energy) | 608 | ≈1,410 | ≈+800 |
| Telemetry family + token slot | 941 | 1,230 | +289 |
| HTTPControl (Vehicles tab, BLE pairing) | 1,880 | 2,060 | +180 |
| EVSE classes (ChargingPoint, VehicleEndpoint(s) vs Merged, TeslaAPIEVSE, TeslaAPIController) | 479 | 501 | +22 |

**After Task 13, the legacy modules are at or below main as a group.** All of the growth sits in three places:
- the three new packages (≈4.2k);
- Gen3 (≈0.8k);
- the vehicle tab and telemetry (≈0.5k).

The command path shows the problem. Main delivered commands in ≈2,000 lines (VCQ 154, VehiclePriority 210 and the module command methods ≈1,640). After Task 13 the new path takes ≈2,660:
- the provider command methods with TeslaAPI's command, _paidPost and wake helpers (≈660);
- Reconcile (≈1,900);
- Order, Capability, Provider and Suppressions (≈560).

---

## 2. Duplication: new modules against old code that is still alive

The "Task" column says which task deletes the old code: T13 means the plan covers it, MISS means the plan does not.

| New module / symbol | Old code doing the same job, still alive at HEAD | Lines (old) | Task |
|---|---|---|---|
| Registry `Vehicle` fields (Registry/Vehicle.py 284, Fields.py 175) | `CarApiVehicle` (TeslaAPI.py:2528–3061, 534 lines; 462 after T13): 14 `RegistryField` descriptors (TeslaAPI.py:36–55, 2561–2574) plus wake, backoff and error state (`firstWakeAttemptTime`, `firstChargeNeededTime`, `lastAPIAccessTime`, `delayNextWakeAttempt`, `lastChargeNeededTime`, `errorCount`, `lastErrorTime`, `statusDeferral`, `atHome`) | ≈460 | MISS (structural, §4) |
| Registry fields | `HaVehicle` cached `battery_level`, `charge_limit`, `available_current`, `charging`, `lat`, `lon`, `at_home`, `last_state_update` (HomeAssistant.py:61–200). `parse_from_home_assistant` writes the cache and the registry `seen` dict side by side | ≈25 | MISS |
| Registry fields | TeslaBLE per-VIN dicts `_stopTryingToApplyLimit`, `_lastAppliedChargeLimit`, `_stopAskingToStartCharging` (TeslaBLE.py:190–196 and uses) | ≈20 + uses | T10/T13 |
| Registry attach (Telemetry) | `Telemetry.vehicles/unknownVehicles/vehicleNames/orphanedIds/warnedUnmapped` remain as an id→registry-Vehicle map. This is legitimate: it replaced the CarApiVehicle map | — | keep |
| Registry `ReadSource` and `Sources.py` (TeslaBLEReadSource, TeslaAPIReadSource, HomeAssistantReadSource) | **Parallel to the Providers.** `TeslaBLEReadSource.canRead` (Sources.py:35–39) is `TeslaBLEProvider.ready` (TeslaBLEProvider.py:50–55) verbatim. `TeslaAPIReadSource.canRead` restates `OwnerAPIProvider.ready` + `FleetAPIProvider.ready` for reads. `HomeAssistantReadSource.canRead` restates part of `HomeAssistantProvider.ready`. `ReadSource.order` duplicates the provider tier/rank, which `ProviderOrder.orderReadSources` (Order.py:113–128) then reconciles through `source.provider`. `Run._workerOf` maps a source to a worker via its provider name. Two class hierarchies per channel | 201 + ≈50 plumbing | MISS |
| `Providers/Suppressions.commandPolicy` | `VehiclePriority.commandPolicy` and `commandPolicyOverridden` (VehiclePriority.py:79–86) | 8 | T13 (`Suppressions.commandPolicyOverridden` is left orphaned: MISS) |
| `ProviderOrder.candidates` | `ProviderOrder.dispatch` and `_succeeded` (Order.py:136–163, 226–231), `Provider.attempts` and HA's override, all of VehiclePriority (333) | ≈400 | T13 |
| Provider outcome methods (`FleetAPIProvider.*` → `TeslaAPI.command/_paidPost/wakeOutcome`) | `TeslaAPI.car_api_charge` (332), `applyChargeLimit` (195), `setChargeRate` + `_chargeRateAccepted` + `_recordChargeRate` (≈100), `wakeVehicle` (44), `CarApiVehicle.apply_charge_limit` (71), `_unavailableResult` (14) | ≈760 | T13 |
| `TeslaAPI.wakeOutcome` + `wakeDue` + `_askChargeNeed` + `_chargeNeedEnded` + `_wakeSettled` (≈135) | **The whole of `TeslaAPI.car_api_available`** (TeslaAPI.py:443–702, 260 lines): its wake loop and its token and backoff gate. After the simulated Task 13 it has no caller left; every remaining hit is a log string in its own body. The plan deletes only "the charge/limit wake loop inside" it | 260 (plan ≈185) | **MISS ≈75** |
| `TeslaBLE.commandOutcome/_classify` (TeslaBLEProvider) | `TeslaBLE.car_api_charge` (131), `applyChargeLimit` (143), `setChargeRate` (90), `startCharging` (34), `stopCharging` (22), `_allVehicleTargets` (16), `_stampWrite` (10, legacy own-write stamps), `_is_already_satisfied` (3, legacy callers only) | ≈450 | T13 except `_stampWrite` (MISS) |
| Reconciler fallback (`FreeChannel`, `RETRY`, `PAID_AFTER`) | **TeslaBLE's retry layer**, a second policy under the reconciler: `_execute_with_retry` (89, up to 4 tries with backoff), `BLECircuitBreaker` (46, open for 60 s after 5 failures), `_init_retry_stats`/`_record_retry_attempt`/`_calculate_backoff`/`_is_transient_exception` (≈53), `retry_stats`, and the config keys `maxRetries`, `retryDelay`, `circuitBreaker*` | ≈190 | MISS (decision) |
| HA provider outcome methods (`HomeAssistant._post_service`) | `HomeAssistant.car_api_charge` (63), `applyChargeLimit` (65), `setChargeRate` (64), `_vehiclesFor` (9). Left orphaned by T13: `_call_service` (3), `_is_vehicle_connected` (10), `car_api_available` (9), `numCarsAtHome` (4), `minBatteryLevelAtHome` (9, Policy only asks TeslaAPI), `getCarApiVehicles` + `getVehicleCount` (4), and the attributes `lastChargeLimitApplied`, `carApiLastStartOrStopChargeTime`, `minChargeLevel` | 201 + ≈45 | T13 + **MISS ≈45** |
| `Reconcile/HeldLimits.py` (250) + `Rules.py` (137) | Main's `chargeLimits` wrappers took ≈20 lines (TWCMaster.py:923–930, 1479–1481, 1514–1518). HEAD keeps them as shims: `getNormalChargeLimit`, `saveNormalChargeLimit` and `removeNormalChargeLimit` (≈12), **plus `_heldLimitKey`** (21) and **`_adoptListedHeldLimits`** (10). `Rules.decideChargeLimit` turns `HeldLimit` back into main's `(outside, lastApplied=-1)` encoding internally (`_held`, `lastApplied = -1 if …`, `limit = -1 if restore`). That is the old algorithm wrapped, not re-expressed | ≈45 + ≈30 | T13 deletes the three wrappers; `_heldLimitKey` and `_adoptListedHeldLimits` are a **MISS (31)** |
| `Reconcile/Run.RateLimits` (48) + `Workers.allows` | `VehiclePriority._fallbackDue`/`FALLBACK_INTERVAL` (T13). Still alive afterwards: `WallConnectorVinReader._allowed/_calls` (≈15, its own rate window), HA's `CHARGE_SWITCH_LIMIT`, and `TeslaAPI.getCarApiRetryRemaining` backoff (pre-existing). The reconciler's per-aspect `RETRY` (60/300 s) already spaces attempts more widely than any declared limit except HA's 10 s start/stop | ≈80 | MISS |
| `Reconcile/Run.Workers` + generalized VCQ | Legacy VCQ mode: `_DISPATCH`, `_applyChargeLimitKwargs`, `_setAmps`, `_key`, `_is_high_priority`, `_execute`, `cancel`, per-put `callback` (≈60) | 60 | T13 |
| `EVSEInstance/VehicleEndpoint.REFRESH_SECONDS`, `_lastAmps`, `_lastQueuedAt` | `TeslaAPI.CHARGE_RATE_RESEND_AFTER`, `CarApiVehicle.lastChargeRateSent*`, `TWCSlave.__lastAPIAmps*`: three resend throttles for one rate | ≈30 | T12/T13 |
| `ChargingPoint`/`VehicleEndpoint`/`VehicleEndpoints` (501) | They replace `MergedEVSE`/`TeslaAPIEVSE`/`TeslaAPIController` (479). The spec said "the class zoo shrinks"; it is a rename plus 22 lines. `VehicleEndpoints._blindTWCs` and `_telemetryPluggedIn` (≈50) are presence logic that Phase 5 owns, moved rather than deleted. `POWER_FLOWING_AMPS = 1.0` is defined in both VehicleEndpoints.py:26 and Reconciler.py:53 | — | moved, Phase 5 |
| TeslaAPI HTTP | **Four request paths with their own 401/403/410/412/429 handling:**<br>- `CarApiVehicle.get_car_api` (106);<br>- `_paidPost` (83) + `commandRefused` (17);<br>- `loadVehicleList` (60) + `slotRequestFailed` (38);<br>- `_energyGet` + `_energyRefused` + `_refuseWallConnectors` (≈31).<br>Each builds headers and maps status codes to a slot refusal its own way | ≈330 | MISS |

### Size of the suspects named in the brief
- **TeslaBLE +617** breaks down as:
  - BLE status, pairing and range scan, which the spec requires: ≈330 (`scanForVehicleInRange` 58, `_setBleStatus` 42, `bleStatus` 40, `_claimKeyedVehicles` 41, `requestRangeScan`/`runPendingScans`/`requeueIfRequested`/`rangeStatus` ≈60, `_notePairingResult`/`_noteBleRefusal`/`_inPairingWindow`/`_settingsKey`/`_storedStatus`/`blePairingAttempt` ≈80, `_bluezAddresses`/`_heardAddresses`/`bleLocalName` ≈25);
  - outcome classification: ≈70;
  - read-source wiring and registry claims: ≈40;
  - comments: +79.

  Task 13 takes ≈436 back out. What is left over main (+181) is the spec-required BLE status work less the deleted legacy code.
- **TeslaAPI +514** breaks down as:
  - the new command and wake path: ≈260 (`command` 30, `_paidPost` 83, `commandRefused` 17, `wakeOutcome` 95, `wakeDue` 20, charge-need helpers 15);
  - energy-site and Wall Connector VINs for Gen3: ≈150;
  - registry glue: ≈100 (`RegistryField` 19 + descriptors 14, `_bind` 24, `vehicle`/`_liveVehicle` 13, `_telemetryState`/`syncSource`/`syncTimestamp` 19, `_readFresh` 23);
  - comments: +129;
  - reads moved to the cascade: −80.

  After Task 13 it is 430–500 below main.

---

## 3. Task 13 check: what it misses

Method: I deleted every symbol Task 13 names from a copy of d2a7a57. Then I re-scanned the copy for definitions with no reference in code, ignoring strings, comments and tests. A name defined twice (TeslaAPI and HA) was checked as calls minus definitions.

| Missed item | Lines | Why it is dead after T13 |
|---|---|---|
| `TeslaAPI.car_api_available`: everything except the wake loop | ≈75 (260 total, ≈185 planned) | no caller left |
| `HomeAssistant.car_api_available` | 9 | no caller |
| `HomeAssistant.minBatteryLevelAtHome`, `numCarsAtHome`; `TeslaAPI.numCarsAtHome` | 16 | no caller (Policy.py:316 asks TeslaAPI only; numCarsAtHome has no caller on main either) |
| `HomeAssistant.getCarApiVehicles`, `getVehicleCount` | 4 | only VehiclePriority._listUnloaded called them |
| `HomeAssistant._is_vehicle_connected`, `_call_service` | 13 | legacy-only callers |
| `HaVehicle` cached fields and `at_home` (writes in `parse_from_home_assistant`) | ≈25 | nothing reads them once the legacy methods are gone |
| `TeslaAPI.findReason` | 6 | car_api_charge only |
| `TeslaAPI.refuseCommandIfReadOnly` | 16 | legacy only |
| `TeslaAPI.updateLastStartOrStopChargeTime` + `carApiLastStartOrStopChargeTime` (TeslaAPI and HA) | ≈6 | the getter is deleted; WebIPCControl.py:316 also reads the attribute (the plan names only the getter call at :321) |
| `TeslaBLE._stampWrite` | 10 | legacy setChargeRate and applyChargeLimit only |
| `TWCMaster._heldLimitKey` | 21 | only the deleted wrappers call it |
| `TWCMaster._adoptListedHeldLimits` + its call in `loadSettings` | 12 | redundant with `CarApiVehicle._bind`'s adoptLegacyId, which runs on every bind |
| `ProviderOrder._count` | 5 | dispatch only |
| `Suppressions.commandPolicyOverridden` | 3 | only VehiclePriority read it |
| `Provider.vehicleAttachment` + `HomeAssistantProvider.vehicleAttachment` | ≈8 with comments | read only by VehiclePriority |
| `HeldLimits.holding` | 6 | no caller even at HEAD |
| `CarApiVehicle.stopTryingToApplyLimit` reads in `car_api_available` | — | covered once the whole function goes |
| **Total missed** | **≈235** | |

Task 13 also leaves these alone, though they are not orphaned:
- the TeslaBLE retry layer (§2, ≈190);
- the parallel read sources (§2, ≈250);
- the four HTTP paths (§2);
- the RateLimits redundancy (§2, ≈80).

**Line-check risk.** Task 13's own check (`removed ≥ 3,000` since 39d7cfb) is reachable only if these misses are taken. Since 39d7cfb, Task 6 removed 800, Task 7 261 and Task 8 92, about 1,150 so far. The planned Task 13 deletions add about 2,050 (1,871 in my simulation plus the ≈185 car_api_available loop), for ≈3,200 removed. Gross additions, though, are already past the 1,400 budget (the ledger re-forecast says so).

---

## 4. Designs that add without removing

| Layer | What it wraps | Could the wrapped code go? | Saves |
|---|---|---|---|
| `RegistryField` descriptors on `CarApiVehicle` (TeslaAPI.py:36–55, 2561–2574), with `_bind`, `vehicle`, `_liveVehicle`, `syncSource`, `syncTimestamp`, `_telemetryState` | Keeps `CarApiVehicle` as a second per-vehicle object, with `atHome`, the wake and backoff state, and the REST read methods. Callers still look the car up as `vehicle.attachment("TeslaAPI")`: VehicleEndpoints.py:120/287, Gen3TWC.py:282, HTTPControl.py:511, TWCMaster.py:989/1004 | **Yes, as a phase, not a task.** The REST methods (`get_car_api`, `is_awake`, `update_vehicle_data`, `update_location`, `update_charge`) become `TeslaAPI` methods that take a vin. The wake hold and backoff fold into the reconciler's attempt record, or a small per-VIN dict in TeslaAPI. `atHome` moves to presence (Phase 5). Callers read the registry. This is the only change that recovers hundreds of lines and meets spec Goal 1 ("one registry holding all per-vehicle state") | ≈250–350 |
| `HaVehicle` cache next to the registry | HaVehicle holds 7 cached fields plus `at_home`; the registry already holds the same values | The cache can go; HaVehicle shrinks to its entity map (`entity_ids`, `has_*`) | ≈25 (HaVehicle 129 → ≈60 with the cache and location helpers gone) |
| `ReadSource` hierarchy beside `Provider` | Each of BLE, TeslaAPI and HA gets both a ReadSource and a Provider class | Give `Provider` a `fields` set and a `fetch(vehicle, field, allowWake)` method. That deletes `ReadSource.py`'s class, `Sources.py`'s three classes, `VehicleRegistry.registerReadSource/useReadOrder/readSources`, `ProviderOrder.orderReadSources`, the `readSource` attributes on the modules and `Run._workerOf`'s source filter. `cascade()` stays (≈30) and walks `providerOrder.ordered(READ_CHARGE)` | ≈150 |
| `Rules.decideChargeLimit` over `HeldLimit` | It translates back to the `-1` sentinel internally | Rewrite it natively on `HeldLimit` (held None = we hold none; restore = put `outside` back) | ≈30 |
| `HeldLimits` (250) with `storeKey`, `_legacyEntry`, `adoptLegacyId`, `LEGACY_PREFIX`, plus the TWCMaster shims | Lazy migration of `chargeLimits[numericID]` to `heldLimits[VIN]` | Decision: either migrate once at load (resolve IDs from the first vehicle list and keep unresolved ones verbatim), or keep the `chargeLimits` key and tuple format keyed by VIN, with no new key and no downgrade warning | ≈100–150 |
| TeslaBLE retry layer under the reconciler | `_execute_with_retry`, `BLECircuitBreaker`, retry stats | Decision: the provider contract is one classified tesla-control command and the reconciler owns retry. At most one in-call retry for flaky BLE | ≈150–190 |
| Generalized `VehicleCommandQueue` + `Workers` + `runAttempt` hooks | Legacy mode (T13). After T13 there are still four layers (`Reconciler.plan` → `Workers.submit` → VCQ → `runAttempt` → provider) plus:<br>- single-subscriber callback lists (`DesiredStore.onChange`, `VehicleRegistry.onRemove`, `Workers.setReport`), each with its own lock and exception wrapper;<br>- the `_reconcilerParts` lazy import and `isinstance` hook check (Run.py:83–87, 198–201) for a hook with one implementation;<br>- VCQ `inline` mode and `_entries`, used only by tests | Decision: move `runAttempt` into `VehicleReconciler` (the hooks become methods), let the reconciler own its two VCQs, make the callbacks direct calls, and remove test-only modes from lib | ≈150–200 |
| `VehicleEndpoints` presence logic | `_blindTWCs`, `_telemetryPluggedIn` on CarApiVehicle | Phase 5 presence port | moved |
| Persistence: `settings["Vehicles"]` (session stats, BLE keys and status), `settings["vehicleRegistry"]`, `settings["heldLimits"]`, all keyed by VIN | Three VIN-keyed blobs | Decision: fold `heldLimits` into the registry entry. This also removes the migration's case-collision and key-rule code | ≈50 beyond the HeldLimits item |

---

## 5. Over-engineering, dead code, declared-but-unread

### Declared but never read (lib, d2a7a57)
- Read capabilities: `READ_LIST`, `READ_ONLINE`, `READ_PLUG`, `READ_VIN`, `READ_AMPS` and `READ_LOCATION` (Capability.py:6–13) are declared in provider tables and consumed nowhere. `ordered()` skips every passive one, and nobody asks `ordered(READ_*)`. The only read consumer is `orderReadSources`, which uses `READ_CHARGE` for the suppression check and the minimum read tier. About 30 lines of declarations.
- `TelemetryProvider` (34) and `TelmetryBase.providers()` (2): every declaration is passive, so it never enters a walk. Its `ready()` has no caller, and it has no read source. It exists only for `Provider.summary`.
- `Provider.sharedControl`, `Gen3TWCProvider.sharedControl`, `Gen3TWCs.sharedControl`: set and never read.
- `Declaration.passive`: read once, only to skip the passive providers above.
- `Cost.price` is read only in `Provider.summary`. The spec says the cost field must allow a price, so keep the field and drop the reader.

### Built for the Vehicles tab (Phase 6), with no lib consumer
- `Desired._attemptSummary` (10), `AttemptRecord.summary` (16), `FreeChannel.summary` (2), `_desiredSummary` (9), `DesiredStore.summary` (16)
- `VehicleReconciler.summary` (6), `Workers.summary` (2), `VehicleCommandQueue.summary` (12), `Provider.summary` (13)
- Total ≈86. Only `Vehicle.summary` and `VehicleRegistry.summaries` feed a template.

### Orphans at HEAD (no code reference in lib)
- `VehicleRegistry.pointFor` (3)
- `Vehicle.fresherThanWrite` + `FieldStore.fresherThanWrite` (≈9)
- `CarApiVehicle.syncTimestamp` (5)
- `TeslaAPI.energySites` (7)
- `Gen3TWCs.unitTargets` (5), `Gen3TWCs.headroom` (6)
- `ChargingPoint.vehicleEndpoints` (3)
- `HeldLimits.holding` (6)
- `VehicleCommandQueue._entries` (4, tests only)
- Total ≈50.

### One implementation or one caller
- `ReadSource` (3 implementations that mirror the providers; §4).
- `Provider.limitations` (Gen3 only, one caller).
- `Suppressions.noticeOnce` (one caller).
- The `DesiredStore.onChange`, `VehicleRegistry.onRemove` and `Workers.setReport` callback lists (one subscriber each).
- `VehicleRegistry.useReadOrder` (one caller, TWCMaster).
- `ProviderOrder.providers()` (only the startup log line).
- `runAttempt`'s `beforeWrite`/`afterWrite` hook protocol (one implementation, `VehicleReconciler`).
- `CAPABILITY_FOR` as a function over a 3-entry table.

### Dead before this branch (on main as well; deleting them counts toward getting back under main)
| Symbol | Lines |
|---|---|
| TeslaBLE `_kill_process_group` | 48 |
| TeslaBLE `_is_transient_error` | 29 |
| TeslaBLE `BLECircuitBreaker.get_status` | 9 |
| TeslaBLE `closeFile` | 3 |
| Control/APIValidator `validate_required_fields`, `validate_integer`, `validate_string`, `validate_choice`, `is_safe_string` (only `validate_json` is used) | 97 |
| EVSEController `startAllCharging`, `stopAllCharging` | 8 |
| TWCMaster `getSendServerTime`, `setSendServerTime`, `getMasterSign`, `setkWhDelivered`, `delete_background_task` | 20 |
| TeslaAPI `numCarsAtHome` | 3 |
| **Total** | **≈217** |

### Rate limits nobody needs
`RateLimits` (Run.py:132–178), `Workers.allows`, `Declaration.rateLimit` and `FLEET_COMMAND_LIMIT` (whose comment calls it "declared, not enforced", although `RateLimits` does enforce it). At 50 calls per 60 s it can never bind under a 60 s per-aspect `RETRY`. `HA CHARGE_SWITCH_LIMIT` (1 per 10 s) is the only declaration that can bite, and only on a start/stop flip inside a new desire. A minimum gap on `AttemptRecord.lastSentAt` in `plan()` covers that case.

---

## 6. The path to below main

Baseline: ≈28,500 after Task 13 as planned (simulated). Main is 23,180. The gap is ≈5,300.

| # | Change | Est. lines | Owner | Kind |
|---|---|---|---|---|
| 1 | Dissolve `CarApiVehicle` into the registry Vehicle plus TeslaAPI methods that take a vin. `RegistryField` goes; wake and backoff state folds into the attempt record; `HaVehicle` shrinks to its entity map; callers read the registry | −300 (range −250..−350) | **Later phase** (with Phase 5 presence: `atHome`) | **Decision** |
| 2 | Task 13 misses (§3) | −235 | **Task 13** (add them to its list and to the grep test) | Mechanical |
| 3 | Pre-existing dead code (§5): BLE helpers, APIValidator, EVSEController, TWCMaster getters | −217 | **New task 13a**, or a small PR to main first | Mechanical |
| 4 | Dead summaries, declared-never-read capabilities, `TelemetryProvider`, `sharedControl`, HEAD orphans (§5) | −170 (summaries 86 + READ_* ≈30 + TelemetryProvider 36 + sharedControl/passive ≈8 + orphans ≈50 ≈ 210, less ≈40 already counted in #2) | **Task 13** | Mechanical (re-add the summaries in Phase 6 when the tab needs them) |
| 5 | Consolidate the command stack: `runAttempt` into the reconciler, direct callbacks, no test-only VCQ modes | −175 (−150..−200) | **New task after Task 12** | **Decision** |
| 6 | Remove TeslaBLE's inner retry, circuit breaker and retry stats; the reconciler owns retry | −170 (−150..−190) | **Task 13** if approved | **Decision** |
| 7 | Merge `ReadSource` into `Provider` (`fields` + `fetch`); delete the parallel class tree and its ordering plumbing | −150 | **New task 13b** (after T13; touches Run.py's read-before-write) | Mostly mechanical |
| 8 | HeldLimits: migrate once at load (or keep the `chargeLimits` key), `Rules` natively on `HeldLimit`, `heldLimits` optionally folded into the registry entry | −130 (−100..−180) | **Task 10** (it rewires the limit) | **Decision** |
| 9 | One TeslaAPI request helper and one status classifier for `get_car_api`, `_paidPost`, `loadVehicleList` and the energy reads | −120 | **New task 13c** | Mechanical, with tests |
| 10 | Drop `RateLimits`/`Workers.allows`/`rateLimit` and `WallConnectorVinReader._allowed`; replace HA's 10 s gate with a `lastSentAt` minimum gap | −80 | **Task 13** | Mostly mechanical |
| | **Sum of 1–10** | **≈−1,750** | | |

The projection with every item taken is ≈28,500 − 1,750 = **≈26,750, still ≈15% above main**.

The largest remaining levers are user decisions, not deletions:
- **Gen3 cloud VIN** costs ≈410 lines: `WallConnectorVins.py` 182, TeslaAPI energy ≈150, TeslaAPIProviders wall-connector parts ≈20, and the Gen3TWC `cloudVin`/`din`/`refreshVersion`/`_correlate` parts ≈60. The **Gen3 multi-unit headroom solver** costs ≈120 (`solve`, `demandAmps`, `_supply`, `headroom`, `republish`, `_servedLoad`, `_maxFuse`, `unitTargets`, `setUnitTarget`). Both are unverified on hardware, and the user declined dropping them on 2026-10-15 (Option 1). Taking both would bring the projection to ≈26,200.
- The Vehicles tab and BLE status/range work (HTTPControl +180, TeslaBLE ≈330) are spec Goals 7 and 6 respectively, pulled forward from Phases 5–6. They are legitimate, but they are why "Phase 3 should be smaller" does not hold.

**Why below main is not reachable by deletion.** After Task 13 the legacy modules together are already at or below main: TeslaAPI is 430–500 under, HA 75 under and VehiclePriority 210 under, against TeslaBLE +181, TWCMaster +144 and VCQ +170. All of the growth is the three new packages (≈4.2k with Targets), and the spec requires each of them:
- a VIN-keyed registry with per-field source and age, own-write stamps and liveness;
- desired state with reconcilers, classified outcomes and time-aware fallback;
- provider capability, cost and suppression tables.

Getting under main would need:
- (a) item 1 as a full phase, so `CarApiVehicle` and `HaVehicle` stop being second vehicle objects;
- (b) Phase 4 deleting `TWCSlave.send_master_heartbeat`'s per-slave allocation (≈240 lines), which the spec already mandates ("the legacy path is retired, not kept beside the new one"), without growing the distributor by as much;
- (c) shrinking the new packages themselves. Reconcile alone is ≈1,900 lines for three aspects, and Desired.py plus Reconciler.py are still growing (+35 lines in d2a7a57).

A realistic floor with every item above, both Gen3 cuts and a lean Phase 4 is ≈25,500–26,000, which is 10–12% above main.

### Items that need a user decision
1. **Dissolve `CarApiVehicle`** (and slim `HaVehicle`) as a dedicated phase: −250..−350. It is the structural fix for spec Goal 1.
2. **TeslaBLE inner retry and circuit breaker**: delete it, keep one in-call retry, or keep it as it is. −150..−190.
3. **HeldLimits storage**: keep the new `heldLimits` key with a lazy ID migration, migrate once at load, or go back to `chargeLimits` keyed by VIN; and whether to fold it into the registry entry. −100..−180.
4. **Command-stack consolidation**: `runAttempt` into the reconciler, direct callbacks, no test-only queue modes. −150..−200.
5. **Gen3 cloud VIN (−410) and the multi-unit headroom solver (−120)**: declined once (Option 1), re-raised here because they are the largest single levers.
6. **HA's 10 s start/stop gate**: replace the declared rate limit with a reconciler minimum gap (part of item 10, −80).
7. **Phase-6 summaries**: delete them now and re-add with the tab (item 4), or keep them as an API.
