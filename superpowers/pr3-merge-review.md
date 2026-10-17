# PR 3 merge review: f83237b + fe764ff (feat/token-slots), 01c4e3f + 621c532 (1.3.4)

Verdict: **Approve.** The conflict resolution is faithful to both sides. No Critical or Important findings. Four Minor items follow.

Paths below are relative to `scratchpad/wt-slots` at fe764ff.

## What was verified

- **Nothing dropped.** For every file in `git diff ab73f02 fe764ff`, I compared the +/- lines with PR 3's own diff (`b6645fe..8017385`). All files except four match exactly: TeslaAPI.py, test_teslaapi_vehiclelist.py, test_teslaapi_request_errors.py and the fe764ff files. In TeslaAPI.py the only real difference is where the list fetch lives. The rest is diff-alignment noise in the dedented wake loop. The wake loop from `# Wake cars if needed` to `car_api_charge` is byte-identical to 8017385 on both lines. ab73f02 contains origin/main, and every file PR 3 does not touch equals PR 2's head. So no upstream hunk from #668, #670, #671 or #679 was lost.
- **`loadVehicleList` (TeslaAPI.py:308-367).** This is upstream's structure: `vehicleListLock`, the early `return True`, `timeout=30`, `req = None`, and the True/False return. It uses `slotFor("read")` (None means no request and False), `vehicleListURL(slot)` (Owner gives /products), `slot.accessToken` and `slot.verifyCert`. A 401/403/410/412 goes to `slotRequestFailed` and returns False, with no retry and no `carApiLastErrorTime`. Other failures (timeout, connection error, 5xx/429 with no `count`, bad JSON) fall through to the KeyError/TypeError branch, which calls `updateCarApiLastErrorTime()`. That is the same as upstream and the same as PR 3's old inline code. Apart from the slot changes, the body equals PR 3's old inline fetch plus upstream's timeout. No log line includes a token: only the URL, `str(req)` and the response body are logged.
- **`car_api_available`.** It keeps PR 3's order: retry gate, `refreshTokenIfNeeded()`, the `slotFor("read")` gate with its reason log, then `getVehicleCount() < 1 and not loadVehicleList()`.
- **Callers.** There are two: `car_api_available` (TeslaAPI.py:420) and `Telemetry.updateVehicles` (Telemetry.py:229-230, gated on `not getCarApiRetryRemaining()`). If no slot is usable, Telemetry gets False without a request and reschedules its retry. If a synced slot has expired, `empty()` makes it unusable, so no request is sent. HomeAssistant's `car_api_available` is its own method. #668 (VehicleCommandQueue, TeslaBLE) and #670 (Policy) do not call it, and they touch no token or base-URL state.
- **Locks.** The lock is held across `slotRequestFailed` and, for a refresh, across `refreshSlot`, `slot.refresh()` and `master.queue_background_task`. `queue_background_task` takes `backgroundTasksLock` only briefly (TWCMaster.py:1283-1297), and nothing holds `backgroundTasksLock` while it calls into TeslaAPI. `refreshTokenIfNeeded` and `refreshSlot` never take `vehicleListLock`. VehicleCommandQueue has no lock. Policy's `_evalLock` and TeslaBLE's `_bleLock` are not taken under `vehicleListLock`, nor the reverse. **No lock-order cycle, so no deadlock.** The lock is an RLock, so re-entry on the same thread is safe.
- **Removed accessors.** I grepped lib for `Bearer|baseURL|verifyCert|getCarApi*Token|carApiBearerToken|apiRefresh|readOnly`, excluding TeslaAPI.py and TeslaTokenSlot.py. The hits are settings keys (TWCMaster save/load, HTTPControl), Powerwall2's slot-based code, and `readOnly` property users (VehiclePriority, TeslaAPIEVSE). These were all pre-existing in PR 3. No upstream code needed porting other than `loadVehicleList`.
- **1.3.4.** `loadVehicleList` through the end of `car_api_available`'s gate, `slotRequestFailed`, `TeslaTokenSlot.refresh` and test_teslaapi_vehiclelist.py are all identical to main. The diff-of-diffs shows the same four files. The wake loop equals 9ab2271's.
- **Tests.** Main gives `764 passed`. On 1.3.4 the vehiclelist, tokenslot, token_slots and request_errors files give `68 passed`. The ported tests assert the request target, the Authorization header, the call counts, that the token is kept, that the slot is paused and that no error time is recorded. fe764ff's tests check `last_request.timeout == 30`, and that a ConnectTimeout returns "unreachable" and keeps both tokens. Both are real assertions.

## Critical

None.

## Important

None.

## Minor

