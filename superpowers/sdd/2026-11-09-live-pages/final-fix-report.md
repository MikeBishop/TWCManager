# Final whole-branch review: fix report

Commits (branch feat/live-pages, not pushed):
- ce61cb61 Live pages: round point max amps, fix total docs, drop stray div (findings 2-4)
- 379af8e0 Live pages: Vehicles page addresses rows by position (finding 1)

## Finding 1: dotted keys in Vehicles page hook paths

- `themes/Default/vehicles.html.j2`: vehicle rows now use `vehicles.{{ loop.index0 }}.<field>`.
  Order matches: the template loops over `registry.vehicles()`, and `Views.vehiclesView` builds its
  list from the same `master.vehicleRegistry.vehicles()`, which returns `sorted(self._vehicles)`
  (VehicleRegistry.py:107-109). The fingerprint covers that ordered key list, so if the set changes
  the page reloads.
- Charge history had the same problem: `history.{{ vehicle }}` used the settings "Vehicles" key,
  and `history` was a dict, so you can't address it by position. Changed `_settingsShape` (Views.py)
  so `history` is a list in sorted-key order, each entry `{key, chargeSessions, totalkWh}`. The
  template loops over `master.settings["Vehicles"].keys()|sort`, which is the same order, and its
  rows now use `history.{{ loop.index0 }}.<field>`. The fingerprint already covers historyKeys.
  Updated docs/modules/control_HTTP_API/getVehicles.md (example and description).
- vehicleDetail.html.j2: every hook is a fixed `vehicle.*` path, with no data-derived segments.
  Nothing to change. policy.html.j2 paths use positional indexes and generated node ids
  ("0-1"), so they are safe too.
- Tests (tests/unit/test_live_views.py):
  - `_lookup` re-implements live.js's rule (key, else id, else numeric index).
  - `dottedMaster()` uses the Vehicles-page fixture plus an anonymous car with key
    `anon:Gen3TWC-192.168.1.50`, a history record `legacy.record`, and Fleet + telemetry spend.
  - `test_vehicles_hooks_match_the_api_with_dotted_keys` resolves every data-field/show/list/keyed-list
    path against `vehiclesView` and checks every data-format/show-if/row name exists in format.js.
    It also checks that each row's index points to that row's own vehicle (anonymous Gen3 car,
    VIN car) and that the history row points to its own record.
  - `test_vehicle_detail_hooks_match_the_api` does the same against `vehicleView`, with a BLE status
    that has every field, so all BLE and spend paths are covered.
  - `test_live_pages_divs_balance` counts `<div` and `</div>` in policy, vehicles, vehicleDetail and
    showStatus.
  - The dotted-key test fails against the old template (checked).
  - Updated existing assertions in test_vehicles_page.py (positional paths) and
    test_live_views.py (history is now a list).
- Browser check (Playwright/Chromium, script at
  /tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/final-fix/browser.py):
  rendered the Vehicles page with the dotted fixture and served /api/getVehicles from vehiclesView.
  After the first poll:
  - `Unknown car on TWC Gen3TWC-192.168.1.50 Home Not watched: off 0 s ago via created —`
    (live cells filled)
  - `legacy.record 1 2` (history row filled)
  - The only console errors came from CDN jQuery being blocked in the sandbox.

## Finding 2: showStatus `.maxAmps` float noise
Added `data-format="round2"` to the `.maxAmps` span shown for non-Gen2 rows.

## Finding 3: getChargingPoints.md `total`
The doc now says `total` is getSlaveTWCs' total row in the same form: it sums the Gen2 TWCs, and
its `lastAmpsOffered` also counts the amps offered to points known only through the car. Gen3 TWCs
are not included.

## Finding 4: policy.html.j2 stray `</div>`
Removed the extra `</div>` before `</body>`. The template now has 10 `<div` and 10 `</div>`, and
the test above guards it.

## Commands
- `/root/venv/bin/pytest tests/unit -q` -> 2699 passed, 1 warning
- `node --test tests/js/*.test.js` -> 33 tests, 33 pass, 0 fail
- `/root/venv/bin/black --check lib/TWCManager/Control/Views.py` -> 1 file would be left unchanged

## Concerns
- `/api/getVehicles` `history` changed shape from a dict keyed by VIN to a list of entries with
  `key`. It is new on this branch, so no released client depends on it. The docs are updated.
