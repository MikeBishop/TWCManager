# Task 4 review: Watch skeleton, Ring 1 (63fea432..3c02f7c4)

## Verdicts

- **Spec compliance: PASS, with notes.** The interfaces, situations, source order, leaf lock, the cover check made when a ring is due, and per-car single flight all match the brief.
  - The `done` callback is a sound deviation, and the brief allowed it ("the queue's report").
  - A flat `_due[vin]` in place of `_due[vin]["status"]` is fine; see S3, which removes it.
  - Inherited from the brief, not the implementer: spec line 66 says the watch resumes "at once" when a feed drops. The brief's design delays that by up to one cadence (30 min for an away car that is asleep). This is acceptable because an asleep car isn't changing, but the plan should say so (N3).
- **Quality: APPROVE WITH CHANGES.** Watch.py can drop about 30 lines (190 to about 160) with no behaviour lost. One robustness hole (Q1). The in-flight guard has no test that would fail without it (T1).

## Size: concrete cuts (Watch.py, 190 lines)

| # | Cut | Lines |
|---|-----|-------|
| S1 | Drop `_bleUsable`, the `self._ble` cache and `import os`. A loaded TeslaBLE always has its binary: `TeslaBLE.__init__` calls `releaseModule` when the binary is missing or not executable (TeslaBLE.py:147-161). So `canScan() or isfile(binaryPath)` is always True. "A TeslaBLE module is present" is the whole test. | -9 |
| S2 | Remove the `_due` dict and derive the next check: `nextAt = lastAt + cadence(situation now)`. `_done` then records only `(answer, now)`; it no longer calls `situation`/`presence` on the worker. `_settle` shrinks. `status()["nextAt"]` comes from `_last` plus the memo's situation. Side benefits: the cadence follows a situation change at once (a car that wakes moves from 900 s to 240 s), Q1 goes away, and it is the same pattern as Task 5's planned `_lastRead[vin]`, so Tasks 5–6 get one stamp per ring instead of a `_due` per ring. The skip path (unwatched or no source) stamps `at` with no answer. | -4 to -6 |
| S3 | `_CADENCE`: the situation strings are already the settings-key stems. Use `self._settings[{HOME_CHARGING: HOME_AWAKE, UNKNOWN: AWAY_AWAKE}.get(s, s) + "Secs"]` with the two aliases on one line, and keep the why-comment for UNKNOWN. | -5 |
| S4 | Constants: `HOME_ASLEEP, ..., UNKNOWN = ("homeAsleep homeAwake homeCharging awayAsleep awayAwake unknown".split())` takes 3 lines under black instead of 8. | -5 |
| S5 | `_module(master, *providers)` duplicates `Presence._ble(master)` (Presence.py:202) for BLE, and `master.getModuleByName` (the established lookup: TWCMaster, HTTPControl, WebIPC) for TeslaAPI/HA. Reuse those. Tests must register the module in `master.modules`, or keep provider lookup but share Presence's helper. | -4 to -6 |
| S6 | `notWatched`: `feed != "TeslaAPI"` is redundant. Only `Telemetry` registers liveness (Telemetry.py:84), so `sourceLiveAt("TeslaAPI")` is `NOT_TRACKED`, which is never a number. | -2 |

