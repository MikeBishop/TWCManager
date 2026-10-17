# Task 9 report
Status: DONE. Commit on presence/3-plug-presence (see git log HEAD).
- Added DEFAULT_AT_HOME_RADIUS_FEET = 1000 in TeslaAPI.py and HomeAssistant.py; is_location_home uses it. Comments updated; config.json/.testconfig.json/demo.json comments say default is 1000 ft; CHANGELOG v1.4.0 Features line added verbatim.
- Tests: TestHomeRadius (2) in test_teslaapi_presence.py, 2 in test_homeassistant_presence.py. Before implementation both default_radius tests failed (1100 ft counted as home); explicit-override tests passed (expected). After: all pass.
- Suite: 1097 passed (baseline 1093 + 4).
- black run on touched files; black's reformat of unrelated pre-existing hunks in test_teslaapi_presence.py was reverted per constraints.
- Commit trailer used: Opus 5.5 per global-constraints (system attribution said Sonnet 5.5).
