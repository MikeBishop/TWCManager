# Pre-flight conflict scan — Phase 3 (desired state and reconcilers)

Plan: `.superpowers/plans/2026-10-15-vehicle-model-phase3-reconcilers.md` (11 tasks)
Spec (binding): `.superpowers/specs/2026-10-13-vehicle-model-design.md`
User rulings: `sdd/2026-10-15-vehicle-model-phase3-reconcilers/progress.md` (Q1 disruptive stop waits 60 s for BLE only when BLE is set up; per-car shared channel failure; BLE ping before assuming BLE is still down)
Base: `vehicle-model/phase2` = 6a6c14e (read-only copy exported to `scratchpad/preflight3/base`). Port source: `presence/2-charge-limits`.

## What was checked, and how

- **Base suite** in the scratch copy: `1326 passed, 1 xfailed` (the plan cites 1320 at 8959380).
- **Fixtures run against the base** (as scratch pytest probes, since deleted):
  - `test_gen2twc_provider.make()`: `startCarsCharging(VIN)` in mode 1 raises `AttributeError: 'NoneType' object has no attribute 'clearOverride'`. `stopTimeout` starts at `datetime.max`. The registry passes its `_clock` to each Vehicle it creates. `beginPlugSession` works.
  - `Policy(m).enforcePolicy(...)` twice on that master: passes, so the Task 7 Policy test fixture is viable.
  - `api_with_registry` + `fleet_token`: the Fleet slot is usable for commands, `getVehicleByVIN` resolves, and the retry wait is 0. **After `reportScopeRefused("command", refused=True)`, `usable("command")` is still True** (Finding 27).
  - Owner 412 on `loadVehicleList`: returns False and leaves the slot unusable for reads. The fixture works.
  - `make_ha()`: one provider; `_session` is a MagicMock. `_call_service` catches Timeout and HTTPError itself and returns False.
  - `test_teslable_pairing_status.make()`: one provider. `KEY_NOT_PAIRED_TEXT` does not exist (the constant is `KEY_REFUSED_TEXT`).
- **Every file:line and symbol** the plan names was read at base, plus `VehiclePriority`, `VehicleCommandQueue`, `TWCSlave.send_master_heartbeat`, `Gen2TWC`, `VehicleEndpoints`, `Sources.py`, `TeslaTokenSlot` and `HomeAssistant._call_service`. The port source `ChargeLimitRules.py` and its test table were read from `presence/2-charge-limits`.
- **Each mandated test was walked by hand** against the plan's Interfaces text, at the clock values the test sets.
- **User rulings, checked one by one:**
  - Shared per-car channel health: F3, F33.
  - Stale-failure BLE probe: F3, F24, F31.
  - 60 s disruptive-stop wait only when BLE is set up: Decision 7 matches. Breakages around it: F10, F11, F14.
- **Forward dependencies:**
  - Real breaks: F1 (T3 deletes what T10 still needs) and F49 (T7–T9 window).
  - Checked and fine: T3's lazy `satisfied` placeholder and the `beforeWrite` fallback, apart from the Mock problem (F17); the T1 helpers defining command methods before `Provider` has them; T4's new Gen2 START and the billed-stop suppression being visible to the façade walk (harmless).
- **Cost and wiring sweep:** F4, F6, F7, F8, F10, F11, F34, F37 (and F33 on wording).

## 1. Pair table (tasks sharing a file or an interface)

