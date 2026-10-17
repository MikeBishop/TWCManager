### Task 11: Charging points by generic grouping; the distributor allocates per point (closes A18)

Within a point, Phase 2 uses a transitional rule: when the point has a local (TWC) member it carries the whole target and `TWCSlave.send_master_heartbeat` applies `chargeRateControl` exactly as today (mode 2 / mode 3 below 6 A queue the car's rate through the façade and offer the wiring maximum); vehicle members of such a point get no direct amps command from the distributor, which ends the `MergedEVSE`-vs-`_evseTargetAmps` fight (inventory I3). Points without a local member send the target to their vehicle endpoints. Phase 3's layered actuators replace this rule.

**Files:**
- Create: `lib/TWCManager/EVSEInstance/ChargingPoint.py`.
- Delete: `lib/TWCManager/EVSEInstance/MergedEVSE.py`.
- Modify: `lib/TWCManager/TWCMaster.py:504-532` (`getDedupedEVSEs` → `chargingPoints`), `:534-620` (`distributeEVSEPower`), `tests/unit/test_distributor_loop.py:27` (`m.chargingPoints = lambda: evses`), `CHANGELOG.md`.
- Test: `tests/unit/test_charging_points.py`.

**Interfaces:**
- Consumes: `EVSEInstance.vehicleKey/occupied/isLocal/isReadOnly/minPower/maxPower/wantsToCharge/setTargetPower`, `Gen2TWC`, `VehicleEndpoint`.
- Produces (`ChargingPoint.py`):
  - `class ChargingPoint(EVSEInstance):` `__init__(self, master, key: str, endpoints: List[EVSEInstance])`; `key`, `endpoints` (copy); `localEndpoints` / `vehicleEndpoints` (by `isLocal`); `ID` = `"Point-" + key`; `isReadOnly` → all; `isLocal` → any; `isCharging`/`wantsToCharge` → any; `occupied` → `True` if any member is `True`, else `False` if all are `False`, else `None`; `currentAmps`/`currentVoltage`/`currentPower` → averaged over the local members when any, else all (as `MergedEVSE`); `minPower` → max over members; `maxPower` → min over members; `currentVIN` → first non-empty; `vehicleKey` → `key`; `controllers` → union in order; `setTargetPower(watts)`: local members when any (each gets `watts`), else every non-read-only member; `startCharging` → every member; `stopCharging` → `chargeStopMode` 1: non-local non-read-only members, else local members, falling back to all (as `MergedEVSE`; no Phase 2 caller).
  - `groupEndpoints(master, endpoints: List[EVSEInstance]) -> List[ChargingPoint]`: endpoints sharing a `vehicleKey` (upper-cased, `None` never groups) form one point keyed by it; an endpoint with `vehicleKey None` is its own point keyed by its `ID`; order: first appearance.
- Produces (`TWCMaster`): `chargingPoints(self) -> List[ChargingPoint]` = `groupEndpoints(self, self.getAllEVSEs())`; `getDedupedEVSEs` removed. `distributeEVSEPower`: same activation rule (a controller other than `Gen2TWCs` registered), iterates `chargingPoints()`; after the water-fill, the **idle-TWC rule**: every point not in `wants_power`, not read-only, with a member whose `idleMinimum` is `True` (a Gen2 TWC) is offered `point.minPower` when `remaining_watts >= point.minPower` (then `remaining_watts -= point.minPower`), else `0` — in both the early `not wants_power` branch and the final zero-out loop; every other idle point (a Gen3 unit, which reports `vehicle_connected` whatever its headroom, or a vehicle endpoint) still gets `0`. A Gen3 endpoint takes part in `groupEndpoints` like any other: its `vehicleKey` is the correlated VIN or its anonymous key, so two Gen3 units are two points and a correlated car's vehicle endpoint joins its Gen3's point. The distributor never sums Gen3 units: each unit's point gets its own target and `Gen3TWC.setTargetPower` hands it to `Gen3TWCs.setUnitTarget`, where the shared headroom is derived (Task 4, G2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_charging_points.py
from unittest.mock import MagicMock, Mock
from TWCManager.EVSEInstance.ChargingPoint import ChargingPoint, groupEndpoints
from TWCManager.TWCMaster import TWCMaster
VIN = "5YJ3E1EA1KF000001"

def ep(ID, key=None, local=False, minW=1200, maxW=7680, wants=True, ro=False, occupied=None, amps=0.0, idleMin=None):
    e = MagicMock(); e.ID = ID; e.vehicleKey = key; e.isLocal = local; e.minPower = minW; e.maxPower = maxW
    e.idleMinimum = local if idleMin is None else idleMin                  # a Gen2 TWC by default; Gen3 passes idleMin=False
    e.wantsToCharge = wants; e.isReadOnly = ro; e.occupied = occupied; e.currentAmps = amps; e.currentVoltage = [240, 0, 0]
    e.currentVIN = key if key and not key.startswith("anon:") else ""; e.controllers = ["Gen2TWCs" if local else "VehicleEndpoints"]; return e

def test_grouping_is_by_vehicle_key_and_merge_count_may_be_one():
    twc = ep("Gen2TWC-8244", VIN.lower(), local=True); car = ep("Vehicle-" + VIN, VIN); idle = ep("Gen2TWC-8245", None, local=True); anon = ep("Gen2TWC-8246", "anon:8246", local=True)
    pts = groupEndpoints(Mock(), [twc, car, idle, anon])
    assert [p.ID for p in pts] == ["Point-" + VIN, "Point-Gen2TWC-8245", "Point-anon:8246"]
    assert pts[0].endpoints == [twc, car] and pts[0].isLocal and pts[0].currentVIN == VIN and pts[0].vehicleKey == VIN
    assert pts[1].endpoints == [idle] and pts[1].vehicleKey == "Gen2TWC-8245"

def test_point_limits_and_occupancy():
    p = ChargingPoint(Mock(), VIN, [ep("a", VIN, local=True, minW=1440, maxW=7680, occupied=True), ep("b", VIN, minW=1200, maxW=3840, ro=True)])
    assert (p.minPower, p.maxPower, p.isReadOnly, p.occupied) == (1440, 3840, False, True)
    assert ChargingPoint(Mock(), "x", [ep("a"), ep("b")]).occupied is None

def test_target_goes_to_the_local_member_only_when_present():
    twc = ep("t", VIN, local=True); car = ep("c", VIN)
    ChargingPoint(Mock(), VIN, [twc, car]).setTargetPower(2400)
    twc.setTargetPower.assert_called_once_with(2400); car.setTargetPower.assert_not_called()
    ChargingPoint(Mock(), VIN, [car]).setTargetPower(2400); car.setTargetPower.assert_called_once_with(2400)

def distributor(points, amps, controllers=("Gen2TWCs", "VehicleEndpoints")):
    m = TWCMaster.__new__(TWCMaster); m.config = {"config": {"defaultVoltage": 240, "numberOfPhases": 1}}
    ctrl = MagicMock(); ctrl.maxPower = 100000
    m.getModulesByType = lambda t: [{"name": n, "ref": ctrl} for n in controllers]
    m.chargingPoints = lambda: points; m.getMaxAmpsToDivideAmongSlaves = lambda: amps; return m

def test_stopped_car_stays_one_point():                             # Review Focus 5 / A18
    twc = ep("Gen2TWC-8244", VIN, local=True, wants=False); car = ep("Vehicle-" + VIN, VIN, wants=True)
    pts = groupEndpoints(Mock(), [twc, car]); assert len(pts) == 1
    distributor(pts, 40).distributeEVSEPower()
    twc.setTargetPower.assert_called_once_with(7680); car.setTargetPower.assert_not_called()

def test_idle_twc_keeps_its_minimum_when_budget_allows():
    busy = ep("Vehicle-" + VIN, VIN, maxW=4800); idle = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440)
    distributor(groupEndpoints(Mock(), [busy, idle]), 40).distributeEVSEPower()           # 9600 W: 4800 to the car, 1440 to the idle TWC
    assert busy.setTargetPower.call_args.args[0] == 4800 and idle.setTargetPower.call_args.args[0] == 1440
    busy2 = ep("Vehicle-" + VIN, VIN, maxW=4800); idle2 = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440)
    distributor(groupEndpoints(Mock(), [busy2, idle2]), 20).distributeEVSEPower()          # 4800 W: nothing left for the idle TWC
    assert idle2.setTargetPower.call_args.args[0] == 0
    idle3 = ep("Gen2TWC-8245", None, local=True, wants=False, minW=1440); remote = ep("Vehicle-x", "X", wants=False)
    distributor(groupEndpoints(Mock(), [idle3, remote]), 40).distributeEVSEPower()         # nobody wants power: idle TWC still gets its minimum
    assert idle3.setTargetPower.call_args.args[0] == 1440 and remote.setTargetPower.call_args.args[0] == 0

