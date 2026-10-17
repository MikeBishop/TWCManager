# Task 11 report: Charging points by generic grouping; distributor allocates per point

**Status:** DONE (Steps 1-5). **Step 6 (live check on the box) NOT run**, as instructed; the coordinator runs it with the user.

**Commit:** `9358db4` "Group charging endpoints into charging points and allocate per point" on `vehicle-model/phase2` (worktree `scratchpad/wt-vm2`), parent `4aa71a1`.

**Tests:** full suite `tests --ignore=tests/API --ignore=tests/integration`: **1286 passed, 1 xfailed** (baseline 1267 at 4aa71a1; +17 in `test_charging_points.py`, +2 in `test_vehicle_endpoint.py`). The xfail is pre-existing (`tests/scenarios/bugs/test_regression_template.py`, present at 4aa71a1).

## What changed

- `lib/TWCManager/EVSEInstance/ChargingPoint.py` (new): `ChargingPoint(EVSEInstance)` and `groupEndpoints(master, endpoints)` per the brief's Interfaces. `setTargetPower` sends to local members when any exist; otherwise to every non-read-only member. `stopCharging` follows MergedEVSE's chargeStopMode routing (it has no Phase 2 caller).
- `lib/TWCManager/EVSEInstance/MergedEVSE.py`: deleted.
- `lib/TWCManager/TWCMaster.py`: `getDedupedEVSEs` is replaced by `chargingPoints()` = `groupEndpoints(self, self.getAllEVSEs())`. `distributeEVSEPower` keeps the same activation rule (a controller other than Gen2TWCs) and the same water-fill, now over points. `available_watts` is computed before the wants-power check, and one loop over the points that don't want power applies the **idle-TWC rule**: a point with a member whose `idleMinimum is True` (Gen2 only) gets `point.minPower` while `remaining_watts` allows, otherwise 0. All other idle points get 0. That one loop covers both the old "nobody wants power" branch and the zero-out loop. It also adds one DEBUG line per round: `distributeEVSEPower: <available> W over Point-<key>=<w> W, ...`. Step 6 needs this line.
- `lib/TWCManager/EVSEController/VehicleEndpoints.py`: an occupied Gen3 whose `vehicleKey` is None now counts as blind, the same as an `anon:` key (`unit.occupied is True and _unknownKey(unit.vehicleKey)`).
- `lib/TWCManager/EVSEInstance/EVSEInstance.py`: docstring (MergedEVSE → ChargingPoint).
- `tests/unit/test_distributor_loop.py`: `m.chargingPoints = lambda: evses`.
- `CHANGELOG.md`: the two entries from the brief, verbatim (Architecture, Bugfixes).
- `docs/Gen3_Status.md`: this file is outside the brief's list. I changed it because its MergedEVSE limitation note was no longer true: a correlated car now joins its Gen3's point.
- black was run on the lib files I touched.

## Tests added

`tests/unit/test_charging_points.py`: the brief's 10 tests verbatim. I added one assertion: an all-False `occupied` gives False. Then 8 real-object tests on a real `TWCMaster("AB", ...)`, a real `Gen2TWC` (`newSlave`), the real `VehicleEndpoints` controller with real `VehicleEndpoint`s, a real `ProviderOrder` (the real Gen2TWC provider plus the `fleet()` test provider), and, for test 7, a real `Gen3TWCs`/`Gen3TWC`. Only `queue_vehicle_command`, `queue_background_task`, the TeslaAPI/Policy module lookups and the budget are stubbed. Each runs through `chargingPoints()` and `distributeEVSEPower()`:

1. `test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum`: lastVIN + state 03 + endpoint form ONE point, `minPower == s.minPower == 1440`, no setAmps, `_evseTargetAmps == 32`.
2. `test_lower_case_vin_on_the_twc_groups_with_the_endpoint`: covers a lower-case lastVIN and a lower-case currentVIN.
3. `test_mode_1_budget_below_the_twc_floor_offers_zero_and_no_fleet_send`: 5 A budget, so the offer is 0 and nothing is sent.
4. `test_mode_2_named_twc_leaves_the_rate_to_the_heartbeat`: the distributor queues no setAmps. Then `receive_slave_heartbeat` runs, and the only queued command is `setChargeRate` (20 A).
5. `test_twc_point_sets_the_twc_target_and_never_the_endpoint`: the endpoint's `setTargetPower` is wrapped in a spy and is never called. This covers the water-fill (20 A), the nobody-wants-power branch (idle minimum 6 A), zero-out with no budget left (0), and zero-out with room left (6 A).
6. `test_car_on_no_twc_is_its_own_point_and_queues_amps`: a car on no TWC is its own point and queues `setAmps` 20 A. The car on the named TWC queues nothing.
7. `test_correlated_gen3_car_joins_the_gen3_point_and_queues_no_amps`: a real Gen3 correlates the single candidate. The point holds the unit and the endpoint, `u.lastTarget == 4800`, and no setAmps is queued.
8. `test_gen2_at_00_with_a_sleeping_car_is_two_points_as_before_task_10`: pinned behaviour, see Concerns.

The brief's grep test (`test_no_type_knowledge_left`) passes.

`tests/unit/test_vehicle_endpoint.py`:
- `test_occupied_gen3_without_a_vehicle_key_is_blind`: occupied True with key None blinds. Occupied None/False with key None does not.
- `test_a_car_only_ble_can_serve_is_writable_over_ble`: `master({}, ble())` and `ble_only` with ble+fleet both give `not isReadOnly` and `provider == "TeslaBLE"`.

## Fail-before evidence

New test file before `ChargingPoint.py` existed:
```
tests/unit/test_charging_points.py:6: in <module>
    from TWCManager.EVSEInstance.ChargingPoint import ChargingPoint, groupEndpoints
E   ModuleNotFoundError: No module named 'TWCManager.EVSEInstance.ChargingPoint'
```
Gen3 blind fold-in before the fix (1 failed, 9 passed):
```
E   assert [<TWCManager....7d40a66471a0>] == []
E     Left contains one more item: <TWCManager.EVSEInstance.VehicleEndpoint.VehicleEndpoint object at 0x7d40a66471a0>
```
The BLE positive test already passed before any change. It was asked for as a positive test, so it pins existing behaviour rather than showing a TDD red.

