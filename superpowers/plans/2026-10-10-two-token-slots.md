# Two Tesla API Token Slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TeslaAPI keeps an Owner API token and a Fleet API token at once: reads use the Owner token when it is usable, commands use only the Fleet token, and TeslaMate sync, pasting, the Fleet login and settings migration each fill the slot that matches the token's type.

**Architecture:** A new `TeslaTokenSlot` class holds one token's state and does its own expiry, pause and refresh. `TeslaAPI` keeps two instances (`ownerSlot`, `fleetSlot`) and one chooser, `slotFor(purpose)`. Every request asks `slotFor` for a slot and takes its token, base URL and cert setting from it. Read failures act on that slot only (clear on a 401, pause for an hour on 403/410/412), so the next request picks the other slot. One intake function, `storeToken`, sends tokens to a slot by type and decides who may replace whom.

**Tech Stack:** Python 3, requests, PyJWT, Jinja2 templates, pytest with requests_mock, black.

**Spec:** `.superpowers/specs/2026-10-10-two-token-slots-design.md` (binding). Background: `.superpowers/unified-integrations-proposal.md` §5, `.superpowers/owner-api-refresh-prs.md` (PR 2).

**Branches:** main line: create `feat/token-slots` from `fix/owner-api-refresh` (head `b6645fe`, which merges #682's crash fix) in a new worktree (superpowers:using-git-worktrees; fallback `git -C /home/mbishop/github/TWCManager worktree add -b feat/token-slots <path> fix/owner-api-refresh`). Tasks 1–6 commit there. Task 7 ports to `port-token-slots-1.3.4`, created from `port-owner-api-refresh-1.3.4`. Never check out, commit to or edit tracked files in the `ble-threading-twcmanager-62cb96` worktree.

**Commands:** `$PY` = `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python`; `$BLACK` = the `black` next to it. The shell is fish: `set -x PY …`. Run every command from the task worktree's root.

## Global Constraints

- Release branches have exactly 62 pre-existing unit failures; the port must leave exactly that set failing (sorted FAILED lists identical before and after). Main must stay at zero failures (572 passing at the start).
- Black formatting: `$BLACK lib tests` before every commit; `$BLACK --check lib tests` must pass.
- No new log line may contain a token value (access or refresh). Any line this PR moves or rewrites that prints one loses the token: the INFO4 "Car API auth response" in the refresh, and the INFO8 "empty carApiBearerToken '…'" line in `car_api_available`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- No retry of a failed request on the other slot. No fallback logic in `TeslaAPI` other than `slotFor`.
- No new config setting and no configurable order.
- The module is still looked up as `getModuleByName("TeslaAPI")`. No caller changes the name it looks up.
- TWCManager never refreshes a `synced` token and never holds TeslaMate's refresh token.
- Owner refresh: `client_id` `ownerapi` at `https://auth.tesla.com/oauth2/v3/token`, through the TLS 1.3 `session`. Fleet refresh: as PR 2 does (main: `fleetRefreshURL`; 1.3.4: `authTokenURL` when `usePKCE()`).
- Read pause: 3600 seconds, on HTTP 403, 410 or 412 only. Timeouts, 5xx and 429 keep today's handling.
- Settings keys: Fleet = `carApiBearerToken`, `carApiRefreshToken`, `carApiTokenExpireTime` (unchanged). Owner = `ownerApiBearerToken`, `ownerApiRefreshToken`, `ownerApiTokenExpireTime`.
- 1.3.4 gets no BLE read path.

## Review Focus

Inputs the spec implies but no spec-listed test covers, most likely to bite first. Each line names the task that holds its test.

1. **Sync configured but TeslaMate unreachable at startup.** `doSyncTokens(firstrun=True)` turns sync off before `loadSettings`, so "sync on at load" is false. The live box's `carApi*` holds a TeslaMate Owner token *with TeslaMate's refresh token* and the `99999³` expiry. Migration must still mark it `synced`, drop the refresh token and never refresh it. A saved `99999³` expiry counts as evidence of `synced`. Test: Task 5, `test_sentinel_marks_synced_when_sync_off_at_load`.
2. **The never-expires sentinel already on disk.** Retiring `SYNCED_TOKEN_EXPIRY` doesn't remove `carApiTokenExpireTime = 99999³` from existing settings.json. A restored token must take its own `exp`; an undecodable one expires now. Test: Task 2, `test_restore_legacy_sentinel_uses_token_exp`.
3. **Storm Watch 403 on a Fleet-only install.** A Fleet token without `energy_device_data` scope gets 403 from `energy_sites`. Spec §2: Storm Watch failures never pause or clear a slot, and its 403 is reported once per token as a missing `energy_device_data` scope. Test: Task 3, `test_storm_watch_403_does_not_pause_slot`.
4. **Both slots empty or both paused.** `car_api_available`, `is_awake` and `update_vehicle_data` return False with no HTTP call and no error backoff recorded. `readOnly` is True. Test: Task 2, `test_no_usable_slot_makes_no_requests`, plus Task 3, `test_both_paused_no_requests`.
5. **Fleet login while sync is on.** The spec's goal is that sync stays on beside a Fleet login. The login form must show, and the login exchange must work, when sync is on and the Fleet slot is empty or holds a non-synced token. Both are refused only when the Fleet slot holds a live synced token. Test: Task 6, `test_fleet_login_allowed_while_sync_on_and_fleet_slot_free`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `lib/TWCManager/Vehicle/TeslaTokenSlot.py` | create | `TeslaTokenSlot` (one token's state, expiry, pause, refresh) and `decodeToken()` |
| `lib/TWCManager/Vehicle/TeslaAPI.py` | modify | two slots, `slotFor`, `storeToken`, `readOnly` property, request paths, migration |
| `lib/TWCManager/TWCMaster.py` | modify | load/save of both slots, migration call (`loadSettings` ~1097, `saveSettings` ~1484) |
| `lib/TWCManager/Vehicle/TeslaMateVehicle.py` | modify | fetch and apply the access token only |
| `lib/TWCManager/EMS/TeslaPowerwall2.py` | modify | Storm Watch uses the read slot (failures never pause or clear it) |
| `lib/TWCManager/Control/HTTPControl.py` | modify | settings token fields, `/teslaAccount/removeToken`, `apiAvailable` |
| `lib/TWCManager/Control/WebIPCControl.py` | modify | `getStatus` / `dumpState` for two slots |
| `lib/TWCManager/Control/themes/Default/settings.html.j2` | modify | slot status rows + Remove buttons |
| `lib/TWCManager/Control/themes/Default/handle_teslalogin.html.j2` | modify | result texts; login form gate |
| `docs/modules/Vehicle_TeslaMate.md`, `CHANGELOG.md` | modify | sync behaviour; downgrade note |
| `tests/unit/teslatokens.py` | modify | shared helpers (`no_threads`, `add_home_vehicle`, URL constants) |
| `tests/unit/test_teslatokenslot.py` | create | Task 1 |
| `tests/unit/test_teslaapi_token_slots.py` | create | Tasks 2–3 (selection, fallthrough) |
| `tests/unit/test_teslaapi_token_migration.py` | create | Task 5 |
| `tests/unit/test_teslaapi_token_paste.py` | create | Task 6 |
| existing `test_teslaapi_*.py`, `test_teslamate_token_sync.py` | modify | ported to the slot API (Task 2) and to the new rules (Tasks 4–6) |

---

### Task 1: `TeslaTokenSlot` class

**Files:**
- Create: `lib/TWCManager/Vehicle/TeslaTokenSlot.py`
- Test: `tests/unit/test_teslatokenslot.py`

