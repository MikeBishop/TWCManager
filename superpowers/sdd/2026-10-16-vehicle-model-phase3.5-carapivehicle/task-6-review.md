# Task 6 review: Owner and Fleet commands follow the provider order

Commit 2facd2f on base 64c3932 (wt-vm35). Read-only review.

## Verdicts
- **Spec compliance: ✅**
- **Code quality: Approved.** No Critical or Important findings. There are a few Low and Info notes below.

## Verification run
- Full unit suite at HEAD (`tests --ignore=tests/API --ignore=tests/integration`): **1846 passed, 1 xfailed**. This matches the report.
- HEAD tests against BASE lib, in a temporary worktree: lib checked out at 64c3932, the 5 affected test files run, worktree removed afterwards. Result: **19 failed, 177 passed**. The report says 15. The behavioural failures are the ones that matter:
  - all 5 new parity cases (`test_both_tokens_off_car_commands_free`, `..._matches_owner_only[×4]`);
  - `test_both_tokens_go_to_owner`;
  - `test_both_tokens_owner_refusal_hands_to_fleet[×5]`;
  - `TestBothTokens::test_off_car_commands_through_owner`.

  The other failures are `canCommand` AttributeErrors in translated asserts. `test_other_cars_*` (×6) pass on BASE. That is correct: they are guards for behaviour that did not change.
- Lib delta from `git diff --numstat` on lib: +36/−42, so **−6**. Confirmed.
- Remaining callers:
  - Nothing in lib, tests/integration or tests/API calls `command()` or `wakeOutcome()` without `slot=`. The keyword is required now, so a missed caller would raise rather than silently pick a slot.
  - `commandSlotFor` is gone from lib, tests and docs.
  - No stale "Fleet first" wording is left in lib or docs.
- requests_mock records unmatched requests in `request_history`. I checked this directly. So the `"fleet-api" not in q.url` and `paid(...) == (0,0,0)` assertions would catch a stray Fleet request in the Owner-mocked parity runs.

## Check 1: no cross-token send
- `canCommand(vehicle, slot)` (TeslaAPI.py:508) answers for the slot it is given:
  - Owner slot: `ownerCommandsAllowed(car)`.
  - Any other slot: `slot.usable("command")`.
- `command()` (TeslaAPI.py:1450) and `wakeOutcome()` (TeslaAPI.py:1528) send with that same `slot`. The old `slot = chosen` substitution is deleted, so no path swaps tokens.
- Providers always pass `getattr(self.carapi, self.slotName)` (TeslaAPIProviders.py:95, 113, 134).
- Broadcast (vehicle None):
  - `OwnerAPIProvider.ready(None, …)` and `FleetAPIProvider.ready(None, …)` both return False for commands, so no command is sent with no vehicle.
  - `available()` affects only `ProviderOrder.ordered()` and the TWCMaster READ_CHARGE gate. The Owner gate now opens with both tokens, but it is harmless because the per-car `ready` decides.
  - `canCommand(None, ownerSlot)` would raise. No caller passes None: all are `_listed()` vehicles, or attached vehicles in `ready`/`refuseCommandFor`.
- Wakes: `wakeOutcome` has the same gate.
  - The free online check uses `slot` if it can read, else `slotFor("read")`. That is a free GET, not a command, and it was the same before.
  - An Owner 403 on `wake_up` goes through `ownerRefusal`. It latches the car and returns REFUSED "signing required" (NOT_SENT, EXCLUDING), so Fleet's wake on the next pass is the intended handover.
- `stopCharging`'s asleep short-cut (TeslaAPIProviders.py:113) checks `canCommand` for the provider's own slot. Its `onlineState` is the free read-slot check. The command it falls through to still goes through the `command()` gate.
- Debug API: `ProviderOrder.debugCommand` (Order.py:136) takes the first candidate with a module and submits one Attempt for that provider. For an "off" car with both tokens that is now OwnerAPI, and it sends with the Owner token. It is one-shot, so a refusal does not fall through to Fleet. That is acceptable and matches the "never sent twice" contract.

## Check 2: paid spend
I traced `Reconciler.plan` (Reconciler.py:250-360) and `Desired` outcome handling (Desired.py:325-380). Key points:
- OwnerAPI's commands are `OWNER_COMMAND` = `Cost(TIER_BILLED, 0.0)`, the same tier as Fleet, and rank 4 < 5. So `paid[0]` is OwnerAPI until it is excluded.
- An Owner send counts against `paidSends`. Fleet can only be chosen once Owner is in `rec.excluded`, which takes REFUSED (or UNSUPPORTED).

Results by Owner outcome:
- **Owner 500 / bad body** (ERROR, sent): blind retry goes to `paid[0]` = Owner again. After two sends the budget is spent. **No Fleet send.** Covered by `matches_owner_only[retry]`.
- **Owner 408 / asleep / failed wake** (UNREACHABLE, sent): same as 500, plus `delayNextWakeAttempt` on the shared car record, which also holds any later Fleet wake. Covered by `matches_owner_only[asleep]`.
- **Transport timeout** (ERROR exception-type): same as 500.
- **Owner 429** (TeslaAPI.py:442):
  - It raises the car's `errorCount` to 30 or more and stamps the car's backoff. That backs off this car's reads (Owner, free) and also blocks any Fleet command or wake for the car: `command()`/`wakeOutcome()` check `getCarApiRetryRemaining(car)` before any I/O and return UNREACHABLE "backoff" (NOT_SENT, waits RETRY).
  - So a 429 can never cause a Fleet send. It costs only availability for the backoff window.
  - Before this change, in a both-token install a Fleet 429 did the same thing, and an Owner command 429 could not happen. Info only (I-1).
