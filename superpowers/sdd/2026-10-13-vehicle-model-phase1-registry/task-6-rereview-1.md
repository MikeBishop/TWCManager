### Finding Verdicts — ADDRESSED | NOT ADDRESSED with file:line
1. ADDRESSED: VehicleRegistry.py:66-72 (getOrCreate rejects non-ASCII) matches load at :204; comment corrected. Test test_get_or_create_rejects_non_ascii_like_load.
2. ADDRESSED: VehicleRegistry.py:172 wraps in _number() (bool/NaN/str/object -> None); Vehicle.age/summary tested not to raise.
3. ADDRESSED: VehicleRegistry.py:31-40 (days None or <=0 -> warning + 30); parametrized test covers 0, -3, "x", None, True.
4. ADDRESSED: VehicleRegistry.py:76-78 DEBUG when source == "persisted"; load passes "persisted" (:221); test_load_logs_added_at_debug.
5. ADDRESSED: test_to_json_omits_anonymous.

### New Breakage in the Fix Diff — None
Focused run: tests/unit/test_registry_membership.py, 31 passed.

### Out-of-Scope Observations — None

### Verdict — **Fix round:** All findings addressed, no new Critical/Important breakage
