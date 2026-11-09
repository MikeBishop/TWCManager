# SDD ledger — plan: .superpowers/plans/2026-11-04-tesla-tariff-pricing.md
Spec: .superpowers/specs/2026-11-04-tesla-tariff-pricing-design.md
Pre-flight: T1->T3 (tariffPriceAt, siteZone) consistent. T1->T4 (tariffPriceAt, touPeriodAt) consistent; T4 needs label+price per slot — calls both. T2->T4 (cheapestWindow, priceRange, windowActive, serialise) consistent. T3->T4 (_siteTariff) consistent.
Task 1: complete (commits 3ba9084..3172f72, tests: python -m pytest tests/unit/test_teslapowerwall2_ems.py -q -p no:cacheprovider → ============================== 42 passed in 0.30s ==============================)
Task 1: Ruling: CPP test fixture on 2026-07-16 inside DUKE's May-Sep season instead of Jan 12 — reused by Task 4's horizon test — none
Task 2: complete (commits 3172f72..f2e3494, tests: python -m pytest tests/unit/test_pricing_forecast.py tests/unit/test_pricing_amber.py -q -p no:cacheprovider → ============================== 17 passed in 0.11s ==============================)
Task 2: Ruling: cheapestWindow takes tz (default None = host zone, Amber's existing behaviour) for the start-hour filter — Tesla must filter by site-local hour, not host hour — cost if wrong: none for Amber
Task 2: Ruling: window size numHours*60//slotMinutes rather than Amber's int(numHours)*2 — same for integer hours; fractional hours now honoured — cost: Amber config with fractional hours picks a slightly longer window than before
Task 3: complete (commits f2e3494..07c2c66, tests: python -m pytest tests/unit/test_pricing_tesla.py tests/unit/test_policy.py -q -p no:cacheprovider → ============================== 95 passed in 0.85s ==============================)
Task 4: Ruling: plan's CPP test expected the cheapest window at 00:00 on the CPP day; the CPP season's own OFF_PEAK replaces Winter's SUPER_OFF_PEAK, so the earliest equal-price run (22:00 the evening before) wins — test corrected, which also proves the CPP season is applied — none
Task 4: Ruling: zone-dependent forecast tests skip without zoneinfo (Python 3.8 CI); price tests still run there on host clock, verified by a simulated no-zoneinfo run (51 passed, 11 skipped) — cost: 3.8 forecast code unexercised by tests
Task 4: complete (commits 07c2c66..2240d1f, tests: python -m pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios -q -p no:cacheprovider → ================= 2657 passed, 1 warning in 174.69s (0:02:54) ==================)
Task 5: complete (commits 2240d1f..063ac22, tests: python -m pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios -q -p no:cacheprovider → ================= 2657 passed, 1 warning in 175.59s (0:02:55) ==================)
Final review: opus reviewer, 1 Critical, 3 Important, 7 Minor
Final: fixed cheapest window rolls forward inside itself (Critical) — test_cheap_window_holds_for_its_whole_length, test_latched_window_holds_until_it_ends, TestAmberLatchedWindow RED→GREEN, suite 2664/2664
Final: fixed window search rejects DST transitions — test_window_spans_dst_change RED→GREEN, suite 2664/2664
Final: fixed season named ALL priced twice — test_season_named_all_counts_once RED→GREEN, suite 2664/2664
Final: fixed host-clock forecast uses fixed offset across DST — test_host_clock_forecast_follows_host_dst RED→GREEN, suite 2664/2664
Final: fixed (re-graded Minor→Important) bools refused in numeric policy comparisons, silently breaking e.g. gridStatus gte 1 — test_bool_still_compares_numerically RED→GREEN, suite 2664/2664
Final: Ruling: latch fix applied to Amber too (shared helper) — same rolling bug there; Pricing type unreleased — cost: Amber behaviour change Nathan must accept
Final: minor (deferred): forecast cache deadline compared by wall clock; up to an hour stale at fall-back
Final: minor (deferred): cheapWindow.hours between 0 and 0.5 raises IndexError (Amber raised ZeroDivisionError already)
Final: minor (deferred): currency reports "$" before the tariff is read
Final: minor (deferred): tariff with ALL.ALL but no seasons gets no price (Tesla requires at least one season)
Final: minor (deferred): endHour doc wording says window "may run to" it; code bounds only the start (inherited from Amber docs)
Final: minor (deferred): spec non-goal "changing the policy engine" vs doesConditionMatch guard; note in PR description
Final: Ruling: declined-to-judge items (getCloudJson concurrency, holiday-year seasons, 30-min precision, additive ALL, per-access refresh cost, string hours) — existing code or accepted spec calls — none
