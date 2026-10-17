# Presence branch: rebase onto origin/main and split into a stack

Date: 2026-10-11. Everything is local. Nothing was pushed. `fix/vehicle-presence` (1641265), `deploy/presence` (182aec9) and the ble-threading worktree were not touched.

Worktree: `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-presence`. It has `presence/rebased` checked out.

## Step 1: rebase (`presence/rebased` = 597cd4c)

`git rebase --onto origin/main origin/ble-command-worker presence/rebased`, with origin/main at 8040bd5 and origin/ble-command-worker at 2c38506.

- Merge a78fe3d brought in only 2c38506, which is already in origin/main through #668. The merge dropped out as expected.
- The branch contains no copies of #669, #670 or #671 code. Those only ever reached `deploy/presence` through merges, so no commit was dropped as a duplicate.
- Result: 60 commits. Full suite: **1071 passed** (origin/main alone: 601 passed). The one warning is the same one origin/main shows.

### Conflicts and how they were resolved

| Commit (original) | File | Resolution |
|---|---|---|
| 14ffaf2 Turn the vehicle modules into charge-limit channels | TeslaAPI.py | Took the new signature `applyChargeLimit(limit, vin=None, remoteOnly=False)` and its comment block, and kept #679's `refuseCommandIfReadOnly("set_charge_limit")` as the first statement. |
| 14ffaf2 | VehiclePriority.py | Took the `_dispatch()` refactor (dedented loop) and re-inserted #679's `_skip_read_only_for_command` check into it, ahead of the new caller `skip` check. |
| 9d513dd Keep TeslaAPI dedupe…; scope wakes per VIN | TeslaAPI.py | Kept #671's `loadVehicleList()` extraction and #679's `vehicleListURL()`. Applied only the commit's `vin=None` parameter to `car_api_available`. The wake-loop filter by VIN merged on its own, inside #679's `and not self.readOnly` gate. |
| 32bd76b Drive VehiclePresence from TWC events… | TWCManager.py | Kept #670's `if fakeMaster == 1: Policy.start()` and the commit's own `if fakeMaster == 1: vehiclePresence.start()` as two blocks, the same layout `deploy/presence` used. Shutdown merged cleanly in the order the ledger asked for: `Policy.stop()` first, then `vehiclePresence.stop()`. |
| 32bd76b | tests/unit/test_twcslave.py | Kept both #670's `TestPolicyNotOnMainLoop` and the new `TestPresenceTriggers`. |
| b502780 early restore is BLE only (localOnly) | VehiclePriority.py | Kept the read-only skip and added the `only` (localOnly) filter to the caller-skip check. |
| 7295a10 localOnly safe everywhere | TeslaAPI.py | The `localOnly` early return comes first, then #679's read-only refusal. A localOnly call is a quiet no-op, not a logged refusal. |
| 6aca1eb Don't resend a charge rate… | TeslaAPI.py `setChargeRate` | Kept #679's `getCarApiBaseURL()` guard (the refusal stays at the top), then the commit's `int(charge_rate)`. |
| a5480b7 Harden setChargeRate… | TeslaAPI.py | Same spot: #679's guard, then the commit's `int(float())` parsing. |

### Fixes to upstream tests, squashed into the commit that broke them

After the rebase, 6 tests failed and 10 errored, all in tests that #679 added and that predate the presence API. Each fix went into the commit that caused the failure, so every commit stays green:

- **087a2b6 (Key normal charge limits by VIN):** `tests/unit/teslatokens.py` `FakeMaster` gains a no-op `migrateNormalChargeLimit()`. `TeslaAPI.addVehicle` now calls it.
- **a7e79c7 (vehicle modules as channels):** two changes in `test_teslaapi_readonly_gate.py`. `applyChargeLimit(80, checkArrival=True)` becomes `applyChargeLimit(80)`, because `checkArrival` no longer exists. The parametrized `test_every_command_method_skips` now passes `(80,)` to `applyChargeLimit`, which is an explicit method with a required `limit`.
- **67e866a (scope wakes per VIN):** `TestWakeIsPerVin` sets `api.baseURL`. Since #679, `car_api_available` returns early when there is no base URL.

### Tests at every commit

