# Slim Task 14 report: old-vs-new parity table with counted requests

Status: offline part DONE_WITH_CONCERNS. The live check is not run; its procedure is below.

- Branch `vehicle-model/phase3` (worktree wt-vm3), BASE e6e67d7.
- Commit bef82f0 "Pin the old-vs-new command behaviour per install type with real objects and paid-call counts".
  It adds only `tests/unit/test_command_path_parity.py` (30 tests, 935 lines, black-formatted).
- lib delta: 0 (`git diff --stat e6e67d7 -- lib/` is empty).
- Suite: `tests --ignore=tests/API --ignore=tests/integration` gives 1763 passed, 1 xfailed (BASE 1733 + 30).

## How each side was measured

**New** (`tests/unit/test_command_path_parity.py`, committed):
- Real `TWCMaster` with the reconciler on a test clock and its queues run inline.
- Real `TeslaAPI`: every HTTP request goes through `requests_mock`, and an unmatched URL answers 599 and is counted, never raised.
- Real `TeslaBLE`: only `_sendCommand_internal` (the tesla-control run) is replaced. `None` is a radio that times out, so the module's own quick retry is real.
- Real `HomeAssistant`, with its session on `requests_mock`.
- Real Gen3 controller and units.
- Real Gen2 heartbeat (`gen2_helpers.drive`) and `ChargingPoint`.

