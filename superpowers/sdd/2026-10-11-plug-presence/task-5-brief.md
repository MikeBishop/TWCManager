### Task 5: Departure restore: BLE right away, a remote fallback when BLE has gone, re-plug cancels

> **Superseded in part (user-directed, 2026-10-11):** the tracker (Task 2) holds presence only: `home` plus `basis` ("evidence" | "presumed"). There is no DEPARTING state. Implement this task as a **reconciler** on presence × held limit. "Departing" below means *not home while `_restorePending(vin)`* (`hasSaved and lastApplied != -1`). `DepartingRecord` keys off that condition, starting when a car goes not-home with a limit held. The held-limit-after-restart and BLE-retry rules need no special cases: a presumed car read unplugged calls `onDeparting`, the handler restores if anything is held, and the probe loop retries while held and reachable. Keep the constants, the 5-minute fallback, the remote-immediately-without-BLE rule and the tests, with names adapted (`DEPARTING` → "not home with a held limit").

**Files:**
- Modify: `lib/TWCManager/PresenceHandlers.py`, `lib/TWCManager/VehiclePresence.py`
- Test: `tests/unit/test_presence_handlers.py`, `tests/unit/test_vehicle_presence.py`

**Interfaces:**
- Produces, in `PresenceHandlers.py`:
  - `bleApplies(master, vin) -> bool`: TeslaBLE is loaded and `settings["Vehicles"][vin]["bleProven"]` is set. `VehiclePresence`'s default `bleApplies` uses it.
  - `departingHandler(master)` → `onDeparting(vin, unambiguous) -> bool`. If nothing is held (`not hasSaved or lastApplied == -1`), it returns False. If `bleApplies`, it queues the `localOnly` restore (carried). Otherwise it does what `departureHandler` does, immediately: `remoteOnly` if `hasRemoteChannel`. The `unambiguous` argument is kept for the signature. Task 4 always passes True, so its False branch can't be reached; leave that branch in place and don't write a test for it.
  - `departureHandler(master)`: unchanged. It is the remote restore, called by the tracker only as the BLE-gone fallback.
  - `arrivalHandler`: before anything else it calls `master.vehicleCommandQueue.cancel("applyChargeLimit", lambda t: t.get("vin") == vin and t.get("limit") == -1)`.
- In `VehiclePresence`:
  - Constants: `DEPARTING_PROBE_INTERVAL = 60`, `DEPARTING_PROBE_CAP = 1800`, `DEPARTING_SLOW_PROBE_INTERVAL = 600`, `BLE_GONE_RESTORE_AFTER = 300`.
  - `_departing: dict[vin, DepartingRecord]`, where `DepartingRecord` is a dataclass with `since: float`, `viaBle: bool`, `bleGoneSince: float | None = None` and `fallbackSent: bool = False`. It is created on entry to DEPARTING and dropped on exit.
  - `_restorePending(vin) -> bool` is `hasSaved and lastApplied != -1`, from `master.getNormalChargeLimit(vin)`.
  - While a car is DEPARTING with `viaBle`, a restore pending and no fallback sent yet, it gets a `_probe(vin, bleOnly=True)` every `DEPARTING_PROBE_INTERVAL` (every `DEPARTING_SLOW_PROBE_INTERVAL` once `since` is older than `DEPARTING_PROBE_CAP`). Reach False sets `bleGoneSince` if it isn't set; reach True clears it. When `now - bleGoneSince >= BLE_GONE_RESTORE_AFTER` and the restore is still pending, the tracker runs `onDeparture(vin, None)` once and sets `fallbackSent`. When the restore is no longer pending, probing stops. A car without BLE (`viaBle` False) is never probed.
  - **BLE restore retry (controller ruling, user-approved):** while DEPARTING with `viaBle`, a restore still pending, and a probe that finds BLE reachable, re-queue the `localOnly` restore (at most once per probe interval, and only if no `applyChargeLimit` -1 for that VIN is already queued). That covers a BLE restore that failed while the car stayed in range.
  - **Held limit after a restart (controller ruling, user-approved):** when discovery finds a PRESUMED car unplugged *and* `_restorePending(vin)` is true (TWCManager holds a limit on it from before the restart), the car goes to DEPARTING instead of NOT_HOME, so `onDeparting` runs the normal restore (BLE first, then the remote fallback). With nothing held, it stays NOT_HOME and nothing is sent, as before.

- [ ] **Step 1: Write the failing tests**

```python
# test_presence_handlers.py
def test_departing_ble_car_queues_one_local_restore():      # queued == [{"cmd":"applyChargeLimit","limit":-1,"vin":V1,"localOnly":True}]
def test_departing_non_ble_car_queues_one_remote_restore_now():  # bleProven False, Fleet token, prefer_ble -> remoteOnly True
def test_departing_non_ble_car_without_remote_channel_queues_nothing():  # ble_only
def test_departing_with_nothing_held_queues_nothing():
def test_arrival_cancels_a_pending_restore_first():
# test_vehicle_presence.py
def test_ble_gone_for_five_minutes_sends_one_remote_restore():  # probes fail from t=0; at t=299 no onDeparture; at t>=300 exactly one
def test_ble_gone_fallback_needs_a_remote_channel():       # with the real departureHandler and ble_only: nothing queued
def test_ble_restore_done_stops_probing():                 # lastApplied -> -1: no further due times for V1
def test_replug_before_fallback_cancels_it():              # plugState(True,"ble") at t=120 -> HOME; no onDeparture ever
def test_reachable_probe_resets_the_gone_timer():
def test_departing_probes_slow_after_the_cap():
def test_non_ble_departing_car_is_never_probed():
def test_failed_ble_restore_retried_while_still_reachable():  # restore fails; next reachable probe re-queues one localOnly restore; none while one is queued
def test_presumed_car_found_unplugged_with_held_limit_departs_and_restores():  # saved (True,100,50): DEPARTING + one restore
def test_presumed_car_found_unplugged_with_nothing_held_goes_not_home():       # saved (True,100,-1): NOT_HOME, nothing queued
```

Move `TestDepartAndReturnThroughTheQueue` here. It now runs unplug → DEPARTING → plug evidence → HOME through the real handlers and the queue, and asserts that the HOME apply replaces the restore.

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `bleApplies`, the handler changes, `DepartingRecord`, the BLE-only probe schedule and the fallback timer**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_presence_handlers.py tests/unit/test_vehicle_presence.py -q`.

- [ ] **Step 5: Commit**

Subject: `Restore on unplug over BLE, then remotely once BLE has been gone 5 min`.

---

