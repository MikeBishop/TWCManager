# Prices from the Powerwall Tariff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `TeslaPricing` module that reports import/export price, a forecast and a cheapest window from the Powerwall's tariff, sharing Amber's window logic instead of copying it.

**Architecture:** `TeslaPowerwall2` gains pure tariff-price functions next to `touPeriodAt`. A new `Pricing/Forecast.py` holds the cheapest-window, min/max and serialisation logic taken out of `AmberPricing`. `Pricing/TeslaPricing.py` reads the tariff through the loaded `TeslaPowerwall2` module (no fetch of its own) and builds a 30-minute forecast from it.

**Tech Stack:** Python 3.8+, pytest, requests_mock (existing).

**Spec:** `.superpowers/specs/2026-11-04-tesla-tariff-pricing-design.md`

## Global Constraints

- Python 3.8 must import and run every touched module (`zoneinfo` may be missing; fall back to the host clock as `touPeriod` does).
- No new dependencies. No Fleet read beyond the existing cached `site_info` / `tariff_rate`.
- An unknown price is never reported as 0 to policy: the attribute is absent (property raises `AttributeError`).
- Amber's behaviour and its existing tests in `tests/unit/test_pricing_amber.py` stay unchanged.
- Comments explain why the code is what it is; no history, no PR/phase references.
- Lib growth limited to the new module's own logic; Amber shrinks by what moves to `Forecast.py`. Report `git diff --stat main -- lib` per task.
- Docs are for installers: capabilities and setup, no internal names; say "EVSE", not "charger".
- Format with Black before each commit.
- `python` below means the main checkout's virtualenv (`/home/mbishop/github/TWCManager/.venv/bin/python`); there is no system `python`.
- Full test run: `python -m pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios -q`

## Review Focus

- A price that cannot be resolved (tariff not read yet, Powerwall module not loaded, no `sell_tariff`) must leave `importPrice`/`exportPrice` absent so `modules.TeslaPricing.importPrice lt X` does not match. Pinned in Task 3.
- A forecast crossing a DST change (America/New_York, 2026-11-01) keeps 30-minute UTC steps and prices each slot by local wall time. Pinned in Task 4.
- An Owner-only token gives no time zone: forecast timestamps must still be timezone-aware (host local). Pinned in Task 4.
- A one-day CPP season inside the horizon prices its window at the CPP season's `ON_PEAK` rate. Pinned in Task 4.
- A gap in the forecast (unpriced slot) must not let a window span it. Pinned in Task 2.

---

### Task 1: Tariff price lookup in the Powerwall module

**Files:**
- Modify: `lib/TWCManager/EMS/TeslaPowerwall2.py` (module functions above the class; `touPeriod` property)
- Test: `tests/unit/test_teslapowerwall2_ems.py` (new class `TestTariffPriceAt`)

**Interfaces:**
- Produces:
  - `activeSeason(tariff, now) -> tuple[str, dict] | None` — winning season's name and dict; same shortest-span rule `touPeriodAt` uses today.
  - `touPeriodAt(tariff, now) -> str` — unchanged behaviour, now built on `activeSeason`.
  - `tariffPriceAt(tariff, now) -> float | None` — price for `now` (site-local datetime) from `tariff["energy_charges"]`. Callers pass `tariff["sell_tariff"]` for export.
  - `siteZone(zone) -> tzinfo | None` — `ZoneInfo(zone)`, or `None` when `zoneinfo` is missing, `zone` is `None`, or unknown.

- [ ] **Step 1: Write the failing tests.** Add fixture `DUKE_PRICED = dict(copy.deepcopy(DUKE), currency="USD", energy_charges=CHARGES, sell_tariff={"seasons": DUKE["seasons"], "energy_charges": SELL})` where `CHARGES = {"ALL": {"rates": {"ALL": 0}}, "Summer": {"rates": {"OFF_PEAK": 0.158036, "SUPER_OFF_PEAK": 0.146273}}, "Winter": {"rates": {"OFF_PEAK": 0.158036, "ON_PEAK": 0.30, "SUPER_OFF_PEAK": 0.146273}}}` and `SELL` is the same with every rate halved.