The real-object tests were also run against **4aa71a1's own `getDedupedEVSEs`/`distributeEVSEPower`/`MergedEVSE`**: a scratch pytest plugin loaded them from `git show 4aa71a1:...` onto today's TWCMaster, with `chargingPoints` aliased to the old `getDedupedEVSEs`. Result: 8 failed. The mode-1 `amps: 5` and mode-2 `amps: 20` lines are the interim paid path this task closes:
```
    E   ValueError: too many values to unpack (expected 1)
    E   AssertionError: assert ['Vehicle-5YJ...Gen2TWC-8244'] == ['Point-5YJ3E1EA1KF000001']
    E     
    E     At index 0 diff: 'Vehicle-5YJ3E1EA1KF000001' != 'Point-5YJ3E1EA1KF000001'
    E     Left contains one more item: 'Gen2TWC-8244'
    E     Use -v to get more diff
    E   AssertionError: assert (0.0 == 0 and [{'cmd': 'set...', 'amps': 5}] == []
    E    +  where 0.0 = <TWCManager.EVSEInstance.Gen2TWC.Gen2TWC object at 0x72816eec31a0>._evseTargetAmps
    E     
    E     Left contains one more item: {'cmd': 'setAmps', 'vin': '5YJ3E1EA1KF000001', 'amps': 5}
    E     Use -v to get more diff)
    E   AssertionError: assert ([{'cmd': 'set..., 'amps': 20}] == []
    E     
    E     Left contains one more item: {'cmd': 'setAmps', 'vin': '5YJ3E1EA1KF000001', 'amps': 20}
    E     Use -v to get more diff)
    E   assert 0.0 == 20
    E    +  where 0.0 = <TWCManager.EVSEInstance.Gen2TWC.Gen2TWC object at 0x72816ee9fda0>._evseTargetAmps
    E   AssertionError: assert ['Merged-Gen2...1EA1KF000001'] == ['Point-5YJ3E...1EA1KF000002']
    E     
    E     At index 0 diff: 'Merged-Gen2TWC-8244-Vehicle-5YJ3E1EA1KF000002' != 'Point-5YJ3E1EA1KF000001'
    E     Use -v to get more diff
    E   ValueError: too many values to unpack (expected 1)
    E   AssertionError: assert (None is None and ['Vehicle-5YJ...Gen2TWC-8244'] == ['Point-Gen2T...1EA1KF000001']
    E    +  where None = <TWCManager.EVSEInstance.Gen2TWC.Gen2TWC object at 0x72816eef8650>.vehicleKey
    E     
    E     At index 0 diff: 'Vehicle-5YJ3E1EA1KF000001' != 'Point-Gen2TWC-8244'
    E     Use -v to get more diff)
    FAILED tests/unit/test_charging_points.py::test_stopped_car_and_its_endpoint_form_one_point_with_the_twc_minimum
    FAILED tests/unit/test_charging_points.py::test_lower_case_vin_on_the_twc_groups_with_the_endpoint
    FAILED tests/unit/test_charging_points.py::test_mode_1_budget_below_the_twc_floor_offers_zero_and_no_fleet_send
    FAILED tests/unit/test_charging_points.py::test_mode_2_named_twc_leaves_the_rate_to_the_heartbeat
    FAILED tests/unit/test_charging_points.py::test_twc_point_sets_the_twc_target_and_never_the_endpoint
    FAILED tests/unit/test_charging_points.py::test_car_on_no_twc_is_its_own_point_and_queues_amps
    FAILED tests/unit/test_charging_points.py::test_correlated_gen3_car_joins_the_gen3_point_and_queues_no_amps
    FAILED tests/unit/test_charging_points.py::test_gen2_at_00_with_a_sleeping_car_is_two_points_as_before_task_10
    ======================= 8 failed, 9 deselected in 0.23s ========================
```
(With only `ChargingPoint.py` present, the brief's mock-based tests failed 13 of 17 against the old distributor; the 4 that passed only exercise `ChargingPoint` and `groupEndpoints` directly.)

## Constraints check

- Pure Gen2: the activation rule is unchanged (`test_pure_gen2_leaves_distributor_off`), and the per-slave heartbeat path is untouched. TWCSlave.py was not modified.
- Nothing new on the serial thread except the in-memory grouping and one DEBUG log line. No I/O, no locks taken, no new paid call path: the only amps path left is the existing queued `setAmps`, now reached only from points with no local member.

## Concerns

1. **Brief-internal inconsistencies, resolved by following the brief's own tests:**
   - `groupEndpoints` upper-cases VIN keys but leaves `anon:` keys as issued. The prose says "upper-cased", but the brief's tests expect `Point-anon:8246`.
   - `ChargingPoint.currentVIN` returns the first non-empty VIN **upper-cased**. The prose says "first non-empty", but the brief's test expects `VIN` from a lower-case TWC VIN.
2. **The brief places the `chargeRateControl` branch in `TWCSlave.send_master_heartbeat`; it is in `receive_slave_heartbeat` (TWCSlave.py ~603-1080).** Test 4 drives that method. This matters for the Step 6 reasoning.
3. Test 4 sets `s._TWCSlave__lastAPIAmpsRequest = 0` to get past TWCSlave's class-level hold-off. That hold-off blocks any API rate send until 30 s after the module is imported. This only lets the test reach today's behaviour; the hold-off itself is unchanged.
4. **Gen2 at state 00 with a sleeping car (key None):** I pinned this with a test rather than changing it. The TWC and the car are two points, the car still queues `setAmps` (over Fleet in mode 1 when no BLE), and the TWC gets its idle minimum. This is the pre-Task-10 behaviour (TeslaAPIEVSE was listed the same way). Attributing a car to a TWC at 00 is Phase 5 presence attribution, per the brief's carry-forwards. It is a residual paid path, not a regression.
5. Grouping a car with its Gen3 now means the car's endpoint gets no amps command while its point has a local member. That matches decision 11, and the Gen3's shared headroom carries the target.
6. The DEBUG line runs once per distributor round. It is cheap but chatty at DEBUG level.
7. The full-suite baseline was 1267, not the brief's 1153.
8. **Step 6 was not run** (another session holds the box). For that check: the DEBUG line to grep for is `distributeEVSEPower: ... Point-<VIN>=... W`.

## Fix round 1 (review I1)

**Commit:** `b72c79c` "Keep each TWC in its own charging point", on top of `9358db4`.

**Tests:** full suite **1289 passed, 1 xfailed** (+3: the review I1 tests).

### Fix

In `groupEndpoints` (`lib/TWCManager/EVSEInstance/ChargingPoint.py`), a local endpoint never joins a group that already has a local member. It becomes its own point, keyed by its ID. A point therefore holds at most one TWC, and a second TWC that claims the same car through a stale `lastVIN` is budgeted on its own.

The car's endpoint joins the first group with its key: the first TWC to claim it in endpoint order. That point keeps a local member, so the endpoint still gets no amps command.

Which TWC keeps the car follows endpoint order, not "the one whose `currentVIN` matches". This is wiring-safe either way. Preferring the `currentVIN` holder is a Phase 5 attribution refinement, along with the review's note that another TWC reporting the VIN as its `currentVIN` is evidence the car was unplugged.

### Not done: clearing `lastVIN` at state 00

`Gen2TWC.vehicleKey` already ignores `lastVIN` at state 00; it uses it only while the TWC reports a plugged state. Clearing it would mean writing to it from inside a property getter, which can run on any thread that reads the key. That is not a minimal change. It also would not cover a TWC that goes straight from one plug session to the next without the 00 being observed. The grouping guard is the fix.

### Tests (`tests/unit/test_charging_points.py`)

- `test_a_point_holds_at_most_one_local_endpoint`: mock-level grouping check. Two TWCs claim one VIN; the second, with a lower-case VIN, becomes `Point-Gen2TWC-8245`.
- `test_two_twcs_claiming_one_car_stay_separate_points_within_budget`: real objects. Two `newSlave`s claim VIN at a 40 A budget, run over 3 rounds, in two variants:
  - a stale `lastVIN` at 0x01, beside a TWC whose `currentVIN` is the car;
  - both TWCs with the same stale `lastVIN`.

  Checks: two points; exactly one point holds the vehicle endpoint; `sum(_evseTargetAmps) <= 40`; no `setAmps`.
- `test_twc_offers_never_exceed_the_budget_or_wiring_across_point_shapes`: real objects, 4 shapes × budgets 5/6/12/20/40/64/80/100 A, 2 rounds each. The shapes are:
  - two cars on two TWCs plus one stale `lastVIN`;
  - stale + serving + idle;
  - three TWCs with the same stale `lastVIN`;
  - two serving + idle.

  Checks: the sum of TWC offers is ≤ min(budget, `wiringMaxAmpsAllTWCs`); no car is in more than one point; no `setAmps` for any car a TWC claims. A car on no TWC may still queue its own amps.
- The bus holds at most 3 slaves (`newSlave` drops the oldest), so no shape has more than three TWCs.

### Fail-before on 9358db4

```
FAILED test_two_twcs_claiming_one_car_stay_separate_points_within_budget
E   AssertionError: assert ['Point-5YJ3E1EA1KF000001'] == ['Point-5YJ3E...Gen2TWC-8245']
FAILED test_twc_offers_never_exceed_the_budget_or_wiring_across_point_shapes
E   AssertionError: ((serving VIN, stopped vin2, stale VIN), 12, [6.0, 6.0, 6.0])
E   assert 18.0 <= (12 + 1e-09)
```

### Reviewer probe

`probe-t11/test_probe_t11.py`: 10 passed. The I1 reproducer, `test_stale_lastvin_two_twcs_one_point`, now fails its over-allocation assertion: it asserts `> 40` and gets `32.0 + 6.0`. That inversion is expected.

### Minor items folded in

- m3: the DEBUG line is now built only when `logger.isEnabledFor(logging.DEBUG)`.
- m4: the `distributeEVSEPower` docstring now names `receive_slave_heartbeat`, and the over-long docstring line in `VehicleEndpoints._blindTWCs` is rewrapped.

### Not changed

- m1 (Task 10's lost coverage) is carried forward.
- m2 (a 0 W offer can still go out as `minAmpsTWCSupports` on the wire) is pre-existing; it belongs in the Step 6 notes.
- m5 and m6 would change the brief's CHANGELOG text, which was to be used word for word. Left for the coordinator or the user.
