# Squash report: vehicle-model/phase3 -> vehicle-model/phase3-squashed

BASE 75746bea, original TIP ed521403 (97 commits). New tip e616207eb0c7450360961619fd90443e1b18b423 (19 commits), worktree /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-sq3.

| # | New SHA | Subject | Original commits folded | Suite |
|---|---|---|---|---|
| 1 | a7618b35 | Add the desired-state store and VIN-keyed held charge limits | 760a60f2 3f71f9ca 748ebb8f 1684feb5 513e16de ffc7e7b6 39b3ba0b | 1386 passed |
| 2 | 7bd3f354 | Run vehicle commands as classified provider outcomes on BLE and cloud workers | 71e7f06d 3488ea04 3a78c543 e8ed2be8 c868dd5e caf2b07f 12f212e5 8050fc92 202dd9ac fdb9c253 b825cddd | 1457 passed |
| 3 | 1cf3c016 | Declare provider capabilities, costs and suppressions as tables | c5795af4 c3d0bb74 | 1556 passed |
| 4 | 56c81582 | Add the reconciler: charge-limit rules, adoption and one paid fallback | e37bd28a 3ce9e39d b7e296ed cac93394 9a85ea6f 53edc097 9abfc1ed fafc26b5 | 1674 passed |
| 5 | 93a46d9a | Set charge limits through desired state and delete the legacy limit path | 74ff8c43 3648fbb3 fe766da4 a32b7342 | 1669 passed |
| 6 | 0572ab02 | Start and stop charging as desired state and delete the legacy path | a81beb6c b8c0a2c0 a3d629bc 77e6b854 | 1680 passed |
| 7 | 8d4d7d3a | Set charge amps through desired state and delete the legacy rate path | 7958b471 2b2fb276 c164c8f4 248b3d84 86527794 b37f588f 07a6512a 25b7be4c | 1618 passed |
| 8 | 8dd2a703 | Carry main's remaining command behaviours onto the reconciler | e6d7f650 e5464a16 4b191425 7054e603 52d11e5a 57c6c50a | 1659 passed |
| 9 | ae3c5455 | Send one classified TeslaBLE command with one quick retry | bef35e98 7c291d68 a25ad3eb | 1672 passed |
| 10 | 3d752b04 | Read vehicle fields through the providers | 71532eca 8fc898d3 b03dcdf3 | 1677 passed |
| 11 | 0cc09647 | Send every TeslaAPI request through one helper and status classifier | 17537d54 9fcf416d 450c192e 6305b256 da1a0501 ea1ec8ae 7f727beb(moved) ae5f2801(moved) | 1722 passed |
| 12 | ae157956 | Locate cars from their latest free position for presence | 479190c1 40ba12be a1225bad ea6c0c88 5c73c3f6 3ade80e7(moved) | 1733 passed |
| 13 | ee5581de | Remove code the new command path orphaned or that was already dead | 7e669168 929a2689 777bdb6b 63d1dd08 401a4866(moved) a92cdd22(moved) | 1735 passed |
| 14 | 9be4a1f4 | Document the reconciler, paid fallback and presence | 541b981d 6c5cb2f4 c7b7e110 | 1735 passed |
| 15 | 23e692c6 | Pin old-vs-new command behaviour per install type and fix what it found | 77162410 0113c3c2 a7dc9f82 e8746650(moved) | 1768 passed |
| 16 | 89e1a294 | Remove dead and test-only helpers | 51871492 1bcfc82b 7b1e86da 47dbef90 | 1764 passed |
| 17 | 414e24ea | Log the Home Assistant host and exception types, not URLs or text | 13f0c8ed 00047bfc | 1766 passed |
| 18 | 97bf9f94 | Check again after a cloud wake the car did not answer | 7e6d82d5(swapped after 00047bfc) fa686f06 ed94872c 304788e2 7ae4d731 | 1774 passed |
| 19 | e616207e | Keep held limits in chargeLimits, keyed by VIN; never set an unknown limit | 69a8e0ff 89963138 ed521403 | 1769 passed |

## Deviations
- Moved (no conflicts): 7f727beb, ae5f2801 into group 11; 3ade80e7 into 12; 401a4866, a92cdd22 into 13; e8746650 into 15; 7e6d82d5 after 00047bfc into 18.
- Group 2 folds the per-channel lanes with the provider command methods and the workers that replace the lanes, so no commit adds Lanes.py only to delete it.
- None failing: every new commit passes tests/unit + tests/EMS (counts above; 1 warning each, no failures).

## Tree identity
`git diff ed521403 e616207e` prints nothing (0 bytes). All 97 original commits used exactly once (checked by sorted-list diff). Author kept: Mike Bishop <<email>> on every commit.
