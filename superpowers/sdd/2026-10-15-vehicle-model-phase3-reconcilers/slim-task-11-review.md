# Slim Task 11 review (bba7c4f..2ecf54f)

Reviewer: read-only, code at `scratchpad/wt-vm3` @ 2ecf54f. Line numbers are at 2ecf54f (paths relative to `lib/TWCManager/` unless they start with `tests/`).

## Verdicts

- **(A) Spec compliance: PASS.** Every deletion in the brief happened, with no remaining references in `lib/` or `html/`. I grepped `applyChargeLimit`, `apply_charge_limit`, `lastLimitAttemptTime`, `NormalChargeLimit`, `_heldLimitKey`, `_adoptListedHeldLimits`, `adoptLegacyId`, `LEGACY_PREFIX`, `storeKey`, `lastChargeLimitApplied`, `stopTryingToApplyLimit`, `_stopTryingToApplyLimit`, `_lastAppliedChargeLimit`, `_applyChargeLimitKwargs` and `carApiLastChargeLimitApplyTime`. The only `set_charge_limit` and `charging-set-limit` senders left are the providers that the reconciler drives. The Interfaces are present: `Targets.py` with its five functions, `desired`, `registry.removed`, `reconciler`, `policyLimit`/`setPolicyLimit`, `reconciler.start()`, the shutdown order and `shutdownTimeouts`. Every required test exists. Two deviations are accepted or explained:
  - I9 is stricter than the ruling (accepted).
  - `checkCharge` is queued at startup and on arrival, because the brief's premise that `checkCharge` is periodic is false. See I2.
- **(B) Quality and cost safety: NOT YET.** 1 Critical, 2 Important, 5 Minor.

Suite: `tests --ignore=tests/API --ignore=tests/integration` gives **1661 passed, 1 xfailed**, which matches the report. Targeted files: 187 passed. I confirmed C1 and I1 with a throwaway probe (two tests, both passed against the buggy behaviour, then removed; the tree is clean).

The lib delta is honest. `git diff --numstat bba7c4f -- lib` gives +331/−771, net −440. Most of `TeslaAPI.py`'s +70 is the existing list GET moved into `_vehicleList`. `Targets.py` (86 lines) duplicates nothing that still exists: `_present` has no other copy in the tree. `TeslaBLE._allVehicleTargets` is a different thing (the BLE key store) and goes in 12b per pre-flight I1. `targetsFor` has no lib caller until 12a, which the Interface requires.

Cost: no new paid call. The startup `checkCharge` adds one free `GET /vehicles`. Newly listed cars start with `atHome=False`, so no `vehicle_data` is read. While IDs wait, the extra list fetch is free. Arrival cost is at or below BASE, because BASE also ran `updateChargeAtHome` at the end of `applyChargeLimit(checkArrival=True)`. Restores never wake (Reconciler.py:151).

Locks: `resolveLegacyIds` takes only `settingsLock`, and only for dict work. It logs and saves after releasing it. It is reached under `vehicleListLock`, which is the allowed `vehicleListLock -> settingsLock` order. The c6 `heldLimits.remove` is called under no reconciler lock. One I/O concern is M1.

Logging: no token reaches a log line. `_vehicleList` logs the URL (no token), `str(req)` and the response body (VINs, no token). The drop warning names only the ID and the limit.

## Critical

**C1: The departure restore never fires for a car with a TeslaAPI attachment, because `atHome` becomes True at plug-in and nothing clears it.**
- Evidence:
  - `Targets._present` (Reconcile/Targets.py:22-26) checks `twcVin`, and then, for any car with a TeslaAPI attachment, returns `bool(api.atHome)`.
  - `atHome` is set True on every TWC VIN report: `vehicleIsDefinitelyHome` (TeslaAPI.py:2283), queued from TWCMaster.py:1559. Apart from the class default, only `update_location` and `update_vehicle_data` (TeslaAPI.py:2679, :2737) ever set it False.
  - After this task, nothing calls those on departure. `checkDeparture` now runs only `onDeparture(master)` (TWCManager.py:336-337). BASE's `applyChargeLimit(checkDeparture=True)` read the location there.
  - So after an unplug (`twcVin` cleared), the car still counts as present. `onDeparture` (Targets.py:82-86) skips it, and the held limit is never restored. The car leaves at our limit (for example 50%) instead of the user's normal one. This covers every Owner, Fleet and BLE+Fleet car.
  - The same stale presence keeps the car in `presentVehicles`. A policy transition while the car is away then sets a desire, and the reconciler reads ($0.002) and sends ($0.001) a new limit to a car on the road, for example one at a Supercharger. BASE checked `atHome` after a fresh read and restored instead.
  - Probe: car attached with `atHome=True`, `twcVin` observed then cleared, `heldLimits.set(VIN, 90, 50)`. After `onDeparture(m)`, `desired.get(VIN, CHARGE_LIMIT)` is None.
