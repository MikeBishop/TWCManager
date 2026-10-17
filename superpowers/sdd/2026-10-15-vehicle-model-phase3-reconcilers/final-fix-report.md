# Final-review fix report: vehicle-model Phase 3

Branch `vehicle-model/phase3` in `scratchpad/wt-vm3`. BASE is fc6eba7 and HEAD is db47522. Nothing was pushed.

## Commits

| Commit | Item | Lib lines after |
|---|---|---|
| 3400e04 | I1: hold the TWC at the target until the car's mode-2 rate lands | 27,388 (+16) |
| a9b0803 | I2 item 3: drop the EVSEInstance start/stop | 27,340 (−48) |
| 508d22c | I2 items 4 and 7: dead and test-only helpers | 27,285 (−55) |
| d002eb8 | I2 item 5: `isAnonKey` / `canonicalKey` | 27,273 (−12) |
| 6cdd5e4 | I2 item 8, plus two home-location helpers | 27,252 (−21) |
| cdb5b1e | M1: write the expiry before the zero | 27,254 (+2) |
| 66f0704 | M8: log the HA host and exception types | 27,264 (+10) |
| 3d36dc6 | M13 and M6: comments | 27,267 (+3) |
| db47522 | M8: the last HA traceback; I1: a test for the floor clamp | 27,270 (+3) |

**Lib** (`find lib -name '*.py' | xargs cat | wc -l`):
- 27,372 at BASE, 27,270 at HEAD: **−102 net**.
- The parts: I1 +16, I2 **−136**, Minors +18.

**Suite:** `tests --ignore=tests/API --ignore=tests/integration` gives **1764 passed, 1 xfailed**. BASE was 1764 passed, 1 xfailed.
- +2 I1 tests (the parity probe and the floor clamp).
- −4 deleted plumbing tests.
- +2 Minor tests (M1, M8).

`black --check lib` passes.

## I1: mode-2 overshoot

### Fix

The hold lives in the heartbeat's car-carries branch (`TWCSlave.send_master_heartbeat`). That branch runs for chargeRateControl 2, and for mode 3 when the target is below 6 A. The TWC offers `wiringMaxAmps` only when `_carRateConfirmed()` is true: every car carrying the rate believes the desired amps. That means `satisfied(AMPS, desired, known(v, AMPS))`, where `known` is either our delivered write or a newer reading.

Until then the TWC offers `int(target)`. A newer reading that disagrees with the target puts the TWC back on the target.

`ChargingPoint.setTargetPower` now hands the TWC `max(floor, target)` instead of `maxPower`, so the heartbeat has a target to hold:
- In mode 2 this is the target, never below the floor. A 5 A target is not zeroed by the heartbeat's below-minimum branch.
- In mode 3 below the floor this is still the floor. That is unchanged: the floor is already the least the TWC can offer.

### Why the check is in the heartbeat, not only in ChargingPoint

The heartbeat's mode-2 branch overwrote any target with `wiringMaxAmps`. So `_evseTargetAmps == 10` alone, the review's proposed assertion, would not have changed what the TWC is offered.

With the check in the heartbeat, one rule covers three paths:
- the distributor's points;
- the heartbeat-only path (VIN-less, or pure Gen2 without VehicleEndpoints);
- mode 3's below-6 A branch.

### Wiring rule check

- Configured limits are already the 80% derating. A one-cycle excursion is fine.
- The TWC offers the target on the first heartbeat after the target is set, because the desire is unconfirmed at that point. It offers the maximum only after confirmation.
- `set_last_amps_offered` still caps every offer by `wiringMaxAmpsAllTWCs` and `wiringMaxAmps`.
- The idle minimum is untouched. The below-minimum branch, where a Gen2 offer of 0 means the hardware minimum, is before the changed branch.

### What is not affected

- **Mode 1** goes through the TWC-control `else` branch, which is unchanged.
- **Mode 3 at or above the floor** takes ChargingPoint's first branch and the heartbeat's `else`, both unchanged.
- **Gen3** has no `pointOwnsAmps`, so ChargingPoint gives the whole target to the unit, unchanged. `test_gen3_shared_headroom_meets_the_budget` and the Gen3 point tests pass.
- **Paid calls:** the fix adds none. The paid bound is unchanged: `amps sent [10, 10]`.

### Behaviour changes to note

These are visible, but correct under the wiring rule. CHANGELOG and docs/Settings.md were updated.

- A mode-2 car that no provider can set amps for (Owner-only, or ble_only without a key) now has the TWC hold it to its share. In effect this is mode 1 on the wire. At BASE it drew up to the TWC maximum.
- Each time the mode-2 rate changes, the TWC drops to the new target until the car confirms it, then returns to its maximum. Main kept a constant maximum offer in mode 2. Main's mode 3 already raised the offer like this, but watch for the 2017 "raise drops the car to 6 A" firmware behaviour on a live mode-2 install.

### Test that is red at BASE

