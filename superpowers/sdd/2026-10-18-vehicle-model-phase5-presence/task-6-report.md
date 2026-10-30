# Task 6 report: Vehicles page, presence and pending commands

Commit on vehicle-model/phase5 (parent 59d6584e). Not pushed.

## Implemented
- HTTPControl.py: `presenceText(master, v)` (global `presence`), `_wanted`, `pendingCommands(master, vin)`, globals registered next to `providerLines`.
- Reconciler: public `said(key, aspect)` accessor.
- vehicles.html.j2: Presence column. vehicleDetail.html.j2: "Pending commands" table or "Nothing pending".
- A5: `Vehicle.summary()` is six keys (vin, name, anonymous, point, lastSeenAge, lastSeenSource); `VehicleRegistry.summaries()` deleted, WebIPC debug dump walks `vehicles()` and prints each summary.
- pendingCommands: one row per open desire (settled, already-satisfied and adopted ones are hidden). First applicable state:
  - in flight: "Sending via BLE (12 s)", plus ", not waking: nothing offered" when `wakeSkipped` is set
  - held: "Waiting: driving"
  - reconciler's logged reason: "Not sent: battery below minChargeLevel", "Not sent: no provider can deliver"
  - never tried: "Not tried yet"
  - paid budget spent: "Not sent: paid request limit reached"
  - not-sent outcome: "Not sent: backoff, retries in 2 min"
  - otherwise: "Last try via BLE: unreachable, 2 min ago" / "Last try via BLE: error (timeout), 5 s ago"
  - what: "Charge limit -> 50%", "Charge limit -> car's own" (RELEASE), "Charging -> start/stop", "Charge rate -> 16 A" (real arrow).
- Presence cell: Home / Probably home / Away.

## Tests
- New: presence column per state (test_vehicles_page); pending in-flight, no-wake, held, not-sent/retry/said/hands-off/budget, last outcome/untried, empty, hidden-when-settled (test_vehicle_detail_page).
- A5 rewrites: test_attachments_and_summary asserts the exact six keys; claims/fields assertions removed; `test_summary_evaluates_a_claim_once` -> `test_summary_evaluates_no_claim`; `test_summary_field_age_is_liveness_aware` deleted (age liveness stays covered by `test_registry_liveness_feeds_age_and_trusted` and the FeedReg test); `test_summaries_sorted_by_key` -> `test_vehicles_sorted_by_key`.
- tests/unit + tests/EMS: 2091 passed, 1 warning (baseline 2084). Black clean.
- TDD: tests written after lib in this task (not literal red-first); presence-cell test failed first on a cell-index mistake and a marks setup, both test-side.

## Lib delta
26,367 -> 26,440 = +73 (git diff --shortstat: +111/-23, of which 15 are template lines). Target was <= 0: missed by 73. Cause: pendingCommands with its fixed vocabulary is ~62 lines after black; A5 saved only ~20 (summary 26 -> 12, summaries 3, offset by WebIPC +1). The audit's ~30-line estimate assumed fewer states; I did not drop states the brief lists. Candidates to recover: drop the paid-budget and not-waking branches (~7), or fold A7/A8 from the audit.

## Parked churn item
Noted, not fixed. The page work does not touch the path, and `presentVehicles` already excludes NOT_HOME cars (homeForLimits), so I could not reproduce RELEASE-set-then-NOT_HERE-cleared per pass from reading alone; needs a repro with a PRESUMED car whose restore is held (Targets._apply / Run.inapplicable).

## Concerns
- "Not sent: nothing offered -- retries when the car is awake" is not producible: `wakeSkipped` exists only on an in-flight attempt and is not stored on the record, so it shows as ", not waking: nothing offered" while sending.
- Raw outcome details can appear ("Not sent: wake held", "error (401)"); no mapping table added to stay small.
- Elapsed text for in flight uses `Attempt.since`, which is plan time, not queue-start time.

## Fix round 1 (review applied in full)
- Deleted the dead old `return {...}` in `Vehicle.summary()`.
- `pendingCommands(master, vehicle)` follows the review's design: one `peek`, no `record()` (a render creates no entries; tested), one guarded outcome line (no separate held branch, so no `lastOutcome` None crash; tested), settled/satisfied rows skipped. Paid-budget, retry-time and wake-skip branches and their imports are gone; `presenceText` is replaced by `PRESENCE_TEXT` and a lambda global. Wording moved into vehicleDetail.html.j2.
- Rendered rows, by state (aspect -> value, then the text):
  - in flight: "Charge limit -> 50% | sending via BLE, started 12 s ago"
  - held (real noteOutcome HELD): "Charging -> start | held: driving via TWC, 0 s ago"
  - reconciler said: "Charging -> stop | hands off: battery below minChargeLevel"; "... | no provider can deliver"
  - last outcome: "Charge limit -> 70% | unreachable via BLE, 2 min ago"; "... | backoff via BLE, 2 min ago"
  - untried (also heldAt set with no outcome): "Charge rate -> 16 A | not tried yet"
  - RELEASE: "Charge limit -> car's own"
  - empty: "Nothing pending"
- Tests: exact == on the new wording; real-hold and heldAt-without-outcome rows added; removed-branch tests dropped; `import time` first.
- Result: tests/unit + tests/EMS 2093 passed. Lib .py lines 26,382 vs 26,367 base = +15 (git diff --shortstat 59d6584e -- lib: +65/-30, which includes about 20 template lines).
