Title: Vehicle model, phase 4: one control tick and one distributor for every install (closes #690)

Phase 4 of the 1.4.0 vehicle-model rework (the spec runs to Phase 5; this stack now opens Phases 1, 2, 3, 3.5 and 4); base `vehicle-model/phase3.5`; review after Phase 3.5.

## Where this sits

Stack: Phase 1 #703 → Phase 2 #704 → Phase 3 #705 → Phase 3.5 #706 → **Phase 4 (this PR)** → *later, not in this stack:* Phase 5 presence port (which also takes the rest of the Vehicles tab).

## What changes for users

- **One distributor on a ~1 s control tick, for every install.** A `ControlTick` thread computes every Gen2 offer and makes the start/stop decisions. Installs with `vehicle.TeslaAPI.enabled: false` move from the old per-slave sharing to the distributor's water-fill. A Gen2 target can lag by up to one tick.
- **Gen3-only installs are controlled.** Before, the distributor ran only once a Gen2 slave was known. Configure `controller.Gen3TWCs`; nothing else changes. The Gen3 units keep their own RS-485 adapter (`controller.Gen3TWCs.port`), and the Gen2 link (`interface.RS485`) stands down if it is pointed at that same port.
- **Vehicle-only installs are controlled.** Configure the vehicle module(s); nothing else changes.
- **A missing Gen2 adapter no longer stops TWCManager.** If the Gen2 link's port (`interface.RS485.port`) can't be opened, it logs one error and retries every 30 s, so an adapter that appears late at boot is picked up without a restart; before, startup aborted. While the link is closed, messages queued for the TWCs are dropped rather than sent late, and the "no slave linked yet" hold on API-rated cars applies only while the link is open. An adapter unplugged at run time now takes the same close-and-retry path instead of logging a traceback every 5 s.
- **Fail-safe.** If the control pass keeps failing, its traceback is logged on the first failure and every 60th; after 30 failed passes in a row (about 30 s) the offers are withdrawn: each TWC drops to its idle minimum and each Gen3 unit to a zero target, while a car controlled only through the API keeps its last rate. The first good pass restores normal offers.
- **Rate before start.** When a rate and a start are due on the same pass, the order is limit, then rate, then start; a stop never waits behind a rate. The car starts at the intended rate, which keeps overshoot down when tracking solar.
- **Token refresh is off the serial loop (closes #690).** It runs on the background thread, one refresh per slot at a time; a second caller waits and shares the result, so a single-use refresh token is never spent twice. The first periodic refresh runs 5 minutes after start.
- **RS-485 writes come only from the serial loop.** Other threads call `master.sendRS485(msg)`, which queues the message; the loop sends it between slave replies, so a write never lands inside a reply.
- **The wiring cap is checked on every offer.** Before, it was checked only when the offer changed, so a TWC whose neighbour ramped up kept an uncapped offer.

## Not ported into the rearchitecture

@ngardiner, this is a decision I made and you may disagree with it. I left three behaviours out of the single distributor rather than carry them over. Each can return as a feature if there is demand; say so and I will add it.

- **The 6 A spike workaround.** It briefly offered 16 or 21 A to get past a 6 A limit that 2017 car firmware imposed after an offer increase. I know it only from code comments, and it was probably fixed long ago. `spikeAmpsProactively` and `spikeAmpsReactively` still load and are ignored; the Debug page's "Spike Amps" row is gone.
- **Flex** (`greenEnergyFlexAmps`, a policy's `allowed_flex`, `useFlexAmpsToStartCharge`). It let a car start or keep charging when its share was up to that many amps short of the minimum. Main's default path (TeslaAPI enabled) has ignored it since #483, so only TeslaAPI-disabled installs lose it. The keys still load and are ignored.
- **Track Green dampening.** It held a drawing car at the TWC minimum for `startStopDelay` after its share crossed the minimum, to avoid start/stop churn. On main's default path a compatibility write has mostly disabled it since #483. The 60 s start/stop gates still protect the TWC relay, and `startStopDelay` still drives them.

## Evidence

- **Unit tests:** 1969 passed, 1 xfailed (main's placeholder `test_regression_template`).
- **Parity:** the 51 existing rows are unchanged in count and order. Two new rows cover vehicle-only installs: Fleet makes one $0.001 `set_charging_amps` command per hour at 16 A; BLE makes none.
- **One-day soak** on my Gen2 + BLE + TeslaMate box (`prefer_ble`). The midnight scheduled charge started 41 s after the schedule. Two real depart/return cycles were handled. There were no restarts and no control-tick failures or tracebacks.
- **Gen2 adapter follow-up** (the last two commits) was deployed on the same box afterwards: the slave linked and heartbeats ran as before, with no tracebacks, and that night's scheduled charge started 57 s after midnight over BLE (limit, then start) and ramped to 48 A.
- **Caveats.** Paid Fleet calls during the soak are inferred, not logged; logging lands in the next phase. BLE limit-lowering retries against a sleeping car were noisy (about every 5 minutes); that is fixed in the presence phase.

## Size

| | lib lines | vs main |
|---|---|---|
| `main` | 23,180 | |
| Phase 3.5 | 27,425 | +4,245 |
| this PR | 26,531 (−894) | +3,351 |

The stack is still about 14% larger than `main`. Most of the gap is the registry, providers and reconciler that `main` does not have. The presence phase follows and is expected to shrink it further.

## Known limits

- A car known only to BLE or Home Assistant gets no endpoint until the presence phase, so its rate control waits for it.
- **Gen3 is unit-tested only; I have no Gen3 hardware.** @ngardiner, the hardware request in #704 still stands.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
