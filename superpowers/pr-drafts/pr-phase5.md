Vehicle model, phase 5: presence from events, sleeping cars left alone, the Vehicles tab

Phase 5 of the vehicle-model rework (the spec runs to Phase 6); base `vehicle-model/phase4` (#710); review after Phase 4. The stack now targets **1.4.1**: `main` shipped 1.4.0 without it.

## Where this sits

Stack: Phases 1, 2, 3 and 3.5 (#703–#706) are merged → Phase 4 #710 → **Phase 5 (this PR)** → Phase 6 #726, the vehicle watch for cars on chargers TWCManager doesn't control (base `vehicle-model/phase5`).

## What changes for users

- **Presence from events, with no paid read.** A car is Home, Away or Probably home, decided fresh from plug-ins, unplugs, positions (from any source, TeslaMate and Fleet Telemetry included), drive starts and BLE contact; the newest evidence wins. Probably-home cars count in `numCarsAtHome` and `minBatteryLevelAtHome`. A Home Assistant zone state of `home` with no coordinates no longer places a car. A charge limit, start or rate for a car waits until it is plugged in or confirmed home; a TWC's own commands (start, stop, amps) are never held back by where a car is.
- **Home is learned only from a fresh position the car reported.** `atHomeRadius` defaults to 1,000 ft (was 10,560); a configured value wins. Home is set or moved only from a position under 10 minutes old, by the fix's own GPS time, when a TWC reads the car's VIN or the position arrives over BLE (and, with no home set yet, while a TWC is naming the car). A position that did not come over BLE must also have been read at or after the car reached its TWC (its plug-in or the VIN read), so a read from before the drive home never moves home; once home is set, only BLE or the Settings page moves it. A feed's retained copy, redelivered at a restart or reconnect, never counts. It is never seeded from a car's first position, and the paid `update_location` read is gone. A car-only install with no TWC and no BLE must set home on the Settings page; one warning says so, and until then its cars get no limit.
- **A sleeping car is left alone.** Before a command that may not wake the car, TWCManager checks it without waking it: BLE's sleep-safe check, or the Tesla API's free online check. If the car is asleep the command waits (logged once), so no paid Fleet API command goes to a car known asleep. Nothing is re-run until a sign of life (a newer awake state, a plug or unplug, a drive start or end, current drawn, a successful wake). For a car no live telemetry feed reports on, the free online check looks again every 15 minutes at home and every 30 minutes elsewhere.
- **A car is woken only when it is expected to charge** once everything wanted is applied: plugged in or arriving, no stop wanted, its TWC or charger offered power, and its limit above its battery (an unknown limit or battery counts as charging). After a start, no wake until TeslaMate or Fleet Telemetry has reported once (or 60 s). A car expected to stay idle gets changes only when it is awake anyway. Departure restores and stops never wake.
- **A policy with no limit releases the car** to its own limit, applied like any limit; a departing car's original limit is restored wherever it is.
- **Fixes from the box soak, folded into the commits above.** A plug-in that finds no candidate car starts a Bluetooth scan for it. A plugged-in car is no longer treated as driving. A pilot cap fix (in Phase 2, #704) stops a car read while its TWC held the 6 A sleep pilot from being capped at 6 A, which had left it uncharged overnight.
- **A wake that answers offline, asleep or waking is polled.** The car connects seconds later, so the free online check runs every 5 s for up to 45 s, then the command is sent. Only a car still not online after that waits 30 minutes for the next wake.
- **Fresh current at a car's TWC counts as charging for a start** (a reading under 30 s old), so a start is not blind-retried while the TWC is delivering. A held cloud command is rechecked with the free online check alone and logs once.
- **A Gen2 status change means "check the car".** A 00, the TWC's max amps dropping to 0 during one, or a change between plugged and not makes TWCManager check the car about 20 s later, once per event and never waking it. The order is:
  1. A live feed's report since the change.
  2. Else BLE's sleep-safe check: a sleeping car, or one the check cannot tell is awake, is still plugged in; an awake one gets a BLE charge read.
  3. Else the Tesla API, which reads only a car its free online check finds awake.

  A check that cannot tell runs once more two minutes after the change, as the cloud can lag an unplug's wake. A car nothing can check is never unplugged by the TWC alone. A Gen2 unplug ends its plug session (before: 5 s after charging stopped). The 5, 20 and 45 minute departure reads after a TWC's power drops are gone.
- **A VIN-less plug-in is matched to the one car that can be there** (plugged in just now, BLE-read at that pilot and draw, or BLE-reached) and left unnamed when several could be. On a Gen2 that reads VINs, the VIN read replaces the match. The match never BLE-reads a car not known to be awake. It runs on the BLE worker, and a Gen3's vitals never read BLE. An unnamed TWC's rate goes only to cars plugged in here, no longer to the first car.
- **BLE work moves to the BLE worker.** Range scans and attribution reads run there, not on the background-task thread.
- **Fleet Telemetry.** The module maps the charger fields (`ChargeAmps`, `ChargerVoltage`, `ChargerPhases`, `ChargeCurrentRequest`, the home-charger narrowing fields) and reads the typed values Tesla sends. The doc lists the nine fields presence needs, with suggested `minimum_delta`s. With a Fleet token, TWCManager reads each car's `fleet_telemetry_config` (free, never wakes) a few minutes after start and daily, and warns once, on the log and the car's page, when a config is missing, unapplied or lacks a needed field. The check covers every car on the account, so a car you don't stream warns too.
- **The Vehicles tab.** The Vehicles page shows each car's presence. A vehicle's page lists its pending commands, one line each: in flight, or why not sent. The per-field summary is gone from the debug dump.
- **`/api/checkArrival` and `/api/checkDeparture` answer 404.** Presence no longer needs the hints.
- **Logging.** INFO lines for each reconciler outcome, each paid Fleet request (endpoint and price, never the URL, VIN or token), and each telemetry change of plug state, drive state or geofence.

## Evidence

- **Unit tests:** 2,337 passed, 1 xfailed (main's placeholder `test_regression_template`).
- **Parity:** the command-path parity rows pass at this tip. Every moved count follows a ruling made during the phase:
  - The expected-to-charge wake rule moved four carried rows: a lower to a car that will charge now wakes first (BLE: an extra `wake` run; Owner-only asleep: the wake is held, so no paid send). It also removed the spent-re-arm row, which relied on a lower never waking.
  - The Fleet asleep hold moved the two rows that restore a limit to an asleep Fleet-only car from `(0, 0, 2)` to `(0, 0, 0)`. The free online check finds the car asleep, so the restore waits.
  - The free online check before a no-wake cloud command adds one free `vehicles/{vin}` GET in 15 rows. Free GETs aren't billed, and no paid count moved with them.
  - The idle 0 A row (a car on a TWC offering nothing, a raise pending) now has its BLE ping answer asleep, as the car is, so the raise neither wakes it nor reaches it over BLE. A new row checks the other side: with 32 A to share, the same sleeping car at 00 is woken over BLE for the raise. Paid stays `(0, 0, 0)` in both.
  - The steady-00 row gains one free BLE ping, from the two-minute recheck of an unanswered plug check. Paid is unchanged.
  - The harness's BLE ping stub now answers as VCSEC does for an awake car. No row's count moved with it.
- **Live box** (Gen2 + BLE + TeslaMate, `prefer_ble`): the phase was deployed and soaked after each change, covering arrival, plug-in, unplug during an awake 00 run, the driveway shuffle and restarts. The soak found the fixes folded in above (the sleep-pilot overnight miss, the scan on a candidate-less plug-in, the wake poll, the recheck). It was followed by an **API-only soak, 2026-10-22 to 10-26** (BLE off, TeslaMate telemetry off, Owner + Fleet): no tracebacks or warnings, departures seen, Fleet spend about $0.005 a day in commands (five commands in the reviewed window, no wakes, no blind retries), and zero Fleet Data requests on Tesla's dashboard (the free online check isn't counted).
- **Not soaked:** the branches as restacked onto `main` (after #704 merged) were not soaked; the maintainer is merging actively, so I went straight to review. Every phase tip passes the full suite, and the parity file is byte-identical to the soaked build's.

## Size

| | lib lines | vs this base |
|---|---|---|
| `main` (686b36ec, Phases 1–3.5 merged) | 27,546 | |
| Phase 4 | 26,637 | −909 vs `main` |
| this PR | 26,650 (+13) | −896 vs `main` |

The phase adds 13 lines over Phase 4. Its target was to shrink; it misses it. Each increase is a behaviour ruled during the phase: the sleeping-car rule, BLE worker jobs, the expected-to-charge gate, the status-edge check, the Fleet Telemetry fields and config check, the Fleet asleep hold, and the late soak fixes. Getting under Phase 4 would mean cutting one of them. The stack as a whole is smaller than `main`, because the registry and reconciler replace more code than they add.

## Known limits

- **Fleet-only driveway shuffle: two paid commands.** A Fleet-only car (no BLE) that backs out of the radius and returns gets its restore and the re-apply as two paid Fleet commands ($0.002). Over BLE the same shuffle is free.
- A guest car later on the same TWC can keep a car that left idle counted as home until that car reports a position outside the radius or starts driving.
- A VIN a TWC rejected during a charge session stays rejected until the unplug.
- A car charging away from a TWC, with no telemetry feed, is not watched for its departure; Phase 6's vehicle watch (#726) covers it.
- **A Fleet-only stop can be skipped** when the car's last reading says "Stopped" (pre-existing).
- A BLE→Owner amps fallback can wait 15–30 minutes, on a BLE install whose radio dropped.
- Where the cloud lags an unplug beyond the two-minute recheck, the unplug is seen at the next status check; API-only departures are usually seen at the next 15-minute check.
- A Probably-home car with a pending limit may be woken and read on the paid path, up to the paid budget.
- **Gen3 is unit-tested only; I have no Gen3 hardware.**

🤖 Generated with [Claude Code](https://claude.com/claude-code)
