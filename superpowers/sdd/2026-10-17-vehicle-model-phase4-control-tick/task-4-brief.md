### Task 4: The heartbeat is protocol-only: offers are computed on the tick; charging points own car amps; the 6 A spike workaround and dampening are dropped (expected lib Δ ≈ −320)

After Task 3, `receive_slave_heartbeat` still turns the distributor's target into the wire offer: min/probe, `chargeRateControl` branches, the spike, the 5 s decrease hold, dampening, flip tracking and `set_last_amps_offered`'s caps. The spike and dampening (with its flip tracking) are deleted, not ported (a, f). It also writes car amps for a point with no car member.

All of that moves to the tick:
- `TWCSlave.offerFor` is the ported rule set, minus the spike.
- `ChargingPoint.setTargetPower` writes car amps for **every** point: car members' keys; else the TWC's named car; else the anonymous fan-out.

The heartbeat sends `self.offer`. Before the first tick it sends the idle `00` payload (Review Focus 1).

**Files:**
- Modify `lib/TWCManager/TWCSlave.py`:
  - delete 818–1121 (everything after the Task 3 cut, up to and including the `masterHeartbeatData =` line). The positive-offer `cancelStopCarsCharging` inside it (:1114–1116) moves to `controlPass` in this task (F4);
  - delete `set_last_amps_offered` (1180–1253);
  - delete the car-amps helpers 126–174 and 181–183, keeping `minAmpsToOffer` (:175–179, F5); `_ampsKeys` (:86); `APIcontrol` (:94); the imports that become unused (`AMPS`, `known`, `satisfied`, `isAnonKey`, :7–11; `broadcastVehicles`/`located` stay for `pluggedCars`, F22);
  - add `Offer`, `OfferContext`, `offerFor`, `heardFrom` (T3), `plugSessions`, `liftedSession`;
  - `send_master_heartbeat` builds `masterHeartbeatData` from `self.offer`, then the override (:538–539, unchanged), then sends;
  - move the `lastAmpsOffered < 0` init (BASE :721–722) into `offerFor`.
- Modify `lib/TWCManager/EVSEInstance/Gen2TWC.py`:
  - `setTargetPower` stores `self.pointAmps`;
  - delete `_evseTargetAmps`, `pointOwnsAmps` and the `lastAmpsDesired` compat write;
  - keep `minAmps`, `maxOfferAmps`, `layerFloorAmps` and `_rangeOverride`.
- Modify `lib/TWCManager/EVSEInstance/ChargingPoint.py`: add `anonymousCars(master, slave)` (moved from `TWCSlave._anonCars`) and `ChargingPoint._carKeys()`; `setTargetPower` handles a TWC-only point the way it handles a point with car members; add `confirmed()`.
- Modify `lib/TWCManager/TWCMaster.py`:
  - `controlPass` builds one `OfferContext` and sets `slave.offer = slave.offerFor(slave.pointAmps, ctx, now)` for every slave **with `heardFrom` True** (F9; an unheard slave keeps `offer is None`, so its heartbeat sends `00`). With `distribute=False` it uses `self.chargingPoints()` for `ctx.confirmed`;
  - then, for each such slave with a key and `offer.amps > 0`, `cancelStopCarsCharging(key)` (BASE :1114–1116, any protocol), **skipped during the chargeStopMode-2 silence** (`respondToSlaves == 0` and `respondToSlavesExpiry` in the future: BASE returned from `send_master_heartbeat` and got no replies, so neither ran, F7);
  - delete `spikeAmpsToCancel6ALimit`, `getSpikeAmps` and `setSpikeAmps`;
  - `observeChargingSessions`'s session end (:1317) bumps `slaveTWC.plugSessions`;
  - fix the stale spike comment in `getMaxAmpsForTargetGridUsage` (:951–955).
