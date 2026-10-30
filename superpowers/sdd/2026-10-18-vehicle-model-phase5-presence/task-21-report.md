# Task 21 report: Fleet Telemetry config check

Commit 85100b95 on vehicle-model/phase5 (parent cbdbb5d0). Not pushed.

## What triggers it
`refreshTokens(master)` in lib/TWCManager/TWCManager.py, the background-thread task that runs every 300 s
(first run 300 s after startup) and already does the free Fleet/Owner token refresh and list retry. After those,
when the `FleetTelemetryMQTT` module is loaded (`getModuleByName` returns None if disabled or released), it calls
`fleetTLM.checkConfigs(carapi)`.

`checkConfigs` returns at once unless all hold: `now >= configCheckDue`, the account has listed cars
(`registry.attached("TeslaAPI")` with a VIN), and `carapi.fleetSlot.usable("read")`. Once it runs, `configCheckDue`
is set to now + 24 h. So the first check happens on the first refreshTokens pass that has a Fleet token and a car
list, then once a day. It does not retry: a failed read waits for the next daily pass.

## Where it runs
Only on the background tasks thread, never the serial loop. The HTTP read is
`TeslaAPI.telemetryConfig(vin)`, which is `GET vehicles/{vin}/fleet_telemetry_config` through the existing
`_request` helper with the Fleet slot. It goes to the slot's baseURL, which is the tesla-http-proxy when one is
configured, the same path every other Fleet read takes. It uses `tries=1`.

It has a new purpose, `"config"`. In `_classify`, any non-200 answer for that purpose is a plain
`Outcome(ERROR)` with no other effect: it doesn't clear the slot on a 401, pause reads on a 403/410/412, latch
anything, or start the 429 backoff. A refused config read therefore never affects vehicle_data reads or commands.
This shares a branch with "energy" (+1 net line). If the response isn't 200, isn't JSON, or has no "response", the
result is None, and checkConfigs logs that at DEBUG.

