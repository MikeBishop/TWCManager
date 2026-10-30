# Squash plan: vehicle-model/phase3.5 (BASE ed521403, TIP 3be7a5b2, 22 commits)

Branch vehicle-model/phase3.5-squashed, worktree scratchpad/wt-sq35. Original order kept except 490e263e
(test-only) moves before 3c47b816 to join the Owner API group.

1. Pin the held-limit migration's edge cases — 99b46236, a8432c91
2. Answer sync state from the registry vehicle — 3bc9d23c, 43a016dd
3. Make Forget atomic with a listing — 70c9e197
4. Dissolve CarApiVehicle into TeslaAPI and an attached record — 4f952aa0, e2b279db, 966c60cb, 950f848c
5. Let the Owner API command cars listed with command_signing off — 9853e251, dd46f661, 6bcb5dd2, f7d45e80,
   c027d62d, 561349f1, 2f67b699, 490e263e
6. Log vehicle wake decisions at INFO — 3c47b816
7. Raise TeslaBLE's default command timeout to 15 s — 65e0f02e
8. Make the Vehicles page readable; drop Vehicle.tier — 18af36eb, dbc8fa6d
9. Record Tesla API observations under the slot that made them — 3be7a5b2
