# Task 8 report: keep `chargeLimits`, drop the `heldLimits` rename

Status: DONE. One deliberate deviation from the brief's default: nothing held is stored as `[outside, -1]`, not removed. The brief's own exception allows this; the reasons are below.

## Commits

### vehicle-model/phase3 (was 3fcae411, new tip **7ff8d9ae**)
- `8f88ae31` Keep held limits in chargeLimits, keyed by VIN. Lib, tests, and the CHANGELOG migration line.
- `7ff8d9ae` Say that only a charge limit set in the car is adopted. This is the CHANGELOG fix the coordinator added mid-task.

### vehicle-model/phase3.5 (was 54059990, new tip **ab6df576**)
I rebased it with `git rebase --onto 7ff8d9ae 3fcae411`, then ran a non-interactive reword pass. The tree did not change.
- `dee7c52f` became `3380ae70` "Pin the one-pass held-limit migration's edge cases". It is tests only now: phase3 already has the one-pass `_migrate`, because with a single key the natural code *is* the one pass. Four of its five characterization tests are kept, adapted (see the test map).
- `6e810e46` became `b89a4606` "Pin that a non-dict chargeLimits never waits". Tests only. Its lib half (inline `loaded`, `is not None`) is subsumed.
- `97916c49` became `5e43c7f8`. In its CHANGELOG hunk, the rewording of the rename line was dropped, because that line no longer exists.
- `ca9fcbc9` became `4d545833`. The `_vins` helper hunk was dropped (the new code computes the VIN set once). I removed the sentence "HeldLimits shares its VIN-set helper." from its message.
- `54059990` "Say why held limits moved to a new settings key" was **skipped**. It became empty: there is no rename to explain.
- The other 3.5 commits replayed cleanly.
- The 3.5 commit list therefore has 19 commits above phase3, not 20.

## Tests
- phase3 tip (the same tree as 8f88ae31 apart from the CHANGELOG line): **1781 passed, 1 xfailed**. The baseline was 1783; 2 tests were deleted, both of whose scenarios need two keys.
- phase3.5 tip: **1866 passed, 1 xfailed**. The baseline was 1869; 3 tests deleted: the same 2, plus 3.5's `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load`.
- The one warning is the existing urllib3 one.
- I only ran the full suite at the two tips. At the two stops where `HeldLimits.py` conflicted and tests were added (`dee7c52f` and `6e810e46`), I also ran `test_held_limits.py` and `test_limit_wiring.py`. At the `ca9fcbc9` stop I took the phase3 file and continued without running tests.
- `test_command_path_parity.py` was not touched. Its counts are unchanged, and its `HeldLimit(80, None)` assertion still holds.

## Lib line counts
- phase3: 27,303 → **27,241 (−62)**
- phase3.5: 27,407 → **27,386 (−21)**. Task 1 had already shrunk the two-key one-pass, so less is left to take here.

## On-disk format (exact)
`settings["chargeLimits"] = {VIN: [outside, held]}`
- `held` is an int from 50 to 100 while TWCManager holds a limit.
- `held` is `-1` when nothing is held. Writes are lists. Main writes tuples, and json turns those into lists anyway.

Reads are lenient, as main's `getNormalChargeLimit` is:
- A bare int `n` is `(n, nothing held)`.
- A held value of `-1`, `0` or `None` means nothing held.
- An integral float is read as an int.
- An out-of-range held value keeps the outside limit and holds nothing. It is warned about, and normalised to `[outside, -1]` at load.
- An entry whose outside value is unusable is dropped at load, with a warning.

`HeldLimits.set(vin, outside, None | 0 | -1)` writes `[outside, -1]`. `remove()` deletes the entry. The only caller of `remove()` is the reconciler's c6 path: a restore that is already satisfied.

