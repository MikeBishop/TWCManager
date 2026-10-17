# Final-review fix round: re-review

Scope: presence/3 3e20776..6c61310, presence/4 8152165..8f47928 (rebased), deploy/presence-3 merges b637a6e and 1d4258b. I checked the deploy tree at 1d4258b directly. Mutations ran in a `git archive 1d4258b` copy (`scratchpad/rr`); `wt-plug` was not modified.

Focused run at 1d4258b: test_vehicle_presence, test_plug_presence_scenarios, test_presence_handlers, test_teslaapi_controller, test_teslaapi_evse, test_twcmaster. Result: **286 passed**.

### Finding Verdicts

**I1: ADDRESSED.** It is built to the user's reconciliation design.
- `VehiclePresence.py:1286-1320` (`_sweepHeld`) and `:1322-1348` (`_remoteRestoreIfDue`) are the single remote code path. `_startDeparting` (`:1268-1284`) opens a `DepartingRecord` only when BLE applies, and only for the BLE-first window. `departingHandler.onDeparting` no longer queues a remote restore (`PresenceHandlers.py:141-146`).
- The state is the saved limit. `_restorePending` means `lastApplied != -1`. A failed restore leaves the limit held, so the next pass finds it again.
- Backoff is per VIN and in memory: `_remoteRetry`, 600 s doubling to a 3600 s cap. Only an actual attempt advances it. It is dropped when the limit stops being held (`:1298-1301`) and in `_goHome` (`:1236`).
- No double-queue: `_restoreQueuedNow` blocks a second queue entry, and the queue key `(applyChargeLimit, vin)` coalesces anything that gets past it.
- No zero-delay loop: every attempt sets `now + >=600`, and the thread wakes every 60 s while any car is NOT_HOME (`_timeUntilNextDue`).
- Every attempt goes through `departureHandler` → `_remoteRestore` → `hasRemoteChannel` (`slotFor("command")` plus commandPolicy, `PresenceHandlers.py:9-23`) → queued `remoteOnly` → VehiclePriority.

Traces I re-ran myself with ad-hoc tests against the real `departureHandler`:
- **BLE car, prefer_ble, Fleet command slot, BLE never reachable after unplug.** BLE restore queued at once (`localOnly`), then remote attempts at **360, 960, 2160, 4560 s**. Exactly 4 `remoteOnly` tasks were queued.
- **Same car under ble_only.** The handler is asked on the same schedule (4 times in 8000 s). Each time it logs "no remote command channel…" and queues nothing. There is no tight loop.
- **Success stops it, arrival cancels and resets.** Covered by `test_a_successful_restore_stops_the_retries` and `test_arrival_cancels_the_retry_and_resets_the_backoff`. I read both and they assert the right things.
- **Startup with a held limit and the car not home.** A non-BLE car is tried on the first pass (`test_held_limit_at_startup_...`). A BLE car gets the BLE restore on the first pass, and the remote route follows after its window closes.
- **A presumed car (no evidence) is never restored.** The sweep lists only `home is False`, and both `_sweepHeld` and `_remoteRestoreIfDue` re-check `NOT_HOME` under the lock. My ad-hoc test (presumed car, held limit, Fleet slot, 8000 s of passes) made no handler call and queued no command.

**I2: ADDRESSED.**
- `bleSilent` (`VehiclePresence.py:444-462`) now needs at least 2 failures since the last success, at least `PROBE_INTERVAL` apart. A single failed probe therefore never lists a Fleet EVSE: `test_one_failed_probe_on_arrival_lists_no_fleet_evse` checks one failure gives no EVSE, two do, and a later success removes it.
- The re-probe is BLE only (`_probe(bleOnly=True)`, sources `("ble",)`) and never wakes the car. The test asserts the calls are `["ble"]*4`.
- A success clears `_reachFail` and the recheck (`:1035-1038`). Leaving home clears both (`_setHome(False)`, `:1253-1256`).
- The recheck chain is scheduled only for a HOME car that BLE applies to and that no TWC names or is attributed to. Only one recheck is pending at a time.

**M1: ADDRESSED.** `_startDeparting` no longer probes inline; it nominates the first probe for `+DEPARTING_PROBE_INTERVAL` (`VehiclePresence.py:1284`).