| Pair | Producer → consumer (exact names) | Match? |
|---|---|---|
| T1→T3 | `Attempt(key, aspect, capability, value, provider, wake, maxAge, restore, since)`, `Outcome`, `FIELD_FOR`, `ScriptedProvider`, `make_order` → `Lane.submit`, `runAttempt`, `debugCommand`, test_lanes | **No.** `make_order` returns a plain `Mock` master, so `master.reconciler.beforeWrite()` returns a Mock and the `value, early = …` unpack raises TypeError (F17). `debugCommand`'s Attempt omits the required `since` field (F19). |
| T1→T6 | `DesiredStore.set/get/adopt/record/health/state/settled/endSession/onChange`, `ChannelHealth`, `ControlState.probeInFlight` → `VehicleReconciler.plan/report/pass_` | **No.** `adopt()` receives `chargingState` strings ("Charging"/"Stopped") but its CHARGING rule is written for `True` (F25). `settled()` requires strictly newer, which never holds under the tests' fixed clock (F21). The default clocks mix `time.time` and `time.monotonic` (F5). |
| T1→T7 | `set(..., decision=)`, `clear` → `applyPolicyLimit`/`onArrival`/`onDeparture` | Yes |
| T1→T8 | `release`, `bounds().wantsCharge`, `endSession` → `cancelStopCarsCharging`, `VehicleEndpoint.wantsToCharge`, `pass_` unplug detection | **No.** `release` depends on `settled` (F21). `endSession` fires only when `twcVin` goes from set to None (F36). |
| T1→T9 | `Desired.lift`, `bounds.lifted/maxAmps` → `ChargingPoint.setTargetPower`, `TWCSlave.vehicleRateRaised` | Yes |
| T2→T3 | `Vehicle.read(field, maxAge, allowWake, sources=[ReadSource])`, `believed` → `runAttempt` | Yes (`sources` is a list of ReadSource objects with `.provider`) |
| T2→T6/T8 | `believed(field)` → `satisfied`, adoption, the "excluded sources are ignored for satisfaction" rule | **No.** `believed` is unfiltered, but T6/T8 need TWC-sourced observations left out (F23). |
| T2→T6/T7 | `HeldLimits.get/set/holding` → `beforeWrite/afterWrite`, adoption save, `Targets` | Yes |
| T2→T5 (TeslaAPI.py) | `_bind` → `heldLimits.adoptLegacyId`; T5 adds `command()` beside it | No conflict. The legacy numeric-ID store is lossy (F32). |
| T2→T10 | Wrappers `get/save/removeNormalChargeLimit` deleted; `heldLimitText` | Yes |
| T3→T4/T5 | `Provider.setChargeLimit/startCharging/stopCharging/setAmps/wake/probe -> Outcome`, `PROBE`, `commandMethod` | Signatures match. Outcome is truthy, which breaks the façade `dispatch` while it is still live (F1). |
| T3→T6 | `runAttempt` ↔ `satisfied`, `beforeWrite`, `afterWrite`, `report`; `Lanes.allows`, `setReport` | **No.** `report` handles `aspect is None` as a one-shot before it reaches the probe branch (F24). Dropped or coalesced entries never report (F12). |
| T3→T8 | `Lanes.cancel(key, aspect)` → `cancelStopCarsCharging` | **No.** It cancels starts too, and a cancelled entry never reports, so `inFlight` stays set (F12). |
| T3→T10 | T3 deletes `ProviderOrder.dispatch`; `VehiclePriority.setAmps` (VehiclePriority.py:248) uses it until T10 | **No** (F1) |
| T3→T7 | `Lanes.start/drain` → TWCManager.py :845 / :2055 | Yes |
| T4→T6 | `TeslaBLE.probe` → PROBE attempts; `commandOutcome` REFUSED → EXCLUDING | Interfaces match. Side effects are wrong (F31). |
| T4→T8 | Gen2 `START_CHARGING`/`STOP_CHARGING` and the mode-2/3 billed-stop suppression → stop/start routing | **No.** Gen2 START wins under mode 2 even after a BLE stop (F14). The mode-3 stop runs off the serial thread (F13). |
| T5→T6 | `wakeDue`/`wakeOutcome` → `Attempt.wake` | **No.** No free online check before a wake, and restores wake (F6). |
| T6→T7 | Reconciler ↔ the `onDeparture` restore desire | **No.** A restore the rules settle without sending is re-planned forever (F4). |
| T6→T8 | CHARGING aspect: `satisfied`, `allowWake`, `LIMIT_THEN_START_GAP`, lane wake-first | **No.** The tests ignore the wake (F26) and the start gap (F28). |
| T6→T9 | `FIELD_FOR[AMPS] = "availableCurrent"` → lift logic and adoption | **No.** The field is the charger pilot current (F7). |
| T7→T8 | `targetsFor(master, vin)` → `start/stop/cancelStopCarsCharging` | **No.** `targetsFor(None)` leaves out anonymous vehicles, and the heartbeat passes `currentVIN` "" (F10). |
| T8↔T9 (TWCSlave.py, ChargingPoint.py, VehicleEndpoint.py) | T8 edits the stop/start lines; T9 makes `_queueChargeRate` write desired AMPS while `ChargingPoint.setTargetPower` also writes AMPS | **No.** Two writers of one aspect (F8). |
| T9→T10 | `VehicleEndpoint` queue, `REFRESH_SECONDS` and `targetAmps` removed | Yes |
| T6/T5→T11 | Row 4 sample: `Clock c` in the reconciler, but TeslaAPI's real-time `wakeDue` | **No** (F38) |
| T7↔T10 (TWCManager.py) | T7 changes checkArrival/checkDeparture; T10 changes checkCharge and the module list | Yes |

## 2. Per-task table

