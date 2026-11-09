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