- **Owner 401** with an expired token and a failed refresh: REFUSED "401". It is not NOT_SENT, so it counts one `paidSends` and excludes Owner. Fleet then has one send left in this arm. That means less spend, not more, though Fleet's first chance is one send shorter (I-2).
- **Owner refusal** (403/VCP/410/412/fleetapi-only): NOT_SENT and EXCLUDING. Fleet sends on the next pass with no RETRY wait and gets a full budget. This is the brief's intended handover, checked end to end in `test_both_tokens_owner_refusal_hands_to_fleet` (`paidSends == 1`, `lastProvider == "FleetAPI"`, later desire Fleet-only).

Install combinations:

| Install | Result |
|---|---|
| Owner-only (off / required / missing) | Unchanged: `canCommand(owner)` ≡ the old `commandSlotFor` result when Fleet is unusable. Row 3b and the existing parity rows pass. |
| Fleet-only | Owner `available` is False (no owner token). Fleet unchanged. |
| Both tokens, off car | Owner only, $0 (new row 3c). Fleet only after a refusal or 401. |
| Both tokens, required / missing / unknown car | Owner `ready` False, no HTTP. Fleet as before (`test_both_tokens_other_cars_go_to_fleet`, `test_other_cars_command_through_fleet_only`). |
| Mixed fleet, both tokens | Decided per car. A 429 backoff is per car (`target = car`). |
| BLE / ble_only / prefer_ble / api_only / HA | Untouched. Owner and Fleet share TIER_BILLED, so the free-first, PAID_AFTER and suppression rules apply to the pair as before. `ble_only` suppresses cloud (CLOUD_SUPPRESSED) for both. |

**Net: no new paid Fleet calls in any combination.** With both tokens, Fleet commands and wakes for "off" cars drop to $0 unless Tesla refuses Owner.

## Check 3: read-only hints
- `refuseCommandFor` (TeslaAPI.py:1335) returns False when either slot can command the car. A car Fleet can command never reaches the per-car line. Tested with caplog in `test_other_cars_command_through_fleet_only`.
- Module-wide `noteReadOnly` and `readOnly` are unchanged and still keyed on the Fleet slot plus the Owner cars.
- Template `ownerTokenOnly` keeps its meaning: an Owner token and no Fleet command token. It is still correct for choosing the Owner-token paragraph.
- I-3: with both tokens, the "else" paragraph still says REST charge commands need the VCP, and does not mention that "off" cars now go to Owner for free. This was imprecise before too. Optional.

## Check 4: locks, I/O, logs
- `canCommand` reads slot and car fields only. No lock, no I/O.
- `ready` and `available` still do no I/O.
- No new log line, so no token can reach a log.
- `_request` logs only method, path and status.

## Check 5: tests
- The test map in the report matches the diff. Both INTENTIONALLY CHANGED tests are marked and rewritten to the new expectation:
  - `test_off_car_commands_through_fleet` → `..._through_owner`;
  - `test_both_tokens_go_to_fleet` → `..._go_to_owner`.
- Translated asserts keep their intent. The dropped `commandSlotFor(None)` assert is justified because there is no vehicle-less chooser now.
- The new tests exercise the change (they fail on BASE, see above) and go through the real reconciler walk where the brief requires it (req 4).
- `matches_owner_only` is a strong design: it asserts that adding a Fleet token changes nothing in commands, request shape or per-pass paid records.
- **L-1 (report accuracy):** the report says "15 failed and 177 passed" on unchanged lib. I measured 19 failed / 177 passed. Cosmetic.

## Check 6: dead code and lib size
- −6 is confirmed. `commandSlotFor` is fully removed.
- `ownerTokenOnly` (TeslaAPI.py:503) is now used only by the login template (plus the template test). It is still needed there, so it is not dead. Inlining it into Jinja would move logic into the template for about 3 lines saved. Not recommended.
- **L-2 (optional, small duplication):** `OwnerAPIProvider.available` (TeslaAPIProviders.py:173-176) repeats the first two clauses of `ownerCommandsAllowed`, namely `ownerTokenHeld() and "command" not in ownerSlot.refusedPurposes`. A shared helper would not shrink the lib, because the third and fourth clauses are per car. Leave it.
- `refuseCommandFor`'s `canCommand(vehicle, self.fleetSlot)` is just `fleetSlot.usable("command")`. The symmetric form reads well and costs nothing. Fine.

## Findings
- **I-1 (Info), TeslaAPI.py:442.** With both tokens, an Owner command 429 now backs off the car's free reads and its Fleet commands for the backoff window. There is no spend and no Fleet send. The window is a short availability loss, the same as a Fleet 429 before. Worth a PR-notes line at most.
- **I-2 (Info), TeslaAPI.py:394-415 / Desired.py:343-360.** An Owner 401 whose refresh fails is "sent" REFUSED. It uses one of the arm's two paid sends before Fleet takes over. That is conservative (less spend). No action.
- **I-3 (Info), handle_teslalogin.html.j2:15-20.** With both tokens, the login-success text does not mention free Owner commands for "off" cars. Pre-existing wording. Optional.
- **I-4 (Info), TeslaAPI.py:1404-1430.** As the implementer noted, the Owner latch/retire messages tell a user who has both tokens that they need a Fleet token. This is redundant but true. Left alone to avoid lib growth. Agreed.
- **I-5 (Info), docs/Settings.md:59.** "billed providers (the Fleet API, then Home Assistant) last" does not name the Owner API, which is now ahead of Fleet. Pre-existing and outside the brief's named docs. Optional follow-up.
- **L-1 (Low), task-6-report.md "Tests".** The BASE run is 19 failed, not 15. Report accuracy only.
- **L-2 (Low/optional), TeslaAPIProviders.py:173-176.** Small overlap with `ownerCommandsAllowed`. Not worth changing.
