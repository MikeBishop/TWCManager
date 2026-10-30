# Task 5 report: one attribution for VIN-less plugs, and the fan-out over candidates

Commit **96ae2c6d** on `vehicle-model/phase5` (worktree `scratchpad/wt-vm5`, parent 52ebb609). Not pushed.

## What I implemented

Built per the controller addendum and audit §4. I did not port `PresenceAttribution.py`, and there is no `Candidate` NamedTuple.

- **`Presence.pick(master, offered=None, actual=0, read=False) -> Optional[Vehicle]`.** It runs as a filter over `candidates(master)` in three stages. It does no I/O unless `read` is set.
  1. **The F12 single-car guess, decisive.** Exactly one pool car that is not NOT_HOME, whose newest `pluggedIn` reading (any source) is True and no more than `PLUGGED_JUST_NOW = 120` s old. The reading goes through `_plugEvidence(v, "pluggedIn", obs, True)`: the radius gate is open (no home or fix needed), but the fast-charger, no-cable and over-power veto still applies.
  2. **The BLE verdict per pool car.** It uses TeslaBLE's own `chargingState`, `availableCurrent` and `actualCurrent`, each no more than `REACH_WINDOW` (300 s) old.
     - **False:** the car reads unplugged, or plugged with a pilot more than `PILOT_MATCH_TOLERANCE = 1` A from the point's offer.
     - **True:** the pilot matches, and while the point delivers 1 A or more the car's actual current matches too.
     - **None:** nothing says either way, including a plugged read with no pilot, or no offer to compare (Gen3).
     - With `read`, a BLE-claimed pool car that has no fresh `chargingState` gets one `v.read("chargingState", 0, providers=("TeslaBLE",), force=True)`. That is BLE only: no wake, no TeslaAPI.
  3. **The winner.** Exactly one True car. Otherwise, among cars not False, the one BLE reached in the last 300 s (`_reached`, the contact/absent test factored out of `candidates`). Otherwise the one inside the radius. Anything else returns None.
- **`Presence.attribute(master, pointId, source, offered=None, actual=0) -> Optional[str]`.** Background thread only.
  - It returns None unless the point's session is still anonymous. The queued Gen2 task can run after a VIN read named the car, or after the session ended.
  - It runs `pick(read=True)`. With no winner it logs at INFO: `"<point>: no single car plugged in; left anonymous"`. Gen2 queues one task per anonymous session, so this is once per plug session; scenario 5 pins the count.
  - With a winner it calls `registry.observeTwcVin(pointId, vin)`, which merges the anonymous session's readings into the car, then `v.observe("pluggedIn", True, source)`. That reading is the plug-in evidence.
  - `noteObservation` marks `plugIn` and calls `onArrival` once. The arrival set is now `TELEMETRY_SOURCES | {"Gen2TWC", "Gen3TWC"}`. For Gen3, the vitals pass's own `pluggedIn True` that follows sees `was is True`, so there is no second arrival.
- **Gen2.** `_plugSession(slave, True)` queues `{"cmd": "attributePlug", "slaveTWC": TWCID, "args": (twcid, "Gen2TWC", reportedAmpsMax, reportedAmpsActual)}`.
  - It skips TWCs whose settings record `supportsVINQuery`.
  - `_taskKey` dedupes `attributePlug` per TWC, the same way as `getVehicleVIN`.
  - The `TWCManager.py` background handler runs `Presence.attribute(master, *task["args"])`.
- **Gen3.** The `_correlate` guess loop is replaced by `return attribute(self.master, self.pointId, "Gen3TWC")`. The cloud-VIN half is unchanged, except one dead line: `observeTwcVin` already clears every other car attributed to the point.
- **The fan-out (h).** For an anonymous key, `ChargingPoint._carKeys` returns `[v.key for v in candidates(master, SET_AMPS) if pluggedHere(master, v)]`. It no longer falls back to `vehicles[0]`.
- **The 00 probe is deleted.** Only `PLUGGED_STATES` opens an anonymous Gen2 session.
- **`candidates(master)` without a capability** now also drops any car whose `twcVin` names a point (carried item 2). It is still the one definition (F13), used by `pick` and by the unplug fallback.
- **Black** was run on every touched black-style file, including `Presence.py`. `black --check` on `Presence.py` is clean.

