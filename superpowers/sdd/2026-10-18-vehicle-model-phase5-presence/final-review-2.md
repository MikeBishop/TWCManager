# Phase 5 final review #2: presence port with the Vehicles tab (vehicle-model/phase4..vehicle-model/phase5, tip 52a2652c)

Reviewer: Fable (whole branch). Checkout `scratchpad/wt-vm5`, read-only, tree clean. 20 commits, 122 files, +6,886/−2,410; lib 26,531 → 26,413 (verified: `git ls-files lib | grep '\.py$' | xargs cat | wc -l`).

Verification run here, not taken from the reports:
- `tests/unit tests/EMS` in a fresh venv (requirements + requirements-test): **2232 passed**, 1 warning (46 s).
- `black --check lib`: clean. Lib diff has no 3.9+ syntax (the one `:=` in `Presence.attribute` is 3.8).
- Comment rule grep over added lib lines (phase/task/PR/ruling IDs, "used to", "no longer", "previously", "formerly", "before,", "instead of"): one semantic hit (`Rules.py` docstring, "a held limit the car is no longer at"), nothing historical.
- Removed-name grep over lib and docs (`checkArrival|checkDeparture|update_location|at_home|vehicleIsDefinitelyHome|LINK_GRACE|unplugStep|UNPLUG_DEBOUNCE|anonEndedAt|pluggedCars|anonymousCars|CORRELATE_WINDOW|summaries|Declaration`): only the CHANGELOG lines that announce the removals.
- Two throwaway probes in the scratchpad (not in the tree) confirm Important 1 and Important 2 below; both reproduce on real master, registry, reconciler and TeslaAPI with `requests_mock`, as the parity rows do.

The first final review's findings were re-checked against the final code: Important 1 (telemetry-unplugged attribution) is fixed and now bounded by the session's `since`; Important 2(a) (gpsAsOf dating) is fixed; Minors 3 and 4 were superseded when Task 19 replaced the unplug filters with "check the car"; Minors 6, 7, 8 and 10 are fixed; Minor 9 (the RELEASE/NOT_HERE residual) is still documented and still unconfirmed (Minor 7 below).

## Verdict

**Ready with fixes.** One cheap ruling violation (a retained telemetry position can move home at a VIN read) and one documented promise the Fleet-only path does not keep (a car known asleep still gets paid commands) should be settled before the PR opens; the second needs a user ruling because either the code or the docs must change, and the code change moves a parity count. Everything else is minor.

## Strengths (what the per-task reviews could not see as a whole)

- **One presence, read everywhere.** `Presence.decide` is the single source for the Vehicles page, `applicable`, `whyQuiet`, `candidates`, `homeCars`, `pluggedHere` and the TeslaAPI `numCarsAtHome`/`minBatteryLevelAtHome`. No cached `atHome` is left anywhere; the only cross-component state is the in-memory marks, and they are max-merged under the vehicle lock.
- **Every wake has one gate.** `B.whyQuiet` decides "expected to charge" once per plan; `Run.runAttempt` cannot wake without `attempt.wake`; restores and stops set `wake=False` at plan time, and `inapplicable` exempts them. I traced every path to `provider.wake`, `wake_up` and `vehicle_data`: the Fleet `fetch` always runs the free online check first; `checkPlug` bypasses the deferral and the 120 s cache with `staleBefore` but still reads only an awake car; `pick` pings before any BLE charge read and never reads a car known asleep; Gen3 `_correlate` passes no offer, so it never reads BLE on the vitals thread.
- **The status-edge check is a serial-thread state machine with no I/O.** `TWCSlave.plugCheckDue` is 20 lines; the check itself runs on the BLE worker as a `Job`, coalesced per TWC; `_plugSession` on that worker ends the session only when every candidate reads unplugged. "Nothing can check → no unplug" holds: an HA-only car gives `None`, as does a Fleet car whose online check says asleep.
- **Threads and locks.** Serial thread: `plugCheckDue`, `_plugSession(begin)`, `attributePlugs`, `recordVehicleVIN` → `learnHome`/`onArrival` (settings dict work, no I/O). BLE worker: scans (`_scanRequested`), attribution, plug checks. MQTT thread: `noteObservation` → `_restoreDeparted`, `attributePlugs()` (a submit only). Lock order holds: `scanForVehicleInRange` is `@_serialized` and `_noteScan` takes `settingsLock` inside it; `_noteBleProof` observes `bleReach` under `_bleLock`, and that hook only marks; the ping's `_tool` releases `_bleLock` before `scanForVehicleInRange` retakes it. `Reconciler.pass_` holds no lock across `applicable` (which takes `settingsLock` through `holding()`).
- **Restart.** A persisted held limit plus a retained TeslaMate limit settles without a send; a retained position outside places the car Away and the first policy pass restores it (`lastWrite` is gone, so the `<=` guard does not block); a retained `asleep` state is sleep evidence but never life; a Gen2 attribution at restart marks `plugIn` but not `lifeAt`; `settleUntil` holds wakes until each feed has reported. `UNDECIDED` keeps `onArrival` from releasing a held car before the first policy pass.
- **Fleet Telemetry.** Converters take the typed forms only (`int(float())`, prefixed enums sliced by their exact prefix lengths: `DetailedChargeState` 19, `FastCharger` 11, `CableType` 9); `Location` is a dict; Gear sets only the sync state; `REQUIRED` derives to exactly the nine fields the doc lists. `checkConfigs` runs on the background thread, through a dedicated `_request` purpose that cannot latch or back off the Fleet read slot, and the claim doubles as the warn-once state.
- **Docs match the code** on every rule I checked (the 20 s wait, once per event, every 00 at 0 A, feed-then-BLE-then-API, "a Gen2 plug counts only while the TWC reports one", probably-home counted in the policy properties, home seeding cases, the 404s, the dropped 5/20/45 reads), with the one exception in Important 2.

