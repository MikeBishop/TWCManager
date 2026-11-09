# Live Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The home page (both themes), Policy, Vehicles and Vehicle details pages stay current while open, each filled from a documented JSON API that the browser formats.

**Architecture:** A new `Control/Views.py` builds each page's raw data (and its fingerprint) from cached state only; `HTTPControl.py` serves it as `/api/getChargingPoints`, `/api/getVehicles`, `/api/getVehicle/<VIN>` and `/api/getPolicyState`. Templates render structure plus `data-*` hooks; `static/js/format.js` (every display rule, pure functions) and `static/js/live.js` (one shared poller) fill the hooks on load and on every poll. The Python display helpers leave the lib; their wording tests move to `node --test`.

**Tech Stack:** Python 3.8+, `http.server`, Jinja2, plain DOM JavaScript (classic scripts), Node's built-in test runner (no npm, no package.json), pytest.

**Spec:** `docs/superpowers/specs/2026-10-30-live-pages-design.md` (archived on `origin/docs/vehicle-model-planning` as `superpowers/specs/2026-10-30-live-pages-design.md`).

**Base:** branch `feat/live-pages` from `upstream/main` (f094c7c8). `docs/superpowers/` is git-excluded locally (`.git/info/exclude`): never `git add` it.

## Global Constraints

- Python 3.8 (`python_requires=">= 3.8"`): no `X | Y` types, no `list[str]` annotations, no `str.removeprefix`.
- Endpoints are GET, return JSON with `Cache-Control: no-store`, same access as the existing `/api/get*` routes; `/api/getVehicle/` is a prefix match.
- Handlers read cached state only: never `vehicle.read()`, `Gen3TWC.refreshVitals()`, or any provider/network I/O; no long-held locks.
- No token, refresh token, client secret or webhook URL in any response.
- Times are epoch seconds; each response carries `now` (server epoch seconds); ages are computed from `now`, never the browser clock.
- Python keeps no copy of wording JS produces. Templates render structure and placeholders, never a formatted live value.
- Today's text is the spec for every formatter (exact strings below). No layout or wording changes beyond what moving the formatting requires.
- `format.js` and `live.js` are classic scripts defining one global each (`Format`, `Live`) and `module.exports` when `module` exists. No `.mjs`. No jQuery in either.
- Scripts load per page in the templates that use them, not in `bootstrap.html.j2`.
- JS tests: `tests/js/*.test.js`, CommonJS, run with `node --test tests/js/`. No package.json.
- Polling: 3 s on both home pages, 5 s on Policy, Vehicles, Vehicle details; paused while `document.visibilityState === "hidden"`, immediate fetch on return.
- User-facing docs describe capabilities, not internals; say "EVSE" or "charging station", never "charger", for the wall unit.
- `/api/getSlaveTWCs` keeps its exact output.
- Never commit `.github/workflows/` (the PAT rejects it); the CI step is handed to the operator in Task 11.

## Review Focus

1. **Policy values that JSON can't carry.** A `modules.<Name>.<attr>` macro can resolve to an object, a method or `float("nan")`; Python's `json.dumps` writes `NaN`, which `JSON.parse` rejects, so one odd value would blank the whole page. Expect the API to answer 200 with non-finite floats as `null` and other objects as their `str()`. Test: Task 2 `test_json_safe_*`, Task 5 `test_policy_state_survives_odd_values`.
2. **Vehicle detail URLs that don't name a known car.** Lower-case VIN, URL-encoded or trailing-slash path, empty segment, garbage, and a car forgotten while its page is open. Expect lower-case to find the car, everything else a JSON 404 without a traceback, and an unknown-VIN page that does not poll (otherwise a 404-triggered reload would loop every 5 s). Test: Task 4 `test_get_vehicle_route_variants`, Task 8 `test_unknown_vin_page_does_not_poll`.
3. **A car name or message carrying markup.** Names, BLE attempt messages and reasons now reach the page through JS. Expect them shown as text, never parsed as HTML. Test: Task 7 `live.js never assigns innerHTML` and Task 8 `test_names_and_error_are_escaped` (form error still server-escaped; name absent from server HTML).
4. **Points with half their facts missing.** An idle Gen2 TWC with no car, an anonymous car, a Gen3 unit before its first vitals, a car-only point with no desired rate. Expect each listed with blanks or zeros, never a 500. Test: Task 3 `test_points_with_missing_facts`, Task 6 `pointKind`/`blank` cases.
5. **A fresh install's settings.** No `Vehicles` key, empty `VehicleGroups`, no Fleet token, no watch. Expect `/api/getVehicles` to answer with empty history and `spend` flags false. Test: Task 4 `test_vehicles_view_on_fresh_settings`.

---

## File Structure

| File | Responsibility |
|---|---|
| `lib/TWCManager/Control/Views.py` (create) | Raw page data and fingerprints: `fingerprint`, `jsonSafe`, `slaveTotals`, `chargingPointsView`, `vehiclesView`, `vehicleView`, `policyTree`, `policyLayout`, `policyStateView`, and the data helpers they use. |
| `lib/TWCManager/Control/HTTPControl.py` (modify) | Routes and `sendJSON`; template globals; loses `ageText`, `SOURCE_NAMES`, `sourceName`, `providerLines`, `heldLimitText`, `watchLine`, `_spendShown`, `_usd`, `_lastMonth`, `_teleText`, `spendLines`, `carSpend`, `PRESENCE_TEXT`, `pendingCommands`, `do_get_policy`. |
| `lib/TWCManager/Control/static/js/format.js` (create) | Every display rule, pure functions. |
| `lib/TWCManager/Control/static/js/live.js` (create) | The shared poller and DOM binder. |
| `lib/TWCManager/Control/static/js/vehicleImage.js` (modify) | Exposes `drawVehicleImage(img)` for entries added live. |
| `lib/TWCManager/Control/static/js/status.js` (modify) | `.VINClick` opens `/vehicleDetail/<vin>` (replaces `loadVIN`). |
| `themes/Default/{vehicles,vehicleDetail,policy,showStatus,main,jsrefresh}.html.j2`, `themes/Modern/{main,jsrefresh}.html.j2` (modify) | Structure + hooks. |
| `tests/unit/live_helpers.py` (create) | `callAPI(master, path)` handler harness. |
| `tests/unit/test_live_views.py` (create) | Views data, fingerprints, no I/O, no secrets. |
| `tests/unit/test_policy_view.py` (create) | Walker, layout, policy state. |
| `tests/unit/test_vehicles_page.py`, `test_vehicle_detail_page.py` (modify) | Keep form/action/escaping/structure tests; wording tests move to JS; pending-selection tests move to data. |
| `tests/js/format.test.js`, `tests/js/live.test.js` (create) | Wording rules; live.js pure helpers. |
| `docs/modules/control_HTTP_API/{getChargingPoints,getVehicles,getVehicle,getPolicyState}.md` (create), `docs/modules/Control_HTTP.md`, `CHANGELOG.md` (modify) | API docs. |

### The hook vocabulary (used by Tasks 7–10)

`live.js` reads these attributes; templates write them. Paths are dot-separated over the merged response. A segment applied to an array selects the element whose `key` (else `id`) equals it, else a numeric index. A path starting with `.` is relative to the enclosing keyed-list item.

| Attribute | Effect each poll |
|---|---|
| `data-field="<path>"` `[data-format="<name>"]` | `el.textContent = Format[name](value, ctx)`; without `data-format`, `null`/`undefined` → `""`, else `String(value)`. `ctx = {data, el, item}`. |
| `data-show="<path>"` `[data-show-if="<name>"]` | `el.hidden = !(name ? Format[name](value, ctx) : Live._truthy(value))`. `_truthy`: false for `null`, `undefined`, `false`, `0`, `""`, `[]`. |
| `data-class-if="<path>" data-class-true="<c>" data-class-false="<c>"` | Toggles the two classes by `Live._truthy(value)`. |
| `data-list="<path>" data-row="<name>"` | Replaces the element's children with one `<tr>` per array item, one `<td>` per string in `Format[name](item, ctx)` (text only). |
| `data-keyed-list="<path>" data-template="<id>"` | Keyed by `item.key ?? item.id`: clones `<template id>` for a new key (sets `data-key`), removes gone keys, keeps order, binds hooks inside with `item`. |
| `img[data-image]` inside a keyed entry | On add: `img.dataset.vin = item.vin || ""`, `img.dataset.appearance = JSON.stringify(item.appearance || {})`, then `window.drawVehicleImage(img)` if defined. |