## Deletions, each verified

All four of the audit's deletions were taken. None fell through.

| Deletion | Verified with | Result |
|---|---|---|
| `TWCSlave.pluggedCars` with its three imports (`SET_AMPS`, `VEHICLE_SOURCES_EXCLUDED`, `_plug, candidates, inside`) | `git grep -nwE "SET_AMPS\|VEHICLE_SOURCES_EXCLUDED\|_plug\|inside\|candidates" -- lib/TWCManager/TWCSlave.py` | nothing |
| `ChargingPoint.anonymousCars` | `git grep -nw anonymousCars -- lib html tests/unit tests/integration tests/API docs` | nothing |
| `Gen3TWC._correlate`'s candidate loop and `CORRELATE_WINDOW`, plus the `HOME, presence` import | `git grep -nwE "CORRELATE_WINDOW" -- lib html tests docs` → nothing; `git grep -nw "presence\|HOME" -- lib/TWCManager/EVSEInstance/Gen3TWC.py` → nothing | both empty |
| The `pluggedCars()[0]` probe in `TWCMaster.observeChargingSessions` | `git grep -nwE 'pluggedCars\|CORRELATE_WINDOW\|_PLUGGED\|anonymousCars' -- lib html tests/unit tests/integration tests/API docs` | only `Presence.py:22,70` (`_PLUGGED`, the plug-state set) and `test_presence.py:263` (its test). The brief's Step 5 grep is satisfied: hits only in `Presence.py` and its own test. |

## Test mapping

- **`test_presence_attribution.py`: the 10 tests are rewritten against `pick`, on a real master and registry, with the same scenarios and winners.**
  - These tests never existed on this branch; they live on `presence/3-plug-presence`.
  - Each `Candidate` is now a real car. Reach is `bleReach True`, inside is `placeAt`, and the BLE charge read is TeslaBLE `chargingState`, `availableCurrent` and `actualCurrent`.
  - `test_fast_charger_is_never_the_twc` changes scenario: BLE never reports `fastChargerPresent`. It now pins the F12 veto instead: a Fleet `pluggedIn True` with `fastChargerPresent True` just now is no guess, and nothing places the car here.
  - The reason strings ("BLE pilot match" and the rest) are gone. The tests assert winners only.
- **`test_amps_reconciler.py::test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0`** is renamed `..._only_cars_plugged_in_here_and_never_vehicles_0`. **INTENTIONALLY CHANGED (h)**:
  - "none known plugged in" now gives no call, where it was `vehicles[0]`;
  - "HA Stopped for all" now gives no call, where it was the `vehicles[0]` fallback;
  - the `anonymousCars(m, s) == [VIN]` probe is now `pt._carKeys() == [VIN]`.
- **`anonTwc` fixture: PLUMBING-ONLY.**
  - It sets `here=False`, because `setup()`'s `pluggedIn True, "Gen3TWC"` would put VIN on a Gen3 that doesn't exist. In lib, a Gen3TWC `pluggedIn` only lands on the car the unit names.
  - The other TWC names VIN3 the real way: `observeTwcVin("8245", VIN3)` with `reportedState = 0x03`. Setting `currentVIN` alone never happens without the registry naming.
  - `test_an_anonymous_mode_1_lift_goes_to_the_plugged_in_car_only` passes unchanged after the fixture fix.
