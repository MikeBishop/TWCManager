# Task 21 review: Fleet Telemetry config check (85100b95 on cbdbb5d0)

Checked: brief, report and diff, plus the surrounding code (`_request`, `_classify`, `get_car_api`,
`TeslaTokenSlot.usable`, `Vehicle.claim`, `Telemetry._observe`, `providerLines`, registry expire).
The 18 new tests pass. black is clean on the three lib files.

## Verdicts

- **Spec compliance: PASS, with two noted deviations.**
  1. The lib grows by +55 against a target of ≤ +30. See Size below: about 5 lines can come out. Getting to +30
     would mean dropping something the brief asks for.
  2. The first check runs about 300 s after startup, on the first `refreshTokens` pass, not "at startup". This is
     acceptable: the token refresh has just run, so the token is ready. The docs say "a few minutes after startup".

  Everything else in the brief is met:
  - It runs only on the background thread and is triggered only by the module plus a Fleet token.
  - It checks once a day and only after the car list has loaded.
  - The field set comes from `events`, with the optional fields marked where the mapping is defined.
  - It warns once per distinct problem, and covers missing config, unsynced config and missing fields.
  - Failures stay quiet.
  - The problem shows on the page through the existing claim status, with no template change.
  - The docs paragraph is there, and every listed test exists.
- **Quality: APPROVE WITH MINOR CHANGES.** I found no correctness defects. The changes requested are small size
  trims and tidying.

## 1. Size: concrete cuts

| # | Where | Change | Saves |
|---|-------|--------|-------|
| S1 | FleetTelemetryMQTT.py:67-70 (`checkConfigs(self, carapi, now=None)` + `now = ...`) | Drop the `now` parameter and use `time.time()` inline in the guard. Tests patch `time.time` (or `FleetTelemetryMQTT.configCheckDue`) instead. Its only purpose is test plumbing. | 1 |
| S2 | FleetTelemetryMQTT.py:81-83 | `claim = vehicle.claims.get(...)` plus `(claim.status if claim else "reports")` becomes `getattr(vehicle.claims.get(name), "status", "reports")` in the comparison. | 1 |
| S3 | FleetTelemetryMQTT.py:77-79 | The `logger.debug("No Fleet Telemetry config read ...")` line restates a log that already exists: `_request` logs every HTTP answer at INFO8 (13, above DEBUG) with the status, and `telemetryConfig` gives None only after that, or for a transport error. Use just `if answer is None: continue`. A transport error then has no log of its own; the brief asks for "logs at DEBUG", so this cut is the reviewer's call. | 1 |
| S4 | FleetTelemetryMQTT.py:68-70 (checkConfigs comment, 3 lines) | "once the Fleet token and car list are ready, then daily; background thread" restates the guard right below it. Keep the reasons only, e.g. `# A free read that never wakes the car. The claim holds the shown` / `# problem, so each one is warned of once`. | 1 |
| S5 | TeslaAPI.py:365-370 (`_classify` comment) | The added words left a short line ("reads keep the token. Elsewhere a 401 refreshes"). Reflowing the paragraph gets back the +1. | 1 |
| S6 | FleetTelemetryMQTT.py:57-66 (`configProblem`) | It could be inlined into checkConfigs, which would save the `def` and comment lines. The if/elif assignment chain makes the loop harder to read, so **not recommended**. | (2) |
| — | TeslaAPI.py:650 `tries=1` | Dead: the "config" branch of `_classify` never returns `_REFRESHED`, so `tries` has no effect. Removing it is clearer. | 0 |
| — | FleetTelemetryMQTT.py:72 `if v.vin` | Dead: `getOrCreate` refuses a car without a VIN, so every attached car has one. | 0 |

Recommended total is S1 to S5, about −5, which gives **+50**. Getting to ≤ +30 would mean cutting a feature: the
`synced` check, the doc pointer, the daily re-check or the problem shown on the page. The brief asks for each of
those. The obvious structural savings are already in place:
- the claim status doubles as the warn-once state, so there is no dict or `__init__`
- "config" shares the energy branch in `_classify`
- the problem reaches the page through existing display code
- the field set is derived rather than listed by hand

I looked for other duplication and found none:
- The OPTIONAL/REQUIRED lines are at black's minimum. Any single set literal of 7 or 9 names is too long and black
  splits it one name per line.
- `_DOC` costs one line. Inlining the path wraps the warning call to three lines.
- The 3-line trigger is the minimum for an optional module.