`live.js` never writes `.value`, `.checked` or `.disabled` of a form control and never assigns `innerHTML`.

---

### Task 1: Node toolchain and core formatters

**Files:**
- Create: `lib/TWCManager/Control/static/js/format.js`
- Test: `tests/js/format.test.js`

**Interfaces:**
- Produces (all on global `Format`, exported via `module.exports`):
  - `age(seconds: number|null) -> string`
  - `ageAt(at: number|null, ctx) -> string` = `age(at == null ? null : ctx.data.now - at)`
  - `sourceName(raw: string) -> string`
  - `usd(amount: number) -> string`
  - `count(n: number) -> string` (en-US thousands separators)
  - `pyStr(v) -> string`
  - `duration(seconds: number) -> string`

- [ ] **Step 1: Install Node if missing**

Run: `node --version || (apt-get update && apt-get install -y nodejs)`
Expected: `v18` or later (needed for `node --test` with a directory).

- [ ] **Step 2: Write the failing tests** in `tests/js/format.test.js`

```js
const test = require("node:test");
const assert = require("node:assert/strict");
const F = require("../../lib/TWCManager/Control/static/js/format.js");

test("age", () => {
  assert.equal(F.age(null), "never");
  assert.equal(F.age(30), "30 s ago");
  assert.equal(F.age(90), "1 min ago");
  assert.equal(F.age(3600 * 5), "5 h ago");
  assert.equal(F.age(86400 * 3), "3 d ago");
  assert.equal(F.age(59.9), "59 s ago"); // int() truncation
  assert.equal(F.ageAt(100, { data: { now: 130 } }), "30 s ago");
  assert.equal(F.ageAt(null, { data: { now: 130 } }), "never");
});

test("sourceName", () => {
  assert.equal(F.sourceName("Gen2TWC"), "TWC");
  assert.equal(F.sourceName("TeslaBLE"), "BLE");
  assert.equal(F.sourceName("FleetAPICached"), "Fleet API (cached)");
  assert.equal(F.sourceName("Gen3TWC"), "Gen3 Wall Connector");
  assert.equal(F.sourceName("SomethingNew"), "SomethingNew");
});

test("usd keeps a third decimal below one cent", () => {
  assert.equal(F.usd(0), "$0.00");
  assert.equal(F.usd(0.002), "$0.002");
  assert.equal(F.usd(0.31), "$0.31");
});

test("count", () => assert.equal(F.count(41800), "41,800"));

test("pyStr matches Python str() for JSON values", () => {
  assert.equal(F.pyStr(true), "True");
  assert.equal(F.pyStr(null), "None");
  assert.equal(F.pyStr(5), "5");
  assert.equal(F.pyStr(0.5), "0.5");
  assert.equal(F.pyStr("tm_hour"), "tm_hour");
  assert.equal(F.pyStr(["a", 1, false]), "['a', 1, False]");
});

test("duration matches str(timedelta) without microseconds", () => {
  assert.equal(F.duration(3723.9), "1:02:03");
  assert.equal(F.duration(86400 + 5), "1 day, 0:00:05");
  assert.equal(F.duration(2 * 86400), "2 days, 0:00:00");
});
```

- [ ] **Step 3: Run to verify failure**

Run: `node --test tests/js/`
Expected: FAIL, `Cannot find module .../format.js`.

- [ ] **Step 4: Implement `format.js`**

Wrapper shape (the rest of the file follows it):

```js
var Format = (function () {
  var F = {};
  // ... functions ...
  return F;
})();
if (typeof module !== "undefined") { module.exports = Format; }
```

Values copied from `HTTPControl.py:37-65` (`ageText`, `SOURCE_NAMES`) and `:132-134` (`_usd`). `pyStr`: strings as-is; `true/false/null` → `True/False/None`; numbers `String(n)` (a float with an integral value prints without `.0`, the one unavoidable difference after JSON); arrays `"[" + items.map(repr).join(", ") + "]"` where `repr` quotes strings with `'`. `count`: `n.toLocaleString("en-US")`.

- [ ] **Step 5: Run to verify pass**

Run: `node --test tests/js/`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/TWCManager/Control/static/js/format.js tests/js/format.test.js
git commit -m "Live pages: format.js core rules under node --test"
```

---

### Task 2: Views module: fingerprint, JSON safety, handler harness

**Files:**
- Create: `lib/TWCManager/Control/Views.py`
- Modify: `lib/TWCManager/Control/HTTPControl.py` (add `sendJSON` method to the handler)
- Create: `tests/unit/live_helpers.py`
- Test: `tests/unit/test_live_views.py`

**Interfaces:**
- Produces:
  - `Views.STARTED: float` (module import time = service start)
  - `Views.fingerprint(*shape) -> str`: first 12 hex chars of `sha1(json.dumps([STARTED, *shape], sort_keys=True, default=str))`
  - `Views.jsonSafe(obj) -> obj`: recursively copies dicts (keys `str()`), lists/tuples/sets (→ list); non-finite floats → `None`; `bool/int/float/str/None` as-is; anything else → `str(obj)`
  - `HTTPControlHandler.sendJSON(self, data, code=200) -> None`: status `code`, `Content-type: application/json`, `Cache-Control: no-store`, body `json.dumps(Views.jsonSafe(data))`; swallows `BrokenPipeError` via `debugLogAPI`
  - `tests/unit/live_helpers.callAPI(master, path) -> (status: int, headers: dict, body: bytes)`: builds `CreateHTTPHandlerClass(master)`, makes an instance with `cls.__new__(cls)`, sets `path`, `url = urllib.parse.urlparse(path)`, `client_address = ("127.0.0.1", 0)`, `wfile = io.BytesIO()`, replaces `send_response`/`send_header`/`end_headers` with recorders, calls `do_API_GET()`

- [ ] **Step 1: Write the failing tests**

```python
def test_fingerprint_is_stable_and_shape_sensitive():
    assert fingerprint("a", ["x"]) == fingerprint("a", ["x"])
    assert fingerprint("a", ["x"]) != fingerprint("a", ["y"])
    assert len(fingerprint()) == 12

def test_fingerprint_changes_with_start_time(monkeypatch):
    before = fingerprint("a")
    monkeypatch.setattr(Views, "STARTED", Views.STARTED + 1)
    assert fingerprint("a") != before

def test_json_safe_non_finite_and_objects():
    out = jsonSafe({"a": float("nan"), "b": [float("inf"), 1.5], 3: object, "c": (1,)})
    assert out["a"] is None and out["b"] == [None, 1.5] and out["c"] == [1]
    assert out["3"].startswith("<class")
    json.loads(json.dumps(out, allow_nan=False))
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v`
Expected: FAIL, `ModuleNotFoundError: TWCManager.Control.Views`.

- [ ] **Step 3: Implement `Views.STARTED`, `fingerprint`, `jsonSafe`, `HTTPControlHandler.sendJSON`, `live_helpers.callAPI`**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_live_views.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/Views.py lib/TWCManager/Control/HTTPControl.py tests/unit/live_helpers.py tests/unit/test_live_views.py
git commit -m "Live pages: Views fingerprint, JSON-safe responses, handler harness"
```

---

### Task 3: `/api/getChargingPoints`

**Files:**
- Modify: `lib/TWCManager/Control/Views.py`, `lib/TWCManager/Control/HTTPControl.py:728-807` (getSlaveTWCs totals), route in `do_API_GET`
- Test: `tests/unit/test_live_views.py` (fixtures from `tests/unit/test_charging_points.py` / `gen2_helpers.py`)