- **`test_limit_wiring.py::test_at_00_a_plugged_car_a_free_source_shows_at_home_begins_the_session`** becomes `test_only_a_plugged_state_begins_the_session_and_00_ends_it`. **INTENTIONALLY CHANGED** by the probe deletion (ruling 55 / audit §4). Now 00 opens nothing; 03 opens the anonymous session and the lift goes; 00 plus Disconnected ends it. **This has no letter in global-constraints.md** (see Concerns).
- **`test_limit_reconciler.py::test_paid_sends_that_never_reached_the_car_rearm_on_a_reading_after_it_wakes`: PLUMBING-ONLY.** I dropped `v.observe("pluggedIn", True, "Gen2TWC")` from the "only the heartbeat reads" loop. Nothing in lib writes that per heartbeat; the heartbeat writes `actualCurrent` only. With Gen2TWC now an arrival source, that unreal reading caused an arrival. The counts are unedited.
- **`test_twcmaster_vin_confirmation.py`: PLUMBING-ONLY.** The Mock slave's `pluggedCars` stub line is removed, because the method is gone.
- **`test_gen3twc_provider.py::make()`: PLUMBING-ONLY.** `m.getSlaveTWCs.return_value = []`. `pick` → `candidates` → `twcVinAt` iterates the slaves, and a bare Mock isn't iterable.
  - The Gen3 `_correlate` tests (`test_single_candidate_car_is_correlated`, `test_two_candidate_cars_stay_anonymous`, `test_old_plug_evidence_or_a_car_already_on_a_twc_is_not_a_candidate`) were **not rewritten**. They pass unchanged through `attribute`.
  - So do `test_charging_points.py` (both "correlated" tests), `test_vehicle_endpoint.py::test_anonymous_car_on_a_gen3_is_blind_but_a_correlated_one_is_not`, and `test_wall_connector_vins.py`.
- **Parity `gen3()` helper: PLUMBING-ONLY.** `g.getSlaveTWCs = m.getSlaveTWCs`, for the same reason. This is the parity file's **only deleted line**: `git diff 52ebb609 --stat` shows 177 insertions and 1 deletion. No existing row's count or timing changed.
- **Task 2's `candidates` tests** (`test_presence.py:283-317`, `test_candidates_for_a_broadcast_are_only_cars_base_reached`) pass unchanged with the new exclusion.

### New tests (22)

- **`test_presence_attribution.py` (10).** Listed above.
- **`test_presence.py` (+4):**
  - `test_attribution_reads_only_local_providers`: Owner and Fleet tokens, two cars home, one BLE charge read, `requests_mock.call_count == 0`.
  - `test_a_single_candidate_inside_is_attributed_merges_the_session_and_arrives_once`: Gen2 through real heartbeats and the queue. The anonymous session is gone, the car carries its `actualCurrent`, and `onArrival` fires once. A Gen3 unit on the same registry adds exactly one more.
  - `test_two_candidates_attributed_by_ble_pilot`.
  - `test_a_vinless_unplug_never_departs_a_car_another_twc_names` (carried item 2): two Gen2 slaves; the car is named at 8245 at 00.
- **`test_gen3twc_provider.py` (+2):**
  - `test_gen3_single_car_plugged_within_120_s_is_still_guessed_without_home_or_ble` (F12; at exactly 120 s);
  - `test_gen3_cloud_vin_still_corrects_a_guess`.