- Why the brief's interim doesn't cover it: the brief accepts that `atHome` is refreshed only by existing reads, but the departure path had one of those reads (BASE TeslaAPI.py ~1216) and this task deleted it.
- Fix (pick one):
  - (a) **Free.** In `_present`, a car whose latest `twcVin` observation is None (unplugged) counts as absent unless a location reading is newer than that observation (`vehicle.latest("lat").at > vehicle.latest("twcVin").at`). A car parked unplugged at home is then restored. That is harmless: the next plug-in re-applies the policy, and it costs at most one $0.001 send with no wake.
  - (b) **BASE parity.** In `checkDeparture`, before `onDeparture`, call `api.update_location(0)` for each `heldLimits.holding()` VIN that has a TeslaAPI attachment and no `twcVin`. That is a paid `vehicle_data` ($0.002) that never wakes, at most 3 per departure (5, 20 and 45 min), and only for cars we hold a limit on. It matches BASE.
  - Add a test: a car with `atHome=True`, `twcVin` cleared and a held limit gets one restore desire from `onDeparture`. A policy transition does not target it.

## Important

**I1: A record the reconciler makes while an ID waits silently beats the legacy entry, so the user's normal limit is lost.**
- Evidence:
  - `resolveLegacyIds` keeps any VIN already in the store (Reconcile/HeldLimits.py:199, `elif vin not in store`) and logs nothing for the discarded legacy entry.
  - That is right for entries that were in the store at `load()` (M9 dev builds). It is wrong for an entry the reconciler created after `load()`. Here is how that happens. The car's legacy entry waits under its numeric ID, for example `(outside 90, held 50)`, and the car is still at our old 50. The policy sets a different target, say 60. `beforeWrite` sees `held=None`, takes the current 50 as normal and saves `HeldLimit(50, 60)` under the VIN. Then the list resolves, the VIN is in the store, and the user's 90 is dropped with no warning.
  - Probe: `load()` with `{"chargeLimits": {"11": [90, 50]}}`, then `set(VIN, 50, 60)`, then `resolveLegacyIds({"11": VIN})`. `get(VIN)` is `HeldLimit(50, 60)`.
- Windows:
  - (1) The time between the first list's `addVehicle` (Fleet and Owner become ready) and the second slot's GET, up to 30 s. During it, a twcVin-present car can be planned.
  - (2) Much longer, the deferral the implementer added when the second list fails (TeslaAPI.py:420-424). The next try then comes only at the next arrival (see I2), and Owner+Fleet installs are a normal setup.
  - (3) A car served by BLE or HA (ready without the list) is planned before the startup `checkCharge` runs.
- Fix: in `load()`, record the store's VINs (`self._loadedVins`). In `resolveLegacyIds`, the store wins only for those. For a VIN added after load, merge `HeldLimit(legacy.outside, store.held)`, keeping our current hold and the user's normal. Log one line whenever a matched legacy entry is discarded. Add a test that is the probe above, expecting `HeldLimit(90, 60)`.

