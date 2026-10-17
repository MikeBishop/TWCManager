# Task 7 report

Implemented: wake loop `if not vehicle.atHome: continue` (lat != 10000 clause removed); HomeAssistant `_atHome` (presence.isHome when presence and vin exist, else at_home) used in car_api_charge, applyChargeLimit, numCarsAtHome, minBatteryLevelAtHome; TeslaAPIController.allEVSEs uses isPluggedHome (atHome without presence).

Tests: all 10 brief tests added (DEPARTING/NOT_HOME mapped to a car unplugged on a TWC; HOME = TWC proof). New file test_teslaapi_controller_presence.py. The every-channel test sits in test_teslable_presence.py (needs its `ble` fixture). Full suite 1070 pass.

TDD RED (before impl): 7 failed - unplugged-car-with-lat-10000 wake, 4 HA tests, controller EVSE test (presumed listed), plus the every-channel test (harness). GREEN after impl. Several tests (counts, scheduled pending, departing wake, policy-wide skips) pass at RED because Task 2 already made atHome/isHome authoritative; they are regression guards.

Fix-ups: existing HA test make_ha now sets master.vehiclePresence = None (a Mock master made isHome truthy).
Black: run on the touched source files and the clean test files; test_teslaapi_presence.py and test_teslable_presence.py were not black-clean, new hunks written in black style, not reformatted.

Self-review / concerns: HA in the wake path had no presence consequence beyond the lat clause; a never-located, never-seen car is PRESUMED and so is still woken (spec intent: presumed = home). Controller filter calls presence.isPluggedHome(v.VIN) directly (no exception guard, matching isHome use elsewhere).
