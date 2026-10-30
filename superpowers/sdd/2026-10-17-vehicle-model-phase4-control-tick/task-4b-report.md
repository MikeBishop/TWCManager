# Task 4b report: the rate before the start

Status: DONE. Commit 6b89f9fd on vehicle-model/phase4 (BASE a84079f4). Not pushed.

## Implementation
`lib/TWCManager/Vehicle/Reconcile/Reconciler.py`:
- `_ORDER = (CHARGE_LIMIT, AMPS, CHARGING)` (was CHARGE_LIMIT, CHARGING, AMPS); new `_STOP_ORDER = (CHARGE_LIMIT, CHARGING, AMPS)`.
- `pass_()` picks the order for each car: `_STOP_ORDER` when the car's CHARGING desire is `False` (a stop), else `_ORDER`.
- The rule: put a stop first and a start last. A car with no CHARGING desire gets `_ORDER`, which only matters for the limit and the rate. The plan order is the order attempts are submitted in, and each queue's low table is FIFO (`VehicleCommandQueue._next`), so on one worker the rate runs before the start. Stops are already high priority in the queue, but if the rate went first on an idle worker, the worker would pick it up before the stop arrived. Keeping a stop first avoids that.
- These are unchanged: the limit-then-start gate (`LIMIT_THEN_START_GAP`, the check in `plan`), paid caps, send gaps, wake rules and provider choice. `plan()` itself is untouched.

## Tests / results
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1933 passed, 1 xfailed, 1 warning**. That is the 1928 baseline plus 5 new test cases.
- The warning (seen with `-o addopts="" -rw`, because setup.cfg's addopts has `--disable-warnings`): `tests/unit/test_enphase_ems.py::TestEnphaseGetters::test_get_generation_returns_float`, a urllib3 `InsecureRequestWarning` (an unverified HTTPS request to api.enphaseenergy.com). It was there before this task and has nothing to do with it.
- Black run on Reconciler.py (no changes needed).

## TDD evidence
RED, before the lib change, `-k rate_due`: 3 failed, 2 passed.
- `test_a_start_goes_after_the_rate_due_on_the_same_pass[ble]` and `[fleet]` got `['startCharging', 'setAmps']`, expected `['setAmps', 'startCharging']`.
- `test_a_real_fleet_start_goes_after_the_rate_due_on_the_same_pass` got `charge_start` before `set_charging_amps`.
- The two `test_a_stop_never_waits_behind_the_rate...` cases passed. They are regression guards: stop-first is today's behaviour and must survive the reorder.

GREEN, after the change: all 5 pass. One existing test then failed because it pinned the old order (mapped below); it was updated.

## Files changed
- lib/TWCManager/Vehicle/Reconcile/Reconciler.py (+5/-3)
- tests/unit/test_charging_reconciler.py:
  - 5 new test cases;
  - a `twc=True` parameter on the `fleetOnTwc` helper, so a Fleet car can be off a TWC (PLUMBING-ONLY: the default is unchanged; Fleet never sets a rate that a local TWC covers);
  - `import pytest`, `AMPS` and `prov` imports;
  - 1 updated assertion.
- tests/unit/test_command_path_parity.py: comment only (row 26 now cites Task 4b). No assertion or count changed.

## Lib delta
27,090 before, 27,092 after (+2; target is at most +5). `git diff --shortstat a84079f4 -- lib`: 1 file changed, 5 insertions(+), 3 deletions(-).

## Test map
- New:
  - `test_a_start_goes_after_the_rate_due_on_the_same_pass[ble|fleet]`: ScriptedProvider BLE and Fleet, real reconciler walk.
  - `test_a_real_fleet_start_goes_after_the_rate_due_on_the_same_pass`: real TeslaAPI, Fleet token, requests_mock. POSTs are `set_charging_amps` then `charge_start`.
  - `test_a_stop_never_waits_behind_the_rate_due_on_the_same_pass[ble|fleet]`: `stopCharging` before `setAmps`.
- Rewritten: `test_an_offer_starts_the_car_from_the_heartbeat` expected `["startCharging", "setAmps"]` and now expects `["setAmps", "startCharging"]`. This is INTENTIONALLY CHANGED by Task 4b's own requirement (the user's 2026-10-17 request, the brief's named behaviour change). It is not one of (a)–(f): the brief adds it.
- Helper: `fleetOnTwc(..., twc=True)` is PLUMBING-ONLY (the default keeps every existing caller as it was).

## Parity counts and order
- I dumped every request in `test_command_path_parity.py` (all requests_mock history, including HA service calls, plus every real TeslaBLE `tesla-control` run) with a throwaway pytest plugin.
- I ran it on a scratch checkout of a84079f4 and on the task tree. Across 51 tests, 326 HTTP requests and 12 tests with BLE runs, the sequences were **identical**.
- So no request count and no command order changed in any row. Row 26 still runs wake, set-limit 70, wake, set-amps 32, wake, start.
- The plugin and the scratch checkout were removed afterwards.

## Self-review
- The change is small and comes with tests both ways. YAGNI: no new knobs. `plan()` is unchanged, so the limit-before-start gate still holds; `test_start_waits_five_seconds_after_a_limit_write_and_wakes` and `test_fleet_start_sends_the_limit_first` still pass.
- No background processes were left running. The extra worktree was removed.

## Concerns
- The guarantee covers submission order, so it holds on one worker: the same provider, or two providers that share a queue. If the rate and the start go to different workers (for example the rate via Fleet on the cloud queue and the start via BLE on the ble queue), the two threads can still race. The brief's tests cover the same-provider case. Closing the cross-queue case would need the start to wait for an AMPS attempt that is in flight, which is a behaviour change the brief did not ask for.
- The Gen2 TWC's own target (`p.module is None`, set by the distributor) is not a reconciler attempt, so this ordering does not apply to it.
