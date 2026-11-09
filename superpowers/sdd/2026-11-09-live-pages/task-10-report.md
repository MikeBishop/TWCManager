# Task 10 report: Both home pages list every charging point, live

Commit: 2bea4356 "Live pages: both home pages list every charging point, live"

## What I implemented
- Default `showStatus.html.j2`: the status panel's `<div id=...>` elements are now `data-field="<key>"`. Scheduled Charging Amps reads `ScheduledCharging.amps` (no more `{{ scheduledAmpsMax }}`), and the start hour uses `data-format="scheduledStart"`. The points table is `<tbody data-keyed-list="points" data-template="point-row">` with a `<template id="point-row">` holding one `<tr>`: pointKind + `.gen2.twcid` (blank), gen2 state/version/lifetimekWh (blank), `.maxAmps`, `.ampsOffered`, `.ampsDrawn`, `.volts` (volts), and a heartbeat `secondsSince` inside a `data-show=".gen2"` span with a static " sec". The VIN spans keep `VINClick` and have no onClick. The totals row reads `total.*`. I removed the per-row dropdown `id`, which would otherwise be duplicated across rows.
- Default `main.html.j2` loads format.js and live.js. In Default `jsrefresh.html.j2`, polling is gone. A Live.onData hook sets the Charge Now button value and the cancel button's disabled state, plus the navbar server time. It calls Live.start with getStatus + getChargingPoints, a 3000 ms interval and `fingerprint("home")`. The chargeNow click handler is kept.
- Modern `main.html.j2`:
  - Power cells use powerValue + powerUnit spans, surplus uses surplusWatts/surplusUnit/surplusAmps, and chargerAvailAmps reads `total.lastAmpsOffered` with fixed2.
  - The heading is `Charge Point<span data-field="points" data-format="pluralS">`.
  - The cards are a `<div data-keyed-list="points" data-template="point-card">` built from a template. Each card has the TWC SVG in a `data-show=".local"` wrapper and `<img class="vehicleImage" data-image hidden>` in a `data-show=".local" data-show-if="not"` wrapper (`Format.not` already existed). It also shows gen2 ID/version/state, a chargeTime from `.gen2.chargingSince`, offered/drawn, lifetime, `.volts.0/1/2`, gen2 VINs, `.soc` and `.chargeLimit`.
  - The page loads compositor.js, vehicleImage.js, format.js and live.js.
  - The policy buttons and help texts are no longer rendered from `activeAction` on the server.
- Modern `jsrefresh.html.j2`: Live.onData sets the consumption colour, the Charge Now label and cancel button state, chargeNowAmpsText, chargeNowTimeEndText (minutes remaining come from `data.now`, not the browser clock; built from text nodes plus `<br>`), and the policy-action button classes and help texts from `data.activePolicyAction`. It also sets the server time. Live.start adds `["/api/getActivePolicyAction", "activePolicyAction"]`. The click handler is kept.
- `status.js`: `loadVIN` is replaced by a delegated `.VINClick` click handler. When the span's text is non-empty, it opens `/vehicleDetail/` + encodeURIComponent(text) in a new tab, as `loadVIN` did. The old code pointed at the wrong route, `/vehicleDetails/`.
- `HTTPControl` "/" route: dropped `scheduledAmpsMax` and `activeAction` from the template context. Nothing else uses them.

## Tests
- I added `renderHome(m, theme)` to tests/unit/test_live_views.py, plus the brief's three tests and `test_home_hooks_match_the_apis[Default|Modern]`. That last test checks that every data-field/show/keyed-list path in each rendered page resolves against real getStatus + chargingPointsView data, with relative paths resolved against the gen2 point. It also checks that every data-format/show-if name is defined in format.js.
- RED: `pytest tests/unit/test_live_views.py -q -k home` gave 4 failed. The pages rendered, but the assertions on `data-keyed-list="points"`, `pointKind` and `data-image` failed, as expected before the change.
- GREEN: the same command gave 6 passed. `/root/venv/bin/pytest tests/unit -q` gave 2693 passed, with 1 warning that is unrelated to this task and does not appear when the new tests run on their own. `node --test tests/js/*.test.js` gave 28 passed, 0 failed. black --check on HTTPControl.py passes.

## Concerns / notes
- Following the brief, Amps Offered on both pages shows `.ampsOffered` raw, so you see 16.333 where the old getSlaveTWCs-based page showed a value rounded to 2 places.
- The navbar server time (`currentServerTime` from getStatus, which contains `&nbsp;`) used to be written with `.html()` by the old polling. It is now set in both onData hooks with `&nbsp;` replaced by U+00A0, which keeps that behaviour without changing the shared navbar.
- The VINs on both pages come from `.gen2.*`, so a car-only point shows no VIN text; on Modern, its picture identifies it.
- Modern's leftover `{{ twcid }}_durationVal`/`_ampsVal` ids were already rendered with an empty twcid, because the variable was scoped to the old loop. I left them unchanged.
- I have not tested in a real browser. There is no DOM test harness, so the hooks are checked statically against the APIs.

## Fix round 1 (R15)
1. I added `Format.round2(v)`, which returns `String(Math.round(v*100)/100)`, or "" for null. Amps Offered uses it on both pages. Old getSlaveTWCs rounded only `lastAmpsOffered` per TWC; `reportedAmpsActual` was a raw float, and the totals were already rounded by `slaveTotals`. So In Use and the totals stay as they were.
2. Default Max Amps now shows `.gen2.maxAmps` for Gen2 rows, and `.maxAmps` in a sibling span with `data-show=".gen2" data-show-if="not"` for other rows. Modern shows no max, so nothing changed there.
3. Car-only entries now show `.vin`, in a `VINClick` span with `data-show=".gen2" data-show-if="not"`. On Default it is on the C: line, on Modern the VIN line.
4. I added `Format.whole(v)`, which returns `String(Math.round(v))`, or "" for null. Modern's `.volts.0/1/2` use it.
- New tests: node tests "round2 ..." and "whole ...". Unit tests `test_home_rounds_offered_and_names_the_car_without_a_twc[Default|Modern]` and `test_default_max_amps_is_the_twcs_own_for_a_twc`. The existing hook-path test still checks that every path and formatter resolves.
- `node --test tests/js/*.test.js`: pass 33, fail 0
- `/root/venv/bin/pytest tests/unit/test_live_views.py -q -k home`: 8 passed
- `/root/venv/bin/pytest tests/unit -q`: 2696 passed, 1 warning, the same unrelated warning as before
- I did not touch live.js.