**Interfaces:**
- Consumes: nothing from this PR. `fleet_token`/`owner_token` in `tests/unit/teslatokens.py` gain an optional `scp` argument (default for `fleet_token`: the full scope list seen on a live Fleet token, `["openid", "user_data", "vehicle_device_data", "vehicle_cmds", "vehicle_charging_cmds", "energy_device_data", "energy_cmds", "offline_access"]`; `scp=None` omits the claim). Reuses `make_jwt`, `owner_token`, `fleet_token`, `AUTH_TOKEN_URL`, `FLEET_REFRESH_URL` from `tests/unit/teslatokens.py`.
- Produces (module `TWCManager.Vehicle.TeslaTokenSlot`):
  - `decodeToken(token) -> dict | None`: unverified JWT claims, or None. This is today's `TeslaAPI.decodeToken` body moved here; `TeslaAPI.decodeToken` delegates to it.
  - `SCOPES = {"read": ("vehicle_device_data",), "command": ("vehicle_charging_cmds", "vehicle_cmds"), "energy": ("energy_device_data",)}`: any one listed scope satisfies the purpose (spec §2, scope check).
  - `SOURCES = ("synced", "pasted", "login")`, `PAUSE_SECONDS = 3600`, `DEFAULT_LIFETIME = 8 * 60 * 60`, `REFRESH_MARGIN = 60 * 60`.
  - `class TeslaTokenSlot:`
    - `__init__(self, kind: str, classify: Callable[[str], tuple[str, str, bool | str]], refreshURL: str, clientID: str, post: Callable)`. `kind` is `"owner"` or `"fleet"`. `classify(token)` returns `(tokenType, baseURL, verifyCert)`. `post` is `session.post` for Owner and `requests.post` for Fleet.
    - Attributes: `scopes: frozenset | None = None` (the decoded `scp` list; None when the claim is absent or not a list), `scopeErrorsLogged: set` (reset by `setTokens`/`clear`), `kind`, `accessToken=""`, `refreshToken=""`, `expireTime=0`, `tokenType=""`, `baseURL=""`, `verifyCert=True`, `source=""`, `pausedUntil=0`, `changes=0` (incremented by every `setTokens`, `clear` and `restore`).
    - `setTokens(self, accessToken: str, refreshToken: str | None = None, expireTime: float | None = None, source: str = "pasted") -> None`.
    - `clear(self) -> None`.
    - `empty(self, now: float | None = None) -> bool`.
    - `usable(self, purpose: str, now: float | None = None) -> bool`. `purpose` is `"read"`, `"command"` or `"energy"`.
    - `missingScope(self, purpose: str) -> str | None`: for a `fleet`-type token whose `scopes` is not None and contains none of `SCOPES[purpose]`, the first required scope name; otherwise None (Owner tokens and tokens without `scp` are never missing a scope).
    - `reportScopeRefused(self, purpose: str) -> None`: logs one ERROR per token per purpose (tracked in `scopeErrorsLogged`): `"Tesla Fleet API token lacks the " + scope + " scope, needed for " + label + "; log in to the Fleet API again and grant it."` with label `vehicle data` / `charge commands` / `Powerwall Storm Watch`. Never includes the token.
    - `pause(self, now: float | None = None) -> None`.
    - `needsRefresh(self, now: float | None = None) -> bool`.
    - `refresh(self, now: float | None = None) -> str`. Returns `"success"`, `"rejected"`, `"unreachable"` or `"not_configured"`.
    - `snapshot(self) -> tuple` / `restore(self, snap: tuple) -> None`.
    - `status(self, now: float | None = None) -> dict` with keys `holdsToken: bool`, `tokenType: str`, `source: str`, `expires: str` (`"%Y-%m-%d %H:%M"` local, `""` when empty), `paused: bool`.

