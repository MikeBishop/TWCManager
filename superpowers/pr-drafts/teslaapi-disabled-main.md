Start and run with the Tesla API turned off in config

With `vehicle.teslaAPI.enabled: false`, TWCManager stops at startup:

```
AttributeError: 'NoneType' object has no attribute 'migrateSavedTokens'
  File ".../TWCManager/TWCMaster.py", line ..., in loadSettings
```

`getModuleByName("TeslaAPI")` answers `None` for a disabled module, as it does for any module whose `enabled()` is False. But `loadSettings` and `saveSettings` used the result without checking. The same was true before the token slots: 1.3.3 had it too. I found it setting up a second TWCManager instance with no vehicle modules. A BLE-only install that turns the API off hits it at once.

An audit of every `getModuleByName("TeslaAPI")` on `main` found five more places that assume it's there. Each now treats a missing Tesla API as no Tesla API:

| Where | When it runs | Now |
|---|---|---|
| `TWCMaster.loadSettings` / `saveSettings` | startup, every settings save | token migration and restore skipped; saved tokens left in settings for when it's turned back on |
| `Reconcile/Targets.py` `located()`, departure read | the charge-limit reconciler | the location is unknown; no read |
| `Policy.enforcePolicy` stop-by-limit override | a policy pass with the override set | no battery level to lower the limit below, so the policy's own limit applies |
| `TeslaPowerwall2.getStormWatch` | every Storm Watch check | same as no energy token: no request |
| `HTTPControl` token paste, `WebIPCControl` status and dump | the web pages | an error result / the API fields left out |

Every TeslaBLE, TeslaMateVehicle and Gen3TWCs lookup already checks. TWCProtocol and Policy are always loaded.

## Tests

Each test fails without the change:
- `test_a_disabled_tesla_api_starts_and_keeps_its_saved_tokens`: load and save with no TeslaAPI, and the saved Owner token survives the save.
- `test_a_disabled_tesla_api_leaves_the_policy_limit_alone`.
- `test_a_car_with_a_tesla_api_record_is_not_located_without_the_module`.
- `test_storm_watch_without_the_tesla_api_sends_nothing`.

Unit suite: 2,024 passed, 1 xfailed. The same fix for `release/1.3.4` is #PR134.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
