# Two Tesla API token slots (PR 3 of the unified-integrations plan)

Date: 2026-10-10
Status: approved by the user 2026-10-10
Background: `.superpowers/unified-integrations-proposal.md` (§5, PR 3; addendum). Builds on PR 1 (#679/#680, token classification, read-only gate) and PR 2 (`fix/owner-api-refresh` / `port-owner-api-refresh-1.3.4`, Owner API refresh parity).

## Why

TWCManager stores one Tesla API token. Users have two kinds:

- **Owner API tokens** (`aud` contains owner-api, `azp` ownerapi). Free, read-only now that Tesla refuses Owner API commands. TeslaMate holds one and token sync copies it over. The v1.3.3 image also saved one.
- **Fleet API tokens** (Fleet `aud` / `ou_code`). Paid per call, and the only way to send commands over the internet (through the user's vehicle command proxy).

With one slot, turning on TeslaMate sync replaces a Fleet login, and a 1.3.3 user who adds a Fleet login loses free reads. The user wants both kept at once, so TeslaMate sync can stay on permanently, reads are free when possible and commands still work.

This is for **v1.3.4**, the reconverged release that retires the 1.3.3 (Owner API) line. The 1.4.0 plan adds a central class that exposes read and write capabilities and walks a priority order (PR 4, `IntegrationOrder`, moved to 1.4.0). This PR must not build a fallback that 1.4.0 makes dead code.

## Behaviour the user wants

Reads: TeslaMate when it is pushing fresh data, then BLE when the car is home (main only; **do not backport BLE reads to 1.3.4**), then the Owner API if there is a token, then the Fleet API.

Commands: BLE if configured, then the Fleet API. TeslaMate and the Owner API can't send commands.

When a token stops working, log the error and fall through to the next source.

TeslaMate and BLE ordering already exist today and are out of scope. This PR adds the Owner-before-Fleet part.

## Design (decided with the user)

### 1. A token slot class, two instances

A small class holds one token's state: access token, refresh token, expiry, token type (owner / fleet / unknown, from PR 1's classification), its base URL and cert-verify setting, its refresh endpoint and client ID (PR 2), and **source**: `synced` (TeslaMate), `pasted`, or `login` (the Fleet OAuth login).

`TeslaAPI` holds two instances, `ownerSlot` and `fleetSlot`. The slot class owns per-token logic that today sits on `TeslaAPI` (classification result, expiry handling, refresh). Neither slot knows about the other.

`TeslaAPI` stays one module under the name `TeslaAPI`. The ~30 places that look it up by name do not change in what they look up.

### 2. Slot selection, not per-request fallback

One small function on `TeslaAPI` picks the slot for a request:

- **Reads** (vehicle list, vehicle data, location, charge state): the Owner slot if it holds a usable token, otherwise the Fleet slot.
- **Commands** (`charge_start`/`charge_stop`, `set_charging_amps`, `set_charge_limit`, `wake_up`, anything else PR 1's read-only gate covers): the Fleet slot only. With no usable Fleet token, the command is refused the way PR 1's read-only gate refuses it today (usual failure value, no HTTP call, no error time recorded, log once per state change).

There is **no retry of a failed request on the other slot**. Fallthrough happens at the slot level: when a slot's token dies (a 401 on use, or a rejected refresh) that slot is cleared and an ERROR is logged, and the next request selects the other slot. The one request that hit the failure fails; the next poll succeeds. The user accepted this for 1.3.4.

**What counts as a dead or refused token (decided with the user):**

- A 401 whose body says "expired", on a slot TWCManager refreshes (not `synced`): refresh once and retry, as `get_car_api` does today.
- Any other 401, or a rejected refresh: clear the slot and log an ERROR, as today.
- A 403, 410 or 412 (Tesla refusing that API or endpoint, as the Owner API already does with 412 on `/vehicles`): keep the token, but **pause the slot for reads for one hour**, with an ERROR logged. Reads select the other slot meanwhile; after the hour the slot is tried again. For a `synced` slot, a newly synced token ends the pause early. Other failures (timeouts, 5xx, 429) keep today's handling and do not pause or clear a slot.
- This applies to vehicle reads: `CarApiVehicle.get_car_api` and the vehicle-list fetch in `car_api_available`. Storm Watch's energy-site read (`TeslaPowerwall2`) uses the read slot, but its failures never pause or clear a slot; its scope handling is below.

**Scope check for Fleet tokens (decided with the user):** Fleet access tokens are JWTs whose `scp` claim lists granted scopes. A Fleet slot is not usable for a purpose whose scope its token lacks, and no request is made:

| Purpose | Required scope (any one) |
|---|---|
| vehicle reads | `vehicle_device_data` |
| commands (`charge_start`/`charge_stop`, `set_charging_amps`, `set_charge_limit`) | `vehicle_charging_cmds` or `vehicle_cmds` |
| Storm Watch energy read | `energy_device_data` |

- Log one ERROR per token per missing scope, naming the scope and saying to redo the Fleet login with it. Not every poll.
- No pause and no clearing: reads go to the Owner slot, commands stay on BLE (or are refused as in the read-only gate). A new token re-evaluates.
- A token with no `scp` claim is treated as having every scope, so the check never blocks a token that works today. Owner tokens are not checked (the Owner API doesn't enforce scopes).
- A 403 from the Storm Watch energy endpoint is treated as missing `energy_device_data`: the same ERROR (replacing today's WARNING), no pause, no clear. A 403 from vehicle reads keeps the one-hour pause above.
- TWCManager sends no command that needs `vehicle_cmds` specifically; all its commands are charging commands. (Confirmed from a live Fleet token's `scp` claim on 2026-10-10: `openid`, `user_data`, `vehicle_device_data`, `vehicle_cmds`, `vehicle_charging_cmds`, `energy_device_data`, `energy_cmds`, `offline_access`.)
- `wake_up` goes through the command slot and is checked with the command scopes (my call; its exact scope in Tesla's docs is unconfirmed).

"Usable" means the slot has an access token of known type for that slot, holds the scope for the purpose, and (for reads) is not paused.

**Read-only is a special case of scope (decided with the user):** each slot reports what its token grants. The Owner slot grants reads and energy, never commands (a fixed property of the Owner API, not read from the token, and not logged as a missing scope). A Fleet slot grants what its `scp` lists (everything when there is no `scp`). The chooser is one uniform walk: Owner slot, then Fleet slot, first usable for the purpose. Commands reach the Fleet slot because the Owner slot never grants them, not through a special rule. `readOnly` is "no slot grants commands". This is a small version of 1.4.0's capability walk. Keep the definition in one place; it is what 1.4.0's central class will replace.

`TeslaAPI.readOnly` keeps its meaning for its existing readers (`VehiclePriority`, `TeslaAPIEVSE`, the login template): true when commands are impossible, i.e. no usable Fleet slot.

### 3. Settings keys and migration

- Fleet slot: the existing `carApiBearerToken`, `carApiRefreshToken`, `carApiTokenExpireTime` keys, unchanged.
- Owner slot: new `ownerApiBearerToken`, `ownerApiRefreshToken`, `ownerApiTokenExpireTime`.
- Each slot's source is saved too (key names are the builder's call).

Migration on load, once, idempotent:

- Classify the token in the `carApi*` keys by its access token (PR 1 rules).
  - Owner API token: move it with its refresh token and expiry to the Owner slot. Clear the `carApi*` keys. If it is marked `synced` (below), drop the refresh token instead of moving it: that is TeslaMate's, which TWCManager must not hold (§5).
  - Fleet token: stays.
  - Unknown type: stays where it is, ERROR logged (PR 1's error rule; not the proposal's older "assume Owner").
- Source for migrated tokens: if TeslaMate sync is on at load and the token is an Owner token, mark it `synced` (this is the live box today: a synced Owner token sitting in `carApi*`). Otherwise `pasted`. A Fleet token that came from the login can't be told from a pasted one; mark it `login` if the existing settings say so, otherwise `pasted` (builder's call how to detect).
- **Load order (my call):** `TWCMaster.loadSettings` today skips restoring the saved token while sync is on, assuming the startup sync already set it. That skip goes: both slots are restored from settings regardless of sync, and migration runs regardless of sync. A saved `pasted` or `login` token then wins over a token the startup sync placed first (§5: sync never replaces those); a saved `synced` token is replaced by the fresher startup sync, which is the normal resync.
- Downgrading after migration loses the Owner token (old code doesn't read `ownerApi*`). Accepted; note it in the changelog.

### 4. Refresh

Each slot refreshes against its own endpoint and client ID: Owner tokens with `client_id ownerapi` at auth.tesla.com, Fleet tokens as PR 2 does. A rejected refresh clears only that slot.

**A `synced` slot can't be refreshed, by construction:** it holds no refresh token (§5). Its expiry is the access token's own decoded `exp`; once that passes, the slot counts as empty until the next sync fills it (TeslaMate rotates every 6 h, each token lives 8 h, and sync runs hourly). PR 1's never-expires sentinel (`SYNCED_TOKEN_EXPIRY`) and `restoreCarApiTokenExpireTime`'s swap back to `exp` when sync is off are no longer needed for synced tokens; remove or retire them as the builder sees fit. A refresh attempt on a slot with no refresh token is the existing `not_configured` result, never a request.

**A `synced` token while sync is off:** unchanged by sync turning off (which can happen without the user: `TeslaMateVehicle.doSyncTokens(firstrun=True)` disables sync when the TeslaMate database is unreachable at startup). It is used until its `exp`, then the slot is empty. With sync off, a paste or Fleet login may replace a synced token (the refusal in §6 applies only while sync is on).

### 5. TeslaMate sync

- **Sync fetches and applies only the access token** (decided with the user). TWCManager never uses a synced token's refresh token, so it doesn't read, decrypt or store it: `TeslaMateVehicle.fetchLatestTokens` stops selecting/decrypting the refresh column, and the sync entry point (`applySyncedTokens` today) takes an access token only. This removes the risk of TWCManager spending TeslaMate's single-use refresh token, and one secret from TWCManager's settings.
- A synced token goes to the slot matching its type: Owner token to the Owner slot, **Fleet token to the Fleet slot** (newer TeslaMate releases can use the Fleet API, and the user expects such a token may still work through their proxy since TeslaMate would run on the user's Fleet key).
- Sync may fill an **empty** slot, or replace a token whose source is `synced`. It **never replaces a `pasted` or `login` token**. When it skips for that reason, log at INFO once per state change, not every hour.
- A synced token of unknown type is skipped with an ERROR.
- If a synced Fleet token can't sign commands, nothing checks up front; the failure is logged when a command first reaches the Fleet API.
- Healing: when a pasted token dies and its slot is cleared, the next hourly sync can fill it.

### 6. Pasting and the settings page

- One paste area, as today (the access/refresh token fields). Not one per slot.
- The settings page shows each slot's status: whether it holds a token, its expiry, and its source (synced from TeslaMate / pasted / Fleet login).
- A pasted token goes to the slot matching its type. The other slot is untouched.
  - Unknown type: refused with a message that the token type couldn't be recognised; nothing stored.
  - A refresh token pasted alone: its type comes from PR 2's `refreshTokenType` logic (Owner refresh tokens are JWTs; the Fleet PKCE refresh token seen live is opaque), and it goes to that slot.
- **With sync on, nothing overwrites a `synced` token**: a paste or a Fleet login into a slot holding a synced token is refused, with a message saying TeslaMate manages that slot and how to replace it (remove the token, or turn sync off). This protects against an accidental overwrite.
- Each slot gets a **Remove token** button, so the user can deliberately clear a slot (including a synced one) and then paste.
- With sync on, pasting into a slot that is empty or holds a non-synced token is allowed.

### 7. Main and 1.3.4

Same design on both. Develop on main, stacked on PR 2 (`fix/owner-api-refresh`), then port to 1.3.4, stacked on `port-owner-api-refresh-1.3.4`, the way PRs 1 and 2 were done. On main, `TeslaAPIEVSE`/`TeslaAPIController` Fleet charge-rate calls are commands and use the Fleet slot.

## Goals

- Owner and Fleet tokens coexist and survive restarts.
- TeslaMate sync can stay on alongside a Fleet login.
- Reads use the free Owner API when a usable Owner token exists.
- Existing installs upgrade with no manual steps: a Fleet-only 1.3.4 user sees no change; a 1.3.3 user's Owner token lands in the Owner slot; the live box's synced token keeps resyncing.

## Non-goals

- No per-request retry on the other slot.
- No new config setting and no configurable order; the order is fixed and an empty slot is skipped.
- No BLE read backport to 1.3.4.
- No `IntegrationOrder` or central read/write class (1.4.0).
- No change to who looks up `TeslaAPI` by name.
- Fixing the existing INFO4 log of the refresh response (it prints tokens) is not required. If this PR touches that line anyway, remove the token content while there.

## Anti-goals (failure even if it works)

- Fallback logic inside `TeslaAPI` beyond the one slot chooser, which 1.4.0 would delete.
- TWCManager ever refreshing a synced token, or holding TeslaMate's refresh token at all.
- Sync silently overwriting a token the user pasted or logged in with.
- An accidental paste overwriting a synced token while sync is on.
- Any token value in a log line.

## Constraints

- Release branches have 62 pre-existing unit failures; ports must leave exactly that set failing.
- Black formatting.
- Never log a token: no new log line may contain a token value. (Existing offenders are deferred, see Non-goals.)
- Commits end with the Co-Authored-By line; PR bodies with the Claude Code line.

## Left to the builder

- Slot class name, file placement, and method names; whether existing `getCarApiBearerToken()`-style accessors stay as Fleet-slot shims or callers move to slot access.
- Saved-source key names and the template layout of the slot status rows.
- How `CarApiVehicle.get_car_api` and the vehicle-list fetch obtain the read slot's token and base URL.
- How WebIPCControl's token output (it prints `carApiTokenExpireTime`) shows two slots.
- Test structure.

## Tests the user will expect to see

- Migration: Owner token in `carApi*` moves to the Owner slot; Fleet stays; unknown stays with ERROR; idempotent; synced marking when sync is on.
- Selection: reads use Owner when usable, Fleet otherwise; commands use Fleet only and are refused (no HTTP call) without a usable Fleet token.
- Slot-level fallthrough: a 401 on an Owner read clears the Owner slot and the next read goes to Fleet; a 412 pauses the Owner slot for an hour (token kept) and reads go to Fleet, then return; a new sync ends a synced slot's pause.
- Refresh per slot; a synced slot holds no refresh token and never makes a refresh request; it counts as empty after its `exp`.
- Sync: TeslaMate's refresh token is neither decrypted nor stored; migrating a synced Owner token drops its stored refresh token.
- Sync: fills empty slot by type; replaces its own token; never replaces pasted/login; unknown skipped; Fleet token from TeslaMate lands in an empty Fleet slot.
- Paste: routed by type; unknown refused; refresh-token-alone routed by type; paste over a synced token refused while sync is on; Remove token clears a slot.
