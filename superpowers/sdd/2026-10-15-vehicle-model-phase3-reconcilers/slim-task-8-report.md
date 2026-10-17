# Slim Task 8 report: provider declarations as data

**Status:** DONE
**Commit:** cf63e52 (on vehicle-model/phase3, parent ccbe58c)
**Tests:** full suite `tests --ignore=tests/API --ignore=tests/integration`: 1551 passed, 1 xfailed (1454 at ccbe58c; +97 new, mostly the parametrized parity test)
**Lib line delta:** +132 / −92 = **+40 net** (12 files). The plan's row expected about −45 for the tables alone ("provider tables and probe removal −90", and the probe went in Task 6). The table conversion itself is about net 0 (each `declarations()` body becomes a class dict). The + comes from the wake-scope fix (TeslaAPI +14, TeslaTokenSlot +2), the carry-forwards (Desired +10, Outcome +3), and `suppressedFor`/`CLOUD_SUPPRESSED` (+15).

## What changed

- `Provider`: `DECLARATIONS = {}` and `SUPPRESSED = None` class tables. `declarations()` returns `self.DECLARATIONS`. Added `CLOUD_SUPPRESSED = {"ble_only": COMMANDS, "localStops": {STOP_CHARGING}}`. Added `suppressedFor(provider, condition)`: a provider with a non-dict `SUPPRESSED` (None, a test double or a Mock) gets `{}` only when `local is True`, and `CLOUD_SUPPRESSED` otherwise, so it fails closed.
- Each provider has a class `DECLARATIONS`, equal to its old `declarations()` output and pinned literally in the test:
  - Gen2 and Gen3: `SUPPRESSED = {}`.
  - TeslaBLE: `{"api_only": ALL}`.
  - Owner, Fleet, HA and telemetry: `CLOUD_SUPPRESSED`.
  - `ready()` is unchanged. `attempts()` and HA's override are untouched.
- `Suppressions`: `conditions()` returns `{commandPolicy}`, plus `"localStops"` when `chargeStopMode` is 2 or 3. `suppressed()` checks the explicit setting, then `any(cap in suppressedFor(p, c) for c in conditions())`. `_localStops` was folded into `conditions()`.
- `TeslaTokenSlot`: `SCOPES["wake"]`, `SCOPE_LABELS["wake"] = "waking the car"`, and `RETIRED_ON_REFUSAL = {"command", "wake"}`.
- `TeslaAPI`:
  - `_paidPost(..., purpose="command")`: a 403 calls `reportScopeRefused(purpose, refused=True)`. For `purpose="wake"` it returns `Outcome(UNREACHABLE, "wake refused")`.
  - `wakeOutcome` checks `slot.usable("wake")` right after `slotFor("command")`, before the backoff and the free online check. It passes `purpose="wake"` and returns the refusal directly, without the "will try again" tail or the `firstWakeAttemptTime` stamp.
  - Legacy `wakeVehicle` (live until Task 13 via `car_api_available`) now also returns False when `not slot.usable("wake")`. Without this a later paid wake could reach the refused token.
  - `setTokens`, `clear` and `restore` already reset `refusedPurposes`, so a new token lifts the refusal (tested).
- Carry-forwards:
  - `Outcome.NOT_SENT` gains "no vehicle" and "no provider".
  - `DesiredStore.noteOutcome` returns False for `aspect is None`.
  - `noteOutcome` calls `free.failure` only for an outcome that is not `isNotSent`. A free-channel failure needs a request to that channel.

## Tests

- New `tests/unit/test_provider_tables.py`:
  - `test_order_ready_and_available_match_the_rule_the_tables_replace`: 7 install shapes × commandPolicy {unset, prefer_ble, ble_only, api_only} × chargeStopMode {1, 2, 3}, all with real provider instances.
    - Shapes: gen2; gen2+ble; gen2+owner+fleet; gen2+ble+fleet; full gen2+ble+owner+fleet+ha+telemetry; gen3+owner+fleet; gen3+ble+ha.
    - For every capability it builds `ordered`, `candidates`, `candidates(amps=4)`, and per provider `suppressed`/`ready`/`available`. It does this once with the new `Suppressions.suppressed` and once with the ccbe58c rule copied verbatim into the test (`legacySuppressed`), and asserts the two are equal.
    - It passed at ccbe58c too, which is expected: it is a parity test.
  - `test_expected_order_on_a_full_install`: literal ccbe58c candidates for setAmps below the TWC floor, stop, wake and readCharge, at five policy × stop-mode points.
  - `test_tables_match_the_declarations_they_replace`, `test_a_provider_without_a_table_is_suppressed_by_locality`, `test_suppressions_come_from_the_tables`: the brief's tests, plus a Mock with no `local` attribute (fails closed) and the `conditions()` values.
  - `test_a_403_on_wake_refuses_wakes_only` counts `wake_up` POSTs and free GETs:
    - The first wake returns UNREACHABLE "wake refused" after 1 `wake_up`.
    - A second wake returns the same, with still 1 `wake_up` and no extra free `vehicles/{vin}` GET.
    - `setAmps` is DONE, `usable("command")` stays True, and Fleet stays ready for stop.
    - Legacy `wakeVehicle` returns False with still 1 `wake_up`.
    - A new token lifts `usable("wake")`.
  - `test_a_command_403_still_refuses_commands`.
