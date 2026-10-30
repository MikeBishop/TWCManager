Show month-to-date Fleet API and Fleet Telemetry spend on the Vehicles pages

TWCManager logs every paid Fleet API request ("Tesla fleet paid request: command:set_charge_limit ($0.001)"), but nothing adds them up. Seeing whether you're comfortably inside what you're willing to spend this month meant grepping the log. This PR puts that figure on the Vehicles pages, and shows enough detail to diagnose spending that's higher than expected.

## What you see

**On the Vehicles page,** above the car table:
- `Fleet API this month: $0.31 · on pace for $0.48 by Nov 1`
- `Fleet Telemetry this month: approx. 41,800 signals, $0.28 · on pace for $0.43`, where Fleet Telemetry is enabled.
- Last month's total is added to each line when it isn't zero.

The car table also gets a "Fleet this month" column, for example `$0.28`, or `$0.28 + approx. $0.25 telemetry`.

**On each car's page,** a "Fleet spend" section shows:
- the month's total and request count;
- a table by request type (`command:set_charge_limit`, `wake_up`, `vehicle_data`, …) with count, cost, and when the last one was;
- where Fleet Telemetry is enabled, the car's approximate telemetry cost, with signal counts by field. A field with a `minimum_delta` set too fine shows up at the top.

None of it appears on an install with no Fleet API token and no Fleet Telemetry. It's informational only: no allowance, no percentage, and nothing it shows ever holds back a command or a read. The vehicle watch's own budget is unchanged.

## How it counts

- **Fleet API requests** are counted at the existing paid-request log line, so the count and the log always agree. The prices are the existing `_PAID` values.
- **Fleet Telemetry signals** are each live (not retained) `telemetry/<VIN>/v/<Field>` message, priced at Tesla's published 150,000 signals per $1. The figure is labelled "approx." because it counts what TWCManager received. Tesla bills what the car sent, which also covers anything sent while TWCManager was down and fields it doesn't subscribe to. The docs say so.
- **What the counts cover:** only requests and signals TWCManager itself sees. Another app on the same Tesla account adds to the bill without appearing here.
- **Saving:** the counts persist in `settings.json` beside the watch budget. Counting never triggers a save: telemetry can arrive several times a second, so changed counts go to disk at most every 10 minutes, and at shutdown.
- **The calendar month** is in the box's local time, and only rolls forward. A box that boots before it has the right time (a Raspberry Pi without a battery-backed clock) doesn't close the month or save an empty one.
- **`vehicle_data_cached`** is free, and a test keeps it out of the paid count. This is for a later free cached-read provider being explored separately.

## Evidence

- **Unit tests:** 2,455 passed, 1 xfailed on this branch. New tests cover:
  - counting per car and type, and per field;
  - month rollover, including a restart across the boundary and a gap of two months;
  - per-car last month;
  - pacing, with no pace shown on the month's first day;
  - malformed saved data, including a bad timestamp;
  - the clock stepping back;
  - eight threads counting at once;
  - retained MQTT copies not counting;
  - the paid-request hook, with Owner API requests not counted;
  - the save timer;
  - page rendering with and without a Fleet token or telemetry;
  - the small-amount and singular-request text.
- **Live box:** deployed alongside #734. The Vehicles page shows the Fleet API line with its pace, and the car's page shows its Fleet spend section with the request-type table. Counting starts from deployment; it doesn't backfill from the log. For a visual check, the box's settings were seeded by hand from the month's logged paid requests (`Fleet API this month: $0.006 · on pace for $0.007 by Nov 1`).

## Size

+279 lib lines: `FleetSpend` is about 150 of them, the page helpers about 75, and the hooks 15.

## Notes

- **Overlap with #734:** both touch `TWCMaster.py` and `ControlTick.py` in different places. They cherry-pick onto each other cleanly, and the combined tree passes 2,501 tests.
- **Changelog:** one line under 1.4.1 Features.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