**M1. The list path's 401 handling is untested, so the "no retry" claim is never exercised.**
Location: tests/unit/test_teslaapi_vehiclelist.py:72 and TeslaAPI.py:330-335.
`test_refused_list_pauses_slot_without_error_or_retry` uses a 412, and a 412 never retries anywhere, so the "no retry" half of its name is vacuous. The list-path behaviour that differs from `get_car_api` is this: a 401 "expired" on a refreshable slot refreshes once, does not re-GET, and returns False. No test covers it, and none covers a non-expired 401 clearing the slot when `loadVehicleList` is called directly, which is Telemetry's path. Scenario: someone later "fixes" the list path to retry after a refresh, or drops the 401 from the status tuple so it falls into the KeyError branch and sets API error backoff. Nothing fails. Suggested test: mock the list with 401 `"token expired"` and a successful refresh POST, then assert the list call_count is 1, the refresh call_count is 1, the result is False, the token has changed and `carApiLastErrorTime == 0`.

**M2. The worst-case hold on `vehicleListLock` is now about 60 s; upstream's was 30 s.**
Location: TeslaAPI.py:314 and 324-335, TeslaTokenSlot.py:196-199.
A list GET that hangs until its timeout holds the lock for up to 30 s. A 401 "expired" followed by a hung refresh holds it for another 30 s. Scenario: Telemetry's `threading.Timer` retry is inside `loadVehicleList` on a refresh while the vehicle-command worker or background thread enters `car_api_available` with no vehicles. That worker waits up to about 60 s before it can return. This is bounded and has no correctness impact. fe764ff turned "forever" into 60 s. It needs only a note. If it matters, release the lock before refreshing: have `loadVehicleList` return a "refresh needed" result and refresh outside the `with`.

**M3. `TeslaTokenSlot.refresh` is not serialised, and the merge adds another thread that can trigger it.**
Location: Telemetry.py:229-230 → TeslaAPI.py:333 → slotRequestFailed:247 → TeslaTokenSlot.refresh.
`TeslaTokenSlot.refresh` takes no lock, and neither does `refreshSlot`. Before the merge, a refresh could already start from the main loop (TWCManager.py:990, every 5 min), from `car_api_available` on the background or worker thread, and from Powerwall2. With the merge, Telemetry's timer thread can also start one through a 401 "expired" on the list. Scenario: two threads POST the same refresh token at once. If Tesla treats the refresh token as single-use, the slower POST gets 401, `refresh` clears the slot (TeslaTokenSlot.py:211-216), and the user has to re-supply tokens. The window is narrow. It needs the access token to be rejected as expired while still outside `needsRefresh`'s 1 h margin (REFRESH_MARGIN, TeslaTokenSlot.py:26), at the same moment another thread refreshes. The race existed in PR 3 before the merge, so it is not a merge regression. Fix it as a follow-up if at all: a per-slot lock in `refresh`, and after acquiring it, skip the POST if the refresh token has already changed.

**M4. Telemetry now regularly reaches a slot failure that changes no state.**
Location: Telemetry.py:29 and 229-230 → TeslaAPI.py:243-251 → refreshSlot:224 → TeslaTokenSlot.refresh:178-183.
Setup: a pasted or login Fleet token that has expired. It is still `usable`, because `empty()` checks expiry only for a synced slot. It has a refresh token, but `teslaApiClientID` is not set. (The Owner slot always has client ID "ownerapi", so only the Fleet slot can be in this state.) On each Telemetry retry, the list GET returns 401 "expired" and `refresh()` logs an ERROR and returns "not_configured". `refreshSlot` ignores that result: it records no error time and does not clear or pause the slot. `loadVehicleList` returns False, and `scheduleUnmappedRetry` repeats the cycle. The cost is one Tesla GET plus one ERROR log every `unmappedRetrySecs` (300 s), with no end. `car_api_available` already did the same thing in PR 3 before the merge, so this is not a merge regression. The merge only adds a periodic caller that skips `refreshTokenIfNeeded`. The rate is low and the log says what to fix. Possible follow-up: have `slotRequestFailed` pause the slot when the refresh returns "not_configured".

## Notes (no action)

- 1.3.4 check: I compared the TeslaAPI.py diff-of-diffs (621c532 against 9ab2271's own diff) as sorted sets. Every difference is the inline list fetch moving into `loadVehicleList`. No other function differs. HomeAssistant.py:501 defines its own `car_api_available`.

- When Telemetry calls `loadVehicleList` without calling `refreshTokenIfNeeded()` first, it can spend one request on an expired pasted or login token. That request refreshes the token, and the next call succeeds. This matches the merger's report and the spec's list-path semantics.
- The merger's report is accurate on every point I checked.
