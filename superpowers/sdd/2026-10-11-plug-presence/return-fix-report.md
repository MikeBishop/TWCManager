# Return fix report: the restore/arrival race (live bug 2026-10-12 09:17)

Worktree: `scratchpad/wt-plug`. It is left on `deploy/presence-3`, and the tree is clean. Nothing was pushed and nothing was stashed. Interpreter: `<PY>` from global-constraints.

## Branch tips

| branch | before | after |
|---|---|---|
| presence/3-plug-presence | 6c61310 | **8233d6b** |
| presence/4-fleet-rate-queue | 8f47928 | **e987d0a** (rebased with `--onto presence/3-plug-presence 6c61310`, no conflicts) |
| deploy/presence-3 | 1d4258b | **8da7e41** (merged with `--no-ff` from presence/4) |

## Suite counts (`<PY> -m pytest tests/unit -q`)

| branch | before | after |
|---|---|---|
| presence/3 | 1125 passed | **1154 passed** |
| presence/4 (rebased) | n/a | **1212 passed** |
| deploy/presence-3 | n/a | **1382 passed** (the 29 new tests also ran by name on deploy and all passed) |

## Commits on presence/3

### 1eb1ac9: Let our own charge-limit write supersede an older read (Fix 1)

- `ChargeLimitRules.py` now holds the shared rule:
  - `noteChargeLimitWrite(vehicle, limit)` and `noteChargeLimitWriteFor(master, vin, limit)` stamp `vehicle.chargeLimitWritten = (limit, monotonic)`.
  - `noteChargeLimitRead(vehicle)` stamps `vehicle.chargeLimitReadAt`.
  - `latestChargeLimit(vehicle, limit)` returns the limit we wrote if the write is newer than the read. A read with no stamp counts as older than any write. A Mock attribute is ignored.
  - `telemetryChargeLimit` now goes through `latestChargeLimit`.
- The records live on the CarApiVehicle, next to the telemetry value they compete with.
- Where writes are recorded:
  - TeslaBLE: after a successful `charging-set-limit`, through `noteChargeLimitWriteFor`.
  - TeslaAPI: after a successful `apply_charge_limit`.
- Where reads are stamped:
  - `Telemetry.applyDataToVehicle` stamps `chargeLimit` only when the value changes, because a broker replays its retained value on reconnect.
  - `CarApiVehicle.update_charge` (BLE read path).
  - `update_vehicle_data`, which now sets the limit only when `charge_limit_soc` is present, then stamps it.
- TeslaAPI's read before writing passes its `current` through `latestChargeLimit`. This covers live telemetry and also a cached `vehicle_data` value (a status deferral) that predates our write.
- I chose the "written value is authoritative" option over forcing a live read. It does no I/O, and it matches how the code already trusts telemetry that equals our own limit.

### 9c63b15: Let a return plugged in win over the departure restore (Fix 2)

- `VehiclePresence.runPass` collects `pluggedHere`: the VINs whose probe in this pass read them plugged in from a strong source (BLE or TWC) and not on a fast charger.
- `_reconcileDeparting` skips its "retrying its restore" when the probe says plugged in here. It logs "in BLE range and plugged in here; no restore, its arrival follows".
- `_sweepHeld(now, pluggedHere)` also skips those VINs, so the remote route can't fire in the same pass either. I checked that both skips are needed: with the sweep skip removed, a remote restore fires at 960 s in the unit test.
- The queue behaves as the brief expects (verified, no change needed):
  - The arrival's apply and the restore share the key `(applyChargeLimit, vin)`, and `_cancelRestore` drops a pending restore. So an apply replaces a pending restore.
  - A running restore is left alone. It finishes first, then the apply runs, and Fix 1 makes that apply's read correct.

### 8233d6b: Send a TWC's charge rate to the car it names (Check 3)

- `TWCSlave._queueChargeRate` now uses `_chargeRateVehicle()`. It picks the car `_chargeVIN()` names (currentVIN, then plugVIN, then the car a VIN-less plug was attributed to):
  - its CarApiVehicle if TeslaAPI lists one,
  - otherwise the bare VIN.
