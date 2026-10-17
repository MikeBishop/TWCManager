# Slim Task 13 review (6c75533..b4f3b39, 9 commits)

**Spec compliance: PASS with one deviation.** `APIValidator.validate_float` was deleted. It was not on the brief's list, and it is live (C1). The other kept-against-brief items (`numCarsAtHome`, `minBatteryLevelAtHome`, `HeldLimits.holding`, `ChargingPoint.vehicleEndpoints`, the TeslaAPI `getCarApiVehicles`/`getVehicleCount`) are each correctly kept: each has a live caller or is reachable from a policy.

**Quality/cost/security: CHANGES REQUIRED.** 1 Critical, 2 Important, 5 Minor.

**Verified:**
- **Suite:** 1729 passed, 1 xfailed at b4f3b39. The tree stays clean.
- **Mutations:** 18 run, 18 killed, all in a `git archive` copy. One cited test missed its mutation and needed a re-target (see M3).
- **Line figures:** they reproduce exactly. The lib total is 27,331. 6c75533 → b4f3b39 is +60/−461 (−401). Since 39d7cfb it is +2,746/−5,231, so removed ≥ added and the awk exits 0. The origin/main and 6a6c14e shortstats match the report.

## Critical

### C1. `/api/setConsumptionOffset` crashes: a live `validate_float` was deleted

**Evidence:**
- `lib/TWCManager/Control/HTTPControl.py:1052` calls `APIValidator.validate_float(offset)`. The call is also on origin/main (`HTTPControl.py:914`).
- 0364f3a deleted the method; `APIValidator.py` now holds only `validate_json`.
- Repro at HEAD: `AttributeError: type object 'APIValidator' has no attribute 'validate_float'`.
- `do_POST` has no try/except, so the request ends with no response.
- The report says "`validate_float` was not in the brief, but the audit's 'only `validate_json` is used' covers it". That audit line was wrong, and a one-word grep finds the caller.
- The endpoint is pinned by `tests/integration/test_api_endpoints.py:156` (`test_set_consumption_offset`), and by `tests/integration/test_api_input_validation.py:302-342`. The gating run excludes `tests/integration`, so nothing caught it.

**Fix:**
- Restore `validate_float` verbatim from `git show 6c75533:lib/TWCManager/Control/APIValidator.py` (lines 71–89). The handler unpacks its `(success, value, error)` 3-tuple.
- Add a unit pin, for example `test_api_validator.py::test_validate_float_accepts_numbers_and_rejects_text`. The integration folder is not in the gate.
- `validate_float` is not in `test_no_legacy_command_paths.py`'s pattern, so no grep change is needed.
- Before re-review, re-grep each name 0364f3a deleted. This was done here: no other deleted name has a caller.

## Important

### I1. The changelog's paid-send sentence misstates when a resend happens and leaves out the per-send cost

**Evidence:** `CHANGELOG.md:36` says a paid provider "sends a desired value once, retries it once, and sends it again only after a newer reading of the car, at most four times in all". Against `Reconciler.py:318-342` and `Desired.py:348-360`:
- **"Only after a newer reading" is wrong for two cases.**
  - The re-arm at `Reconciler.py:324-336` also fires on `ride`, a wanted start that needs a cloud wake (`_startWanted`). No reading is needed, and that re-arm can send twice more, with a wake.
  - Any reading does not qualify. It must be one that *reached the car*: a live source, or a value unlike the belief at the send (`Belief.reachedCar`). The re-arm also happens only when no earlier paid send reached the car (`not rec.paidReached`).
- **"Retries it once" applies only in some cases.** The retry is blind, never wakes, reads nothing, and runs only after a first send that failed retryably and was not a failed wake (`Desired.py:353-356`).
- **"At most four times in all" counts commands only.** The count itself is correct: 2 sends per arm × 2 arms. But each non-blind paid send may carry a billed `wake_up` (`Reconciler.py:377-379`) and a read-before-write. That read is a Fleet `vehicle_data`, up to 3 GETs (`maxAge = READ_MAX_AGE + PAID_AFTER`). A cost-reading user will take "four" as the number of billed calls.
- **"Used only after the free ones have failed for 5 minutes / 60 seconds" is wrong with no free candidate.** On a Fleet-only install, `freeFailed = not free` at `Reconciler.py:313` is true at once, so the paid provider is used immediately.

**Fix:** reword along these lines:

> A paid provider (Fleet API, Home Assistant) is used at once when no free one can serve the car, else only after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps). It sends a desired value once, and once more after a failure, or after a reading shows the command reached the car. If no send reached the car, a reading from the car or a pending start allows two more. That is at most four commands per desired value; each may be preceded by a wake and a vehicle_data read.

### I2. Settings.md's command-policy section still describes walk-to-first-success

