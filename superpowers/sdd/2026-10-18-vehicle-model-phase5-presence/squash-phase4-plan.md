# Squash plan: vehicle-model/phase4 (3be7a5b2..044e5262, 28 commits)

Branch vehicle-model/phase4-squashed, worktree scratchpad/wt-sq4. Original order kept except where noted.

1. Send every RS-485 message from the serial loop — e440006f, 044e5262 (3.8 test fix moved up)
2. Refresh Tesla tokens off the serial loop, one refresh per slot at a time — 5e7cb5f4, 95acd4bb, 37ed527e (moved up)
3. Run the one distributor on a 1 s control tick for every install — 7a85f0b7, 17d1b1e1
4. Compute TWC offers on the control tick; charging points own car amps — a3c897c2, d105895d (moved up)
5. Plan a car's charge rate before its start command — 4ed54888
6. Decide TWC start and stop on the control tick — 4b3e048c, 3cfb5a77
7. Collapse the EVSE scaffolding the second allocator needed — cf4b3e43
8. Keep one copy of the settings defaults — 81ef750f
9. Make comments say why, not where they came from — f6573c75, 7d16f4b5
10. Run the serial loop and shutdown only when an interface is loaded — 16ef17ee
11. Withdraw offers when the control pass keeps failing — 4705a546, 8879c62f, 911808ae, 8a61a0f0 (moved up past 668d2270/9664f8f6/1a4fc98f)
12. Drop the empty Advanced Settings section from the debug page — 668d2270
13. Stop the solar export example recommending flex charging — 9664f8f6
14. Hold the offers during the chargeStopMode 2 silence — 1a4fc98f
15. Keep running when the Gen2 RS-485 adapter is absent — d9f3f51a, 30c4dbad
Dropped (net zero): 7ee8b607 and its revert 77dbdbb7.

Fallback: a move that conflicts folds into the nearest group in original position instead.
