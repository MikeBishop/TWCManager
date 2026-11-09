### Task 11: Docs, changelog, running-app check, CI handoff

**Files:**
- Create: `docs/modules/control_HTTP_API/getChargingPoints.md`, `getVehicles.md`, `getVehicle.md`, `getPolicyState.md`
- Modify: `docs/modules/Control_HTTP.md` (API table rows, linked like `saveSettings`), `CHANGELOG.md` (v1.4.1 Features)
- Integration: `tests/integration/test_api_endpoints.py`

- [ ] **Step 1: Write the four API docs** following `getPricing.md`'s sections (Introduction, Format of request with a cURL example, Format of response with an example and a field list). Capabilities, not internals; times are epoch seconds; `fingerprint` explained as "changes when the page's layout would; clients can ignore it". No "charger" for the wall unit.

- [ ] **Step 2: Changelog line** under `## v1.4.1 - Upcoming` → Features: `(@MikeBishop) - The home page (both themes), Policy, Vehicles and vehicle pages keep themselves current while open. The home page lists every charging point (Gen2 and Gen3 TWCs, and EVSEs TWCManager controls through the car); new APIs getChargingPoints, getVehicles, getVehicle and getPolicyState carry what those pages show`.

- [ ] **Step 3: Integration tests** in `tests/integration/test_api_endpoints.py`:

```python
@pytest.mark.parametrize("path", ["/getChargingPoints", "/getVehicles", "/getPolicyState"])
def test_live_page_apis(api_get, assert_json_response, path):
    response = api_get(path)
    data = assert_json_response(response, 200)
    assert response.headers["Cache-Control"] == "no-store" and len(data["fingerprint"]) == 12

def test_get_vehicle_unknown_is_404(api_get):
    assert api_get("/getVehicle/5YJ3E1EA1KF000009").status_code == 404
```

- [ ] **Step 4: Full checks**

Run: `pytest tests/unit/ -q && node --test tests/js/*.test.js`
Expected: PASS.

- [ ] **Step 5: Running-app check.** Start TWCManager with `etc/twcmanager/.testconfig.json` as the CI job does, then with Playwright load `/`, `/policy`, `/vehicles`, and a `/vehicleDetail/<VIN>` for a car added through the Add vehicle form. For each: no `.live-offline` notice after 4 s; at least one `[data-field]` non-empty; `/` lists the Dummy TWC; set `webControlTheme` to `Default` and repeat `/`. Then stop the server and confirm the notice appears within one interval. Run `pytest tests/integration/ -k "live_page or get_vehicle_unknown"` against it.

- [ ] **Step 6: CI handoff (do not commit).** Write to the scratchpad, for the operator to add to the `unit-tests` job in `.github/workflows/test_suite.yml` after "Run unit tests":

```yaml
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 'lts/*'
      - name: Run JavaScript tests
        run: node --test tests/js/*.test.js
```

- [ ] **Step 7: Commit**

```bash
git add docs/modules CHANGELOG.md tests/integration && git commit -m "Live pages: API docs and changelog"
```
