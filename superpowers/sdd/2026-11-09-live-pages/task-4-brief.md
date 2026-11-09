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

