# Task 2 review: VehiclePresence tracker core around plug evidence

Range c66f3a2..9fd8493 (b8127c1 brief as written; 9fd8493 user-directed presence-only change). Judged against the brief plus the presence-only change.

How I reviewed it: the VehiclePresence.py hunk is a near-total rewrite, so I read the final file in the checkout (lines 1-721) instead of the interleaved hunk. Caller and test hunks were read from the diff. I ran no tests; nothing raised a doubt that a run would settle.

### Spec Compliance

- ✅ Spec compliant, with the presence-only change applied.
  - State: per-VIN `_home` bool, absent = presumed (VehiclePresence.py:146, 265-274). `state()` returns home/presumed/not_home. `basis()` returns evidence/presumed. `isHome` is HOME or PRESUMED, `isPluggedHome` is HOME only (276-282). No DEPARTING, AWAY, ARRIVING or failed-probe state is left. The other per-VIN dicts are the briefed evidence records (`_plug`, `_inside`, `_reach`) and the carried scheduling state (`_lastProbe`, `_due`). No other state leaks into the tracker.
  - Constants PROBE_INTERVAL/STRONG_EVIDENCE_HOLD/BLE_REACH_MAX_AGE match the brief (86-90). PlugRecord matches (69). The `presenceSources` WARNING is in place (159-165).
  - Transitions all go through `_leave` (688-691) and `_goHome` (683-686):
    - home to not-home: TWC unplug (571-584), a weak or strong unplugged read or edge (605-626), and presumed outside the radius without BLE reach (563-565). Each one queues `onDeparting(vin, True)`.
    - not-home to HOME queues `onArrival`.
    - PRESUMED to HOME runs nothing.
  - Evidence rules:
    - strong vs. weak sources (72).
    - the hold, both directions (594, 614, 660-668).
    - fastCharger is ignored (591).
    - "here" = inside, BLE reach, or named by a TWC (648-654).
    - a TWC naming the car beats a weak unplug (607).
    - live telemetry overrides a TWC unplug, with an INFO log (576-582).
    - stale telemetry (None) does not block the unplug.
    - a weak plug that isn't here yet is still recorded (602).
    - home-by-telemetry nominates a probe when bleApplies (643-646).
  - Ordering: weak plugged then location/contact, and location/contact then weak plugged, both reach HOME (`_reapplyWeakPlugged` 628-634; tests 204-227 and 239-245). The re-apply reads only the latest `_plug` record, so a newer strong or weak unplugged record blocks it.
  - Task-1 observer invariant: each signature is present and unchanged:
    - `nominate` (288), `observeContact` (335), `observeProof` (342), `observeUnplug` (348), `observePlug` (354), `observeLocation` (361), `state` (261), `start`/`stop` (243, 254).
    - `observeTelemetryPlug` (330) gains `edge=True`, which is a compatible superset.
    - Call-site check: I grepped `lib/` for presence calls. They are TWCSlave.py:144/237/255/282, TWCMaster.py:1464, Telemetry.py:198/211, TeslaBLE.py:249/779, TeslaAPI.py:1901/1920 and HTTPControl.py:592/598. All match.
  - Callers: `CarApiVehicle.atHome` uses `isHome` and falls back to the raw fix (TeslaAPI.py:1895-1905). TeslaBLE skips `not isHome` (TeslaBLE.py:779). The config.json block is removed.
  - Lock discipline holds:
    - `_apply` runs under the lock and does no I/O.
    - `twcVins`, `bleApplies` and `pluggedIn` are evaluated before the lock (427-441).
    - The home-proof hook runs unlocked (446-450).
    - `nominate` is called after the apply loop releases the lock (454-455).
    - Handlers run unlocked, each after a short locked state re-check (472-484). A test asserts this (test_vehicle_presence.py:489, 511).
