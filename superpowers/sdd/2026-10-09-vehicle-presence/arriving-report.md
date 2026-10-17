# BLE-confirmed arrival: report

Status: DONE. Commit 15f9d21, "Arrivals of BLE-proven cars wait for BLE to confirm".

## Design (lib/TWCManager/VehiclePresence.py)
- `ARRIVING = "arriving"` is an internal state, held in `_state`, with `_arrivingSince[vin]` recording when it started. The class attribute `ARRIVAL_CONFIRM_TIMEOUT = 600`.
- `bleApplies` is a constructor hook. The default `_defaultBleApplies(vin)` requires all of:
  - "ble" in the resolved source order;
  - `master.settings` is a dict and `settings["Vehicles"][vin]["bleProven"]` is set;
  - `getModuleByName("TeslaBLE")` is truthy.
  The dict check matters: tests that use `Mock()` masters would otherwise apply. The hook is evaluated once per pass, **outside the lock**, for the VINs that are observed, due or arriving.
- Entering ARRIVING:
  - from a location home answer (a pushed `observeLocation`, or a probe decided by telemetry or api) for a VIN BLE applies to that is not already HOME;
  - this is not a transition, so no handler runs; INFO log "inside the home radius (was X); arriving, waiting up to 600 s for BLE to confirm";
  - covers UNKNOWN → ARRIVING (startup) and AWAY → ARRIVING.
- Probing while ARRIVING:
  - `_probe(vin, arriving=True)` runs "ble" first, then the rest of the order, so a telemetry or API away answer can still cancel. Without the rest, a car located only through the API would never get an away answer before the timeout. A drive-by would then become a bogus HOME, followed 10 minutes later by a departure restore.
  - A car that enters ARRIVING from a pushed fix gets its first BLE probe in the same pass, if the rate limit allows.
  - A probe-driven entry (a location source says home before BLE has been tried in that pass) also calls the ble source in the same pass, so a car already in range is confirmed at once.
  - The next probe is scheduled at max(now, lastProbe + PROBE_INTERVAL), and the timeout deadline is also put in `_due`, so the thread wakes for both. The cadence is one probe per PROBE_INTERVAL; tests check it.
- Exits:
  - Reachable BLE probe → HOME. INFO "arrival confirmed by BLE". The limit is the probe's own when it has one, otherwise the telemetry fill-in in `_runHandler`. Precedence: a BLE limit overrides a limit that an earlier location source gave in the same pass (BLE reads the car live; telemetry can lag). `test_probe_driven_entry_tries_ble_in_the_same_pass`: telemetry 50, BLE 90 → the arrival gets 90.
  - BLE contact → HOME ("confirmed by BLE contact").
  - TWC proof → HOME ("confirmed by a TWC proof").
  - Timeout → HOME ("confirmed by timeout"), checked after the probe loop; the limit is the fill-in.
  - An away answer (pushed or probed) → AWAY. INFO "arrival cancelled". `_runHandler` runs no handler for arriving → away, because `old != HOME`.
- Failed probes while ARRIVING return early in `_applyProbe`, so they never touch `_failedProbes` and the away rule.
- VINs BLE doesn't apply to keep today's behaviour: a location home answer makes them HOME at once.
- Lock invariant: sources (`_callSource`), `bleApplies`, `limitLookup` and the handlers all run without the presence lock. A test asserts this for every call.

## state() reports ARRIVING as UNKNOWN: why, caller by caller
`state()` callers (grep for `vehiclePresence` / `.state(`):
- `CarApiVehicle.atHome` (TeslaAPI.py:1669-1685): "home" → True, "away" → False, anything else → raw `_locationAtHome`.
  - With UNKNOWN, the raw answer (True, the fix was inside the radius) is used. That is exactly today's value for every atHome reader: getCarsAtHome / minBatteryLevelAtHome (TeslaAPI.py:1565, 1572), TeslaAPIController (TeslaAPIController.py:59), HTTPControl lastAtHome (HTTPControl.py:377), the TeslaAPI policy-wide apply gates (TeslaAPI.py:944, 952, 1002) and the charge path (TeslaAPI.py:342, 642, 1458, 1468).
  - "away" would flip all of those to False for up to 10 minutes, including at every startup: a real behaviour change for charging decisions.
  - A new constant would also fall through to raw here, but it would leak a value the other callers do not know.