**I2: The vehicle list has no retry after a failed startup load (pre-flight C1 is only half closed).**
- Evidence:
  - `checkCharge` is queued only at startup (TWCManager.py:844), by `checkArrival` (:329-333) and by `TeslaAPI.minBatteryLevelAtHome` (TeslaAPI.py:2334-2336). The last runs only when `limitOverride` or a policy condition reads it, so on a default install `checkCharge` is not periodic.
  - When the startup GET fails, the list next loads only at an arrival or from a legacy `car_api_charge`. Network down at boot after a power cut is common: the Pi often comes up before the router.
  - In this task the legacy charge command still loads the list, so stops and starts still work. But the reconciler's Fleet limit is unavailable until then: `FleetAPIProvider.ready` is False, so `presentVehicles` drops the car and no limit desire exists.
  - Waiting legacy IDs, including I1's deferral, also resolve only at that next trigger.
  - After 12a deletes `car_api_charge`, a Fleet-only install can never deliver a stop until the next plug-in.
- Fix (now, about 4 lines): queue `checkCharge` from an existing periodic path while `TeslaAPI.getVehicleCount() < 1` or `heldLimits.waiting()`, rate-limited by the existing `lastChargeCheck`/`chargeUpdateInterval`, or a shorter list-only interval. An example of such a path is the policy loop or the main loop's existing minute ticks. Both calls are free. Add a test: a failed startup list is retried with no plug-in, GETs only.
- 12a must not land without this.

## Minor

**M1: The second list GET now runs under `vehicleListLock`** (TeslaAPI.py:408 inside the `with` at :387). That raises the worst-case hold from 30 s to 60 s for Telemetry name lookups and `car_api_available`. The first GET was already under it, which is pre-existing. Fix: return `listed` out of the `with` block and call `resolveHeldLimits(slot, listed)` after releasing it. `resolveLegacyIds` already serializes itself under `settingsLock`.

**M2: Limit before start does not hold in the interim, by design (pre-flight M10).** The legacy Fleet, BLE and HA starts (`car_api_charge`, still on the legacy queue) no longer send the limit first. The reconciler's limit desire runs on its own queue, and its start gate (Task 9 ruling, `LIMIT_THEN_START_GAP`) only covers starts the reconciler submits, which begins in 12a.
- Result: for a few seconds a car may start toward its own limit before ours lands.
- There is no double send, because no legacy path sends a limit any more.
- Record it as an interim that 12a closes, and check in the 12a review that the start gate applies to every start.

**M3: Stale references.** `tests/unit/test_teslaapi_charge_vin.py:29` mocks `a.applyChargeLimit`, which is dead. `docs/modules/Vehicle_HomeAssistant.md:114` still names `applyChargeLimit`. Delete the mock and reword the doc.

**M4: The token-leak assertion only sees WARNING.** In `tests/unit/test_limit_wiring.py:103,111`, `caplog.at_level(logging.WARNING)` means the INFO6, INFO8 and DEBUG lines in `_vehicleList` and `slotRequestFailed` are never checked. Code inspection finds no token, but the test should capture at `logging.DEBUG` (level 1) so it pins that.

**M5: A legacy entry dropped because its VIN already has a store entry goes unlogged** (HeldLimits.py:199). This is separate from I1's merge. Log at INFO the ID, the VIN and the discarded outside limit, so a user can restore it as the unmatched warning allows.

## Hunt checklist

- **Pre-flight C1.** The list loads at startup, on arrival, and from the legacy charge command. It does not retry after a failure (I2). A Fleet- or Owner-only car is present for the policy limit when it is on a VIN-reporting point (`twcVin`). In that case `vehicleIsDefinitelyHome` also sets `atHome`, so the limit is applied. A car on a TWC that reports no VIN becomes present only after some read sets `atHome`. The interim the brief accepts is harmless there. The real gap is the other direction: absence (C1).
- **Data loss.** A restart before resolution loses nothing: `chargeLimits` and the `id:*` keys stay on disk until a save after resolution, and the test is `test_an_unresolved_id_survives_a_restart`. A failed list fetch drops nothing (`all(isinstance(cars, list))`). An empty union drops nothing. The one loss path is I1.
- **Interleaving.** No path double-sends. Limit-before-start is lost until 12a (M2).
- **Locks.** The order holds. One lock hold got longer (M1).
- **Logging.** No token appears anywhere.
- **Size.** The −440 is honest. `Targets.py` duplicates nothing.
