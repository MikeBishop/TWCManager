# Task 1 report: held limits migrate in one pass

Status: DONE

## Commits (worktree wt-vm35, branch vehicle-model/phase3.5, BASE db47522)

- `c518644` Migrate held limits in one pass; chargeLimits is the waiting list

## Tests

- Step 3 (BASE lib, new and retargeted tests): `test_held_limits.py test_limit_wiring.py test_vehicles_page.py`: 73 passed.
- After implementation, the same three files: 73 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **1769 passed, 1 xfailed** (baseline 1764 + 5 new). The "1 warning" is the existing urllib3 InsecureRequestWarning in test_enphase_ems and is unrelated.
- Greps: `-w _waiting|vins` in HeldLimits/TeslaAPI/TWCMaster finds only TeslaAPI's local variable `vins` in the Wall Connector VIN lookup (unrelated). `heldLimits.(vins|_waiting)` in lib: 0. `"id:` in lib: 0.

## Lib delta

27,270 -> 27,225 (**-45**, brief expected about -48).

## Implementation notes

- `_migrate` follows the brief's code and check order exactly. Two layout changes keep the line count down under black:
  - The five log formats are module constants (`_MALFORMED`, `_UNHELD`, `_UNLISTED`, `_COLLIDED`, `_MERGED`), with text unchanged.
  - Warnings and infos are collected as arg tuples and logged after the lock is released: warnings first, then infos, as the brief allows.
- `_snapshot` is inlined into `holding()`. I did not use a walrus because `python_requires >= 3.6` and lib has no `:=` anywhere.
- The comment that named `vins()` (in `set`) now names `holding()`.
- I ran `black` on HeldLimits.py and test_held_limits.py. Black also reformatted a few existing lines in test_held_limits.py (blank lines, wrapping). These are cosmetic.
- I did not run `black` on test_limit_wiring.py. It was not black-clean at BASE (`black --check` exits 1 on db47522), and black would rewrite the whole file for a 2-line fixture change.

## Deleted / rewritten test map

- `test_limit_wiring.py::test_legacy_ids_resolve_once_from_the_first_vehicle_list`: plumbing only. The fixture moves the unmatched entry from the dev-build store key `"id:44": {"outside": 75, ...}` to `chargeLimits["44"]: 75`, which lib no longer reads from the store. The l.99 expected chargeLimits gains `"44": 75` (F4). All other assertions are unchanged: one warning naming 44 and 75%, the final heldLimits, 1+1 list GETs, and the M5 info line.
- `test_held_limits.py::test_realistic_settings_file_migrates`: plumbing only. `vins()` became `sorted(m.settings["heldLimits"])`. Every entry is well formed, as the preceding `held ==` assertion proves.
- `test_held_limits.py::test_no_legacy_key_no_save`: plumbing only. `vins() == []` became `holding() == []`. Both follow from `"heldLimits" not in m.settings`, which the same line asserts.
- `test_held_limits.py::test_store_works_before_load_and_on_a_bare_master`: plumbing only. The `vins() == []` term is dropped; `get` and `holding` remain.
- No test was deleted.

New characterization tests (they pass at BASE and after):
- `test_waiting_is_false_before_load`
- `test_an_id_naming_a_vin_load_migrated_keeps_that_entry`
- `test_an_id_keys_out_of_range_hold_warns_at_load_not_at_resolve`
- `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load`
- `test_a_resolve_saves_once_and_logs_no_migrated_line`

## Self-review

- **Lock:** the whole read-modify-write runs under `settingsLock`. That covers the legacy and store reads, the loop, the writes to `heldLimits` and `chargeLimits`, and `_loadedVins`. Logging and `_save()` happen after release. No I/O happens under the lock.
- **Race:** `waiting()` is checked without the lock. `_migrate` re-reads `chargeLimits` under the lock, so a second concurrent resolve finds it gone (not a dict) and returns without saving. This matches BASE, where `_waiting` was swapped under the lock.
- **Saves:**
  - load saves when `keep != legacy`, the same as BASE `ids != legacy`.
  - At resolve, every ID is either moved or dropped, so `keep == {}` against a non-empty legacy and the save always runs. BASE always saved here.
  - A repeated load and a restart from the migrated file do not save. `test_migration_is_idempotent_and_a_rerun_loses_nothing` covers both and still passes.
- **F9:** `waiting()` requires `_loadedVins is not None`, a dict, and a non-empty value.
- **Semantics (a)/(b):** the TeslaAPI side (`listPending`, `loadList`, `resolveHeldLimits`) is untouched. The Review Focus tests are unchanged in assertion and pass.
- **INTENTIONALLY CHANGED (F10, accepted, not pinned):** two numeric IDs name one VIN whose store entry was loaded malformed. The second ID now merges as `(limit2.outside, own.held)`, where BASE kept the first ID's value.
- **Log order:** within one pass, all warnings come first, then the infos. BASE grouped dropped, unheld, collided, then infos. No test depends on the order.
- **Theoretical difference:** BASE resolved from the in-memory snapshot taken at load. The new code reads the current `chargeLimits` at resolve. Nothing writes `chargeLimits` except the settings file, and a `loadSettings` re-runs `load()`, so the result is the same.

## Concerns

None blocking. Lib delta is -45 against a projected -48. The 3 lines go to the extra `vinsNow` local and the log-format constants, which keep the code readable under black.

## Fix round 1

Commit: `b44ea1e`

- HeldLimits.py: dropped the `vinsNow` local. `loaded` now uses the brief's inline `frozenset(...)` in the not-final branch, so a resolve no longer computes it.
- `holding()`: `if limit and ...` became `limit is not None and ...`.
- New test `test_a_non_dict_charge_limits_never_waits` (pins F9): after `load()` with `chargeLimits` set to a list, `waiting()` is False and the value is left as it was.
- Full suite: **1770 passed, 1 xfailed** (the 1 warning is the existing urllib3 one in test_enphase_ems).
- Lib count: 27,230 (−40 from BASE 27,270). black needs 5 more lines for the inline form and the `is not None` wrap.
