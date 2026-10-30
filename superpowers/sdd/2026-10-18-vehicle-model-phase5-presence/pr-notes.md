Title: Vehicle model, phase 5: presence from events, sleeping cars left alone, the Vehicles tab

Phase 5 of the 1.4.0 vehicle-model rework; base `vehicle-model/phase4` (#710, 7432894b, on main bd5a7603). Not for self-merge. PR description draft: `.superpowers/pr-drafts/pr-phase5.md`.

Rebuilt 2026-10-21 from the final code (vehicle-model/phase5 after the second final review's fixes) and the CHANGELOG. Supersedes the earlier notes, which described the 5/20/45 reads, the 60 s unplug debounce and link grace (all gone).

## What changes for users (CHANGELOG order)

- Presence from events: Home, Away, Probably home; no paid read; probably-home counted in numCarsAtHome/minBatteryLevelAtHome; HA zone `home` without coordinates no longer places a car; car-addressed limit/start/rate wait for plugged or home; a TWC's own commands never gated.
- Home: `atHomeRadius` 1,000 ft. Home is set or moved only by a fresh position (<10 min by its GPS time) that the car actually reported (never a retained copy), at a TWC VIN read or a BLE fix, or while a TWC names the car if no home is set. Never from a first fix. Car-only installs set home by hand (one warning).
- Sleeping car left alone: BLE sleep-safe check or the Tesla API free online check before a no-wake command; asleep → held (logged once), no paid Fleet send; re-plan only on a sign of life. A cloud hold with no live feed re-checks free every 15 min at home, 30 min elsewhere (`Presence.HOME_ASLEEP_SECS`/`AWAY_ASLEEP_SECS`, shared with Phase 6's watch).
- Expected-to-charge wake gate (plugged or arriving, no stop, offer > 0, limit > battery; unknown counts as charging); start grace until each feed reported (or 60 s); restores and stops never wake.
- Policy with no limit releases; departure restore wherever the car is.
- Gen2 status change = check the car (feed since the edge → BLE ping (asleep or unknown ⇒ plugged; awake ⇒ BLE read) → Tesla API read of an awake car). Nothing can check ⇒ no unplug. Session ends at the unplug. 5/20/45 departure reads dropped.
- VIN-less attribution (one car that can be there; else unnamed); VIN read overrides; never BLE-reads a car not known awake; on the BLE worker. Unnamed TWC rate only to cars plugged in here.
- BLE scans and attribution reads on the BLE worker.
- Fleet Telemetry: charger fields mapped, typed values only, doc lists the nine required fields and minimum_delta; daily free config check warns per car (every car on the account).
- Vehicles tab: presence column; per-car pending commands; debug dump drops per-field summary.
- `/api/checkArrival`, `/api/checkDeparture` → 404.
- INFO logging: reconciler outcomes, paid Fleet requests (endpoint and price), telemetry plug/drive/geofence changes.

The CHANGELOG covers the Fleet Telemetry field mapping and the config check (two Features lines).

## Call-outs for the reviewer

- (h) Reverses the Phase 3 ruling that a VIN-less rate goes to the first car.
- A Probably-home car with a pending limit may be woken and read on the paid path, up to the budget (allowed change (b)).
- Fleet-only driveway shuffle: two paid commands (restore + re-apply, $0.002); over BLE it is free. Ruled accepted; stated in the PR.
- The VIN-less check pays one `vehicle_data` per awake Fleet candidate on a 00@0 edge (~7–10 checks/day on the box).

## Known residuals

- A guest car later on the same TWC can keep a departed idle car Home until an outside fix or drive start.
- A VIN rejected during a charge session stays rejected until the unplug.
- A car charging away from a TWC with no telemetry feed is not watched for departure (Phase 6).
- The earlier "away car whose restore failed may repeat a not-here line" residual cannot happen (an away car gets no policy limit; restores are exempt from applicability); pinned by `test_a_failing_restore_to_an_away_car_logs_no_not_here`, sentence removed from PolicyCustomization.md.

## Parity (against Phase 4, 7432894b)

- 102 rows: 42 carried, 60 new, 1 removed (`test_a_spent_rearm_lets_the_start_go_without_the_limit`, which relied on a lower never waking).
- Moved by the expected-to-charge ruling: `test_ble_only_limits_never_wake_to_lower` (wake before each lower), `test_owner_only_off_car_matches_fleet_only` (asleep scenario: wake held, no paid send), `test_ble_plus_fleet_waits_five_minutes` (wake + retry before the send), `test_telemetry_limit_change_is_adopted` (a wake run first).
- Moved by the Fleet asleep hold (user ruling 2026-10-21, option a): scenario 18 `test_fleet_only_restore_to_a_car_found_asleep_is_held` (0,0,2) → (0,0,0); row 17b `test_vanished_car_restore_with_fleet_is_bounded` moves the same way (ruled by the coordinator 2026-10-21).
- Idle 0 A row (`test_an_idle_car_at_0_a_never_departs_on_a_twc_00_even_when_the_re_apply_would_be_a_raise`): its ping answers asleep; with the held car kept on its TWC's 0 A offer at 00, its BLE limit run [80] → [] and free GETs 6 → 0; paid (0,0,0) unchanged.
- The free online check before a no-wake cloud command adds one free GET in 15 rows; no paid count moved.
- Harness: `realBle(ping=True)` now reports the car awake, as VCSEC's answer does; a scan-only answer is modelled with a callable. No count moved with it.

## Evidence

- Suite (`tests` minus API and integration): 2,270 passed, 1 xfailed.
- `black --check lib` clean; Python 3.8 syntax (one more `:=` in `Presence.checkPlug`).
- Live box (Gen2 + BLE + TeslaMate, prefer_ble) through the phase: arrival, plug-in, unplug during an awake 00 run, driveway shuffle, restarts; no tracebacks.

## Size

| | lib lines | vs main |
|---|---|---|
| `main` (bd5a7603) | 23,472 | |
| Phase 4 | 26,534 | +3,062 |
| this PR | 26,471 (−63) | +2,999 |

Target 26,140, missed by 331. The phase reached 26,198. Every increase after that is a ruled behaviour: the sleeping-car rule, BLE worker jobs, the expected-to-charge gate, the status-edge check, the FT fields and config check, and the Fleet asleep hold.