- `TeslaBLE.applyChargeLimit` (TeslaBLE.py:773) skips only `== "away"`. With UNKNOWN, the policy-wide BLE apply still tries the arriving car.
  - If it lands, that is BLE contact: `_reportContact(True)` → `observeContact` → HOME at once, an earlier confirmation than the 60 s probe.
  - It does no harm: since cfc59d6 it reads before it writes (adopting a hand-set limit and setting the dedupe). The arrival handler then resets the dedupe, and the per-VIN apply finds the car already at the target.
  - **Tradeoff:** while the car is still out of range, those attempts fail and can open TeslaBLE's circuit breaker. That costs little since efb8a14 (a fast fail, no read), and the breaker is closed again by contact or a TWC proof (4cb6a43). Reporting "away" would avoid those attempts, at the atHome cost above.
  - **Why this does not recreate the live problem** (breaker open, car really home, nothing getting through): `probePresence` is `@_serialized` but not wrapped in `_execute_with_retry`, so the breaker never gates it. `test_successful_probe_closes_the_breaker` opens the breaker, runs `probePresence`, and sees it closed. A breaker opened by failed policy-wide applies during ARRIVING cannot block the confirming probe. The probe runs, confirms the arrival, and closes the breaker.
- PresenceSources does not call `state()`: `apiSource` reads `_locationAtHome` directly, `telemetrySource` computes from sync coordinates, and `bleSource` probes.
- The TeslaBLE `_reportContact` / Telemetry / TeslaAPI `_reportLocation` paths only call observers.

## Tests (tests/unit/test_vehicle_presence.py)
TestBleConfirmedArrival (19) and TestDefaultBleApplies (3) cover:
- entering ARRIVING, with `state()` reporting UNKNOWN and an INFO log;
- BLE confirmation with the probe limit, and with the fill-in;
- a probe-driven entry confirmed by BLE in the same pass, and one that waits;
- BLE probed first whatever the order;
- the timeout (at 599 s still arriving, confirmed at 600 s with the fill-in) and the settable class attribute;
- drive-bys: across passes, in one batch, and cancelled by a probe's away answer (no arrival, no departure, nothing left to time out);
- confirmation by BLE contact, and by a TWC proof;
- failed probes not counting toward the away rule (5 intervals, then the timeout → HOME);
- the probe cadence;
- `_timeUntilNextDue` waking the thread within PROBE_INTERVAL;
- a VIN BLE doesn't apply to going HOME at once;
- an already-HOME car staying HOME;
- the lock invariant for `bleApplies`, `limitLookup` and the sources;
- the default `bleApplies` truth table, including a `Mock()` master.

Full suite: 770 passed, 1 warning (pre-existing). test_vehicle_presence.py run 5 times: 81 passed each. black --check clean.

## Concerns
- **Deviation needing a decision: the arriving-probe order.** The design said "probes BLE". I run BLE first, then the rest of the order, so a telemetry or API away answer can cancel. The cost: an ARRIVING car with no live telemetry hits the API source every 60 s for up to 600 s (up to 10 online checks plus data fetches when it is online), where a HOME car is probed only on nomination. With TeslaMate live (the user's box), telemetry answers first and the API source is never reached. Alternative: restrict arriving probes to ["ble", "telemetry"], and accept a bogus HOME followed by a departure restore for drive-bys of cars located only through the API.
- See the circuit-breaker tradeoff above: a BLE car arriving early sees failed policy-wide BLE attempts until it is in range.
- The TeslaAPI policy-wide apply also treats an ARRIVING car as home, via raw atHome, as it did before. For a drive-by it may send an API apply, as it already could.
- A car that is HOME only by timeout, with no BLE contact, is still subject to the BLE-only away rule afterwards. That is unchanged behaviour, but a car parked just outside BLE range would flip AWAY after 2 failed probes if no telemetry is live, and then back to ARRIVING on the next fix. With telemetry live the away rule does not apply.
- Arriving VINs add up to two due times per pass (the next probe and the deadline). Popped due times are removed, so the set stays small.
- After a cancel, `_due[vin]` still holds the scheduled probe and the +600 s deadline. Each fires one rate-limited, ordinary probe later. Harmless.
- Startup with a bleProven car parked out of BLE range: before, location home → arrival handler → `lastChargeLimitApplied == 0` → nothing queued. Now the arrival fires at +600 s, after the policy has been evaluated, so a per-VIN apply is queued. It normally finds the car already at the policy limit (the policy-wide apply reached it through raw atHome), so it costs one wasted read. Still a behaviour change.
- The flapping case above (HOME by timeout → BLE-only away rule → AWAY with a departure → ARRIVING → ...) affects only cars with no live telemetry, and the API source has to have no answer (car asleep) for it to happen.
