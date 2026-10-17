# Task 4 review: local provider command outcomes (97377b8..bb512d0)

**Spec compliance: COMPLIANT**
**Task quality: PASS WITH FINDINGS** (3 Important, 1 Medium, 3 Low)

Tests: the task set (8 files) passed, 142 tests. I also ran my own probe script against the checkout (scratchpad `t4probe/probe_t4.py`); results are cited below.

## Spec compliance

Every interface in the brief is present, with the specified signatures, kinds and details:

- **TeslaBLE:** `commandOutcome`, `probe`, `_sendCommand_internal(..., noteProof=True)`.
- **TeslaBLEProvider:** `probe`, `setChargeLimit`, `startCharging` (returns `SATISFIED "scheduled"` when the schedule blocks), `stopCharging`, `setAmps`, `wake`. None of them pre-wakes.
- **Gen2TWC / TWCSlave:** `Gen2TWC.stopRequested`, consumed at the top of `TWCSlave.send_master_heartbeat`.
- **Gen2TWCProvider:**
  - It declares `START_CHARGING` at LOCAL, and its readiness is gated as specified.
  - `startCharging` and `stopCharging` return the specified kinds and details: `no slave`, `mode N`, `respond`, `queued`.
  - `_slaveForKey` now upper-cases a VIN key (M5).
- **Gen3TWCProvider:** commands return outcomes, with `no unit` when no unit serves the key.
- **Suppressions:** billed stops are suppressed under `chargeStopMode` 2 and 3.
- **ProviderOrder.dispatch:** success is decided by `_succeeded`.
- **tests/unit/gen2_helpers.drive:** present.

The names later tasks use all exist: `commandOutcome`, `probe`, `stopRequested`, `gen2_helpers.drive`, `lastStopProvider`, `noteProof` and `_slaveForKey`.

Deviations:

1. **`getModuleByName = Mock(return_value=None)` in the refusal test: accept.** The Mock master answers `TeslaAPI` with a Mock whose `vehicleScheduledChargingPending` is truthy. The real method returns a bool.
2. **`getattr(self, "stopRequested", False)` in the heartbeat: accept.** A cleaner fix is a class attribute `stopRequested = False` on `TWCSlave`, next to `timeLastRx` at `TWCSlave.py:27`. The brief's literal `self.stopRequested` would then work on bare instances (L1).
3. **Wider Gen3 test: accept.**

## Hard checks (verified)

- **No RS-485 write off the serial thread from this task.**
  - The mode-3 stop only sets `slave.stopRequested` (`Gen2TWCProvider.py:113-125`).
  - The probe sent the stop through the real heartbeat via `gen2_helpers.drive`, and the caller made zero `sendStopCommand` calls.
  - The flag is consumed before the `respondToSlaves` quiet return. The probe showed one stop sent while `respondToSlaves=0`, with the flag cleared afterwards.
  - Heartbeats run only on the serial loop (`TWCManager.py:973`, `:1332`).
  - The bool flag has no lost-update race that matters: a set racing the consume gives one send, or a send on the next heartbeat.
  - Writing a stop frame and then a heartbeat frame back to back is today's mode-3 behaviour (`TWCSlave.py:579` → `stopCarsCharging`).
- **The heartbeat does no vehicle I/O.** This task adds no registry writes there. The existing one at `TWCSlave.py:600` is unchanged.
- **The probe:**
  - It makes one `_sendCommand_internal(vin, "body-controller-state", noteProof=False)` call, with `_execute_with_retry` asserted unused.
  - The probe confirmed `_run_command_with_timeout` is called once, with `timeout=commandTimeout` (5).
  - It runs under `_bleLock` (`@_serialized`).
  - The claim stays `unproven` after an answer.
  - VCSEC `body-controller-state` needs no infotainment session, so it does not wake the car. This is tesla-control's documented behaviour; I could not verify it on hardware here.
- **Refusals:**
  - `_execute_with_retry` returns at once on a refusal, so `_keyRefusal.refused` survives to `_classify` on the same thread (it is a `threading.local`).
  - Outside the pairing window, the claim is dropped and `ready` goes False.
  - Inside the window, the claim is kept. The outcome kind is the subject of I3.
