# Month-to-date Fleet spend on the Vehicles pages: design

## Intent

An installer using the Tesla Fleet API (paid per request) or Fleet Telemetry (paid per streamed signal) should be able to see at a glance whether TWCManager is keeping them comfortably inside what they're willing to spend this month. When they aren't, the page should show enough to diagnose why. Today the only record is one INFO log line per paid request ("Tesla fleet paid request: command:set_charge_limit ($0.001)"). The watch budget on the Vehicles page covers only the vehicle watch's own reads, and it appears only for cars the watch is watching.

## Goals

- **Vehicles overview, as the user chose:**
  - One line above the car table: "Fleet API this month: $X · on pace for $Y by <first of next month>".
  - Where Fleet Telemetry is enabled, a second line: "Fleet Telemetry this month: approx. N signals, $X · on pace for $Y".
  - A per-car column, "Fleet this month": the car's Fleet API spend, plus "approx. $Z telemetry" where telemetry is enabled.
- **A car's own page:**
  - "Fleet API this month: $X in N requests".
  - A table by request type (e.g. `command:set_charge_limit`, `command:set_charging_amps`, `wake_up`, `vehicle_data`), with count, cost, and when the last one happened.
  - Where telemetry is enabled, "Fleet Telemetry this month: approx. N signals, $X", with a table of signal counts by field. Seeing which field drives the count points at a `minimum_delta` set too fine.
- **Last month:** at the start of a month, the overview and each car's page also show last month's final total, if it was non-zero (user).
- **Survives restarts:** the counts persist across restarts, the way the watch budget already does.

## Non-goals

- No allowance, percentage or limit. The user knows what they're comfortable spending (user). It is informational only: it never holds back a command. The watch's own budget (`watch.monthlyBudgetUSD`) still limits the watch's paid reads, unchanged.
- No per-request cause ("schedule start", "raised limit"). Type and time are enough, and the log has the rest (user).
- No history beyond last month.
- No exact bill. TWCManager reports only what it sees.

## Anti-goals

- **A number that looks authoritative but isn't.** Telemetry counts are labelled "approx." on the page (user). The docs explain that TWCManager counts what it received, while Tesla bills what the car sent, and that requests or signals from another app on the same account don't appear. The page itself carries no "while running" caveat, because TWCManager is expected to run full-time (user).
- **Leaking a VIN or URL into logs or pages.** Request types are recorded exactly as the existing log line names them.

## How (decided)

- **Counting Fleet API requests.** At the existing paid-request site, `TeslaAPI` around line 346 on `main`: where the code checks `_PAID_PATH` and that the slot is the Fleet slot, and logs the paid line, also record:
  - the request type (`kind`) and its price (`_PAID[...]`);
  - the car the request is for.
- **Counting telemetry.** In `FleetTelemetryMQTT`'s message handler, count each live (non-retained) per-field message (`telemetry/<VIN>/v/<Field>`) per car and per field. Retained redeliveries are already distinguished there and must not count.
- **The telemetry price** is one constant beside `_PAID`, checked against Tesla's published Fleet Telemetry pricing before building. Shown cost = signals × price.
- **Month boundary:** the calendar month in the box's local time. At the boundary, the month's totals become "last month", and the per-type and per-field detail is dropped.
- **"On pace for":** spend so far ÷ elapsed fraction of the month × 1. Hide it during the month's first day, when the fraction is too small to mean anything.
- **Persistence:** stored in `settings.json` beside `watchBudget`. *(My call.)* Settings saves are event-driven (a queued `saveSettings` task), so counting never triggers a save itself. The counts live in memory and go out with any save, plus one queued save at most every 10 minutes while they have changed, and at shutdown. A crash loses at most 10 minutes of counts.
- **When things show.** *(My call.)*
  - The Fleet API line and the per-car column appear only when a Fleet API token is configured. They show $0.00 when nothing has been spent, which is reassurance in itself.
  - The telemetry line appears only when the Fleet Telemetry module is enabled (a global setting). It shows "approx. 0 signals" until the first arrives. A car's telemetry figures appear only for cars that have sent signals.
  - Without Fleet configured, neither line nor the column appears.
- **Every paid request belongs to a car.** Only `vehicle_data`, `wake_up` and `command/*` are paid (`_PAID_PATH`), and each is a per-car path. Account listings and the energy site's `live_status` are free. A paid call that reaches the counter without a registry car still counts toward the overview total; the overview shows no separate line for it.

## Left to the builder

- The data structure and module: a small `FleetSpend` class, like `WatchBudget`, is the obvious shape.
- Exact markup and styling, matching the existing Vehicles templates.
- Whether HTTPControl also exposes the totals in a JSON API (nice to have, not required).
- Tests: counting and pricing, month rollover (including a restart across the boundary), retained messages excluded, persistence round-trip, and rendering with and without telemetry.
- Docs: Vehicle_TeslaAPI.md (Fleet section) and Vehicle_FleetTelemetryMQTT.md, each saying what is counted and why the bill can differ. Follow the user-facing docs rules: written for installers, "EVSE/charging station", no internals.

## Constraints

- Python 3.8. The project treats lib growth as a red flag, so keep it small.
- Comments say why the code is the way it is.
- A CHANGELOG line under the upcoming release's Features, since this is a new user-visible feature.