Semantics the tests pin:
- `setTokens`: sets `scopes` from the decoded `scp` claim and clears `scopeErrorsLogged`. A non-empty access token is classified through `classify` (an empty one is not, and leaves `tokenType` `""`). `refreshToken=None` keeps the current refresh token; `""` clears it. `expireTime=None` means the decoded `exp`, or now + `DEFAULT_LIFETIME` when there is none. `source == "synced"` forces `refreshToken = ""` and `expireTime = exp`. Every call resets `pausedUntil` to 0.
- `empty(now)`: true when there is no access token, or when `source == "synced"` and `now >= expireTime`.
- `usable(purpose, now)`: not empty, `tokenType == kind`, `missingScope(purpose) is None` (calling `reportScopeRefused(purpose)` when it isn't, so the ERROR fires on first use without a request), and for `"read"` and `"energy"` also `now >= pausedUntil`. This is the spec's one definition of "usable". There is deliberately no expiry test: a pasted or login token past its expiry stays usable, so the command path (which refuses before `car_api_available` refreshes) and the read path's 401-"expired" → refresh → retry keep working as today. A synced token's expiry goes through `empty()`.
- `needsRefresh(now)`: has a refresh token, and either there is no access token or `expireTime - now < REFRESH_MARGIN`.
- `refresh`: with no refresh token, returns `"not_configured"` and makes no request. With an empty `clientID` (Fleet), logs today's "no teslaApiClientID configured" ERROR and returns `"not_configured"`. A 401 calls `clear()` and returns `"rejected"`. No response at all returns `"unreachable"`. Any other HTTP error or bad body returns `"rejected"` and keeps the tokens. Success calls `setTokens(access, refresh, now + expires_in, self.source)`. The request body is PR 2's: `client_id`, `grant_type=refresh_token`, `refresh_token`, `scope=offline_access`. The response log line says only that a response arrived, never its content.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_teslatokenslot.py`. Build slots with a stub `classify` that maps `owner_token()` to `("owner", OWNER_URL, True)`, `fleet_token()` to `("fleet", FLEET_NA_URL, True)` and anything else to `("unknown", "", True)`. Owner slot: `post=requests.post`, `refreshURL=AUTH_TOKEN_URL`, `clientID="ownerapi"`.

```python
def test_synced_token_drops_refresh_and_uses_exp():
    s = owner_slot(); tok = owner_token(expires_in=3600)
    s.setTokens(tok, "teslamate-refresh", 99999 * 99999 * 99999, "synced")
    assert s.refreshToken == "" and s.expireTime == decode_exp(tok)

def test_synced_slot_is_empty_after_exp():
    s = owner_slot(); s.setTokens(owner_token(expires_in=-1), source="synced")
    assert s.empty() is True and s.usable("read") is False

def test_synced_slot_never_refreshes(requests_mock):
    hit = requests_mock.post(AUTH_TOKEN_URL, json={})
    s = owner_slot(); s.setTokens(owner_token(expires_in=60), source="synced")
    assert s.needsRefresh() is False
    assert s.refresh() == "not_configured" and hit.called is False

def test_expired_pasted_token_stays_usable():
    s = fleet_slot(); s.setTokens(fleet_token(expires_in=-60), "r")
    assert s.usable("command") is True and s.needsRefresh() is True

def test_usable_requires_matching_type():
    s = fleet_slot(); s.setTokens(owner_token())
    assert s.usable("read") is False and s.usable("command") is False

def test_pause_blocks_reads_not_commands_for_an_hour():
    s = fleet_slot(); s.setTokens(fleet_token(expires_in=7200)); now = time.time()
    s.pause(now)
    assert s.usable("read", now + 3599) is False
    assert s.usable("command", now) is True
    assert s.usable("read", now + 3600) is True

def test_new_token_ends_pause():
    s = owner_slot(); s.setTokens(owner_token(), source="synced"); s.pause()
    s.setTokens(owner_token(jti="new"), source="synced")
    assert s.usable("read") is True

def test_access_token_alone_keeps_refresh_token():
    s = owner_slot(); s.setTokens(owner_token(), "r1"); s.setTokens(owner_token(jti="2"))
    assert s.refreshToken == "r1"

def test_jwt_without_exp_gets_default_lifetime():
    s = owner_slot(); before = time.time()
    s.setTokens(make_jwt(aud=OWNER_AUD))  # no exp claim
    assert before + 8 * 3600 <= s.expireTime <= time.time() + 8 * 3600

def test_fleet_token_missing_scope_not_usable_and_logs_once(caplog):
    s = fleet_slot(); s.setTokens(fleet_token(scp=["openid", "vehicle_device_data"]))
    assert s.usable("read") is True
    assert s.usable("command") is False and s.usable("command") is False
    assert caplog.text.count("vehicle_charging_cmds") == 1   # one ERROR per token per purpose
    assert s.usable("energy") is False and "energy_device_data" in caplog.text

def test_either_command_scope_suffices():
    s = fleet_slot(); s.setTokens(fleet_token(scp=["vehicle_cmds"]))
    assert s.missingScope("command") is None

def test_token_without_scp_has_every_scope():
    s = fleet_slot(); s.setTokens(fleet_token(scp=None))   # helper omits the claim
    assert s.usable("read") and s.usable("command") and s.usable("energy")

def test_owner_token_scope_not_checked():
    s = owner_slot(); s.setTokens(owner_token(scp=["openid"]))
    assert s.usable("read") and s.usable("energy")

def test_new_token_reevaluates_scope(caplog):
    s = fleet_slot(); s.setTokens(fleet_token(scp=["vehicle_device_data"])); s.usable("command")
    s.setTokens(fleet_token(scp=["vehicle_charging_cmds"], jti="2"))
    assert s.usable("command") is True

def test_owner_refresh_request(requests_mock):  # body and endpoint per PR 2
def test_refresh_401_clears_slot(requests_mock):   # accessToken == refreshToken == "" and changes bumped
def test_refresh_unreachable_keeps_tokens(requests_mock):  # ConnectionError -> "unreachable"
def test_fleet_refresh_without_client_id_is_not_configured(requests_mock, caplog)
def test_refresh_success_keeps_source(requests_mock)   # source "login" stays "login"
def test_refresh_logs_no_token(requests_mock, caplog):
    # after a successful refresh, neither new token string appears in caplog.text (level 1)
def test_snapshot_restore_round_trip()
def test_status_of_empty_and_filled_slot()  # holdsToken, source, expires text, paused
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslatokenslot.py -q`
Expected: FAIL (`ModuleNotFoundError: TWCManager.Vehicle.TeslaTokenSlot`)

- [ ] **Step 3: Implement `TeslaTokenSlot` and `decodeToken`** in `lib/TWCManager/Vehicle/TeslaTokenSlot.py` with the signatures and semantics above. Use logger `LoggerFactory.get_logger("TeslaAPI", "Vehicle")` so log routing doesn't change. Do not wire it into `TeslaAPI` yet.

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m pytest tests/unit/test_teslatokenslot.py -q && $PY -m pytest tests/unit -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
$BLACK lib tests
git add lib/TWCManager/Vehicle/TeslaTokenSlot.py tests/unit/test_teslatokenslot.py
git commit -m "feat: add TeslaTokenSlot, one Tesla API token's state and refresh

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: TeslaAPI holds two slots; requests go through `slotFor`

The state move. All single-token state and accessors leave `TeslaAPI`, and every caller moves to slot access in this one commit. Tokens still enter only through `storeToken`, under today's sync rule (while sync is on, only `source="synced"` is accepted). Tasks 4 and 6 refine that rule. Interim gap: until Task 5, a saved synced token restores as `pasted` with its refresh token. Don't deploy a build from between Tasks 2 and 5.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (class attrs 33–113, `__init__`, `refreshToken`…`refreshTokenIfNeeded` 181–300, `car_api_available` 302–600, command URLs in `car_api_charge` ~820, `applyChargeLimit`, accessors 1160–1222, intake 1308–1690, `setChargeRate`, `wakeVehicle`, `CarApiVehicle.verifyCert`/`is_awake`/`get_car_api`/`update_vehicle_data`/`apply_charge_limit`)
- Modify: `lib/TWCManager/TWCMaster.py:1097-1106, 1484-1487`; `lib/TWCManager/EMS/TeslaPowerwall2.py:238-245, 264, 298`; `lib/TWCManager/Control/HTTPControl.py:1193-1196, 1724-1754`; `lib/TWCManager/Control/WebIPCControl.py:133-137, 333-338`
- Modify: `tests/unit/teslatokens.py`
- Test: create `tests/unit/test_teslaapi_token_slots.py`. Port `test_teslaapi_request_errors.py` (from #682), `test_teslaapi_readonly_gate.py`, `test_teslaapi_owner_read.py`, `test_teslaapi_token_classification.py`, `test_teslaapi_refresh.py`, `test_teslaapi_fleetlogin.py` and `test_teslamate_token_sync.py`.

**Interfaces:**
- Consumes: Task 1's `TeslaTokenSlot`, `decodeToken`.
- Produces (on `TeslaAPI`):
  - `ownerSlot`, `fleetSlot`: `TeslaTokenSlot` instances built in `__init__`. Owner: `refreshURL=authTokenURL`, `clientID="ownerapi"`, `post=self.session.post`. Fleet: `refreshURL=fleetRefreshURL`, `clientID=refreshClientID`, `post=requests.post`. Build them after the session and config are set. On a config `KeyError`, build them with the class defaults.
  - `tokenRoute(self, token: str) -> tuple[str, str, bool | str]`: today's `applyTokenClassification`, minus the state. Owner gives `regionURL["OwnerAPI"]` with verify True. Fleet gives `proxyURL`/`proxyCert` when a proxy is set, otherwise the region URL. Unknown gives `""`, logs the existing ERROR text, and keeps the INFO "token type …, base URL host …" line (no token in it). Both slots' `classify` is this method.
  - `slotOfType(self, tokenType: str) -> TeslaTokenSlot | None`: `"owner"` gives `ownerSlot`, `"fleet"` gives `fleetSlot`, anything else gives None.
  - `slotFor(self, purpose: str) -> TeslaTokenSlot | None`: the only chooser. Exactly this:
    ```python
    if purpose in ("read", "energy") and self.ownerSlot.usable(purpose):
        return self.ownerSlot
    return self.fleetSlot if self.fleetSlot.usable(purpose) else None
    ```
  - `readOnly` becomes a read-only `@property`: `self.slotFor("command") is None`. Remove the class attribute and `readOnlyRefusalLogged`. Add `refusalLoggedAt = None`, which holds `fleetSlot.changes` at the last refusal log.
  - `storeToken(self, accessToken: str, refreshToken: str | None = None, source: str = "pasted", expireTime: float | None = None) -> str`. The type comes from `classifyToken(decodeToken(accessToken))`, or from `refreshTokenType(refreshToken)` when `accessToken` is empty. Results: `"unknown_type"` (nothing stored), `"error"` (both tokens empty), `"token_sync"` (Task 2 rule: sync on and source isn't `synced`), `"success"`. On success it calls `slot.setTokens(...)`. It does not queue a save; callers do that, as today.
  - `restoreSlot(self, slot, accessToken: str, refreshToken: str, expireTime, source: str = "pasted") -> None`. Settings-load path: no policy, no refresh. Does nothing when both tokens are empty. When `expireTime` equals `LEGACY_SYNCED_EXPIRY` or isn't a number, use the token's `exp`, or `time.time()` when it can't be decoded.
  - `LEGACY_SYNCED_EXPIRY = 99999 * 99999 * 99999`: renamed from `SYNCED_TOKEN_EXPIRY`. Only ever compared against, never set.
  - `refreshSlot(self, slot, saveOnFailure: bool = True) -> str`: `slot.refresh()` plus today's bookkeeping. On success, queue `saveSettings`. On failure, call `updateCarApiLastErrorTime()` and queue `saveSettings` if `saveOnFailure`.
  - `refreshTokenIfNeeded(self) -> None`: `refreshSlot` for each slot whose `needsRefresh()` is true. The `tokenSyncEnabled()` gate goes, because a synced slot has no refresh token.
  - `vehicleListURL(self, slot) -> str`: `/products` when `slot.tokenType == "owner"`, otherwise `slot.baseURL`.
  - `CarApiVehicle.get_car_api(self, path: str, checkReady=True, provesOnline=True) -> tuple[bool, dict | None]`. `path` is relative to the slot base (`"<VIN>"`, `"<VIN>/vehicle_data?endpoints=…"`). It takes `slot = self.carapi.slotFor("read")` and returns `(False, None)` with no request when that is None. It uses `slot.baseURL`, `slot.accessToken` and `slot.verifyCert`. A 401 "expired" calls `self.carapi.refreshSlot(slot)` and retries once. This fixes today's call to a nonexistent `CarApiVehicle.apiRefresh`. Set `req = None` before each attempt, which fixes the unbound `req` when `requests.get` raises.
  - `applySyncedTokens(self, accessToken, refreshToken) -> bool`: kept for now. Returns `storeToken(accessToken, "", "synced") == "success"`; `refreshToken` is ignored. Task 4 replaces it.
  - Removed from `TeslaAPI`: `baseURL`, `verifyCert`, `carApiBearerToken`, `carApiRefreshToken`, `carApiTokenExpireTime`, `SYNCED_TOKEN_EXPIRY`, `getCarApiBearerToken`, `getCarApiRefreshToken`, `getCarApiTokenExpireTime`, `getCarApiBaseURL`, `setCarApiBearerToken`, `setCarApiRefreshToken`, `setCarApiTokenExpireTime`, `restoreCarApiTokenExpireTime`, `clearCarApiBearerToken`, `applyTokenClassification`, `refreshToken`, `apiRefresh`, `refreshTokenIsOwner`, `pasteAccessToken` (callers use `storeToken(token)`, whose `refreshToken=None` keeps the slot's refresh token). Also removed: `CarApiVehicle.verifyCert`. Kept: `classifyToken`, `refreshTokenType`, `decodeToken` (now delegating), `savePastedToken`, `pasteRefreshToken`, `fleetTokenExchange`, `saveApiToken`, `refuseCommandIfReadOnly`.

Rewiring, one line each (no new behaviour beyond what the tests below pin):
- `car_api_available`: call `refreshTokenIfNeeded()` first, then `slot = slotFor("read")`. With None, log at INFO8 "car_api_available returning False: no usable Tesla API token (<reason>)", where the reason is `token type unknown` if either slot holds a token of the wrong or unknown type, `paused` if one is paused, and `no Tesla API token yet` otherwise. Then return False. The vehicle list uses `vehicleListURL(slot)` and the slot's token and cert. The final INFO8 line drops the token text.
- Commands (`setChargeRate`, `wakeVehicle`, `car_api_charge`'s charge_start/stop POST, `applyChargeLimit`, `CarApiVehicle.apply_charge_limit`): after `refuseCommandIfReadOnly` passes, use `slot = self.slotFor("command")` (or `self.carapi.slotFor("command")`) for the URL, token and cert. `wakeVehicle`'s 401 "expired" calls `refreshSlot(slot)`. On main, `TeslaAPIEVSE`/`TeslaAPIController` reach commands only through `setChargeRate`, so they need no change.
- `refuseCommandIfReadOnly(command)`: refuses when `readOnly`. Logs at INFO only when `fleetSlot.changes != refusalLoggedAt`, then records it. Message: `"Tesla API is read-only (no usable Fleet API token); not sending " + command + " or any other vehicle command. Commands need a Fleet API token or the TeslaBLE module."`
- `savePastedToken`/`pasteRefreshToken`/`fleetTokenExchange`: same flows on slots. `pasteRefreshToken` targets `slotOfType(refreshTokenType(token))`, takes `slot.snapshot()`, `clear()`s, sets `slot.refreshToken = token` with `slot.source = "pasted"`, calls `refreshSlot(slot, saveOnFailure=False)`, and on rejection calls `slot.restore(snap)`. It also snapshots and restores `carApiLastErrorTime`/`errorCount` as today. `fleetTokenExchange` stores with `storeToken(access, refresh, "login", now + expires_in)`.
- `TWCMaster.loadSettings` (still skipped while sync is on; Task 5 changes that): `restoreSlot(fleetSlot, carApi*…)`, then `restoreSlot(ownerSlot, ownerApi*…)`. `saveSettings`: write the `carApi*` keys from `fleetSlot` and the `ownerApi*` keys from `ownerSlot` (`accessToken`, `refreshToken`, `expireTime`).
- `TeslaPowerwall2.getStormWatch`: call `carapi.refreshTokenIfNeeded()`, then `slot = carapi.slotFor("energy")`. Go ahead when `slot` is not None; take token, base URL and `verify` from the slot. Replace the old `token and now < expiry` test with `slot is not None and now < slot.expireTime`. Storm Watch has no retry, so it skips an expired token as it does today.
- `HTTPControl`: `apiAvailable = bool(teslaapi and teslaapi.fleetSlot.accessToken)`, so an Owner-only user still sees the Fleet login form. In `process_save_settings`, the access field (with or without the refresh field) does `result = carapi.storeToken(access, refresh or None, "pasted")`; the refresh field alone keeps `pasteRefreshToken`. Any result other than `"success"` redirects to `/teslaAccount/<result>`.
- `WebIPCControl`: `getStatus` needs a token when `slotFor("read") is None`. `dumpState` prints `ownerApiTokenExpireTime=` and `carApiTokenExpireTime=` (Fleet) lines from the two slots.

Test porting (mechanical unless the test's meaning changed):

| Old | New |
|---|---|
| `api.setCarApiBearerToken(t)` | `api.storeToken(t)`. In a test that runs with sync on and isn't about sync, use `api.<slot>.setTokens(t, source=…)` |
| `api.getCarApiBearerToken()` / `getCarApiRefreshToken()` / `getCarApiTokenExpireTime()` | `api.<slot>.accessToken` / `.refreshToken` / `.expireTime`, the slot matching the token's type |
| `api.getCarApiBaseURL()`, `api.verifyCert`, `vehicle.verifyCert` | `api.<slot>.baseURL` / `.verifyCert` |
| `api.carApiRefreshToken = r` | `api.<slot>.refreshToken = r` |
| `api.apiRefresh()` | `api.refreshSlot(api.<slot>) == "success"` |
| `api.readOnly = True` (setup) | delete; store the token that makes it so |
| `SYNCED_EXPIRY` asserts after a sync | `slot.expireTime == exp(token)` and `slot.refreshToken == ""` |
| `TestSyncOn.test_no_refresh_while_sync_on` | becomes `test_synced_slot_not_refreshed`. A pasted Owner token with a refresh token *does* refresh while sync is on (spec §4) |
| `TestAccessTokenPastedAlone` "dropped" cases | the other type's refresh token now sits in the other slot and stays there (spec §6) |
| `TestRefusalLogging.test_logged_once_per_state_change` | "Fleet then Owner" becomes "Fleet stored, then `fleetSlot.clear()`": logs again once |

Move `_NoThread`/`no_threads` from the gate test into `teslatokens.py`. Add `add_home_vehicle(api) -> CarApiVehicle` (VIN1, atHome, `lastAPIAccessTime=now`), `OWNER_API_URL` and `FLEET_NA_URL`. `new_api()` and `master_with_settings()` stop resetting the removed attributes.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_teslaapi_token_slots.py`:

```python
def test_pasted_tokens_land_in_slot_by_type():
    api = new_api(); api.storeToken(owner_token()); api.storeToken(fleet_token())
    assert api.ownerSlot.tokenType == "owner" and api.fleetSlot.tokenType == "fleet"

def test_reads_use_owner_when_usable(no_threads, requests_mock):
    # both slots filled; GET OWNER_API_URL/VIN1/vehicle_data answered 200
    # update_vehicle_data() is True; the request's Authorization is the Owner token; FLEET_NA_URL not called

def test_reads_use_fleet_without_owner(no_threads, requests_mock)
def test_vehicle_list_from_owner_products_when_both_present(no_threads, requests_mock)
    # GET OWNER_API_URL[:-8] + "products" called once; fleet /vehicles not called

def test_commands_use_fleet_only(no_threads, requests_mock):
    # both slots; setChargeRate(10, v) POSTs to FLEET_NA_URL/VIN1/command/set_charging_amps with the Fleet token

def test_command_refused_without_usable_fleet(no_threads, requests_mock):
    # Owner only: setChargeRate, wakeVehicle, car_api_charge, applyChargeLimit, apply_charge_limit
    # make no request (requests_mock.call_count == 0) and record no error time; api.readOnly is True

def test_no_usable_slot_makes_no_requests(no_threads, requests_mock):  # Review Focus 4
    # empty api: car_api_available() is False, vehicle.is_awake() is False, update_vehicle_data() is False,
    # requests_mock.call_count == 0, api.getCarApiLastErrorTime() == 0, api.readOnly is True

def test_refresh_if_needed_refreshes_each_slot_at_its_endpoint(requests_mock):
    # Owner slot (expires in 60s, owner refresh JWT) -> AUTH_TOKEN_URL client_id "ownerapi";
    # Fleet slot (expires in 60s, opaque refresh) -> FLEET_REFRESH_URL client_id "my-client-id"

def test_rejected_refresh_clears_only_that_slot(requests_mock)
def test_get_car_api_expired_401_refreshes_once_and_retries(no_threads, requests_mock):
    # first GET 401 {"error":"token expired"}, refresh 200, second GET 200 -> (True, resp); refresh called once

def test_get_car_api_connection_error_returns_false(no_threads, requests_mock)  # no UnboundLocalError

def test_restore_legacy_sentinel_uses_token_exp(tmp_path):  # Review Focus 2
    # master_with_settings with carApiBearerToken=fleet_token(), carApiTokenExpireTime=99999**3;
    # after loadSettings: api.fleetSlot.expireTime == exp(token)

def test_save_and_load_keep_both_slots(tmp_path)
    # storeToken(owner, "r-o"), storeToken(fleet, "r-f"); saveSettings; new master loads: both slots restored

def test_readonly_property_follows_fleet_slot()
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_slots.py -q`
Expected: FAIL (`AttributeError: 'TeslaAPI' object has no attribute 'storeToken'` or similar)

- [ ] **Step 3: Implement the Interfaces and rewiring above** in `TeslaAPI.py`, `TWCMaster.py`, `TeslaPowerwall2.py`, `HTTPControl.py` and `WebIPCControl.py`.

- [ ] **Step 4: Port the existing tests** using the table. Keep every existing test's intent; delete a test only when its subject was removed (the `SYNCED_TOKEN_EXPIRY` sentinel and `restoreCarApiTokenExpireTime`), and add the replacement assertion next to it.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m pytest tests/unit -q && git grep -n "getCarApiBearerToken\|getCarApiBaseURL\|setCarApiBearerToken\|SYNCED_TOKEN_EXPIRY\|apiRefresh\|readOnlyRefusalLogged" -- lib tests`
Expected: all pass; the grep prints nothing

- [ ] **Step 6: Commit**

```bash
$BLACK lib tests
git add -A lib tests
git commit -m "feat: hold Owner and Fleet API tokens in two slots

Reads use the Owner API token when it is usable and the Fleet token
otherwise; commands use only the Fleet token.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2b: Read-only as a scope (uniform chooser)

Decided with the user after planning (spec §2, "Read-only is a special case of scope"). No behaviour change.

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaTokenSlot.py` (`missingScope`/`usable`), `lib/TWCManager/Vehicle/TeslaAPI.py` (`slotFor`)
- Test: `tests/unit/test_teslatokenslot.py`, `tests/unit/test_teslaapi_token_slots.py`

**Interfaces:**
- Consumes: Task 1 `TeslaTokenSlot`, Task 2 `slotFor`, `readOnly`, `refuseCommandIfReadOnly`.
- Produces:
  - `TeslaTokenSlot.grants(self, purpose: str) -> bool`: Owner kind grants `"read"` and `"energy"` only; Fleet kind grants a purpose when `missingScope(purpose) is None`.
  - `usable(purpose)` uses `grants(purpose)` in place of the scope test. `reportScopeRefused` / the missing-scope ERROR fire only for Fleet tokens; an Owner slot asked for `"command"` returns False silently.
  - `TeslaAPI.slotFor(self, purpose)` becomes exactly: `for slot in (self.ownerSlot, self.fleetSlot): if slot.usable(purpose): return slot` then `return None`.
  - `readOnly` stays `self.slotFor("command") is None` (now meaning "no slot grants commands"). `refuseCommandIfReadOnly` text unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_owner_slot_never_grants_commands_and_logs_nothing(caplog):
    s = owner_slot(); s.setTokens(owner_token())
    assert s.grants("read") and s.grants("energy") and not s.grants("command")
    assert s.usable("command") is False and "scope" not in caplog.text

def test_slot_for_is_uniform_walk():
    # api with owner + fleet tokens: slotFor("read") is ownerSlot, slotFor("energy") is ownerSlot,
    # slotFor("command") is fleetSlot; owner only: slotFor("command") is None and readOnly is True
```

- [ ] **Step 2: Run to verify failure** — `$PY -m pytest tests/unit/test_teslatokenslot.py tests/unit/test_teslaapi_token_slots.py -q`; expected FAIL (`grants` missing).
- [ ] **Step 3: Implement** the Interfaces above.
- [ ] **Step 4: Run to verify pass** — `$PY -m pytest tests/unit -q`; all pass.
- [ ] **Step 5: Commit** — black on touched files; message `refactor: treat read-only as a scope the Owner API slot never grants` with the Co-Authored-By line.

---

### Task 3: Slot-level fallthrough on read failures

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`car_api_available` vehicle-list fetch, `CarApiVehicle.get_car_api`)
- Modify: `lib/TWCManager/EMS/TeslaPowerwall2.py` (`getStormWatch` 403 branch: `reportScopeRefused("energy")`)
- Test: `tests/unit/test_teslaapi_token_slots.py`, `tests/unit/test_teslapowerwall2_ems.py`

**Interfaces:**
- Consumes: `slotFor`, `refreshSlot`, `TeslaTokenSlot.clear/pause/source/refreshToken`.
- Produces: `TeslaAPI.slotRequestFailed(self, slot, response) -> bool`. Returns True only when it refreshed the slot and the caller should retry once. Rules:
  - `response is None` → False.
  - 401 with `"expired"` in the body, `slot.source != "synced"` and a refresh token present → `refreshSlot(slot) == "success"`.
  - any other 401 → ERROR `"Tesla <Owner|Fleet> API token was rejected (HTTP 401); removing it."`, then `slot.clear()`, queue `saveSettings`, return False.
  - 403/410/412 → ERROR `"Tesla <Owner|Fleet> API refused a read (HTTP <code>); not using that token for reads for an hour."`, then `slot.pause()`, return False.
  - anything else → False, with no change.
  - Slot-level failures (clear or pause) don't call `updateCarApiLastErrorTime`, so the next poll can use the other slot at once.

Callers: `get_car_api` (which retries once on True; Task 2's direct 401 "expired" branch is replaced by this), the vehicle-list fetch (checks `req.status_code`, no retry, returns False), and the vehicle-data path only. **Storm Watch does not call `slotRequestFailed`** (an energy-scope 403 must not pause vehicle reads). On a 403 it calls `slot.reportScopeRefused("energy")`, which replaces today's `logger.warn("... does your API token have energy_device_data scope?")`; other errors keep today's handling. It takes its token/URL from `slotFor("energy")` per Task 2.

- [ ] **Step 1: Write the failing tests**

```python
def test_owner_401_clears_owner_and_next_read_uses_fleet(no_threads, requests_mock, caplog):
    # both slots; GET owner vehicle_data -> 401 {"error":"invalid bearer"}
    # first update_vehicle_data() is False; api.ownerSlot.accessToken == ""; ERROR logged
    # second update_vehicle_data() hits FLEET_NA_URL and is True
    # neither token string in caplog.text

def test_owner_412_pauses_for_an_hour_then_returns(no_threads, requests_mock, monkeypatch):
    # owner list /products -> 412; car_api_available() is False; ownerSlot token kept; ownerSlot.pausedUntil ~ now+3600
    # next car_api_available() lists via fleet /vehicles and is True
    # advance time.time by 3600 -> slotFor("read") is api.ownerSlot

def test_new_sync_ends_synced_pause():
    # ownerSlot synced + paused; api.storeToken(owner_token(jti="n"), "", "synced") -> slotFor("read") is ownerSlot

def test_synced_401_expired_clears_without_refresh(requests_mock)  # no POST to AUTH_TOKEN_URL
def test_5xx_and_429_do_not_pause_or_clear(no_threads, requests_mock)  # 503 and 429: slot unchanged
def test_both_paused_no_requests(no_threads, requests_mock)  # Review Focus 4: both paused -> car_api_available False, 0 calls
def test_slot_failure_records_no_api_error(no_threads, requests_mock)  # getCarApiLastErrorTime() == 0 after 412
```

In `test_teslapowerwall2_ems.py`:

```python
def test_storm_watch_403_does_not_pause_slot(requests_mock, caplog):  # Review Focus 3
    # Fleet-only TeslaAPI (token without scp) registered on the Powerwall's master; energy_sites live_status -> 403
    # afterwards api.fleetSlot.usable("read") is True, api.fleetSlot.usable("command") is True, api.readOnly is False
    # exactly one ERROR naming energy_device_data, even after a second poll
def test_storm_watch_skips_request_when_token_lacks_energy_scope(requests_mock):
    # Fleet token scp without energy_device_data: no request to energy_sites, ERROR logged
def test_storm_watch_uses_owner_slot_when_present(requests_mock)  # Authorization header is the Owner token
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_slots.py tests/unit/test_teslapowerwall2_ems.py -q`
Expected: FAIL (new tests)

- [ ] **Step 3: Implement `slotRequestFailed`** and call it from the two vehicle read paths; change Storm Watch's 403 branch to `slot.reportScopeRefused("energy")`.

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m pytest tests/unit -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
$BLACK lib tests
git add lib tests
git commit -m "feat: clear or pause a token slot when Tesla refuses a read

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: TeslaMate sync applies the access token only, by type, and never replaces a user's token

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaMateVehicle.py:199-275` (`fetchLatestTokens`, `doSyncTokens`)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`storeToken` synced branch, `applySyncedTokens` → `applySyncedToken`)
- Modify: `docs/modules/Vehicle_TeslaMate.md:21-24`
- Test: `tests/unit/test_teslamate_token_sync.py`