`tests/unit/test_command_path_parity.py::test_mode_2_twc_holds_the_target_until_the_car_rate_lands`:
- **Probe:** Fleet-only, mode 2, target 10 A. Fleet answers 500, 500, then 200. The heartbeat runs every 10 s for 1 h, and each offer is recorded. The test asserts `amps == [10, 10]` and `max(offers[1:]) <= 10`.
- **Confirmed case:** Fleet answers 200. The test asserts `amps == [10]` and that the final offer is `wiringMaxAmps`, so the existing behaviour resumes.

Run against fc6eba7 (a scratch worktree with this test file copied in):

```
E   assert ([10, 10] == [10, 10]
E     Use -v to get more diff and 32 <= 10)
E    +  where 32 = max([32, 32, 32, 32, 32, 32, ...])
FAILED tests/unit/test_command_path_parity.py::test_mode_2_twc_holds_the_target_until_the_car_rate_lands
```

Other I1 test changes:
- `test_amps_reconciler.py::test_mode_2_twc_target_never_drops_below_the_floor` (new): a 5 A car rate leaves the TWC at 6 A. Reverting the clamp to `amps` fails it.
- `test_amps_reconciler.py::test_mode_2_car_carries_and_the_twc_offers_its_max` (INTENTIONALLY CHANGED): it now drives the heartbeat. The TWC offers 10 before delivery and `wiringMaxAmps` after. A newer disagreeing reading brings it back to 10.
- `test_twc_only_point_keeps_the_heartbeat_path_under_mode_2` (extended): the heartbeat-only rate is held, then released after a BLE DONE.
- Parity row 21 `test_mode_2_undeliverable_rate_pays_twice` (INTENTIONALLY CHANGED): it expects `_evseTargetAmps == 10`, not `maxOfferAmps`.
- `test_charging_points` row 4 (INTENTIONALLY CHANGED, renamed): `test_mode_2_named_twc_offers_its_max_and_the_car_carries_the_rate` is now `test_mode_2_named_twc_holds_the_target_and_the_car_carries_the_rate`. It expects the target, 20.

## I2: removed items and grep evidence

**Policy reach:** `Policy.policyValue` returns `getattr(module, pieces[2], value)` without calling it. A policy can therefore use a module's property or data attribute, but it can never call a method.

None of the removed names is a property or data attribute of an object in `master.modules`. The one exception is `lastVehicleStatusTime`, and it lived on `CarApiVehicle`, which is not a module.

Kept for policy reach (documented in PolicyCustomization.md and Vehicle_HomeAssistant.md):
- `TeslaAPI.numCarsAtHome` / `minBatteryLevelAtHome`
- `HomeAssistant.numCarsAtHome` / `minBatteryLevelAtHome`

**Grep scope:** every name below was checked with `git grep -nw` across lib (the theme templates live under `lib/TWCManager/Control/themes`), html, tests/integration, tests/API, docs and tests/unit.

