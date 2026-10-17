# Slim Task 12c re-review 1 (fix round 1: 4fd7c9d..6c75533)

Scoped re-review, read-only. The code was read at `scratchpad/wt-vm3` (6c75533), and the tree was left clean. Mutations ran on a `git archive` copy (`scratchpad/rr12c`, since deleted). The fixed tests were also run against the 4fd7c9d library.

**Verdict: APPROVED.** There are 0 Critical and 0 Important findings, and 1 new Minor.

## Findings

| Finding | Status | Fails with the fix reverted? |
|---|---|---|
| I1: held-limit presence pinned | Addressed. `test_a_held_car_with_no_position_or_ble_is_present_for_a_cloud_provider` uses prefer_ble, no claim and no position, and checks the `held=False` negative. | Yes, when the held clause is dropped (only that test fails). It is a pin: it passes at 4fd7c9d, which already had the clause. |
| I2: 00 middle ground | Addressed as ruled. `TWCMaster.py:1331-1340`: 00 begins only when `pluggedCars()` is non-empty, meaning an unnamed car the fan-out reaches, not placed away, with a free plugged reading. With no such car, 00 ends an anonymous session. | Yes. Removing the begin fails `test_at_00_…`, and the test also fails at 4fd7c9d. Making the begin unconditional fails 3 tests, including `test_an_empty_twc_at_00_…`. Removing the away filter fails `test_an_empty_twc_at_00_…`. |
| M2: restart test independent of the sweep | Addressed. The test now asserts on the first `setPolicyLimit(70)`. | Yes. Reverting `_present` to `bool(api.atHome)` fails 4 tests, the restart test among them. |
| M1 / age-guard ruling | Addressed. `Targets.py:138-140`: an away fix no newer than `lastWrite("chargeLimit")` is no departure. | Yes. Removing the guard fails `test_an_away_fix_older_…`, and the test also fails at 4fd7c9d. The `<=` versus `<` boundary is unpinned; see N1. |
| M3: fakes and getattr | Addressed. `located()` calls `api.locate()` directly, and the three fakes gain `locate`. | n/a (refactor) |
| M4 | Unchanged, as ruled. Removing the `read` gate fails 3 tests. | n/a |
| M5 | Deferred to the Task 13 docs, as ruled. | n/a |
| M6 | Re-checked with the 00 rule; still bounded (see below). | n/a |
| M7: shared sweep | Done. `onDeparture` and the policy pass share `_restoreDeparted`. Removing the sweep fails 2 tests. Lib is +15 this round and +60 for 12c. That is acceptable for a live-failure fix, but it is growth to remember against the shrink budget. | n/a |

**`Targets.located` rename.** Used consistently. There is no `_located` left in `lib/` or `tests/`. It is used at `Targets.py:37` (`_present`), at `:66` (`broadcastVehicles`) and at `TWCSlave.py:112` (`pluggedCars`), imported at `TWCSlave.py:9`.

**Suites.** The four touched test files give 80 passed. `tests/unit` gives 1718 passed. `tests/unit` + `tests/EMS` + `test_pid_file_fallback` gives 1722 passed. All of these were run in wt-vm3. The report's 1727 passed / 1 xfailed was probably a different selection; the difference was not chased. The `test_registry_callers` git-grep test fails only in a non-git archive copy, so it is an environment artefact.

## New issue

### N1 (Minor): a retained TeslaMate redelivery stamped at our write time counts as stale

- **Where:** `Targets.py:139` (`fix.at <= write.at`) together with `Telemetry.py:274-276`. A retained value that differs from this source's last report, where that report predates our write, is stamped `min(now, write.at)`.
- **Scenario:** the MQTT broker connection drops while the held car drives away, then reconnects once the car is parked and asleep away from home. The retained away fix is stamped exactly `write.at`, so it is judged stale and there is no restore. With TeslaMate live, `onDeparture` does not read.
- **Impact:** the restore is delayed until the next live position publish, which is the next drive. If that drive is home, the restore is skipped, which is harmless. So it is a delay, not a permanent block.
- **Why `<=`:** it is the deliberate choice for a retained value that may genuinely predate the write. `<` would trade this case for the opposite one.
- **Pinning:** no test pins the boundary. Changing `<=` to `<` leaves all 80 tests green.
- **Fix:** none needed. Optionally, add a one-line comment saying that the equality is intentional (retained redelivery).

