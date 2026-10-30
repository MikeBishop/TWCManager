# Squash report: vehicle-model/phase1

Branch vehicle-model/phase1-squashed (worktree scratchpad/wt-sq1), base 03d79325, new tip 45c21341c47a09b06e35645ec56ab059f3bc552a.
50 original commits -> 19. Original branch untouched; nothing pushed.

## Groups

| # | New SHA | Subject | Original commits folded | Tests |
|---|---|---|---|---|
| 1 | b95840bd | Key vehicle commands by (cmd, vin) and add explicit cancellation | f820af7b 5d2030fd 4797177a | 827 passed |
| 2 | f32c363f | Add a settings lock taken by off-thread writers | 7b608c00 | 832 passed |
| 3 | 3ecfdfcf | Add the vehicle field store | 282daa71 939db15b | 845 passed |
| 4 | 14ee31fd | Add the registry Vehicle with VIN or anonymous identity, claims and tiers | c07006b8 d54dadc1 798ed014 | 859 passed |
| 5 | 5867cfcf | Add read sources and a freshness-bounded read cascade that never wakes | fd69b47b 8e291b8f | 872 passed |
| 6 | 00cb287b | Add VehicleRegistry with forgetting, persistence and user-asserted vehicles | 1b5698a0 15f623aa 40eeff79 | 903 passed |
| 7 | 5376497e | Confirm TWC-reported VINs and track anonymous plug-session vehicles | bed2726d c8ed8497 0c083ea6* | 922 passed |
| 8 | 2a2232d2 | Persist the vehicle registry in settings.json and forget unseen vehicles hourly | 310ed914 | 926 passed |
| 9 | 411f83fa | Back CarApiVehicle fields with the registry | 8e05d775 a0753993 | 942 passed |
| 10 | 94f72377 | Read vehicle state through the registry cascade without waking cars | 27383ae7 912f11ed | 966 passed |
| 11 | 99659f01 | Attach telemetry to registry vehicles by VIN or name | aab52a38 047e009d 748c0a9f a2bb3849 7b14e837* | 1013 passed |
| 12 | bc5066bd | Register Home Assistant vehicles, claims and reads in the registry | 5445aae8 889ad49f | 1024 passed |
| 13 | bb886cc3 | Track BLE pairing status per VIN | 736f2b6a a1e2e26f db5445b6 6307cb31* 59ea990d* | 1064 passed |
| 14 | 1d20fd4f | Stamp the registry with our own charge-limit and charge-rate writes | b38353f7 8b2b3243 3cb14d3b* | 1081 passed |
| 15 | c2881e10 | Read vehicles from the registry in Policy, TWCSlave and the web UI | b193eeba 2be2883b 2fd2421c* | 1092 passed |
| 16 | 8082eee9 | List the vehicle registry on the Vehicles page and add vehicles by VIN | 9d2de08c 2ea1bb7a | 1100 passed |
| 17 | 66efc80a | Show BLE pairing status and a range scan on the vehicle page | 20c76df9 fc8436df de2669e9 ce89f9ef* | 1149 passed |
| 18 | 6dc1356e | Only a well-formed VIN becomes a registry vehicle | bfa5b1a0 | 1152 passed |
| 19 | 45c21341 | Forget a vehicle added by VIN that nothing else knows | 03ae854c e2348972 ec8790ca | 1156 passed |

\* = moved back from its original position into the group it fixes.

## Deviations

- None from the plan. Moving 0c083ea6 and 6307cb31 back produced append-only conflicts (both sides adding tests at
  file end) in tests/unit/test_twcmaster_vin_confirmation.py (at 0c083ea6, then replaying 912f11ed) and
  tests/unit/test_teslable_pairing_status.py (at 6307cb31, then replaying 20c76df9, fc8436df, de2669e9); resolved by
  keeping both sides in final-file order. 59ea990d, 7b14e837, 3cb14d3b, 2fd2421c, ce89f9ef applied cleanly. No code
  conflicts.

## Tests

Every new commit: tests/unit + tests/EMS all pass (counts in table; 1 warning each, pre-existing). No failures.

## Tree identity

`git diff ec8790ca vehicle-model/phase1-squashed` prints nothing; `git rev-parse ec8790ca^{tree} HEAD^{tree}`:

```
a011f208c624eeca38826099b130f7c704104329
a011f208c624eeca38826099b130f7c704104329
```