`load()` does the following:
- It upper-cases VIN keys. If two keys differ only in case, it warns and keeps the later one.
- It drops malformed entries and normalises out-of-range held values.
- It leaves numeric-ID keys in place: they wait, on disk where they were.
- It leaves well-formed 1.3.x entries untouched (`(80,-1)`, `(80,0)`, `(80,None)`, `80`). A clean 1.3.x file causes no save.

`resolveLegacyIds()` keeps the existing user-decided semantics, now on one key:
- An unlisted ID is dropped with one warning. The TeslaAPI side, which waits until every usable slot's list is non-empty, is unchanged.
- If the ID's VIN has no entry, the ID's entry moves to it as written.
- If the VIN was present when `load()` ended, that entry is kept and the ID's is discarded (an INFO line).
- If the VIN was recorded since load, it merges as `[ID.outside, own.held]` (an INFO line).

Other details:
- `waiting()` is a flag set by `_migrate`: true after `load()` while non-VIN keys remain, false before `load()` and for a non-dict value (F9).
- Lock use: dict work happens under `settingsLock` only. Logs and the save come after it is released.
- No `heldLimits` settings key remains anywhere in lib, docs, CHANGELOG or tests. The only `heldLimits` left is the `master.heldLimits` attribute.
- The `"id:"` handling, the `_waiting` dict copy, `_storedEntry`, `LEGACY_KEY`, `vins()`/`_snapshot` and the "Migrated chargeLimits to heldLimits" line are gone.

## Does any reader need the outside value with nothing held? Yes, one. That is why held is -1, not absent
`Rules.decideChargeLimit` has a branch for when the current limit is unknown and the provider sends anyway (`sendWhenUnknown=True`: free providers such as BLE). It records `HeldLimit(target if held is None else held.outside, target)`.

The 3.5 tip writes outside-with-nothing-held records on purpose, to feed that branch:
- Adoption: `Reconciler._save(vehicle, adopted, None)`.
- A settled restore: `saveNow HeldLimit(current, None)`.
- A sent restore: `saveOnSuccess HeldLimit(normal, None)`.

If those records were removed instead, this sequence loses the car's normal limit:
1. A restore completes.
2. The next blind apply records `(target, target)`.
3. The next restore sees the car at `target == outside`, which it treats as already restored.
4. The car stays at the policy limit.

That is main's TeslaBLE bug: main removed the entry on restore. It would be a regression against the 3.5 tip. No rules test pins `(unknown current, held=(x, None))`.

So, following the brief's exception, nothing held is kept on disk as `[outside, -1]`, which is also main's TeslaAPI form.

Secondary readers:
- `HTTPControl.heldLimitText` shows "N% (restored)". This is cosmetic.
- `Targets` / `_restoreDeparted` / `_present` read only `holding()`, which lists held entries. They don't care either way.

Caveat: the 3.5 tip's c6 path (`Reconciler.plan`, a satisfied restore) already calls `remove()`. That path has the same exposure today, so the protection is not complete. I left it alone because it is out of scope.

Downgrade compatibility:
- A 1.3.x TeslaAPI reads `(outside, -1)` as "was at home, not overriding". It detects the departure on its next pass and removes the entry. This is benign.
- A 1.3.x TeslaBLE reads `has_saved` and restores to `outside`. This is also benign.

