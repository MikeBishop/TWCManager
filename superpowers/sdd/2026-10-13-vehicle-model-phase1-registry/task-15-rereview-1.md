### Finding Verdicts
- 0 ADDRESSED. HTTPControl.py process_home_location (about :1633-1650): empty/None selection logs and changes nothing, falls through to saveSettings and the redirect. settings.html.j2 wraps the learn button and select in `{% if locatedVehicles() %}`. Tests: test_learn_home_location_without_a_selection_is_a_noop, test_learn_home_location_from_selection, test_settings_page_hides_learn_without_a_located_vehicle.
- 1 ADDRESSED. debug.html.j2:76 filters `vehicle.vin and vehicle.attachment("TeslaAPI")`. The test asserts the VIN-only BLE vehicle (...003) is absent.
- 4 ADDRESSED. test_registry_callers.py passes `cwd=REPO`, with REPO = parents[2] of the test file. Passes when run from /tmp.
- 5 ADDRESSED. The mock_tesla_api locals are gone from test_policy.py. getModuleByName still returns Mock(), which Policy.py:316 needs.

locatedVehicles (HTTPControl.py:~211): ADDRESSED. It returns only registry vehicles whose lat and lon observations are both non-None. The 10000 sentinel is only a RegistryField read default (TeslaAPI.py:2052) and is never observed into the registry, so it cannot appear. HomeAssistant observes lat/lon only after a successful float parse. It creates no vehicles (read-only vehicles()). It does not touch the TeslaAPI module, and the registry-only test with teslaapi=None passes.

Tests: test_registry_callers, test_policy and test_teslaapi_token_paste: 102 passed.

### New Breakage in the Fix Diff
None. test_teslaapi_token_paste.py correctly stubs the new global in its render harness.

### Out-of-Scope Observations
- locatedVehicles does not defensively exclude an explicitly observed 10000. No current provider observes it, so this is theoretical.
- process_home_location's `del master.settings[...]` on unset raises KeyError if the home location is already unset. This is pre-existing and not part of this diff.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage
