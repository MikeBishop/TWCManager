# Prices from the Powerwall tariff — design

Date: 2026-11-04. Size: project (new Pricing module, a shared forecast helper
moved out of Amber, docs, tests).

## Intent

The Powerwall time-of-use PR (`touPeriod`) noted that the tariff it reads also
carries prices, and deferred exposing them until Nathan's Pricing module type
settled the shape. That type has landed (`7767998f`, `57a43de1`): Pricing
modules report `importPrice` / `exportPrice` / `currency`, and a module with the
`Forecasting` capability also offers a price forecast, `forecastMinPrice` /
`forecastMaxPrice` and a configurable cheapest window (`cheapWindowActive`).

Powerwall owners already keep their rate plan in the Tesla app. This work makes
that plan a Pricing source, so they get everything the Pricing type offers
without Amber or a hand-typed Static price:

- price-threshold policies written as `modules.<Module>.importPrice` work the
  same whether prices come from Amber, Static or the Powerwall tariff;
- `/api/getPricing` and `/api/getPricingForecast` show the tariff's prices;
- cheapest-window charging works from the tariff. A rate plan is a fixed
  schedule, so the forecast is exact for any horizon and needs no network
  beyond the tariff read `touPeriod` already makes.

## Goals

- A Pricing module that reports the current import and export price from the
  Powerwall's tariff, with the tariff's currency.
- It offers `Forecasting`: a forecast covering the same horizon Amber's does,
  `forecastMinPrice` / `forecastMaxPrice`, and `cheapWindowActive` /
  `cheapWindowStart` from a `cheapWindow` config identical to Amber's.
- A critical-peak day written into the tariff (as for `touPeriod`) shows up in
  price and forecast within one tariff refresh.

## Non-goals

- Demand charges and daily charges. They are not per-kWh prices.
- Writing the tariff.
- Prices for sites without a Powerwall, or from the local gateway API (it does
  not expose the tariff).
- Changing the policy engine or the macro language.

## Anti-goals

- A second fetch of the tariff, or any paid Fleet read. Prices come from the
  same cached `site_info` read `touPeriod` uses.
- A missing tariff or a missing rate that looks like a price of 0. A
  `importPrice < X` policy must not start charging because a price is unknown.
- Copying Amber's cheapest-window code. Net lib lines should grow by the new
  module's own logic only (see [[rearchitecture-must-shrink]]).
- Cutting what `touPeriod` does today, or its behaviour on Python 3.8.

## Data (verified against the live site, 2026-11-04)

`site_info.tariff_content_v2` (Fleet) or `tariff_rate` (Owner) — the same
object `TeslaPowerwall2.getTariff()` already returns — has, besides `seasons`:

```
"currency": "USD",
"energy_charges": {
  "ALL":    {"rates": {"ALL": 0}},
  "Summer": {"rates": {"OFF_PEAK": 0.158036, "PARTIAL_PEAK": 0.187444,
                       "SUPER_OFF_PEAK": 0.146273}},
  "Holiday 2027-05-31": {"rates": {"OFF_PEAK": 0.158036, "SUPER_OFF_PEAK": 0.146273}},
  ...
},
"sell_tariff": {"energy_charges": { same shape }, "seasons": {...}, ...},
"demand_charges": {...}, "daily_charges": [...]
```

- Rates are currency per kWh, keyed by the **season name** used in `seasons`
  and then by the period label `touPeriodAt` returns.
- `ALL`, as a season key or as a rate key, applies to every period (Tesla
  Fleet API docs, `tou_settings`). Tesla recommends a flat tariff be written as
  `energy_charges.ALL.rates.ALL` alone, with no periods. The live site and
  Tesla's example (`PGE-EV2-A.json`) both carry `ALL.ALL = 0` beside
  per-period rates.
- `sell_tariff` has its own `seasons`, `energy_charges` and `currency`. On the
  live site (Duke net metering) its rates mirror the buy rates.
- `currency` is one of `USD`, `EUR`, `GBP`, where Amber and Static report a
  symbol (`"$"`).
- Tesla validates every tariff written through the API: seasons cover the
  year with no gaps or overlaps; periods cover each week with no gaps or
  overlaps; every period with times has a price and every price has times;
  no negative prices; buy price >= sell price at all times. A CPP day written
  by the script therefore carries its `ON_PEAK` rate, and export never
  exceeds import.
- Labels may be any string; the app displays only `ON_PEAK`, `OFF_PEAK`,
  `PARTIAL_PEAK`, `SUPER_OFF_PEAK`.

## Approaches

- **A. A new Pricing module reading the tariff through the Powerwall EMS module
  (chosen).** It looks up `TeslaPowerwall2` at call time and uses its
  `getTariff()`, so the fetch, cache, token handling, site discovery and time
  zone come for free. It appears wherever Pricing modules do: API, UI, policy
  refresh.
- B. Add `importPrice` / `exportPrice` attributes to the EMS module. Smaller,
  but it is not a Pricing module, so it is missing from `/api/getPricing` and
  gets no forecast or cheapest window. Rejected.
- C. A standalone Pricing module that fetches the tariff itself. Duplicates
  the cloud fetch path and doubles the reads. Rejected.

Within A, the cheapest-window and derived-attribute code is moved out of
`AmberPricing` into a shared helper both modules use, rather than copied.

## Decisions

### Tariff resolution (`lib/TWCManager/EMS/TeslaPowerwall2.py`)

- Split the season choice out of `touPeriodAt` into a function that returns the
  winning season's **name** as well as the season, using the same
  shortest-span rule. `touPeriodAt` keeps its behaviour and signature.
