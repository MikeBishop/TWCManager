# Backports report: RS485 import, #669, #670, #671 to release/1.3.3 and release/1.3.4

Nothing pushed. Every branch is local to this worktree and has no upstream set.

## Branch layout and why

The maintainer's existing ports (`port-ble-stopasking-1.3.x`, `port-fleet-oauth-1.3.x`,
`port-owner-api-removal-1.3.x`) each branch off **release/1.3.4** and are PR'd into 1.3.4.
None of them is an ancestor of release/1.3.3. Nathan carries fixes to 1.3.3 as separate
commits (same subjects, different SHAs, no `-x` lines). A single branch can't serve both
lines because 1.3.3 diverged from 1.3.4, and #671 needs different code on each line.
So I followed the brief's fallback and made one branch per fix per line:
`port-<topic>-1.3.3` / `port-<topic>-1.3.4`. Each `-1.3.4` branch is what Nathan would
call `port-<topic>-1.3.x`. For RS485, #669 and #670 the 1.3.3 and 1.3.4 branches carry
the same change (same diff lines), so the controller can rename or collapse them to fit
his style.

The branches are independent. Merging #669 and #670 together gives a trivial conflict in
tests/unit/test_twcslave.py, where both append a test class at the end of the file. Keep
both. The same conflict happens on main. I checked all four ports merged together on each
line: no new failures (1.3.3: 62 failed / 392 passed; 1.3.4: 62 failed / 401 passed;
the 62 are the baseline failures).

## Baseline (before any change)

Python 3.12.3 venv. No dependencies were missing on either release branch.

| Base | Result |
|---|---|
| origin/main | 451 passed |
| origin/release/1.3.3 | 62 failed, 363 passed |
| origin/release/1.3.4 | 62 failed, 373 passed |

Both release lines fail the same 62 tests before any change: test_dummy 4, test_fronius 1,
test_kostal 1, test_mqttcontrol 2, test_protocol 1, test_remaining_ems_modules 11,
test_teslapowerwall2 3, test_twcmanager 12, test_twcmaster 16, test_vehicle_priority 3,
test_victron 8. Causes include `releaseModule` assertion mismatches, "Port must be
configured" SerialException and `TWCMaster has no attribute chargeNow`. These are stale
tests on the release lines. None of my changes touches them. For each branch below,
"no new failures" means the set of failing test IDs matches the baseline exactly.

## Branches

| Branch | Base | Commits | Tests (full unit suite) | Conflicts / resolution | Left out / why |
|---|---|---|---|---|---|
| `fix/rs485-serial-import` | origin/main | 2a9946b "Import serial at module level in the RS485 interface" (new) | 455 passed. The 4 tests in test_rs485.py all fail on main's RS485.py and pass with the fix. | None. RS485.py and test_rs485.py are taken from 2c38506. | SIGTERM shutdown flag (TWCManager.py, test_sigterm_shutdown.py) left out; it stays in #668. I added `read()` and `send()` tests to test_rs485.py so all three `except serial.` sites (getBufferLen, read, send) are covered. |
| `port-rs485-serial-import-1.3.3` | release/1.3.3 | b7c0ac7 (`-x` from 2a9946b, amended) | 62F/365P, no new failures. Both new tests fail without the fix. | No textual conflict. Test file adapted (see next column). | On 1.3.x only `read()` has an `except serial.serialutil.SerialException`. getBufferLen/send have no handler there; that came with #461 on main. I did not backport #461. Tests target `read()`: a SerialException triggers reconnect, and a KeyboardInterrupt in `read()` reaches the caller. |
| `port-rs485-serial-import-1.3.4` | release/1.3.4 | 52c3daa (same as above) | 62F/375P, no new failures. Both new tests fail without the fix. | Same as 1.3.3. | Same as 1.3.3. |
| `port-resend-amps-starting-1.3.3` | release/1.3.3 | 39be89f (`-x` 78bd9c2) | 62F/368P, no new failures. With TWCSlave.py reverted, the 5 new tests fail on AttributeError (`_amps_heartbeat` missing; same on main). `test_state_08_resends_even_when_max_matches` is the one that checks the new behaviour. The test file matches main's. | Clean | none |
| `port-resend-amps-starting-1.3.4` | release/1.3.4 | 9a9cd3d (`-x` 78bd9c2) | 62F/378P, no new failures. Same caveat as 1.3.3: the 5 tests fail on AttributeError without the fix. | Clean | none |
| `port-teslamate-vehicle-mapping-1.3.3` | release/1.3.3 | 64577a0 (`-x` b3bff0e, conflict resolved; backport notes in the message) | 62F/371P, no new failures. With lib/ reverted, all 8 new tests fail. | TeslaAPI.py, 3 hunks. (1) Imports: kept 1.3.3's (HTTPAdapter, ssl, urllib3); only `Thread` changed to `RLock, Thread`; `secrets` not added. (2) Added `loadVehicleList` using **`self.session.get(..., timeout=30)`**, with the **owner-api `vehicles`→`products` rewrite moved inside it**. Kept 1.3.3's `car_api_available(self, email=None, password=None, charge=None, applyLimit=None)` signature. Did **not** add `refreshTokenIfNeeded` (it only exists on 1.3.4). (3) The inline list GET is replaced by `if self.getVehicleCount() < 1 and not self.loadVehicleList(): return False`, after the token-refresh / password-login block that ends `return ret`. test_teslaapi_vehiclelist.py now patches `api.session.get`. The original patched `requests.get`, which doesn't intercept the session. Added a products-shaped test. | none |
| `port-teslamate-vehicle-mapping-1.3.4` | release/1.3.4 | 7a3839b (`-x` b3bff0e) | 62F/380P, no new failures. With lib/ reverted, all 7 new tests fail. | Clean. 1.3.4's vehicle-list GET is the same as main's (`requests.get`, Fleet URL). | none |
| `port-policy-evaluation-thread-1.3.3` | release/1.3.3 | 7fc0851, 7e9f8b8, 47fdd6e, cd6abb2, cd21419 (`-x` 5fcfe06..a4d9feb) | 62F/377P, no new failures. With lib/ reverted, test_policy + test_twcslave give 16 failed + 10 errors. | Clean. The +/- lines are identical to origin/main...fix/policy-evaluation-thread. | none (see "#670 port" below) |
| `port-policy-evaluation-thread-1.3.4` | release/1.3.4 | 16e3f8a, 9762c86, 3d9a7e1, e08db82, 24e071d (`-x` same) | 62F/387P, no new failures. With lib/ reverted, 16 failed + 10 errors. | Clean. Diff identical to main's. | none |

