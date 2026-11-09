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

