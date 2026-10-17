### Task 8: Provider declarations as data

**Files:**
- Modify: `Vehicle/Providers/Provider.py`, `Suppressions.py`, `Gen2TWCProvider.py`, `Gen3TWCProvider.py`, `TeslaBLEProvider.py`, `TeslaAPIProviders.py`, `HomeAssistantProvider.py`, `TelemetryProvider.py`, `Vehicle/TeslaAPI.py` (`wakeOutcome` and the `wake_up` 403), `Vehicle/TeslaTokenSlot.py` (`RETIRED_ON_REFUSAL` gains `"wake"`; `SCOPES["wake"] = ("vehicle_charging_cmds", "vehicle_cmds")` and `SCOPE_LABELS["wake"] = "waking the car"`, without which `usable("wake")` raises `KeyError`; pre-flight M4).
- Test: `tests/unit/test_provider_tables.py`. Adjust the suppression doubles: `test_provider_order.py:66–77`, `test_vehicle_priority.py:43–51`, `test_provider_outcomes_local.py:49` (a `Mock(local=False)` provider; pre-flight M5).

**Interfaces:**
- Produces (`Provider`):
  - `DECLARATIONS: Dict[str, Declaration] = {}`; `declarations()` returns `self.DECLARATIONS`. Each provider's table equals its current `declarations()` output: Gen2, Gen3, TeslaBLE, Owner, Fleet, HA, telemetry.
  - `SUPPRESSED: Optional[Dict[str, FrozenSet[str]]] = None`: condition → capabilities. A provider with no table (`None`, including test doubles and `Mock`s) falls back to the locality rule: `CLOUD_SUPPRESSED` when `not provider.local`, else `{}` (`suppressedFor(provider, condition)` helper; fails closed, as today; pre-flight M5). Conditions are `"ble_only"`, `"api_only"` and `"localStops"` (`chargeStopMode` 2/3).
  - `CLOUD_SUPPRESSED = {"ble_only": COMMANDS, "localStops": frozenset({STOP_CHARGING})}` is used by Owner, Fleet, HA and telemetry. TeslaBLE uses `{"api_only": ALL}`.
  - `ready()` stays a method on each provider.
  - `attempts()` and HA's override stay until Task 13, which deletes them with `dispatch` and `VehiclePriority` (both still walk them; pre-flight H1). The reconciler never calls `attempts()`.
- Produces (`Suppressions`):
  - `conditions(self) -> FrozenSet[str]`: `{commandPolicy}`, plus `"localStops"` when `chargeStopMode` ∈ (2, 3).
  - `suppressed(provider, capability)`: the explicit setting, then `any(capability in suppressedFor(provider, c) for c in conditions())`.
- Produces (`TeslaAPI`), ledger Task 5 M2:
  - A 403 on `wake_up` records `reportScopeRefused("wake", refused=True)`, not `"command"`.
  - That 403, and every later wake while `not slot.usable("wake")` (which sends no request), returns `Outcome(UNREACHABLE, "wake refused")`, not `REFUSED`. A REFUSED would exclude FleetAPI from every command for the desire (Task 7 `noteOutcome`); UNREACHABLE only aborts this billed command (I2 guard) and is `NOT_SENT`. A command that needs no wake (stop, amps, a lower) still goes over Fleet. BLE's REFUSED wake (key refused) is unchanged.
  - `wakeOutcome` checks `slot.usable("wake")` before the free online check. `slotFor("command")` stays the slot chooser.
  - `setTokens` lifts it.

- [ ] **Step 1: Write the failing tests.**

```python
# helpers in this file: providers_of_every_kind() (one real instance per provider class, as test_provider_registration builds them) and master(settings) (a Mock master with .settings and .config; pre-flight L5)
def test_tables_match_the_declarations_they_replace():
    for p in providers_of_every_kind(): assert p.declarations() is type(p).DECLARATIONS
    assert FleetAPIProvider.DECLARATIONS[C.SET_AMPS] == C.Declaration(C.FLEET_COMMAND, C.RateLimit(50, 60))
    assert HomeAssistantProvider.DECLARATIONS[C.STOP_CHARGING].rateLimit == C.RateLimit(1, 10)

def test_a_provider_without_a_table_is_suppressed_by_locality():          # pre-flight M5
    m = master({"commandPolicy": "ble_only"}); assert Suppressions(m).suppressed(Mock(local=False, SUPPRESSED=None, name="X"), C.SET_AMPS)

def test_suppressions_come_from_the_tables():
    m = master({"commandPolicy": "ble_only"}); s = Suppressions(m)
    assert s.suppressed(fleet, C.SET_AMPS) and not s.suppressed(ble, C.SET_AMPS)
    m.settings.update(commandPolicy="api_only"); assert s.suppressed(ble, C.READ_CHARGE) and not s.suppressed(fleet, C.SET_AMPS)
    m.settings.update(commandPolicy="prefer_ble", chargeStopMode="3"); assert s.suppressed(fleet, C.STOP_CHARGING) and s.suppressed(ha, C.STOP_CHARGING) and not s.suppressed(gen2, C.STOP_CHARGING)

def test_a_403_on_wake_refuses_wakes_only(requests_mock):                    # paid calls counted
    ...; assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake refused") and len(calls(requests_mock, "wake_up")) == 1
    assert p.wake(VIN) == O.Outcome(O.UNREACHABLE, "wake refused") and len(calls(requests_mock, "wake_up")) == 1
    assert p.setAmps(VIN, 10).kind == O.DONE and api.fleetSlot.usable("command")
```

  Task 9 adds the reconciler-level counterpart: `test_a_refused_fleet_wake_does_not_exclude_fleet_for_the_car`. A 403 wake on a start, then a stop for the same car, gives one `charge_stop` POST and 1 `wake_up` in total.

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** `$PYTEST tests/unit/test_provider_tables.py tests/unit/test_provider_order.py tests/unit/test_provider_capabilities.py tests/unit/test_provider_outcomes_cloud.py tests/unit/test_provider_outcomes_local.py -q --timeout=60 -p no:cacheprovider`, then the full suite → PASS.
- [ ] **Step 5: Commit.** `git commit -m "Declare provider capabilities, costs and suppressions as tables; a refused Fleet wake retires wakes only"`

