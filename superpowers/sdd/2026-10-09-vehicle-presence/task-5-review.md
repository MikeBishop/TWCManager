# Task 5 review: VehiclePresence core (0059579..0c54080)

### Spec Compliance

- ✅ Spec compliant. All Produces items exist: constants and `DEFAULT_SOURCE_ORDER` (VehiclePresence.py:21-25), constructor signature with `clock=time.monotonic` (:35-61), `start/stop/state/nominate/observeContact/observeLocation/runPass` (:97-234), `PROBE_INTERVAL = 60`, `AWAY_AFTER_FAILED_PROBES = 2` (:31-33), `TWCMaster.vehiclePresence = VehiclePresence(self)` after the queue, no thread started (TWCMaster.py:110-112; `self.config` is set at the top of `__init__`, so `_resolveOrder` can read it).
- The only deviation is the accepted one: `_collectDue` returns a `None` sentinel and `runPass` expands it outside the lock (:195-198, :236-250).
- Test file: `tests/unit/test_vehicle_presence.py` is byte-identical to the brief's block (checked by extracting it from task-5-brief.md and running `diff`). The master test matches the brief.
- The test count reconciles: 558 (after Task 4, per progress.md) + 29 + 1 = 588. `pytest --collect-only` reports 588, and the presence file gives 29 passed.
- ⚠️ Cannot verify from this diff: the BLE away rule relies on failed probes being counted only by the pass's own `_probe` result. `observeContact(..., probe=True)` failures are dropped (:133-138), as the brief and its tests require. The controller should check in Task 6 that BLE presence probes run only through the presence `ble` source. A probe run anywhere else would never count toward away.

### Named-risk checks

- **(a) Lock discipline.** I walked every `with self._lock` block: start :98-105 (thread object only, `start()` outside the lock), stop :111-112, state :116-117, nominate :123-124 (clock read outside), observeContact :140-141, observeLocation :146-147, `_run` :155-158 and :161-163, and runPass :191-193, :202-206, :211-222, :224-225 and :230-231. None of them calls a source, `_probe`, a handler or `knownVehicles()`. The only callouts under the lock are `_timeUntilNextDue` calling `self._clock()` (time.monotonic, which is harmless) and `logger.debug/info` (see Minor 3). The invariant holds. `test_handlers_run_without_the_presence_lock` covers the handler side. Nothing checks that sources or `knownVehicles` run unlocked (Minor 4).
- **(a, outside the diff) TeslaAPI call.** The risk: `_defaultKnownVehicles` is the only Task 5 call into a vehicle module, and the "never wake_up" constraint needs it to be a plain getter. Checked: `TeslaAPI.getCarApiVehicles` (lib/TWCManager/Vehicle/TeslaAPI.py:1129-1130) returns `self.carApiVehicles` with no I/O and no wake.
- **(b) Rules vs. spec "Decision rules".**
  - BLE probe success → home: `_probe` breaks on the first definite answer, then `_applyProbe` runs (:289-294).
  - A fix outside the geofence → away: `_applyLocation` (:307-308) and probe atHome False.
  - BLE-only away: counts only when `bleFailed and not telemetryLive` (:295-301). It resets on any definite answer, which is a superset of "a successful probe resets", and a later source answering resets it too (tested). It resets on contact success (:303-305).
  - unknown→home runs arrival, unknown→away runs nothing, home→away runs departure (:321-329).
  - A non-probe failure is no evidence (:133-134).
  - A source exception counts as no answer (:261-265).
  - All of these match.
- **(c) Thread lifecycle.**
  - `start` is idempotent under the lock (:98-106).
  - `stop` sets the flag and the event and returns. The thread re-checks after wake (:161-163), the probe loop breaks (:212-213), and handlers are skipped (:230-233).
  - Lost wakeups: the timeout is computed under the lock, then `wait`, then `clear()`, then `runPass` reads state. Any nominate after the timeout computation sets the event, so `wait` returns at once. A nominate between `wait` and `clear` already wrote `_due`/`_observations` before setting the event, and the `runPass` that follows sees them. No window.
  - A pass exception is logged and the loop continues (:164-169). BaseException is logged and re-raised.
