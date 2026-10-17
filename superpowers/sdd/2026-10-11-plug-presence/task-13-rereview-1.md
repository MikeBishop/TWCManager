### Finding Verdicts
1. ADDRESSED. tests/unit/test_teslable_presence.py (policy_wide_apply test, ~:945-956) and tests/unit/test_plug_presence_scenarios.py (~:710-728). Mutation run on a HEAD copy with TeslaAPI.py:1204 replaced by `if False:` shows 2 failed (the teslable test and the fleet_command param), owner_read_only passes as expected. Unmutated HEAD passes.
2. ADDRESSED. tests/unit/test_teslaapi_presence.py `test_presumed_car_with_no_location_fix_is_woken` (~:871). Uses a real tracker and real car, asserts lat 10000, presumed, atHome True, and that wakeVehicle is called for the car. Passes on HEAD.
3. ADDRESSED. deploy-presence-3-merge-report.md:158-164 now says a PRESUMED no-fix car is woken, cites the test, and keeps the isHome-raises exception.

### New Breakage in the Fix Diff
None (test-only changes; the 3 touched tests and the new one pass).

### Out-of-Scope Observations
None

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage
