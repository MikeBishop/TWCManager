# Task 9 report

Commit: b6a4d5f4 (vehicle-model/phase3.5, on ad029963). Not pushed.
Tests: 1867 passed, 1 xfailed (baseline 1863; +4 new tests, 2 changed).
Lib delta: 27360 -> 27420 (+60 lines; mapping ~15, providerLines ~20, TeslaAPI reason helpers ~20, telemetry claim 4). Over the +10 target because items 5 and 6 add logic; items 1-4 alone would be about +30 (the 9-entry mapping dict is itself ~12 lines).

## Items
1. Tier column removed from both pages; _tierOf and summary()["tier"] removed. Nothing reads it: WebIPC dumps str(summary) as debug text only, no JSON /api. Vehicle.tier property kept (inlined) because ~30 test assertions use it; lib no longer reads it.
2. providers joined with <br>.
3. SOURCE_NAMES + sourceName() in HTTPControl, template global; used for provider names and "via X". Also maps TeslaAPI -> "Tesla API".
4. Header "Charge limit set by TWCManager"; cell "80% (car's own limit: 90%, restored when released)" (held first, outside in parens); em dash otherwise.
5. providerLines(master, vehicle): status shown unless "listed"; capability "commands"/"read-only (reason)", omitted when paired/unproven already implies it. Reasons from new TeslaAPI.ownerReadOnlyReason(car) (ownerCommandsAllowed now calls it, same conditions) and fleetReadOnlyReason(). No HTTP; computed at render.
6. TelmetryBase._observe (live branch only) claims the car: claim(source, False, "reports", keepsAlive=False), once per car. Chose keepsAlive=False: live reports already refresh lastSeen, so a car actually reported stays; keepsAlive=True would pin a car forever after the feed stopped reporting it (claims are never dropped), defeating the 30-day forget. Retained messages never reach this branch, so they never create/revive/claim. Not added to any provider walk. Shown as "TeslaMate: reports, read-only".
7. vehicleDetail.html.j2 emits <meta http-equiv="refresh" content="3"> in <head> only while status.scanPending; bleStatus now evaluated once in the head (moved from the body). PRG 302 unchanged.

## Test map
- tests/unit/test_vehicles_page.py: test_list_renders_registry_rows (changed: BLE name, new held wording/header, no Held limit), test_held_limit_reads_the_vin_store_after_adoption (changed wording), new test_providers_one_per_line_with_source_names_and_no_tier (items 1-3, 6 display), new test_provider_capability_text_for_tesla_cloud_and_ble (5)
- tests/unit/test_vehicle_detail_page.py: detail test now asserts no "Tier"; new test_scan_pending_page_refreshes_itself_only_while_pending (7)
- tests/unit/test_registry_vehicle.py: summary asserts no "tier" (changed); test_summary_tier_from_single_claim_evaluation renamed test_summary_evaluates_a_claim_once
- tests/unit/test_telemetry_registry.py: new test_a_live_report_lists_the_source_on_the_car_but_retained_does_not (6, incl. ages out)

## Sample row
Before: VIN | <car> | managed | TeslaBLE (paired), OwnerAPI (listed) | 0 s ago via TeslaAPI | 90% (holding 80%)
After:  VIN | <car> | BLE: paired<br>Owner API: read-only (car requires signed commands)<br>TeslaMate: reports, read-only | 0 s ago via Tesla API | 80% (car's own limit: 90%, restored when released)