- ⚠️ Cannot verify from the diff:
  - `departingHandler` is now also called for a PRESUMED car found unplugged or outside the radius. When a limit is held, it queues a BLE restore that may not reach the car. Whether that is acceptable until Task 5's reconciler lands is for the controller to decide. The Task 5 brief still assumes a DEPARTING state and needs re-reading against the presence-only model.
  - The spec says "A presumed car gets no Fleet API EVSE" (design.md:19), but `atHome` = `isHome` (TeslaAPI.py:1901) makes every PRESUMED car eligible for the Fleet EVSE path, wakes/polls, `numCarsAtHome` and `minBatteryLevelAtHome` until Task 7. This follows the brief, so it is not a failure here. The controller should confirm that Task 7 narrows every consumer the spec lists: the EVSEs, `updateChargeAtHome` and `vehicleScheduledChargingPending`.
  - `_defaultTwcVins` depends on `TWCSlave.plugVIN`/`NON_TESLA`. I checked that both exist (TWCSlave.py:87, 126).

### Strengths

- The decision table is small, readable and one-to-one. Each row is a named method, and every transition funnels through `_setHome`, which logs old -> new with a reason.
- Observations carry their own timestamp `at`, so batching does not change what a record says.
- `_recordPlug` refuses to let a weak record overwrite a strong one inside the hold. Without that, the next conflicting weak reading would have nothing to lose to. This is a sound interpretive call, and it is documented.
- Handlers are re-checked against the end-of-batch state before they run, so an unplug and a replug in one batch never fire a spurious restore.
- The tests drive the real tracker through `runPass` with a fake clock and assert on observable handler calls. There is also good coverage beyond the brief: hold expiry in both directions, VIN-less no-ops, unlocked lookups, and a real tracker in the TeslaBLE skip test.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. VehiclePresence.py:472-484 and test_vehicle_presence.py:362-371. Handlers are gated on the end-of-batch state, but not on the net transition.
   - A HOME car that is unplugged and replugged in one batch (HOME→HOME net) still gets `onArrival`, and the test enshrines `arrivals == [(V1, None)]`. Symmetrically, NOT_HOME→HOME→NOT_HOME runs `onDeparting` with no net change.
   - Duplicate fires are worse. HOME→NOT_HOME→HOME→NOT_HOME in one batch appends `("departing", vin)` twice (688-691), both entries pass the end-state check (476-480), and `onDeparting` runs twice for one VIN in one pass. Whether that is harmless depends on `departingHandler` deduping, which is outside this diff. The Task 5 reconciler author should see this.
   - Harmless if the handlers are idempotent (Task 5's reconciler), but it is an extra apply over BLE on a flapping TWC.
   - Fix: compare each VIN's state at the start and end of the batch, and fire at most one handler per net change.
2. VehiclePresence.py:594, 614, 652, 660-668, 674-679. Evidence ages are measured with `self._clock()` at apply time, but records are stamped with the observation time `at`.
   - If the thread is delayed past the hold (for example by a slow probe or handler in the previous pass), a weak reading observed inside STRONG_EVIDENCE_HOLD is judged outside it and wins.
   - Fix: compare against the incoming observation's `at`.
3. VehiclePresence.py:628-634 and 648-654. Neither a weak plugged record nor `_inside` ages out.
   - If a telemetry unplug is missed, a days-old "plugged in" plus a fresh BLE contact or location fix at home makes the car HOME while it is parked unplugged.
   - This is consistent with the spec's "evidence persists until unplug evidence", but it is worth a bound or a note for Task 6 (discovery).
4. TeslaBLE.py:774-777. The comment still says "a DEPARTING or NOT_HOME car". DEPARTING no longer exists after 9fd8493.
5. VehiclePresence.py:528-530. `_applyProof` records the source as `"twc"` whatever `source` the proof carried. Only "twc" is used today (TWCMaster.py:1464), so this is harmless for now.
6. VehiclePresence.py:161-165. The presenceSources WARNING fires on key presence even when the value is null or empty. The brief says "if set". Cosmetic.
7. test_teslaapi_presence.py (test_at_home_reads_is_home) and test_teslable_presence.py (test_unplugged_and_not_home_are_skipped_presumed_is_not). The 10-line real-`VehiclePresence(...)` construction is repeated three times verbatim. A small shared factory would remove the duplication.

### Assessment

**Task quality:** Approved

**Reasoning:** The tracker implements the brief's evidence rules and the user's presence-only model exactly. It keeps lock discipline and every Task-1 observer signature. What remains is batching and ageing edge cases that the Task 5 reconciler and Task 6 discovery largely absorb.
