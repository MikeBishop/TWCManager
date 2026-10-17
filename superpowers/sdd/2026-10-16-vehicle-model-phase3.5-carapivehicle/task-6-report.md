# Task 6 report: Owner and Fleet commands follow the provider order

Status: DONE. Worktree wt-vm35, branch vehicle-model/phase3.5, base 64c3932. Not pushed.

## Commit
- 2facd2f Send Owner and Fleet commands in provider order, not Fleet first

## Tests
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1846 passed, 1 xfailed** (baseline 1830 + 1). The 16 added cases are listed below.
- `tests/integration --collect-only -q`: 212 collected.
- Test-first: the tests were written first. Run against unchanged lib, 15 failed and 177 passed in the 5 affected files. All pass after the lib change.
- Black: `--check` is clean on the 3 changed lib files.

## Lib delta
27,347 -> **27,341 (-6)**.

## What changed (lib)
- **`TeslaAPI.commandSlotFor` is deleted.** It is replaced by `canCommand(vehicle, slot)`:
  - The Owner slot can command when `ownerCommandsAllowed(car)` holds: an owner token, the Owner slot not refused "command", signing exactly "off", and the car not latched.
  - Any other slot can command when `slot.usable("command")`.
  - A provider asks only about its own slot, so neither provider ever sends with the other's token.
- **`command()` / `wakeOutcome()`:** `slot` is now a required keyword. They refuse ("no command token") unless `canCommand(vehicle, slot)`. The old chooser code is gone: `chosen`, `slot not in (None, chosen)` and `slot = chosen`.
- **`_TeslaAPIProvider.stopCharging`:** the asleep short-cut now uses `canCommand(vehicle, own slot)`.
- **`OwnerAPIProvider`:**
  - `ready` (commands) returns `canCommand(vehicle, ownerSlot)`, after the `refuseCommandFor` hint as before.
  - `available` (commands) returns `ownerTokenHeld() and "command" not in ownerSlot.refusedPurposes`. It used `ownerTokenOnly`, which encoded Fleet-first.
- **`refuseCommandFor`:** a car counts as commandable if `canCommand(vehicle, fleetSlot) or canCommand(vehicle, ownerSlot)`. Its meaning is unchanged: read-only only when no provider can command it. A car Fleet can command gets no per-car line.
- **Unchanged:**
  - `ownerTokenOnly` is kept. The login template still uses it, with its user-facing meaning: only an Owner token for commands.
  - `readOnly`, `noteReadOnly`, `refusalState`, and the wake guard (`slot is fleetSlot and not slot.usable("wake")`).
- Comments that named `commandSlotFor` were updated in TeslaAPI.py, TeslaAPIProviders.py and TeslaTokenSlot.py.

## Brief requirements
1. **OwnerAPI ready iff** the car is listed, `ownerCommandsAllowed(car)` holds and the Owner slot is not refused "command". A Fleet token no longer matters. Test: `TestBothTokens::test_off_car_commands_through_owner`, which checks Owner ready+available with both tokens and `candidates == ["OwnerAPI", "FleetAPI"]`.
2. **FleetAPI ready** is unchanged, textually.
3. **Each provider sends with its own slot.** Tests:
   - `test_off_car_commands_through_owner`: the Owner send carries the Owner bearer and the Fleet send carries the Fleet bearer.
   - `test_fleet_provider_still_refuses`: Fleet never sends with the Owner token. This test is unchanged.
   - The direct `api.command/wakeOutcome` tests now pass an explicit slot.
4. **Owner refusal hands over to Fleet with no RETRY wait.** This goes through the real reconciler walk. Test: `TestThroughTheWalk::test_both_tokens_owner_refusal_hands_to_fleet[403 VCP | 200 VCP | 410 | 412 fleetapi-only | 200 fleetapi-only]`:
   - pass 1: one Owner POST and no Fleet POST;
   - pass 2: one Fleet POST with the Fleet bearer, with `paidSends == 1` and `lastProvider == "FleetAPI"`;
   - a later desire goes to Fleet only;
   - no API error is recorded.
5. **Both tokens with a "required", missing or unknown car:** Fleet only, zero Owner calls. Tests:
   - `TestThroughTheWalk::test_both_tokens_other_cars_go_to_fleet[required|None|weird]` (walk);
   - `TestBothTokens::test_other_cars_command_through_fleet_only[...]`: the Owner provider is not ready, refuses without HTTP, `readOnly` is False, and no "read-only" line is logged.