## #671 on 1.3.3: the coordinator's checks

1. **session.get**: done. `loadVehicleList` calls `self.session.get(url, headers=..., verify=self.verifyCert, timeout=30)`. The new test patches `api.session.get` and asserts it is called.
2. **owner-api → products rewrite**: moved into `loadVehicleList`. Test `test_owner_api_lists_products_and_skips_energy_sites` sets `baseURL=https://owner-api.teslamotors.com/api/1/vehicles` and asserts the GET goes to `.../api/1/products`.
3. **Pre-GET block ending `return ret`**: left where it is, unchanged. The `loadVehicleList()` call comes after it, inside `if self.getCarApiBearerToken() != "":`, as before.
4. **products response shape**: 1.3.3's `addVehicle` is `if "vin" in json: append(CarApiVehicle(...))`, so energy products are skipped. This shape assumption is not new: 1.3.3's existing `car_api_available` already iterated `apiResponseDict["count"]` / `["response"][i]` over the products URL. The backport moves that logic; it doesn't add a new assumption. The new test feeds `{"count": 2, "response": [vehicle-with-vin, energy-site]}` and asserts exactly one vehicle (VIN1) is added and the call returns True.
5. **Telemetry.py identical on both release branches**: confirmed (`diff` is empty). The Telemetry hunk applied cleanly on both. Telemetry.py already imports `threading` on both lines, which the new retry Timer needs.
6. **getCarApiRetryRemaining**: present on 1.3.3 (line 1091) as `getCarApiRetryRemaining(self, vehicle=None)`, the same signature as 1.3.4/main. Telemetry calls it with no arguments, which is fine.

Also: in 1.3.3's old inline code, `req` was never initialised, so `if req:` in the except path could raise NameError. The new `loadVehicleList` initialises `req = None`, which fixes that as a side effect.

## #670 port (policy evaluation thread)

The brief said to stop if the main loop differs materially. It doesn't:
- Both release lines have the same structure as main. `setChargingPerPolicy()` has exactly
  one main-loop caller (TWCSlave heartbeat). `applyPolicyImmediately()` callers are in
  HTTPControl/MQTTControl. The startup anchor (`backgroundTasksThread.start()` followed
  by the sunrise task) is there, as are the `fakeMaster` config key, the
  `except KeyboardInterrupt: break` exit and the `saveSettings` drain after the loop.
- The concurrency infrastructure matches main: the same locks (TWCMaster
  backgroundTasksLock, HASS/MQTT status locks, HomeAssistant `_rest_lock`). Main has no
  extra command worker or vehicle lock that the policy thread relies on (the vehicle
  command worker is on fix/vehicle-presence, not main). So the policy thread runs with the
  same threading assumptions it has on main.
- All 5 commits cherry-picked cleanly, and the resulting diff lines are identical to main's.

Caveat (same as on main): the start()/stop() wiring in TWCManager.py is module-level
script code. Unit tests don't cover it; only Policy/TWCSlave behaviour is tested. It
should get a smoke run on hardware before release.

## Other notes

- Cherry-picks keep original authorship (Mike Bishop) and their original trailers.
  New or amended commits (2a9946b, both RS485 ports, the 1.3.3 #671 resolution note)
  carry `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 2c38506 on origin/ble-command-worker (#668) still carries the RS485 import. Once
  fix/rs485-serial-import lands, #668 needs a rebase to drop that hunk and test_rs485.py.
