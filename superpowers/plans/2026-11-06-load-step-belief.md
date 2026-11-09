# Load Step: Meter Steps Explained by Belief — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the vehicle watch's load step from firing on changes in *believed* charger load, and stop house-load falls from acting for a car believed charging.

**Architecture:** `LoadStep` samples raw meter consumption instead of consumption minus believed charger load. `Watch` keeps 120 s of believed charger load; a reported step that the belief moved through, in the same direction and by at least half the step's size, is explained and nothing acts. A fall acts for a car believed charging only when it is at least half that car's believed draw.

**Tech Stack:** Python 3, pytest, `requests_mock`.

**Spec:** `/home/mbishop/github/TWCManager/.claude/worktrees/charge-attribution-limit-logs-4afa23/.superpowers/specs/2026-11-06-load-step-belief-design.md`

**Where:** worktree `/home/mbishop/github/TWCManager/.claude/worktrees/fleet-backfill`, branch `feat/fleet-charge-backfill` (HEAD `6aac990b`). All paths below are relative to it. Tests run with `.venv/bin/python -m pytest`.

## Global Constraints

- No added delay to a real start or stop: hold length and threshold (`LoadStep`, `emsNoiseWatts`) unchanged.
- No more reads or polls than today in any case.
- Explanation applies only under `master.subtractChargerLoad`; without it, behaviour is today's.
- Window 120 s, time-based (not sample-count). Fraction one half, for both the explanation and the fall size. Both module constants with a comment saying why, not settings.
- Lib growth minimal; line budgets are targets. Remove `Watch.unexplainedWatts` (its only caller goes away).
- Comments explain why the code is as it is, never how it used to be.

## Review Focus

1. A belief change older than 120 s does not explain a step: a command sent 150 s before the meter rises still lets the rise act. (Task 1 test.)
2. Belief and meter moving in *opposite* directions never explain: one car's belief clearing while another car plugs in still lets the rise act. (Task 1 test.)
3. The fall filter covers a car read over BLE/feeds (`readNow` path), not only Fleet-only cars. (Task 2 test.)
4. A fall for a car believed charging but reporting 0 A (believed draw from a commanded rate) still acts when car-sized. Covered by the rule using `liveWatts`, which includes commanded rates; no extra test.
5. Known, accepted: two cars starting together, one commanded and one not, is explained when the commanded car's belief is at least half the combined rise. The uncommanded car is found at its next ordinary check. No test; note in the comment on the window.

---

### Task 1: Step on the meter; a matching belief change explains it

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`LoadStep` ~139-151, `Watch.__init__` ~155-165, `unexplainedWatts` ~313-318 removed, `loadSample` ~320-366)
- Test: `tests/unit/test_watch_load_step.py`

**Interfaces:**
- Produces: `LoadStep.size: float`, the absolute size in watts of the step `sample()` last reported (`watts - base` at the holding sample). `sample()` still returns `Optional[str]`.
- Produces: in `loadSample`, local `step` is `None` when explained; Task 2 reads `self._step.size`.
- Removes: `Watch.unexplainedWatts()`.

- [ ] **Step 1: Write the failing tests**

Add helpers and tests to `tests/unit/test_watch_load_step.py`. Fleet-only car via existing `fleetStep`; 240 V, power factor 1, so 32 A = 7680 W.

```python
def metered(requests_mock):
    # The meter sees the EVSE; the watch's belief is the charger load
    m, r, v, c, w, car = fleetStep(requests_mock)
    m.watch = w; m.subtractChargerLoad = True; m.getRealPowerFactor = lambda amps: 1
    return m, r, v, c, w, car

def feed(m, w, c, *watts):
    for x in watts: c.t += 30; m.setConsumption("t", x); w.loadSample()

def charging(v, amps):
    v.observe("chargingState", "Charging" if amps else "Complete", "FleetAPI"); v.observe("actualCurrent", amps, "FleetAPI")

def stepped(w):
    # The time of the load step a suspicion carries, if any
    return w._suspect.get(VIN, (None, None))[1]

def test_a_belief_clearing_after_the_meter_fell_is_no_rise(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); charging(v, 32)
    feed(m, w, c, 8200, 8200, 500, 500); assert stepped(w)                          # the stop's own fall
    w._suspect.clear(); charging(v, 0); feed(m, w, c, 500, 500, 500)
    assert stepped(w) is None

def test_a_belief_arriving_after_the_meter_rose_is_no_fall(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); feed(m, w, c, 500, 500)
    T = c.t + 30; feed(m, w, c, 8200, 8200); assert stepped(w) == T                 # an unexplained start acts
    w._suspect.clear(); charging(v, 32); feed(m, w, c, 8200, 8200, 8200)
    assert stepped(w) is None

def test_a_start_the_belief_leads_makes_no_step(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); feed(m, w, c, 500, 500)
    v.noteWrite("chargingState", "Charging", "FleetAPI"); v.noteWrite("chargeCurrentRequest", 32, "FleetAPI")
    feed(m, w, c, 500, 8200, 8200); assert stepped(w) is None

def test_a_belief_change_older_than_the_window_explains_nothing(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); feed(m, w, c, 500, 500)
    v.noteWrite("chargingState", "Charging", "FleetAPI"); v.noteWrite("chargeCurrentRequest", 32, "FleetAPI")
    feed(m, w, c, 500, 500, 500, 500, 500); feed(m, w, c, 8200, 8200); assert stepped(w)

def test_a_belief_falling_never_explains_a_rise(requests_mock):
    m, r, v, c, w, car = metered(requests_mock)
    other = m.vehicleRegistry.getOrCreate(VIN2, "t"); placeAt(m, other, HOME)
    for f, x in (("state", "online"), ("chargingState", "Charging"), ("actualCurrent", 32)): other.observe(f, x, "TeslaBLE")
    feed(m, w, c, 8200, 8200); w._suspect.clear()
    other.observe("actualCurrent", 0, "TeslaBLE"); other.observe("chargingState", "Complete", "TeslaBLE")
    feed(m, w, c, 15900, 15900); assert stepped(w)                                  # VIN plugged in as VIN2 stopped

def test_without_subtracting_charger_load_a_leading_belief_explains_nothing(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); m.subtractChargerLoad = False; feed(m, w, c, 500, 500)
    v.noteWrite("chargingState", "Charging", "FleetAPI"); v.noteWrite("chargeCurrentRequest", 32, "FleetAPI")
    feed(m, w, c, 500, 8200, 8200); assert stepped(w)
```

