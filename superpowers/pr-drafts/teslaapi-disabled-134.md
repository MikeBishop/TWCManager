Start and run with the Tesla API turned off in config (1.3.4)

The 1.3.4 version of #PRMAIN. With `vehicle.teslaAPI.enabled: false`, TWCManager stops at startup (`'NoneType' object has no attribute 'migrateSavedTokens'` in `loadSettings`). `getModuleByName("TeslaAPI")` answers `None` for a disabled module, and 1.3.4 uses the result without checking in eleven places. This has been true since 1.3.3 at least.

The places, each of which now treats a missing Tesla API as no Tesla API:
- **Startup and settings save:** `TWCMaster.loadSettings` and `saveSettings`. Token migration and restore are skipped, and saved tokens are left in settings for when the API is turned back on.
- **Every policy pass:** the policy's vehicle loop on a policy change, and the stop-by-limit override, which now leaves the policy's own limit.
- **Every slave pass:** `TWCSlave.getLastVehicle`.
- **Storm Watch:** `TeslaPowerwall2.getStormWatch` makes no request.
- **The web interface:**
  - `HTTPControl`'s `vehicles` template global, set when the web server starts;
  - the debug command, which answers 400;
  - the token paste, which redirects with an error;
  - WebIPC's status and dump, which leave the API fields out.

## Tests

Each test fails without the change:
- `test_a_disabled_tesla_api_starts_and_keeps_its_saved_tokens`.
- `test_a_disabled_tesla_api_changes_policy_and_leaves_the_limit`.
- `test_storm_watch_without_the_tesla_api_sends_nothing`.

The unit suite here fails no test that `release/1.3.4` doesn't already fail: 62 fail on the unmodified branch in my environment, mostly `test_dummy.py`.

The CHANGELOG entry opens a `v1.3.4.post2 - Upcoming` section.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
