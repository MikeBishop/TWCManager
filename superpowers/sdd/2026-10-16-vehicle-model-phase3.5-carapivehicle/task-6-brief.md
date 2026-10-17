# Task 6: Owner and Fleet commands follow the provider order (drop Fleet-first)

## Decision (user, 2026-10-16)
On Phase 3.5 only, a command goes to the first provider in the order that can handle it. OwnerAPI (rank 4) already sorts
before FleetAPI (rank 5) in the same tier. Today two gates override that, carried from the conservative 1.3.4 fix:
- `OwnerAPIProvider.available()` (Providers/TeslaAPIProviders.py) disables Owner commands while a Fleet token can command
  (`ownerTokenOnly`).
- `TeslaAPI.commandSlotFor()` (TeslaAPI.py ~508) returns the Fleet slot first.
Remove both. Each provider answers only for its own slot.

## Required behaviour
1. OwnerAPI is ready for a command/wake on a vehicle iff the car is listed, `ownerCommandsAllowed(car)` (command_signing
   exactly "off", not latched) and the Owner slot is not refused for "command" — whether or not a Fleet token exists.
2. FleetAPI is ready for a command/wake iff the Fleet slot is usable for "command" (unchanged).
3. `command()`, `wakeOutcome()` and `stopCharging` send with the slot of the provider making the attempt (the Owner provider
   uses the Owner slot, the Fleet provider the Fleet slot); a provider never sends with the other's token. Replace
   `commandSlotFor` with whatever is smallest (e.g. a per-provider slot + a per-car `ownerCommandsAllowed` check); delete
   code that only served Fleet-first.
4. With both tokens and an "off" car: commands go to Owner; on an Owner refusal (403/VCP/410/412/"only available on
   fleetapi") the car (or Owner slot) is latched/refused and, because those details are NOT_SENT and EXCLUDING (3489e93),
   FleetAPI sends on the next pass with no RETRY wait. Test this end to end through the real reconciler walk.
5. With both tokens and a "required"/missing/unknown car: Fleet only, zero Owner command calls (unchanged).
6. Read-only hints (`readOnly`, `noteReadOnly`, `refuseCommandFor`, template `ownerTokenOnly`) keep their user-facing
   meaning: a car is read-only only when no provider can command it. Don't log a per-car "read-only" line for a car Fleet
   can command. Adjust `ownerTokenOnly` usage only where it encoded Fleet-first.
7. Paid counts: test_command_path_parity.py existing rows unchanged except any row with both tokens and an "off" car, which
   must now show 0 Fleet commands/wakes (mark such row changes INTENTIONALLY CHANGED). Add a row: both tokens, "off" car,
   raise + start: Owner requests only, $0.

## Constraints
- Phase 3.5 branch only. Do not touch main, release/1.3.4, #701/#702 branches, or the box.
- Lib must not grow; expected small negative delta.
- Lock order and no-I/O-under-lock rules unchanged; no token in logs.
- Map every deleted or rewritten test (several test_teslaapi_readonly_gate.py cases assert Fleet-first; rewrite them as
  INTENTIONALLY CHANGED with the new expectation).
- Update docs/modules/Vehicle_TeslaAPI.md and the CHANGELOG #659 line where they say Fleet is preferred.
