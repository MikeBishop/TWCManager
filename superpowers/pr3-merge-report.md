# PR 3 (two token slots) merge onto updated PR 2 branches

## Main line: `fix/owner-api-refresh` (ab73f02) into `feat/token-slots` (8017385)

Merge commit: **f83237b** (worktree `scratchpad/wt-slots`, not pushed).

### Textual conflicts
- `CHANGELOG.md`: upstream reorganised v1.4.0 into Features / Architecture / Bugfixes at the top. Resolution: took upstream's layout verbatim (including its Architecture line "Remove Tesla Owner API login flow ... Owner API tokens used read-only", which PR 3 had not changed). Added PR 3's "Keep an Owner API token and a Fleet API token at once ..." entry as the last Features item.
- `lib/TWCManager/Vehicle/TeslaAPI.py`, `car_api_available`: PR 3 had inlined a slot-based vehicle-list fetch and dedented the wake loop. Upstream (#671) moved the fetch into `loadVehicleList()`.

### How `loadVehicleList` was resolved
I kept upstream's structure: `vehicleListLock` (an RLock), the early `return True` when vehicles are already known, the 30 s timeout, and the `True`/`False` return. PR 3's slot logic now runs inside it:
- `slot = self.slotFor("read")`. If it is None, no request is made and the method returns False.
- URL is `self.vehicleListURL(slot)`, which gives Owner `/products`. The request uses `Authorization: Bearer slot.accessToken` and `verify=slot.verifyCert`.
- 401/403/410/412 go to `self.slotRequestFailed(slot, req)` and the method returns False. It does not retry, even when `slotRequestFailed` refreshed the slot, and it records no `carApiLastErrorTime`. These are PR 3's list-path semantics.
- Other failures keep the existing bookkeeping: an unparseable or missing `count` calls `updateCarApiLastErrorTime()` and returns False, and success calls `resetCarApiLastErrorTime()`. `req = None` is set before the try.
- `car_api_available` keeps PR 3's order: `refreshTokenIfNeeded()`, then the `slotFor("read")` gate with the reason log, then `if self.getVehicleCount() < 1 and not self.loadVehicleList(): return False`. After that comes PR 3's dedented wake loop, unchanged.
- Dedent check: I compared base's wake loop, dedented by 4, with PR 3's. The only differences are a black re-wrap and PR 3's intended tail change, which drops the `empty carApiBearerToken '<token>'` log text and the token check. No statement moved between branches. Upstream did not touch the wake loop; its only TeslaAPI.py change was `loadVehicleList` + `RLock` import.

### Other call sites and ports
- `loadVehicleList` callers: `TeslaAPI.car_api_available` and `Telemetry.updateVehicles` (#671; called on the policy/retry path with `loadList=True`). Telemetry needs no change, because the slot gating sits inside `loadVehicleList`. Note: Telemetry calls it without `refreshTokenIfNeeded()` first. A pasted or login token that has expired but can be refreshed is still `usable` (`empty()` checks expiry only for synced slots), so that path makes one request. It gets a 401 "expired", `slotRequestFailed` refreshes the slot, and the call returns False. The next call succeeds. This matches PR 3's no-retry list semantics, and upstream had the same gap.
- I grepped the upstream changes in lib (#668 VehicleCommandQueue/TWCMaster/TWCManager/TeslaBLE, #670 Policy, #671 Telemetry). Apart from `loadVehicleList`, none of them use a removed accessor. `TWCManager.py`'s periodic `carapi.refreshTokenIfNeeded()` still exists in PR 3. The auto-merged `TWCMaster.py` hunks (VehicleCommandQueue, `queue_vehicle_command`) do not touch the slot load/save code.
- `tests/unit/test_teslaapi_vehiclelist.py` (new upstream test) was ported. It keeps its Mock master, so the token goes in via `api.fleetSlot.setTokens(fleet_token())`. `storeToken` would refuse it because a Mock's `tokenSyncEnabled()` is truthy. `test_no_token_makes_no_call` now uses `fleetSlot.clear()`, and the `no_threads` fixture is used where vehicles are added. I added two tests:
  - `test_lists_from_owner_products_when_both_slots_present`: covers the direct (Telemetry) path, which hits `/products` with the Owner token and never the Fleet `/vehicles`.
  - `test_refused_list_pauses_slot_without_error_or_retry`: a 412 makes one call, keeps the token, pauses reads and records no error time.
- `tests/unit/test_teslaapi_request_errors.py`: upstream (#682) added `api.baseURL = ...` to the fixture. I dropped it, because the slot supplies the base URL and that attribute no longer exists.

### Verification
```
$PY -m pytest tests/unit -q
======================== 762 passed, 1 warning in 4.61s ========================
```
I ran it again after the commit and got 762 passed. The removed-accessor grep printed nothing (exit 1). It covered `getCarApiBearerToken|getCarApiBaseURL|setCarApiBearerToken|apiRefresh|SYNCED_TOKEN_EXPIRY|readOnlyRefusalLogged|applySyncedTokens|pasteAccessToken|clearCarApiBearerToken|get/setCarApiRefreshToken|get/setCarApiTokenExpireTime|restoreCarApiTokenExpireTime|applyTokenClassification|refreshTokenIsOwner`, `.carApiBearerToken/.carApiRefreshToken/.carApiTokenExpireTime` attributes, `(api|self|carapi|vehicle|teslaapi).(baseURL|verifyCert)` and `.refreshToken(` across lib and tests. TeslaTokenSlot.py was excluded because its `self.baseURL` is the slot's own. Settings-key strings such as `"carApiBearerToken"` are legitimate and were excluded.
I ran black on TeslaAPI.py, test_teslaapi_vehiclelist.py and test_teslaapi_request_errors.py; it left them unchanged. No new log line includes a token: the list path logs only the URL and `str(req)`.

## 1.3.4 line: `port-owner-api-refresh-1.3.4` (bbf18ba) into `port-token-slots-1.3.4` (9ab2271)

Merge commit: **01c4e3f** (worktree `scratchpad/wt-slots-134`, not pushed).

### Conflicts
- Only `TeslaAPI.py` `car_api_available` conflicted. The layout was identical to main's. `CHANGELOG.md` auto-merged cleanly, and PR 3's Features entry plus upstream's new Bugfixes lines are both present.
- Upstream's TeslaAPI.py change (#677) is byte-identical to main's #671 diff: the same `loadVehicleList`, lock and 30 s timeout, called from `car_api_available` and `Telemetry.updateVehicles`.
- I applied the same resolution. The `+/-` lines of the resolved TeslaAPI.py diff against PR 3's head match main's merge exactly (verified with `diff`). The 1.3.4 differences, such as Fleet refresh at `authTokenURL` when `usePKCE()` and the lack of a BLE read path or EVSE layer, are outside this code and were not touched.
- I applied the same test ports: the copied `test_teslaapi_vehiclelist.py` (the helpers exist in 1.3.4's `teslatokens.py`) and the dropped `api.baseURL` line in `test_teslaapi_request_errors.py`. Upstream's other new 1.3.4 code (#676 policy thread, #674 RS485, #677 Telemetry) uses no removed accessor.

### Verification
```
$PY -m pytest tests/unit -q -p no:randomly | grep '^FAILED' | sort > 134-after.txt
wc -l: 62 ; diff 134-base.txt 134-after.txt -> IDENTICAL
======================== 62 failed, 631 passed in 4.13s ========================
PR 3 + touched tests (vehiclelist, token_slots, teslatokenslot, token_migration,
token_paste, request_errors, teslamate_token_sync, teslaapi_refresh): 182 passed
```
None of the 62 failures is a PR 3 test. The three `test_teslapowerwall2_ems` failures are pre-existing release-baseline Getters/Initialization tests. The removed-accessor grep printed nothing, and black left the files unchanged.

## Concerns
- None blocking. As noted above, the Telemetry path can spend one request when a refreshable token has expired (the refresh happens, then the list loads on the next call). This matches upstream's existing behaviour.
- New lock-across-network combination that exists on neither parent: on a 401 "expired" list response, `loadVehicleList` still holds `vehicleListLock` while `slotRequestFailed` → `refreshSlot` → `TeslaTokenSlot.refresh` POSTs to the token endpoint. That POST (`TeslaTokenSlot.py:196`, on both lines) has **no `timeout=`**, so a hung refresh would block every other `loadVehicleList()` caller (car_api_available, Telemetry retry) indefinitely. I did not fix it in the merge, because the refresh paths had no timeout before PR 3 either. Suggested follow-up: add `timeout=30` to the refresh POST.
- Both commits are true merges (f83237b parents 8017385 + ab73f02; 01c4e3f parents 9ab2271 + bbf18ba). There are no follow-up commits.

## Follow-up: Concern 1 fixed (separate commits after each merge)

The fix is commit **fe764ff** on feat/token-slots and **621c532** on port-token-slots-1.3.4. Both carry the message "fix: time out a hung Tesla token refresh".
- `TeslaTokenSlot.refresh` now passes `timeout=REFRESH_TIMEOUT` (30 s, the same as `loadVehicleList`) to the refresh POST. This applies to both slots: the Owner slot uses `session.post` and the Fleet slot uses `requests.post`.
- A timeout is a `RequestException` that leaves `req` as None, so `refresh` returns `"unreachable"` and does not clear the tokens.
- I added two tests to `tests/unit/test_teslatokenslot.py`:
  - `test_refresh_post_has_timeout`: requests_mock's `last_request.timeout == 30`.
  - `test_refresh_timeout_is_unreachable_and_keeps_tokens`: `exc=requests.exceptions.ConnectTimeout` returns "unreachable", and the access and refresh tokens are kept.
- Results:
  - Main: `$PY -m pytest tests/unit -q` gives 764 passed.
  - 1.3.4: the sorted FAILED list (`-p no:randomly`) is 62 entries and IDENTICAL to 134-base.txt. `test_teslatokenslot.py` gives 32 passed.
  - Black was run on both touched files.