**Interfaces:**
- Consumes: `storeToken`, `slotOfType`, `TeslaTokenSlot.empty/source/changes`.
- Produces:
  - `TeslaAPI.applySyncedToken(self, accessToken: str) -> str`, which returns `storeToken(accessToken, "", "synced")`'s result. Remove `applySyncedTokens`.
  - `storeToken` synced branch:
    - unknown type → ERROR `"TeslaMate token sync: the token's type (Owner API or Fleet API) was not recognised; not using it."`, returns `"unknown_type"`.
    - target slot not `empty()` and `source in ("pasted", "login")` → `"kept"`. Logs INFO `"TeslaMate token sync: keeping the <Owner|Fleet> API token you <pasted|logged in with>; not replacing it."` only when `slot.changes != self.syncSkipLoggedAt[kind]`, then records it. `syncSkipLoggedAt = {"owner": None, "fleet": None}`.
    - otherwise `setTokens(access, "", None, "synced")` → `"success"`.
  - `TeslaMateVehicle.fetchLatestTokens(conn, cur) -> tuple | None` runs `SELECT access FROM <table> ORDER BY id DESC LIMIT 1`. `doSyncTokens` decrypts only `result[0]`, calls `carapi.applySyncedToken(access_token)`, logs "Successfully synced tokens…" only on `"success"`, and drops every `refresh_token` variable.