**Interfaces:**
- Consumes: `fingerprint`, `sendJSON`, `callAPI` (Task 2)
- Produces:
  - `Views.slaveTotals(master) -> dict`: exactly the `"total"` dict `getSlaveTWCs` writes today (keys `carsCharging, lastAmpsOffered, lifetimekWh, maxAmps, reportedAmpsActual, TWCID="total"`, same rounding, including car-side desired amps). `getSlaveTWCs` now calls it.
  - `Views.chargingPointsView(master) -> dict`:
    ```
    {"fingerprint": fingerprint("home"), "now": float,
     "points": [{
        "id": point.ID, "controllers": point.controllers, "local": bool(point.localEndpoints),
        "vin": str|None, "name": str, "anonymous": bool, "appearance": dict,
        "ampsOffered": float, "ampsDrawn": float, "volts": [a, b, c],
        "minAmps": float, "maxAmps": float, "soc": num|None, "chargeLimit": num|None,
        "gen2": None | {"twcid", "state", "version", "lifetimekWh", "maxAmps",
                        "lastHeardAt", "currentVIN", "lastVIN", "chargingSince": float|None}}],
     "total": slaveTotals(master)}
    ```
    Car: `master.vehicleRegistry.get(point.key)` (None for an endpoint-ID key). `ampsOffered`: Gen2 member `lastAmpsOffered`; else Gen3 member `convertWattsToAmps(getattr(e, "lastTarget", 0) or 0)`; else sum of `master.desired.get(e.vehicle.key, AMPS).value` over vehicle members (0 when none). `ampsDrawn`: Gen2 `reportedAmpsActual`; Gen3 `currentAmps`; else car `value("actualCurrent") or 0`. Min/max: `point.convertWattsToAmps(point.minPower|maxPower, point.currentVoltage)`. `chargingSince`: `lastChargingStart` if `> 0` else `None`. `lastHeardAt`: `timeLastRx`.
  - Route `GET /api/getChargingPoints` → `self.sendJSON(Views.chargingPointsView(master))`.

- [ ] **Step 1: Write the failing tests**

```python
def test_slave_totals_match_get_slave_twcs(gen2_master):
    status, _, body = callAPI(gen2_master, "/api/getSlaveTWCs")
    assert json.loads(body)["total"] == slaveTotals(gen2_master)

def test_points_list_every_kind(mixed_master):  # one Gen2 with car, one Gen3, one car-only
    view = chargingPointsView(mixed_master)
    kinds = sorted(tuple(p["controllers"]) for p in view["points"])
    assert ("Gen3TWCs",) in kinds and ("VehicleEndpoints",) in kinds
    gen2 = next(p for p in view["points"] if p["gen2"])
    assert gen2["gen2"]["twcid"] == "8244" and gen2["vin"] == VIN
    car = next(p for p in view["points"] if p["controllers"] == ["VehicleEndpoints"])
    assert car["local"] is False and car["ampsOffered"] == 16  # its desired AMPS
    assert car["gen2"] is None

def test_points_with_missing_facts(idle_master):  # Review Focus 4
    view = chargingPointsView(idle_master)  # idle Gen2 (no car), Gen3 with empty vitals
    for p in view["points"]:
        assert p["vin"] is None and p["name"] == "" and p["soc"] is None
        assert isinstance(p["ampsDrawn"], float)
    json.dumps(view, allow_nan=False)

def test_points_route_headers(mixed_master):
    status, headers, body = callAPI(mixed_master, "/api/getChargingPoints")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert json.loads(body)["fingerprint"] == fingerprint("home")

def test_points_never_fetch(mixed_master, monkeypatch):
    monkeypatch.setattr(Gen3TWC, "refreshVitals", Mock(side_effect=AssertionError))
    monkeypatch.setattr(Vehicle, "read", Mock(side_effect=AssertionError))
    chargingPointsView(mixed_master)
```

Build the three master fixtures from the helpers `tests/unit/test_charging_points.py` already uses (heard-from Gen2 slave, `Gen3TWCs` module with `allEVSEs`, a registry car plugged in with a `SET_AMPS` provider and a desired AMPS of 16).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v -k "points or slave_totals"`
Expected: FAIL, `ImportError: cannot import name 'slaveTotals'`.

- [ ] **Step 3: Implement `slaveTotals`, `chargingPointsView`, the route; make `getSlaveTWCs` use `slaveTotals`**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_live_views.py tests/unit/test_charging_points.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/Views.py lib/TWCManager/Control/HTTPControl.py tests/unit/test_live_views.py
git commit -m "Live pages: /api/getChargingPoints lists every charging point"
```

---

### Task 4: `/api/getVehicles` and `/api/getVehicle/<VIN>`

**Files:**
- Modify: `lib/TWCManager/Control/Views.py`, `HTTPControl.py` (routes only; old helpers stay until Task 8)
- Test: `tests/unit/test_live_views.py` (reuse `master()` and `spending()` from `tests/unit/test_vehicles_page.py`)

**Interfaces:**
- Consumes: Tasks 2–3
- Produces:
  - `Views.spendShown(master) -> (fleet: bool, telemetry: bool)` (logic of `HTTPControl._spendShown`)
  - `Views.providerClaims(master, vehicle) -> list` of `{"provider", "status", "commands": bool, "readOnlyReason": str|None}`: skips `OwnerAPI`/`FleetAPI` claims whose token isn't held (`ownerTokenHeld()`/`fleetTokenHeld()`), reason from `ownerReadOnlyReason(vehicle.attachment("TeslaAPI"))` / `fleetReadOnlyReason()` only when `commands` is false; order of `vehicle.claims`.
  - `Views.pendingCommandData(master, vehicle) -> list` of `{"aspect", "value", "inFlight": {"provider", "since"}|None, "said": str|None, "lastOutcome": {"kind", "detail", "provider", "at"}|None}`. Row selection exactly as `pendingCommands` (`HTTPControl.py:206-233`): skip a desire with no record; skip satisfied/settled ones unless in flight. `said` = `master.reconciler.blockedReason(...)`; `detail` = `last.detail.replace(RULES, "")`; `provider` = `rec.lastProvider`; `at` = `rec.lastOutcomeAt`. Never creates desired state.
  - `Views.vehicleEntry(master, vehicle, fleet, telemetry) -> dict`:
    ```
    {"key", "vin", "name", "anonymous", "point", "appearance",
     "presence": presence(master, v),          # "home" | "presumed" | "notHome"
     "watch": master.watch.status(v) if master.watch else {"watched": False, "why": "off"},
     "providers": providerClaims(...),
     "lastSeenAt": float, "lastSeenSource": str,
     "heldLimit": {"held", "outside"} | None,
     "spend": master.fleetSpend.car(vin) if (fleet or telemetry) and not anonymous else None}
    ```
    `lastSeenAt` = `now - summary()["lastSeenAge"]` computed with the same `now` as the response.
  - `Views.vehiclesView(master) -> dict`:
    ```
    {"fingerprint": fingerprint("vehicles", keys, groups, historyKeys, fleet or telemetry),
     "now", "budget": master.watchBudget.tokens(),
     "spend": {"fleet", "telemetry", "month": fleetSpend.month() if fleet or telemetry else None},
     "vehicles": [vehicleEntry(...) for v in registry.vehicles()],
     "history": {key: {"chargeSessions", "totalkWh"}}}
    ```
    `keys` = sorted registry keys; `groups` = sorted `VehicleGroups` names; `historyKeys` = sorted `Vehicles` keys; settings read under `settingsLock` with `.get(..., {})`.
  - `Views.vehicleView(master, vin) -> dict|None`: `None` when `registry.get(vin)` is None, else
    `{"fingerprint": fingerprint("vehicle", vin.upper(), True, groups), "now", "budget", "spend": {"fleet", "telemetry"}, "vehicle": dict(vehicleEntry(...), pending=pendingCommandData(...), ble=ble.bleStatus(vin) if TeslaBLE loaded else None, chargeSessions=settings Vehicles.get(vin, {}).get("chargeSessions", 0))}`.
  - Template global `fingerprint(page, vin=None)` returning the same string the view would (`"vehicles"` / `"vehicle"` / `"policy"` / `"home"`); implement as `Views.pageFingerprint(master, page, vin=None) -> str` used by both views and the global.
  - Routes: `GET /api/getVehicles`; `GET /api/getVehicle/<VIN>` where VIN = `urllib.parse.unquote(path[len("/api/getVehicle/"):]).strip("/")`; `None` → `sendJSON({"error": "unknown vehicle"}, 404)`.

- [ ] **Step 1: Write the failing tests** (data counterparts of the page tests Task 8 retires)

