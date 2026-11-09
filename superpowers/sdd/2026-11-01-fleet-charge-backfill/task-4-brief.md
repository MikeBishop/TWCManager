### Task 4: Suspicion and the free poll

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py` (`DEFAULTS`, `KINDS`, `__init__`, `_visit`, `_read`, new `suspect`, `_poll`, `fleetOnly`)
- Test: create `tests/unit/test_watch_poll.py` (reuse `apiOnly`, `chargingFleetCar`, `later`, `passes`, `snapshotAt`, `counts`, `paid`)

**Interfaces:**
- Consumes: `ChargeLedger`, `Snapshot` (Task 2); `ProviderOrder.read(v, "chargingState", False, ["FleetAPICached"], cutoff=T)` (Order.py:107, never waits from the watch); `"chargeEnergyAdded"` (Task 1).
- Produces:
  - `DEFAULTS`: `pollSecs=60`, `pollGiveUpSecs=600` (Task 8 retunes).
  - `fleetOnly(master, v) -> bool` (module function): `cloudOnly(master, v)`, or BLE configured and `lost`/deaf so the watch reads it through the cloud.
  - `Watch.ledger: ChargeLedger` (created in `__init__`; Task 6 restores it from settings).
  - `Watch.suspect(self, vin: str, at: float, why: str) -> None`: keeps the earliest open `T` per car; logs at DEBUG `"Suspect %s since %s: %s"`.
  - `Watch.liveWatts(self, vin: str) -> float` (`believedAmps` x voltage, for `ledger.wattsBetween`).
  - Job kind `"poll"` on the cloud worker.

Behavior in `_visit` for a `fleetOnly` car at home:
- Asleep: no poll. An open suspicion is dropped (its snapshot stands); an open ledger session is ended (`ledger.end`).
- Awake with a suspicion open, or a ledger session open: when `now >= lastPoll + pollSecs`, submit `"poll"`: one cached fetch with `cutoff=T` (session-only: `cutoff=last snapshot stamp + 1`). A snapshot stamped after the cutoff becomes `Snapshot(stamp, chargingState, chargeEnergyAdded, actualCurrent * voltage * (phases or 1))` and goes to `ledger.observe(vin, snap, startHint=T if why was a load step within 600 s else None)`; then the suspicion closes. Not `Charging` and no session: just close. A change queues `saveSettings`.
- Give up when `now >= T + pollGiveUpSecs` with nothing newer: close the suspicion, pay nothing.
- The event read's pay-if-stale branch and the routine `cloudChargingReadSecs` read do not run for `fleetOnly` cars (`_read` returns early for them unless `fix` is set). Their removal is the point; delete code made dead by it.
- A snapshot saying `Charging` opens a session only when `presence == HOME`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_suspicion_polls_until_a_newer_snapshot_and_pays_nothing(requests_mock): ...   # snapshot at T-60 for 4 polls, then T+250 Charging -> ledger open, paid == (0,0,0) after the setup reads
def test_the_poll_gives_up_without_paying(requests_mock): ...
def test_a_session_polls_each_minute_and_ends_on_a_closing_snapshot(requests_mock): ...
def test_an_asleep_car_is_never_polled_and_its_session_ends(requests_mock): ...
def test_no_routine_paid_read_while_a_fleet_only_car_charges(requests_mock): ...        # 30 min of passes: paid reads only the courtesy/fix ones
def test_a_snapshot_charging_away_opens_no_session(requests_mock): ...                   # Review Focus 1
def test_fetch_errors_keep_the_cadence_and_never_pause_the_slot(requests_mock): ...     # Review Focus 4: 429, 404, timeout
def test_a_snapshot_stamped_just_before_the_suspicion_is_not_taken(requests_mock): ...  # Review Focus 5: stamp T-2 -> poll continues
def test_a_ble_car_in_range_is_unchanged(requests_mock): ...                             # no "poll" jobs; existing BLE reads as before
```

- [ ] **Step 2: Run, expect FAIL**

Run: `pytest tests/unit/test_watch_poll.py -q`

- [ ] **Step 3: Implement** in `Watch.py`, keeping state in the existing `_lock`-guarded maps (`_want` gains nothing; a new `_suspect: Dict[str, Tuple[float, str]]` and `_last[(vin, "poll")]`).

- [ ] **Step 4: Run the new tests and every watch test**; fix tests in `test_watch.py`/`test_watch_cached.py` that assert the retired paid reads for Fleet-only cars by changing their expectation to the poll, not by deleting them.

Run: `pytest tests/unit/test_watch*.py -q`

- [ ] **Step 5: Commit** `feat: poll the free snapshot while a Fleet-only car may be charging`

---

