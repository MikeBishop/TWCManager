# TeslaMate Token Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TeslaMate token sync work again: accept every hourly resync, classify each token by `aud` before `ou_code` so Owner API tokens go to owner-api (read-only), and stop vehicle commands while the token is read-only. Land it on `main`, then port it to `release/1.3.4` (all three changes) and `release/1.3.3` (sync acceptance only).

**Architecture:** All token handling stays in `TeslaAPI` (`lib/TWCManager/Vehicle/TeslaAPI.py`). A new `applySyncedTokens()` is the sync route past the `tokenSyncEnabled()` refusal. A new `classifyToken()`/`applyTokenClassification()` pair runs on every accepted token and sets `baseURL`, `verifyCert` and a new `readOnly` flag, using a remembered `proxyURL`/`proxyCert`. A new `refuseCommandIfReadOnly()` guards every TeslaAPI command entry point. `VehiclePriority` skips any module whose `readOnly is True` for its `COMMAND_METHODS`, and `TeslaAPIEVSE.isReadOnly` follows `TeslaAPI.readOnly`.

**Tech Stack:** Python 3, PyJWT 2.x (`jwt.decode` with `verify_signature: False`), `requests`, pytest with `requests-mock` (fixture `requests_mock`, module `requests_mock` for `ANY`) and `caplog`. Formatting: black (CI runs `black --exclude="setup.py|tests/*" --check .`).

**Spec:** `.superpowers/specs/2026-10-10-teslamate-token-sync-design.md` (binding). Background: `.superpowers/unified-integrations-proposal.md` sections 3, 5 and the 2026-10-10 addendum.

## Global Constraints

- Development branch `fix/teslamate-token-sync`, created from `origin/main` (0b7d143 when this plan was written). Port branches: `port-teslamate-token-sync-1.3.4` from `origin/release/1.3.4`, `port-teslamate-token-sync-1.3.3` from `origin/release/1.3.3`.
- Test command (run from the repository root): `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python -m pytest tests/unit -q`. Below this is written `$PY -m pytest ...`, where `PY` is that interpreter path. Set it once per shell: bash `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python`; fish `set PY /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python`.
- Baselines: `origin/main` gives `451 passed`. `release/1.3.4` gives `62 failed, 373 passed`; `release/1.3.3` gives `62 failed, 363 passed`. The 62 release failures are pre-existing; a port task must not add a failure.
- Never log a token. Classification logs at INFO name the token type, the base URL host and read-only, nothing else.
- Unknown token type: `baseURL = ""`, one ERROR line, `readOnly = False`, token still stored. *(Decided by the user 2026-10-10: error rather than default to the Owner API.)*
- While sync is on, TWCManager never refreshes a token: the sync sets the "never expires" sentinel `99999 * 99999 * 99999`, and `setCarApiRefreshToken` still skips refresh. The sentinel is one named constant, `TeslaAPI.SYNCED_TOKEN_EXPIRY`, used both where the sync sets it and where settings load reads it back.
- If settings load finds the sentinel while sync is **off**, the expiry is taken from the stored bearer token's `exp` (decoded with no signature check). If that can't be decoded, it is `time.time()`, so a normal refresh or re-login follows.
- Read-only refusals: return the method's usual failure value (`False` or `"error"`), make no HTTP call, record no API error time, and log at INFO once per change of read-only state.
- Put new tests in new files: `tests/unit/teslatokens.py` (helpers), `tests/unit/test_teslamate_token_sync.py`, `tests/unit/test_teslaapi_token_classification.py` and `tests/unit/test_teslaapi_readonly_gate.py`. Do not append to `tests/unit/test_vehicle_priority.py` or `tests/unit/test_teslaapi_fleetlogin.py`, which differ between branches and would make the cherry-picks conflict.
- Run black on every touched `lib/` file. `release/1.3.4` and `release/1.3.3` `TeslaAPI.py` are already not black-clean (one pre-existing line in `CarApiVehicle.is_awake` on 1.3.4, and more on 1.3.3). Don't reformat them in the port.
- Every commit message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. That is the model writing this plan. An executor running on a different model puts its own model name in place of `Opus 5.5`.
- Don't push or open PRs unless the user asks. Task 6 holds the PR text.

## File map

| File | Responsibility | Tasks |
|---|---|---|
| `lib/TWCManager/Vehicle/TeslaAPI.py` | token acceptance, classification, read-only gate | 1, 2, 3 |
| `lib/TWCManager/Vehicle/TeslaMateVehicle.py` | `doSyncTokens` calls `applySyncedTokens` | 1 |
| `lib/TWCManager/Vehicle/VehiclePriority.py` | skip read-only modules for command methods | 3 |
| `lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py` | `isReadOnly` follows `TeslaAPI.readOnly` (main only) | 3 |
| `tests/unit/teslatokens.py` | JWT builders, `FakeMaster`, `new_api` | 1 (used by 2, 3) |
| `tests/unit/test_teslamate_token_sync.py` | sync acceptance, no refresh | 1 |
| `tests/unit/test_teslaapi_token_classification.py` | classification, base URL sites | 2 |
| `tests/unit/test_teslaapi_readonly_gate.py` | command gate | 3 |

## Every place `baseURL`, `regionURL` or `verifyCert` is read or written on origin/main

Task 2 changes or checks each of these. Line numbers are at `origin/main`.

