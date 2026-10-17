# Final fix pass re-review: 32bd76b..5a5c112

Reviewer: Opus 5.5. Read-only. Diff read in full (lib, then tests). Unit suite: 707 passed, 1 pre-existing warning.
One focused probe was run from the scratchpad (a proof and an away fix in the same snapshot, see N1).

## Finding Verdicts

Numbered as in final-fix-report.md.

1. **atHome stale for telemetry-synced cars, so the policy-wide TeslaAPI apply commands away cars**: ADDRESSED.
   - `CarApiVehicle.atHome` is now a property. It returns `presence.state()` when that is home or away, and otherwise falls back to raw `_locationAtHome` (TeslaAPI.py:1668-1690).
   - Telemetry departures reach presence (Telemetry.py:182-183), so the vin=None loop's skip sees AWAY (TeslaAPI.py:1002).
   - `needToWake` and the stopTrying reset are gated the same way (:944, :952-957).
   - Tests: `test_policy_wide_gate_skips_car_presence_says_away` and `..._uses_raw_when_presence_unknown`.
2. **TeslaBLE vin=None apply skips AWAY cars**: ADDRESSED.
   - The skip applies only when `vin is None` (TeslaBLE.py:756-768), and a per-VIN apply is never skipped.
   - When every target is skipped, the result is True, the same as the existing all-skipped dedupe path.
3. **Bound `_observations` and due times**: ADDRESSED. Observations go into `deque(maxlen=256)` (VehiclePresence.py:93-96). Each per-key due set is capped at 64 (:155-158). The cap policy has a side effect, see N2.
4. **Real-queue HOME -> AWAY -> HOME test**: ADDRESSED. `TestDepartAndReturnThroughTheQueue` uses the real handlers and a real `VehicleCommandQueue`. It asserts the pending entry after each transition, and the module sees exactly `[(50, V1, False)]`.
5. **Arrival before the first policy evaluation**: ADDRESSED. `limit == 0` returns after the reset and adoption, and -1 still restores (PresenceHandlers.py:55-64). Both paths are tested.
6. **`resetChargeLimitState` clears `stopAskingToStartCharging`**: ADDRESSED (TeslaAPI.py:1528-1530), and tested.
7. **INFO outcome line for a per-VIN TeslaAPI apply**: ADDRESSED.
   - The outcome is tracked on every branch and logged only when `vin is not None` (TeslaAPI.py:990-1080).
   - The early `return "error"` paths stay silent at INFO, as the report states.
8. **TWC VIN as proof of home; reconcile on the presence thread**: ADDRESSED, with a gap (N1).
   - `recordVehicleVIN` only calls `observeProof` (TWCMaster.py:1462).
   - The hook runs unlocked (VehiclePresence.py:255-259, 352-362).
   - `reconcileHomeLocation` reads raw `_locationAtHome` and no longer forces it True.
   - 5a5c112 recomputes the raw value only after an actual home move (TeslaAPI.py:1516-1518).

## Named risk checks

(a) **Feedback loop: clean.** The grep of every atHome read in lib/ classifies as follows.
- **Presence inputs, all raw or source data:**
  - `apiSource` reads `_locationAtHome` (PresenceSources.py:106).
  - `telemetrySource` computes `is_location_home(sync…)` (:53).
  - `bleSource` reports contact only (:83).
  - `Telemetry._reportLocation` computes from sync coords (Telemetry.py:182).
  - `CarApiVehicle._reportLocation` reads raw (TeslaAPI.py:1701).
  - `observeProof` takes the TWC VIN.
- **Writers (setter, raw only):** TeslaAPI.py:1518, 1884, 1899, 1954.
- **Raw readers on purpose:** reconcile (:1482, :1487) and status deferral (:1981).
- **Property consumers, none of which feeds presence:**
  - TeslaAPI.py:342 (wake gate), 642 (start/stop), 944/952/1002 (limit gates), 1458, 1468, 1565, 1572.
  - TeslaAPIController.py:59.
  - HTTPControl.py:377.

