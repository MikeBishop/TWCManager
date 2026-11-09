# Fleet-only charge history backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A car only the Fleet API sees gets an eventually correct charge history and needs no paid read to detect a charge, by polling the free `vehicle_data_cached` snapshot while something may have changed and reconstructing each session from `charge_energy_added`.

**Architecture:** A new pure `ChargeLedger` turns a car's snapshots into wall-power segments and persists them. `Watch` keeps a per-car suspicion (opened by load steps, wakes, commands, a staleness check) and, for cloud-read cars, polls the free snapshot until one newer than the suspicion arrives, feeding the ledger. Control reads a commanded-rate belief; `/api/getHistory` adds ledger segments to the measured buckets.

**Tech Stack:** Python 3.8+, pytest with `requests_mock`, existing `TWCManager.Vehicle` registry, provider order and reconciler.

**Spec:** `.superpowers/specs/2026-11-01-fleet-charge-backfill-design.md` (approved 2026-11-01). Read it first; this plan argues from it.

## Global Constraints

- **Ship gate (user):** nothing merges or deploys as the default build until Task 8 has replayed **several days at least** of the 30-second load log (`~/cachelog/load.jsonl` on the box, `fleet-loadlog.service`, started 2026-11-01) and the user has seen the numbers.
- Python 3.8 floor (`setup.py`); no new dependencies.
- Fleet-only means: a watched car whose charge readings come from the cloud: `Watch.cloudOnly(master, v)`, or a BLE car the radio has lost that the watch reads through the cloud (`_read`'s `deaf` path). Cars reported live (TWC, Gen3, a feed, BLE in range) are unchanged.
- Never wake a car to poll; never poll a car believed asleep; a step on an asleep car asks the free online check (`TeslaAPI.onlineState`) instead.
- No paid read for detection. The courtesy/location read (`late`/`fix` in `Watch._visit`) and the reconciler's pre-write reads are unchanged.
- Never invent energy: missing evidence ends a session at its last `Charging` snapshot.
- Battery -> wall efficiency: `0.93` (measured 0.91-0.98), unless Task 8's offline check says otherwise.
- Comments say why the code is as it is, never its history. Match the surrounding dense style (see `tests/unit/test_watch_load_step.py`).
- Library growth small; remove the paid paths this retires for Fleet-only cars rather than leaving them dead.
- Gen3 behavior must not regress.
- Full test run: `pytest tests/unit --ignore=tests/API --ignore=tests/integration -q`.

## Review Focus

1. **A car charging away from home** (a Supercharger, a friend's EVSE): a snapshot says `Charging` and has no location. Expect no home session unless `Presence.presence(master, v) == HOME`. Test in Task 4.
2. **Restart mid-session:** the ledger's open session is persisted; the first snapshot after restart continues it (energy at or above the last) rather than opening a second session or crediting the gap twice. Test in Task 2 (round-trip) and Task 6 (load/save wiring).
3. **Snapshot missing fields** (`charge_energy_added` or `charger_actual_current` absent or `None`, voltage 2 when idle): no exception; a session without energy starts at the snapshot's own stamp and backfills nothing earlier. Test in Task 2.
4. **Fetch failures during a poll** (404, 412, 429, timeout): the poll keeps its cadence until give-up, pays nothing, never pauses the Fleet slot. Test in Task 4.
5. **Clock skew** between the local clock (suspicion time T) and the car's stamp: a snapshot stamped up to 2 s before T because of skew must not be taken as post-event (it may be pre-event), and polling simply continues. Test in Task 4.

---

### Task 1: Observe `charge_energy_added`

**Files:**
- Modify: `lib/TWCManager/Vehicle/Registry/Fields.py` (add `"chargeEnergyAdded"` to `FIELDS`, beside the charge fields)
- Modify: `lib/TWCManager/Vehicle/TeslaAPI.py:1872-1891` (`_observeCharge`: add `("charge_energy_added", "chargeEnergyAdded")`)
- Modify: `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py` (the cached and paid Fleet providers' `FIELDS` include it if they enumerate fields)
- Test: `tests/unit/test_watch_cached.py`

**Interfaces:**
- Produces: registry field `"chargeEnergyAdded"` (kWh, float, battery side) observed by every Fleet read path at the snapshot's stamp.

- [ ] **Step 1: Write the failing test**

```python
def test_a_snapshot_carries_the_session_energy(requests_mock):
    m, r, v, c = setup(here=False); chargingFleetCar(requests_mock, m, v)
    requests_mock.get(FLEET + VIN + "/vehicle_data_cached", json={"response": {"charge_state": {
        "timestamp": 1_000_000, "charging_state": "Charging", "charge_energy_added": 1.02}, "vehicle_state": {}}})
    m.getModuleByName("TeslaAPI").read_cached(v)
    obs = v.latest("chargeEnergyAdded"); assert obs.value == 1.02 and obs.at == 1000.0
```

- [ ] **Step 2: Run it, expect FAIL** (`latest` returns None)

Run: `pytest tests/unit/test_watch_cached.py::test_a_snapshot_carries_the_session_energy -v`

- [ ] **Step 3: Add the field and the mapping** (two one-line changes; check `test_registry_fields.py`/`test_provider_tables.py` for field lists that must grow too)

- [ ] **Step 4: Run the test and the registry/provider table tests, expect PASS**

Run: `pytest tests/unit/test_watch_cached.py tests/unit/test_registry_fields.py tests/unit/test_provider_tables.py -q`

- [ ] **Step 5: Commit** `feat: observe the Fleet session energy (charge_energy_added)`

---

### Task 2: `ChargeLedger`

**Files:**
- Create: `lib/TWCManager/Vehicle/ChargeLedger.py`
- Test: `tests/unit/test_charge_ledger.py`

**Interfaces:**
- Produces:
  - `class Snapshot(NamedTuple): stamp: float; state: str; energy: Optional[float]; watts: float` (watts: wall AC, `actualCurrent * voltage * phases`, 0 when not charging)
  - `class ChargeLedger:` constants `EFFICIENCY = 0.93`, `KEEP_SECS = 2 * 86400`
    - `__init__(self, clock=time.time)`
    - `observe(self, vin: str, snap: Snapshot, startHint: Optional[float] = None) -> bool` (True when segments changed; caller saves settings)
    - `end(self, vin: str) -> bool` (close an open session at its last `Charging` stamp)
    - `isOpen(self, vin: str) -> bool`
    - `wattsBetween(self, start: float, end: float, live: Callable[[str], float]) -> float` (mean wall watts over `[start, end)`, every car summed; an open session runs from its last snapshot to `clock()` at `live(vin)` watts)
    - `toJSON(self) -> dict`, `@classmethod fromJSON(cls, data: dict, clock=time.time) -> "ChargeLedger"` (tolerates `{}`/`None`)
    - `prune(self, now: float) -> None` (drop segments ending before `now - KEEP_SECS`)
  - Thread safety: one leaf lock; never held across a call out.

Rules (spec section 5), with `wall(kWh, secs) = kWh * 3.6e6 / EFFICIENCY / secs`:

| Case | Segment written |
|---|---|
| first `Charging` S, `startHint` set and `<= S.stamp` | `startHint -> S.stamp` at `wall(S.energy, S.stamp - startHint)` |
| first `Charging` S, no hint, energy known, `S.watts > 0` | start `= S.stamp - S.energy * 3.6e6 / (S.watts * EFFICIENCY)`; then as above |
| first `Charging` S, energy unknown | none; session opens at `S.stamp` |
| `Charging` S after P, `S.energy >= P.energy` | `P.stamp -> S.stamp` at `wall(S.energy - P.energy, ...)` |
| `Charging` S after P, `S.energy < P.energy` | close at `P.stamp`; S opens a new session (first-snapshot rules, no hint) |
| not `Charging` C after P | end `= min(C.stamp, P.stamp + max(0, C.energy - P.energy) * 3.6e6 / (P.watts * EFFICIENCY))`; `P.stamp -> end` at `P.watts`; close |
| `end(vin)` | close at `P.stamp`, nothing written |
| snapshot stamped at or before the last seen | ignored (returns False) |

- [ ] **Step 1: Write the failing tests** (values from the 2026-11-01 log)

```python
def test_a_session_starts_from_its_energy_when_no_step_was_seen():
    l = ChargeLedger(clock=lambda: T0 + 400)
    l.observe(VIN, Snapshot(T0, "Charging", 1.02, 11376.0))
    start = T0 - 1.02 * 3.6e6 / (11376.0 * 0.93)
    assert l.wattsBetween(start, T0, lambda v: 0) == pytest.approx(11376.0, rel=0.01)

def test_a_load_step_sets_the_start():
    l = ChargeLedger(clock=lambda: T0); l.observe(VIN, Snapshot(T0, "Charging", 0.82, 11328.0), startHint=T0 - 300)
    assert l.wattsBetween(T0 - 300, T0, lambda v: 0) == pytest.approx(0.82 * 3.6e6 / 0.93 / 300)

def test_energy_between_snapshots_is_spread_across_them(): ...   # 1.02 at T0, 3.28 at T0+743 -> 2.26 kWh over 743 s
def test_the_closing_snapshot_ends_it_by_energy_and_trims_the_belief(): ...  # live(vin)=11520 credited past the end must vanish once C arrives
def test_the_end_never_passes_the_closing_stamp(): ...
def test_without_a_closing_snapshot_it_ends_at_the_last_charging_stamp(): ...  # end(vin): wattsBetween after P.stamp == 0
def test_an_energy_drop_while_charging_is_a_new_session(): ...
def test_a_snapshot_without_energy_backfills_nothing_before_its_stamp(): ...   # Review Focus 3
def test_an_old_or_repeated_snapshot_changes_nothing(): ...
def test_the_ledger_round_trips_with_a_session_open(): ...      # Review Focus 2: fromJSON(toJSON()) then a later snapshot continues it
def test_segments_older_than_two_days_are_pruned(): ...
def test_two_cars_sum(): ...
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError`)

Run: `pytest tests/unit/test_charge_ledger.py -q`

- [ ] **Step 3: Implement `ChargeLedger.py`** per the table. Store per car `{"open": {"stamp", "energy", "watts"} | None, "segments": [[start, end, watts], ...]}`; JSON-native types only (it goes into `settings.json` via the C encoder).

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit** `feat: add a charge ledger that rebuilds sessions from snapshots`

---

### Task 3: Commanded-rate belief

**Files:**
- Modify: `lib/TWCManager/Vehicle/Watch.py:200-209` (`chargingAmps`, new `believedAmps`)
- Test: `tests/unit/test_watch_load_step.py` (belief), `tests/unit/test_charging_points.py` or `tests/unit/test_distributor_loop.py` (allocation pin; use whichever already builds two cloud cars on one circuit)

**Interfaces:**
- Consumes: `Vehicle.lastWrite(field) -> Optional[Observation]` (stamped by `Reconcile/Run.py:255` via `noteWrite` for DONE, and for SATISFIED on limit/amps), `Vehicle.latest(field)`.
- Produces:
  - `Watch.believedAmps(self, v) -> float`: if `lastWrite("chargingState")` or `lastWrite("chargeCurrentRequest")` is newer than `latest("actualCurrent")`, then `max(reading, commanded)` where a written `"Stopped"` commands nothing new and a written `"Charging"` makes the car count at `lastWrite("chargeCurrentRequest")` (else its `chargeCurrentRequestMax`); otherwise the reading, counted only while `situation == HOME_CHARGING` as today.
  - `Watch.chargingAmps(self, ledgered: bool = True) -> float`: sums `believedAmps`; `ledgered=False` leaves out Fleet-only cars (Task 6 uses it).

No change to `_drawAmps`/`_drawing`/`taken` (TWCMaster ~73-89, ~745): allocation already takes `max(given, draw)` and a cloud car's draw stays its last reading until a newer one. That is the spec's "never allocate on the assumption"; Step 1 pins it.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_accepted_start_counts_at_the_commanded_amps_until_a_reading(): ...   # chargingAmps == 32 after noteWrite("chargingState","Charging") + noteWrite("chargeCurrentRequest",32), car reading "Stopped"
def test_a_lowered_rate_keeps_the_old_draw_until_a_newer_reading(): ...          # reading 48 A, write 16 -> 48; new reading 16 -> 16
def test_a_raised_rate_counts_at_once(): ...                                       # reading 16, write 32 -> 32
def test_a_second_car_gets_its_full_share_only_once_the_first_reads_lower(): ... # allocation pin: two Fleet cars, one 48 A circuit
```

- [ ] **Step 2: Run, expect the first three FAIL; the allocation pin should already PASS** (if it fails, stop and report: the spec's assumption about `taken` is wrong)

- [ ] **Step 3: Implement `believedAmps` and switch `chargingAmps` to it**

- [ ] **Step 4: Run, expect PASS**, plus `tests/unit/test_watch*.py tests/unit/test_twcmaster.py -q`

- [ ] **Step 5: Commit** `feat: count a car at its commanded rate until a reading confirms it`

---

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

### Task 6: History from buckets plus ledger

**Files:**
- Modify: `lib/TWCManager/TWCMaster.py:1099` (`getChargerLoad(self, ledgered: bool = True)`), `:2202` (`sampleHistory` uses `getChargerLoad(ledgered=False)`), `:1298`/`:1870` (`loadSettings` restores `watch.ledger` from `settings.get("chargeLedger")`; `saveSettings` writes `watch.ledger.toJSON()` under the lock, as `vehicleRegistry` is; `ledger.prune(now)` there too)
- Modify: `lib/TWCManager/Control/HTTPControl.py:833-860` (`/api/getHistory`)
- Test: `tests/unit/test_twcmaster.py` (`TestTWCMasterHistory`), `tests/unit/test_httpcontrol.py`

**Interfaces:**
- Consumes: `Watch.chargingAmps(ledgered=False)` (Task 3), `Watch.ledger`, `Watch.liveWatts` (Task 4), `ChargeLedger.wattsBetween/toJSON/fromJSON/prune` (Task 2).
- Produces: settings key `"chargeLedger"`.

`/api/getHistory`: each 5-minute slot's `charger_power` = the stored bucket (0 if none) + `ledger.wattsBetween(slot, slot + 300, watch.liveWatts)`; the current slot = `historyWatts()` + the same. With no watch, unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_history_buckets_leave_out_fleet_only_cars_but_keep_live_ones(): ...
def test_get_history_adds_ledger_segments_to_buckets(): ...     # a segment 00:05:06-00:23:00 at 11 kW shows in slots 00:05..00:20, partial at both ends
def test_a_backfilled_session_replaces_the_live_belief_in_history(): ...
def test_the_ledger_survives_save_and_load(): ...               # Review Focus 2
```

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run the full unit suite, expect PASS**

Run: `pytest tests/unit --ignore=tests/API --ignore=tests/integration -q`

- [ ] **Step 5: Commit** `feat: add Fleet-only charge sessions to the charge history`

---

### Task 7: Docs and changelog

**Files:**
- Modify: `docs/modules/Vehicle_TeslaAPI.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** Add an installer FAQ entry: with Fleet only, charge history fills in a few minutes late but correct, at no API cost; for live data (green tracking that follows the sun minute by minute) use Fleet Telemetry, BLE, or an EVSE that reports current. Capabilities, not internals; "EVSE", not "charger".
- [ ] **Step 2:** `git describe --tags --abbrev=0`; check whether the TWC-less watch (`Watch.py` `cloudOnly`) shipped in that tag (`git show <tag>:lib/TWCManager/Vehicle/Watch.py`). Shipped: one Bugfixes line ("Fix charge history missing sessions for cars read only through the Fleet API."). Not shipped: one Features line. 1-2 sentences, verb first.
- [ ] **Step 3: Commit** `docs: explain Fleet-only charge history`

---

### Task 8: Replay the load log and tune (ship gate)

**Files:**
- Create (scratch, not committed): `scratchpad/replay_steps.py`
- Modify: the spec's Constraints section (record the numbers); `Watch.DEFAULTS` if tuning changes `pollGiveUpSecs` or the threshold

**Precondition:** `~/cachelog/load.jsonl` on the box covers several days at least (user's gate). Check with `ssh twcmanager 'head -1 ~/cachelog/load.jsonl; tail -1 ~/cachelog/load.jsonl; wc -l ~/cachelog/load.jsonl'`.

- [ ] **Step 1:** Copy the log down. Replay `LoadStep(1200.0)` over `consumptionWatts - chargerLoadWatts` (main instance) sample by sample. Count, per day: up steps with the car's logged `state == "online"`; down steps while the fake master's TWC load > 0; the poll-minutes those would open with `pollSecs=60` and `pollGiveUpSecs` in `{300, 600, 900}`, merging overlaps; the online checks the asleep-car path would make.
- [ ] **Step 2:** Offline efficiency check: from `~/cachelog/cached.jsonl` (24 h snapshot log, TWC load in each line), compare each session's `charge_energy_added` with the TWC-metered energy; confirm `0.93` or replace it in `ChargeLedger.EFFICIENCY`.
- [ ] **Step 3:** Write the table into the spec; propose a give-up time and threshold. **Stop and show the user.** Do not proceed to Task 9 without their go-ahead.
- [ ] **Step 4:** Apply what they choose; run the full unit suite; commit `tune: snapshot poll give-up from the load log`.

---

### Task 9: Live check on the box

Deploys to `twcmanager` are pre-approved; record the rollback (the build currently running) before deploying.

- [ ] **Step 1:** Deploy the branch to the TWC-less (main) instance only; restart `twcmanager`. Note the paid-request count for the 24 h before (`journalctl -u twcmanager | grep -c "paid request"`).
- [ ] **Step 2:** After one night of scheduled charging, compare `/api/getHistory` on :8080 with the fake master's on :8081 slot by slot: each session's start and end within ~1 slot, energy within the efficiency band. Count paid requests over the same 24 h: fewer than before, and only courtesy/fix reads and reconciler pre-write reads.
- [ ] **Step 3:** Report to the user with the comparison. Stop `fleet-loadlog.service` only when they say so.
- [ ] **Step 4:** Prepare the PR description and diff for the user's review; do not open it (user reviews first; user does not self-merge).
