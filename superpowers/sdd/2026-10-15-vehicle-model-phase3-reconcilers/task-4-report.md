# Task 4 report: local provider command methods return outcomes

**Status:** DONE (with concerns)
**Commit:** bb512d0 on `vehicle-model/phase3` (parent 97377b8)
**Tests:** task set 142 passed; full suite `tests --ignore=tests/API --ignore=tests/integration` 1423 passed, 1 xfailed (was 1415 at 97377b8; +7 in `test_provider_outcomes_local.py`, +1 `test_gen3_commands_return_outcomes`).

## What changed

- `TeslaBLE.py`
  - `commandOutcome(vin, command, args=None)`: upper-cases the VIN, resets `_keyRefusal.refused`, calls `sendCommand(vin, command[, args])` positionally (args are omitted when None), then classifies.
  - `probe(vin)`: one `_sendCommand_internal(vin, "body-controller-state", noteProof=False)`, with no `_execute_with_retry`, classified the same way.
  - `_classify` order:
    1. the refusal flag or a stored `"refused"` → `REFUSED "key"`;
    2. `None` → `UNREACHABLE "no reply"`;
    3. a satisfied reason → `SATISFIED <reason>`;
    4. `parseCommandOutput` → `DONE`;
    5. anything else → `ERROR <category>`.
  - `_satisfiedReason` and `_errorCategory` are factored out of `_is_already_satisfied` and `parseCommandOutput`; both methods keep their behaviour.
  - `_sendCommand_internal(..., noteProof=True)` gates both `_noteBleProof` sites. Claims are never touched here.
- `TeslaBLEProvider`: adds `probe`, `setChargeLimit`, `startCharging`, `stopCharging`, `setAmps` and `wake`, per the brief.
  - `startCharging` returns `SATISFIED "scheduled"` when `_scheduleBlocksStart`.
  - No pre-wake.
- `Gen2TWCProvider`
  - Declares `START_CHARGING: Declaration(LOCAL)`.
  - `ready(START_CHARGING)` needs mode 2, a slave and `desired.state(key).lastStopProvider == "Gen2TWC"`. It reads `getattr(master, "desired", None)` and returns False when that is absent, because the real `TWCMaster` has no `desired` yet and `Provider.summary()` calls `ready` unguarded.
  - `startCharging` sets `respondToSlaves = 1` under `settingsLock` → `DONE "respond"`.
  - `stopCharging` outcomes:
    - no slave → `UNSUPPORTED "no slave"` (checked first);
    - mode 2 → `stopRespondingToSlaves()` → `DONE "respond"`;
    - mode 3 → `slave.stopRequested = True` → `DONE "queued"`;
    - any other mode → `UNSUPPORTED "mode N"`.
  - `setAmps` → `DONE` (no slave → `UNSUPPORTED "no slave"`).
  - `_slaveForKey` upper-cases a well-formed VIN key and leaves `anon:` keys alone (M5).
- `Gen2TWC.stopRequested = False` is set in `__init__`. `TWCSlave.send_master_heartbeat` consumes it at the very top, before the `respondToSlaves` quiet return, and calls `master.sendStopCommand(self.TWCID)`. It uses `getattr(self, "stopRequested", False)` because bare `TWCSlave` is still built in `test_twcslave.py` and `test_registry_callers.py`.
- `Gen3TWCProvider`: `startCharging`, `stopCharging` and `setAmps` → `DONE`; `UNSUPPORTED "no unit"` when no unit serves the key.
- `Suppressions.suppressed`: `STOP_CHARGING` on a non-local provider is suppressed when `chargeStopMode` is 2 or 3. A non-integer value reads as "not suppressed".
- `ProviderOrder.dispatch`: success is `_succeeded(r)`, meaning `isOutcome(r) and r.kind in SETTLED`, or for a legacy return `bool(r) and r != "error"`.
- `tests/unit/gen2_helpers.py` is the reference copy, unchanged.
- Adjusted Phase 2 tests:
  - `test_commands_call_the_module_by_vin`: now asserts `sendCommand(VIN, "charging-set-amps", 12)` and `wake` → `UNREACHABLE`.
  - The Gen2 disruptive-stop test: mode 3 is now queued, with no `sendStopCommand` from the caller.
  - The Gen2 set-amps test.
  - The Gen3 commands test.
- black was run only on the 8 lib files touched; it changed nothing.

## Fail-before (before implementation)

The brief predicted `AttributeError: setChargeLimit`. The base `Provider` already returns `Outcome(UNSUPPORTED, "not implemented")`, so the failures seen were comparisons instead (12 failed, 36 passed):

```
E   AssertionError: assert Outcome(kind=... implemented') == Outcome(kind=...il='no reply')
E   AssertionError: assert ('unsupported' == 'refused'
E   AssertionError: assert ('unsupported' == 'done'
E   AssertionError: assert (Outcome(kind=... implemented') == Outcome(kind=...l='scheduled')
E   AssertionError: assert (False == Outcome(kind='unsupported', detail='mode 1'))
E   AssertionError: assert (True == Outcome(kind='done', detail='queued'))
E   AssertionError: assert ('unreachable' == 'done'          # dispatch returned the truthy UNREACHABLE
E   AttributeError: 'bool' object has no attribute 'kind'
FAILED test_provider_outcomes_local.py (all 7), test_teslable_provider::test_commands_call_the_module_by_vin,
       test_gen2twc_provider (2), test_gen3twc_provider (2)
```

## Deviations from the brief

