# Restack onto bd5a7603: independent review

Verdict: **fix first** (three small fixes; nothing structural). Everything else checks out.

Suites rerun in detached worktrees (brief's command): restack2/phase1 1353 passed, 1 xfailed; phase3 1905 passed, 1 xfailed; phase3.5 1876 passed, 1 xfailed. These match the report.

## Findings, ranked

1. **CHANGELOG says #667 twice from Phase 3 on.** See restack2/phase3 CHANGELOG.md:36 vs :100-101, and every later tip. Phase 3's Architecture line ends "(closes #667)". Main's two Bugfix lines are kept beside it: "Cancel a pending stop… (closes #667)" and "Queue charge start/stop commands per vehicle and send at most one per vehicle per minute". The second line describes the queue that Phase 3 deletes. The brief asked to merge overlaps. Phase 1 and 2 did this; Phase 3 did not.
   - Fix: in the commit that deletes the legacy charge path (a6389ecd, "Start and stop charging as desired state…"), fold main's two lines into the Architecture line, or drop one "(closes #667)".
   - Also, the Architecture line lists "Fleet API, Home Assistant" as the paid providers. From Phase 2/3 the Owner API commands at that tier too.

2. **The interim Owner port's "asleep car is not charging" rule is still Fleet-only.** See restack2/phase3 lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:107, which still tests `self.carapi.slotFor("command") is not None`. Owner-only installs never satisfy it.
   - Effect: in Phase 3, an off car that is asleep gets a free charge_stop over the Owner API, which ends UNREACHABLE (408). There is no wake (allowWake never wakes for a stop) and no money is spent.
   - Main short-circuits this case.
   - The report says this rule "uses commandSlotFor". It does not.
   - Fix: `self.carapi.commandSlotFor(car) is not None` in the commit that moved the command methods into `_TeslaAPIProvider`. Phase 3.5 already does the right thing (`canCommand` at :113).

3. **Two of #702's tests disappear at 3.5 without a committed replacement:** `test_read_pause_does_not_block_owner_commands` and `test_cleared_owner_slot_blocks`.
   - Phase 3 ported them. 3.5 takes its own test file whole, and the report checked these behaviours only with uncommitted probes.
   - The behaviour itself holds: `ownerTokenHeld` ignores the read pause, and a cleared slot means `canCommand` is False with no HTTP call.
   - Fix: add both to restack2/phase3.5 tests/unit/test_teslaapi_readonly_gate.py (`TestOffCarCommandsThroughOwner`) in 815ac1f2.

4. **3.5 puts the Owner API ahead of Fleet for off cars.** This is a design difference that a maintainer is likely to raise. See restack2/phase3.5 TeslaAPIProviders.py:143/188 (rank 4 vs 5) and CHANGELOG.md:99.
   - Main's #702 says "Fleet first, so a working Fleet (and proxy) setup is unchanged".
   - What a user sees: someone with Fleet plus the proxy and a TeslaMate-synced Owner token, with a `command_signing: off` car (older S/X), now has commands go over the Owner API. Fleet gets them only after an Owner refusal, in the same round. This saves billed calls.
   - The visible cost: if Tesla refuses Owner commands (410/412), the user gets an ERROR line, "Tesla no longer accepts Owner API commands … Charge commands need a Fleet API token with the Vehicle Command proxy…". That is wrong for them, because Fleet works. They get it again, plus one refused call, every time the synced token changes (TeslaAPI.py:1407 `noteOwnerCommandsRetired`). On main this user never sees an Owner call or that line.
   - Not a correctness regression, but it reverses a stated #702 promise.
   - Suggest: when the Fleet slot commands, word the line as "using the Fleet API" (and log at WARNING/INFO), or rank Owner after Fleet.

5. **3.5 retires Owner commands for the whole slot on 410/412.** A design difference, not a regression.
   - Main: latches only the one car and logs a WARNING per car; the latch lasts until restart. Other off cars each spend one refused call before they latch.
   - 3.5: one ERROR line, every car stops at once, and the latch lifts when the token is entered or synced again (an unchanged resync keeps it, TeslaAPI.py:1173).
   - What users see: fewer refused calls and one line instead of N. The level goes up from WARNING to ERROR, which the report didn't mention. After a token change Owner commands are retried once, where main never retries.
   - It is documented in docs/modules/Vehicle_TeslaAPI.md:171. The CHANGELOG #659 line covers only the ordering, not the retirement, which the report says it covers.

6. **Phase 1 wording (nit).** See restack2/phase1 commit c418c653 and VehicleCommandQueue.py:9-13. Both say "None as the distinct 'all vehicles' target", then say that charge commands with None overlap per-car ones. Say that None is distinct for applyChargeLimit only.

7. **Interim Owner pacing differs from main (info).** In Phases 2–3, Owner commands run at `OWNER_COMMAND` (billed tier, cost 0).
   - With BLE configured, an off car's command goes over the Owner API only after the free channel has failed for 60 s (start/stop, amps) or 300 s (limit).
   - Each desire gets at most 4 sends.
   - Main's VehiclePriority fell through to the Owner API in the same call. This matches 3.5's design, so it is consistent, but it isn't called out as a difference.

## Verified

- **Phase 1 queue.** For charge commands, `_key`, `_replaces`, the `CHARGE_COMMAND_INTERVAL` gate at `put()`, and the `_lastChargeTime` stamp in `_next()` match main exactly. "" counts as None.
  - `cancel()` skips `_high` while draining, so no stop is cancelled during shutdown.
  - `cancelStopCarsCharging(vin)` covers the car's own stops and vehicle-less stops; with no vin it covers every stop.
  - TWCSlave passes `currentVIN` at both call sites.
  - Dropping Phase 1's explicit start-cancel in `stopCarsCharging` is safe. A pending start can only exist if it was put after the interval. With no intervening overlapping dispatch, a later stop is also past the interval, so it replaces the start.
  - Main's TestPerVehicleCharge, TestCancelStop and TestChargeInterval are present and meaningful, using a real queue, a blocked worker and a monkeypatched clock. `test_stop_replaces_pending_vehicleless_start` and `test_start_replaces_pending_stop` are covered by `test_stop_for_one_car_replaces_a_vehicleless_start` and `test_vehicleless_start_replaces_every_pending_stop`.
  - No Phase 1 test was lost except `test_none_vin_is_distinct_from_named_vin`, deliberately inverted. Main's #702 gate tests are all present in Phase 1 and 2.
- **Phase 2/3 interim.** Commands are never sent twice.
  - `OwnerAPIProvider.available` requires the Fleet slot not to command; `FleetAPIProvider.ready` requires it to. They are mutually exclusive, and both send through `commandSlotFor`.
  - With both tokens Fleet carries the commands, as on main.
  - Owner wakes happen only for off cars, as on main (`wakeVehicle` used `commandSlotFor`). Fleet's 403 wake latch is not applied to the Owner slot.
  - No new Fleet or paid path.
  - Refusal latch and log levels match main: WARNING per car; INFO read-only line once per state change.
- **Phase 3 guarantees.** The named tests exist and pass on restack2/phase3 (7 reconciler tests and TestChargeStartStopCancelRules, 5 tests). `RETRY[CHARGING] = 60.0` gates re-sends after an outcome (Reconciler.py:70, :262).
- **Range-diffs.** No stack test was deleted at any phase; old vs new test-name sets differ only by additions. Commit messages are unchanged except c418c653 (accurate apart from #6) and 3.5's CHANGELOG hunk. Docker: one nsenter/setsid runner at every tip, and Phase 6 changes only the Dockerfile vs main.
- **Python 3.8.** All of phase6 `lib/` parses with `feature_version=(3,8)`. The only PEP 585 generics are main's own Gen3TWCs.py, under `from __future__ import annotations`.
- **Scrub.** No restack2 tip (phase1–6, 707) contains the car name. History contains it only as removal lines of main's pre-existing test file in fa65c4e1. reconcile_helpers HOME is the placeholder at every tip that has it. The original latitude appears in no restack2 patch.