| Site | Use | Result after this plan |
|---|---|---|
| `TeslaAPI.py:18` `baseURL = ""` | class default | unchanged |
| `TeslaAPI.py:19-23` `regionURL` | Fleet regions | gains `"OwnerAPI"`; every Fleet-only use goes through new `fleetRegions()` |
| `TeslaAPI.py:93-96` `__init__` | sets `baseURL`/`verifyCert` from `teslaProxy`/`teslaProxyCert` | also stored as `self.proxyURL`/`self.proxyCert`, so classification can restore them |
| `TeslaAPI.py:255` `car_api_available` vehicle list GET | reads `self.baseURL` | guarded: returns False with no request when `baseURL` is `""` (otherwise `requests.get("")` raises MissingSchema and records an API error) |
| `TeslaAPI.py:718` `car_api_charge` command URL | reads | gated by `readOnly` (Task 3); reached only after `car_api_available`, which has the empty guard |
| `TeslaAPI.py:1072` `getCarApiBaseURL` | accessor | unchanged; all readers below go through it |
| `TeslaAPI.py:1137-1141` `regionAudience` | `regionURL.get(region, NA)` | uses `fleetRegions()`, so `"OwnerAPI"` can never become a login audience |
| `TeslaAPI.py:1155` `teslaLoginInfo()["regions"]` | Settings/login region dropdown | `fleetRegions()`, so the UI never offers `OwnerAPI` |
| `TeslaAPI.py:1164` `getLoginURL` region validation | `region not in regionURL` | `region not in fleetRegions()` |
| `TeslaAPI.py:1219-1220` comment in `fleetTokenExchange` | describes ou_code-only derivation | comment updated |
| `TeslaAPI.py:1281-1289` `setCarApiBearerToken` | classified only `if not self.baseURL` (first token only, and never when `teslaProxy` is set) | every token classified (`applyTokenClassification`) |
| `TeslaAPI.py:1340` `setChargeRate` | reads | gated by `readOnly` (Task 3) and the empty guard (Task 2) |
| `TeslaAPI.py:1453` `wakeVehicle` | reads | gated by `readOnly` (Task 3) and the empty guard (Task 2). Without the guard, its `except` reads `req.status_code` with `req` unbound |
| `TeslaAPI.py:1501, 1547` `CarApiVehicle.verifyCert` | copied from `teslaProxyCert` once | becomes a property that returns `self.carapi.verifyCert`, so it follows the token (owner-api must not be verified against the proxy's certificate) |
| `TeslaAPI.py:1633` `CarApiVehicle.is_awake` | `getCarApiBaseURL()/VIN` | goes through `get_car_api`, which gets the empty guard |
| `TeslaAPI.py:1640` `CarApiVehicle.get_car_api` | GET | empty guard: `return False, None`, no request, no error time (otherwise its `except` reads `req.status_code` with `req` unbound) |
| `TeslaAPI.py:1654, 1967` `verify=self.verifyCert` | per-vehicle | now the property above |
| `TeslaAPI.py:1782` `update_vehicle_data` | read URL | unchanged; owner-api serves `/api/1/vehicles/<VIN>/vehicle_data` (1.3.3 does this today) |
| `TeslaAPI.py:1955` `CarApiVehicle.apply_charge_limit` | command URL | gated by `readOnly` (Task 3) |
| `EMS/TeslaPowerwall2.py:243, 258, 292` `getStormWatch` | `baseURL.replace("vehicles", "products"/"energy_sites")` | no change. Owner URL → owner-api `/products` and `/energy_sites` (the 1.3.3 behaviour). Fleet → as today. `""` → `httpSession.get("")` raises inside its `try ... except Exception`, which logs a warning. It also needs `now < getCarApiTokenExpireTime()`, so the sync sentinel (Task 1) matters to it |
| `Control/HTTPControl.py:1731` Settings save | `setCarApiBearerToken(field)` | still refused while sync is on; otherwise classified |
| `TWCMaster.py:1099` `loadSettings` | `setCarApiBearerToken(saved)` at startup, after modules load (`TWCManager.py:796`) | refused while sync is on (TeslaMate is registered by then); otherwise classified |
| `TWCMaster.py:1101` `loadSettings` | `setCarApiTokenExpireTime(saved)` | now `restoreCarApiTokenExpireTime(saved)` (Task 1): a saved sentinel is kept only while sync is on |
| `vehicleOnlineStates` | — | **not present on origin/main** (`git grep vehicleOnlineStates origin/main` is empty). Nothing to change |

Pre-existing issues seen while mapping, **out of scope** (mention them only): `CarApiVehicle.get_car_api` calls `self.apiRefresh()` (`TeslaAPI.py:1665`), which `CarApiVehicle` doesn't have. `apiRefresh`'s 401 path calls `setCarApiBearerToken("")`, which returns False without clearing the token. `loadSettings` runs after the startup sync, so it puts back the saved refresh token and expiry until the next hourly resync.

---

### Task 0: Create the development branch

**Files:** none.

**Interfaces:**
- Consumes: nothing.
- Produces: branch `fix/teslamate-token-sync` at `origin/main`.

- [ ] **Step 1: Fetch and branch**

Run from the TWCManager clone (a worktree that has no other branch checked out there):

```bash
git fetch origin
git switch -c fix/teslamate-token-sync origin/main
```

- [ ] **Step 2: Confirm the baseline**

Run: `$PY -m pytest tests/unit -q`
Expected: `451 passed` (one warning). If the count differs, `origin/main` has moved. Record the new number and use it in place of 451 below; each task adds the test counts listed for it.

---

### Task 1: Reproduce the hourly-resync refusal, then accept synced tokens

The bug: `TeslaMateVehicle.doSyncTokens` sets tokens through `TeslaAPI.setCarApiBearerToken`, which returns False once `master.tokenSyncEnabled()` is true. That is true after `TeslaMateVehicle` is registered, i.e. for every hourly `resyncTokens`, and the return value is ignored. Two more defects are on the same path:
- **Sentinel order.** `doSyncTokens` sets the expiry sentinel *before* `setCarApiBearerToken`, which overwrites it with the JWT's decoded `exp`.
- **Startup refresh.** On the startup sync, `tokenSyncEnabled()` is still False (the module is not registered yet). So `setCarApiRefreshToken` can start a TWCManager refresh of TeslaMate's token, at the Fleet auth host with `teslaApiClientID`.

Also, `wakeVehicle` calls `apiRefresh()` on a 401 without checking sync. The fix adds a sync route and keeps all refresh off while sync is on.

Once the sentinel sticks, `saveSettings` writes it to settings.json. If the user later turns sync off, `TWCMaster.loadSettings` would put back a token that never expires and so is never refreshed. So settings load now goes through `TeslaAPI.restoreCarApiTokenExpireTime`, which keeps a saved sentinel only while sync is on. Otherwise it uses the stored token's `exp`, or `time.time()` if the token can't be decoded.

**Files:**
- Create: `tests/unit/teslatokens.py`
- Create: `tests/unit/test_teslamate_token_sync.py`
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:49` (class constant), `:142-143` (`apiRefresh` head), `:1265-1269` (`setCarApiBearerToken` head), `:1319-1321` (add `restoreCarApiTokenExpireTime` and `applySyncedTokens` after `setCarApiTokenExpireTime`)
- Modify: `lib/TWCManager/Vehicle/TeslaMateVehicle.py:230-235`
- Modify: `lib/TWCManager/TWCMaster.py:1101` (`loadSettings` expiry restore)

**Interfaces:**
- Consumes: `TWCMaster.tokenSyncEnabled() -> bool` (unchanged; True when the `TeslaMateVehicle` module is registered with `syncTokens` true).
- Produces:
  - `TeslaAPI.SYNCED_TOKEN_EXPIRY = 99999 * 99999 * 99999` (class constant, int)
  - `TeslaAPI.setCarApiBearerToken(self, token=None, fromSync=False) -> bool`: refuses (returns False) only when `tokenSyncEnabled()` and not `fromSync`
  - `TeslaAPI.applySyncedTokens(self, accessToken: str, refreshToken: str) -> bool`: sets the bearer token with `fromSync=True`, stores the refresh token without refreshing, then sets `SYNCED_TOKEN_EXPIRY`
  - `TeslaAPI.apiRefresh(self) -> bool`: returns False with no HTTP call while `tokenSyncEnabled()`
  - `TeslaAPI.restoreCarApiTokenExpireTime(self, value) -> bool`: the settings-load setter. When `value == SYNCED_TOKEN_EXPIRY` and sync is off, it stores the bearer token's `exp` (or `time.time()` if undecodable); otherwise it stores `value`. Called from `TWCMaster.loadSettings`
  - Test helpers in `tests/unit/teslatokens.py`: `make_jwt(**claims) -> str`, `owner_token(expires_in=28800, **extra) -> str`, `fleet_token(expires_in=28800, **extra) -> str`, `FakeMaster(**config_overrides)` (attributes `config`, `settings`, `modules`, `tasks`, `stats`; methods `getModuleByName`, `tokenSyncEnabled`, `queue_background_task`, `getHomeLatLon`), `new_api(master=None, **config_overrides) -> TeslaAPI` (registers the API as `master.modules["TeslaAPI"]`, clears class-level token and vehicle state), constants `OWNER_AUD`, `FLEET_AUD`, `FLEET_REFRESH_URL`, `AUTH_TOKEN_URL`, `SIGNING_KEY`.

- [ ] **Step 1: Write the test helpers**

Create `tests/unit/teslatokens.py`:

```python
"""
Shared helpers for the TeslaAPI token tests.

Builds JWTs shaped like the tokens TWCManager sees in the field, and a small
master stand-in whose tokenSyncEnabled() follows the TeslaMate module the way
TWCMaster.tokenSyncEnabled() does.
"""

import time

import jwt

SIGNING_KEY = "unit-test-signing-key-0123456789abcdef"

OWNER_AUD = [
    "https://auth.tesla.com/oauth2/v3/userinfo",
    "https://owner-api.teslamotors.com/",
]
FLEET_AUD = [
    "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "https://fleet-api.prd.eu.vn.cloud.tesla.com",
]

FLEET_REFRESH_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
AUTH_TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"


def make_jwt(**claims):
    """Encode claims as an HS256 JWT. TeslaAPI never verifies the signature."""
    return jwt.encode(claims, SIGNING_KEY, algorithm="HS256")


def owner_token(expires_in=8 * 60 * 60, **extra):
    """A live-shaped TeslaMate access token: Owner API aud, azp ownerapi,
    and (as observed live on 2026-10-10) an ou_code of NA."""
    claims = {
        "iss": "https://auth.tesla.com/oauth2/v3",
        "aud": OWNER_AUD,
        "azp": "ownerapi",
        "scp": ["email", "offline_access", "openid"],
        "ou_code": "NA",
        "exp": int(time.time() + expires_in),
    }
    claims.update(extra)
    return make_jwt(**claims)


def fleet_token(expires_in=8 * 60 * 60, **extra):
    """A Fleet API access token as issued to a registered third-party app."""
    claims = {
        "iss": "https://auth.tesla.com/oauth2/v3/nts",
        "aud": FLEET_AUD,
        "azp": "my-client-id",
        "scp": ["openid", "offline_access", "vehicle_device_data", "vehicle_cmds"],
        "ou_code": "NA",
        "exp": int(time.time() + expires_in),
    }
    claims.update(extra)
    return make_jwt(**claims)


class FakeMaster:
    """Just enough of TWCMaster for TeslaAPI and TeslaMateVehicle."""

    def __init__(self, **config_overrides):
        cfg = {"teslaApiClientID": "my-client-id"}
        cfg.update(config_overrides)
        self.config = {"config": cfg, "vehicle": {"teslaAPI": {"enabled": True}}}
        self.settings = {}
        self.modules = {}
        self.tasks = []
        self.stats = {"moduleSuccess": {}, "moduleFailures": {}}

    def getModuleByName(self, name):
        return self.modules.get(name)

    def tokenSyncEnabled(self):
        # Mirrors TWCMaster.tokenSyncEnabled()
        teslamate = self.modules.get("TeslaMateVehicle")
        return bool(teslamate and teslamate.syncTokens)

    def queue_background_task(self, task):
        self.tasks.append(task)

    def getHomeLatLon(self):
        return (37.0, -122.0)


def new_api(master=None, **config_overrides):
    """A TeslaAPI registered on a FakeMaster, with no inherited class state."""
    from TWCManager.Vehicle.TeslaAPI import TeslaAPI

    master = master or FakeMaster(**config_overrides)
    api = TeslaAPI(master)
    api.carApiBearerToken = ""
    api.carApiRefreshToken = ""
    api.carApiVehicles = []
    master.modules["TeslaAPI"] = api
    return api
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_teslamate_token_sync.py`:

```python
"""
TeslaMate token sync: tokens pushed by TeslaMateVehicle.doSyncTokens must be
accepted on every sync, not only the first one, and TWCManager must never
refresh a synced token itself (TeslaMate owns the refresh).
"""

import time
from unittest.mock import Mock

import pytest

from tests.unit.teslatokens import (
    AUTH_TOKEN_URL,
    FLEET_REFRESH_URL,
    FakeMaster,
    new_api,
    owner_token,
)

# The "never expires" sentinel TeslaMateVehicle.doSyncTokens has always set,
# so that TWCManager never refreshes a token TeslaMate owns.
SYNCED_EXPIRY = 99999 * 99999 * 99999


def make_teslamate(master, access, refresh, registered=True):
    """A TeslaMateVehicle wired to a fake TeslaMate database.

    Built with __new__ so __init__ does not start MQTT or the hourly
    resync Timer. registered=True puts it in master.modules, which is what
    makes master.tokenSyncEnabled() return True.
    """
    from TWCManager.Vehicle.TeslaMateVehicle import TeslaMateVehicle

    tm = TeslaMateVehicle.__new__(TeslaMateVehicle)
    tm.master = master
    tm.syncTokens = True
    tm._TeslaMateVehicle__db_host = "db"
    tm._TeslaMateVehicle__db_name = "teslamate"
    tm._TeslaMateVehicle__db_user = "teslamate"
    tm._TeslaMateVehicle__db_pass = "secret"
    tm.encryption_key = "key"
    tm.rows = {"access": access, "refresh": refresh}
    # The fake database stores plaintext; decryption is the identity.
    tm.decrypt_data = lambda data: data
    if registered:
        master.modules["TeslaMateVehicle"] = tm
    return tm


@pytest.fixture
def fake_db(monkeypatch):
    """Patch psycopg2.connect to return the current tm.rows."""
    import TWCManager.Vehicle.TeslaMateVehicle as tmmod

    state = {"tm": None}

    def connect(**kwargs):
        conn = Mock()
        rows = state["tm"].rows
        conn.cursor.return_value.fetchone.return_value = (
            rows["access"],
            rows["refresh"],
        )
        return conn

    monkeypatch.setattr(tmmod.psycopg2, "connect", connect)
    return state


@pytest.fixture
def refresh_endpoints(requests_mock):
    """Mock both token endpoints so a refresh attempt is observable."""
    body = {"access_token": "X", "refresh_token": "Y", "expires_in": 28800}
    return [
        requests_mock.post(FLEET_REFRESH_URL, json=body),
        requests_mock.post(AUTH_TOKEN_URL, json=body),
    ]


class TestHourlyResync:
    def test_resync_after_registration_replaces_bearer_token(self, fake_db):
        master = FakeMaster()
        api = new_api(master)
        first, second = owner_token(), owner_token(jti="rotated")
        tm = make_teslamate(master, first, "refresh-1", registered=False)
        fake_db["tm"] = tm

        # Startup sync runs from TeslaMateVehicle.__init__, before the
        # module is registered, so tokenSyncEnabled() is still False.
        tm.doSyncTokens(True)
        assert api.getCarApiBearerToken() == first

        # The module is now registered; this is what resyncTokens() sees.
        master.modules["TeslaMateVehicle"] = tm
        assert master.tokenSyncEnabled() is True
        tm.rows = {"access": second, "refresh": "refresh-2"}
        tm.doSyncTokens()

        assert api.getCarApiBearerToken() == second
        assert api.getCarApiRefreshToken() == "refresh-2"

    def test_hand_entered_token_still_refused_while_sync_on(self, fake_db):
        master = FakeMaster()
        api = new_api(master)
        synced = owner_token()
        fake_db["tm"] = make_teslamate(master, synced, "refresh-1")
        fake_db["tm"].doSyncTokens()

        assert api.setCarApiBearerToken(owner_token(jti="typed")) is False
        assert api.getCarApiBearerToken() == synced


class TestNoRefreshForSyncedTokens:
    def test_sync_sets_never_expires_after_the_token(self, fake_db, refresh_endpoints):
        master = FakeMaster()
        api = new_api(master)
        # TeslaMate has not refreshed for a while: 10 minutes left.
        tm = make_teslamate(
            master, owner_token(expires_in=600), "refresh-1", registered=False
        )
        fake_db["tm"] = tm

        tm.doSyncTokens(True)

        assert api.getCarApiTokenExpireTime() == SYNCED_EXPIRY
        assert all(ep.call_count == 0 for ep in refresh_endpoints)

    def test_refresh_paths_do_nothing_while_sync_on(self, fake_db, refresh_endpoints):
        master = FakeMaster()
        api = new_api(master)
        fake_db["tm"] = make_teslamate(master, owner_token(), "refresh-1")
        fake_db["tm"].doSyncTokens()
        # Even with an expiry in the past, nothing may refresh.
        api.setCarApiTokenExpireTime(time.time() - 60)

        # The settings-load path (TWCMaster.loadSettings) and the direct
        # refresh used by wakeVehicle on a 401.
        api.setCarApiRefreshToken(api.getCarApiRefreshToken())
        assert api.apiRefresh() is False

        assert all(ep.call_count == 0 for ep in refresh_endpoints)
        assert api.getCarApiRefreshToken() == "refresh-1"


class TestSettingsLoadAfterSyncTurnedOff:
    """settings.json keeps the never-expires sentinel after a sync. If sync is
    later turned off, loading it must not leave a token that never refreshes."""

    def load(self, tmp_path, settings, teslamate_registered=False):
        import json

        from TWCManager.TWCMaster import TWCMaster
        from TWCManager.Vehicle.TeslaAPI import TeslaAPI

        (tmp_path / "settings.json").write_text(json.dumps(settings))
        config = {
            "config": {
                "settingsPath": str(tmp_path),
                "wiringMaxAmpsAllTWCs": 80,
                "teslaApiClientID": "my-client-id",
            },
            "vehicle": {"teslaAPI": {"enabled": True}},
        }
        master = TWCMaster("AB", config)
        # Not new_api(): TWCMaster.modules has its own structure.
        api = TeslaAPI(master)
        api.carApiBearerToken = ""
        api.carApiRefreshToken = ""
        api.carApiVehicles = []
        modules = {"TeslaAPI": api}
        if teslamate_registered:
            modules["TeslaMateVehicle"] = Mock(syncTokens=True)
        master.getModuleByName = modules.get
        master.loadSettings()
        return api

    def test_sentinel_replaced_by_token_exp_when_sync_off(self, tmp_path):
        import jwt

        token = owner_token()
        exp = jwt.decode(token, options={"verify_signature": False})["exp"]
        api = self.load(
            tmp_path,
            {
                "carApiBearerToken": token,
                "carApiRefreshToken": "refresh-1",
                "carApiTokenExpireTime": SYNCED_EXPIRY,
            },
        )
        assert api.getCarApiTokenExpireTime() == exp

    def test_sentinel_with_undecodable_token_expires_now(self, tmp_path):
        before = time.time()
        api = self.load(
            tmp_path,
            {
                "carApiBearerToken": "not-a-jwt-at-all",
                "carApiRefreshToken": "",
                "carApiTokenExpireTime": SYNCED_EXPIRY,
            },
        )
        assert before <= api.getCarApiTokenExpireTime() <= time.time()

    def test_sentinel_kept_while_sync_on(self, tmp_path):
        api = self.load(
            tmp_path,
            {
                "carApiBearerToken": owner_token(),
                "carApiRefreshToken": "refresh-1",
                "carApiTokenExpireTime": SYNCED_EXPIRY,
            },
            teslamate_registered=True,
        )
        assert api.getCarApiTokenExpireTime() == SYNCED_EXPIRY

    def test_ordinary_saved_expiry_unchanged(self, tmp_path):
        saved = int(time.time()) + 5 * 60 * 60
        api = self.load(
            tmp_path,
            {
                "carApiBearerToken": owner_token(),
                "carApiRefreshToken": "refresh-1",
                "carApiTokenExpireTime": saved,
            },
        )
        assert api.getCarApiTokenExpireTime() == saved
```

- [ ] **Step 3: Run the tests to verify that they fail**

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py -q`
Expected: `6 failed, 2 passed`:
- `test_resync_after_registration_replaces_bearer_token`: `AssertionError: assert 'eyJ...' == 'eyJ...'`. The bearer token is still the startup token, so **this reproduces the bug**.
- `test_hand_entered_token_still_refused_while_sync_on`: `AssertionError: assert '' == 'eyJ...'`. Even the first sync after registration is refused.
- `test_sync_sets_never_expires_after_the_token`: `assert 17916... == 999970000299999`. The sentinel was overwritten, and the log shows a `POST https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token`, i.e. TWCManager refreshed TeslaMate's token.
- `test_refresh_paths_do_nothing_while_sync_on`: `assert True is False`, because `apiRefresh()` refreshed while sync was on.
- `test_sentinel_replaced_by_token_exp_when_sync_off`: `assert 999970000299999 == 17916...`. With sync off, settings load keeps a never-expiring token.
- `test_sentinel_with_undecodable_token_expires_now`: `assert 999970000299999 <= 17916...`.
- `test_sentinel_kept_while_sync_on` and `test_ordinary_saved_expiry_unchanged` pass already. They guard the behaviour the fix must keep.

- [ ] **Step 4: Add the sentinel constant**

In `lib/TWCManager/Vehicle/TeslaAPI.py`, replace line 49:

```python
    carApiTokenExpireTime = time.time()
```

with:

```python
    carApiTokenExpireTime = time.time()
    # Expiry given to tokens supplied by a token sync source (TeslaMate). The
    # source refreshes them; TWCManager must never try to.
    SYNCED_TOKEN_EXPIRY = 99999 * 99999 * 99999
```

- [ ] **Step 5: Stop `apiRefresh` while sync is on**

Replace lines 142-143:

```python
    def apiRefresh(self):
        # Refresh tokens expire in 45
```

with:

```python
    def apiRefresh(self):
        if self.master.tokenSyncEnabled():
            # The sync source (TeslaMate) owns and refreshes these tokens.
            # Refreshing here would rotate the token out from under it.
            logger.log(logging.INFO8, "Token sync is on; not refreshing token")
            return False
        # Refresh tokens expire in 45
```

- [ ] **Step 6: Let the sync route past the refusal**

Replace lines 1265-1269:

```python
    def setCarApiBearerToken(self, token=None):
        if token:
            if self.master.tokenSyncEnabled():
                # We won't accept tokens if Token Sync is already in place
                return False
```

with:

```python
    def setCarApiBearerToken(self, token=None, fromSync=False):
        if token:
            if self.master.tokenSyncEnabled() and not fromSync:
                # While token sync is on, only the sync source may set the
                # token; refuse ones from the web UI, settings or a refresh.
                return False
```

- [ ] **Step 7: Add `restoreCarApiTokenExpireTime` and `applySyncedTokens`**

Replace lines 1319-1321:

```python
    def setCarApiTokenExpireTime(self, value):
        self.carApiTokenExpireTime = value
        return True
```

with:

```python
    def setCarApiTokenExpireTime(self, value):
        self.carApiTokenExpireTime = value
        return True

    def restoreCarApiTokenExpireTime(self, value):
        # Settings-load path (TWCMaster.loadSettings). A saved
        # SYNCED_TOKEN_EXPIRY only applies while token sync is on; once it is
        # off, use the stored token's own exp, so TWCManager's normal refresh
        # (or a re-login) follows instead of a token that never refreshes.
        if value == self.SYNCED_TOKEN_EXPIRY and not self.master.tokenSyncEnabled():
            value = time.time()
            try:
                decoded = jwt.decode(
                    self.getCarApiBearerToken(),
                    options={
                        "verify_signature": False,
                        "verify_aud": False,
                        "verify_exp": False,
                    },
                )
                value = int(decoded["exp"])
            except (jwt.exceptions.InvalidTokenError, KeyError, TypeError, ValueError):
                pass
        return self.setCarApiTokenExpireTime(value)

    def applySyncedTokens(self, accessToken, refreshToken):
        # Entry point for token sync sources (TeslaMate). Accepted whether or
        # not tokenSyncEnabled() is already true, and never refreshes.
        if not self.setCarApiBearerToken(accessToken, fromSync=True):
            return False
        # Stored directly: setCarApiRefreshToken() may start a refresh.
        self.carApiRefreshToken = refreshToken
        # Last, so the token's decoded exp cannot replace the sentinel.
        self.setCarApiTokenExpireTime(self.SYNCED_TOKEN_EXPIRY)
        return True
```

- [ ] **Step 8: Use it from `doSyncTokens`**

In `lib/TWCManager/Vehicle/TeslaMateVehicle.py`, replace lines 230-235:

```python
                        if carapi:
                            # We don't want to refresh the token - let the source handle that.
                            carapi.setCarApiTokenExpireTime(99999 * 99999 * 99999)
                            carapi.setCarApiBearerToken(access_token)
                            carapi.setCarApiRefreshToken(refresh_token)
                            self.lastSync = time.time()
```

with:

```python
                        if carapi:
                            # applySyncedTokens marks the tokens as never
                            # expiring, so TWCManager leaves refresh to
                            # TeslaMate.
                            carapi.applySyncedTokens(access_token, refresh_token)
                            self.lastSync = time.time()
```

- [ ] **Step 9: Restore the expiry through the new method in `loadSettings`**

In `lib/TWCManager/TWCMaster.py`, replace line 1101:

```python
        carapi.setCarApiTokenExpireTime(self.settings.get("carApiTokenExpireTime", ""))
```

with:

```python
        carapi.restoreCarApiTokenExpireTime(
            self.settings.get("carApiTokenExpireTime", "")
        )
```

(`loadSettings` runs bearer, then refresh, then expiry, so the bearer token whose `exp` is read is the one just loaded. The existing `tests/unit/test_twcmaster.py` fixtures use a `Mock` TeslaAPI, which accepts the new call.)

- [ ] **Step 10: Run the tests to verify that they pass**

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py -q`
Expected: `8 passed`.

Run: `$PY -m pytest tests/unit -q`
Expected: `459 passed`.

Run: `$PY -m black --check lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaMateVehicle.py lib/TWCManager/TWCMaster.py`
Expected: `3 files would be left unchanged.`

- [ ] **Step 11: Commit**

```bash
git add tests/unit/teslatokens.py tests/unit/test_teslamate_token_sync.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/TeslaMateVehicle.py lib/TWCManager/TWCMaster.py
git commit -m "fix: accept TeslaMate token resyncs after startup" -m "setCarApiBearerToken refused every token once tokenSyncEnabled() was true, which includes TeslaMate's own hourly resync, so TWCManager kept the startup token until it expired. The sync now goes through applySyncedTokens(), which passes the refusal, stores the refresh token without refreshing, and sets the never-expires sentinel after the token, so the decoded exp no longer replaces it. apiRefresh() now does nothing while sync is on, which also covers wakeVehicle's refresh on a 401. Hand-entered tokens are still refused while sync is on. Because the sentinel is now saved to settings.json, loadSettings restores the expiry through restoreCarApiTokenExpireTime(): with sync off, a saved sentinel is replaced by the stored token's exp (or now, if it can't be decoded), so TWCManager's own refresh resumes." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Classify every token by `aud` first, and follow it with `baseURL`

**Files:**
- Create: `tests/unit/test_teslaapi_token_classification.py`
- Modify `lib/TWCManager/Vehicle/TeslaAPI.py` (line numbers at `origin/main`; Task 1 shifts the later ones, so match on the quoted code):
  - `:19-23` `regionURL` and new class attributes
  - `:93-96` `__init__` proxy
  - `:250-251` `car_api_available`, guard before the refresh
  - `:1137-1141` `regionAudience` and new `fleetRegions`
  - `:1155` `teslaLoginInfo`
  - `:1164` `getLoginURL`
  - `:1219-1220` comment in `fleetTokenExchange`
  - `:1270-1304` body of `setCarApiBearerToken`, plus new `classifyToken` and `applyTokenClassification`
  - `:1327-1332` `setChargeRate`, guard after the vehicle is chosen
  - `:1449-1450` `wakeVehicle` guard
  - `:1501` and `:1547` `CarApiVehicle.verifyCert`
  - `:1555` new `verifyCert` property
  - `:1640-1642` `get_car_api` guard

**Interfaces:**
- Consumes: `setCarApiBearerToken(token=None, fromSync=False)` and the helpers from Task 1 (`new_api`, `owner_token`, `fleet_token`, `make_jwt`).
- Produces:
  - `TeslaAPI.regionURL["OwnerAPI"] == "https://owner-api.teslamotors.com/api/1/vehicles"`
  - `TeslaAPI.proxyURL: str` (`"<teslaProxy>/api/1/vehicles"` or `""`) and `TeslaAPI.proxyCert` (the `teslaProxyCert` value, default `True`)
  - `TeslaAPI.readOnly: bool` (class default `False`)
  - `TeslaAPI.fleetRegions(self) -> list[str]`, i.e. `["NA", "EU", "CN"]`
  - `TeslaAPI.classifyToken(self, decoded: dict | None) -> tuple[str, str | None]`, one of `("owner", None)`, `("fleet", "<region>")` or `("unknown", None)`
  - `TeslaAPI.applyTokenClassification(self, decoded: dict | None) -> None`: sets `baseURL`, `verifyCert` and `readOnly`, and logs
  - `CarApiVehicle.verifyCert` (read-only property, returns `self.carapi.verifyCert`)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_teslaapi_token_classification.py`:

```python
"""
TeslaAPI token classification.

Every accepted bearer token is classified, and the base URL follows the
current token:
  1. aud names owner-api            -> Owner API, read-only, proxy ignored
  2. Fleet (aud fleet-api / ou_code) -> teslaProxy if set, else region URL
  3. anything else                  -> unknown: baseURL "", ERROR logged
"""

import logging

import pytest
import requests_mock as rm

from tests.unit.teslatokens import (
    fleet_token,
    make_jwt,
    new_api,
    owner_token,
)

OWNER_URL = "https://owner-api.teslamotors.com/api/1/vehicles"
NA_URL = "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles"
EU_URL = "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles"
PROXY = "https://localhost:4443"
PROXY_URL = PROXY + "/api/1/vehicles"
PROXY_CERT = "/etc/twcmanager/proxy.pem"


@pytest.fixture
def proxy_api():
    return new_api(teslaProxy=PROXY, teslaProxyCert=PROXY_CERT)


class TestOwnerToken:
    def test_live_teslamate_token_is_owner_api_read_only(self):
        api = new_api()
        assert api.setCarApiBearerToken(owner_token()) is True
        assert api.getCarApiBaseURL() == OWNER_URL
        assert api.readOnly is True

    def test_owner_token_ignores_tesla_proxy(self, proxy_api):
        proxy_api.setCarApiBearerToken(owner_token())
        assert proxy_api.getCarApiBaseURL() == OWNER_URL
        assert proxy_api.readOnly is True
        # The proxy's certificate must not be used to verify owner-api.
        assert proxy_api.verifyCert is True

    def test_aud_as_plain_string(self):
        api = new_api()
        api.setCarApiBearerToken(make_jwt(aud="https://owner-api.teslamotors.com/"))
        assert api.getCarApiBaseURL() == OWNER_URL


class TestFleetToken:
    def test_fleet_token_without_proxy_uses_region(self):
        api = new_api()
        api.setCarApiBearerToken(fleet_token())
        assert api.getCarApiBaseURL() == NA_URL
        assert api.readOnly is False
        assert api.verifyCert is True

    def test_fleet_token_with_proxy_uses_proxy(self, proxy_api):
        proxy_api.setCarApiBearerToken(fleet_token())
        assert proxy_api.getCarApiBaseURL() == PROXY_URL
        assert proxy_api.readOnly is False
        assert proxy_api.verifyCert == PROXY_CERT

    def test_ou_code_selects_region(self):
        api = new_api()
        api.setCarApiBearerToken(fleet_token(ou_code="EU"))
        assert api.getCarApiBaseURL() == EU_URL

    def test_no_ou_code_matches_aud_host(self):
        api = new_api()
        api.setCarApiBearerToken(
            make_jwt(aud=["https://fleet-api.prd.eu.vn.cloud.tesla.com"])
        )
        assert api.getCarApiBaseURL() == EU_URL

    def test_no_ou_code_unknown_fleet_host_defaults_to_na(self):
        api = new_api()
        api.setCarApiBearerToken(
            make_jwt(aud=["https://fleet-api.prd.xx.vn.cloud.tesla.com"])
        )
        assert api.getCarApiBaseURL() == NA_URL

    def test_ou_code_alone_is_fleet(self):
        api = new_api()
        api.setCarApiBearerToken(make_jwt(ou_code="NA"))
        assert api.getCarApiBaseURL() == NA_URL
        assert api.readOnly is False


class TestUnknownToken:
    @pytest.mark.parametrize(
        "token",
        ["not-a-jwt-at-all", make_jwt(sub="someone", aud=["https://example.com"])],
        ids=["undecodable", "no-recognised-claims"],
    )
    def test_unknown_token_clears_base_url_and_logs_error(
        self, proxy_api, caplog, token
    ):
        caplog.set_level(logging.INFO)
        assert proxy_api.setCarApiBearerToken(token) is True

        assert proxy_api.getCarApiBearerToken() == token  # still stored
        assert proxy_api.getCarApiBaseURL() == ""
        assert proxy_api.readOnly is False
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert errors, "expected an ERROR log line"
        assert all(token not in r.getMessage() for r in caplog.records)

    def test_unknown_token_makes_no_api_calls(self, requests_mock, monkeypatch):
        import TWCManager.Vehicle.TeslaAPI as teslaapi

        monkeypatch.setattr(teslaapi, "Thread", lambda *a, **k: _NoThread())
        any_call = requests_mock.register_uri(rm.ANY, rm.ANY, json={})
        api = new_api()
        api.setCarApiBearerToken(fleet_token())
        api.addVehicle({"id": 1, "vin": "VIN1", "display_name": "Car"})
        vehicle = api.getCarApiVehicles()[0]
        api.setCarApiBearerToken("not-a-jwt-at-all")

        assert api.car_api_available() is False
        assert vehicle.is_awake() is False
        assert api.wakeVehicle(vehicle) is False
        assert api.setChargeRate(10, vehicle) is False

        assert any_call.call_count == 0
        assert api.getCarApiLastErrorTime() == 0
        assert vehicle.lastErrorTime == 0


class _NoThread:
    daemon = False

    def start(self):
        pass


class TestSwitching:
    def test_owner_fleet_owner_restores_url_each_time(self, proxy_api):
        proxy_api.setCarApiBearerToken(owner_token())
        assert (proxy_api.getCarApiBaseURL(), proxy_api.readOnly) == (OWNER_URL, True)

        proxy_api.setCarApiBearerToken(fleet_token())
        assert (proxy_api.getCarApiBaseURL(), proxy_api.readOnly) == (
            PROXY_URL,
            False,
        )
        assert proxy_api.verifyCert == PROXY_CERT

        proxy_api.setCarApiBearerToken(owner_token())
        assert (proxy_api.getCarApiBaseURL(), proxy_api.readOnly) == (OWNER_URL, True)
        assert proxy_api.verifyCert is True

    def test_switch_without_proxy(self):
        api = new_api()
        for token, url in [
            (owner_token(), OWNER_URL),
            (fleet_token(ou_code="EU"), EU_URL),
            (owner_token(), OWNER_URL),
        ]:
            api.setCarApiBearerToken(token)
            assert api.getCarApiBaseURL() == url

    def test_vehicle_verify_follows_token(self, proxy_api, monkeypatch):
        import TWCManager.Vehicle.TeslaAPI as teslaapi

        monkeypatch.setattr(teslaapi, "Thread", lambda *a, **k: _NoThread())
        proxy_api.setCarApiBearerToken(fleet_token())
        proxy_api.addVehicle({"id": 1, "vin": "VIN1", "display_name": "Car"})
        vehicle = proxy_api.getCarApiVehicles()[0]
        assert vehicle.verifyCert == PROXY_CERT

        proxy_api.setCarApiBearerToken(owner_token())
        assert vehicle.verifyCert is True

    def test_classification_logged_without_token(self, caplog):
        caplog.set_level(logging.INFO)
        api = new_api()
        token = owner_token()
        api.setCarApiBearerToken(token)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "owner-api.teslamotors.com" in text
        assert "read-only" in text
        assert token not in text


class TestRegionListsExcludeOwnerApi:
    def test_login_regions_are_fleet_only(self):
        api = new_api(teslaApiRedirectUri="https://twc.example.com/cb")
        assert "OwnerAPI" in api.regionURL
        assert api.teslaLoginInfo()["regions"] == ["NA", "EU", "CN"]

    def test_login_url_rejects_owner_api_region(self):
        api = new_api(
            teslaApiRedirectUri="https://twc.example.com/cb",
            teslaApiClientSecret="secret",
            teslaApiRegion="EU",
        )
        url = api.getLoginURL("OwnerAPI")
        assert "fleet-api.prd.eu.vn.cloud.tesla.com" in url
        assert "owner-api" not in url

    def test_region_audience_never_owner_api(self):
        api = new_api()
        assert api.regionAudience("OwnerAPI") == (
            "https://fleet-api.prd.na.vn.cloud.tesla.com"
        )
```

- [ ] **Step 2: Run the tests to verify that they fail**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_classification.py -q`
Expected: `16 failed, 3 passed`. Representative failures:
- `test_live_teslamate_token_is_owner_api_read_only`: `- https://owner-api.teslamotors.com/api/1/vehicles / + https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles`. This is the ou_code misclassification.
- `test_owner_token_ignores_tesla_proxy`: `+ https://localhost:4443/api/1/vehicles`.
- `test_fleet_token_without_proxy_uses_region`: `AttributeError: 'TeslaAPI' object has no attribute 'readOnly'`.
- `test_unknown_token_makes_no_api_calls`: `assert True is False`, where `True = car_api_available()`.
- `test_login_regions_are_fleet_only`: `assert 'OwnerAPI' in {...}`.

- [ ] **Step 3: Add `OwnerAPI`, `proxyURL`, `proxyCert` and `readOnly`**

Replace lines 19-23:

```python
    regionURL = {
        "NA": "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
        "EU": "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles",
        "CN": "https://fleet-api.prd.cn.vn.cloud.tesla.cn/api/1/vehicles",
    }
```

with:

```python
    regionURL = {
        "NA": "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
        "EU": "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles",
        "CN": "https://fleet-api.prd.cn.vn.cloud.tesla.cn/api/1/vehicles",
        # Not a Fleet region: the read-only Owner API used by TeslaMate tokens.
        # fleetRegions() leaves it out of every region list and lookup.
        "OwnerAPI": "https://owner-api.teslamotors.com/api/1/vehicles",
    }
    # teslaProxy base URL and certificate from config.json, kept apart from
    # baseURL so it can be restored when a Fleet token replaces an Owner one.
    proxyURL = ""
    proxyCert = True
    # True while the current token is an Owner API token, which cannot send
    # vehicle commands.
    readOnly = False
```

- [ ] **Step 4: Remember the proxy in `__init__`**

Replace lines 93-96:

```python
            proxyURL = self.config["config"].get("teslaProxy", "")
            if proxyURL:
                self.baseURL = proxyURL + "/api/1/vehicles"
                self.verifyCert = self.config["config"].get("teslaProxyCert", True)
```

with:

```python
            proxyURL = self.config["config"].get("teslaProxy", "")
            if proxyURL:
                self.proxyURL = proxyURL + "/api/1/vehicles"
                self.proxyCert = self.config["config"].get("teslaProxyCert", True)
                # Until a token is classified, assume it suits the proxy.
                self.baseURL = self.proxyURL
                self.verifyCert = self.proxyCert
```

- [ ] **Step 5: Make no request without a base URL in `car_api_available`**

Replace lines 250-251:

```python
        # Authenticate to Tesla API
        self.refreshTokenIfNeeded()
```

with:

```python
        if not self.getCarApiBaseURL():
            # The token type is unknown; setCarApiBearerToken logged why.
            logger.log(
                logging.INFO8, "car_api_available returning False: no API base URL"
            )
            return False

        # Authenticate to Tesla API
        self.refreshTokenIfNeeded()
```

- [ ] **Step 6: Keep `OwnerAPI` out of the Fleet region lists**

Replace lines 1137-1141:

```python
    def regionAudience(self, region):
        # Confidential-client only: the token audience is the regional FleetAPI
        # base URL without the /api/1/vehicles path suffix used elsewhere.
        base = self.regionURL.get(region, self.regionURL["NA"])
        return base.replace("/api/1/vehicles", "")
```

with:

```python
    def fleetRegions(self):
        # The Fleet API regions, in regionURL order; never "OwnerAPI".
        return [region for region in self.regionURL if region != "OwnerAPI"]

    def regionAudience(self, region):
        # Confidential-client only: the token audience is the regional FleetAPI
        # base URL without the /api/1/vehicles path suffix used elsewhere.
        if region not in self.fleetRegions():
            region = "NA"
        return self.regionURL[region].replace("/api/1/vehicles", "")
```

Replace line 1155:

```python
            "regions": list(self.regionURL.keys()),
```

with:

```python
            "regions": self.fleetRegions(),
```

Replace line 1164:

```python
        if region not in self.regionURL:
```

with:

```python
        if region not in self.fleetRegions():
```

Replace lines 1219-1220 (the comment in `fleetTokenExchange`):

```python
        # baseURL is left to setCarApiBearerToken, which derives the region from
        # the token's ou_code when no teslaProxy is configured.
```

with:

```python
        # baseURL is left to setCarApiBearerToken, which classifies the token
        # and picks the proxy or the region URL for a Fleet token.
```

- [ ] **Step 7: Classify every accepted token**

In `setCarApiBearerToken` (after Task 1 it starts `def setCarApiBearerToken(self, token=None, fromSync=False):`), replace everything from `            else:` / `                self.carApiBearerToken = token` to the end of the method (origin/main lines 1270-1304):

```python
            else:
                self.carApiBearerToken = token
                try:
                    decoded = jwt.decode(
                        token,
                        options={
                            "verify_signature": False,
                            "verify_aud": False,
                            "verify_exp": False,
                        },
                    )
                    if not self.baseURL:
                        if decoded.get("ou_code", "") in self.regionURL:
                            self.baseURL = self.regionURL[decoded["ou_code"]]
                        else:
                            logger.error(
                                "Unable to determine Fleet API region from token. "
                                "Set teslaProxy in config.json or provide a valid "
                                "Fleet API token."
                            )

                    if "exp" in decoded:
                        self.setCarApiTokenExpireTime(int(decoded["exp"]))
                    else:
                        self.setCarApiTokenExpireTime(time.time() + 8 * 60 * 60)

                except jwt.exceptions.DecodeError:
                    logger.error(
                        "Unable to decode Tesla API token; cannot determine Fleet "
                        "API region."
                    )
                    self.setCarApiTokenExpireTime(time.time() + 8 * 60 * 60)
                return True
        else:
            return False
```

with:

```python
            else:
                self.carApiBearerToken = token
                decoded = None
                try:
                    decoded = jwt.decode(
                        token,
                        options={
                            "verify_signature": False,
                            "verify_aud": False,
                            "verify_exp": False,
                        },
                    )
                except jwt.exceptions.InvalidTokenError:
                    pass
                self.applyTokenClassification(decoded)

                if decoded and "exp" in decoded:
                    self.setCarApiTokenExpireTime(int(decoded["exp"]))
                else:
                    self.setCarApiTokenExpireTime(time.time() + 8 * 60 * 60)
                return True
        else:
            return False

    def classifyToken(self, decoded):
        # Returns (tokenType, region) for a token's decoded JWT claims.
        # tokenType is "owner", "fleet" or "unknown"; region is a Fleet region
        # key for "fleet" and None otherwise. An Owner API token can also
        # carry ou_code, so aud is checked for owner-api first.
        if not isinstance(decoded, dict):
            return ("unknown", None)
        aud = decoded.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        aud = [str(entry) for entry in aud]
        if any("owner-api" in entry for entry in aud):
            return ("owner", None)
        ouCode = decoded.get("ou_code", "")
        if ouCode in self.fleetRegions():
            return ("fleet", ouCode)
        if any("fleet-api" in entry for entry in aud):
            for region in self.fleetRegions():
                host = urlsplit(self.regionURL[region]).netloc
                if any(host in entry for entry in aud):
                    return ("fleet", region)
            return ("fleet", "NA")
        return ("unknown", None)

    def applyTokenClassification(self, decoded):
        # Point baseURL, verifyCert and readOnly at the API the current
        # token belongs to. Runs for every accepted token.
        tokenType, region = self.classifyToken(decoded)
        if tokenType == "owner":
            # The Vehicle Command proxy only takes Fleet tokens.
            baseURL, verifyCert, readOnly = self.regionURL["OwnerAPI"], True, True
        elif tokenType == "fleet" and self.proxyURL:
            baseURL, verifyCert, readOnly = self.proxyURL, self.proxyCert, False
        elif tokenType == "fleet":
            baseURL, verifyCert, readOnly = self.regionURL[region], True, False
        else:
            baseURL, verifyCert, readOnly = "", True, False
            logger.error(
                "Unable to determine the Tesla API token type (Owner API or "
                "Fleet API). No Tesla API calls will be made until a "
                "recognised token is supplied."
            )
        self.baseURL = baseURL
        self.verifyCert = verifyCert
        self.readOnly = readOnly
        logger.info(
            "Tesla API token type: %s, base URL host: %s, read-only: %s"
            % (tokenType, urlsplit(baseURL).netloc or "none", readOnly)
        )
```

(`urlsplit` is already imported at line 10.)

- [ ] **Step 8: Add the empty-base-URL guards in `setChargeRate`, `wakeVehicle` and `get_car_api`**

In `setChargeRate`, replace origin/main lines 1332-1334:

```python
            vehicle = vehicles[0]

        # Do not set charge_rate to 0 as this will effectively stop the car from charging all together
```

with:

```python
            vehicle = vehicles[0]

        if not self.getCarApiBaseURL():
            # The token type is unknown; setCarApiBearerToken logged why.
            return False

        # Do not set charge_rate to 0 as this will effectively stop the car from charging all together
```

Replace lines 1449-1450:

```python
    def wakeVehicle(self, vehicle):
        apiResponseDict = None
```

with:

```python
    def wakeVehicle(self, vehicle):
        if not self.getCarApiBaseURL():
            # The token type is unknown; setCarApiBearerToken logged why.
            return False
        apiResponseDict = None
```

In `CarApiVehicle.get_car_api`, replace lines 1640-1642:

```python
    def get_car_api(self, url, checkReady=True, provesOnline=True):
        if checkReady and not self.ready():
            return False, None
```

with:

```python
    def get_car_api(self, url, checkReady=True, provesOnline=True):
        if not self.carapi.getCarApiBaseURL():
            # The token type is unknown; setCarApiBearerToken logged why.
            return False, None

        if checkReady and not self.ready():
            return False, None
```

- [ ] **Step 9: Make `CarApiVehicle.verifyCert` follow the token**

Delete line 1501 (in the `CarApiVehicle` class attributes):

```python
    verifyCert = None
```

Delete line 1547 (in `CarApiVehicle.__init__`):

```python
        self.verifyCert = config["config"].get("teslaProxyCert", True)
```

Then replace the start of `checkSyncNotStale` (line 1557):

```python
    def checkSyncNotStale(self):
```

with:

```python
    @property
    def verifyCert(self):
        # Follows the current token: the proxy certificate only applies
        # while requests go to teslaProxy.
        return self.carapi.verifyCert

    def checkSyncNotStale(self):
```

- [ ] **Step 10: Run the tests to verify that they pass**

Run: `$PY -m pytest tests/unit/test_teslaapi_token_classification.py -q`
Expected: `19 passed`.

Run: `$PY -m pytest tests/unit -q`
Expected: `478 passed`. The existing `tests/unit/test_teslaapi_fleetlogin.py` uses the undecodable token `"A"`. That now logs the unknown-type ERROR, but none of its assertions read `baseURL`, so it still passes.

Run: `$PY -m black --check lib/TWCManager/Vehicle/TeslaAPI.py`
Expected: `1 file would be left unchanged.`

- [ ] **Step 11: Commit**

```bash
git add tests/unit/test_teslaapi_token_classification.py lib/TWCManager/Vehicle/TeslaAPI.py
git commit -m "fix: classify every Tesla token by aud before ou_code" -m "A TeslaMate access token is an Owner API token (aud owner-api, azp ownerapi) that also carries ou_code NA, so the ou_code-only check sent it to the Fleet API, which answered 401. Classification only ran while baseURL was empty, so it never ran with teslaProxy set and never ran after the first token. Every accepted token is now classified: owner-api aud gives the Owner API URL, read-only, with teslaProxy ignored; a Fleet token gives the proxy or its region URL; anything else clears baseURL and logs an error. The proxy URL and certificate are remembered so a Fleet token can restore them, and CarApiVehicle.verifyCert now follows the token. With no base URL, no request is made and no API error is recorded. OwnerAPI is kept out of the Fleet login region list, the region validation and the audience." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Refuse commands while the token is read-only

**Files:**
- Create: `tests/unit/test_teslaapi_readonly_gate.py`
- Modify `lib/TWCManager/Vehicle/TeslaAPI.py`:
  - the class attributes added in Task 2 (`readOnlyRefusalLogged`)
  - origin/main `:294` `car_api_available` wake-loop condition
  - `:564-567` `car_api_charge` head
  - `:889` `applyChargeLimit` head
  - `applyTokenClassification` (Task 2)
  - a new `refuseCommandIfReadOnly` before `applySyncedTokens` (Task 1)
  - `:1327-1332` `setChargeRate` head
  - `wakeVehicle` head (Task 2 guard)
  - `:1938-1940` `CarApiVehicle.apply_charge_limit` head
- Modify: `lib/TWCManager/Vehicle/VehiclePriority.py:78` (new method before `_calculate_retries`) and `:109-114` (hook after the commandPolicy skip)
- Modify: `lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py:46-48`

**State-changing paths found on origin/main, and how each is closed:**
- `TeslaAPI.setChargeRate` (`:1323`). Callers: `TWCSlave.py:892, 906` via VehiclePriority; `TeslaAPIEVSE.setTargetPower` (`TeslaAPIEVSE.py:142`) **directly**; `apiDebugInterface` (`:133`) directly. Gated in the method.
- `TeslaAPI.car_api_charge` (`:564`). Callers: `TWCManager.py:323` via VehiclePriority. Gated in the method.
- `TeslaAPI.applyChargeLimit` (`:889`). Callers: `TWCManager.py:321, 335, 344` via VehiclePriority; `car_api_charge` (`:716`). Gated in the method.
- `TeslaAPI.wakeVehicle` (`:1449`). Callers: `car_api_available` wake loop (`:381`); `apiDebugInterface` (`:136`). Gated in the method, **and** the wake loop is skipped while read-only. Otherwise a refused wake returns False, which the loop records as `state == "error"`, and `updateCarApiLastErrorTime()` would start the backoff that blocks reads.
- `CarApiVehicle.apply_charge_limit` (`:1938`). Callers: `applyChargeLimit` only. Gated too, as a second guard.
- `startCharging`/`stopCharging`: **TeslaAPI has neither on main** (they are TeslaBLE methods and EVSE methods). `TeslaAPIEVSE.startCharging`/`stopCharging` call `master.startCarsCharging`/`stopCarsCharging`, which queue a `charge` task that reaches `car_api_charge` through VehiclePriority. That is closed by the two items above.
- `TeslaAPIEVSE.isReadOnly` (`TeslaAPIEVSE.py:47`) returned `False` unconditionally. It now returns `TeslaAPI.readOnly`. Then `TWCMaster.distributeEVSEPower` (`TWCMaster.py:509, 513, 571`) stops budgeting watts for a car it can't command, and `MergedEVSE.setTargetPower` (`MergedEVSE.py:154-158`) routes power to the local TWC. `MergedEVSE.stopCharging` (`:175-181`) falls back to all EVSEs when none is writable. For a TeslaAPIEVSE that ends in `master.stopCarsCharging`, which reaches the gated `car_api_charge` via VehiclePriority. **No `MergedEVSE` change is needed.**

**Interfaces:**
- Consumes: `TeslaAPI.readOnly`, `TeslaAPI.applyTokenClassification` (Task 2), `VehiclePriority.COMMAND_METHODS` (origin/main `VehiclePriority.py:21-30`), and the Task 1 helpers.
- Produces:
  - `TeslaAPI.readOnlyRefusalLogged: bool` (class default `False`; reset in `applyTokenClassification` when `readOnly` changes)
  - `TeslaAPI.refuseCommandIfReadOnly(self, command: str) -> bool`
  - `VehiclePriority._skip_read_only_for_command(self, module_ref, method_name: str) -> bool`
  - `TeslaAPIEVSE.isReadOnly -> bool` (follows `TeslaAPI.readOnly`)
  - Refusal return values: `setChargeRate -> False`, `car_api_charge -> "error"`, `applyChargeLimit -> "error"`, `wakeVehicle -> False`, `CarApiVehicle.apply_charge_limit -> False`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_teslaapi_readonly_gate.py`:

```python
"""
Read-only command gate.

While TeslaAPI holds an Owner API token (readOnly), no vehicle command may
reach Tesla: VehiclePriority skips TeslaAPI for command methods, and
TeslaAPI's own command entry points refuse without an HTTP call and without
recording an API error (which would back off reads too). Reads still run.
"""

import logging
import re
import time
from unittest.mock import Mock

import pytest
import requests_mock as rm

from tests.unit.teslatokens import fleet_token, new_api, owner_token

OWNER_URL = "https://owner-api.teslamotors.com/api/1/vehicles"


class _NoThread:
    daemon = False

    def start(self):
        pass


@pytest.fixture
def no_threads(monkeypatch):
    import TWCManager.Vehicle.TeslaAPI as teslaapi

    monkeypatch.setattr(teslaapi, "Thread", lambda *a, **k: _NoThread())


@pytest.fixture
def owner_api(no_threads):
    api = new_api()
    api.setCarApiBearerToken(owner_token())
    api.addVehicle({"id": 1, "vin": "VIN1", "display_name": "Car"})
    vehicle = api.getCarApiVehicles()[0]
    vehicle.atHome = True
    # Recently contacted, so ready() is True without an HTTP call.
    vehicle.lastAPIAccessTime = time.time()
    return api


@pytest.fixture
def any_http(requests_mock):
    return requests_mock.register_uri(rm.ANY, rm.ANY, json={})


def no_error_recorded(api):
    vehicle = api.getCarApiVehicles()[0]
    return api.getCarApiLastErrorTime() == 0 and vehicle.lastErrorTime == 0


class TestTeslaAPIRefusesCommands:
    def test_set_charge_rate(self, owner_api, any_http):
        vehicle = owner_api.getCarApiVehicles()[0]
        before = vehicle.lastAPIAccessTime
        assert owner_api.setChargeRate(10, vehicle) is False
        assert any_http.call_count == 0
        assert no_error_recorded(owner_api)
        assert vehicle.lastAPIAccessTime == before

    def test_start_and_stop_charge(self, owner_api, any_http):
        assert owner_api.car_api_charge({"charge": True}) == "error"
        assert owner_api.car_api_charge({"charge": False}) == "error"
        assert any_http.call_count == 0
        assert no_error_recorded(owner_api)

    def test_apply_charge_limit(self, owner_api, any_http):
        assert owner_api.applyChargeLimit(80) == "error"
        assert owner_api.applyChargeLimit(80, checkArrival=True) == "error"
        vehicle = owner_api.getCarApiVehicles()[0]
        assert vehicle.apply_charge_limit(80) is False
        assert any_http.call_count == 0
        assert no_error_recorded(owner_api)

    def test_wake(self, owner_api, any_http):
        vehicle = owner_api.getCarApiVehicles()[0]
        assert owner_api.wakeVehicle(vehicle) is False
        assert any_http.call_count == 0
        assert no_error_recorded(owner_api)

    def test_car_api_available_skips_wake_loop(self, owner_api, any_http):
        vehicle = owner_api.getCarApiVehicles()[0]
        vehicle.lastAPIAccessTime = 0  # asleep as far as we know
        owner_api.car_api_available(charge=True)
        owner_api.car_api_available(applyLimit=True)
        assert any_http.call_count == 0
        assert no_error_recorded(owner_api)

    def test_fleet_token_is_not_refused(self, owner_api, requests_mock):
        owner_api.setCarApiBearerToken(fleet_token())
        cmd = requests_mock.post(
            re.compile(r".*/VIN1/command/set_charging_amps"),
            json={"response": {"result": True, "reason": ""}},
        )
        vehicle = owner_api.getCarApiVehicles()[0]
        assert owner_api.setChargeRate(10, vehicle) == {
            "response": {"result": True, "reason": ""}
        }
        assert cmd.call_count == 1


class TestRefusalLogging:
    def refusals(self, caplog):
        return [
            r
            for r in caplog.records
            if r.levelno == logging.INFO
            and "read-only" in r.getMessage()
            and "not sending" in r.getMessage()
        ]

    def test_logged_once_per_state_change(self, owner_api, any_http, caplog):
        caplog.set_level(logging.INFO)
        vehicle = owner_api.getCarApiVehicles()[0]
        owner_api.setChargeRate(10, vehicle)
        owner_api.setChargeRate(12, vehicle)
        owner_api.car_api_charge({"charge": True})
        assert len(self.refusals(caplog)) == 1

        # Fleet token: commands allowed. Back to Owner: logs again, once.
        owner_api.setCarApiBearerToken(fleet_token())
        owner_api.setCarApiBearerToken(owner_token())
        owner_api.setChargeRate(10, vehicle)
        owner_api.setChargeRate(10, vehicle)
        assert len(self.refusals(caplog)) == 2

    def test_resync_of_owner_token_does_not_log_again(
        self, owner_api, any_http, caplog
    ):
        caplog.set_level(logging.INFO)
        vehicle = owner_api.getCarApiVehicles()[0]
        owner_api.setChargeRate(10, vehicle)
        owner_api.setCarApiBearerToken(owner_token(jti="rotated"))
        owner_api.setChargeRate(10, vehicle)
        assert len(self.refusals(caplog)) == 1


class TestReadsStillRun:
    def test_vehicle_data_read_uses_owner_api(self, owner_api, requests_mock):
        data = requests_mock.get(
            OWNER_URL + "/VIN1/vehicle_data",
            json={
                "response": {
                    "drive_state": {"latitude": 37.0, "longitude": -122.0},
                    "charge_state": {"battery_level": 55, "charge_limit_soc": 80},
                    "vehicle_state": {"vehicle_name": "Car"},
                }
            },
        )
        vehicle = owner_api.getCarApiVehicles()[0]
        assert vehicle.update_vehicle_data() is True
        assert data.call_count == 1
        assert vehicle.batteryLevel == 55

    def test_vehicle_list_read_uses_owner_api(self, no_threads, requests_mock):
        api = new_api()
        api.setCarApiBearerToken(owner_token())
        listing = requests_mock.get(
            OWNER_URL,
            json={
                "count": 1,
                "response": [{"id": 1, "vin": "VIN1", "display_name": "Car"}],
            },
        )
        assert api.car_api_available() is True
        assert listing.call_count == 1
        assert api.getVehicleCount() == 1


class TestVehiclePrioritySkipsReadOnly:
    def make(self, api_read_only):
        from TWCManager.Vehicle.VehiclePriority import VehiclePriority

        master = Mock()
        master.stats = {"moduleSuccess": {}, "moduleFailures": {}}
        master.config = {}
        master.settings = {}
        ble = Mock()
        ble.setChargeRate = Mock(return_value=False)
        ble.updateChargeAtHome = Mock(return_value=False)
        api = Mock()
        api.readOnly = api_read_only
        api.setChargeRate = Mock(return_value=True)
        api.updateChargeAtHome = Mock(return_value=True)
        master.getModuleByPriority = Mock(
            side_effect=[("TeslaBLE", ble, 20), ("TeslaAPI", api, 10), ("", None, 0)]
        )
        return VehiclePriority(master), master, ble, api

    def test_read_only_api_skipped_for_commands(self):
        priority, master, ble, api = self.make(api_read_only=True)
        assert priority.setChargeRate(10) is False
        assert ble.setChargeRate.called
        assert not api.setChargeRate.called
        assert "TeslaAPI" not in master.stats["moduleFailures"]

    def test_read_only_api_used_for_reads(self):
        priority, master, ble, api = self.make(api_read_only=True)
        assert priority.updateChargeAtHome() is True
        assert api.updateChargeAtHome.called

    def test_writable_api_used_for_commands(self):
        priority, master, ble, api = self.make(api_read_only=False)
        assert priority.setChargeRate(10) is True
        assert api.setChargeRate.called

    @pytest.mark.parametrize(
        "method", ["car_api_charge", "applyChargeLimit", "wakeVehicle"]
    )
    def test_every_command_method_skips(self, method):
        priority, master, ble, api = self.make(api_read_only=True)
        setattr(ble, method, Mock(return_value=False))
        setattr(api, method, Mock(return_value=True))
        getattr(priority, method)()
        assert not getattr(api, method).called


class TestTeslaAPIEVSE:
    def make_evse(self, carapi):
        from TWCManager.EVSEInstance.TeslaAPIEVSE import TeslaAPIEVSE

        master = Mock()
        master.config = {"config": {}}
        master.getModuleByName = Mock(return_value=carapi)
        return TeslaAPIEVSE(Mock(VIN="VIN1"), Mock(), master)

    def test_read_only_follows_tesla_api(self, owner_api):
        evse = self.make_evse(owner_api)
        assert evse.isReadOnly is True
        owner_api.setCarApiBearerToken(fleet_token())
        assert evse.isReadOnly is False

    def test_not_read_only_without_tesla_api(self):
        assert self.make_evse(None).isReadOnly is False
```

Note on `TestVehiclePrioritySkipsReadOnly`: the existing `tests/unit/test_vehicle_priority.py::TestCommandPolicy` builds the API module as a bare `Mock()`, whose `readOnly` attribute is a truthy `Mock`. The production check must therefore be `getattr(module_ref, "readOnly", False) is True`, or those existing tests regress.

- [ ] **Step 2: Run the tests to verify that they fail**

Run: `$PY -m pytest tests/unit/test_teslaapi_readonly_gate.py -q`
Expected: `12 failed, 6 passed`. Representative failures:
- `test_set_charge_rate`: `assert {} is False`, so the command was POSTed.
- `test_start_and_stop_charge`: `assert 2 == 0`, two HTTP calls.
- `test_apply_charge_limit`: `AttributeError: 'FakeMaster' object has no attribute 'getNormalChargeLimit'`, because the command path ran.
- `test_wake`: `assert {} is False`.
- `test_car_api_available_skips_wake_loop`: `assert 1 == 0`.
- `test_logged_once_per_state_change`: `assert 0 == 1`.
- `test_read_only_api_skipped_for_commands`: `assert True is False`.
- `test_every_command_method_skips[...]`: `assert not True`.
- `test_read_only_follows_tesla_api`: `assert False is True` (`isReadOnly` is always False on main).

- [ ] **Step 3: Add the refusal-logged flag**

In `lib/TWCManager/Vehicle/TeslaAPI.py`, replace the Task 2 lines:

```python
    # True while the current token is an Owner API token, which cannot send
    # vehicle commands.
    readOnly = False
```

with:

```python
    # True while the current token is an Owner API token, which cannot send
    # vehicle commands.
    readOnly = False
    readOnlyRefusalLogged = False
```

- [ ] **Step 4: Skip the wake loop while read-only**

Replace origin/main line 294 in `car_api_available`:

```python
            if self.getVehicleCount() > 0 and (charge or applyLimit):
```

with:

```python
            if (
                self.getVehicleCount() > 0
                and (charge or applyLimit)
                and not self.readOnly
            ):
```

- [ ] **Step 5: Gate `car_api_charge` and `applyChargeLimit`**

Replace lines 564-566:

```python
    def car_api_charge(self, task):
        # Do not call this function directly.  Call by using background thread:
        # queue_background_task({'cmd':'charge', 'charge':<True/False>})
```

with:

```python
    def car_api_charge(self, task):
        # Do not call this function directly.  Call by using background thread:
        # queue_background_task({'cmd':'charge', 'charge':<True/False>})
        if self.refuseCommandIfReadOnly("charge_start/charge_stop"):
            return "error"
```

Replace line 889:

```python
    def applyChargeLimit(self, limit, checkArrival=False, checkDeparture=False):
```

with:

```python
    def applyChargeLimit(self, limit, checkArrival=False, checkDeparture=False):
        if self.refuseCommandIfReadOnly("set_charge_limit"):
            return "error"
```

- [ ] **Step 6: Let the next refusal log again when read-only changes**

In `applyTokenClassification` (Task 2), replace:

```python
        self.baseURL = baseURL
        self.verifyCert = verifyCert
        self.readOnly = readOnly
```

with:

```python
        if readOnly != self.readOnly:
            # Let the next refused command log again.
            self.readOnlyRefusalLogged = False
        self.baseURL = baseURL
        self.verifyCert = verifyCert
        self.readOnly = readOnly
```

- [ ] **Step 7: Add `refuseCommandIfReadOnly`**

Replace the Task 1 line:

```python
    def applySyncedTokens(self, accessToken, refreshToken):
```

with:

```python
    def refuseCommandIfReadOnly(self, command):
        # True when the current token cannot send vehicle commands. Logs at
        # INFO once per read-only period, makes no HTTP call and records no
        # API error (an error would start the backoff that also blocks reads).
        if not self.readOnly:
            return False
        if not self.readOnlyRefusalLogged:
            logger.info(
                "Tesla API token is read-only (Owner API); not sending "
                + command
                + " or any other vehicle command. Commands need a Fleet API "
                "token or the TeslaBLE module."
            )
            self.readOnlyRefusalLogged = True
        return True

    def applySyncedTokens(self, accessToken, refreshToken):
```

- [ ] **Step 8: Gate `setChargeRate`, `wakeVehicle` and `CarApiVehicle.apply_charge_limit`**

At the top of `setChargeRate` (origin/main lines 1327-1332), replace:

```python
        if not vehicle:
            vehicles = self.getCarApiVehicles()
            if not vehicles:
                logger.error("No Tesla vehicles available to set charge rate")
                return False
            vehicle = vehicles[0]
```

with:

```python
        if self.refuseCommandIfReadOnly("set_charging_amps"):
            return False

        if not vehicle:
            vehicles = self.getCarApiVehicles()
            if not vehicles:
                logger.error("No Tesla vehicles available to set charge rate")
                return False
            vehicle = vehicles[0]
```

(This sits above `vehicle.lastAPIAccessTime = time.time()`, so a refused command doesn't make `ready()` think the car was just contacted.)

In `wakeVehicle`, replace the Task 2 head:

```python
    def wakeVehicle(self, vehicle):
        if not self.getCarApiBaseURL():
```

with:

```python
    def wakeVehicle(self, vehicle):
        if self.refuseCommandIfReadOnly("wake_up"):
            return False
        if not self.getCarApiBaseURL():
```

In `CarApiVehicle.apply_charge_limit`, replace origin/main lines 1938-1940:

```python
    def apply_charge_limit(self, limit):
        if self.stopTryingToApplyLimit:
            return True
```

with:

```python
    def apply_charge_limit(self, limit):
        if self.carapi.refuseCommandIfReadOnly("set_charge_limit"):
            return False

        if self.stopTryingToApplyLimit:
            return True
```

- [ ] **Step 9: Skip read-only modules in VehiclePriority**

In `lib/TWCManager/Vehicle/VehiclePriority.py`, replace line 78:

```python
    def _calculate_retries(self, priority):
```

with:

```python
    def _skip_read_only_for_command(self, module_ref, method_name):
        """Return True if module_ref holds a read-only token (TeslaAPI with an
        Owner API token) and method_name is a state-changing command. The
        next module is tried instead; the skip is not counted as a failure.
        Compared with `is True` so a module without the attribute, or a
        Mock in tests, is never skipped."""
        if method_name not in self.COMMAND_METHODS:
            return False
        return getattr(module_ref, "readOnly", False) is True

    def _calculate_retries(self, priority):
```

Replace lines 109-116:

```python
                if self._skip_module_for_command(module_name, name):
                    logger.log(
                        logging.INFO2,
                        f"VehiclePriority: commandPolicy {self.commandPolicy} excludes {module_name} for {name}",
                    )
                    continue

                # Calculate retries for this priority level
```

with:

```python
                if self._skip_module_for_command(module_name, name):
                    logger.log(
                        logging.INFO2,
                        f"VehiclePriority: commandPolicy {self.commandPolicy} excludes {module_name} for {name}",
                    )
                    continue

                if self._skip_read_only_for_command(module_ref, name):
                    logger.log(
                        logging.INFO2,
                        f"VehiclePriority: {module_name} is read-only; skipping it for {name}",
                    )
                    continue

                # Calculate retries for this priority level
```

- [ ] **Step 10: Make `TeslaAPIEVSE.isReadOnly` follow TeslaAPI**

In `lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py`, replace lines 46-48:

```python
    @property
    def isReadOnly(self) -> bool:
        return False
```

with:

```python
    @property
    def isReadOnly(self) -> bool:
        # An Owner API token can read the vehicle but not command it, so the
        # distributor must not budget power for it.
        carapi = self.master.getModuleByName("TeslaAPI")
        return carapi is not None and getattr(carapi, "readOnly", False) is True
```

- [ ] **Step 11: Run the tests to verify that they pass**

Run: `$PY -m pytest tests/unit/test_teslaapi_readonly_gate.py -q`
Expected: `18 passed`.

Run: `$PY -m pytest tests/unit -q`
Expected: `496 passed`. That includes the unchanged `tests/unit/test_vehicle_priority.py`, which shows that a bare `Mock` module is still not skipped.

Run: `$PY -m black --check lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/VehiclePriority.py lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py`
Expected: `3 files would be left unchanged.`

- [ ] **Step 12: Commit**

```bash
git add tests/unit/test_teslaapi_readonly_gate.py lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/VehiclePriority.py lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py
git commit -m "fix: refuse Tesla vehicle commands while the token is read-only" -m "An Owner API token can read vehicle data but not send commands. While TeslaAPI holds one, VehiclePriority skips it for its COMMAND_METHODS, and so tries the next channel without counting a failure. TeslaAPI's own entry points refuse too, because some callers bypass VehiclePriority (TeslaAPIEVSE.setTargetPower, the debug page): setChargeRate, car_api_charge, applyChargeLimit, wakeVehicle and CarApiVehicle.apply_charge_limit. Each refusal returns the usual failure value, makes no HTTP call, records no API error time and logs at INFO once per change of read-only state. car_api_available skips its wake loop while read-only. TeslaAPIEVSE.isReadOnly now follows TeslaAPI, so the power distributor no longer budgets for a car it can't command. Reads are unaffected." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Port to release/1.3.4

**Files** (line numbers at `origin/release/1.3.4`):
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (cherry-picked; touches `:22`, `:49`, `:96`, `:142`, `:556`, `:862`, `:1103-1125`, `:1231`, `:1285`, `:1289`, `:1389`, `:1485`, `:1580`, `:1793`)
- Modify: `lib/TWCManager/Vehicle/TeslaMateVehicle.py:230-235` (identical to main)
- Modify: `lib/TWCManager/TWCMaster.py:944` (`loadSettings` expiry restore; cherry-picked cleanly)
- Modify: `lib/TWCManager/Vehicle/VehiclePriority.py:13-14`, `:21-23`, `:52-54` (conflict resolution below)
- Create: the four test files from Tasks 1-3, with `TestTeslaAPIEVSE` removed from `tests/unit/test_teslaapi_readonly_gate.py`
- Not present on 1.3.4, so nothing to port: `lib/TWCManager/EVSEInstance/` (whole directory), `MergedEVSE`, `TeslaAPIController`

**What `git diff origin/main origin/release/1.3.4` shows in the touched files, and what each does to the cherry-pick:**

| File / region | Difference on 1.3.4 | Effect |
|---|---|---|
| `TeslaAPI.py` `apiRefresh` | refresh URL is `self.authTokenURL if self.usePKCE() else self.fleetRefreshURL` | none. Task 1 inserts above the comment, and the context matches |
| `TeslaAPI.py` `applyChargeLimit` | no first `car_api_available()` pre-check | none. The Task 3 gate goes directly under the `def` line |
| `TeslaAPI.py` `car_api_charge` | no `respectVehicleSchedule` block | none, outside the hunk |
| `TeslaAPI.py` `is_location_home`, `vehicleIsDefinitelyHome`, `vehicleScheduledChargingPending`, `gpsAsOf`, BLE-first reads in `update_location`/`update_charge` | absent on 1.3.4 | none, outside the hunks |
| `TeslaAPI.py` `CarApiVehicle.is_awake` | `get_car_api(...)` call wrapped over 3 lines | none; also the one pre-existing black diff on 1.3.4 |
| `VehiclePriority.py` | **no `VALID_COMMAND_POLICIES`, `commandPolicy`, `COMMAND_METHODS` or `_skip_module_for_command`, and no skip in `__getattr__`** | **content conflict** in Task 3. Resolve as below |
| `EVSEInstance/TeslaAPIEVSE.py` | file doesn't exist | **modify/delete conflict** in Task 3. Resolve by deleting |
| `tests/unit/test_vehicle_priority.py` | heavily different (432 vs 629 lines) | none, because the new tests live in new files |
| `tests/unit/test_teslaapi_fleetlogin.py`, `TeslaMateVehicle.py` | identical | none |
| `TWCMaster.py` `loadSettings` | same three token lines (`:941-944`); the rest of the file differs | none, auto-merges |

This was checked by doing the cherry-picks in a scratch clone. Tasks 1 and 2 apply with no conflicts (`Auto-merging lib/TWCManager/Vehicle/TeslaAPI.py`). Task 3 stops with exactly these two conflicts:

```
CONFLICT (modify/delete): lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py deleted in HEAD and modified in <T3> (fix: refuse Tesla vehicle commands while the token is read-only).
CONFLICT (content): Merge conflict in lib/TWCManager/Vehicle/VehiclePriority.py
```

**Interfaces:**
- Consumes: the three commits from Tasks 1-3, `<T1>`, `<T2>` and `<T3>` (looked up in Step 1).
- Produces: branch `port-teslamate-token-sync-1.3.4` with the same public names as main: `TeslaAPI.applySyncedTokens`, `restoreCarApiTokenExpireTime`, `setCarApiBearerToken(token=None, fromSync=False)`, `SYNCED_TOKEN_EXPIRY`, `regionURL["OwnerAPI"]`, `proxyURL`, `proxyCert`, `readOnly`, `readOnlyRefusalLogged`, `fleetRegions`, `classifyToken`, `applyTokenClassification` and `refuseCommandIfReadOnly`, plus `VehiclePriority.COMMAND_METHODS` (new on 1.3.4) and `VehiclePriority._skip_read_only_for_command`.

- [ ] **Step 1: Branch, look up the commits, record the baseline**

```bash
git fetch origin
git log --reverse --format='%h %s' origin/main..fix/teslamate-token-sync
git switch -c port-teslamate-token-sync-1.3.4 origin/release/1.3.4
$PY -m pytest tests/unit -q
```

The log lists three commits, oldest first. Below, `<T1>`, `<T2>` and `<T3>` stand for those three hashes; they are looked up here, not left open. The baseline is expected to be `62 failed, 373 passed`.

- [ ] **Step 2: Cherry-pick Tasks 1 and 2**

```bash
git cherry-pick <T1> <T2>
```

Expected: both apply (`Auto-merging lib/TWCManager/TWCMaster.py`, `Auto-merging lib/TWCManager/Vehicle/TeslaAPI.py`) with no conflict.

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py tests/unit/test_teslaapi_token_classification.py -q`
Expected: `27 passed`.

- [ ] **Step 3: Cherry-pick Task 3 and resolve the expected conflicts**

```bash
git cherry-pick <T3>
```

Expected: stops with the two conflicts above.

Resolve `TeslaAPIEVSE.py` by deleting it (1.3.4 has no EVSE layer):

```bash
git rm -q lib/TWCManager/EVSEInstance/TeslaAPIEVSE.py
```

Resolve `VehiclePriority.py` by restoring the 1.3.4 file and applying the 1.3.4 form of the change:

```bash
git checkout origin/release/1.3.4 -- lib/TWCManager/Vehicle/VehiclePriority.py
```

Then in `lib/TWCManager/Vehicle/VehiclePriority.py` (1.3.4 line numbers), replace lines 13-14:

```python
class VehiclePriority:
    master = None
```

with:

```python
class VehiclePriority:
    master = None

    # State-changing (command) methods. A module holding a read-only token
    # (TeslaAPI with an Owner API token) is skipped for these.
    COMMAND_METHODS = frozenset(
        [
            "car_api_charge",
            "setChargeRate",
            "startCharging",
            "stopCharging",
            "applyChargeLimit",
            "wakeVehicle",
        ]
    )
```

Replace line 23:

```python
    def _calculate_retries(self, priority):
```

with:

```python
    def _skip_read_only_for_command(self, module_ref, method_name):
        """Return True if module_ref holds a read-only token (TeslaAPI with an
        Owner API token) and method_name is a state-changing command. The
        next module is tried instead; the skip is not counted as a failure.
        Compared with `is True` so a module without the attribute, or a
        Mock in tests, is never skipped."""
        if method_name not in self.COMMAND_METHODS:
            return False
        return getattr(module_ref, "readOnly", False) is True

    def _calculate_retries(self, priority):
```

Replace lines 52-54:

```python
                    break

                # Calculate retries for this priority level
```

with:

```python
                    break

                if self._skip_read_only_for_command(module_ref, name):
                    logger.log(
                        logging.INFO2,
                        f"VehiclePriority: {module_name} is read-only; skipping it for {name}",
                    )
                    continue

                # Calculate retries for this priority level
```

Check the result against this expected diff:

```diff
diff --git a/lib/TWCManager/Vehicle/VehiclePriority.py b/lib/TWCManager/Vehicle/VehiclePriority.py
index c3d38ce..a5eb1de 100644
--- a/lib/TWCManager/Vehicle/VehiclePriority.py
+++ b/lib/TWCManager/Vehicle/VehiclePriority.py
@@ -13,6 +13,19 @@ logger = LoggerFactory.get_logger("VehiclePriority", "Vehicle")
 class VehiclePriority:
     master = None
 
+    # State-changing (command) methods. A module holding a read-only token
+    # (TeslaAPI with an Owner API token) is skipped for these.
+    COMMAND_METHODS = frozenset(
+        [
+            "car_api_charge",
+            "setChargeRate",
+            "startCharging",
+            "stopCharging",
+            "applyChargeLimit",
+            "wakeVehicle",
+        ]
+    )
+
     def __init__(self, master):
         self.master = master
 
@@ -20,6 +33,16 @@ class VehiclePriority:
         # Need to catch this one to avoid an exception
         return True
 
+    def _skip_read_only_for_command(self, module_ref, method_name):
+        """Return True if module_ref holds a read-only token (TeslaAPI with an
+        Owner API token) and method_name is a state-changing command. The
+        next module is tried instead; the skip is not counted as a failure.
+        Compared with `is True` so a module without the attribute, or a
+        Mock in tests, is never skipped."""
+        if method_name not in self.COMMAND_METHODS:
+            return False
+        return getattr(module_ref, "readOnly", False) is True
+
     def _calculate_retries(self, priority):
         """Calculate number of retries based on priority level.
         For every 10 priority points, we get 1 retry.
@@ -51,6 +74,13 @@ class VehiclePriority:
                     )
                     break
 
+                if self._skip_read_only_for_command(module_ref, name):
+                    logger.log(
+                        logging.INFO2,
+                        f"VehiclePriority: {module_name} is read-only; skipping it for {name}",
+                    )
+                    continue
+
                 # Calculate retries for this priority level
                 retries = self._calculate_retries(priority)
                 max_attempts = retries + 1  # +1 for the initial attempt
```

In `tests/unit/test_teslaapi_readonly_gate.py`, delete the whole last class, `TestTeslaAPIEVSE`, from `class TestTeslaAPIEVSE:` to the end of the file, together with the two blank lines before it. These are the lines to delete:

```python
class TestTeslaAPIEVSE:
    def make_evse(self, carapi):
        from TWCManager.EVSEInstance.TeslaAPIEVSE import TeslaAPIEVSE

        master = Mock()
        master.config = {"config": {}}
        master.getModuleByName = Mock(return_value=carapi)
        return TeslaAPIEVSE(Mock(VIN="VIN1"), Mock(), master)

    def test_read_only_follows_tesla_api(self, owner_api):
        evse = self.make_evse(owner_api)
        assert evse.isReadOnly is True
        owner_api.setCarApiBearerToken(fleet_token())
        assert evse.isReadOnly is False

    def test_not_read_only_without_tesla_api(self):
        assert self.make_evse(None).isReadOnly is False
```

The file must still end with one newline after `assert not getattr(api, method).called` (`$PY -m black --check tests/unit/test_teslaapi_readonly_gate.py` reports unchanged).

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py tests/unit/test_teslaapi_token_classification.py tests/unit/test_teslaapi_readonly_gate.py -q`
Expected: `43 passed`.

Run: `$PY -m pytest tests/unit -q`
Expected: `62 failed, 416 passed`. Same 62 failures as the baseline, plus 43 new passes. Compare the failure lists if the count differs: `$PY -m pytest tests/unit -q 2>&1 | grep ^FAILED | sort > /tmp/after.txt`, and the same on `origin/release/1.3.4` into `/tmp/before.txt`, then `diff` them. The output must be empty.

Run: `$PY -m black --check lib/TWCManager/Vehicle/VehiclePriority.py lib/TWCManager/Vehicle/TeslaMateVehicle.py`
Expected: unchanged. (`TeslaAPI.py` on 1.3.4 already fails black on one line in `CarApiVehicle.is_awake`. Don't reformat it here.)

- [ ] **Step 5: Finish the cherry-pick**

```bash
git add lib/TWCManager/Vehicle/VehiclePriority.py tests/unit/test_teslaapi_readonly_gate.py
git commit -m "fix: refuse Tesla vehicle commands while the token is read-only" -m "An Owner API token can read vehicle data but not send commands. While TeslaAPI holds one, VehiclePriority skips it for state-changing methods, and TeslaAPI refuses setChargeRate, car_api_charge, applyChargeLimit, wakeVehicle and CarApiVehicle.apply_charge_limit with no HTTP call, no API error time and one INFO line per change of read-only state. car_api_available skips its wake loop while read-only. Reads are unaffected." -m "Port to release/1.3.4: 1.3.4 has no commandPolicy, so VehiclePriority gains the COMMAND_METHODS set (same members as main) alongside the read-only skip. 1.3.4 has no EVSEInstance layer, so the TeslaAPIEVSE.isReadOnly change and its tests are dropped." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`git commit` during a stopped cherry-pick completes it with this message.

Expected `git log --oneline origin/release/1.3.4..HEAD`: three commits, with the same subjects as Tasks 1-3.

---

### Task 5: Port the sync acceptance (Task 1 only) to release/1.3.3

1.3.3 already classifies by `aud` first (`TeslaAPI.py:1230-1236 @ 1.3.3`), so only the Task 1 commit is ported. `readOnly` is **not** added on 1.3.3. Nothing there would read it (1.3.3's `VehiclePriority` has no command set, and there is no EVSE layer), so it would be dead code.

**Files** (line numbers at `origin/release/1.3.3`):
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:52` (constant), `:156-157` (`apiRefresh` head), `:1214-1218` (`setCarApiBearerToken` head), `:1262-1264` (add `applySyncedTokens`)
- Modify: `lib/TWCManager/Vehicle/TeslaMateVehicle.py:230-235` (identical to main)
- Modify: `lib/TWCManager/TWCMaster.py:943` (`loadSettings` expiry restore)
- Create: `tests/unit/teslatokens.py`, `tests/unit/test_teslamate_token_sync.py` (identical to main)

**Interfaces:**
- Consumes: the Task 1 commit.
- Produces: on 1.3.3, `TeslaAPI.SYNCED_TOKEN_EXPIRY`, `TeslaAPI.setCarApiBearerToken(token=None, fromSync=False)`, `TeslaAPI.applySyncedTokens(accessToken, refreshToken)`, `TeslaAPI.restoreCarApiTokenExpireTime(value)`, and `apiRefresh` returning False while sync is on. These are the same signatures as main.

- [ ] **Step 1: Branch, look up the commit, record the baseline**

```bash
git fetch origin
git log --reverse --format='%h %s' origin/main..fix/teslamate-token-sync
git switch -c port-teslamate-token-sync-1.3.3 origin/release/1.3.3
$PY -m pytest tests/unit -q
```

`<T1>` below is the first (oldest) hash listed: `fix: accept TeslaMate token resyncs after startup`. The baseline is expected to be `62 failed, 363 passed`.

- [ ] **Step 2: Show the bug on 1.3.3 before the fix**

Copy only the tests in from the Task 1 commit:

```bash
git checkout <T1> -- tests/unit/teslatokens.py tests/unit/test_teslamate_token_sync.py
$PY -m pytest tests/unit/test_teslamate_token_sync.py -q
```

Expected: `6 failed, 2 passed`, the same tests as in Task 1 Step 3. Note that `test_sync_sets_never_expires_after_the_token` shows the decoded `exp` (`17916...`) in place of `999970000299999`, and `test_refresh_paths_do_nothing_while_sync_on` fails because `apiRefresh()` has no sync check on 1.3.3. Then remove the copies again:

```bash
git rm -q -f tests/unit/teslatokens.py tests/unit/test_teslamate_token_sync.py
git status --short
```

Expected: `git status --short` prints nothing.

- [ ] **Step 3: Cherry-pick Task 1**

```bash
git cherry-pick <T1>
```

Expected: applies with `Auto-merging lib/TWCManager/TWCMaster.py` and `Auto-merging lib/TWCManager/Vehicle/TeslaAPI.py`, and no conflict (`loadSettings` at `TWCMaster.py:940-943 @ 1.3.3` matches main). On 1.3.3 the `apiRefresh` body below the inserted guard differs (no `refreshClientID` check; `ownerapi` picks `refreshURL`), but the hunk context is the `def` line and the comment, which match. The resulting 1.3.3-specific code must match this diff exactly:

```diff
diff --git a/lib/TWCManager/TWCMaster.py b/lib/TWCManager/TWCMaster.py
index 69d3161..36eefa0 100644
--- a/lib/TWCManager/TWCMaster.py
+++ b/lib/TWCManager/TWCMaster.py
@@ -940,7 +940,9 @@ class TWCMaster:
         carapi = self.getModuleByName("TeslaAPI")
         carapi.setCarApiBearerToken(self.settings.get("carApiBearerToken", ""))
         carapi.setCarApiRefreshToken(self.settings.get("carApiRefreshToken", ""))
-        carapi.setCarApiTokenExpireTime(self.settings.get("carApiTokenExpireTime", ""))
+        carapi.restoreCarApiTokenExpireTime(
+            self.settings.get("carApiTokenExpireTime", "")
+        )
 
         # We start with vehicles, but this should be templated in future for all modules to both remove the above logic,
         # and to push settings logic out to the individual modules
diff --git a/lib/TWCManager/Vehicle/TeslaAPI.py b/lib/TWCManager/Vehicle/TeslaAPI.py
index 66b7dc5..db168e5 100644
--- a/lib/TWCManager/Vehicle/TeslaAPI.py
+++ b/lib/TWCManager/Vehicle/TeslaAPI.py
@@ -50,6 +50,9 @@ class TeslaAPI:
     carApiBearerToken = ""
     carApiRefreshToken = ""
     carApiTokenExpireTime = time.time()
+    # Expiry given to tokens supplied by a token sync source (TeslaMate). The
+    # source refreshes them; TWCManager must never try to.
+    SYNCED_TOKEN_EXPIRY = 99999 * 99999 * 99999
     carApiLastStartOrStopChargeTime = 0
     carApiLastChargeLimitApplyTime = 0
     clientID = "81527cff06843c8634fdc09e8ac0abefb46ac849f38fe1e431c2ef2106796384"
@@ -154,6 +157,11 @@ class TeslaAPI:
         return False
 
     def apiRefresh(self):
+        if self.master.tokenSyncEnabled():
+            # The sync source (TeslaMate) owns and refreshes these tokens.
+            # Refreshing here would rotate the token out from under it.
+            logger.log(logging.INFO8, "Token sync is on; not refreshing token")
+            return False
         # Refresh tokens expire in 45
         # days when first issued, so we'll get a new token every 15 days.
         headers = {"accept": "application/json", "Content-Type": "application/json"}
@@ -1211,10 +1219,11 @@ class TeslaAPI:
 
         return "unknown"
 
-    def setCarApiBearerToken(self, token=None):
+    def setCarApiBearerToken(self, token=None, fromSync=False):
         if token:
-            if self.master.tokenSyncEnabled():
-                # We won't accept tokens if Token Sync is already in place
+            if self.master.tokenSyncEnabled() and not fromSync:
+                # While token sync is on, only the sync source may set the
+                # token; refuse ones from the web UI, settings or a refresh.
                 return False
             else:
                 self.carApiBearerToken = token
@@ -1263,6 +1272,38 @@ class TeslaAPI:
         self.carApiTokenExpireTime = value
         return True
 
+    def restoreCarApiTokenExpireTime(self, value):
+        # Settings-load path (TWCMaster.loadSettings). A saved
+        # SYNCED_TOKEN_EXPIRY only applies while token sync is on; once it is
+        # off, use the stored token's own exp, so TWCManager's normal refresh
+        # (or a re-login) follows instead of a token that never refreshes.
+        if value == self.SYNCED_TOKEN_EXPIRY and not self.master.tokenSyncEnabled():
+            value = time.time()
+            try:
+                decoded = jwt.decode(
+                    self.getCarApiBearerToken(),
+                    options={
+                        "verify_signature": False,
+                        "verify_aud": False,
+                        "verify_exp": False,
+                    },
+                )
+                value = int(decoded["exp"])
+            except (jwt.exceptions.InvalidTokenError, KeyError, TypeError, ValueError):
+                pass
+        return self.setCarApiTokenExpireTime(value)
+
+    def applySyncedTokens(self, accessToken, refreshToken):
+        # Entry point for token sync sources (TeslaMate). Accepted whether or
+        # not tokenSyncEnabled() is already true, and never refreshes.
+        if not self.setCarApiBearerToken(accessToken, fromSync=True):
+            return False
+        # Stored directly: setCarApiRefreshToken() may start a refresh.
+        self.carApiRefreshToken = refreshToken
+        # Last, so the token's decoded exp cannot replace the sentinel.
+        self.setCarApiTokenExpireTime(self.SYNCED_TOKEN_EXPIRY)
+        return True
+
     def setChargeRate(self, charge_rate, vehicle=None, set_again=False):
         # As a fallback to allow initial implementation of the charge rate functionality for single car installs,
         # If no vehicle is specified, we take the first returned to us.
diff --git a/lib/TWCManager/Vehicle/TeslaMateVehicle.py b/lib/TWCManager/Vehicle/TeslaMateVehicle.py
index 8734663..2b6bcb6 100644
--- a/lib/TWCManager/Vehicle/TeslaMateVehicle.py
+++ b/lib/TWCManager/Vehicle/TeslaMateVehicle.py
@@ -228,10 +228,10 @@ class TeslaMateVehicle(TelmetryBase):
                         # Set Bearer and Refresh Tokens
                         carapi = self.master.getModuleByName("TeslaAPI")
                         if carapi:
-                            # We don't want to refresh the token - let the source handle that.
-                            carapi.setCarApiTokenExpireTime(99999 * 99999 * 99999)
-                            carapi.setCarApiBearerToken(access_token)
-                            carapi.setCarApiRefreshToken(refresh_token)
+                            # applySyncedTokens marks the tokens as never
+                            # expiring, so TWCManager leaves refresh to
+                            # TeslaMate.
+                            carapi.applySyncedTokens(access_token, refresh_token)
                             self.lastSync = time.time()
                             logger.log(
                                 logging.INFO,
```

Note what the 1.3.3 diff deliberately keeps unchanged: classification still runs only `if not self.baseURL`, and an undecodable token still falls back to the Owner API. Changing either is 1.3.4/main behaviour (Task 2), not part of this port.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/unit/test_teslamate_token_sync.py -q`
Expected: `8 passed`.

Run: `$PY -m pytest tests/unit -q`
Expected: `62 failed, 371 passed`, i.e. the 62 baseline failures and nothing new. Compare the `^FAILED` lists as in Task 4 Step 4 if the count differs.

- [ ] **Step 5: Check the commit message**

The cherry-pick keeps the Task 1 message unchanged, trailer included:

```bash
git log -1 --format=%B
```

Expected: subject `fix: accept TeslaMate token resyncs after startup`, the Task 1 body, and last the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 6: PR descriptions

**Files:** none; this text goes into the PRs when the user asks for them to be opened.

**Interfaces:**
- Consumes: the branches from Tasks 1-5.
- Produces: three PR bodies.

- [ ] **Step 1: PR for `fix/teslamate-token-sync` → `main`**

Title: `Fix TeslaMate token sync: accept resyncs, classify Owner API tokens, refuse commands on read-only tokens`

```markdown
## Summary

TeslaMate token sync has been broken on `main` in two independent ways. This is PR 1 of the unified-integrations plan.

1. **Synced tokens were refused after startup.** `setCarApiBearerToken` refuses tokens while `tokenSyncEnabled()` is true, and that includes TeslaMate's own hourly resync (it runs after the module is registered). TeslaMate rotates its access token every 6 h and each one lives 8 h, so TWCManager kept the startup token until it expired. Syncs now go through `TeslaAPI.applySyncedTokens()`. That method:
   - passes the refusal;
   - stores the refresh token without starting a refresh;
   - sets the never-expires sentinel *after* the token. Before, the decoded `exp` overwrote it, and on startup TWCManager could refresh TeslaMate's token at the Fleet auth host.

   `apiRefresh()` now does nothing while sync is on, which also covers `wakeVehicle`'s refresh on a 401. Hand-entered tokens are still refused while sync is on.

   Because the sentinel is now saved to settings.json, settings load restores the expiry through `restoreCarApiTokenExpireTime()`. If sync has since been turned off, a saved sentinel is replaced by the stored token's own `exp` (or the current time, if the token can't be decoded), so TWCManager's normal refresh or a re-login follows.
2. **Owner API tokens were sent to the Fleet API.** A live TeslaMate access token has `aud` = owner-api and `azp` = `ownerapi`, *and* `ou_code: "NA"`. The `ou_code`-only check classified it as a Fleet token, and the Fleet API answered 401. Every accepted token is now classified, `aud` first:
   - **owner-api `aud`:** Owner API URL, `readOnly`, `teslaProxy` ignored (the command proxy only takes Fleet tokens).
   - **Fleet:** `teslaProxy` if configured, otherwise the `ou_code` region (or the region named in `aud`).
   - **Anything else:** `baseURL` is cleared and an ERROR is logged.

   Switching between token types restores the right URL and TLS verification each time.
3. **Read-only command gate.** While the token is an Owner API token:
   - VehiclePriority skips TeslaAPI for command methods, without counting a failure.
   - TeslaAPI refuses `setChargeRate`, `car_api_charge`, `applyChargeLimit` and `wakeVehicle`, plus `CarApiVehicle.apply_charge_limit`. A refusal makes no HTTP call, records no error time (an error would back off reads too) and logs once at INFO per state change.
   - `TeslaAPIEVSE.isReadOnly` follows TeslaAPI, so the distributor stops budgeting power for a car it can't command.
   - Reads are unaffected.

### Review follow-ups

- **Settings load no longer undoes the startup sync.** `TWCManager.py` loads settings after every module is registered, so TeslaMate's startup sync has already set the tokens and `tokenSyncEnabled()` is already true. While sync is on, `loadSettings` now restores none of the saved bearer token, refresh token or expiry. Before, it put back the saved refresh token and (on the first boot after upgrading) an expiry in the past, so Storm Watch and the UI saw an expired token until the next hourly resync.
- `applySyncedTokens` sets the never-expires sentinel before it stores the refresh token (still after the bearer token), so nothing can refresh with the new refresh token under the decoded `exp`.
- `classifyToken` no longer raises on `"aud": null` or a non-string `aud`: null counts as no `aud` (so `ou_code` can still classify the token), a lone string is a one-item list, and any other type makes the token unknown.
- The INFO8 line when `car_api_available` has no base URL now says "no Tesla API token yet" when there is no token, and "token type unknown" only when a token couldn't be classified.
- **The login exchange is refused while sync is on.** The login form is hidden, but `/teslaAccount/callback` and `/teslaAccount/saveToken` can still be reached by URL. `fleetTokenExchange` used to refuse the bearer token but store the refresh token, overwrite the sentinel and report success. It now stores nothing, doesn't use the code, and returns `token_sync`; the login page says sync is on and the tokens were not stored.
- **A refresh token typed into Settings is refused while sync is on.** `setCarApiRefreshToken` now refuses (and logs a WARNING) like the bearer setter; Settings still saves the other fields and redirects to the same `token_sync` notice.

## Known limitations (documented, not fixed here)

- **Single token slot.** Turning on TeslaMate sync replaces a Fleet token, as it always has. A TeslaMate-synced Owner API token and a Fleet token for commands can't be held at the same time. PR 3 of the plan adds a second slot.
- **No Owner API refresh yet.** With sync *off*, a hand-pasted Owner API token is refreshed through the Fleet path when it nears expiry, which fails and clears it. The `ownerapi` refresh client, the products swap and the TLS 1.3 session are PR 2.
- **TeslaMate DB down at startup (pre-existing).** If the TeslaMate database can't be reached at startup, `TeslaMateVehicle` turns `syncTokens` off, so `tokenSyncEnabled()` is false. The hourly resync still runs and applies TeslaMate's tokens, but with sync reported off the refresh paths (e.g. a refresh on a 401 in `wakeVehicle`) are open to TWCManager, and a hand-entered token is accepted. Not changed here.

## Testing

- New: `tests/unit/test_teslamate_token_sync.py` (reproduces the refused resync and the startup refresh first), `tests/unit/test_teslaapi_token_classification.py`, `tests/unit/test_teslaapi_readonly_gate.py`. Shared helpers are in `tests/unit/teslatokens.py`.
- `pytest tests/unit -q`: 509 passed (451 before).
- Not yet verified against a live TeslaMate: that owner-api accepts the VIN in the path for `vehicle_data`, and the vehicle list without the `/products` swap (PR 2).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: PR for `port-teslamate-token-sync-1.3.4` → `release/1.3.4`**

Title: `[1.3.4] Fix TeslaMate token sync: accept resyncs, classify Owner API tokens, refuse commands on read-only tokens`

```markdown
## Summary

Port of the `main` fix (nine commits: the three original fixes and the six review follow-ups, each cherry-picked with `-x`) to `release/1.3.4`. On 1.3.4 TeslaMate token sync is broken in the same two ways:

1. **Hourly resyncs were silently refused** because `setCarApiBearerToken` refused tokens while `tokenSyncEnabled()` was true. Syncs now use `TeslaAPI.applySyncedTokens()`, which also keeps the never-expires sentinel in place, so TWCManager never refreshes TeslaMate's token. If sync is later turned off, settings load replaces a saved sentinel with the stored token's `exp` (or the current time, if it can't be decoded), so TWCManager's own refresh resumes.
2. **Owner API tokens were sent to the Fleet API**, because TeslaMate's owner token also carries `ou_code: "NA"`. Each token is now classified by `aud` first:
   - **Owner API:** read-only, `teslaProxy` ignored.
   - **Fleet:** the proxy or the region URL.
   - **Unknown:** no base URL, plus an ERROR.
3. **Read-only command gate.** While the token is an Owner API token, VehiclePriority skips TeslaAPI for commands. TeslaAPI itself refuses `setChargeRate`, `car_api_charge`, `applyChargeLimit`, `wakeVehicle` and `CarApiVehicle.apply_charge_limit`, with no HTTP call, no error backoff and one INFO line per state change. Reads are unaffected.

### Differences from the `main` PR

- 1.3.4 has no `commandPolicy`, so `VehiclePriority` gains the `COMMAND_METHODS` set (same members as main) and only the read-only skip.
- 1.3.4 has no `EVSEInstance` layer, so the `TeslaAPIEVSE.isReadOnly` change and its tests are not included.

### Review follow-ups

- **Settings load no longer undoes the startup sync.** `TWCManager.py` loads settings after every module is registered, so TeslaMate's startup sync has already set the tokens and `tokenSyncEnabled()` is already true. While sync is on, `loadSettings` now restores none of the saved bearer token, refresh token or expiry. Before, it put back the saved refresh token and (on the first boot after upgrading) an expiry in the past, so Storm Watch and the UI saw an expired token until the next hourly resync.
- `applySyncedTokens` sets the never-expires sentinel before it stores the refresh token (still after the bearer token), so nothing can refresh with the new refresh token under the decoded `exp`.
- `classifyToken` no longer raises on `"aud": null` or a non-string `aud`: null counts as no `aud` (so `ou_code` can still classify the token), a lone string is a one-item list, and any other type makes the token unknown.
- The INFO8 line when `car_api_available` has no base URL now says "no Tesla API token yet" when there is no token, and "token type unknown" only when a token couldn't be classified.
- **The login exchange is refused while sync is on.** The login form is hidden, but `/teslaAccount/callback` and `/teslaAccount/saveToken` can still be reached by URL. `fleetTokenExchange` used to refuse the bearer token but store the refresh token, overwrite the sentinel and report success. It now stores nothing, doesn't use the code, and returns `token_sync`; the login page says sync is on and the tokens were not stored.
- **A refresh token typed into Settings is refused while sync is on.** `setCarApiRefreshToken` now refuses (and logs a WARNING) like the bearer setter; Settings still saves the other fields and redirects to the same `token_sync` notice.

## Known limitations (documented, not fixed here)

- **Single token slot.** Enabling TeslaMate sync replaces a Fleet token, as before. Holding an Owner API token for reads and a Fleet token for commands at the same time needs the second slot (PR 3).
- **No Owner API refresh yet.** With sync *off*, a pasted Owner API token is refreshed via the Fleet path on expiry and cleared (PR 2 adds the `ownerapi` refresh).
- **TeslaMate DB down at startup (pre-existing).** If the TeslaMate database can't be reached at startup, `TeslaMateVehicle` turns `syncTokens` off, so `tokenSyncEnabled()` is false. The hourly resync still runs and applies TeslaMate's tokens, but with sync reported off the refresh paths (e.g. a refresh on a 401 in `wakeVehicle`) are open to TWCManager, and a hand-entered token is accepted. Not changed here.

## Testing

- `pytest tests/unit -q`: 62 failed, 429 passed. The 62 failures are pre-existing on `release/1.3.4` (baseline 62 failed, 373 passed; same set), and the 56 new tests pass.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 3: PR for `port-teslamate-token-sync-1.3.3` → `release/1.3.3`**

Title: `[1.3.3] Accept TeslaMate token resyncs after startup`

```markdown
## Summary

Port of the sync-acceptance commit, plus four review follow-ups (settings load, sentinel order, and the login and Settings token refusals). 1.3.3 already classifies tokens by `aud` before `ou_code`, so the Owner API misclassification fixed on 1.3.4/main doesn't happen here.

- **The bug:** `setCarApiBearerToken` refused tokens while `tokenSyncEnabled()` was true. That includes TeslaMate's hourly resync, so TWCManager kept the startup token until it expired (TeslaMate rotates every 6 h, and tokens live 8 h).
- **The fix:** syncs now use `TeslaAPI.applySyncedTokens()`. It:
  - passes that refusal;
  - stores the refresh token without refreshing;
  - sets the never-expires sentinel after the token (before, the decoded `exp` replaced it).

  `apiRefresh()` does nothing while sync is on. Hand-entered tokens are still refused while sync is on.
- **Turning sync off later:** the sentinel is now saved to settings.json. If sync has been turned off, settings load replaces a saved sentinel with the stored token's `exp` (or the current time, if it can't be decoded), so the normal `ownerapi` refresh or a re-login follows.

No `readOnly` flag on 1.3.3: nothing on this branch would read it.

### Review follow-ups

- **Settings load no longer undoes the startup sync.** `TWCManager.py` loads settings after every module is registered, so TeslaMate's startup sync has already set the tokens and `tokenSyncEnabled()` is already true. While sync is on, `loadSettings` now restores none of the saved bearer token, refresh token or expiry. Before, it put back the saved refresh token and (on the first boot after upgrading) an expiry in the past, so Storm Watch and the UI saw an expired token until the next hourly resync.
- `applySyncedTokens` sets the never-expires sentinel before it stores the refresh token (still after the bearer token), so nothing can refresh with the new refresh token under the decoded `exp`.
- **The login exchange is refused while sync is on.** The login form is hidden, but `/teslaAccount/saveToken` can still be reached by URL. `saveApiToken` (1.3.3's Owner API code exchange) used to refuse the bearer token but store the refresh token, overwrite the sentinel and report success. It now stores nothing, doesn't use the code, and returns `token_sync`; the login page says sync is on and the tokens were not stored.
- **A refresh token typed into Settings is refused while sync is on.** `setCarApiRefreshToken` now refuses (and logs a WARNING) like the bearer setter; Settings still saves the other fields and redirects to the same `token_sync` notice.

## Known limitations

- **Single token slot**, as on the other branches: enabling TeslaMate sync replaces whatever token was there. Users who need more should move to 1.3.4.
- **Only the first token is classified (out of scope).** 1.3.3 picks the base URL only when none is set yet (`if not self.baseURL`). With `teslaProxy` set, or with a Fleet base URL held from before sync was turned on, a synced Owner API token is sent to the proxy or Fleet host until TWCManager restarts. Fixing it means porting the per-token classification from 1.3.4.
- **TeslaMate DB down at startup (pre-existing).** If the TeslaMate database can't be reached at startup, `TeslaMateVehicle` turns `syncTokens` off, so `tokenSyncEnabled()` is false. The hourly resync still runs and applies TeslaMate's tokens, but with sync reported off the refresh paths (e.g. a refresh on a 401 in `wakeVehicle`) are open to TWCManager, and a hand-entered token is accepted. Not changed here.

## Testing

- New: `tests/unit/test_teslamate_token_sync.py` (fails on unpatched 1.3.3, passes after), with helpers in `tests/unit/teslatokens.py`.
- `pytest tests/unit -q`: 62 failed, 376 passed. The 62 failures are pre-existing (baseline 62 failed, 363 passed; same set).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Spec coverage

| Spec item | Where |
|---|---|
| Confirm the resync refusal with a test before fixing | Task 1 Steps 2-3 (and Task 5 Step 2 on 1.3.3) |
| 1. Synced tokens accepted via an explicit route | Task 1 Steps 6-8 (`fromSync`, `applySyncedTokens`) |
| 1. Never-expires sentinel survives decoded `exp`; sentinel/token order | Task 1 Step 7 (sentinel set last), test `test_sync_sets_never_expires_after_the_token` |
| 1. `setCarApiRefreshToken` still skips refresh while sync is on | review follow-up: it now refuses outright and stores nothing; tests `test_refresh_paths_do_nothing_while_sync_on`, `TestSettingsPageWhileSyncOn` |
| 1. Hand-entered token still refused | test `test_hand_entered_token_still_refused_while_sync_on` |
| 1. (Amendment) Saved sentinel with sync off → token `exp`, or now | Task 1 Steps 7, 9; tests `TestSettingsLoadAfterSyncTurnedOff` |
| 2. Classified on every token set | Task 2 Step 7 |
| 2. Rule 1: owner-api `aud` (string or list) → Owner URL, proxy ignored, `readOnly` | Task 2 Steps 3, 7; tests `TestOwnerToken` |
| 2. Rule 2: Fleet → proxy or region; NA / `aud` host when no `ou_code`; not read-only | Task 2 Step 7; tests `TestFleetToken` |
| 2. Rule 3: unknown → `""`, ERROR without the token, `readOnly` False, token stored, proxy doesn't rescue it | Task 2 Steps 5, 7, 8; tests `TestUnknownToken` |
| 2. `proxyURL` remembered; owner → fleet → owner restores it | Task 2 Steps 3-4; tests `TestSwitching` |
| 2. INFO log of type, host and read-only, never the token | Task 2 Step 7; test `test_classification_logged_without_token` |
| `regionURL["OwnerAPI"]` | Task 2 Step 3 |
| Every other `baseURL` reader/writer named and safe | "Every place..." table; Task 2 Steps 5, 6, 8, 9 |
| 3. VehiclePriority skips read-only TeslaAPI for commands, not counted as a failure | Task 3 Step 9; tests `TestVehiclePrioritySkipsReadOnly` |
| 3. `setChargeRate`, `car_api_charge`, `applyChargeLimit` refuse with no HTTP call and no error time | Task 3 Steps 5, 8; tests `TestTeslaAPIRefusesCommands` |
| 3. Log once at INFO per state change | Task 3 Steps 6-7; tests `TestRefusalLogging` |
| 3. Reads unaffected | tests `TestReadsStillRun`, `test_read_only_api_used_for_reads` |
| 4. Single-slot limitation documented | Task 6, all three PR bodies |
| Branches: 1.3.4 gets 1-3, 1.3.3 gets 1 only | Tasks 4, 5 |
