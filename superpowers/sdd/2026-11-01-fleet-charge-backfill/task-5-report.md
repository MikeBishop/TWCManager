# Task 5 report: triggers for the snapshot poll

Status: DONE_WITH_CONCERNS (all tests pass; concerns are behavioural notes for review)

Commit: 507401de `feat: open a snapshot poll on load steps, wakes, commands and stale beliefs` (BASE 2c94fc75)

## What was done

lib/TWCManager/Vehicle/Watch.py (+86 -22):
- `_deaf(vin)` became `_fleet(v)`: `fleetOnly(master, v, deaf)` using the watch's own `TWICE` knowledge. Used by `chargingAmps`, `_visit`, `loadSample`, `_stale` and `commanded`.
- `suspect(vin, at, why, step=False)`: `_suspect[vin]` is now `(since, stepAt)`. `since` stays the earliest. `stepAt` is the latest load-step time while the suspicion is open. `step=True` replaces the `why.startswith("load step")` coupling. `_poll` passes `stepAt` as `startHint` when `snap.stamp - stepAt <= STEP_SECS` (the ledger already ignores a hint later than the stamp).
- `commanded(vin, sentAt)`: suspects the car from `sentAt` when `_fleet(v)`.
- `loadSample`: tracks `_sampleAt`, so `first` = the previous sample's time (the step's first sample, the one before the held one). Gating on `where != NOT_HOME and back` is unchanged. Non-Fleet-only cars follow the old path exactly, including the 1200 s / 300 s throttle. Fleet-only cars:
  - an up step on an awake or unknown car (the existing `maybe` set) suspects it from `first`, with `step=True` and no throttle;
  - a down step on a car that is `HOME_CHARGING` or has `believedAmps > 0` suspects it the same way;
  - an up step on a car believed asleep calls `_wakeCheck`. This submits the existing `"status"` job now (skipped if one is in flight), using `_source` for the check, so the call runs on a worker. It suspects from `first` only if the answer leaves the car in `AWAKE`.
- `_stale(now)`, called on every sample: with `subtractChargerLoad` on, it checks `getChargerLoad() > getConsumption() + LoadStep.threshold`. When two samples in a row are over, it suspects every Fleet-only car with `believedAmps > 0`, with T = the first of the two. The "EMS reporting consumption" condition is the existing `consumptionValues` guard at the top of `loadSample`.
- `_visit`:
  - Computes `fleet` once, up front.
  - Splits the event conditions into `woke`, `arrived`, `plugged` and `opened`. For Fleet-only cars, arrival, plug-in and door no longer ask a read. The wake still asks, because that ask carries the unchanged `fix` (location) read. Any of the four suspects the car. T is the arrival's `since`, the plug-in mark's time, or now, whichever is earliest.
  - Controller ruling: a Fleet-only car that is `HOME_CHARGING` or has `believedAmps > 0`, with no open suspicion and no open ledger session, is suspected at `now`.

lib/TWCManager/Vehicle/Reconcile/Desired.py (+2): `Attempt.sentAt: Optional[float] = None`.
lib/TWCManager/Vehicle/Reconcile/Run.py (+1): `attempt = attempt._replace(sentAt=master.vehicleRegistry.now())` just before the provider call.
lib/TWCManager/Vehicle/Reconcile/Reconciler.py (+3): `afterWrite` calls `master.watch.commanded(attempt.key, attempt.sentAt)` on `O.SETTLED` (DONE/SATISFIED) for any aspect. `runAttempt`'s early returns (SATISFIED by read, rules, asleep holds) never reach `afterWrite`, so only commands actually sent suspect.

Library growth: +92 / -22 (net +70).

## Tests