## Test map
phase3 (`8f88ae31`):
- `test_held_limits.py`:
  - `test_legacy_charge_limits_migrate`: rewritten to one key. VIN keys normalise in place, the ID re-keys, and `holding()` is unchanged.
  - `test_set_and_remove`: rewritten. It now pins `[80, 50]`, then `[80, -1]` for nothing held, then removal.
  - `legacySettings()`: gains a `VIN4: 85` bare-int VIN key.
  - `test_realistic_settings_file_migrates`: rewritten. Pins the 1.3.x file with `(80,-1)`, `(80,50)`, `80`, `(80,None)`, `(85,0)`, numeric-ID and VIN keys: the exact normalised dict, 4 warnings, `get()` for each car, `holding()`, `waiting()`.
  - `test_migration_is_idempotent_and_a_rerun_loses_nothing` and `test_crash_before_the_save_reruns_the_same_migration`: plumbing (key).
  - `test_saved_file_carries_the_store_and_restarts_clean`: rewritten. It pins the exact on-disk `chargeLimits` after a set held (`[80, 60]`) and a set nothing-held (`[90, -1]`). On restart it pins the values, `holding()`, no save, and a later re-key.
  - `test_an_existing_store_keeps_its_own_cars`: **deleted**. It needs two keys.
  - `test_both_keys_present_the_store_wins`: **deleted**. It needs two keys.
  - `test_no_legacy_key_no_save`: renamed `test_no_charge_limits_no_save`. Plumbing.
  - `test_migration_swaps_under_the_lock`: now watches the `chargeLimits` write, using a lower-case VIN so that load writes.
  - `test_resolving_keeps_an_existing_vin_entry`: fixture plumbing (the VIN entry is loaded from `chargeLimits`).
  - `test_resolving_replaces_a_malformed_vin_entry`: plumbing. The malformed VIN entry is inserted after load.
  - `test_store_works_before_load_and_on_a_bare_master`: plumbing; also asserts that `waiting()` is False.
  - `test_store_never_keeps_the_sentinel`: became `test_nothing_held_is_stored_as_minus_one`. **Assertion changed**: held -1, 0 and None all store `[80, -1]`.
  - `test_out_of_range_held_keeps_the_outside_limit`: adds the on-disk normalisation to `[80, -1]`.
  - `test_integral_floats_round_trip_as_ints`: plumbing (list format).
  - `test_integral_floats_migrate`: became `test_integral_floats_read_as_ints`. Asserts through `get()`.
  - `test_non_integral_floats_are_invalid`, `test_set_rounds_finite_numbers`, `test_listing_before_load_is_resolved_on_the_next_check` and `test_set_refuses_a_non_vin_and_maps_zero_to_none`: plumbing (key/format).
- `test_limit_wiring.py`:
  - `test_legacy_ids_resolve_once_from_the_first_vehicle_list`: fixture on one key. The unmatched `"44": 75` and `VIN4: [66, -1]` now live in `chargeLimits`. The expected final dict is `{VIN: [80,-1], VIN2: [90,50], VIN3: 85, VIN4: [66,-1]}`. One warning (44, 75%), the M5 info line, and 1+1 list GETs are unchanged.
  - `test_a_failed_second_list_defers_the_drop`: plumbing (`"11" in chargeLimits`, then `{VIN3: [90, 50]}`).
- `test_limit_reconciler.py`:
  - `test_adopted_float_is_saved_as_an_int`: on disk, `[80, -1]` with an int outside.
  - `test_no_wake_to_lower_wake_to_raise_never_for_a_restore`: **new pin**. After the restore, `chargeLimits == {VIN: [90, -1]}`.
- `test_vehicles_page.py::test_held_limit_reads_the_vin_store_after_adoption`: plumbing. It adds the ID entry instead of overwriting the dict.

phase3.5 rebase:
- `3380ae70` has four characterization tests: `test_waiting_is_false_before_load`, `test_an_id_naming_a_vin_load_migrated_keeps_that_entry`, `test_an_id_keys_out_of_range_hold_warns_at_load_not_at_resolve` and `test_a_resolve_saves_once_and_logs_no_migrated_line`.
  - One assertion was adapted: `"chargeLimits" not in settings` became `== {VIN: 70}`.
  - `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load` was **not carried over**. It needs two keys.
- `b89a4606` keeps `test_a_non_dict_charge_limits_never_waits` unchanged.

