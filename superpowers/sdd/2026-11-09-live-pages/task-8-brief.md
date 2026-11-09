### Task 8: Vehicles and Vehicle details pages go live; display helpers leave the lib

**Files:**
- Modify: `themes/Default/vehicles.html.j2`, `themes/Default/vehicleDetail.html.j2`, `HTTPControl.py` (remove `ageText`, `SOURCE_NAMES`, `sourceName`, `providerLines`, `heldLimitText`, `watchLine`, `_spendShown`, `_usd`, `_lastMonth`, `_teleText`, `spendLines`, `carSpend`, `PRESENCE_TEXT`, `pendingCommands` and their template globals; drop now-unused imports)
- Modify: `tests/unit/test_vehicles_page.py`, `tests/unit/test_vehicle_detail_page.py`

**Interfaces:**
- Consumes: `pageFingerprint` global (Task 4), `vehiclesView`/`vehicleView` shapes, formatter names (Task 6), hook vocabulary (Task 7).
- Template rules:
  - New template global `spendShown()` → `Views.spendShown(master)`.
  - Vehicles: spend lines `<p data-field="spend" data-format="fleetLine" data-show="spend.fleet">` and the same with `telemetryLine` / `spend.telemetry`; the spend `<th>`/`<td>` stay server-conditional on `spendShown()` (it is in the fingerprint). Vehicle details' heading/telemetry lines use path `vehicle` with `spendHeading` / `spendTelemetry`. Each registry row keeps its static VIN/link/picture; its cells become `data-field="vehicles.<key>.<field>"` with formats `presence`, `watchLine`, `providerLines` (cell `style="white-space: pre-line"`), `lastSeen` (path `vehicles.<key>`), `heldLimit`, `spendCell` (path `vehicles.<key>`); name `data-field="vehicles.<key>.name"`. History counts `data-field="history.<key>.chargeSessions"` / `.totalkWh`. Groups table and forms unchanged.
  - Vehicle details: `<meta refresh>` removed. When `registry.get(vin)` is set: name, providers, last seen, pending (`<tbody data-list="vehicle.pending" data-row="pendingRow">` plus `<p data-show="vehicle.pending" data-show-if="isEmpty">Nothing pending</p>`; add `Format.isEmpty(list)`), Fleet spend section wrapped in `data-show="vehicle.spend"`, types `data-list="vehicle.spend.types" data-row="spendTypeRow"`, fields `data-row="fieldRow"`, charge sessions `data-field="vehicle.chargeSessions"`. BLE block rendered when `'TeslaBLE' in master.modules`: label/since/attempt/last scan via the `ble*` formats; the scan form wrapped in `data-show="vehicle.ble.canScan"`, its two submit buttons (`Scanning…` disabled, `Scan for vehicle`) each in a wrapper toggled by `vehicle.ble.scanPending`; scan-blocked text `data-show="vehicle.ble.scanBlocked"`; pair vs re-pair buttons in wrappers toggled with `data-show-if="bleRepair"` and a new `Format.bleNotRepair`. Scripts and `Live.start({urls: ["/api/getVehicle/<vin>"], interval: 5000, fingerprint})` emitted only in this branch.
  - When the registry doesn't know the VIN: VIN facts, charge sessions (raw int), groups; no BLE block, no live scripts.

- [ ] **Step 1: Rewrite the Python page tests** to structure only. Keep, adjusted to the new markup: `test_list_renders_registry_rows` (link, `Unknown car on TWC 8244`, `Charge history`, add form, `data-field="vehicles.<VIN>.presence"` present), `test_names_and_error_are_escaped` (form error escaped; `TestCar` and `<script>x</script>` absent from server HTML), add/forget/group/local-mgmt tests unchanged. Replace `env()` globals with `pageFingerprint`/`spendShown` lambdas and `bleModule` flag. Delete the wording tests now covered in `tests/js/format.test.js` (`test_age_text`, provider-text, presence column, watch line, spend lines, pending-text) and the pending-selection tests now in `test_live_views.py`. Add:

```python
def test_page_carries_fingerprint_and_starts_live():
    html = render(master())
    assert 'Live.start' in html and pageFingerprint(m, "vehicles") in html
    assert '/static/js/format.js' in html and '/static/js/live.js' in html

def test_scan_pending_no_longer_meta_refreshes():
    assert 'http-equiv="refresh"' not in render_detail(master(), status(scanPending=True))

def test_unknown_vin_page_does_not_poll():  # Review Focus 2
    html = render_detail(master(), None, vin="5YJ3E1EA1KF000009")
    assert "Live.start" not in html and "Vehicle VIN" in html

def test_display_helpers_left_the_lib():
    import TWCManager.Control.HTTPControl as H
    for name in ("ageText", "sourceName", "providerLines", "heldLimitText", "watchLine",
                 "spendLines", "carSpend", "PRESENCE_TEXT", "pendingCommands", "_usd"):
        assert not hasattr(H, name)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_vehicles_page.py tests/unit/test_vehicle_detail_page.py -v`
Expected: FAIL (`Live.start` missing; helpers still present).

- [ ] **Step 3: Rewrite both templates; remove the helpers and their globals**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q && node --test tests/js/*.test.js && grep -rn "ageText\|providerLines\|carSpend\|pendingCommands\|PRESENCE_TEXT" lib/ || echo clean`
Expected: PASS, `clean`.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: Vehicles and vehicle pages fill from their APIs"
```

---

