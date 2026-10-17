# Task 5: Port #659 (Owner API commands for cars with command_signing off) onto Phase 3.5

## Context
Issue ngardiner/TWCManager#659. A peer session built the feature on `vehicle-model/phase3` (db47522) as local branch
`vehicle-model/phase3-owner-commands`: 2ef5ba3, f0a7b4b, 3a3c4ff, 72439ec, 3489e93 (in the main repo ~/github/TWCManager;
the same objects are visible from the wt-vm35 worktree). It conflicts with Phase 3.5, which dissolved `CarApiVehicle`
(7d946ab): `CarApiVehicle.__init__`, `carApiVehicles` and `getVehicleByVIN` no longer exist. This is a PORT, not a merge:
resolving text conflicts alone leaves `command_signing` never recorded and the feature silently disappears.

Reference material (same directory as this brief):
- `659-reference.diff` — full db47522..3489e93 diff (lib, tests, docs, templates).
- `659-reference-review.md` — the peer's independent review, findings 1–5 and checklist.

## Requirements
Reproduce the reference branch's behaviour on top of HEAD 6c4ba54, adapted to the 3.5 structure:
1. `addVehicle` reads `command_signing` from the `/products` (vehicle list) entry into `CarApiState`, together with the
   `ownerCommandsRefused` latch and `refusalLoggedAt`. No separate per-car map.
2. The OwnerAPI keep-alive/claim in `addVehicle` becomes `lambda: ownerCommandsAllowed(state)` (or equivalent) instead of
   a constant False.
3. `readOnly` and `_signingState` iterate `registry.attached("TeslaAPI")` pairs.
4. `TeslaAPI.commandSlotFor(vehicle)` is the single slot chooser (Fleet first; the Owner slot only for
   `command_signing == "off"` and not latched/retired), used by `command()`, `wakeOutcome()` and `stopCharging`.
5. Command methods move from `FleetAPIProvider` to the shared base in `Providers/TeslaAPIProviders.py`; `OwnerAPIProvider`
   declares the commands. New `OWNER_COMMAND` capability (billed tier, price 0) in `Capability.py`.
6. `_classify`: an Owner 403 or VCP-error text latches that car; Owner 410 / 412 / "only available on fleetapi" refuse
   commands for the whole owner slot. Neither starts the error backoff.
7. Commit 3489e93 is KEPT (user decision 2026-10-16): "signing required" and "owner commands retired" join `NOT_SENT`, and the
   H2 hold in `Reconciler.plan` skips EXCLUDING outcomes.
8. Docs, CHANGELOG, `handle_teslalogin.html.j2` / `request_teslalogin.html.j2`, `VehicleEndpoint.py`, `TeslaTokenSlot.py`
   changes from the reference carry over (adjust wording if 3.5 changed the surrounding text).
9. Port the reference's tests (notably `test_teslaapi_readonly_gate.py` additions, `test_limit_reconciler.py`,
   `test_provider_tables.py`, providers/slots/classification/refresh tests) onto 3.5 test plumbing
   (`tests/unit/teslatokens.py`, the renamed registry test file). Tests that used `api.carApiVehicles` use
   `registry.attached("TeslaAPI")`.

Also fix from the peer review:
- Finding 2: the per-car read-only line must name the right reason when the Owner slot itself has "command" in
  `refusedPurposes` (412 or failed refresh); include that flag in the re-log key. Test it.
- Finding 3: a 200 whose parsed body carries a string `error` on the owner slot calls the owner-refusal note (latch) before
  the TypeError path, matching main. Test it.
Finding 5 (latch on any Owner 403) is accepted design — no change.

## Constraints
- No change for Fleet-only, BLE, HA or Gen3 paths beyond the reference's stated intended changes (Fleet token lacking
  command scope lets an Owner token command "off" cars; faster handover after an Owner refusal). The existing
  test_command_path_parity.py (31 rows) must keep its paid counts; add a row/test for owner-only "off" car parity with
  Fleet-only if the reference's scratch parity is not already covered.
- No new paid Fleet calls. Lock order _bleLock -> settingsLock -> registry leaf; vehicleListLock -> settingsLock; no new
  I/O under locks. No log line may contain a token.
- This is a feature, so lib grows; keep it as small as the reference or smaller (reference lib net: +267). Report the
  delta and do not duplicate code the 3.5 structure already provides.
- Map every deleted or rewritten test.
</content>
</invoke>
