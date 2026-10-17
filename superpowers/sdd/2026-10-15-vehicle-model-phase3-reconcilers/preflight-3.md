# Pre-flight 3 — narrow check of the third revision

Scope: only the 17 items still open after pre-flight 2 (N1–N13 and the partials F11, F26, F37, F38), and the sections this revision touched. Plan: 1356 lines. Base: 6a6c14e (the scratch copy).

## What was checked, and how

- **The sections this revision touched**:
  - Task 1 store: round reset on a desired change, `notBefore`, `noteOffering`.
  - Task 4 `gen2_helpers.drive`.
  - Task 5 `wakeOutcome` with `is_awake(now=)`.
  - Task 6 step 1 settled gate, step 3 adoption, `beforeWrite`, `report`, and the new tests.
  - Task 7 `presentVehicles(capability)` and its test.
  - Task 8 heartbeat observe, `_stopIsForced`, `policyAmpsRequested`, offering, and the new tests.
  - Task 9 heartbeat test.
  - Task 11 row-4 sample.
  - Decisions 32–35.
- **Ran against the base copy**:
  - A `drive()` written to the plan's spec, run against the `make()` / `setup()` masters, failed three separate ways:
    1. `getModuleByName` is a Mock that returns None, so `receive_slave_heartbeat` fails at TWCSlave.py:660 with `AttributeError: 'NoneType' object has no attribute 'fireWebhook'`, even after a Policy module is registered.
    2. `CONFIG` has no `fakeMaster`, so `print_status` (TWCSlave.py:139) raises `KeyError`.
    3. `make()` builds `TWCMaster("AB", …)` with a str TWCID, so `send_master_heartbeat` raises `TypeError: can't concat str to bytearray`.
- **Read at base**:
  - `recordVehicleVIN`: it sets `currentVIN` before `observeTwcVin` confirms the VIN (TWCMaster.py ~1495).
  - `num_cars_charging_now`: it has side effects (session start and end, a Status publish per slave).
  - `setMaxAmpsToDivideAmongSlaves` is the only writer of the budget; `TWCMaster.__init__` never calls it.
  - `is_awake`: a 120 s cache.
- **Threading rule:** a registry `observe` on the serial thread takes only leaf locks (`FieldStore`, `Vehicle._lock`) and does no I/O. That is the same pattern Phase 1 already allows for the TWC VIN, so it is permitted, provided it is guarded (S1).

## 1. Status of the 17 items

| Item | Status | Evidence / gap |
|---|---|---|
| N1 | RESOLVED | Step 1 settled gate (new evidence after `settledAt`, plus `notBefore = settledAt + RETRY` for an unstamped settle); `receive_slave_heartbeat` observes `actualCurrent`. Tests for N1(a) (fake clock and real clock) and N1(b). Follow-ups in S1, S4. |
| N2 | RESOLVED | Step 3 compares CHARGING values as charging-like versus stopped-like, mapping both the stamp and the read. |
| N3 | RESOLVED | `noteOffering` with `offering`/`offeringSince`; a stopped-looking read while nothing is offered is hands-off; `test_a_stop_caused_by_our_own_zero_offer_is_hands_off` pins it. Gap in S6. |
| N4 | RESOLVED | `report` clears `inFlight` only when `rec.inFlight is attempt` (probes the same way); a stale report is logged at DEBUG. |
| N5 | **PARTIAL** | `tests/unit/gen2_helpers.drive` is specified, but against the `make()`/`setup()` masters Tasks 4, 8 and 9 use it fails three ways (confirmed above). Ruling: `drive` replaces `getModuleByName` with a dict lookup (as `test_gen2_idle_minimum.real` does), adds `fakeMaster` and `displayMilliseconds` to both `master.config["config"]` and `slave.configConfig`, and sets a bytes `master.TWCID`; or those tests build their master with `real()`. |
| N6 | RESOLVED | Task 3 Files rewrite both debug tests; `tries_each_provider_once` becomes one provider per command. |
| N7 | RESOLVED | `wakeOutcome` → `is_awake(slot, now=now)`; the provider passes its own clock. |
| N8 | RESOLVED | A settled apply leaves the desire unadopted. |
| N9 | RESOLVED | The test now expects no anonymous car in mode 1 and adds a slave on 8245 for mode 2. A new defect in the same test: S5. |
| N10 | RESOLVED | `trusted(field, exclude=)` in step 3. |
| N11 | RESOLVED | Decision 34: `holding()`/`vins()` return VIN keys only. |
| N12 | RESOLVED | A desired change starts a new round (`set` resets the record). Side effect: S3. |
| N13 | RESOLVED | `presentVehicles(master, capability)`; `targetsFor(…, capability)`. |
| F11 | RESOLVED | No stamp after a disruptive stop; the heartbeat's readings drive satisfaction; re-sent on a newer reading after `RETRY`. |
| F26 | RESOLVED | `test_a_free_success…` asserts `f.calls == ["wake", "startCharging"]` and `len(cmds(f)) == 1`. |
| F37 | RESOLVED | `_stopIsForced` uses `policyAmpsRequested` (recorded before the wiring clamp); the test covers 16 A shared by 3 cars. Needs a default value: S2. |
| F38 | RESOLVED | The row-4 counts are corrected (no `vehicle_data` while asleep, one free check cached for the wake, no second wake). TeslaAPI's `time.time` is patched to the test clock. |

**Totals: 16 resolved, 1 partial (N5), 0 not resolved.**

## 2. New findings in the touched sections

Commands that can repeat were checked one by one: a disruptive stop, a SATISFIED start or stop, a retry after a backoff reset, a start while nothing is offered, and the heartbeat stop path. No new High. Six Medium, two Low.

### Medium

**S1 — The serial-thread observe has no None guard (Task 8).**
Plan text: "`registry.get(self.vehicleKey).observe("actualCurrent", …)` whenever `vehicleKey` is set".
`recordVehicleVIN` sets `currentVIN` before `observeTwcVin` confirms it, so while a new VIN is pending or rejected, `vehicleKey` names a VIN the registry does not hold. `registry.get` then returns None, and `.observe` raises AttributeError in `receive_slave_heartbeat` on every heartbeat, on the serial thread.
The observe itself is allowed: leaf locks, no I/O, the same as the TWC VIN write Phase 1 permits.
Ruling: `v = registry.get(key); if v is not None: v.observe(…)`.

**S2 — `policyAmpsRequested` has no default, and `_stopIsForced` re-runs a function with side effects (Task 8).**
- The attribute is set only in `setMaxAmpsToDivideAmongSlaves`, which `TWCMaster.__init__` never calls. A heartbeat stop before the first policy pass therefore raises AttributeError on the serial thread, and the `drive`-based Task 8 tests that never set a budget hit it too.
- `_stopIsForced` calls `num_cars_charging_now()`, which publishes Status per slave and runs session start and end transitions. Calling it a second time from inside the heartbeat duplicates those.

Ruling: class default `policyAmpsRequested = 0` (not forced), and pass the heartbeat's own `numCarsCharging` into `_stopIsForced`.

**S3 — A desired change resets the paid backoff too (Task 1, from the N12 fix).**
Plan text: `set` "returns True when desired changed — and then the aspect's record starts a new round: `newRound()`, `backoffUntil = 0`, `backoff = 0`, `notBefore = 0`".
- The spec resets backoff on "success/arrival/plug-in".
- On a fast aspect (amps under Track Green Energy, where `VehicleEndpoint.setTargetPower` changes the value every few cycles), a failing Fleet gets a fresh paid attempt for every new value, limited only by the lane's 50-per-minute rate limit.
- This is no worse than today's façade (two Fleet tries per change), but it gives up the backoff the plan claims.

Ruling: a desired change resets the free providers' `tried` (and the backoff when every candidate is free); paid `tried` and backoff persist until success or a session event.

**S4 — The settled gate's "evidence" clause is ambiguous for Tesla cars (Task 6, step 1).**
Plan text: "an observation of `FIELD_FOR[aspect]` (or, for `CHARGING`, of the TWC stand-in `actualCurrent`) with `at > rec.settledAt`".
The heartbeat now observes `actualCurrent` every second for every keyed car. If that counts as evidence for a car whose state comes from `chargingState`, the gate opens every `RETRY`. A Fleet stop that came back SATISFIED `not_charging`, against a stale "Charging" read, is then re-sent every 60 s until `READ_MAX_AGE` forces a read: about 5 paid commands per event.
Ruling: the `actualCurrent` clause applies only when `known()` is actually using the TWC stand-in.

**S5 — `test_present_rule_until_phase_5` cannot run (Task 7).**
Its first assert uses `C.SET_CHARGE_LIMIT`, but `C` is imported later inside the same function (`from TWCManager.Vehicle.Providers import Capability as C`). That makes `C` local to the whole function, so the first use raises UnboundLocalError. Ruling: import `Capability as C` (and `targetsFor`) at module top.

**S6 — The "nothing offered" guard sits behind adoption's preconditions (Task 6, step 3).**
Hands-off for a stopped-looking read while the point offers nothing runs only inside step 3, which first needs an own write and a read newer than both the write and the desire. If the start left no stamp (a Fleet SATISFIED start), or the desire was set after the read, step 4 re-asserts the start while the TWC offers nothing. On Fleet that is `charge_start` (plus a wake when due) on each new reading after `RETRY`, the whole time Track Green Energy is offering 0. Today a start is only requested while offering at least the minimum.
Ruling: a general rule ahead of step 4: `CHARGING` True is not planned while `state.offering` is False, for points that report offering.

### Low

**S7 — The row-4 helper patches `time.time` for the whole process.** It monkeypatches TeslaAPI's `time.time`, which is the global `time.time`, for the test. That works, since the defaults captured at construction are unaffected and token `exp` values are far in the future, but log timestamps and any other `time.time()` caller see the fake clock. A TeslaAPI-local `_now` hook would be cleaner.

**S8 — Task 5's Files and Interfaces do not list the `CarApiVehicle.is_awake(now=)` signature change.** It appears only in the `wakeOutcome` text and Decision 35. Add it to Task 5's Files and Interfaces.

## Counts

17 items: 16 resolved, 1 partial (N5), 0 not resolved. New: High 0, Medium 6 (S1–S6), Low 2 (S7, S8).