## Questions asked

### Can the age guard ever block a needed restore for good?

No.

- **Restart:** writes live only in the in-memory `FieldStore._writes`, so after a restart `lastWrite` is None and the guard is inactive. Behaviour is then the same as before the guard: a stale away fix restores, and a restore never wakes.
- **While running:** the guard holds only while no fix is newer than our last write. Every later non-retained publish is stamped now, and so is every paid `update_location` from `onDeparture` when telemetry is not live. Either one clears the guard.
- **Write loop:** a satisfied desire is cleared, and an absent car gets no new desire. So no write loop can keep re-arming the guard.
- **Remaining delay:** the only gap is N1's delay.

### Can the 00 rule start sessions repeatedly and cost a BLE wake each time?

No; it is bounded.

- **When a session begins and ends:** a begin needs `vehicleKey is None`. An end needs a free source to stop showing an at-home plugged car, for example TeslaMate going "Disconnected". So a re-begin follows a real replug as seen by TeslaMate.
- **Lift:** a session end at 00 does not reset `vehicleRateRaised`. Only the charging-end debounce or API control resets it. So the lift wakes at most once per charge cycle or restart, the same as main, which woke too.
- **Start:** the start desire is sent once per write. "Complete" satisfies it, and an offer below the minimum withdraws it. A start wakes only when a free source says "Stopped" and the policy offers at least the minimum. That is main parity.
- **Remaining fan-out:** the two VIN-less Gen2s case is listed as still open in the report. The per-desire caps bound it.
- **Note:** `pluggedCars()` runs on every 00 heartbeat for each idle Gen2. It does no I/O, but `located()` keeps M2's side effect of writing `atHome` from the serial thread. This was already noted and is not new.

## Live scenario at 6c75533

**Setup:** restart; the car is plugged in and asleep; the TWC VIN is unknown; the Gen2 shows 03 or 00; TeslaMate has the car at home with "Complete", limit 50 and SOC 51; heldLimits is (100, 50); commandPolicy is ble_only.

**Traced:**

1. **Presence.** `_present` → `located` → `CarApiVehicle.locate()` reads TeslaMate's position and finds it home, so the car is present. The sweep skips it because it is present.
2. **At 03.** The heartbeat begins `anon:8244`, as before.
3. **At 00.** `pluggedCars()` finds the VIN car: it is reached by the fan-out, not placed away, and TeslaMate says "Complete". So the session begins too.
4. **At 00:00.** `setPolicyLimit(70)` sets the 70 desire. The raise over the known 50 is allowed to wake, so BLE does a wake, then `setChargeLimit 70`, and the held limit becomes (100, 70).
5. **Lift.** The lift fires once per restart: a BLE wake, then `setAmps 32`.
6. **Start.** "Complete" satisfies the start. The car starts itself at 70 > 51; amps flow and the VIN merges.

**Probe.** A probe (scratch, deleted) covered both 03 and 00, with heartbeats before or after the policy pass. In each case it ran a Non-Scheduled 50, then a Scheduled 70, then the reconciler passes. All four variants:

- recorded `wake`, then `setChargeLimit 70`, plus one `wake`, `setAmps 32`
- ended with heldLimit (100, 70)
- made 0 HTTP requests under a catch-all `requests_mock`

When heartbeats run first, the lift's wake happens at restart time, as main's did.

**Live scenario works: yes.** Presence comes from TeslaMate's free position, so the 70 is desired on the first Scheduled pass. The raise is allowed to wake, and ble_only leaves BLE as the only candidate, so there are no Fleet or Owner requests. At 00 the session now begins from TeslaMate's at-home "Complete", so the lift and start reach the car there too.
