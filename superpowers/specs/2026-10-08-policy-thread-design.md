# Policy Evaluation Thread — Design

Date: 2026-10-08
Branch: `fix/policy-evaluation-thread` (off `main`)
Status: approach approved (option A); awaiting spec review

## Problem

The policy engine is evaluated on the serial main loop. `TWCSlave.receive_slave_heartbeat` calls `Policy.setChargingPerPolicy()` on every heartbeat (`TWCSlave.py:700`). That function is rate-limited internally to `policyCheckInterval` (30 s). Each evaluation resolves conditions through `Policy.policyValue`. For `modules.<Name>.<attr>` conditions, that does a `getattr` on the module. Some module attributes are properties that do network I/O when their cache is stale:

- **`TeslaPowerwall2.gridStatus` and `batteryLevel`** fetch over HTTPS from the local gateway. `cacheTime` is 10 s and the policy runs every 30 s, so every evaluation fetches. Roughly hourly, the fetch also logs in again (`doPowerwallLogin`).
- **`TeslaPowerwall2.stormWatch`** calls the Tesla cloud. It first calls `TeslaAPI.refreshTokenIfNeeded()`, so a Fleet API token refresh can happen on the serial thread.

The live box's policy uses all three conditions. A stack captured on the box (faulthandler, 2026-10-08 14:01) shows the main thread blocked for 2.9 s in `doPowerwallLogin`, by way of `receive_slave_heartbeat → setChargingPerPolicy → checkConditions → policyValue → gridStatus`. After the BLE work, the main-loop stalls that remain are 1.0–1.6 s and line up with policy ticks.

Two secondary issues:

- **Evaluation already runs on several threads.** `applyPolicyImmediately()` is called from HTTP request threads (Charge Now, set policy) and the MQTT control thread, and it evaluates synchronously on the calling thread. An HTTP request can also block on the same network fetches.
- **Exceptions stall the main loop.** An exception during evaluation propagates to the main loop's catch-all, which logs it and sleeps for 5 s.

## Goals

- The serial main loop never runs policy evaluation, so it never waits on module I/O that evaluation triggers.
- Policy evaluation runs on exactly one thread, one evaluation at a time.
- Evaluation keeps the `policyCheckInterval` cadence, and `applyPolicyImmediately()` still causes a prompt re-evaluation.
- A failing evaluation is logged. It does not stop later evaluations and does not affect the main loop.

## Non-goals

- Changing module caching, i.e. making EMS properties cache-only (option B). That can follow separately if wanted.
- Changing policy semantics: matching, latching, enforcement, or the values chosen.
- Making `policyIsGreen()` or `getActivePolicyAction()` asynchronous. They are cheap reads of state.
- Draining or joining the thread on shutdown. It is a daemon thread with no durable work. It is, however, told to stop at the start of shutdown (see below), so it starts no new evaluations and queues no new tasks while the other queues drain.

## Design

### Policy thread (in `lib/TWCManager/Policy/Policy.py`)

The `Policy` class gains:

```python
def start(self): ...                  # starts the daemon evaluation thread; idempotent
def applyPolicyImmediately(self): ... # now: wake the thread; returns immediately
def stop(self): ...                   # shutdown: no further evaluations; returns immediately
```

New state: a `threading.Event` (`_wake`), a `threading.Event` (`_stopping`), the thread handle, and an evaluation lock (`_evalLock`).

Thread loop:

```
evaluate once immediately at start
loop until _stopping:
    _wake.wait(timeout=policyCheckInterval)
    _wake.clear()
    if _stopping: exit
    evaluate
```

`stop()` sets `_stopping` and then sets `_wake`, so a thread blocked in its wait exits right away. Once `_stopping` is set:
- `applyPolicyImmediately()` does nothing.
- `setChargingPerPolicy()` returns without evaluating, whoever calls it.

An evaluation that is already running finishes; there is no pre-emption, matching the vehicle queue. `stop()` does not join the thread.

Each evaluation is wrapped in `try/except Exception`. A failure is logged at error level with a traceback, and the thread continues.

`setChargingPerPolicy()` keeps its name. It becomes the evaluation body without the rate limit, and it holds `_evalLock` for the duration, so even a stray direct caller cannot overlap the thread. The `lastPolicyCheck` gate is removed, because cadence is now owned by the thread. `lastPolicyCheck` is still set at each evaluation as a "last evaluated" timestamp; nothing reads it.

