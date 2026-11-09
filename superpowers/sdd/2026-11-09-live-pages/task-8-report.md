# Task 8 report: Vehicles and Vehicle details pages go live

## Commits
- 4e3cc33b Live pages: Views.py black-clean (R11; black only, no logic change)
- 9801949c Live pages: Vehicles and vehicle pages fill from their APIs

## What was implemented
- `vehicles.html.j2`: loads format.js + live.js and calls
  `Live.start({urls: ["/api/getVehicles"], interval: 5000, fingerprint: {{ fingerprint("vehicles")|tojson }}})`.
  Spend lines are `<p data-field="spend" data-format="fleetLine|telemetryLine" data-show="spend.fleet|spend.telemetry" hidden>`.
  The spend `<th>`/`<td>` stay server-conditional on `spendShown()` (`{% set fleet, telemetry = spendShown() %}`).
  Each registry row keeps its static picture/VIN/link; cells are `data-field="vehicles.<key>.<field>"` with
  `presence`, `watchLine`, `providerLines` (`style="white-space: pre-line"`), `lastSeen` (path `vehicles.<key>`),
  `heldLimit`, `spendCell` (path `vehicles.<key>`), name `vehicles.<key>.name`. History counts are
  `history.<key>.chargeSessions` / `.totalkWh`. Groups table and forms unchanged.
- `vehicleDetail.html.j2`: meta refresh removed. Scripts + `Live.start({urls: ["/api/getVehicle/<vin>"], interval: 5000, fingerprint: fingerprint("vehicle", vin)})`
  only when `registry.get(vin)` is set. In that branch: name/providers/last seen hooks, pending
  `<tbody data-list="vehicle.pending" data-row="pendingRow">` + `<p data-show="vehicle.pending" data-show-if="isEmpty">Nothing pending</p>`,
  Fleet spend section in `<div data-show="vehicle.spend">` (heading via `spendHeading`, telemetry via `spendTelemetry`,
  types `data-list="vehicle.spend.types" data-row="spendTypeRow"`, fields `data-row="fieldRow"`), charge sessions
  `data-field="vehicle.chargeSessions"`. BLE block only when the registry knows the VIN and `'TeslaBLE' in master.modules`:
  `ble*` formats, scan form in `data-show="vehicle.ble.canScan"`, the two scan buttons each in a span toggled by
  `vehicle.ble.scanPending` (second with `data-show-if="not"`), scan-blocked `<small>` with `data-show="vehicle.ble.scanBlocked"`,
  pair/re-pair spans with `data-show-if="bleRepair"` / `"bleNotRepair"`. Unknown VIN: VIN facts, raw charge-session int, groups,
  no BLE block, no scripts.
- `HTTPControl.py`: removed `ageText`, `SOURCE_NAMES`, `sourceName`, `providerLines`, `heldLimitText`, `watchLine`,
  `_spendShown`, `_usd`, `_lastMonth`, `_teleText`, `spendLines`, `carSpend`, `PRESENCE_TEXT`, `pendingCommands` and
  their template globals; added `spendShown=lambda: Views.spendShown(master)` next to `fingerprint`. Dropped now-unused
  imports (NOT_HOME, PRESUMED, known, newerReading, RULES, satisfied, COVERED). pyflakes on HTTPControl.py: no new
  warnings vs base. Black-clean (both files).
- `Format.isEmpty` / `Format.bleNotRepair` already existed in format.js (Task 6); format.js and live.js untouched.

## Design decisions to review
- Every `data-show` element is rendered `hidden` initially; live.js's immediate first poll reveals what applies
  (no Python copy of the show predicates). Nested shows inside an already-hidden parent are not marked hidden.
- The BLE block is wrapped in `<div data-show="vehicle.ble" hidden>` so an entry with no BLE status (e.g. a VIN-less
  anonymous car) shows nothing rather than throwing formatters.
- Fleet spend heading and telemetry block use `data-show="vehicle" data-show-if="spendHeading"/"spendTelemetry"`
  (empty string = hidden), matching the old `{% if spend.heading %}` / `{% if spend.telemetry %}` without adding a predicate.
