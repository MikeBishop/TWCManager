# Squash report: vehicle-model/phase4 (3be7a5b2..044e5262, 28 commits -> 15)

Branch vehicle-model/phase4-squashed, worktree scratchpad/wt-sq4, tip 956e0672. Author Mike Bishop kept on all.

| # | New SHA | Subject | Original commits | Tests (unit+EMS) |
|---|---------|---------|------------------|------------------|
| 1 | 0a55f0f1 | Send every RS-485 message from the serial loop | e440006f, 044e5262 | 1872 passed |
| 2 | 939d36e7 | Refresh Tesla tokens off the serial loop, one refresh per slot at a time | 5e7cb5f4, 95acd4bb, 37ed527e | 1888 passed |
| 3 | fbf9b3b8 | Run the one distributor on a 1 s control tick for every install | 7a85f0b7, 17d1b1e1 | 1903 passed |
| 4 | 0cdb7bac | Compute TWC offers on the control tick; charging points own car amps | a3c897c2, d105895d | 1920 passed |
| 5 | 7d34e909 | Plan a car's charge rate before its start command | 4ed54888 | 1925 passed |
| 6 | 39461a2f | Decide TWC start and stop on the control tick | 4b3e048c, 3cfb5a77 | 1934 passed |
| 7 | 56f81ede | Collapse the EVSE scaffolding the second allocator needed; guard the retired names | cf4b3e43 | 1938 passed |
| 8 | 6c309017 | Keep one copy of the settings defaults | 81ef750f | 1938 passed |
| 9 | e1d33ff9 | Make comments say why, not where they came from | f6573c75, 7d16f4b5 | 1939 passed |
| 10 | 9be9ceb6 | Run the serial loop and shutdown only when an interface is loaded | 16ef17ee | 1940 passed |
| 11 | a1167d6d | Withdraw offers when the control pass keeps failing | 4705a546, 8879c62f, 911808ae, 8a61a0f0 | 1944 passed |
| 12 | 4c055723 | Drop the empty Advanced Settings section from the debug page | 668d2270 | 1944 passed |
| 13 | d37038fe | Stop the solar export example recommending flex charging | 9664f8f6 | 1944 passed |
| 14 | 440528a6 | Hold the offers during the chargeStopMode 2 silence | 1a4fc98f | 1945 passed |
| 15 | 956e0672 | Keep running when the Gen2 RS-485 adapter is absent | d9f3f51a, 30c4dbad | 1960 passed (run as 013741be; only the message changed since) |

Dropped as a net-zero pair: 7ee8b607 "Publish amps_offered and amps_desired only when they change" and its revert 77dbdbb7.

## Deviations
- Reordered (moved earlier): 044e5262 into #1, 37ed527e into #2, d105895d into #4, 8a61a0f0 into #11. Small hand-resolved
  conflicts: d105895d vs a3c897c2 / f6573c75 (the "(final review I1)" comment tag beside the removed liftedSession line);
  8a61a0f0 / 1a4fc98f in tests/unit/test_control_tick.py (the silence test from 1a4fc98f kept in #14, the renamed
  wiring-cap test in #11). No group failed tests, so no fallback folding was needed.
- Every commit passes; 1 warning throughout.

## Tree identity
`git diff 044e5262 956e0672` prints nothing (0 bytes).
