# X3 report: fold FieldStore into Vehicle

Status: DONE. Commit: see `git log -1` on vehicle-model/phase5 (message "Keep a vehicle's fields on the vehicle").

## What changed
- `Fields.py`: `FieldStore` removed; `Observation`, `FIELDS`, constants, `NOT_TRACKED` kept.
- `Vehicle.py`: owns `_latest`, `_writes`, `_bySource` and `_fieldLock`; `_store` (the old `FieldStore._store` with the FIELDS check); `latest/reported/lastWrite/snapshot` read the tables directly; `trusted` and `age` computed in place (`_ageOf` shared with `summary`); `noteWrite` takes optional `at`.
- `VehicleRegistry.py`: anonymous merge uses `anon.snapshot()`.

## Lock layout
Before: `Vehicle._lock` (claims/attachments/marks/lastSeen) and a separate `FieldStore._lock` (non-reentrant leaf).
After: same two locks; the field one is `Vehicle._fieldLock`. Same work under it: the stamp clock read plus table update in `_store`; single table reads for latest/reported/lastWrite/snapshot. `trusted` reads `lastWrite` (one short hold) after `_liveAt` and `clock()`, as before. Neither lock is held across the other or across any call into the registry; `observe`'s hook still runs outside both; `_liveAt` (registry call) still runs with no lock held.

## Tests rewritten
tests/unit/test_registry_fields.py: `FieldStore(...)` replaced by a Vehicle built via `mk()` (stub registry giving per-source liveAt). Every assertion is kept verbatim. The `liveAt=` keyword arguments became `registry.live[source]` settings (same values). `test_clock_read_inside_lock` now checks `_fieldLock` is held at the stamp read; Vehicle.observe makes later unrelated clock calls, so it asserts the first call and uses `seen=False`, and noteWrite asserts `[True]`. test_registry_read_cascade.py: `_fields._lock` -> `_fieldLock`.

## Tests
tests/unit + tests/EMS: 2035 passed, 1 warning (baseline equal). black run on touched files.

## Lib delta
`git diff --shortstat 5782c78c -- lib`: 3 files, 96 insertions, 158 deletions = net -62 lines (estimate -35; beat it).

## Concerns
- `age()` now uses the single latest observation it already fetched rather than re-reading it (removes a race window only).
- Advisor not consulted: the lock layout is unchanged, only relocated.

## Fix round 1
- Removed the test-only `at` from `Vehicle.noteWrite`; the older-write test now sets stamps through `Clock` (950, then 900, then 950), assertions unchanged.
- `test_clock_read_inside_lock` uses `seen=False` and asserts `held == [True, False]`.
- Commit body states the age/summary single-read change.
- tests/unit + tests/EMS: see run below, 2035 passed.
