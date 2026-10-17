# Task 6 report: Owner API and Fleet API as separate providers

Status: DONE_WITH_CONCERNS
Commit: 3f89dea (branch vehicle-model/phase2, worktree wt-vm2; parent 607e6d1)

## What changed
- `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py` (new): `OwnerAPIProvider` (rank 4, CLOUD_FREE reads READ_LIST/ONLINE/CHARGE/LOCATION, ready = ownerSlot.usable("read") and attachment) and `FleetAPIProvider` (rank 5; READ_LIST/ONLINE free, READ_CHARGE/LOCATION FLEET_DATA, four commands FLEET_COMMAND with RateLimit(50, 60), WAKE FLEET_WAKE). Fleet reads are ready only when the Fleet slot can read and the Owner slot cannot. Commands and wake are ready when fleetSlot.usable("command"). `available()` is the broadcast gate. `ampsRange` is (1, vehicleMaxAmps). `setAmps` and `wake` resolve the car by VIN and return False when the VIN is unknown. Nothing here does I/O or logs.
- `Registry/Sources.py`: `TeslaAPIReadSource(carapi, kind="owner")` gains `provider` ("OwnerAPI"/"FleetAPI") and `slot()`. `canRead` needs the attachment and `slot().usable("read")`, and for fleet also `not ownerSlot.usable("read")`. `fetch` passes `slot=` to `is_awake` and `update_vehicle_data`. `name` stays "TeslaAPI" and `order = 1` stays a class attribute.
- `TeslaAPI.py`: `ownerReadSource` and `fleetReadSource` are registered, owner first. Registration order is what keeps owner ahead of fleet while `registerProviders` is not wired. Also adds `providers()`. `_bind` claims "OwnerAPI" (False, "listed") and "FleetAPI" (`lambda: carapi.fleetSlot.usable("command")`, "listed"), and no longer claims "TeslaAPI". That lambda behaves the same as the old `not readOnly`, because the Owner slot never grants command. `is_awake(slot=None)`, `update_vehicle_data(slot=None)` and `get_car_api(..., slot=None)` are added. An explicit slot that is no longer `usable("read")` returns (False, None) with no request.
- Tests: new `tests/unit/test_teslaapi_providers.py` (10 tests: the brief's 5, plus a paused-slot guard, a paid-endpoint count parametrized over 3 Owner outcomes, and Fleet-only reads). `test_carapivehicle_registry.py:161,172` now check "FleetAPI". In `test_reads_no_wake.py` and `test_telemetry_registry.py`, the fixtures now hold an Owner token, because `canRead` now needs a usable slot (real behavior is unchanged: with no slot, `get_car_api` already returned False). Their stand-in lambdas now accept `slot=None`.

## Cost
- No new paid call path, and no paid call happens at a new time in the normal case. A Fleet `vehicle_data` happens only when the Owner slot cannot read, as `slotFor("read")` chose before. Commands and wake still go through `setChargeRate`/`wakeVehicle` (`slotFor("command")`), unchanged.
- `test_owner_reads_cost_nothing_with_a_fleet_token_held[lands|asleep|unusable]` holds both tokens, mocks the Owner `vehicles/{vin}` and `vehicle_data`, catches every `fleet-api.prd.*` request with a regex, runs `car.update_charge()`, and asserts the Fleet matcher's call_count == 0.
- Mutation check: I removed the fleet `not ownerSlot.usable("read")` gate. `[unusable]` (car online, Owner vehicle_data unusable, so the cascade moves to the Fleet source) then fails with `assert 1 == 0`, and so does `test_fleet_reads_only_when_owner_cannot`. `[asleep]` alone cannot catch it: the car's 2-minute awake cache stops the Fleet source short of any request.
- `test_fleet_reads_when_owner_holds_no_token` confirms that Fleet-only installs still read (1 free online check + 1 vehicle_data).

## TDD fail-before (607e6d1 + new test file)
```
E   AttributeError: 'TeslaAPI' object has no attribute 'providers'
E   AssertionError: assert ({'TeslaAPI'} == {'FleetAPI', 'OwnerAPI'}
E   AttributeError: 'TeslaAPI' object has no attribute 'ownerReadSource'
E   TypeError: CarApiVehicle.get_car_api() got an unexpected keyword argument 'slot'
6 failed, 3 passed
```
The 3 that passed before the change are the cost and Fleet-only regression guards. They pin today's behavior, and the mutation check above shows they catch a lost gate.

## Results
- Brief Step 4 set plus test_telemetry_registry: 107 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1226 passed, 1 xfailed. That is 1216 + 10 new.
- black (26.10.1) run only on the three touched lib files.

## Concerns
1. Error-path timing: if the Owner slot is cleared (401) or paused (403/410/412) mid-cascade, the Fleet source now reads in the same cascade. Before, that read waited for the next poll. These are the same paid calls `slotFor("read")` would make, just one poll earlier, and only on that error path. The brief's `canRead` spec produces this. I implemented it as written.
2. The brief's Step 5 runs `black lib/TWCManager/Vehicle/`. I followed the dispatch rule instead and ran black only on the touched files.
3. Test fixture changes outside the brief's list (`test_reads_no_wake.py`, `test_telemetry_registry.py`): each now stores an Owner token, and the stand-ins take `slot=None`. Neither change alters what the tests assert.
4. Fleet READ_LIST/READ_ONLINE are free, but Fleet `ready()` still refuses them while the Owner slot can read, as the brief's "for reads" says. Harmless, since Owner serves them.
5. `registerProviders` is still not called from TWCManager.py, so these providers are not yet in the live ProviderOrder. Reads are ordered by registration (owner first) until then. Once they are registered, ordering is by tier and rank: owner (free, 4) before fleet (min read tier free, 5).

## Fix round 1

Commit: 70b53af (on top of 3f89dea). Only tests changed; no lib changes.

- **I1** `test_a_paused_slot_sends_nothing` now takes `requests_mock`, registers `ANY, ANY` and asserts `call_count == 0`. Mutation M4: I commented out the guard in `get_car_api` (`elif not slot.usable("read"): return False, None`), ran the test and restored the file. It failed with `AssertionError: assert (True, {'state': 'online'}) == (False, None)`.
- **I2** New test `test_a_refused_owner_read_hands_reads_to_fleet`. Both tokens are held and Owner `vehicle_data` returns 403. Poll 1 makes 1 Owner online call, 1 Owner data call, 0 Fleet online calls (it reuses the awake cache; see the comment, which covers m3) and 1 Fleet data call, and the Owner slot is paused. The next poll that must read (`update_location(0)`) makes no Owner call and 2 Fleet data calls in total. Mutation M2: I changed the Fleet gate to `ownerSlot.empty()`, ran the test and restored the file. It failed with `assert (False is True)`, `update_charge()` returning False.
- **m1 (fixed)** New test `test_a_data_only_fleet_token_reads_but_never_commands`. With `scp=["openid","vehicle_device_data"]`, `available(READ_CHARGE)` and `ready(READ_CHARGE)` are True. `available(SET_AMPS/WAKE)` and `ready(SET_AMPS)` are False, and the tier is "observed". Mutation M10: I changed `available(READ_*)` to use `usable("command")`, ran the test and restored the file. It failed with `assert (False is True)` on `available('readCharge')`.
- **m2 (not fixed, carried forward):** every listed Tesla now shows two claims on vehicles.html.j2 and vehicleDetail.html.j2. Left for Task 10, or for a later task that shows claim status.
- **m3:** no fix needed. It is documented in the I2 test's comment.
- I restored each mutation by copying the file back from scratchpad (no stash). `git diff lib` was empty before the commit.
- Full suite: 1228 passed, 1 xfailed (1226 + 2 new).
