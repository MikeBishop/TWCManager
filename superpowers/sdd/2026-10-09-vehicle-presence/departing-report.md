# Concern-3 fix and DEPARTING on unplug: report

Status: DONE.

## Commits
- ab545e7 A car home by the arriving timeout is not declared away by BLE (A)
- a00451e TWC slaves report debounced unplug and replug to presence (B, slave side and record-only observers)
- 516916a Unplugging a BLE car makes it DEPARTING and restores its limit over BLE (B, presence and handlers)

## A. No flap after a timeout arrival (ab545e7)
- `_timeoutHome` holds the VINs that became HOME by the ARRIVING timeout.
- While a VIN is in it, the BLE-only away rule is skipped in `_applyProbe`. Location sources still decide departure.
- It is cleared by a BLE contact observation, a probe decided by "ble", or any exit from HOME.
- Tests:
  - 5 failed probes with no telemetry: the car stays HOME, with no departure and no re-arrival;
  - a location "away" → AWAY plus departure;
  - after a contact or a reachable probe, the away rule applies again;
  - a later normal arrival is not exempt.

## B1. Debounce in the slave (a00451e)
- `TWCSlave._checkPlugState(previousState, now)` runs from `_checkPresenceTriggers` on every heartbeat (about 1/s). The existing nominations are unchanged and still go out for every car.
- Unplug: state 00 entered from non-00 and held for `UNPLUG_DEBOUNCE` = 60 s → `vehiclePresence.observeUnplug(twcKey, currentVIN or lastVIN or None, excluded)`, once per unplug.
  - `excluded` is the set of `currentVIN`s that other slaves report right now.
  - `twcKey` is the TWCID in hex ("ABCD"). TWCID is a bytearray and cannot be hashed.
- Replug, after a reported unplug: a plugged state (01/03/08) starts the hold, which only a 00 resets, so 03 → 06 → 0A while charging does not restart it. After 60 s → `observePlug(twcKey)`.
- Why in the slave:
  - heartbeats arrive about once a second, so the 60 s hold is evaluated promptly;
  - the check is pure time arithmetic plus a record-only observer call, so it is safe on the serial loop;
  - evaluating it in presence through a nomination would have the presence thread read slave state across threads.
- `_checkPresenceTriggers` takes `now=None` so tests can supply the time.
- Startup in 00 is not an unplug: it needs a transition from non-00.
- Tests (TestPlugDebounce, 9):
  - 59 s → nothing, 60 s → reported; once per unplug;
  - VIN-less → None; `excluded` is passed;
  - flicker under 60 s → nothing, and the existing nominations are unchanged;
  - replug after 60 s, with charging states not restarting the hold;
  - a replug flicker → no `observePlug` and no second `observeUnplug`;
  - an error state does not start the replug hold;
  - no plug report without a reported unplug;
  - startup in 00;
  - an unreadable slave list → empty `excluded`.

## B2. Presence (516916a)
- `DEPARTING` is internal; `state()` reports it as AWAY (see below). Class attribute `DEPARTING_PROBE_CAP = 1800`.
- Unplug processing happens under the lock, with no I/O:
  - Named VIN: it must be a BLE car (same `bleApplies` predicate as ARRIVING) and HOME or UNKNOWN. Not AWAY, ARRIVING or DEPARTING.
  - VIN-less: the candidates are the HOME BLE cars minus `excluded`. Unambiguous means named, or exactly one candidate.
  - Records `_departing[twc]`, the time it started and the failure count. Logs INFO "departing (was X): TWC … unplugged [(one of N candidates)]".
- Early restore: `departingHandler(master)`, injected as `onDeparting`, runs **outside the lock**.
  - Unambiguous and a limit is held → reset the dedupe state and queue `{"cmd":"applyChargeLimit","limit":-1,"vin":vin}`, with no remoteOnly. Per your revision, it does this **even with a remote channel**.
  - Ambiguous → INFO "no early restore". No held limit → INFO, nothing queued.