- With no named car it falls back to the last session's car, then to a broadcast. It also no longer crashes when no TeslaAPI module is loaded.
- `TeslaAPI.setChargeRate` resolves a VIN string to its vehicle, and sends nothing for a VIN it doesn't know. TeslaBLE already accepted a VIN.
- The existing queue tests now mock `_chargeRateVehicle` instead of `getLastVehicle`.

## Check 3 finding

- **It was broken at startup.** The box journal shows:
  - 00:20:48: "BLE: no configured vehicle is a charge candidate; charge rate not sent" three times.
  - 00:21:08: "telemetry being provided by TeslaMateVehicle", meaning the TeslaAPI vehicle list had just loaded.
  - 00:21:53: "Set charge rate 48A for <CarApiVehicle ...>: success".
- **Why:**
  - The targeted path needed a CarApiVehicle (`getLastVehicle()`), and the list wasn't loaded yet, so the rate went out as a broadcast.
  - `broadcastVINs()` correctly leaves out a car a TWC names, so the car got nothing.
  - Without a TeslaAPI vehicle list at all, it would never have been sent.
- **Fix:** commit 8233d6b targets the named car by VIN.

## Tests, with fail-before evidence

**Fix 1**

Tests:
- `test_charge_limit_rules.py::TestOwnWriteSupersedesAnOlderRead` (8 tests)
- `test_teslable_presence.py::TestOwnWriteSupersedesOlderTelemetry` (3)
- `test_teslaapi_presence.py::TestOwnWriteSupersedesAnOlderRead` (4, including telemetry-fed and cached-API variants, and a live read after a write standing)
- `test_telemetry_mapping.py::test_a_new_charge_limit_is_stamped_as_read_and_a_replay_is_not`

The brief's three cases are each covered for TeslaBLE: telemetry 50 at t0 and a restore to 100 at t1, then apply 50 sends; telemetry updated to 100 after t1, apply sends; telemetry 50 sampled after the write, nothing sent.

Run against a no-op stub of the new API (`latestChargeLimit` returns the read):
```
FAILED test_teslaapi_presence.py::TestOwnWriteSupersedesAnOlderRead::test_apply_after_our_restore_sends[TeslaMateVehicle]
FAILED test_teslaapi_presence.py::TestOwnWriteSupersedesAnOlderRead::test_apply_after_our_restore_sends[TeslaAPI]
FAILED test_teslable_presence.py::TestOwnWriteSupersedesOlderTelemetry::test_apply_after_our_restore_sends_despite_older_telemetry
  AssertionError: assert ('charging-set-limit', '100') == ('charging-set-limit', '50')
FAILED test_charge_limit_rules.py::...::test_write_after_the_read_wins
FAILED test_charge_limit_rules.py::...::test_a_never_stamped_read_is_older_than_any_write
FAILED test_charge_limit_rules.py::...::test_write_for_vin_finds_the_api_vehicle
6 failed, 8 passed
```

**Fix 2, scenario replay of 09:17** (`test_plug_presence_scenarios.py`)

The setup: ble_only, a VIN-reading TWC, TeslaMate live. The car departs, the BLE restore fails, BLE is gone for more than 300 s, and there is no remote channel.

Tests:
- `test_2026_10_12_return_plugged_in_keeps_the_policy_limit`: one departing probe reads both BLE reach and a BLE plug. It asserts no restore to 80 is ever sent, car.limit is 50, and saved is (80, 50).
- `test_2026_10_12_arrival_during_a_running_restore_ends_at_the_policy_limit`: the restore is running on the worker when the TWC reads the VIN. It ends with the car at 50 and saved (80, 50).

Unit tests:
- `test_vehicle_presence.py::TestReturnPluggedInWinsOverTheRestore`: no BLE retry and no remote restore in the pass, then arrival on the next pass.
- A fast-charger read still retries the restore.