```python
class TestTariffPriceAt:
    def _at(self, tariff, *when):
        from TWCManager.EMS.TeslaPowerwall2 import tariffPriceAt
        return tariffPriceAt(tariff, datetime(*when))

    def test_peak_price(self):
        assert self._at(DUKE_PRICED, 2026, 7, 15, 15, 0) == 0.30

    def test_season_wrap_price(self):
        assert self._at(DUKE_PRICED, 2026, 1, 10, 3, 0) == 0.146273

    def test_all_rates_add(self):
        t = copy.deepcopy(DUKE_PRICED)
        t["energy_charges"]["ALL"]["rates"] = {"ALL": 0.01, "ON_PEAK": 0.02}
        t["energy_charges"]["Winter"]["rates"]["ALL"] = 0.04
        assert self._at(t, 2026, 7, 15, 15, 0) == pytest.approx(0.37)
        assert self._at(t, 2026, 7, 15, 21, 0) == pytest.approx(0.208036)

    def test_flat_tariff_prices_every_hour(self):
        flat = {"seasons": {"Year": {"fromMonth": 1, "fromDay": 1, "toMonth": 12, "toDay": 31, "tou_periods": {}}},
                "energy_charges": {"ALL": {"rates": {"ALL": 0.25}}}}
        assert self._at(flat, 2026, 3, 3, 17, 0) == 0.25

    def test_label_without_rate_is_unknown(self):
        t = copy.deepcopy(DUKE_PRICED)
        del t["energy_charges"]["Winter"]["rates"]["ON_PEAK"]
        del t["energy_charges"]["ALL"]
        assert self._at(t, 2026, 7, 15, 15, 0) is None

    def test_cpp_season_uses_its_own_rates(self):
        t = copy.deepcopy(DUKE_PRICED)
        t["seasons"]["CPP"] = {"fromMonth": 1, "fromDay": 12, "toMonth": 1, "toDay": 12,
            "tou_periods": {"ON_PEAK": {"periods": [{"toDayOfWeek": 6, "fromHour": 6, "toHour": 9}]},
                            "OFF_PEAK": {"periods": [{"toDayOfWeek": 6, "fromHour": 9, "toHour": 6}]}}}
        t["energy_charges"]["CPP"] = {"rates": {"ON_PEAK": 0.90, "OFF_PEAK": 0.158036}}
        assert self._at(t, 2026, 1, 12, 7, 0) == 0.90
        assert self._at(t, 2026, 1, 13, 7, 0) == 0.146273

    def test_sell_tariff_resolves_on_its_own_seasons(self):
        assert self._at(DUKE_PRICED["sell_tariff"], 2026, 7, 15, 15, 0) == 0.15

    def test_no_charges_or_malformed_is_unknown(self):
        for bad in ({}, DUKE, dict(DUKE, energy_charges=None), dict(DUKE, energy_charges={"Winter": "x"})):
            assert self._at(bad, 2026, 7, 15, 15, 0) is None

    def test_site_zone(self):
        from TWCManager.EMS.TeslaPowerwall2 import siteZone
        assert siteZone(None) is None and siteZone("Not/AZone") is None
        assert siteZone("America/New_York") is not None
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_teslapowerwall2_ems.py -q`. Expected: the new class fails on import of `tariffPriceAt`; existing tests pass.
- [ ] **Step 3: Implement** `activeSeason`, `tariffPriceAt`, `siteZone` in `TeslaPowerwall2.py`; rewrite `touPeriodAt` on `activeSeason`; `touPeriod` uses `siteZone` (`datetime.now(siteZone(zone))`). `tariffPriceAt` sums whichever of `energy_charges[season].rates[label]`, `energy_charges[season].rates["ALL"]`, `energy_charges["ALL"].rates[label]`, `energy_charges["ALL"].rates["ALL"]` exist; `None` if none exists or no season covers `now`. Never raises on malformed input (same tolerance as `touPeriodAt`).
- [ ] **Step 4: Run** the same command. Expected: all pass, including `TestTouPeriodAt` and `TestTouPeriodProperty` unchanged.
- [ ] **Step 5: Commit** — `Resolve the current price from a Powerwall tariff`.