def test_idle_gen3_units_get_zero_and_two_units_are_two_points():                  # G2 (grouping side)
    g1 = ep("Gen3TWC-10.0.0.1", "anon:Gen3TWC-10.0.0.1", local=True, wants=True, maxW=11520, idleMin=False)
    g2 = ep("Gen3TWC-10.0.0.2", None, local=True, wants=False, minW=1440, idleMin=False)
    pts = groupEndpoints(Mock(), [g1, g2]); assert [p.ID for p in pts] == ["Point-anon:Gen3TWC-10.0.0.1", "Point-Gen3TWC-10.0.0.2"]
    distributor(pts, 40).distributeEVSEPower()
    assert g1.setTargetPower.call_args.args[0] == 9600 and g2.setTargetPower.call_args.args[0] == 0

def test_correlated_car_joins_its_gen3_point():
    g = ep("Gen3TWC-10.0.0.1", VIN, local=True, idleMin=False); car = ep("Vehicle-" + VIN, VIN)
    (pt,) = groupEndpoints(Mock(), [g, car]); pt.setTargetPower(2400)
    g.setTargetPower.assert_called_once_with(2400); car.setTargetPower.assert_not_called()

def test_pure_gen2_leaves_distributor_off():                         # Review Focus 2
    idle = ep("Gen2TWC-8245", None, local=True, wants=False)
    distributor([ChargingPoint(Mock(), "Gen2TWC-8245", [idle])], 40, controllers=("Gen2TWCs",)).distributeEVSEPower()
    idle.setTargetPower.assert_not_called()

