### Task 4: The watch: who, what situation, Ring 1 on a clock

**Files:**
- Create: `lib/TWCManager/Vehicle/Watch.py`
- Modify: `lib/TWCManager/Vehicle/Reconcile/Reconciler.py:124-125`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Consumes: `Presence.decide/presence/asleep/drivingNow/twcVinAt`, `Vehicle.syncSource`, `TeslaBLE.ping(vin, scan)`, `TeslaBLE.canScan()`, `TeslaAPI.onlineState(vehicle)`, `HomeAssistant` attachment's `refresh_from_home_assistant(api)`, `VehicleReconciler.submitJob`.
- Produces:
  ```python
  # Watch.py
  HOME_ASLEEP, HOME_AWAKE, HOME_CHARGING, AWAY_ASLEEP, AWAY_AWAKE, UNKNOWN = (
      "homeAsleep", "homeAwake", "homeCharging", "awayAsleep", "awayAwake", "unknown")
  DEFAULTS = dict(enabled=True, homeAsleepSecs=900, homeAwakeSecs=240, awayAsleepSecs=1800,
      awayAwakeSecs=300, chargingReadSecs=300, cloudChargingReadSecs=900,
      sleepCourtesySecs=1200, scanAwaySecs=150, monthlyBudgetUSD=3.0, emsTrigger=True,
      emsNoiseWatts=300)
  def notWatched(master, v) -> Optional[str]   # None = watched; else "anonymous" | "named by TWC <id>" | "covered by <feed>" | "disabled"
  def situation(master, v) -> str
  class Watch:
      def __init__(self, master, clock=time.time): ...
      def settings(self) -> dict                 # DEFAULTS overlaid with config["watch"]
      def pass_(self, now: Optional[float] = None) -> None   # the control tick
      def status(self, v) -> dict                # {"watched": bool, "why": str, "last": str, "lastAt": float, "nextAt": float}
  ```
  `VehicleReconciler.submitJob(self, key, kind, run, worker="ble") -> bool`: `worker="cloud"` puts on the cloud queue.
- `situation`: `UNKNOWN` when `asleep(v)` is None and no state is known; `HOME_*` when `presence == HOME`; `AWAY_*` for NOT_HOME and PRESUMED; `*_ASLEEP` when `asleep(v) is True` or the feed's/cloud's last state is `offline`; `HOME_CHARGING` when HOME, not asleep and `chargingState == "Charging"`.
- Ring 1 source per car, in order: the BLE ping when `TeslaBLE` is loaded and `canScan()` or the tool binary is present; else `TeslaAPI.onlineState` when the car has a `TeslaAPI` attachment; else the HA refresh when it has a `HomeAssistant` attachment; else nothing (the car is watched but has no status source; `status()["why"]` says so).
- Scheduling: per car, `_due[vin]["status"]` is the next time; a job is submitted when `now >= due` and `vin not in _inflight`; the job's completion (the queue's report, or the job's own `finally`) clears `_inflight` and sets the next due from `cadence(situation)`. The memo `_seen[vin]` (situation, presence, `markAt("plugIn")`, `chargingState`) is refreshed every pass and compared; Task 5 uses the comparison.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_watch.py`; `setup()` from `test_limit_reconciler` gives an inline reconciler whose BLE/cloud queues run on `runPending`)

```python
def test_a_twc_named_car_and_a_feed_covered_car_are_not_watched():
    m, r, v, c = setup(here=False)
    assert notWatched(m, v) is None
    m.vehicleRegistry.observeTwcVin("8244", VIN); slave = gen2Slave(m, "8244", state=0x03)   # tests/unit/gen2_helpers
    assert notWatched(m, v).startswith("named by")
    m2, r2, v2, c2 = setup(here=False)
    v2.observe("state", "online", "TeslaMateVehicle"); liveFeed(m2, "TeslaMateVehicle")     # registers liveness returning now
    assert notWatched(m2, v2) == "covered by TeslaMateVehicle"

def test_situations():
    m, r, v, c = setup(here=False)
    assert situation(m, v) == UNKNOWN
    placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    assert situation(m, v) == HOME_ASLEEP
    c.t += 10; v.observe("state", "online", "TeslaBLE")
    assert situation(m, v) == HOME_AWAKE
    v.observe("chargingState", "Charging", "TeslaBLE")
    assert situation(m, v) == HOME_CHARGING
    placeAt(m, v, AWAY); v.observe("state", "offline", "FleetTelemetryMQTT")
    assert situation(m, v) == AWAY_ASLEEP

def test_ring_one_pings_on_the_cadence_and_not_before():
    m, r, v, c = setup(here=False, ble=True)             # a TeslaBLE module with ping stubbed to answer asleep
    placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); pings = bleAnswers(m, asleep=True)
    w.pass_(); runPending(r.ble)
    assert pings.count == 1
    c.t += 899; w.pass_(); runPending(r.ble); assert pings.count == 1
    c.t += 1;   w.pass_(); runPending(r.ble); assert pings.count == 2

def test_cloud_status_check_for_a_car_ble_cannot_reach(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="asleep", at=AWAY)   # test_command_path_parity.FleetCar
    attachFleet(m, v, car)                                # the parity file's way of listing the car on the Fleet slot
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud)
    assert counts(requests_mock)["free"] == 1 and paid(requests_mock) == (0, 0, 0)
    assert v.value("state") == "asleep"

def test_one_watch_job_in_flight_per_car_and_commands_are_not_starved():
    m, r, v, c = setup(here=False, ble=True); cars = [v] + [m.vehicleRegistry.getOrCreate(x, "t") for x in (VIN2, VIN3, VIN4)]
    for x in cars: placeAt(m, x, HOME); x.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); w.pass_(); w.pass_()
    assert len(entries(r.ble)) == 4                       # one per car, not eight
    m.desired.set(VIN, CHARGE_LIMIT, 80, "policy"); r.pass_()
    order = [e.kind if hasattr(e, "kind") else "attempt" for e in entries(r.ble)]
    assert order.count("attempt") == 1 and order.index("attempt") <= 4

def test_a_feed_blip_shorter_than_the_cadence_makes_no_ping():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME)
    v.observe("state", "online", "TeslaMateVehicle"); feed = liveFeed(m, "TeslaMateVehicle")
    w = Watch(m, clock=c); pings = bleAnswers(m, asleep=True)
    w.pass_(); runPending(r.ble); assert pings.count == 0
    feed.down = True; c.t += 30; w.pass_(); runPending(r.ble)          # not yet due: covered when last checked
    feed.down = False; c.t += 30; w.pass_(); runPending(r.ble)
    assert pings.count == 0
    feed.down = True; c.t += 240; w.pass_(); runPending(r.ble)
    assert pings.count == 1
```

