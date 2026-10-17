# TeslaMate token sync: independent review

Date: 2026-10-10. Reviewed: fix/teslamate-token-sync (538f8c7, 3e11e31, 04bb080), port-teslamate-token-sync-1.3.4 (e5e08ca, 9644c72, dfc4e7a), port-teslamate-token-sync-1.3.3 (3c220d6).
Authority: .superpowers/specs/2026-10-10-teslamate-token-sync-design.md.

## Verdicts

| Branch | Verdict |
|---|---|
| fix/teslamate-token-sync | ready with fixes (M1) |
| port-teslamate-token-sync-1.3.4 | ready with fixes (M1) |
| port-teslamate-token-sync-1.3.3 | ready with fixes (M1) |

M1 is a small change in the line this PR already touches, and it applies the same way on all three branches. Nothing else blocks.

## Test evidence

- main: 496 passed (baseline origin/main 451 passed).
- 1.3.4: 62 failed, 416 passed. The failure set is identical to origin/release/1.3.4 (62 failed, 373 passed).
- 1.3.3: 62 failed, 371 passed. The failure set is identical to origin/release/1.3.3 (62 failed, 363 passed).
- The new tests were run with `lib/` reverted to the base branch:
  - main: 36 of 45 fail.
  - 1.3.4: 35 of 43 fail.
  - 1.3.3: 6 of 8 sync tests fail.
  - The tests that still pass are regression guards: an ordinary saved expiry, sentinel kept while sync is on, the ou_code region, region lists, a Fleet token not refused, and VehiclePriority reads/writable.
- Mocking is appropriate:
  - The real TeslaAPI, TeslaMateVehicle.doSyncTokens, TWCMaster.loadSettings and VehiclePriority are exercised.
  - Only psycopg2, HTTP (requests_mock ANY) and threads are faked.
  - VehiclePriority tests use Mock modules, but VehiclePriority itself is real.
- black: the touched files on main are clean. On the ports, the only diffs are the documented pre-existing lines.
- The TeslaAPI.py diff is byte-identical between main and 1.3.4.

## Findings

### Medium

- **M1** (all three branches): `TWCMaster.loadSettings` overwrites the startup sync while sync is on.
  - Locations: main TWCMaster.py:1100-1103, 1.3.4 :943-946, 1.3.3 :942-945.
  - Load order is TeslaAPI, then TeslaMateVehicle (startup sync, then registration), then `loadSettings` (TWCManager.py:696-796). By then sync is on, so:
    - `setCarApiRefreshToken(saved)` stores the stale refresh token unconditionally;
    - `restoreCarApiTokenExpireTime(saved)` stores any non-sentinel saved value over the sentinel.
  - Reproduced with a probe against main. The saved settings were written by pre-fix code, so the saved expiry is the old token's exp. After `loadSettings`: the bearer is the fresh synced token, the refresh token is "old-refresh", the expiry is not the sentinel, and the expiry is in the past.
  - Every existing TeslaMate-sync user hits this on the first boot after the upgrade.
  - No refresh fires, because every refresh path is gated on `tokenSyncEnabled()`. But `TeslaPowerwall2.getStormWatch` requires `now < expiry`, so cloud Storm Watch is dark, and the UI shows an expired token, until the next hourly resync.
  - The plan listed this as pre-existing and out of scope. But this PR is what makes the sentinel persist, it rewrote this exact line, and the brief asks for the restore to be correct "in both sync states".
  - Fix: in `loadSettings`, skip the bearer, refresh and expiry restores while `tokenSyncEnabled()`. TWCMaster's own comment says that with sync on "we don't use our own settings". Alternatively, have `restoreCarApiTokenExpireTime` ignore the saved value when sync is on.
  - Add a test: sync on, saved non-sentinel expiry, after a startup sync, and the sentinel and the synced refresh token survive.

### Low

- **L1** (main/1.3.4 TeslaAPI.py:1284-1286 / :1250-1252; 1.3.3 TeslaAPI.py:1204-1206): the login token exchange (`fleetTokenExchange` / 1.3.3 code exchange) is only partly refused while sync is on.
  - The bearer is refused, but the refresh token is stored, the sentinel is overwritten with now+expires_in, and the exchange returns "success".
  - The login form is hidden while sync is on, but `/teslaAccount/login` and `/callback` can still be reached by URL.
  - Pre-existing. It undercuts "hand-entered tokens are refused".
- **L2** (main HTTPControl.py:1733; same on the ports): a refresh token entered in Settings is stored while sync is on. Only the refresh is gated, not the storage. Pre-existing.
- **L3** (main TeslaAPI.py:1347, 1.3.4 :1313): `classifyToken` raises on a token with an explicit `"aud": null` or a numeric aud.
  - `decoded.get("aud", [])` returns None, and the comprehension raises TypeError out of `setCarApiBearerToken`.
  - Fix: use `decoded.get("aud") or []` and treat a non-list as `[aud]`.

