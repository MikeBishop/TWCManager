# Task 4 report: the watch, who / situation / Ring 1 on a clock

Status: DONE_WITH_CONCERNS
Commit: 3c02f7c4 on vehicle-model/phase6 (base 63fea432), in scratchpad/wt-vm6. Not pushed.
Suite: 2268 passed, 1 xfailed (BASE 2259 + 9 new in tests/unit/test_watch.py).
Lib: 26540 -> 26734 (+194). Watch.py is 190 lines; about 30 of those are the black-expanded situation tuple and DEFAULTS. Run.py +1, Reconciler +3, TWCMaster +0 (net).

## What was built

- `lib/TWCManager/Vehicle/Watch.py`
  - The situation constants, `DEFAULTS` (verbatim from the brief), `notWatched` and `situation` match the Interfaces block.
  - `notWatched` checks in this order: anonymous, disabled (`config["watch"]["enabled"]`), `twcVinAt > NEVER` ("named by TWC <id>"), and covered. A car is covered when `syncSource != "TeslaAPI"` and `registry.sourceLiveAt(syncSource, v)` is a number. `syncSource` alone is not enough: a down feed keeps it for SYNC_TIMEOUT (1 h).
  - `situation(master, v, where=None)` has an optional presence argument, so `pass_` runs `decide` once per car.
  - The `Watch` class has `settings()`, `pass_()` and `status()`.
    - `pass_` refreshes `_seen[vin]` (situation, presence, plugIn mark, chargingState) for every non-anonymous car on every pass. Under the leaf lock it claims a due car that has nothing in flight.
    - When the car's check is due, `_check` asks `notWatched` and picks the source. A car with no source, or one that isn't watched, is rescheduled by cadence with no submit.
    - Source order: BLE ping (scan=False) when TeslaBLE is loaded and `canScan()` or its binary is present (cached per module object, so no stat on every tick). Then `TeslaAPI.onlineState` when the car has a TeslaAPI attachment. Then the HA refresh. All cloud and HA checks go to the cloud queue.
  - Cadences:
    - HOME_CHARGING uses `homeAwakeSecs`, because no Ring-1 key exists for charging and the spec says 3–5 min.
    - UNKNOWN uses `awayAwakeSecs`, because nothing says the car can't move.
- **Completion: one deviation from the brief's try/finally, which the brief also allowed ("the queue's report").** `Run.Job` gained an optional `done` field (default None), and `Reconciler.report` calls `job.done(outcome)` for a Job.
  - The queue reports every accepted entry exactly once, and a rejected `put` goes through `lost` and so through `report`. So `done` fires whether the job ran, raised, or was dropped (overflow, shutdown).
  - A try/finally inside the job would never run for a dropped job, and the car would stay "in flight" forever.
  - `submitJob(key, kind, run, worker="ble", done=None)`: `worker="cloud"` puts the job on the cloud queue.
- **TWCMaster** takes the budget default from `Watch.DEFAULTS` (`dict(WATCH, **config["watch"])`). 3.0 is now written in one place only.
- **`status(v)`** returns:
  - `watched`: True when the car is not excluded. A car with no status source still counts as watched, with why = "no status source".
  - `why`
  - `last`: the car's state after an answered check, or "no answer"
  - `lastAt`, `nextAt`: None until set

## Test helpers (all in tests/unit/reconcile_helpers.py unless noted)

- `bleAnswers(master, asleep=None, answer=True, charging=None, ok=None)` behaves as the brief says.
  - It sets `ping` on a real TeslaBLE, or swaps in a fresh SimpleNamespace for a scripted provider. The scripted provider's default module is shared, so it is never mutated.
  - `ok=` keeps the old behaviour (reach only). The two existing callers (`bleAnswers(m)`) pass with the new default.
  - `charging` is not used anywhere in the plan. I read it as the door: awake + charging → `chargePortOpen`.
- `bleReads`, `bleScans`, `liveFeed` and `gen2Slave` follow the brief. gen2_helpers had no slave factory, so `gen2Slave` uses `master.newSlave(bytes.fromhex(twcid), 80)`.
- `attachFleet` and `attachOwner` wrap a new `listApi(master, vin, fleet, owner, signing)`.
  - `listApi` is the listing code taken out of `test_command_path_parity.install`, which now calls it.
  - Putting the helpers here avoids a circular import, since parity imports reconcile_helpers.
- `inline(reconciler, kind=InlineQueue)`: passing `VehicleCommandQueue` gives queues that hold every entry until `runPending`.
- `test_limit_reconciler.setup(..., ble=False)`: `ble=True` loads a real TeslaBLE (teslaControlPath /bin/true, dbus and pipe patched, `isDockerCached=False`) and registers its provider.

