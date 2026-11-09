### Task 10: Both home pages list every charging point, live

**Files:**
- Modify: `themes/Default/showStatus.html.j2`, `themes/Default/main.html.j2`, `themes/Default/jsrefresh.html.j2`, `themes/Modern/main.html.j2`, `themes/Modern/jsrefresh.html.j2`, `static/js/status.js`
- Test: `tests/unit/test_live_views.py` (template render checks)

**Interfaces:**
- Consumes: `chargingPointsView` shape (Task 3), formatters (Task 6), `live.js` (Task 7), `pageFingerprint(master, "home")`.
- Both home pages: `Live.start({urls: ["/api/getStatus", "/api/getChargingPoints"], interval: 3000, fingerprint})`; Modern adds `["/api/getActivePolicyAction", "activePolicyAction"]`. `getStatus` itself is unchanged: its `ScheduledCharging.amps` already carries the scheduled amps, and `scheduledChargingFlexStart` the flex hour.
- `jsrefresh.html.j2` (both): polling removed; keeps the Charge Now click handler; gains a `Live.onData` hook carrying today's non-text side effects (Charge Now button label/disabled; Modern: consumption colour, `chargeNowAmpsText`, `chargeNowTimeEndText`, policy-action button classes and help texts, from `data.activePolicyAction`).
- Default status panel: each `<div id=...>` becomes `data-field="<key>"`; Scheduled Charging Amps `data-field="ScheduledCharging.amps"` (no more `{{ scheduledAmpsMax }}`); start hour `data-format="scheduledStart"`.
- Default table: `<tbody data-keyed-list="points" data-template="point-row">`; the row template's first cell is `data-field=".controllers" data-format="pointKind"` followed by the point's TWC ID (`.gen2.twcid`, `blank`); State/Version/Lifetime kWh/Last Heartbeat/VINs from `.gen2.*` with `blank` / `secondsSince` (the " sec" suffix stays static text inside a `data-show=".gen2"` span); Max Amps `.maxAmps`, Offered `.ampsOffered`, In Use `.ampsDrawn`, voltage `.volts` with `volts`. VIN spans keep class `VINClick`, no `onClick`. Totals row from `total.*`.
- Modern "Charge Points": heading `Charge Point<span data-field="points" data-format="pluralS">`; `<div data-keyed-list="points" data-template="point-card">`; the card shows the TWC drawing in a wrapper `data-show=".local"` and `<img class="vehicleImage" data-image hidden>` in a wrapper `data-show=".local" data-show-if="not"` (add `Format.not`); version/state `.gen2.*`, charge time `.gen2.chargingSince` with `chargeTime`, offered/drawn/lifetime/volts, VINs, SoC `.soc`, last limit `.chargeLimit`. `chargerAvailAmps` = `total.lastAmpsOffered` with `fixed2`; power cells use `powerValue` + `powerUnit` spans; surplus via `surplus*`.
- `status.js`: `loadVIN` replaced by a delegated click on `.VINClick` opening `"/vehicleDetail/" + encodeURIComponent(text)` when non-empty. Modern loads `compositor.js`, `vehicleImage.js`, `format.js`, `live.js`.

- [ ] **Step 1: Write the failing tests** (render each theme's `main.html.j2` through `CreateHTTPHandlerClass(master)`'s environment with `webControlTheme` set)

```python
@pytest.mark.parametrize("theme", ["Default", "Modern"])
def test_home_page_lists_points_live(theme, mixed_master):
    html = renderHome(mixed_master, theme)
    assert 'data-keyed-list="points"' in html and "/api/getChargingPoints" in html
    assert "getSlaveTWCs" not in html and "setTimeout(request" not in html
    assert pageFingerprint(mixed_master, "home") in html

def test_default_home_names_the_kind_and_has_no_picture(mixed_master):
    html = renderHome(mixed_master, "Default")
    assert 'data-format="pointKind"' in html and "vehicleImage" not in html

def test_modern_home_draws_a_car_for_a_point_without_a_twc(mixed_master):
    html = renderHome(mixed_master, "Modern")
    assert "data-image" in html and "/static/js/vehicleImage.js" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v -k home`
Expected: FAIL.

- [ ] **Step 3: Rewrite the templates and scripts**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q && node --test tests/js/*.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: both home pages list every charging point, live"
```

---

