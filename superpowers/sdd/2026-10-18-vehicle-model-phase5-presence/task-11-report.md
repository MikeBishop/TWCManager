# Task 11 report: DONE

Commit: "Wake a car only when it is expected to charge". Lib +6 (33+/27-). Full unit+EMS: 2138 passed (2131 + 7 new).

Design: Belief.whyQuiet(master, vehicle) returns the reason (or None = expected to charge); replaces allowWake, idle, the start's ride in `wakes`.
Plugged/arriving = pluggedNow unknown-or-True, or the limit-apply cell SENDs; unknown plug (PRESUMED) counts as charging; offer test skipped for arriving.

Expectations changed (all follow rule 3: unknown battery => wakes; lowerings of a car still charging wake):
- test_limit_reconciler: 3 start tests' name lists (lower now wakes; wakes fail asleep), unknown-limit test renamed (wakes, reads, then sends).
- test_presence x2, test_sleeping_car x2 (wake added), test_teslaapi_readonly_gate x1 (wake added).
- Parity: row 2 (BLE-only lowers: wake+send each), row 5/6 ble_plus_fleet (BLE runs 2->4; paid still (0,0,1), $0.001),
  row 7 telemetry adopted (runs [50]->[None,50]), arrive-then-D restore, 2026_10_12 x2 ([90,50]->[90,None,50]), vinless ambiguous (wake allowed),
  owner/fleet off-car asleep (2 set_charge_limit -> 0 commands: the wake fails, wake hold keeps commands out; the any(paid record) check is skipped for asleep),
  row 23 spent re-arm (old: 4 failed limit sends, then start with paid (1,1,5); new: 0 commands + one failed wake_up paid (0,1,0), then after waking
  set_charge_limit + charge_start, paid (1,2,2), limit 50). Real cost change: a sleeping Fleet car whose lower leaves it charging pays a $0.02 wake instead of $0.001 sends.
Fixture plumbing (not expectations): shared limit_reconciler setup gives the car battery 60 (new param) so lowers to 50 are quiet where wake isn't the subject;
7 start tests set battery 40 (limit above battery so the start charges); 3 charging_reconciler tests battery 40; 2 sleeping tests battery 80 (quiet lower).
No restart/mode-1 lift row moved. New tests (7) in test_limit_reconciler.py; quiet-lower, pending-higher, unknown-battery already passed on old code (pin behaviour).
Concern: the sleeping-car lowering with unknown battery now wakes (Task 8 "leave it alone" holds only when battery is known).

## Fix round 1
Commit "An unplugged car at home is not expected to charge". Dropped `arriving` (and its imports); minor 1: a release with nothing held uses the known limit;
renamed the spent-rearm parity row (now test_a_lower_that_wakes_a_refusing_car_rides_the_start_once_it_wakes); arrive/D row asserts full runs [None, 50, 90];
off-car asleep row asserts lastOutcome.detail == "wake held". Two new tests (unplugged-at-home lower not woken; release-with-nothing-held), both fail before / pass after.
Full: 2140 passed. Lib vs pre-task base: +4. No parity row moved again.
