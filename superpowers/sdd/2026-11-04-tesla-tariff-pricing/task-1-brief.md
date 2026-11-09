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