## Findings

### Critical

None.

### Important

**1. A retained telemetry position moves home at a VIN read.**
`lib/TWCManager/Vehicle/Presence.py:442-460` (`learnHome`), `lib/TWCManager/TWCMaster.py:1588-1592` (`recordVehicleVIN` passes `vehicle.latest("lat")`, `latest("lon")`).
Ruling (user 2026-10-19): "home moves only on a fresh position read (TWC reads the VIN, or BLE fix; fix < 10 min by its own GPS time)". TeslaMate has no GPS time, so `learnHome` falls back to the reading's own stamp; a retained `latitude`/`longitude` redelivered at startup or on an MQTT reconnect is stored `seen=False` with `at=now` (`Telemetry._observe`), so it passes the 600 s bound although it is a copy of whatever TeslaMate last published, not a read.
Scenario: restart with the car charging on a VIN-reading Gen2 while TeslaMate's retained position is stale or frozen (the 2019 GPS-freeze case that motivated the bound) and more than 1,000 ft from home. `recordVehicleVIN` → `learnHome` → home moves there; every car becomes Away; held limits restore; nothing is applied until home is reset by hand.
Probe (real master, `home()`, slave at 03 with `currentVIN`, `observe("lat"/"lon", AWAY, "TeslaMateVehicle", seen=False)`, `recordVehicleVIN`): `getHomeLatLon()` → `[40.0, -86.0]`.
Low frequency, high impact, one line.
Fix: in `learnHome`, `if lat is None or lon is None or not (lat.seen and lon.seen): return False` (a copy is never a fix). Optionally pair the coordinates by source in `recordVehicleVIN` (`vehicle.reported("lon").get(lat.source)`), which T2-loc asked for. One test through `recordVehicleVIN` with a `seen=False` position, beside `test_a_fresh_fix_outside_moves_home_when_a_twc_reads_the_cars_vin`.