New, in tests/unit/test_watch_load_step.py (helper `fleetStep`, built on test_watch_poll's `start`):
- test_an_up_step_suspects_an_awake_fleet_only_car_from_the_steps_first_sample (asserts `(since, stepAt) == (T, T)`, where T is the first 5300 W sample, 30 s before the held one)
- test_an_up_step_asks_an_asleep_car_online_and_suspects_it_only_if_awake (one free check per step; no suspicion while asleep; T = the first sample once awake)
- test_a_cycling_load_does_not_throttle_a_fleet_only_suspicion
- test_a_down_step_suspects_a_charging_car

New, in tests/unit/test_watch_poll.py:
- test_an_accepted_command_suspects_the_car_from_its_send_time (the command handler advances the clock 20 s; T = the send time)
- test_a_refused_command_suspects_nothing (403 gives REFUSED)
- test_believed_load_above_consumption_twice_suspects_the_car
- test_one_sample_above_consumption_is_a_ramp_not_staleness
- test_a_fleet_only_car_believed_charging_with_no_session_is_suspected (controller ruling; the restart case)
- test_a_wake_and_a_plug_in_suspect_a_fleet_only_car_and_pay_nothing (the wake's one location read stays)

RED (before any lib change):
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_poll.py tests/unit/test_watch_load_step.py
E   TypeError: Watch.suspect() got an unexpected keyword argument 'step'
E   KeyError: '5YJ3E1EA1KF000001'   (x5: no suspicion opened)
E   AssertionError: assert '5YJ3E1EA1KF000001' in {}
E   assert (1 == (1 + 1))          (no free online check on the asleep step)
FAILED tests/unit/test_watch_poll.py::test_a_suspicion_polls_until_a_newer_snapshot_and_pays_nothing
FAILED tests/unit/test_watch_poll.py::test_an_accepted_command_suspects_the_car_from_its_send_time
FAILED tests/unit/test_watch_poll.py::test_believed_load_above_consumption_twice_suspects_the_car
FAILED tests/unit/test_watch_poll.py::test_a_fleet_only_car_believed_charging_with_no_session_is_suspected
FAILED tests/unit/test_watch_poll.py::test_a_wake_and_a_plug_in_suspect_a_fleet_only_car_and_pay_nothing
FAILED tests/unit/test_watch_load_step.py::test_an_up_step_suspects_an_awake_fleet_only_car_from_the_steps_first_sample
FAILED tests/unit/test_watch_load_step.py::test_an_up_step_asks_an_asleep_car_online_and_suspects_it_only_if_awake
FAILED tests/unit/test_watch_load_step.py::test_a_cycling_load_does_not_throttle_a_fleet_only_suspicion
FAILED tests/unit/test_watch_load_step.py::test_a_down_step_suspects_a_charging_car
========================= 9 failed, 33 passed
```
The two negative tests (refused command, one-sample ramp) passed at RED, as negatives do. The refused test asserts `out.kind == "refused"`, so it checks a real refusal path. My first draft used "not_charging", which TeslaAPI maps to SATISFIED, and that draft failed after the change, as it should have.

Some test bugs were fixed during GREEN: test-side timing (the onlineState real-time deferral, so `later()` is needed before a second check), a T miscount, and plugging the car via `v.mark("plugIn")`.

GREEN:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_poll.py tests/unit/test_watch_load_step.py
============================== 42 passed in 1.62s ==============================
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch*.py tests/unit/test_*reconciler*.py tests/unit/test_charge_ledger.py tests/unit/test_command_path_parity.py
======================== 500 passed in 82.64s (0:01:22) ========================
$ PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration
============ 2633 passed, 1 xfailed, 1 warning in 305.02s (0:05:05) ============
```
test_a_cycling_load_reads_a_car_once_a_courtesy_window is unchanged and passes.

## Existing tests changed

- test_watch_poll.py `start()`: gains a `state="online"` parameter (needed for the asleep-car tests).
- test_a_suspicion_polls_until_a_newer_snapshot_and_pays_nothing: `w.suspect(..., "load step up", step=True)`. The start hint is now an explicit flag, not the string.
- test_no_routine_paid_read_while_a_fleet_only_car_charges: cached polls 30 -> 31. The car is believed charging before the first pass, so the believed-charging ruling suspects it on that pass and it is polled one minute earlier. The test's intent (no paid read) is unchanged.

## Concerns

1. **Polling while belief and snapshot disagree.** The believed-charging rule reopens a suspicion as soon as the previous one gives up (600 s). Suppose a Fleet-only car stays believed `HOME_CHARGING` (or has `believedAmps > 0`) and no snapshot newer than T arrives. It is then polled once a minute indefinitely until it sleeps or a snapshot settles the belief. That costs nothing but is unbounded. Normally a snapshot taken by the poll updates `chargingState` through the cached provider, which ends the belief. The case that can persist is a car that is awake, believed charging, and uploading nothing. The same holds for staleness (it re-fires while over).
2. **Up steps on a `HOME_CHARGING` Fleet-only car do not suspect it.** I kept the existing `maybe` set. Such a car is already polled through its open session, or through the believed-charging rule.
3. **Event T for wakes and doors is `now`** (the pass that noticed them), not when the car actually woke. A snapshot uploaded between the wake and its detection is not accepted; the poll waits for a newer one or gives up. Arrival and plug-in use their own event times.
4. **The `_wakeCheck` race.** `_wakeCheck` runs on the background thread and checks `_inflight` before `_submit`. If `_visit` submits a status job in between, `submitJob`'s one-per-(key, kind) queue refuses the duplicate, and the refusal settles that kind. Harmless, but it can stamp the status cadence early.
5. **The wake ask for a Fleet-only car still sets a want.** A deaf BLE car is not `cloudOnly`, so it has no `fix`, and the want lingers as it did after Task 4 (concern 3 there). Arrival, plug-in and door no longer add wants for Fleet-only cars.
6. **`afterWrite` suspects on SATISFIED from the provider too** (for example "not_charging" on a stop), as the brief says. One extra free poll window.
7. Watch.py was not black-clean before this task either; I did not reformat it.

---

## Fix round 1 (commit 12a99f3a `fix: re-suspect a believed charge only on new evidence`)

Finding: polling never stopped. A belief that no snapshot settled was re-suspected right after each 600 s give-up, by both the believed-charging rule and staleness.

Change (lib/TWCManager/Vehicle/Watch.py, +17 -2):
- New module function `evidence(v)`: the newest `.at` among `v.latest("chargingState")`, `v.latest("actualCurrent")`, `v.lastWrite("chargingState")` and `v.lastWrite("chargeCurrentRequest")`, or NEVER if there is none.
- `Watch._spent`: vin -> evidence. `_poll` records it when it gives up a suspicion, whether on timeout or asleep.
- `Watch._fresh(v)`: `_spent.get(vin) != evidence(v)`. Both the believed-charging rule in `_visit` and `_stale` now require it. Real triggers (load steps, wakes, arrival, plug-in, door, commands) are not gated.

Tests (tests/unit/test_watch_poll.py; the reviewer's probe was adapted and the scratch file stays outside the tree):
- `test_a_belief_no_snapshot_settles_is_polled_one_window_until_new_evidence`: a Complete snapshot stamped T-600, then Charging is observed. Over 60 minutes the car gets 9 cached polls (T+60 to T+540) and then none. A newer actualCurrent reading follows, and 20 more minutes give one more window: 19 polls in total, 0 paid.
- `test_staleness_suspects_once_per_evidence`: the believed 32 A sits above a 2000 W meter, sampled every 30 s for 40 minutes, giving 9 polls (one window). A `noteWrite` of the current request follows, and 40 more minutes give 18 polls in total.

RED (lib reverted, new tests kept):
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch_poll.py
E   assert (55 == 9)
E   assert (38 == 9)
FAILED tests/unit/test_watch_poll.py::test_a_belief_no_snapshot_settles_is_polled_one_window_until_new_evidence
FAILED tests/unit/test_watch_poll.py::test_staleness_suspects_once_per_evidence
========================= 2 failed, 20 passed in 1.52s =========================
```
Mutation check: with the fix applied but the `_fresh` gate removed from `_stale` only, the staleness test alone fails (`assert (38 == 9)`). So that test covers the staleness gate on its own.

GREEN:
```
$ PYTHONPATH=lib .venv/bin/python -m pytest -q tests/unit/test_watch*.py tests/unit/test_*reconciler*.py
============================= 368 passed in 56.24s =============================
$ PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration
============ 2635 passed, 1 xfailed, 1 warning in 305.70s (0:05:05) ============
```

Notes:
- `_spent` is written under the lock in `_poll` and read without it in `_fresh` (a single dict get). The worst case is one extra suspicion.
- Entries in `_spent` are never removed. There is at most one per car, and a stale entry stops matching as soon as evidence changes.
- Concern 1 from the first round is resolved. The other concerns stand.
