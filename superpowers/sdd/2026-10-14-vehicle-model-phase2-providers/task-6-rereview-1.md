# Task 6 re-review 1 (3f89dea..70b53af, tests only)

Verdict: APPROVED. I1, I2 and m1 are addressed, and the diff adds nothing broken.

Scratch copy: `scratchpad/probe-t6r` (from `wt-vm2` at 70b53af). Baseline `test_teslaapi_providers.py`: 12 passed.

| Finding | Mutation (my re-run) | Result |
|---|---|---|
| I1 | M4: `get_car_api` guard `elif not slot.usable("read")` disabled | `test_a_paused_slot_sends_nothing` fails (only that test) |
| I2 | M2: Fleet `canRead` gate replaced by `ownerSlot.empty()` | `test_a_refused_owner_read_hands_reads_to_fleet` fails (only that test) |
| m1 | M10: `available(READ_*)` uses `usable("command")` | `test_a_data_only_fleet_token_reads_but_never_commands` fails (only that test) |

Extra check: with the Fleet `ready()` gate (`TeslaAPIProviders.py:85`) changed to `ownerSlot.empty()`, `test_fleet_reads_only_when_owner_cannot` and the new m1 test fail.

Notes:
- I1 now registers `ANY, ANY` and asserts `call_count == 0`, so it no longer depends on a real network failure.
- The I2 test asserts the Concern 1 counts: Owner online 1, Owner data 1, Fleet online 0, Fleet data 1. The next poll makes no Owner call and Fleet data reaches 2. The comment covers m3.
- No new test passes vacuously. The diff touches tests only.
- m2 remains deferred to Task 10. m3 needs no fix.
