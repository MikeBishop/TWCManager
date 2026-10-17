# Unified vehicle integrations: Owner API read-back and one preference order

Study of `origin/release/1.3.3` (71123cc), `origin/release/1.3.4` (8eac98d),
`origin/main` (0b7d143), the three `port-*-1.3.x` branches, and local
`fix/vehicle-presence` (1641265). All citations are `file:line @ rev`; code was
read from git objects only. `base` = d46616e, the merge-base of 1.3.3 and 1.3.4.

**Short answer to the key question (section 3): yes.** The read-only Owner API
can come back to 1.3.4 and main in roughly 100-150 lines of `TeslaAPI.py` plus
a read-only gate, because the 1.3.4 read path is URL-generic
(`baseURL + "/" + VIN + ...`) and 1.3.3 is production evidence that owner-api
accepts exactly those URLs. The removed 161 lines were mostly the *login* flow,
which is not needed: TeslaMate token sync and a pasted refresh token cover auth.

---

## 1. Current state per branch

### 1.1 Modules and who owns the vehicle model

All 1.3.x branches and main load the same `Vehicle.*` modules in this order:
`VehiclePriority, TeslaAPI, TeslaBLE, TeslaMateVehicle, FleetTelemetryMQTT,
HomeAssistant` (`TWCManager.py:83-88 @ 1.3.4`; same list at F:84-89).

| Module | Role today | Reads | Commands | Own vehicle list? |
|---|---|---|---|---|
| TeslaAPI | cloud (Owner on 1.3.3, Fleet on 1.3.4/main) | vehicle list, `/{VIN}` online state, `vehicle_data` | charge start/stop, set_charging_amps, set_charge_limit, wake_up | **yes - `carApiVehicles` is the model everyone else attaches to** |
| TeslaBLE | local, `tesla-control` subprocess | none on 1.3.x; main adds `get_charge_state`, `get_location_state` (`git diff 1.3.4 main -- TeslaBLE.py`); F adds `probePresence` (`TeslaBLE.py:1065 @ F`) | charging-set-amps, start/stop, wake, charge limit | no, uses `settings["Vehicles"]` VINs |
| TeslaMateVehicle | MQTT overlay + token sync | battery, limit, lat/lon, state, pilot/actual current (`TeslaMateVehicle.py:50-63 @ 1.3.4`) | none | no - attaches to TeslaAPI's `CarApiVehicle` by display name (`Telemetry.py:166-185 @ 1.3.4`) |
| FleetTelemetryMQTT | same base class | same mechanism | none | no |
| HomeAssistant | HA Tesla integration | battery/limit/location via HA entities | charge switch, amps number, limit number | yes, `HaVehicle` list (`HomeAssistant.py:48-140 @ 1.3.4`) |
| VehiclePriority | dispatcher | - | - | - |

Key coupling: **telemetry has nowhere to land without a cloud vehicle list.**
`Telemetry.updateVehicles` only maps an MQTT car onto an existing
`TeslaAPI.getCarApiVehicles()` entry (`Telemetry.py:176-185 @ 1.3.4`). With BLE +
TeslaMate and no cloud token, `carApiVehicles` is empty and every TeslaMate
message sits in `unknownVehicles` forever. The user's
`fix/teslamate-vehicle-mapping` (b3bff0e) fixes the race but not the dependency.

### 1.2 Routing of reads and commands

Commands are queued as background tasks and dispatched through
`VehiclePriority` (`TWCManager.py:298-328 @ 1.3.4`); `get_vehicle_module()`
(HomeAssistant, else TeslaAPI) is only the fallback when VehiclePriority is
missing, which never happens (`TWCManager.py:281-301 @ 1.3.4`).

`VehiclePriority.__getattr__` walks `master.getModuleByPriority("Vehicle", p)`
from 100 downward and returns the first truthy, non-`"error"` result
(`VehiclePriority.py:30-129 @ 1.3.4`). Priorities are a static table:
TeslaBLE 20, TeslaAPI 10, **everything else `None`**
(`TWCMaster.py:119-127 @ 1.3.4`, identical at F:160-168). `getModuleByPriority`
requires a truthy priority (`TWCMaster.py:388-395 @ 1.3.4`), so:

