# Task 11 report: Docs, changelog, running-app check, CI handoff

Commit: 64ab10a6 Live pages: API docs and changelog (not pushed)

## Implemented
- docs/modules/control_HTTP_API/getChargingPoints.md, getVehicles.md, getVehicle.md, getPolicyState.md:
  getPricing.md's layout (Introduction; Format of request with cURL; Format of response with an example and a field list).
  The examples are real responses from the running app (the getChargingPoints example has a car on the TWC filled in, for illustration).
  Times are given as epoch seconds; fingerprint is described as "changes when the page's layout would ... Clients can ignore it". getVehicle documents the 404 for an unknown VIN.
  No "charger" for the wall unit (checked with grep).
- docs/modules/Control_HTTP.md: four rows added in alphabetical order, linked the same way as saveSettings.
- CHANGELOG.md: the brief's line, verbatim, first under v1.4.1 Features.
- tests/integration/test_api_endpoints.py: the brief's two tests, verbatim (module-level, after the existing classes).
- CI snippet (not committed): /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/ci-node-step.yml (uses `node --test tests/js/*.test.js`, per R8).

## Tests
- /root/venv/bin/pytest tests/unit -q -> 2696 passed, 1 warning. The warning also appears without my change; I changed no unit-tested code.
- node --test tests/js/*.test.js -> tests 33, pass 33, fail 0
- black --check lib -> 99 files would be left unchanged
- /root/venv/bin/pytest tests/integration/ -k "live_page or get_vehicle_unknown" -q, run against the live server -> 4 passed

## Running-app check
I started the app the way CI does, from a copy of .testconfig.json at /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/app-check/run/config.json with MySQL, Sentry and MQTT turned off. No config.json was left in the repo, and the server is stopped.
The car was added with POST /vehicle/add vin=5YJ3E1EA1KF000001, which gave a 302 to /vehicleDetail/5YJ3E1EA1KF000001.
Script: /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/app-check/check.py (Playwright, Python). Output: /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/app-check/check.out
Results, each after a 4.5 s wait:
- / (Modern): no .live-offline notice; 24/30 data-fields filled; TWC 4142 listed. The empty ones (VIN, Last VIN, SoC, limit) are empty because no car is present.
- /policy: no notice; 14/20 filled. The empty ones are value sides whose live value equals the written one, so F.resolved shows nothing, as designed.
- /vehicles: no notice; presence, watch, last seen, held limit and history are filled. Name and providers are empty because this car has neither.
- /vehicleDetail/<VIN>: no notice; last seen and charge sessions are filled; picture and VIN details render.
- / (Default theme, set with /api/setSetting webControlTheme=Default): no notice; 27/30 filled; 4142 listed.
- Stopping the server with / open: "Can't reach TWCManager" appeared about 2.0 s later, within the 3 s interval.
- Console: no errors from live.js or format.js on any page.
Screenshots (deviceScaleFactor 1): /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/app-check/home-modern.png, policy.png, vehicles.png, vehicle.png, home-default.png, offline.png (all in /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/app-check/)

## Concerns (both pre-existing, not fixed: out of scope)
1. On a fresh install (no settings.json), /vehicles and /vehicleDetail/<VIN> render as an empty 200 page. jinja2 raises UndefinedError: 'dict object' has no attribute 'VehicleGroups' at vehicles.html.j2:95 and vehicleDetail.html.j2:202.
   Cause: TWCMaster.loadSettings returns early when the file is missing (dict(DEFAULT_SETTINGS); return) and so skips creating VehicleGroups and its other defaults. This has been there since before this branch; the template lines predate it too.
   A restart after the first settings save fixes it, which is how I finished the check. CI also starts with a fresh /tmp/twcmanager, so any integration test that GETs those pages on first boot would get an empty body.
   Suggested fix (needs a decision): let the missing-file branch fall through to the default-filling block, or have the templates use settings.get("VehicleGroups", {}).
2. Modern theme: on every Modern page, commonUI.js throws "$(...).tooltip is not a function" (a pageerror). Two jQuery copies load (3.3.1 from bootstrap.html.j2, 3.6.0 from bootstrap.js.html.j2), and Bootstrap 5 has no jQuery tooltip plugin. This predates the branch and does not affect live.js: the fields fill and the offline notice works.

## Fix round 1 (docs only)
1. getChargingPoints.md `local`: now "true when a Gen2 or Gen3 TWC is part of the point, and false for a point known only through the car".
2. getVehicle.md `ble`: now also null when the car's VIN is not known.
3. getVehicles.md: documented the shape of `spend.month` (api, telemetry, signals, last {api, telemetry}, pace {api, telemetry, by} or null on the month's first day) and of per-vehicle `spend` (api, telemetry, requests, types[{kind, count, cost, last}] costliest first, signals, fields[{field, count}] most first, last {api, telemetry}). Also noted that per-vehicle `spend` is null for a car known only by its TWC.
4. getVehicles.md `history`: keyed by VIN, only for vehicles that have charge history.
5. getVehicles.md `point`: "the ID of the TWC the car is on". getChargingPoints has no `point` field (a point's own ID is `id`), so I changed nothing there. getVehicle.md refers to getVehicles for this field.
Tests: no code changed. The docs were checked against Views.py and FleetSpend.py. `grep -n charger docs/modules/control_HTTP_API/get{ChargingPoints,Vehicles,Vehicle,PolicyState}.md` finds nothing.
Commit: see git log (Live pages: API docs fixes from review).
