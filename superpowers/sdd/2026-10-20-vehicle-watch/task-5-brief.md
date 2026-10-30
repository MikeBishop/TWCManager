### Task 5: Ring 2 on change: arrivals, wakes, charging, the courtesy window

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Produces: `Watch.readNow(self, vin: str, reason: str, cls: str = EVENT) -> None` (thread-safe; the next pass submits the read); `Watch.status()["last"]` names the last job (`"ping"`, `"status"`, `"read"`, `"scan"`).
- Read classes: an **event read** on (i) the memo's `presence` becoming HOME, (ii) `markAt("plugIn")` growing, (iii) `HOME_ASLEEP`→`HOME_AWAKE`, (iv) `readNow`; a **routine read** every `chargingReadSecs` (BLE) or `cloudChargingReadSecs` (cloud) while `HOME_CHARGING`, and every `chargingReadSecs` for a TWC-named car whose slave reports `reportedAmpsActual >= 1` or whose Gen3 unit's `currentAmps >= 1` (the one case a TWC-named car is touched).
- Courtesy: in `HOME_AWAKE` no read is made within `sleepCourtesySecs` of the last read of that car, except an event read for a plug-in or `readNow`.
- The read itself: `vehicle.read("chargingState", 0, force=True, providers=<local providers>)` on the BLE worker when a local provider is ready for `READ_CHARGE`; else on the cloud queue, after `master.watchBudget.spend(price, cls)` where `price` is the first non-local ordered provider's `cost(READ_CHARGE).price` (0.0 for Owner); a refused spend logs DEBUG and reschedules at the routine cadence. A read-only car (`VehicleEndpoint.isReadOnly`, i.e. no `SET_AMPS` candidate) gets event reads only.
- Behaviour change (named): (f) a car arriving by any route gets a read; a car waking at home gets a read; a charging car is read on the cadence.

- [ ] **Step 1: Write the failing tests**

```python
def test_arrival_by_twc_plug_in_reads_the_battery_once():
    m, r, v, c = setup(here=False, ble=True); w = Watch(m, clock=c); reads = bleReads(m, soc=18)   # helper: BLE charge read stub counting calls
    m.vehicleRegistry.observeTwcVin("8244", VIN); gen2Slave(m, "8244", state=0x03)
    v.observe("pluggedIn", True, "Gen2TWC")
    w.pass_(); runPending(r.ble)
    assert reads.count == 1 and v.value("batteryLevel") == 18
    c.t += 60; w.pass_(); runPending(r.ble); assert reads.count == 1

def test_a_wake_at_home_reads_once_then_waits_the_courtesy_window():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m, charging="Stopped")
    w.pass_(); c.t += 10; v.observe("state", "online", "TeslaBLE"); w.pass_(); runPending(r.ble)
    assert reads.count == 1
    for _ in range(4): c.t += 240; w.pass_(); runPending(r.ble)
    assert reads.count == 1                                          # inside sleepCourtesy (1200 s)
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 1  # still no routine read while not charging

def test_a_charging_car_is_read_on_the_cadence_and_released_when_it_sleeps():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); reads = bleReads(m, charging="Charging", amps=24)
    w.pass_(); runPending(r.ble); assert reads.count == 1 and situation(m, v) == HOME_CHARGING
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2
    c.t += 10; v.observe("state", "asleep", "TeslaBLE")
    e = VehicleEndpoint(v, m.providerOrder, m); assert not e.wantsToCharge
    c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2

def test_cloud_reads_draw_from_the_budget_and_stop_at_the_floor(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", charging="Charging", at=HOME); attachFleet(m, v, car)
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud)              # status then the wake-at-home event read
    paidBefore = paid(requests_mock)[0]; assert paidBefore == 1
    for _ in range(40): c.t += 900; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] <= 26                               # routine reads stop at half the day's tokens
    assert m.watchBudget.tokens() >= 0.05 - 0.002

def test_read_now_is_an_event_read_even_for_a_read_only_car(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=HOME, api=OWNER); attachOwner(m, v, car)  # Owner-only: read-only
    w = Watch(m, clock=c); w.pass_(); runPending(r.cloud); n = counts(requests_mock)["free"]
    w.readNow(VIN, "test"); w.pass_(); runPending(r.cloud)
    assert counts(requests_mock)["free"] == n + 1 and paid(requests_mock) == (0, 0, 0)

def test_a_twc_named_car_is_read_only_while_current_flows():
    m, r, v, c = setup(here=False, ble=True); w = Watch(m, clock=c); reads = bleReads(m, soc=50)
    m.vehicleRegistry.observeTwcVin("8244", VIN); s = gen2Slave(m, "8244", state=0x03); v.observe("pluggedIn", True, "Gen2TWC")
    w.pass_(); runPending(r.ble); assert reads.count == 1            # the arrival read
    s.reportedAmpsActual = 0; c.t += 600; w.pass_(); runPending(r.ble); assert reads.count == 1
    s.reportedAmpsActual = 24; c.t += 300; w.pass_(); runPending(r.ble); assert reads.count == 2
```

- [ ] **Step 2: Run to verify they fail.** Expected: `AttributeError: readNow`, read counts 0.

- [ ] **Step 3: Implement** the transition memo comparison, `readNow`, the two read classes, the courtesy window, the TWC-named current rule and the budget call, per the Interfaces block. The read job observes nothing itself: the cascade's providers do. After a read, `_lastRead[vin] = now`.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Read a watched car when something changes: arrival, wake, charging, on request"
```

---