- **HomeAssistant is orphaned.** It implements `car_api_charge`,
  `applyChargeLimit`, `setChargeRate` (`HomeAssistant.py:511-690 @ 1.3.4`) but no
  dispatcher ever reaches them. This is an existing hole that one ordered
  list fixes for free.
- Reads do not go through VehiclePriority at all. `Policy.py:194`,
  `TWCSlave.py:1215`, `WebIPCControl.py:343`, `Telemetry.py:177` (all @ 1.3.4)
  call `getModuleByName("TeslaAPI").getCarApiVehicles()` directly; the only
  VehiclePriority-routed read is `updateChargeAtHome` (`TWCManager.py:321`,
  `TeslaAPI.py:1357-1361 @ 1.3.4`).

main adds `commandPolicy` (`prefer_ble | ble_only | api_only`) with a
`COMMAND_METHODS` set that the policy gates
(`VehiclePriority.py:15-76 @ main`). F adds caller-side `skip`/`only`
(`remoteOnly`, `localOnly`) and a fan-out `resetChargeLimitState`
(`VehiclePriority.py:85-124 @ F`).

**main's EVSE layer bypasses VehiclePriority.** `TeslaAPIEVSE.setTargetPower`
calls `getModuleByName("TeslaAPI").setChargeRate` directly
(`TeslaAPIEVSE.py:140-142 @ main`). F reroutes that through the vehicle command
queue (3ea8622 "Queue Fleet API charge rates to the vehicle worker";
`TeslaAPI.py:1028-1034 @ F` documents the invariant). Any read-only gate that
lives only in VehiclePriority leaks on main until that lands.

### 1.3 Where reads and commands are entangled inside TeslaAPI

- `car_api_available(charge, applyLimit)` is the gate for both: it refreshes
  the token, fetches the vehicle list, **and runs the wake loop** when
  `charge` or `applyLimit` is set (`TeslaAPI.py:222-505 @ 1.3.4`; wake loop
  294-470). `car_api_charge` calls it with `charge=` (`TeslaAPI.py:583`), so
  "is the API available" and "wake the car" are one call.
- `applyChargeLimit` reads (`vehicle.update_location()`, `:903`) and then
  commands inside the same loop (`TeslaAPI.py:862-1020 @ 1.3.4`).
- `CarApiVehicle.is_awake` prefers telemetry `syncState`, else GETs
  `/{VIN}` (`TeslaAPI.py:1554-1578 @ 1.3.4`) - a pure read that already costs
  nothing on owner-api.
- `update_charge`/`update_location` short-circuit when `syncSource !=
  "TeslaAPI"` (`TeslaAPI.py:1668-1682, 1776-1780 @ 1.3.4`). F extends
  `update_charge(allowBle, forceLive)` to try BLE first, then API
  (`TeslaAPI.py:2057-2100 @ F`), i.e. **read fallback is hand-rolled inside
  TeslaAPI rather than dispatched**.
- F's `vehicleOnlineStates()` is a bare `requests.get` of the vehicle list
  (`TeslaAPI.py:1168-1196 @ F`, `requests.get` at `:1180`); PresenceSources' `apiSource` uses it to avoid
  waking (`PresenceSources.py:101-121 @ F`).

### 1.4 Auth and tokens

| | 1.3.3 | 1.3.4 / main |
|---|---|---|
| Login | ownerapi PKCE: user opens auth.tesla.com link with `client_id=ownerapi`, pastes the `void/callback` URL back (`request_teslalogin.html.j2 @ 1.3.3`; `saveApiToken` `TeslaAPI.py:1149-1212 @ 1.3.3`) | Fleet Authorization Code: PKCE by default, optional client secret (`getLoginURL`, `fleetTokenExchange`, `TeslaAPI.py:1125-1229 @ 1.3.4`); `/teslaAccount/login`, `/callback`, paste-back `/saveToken` (`HTTPControl.py:1052-1075, 1267 @ 1.3.4`) |
| Refresh | `client_id=ownerapi` at auth.tesla.com when `refreshClientID=="ownerapi"` (default), else fleet-auth (`TeslaAPI.py:156-175 @ 1.3.3`) | refuses without `teslaApiClientID` (`TeslaAPI.py:142-150 @ 1.3.4`); host is auth.tesla.com for PKCE, fleet-auth for confidential (`:160`) |
| Region / base URL | JWT `aud` contains `owner-api` -> OwnerAPI base URL, else `ou_code` (`TeslaAPI.py:1231-1243 @ 1.3.3`); decode failure falls back to owner-api | `ou_code` only; otherwise logs an error and `baseURL` stays `""` (`TeslaAPI.py:1247-1255 @ 1.3.4`, same at F) |
| TLS | `TLS13Adapter` mounted on all Tesla hosts (`TeslaAPI.py:20-31, 113-122 @ 1.3.3`) | plain `requests` |
| TeslaMate token sync | reads `tokens` table, decrypts, pushes into TeslaAPI with a never-expiring timestamp (`TeslaMateVehicle.py:181-270 @ 1.3.4`, same code at 1.3.3); `setCarApiBearerToken` **refuses any other token while sync is on** (`TeslaAPI.py:1233-1235 @ 1.3.4`) | same |
| Persistence | single slot `carApiBearerToken/RefreshToken/TokenExpireTime` in settings.json (`TWCMaster.py:941-943, 1321-1323 @ 1.3.3`; identical at 1.3.4) | same |