1. **Test fixture.** In `test_ble_key_refusal_is_refused_and_the_claim_follows_the_pairing_window` I added `master.getModuleByName = Mock(return_value=None)`.
   - Why: `make()`'s Mock master answers `getModuleByName("TeslaAPI")` with a Mock, whose `vehicleScheduledChargingPending` is truthy. The real `_scheduleBlocksStart` therefore reported a schedule block, and `startCharging` returned `SATISFIED "scheduled"` before the refusal path was ever reached.
   - What I did not do: I left `_scheduleBlocksStart` as it is, since the real TeslaAPI method returns a bool.
2. **Heartbeat read.** `TWCSlave.send_master_heartbeat` reads `getattr(self, "stopRequested", False)`, not the brief's literal `self.stopRequested`, because bare `TWCSlave` instances still exist in tests.
3. **Gen3 test.** `test_gen3_commands_return_outcomes` also covers `startCharging` and `setAmps`, both for a served key and for an unknown one.

## Checks

- The full suite's "1 warning" did not reproduce on a rerun: a second full run printed no warnings summary. The warning is not from the new tests.
- The only producer of a cloud stop on the legacy path is `stopCarsCharging` mode 1 (`{"cmd": "charge", "charge": False}`). Modes 2 and 3 never queue one, so the new suppression cannot drop a stop that reaches the cloud today.

## Concerns

1. **Legacy façade path until Task 10.** `VehiclePriority.setAmps` → `dispatch` → `TeslaBLEProvider.setAmps` now sends a bare `charging-set-amps`.
   - What is lost: today's pre-wake from `setChargeRate` and the `availableCurrent` `_stampWrite`. Providers do not stamp under the Outcome contract.
   - Risk: a sleeping car's BLE set-amps can now fail all 3 attempts and fall through to a Fleet `setAmps` where a BLE wake might have succeeded first.
   - The brief accepts this; no existing test asserts the stamp through the façade.
2. **Existing raw-output logging.** `_sendCommand_internal` already logs raw tesla-control output at WARNING ("failed with return code ...: {output}" and "full error output: {output}"). That breaks the rule against raw output at INFO or above, and `probe` now reaches that path too.
   - It predates this task, so I left it as it was. I recommend demoting it to DEBUG in a follow-up.
3. **`probe` and a stored refusal.** `probe` returns `REFUSED "key"` when the stored status is `"refused"`, even if the VCSEC query was answered. This follows the brief's rule, which is applied before the output is read, and means a refused key is never treated as usable.
4. **`ready(START_CHARGING)` side effect.** `desired.state(key)` creates a `ControlState` entry for the key, as specified. It is harmless, but it means `ready` writes into the store.

## Fix round 1

**Commit:** f394844, on top of bb512d0.
**Tests:** the full suite passes: 1428 passed, 1 xfailed (+5 new tests).

**Fails before the fixes:** 6 tests failed.
- `test_ble_key_refusal_…` failed with REFUSED/key against ERROR/pairing.
- The gen2 test failed with `desired.keys()` equal to `['5YJ3E1EA1KF000001']` instead of `[]`.
- The logging test found raw `SECRET-MARKER` in WARNING lines at TeslaBLE.py:704 and :707.
- The in-window refusal test failed.
- The breaker test failed.
- `TWCSlave.stopRequested` failed with an AttributeError.
- The out-of-window refusal test already passed.

**Fixes:**
- **I1:** In `_sendCommand_internal`, I deleted the duplicate "full error output" WARNING.
  - The WARNING now logs only the command, the return code and `_errorCategory(output)`.
  - The raw output moved to DEBUG, truncated to `[:200]`.
  - Test `test_a_failing_command_or_probe_logs_no_raw_output_at_info_or_above` covers a failing command and a failing probe. It asserts no output at INFO or above, that the category and the command appear, and that the output is still logged at DEBUG.
- **I2:** I added `DesiredStore.peek(key) -> Optional[ControlState]`. It takes the lock and never creates an entry.
  - `Gen2TWCProvider.ready(START_CHARGING)` uses it, so None means False.
  - The gen2 test asserts `desired.keys() == []` after `summary()` and `ready()` in mode 2.
- **I3 (coordinator ruling):** A key refusal inside the pairing window now returns `Outcome(ERROR, "pairing")`; outside the window it is still `REFUSED "key"`.
  - The brief's assertion is updated to `== O.Outcome(O.ERROR, "pairing")`, with the claim kept.
  - New tests use real tesla-control refusal output through `_sendCommand_internal`, covering both a command and a probe:
    - `test_key_refusal_inside_the_pairing_window_is_a_retryable_error_and_keeps_the_claim`
    - `test_key_refusal_outside_the_pairing_window_is_refused_and_drops_the_claim`
- **M1:** When a probe is answered (output not None and not REFUSED), it calls `circuit_breaker.record_success(vin)`. A failed probe records nothing.
  - Test `test_an_answered_probe_closes_an_open_circuit_breaker` checks three things:
    - An open breaker blocks `setAmps` with no wire call.
    - An answered probe closes the breaker, so the next `setAmps` reaches the wire.
    - Repeated failed probes do not open the breaker.
- **L1:** `TWCSlave.stopRequested = False` is now a class attribute next to `timeLastRx`. The heartbeat reads `self.stopRequested` as the brief writes it, and `Gen2TWC.__init__` still sets the instance attribute.

**Left as is:**
- **L2:** The mode-2 start is ready only while the slave exists, about 26 s after a stop. This needs no code here; it carries to Task 8, which should not expect a Gen2 start after the slave times out, and should not treat a missing slave as "not stopped by us".
- **L3:** An answer with return code 0 is re-parsed by `parseCommandOutput`, so an unrecognised success becomes a retryable `ERROR "unknown"`. That is today's behaviour, kept and noted for Tasks 6 and 11.
- **Out-of-scope RS-485 writes off the serial thread:** `HTTPControl.py:906` and `TWCManager.py:370` predate this task. I left them unchanged and have only noted them.
