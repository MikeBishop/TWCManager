Vehicle model, phase 6: a vehicle watch for cars no TWC or live feed covers

Phase 6 of the vehicle-model rework, the last in the spec; base `vehicle-model/phase5` (#725); review after Phase 5. The stack targets **1.4.1**: `main` shipped 1.4.0 without it.

## Where this sits

Stack: Phases 1, 2, 3 and 3.5 (#703–#706) are merged → Phase 4 #710 → Phase 5 #725 → **Phase 6 (this PR)**.

Phase 5 decides presence from events and polls nothing, and says so: a car charging on a mobile connector (UMC) or another EVSE, with no TWC naming it and no telemetry feed, is never noticed arriving, plugging in, finishing or leaving. This phase closes that gap.

## What changes for users

- **A watch for every car that no TWC names and no live telemetry feed (TeslaMate, Fleet Telemetry) covers.** It notices arrival, plug-in, charge start, charge end and departure, so such a car gets a fair share of power and a car that is done or gone stops being counted. It never wakes a car and never keeps one awake: an asleep car is not charging and not moving, and the watch's one routine question is the free sleep-state check. A car with no VIN is not watched. When a feed goes down the watch picks the car up at its next due check.
- **Three rings, cheapest first.** Passive listening (a Bluetooth scan, a step in the house's consumption, what TWCs and feeds report); free status checks on a clock (home asleep 15 min, home awake or charging 4 min, away asleep 30 min, away awake 5 min); and charge reads only on a change (arrival, wake, plug-in, charge-port door opening) and, while a car charges at home, every 5 minutes over BLE or the Owner API, or every 15 minutes on the Fleet API while a policy reads its battery level. After a wake-triggered read an awake car at home is not read again for 20 minutes (`sleepCourtesySecs`).
- **BLE ping and door.** BLE's sleep-safe check needs no pairing and works for every car in range. While the car is awake it also reports the charge-port door: a closed door counts as unplugged, and an open one on an awake car at home is confirmed by a charge read. An asleep car draws nothing; asleep after Charging, it has finished.
- **One shared range scan, with back-off.** One `bluetoothctl` scan listens for every car at once. Two missed checks in a row run a scan; a scan that also misses marks the car out of range. A lost car is scanned every 150 s for the `awayAsleepSecs` after its last sign of life, then every `awayAsleepSecs`. A BLE install makes no cloud status checks, except for a command held for a sleeping car.
- **The API-only rule.** A watched car that only the Tesla API can see (no BLE module, or its radio can't work: no controller, powered off or blocked, `bluetoothd` silent) is polled for sleep state, read on the asleep-to-awake edge (anywhere), and read again while awake once its last position fix is 20 minutes old, so a parked car is read about once per wake and a departure while awake is seen within a window. After a fix away from home, nothing runs for that car until it could be back: its straight-line distance home at 120 km/h (75 mph, `returnKph`), never less than 5 minutes. Paid charging reads on the Fleet API run only while a policy reads the battery level; the Owner API is free and keeps the 5-minute cadence. The Fleet API cost is about one $0.002 read per wake at home, about $0.01 a day for a car with a few trips. Fleet Telemetry is still the cheaper option for Fleet-only users, and the docs say so, but it is not required.
- **A monthly budget for paid reads.** `watch.monthlyBudgetUSD` ($3 by default, saved across restarts, so a restart doesn't refill the month) covers the watch's own Fleet reads. It refills steadily and holds at most one day's worth; a read caused by a change may spend all of it and a routine charging read leaves half a day in reserve. When it runs out cloud reads stop and the free checks continue; the log says once when a change-caused read is refused and once when it is available again. Commands, and the reads made before them, don't draw from it. Free reads are never held back.
- **UMC monitoring.** With a consumption meter configured, a step in the house's load that nothing known explains reads the candidate cars at once: a rise asks about awake or unknown-state cars not charging, a fall about cars known to be charging. A rise reads a car at most once per `sleepCourtesySecs`, so a cycling load never keeps a car awake; a car known to be away is never asked. A car that starts charging on a mobile connector is then in the fair share within about a minute. A power start reads cars at home only.
- **The watch replaces the polling it overlapped.** The Tesla API's deferral ladder (300/1800/3600 s of paid `vehicle_data`) and the half-hourly battery refresh of cars at home are removed; a read stays fresh for 5 minutes for every caller. `cloudUpdateInterval` no longer sets how often cars are read (the Powerwall module still uses it as its cache time). For a watched car, the watch's status checks serve a held command's sleep check.
- **Docker scan readiness.** A container can run the range scan through `nsenter` into the host's network namespace; it uses the `CAP_SYS_PTRACE` the compose file has granted since 1.4.0. When no scan can run (no controller, adapter off or blocked, `bluetoothd` not answering) the log and the Vehicles page say why, and a car with a Tesla API connection falls back to the API-only rule.
- **The charger load counts every charger the meter sees.** With `subtractChargerLoad`, the load taken out of the house's consumption now includes Gen3 Wall Connectors and watched cars charging at home on other chargers, not only Gen2 TWCs. Before, a green policy counted such a car's own draw as house load and shrank its offer; Gen3 had this in 1.4.0 too.
- **The meter is read whenever the consumption step needs it.** EMS sources were polled only under a green policy, `policy.alwaysPollEMS` or `maxAmpsAllowedFromGrid`, so under any other policy the step never ran. While `emsTrigger` is on, an energy source is configured and a car is watched, the watch now asks for the poll on every policy pass.
- **The offered total counts a car's own rate.** The status header added up only what each Gen2 TWC is offered, so an install whose car charges on another charger showed 0 A offered. It now includes the amps offered to each charging point with no TWC in it.
- **The Vehicles-page watch line.** Each car shows whether it is watched (and if not, why), the last check and its answer, when the next is due, and the budget, for example "Watched: online ... via ble, next in 4 min".
- **Settings.** An optional top-level `watch` block in `config.json`: `enabled`, the cadences above, `scanAwaySecs`, `sleepCourtesySecs`, `returnKph`, `monthlyBudgetUSD`, `emsTrigger`, `emsNoiseWatts`. `watch.enabled: false` turns the whole watch off. All defaults are documented in Settings.md, with the rings, the API-only rule and the budget.

## Evidence

- **Unit tests:** 2,458 passed, 1 xfailed (main's placeholder `test_regression_template`). The phase adds tests for the budget (including persistence and an empty bucket), the cadences, the consumption step (a dryer step with no awake watched car triggers nothing), the API-only rule, the scan back-off and Docker readiness.
- **Parity:** the command-path parity rows keep their paid counts; the phase moves none.
- **Live box, joint soak** (Gen2 + BLE + TeslaMate, `prefer_ble`, 2026-10-21 to 10-22): departure and arrival were seen, and the feed-down case was tested by turning TeslaMate telemetry off, after which the watch took the car over ("Watched: online ... via ble"). The soak found the overnight miss under a 6 A sleep pilot. The fix is in Phase 2 (a car is capped by its own charging maximum, not the charger's pilot); this phase carries a regression test that replays that night through the full stack.
- **Live box, API-only soak, 2026-10-22 to 10-26** (BLE off, TeslaMate telemetry off, Owner + Fleet): no tracebacks or warnings and no restarts over the last three days; departures seen (one seen 24 s after the unplug; the cloud lagged an unplug by 7 to 24 minutes on two other occasions, see known limits); Fleet spend about $0.005 a day in commands (five commands in the reviewed window, no wakes, no blind retries); and **zero Fleet Data requests on Tesla's dashboard**, since the free online check isn't counted. The soak found the three Phase 5 follow-ups (the two-minute recheck, the wake poll, no blind retry while the TWC delivers current) and the home-learning rule, all now folded into Phase 5.
- **Not soaked:** the branches as restacked onto `main` (after #704 merged) were not soaked; the maintainer is merging actively, so I went straight to review. Every phase tip passes the full suite, and the parity file is byte-identical to the soaked build's.

## Size

| | lib lines | vs this base |
|---|---|---|
| `main` (686b36ec, Phases 1–3.5 merged) | 27,546 | |
| Phase 5 | 26,650 | −896 vs `main` |
| this PR | 27,233 (+583) | −313 vs `main` |

The phase was meant to end at or below where it started, and it does not: it adds +583 lines. It removes the deferral ladder and the battery refresh, but the watch, the budget, the consumption step and the Docker scan readiness are new. The API-only rule replaced three away-handling paths and their state, which kept `Watch.py` to about 400 lines; the rest is the feature. The stack as a whole is still smaller than `main`.

## Known limits

- **Fleet-only driveway shuffle costs paid commands.** A Fleet-only car that backs out of the radius and returns gets its restore and re-apply as paid Fleet commands ($0.001 each; BLE does the same free).
- **API-only departures are usually seen at the next 15-minute status check.** The cloud can lag an unplug past Phase 5's two-minute recheck.
- **A Fleet-only stop can be skipped** when the car's last reading says "Stopped" (pre-existing).
- **A BLE→Owner amps fallback can wait 15–30 minutes**, on a BLE install whose radio dropped.
- A Fleet-only car with no battery policy that unplugs and drives off while charging is caught only when it sleeps or next wakes.
- A cloud read answered from a deferral still spends a budget token (this under-spends the month, never over).
- **Gen3 is unit-tested only; I have no Gen3 hardware.**

🤖 Generated with [Claude Code](https://claude.com/claude-code)