Each of the 60 rebased commits was run on its own. All pass except 4c5a008 (originally 6437f29, "A TWC unplug needs a plugged run…"): 1 failure, `TestSameTwcReplugEndToEnd`. The original 6437f29 fails the same way on its old base (917 passed, 1 failed), and the next commit fixes it. This is pre-existing and was not introduced by the rebase.

## Step 2: the stack

| Branch | Base | Head | Commits | lib +/- | tests +/- | Suite |
|---|---|---|---|---|---|---|
| presence/1-command-queue | origin/main 8040bd5 | ce9df78 | 2 | +60/-13 | +174/-27 | 613 passed |
| presence/2-charge-limits | ce9df78 | 1cc9178 | 13 | +569/-279 | +1183/-4 | 736 passed |
| presence/3-presence-tracker | 1cc9178 | c7d4cf1 | 19 | +1041/-23 | +1960/-0 | 921 passed |
| presence/4-arrive-depart | c7d4cf1 | 94cf1c5 | 19 | +821/-99 | +1849/-186 | 1035 passed |
| presence/5-fleet-rate-queue | 94cf1c5 | b7e1623 | 8 | +163/-11 | +455/-0 | 1073 passed |
| fix/672-fleet-evse (separate) | origin/main 8040bd5 | 937fadf | 6 | +137/-8 | +346/-0 | 633 passed |

The whole suite was run at every commit of every branch. Every commit passes except 4c5a008 in branch 4, the pre-existing failure described above.

### 1. presence/1-command-queue (wave C, fixes #667)
- cbd5952 Key vehicle commands by (cmd, vin) and add explicit cancellation
- ce9df78 Pass vin to applyChargeLimit only when set

### 2. presence/2-charge-limits (wave D)
- 087a2b6 Key normal charge limits by VIN
- a7e79c7 Turn the vehicle modules into charge-limit channels
- 67e866a Keep TeslaAPI dedupe on the policy path; scope wakes and HA errors per VIN
- c2b59c6 TeslaAPI: log the outcome of a per-VIN charge limit apply at INFO
- c50d510 TeslaAPI.resetChargeLimitState also clears stopAskingToStartCharging
- 4c3a33e TeslaBLE reads the car's charge limit before setting it
- 311022b TeslaBLE skips the pre-write read while the circuit breaker is open
- bedcd6c Add ChargeLimitRules: one copy of the charge-limit decision rules
- 22e5841 TeslaAPI.applyChargeLimit uses the shared charge-limit rules
- 0535d43 TeslaBLE.applyChargeLimit uses the shared rules and prefers telemetry
- ef35253 TeslaBLE skips a restore without a wake when no limit is held
- 16dd529 A restore reads the car live when telemetry shows a limit not ours
- 1cc9178 TeslaAPI's live read on a restore never goes over BLE

Moved forward from after wave E and the features: the BLE read-before-write, the breaker skip, the ChargeLimitRules extraction (all three commits), the no-wake restore skip and the restore live-read fixes. Their library changes replayed without a conflict. Only the tests needed work: test classes that later commits append had to be re-placed, and `open_breaker()` moved, as described next.

A check at this branch's tip: `localOnly`, `bleProven`, `vehiclePresence` and `VehiclePresence` code are all absent from TeslaAPI, TeslaBLE, HomeAssistant and VehiclePriority. `test_flags_are_gone` expects `["self","limit","vin","remoteOnly"]`. The only mentions of presence are comments that a7e79c7 wrote ("the caller (VehiclePresence)…").

### 3. presence/3-presence-tracker (wave E, includes the core re-apply-on-return fix)
- 7277dd0 Add a BLE presence probe that never wakes the car
- a73d5b3 Add VehiclePresence: per-VIN home/away tracking on its own thread
- ceacea0 Harden VehiclePresence passes against bad inputs
- 15d6805 Add presence sources: telemetry, BLE probe and online-only API
- 2cebb08 Presence sources: add request timeout, skip non-BLE VINs, no guess without home
- 0972265 Track BLE proof per VIN so API-only cars are never declared away by BLE
- 27a5e1f Add arrival and departure handlers for VehiclePresence
- 93e6104 Drive VehiclePresence from TWC events, telemetry and the API
- 3b83505 Make CarApiVehicle.atHome defer to VehiclePresence
- b0ddcdf TeslaBLE: policy-wide apply skips cars presence says are away
- 7594e70 VehiclePresence: bound observations and due times without the thread
- bb5837c Treat a TWC-reported VIN as proof of home, owned by presence
- b8e55a0 Test depart-then-return through the real handlers and queue
- d4055ae Arrival before the first policy evaluation queues nothing
- 8cf363e Re-evaluate at-home after moving the home location
- a2855bb Keep proofs and late presence checks from being undone
- f939ff8 Pushed arrivals carry the telemetry charge limit
- 490c7cb Fill in the telemetry charge limit for arrivals only
- c7d4cf1 Evidence the car is present closes TeslaBLE's circuit breaker