### Task 2: Shared forecast helper; Amber uses it

**Files:**
- Create: `lib/TWCManager/Pricing/Forecast.py`
- Modify: `lib/TWCManager/Pricing/AmberPricing.py` (`_recomputeDerived`, `getPriceForecast`, `getCheapestWindow` delegate; their bodies move)
- Test: `tests/unit/test_pricing_forecast.py`

**Interfaces:**
- Consumes: forecast entries `{"timestamp": aware datetime, "importPrice": float, ...}` (Amber's existing shape).
- Produces (module functions in `TWCManager.Pricing.Forecast`):
  - `cheapestWindow(forecast, numHours, startHour=None, endHour=None, slotMinutes=30) -> dict | None` — Amber's search, returning `{"startHour", "startTimestamp" (ISO str), "avgPrice", "totalCost"}`; `None` for empty forecast or `numHours` outside 1..24. A candidate window whose consecutive timestamps differ by anything other than `slotMinutes` is skipped. Ties keep the earliest.
  - `priceRange(forecast) -> tuple[float, float] | None`
  - `windowActive(startTimestamp, hours, now) -> int` — 1 if `startTimestamp <= now < start + hours`, else 0; 0 when `startTimestamp` is `None`.
  - `serialise(forecast, hoursAhead, slotMinutes=30) -> list[dict]` — first `hoursAhead * 60 // slotMinutes` entries, timestamps as ISO strings.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_pricing_forecast.py`, building forecasts with a helper `_fc(prices, start=datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc))` that makes 30-minute entries:

```python
def test_cheapest_window_picks_lowest_average():
    best = cheapestWindow(_fc([4, 4, 1, 1, 3, 3]), 1)
    assert best["avgPrice"] == 1 and best["startTimestamp"] == "2026-07-15T01:00:00+00:00"

def test_tie_keeps_earliest():
    assert cheapestWindow(_fc([2, 2, 2, 2]), 1)["startTimestamp"] == "2026-07-15T00:00:00+00:00"

def test_window_never_spans_a_gap():
    fc = _fc([5, 1, 9, 1, 5])
    del fc[2]                      # 01:00 missing: 00:30 and 01:30 are not adjacent
    best = cheapestWindow(fc, 1)
    assert best["avgPrice"] == 3   # a window spanning the gap would average 1
    assert best["startTimestamp"] == "2026-07-15T00:00:00+00:00"

def test_empty_and_out_of_range():
    assert cheapestWindow([], 1) is None and cheapestWindow(_fc([1, 1]), 0) is None
    assert cheapestWindow(_fc([1, 1]), 25) is None and priceRange([]) is None

def test_hour_filter_wraps_midnight():
    # 22:00 to 06:00 bound, as Amber's startHour/endHour; uses local hours of the timestamps
    ...assert the chosen start's local hour is >= 22 or < 6

