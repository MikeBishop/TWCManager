# Expected-Rate Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A load rise counts as a possible start for a watched car only if it is at least half the rate that car starts at with nothing commanding it.

**Architecture:**
- Each car keeps its last 5 home plug-in amps samples. The samples live on `Vehicle` and are saved through `VehicleRegistry.toJSON`/`load`.
- `Watch._visit` takes the sample once per plug-in.
- `Watch.expectedWatts(v)` turns the samples into watts.
- `Watch.loadSample` and `_mayBeBack` skip a car whose expected rate the rise is too small for.

**Tech Stack:** Python 3, pytest, requests_mock (existing test helpers).

**Spec:** `.superpowers/specs/2026-11-07-expected-rate-filter-design.md` (approved 2026-11-07).

## Global Constraints

- Samples come only from a car at home and plugged in (`Presence.pluggedHere`). A reading of a car not plugged in reports the car's own maximum.
- One sample per plug-in, from its first reading. A plug-in starts after `since = max(unpluggedAt(v), arrivedAt(v))` (Presence). `markAt("plugIn")` is set only for anonymous TWC sessions, so it is not used.
- The sample is `v.latest("chargeCurrentRequest")` with `obs.at >= since`. No sample if `v.lastWrite("chargeCurrentRequest")` is newer than `since`, because then a command has touched the car's amps.
- Keep the last 5 samples. Expected watts = `master.convertAmpsToWatts(min(samples))`. No samples means expected 0, which filters nothing.
- Rule: a car is skipped for an "up" step when `self._step.size < self.expectedWatts(v) / 2`. Skipped means no suspicion, no `readNow`, no `_waking`, and no `_backStep`.
- Falls, the belief explanation, `notWatched` and cadence reads are unchanged.
- Comments explain why the code is as it is, never history. No changelog entry: this is unreleased work.

## Review Focus

1. **Restart mid-charge:** the field observations are gone, so `since` falls back to NEVER. The saved `since` must stop a re-sample of the same session. Test in Task 1.
2. **A car that charged away and was then read at home before any unplug reading:** an away-charger amps value must not be sampled. `arrivedAt` bounds it. Test in Task 2.
3. **Multi-car:** one car's samples must not filter another car with no samples. Test in Task 3.
4. **BLE-watched car:** the `readNow` path is filtered the same way. Test in Task 3.
5. **Corrupt saved blob:** non-numeric, negative, or more than 5 samples are dropped on load, never raised. Test in Task 1.

---

### Task 1: Home amps samples on Vehicle, saved with the registry

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Vehicle.py`
- Modify: `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py` (`toJSON`, `_loadOne`)
- Test: `tests/unit/test_registry_vehicle.py`

**Interfaces:**
- Produces:
  - `HOME_AMPS_KEPT = 5` (Vehicle.py).
  - `Vehicle.noteHomeAmps(amps: float, since: float) -> bool`: True if recorded. False when `since <= ` the stored since, or `amps` isn't a positive number.
  - `Vehicle.homeAmps() -> List[float]`: oldest first.
  - Both are guarded by `self._lock`.
  - The registry entry gains `"homeAmps": {"amps": [...], "since": float}` only when there are samples.

- [ ] **Step 1: Write the failing tests**

```python
def test_home_amps_keep_the_last_five_one_per_plug_in():
    r = VehicleRegistry(clock=lambda: 1000.0); v = r.getOrCreate(VIN, "t")
    for i, amps in enumerate((48, 32, 48, 16, 48, 40)):
        assert v.noteHomeAmps(amps, since=100 + i)
    assert v.homeAmps() == [32, 48, 16, 48, 40]
    assert not v.noteHomeAmps(6, since=105)                 # same plug-in
    assert not v.noteHomeAmps(0, since=200)

def test_home_amps_survive_a_save_and_load_and_keep_their_plug_in():
    r = VehicleRegistry(clock=lambda: 1000.0); v = r.getOrCreate(VIN, "t"); v.noteHomeAmps(48, since=500)
    r2 = VehicleRegistry(clock=lambda: 1000.0); r2.load(r.toJSON()); v2 = r2.get(VIN)
    assert v2.homeAmps() == [48] and not v2.noteHomeAmps(6, since=float("-inf"))  # a restart's NEVER

