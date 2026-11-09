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