- **`test_command_path_parity.py` (+6 rows, appended, each with its full paid tuple).** Helpers: `attributeQueued(m)` (what the background thread does with `attributePlug`), `chargeRead(...)` (BLE charge state per VIN) and `twoCarsHome`.

  | Row | What it checks | Paid tuple |
  |---|---|---|
  | `test_vin_less_single_candidate_plug_one_apply` (scenario 3) | Away, then home, then a VIN-less 03: named, and the limit goes once over BLE | (0, 0, 0) |
  | `test_vin_less_two_candidates_ble_pilot_one_apply` (scenario 4) | BLE pilot 32 A against Disconnected: one car named and rated (`charging-set-amps` to VIN only); each car's limit goes once | (0, 0, 0) |
  | `test_vinless_ambiguous_plug_rates_nobody_and_logs_once` (scenario 5) | Nobody named or rated; one INFO line over 60 beats with the queue drained each beat | (0, 0, 0) |
  | `test_vinless_rate_never_falls_back_to_vehicles_0` ((h)) | Row 25 with neither car plugged: no AMPS desire ever set for either car, no amps request | (0, 0, 0) |
  | `test_supercharger_telemetry_plugged_is_not_home` (scenario 6) | Pushed `pluggedIn`, `fastChargerPresent` and Charging while away; a VIN-less plug at home names nobody and applies nothing | (0, 0, 0) |
  | `test_a_returning_car_on_an_unnamed_gen2_asleep_starts_over_ble` (carried item 1) | Attributed, unplugged (NOT_HOME), returns with BLE contact, 03 at 6 A, no VIN: named again, `pluggedHere`, and the start goes over BLE | (0, 0, 0) |

## Carried items

1. **Returning car on an unnamed Gen2: done.** `attribute` writes `twcVin` plus `pluggedIn True` from the point's source, so `pluggedNow` and `pluggedHere` see the plug and the start cell SENDs. Pinned by the last parity row.
2. **Single-candidate unplug fallback excludes cars another TWC names: done, in `candidates(master)`** (`not v.value("twcVin")`). Pinned with two Gen2 slaves.
   - **Deviation from the addendum:** the fallback is still Task 4's single `candidates()` car, not `pick`'s winner. With `pick`, `test_no_gps_source_plug_unplug_cycle_end_to_end` failed. The only car had no fresh BLE contact (more than 300 s) and no fix, so `pick` departed nobody, and the held limit would have stayed forever on a BLE-only box.
   - A car attribution named is found by `vehicleAt` first, so the fallback only runs when nothing was named.
3. **Nothing-offered rule: resolved by attribution.** A named car makes `Gen2TWC.vehicleKey` the VIN, so `master.offered` is keyed by it and the no-wake-at-0 A rule sees it.
   - **What remains:** with an ambiguous plug, the fan-out cars (`pluggedHere`) are still rated under the TWC's `anon:` key in `master.offered`, so the 0 A no-wake rule doesn't see their offer.
   - I added no lines for this. A one-line fix exists: key `offered` by every key in `p._carKeys()`.

**Row 26 scratch check** (no row edit): running row 26's body with `attributeQueued(m)` in each beat names the car on the first 03. The result is identical to the committed row: `[wake, set-limit 70, wake, set-amps 32, wake, start]`, `HeldLimit(100, 70)`, `call_count == 0`.

## What Task 6 consumes

- `Presence.pick(master, offered=None, actual=0, read=False)`.
- `Presence.attribute(master, pointId, source, offered=None, actual=0) -> Optional[str]`. The brief's `read=` flag is dropped: both callers are on the background thread.
- `PILOT_MATCH_TOLERANCE = 1` and `PLUGGED_JUST_NOW = 120.0`.
- The `attributePlug` task shape (`slaveTWC`, `args`).
- The INFO line `"<point>: no single car plugged in; left anonymous"`. It is the only ambiguity signal a Vehicles tab could surface.
- `candidates(master)` now excludes cars named at any point.
- The arrival sources include `Gen2TWC`.

## TDD evidence

I copied the final versions of the eight touched test files into a detached worktree at 52ebb609 (BASE lib). **20 fail**:
- all 10 attribution tests;
- the 4 new presence tests;
- parity scenarios 3, 4, 5 and the returning-car row;
- the rewritten `test_limit_wiring` test;
- the vin-confirmation test, because its Mock stub was removed.

These pass on BASE by design, as characterization:
- the F12 Gen3 pair;
- scenario 6;
- the (h) row before its "AMPS desire never set" probe was added. Main's `vehicles[0]` rate was already held at send time by Task 3's applicability. With the probe, (h) fails on BASE and passes now.