- [ ] **Step 1: Write the failing tests.** Update the `fake_db` and `make_teslamate` fixtures: `fetchone` returns `(rows["access"],)`, and `rows` loses `"refresh"`. Then:

```python
def test_refresh_column_neither_selected_nor_decrypted(fake_db):
    # record cur.execute SQL and decrypt_data calls: "refresh" not in SQL; decrypt_data called once with the access value

def test_sync_fills_empty_owner_slot(fake_db)      # ownerSlot.source == "synced", refreshToken == ""
def test_fleet_token_from_teslamate_fills_empty_fleet_slot(fake_db)
def test_sync_replaces_its_own_token(fake_db)      # second sync with jti="2" replaces the accessToken
def test_sync_never_replaces_pasted_or_login(fake_db, caplog):  # parametrize source in ("pasted", "login")
    # slot keeps the user token; three syncs log the INFO exactly once; no token string in caplog.text
def test_unknown_synced_token_skipped_with_error(fake_db, caplog)
def test_healing_cleared_slot_refilled_by_next_sync(fake_db)
    # pasted owner token; ownerSlot.clear() (as a 401 would); sync -> ownerSlot.source == "synced"
def test_sync_beside_fleet_login(fake_db)
    # fleetSlot holds a login token; Owner sync fills ownerSlot; fleetSlot unchanged; readOnly is False
```