- **dispatch cannot count a failure as success.** The probe gave ERROR, REFUSED, UNSUPPORTED and UNREACHABLE, and `dispatch` returned False for each. The legacy truthiness rule applies only to non-Outcome returns.
- **Billed-stop suppression drops nothing that reaches the cloud today.**
  - The only cloud-stop producer is `TWCMaster.stopCarsCharging` in mode 1 (`TWCMaster.py:2108`).
  - Modes 2 and 3 never queue a cloud stop.
  - `debugCommand` carries only `setChargeRate` and `wakeVehicle`.
  - Mode 3's cloud start (`startCarsCharging`) is untouched, because START is not suppressed.
- **Mode-2 start gating.**
  - The start needs all of: mode 2, a slave, and `lastStopProvider == "Gen2TWC"`.
  - A BLE-recorded stop, or no recorded stop at all, gives False (tested).
  - See L2 for the slave-timeout window.
- **Paid-call surface for current installs.**
  - The legacy path is `VehicleEndpoint` → queue `setAmps` → `VehiclePriority.setAmps` → `dispatch(localRule=True)`.
  - `candidates()` (`Order.py:103-109`) drops billed tiers whenever a ready local provider covers the amps. A BLE-claimed car therefore never falls through to a Fleet `setAmps`.
  - So the implementer's concern c1 is narrower than stated: only a value BLE does not `cover` reaches Fleet, as it does today. The interim ruling stands.
  - What is lost is BLE's pre-wake and `_stampWrite`, as the report says.
- **Tokens in logs.**
  - `Outcome.detail` never carries output: `_classify` passes only a reason word or a category.
  - Outside `_sendCommand_internal`, tesla-control output is logged at DEBUG only (`TeslaBLE.py:458`, `595`, `697`, `714`). State reads log only the return code (`:1147`). The pairing INFO line carries only success or failure.
  - The exception is I1.

## Findings

### Important

**I1 (ruling c2): raw tesla-control output is logged at WARNING, and the new probe now reaches it.** `lib/TWCManager/Vehicle/TeslaBLE.py:704-707`

- `"BLE command '…' failed with return code N: {output}"` and `"BLE command full error output: {output}"` interpolate the raw stderr.
- That stderr is from a `-debug` run, so it carries session and protocol detail.
- My probe 4 had `probe()` emit both lines at WARNING, with an injected marker string in them.

Fix:
- Delete line 707; it duplicates 705.
- Demote 705 to DEBUG and truncate it (`output[:200]`), like the other DEBUG lines.
- If a WARNING is still wanted, log only `command`, `return_code` and `self._errorCategory(output)`.
- Add a test: a failing command or probe logs nothing at INFO or above that contains the output.

**I2 (ruling c4): `ready(START_CHARGING)` creates DesiredStore entries.** `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py:84`

- `desired.state(vehicle.key)` → `DesiredStore._state` (`Desired.py:290-295`) inserts a `ControlState`.
- `ready` is called unguarded from `Provider.summary` (`Provider.py:100`, the status page) and from `Order.candidates` (`Order.py:76`, every walk).
- Probe 2: `desired.keys()` went from `[]` to `['5YJ3E1EA1KF000001']` after one `ready()`.
- A read path must not write. An entry created after the registry's `forget` is never collected.

Fix:
- Add a non-creating, locked read beside `state` at `Desired.py:523`. For example, `peek(key) -> Optional[ControlState]` returning `self._states.get(key)`, or `lastStopProvider(key) -> Optional[str]`.
- Use it in `ready`, so `None` gives False.
- Assert `m.desired.keys() == []` after a `ready()` in `test_gen2_stop_and_start_outcomes_and_the_billed_stop_suppression`.

**I3 (brief gap, not an implementer error): a key refusal inside the pairing window returns REFUSED, so BLE is excluded for the round right while the owner is pairing.** `lib/TWCManager/Vehicle/TeslaBLE.py:514-516`