## CHANGELOG
- The migration line is now: "Held charge limits in settings `chargeLimits` are keyed by VIN; entries keyed by the Tesla API's numeric vehicle ID are re-keyed when the vehicle list names them. A 1.3.x build still reads the VIN-keyed entries after a downgrade; re-keyed Tesla API entries won't match there".
- Adoption, as the coordinator asked: "A limit or charge rate changed in the car or the Tesla app is adopted, not undone." became "A charge limit changed in the car or the Tesla app is adopted, not undone, until the next policy decision." `Desired.adopt` raises for any other aspect.
  - `docs/` has no such claim; I checked with a grep for adopt, "not undone" and "Tesla app".

## Concerns
- **The format decision (`-1`, not absence)** is mine, under the brief's exception. If the user prefers absence anyway, it is a small change: in `set()`, call `remove()` when held is None. The pins flip in `test_set_and_remove`, `test_nothing_held_is_stored_as_minus_one`, `test_saved_file...`, the reconciler restore pin and the adopted-float test. The cost is the blind-apply regression described above.
- The same CHANGELOG entry still ends "...and the -1 restore sentinel". I read that as the policy-level `-1` "restore" argument to `applyChargeLimit`, not the stored value, so I left it. Reword it if it reads as the on-disk -1.
- The 3.5 Task 1 commits now carry only tests: the one-pass logic moved down into phase3.

## Fix round 1 (redirected)

The user's decision replaced fix-round rulings 1, 3 and 4. A charge limit is never written while its current value is unknown, whatever the provider. I had made a first fix commit on phase3 (`2375a3e3`, which kept `[outside, -1]` in c6). I discarded it: phase3 was reset to `7ff8d9ae`, and the new commit was built on that.

### Commits
- phase3, new tip **`a678b9b5`**: "Never set a charge limit whose current value no source knows". It sits on `8f88ae31` and `7ff8d9ae`, which are unchanged.
- phase3.5, new tip **`6af811a1`**: 20 commits above phase3. Changes from the previous rebase:
  - "Pin the one-pass held-limit migration's edge cases" and "Pin that a non-dict chargeLimits never waits" were re-resolved (the fixtures are listed in the test map below).
  - **New** `b868eb96` "Count only registry callers in the atomic-Forget guard". `test_registry_callers.py::test_no_caller_outside_teslaapi_reaches_for_its_list` grepped for every `.forget(`. The master's new removal callback calls `DesiredStore.forget`, so the guard now matches `[rR]egistry\.forget\(` only. It still finds exactly one caller, HTTPControl's `forget(vin, ifUnattached=True)`.
  - **New** `6af811a1`: 3.5's `test_a_limit_raise_with_unknown_current_limit_logs_why_no_wake`, from commit 48b4ff9b, now gives BLE a read of 60. The planned limit is still unknown, and the read before the write finds one, so the "current limit unknown" no-wake line is still reachable and pinned.
  - **Not green:** the intermediate 3.5 commits from 48b4ff9b to the tip fail that test. Only the tip is green.

### What changed
- **Rules / Reconciler:**
  - `sendWhenUnknown` is removed.
  - The "current limit unknown" send and restore branches are removed.
  - An unknown current value now returns `(None, None, None, False, "could not read the current limit; nothing sent")` for every provider. The reconciler treats it as it always treated a paid provider: a rules UNREACHABLE (`unread` counter), retried later.
  - The value may come from any channel (`believed`, after the existing read step). For example, a TeslaMate reading lets BLE write.
- **HeldLimits:**
  - Holding nothing means there is no entry.
  - `set(vin, outside, None|0|-1)` calls `remove()`. Every "held None" save path therefore removes the entry: a restore (sent or settled), adoption, and a hand-set limit standing.
  - c6 already removed.
  - `get()` and `holding()` see only real holds.
  - `_entry()` returns a hold or None, plus the warning to log when dropping it. `_encode` is gone.
  - The header says absence means nothing held, and explains why that is safe now: a limit is only sent with the current value known, and that value is then the normal limit.
  - The `_loadedVins` reset is folded into one line (the nit).
