# Phase 5 final review: presence from events (044e5262..207f98c5)

Reviewer: Fable (whole-branch). Checkout `scratchpad/wt-vm5`, read-only. 30 commits, 113 files, +4,404/−2,119. Lib 26,531 → 26,198 (verified: `git ls-files lib | grep '\.py$' | xargs cat | wc -l` = 26,198).

Reviewed in passes: lib by package (Reconcile, Registry, Presence, TeslaBLE/TeslaAPI/HA/Telemetry, Control + EVSEInstance, Providers, top-level TWCMaster/TWCSlave/TWCManager), then tests (parity non-append hunks, `test_presence.py`, `test_gen2_unplug.py`, `test_paid_logging.py`, page tests), then docs and CHANGELOG. Each ledger Ruling was checked against the code (list under Plan alignment).

Verification run here, not taken from the reports:
- `tests/unit tests/EMS`: **2093 passed**, 1 warning (41.7 s).
- `black --check lib`: clean. No 3.9+ syntax in the lib diff (grep for `list[`, `dict[`, `:=`, `removeprefix`, `X | None`).
- Comment rule grep over added lib lines (phase/PR/ruling IDs, "used to", "no longer", "previously"): no hits beyond one semantic use of "no longer at" in a docstring.
- Removed-name grep (`vehicleScheduledChargingPending|checkArrival|checkDeparture|is_location_home|update_location|locate|located|broadcastVehicles|_present|vehicleIsDefinitelyHome|at_home|_scheduleBlocksStart|pluggedCars|anonymousCars|CORRELATE_WINDOW|_telemetryPluggedIn|summaries|Declaration`): only the kept `checkDeparture` task, a log string, the parity `located=` fixture keyword, the 404 test, and one stale docs line (Minor 8).
- Two throwaway probe tests (run from `tests/unit`, deleted afterwards; tree verified clean) confirmed Important 1 and Important 2(a) below.

## Strengths

- **Presence is small and legible.** `Presence.decide` returns (state, deciding event, time) from marks and the newest fix; the rules in the plan map one-to-one onto code, and the "why" string feeds both logs and the Vehicles page. There is no presence state machine, no tick pass and no polling.
- **One applicability rule, applied where the read already happened.** `Reconciler.inapplicable` runs in `beforeWrite` after the attempt's read; `Run.runAttempt` refuses to wake a NOT_HOME car before the paid wake; restores and stops are exempt exactly as ruled; charging-point commands (`provider.module is None`) are exempt as ruled (T4-S12).
- **Money is counted by what was actually sent.** `TeslaAPI._request` classifies paid requests by slot and path; `Vehicle.paidRequests` feeds `Attempt.paidBefore`/`noteOutcome(spent=…)`, so a hold charges its wake and read to the desire's budget and nothing else. The paid log line carries only token type, endpoint and price.
- **Parity discipline held.** The non-append hunks in `test_command_path_parity.py` are the seven fixture changes listed in the PR notes, and no existing row's counts moved. The new rows are real end-to-end scenarios on real objects (master, registry, reconciler, TeslaAPI with `requests_mock`, TeslaBLE with only the tool run stubbed), including the box episodes (13:08 departure, 15:18→15:21 arrival, the 47 A false 00, the 07:58–08:39 wake table) and the loop rows.
- **The Gen2 unplug rule is evidence-based and tiny.** `TWCSlave.unplugStep` is 16 lines on the serial thread with no I/O, logs every onset with the max-amps before/after, and the filter-(b) veto sits beside the session end in `_plugSession`.
- **Thread discipline is kept.** The observe hook runs after the store and outside both leaf locks; marks are max-merged under the vehicle lock; `onArrival` takes Desired then settings; `_plugSession` still catches everything on the serial thread; the Vehicles page reads reconciler state through `peek`/`said` without creating entries; `settingsLock` is never held across file I/O (checked `saveSettings`).
- **The size pass was real.** The three package `__init__` re-exports, `FieldStore`, `Declaration`, dead `setAmps`, `decision()/settled()`, `_readFresh`, the three VIN-key lookups and the `summary` field view are gone; the import style change lost no readability. Lib shrank 333 lines while adding presence, holds, the ping, attribution and the page work.

## Issues

### Critical (Must Fix)