- A price lookup function: given a tariff (or its `sell_tariff`) and a local
  `datetime`, return the price in effect, or `None`. Price is the sum of
  whichever of these exist: `energy_charges[season].rates[label]`,
  `energy_charges[season].rates.ALL`, `energy_charges.ALL.rates[label]`,
  `energy_charges.ALL.rates.ALL`. `None` only when none exists. A flat tariff
  (`ALL.ALL` only) therefore prices every hour.
- Export price resolves against `sell_tariff`'s own `seasons` and
  `energy_charges`, not the buy tariff's.
- The time zone choice `touPeriod` makes (`installation_time_zone`, else the
  host clock) is shared, not repeated.

### Shared forecast helper (`lib/TWCManager/Pricing/`)

- Move `getCheapestWindow`'s search and `_recomputeDerived`'s min/max and
  in-window logic into a helper that works on a forecast list
  (`[{"timestamp": aware datetime, "importPrice": float, ...}]`) and a slot
  length in minutes. Amber passes 30; its behaviour and tests stay the same.
- `getPriceForecast`'s serialisation (timestamps to ISO strings, cut to the
  horizon) moves with it.

### The module (`lib/TWCManager/Pricing/TeslaPricing.py`)

- Config `pricing.Tesla`; policy names `modules.TeslaPricing.*`. Opt-in with
  `enabled`, like the other Pricing modules. Without the `TeslaPowerwall2`
  module loaded, it logs once and stays loaded but reports no price, rather
  than unloading, because module load order is not guaranteed.
- Capabilities: `AdvancePricing`, `Forecasting`.
- `importPrice` / `exportPrice`: resolved on each access from the cached
  tariff, like `touPeriod`. When the price is unknown the attribute is
  **absent** (the property raises `AttributeError`), so `policyValue`'s
  `getattr(module, attr, value)` falls back to the unresolved macro and a
  numeric comparison does not match. `getImportPrice()` / `getExportPrice()`
  return `None` in that case; the API reports `null`.
- `currency`: the symbol for the tariff's code (`$`, `€`, `£`), matching what
  Amber and Static report; any other code passes through unchanged.
- `update()`: no-op beyond touching the EMS module's tariff cache, so the
  background `getPricing` task works.
- Forecast: step through the horizon in 30-minute slots, evaluating the price
  lookup at each slot's start in the site's time zone. Slots with no price are
  left out. Rebuild when the cached tariff object changes or the first slot has
  passed; no fetch of its own.
- `cheapWindow` config, `cheapWindowActive`, `cheapWindowStart`,
  `forecastMinPrice`, `forecastMaxPrice`: same meaning and config shape as
  Amber's, via the shared helper.

### Docs and changelog

- New `docs/modules/Pricing_Tesla.md` in the style of the other Pricing pages,
  for installers: prices come from the rate plan in the Tesla app; needs the
  Powerwall source configured and Tesla API access to energy data; how to set
  up a `cheapWindow`. See [[user-facing-docs]].
- `docs/PolicyCustomization.md`: add `TeslaPricing` to the list of Pricing
  modules; the price examples already use the generic form.
- Commented example under `pricing` in `etc/twcmanager/config.json`.
- Changelog: one new-feature line, verb first. No Bugfixes line.

## Builder's calls (mine, flag if wrong)

- `ALL` rates add to a period's own rate rather than standing in when it is
  missing. Tesla says only that they "apply to all time periods"; both readings
  agree on every tariff seen so far (`ALL.ALL` is 0, or the only price).
- Forecast slots of 30 minutes, matching Amber. Tariff windows on a quarter
  hour lose up to 15 minutes of precision at the edge; none seen so far.
- When several windows tie for cheapest (common on a fixed plan), the earliest
  wins, as Amber's search already does.
- No `sell_tariff`: export price is absent, not 0 and not the buy price.
- Holiday seasons are named with a year but recur yearly in the data. The CPP
  script writes and prunes them, so they are resolved as-is, the same way
  `touPeriod` does.
- Owner-only token: times follow the host clock, the existing `touPeriod`
  caveat. Documented, not fixed here.
- Empty forecast (no tariff, no EMS module, every slot unpriced): the shared
  helper returns `None` for min, max and window. Tesla leaves
  `forecastMinPrice` / `forecastMaxPrice` absent (same fail-safe as
  `importPrice`) and `cheapWindowActive` 0. Amber maps `None` to its current
  0s, so its behaviour is unchanged.
- Gaps: the window search checks that each slot's timestamp follows the
  previous one by the slot length; a window that spans a missing slot is not a
  candidate. Amber's series is contiguous, so its results do not change.
- Slots are aligned to the half hour in the site's time zone; the first slot is
  the one containing now.
- `cheapWindowActive` and `cheapWindowStart` are properties, computed on each
  access from the cached forecast and the current time, so they never lag a
  slot boundary. The forecast itself is rebuilt when `getTariff()` returns a
  different object (each cloud refresh does) or its first slot has ended.
- Hours no window names price as `OFF_PEAK`, the label `touPeriodAt` gives
  them. Tesla's validation forbids such gaps, so this matters only for a flat
  tariff (where `ALL` prices them) or a tariff not written through the API.
- Missing rates and forecast gaps are handled for robustness, not because a
  valid tariff produces them: an unread tariff is the realistic case.

## Left to the builder

- Where the shared forecast helper lives (module of functions vs a mixin) and
  its name.
- Tests: price lookup across season wrap, a one-day season inside its parent,
  a label with no rate, `ALL.ALL` added, sell tariff with its own seasons,
  missing `sell_tariff`; forecast slots across a period boundary and midnight;
  cheapest window on a fixed plan; unknown price does not match an `lt` policy;
  Amber's existing tests unchanged.
