# Plug-based Vehicle Presence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the home/away/arriving presence state machine with a plug-based model (HOME = plugged in here; NOT HOME otherwise, DEPARTING after an unplug), so no charge-limit command, wake or charge command reaches a car that isn't plugged in here.

**Architecture:** One new stacked branch, `presence/3-plug-presence`, on `presence/2-charge-limits`. Task 1 cherry-picks the carried commits of the old branches 3 and 4. The VehiclePresence decision layer is then rewritten around plug evidence. The vehicle modules (TeslaBLE, TeslaAPI, Telemetry, HomeAssistant) report plug evidence, and they gate every non-restore command on what they read. Every consumer of "at home" asks `VehiclePresence.isHome()`. After that, `presence/5-fleet-rate-queue` is rebased as `presence/4-fleet-rate-queue`, and `deploy/presence-3` is rebuilt by merging `feat/token-slots` (#692).

**Tech Stack:** Python 3, pytest, black. Threads: the serial main loop, the VehiclePresence thread and the vehicle command worker.

**Spec:** `.superpowers/specs/2026-10-11-plug-presence-design.md` (binding). Background: `.superpowers/presence-split-report.md`, `.superpowers/sdd/2026-10-09-vehicle-presence/progress.md`, `.superpowers/deploy-presence-2-merge-report.md`.

## Global Constraints

- Two states per vehicle: HOME (plugged in here) and NOT HOME, which is internally DEPARTING after an unplug. No AWAY and no ARRIVING anywhere.
- Charge-limit policy applies only to HOME (or presumed-present) cars. "DEPARTING is always excluded" and "A DEPARTING car is never presumed present."
- "No wake is ever sent just to find out whether the car should be woken later."
- Evidence strength: "A TWC naming the car, or a BLE charge read, decides on its own." "When they disagree, BLE or the TWC wins."
- "BLE silent: says nothing about whether the car is home."
- The carried TWC rules are unchanged: "a plugged run of at least 60 s before a change counts, there is a 300 s grace after a TWC re-link, and TeslaMate `plugged_in` overrides a Gen2 TWC's steady 00 for an idle plugged car."
- `atHomeRadius` default: **1,000 ft** (was 10,560). An explicit config value still overrides it.
- Departure-restore fallback after BLE has been unreachable for N = **5 minutes**, only "if `commandPolicy` allows a remote channel".
- The fingerprint (offset current) is **not** built here. It's a follow-up.
- Branches 1 and 2, `feat/token-slots` (#692/#693) and IntegrationOrder stay unchanged. `presence/5-fleet-rate-queue` and `deploy/presence-2` are left as they are; new branches are created next to them.
- Every branch passes the full suite: `<PY> -m pytest tests/unit -q`, where `<PY>` = `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/0d80154a-e8ed-4486-8cbb-803c4281947c/scratchpad/venv/bin/python`. Individual commits don't have to pass.
- Run `<PY> -m black` only on the files a commit touches. Don't reformat a test file that wasn't black-clean before; write the new hunks in black style.
- Every new commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Cherry-picked commits keep their messages (see Task 1).
- No log line may contain a token.
- Work in your own worktree. Don't check out branches in, or edit tracked files of, `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96`. Nothing is pushed. The live box stays on `commandPolicy: ble_only`, and this plan includes no deploy.

## Review Focus

1. **The 60 s unplug debounce.** The car stays HOME until the TWC's debounced unplug, so a policy apply in that minute can target a car that is leaving. Expected: the read-before-write shows it unplugged and nothing is sent. Test in Task 6 (`test_ble_apply_to_a_car_read_as_unplugged_sends_nothing`).
2. **A restart while a car is away with a held limit.** The car is presumed present, the policy apply goes to BLE, BLE fails, and `prefer_ble` falls back to the Fleet API. Expected: the Fleet path reads the car, sees it unplugged or outside the radius, sends no `set_charge_limit` and marks the car NOT_HOME. Test in Task 6 (`test_presumed_car_found_away_on_the_fleet_path_gets_nothing`).
3. **TeslaMate goes stale (syncSource reverts to "TeslaAPI") while a car is HOME.** `telemetryPluggedIn` turns None. Expected: no state change. None is never "unplugged". Test in Task 2 (`test_stale_telemetry_is_not_an_unplug`).
4. **Two cars, one VIN-less TWC, both asleep when it's plugged in.** The probe can't read either one's charge state. Expected: nobody becomes HOME, one INFO line, no wake. Test in Task 4 (`test_two_sleeping_candidates_are_ambiguous_and_never_woken`).
5. **TeslaMate reconnects and its retained `plugged_in=false` arrives for a car that a VIN-reading TWC names right now.** Expected: the TWC wins and the car stays HOME. Test in Task 2 (`test_telemetry_unplug_loses_to_a_twc_naming_the_car`).

---

## File structure

| File | Responsibility after this plan |
|---|---|
| `lib/TWCManager/VehiclePresence.py` | Per-VIN plug-presence state, evidence records, decision rules, thread, DEPARTING timer (rewritten decision layer; thread/bounds carried) |
| `lib/TWCManager/PresenceAttribution.py` (new) | Pure function: which car a VIN-less TWC's plug belongs to |
| `lib/TWCManager/PresenceSources.py` | Sleep-safe evidence sources (BLE reach + awake charge read, live telemetry, online-only API) |
| `lib/TWCManager/PresenceHandlers.py` | HOME apply, departing restore (BLE or remote), remote fallback restore, home-proof hook, `bleApplies` |
| `lib/TWCManager/TWCSlave.py` | Debounced plug/unplug reports; targeted charge VIN |
| `lib/TWCManager/Vehicle/TeslaBLE.py`, `TeslaAPI.py`, `Telemetry.py`, `HomeAssistant.py` | Report plug evidence; gate commands; HOME-only policy-wide applies and broadcasts |
| `lib/TWCManager/EVSEController/TeslaAPIController.py` | Fleet EVSEs only for HOME cars (branch 3); BLE-silent rule (branch 4) |
| `etc/twcmanager/{config,.testconfig,demo}.json`, `CHANGELOG.md` | Radius default text, `presenceSources` removal, changelog |

---

## Branch `presence/3-plug-presence`

### Task 1: Create the branch and carry over the surviving commits

**Files:** none edited by hand.

**Interfaces:**
- Produces: a branch whose tree equals `presence/4-arrive-depart` except `lib/TWCManager/VehiclePresence.py` and `tests/unit/test_vehicle_presence.py`. Those two stay at the version branch 3 had, without the telemetry-limit fill. Verified in a probe: 958 passed.
- Invariant for later tasks: the carried code calls these presence methods, and Task 2 must provide each with exactly this signature: `nominate(vin, reason, delays=(0,))`, `observeContact(vin, reachable, probe=False)`, `observeProof(vin, source)`, `observeUnplug(twc, vin, excluded=frozenset())`, `observePlug(twc, vinReading=False)`, `observeTelemetryPlug(vin, pluggedIn)`, `observeLocation(vin, atHome)`, `state(vin)`, `start()`, `stop()`. The suite is green after this task only because the callers are mocked.

- [ ] **Step 1: Create the worktree and branch**

```bash
git worktree add -b presence/3-plug-presence <scratch>/wt-plug presence/2-charge-limits
```

- [ ] **Step 2: Cherry-pick branch 3 minus the telemetry-limit fill (17 commits, all clean in the probe)**

Skipped: `f939ff8` and `490c7cb`. Their effect is removed again by `b3c692a`.

```bash
git cherry-pick 7277dd0 a73d5b3 ceacea0 15d6805 2cebb08 0972265 27a5e1f 93e6104 3b83505 b0ddcdf 7594e70 bb5837c b8e55a0 d4055ae 8cf363e a2855bb c7d4cf1
<PY> -m pytest tests/unit -q   # expect 905 passed
```

- [ ] **Step 3: Cherry-pick the branch-4 commits without their tracker hunks, in this order**

For each SHA in `c274d6c fada5b4 df426ed 07c06b2 7e9ca95 b3c692a 66acf97 87bb011 05437b7 11753a9 4c5a008 32d798a 94cf1c5`:

```bash
git cherry-pick -n <sha>
git checkout HEAD -- lib/TWCManager/VehiclePresence.py tests/unit/test_vehicle_presence.py
git commit -C <sha>          # "whole" rows below
git commit -F <msgfile>      # "partial" rows: message below
```

| SHA | Kind | Message |
|---|---|---|
| c274d6c | partial | original message, plus the paragraph below |
| fada5b4 | partial | subject `Add the departing handler: restore the limit over BLE on unplug`, original body, plus the paragraph below |
| df426ed, 7e9ca95, 87bb011, 11753a9, 4c5a008, 94cf1c5 | whole | `-C` |
| 07c06b2, b3c692a, 66acf97 | partial (only a tracker-test hunk or tracker comments dropped) | original message, plus the paragraph below |
| 05437b7 | partial | subject `TWC plug evidence says whether the TWC reads VINs`, original body, plus the paragraph below |
| 32d798a | partial | subject `Add CarApiVehicle.pluggedIn and a live-telemetry plug lookup`, original body, plus the paragraph below |

The paragraph to add, inserted before the trailer: `Carried without its VehiclePresence part; the plug-presence tracker replaces that.` The message must end with the original trailer and then the `Co-Authored-By: Claude Opus 5.5` line, if the original trailer isn't already that line.

Not carried at all, because the new tracker replaces them: `045160f 443b181 8764711 6805b0b b0a86f9 0b46958`.

- [ ] **Step 4: Verify the carry**

Run: `<PY> -m pytest tests/unit -q` → `958 passed`.
Run: `git diff --stat presence/4-arrive-depart` → only `lib/TWCManager/VehiclePresence.py` and `tests/unit/test_vehicle_presence.py` are listed.

---

### Task 2: Rewrite the tracker core: plug states, evidence records, decision rules

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py` (rewrite the decision layer. Keep the thread, `start`/`stop`, `nominate`/`_due`/`_collectDue`, `MAX_OBSERVATIONS`/`MAX_DUE_PER_VIN`, `_callSource`, `_runHomeProof` and handler runners.)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`CarApiVehicle.atHome` getter), `lib/TWCManager/Vehicle/TeslaBLE.py` (the policy-wide skip at the `presence.state(vehicle_vin) == "away"` check)
- Modify: `etc/twcmanager/config.json` (remove the commented `presenceSources` block)
- Test: `tests/unit/test_vehicle_presence.py` (rewrite), `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_teslable_presence.py`

**Interfaces:**
- Consumes: the Task 1 invariant (every observer signature above, unchanged).
- Produces, in `VehiclePresence.py`:
  - State constants: `HOME = "home"`, `PRESUMED = "presumed"`, `DEPARTING = "departing"`, `NOT_HOME = "not_home"`. A VIN with no entry in `_state` is PRESUMED. `AWAY`, `UNKNOWN`, `ARRIVING`, `AWAY_AFTER_FAILED_PROBES`, `_failedProbes`, `_dropAwayFixes`, `DEFAULT_SOURCE_ORDER`/`sourceOrder`/`presenceSources` are removed. If `config["vehicle"]["presenceSources"]` is set, log one WARNING that it is ignored.
  - Class constants: `PROBE_INTERVAL = 60`, `STRONG_EVIDENCE_HOLD = 300`, `BLE_REACH_MAX_AGE = 300`.
  - Records (in memory only, never persisted; a restart means presumption): `_plug: dict[vin, PlugRecord]` with `PlugRecord = namedtuple("PlugRecord", "pluggedIn source at")`, where `source` is one of `"twc" | "ble" | "telemetry" | "api"` and `"twc"`/`"ble"` are strong. `_inside: dict[vin, tuple[bool, float]]` holds the last location answer. `_reach: dict[vin, tuple[bool, float]]` holds the last BLE contact result.
  - New observer: `observePlugState(vin, pluggedIn: bool, source: str, edge: bool = False, fastCharger: bool = False) -> None`. It is record-only. `edge=True` means "a change was seen" (a TWC unplug, a telemetry change); `edge=False` means "a read".
  - `observeTelemetryPlug(vin, pluggedIn, edge=True)` delegates to `observePlugState(vin, pluggedIn, "telemetry", edge=edge)`.
  - `observeContact(vin, reachable, probe=False)` records successes, and records failures only when `probe=True`. It never causes a transition.
  - `observeLocation(vin, atHome)` records `_inside`. It causes a transition only by the rule below.
  - Queries: `state(vin) -> str` (one of the four constants), `isHome(vin) -> bool` (HOME or PRESUMED), `isPluggedHome(vin) -> bool` (HOME only), `bleReachable(vin) -> bool` (last contact succeeded within `BLE_REACH_MAX_AGE`).
  - Constructor kwargs: drop `sourceOrder`; keep `sources, onArrival, onDeparture, onHomeProof, knownVehicles, clock, bleApplies, onDeparting, pluggedIn`; add `twcVins=None` (a callable returning the set of VINs that a TWC currently names through `currentVIN` or a real `plugVIN`; the default reads `master.getSlaveTWCs()`).
  - The default `bleApplies` drops the `"ble" in order` check (there is no order now). Until Task 5 moves it to `PresenceHandlers.bleApplies`, it is TeslaBLE loaded and `bleProven`.
  - Handlers are called as now: `onArrival(vin, None)`, `onDeparting(vin, unambiguous) -> bool`, `onDeparture(vin, None)` (the remote restore; Task 5 decides when).
- `CarApiVehicle.atHome` getter: `presence.isHome(self.VIN)` when presence exists and the VIN is set, else `self._locationAtHome`. The setter is unchanged.
- TeslaBLE's policy-wide apply skips a VIN when `not presence.isHome(vin)`.

**Decision rules.** These are applied on the presence thread, in observation order, with the lock held. "Here" means: `_inside` is True, or `bleReachable(vin)`, or `vin in twcVins()`. A handler runs only on the transition shown.

| Evidence | Current state | Result |
|---|---|---|
| `proof(vin, "twc")` | any | HOME. Record a strong plugged record. Run the home-proof hook (carried). Run `onArrival` if the car was DEPARTING or NOT_HOME. |
| `unplug(twc, vin≠None)` | HOME, PRESUMED | If live telemetry says the car is plugged in (`pluggedIn(vin) is True`): ignore it and log INFO (carried rule). Otherwise DEPARTING, record a strong unplugged record, run `onDeparting(vin, True)`. |
| `unplug(twc, None)`, `plug(twc, …)` | — | Task 4 (in this task they are debug-logged no-ops) |
| `plugState(True, "ble")` | any not HOME | HOME. Run `onArrival` if the car was DEPARTING or NOT_HOME. |
| `plugState(True, weak)` | any not HOME | Ignored if `fastCharger` or if a strong unplugged record is younger than `STRONG_EVIDENCE_HOLD`. Otherwise, if the car is here, the same as the BLE row. If it isn't here (yet), the `_plug` record is still written and the state is unchanged. When it does become HOME this way and `bleApplies(vin)`, nominate one probe for it (`nominate(vin, "home-by-telemetry")`), so that `_reach` is fresh. |
| `location(vin, True)` or `contact(vin, True)` | any not HOME | If the latest `_plug` record is a weak plugged one (not `fastCharger`, with no newer strong unplugged record), re-apply the weak-plugged row. TeslaMate's retained `plugged_in` and its lat/lon arrive in either order. Otherwise the evidence is only recorded. |
| `plugState(False, any)` | HOME | DEPARTING, run `onDeparting(vin, True)`. For a weak source: ignored if `vin in twcVins()` or a strong plugged record is younger than `STRONG_EVIDENCE_HOLD`. |
| `plugState(False, any)` | PRESUMED | DEPARTING with `onDeparting` if `edge`, otherwise NOT_HOME with no handler (discovery). The same weak-source exceptions apply. |
| `location(vin, False)` | PRESUMED | NOT_HOME (no handler) unless `bleReachable(vin)`. Location changes no other state. |
| `contact` | any | Recorded only, except for the re-apply row above. |

- [ ] **Step 1: Rewrite `tests/unit/test_vehicle_presence.py` with the failing tests**

Keep, adapting them to the new names: `FakeClock`, `Recorder`, `make(...)` without `order`, `TestScheduling::test_observers_record_only`, `test_handlers_run_without_the_presence_lock`, `TestThread`, `TestDefaults`, `TestBoundedWithoutThread`, `TestHomeProof` (minus the away-fix tests) and `TestNominationStorm`. Delete `TestDecisionRules`, `TestSourceFallback` and `TestFixRound1`. `TestDepartAndReturnThroughTheQueue` moves to Task 5. Add these tests:

```python
def test_every_vin_starts_presumed():      assert p.state(V1) == PRESUMED and p.isHome(V1) and not p.isPluggedHome(V1)
def test_twc_proof_makes_home_and_arrives_from_not_home():  # NOT_HOME -> HOME; rec.arrivals == [(V1, None)]
def test_proof_of_a_presumed_car_runs_no_arrival():         # PRESUMED -> HOME; rec.arrivals == []
def test_unplug_naming_a_home_car_departs():                # state DEPARTING; rec.departing == [(V1, True)]; not p.isHome(V1)
def test_unplug_ignored_while_live_telemetry_says_plugged():  # pluggedIn=lambda v: True; state stays HOME
def test_departing_is_never_presumed():                     # after unplug: isHome False; a location(True) and a contact(True) change nothing
def test_ble_contact_never_transitions():                   # contact on NOT_HOME and on DEPARTING: state unchanged
def test_ble_plugged_read_makes_home_without_location():    # NOT_HOME + plugState(True,"ble") -> HOME, one arrival
def test_telemetry_plugged_outside_radius_is_not_home():    # location False + plugState(True,"telemetry") -> stays NOT_HOME (Supercharger)
def test_telemetry_plugged_inside_radius_is_home():         # location True + plugState(True,"telemetry") -> HOME (UMC case)
def test_telemetry_plugged_then_location_inside_is_home():   # plugState(True,"telemetry") first, then location True -> HOME, one arrival
def test_home_by_telemetry_nominates_a_ble_probe():         # bleApplies True -> a due time for V1; bleApplies False -> none
def test_telemetry_plugged_with_ble_reach_is_home_without_gps():
def test_fast_charger_plug_is_never_home():                 # plugState(True,"api",fastCharger=True) inside radius -> unchanged
def test_ble_unplugged_beats_a_recent_telemetry_plugged():  # strong False at t, weak True at t+10 -> stays DEPARTING
def test_telemetry_unplug_loses_to_a_twc_naming_the_car():  # twcVins={V1}; plugState(False,"telemetry",edge=False) on HOME -> HOME
def test_stale_telemetry_is_not_an_unplug():                # pluggedIn returns None; TWC unplug naming V1 -> DEPARTING (not ignored), and no plugState is synthesized
def test_presumed_read_unplugged_is_not_home_with_no_handler():  # plugState(False,"api") on PRESUMED -> NOT_HOME; rec.departing == []
def test_presumed_edge_unplug_departs():                    # observeTelemetryPlug(V1, False) (edge) on PRESUMED -> DEPARTING
def test_presumed_outside_radius_without_ble_is_not_home(): # location False -> NOT_HOME; with a recent reach -> stays PRESUMED
def test_presence_sources_setting_is_ignored_with_a_warning(caplog):
```

In `test_teslaapi_presence.py`, add `test_at_home_reads_is_home` (PRESUMED → True, DEPARTING → False, no presence → `_locationAtHome`). In `test_teslable_presence.py`, update `TestSkipsAwayVehicles` so that a DEPARTING car and a NOT_HOME car are both skipped while a PRESUMED car is not.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `<PY> -m pytest tests/unit/test_vehicle_presence.py -q`. Expected: failures on the missing `PRESUMED` and `observePlugState`.

- [ ] **Step 3: Implement the state model, records, observers, queries and decision table in `VehiclePresence.py`; switch `CarApiVehicle.atHome` and TeslaBLE's skip to `isHome`; remove the `presenceSources` comment block from `config.json`**

`runPass` now does three things: drain the observations and apply the table, then probe due VINs (Task 3 defines what a probe returns; until then a probe is a no-op), then run the queued handlers without the lock.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_vehicle_presence.py tests/unit/test_teslaapi_presence.py tests/unit/test_teslable_presence.py -q`. Expected: pass.

- [ ] **Step 5: Commit**

Subject: `Rewrite VehiclePresence around plug evidence (HOME / DEPARTING / presumed)`.

---

### Task 3: Sleep-safe evidence probes and startup discovery

**Files:**
- Modify: `lib/TWCManager/PresenceSources.py`, `lib/TWCManager/VehiclePresence.py` (`_probe`, `start`), `lib/TWCManager/Vehicle/TeslaBLE.py` (`get_charge_state`), `lib/TWCManager/TWCSlave.py` (remove the nominations)
- Test: `tests/unit/test_presence_sources.py`, `tests/unit/test_vehicle_presence.py`, `tests/unit/test_teslable_presence.py`, `tests/unit/test_twcslave.py`

**Interfaces:**
- Produces, in `PresenceSources.py`: each source is `callable(vin) -> None | dict` and returns a subset of the Evidence keys: `reach: bool`, `pluggedIn: bool|None`, `inside: bool|None`, `pilot: float|None`, `actual: float|None`, `fastChargerType: str|None`, `fastChargerPresent: bool|None`. The `"limit"` key is removed.
  - `telemetrySource` gives `inside` (None while home is unset) and `pluggedIn` from `telemetryPluggedIn`. It applies only while telemetry is live.
  - `bleSource` gives `reach` from `probePresence`. Only when the probe says the car is awake does it call `get_charge_state` and add `pluggedIn`, `pilot` (=`availableCurrent`), `actual`, `fastChargerType` and `fastChargerPresent`. It returns None for a VIN that isn't in `settings["Vehicles"]`. Reach False is recorded for every car in Vehicles. `bleProven` gating moves to `bleApplies` (Task 5).
  - `apiSource` is unchanged in shape and keeps its online-only rule. It gives `inside` (raw `_locationAtHome`; None while home is unset), and `pluggedIn = chargingState != "Disconnected"`, which is None when chargingState is `"Unknown"`, plus `fastChargerPresent`.
- `VehiclePresence._probe(vin, bleOnly=False) -> dict` merges every applicable source: `reach` from ble; `pluggedIn` from ble, else telemetry, else api, with the source name kept; `inside` from telemetry, else api. `runPass` applies the result as `contact(reach, probe=True)`, `plugState(pluggedIn, source, edge=False, fastCharger=...)` and `location(inside)`, in that order.
- `nominate(vin, reason, delays)` keeps its meaning of "probe this VIN (None = every known VIN) at those times". `start()` calls `nominate(None, "startup")` once.
- TeslaBLE: module-level `blePluggedIn(cs: dict) -> bool | None`, where `cs` is the raw `chargeState`. True if `chargePortLatch` is Engaged, or `connChargeCable` contains "SAE" or "IEC", or `chargingState` is anything but Disconnected/None. False if `chargingState` is Disconnected and the latch isn't Engaged. Otherwise None. Enum values go through `_extract_enum_value`. `get_charge_state` adds the keys `pluggedIn`, `chargePortLatch`, `connChargeCable`, `chargeCurrentRequest`, `fastChargerType` and `fastChargerPresent`.
- TWCSlave: remove `_nominatePresence` and `_presenceVIN` and their three call sites (power-start, power-drop 300/1200/2700, unplug 300/1200/2700). Location isn't polled any more. HTTPControl's `nominate(None, "api")` stays.

- [ ] **Step 1: Write the failing tests**

```python
# test_teslable_presence.py
@pytest.mark.parametrize("cs,expected", [
    ({"chargePortLatch": "ChargePortLatchEngaged", "chargingState": "Stopped"}, True),
    ({"connChargeCable": "ChargeCableTypeSAE"}, True),
    ({"chargingState": "Disconnected", "chargePortLatch": "ChargePortLatchDisengaged"}, False),
    ({}, None)])
def test_ble_plugged_in_derivation(cs, expected): assert blePluggedIn(cs) is expected
def test_get_charge_state_exposes_plug_and_pilot_fields():  # keys pluggedIn, availableCurrent==47, fastChargerType=="ACSingleWireCAN"
# test_presence_sources.py
def test_ble_source_reads_charge_only_when_awake():   # awake False -> get_charge_state not called; result == {"reach": True}
def test_ble_source_reports_unreachable_as_reach_false():
def test_api_source_never_queries_an_offline_car():   # vehicleOnlineStates -> "asleep": update_vehicle_data not called
def test_api_source_reports_plug_and_fast_charger():
def test_telemetry_source_gives_inside_and_plugged():
# test_vehicle_presence.py
def test_startup_nominates_every_known_vin_once():
def test_probe_of_an_asleep_ble_car_keeps_it_presumed():  # reach True, no read -> PRESUMED, contact recorded
def test_probe_merges_ble_plug_over_telemetry():          # ble pluggedIn False, telemetry True -> plugState source "ble"
def test_ble_only_probe_calls_only_the_ble_source():
# test_twcslave.py: TestPresenceTriggers
def test_twc_events_nominate_nothing():  # power-start, power-drop, unplug: master.vehiclePresence.nominate.assert_not_called()
```

Delete the old nomination tests in `TestPresenceTriggers`: `test_power_start_nominates_current_vin_now`, `test_power_drop_nominates_with_departure_delays` and `test_unplug_without_a_power_drop_still_nominates`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `<PY> -m pytest tests/unit/test_presence_sources.py tests/unit/test_vehicle_presence.py tests/unit/test_teslable_presence.py tests/unit/test_twcslave.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement the sources, `_probe`, startup nominate, `blePluggedIn` and the `get_charge_state` keys; remove the TWCSlave nominations**

- [ ] **Step 4: Run the same tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `Presence probes gather sleep-safe plug evidence; startup discovers`.

---

### Task 4: Attribute a VIN-less TWC's plug and unplug

**Files:**
- Create: `lib/TWCManager/PresenceAttribution.py`
- Modify: `lib/TWCManager/VehiclePresence.py`, `lib/TWCManager/TWCSlave.py` (`_checkPlugState`)
- Test: `tests/unit/test_presence_attribution.py` (new), `tests/unit/test_vehicle_presence.py`, `tests/unit/test_twcslave.py`

**Interfaces:**
- Consumes: the Evidence dict from Task 3, and `_presenceKey()`, `reportedAmpsMax`, `reportedAmpsActual`, `plugVIN` and `NON_TESLA` on the slaves.
- Produces, in `PresenceAttribution.py`:
  - `PILOT_MATCH_TOLERANCE = 1` (amps).
  - `Candidate = namedtuple("Candidate", "vin reach inside pluggedIn pilot actual fastChargerType fastChargerPresent")`.
  - `pickPluggedCar(candidates: list[Candidate], offeredAmps: float, actualAmps: float) -> tuple[str | None, str]`, which returns `(vin or None, reason)`. The rules, in order:
    0. A candidate with `pluggedIn is True` and `pilot is None` (an awake read without the field) is neither dropped by rule 2 nor matched by rule 3. It goes on to rule 4.
    1. Drop every candidate whose `pluggedIn is False`.
    2. Drop every candidate whose `pluggedIn is True` and that has `fastChargerPresent is True` or `abs(pilot - offeredAmps) > PILOT_MATCH_TOLERANCE`. That car is on another charger.
    3. `matched` = the candidates with `pluggedIn is True`, `fastChargerType == "ACSingleWireCAN"`, a pilot within tolerance, and, when `actualAmps >= 1` and `actual` is known, `abs(actual - actualAmps) <= PILOT_MATCH_TOLERANCE`. Exactly one → `(vin, "BLE pilot match")`. More than one → `(None, "ambiguous")`.
    4. `pool` = the candidates with `reach` or `inside`. If any of them has `reach`, keep only those. Exactly one → `(vin, "single candidate")`. Otherwise `(None, "ambiguous")` or `(None, "no candidate")`.
- In `VehiclePresence`:
  - `_twcVin: dict[twcKey, vin]`, the attribution of each VIN-less TWC.
  - `_ambiguousLogged: set[twcKey]`, cleared on that TWC's unplug.
  - `vinForTwc(twc) -> str | None`.
  - `observePlug(twc, vinReading=True)` stays a no-op, because the VIN proof follows.
  - A VIN-less plug on a TWC whose `_twcVin` already names a HOME car is a no-op. This stops the debounced report and the carried power-start report from triggering two probe sweeps for one plug-in. A car leaving HOME has every `_twcVin` entry that points to it removed.
  - A VIN-less plug runs `_probe(v)` (rate limit bypassed) for every known VIN that isn't in `twcVins()` and isn't attributed to another TWC. It reads `offered`/`actual` from the slave whose `_presenceKey() == twc`. A winner becomes HOME (with `onArrival` from DEPARTING or NOT_HOME) and goes into `_twcVin[twc]`. With no winner, it logs one INFO per plug session: `"TWC %s plugged in; can't tell which car (%s); no car is home from it"`.
  - `unplug(twc, None, excluded)`: the target is `_twcVin.pop(twc)` if that's set. Otherwise the candidates are the HOME or PRESUMED cars that aren't excluded, aren't attributed to another TWC and aren't plugged in according to live telemetry. One candidate departs (`onDeparting(vin, True)`). With several, each one that BLE applies to is probed, and every car read as `pluggedIn is False` departs (`onDeparting(vin, True)`). If none is read that way, it logs INFO and no car departs.
- TWCSlave `_checkPlugState`: `observePlug` fires once when a plugged state (01/03/08) has held `UNPLUG_DEBOUNCE` after a 00 run that itself lasted at least `UNPLUG_DEBOUNCE`, whether or not that 00 was reported as an unplug (for example, an empty TWC since link-up). Track that with a new `_zeroHeld` flag, set when the 00 reaches the debounce and cleared once the plug is reported. The carried power-start plug evidence (`PLUG_EVIDENCE_WINDOW`) is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# test_presence_attribution.py (offered 47, actual 0 unless stated)
def test_single_candidate_inside_radius_wins():
def test_ble_pilot_match_picks_one_of_two():          # A pilot 47 ACSingleWireCAN, B reach only -> A, "BLE pilot match"
def test_two_pilot_matches_are_ambiguous():
def test_pilot_mismatch_means_another_charger():      # sole candidate pilot 32 -> (None, ...)
def test_fast_charger_is_never_the_twc():
def test_ble_reachable_beats_ble_silent_inside_radius():  # A reach, B inside only -> A
def test_read_unplugged_is_never_a_candidate():
def test_actual_current_must_match_while_drawing():   # actualAmps 30: candidate actual 12 -> not matched
def test_plugged_read_without_pilot_falls_through_to_reach():
# test_vehicle_presence.py
def test_vin_less_plug_with_one_candidate_comes_home_with_one_apply():
def test_vin_less_plug_two_candidates_attributed_by_pilot():
def test_ambiguous_plug_makes_nobody_home_and_logs_once(caplog):  # two plugs in one session -> one INFO
def test_two_sleeping_candidates_are_ambiguous_and_never_woken():  # probe reach True awake False for both; get_charge_state/wakeVehicle not called
def test_vin_less_unplug_departs_the_attributed_car():
def test_vin_less_unplug_with_two_presumed_cars_departs_the_one_read_unplugged():
def test_vin_reading_plug_is_left_to_the_proof():
def test_second_plug_report_for_an_attributed_twc_probes_nothing():
def test_leaving_home_clears_the_twc_attribution():
# test_twcslave.py: TestPlugDebounce
def test_plug_into_an_empty_twc_is_reported_after_the_debounce():   # 00 since link for 120 s, then 03 for 60 s -> observePlug once
```

Change `test_no_plug_report_without_a_reported_unplug` so that it covers only a 00 shorter than the debounce.

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `pickPluggedCar`, the tracker's VIN-less plug and unplug paths, and `_zeroHeld` in TWCSlave**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_presence_attribution.py tests/unit/test_vehicle_presence.py tests/unit/test_twcslave.py -q`.

- [ ] **Step 5: Commit**

Subject: `Attribute a VIN-less TWC's plug: single candidate or BLE pilot match`.

---

### Task 5: Departure restore: BLE right away, a remote fallback when BLE has gone, re-plug cancels

> **Superseded in part (user-directed, 2026-10-11):** the tracker (Task 2) holds presence only: `home` plus `basis` ("evidence" | "presumed"). There is no DEPARTING state. Implement this task as a **reconciler** on presence × held limit. "Departing" below means *not home while `_restorePending(vin)`* (`hasSaved and lastApplied != -1`). `DepartingRecord` keys off that condition, starting when a car goes not-home with a limit held. The held-limit-after-restart and BLE-retry rules need no special cases: a presumed car read unplugged calls `onDeparting`, the handler restores if anything is held, and the probe loop retries while held and reachable. Keep the constants, the 5-minute fallback, the remote-immediately-without-BLE rule and the tests, with names adapted (`DEPARTING` → "not home with a held limit").

**Files:**
- Modify: `lib/TWCManager/PresenceHandlers.py`, `lib/TWCManager/VehiclePresence.py`
- Test: `tests/unit/test_presence_handlers.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Produces, in `PresenceHandlers.py`:
  - `bleApplies(master, vin) -> bool`: TeslaBLE is loaded and `settings["Vehicles"][vin]["bleProven"]` is set. `VehiclePresence`'s default `bleApplies` uses it.
  - `departingHandler(master)` → `onDeparting(vin, unambiguous) -> bool`. If nothing is held (`not hasSaved or lastApplied == -1`), it returns False. If `bleApplies`, it queues the `localOnly` restore (carried). Otherwise it does what `departureHandler` does, immediately: `remoteOnly` if `hasRemoteChannel`. The `unambiguous` argument is kept for the signature. Task 4 always passes True, so its False branch can't be reached; leave that branch in place and don't write a test for it.
  - `departureHandler(master)`: unchanged. It is the remote restore, called by the tracker only as the BLE-gone fallback.
  - `arrivalHandler`: before anything else it calls `master.vehicleCommandQueue.cancel("applyChargeLimit", lambda t: t.get("vin") == vin and t.get("limit") == -1)`.
- In `VehiclePresence`:
  - Constants: `DEPARTING_PROBE_INTERVAL = 60`, `DEPARTING_PROBE_CAP = 1800`, `DEPARTING_SLOW_PROBE_INTERVAL = 600`, `BLE_GONE_RESTORE_AFTER = 300`.
  - `_departing: dict[vin, DepartingRecord]`, where `DepartingRecord` is a dataclass with `since: float`, `viaBle: bool`, `bleGoneSince: float | None = None` and `fallbackSent: bool = False`. It is created on entry to DEPARTING and dropped on exit.
  - `_restorePending(vin) -> bool` is `hasSaved and lastApplied != -1`, from `master.getNormalChargeLimit(vin)`.
  - While a car is DEPARTING with `viaBle`, a restore pending and no fallback sent yet, it gets a `_probe(vin, bleOnly=True)` every `DEPARTING_PROBE_INTERVAL` (every `DEPARTING_SLOW_PROBE_INTERVAL` once `since` is older than `DEPARTING_PROBE_CAP`). Reach False sets `bleGoneSince` if it isn't set; reach True clears it. When `now - bleGoneSince >= BLE_GONE_RESTORE_AFTER` and the restore is still pending, the tracker runs `onDeparture(vin, None)` once and sets `fallbackSent`. When the restore is no longer pending, probing stops. A car without BLE (`viaBle` False) is never probed.
  - **BLE restore retry (controller ruling, user-approved):** while DEPARTING with `viaBle`, a restore still pending, and a probe that finds BLE reachable, re-queue the `localOnly` restore (at most once per probe interval, and only if no `applyChargeLimit` -1 for that VIN is already queued). That covers a BLE restore that failed while the car stayed in range.
  - **Held limit after a restart (controller ruling, user-approved):** when discovery finds a PRESUMED car unplugged *and* `_restorePending(vin)` is true (TWCManager holds a limit on it from before the restart), the car goes to DEPARTING instead of NOT_HOME, so `onDeparting` runs the normal restore (BLE first, then the remote fallback). With nothing held, it stays NOT_HOME and nothing is sent, as before.

- [ ] **Step 1: Write the failing tests**

```python
# test_presence_handlers.py
def test_departing_ble_car_queues_one_local_restore():      # queued == [{"cmd":"applyChargeLimit","limit":-1,"vin":V1,"localOnly":True}]
def test_departing_non_ble_car_queues_one_remote_restore_now():  # bleProven False, Fleet token, prefer_ble -> remoteOnly True
def test_departing_non_ble_car_without_remote_channel_queues_nothing():  # ble_only
def test_departing_with_nothing_held_queues_nothing():
def test_arrival_cancels_a_pending_restore_first():
# test_vehicle_presence.py
def test_ble_gone_for_five_minutes_sends_one_remote_restore():  # probes fail from t=0; at t=299 no onDeparture; at t>=300 exactly one
def test_ble_gone_fallback_needs_a_remote_channel():       # with the real departureHandler and ble_only: nothing queued
def test_ble_restore_done_stops_probing():                 # lastApplied -> -1: no further due times for V1
def test_replug_before_fallback_cancels_it():              # plugState(True,"ble") at t=120 -> HOME; no onDeparture ever
def test_reachable_probe_resets_the_gone_timer():
def test_departing_probes_slow_after_the_cap():
def test_non_ble_departing_car_is_never_probed():
def test_failed_ble_restore_retried_while_still_reachable():  # restore fails; next reachable probe re-queues one localOnly restore; none while one is queued
def test_presumed_car_found_unplugged_with_held_limit_departs_and_restores():  # saved (True,100,50): DEPARTING + one restore
def test_presumed_car_found_unplugged_with_nothing_held_goes_not_home():       # saved (True,100,-1): NOT_HOME, nothing queued
```

Move `TestDepartAndReturnThroughTheQueue` here. It now runs unplug → DEPARTING → plug evidence → HOME through the real handlers and the queue, and asserts that the HOME apply replaces the restore.

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `bleApplies`, the handler changes, `DepartingRecord`, the BLE-only probe schedule and the fallback timer**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_presence_handlers.py tests/unit/test_vehicle_presence.py -q`.

- [ ] **Step 5: Commit**

Subject: `Restore on unplug over BLE, then remotely once BLE has been gone 5 min`.

---

### Task 6: Discovery on wake: every command path reads before it acts

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py` (`discover`), `lib/TWCManager/Vehicle/TeslaBLE.py`, `lib/TWCManager/Vehicle/TeslaAPI.py`, `lib/TWCManager/Vehicle/Telemetry.py`
- Test: `tests/unit/test_teslable_presence.py`, `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_telemetry_timers.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Produces: `VehiclePresence.discover(vin, pluggedIn: bool | None, source: str, inside: bool | None = None, fastCharger: bool = False) -> bool`. It runs synchronously, is record-only (it calls `observePlugState(..., edge=False)` and `observeLocation` for the values it's given) and does no I/O. It returns False when `pluggedIn is False`, when `fastCharger` is set, or when `inside is False and not bleReachable(vin)`. Otherwise it returns True. Callers use it only for applies with `limit != -1` and for charge starts. A restore is never gated.
- TeslaBLE:
  - `get_charge_state` reports every successful read with `observePlugState(vin, pluggedIn, "ble", fastCharger=fastChargerPresent is True)` when `pluggedIn` isn't None.
  - `_readChargeLimit` becomes `_readChargeState(vin) -> dict | None`. It keeps the breaker check and gives the limit as `["chargeLimit"]`.
  - In `applyChargeLimit`, for `limit != -1`, after the read (or the telemetry lookup, which uses `telemetryPluggedIn` as its plug value): if presence exists and `not presence.discover(vin, plugged, source)`, send nothing, count the car as skipped, log INFO `"%s is not plugged in here; charge limit not sent"`, and leave `_stopTryingToApplyLimit` unset.
  - A start whose output `_is_already_satisfied` with "disconnected" reports `observePlugState(vin, False, "ble")`.
- TeslaAPI:
  - `update_vehicle_data` reports `observePlugState(vin, charging_state != "Disconnected", "api", fastCharger=charge.get("fast_charger_present") is True)` when `charging_state` is present.
  - `CarApiVehicle.lastVehicleDataFetch`: a new attribute, set to `time.monotonic()` by every successful `update_vehicle_data`.
  - `applyChargeLimit`, for `limit != -1` and per vehicle after `update_charge`: if `not presence.discover(vin, plugged, "api", inside=vehicle._locationAtHome if lastVehicleDataFetch changed during this call else None, fastCharger=...)`, it skips the vehicle. Here `plugged` is False for `"Disconnected"`, None for `"Unknown"`, and True otherwise. There is no extra `update_location()` call: an API read already includes location, a BLE read is strong, and telemetry pushes its location.
  - `car_api_charge` puts the same gate after its `update_charge`/`update_location`, ahead of the carried `"Disconnected"/"Complete"` skip.
- Telemetry `_reportPlug(vehicle, previous, pluggedIn)`: the first bool value (`previous` isn't a bool) is reported with `observeTelemetryPlug(vin, value, edge=False)`, and a change with `edge=True`. This replaces 94cf1c5's "the retained value is not a change".

- [ ] **Step 1: Write the failing tests**

```python
def test_ble_apply_to_a_car_read_as_unplugged_sends_nothing():   # charging-set-limit never sent; presence.state -> DEPARTING after runPass (was HOME)
def test_ble_restore_is_never_gated():                           # limit -1 with read unplugged -> charging-set-limit sent
def test_ble_read_reports_plug_state():                          # observePlugState called with (V1, True, "ble", fastCharger=False)
def test_ble_start_answered_disconnected_reports_unplugged():
def test_api_vehicle_data_reports_plug_and_fast_charger():
def test_presumed_car_found_away_on_the_fleet_path_gets_nothing():  # PRESUMED, BLE breaker open, Fleet read: Disconnected + outside -> no set_charge_limit POST; after runPass state NOT_HOME
def test_presumed_plugged_car_on_the_fleet_path_gets_the_limit():
def test_api_charge_start_skips_a_car_at_a_supercharger():        # fast_charger_present True -> no charge_start
def test_retained_telemetry_value_is_reported_once_as_a_read():   # first value -> observeTelemetryPlug(V, True, edge=False); same value again -> nothing
def test_telemetry_change_is_reported_as_an_edge():
def test_discover_returns_false_outside_radius_without_ble():
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `discover`, the TeslaBLE/TeslaAPI reports and gates, and the Telemetry initial-value report**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_teslable_presence.py tests/unit/test_teslaapi_presence.py tests/unit/test_telemetry_timers.py tests/unit/test_vehicle_presence.py -q`.

- [ ] **Step 5: Commit**

Subject: `Read before acting: a car read as unplugged or away gets nothing`.

---

### Task 7: HOME is the only "home": wakes, policy-wide applies, HomeAssistant, Fleet EVSEs, counts

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`car_api_available`), `lib/TWCManager/Vehicle/HomeAssistant.py`, `lib/TWCManager/EVSEController/TeslaAPIController.py`
- Test: `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_homeassistant_presence.py`, `tests/unit/test_teslaapi_controller_presence.py` (new; branch 2 has no controller tests, and branch 5's `ace0fef` creates `test_teslaapi_controller.py`, so a separate file avoids an add/add conflict in Task 11)

**Interfaces:**
- Consumes: `isHome` and `isPluggedHome` (Task 2).
- `car_api_available` wake loop: `if not vehicle.atHome: continue`. The `vehicle.lat != 10000` clause goes away, because presence is the authority.
- HomeAssistant: `_atHome(self, v) -> bool` returns `presence.isHome(v.vin)` when `master.vehiclePresence` exists and `v.vin` is set, and `v.at_home` otherwise. It is used in `car_api_charge`, `applyChargeLimit`, `numCarsAtHome` and `minBatteryLevelAtHome`.
- `TeslaAPIController.allEVSEs`: lists a vehicle only if `presence.isPluggedHome(v.VIN)`, or `v.atHome` when there is no presence. A presumed car gets no Fleet EVSE, because an EVSE sends rates without reading first.
- `numCarsAtHome`, `minBatteryLevelAtHome`, `updateChargeAtHome` and `vehicleScheduledChargingPending` keep reading `atHome`, which now counts HOME and PRESUMED cars.

- [ ] **Step 1: Write the failing tests**

```python
def test_asleep_plugged_car_is_woken_to_charge():         # HOME, ready() False -> wakeVehicle called
def test_asleep_unplugged_car_is_never_woken():           # NOT_HOME with lat 10000 -> wakeVehicle not called
def test_departing_car_is_never_woken():
def test_counts_include_only_plugged_or_presumed_cars():  # V1 HOME, V2 NOT_HOME, V3 DEPARTING -> numCarsAtHome == 1; minBatteryLevelAtHome == V1.batteryLevel
def test_update_charge_at_home_skips_unplugged_cars():
def test_scheduled_charging_pending_ignores_unplugged_cars():
def test_ha_policy_wide_apply_skips_a_departing_car():     # set_value not called
def test_ha_charge_uses_presence_over_its_own_location():
def test_fleet_evse_only_for_a_plugged_home_car():         # HOME -> listed; PRESUMED, DEPARTING -> not listed
def test_policy_wide_apply_skips_departing_on_every_channel():  # VehiclePriority(prefer_ble) + TeslaBLE + TeslaAPI + HA; DEPARTING V1 -> no sendCommand, no POST, no set_value
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement the wake rule, `_atHome` in HomeAssistant and the EVSE filter**

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `HOME is the single meaning of at home for wakes, applies and EVSEs`.

---

### Task 8: Send charge commands to the car the plug evidence names

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py`, `lib/TWCManager/TWCSlave.py`, `lib/TWCManager/Vehicle/TeslaAPI.py` (`car_api_charge`), `lib/TWCManager/Vehicle/TeslaBLE.py` (`car_api_charge`), `lib/TWCManager/Vehicle/HomeAssistant.py` (`car_api_charge`)
- Test: `tests/unit/test_twcslave.py`, `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_teslable_presence.py`, `tests/unit/test_homeassistant_presence.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Consumes: `vinForTwc(twc)` (Task 4), `isHome` and `bleReachable` (Task 2).
- `VehiclePresence.broadcastVINs() -> list[str]`: the known VINs, sorted, that are `isHome(v)` or here (`_inside` True or `bleReachable(v)`). A car that is neither is never included. **Also excluded (user-approved, 2026-10-11):** a car with evidence that it's plugged in somewhere else, i.e. attributed to another TWC (`vinForTwc`), or home with evidence and BLE-silent (on a UMC; `bleSilent` arrives in Task 12, so here use `isPluggedHome(v) and not bleReachable(v) and v not in twcVins()` only when a BLE contact failure is recorded). A purely presumed car stays included until its first read gives evidence. Test: `test_vin_less_broadcast_skips_a_car_plugged_in_elsewhere`.
- `TWCSlave._chargeVIN() -> str | None`: `currentVIN`, else `plugVIN` when it is neither None nor `NON_TESLA`, else `master.vehiclePresence.vinForTwc(self._presenceKey())`, else None. It replaces `self.currentVIN` in the `startCarsCharging`, `stopCarsCharging` and `cancelStopCarsCharging` calls.
- `TeslaAPI.car_api_charge(task)`: `vin = task.get("vin")`. The targets are that vehicle alone, or for `vin` None the vehicles in `presence.broadcastVINs()` (every vehicle when there's no presence). It calls `car_api_available(charge=charge, vin=vin)`. The stop-path reset loop covers only the targets.
- `TeslaBLE.car_api_charge`, for `vin` None: `settings["Vehicles"]` ∩ `presence.broadcastVINs()`.
- `HomeAssistant.car_api_charge`: honours `task["vin"]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_goes_to_the_vin_the_twc_reads():                  # startCarsCharging called with V1 (currentVIN "")->plugVIN
def test_start_on_a_vin_less_twc_goes_to_its_attributed_car():
def test_unattributed_vin_less_start_broadcasts_to_candidates_only():  # V1 inside, V2 NOT_HOME outside -> only V1 commanded
def test_api_charge_with_a_vin_touches_no_other_car():          # charge_start POST only for V1; V2.update_charge not called
def test_ble_broadcast_skips_a_car_away_and_unplugged():
def test_ha_charge_with_a_vin_touches_no_other_car():
def test_broadcast_vins_never_include_an_away_unplugged_car():
```

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `broadcastVINs`, `_chargeVIN` and the `car_api_charge` targeting in the three modules**

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

Subject: `Charge commands go to the car the plug names, broadcasts to candidates`.

---

### Task 9: Tighten the default `atHomeRadius` to 1,000 ft

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py` (`is_location_home` and its comment), `lib/TWCManager/Vehicle/HomeAssistant.py` (`is_location_home`), `etc/twcmanager/config.json`, `etc/twcmanager/.testconfig.json`, `etc/twcmanager/demo.json` (comments: "The default value is 1000 feet"), `CHANGELOG.md` (v1.4.0)
- Test: `tests/unit/test_teslaapi_presence.py`, `tests/unit/test_homeassistant_presence.py`

**Interfaces:**
- Produces: a module constant `DEFAULT_AT_HOME_RADIUS_FEET = 1000` in TeslaAPI.py and another in HomeAssistant.py. Each module uses its own, so HomeAssistant doesn't import TeslaAPI.
- CHANGELOG line, under v1.4.0 Features, verbatim: `* (@MikeBishop) - Vehicle presence follows the charge cable: a car is home when it is plugged in here, and charge limits are applied only then and restored on unplug. The default atHomeRadius is now 1,000 ft (was 10,560 ft / 2 miles); configs that never set atHomeRadius get the tighter default, so set it explicitly (e.g. 10560) to keep the old radius.`

- [ ] **Step 1: Write the failing tests**

```python
def test_default_radius_is_1000_feet():   # home (0,0); a point 900 ft north -> True; 1100 ft -> False (1 deg = 364488.888 ft)
def test_explicit_radius_still_overrides():  # config atHomeRadius 10560: 5000 ft -> True
# the same two tests for HomeAssistant.is_location_home
```

- [ ] **Step 2: Run the tests and confirm they fail**
- [ ] **Step 3: Implement the constants, comments and CHANGELOG entry**
- [ ] **Step 4: Run the tests and confirm they pass**
- [ ] **Step 5: Commit**

Subject: `Default atHomeRadius to 1,000 ft`.

---

### Task 10: The spec's end-to-end scenarios, then the branch gate

**Files:**
- Test: `tests/unit/test_plug_presence_scenarios.py` (new). It wires a real `VehiclePresence` (FakeClock, `runPass` driven by the test), the real `PresenceHandlers`, a real `VehicleCommandQueue` drained synchronously, `VehiclePriority`, and a real `TeslaBLE` with `sendCommand`/`probePresence`/`_fetch_state_json` stubbed. It also wires a real `TeslaAPI` with `requests` stubbed, recording every POST URL.

**Interfaces:**
- Consumes everything above. It adds no library code. A failure here goes back to the task that owns the code.

- [ ] **Step 1: Write the scenario tests**

```python
def test_2026_10_11_unplug_ble_silence_inside_radius_policy_cycles_send_nothing():
    # HOME via BLE read, limit 50 held; TWC unplug -> DEPARTING; BLE restore fails (no reach);
    # location inside radius; 10 policy cycles of applyChargeLimit(50) (vin None) with prefer_ble and a Fleet token:
    assert ble_commands("charging-set-limit") == [] and fleet_posts("set_charge_limit") == []
    # BLE gone 5 min -> exactly one remote restore (limit -1), nothing else:
    assert fleet_posts("set_charge_limit") == [restore_of(V1)]
def test_plug_in_on_a_vin_twc_comes_home_with_one_apply():
def test_vin_less_single_candidate_plug_one_apply():
def test_vin_less_two_candidates_ble_pilot_one_apply():
def test_vin_less_ambiguous_plug_applies_to_nobody():
def test_supercharger_telemetry_plugged_is_not_home():
def test_unplug_restores_over_ble_at_once():
def test_replug_cancels_the_pending_remote_restore():
def test_startup_asleep_car_is_presumed_and_not_woken_until_charging_needs_it():
def test_startup_wake_finds_the_car_unplugged_and_sends_nothing():
def test_startup_wake_finds_the_car_plugged_and_starts_charging():
def test_gen2_steady_00_after_link_does_not_block_startup_charging():
def test_ble_silent_umc_car_with_telemetry_inside_radius_is_home():
def test_no_gps_source_plug_unplug_cycle_end_to_end():     # BLE + VIN-less TWC only; no telemetry, no API module
def test_fleet_only_unplug_one_remote_restore_plug_one_remote_apply():
def test_departing_car_is_never_presumed_present():
```

- [ ] **Step 2: Run them**

Run: `<PY> -m pytest tests/unit/test_plug_presence_scenarios.py -q`. Expected: PASS. Fix any failure in the owning task's code, with that task's commit style.

- [ ] **Step 3: Branch gate**

Run: `<PY> -m pytest tests/unit -q` → all passed, 0 failed.
Run: `<PY> -m black --check <every lib file changed since presence/2-charge-limits>` → clean.
Run: `git diff presence/2-charge-limits -- lib | grep -nE '^\+.*log.*(oken|Bearer)'` → review every hit. No hit may interpolate a token value.
Run: `git grep -nE 'ARRIVING|AWAY_AFTER_FAILED_PROBES|_failedProbes|_timeoutHome|presenceSources' presence/3-plug-presence -- lib` → no output (except the one warning string that names `presenceSources`).

- [ ] **Step 4: Commit**

Subject: `Test the plug-presence scenarios end to end, including 2026-10-11`.

---

## Branch `presence/4-fleet-rate-queue`

### Task 11: Rebase the Fleet rate queue onto the new branch 3

**Files:** conflict resolution only. Expect `lib/TWCManager/EVSEController/TeslaAPIController.py` to conflict (Task 7 changed the vehicle filter that `ace0fef`/`e5478df` rewrite), and possibly `TWCSlave.py`/`TeslaAPI.py` where Tasks 6/8 touched lines near the #694 code.

**Interfaces:**
- Produces: `presence/4-fleet-rate-queue`, with the 8 commits of `presence/2-charge-limits`…: `ace0fef 680c5ec 52837bd 03a47e2 e5478df 5bda833 806ec3b b7e1623` replayed. `presence/5-fleet-rate-queue` stays where it is. In a probe, rebasing onto the Task 1 tip was clean (996 passed).
- Resolution rule for `allEVSEs`: the list comprehension keeps #694's `v.VIN not in served and not (unknown and self._telemetryPluggedIn(v))` and Task 7's `isPluggedHome` test in place of `v.atHome`. Then run `tests/unit/test_teslaapi_controller.py` and `tests/unit/test_teslaapi_controller_presence.py`. A #694 test that builds vehicles without presence keeps `v.atHome`, and that's the no-presence fallback.

- [ ] **Step 1: Rebase**

```bash
git branch presence/4-fleet-rate-queue presence/5-fleet-rate-queue
git rebase --onto presence/3-plug-presence presence/4-arrive-depart presence/4-fleet-rate-queue
```

- [ ] **Step 2: Resolve with the rule above, black the conflicted lib files, then `git rebase --continue`**

- [ ] **Step 3: Verify**

Run: `<PY> -m pytest tests/unit -q` → all passed.
Run: `git log --oneline presence/3-plug-presence..presence/4-fleet-rate-queue` → 8 commits.

---

### Task 12: A BLE-silent car plugged in at home may get a Fleet EVSE

**Files:**
- Modify: `lib/TWCManager/VehiclePresence.py` (`bleSilent`), `lib/TWCManager/EVSEController/TeslaAPIController.py` (`allEVSEs`)
- Test: `tests/unit/test_teslaapi_controller.py`

**Interfaces:**
- Produces: `VehiclePresence.bleSilent(vin) -> bool`. It is True when `bleApplies(master, vin)` and the last recorded contact is a failure with no success within `BLE_REACH_MAX_AGE`.
- `allEVSEs`: a car that #694's `blind` or `unknown and telemetry-plugged` rule would exclude is listed anyway when `presence.isPluggedHome(vin)`, `presence.bleSilent(vin)` and `presence.vinForTwc` names no TWC for it, i.e. `vin not in` the `_twcVin` values. Expose that as `presence.isTwcAttributed(vin) -> bool`. With no presence, #694 is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_ble_silent_umc_car_gets_a_fleet_evse_beside_an_idle_vin_less_twc():   # real VehiclePresence: telemetry plugged + inside -> HOME -> nominated probe runs with probePresence unreachable -> bleSilent; unknown=True -> listed
def test_never_probed_car_is_not_ble_silent():   # no contact recorded -> bleSilent False -> #694 exclusion still applies
def test_ble_reachable_car_beside_a_vin_less_twc_gets_no_fleet_evse():
def test_car_attributed_to_a_vin_less_twc_gets_no_fleet_evse():
def test_without_presence_694_rules_are_unchanged():
```

- [ ] **Step 2: Run the tests and confirm they fail**
- [ ] **Step 3: Implement `bleSilent`, `isTwcAttributed` and the `allEVSEs` exception**
- [ ] **Step 4: Run the full suite and confirm it passes**

Run: `<PY> -m pytest tests/unit -q`.

- [ ] **Step 5: Commit**

Subject: `A BLE-silent car plugged in at home may get a Fleet API EVSE`.

---

## Branch `deploy/presence-3`

### Task 13: Merge token slots (#692) and port the presence code to the slot API

**Files:**
- Conflicts: mainly `lib/TWCManager/Vehicle/TeslaAPI.py`, resolved as in `.superpowers/deploy-presence-2-merge-report.md` items 1–4.
- Port: `lib/TWCManager/PresenceSources.py`, `lib/TWCManager/PresenceHandlers.py`, `lib/TWCManager/Vehicle/TeslaAPI.py` (`vehicleOnlineStates`), and the tests that 92dae4d touched
- Test: `tests/unit/test_plug_presence_scenarios.py` (a deploy-level class)
- Create: `.superpowers/deploy-presence-3-merge-report.md` (same shape as the presence-2 report)

**Interfaces:**
- Consumes: the token-slot API: `slotFor("read" | "command") -> TeslaTokenSlot | None`, `slot.accessToken`, `slot.verifyCert`, `vehicleListURL(slot)`, `slotRequestFailed(slot, req)` and `storeToken(...)` in tests.
- Port mapping (from 92dae4d): `apiSource` uses `api.slotFor("read") is None` in place of `not api.getCarApiBearerToken()`. `hasRemoteChannel` uses `api.slotFor("command") is None`. `vehicleOnlineStates` reads `slotFor("read")` and `vehicleListURL(slot)`, sends `slot.accessToken` and `verify=slot.verifyCert`, and on 401/403/410/412 calls `slotRequestFailed`.

- [ ] **Step 1: Branch and merge**

```bash
git branch deploy/presence-3 presence/4-fleet-rate-queue
git checkout deploy/presence-3 && git merge --no-ff feat/token-slots   # fe764ff
```

- [ ] **Step 2: Resolve the conflicts as in the presence-2 report, then commit the merge**

The subject is `Merge feat/token-slots (#692) into deploy/presence-3`, and the message lists each conflict and how it was resolved. Then run the suite. The failures here should all come from removed accessors.

- [ ] **Step 3: Port the code, then check for leftover accessors**

Try `git cherry-pick -n 92dae4d` and resolve it against the new sources and handlers. Then run:
`git grep -nE 'getCarApiBearerToken|getCarApiBaseURL|carApiBearerToken\b|\.baseURL|(self|api|carapi)\.verifyCert' -- lib tests | grep -v TeslaTokenSlot.py | grep -v '"carApiBearerToken"'`. Expected: no output.

- [ ] **Step 4: Add the deploy-level regression class**

```python
class TestDeployRegression20261011:
    @pytest.mark.parametrize("slots", ["fleet_command", "owner_read_only"])
    def test_departing_car_inside_radius_gets_nothing_on_any_channel(self, slots):
        # same sequence as test_2026_10_11_..., with api.storeToken(fleet_token()) or an Owner-only slot
        assert ble_commands("charging-set-limit") == [] and fleet_posts("set_charge_limit") == []
    def test_fleet_fallback_restore_needs_a_command_slot(self):  # Owner slot only -> hasRemoteChannel False -> no restore queued
```

- [ ] **Step 5: Gate and commit**

Run: `<PY> -m pytest tests/unit -q` → all passed.
Run `black` on the conflicted and ported lib files only.
Run the token-in-log check from Task 10 over `git diff presence/4-fleet-rate-queue -- lib`.
Commit subject: `Port the plug-presence code to the Tesla API token slots`.
Write `.superpowers/deploy-presence-3-merge-report.md`: conflicts, port sites, test count, and the same "things to watch on the box" section.

---

## Decisions this plan makes (the spec left them open)

- **States:** `HOME`, `PRESUMED` (no entry, or no evidence), `DEPARTING` (after unplug evidence) and `NOT_HOME` (discovery found it unplugged or away). `isHome` is HOME or PRESUMED; `isPluggedHome` is HOME only.
- **Plug evidence:** kept in memory per VIN (`PlugRecord`). It isn't persisted, so a restart falls back to presumption.
- **Evidence strength:**
  - TWC and BLE evidence is strong. A strong record younger than `STRONG_EVIDENCE_HOLD` (300 s) beats conflicting weak evidence, and a TWC naming the car right now beats a weak unplug.
  - The one exception is carried from branch 4: a TWC unplug is ignored while live TeslaMate says the car is plugged in.
  - "Here" means inside the radius, or BLE reachable within 300 s, or named by a TWC.
  - Weak plugged evidence is always recorded. It takes effect once the "here" evidence arrives, in whatever order the two come.
  - A car that becomes HOME on weak evidence gets one probe, so that `bleSilent` is meaningful.
- **Edge versus read:**
  - An unplug edge (a TWC unplug or a telemetry change) moves a presumed car to DEPARTING, with a restore.
  - A read showing unplugged moves a presumed car to NOT_HOME and sends nothing.
  - Any unplug evidence moves a HOME car to DEPARTING.
- **`presenceSources`:** dropped (with a warning if set). It was never released, and evidence strength is fixed, so an order means nothing.
- **Probes:** `nominate` is a sleep-safe discovery: a BLE body-controller probe, a charge read only if the car is awake, live telemetry, and the API only for a car that's online. It runs once at startup, on a VIN-less plug or unplug, for DEPARTING cars, and from the HTTP checkArrival endpoint. The location-era TWC nominations are removed.
- **Attribution:**
  - `PresenceAttribution.pickPluggedCar` compares the pilot against the TWC's `reportedAmpsMax`, within ±1 A, and requires `ACSingleWireCAN`.
  - A BLE-reachable candidate beats a BLE-silent one.
  - An ambiguous plug makes no car HOME and logs one INFO per plug session.
  - An ambiguous VIN-less unplug is settled by BLE charge reads. If no read settles it, no car departs.
- **TWCSlave:** a plug is reported after any held 00 (even one that wasn't reported as an unplug), so an empty TWC's first plug-in counts.
- **DEPARTING timing:** a BLE-only probe every 60 s, slowing to every 600 s after 30 min, only while a BLE restore is pending. The remote fallback goes after BLE has been unreachable for 300 s (N = 5).
- **Handlers:** the signatures don't change. `onDeparting` picks BLE (`localOnly`) or remote (`remoteOnly`) through `bleApplies`. The HOME handler first cancels any pending restore for the VIN. A PRESUMED → HOME transition runs no handler, because the policy-wide apply already covers that car.
- **Synchronous gate:** `VehiclePresence.discover(...)` is the read-before-act check in TeslaBLE and TeslaAPI. Restores are never gated.
- **Counts:** `numCarsAtHome` and `minBatteryLevelAtHome` count HOME and PRESUMED cars.
- **Fleet EVSE:** only for a car that is HOME, never one that is presumed. On branch 4, a BLE-silent HOME car is exempt from #694's VIN-less exclusions.
- **Branches:** `presence/4-fleet-rate-queue` (the rebased branch 5) and `deploy/presence-3`. The old `presence/3-presence-tracker`, `presence/4-arrive-depart`, `presence/5-fleet-rate-queue` and `deploy/presence-2` are kept.

## Follow-ups (not in this plan)

- **HomeAssistant departure restore:** HA can't act on the `-1` restore sentinel. User's direction (2026-10-11): once 1.4.0's combined fallback (IntegrationOrder) exists, one piece of code reads the stored outside limit and sends that explicit value through whichever channel the order picks, instead of each module interpreting `-1`. Until then, HA installs get no departure restore (documented limitation).
- Several cars on VIN-less TWCs: the offset-current fingerprint.
