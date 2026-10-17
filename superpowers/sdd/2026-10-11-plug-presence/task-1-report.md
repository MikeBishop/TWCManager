# Task 1 report

Status: DONE. Branch presence/3-plug-presence, head c66f3a2, worktree <scratch>/wt-plug. 30 commits over presence/2-charge-limits (17 + 13).

## Commands
- git worktree add -b presence/3-plug-presence <scratch>/wt-plug presence/2-charge-limits
- Step 2: cherry-pick of the 17 SHAs, all clean. pytest: 905 passed.
- Step 3: scripted loop <scratch>/carry.py: cherry-pick -n, checkout HEAD -- the two presence files, commit (-C for whole rows, -F <scratch>/msg-<sha> for partial rows, with the carried-without paragraph before the Opus 5.5 trailer; subjects replaced for fada5b4, 05437b7, 32d798a).
- Note: the cherry-picks of c274d6c fada5b4 07c06b2 b3c692a 66acf97 05437b7 32d798a reported content conflicts, but only in lib/TWCManager/VehiclePresence.py and tests/unit/test_vehicle_presence.py, which the next step discards by checking out HEAD. The script checked that no other file conflicted. Nothing else was resolved by hand.

## Results
- pytest tests/unit -q: 958 passed (after step 3).
- git diff --stat presence/4-arrive-depart: only the two files (VehiclePresence.py 559 lines, test_vehicle_presence.py 1222 lines, 32 insertions, 1749 deletions).

## Commits (oldest to newest)
b712d53 Add a BLE presence probe that never wakes the car
dc7518f Add VehiclePresence: per-VIN home/away tracking on its own thread
4c7e737 Harden VehiclePresence passes against bad inputs
5f783ac Add presence sources: telemetry, BLE probe and online-only API
38767e9 Presence sources: add request timeout, skip non-BLE VINs, no guess without home
50f02ed Track BLE proof per VIN so API-only cars are never declared away by BLE
a485369 Add arrival and departure handlers for VehiclePresence
9f68869 Drive VehiclePresence from TWC events, telemetry and the API
050a767 Make CarApiVehicle.atHome defer to VehiclePresence
ca95fed TeslaBLE: policy-wide apply skips cars presence says are away
1454bdb VehiclePresence: bound observations and due times without the thread
0b92117 Treat a TWC-reported VIN as proof of home, owned by presence
88988ad Test depart-then-return through the real handlers and queue
425892d Arrival before the first policy evaluation queues nothing
b06ab24 Re-evaluate at-home after moving the home location
c15c818 Keep proofs and late presence checks from being undone
aeb2488 Evidence the car is present closes TeslaBLE's circuit breaker
c92cef4 TWC slaves report debounced unplug and replug to presence
5455208 Add the departing handler: restore the limit over BLE on unplug
b85a59b Attribute an unplug to the car of this plug session, not lastVIN
f73ab99 The early restore on unplug is BLE only (localOnly)
a4bd744 Trust NON_TESLA only on a VIN-reading TWC; localOnly safe everywhere
0685c3f Hand-set limits are adopted by the channel, not on arrival
220d1bc The departure handler always queues the restore while a limit is held
e526329 Unplug attribution: exclude idle cars elsewhere, keep plugVIN across a hold flicker
be55c56 TWC plug evidence says whether the TWC reads VINs
3739fef Power-start is plug evidence only shortly after a plug-in
92e4748 A TWC unplug needs a plugged run before it and none in the link grace
ac3f684 Add CarApiVehicle.pluggedIn and a live-telemetry plug lookup
c66f3a2 TeslaMate's plugged_in feeds presence