- **(d) Determinism.** FakeClock drives all rule and scheduling tests through a synchronous `runPass`. The thread tests use `threading.Event.wait(2.0)` for positive assertions. The negative assertion in `test_stop_prevents_new_passes` comes after `join`, so it is deterministic. No `time.sleep`.

### Strengths

- The implementer moved `knownVehicles()` out of the lock without being asked, so the lock order stays `_bleLock → presence._lock` with no inversion. That was a real latent deadlock in the brief's code.
- Clean split: observers do pure recording, `_probe` does I/O, the `_apply*`/`_setState` rules run locked, and `_runHandler` runs unlocked. Each section is labeled with whether the lock is held.
- Handler exceptions are isolated per transition (:331-340). Source exceptions are isolated per source.
- The rate-limit timestamp is set before the probe (:222), so a slow probe can't be double-scheduled by a concurrent pass.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **A `knownVehicles()` exception drops a whole pass's work.** VehiclePresence.py:191-198. `runPass` swaps out `_observations` and pops the due times under the lock, then calls `self._knownVehicles()` with no guard. If that call raises, every observation in this pass and every explicitly nominated VIN popped with it is lost. For example, a BLE contact success would leave a home car `unknown` until something nominates it again. The default implementation guards only the `getCarApiVehicles()` loop, not `getModuleByName` or the settings access, so the chance is low. The brief's version had the same flaw. Fix: wrap the single call in try/except, log it, and treat it as `[]`. `test_thread_survives_an_exception_in_a_pass` still holds after that change, because it asserts survival, not an aborted pass.
2. **A pushed home fix doesn't reset the failed-probe count.** VehiclePresence.py:307-308. This is plan-inherited: the brief's code is identical. `_applyHome` (contact) resets `_failedProbes` and `_applyLocation(vin, True)` does not. Sequence: one failed BLE probe (count 1), then `observeLocation(True)` sets HOME, then one more failed probe sets AWAY. That is a departure after a single failure that followed a fresh home fix. The spec ("push observations follow the same rules"; "2 consecutive failed BLE probes") is ambiguous on this, so the controller should rule. Suggested fix: reset the count when `atHome` is true, and add a test.
3. **Logging under the presence lock.** VehiclePresence.py:316 (`logger.info` in `_setState`) and :216 (`logger.debug`). A slow or blocking log handler stalls every observer, including TeslaBLE while it holds `_bleLock`. To fix, return the transition and log after release.
4. **A source returning a non-dict escapes `_probe`.** VehiclePresence.py:270-272. `result.get` raises outside the per-source try, which aborts the whole pass (losing observations, as in Minor 1). The spec says a source failure counts as no answer. To fix, move the result handling inside the try, or validate `isinstance(result, dict)`.
5. **Test gap.** The tests check that handlers run without the lock, but nothing checks the same for sources or `knownVehicles()`. The invariant that matters most for TeslaBLE (sources unlocked) has no regression guard. The implementer's deviation (expanding outside the lock) has no test either. Add a `_lock.locked()` probe inside a source and inside `knownVehicles`.
6. **Restart edge.** VehiclePresence.py:98-105. `start()` called after `stop()` while the old thread is still in a long probe returns early without clearing `_stopped`. The old thread then exits and nothing runs. No current caller restarts, so this is noted only.

### Assessment

**Task quality:** Approved

**Reasoning:** The lock discipline, thread lifecycle and decision rules all hold up, and the tests are deterministic and identical to the brief. The remaining items are robustness edges: work dropped when `knownVehicles` raises or a source returns a non-dict, the reset on a location fix, and logging under the lock. None of them breaks the invariant or the spec's stated rules.