**Evidence:** `docs/Settings.md:59` says commands "walk a fixed order of providers … The first provider that succeeds wins". That was VehiclePriority. The reconciler sends one attempt to one provider. A billed provider is used only after the free channel has failed for `PAID_AFTER` (300 s for a limit, 60 s otherwise), with the send cap described in I1.
- `prefer_ble` ("fall back to cloud", line 61) gives no hint of the delay or the cap.
- The `etc/twcmanager/config.json:811` comment says the same.
- The brief puts docs accuracy for `commandPolicy` in scope. This is the page users read for when billed commands go out.

**Fix:**
- Replace the first sentence with: "Vehicle commands go to the first ready provider in a fixed order: the TWC itself, then BLE, then the cloud, with billed providers (the Fleet API, then Home Assistant) last. A billed provider is used only when no free one can serve the car, or after the free ones have failed for 5 minutes (charge limit) or 60 seconds (start/stop, amps), and sends each desired value at most four times."
- Add "after a delay" to `prefer_ble`'s line and to the config.json comment.

## Minor

### M1. "Removes … the vehicle command queue" is inaccurate, and older 1.4.0 entries contradict it

**Evidence:**
- `Reconciler.py:25,108` still builds `VehicleCommandQueue` as its ble/cloud attempt queues. What went was the legacy queue *mode* and the per-VIN command dispatch.
- Two 1.4.0 Bugfixes entries describe code that no longer exists:
  - "Queue vehicle commands per VIN and really cancel pending stop-charging commands (#667)", at `CHANGELOG.md:47`;
  - "VehiclePriority now treats TeslaAPI 'error' …", in the same section. VehiclePriority shipped in v1.3.3 and this entry removes it.

The report says the changelog lists only changes against 1.3.x.

**Fix:**
- Say "Removes VehiclePriority, the per-VIN vehicle command dispatch, …".
- Fold the #667 entry into the reconciler entry: a stop is cancelled when a start becomes desired.
- Drop the VehiclePriority bugfix line, or mark it superseded.

### M2. PolicyCustomization's presence steps are slightly off the code

**Evidence:** `docs/PolicyCustomization.md:54-63` against `Targets.py:29-45`:
- Step 3 (last plugged in at home, or a held limit) applies only to a car with a TeslaAPI attachment (`if api is not None`). A BLE-only or HA-only car with a held limit is not present through step 3.
- A car with a Home Assistant attachment returns `bool(ha.at_home)` and never reaches step 5 (the BLE key). The doc's "else" implies an HA-not-home car with a BLE key still counts.
- The no-home paragraph is otherwise accurate:
  - `locate()` never seeds home (`TeslaAPI.py:1857`);
  - `update_location` seeds home from a fix ≤ 600 s old;
  - HA seeds home from any position (`HomeAssistant.py:565`);
  - `setLatLon`/`setSetting` and the settings-page "learn" work as described.

**Fix:**
- Step 3: "for a car on your Tesla API account, with no usable position: …".
- Step 4: "a car Home Assistant tracks counts as at home exactly when Home Assistant says so; else".

### M3. A deleted-test mapping row cites a test that does not pin the feed wiring

**Evidence:** the TelemetryProvider row says feed liveness is pinned by `test_registry_vehicle.py::test_registry_liveness_feeds_age_and_trusted`. That test uses a fake `Reg`.
- Mutating `VehicleRegistry.registerLiveness` to drop the feed leaves it passing (D3 survived).
- The real pins are `test_telemetry_registry.py::test_connection_state_is_the_feed_liveness`, `test_subclass_connects_set_liveness_and_teslamate_healthy_gates_it` and `test_own_write_then_silent_healthy_feed_is_trusted_after_feed_lag`. Removing `Telemetry.py:78`'s `registerLiveness` call fails 10 tests (D3c).
- The behaviour is covered; only the citation is wrong.

**Fix:** cite the `test_telemetry_registry.py` tests in the row.

### M4. The autoblack CI check now fails on three files that were clean at BASE

**Evidence:** `black --check` passes all three at 6c75533 and fails them at b4f3b39. `.github/workflows/autoblack.yml:35` runs `black --check` over lib.
- `TeslaPowerwall2.py:306`: the line is 91 characters.
- `Gen2TWCProvider.py:20`: a missing blank line before the class.
- `Desired.py:141,157`: missing blank lines before the classes.

`Gen2TWCProvider.py:1-3` and `Gen3TWCProvider.py:1-4` also have header comments broken mid-sentence where text was cut.

**Fix:** run `black` on the three files and reflow the two header comments.

### M5. The startup "Providers:" line no longer lists the telemetry feeds

**Evidence:** at `Order.py:208-209`, only `registerProviders` logs the line.
- No doc or test references the line (`git grep "Providers:"` finds only Order.py), and nothing parses it.
- A `providerSuppressions` entry naming `TeslaMateVehicle` was already a no-op. It is now dropped at DEBUG (`Suppressions._parse`).
- Settings.md:86 now says the feeds are not providers.
- The only cost is a user comparing logs before and after.