- The brief and its test (`test_ble_key_refusal_…_pairing_window`, second assert) specify `REFUSED` inside the window. So the code is compliant.
- But `Outcome.py:20` defines REFUSED as "the provider has retired its slot or claim". Inside the window `_noteBleRefusal` (`:2037-2042`) deliberately keeps the claim: "the owner has not tapped the key card yet".

What this causes once Task 6 lands:
- Task 6 `plan` step 7 drops `rec.excluded`, and `AttemptRecord.exclude(…, REFUSED)` puts BLE in `refused` (`Desired.py:168-173`). That exclusion survives `newDesire` and clears only on `newRound`, which happens after every candidate is exhausted (step 9, backoff ≥ 600 s) or on a session event.
- If a paid candidate exists, the car goes to Fleet after `PAID_AFTER` even though the owner taps the card seconds later.
- If none exists, the aspect backs off for 600 s.
- So a normal first-pairing flow costs a paid call or a ten-minute delay.

Fix:
- In `_classify`, when `_keyRefusal.refused` holds and `self._inPairingWindow(vin)` is True, return `Outcome(ERROR, "pairing")`. That is retryable at `RETRY[aspect]` cadence, and the first retry after the tap proves the key via `_noteBleProof`.
- Change the test's second assert to `== O.Outcome(O.ERROR, "pairing")`, with the claim kept.
- The coordinator should rule on this, because it changes the brief's specified kind.

### Medium

**M1: the probe bypasses the circuit breaker in both directions.** `lib/TWCManager/Vehicle/TeslaBLE.py:501-512`

- `probe` calls `_sendCommand_internal` directly. It never consults `circuit_breaker.is_open` (`:1305`) and never calls `record_success`.
- Scenario:
  1. After 5 exhausted commands, the breaker is open for `circuitBreakerTimeout` (60 s).
  2. The Task 6 stale-failure probe answers DONE.
  3. The reconciler sends the real command over BLE.
  4. `sendCommand` meets the open breaker and returns `None`, giving `UNREACHABLE` with no wire attempt.
  5. The next pass goes paid.
- Plan Task 6's "a good probe sends over BLE" then fails for up to 60 s after a trip.

Fix:
- When a probe is answered (output not None and the key not refused), call `self.circuit_breaker.record_success(vin)`, since the channel is demonstrably up.
- Do not record failures from probes.
- Add a test: an open breaker plus an answered probe lets the next `commandOutcome` reach `sendCommand`'s inner call.

### Low

**L1: the heartbeat flag is read with `getattr` and a default.** `lib/TWCManager/TWCSlave.py:374`

- Declare `stopRequested = False` as a `TWCSlave` class attribute beside `timeLastRx` (`:27`).
- The heartbeat can then read `self.stopRequested` as the brief writes it.

**L2: the mode-2 start can only be ready in the first ~26 s of a stop.** `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py:78-84`

- While quiet, slaves stop answering. The serial loop deletes a slave after `slaveTimeout`, 26 s (`TWCManager.py:956-971`).
- After that, `slaveFor(vehicle)` is None, so `ready(START_CHARGING)` is False until `respondToSlavesExpiry` (60 s) resumes everything anyway.
- Today's mode 2 has the same 60 s self-healing, so nothing breaks. But Task 8 should not expect a Gen2 start after ~26 s, nor treat a missing slave as "not stopped by us". Carry this to Task 8.

**L3: an rc==0 answer is re-parsed, so a command that succeeded can be re-sent.** `lib/TWCManager/Vehicle/TeslaBLE.py:524-526`

- `_sendCommand_internal` treats rc==0 as success (`output or "ok"`). `_classify` then re-runs `parseCommandOutput` on it.
- An rc==0 answer whose `-debug` stderr matches no success indicator becomes `ERROR "unknown"`, which is RETRYABLE.
- This preserves today's semantics. In practice the `"ok"` substring indicator makes it rare.
- Note for Task 6 and Task 11. If it is fixed, `_sendCommand_internal` should return a sentinel success marker for rc==0.

Out of scope, noted so they are on record: some RS-485 writes predate this task and already run off the serial thread:
- `HTTPControl.py:906` (`/api/sendStopCommand` on the HTTP thread);
- `TWCManager.py:370` (the background task's `sendStopCommand`).

This task adds none.