Port `TestHourlyResync`, `TestNoRefreshForSyncedTokens` and `TestSettingsLoadWhileSyncOn` to single-column rows. `TestSettingsLoadWhileSyncOn` asserts `refreshToken == ""` and the token's `exp`.

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** the Interfaces above. Rewrite `Vehicle_TeslaMate.md` lines 21–24 to say: sync copies TeslaMate's access token only, into the Owner or Fleet slot by type; it never replaces a token you pasted or logged in with; TWCManager doesn't refresh synced tokens; you can still log in with the Fleet API while sync is on.

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m pytest tests/unit -q && git grep -n "applySyncedTokens\|refresh_token" -- lib/TWCManager/Vehicle/TeslaMateVehicle.py`
Expected: all pass; the grep prints nothing

- [ ] **Step 5: Commit**

```bash
$BLACK lib tests
git add lib docs tests
git commit -m "feat: TeslaMate sync fills the matching token slot with the access token only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Saved token sources, one-time migration, and load regardless of sync

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`migrateSavedTokens`, `restoreSlot`)
- Modify: `lib/TWCManager/TWCMaster.py` (`loadSettings` step 2, `saveSettings` step 1)
- Modify: `CHANGELOG.md` (main: under `## v1.4.0 - Upcoming`; the port moves it to the v1.3.4 section)
- Test: create `tests/unit/test_teslaapi_token_migration.py`; adjust `TestSettingsLoadWhileSyncOn` / `TestSettingsLoadAfterSyncTurnedOff` in `test_teslamate_token_sync.py`

