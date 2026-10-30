# Task 4 report: the Gen2 unplug rule with its two filters

Commit **02d47b30** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent e5267e5b). Not pushed.

## What I implemented, and where

- **`TWCSlave.unplugStep(now) -> bool`** (`lib/TWCManager/TWCSlave.py`). It runs on the serial thread with no I/O, doing only stamp and float comparisons on each heartbeat pass.
  - Constants (class): `UNPLUG_DEBOUNCE, PLUGGED_RUN, LINK_GRACE = 60, 60, 300`.
  - State (class defaults, three fields): `pluggedSince` (start of the current non-00 run), `ampsMaxBefore` (`reportedAmpsMax` on the last non-00 heartbeat; set to 0 once the current 00 run can no longer be an unplug, or after it has fired), `zeroSince` (00-run onset, or None).
  - **Non-00:** if a 00 run was open, the plugged run restarts now; `ampsMaxBefore = reportedAmpsMax`.
  - **First 00 heartbeat (onset):** stamps `zeroSince`. The run qualifies only if all of these hold:
    - `ampsMaxBefore > 0` (filter (a), first half);
    - `reportedAmpsMax == 0` on this first 00 heartbeat (filter (a), second half; strict per F6);
    - the plugged run is ≥ `PLUGGED_RUN`;
    - the onset is ≥ `LINK_GRACE` after the first reply.

    If the run doesn't qualify, `ampsMaxBefore` is set to 0. Every onset logs at INFO: `"TWC %s: 00 onset, max %.2f A before, %.2f A now: %s"`, where `%s` is `an unplug if it holds` or `not an unplug`.
  - **Later 00 heartbeats:** returns True once, when `ampsMaxBefore` and `now - zeroSince >= UNPLUG_DEBOUNCE`, and disarms by setting `ampsMaxBefore = 0`.
- **Placement** (`TWCMaster.observeChargingSessions`). The loop takes `now = time.time()` once. At the top of the per-slave body, ahead of the amps if/else (so charging heartbeats also refresh the plugged run and max), it calls `if slaveTWC.unplugStep(now): self._plugSession(slaveTWC, False)`.
  - The addendum asked for the rule inline in the loop. I put the body on the slave instead. It is the same single state, not a parallel machine. `self.` names keep black from splitting lines, which saved about 10 lines.
- **LINK_GRACE reuses the first-reply time.** `TWCSlave.heardFrom` is now the first reply's time (`self.heardFrom = self.heardFrom or now`; default 0). Every truthiness check stays valid, and tests that set `heardFrom = True` read as "linked at epoch 1".
  - I added no `linkReady()` and did not touch `TWCManager.py` (addendum).
- **The filtered end** (`TWCMaster._plugSession(slave, begin=False)`). It keeps the existing try/except and makes registry calls only:
  - `v = registry.vehicleAt(twcid)`, else the single `Presence.candidates(master)` car (T12);
  - filter (b): if `Presence.telemetrySaysPlugged(master, v)`, it logs `"TWC %s: not an unplug, %s is plugged in"` and returns. It writes nothing, and the session stays;
  - otherwise `v.observe("pluggedIn", False, "Gen2TWC")`. `noteObservation` marks `unplug` for that source;
  - then `registry.endPlugSession(twcid)` (g), which also removes any anonymous placeholder.
- **`Gen2TWC.vehicleKey`.** After the `currentVIN` branch, `v = reg.vehicleAt(twcid)`. It returns `v.key` if `v` is anonymous, or if `v` is a VIN car while the TWC reports a plugged state; otherwise None.
  - This replaces both the `anonKey` branch and the `lastVIN` branch. `vehicleAt` prefers the attributed car over an anonymous placeholder.
  - Why this matters: if the anonymous branch came first, a placeholder left over from a charge start whose VIN read never confirmed would make the raw-00 anonymous close fire. That close would then end the attributed car's session and mark its unplug with no filter. That is the false-00 loop this task exists to prevent. `test_vehicle_key_names_the_car_after_a_charge_stop_and_nobody_after_an_unplug` pins it with a 47 A waking 00.
  - The PLUGGED_STATES gate keeps BASE's "no key at 00". Without it, `chargeGate` would issue a start for a VIN car at 00, which would be an unlisted change (F11).
