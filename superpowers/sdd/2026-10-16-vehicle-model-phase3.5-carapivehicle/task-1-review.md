# Task 1 review: held limits migrate in one pass (db47522..c518644)

**Spec verdict: ✅ compliant.** **Quality verdict: approved.** Five Minor findings, none blocking.

## What I verified

### Tests
- Full suite at c518644 (`tests --ignore=tests/API --ignore=tests/integration`): **1769 passed, 1 xfailed**. This matches the report.
- I put the c518644 test files on BASE lib (a `git archive db47522` copy in scratch). `test_held_limits.py`, `test_limit_wiring.py` and `test_vehicles_page.py` gave **73 passed**. A probe confirmed the tests imported the BASE `HeldLimits.py`, which still has `vins()`. So all 5 new characterization tests and the retargeted fixture hold at BASE, as Step 3 requires.

### Differential fuzz, BASE against new
I ran 20,000 random cases through both versions in one deterministic harness:
- Legacy keys: upper and lower case VINs, numeric IDs and junk keys.
- Legacy values: well-formed, malformed, out-of-range held values, floats and None.
- Store: well-formed entries, malformed entries and lowercase VIN keys.
- `chargeLimits` set to a non-dict 10% of the time (str, list, `{}`).
- Between load and resolve: a reconciler `set()` 40% of the time, and a store entry malformed 20% of the time.
- `listed` maps to valid, lowercase, `"bad"`, `None` and `""` VINs, with int and str keys.

For each case I compared:
- the settings after `load()`, its logs (as a multiset) and its save count;
- `waiting()`;
- the settings after `resolveLegacyIds`, its logs and its save count;
- a second resolve (idempotence).

**Result: 27 of 20,000 cases differ, and every one is the F10 class.** Two or more listed IDs name one VIN that was in `_loadedVins` but whose entry is malformed at resolve time. Some of these entries were loaded malformed. In the rest, the harness corrupted the entry after load, which only a hand edit could do. **There are 0 other differences.** That covers state, saves, waiting, the warn/info multiset and idempotence. Log order was compared as a multiset on purpose, because the brief allows the order to change.

### Spec points
- **`_migrate` matches the brief's code.**
  - The check order is the same.
  - The `(isVin or own is not None)` clause is present.
  - The collision rule applies only to VIN keys.
  - `keep` / `del` / `changed = keep != legacy` are as specified.
  - The `_loadedVins` value is taken after the loop, and only on the load pass.
  - The early return for a non-dict legacy sets `_loadedVins` on the load pass only.
- **`waiting()`** is `_loadedVins is not None and isinstance(legacy, dict) and bool(legacy)`. This is F9.
- **`resolveLegacyIds`** normalises `listed`, then gates on `listed and self.waiting()`.
- **`_waiting`, `vins()` and `_snapshot` are gone.** `_snapshot` is inlined into `holding()`. The comment at `set` now names `holding()`.
- **No `"id:"` remains in lib:** `grep '"id:' lib` returns nothing. No lib caller of `vins()` or `_waiting` remains; the hits in TeslaBLE, TeslaAPI and WallConnectorVins are unrelated locals.
- **Locks:**
  - The whole read-modify-write runs under `settingsLock`. Logging and `_save()` happen after release.
  - No new lock is taken. The lock order is unchanged: only `settingsLock`, reached from the same TeslaAPI call sites as before.
  - There is no I/O under the lock.
- **Saves:**
  - Load saves when `keep != legacy`, as BASE saved when `ids != legacy`.
  - Resolve always saves, because `keep == {}` against a non-empty legacy.
  - Two concurrent resolves are safe. The second re-reads `chargeLimits` under the lock, finds it gone, and returns without saving.
- **Persistence across restart:**
  - A user upgrading with `chargeLimits` is covered by `test_saved_file_carries_the_store_and_restarts_clean`, `test_migration_is_idempotent_and_a_rerun_loses_nothing` and `test_crash_before_the_save_reruns_the_same_migration`.
  - A user with `heldLimits` already is covered by `test_an_existing_store_keeps_its_own_cars`, `test_both_keys_present_the_store_wins` and `test_no_legacy_key_no_save`.
  - All of these are unchanged in assertion and pass.
