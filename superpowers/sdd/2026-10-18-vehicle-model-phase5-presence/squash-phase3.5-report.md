# Squash report: vehicle-model/phase3.5

Branch vehicle-model/phase3.5-squashed (worktree scratchpad/wt-sq35), base ed521403, tip 9e040158.
22 original commits -> 9. Author Mike Bishop on all. Original branch untouched (3be7a5b2). Not pushed.

| # | New SHA | Subject | Original commits | pytest unit+EMS |
|---|---------|---------|------------------|-----------------|
| 1 | 54524f88 | Pin the held-limit migration's edge cases | 99b46236, a8432c91 | 1774 passed |
| 2 | d2b9a547 | Answer sync state from the registry vehicle | 3bc9d23c, 43a016dd | 1783 passed |
| 3 | aeb17c14 | Make Forget atomic with a listing | 70c9e197 | 1785 passed |
| 4 | 785135c3 | Dissolve CarApiVehicle into TeslaAPI and an attached record | 4f952aa0, e2b279db, 966c60cb, 950f848c | 1787 passed |
| 5 | 454f009a | Let the Owner API command cars listed with command_signing off | 9853e251, dd46f661, 6bcb5dd2, f7d45e80, c027d62d, 561349f1, 2f67b699, 490e263e | 1851 passed |
| 6 | 2bf887b1 | Log vehicle wake decisions at INFO | 3c47b816 | 1854 passed |
| 7 | 618af27e | Raise TeslaBLE's default command timeout to 15 s | 65e0f02e | 1854 passed |
| 8 | aa7de6db | Make the Vehicles page readable and drop Vehicle.tier | 18af36eb, dbc8fa6d | 1857 passed |
| 9 | 9e040158 | Record Tesla API observations under the slot that made them | 3be7a5b2 | 1859 passed |

All passes had 1 warning, 0 failures.

Deviations: one reorder — 490e263e (test-only) moved ahead of 3c47b816 to join group 5; applied cleanly.
Messages for groups 6 and 7 kept the original text. Others were rewritten without issue numbers or review-round notes.

Tree identity: `git diff 3be7a5b2 9e040158` prints nothing (0 bytes).
