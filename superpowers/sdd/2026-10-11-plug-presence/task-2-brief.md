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