- **Docstrings.** `_blindTWCs` (VehicleEndpoint) and `groupEndpoints` (ChargingPoint) no longer mention `lastVIN`.

## Deletions taken, and how each was verified

- **Charge-stop `_plugSession(slaveTWC, False)`: deleted.** `git grep -n "_plugSession(slaveTWC, False)" -- lib` gives only `TWCMaster.py:1298` (the filtered unplug) and `:1364` (the anonymous raw-00 close). `recordVehicleSessionEnd`, `plugSessions += 1`, `lastVIN = currentVIN` and the VIN-query reset stay.
- **`Gen2TWC.vehicleKey`'s `lastVIN` branch: deleted** (along with the separate `anonKey` branch). `git grep -n lastVIN -- lib/TWCManager/EVSEInstance/Gen2TWC.py` returns nothing. `lastVIN` stays for the kWh session record, `/api` and `getLastVehicle`: `git grep -nw lastVIN -- lib html docs` gives 11 hits, none in key logic.
- **`isAnonKey` raw-00 close: kept. It is not subsumed.** An anonymous session whose 00 never qualifies would otherwise linger. That happens with an idle car at 0 A (F6), a 00 inside the link grace, or a short plugged run. A lingering anonymous key at 00 lets `chargeGate` "start" an anonymous key, which fans out to the candidates and can bring paid wakes.
  - With the `vehicleKey` reorder, the close is reached only when no car is attributed to the point, so it never touches a VIN car's `twcVin`.
  - It shares `_plugSession(False)`. Its `vehicleAt` returns the anonymous record, so the candidates fallback never runs for it.
- **Also dropped:** the `_plugSession` if/else (now `return` after begin).

## What Task 5 consumes

- `TWCSlave.unplugStep(now) -> bool`, `UNPLUG_DEBOUNCE`, `PLUGGED_RUN`, `LINK_GRACE`, and `heardFrom` as the first-reply time (0 = never).
- `TWCMaster._plugSession(slave, False)` serves two callers: the filtered unplug, and the raw-00 anonymous close in the `pluggedCars()[0]` probe's branch, which Task 5 touches. For the filtered unplug it is: the VIN car, or else the single `candidates(master)` car, with the telemetry veto, then `endPlugSession`. Task 5's attribution can replace the single-candidate fallback with its filtered winner. The fallback is one `if v is None:` block.
- `Gen2TWC.vehicleKey` now comes from `registry.vehicleAt(twcid)`. An anonymous placeholder is returned only when no car is attributed.
- The VIN-less 00 probe (`pluggedCars()[0]` at `TWCMaster.py` `observeChargingSessions`) is untouched. Task 5 deletes it.

## Tests

### New tests

- **`tests/unit/test_gen2_unplug.py`** (6, through a real `Gen2TWC` and real heartbeats):
  - the drop is one unplug;
  - 47 A on the first 00 (and a drop on the second heartbeat) is never one;
  - idle at 0 A is never one (F6);
  - link grace and a short run are never one;
  - the onset log;
  - one report per run.
- **`tests/unit/test_presence.py`** (+6):
  - telemetry veto;
  - `twcVin` kept at charge stop until the unplug (g);
  - `vehicleKey` after charge stop and after unplug (E5), including a lingering anonymous placeholder plus a waking 00;
  - VIN-less single candidate (T12);
  - non-Tesla plug (the account car away) departs nobody;
  - restart steady 00 with telemetry plugged is HOME and restores nothing.
