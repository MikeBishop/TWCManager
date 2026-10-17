# Pre-flight review: Phase 3.5 (dissolve CarApiVehicle)

Plan: `.superpowers/plans/2026-10-16-vehicle-model-phase3.5-carapivehicle.md`
Code: `scratchpad/wt-vm35` @ db47522 (lib = 27,270 by both `git ls-files` and `find`; matches the plan).
Method: read-only. Every claim below was checked against db47522 source and tests. Nothing was executed except greps and `git log`.

## Verdict: **go-with-fixes**

The architecture is sound and the two folds are correct on the reachable paths. There is no new paid call and no lock-order change. Every symbol the plan deletes exists at the cited line. The defects are in test mapping and retargeting: three tasks would hit unplanned red tests or unmapped deletions. There are also two small behaviour edges, in Task 1's `waiting()` and in Task 3's fold 1. The fixes are all plan text, not design.

---

## 1. Task pairs sharing a file or interface

| Pair | Producer → consumer | Conflict? |
|---|---|---|
| T1 ↔ T3 (`TeslaAPI.listPending/loadList/resolveHeldLimits`, `test_limit_wiring.py`) | T1 changes what `HeldLimits.waiting()` means; it now reads `settings["chargeLimits"]`. T3 replaces `len(carApiVehicles)` with `bool(registry.attached("TeslaAPI"))` in the same three methods. | No code conflict. **Test conflict:** T1 edits the fixture of `test_legacy_ids_resolve_once_from_the_first_vehicle_list` (l.95–99). T3 must rewrite the same test's re-list (l.115). The plan says "use a fresh `api_with_registry()`", which cannot work here (finding 5). |
| T2 → T3 (`Vehicle.telemetryState/syncSource/SYNC_TIMEOUT`) | T2 adds them; T3's `is_awake(vehicle)` consumes `vehicle.telemetryState()` and `vehicle.SYNC_TIMEOUT/4`. | Consistent. |
| T2 → T3 (`Targets.py`) | T2 rewrites l.66 (`v.value("lat",10000)`) and l.136 (`vehicle.syncSource`). T3 rewrites `located(master, v)` (l.20–26, 37, 66) and l.137 (`update_location` through the module). | Consistent; the edits touch disjoint lines. |
| T2 → T3 (`getLastVehicle`, `HTTPControl:509–514`) | T2 returns the registry Vehicle and reads `attachment("TeslaAPI").atHome`. T3 makes that attachment `CarApiState.atHome`. | Consistent. |
| T2 → T3 (`RegistryField`, `actualCurrent` descriptor) | T2 keeps `RegistryField` and renames `_actualCurrent` to `actualCurrent`; T3 deletes both. | Consistent: `update_vehicle_data`'s `setattr(self,"actualCurrent",…)` still lands in T2. |
| T2 ↔ test stubs (`test_vehicle_endpoint`, `test_charging_points`, `test_gen2_idle_minimum`) | These tests attach a `SimpleNamespace(syncSource=…, pluggedIn=…, locate=…)` as "TeslaAPI". T2 makes `_telemetryPluggedIn` read the registry, so the stub fields stop driving behaviour. | **Yes**: `test_vehicle_endpoint.py::test_controller_lists_at_home_api_cars_and_keeps_blind_rules` (l.64) breaks in T2. T2's file list omits it (finding 1). |
| T3 → T4 (guard, comments) | The T4 guard includes T1's `startswith("id:")` and T3's names. T3's own Step 5 grep (`CarApiVehicle` → 0 in lib) already forces three comments T4 lists later: `TeslaAPI.py:172`, `TeslaAPIProviders.py:139` and `Reconciler.py:64,74`. | Harmless overlap. The T4 sweep list should drop what T3 must already do. |
| T1 → T4 (live check) | T4 step 1 stops if `id:` keys exist on the box. | The check comes after T1 is built. Do it before T1 (finding 19). |

## 2. Per-task checks

