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

