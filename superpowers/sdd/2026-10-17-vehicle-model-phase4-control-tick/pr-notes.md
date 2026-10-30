# Phase 4 PR notes (for the PR body)

## What changes

- **One control tick.** A 1 s `ControlTick` thread runs the one distributor, computes every Gen2 offer (`TWCSlave.offerFor`) and makes the start/stop decisions (`TWCSlave.chargeGate`). The serial loop now only talks RS-485: it receives replies, sends heartbeats and flushes queued messages.
- **The RS-485 outbox.** Any thread can call `master.sendRS485(msg)`, which queues the message. The serial loop sends queued messages between slave replies (`flushRS485`), so a write never lands in the middle of a reply. The queue is FIFO and unbounded, which is safe because every producer is rate-limited. Shutdown flushes the queue before closing the interface.
- **Token refresh off the loop (closes #690).** Tesla token refresh runs on the background thread, with at most one refresh per slot at a time. A second caller waits and shares the result, so a single-use refresh token is never spent twice. A token pasted during an in-flight refresh is refreshed on its own afterwards. **The first periodic refresh now runs 300 s after start**, and a pending vehicle-list retry is on the same timer.
- **Rate before start.** When a car's rate and a start are both due on the same pass, the reconciler sends the rate first. The order is limit, then rate, then start, and a stop never waits behind a rate. The car starts at the intended rate, which keeps overshoot down when tracking solar.
- **The EVSE scaffolding has collapsed.** With one distributor nothing switches on controller type, so `EVSEController`, `Gen2TWCs` and `VehicleEndpoints` are gone. `EVSEInstance` is now a small mixin. `Gen3TWCs` is still registered as an "EVSEController" module named "Gen3TWCs".
- **Comments.** Comments across the stack now explain why the code is the way it is; history stays in commit messages. A test keeps phase names and issue or PR numbers out of lib comments.

## Behaviour changes

- **TeslaAPI-disabled installs use the distributor** (`test_teslaapi_disabled_install_uses_the_one_distributor`). With `vehicle.TeslaAPI.enabled: false`, an install moves from the old per-slave "share by cars charging" to the distributor's water-fill. Every other install already ran the water-fill, because TeslaAPI is enabled by default.
- **Up to one tick of lag.** A Gen2 target can lag by up to one tick (~1 s). The distributor now runs once a second rather than once per heartbeat round (≈ N × 1.1 s). Start/stop gates also run every tick. They write desired state only, so the paid request counts are unchanged.
- **The wiring cap is checked on every offer** (`test_wiring_cap_is_rechecked_when_others_draw_more`). Before, it was checked only when the offer changed. Then if another TWC ramped up, this TWC's offer stayed uncapped, which is a sustained overshoot of the derated limit.
- **Gen3-only installs are controlled** (`test_a_gen3_only_install_is_controlled`). Before, the distributor ran only when a Gen2 slave was known. Now a Gen3-only install is throttled through its fake-Neurio headroom.
  - Configure `controller.Gen3TWCs` and set `interface.RS485.enabled: false` (`Dummy` and `TCP` are off by default). With no interface module loaded the serial loop idles and shutdown skips the bus. Left enabled, RS-485 with no `port` logs an error and unloads itself, but the shipped config sets `port: /dev/ttyUSB0`, and a configured port with no adapter behind it aborts startup.
- **Vehicle-only installs are controlled** (`test_a_vehicle_only_install_is_controlled`).
  - BLE-only: no paid calls.
  - Fleet-only: in the parity row, one $0.001 `set_charging_amps` per hour at 16 A.
  - Configure the vehicle module(s) and set `interface.RS485.enabled: false`, as for (g). This is also what makes the cars rateable: an install with an interface loaded and no slave linked is treated as blind to its cars, so a configured but absent TWC never turns home cars into Fleet-rated ones.
  - A car that only BLE or Home Assistant knows gets no endpoint yet. Its rate control waits for the presence work.

## Not ported into the rearchitecture

Each of these can come back as a feature if anyone needs it.

- **The 6 A spike workaround** (`test_spike_settings_are_ignored`). It briefly offered 16 or 21 A to get past a car-side 6 A limit that 2017 car firmware imposed after an offer increase. It is known only from code comments and was probably fixed long ago. `spikeAmpsProactively` and `spikeAmpsReactively` still load without error but are ignored, and the Debug page's "Spike Amps" row is gone. *The maintainer may disagree; please say so.*
- **Flex** (`test_flex_settings_are_read_but_ignored`, `test_a_policy_with_allowed_flex_evaluates_without_error`). `greenEnergyFlexAmps`, or a policy's `allowed_flex`, let a car start or keep charging when its share was up to that many amps short of the minimum (`useFlexAmpsToStartCharge` covered starting). Main's default path (TeslaAPI enabled) has ignored it since #483, so only TeslaAPI-disabled installs lose it. The keys still load and are ignored.
- **Track Green dampening** (`test_green_policy_does_not_hold_a_car_below_the_minimum`). It held a drawing car at the TWC minimum for `startStopDelay` after its share crossed the minimum, to avoid start/stop churn. On main's default path a compatibility write has mostly disabled it since #483. The 60 s start/stop gates still protect the TWC relay, and `startStopDelay` still drives them.

## Size

lib `.py` lines (`git ls-files lib | grep '\.py$' | xargs cat | wc -l`):

| | Lines |
|---|---|
| origin/main | 23,180 |
| Phase 3.5 (1029809b) | 27,425 |
| Phase 4 | 26,490 (−935) |

Phase 4 is 3,270 lines larger than main. Code is ≈ 2,820 of that and comments ≈ 330. Most of the remaining gap is the vehicle-model layers (registry, providers, reconciler) that main does not have. The presence port (Phase 5) is expected to shrink it further.

Per task (actual against plan): T1 −48 (−50), T2 +39 (+22), T3 −33 (−58), T4 −293 (−320), T4b +2 (none planned), T5 −66 (−88), T6 −576 (−315).

## Live check

Script and procedure: `live-check.sh` in the same directory (not run yet).