If `placeAt`/`VIN2` interplay in `test_a_belief_falling_never_explains_a_rise` needs the meter numbers adjusted (VIN2's 7680 W leaves after the first feed), keep the intent: belief down, meter up by a car's draw, rise acts.

Also add to `test_a_step_held_for_two_samples_is_reported_once`: after the sequence, `assert s.size == 1300`.

Delete `test_known_draw_is_subtracted_only_when_configured` (covered by the last test above). In the green-offer test (~line 83), replace the `unexplainedWatts` assertion with `assert m.getChargerLoad() == pytest.approx(36 * 240)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_watch_load_step.py -q`
Expected: the start-the-belief-leads, belief-clearing and `s.size` tests FAIL; others may pass.

- [ ] **Step 3: Implement**

In `Watch.py`:
- `LoadStep.sample`: set `self.size = abs(moved)` when it returns a step. Init `size = 0.0`.
- Module constants: `BELIEF_SECS = 120` (covers the 30–90 s a Fleet-only car's snapshots trail the meter, and a command leading it) and use `/ 2` for the half, explained in the same comment.
- `Watch.__init__`: `self._belief = collections.deque()` of `(at, watts)`, the step thread's alone.
- `loadSample`: `step = self._step.sample(self.master.getConsumption())`, record the belief (below), then `if step and self._explained(step): step = None`.
- Every sample under `master.subtractChargerLoad`: append `(now, master.getChargerLoad())` to `_belief` and drop entries with `at < now - BELIEF_SECS`. Without it, clear `_belief`.
- New `_explained(self, step) -> bool`: `False` if `_belief` is empty; else whether `latest - oldest` has the sign of `step` and magnitude `>= self._step.size / 2`.
- Delete `unexplainedWatts`. Update the comment at the top of `loadSample`: the meter steps, and a step the believed load moved through is the belief, not a car.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_watch_load_step.py tests/unit/test_watch_poll.py tests/unit/test_watch.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch_load_step.py
git commit -m "Step on the meter; a matching change in believed charger load explains a step"
```

---

### Task 2: A fall acts for a charging car only if car-sized

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`loadSample` car loop)
- Test: `tests/unit/test_watch_load_step.py`

**Interfaces:**
- Consumes: `self._step.size` (Task 1), `Watch.liveWatts(vin) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_fall_too_small_to_be_the_charging_car_is_ignored(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); charging(v, 32)
    feed(m, w, c, 8200, 8200, 6700, 6700); assert stepped(w) is None                # 1500 W < 3840 W

def test_a_car_sized_fall_while_charging_acts(requests_mock):
    m, r, v, c, w, car = metered(requests_mock); charging(v, 32)
    feed(m, w, c, 8200, 8200, 4000, 4000); assert stepped(w)                        # 4200 W >= 3840 W

def test_a_small_fall_reads_no_ble_car(caplog):
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 32, "TeslaBLE")
    w = m.watch = Watch(m, clock=c); m.getRealPowerFactor = lambda amps: 1
    step(m, w, c, 8200, 6700); assert " asked" not in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_watch_load_step.py -q -k "fall"`
Expected: the two "too small"/"small fall" tests FAIL.

- [ ] **Step 3: Implement**

In the `loadSample` car loop, before the `if not self._fleet(v)` branch (home cars only; the not-home branch acts on rises alone): skip the car when `step == "down" and self._step.size < self.liveWatts(v.vin) / 2`. One condition, both the `readNow` and `suspect` paths. Comment: a fall smaller than half what the car is believed drawing is the house, not this car stopping.

- [ ] **Step 4: Run the full unit suite**

Run: `.venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios -q`
Expected: all PASS. Check `git diff --stat main...` growth of `Watch.py` against `6aac990b`: net change should be small (target ≤ +10 lines).

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch_load_step.py
git commit -m "A load fall acts for a charging car only when it could be that car"
```