(b) **Lock order: clean.**
- `state()` touches only `_state` under `_lock`. Presence holds `_lock` only for recording, snapshot/`_collectDue`, `_apply*`, `_dropAwayFixes` and `_stopped` checks.
- Sources, probes, handlers, the hook and `knownVehicles()` all run unlocked (VehiclePresence.py:233-299).
- Callers of the getter that hold `_bleLock`, `backgroundTasksLock` or nothing (HTTP, the serial loop) take `_lock` as a leaf, and presence never acquires those locks while holding `_lock`.
- The only call made under `_lock` is `logger.info` in `_setState`, which is unchanged from the base.

(c) **observeProof/reconcile: sound, but incomplete.**
- `recordVehicleVIN` does no I/O: it updates settings, queues a background task and calls `observeProof`.
- The hook runs unlocked.
- Dropping `("location", vin, False)` that arrived during the hook is sound. It is only for the proof's VIN, only for the window in which the car is plugged into a TWC, and a car cannot drive away while plugged in.
- The gap: it does not cover away fixes already in the same snapshot behind the proof (N1).

(d) **Bounded buffers.**
- **Observations, keeping the newest: fine.** Location state is latest-wins. Losing an old intermediate away/home pair loses only a no-op cycle. When the thread runs, it drains every pass, far below 256.
- **Due times, keeping the earliest: not neutral while the thread runs** (N2).

(e) **TeslaBLE all-away returns True: correct.**
- The return value is the same as the existing all-skipped dedupe path. That is consistent, because TeslaAPI's own policy-wide loop skips the same cars through the `atHome` property.
- A mixed case (one car away, one attempted and failed) returns False. The fallback then reaches TeslaAPI, which also skips the away car.
- Policy re-queues every loop and nothing about the skipped VIN is recorded, so arrival's per-VIN apply reaches the car.
- The `_bleLock -> presence._lock` order is the existing one.
- The skip does raise the cost of a wrongly-AWAY plugged-in car (see N1).

## New Breakage in the Fix Diff

- **N1 (Minor). An away fix queued behind a proof in the same snapshot is not dropped.** VehiclePresence.py:252-268.
  - `_dropAwayFixes` filters only `self._observations`, which holds arrivals during the hook. The local `observations` list is not filtered.
  - Probe: `[proof(V), location(V, False)]` in one pass gives arrival then departure, final state AWAY. The departure's remote-only restore replaces the arrival apply under the same key.
  - On a BLE install the TeslaBLE policy-wide apply then skips this plugged-in car until another nomination or contact.
  - It needs a wrong or stale geofence fix, plus a thread busy in a probe when the proof lands. That is the exact situation reconcile exists for, for example a `car_api_charge` start at plug-in calling `update_location`.
  - Why Minor and not Important: the car does not stay AWAY for long.
    - A BLE charge start/stop sends a successful contact, and that sets HOME.
    - A power-start nomination probes the car. Telemetry then judges the car against the moved home and finds it HOME.
    - An HTTP nominate or the next plug-in proof also recovers it.
  - Until one of those happens, the policy limit is not applied and a restore has been queued. If the policy is holding charge off, the wait can last until the scheduled start.
  - Fix (one line): when handling a proof, also drop later `("location", vin, False)` entries for that VIN from the local list.
- **N2 (Minor). The due-time cap keeps the earliest, which evicts the late "has it left" probes during a nomination storm.** VehiclePresence.py:155-158.
  - With the thread running, only future times accumulate. A Gen2 state-00 power-drop/unplug flap (delays 300/1200/2700, ledger Minor 5) fills the 64 slots with the soonest +300 entries and discards the +1200/+2700 ones.
  - When the flap stops, only about 64 s of probes remain. A BLE-only car that then leaves may never collect 2 failed probes, so it stays HOME.
  - The comment "in normal operation neither limit is reached" is not true in that case.
  - Fix: dedupe or round due times, or keep the earliest and the latest.

## Out-of-Scope Observations

- **After a home move, other cars keep their raw `_locationAtHome` computed against the old home.**
  - TeslaAPI.py:1518 recomputes it only for the reconciled car. Presence state masks this for cars it knows.
  - Moving home this way is rare.
- **Stale-GPS reconcile leaves raw False.**
  - Any later away fix for a plugged-in car (API or telemetry) flips presence AWAY, which shows up as a departure and policy-wide BLE skips until the next proof or contact.
  - This existed at the base in a similar form, through probe `update_vehicle_data`.

## Verdict

**Fix round:** all findings addressed, with no new Critical or Important breakage. Two new Minor items, N1 and N2.