- data-list tables cannot carry the old `<td>&nbsp;</td>` spacer columns (one `<td>` per formatter string), so the
  pending/types/fields tables lost their spacer cells; their header rows dropped spacers to stay aligned.
- Removed the `bleStatus` template global too: its only user was vehicleDetail's old head/BLE block; not in the brief's
  list, but leaving it would be dead code. Easy to restore if wanted.
- Detail test helper is now `render(m, vin=VIN)` (status argument removed since BLE status arrives by the API);
  the brief's sample tests were adapted to that helper (`render(withBLE(master()))` etc.) with the same assertions.

## Tests
Kept/adapted: list rows (link, Unknown car on TWC 8244, Charge history, add form, `vehicles.<VIN>.presence` hook),
escaping (form error escaped; `TestCar` and `<script>x</script>` absent), add/forget/group/local-mgmt tests, BLE panel
presence/absence, charge sessions (hook for known VIN, raw int for unknown), scan/pair button structure, scan-blocked hook,
pending list hook, no-desired-state-on-render, spend hooks. Held-limit adoption test kept as data-level
(`vehiclesView` heldLimit dicts). Added the four brief tests (fingerprint+live on both pages, no meta refresh,
unknown VIN doesn't poll, helpers left the lib).
Deleted (covered by tests/js/format.test.js or test_live_views.py): age text, provider text/capability/token,
presence column, watch line, spend line/column wording, last month, small telemetry, all pending wording/selection tests,
types/fields wording.

### TDD evidence
RED: `/root/venv/bin/pytest tests/unit/test_vehicles_page.py tests/unit/test_vehicle_detail_page.py -q`
-> 21 failed, 10 passed (`'providerLines' is undefined` x7, `'spendLines' is undefined` x7,
`'bleStatus' is undefined` x6 since the new env no longer supplies the old globals; `assert not True` for helpers still in the lib).
GREEN: same command -> all pass; focused with test_live_views: 64 passed.

### Full suites
- `/root/venv/bin/pytest tests/unit -q` -> 2683 passed, 1 warning (PytestUnraisableExceptionWarning from a
  TemporaryFile deallocator; present on base too: 2700 passed, 1 warning before this task).
- `node --test tests/js/*.test.js` -> 27/27 pass.
- `/root/venv/bin/black --check lib/TWCManager/Control/Views.py lib/TWCManager/Control/HTTPControl.py` -> unchanged.
- Brief's grep `ageText|providerLines|carSpend|pendingCommands|PRESENCE_TEXT` over lib/ (excluding format.js) hits only
  `data-format="providerLines"` in the two templates: that is the JS formatter name, not a Python helper. No Python hits.

## Files changed
- lib/TWCManager/Control/Views.py (black only)
- lib/TWCManager/Control/HTTPControl.py
- lib/TWCManager/Control/themes/Default/vehicles.html.j2
- lib/TWCManager/Control/themes/Default/vehicleDetail.html.j2
- tests/unit/test_vehicles_page.py
- tests/unit/test_vehicle_detail_page.py

## Concerns
- Not exercised in a browser (no DOM test harness); hook correctness rests on structure tests plus format/live unit tests.
- The brief's literal grep "|| echo clean" would not print `clean` because of the data-format attribute names (see above).

## Fix round 1
1. (R14) Scan-blocked text is either/or with the scan button again: `Format.bleScanBlocked` returns "" when `b.canScan`
   (it only shows when `!canScan && scanBlocked`), and the `<small>` in vehicleDetail.html.j2 is now driven by
   `data-show="vehicle.ble" data-show-if="bleScanBlocked"`. The wording didn't change. New format.test.js assertion:
   canScan true + scanBlocked "bluetoothctl not installed (install the bluez package)" gives "". The detail page structure test now
   expects the new data-show hook.
2. ble* formatters and predicates are null-guarded: bleLabel/bleSince/bleAttempt/bleLastScan/bleScanBlocked return "",
   bleRepair/bleNotRepair return false for a null status. New test "ble formatters tolerate no BLE status".

Commands and output:
- `node --test tests/js/*.test.js`: tests 28, pass 28, fail 0
- `/root/venv/bin/pytest tests/unit/test_vehicle_detail_page.py -q`: 18 passed
