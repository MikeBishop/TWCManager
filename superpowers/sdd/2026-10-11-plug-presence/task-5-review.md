# Task 5 review (a0fbb5d..f4d6837)

Paths below are in the wt-plug checkout at f4d6837.

### Spec Compliance

- ❌ Issues found:
  - With `commandPolicy: ble_only` (the live box's setting), the 5-minute fallback does nothing, but it still sets `fallbackSent`, and that stops all further BLE probing (VehiclePresence.py:1080, :1092). This is plan-mandated: the brief sets `fallbackSent` unconditionally. The spec says to "retry while BLE reaches the car". A car whose BLE restore failed as it drove off keeps the held limit even when it later comes back into BLE range without being plugged in. (Important #1)
  - The reconciler only runs at a transition. A limit that becomes held after the car is already not home is never restored, so "not home + limit held → restore" is not enforced as an invariant. This is brief-vs-spec tension: the brief starts the record at the transition. (Important #2)
- ⚠️ Cannot verify from diff: nothing open. The restart rule (a presumed car read unplugged with a limit held) is shown by `TestDiscoveryWithAHeldLimit` through the existing `_leave` path.

Spec items checked as met:
- `bleApplies` is moved and delegated to (PresenceHandlers.py:32, VehiclePresence `_defaultBleApplies`).
- `onDeparting` behaves as specified: nothing held → False; BLE → `localOnly`; otherwise `_remoteRestore` right away. The `unambiguous=False` branch is kept.
- `departureHandler` behaves as before, through the shared `_remoteRestore`.
- `arrivalHandler` calls `_cancelRestore` first, also before the early return when the policy hasn't been evaluated (PresenceHandlers.py:68).
- The constants are present.
- `DepartingRecord` has the specified fields.
- `_restorePending` is implemented.
- The probe cadence is 60/600 with an 1800 s cap.
- The fallback fires once after 300 s gone.
- A reachable probe resets the gone timer.
- The retry is gated on `queued()`.
- A non-BLE car is never probed.
- A replug cancels the restore (`_goHome` pops the record and `onArrival` cancels).
- `TestDepartAndReturnThroughTheQueue` is moved and rewritten to use the real handlers and a real queue.
- Task-4 fixes 1–3 are all at VehiclePresence.py:913, :737 and :726, each with a test.

### Strengths

- The advisor-found drift bug (a slow failing probe pushes the fallback due time into the rate limit) is real. It is pinned by `test_slow_failing_probes_still_reach_the_fallback` and fixed narrowly.
- `_remoteRestore` removes the duplicated remote-restore body cleanly, and `departureHandler`'s behaviour is unchanged.
- `queued()` is thread-safe:
  - `_running` is set in `_next` and cleared in the worker's `finally`, both under `_cond` (VehicleCommandQueue.py:152, :192). `queued()` reads under the same lock.
  - No other path clears `_busy` (checked :151 and :191), so `_running` cannot go stale.
  - It is read-only, so putting it on branch 3 does not change branch 1's behaviour. The file edit should still be flagged to the user, as the report does.
- `TestDepartAndReturnThroughTheQueue` now covers the user-visible contract end to end: a pending restore is replaced and only the 50% apply runs.
- The tests use a scripted clock and probe recorder and assert exact probe times, for example `[0, 60, …, 1800, 2400, 3000, 3600]`, rather than mock call counts.

### Probe-storm check (requested)

Named risk: departing BLE-only probes bypass `PROBE_INTERVAL` (VehiclePresence.py:601), so extra nominations could multiply probes.

What I checked: `nominate` (VehiclePresence.py:409–424). It drops any due time within `PROBE_INTERVAL` (60 s) of an existing due time for that VIN, so a VIN's pending due times are always at least 60 s apart.

- In fast mode, a chain always has its next due time within 60 s, so an outside nomination gets absorbed.
- The worst case is about one BLE-only probe per 60 s, plus one extra each for a `nominate(None)` or home-by-telemetry nomination.
- There is no storm. See Minor #1 for the slow-mode erosion.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **Plan-mandated. VehiclePresence.py:1092 / :1080, PresenceHandlers.py:166.** Under `ble_only`, the fallback ends BLE retries without sending anything.
   - Under `ble_only`, `onDeparture` reaches `_remoteRestore`, which logs "no remote command channel" and returns False. The tracker still sets `fallbackSent`, so probing stops and there is no BLE retry until a plug brings the car home.
   - This conflicts with the spec's "retry while BLE reaches the car", and the deployed configuration hits this path.
   - The implementer followed the brief, so this is plan-mandated:
     - The brief says the tracker "runs `onDeparture(vin, None)` once and sets `fallbackSent`", with no condition on success.
     - It limits probing to "no fallback sent yet".
     - Its own listed test `test_ble_gone_fallback_needs_a_remote_channel` (ble_only: nothing queued) encodes this dead end.
   - The controller or user should rule on it.
   - Fix: keep setting `fallbackSent`, but after the fallback keep nominating at `DEPARTING_SLOW_PROBE_INTERVAL` while the limit is held, with no clamp to the fallback time. A reachable probe then runs the `localOnly` retry. These probes are wake-free.
   - Do not "set `fallbackSent` only when a restore was queued". Once `now - gone >= 300`, the clamp at :1112 (`max(0, gone + 300 - now)`) gives a delay of 0. The departing probe also bypasses the rate limit (:601), so every pass would re-probe: a probe storm.
   - The "no probing after the fallback" assertion in `test_ble_gone_for_five_minutes_sends_one_remote_restore` would change.
   - Add a test: `ble_only` and BLE gone for 300 s give no remote command; then reach becomes True, and one `localOnly` retry follows.
   - A failed remote restore that is not retried matches the existing `departureHandler` rule and is acceptable.

2. **Brief vs spec tension. VehiclePresence.py:631 / :1044.** Records start only on the home → not-home transition (implementer concern (a)).
   - The brief says the record starts "when a car goes not-home with a limit held". The superseded box and the spec frame the feature as a reconciler on presence × held limit. The controller should rule on which applies.
   - As built, a limit that becomes held while the car is already not home is never restored. I checked whether the apply path re-checks presence:
     - TeslaBLE.py:793–808 gates only the policy-wide apply (`vin is None`), and it checks `isHome` before the BLE write, not after.
     - The per-VIN arrival apply is never gated.
   - So there are two windows:
     - An arrival apply running in the worker when the car unplugs. `onDeparting` sees `lastApplied == -1`, then the apply finishes and sets 50.
     - A policy-wide apply that passed `isHome` and is mid-write (BLE writes take seconds, longer with retries) as the car unplugs, while nothing was held before.
   - Likelihood is low: an unplug within the first minute after plugging in, or a policy change at the moment of unplug. But when it happens it is silent: the car drives off at the managed limit and keeps it until it next plugs in at home.
   - Fix: at the end of each pass, check the NOT_HOME known VINs that have no record and whose `_restorePending` is true. For each, call `_runDeparting(vin, True)` and then `_startDeparting(vin, now)`, mirroring :630–631. `_startDeparting` assumes `onDeparting` has already run. `getNormalChargeLimit` is an in-memory read, so this is cheap.
   - Add a test: the car is not home with nothing held; held becomes True; the next pass runs `onDeparting` and creates a record.

#### Minor (Nice to Have)

1. **VehiclePresence.py:1113 (with :420).** In slow mode (600 s), an outside nomination of a departing VIN lands more than 60 s from the chain's next due time. Its probe's reconcile then starts a second self-perpetuating chain, so repeated outside nominations can erode the slow cadence back toward one probe per 60 s. This is bounded and wake-free. Suggested fix: before nominating, drop the VIN's other future due times, or skip nominating when one is already due within `delay`.
2. **VehiclePresence.py:612–615.** When the departing due time fires after the limit is no longer held, the whole probe of that VIN is skipped, including a coinciding non-departing nomination. This is rare, and the report notes it.
3. **VehiclePresence.py:1105 (`_reconcileDeparting` retry).** The retry calls `onDeparting`, which re-checks `bleApplies`. If TeslaBLE has been unloaded or `bleProven` cleared since the record began, a "BLE retry" turns into an immediate remote restore while the car is reachable over BLE. This is harmless but surprising, and should get a comment or be passed through explicitly.
4. **VehiclePresence.py:1044 (`_startDeparting`).** The first BLE-only probe runs right after the `localOnly` restore is queued, so the probe and the worker's restore may contend for the BLE adapter. This is not a correctness issue, since TeslaBLE serialises, but it adds up to `presenceProbeTimeout` (15 s) to the pass. Starting the first probe at +`DEPARTING_PROBE_INTERVAL` would avoid the contention.

5. **VehiclePresence.py:1061 (`_startDeparting`).** It passes the pass-start `now` to `_reconcileDeparting`. The due loop instead passes `probedAt`, captured just before the probe, as the drift fix intended. The only effect is a slightly earlier `bleGoneSince`.

Check run: the brief says to move `TestDepartAndReturnThroughTheQueue`. I grepped `tests/unit` at HEAD: there is one definition (test_vehicle_presence.py:1337), and none existed at base a0fbb5d. Nothing is shadowed and no copy is left behind.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The reconciler, the handlers and the queue change are well built and well tested. However, under the deployed `ble_only` policy the "remote fallback" ends BLE retries without sending anything. And the reconciler only starts at a transition, so a limit that becomes held after departure is never restored. Both contradict the spec's presence × held-limit invariant, and both have small fixes.
