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