| Removed | Where | Evidence after removal |
|---|---|---|
| `startCharging`/`stopCharging` on EVSEInstance (abstract), Gen2TWC (stubs), VehicleEndpoint, ChargingPoint, Gen3TWC | EVSEInstance/* | `git grep -nE "\.(startCharging\|stopCharging)\(\)"` returns 0. The remaining hits are Provider methods, reached by capability name, plus Capability constants. Gen3TWCProvider now calls `setUnitTarget` through one `_onUnit` helper, which also removes the triple unit-is-None guard. |
| `TWCMaster.getSetting` / `setSetting` | TWCMaster | 0 lib callers. `setSetting` matches only the HTTP route `/api/setSetting` (HTTPControl, docs, tests/API), which is a different thing. |
| `TWCMaster.time_now`, `TWCManager.time_now` | TWCMaster, TWCManager | 0 refs |
| `CarApiVehicle.lastVehicleStatusTime` | TeslaAPI | 0 refs |
| `TeslaAPI.getVehicleCount` / `getCarApiVehicles` | TeslaAPI | 0 refs in lib, html, templates, docs. Tests now use `carApiVehicles`. The registry-callers guard now greps for any non-`self.` `.carApiVehicles` or `getCarApiVehicles` in lib, and finds none. |
| `Provider.commandMethod` (identity function) | Provider, Run | 0 refs |
| `updateSettings` stubs returning True (TeslaAPI, HomeAssistant, Telemetry) | 3 modules | The master now calls `updateSettings` only where it is defined. The only definition left is TeslaBLE's real one. `git grep -nw updateSettings` across docs, html, contrib, etc, tests/integration and tests/API: 0 hits. |
| `VehicleRegistry._normalise`, `ChargingPoint._groupKey`, `WallConnectorVins._anonymous`, and the prefix tests in VehicleEndpoints, TWCSlave and TWCMaster | 6 files | Replaced by `isAnonKey` / `canonicalKey` in VehicleRegistry.py; 0 refs to the old names. |
| `HomeAssistant.is_location_within_radius` | HomeAssistant | Inlined into its one caller. The 3 remaining refs are TeslaAPI's own method, which is kept. |
| The three HA float-parse try/excepts | HaVehicle | Now one loop: same entities, same order, same fail-fast. |
| The `vehicleIsDefinitelyHome` log plumbing | TeslaAPI | The same three messages, now through one local helper. |

**Kept, with the reason:**
- `TWCMaster.checkModuleCapability`: `graphs.html.j2:10` calls it. The review listed it as dead; it is not.
- Item 6, the `chargeStopMode`/`chargeRateControl` accessors: it saves no lines. Each call site is one line either way, and the accessor pair adds about 6. The Mock-master tests would also need changes.
- Item 2, "is this car home": the remaining copies differ in behaviour. HA seeds home without TeslaAPI's GPS-age check and without the sunrise task; `broadcastVehicles.reached` treats an unseeded home as home; Gen3 and VehicleEndpoints read `atHome`, not `locate()`. None of these can be merged without a behaviour change, so they are left to Phase 5.
- Item 1, HeldLimits: deferred by your ruling, including the `"id:"` keys.
- Item 7, `READ_MAX_AGE`: Reconcile would have to import TeslaAPI to share it, which is the wrong layering. It goes with Phase 3.5.

**Deleted tests:** all four are PLUMBING-ONLY. Each tested only the removed wrapper.

| Deleted test | Mapping |
|---|---|
| `test_twcmaster.py::TestTWCMaster::test_get_setting` | PLUMBING-ONLY (`settings.get`) |
| `test_twcmaster.py::test_get_setting_default` | PLUMBING-ONLY |
| `test_twcmaster.py::test_set_setting` | PLUMBING-ONLY |
| `test_settings_lock.py::test_set_setting_takes_the_lock_and_get_does_not` | PLUMBING-ONLY. Writers taking the lock stays pinned by `test_off_thread_master_writers_take_the_lock`. |

**Rewritten tests:** `test_settings_lock_is_reentrant` now uses the dict, and the registry-callers guard was updated as described above.

## Minors

| # | Status | Notes |
|---|---|---|
| M1 | Fixed (cdb5b1e) | Expiry written before the zero. A new test pins the write order. |
| M2 | Skipped | Stops are deliberately exempt from the stale-desire check: the drain path, audit row 56. Dropping a cleared stop safely needs a cleared-at stamp (new state) and a ruling on drain. The exposure is a narrow race costing at most $0.001 or 60 s of mode-2 silence. |
| M3 | Skipped | No vehicle path raises a BaseException today. The fix adds a new NOT_SENT detail and changes the worker lifecycle, which is not cheap. |
| M4 | Skipped | Needs the arrival routed through the policy thread or a new lock. Any harm is corrected at the next policy pass. |
| M5 | Skipped | A final `pass_()` would still honour MIN_SEND_GAP/RETRY, so it would not queue the held stop. Bypassing the holds at SIGTERM is a design call. |
| M6 | Documented (3d36dc6) | Comment in `plan()`: a racing `newDesire()` can only lose a retry, never add a paid send. |
| M7 | Skipped | The raw `-debug` output at DEBUG is an earlier deliberate ruling (TeslaBLE comment: "The -debug output carries session detail: DEBUG only"), kept for BLE diagnosis, and it carries no key material today. Removing it is a diagnosability trade for you to decide. |
| M8 | Fixed (66f0704, db47522) | All eight HA sites the review listed (BASE lines 229, 239, 257, 264, 335, 339, 511, 514) now log the hostname or the exception type. Line 264 was a `logger.exception`, whose traceback ends in `str(e)`; it now logs the type only. The six TeslaBLE catch-alls near key handling log the type only. The new test covers init, connection error, discovery failure and state read. It fails before the fix: the URL's password appeared in the log, and the discovery leg fails with `logger.exception`. |
| M9 | Skipped | Pre-existing catch-alls (`TWCManager.py`, `Policy.py`). Nothing token-bearing reaches them today, and they are out of this branch's scope. |
| M10 | Skipped | The review marks it as optional, after the live check. It is main parity. |
| M11 | Skipped | Watch item only. Look for `adopted` lines around 00:00 on the live box. |
| M12 | Skipped | By design (Q3). The review says no fix is needed. |
| M13 | Fixed (3d36dc6) | The comment now says PAID_AFTER and RETRY are two knobs that share values today. |

## Concerns

- **I1 changes mode-2 behaviour on the wire.** The TWC follows each new target until the car confirms it, then returns to its maximum. This is untested on hardware with mode 2. A mode-2 car that cannot be commanded is now held by the TWC.
- **Policy reach:** removing `getSetting`, `setSetting` and `time_now` departs from the literal rule. `modules.master.X` reaches them, but only as uncalled bound methods, because Policy never calls what it gets. So no policy can use them.
- **I2 total:** −136 lines against the ~−140 target. The net branch delta after I1 and the Minors is −102, so lib is still 520 lines over 26,750. The rest is HeldLimits (deferred) and structural (Phase 3.5).