Total: about -30. Not duplication, keep:
- `situation` (composes Presence; doesn't repeat it)
- `status()` (small)
- the anonymous skip in `pass_` (`_seen` needs every non-anonymous car, including TWC-named ones, for Task 5's arrival reads)

TWCMaster now does a third overlay of `config["watch"]` over DEFAULTS (with Watch.settings and notWatched's "enabled"). When Task 9 builds `master.watch`, take the budget from `watch.settings()` and drop the TWCMaster overlay.

## Focus 2: `Job.done` from `Reconciler.report`

All paths are correct. Each accepted or rejected Job reaches `report` exactly once:
- **Success:** `_runOne`, then `_deliver(entry, result)`.
- **Exception, including BaseException:** `_deliver(entry, e)`.
- **Replaced:** `put` adds the old entry to losers, then `lost`, then `report(Outcome ERROR)`.
- **Overflow drop:** the oldest low entry, or the newcomer itself, goes to `lost`.
- **Shutdown:** `close()`, `waitDrained` timeout, or a put against a dead or draining queue all go to `lost`.

A try/finally in the job would leak `_inflight` on every path where the job never runs, so the deviation is right.

Coalescing on `(vin, "status")`:
- The watch never submits a second status job while one is in flight, so it never replaces its own job.
- A replacement by another submitter would fire the old job's `done` once ("no answer") and the new job's `done` once. That is never zero times and never twice for the same job.
- Watch for this in Task 6: TeslaBLE.py:1184 already submits `(vin, "scan")` jobs. If the watch's scan job uses kind `"scan"`, the two coalesce. That is benign (each job's `done` still fires once), but the watch may record "no answer" for a scan that TeslaBLE then runs.

`done` can run synchronously inside `put` on the tick thread (replace or drop). That is safe: `pass_` holds no lock then, and `_lose` runs outside `_cond`.

**Q1 (Important, robustness):** `_done` calls `situation()` (registry and Presence) before `_settle`. Any exception there is swallowed by `_deliver`/`_lose`'s try/except, `_inflight` is never cleared, and that car is never watched again until restart. Fix with S2 (`_done` touches no registry), or put `_settle` in a `finally`.

**N1 (Minor):** the BLE lambda uses `ping(...) is not None`. With `scan=False`, ping's contract is True (answered) or None (no answer). False means "a scan ran and missed", so it should not count as answered, where it would record the stale `state` as the answer. Use `is True`.

## Focus 3: onlineState echoing a dropped feed

This is real but narrow. With the feed down, `telemetryState()` age is `now - obs.at`, because liveness is None. Two consequences:
- The echo happens only when the feed's last `state` change is under 15 min old at the time of the check.
- Because the watch first re-checks a newly uncovered car only at its cadence, the echoed state is at most 15 min old and was a real report.

Cost: one cadence of extra delay before a real GET, and `_last` shows "answered" for an echo. That is cosmetic, plus 4–30 min of latency in a rare window.

**Recommendation: defer to Task 8**, which already folds in the onlineState cache. Add one line to the Task 8 brief: the telemetry shortcut must require the source live (`registry.sourceLiveAt(obs.source, vehicle)` is a number), not only a young observation.

If it is fixed now, that is the smallest fix (+1 condition in TeslaAPI.onlineState). It also helps the pre-command callers: with the feed down they GET (free, still 120 s cached) instead of trusting the last feed state.

## Focus 4: locking and the tick

All correct:
- The lock is a leaf. It guards only dict and set operations in `pass_`, `_settle` and `status`. `notWatched`, `_source`, `submitJob`, `situation` and `presence` all run outside it.
- No I/O on the tick: `os.path.isfile` and `canScan` (`shutil.which`) are cached once per module object. S1 removes even that.
- One job per car: a car is claimed under the lock before the submit, and released only through `done` or the exception path.
- The cover check runs in `_check` only when the car is due. The blip test pins this.

**N3:** decide explicitly that "resume at once" (spec) means "at the next due check, within one cadence", and say so in Task 10's docs.

## Focus 5: unpruned per-car dicts

These dicts don't matter: they hold a few entries per car ever seen, and the registry's `removed` slot is a single callback already used by `desired.forget`. Don't add pruning code. When Task 5 adds the memo comparison, write `old, self._seen = self._seen, {}` each pass, which prunes `_seen` for free. A stale `_last` entry is harmless.

## Focus 6: tests and comments

- **T1 (Important):** the in-flight guard is untested. By inspection (no pytest in this environment, so not run), removing `vin not in self._inflight` leaves all 9 tests passing, because the queue's coalescing keeps the count at 4.
  - Crisp test: hold the jobs (`inline(r, VehicleCommandQueue)`), capture `first = entries(r.ble)`, advance `c.t` past the cadence, call `pass_()`, then `assert all(a is b for a, b in zip(entries(r.ble), first))` and `w.status(v)["last"] == ""`.
  - Without the guard, the job is replaced by a new Job object, and the replaced job's `done` records "no answer".
- **T2 (Minor):** `order.index("attempt") <= 4` cannot fail: with 4 watch jobs FIFO and one attempt, the index is always 4. The "commands are not starved" claim is untested; there is no priority yet (report concern 3). Either assert something that could fail, or drop the clause from the name.
- **T3 (Minor):** `test_a_dropped_job_frees_the_car` flips the private `r.ble._draining`. Acceptable; a replaced-job case would also cover the `done` path without private state.
- **Comments:** comply with the rule. They explain why and carry no history.