**M2: ADDRESSED.**
- `observeProof(vin, source, twc=None)` (`:554-560`). `TWCMaster.py:1482` passes `slaveTWC._presenceKey()`, which is the same hex key `observePlug`/`observeUnplug` use.
- `_applyProof` drops a `_twcVin` entry for that TWC when it names a different VIN (`:1094-1104`).
- The proof value is now a tuple. Both consumers were updated: `runPass` at `:714-717` and `_apply` at `:1018-1019`.

**M7: ADDRESSED.**
- The TeslaBLE comment no longer mentions DEPARTING.
- The PresenceHandlers restore comments describe the backoff route (`PresenceHandlers.py:105-109`, `:117-129`, `:164-167`).

**commandPolicy gate: ADDRESSED.**
- `TeslaAPIEVSE.setTargetPower` returns before queueing `fleetSetChargeRate` under ble_only (`EVSEInstance/TeslaAPIEVSE.py:136-153`). It reads the policy the same way `hasRemoteChannel` does and falls back to prefer_ble.
- `test_ble_only_command_policy_queues_no_fleet_rate` covers both policies.
- This gate is needed. `VehicleCommandQueue._DISPATCH["fleetSetChargeRate"]` calls `task["module"].setChargeRate` directly (`_OWN_MODULE`), and `TeslaAPI.setChargeRate` checks only the read-only token.

### Mutation checks (archive copy, focused suites)

| Mutation | Result |
|---|---|
| I1: never retry after the first attempt (`if retry is not None: return`) | 7 failures, including `test_non_ble_car_backs_off_600_1200_2400_then_hourly`, `test_ble_car_backs_off_from_the_end_of_its_ble_window`, `test_a_queued_or_running_restore_is_not_queued_again`, and the scenario `test_fleet_only_failed_remote_restore_is_retried_after_600_s` |
| I1: no backoff (retry every pass) | Fails, including the scenario test |
| I2: delete the two-failure rule in `bleSilent` | 3 failures: `test_one_failed_probe_on_arrival_lists_no_fleet_evse`, `test_two_failed_probes_close_together_are_not_ble_silent`, `TestBleSilentRecheck.test_failed_probe_is_confirmed_then_rechecked_slowly` |
| I2: recheck not BLE-only | `test_failed_probe_is_confirmed_then_rechecked_slowly` fails |
| I2: delete only the `fail[1] < 2` term | All pass. This is an equivalent mutant: with one failure, `reach[1] == fail[0]`, so the spacing term already returns False. It is not a test gap. |

### New Breakage in the Fix Diff

No Critical or Important issues.

- **Minor, cosmetic: `VehiclePresence.py:1381-1386`.** When the BLE window closes, an INFO line says "...restoring remotely" even under ble_only. The handler's "no remote command channel can restore…" line follows it at once, so the log contradicts itself once per departure.
- **Minor, test gap: presumed cars.** No dedicated test asserts that a presumed car with a held limit gets no restore, which is the user's explicit invariant. The code guards it twice (the sweep lists only `home is False`, and both functions re-check `NOT_HOME`), and my ad-hoc test confirms the behaviour. A mutation that widened the sweep and dropped one guard did fail 6 existing tests, but those tests are about other things, so they catch it only by accident. Suggest adding a dedicated test before the PRs.
- **Already disclosed in the fix report, accepted.**
  - Under ble_only, a BLE car away with a held limit produces one INFO line per backoff step (hourly at the cap).
  - `_resetLimitState` runs on each attempt.
  - A remote restore never wakes an asleep car, so "retried" does not mean "will land while it sleeps".

### Remaining command-path bypasses of commandPolicy

- **`TeslaAPI.apiDebugInterface` (`Vehicle/TeslaAPI.py:175-197`).** It is reached from HTTPControl `/api/sendTeslaAPICommand` (`Control/HTTPControl.py:774-786`) and calls `setChargeRate` and `wakeVehicle` directly, without VehiclePriority. It is a user-initiated web debug action, not automatic; it does honour the read-only token check.

