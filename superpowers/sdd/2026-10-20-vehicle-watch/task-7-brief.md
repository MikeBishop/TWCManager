### Task 7: The consumption step

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`, `lib/TWCManager/TWCManager.py:393-415` (`check_green_energy`)
- Test: `tests/unit/test_watch_load_step.py`

**Interfaces:**
- Produces:
  ```python
  class LoadStep:
      def __init__(self, thresholdWatts: float): ...
      def sample(self, watts: float, now: float) -> Optional[str]   # "up" | "down" | None, after a step held for two samples
  Watch.loadSample(self, now: Optional[float] = None) -> None       # computes unexplained watts, feeds LoadStep, calls readNow
  Watch.unexplainedWatts(self) -> float
  ```
- `unexplainedWatts` = `master.getConsumption()` minus, only when `master.subtractChargerLoad`, the known draw: `master.getChargerLoad()` (Gen2), each Gen3 unit's `currentAmps` × its voltage, and each watched car's `actualCurrent` × `VehicleEndpoint.currentVoltage` while `situation == HOME_CHARGING`.
- Threshold watts = `max(emsNoiseWatts, carMinAmps × V × phases)` with `carMinAmps = 5 if phases < 3 else 1`, `V = config.defaultVoltage` (240), `phases = config.numberOfPhases` (1).
- On `"up"`: candidates are watched cars in `HOME_AWAKE`, `UNKNOWN` or whose presence is PRESUMED with `asleep(v)` not True, ordered HOME first; `readNow(vin, "load step up")` for the first, then the next only if the first's read did not report Charging (checked on the following pass). On `"down"`: `readNow` for each car in `HOME_CHARGING`. Debounce: no triggered read for a car within 300 s of its last triggered read.
- `check_green_energy()` calls `master.watch.loadSample()` after the EMS loop when `master.watch.settings()["emsTrigger"]`.
- Behaviour change (named): (h) a consumption step makes a read.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_step_held_for_two_samples_is_reported_once():
    s = LoadStep(1200.0)
    assert [s.sample(w, t) for t, w in enumerate([500, 500, 2000, 2000, 2000, 700, 700])] == [None, None, None, "up", None, None, "down"]

def test_a_dryer_with_no_awake_watched_car_triggers_no_read():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m); m.setConsumption("t", 500); w.loadSample()
    m.setConsumption("t", 2500); w.loadSample(); c.t += 30; w.loadSample(); w.pass_(); runPending(r.ble)
    assert reads.count == 0

def test_a_step_up_reads_the_awake_home_car_and_a_step_down_reads_the_charging_one():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); w.pass_(); runPending(r.ble)                # the wake event read
    reads = bleReads(m, charging="Charging", amps=20)
    m.setConsumption("t", 500); w.loadSample(); m.setConsumption("t", 5300); w.loadSample(); c.t += 30; w.loadSample()
    w.pass_(); runPending(r.ble); assert reads.count == 1 and situation(m, v) == HOME_CHARGING
    reads.charging = "Complete"
    m.setConsumption("t", 500); w.loadSample(); c.t += 30; w.loadSample(); w.pass_(); runPending(r.ble)
    assert reads.count == 2 and v.value("chargingState") == "Complete"

def test_known_draw_is_subtracted_only_when_configured():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    v.observe("chargingState", "Charging", "TeslaBLE"); v.observe("actualCurrent", 20, "TeslaBLE")
    w = Watch(m, clock=c); m.setConsumption("t", 6000)
    m.subtractChargerLoad = False; assert w.unexplainedWatts() == 6000
    m.subtractChargerLoad = True;  assert w.unexplainedWatts() == pytest.approx(6000 - 20 * 240)
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** `LoadStep`, `unexplainedWatts`, `loadSample`, and the `check_green_energy` call (guarded: `getattr(master, "watch", None)`).

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py lib/TWCManager/TWCManager.py tests/unit/test_watch_load_step.py
git commit -m "A consumption step makes the watch read the car that may have caused it"
```

---

