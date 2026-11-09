# Task 4 report: /api/getVehicles and /api/getVehicle/<VIN>

Commit: ef825dc9 Live pages: /api/getVehicles and /api/getVehicle/<VIN>

## Implemented

`lib/TWCManager/Control/Views.py` (imports model modules only: Presence, Belief, Desired, Outcome.RULES, Rules, Registry.VIN — R7):
- `pageFingerprint(master, page, vin=None)`: "home" -> `fingerprint("home")` (unchanged value, R4); "vehicles" -> `fingerprint("vehicles", keys, groups, historyKeys, fleet or telemetry)`; "vehicle" -> `fingerprint("vehicle", vin.upper(), exists, groups)` where `exists` is `registry.get(vin) is not None` (always True inside vehicleView, matching the brief's literal `True`); "policy" -> `fingerprint("policy", [p["name"] for p in charge_policy])` per the plan's Task 5 shape; anything else raises ValueError. `chargingPointsView` now uses `pageFingerprint(master, "home")`.
- `spendShown(master)`: same logic as `HTTPControl._spendShown`.
- `providerClaims(master, vehicle)`: claim order, raw provider names, OwnerAPI/FleetAPI skipped without token, `readOnlyReason` only when `commands` is False.
- `pendingCommandData(master, vehicle)`: row selection mirrors `pendingCommands` (peek, skip no-record, skip satisfied/settled unless in flight); `said` = blockedReason (always reported raw); `lastOutcome` reported whenever present (JS decides precedence: inFlight > said > lastOutcome). Never creates desired state.
- `vehicleEntry(master, vehicle, fleet, telemetry, now=None)`: brief keys exactly; `lastSeenAt = now - lastSeenAge` with the response's `now` (extra optional `now` param for that).
- `vehiclesView`, `vehicleView` with the brief's shapes. Settings read under `settingsLock` with `.get(..., {})`. vehicleView looks up chargeSessions with `vehicleRecordKey` on `vehicle.vin` (case-insensitive, so `/api/getVehicle/<lowercase vin>` finds history); `ble` = `getModuleByName("TeslaBLE").bleStatus(vehicle.vin)` when the module is loaded and the car has a VIN.

`HTTPControl.py`: routes `GET /api/getVehicles` and prefix `GET /api/getVehicle/` (unquote + strip("/"), 404 `{"error": "unknown vehicle"}`); template global `fingerprint(page, vin=None)` -> `Views.pageFingerprint`. Old display helpers untouched.

## Tests (tests/unit/test_live_views.py, +23 tests)
Entry raw fields (selected by key, R5), top-level view, watch passthrough, presence states, provider claims order, token-not-held (parametrized), read-only reason, pending rows (in flight, every aspect, held outcome, held w/o outcome, said+lastOutcome, lastOutcome fields), hides satisfied/settled, drifted, held-asleep, no desired state created, spend, fingerprints (vehicles shape, vehicle, home), fresh settings, detail fields incl. BLE, secrets (R6: "tok" absent, no key contains token/secret/webhook), never reads providers, both routes incl. 404 variants and no-store header, template global via a real handler instance (BaseHTTPRequestHandler.__init__ patched out).

Brief test adjustment: `test_vehicle_views_never_read_providers` — the Mock(spec) api's `fleetSlot.accessToken` is a truthy Mock, so spend shows and the fixture master needs `fleetSpend`; I call `spending(m)` first and also add OwnerAPI/FleetAPI claims so the api path is exercised.

## TDD evidence
RED: `git stash push lib; /root/venv/bin/pytest tests/unit/test_live_views.py -q` -> `ImportError: cannot import name 'pageFingerprint' from 'TWCManager.Control.Views'` (expected: names missing). (Implementation was drafted before tests; RED obtained by stashing it.)
GREEN: `/root/venv/bin/pytest tests/unit/test_live_views.py -q` -> 33 passed.
Full: `/root/venv/bin/pytest tests/unit -q` -> 2689 passed, 1 warning (pre-existing urllib3 warning).
Old page tests untouched and green.

## Concerns
- Template global is registered as `fingerprint` (R4); the plan's Task 8 text says `pageFingerprint` global — Task 8 should use `fingerprint(...)` or add an alias.
- The "vehicle" fingerprint follows the brief (vin, exists, groups) and does not include spend-shown or BLE-loaded, though the detail page's sections depend on them; those only change on restart (module load) or Fleet token add, so a token added at runtime would not trigger a reload of the details page.
- `ble.bleStatus` returns ages (`sinceAge`, `lastScanAge`, `attempt.age`) computed from its own `time.time()`, not the response `now`; passed through as the brief specifies.
- black not installed in the venv; formatting checked by eye only.

## Fix report (review round 1)

Finding: vehiclesView duplicated the "vehicles" fingerprint shape instead of sharing pageFingerprint's.

Change: added `Views._vehiclesFingerprint(vehicles, groups, historyKeys, fleet, telemetry)`, which is now the only definition of the Vehicles shape. `pageFingerprint(master, "vehicles")` and `vehiclesView` both call it. vehiclesView passes it the same registry/settings snapshot it uses for the list. Every page shape now has exactly one `fingerprint("<page>", ...)` call (`grep -n 'fingerprint("' Views.py`: vehicles helper, home, vehicle, policy). vehicleView and chargingPointsView already went through pageFingerprint.

Covering tests: test_vehicles_fingerprint_follows_shape (view == pageFingerprint, and it changes with groups and with spend shown), test_get_vehicles_route (route fingerprint == pageFingerprint), test_fingerprint_template_global.
- `/root/venv/bin/pytest tests/unit/test_live_views.py -q` -> 33 passed in 0.13s
- `/root/venv/bin/pytest tests/unit -q` -> 2689 passed, 1 warning (the urllib3 warning that was already there)
