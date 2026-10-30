# Squash plan: vehicle-model/phase2 (ec8790ca..75746bea, 41 commits) -> vehicle-model/phase2-squashed

Groups in build order (first listed commit is picked, the rest fixed up into it). Moved commits marked (moved).

1. Add the provider vocabulary, Provider base and fixed provider order: f8d39b08 e7a91e46
2. Add the Gen2 TWC provider: a3cd7731 a1c914fa
3. Add the Gen3 TWC provider with shared headroom and anonymous sessions: 6a0538de 906e853b b1390896 60fd0389
4. Add the TeslaBLE provider: 353b45d1
5. Split the Tesla API into Owner and Fleet providers: b97e78f9 23508b36
6. Identify the car on a Gen3 from the energy site's live_status: 23a66baf effca9af 415be6c7
7. Add telemetry and HomeAssistant providers; register every module's providers: 84788260 ba2966be 75746bea (moved)
8. Make VehiclePriority a facade over the provider order: 776286c4 2b4b2b87 c708ff2e 289d3d57 210dd292 c7fec91a
9. Replace TeslaAPIEVSE/TeslaAPIController with vehicle endpoints: 1344db4b e0906bd5 (moved)
10. Group endpoints into charging points: 4c0ba70c ffff515e
11. End a provider walk on a Fleet success, skip or wake hold; hold a fallback to Fleet's cadence: 6a74f0ef a40df4d7 (moved) c560b2ab (moved)
12. Let TeslaBLE and TeslaAPI take a targeted charge limit: 0cf0fb6e 9bce1957
13. Offer an idle Gen2 TWC the minimum its heartbeat sends: 1bc4c26f 5afc898b (moved)
14. Let a TWC decide whether its charging point wants power: a3b8d316
15. Drop provider declarations nothing reads: 2537f930
16. Document the provider changes for users: 88d69111 84d71d96
17. Leave the idle TWC minimum out of every budget: a1c8f293 7594307a 31e5d185
   (after the docs because 7594307a/31e5d185 edit the Interface_RS485/CHANGELOG text 88d69111 adds)