| Task | Self-consistent? | Notes |
|---|---|---|
| 1 Outcome + DesiredStore | Mostly | Tests pass as specified. `onChange` callback signature `(key, aspect)` is implied only by the test. `settled` strictness (F21) and `adopt` typing (F25) bite later tasks. |
| 2 believed + HeldLimits | Mostly | Tests consistent. Unresolved numeric-ID held limits are lost after the migration saves (F32). Wrappers called with numeric IDs during T2–T6. `heldLimitText` `None → —` changes today's "(restored)" text (L). |
| 3 Lanes | **No** | Deletes `dispatch` "nothing else called them" while VehiclePriority does (F1). `orderKey` does not exist. Mock master breaks `beforeWrite` (F17). Drain test races thread start (F18). `debugCommand` targets the TWC and omits `since` (F19). Dropped or cancelled entries never report (F12). `Provider.readSource` does not exist (L). |
| 4 Local outcomes | Mostly | Gen2 "mode 1" outcome appears only in the test (L). Claim dropped inside the pairing window; probe marks the key paired (F31). Gen2 START and mode-3 stop issues surface in T8 (F13, F14). All test line refs are wrong (L). |
| 5 Cloud outcomes | **No** | 403 test fails, confirmed (F27). HA `serviceOutcome` cannot see Timeout through `_call_service` (F29). Global `time.sleep = Mock()` (F30). `wakeOutcome` has no online check (F6). Test line refs wrong (L). |
| 6 Rules + reconciler | **No** | Adoption rule (F2). BLE never retried (F3). Busy loop (F4). Clocks (F5). Restore wakes (F6). `test_restore_with_nothing_held…` and `test_limit_is_sent_once` fail (F20, F21). Port diverges from the presence/2 table (F22). Probe report ordering (F24). "Once per desired change" contradiction (F33). |
| 7 Limit wiring | Mostly | `test_departure…` needs ScriptedProvider BLE not ready for an unclaimed VIN, while T6 needs it ready (F16). Observed-tier cars get desired state (L). |
| 8 Charging aspect | **No** | `clearOverride` AttributeError, confirmed (F9). Non-Tesla stop never reached (F10). Disruptive stop never re-asserted (F11). Cancel (F12). Serial write off-thread (F13). Mode-2 start (F14). Tests ignore wake-first (F26) and the 5 s gap (F28). Bounds never cleared without `twcVin` (F36). Wiring stops ignored after a user start (F37). |
| 9 Amps aspect | **No** | Pilot-current field (F7). Two AMPS writers, and TWC-only points sent to max under mode 2 (F8). BLE AMPS tests ignore wake-first (F26). Paid read before every Fleet rate (F34). |
| 10 Retire legacy | Mostly | Grep test also hits comments not in the file list (L). `checkCharge` ignores api_only (L). |
| 11 Parity + live | Mostly | Row-4 sample mixes clocks (F38). Row 1 "DEBUG only" vs step 9 INFO (L). The table's parity claims for rows 4 and 11 are contradicted by F6 and F34. |

## 3. Findings

Severity: **High** = a mandated behaviour or test that breaks the suite, the spec, a user ruling, the wiring rule or cost; **Medium** = a mandated test or interface that fails or conflicts, fixable locally; **Low** = references, wording, cosmetics.

### High

**F1 — Task 3 deletes `ProviderOrder.dispatch`, which the live façade still uses.**
Plan text: "`dispatch` and `orderKey` are deleted; nothing else called them (M3)."
At base, `VehiclePriority.setAmps` (VehiclePriority.py:248) calls `self.order.dispatch`. Its callers:
- `VehicleEndpoint.setTargetPower` queues `{"cmd":"setAmps"}`.
- `VehicleCommandQueue._setAmps` runs it.
- `tests/unit/test_vehicle_priority.py:88,137-138` assert on it.