**My view:** the +30 target was set too low for a request wrapper, a field set, a problem classifier, a scheduler
and a trigger. Accept about +50 after the trims rather than drop a requirement.

### Reusing get_car_api

The implementer was right to reject it, and there is a stronger reason than the one given. `get_car_api` uses
purpose "read", so a 403 or 410 pauses vehicle_data reads on the Fleet slot for an hour, and a 412 latches them
until the token changes. Beyond that:

- A 200 whose `response` is null is plausibly Tesla's answer for a car with no telemetry config. `get_car_api`
  treats that as a non-transient error: it logs "Can't access vehicle status" at INFO and calls
  `updateCarApiLastErrorTime(car)`, which puts the car's **vehicle_data reads into backoff**.
- It retries up to 3 times, with 5 s sleeps.

Adding a `purpose` argument to `get_car_api` would fix the latch but not the backoff, and it would add lines to a
hot path. The commit already reuses the right layer: `telemetryConfig` is a thin `_request` wrapper, written the
same way as `_fetchEnergySites`/`_vehicleList`, with a dedicated purpose that `_classify` acts on. Nothing smaller
is safe.

## 2. Correctness

- **Never wakes, never paid.** The path doesn't match `_PAID_PATH`, and `vehicle` isn't passed, so
  `paidRequests` and the "paid request" log are never touched. The endpoint is server-side. Both have tests.
- **Off the serial thread.** It runs only from `refreshTokens`, which runs on the background task thread.
- **Failures stay quiet.**
  - The "config" purpose gives `Outcome(ERROR)` for every non-200, with no clearing, pausing, latching, 429
    backoff or `errorCount` change.
  - A 401 isn't refreshed here, which is fine: `refreshTokenIfNeeded` ran just before.
  - Transport errors, non-JSON answers and a missing "response" give None.
  - The parametrized tests (401/403/404/412/500) check that the slot is still usable.
- **Warn-once.** The key is the claim status, compared with the new problem.
  - Unchanged problem: no repeat warning. A different problem warns, and so does A→B→A, which fits "distinct problem".
  - On restart it warns again, since the state is in memory. That is acceptable and is in the report.
  - Benign TOCTOU: `_observe` on the MQTT thread can find no claim, and set "reports" just after the background
    thread sets a problem. Then the next day's check warns again. This is low-impact, and no fix is needed.
- **Fix status (nit).** When a problem clears, the claim goes to "reports" even if the car has never streamed a
  message. The page would say "reports" when nothing has arrived yet. It is cosmetic. `dropClaim` would be more
  accurate, and `_observe` would add the claim back on the first message, but it costs a line. Optional.
- **Readiness.**
  - The guard needs both `fleetSlot.usable("read")` (token present, scope, not paused) and a non-empty car list.
  - `configCheckDue` is set only once both hold, so a not-ready pass retries 300 s later rather than a day later.
  - A slot cleared by another thread partway through the loop would make `"Bearer " + None` raise. The same race
    exists for every caller of `_request`, so I am not counting it here.
- **No token in logs.** `_request` logs the method, path (with the VIN, as for other reads) and status only.
  Transport errors are logged by exception type only. The warning has the VIN, the problem and the doc path.
- **Response shape.**
  - `response.config.fields` (dict keys) and `response.synced` match the Fleet API docs' example.
  - A null `response` or a null `config` both give "no Fleet Telemetry config", which is good.
  - A missing `synced` reads as "not applied yet". That is acceptable.
  - `key_paired: false` isn't reported. The brief doesn't ask for it.
  - As the report says, check on the live box what an unconfigured car actually gets (a 200 with config null, or a
    404).
- **Field set.** REQUIRED is BatteryLevel, ChargeAmps, ChargeCurrentRequest, ChargeLimitSoc, ChargerPhases,
  ChargerVoltage, DetailedChargeState, Gear and Location. That matches the docs' Presence and Charging groups plus
  the battery level and charge limit. The optional fields match the brief.

## 3. Comment rule

All the new comments explain why. None of them describe history, and none carry a task or ruling ID. That covers
the OPTIONAL block, configProblem, checkConfigs, telemetryConfig, the `_classify` paragraph, and the test module
docstring and inline comments. The only issue is S4: part of the checkConfigs comment restates the guard below it.

## Tests

All 18 pass. Coverage matches the brief's list. One nit: `test_optional_field_missing_no_warning` uses the default
REQUIRED-only field set, which is already missing every optional field. It is correct but doesn't make that
obvious. It could pass `fields=sorted(REQUIRED)` explicitly, or rely on the assert it already has.