- `tests/unit/test_outcome_desired.py`:
  - `test_a_worker_error_that_made_no_request_counts_against_nothing[no vehicle|no provider]` checks that `paidAt` is None, `paidRetryDue` is false, `lastSentAt` is 0, and `free.failingSince`/`lastAttemptAt` and `lastFreeAt` are untouched.
  - `test_a_debug_one_shot_report_changes_nothing`.
- Suppression doubles adjusted:
  - `test_provider_order.ble()` and the TeslaBLE `P` in `test_vehicle_priority.py` get `SUPPRESSED = {"api_only": C.ALL}`. Without it the name-based api_only rule is gone and the two api_only tests fail; they did before the adjustment.
  - `test_provider_outcomes_local.py` uses `Mock(local=False, SUPPRESSED=None, ...)`.

### Fail-before (at ccbe58c with the new tests, before any lib change)

```
FAILED test_provider_tables.py::test_tables_match_the_declarations_they_replace   AttributeError: type object 'Gen2TWCProvider' has no attribute 'DECLARATIONS'
FAILED test_provider_tables.py::test_a_provider_without_a_table_is_suppressed_by_locality   AttributeError: Mock object has no attribute 'local'
FAILED test_provider_tables.py::test_suppressions_come_from_the_tables   AttributeError: 'Suppressions' object has no attribute 'conditions'
FAILED test_provider_tables.py::test_a_403_on_wake_refuses_wakes_only   Outcome(kind='refused', detail='403') != Outcome(kind='unreachable', detail='wake refused')
       (log: "token lacks the vehicle_charging_cmds scope, needed for charge commands"; "Car API wake C failed (refused 403). Will try again in 1800 seconds.")
FAILED test_outcome_desired.py::test_a_worker_error_that_made_no_request_counts_against_nothing[no vehicle]   'no vehicle' not in NOT_SENT
FAILED test_outcome_desired.py::test_a_worker_error_that_made_no_request_counts_against_nothing[no provider]  'no provider' not in NOT_SENT
FAILED test_outcome_desired.py::test_a_debug_one_shot_report_changes_nothing   ValueError: unknown aspect None
7 failed, 107 passed
```

After the lib change and before the doubles were adjusted, `test_provider_order.py::test_api_only_suppresses_ble_for_everything` and `test_vehicle_priority.py::test_api_only_walks_fleet_without_ble` failed as predicted (the TeslaBLE double had no table).

## Concerns

1. **Free-failure guard is broader than the two details.** `free.failure` is now skipped for every `isNotSent` outcome, including a free provider's `"rules: ..."` early return, not only "no vehicle"/"no provider". I judged this correct: a rules outcome made no BLE request, so it should not start the fallback timer toward Fleet. No existing test covers a free rules outcome. Task 9 should confirm this matches its rules.
2. **A command 403 does not retire wakes.** It still refuses `"command"` only, so a token refused for commands (same scopes as wake) could still spend one $0.02 wake that 403s. In practice `slotFor("command")` returns None after a command 403, and `wakeOutcome` uses that chooser, so the new path sends no wake. The legacy `wakeVehicle` also uses `slotFor("command")`, so it is covered too. I did not change this; I flag it in case a future wake path picks the slot another way.
3. **Lib delta is +40, not negative.** The tables themselves are about net 0. The plan's −90 row included the BLE probe, which Task 6 already removed.
4. **Ordering inside a provider.** Gen3 `ready()` now reads `self.DECLARATIONS` directly. Owner and Fleet `ready()` still call `self.declarations()`, which returns the same object.