No automatic bypass remains. I checked every caller of `setChargeRate`, `car_api_charge`, `applyChargeLimit`, `wakeVehicle` and `car_api_available` outside the vehicle modules:
- Commands go through the queue, which resolves VehiclePriority first, or through `fleetSetChargeRate`, which is now gated.
- `TeslaAPI.car_api_charge`'s internal `self.applyChargeLimit` (`TeslaAPI.py:~906`) runs only inside a `car_api_charge` that VehiclePriority already let through.
- The `wakeVehicle` calls at `TeslaAPI.py:2519/2674` are BLE wakes.
- `updateChargeAtHome` is a read.
- `startCharging`/`stopCharging` on TeslaAPIEVSE queue `charge` through VehiclePriority.
- TeslaBLE's only use of the TeslaAPI module is the read `vehicleScheduledChargingPending` (`TeslaBLE.py:229-233`); it has no BLE-to-API command fallback of its own.

### Out-of-Scope Observations

- **The EVSE is still listed and budgeted under ble_only.** Its share is simply not sent, so if a car ever qualifies (HOME, bleSilent, not TWC-named) the TWC loses that share until BLE answers. With the two-failure rule this is rarer. Making `TeslaAPIEVSE.isReadOnly` (or `allEVSEs`) honour ble_only would remove the wasted budget. The fix report discloses this.
- **TeslaAPIEVSE `stopCharging`.** Under ble_only, a zero-share stop from the distributor for a listed EVSE would go to BLE `charge_stop` for a car that may actually be on the TWC. This is the "distributor zero-share stop" item already ruled to a separate branch, and the two-failure rule makes it rarer.
- **The silent recheck writes its due time straight into `_due`**, so it skips `nominate`'s dedupe and trim. The trim keeps the earliest 64 times (`MAX_DUE_PER_VIN = 64`), so it could drop the recheck only with more than 64 earlier due times for one VIN. That is not reachable in practice.
- **Slow BLE probes continue indefinitely.** After the BLE window closes, the departing record keeps BLE probes every 600 s for as long as the limit is held (pre-existing behaviour). Under ble_only on the box, a car away for days holding a limit gets a BLE body-controller probe every 10 minutes, and each one can hold `_bleLock` up to `presenceProbeTimeout`.
- **Deploy merge (b637a6e, 1d4258b): intent unchanged.**
  - The non-context lines of `git diff 14ae080 cce331f -- lib` and `git diff 8f47928 1d4258b -- lib` are byte-identical, so the token-slot delta is unchanged.
  - `hasRemoteChannel` uses `slotFor("command")` and the API presence source uses `slotFor("read")`.
  - No removed accessor is reintroduced: no `.carApiBearerToken`, `.carApiRefreshToken` or `.carApiTokenExpireTime` attribute and no `getCarApiBearerToken` in lib. The remaining hits are settings keys and the HTTPControl form field names.
  - The scenario and presence tests use `storeToken(fleet_token()/owner_token())`.
  - The test-side delta shrank only because 8c11dea carried the cce331f test edits back into presence/3. I checked the test names to confirm.
    - Every `def test_` at 8f47928 or cce331f is present at 1d4258b, with two kinds of exception.
    - Seven token tests from 8f47928 are missing, but they were already absent at cce331f (deploy replaced them with the slot tests).
    - Two cce331f tests are missing because I1 renamed them on purpose (`..._sends_one_remote_restore` → `..._closes_the_ble_window`; `test_departing_non_ble_car_queues_one_remote_restore_now` → `..._is_left_to_the_remote_route`).

### Verdict

**Fix round:** All addressed, no new Critical/Important. Two Minor items remain: the contradictory "restoring remotely" INFO line under ble_only, and the missing unit test for "a presumed car is never restored". Fix both before the PRs; neither blocks the deploy.

**Deploy to box now?** Yes.
- On the box (ble_only, Owner and Fleet slots, BLE car), the remote route reaches the handler on the backoff and queues nothing.
- The newly found Fleet EVSE rate bypass of ble_only is closed.
- I2 no longer lets a single failed probe hand a car on the TWC a Fleet EVSE.
- The deploy merge keeps the token-slot port intact.
- Watch for:
  - the hourly "no remote command channel" INFO line while the car is away holding a limit;
  - BLE probes every 10 minutes for that car;
  - no `fleetSetChargeRate` or `set_charging_amps` anywhere in the log.