### Informational

- **I1** (1.3.3 TeslaAPI.py:1240): 1.3.3 still classifies only the first token (`if not self.baseURL`).
  - With `teslaProxy` set, or with a Fleet baseURL held before sync was turned on, a synced Owner token goes to the wrong host until restart.
  - This was scoped out by the spec ("change 1 only"). Mention it in the 1.3.3 PR text.
- **I2** (main TeslaAPI.py:1444-1452): in `applySyncedTokens`, the refresh token is stored before the sentinel.
  - At startup only (sync not yet registered), a concurrent `refreshTokenIfNeeded` in that window could refresh with the decoded exp.
  - The window is negligible. Setting the sentinel before storing the refresh token, and still after the bearer, would close it.
- **I3** (main TeslaMateVehicle.py:205-213): if the TeslaMate DB is unreachable at startup, `syncTokens` becomes False.
  - The hourly resync still runs and applies tokens, but `tokenSyncEnabled()` is False, so the refresh paths (e.g. wake on 401) are open for TeslaMate's token.
  - Pre-existing semantics, not introduced here.
- **I4** (main TeslaAPI.py:272): the `car_api_available` empty-baseURL guard runs before `refreshTokenIfNeeded`. With no proxy and an empty bearer, the refresh comes only from the 5-minute main-loop `refreshTokenIfNeeded` (TWCManager.py:950; 1.3.4 :874), which covers it.
  - Nit: the INFO8 text "token type is unknown" is wrong when there is simply no token yet.
- **I5** (main TeslaAPIEVSE.py:47-51): a read-only TeslaAPIEVSE is now excluded from `distributeEVSEPower`, so its draw is not budgeted. That is consistent with the read-only gate and not a regression, since commands were 401ing before.

## Checks that passed

- **Sync acceptance:**
  - `applySyncedTokens` passes the refusal via `fromSync`, and hand-entered bearer tokens are still refused.
  - The sentinel is set last.
  - Refresh is blocked in every path while sync is on: `apiRefresh` head (covers wakeVehicle 401), `refreshTokenIfNeeded`, `setCarApiRefreshToken`, and 1.3.3's inline car_api_available refresh.
  - The startup sync, before registration, no longer calls `setCarApiRefreshToken`, so the old startup refresh to fleet-auth is gone.
  - `CarApiVehicle.get_car_api`'s `self.apiRefresh()` is a pre-existing AttributeError (noted in the plan).
- **Restore with sync off:** a saved sentinel becomes the stored token's exp, or now if it can't be decoded. It decodes the bearer that `loadSettings` set one line earlier, so the order is safe.
- **Classification:**
  - aud owner-api is checked first. A live-shaped token gives OwnerAPI, read-only, verifyCert True, proxy ignored.
  - A Fleet token gives the proxy and proxyCert, or the ou_code/aud-host region, or NA.
  - Anything else gives baseURL "", an ERROR without the token, readOnly False, and the token is still stored.
  - Owner, Fleet, Owner restores the URL and cert each time. `CarApiVehicle.verifyCert` follows the token.
- **Unknown token, no HTTP:**
  - Guarded in `car_api_available`, `setChargeRate`, `wakeVehicle` and `get_car_api`.
  - `car_api_charge`/`applyChargeLimit` reach HTTP only through `car_api_available`.
  - In Powerwall2, `get("")` raises MissingSchema inside its try.
- **Other readers on main:**
  - The login region list, `getLoginURL` and `regionAudience` use `fleetRegions()`.
  - TeslaPowerwall2 /products and /energy_sites work on owner-api.
  - HTTPControl still uses the setters.
  - `CarApiVehicle.is_awake` and `update_vehicle_data` go through `get_car_api`.
- **Gate:**
  - Covers `setChargeRate`, `car_api_charge`, `applyChargeLimit`, `wakeVehicle`, `CarApiVehicle.apply_charge_limit` and the `car_api_available` wake loop. That includes direct callers (`TeslaAPIEVSE.setTargetPower` and `apiDebugInterface`).
  - No HTTP call and no error time are recorded.
  - INFO is logged once per state change, and is reset only when readOnly flips.
  - VehiclePriority skips via `continue` before retries and stats, so no failure is counted, and only for COMMAND_METHODS. `getModuleByPriority` uses a strict `<`, so the loop can't spin.
  - Reads are unaffected.
- **Ports:**
  - The 1.3.4 COMMAND_METHODS has the same members as main.
  - Dropping the EVSE layer is correct: 1.3.4 has no EVSEInstance.
  - 1.3.3 carries sync acceptance only, and works with its aud-first first-token classification and its TLS session/ownerapi refresh paths.
- **Commit messages:** accurate on all branches. Each claim matches the code, and the 1.3.4 port notes are correct.