| Task | Tests match code? | Files created / touched later | Deleted symbols exist at db47522? | Callers of deleted symbols handled? |
|---|---|---|---|---|
| **T1** | Mostly. The five characterization tests all pass at BASE by reading (traced `load`/`resolveLegacyIds`). **But** Step 2's "every assertion stays" is false: `test_limit_wiring.py:99` asserts `chargeLimits == {"11","22","33"}`, and moving `id:44` into `chargeLimits["44"]` adds `"44": 75` to it (finding 4). | No new files. `test_limit_wiring.py` is touched again in T2 (l.202) and T3 (l.115, 220–221). | Yes: `_waiting` :91; `id:` :118–123 and :214–215; `vins` :281. | `vins()`: tests only (`test_held_limits.py:142,207,252`), plus a comment at `HeldLimits.py:247`. `_waiting`: no outside reader. `"id:"`: lib only. Docs/html/templates: none. |
| **T2** | No. The "same syncSource retargeting" list names `test_teslaapi_providers`, `test_teslaapi_readonly_gate` and `test_reads_no_wake`, which have **no** `syncSource` reader. It misses `test_limit_wiring.py:202` (`car.syncSource`), `test_telemetry_registry.py:264–272` (listed) and the stub-driven `test_vehicle_endpoint.py:64` (finding 1). One deletion is unmapped: `test_reads_no_wake.py::test_ble_actual_current_change_is_timed` (l.158–163) reads `lastCurrentChangeTime` (finding 2). | No new files. | Yes: `syncTimeout` :1592, `_telemetryState` :1639, `syncSource` :1649, `actualCurrent` :1949/1953, `lastCurrentChangeTime` :1586. | Lib readers: `HTTPControl:509–514`, `TWCMaster:679–692`, `Targets:66,136`, `VehicleEndpoints:81–90,122`. All are listed and none is missing. The plan cites `Gen3TWC.py:282`; the file is `EVSEInstance/Gen3TWC.py:281`. |
| **T3** | Mostly. The characterization and interface tests are well aimed, but `test_a_listed_car_is_never_forgotten_or_expired` is half vacuous (finding 8). The tri-state changes asserted values in three tests the plan treats as plumbing (finding 3). | `git mv` of `test_carapivehicle_registry.py` breaks **8 importers**: `test_held_limits:260,380`, `test_provider_outcomes_cloud:8`, `test_provider_tables:15`, `test_teslaapi_providers:10`, `test_teslaapi_readonly_gate:152`, `test_vehicle_endpoint:10`, `test_wall_connector_vins:8` (finding 14). | Yes: `RegistryField` :39, `CarApiVehicle` :1540, `carApiVehicles` :139, `getVehicleByVIN` :779, `ready` :1655, `_bind` :1604, `_liveVehicle` :1622, `READ_MAX_AGE` :1565, `Reconciler.READ_MAX_AGE` :75. | Lib: complete (`TeslaAPIProviders:55,140,163–164,184`, `Targets:26,137`, `TWCSlave:113`, `TeslaBLE:189`). The comment at `TeslaAPI.py:172` is not listed, but the Step 5 grep forces it. Templates: `debug.html.j2:74` only needs a truthy attachment, OK. `docs/`, `html/`, `tests/integration`, `tests/API`: no hits at BASE (verified). `Policy.policyValue` uses `getattr(module, name, value)`, so a policy naming `carApiVehicles` degrades to the literal string and does not raise. `Reconciler.READ_MAX_AGE` has no importer. |
| **T4** | The guard pattern is valid ERE. The Python adjacent-literal concatenation inside the list works. | — | n/a | `CHANGELOG.md:23` is wrong at BASE and stays wrong (finding 20). |

## 3. Hidden behaviour changes

**Paid calls.** No new paid request on any normal path. There is one edge in fold 1 (finding 6):
- Today `ready()` makes a second `is_awake()` call, with `slot=None` and a fresh `now`.
- If that call crosses the 120 s cache boundary, or sees TeslaMate flip to "asleep" between the two calls, today's code does one free GET and may skip `vehicle_data`.
- After the fold, `vehicle_data` ($0.002) is sent.

The probability is tiny, but the plan's wording "provably identical on every reachable path" is too strong.

**Thread safety and lock order.** No change:
- `CarApiState` is mutated exactly as `CarApiVehicle` was.
- `registry.attached()` takes the registry leaf, releases it, then takes each `Vehicle._lock` in turn.
- `vehicleListLock → registry` already existed.
- `Policy` reads (`numCarsAtHome`/`minBatteryLevelAtHome`) now take registry leaf locks from the main thread. Leaf locks are allowed.