```python
def test_vehicle_entry_raw_fields():
    m = master()
    e = vehiclesView(m)["vehicles"][-1]  # sorted: the VIN after "anon:8244"
    assert e["vin"] == VIN and e["presence"] == "presumed"
    assert e["heldLimit"] == {"held": 80, "outside": 90}
    assert e["providers"] == [{"provider": "TeslaBLE", "status": "paired", "commands": True, "readOnlyReason": None}]
    assert e["watch"] == {"watched": False, "why": "off"} and e["spend"] is None
    assert abs(e["lastSeenAt"] - time.time()) < 5

@pytest.mark.parametrize("held", ["Owner", "Fleet"])
def test_a_cloud_api_without_its_token_is_not_listed(held): ...  # port of test_vehicles_page.py:229-245 against providerClaims

def test_read_only_reason_only_when_it_cannot_command(): ...  # port of :201-227: reasons present for commands=False, None otherwise

def test_pending_data_rows(): ...  # ports of test_vehicle_detail_page.py:241-375 asserting dict rows, e.g.
    # in flight: row["inFlight"] == {"provider": "TeslaBLE", "since": a.since}
    # held: row["lastOutcome"]["detail"] == "held: driving" and row["lastOutcome"]["provider"] == "Gen2TWC"
    # said wins: row["said"] == "hands off: battery below minChargeLevel"
    # hides satisfied/settled, shows drifted, held-asleep cases: same aspect lists as today
    # m.desired.keys() == [] after the view

def test_spend_in_views():
    m = master(); s = spending(m); s.request(VIN, "vehicle_data", 0.30)
    v = vehiclesView(m)
    assert v["spend"]["fleet"] and not v["spend"]["telemetry"]
    assert v["spend"]["month"]["api"] == pytest.approx(0.30)
    assert v["vehicles"][-1]["spend"]["requests"] == 1

def test_vehicles_fingerprint_follows_shape():
    m = master(); before = vehiclesView(m)["fingerprint"]
    assert before == pageFingerprint(m, "vehicles")
    m.settings["VehicleGroups"]["Guests"] = {"Members": []}
    assert vehiclesView(m)["fingerprint"] != before
    m2 = master(); spending(m2)  # a Fleet token now held: the spend column shows
    assert vehiclesView(m2)["fingerprint"] != before

def test_vehicles_view_on_fresh_settings():  # Review Focus 5
    m = master(); m.settings = {"VehicleGroups": {}}
    v = vehiclesView(m)
    assert v["history"] == {} and v["spend"] == {"fleet": False, "telemetry": False, "month": None}

def test_no_secrets_in_vehicle_apis():
    m = master(); spending(m)  # fleetSlot.accessToken == "tok"
    m.fleetSpend.request(VIN, "wake_up", 0.02)
    for body in (json.dumps(vehiclesView(m)), json.dumps(vehicleView(m, VIN))):
        assert '"tok"' not in body and "token" not in body.lower() and "secret" not in body.lower()

def test_vehicle_views_never_read_providers(monkeypatch):
    monkeypatch.setattr(Vehicle, "read", Mock(side_effect=AssertionError))
    m = master()
    api = Mock(spec=["ownerTokenHeld", "fleetTokenHeld", "ownerReadOnlyReason", "fleetReadOnlyReason", "fleetSlot"])
    m.getModuleByName = lambda n: api if n == "TeslaAPI" else None
    vehiclesView(m); vehicleView(m, VIN)

def test_get_vehicle_route_variants():  # Review Focus 2
    m = master()
    for path in ("/api/getVehicle/" + VIN.lower(), "/api/getVehicle/" + VIN + "/"):
        status, _, body = callAPI(m, path)
        assert status == 200 and json.loads(body)["vehicle"]["vin"] == VIN
    for path in ("/api/getVehicle/", "/api/getVehicle/5YJ3E1EA1KF000009", "/api/getVehicle/%3Cx%3E"):
        status, headers, body = callAPI(m, path)
        assert status == 404 and json.loads(body) == {"error": "unknown vehicle"}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v -k "vehicle or pending or spend or secrets"`
Expected: FAIL on missing names.

- [ ] **Step 3: Implement the functions and routes above**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q`
Expected: PASS (old page tests untouched and still green).

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: /api/getVehicles and /api/getVehicle/<VIN>"
```

---

### Task 5: `/api/getPolicyState` and the one policy walker

**Files:**
- Modify: `lib/TWCManager/Control/Views.py`, `HTTPControl.py` (route; template globals `policyTree`, `policyLayout`)
- Test: `tests/unit/test_policy_view.py`

**Interfaces:**
- Produces:
  - `Views.policyTree(policy) -> dict`: the root group `{"id": "g", "kind": "group", "op": "AND", "children": [...]}`; for each `(m, c, v)` of the group's zipped lists, a child is a group (op flipped, `id = parent + "-" + i`) when all three are lists, else a leaf `{"id", "kind": "leaf", "match": m, "condition": c, "value": v}`. Node ids index the raw nesting, so a one-item group keeps its own id.
  - `Views.policyState(mod_policy, tree) -> dict` id → state. Leaf: `{"match": policyValue(m), "value": policyValue(v), "truth": bool(doesConditionMatch(m, c, v, False))}`. Group: `{"truth": all(...)}` for AND, `any(...)` for OR over its children's truth. (`doesConditionMatch` logs at INFO8 per leaf; accepted, per spec.)
  - `Views.policyLayout(mod_policy) -> list` of blocks, porting `do_get_policy`'s bucketing (`HTTPControl.py:1516-1574`) exactly: `{"type": "policy", "index": i, "category": None|"Default"|"Default, Modified"|"Custom"}` or `{"type": "ext", "name": "Emergency"|"Before"|"After", "items": [policy blocks]}` (an ext block with empty `items` is the "no policies" marker).
  - `Views.policyStateView(master) -> {"fingerprint": fingerprint("policy", names), "now", "active": str(mod.active_policy), "policies": [{"name", "nodes": policyState(...)}]}` in `charge_policy` order.
  - Route `GET /api/getPolicyState`.

- [ ] **Step 1: Write the failing tests**

```python
NESTED = {"name": "N", "match": ["a", ["b", "c"]], "condition": ["eq", ["gt", "lt"]], "value": [1, [2, 3]]}

def test_tree_ids_and_ops():
    t = policyTree(NESTED)
    assert [c["id"] for c in t["children"]] == ["g-0", "g-1"]
    assert t["children"][1]["op"] == "OR" and t["children"][1]["children"][0]["id"] == "g-1-0"

def test_single_item_group_keeps_its_slot():
    t = policyTree({"name": "S", "match": [["x"]], "condition": [["eq"]], "value": [[1]]})
    assert t["children"][0]["kind"] == "group" and t["children"][0]["children"][0]["id"] == "g-0-0"

def test_state_resolves_both_sides_and_groups(policy_mod):  # Policy module over a fake master
    policy_mod.master.settings["x"] = 5
    p = {"name": "P", "match": ["settings.x", ["settings.x", "tm_hour"]],
         "condition": ["gt", ["eq", "lt"]], "value": [3, [4, -1]]}
    s = policyState(policy_mod, policyTree(p))
    assert s["g-0"] == {"match": 5, "value": 3, "truth": True}
    assert s["g-1"]["truth"] is False and s["g"]["truth"] is False

def test_layout_default_set(policy_mod): # default policies only
    blocks = policyLayout(policy_mod)
    assert [b["name"] for b in blocks if b["type"] == "ext"] == ["Emergency", "Before", "After"]
    assert all(b["category"] == "Default" for b in blocks if b["type"] == "policy")

def test_layout_custom_bucket_and_modified(policy_mod): ...  # an extension policy lands in the "Before" ext block's items; a renamed-condition default reads "Default, Modified"
def test_layout_replaced(policy_mod): ...  # override with no default names: every block is {"type": "policy", "category": "Custom"}

def test_policy_state_survives_odd_values(policy_mod):  # Review Focus 1
    policy_mod.master.modules = {"Odd": {}}
    policy_mod.master.getModuleByName = lambda n: SimpleNamespace(nan=float("nan"), obj=object())
    policy_mod.charge_policy = [{"name": "O", "match": ["modules.Odd.nan", "modules.Odd.obj"],
                                 "condition": ["eq", "eq"], "value": [1, 1]}]
    status, _, body = callAPI(policy_mod.master, "/api/getPolicyState")
    nodes = json.loads(body)["policies"][0]["nodes"]
    assert status == 200 and nodes["g-0"]["match"] is None and nodes["g-1"]["match"].startswith("<object")

def test_policy_fingerprint_follows_names(policy_mod): ...  # renaming a policy changes it; equals pageFingerprint(master, "policy")
```

