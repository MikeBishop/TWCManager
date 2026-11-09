### Task 5: Triggers: load steps, wakes, commands, staleness

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`loadSample`, `_visit` triggers)
- Modify: `lib/TWCManager/Vehicle/Reconcile/Reconciler.py:571` (`afterWrite`)
- Modify: `lib/TWCManager/Vehicle/Reconcile/Run.py` (record the send time on the attempt, if not already available, so `afterWrite` can pass it)
- Test: `tests/unit/test_watch_load_step.py`, `tests/unit/test_watch_poll.py`

**Interfaces:**
- Consumes: `Watch.suspect` (Task 4), `TeslaAPI.onlineState(v)`.
- Produces: no new public names.

Behavior:
- `loadSample` for a `fleetOnly` car: an up step suspects it if awake or unknown (`T` = the step's first sample, i.e. the sample before the held one); if believed asleep it submits the free online check now (the `"status"` job, ignoring its cadence) and suspects only if that answers awake. A down step suspects it while it is `HOME_CHARGING` or `believedAmps > 0`. No 1200 s courtesy throttle for `fleetOnly` cars (polling never keeps a car awake); BLE and other paths keep theirs.
- Staleness: `getChargerLoad() > getConsumption() + LoadStep.threshold` on two consecutive samples, with an EMS reporting consumption and `subtractChargerLoad` on: suspect every `fleetOnly` car with `believedAmps > 0`, `T` = the first of the two.
- Today's other triggers (wake, arrival, plug-in mark, port door) call `suspect` for `fleetOnly` cars instead of asking a read.
- `afterWrite`: on `DONE` or `SATISFIED` for any aspect, `master.watch.suspect(attempt.key, sentAt, "command")` when the car is `fleetOnly`.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_up_step_suspects_an_awake_fleet_only_car_from_the_steps_first_sample(): ...
def test_an_up_step_asks_an_asleep_car_online_and_suspects_it_only_if_awake(): ...
def test_a_cycling_load_does_not_throttle_a_fleet_only_suspicion(): ...       # but test_a_cycling_load_reads_a_car_once_a_courtesy_window still passes for BLE
def test_a_down_step_suspects_a_charging_car(): ...
def test_believed_load_above_consumption_twice_suspects_the_car(): ...
def test_one_sample_above_consumption_is_a_ramp_not_staleness(): ...
def test_an_accepted_command_suspects_the_car_from_its_send_time(): ...
def test_a_refused_command_suspects_nothing(): ...
```

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, expect PASS**, plus `pytest tests/unit/test_watch*.py tests/unit/test_*reconciler*.py -q`
- [ ] **Step 5: Commit** `feat: open a snapshot poll on load steps, wakes, commands and stale beliefs`

---