- **User semantics (a): unmatched IDs dropped with one warning, only after every usable slot's list is non-empty.** The TeslaAPI side is untouched. `test_legacy_ids_resolve_once_from_the_first_vehicle_list`, `test_an_empty_vehicle_list_drops_nothing` and `test_a_failed_second_list_defers_the_drop` pass. The one-warning assertion (names 44 and 75%) is unchanged.
- **User semantics (b): later-added VINs merge as (legacy.outside, store.held).** This is the `else` branch, and the fuzz shows parity for it.
- **No new paid calls.** No HTTP code changed.
- **Lib shrinks:** `HeldLimits.py` goes from 289 to 244 lines (**−45**). It is the only lib file touched. The brief expected about −48. The 3-line gap comes from the `vinsNow` local and the message constants, which is reasonable.
- **Other writers of `chargeLimits`:**
  - `loadSettings` runs only at startup (`TWCManager.py:805`) and calls `load()` right after.
  - `/api/setSetting` and the settings form can write any key, but only as a string. A string is not a dict, so `waiting()` turns False. That is the user's own deliberate edit, so it is not a concern.
  - Reading from `settings` instead of an in-memory snapshot is therefore equivalent. If anything it is more robust: BASE could pop a replaced dict's `chargeLimits` using stale IDs.

### Test mapping (deleted or rewritten)
| Test | Change | Holds? |
|---|---|---|
| `test_limit_wiring::test_legacy_ids_resolve_once_from_the_first_vehicle_list` | `"id:44"` store key becomes `chargeLimits["44"]: 75`; expected post-load `chargeLimits` gains `"44": 75` (F4) | Yes. The one-warning (44, 75%), final `heldLimits`, 1+1 GETs, M5 info, INFO8 capture, no-token-leak and re-list assertions are all unchanged. The only assertion lost is that `"id:"` keys are cleaned, which is deleted behaviour. |
| `test_held_limits::test_realistic_settings_file_migrates` | `vins()` becomes `sorted(settings["heldLimits"])` | Yes. The `held == {...}` assertion just before it fixes the exact store, with all three entries well formed, so the two are equivalent. |
| `test_held_limits::test_no_legacy_key_no_save` | `vins() == []` becomes `holding() == []` | Yes. Both are implied by `"heldLimits" not in m.settings` on the same line. |
| `test_held_limits::test_store_works_before_load_and_on_a_bare_master` | the `vins() == []` term is dropped | Yes. `holding()` still exercises the same snapshot path on a bare master, and `vins()` no longer exists. |

The other changes in `test_held_limits.py` are formatting from black: blank lines and line wrapping. Every assertion is unchanged.

The 5 new characterization tests match the brief's Step 1 specification point by point, and they pass at BASE and at head.

## Findings

1. **Minor**, `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py:146`
   - `vinsNow` is computed on every resolve pass, where it is unused.
   - `loaded = self._loadedVins if final else frozenset(...)`, as the brief wrote it, avoids this and the extra name.
   - Cost is trivial; this is about readability.
2. **Minor**, `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py:244`
   - `if limit and limit.held is not None` relies on a 2-tuple `HeldLimit` always being truthy.
   - `limit is not None` says what is meant.
3. **Minor**, `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py:120`
   - The F9 dict check in `waiting()` has no test pinning it: a truthy non-dict `chargeLimits` after `load()` should give `waiting()` False.
   - The brief did not require one, and the fuzz confirms parity with BASE.
   - A one-line assertion would protect the 5-minute re-list hazard F9 exists for.
4. **Minor**, `tests/unit/test_held_limits.py` (passim)
   - Black reformatted about 20 unrelated existing lines: blank lines and wraps in `test_believed_prefers_a_newer_read_over_our_write`, `test_saved_file_carries_the_store_and_restarts_clean`, `test_listing_before_load_is_resolved_on_the_next_check` and others.
   - This is cosmetic, but it adds noise to the review diff.
5. **Minor (informational)**, `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py:135`
   - A store that still holds a dev-build `"id:NN"` key now keeps it forever.
   - It is inert, because `get` and `holding` ignore non-VIN keys, and the brief accepts this: the controller box has none.
   - No action needed.

No Critical or Important findings.
