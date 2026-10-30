# Squash report: vehicle-model/phase2 -> vehicle-model/phase2-squashed

BASE ec8790ca, original TIP 75746bea (41 commits), new tip 0232af54cc47c8db0ea007be9c553480523641c5 (17 commits).
Worktree: scratchpad/wt-sq2. Original branch untouched (still 75746bea). Author Mike Bishop on every commit.

| # | New SHA | Subject | Original commits | Tests |
|---|---|---|---|---|
| 1 | 10fa92d4 | Add vehicle providers and a fixed provider order | f8d39b08 e7a91e46 | 1179 passed |
| 2 | c1fa9f23 | Add the Gen2 TWC provider | a3cd7731 a1c914fa | 1192 passed |
| 3 | 3e1bc1ea | Add the Gen3 TWC provider with one shared headroom | 6a0538de 906e853b b1390896 60fd0389 | 1213 passed |
| 4 | 86a47374 | Add the TeslaBLE provider | 353b45d1 | 1219 passed |
| 5 | 80f5e73a | Split the Tesla API into Owner and Fleet providers | b97e78f9 23508b36 | 1231 passed |
| 6 | 09b70747 | Identify the car on a Gen3 TWC from the energy site's live_status | 23a66baf effca9af 415be6c7 | 1269 passed |
| 7 | b3a78a74 | Add telemetry and HomeAssistant providers; register them at startup | 84788260 ba2966be 75746bea (moved) | 1286 passed |
| 8 | ce5d8738 | Make VehiclePriority a facade over the provider order | 776286c4 2b4b2b87 c708ff2e 289d3d57 210dd292 c7fec91a | 1280 passed |
| 9 | 1ac655d2 | Replace TeslaAPIEVSE/TeslaAPIController with vehicle endpoints | 1344db4b | 1270 passed |
| 10 | ddc71721 | Group charging endpoints into charging points and allocate per point | 4c0ba70c ffff515e e0906bd5 (moved) | 1296 passed |
| 11 | 19ec69e6 | End a provider walk on a Fleet success, skip or wake hold | 6a74f0ef a40df4d7 (moved) c560b2ab (moved) | 1309 passed |
| 12 | 869f5ce4 | Let TeslaBLE and TeslaAPI take a targeted charge limit | 0cf0fb6e 9bce1957 | 1315 passed |
| 13 | 7bf729ac | Offer an idle Gen2 TWC the minimum its heartbeat sends | 1bc4c26f 5afc898b (moved) | 1321 passed |
| 14 | b20758fc | Let a TWC decide whether its charging point wants power | a3b8d316 | 1322 passed |
| 15 | 038ccb8d | Drop provider declarations nothing reads | 2537f930 | 1322 passed |
| 16 | 567d079c | Document the provider changes for users | 88d69111 84d71d96 | 1322 passed |
| 17 | 0232af54 | Leave the idle TWC minimum out of every budget | a1c8f293 7594307a 31e5d185 | 1329 passed |

All 41 original commits used exactly once. Every commit passes `tests/unit tests/EMS` (1 warning each).

## Deviations
- Plan had e0906bd5 (restored endpoint-controller tests) in group 9; it conflicted there because its context includes
  tests 4c0ba70c adds, so it is folded into group 10 instead.
- Group 17 sits after the docs commit because 7594307a/31e5d185 edit CHANGELOG/Interface_RS485 text that 88d69111 adds.
- Docs kept as a docs-only commit (16): 88d69111 spans every group.

## Tree identity
`git diff 75746bea 0232af54 | wc -c` -> 0.
