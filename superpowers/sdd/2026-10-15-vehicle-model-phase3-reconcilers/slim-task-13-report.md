# Slim Task 13 report: final cleanup, docs, line check

**Status: DONE_WITH_CONCERNS.** All work is committed on `vehicle-model/phase3` in wt-vm3, starting from BASE 6c75533. Nothing is pushed.

## Commits

| Commit | What | lib Δ |
|---|---|---|
| 0364f3a | Delete helpers that were already dead on main | −165 |
| 4becbcf | Drop the unread read capabilities, TelemetryProvider, `passive`, `sharedControl`, `vehicleAttachment` and `commandPolicyOverridden` | −105 |
| b58b325 | Drop the unread reconciler and provider summaries | −76 |
| eec1b05 | Remove the orphans; `LANE_DETAILS` → `QUEUE_DETAILS`; fix the malformed held-limit merge; add the grep test | −58 |
| 654ce07 | `TeslaAPI._request` takes one `tries` budget in place of `resend`/`retried` (carried 1) | +2 |
| b5ced07 | Storm Watch: 10 s timeout, exception type only in logs (carried 2) | −1 |
| 8c97c09 | Pin the age guard's `<=` boundary (carried 3) | +2 |
| 77b4d2d | Docs (presence, no home set) and changelog (carried 4, 5) | 0 |
| b4f3b39 | Changelog trimmed to changes against the last release; setting home by hand; Vehicle_HomeAssistant.md's field list | 0 |

**Tests:** 1729 passed, 1 xfailed. The suite is `tests --ignore=tests/API --ignore=tests/integration`; BASE gave 1727 passed and 1 xfailed. The change is −5 deleted tests and +7 new ones (counting parametrized cases).

**lib:** 27,732 → 27,331, a Δ of −401. The expected Δ was ≈ −400.

## Item check at BASE (`git grep`)

**Already gone at BASE (skipped):**
- `TeslaAPI.car_api_available`, `findReason`, `refuseCommandIfReadOnly`, `updateLastStartOrStopChargeTime` and `carApiLastStartOrStopChargeTime` (in both modules and in WebIPCControl);
- `HomeAssistant._is_vehicle_connected` and `_call_service`;
- `VehicleReconciler.summary` and `VehicleCommandQueue.summary`;
- every name in the brief's first three grep groups (`VehiclePriority` and the others).

