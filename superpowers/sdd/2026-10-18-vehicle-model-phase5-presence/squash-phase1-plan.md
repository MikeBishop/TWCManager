# Squash plan: vehicle-model/phase1 (03d79325..ec8790ca, 50 commits)

Branch vehicle-model/phase1-squashed, worktree scratchpad/wt-sq1. Original order kept; late fix-ups moved back into the
group they fix (marked *moved*).

1. Key vehicle commands by (cmd, vin) with explicit cancellation — f820af7b 5d2030fd 4797177a
2. Settings lock — 7b608c00 (+ *moved* none; 0c083ea6's comment change stays with group 7)
3. Vehicle field store — 282daa71 939db15b
4. Registry Vehicle identity, claims, tiers — c07006b8 d54dadc1 798ed014
5. Read sources and freshness-bounded read cascade — fd69b47b 8e291b8f
6. VehicleRegistry: membership, forgetting, persistence — 1b5698a0 15f623aa 40eeff79
7. Confirm TWC-reported VINs, anonymous plug-session vehicles — bed2726d c8ed8497 *moved* 0c083ea6
8. Persist registry in settings.json, hourly forget — 310ed914
9. CarApiVehicle backed by the registry — 8e05d775 a0753993
10. Reads through the cascade, no wake on reads; home check off serial thread — 27383ae7 912f11ed
11. Telemetry attaches to registry vehicles — aab52a38 047e009d 748c0a9f a2bb3849 *moved* 7b14e837
12. Home Assistant in the registry — 5445aae8 889ad49f
13. BLE pairing status per VIN — 736f2b6a a1e2e26f db5445b6 *moved* 6307cb31 59ea990d
14. Own-write stamps — b38353f7 8b2b3243 *moved* 3cb14d3b
15. Registry callers: Policy, TWCSlave, web UI, debug by VIN — b193eeba 2be2883b *moved* 2fd2421c
16. Vehicles page lists registry, Add by VIN — 9d2de08c 2ea1bb7a
17. BLE status and range scan on the vehicle page — 20c76df9 fc8436df de2669e9 *moved* ce89f9ef
18. Only a well-formed VIN becomes a registry vehicle — bfa5b1a0
19. Forget a vehicle added by VIN — 03ae854c e2348972 ec8790ca

Fallback: a move that conflicts badly or breaks the suite at its new spot stays at (or folds into the group nearest) its
original position; noted in the report.
