# Powerwall time-of-use period for policies — design

Date: 2026-10-29. Size: small change.

## Intent

Let a policy condition test which rate-plan period the Powerwall's tariff says
is in effect right now. Driving use case: an `emergency` policy that stops
charging during peak while the grid is up, replacing a commented-out policy
that hard-codes `tm_hour` 14–20 and `tm_mon` 5–9:

```
"match":     [ "modules.TeslaPowerwall2.gridStatus",
               [ "modules.TeslaPowerwall2.touPeriod", "modules.TeslaPowerwall2.touPeriod" ] ],
"condition": [ "eq", [ "eq", "eq" ] ],
"value":     [ true, [ "ON_PEAK", "PARTIAL_PEAK" ] ],
"charge_amps": 0
```

Duke critical-peak (CPP) days vary. A separate script writes each CPP day
into the Powerwall tariff as a one-day season whose CPP window is `ON_PEAK`
and the rest of the day unchanged, and later drops past one-day seasons. The
tariff in the Tesla app becomes the single source of truth; TWCManager only
reads it.

## Goals

- `modules.TeslaPowerwall2.touPeriod`: the current period label
  (`ON_PEAK`, `PARTIAL_PEAK`, `OFF_PEAK`, `SUPER_OFF_PEAK`, or any label the
  tariff uses), usable in any policy.
- Pick up a CPP day within one refresh cycle of the script writing it.

## Non-goals

- Writing the tariff (the CPP script's job).
- Prices, sell rates, demand charges, "cheapest window" logic.
- A webhook / API to force a re-read: a 30-minute refresh fits inside Duke's
  one-hour short-notice case. Revisit if that proves too slow.
- Local gateway API: it does not expose the tariff.

## Anti-goals

- Paid Fleet API calls for this.
- New dependencies.
- A failed or missing read blocking charging.

## Constraints and data (verified against the live site, 2026-10-29)

- `GET /api/1/energy_sites/{id}/site_info` (uncharged; same `energy_device_data`
  scope the Storm Watch read already uses) returns `tariff_content` (v1),
  `tariff_content_v2`, and `installation_time_zone`. Tesla's published
  sample omits the tariff fields; the real response has them.
- v1 shape: `seasons[name] = {fromMonth, fromDay, toMonth, toDay,
  tou_periods: {LABEL: [{fromDayOfWeek, toDayOfWeek, fromHour, fromMinute,
  toHour, toMinute}, ...]}}`. v2 wraps each label's list as `{"periods": [...]}`.
- Seasons wrap the year end (`fromMonth: 10, toMonth: 4`); season names are
  labels only.
- `toHour: 0, toMinute: 0` means end of day (midnight).
- Day of week 0 = Monday … 6 = Sunday (matches Python `tm_wday`).
- Seasons are month/day ranges only; any count and any length, including
  one-day CPP seasons.
- `tariff_rate` returns the same v1 content but sits in an `energy_reads`
  billing category; not used.

## Approaches

- **A. Read `site_info`, resolve locally (chosen).** Fetch the tariff on the
  existing Storm Watch cadence, resolve the current period in the site's time
  zone on every policy check. Free endpoint, reuses the module's token, site
  discovery and 403 scope handling, has the time zone. Chosen once the live
  read showed `site_info` carries the tariff.
- B. Same, using python-tesla-fleet-api's resolver. Tested, but async and
  pulls in aiohttp for ~60 lines in a synchronous `requests` codebase. Rejected.
- C. Read `tariff_rate`. Documented, but potentially billable and lacks the
  time zone. Rejected.

## Decisions

- Data: `site_info`'s tariff, fetched in the same call path and cache
  (`cloudUpdateInterval`, default 1800 s) as the Storm Watch read. Share one
  fetch/cache helper between `live_status` and `site_info` rather than
  duplicating the token/discovery/error code.
- Fetch lazily, as Storm Watch does: only sites whose policies read
  `touPeriod` make the call.
- `touPeriod` resolves on every access from the cached tariff; no network.

## Builder's calls (mine, flag if wrong)

- Read `tariff_content_v2` (what the app and the CPP script write); handle
  `{"periods": [...]}`.
- Time: now in `installation_time_zone` (`zoneinfo`); fall back to the box's
  local time if absent.
- A time matched by no window resolves to `OFF_PEAK`.
- If seasons overlap (Tesla forbids it, but a lazily-cleaned tariff might
  briefly), the shortest matching season wins, so a one-day CPP season beats
  its parent.
- A failed read keeps the last good tariff. No tariff ever read: `touPeriod`
  is `""`, so a peak policy does not match and charging proceeds as today.
- Docs: add `touPeriod` to the `TeslaPowerwall2` list in
  `docs/PolicyCustomization.md`, with the peak policy as an example, written
  for installers (labels come from the tariff in the Tesla app; needs the
  Tesla API with energy scope).
- Changelog: one new-feature line (1–2 sentences, verb first); no Bugfixes
  line.
- `live_status` (checked 2026-10-29) carries no tariff or period, so the
  tariff needs its own `site_info` read.

## Left to the builder

- Resolver placement (module method vs small helper) and tests: season wrap,
  midnight end, weekday ranges, one-day season inside a parent, unmatched
  time, missing tariff.
