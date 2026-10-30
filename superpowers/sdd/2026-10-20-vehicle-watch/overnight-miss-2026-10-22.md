# Missed overnight charge, 2026-10-22 — root cause

Box: deploy/phase6-diag d62b20f3 = vehicle-model/phase6 62a0e08c + DIAG. Read-only investigation (journal, read-only HTTP API, settings/config non-secret keys). Local tree: scratchpad `wt-vm6` at 62a0e08c.

## Root cause

The car's charging endpoint caps its charging point at the charger's own pilot, and on a Gen2 TWC that pilot is TWCManager's last offer. Once the car had been read while the TWC sat at its 6 A sleep pilot, the point could never be offered more than 6 A again, and with the TWC's measured voltage above 240 V the target rounded down to 0 — the TWC's idle minimum, `offered[VIN] = 0`, "nothing offered", no wake, no start, all night.

- `lib/TWCManager/Vehicle/Providers/Provider.py:109-113` — `vehicleMaxAmps` returns `vehicle.value("availableCurrent")` (the charger's pilot, `chargerPilotCurrent` over BLE / `charger_pilot_current` from TeslaMate and the APIs) before the wiring fallback. Introduced in 60836e47 "Add vehicle providers and a fixed provider order" (Phase 2).
- `lib/TWCManager/EVSEInstance/VehicleEndpoint.py:79-82` — `VehicleEndpoint.maxPower = vehicleMaxAmps × currentVoltage`, where `currentVoltage` is the car's last-read voltage or the 240 V default when the car reports < 90 V (it does while not charging). 4118bec0 (Phase 3).
- `lib/TWCManager/EVSEInstance/ChargingPoint.py:64-67` — `ChargingPoint.maxPower = min(e.maxPower for e in self.endpoints)`: the car member's cap binds the TWC's point. `minPower = max(...)` (`:59-62`) is the TWC's `minAmpsToOffer × its measured volts`. 415493d7 "Group charging endpoints into charging points" (Phase 3).
- `lib/TWCManager/TWCMaster.py:649-650` — `if 0 < offer < point.minPower: offer = 0`. With `availableCurrent = 6`: car cap 6 × 240 = 1440 W; TWC minimum 6 × 243 = 1458 W; target 0. At 240 V on the TWC the two are equal and the target is 6.0 A — the same 6 A the TWC already shows.
- `lib/TWCManager/TWCMaster.py:678-686` — `self.offered[VIN] = 0` (the car is a member, so its key is written last, overriding `heldKey`).
- `lib/TWCManager/Vehicle/Reconcile/Belief.py:124-125` — `whyQuiet` → `"nothing offered"`; `Reconciler.py:325-326` makes `wakes` False; `Run.py:164-165` then holds the BLE limit attempt on a known-asleep car: the 00:00:04 `held: asleep`. The ruling was applied correctly to a wrong offer.
- `lib/TWCManager/TWCSlave.py:160-166` — `offerFor` turns a target below `minAmpsToOffer` into `Offer(0, 0)` → `_amps_heartbeat` sends `09 00.00 A` → the Gen2 holds its hardware minimum, 6 A; `chargeGate` (`:225-249`) answers `withdraw`, never `start`.

Nothing in Phase 6 changed these lines. The latent fault became visible because the registry held a 6 A pilot reading: TeslaMate telemetry is off (no live pilot updates), the 21:10 restart emptied the registry, and the first read of the car after a BLE wake happened while the Gen2's pilot was at the 6 A it holds for a sleeping car.

## Evidence chain (journal, `/tmp/n.log` on the box; config via the API)

Config/settings: `chargeRateControl 1`, `wiringMaxAmpsAllTWCs 48`, `wiringMaxAmpsPerTWC 48`, `minAmpsPerTWC 6`, `defaultVoltage 240`, policies 48 A, `scheduledLimit 70`, `nonScheduledLimit 50`, `startStopDelay 300`, TeslaMate `syncTelemetry false`.

1. 21:10:57 restart. TWC 8244 replies `03 00.00/47.00` (the 47 is what the previous process commanded; the car is asleep). Registry is empty of car readings: the DIAG `pick` line at 21:11:04 shows `state=None pilot=None amps=None`.
2. 21:11:04 attribution names the car on 8244 (`reached=True` → twcVin). 21:12:02 limit attempt: BLE read fails on the sleeping car ("could not read the current limit"). 21:12:05 BLE wake for the mode-1 lift; 21:12:15 `setAmps` done (48 A lift).
3. 21:12:07 TWC `03 → 00`, max 47. At 00 a Gen2 names a car only through `currentVIN` (read only on a charge start, `TWCMaster.py:1325-1337`), so `Gen2TWC.vehicleKey` is None (`Gen2TWC.py:48-49`, PLUGGED_STATES): two points, exactly the shape `test_gen2_at_00_with_a_sleeping_car_is_two_points` pins. The TWC's own point gets the full share: 48 × 240 / 243 V = 47.4 → 47 A, master heartbeat `00` (no change) — the 47 seen until 21:24:30.
4. 21:12:34 `TWC 8244: plugged in: {VIN: True}`: `checkPlug`'s read cascade (`Presence.py:237`) and the watch's plug-in event read both read the car over BLE here (reads log at DEBUG only, so their values are not in the journal). They are the only reads before 21:24:30.
5. 21:24:30 the car has gone back to sleep; the TWC drops to `03 00.00/06.00` on its own (ledger 2026-10-20: "car sleeps → 03@6A"). State 03 is a plugged state, so `vehicleKey` now returns the attributed car: the two points merge into one, and the car endpoint's cap applies. The very next tick: `M: 09 00.00/00.00A` — target 0. For that the car's `availableCurrent` had to be ≤ 6 already, i.e. the 21:12:34 reads saw a 6 A pilot (the Gen2's pilot for a car that slept under it; its heartbeat max had not been renegotiated with the car). I could not confirm the pilot value directly — reads are not logged at INFO.
6. 21:24 → 07:08: `03 00.00/06.00A  M: 09 00.00/00.00A` unchanged. No tick failures (no "Control tick" or level-30/40 lines besides the one BLE retry), so `withdrawOffers` never ran; the 0 is the distributor's own answer.
7. 00:00:01 Scheduled Charging (48 A, limit 70) changes nothing the point sees; 00:00:04 the limit is `held: asleep` because `whyQuiet` says "nothing offered" (`offered[VIN] == 0`), so the attempt may not wake.
8. The confirmation that `availableCurrent == 6` with the car's voltage defaulted to 240 V: between 06:23 and 07:06 the master heartbeat flipped `M: 00` ↔ `M: 09 0 A` eight times, and every `M: 00` (offer 6 == the TWC's 6) coincides with the TWC reporting 240 V, every `M: 09` with 241 V (06:23:15/16, 06:24:16/18, 06:52:50/52, 06:53:51/53, 06:56:55/57, 06:57:56/58, 07:04:05/07, 07:06:07/09). Only a car cap of 6 × 240 W against a TWC minimum of 6 × V_twc produces that.
9. 07:08 the car woke itself (09), 07:10:22 charging at 6.25 A; Phase 6's power-start `readNow` (`TWCMaster.updateChargeAtHome`) re-read the car at the 6 A pilot, ~242 V. At 07:45 the car is still charging at 6 A with 48 A available under Non Scheduled Charging, `M: 00` at 240–242 V: the live box is in the stuck-at-6 A variant now. `/api/getSlaveTWCs`: `lastAmpsOffered 6`, `reportedAmpsActual 6.16`, `state 1`.

Previous builds charged at 47 A (e.g. 2026-10-20 00:00:52) because their registry never held a ≤ 6 A pilot when the point merged: telemetry was live, or the car had last been read at a 47/48 A pilot (DIAG 2026-10-20 13:57:18 `pilot=47` three seconds after the TWC went to 47; 2026-10-21 10:05:41 `pilot=48`).

## Suspects ruled out

- 6cc3eb6b (Phase 6, `VehicleEndpoint.wantsToCharge` asleep-after-Charging): the point's `wantsToCharge` is the TWC member's (`ChargingPoint.py:46-49`), and the Gen2 reports max 6 > 0. Reverting the rule in the scratch test changes nothing.
- `withdrawOffers`: never called (no tick failures logged; it logs at WARNING/ERROR).
- `Gen2TWC.heldKey` / the offer map: only decides the key; the car is a point member so `offered[VIN]` is written from `carKeys` either way, and 0 is the real target.
- F3 "awake within 5 min" gate, Fleet asleep hold: the limit went over BLE; the hold came from `whyQuiet`, correctly, given the 0 offer.
- Restart / anonymous session: the plug was attributed at 21:11:04 (twcVin), so the TWC named the car from the first plugged state. The restart matters only because it emptied the registry.
- `whyQuiet` "nothing offered" with the 6 A idle pilot: consistent with the ruling (offer = our target, which was 0).

## Reproducing test

`/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/overnight-miss/test_overnight_miss.py` (outside the repo; 7 tests, all pass against unmodified 62a0e08c). Run from `wt-vm6`:

```
PYTHONPATH=$PWD:$PWD/lib <scratchpad>/venv/bin/python -m pytest -c pytest.ini --rootdir . -p no:cacheprovider -p conftest -o addopts="" <scratchpad>/overnight-miss/test_overnight_miss.py
```

It builds the box's shape with `tests/unit/test_charging_points.real()` (mode 1, 48/48/6 A, 48 A budget), a Gen2 at 03 with max 6 and 243 V, the car attributed by twcVin and asleep, and shows:

- no pilot reading → target 47.4 A, `offered[VIN] > 0`, `whyQuiet` None;
- `availableCurrent 6` (car voltage < 90 V → 240) → `pt.maxPower == 1440 < pt.minPower == 1458`, target 0, `Offer(0, 0)`, `chargeGate == "withdraw"`, `offered[VIN] == 0`, `whyQuiet == "nothing offered"`;
- TWC at 240 V → target 6.0; at 241 V → 0 (the morning flapping);
- charging at 6 A, read at pilot 6 / 242 V → stays 6.0; read at pilot 48 → 47.6 (the cap is our own last offer);
- `carAmpsRange` is `(1, 6)` with the 6 A pilot, so no car provider `covers` the 48 A lift;
- the Phase 5 `wantsToCharge` rule gives the same 0;
- with `vehicleMaxAmps` patched to the car's own maximum: 47.4 A, `Offer(47, 47)`, `chargeGate == "start"`, `whyQuiet` None, lift coverable; a car reporting `chargeCurrentRequestMax 32` is capped at 32.

## Smallest correct fix

`lib/TWCManager/Vehicle/Providers/Provider.py:109-113`:

```python
def vehicleMaxAmps(vehicle, configConfig: dict) -> float:
    # VehicleEndpoint.maxPower's rule: the car's own AC maximum, never the
    # charger's pilot, which on our own charging point is our last offer
    return vehicle.value("chargeCurrentRequestMax") or configConfig.get(
        "wiringMaxAmpsPerTWC", 32
    )
```

`chargeCurrentRequestMax` is the car's onboard-charger maximum (already a registry field, mapped from TeslaMate, Fleet Telemetry and the APIs; BLE's `get_charge_state` does not map it yet — `chargeCurrentRequestMax` from the ChargeState protobuf could be added at `TeslaBLE.py:681-692`). The one line also fixes `carAmpsRange`, so BLE/Fleet ranges no longer exclude a lift above the pilot.