**Interfaces:**
- Consumes: `restoreSlot`, `classifyToken`, `refreshTokenType`, `LEGACY_SYNCED_EXPIRY`, `TeslaTokenSlot.empty`.
- Produces:
  - Settings keys `carApiTokenSource` and `ownerApiTokenSource`, whose values are in `SOURCES`, or `""` when the slot is empty. `saveSettings` writes them from `slot.source`.
  - `TeslaAPI.migrateSavedTokens(self, settings: dict, syncOn: bool) -> bool` mutates `settings` and returns True if it changed anything. Rules:
    - Nothing to do when `carApiBearerToken` and `carApiRefreshToken` are both empty, or when `carApiTokenSource` is already present (that means already migrated: idempotent).
    - The type comes from the access token, or from `refreshTokenType` when only a refresh token is saved.
    - `synced` is `carApiTokenExpireTime == LEGACY_SYNCED_EXPIRY` or (`syncOn` and type is owner). For any type, `synced` means the saved refresh token is dropped (it is TeslaMate's) and the source is `synced`; otherwise the source is `pasted`.
    - Owner: copy to the `ownerApi*` keys, overwriting them, and set `ownerApiTokenSource`. Clear `carApi*` to `""`/`""`/`0` and set `carApiTokenSource = ""`.
    - Fleet: stays; set `carApiTokenSource`. Nothing records a Fleet login, so `login` is never inferred.
    - Unknown: stays; set `carApiTokenSource`. The ERROR comes from `tokenRoute` when the slot is restored.
  - `restoreSlot` gains one rule: a saved `source == "synced"` does not overwrite a slot that is already non-empty, because the startup sync, which runs before `loadSettings`, filled it with a fresher token. A saved `pasted` or `login` token does overwrite.
  - `loadSettings` step 2, always (the sync skip goes): `migrateSavedTokens(self.settings, self.tokenSyncEnabled())`, then `restoreSlot` for the Fleet slot and the Owner slot with their source keys (missing → `"pasted"`).

- [ ] **Step 1: Write the failing tests** (`master_with_settings` from `test_teslamate_token_sync.py`):

```python
def test_owner_token_moves_to_owner_slot(tmp_path)
    # carApi* = owner_token(), "r1"; sync off -> ownerSlot token + "r1", source "pasted"; fleetSlot empty; settings carApi* cleared
def test_fleet_token_stays(tmp_path)       # fleetSlot holds it, source "pasted"; ownerApi* untouched
def test_unknown_token_stays_with_error(tmp_path, caplog)  # fleetSlot.accessToken == token, tokenType "unknown", ERROR
def test_synced_fleet_or_unknown_token_drops_refresh(tmp_path)  # parametrize fleet/unknown + 99999**3: refreshToken "", source "synced"
def test_refresh_only_owner_routed_by_refresh_type(tmp_path)  # carApiBearerToken "", owner refresh JWT -> ownerApiRefreshToken
def test_migration_is_idempotent()
    # migrateSavedTokens(s, False) True; copy; second call False and s unchanged
def test_synced_owner_marked_and_refresh_dropped_when_sync_on(tmp_path, fake_db)
    # live box: carApi* = owner token, "teslamate-refresh", 99999**3; startup sync registered first
    # -> ownerSlot.source "synced", refreshToken "", fresh sync token kept (saved synced token didn't overwrite it)
def test_sentinel_marks_synced_when_sync_off_at_load(tmp_path):  # Review Focus 1
    # same settings, no TeslaMate module -> ownerSlot.source "synced", refreshToken "", expireTime == exp(token);
    # refreshTokenIfNeeded() makes no request
def test_saved_pasted_token_wins_over_startup_sync(tmp_path, fake_db)
    # ownerApi* pasted token saved; startup sync put another owner token first -> pasted one restored
def test_owner_key_overwritten_by_newer_carapi_owner_token(tmp_path)
    # both ownerApi* (old) and carApi* (owner, newer) present, no carApiTokenSource -> ownerApi* = carApi* token
def test_sources_round_trip_through_save(tmp_path)
```

Rewrite `TestSettingsLoadWhileSyncOn` as "saved synced token doesn't replace the startup sync; saved pasted one does". `TestSettingsLoadAfterSyncTurnedOff` now asserts slot fields.

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_migration.py tests/unit/test_teslamate_token_sync.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** the Interfaces. Add a CHANGELOG entry: *"Keep an Owner API token and a Fleet API token at once: reads use the free Owner API when possible, commands use the Fleet API, and TeslaMate token sync can stay on beside a Fleet login. Settings migrate automatically on first start; downgrading afterwards loses the Owner API token (stored under new `ownerApi*` keys)."*

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m pytest tests/unit -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
$BLACK lib tests
git add lib tests CHANGELOG.md
git commit -m "feat: migrate a saved Owner API token to its own slot and save each slot's source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Paste routing, synced-slot protection, Remove token, slot status on the settings page

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`storeToken` non-synced branch, `savePastedToken`, `pasteRefreshToken`, `fleetTokenExchange`, new `syncedSlotLocked`, `removeToken`)
- Modify: `lib/TWCManager/Control/HTTPControl.py` (GET webroutes ~1171, `do_POST` ~1426, `process_save_settings`)
- Modify: `lib/TWCManager/Control/themes/Default/settings.html.j2:186-201`, `handle_teslalogin.html.j2`
- Test: create `tests/unit/test_teslaapi_token_paste.py`; port `TestSettingsPageWhileSyncOn` (`test_teslamate_token_sync.py`), `TestLoginWhileTokenSyncOn` (`test_teslaapi_fleetlogin.py`) and the `token_sync` page test in `test_teslaapi_refresh.py`