def test_window_active_and_serialise():
    start = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
    assert windowActive(start.isoformat(), 2, start + timedelta(minutes=119)) == 1
    assert windowActive(start.isoformat(), 2, start + timedelta(hours=2)) == 0
    assert windowActive(None, 2, start) == 0
    out = serialise(_fc([1] * 10), 2)
    assert len(out) == 4 and isinstance(out[0]["timestamp"], str)
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_pricing_forecast.py -q`. Expected: import error.
- [ ] **Step 3: Implement** `Forecast.py` by moving Amber's loop (`getCheapestWindow` body, `_recomputeDerived` min/max and in-window test, `getPriceForecast` serialisation) and adding the adjacency check. Amber keeps its public methods and attributes; `_recomputeDerived` maps `priceRange(...) is None` to its existing 0s; `cheapWindowActive` stays a plain attribute in Amber.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_pricing_forecast.py tests/unit/test_pricing_amber.py -q`. Expected: all pass, Amber's tests unmodified.
- [ ] **Step 5: Commit** — `Share the cheapest-window search between pricing modules`. Report the lib line delta (Amber should shrink by roughly what Forecast.py adds).

### Task 3: `TeslaPricing` current prices

**Files:**
- Create: `lib/TWCManager/Pricing/TeslaPricing.py`
- Modify: `lib/TWCManager/TWCManager.py` (add `"Pricing.TeslaPricing"` after `"Pricing.AmberPricing"`)
- Modify: `lib/TWCManager/Policy/Policy.py:469-487` (`doesConditionMatch` numeric comparisons)
- Test: `tests/unit/test_pricing_tesla.py`, `tests/unit/test_policy.py`

Today an unresolved `modules.*` reference stays as its macro text, and `gt`/`gte`/`lt`/`lte` against a number raise `TypeError`. That aborts the whole policy evaluation for the cycle (logged as `PolicyError`), so no policy applies, contrary to the "price rules fail safe" sentence in `docs/PolicyCustomization.md`. This affects every Pricing module when disabled, not only Tesla. The Pricing type is unreleased, so no Bugfixes changelog line.

**Interfaces:**
- Consumes: `master.getModuleByName("TeslaPowerwall2").getTariff() -> (tariff | None, zone | None)`; `tariffPriceAt`, `siteZone` from Task 1.
- Produces: class `TeslaPricing(master)` — config `pricing.Tesla`; `capabilities = {"AdvancePricing": True, "Forecasting": True}`; `getCapabilities(name)`; `update()`; `getImportPrice() / getExportPrice() -> float | None`; properties `importPrice`, `exportPrice` (raise `AttributeError` when unknown); `currency` property (`USD`→`$`, `EUR`→`€`, `GBP`→`£`, other codes unchanged, `"$"` before a tariff is read); internal `_siteTariff() -> (tariff | None, now: aware datetime)`.

- [ ] **Step 1: Write the failing tests.** `_master(cfg, tariff, zone="America/New_York")` returns a Mock whose `getModuleByName("TeslaPowerwall2")` yields a stub with `getTariff()` returning `(tariff, zone)`; reuse `DUKE_PRICED` by importing it from `tests.unit.test_teslapowerwall2_ems`. Freeze time by passing `now` into `_siteTariff` via a patched `datetime` (same `Frozen` pattern as `TestTouPeriodProperty`), at 2026-07-15 15:00 New York.

```python
def test_disabled_unloads(): ...releaseModule called with ("lib.TWCManager.Pricing", "TeslaPricing")
def test_prices_from_tariff():
    p = TeslaPricing(_master({"enabled": True}, DUKE_PRICED))
    assert p.importPrice == 0.30 and p.exportPrice == 0.15 and p.currency == "$"
    assert p.getCapabilities("Forecasting") is True
def test_unknown_price_is_absent():
    for tariff in (None, DUKE):                       # not read yet; no energy_charges
        p = TeslaPricing(_master({"enabled": True}, tariff))
        assert not hasattr(p, "importPrice") and p.getImportPrice() is None
def test_no_sell_tariff_leaves_export_absent(): ...
def test_without_powerwall_module(): ...getModuleByName returns None: stays loaded, prices absent, logs once over two reads
def test_unknown_price_does_not_match_lt_policy():
    # Policy.policyValue falls back to the macro text; doesConditionMatch("modules.TeslaPricing.importPrice", "lt", 0.5, False) is False, no raise
    ...build Policy as tests/unit/test_policy.py::TestPricingPolicyValue does, with master.modules = {"TeslaPricing": {...}}
def test_currency_codes(): EUR -> "€", GBP -> "£", "AUD" -> "AUD"
```