**Settings persistence (Task 1):**
- A user whose `settings.json` still has numeric-ID `chargeLimits` sees no change: the IDs wait on disk, `waiting()` is True, and they resolve at the first non-empty full listing.
- A **non-dict truthy** `chargeLimits` (list or string): at BASE `waiting()` is False. Under the plan it is True **forever**. `listPending()` is then True every 5 min (`TWCManager.py:1014`), which queues `loadVehicleList`, and `resolveHeldLimits` lists every usable slot. These are free GETs, but forever (finding 9).
- `"id:"` keys:
  - Only `deploy/phase3-live` (= db47522) contains the writer `0fd13a1`.
  - That build also contains the resolver that deletes those keys.
  - No other deploy branch contains the writer.
  - So the plan's claim holds. Any leftover would sit harmlessly in `heldLimits` (`_snapshot` filters non-VINs).

**Task 1 exactness.** One divergence from today, finding 10:
- Two numeric IDs name one VIN, and that VIN was loaded with a malformed store entry.
- BASE: the second ID sees `kept=True` (`_loadedVins`), so the first ID's value is kept.
- Plan: `vin not in written` blocks the skip, so the second ID merges `(limit2.outside, own.held)`.

**Forget race (rejoin removal).** `forgetVehicle` runs `canForgetVehicle` and then `registry.forget` without atomicity (`HTTPControl.py:117–119`). If the first listing attaches a user-asserted VIN in that window:
- Today: the next `update_charge` rejoins through `CarApiVehicle.vehicle`.
- Under the plan: the car is gone from `attached()` until restart, if any other car is listed.

It is reachable only by a race, so it is Low (finding 7). The plan's claim "nothing in production can forget a listed car" should say "except this race".

**Ordering.** `updateChargeAtHome` and `numCarsAtHome` now iterate in registry order (sorted VIN), not list order:
- Counts and minimums are unchanged.
- Only the order of per-car reads changes (Info).
- The `TWCSlave.py:132` comment is already false, as the plan notes.

**`addVehicle` and malformed listings.**
- A listing that lacks `id` no longer raises `KeyError` (acknowledged).
- A listing with a lowercase VIN and a null `display_name` gets an upper-case name (negligible).

**`get_car_api(checkReady=False)` in tests.** Fourteen direct calls passed `provesOnline=True` by default:
- `request_errors:78,99,181,304,340,380`
- `token_slots:241,263,280,419,432`
- `providers:109`

After the merge they no longer set `lastAPIAccessTime`. No current assertion depends on it (checked), but the report should note it.

## 4. Lib-delta realism; missed deduplication

| Task | Plan | Assessment |
|---|---|---|
| T1 | −65 (−55..−75) | **Optimistic.** Today's messages (4 load warnings, 1 resolve warning, 1 info) are about 37 formatted lines, and the deferred-log collection under `black` costs about the same. Logic shrinks from about 70 lines to about 40. Expect **−40..−55**. |
| T2 | −20 | Realistic: about −37 in `CarApiVehicle`, about +18 in `Vehicle.py`. |
| T3 | −155 | Plausible. The plan's itemisation adds up to about −140 before re-wrapping. Each re-homed method needs a `car = vehicle.attachment("TeslaAPI")` line (about 8 methods, +8). `_listed` (+4) and the `Targets` master plumbing (+2) are extra. Expect **−130..−155**. |
| T4 | −5 | OK. |
| **Total** | ≈27,025 | Likely **≈27,040–27,070**, before the extras below. |

Extra behaviour-neutral savings the plan missed:

| Where | Change | ≈ lines |
|---|---|---|
| `TWCSlave.py:131–137` (`_anonCars`) | `listed = [v for v, _ in self.master.vehicleRegistry.attached("TeslaAPI")]`. Same registry order. | −3 |
| `VehicleEndpoints.py:115–123` (`allEVSEs`) | Loop over `attached("TeslaAPI")` pairs. The `isAnonymous` skip is redundant because an anonymous vehicle never has the attachment. | −3 |
| `HeldLimits.py:275–282` | Once `vins()` goes, inline `_snapshot` into `holding()` (its only caller). | −3 |
| `TeslaAPI.py:1502–1504` (`vehicleIsDefinitelyHome`) | Replace the nested `say()` with `logger.log(logging.INFO2, …)` directly. Same text and level. | −3 |
| `HomeAssistant.py:216,404,579–596` | HA's own `carApiVehicles` list → `registry.attached("HomeAssistant")`. Same pattern as T3. Optional: it is outside the CarApiVehicle scope, and the discovery log at l.263–268 iterates the list. | −2..−4 |

These total about **−12..−16**. Two further levers change log wording or are cosmetic, so they are not taken:
- merging `update_vehicle_data`'s three `try` blocks (about −14);
- the backoff DEBUG2 formatting.

## 5. Deleted and changed test mapping

| Test | Task | Plan mapping | Should be |
|---|---|---|---|
| `test_carapivehicle_registry::test_actual_current_change_time_only_moves_on_change` | T2 | PLUMBING-ONLY | OK |
| `test_reads_no_wake::test_ble_actual_current_change_is_timed` | T2 | **missing** | PLUMBING-ONLY (same reason: no lib reader of `lastCurrentChangeTime`). Its `latest("actualCurrent").source == "TeslaBLE"` half is covered by `test_ble_read_fills_fields_and_api_untouched`. |
| `test_registry_callers::test_get_last_vehicle_uses_registry_attachment` | T2 | INTENTIONALLY CHANGED | OK |
| `test_vehicle_endpoint::test_controller_lists_at_home_api_cars_and_keeps_blind_rules` | T2 | **missing** | Plumbing: observe `state` from `TeslaMateVehicle` and `pluggedIn=True` on the registry vehicle in place of the stub fields. Assertions unchanged. |
| `test_limit_wiring.py:202` (`car.syncSource`) | T2 | **missing** | Plumbing |
| `test_limit_wiring::test_legacy_ids_resolve_once…` l.99 | T1 | "plumbing, every assertion stays" | Fixture plumbing, **but l.99's expected dict gains `"44": 75`**; say so. |
| `…::test_writes_after_forget_land_on_the_live_vehicle`, `…_and_relist_by_another_provider`, `…::test_relisting_the_api_attaches_the_new_car`, `…::test_attributes_are_observations_with_source_and_defaults` | T3 | as listed | OK, but the third's mapping (`test_a_failed_boot_list_load_recovers_without_an_arrival`) covers a failed list, not a re-list. Say "no replacement: re-list after forget is unreachable". |
| `test_provider_outcomes_cloud::test_a_cached_failed_check_stays_unknown` (l.206–208) | T3 | treated as plumbing, cited as an unchanged pin in Review Focus 3 | **INTENTIONALLY CHANGED**: `is False` → `is None`. The l.207 step (Known leaked by telemetry) has no tri-state analogue and is deleted, because the bug class is structurally gone. |
| `test_teslaapi_token_slots::test_no_usable_slot_makes_no_requests` l.173 | T3 | missing | INTENTIONALLY CHANGED (`is_awake()` → None) |
| `test_teslaapi_token_classification::test_unknown_token_makes_no_api_calls` l.127 | T3 | missing | INTENTIONALLY CHANGED (same) |
| `test_registry_membership::test_find_by_name_and_attached` | T3 | INTENTIONALLY CHANGED | OK |
| `test_reads_no_wake` (setup patches `car.is_awake` and `car.update_vehicle_data` as instance attributes; `del car.update_vehicle_data` at l.200) | T3 | plumbing | OK. The patches move to `api.*` with a `(vehicle, slot=None)` signature. |

---

## Numbered findings