Verified on a throwaway copy of the tree with the patch (`<scratchpad>/wt-fix`): `tests/unit` 2370 passed, 5 failed — `test_registry_callers.py` and `test_teslaapi_registry.py::test_update_vehicle_data_has_a_single_caller` are `git grep` scans that cannot run in a non-git copy; the other three pin the pilot rule and must change with it: `test_provider_capabilities.py::test_vehicle_max_amps_falls_back_to_wiring` (`:50-54`), `test_teslable_provider.py::test_amps_range_is_one_to_vehicle_max` (`:27-34`), `test_vehicle_endpoint.py::test_state_from_registry_values_without_reads` (`:57-60`, `maxPower == 16 * 240` from `availableCurrent`). `test_amps_reconciler.py:40` already documents the right intuition ("the TWC's own offer, read back from the car") for the amps aspect; the distributor's cap missed it.

Add the scratch test's cases to `tests/unit/test_charging_points.py` (merged TWC+car point, pilot read while idle, must still get the share; the 240/241 V case).

Not a fix on its own: restarting the service clears the reading and the TWC would offer 47 A until the car is next read at a low pilot.

## Also seen

1. Live now: the car is charging at 6 A with 48 A available (since 07:10). With the TWC at 243 V the target flips to 0; `chargeGate` (`TWCSlave.py:233-240`) then issues a `stop` once the offer is 60 s old and the draw has been steady for `startStopDelay` (300 s) — TWCManager could stop the user's own charge. Not observed yet (the draw wobbles 2–6 A, which keeps `cancelStop`), but possible until the fix or a restart.
2. `ChargingPoint.minPower`/`maxPower` compare the TWC member at its measured voltage with the car member at the 240 V default (`VehicleEndpoint.currentVoltage`): a 1 V change on the bus moves a point between a stop and its minimum. Compare in amps, or price every member at the point's voltage.
3. With a ≤ 6 A pilot, `Order.candidates(..., amps=48)` finds no car provider for the lift (`Order.py:89-96`): `Reconciler.plan` says "no provider can deliver" at DEBUG only. A lift that cannot be delivered deserves an INFO line once.
4. Nothing at INFO shows the distributor dropping a plugged, named car's point to 0 with 48 A available, nor a car's charge read values. One INFO line when a Gen2 point's target goes to 0 while the TWC reports a plugged state (with the binding member and its cap) would have shown this in the first minute. The DIAG `pick` line only fires for unnamed plugs.
5. `whyQuiet`'s "nothing offered" is right by the ruling but misleading on a Gen2, whose hardware minimum still pilots 6 A: a woken car would draw 6 A. Consider wording ("offered only the TWC's idle minimum").
6. Ledger follow-up already noted: the post-start telemetry grace counts a feed whose sync is off.
