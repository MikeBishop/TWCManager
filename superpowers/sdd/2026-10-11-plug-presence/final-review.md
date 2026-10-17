# Final whole-branch review: plug-based vehicle presence

Range: `presence/2-charge-limits..presence/4-fleet-rate-queue` (primary), `presence/4-fleet-rate-queue..deploy/presence-3` (skimmed for interaction).
Checkout: `scratchpad/wt-plug` at `deploy/presence-3` (cce331f). Focused run: `test_plug_presence_scenarios`, `test_vehicle_presence`, `test_presence_handlers`, `test_teslaapi_controller`, `test_twcslave`: 284 passed.
Reviewer: Fable (self-reviewed; no advisor used, per the brief).

## Strengths

- **The 2026-10-11 incident is closed at both root causes.** The departed car is NOT_HOME on evidence, never re-presumed (`VehiclePresence._leave`/`_setHome`), and both policy-wide applies gate on `isHome` (TeslaBLE `applyChargeLimit`, TeslaAPI via `vehicle.atHome` -> `presence.isHome`). TeslaBLE reports a not-home skip as *handled* (`overall_success = True`), so VehiclePriority does not fall through to the Fleet API; TeslaAPI's `notHere` returns "success" for the same reason. `test_2026_10_11_...` and `TestDeployRegression20261011` drive the real queue, handlers and both channels and assert nothing is posted.
- **Lock discipline is clean.** I traced every `with self._lock` in VehiclePresence: the lock is held only to read/mutate the dicts. All I/O (`_probe`, `_pluggedInFor`, `_twcAmpsNow`, `_knownNow`, `_runHomeProof`, handlers, `nominate` from `_reconcileDeparting`) runs with the lock released. TeslaBLE calls `observeContact`/`observePlugState` while holding `_bleLock`, and those only take the presence lock, so the order is BLE -> presence, never the reverse. The queue's `Condition` is never held while calling into modules. The TWC serial thread only records (`observeUnplug`, `observePlug`) and takes the presence lock for `vinForTwc`. No deadlock or lock-held-across-I/O path found.
- **Reconciler covers the restart and in-flight-apply gaps.** The held limit lives in `settings["chargeLimits"]` (persisted via `saveNormalChargeLimit` -> `saveSettings`), survives a restart, and is restored by three independent routes: the departing handler on an unplug/read, `_sweepHeld` for a limit that became held after the car left (apply still running at unplug), and discovery (`discover` -> `_applyUnplugged` -> `_leave` -> onDeparting) for a presumed car found away after a restart.
- **Restore vs. arrival race is safe by construction.** `_cancelRestore` drops only a *pending* restore; a running one finishes and the arrival apply (same key) runs after it, so the end state is the policy limit. In the opposite order (apply running at unplug) the read-before-write in the apply sees Disconnected and sends nothing; if the apply completes first, `_sweepHeld` picks it up on the next 60 s tick.
- **Read-before-write is a real second line of defence.** The single-candidate attribution rule (spec's own rule) can mark the wrong Tesla HOME when a non-Tesla plugs into a CAN-off TWC; the BLE/API read then says Disconnected, `discover` returns False (strong source), nothing is sent, and the car goes NOT_HOME. I traced it to convergence.
- Evidence rules are implemented as the spec states them: strong (twc/ble) within `STRONG_EVIDENCE_HOLD` beats weak; a TWC naming the car beats a weak unplug; BLE silence is never absence; `WEAK_PLUG_MAX_AGE` stops an hours-old TeslaMate "plugged" plus a drive-past from making HOME.
- Broadcasts are confined to `broadcastVINs()`; charge commands carry the plug's VIN (`TWCSlave._chargeVIN`); Fleet wakes honour `vins`.
- The deploy-branch port (`slotFor("command")` for `hasRemoteChannel`, `slotFor("read")` for the presence API probe, `slotRequestFailed` on the online read) is small, correct, and the owner_read_only regression test plus the `hasRemoteChannel` mutation check close the obvious interaction.

## Issues

### Critical

None.

### Important

**I1. The remote departure restore is single-shot; a failure leaves the car on the home limit for the whole trip.**
- `lib/TWCManager/VehiclePresence.py:1173-1190` (`_startDeparting`, `viaBle=False` returns after recording) and `:1244-1252` (`fallbackSent = True` "once, whether or not a remote channel can send it"); `lib/TWCManager/PresenceHandlers.py:105-108` ("A failed restore is dropped, not replayed").
- For a **no-BLE install** (Fleet-only, TeslaMate+Fleet): `onDeparting` queues one `remoteOnly` restore. TeslaAPI returns "error" if `car_api_available()` is in `carApiErrorRetryMins` backoff from any earlier error, if `vehicle.ready()` is False, or on a 5xx. VehiclePriority retries once immediately, then the task is gone. The `DepartingRecord(viaBle=False)` stays in `_departing`, which makes `_sweepHeld` skip the VIN (`vin not in self._departing`), and `_reconcileDeparting` returns on `not record.viaBle`. Nothing ever retries.
- For a **BLE install** the 5-minute fallback is the same: `fallbackSent` is set before the handler runs, and the restore needs the car awake (`needToWake` is False for `limit == -1`, so `update_charge` on an asleep car fails and `decideChargeLimit` says "could not read; nothing sent"). After that only BLE retries happen, and the car is gone.
- Why it matters: the anti-goal "never lose a held outside limit" is met on paper (the saved pair survives), but the user-visible effect is the car driving around at 50% until it returns. For the 2026-10-11 user this is exactly the failure they will notice next.
- Fix (presence/3-plug-presence): bounded re-arm. Keep the record and, while `_restorePending(vin)`, re-run `_runDeparture` every `DEPARTING_SLOW_PROBE_INTERVAL` up to N (3) times for both the `viaBle=False` record and the post-fallback BLE record. Reuse the existing slow-probe cadence so there is no zero-delay loop (the ledger's reason for making `fallbackSent` unconditional). Add `remoteAttempts` to `DepartingRecord`. Tests: `test_fleet_only_unplug_one_remote_restore...` becomes "one restore when it succeeds; a second after 600 s when the first failed; never more than N".
- Not blocking the box: `commandPolicy: ble_only` and an Owner-only token mean no remote channel exists there today.

**I2. One failed BLE probe makes a HOME car `bleSilent` with no re-probe, which can hand a car on the TWC a Fleet API EVSE.**
- `lib/TWCManager/VehiclePresence.py:423-435` (`bleSilent`), `lib/TWCManager/EVSEController/TeslaAPIController.py:106-117` (`_umcCar`) and `:149-158`.
- `_reach[vin] = (False, at)` is written by any failed probe and replaced only by a later contact. HOME cars are probed once (`toNominate` "home-by-telemetry", or as a VIN-less candidate) and never again. Sequence: car comes home, plugs into the VIN-reading TWC at a time the policy offers 0 A (no charge -> no VIN -> no proof); TeslaMate says plugged_in + inside -> HOME; the one body-controller probe times out (the box measured 4.2 s for a good answer; sporadic BLE failures are real on this hardware); `_reachOk` is >300 s old because the car was away. Now `bleSilent` is True, the TWC is `blind` (non-00 state) but `_umcCar` exempts the car, and `allEVSEs` lists it. The distributor gives it a power share and queues `fleetSetChargeRate` (paid) to a car that is physically on the TWC, while the TWC also gets a share.
- Recovery exists but is incidental: the next policy-wide BLE apply sends `charging-set-limit` (a successful command updates `_reach`), or the car starts charging and the VIN proof lands. On the box the Owner-only token refuses `set_charging_amps` ("Tesla API is read-only"), so the cost is a wrong power split for a minute or two, not money.
- Fix (presence/4-fleet-rate-queue, since `bleSilent`/`_umcCar` landed in Task 12): (a) require two consecutive failed probes, or a failed probe at least `PROBE_INTERVAL` after a previous failure, before `bleSilent` is True; (b) while a HOME car is `bleSilent` and not TWC-attributed, nominate a BLE-only probe every `DEPARTING_SLOW_PROBE_INTERVAL` so the exemption ages. Test: a single failed probe on arrival does not list an EVSE; the second one does; a later success removes it.
- Related ledger items this subsumes: Task 8 "failed-probe exclusion never ages", Task 12 "bleSilent never ages".

### Minor

**M1. The first departing probe races the BLE restore for `_bleLock`.** `VehiclePresence.py:1187-1190`: `_startDeparting` runs `_probe(bleOnly=True)` inline on the presence thread right after `onDeparting` queued the `localOnly` restore to the worker. `probePresence` is `@_serialized`; if it wins the lock the restore waits up to `presenceProbeTimeout` (15 s) while the car is pulling out. The inline probe adds nothing (the restore is already queued, so `_reconcileDeparting` won't re-queue; a successful restore reports contact itself). Fix (presence/3): replace the inline probe with `self.nominate(vin, "departing", delays=(self.DEPARTING_PROBE_INTERVAL,))`. Ledger Task 5 minor 4 -> upgrade to fix-before-PR, cheap.

**M2. A VIN proof does not clear a wrong attribution on the same TWC.** `_applyProof` (`VehiclePresence.py:1013-1015`) has no TWC key, so `_twcVin[twc]` from an earlier `_vinLessPlug` (power-start within `PLUG_EVIDENCE_WINDOW` on a TWC that had not yet read a VIN this run) can name car B while the proof names car A. B stays `isTwcAttributed` (no Fleet EVSE, excluded from broadcasts) until it leaves. B is always "here" (inside/BLE) for this to happen, so no stray command; wrong bookkeeping only. Fix (presence/3): `observeProof(vin, source, twc=None)` from `recordVehicleVIN`, and drop that TWC's attribution when it names a different VIN.

**M3. A car away at restart under `ble_only` with no location source stays PRESUMED indefinitely.** Nothing re-nominates it (`_timeUntilNextDue` returns None with no due times and no NOT_HOME cars); the policy-wide BLE apply wakes/reads/sends to it every cycle until the breaker opens. No wrong command (BLE is local and fails), but noisy logs and `numCarsAtHome` counts it. With TeslaMate (the box) the retained location resolves it. Suggest a slow re-probe (e.g. hourly) for PRESUMED cars; upstream only.

**M4. Fail-open/fail-closed is inconsistent across modules when presence raises.** Fail closed: `discover` in TeslaBLE/TeslaAPI. Fail open: `_broadcastTargets` (every configured car), `_chargeTargetVINs` (None -> every vehicle), `CarApiVehicle.atHome` (location fallback), `TWCSlave._chargeVIN` (None -> broadcast). Unguarded: `HomeAssistant._atHome`, `TeslaAPIController.allEVSEs` (`isPluggedHome`). In practice none of these can raise (`state()`/`broadcastVINs` are dict reads under a lock with every external call already wrapped), so this is a consistency note: the open-on-failure paths all lead to a *start/stop* broadcast, never to a charge-limit, which is the anti-goal that matters. Document the rule in one place (VehiclePresence header) rather than change code.

**M5. Strong BLE plugged read on a fast charger still makes HOME.** `_applyPlugged` (`:1036-1039`) returns before the `fastCharger` check for strong sources; `discover` handles it, and a DC charger inside BLE range of the box is implausible. Keep deferred; reorder the check when touching the function.

**M6. `fastCharger` and the `_reach` record never age; `_inside` never ages by design.** Documented in the header. Fine, given M4/I2.

**M7. Stale comment.** `TeslaBLE.py:840-841` says "a DEPARTING or NOT_HOME car"; DEPARTING is not a tracker state since Task 2. Also `PresenceHandlers.py:116-130` describes "falls back to the departure handler's remote restore once BLE has gone" without mentioning that it is once.

**M8. Test-suite coupling.** `test_vehicle_presence.py` touches private attributes 63 times (`_departing`, `_reach`, `_twcVin`, `_plug`, `_home`); `test_plug_presence_scenarios.py` 6 times (`_departing[V1].bleGoneSince`, `_twcVin` writes); the scenario `World` is ~600 lines and models BLE, Fleet, TeslaMate, TWC and the clock. This is the right shape for a state machine's unit tests and for end-to-end scenarios, but every rename of a dict will break ~60 tests. Suggest a tiny inspection API (`debugState(vin) -> dict`) used by tests instead of the raw dicts. Nothing vacuous found: every test I read asserts on commands sent / not sent, state, or saved limits, and the 2026-10-11 test asserts both positive (the one restore) and negative (no wake, no set_charge_limit, no vehicle_data) outcomes.

**M9. `_reportContact` under `_bleLock` writes `master.settings["Vehicles"][vin]["bleProven"]`** from the worker thread while the background thread may be serialising settings. Pre-existing pattern across the codebase (settings is mutated from several threads); noting only.

## Deferred-item adjudication

| Ledger item | Ruling |
|---|---|
| T1 partial commits carry new author dates | keep deferred (cosmetic) |
| T2 handlers judged on batch end state (H->N->H runs onArrival; double onDeparting) | keep deferred: one extra read-before-write apply at worst; the restore coalesces on the queue key |
| T2 hold/reach ages measured at apply time | keep deferred: observations drain within the same pass |
| T2 weak plugged record / `_inside` never age | resolved for the plug record by `WEAK_PLUG_MAX_AGE`; `_inside` not ageing is documented and correct for a parked car |
| T2 TeslaBLE stale "DEPARTING or NOT_HOME" comment | still present at `TeslaBLE.py:840`; fix with M7 before PRs |
| T2 `_applyProof` records source "twc" regardless | keep deferred: only "twc" proofs exist |
| T2 presenceSources warning on null/empty | keep deferred |
| T2 duplicated test setup | keep deferred |
| T3 blePluggedIn Unknown/SNA | resolved (`chargingStatePlugged` returns None) |
| T3 apiSource cached chargingState | resolved (`lastChargeState`, fetch-stamp check) |
| T4 rule-4 single-candidate guess gets strong "twc" label | keep deferred: a wrong guess is corrected by the read-before-write within one apply; a weak TeslaMate unplug is ignored for at most 300 s and the TWC's own unplug still departs the car |
| T4 ambiguous plug swept twice | keep deferred |
| T4 missing tests (`_defaultTwcAmps`, target-in-excluded, telemetry-kept) | keep deferred; add with M2's test |
| T4 verify on box: `reportedAmpsMax == chargerPilotCurrent` | box watch list (the user's TWC reads VINs, so attribution is rarely exercised there) |
| T5 slow-mode outside nomination starts a second probe chain | keep deferred: `nominate` dedupes within 60 s; worst case two BLE probes per 600 s |
| T5 unheld departing due skips coinciding nominations | keep deferred |
| T5 BLE retry re-runs onDeparting; if BLE gone, immediate remote | keep deferred: `bleApplies` cannot change at runtime |
| T5 first departing probe competes with the restore for BLE | **fix before PRs** (M1) |
| T5 `_startDeparting` uses pass-start now | keep deferred |
| T6 TeslaAPI `_discover` BLE branch recorded as "api" | keep deferred: `get_charge_state` already reported the same read as "ble" |
| T6 strong BLE plugged + fastCharger makes HOME | keep deferred (M5) |
| T6 missing tests (BLE telemetry gate, API start gate) | keep deferred |
| T6 no test for weak outside + BLE-unreachable | keep deferred |
| T7 `isPluggedHome` unguarded in the controller | keep deferred (M4) |
| T7 `test_departing_car_is_never_woken` convoluted | keep deferred |
| T8 fail-open on presence exception | keep deferred (M4) |
| T8 targeted start runs policy-wide `applyChargeLimit` | confirmed at `TeslaAPI.py:906` (`self.applyChargeLimit(self.lastChargeLimitApplied)` with no vin inside the per-vehicle start loop). Pre-existing; the policy-wide gates (`atHome`, 60 s rate limit, `_discover`) hold, so no not-home car gets a limit. Keep deferred; pass `vin=vehicle.VIN` when touching the function |
| T8 BLE stop clears `_stopAskingToStartCharging` for all cars | keep deferred (mirrors TeslaAPI) |
| T8 failed-probe exclusion never ages | **fix before PRs** (I2) |
| T8 no test for `vinForTwc` raising | keep deferred |
| T8 HA targeted VIN not held returns success | keep deferred (HA restore is a documented follow-up) |
| T8 enphase test warning | pre-existing |
| T9 HA docs `atHomeRadius` default | keep deferred; one line |
| T10 c3 `_cancelRestore` redundant with key replacement | **not redundant**: `onArrival` returns early when `lastChargeLimitApplied == 0` and queues nothing, so without the cancel a pending restore would run against a car that is home. Keep the cancel |
| T10 c4 departed car w/o telemetry stays a broadcast candidate | keep: the spec's candidate rule ("inside the radius or BLE reachable") says so, and it is the fallback for an unattributed plug; Fleet wake is gated by `atHome` so the cost is a BLE attempt and at most one `vehicle_data` read |
| T10 c5 `_discover` trusts cached `chargingState` with a live feed | keep deferred: TeslaMate and FleetTelemetryMQTT both map a charging-state topic, so "live" implies the value is pushed |
| T10 c6 `_lastProbe` set without a probe on departing end | keep deferred |
| T10 scenario fixture reaches private internals | keep deferred (M8) |
| T12 bleSilent never ages | **fix before PRs** (I2) |
| T12 test writes `presence._twcVin` | keep deferred (M8) |
| T13 `atHome` falls back to location if `isHome` raises | keep deferred (M4) |
| T13 charge_start/wake POST without timeout | token-slots branch; box watch list |

## Declined to judge

- HomeAssistant gets no departure restore (`-1` sentinel) — plan follow-up, user-directed.
- The offset-current fingerprint for several cars on VIN-less TWCs — plan follow-up.
- A presumed car is woken by the Fleet API at startup when the policy limit rises (one wake + `vehicle_data`, then NOT_HOME) — the spec's "presumed present, discovered on wake" rule.
- A single Tesla parked unplugged at home is woken over BLE and read when a non-Tesla plugs into a CAN-off TWC — the spec's single-candidate rule; the read-before-write prevents any command.
- A car on a VIN-reading TWC that is plugged in but not charging has no TWC identity until it charges (Gen2 reports VINs only while charging) — the spec's evidence table says "a TWC that reports the car's VIN"; TeslaMate/API+location covers it.
- A NOT_HOME car inside the radius remains a broadcast candidate — the spec's candidate definition.
- The 1,000 ft default and the changelog wording — the user's call in the spec.
- GPS drift outside 1,000 ft for a car on a UMC making it NOT_HOME — follows from the radius; user can widen it.
- Token-slot internals, `TeslaTokenSlot`, Owner/Fleet slot migration — reviewed on #692/Task 13 with a mutation check; I checked only the three ported call sites.
- The charge_start/wake_up POSTs without timeouts — token-slots code, unchanged here.
- Distributor zero-share stop — ruled to a separate branch off main.
- The Fleet API wake for a presumed car counting as a paid command — pricing is outside the plan.

## Recommendations

1. Before PRs: I1 (bounded remote-restore retry), I2 (bleSilent needs a second failure and a slow re-probe), M1 (nominate the first departing probe instead of probing inline), M2 (proof clears the TWC's attribution), M7 (two comments). All are small; I1 and M1 are in VehiclePresence/PresenceHandlers only, I2 touches `bleSilent` plus one nomination.
2. Carry the Task 13 test changes back to presence/3 and presence/4 as the ledger says, and squash the "fix round" commits into their tasks before opening PRs; the branch reads well commit-by-commit otherwise.
3. Box watch list (first days): `grep -E "presence:|can't tell which car|restoring its normal charge limit|not plugged in here"` in the log; confirm the BLE restore on unplug lands before the car leaves (look for the restore's `Restored ... to charge limit` line within ~20 s of `TWC .. unplugged`); confirm no `fleetSetChargeRate`/EVSE line appears for the car while it is on the TWC (I2); confirm `reportedAmpsMax` in the heartbeat equals the BLE `chargerPilotCurrent` if the TWC ever logs a VIN-less plug.
4. Consider an inspection accessor for tests (M8) when touching VehiclePresence next; it will pay for itself on the first rename.

## Assessment

**Ready to deploy to the box?** Yes.
**Ready for upstream PRs?** With fixes (I1, I2, M1, M2, M7).

**Reasoning:** The motivating incident cannot recur on this code: a departed car is NOT_HOME on evidence, both policy-wide applies skip it, and a not-home skip no longer falls through to the Fleet API. Concurrency is sound (lock never held across I/O; BLE -> presence ordering only; queue coalescing makes the restore/apply race converge). The held outside limit is persisted and has three restore routes. The two Important findings are both about the *remote* channel (a single-shot restore that can silently fail; a sticky BLE-silent exemption that can list a TWC car as a Fleet EVSE). On the live box neither applies: `commandPolicy: ble_only` rules out the remote channel, the Owner-only token refuses every Fleet command, the TWC reads VINs, and TeslaMate supplies location. Upstream users on Fleet-only or multi-car VIN-less setups would hit them, so they should be fixed before the PRs, and both fixes are contained.
