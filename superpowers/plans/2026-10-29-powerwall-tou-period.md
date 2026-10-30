# Powerwall Time-of-Use Period Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `modules.TeslaPowerwall2.touPeriod`, the rate-plan period in effect now, resolved from the tariff in the Powerwall's `site_info`.

**Architecture:** A pure function resolves a `tariff_content_v2` object plus a local datetime to a period label. The module's existing Storm Watch cloud read is generalised into one cached fetch helper used for both `live_status` and `site_info`; `touPeriod` reads the cached `site_info` and resolves on every access.

**Tech Stack:** Python 3 stdlib (`datetime`, `zoneinfo`), `requests`, pytest + `requests_mock`.

**Spec:** `.superpowers/specs/2026-10-29-powerwall-tou-period-design.md`

## Global Constraints

- No new dependencies; no paid Fleet API endpoints (`site_info` and `live_status` only).
- Tariff refresh uses the existing `cloudCacheTime` (`config.cloudUpdateInterval`, default 1800 s); fetch is lazy (only when a property is read).
- A failed or missing read never blocks charging: keep the last good tariff; never read → `touPeriod == ""`.
- Never log an exception's text or a URL from the cloud path (it can carry the token): log `type(e).__name__` only, as `getStormWatch` does today.
- Work on a new branch `feat/powerwall-tou-period` from `main` (the current branch holds unrelated work).
- Full test run: `pytest --ignore=tests/API --ignore=tests/integration`.
- Comments explain why the code is as it is, not its history.

## Review Focus

1. Malformed tariff (season missing `tou_periods`, window missing keys, label value neither list nor `{"periods": [...]}`) → `touPeriodAt` returns a label or `""`, never raises (Task 1 test `test_malformed_tariff_never_raises`).
2. Unknown `installation_time_zone` string → falls back to the box's local time, no exception (Task 2 test `test_bad_time_zone_falls_back_to_local`).
3. `site_info` fails after an earlier success → `touPeriod` still resolves from the last good tariff (Task 2 test `test_failed_refresh_keeps_last_tariff`).
4. Token without `energy_device_data`, or no TeslaAPI module → `touPeriod == ""`, no request made (Task 2 test `test_no_energy_scope_gives_empty_period`).
5. Reading both `stormWatch` and `touPeriod` → separate cache entries, each endpoint fetched once per cache period, `products` discovery shared (Task 2 test `test_storm_watch_and_tariff_cache_separately`).

---

### Task 1: Tariff period resolver

**Files:**
- Modify: `lib/TWCManager/EMS/TeslaPowerwall2.py` (module-level function above the class)
- Test: `tests/unit/test_teslapowerwall2_ems.py` (new class `TestTouPeriodAt`)

