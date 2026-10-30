# Task 7 report: docs, CHANGELOG, PR notes, whole-branch checks

Commit 9dfb12f4 "Document event-based presence" on vehicle-model/phase5 (not pushed). No lib changes.

## Files changed
- docs/PolicyCustomization.md: rewrote the Charge Limits at-home section (home/away/probably home rules, Gen2 00 filters, home learning, no-home behaviour, wake and restore rules, residuals), the -1 text, and the `numCarsAtHome` / `minBatteryLevelAtHome` entries.
- docs/Settings.md: new Home Location section; the stop-command line points to the rules.
- docs/modules/Vehicle_HomeAssistant.md: presence now from the shared rules, zone-without-coordinates note, radius default.
- CHANGELOG.md (1.4.0): extended the radius/home entry; 3 Features lines; 4 Bugfixes lines plus the residuals line.
- PR notes (outside the repo): pr-notes.md in this directory.

## Addendum items and where documented (D = docs, C = CHANGELOG, P = pr-notes)
- Home learning (TWC-named fresh fix or BLE fix; never first fix; car-only install must set it; one WARNING; no-home cars not home/rated): D PolicyCustomization, D Settings, C radius entry, P (f).
- Policy always has a limit; -1 is a release applied like any limit; departure restore separate: D PolicyCustomization, C, P.
- No raise-wake while offered 0 A: D, C, P.
- Charging point's own commands never gated: D, C, P.
- "Plugged" for car-addressed start/amps: D (summary), P (full wording); C says commands wait until plugged or confirmed home.
- Gen2 unplug filters, 60 s debounce, INFO lines, n=2: D, C, P. Link grace and plugged-run guard are in P only (too fine for users).
- VIN-less attribution, 00-probe deletion, Gen2 plug counts only while point reports a plug, no vehicles[0] fallback (h): C, P.
- Paid budget counts paid requests actually made: P only (internal).
- New INFO logging: C, P (m).
- Removed endpoints 404: C, P (d). 5/20/45 reads stay: C, P.
- Vehicles page Presence column, Pending commands, per-field summary gone from debug dump: C, P.
- Known residuals (guest car, rejected VIN, RELEASE/NOT_HERE churn): D, C (first two), P.
- Size: P (26,531 -> 26,198).
- Parity non-append hunks (7, with reasons): P.

## Verified in code
Presence.py decide/applicable/learnHome/_STRONG, TWCSlave.unplugStep (constants 60/60/300), Targets.onDeparture and TWCSlave queueing the 5/20/45 checkDeparture tasks, Reconciler log lines, TeslaAPI paid-request log, Telemetry/TeslaMate logChange (pluggedIn, state, geofence), HTTP templates (Presence on vehicles.html.j2, Pending commands on vehicleDetail), test_presence 404 row.

## Checks
- tests/unit + tests/EMS: 2093 passed, 1 warning (matches baseline).
- tests minus API and integration: 2102 passed, 1 xfailed, 1 warning.
- black --check lib: clean (90 files).
- Parity diff vs 044e5262: appended rows plus 7 plumbing hunks, all listed in pr-notes.md; 6 lines removed, all in those hunks.
- Greps: no `ast.unparse`, `removeprefix`, `functools.cache`, `zoneinfo`, `match` statements in the lib diff. Retired names (`pluggedCars`, `anonymousCars`, `CORRELATE_WINDOW`, `_telemetryPluggedIn`, `PresenceAttribution`, `vehicleIsDefinitelyHome`, `update_location`, `plugVIN`, `.atHome`, `_scheduleBlocksStart`) appear nowhere in lib, html or docs. Only tests mention them: test_presence.py:775 (`/api/checkArrival` 404 assertion, intended) and tests/unit/test_reads_no_wake.py:79 (a test still named `test_update_location_zero_forces_a_fresh_read`, body tests `read("lat", 0)`).
- `from __future__ import annotations` and `list[...]` annotations exist in Gen3TWCs.py / Gen3TWC.py, but not in this phase's diff (pre-existing; 3.8 CI was green on phase 4).

## Lib total
26,198 (Phase 5 base 26,531: -333; main 23,180: +3,018). Target 26,140 missed by 58.

## Concerns
- The brief's PR-notes list (a)-(m) was taken from global-constraints.md; there is no (i). 
- test_reads_no_wake.py:79 keeps a stale test name containing a retired method name (harmless; rename if wanted).
- Docs say "Probably home" cars wait for a limit until plugged in or confirmed home; this follows applicable() (HOLD "not known here"), not a behaviour I could exercise on hardware.
- The Gen2 filters are tuned on n=2 and documented as such.
