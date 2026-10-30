### Task 8: Delete the polling the watch replaces; fold in the pre-command ping

**Files:**
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:144-145, 206-208, 1629-1646, 1815, 1876-1890`; `lib/TWCManager/Vehicle/HomeAssistant.py:542-557`; `lib/TWCManager/TWCMaster.py:462-480`; `lib/TWCManager/Vehicle/Reconcile/Run.py:150-163`; `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py:35-50`; `lib/TWCManager/Vehicle/Watch.py` (`freshFor`)
- Test: `tests/unit/test_teslaapi_providers.py`, `tests/unit/test_teslaapi_registry.py`, `tests/unit/test_policy.py`, `tests/unit/test_watch.py`, `tests/unit/test_command_path_parity.py` (run, not edited)

**Interfaces:**
- `TeslaAPI`: `chargeUpdateInterval`, `lastChargeCheck`, `updateChargeAtHome` removed; `minBatteryLevelAtHome` and `numCarsAtHome` are pure registry reads; `update_vehicle_data` sets `car.statusDeferral = now + READ_MAX_AGE` after every successful read (one value) and `_TeslaAPIProvider.fetch` honours it as today; `is_far_from_home` stays (Task 6 uses it). `config.cloudUpdateInterval`, when present, logs once at INFO that it is ignored.
- `HomeAssistant`: `numCarsAtHome`/`minBatteryLevelAtHome` no longer call `updateChargeAtHome`; `updateChargeAtHome` stays as the watch's HA status job target (Task 4 calls `refresh_from_home_assistant` directly; delete `updateChargeAtHome` if nothing else calls it after this task: grep).
- `TWCMaster.updateChargeAtHome(self)` (the `checkCharge` task from `TWCSlave.py:678`, a power start): `for v in vehicles: if presence(self, v) == HOME: self.watch.readNow(v.vin, "power start")`; the TWC-named car on that slave included (it is drawing).
- `Run.runAttempt`: the pre-command ping's `known = asleep(vehicle, now - REACH_WINDOW)` becomes `asleep(vehicle, now - master.watch.freshFor(vehicle))` where `Watch.freshFor(v) -> float` returns the car's current Ring 1 cadence when the watch pinged it inside that window, else `REACH_WINDOW`. So a car the watch pinged 8 minutes ago on a 15-minute cadence is not pinged again before a command.
- Behaviour changes (named): (i) no 1800 s battery refresh; (j) one deferral value; (k) the pre-command ping defers to the watch's fresher answer.

- [ ] **Step 1: Write the failing tests**

```python
# test_teslaapi_registry.py
def test_min_battery_level_at_home_reads_the_registry_and_queues_nothing():
    m, api, v = listed()                                   # the file's fixture: a listed car at home
    v.observe("batteryLevel", 33, "TeslaBLE")
    m.queue_background_task = lambda *a, **k: pytest.fail("no checkCharge")
    assert api.minBatteryLevelAtHome == 33

def test_cloud_update_interval_is_ignored_with_one_log_line(caplog):
    m, api = apiWith(config={"cloudUpdateInterval": 600})
    assert "cloudUpdateInterval" in caplog.text and not hasattr(api, "chargeUpdateInterval")

# test_teslaapi_providers.py
def test_two_callers_inside_read_max_age_pay_once(requests_mock):
    m, r, v, c = setup(here=False); car = FleetCar(requests_mock, state="online", at=HOME); attachFleet(m, v, car)
    v.read("batteryLevel", maxAge=READ_MAX_AGE); c.t += 100; v.read("chargingState", 0, force=True)
    assert paid(requests_mock)[0] == 1                      # the deferral dedupes the forced read inside 300 s
    c.t += 300; v.read("chargingState", 0, force=True); assert paid(requests_mock)[0] == 2

# test_watch.py
def test_a_power_start_asks_the_watch_to_read_every_home_car():
    m, r, v, c = setup(here=False, ble=True); placeAt(m, v, HOME); v.observe("state", "online", "TeslaBLE")
    w = m.watch = Watch(m, clock=c); w.pass_(); runPending(r.ble); reads = bleReads(m)
    m.updateChargeAtHome(); w.pass_(); runPending(r.ble); assert reads.count == 1

def test_the_pre_command_ping_trusts_a_watch_ping_inside_its_cadence():
    m, r, v, c = setup(ble=True); placeAt(m, v, HOME); w = m.watch = Watch(m, clock=c); pings = bleAnswers(m, asleep=False)
    w.pass_(); runPending(r.ble); assert pings.count == 1
    c.t += 480; m.desired.set(VIN, CHARGE_LIMIT, 70, "policy"); r.pass_(); runPending(r.ble)
    assert pings.count == 1                                  # no second ping before the command
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Delete and rewire** as the Interfaces block says. Grep scope for removed names, verbatim: `git grep -nwE 'chargeUpdateInterval|lastChargeCheck|cloudUpdateInterval' -- lib html tests/unit tests/integration tests/API docs`. Every hit is removed, rewritten, or (docs) updated in Task 10.

- [ ] **Step 4: Run the full suite, then the parity file alone and compare its paid counts with BASE.** Expected: all pass; **no parity count moves**. If one does, stop and report with the row.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/TeslaAPI.py lib/TWCManager/Vehicle/HomeAssistant.py lib/TWCManager/TWCMaster.py lib/TWCManager/Vehicle/Reconcile/Run.py lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py lib/TWCManager/Vehicle/Watch.py tests/unit
git commit -m "The watch replaces the deferral ladder and the half-hourly battery refresh"
```

---