On the pre-fix code (6c61310), both scenarios fail. The first replays the live log exactly: "Restored ... 80%", then "Charge limit for ...: already at 50%; nothing sent".
```
FAILED test_plug_presence_scenarios.py::test_2026_10_12_return_plugged_in_keeps_the_policy_limit
FAILED test_plug_presence_scenarios.py::test_2026_10_12_arrival_during_a_running_restore_ends_at_the_policy_limit
2 failed
```

With Fix 1 only (1eb1ac9), the running-restore variant passes. These two still fail:
```
FAILED test_vehicle_presence.py::TestReturnPluggedInWinsOverTheRestore::test_a_plugged_in_probe_queues_no_restore_and_the_arrival_follows
FAILED test_plug_presence_scenarios.py::test_2026_10_12_return_plugged_in_keeps_the_policy_limit
  AssertionError: assert '80' not in ['80', '50']
2 failed, 2 passed
```

**Check 3**

Tests:
- `test_twcslave.py::TestChargeRateTarget` (7 tests)
- `test_teslaapi_presence.py::TestChargeRateByVin` (2)

Before the fix:
```
FAILED TestChargeRateTarget::test_named_car_without_an_api_vehicle_gets_its_vin
FAILED TestChargeRateTarget::test_named_car_without_a_teslaapi_module_gets_its_vin
FAILED TestChargeRateTarget::test_the_plug_session_comes_before_the_last_session
FAILED TestChargeRateTarget::test_an_attributed_car_is_named
FAILED TestChargeRateTarget::test_no_car_named_is_a_broadcast
FAILED TestChargeRateByVin::test_a_vin_resolves_to_its_vehicle
FAILED TestChargeRateByVin::test_an_unknown_vin_sends_nothing
7 failed, 2 passed
```

## Deploy merge (8da7e41)

- **Conflicts:**
  - TeslaAPI.py: imports, the `baseURL` class attribute, and `verify=` in setChargeRate.
  - `test_teslaapi_chargerate.py` (add/add).
- **Resolution:** I kept the slot-API form in every hunk (`urllib3` import, no `jwt`, no `baseURL`, `slot.verifyCert`, `fleet_token()` in the test) and took the new ChargeLimitRules import list.
- **Check:** `git diff HEAD` on TeslaAPI.py contains exactly the presence/3 changes. `slotFor("command")` is still in setChargeRate.
- **Formatting:** black ran only on the touched lib files. Each was black-clean before the merge and is clean after.
- **Token check:** a grep of the merge diff's added log lines finds no tokens. The new log lines carry only VINs, limits and exception text.

## Concerns

1. **Fix 1 narrows the restore's live read.**
   - What changes: when our write is newer than telemetry's stamp, a restore now trusts the written limit instead of doing a BLE or API read.
   - The risk: if the user sets a limit by hand within TeslaMate's lag after our apply, the restore overrides it.
   - This is the brief's rule, and the code already trusts telemetry that equals our own limit in the same way.
2. **The write records and read stamps are in memory only.** They live on the CarApiVehicle objects, so a restart or a vehicle-list reload loses them. Within seconds of a restart, a stale read could again win.
3. **A changed replay still counts as new.** The telemetry stamp is set only when the value changes. A retained replay whose value differs from the current attribute (for example, after a live read overwrote it) still counts as a new read. This exposure existed before and is not widened.
4. **`pluggedHere` covers only this pass's probe.**
   - A plug observation that arrives from another path during the pass can still race a sweep restore.
   - A pending restore is cancelled by the arrival.
   - A running restore is made safe by Fix 1.
5. **Check 3 changes which car gets the rate in one case.** `_chargeRateVehicle` now prefers the plug session's car (plugVIN or attribution) over `lastVIN`. Before, `lastVIN` won whenever currentVIN was empty. I think this is more correct, but it is a behaviour change.
6. **Advisor review.** The advisor reviewed the final state (the three branch tips, the merge resolution and the suite counts) and found no blockers. Its first call, earlier in the session, timed out.
7. **No deploy was done.** The box was not touched and commandPolicy is unchanged; the deploy is left for after review.
