# Review: #659 Owner API commands, vehicle-model/phase3 branch (2ef5ba3, f0a7b4b, 3a3c4ff)

Verdict: nothing blocking in the code for the reporter's setup. Two things need
fixing before merge: the merge claim about phase3.5 is false (hard conflicts and a
deep semantic overlap), and one per-car log line names the wrong reason. The rest
is low severity. Suite: 1785 pass (verified).

Scratch tests kept in scratchpad, not committed: scratch_659_parity.py,
scratch_659_edges.py (run with PYTHONPATH=wt-p3:wt-p3/lib ... --rootdir=wt-p3).

## Findings, ranked

### 1. CONFIRMED (process/high): phase3.5 does NOT merge cleanly, and the overlap is semantic, not textual
`git merge-tree --write-tree HEAD vehicle-model/phase3.5` exits 1 with content conflicts in
`lib/TWCManager/Vehicle/TeslaAPI.py`, `lib/TWCManager/Vehicle/Providers/TeslaAPIProviders.py`,
`tests/unit/teslatokens.py`, `tests/unit/test_teslaapi_providers.py`, and a modify/delete on
`tests/unit/test_carapivehicle_registry.py` (3.5 deletes it; this branch edits it).
3.5 (7d946ab "Dissolve CarApiVehicle") removes everything this diff hangs state on:
- `CarApiVehicle.__init__` (where `commandSigning`, `ownerCommandsRefused`, `refusalLoggedAt` are set, TeslaAPI.py:1757-1762) is gone; 3.5 attaches a bare `CarApiState` in `addVehicle` and claims `OwnerAPI` as a constant `False` there.
- `self.carApiVehicles` (used by `readOnly` 480-483 and `_signingState` 1299-1307) and `getVehicleByVIN` (used by `_TeslaAPIProvider._car`, Providers:131) are gone; 3.5 resolves cars via `vehicle.attachment("TeslaAPI")` and `registry.attached()` returning (vehicle, attachment) pairs.
- 3.5's `command()`/`wakeOutcome()` take the registry Vehicle and still call `slotFor("command")`; its `stopCharging` still tests `slotFor("command") is not None`.
Failure scenario: rebasing this onto 3.5 by resolving text conflicts leaves `commandSigning` never recorded (no `__init__`), so every car is read-only on an Owner token and the feature silently vanishes while the (auto-merged) gate tests fail on `api.carApiVehicles`.
Fix: port, don't merge. On 3.5: read `command_signing` into `CarApiState` in `addVehicle`, make the `OwnerAPI` claim `lambda: ownerCommandsAllowed(state)`, make `readOnly`/`_signingState` iterate `registry.attached("TeslaAPI")`, route `command`/`wakeOutcome`/`stopCharging` through `commandSlotFor`. Correct the PR note.

### 2. CONFIRMED (medium, log): wrong reason in the per-car read-only line when the Owner token itself is command-refused
`refuseCommandFor` (TeslaAPI.py:1335-1376) picks `why` from `commandSigning` only. If the Owner slot has "command" in `refusedPurposes` (412 on an owner command, TeslaAPI.py:412-421; or an expired token whose refresh failed, 371-384) a car listed `"off"` is read-only, and the line says: "Tesla reports command_signing: off for it, a value TWCManager does not know, so it is treated as read-only." Reproduced in scratch_659_edges.py::test_per_car_line_when_owner_token_is_command_refused.
Fix: add a branch before the signing switch: `elif "command" in self.ownerSlot.refusedPurposes: why = "Tesla refused commands with the Owner API token (HTTP 412 or an expired token that could not be refreshed)."` and include that flag in `refusalState` so the line re-logs when it changes.