- Modify `lib/TWCManager/TWCManager.py:1232–1242`: drop `setSpikeAmps`.
- Modify `lib/TWCManager/Control/HTTPControl.py:2005–2012`: drop the spike checkboxes block.
- Modify `lib/TWCManager/Control/themes/Default/debug.html.j2:112–117`: drop the "Spike Amps" row.
- Modify `lib/TWCManager/Vehicle/Providers/Gen2TWCProvider.py`: fix the `:84` comment naming `send_master_heartbeat`; `setAmps` is unchanged (it calls `setTargetPower`).
- Modify `docs/Debug.md` (delete "Spike Amps") and `docs/modules/Interface_RS485.md:38` (same rules, "the control tick" for "the heartbeat").
- Tests: `test_gen2_idle_minimum.py`, `test_amps_reconciler.py` (:30, :68–89, :100, :102, :105, :157–187, :198), `test_limit_wiring.py:308`, `test_charging_points.py`, `test_twcslave.py`, `test_gen2twc_provider.py:184`, `test_command_path_parity.py:892,897,1082` (plumbing), and `test_control_tick.py`. `test_twcmaster.py` is untouched (F12). `test_twcslave.py:176` `test_slave_heartbeat_data_default` keeps passing (class default).

**Interfaces:**
- Consumes: `controlPass`, `tickThenBeat` (Task 3).
- Produces:
  - `TWCSlave.Offer = NamedTuple("Offer", [("amps", float), ("desired", float)])`, immutable, written by the tick only. `TWCSlave.offer: Optional[Offer] = None`.
  - `TWCSlave.pointAmps: float = 0`: the distributor's raw target (watts → amps), written by `Gen2TWC.setTargetPower`. Named so that `test_no_legacy_command_paths.py:19`, which bans the string `targetAmps` in `lib`, stays meaningful (F3).
  - `OfferContext = NamedTuple(...)` with fields `budgetAmps: float` (`getMaxAmpsToDivideAmongSlaves()`), `carsCharging: int` (`num_cars_charging_now()`), `mode: int` (`chargeRateControl`), `totalAmpsInUse: float`, `confirmed: Dict[bytes, bool]` (TWCID → car rate confirmed, from `ChargingPoint.confirmed()`).
  - `TWCSlave.offerFor(target: float, ctx: OfferContext, now: float) -> Offer`. It updates `lastAmpsOffered`/`timeLastAmpsOfferedChanged` and publishes `amps_offered`/`amps_desired`.
  - `TWCSlave.plugSessions: int = 0` (serial; `observeChargingSessions` bumps it at each session end, replacing the `_resetVehicleRateRaised()` call at `TWCMaster.py:1317`) and `TWCSlave.liftedSession: Optional[int] = None` (tick). `TWCSlave.vehicleRateRaised` becomes a read-only property `liftedSession == plugSessions`. `ChargingPoint` sets `local.liftedSession = local.plugSessions` after a lift, and `None` where BASE called `_resetVehicleRateRaised()`: mode 3 below the floor (`ChargingPoint.py:191`) **and** every pass in which the car carries, i.e. mode 2 or mode 3 below 6 A, for every point type (BASE `TWCSlave.py:934`, F6). So a runtime switch from mode 2 to mode 1 mid-session lifts again, as at BASE. `test_amps_reconciler.py:105`, which assigns `s.vehicleRateRaised = True`, sets `s.liftedSession = s.plugSessions` instead (PLUMBING-ONLY).
  - `ChargingPoint._carKeys() -> List[str]`, `ChargingPoint.confirmed() -> bool`, and `anonymousCars(master, slave) -> List[Vehicle]`, with `_anonCars`'s semantics exactly.

**`offerFor`: the ported rules, in BASE order, spike and dampening removed.** It is written out here because the tests do not fix the order.

```python
def offerFor(self, target, ctx, now):
    if self.lastAmpsOffered < 0:
        self.lastAmpsOffered = self.reportedAmpsMax         # BASE receive :721
    minOffer, n = self.minAmpsToOffer(), ctx.carsCharging
    desired = target
    if desired < minOffer:
        # idle-TWC probe (not counted against the budget) or a stop
        desired = self.minAmpsTWCSupports if n and ctx.budgetAmps / n > minOffer else 0
    elif ctx.mode == 2 or (ctx.mode == 3 and desired < 6):
        self.liftedSession = None                             # BASE :934, every pass (F6)
        desired = self.wiringMaxAmps if ctx.confirmed.get(bytes(self.TWCID)) else int(desired)
    else:
        desired = int(desired)
        if desired < self.lastAmpsOffered and now - self.timeLastAmpsOfferedChanged < 5:
            desired = self.lastAmpsOffered                   # BASE :1080-1091, kept (not spike)
    amps = self._capped(desired, ctx.totalAmpsInUse)        # BASE set_last_amps_offered caps, every pass (e)
    if amps != self.lastAmpsOffered:
        self.lastAmpsOffered, self.timeLastAmpsOfferedChanged = amps, now
    self._publishStatus("amps_offered", "ampsOffered", amps, "A")
    self._publishStatus("amps_desired", "ampsDesired", desired, "A")
    return Offer(amps, desired)
```

