# Live home, Policy and Vehicles pages: design

Status: specced, build deferred (user, 2026-10-30: "a bigger lift than I want to bite off right now").

## Intent

The home page keeps itself current: every 3 s it fetches `/api/getStatus` and `/api/getSlaveTWCs` and drops each value into the element whose id matches. But its charging-station table lists only Gen2 TWCs (`master.getSlaveTWCs()`), so a Gen3 unit or a car charging on an EVSE TWCManager controls through the car never appears; on an install with no Gen2 TWC the table is empty. The Policy, Vehicles and Vehicle details pages are rendered once per load and go stale. The user wants all four pages to stay current while open, on one shared mechanism.

The user's architectural preference drives the shape: **the UI should draw on the same API other clients use**, so the two can't diverge and anything added to a page gets API coverage by default. So each page gets a JSON API of raw values, and the browser turns those values into display text, both on first load and on every refresh.

## Goals

- **Home page, in both themes.** Two home pages are reachable: the Modern theme's (`themes/Modern/main.html.j2`, which the Settings page preselects and the live box runs) and the Default theme's (`themes/Default/main.html.j2` with `showStatus.html.j2`, which the server falls back to when `webControlTheme` has never been saved, per the maintainer's commit `4ba5c7c9`, 2026-08-24). The theme setting changes only the home page; every other page comes from `themes/Default/` under either theme. Both home pages get the same treatment, on the same shared scripts and APIs; each keeps its own layout. Live: the status panel (as today, from `/api/getStatus`, now including scheduled charging amps and the flex start hour, which are rendered once or formatted in page script today) and the "Charge Points" section listing **every charging point** from `master.chargingPoints()`: Gen2 TWCs, Gen3 units and EVSEs controlled through the car. Each entry shows the point's kind, the car it serves, amps offered or targeted, amps drawn, voltage, minimum and maximum; Gen2-only fields (state, protocol version, lifetime kWh, last heartbeat, current and last VIN) are blank for other kinds. The totals stay.
  - **Points come and go live (user).** A car arriving creates a charging point, so a point appearing or going adds or removes its entry in place; it does not reload the page. The list is keyed by point ID: `live.js` adds an entry from a `<template>` for a new ID, removes a gone one, and updates the rest in place.
  - **Icon (user).** In the Modern home page, a TWC point keeps the TWC drawing; a point with no TWC (a car charging on an EVSE TWCManager controls through the car) shows that car's picture, from the same `vehicleImage.js` and compositor the Vehicles pages use. The Default home page's table has no icon column; its rows name the point's kind instead (my call: adding a picture column would change that page's layout, which this work otherwise leaves alone).
  - Both home pages' own polling (`themes/Default/jsrefresh.html.j2`, `themes/Modern/jsrefresh.html.j2`) is replaced by `live.js`.
  - Static: the charge schedule panel and the commands section.