- **What load() does to old entries:**

  | Entry | What happens | Warning? |
  |---|---|---|
  | Holds nothing: a bare int, or held `-1`, `0` or `None` | Dropped | No |
  | Held out of range | Dropped | Yes, "…its held limit is out of range" |
  | Malformed | Dropped | Yes |
  | Real hold (held 50–100), VIN key | Kept as written | No |
  | Real hold, numeric ID | Waits, as before | No |

  - The rules apply equally to numeric-ID keys: an ID holding nothing is dropped at load and never waits.
  - The settings are saved only if something changed. A clean 1.3.x file that has only real holds causes no save. This is pinned.
  - Re-key semantics are unchanged: a VIN present at load wins; one recorded since load merges `[ID.outside, own.held]`; an unlisted ID gets one warning.
- **Forget:** `TWCMaster._vehicleRemoved` is the registry's `removed` callback. It runs `desired.forget(key)` and `heldLimits.remove(key)`.
  - It covers the Vehicles-page Forget and the registry's 30-day expiry.
  - Anonymous plug-session ends also call it. They match no entry, so nothing is saved.
  - Before this, no Forget path dropped the entry.
- **HTTPControl.heldLimitText:** the "(restored)" branch is dead and is removed.
- **CHANGELOG:**
  - Line 24 now ends: "After a downgrade, only 1.3.x's TeslaBLE path reads the VIN-keyed entries; its Tesla API path, keyed by numeric ID, starts over".
  - Line 37 no longer mentions "the -1 restore sentinel".
  - New bugfix line: "A charge limit is only changed when its current value is known (from any source); TeslaBLE no longer sets a limit it could not read".

**Correction to the earlier report:** 1.3.x TeslaAPI never reads VIN-keyed entries; it looks up numeric IDs only. After a downgrade it starts over: it treats the car as newly arrived and writes new ID-keyed entries. Only 1.3.x TeslaBLE reads the VIN-keyed entries.

### Format (final)
- `settings["chargeLimits"] = {VIN: [outside, held]}`, with held 50–100, for each car TWCManager holds a limit on. There is no entry otherwise.
- Writes are lists.
- Reads are lenient. Old shapes that hold nothing are read as absent and dropped at load.

### Tests
- phase3 `a678b9b5`: **1778 passed, 1 xfailed** (before this round: 1781).
  - The rules table lost 7 unknown rows and gained 4: −6 tests counting `test_rules` and `test_invariants`.
  - +1 test for the clean file causing no save.
  - +2 wiring tests.
- phase3.5 `6af811a1`: **1863 passed, 1 xfailed** (before this round: 1866).

### Lib line counts
- phase3: **27,215**. That is −26 from 27,241 and −88 from the original 27,303.
- phase3.5: **27,360**. That is −26 from 27,386 and −47 from the original 27,407.

### Parity (`test_command_path_parity.py`)
- No row's command or paid-call counts changed.
- The one edit is `test_telemetry_limit_change_is_adopted`: the expected held value went from `HeldLimit(80, None)` to `None`, because an adopted limit holds nothing and so has no entry. Its `b.runs == 1` and `call_count == 0` assertions are unchanged.

### Test map (this round)
- `test_charge_limit_rules.py`:
  - The `sendWhenUnknown` column is gone.
  - **INTENTIONALLY CHANGED:** the four "unknown, BLE" rows sent blind (or settled). They are replaced by "unknown, apply / first apply / restore / restore, nothing saved", all `(None, None, None, False)`. The three "unknown, API" rows fold into these.
  - `test_held_values_are_clamped_to_50_100`: its blind-BLE clamp line is deleted.