Test helpers this task adds (later tasks use them; exact names):
- `tests/unit/test_limit_reconciler.setup(*providers, clock=True, here=True, battery=60, ble=False)`: `ble=True` loads a real `TeslaBLE` on the master (as `test_teslable_pairing_status.scanner()` does, `isDockerCached = False`), registers its provider, and leaves `_tool` to the stubs below.
- `reconcile_helpers.bleAnswers(master, asleep=None, answer=True, charging=None)` → an object with `.count`; replaces `TeslaBLE.ping` with a stub that counts, returns `answer` (True/False/None), and when `answer` is True observes `state` ("asleep" if `asleep` else "online") from `TeslaBLE`. (Extend the existing `bleAnswers(master, ok=True)`; keep `ok` working.)
- `reconcile_helpers.bleReads(master, soc=50, charging="Stopped", amps=0, limit=80)` → an object with `.count` and settable `.charging`/`.amps`/`.soc`; replaces `TeslaBLE.get_charge_state` with a stub that counts and returns the normalized dict (`batteryLevel`, `chargeLimit`, `chargingState`, `actualCurrent`, `availableCurrent`, `voltage` 240, `phases` 1).
- `reconcile_helpers.bleScans(master, inRange=False)` → `.count`; replaces `TeslaBLE.scanForVehicleInRange` with a stub that counts, observes `bleReach` as the real one does, and returns `inRange`.
- `reconcile_helpers.liveFeed(master, source)` → an object with `.down` (False); registers `master.vehicleRegistry.registerLiveness(source, lambda v: None if feed.down else registry.now())`.
- `reconcile_helpers.gen2Slave(master, twcid, state=0x03, amps=0.0)`: use the Gen2 slave factory already in `tests/unit/gen2_helpers.py` if one exists (read it first); else add one that creates and links a slave with `reportedState` and `reportedAmpsActual` set.
- `attachFleet(master, vehicle, car)` / `attachOwner(master, vehicle, car)`: the parity file's way of listing a `FleetCar` on the Fleet or Owner slot (read `test_command_path_parity.py` for the listing helper it uses and re-export it from `reconcile_helpers`).

- [ ] **Step 2: Run to verify they fail.** Expected: `ModuleNotFoundError: Watch`.

- [ ] **Step 3: Implement `Watch.py`** per the Interfaces block. `pass_` walks `master.vehicleRegistry.vehicles()`, skips `notWatched`, computes `situation`, submits one status job per due car. A BLE status job is `lambda: ble.ping(vin, scan=False)`; a cloud one `lambda: carapi.onlineState(vehicle)`; an HA one `lambda: hv.refresh_from_home_assistant(ha)`. Each job runs under a `try/finally` that clears `_inflight` and reschedules. The watch's own lock guards `_due`, `_inflight`, `_seen` only. `settings()` reads `master.config.get("watch", {})` over `DEFAULTS` once at construction. The "feed covers it" check happens at the moment a ring is due, which gives Review Focus 4 for free.
- `Reconciler.submitJob(self, key, kind, run, worker="ble")`: `(self.cloud if worker == "cloud" else self.ble).put(Run.Job(key, kind, run))`.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py lib/TWCManager/Vehicle/Reconcile/Reconciler.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Watch cars no TWC or feed covers: the free sleep question on a slow clock"
```

---

