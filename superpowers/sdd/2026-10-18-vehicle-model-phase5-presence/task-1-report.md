# Task 1 report

Implemented: Reconciler.report logs every outcome at INFO; TeslaAPI._request logs one INFO line per Fleet paid request (module _PAID/_PAID_PATH; no URL/VIN/token; logged after every HTTP response incl. 408 and refresh resends; transport errors with no response log nothing); TelmetryBase.logChange logs "%s: %s %s -> %s" on change per (car, field) for pluggedIn/state (in _observe, 2-name set _LOGGED) and TeslaMateVehicle logs the geofence topic (subscribed, logged only, via mqttMessage).
Decision: first observed value counts as a change (old shown as None); retained startup cost is at most one line per car per field.
Note: _request's "paid" regex matches path suffix after dropping the query string.

TDD: RED (lib reverted) `pytest tests/unit/test_paid_logging.py` -> 4 failed, 1 passed (free-requests test passes trivially pre-change, as expected: it asserts absence). GREEN: 5 passed. Full suite: 1959 passed, 1 xfailed (BASE 1954 + 5 new).
Lib lines: 26320 -> 26352 (+32 vs expected +18; 14 over, under the 25 limit; black wrapping of the geofence call and the _request block). shortstat: 4 files, 36 insertions, 3 deletions.
Files: Vehicle/Reconcile/Reconciler.py, Vehicle/TeslaAPI.py, Vehicle/Telemetry.py, Vehicle/TeslaMateVehicle.py, tests/unit/test_paid_logging.py (new).
Concerns: line overage only. Reconciler log line prints attempt.key, unchanged format (not a paid-request line).

## Fix round 1
- Telemetry._observe: logChange now sits inside the live (`not retained`) branch; a retained redelivery never logs. Test 5 gained a retained pluggedIn True after a live False (would log "False -> True" if buggy).
- Free-requests test asserts requests_mock.call_count == 5.
- Covering tests: 5 passed. Full suite: 1959 passed, 1 xfailed.
