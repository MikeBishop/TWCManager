### Task 9: Wiring: the tick, config, the Vehicles page

**Files:**
- Modify: `lib/TWCManager/TWCManager.py:795`, `lib/TWCManager/ControlTick.py:62-70`, `lib/TWCManager/Control/HTTPControl.py:388-420`, `lib/TWCManager/Control/themes/Default/vehicles.html.j2`
- Test: `tests/unit/test_control_tick.py` (exists: check; else create), `tests/unit/test_http_vehicles.py` (the Vehicles page tests from Phase 5; find by `grep -l "vehicles.html" tests/unit`)

**Interfaces:**
- `master.watch = Watch(master)` created in `TWCManager.py` right after `master.controlTick = ControlTick(master)` (`:795`), before the tick starts; `ControlTick.housekeeping` calls `self.master.watch.pass_()` under `_guarded("watch", ...)`; `watch.enabled` False (config) makes `pass_` a no-op and `notWatched` return `"disabled"`.
- Template global `watchLine(v) -> str`: `"Not watched: <why>"` or `"Watched: <last> <ageText(lastAt)>, next in <n> min; budget $<tokens>"`; one `<td>` on the Vehicles list after presence.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_tick_runs_the_watch_each_pass_and_a_watch_error_does_not_stop_distribution():
    m, s = make_master(); m.watch = Mock(); m.watch.pass_.side_effect = RuntimeError("boom")
    tick = ControlTick(m); m.config["config"]["fakeMaster"] = 1; m.controlPass = Mock()
    tick.pass_(); tick.pass_()
    assert m.controlPass.call_count == 2 and m.watch.pass_.call_count == 2

def test_the_vehicles_page_shows_the_watch_line(client):     # the Phase 5 page fixture
    m = client.master; v = m.vehicleRegistry.getOrCreate(VIN, "t")
    html = client.get("/vehicles")
    assert "Watched" in html or "Not watched" in html
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** the wiring, the template global and the cell. Settings: `config["watch"]` parsed once in `Watch.settings()` (Task 4); unknown keys ignored.

- [ ] **Step 4: Run the test files and the full suite.** Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/TWCManager.py lib/TWCManager/ControlTick.py lib/TWCManager/Control/HTTPControl.py lib/TWCManager/Control/themes/Default/vehicles.html.j2 tests/unit
git commit -m "Run the watch on the control tick; show it on the Vehicles page"
```

---