def test_unreadable_saved_home_amps_are_dropped():
    blob = {"version": 1, "vehicles": {VIN: {"homeAmps": {"amps": ["x", -3, 32, 32, 32, 32, 32, 40], "since": "y"}}}}
    r = VehicleRegistry(clock=lambda: 1000.0); r.load(blob)
    assert r.get(VIN).homeAmps() == [32, 32, 32, 32, 40]
```

Use the file's existing `VIN` and constructor style. Adjust the constructor call to match how the file builds registries.

- [ ] **Step 2:** Run `pytest tests/unit/test_registry_vehicle.py -k home_amps -v`. Expected: FAIL, no `noteHomeAmps`.
- [ ] **Step 3:** Implement. On load:
  - keep only positive numbers, the last 5;
  - a non-number `since` becomes NEVER;
  - restore through a private setter, not `noteHomeAmps`, so the loaded since is kept even when it is NEVER.
- [ ] **Step 4:** Run the Step 2 tests plus `pytest tests/unit/test_registry_vehicle.py tests/unit/test_vehicle_appearance.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Keep each car's home plug-in amps with the registry`.

### Task 2: Watch takes the sample and knows the expected rate

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`_visit`, new `_noteHomeAmps`, new `expectedWatts`)
- Test: `tests/unit/test_watch_load_step.py`

**Interfaces:**
- Consumes: Task 1's `noteHomeAmps` and `homeAmps`.
- Produces: `Watch.expectedWatts(v) -> float` (0.0 with no samples).
- `_noteHomeAmps(v, now)` runs in `_visit` only for watched cars (`why is None`).

- [ ] **Step 1: Write the failing tests** (use `homeCar`-style setup with `m.getRealPowerFactor = lambda a: 1`):

```python
def test_the_first_home_plug_in_reading_is_the_expected_rate():
    m, v, c, w = homeCar(None); v.observe("chargingState", "Disconnected", "TeslaBLE"); c.t += 60
    v.observe("chargingState", "Stopped", "TeslaBLE"); v.observe("chargeCurrentRequest", 48, "TeslaBLE")
    w.pass_(); assert v.homeAmps() == [48] and w.expectedWatts(v) == pytest.approx(48 * 240)
    v.observe("chargeCurrentRequest", 32, "TeslaBLE"); w.pass_(); assert v.homeAmps() == [48]  # same plug-in

def test_a_rate_after_an_amps_command_is_no_sample():
    m, v, c, w = homeCar(None); v.observe("chargingState", "Disconnected", "TeslaBLE"); c.t += 60
    v.noteWrite("chargeCurrentRequest", 6, "TeslaBLE"); v.observe("chargingState", "Stopped", "TeslaBLE")
    v.observe("chargeCurrentRequest", 6, "TeslaBLE"); w.pass_(); assert v.homeAmps() == []

def test_an_unplugged_or_away_reading_is_no_sample():
    m, v, c, w = homeCar(None); v.observe("chargingState", "Disconnected", "TeslaBLE")
    v.observe("chargeCurrentRequest", 48, "TeslaBLE"); w.pass_(); assert v.homeAmps() == []   # unplugged: its own max
    placeAt(m, v, AWAY); c.t += 60; v.observe("chargingState", "Stopped", "TeslaBLE")
    v.observe("chargeCurrentRequest", 16, "TeslaBLE"); w.pass_(); assert v.homeAmps() == []   # away charger

def test_an_away_chargers_rate_read_before_arrival_is_no_sample():
    # Review Focus 2: plugged in away, then read home before any unplug reading
    ...  # observe 16 A plugged while AWAY, then placeAt HOME with a newer arrival mark
         # and no newer chargeCurrentRequest: pass_ records nothing
```

Write the last test fully. Get the arrival from whatever sets `markAt("driveEnd")`/`"outside"` in `placeAt`; check `reconcile_helpers.placeAt`.