**Still live at BASE, so kept (the audit's static scan missed these):**
- **`HeldLimits.holding`:** Task 12c's `Targets._restoreDeparted` calls it.
- **`ChargingPoint.vehicleEndpoints`:** `ChargingPoint.setTargetPower` uses it (ChargingPoint.py:155).
- **`TeslaAPI.minBatteryLevelAtHome`:** `Policy.py:312` calls it.
- **`numCarsAtHome` and `minBatteryLevelAtHome` on both TeslaAPI and HomeAssistant:**
  - `Policy.py:417` resolves `modules.<Module>.<attr>` with `getattr`, so a user's policy reaches these.
  - Both are documented: PolicyCustomization.md:210-213 and Vehicle_HomeAssistant.md:94-95.
  - Deleting them would silently break user policies.
- **`HaVehicle.battery_level`, `lat`, `lon` and `at_home`:** the two properties above read them, and `Targets._present` and `broadcastVehicles` read `at_home`. Only HaVehicle's other cached fields went: `charge_limit`, `available_current`, `charging` and `last_state_update`.
- **`TeslaAPI.getCarApiVehicles` and `getVehicleCount`:** both are used. Only HomeAssistant's copies went.

**Deleted** (each existed at BASE):
- **Dead on main:**
  - APIValidator `validate_required_fields`, `validate_integer`, `validate_float`, `validate_string`, `validate_choice` and `is_safe_string`. `validate_float` was not in the brief, but the audit's "only `validate_json` is used" covers it.
  - `EVSEController.startAllCharging` and `stopAllCharging`.
  - TWCMaster `getSendServerTime`, `setSendServerTime`, `getMasterSign`, `setkWhDelivered` and `delete_background_task`.
- **Declarations:**
  - `READ_LIST`, `READ_ONLINE`, `READ_LOCATION`, `READ_PLUG`, `READ_VIN` and `READ_AMPS`, with their table entries. `READS` is now `{READ_CHARGE, READ_WALL_CONNECTOR_VINS}`, and Gen2's `READ_CAPABILITIES` ready branch went too.
  - `TelemetryProvider` and `TelmetryBase.providers()`.
  - `Declaration.passive`, with Order.py's skip of it.
  - `sharedControl` in Provider, Gen3TWCProvider and Gen3TWCs.
  - `Provider.vehicleAttachment` and HomeAssistantProvider's copy.
  - `Suppressions.commandPolicyOverridden`.
- **Summaries:** `Provider.summary`, `_attemptSummary`, `AttemptRecord.summary`, `FreeChannel.summary`, `_desiredSummary` and `DesiredStore.summary`. `Cost.price` stays as a field.
- **Orphans:**
  - `VehicleRegistry.pointFor`;
  - `fresherThanWrite` in both Vehicle and FieldStore (`trusted()` keeps `_fresher`);
  - `CarApiVehicle.syncTimestamp`;
  - `TeslaAPI.energySites`;
  - the `Gen3TWCs.unitTargets` property and `headroom()` (the solver and `_unitTargets` stay);
  - HomeAssistant `getCarApiVehicles` and `getVehicleCount`;
  - HaVehicle's unread fields;
  - unused `logging` and `time` imports in HomeAssistant.py.
- **Renames and rewording:**
  - `LANE_DETAILS` → `QUEUE_DETAILS`.
  - The last "lane" comments are reworded (Outcome.py, TeslaAPIProviders.py).
  - Provider.py's comments no longer mention the façade.
- **Parked nits folded in:**
  - **HeldLimits `resolveLegacyIds`:** a malformed VIN entry used to be logged as "kept" while the legacy limit was lost. It now counts as absent, and the legacy limit replaces it. Test: `test_resolving_replaces_a_malformed_vin_entry`, which fails on BASE.
  - **`WallConnectorVins.py` DEBUG traceback:** already frames-only at BASE (no message text), so nothing to do.

## Carried items

1. **`tries`** (654ce07):
   - `_request(..., tries=3)` counts the requests and token refreshes a call may make, one each, and refreshes at most once:
     - 3 (the default for commands, wakes and energy) refreshes an expired token and resends;
     - 2 (the vehicle list) refreshes but does not resend;
     - 1 never refreshes, so a 401 retires the slot.
   - The read loop passes `3 - sent + (not refreshed)`. This maps exactly onto the old `resend=sent<2, retried=refreshed`.
   - `_classify`'s `retried` became `refresh`.
   - New parametrized test `test_a_read_refreshes_at_most_once_across_its_tries` pins the two cross-try cases that only `retried` carried: (401, busy, 401) retires the slot; (busy, busy, 401) refreshes and keeps the slot. Both cases send 3 GETs with 1 refresh, and the test was written and passing before the refactor.
   - Mutation check: replacing the one-refresh cap with a plain decrement, ignoring `refreshed`, or giving the list `tries=1` each fails a test.
   - All existing tests pass unchanged.
2. **Storm Watch** (b5ced07):
   - Both `httpSession.get` calls get `timeout=10`.
   - All three warnings log `type(e).__name__` only.
   - It is not routed through `_request`. That helper's energy classifier would latch Wall Connector VIN reads on a Powerwall 403 (`_refuseWallConnectors`). It would also add 401 refresh/clear behaviour that Storm Watch never had, and `test_storm_watch_403_does_not_pause_slot` pins the current 403 handling.
   - Test `test_storm_watch_times_out_and_logs_no_exception_text` fails on BASE twice over: first on the timeout, then, with only the timeout added, on token text in the log.
3. **Age guard** (8c97c09):
   - Targets.py has a comment saying the `<=` is intentional: a retained MQTT position redelivered after our write carries the write's stamp.
   - `test_an_away_fix_stamped_at_our_write_instant_is_no_departure` pins both sides: equal stamps restore nothing; a fix 1 ms later restores. It fails with `<`.
4. **No-home-set docs:** a new "A car counts as at home when" block in PolicyCustomization.md's Charge Limits section, where the GPS-based limits are described. It covers:
   - the presence order;
   - re-checking on every pass, so a restart finds the car again;
   - departure and the age guard;
   - what happens with no home location: presence relies on the TWC's VIN, a held limit or the last plug edge, HA, or a BLE key, until a Tesla API read (billed `vehicle_data` on Fleet) or Home Assistant sets home.
5. **Changelog** (Architecture and Bugfixes), listing only changes against the last release (1.3.x), not churn inside unreleased v1.4.0 work:
   - the reconciler, including PAID_AFTER 300/60 s, the paid-send cap (once, one retry, re-arm on a newer reading, ≤4 in all) and limit before start;
   - the TeslaBLE retry/breaker removal, with the brief's exact sentence;
   - unmatched numeric-ID held limits are dropped (user decision);
   - presence: re-checked every policy pass from the latest free position, departure by position, and the write-stamp guard;
   - BLE failure no longer falls to paid at once, and HA is used only after Fleet is unavailable or refused;
   - 10 s reads, at most 3 vehicle_data GETs, a refreshed token refused again is removed, and a 412 on a command stops commands only;
   - the Storm Watch fixes.

   **Left out on purpose:**
   - the provider capability names, which never shipped;
   - Gen3 per-unit targets (Gen3 itself is new in 1.4.0);
   - the mode-2 cloud-start suppression and the Gen2 anonymous session, which are parity with main.

   **Doc changes outside the changelog:**
   - Settings.md: the providerSuppressions paragraph lists only `readCharge` and `wallConnectorVins` and says the removed names are ignored.
   - PolicyCustomization.md: the no-home-set paragraph also says how to set home by hand (web-interface learn, or `homeLat`/`homeLon` through setSetting).
   - Vehicle_HomeAssistant.md: the list of fields the module keeps is corrected; it was stale at BASE.

## Grep test

`tests/unit/test_no_legacy_command_paths.py` contains:
- **`test_legacy_paths_and_dead_code_are_gone`:** the brief's four groups verbatim. The `def summary` group excludes `Registry/Vehicle.py` and `Registry/VehicleRegistry.py` (pre-flight I10).
- **`test_unread_declarations_and_orphans_are_gone`:** this task's deletions:
  - the six `READ_*`, `TelemetryProvider`, `sharedControl`, `passive=`, `vehicleAttachment` and `commandPolicyOverridden`;
  - the dead-on-main defs;
  - the orphan defs, `LANE_DETAILS` and `\blane\b`.

Both fail at BASE and pass at HEAD.

## Deleted-test mapping

| Deleted test | Now pinned by / status |
|---|---|
| `test_twcmaster.py::TestTWCMasterSlaveManagement::test_get_master_sign` | PLUMBING-ONLY: `getMasterSign` had no caller on main or here. `masterSign` itself is still used by the protocol code. |
| `test_provider_registration.py::test_telemetry_provider_is_passive_free_and_ready_while_live` | PLUMBING-ONLY: TelemetryProvider declared only passive reads, so it never entered a walk, and its `ready()` had no caller (audit §5). Feed liveness is pinned by `test_telemetry_registry.py::test_connection_state_is_the_feed_liveness`, `test_subclass_connects_set_liveness_and_teslamate_healthy_gates_it` and `test_own_write_then_silent_healthy_feed_is_trusted_after_feed_lag` (review M3). |
| `test_provider_registration.py::test_passive_providers_never_enter_the_walk` | PLUMBING-ONLY: no passive declaration remains, and `Declaration.passive` is deleted. A provider without the capability is still skipped, as `test_provider_tables.py::test_order_ready_and_available_match_the_rule_the_tables_replace` and `test_expected_order_on_a_full_install` pin. |
| `test_provider_capabilities.py::test_summary_lists_each_capability` | INTENTIONALLY CHANGED: user decision 7 on the dedup audit ("delete unread summaries now"; progress.md, "User decisions on dedup audit"). Phase 6 re-adds what the tab needs. `Cost.price` is still pinned by `test_vocabulary_and_prices`. |
| `test_carapivehicle_registry.py::test_sync_timestamp_is_the_state_observation_time` | PLUMBING-ONLY: `syncTimestamp` was an orphan (audit §5). `syncSource` stays pinned by `test_sync_getters_have_legacy_defaults_before_any_state` and the telemetry state tests (`test_carapivehicle_registry.py:86-88`). |

**Renamed, with a clause trimmed (not deleted):**
- **`test_gen3twc_provider.py::test_capabilities_normal_tier_stop_and_declared_shared_control` → `test_capabilities_and_normal_tier_stop`:** the `sharedControl` and `passive` clauses went. The real shared-bus behaviour is pinned by `test_zero_target_beside_a_charging_sibling_declares_no_individual_stop` (NO_INDIVIDUAL_STOP) and the `test_charging_reconciler.py:132` shared-unit case.
- **`test_registry_read_cascade.py::test_provider_without_field_not_ready_or_not_reading_is_skipped` → `test_provider_without_field_or_not_ready_is_skipped`:** the passive-reader clause went (PLUMBING-ONLY, as above).

**Other trimmed clauses:**
- **`fresherThanWrite`:**
  - In `test_registry_fields.py::test_own_write_stamp_and_freshness`, each `fresherThanWrite` assertion is rewritten on `trusted()`, which keeps the same strictly-newer rule, including the same-instant P1 case.
  - The Vehicle copy's clause in `test_registry_vehicle.py` went. The `trusted()` assertion beside it pins the behaviour.
- **Summaries in `test_outcome_desired.py`:** replaced by direct state assertions (`s.free(VIN) is f`, `s.record(VIN, AMPS).excluded`).
- **`p.summary(v)` in `test_provider_outcomes_local.py`:** dropped. The no-desired-state-created assertion stays.
- **Read declarations:** the READ_* clauses in `test_provider_tables`, `test_provider_capabilities`, `test_gen2twc_provider`, `test_wall_connector_vins`, `test_teslaapi_providers` and `test_teslable_provider` follow the declaration change.
- **Gen3 `headroom()`:** a local `headroom(ctl)` helper in `test_gen3twc_provider.py` computes the same value, so all six headroom assertions stay.
- **`pointFor`:** replaced by `value("twcVin")`.
- **`energySites`:** replaced by `_fetchEnergySites(...) is None`.
- **`test_registry_callers.py`:** now expects only TeslaAPI.py to define `getCarApiVehicles`.

## Line check

```
git ls-files lib | grep '\.py$' | xargs cat | wc -l   → 27331   (target ≤ 26,750: over by 581)
git diff --shortstat origin/main -- lib  → 59 files changed, 8434 insertions(+), 4207 deletions(-)
git diff --shortstat 6a6c14e -- lib      → 47 files changed, 3838 insertions(+), 3999 deletions(-)
git diff --shortstat 39d7cfb -- lib      → 47 files changed, 2746 insertions(+), 5231 deletions(-)
awk removed ≥ added since 39d7cfb        → added 2746 removed 5231, exit 0 (PASS)
```

**Fixed points** (lib `.py` total, from `git ls-tree` at each commit):

| Commit | lib total |
|---|---|
| origin/main | 23,180 |
| 6a6c14e | 27,483 |
| 39d7cfb | 29,807 |
| d98d643 | 30,246 |

**Per-task, actual vs expected** (from the "lib" figures in progress.md, re-measured at each task's last commit):

| Task | Last commit | Expected Δ | Actual Δ | Total after |
|---|---|---|---|---|
| 10 | bba7c4f | ≈ −200 | −134 | 30,112 |
| 11 | d35a95c | ≈ −450 | −387 | 29,725 |
| 12a | 8b22849 | ≈ −850 | −833 | 28,892 |
| 12b | 464d83c | ≈ −800 | −731 | 28,161 |
| 13a | f0327e5 | ≈ −260 | −272 | 27,889 |
| 13b | fc7bd2f | ≈ −150 | −160 | 27,729 |
| 13c | bcb4042 | ≈ −120 | −57 | 27,672 |
| 12c (unplanned) | 6c75533 | 0 | +60 | 27,732 |
| 13 | 8c97c09 / 77b4d2d | ≈ −400 | −401 | 27,331 |
| **Tasks 10–13** | | **≈ −3,230** | **−2,915** | |

**Where the 581 over comes from:**
- The plan projected ≈ 27,016 after Task 13 and accepted ≈ 250 over 26,750 until the CarApiVehicle phase (≈ −300). This branch is 315 above that projection.
- The shortfalls against expectation are:
  - Task 10, +66 (Run.py kept, per I8);
  - Task 11, +63;
  - Task 12b, +69;
  - Task 13c, +63 (per-path differences kept on purpose);
  - Task 12c's unplanned +60.
- In Task 13 itself, the policy-reachable `numCarsAtHome`/`minBatteryLevelAtHome` pair (≈ 20 lines in both modules) and their HaVehicle fields stay.
- No deletions were padded to close the gap.

**Other budget figures:**
- The pre-flight-slim gross budget (≤ 1,400 added since 39d7cfb) is not met: 2,746 added. The progress ruling made the binding checks net growth against 6a6c14e (now −152 `.py` lines) and removed ≥ added since 39d7cfb (PASS).
- The ≥ 3,000 removed check passes (5,231).

## Concerns

1. **The audit's "no caller" list missed dynamic access.** `numCarsAtHome` and `minBatteryLevelAtHome` are reachable from user policies through `Policy.py`'s `getattr`, so they were kept against the brief. Removing them is a user-visible API change, so it is the user's decision.
2. **The changelog phrasing of the reconciler's paid cap and limit-before-start is condensed from the rulings.** A reviewer should check it against Rules.py and Reconciler.py: I wrote "at most four times in all".
3. **The startup "Providers:" log line no longer lists TeslaMateVehicle or FleetTelemetryMQTT.** Nothing parses it. The change is not in the changelog, because providers are new in 1.4.0.
4. **The lib total is 581 over 26,750 (315 over the plan's projection).** The CarApiVehicle phase is the planned closer.

## Fix round 1 (review: slim-task-13-review.md)

| Commit | What | lib Δ |
|---|---|---|
| c726cad | C1: restore `APIValidator.validate_float` verbatim from 6c75533; new `tests/unit/test_api_consumption_offset.py` | +21 |
| 64766fb | I1, I2, M1, M2: docs and changelog | 0 |
| e6e67d7 | M4: black on TeslaPowerwall2.py, Gen2TWCProvider.py, Desired.py (and APIValidator.py); the two provider header comments reflowed | +2 |

- **C1:**
  - `test_api_consumption_offset.py` drives the real `/api/setConsumptionOffset` handler: 2.5 → 204 and saved; "abc" → 400; missing → 400. It also tests `validate_float` directly.
  - With the method removed, 3 of the 4 cases fail with `AttributeError`. The missing-offset case never reaches `validate_float`.
- **Deleted-name check:** every name this task deleted was grepped across HTTPControl.py, `tests/integration`, `tests/API`, `lib/TWCManager/Control/themes` and `html`, using `git grep -w`.
  - The only code hit was `validate_float` (HTTPControl.py:1052), now restored.
  - `summary()` hits are `Vehicle.summary` in vehicles.html.j2 and vehicleDetail.html.j2, which is kept.
  - The words `charging`/`charge_limit` appear only in prose or as unrelated identifiers.
  - Nothing else matched.
- **I1:**
  - CHANGELOG.md:36 now carries the review's wording. I checked it against `Reconciler.py:310-343` and `Desired.py:348-360`:
    - `freeFailed = not free or …`;
    - the second send needs `paidRetryDue` or `reachedCar`;
    - the re-arm needs `not paidReached` plus a reached reading, `ride` or `_chargingSince`, at most once per desire;
    - a non-blind paid attempt may wake and reads up to `READ_MAX_AGE + PAID_AFTER`.
  - `Belief.reachedCar` (a live source, or a value unlike the belief at the send) matches "a reading shows the command reached the car".
- **I2:**
  - Settings.md now says: free providers first; billed only when no free one can serve the car or after 5 min / 60 s; at most four sends per desired value; `prefer_ble` "after a delay".
  - The config.json commandPolicy comment says the same.
- **M1:**
  - The changelog says "the per-VIN vehicle command dispatch" in place of "the vehicle command queue".
  - #667 is folded into the reconciler entry ("a pending stop is cancelled when charging is wanted again").
  - The #667 bugfix line and the VehiclePriority fix line are removed.
- **M2:** the PolicyCustomization steps now match `Targets._present`:
  - the position decides home or away for a Tesla API car;
  - the plugged/held fallback applies only to a Tesla API car with no position;
  - an HA-tracked car is at home exactly when HA says so.
- **M3:** the TelemetryProvider row now cites the `test_telemetry_registry.py` tests.
- **M4:**
  - `black --exclude="setup.py|tests/*" --check lib` passes: 93 files unchanged.
  - The restored `validate_float` also needed black, because the file's spacing changed.
- **M5:** no change.

**Suite:** 1733 passed, 1 xfailed (+4 tests).

**lib:**
- Fix round 1 is +23; the lib total went from 27,331 to 27,354.
- Task 13 in total is −378: 27,732 → 27,354.
- The total is 604 over 26,750.
- Since 39d7cfb: added 2,751, removed 5,213; the awk exits 0 (PASS).