def test_no_type_knowledge_left():
    import subprocess
    from pathlib import Path
    out = subprocess.run(["git", "grep", "-l", "MergedEVSE\\|getDedupedEVSEs\\|TeslaAPIEVSE\\|TeslaAPIController", "--", "lib/TWCManager"],
                         capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2])).stdout.split()
    assert out == []
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError` for `ChargingPoint`).

- [ ] **Step 3: Implement** per Interfaces; delete `MergedEVSE.py`; update `test_distributor_loop.py`.

- [ ] **Step 4: Run the full suite** → PASS (baseline 1153 plus this phase's tests).

- [ ] **Step 5: Changelog and commit**

CHANGELOG `* Architecture`: `    * (@MikeBishop) - Charging endpoints (a TWC, or a car whose amps BLE, Fleet or HomeAssistant can set) are grouped into charging points by the car they serve; the distributor allocates per point, an idle TWC keeps its minimum, and a car's amps are queued to the vehicle worker instead of being sent to the Fleet API from the RS-485 loop`. `* Bugfixes`: `    * (@MikeBishop) - A car that stops charging on its TWC no longer gets a second power share and Fleet charge-rate commands of its own`.
```bash
black lib/TWCManager/EVSEInstance/ lib/TWCManager/TWCMaster.py
git add -A lib/TWCManager/EVSEInstance lib/TWCManager/TWCMaster.py tests/unit CHANGELOG.md
git commit -m "Group charging endpoints into charging points and allocate per point"
```

- [ ] **Step 6: Live check on the user's box (deploy branch, pre-approved; coordinate first — the ledger notes another session may hold the box)**

Deploy `vehicle-model/phase2` to `twcmanager`, restart, and confirm in the log: `Providers: Gen2TWC, TeslaBLE, ...` at boot in rank order; no `Main loop stalled` beyond the boot-time one seen on 8e07669; with the car on the TWC, exactly one `Point-<VIN>` in a `distributeEVSEPower` DEBUG line (add the line if absent: one DEBUG per round listing point IDs and offers) and **zero** Fleet `set_charging_amps` requests while the TWC serves the car; a BLE charge-limit apply still lands (façade walk BLE first); `/api/sendTeslaAPICommand` wake from the debug page works and is logged under the provider that served it. Record findings in the PR description, then roll the box back per the ledger's rollback note.

---

## Inventory rows this phase closes