Build `policy_mod` the way `tests/unit/test_policy.py` constructs the Policy module; give its master `getModuleByName("Policy")` → the module so `callAPI` works.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_policy_view.py -v`
Expected: FAIL on missing names.

- [ ] **Step 3: Implement `policyTree`, `policyState`, `policyLayout`, `policyStateView`, the route and the two template globals**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_policy_view.py tests/unit/test_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: /api/getPolicyState from one policy walker"
```

---

### Task 6: Page formatters

**Files:**
- Modify: `lib/TWCManager/Control/static/js/format.js`
- Test: `tests/js/format.test.js`

**Interfaces:**
- Consumes: the response shapes of Tasks 3–5; `ctx = {data, el, item}`.
- Produces (each a `Format.<name>(value, ctx)`; the source rule each ports is in brackets):
  - `presence(p)`: `home`→`Home`, `presumed`→`Probably home`, `notHome`→`Away` [`PRESENCE_TEXT`]
  - `watchLine(s, ctx)`: uses `ctx.data.now`, `ctx.data.budget` [`watchLine`, `HTTPControl.py:105-122`; `"covered by "` prefix]
  - `providerLine(claim) -> string` and `providerLines(claims) -> string` joined with `"\n"` (templates style the cell `white-space: pre-line`) [`providerLines` `:68-92`]
  - `lastSeen(entry, ctx)`: `ageAt(entry.lastSeenAt) + " via " + sourceName(entry.lastSeenSource)`
  - `heldLimit(l)`: `null`→`"—"`, else `"80% (90%)"` (`held`, then `outside`) [`heldLimitText`]
  - `fleetLine(spend)` / `telemetryLine(spend)`: the two summary lines; `""` when that flag is false [`spendLines`, `_lastMonth`, `_teleText`]
  - `spendCell(entry, ctx)` [`carSpend().cell`], `spendHeading(entry, ctx)` [`.heading`], `spendTelemetry(entry, ctx)` [`.telemetry`]; all read `ctx.data.spend.fleet/telemetry`
  - `spendTypeRow(t, ctx) -> [kind, String(count), usd(cost), ageAt(last)]`, `fieldRow(f) -> [field, count(count)]`
  - `pendingRow(p, ctx) -> [label, why]`: label `"Charge limit → 50%"` / `"Charge limit → car's own"` (value −1) / `"Charging → start|stop"` / `"Charge rate → 16 A"`; why per `pendingCommands` order: in flight `"sending via BLE, started 12 s ago"`; else `said`; else last outcome `"<detail or kind> via <source>, <age>"`; else `"not tried yet"`
  - `bleLabel(b)`: label + `" (scanning unavailable)"` when `!canScan && label === "Range unknown"`; `bleSince(b, ctx)`: `"since " + ageAt(b.since)` or `""`; `bleAttempt(b, ctx)`: `message + (" (" + ageAt(at) + ")" if at is a number)`; `bleLastScan(b, ctx)`: `ageAt(b.scannedAt)`; `bleRepair(b)`: `status in ("paired","refused")`; `bleScanBlocked(b)`: `"No range scan: " + scanBlocked` or `""`
  - `resolved(v, ctx)`: `""` when `JSON.stringify(v) === ctx.el.dataset.literal`, else `" (" + pyStr(v) + ")"` [`render_leaf`]
  - `pointKind(controllers)`: first local of `Gen2TWCs`→`TWC`, `Gen3TWCs`→`Gen3 Wall Connector`; no local → `EVSE via car`
  - `blank(v)`: `null`/`undefined` → `""`, else `String(v)` (Gen2-only cells)
  - `fixed2(v)`: `Number(v || 0).toFixed(2)`; `volts(list)`: `"a / b / c"` with each `Math.round`; `secondsSince(at, ctx)`: `String(Math.round((now - at) * 100) / 100)`; `chargeTime(since, ctx)`: `since == null ? "--:--:--" : duration(now - since)`
  - `scheduledStart(status)`: `start` unless `start != flex`, then `start + "(Flex " + flex + ")"` (status = `ctx.data`, so hooks use `data-field="scheduledChargingStartHour" data-format="scheduledStart"` with `value` ignored) [Default `jsrefresh.html.j2:16-20`]
  - `powerValue(w)` / `powerUnit(w)`: `w > 1000` → `(w*0.001).toFixed(2)` / `kW`, else `Math.round(w)` / `Watt` [Modern `jsrefresh.html.j2:17-24`]; `surplusWatts(_, ctx)` / `surplusUnit(_, ctx)` / `surplusAmps(_, ctx)` from generation − consumption (`0` when not positive) [`:29-48`]
  - `pluralS(list)`: `"s"` when `list.length > 1`
  - Predicates for `data-show-if`: `isEmpty(list)` (`!list || !list.length`), `not(v)` (`!Live-truthy`: false for `null`, `undefined`, `false`, `0`, `""`, `[]`), `bleNotRepair(b)` (`!bleRepair(b)`)

- [ ] **Step 1: Write the failing tests**, one per rule, with the exact strings the Python tests pin today:

```js
const now = 1_000_000;
const ctx = (data, el) => ({ data: Object.assign({ now, budget: 2.5 }, data), el: el || { dataset: {} } });

test("presence", () => { /* Home / Probably home / Away */ });
test("watch line", () => {
  assert.equal(F.watchLine({ watched: false, why: "off" }, ctx()), "Not watched: off");
  assert.equal(F.watchLine({ watched: false, why: "covered by TeslaMateVehicle" }, ctx()), "Not watched: covered by TeslaMate");
  const s = { watched: true, why: "", via: "ble", last: "asleep", lastAt: now - 120, nextAt: null };
  assert.equal(F.watchLine(s, ctx()), "Watched: asleep 2 min ago via ble; budget $2.50");
  assert.equal(F.watchLine({ ...s, via: null, why: "no status source" }, ctx()), "Not watched: no status source");
  assert.match(F.watchLine({ ...s, nextAt: now + 150 }, ctx()), /, next in 3 min;/);
});
test("provider lines", () => {
  const c = (provider, status, commands, readOnlyReason = null) => ({ provider, status, commands, readOnlyReason });
  assert.equal(F.providerLines([c("TeslaBLE", "paired", true), c("TeslaMateVehicle", "reports", false), c("Gen3TWC", "", true)]),
    "BLE: paired\nTeslaMate: reports, read-only\nGen3 Wall Connector: commands");
  assert.equal(F.providerLine(c("FleetAPI", "listed", false, "token lacks command scope")), "Fleet API: read-only (token lacks command scope)");
  assert.equal(F.providerLine(c("TeslaBLE", "unproven", false)), "BLE: unproven");
  assert.equal(F.providerLine(c("HomeAssistant", "entities", true)), "Home Assistant: entities, commands");
  assert.equal(F.providerLine(c("TeslaBLE", "paired", false)), "BLE: paired, read-only");
  assert.equal(F.providerLine(c("OwnerAPI", "listed", true)), "Owner API: commands");
});
test("held limit", () => { assert.equal(F.heldLimit({ held: 80, outside: 90 }), "80% (90%)"); assert.equal(F.heldLimit(null), "—"); });
test("fleet summary line with pace and last month", () => {
  const m = { api: 0.31, telemetry: 0, signals: 0, last: { api: 0, telemetry: 0 }, pace: { api: 0.62, telemetry: 0, by: "Dec 1" } };
  assert.equal(F.fleetLine({ fleet: true, month: m }), "Fleet API this month: $0.31 · on pace for $0.62 by Dec 1");
  assert.equal(F.fleetLine({ fleet: true, month: { ...m, api: 0, pace: null } }), "Fleet API this month: $0.00");
  assert.equal(F.fleetLine({ fleet: true, month: { ...m, pace: null, last: { api: 0.02, telemetry: 0 } } }), "Fleet API this month: $0.31 · Last month: $0.02");
  assert.equal(F.fleetLine({ fleet: false, month: m }), "");
});
test("telemetry line is approximate", () => {
  const m = { api: 0, telemetry: 0.28, signals: 41800, last: { api: 0, telemetry: 0 }, pace: null };
  assert.equal(F.telemetryLine({ telemetry: true, month: m }), "Fleet Telemetry this month: approx. 41,800 signals, $0.28");
  assert.equal(F.telemetryLine({ telemetry: true, month: { ...m, telemetry: 0.002, signals: 300 } }), "Fleet Telemetry this month: approx. 300 signals, $0.002");
});
test("car spend cell, heading and telemetry", () => {
  const car = { api: 0.02, telemetry: 0.002, requests: 1, signals: 300, types: [], fields: [], last: { api: 0, telemetry: 0 } };
  const both = ctx({ spend: { fleet: true, telemetry: true } });
  assert.equal(F.spendCell({ spend: car }, both), "$0.02 + approx. $0.002 telemetry");
  assert.equal(F.spendHeading({ spend: car }, both), "Fleet API this month: $0.02 in 1 request");
  assert.equal(F.spendHeading({ spend: { ...car, requests: 2, api: 0.04 } }, both), "Fleet API this month: $0.04 in 2 requests");
  assert.equal(F.spendTelemetry({ spend: { ...car, signals: 3 } }, both).startsWith("Fleet Telemetry this month: approx. 3 signals"), true);
  assert.deepEqual(F.spendTypeRow({ kind: "wake_up", count: 2, cost: 0.04, last: now - 30 }, both), ["wake_up", "2", "$0.04", "30 s ago"]);
});
test("pending rows", () => {
  const p = (o) => Object.assign({ aspect: "chargeLimit", value: 50, inFlight: null, said: null, lastOutcome: null }, o);
  assert.deepEqual(F.pendingRow(p({ inFlight: { provider: "TeslaBLE", since: now - 12 } }), ctx()), ["Charge limit → 50%", "sending via BLE, started 12 s ago"]);
  assert.deepEqual(F.pendingRow(p({ value: -1 }), ctx()), ["Charge limit → car's own", "not tried yet"]);
  assert.equal(F.pendingRow(p({ aspect: "charging", value: true }), ctx())[0], "Charging → start");
  assert.equal(F.pendingRow(p({ aspect: "amps", value: 16 }), ctx())[0], "Charge rate → 16 A");
  const last = { kind: "unreachable", detail: "", provider: "TeslaBLE", at: now - 120 };
  assert.equal(F.pendingRow(p({ lastOutcome: last }), ctx())[1], "unreachable via BLE, 2 min ago");
  assert.equal(F.pendingRow(p({ lastOutcome: { ...last, detail: "backoff" } }), ctx())[1], "backoff via BLE, 2 min ago");
  assert.equal(F.pendingRow(p({ lastOutcome: last, said: "no provider can deliver" }), ctx())[1], "no provider can deliver");
  assert.match(F.pendingRow(p({ lastOutcome: { ...last, detail: "held: driving", provider: "Gen2TWC" } }), ctx())[1], /^held: driving via TWC, /);
});
test("ble", () => {
  const b = (o) => Object.assign({ status: "unpaired", label: "In range (not paired)", canScan: true, since: null, scannedAt: now - 42, scanPending: false, scanBlocked: null, attempt: null }, o);
  assert.equal(F.bleLabel(b({ label: "Range unknown", canScan: false })), "Range unknown (scanning unavailable)");
  assert.equal(F.bleLabel(b()), "In range (not paired)");
  assert.equal(F.bleSince(b({ since: now - 120 }), ctx()), "since 2 min ago");
  assert.equal(F.bleSince(b(), ctx()), "");
  assert.equal(F.bleAttempt(b({ attempt: { ok: false, at: now - 120, message: "<b>timed out</b>" } }), ctx()), "<b>timed out</b> (2 min ago)");
  assert.equal(F.bleLastScan(b(), ctx()), "42 s ago");
  assert.equal(F.bleLastScan(b({ scannedAt: null }), ctx()), "never");
  assert.equal(F.bleRepair(b({ status: "refused" })), true);
  assert.equal(F.bleRepair(b()), false);
  assert.equal(F.bleNotRepair(b()), true);
  const why = "Bluetooth adapter is powered off or blocked (rfkill)";
  assert.equal(F.bleScanBlocked(b({ canScan: false, scanBlocked: why })), "No range scan: " + why);
});
test("predicates", () => {
  assert.equal(F.isEmpty([]), true); assert.equal(F.isEmpty([1]), false);
  assert.equal(F.not(false), true); assert.equal(F.not(true), false);
});
test("policy resolved suffix", () => {
  const el = (lit) => ({ dataset: { literal: JSON.stringify(lit) } });
  assert.equal(F.resolved(5, ctx({}, el("settings.x"))), " (5)");
  assert.equal(F.resolved(5, ctx({}, el(5))), "");
  assert.equal(F.resolved(true, ctx({}, el("x"))), " (True)");
});
test("home", () => {
  assert.equal(F.pointKind(["Gen2TWCs", "VehicleEndpoints"]), "TWC");
  assert.equal(F.pointKind(["Gen3TWCs"]), "Gen3 Wall Connector");
  assert.equal(F.pointKind(["VehicleEndpoints"]), "EVSE via car");
  assert.equal(F.blank(null), "");
  assert.equal(F.chargeTime(null, ctx()), "--:--:--");
  assert.equal(F.volts([240, 0, 0]), "240 / 0 / 0");
  assert.equal(F.scheduledStart(null, ctx({ scheduledChargingStartHour: 22, scheduledChargingFlexStart: 21 })), "22(Flex 21)");
  assert.equal(F.scheduledStart(null, ctx({ scheduledChargingStartHour: 22, scheduledChargingFlexStart: 22 })), "22");
  assert.equal(F.powerValue(1500) + " " + F.powerUnit(1500), "1.50 kW");
  assert.equal(F.powerValue(800) + " " + F.powerUnit(800), "800 Watt");
});
```

Fill the two `/* ... */` bodies with the asserted strings named in them (from `test_vehicle_detail_page.py:39-96`).

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/`
Expected: FAIL (`F.presence is not a function`, ...).

- [ ] **Step 3: Implement the formatters**

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/static/js/format.js tests/js/format.test.js
git commit -m "Live pages: page wording rules move to format.js"
```

---

### Task 7: `live.js` and live vehicle pictures

**Files:**
- Create: `lib/TWCManager/Control/static/js/live.js`
- Modify: `lib/TWCManager/Control/static/js/vehicleImage.js`
- Test: `tests/js/live.test.js`

**Interfaces:**
- Consumes: `Format` (global in the browser, `require("./format.js")` under Node); the hook vocabulary above.
- Produces (global `Live`, exported under Node):
  - `Live.start({urls, interval, fingerprint})`: `urls` items are a string (response merged into the data object with `Object.assign`) or `[url, key]` (response stored at `data[key]`). Fetches all with `cache: "no-store"` on load and every `interval` ms; any 404, or any response whose `fingerprint` differs from the page's, calls `location.reload()`. On fetch failure: keeps last values, shows one notice element (created by live.js at the top of `<body>`, class `live-offline`, text `Can't reach TWCManager`), retries on the interval; hides it on the next success. Pauses while hidden; fetches immediately on `visibilitychange` to visible.
  - `Live.onData(fn)`: `fn(data)` after each successful bind (page-specific script: Charge Now button state, policy action buttons, consumption colour, active policy).
  - `Live.bind(root, data)`: applies every hook under `root`.
  - Pure, tested under Node: `Live._lookup(data, path, item)`, `Live._truthy(v)`, `Live._mustReload(pageFingerprint, responses: [{status, body}]) -> bool`.
  - `window.drawVehicleImage(img)`: the per-image body of today's `vehicleImage.js` loop; the on-ready loop now calls it.

- [ ] **Step 1: Write the failing tests**

```js
const L = require("../../lib/TWCManager/Control/static/js/live.js");
const fs = require("node:fs");