### 3. PLAUSIBLE (low): an HTTP 200 whose body carries the VCP error is not latched and gets the blind retry
`_classify` returns `None` for status 200 before the owner check (TeslaAPI.py:352-353, 394-397), so a body like `{"response": null, "error": "Tesla Vehicle Command Protocol required..."}` on 200 reaches `_paidPost`, raises `TypeError` (1465-1468) and comes back `Outcome(ERROR, "TypeError")`, which is RETRYABLE. Traced live in scratch: 2 owner POSTs per desire, no latch, no backoff. Main's `noteOwnerCommandRefused(vehicle, req)` is called on the parsed response in every command path regardless of status (the 403-or-text test lives inside the helper; verified in wt-main's car_api_charge, setChargeRate and wakeVehicle hunks), so main latches on this body and phase3 does not: a CONFIRMED parity divergence, but the triggering response is only plausible since the brief's live evidence shows 403 for this error. Cost is zero (owner); the car just never latches and the walk keeps retrying within its budget.
Fix: in `_paidPost`, when the parsed body has a string `error` and `slot is self.ownerSlot`, call `noteOwnerCommandRefused(vehicle, 200, req.text)` before the TypeError return.

### 4. PLAUSIBLE (low): a free Owner 403 spends the desire's first paid send, delaying fall-through to the next paid provider
`_SIGNING_REQUIRED` has detail "signing required", not in `NOT_SENT` (Outcome.py:48-63), so `noteOutcome` counts it as a sent paid request: `paidSends=1`, `paidReached=True`, `paidRetryDue=False` (Desired.py:343-352). With Owner + HomeAssistant and no BLE, the first HA send waits RETRY (300 s for a limit) plus a reading that reached the car, or a new desired value. The implementer states this; `test_403_falls_through` pins it as "as a Fleet 403 does". It is a one-time cost per car (the latch is permanent), so acceptable; noting because the request cost nothing and no car state was touched.
Fix (optional): add "signing required" to `NOT_SENT` so the fallback is immediate; then the wake path's `_tagged` keeps the detail untagged too.

### 5. PLAUSIBLE (low): any Owner 403 on a command or wake latches the car permanently, whatever the body
`noteOwnerCommandRefused` (1377-1402) latches on `status == 403` alone. An unrelated 403 (account lock, Tesla-side rate refusal) marks the car read-only until restart with a WARNING that blames signing. Plan decision 6 accepted "403 and/or text", so this is design, not defect. Latch lifetime verified: `carApiVehicles` is only ever the class default (TeslaAPI.py:144), never rebuilt at runtime, so "until restart" in the docs is accurate.

## Checklist answers

1. Price 0 in the billed tier. Nothing reads `Cost.price` (grep: only its definition, Capability.py:47). Selection uses tier only (`_tier`, Reconciler.py:92-95; `Order._key` Order.py:49 sorts (tier, rank, index)). OwnerAPI rank 4 sorts before FleetAPI rank 5 inside the billed tier, but `OwnerAPIProvider.available(COMMAND)` requires `ownerTokenOnly` (= no usable Fleet command slot) so both are never in one walk. Reporter's setup (owner token, no BLE, no Fleet, "off" car): `free` is empty so `freeFailed = not free` is True on the first pass and `paidAgain` holds (Reconciler.py:313-318, 341-345). CONFIRMED by scratch_659_parity.py: limit, amps and start each POST on pass 0 with identical attempt shape (wake, maxAge 600/None/360, force) and identical paid accounting (1, True, False) for owner-only vs Fleet-only; with a failing BLE both wait PAID_AFTER and send on the same pass (300 s). No `PAID_AFTER` wait on a non-existent free provider.

2. Method move. Fleet-only and Fleet+owner walks: `commandSlotFor` returns the Fleet slot whenever `fleetSlot.usable("command")` (TeslaAPI.py:494-503); `OwnerAPIProvider.available(COMMAND)` is False then, so OwnerAPI is not in `ordered()`; `command()`/`wakeOutcome()` refuse a provider whose slot is not the chosen one (1421-1424, 1500-1503), so FleetAPIProvider cannot send with the owner token nor vice versa. Budget key is `attempt.provider` = "FleetAPI" and cost `FLEET_COMMAND`/`FLEET_WAKE`, both unchanged; `report()` logs the provider name unchanged. One intended behaviour change: a Fleet token lacking command scope (or 403/412-retired) now lets an Owner token command "off" cars (`test_fleet_token_without_command_scope_leaves_owner`); decision 3 wording covers it. `clock`/`ampsRange` moved to the base class; tests set `clock` on instances, fine. Owner now has `ampsRange`, so the amps-range filter applies to it as to Fleet.

