# Task 5 report: port #659 (Owner API commands for command_signing "off") onto Phase 3.5

Status: DONE. Worktree wt-vm35, branch vehicle-model/phase3.5, base 6c4ba54. Not pushed.

## Commits
- 5190831 Let the Owner API command cars Tesla lists with command_signing off (#659). Ported from 2ef5ba3, 3a3c4ff, 72439ec, 3489e93: lib, templates, and all ported tests.
- 3ffd8c8 Pin owner-only "off" car parity with Fleet-only command paths (#659). New parity test (brief constraint).
- 40f77ca Document per-vehicle Owner API commands (#659). Ported from f0a7b4b: CHANGELOG, docs/README.md, docs/modules/Vehicle_TeslaAPI.md.

## Tests
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1829 passed, 1 xfailed**. Baseline was 1783 + 1 xfailed, so 46 tests were added: 43 ported from the reference and 3 new parity cases. The run's one warning comes from test files this task did not change: the 8 changed test files run together with 0 warnings. pytest.ini has `--disable-warnings`, so the source is not printed.
- `tests/integration --collect-only -q`: 212 collected.
- test_command_path_parity.py: the existing 31 rows pass unchanged, so their paid counts did not move. The 3 new parametrized cases are added on top.
- Test-first: the ported tests were applied before any lib change. They failed (41 failed / 317 passed in the affected files), then passed after the port.
- Black: `black --check` passes on all 7 changed lib .py files.
- test_registry_callers.py guard still passes. No `carApiVehicles|CarApiVehicle|getVehicleByVIN|.VIN` came back.

## Lib delta
`git ls-files lib | grep '\.py$' | xargs cat | wc -l`: 27,098 -> **27,358 (+260)**. The reference was +267.
Where it saves against the reference:
- 3.5's `_listed` is reused; there is no `_car`/`getVehicleByVIN`.
- `readOnlyFor` is dropped: `commandSlotFor(v) is None` covers it.
- There is no `CarApiVehicle.__init__`/`_bind` plumbing; the state lives on `CarApiState` class defaults.

## How each brief requirement is met
1. **command_signing in CarApiState.** `CarApiState` gains class defaults `commandSigning = None`, `ownerCommandsRefused = False` and `refusalLoggedAt = None`. `addVehicle` builds the state and sets `commandSigning = json.get("command_signing")` before `getOrCreate(..., attach=...)`, so the attachment lands complete under the registry lock. There is no separate map.
2. **OwnerAPI claim.** It is now `vehicle.claim("OwnerAPI", lambda: self.ownerCommandsAllowed(state), "listed")`. `ownerCommandsAllowed(car)` takes the CarApiState, is False for None, and fails closed unless signing is exactly "off".
3. **readOnly / _signingState.** Both iterate `self.registry.attached("TeslaAPI")` pairs; `_signingState` keys on `vehicle.vin`. `noteOwnerCommandsRetired` does the same.
4. **commandSlotFor(vehicle).** It takes the registry Vehicle (None means any car). It returns Fleet first, else the Owner slot only via `ownerCommandsAllowed`. `command()`, `wakeOutcome()` (both now take `slot=`) and the base provider's `stopCharging` use it. The wake guard `slot is self.fleetSlot and not slot.usable("wake")` is needed because the Owner slot never grants "wake".
5. **Command methods moved.** `ampsRange`, `clock`, `_listed`, `_command`, the four commands and `wake` move to `_TeslaAPIProvider`. `_command` and `wake` pass `slot=getattr(self.carapi, self.slotName)`. `OwnerAPIProvider` declares the five commands at `OWNER_COMMAND = Cost(TIER_BILLED, 0.0)`, gets a per-car `ready` (which calls `refuseCommandFor`) and an `available` broadcast gate. `stopCharging` keeps 3.5's `onlineState(...) is False` form.
6. **_classify.** The parameter changed from `car=` to `vehicle=`, both in `_request` and `_classify`. Only two lib callers pass it (`_paidPost`, `get_car_api`), and no test calls either directly. `car` is derived for the 429 target. A paid Owner answer goes through `ownerRefusal` before the generic 403/412 branches, and also on HTTP 200:
   - 410/412/"only available on fleetapi" means `noteOwnerCommandsRetired`: the slot refuses "command" and one error line is logged.
   - 403 or VCP text means `noteOwnerCommandRefused`: that car is latched and a warning naming it is logged.
   - Neither calls `updateCarApiLastErrorTime`. Tesla's error text is matched but never logged.
7. **3489e93 kept.** "signing required" and "owner commands retired" are in `NOT_SENT`, and the H2 hold in `Reconciler.plan` skips `EXCLUDING` kinds. Those files were applied verbatim, since 3.5 had not touched them.
8. **Docs and templates.** CHANGELOG, docs/README.md, Vehicle_TeslaAPI.md, handle_/request_teslalogin.html.j2, VehicleEndpoint.py and TeslaTokenSlot.py applied cleanly with `git apply --3way`. The wording is still accurate on 3.5: "TWCManager reads the vehicle list once" holds, because `loadVehicleList` lists only while nothing is attached. "Until it restarts" also holds, because attached cars never expire and the state is never rebuilt.
9. **Tests ported** onto 3.5 plumbing. `add_home_vehicle` keeps returning the registry Vehicle and gains `command_signing/vin/name/id`. Every `api.carApiVehicles[...]` use is replaced by `registry.attached("TeslaAPI")`, `registry.get(VIN)` or a `listed(api, i)` helper.

## Review findings 2 and 3
Both were already fixed in the reference by 72439ec, which came after the review; they were ported as-is.
- **Finding 2.** `refuseCommandFor` checks `"command" in ownerSlot.refusedPurposes` first ("Tesla refused commands with the Owner API token ..."), and `refusalState` includes that flag, so the line re-logs when it changes. Test: `TestOwnerCommandsRetired::test_per_car_line_names_the_token` (2 lines; the second names the token, not command_signing).
- **Finding 3.** `_classify` runs `ownerRefusal` on a paid Owner HTTP 200, so a 200 whose body carries the VCP error latches the car before `_paidPost` can reach the TypeError path. Tests: `TestOwner403Latch::test_vcp_error_on_http_200_latches[command|wake]` (outcome REFUSED "signing required", one POST, latched, no backoff) and `TestOwnerCommandsRetired::test_retired_on_http_200`.
- **Finding 5:** unchanged, as the brief accepts.

## Test map (every deleted or rewritten test)
| Test | Change |
|---|---|
| teslatokens.add_home_vehicle | Extended with `command_signing, vin, name, id`; still returns the registry Vehicle |
| test_teslaapi_registry::test_debug_interface_resolves_by_vin (reference: test_carapivehicle_registry) | `wakeOutcome` assert adds `slot=api.fleetSlot` |
| test_teslaapi_providers::test_two_providers_with_honest_costs | `owner.cost(SET_AMPS) is None` becomes `== OWNER_COMMAND`, price 0; adds `owner.available(SET_AMPS) is False` |
| test_teslaapi_providers::test_fleet_commands_resolve_the_car_by_vin | Asserts gain `slot=api.fleetSlot`; "Owner declares no commands / UNSUPPORTED" becomes "owner sends with slot=api.ownerSlot" |
| test_provider_tables::test_tables_match_the_declarations_they_replace | OwnerAPI declarations gain the 5 commands at OWNER_COMMAND |
| test_teslaapi_readonly_gate module docstring | Rewritten for per-car commands |
| TestRefusalHint::test_logged_once_per_state_change | Now uses a token-less api (the module line is only for no token); same assertions |
| TestRefusalHint::test_resync_of_owner_token_does_not_log_again | Drives `OwnerAPI.ready` (the per-car line) instead of the Fleet broadcast gate |
| TestCheckChargeRefreshesEachModuleOnce (owner token) | `readOnly is True` becomes `slotFor("command") is None` |
| test_teslaapi_refresh (4 tests) and TestNoClientID | `readOnly is True` becomes `slotFor("command") is None` (an Owner token with no cars listed is not readOnly now) |
| test_teslaapi_refresh login page tests (2) | `Mock(readOnly=...)` becomes `Mock(ownerTokenOnly=...)`; adds a command_signing text check |
| test_teslaapi_token_classification (3 asserts) | `readOnly is True` becomes `slotFor("command") is None` |
| test_teslaapi_token_slots::test_readonly_property_follows_fleet_slot | Lists a car (no signing) before asserting readOnly |
| test_teslaapi_token_slots::test_slot_for_is_uniform_walk | Drops the `owner_only.readOnly` assert (covered by the gate tests) |
| test_command_path_parity install() | Sets `clock` on both registered providers (was FleetAPI only; set inside the register loop, since `providers()` builds fresh instances) and passes `command_signing` (None for every existing row, so unchanged); `FleetCar` gains `api=` base (default Fleet) |

Added: the gate test classes TestOffCarCommandsThroughOwner, TestOwnerTokenRefusesOtherCars, TestMixedFleet, TestBothTokens, TestOwner403Latch, TestOwnerCommandsRetired, TestThroughTheWalk and TestVehicleEndpointPerCar, plus `test_owner_token_names_the_car_not_the_module`. Also added: test_limit_reconciler::test_a_not_sent_refusal_lets_the_next_paid_provider_go_at_once, and test_command_path_parity::test_owner_only_off_car_matches_fleet_only[raise|retry|stop]. The parity test checks identical request method and path sequences between Fleet-only and owner-only-"off", the same commands, and nothing paid or "other" on the Owner side.

Translation notes in the gate tests:
- `car.vehicle` becomes the registry Vehicle from the pair.
- `readOnlyFor(car)` becomes `commandSlotFor(vehicle) is None`.
- `car.update_vehicle_data()` / `car.batteryLevel` become `api.update_vehicle_data(vehicle)` / `vehicle.value("batteryLevel")`.

## Constraints
- **Fleet-only, BLE, HA and Gen3:** unchanged. The 31 parity rows pass, and the Fleet provider's budget key and cost are unchanged. The intended changes from the reference stand: a Fleet token without command scope lets the Owner token command "off" cars, and handover after an Owner refusal is faster (NOT_SENT).
- **No new paid Fleet calls.**
- **Locks:**
  - `readOnly`, `refuseCommandFor` and `noteOwnerCommandsRetired` take only the registry leaf lock (`attached()`).
  - The claim lambda reads slot state only, as the existing Fleet claim lambda does.
  - No I/O under any lock: `ownerRefusal` runs in `_request`, outside the locks. The "list" purpose under vehicleListLock never takes the owner path, because `paid` is False there.
- **Logs:** no token is logged, and Tesla's error text is never logged.

## Self-review
- The `_classify` signature changed from `car` to `vehicle`. This was needed to name the car in the latch warning, since CarApiState has no name. Checked: the 429 path still backs off the per-car state, and the "read" callers pass the same vehicle.
- `refuseCommandFor` assumes the vehicle is attached. Its only caller, `OwnerAPIProvider.ready`, checks the attachment first. `noteOwnerCommandRefused` guards `car is not None`.
- Latch lifetime: a forget detaches; `expire` skips attached cars; a re-list happens only when nothing is attached. So the latch holds until restart, as the docs say.
- `readOnly` with an Owner token and no cars listed is False, as in the reference. The login-success template now keys on `ownerTokenOnly`.

## Concerns
- Lib grows +260, as a feature is expected to. It is under the reference's +267, but only just. The verbose refusal-line text (4 `why` branches) and the three `note*/ownerRefusal` methods are most of it. I found nothing duplicated against the 3.5 structure.
- `_signingState` is kept as the brief asks. It only affects the module-wide line, which now logs only when no Owner token is held, so in practice it rarely matters. It could be dropped (about 7 lines) if the reviewer agrees.
- The parity test compares request shapes for 3 scenarios (asleep raise, 500 retry, stop). It does not separately compare `paidSends`/`paidReached` accounting as the peer's scratch did. Identical request sequences across 3600 s of passes imply the same pacing.

No `readOnly` use in tests/integration or tests/API (grep), so the readOnly semantic change (an Owner token with no cars listed is not read-only) touches no integration test.

## Fix round 1
Commits:
- b2f0cdb: S1, S2 and L2.
- 64c3932: the reviewer's paid-records test, adopted.

What changed:
- **S1.** `_signingState` is deleted. `noteReadOnly` keys on `fleetSlot.changes` again, and the comments on `refusalLoggedAt` and `noteReadOnly` are restored to match. No test pinned the old key.
- **S2.** The "field missing" and "unknown value" branches in `refuseCommandFor` are merged into one reason: "Tesla did not report command_signing: off for it, so it is treated as read-only." The unused `signing` local is gone.
  - Rewritten test: `TestOwnerTokenRefusesOtherCars::test_unknown_car_is_named_once[None|weird]` now asserts the one wording. It used to expect "did not report" or "does not know" depending on the case.
- **L2.** The duplicated `commandSlotFor` asserts are removed from `test_module_is_not_read_only` and `test_refused_without_http`.
- **Item 4.** `scratchpad/t5review/test_t5_paid_records.py` is folded into `test_command_path_parity.py` rather than added as a separate file.
  - The row 3b test now runs through `off_car_run` and also checks the per-pass paid records (`paid_records`: paidSends, paidReached, paidRetryDue, paidAt, lastOutcome, lastOutcomeAt for CHARGE_LIMIT and CHARGING).
  - A fourth scenario, "asleep" (the car never wakes, so commands get 408), joins raise, retry and stop. The parametrized case grows from 3 to 4.
  - The test asserts:
    - the expected commands;
    - that some paid send was recorded;
    - that the owner and Fleet runs are equal on commands, request shape and per-pass records;
    - that the owner run pays nothing and makes no "other" requests.

Results:
- Full suite: **1830 passed, 1 xfailed**.
- tests/integration collects 212.
- The 31 existing parity rows are unchanged.
- Black is clean.
- Lib: **27,347 (+249 vs BASE 27,098)**.
