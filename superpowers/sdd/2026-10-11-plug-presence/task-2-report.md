# Task 2 report: tracker core around plug evidence

Status: DONE (with a user-directed design change applied mid-task)
Worktree: wt-plug, branch `presence/3-plug-presence`
Commits (on c66f3a2):
- `b8127c1` Rewrite VehiclePresence around plug evidence (HOME / DEPARTING / presumed). This is the brief as written.
- `9fd8493` VehiclePresence holds presence only: home plus its basis. This is the user-directed change. It is a follow-up commit, not an amend.

## User-directed change (coordinator message, mid-task)

The tracker holds presence only. Per VIN it keeps `home: bool` plus a basis, `"evidence"` or `"presumed"`. A VIN with no entry is home/presumed. There is no DEPARTING state.
- `state(vin)` returns `"home"`, `"presumed"` or `"not_home"`. The constants are `HOME`, `PRESUMED` and `NOT_HOME`, plus `EVIDENCE = "evidence"` for the basis. `DEPARTING` is removed.
- There is a new query, `basis(vin)`, which returns `"evidence"` or `"presumed"`.
- `isHome` is True for HOME or PRESUMED. `isPluggedHome` is True for HOME only, meaning home on evidence. `bleReachable` is unchanged.
- **Every** change from home to not home calls `onDeparting(vin, True)`. That covers a TWC unplug naming the car, a plug edge, a read showing unplugged (including a presumed car's read), and a presumed car found outside the radius without BLE reach. The tracker does not treat edges and reads differently when deciding on handlers. `edge` is still accepted and appears only in the log reason.
- Not home to HOME runs `onArrival(vin, None)`. PRESUMED to HOME runs nothing.
- Test renames: `test_departing_is_never_presumed` became `test_not_home_is_never_presumed`. `test_presumed_read_unplugged_is_not_home_with_no_handler` became `test_presumed_read_unplugged_is_not_home_and_calls_on_departing`; it covers read, edge and `observeTelemetryPlug`, and absorbs `test_presumed_edge_unplug_departs`. `test_unplug_naming_a_home_car_departs` now asserts not home plus exactly one `onDeparting`.

## Implemented (final state)

`lib/TWCManager/VehiclePresence.py`:
- **Kept:** the thread, `start`/`stop`, `nominate`/`_due`/`_collectDue`, `MAX_OBSERVATIONS`/`MAX_DUE_PER_VIN`, `_callSource`, `_runHomeProof`, and the handler runners (`_runDeparting`, `_runArrival`).
- **Removed:** `AWAY`, `UNKNOWN`, `ARRIVING`, `AWAY_AFTER_FAILED_PROBES`, `_failedProbes`, `_dropAwayFixes`, `DEFAULT_SOURCE_ORDER`, `sourceOrder` and `_order`. Setting `config["vehicle"]["presenceSources"]` logs one WARNING.
- **Constants:** `PROBE_INTERVAL = 60`, `STRONG_EVIDENCE_HOLD = 300`, `BLE_REACH_MAX_AGE = 300`.
- **Records (memory only):**
  - `_plug`: vin -> `PlugRecord(pluggedIn, source, at)`.
  - `_inside`: vin -> (bool, t).
  - `_reach`: vin -> (bool, t).
  - Evidence times are stamped when the observation is made and carried in the observation tuple `(kind, key, value, at)`.
- **Observers:**
  - New `observePlugState(vin, pluggedIn, source, edge=False, fastCharger=False)`. Unknown sources are debug-dropped.
  - `observeTelemetryPlug(vin, pluggedIn, edge=True)` delegates to it.
  - `observeContact` records successes, and failures only when `probe=True`.
  - `observeLocation`, `observeProof`, `observeUnplug` and `observePlug` keep the Task-1 signatures.
- **Constructor:** drops `sourceOrder` and adds `twcVins`. The default `twcVins` is the union, over `master.getSlaveTWCs()`, of each slave's `currentVIN` and a real `plugVIN` (not `NON_TESLA`); it returns `set()` on error. The default `bleApplies` is "TeslaBLE loaded and `bleProven`".
- **`runPass`:**
  1. Drain the observations.
  2. Evaluate `twcVins`, `bleApplies` and `pluggedIn` once, without the lock (`pluggedIn` only when the batch has an unplug).
  3. Apply the table in order under the lock. The home-proof hook runs unlocked before its proof is applied, as before.
  4. Nominate "home-by-telemetry" probes after the lock is released, because `nominate` takes the lock.
  5. Probe due VINs. A probe is rate-limited only; `_probe` is a no-op.
  6. Run the handlers without the lock, in order. Each is re-checked first: departing runs only if the car is still not home, arrival only if it is still HOME.
- **Decision table:** implemented as briefed, with the user change above.
  - "Here" means `_inside` True, or `bleReachable`, or the VIN is in `twcVins()`.
  - The carried rule stays: a TWC unplug is ignored, with an INFO log, while live telemetry says the car is plugged in.
  - `unplug(twc, None)` and `plug(twc, …)` are debug-logged no-ops.

Callers:
- `CarApiVehicle.atHome` returns `bool(presence.isHome(VIN))`. It falls back to `_locationAtHome` when there is no presence object, no VIN, or the call raises. The setter is unchanged.
- TeslaBLE's policy-wide skip is `not presence.isHome(vin)`.
- `etc/twcmanager/config.json`: the commented `presenceSources` block is removed.

## Tests

- **Brief tests:** all 21 named tests are present in `tests/unit/test_vehicle_presence.py`, renamed where the user change required. Extra tests cover the hold expiry, twcVins beating a weak plug, a TWC naming the car as "here", records and reach ageing, the default `twcVins`, the default `bleApplies`, the absence of a warning when `presenceSources` is unset, lookups running unlocked, an unplug and a replug in one batch, and VIN-less plug/unplug as no-ops.
- **Kept and adapted:** FakeClock, Recorder, `make` (no `order`), `test_observers_record_only`, `test_handlers_run_without_the_presence_lock`, TestThread, TestDefaults, TestBoundedWithoutThread, TestHomeProof (without the away-fix tests) and TestNominationStorm.
  - TestThread's `test_thread_runs_a_pass_when_nominated` is renamed `..._when_observed`, because a probe is a no-op now.
  - `test_known_vehicles_failure_keeps_observations` replaces the old TestFixRound1 variant.
- **`test_teslaapi_presence.py`:**
  - `test_at_home_reads_is_home` added: PRESUMED gives True, not home after an unplug gives False, and with no presence the raw fix is used.
  - The parametrized state test is rewritten for `isHome`.
  - The policy-gate and ReconcileHomeLocation mocks now mock `isHome`.
  - `test_policy_wide_gate_uses_raw_when_presence_unknown` is renamed `test_policy_wide_gate_applies_to_a_presumed_car`.
- **`test_teslable_presence.py`:** the `TestSkipsAwayVehicles` helper mocks `isHome`. A new real-tracker test checks that cars that are not home (after an unplug, and via discovery) are skipped and that a PRESUMED car is not.

TDD evidence:
- Commit 1:
  - RED: collection error `ImportError: cannot import name 'DEPARTING'`, plus 8 failures in the two channel test files.
  - GREEN: 163 targeted tests pass, and the full suite passes (959).
- Commit 2:
  - RED: 24 targeted failures (missing `basis`, state strings, `onDeparting` expectations).
  - GREEN: 163 targeted tests pass, and the full suite passes (959, 1 warning that was there before).

Black: run on `VehiclePresence.py`, `TeslaAPI.py`, `TeslaBLE.py` and `test_vehicle_presence.py`. `test_teslaapi_presence.py` and `test_teslable_presence.py` were not black-clean before this task, so they were not reformatted; the new hunks are written in black style (checked with `black --diff`).

## Files
- lib/TWCManager/VehiclePresence.py
- lib/TWCManager/Vehicle/TeslaAPI.py
- lib/TWCManager/Vehicle/TeslaBLE.py
- etc/twcmanager/config.json
- tests/unit/test_vehicle_presence.py
- tests/unit/test_teslaapi_presence.py
- tests/unit/test_teslable_presence.py

## Self-review: interpretive calls
- **A weak record never replaces a strong one inside the hold.** `_plug` holds one latest record, and both hold rules read it. Without this rule, a weak write would erase the strong record that the next conflicting weak reading must lose to. Ignored weak evidence is never recorded.
- **`fastCharger=True` writes no record.** As a result, the re-apply row can never fire on a fast-charger plug. One side effect: a stale weak-plugged record from before could outlive a Supercharger visit, which only matters if the unplug in between was also missed.
- **A TWC unplug naming the car records a strong unplugged record in every state.** The transition and its handler only happen from home or presumed.
- **`plugState(True, "twc")` is handled as strong,** the same as the BLE row. The table names only "ble".
- **A weak "plugged in" on a HOME car is recorded,** subject to the overwrite rule. The table has no row for it.
- **The arrival handler is skipped** if the car is no longer HOME by the time the handlers run. This mirrors the carried departing check, and covers a plug and an unplug in the same batch.
- **`twcVins` is a per-pass snapshot** taken before the lock.

## Concerns
- **Every `car.atHome` consumer in TeslaAPI now reads True for a PRESUMED car.** That includes the wake/poll gates, `numCarsAtHome` and `minBatteryLevelAtHome`. This is what the spec intends, but it is the widest behaviour change here. Task 7 narrows the plugged-only uses to `isPluggedHome`.
- **A HOME car leaves only on plug evidence.** A location fix outside the radius or BLE silence never moves it. This is by design; a missed unplug edge leaves the car HOME until discovery (Task 6).
- **Because of the user change, `onDeparting` now also runs for a PRESUMED car found unplugged or outside the radius.** The carried `departingHandler` no-ops when nothing is held. When a limit *is* held, it queues a `localOnly` BLE restore, which may fail for a car that is out of range. Task 5's reconciler owns this, and Task 5's brief, which assumed a DEPARTING state and a "held-limit → DEPARTING" override, needs re-reading against the presence-only model.
- **The ledger's ruling on the T2/T5 conflict is moot under the user change.** The old ruling was that "PRESUMED read unplugged → NOT_HOME" with no handler would be overridden in Task 5.