- **A1** (`Capability`/provider interface, fixed order replacing `calculateModulePriority`/`getModuleByPriority` as the policy; those two methods stay in `TWCMaster` unused until Phase 3 deletes `VehiclePriority`), **A2** (`commandPolicy` as suppressions on the order), **A8** (`VehicleEndpoint` asks the order; `isReadOnly` and `provider` derived from candidates; `isLocal` stays `False`, which the charging-point rule relies on), **A9** (cost per operation; read sources ordered free before billed; Fleet reads only when Owner cannot), **A10** (HomeAssistant in the order, last; default-on when loaded), **A17** (read-only under `ble_only` → no power share), **A18** (grouping by vehicle key; a stopped car stays one point), **A24** (Owner and Fleet are separate providers; the order, not `slotFor`, decides which channel a command uses; `slotFor` remains only inside `TeslaAPI`'s own methods), **A26** (debug API via `ProviderOrder.debugCommand`).
- Declared for Phase 3: Gen2 disruptive stop (`STOP_CHARGING`, tier 3, `chargeStopMode` 2/3), Fleet rate limit, `Provider.summary()` for Phase 6 panels.

## Carry-forwards to later phases

- Phase 3 (amps reconciler, layered actuators): `ChargingPoint.setTargetPower`'s TWC-carries-all rule and `TWCSlave`'s `chargeRateControl` branch are replaced; the `#660` raise-to-max over Fleet for a Fleet-only car on a TWC is dropped by the default paid-amps rule in this phase (BLE still raises for free) — decide there whether a one-time raise is worth $0.001/session.
- Phase 3: `Gen2TWCProvider.stopCharging` gets its caller; `TWCMaster.stopCarsCharging`/`startCarsCharging` go. The Gen3 zero-headroom stop is declared at the normal local tier but is unverified on hardware: treat it as a normal stop and watch the car's behaviour (G4); on a multi-unit bus the provider declares `NO_INDIVIDUAL_STOP`, so the reconciler picks another actuator (BLE or Fleet on that car) for a per-unit stop.
- Separate design (inventory A27): Gen3 correlation beyond "exactly one freshly plugged candidate" is VIN-less fingerprinting.
- Phase 5: `Gen2TWC.vehicleKey`'s `lastVIN`-while-plugged-state rule and `occupied` become presence attribution; the registry plug session is still `isCharging`-based (ledger I5).
- Phase 6: `Provider.summary(vehicle)` feeds the per-car provider panels; Forget drops the `CarApiVehicle` (ledger M8).

## Decisions made in this plan

1. Package layout: `lib/TWCManager/Vehicle/Providers/` for the provider layer; endpoints keep the `EVSEInstance` base class and file names; `ChargingPoint`, `VehicleEndpoint`, `VehicleEndpoints` replace `MergedEVSE`, `TeslaAPIEVSE`, `TeslaAPIController` (files deleted) — minimal churn, spec's "endpoint + charging point" vocabulary.
2. Cost is `(tier, price)`; the order sorts by `(tier, fixed rank)`; locality is folded into tier 0 — "by cost then locality" with one key.
3. Fixed ranks: Gen2TWC 0, Gen3TWC 1, TeslaBLE 2, telemetry 3, OwnerAPI 4, FleetAPI 5, HomeAssistant 6 — the spec's list order with Gen3 beside Gen2 (G1: its own rank rather than a tie, so the order is total).
4. HomeAssistant is billed-tier with unknown price and ranked after Fleet for reads and commands — spec lists HA last; Phase 1 ruled HA reads last; HA's Tesla integration is commonly the user's own Fleet app.
5. One `Gen2TWCProvider` for every TWC (readiness per vehicle via attribution) rather than one provider per TWC — slaves appear and vanish at runtime; ranges are still per device.
6. `api_only` keeps meaning "TeslaBLE suppressed for every operation" with a one-time INFO notice, instead of mapping to the default — users chose it because Bluetooth does not work for them; the default would add a 5–15 s BLE timeout before every command (the "reason that surfaces" the spec allowed for).
7. `ble_only` suppresses every remote provider for commands (Fleet and HomeAssistant), not only TeslaAPI — HA is now reachable.
8. The default "Fleet never sets amps" rule considers the requested amps: a local path counts only when its range covers the target — keeps `chargeRateControl` 3 working below 6 A over Fleet and makes mode 2 (TWC not an amps path) work; the `#660` raise over Fleet is dropped when the TWC covers the target (spec default; BLE still raises).
9. Fine-grained suppressions live in `settings["providerSuppressions"]` / config `vehicle.providerSuppressions` with no UI this phase; `commandPolicy` stays the UI control, relabelled — Phase 6 owns provider UI.
10. Ledger I5: TWC endpoint correlation is `currentVIN`, else the anonymous plug session, else `lastVIN` while the TWC reports a plugged state; `occupied` is tri-state (Gen2 00 is unknown, not empty); the registry plug session stays `isCharging`-based until Phase 5 — charging points no longer inherit "session == charging".
11. Inside a point the TWC member carries the whole target and `TWCSlave` applies `chargeRateControl` as today; vehicle members of a TWC point get no distributor amps command — removes the I3 fight without pre-empting Phase 3's layered actuators.
12. `VehicleEndpoints` is registered only when TeslaAPI is loaded and lists TeslaAPI-attached at-home cars (today's condition and rule) — BLE-only and HA-only installs stay on the per-slave path until Phase 4, so no new code path on their boxes.
13. `VehicleEndpoint.setTargetPower` queues `setAmps` to the vehicle worker (on change or every 600 s) instead of calling Fleet synchronously on the serial loop — threading constraint; TeslaAPI's own repeat-skip still gates paid resends.
14. The Fleet read source is ready only when the Owner slot cannot read — reproduces `slotFor("read")`, so splitting the sources adds no paid read.
15. Claims split into `OwnerAPI` (listed, no commands) and `FleetAPI` (commands when the slot can); the attachment name stays `"TeslaAPI"` — tier semantics unchanged, Vehicles tab shows which slot does what.
16. Fleet declares `RateLimit(50, 60)` on commands (Tesla's published per-vehicle limit), unenforced until Phase 3 lanes; other providers declare none.
17. Gen2 disruptive stops are one `STOP_CHARGING` capability at tier 3, ready only when `chargeStopMode` is 2 or 3 (off by default), with `stopCharging(vin)` implemented but uncalled this phase; `TWCMaster.stopCarsCharging` is unchanged.
18. Idle-TWC minimum is a distributor rule: a local point not wanting power gets its minimum when the remaining budget allows — spec "must be kept"; today's distributor path offered 0.
19. Per-device range override config key `controller.Gen2TWCs.ranges.<TWCID>.{minAmps,maxAmps}` — mirrors the existing `controller.Gen3TWCs` key shape.
20. `calculateModulePriority`/`getModuleByPriority` stay in `TWCMaster` unused by the façade — removed with `VehiclePriority` in Phase 3.
21. `TeslaAPI.apiDebugInterface` is deleted; `/api/sendTeslaAPICommand` calls `ProviderOrder.debugCommand`, which honours suppressions and readiness and works on BLE-only installs.
22. G1: Gen3 TWC is a provider (Task 4, right after Gen2): local, free, tier 0, its own rank 1 (not a tie with Gen2, so the order stays total); capabilities `setAmps` with range 6..fuse per device, start/stop, passive plug/amps reads from vitals; registered only inside the existing `controller.Gen3TWCs.enabled` block, so a disabled Gen3 changes nothing.
23. G2 (revised, user direction): Gen3 units are separate endpoints with their own targets for the distributor and charging points; only `Gen3TWCs`, which owns the one fake-Neurio value, aggregates: it water-fills one shared headroom `h` so the net draw matches the sum of per-unit targets (unknown demand = unlimited; a unit measured below `h` is car-limited and its vitals amps are its demand; all unconstrained → `h = sum/n`; one unit → `h = target`, today's behaviour), each unit in its own fuse terms (bisection on the house amps `H` with `h_i = F_i − H`; no smallest-fuse approximation), clamped to `[6 A, fuse]`, recomputed on target changes and once per vitals refresh, damped at 1 A. A zero-target unit beside a charging sibling cannot be stopped through the shared value: it is excluded from the sum, may draw up to `h`, and the provider declares `NO_INDIVIDUAL_STOP` while more than one unit is occupied; all targets 0 is still a full-fuse house load. Tested: two unconstrained, one car-limited, one zero-target, single unit.
24. G3: `vehicle_connected` rising starts `anon:Gen3TWC-<ip>` through the Phase 1 plug-session API and falling ends it; `occupied` is `vehicle_connected`; the car is correlated only when exactly one non-anonymous registry car reports `pluggedIn` True within 120 s of the connect, is not already attributed to another point, and is not known away (`atHome` False) — then `observeTwcVin` merges the anonymous vehicle and the car's vehicle endpoint joins the Gen3's point; otherwise it stays anonymous (VIN-less fingerprinting is its own design) and the `VehicleEndpoints` blind rule lists no vehicle endpoints, so no Fleet amps go to any candidate.
25. G4: the Gen3 zero-headroom stop is `STOP_CHARGING` at the normal local tier, unlike Gen2's tier-3 disruptive stops; unverified on hardware, carried to Phase 3.
26. G5: no new polling loop — `Gen3TWC.refreshVitals()` keeps today's 5 s / 10 s TTLs and runs on the background thread via a `gen3Vitals` task queued when `allEVSEs` finds a stale cache; every property reads the cache; no HTTP on the serial thread or under a registry/settings lock. Cost: the first distributor round after boot sees no Gen3 units (one round of delay).
27. G6: Gen3 is verified by unit tests only (no hardware on the box).
28. Gen3 `isLocal` becomes `True` (on-premise, tier 0): the old `False` only steered `MergedEVSE`, which is gone.
29. Idle Gen3 units get 0 headroom (today's distributor behaviour): plug detection comes from vitals, not from an offered minimum, so the idle-TWC-minimum rule is keyed on a new `EVSEInstance.idleMinimum` flag that only `Gen2TWC` sets.
30. G7: Gen3 car identity in order: a cloud VIN from `live_status.wall_connectors` matched by DIN, then the single-candidate rule (G3), then anonymous; a cloud VIN goes through the same `observeTwcVin` path as a Gen2 TWC VIN (unknown VIN pending until the next poll confirms it; known VIN at once) — it is evidence of which car is plugged in, nothing more. Facts about `live_status`/DIN are from the tesla-fleet-api types and unverified on hardware.
31. G8: a free read capability `wallConnectorVins` on the Owner and Fleet providers (`Declaration(CLOUD_FREE, RateLimit(2, 60))`), ordered after local sources; ready only when the slot has a token with energy scope, the products list holds an energy site, and no 401/403 has been seen since the token last changed (one INFO on refusal); Owner tried first, Fleet only when Owner cannot (free either way); never wakes a car, never touches vehicle endpoints.
32. G9: no new free-running loop — queried on a Gen3 `vehicle_connected` rising edge and then every 60 s while a Gen3 is occupied without a VIN, stopping once the session has one; products discovery at first use then at most hourly; all from `refreshVitals()` on the background thread, no HTTP under locks or on the serial thread; the provider's `RateLimit` is honoured by the reader.
33. G10: DIN match primary `<part_number>--<serial_number>` from local `/api/1/version` (fetched once, cached; format unconfirmed), config override `controller.Gen3TWCs.devices[].din`; fallback only when the local DIN is unknown: exactly one local Gen3 and exactly one cloud wall connector; a known DIN that matches nothing is skipped (it is evidence of a different connector); otherwise one INFO and fall to G3.
34. G11: Gen2 TWCs never use the energy-site path; a Gen2-only install with wall connectors on the account has no local Gen3 units, so nothing is queried.
36. Pre-flight rulings 1–24 (`.superpowers/sdd/2026-10-14-vehicle-model-phase2-providers/preflight.md`) are folded into the tasks above; the ones that change behaviour: a candidate whose known range does not cover the target is dropped (spec's layered rule); Gen2 `ampsRange` floors at 6 A under `chargeRateControl` 3 (the threshold `TWCSlave` really uses); `dispatch` never reaches TWC providers (no TWC target written off the serial thread); both TeslaAPI claims are made at bind with live callables; `Provider.available()` gates broadcasts (today's read-only skip); the blind rule keys on `vehicleKey`; HomeAssistant stays last and is named as such in the constraint and CHANGELOG; `api_only` keeps suppressing TeslaBLE only.
35. Task split: G7–G11 are their own Task 7 ("Wall Connector VIN from the energy site"), placed after the Owner/Fleet providers it extends rather than directly after the Gen3 task, because Task 4 already carries the plug sessions, correlation and shared headroom and the capability lives on `TeslaAPIProviders.py` (created in Task 6).

## Questions for the user

None — every open point above is decided with its reason; say so if any decision should go the other way before Task 1 starts.
