# Task 8 report: delete the polling the watch replaces

Status: DONE_WITH_CONCERNS. Commit 175948ca on vehicle-model/phase6 (base e3a08225). Not pushed.

## Results
- Full suite: 2332 passed, 1 xfailed. BASE was 2332 passed + 1 xfailed. 5 tests added, 5 deleted, 2 rewritten.
- Parity: `tests/unit/test_command_path_parity.py` was not edited (git diff is empty). 113 passed. No count moved.
- lib: 26971 → 26906 (**−65**). Watch.py unchanged at 371 lines. Run.py, TeslaAPIProviders.py and Watch.py were not touched (see deviation 1).

## Deleted or rewired
- TeslaAPI
  - Removed `lastChargeCheck`, `chargeUpdateInterval`, `updateChargeAtHome`, `is_far_from_home` and `update_charge`. After this task nothing in lib called `is_far_from_home` or `update_charge`.
  - Removed the `inside`/`HOME`/`presence` imports and the dead `lat, lon` line.
  - `update_vehicle_data` now sets one deferral value after a successful read: `car.statusDeferral = now + READ_MAX_AGE`. `fetch` honours the deferral as before.
  - `minBatteryLevelAtHome` and `numCarsAtHome` only read the registry now.
  - If `cloudUpdateInterval` is present, TeslaAPI logs one INFO line at construction: "Car reads ignore cloudUpdateInterval: the watch sets them". The wording is deliberate because `EMS/TeslaPowerwall2.py:45` still uses the same key as its cloud cache time, so the key is not dead overall.
- HomeAssistant
  - `updateChargeAtHome` is deleted; nothing called it after this task. The watch calls `refresh_from_home_assistant` directly.
  - `numCarsAtHome` and `minBatteryLevelAtHome` no longer refresh.
- TWCMaster.updateChargeAtHome
  - It is now the power-start hook: `watch = getattr(self, "watch", None)`. For each registry vehicle whose `presence == HOME`, it calls `watch.readNow(vin, "power start")`.
  - The TWC-named car is included because it is HOME.
  - Without a watch it does nothing until Task 9 wires `master.watch`.
- Boot (TWCManager.py)
  - The boot `checkCharge` used to be what loaded the Tesla vehicle list, through `TeslaAPI.updateChargeAtHome → loadList`. It is replaced by queueing `refreshTokens` with no delay. Its first run loads the list, because `listPending()` is true at boot, and the 5-minute self-requeue continues as before.
  - Side effect: FleetTelemetryMQTT `checkConfigs` (free calls, at most once a day) now runs at boot instead of 5 minutes later.
  - The `checkCharge` task name survives as the power-start carrier (`TWCSlave.py:678`).
- Comment updates in Fields.py (READ_MAX_AGE) and Telemetry.py (the list-load note).

## Tests
- New, each confirmed to fail with its rule removed:
  - `test_watch::test_a_power_start_asks_the_watch_to_read_every_home_car`
  - `test_teslaapi_providers::test_two_callers_inside_read_max_age_pay_once`. Plumbing change: the deferral runs on real `time.time`, so the test ages `statusDeferral` itself, as test_watch's `later()` already does.
  - `test_teslaapi_registry::test_min_battery_level_at_home_reads_the_registry_and_queues_nothing`. Plumbing change: built on test_limit_reconciler `setup` + `new_api`, because `listed()`/`apiWith()` don't exist.
  - `test_teslaapi_registry::test_cloud_update_interval_is_ignored_with_one_log_line`
  - `test_watch::test_the_pre_command_ping_trusts_a_watch_ping_inside_its_cadence`. This one is reworked; see deviation 1.
- Rewritten:
  - `test_presence::test_away_cars_keep_the_status_deferral_ladder` → `test_every_read_defers_the_next_by_the_read_max_age`.
  - `test_update_charge_at_home_reads_only_home_cars` → `test_a_power_start_asks_a_read_of_home_cars_only`, which uses an `m.watch` Mock and covers both the AWAY and the presumed cases.
- Deleted:
  - `TestCheckChargeRefreshesEachModuleOnce` (3 tests). The per-module dispatch and suppression walk is gone; the watch's reads go through `providerOrder.candidates`.
  - `test_ble_read_marks_car_awake_but_cache_hit_does_not` and `test_ble_read_on_an_injected_clock_marks_car_awake`. The behaviour they covered (a BLE read sets `lastAPIAccessTime`) lived only in `update_charge`.
  - `lastAPIAccessTime` asserts removed from `test_read_stamped_like_the_previous_one_still_counts_as_fetched`.
- Mechanical updates:
  - `api.update_charge(v)` → `v.read("batteryLevel", maxAge=READ_MAX_AGE)`.
  - `api.updateChargeAtHome()` → `api.loadList()` in the held-limit, list-load and charging tests.
  - `is_far_from_home` mocks dropped.

## Deviations / concerns
1. **Rule (k), the pre-command ping trusting the watch's cadence, is not implemented. With default cadences it changes nothing.**
   - `Presence.asleep(v, lately)` returns True for a newest-asleep reading whatever its age. The window only bounds the awake answer, False.
   - So the brief's case, an asleep car pinged 8 minutes earlier on a 15-minute cadence, is already not re-pinged. I checked this: the brief's test passed with `freshFor` stubbed to return REACH_WINDOW.
   - For an awake car, every awake cadence (homeAwake 240; awayAwake 300, which is also the cadence for charging and unknown cars) is at most `REACH_WINDOW` (300). So a car the watch has heard from always falls inside the existing window.
   - `freshFor` would only matter if someone configured `homeAwakeSecs` above 300. In that case it would trust an awake answer older than 5 minutes before a no-wake command, and the car may have fallen asleep in between.
   - Instead, the test pins the invariant: it asserts `max(homeAwakeSecs, awayAwakeSecs) <= REACH_WINDOW`, and checks that an awake car the watch pinged `homeAwakeSecs - 1` seconds earlier gets no second ping before a quiet (lowering) command. It fails if REACH_WINDOW drops below the cadence.
   - If you still want `freshFor`, it is about 6 lines (Watch + Run).
2. A BLE read no longer stamps `lastAPIAccessTime`. That only lets the cloud skip its free online check for 2 minutes, so the cost is at most one extra free call.
3. Until Task 9 wires `master.watch`, two things happen on a running box:
   - A power start reads nothing.
   - HA cars' battery levels are no longer refreshed by the policy's `minBatteryLevelAtHome`/`numCarsAtHome`.
4. Task 10 docs: shipped `etc/twcmanager/config.json`, `demo.json` and `.testconfig.json` still carry `cloudUpdateInterval: 1800` with a comment saying it paces cloud polling. Every default install will log the INFO line once. Those comments should say the key now only sets the Powerwall cloud cache.
5. The `inside()` import was the only use in TeslaAPI and is now gone. `Presence.inside` is still used elsewhere.

## Fix round 1 (amended: c398f77f)
- **Finding 1:** HomeAssistant's `minBatteryLevelAtHome` now reads the registry: `min([v.value("batteryLevel", 10000) for v, _ in cars] or [10000])`.
  - Deleted the `HaVehicle.battery_level` cache field, its comment, and its assignment in `refresh_from_home_assistant`.
  - New test `test_homeassistant_registry::test_min_battery_level_at_home_is_the_registrys_not_the_last_ha_parse`: HA parses 50, BLE then observes 33, and the property must return 33. Against the old HA code it fails, returning 50.
  - Dropped the stale `hv.battery_level` assert in `test_refresh_does_not_resurrect_forgotten_vehicle`.
- **Finding 3:** the test_held_limits comment now says "the next token refresh resolves".
- **Finding 4:** the READ_MAX_AGE comment now says "a cloud read", not "a paid cloud read".
- **Finding 5:** the TeslaAPI comment now reads "The Powerwall reads it as its cloud cache time".
- **Finding 6:** the cloudUpdateInterval test now counts the log records and asserts there is exactly one.
- **Finding 7:** moved "# VIN2: presumed" onto the HOME `assert_called_once_with` line.
- **Findings 2 and 8:** left to Task 10 (changelog) and Task 9, as ruled.
- **Suite:** 2333 passed, 1 xfailed.
- **Parity:** the parity file is identical to e3a08225.
- **lib:** 26971 → 26900 (−71).