**Interfaces:**
- Produces: `touPeriodAt(tariff: dict, now: datetime.datetime) -> str`. `tariff` is a `tariff_content_v2` object (or v1 — the only difference handled is a label's value being a list vs `{"periods": list}`). `now` is naive or aware, already in the site's local time; only its month, day, `weekday()`, hour, minute are used.

Rules (from the live site, spec "Constraints and data"):
- Season matches if `(month, day)` lies in `[(fromMonth, fromDay), (toMonth, toDay)]` inclusive; when from > to the range wraps the year end.
- Several seasons match → the one spanning the fewest days wins (one-day CPP season beats its parent). Span = days from from-date to to-date in a non-leap year, mod 365, +1.
- Window matches if `now.weekday()` in `[fromDayOfWeek, toDayOfWeek]` (wrap if from > to; 0 = Monday) and minute-of-day in `[fromHour*60+fromMinute, toHour*60+toMinute)`, where an end of 0 means 1440; if start > end the window wraps midnight.
- Missing numeric keys default to 0 (the API omits zero values).
- No season matches, or no `seasons`, → `""`. Season matches but no window → `"OFF_PEAK"`.
- Wrong types anywhere → treat that season/window as non-matching; never raise.

Test fixture: copy the live tariff's `seasons` into a module constant `DUKE` in v2 form (labels wrapped in `{"periods": [...]}`): "Summer" Oct 1–Apr 30 with OFF_PEAK all days 05:00–00:00 and SUPER_OFF_PEAK all days 00:00–05:00; "Winter" May 1–Sep 30 with OFF_PEAK Mon–Fri 05:00–14:00 and 20:00–00:00 and Sat–Sun 05:00–00:00, ON_PEAK Mon–Fri 14:00–20:00, SUPER_OFF_PEAK Mon–Fri and Sat–Sun 00:00–05:00. (Exact window values: spec/session record of the 2026-10-29 read.)

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime
from TWCManager.EMS.TeslaPowerwall2 import touPeriodAt

class TestTouPeriodAt:
    def test_weekday_peak_in_season(self):
        assert touPeriodAt(DUKE, datetime(2026, 7, 15, 15, 0)) == "ON_PEAK"   # Wed

    def test_peak_end_is_exclusive(self):
        assert touPeriodAt(DUKE, datetime(2026, 7, 15, 20, 0)) == "OFF_PEAK"

    def test_weekend_has_no_peak(self):
        assert touPeriodAt(DUKE, datetime(2026, 7, 18, 15, 0)) == "OFF_PEAK"  # Sat

    def test_midnight_end_covers_late_evening(self):
        assert touPeriodAt(DUKE, datetime(2026, 7, 15, 23, 59)) == "OFF_PEAK"

    def test_season_wrapping_year_end(self):
        assert touPeriodAt(DUKE, datetime(2026, 1, 10, 3, 0)) == "SUPER_OFF_PEAK"
        assert touPeriodAt(DUKE, datetime(2026, 10, 29, 15, 0)) == "OFF_PEAK"

    def test_one_day_season_beats_parent(self):
        cpp = copy.deepcopy(DUKE)
        cpp["seasons"]["CPP"] = {"fromMonth": 1, "fromDay": 12, "toMonth": 1, "toDay": 12,
            "tou_periods": {"ON_PEAK": {"periods": [{"fromDayOfWeek": 0, "toDayOfWeek": 6,
                "fromHour": 6, "toHour": 9}]}}}
        assert touPeriodAt(cpp, datetime(2026, 1, 12, 7, 0)) == "ON_PEAK"
        assert touPeriodAt(cpp, datetime(2026, 1, 12, 10, 0)) == "OFF_PEAK"
        assert touPeriodAt(cpp, datetime(2026, 1, 13, 7, 0)) == "OFF_PEAK"

    def test_v1_list_form(self):
        v1 = {"seasons": {"All": {"fromMonth": 1, "fromDay": 1, "toMonth": 12, "toDay": 31,
            "tou_periods": {"ON_PEAK": [{"toDayOfWeek": 6, "fromHour": 16, "toHour": 21}]}}}}
        assert touPeriodAt(v1, datetime(2026, 3, 3, 17, 0)) == "ON_PEAK"

    def test_no_season_matches(self):
        assert touPeriodAt({}, datetime(2026, 7, 15, 15, 0)) == ""
        only_summer = {"seasons": {"S": {"fromMonth": 6, "fromDay": 1, "toMonth": 9, "toDay": 30,
            "tou_periods": {}}}}
        assert touPeriodAt(only_summer, datetime(2026, 1, 1, 12, 0)) == ""

    def test_malformed_tariff_never_raises(self):
        now = datetime(2026, 7, 15, 15, 0)
        for bad in ({"seasons": None}, {"seasons": {"S": None}},
                    {"seasons": {"S": {"toMonth": 12, "toDay": 31}}},
                    {"seasons": {"S": {"toMonth": 12, "toDay": 31,
                        "tou_periods": {"ON_PEAK": "x"}}}},
                    {"seasons": {"S": {"toMonth": 12, "toDay": 31,
                        "tou_periods": {"ON_PEAK": [None, {"fromHour": "a"}]}}}}):
            assert touPeriodAt(bad, now) in ("", "OFF_PEAK")
```

(`DUKE` and `import copy` at module top.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_teslapowerwall2_ems.py::TestTouPeriodAt -v`
Expected: FAIL with `ImportError: cannot import name 'touPeriodAt'`

- [ ] **Step 3: Implement `touPeriodAt(tariff, now) -> str`** in `lib/TWCManager/EMS/TeslaPowerwall2.py` per the rules above. Small private helpers for "date in season / span" and "window matches" are fine; wrap per-season and per-window evaluation so a bad entry is skipped.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_teslapowerwall2_ems.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/EMS/TeslaPowerwall2.py tests/unit/test_teslapowerwall2_ems.py
git commit -m "Resolve the current period from a Powerwall tariff"
```

---

### Task 2: Cloud fetch helper, `touPeriod`, docs, changelog

**Files:**
- Modify: `lib/TWCManager/EMS/TeslaPowerwall2.py` (`getStormWatch`, new `getCloudJson`, `getTariff`, property `touPeriod`)
- Modify: `docs/PolicyCustomization.md` (TeslaPowerwall2 property list ~line 252; example policy)
- Modify: `CHANGELOG.md` (v1.4.1 Upcoming → Features)
- Test: `tests/unit/test_teslapowerwall2_ems.py` (extend `TestStormWatchTokenSlots`, or a sibling class reusing its `_powerwall` helper)

**Interfaces:**
- Consumes: `touPeriodAt(tariff, now) -> str` (Task 1).
- Produces:
  - `getCloudJson(self, endpoint: str) -> dict` — `GET {energy_sites base}/{cloudID}/{endpoint}`, returns `response` body, cached under `lastFetch["CLOUD/" + endpoint]` for `cloudCacheTime`. All existing `getStormWatch` behaviour moves here unchanged: slot lookup, token expiry check, `products` discovery of `cloudID`, 10 s timeout, 403-on-fleet → `slot.reportScopeRefused("energy", refused=True)`, type-only logging, keep previous data on failure.
  - `getStormWatch(self) -> dict` = `self.getCloudJson("live_status")`.
  - `getTariff(self) -> dict` = `self.getCloudJson("site_info")`.
  - property `touPeriod -> str`: `info = self.getTariff()`; `tariff = info.get("tariff_content_v2")`; no dict → `""`; `now` = `datetime.now(ZoneInfo(info["installation_time_zone"]))`, falling back to `datetime.now()` when absent or `ZoneInfoNotFoundError`/`ValueError`; return `touPeriodAt(tariff, now)`.

Test fixture: `SITE_INFO = ".../energy_sites/42/site_info"` alongside the existing `SITE`; a response `{"response": {"installation_time_zone": "America/New_York", "tariff_content_v2": DUKE}}`. Freeze "now" by patching the module's `datetime` (or pass through a seam of your choice) so results don't depend on the test's run time.

- [ ] **Step 1: Write the failing tests**

- `test_tou_period_reads_site_info`: fleet token with energy scope; `site_info` mocked as above; now frozen to 2026-07-15 15:00 New York → `pw.touPeriod == "ON_PEAK"`; one request to `site_info`.
- `test_failed_refresh_keeps_last_tariff`: first read succeeds; clear the cache timestamp (`pw.lastFetch["CLOUD/site_info"] = (0, pw.lastFetch["CLOUD/site_info"][1])`); `site_info` now 500 → `pw.touPeriod == "ON_PEAK"` still; log contains `HTTPError`, not `Bearer`.
- `test_no_energy_scope_gives_empty_period`: token without `energy_device_data` → `pw.touPeriod == ""`, `site_info` call_count 0. Also `master.getModuleByName` returning `None` → `""`.
- `test_bad_time_zone_falls_back_to_local`: `installation_time_zone: "Not/AZone"` → returns a label from `DUKE` (no exception).
- `test_storm_watch_and_tariff_cache_separately`: `cloudID = None`; `products` mocked with one `ac_powerwall` site 42; read `stormWatch`, `touPeriod`, then both again with default `cloudCacheTime` → `products` 1 call, `live_status` 1, `site_info` 1.
- Existing four Storm Watch tests stay green unchanged.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_teslapowerwall2_ems.py -v`
Expected: new tests FAIL (`AttributeError: ... 'touPeriod'`); existing tests PASS.

- [ ] **Step 3: Implement** `getCloudJson`, re-point `getStormWatch`, add `getTariff` and `touPeriod`. Net line growth in the module should be small: the helper is the old `getStormWatch` body with the endpoint as a parameter and the log/key text generalised ("Skipping Powerwall cloud read; ...", "Error fetching Powerwall %s: %s" with endpoint and type name).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_teslapowerwall2_ems.py -v`
Expected: all PASS

- [ ] **Step 5: Docs.** In `docs/PolicyCustomization.md`, under "From `TeslaPowerwall2`", add after `stormWatch`:

```
    - `touPeriod`:  The rate-plan period in effect now, from the tariff set in
      the Tesla app (for example `ON_PEAK`, `PARTIAL_PEAK`, `OFF_PEAK` or
      `SUPER_OFF_PEAK`); empty until the tariff has been read. Needs the Tesla
      API with a token that can read energy data, and refreshes every
      `cloudUpdateInterval`
```

and an example in the extension-points area: an `emergency` policy "Peak Electricity" matching `gridStatus eq true` and `touPeriod` eq `ON_PEAK` or `PARTIAL_PEAK` with `charge_amps: 0`, one sentence saying it stops charging during peak periods while the grid is up, and that it overrides Charge Now. Installer voice: what it does and how to set it up, not internals.

- [ ] **Step 6: Changelog.** Under `## v1.4.1 - Upcoming` → `* Features`, append:

```
    * (@MikeBishop) - Policies can match the Powerwall's current rate-plan period (`modules.TeslaPowerwall2.touPeriod`, such as `ON_PEAK`), read from the tariff set in the Tesla app with a free energy-site read
```

- [ ] **Step 7: Full test run**

Run: `pytest --ignore=tests/API --ignore=tests/integration -q`
Expected: no failures.

- [ ] **Step 8: Commit**

```bash
git add lib/TWCManager/EMS/TeslaPowerwall2.py tests/unit/test_teslapowerwall2_ems.py docs/PolicyCustomization.md CHANGELOG.md
git commit -m "Expose the Powerwall's time-of-use period to policies"
```

---

### Task 3: Verify on the live box

**Files:** none in the repo; `/etc/twcmanager/config.json` on `twcmanager` only with the user's go-ahead.

- [ ] **Step 1:** Deploy the branch to `ssh twcmanager` and restart (pre-approved).
- [ ] **Step 2:** Confirm in the log at INFO8 policy evaluation, or with a one-off Python call against the running config, that `touPeriod` returns the expected label for now in America/New_York (2026-10-29 falls in "Summer" Oct–Apr: `OFF_PEAK` 05:00–24:00, `SUPER_OFF_PEAK` 00:00–05:00), and that the log shows no Powerwall cloud errors.
- [ ] **Step 3:** Ask the user before editing their config to uncomment the "Peak Electricity" policy with the `touPeriod` conditions.