**Old**: origin/main 03d7932.
- The harness is `slim-task-14-old-harness.py` and its output is `slim-task-14-old-results.jsonl`, both in this directory.
- To re-run it: `git archive origin/main | tar -x -C old-main`, copy the harness to `old-main/tests/unit/test_parity_old.py`, then run pytest from `old-main`.
- It uses real `TeslaAPI`, real `TeslaBLE` (with `_sendCommand_internal` replaced, so main's 4-try retry and circuit breaker are real), and real `VehiclePriority`, with main's static module priorities (BLE 20, API 10, others none). Each is called the way main's `VehicleCommandQueue._DISPATCH` calls it.
- For rows 13, 14, 21 and 25 it uses main's real `TWCMaster` and `TWCSlave` heartbeat, with queued commands dispatched synchronously.

**The same scripted car on both sides** (`FleetCar`):
- `vehicles/{vin}` gives the state.
- `wake_up` brings the car online.
- `vehicle_data` returns 408 while the car is asleep.
- Commands return 408 while asleep; otherwise they follow a script of status, result and reason.
- Once woken, the car stays online.

**Shared settings and cadences:**
- `wakeDelayMins` is 0 on both sides.
- Old cadences:
  - the policy calls `applyChargeLimit` every 30 s (main's `policyCheckInterval`);
  - heartbeat start/stop calls every 10 s while the condition holds. Main asks every heartbeat (about 1 s), coalesced while one runs, so for BLE this is a lower bound;
  - TWCSlave rows: one heartbeat per second.
- New: the reconciler passes every 10 s (30 s where noted), with the same policy and heartbeat calls.

**Counting.** Paid requests are Fleet-host `vehicle_data`, `wake_up` and `/command/`. Owner-API and `vehicles/{vin}`, list, products and `live_status` requests are free. HA service calls are counted separately. Prices are vehicle_data $0.002, wake $0.02 and command $0.001. A 408'd command is counted as a request; whether Tesla bills it is unknown.

## Parity table

In the request columns, "vd/wk/cmd" means vehicle_data / wake_up / commands, followed by the free count, then BLE runs or HA calls, then $.

| # | Install / trigger | Old (origin/main) | New (phase3) | Old requests | New requests | Diff → ruling | New test |
|---|---|---|---|---|---|---|---|
| 1 | Pure Gen2, no vehicle module; heartbeat stop/start (mode 1) | VehiclePriority finds no module → False | Unaddressed fan-out finds no car; no desire, nothing planned | 0 | 0 | same | `test_pure_gen2_sets_desired_and_attempts_nothing` |
| 2 | BLE-only; policy lowers 90→70→60 | BLE wake + set each time | BLE set each time, never a wake to lower | BLE: wake 2, set 2; $0 | BLE: set 2; $0 | no wake to lower → spec #698 one limit rule (slim plan row 2, `allowWake`) | `test_ble_only_limits_never_wake_to_lower` |
| 3 | Owner token only; limit + stop | read-only API skipped; nothing | Fleet not ready, Owner declares no commands; no desire | 0 | 0 | same | `test_owner_only_never_commands` |
| 4 | Fleet-only, asleep; raise 50→80 | free check, wake, vd, cmd; then vd every 5 min while awake (main's `update_location()` on each apply of a wasAtHome car) | free check, wake, 1 vd, cmd; nothing after the stamp | 12/1/1 · 12 free · $0.045 | 1/1/1 · 1 free · $0.023 | cheaper (no per-pass paid location poll) → 12c ruling (b): departure by free position | `test_fleet_only_raise_costs_the_same` |
| 5 | BLE+Fleet, BLE radio down, car awake; lower 90→50 | BLE 3 VP attempts × main's 4-try retry (wake 168, set 8 runs, breaker) then Fleet on the **first** pass; vd every 5 min | BLE 1 try + quick retry; Fleet at 300 s, once | 12/0/1 · 12 free · BLE 176 · $0.025 | 0/0/1 · 0 free · BLE 2 · $0.001 | Fleet waits 300 s → Decision 4 / Q2 (2026-10-11 stray); BLE retry → 13a ruling | `test_ble_plus_fleet_waits_five_minutes` |
| 6 | BLE+Fleet, BLE radio down; heartbeat stop | BLE stop ×12 runs, then Fleet stop + 1 vd on the first pass | BLE 1 try + quick retry; Fleet at 60 s, once, no vd | 1/0/1 · 1 free · BLE 16 · $0.003 | 0/0/1 · 1 free · BLE 2 · $0.001 | → Decision 4 / Q2 | `test_ble_plus_fleet_stop_waits_a_minute` |
| 7 | TeslaMate+BLE; app sets 80 while we hold 50 | not re-sent (BLE flag); saved outside = 50 (user's 90 lost; 80 never recorded) | adopted: desired 80, `HeldLimit(80, None)`, nothing sent | BLE: wake 1, set 1; 0 after | BLE: set 1; 0 after | adoption → Decision 8 | `test_telemetry_limit_change_is_adopted` |
| 8 | BLE+Fleet; app starts a car we stopped | heartbeat re-stops over BLE | re-stopped once per newer reading over BLE | BLE stop 2; $0 | BLE stop 2; $0 | same | `test_app_start_is_overridden_over_ble` |
| 9 | Fleet-only, car awake; Fleet 500 on a limit | VP tries API twice per policy pass (60 s gate): 21 cmds + 7 vd per hour | 1 send + 1 blind retry at 300 s | 7/0/21 · 8 free · $0.035 | 0/0/2 · $0.002 | → Decision 5 / Q1 | `test_fleet_failure_is_retried_once` |
| 10 | Fleet+HA; Fleet 500 on a limit | as row 9; HA never (no module priority on main) | Fleet 2; HA never in one desire | 7/0/21 · HA 0 · $0.035 | 0/0/2 · HA 0 · $0.002 | → Decision 5; 12b M8 | `test_fleet_then_ha_never_in_one_desire` (+ `test_limit_reconciler.py::test_fleet_then_ha_never_in_one_pass`) |
| 11 | Gen3 two units; stop the car on unit B (A at 20 A) | `setTargetPower(0)` on B writes the shared register = full fuse → A's headroom 0 A too | `NO_INDIVIDUAL_STOP` → BLE stop to B's car; register untouched, A keeps 20 A | 0; A: 0 A | 0 HTTP; BLE stop 1 | per-unit stop → NO_INDIVIDUAL_STOP ledger carry (original Task 8) + 12b Gen3 ruling | `test_gen3_stop_routes` |
| 12 | chargeStopMode 2, BLE+Fleet; heartbeat stop | shun (`respondToSlaves=0`) at once; no vehicle command | keyed car: BLE stop, shun at 60 s; keyless: shun at once; Fleet never | 0; BLE 0 | 0 paid; keyed BLE 2 runs | BLE first → slim plan row 12, Decision 4 (disruptive = paid tier), Q4 | `test_stop_mode_2_ble_then_disruptive` |
| 13 | chargeRateControl 3, Fleet-only on a TWC; 4 A then 10 A | 4 A < minAmpsPerTWC: TWC offers 0 (mode-3 API branch unreachable below 6); 10 A: lift 32 once | car 4 A ×2 (low-amps repeat), TWC holds 6; 10 A: TWC, lift 32 once | 0/0/1 · $0.001 | 0/0/3 · $0.003 | +2 paid → layered actuators (Phase 2 Task 3 ruling / original Decision 11); lift → 12b I1 | `test_mode_3_fleet_only_below_floor` |
| 14 | chargeRateControl 1, Fleet-only; plug-in | lift 32 once per session | lift 32 once; none if the car already asks 32 | 0/0/1 · $0.001 | 0/0/1 (0 if asking 32) · $0.001 | same (≤) | `test_mode_1_lift_once_per_session` |
| 15 | Fleet token 401 on a limit | retried every pass, slot kept: 21 cmds + 7 vd | REFUSED, slot cleared, 1 cmd | 7/0/21 · $0.035 | 0/0/1 · $0.001 | → plan row 15 (A21), 13c ruling (refused-again retires) | `test_fleet_401_retires` |
| 16 | HA-only, two cars; heartbeat stops one | **nothing**: VehiclePriority never reaches HA (`calculateModulePriority` gives it none). A direct `car_api_charge` would turn off both switches (ignores the VIN) | HA `switch.turn_off` for that car only | HA 0 | HA 1 | **UNRULED** (see below) | `test_ha_only_targeted_stop` |
| 17a | ble_only + Owner/Fleet tokens; held 50, car gone (TeslaMate away) | never restored (BLE skips an applied limit; API excluded); the record stays 90/50 | restore over BLE hourly; never Fleet, never a wake | 0; BLE 0 | 0 HTTP; BLE 8 runs / 3 h | restore → plan row 17a, Decision 6 / Q3, 12c ruling (b) | `test_vanished_car_restore_is_hourly_and_free` |
| 17b | BLE+Fleet; held 50, car gone and asleep | never restored (BLE "all skipped" = success, so VP never reaches the API; `checkDeparture` likewise) | BLE hourly; Fleet without a wake after 300 s, 2 sends (408) | 0 | 0/0/2 · $0.002 | +2 paid → plan row 17b, pre-flight L4, Q1 | `test_vanished_car_restore_with_fleet_is_bounded` |
| 18 | Any; SIGTERM with a stop pending | `drain_high_priority(60)` | `reconciler.drain` runs pending stops only | — | — | same | `test_reconciler_queues.py::test_drain_runs_pending_stops_only` (no HTTP) |
| 19 | Fleet-only, car's schedule pending; heartbeat start | wake + vd each minute, then skip | hands off (TeslaMate shows pending); nothing | 12/1/0 · 25 free · $0.044 | 0 | cheaper → Decision 8 (schedule hands-off), Decision 15 (reads through providers) | `test_scheduled_charge_skips_the_start` |
| 20 | Fleet+Telemetry streaming, Fleet 408; lower a limit, 1 h | vd (408) every pass, no command | 3 commands, no wake | 60/0/0 · 30 free · $0.120 | 0/0/3 · $0.003 | → Task 10 I2 (≤4 per desire, one re-arm) | `test_streaming_telemetry_with_fleet_408_is_bounded` |
| 22 | Task 10 I2, start aspect: same, heartbeat start | vd (408) every call | 3 starts, no wake | 720/0/0 · 30 free · $1.44 | 0/0/3 · 1 free · $0.003 | → Task 10 I2 | `test_telemetry_rearm_on_a_start_is_once_per_desire` |
| 21 | Task 12b M3: mode 2, rate Fleet cannot deliver (500), 1 h | heartbeat re-queues the rate every ~21 s, forever: 172 sends | 1 send + 1 blind retry; TWC offers its max | 0/0/172 · $0.172 | 0/0/2 · $0.002 | → Decisions 5, 8 (see concerns: "main stops after about 5" is not what main does) | `test_mode_2_undeliverable_rate_pays_twice` |
| 23 | Task 10 M2: limit lowered on an asleep car, re-arm spent, then a start | sends nothing while asleep; the start wakes, reads and applies the limit first | 4 limit sends (408); the start goes without a 5th; car stays at 90 | 1/1/2 · 15 free · $0.024 | 1/1/5 · 1 free · $0.027 | start without the limit → Task 10 M2 | `test_a_spent_rearm_lets_the_start_go_without_the_limit` |
| 24 | Task 12a I1: anonymous Gen2, mode 1 stop, two Fleet cars | `car_api_charge` without a VIN: both cars, a vd each | fan-out to both; no read | 2/0/2 · 2 free · $0.006 | 0/0/2 · 2 free · $0.002 | same targets → 12a I1 | `test_anonymous_stop_fans_out_as_main` |
| 25 | Task 12b `_anonCars`: VIN-less Gen2, mode 2, car 1 unplugged, car 2 charging | `setChargeRate(vehicle=None)` → vehicles[0] = the **unplugged** car | the plugged-in car only | 0/0/1 → car 1 | 0/0/1 → car 2 | → 12b I2 / N1 (`_anonCars`) | `test_vinless_rate_goes_to_the_plugged_in_car_only` |
| 26 | Task 12c / live 2026-10-16: restart, car plugged in and asleep, no TWC VIN; Scheduled 70 (ble_only, Owner+Fleet tokens, TeslaMate) | main (held record VIN-keyed, as main's BLE and the box write it): BLE wake+limit 70, wake+amps 32, wake+start; 0 HTTP; saves 100/70. cfd0086 (the box) instead used Fleet (wake deferral, `set_charge_limit`): a 1.3.4 behaviour | BLE wake+limit 70, wake+amps 32 (the lift); no start; `HeldLimit(100, 70)` | 0 · BLE 6 | 0 · BLE 4 | limit, lift and held record same; **no start: UNRULED** (see below) | `test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit` (+ `test_limit_wiring.py` 12c tests) |
| 27 | Task 12a: mode 2 stop then start | start = `respondToSlaves=1` only | keyless: `respondToSlaves=1`; keyed: BLE stop, then wake+start (free); Fleet never | 0 | 0 paid; keyed BLE 3 | free BLE start → 12a concern-2 ruling, I2 | `test_mode_2_start_sends_no_paid_command` |
| 28 | Task 12a I3: car below minChargeLevel, heartbeat stop | not stopped, after reads | not stopped (hands off), no reads | 2/0/0 · 5 free · $0.004 | 0 | → 12a I3 | `test_a_car_below_min_charge_level_is_not_stopped` |
| 29 | Gen3 shared headroom: targets 20 A + 10 A | last writer wins: 10 A each (20 A) or 20 A each (**40 A** on a 30 A allocation, every cycle) | solver: 15 A each = 30 A in either order | 0 | 0 | sustained overshoot fixed (wiring rule) → Decision 15 (headroom solver stays), 12b Gen3 ruling | `test_gen3_shared_headroom_meets_the_budget` |
| 30 | Gen3 cloud VIN | none (`currentVIN` is "") | products + `live_status`, free; the session is named | 0 | 0 paid · 2 free | → Decision 15 (Gen3 cloud VIN stays) | `test_gen3_cloud_vin_is_free` |

Rows: 31 (1–16, 17a, 17b, 18–30), from 30 new tests plus one cross-cited test (row 18).

Every row that shows more paid calls than old says why:
- row 13 (+2): layered mode 3;
- row 17b (+2): the restore the old code never made;
- row 23 (+3 408s): M2.

Every other row is equal or cheaper.

## Unruled differences (findings)

1. **Row 16: HA-only installs.** On main, `VehiclePriority` (always loaded) never reaches Home Assistant, because `calculateModulePriority` gives it no priority. So main sends HA no start, stop or limit. Phase 3 sends targeted HA calls, which are HA-billed. Slim plan row 16 and the deleted-test audit's row-61 ruling ("main's unaddressed HA start/stop") both assume main reached HA. Measured, it does not. The confirming path is main's `registerModule` (TWCMaster.py around line 1346), which sets the priority from `calculateModulePriority`; that gives only TeslaBLE (20) and TeslaAPI (10) a priority. Nobody compared this with main because the brief's "HA stops that car" column was measured at 6a6c14e. The behaviour is the intended Phase 2 HA provider, but no ruling compares it with main. It is a new paid path on HA-only installs.
2. **Row 26: no start after the restart's limit raise.** Main's BLE start path ignores "Complete", so after the 70% write it also sent wake + charging-start over BLE (free). Phase 3 treats TeslaMate's stale "Complete" as a satisfied start and sends none. It relies on the car resuming by itself, which it did live at 00:17. Cost-neutral (BLE). The risk is that a car which does not resume on its own waits for a newer reading.

## Concerns

- **Row 21 versus the 12b M3 ruling and Decision 8.**
  - M3 says mode 2 with an undeliverable rate "behaves as on main". Decision 8 says "main stops after about 5".
  - Measured on main's real `TWCSlave`, the heartbeat re-queues a failing rate about every 21 s indefinitely (172 POSTs per hour), because `__lastAPIAmpsRepeat` resets on each send. Phase 3 pays 2.
  - The direction (fewer paid calls) is ruled by Decisions 5 and 8, but both texts describe main wrongly.
- **Row 13.** The brief's "Fleet ×2, then TWC, 2 → 2" is not main. With `minAmpsPerTWC` 6, main's mode-3 below-floor API branch is unreachable (an `elif` after the below-minimum `if`). Main offers 0 A and later lifts once: 1 paid. Phase 3 pays 3. This is ruled (layered actuators), but the brief's Phase 2 column came from 6a6c14e, not main.
- **The old side is a harness, not the box.**
  - The cadences are stated above. Old start/stop at 10 s is a lower bound for BLE runs, and the old TeslaAPI paths have their own 60 s gates.
  - The car model stays online once woken. That inflates old's per-pass `vehicle_data` in rows 4 and 5, because main keeps polling an awake car.
  - Rows 20 and 22 scale with cadence.
- **The brief's "modify this plan" step.** The table lives here; the plan file was not edited. The sdd files are not in the wt-vm3 commit.
- **Row 17b on main.** BLE's "all skipped = success" short-circuits VehiclePriority, so main never restored a held limit through the API on BLE+Fleet installs. Phase 3 does restore, and that is where its +2 paid comes from.

## Live-check procedure (deferred; the user schedules it)

Pre-approved: deploy, restart, and the rfkill window. The implementer does not run it. Before starting, record the box HEAD (expected cfd0086) and back up `/etc/twcmanager/settings.json`.

1. **Prepare.**
   - **Command policy:** the box runs `commandPolicy: ble_only` (set after the 2026-10-11 stray). Under ble_only Fleet never sends (row 17a), so run steps 3–6 and the BLE parts of step 8 on ble_only. Step 7 and the Fleet restore in step 8 need `prefer_ble`. Switch only with the user's explicit go, after backing up `/etc/twcmanager/settings.json`, and switch back before rollback.
   - **Watchdog:** pause the `~/phase3-watchdog` cron (every 10 min, 00:30–04:00) for the test window, or confirm the window falls outside it. It rolls back on a slow start, and Phase 3 can wait up to 300 s for a BLE limit.
   - **Paid-call logging:** temporarily set `logLevel` (or `debugLevel`) in `/etc/twcmanager/config.json` so INFO8 reaches the journal. Every TeslaAPI request then logs `Car API <METHOD> <path>: HTTP <status>`.
   - **Token safety:** confirm the deployed tree has no Authorization-header logging. `git -C ~/TWCManager diff` must be empty, and `grep -rn "request.headers" ~/TWCManager/lib` must find no log line.
   - **Retention:** the journal is volatile (about 9 h), so copy logs out after each step.
2. **Deploy.** Bundle `cfd0086..vehicle-model/phase3` (or the reviewed head), scp it, then run `git fetch <bundle> HEAD && git checkout --detach FETCH_HEAD`, then `sudo systemctl restart twcmanager`. Expect:
   - a boot line `Providers: ...`;
   - no `Main loop stalled` after boot.
3. **Restart with the car plugged in and asleep** (the 2026-10-16 regression).
   - Setup: the car plugged into the Gen2, asleep, limit held at 50, TeslaMate showing it at home.
   - Restart the service, then switch the policy to Scheduled 70 (or wait for its start).
   - Expect, with no other action:
     - BLE `wake` then `charging-set-limit 70`, then the BLE amps lift;
     - zero Fleet requests (`grep "Car API" | grep -c fleet` = 0);
     - `/api/getSlaveTWCs`, or the car page, showing the held limit 100/70;
     - the car starting by itself within minutes.
   - If it does not start, note it: this is unruled difference 2.
4. **Midnight schedule.** Let the Scheduled policy take over at 00:00 with SOC above the non-scheduled limit. Expect the same as step 3: one BLE limit write, no Fleet, and charging by about 00:05. Compare the timing with the cfd0086 log (limit at about 00:17 via Fleet).
5. **Policy limit change (awake car).** Expect one `setChargeLimit` via TeslaBLE and no Fleet request.
6. **App-set limit.** Set the limit in the Tesla app. Expect `charge limit set elsewhere to N; adopted` at INFO, not undone on later policy passes.
7. **rfkill window (prefer_ble, with the user's go; under ble_only expect BLE unreachable and zero Fleet for as long as the block lasts).**
   - Run `sudo rfkill block bluetooth`, then trigger a limit change by moving to a policy with another limit. Use a lower limit, so no wake is wanted.
   - Expect BLE `failed; retrying once` / unreachable for 300 s, then exactly one Fleet `POST .../command/set_charge_limit`, and no `wake_up`.
   - Hold the block for at least 6 min to confirm no second Fleet request (the one blind retry happens only after a failure).
   - Then run `sudo rfkill unblock bluetooth` and confirm BLE answers again.
8. **Depart and return.**
   - **Unplug and drive away.** Expect, once TeslaMate's position is newer than the last limit write:
     - the held limit restored over BLE when in range, otherwise hourly retries;
     - never a `wake_up`;
     - under ble_only, no Fleet request at all;
     - under prefer_ble (with the user's go), at most 2 Fleet `set_charge_limit` for the restore.
   - **Return and plug in.** Expect the policy limit to be desired again, sent over BLE.
9. **Count paid calls from the logs.** For the whole window, count `wake_up`, `vehicle_data` and `command/` among the `Car API` lines:
   ```
   journalctl -u twcmanager --since "<start>" | grep "Car API" | grep -oE "wake_up|vehicle_data|command/[a-z_]+" | sort | uniq -c
   ```
   - Price the counts at vehicle_data $0.002, wake $0.02 and command $0.001.
   - The INFO8 line does not name the token slot, and reads go to the Owner slot first (free, synced from TeslaMate). The logged path is relative (`vehicles/<VIN>/...`) and carries no host. So treat the `vehicle_data` count as an upper bound, or confirm the read slot first: while the Owner slot is usable, reads are free. `wake_up` and `command/` go only through the Fleet slot and can be priced directly.
   - Expect: no `wake_up` except for raises (with BLE up, none); `command/` only in the rfkill window (1) or restores (≤2); `vehicle_data` only for a departure check on a car TeslaMate cannot place.
   - Cross-check against `~/twc-events/events.log`.
10. **Record and roll back.** Record the findings in the PR description, then roll back:
    - `git -C ~/TWCManager checkout --detach cfd0086`;
    - `sudo cp ~/twcmanager-settings.json.bak-20261015-phase3 /etc/twcmanager/settings.json`;
    - revert the log level in `/etc/twcmanager/config.json`;
    - `sudo systemctl restart twcmanager`;
    - re-enable the watchdog cron if it was paused;
    - confirm the boot log and one heartbeat.