- **Policy page.** Live: the current value feeding each condition (both sides, where a side resolves through `policyValue`), whether each condition and each AND/OR group is true, and which policy is active. Values are recomputed on each poll, as the page does on load today; they may disagree with the active policy until the engine's next check (every `policyCheckInterval`), which the user accepts ("the policy will catch up shortly"). Static: the set of policies, their rules, and the extension-point layout. Those can only change when the config reloads, which restarts the service.
- **Vehicles page.** Static: the list of cars (rows), the add-vehicle form, the groups table and add-group form. Live: everything changeable or dated in a row: presence, watch line, provider lines, last seen (age and source), charge limit (held and car's own), Fleet spend cell; the Fleet spend summary lines above the table; the charge history counts (sessions, kWh).
- **Vehicle details page.** Static: the layout, the VIN-decoded facts, the forms (forget, BLE scan and pair, group membership). Live: name, provider lines, last seen; pending commands; the Fleet spend section (heading, per-type rows with count, cost and last-sent age; telemetry line and per-field counts); charge sessions; the BLE status block (label, since, last attempt, last scan, whether a scan is pending, and which buttons apply). Live BLE status replaces the page's current 3 s `<meta refresh>` while a scan is pending.
- **Reload fallback (user).** Each API response carries a fingerprint of the page's underlying shape. When the fingerprint differs from the one the page was rendered with, the page reloads itself. Losing a half-filled form to that reload is acceptable, because it's rare (user).
- **API coverage by default.** The three endpoints are documented user-facing APIs, like the existing `docs/modules/control_HTTP_API/*.md`.
- **Tests for the display text.** The wording rules that Python unit tests pin today move to JavaScript with them, under a minimal JS test runner (user's choice): Node's built-in `node --test`, with no npm dependencies.

## Non-goals

- Every other page (settings, schedule, graphs, debug, upgrade) stays as it is.
- `/api/getSlaveTWCs` stays, unchanged, for existing users; the home page stops using it.
- The theme setting's name and scope. The user's direction is to narrow it to a "home page theme", since the home page is the only page whose content differs; that is raised with the maintainer separately (ngardiner/TWCManager#747), and this work does not depend on it.
- No push channel (WebSocket or server-sent events). Polling matches the home page and the existing server.
- No layout or wording changes beyond what moving the formatting requires. Today's text is the spec for the JS formatters.
- Adding or removing rows live. A car added or forgotten changes the fingerprint and reloads the page.

## Anti-goals

- **Formatting in two places.** Python must not keep a copy of any wording the JS now produces. Python keeps only the data. Templates render structure and a placeholder for each live value, never the formatted value itself.
- **Polling that slows the control tick.** The handlers read cached state only: `vehicle.latest()` and friends, never `vehicle.read()` or any provider I/O, and no long-held locks.
- **Leaking secrets.** No token, refresh token, client secret or webhook URL in any response. VINs, car names and positions already shown on these pages are fine. Provider read-only reasons are fine.
- **Pages that are blank without the API.** First paint fills from the same API call made at load. If that call fails, the page shows its structure with a visible "can't reach TWCManager" note rather than silently empty cells.

## Constraints

- Python 3.8 (setup.py `python_requires=">= 3.8"`).
- The HTTP server is `HTTPControl.py`'s threaded `BaseHTTPRequestHandler`. Routes are matched by `self.url.path`, and existing APIs are `/api/get<Name>` (`getStatus`, `getSlaveTWCs`, `getPolicy`, ...).
- The front end loads jQuery and Bootstrap through `bootstrap.html.j2`. Scripts live in `lib/TWCManager/Control/static/js/`.
- Lib growth is a red flag (the project's rule). The Python display helpers this replaces (`ageText`, `sourceName`, `providerLines`, `heldLimitText`, `watchLine`, `spendLines`, `carSpend`, `_usd`, `_lastMonth`, `_teleText`, `PRESENCE_TEXT`, the text parts of `pendingCommands`, and the Policy page's HTML string assembly in `do_get_policy`) should leave the lib, with the data they read becoming the API's content.
- User-facing docs: describe capabilities, not internals, and say "EVSE" or "charging station", never "charger", for the wall unit.

## Approaches

1. **Re-fetch the page and copy the live elements in.** Least new code, with no API and no JS formatting. Rejected: it gives other clients nothing, and the user wants the UI and the API to be one thing.
2. **One fragment endpoint per page** (server renders the live pieces, keyed by element id). The user's first lean, then refined by their API-first goal: fragments are HTML, not an API another program can use.
3. **A JSON API of raw values per page, formatted in the browser (chosen).** The page's own refresh is the API's first client. Formatting lives once, in JS, tested with Node's runner. Costs: the formatting rewrite, and adding Node to CI.

The user chose 3, with raw values in the API and display text built in the browser.

## How (decided)

### Endpoints

All three are GET requests returning JSON with `Cache-Control: no-store`.

- `/api/getVehicles`: `{"fingerprint": ..., "spend": {...}, "vehicles": [...], "history": {...}}`. One entry per registry car, in `registry.vehicles()` order, each keyed by `key`.
- `/api/getVehicle/<VIN>`: `{"fingerprint": ..., "vehicle": {...}}` for one car. It returns 404 when the registry doesn't know the VIN, and the page reloads on a 404.
- `/api/getPolicyState`: `{"fingerprint": ..., "active": "<name>", "policies": [...]}`. Each policy lists its leaves in a stable order (a path through its match/condition/value nesting). Each leaf gives the raw resolved `match` and `value` and its truth, and each group gives its truth. It calls `policyValue` and `doesConditionMatch` as the page does today, including the two function macros (`getMaxAmpsForTargetGridUsage()`, `checkScheduledCharging()`); the user chose live values over the engine's last evaluation.
- `/api/getChargingPoints`: `{"fingerprint": ..., "points": [...], "total": {...}}`. One entry per `master.chargingPoints()` point: its ID, kind (its controllers), the car it serves, raw amps offered or targeted and drawn, voltage per phase, minimum and maximum, and the Gen2-only fields where they apply. The total sums as `getSlaveTWCs`' total does today, including a car-side point's desired amps.
- `/api/getStatus` gains the scheduled charging amps (rendered once today) and keeps the flex start hour as a raw value; the page formats "(Flex …)" in `format.js`.

**Field set.** It is everything the three pages show today, as raw data. For example:
- times are epoch seconds (`lastSeenAt`, not an age);
- amounts are numbers in dollars;
- presence is its state name (`HOME`, `PRESUMED`, `NOT_HOME`);
- a provider claim is `{provider, status, commands, readOnlyReason}`, where `readOnlyReason` is the text `TeslaAPI` already returns;
- a pending command is `{aspect, value, inFlight: {provider, since} | null, said, lastOutcome: {kind, detail, provider, at} | null}`;
- the watch is the dict `master.watch.status()` returns, plus the budget;
- spend is the dicts `fleetSpend.month()` and `fleetSpend.car()` return, plus whether a Fleet token is held and whether Fleet Telemetry is enabled (today's `_spendShown`);
- BLE status is the dict `bleStatus(vin)` returns.

The API includes `now` (the server's epoch seconds), so ages are computed against the server's clock, not the browser's.

### Fingerprint

A short string that changes when the page's structure would. It combines the service start time (a restart, which includes any config change) with the page's shape:
- for the Vehicles page, the sorted registry keys, the group names, and whether the spend column shows;
- for Vehicle details, the car's presence in the registry and the group names;
- for the Policy page, the policy names in order;
- for the home page, the start time only: its points are a live keyed list.

The server renders the fingerprint into the page as a `data-` attribute, and the page reloads when a response's differs.

### Front end

- **Templates render structure only.** Each live value is an element carrying `data-field="<path>"` (for example `vehicles.<key>.presence`). Templates stop calling the removed helpers.
- **`static/js/format.js`** holds every display rule as pure functions taking raw values. It is today's wording exactly, for example ages ("12 s ago", "5 min ago", "3 h ago", "2 d ago", "never"), the display names for sources, "$0.006" below one cent, "1 request" versus "2 requests", "approx." on telemetry, the watch line, provider lines, held limit "50% (80%)" or "—", and the pending-command text. It is written as an ES module the page loads, and that Node can import for tests.
- **`static/js/live.js`** is one shared poller. On load and then every interval, it fetches the page's API, compares the fingerprint, and sets each `data-field` element's text from the formatter for its field. The Policy page's leaf and group truth also toggle the existing `leaf-true`/`leaf-false` and `group-true`/`group-false` classes, and the active badge and highlight move to the active policy. It never touches form controls.

### Tests

- **Python:** the API's data (fields present, raw types, no secrets, fingerprint changes when the shape changes), and that the handlers don't call provider I/O. The existing page tests that assert exact wording move to JS.
- **JavaScript:** `tests/js/*.test.mjs` run under `node --test`, one test per wording rule carried over from the Python tests. Examples: `test_vehicles_page.py`'s singular "request" and three-decimal small amounts, the telemetry "approx." line, last month's total appearing only when it's non-zero, and the watch line.
- **CI:** `.github/workflows/test_suite.yml` gains a step with `actions/setup-node` (an LTS release) running `node --test tests/js/`. The repo has no package.json today, and this adds none.

## Left to the builder

- Module boundaries in Python. One natural cut is a `Control/Views.py` with a function per endpoint, called by the handler and by the template context for the fingerprint.
- Exact field names and nesting, within the rule above (raw values, everything shown today).
- The leaf-path scheme for policy leaves.
- How `live.js` maps a `data-field` to its formatter.
- Whether the charge-history and groups tables on the Vehicles page get `data-field` hooks or stay fully static (their counts change only after a charge session).
- The API docs' layout, following the existing control_HTTP_API pages.

## Calls made after the builder check (not the user's)

- **Policy structure, one walker.** One Python function walks a policy's match/condition/value nesting and yields each group and leaf with its path. The template draws the structure from it and the API reports state from it; there is no second walker. A path indexes the raw nested lists, so a single-item group that the page draws as a bare leaf still occupies its slot. The extension-point layout (boxes and "no policies" markers) is template-only; the API carries no category.
- **Sections that come and go are shown and hidden, not reloaded.** An element may carry `data-show="<path>"`, and `live.js` hides it while that field is false or empty: the Fleet spend section, "Nothing pending", the BLE block, which BLE button applies, the scan-pending state. Only the fingerprint's shape forces a reload.
- **Lists that grow and shrink are redrawn as a block.** Pending commands, Fleet spend request types and telemetry fields: the container carries `data-list="<path>"` and a row formatter name, and `live.js` replaces its rows each poll from `format.js`'s row formatter. Rows hold no form controls, so nothing in progress is lost.
- **`format.js` is a classic script** that defines one global and, when `module` exists, also exports itself, so pages load it with an ordinary `<script>` tag and Node's tests `require` it. No `.mjs`: Python 3.8's `mimetypes` may not map it to JavaScript. Tests are `tests/js/*.test.js`, CommonJS, run with `node --test tests/js/`.
- **Scripts load per page,** in the templates that use them (both home pages, Policy, Vehicles, Vehicle details), not in the shared `bootstrap.html.j2`.
- **Access** is the same as the existing `/api/get*` routes. `/api/getVehicle/<VIN>` is a prefix match on `/api/getVehicle/`.
- **Log volume:** the Policy API runs the same checks the page runs on load, now every 5 s while the page is open. If `doesConditionMatch` can be called without its per-check log line, the API does so; otherwise the extra debug lines are accepted.

## Calls made in writing this (not the user's)

- Polling every 5 s on the Policy and Vehicles pages; the home page keeps its 3 s. Polling pauses while the tab is hidden (`document.visibilityState`) and resumes with an immediate fetch.
- A failed poll keeps the last values, marks the page as not live with a small notice, and retries on the normal interval.
- The new JS is plain DOM code, not jQuery, so `format.js` can run under Node unchanged.
- The VIN-decode table on Vehicle details stays in the template: it's static, derived from the VIN, and not state.
- Ages are computed from the server's `now`, not the browser's clock.
- The endpoint names follow the existing `/api/get<Name>` pattern.
