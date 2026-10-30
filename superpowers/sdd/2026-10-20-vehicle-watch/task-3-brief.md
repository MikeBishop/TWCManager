### Task 3: The paid-read budget

**Files:**
- Create: `lib/TWCManager/Vehicle/WatchBudget.py`
- Modify: `lib/TWCManager/TWCMaster.py:1112-1190` (`loadSettings`), `:1672-1700` (`saveSettings`)
- Test: `tests/unit/test_watch_budget.py`

**Interfaces:**
- Produces:
  ```python
  EVENT, ROUTINE = "event", "routine"
  class WatchBudget:
      def __init__(self, monthlyUSD: float, clock=time.time, floor: float = 0.5): ...
      capacity: float            # monthlyUSD / 30: one day's worth
      def tokens(self, now: Optional[float] = None) -> float
      def spend(self, price: float, cls: str, now: Optional[float] = None) -> bool
      def toJSON(self) -> dict   # {"tokens": float, "at": float}
      def load(self, data) -> None   # None or a malformed dict: start full
  ```
  `master.watchBudget` is the instance; `settings["watchBudget"]` its JSON.
- Rules: fill rate `monthlyUSD / (30 * 86400)` per second, capped at `capacity`; `spend` for `EVENT` succeeds when `tokens >= price`; for `ROUTINE` when `tokens - price >= floor * capacity`; a zero price always succeeds and still refreshes the stamp; `spend` logs INFO once when the bucket first cannot pay and once when it can again (a `_empty` flag).

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_watch_budget.py`, a `Clock` like `reconcile_helpers.Clock`)

```python
def test_event_reads_may_spend_the_whole_bucket_but_routine_stops_at_the_floor():
    c = Clock(0.0); b = WatchBudget(3.0, clock=c)      # capacity 0.1
    assert b.capacity == pytest.approx(0.1)
    assert b.spend(0.002, ROUTINE) and b.tokens() == pytest.approx(0.098)
    while b.spend(0.002, ROUTINE): pass
    assert b.tokens() == pytest.approx(0.05, abs=0.002)   # the floor holds
    assert b.spend(0.002, EVENT) and not b.spend(0.2, EVENT)

def test_tokens_refill_at_the_monthly_rate_and_cap_at_a_day():
    c = Clock(0.0); b = WatchBudget(3.0, clock=c)
    while b.spend(0.002, EVENT): pass
    c.t += 86400 / 2
    assert b.tokens() == pytest.approx(0.05, abs=0.001)
    c.t += 86400 * 10
    assert b.tokens() == pytest.approx(0.1)

def test_restart_keeps_the_bucket_and_elapsed_time_refills_it():
    c = Clock(1000.0); b = WatchBudget(3.0, clock=c)
    while b.spend(0.002, EVENT): pass
    saved = b.toJSON()
    c.t += 3600
    b2 = WatchBudget(3.0, clock=c); b2.load(saved)
    assert b2.tokens() == pytest.approx(0.1 / 24, abs=0.001)
    b3 = WatchBudget(3.0, clock=c); b3.load({"tokens": "junk"})
    assert b3.tokens() == pytest.approx(0.1)

def test_a_zero_price_always_spends_and_settings_round_trip(tmp_path):
    # master.loadSettings/saveSettings carry settings["watchBudget"]
    m, s = make_master()                                  # tests/unit/test_limit_reconciler.make_master
    m.config["config"]["settingsPath"] = str(tmp_path)
    while m.watchBudget.spend(0.002, EVENT): pass
    assert m.watchBudget.spend(0.0, ROUTINE)
    m.saveSettings(); m.settings.clear(); m.loadSettings()
    assert m.watchBudget.tokens() < 0.01
```

- [ ] **Step 2: Run to verify they fail.** Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `WatchBudget`** as specified; `toJSON` stores tokens and the stamp; `load` accepts the two numbers, else starts full. In `TWCMaster.__init__` create `self.watchBudget = WatchBudget(float(config.get("watch", {}).get("monthlyBudgetUSD", 3.0)))`; `loadSettings` calls `self.watchBudget.load(self.settings.get("watchBudget"))` next to the registry blob (`:1182`); `saveSettings` writes `self.settings["watchBudget"] = self.watchBudget.toJSON()` under `settingsLock` next to `vehicleRegistry` (`:1690`).

- [ ] **Step 4: Run the test file and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Vehicle/WatchBudget.py lib/TWCManager/TWCMaster.py tests/unit/test_watch_budget.py
git commit -m "A monthly budget for the watch's paid reads, kept across restarts"
```

---