- `test_limit_wiring.py`:
  - `test_rules_need_no_sentinel`: plumbing (8-column rows).
  - **New** `test_ble_never_sets_a_limit_it_cannot_read_but_another_channel_s_reading_will_do`. With no reading, BLE sends nothing over four hours of passes. After a TeslaMate reading, it sends 50 and records `[90, 50]`.
  - **New** `test_forgetting_a_vehicle_drops_its_held_limit`.
  - `test_legacy_ids_resolve_once_from_the_first_vehicle_list`: the fixtures now hold real limits, plus `"55": 80`, which pins that a nothing-held ID is dropped silently at load. The assertions are otherwise unchanged: one warning (44, 75%), the VIN4 info line, 1+1 GETs.
  - `test_an_unresolved_id_survives_a_restart`: fixture now `[80, 60]`.
  - `test_a_satisfied_restore_removes_the_held_record`: unchanged, and passes.
- `test_limit_reconciler.py`:
  - `test_app_set_limit_is_adopted_and_becomes_outside`: **INTENTIONALLY CHANGED**, adoption now leaves no entry (`get is None`). The later decision still records `(80, 50)`.
  - `test_adopted_float_is_saved_as_an_int`: adoption leaves no entry. The int pin moves to the following apply's `[80, 50]`.
  - `test_no_wake_to_lower_wake_to_raise_never_for_a_restore`: restored means no entry (round 0's `[90, -1]` pin is removed).
  - `test_restore_to_an_absent_car_retries_hourly_and_never_wakes`: **INTENTIONALLY CHANGED** fixture. It adds a TeslaMate reading, because a restore with no known limit now sends nothing.
  - `test_a_free_channel_that_cannot_reach_the_car_still_starts_the_paid_timer`: **INTENTIONALLY CHANGED**. The free provider now sends only with a TeslaMate reading. Its last line asserts that free also returns UNREACHABLE on an unknown limit; it used to assert that free sends.
  - `test_a_rules_settled_restore_clears_the_desire_and_does_not_loop`: a hand-set limit standing leaves no entry.
- `test_reconciler_queues.py`: plumbing. `reconciler()` seeds an hour-old TeslaMate `chargeLimit` of 90, so the runner tests' limit attempts still send, and still read first when given a maxAge.
- `test_held_limits.py`, rewritten to the absence rule:
  - `test_legacy_charge_limits_migrate`.
  - `test_set_and_remove`.
  - `test_realistic_settings_file_migrates`: the only survivors are `VIN2: [90,50]` and the waiting ID `[75,60]`. There are 4 warnings, all "Dropped"; 1 is out of range.
  - **new** `test_a_clean_file_holding_only_real_limits_is_not_saved`.
  - `test_saved_file_carries_the_store_and_restarts_clean`: a restore leaves no entry on disk.
  - `test_resolving_keeps_an_existing_vin_entry` and `test_resolving_replaces_a_malformed_vin_entry`: fixtures now hold real limits.
  - `test_nothing_held_is_stored_as_minus_one` is now `test_nothing_held_is_no_entry`.
  - `test_out_of_range_held_keeps_the_outside_limit` is now `test_out_of_range_held_is_dropped_with_a_warning`.
  - `test_invalid_outside_is_dropped`, `test_case_collision_warns_naming_both_keys`, `test_integral_floats_round_trip_as_ints`, `test_integral_floats_read_as_ints` (a bare int now reads as None), `test_non_integral_floats_are_invalid` (an invalid held value now drops the entry, with a warning), `test_set_refuses_what_is_not_a_finite_number`: fixtures and assertions follow the absence rule.
  - `test_set_refuses_a_non_vin_and_maps_zero_to_none` is now `…_to_no_entry`.
  - On 3.5, the four Task 1 characterization tests:
    - Fixtures now hold real limits.
    - `test_an_id_keys_out_of_range_hold_warns_at_load_not_at_resolve`: the out-of-range ID is now dropped at load with a warning, and nothing waits.
- `test_vehicles_page.py::test_held_limit_reads_the_vin_store_after_adoption`: the ID fixture is now `[85, 60]`, and the text is "85% (holding 60%)" (the "(restored)" display is gone).
