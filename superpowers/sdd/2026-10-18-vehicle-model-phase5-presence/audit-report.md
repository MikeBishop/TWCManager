# Size audit: vehicle-model stack (2e6070f9) against main (03d79325)

Trees: stack `scratchpad/wt-audit` (2e6070f9), main `scratchpad/wt-main` (03d79325). Every count below uses
`find lib -name '*.py' | xargs cat | wc -l` (per file: `wc -l`). Line numbers refer to wt-audit.

## 0. Headline

- **The gap is +3,388 lines (26,568 against 23,180), and the vehicle model accounts for all of it.**
  - `Vehicle/` plus its three new packages come to **+3,736**.
  - Everything else nets **−348**: the EVSE layer −43, the top-level files −251 and EMS/Logging −140.
- **Most of the gap is code, not comments:**
  - code +2,882;
  - comments +469;
  - blank lines +162;
  - docstrings −125.
  The new packages are about 20% comments, which is about main's ratio. Comments aren't the main lever.
- **By phase, net:**

  | Phase | P1 | P2 | P3 | P3.5 | P4 | P5 so far |
  |---|---|---|---|---|---|---|
  | Net lines | +2,348 | +2,087 | −324 | +208 | −915 | +37 |

  Phase 4 carries two commits beyond 57dcea94, so the Phase 5 base is effectively **26,531**.
- **Phase 5 so far is +37. The plan expected about −157 by now.**

  | Task | Actual | Plan |
  |---|---|---|
  | T0 | −171 | −164 |
  | T1 | +33 | +18 |
  | T2 | +70 | −88 |
  | T3 | +105 | +77 |

  Task 2 (Presence) is the overrun:
  - `Presence.py` is already 311 lines;
  - the plan budgeted about 225 for it *after* Task 5.
- **The honest conclusion: the gap is architectural.**
  - Registry, Providers and Reconcile *are* the design: 4,206 lines, about 3,584 of them code.
  - Main's deletions they replaced come to about 2,200: VehiclePriority, MergedEVSE, TeslaAPIEVSE, TeslaAPIController and the TeslaAPI, TeslaBLE, HomeAssistant and TWCSlave trims.
  - Every defensible cut below adds up to **low hundreds of lines, not thousands**.
  - Where the design is heavy:
    - `AttemptRecord`'s 18 fields;
    - the paid-send state machine in `Reconciler.plan()`;
    - the TeslaAPI wake hold underneath it.

  That weight is real and CHANGELOG-promised: "at most four commands per desired value", the wakeDelayMins hold and the numeric-ID held-limit migration. It is "audit before Phase 6" material, not a cut today (§2, Tier D).

**Achievable now, with no behaviour change:**

| Tier | What | Lines |
|---|---|---|
| A | Structural | ≈ −245 |
| B | Mechanical import style | ≈ −110 |
| C | Comment pass | ≈ −95 |
| **A–C** | **Total** | **≈ −450** |

On top of that, Tasks 4–6 built as §4 describes come to ≈ +20 gross instead of the plan's +132, so ≈ 110 fewer lines are added.

## 1. Where the growth is (every module with |Δ| ≥ 50)

