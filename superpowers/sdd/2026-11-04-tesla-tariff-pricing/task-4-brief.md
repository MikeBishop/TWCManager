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