Deleting it in T3 fails the full suite (T3 Step 4 does not run those files) and breaks rate commands until T9/T10. `orderKey` does not exist at base. Separately, once T4/T5 make provider methods return `Outcome` (a non-empty tuple, so always truthy), `dispatch`'s `if result and result != "error"` counts `UNREACHABLE` and `ERROR` as success.
Ruling: keep `dispatch` until T10 (T10's grep already covers `def dispatch`). In T4, make `dispatch` treat `isOutcome(r) and r.kind in SETTLED` as success. Drop the `orderKey` wording.

**F2 — Task 6 adoption compares the read with *desired*, not with our write, and ignores when the desire was set.**
Plan text, step 3: "`latest.at > write.at` … and `not satisfied(aspect, d.value, latest)` → adopt."
A read that merely confirms our own write (newer than the write, equal to it) is adopted as soon as desired changes:
- Every later policy limit, restore or start is "adopted" back to the old value and never sent.
- `test_app_set_limit_is_adopted_and_becomes_outside` fails at its last line: the decision is re-adopted and `pass_()` returns 0, not 1.
- `test_no_wake_to_lower_wake_to_raise` fails: the confirming 50 is adopted over the restore to 90.

Spec: adopt "a vehicle read newer than our last write [that] confirms a different value."
Ruling: adopt only when `latest.at > max(write.at, d.at)` and `latest` differs from the **write** (`not satisfied(aspect, write.value, latest)`), using the source-filtered latest (F23).

**F3 — A failing free provider is never retried (Task 6, step 8).**
Plan text: "a failing free `p` is skipped." The only recovery is the probe, which runs only "before the first paid/disruptive pick", or a `bleReach` True from a scan the Vehicles page triggers.
- On BLE-only and Gen2+BLE installs (no paid candidate) one BLE timeout disables BLE for that car on every aspect. The car is then backed off forever (`test_pass_is_bounded…` depends on exactly this).
- A mode-1 stop is never re-sent, so the car keeps drawing: a sustained overshoot.
- This contradicts the user ruling ("do a BLE ping before assuming it's still down"), the spec's re-assert rule, and the plan's own Review Focus 2 ("three BLE failures and the 60 s retry").

Ruling: a failing free provider stays a candidate at `RETRY[aspect]` cadence (bounded by `attempts()` and backoff). The stale-failure probe also runs when no paid candidate exists. Shared health governs only *paid eligibility*.
Precedence, so the ruling keeps `test_fleet_waits_for_ble_to_time_out_and_is_sent_once` true: once the channel is paid-eligible for an aspect, the paid pick (probe first if stale) takes that aspect's one in-flight slot. The free retry continues only on passes where no paid attempt is due.

**F4 — A rules-settled attempt busy-loops (Tasks 6 and 7).**
Plan text: `beforeWrite` → "`decision.settled` → `(None, Outcome(SATISFIED, …))`"; `report` → "`SETTLED` → `rec.reset()`".
When the rules settle without sending ("set by hand to N%; nothing to restore"; "nothing to restore"), desired ≠ believed still holds. With no own-write stamp in memory (for example a hold from before a restart), adoption cannot fire either. `reset()` sets `tried = 0`, so the next pass re-plans at once, and `report → wake()` re-runs the pass immediately.
Result: a CPU-bound loop that does a paid Fleet `vehicle_data` every time the 300 s `maxAge` lapses, and a forced `maxAge 0` read on the first lap. `onDeparture`'s restore desire is never cleared (`applyPolicyLimit` touches present cars only), so the loop lasts until the desire changes.
Ruling: a rules-settled outcome must reconcile desired. For a restore, `desired.clear` (or adopt `current`). For an apply, adopt the read. The lane must not stamp on early returns (it does not today; keep it so).

**F5 — The mandated default clocks mix two time domains (Tasks 1, 3, 6, 7).**
Plan text: `DesiredStore(clock=time.time)`, `Lane/Lanes(clock=time.monotonic)`, `VehicleReconciler(clock=time.monotonic)`; the registry's write stamps, observations and `bleReach.at` use `time.time`. T7 builds all three with defaults.
In production:
- Step 11's "within `LIMIT_THEN_START_GAP` of a chargeLimit own write" compares monotonic `now` with an epoch `write.at`. The difference is hugely negative, so every start is blocked forever after any limit write.
- `settled()` compares a monotonic `settledAt` with an epoch `d.at`, so it never holds and `release()` drops delivered stops.
- `bleReach` folding writes epoch times into `failingSince`, which breaks the paid window and the probe window.

The tests share one `Clock`, so none of this is caught.
Ruling: one domain. Use the registry clock (`time.time`) for DesiredStore, Lanes and the reconciler; keep `monotonic` only for the lane's own rate-limit windows.

**F6 — Cost: new paid Fleet wakes (Tasks 5 and 6).**
Plan text: `wakeOutcome` → "not due → … ; posts `wake_up`"; `allowWake(CHARGE_LIMIT)` → "a raise, including a restore that raises".
- (a) Base `car_api_available` checks `vehicle.ready()` (free online check) before every wake (TeslaAPI.py:517, :544). `wakeOutcome` does not, so every Fleet raise or start on an online car pays $0.02.
- (b) Base TeslaAPI departure restores never set `needToWake` (`limit == -1`). The plan wakes for every restore that raises. That covers every BLE+Fleet departure (BLE out of range → 300 s → Fleet wake) and a vanished car once per backoff round (hourly, about $14/month per car).

Spec: "a held limit on a car that vanished, backs off to hourly, never wakes"; cascades "prefer free operations".
Ruling: `wakeOutcome` checks free online state first and returns `SATISFIED` "online" without posting. Restore attempts carry `wake=False` on billed providers (BLE may still wake locally).

**F7 — The AMPS aspect reads the wrong field (Tasks 6 and 9).**
Plan text: `FIELD_FOR = {…, AMPS: "availableCurrent"}`; adoption "a vehicle-sourced `availableCurrent` newer than our write and lower than it → `bounds.maxAmps`"; mode-3 lift "when … `believed("availableCurrent")` … is below `amps`."
`availableCurrent` is `charger_pilot_current` (TeslaAPI.py:2610, TeslaMateVehicle.py:71, TeslaBLE.py:1118): the EVSE's offer, not the car's own amps setting.
- On a TWC, after a lift to 32 the next vehicle read reports the TWC's offer (say 8). That is newer and lower, so it is adopted as a user bound, and the car is capped at whatever the TWC offered for the whole plug session.
- On a UMC with a Fleet-only car, the pilot (say 32) never equals the set rate, so every new vehicle read re-asserts a paid `set_charging_amps`.
- Mode-3 lifts fire whenever the TWC offer rises.

Ruling: add a registry field for the car's request (`charge_current_request` from Fleet and BLE, `ChargeCurrentRequest` from Fleet Telemetry) and use it for AMPS. Until a source reports it, AMPS is satisfied by the own-write stamp alone and never adopts.

**F8 — Task 9's layered rule breaks mode 2 and 3 on TWC-only points and creates two AMPS writers.**
Plan text: mode 2 → "`local.setTargetPower(local.maxPower)`; vehicle members `desired.set(…)`". `_queueChargeRate` → `desired.set(self.vehicleKey, AMPS, int(amps), "heartbeat")`. The heartbeat branch is kept (Decision 11).
- `VehicleEndpoints` is registered only with TeslaAPI (its docstring), so BLE-only and Gen2 points have no vehicle member. Mode 2 sets the TWC to max. The heartbeat's mode-2 branch (TWCSlave.py:866-895) then sees `_evseTargetAmps` = max and sets the car's amps to max, so the car draws the TWC maximum whatever the target: a sustained overshoot.
- With a vehicle member, the heartbeat writes AMPS = max ("heartbeat") while the point writes AMPS = target ("distributor"). Desired flips every cycle, and each flip is an attempt: paid on Fleet, with the car alternately at max.
- In mode 3 below the floor the heartbeat sees 6 A, takes the TWC branch and lifts the car to `wiringMaxAmps`, against the point's 4 A.

Ruling: apply the layered rule only when the point has a vehicle member; otherwise keep the Phase 2 whole-target-to-TWC path. When a point has a vehicle member, the heartbeat's mode-2/3 and raise branches must not write AMPS (the point owns the aspect).

**F9 — Task 8 tests error on the mandated `clearOverride` (confirmed at base).**
Plan text: `startCarsCharging` "keeps `self.getModuleByName("Policy").clearOverride()` under `chargeStopMode` 1 as today."
The `setup` → `make()` fixture stubs `getModuleByName` to return None, and `make()` then `startCarsCharging(VIN)` raises AttributeError. Every T8 test that calls `startCarsCharging` in mode 1 errors (eight tests, including the probe and shared-health tests).
Ruling: guard it (`policy = self.getModuleByName("Policy"); if policy: policy.clearOverride()`), the same for `overrideLimit`, or have the fixture return a Mock Policy.

**F10 — Non-Tesla and VIN-less cars are never stopped under mode 2/3 (Task 8).**
Plan text: `stopCarsCharging(vin)` → `for v in targetsFor(self, vin)`; `targetsFor(None)` → `presentVehicles` = "non-anonymous registry vehicles".
The real caller, TWCSlave.py:574, passes `self.currentVIN`, which is "" for a non-Tesla car, so `targetsFor(None)` yields no anonymous vehicle and nothing is set. Today mode 2/3 stops the bus unconditionally. The plan's test calls `stopCarsCharging(anon.key)` directly, which masks this. Pure Gen2 with mode 2/3 regresses (Global Constraint "No regression for pure-Gen2 … `chargeStopMode` (1/2/3)"), and the car draws its minimum while the budget says 0: sustained.
Ruling: the heartbeat passes `self.vehicleKey` to stop, start and cancel. `targetsFor` resolves anonymous keys.

**F11 — A disruptive stop is "satisfied" by our own stamp and never re-asserted (Tasks 3, 6 and 8).**
The lane stamps `chargingState="Stopped"` on DONE, and TWC observations are excluded from satisfaction. Mode 2 resumes on its own after 60 s (`respondToSlavesExpiry`).
- For a non-Tesla car (no vehicle reads), believed stays "Stopped" forever, so the heartbeat's repeated `stopCarsCharging` (desired unchanged) never re-stops it.
- For a Tesla car, a telemetry "Charging" after the auto-resume is newer than our write and is adopted as "user started it", so every further stop is ignored for the session.

Both are sustained overshoot.
Ruling: a disruptive stop's stamp expires with `respondToSlavesExpiry` (or is not stamped). For vehicles with no vehicle read path, TWC current may be used to satisfy a desired-False, but never to adopt. A resume our own disruptive stop caused is never adopted.

**F12 — Cancelled, dropped and coalesced lane entries never report, so `inFlight` sticks (Tasks 3 and 8).**
Plan text: `cancelStopCarsCharging` → "`desired.release(…)` per target plus `lanes.cancel(v.key, CHARGING)`"; `Lane.submit` "when full the oldest non-stop entry is dropped"; "replaces a pending entry with the same `(key, aspect)`".
- `lanes.cancel` removes *any* pending CHARGING attempt, including starts.
- No cancelled, dropped or replaced entry reports, so `rec.inFlight` stays set and step 1 never plans that (car, aspect) again until `endSession`.
- TWCSlave.py:1069 calls `cancelStopCarsCharging()` (all present cars) on every heartbeat with an offer above 0, so on a threaded BLE lane this hits routinely.
- A probe and a debug one-shot share the key `(vin, None)` and replace each other, so `probeInFlight` sticks.

Ruling: `cancel` removes only `STOP_CHARGING` entries. Every removed entry is reported (`Outcome(ERROR, "cancelled"/"dropped")`, not counted against health). Probes and one-shots get distinct coalescing keys.

**F13 — The mode-3 stop writes to RS-485 from the reconciler thread (Tasks 4 and 8).**
Plan text: `Gen2TWCProvider.stopCharging` mode 3 → `master.sendStopCommand(slave.TWCID)`; the `"local"` lane "is always inline". The reconciler's `pass_` submits, so the serial write runs on the reconciler thread concurrently with the serial loop, and `Interface/RS485.send` has no lock.
This violates the spec's threading table ("RS-485 loop: Gen2 protocol only") and the Gen2 provider rule ("its attempt is publishing a target the serial loop sends").
Ruling: the Gen2 stop publishes a per-slave stop request that `send_master_heartbeat` sends on the serial thread.

**F14 — The mode-2 "start" does not undo a BLE stop (Tasks 4 and 8, Decision 22 vs the Q1 ruling).**
Under Q1 a BLE-ready car in mode 2 is stopped by BLE. Gen2 `START_CHARGING` (LOCAL, rank 0) is first in the START order, sets `respondToSlaves = 1`, returns DONE and is stamped "Charging". The car, stopped by a vehicle command, is never restarted, and the heartbeat's repeated starts leave desired unchanged.
Ruling: a start goes through the provider that delivered the last stop. Concretely: Gen2 is ready for START only when the last delivered stop was the Gen2 disruptive one (record it on the CHARGING record); otherwise use the vehicle command.

### Medium

**F15 — The pure-Gen2 and observed-tier vehicles path logs at INFO.** Plan text: step 9 "INFO once (`no provider could deliver…`)"; Task 11 row 1: "no backoff log spam (DEBUG only)". Spec: "Only managed vehicles get vehicle-command desired state". Ruling: zero-candidate rounds log at DEBUG, and `applyPolicyLimit`/`targetsFor` skip vehicles with no command-capable claim (anonymous keys still get CHARGING for local providers).

**F16 — `ScriptedProvider.ready` is unspecified and the tests need contradictory answers.**
- T6 and T8 need BLE ready for an unclaimed VIN.
- T7 `test_departure_restores…` needs BLE *not* ready for unclaimed VIN2 ("BLE not ready for a car it holds no claim on").
- T8 `test_non_tesla…` needs BLE not ready for an anonymous key.

Ruling: `ready = bool(vehicle.vin)` plus an optional `readyFor` predicate. T7's test sets `ble.ready = lambda v, c: v.vin != VIN2` explicitly.

**F17 — `make_order` builds a Mock master, so `runAttempt` raises in T3's tests.** `runAttempt` says "a missing `reconciler` attribute means `(attempt.value, None)`", but a `Mock` has every attribute, and `value, early = Mock()` raises TypeError. The exception becomes ERROR, so every test_lanes test that expects a command call fails. Ruling: `make_order` deletes `m.reconciler` (or uses `Mock(spec=[...])`), and `runAttempt` checks `isinstance(..., VehicleReconciler)`.

**F18 — `test_drain_runs_pending_stops_only` races.** `m.lanes.start(); m.lanes.drain(5)` lets the lane thread pop the stop *and* the limit before drain marks stopping. Ruling: drain is callable on an unstarted lane (it runs pending stops on the caller), and the test does not call `start()`.

**F19 — `debugCommand` changes behaviour.** Plan text: "`provider=<first of candidates(vehicle, cap, amps, localRule=False)>`".
- The first candidate for `setChargeRate` on a TWC car is Gen2TWC (module-less), so the debug page writes a TWC target from the HTTP thread. That regresses the M1 test `test_debug_set_charge_rate_reaches_fleet_past_a_covering_twc` and `dispatch`'s "never write a TWC target".
- No fall-through to the next provider.
- The `Attempt` omits `since`.

Ruling: skip `module is None` providers, set `since`, and accept (and document) one provider per debug command.

**F20 — `test_restore_with_nothing_held_settles_and_unknown_limit_on_cloud_sends_nothing` cannot pass.** `plan()` has no plan-time "nothing to restore" rule, so `pass_()` returns 1. In `decideChargeLimit`, the "current unknown and not `sendWhenUnknown`" rule comes first, giving UNREACHABLE, not settled. Ruling: plan step 4b — a CHARGE_LIMIT restore with no held limit (`heldLimits.get(vin)` None or `.held` None) is settled and its desire cleared without an attempt.

**F21 — `settled()` requires strictly newer.** Plan text: "record's `settledAt` is newer than the desired's `at`". Under a fixed Clock both are 1000, so `test_limit_is_sent_once_and_recorded_as_held` (`settled` assert) and `test_cancel_releases_an_undelivered_stop_only` (release returns 1, not 0) fail. Ruling: `>=`.

**F22 — The rules port diverges from presence/2's table.** Plan text: "`restore and (held is None or held.held is None)` → settled, 'nothing to restore'". presence/2 settles only when nothing is saved. For a saved but not-held entry it goes on to `saveNow=(current,-1)`, or sends `outside` when the current limit is unknown over BLE. The ported row "restore with nothing held (-1)" (expects `saveNow`) fails. Ruling: port the rules verbatim (`held is None` ⇔ `not hasSaved`; `held.held is None` ⇔ `lastApplied == -1`) and keep the table unchanged. F20's plan-time settle covers the "nothing to restore" case before the lane.

**F23 — `believed()` must leave out excluded sources.** Plan text: "a `chargingState` observation from a source in `VEHICLE_SOURCES_EXCLUDED` is ignored for adoption and satisfaction alike", but step 2 uses the unfiltered `vehicle.believed(field)`. Review Focus 4's `test_twc_current_alone_never_adopts_charging` then plans a BLE stop. Ruling: `believed(field, exclude=…)` (or a reconciler helper over `reportedBy`).

**F24 — The probe is handled after the one-shot branch in `report`.** Plan text: "one-shot (`aspect is None`) → INFO only; otherwise …; A probe outcome (`capability == PROBE`) clears `state.probeInFlight`". A probe's aspect is None, so a literal implementation never clears `probeInFlight`, and every aspect for that car waits forever. Ruling: test `capability == PROBE` first.

**F25 — `adopt()` typing for CHARGING.** `adopt(vehicle, aspect, latest.value)` passes "Charging"/"Stopped", but the store's rule reads "`CHARGING` True → `bounds.wantsCharge`". Adopting "Stopped" (the user stopped the car in the app) is undefined. Ruling: map through `satisfied` (`"Charging"`-like → True). Define the user-stop case: clear desired True for the session (spec: fast aspect → bound).

**F26 — Task 8/9 tests ignore the lane's wake-first.**
- Fleet start: `test_shared_channel_health_*` (2 tests) and `test_a_free_success_puts_ble_first_again`. In the last, BLE's *wake* consumes the scripted UNREACHABLE.
- `test_paid_calls_never_exceed_desired_changes` counts the wakes and exceeds `changes`.
- BLE AMPS: `test_mode_1_…`, `test_mode_3_…` expect `[("setAmps",…)]`, but local AMPS attempts wake.

Ruling: filter `x[0] != "wake"` or assert the wake explicitly. Decide whether BLE wakes before every rate change (today it does, and proceeds if the wake fails).

**F27 — A 403 on a command does not make the slot unusable (confirmed).** `reportScopeRefused(…, refused=True)` only logs, so `test_fleet_401_retires_the_slot_and_403_refuses_the_scope` fails, and Fleet is re-tried after every `newRound`. Ruling: `TeslaTokenSlot` records refused purposes (cleared by `setTokens`/`clear`), and `usable()` honours them.

**F28 — The test that a later aspect goes paid at once contradicts the start gap.** `test_shared_channel_health_lets_a_later_aspect_go_paid_at_once` starts 1 s after the Fleet limit write, and step 11 blocks it for `LIMIT_THEN_START_GAP` (5 s). Ruling: the test advances `LIMIT_THEN_START_GAP + 1`.

**F29 — HA `serviceOutcome` cannot classify through `_call_service`.** `_call_service` (HomeAssistant.py:526) catches Timeout and HTTPError and returns False (and logs `e.response.text[:200]`, against the logging constraint). The test needs both the mocked `_call_service` path and the Timeout→UNREACHABLE path. Ruling: refactor to `_post_service(...) -> Outcome`; `_call_service` wraps it (`kind == DONE`), and the response-body log goes.

**F30 — `test_low_amps_are_sent_twice_and_counted` does `import time; time.sleep = Mock()`.** That replaces the stdlib sleep for the rest of the session, which affects threaded lane, drain and sigterm tests. Ruling: `monkeypatch.setattr(TeslaAPI_module.time, "sleep", …)`.

**F31 — BLE probe and refusal side effects.**
- (a) `commandOutcome` "drops [the claim] if it does" after `_keyRefusal.refused`, including inside `PAIRING_WINDOW`, where `_noteBleRefusal` deliberately keeps it.
- (b) The probe goes through `_sendCommand_internal`, which calls `_noteBleProof` on success. `body-controller-state` is answered without an authenticated session, so an unproven key becomes "paired" and the car "managed".

Ruling: no claim drop in the pairing window; the probe passes a flag that skips `_noteBleProof`.

**F32 — Legacy numeric-ID held limits are lost.** `load()` deletes `chargeLimits`, writes `heldLimits` and saves, and ID-keyed entries live only in `_legacyById` (memory). If TeslaAPI does not bind the car in that run (token expired, offline), Fleet/Owner installs (the TeslaAPI path keys everything by ID) lose their held limits: spec anti-goal "Losing a held outside limit". Ruling: persist unresolved IDs (`heldLimits["id:12345"]`) until adopted. The interim wrappers resolve numeric IDs through `CarApiVehicle`.

**F33 — "A paid attempt is sent at most once per desired change" vs the retry rules.** Fleet `attempts()` = 2 per round plus unbounded backoff rounds; `test_fleet_only_car_goes_at_once…` expects 3 sends. Ruling: reword the constraint to "at most `attempts()` per round, rounds backing off 600→3600 s". Restores never wake (F6).

**F34 — Cost: AMPS read-before-write adds a paid read.** Every Fleet `setAmps` attempt with `availableCurrent` older than 300 s first does a Fleet `vehicle_data` ($0.002). Today `setChargeRate` reads nothing, so row 11's "2 → 2" claim fails. Ruling: AMPS attempts carry `maxAge=None` (stamp-based), or read-before-write uses only free sources.

**F35 — The restore's forced live read does not force a read.** Plan text: `maxAge = 0 if needsLiveRead(...)`. With a healthy TeslaMate feed, `Vehicle.age()` is 0 (the liveness rule), so `read(…, 0)` returns the telemetry value without a cascade, and the 09:17 carry is not closed. Ruling: add `read(…, force=True)` that skips report-on-change sources.

**F36 — Plug-session end comes only from `twcVin`.** Cars on VIN-less TWCs, UMCs or Gen3 never have `twcVin`, so `wantsCharge`, `maxAmps` and `lifted` persist until restart (spec: "Bounds clear on unplug"). Ruling: also end the session on a `pluggedIn` False observation and on the TWC slave's session end for its `vehicleKey`.

**F37 — A user-start bound overrides wiring stops.** `DesiredStore.set` ignores *every* CHARGING False under `wantsCharge`, including the distributor's stop for a point that cannot get `minAmpsToOffer()` on a shared wiring limit, giving sustained overshoot. Ruling: the bound admits the car to allocation (spec), and a stop forced by a configured wiring or controller limit is still delivered.

**F38 — Task 11 row-4 sample cannot pass as written.** The reconciler runs on `Clock c`, but `TeslaAPI.wakeDue`'s hold uses `time.time()`, so `c.t += 1801` does not release the hold and the second `wake_up` never happens. The first-pass `vehicle_data: 1` also depends on the observation being stale. Ruling: inject the clock into `wakeDue`/`wakeOutcome` (`now=`) from the attempt, or patch time in the parity helpers.

### Low

**F39 — Line references are off at base 6a6c14e.**
- TWCMaster: `getNormalChargeLimit` is at 975, `save` 1642, `remove` 1590, `start` 2053, `stop` 2066, `queue_vehicle_command` 1375, `_resolveVehicleCommandModule` 1380.
- `Vehicle.read` is at 138-152, not 115-131.
- ChargingPoint is +1.
- `apply_charge_limit` is at 2660.
- Every test-file line ref names lines past the end of the file: `test_teslable_provider.py:582` (79 lines, really :41-43), `test_gen3twc_provider.py:527` (181, really :97-98), `test_teslaapi_providers.py:661` (231, really :84-89), `test_provider_registration.py:837/849` (170, really :43/:54), `test_charging_points.py:1150` (249, the test is at :36), `test_vehicle_endpoint.py:1053` (133, :55), `test_gen2twc_provider.py:380` (178, :161-178).

Ruling: implementers locate the tests by name.

**F40 — The suite baseline is 1326 passed + 1 xfailed at 6a6c14e**, not 1320. Record 1326.

**F41 — `Provider.readSource` does not exist** (Task 3: "`readSource` keeps its Phase 2 meaning and is now used"); read sources carry `.provider`. Drop the sentence. `orderKey` does not exist (F1).

**F42 — `KEY_NOT_PAIRED_TEXT` is a new alias of `KEY_REFUSED_TEXT`** (TeslaBLE.py:105). Use the existing name in the test.

**F43 — Stale plan text.** "Questions for the user" 1 and 2 are already answered in the ledger. Decisions are numbered 1-8, 23, 24, 9-22. Remove the questions and renumber.

**F44 — The Task 10 grep test hits untouched comments.** `test_no_legacy_command_paths` greps for `VehiclePriority`, which still appears in comments at Provider.py:53, HomeAssistantProvider.py:42 and TeslaAPI.py:1258/2101, none on T10's file list. Add them.

**F45 — `checkCharge` ignores suppressions.** `checkCharge` → each Vehicle module's `updateChargeAtHome()` reads through BLE under `api_only` (the façade walk dropped it). Skip modules whose provider is suppressed for `READ_CHARGE`.

**F46 — Start-only "satisfied" reasons stamp "Charging".** `command()` treats `disconnected`/`complete` as SATISFIED for `charge_start`, and the lane then stamps "Charging". Map `disconnected` on start to UNSUPPORTED (or hands-off).

**F47 — A failed BLE wake now aborts the command.** Today `setChargeRate` and `applyChargeLimit` log a failed wake and proceed. Note it in the CHANGELOG, or proceed on UNREACHABLE for local providers.

**F48 — The Gen2 "mode 1" outcome appears only in the test.** `Outcome(UNSUPPORTED, "mode 1")` is asserted by the T4 test but missing from the Interfaces, and its precedence relative to "no slave" is implied only by the test. Add it to the Interfaces.

**F49 — Commands queue silently between Tasks 7 and 9.** The vehicle command queue is not started from T7, so `VehicleEndpoint` and `TWCSlave` rate commands queue silently until T9. This is acceptable under Decision 20 (no mid-phase deploy); state it in T7.

**F50 — `heldLimitText` changes visible text.** It shows "—" for `held is None` where today it shows "N% (restored)". Keep "(restored)".

## Counts

High 14 (F1–F14) · Medium 24 (F15–F38) · Low 12 (F39–F50)