**Fix:** none required. Optionally, log "Telemetry feeds: TeslaMateVehicle, FleetTelemetryMQTT" once where `registerLiveness` runs.

## Checks with no finding

- **Deletions:**
  - Every deleted name except `validate_float` was grepped across `lib`, `html`, `lib/TWCManager/Control/themes`, `etc`, `docs` and the config samples, and none has a caller.
  - `Policy.py:412-417` `modules.X.Y` returns the attribute raw. Of the deleted module attributes, only a policy reading `Gen3TWCs.unitTargets` or `sharedControl` could have reached any, and neither is useful in a condition.
  - `numCarsAtHome` and `minBatteryLevelAtHome` and their HaVehicle fields (`battery_level`, `lat`, `lon`, `at_home`) stay. Nothing reads HaVehicle's deleted `charge_limit`, `available_current`, `charging` or `last_state_update`.
  - The templates use only `Vehicle.summary` and `VehicleRegistry.summaries`, which are kept.
- **`_request` collapse:** the behaviour is identical.
  - `tries=3`, the default: one refresh, then a resend. `tries=2`: one refresh, no resend. `tries=1`: no refresh.
  - The read loop's `3 - sent + (not refreshed)` maps 4/3/2/1 onto the old `resend=sent<2, retried=refreshed` in every reachable state.
  - At most 3 vehicle_data GETs: (no refresh) 3 sends; (refresh on the first) 2 + 1; (refresh on the second) 1 + 2. Energy and command callers keep the old defaults.
  - Seven mutations were all killed: drop `+ (not refreshed)`; refresh always allowed; a refresh consumes no try; the resend after a refresh is not counted; cap 1 → 2; refresh gate `> 1`. The kills came from `test_a_read_refreshes_at_most_once_across_its_tries`, `test_a_refresh_spends_one_of_a_reads_three_tries` and `test_every_path_classifies_status_codes[...-401]`.
- **Storm Watch:**
  - Both GETs have `timeout=10`. Both warnings log `type(e).__name__`.
  - The 403 branch is equivalent to the old nested form: a Fleet 403 still refuses `"energy"`, and anything else warns.
  - There is no other behaviour change, and it is not routed through `_request` (per the ruling).
  - Four mutations (each timeout, each log) were all killed by `test_storm_watch_times_out_and_logs_no_exception_text`.
- **Age guard:** `<=` → `<` fails `test_an_away_fix_stamped_at_our_write_instant_is_no_departure`. The test asserts the equal stamps explicitly.
- **`resolveLegacyIds`:** correct.
  - A malformed store entry was already unreadable (`get()` and `_snapshot()` go through `_storedEntry`), so replacing it with the legacy entry loses no readable limit. Before, the legacy limit was lost and the log claimed it was "kept".
  - A well-formed entry follows the unchanged kept/merge rules.
  - Reverting to `vin not in store` fails `test_resolving_replaces_a_malformed_vin_entry`.
- **Deleted-test mapping:** 4 rows were mutation-checked, and each named replacement fails:
  - `syncSource` default → `test_sync_getters_have_legacy_defaults_before_any_state`;
  - `_fresher` `>` → `>=` → `test_own_write_stamp_and_freshness` (the `fresherThanWrite` rewrite);
  - Order's skip of a provider without the declaration removed → `test_order_ready_and_available_match_the_rule_the_tables_replace` (the passive row);
  - TelemetryProvider liveness → see M3.
- **Gen3:**
  - The removed `READ_PLUG`/`READ_AMPS` were passive and never walked. `sharedControl`, `unitTargets` and `headroom()` had no reader. The solver, `_unitTargets` and `NO_INDIVIDUAL_STOP` are unchanged.
  - The Wall Connector VIN energy path keeps its classifier and the old default retry (`tries=3`).
  - The Gen3 tests pass, and the six `headroom` assertions are kept through a local helper.
- **Changelog, other rulings:**
  - These are present and accurate: the 13a BLE retry sentence (exactly as the brief has it), the numeric-ID drop (I9), presence and the age guard (12c), BLE → Fleet only after the window, and HA only after Fleet is unavailable or refused (M8).
  - These are also accurate: 10 s reads and at most 3 GETs, the second-refusal retirement and the command-only 412 (13c, Task 5 I1), and Storm Watch.
  - The rulings left out are parity with main or unreleased 1.4.0 features (commandPolicy and Gen3 are listed under 1.4.0 Features).
- **Docs:**
  - BLE retries (`Settings.md:71-73`) match `TeslaBLE.sendCommand`.
  - The `providerSuppressions` paragraph matches `Capability.READS`.
  - The `Vehicle_HomeAssistant.md` field list matches the code.
  - For commandPolicy, see I2. For presence, see M2.
- **Security:** Storm Watch and `_request` log no exception text. The R9 rule holds.