3. URL shape. `_request` builds `slot.baseURL[:-len("vehicles")] + path` (TeslaAPI.py:313-315) with `_paidPost` path `vehicles/<VIN>/<command/name | wake_up>` (1455-1462): `https://owner-api.teslamotors.com/api/1/vehicles/<VIN>/command/set_charge_limit`. Owner reads already use `vehicles/<VIN>` (is_awake, 1876-1878) and `vehicles/<VIN>/vehicle_data?...` (2011-2016) against the same base, and TeslaMate-token users read that way in production today. Same shape, CONFIRMED by the test URLs.

4. 403 with non-JSON/empty body. `noteOwnerCommandRefused` wraps `json.loads` in `(ValueError, AttributeError, TypeError)` and latches on status alone. Reproduced for "", HTML, "null", "[1,2]", `{"error":5}` on commands and "" on wake: one POST, latched, `getCarApiLastErrorTime()==0`, `lastErrorTime==0`, `paidRetryDue False`. The owner check sits before the generic 403/412/429 branches (394-397), so no `slot.refuse`, no `reportScopeRefused`, no `updateCarApiLastErrorTime`. CONFIRMED.

5. Owner wake 403 → REFUSED. Flow: `wakeOutcome` returns `_SIGNING_REQUIRED` (1538-1539) → `Run._wake` tags "wake signing required" and ends the attempt (Run.py:117-119) → `noteOutcome` excludes OwnerAPI for the record and spends one paid send; `lastSentAt` is not stamped (EXCLUDING). Afterwards `ownerCommandsAllowed` is False → `ready` False and `commandSlotFor` None → no more wakes or commands for that car (scratch: 1 POST over 1200 s). `_limitSpent`'s `all([])` is True once no provider is able, so a held start is not stuck. Safe. CONFIRMED.

6. readOnly / noteReadOnly / template. Owner-only: `noteReadOnly` returns early when `ownerTokenHeld()`, per-car lines come from `refuseCommandFor` keyed on `(fleetSlot.changes, commandSigning, ownerCommandsRefused)`; `test_required_car_is_named_once` pins one line per 6 ready() calls. Mixed: Fleet usable → `readOnly` False, `OwnerAPI.ready` never reaches `refuseCommandFor` (`test_no_per_car_hint_while_fleet_commands`). Fleet-only/no token: module line keyed on `(fleetSlot.changes, _signingState())`. `fleetSlot.changes` increments on every token refresh (~7 h), so the hint can re-log then; pre-existing behaviour. No per-poll spam found. Template reads `ownerTokenOnly` (handle_teslalogin.html.j2:6); the else branch (Fleet) still says "you also need the proxy", correct. Only wording defect is finding 2.

7. Tests. Assertions match claims. `TestThroughTheWalk` uses `test_limit_reconciler.setup` (real `VehicleReconciler` + `ProviderOrder`, inline submit) with the real TeslaAPI providers and a scripted fallback, so the walk is real. Gaps: no non-JSON 403 body case (covered by my scratch, passes); no test of finding 2's path; `test_403_falls_through` documents rather than questions the spent paid send.

8. Overlap with phase3.5: see finding 1.

## Adversarial pass, no defect
- 412 on an owner command retires the whole owner slot for commands (412 branch is slot-wide). Consistent with the Fleet semantics ("Tesla will keep refusing"); a TeslaMate resync resets `refusedPurposes` so it is re-tried once per sync. Pre-existing pattern.
- Read pause on the owner slot does not block owner commands (decision 2). With no Fleet read slot, the wake's online check fails and the attempt ends "wake online check failed" (NOT_SENT), so no blind billed-tier send. Same as Fleet.
- `command()`'s `slot not in (None, chosen)` relies on identity for `TeslaTokenSlot` (no `__eq__`); correct.
- Debug page `debugCommand("wakeVehicle")` picks OwnerAPI for an "off" car and goes through `wakeOutcome` with the owner slot; `test_debug_interface_resolves_by_vin` updated accordingly.
- `ble_only` suppression (CLOUD_SUPPRESSED) applies to OwnerAPI commands as to Fleet.
- Docs: Vehicle_TeslaAPI.md statements about ordering ("after TeslaBLE has failed for a while", "never to set a car's charge rate where a TWC or BLE can") match the reconciler and `localRule`. "until it restarts" is accurate (finding 5).