- **`tests/unit/test_command_path_parity.py`** (+8 rows, appended only; `git diff e5267e5b --stat` on the file shows 210 insertions and 0 deletions):
  - `box_2026_10_18_departure_restores_over_ble_within_a_minute`: BLE `charging-set-limit 90` once, at onset+60..+120 s, no wake, paid (0,0,0);
  - `box_2026_10_18_false_00_at_47_a_with_telemetry_plugged_is_no_departure`;
  - `box_2026_10_17_morning_wake_episodes_declare_no_departure`: the 07:58:28–08:39:01 run table at 1 s heartbeats;
  - `a_sleeping_car_at_a_gen2_00_is_never_woken_by_a_restore`: 3 real cycles; no BLE wake; `wake_up` count 0;
  - `an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise`: policy 80 above 50; no unplug, no `onArrival`, no wake, paid 0;
  - `no_gps_source_plug_unplug_cycle_end_to_end` (scenario 15): **departure half only**, with BLE plus a VIN-less TWC. The re-plug attribution half belongs to Task 5;
  - `gen2_steady_00_inside_the_link_grace_is_no_departure` (scenario 12): **renamed** from `..._does_not_block_startup_charging`. See Concerns;
  - `plug_in_on_a_vin_twc_comes_home_with_one_apply` (scenario 2).

### TDD evidence

On a detached worktree at e5267e5b (BASE lib) with the final, committed versions of the three new or extended test files copied in, **15 fail**:
- all 6 in `test_gen2_unplug.py`;
- presence: veto, charge-stop-keeps, `vehicleKey`, VIN-less;
- parity: box departure, morning episodes, sleeping-car, idle-at-0, no-GPS.

These pass on BASE as characterization rows: non-Tesla, restart steady 00, the 47 A box row, the scenario-12 grace row, and scenario 2. The six unit tests were written first and failed (`_unplugged` missing, no unplug mark) before any lib change.

### Changed existing tests (deleted-test rule)

- `test_gen2twc_provider.py::test_vehicle_key_keeps_last_vin_while_plugged_state` → `..._keeps_the_confirmed_car_while_plugged_state`. **PLUMBING-ONLY**: `s.lastVIN = VIN` becomes a `twcVin` observation, and an `endPlugSession` (the unplug) comes before the anonymous session.
- `test_gen2twc_provider.py::test_amps_range_never_none_while_set_amps_ready`: `s.lastVIN = VIN` becomes `known.observe("twcVin", …)`. PLUMBING-ONLY.
- `test_twcmaster_vin_confirmation.py::test_charging_session_begins_and_ends_anonymous_vehicle` → `test_anonymous_plug_session_begins_at_a_charge_and_ends_at_the_unplug`. **INTENTIONALLY CHANGED (g)**: the session survives the charge stop and ends when `unplugStep` fires. The Mock slave's `unplugStep` is stubbed as `Mock(return_value=False)`, then set to return True for the unplug, because a bare Mock return is truthy.
- `test_charging_points.py`: `stoppedTwc` and the shapes' `stopped` use a `named()` `twcVin` helper, and `stale` uses `currentVIN`. PLUMBING-ONLY.
  - `test_two_twcs_claiming_one_car_stay_separate_points_within_budget` lost its "both TWCs report the same stale lastVIN" shape. It is unreachable by design (`twcVin` names one point per car). The stale double claim is now made through `currentVIN`.
- Lift tests: `test_control_tick.py::test_the_lift_survives_a_session_end_racing_the_tick` gets `twcVin` set as the confirmation does, and `test_offer_characterization.py::test_mode_1_lift_goes_once_per_session_for_a_twc_only_point` gets an `observeTwcVin` after the first beat. Both PLUMBING-ONLY: real VIN confirmation sets `twcVin` and drops the charge-start anonymous placeholder.
- `test_registry_plug_sessions.py`, `test_outcome_desired.py` and the `test_amps_reconciler.py` lift tests needed no change. They drive the registry's `endPlugSession` directly, which still clears `twcVin`.
- `black` was run on all touched black-style files. It reflowed two pre-existing lines in `test_gen2twc_provider.py`. `test_charging_points.py` is a legacy `;` file: no new `;` joins were added, and edited lines keep their style.

### Results

- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2064 passed, 1 xfailed**.
- `tests/unit tests/EMS`: **2055 passed, 1 warning**. That is 2035 at the task's baseline, plus 6 unit, 6 presence and 8 parity tests.
- No existing parity count or timing moved; the file diff is append-only.

## Lib delta

- `git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 26,324 before, 26,358 after.
- `git diff --shortstat e5267e5b -- lib`: 5 files changed, 51 insertions(+), 17 deletions(−). **Net +34.**
- Target ≤ +10; plan +41. I am 24 over target, just inside the "> 25 over: stop" line.
- Where the lines go:
  - rule body about +20;
  - filtered end (vehicleAt, candidates fallback, veto log, observe) about +10;
  - constants and state about +4.
- Deletions: −1 for the charge-stop end and about −3 from merging the `vehicleKey` branches.
- Why +10 wasn't reachable:
  - the onset log alone is 3 lines;
  - three filters plus the debounce need at least three stamps;
  - the one remaining deletion candidate (the anonymous raw-00 close) is not subsumed; see above.
- I found no further dead duplication on this path. `getLastVehicle` and `lastVIN` still serve `/api` and kWh records.

## Concerns

1. **Scenario 12's start half is NEEDS_CONTEXT** (Task 3's applicability table, not changed here). After a restart, a held, never-unplugged car at a Gen2 00 with no telemetry is PRESUMED. The start's BLE ping answers, which gives `contact` and makes the car HOME. Then `applicable` for a start needs a plug, and the held-car presumption applies only in the PRESUMED cell. The result is `"<vin> charging: not here (not plugged in)"` and `satisfied rules: not here`, so no `charging-start` is sent.
   - Question for the controller: should a held car with no unplug mark keep the plug presumption at HOME (BLE contact), or does contact correctly cancel it? The renamed row asserts only Task 4's part: no departure, no restore, no wake, paid 0.
2. **A re-link within the 26 s slave timeout doesn't re-arm `LINK_GRACE`.** There is no `linkReady()`, per the addendum. A slave silent for more than 26 s is deleted and recreated by `newSlave`, so the grace re-arms then.
3. **`vehicleKey` now calls `registry.vehicleAt`** (a scan of the registry's cars under leaf locks; no I/O) wherever `vehicleKey` is read, including once per heartbeat on the serial thread. BASE did a string check. It is cheap with a few cars, but it is new per-heartbeat work. The unplug rule itself is stamp comparisons; `candidates()` runs only once per qualifying run.
4. **An idle car's departure (0 A at 03) never ends its `twcVin`** (F6: only telemetry departs it). Until another car's VIN confirms at that point, an unnamed next car on that TWC reads as the old car's key. This is inherent in (g) plus F6.
5. **Filter (a) rests on n = 2 real unplugs** (evidence file). Every onset is logged with max before/now, so the box can verify it.
6. **Multi-TWC gap (inherited from T12).** A car named by another Gen2 that is now at 00 has `twcVinAt == NEVER`, so `candidates()` includes it. If it is the only candidate, a VIN-less TWC's real unplug departs it. Task 5's pilot filter over `candidates()` narrows this.
7. **The `pluggedCars()[0]` probe can re-begin an anonymous placeholder at 00.** The filtered unplug then finds that placeholder through `vehicleAt`, skips the candidates fallback, and departs no car. This goes away when Task 5 deletes the probe.
8. **Restart:** checked. The registry persists only names and seen times, not observations, so `twcVin` and with it `vehicleKey` start empty after a restart, as `lastVIN` did.
9. Placement deviates from the addendum's wording (body on `TWCSlave.unplugStep`, called from the loop's top) for line count. The state is the single per-slave set the addendum asked for.

---

# Fix round 1: point commands, plug events, scenario 12

Commit **761b4296** (parent 02d47b30). Not pushed.

## What changed

1. **A charging point's own commands always apply.** `Reconciler.beforeWrite` skips `inapplicable` when `provider.module is None`, which is the mark Gen2TWCProvider and Gen3TWCProvider carry today. Commands addressed to the car are still gated: BLE, Owner, Fleet and HA all have a module. The pre-wake NOT_HOME check in `Run.runAttempt` applies only to cloud wakes, so it never sees a point provider.
2. **"Plugged" for a car-addressed start or amps follows events** (`Presence.applicable`, start/amps cell only). The cell now sends when any of these hold:
   - `pluggedNow` (unchanged);
   - the car's newest non-empty `twcVin` observation is newer than `leaving(v)` = max(unplug, driveStart). A Gen2 at 00 keeps naming a sleeping car until the filtered unplug clears `twcVin`, so a 00 heartbeat alone never unplugs it. A drive start also ends it, which F2 requires;
   - the held-car presumption: a held limit, no `unplug` mark, and either PRESUMED (today's cell, unchanged) or no plug reading at all (new; it covers HOME and every other cell).

   To support the third case, `pluggedNow` is split. `plugEvidence(master, v) -> Optional[bool]` (newest reading; None means nothing says either way) has the old body, and `pluggedNow` returns `plugEvidence(...) is True`.
3. **Scenario 12 is restored as `test_gen2_steady_00_after_link_does_not_block_startup_charging`.** After the steady 00 inside the grace, the BLE ping answers once and the car is HOME. `charging-start` then goes over BLE, with no restore, no wake, the held limit kept, and paid (0,0,0).

## Where I narrowed the ruling (please confirm)

- **"Plug-in evidence newer than the newest unplug mark" is not applied literally to the `plugIn` mark.** A literal version broke two existing tests:
  - `test_presence.py::test_start_and_amps_need_a_plug_here`: a TeslaMate "pluggedIn False" reading after a BLE "Stopped" marks no unplug event, because the reading is the first from that source. A plugIn-vs-unplug comparison would send anyway.
  - Parity scenario 10, `test_startup_wake_finds_the_car_unplugged_and_sends_nothing`: the wake's read says Disconnected inside the radius. The held presumption at HOME would have sent `charge_start` and moved paid from (1,1,0) to (1,1,1).

  So readings stay primary (`pluggedNow`), and the held presumption outside PRESUMED needs "no plug reading at all". With that, every existing Task 2/3 assertion and parity row is kept unchanged.
- **Live telemetry `pluggedIn` True** is already a reading inside `pluggedNow`, so I added no separate term.
- **The Gen2 plug-session begin is not counted for a VIN car.** It creates an anonymous record only. A TWC naming the car is the event that counts.

## Tests

New tests:
- `test_presence.py::test_a_charging_point_s_own_start_always_applies`: a point provider starts a car placed outside the radius;
- `test_presence.py::test_a_car_a_gen2_names_at_00_is_plugged_for_a_start_until_it_leaves`: HOME through BLE contact, named at 00, the start goes; after the Gen2 unplug, `away`;
- the scenario 12 row restored.

TDD evidence: with the round-1 lib changes stashed, all 3 fail. With them applied, all 3 pass.

Results:
- `tests/unit tests/EMS`: **2057 passed, 1 warning**.
- The parity file is still append-only against e5267e5b (215 insertions, 0 deletions), so no existing count moved.

## Size (item 4)

`git diff --shortstat e5267e5b -- lib`: 7 files changed, 67 insertions(+), 23 deletions(−). **Net +44** (26,324 → 26,368). Round 1 itself is +10: the `plugEvidence` split (+4), the start/amps cell (+5) and the point gate (+1).

Deletions I looked at again:
- **`Gen2TWC.vehicleKey`'s `lastVIN` branch:** already deleted in 02d47b30.
- **`isAnonKey` raw-00 close: still blocked.** It is not subsumed. An anonymous session whose 00 never qualifies would linger: an idle car at 0 A (F6), a 00 inside the grace, or a short run. `controlPass`'s `chargeGate` would then start the anonymous key at 00, and that start fans out to the candidates over car-addressed channels. That is more permissive now that the held presumption reaches HOME.
- **Old plug tracking in `TWCSlave` replaced by `unplugStep`:** there is none. Its only other plug code is `pluggedCars`, which is Task 5's deletion along with its 00 probe.
- **A cheaper registry scan in `vehicleKey`:** `vehicleAt` → `_attributedTo` scans the registry's cars. An index would add lines, not remove them. Left as is; it is disclosed as Concern 3.

That leaves the task at **+44 against ≤ +10**, which is past the 25-over stop line (+35). Round 1's +10 came from the ruling itself. I found no further deletion that keeps BASE behaviour. Next step is the controller's call.

---

# Fix round 2: a newer unplugged reading beats a stale naming; trims

Commit **52ebb609** (parent 761b4296). Not pushed.

## What changed

- **Important 1.** In the start/amps cell, a TWC naming counts as plugged only when it is newer than `leaving(v)` **and** no plug reading after the naming says unplugged: `pluggedNow(master, v, True, since=named.at)`.
  - A Disconnected reading from before the naming is excluded by `since`, so it cannot block the midnight start.
  - Test: `test_presence.py::test_an_unplugged_reading_after_the_naming_outweighs_it_and_an_older_one_does_not`. An older Fleet Disconnected still gives SEND; a Fleet Disconnected read after the naming gives `(not here, "not plugged in")`.
  - The midnight-start tests still pass: scenario 12 and `..._names_at_00_is_plugged_for_a_start_until_it_leaves`.
- **Size cut: `plugEvidence` folded back into `pluggedNow(master, v, unknown=False, since=NEVER)`.** `applicable` scans once with `pluggedNow(master, v, None)`; its other cells use the result's truthiness, so they read it as before. The old name `plugEvidence` no longer appears anywhere in lib or tests (`git grep -nw plugEvidence -- lib tests` finds nothing).
- **Size cut: the `vehicleAt`/candidates fallback is shorter by one line** (three lines instead of four).
- **Size cut: three comments shortened:** `_plugSession`, the `TWCSlave` unplug-state comment, and the start/amps cell.
- **Minor 1.** `TWCMaster.newSlave` sets `pluggedSince = time.time()` when a known slave links again, so a 00 within `PLUGGED_RUN` of the re-link is never an unplug. The comment it replaced was a how-comment. The new `newSlave` lines run only on linkready (`TWCManager.py` :1231 and :1752); the other callers reach `newSlave` only on a KeyError, which means a new slave.
  - Test: `test_gen2_unplug.py::test_a_re_link_starts_a_new_plugged_run`.
  - The link grace itself still re-arms only for a slave recreated after the 26 s timeout.
- **Minor 3.** The sleeping-car parity row now states its full paid tuple, **(0, 0, 1)**. Over three real unplugs, the restore's single paid request is one blind Fleet `set_charge_limit` to the asleep car. There is no wake on any channel and no `vehicle_data` read. This matches scenario 18's rule that a restore never wakes.
- **Minor 7.** A non-vetoed unplug logs `"TWC %s: unplugged, %s departs"` at INFO.
- **Minor 6 (side effect, for the PR notes).** The charge stop no longer calls `endPlugSession`, which used to pop the point's `_pending` VIN state. So a VIN rejected during one charge session now stays rejected for the rest of that plug-in. The filtered unplug or the raw-00 anonymous close clears it.
- **Not taken, per instructions:** Important 2 and Minor 4 go to Task 5, Minor 2 to Task 7. I did not take the behaviour-changing cuts either: PLUGGED_RUN and the single-candidate fallback stay.

## Tests

- TDD: with the round-2 lib changes stashed, both new tests fail. With them applied, both pass.
- `tests/unit tests/EMS`: **2059 passed, 1 warning**.
- The parity file is still append-only against e5267e5b (216 insertions, 0 deletions). The only edit to a row this task added is the sleeping-car tuple.

## Size

- `git diff --shortstat e5267e5b -- lib`: 7 files changed, 66 insertions(+), 29 deletions(−). **Net +37** (26,324 → 26,361), down from +44.
- This round alone: −7 (the four size cuts −9, then +1 for the re-link guard and +1 for the departure log).
- Still 27 over the ≤ +10 target. The remaining cuts the review lists would change behaviour, and are not taken.
