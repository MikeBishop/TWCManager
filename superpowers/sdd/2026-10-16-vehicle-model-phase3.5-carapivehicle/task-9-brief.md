# Task 9: Vehicles page readability (user UI notes, 2026-10-17)

Branch: vehicle-model/phase3.5 (on top of Task 8's result). Templates `lib/TWCManager/Control/themes/Default/vehicles.html.j2`
and `vehicleDetail.html.j2`, helpers in `lib/TWCManager/Control/HTTPControl.py`, summary in
`lib/TWCManager/Vehicle/Registry/Vehicle.py` (`summary()`, `_tierOf`).

1. **Drop the "Tier" column** (values "managed"/"observed") on both pages: the provider list already says who can command
   the car. Remove `_tierOf`/`tier` from `summary()` if nothing else reads it (grep lib, templates, /api JSON, tests; if an
   /api endpoint returns `tier`, keep the field in the JSON and say so).
2. **Providers one per line** instead of comma-separated (e.g. `<br>` between entries), both pages.
3. **Source names, not class names**, wherever the page shows a provider or the "Last seen … via X" source: TeslaMate (not
   TeslaMateVehicle), Fleet Telemetry (FleetTelemetryMQTT), BLE (TeslaBLE), Owner API, Fleet API, Home Assistant,
   TWC (Gen2TWC), Gen3 Wall Connector (Gen3TWC) — one small mapping used by both pages, falling back to the raw name.
   Display only; internal names, logs and settings are unchanged.
4. **Replace "Held limit"** with a column a user understands at a glance. With Task 8, an entry exists only while
   TWCManager is holding the car at a limit. Header: "Charge limit set by TWCManager". Cell: "50% (car's own limit: 80%,
   restored when released)" while held; "—" otherwise. Keep the wording short; adjust if the exact phrasing reads badly.

Tests: update/add template-rendering tests (tests/unit/test_vehicles_page.py and similar) for each change; map any changed
test. Lib should not grow beyond the mapping (target ≤ +10 lines net). No behaviour change outside the pages.

5. **Show capability, not "listed"** (user, 2026-10-17). Each provider line should say whether that channel can command the car
   or only read it — e.g. "Owner API: read-only (car requires signed commands)", "Owner API: commands", "Fleet API: commands",
   "Fleet API: read-only (token lacks command scope)". The claim's static status "listed" (TeslaAPI.py ~256-257: both
   OwnerAPI and FleetAPI claim with "listed") tells the user nothing, since an unlisted car wouldn't show the line at all.
   Derive commands/read-only from the claim's existing `commands` value (already in `summary()`), with a short reason where
   one is cheaply available (Owner: `command_signing` not "off", latched refusal, slot refused; Fleet: no command scope /
   slot refused). Keep statuses that carry information (TeslaBLE "paired"/"unproven", HA's) and append the capability where
   it differs from what the status implies. Don't add per-request work: computed when the page renders, no HTTP.

6. **List the passive sources too** (user, 2026-10-17: "why is TeslaMate not listed?"). TeslaMate (TeslaMateVehicle via
   Telemetry) and Fleet Telemetry (FleetTelemetryMQTT) feed the registry but hold no claim, because TelemetryProvider was
   deleted in 3214a285 (it declared only passive reads, so it never entered a provider walk). The page's provider list is
   built from claims, so these never appear. Make each telemetry source that reports a car show on that car's list, e.g.
   "TeslaMate: reports (read-only)". Smallest correct way: the telemetry module claims the car when it first reports it
   (commands=False, status "reports"); decide whether that claim should keep the car alive (a car TeslaMate actively reports
   is real — keepsAlive is probably right, but check the 30-day forget rules and say what you chose). Do NOT re-add a
   provider to the command/read walk. Retained MQTT messages must still never create or revive a vehicle (Phase 1 rule).

7. **Scan button never resets** (user, 2026-10-17). POST /vehicle/localMgmt (scan) → 302 → the detail page renders
   `status.scanPending` true ("Scanning…", disabled) and nothing ever re-renders it; the server state clears when the scan
   finishes (TeslaBLE.runPendingScans) or after SCAN_PENDING_MAX, but the page is static. Keep Post/Redirect/Get (the 302 is
   right; a 205 would leave the page showing stale state). While `status.scanPending`, have vehicleDetail.html.j2 refresh
   itself every few seconds (a `<meta http-equiv="refresh" content="3">` emitted only while pending, or an equivalent tiny
   script), so the button returns with the result once the scan ends. Template-only; a rendering test that the refresh is
   present while pending and absent otherwise.