- [ ] **Step 2:** Run `pytest tests/unit/test_watch_load_step.py -k "sample or expected_rate" -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `_noteHomeAmps`:
  - require `pluggedHere(master, v)`;
  - `since = max(unpluggedAt(v), arrivedAt(v))`;
  - `obs = v.latest("chargeCurrentRequest")` with `obs.at >= since`;
  - `w = v.lastWrite("chargeCurrentRequest")` is None or `w.at < since`;
  - then `v.noteHomeAmps(obs.value, since)`, and on True `self._saved(True)`.

  Implement `expectedWatts`: `convertAmpsToWatts(min(v.homeAmps()))`, else 0.0.
- [ ] **Step 4:** Run the Step 2 tests plus the whole `tests/unit/test_watch*.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Learn the rate a car starts at from its home plug-ins`.

### Task 3: A rise too small for a car does nothing for it

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`loadSample`, `_mayBeBack(now, size)`)
- Test: `tests/unit/test_watch_load_step.py`, `tests/unit/test_watch.py`

**Interfaces:**
- Consumes: Task 2's `expectedWatts`.
- `_mayBeBack` gains `size: float` and skips a car when `size < self.expectedWatts(v) / 2`. In `loadSample`, at the top of the car loop for `step == "up"`, the same test `continue`s.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_rise_too_small_for_the_car_opens_no_suspicion(requests_mock):
    m, r, v, c, w, car = fleetStep(requests_mock); v.noteHomeAmps(48, since=0)
    step(m, w, c, 500, 3000); assert VIN not in w._suspect                 # 2.5 kW < 5.76 kW
    step(m, w, c, 3000, 500); T = c.t; step(m, w, c, 500, 12000); assert w._suspect[VIN][0] == T

def test_with_no_samples_a_small_rise_suspects_as_before(requests_mock):
    m, r, v, c, w, car = fleetStep(requests_mock); step(m, w, c, 500, 2500); assert VIN in w._suspect

def test_one_cars_samples_filter_only_that_car(requests_mock):
    ...  # VIN with 48 A samples, VIN2 watched with none: a 2.5 kW rise suspects VIN2 only

def test_a_small_rise_reads_no_ble_car_with_a_known_rate():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); w.pass_(); runPending(r.ble); reads = bleReads(m); v.noteHomeAmps(48, since=0)
    step(m, w, c, 500, 2500); w.pass_(); runPending(r.ble); assert reads.count == 0
```

In `test_watch.py`, next to `test_a_rise_reads_an_api_only_car_away_once_it_could_be_back`, add the 2026-11-07 case:

```python
def test_a_small_house_rise_leaves_the_back_window_for_the_plug_in(requests_mock):
    m, r, v, c, car = apiOnly(requests_mock, at=HOME); northOfHome(m, v, 5, c.t); v.observe("state", "online", "FleetAPI")
    v.noteHomeAmps(48, since=0); w = Watch(m, clock=c); w.pass_(); runPending(r.cloud); later(m, v, c, 400)
    rise(m, w, c, 500, 3000); w.pass_(); runPending(r.cloud); assert paid(requests_mock)[0] == 0
    later(m, v, c, 840); rise(m, w, c, 3000, 14400); w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] == 1 and P.presence(m, v) == P.HOME
```

Before Task 3's code, this test must fail on its second assert: the 3 kW rise spends the window. Confirm that as the RED.

- [ ] **Step 2:** Run the new tests. Expected: FAIL as described.
- [ ] **Step 3:** Implement both tests. Update the `loadSample` and `_mayBeBack` comments to say why a small rise is the house (one line each).
- [ ] **Step 4:** Full unit suite: `pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios -q`. Expected: all pass.
- [ ] **Step 5:** Commit: `Count a load rise only for a car it is big enough to be starting`.

### Task 4: Replay check

- [ ] Run `pollsim.py` from the scratchpad, `bin/pollsim.py data2/load-new.jsonl data2/teslamate.log`, with its filtered row at 0.5 × 48 A × 240 V. Report the poll-active share of home-awake-idle time.
  - The pre-change replay gave 25% from 2 suspicions.
  - One of those (21:37:18) is a belief-drop artifact that the meter-stepped code already explains, so the expected result is about one suspicion.
- [ ] Record the result in the ledger. No commit.