**Interfaces:**
- Consumes: `storeToken`, `slotOfType`, `refreshTokenType`, `TeslaTokenSlot.status/empty/clear`.
- Produces:
  - `TeslaAPI.syncedSlotLocked(self, slot) -> bool`: `master.tokenSyncEnabled() and slot.source == "synced" and not slot.empty()`. The one place the §6 refusal rule lives.
  - `storeToken` non-synced branch: `syncedSlotLocked(target)` → WARNING `"Tesla API token not stored: TeslaMate token sync manages the <Owner|Fleet> API token. Remove that token on the Settings page, or turn off syncTokens, to replace it."` and returns `"token_sync"`. Otherwise it stores. The Task 2 blanket sync refusal goes.
  - `savePastedToken(token)`: a JWT whose `classifyToken` is unknown and whose `iss` isn't the Owner issuer returns `"unknown_type"` with nothing stored. A non-JWT is still a Fleet refresh token (PR 2). The access field on the settings form follows the same rule through `storeToken`.
  - `pasteRefreshToken(token)`: returns `"token_sync"` with no change when `syncedSlotLocked(target)`.
  - `fleetTokenExchange`: refuses with `"token_sync"` *before* the exchange only when `syncedSlotLocked(self.fleetSlot)`.
  - `TeslaAPI.removeToken(self, kind: str) -> bool`: clears `ownerSlot` or `fleetSlot` (synced ones included), queues `saveSettings`, and returns False for any other `kind`.
  - HTTP: `POST /teslaAccount/removeToken` with field `slot` (`owner` or `fleet`) → `removeToken` → 302 to `/settings`. Add `{"route": "/teslaAccount/removeToken", "error": "insecure"}` to the GET webroutes.
  - `handle_teslalogin.html.j2`:
    - new `/teslaAccount/unknown_type` branch: "TWCManager could not recognise this token as an Owner API or Fleet API token. Nothing was stored."
    - `token_sync` text becomes: "TeslaMate token sync manages the token slot this token belongs to, so it was not stored. To replace TeslaMate's token, remove it on the Settings page, or turn off syncTokens in the TeslaMate module's config."
    - the line-66 gate becomes `{% set carapi = master.getModuleByName("TeslaAPI") %}{% if carapi and not carapi.syncedSlotLocked(carapi.fleetSlot) and url.path != "/teslaAccount/success" %}`.
  - `settings.html.j2`: above the manual override row, add one row per slot ("Owner API token", "Fleet API token"). Each shows "none" or `expires <status.expires>` and the source label (`synced` → "synced from TeslaMate", `pasted` → "pasted", `login` → "Fleet API login"), plus "paused for reads" when `status.paused`, and a Remove token button when `holdsToken`. The buttons use `form="removeToken-owner"` / `form="removeToken-fleet"`, which point at two small `<form method=post action=/teslaAccount/removeToken>` elements with a hidden `slot` input. Those forms sit after the main settings `</form>`, because forms can't nest. Guard everything with `{% if carapi %}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_paste_routes_by_type_and_leaves_other_slot():
    # fleetSlot holds a login token; savePastedToken(owner_token()) == "success"; fleetSlot unchanged
def test_unknown_jwt_paste_refused():  # savePastedToken(make_jwt(aud=["x"])) == "unknown_type"; both slots empty
def test_refresh_token_alone_routed_by_type(requests_mock)
    # owner refresh JWT -> AUTH_TOKEN_URL, fills ownerSlot; opaque -> FLEET_REFRESH_URL, fills fleetSlot
def test_paste_over_synced_refused_while_sync_on(requests_mock)
    # ownerSlot synced, sync on: savePastedToken(owner_token(jti="u")) == "token_sync"; settings form posts
    # -> Location /teslaAccount/token_sync; ownerSlot unchanged; no HTTP call
def test_paste_into_other_slot_allowed_while_sync_on()
    # ownerSlot synced, sync on: savePastedToken(fleet_token()) == "success"
def test_paste_over_expired_synced_allowed()  # synced token past exp counts as empty
def test_paste_over_synced_allowed_when_sync_off()
def test_remove_token_clears_slot_and_saves()  # removeToken("owner") True; ownerSlot empty; saveSettings queued; removeToken("x") False
def test_remove_token_route(...)  # POST slot=fleet -> fleetSlot empty, 302 /settings
def test_fleet_login_allowed_while_sync_on_and_fleet_slot_free(requests_mock):  # Review Focus 5
    # sync on, ownerSlot synced, fleetSlot empty: fleetTokenExchange(code, state) == "success", fleetSlot.source "login";
    # login page renders the request_teslalogin form
def test_fleet_login_refused_before_exchange_when_fleet_slot_synced(requests_mock)  # token endpoint not called
def test_settings_page_shows_slot_status()
    # render settings.html.j2 with synced owner + login fleet: contains "synced from TeslaMate", "Fleet API login", two removeToken forms
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_paste.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** the Interfaces. Port the three existing sync-refusal test classes to the per-slot rule.

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m pytest tests/unit -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
$BLACK lib tests
git add lib tests
git commit -m "feat: route pasted tokens by type, protect synced slots, add Remove token

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Port to 1.3.4

**Files:** the same as Tasks 1–6, on `port-token-slots-1.3.4`. The 1.3.4 differences, task by task:

| Task | Do 1.3.4 differences matter? |
|---|---|
| 1 | No. New files only; the refresh endpoint is injected. |
| 2 | **Yes.** (a) 1.3.4's `refreshToken` has `myRefreshURL = self.authTokenURL if self.usePKCE() else self.fleetRefreshURL`. Resolve the conflict by deleting `refreshToken` and building `fleetSlot` with `refreshURL = self.authTokenURL if self.usePKCE() else self.fleetRefreshURL` (still `requests.post`, Fleet `clientID`). (b) `is_awake`/`update_vehicle_data` hunks sit next to code 1.3.4 lacks (`gpsAsOf`, `scheduledChargingPending`); keep 1.3.4's lines and apply only the slot changes. (c) No `TeslaAPIEVSE`/`TeslaAPIController` and no `TestTeslaAPIEVSE` on 1.3.4: drop those hunks. (d) 1.3.4's `test_teslaapi_refresh.py` wraps `new_api` with a client secret and has `test_public_client_fleet_refresh_request`. Port that test to the slot API: a PKCE Fleet slot refreshes at `AUTH_TOKEN_URL` with `client_id` `my-client-id`, not through `session.post`. `fleetSlot.refreshURL` is fixed in `__init__`, so a 1.3.4 test that sets `api.clientSecret` after construction (`TestRejectedPasteKeepsTokens.working_api`) must pass it through the config instead (`teslaApiClientSecret` in `new_api(...)` / `master_with_settings`). (e) `TWCMaster` offsets (~940, ~1328). BLE: 1.3.4 has no BLE read path, and the slot code doesn't touch BLE, so there's nothing to backport or remove. |
| 3 | Possibly. `TeslaPowerwall2.py` differs near line 271 (the 403 branch); keep 1.3.4's lines and apply the `reportScopeRefused("energy")` change (Storm Watch never calls `slotRequestFailed`). |
| 4 | No. `TeslaMateVehicle.py` and the TeslaMate doc are the same on both branches. |
| 5 | Minor. Move the CHANGELOG entry under `## v1.3.4`; `TWCMaster` offsets. |
| 6 | Minor. `settings.html.j2` lacks the commandPolicy row (line 124 on main); the token row anchor is unchanged. `WebIPCControl` differs only in the ExistentialError block. |

- [ ] **Step 1: Create the branch and record the baseline**

```bash
git -C /home/mbishop/github/TWCManager worktree add -b port-token-slots-1.3.4 <port-path> port-owner-api-refresh-1.3.4
cd <port-path>; $PY -m pytest tests/unit -q -p no:randomly 2>&1 | grep '^FAILED' | sort > <scratch>/baseline-failed.txt; wc -l < <scratch>/baseline-failed.txt
```
Expected: `62`

- [ ] **Step 2: Cherry-pick Tasks 1–6 in order**, one at a time: `git cherry-pick -x <sha>`. Resolve each per the table. After each one, run `$BLACK --check lib tests` and `$PY -m pytest tests/unit/test_teslatokenslot.py tests/unit/test_teslaapi_*.py tests/unit/test_teslamate_token_sync.py tests/unit/test_teslapowerwall2_ems.py -q`. Expected: no new failures in those files beyond the ones listed in the baseline. If you adapt a commit, amend it with a `[1.3.4: …]` line under the `-x` trailer that says what changed.

- [ ] **Step 3: Compare the failure set**

```bash
$PY -m pytest tests/unit -q -p no:randomly 2>&1 | grep '^FAILED' | sort > <scratch>/after-failed.txt
diff <scratch>/baseline-failed.txt <scratch>/after-failed.txt && wc -l < <scratch>/after-failed.txt
```
Expected: no diff output; `62`

No PRs are opened by this plan. The user opens them and doesn't self-merge.
