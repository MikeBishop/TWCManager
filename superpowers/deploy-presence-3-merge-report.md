# deploy/presence-3: merge of feat/token-slots (#692)

Worktree: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-plug`
Branch: `deploy/presence-3` (local only, not pushed)

Commits on top of 14ae080 (presence/4-fleet-rate-queue):

- `a8ef9cb` Merge feat/token-slots (#692) into deploy/presence-3 (`--no-ff`, merges fe764ff; parents 14ae080, fe764ff)
- `3b7fdd0` Port the plug-presence code to the Tesla API token slots
- `cce331f` Make the TeslaAPI away-skip and no-fix wake tests discriminate (fix round 1)

Tests: **1331 passed** after fix round 1 (1330 at 3b7fdd0) (`tests/unit`, venv python). presence/4-fleet-rate-queue
alone: 1160; feat/token-slots alone: 764. At the merge commit alone, 1323
collected and 59 failed, all in test_plug_presence_scenarios.py (11),
test_teslaapi_chargerate.py (11) and test_teslaapi_presence.py (37), all from
token setup through removed accessors (`carApiBearerToken`, `baseURL`, the
`readOnly` setter, `getCarApiBaseURL`); 3b7fdd0 fixes them.

Test-ID check: every test node ID collected on presence/4-fleet-rate-queue
and on feat/token-slots is also collected on deploy/presence-3 (`comm -23`
of the sorted `--collect-only` IDs prints nothing for both).

## Conflict resolutions (all in lib/TWCManager/Vehicle/TeslaAPI.py)

Same five hunks as deploy/presence-2 (5b35c15). Cross-checked:
`git diff b7e1623 14ae080` and `git diff 5b35c15 a8ef9cb` on TeslaAPI.py have
the same changed lines, apart from indentation in the wake loop.

1. Imports: kept `ChargeLimitRules` (`decideChargeLimit`, `needsLiveRead`) and
   `chargingStatePlugged` (presence), and `create_urllib3_context` plus
   `TeslaTokenSlot`/`decodeToken` (token slots). Dropped `import jwt`:
   nothing in the merged file uses `jwt.`.
2. Class attributes: dropped `baseURL`, kept `CHARGE_RATE_RESEND_AFTER = 600`.
3. `car_api_available` wake loop (two hunks): the token-slots side's dedented
   loop (`slotFor("read")` gating, `readOnly` property, the `applyLimit` /
   `stopTryingToApplyLimit` skip), plus three presence changes:
   - the `vin=None, vins=None` parameters;
   - the per-VIN and broadcast-candidate skips as the loop's first checks;
   - the atHome gate without the `lat != 10000` exemption. This change landed
     on the presence stack after deploy/presence-2, so it is new here.
4. `setChargeRate` POST: `verify=slot.verifyCert, timeout=10`, on the
   command slot's URL and token. The presence side's int conversion,
   skip-repeat/resend-after-600s and accepted-rate recording auto-merged intact.

Auto-merged regions checked:
- No `checkArrival`, `checkDeparture` or `updateChargeAtHome()` call is left
  in `applyChargeLimit`.
- `car_api_charge` uses `slotFor("command")` for the charge_start/stop POST and
  keeps presence's targeting (`_chargeTargetVINs`/`_chargeTargets`, wake
  `vin`/`vins`).
- The token-slot refresh path, which goes through TeslaTokenSlot with
  `REFRESH_TIMEOUT`, was not touched by the merge.
- CHANGELOG auto-merged with one new line and no duplicate heading.

## Ported call sites (3 in lib, 6 test files)

lib (the 92dae4d cherry-pick applied cleanly to lib):
- `TeslaAPI.vehicleOnlineStates`:
  - `slotFor("read")` and `vehicleListURL(slot)` (with an Owner slot this
    reads `/products`);
  - sends `slot.accessToken` with `verify=slot.verifyCert`;
  - a 401/403/410/412 goes to `slotRequestFailed(slot, req)`.
- `PresenceSources.apiSource`: `api.slotFor("read") is None`.
- `PresenceHandlers.hasRemoteChannel`: `api.slotFor("command") is None`. An
  Owner token alone is no longer a remote channel.

tests:
- From 92dae4d (test_teslaapi_chargerate, test_teslaapi_presence,
  test_presence_sources, test_presence_handlers): applied as they were.
  The one conflict was in test_vehicle_presence.py, in
  `TestDepartAndReturnThroughTheQueue`. The presence stack had already deleted
  that class (it used the AWAY state), so HEAD's version was kept.
- `test_teslaapi_presence.py` (tests added since presence-2):
  - TestChargeTargets and TestWakeOnlyForAHomeCar no longer set `api.baseURL`,
    and their URLs are now `FLEET_NA_URL`;
  - dropped the `getCarApiBaseURL` Mock stubs and the `api.readOnly = False`
    assignment (readOnly is a property; a Fleet token makes it False).
- `test_plug_presence_scenarios.py`:
  - The `World` takes `slots="fleet_command"` (the default) or
    `"owner_read_only"`. It runs `api.storeToken(fleet_token())` or
    `api.storeToken(owner_token())` and asserts that `readOnly` matches,
    replacing the `carApiBearerToken`/`baseURL`/`carApiRefreshToken`/
    `carApiTokenExpireTime`/`readOnly` assignments.
  - `FakeFleet` routes both the Fleet NA URL and the Owner API URL (including
    `/products`), and fails on any other URL. It still records every GET and
    POST.
  - The 16 existing scenarios' assertions are unchanged, and all 16 pass.
- `test_teslable_presence.py::test_policy_wide_apply_skips_departing_on_every_channel`:
  it set `carApiBearerToken` on a real TeslaAPI. It passed only because that
  made the API read-only, so the TeslaAPI leg was a read-only refusal rather
  than the departing skip. It now stores a Fleet token.

New: `TestDeployRegression20261011` (3 tests):
- `test_departing_car_inside_radius_gets_nothing_on_any_channel[fleet_command|owner_read_only]`:
  runs the 2026-10-11 sequence. Over 10 policy cycles plus the Fleet API's
  policy-wide apply there is no `charging-set-limit`, no `set_charge_limit`
  POST, no wake on either channel and no `vehicle_data` GET.
- `test_fleet_fallback_restore_needs_a_command_slot`: with only an Owner slot,
  `hasRemoteChannel` is False. Past the 5-minute BLE-gone mark no `remoteOnly`
  restore is ever queued (every queue `put` is recorded), no POST is sent and
  the saved limit stays held. A mutation check that reverted `hasRemoteChannel`
  to `slotFor("read")` makes this test fail.

Leftover-accessor grep (the brief's command): `.baseURL` is now an attribute
of the slots, so the brief's grep still matches it. With `slot.baseURL`,
`fleetSlot.baseURL`/`ownerSlot.baseURL`, FakeFleet's `baseURLs` and the
settings.html.j2 form field name filtered out, it prints nothing.
`git grep '\.(carApiBearerToken|carApiRefreshToken|carApiTokenExpireTime)\b'`
also prints nothing. Remaining `"carApiBearerToken"` hits are settings-dict
keys, which PR3 still migrates.

Black: TeslaAPI.py, PresenceSources.py and PresenceHandlers.py were all
black-clean before and after. Black was also run on
test_plug_presence_scenarios.py, test_presence_handlers.py,
test_teslaapi_chargerate.py and test_presence_sources.py, which were all
black-clean on presence/4. Two files were not black-clean before and were not
reformatted: test_teslaapi_presence.py and test_teslable_presence.py. Their new
hunks are in black style.

Token-in-log check: `git diff presence/4-fleet-rate-queue -- lib | grep -nE '^\+.*log.*(oken|Bearer)'`
has 8 hits, all from feat/token-slots code that came in with the merge
(comments, "Attempting token refresh", the refresh-error messages). None
interpolates a token. The port commit adds no hits.

## Startup sanity check

Ran `.../scratchpad/sanity-startup.py` on the worktree, with no network and
`requests` patched to fail. The results match deploy/presence-2:
- **Imports:** every module imports except `EMS.SolarEdge` (an environmental
  pymodbus `Endian` problem).
- **Owner slot:** an Owner JWT saved as synced loads as source `synced`, type
  `owner`, refresh `""`, and `needsRefresh()` is False.
- **Slots:** `slotFor("read")` is the Owner slot, `slotFor("command")` is
  None, and `readOnly` is True.
- **Settings:** migrated to the `ownerApi*` keys.
- **Network:** zero calls.

## Things to watch on the box

- **Owner token alone means TeslaAPI is read-only.** If the box has only the
  TeslaMate Owner token (no Fleet token):
  - Fleet `set_charging_amps`, charge-limit commands and wake are refused,
    logged once at INFO.
  - `hasRemoteChannel` is False, so departure restores are never queued to the
    Fleet API. With `commandPolicy: ble_only` this changes nothing, because
    ble_only already rules out the remote channel.
  - Commands go only through TeslaBLE.
  - The new owner_read_only regression test covers this.
- **vehicleOnlineStates with an Owner token reads `/products`.** This is the
  presence API probe for a car that is online. The tests use a fixture modelled
  on a live response; it has not been checked against the live API here. Look
  for "Tesla API is read-only" and any 412/403 from the presence online read in
  the first hour. A 403/412 on that read pauses the Owner slot
  (`slotRequestFailed`), and after that presence API probes return None.
- **Token sync ordering at first boot is untested.** The sanity check covered
  the saved-token path only. On the box, TeslaMate's startup sync runs before
  `loadSettings`, and `restoreSlot` keeps the live-synced token. That ordering
  was not exercised, so check the first boot's "Tesla API token type" log line.
- **The Fleet wake gate follows presence, not the raw location.** The
  `lat != 10000` exemption is gone, but that does not stop a car with no
  location fix from being woken. A car with no fix and no evidence is PRESUMED,
  `atHome` is True, and the Fleet API wakes it when charging needs it
  (`test_presumed_car_with_no_location_fix_is_woken`, cce331f). Only
  DEPARTING or NOT_HOME cars are skipped. The one exception: if
  `presence.isHome` raises, `atHome` falls back to the raw location, which is
  False before the first fix (pre-existing, from presence/4).
- **The charge_start/stop and wake_up POSTs have no timeout.** This is
  token-slots code (`car_api_charge` and `wakeVehicle`,
  `requests.post(url, headers=headers, verify=slot.verifyCert)`) and is
  unchanged here. With a Fleet token, a hung Fleet API could stall that
  background task.