**2. A Fleet-only car its own online check found asleep still gets paid commands; the docs say nothing runs.**
`lib/TWCManager/Vehicle/Reconcile/Run.py:157-164` (`quiet = ble and …`; the `ASLEEP` hold is BLE-only), `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:35-50` (the read's free online check), `:65-100` (`setChargeLimit`/`setAmps` post without an online gate; only `stopCharging` has one). CHANGELOG.md:25 ("While the car is known asleep nothing is run, until a sign of life") and `docs/modules/Vehicle_TeslaBLE.md:69` ("A Fleet API online check that finds the car asleep counts too") promise a general rule; the code applies it to BLE attempts only. For a Fleet attempt the free check runs inside the read, observes `state asleep` (so `Presence.asleep` is True) and the paid `set_charge_limit` is posted anyway, answered 408, then blind-retried.
Probe (Fleet-only, asleep, policy 90 → 70 with battery 80, one hour of heartbeat and feed noise): `paid == (0, 0, 2)`. The same shape is pinned by parity row 18 (`test_fleet_only_failed_remote_restore_is_retried_per_restore_retry`, `(0, 0, 2)`), carried from Phase 4 under F20.
Cost: $0.002 per lowering or restore to a sleeping Fleet-only car, plus up to two more after a re-arm; bounded by the paid budget, so not a loop, but the request is made to a car we already know cannot take it.
Fix, either of:
- (a) Code, ~4 lines: in `runAttempt`, after the read, for a non-local provider with `not attempt.wake and not isStop(attempt)` and `Presence.asleep(vehicle)` True, return `O.Outcome(O.UNREACHABLE, "asleep")` with `"asleep"` added to `NOT_SENT`. The existing RETRY cadence then re-checks for free (the online GET is cached 120 s) and the paid command goes only once the check finds the car online. Parity row 18 moves to `(0, 0, 0)` and must be listed for the user (F4). Caveat: an away Fleet-only car with no telemetry then gets a free online GET every 5 minutes until it wakes, where today it gets two paid posts and then waits for a reading; that polling belongs to the vehicle-watch follow-up, so the controller may prefer (b) now and (a) with Phase 6.
- (b) Docs, 2 sentences: qualify the CHANGELOG and TeslaBLE lines so the no-run rule is stated for BLE commands, and say that a Fleet-only car gets at most the paid send and its blind retry while asleep.
Needs a user ruling either way.

### Minor

**3. A ping answered by the range scan alone leaves sleep unknown, and three readers then read.**
`lib/TWCManager/Vehicle/TeslaBLE.py:631-638` (`_runPing`: VCSEC no answer, scan hit → True, no sleep status), `lib/TWCManager/Vehicle/Presence.py:399-404` (`fits`: `if ble and not asleep(v)` reads when `None`), `:206-211` (`checkPlug`: falls through to `v.read(... force=True)`), `lib/TWCManager/Vehicle/Reconcile/Run.py:160-181`. A `tesla-control state charge` can wake a sleeping car, so with VCSEC flaky and the car advertising, an attribution or a plug check may wake a car to observe it. Narrow (VCSEC normally answers asleep; the box never showed the case). Fix in the two observation paths only: `fits`: `if ble and asleep(v) is False` before the read; `checkPlug`: `if … ping(v.vin) and asleep(v) is not False: return True` (unknown stays "plugged", which is the fail-safe side). Leave `runAttempt` as is: a quiet send that must wait on an unanswered VCSEC would otherwise never go.

**4. `TWCSlave.heardFrom` carries a time nobody reads.**
`lib/TWCManager/TWCSlave.py:49-50`, `:631`; readers at `TWCMaster.py:495,543,576` test truthiness only. The time was for the link grace, which Task 19 removed. Restore `heardFrom = True`/the bool comment, or use the time. Zero lines, one misleading comment.

**5. The stale offer map after a withdraw.**
`lib/TWCManager/TWCMaster.py:665` sets `self.offered` only in `distributeEVSEPower`; `withdrawOffers` (`:569-580`) zeroes every offer without touching it, so `B.whyQuiet`'s "nothing offered" (`Belief.py:125`) reads the last good pass and a raise may still wake a car on a point now offered 0 A. Rare (the control pass has to be failing). Fix: `self.offered = {}` at the top of `withdrawOffers`.

**6. `checkConfigs` warns daily for every listed car.**
`lib/TWCManager/Vehicle/FleetTelemetryMQTT.py:70-84`. A pre-2021 S/X, or a second car the user never meant to stream, gets `no Fleet Telemetry config` once per process day and the claim line on its page. Acceptable for an opt-in module, but the doc paragraph (`docs/modules/Vehicle_FleetTelemetryMQTT.md:204`) should say the check covers every car on the Fleet account, so the warning for an unstreamed car is expected. Doc-only, one clause.

**7. The RELEASE/NOT_HERE residual is still unconfirmed.** `docs/PolicyCustomization.md:95-96`. Carried from the first review; neither reproduced nor removed. Either reproduce it on the box (an away car whose restore fails) or drop the sentence.

**8. `pr-notes.md` is two weeks of work behind the branch.** `.superpowers/sdd/…/pr-notes.md` says the 5/20/45 reads stay, describes the 60 s debounce and link-grace filters, lists 2093 tests and lib 26,198. The PR description must be rebuilt from the CHANGELOG and the final code: the sleeping-car rule, "check the car" on a Gen2 status edge, the Fleet Telemetry fields, deltas and config check, the Vehicles page, the dropped departure reads, 2232 tests, lib 26,413 (+3,233 vs main; target 26,140 missed by 273), and the known limit the user asked for (two paid commands per driveway shuffle on Fleet-only).

**9. Unpaired coordinates.** `Presence._fix` (`:50-55`) and `recordVehicleVIN` take `latest("lat")` and `latest("lon")` independently, so with two position sources the pair can straddle sources; `noteObservation` pairs by source (`:112`) but evaluates the incoming coordinate against the other's previous value, so a car arriving from far away can get one spurious `outside` mark a moment before its lon lands. Both are harmless today (the mark lands while the car was genuinely outside; sources rarely disagree) and T2-loc deferred pairing. Note only.

## Declined to judge (ruled)

- A single-candidate attribution with no plug evidence (a car parked unplugged inside the radius takes a guest's plug): T9 KEEP, F12.
- A Probably-home car with a pending limit is woken and read on the paid path, up to the budget: allowed change (b), F3.
- A held car with no plug reading is "presumed plugged" for a start: F20, T4-S12.
- A car named by a Gen2 whose newer live feed says unplugged is unplugged (`pluggedNow`'s precedence): first-review fix, watched on the box.
- `updateChargeAtHome` at power start and the away-car `statusDeferral` ladder: F11.
- Candidate fan-out of an anonymous point's rate to every car plugged in at home, including a UMC car: (h).
- Two paid commands per driveway shuffle on Fleet-only: ruled accepted, to be noted in the PR.
- The VIN-less check paying one `vehicle_data` per awake Fleet candidate on a 00@0 edge: T19 (≈7–10 checks/day on the box).

## Size

Lib 26,413: −118 against the phase base, +215 since the first final review (26,198), 273 above the 26,140 target. Each increment after 26,198 is a ruled feature (Tasks 8–21: the sleeping-car rule, BLE worker jobs, the expected-to-charge gate, the status-edge check, Fleet Telemetry fields and the config check), and the ledger accepted each over its target. No dead code found; `heardFrom`'s time is the only dead semantics (Minor 4). Behaviour-preserving cuts I can see:

| Where | Cut | Lines |
|---|---|---|
| `Presence.checkPlug:202-204` | `feed = v.reported("pluggedIn").get(v.syncSource)` repeats `telemetryPlug`'s first line; return the observation from `telemetryPlug` (or a `(value, seen)` pair) and use it in both | −2 |
| `TeslaAPI.update_charge:1904-1913` | The five-line comment restates `_readFresh`'s old one; two lines say why the BLE reply stamps `lastAPIAccessTime` | −3 |
| `TWCSlave.plugCheckDue:135-136` | Inline the `text` variable into the `logger.info` call (black keeps it to two lines) | −1 |
| `Reconciler.plan:347-349` | The "written without the store's lock" note fits two lines | −1 |
| `FleetTelemetryMQTT.checkConfigs:76-78` | `_request` already logs the HTTP answer at INFO8; `if answer is None: continue` (Task 21 S3, the reviewer's call) | −1 |
| `TWCSlave.py:49-50` | Minor 4: back to the bool | 0 |

About −8 in all. Getting to the target would mean cutting ruled behaviour; the honest statement for the PR is the one in Minor 8.

## Recommendations

1. Fix Important 1 now (one line, one test through `recordVehicleVIN`).
2. Put Important 2 to the user: (a) with the parity row 18 move listed, or (b) the two doc sentences; if (a), decide whether the 5-minute free check for an away asleep car is acceptable until Phase 6.
3. Take Minors 3, 4 and 5 in the same fix round (each is one or two lines); Minor 6 is a clause in the FT doc.
4. Rebuild the PR description (Minor 8) from the CHANGELOG, and settle Minor 7 one way or the other in it.