`_capped(desired, total)` applies two caps, keeping BASE's messages and levels:
- If `total - reportedAmpsActual + desired > wiringMaxAmpsAllTWCs`, use `int(wiringMaxAmpsAllTWCs - (total - reportedAmpsActual))`, never below `minAmpsTWCSupports`, and log the BASE INFO "WARNING: Offering slave TWC …" line. Log it only when the capped value differs from the last one logged (`_cappedLogged`), so a sustained cap does not log every second.
- Then cap at `wiringMaxAmps`, with the BASE DEBUG line.

The `cancelStopCarsCharging` on `offer.amps > 0` (BASE :1114–1116) moves into `controlPass` in this task, so no task leaves it out (F4).

**`ChargingPoint.setTargetPower`, generalised.** BASE (`:153–198`) runs the layered branch only when the point has car members (`cars`). From now on the car side is `keys = self._carKeys()`:
- car members' `vehicleKey`s;
- else, when the local member is a Gen2 with a `vehicleKey`, `[that key]` for a VIN, or `[v.key for v in anonymousCars(master, local)]` for an anonymous key;
- else `[]`.

Rates keep BASE's labels (F13): a car member's rate goes through `VehicleEndpoint.setTargetPower` (`by="distributor"`), and a rate for a key with no `VehicleEndpoint` (the TWC's own VIN, or the anonymous fan-out) is written as `desired.set(k, AMPS, amps, "heartbeat")`, as BASE's heartbeat path wrote it. Lifts stay `desired.set(k, AMPS, wiringMaxAmps, "lift", lift=True)` once per session (`local.vehicleRateRaised`). A key that left the set since the last pass gets its rate cleared **only if `d.by == "heartbeat"`** (BASE `_clearCarAmps` :150–155), so a TWC point never clears a `VehicleEndpoint`'s rate for the same car. The point keeps `_lastKeys` on the local member, written only by the tick.

`confirmed()` is BASE `_carRateConfirmed` over `keys`.

The modes follow BASE `carriers()`:
- **mode 1 (TWC carries):** no car rate, plus the lift. The lift is unconditional for a TWC-only point (BASE heartbeat `TWCSlave.py:953–954`). For a point with car members it applies only when the member's request is below the offer (BASE `ChargingPoint.py:181–182`).
- **mode 2:** the car carries.
- **mode 3:** layered at `layerFloorAmps()`.

- [ ] **Step 1: Write the failing tests.**
  - Characterization (BASE+after, with `tickThenBeat`, spike settings 0 at BASE):
    - `test_idle_twc_nobody_charging_sends_zero`
    - `test_idle_twc_probe_when_budget_per_car_exceeds_min` / `..._zero_when_it_does_not`
    - `test_charging_twc_gets_whole_amps_of_its_share`
    - `test_a_decrease_within_5s_is_held_then_applied`
    - `test_all_twc_wiring_cap_uses_others_actual_draw_and_floors_at_twc_minimum`
    - `test_per_twc_wiring_cap`
    - `test_mode_2_offers_the_twc_max_once_the_car_rate_is_confirmed`
    - `test_mode_3_below_six_layers_the_car_and_holds_the_twc_floor`
    - `test_mode_1_lift_goes_once_per_session_for_a_twc_only_point` (BASE: heartbeat path; after: point path; same desired value, `lift=True`)
  - New behaviour:
    - `test_heartbeat_before_the_first_tick_sends_no_change` (Review Focus 1): a new slave, `offer is None`, so `send_master_heartbeat` sends bytes 6..14 == `bytes(9)`. Re-run Task 3's `test_restart_with_a_car_charging_never_offers_zero` against the `offer` path.
    - `test_the_lift_survives_a_session_end_racing_the_tick`: `liftedSession` set for session 3, the serial thread bumps `plugSessions` to 4, the next pass lifts again.
    - Characterization (BASE+after): `test_a_mode_2_to_1_switch_mid_session_lifts_again` (F6).
    - Characterization (BASE+after): `test_a_twc_point_never_clears_a_vehicle_endpoints_rate` (F13): an anonymous point whose fan-out (`vehicles[0]`) drops the car while its `VehicleEndpoint` holds a `"distributor"` rate leaves that rate in place.
    - `test_no_offer_or_cancel_for_an_unheard_slave` (F9) and `test_no_stop_cancel_during_the_mode_2_silence` (F7).
    - `test_wiring_cap_is_rechecked_when_others_draw_more` (e): the offer is unchanged at 20 while another TWC ramps from 20 to 40 on an 48 A circuit, so the next pass offers 8.
    - `test_green_policy_does_not_hold_a_car_below_the_minimum` (f): Track Green, share falls from 10 to 3 while drawing, so the next offer is the probe/stop rule's value at once, not a held `minAmpsTWCSupports`.
    - `test_spike_settings_are_ignored` (a): `spikeAmpsProactively=1` with a car at 6 A offered 12 A sends 12, never 16/21.
    - `test_no_car_amps_code_left_in_the_slave`: `TWCSlave` has none of `_setCarAmps`, `_clearCarAmps`, `_carRateConfirmed`, `_queueChargeRate`, `_requestVehicleRateRaise`, `_anonCars` or `APIcontrol`.
    - `test_receive_writes_no_offer` (static): `receive_slave_heartbeat` source has no `offer`, `lastAmpsOffered =` or `desired.`.
- [ ] **Step 2: Run** them at BASE (scratch checkout of 1029809b; the characterization set must PASS) and on the branch (the new-behaviour set must FAIL). Record both.
- [ ] **Step 3: Implement** as above.
  - `controlPass` uses the points `distributeEVSEPower` returned for `ctx.confirmed`.
  - `test_amps_reconciler.py` rows that call `s._queueChargeRate(x)` or the other removed helpers (:30, :100, :102, :157–187, :198) become `pt.setTargetPower(convertAmpsToWatts(x))` on the slave's point followed by `offersThenBeat`, or `tickThenBeat`. That is PLUMBING-ONLY when the desired value is unchanged. Rows asserting `d.by == "heartbeat"` keep that assertion: the label is unchanged (F13).
  - `test_twc_only_point_keeps_the_heartbeat_path_under_mode_2` and `test_heartbeat_does_not_write_amps_for_a_point_with_a_vehicle_member` are replaced by `test_a_twc_only_point_writes_the_cars_amps_under_mode_2` (same desired values).
  - `test_gen2_idle_minimum.py::offers(spike=...)`: drop the parameter. Rows asserting the same values with spike on and off keep the spike-off assertion (PLUMBING-ONLY). Any row asserting a spike value is INTENTIONALLY CHANGED (a).
  - `test_twcmaster.py:600–670` (`subtractChargerLoad` regressions with "spike" in their names) are kept unchanged; only a stale comment, if any, is reworded (F12).
  - `test_twcslave.py`: `test_slave_api_control_default` is deleted (no replacement: the attribute is gone); `test_slave_last_amps_desired` is deleted, INTENTIONALLY CHANGED (f); `TestVehicleChargeRateDesired` maps to the point-path tests above; `test_heartbeat_code_never_calls_set_charge_rate_inline` is kept (still true).
- [ ] **Step 4: Run** the characterization and new tests, `test_command_path_parity.py`, `test_amps_reconciler.py`, `test_charging_points.py` and `test_gen2_idle_minimum.py` → PASS. Parity counts are untouched.
- [ ] **Step 5: Full suite** → PASS. Grep (Global scope, tests/unit included) for `spikeAmps|getSpikeAmps|setSpikeAmps|_evseTargetAmps|pointOwnsAmps|_setCarAmps|_clearCarAmps|_carRateConfirmed|_queueChargeRate|_requestVehicleRateRaise|_resetVehicleRateRaised|_anonCars|APIcontrol|set_last_amps_offered`. Expect no hits apart from `test_twcmaster.py`'s kept `*_spiked` test names; `docs/Debug.md` is gone from the hits too. `test_no_legacy_command_paths.py` still passes (no `targetAmps` in lib).
- [ ] **Step 6: Commit.** `git commit -m "Compute TWC offers on the control tick; charging points own car amps; drop the 6 A spike workaround"`. The body names (a) for the PR.

---