Test-only adjustments made because wave D now comes first:
- b0ddcdf: its two `TestSkipsAwayVehicles` command lists now include the `("state","charge")` read. Originally 4c3a33e made that edit, but at that point the tests didn't exist yet.
- c7d4cf1: no longer defines the `open_breaker()` test helper. 311022b in branch 2 defines it now, because its own tests need it.

### 4. presence/4-arrive-depart (features)
- 045160f Arrivals of BLE-proven cars wait for BLE to confirm
- 443b181 A car home by the arriving timeout is not declared away by BLE
- c274d6c TWC slaves report debounced unplug and replug to presence
- fada5b4 Unplugging a BLE car makes it DEPARTING and restores its limit over BLE
- df426ed Attribute an unplug to the car of this plug session, not lastVIN
- 07c06b2 The early restore on unplug is BLE only (localOnly)
- 8764711 DEPARTING slows its BLE probes after the cap instead of stopping
- 7e9ca95 Trust NON_TESLA only on a VIN-reading TWC; localOnly safe everywhere
- b3c692a Hand-set limits are adopted by the channel, not on arrival
- 66acf97 The departure handler always queues the restore while a limit is held
- 87bb011 Unplug attribution: exclude idle cars elsewhere, keep plugVIN across a hold flicker
- 6805b0b Replug and arriving-timeout exits reset the failed-probe count
- b0a86f9 A raising BLE source counts as a failed probe for a DEPARTING car
- 05437b7 Plug evidence on another TWC brings the one departing car home
- 0b46958 Test: a full car replugged on a VIN-reading TWC comes home
- 11753a9 Power-start is plug evidence only shortly after a plug-in
- 4c5a008 A TWC unplug needs a plugged run before it and none in the link grace (pre-existing red, see Step 1)
- 32d798a Presence honours live telemetry's plug state
- 94cf1c5 TeslaMate's plugged_in feeds presence

Test-only adjustment: fada5b4's `test_restore_ok_then_departure_queues_nothing` expects `limits[VIN1] == (80, -1)`. In the original history, the later 0535d43 made that edit. Now that 0535d43 comes earlier, the test has to start with the new value.

### 5. presence/5-fleet-rate-queue (the #672 fix plus "queue the Fleet rate to the vehicle worker")
- ace0fef, 680c5ec, 52837bd, 03a47e2, e5478df, 5bda833: cherry-picks of the `fix/672-fleet-evse` commits. 03a47e2 adds only a test here, because 94cf1c5 already carries the `plugged_in` mapping.
- 806ec3b Queue Fleet API charge rates to the vehicle worker
- b7e1623 Update distributeEVSEPower docstring for the queued Fleet rate

Where the queue part sits: its only real dependency is wave C (`queue.cancel` and the worker), plus the #672 controller code beneath it. It sits at the top as branch 5 so that #672 lands on main on its own. The branch is built from the exact `fix/672-fleet-evse` commits, so once #672 merges, rebasing branch 5 should mostly drop them. Once #672 is in main, the queue commits could also move down to sit right after branch 1.

### fix/672-fleet-evse (off origin/main, not stacked)
- 749a9fe No Fleet API EVSE for a car a TWC serves or may serve
- ba0e995 Don't resend a charge rate the car already accepted
- 5260d14 Resend an unchanged charge rate after 10 minutes
- bbd5081 Read TeslaMate's plugged_in onto the vehicle (new: split from 96b18db; TeslaMateVehicle `parse_bool` plus the event mapping, and a new `tests/unit/test_teslamate_plugged_in.py`; ends with the Co-Authored-By trailer)
- b380b4c Close the Fleet EVSE gaps for a car an unnamed TWC may serve
- 937fadf Harden setChargeRate's skip-repeat record