- Probing: the BLE-first order from ARRIVING, every PROBE_INTERVAL, scheduled until `since + DEPARTING_PROBE_CAP`. After the cap it stays DEPARTING; a test shows no more probes and `_timeUntilNextDue() is None`. A nomination (the slave's 300/1200/2700 s ones) can still probe after the cap.
- `_applyDepartingProbe`:
  - a location "away" → AWAY;
  - else if BLE failed → count it, and 2 in a row → AWAY. This is checked before the home answer, so BLE silent plus telemetry "home" counts as a failure (tested). The AWAY transition passes limit None, because the only limit available then came from a location source and may be stale;
  - else if BLE answered → reset the count.
- A BLE contact while DEPARTING resets the count and does not exit (tested). A location "home" does nothing; a location "away" → AWAY.
- Exit to HOME plus the arrival handler: a TWC proof (`_applyHome`), or `observePlug(twc)`, which moves the DEPARTING VINs in `_departing[twc]` to HOME; VINs already AWAY stay AWAY. Every exit clears the VIN from all `_departing` sets.
- `_runHandler` runs the departure handler for `old in (HOME, DEPARTING)`.
- The saved limit is the record (per your revision; no per-VIN tracking).
  - Successful TeslaBLE restore → `removeNormalChargeLimit` (or the already-at-normal path, which also removes it).
  - TeslaBLE finds a hand-set limit → saves `(current, -1)`.
  - Either way `departureHandler` returns at `not hasSaved or lastApplied == -1` and queues nothing.
  - Failed restore (the car left too fast): the entry is untouched, so the departure handler queues the remoteOnly restore if a channel exists, or logs INFO only.
  - Tested end to end with a real TeslaBLE and FakeCar in `test_teslable_presence.py::TestEarlyRestoreThenDeparture` (4 cases: OK, hand-set, failed with a channel, failed without one).
- **Ordering.** The early restore and the departure restore share the queue key `("applyChargeLimit", vin)`. If the early BLE restore is still pending when the car becomes AWAY:
  - The saved limit is still held, so the departure handler queues the remoteOnly restore, which replaces the pending BLE one in place. That is sensible: the car has gone, BLE would fail, and TeslaAPI's remoteOnly restore reads the limit first.
  - With no channel, the departure handler queues nothing, and the pending BLE restore still runs. It most likely fails harmlessly, or succeeds if the car is still in range.
  - If the early restore is running when the car departs, the queue does not replace a running entry. The departure handler reads the saved limit as it stands then. At worst one remote restore follows a BLE restore that is just finishing, and TeslaAPI's read-first logic makes that a no-op ("already at …").
  - Queue test: `test_pending_early_ble_restore_is_replaced_by_the_remote_restore`.

## state() reports DEPARTING as AWAY: caller by caller
- TeslaBLE.py:773, the policy-wide apply, skips `== "away"` → it skips the DEPARTING car, as required. The per-VIN early restore is not skipped (vin given).
- `CarApiVehicle.atHome` (TeslaAPI.py:1669-1685) → False. Its readers, for an unplugged car parked at home:
  - TeslaAPI.py:944/952/1002, the policy-wide API apply: skipped, as required (and no wake for it).
  - TeslaAPI.py:342, car_api_charge "don't wake a car that is not at home": unplugged, so there is nothing to charge.
  - TeslaAPI.py:642, start/stop charge: it is skipped and `stopAskingToStartCharging = True` is set. On replug the arrival handler runs `_resetLimitState`, and `TeslaAPI.resetChargeLimitState` clears `stopAskingToStartCharging` (TeslaAPI.py ~1529, commit 16a4bfd). So charging resumes after replug.
  - TeslaAPI.py:1458 `updateChargeAtHome` and 1468 `vehicleScheduledChargingPending` (vin=None): skipped. Neither matters for an unplugged car.
  - TeslaAPI.py:1565/1572 `numCarsAtHome` / `minBatteryLevelAtHome`: excluded. Their only consumer is the stop override at Policy.py:244, which an unplugged car should not affect.
  - TeslaAPIController.py:59 `allEVSEs`: the car's TeslaAPIEVSE leaves the cache while DEPARTING (it cannot charge unplugged) and comes back on replug.
  - HTTPControl.py:377 `lastAtHome`: shows false while unplugged. Cosmetic.
  - `car_api_available` does not read `atHome`.
- PresenceSources never calls `state()`.

## Tests
- `test_vehicle_presence.py`:
  - TestTimeoutHomeDoesNotFlap (5);
  - TestPlugObservers (1);
  - TestDeparting (18), covering:
    - named unplug and early-restore hook, run outside the lock;
    - non-BLE car, away car;
    - VIN-less: one candidate with exclusion, no candidate;
    - BLE contact does not exit;
    - location home / away;
    - two failed probes → AWAY plus departure;
    - BLE silent plus telemetry home counts as a failure;
    - count reset by a probe or by a contact;
    - cadence and cap;
    - TWC proof and replug back to HOME;
    - a plug on another TWC;
    - multi-car VIN-less (no early restore; the silent car goes AWAY, the other comes HOME on replug);
    - flicker (presence sees nothing);
    - a failing hook.
  - TestVinLessReplugEndToEnd (real handlers: unplug → BLE restore queued → replug → HOME plus the policy apply).
- `test_presence_handlers.py` TestDeparting (5): restore queued with no remoteOnly, even with a remote channel; ambiguous → none; nothing held → none.
- `test_teslable_presence.py` TestEarlyRestoreThenDeparture (4).
- `test_vehicle_command_queue.py`: key replacement (1).
- `test_twcslave.py` TestPlugDebounce (9).

Full suite: 814 passed, 1 warning (pre-existing). `test_vehicle_presence.py` run 5 times: 106 passed each. black --check clean.

## Concerns
- **A stale `lastVIN` is the main risk.** `currentVIN` moves to `lastVIN` when charging stops (TWCMaster.py:1249), so at unplug the slave almost always passes `lastVIN`, and it sticks until another VIN is read. A non-Tesla car (or a car with CAN off) unplugged after a Tesla session on that TWC names the Tesla. If that Tesla is HOME, it becomes DEPARTING and gets an early BLE restore while it is parked. Mitigations in place: only HOME/UNKNOWN BLE cars enter, and the replug or TWC-proof path brings it back (re-applying the policy limit). Its own TWC is not plugged in, so its replug never comes; it stays DEPARTING (reported "away") until a TWC proof, a location "away", or 2 failed probes. Fix option: clear `lastVIN` on unplug after use, or use only `currentVIN` plus a recency bound.
- **The early restore is not strictly "over BLE".** The queued task goes through `VehiclePriority._dispatch`: TeslaBLE (3 attempts), then TeslaAPI (2 attempts) unless `commandPolicy == "ble_only"`. Under `prefer_ble`, a BLE failure inside the early restore (breaker open, adapter hiccup, car already gone) falls through to `TeslaAPI.applyChargeLimit(-1, vin)`, which is a Fleet API command, the cost this revision was meant to avoid. It can fire on a transient BLE failure while the car is still in range. There is still never a double restore: TeslaAPI's restore saves lastApplied = -1, so the departure handler finds nothing. But the "BLE failed + channel → departure's remoteOnly restore" case only happens as described under `ble_only`; under `prefer_ble` the early restore's own API fallback resolves it. `TestEarlyRestoreThenDeparture` calls TeslaBLE directly, so this path is untested. Not changed, since the task dict was specified. Suggested follow-up: a `localOnly` flag (the inverse of remoteOnly) that `VehiclePriority.applyChargeLimit` honours by skipping TeslaAPI, set on the early restore, since the departure handler already supplies the remote fallback.
- A different car replugging into the same TWC moves the departed car back to HOME through the TWC-state path ("all of departing[twcid]"). Within the probe window, the 2-probe AWAY rule keeps that window small. But past `DEPARTING_PROBE_CAP` with no location source, a car that actually left stays DEPARTING indefinitely, and *any* later plug on that TWC (days later, a different car) brings it HOME. That runs an arrival apply over BLE, which fails, then the BLE-only away rule makes it AWAY and the departure handler finds nothing to restore. It corrects itself, but it is a full false cycle.
- A DEPARTING car past the probe cap with no location source stays DEPARTING ("away") indefinitely, until plug evidence. That is intended, but it is invisible to the policy.
- The BLE restore during DEPARTING wakes the car over BLE. That is cheap and local, but it happens on every unambiguous unplug with a held limit, including a plain unplug and replug at home. The replug then re-applies the policy limit: two BLE writes per such cycle.
- A ble source that raises (rather than answering NO_ANSWER) becomes "does not apply" in `_callSource`, so `bleFailed` stays False. A DEPARTING car whose BLE source keeps erroring never goes AWAY by probe; only a location "away" or plug evidence ends it.
- An early restore that fails because of the TeslaBLE circuit breaker leaves the saved limit, so with a channel the remote restore takes over on departure. That is the intended fallback.

---

# Follow-ups on the departing concerns

## Commits
- 5fa7b69 Attribute an unplug to the car of this plug session, not lastVIN
- b502780 The early restore on unplug is BLE only (localOnly)
- e250fee DEPARTING slows its BLE probes after the cap instead of stopping

## 1. plugVIN (5fa7b69)
- `TWCSlave.plugVIN` (default None) and `TWCSlave.NON_TESLA = "non-tesla"`.
- Set in the VIN parse in TWCManager.py: `= potentialVIN` in the valid-VIN branch, and `= slaveTWC.NON_TESLA` in the all-empty branch ("non-Tesla vehicle or CAN disabled"). That parse runs inline in the main loop; the test checks the source.
- Cleared after the unplug is reported, and when a replug hold starts (the first 01/03/08 after a reported unplug). A VIN read during the replug hold is kept.
- Attribution in `_checkPlugState`:
  - a VIN → `observeUnplug(key, vin, excluded)`;
  - NON_TESLA → no observeUnplug, INFO log, nobody departs. The replug is still tracked; presence ignores a plug from a TWC with no departing set;
  - None → `observeUnplug(key, None, excluded)`, which applies the candidate rules.
- `lastVIN` and `currentVIN` are untouched and still give the nominations their hints.
- Tests (TestPlugVIN, 7): starts None; a stale lastVIN is not used (None is passed, and lastVIN is left alone); a non-Tesla unplug after a Tesla session → no observeUnplug; cleared after the report; a flicker keeps the session; cleared at replug start and a new read is kept; the parse sets it. Presence's VIN-less candidate tests are unchanged.
- **Open question.** The all-empty branch's own comment says it covers "non-Tesla vehicle **or CAN communication disabled (DIP switch 2 down)**". If a CAN-off TWC answers the VIN query with all-empty parts, rather than never answering, its plugVIN becomes NON_TESLA and its unplugs depart nobody. The VIN-less candidate path then never fires for that TWC: the behaviour falls back to the delayed nominations, which is safe but means no DEPARTING. I could not tell from the code or the live logs which case the user's TWC is in. If the user's TWC is CAN-off and answers empty, NON_TESLA should be split from "query answered empty", for example by trusting NON_TESLA only when the TWC has reported a VIN before.

## 2. localOnly (b502780)
- The early restore now queues `{"cmd":"applyChargeLimit","limit":-1,"vin":vin,"localOnly":True}`.
- `_applyChargeLimitKwargs` passes `localOnly` only when it is set, as with remoteOnly.
- `VehiclePriority.applyChargeLimit(..., localOnly=False)`: with localOnly, `_dispatch(only=("TeslaBLE",))` skips every module except TeslaBLE. The flag is not forwarded, so module signatures are unchanged.
- Tests:
  - under prefer_ble, BLE fails all 3 attempts → TeslaAPI is never called;
  - localOnly succeeds over BLE;
  - the queue passes localOnly only when it is set;
  - handler and end-to-end expectations are updated.
- Note: if VehiclePriority were not loaded, the queue would resolve TeslaBLE or TeslaAPI directly. Their `applyChargeLimit` takes no `localOnly`, so the early restore would raise TypeError and be logged and dropped (the departure handler is still the fallback). VehiclePriority is in the default module list, so this should not happen in practice.

## 3. Slow probing after the cap (e250fee)
- `DEPARTING_SLOW_PROBE_INTERVAL = 600`. After `DEPARTING_PROBE_CAP`, `_scheduleProbe(vin, now, 600)` schedules the next probe 600 s after the last one. Probing never stops, so a car that leaves later still goes AWAY after 2 failed slow probes.
- Tests:
  - 60 s cadence before the cap;
  - after it, `_timeUntilNextDue` is in (60, 600];
  - no probe until 600 s after the last one, then one per 600 s;
  - a car that drives off hours later goes AWAY and the departure runs.

## Tests
Full suite: 825 passed, 1 warning (pre-existing). test_vehicle_presence.py run 5 times: 107 passed each. black --check clean.

---

# NON_TESLA trust and localOnly everywhere (7295a10)
- `TWCSlave.recordPlugVIN(vin)`, called from the VIN parse in TWCManager.py for both outcomes:
  - a real VIN → `hasReportedVIN = True`, `plugVIN = vin`;
  - "" (all parts empty) → `plugVIN = NON_TESLA`, but only if `hasReportedVIN`. Otherwise it is left as None, because CAN may be off. The flag is per slave and lasts for this run.
  - The open question from the previous section is resolved: a CAN-off TWC's unplug now uses the VIN-less candidate rules.
  - Tests: an empty answer is NON_TESLA only after a real VIN; a CAN-off TWC unplug → `observeUnplug(key, None, excluded)`; the parse calls both.
- `applyChargeLimit` in TeslaBLE and TeslaAPI now accepts `localOnly=False`; HomeAssistant takes it through `**kwargs`.
  - TeslaBLE ignores it.
  - TeslaAPI with `localOnly=True` returns "error" at once: no reads, no `car_api_available`, no command. The departure handler stays the remote fallback.
  - HomeAssistant ignores it.
  - Tests: one per module; the TeslaAPI signature test is updated.
- Full suite: 830 passed, 1 warning (pre-existing). black --check clean.
