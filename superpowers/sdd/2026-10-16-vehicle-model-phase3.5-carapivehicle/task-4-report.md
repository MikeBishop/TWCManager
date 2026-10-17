# Task 4 report

Status: DONE. Worktree wt-vm35, branch vehicle-model/phase3.5, base c02e333, commit: see `git log -1`.

## Changes
- TWCSlave.py:132 comment: "registry (sorted VIN) order" (was "registry order is list order").
- TeslaAPI.py:13: unused `Any` import removed.
- VehicleEndpoints.py:83-85 docstring and Targets.py header: checked; already accurate after Task 3 (no CarApiVehicle wording), no edit.
- CHANGELOG.md:23: now says that for a car the held limits already hold, the older `chargeLimits` entry is dropped without a warning; other cars' entries migrate as usual (matches HeldLimits._migrate and test_both_keys_present_the_store_wins).
- tests/unit/test_registry_callers.py::test_no_caller_outside_teslaapi_reaches_for_its_list extended (brief's regex over lib/TWCManager, html, tests/integration, tests/API) plus an assertion that `git grep "\.forget("` in lib/TWCManager yields exactly one line, with ifUnattached=True (HTTPControl.py:121). No test deleted or rewritten otherwise.

## Orphan sweep
Every def in the 13 lib files changed since db47522, `git grep -nw` over lib and html, excluding comments/defs: no orphans. Only zero-caller hits: HTTPControl do_GET/do_POST/log_message (BaseHTTPRequestHandler overrides) and numCarsAtHome in TeslaAPI and HomeAssistant (policy-reachable properties, kept per policy reach). Nothing deleted.

## Verification
- Full suite: 1782 passed, 1 xfailed. tests/integration collects 212. black --check lib: clean.
- Guard grep over the four trees and docs: no hits.

## Line check
- lib total: 27,123 (Task 4 delta 0, expected about -5; the sweep found nothing to delete). From db47522 (27,270): -147 overall. Over the 26,750 target by 373.
- `git diff --shortstat db47522 -- lib`: 13 files changed, 459 insertions(+), 606 deletions(-)
- `git diff --shortstat origin/main -- lib`: 59 files changed, 8493 insertions(+), 4474 deletions(-)
- awk (removed > added) exit 0.
- Per-task deltas: not independently re-measured here beyond the total; the cumulative -147 is below the plan's ledger (about -203 for Tasks 1-4).

## Live check (for the controller; not run)
Follow brief Step 6, items 1-9 verbatim: prepare (record box HEAD, back up settings.json to ~/twcmanager-settings.json.bak-phase3.5, check jq chargeLimits/chargeRateControl, logLevel for INFO8, empty git diff, no request.headers logging, pause watchdog); deploy via git bundle of <box HEAD>..vehicle-model/phase3.5 and restart; restart with the car plugged in and asleep (anon: session, BLE wake/limit/amps/start, zero Car API lines for vehicles/<VIN>, vehicle_data, wake_up, command/); surfaces (getSlaveTWCs fields, Vehicles tab, Debug send-command list, no Forget on the listed car, policy page); 00:00/05:00 cycle; depart and return; restart with the car away (heldLimits unchanged, no chargeLimits); count paid calls with the journalctl grep (expect 0); roll back.
