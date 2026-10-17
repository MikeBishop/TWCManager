# EVSE Fleet API cost fix: report

Status: DONE. Full unit suite: 953 passed. black is clean on the changed files.

## Commits
- b48f3af No Fleet API EVSE for a car a TWC serves or may serve
  - TeslaAPIController._twcServedVINs() scans master.getSlaveTWCs(). It collects
    currentVIN and real plugVIN values (read with getattr, so main's TWCSlave
    works too). It sets "blind" when a slave with no VIN (no currentVIN, and
    plugVIN is None or NON_TESLA) has reportedAmpsActual > 3. That is
    TWCSlave's power-start threshold.
  - allEVSEs leaves out served VINs. When blind is set it leaves out every
    vehicle. The existing cache sync then drops those vehicles.
  - Errors from the slave scan are caught and treated as "no TWC info", the
    same way _otherSlaveVINs handles them.
  - Nothing is stranded. TeslaAPIEVSE holds no state beyond its
    vehicle/controller/master refs. stopCharging goes to
    master.stopCarsCharging(VIN), which does not use the EVSE object, and
    nothing calls stopAllCharging. setTargetPower(0) was already a no-op.
  - Tests are in tests/unit/test_teslaapi_controller.py (9).
- 6aca1eb Don't resend a charge rate the car already accepted
  - CarApiVehicle.lastChargeRateSent = None (class attribute). It is set only
    when the response has response.result == True. A RequestException, a JSON
    error or result false leaves it unchanged.
  - A repeat request returns True without a POST. Callers treat any result
    other than False as success.
  - set_again keeps its meaning: it is the internal flag for the second send
    of a rate below 5 A (TeslaPy#42). It also bypasses the dedupe, which the
    double send needs.
  - charge_rate is now int() before the clamp. Fleet API takes whole amps,
    and the float shares from convertWattsToAmps would otherwise never
    compare equal.
  - requests.post gets timeout=30.
  - Tests are in tests/unit/test_teslaapi_chargerate.py (7).

## Concerns
- A NON_TESLA slave drawing power counts as blind, as the spec says ("no real
  plugVIN"). Every API vehicle is excluded while a non-Tesla car charges on a
  TWC. This is conservative, but it hides a Tesla on a third-party charger
  during that time.
- The dedupe record can go stale. It only tracks what TeslaAPI.setChargeRate
  sent. If the rate changes through the Tesla app, through BLE
  (TeslaBLE.setChargeRate), or after a failed send, a later request for the
  recorded value is skipped. This includes the TWC's once-per-session raise
  to wiringMaxAmps. There is no expiry. The record lives in memory, so a
  restart clears it.
- The web UI debug "setChargeRate" is also deduped.
- int() truncates, so 31.9 A becomes 31 A. Before this change the float was
  sent as-is.
- Cherry-picking to main: the production code in both commits uses getattr
  and applies there. tests/unit/test_teslaapi_controller.py reads
  TWCSlave.NON_TESLA, which main's TWCSlave doesn't have. Replace it with the
  literal "non-tesla" when cherry-picking.
- VehiclePriority counts any truthy result other than "error" as success. A
  deduped True therefore does not fall back to BLE. Separately, and already
  true before this change: a result-false response dict is also truthy, so
  VehiclePriority counts it as success.
- black --check over the whole tree reports 53 files that were already
  unformatted, test_teslaapi_presence.py among them. They were left alone.

## Follow-up: resend window (concern 2)
- 8e04ca8 Resend an unchanged charge rate after 10 minutes. Adds TeslaAPI.CHARGE_RATE_RESEND_AFTER = 600 and
  CarApiVehicle.lastChargeRateSentTime, which is set together with
  lastChargeRateSent when the send succeeds. A repeat is skipped only within
  600 s of that send. After that the same rate goes out again, and the window
  restarts. This allows at most one POST per car per 10 min.
- New tests cover a repeat inside the window (skipped) and at the window's
  end (resent, then skipped again). Suite: 955 passed. black is clean on the
  changed files.

## Follow-up: review3 fixes (I1, I2, M1-M4)
- 5851cf8 Close the Fleet EVSE gaps for a car an unnamed TWC may serve (I1, M1).
  - A TWC with no known VIN puts the controller in blind mode (no Fleet EVSEs
    at all) when it reports any non-00 state or draws at least 1 A. 1 A is
    the threshold for isCharging and for the VIN query.
  - While any TWC has no known VIN, a car whose live telemetry says
    pluggedIn True is also excluded. "Live" means syncSource is not
    "TeslaAPI", the same test telemetryChargeLimit and
    PresenceSources.telemetryPluggedIn use. The check is inlined on the
    vehicle object, so the commit doesn't depend on the branch-only helper.
  - A failed slave scan now fails closed (blind).
- a5480b7 Harden setChargeRate's skip-repeat record (M2, M3, M4, timeout).
  - Below 5 A, the rate is recorded only when both the first send and the
    set_again resend are accepted.
  - The rate is parsed with int(float(x)). A value that won't parse (a
    non-numeric string, None, NaN or inf) logs an error and returns False
    without a POST.
  - The resend window runs on time.monotonic().
  - The POST timeout is now 10 s.
- 3ea8622 Queue Fleet API charge rates to the vehicle worker (I2).
  - TeslaAPIEVSE.setTargetPower queues {"cmd": "fleetSetChargeRate",
    "amps": int(amps), "vehicle", "module": TeslaAPI}.
  - VehicleCommandQueue runs fleetSetChargeRate on the module named in the
    task, without resolving one. It never goes through VehiclePriority or
    BLE.
  - Coalescing is keyed per VIN, separately from the TWC's setChargeRate.
  - When TeslaAPIController drops an EVSE from its cache, it cancels that
    car's pending fleetSetChargeRate.
- Tests: 973 passed. black is clean on the changed lines. The new test
  block in test_vehicle_command_queue.py was appended without reformatting
  the file's existing lines, which were already not black-formatted.

### Concerns
- 3ea8622 relies on the branch-only vehicle command worker
  (master.queue_vehicle_command), so it doesn't cherry-pick to main as it
  is. On main the 10 s timeout from a5480b7 is the only bound.
- If a TWC never reports a VIN (CAN off, DIP 2 down), its "unknown" flag
  stays set permanently. While a car is plugged into it, every Fleet EVSE
  is gone. While it sits idle at 00, every telemetry-plugged car is
  excluded, including a car on a third-party charger. This is conservative
  by design.
- A queued Fleet rate shares the single worker with BLE commands, which can
  take minutes. The rate can wait behind them, but coalescing keeps only
  the newest rate for each car.
