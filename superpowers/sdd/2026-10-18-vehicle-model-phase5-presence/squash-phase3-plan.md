# Squash plan: vehicle-model/phase3 (75746bea..ed521403, 97 commits) -> vehicle-model/phase3-squashed

Original order kept except where marked (moved).

1. Desired-state store and VIN-keyed held limits: 760a60f2 3f71f9ca 748ebb8f 1684feb5 513e16de ffc7e7b6 39b3ba0b
2. Provider command methods run on BLE and cloud command workers: 71e7f06d 3488ea04 3a78c543 e8ed2be8 c868dd5e caf2b07f 12f212e5 8050fc92 202dd9ac fdb9c253 b825cddd
   (lanes are introduced and replaced by the workers inside this group, so they fold together)
3. Provider capability tables: c5795af4 c3d0bb74
4. Reconciler with charge-limit rules and paid fallback: e37bd28a 3ce9e39d b7e296ed cac93394 9a85ea6f 53edc097 9abfc1ed fafc26b5
5. Charge limits as desired state, legacy limit path removed: 74ff8c43 3648fbb3 fe766da4 a32b7342
6. Start/stop as desired state, legacy path removed: a81beb6c b8c0a2c0 a3d629bc 77e6b854
7. Amps as desired state, legacy rate path removed: 7958b471 2b2fb276 c164c8f4 248b3d84 86527794 b37f588f 07a6512a 25b7be4c
8. Carry main's remaining command behaviours: e6d7f650 e5464a16 4b191425 7054e603 52d11e5a 57c6c50a
9. TeslaBLE single classified command: bef35e98 7c291d68 a25ad3eb
10. Reads through providers: 71532eca 8fc898d3 b03dcdf3
11. One TeslaAPI request helper: 17537d54 9fcf416d 450c192e 6305b256 da1a0501 ea1ec8ae 7f727beb(moved) ae5f2801(moved)
12. Presence from position: 479190c1 40ba12be a1225bad ea6c0c88 5c73c3f6 3ade80e7(moved)
13. Remove dead code: 7e669168 929a2689 777bdb6b 63d1dd08 401a4866(moved) a92cdd22(moved)
14. Docs: 541b981d 6c5cb2f4 c7b7e110
15. Parity test and fixes it found: 77162410 0113c3c2 a7dc9f82 e8746650(moved)
16. More dead/test-only helper removal: 51871492 1bcfc82b 7b1e86da 47dbef90
17. Home Assistant logging: 13f0c8ed 00047bfc
18. Re-check after an unanswered cloud wake: 7e6d82d5(swapped after 00047bfc) fa686f06 ed94872c 304788e2 7ae4d731
19. Held limits in chargeLimits; never set an unknown limit: 69a8e0ff 89963138 ed521403