In `tests/unit/test_policy.py::TestPricingPolicyValue`:

```python
def test_unresolved_module_never_matches_numeric(self):
    # module not loaded at all: master.modules == {}
    for cond in ("gt", "gte", "lt", "lte"):
        assert policy.doesConditionMatch("modules.AmberPricing.importPrice", cond, 0.5, False) is False
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_pricing_tesla.py -q`. Expected: import error.
- [ ] **Step 3: Implement** `TeslaPricing.py` following `StaticPricing`'s init/unload pattern. `_siteTariff` looks up the Powerwall module on each call (load order is not guaranteed) and logs once at INFO if it is missing. `now` is `datetime.now(tz)` when `siteZone(zone)` gives a zone, else `datetime.now().astimezone()`. `update()` calls `_siteTariff()` so the background `getPricing` task keeps the tariff cache warm. Register the module in `TWCManager.py`. In `doesConditionMatch`, after `to_number`, a `gt`/`gte`/`lt`/`lte` where either side is not an `int`/`float` (bools excluded) returns `False`.
- [ ] **Step 4: Run** the Task 3 test file and `tests/unit/test_policy.py`. Expected: pass.
- [ ] **Step 5: Commit** — `Report prices from the Powerwall tariff as a Pricing module`.

### Task 4: `TeslaPricing` forecast and cheapest window

**Files:**
- Modify: `lib/TWCManager/Pricing/TeslaPricing.py`
- Test: `tests/unit/test_pricing_tesla.py`