| Module | main | stack | Δ | Introduced in |
|---|---:|---:|---:|---|
| Vehicle/Reconcile/Reconciler.py | 0 | 583 | +583 | P3 (+33 P5) |
| Vehicle/Reconcile/Desired.py | 0 | 451 | +451 | P3 |
| Vehicle/Registry/VehicleRegistry.py | 0 | 357 | +357 | P1 |
| Vehicle/Registry/Vehicle.py | 0 | 316 | +316 | P1 (+25 P5) |
| Vehicle/Presence.py | 0 | 311 | +311 | P5 |
| Vehicle/Reconcile/Run.py | 0 | 252 | +252 | P3 |
| Vehicle/Providers/TeslaAPIProviders.py | 0 | 229 | +229 | P2/P3 |
| Vehicle/Reconcile/HeldLimits.py | 0 | 221 | +221 | P3 |
| EVSEInstance/ChargingPoint.py | 0 | 211 | +211 | P2 |
| Vehicle/Providers/Order.py | 0 | 210 | +210 | P2 |
| Control/HTTPControl.py | 1,880 | 2,076 | +196 | P1 |
| EVSEInstance/VehicleEndpoint.py | 0 | 189 | +189 | P2/P4 |
| Vehicle/Registry/Fields.py | 0 | 184 | +184 | P1 |
| Vehicle/Providers/WallConnectorVins.py | 0 | 172 | +172 | P2 (Gen3, keep) |
| EVSEController/Gen3TWCs.py | 354 | 511 | +157 | P2 (Gen3, keep) |
| Vehicle/Telemetry.py | 250 | 398 | +148 | P1 |
| Vehicle/Reconcile/Rules.py | 0 | 127 | +127 | P3 |
| Vehicle/Providers/HomeAssistantProvider.py | 0 | 127 | +127 | P2/P3 |
| EVSEInstance/Gen3TWC.py | 254 | 379 | +125 | P2 (Gen3, keep) |
| Vehicle/Reconcile/Belief.py | 0 | 117 | +117 | P3 |
| Vehicle/Providers/Gen2TWCProvider.py | 0 | 116 | +116 | P2 |
| TWCMaster.py | 2,022 | 2,136 | +114 | P1–P4 |
| Vehicle/Providers/Suppressions.py | 0 | 112 | +112 | P2 |
| Vehicle/Providers/Provider.py | 0 | 110 | +110 | P2/P3 |
| Vehicle/TeslaMateVehicle.py | 325 | 431 | +106 | P1 |
| Vehicle/Providers/TeslaBLEProvider.py | 0 | 104 | +104 | P2 |
| Vehicle/Reconcile/Targets.py | 0 | 98 | +98 | P3 (−47 P5) |
| VehicleCommandQueue.py | 154 | 250 | +96 | P1/P3 |
| Vehicle/Providers/Gen3TWCProvider.py | 0 | 80 | +80 | P2 |
| ControlTick.py | 0 | 75 | +75 | P4 |
| Vehicle/TeslaTokenSlot.py | 274 | 348 | +74 | P3/P4 (#690 refresh lock) |
| Vehicle/Reconcile/Outcome.py | 0 | 73 | +73 | P3 |
| Vehicle/Providers/Capability.py | 0 | 68 | +68 | P2 |
| EVSEController/EVSEController.py | 64 | 0 | −64 | P4 |
| TWCManager.py | 2,039 | 1,962 | −77 | — |
| Control/APIValidator.py | 153 | 46 | −107 | P3 |
| EVSEInstance/EVSEInstance.py | 145 | 27 | −118 | P4 |
| Vehicle/TeslaBLE.py | 1,493 | 1,361 | −132 | — |
| EVSEController/TeslaAPIController.py | 147 | 0 | −147 | P2 |
| EVSEInstance/TeslaAPIEVSE.py | 151 | 0 | −151 | P2 |
| Vehicle/HomeAssistant.py | 733 | 563 | −170 | — |
| EVSEInstance/MergedEVSE.py | 181 | 0 | −181 | P2 |
| Vehicle/VehiclePriority.py | 210 | 0 | −210 | P3 |
| TWCSlave.py | 1,252 | 793 | −459 | P4 |
| Vehicle/TeslaAPI.py | 2,547 | 1,920 | −627 | — |

By directory:

| Directory | Δ |
|---|---:|
| Vehicle/Reconcile | +1,956 |
| Vehicle/Providers | +1,342 |
| Vehicle/Registry | +908 |
| Vehicle/ (top level, Presence included) | −470 |
| Control | +67 |
| EVSEInstance | +58 |
| EVSEController | −101 |
| Top-level files | −251 |
| EMS + Logging + others | −140 |

Overhead the package split carries, measured across all changed files:
- 165 lines of black-wrapped `from x import (...)` beyond one line per statement;
- 67 lines of `__init__.py` re-exports.

## 2. Findings, ranked by lines saved

Every finding can land as a cleanup commit on `vehicle-model/phase5` with no restack. The "Introduced" column says where it would go if you want the lower PR itself to shrink. Phases 1–4 mean restacking #703–#706/#710.

### Tier A: structural, no behaviour change (≈ −290)

**A1. Package `__init__.py` re-exports nobody uses: −67.** Introduced P1, P2 and P3.
- `Vehicle/Reconcile/__init__.py:1-34` re-exports 13 names. Lib uses none of them through the package, and tests use only the submodules `Outcome` and `Run`, which import from an empty `__init__`.
- `Registry/__init__.py:1-19` exports 7 names. Only `VehicleRegistry` is used, by `TWCMaster.py:22`.
- `Providers/__init__.py:1-14` exports 6. Only `ProviderOrder` is used, by `TWCMaster.py:24`. `registerProviders` is already imported from `.Order`.
- **Do:**
  - empty all three files;
  - change two imports in TWCMaster.
- **Bonus:** the circular `Providers/__init__ → Provider → Reconcile/__init__ → Desired → Providers.Capability` path goes away. `Order.py:179-180`'s lazy import of `Attempt` can then move to the top.
- **Risk:** none. **Tests:** none change.

**A2. Desired store: dead and test-only API, a duplicated reset and per-call aspect guards: −40.** Introduced P3.
- `DesiredStore.decision()` (`Desired.py:407-415`, 9 lines): **no caller in lib or tests**, ever since d34792fc.
- `DesiredStore.settled()` and `_settled()` (`:443-447`, `:210-215`, 13 lines): test-only. Tests can assert `record(...).settledAt >= get(...).at`, or use a helper in `reconcile_helpers.py`.
- `AttemptRecord.newDesire()` (`:131-149`) resets twelve fields one per line.
  - Replace it with one tuple assignment of the volatile fields only.
  - Never route it through `self.__init__()`. `plan()` reads `rec.inFlight` without the store's lock (`Reconciler.py:252`), and `newDesire` runs with an attempt in flight. Nulling `inFlight` even briefly lets a pass submit a duplicate.
  - `inFlight`, `lastProvider`, `lastSentAt` and `pendingSave` are left untouched, since `MIN_SEND_GAP` spans desires.
  - Saves about 6.
- `_checkAspect` (`:59-61`) is called 8 times, and `ASPECTS` exists only for it.
  - Saves about 12.
  - Keep `adopt`'s explicit `ValueError`: `test_outcome_desired.py:38-39` pins it.
- **Risk:** low. **Tests:** the about 7 `settled(` asserts are rewritten.

**A3. `FieldStore` and `Vehicle` are two layers over one record: −35.** Introduced P1.
- `Vehicle` forwards `latest`, `reported`, `lastWrite` and `noteWrite` (`Vehicle.py:118-126`, `:212-213`).
- It also wraps `age` and `trusted` (`:173-189`) around `FieldStore.age` and `trusted` (`Fields.py:132-180`).
- `snapshot()` serves only `summary` and the anonymous merge (`VehicleRegistry.py:240`).
- **Do:** fold `FieldStore` into `Vehicle`.
  - Keep a separate field lock (the leaf-lock rule).
  - Keep `Observation`, `FIELDS` and the constants in `Fields.py`.
- **Risk:** low (lock placement). **Tests:** `FieldStore` appears 15 times in one test file.

**A4. Provider boilerplate: −40.** Introduced P2.
- **One-field wrapper:** `Capability.Declaration` (`Capability.py:67-68`) wraps a single `Cost`, and `Provider.declarations()` (`Provider.py:41-42`) just returns the class attribute. Make `DECLARATIONS` a `{capability: Cost}` map.
- **Duplicate capability lists:**
  - `TeslaBLEProvider.CAPABILITIES` (`:22-29`) duplicates the keys of its own `DECLARATIONS`; HomeAssistantProvider has the same pair (`:18-24`, `:37-43`).
  - Write `dict.fromkeys(COMMANDS | {READ_CHARGE}, LOCAL)` and `dict.fromkeys((COMMANDS - {WAKE}) | {READ_CHARGE}, HA_BILLED)`.
  - `ready()` then uses `self.declares(capability)`.
- **Owner and Fleet `DECLARATIONS`** (9 lines each) shrink the same way.
- **`ampsRange` written three times:** TeslaAPI (`TeslaAPIProviders.py:72-75`), BLE (`:54-60`) and HA (`:84-88`) each fetch config and return `(1, vehicleMaxAmps(...))`. Use one `Provider.carAmpsRange` helper and assign it in all three. Don't make it the base default: the test doubles rely on `None`.
- **Dead TWC `setAmps`:**
  - `Gen2TWCProvider.setAmps` (`:90-96`) and `Gen3TWCProvider.setAmps` (`:68-69`) have no production caller.
  - `Reconciler.plan` drops `module is None` providers for AMPS (`Reconciler.py:319`), and so does `debugCommand` (`Order.py:173`).
  - Only `test_gen2twc_provider.py:192` calls them.
  - The `SET_AMPS` declaration stays: it feeds `ampsRange` and the local-amps rule.
- **Risk:** none to low. **Tests:** 25 `C.Declaration(...)` uses in 13 test files become plain `Cost`s.

**A5. `Vehicle.summary()` builds the dropped merged field view: −20.** Introduced P1; dead since the spec change of 2026-10-18.
- The templates read only these keys: `anonymous`, `point`, `vin`, `name`, `lastSeenAge` and `lastSeenSource` (`vehicles.html.j2:20-31`, `vehicleDetail.html.j2:16-26`).
- These keys are built for nobody:
  - `fields`, with per-field `age` and `changedAge` (`Vehicle.py:295-303`);
  - `claims` (`:285-288`), since the pages use `providerLines`;
  - `key`, `userAsserted` and `lastSeen`.
- The only other consumer is the WebIPC debug dump (`WebIPCControl.py:330`, through `VehicleRegistry.summaries()`).
- **Do:** trim `summary` to the six keys.
- **Risk:** low. The WebIPC debug dump loses its per-field detail. The CHANGELOG's "the debug dump reads vehicles from the registry" still holds.
- **Tests:** `test_registry_vehicle.py:64-183`, which asserts `fields` and `claims`, gets rewritten.
- Fits Task 6, which touches these pages anyway.

**A6.** Withdrawn after review; see "Checked and not recommended".

**A7. Phase 5 left a read helper behind: −12.** Introduced P1; orphaned in P5.
- `TeslaAPI._readFresh` (`TeslaAPI.py:1802-1824`) has one caller left, `update_charge` (`:1919-1920`), now that `update_location` has gone.
- The only lib caller of `update_charge` (`:1638`) ignores the return value.
- **Do:** `update_charge` becomes `obs = vehicle.read(...)`, plus the BLE-proves-awake stamp.
- **Risk:** none in lib. **Tests:** `test_reads_no_wake.py` (14 references) asserts the stale-means-False result, so those asserts change.

**A8. Three case-insensitive lookups into `settings["Vehicles"]`: −12.** Introduced P1.
- The three copies are:
  - `TeslaBLE._settingsKey` (`TeslaBLE.py:951-967`);
  - `HTTPControl._vehicleRecordKey` (`HTTPControl.py:130-135`);
  - the inline `any(k.upper() == vin ...)` (`:114`).
- `canForgetVehicle` (`:138-151`) also re-reads the BLE status that `TeslaBLE._storedStatus` already reads.
- **Do:** one helper next to `isWellFormedVIN`, and `canForget` calls `bleStatus`.
- **Risk:** none.

**A9. Telemetry attach and load duplicates: −12.** Introduced P1.
- `TelmetryBase.updateVehicles` repeats its 5-line "attach, un-orphan, un-warn and log" block (`Telemetry.py:362-367`, `:383-388`). Make it one `_attach()`.
- `TeslaMateVehicle.loadCarVINs` has two identical `except` blocks (`:129-136`, `:143-148`). Collapse them into one `try`.
- **Risk:** none.

**A10. Small duplicates: −6.**
- `POWER_FLOWING_AMPS` is defined twice: `Belief.py:15` (P3) and `VehicleEndpoint.py:24` (P4).
- `Run.workerOf` and the `getattr(provider, "worker", "cloud")` pattern appear at `Run.py:97-100` and `:177`.

Tier A total: 67 + 40 + 35 + 40 + 20 + 12 + 12 + 12 + 6 = **≈ −245**.

### Tier B: mechanical import style (≈ −110), introduced P2 and P3

The new modules import names in black-exploded tuples. A few examples:
- `Reconciler.py:22-64` is 42 lines for 13 statements.
- `Run.py` is 25 lines for 9 statements.
- `Desired.py` is 22 lines for 6.
- `TeslaAPIProviders.py` is 22 lines for 5.
- `TeslaBLEProvider.py` is 16 lines for 4.

The tests already use the module style, `Capability as C` and `Outcome as O`. Using it in lib recovers about 118 of the 165 wrapped lines, minus a little re-wrapping.
- **Risk:** none.
- It is cosmetic, so take it only as a final mechanical commit (a cheap model).

### Tier C: comments (≈ −95, lowest priority)

These are module headers and docstrings that restate the code. The comment rule allows "why" only.

| Location | Lines now | Lines after |
|---|---:|---:|
| `Reconciler.py:1-21` | 21 | ~8 |
| `HeldLimits.py:1-16` | 16 | ~6 |
| `VehicleCommandQueue.py:1-15` | 15 | ~6 |
| `Rules.decideChargeLimit` docstring (`:302-321`), which restates the branches below it | 20 | ~5 |
| `needsLiveRead` docstring | 8 | 3 |
| `WallConnectorVins.py:1-13` | 13 | 7 |
| `Run.py:1-10` | 10 | 4 |
| `Outcome.py:1-8` | 8 | 4 |
| `Desired.py:1-7` | 7 | 3 |
| `_blindTWCs` docstring (`VehicleEndpoint.py:337-350`) | 13 | 5 |
| `vehicleEndpoints` docstring | 12 | 5 |
| ChargingPoint header | 10 | 5 |
| VehicleEndpoint header | 10 | 5 |

### Checked and not recommended

- **`Targets.presentVehicles` against `Presence.candidates(master, capability)`.**
  - They look alike, but their audiences differ: presentVehicles includes `twcVin` cars, HA cars and the anonymous car for start/stop.
  - F11 pins the broadcast audience, so merging them moves behaviour. No cut.
- **The Gen3 parts** (`WallConnectorVins`, cloud VIN, `Gen3TWCs` +157, `Gen3TWC` +125). Gen3 is essential and stays.
- **`commandPolicy api_only`** (`Suppressions.noticeOnce`, `TeslaBLEProvider.SUPPRESSED`). It is a CHANGELOG feature and stays.
- **The HeldLimits tie-break (`HeldLimits.py:156-161`, `_loadedVins`).** It is not a rare-case nicety. Take an upgrade boot holding `{"12345": [90, 50]}`:
  1. Before the vehicle list arrives, policy saves `[50, 50]` under the VIN.
  2. The "recorded since load: keep the hold" branch then writes `[90, 50]` back.
  3. Under "VIN wins" the restore would send 50, and the real outside limit of 90 would be lost.
  Keep it.
- **`TeslaTokenSlot` +74.** That is the per-slot refresh lock (#690), a threading goal.

### Tier D: design weight, to audit before Phase 6 (not a cut now)

**D1. Paid-send pacing has three mechanisms stacked on each other.** Introduced P3 and P5.

| Layer | Where | What it is |
|---|---|---|
| 1 | `TeslaAPI.wakeOutcome`/`wakeDue` and the `CarApiState` hold fields (`TeslaAPI.py:1478-1610`, about 130 lines) | main's wakeDelayMins hold |
| 2 | Reconciler arm/re-arm: `paidSends`, `paidReached`, `paidRetryDue`, `rearmed`, `wakeCheckBy`, `WAKE_CHECK` (`Reconciler.py:337-391`, `_limitSpent` `:468-487`, `Desired.noteOutcome` `:364-379`, about 110 lines) | per-desire paid sends |
| 3 | Phase 5's `PAID_BUDGET`/`paidSpent` (`:381-384`, `:513`) | a second per-desire budget |

- One counter, "paid requests per desire ≤ 4, spaced by RETRY, with a WAKE_CHECK follow-up", could replace layers 2 and 3. That would save about 50–60 lines.
- But the CHANGELOG states layer 2's exact contract ("once, once more after a failure or a reading..., two more...").
- The parity rows pin the counts and timings.
- It needs a user decision on whether the published contract may simplify. Then Fable review. Not now.

**D2. `AttemptRecord` has 18 fields.** Several of them exist only for D1. Shrinking it follows from D1.

## 3. Recommended cut plan (on `vehicle-model/phase5`, before Tasks 4–6)

Each task keeps the full suite green. `test_command_path_parity.py` counts and timings stay untouched.

**Task X1, packages and imports (cheap model): Δ ≈ −67, plus ≈ −110 if Tier B is taken.**
- Empty the three `__init__.py` files and fix the two TWCMaster imports. Move `Order.py`'s lazy `Attempt` import to the top.
- If you take Tier B, convert the Reconcile and Providers modules to `from ..Providers import Capability as C` and `from . import Outcome as O`.
- Tests: the full suite. No test edits.

**Task X2, Desired store and Provider boilerplate (sonnet): Δ ≈ −86.**
- A2: delete `decision()`; move `settled()` into the test helper; `newDesire` as one tuple reset that never touches `inFlight`; drop `_checkAspect`.
- A4: `DECLARATIONS` as `{cap: Cost}`, `dict.fromkeys`, one `carAmpsRange`, delete Gen2/Gen3 `setAmps`.
- A10.
- Tests: `test_outcome_desired.py`, `test_limit_reconciler.py`, `test_provider_*.py`, `test_gen2twc_provider.py`, `test_teslaapi_providers.py`, the parity file (unchanged).

**Task X3, Registry layer (sonnet): Δ ≈ −55.**
- A3: fold `FieldStore` into `Vehicle`.
- A5: trim `summary` and `summaries`. Alternatively A5 goes with Task 6.
- Tests: `test_registry_vehicle.py`, `test_registry_*.py`, `test_telemetry_registry.py`.

**Task X4, leftovers (sonnet): Δ ≈ −36.**
- A7 `_readFresh`.
- A8 the `Vehicles` key helper.
- A9 Telemetry and TeslaMate.
- Tests: `test_reads_no_wake.py`, `test_vehicles_page.py`, `test_teslamate*.py`.

**Optional Task X5, comment pass (cheap model): Δ ≈ −95.** The Tier C list.

**Realistic Phase 5 end state:**

| Step | lib lines |
|---|---:|
| Now | 26,568 |
| X1–X4, structural Tier A (≈ −245), no Tier B | ≈ 26,323 |
| Tasks 4–6 per §4: T4 ≤ +10, T5 ≈ −20, T6 ≈ +30 gross, ≈ +20 in all | ≈ 26,345 |
| With Tier B and Tier C as well (≈ −205) | ≈ 26,140 |

- That leaves the gap to main at ≈ 2,960–3,165. The plan projected 26,425.
- **Below main is not reachable by cleanup.** It would need D1 or a smaller Reconcile design, which is the Phase 6 design question.
- Target to set: **Phase 5 ends ≥ 185 below its base (26,531)**, or ≥ 390 below it with Tiers B and C.

## 4. Building Tasks 4–6 at ≤ 0 net

**Task 4, the Gen2 unplug filter (plan +41; target ≤ +10).**
- Don't add a parallel 00-run state machine on `TWCSlave`. `TWCMaster.observeChargingSessions` (`TWCMaster.py:1295-1362`) already runs per slave on the serial thread, with these pieces:
  - a debounce stamp (`chargingDroppedBelowThresholdTime`);
  - the session counter `plugSessions`;
  - the `reportedState == 0` branches (`:1351-1362`).
- Put the 00-run onset, the `_beforeMax` capture and the 60 s debounce in that loop's `else` branch, reusing a single onset stamp.
- **Delete these:**
  - the charge-stop `_plugSession(slave, False)` (`:1346`);
  - the `isAnonKey` 00 close (`:1360-1362`) if the filtered unplug subsumes it;
  - `Gen2TWC.vehicleKey`'s `lastVIN` branch (`Gen2TWC.py:49-51`).
- Filter (b) is already one call, `Presence.telemetrySaysPlugged`.
- The unplug write is `observe("pluggedIn", False, "Gen2TWC")`. `noteObservation` already marks `unplug` for a Gen2TWC source (`Presence.py:126`), so no new mark code is needed.
- `LINK_GRACE` can reuse the slave's existing `heardFrom` and first-reply time instead of a new `linkReady()`.

**Task 5, VIN-less attribution (plan +51; target ≤ −20).**
- **Don't port `PresenceAttribution.py` verbatim (71 lines).** This overrides the plan's decision ("ported verbatim", with `test_presence_attribution.py`'s 10 tests changing "only the import"). The cost is rewriting those 10 tests against the filter.
- Write pilot matching as a filter over `Presence.candidates(master)`, about 25 lines: keep cars whose TeslaBLE `availableCurrent` and `actualCurrent` are within 1 A of the point's offer and actual. The single-car guess stays decisive (F12), about 8 lines.
- **Delete these:**
  - `TWCSlave.pluggedCars` with its imports (`TWCSlave.py:7-9`, `:116-127`, 15 lines plus 3);
  - `ChargingPoint.anonymousCars` (`ChargingPoint.py:182-190`, 9);
  - the `Gen3TWC._correlate` candidate loop and `CORRELATE_WINDOW` (`Gen3TWC.py:69`, `:274-298`, about 24);
  - the `pluggedCars()[0]` probe (`TWCMaster.py:1352`).
- Net: about −52 removed against about +35 added, so ≈ −17 to −20.
- No `Candidate` NamedTuple. Build reach, inside and plugged from the `Presence` helpers that already exist (`pluggedNow`, `inside`, `markAt("contact")`).

**Task 6, the Vehicles page (plan +40; target ≤ 0).**
- The Presence column is one template expression through a `presence` global, about 2 lines.
- Write `pendingCommands(master, vin)` with a fixed vocabulary, about 30 lines. Its pieces already exist:
  - `rec.lastOutcome.detail`, which already carries `"rules: held: <why>"`;
  - `Reconciler._whyNoWake`'s strings;
  - the `_said` hands-off and no-provider messages, which only need a public `said(key, aspect)` accessor in place of new wording;
  - `sourceName` and `ageText`, which are already there.
- Gross ≈ +30–32. A5 (the `summary` trim) and A8 already count in Tier A. If they land with Task 6 instead of X3/X4, the task nets ≈ 0 and Tier A drops by 32.

## 5. Notes on method

- **Dead-code calls** were checked with grep over `lib/` (py, j2, js) for method-call and attribute patterns. Test-only callers are reported as test-only.
- **`Provider` command methods** look uncalled to a grep, but `Run._call` reaches them through `getattr(provider, capability)`. They aren't dead. The Gen2/Gen3 `setAmps` finding rests on the reconciler and debugCommand `module is None` exclusions, not on the grep.
- **Phase attribution** was checked by grepping each symbol in `vehicle-model/phase1` … `phase4`.
