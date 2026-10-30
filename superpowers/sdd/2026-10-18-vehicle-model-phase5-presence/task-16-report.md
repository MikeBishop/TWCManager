# Task 16 report: an unmatched plug session ends only on a filtered unplug

Commit **b18262bf** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent 805c0e16). Not pushed. Box untouched.

## Change (`TWCMaster.observeChargingSessions`)

- Deleted the raw-00 anonymous close (`elif reportedState == 0 and isAnonKey(vehicleKey)` in the amps-below-threshold branch).
- An anonymous session now ends through `unplugStep` → `_plugSession(slave, False)`, like a named one: drop >0 → 0 on the first 00, 60 s debounce, plugged run, link grace, live-telemetry veto. The filtered unplug of an anonymous point departs the single `candidates()` car, as before. That is unchanged Task 4 behaviour: the raw close used to delete the placeholder first, so the filter's later firing reached the same candidates fallback.
- Fallback at the top of the loop:
  - `idle = zeroSince is None and not ampsMaxBefore` is computed *before* `unplugStep` mutates them. This is a 00 onset whose last non-00 heartbeat had max 0 A.
  - Then `elif idle and not reportedState and isAnonKey(vehicleKey)`: `anonEndedAt = now; _plugSession(False, depart=False)`, as the old close did.
  - Comment: "A car idle at 0 A leaves no drop to filter: its 00 ends it".
- Serial thread: attribute reads and comparisons only. No I/O, no blocking.
- `anonEndedAt` is set only on the fallback, so the flicker guard never suppresses attribution after a filtered real unplug followed by a quick re-plug. The `_plugSession` flicker comment now names the case that remains: a car idle at 0 A flickering 00 as it wakes.

## Tests

### New tests

Each was confirmed red on 805c0e16 except test 2. Test 2 is green on HEAD by design and red with the fallback removed.

1. `test_command_path_parity.py::test_box_2026_10_20_a_waking_00_keeps_the_plug_for_the_feed_to_name`, the box replay.
   - Setup: one car with TeslaMate, BLE and Fleet. TeslaMate's unplugged reading is 9,000 s old.
   - Plug: 03 at 0 A offered. BLE reads the car `Complete` at a 47 A pilot, so the pilot mismatch leaves the plug anonymous. This is an assumption: the box log doesn't say why the first attribution failed, and this is one way to reproduce the anonymous start. Then 09 at 6 A and 47 A, 03, then 00 at 47 A max for 14 s.
   - Expected: the anonymous session is still open. TeslaMate's plug-in triggers the retry, which names the car (`twcVin 8244`, `pluggedHere`). After 600 s more of 00 at 47 A it is still named.
   - No BLE wake; paid (0,0,0).
   - Red on HEAD at `vehicleKey None` after the 00. The log shows the same "not an unplug" line as the box.
2. `test_gen2_unplug.py::test_an_unnamed_car_idle_at_0_a_ends_its_session_at_the_first_00`. Max 0 A, then one 00: the session is gone and no unplug mark is made.
3. `test_gen2_unplug.py::test_an_unnamed_car_s_unplug_holds_a_minute_then_departs_the_only_car`.
   - At 50 s into the drop to 00 the session is still open. At 70 s it has ended, the only car has its unplug mark, and the log has "TWC 8244: unplugged, <VIN> departs".
4. `test_presence.py::test_live_telemetry_plugged_keeps_an_unnamed_session_through_an_unplug`. A live TeslaMate `pluggedIn True` vetoes the qualifying drop: the session stays, there is no unplug mark, and the log has "not an unplug, <VIN> is plugged in".
   - It sits in `test_presence.py` because the veto needs the TeslaMate attachment from `placed()`.

### Results

- `tests/unit` + `tests/EMS`: **2169 passed, 1 warning** (baseline 2165 + 4).
- `black --check` is clean on `TWCMaster.py`, `test_gen2_unplug.py`, `test_presence.py` and `test_command_path_parity.py`. I did not run black on `test_limit_wiring.py`, a legacy `;` file; the edits keep its style.

## Moved existing tests (old → new, reason)

`test_command_path_parity.py` is append-only (+32/−0). **No parity row's count or timing moved.**

Two tests changed in `test_limit_wiring.py`. Both are **INTENTIONALLY CHANGED** by the user's 2026-10-20 ruling:

- `test_a_vinless_gen2_after_a_restart_is_an_anonymous_plug_session`
  - Before: one 00 heartbeat (32 A → 0) inside the link grace → session gone.
  - Now: that 00 keeps the session ("a car waking says 00 too"). With the link aged (`heardFrom = 1`) and the 60 s debounce elapsed (`zeroSince -= UNPLUG_DEBOUNCE`), the filtered unplug ends it.
  - The "00 never begins one" line is kept.
- `test_only_a_plugged_state_begins_the_session_and_00_ends_it`: same rewrite. It also sets `pluggedSince = 1`, because this test's 03 run follows a 00, which restarts the plugged run.

The test edits age the TWC's timestamps instead of using a time-patched clock, because this file's harness runs on real `time.time`. That is plumbing.

## Lib delta

- `.py` lines: 26,336 → 26,336 (**net 0**; target about +3).
- `git diff --shortstat 805c0e16 -- lib`: 1 file, +7/−7, including the reworded flicker comment.

## Concerns

1. **The filter decides only at the 00 onset.** An unnamed car physically unplugged *during* a long resting 00 run with max > 0 (the box's 47 A case) leaves a session that nothing at the TWC ends.
   - The next car's 03 doesn't re-begin a session, because the key is not None.
   - `attributePlugs` skips the point, because its `plugIn` mark is more than 120 s old.
   - So on a VIN-less Gen2 with no telemetry feed, the next car is never attributed. The stale anonymous key also stays in `chargeGate` and the candidate fan-out.
   - HEAD's raw close prevented this.
   - Also: on HEAD, a waking flicker (00 → 03 within 60 s) re-began the session and so refreshed its `plugIn` mark, which restarted the 120 s retry window. Now the mark dates from the original plug only. A feed plug-in that arrives more than 120 s after the plug, but soon after a flicker, would have been named on HEAD and is not named now. The box case (31 s) is unaffected. Named cars already have the same gap (Task 4 concern 4). It follows from the ruling and doesn't affect the box, which has TeslaMate. A possible follow-up: a 00→non-00 edge after a long 00 run re-arms the session's `plugIn` mark, or ends and re-begins the session.
2. **A 00 inside the link grace, or after a short plugged run (< 60 s), with max > 0 before** no longer ends an anonymous session. That 00 can never qualify. Until a later qualifying run or a telemetry naming, the session lingers as in concern 1. Example: a restart with an unnamed car plugged in that is unplugged within 5 minutes.
3. An anonymous 00 with max > 0 now keeps `vehicleKey == anon:8244` at 00. So `chargeGate` may start that key and fan out to the candidates while the car rests. A named VIN car has no key at 00 (the PLUGGED_STATES gate in `Gen2TWC.vehicleKey`), so this exposure is new for anonymous points only.
   - No parity row moved. The box row asserts no wake and paid (0,0,0).
   - If it matters, a follow-up can apply the same PLUGGED_STATES gate to the anonymous key in `vehicleKey`.

---

# Fix round 1

Commit **3b28a9e6** "An unmatched point at 00 reports no car, like a named one" (parent b18262bf). Not pushed.

## Changes

- **I1: the box row's tail now exercises the system.** Before the 600 s tail:
  - the clock is aligned to a 30 s boundary;
  - `s.protocolVersion = 2`, so chargeGate is live;
  - the policy lambda sets a 32 A budget before each pass.

  The tail now runs reconcile and policy passes, and still gives no wake and paid (0,0,0). The row's 00 check is now `vehicleAt("8244").isAnonymous`, because the key is None at 00 after I2. With 805c0e16's lib (the raw-00 close), the row fails at that check.
- **I2: `Gen2TWC.vehicleKey` returns a key only in PLUGGED_STATES, for anonymous sessions too.**
  - The session stays in the registry.
  - The idle-at-0-A fallback reads `getattr(self.vehicleRegistry.vehicleAt(slaveTWC.twcid), "isAnonymous", False)`. The lookup runs only on an idle 00 onset.
  - The `isAnonKey` import is dropped from TWCMaster.
- **Side effect checked: `m.offered` at 00.** `anon:8244` no longer contributes candidate keys at 00. But a candidate plugged in here has its own VehicleEndpoint point, which keeps `offered[VIN] == 0`, so "nothing offered" (`Belief.whyQuiet`) still holds.
  - New row `test_an_unnamed_plug_at_00_wakes_no_candidate_for_a_raise`. Two cars at home, the plug left unnamed, car 1 reads Stopped with limit 80 over battery 50, and the TWC rests at 00 at 32 A. A policy raise to 90 for 600 s: no wake, paid (0,0,0). Its setup asserts `vehicleKey is None` and `offered[VIN] == 0` at 00.
- **The reviewer's probe as a row: `test_an_unnamed_plug_at_00_starts_no_candidate_as_the_offer_rises`.** Same setup; the budget rises 6 → 12 → 24 → 32 A during the 00 run.
  - Result: no `startCarsCharging`, no CHARGING desire, no BLE `charging-start`, paid (0,0,0).
  - **Red at b18262bf:** 18 starts of `anon:8244`.
  - The car's own VehicleEndpoint still rates it over BLE as the offer rises, as `wake, charging-set-amps` ×3. That is identical on 805c0e16 and not caused by this task. The row doesn't assert against it.
- **M2.**
  - `test_only_a_plugged_state_begins_the_session_and_00_ends_it` is renamed `…_and_a_held_unplug_ends_it`.
  - The ":324/:376" comments now read "no car at 00, the session kept: an unplug holds a minute", and those assertions are `vehicleKey is None` with the anonymous record still present.

## Moved existing tests (old → new, reason)

Parity rows: none moved. The parity file only gained rows: the 2 new ones, plus the box row's tail.

**INTENTIONALLY CHANGED (I2):**
- `test_gen2twc_provider.py::test_vehicle_key_keeps_the_confirmed_car_while_plugged_state`
  - Before: `anon:8244` was the key at 00.
  - Now: `None` at 00, and `anon:8244` once the TWC reports 03.
- `test_offer_characterization.py::test_a_twc_point_never_clears_a_vehicle_endpoints_rate`
  - Before: the anonymous point at 00 had key `anon:8244`, and its fan-out reached VIN at 20 A.
  - Now: the key is None at 00, and VIN's own VehicleEndpoint gives the same `(20, "distributor", False)`.
  - The test still pins that the unnamed point leaves VIN's distributor rate of 16 in place once the other TWC names VIN.
- `test_limit_wiring.py` (two tests, rewritten in round 0): at the first 00 the key is now None and the session is kept.

**PLUMBING-ONLY** (the tests built an anonymous session on a slave left at the default state 00, while the test meant a plugged or charging car):
- `test_amps_reconciler.py::anonTwc` sets `reportedState = 0x03`. This covers 3 tests.
- `test_charging_reconciler.py::test_non_tesla_car_on_a_twc_gets_the_disruptive_stop_at_once` sets 0x01 on both halves (the car draws 12 A).
- `test_charging_reconciler.py::test_a_rejected_twc_vin_falls_back_to_the_anonymous_session` sets 0x01 (a VIN is read while charging).
- `test_gen2twc_provider.py::test_amps_range_never_none_while_set_amps_ready` sets 0x03.
- `test_limit_wiring.py::test_present_rule`: the mode-2 stop slave 8245 is at 0x03.
- `test_gen2_unplug.py` and `test_presence.py`, round-0 tests: the "session kept" check reads the registry, not the key.

## Results

- tests/unit + tests/EMS: **2171 passed, 1 warning** (2165 + 6 new: 4 from round 0 + 2 here).
- `black` was run on the touched black-style files. The legacy `;` files (`test_amps_reconciler.py`, `test_charging_reconciler.py`, `test_limit_wiring.py`) were edited in their own style.

## Lib delta vs 805c0e16

- `.py` lines: 26,336 → **26,337 (+1)**.
- `git diff --shortstat 805c0e16 -- lib`: 2 files, +12/−11.

## Follow-ups (recorded, not built)

- **I3: a session left open after an unplug inside a 00 run.** The filter decides only at the 00 onset. An unnamed car unplugged during a long resting 00 at max > 0 leaves the session open:
  - the next car's 03 doesn't re-begin it;
  - `attributePlugs` skips the point, because its `plugIn` mark is more than 120 s old;
  - on a VIN-less Gen2 with no feed, the next car is never attributed.

  A waking flicker also no longer refreshes the `plugIn` mark. A candidate fix: on a 00 → non-00 edge after a long 00 run, refresh the session's `plugIn` mark, or end and re-begin the session.
- **M1: grace and short runs.** A 00 inside the 300 s link grace, or after a plugged run under 60 s, with max > 0 before, never qualifies. The anonymous session then lingers as in I3. Example: a restart with an unnamed car plugged in that is unplugged within 5 minutes.
- Round 0's concern 3 is resolved by I2. The anonymous key no longer reaches chargeGate at 00.