6. **Read-only hints:** `test_no_per_car_hint_while_fleet_commands` is unchanged and passes, and the new test above covers the case too. The template meaning of `ownerTokenOnly` is unchanged.
7. **Paid counts:**
   - All existing test_command_path_parity rows are unchanged and pass. No existing row has both tokens and an "off" car: both-token rows use `signing=None`. So no row is INTENTIONALLY CHANGED.
   - Added row 3c `test_both_tokens_off_car_commands_free`: both tokens, an "off" asleep car, a policy raise 50->80 and a start over 3600 s. It sends `charge_start` and `set_charge_limit` on the Owner API only, no request touches fleet-api, paid is (0,0,0), $0, and nothing "other".
   - Also added `test_both_tokens_off_car_matches_owner_only[raise|retry|asleep|stop]`. It runs row 3b's four scenarios with a Fleet token added. Commands, request shape and per-pass paid records are identical to owner-only, with no paid request. This also covers a car that never answers (408) or a 500: an Owner failure does not spill into a paid Fleet attempt in the same desire.

## Test map (deleted or rewritten)
| Test | Change |
|---|---|
| gate module docstring | Adds the both-token, provider-order rule |
| `TestOffCarCommandsThroughOwner::test_module_is_not_read_only` | `commandSlotFor(v) is ownerSlot` -> `canCommand(v, ownerSlot)` |
| `TestOwnerTokenRefusesOtherCars::test_refused_without_http` | `commandSlotFor(v) is None` -> `not canCommand(v, ownerSlot)` (split from the `readOnly` assert) |
| `TestOwnerTokenRefusesOtherCars::test_off_must_match_exactly` | Same translation |
| `TestOwnerTokenRefusesOtherCars::test_owner_token_with_no_cars_listed_is_not_read_only` | Dropped the `commandSlotFor(None) is None` assert. There is no vehicle-less chooser now; `readOnly`/`ownerTokenOnly` are still asserted |
| `TestMixedFleet::test_each_car_decided_separately` | `commandSlotFor` -> `canCommand(·, ownerSlot)` |
| `TestBothTokens::test_off_car_commands_through_fleet` | **INTENTIONALLY CHANGED** -> `test_off_car_commands_through_owner`. Both providers are ready, the order is Owner then Fleet, and each sends with its own bearer |
| `TestBothTokens::test_fleet_token_without_command_scope_leaves_owner` | `commandSlotFor is ownerSlot` -> `canCommand(v, ownerSlot) and not canCommand(v, fleetSlot)` |
| `TestThroughTheWalk::test_both_tokens_go_to_fleet` | **INTENTIONALLY CHANGED** -> `test_both_tokens_go_to_owner`: one Owner POST with the Owner bearer, zero Fleet POSTs |
| `TestVehicleEndpointPerCar` | The local `wire_reads` import moved to the module import |
| test_teslaapi_request_errors: `run_path("command")`, the wake test (line 280), the 401-refresh command | Pass `slot=api.fleetSlot`, the slot the old default chose there. Assertions unchanged |
| test_teslaapi_token_classification::`test_unknown_token_makes_no_api_calls` | Asserts the refusal for both slots |
| test_teslaapi_token_slots::`test_commands_use_fleet_only` | Passes `slot=fleetSlot`; adds that the Owner slot refuses the (unsigned-unknown) car |
| test_teslaapi_token_slots::`test_command_refused_without_usable_fleet` | Asserts the refusal for both slots |

Added (16 cases):
- `test_other_cars_command_through_fleet_only` (×3)
- `test_both_tokens_owner_refusal_hands_to_fleet` (×5)
- `test_both_tokens_other_cars_go_to_fleet` (×3)
- `test_both_tokens_off_car_commands_free` (×1)
- `test_both_tokens_off_car_matches_owner_only` (×4)

## Docs
- **docs/modules/Vehicle_TeslaAPI.md:**
  - Owner commands now "sit with the Fleet API in the command order, just ahead of it".
  - The both-tokens paragraph is rewritten: an "off" car goes to the Owner API, then to Fleet at once after a refusal; other cars stay on Fleet and are not logged read-only.
- **CHANGELOG #659 line:** "used only when no Fleet API token can command" is replaced by the provider-order wording.

## Constraints
- No lock or I/O change. `canCommand` reads slot and car state only, as `commandSlotFor` did.
- No new log line, and no token in logs.
- Only the Phase 3.5 worktree was touched.

## Concerns
- **Wording (info):** with both tokens, the existing one-time Owner latch warning and the retirement error still say "Charge commands need a Fleet API token with the Vehicle Command proxy (teslaProxy) or the TeslaBLE module". That stays true when a Fleet token is present, but it is slightly redundant then. It was left unchanged to avoid lib growth.
- **Behaviour (intended):** a user with both tokens and an "off" car now has that car's commands and wakes go unsigned through the Owner API instead of the Fleet/proxy path. That is the decision; it is called out here for PR notes.