1. **[Medium] T2 test retarget list is wrong.** It misses `test_limit_wiring.py:202` and the stub-driven `test_vehicle_endpoint.py:64`, and names three files that have no `syncSource` reader. As written, the T2 full suite goes red.
2. **[Medium] T2 has an unmapped deletion:** `test_reads_no_wake.py::test_ble_actual_current_change_is_timed` (reads `lastCurrentChangeTime`).
3. **[Medium] T3 tri-state changes asserted values** (`is_awake` False → None) in `provider_outcomes_cloud:206–208`, `token_slots:173` and `token_classification:127`. They must be mapped INTENTIONALLY CHANGED, and Review Focus 3 must stop calling the first "unchanged".
4. **[Low] T1 Step 2:** `test_limit_wiring.py:99`'s expected `chargeLimits` gains `"44": 75`, so "every assertion stays" is false.
5. **[Medium] T3 re-list in `test_limit_wiring.py:115`:** "a fresh `api_with_registry()`" loses the master's `heldLimits`. `new_api(master=m)` reuses `m.vehicleRegistry` through `forMaster`, so nothing re-lists and `(2,1)` fails. Swap in a fresh `m.vehicleRegistry` before `new_api(master=m)`.
6. **[Low] Fold 1 is exact except at an edge.** At the 120 s cache boundary, or on a telemetry flip between the two `is_awake` calls, BASE does a free GET and may skip `vehicle_data`; the fold pays $0.002. Reword "provably identical", or accept it explicitly.
7. **[Low] Rejoin removal and the Forget race.** `canForgetVehicle` → `forget` is not atomic (`HTTPControl.py:117–119`). A listing that lands in between loses its attachment until restart; today it self-healed. Accept and document it, or re-check `attachmentNames()` at forget.
8. **[Low] T3 Step 1 `test_a_listed_car_is_never_forgotten_or_expired`:** `expire` skips user-asserted cars anyway (`VehicleRegistry.py:151`). Pin `keepsAlive` with a listed car that is **not** user-asserted.
9. **[Low] T1 `waiting()` with a truthy non-dict `chargeLimits`** stays True forever: free list GETs every 5 min for good. Require `isinstance(dict)` in `waiting()`.
10. **[Low] T1 `_migrate` final pass:** two IDs → one VIN whose loaded entry is malformed now keeps the second ID's normal limit, not the first's. Drop `vin not in written` from the skip at `final`, or document it.
11. **[Low] T1 delta is optimistic.** Expect −40..−55, not −65. The projected total is ≈27,040–27,070.
12. **[Low] T3 `checkReady`/`provesOnline` merge** changes the 14 test calls of `get_car_api(..., checkReady=False)`: they no longer set `lastAPIAccessTime`. No assertion depends on it; list it in the report.
13. **[Low] Mock masters** (`test_vehicle_endpoint`, `test_charging_points`, `test_gen2_idle_minimum`) return a `Mock` TeslaAPI. After T3, `located()` returns a truthy `Mock` from `Mock.locate(v)` in place of the stub's None, so tests can pass for the wrong reason. Set `carapi.locate.return_value = None`, or use a real `TeslaAPI`.
14. **[Low] `git mv` of `test_carapivehicle_registry.py`** breaks 8 importers; list them in T3.
15. **[Low] `vehicleIsDefinitelyHome`** must check that `attachment("TeslaAPI")` is not None after `registry.get(vin)` (unlisted cars live in the registry too). The plan's snippet does this only for `vehicleScheduledChargingPending`.
16. **[Info] Per-car iteration** is now in sorted-VIN order, not list order; counts and values are unchanged.
17. **[Info] T2 flex test:** `scheduledAmpsMax` must be > 0, or `TWCMaster.py:682` divides by zero.
18. **[Info] Path:** `Gen3TWC` is `lib/TWCManager/EVSEInstance/Gen3TWC.py:281`. The unlisted comment `TeslaAPI.py:172` must change in T3 (its grep forces it).
19. **[Info] `"id:"` safety verified from git:** only `deploy/phase3-live` (= db47522) carries the writer, and it also carries the cleaner. Still, run the box `jq` check **before** T1, not in T4.
20. **[Info] `CHANGELOG.md:23`** says the older `chargeLimits` is "kept but ignored, with a warning". At BASE it is deleted silently (`test_both_keys_present_the_store_wins`). Fix it in the T4 sweep (not lib).

## Extra savings (behaviour-neutral)

`TWCSlave._anonCars` −3; `VehicleEndpoints.allEVSEs` −3; `HeldLimits._snapshot` inline −3; `vehicleIsDefinitelyHome` `say()` −3; optional HA list → `attached("HomeAssistant")` −2..−4. Total ≈ −12..−16, which brings the realistic end to about 27,025–27,055.