Consequence worth stating plainly: **TeslaMate token sync on 1.3.4 is broken
for the tokens TeslaMate actually holds.** TeslaMate's tokens come from
auth.tesla.com with an owner-api `aud`. On 1.3.3 the `aud` check wins. On 1.3.4
only `ou_code` is consulted; if the claim is absent `baseURL` is `""` and every
request goes to `"/VIN/vehicle_data"`; if it is present the owner token is sent
to the Fleet host and gets 401. Either way sync yields nothing. (The claim set
of a live token should be confirmed, see section 6.)

---

## 2. Exact Owner-API delta between 1.3.3 and 1.3.4

`port-owner-api-removal-1.3.x` (cd5ef26, 9941b9c, 87e148a, ac3abff; merged as
PR #641) is 14 files, +33/-295. In code terms:

Removed from `TeslaAPI.py` (161 lines, `git diff d46616e ac3abff`):
- `regionURL["OwnerAPI"]`, `__authURL`, `__callbackURL`, `refreshURL`
  (auth.tesla.com), the hard-coded ownerapi `clientID`/`clientSecret`.
- `refreshClientID` default `"ownerapi"` -> `""`; `apiRefresh` now refuses
  without a configured client id and always uses fleet-auth (later re-pointed
  at auth.tesla.com for PKCE by 73023a8).
- The `email/password` and `apiLogin` branch of `car_api_available`
  (dead code: the changelog itself says `apiLogin` did not exist).
- `vehicles -> products` URL swap for owner-api in the vehicle-list fetch.
- `generateChallenge`, `getApiChallenge`, `saveApiToken` (ownerapi code
  exchange).
- `aud`-contains-`owner-api` classification and the decode-failure fallback in
  `setCarApiBearerToken`.

Removed elsewhere: `/teslaAccount/saveToken` route, `apiChallenge` template
global and `apiAvailable` flag (`HTTPControl.py`), the two login templates,
`carApiEmailPassword` IPC plumbing (`WebIPCControl.py`, `TWCManager.py`),
`teslaLoginAskLater` (`TWCMaster.py`, `HomeAssistant.py`).

Then `port-fleet-oauth-1.3.x` (48f2b2c..67289c1) re-added a login page and the
same route names for the Fleet flow, plus `teslaApiRedirectUri/ClientSecret/
Region/Scope` config keys (`config.json:148-179 @ 1.3.4`).

What 1.3.3 did instead (`git diff d46616e origin/release/1.3.3 -- TeslaAPI.py`):
kept all of the above unchanged and **added only** `TLS13Adapter` + a
`requests.Session` used for every Tesla call (43 lines), plus the TeslaMate
resync-timer fix (71123cc, also on 1.3.4 as ecdcf34). So the owner-api read path
on 1.3.3 is byte-for-byte the pre-split code; the only functional delta is TLS
1.3 enforcement.

Not Owner-related but relevant to reconvergence: 1.3.4 carries ~20 Fleet-cost
and BLE fixes that 1.3.3 lacks (wake delay 8caecd8/ceefa39, TeslaMate-asleep
trust 4b8bcc7, `refreshTokenIfNeeded` db9d8a0/8eac98d, BLE stop-asking
9bd4d63, lastLimitApplied unification 7b7f239, `VehiclePriority` "error"
handling 62da820). By patch-id (`git cherry 1.3.4 1.3.3 d46616e`) 1.3.3 has three patches 1.3.4
lacks: b9fb027 (TLS 1.3) and two variants of fixes 1.3.4 also carries
(4b07d9c vs 3001e2f, 45062a0 vs 52528ad). **1.3.4 is the right trunk; 1.3.3
contributes ~50 lines.**

---

## 3. Can a small change bring read-only Owner API back to 1.3.4 and main?

**Yes, conditionally.** Estimated 100-150 lines in `TeslaAPI.py`, ~20 in
`VehiclePriority.py`, ~10 in `TeslaMateVehicle.py`, plus tests; no templates,
no new routes if we accept paste-a-refresh-token as the manual path.

Why it is small: the read path never cared which host it talked to. Base
`update_vehicle_data` builds `baseURL/VIN/vehicle_data?endpoints=...`
(`TeslaAPI.py:1604-1611 @ d46616e`) and `is_awake` builds `baseURL/VIN`
(`:1507`), and 1.3.3 runs exactly that code against
`owner-api.teslamotors.com` today. So VIN-in-path and the `endpoints` parameter
are proven on owner-api; nothing in the read path needs rewriting.

### 3.1 Pieces to restore (all in `TeslaAPI.py` unless noted)

1. `regionURL["OwnerAPI"] = "https://owner-api.teslamotors.com/api/1/vehicles"`
   (1 line, from `:42 @ 1.3.3`).
2. `setCarApiBearerToken`: check `"owner-api" in "".join(aud)` **before**
   `ou_code` (restore `:1231-1232 @ 1.3.3` in front of `:1248 @ 1.3.4`). Also
   set `self.readOnly = True` on that branch. This alone un-breaks TeslaMate
   token sync on 1.3.4 and is a bugfix PR by itself.
3. `car_api_available`: the `vehicles -> products` swap (`:283-284 @ 1.3.3`).
   (Worth testing whether plain `/api/1/vehicles` still answers on owner-api;
   if so this piece is unnecessary.)
4. `apiRefresh`: three-way host selection. 1.3.4 already has `authTokenURL =
   auth.tesla.com/oauth2/v3/token` (`:33 @ 1.3.4`); add `if self.readOnly:
   client_id="ownerapi", url=authTokenURL` and drop the "no client id ->
   refuse" guard in that case (`:142-160 @ 1.3.4`).
5. `TLS13Adapter` + `self.session` from 1.3.3 (`:20-31, 113-122`), and route
   `wakeVehicle`, `get_car_api`, `apiRefresh`, F's `vehicleOnlineStates`
   (`:1180 @ F`, bare `requests.get`) through it. ~45 lines, mostly mechanical.
6. New `readOnly` property, **derived from the token classification in item
   2, never from `teslaProxy`.** Reason: `__init__` assigns `baseURL` from
   `teslaProxy` before any token arrives (`:93-96 @ 1.3.4`) and
   `setCarApiBearerToken` only classifies `if not self.baseURL` (`:1247`), so
   a proxy + TeslaMate-sync deployment would otherwise send an owner token to
   the proxy (401) and never be marked read-only. Item 2 must therefore set an
   explicit owner read URL even when `teslaProxy` pre-populated `baseURL`;
   simplest is to introduce `readBaseURL`/`commandBaseURL` already in PR 2
   (the second token slot in PR 3 then just fills the other one). The Vehicle
   Command proxy needs Fleet tokens, so Owner is read-only unconditionally.

### 3.2 Auth without the removed login flow

- **Primary: TeslaMate token sync.** Already pushes bearer+refresh and sets
  expiry to effectively infinite (`TeslaMateVehicle.py:232-234 @ 1.3.4`);
  `setCarApiRefreshToken` skips refresh when sync is on (`TeslaAPI.py:1272-1283
  @ 1.3.4`). With piece 2 above this works with zero further code and no token
  refresh in TWCManager at all. (Correction, checked on the live box: that
  deployment does NOT use TeslaMate token sync. Its config has syncTelemetry
  only, and its stored bearer token is a Fleet token, with aud
  fleet-api.prd.{na,eu} and the vehicle_cmds scopes. So this path is unverified
  there.)
- **Secondary: paste a refresh token.** `/teslaAccount/saveToken` already
  exists on 1.3.4 as a paste-back (`TeslaAPI.py:1221-1229`); extend
  `saveApiToken` to accept a bare refresh token (no `code=`) and call
  `setCarApiRefreshToken`, which triggers `apiRefresh` -> piece 4. ~15 lines,
  reuses the existing form. Tokens from any ownerapi-capable tool
  (TeslaMate, tesla_auth, Teslemetry's "legacy" flow) work.
- The ownerapi PKCE login page (`generateChallenge`/`getApiChallenge`, 2
  templates) is **not** needed and should stay removed.

### 3.3 Preventing commands on the owner endpoint

Two layers are required, because of 1.2/1.3:

1. `VehiclePriority._skip_module_for_command`: skip any module whose
   `readOnly` is true for `COMMAND_METHODS` (`VehiclePriority.py:65-76 @ main`;
   ~6 lines). This is exactly the "commands skip read-only integrations" rule.
2. Inside `TeslaAPI`, because `car_api_available(charge=...)` wakes cars
   itself (`:294-470 @ 1.3.4`) and main's `TeslaAPIEVSE` calls `setChargeRate`
   directly (`:140-142 @ main`): early-return `"error"`/`False` from
   `car_api_charge`, `setChargeRate`, `wakeVehicle`, `apply_charge_limit`,
   and skip the wake loop when `readOnly`; all command URLs are built from
   `commandBaseURL`, all reads from `readBaseURL`. ~10 lines. `TeslaAPIController`
   should also not expose a `TeslaAPIEVSE` for a read-only TeslaAPI
   (main `TeslaAPIEVSE.isReadOnly` exists at `:47` and `MergedEVSE` already
   filters on it, `MergedEVSE.py:154-177 @ main`), so on main the fix is one
   line: return `self.master.getModuleByName("TeslaAPI").readOnly`.

### 3.4 Size

Roughly: TeslaAPI.py +120/-20; VehiclePriority.py +10; TeslaAPIEVSE.py +2;
TeslaMateVehicle.py +5 (log which kind of token was synced); tests ~150.
Two PRs (bugfix piece 2 first, then the rest). This is well under the Fleet
OAuth port (+688) and comparable to the removal itself.

### 3.5 Risks

- **Tesla closes reads too.** Then `readOnly` TeslaAPI returns errors, the
  BLE/telemetry sources continue, and nothing else regresses, provided the
  ordered-fallback work in section 4 has landed. Until then a dead owner
  endpoint is no worse than today's dead TeslaMate sync on 1.3.4.
- **Refresh at auth.tesla.com with `client_id=ownerapi`.** 1.3.3 does this
  today and the user reports it works; it is the piece most likely to be
  turned off. TeslaMate sync sidesteps it entirely (TeslaMate refreshes).
  The refresh-loop guards from `better_refresh` (79743cd) are already in
  1.3.4 and main; the owner branch of `apiRefresh` must go through them too.
- **TLS 1.3 requirement.** 1.3.3 says auth.tesla.com now requires it. Needs
  Python >= 3.7 and OpenSSL >= 1.1.1; old Pi images may fail. Make the adapter
  tolerant (log and continue if `TLSVersion.TLSv1_3` is unavailable).
- **Single token slot.** Today `setCarApiBearerToken` refuses anything while
  TeslaMate sync is on (`:1233-1235 @ 1.3.4`), so "TeslaMate-synced owner
  token + pasted Fleet token" cannot coexist until the slot is split
  (section 5, PR 3).
- **Owner token JWT shape.** Claims may change; classification should fall
  back to "try `/products` on owner-api once" rather than hard-fail.

---

## 4. Target abstraction

Keep the two dispatchers that exist (VehiclePriority for commands and
module-level reads, PresenceSources for presence) and make them consumers of
**one** ordered list and **one** capability table. Do not add a third
mechanism.

### 4.1 Interfaces

```python
# lib/TWCManager/Vehicle/Integration.py
class Capability(Enum):
    READ_LIST = "read-list"          # enumerate VINs (seeds the vehicle model)
    READ_ONLINE = "read-online"      # online/asleep without waking
    READ_CHARGE = "read-charge"      # SoC, limit, charging state, amps
    READ_LOCATION = "read-location"  # lat/lon or at-home
    COMMAND = "command"              # start/stop, amps, charge limit
    WAKE = "wake"

class VehicleIntegration(Protocol):          # implemented by each Vehicle module
    name: str                                # "TeslaMate", "TeslaBLE", "OwnerAPI", "FleetAPI", "HomeAssistant"
    def configured(self) -> bool: ...        # enabled in config AND has credentials/binary
    def capabilities(self) -> frozenset[Capability]: ...
    @property
    def readOnly(self) -> bool: ...          # == COMMAND not in capabilities()
    cost: int                                # 0 local/free, 1 cloud free, 2 cloud billed (Fleet)
```

`TeslaAPI` exposes two integration views over one module and one vehicle
list: `OwnerAPI` (READ_LIST, READ_ONLINE, READ_CHARGE, READ_LOCATION; cost 1;
readOnly) and `FleetAPI` (all caps incl. COMMAND/WAKE via proxy; cost 2). Each
view carries its own token slot and base URL. This keeps `getModuleByName
("TeslaAPI")` and `CarApiVehicle` ownership intact for every caller in 1.2.

```python
# lib/TWCManager/Vehicle/IntegrationOrder.py
DEFAULT_ORDER = ["TeslaMate", "TeslaBLE", "OwnerAPI", "FleetAPI", "HomeAssistant"]

class IntegrationOrder:
    def __init__(self, master): ...          # reads config vehicle.integrationOrder, else DEFAULT_ORDER
    def ordered(self, capability, *, exclude=()) -> list[VehicleIntegration]:
        """configured() integrations having `capability`, in preference order."""
```

- `VehiclePriority._dispatch(name, ...)` becomes: `cap = COMMAND if name in
  COMMAND_METHODS else READ_*`; iterate `order.ordered(cap, exclude=skip)`.
  This replaces `calculateModulePriority`/`getModuleByPriority`; retry count
  derives from position, not from "priority // 10".
- `commandPolicy` is sugar: `ble_only` = `ordered(COMMAND)` filtered to
  TeslaBLE; `api_only` = filtered to FleetAPI/HomeAssistant; `prefer_ble` = the
  default order. Keep the three values for config compatibility; implement
  them as filters on the list.
- `presenceSources` (F: `["telemetry","ble","api"]`, `VehiclePresence.py:173-186
  @ F`) becomes `ordered(READ_LOCATION)` mapped through the existing
  `buildSources` factories (`PresenceSources.py:124-129 @ F`): TeslaMate ->
  `telemetrySource`, TeslaBLE -> `bleSource`, OwnerAPI/FleetAPI ->
  `apiSource`. Keep `presenceSources` as an override key for one release, then
  deprecate.
- `CarApiVehicle.update_charge` (F's BLE-then-API) becomes
  `for i in order.ordered(READ_CHARGE): if i.readCharge(vehicle): break`, with
  the telemetry short-circuit expressed as TeslaMate being first and "live".
- HomeAssistant gets a real slot (last by default) and stops being dead.

Cost is informational in 1.3.x (logged in `stats["moduleDispatch"]`); in 1.4 it
can drive "never use a cost-2 integration for a read a cost-1 one can answer".

---

## 5. Migration path

### 5.0 Release numbering and distribution (added 2026-10-10)

1.3.4 has never been released, so the reconverged release **is v1.3.4**. There's no 1.3.5.

- **GitHub releases:** the newest is v1.3.2 (2024-03-12). v1.3.3 is a tag with no release.
- **PyPI:** the newest is 1.3.2. 1.3.3 was never published.
- **Docker Hub `twcmanager/twcmanager`:** there are version images up to `v1.3.3` (2026-06-13, from the tag on the Owner-API line) and no `v1.3.4`.
  - The publish workflow (`.github/workflows/docker+pypi.yml`) builds on pushes to `main` and `ci_dev` and on `v*` tags only. Pushes to `release/1.3.x` publish nothing, so nobody installed "1.3.4" except from a git checkout.
  - `:latest` is rebuilt from every push to `main` (last built 2026-08-24, matching `0b7d143`), and `contrib/docker/docker-compose.yml` defaults to `:latest`. **Default Docker users are therefore already running 1.4-in-progress code.** That code has the Fleet `set_charging_amps` exposure (#672), the broken TeslaMate token sync (`ou_code` misclassification), and no Owner API read path.

Consequences:

- PR 1 and the #672 fix are urgent **on main**, not only for 1.4.0.
- Suggest pinning `contrib/docker/docker-compose.yml` to a version tag (`v1.3.4` once tagged), or treating `main` as shipping code.
- Upgrade sources that v1.3.4 must accept: v1.3.2, the v1.3.3 image (Owner API tokens in `carApi*`), and `:latest` (Fleet tokens).


Trunk for 1.3.x is `release/1.3.4`. Each PR lands on 1.3.4 and is cherry-picked
to main unless noted; 1.3.3 receives only PR 1 and then a release note that
points to 1.3.4.

| # | PR (size) | Branches | Composes with |
|---|---|---|---|
| 1 | **Owner-aud token classification + readOnly flag** (section 3.1 items 1, 2, 6; ~40 lines + tests). Fixes TeslaMate sync on 1.3.4. | 1.3.4, main, F (rebase); 1.3.3 gets only the `readOnly` flag (its aud check already exists) | none; prerequisite for everything |
| 2 | **Read-only Owner API path**: products swap, ownerapi refresh host, TLS13 session, refresh-token paste-back, read-only gates in TeslaAPI and VehiclePriority, `TeslaAPIEVSE.isReadOnly` (~150 lines + tests). | 1.3.4, main | The gate inside `TeslaAPI.setChargeRate` (3.3 layer 2) closes main's `TeslaAPIEVSE` bypass on its own; F's 3ea8622 (route `setTargetPower` through the queue) later makes that structural. No dependency on F. |
| 3 | **Second token slot**: settings keys `ownerApiBearerToken/RefreshToken/ExpireTime` beside the existing `carApi*`; per-slot `tokenSyncEnabled` gate; automatic migration on load (JWT `aud` has `owner-api` -> owner slot; `ou_code` and no owner aud -> fleet slot; undecodable -> owner, as 1.3.3 did). TeslaMate sync writes the owner slot only. | 1.3.4, main | wave D/E untouched; `TWCMaster.loadSettings/saveSettings` only |
| 4 | **IntegrationOrder + capabilities** (section 4), with `calculateModulePriority` deleted and `commandPolicy` reimplemented as filters. HomeAssistant enters the order. Config key `vehicle.integrationOrder`. **Moved to 1.4.0 (tentative, user 2026-10-10): it fits the EVSE abstraction work; 1.3.4 ships with two slots and a fixed order.** | main, F (not 1.3.4) | **Lands after wave A (#668 BLE worker) and B (#670 policy thread)**, which do not touch VehiclePriority's walk; **before** or together with wave E (presence tracker) so `presenceSources` is derived rather than a parallel list. Wave C (command queue, `VehicleCommandQueue.py @ F`) only resolves a module name and is unaffected. Wave D (charge-limit channels, `ChargeLimitRules.py @ F`) is per-channel and unaffected. |
| 5 | **Tag v1.3.4** on `release/1.3.4` after PRs 1-3 and the open backports (#674–#677) plus the two 1.3.3-only commits (b9fb027 is subsumed by PR 2; e8f907a docs rewritten). Delete the "two tracks" README section. | 1.3.4 -> tag | - |
| 6 | 1.4: move `carApiVehicles` out of `TeslaAPI` into a `VehicleRegistry` seeded by any READ_LIST integration (OwnerAPI, FleetAPI, HomeAssistant, or `settings["Vehicles"]` for BLE-only); telemetry attaches to the registry. `TeslaAPIController` enumerates from the registry and picks the command integration per VIN from the order. | main only | after F's waves merge |

**Can the Owner-vs-Fleet split collapse into "both configured, preference
order"?** Yes, after PR 3. A 1.3.3 user upgrading to 1.3.4 has: `carApi*`
token with owner aud -> migrated to the owner slot, `teslaApiClientID` unset ->
no Fleet slot, `refreshClientID` falls back to `ownerapi` for that slot; reads
work as before, commands go BLE (or nowhere, as today once Tesla cut
commands), and the Settings page offers the Fleet login as an optional
addition. A 1.3.4 user has a Fleet token (`ou_code`) -> fleet slot, no owner
slot; identical behaviour to today; enabling TeslaMate `syncTokens` adds the
owner slot and reads move to it (free) while commands stay on Fleet/proxy.

**Config migration.** No rewrite required. New keys are optional with
defaults: `vehicle.integrationOrder` (default per 4.1), `vehicle.commandPolicy`
(unchanged semantics), `vehicle.presenceSources` (honoured if present, else
derived). `teslaApiClientID` keeps its meaning; an owner slot never reads it.
Settings migration (PR 3) is one-time on load and idempotent.

**What 1.4 builds on.** `IntegrationOrder` + `Capability` are the seam between
`EVSEController`/`TeslaAPIController` and the vehicle modules: `TeslaAPIEVSE`
asks the order for the first COMMAND-capable integration for its VIN rather
than hard-coding `TeslaAPI`; `MergedEVSE`'s `isReadOnly`/`isLocal` filters
(`MergedEVSE.py:154-177 @ main`) are the same idea one layer up and can be
derived from the integration's capability set.

---

## 6. Open questions for the maintainer

1. Does TeslaMate's `tokens` table still hold auth.tesla.com/ownerapi tokens
   on current TeslaMate releases, and what claims does a fresh one carry
   (`aud`, `ou_code`)? The whole "TeslaMate sync is the free auth path"
   argument and PR 1's classifier depend on this. Please paste a decoded
   header/claims from a live token (secrets redacted).
2. Does plain `GET /api/1/vehicles` still answer on owner-api, or is the
   `/products` swap still required? (Determines whether 3.1 item 3 is needed.)
3. Is a refresh at auth.tesla.com with `client_id=ownerapi` still accepted
   today (1.3.3 users would know)? If not, the manual paste path is bearer-only
   and short-lived; TeslaMate sync remains the only durable owner path.
4. Acceptable to make `release/1.3.4` the single 1.3.x line and retire
   `release/1.3.3` after 1.3.4, with the README "two tracks" note replaced by
   "configure any subset; order decides"?
5. Should HomeAssistant be in the default order at all (it is a cloud,
   possibly billed path through HA's Fleet integration), or opt-in only?
6. Is `cost` worth surfacing in 1.3.x (stats/logging only) or deferred to 1.4?
7. Ordering of the in-flight waves: is landing IntegrationOrder (PR 4) before
   the presence tracker (wave E) acceptable, or should E merge first with
   `presenceSources` as-is and be re-based onto the derived order afterwards?

---

## Addendum (2026-10-10): answers to open questions 1–3 from a live TeslaMate

Taken from the user's TeslaMate, latest image. Claims were decoded inside the container; no token was printed.

1. **TeslaMate still holds Owner API tokens.**
   - **Access token:** `aud` = [`auth.tesla.com/oauth2/v3/userinfo`, `https://owner-api.teslamotors.com/`], `azp` = `ownerapi`, `iss` = `auth.tesla.com/oauth2/v3`, `scp` = [email, offline_access, openid], lifetime 8 h.
   - **It ALSO carries `ou_code: "NA"`.** That is exactly why 1.3.4/main's `setCarApiBearerToken`, which checks `ou_code` alone, classifies a synced owner token as a Fleet token. PR 1's classifier must check `aud` for owner-api *before* `ou_code`, and must not treat `ou_code` as proof of a Fleet token.
   - **Refresh token:** a JWT with `aud` = `auth.tesla.com/oauth2/v3/token` and about a 90-day lifetime.
2. **Read path still works.** TeslaMate's own `list_vehicles` succeeded just now (1 vehicle). Its logs show owner-api `GET /api/1/vehicles/<id>` and `/vehicle_data`, with the only errors being 408 (car asleep) and transient connection errors. TeslaMate addresses vehicles by numeric id. Not verified: whether owner-api accepts the VIN in the path, as 1.3.3 does, and whether it needs the `/products` swap. TWCManager's PR 2 tests should confirm both against a live token.
3. **Refresh with `client_id=ownerapi` still works.** TeslaMate refreshes every 6 h. Its logs show `POST https://auth.tesla.com/oauth2/v3/token -> 200` at 04:23 and 10:23 today. The paste-a-refresh-token path is therefore durable, not bearer-only. One caution: TWCManager refreshing a token that TeslaMate also refreshes would rotate it out from under TeslaMate. With sync on, TWCManager must not refresh, which is already the case on 1.3.4 (`setCarApiRefreshToken` skips the refresh when sync is on).