None found.

### Important (Should Fix)

**1. A car whose live telemetry says unplugged is still attributed to a VIN-less plug, and the naming then overrides that reading.**
`lib/TWCManager/Vehicle/Presence.py:302-334` (`pick`), `:337-347` (`attribute`), `:140-154` (`pluggedNow`).
`pick()` consults plug evidence from TeslaBLE only (`fits` reads `_BLE_CHARGE`); a TeslaMate/Fleet-Telemetry `pluggedIn False` on a HOME car is never looked at, so the car survives into `left` and wins through `_reached` or `inside` as the single candidate. `attribute` then writes `twcVin` and `pluggedIn True`, and `pluggedNow` returns True from the naming, so `onArrival` applies the policy limit, a `VehicleEndpoint` appears (rate commands, paid on Fleet-only), and a start would wake the car. Probe (real master, TeslaMate `state online`/`pluggedIn False`, unnamed Gen2 at 03, `attributePlug` run): `twcVin == "8244"`, `pluggedNow is True`. The same household then sees the T12 unplug depart that car and restore its limit when the guest unplugs.
Why it matters: the spec's anti-goal is a charge or limit command to a car not plugged in here, and the one source that says so plainly is ignored. It is the mirror image of filter (b), which the unplug side does honour.
Fix: in `fits`, return False when the car's live feed says unplugged (`v.syncSource in TELEMETRY_SOURCES and v.value("pluggedIn") is False`, the complement of `telemetrySaysPlugged`), and likewise for any plug reading from a qualifying source stamped after the anonymous session began that maps to unplugged. Do not use a bare `pluggedNow(...) is False`: the Gen2TWC `pluggedIn False` from the previous unplug would then block the returning-car row (`test_a_returning_car_on_an_unnamed_gen2_asleep_starts_over_ble`). Add one test beside `test_two_candidates_attributed_by_ble_pilot`.