The controller code stands alone on main: it reads `plugVIN` and `NON_TESLA` through `getattr`. Its tests used `TWCSlave.NON_TESLA`, which main lacks, so 749a9fe's test file defines `NON_TESLA = getattr(TWCSlave, "NON_TESLA", "non-tesla")`. That is the same value the presence branch uses. On main, `plugVIN` is never set, so the controller relies on `currentVIN` plus the blind and telemetry-plugged rules. The plug-session cases in its tests describe the presence branch.

## Tree-equality check

- With the stack in its original order (before branch 5 was rebuilt from the fix/672 commits), the tree was identical to `presence/rebased`: `git diff presence/rebased <top>` was empty. Two leftovers from re-placing test classes were folded back into the commit that introduced each one: a missing blank-line pair, and the position of one test.
- `git diff presence/rebased presence/5-fleet-rate-queue`: **no library differences**. There are two test-only differences, both from basing branch 5 on the fix/672 commits:
  1. `tests/unit/test_teslaapi_controller.py`: a local `NON_TESLA` constant replaces `TWCSlave.NON_TESLA` (+7/-3).
  2. `tests/unit/test_teslamate_plugged_in.py`: a new file (19 lines, 2 tests) from the fix/672 `plugged_in` commit.
- `black --check` is clean on the library files touched by conflict resolution (TeslaAPI, VehiclePriority, TWCManager, TeslaMateVehicle).

## Needs your decision

1. **Branch 2 on its own loses the Fleet API arrival re-apply and departure restore.** a7e79c7 removes the `checkArrival`/`checkDeparture` handling from TeslaAPI and TWCManager.py. The queueing remains: TWCSlave still queues those tasks, and HTTPControl's `/api/checkArrival` still queues them too, but nothing handles them until branch 3 replaces them with presence. The ledger already called this "inert between T3 and T8; don't deploy mid-branch". If PR 2 merged alone, Fleet-API users would lose re-apply on return. Options: (a) accept this, say so in PR 2, and merge 2 and 3 together; (b) merge waves D and E into one PR; (c) write a small shim that keeps the old checkArrival path until E. Option (c) is new code, so I didn't write it. I recommend (a).
2. **Two commits of the ChargeLimitRules cleanup land in branch 4, not branch 2.** "Hand-set limits are adopted by the channel, not on arrival" (b3c692a) and "The departure handler always queues the restore while a limit is held" (66acf97) remove adoption code from the arrival and departure handlers. They also remove the telemetry limit that f939ff8 and 490c7cb fill into arrivals, and they touch the ARRIVING code from the features. To move them into branch 3, I would have had to strip `limitLookup` out of the feature commits by hand, so they stay in branch 4. As a result, branch 3 still has handler-side adoption and the arrival telemetry fill working alongside the channel adoption from branch 2. That combination existed in the original history between 389815e and eec589b. Alternative: squash f939ff8, 490c7cb and part of b3c692a into a hand-made "net" commit in branch 3. That means rewriting code, so I didn't do it.
3. **`localOnly` is in branch 4, not branch 2.** The email puts `localOnly` in wave D, but it arrives with the departing feature (07c06b2, 7e9ca95), which is its only user. I left it there and recommend updating the email or PR text to match.
4. **#672's placement**: `fix/672-fleet-evse` on main, plus branch 5 on top of the stack, which reuses the same commits and adds the queue part. Confirm this shape, or ask for the queue commits right after branch 1 once #672 has merged.
5. **Trailers on the amended commits.** 087a2b6, a7e79c7 and 67e866a absorbed my upstream-test fixups but still end with only their original `Claude Sonnet 5.5` trailer. Adding an Opus line would change every SHA above them in branches 2 to 5, so I left them alone. The other commits I adjusted (311022b, b0ddcdf, c7d4cf1, fada5b4, 7e9ca95, 749a9fe) already carry the Opus trailer.
6. **Leftover branches and worktree:** `presence/rebased` and the `wt-presence` worktree are kept. The scratch branch `split/try` and the `wt-test` worktree were deleted.