test("lookup by key, id, index and relative path", () => {
  const d = { vehicles: [{ key: "anon:8244", name: "" }, { key: "5YJ", name: "Car" }], points: [{ id: "Point-5YJ", amps: 16 }], policies: [{ nodes: { "g-0": { truth: true } } }] };
  assert.equal(L._lookup(d, "vehicles.5YJ.name"), "Car");
  assert.equal(L._lookup(d, "vehicles.anon:8244.name"), "");
  assert.equal(L._lookup(d, "points.Point-5YJ.amps"), 16);
  assert.equal(L._lookup(d, "policies.0.nodes.g-0.truth"), true);
  assert.equal(L._lookup(d, ".amps", d.points[0]), 16);
  assert.equal(L._lookup(d, "vehicles.nope.name"), undefined);
});
test("truthy", () => { for (const v of [null, undefined, false, 0, "", []]) assert.equal(L._truthy(v), false); assert.equal(L._truthy([1]), true); });
test("reload rules", () => {
  assert.equal(L._mustReload("abc", [{ status: 200, body: { fingerprint: "abc" } }]), false);
  assert.equal(L._mustReload("abc", [{ status: 200, body: { fingerprint: "def" } }]), true);
  assert.equal(L._mustReload("abc", [{ status: 200, body: { carsCharging: 1 } }, { status: 200, body: { fingerprint: "abc" } }]), false);
  assert.equal(L._mustReload("abc", [{ status: 404, body: {} }]), true);
});
test("live.js never assigns innerHTML", () => {  // Review Focus 3
  const src = fs.readFileSync(require.resolve("../../lib/TWCManager/Control/static/js/live.js"), "utf8");
  assert.doesNotMatch(src, /innerHTML|insertAdjacentHTML|document\.write/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/`
Expected: FAIL, `Cannot find module .../live.js`.

- [ ] **Step 3: Implement `live.js`; refactor `vehicleImage.js` to `drawVehicleImage`**

DOM code runs only when `typeof document !== "undefined"`. Elements are created with `document.createElement` and filled with `textContent`.

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/static/js/live.js lib/TWCManager/Control/static/js/vehicleImage.js tests/js/live.test.js
git commit -m "Live pages: shared poller live.js"
```

---

### Task 8: Vehicles and Vehicle details pages go live; display helpers leave the lib

**Files:**
- Modify: `themes/Default/vehicles.html.j2`, `themes/Default/vehicleDetail.html.j2`, `HTTPControl.py` (remove `ageText`, `SOURCE_NAMES`, `sourceName`, `providerLines`, `heldLimitText`, `watchLine`, `_spendShown`, `_usd`, `_lastMonth`, `_teleText`, `spendLines`, `carSpend`, `PRESENCE_TEXT`, `pendingCommands` and their template globals; drop now-unused imports)
- Modify: `tests/unit/test_vehicles_page.py`, `tests/unit/test_vehicle_detail_page.py`

**Interfaces:**
- Consumes: `pageFingerprint` global (Task 4), `vehiclesView`/`vehicleView` shapes, formatter names (Task 6), hook vocabulary (Task 7).
- Template rules:
  - New template global `spendShown()` → `Views.spendShown(master)`.
  - Vehicles: spend lines `<p data-field="spend" data-format="fleetLine" data-show="spend.fleet">` and the same with `telemetryLine` / `spend.telemetry`; the spend `<th>`/`<td>` stay server-conditional on `spendShown()` (it is in the fingerprint). Vehicle details' heading/telemetry lines use path `vehicle` with `spendHeading` / `spendTelemetry`. Each registry row keeps its static VIN/link/picture; its cells become `data-field="vehicles.<key>.<field>"` with formats `presence`, `watchLine`, `providerLines` (cell `style="white-space: pre-line"`), `lastSeen` (path `vehicles.<key>`), `heldLimit`, `spendCell` (path `vehicles.<key>`); name `data-field="vehicles.<key>.name"`. History counts `data-field="history.<key>.chargeSessions"` / `.totalkWh`. Groups table and forms unchanged.
  - Vehicle details: `<meta refresh>` removed. When `registry.get(vin)` is set: name, providers, last seen, pending (`<tbody data-list="vehicle.pending" data-row="pendingRow">` plus `<p data-show="vehicle.pending" data-show-if="isEmpty">Nothing pending</p>`; add `Format.isEmpty(list)`), Fleet spend section wrapped in `data-show="vehicle.spend"`, types `data-list="vehicle.spend.types" data-row="spendTypeRow"`, fields `data-row="fieldRow"`, charge sessions `data-field="vehicle.chargeSessions"`. BLE block rendered when `'TeslaBLE' in master.modules`: label/since/attempt/last scan via the `ble*` formats; the scan form wrapped in `data-show="vehicle.ble.canScan"`, its two submit buttons (`Scanning…` disabled, `Scan for vehicle`) each in a wrapper toggled by `vehicle.ble.scanPending`; scan-blocked text `data-show="vehicle.ble.scanBlocked"`; pair vs re-pair buttons in wrappers toggled with `data-show-if="bleRepair"` and a new `Format.bleNotRepair`. Scripts and `Live.start({urls: ["/api/getVehicle/<vin>"], interval: 5000, fingerprint})` emitted only in this branch.
  - When the registry doesn't know the VIN: VIN facts, charge sessions (raw int), groups; no BLE block, no live scripts.

- [ ] **Step 1: Rewrite the Python page tests** to structure only. Keep, adjusted to the new markup: `test_list_renders_registry_rows` (link, `Unknown car on TWC 8244`, `Charge history`, add form, `data-field="vehicles.<VIN>.presence"` present), `test_names_and_error_are_escaped` (form error escaped; `TestCar` and `<script>x</script>` absent from server HTML), add/forget/group/local-mgmt tests unchanged. Replace `env()` globals with `pageFingerprint`/`spendShown` lambdas and `bleModule` flag. Delete the wording tests now covered in `tests/js/format.test.js` (`test_age_text`, provider-text, presence column, watch line, spend lines, pending-text) and the pending-selection tests now in `test_live_views.py`. Add:

```python
def test_page_carries_fingerprint_and_starts_live():
    html = render(master())
    assert 'Live.start' in html and pageFingerprint(m, "vehicles") in html
    assert '/static/js/format.js' in html and '/static/js/live.js' in html

def test_scan_pending_no_longer_meta_refreshes():
    assert 'http-equiv="refresh"' not in render_detail(master(), status(scanPending=True))

def test_unknown_vin_page_does_not_poll():  # Review Focus 2
    html = render_detail(master(), None, vin="5YJ3E1EA1KF000009")
    assert "Live.start" not in html and "Vehicle VIN" in html

def test_display_helpers_left_the_lib():
    import TWCManager.Control.HTTPControl as H
    for name in ("ageText", "sourceName", "providerLines", "heldLimitText", "watchLine",
                 "spendLines", "carSpend", "PRESENCE_TEXT", "pendingCommands", "_usd"):
        assert not hasattr(H, name)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_vehicles_page.py tests/unit/test_vehicle_detail_page.py -v`
Expected: FAIL (`Live.start` missing; helpers still present).

- [ ] **Step 3: Rewrite both templates; remove the helpers and their globals**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q && node --test tests/js/ && grep -rn "ageText\|providerLines\|carSpend\|pendingCommands\|PRESENCE_TEXT" lib/ || echo clean`
Expected: PASS, `clean`.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: Vehicles and vehicle pages fill from their APIs"
```

---

### Task 9: Policy page goes live

**Files:**
- Modify: `themes/Default/policy.html.j2`, `HTTPControl.py` (remove `do_get_policy`; `/policy` renders the template alone)
- Test: `tests/unit/test_policy_view.py`

**Interfaces:**
- Consumes: `policyTree`, `policyLayout`, `pageFingerprint` globals (Tasks 4–5); `resolved` format.
- Template: the `<style>` block from `do_get_policy` (`HTTPControl.py:1482-1513`) moves verbatim into the template. A recursive macro draws a node: a group with one child draws that child bare; a group draws `.policy-group` > `.group-bar` (`data-class-if="policies.<i>.nodes.<id>.truth" data-class-true="group-true" data-class-false="group-false"`, text `AND`/`OR`) > `.group-body`; a leaf draws `.policy-leaf` (same class hook with `leaf-true`/`leaf-false`) with `.policy-match` = literal `{{ leaf.match }}` + `<span data-field="policies.<i>.nodes.<id>.match" data-format="resolved" data-literal="{{ leaf.match|tojson|forceescape }}">`, `.policy-cond`, `.policy-value` likewise. Boxes: `.policy-box` with `data-policy="{{ name }}"`; header `name` + ` (<category>)`; an `Active` badge per box shown by `Live.onData` (adds `active` class and unhides the badge on the box whose `data-policy == data.active`, removes elsewhere). Ext blocks: `.ext-box` with `.ext-title` `"<name> Extension Point"`, or `.ext-marker` `"<name> Extension Point (no policies)"` when empty. Initial classes are neutral (no truth class) until first bind. `Live.start({urls: ["/api/getPolicyState"], interval: 5000, fingerprint})`.

- [ ] **Step 1: Write the failing tests**

```python
def test_policy_page_renders_structure_only(policy_page):  # render via the handler's templateEnv over a policy_mod master
    html = policy_page()
    assert html.count('class="policy-box') == len(policy_mod.charge_policy)
    assert "Emergency Extension Point" in html and 'data-format="resolved"' in html
    assert "leaf-true" not in html.split("<style>")[-1].split("</style>")[-1]  # no server-side truth
    assert "Live.start" in html and "/api/getPolicyState" in html

def test_do_get_policy_is_gone():
    from TWCManager.Control.HTTPControl import CreateHTTPHandlerClass
    assert not hasattr(CreateHTTPHandlerClass(Mock()), "do_get_policy")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_policy_view.py -v -k page`
Expected: FAIL.

- [ ] **Step 3: Rewrite the template; remove `do_get_policy`**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: Policy page fills from /api/getPolicyState"
```

---

### Task 10: Both home pages list every charging point, live

**Files:**
- Modify: `themes/Default/showStatus.html.j2`, `themes/Default/main.html.j2`, `themes/Default/jsrefresh.html.j2`, `themes/Modern/main.html.j2`, `themes/Modern/jsrefresh.html.j2`, `static/js/status.js`
- Test: `tests/unit/test_live_views.py` (template render checks)

**Interfaces:**
- Consumes: `chargingPointsView` shape (Task 3), formatters (Task 6), `live.js` (Task 7), `pageFingerprint(master, "home")`.
- Both home pages: `Live.start({urls: ["/api/getStatus", "/api/getChargingPoints"], interval: 3000, fingerprint})`; Modern adds `["/api/getActivePolicyAction", "activePolicyAction"]`. `getStatus` itself is unchanged: its `ScheduledCharging.amps` already carries the scheduled amps, and `scheduledChargingFlexStart` the flex hour.
- `jsrefresh.html.j2` (both): polling removed; keeps the Charge Now click handler; gains a `Live.onData` hook carrying today's non-text side effects (Charge Now button label/disabled; Modern: consumption colour, `chargeNowAmpsText`, `chargeNowTimeEndText`, policy-action button classes and help texts, from `data.activePolicyAction`).
- Default status panel: each `<div id=...>` becomes `data-field="<key>"`; Scheduled Charging Amps `data-field="ScheduledCharging.amps"` (no more `{{ scheduledAmpsMax }}`); start hour `data-format="scheduledStart"`.
- Default table: `<tbody data-keyed-list="points" data-template="point-row">`; the row template's first cell is `data-field=".controllers" data-format="pointKind"` followed by the point's TWC ID (`.gen2.twcid`, `blank`); State/Version/Lifetime kWh/Last Heartbeat/VINs from `.gen2.*` with `blank` / `secondsSince` (the " sec" suffix stays static text inside a `data-show=".gen2"` span); Max Amps `.maxAmps`, Offered `.ampsOffered`, In Use `.ampsDrawn`, voltage `.volts` with `volts`. VIN spans keep class `VINClick`, no `onClick`. Totals row from `total.*`.
- Modern "Charge Points": heading `Charge Point<span data-field="points" data-format="pluralS">`; `<div data-keyed-list="points" data-template="point-card">`; the card shows the TWC drawing in a wrapper `data-show=".local"` and `<img class="vehicleImage" data-image hidden>` in a wrapper `data-show=".local" data-show-if="not"` (add `Format.not`); version/state `.gen2.*`, charge time `.gen2.chargingSince` with `chargeTime`, offered/drawn/lifetime/volts, VINs, SoC `.soc`, last limit `.chargeLimit`. `chargerAvailAmps` = `total.lastAmpsOffered` with `fixed2`; power cells use `powerValue` + `powerUnit` spans; surplus via `surplus*`.
- `status.js`: `loadVIN` replaced by a delegated click on `.VINClick` opening `"/vehicleDetail/" + encodeURIComponent(text)` when non-empty. Modern loads `compositor.js`, `vehicleImage.js`, `format.js`, `live.js`.

- [ ] **Step 1: Write the failing tests** (render each theme's `main.html.j2` through `CreateHTTPHandlerClass(master)`'s environment with `webControlTheme` set)

```python
@pytest.mark.parametrize("theme", ["Default", "Modern"])
def test_home_page_lists_points_live(theme, mixed_master):
    html = renderHome(mixed_master, theme)
    assert 'data-keyed-list="points"' in html and "/api/getChargingPoints" in html
    assert "getSlaveTWCs" not in html and "setTimeout(request" not in html
    assert pageFingerprint(mixed_master, "home") in html

def test_default_home_names_the_kind_and_has_no_picture(mixed_master):
    html = renderHome(mixed_master, "Default")
    assert 'data-format="pointKind"' in html and "vehicleImage" not in html

def test_modern_home_draws_a_car_for_a_point_without_a_twc(mixed_master):
    html = renderHome(mixed_master, "Modern")
    assert "data-image" in html and "/static/js/vehicleImage.js" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v -k home`
Expected: FAIL.

- [ ] **Step 3: Rewrite the templates and scripts**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q && node --test tests/js/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: both home pages list every charging point, live"
```

---

### Task 11: Docs, changelog, running-app check, CI handoff

**Files:**
- Create: `docs/modules/control_HTTP_API/getChargingPoints.md`, `getVehicles.md`, `getVehicle.md`, `getPolicyState.md`
- Modify: `docs/modules/Control_HTTP.md` (API table rows, linked like `saveSettings`), `CHANGELOG.md` (v1.4.1 Features)
- Integration: `tests/integration/test_api_endpoints.py`

- [ ] **Step 1: Write the four API docs** following `getPricing.md`'s sections (Introduction, Format of request with a cURL example, Format of response with an example and a field list). Capabilities, not internals; times are epoch seconds; `fingerprint` explained as "changes when the page's layout would; clients can ignore it". No "charger" for the wall unit.

- [ ] **Step 2: Changelog line** under `## v1.4.1 - Upcoming` → Features: `(@MikeBishop) - The home page (both themes), Policy, Vehicles and vehicle pages keep themselves current while open. The home page lists every charging point (Gen2 and Gen3 TWCs, and EVSEs TWCManager controls through the car); new APIs getChargingPoints, getVehicles, getVehicle and getPolicyState carry what those pages show`.

- [ ] **Step 3: Integration tests** in `tests/integration/test_api_endpoints.py`:

```python
@pytest.mark.parametrize("path", ["/getChargingPoints", "/getVehicles", "/getPolicyState"])
def test_live_page_apis(api_get, assert_json_response, path):
    response = api_get(path)
    data = assert_json_response(response, 200)
    assert response.headers["Cache-Control"] == "no-store" and len(data["fingerprint"]) == 12

def test_get_vehicle_unknown_is_404(api_get):
    assert api_get("/getVehicle/5YJ3E1EA1KF000009").status_code == 404
```

- [ ] **Step 4: Full checks**

Run: `pytest tests/unit/ -q && node --test tests/js/`
Expected: PASS.

- [ ] **Step 5: Running-app check.** Start TWCManager with `etc/twcmanager/.testconfig.json` as the CI job does, then with Playwright load `/`, `/policy`, `/vehicles`, and a `/vehicleDetail/<VIN>` for a car added through the Add vehicle form. For each: no `.live-offline` notice after 4 s; at least one `[data-field]` non-empty; `/` lists the Dummy TWC; set `webControlTheme` to `Default` and repeat `/`. Then stop the server and confirm the notice appears within one interval. Run `pytest tests/integration/ -k "live_page or get_vehicle_unknown"` against it.

- [ ] **Step 6: CI handoff (do not commit).** Write to the scratchpad, for the operator to add to the `unit-tests` job in `.github/workflows/test_suite.yml` after "Run unit tests":

```yaml
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 'lts/*'
      - name: Run JavaScript tests
        run: node --test tests/js/
```

- [ ] **Step 7: Commit**

```bash
git add docs/modules CHANGELOG.md tests/integration && git commit -m "Live pages: API docs and changelog"
```
