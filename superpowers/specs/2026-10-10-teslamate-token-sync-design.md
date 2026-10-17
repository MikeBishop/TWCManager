# TeslaMate token sync works (PR 1 of the unified-integrations plan)

Date: 2026-10-10
Status: decisions approved by the user in chat
Background: .superpowers/unified-integrations-proposal.md (sections 3.1, 3.2 and 5; addendum)

## Problem

TeslaMate token sync is broken in two independent ways.

1. **Owner API tokens are misclassified** (1.3.4 and main only).
   - `TeslaAPI.setCarApiBearerToken` chooses the base URL from the JWT's `ou_code`.
   - A live TeslaMate access token is an Owner API token: `aud` includes `https://owner-api.teslamotors.com/` and `azp` is `ownerapi`. **It also carries `ou_code: "NA"`.** It is therefore treated as a Fleet token and sent to the Fleet API, which returns 401.
   - 1.3.3 checks `aud` for owner-api first, and so works.
2. **Synced tokens are refused after startup** (1.3.3, 1.3.4 and main).
   - `setCarApiBearerToken` returns False when `master.tokenSyncEnabled()` is true, the guard against hand-entered tokens while sync is on.
   - `TeslaMateVehicle.doSyncTokens` sets tokens through that same method. The first sync runs from `TeslaMateVehicle.__init__`, before the module is registered, and succeeds. Each hourly `resyncTokens` call runs after registration, and is refused silently because the return value is ignored.
   - TeslaMate rotates its access token every 6 h, and each token lives 8 h. TWCManager therefore keeps the startup token until it expires.
   - Confirm this with a test before fixing it.

## Changes

### 1. Synced tokens are accepted

The `tokenSyncEnabled()` refusal applies only to tokens from other sources: the web UI, a manual save, or a refresh. The sync path supplies its token through an explicit route, e.g. `setCarApiBearerToken(token, fromSync=True)` or a dedicated `applySyncedTokens(access, refresh)`. The implementer picks the shape that keeps callers obvious.

The existing behaviour stays the same:
- the expiry set by sync means TWCManager never refreshes a synced token;
- `setCarApiRefreshToken` still skips refresh while sync is on.

Make sure the decoded `exp` doesn't override the sync's "never expires" sentinel in a way that later triggers a TWCManager refresh. Check the order of `setCarApiTokenExpireTime` and `setCarApiBearerToken` in `doSyncTokens`.

### 2. Token classification, re-evaluated on every token set

Every accepted token is classified, not only the first one. Users switch between token types, for testing if nothing else, so the base URL must follow the current token.

Rules, in order (an Owner API token can also carry `ou_code`, so `aud` is checked first):
1. `aud` (a string or a list) contains `owner-api` → **Owner API token**. `baseURL` is the Owner API vehicles URL (`regionURL["OwnerAPI"] = "https://owner-api.teslamotors.com/api/1/vehicles"`). **`teslaProxy` is ignored**, because the Vehicle Command proxy needs Fleet tokens. `readOnly = True`.
2. Otherwise, if the token is a **Fleet token** (`aud` contains `fleet-api`, or `ou_code` is in `regionURL`):
   - with `teslaProxy` configured → `baseURL` = the proxy URL, as today;
   - without it → the Fleet region URL for `ou_code`, or NA when `ou_code` is absent and `aud` names a region host (match the host to `regionURL`).
   
   `readOnly = False`.
3. Otherwise (no recognised claims, or an undecodable token) → **unknown**. `baseURL` is cleared (`""`), so no API calls are attempted. Log an ERROR saying the token type couldn't be determined (never the token itself). `readOnly = False`. The token is still stored, so a later valid token or sync replaces it. A `teslaProxy` configured for an unknown token doesn't make it usable: the proxy only takes Fleet tokens, and a Fleet token is recognised by rule 2. *(Decided by the user 2026-10-10: error rather than default to the Owner API.)*

Switching from an Owner API token back to a Fleet token must restore the proxy or region URL. That means the URL chosen at `__init__` from `teslaProxy` has to be remembered separately (e.g. `self.proxyURL`), so `baseURL` can be recomputed from it.

Each classification logs the result at INFO: token type, base URL host, and read-only. It never logs the token.

### 3. Minimal command gate for read-only

While `TeslaAPI.readOnly` is true:
- `VehiclePriority` skips TeslaAPI for state-changing commands (its `COMMAND_METHODS`, or equivalent), so the next channel is tried. A read-only TeslaAPI does not count as a failure in its stats.
- `TeslaAPI` itself refuses command entry points that can be reached without going through VehiclePriority: at least `setChargeRate`, `car_api_charge` (start/stop) and `applyChargeLimit`. Each returns the module's usual failure value, logs once at INFO per state change, makes no HTTP call, and records no API error time. Recording an error would trigger the error backoff that also blocks reads.
- Reads are unaffected.

The rest of the read-only Owner API path (products swap, `ownerapi` refresh client, TLS 1.3 session, paste-back of a refresh token) is PR 2, and is out of scope here.

### 4. Known limitation (documented, not fixed)

There is a single token slot. Turning on TeslaMate sync replaces a Fleet token, which is today's behaviour. PR 3 adds a second slot. Note this in the PR description.

## Branches

- `release/1.3.4` and `main`: changes 1–3.
- `release/1.3.3`: change 1 only (sync acceptance). 1.3.3 already classifies by `aud`; add the `readOnly` flag only if the 1.3.3 diff stays trivial.
- Develop on `main` first, then cherry-pick and adapt.

## Tests

- **Classification:**
  - A live-shaped TeslaMate access token (`aud` owner-api plus userinfo, `azp` ownerapi, `ou_code` NA) gives Owner API, read-only, even with `teslaProxy` set.
  - A Fleet token (`aud` fleet-api, `ou_code` NA) gives the proxy URL when one is configured, otherwise the NA region URL; not read-only.
  - An undecodable token, or one without owner-api `aud` and without `ou_code`, gives `baseURL` "" and an ERROR log line that does not contain the token.
  - Switching owner → fleet → owner restores the right URL each time.
- **Sync acceptance:**
  - With a registered `TeslaMateVehicle` that has `syncTokens` on, a resync updates `carApiBearerToken`.
  - A hand-entered token is still refused while sync is on.
  - No refresh is attempted for a synced token.
- **Gate:**
  - A read-only TeslaAPI is skipped by VehiclePriority for commands.
  - `setChargeRate`, `car_api_charge` and `applyChargeLimit` make no HTTP call and don't record an error time.
  - Reads still run.
