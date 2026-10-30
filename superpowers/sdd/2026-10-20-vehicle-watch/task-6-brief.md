### Task 6: Ring 0 for away cars, and the away location read

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py`
- Test: `tests/unit/test_watch.py`

**Interfaces:**
- Away and awake with `canScan()`: a `scanForVehicleInRange(vin)` job every `scanAwaySecs`; two consecutive unanswered pings while awake count as one miss each, and the second runs the scan whose result the scan itself records (`bleReach`). A miss while `asleep(v) is True` records nothing.
- Away and awake with no scan possible and a `TeslaAPI` attachment: one **event-class** location read (`vehicle.read("lat", 0, force=True)`, cloud) not before `fixAt + (3600 if carapi.is_far_from_home(lat, lon) else 1800)` where `fixAt` is `max(v.latest("lat").at, v.latest("lon").at)`; never while asleep; never twice inside the same awake episode unless the read showed driving (`shiftState` in D/R/N), in which case again after `awayAwakeSecs`.
- Behaviour change (named): (g) away cars are polled for position only as above; the ladder's unconditional re-reads go (Task 8 deletes them).

- [ ] **Step 1: Write the failing tests**

```python
def test_an_away_awake_car_is_scanned_and_two_misses_record_absence():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, AWAY); v.observe("state", "online", "TeslaBLE")
    w = Watch(m, clock=c); pings = bleAnswers(m, answer=None); scans = bleScans(m, inRange=False)
    w.pass_(); runPending(r.ble); assert scans.count == 0 and v.latest("bleReach") is None
    c.t += 300; w.pass_(); runPending(r.ble)
    assert scans.count == 1 and v.latest("bleReach").value is False

def test_a_miss_while_asleep_records_nothing():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "asleep", "TeslaBLE")
    w = Watch(m, clock=c); bleAnswers(m, answer=None); scans = bleScans(m, inRange=False)
    for _ in range(3): c.t += 900; w.pass_(); runPending(r.ble)
    assert scans.count == 0 and v.latest("bleReach") is None and P.presence(m, v) == P.HOME

def test_away_location_is_read_once_per_awake_episode_after_the_return_time(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=AWAY); attachFleet(m, v, car)
    v.observe("lat", AWAY[0], "FleetAPI"); v.observe("lon", AWAY[1], "FleetAPI")
    w = Watch(m, clock=c)
    for _ in range(5): c.t += 300; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] == 0                                 # under 1800 s since the fix
    c.t += 300; w.pass_(); runPending(r.cloud); assert paid(requests_mock)[0] == 1
    for _ in range(6): c.t += 300; w.pass_(); runPending(r.cloud)
    assert paid(requests_mock)[0] == 1
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** the miss counter, the scan job, and the location rule. The away ETA uses `carapi.is_far_from_home` (kept) at the last fix.

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/Watch.py tests/unit/test_watch.py tests/unit/reconcile_helpers.py
git commit -m "Scan for an away car's return; read its position no sooner than it could be back"
```

---

