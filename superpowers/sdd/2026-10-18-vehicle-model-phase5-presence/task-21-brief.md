# Task 21: Warn when a car's Fleet Telemetry config lacks fields we need (user, 2026-10-20)

User: "Is there a way to throw a warning on setups that aren't pulling all the fields we need?" then "The API is not
charged; checking that seems like the more straightforward approach." → read each car's config from Fleet API.

## Behaviour
1. For each car that has both the FleetTelemetryMQTT module active and a usable Fleet API token, read
   `GET /api/1/vehicles/{vin}/fleet_telemetry_config` (free, does not wake the car) once at startup — after the Fleet
   token is ready — and again once a day. No other triggers, no retries beyond the existing Fleet request handling.
   Response shape: `{"response": {"synced": bool, "config": {"fields": {"<Field>": {...}}, ...}, "limit_reached": bool,
   "key_paired": bool}}` — verify against the Fleet API docs / existing client code.
2. Required fields = the Fleet Telemetry fields TWCManager actually uses for presence and charging control. Derive the set
   from the module's own field mapping (one source of truth; don't hand-maintain a second list) and mark which are
   required vs optional where the mapping is defined. Required at minimum: whatever presence/plug/drive/charge-state,
   charge limit, battery level and location need. Optional (never warn): FastChargerPresent, FastChargerType,
   ChargingCableType and similar extras. Connectivity events are not a config field — skip.
3. Warn once per car per distinct problem (not every day if unchanged), at WARNING, naming the VIN and the missing
   fields, pointing to docs/modules/Vehicle_FleetTelemetryMQTT.md. Also warn if `config` is absent (car has no
   telemetry config) or `synced` is false ("config not yet applied by the car"). No warning when everything is present.
4. Show the same problem text on the vehicle detail page if that is a one-or-two-line addition via an existing
   per-vehicle note/status mechanism; otherwise log only and say so in the report.
5. Never on the serial thread; run where other Fleet background reads run (Fleet lane / background task — follow the
   existing pattern). A failed request (no token, 4xx, network) logs at DEBUG and stays quiet.

## Constraints
- Not a paid call; still must not count against the paid budget and must never wake.
- Lib growth small: target ≤ +30 net. Reuse the existing Fleet API request helper and the module's field mapping.
- Docs: one short paragraph in docs/modules/Vehicle_FleetTelemetryMQTT.md saying TWCManager checks the config and
  which fields are required.
- Tests: missing required field → one WARNING naming it; second check unchanged → no repeat; all present → none;
  optional field missing → none; synced false → warning; no config → warning; request failure → no warning; no Fleet
  token or module inactive → no request.
- Comment rule (why, not history; no task/ruling IDs); black; Python 3.8; only typed Fleet Telemetry forms.
- Commit: "Warn when a car's Fleet Telemetry config lacks needed fields" + Co-Authored-By trailer for your model.
