### Task 5: Docs, example config, changelog

**Files:**
- Create: `docs/modules/Pricing_Tesla.md` (same sections as `Pricing_Amber.md`: Introduction, Forecasting, Status table, Configuration table, JSON example)
- Modify: `docs/PolicyCustomization.md:273` (add `TeslaPricing` to the Pricing module list; one sentence noting a forecasting module includes it), `docs/modules/control_HTTP_API/getPricingForecast.md:51` (mention Tesla alongside Amber), `etc/twcmanager/config.json` (commented `"Tesla"` block after `"Amber"`, with the same commented `cheapWindow`), `CHANGELOG.md` (one Features line under v1.4.1)

- [ ] **Step 1: Write** the docs. Content the installer needs: prices come from the rate plan set in the Tesla app; requires the Powerwall source configured and Tesla API access to energy data (the same access `touPeriod` needs); a flat-rate plan works; prices update when the tariff is re-read (`cloudUpdateInterval`); with only an Owner API token, times follow the TWCManager host's clock; currency is shown as `$`, `€` or `£`. No internal names.
- [ ] **Step 2: Changelog line**, verb first, 1–2 sentences: `* (@MikeBishop) - Report electricity prices and a cheapest charging window from the rate plan set in the Tesla app (\`pricing.Tesla\`), for policies and the pricing API ([details](docs/modules/Pricing_Tesla.md))`
- [ ] **Step 3: Verify** `python -c "import json,re;..."` is not needed (config.json is commented JSON); instead run the full test suite once more. Expected: pass.
- [ ] **Step 4: Commit** — `Document the Tesla pricing module`.
