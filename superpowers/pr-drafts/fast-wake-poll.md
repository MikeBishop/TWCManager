## Summary

Two unit tests script a car that never wakes, so after the wake the Tesla
API module ran its full nine 5 s online polls with a real `time.sleep`:
45 s each, 90 s of every unit-suite run, nearly all of it idle.

- `test_fleet_wake_comes_after_a_free_online_check`
- `test_an_ended_need_gets_a_fresh_grace_through_wake_outcome`

Both now stub the sleep, as the other wake tests in
`test_provider_outcomes_cloud.py` and `test_command_path_parity.py` already
do. What they assert is unchanged.

## Test plan

- `test_charging_reconciler.py`: 60 passed in 0.87 s (was 46 s)
- `test_provider_outcomes_cloud.py`: 32 passed in 0.53 s (was ~45 s)
- Full unit suite (`--ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios`) passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
