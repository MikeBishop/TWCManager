# Task 8 review: delete the polling the watch replaces (e3a08225..175948ca)

**Spec compliance: PASS.** Rule (k) is not implemented, by the controller's ruling; the pinned invariant test stands in for it.
**Quality: APPROVE with minor fixes.** The minor fixes are findings 1 and 3–5. None blocks.

## Focus answers

### 1. Paid-call safety
After this change, `update_vehicle_data` is reached only through `_TeslaAPIProvider.fetch`. That path checks the deferral, then the free `is_awake`, and only then pays. Every `Vehicle.read` and `providerOrder.read` caller in lib:

- **Reconciler read before a write** (`Run.py:175`).
  - Its `maxAge` is READ_MAX_AGE plus PAID_AFTER on paid attempts, so a value younger than that never fetches.
  - A paid attempt is capped at 2 sends per desire, plus one rearm of 2.
  - Applicability denies NOT_HOME cars everything except stops and restores. A free restore retries hourly.
  - Exposure: a stop, or a forced restore read (`needsLiveRead`), to an away car that was read 300–1800 s earlier.
    - The old ladder answered that read from stored values. Now it pays.
    - This is bounded by the paid-send cap and the usual departure timing: the first read after a departure paid under the ladder too, and a driving car's deferral was 300 anyway.
    - Not a new unbounded path.
- **Watch** (`Watch.py:319`). It is budget-gated (`watchBudget.spend`) and still meets the deferral through `fetch`.
- **`Presence.checkPlug`** zeroes the deferral before its forced read. That was already true at BASE, so nothing changes.
- **Attribution `fits()`** reads through BLE only.
- **No other readers.** The Vehicles page (HTTPControl), policy evaluation, `numCarsAtHome` and `minBatteryLevelAtHome` make no reads now.
- **Removed:** the 1800 s `checkCharge`, which made a paid read of every HOME Fleet car, and the per-power-start read of every HOME TeslaAPI car. Both are net reductions in paid calls.

Parity is unchanged at 113. No path found that pays more than BASE beyond the bounded away stop/restore case above.

### 2. Boot
`refreshTokens` now runs at boot with no delay. It calls `refreshTokenIfNeeded`, then `loadList()` when `listPending()`, then `checkConfigs`.

The old boot `checkCharge` called `loadList()` unconditionally. But `loadList` already does nothing more than `resolveHeldLimits` once cars are attached, and that returns early when nothing is waiting. So the two are equivalent.

By install type:
- **Owner-only or Fleet-only:** loads through `slotFor("read")`, the same as before.
- **No token:** `_noTokenReason` logs once per change of reason.
- **TeslaMate token sync arriving after boot:** the next refresh loads the list, within 300 s. Before, that took up to 1800 s or an arrival, so this is better.
- **Owner + Fleet:** handled as before.

Ordering at boot: `loadSettings` (held limits) runs before the queue, then the background thread starts, then `reconciler.start`, then the refresh is queued. No hazard. `checkConfigs` runs after `loadList` in the same call, so it now runs at boot.

### 3. Deletions
- lib, html and tests are clean of `chargeUpdateInterval`, `lastChargeCheck`, `is_far_from_home` and `update_charge`.
- The `updateChargeAtHome` and `checkCharge` names survive only as the power-start carrier. That is the builder's call under the spec.
- No dead imports in the touched lib files: `presence`, `inside` and `HOME` are gone from TeslaAPI.
- Remnants:
  - Comment `tests/unit/test_held_limits.py:388` (finding 3).
  - `docs/PolicyCustomization.md:302`, and the `cloudUpdateInterval` comments in `etc/twcmanager/{config,demo,.testconfig}.json`. These belong to Task 10.

### 4. `minBatteryLevelAtHome` and `numCarsAtHome`
**TeslaAPI.** The formula is the one BASE had:
- `homeCars` includes PRESUMED cars.
- A car with no reading counts as 10000.
- What changed is freshness. Nothing refreshes the level on a timer now:
  - charging: the watch reads it every 300 s over BLE, every 900 s from the cloud;
  - awake: read on events;
  - asleep: not read, and the level does not change.
- `limitOverride` uses `minBatteryLevelAtHome − 1`. A level that is stale while charging is too low, which still stops the charge. That is the safe direction.

**HomeAssistant.** These are not dead: `policyValue` resolves `modules.HomeAssistant.*` dynamically. See finding 1.

### 5. `lastAPIAccessTime`
Two consumers read it:
- `_ready` skips the free `is_awake` for 2 minutes after an access.
- `onlineState` returns False inside `delayNextWakeAttempt` of the last access.

The BLE stamp therefore saved at most one free call. Worse, after a failed wake it made a BLE read suppress the cloud online check. Removing it is harmless at worst and arguably a fix.

### 6. Tests and comments
- The new tests fail when their rule breaks:
  - pay-once: without the deferral it pays 2; with an 1800 s deferral the third read never pays;
  - `queue_background_task` → `pytest.fail`;
  - power start with no `updateChargeAtHome` → 0 reads;
  - every-read-defers covers both the far and the driving cases.
- Comments are mostly in present tense. Exceptions are findings 4 and 5.

## Findings (ranked)

1. **Minor: HA's `minBatteryLevelAtHome` reads the module cache `hv.battery_level`, not the registry.**
   - With the per-call refresh gone, that cache updates only when HA itself is parsed: the watch's HA status job for an HA-only car, or the HA provider's reads.
   - For a car that also has BLE or TeslaAPI, the watch pings that instead, so HA's cache freezes.
   - Fix: `v.value("batteryLevel", 10000)` for HA's cars, as TeslaAPI does. Then delete the `battery_level` field and its line 130 assignment, which shrinks lib.
2. **Note: the power start reads HOME cars only.**
   - BASE's HA path refreshed every attached HA car whatever its presence. The new path skips HA and PRESUMED cars.
   - This matches the brief and BASE's TeslaAPI rule. Record it for Task 10's changelog, or include PRESUMED if a car with no location should count.
3. **Minor: stale comment** at `tests/unit/test_held_limits.py:388`. "the next checkCharge resolves" should read "the next token refresh resolves".
4. **Minor: inaccurate comment in `Fields.py` READ_MAX_AGE.** "a paid cloud read answers any other caller" is wrong in one word: free Owner reads set the deferral too. It should say "a cloud read".
5. **Nit: comment at `TeslaAPI.py:205`.** "Still the Powerwall's cloud cache time" narrates history. Suggest "The Powerwall reads it as its cloud cache time". The INFO line also fires on every default install, because the shipped configs set the key. Task 10 should handle the config comments.
6. **Nit: `test_cloud_update_interval_is_ignored_with_one_log_line`** does not assert "one". Count the records.
7. **Nit: misplaced comment in `test_a_power_start_asks_a_read_of_home_cars_only`.** "# VIN2: presumed" sits on the AWAY assert. Move it to the HOME `assert_called_once_with` line, where it explains why VIN2 is absent.
8. **Note: depends on Task 9.** Until `master.watch` is wired, a power start reads nothing and HA levels are not refreshed. Tasks 8 and 9 must ship together.