While iterating, the first run of `test_presence_attribution.py` failed 10 of 10 before any lib code.

**Results:**
- `tests/unit tests/EMS`: **2081 passed, 1 warning** (baseline 2059, plus 22 new).
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2090 passed, 1 xfailed**.

## Lib delta

- `git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 26,361 before, 26,368 after.
- `git diff --shortstat 52ebb609 -- lib`: 6 files changed, 90 insertions(+), 83 deletions(−). **Net +7.**
- **Target ≤ −17: 24 over**, inside the 25-over stop line.
- No deletion fell through. All four were taken, about −55 including imports and the probe's comment.
- **The overshoot is `Presence.py` at about +68 net, against the audit's estimate of about +33.** That breaks down as:
  - the three-way BLE verdict (drop, match or neutral). The 10 tests' winners require it: actual-while-drawing and the no-pilot fall-through both need "neutral" to keep a car in the reach pool;
  - the F12 stage with its away-charger veto;
  - the still-anonymous guard and the arrival write in `attribute`;
  - the `_reached` helper.
- I trimmed comments, folded the queue args and dropped the dead Gen3 line. I found no further cut that keeps behaviour.

## Concerns

1. **The 00 probe deletion is a behaviour change with no letter in global-constraints.md.** A free source showing an at-home car plugged in no longer opens an anonymous session at 00; only 03, 04 and the other plugged states do. Practical loss looks small: Task 4's box evidence is that an asleep plugged car reports 03, and 00 is the waking transient. **The controller should letter it or revert it** (+1 line to restore it using `pluggedHere`).
2. **Unplug fallback deviates from the addendum** (Carried item 2 above).
3. **Guard scope: attribution is skipped entirely on a TWC with `supportsVINQuery`**, not just while charging. This is an F11 judgement: on those TWCs BASE never guessed, and a wrong Gen2 guess has no correction for its `pluggedIn` reading.
   - Residual: on a TWC whose first-ever VIN hasn't set the flag yet, attribution can guess first.
   - If that guess is wrong, `recordVehicleVIN`'s `observeTwcVin` clears the wrong car's `twcVin` but not its `pluggedIn True, "Gen2TWC"` reading. Gen3 has `guess.observe("pluggedIn", False, ...)`; Gen2 has no equivalent.
   - If the guess is right, the car arrives twice (attribution, then the VIN confirm). `_apply` with the same policy value is idempotent.
4. **The attributed `pluggedIn True, "Gen2TWC"` reading is strong.** Only a newer plug reading from any source overrides it, for example the filtered unplug's `Gen2TWC False`.
   - On an idle-at-0 A departure (F6, no qualifying unplug) it lingers, like `twcVin` (Task 4 concern 4).
   - Unlike `twcVin`, it isn't gated by `_pointPlugged`, so `pluggedNow` stays True at 00 until something reads otherwise.
5. **`pick(read=True)` cost.** It makes up to one BLE charge read per BLE-paired pool car that lacks a fresh reading, each up to the BLE command timeout, on the background thread. For Gen3, that sits inside the vitals refresh.
6. **Residual reach of the fan-out.** A car a Gen2 names at 00 (`twcVinAt == NEVER`), whose telemetry shows it plugged in and home, is still reachable by another unnamed TWC's `candidates(SET_AMPS)` fan-out. That is BASE behaviour since Task 4's `vehicleKey`. The new exclusion applies only to `candidates(master)` without a capability, so the broadcast audience is unchanged (F11).
7. **Carried item 3 residual:** ambiguous fan-out offers stay keyed by `anon:`.

---

# Fix round 1

Commit **edd5453c** (parent 96ae2c6d). Not pushed.

## Findings and fixes

I checked each finding in the code before acting on it.

- **C1 (the Gen3 vitals refresh blocked on BLE): fixed.** `attribute` now calls `pick(master, offered, actual, read=offered is not None)`. Gen3 passes no offer, so it never makes a forced BLE read. `pick`'s comment says that BLE reading happens only when there is an offer.
  - Test: `test_presence.py::test_a_gen3_plug_in_never_reads_ble`. A Gen3 rising edge with two BLE-claimed cars, no plug reading (so the single-car guess is not decisive) and the car inside the radius. Result: zero `_fetch_state_json` runs, and the car is named by the inside rule.
- **I1 (an attributed Gen2 plug never expired after an idle departure): fixed.** `pluggedNow` ignores a True reading from `Gen2TWC`, so a Gen2 plug counts only through `twcVinAt`, which requires the point to report a non-00 state. The attribution's `pluggedIn True` still marks `plugIn` and drives the one arrival.
  - Test: `test_an_attributed_gen2_plug_ends_with_the_point_s_00_even_idle`. The car is attributed, then idle at 0 A at 03: it is `pluggedHere` and has a VehicleEndpoint. Then 00: no unplug mark, not `pluggedHere`, and no endpoint.
  - The returning-car parity row still passes.
- **Minor 1: the 00-probe deletion stays, per the controller's ruling.** It is labelled under global-constraints (h). Restoring it would queue attribution for an empty TWC whenever a home car is plugged in elsewhere.
  - I removed the vestigial Disconnected observation from `test_limit_wiring.py::test_only_a_plugged_state_begins_the_session_and_00_ends_it`; nothing needed it, because 00 alone ends the anonymous session.
  - This supersedes Concern 1 above.
- **Minor 2 (the offer snapshot): fixed.** The `attributePlug` task now carries only `slaveTWC`. The background handler reads the slave's current `reportedAmpsMax` and `reportedAmpsActual` when it runs, and skips a slave that is gone.
  - The parity helper `attributeQueued` does the same.
- **Minor 3 (offers for fan-out cars): fixed.** `master.offered` is now `{k: w for p, w in offers for k in (p.vehicleKey, *p._carKeys())}`, so fan-out cars on an ambiguous point fall under the no-wake-at-0 A rule. This resolves carried item 3's residual.
  - Test: `test_an_anonymous_point_s_offer_covers_the_cars_it_fans_out_to`.
  - PLUMBING-ONLY: `test_charging_points.py::test_idle_gen3_units_get_zero_and_two_units_are_two_points` now builds its Mock master with an empty registry, because `_carKeys` on an anonymous Gen3 point now runs `candidates()`.
- **Minor 6 (stale comments): fixed.** At the plugged-state open in `observeChargingSessions`: "unnamed, it opens a session to attribute". At the raw-00 close: "00 ends the anonymous session".
- **Size cuts: only the comment trims taken.**
  - `fits` comment: 2 lines → 1.
  - `attribute` comment: 2 lines → 1.
  - `_carKeys` comment: 3 lines → 2.
  - `_taskKey` comment: 2 lines → 1.
  - `pick` comment: reworded at the same length.
  - The task payload shrank by 2 lines.
  - The supportsVINQuery and actual-current cuts were not taken.

## TDD evidence

On a detached worktree at 96ae2c6d with the new `test_presence.py`, the 3 new tests fail (C1, I1, Minor 3) and the other 56 pass. With this commit, all pass.

## Results and size

- `tests/unit tests/EMS`: **2084 passed, 1 warning** (+3 new tests).
- Parity file: the only change since 96ae2c6d is the `attributeQueued` helper. No row changed.
- `git diff --shortstat 52ebb609 -- lib`: 6 files changed, 92 insertions(+), 86 deletions(−). **Net +6** (26,361 → 26,367).
  - That is 3 over the accepted ~+3.
  - This round alone is −1: I1 +2, the handler reading the slave +2, offers +0, and the trims and task payload −5.