Paid budget: `_PAID_PATH` only matches vehicle_data, wake_up and command/*, so this path never increments
`vehicle.paidRequests` (which the reconciler's Desired snapshot reads) and never logs a "paid request". `vehicle`
isn't passed in any case. The endpoint is server-side and never wakes the car. Tests cover both points.

## Required-field set, and how it is derived
It is defined next to the `events` mapping in FleetTelemetryMQTT:
- `OPTIONAL` = FastChargerPresent, FastChargerType, ChargingCableType, ACChargingPower, ChargeCurrentRequestMax
  (the home-charger narrowing group in the docs), plus TimeToFullCharge and VehicleName (display only; the topic
  carries the VIN, so the name isn't needed to map the car).
- `REQUIRED = (set(events) | {"Location", "Gear"}) - OPTIONAL - {"latitude", "longitude", "syncState"}`.
  Location arrives as latitude/longitude, mqttMessage reads Gear directly, and syncState is the connectivity record
  rather than a config field.
- Result: BatteryLevel, ChargeAmps, ChargeCurrentRequest, ChargeLimitSoc, ChargerPhases, ChargerVoltage,
  DetailedChargeState, Gear, Location. This matches the docs' Presence and Charging groups plus battery level and
  charge limit.

`configProblem(answer)` returns one of these, checked in this order:
- "no Fleet Telemetry config" when config is missing or not a dict
- "Fleet Telemetry config lacks A, B" (sorted)
- "Fleet Telemetry config not applied yet" when synced is false
- "" when the config has every required field and is applied

## Warn once and show on the page
The per-car state is the car's `FleetTelemetryMQTT` claim status, so there is no separate dict. When a problem
differs from the claim's current status, it logs at WARNING:
`"<VIN>: <problem>; see docs/modules/Vehicle_FleetTelemetryMQTT.md"`. It then sets
`vehicle.claim("FleetTelemetryMQTT", False, problem, keepsAlive=False)`. An unchanged problem the next day doesn't
log again, and a different problem logs again. When the problem clears, the status goes back to "reports". A
problem-free car that has no claim gets none.

Telemetry's `_observe` adds a claim only when there isn't one, so a later report keeps the problem status in place.
`keepsAlive=False` means the claim never keeps an unseen car in the registry, and canCommand False changes nothing
in command routing. Claims are only used for display, `"TeslaBLE" in claims` checks, and keepsAlive in expire.

**The page shows it.** The provider lines on the vehicle detail page and the vehicles list render claim statuses,
e.g. "Fleet Telemetry: Fleet Telemetry config lacks Gear, read-only". No template or HTTPControl change was needed.
The wording repeats "Fleet Telemetry", but it is clear.

## Docs
docs/modules/Vehicle_FleetTelemetryMQTT.md has one new paragraph after the field groups. It says what is checked
and when (free and doesn't wake the car), that problems go to the log and the Vehicle Details page, and lists the
required and optional fields.

## lib Δ
+60 / -5 = **+55 net**, against the brief's ≤ +30 target:
- FleetTelemetryMQTT.py: +41. The OPTIONAL/REQUIRED sets with a 3-line comment take 9 lines, configProblem 9,
  checkConfigs 20, and the _DOC constant 1.
- TeslaAPI.py: +11 net. telemetryConfig is 10 lines; the _classify comment and branch are +1.
- TWCManager.py: +3 for the trigger.

Already done to keep it down:
- The claim status holds the warned state, so there is no `__init__` or dict.
- The config purpose shares the energy branch.
- The doc path is a constant, which keeps the warning on one line.

What remains is the minimum for a request wrapper, a field-set derivation, a problem classifier, a scheduler and
loop, and a trigger. Calling `get_car_api` instead would save about 12 lines, but it was rejected. It uses purpose
"read", so a 403 or 412 on this endpoint (for example a pre-2021 S/X that can't stream) would pause, or until the
token changes latch, all vehicle_data reads. It would also start the per-car API error backoff and its 5 s retry
sleeps.

## Tests
New file tests/unit/test_fleet_telemetry_config_check.py, 18 tests. They use a real TeslaAPI with a Fleet token,
requests_mock on the NA Fleet URL, and a real FleetTelemetryMQTT on the same registry.
- A missing required field gives one WARNING that names it, the VIN and the doc. An unchanged config the next day
  is read again but not warned again.
- A new, different problem warns again.
- All fields present gives no warning and no claim. A fixed config sets the claim back to "reports".
- A missing optional field gives no warning.
- `synced` false warns, and no config warns.
- Not more than once a day.
- HTTP 401, 403, 404, 412 and 500: no WARNING or ERROR, the Fleet slot is still usable for reads, and no claim.
  The 403 and 412 cases fail if the purpose is "read" (mutation-checked).
- A network failure is quiet.
- The read is never counted as paid (paidRequests 0, no "paid request" log).
- No Fleet token: no request. Module inactive (refreshTokens with no FleetTelemetryMQTT module): no request.
  refreshTokens with the module active: exactly one request.

Full suite: **2232 passed** (baseline 2214, plus 18). black is clean on lib and the new test file.

## Concerns
- lib Δ is +55 against the ≤30 target (see above).
- Response shape and unconfigured cars: I couldn't check the response shape against the live API (no network
  docs). The parser takes `response.config.fields` (dict keys) and `response.synced`. For a car with no telemetry
  config, Tesla's exact answer is unverified:
  - a 200 with config null warns "no Fleet Telemetry config"
  - a 404 or other error is quiet (DEBUG only), so that car would get no warning
  Worth confirming on the live box.
- Claim on non-streaming cars: a car on the account that never streams (another driver's car, or a pre-2021 S/X)
  gets a daily-checked "no Fleet Telemetry config" WARNING once per process lifetime, plus a provider line. That is
  intended by the brief, but users with mixed fleets will see it on every restart.
- Restarts: the warned state lives in the in-memory claim, so each restart warns once again per problem car.

## Fix round 1 (amended as 998d7baf)
Applied review items S1, S2, S4 and S5. Also removed the no-op `tries=1` and the redundant `if v.vin`.

- S1: `checkConfigs` no longer takes `now`. It reads `time.time()` directly.
- S2: the claim-status comparison now uses getattr.
- S4: the checkConfigs comment keeps only the reasons.
- S5: the `_classify` comment is reflowed.
- S3: the DEBUG line is kept. configProblem is unchanged (S6 not applied).

Tests:
- The once-a-day test patches the module's `time` and checks both edges: day minus 1 s gives no request, a full
  day gives one. The other next-day tests reset `configCheckDue`.
- The optional-field test now passes all required fields and no optional ones, and asserts that OPTIONAL is
  non-empty and absent from the config.

lib Δ: +59/-7 = **+52 net**. Neither S1 nor S2 saved a line, because the one-line forms exceed black's 88-column
limit. Suite: 2232 passed.