**Interfaces:**
- Consumes: Task 2's `cheapestWindow`, `priceRange`, `windowActive`, `serialise`; Task 1's `tariffPriceAt`, `touPeriodAt`.
- Produces:
  - module function `tariffForecast(tariff, now, hours=48) -> list[dict]` — `hours * 2` slots, entries `{"timestamp": aware datetime in now's zone, "importPrice": float, "period": str}`; first slot is the half hour containing `now` (floored in `now`'s zone); slots step 30 minutes in UTC and are priced at `slot.astimezone(now.tzinfo)`; unpriced slots omitted. Timestamps are kept in the site's zone so ISO output (and `cheapWindowStart`) carries the local offset.
  - methods `updateForecast(hoursAhead=48)`, `getPriceForecast(hoursAhead=24) -> list`, `getCheapestWindow(numHours, startHour=None, endHour=None) -> dict | None`.
  - properties `forecastMinPrice`, `forecastMaxPrice` (absent when the forecast is empty), `cheapWindowActive` (0/1, computed per access), `cheapWindowStart` (ISO str or `None`).
  - config `pricing.Tesla.cheapWindow = {"hours", "startHour", "endHour"}`, same meaning as Amber's.

- [ ] **Step 1: Write the failing tests.**

```python
NY = ZoneInfo("America/New_York")

def test_forecast_slots_and_prices():
    fc = tariffForecast(DUKE_PRICED, datetime(2026, 7, 15, 13, 10, tzinfo=NY), hours=4)
    assert fc[0]["timestamp"] == datetime(2026, 7, 15, 13, 0, tzinfo=NY)
    assert [e["importPrice"] for e in fc[:4]] == [0.158036] * 2 + [0.30] * 2
    assert fc[2]["period"] == "ON_PEAK" and len(fc) == 8

def test_forecast_across_dst_end():
    fc = tariffForecast(DUKE_PRICED, datetime(2026, 11, 1, 0, 0, tzinfo=NY), hours=4)
    utc = [e["timestamp"].astimezone(timezone.utc) for e in fc]   # same-tzinfo subtraction ignores DST
    steps = {(b - a).total_seconds() for a, b in zip(utc, utc[1:])}
    assert steps == {1800} and len(fc) == 8   # the repeated 01:00 hour is two hours of slots

def test_forecast_without_zone_is_aware():
    fc = tariffForecast(DUKE_PRICED, datetime(2026, 7, 15, 13, 0).astimezone(), hours=1)
    assert all(e["timestamp"].tzinfo is not None for e in fc)

def test_cpp_day_in_horizon():
    ...DUKE_PRICED plus the Task 1 CPP season on 2026-07-16 06:00-09:00 at 0.90; forecast from 2026-07-15 22:00 NY
    ...assert the slots at 06:00-08:30 on the 16th are 0.90 and the cheapest 2h window avoids them

def test_cheap_window_on_fixed_plan():
    p = TeslaPricing(_master({"enabled": True, "cheapWindow": {"hours": 2, "startHour": 22, "endHour": 7}}, DUKE_PRICED))
    # frozen at 2026-07-15 15:00 NY: SUPER_OFF_PEAK (00:00-05:00, 0.146273) is cheapest; earliest wins
    assert p.cheapWindowStart == "2026-07-16T00:00:00-04:00" and p.cheapWindowActive == 0
    # refreeze at 2026-07-16 01:00: active
def test_min_max_and_api_forecast(): forecastMinPrice == 0.146273, forecastMaxPrice == 0.30, getPriceForecast(2) has 4 ISO entries
def test_empty_forecast_attributes(): tariff None -> no forecastMinPrice attribute, cheapWindowActive == 0, cheapWindowStart is None, getPriceForecast(24) == []
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_pricing_tesla.py -q`. Expected: new tests fail.
- [ ] **Step 3: Implement.** `tariffForecast` is a module function (pure, testable). The module caches the forecast and rebuilds when `getTariff()` returns a different object (`is not`) or the cached first slot has ended; `cheapWindowActive`/`cheapWindowStart` are properties that read the cache and call `windowActive` with the current site time. `updateForecast` just warms the cache.
- [ ] **Step 4: Run** the Task 4 tests, then the full run from Global Constraints. Expected: all pass.
- [ ] **Step 5: Commit** — `Forecast prices and the cheapest window from the Powerwall tariff`.

### Task 5: Docs, example config, changelog

**Files:**
- Create: `docs/modules/Pricing_Tesla.md` (same sections as `Pricing_Amber.md`: Introduction, Forecasting, Status table, Configuration table, JSON example)
- Modify: `docs/PolicyCustomization.md:273` (add `TeslaPricing` to the Pricing module list; one sentence noting a forecasting module includes it), `docs/modules/control_HTTP_API/getPricingForecast.md:51` (mention Tesla alongside Amber), `etc/twcmanager/config.json` (commented `"Tesla"` block after `"Amber"`, with the same commented `cheapWindow`), `CHANGELOG.md` (one Features line under v1.4.1)

- [ ] **Step 1: Write** the docs. Content the installer needs: prices come from the rate plan set in the Tesla app; requires the Powerwall source configured and Tesla API access to energy data (the same access `touPeriod` needs); a flat-rate plan works; prices update when the tariff is re-read (`cloudUpdateInterval`); with only an Owner API token, times follow the TWCManager host's clock; currency is shown as `$`, `€` or `£`. No internal names.
- [ ] **Step 2: Changelog line**, verb first, 1–2 sentences: `* (@MikeBishop) - Report electricity prices and a cheapest charging window from the rate plan set in the Tesla app (\`pricing.Tesla\`), for policies and the pricing API ([details](docs/modules/Pricing_Tesla.md))`
- [ ] **Step 3: Verify** `python -c "import json,re;..."` is not needed (config.json is commented JSON); instead run the full test suite once more. Expected: pass.
- [ ] **Step 4: Commit** — `Document the Tesla pricing module`.