**2. `learnHome` neither guards against a stale GPS fix nor runs for a TWC-named car once home is set; the docs and CHANGELOG promise both.**
`lib/TWCManager/Vehicle/Presence.py:107-115` (lat/lon branch), `:355-370` (`learnHome`); `lib/TWCManager/Vehicle/TeslaAPI.py:1824-1836` (lat/lon observed with the read's stamp, `gpsAsOf` separately); `lib/TWCManager/Vehicle/Providers/TeslaBLEProvider.py:38-49` (same for BLE).
(a) `learnHome` tests `now - lat.at > HOME_FIX_MAX_AGE`, but `lat.at` is when the reading was stored, not when the fix was taken. A fresh read carrying an hours-old `gps_as_of` (GPS cold start after a wake, a frozen GPS, which is the documented reason BASE's `vehicleIsDefinitelyHome` checked `gpsAsOf > 600`) passes the guard, so a position kilometres away moves home and makes every car Away. Probe (BLE-sourced lat/lon with `gpsAsOf` 5 h old): home moved 0.2°. Plan (f) and the inventory's R20 both say "fix under 600 s old by its `gpsAsOf`". Today only a BLE location read reaches this path (nothing in lib reads `lat` through the cascade since `update_location` went; the Settings page sets home from the browser), so it is latent, but it is the next `read("lat")` away.
(b) For the TWC-named case, lines 111-112 mark `outside` first; `twcVinAt` then sees that mark newer than the naming and returns NEVER, so line 114 never calls `learnHome` when the fix is outside the radius, which is the only case where home could move. The TWC path therefore only seeds an unset home (which the tests cover) and never moves one. `test_home_is_learned_only_from_a_twc_named_car_with_a_fresh_fix` calls `learnHome` directly and so does not see this.
Fix: compute `named = twcVinAt(...) > NEVER` before marking `outside`; in `learnHome`, when the same source reported `gpsAsOf` at or after the fix, require `now - gpsAsOf <= HOME_FIX_MAX_AGE` (TeslaAPI and BLE both store it). Then either wire the TWC move (and add a test through `noteObservation`) or drop the "a car a TWC names" clause from CHANGELOG, `docs/Settings.md` and `docs/PolicyCustomization.md` so the text matches the code.

### Minor (Nice to Have)

**3. Unattributed anonymous sessions flap, re-running attribution and BLE reads.** `lib/TWCManager/TWCMaster.py:1287-1356` (`observeChargingSessions`), `:1486-1510` (`_plugSession`). While a VIN-less TWC's plug stays ambiguous, every 03→00→03 flicker (the waking pattern in the evidence table) ends the anonymous session at the first 00 heartbeat and opens a new one at the next 03, queueing `attributePlug` again; `pick(read=True)` then runs a forced `tesla-control state charge` for each BLE-claimed candidate on the background thread, and each end logs `TWC 8244: unplugged, anon:8244 departs` and observes `pluggedIn False` on the anonymous vehicle. Suggest: skip the departure log and observe for an anonymous vehicle, and rate-limit attribution per point (the BLE read is the expensive part). The ambiguity-once test holds only because its TWC never flaps.

**4. The link grace is not re-armed on a re-link.** `lib/TWCManager/TWCSlave.py:120-134`, `lib/TWCManager/TWCMaster.py:1261-1265`. `LINK_GRACE` is measured from `heardFrom`, the slave's first heartbeat ever; a re-link through `newSlave` on an existing slave resets only `pluggedSince`, so the 00 after a TWC power-cycle gets the 60 s `PLUGGED_RUN` guard, not the 300 s the plan specified "after a (re)link". The evidence's grace hits were all after restarts (new slave objects), so the deployed risk is small; set `heardFrom = 0` beside `pluggedSince` in the re-link branch and add a row to `test_a_re_link_starts_a_new_plugged_run`.

**5. The ping's range scan runs outside `_bleLock`.** `lib/TWCManager/Vehicle/TeslaBLE.py:631-636` (`_runPing`), `:1007` (comment: scans run under `_bleLock` on the background thread), `:1020-1076`. `_tool` is serialized but `scanForVehicleInRange` is called after it returns, on the BLE worker, while the background thread's `runPendingScans` may be scanning under the lock: two `bluetoothctl scan on` processes at once and unsynchronised writes to `_rangeScan`. Make `_runPing` `@_serialized` (dropping the decorator from the inner call) or take the lock around the scan.

**6. `Vehicle.paidRequests += 1` is unsynchronised.** `lib/TWCManager/Vehicle/TeslaAPI.py:342-345`. The cloud worker and the background thread (`updateChargeAtHome`, the departure reads) both increment it; a lost increment undercounts a hold's `paidSpent` by one. Advisory budget, so low impact; a lock or `itertools.count` would make it exact.

**7. Presence recomputed twice per tick for anonymous points.** `lib/TWCManager/TWCMaster.py:662-663`. `self.offered` is built from `p._carKeys()`, which for an anonymous Gen2 runs `candidates(master, SET_AMPS)` plus `pluggedHere` over every car, after the distributor already called `_carKeys` for the same pass; it also reaches into a private method from another class. Have `ChargingPoint` expose the keys it rated this pass (it already keeps `_lastKeys`).

**8. Two doc inaccuracies.** `docs/PolicyCustomization.md:53-54` says "a paid Tesla API read is never needed to place a car"; under (b) a Probably-home car with a message is woken and read on the Fleet path (`test_presumed_fleet_only_car_gets_the_limit_through_the_paid_sequence` pays (1, 1, 1)). Say "to place a car that has no message pending" or state the paid sequence. `docs/modules/Vehicle_HomeAssistant.md:88` still lists `lat`, `lon` and `at_home` as kept per vehicle; only `battery_level` is.

**9. The "RELEASE/NOT_HERE churn" residual is unconfirmed.** `pr-notes.md:39`, `docs/PolicyCustomization.md:96-97`. `applyPolicyLimit` iterates `presentVehicles`, which excludes NOT_HOME cars, and `_restoreDeparted` sets a restore, not RELEASE, so I could not construct the churn either; the ledger says it was not reproduced. Either reproduce it or drop the sentence rather than warn users about a line that may not exist.

**10. Size against plan.** `Presence.py` is 370 lines against the plan's ≈225 after Task 5; lib ends 58 above the 26,140 target (documented). No dead code found. Residual duplication: the "single remaining candidate" rule appears in `pick` (the rich form) and again in `_plugSession`'s end branch (`cars = candidates(self) …; v = cars[0] if len(cars) == 1`), 3 lines; `homeForLimits` is a one-line alias used in five places. Not worth a change now.

## Declined to judge

- A single outside GPS fix on a car its TWC currently names (03, VIN read) makes it NOT_HOME and blocks car-addressed start/amps while power still flows through the point: ruled F2 (an outside fix overrides the naming).
- A held car with no plug reading is "presumed plugged" for a start or rate: ruled F20 and T4-S12.
- Charging-point commands (Gen2/Gen3 start, stop, amps) are never gated by presence: ruled T4-S12.
- The single-candidate guess with no plug evidence at all (no telemetry, no BLE read): inventory T9 KEEP and F12; only the live-telemetry-unplugged variant is raised (Important 1).
- A Probably-home car with a raise is woken and read on the paid path: allowed change (b).
- A car-only install with no home set is never applied: ruled T2-I2, documented.
- A BLE `state charge` read in the read-before-write may wake a sleeping car: Phase 3/4 behaviour, not changed here.
- The away-car `statusDeferral` ladder, `updateChargeAtHome` at power start, the broadcast audience and HA's on-a-TWC rule: kept per F11.
- An idle Gen2 car at 0 A whose unplug only telemetry can see: ruled F6.
- The 5/20/45-minute departure reads now use `READ_MAX_AGE` rather than a forced read: per plan Task 2.
- `vehicles[0]` fan-out removed and the hint endpoints returning 404: allowed changes (h) and (d).
- Every reconciler outcome at INFO (log volume): allowed change (m).
- `onArrival` and `learnHome` running on the serial thread from `recordVehicleVIN` (Desired lock, `settingsLock`, two queued tasks): dict work only, `settingsLock` is never held across file I/O; noted, not an issue.

## Plan alignment

- Rulings implemented as ruled: F1 (unplug mark only on a plugged→unplugged transition or a Gen2TWC write), F2 (`twcVinAt` bound and the per-point clear in `observeTwcVin`), F3 (`heldAt`, `paidSpent`, re-plan on `lastObservedAt`, `PAID_BUDGET`; refined to "requests actually made"), F4 (NEVER, parked = not driving without a gear), F5 (`b.pings`), F6 (strict filter (a) and the raise-loop row), F7, F8 (ties hold), F9 (absence only from a scan miss; an unanswered ping without a scan is None, not absence), F10, F11 (ladder, HA rule, `lastAtHome`, audience via `candidates(capability)`), F12 (the 120 s rule in `pick`), F13, F14 (paid by slot and path; separate arrival hook), F16 (the three deletions), F17/F18 (rename, test fates), F20. T2-Q2 (`departed()` time against `lastWrite`), T2-I2 (one WARNING), the 2026-10-19 rulings (restore SEND everywhere, RELEASE applied like a limit with wake by direction, no wake while offered 0 A), T4-S12, T4-narrow, T5-probe, the audit tiers and order, Task 6's page scope.
- Carried items closed: Task 4 Minor 4 (cars another point names are out of the fallback: `candidates` and `test_a_vinless_unplug_never_departs_a_car_another_twc_names`), Task 3 parked (b) (anonymous fan-out cars appear in `offered`), Task 5 C1/I1 (no BLE from the vitals; a Gen2 plug counts only while named).
- Deviations: Important 2 (the (f) stale-fix bound and the TWC move), Minor 4 (grace after a re-link), and `pick`'s reached/inside fallback being broader than F12's 120 s rule (per T9; acceptable). Size target missed by 58 (documented).

## Recommendations

1. Fix Important 1 and 2 before merge; both are small and each gets one test through `noteObservation`/`attribute` rather than the helper.
2. Take Minor 3 and 5 with them if time allows: both are about repeated BLE work on live hardware.
3. Correct the two doc lines (Minor 8) and decide on the residual (Minor 9) in the same docs commit.
4. After deploy, watch the `00 onset` lines and `no single car plugged in` frequency on the box for a day; the n=2 caveat in the PR notes is honest and the onset log is what will prove or tune filter (a).

## Assessment

**Ready to merge?** With fixes

**Reasoning:** The port is faithful to the rulings, thread-safe, and verified by real end-to-end rows, but attribution ignores a live feed that says the car is unplugged, and the home-learning path lacks the stale-fix bound the plan required while the docs claim a move it never makes.
