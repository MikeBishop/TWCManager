# deploy/presence-2: merge of feat/token-slots (#692)

Worktree: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-deploy2`
Branch: `deploy/presence-2` (local only, not pushed)

Commits on top of b7e1623 (presence/5-fleet-rate-queue):

- `5b35c15` Merge feat/token-slots (#692) into deploy/presence-2 (`--no-ff`, merges fe764ff)
- `92dae4d` Port the presence code to the Tesla API token slots

Tests: 1240 passed (`tests/unit`, venv python). At the merge commit alone,
37 tests fail; all of them use removed accessors and are fixed by 92dae4d.

## Conflict resolutions (all in lib/TWCManager/Vehicle/TeslaAPI.py)

1. Imports: kept `ChargeLimitRules` (presence) and `create_urllib3_context` plus
   `TeslaTokenSlot` (token slots). The `jwt` import was dropped, not kept:
   the token-slots side removed it because `decodeToken` moved to
   TeslaTokenSlot, and nothing in the merged TeslaAPI.py uses `jwt.`.
2. Class attributes: dropped `baseURL`, kept `CHARGE_RATE_RESEND_AFTER = 600`.
3. `car_api_available` wake loop: the token-slots side's dedented loop (slot
   gating via `slotFor("read")`, `readOnly` property, the `applyLimit` /
   `stopTryingToApplyLimit` skip) with the presence side's `vin=None`
   parameter and its "a per-VIN command must not wake any other vehicle"
   skip as the loop's first check. The presence side changed nothing else
   in this function.
4. `setChargeRate` POST: `verify=slot.verifyCert, timeout=10`, on the command
   slot's URL and token. The presence side's int conversion,
   skip-repeat/resend-after-600s and accepted-rate recording auto-merged and
   are intact.

## Ported call sites (3 in lib, 5 test files)

lib:
- `TeslaAPI.vehicleOnlineStates`: was `getCarApiBaseURL()`/`getCarApiBearerToken()`/`self.verifyCert`.
  Now `slotFor("read")`, `vehicleListURL(slot)` (Owner slot -> `/products`, which
  also carries each vehicle's `state`), `slot.accessToken`, `slot.verifyCert`;
  401/403/410/412 -> `slotRequestFailed(slot, req)` with no retry, as `loadVehicleList` does.
- `PresenceSources.apiSource`: `not api.getCarApiBearerToken()` -> `api.slotFor("read") is None`.
- `PresenceHandlers.hasRemoteChannel`: `not api.getCarApiBearerToken()` -> `api.slotFor("command") is None`.
  This changes behaviour: an Owner API token alone is no longer a remote channel
  (it cannot send commands; PR3 would refuse the restore anyway).

tests:
- `test_teslaapi_chargerate.py`: `carApiBearerToken`/`baseURL` -> `api.storeToken(fleet_token())`.
- `test_teslaapi_presence.py`: `make_api` stores a Fleet token; dropped `api.baseURL`
  and `carapi.getCarApiBaseURL` stubs; the online-states test asserts the Fleet NA URL
  and the slot's token; no-token test uses `fleetSlot.clear()`. New: Owner slot reads
  `/products`; a 403 pauses the slot.
- `test_presence_sources.py`: Mock API stubs `slotFor` instead of `getCarApiBearerToken`.
- `test_presence_handlers.py`: the no-token/raises tests stub `slotFor`; new
  parametrized test with a real TeslaAPI: Owner -> False, Fleet -> True, none -> False.
- `test_vehicle_presence.py`: Mock API stubs `slotFor`.

Removed-accessor grep (method names, `.carApiBearerToken`/`.carApiRefreshToken`/
`.carApiTokenExpireTime` attributes, `self|api|carapi|...` `.baseURL`/`.verifyCert`
outside TeslaTokenSlot.py) prints nothing in lib/ or tests/. Remaining
`"carApiBearerToken"` hits are settings-dict keys, which PR3 still uses.

Black: run on TeslaAPI.py, PresenceSources.py, PresenceHandlers.py,
test_presence_handlers.py, test_teslaapi_chargerate.py, test_vehicle_presence.py
(all black-clean before). test_presence_sources.py and test_teslaapi_presence.py
were not black-clean on the presence branch, so they were not reformatted; the
new hunks are black style.

No new log line includes a token.

## Startup sanity check

Script: `.../scratchpad/sanity-startup.py <worktree>` (no network; requests patched to fail).

- Imported every module in `TWCManager.py`'s `modules_available` plus TWCMaster,
  VehiclePresence, PresenceSources, PresenceHandlers, VehicleCommandQueue,
  ChargeLimitRules, TeslaTokenSlot. Only failure: `EMS.SolarEdge` (venv pymodbus
  has no `Endian`; untouched by either branch, environmental).
- Constructed TWCMaster with `vehicle.TeslaMate.syncTokens: true`, registered a real
  TeslaAPI, `settings.json` with an Owner API JWT in `carApiBearerToken`, a TeslaMate
  refresh token in `carApiRefreshToken`, `carApiTokenExpireTime = 99999**3`; ran
  `loadSettings()` and `refreshTokenIfNeeded()`:
  - Owner slot: source `synced`, type `owner`, refresh token `""`, `needsRefresh()` False.
  - Fleet slot empty; `slotFor("read")` is the Owner slot; `slotFor("command")` None; `readOnly` True.
  - Settings migrated: `carApi*` cleared, `ownerApiBearerToken` set, `ownerApiRefreshToken ""`,
    `ownerApiTokenSource "synced"`.
  - Zero network calls.

## Concerns / things to watch on the box

- If the box has only the TeslaMate Owner token (no Fleet token), TeslaAPI is
  read-only: Fleet `set_charging_amps`, charge-limit commands and wake are
  refused (logged once at INFO), and `hasRemoteChannel` is False, so departure
  restores are not queued to the Fleet API. Commands then go only through TeslaBLE.
  This is PR3's intended behaviour, but it differs from the presence branch alone.
- `vehicleOnlineStates` with an Owner token now reads `/products` (the Owner API
  answers 412 on `/vehicles`). PR3's `/products` fixture (test_teslaapi_owner_read.py,
  modelled on a live response) carries `"state"` on vehicle entries, and energy-site
  entries have no `vin` so they are skipped. Not checked against the live API here.
- The sanity check covered the saved-token path only. On the box, TeslaMate's startup
  sync runs before `loadSettings` and `restoreSlot` keeps the live-synced token over
  a saved synced one; that ordering was not exercised, so glance at the first boot's
  "Tesla API token type" log line.

Verified after commit: 5b35c15 has two parents (b7e1623, fe764ff); black --check clean
on the six reformatted files; working tree clean.
