# Slim Task 12a re-review 2 (fix round 2)

Reviewed 5a42a6d..8b22849 in wt-vm3. Read-only; every mutation was reverted and the tree is clean. tests/unit: 1669 passed.

| Finding | Addressed? | Test fails without the fix? |
|---|---|---|
| N1 (mode-2 ride wake) | Yes (Reconciler.py `_startWanted`) | Yes, but only when the whole `any(...)` clause is removed. Weakening `not p.local` or `declares(WAKE)`, or replacing the predicate with True, leaves it green: in mode 2 the start has no candidate at all. |
| N2 (stop to an asleep car) | Yes (TeslaAPIProviders.py:146-154, Outcome.py NOT_SENT) | Yes: both new tests fail with the check disabled. |
| N3 (`keep` age bound) | Yes (TWCMaster.py:236) | Yes: the reworked flap test fails with the line removed. |

## Extra N1 test (verified by a throwaway probe, deleted)
Mode 1. A policy limit of 50 on a car with an unknown limit, plus a start. The start's only ready provider is a local scripted BLE (ready only for START_CHARGING). The limit's provider is a scripted non-local FleetAPI, ready for everything except START_CHARGING. Run a few passes with the clock advanced 61 s each. Assert the Fleet provider got no `wake`.
- It fails when `not p.local` is dropped (a local provider that declares WAKE rides the wake), and when the predicate is replaced with True.
- A second parametrisation pins `declares(WAKE)`: the start provider is non-local, ready only for START_CHARGING, and its caps omit WAKE (a HomeAssistant-like one). It fails when `declares(WAKE)` is dropped. The mode-1 BLE case alone does not pin that half.

## Free online check before a Fleet stop
- `car.is_awake` goes through `get_car_api(path=VIN, checkReady=False, provesOnline=False)`: a GET of `vehicles/{vin}`, which is free. It never POSTs a wake.
- It is cached for 120 s (`lastVehicleAwakeTime`), and a telemetry "asleep" answers with no request.
- It runs only when `slotFor("command")` is usable, so the no-token refusal makes no request.
- The detail "asleep, not charging" is in NOT_SENT: no paid budget and no send gap.
- A stop attempt never wakes: `allowWake` is False for a stop, and the ride only applies to a limit. The tests assert no `wake_up` and no `charge_stop`.

## New issues
- Minor, TeslaAPIProviders.py:146-154: an asleep answer cached for up to 120 s can be wrong if the car wakes inside that window (the TWC offer wakes it). The stop is then skipped and settled, and it re-sends only on a newer reading. It is bounded by the reading and RETRY, and it is main parity (`ready()` had the same 2-minute cache). No action.
- Minor (test): only the whole-clause mutation fails the N1 test. See above.

APPROVED