## Plumbing changes to the brief's tests (assertions kept)

- **test_situations:** added `c.t += 10` before `placeAt(m, v, AWAY)`.
  - Without it, the away fix ties at the same instant with the plugIn mark from the `Charging` observation, and `decide` stays HOME.
- **test_one_watch_job_in_flight…:**
  - `inline(r, VehicleCommandQueue)`: InlineQueue runs attempts at once, so none would ever be pending.
  - `v.claim("TeslaBLE", True, "paired")`, so the limit attempt is planned over BLE.
  - Note: the 4-entries assertion would also hold without the in-flight guard, because the queue coalesces by `(vin, "status")`. The guard matters for completion bookkeeping, not for the count.
- **Three tests added:**
  - status reports why a car is unwatched or has no source
  - a dropped job frees the car
  - settings overlay the defaults

## Concerns

1. `TeslaAPI.onlineState` answers from the feed's own state, with no GET, while that state is within SYNC_TIMEOUT/4 (15 min) and newer than the last GET. So for up to 15 min after a feed goes down, the cloud Ring 1 echoes the feed's last state. That is free and harmless, but not a real check. The 120 s cache / onlineState is already a fold candidate in the spec, so I left it for a later task.
2. In a BLE install, an away car is pinged over BLE forever, which costs ~2 s per unanswered ping plus up to commandTimeout. Falling back to the cloud check after scan misses is the Task 6 scan rule.
3. The watch's BLE jobs share FIFO order with commands; there is no third priority level yet. The not-starved test passes because the attempt lands right after the per-car jobs.
4. `_seen`, `_due` and `_last` are not pruned when a car leaves the registry. They are bounded by the number of cars ever seen, so this is minor; Task 5/9 can prune on `removed`.
5. The `_seen` comparison is not used yet (Task 5 per the brief); this task only refreshes the memo.

## Fix round 1 (amended: 1a1c0586)

Suite: 2269 passed, 1 xfailed. Lib: 26540 -> 26717 (+177; was +194). Watch.py: 171 lines (was 190).

- **Q1 via S2.** The `_due` dict is gone. `_last[vin] = (answer, at)`, and a car is due when `now >= at + cadence(situation now)`, so the cadence follows a situation change at once.
  - The job itself turns its answer into a word on the worker (`_answer`). `_done(vin, result)` only stamps `(word or "no answer", clock())` under the lock: no registry call, so nothing in it can strand a car in flight.
  - The skip path (unwatched or no source) and the exception path stamp `("", now)`.
  - `status()["nextAt"]` is `lastAt + cadence(memo situation)`.
- **S1.** Dropped `_bleUsable`, the cache and `import os`. A loaded TeslaBLE is the whole test.
- **S3.** The cadence key is the situation stem + "Secs", with HOME_CHARGING aliased to homeAwake and UNKNOWN to awayAwake (the why-comment is kept).
- **S4.** The constants are one `.split()`.
- **S5.**
  - BLE comes from `Presence._ble`; TeslaAPI and HA from `master.getModuleByName`. The tests already register TeslaAPI that way through `new_api`.
  - `_module` is removed.
- **S6.** The covered test is `isinstance(sourceLiveAt(syncSource, v), float)`. `_number` always returns a float, and TeslaAPI is never tracked.
- **N1.** `_answer` counts only `is True` as answered.
- **One source of settings.** `settingsOf(config)` in Watch.py is used by `Watch.__init__`, `notWatched` ("enabled") and TWCMaster's budget.
- **onlineState echo fixed.**
  - The telemetry shortcut in `TeslaAPI.onlineState` also requires `registry.sourceLiveAt(obs.source, vehicle)` to be a number. A feed that is down now gets the free GET (still behind the 120 s cache).
  - New assertion in `test_online_state_is_true_false_or_none_and_is_awake_stays_a_bool`: with the feed dropped, a fresh TeslaMate "online" makes a GET.
  - Tests that modelled a live feed without registering liveness now register it (plumbing):
    - `test_is_awake_trusts_fresh_telemetry…`
    - the same online-state test
    - `test_teslaapi_wake._teslamate` (3 tests)
    - `test_a_cached_failed_check_stays_unknown`
- **T1.** New test `test_a_car_in_flight_is_not_asked_again`: jobs are held, the clock goes past the cadence, and the same Job object is still pending with `last == ""`. It fails with the guard removed (checked by mutating the guard).
- **T2.** The not-starved test now asserts the exact order `["status"]*4 + ["attempt", "status"]`: a check for a car that becomes due after the command waits behind it. This fails if watch jobs ever jump ahead of commands.
- **Not done, per review:** pruning (Focus 5); N3 is for the docs task. The other earlier concerns are unchanged (BLE-only away pinging until Task 6; no third priority level yet).
