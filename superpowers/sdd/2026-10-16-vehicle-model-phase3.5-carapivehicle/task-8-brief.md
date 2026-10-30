# Task 8: Keep `chargeLimits`; drop the `heldLimits` rename

## Decision (user, 2026-10-17)
The rename `chargeLimits` → `heldLimits` (introduced in Phase 3) was change for change's sake: main stores
`chargeLimits[str(ID)] = (outside, lastApplied)` tuples (TWCMaster.saveNormalChargeLimit), keyed by the Tesla API's
numeric vehicle ID (TeslaAPI path) or by VIN (TeslaBLE path). The only substantive change the rework needs is keying by VIN.
So: keep the settings key `chargeLimits` and main's tuple shape, keyed by VIN.

## Format (binding)
- `settings["chargeLimits"] = {VIN: [outside, held]}` — a 2-element list/tuple as main writes it (json round-trips tuples as
  lists). Read leniently as main does (`getNormalChargeLimit`): a bare int `n` means `(n, 0)`; None elements read as 0.
- **Absence is the "not overriding" state.** On main, TeslaAPI wrote `(outside, -1)` after restoring or after seeing a manual
  change (TeslaAPI.py ~1204 on origin/main), while TeslaBLE removed the entry instead (TeslaBLE.py ~750). In the rework, when
  nothing is held the entry is REMOVED — unless you find a reader at the 3.5 tip that genuinely needs the outside value with
  nothing held (then report it, keep `held` as `-1` on disk for main compatibility, and explain why). Reading: `-1`, `0` and
  None in the held slot all mean "nothing held" (main's files contain all three).
- Numeric-ID keys (from 1.3.x installs) are re-keyed to the VIN in place when a vehicle list names them, with the existing
  user-decided semantics: unmatched IDs are dropped with one warning only after every usable token slot's list came back
  non-empty; a VIN already present wins over a re-keyed ID except as main would merge (keep current behaviour: later-added
  VINs merge as (legacy.outside, store.held) — re-express it for the single key).
- No `heldLimits` key anywhere in lib, docs, CHANGELOG or tests. No code path for converting `heldLimits` (it only ever
  existed on development builds; the controller converts the one live box by hand).

## Where
Make the change on `vehicle-model/phase3` (tip 3fcae411) as new commit(s), so Phase 3 never introduces the rename. Then
rebase `vehicle-model/phase3.5` (tip 54059990) onto the new phase3 tip and resolve conflicts (Phase 3.5 Task 1 rewrote
HeldLimits.py into a one-pass `_migrate`; keep its structure, adapted to one key; drop 54059990's rename rationale lines —
CHANGELOG and the HeldLimits.py header — since there's no rename now). Class/module names (`HeldLimits`, `HeldLimit`,
`Reconcile/HeldLimits.py`) may stay — they describe the concept, not the settings key — unless renaming saves lines.
CHANGELOG: replace the migration line with an accurate one (e.g. "Held charge limits in settings `chargeLimits` are keyed by
VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them" plus the downgrade
note: a 1.3.x build still reads VIN-keyed entries; re-keyed TeslaAPI entries won't match there).

## Tests
- Rewrite the HeldLimits/limit-wiring tests to the single key; map every rewritten/deleted test.
- Pin: a 1.3.x settings file with `(80, -1)`, `(80, 50)`, `80`, `(80, None)`, numeric-ID and VIN keys loads correctly; a held
  limit persists as `[outside, held]` under the VIN; restoring removes the entry; restart persistence.
- test_command_path_parity.py counts unchanged.
- Each phase3 commit and the phase3.5 tip green.

## Constraints
- Lib must shrink or stay flat versus the current tips (phase3 27,303; phase3.5 27,407-ish — measure). Report deltas.
- Lock order _bleLock -> settingsLock -> registry leaf; vehicleListLock -> settingsLock; no I/O under locks.
- Local branches only; the controller force-pushes. Never touch other branches, the main checkout's branch, or the box.