### Callers

- **`TWCSlave.receive_slave_heartbeat`:** remove the `setChargingPerPolicy()` call and its comment. The heartbeat code keeps reading results as it does today: `master.getMaxAmpsToDivideAmongSlaves()`, `getAllowedFlex()` and `policyIsGreen()`.
- **`applyPolicyImmediately()` callers** (HTTPControl ×3, MQTTControl ×4): unchanged. The call now returns immediately, and the evaluation happens on the policy thread, typically well under a second later.
- **`TWCManager.py` shutdown:** the first statement of the shutdown block, before `saveSettings` is queued and before any draining, is `master.getModuleByName("Policy").stop()`.
- **`TWCManager.py` startup:** after `backgroundTasksThread.start()`, call `master.getModuleByName("Policy").start()`. The first evaluation then runs at startup, usually before the first slave heartbeat. That shrinks the 6 A "no policy yet" window after a restart but does not remove it, because green-energy policies still wait for EMS data.

### Thread safety

All evaluation runs on one thread. Its writes are:

- Policy attributes: `active_policy`, latch timestamps inside the policy dicts, `limitOverride`, `lastPolicyCheck`.
- `master.setMaxAmpsToDivideAmongSlaves()`, which already takes `backgroundTasksLock`.
- `master.setAllowedFlex()` and `master.lastChargeLimitApplied`, which are plain assignments.
- `master.queue_background_task()`, which is thread-safe.
- Status `setStatus()` calls. These already happen from the background thread today.

Readers on other threads (main, HTTP, background) do single attribute reads, which are atomic under the GIL. Two writers on other threads already exist and are unchanged: HTTP `setPolicy` writes `active_policy`, and `clearOverride()` (called from `startCarsCharging`) writes `limitOverride`. They did the same before this change, so this is no regression.

### Behaviour changes

- `applyPolicyImmediately()` no longer evaluates before returning. A caller that depended on the result being in effect at return would now see it shortly afterwards. No current caller reads it immediately: HTTP and MQTT return a response or an acknowledgement.
- Evaluation errors no longer cause the main loop's 5 s post-exception sleep.
- Cadence is measured from the previous evaluation instead of being gated on heartbeat arrival. As a result, the policy evaluates even when no slave is talking: webhooks, status updates and `checkGreenEnergy` keep running. `applyPolicyImmediately` could already trigger an evaluation in that state. The policy thread only starts when `fakeMaster == 1`. In the other modes (0, fake slave; 2, passive listen), `receive_slave_heartbeat` never runs, so the amps the policy chooses are never used. Evaluating anyway would still send charge-limit commands to cars, fire webhooks and poll EMS. Without the thread, `applyPolicyImmediately` is a no-op in those modes, where before it evaluated synchronously. The user has said they are unsure what behaviour `fakeMaster != 1` should have and has proposed removing those modes, so the PR calls this out.

## Testing

Unit tests go in `tests/unit/test_policy.py`, as a new class. They use a Policy with a mock master and the default policy set, and cover:

- `start()` runs an evaluation immediately. Detect this with a recording wrapper or a patched `setChargingPerPolicy`.
- `applyPolicyImmediately()` returns quickly while an evaluation is blocked, and causes another evaluation promptly afterwards.
- Periodic cadence: with a small `policyCheckInterval`, evaluations repeat without being woken.
- An exception in evaluation is logged, and the next wake still evaluates, so the thread survives.
- `start()` is idempotent: there is no second thread.
- `stop()` stops the thread promptly: it is no longer alive shortly after, even with a long `policyCheckInterval`. After `stop()`, `applyPolicyImmediately()` and direct `setChargingPerPolicy()` calls do not evaluate, and an evaluation already running when `stop()` is called still completes.
- `setChargingPerPolicy()` has no rate limit: two direct calls evaluate twice.
- A guard test checks that the `TWCSlave` source no longer contains `setChargingPerPolicy`.

Existing policy tests must still pass.

Live testing: deploy on the box combined with #668 and #669, with the faulthandler stall diagnostic still in place. Expect no main-thread stacks in `TeslaPowerwall2` or `Policy`, and stall warnings gone apart from startup. Report counts over a window at least as long as the 14 h baseline, which had 6 non-startup stalls.
