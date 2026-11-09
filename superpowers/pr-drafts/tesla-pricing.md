Title: Add a Tesla pricing module that reads the Powerwall's rate plan

The Powerwall time-of-use PR (#744) noted that the tariff it reads also carries prices, and deferred exposing them until the Pricing module type settled. Now that it has (7767998f, 57a43de1), this adds `TeslaPricing`: a Pricing module whose prices come from the rate plan set in the Tesla app.

## What it does

- `modules.TeslaPricing.importPrice` / `exportPrice` from the tariff's `energy_charges` and `sell_tariff`, keyed by season and period. `ALL` rates apply to every period, so a flat plan works too.
- The tariff comes from `TeslaPowerwall2`'s existing cached `site_info` / `tariff_rate` read, so there are no new requests and no paid reads.
- A rate plan is a fixed schedule, so the module offers `Forecasting`: an exact 48-hour forecast at `/api/getPricingForecast`, `forecastMinPrice` / `forecastMaxPrice`, and `cheapWindowActive` with the same `cheapWindow` config as Amber. Slots step in UTC and are priced by the site's wall clock (or the host's, with only an Owner API token), so DST changes are handled.
- A price the plan doesn't give is left absent, not reported as 0, so `importPrice lt X` doesn't match on an unknown price.

## Changes to existing code

- **Policy (bugfix, in 1.4.0):** a `gt`/`gte`/`lt`/`lte` condition on a `modules.*` value whose module isn't loaded compared the unresolved macro text with a number, raised `TypeError`, and abandoned the whole policy pass for that cycle. It now simply doesn't match. This is what the "price rules fail safe" paragraph in PolicyCustomization.md already promised.
- **Amber (@ngardiner, please check):**
  - The cheapest-window search, min/max and forecast serialisation move to `Pricing/Forecast.py` so both modules share them. Amber's results are unchanged for its contiguous series.
  - Bugfix: once inside the cheapest window, the next forecast refresh searched again from "now", found a later window (or tomorrow's) and ended charging early. A window that is under way is now kept until it ends. On a fixed plan the effect was large: the documented 4-hour example charged for 1.5 hours.
  - The search now skips windows containing a missing slot, and compares slots as instants so a window can span a DST change.
  - A fractional `cheapWindow.hours` is honoured rather than rounded down.

## Commits

1. Don't abort policy evaluation on an unresolved numeric comparison
2. Share the cheapest-window search between pricing modules
3. Hold the cheapest window once it starts
4. Resolve the current price from a Powerwall tariff
5. Add a Tesla pricing module that reads the Powerwall's rate plan

## Testing

- Unit tests for the price lookup (season wrap, critical-peak day, `ALL` rates, flat plan, sell tariff, malformed input), the shared forecast helpers (gaps, ties, DST, latching), the module (unknown prices, no Powerwall module, currency, forecast across DST, host clock, window held for its whole length) and the policy fix. Full unit suite: 2664 passed.
- Zone-dependent forecast tests skip on Python 3.8 (no `zoneinfo`); price tests run there on the host clock, checked with a simulated no-`zoneinfo` run.
- Tariff shape checked against the live Duke site's `site_info` and Tesla's example `PGE-EV2-A.json`.

## Known limits (left for follow-up)

- The forecast cache can be up to an hour stale just after clocks fall back.
- `cheapWindow.hours` between 0 and 0.5 errors (Amber did already).
- `currency` shows `$` until the plan has been read.
- `cheapWindow.endHour` bounds where a window starts, not where it ends; the docs (inherited from Amber's) say "may run to".

🤖 Generated with [Claude Code](https://claude.com/claude-code)
