# Task 8 review: keep `chargeLimits`, drop the `heldLimits` rename

Reviewed vehicle-model/phase3 3fcae411..7ff8d9ae and vehicle-model/phase3.5 ab6df576 (range-diff against 54059990).

**Spec: compliant.** The one deviation, keeping `[outside, -1]`, is the exception the brief allows, and it is justified (see concern 1). It is not yet applied consistently.
**Quality: approve, with one Important fix.**

## Verification run
- tests/unit: phase3 7ff8d9ae **1772 passed**; phase3.5 ab6df576 **1857 passed**. With the 9 passed + 1 xfailed outside tests/unit (tests/API and tests/integration need a live server), that matches the report's 1781+1 and 1866+1.
- Lib lines (all lib/**/*.py): 3fcae411 27,303 → 7ff8d9ae 27,241 (−62); 54059990 27,407 → ab6df576 27,386 (−21). These match the report.
- test_command_path_parity.py is untouched on both branches (`git diff --stat`).
- I ran HeldLimits at ab6df576 directly against a fake master (scratch script, since deleted):
  - A clean 1.3.x file `{V1:[80,-1], V2:[80,50], V3:80, V4:[80,None], V5:[85,0], "12345":[70,60], "999":75}` loads with **0 saves** and leaves every value untouched. `waiting()` is True and `holding()` returns `[V2]`.
  - Resolving it with `{"12345": v1-lowercase, "777": V2}`:
    - V1 was present at load, so it wins, with an INFO line.
    - 999 is dropped with one warning.
    - There is 1 save, and `waiting()` becomes False.
  - A lowercase VIN key is upper-cased, with 1 save.
  - Malformed entries:
    - `"x"`, `[80]` and `[None,50]` are dropped with a warning.
    - `[80,30]` and `[80,True]` are normalised to `[80,-1]` with a warning.
  - An ID whose VIN was recorded after load merges to `[ID.outside, own.held]`. Two IDs that map to one VIN merge the same way. This is the same as the old two-key code at 54059990, so the semantics are preserved.
  - Resolving with an empty list does nothing.
- Main's `getNormalChargeLimit`, applied to a file this branch wrote:
  - `[80,-1]` → `(True, 80, -1)`
  - `[80,60]` → `(True, 80, 60)`
  - A VIN given in lower case: `(False, …)`, because keys are now upper-case.

## 1. Format compatibility
**1.3.x → branch: correct for every shape.**
- `n`, `(o,-1)`, `(o,0)` and `(o,None)` read as nothing held. `(o,n)` reads as held when n is 50–100; otherwise it keeps `outside` and warns.
- Numeric IDs wait in place. Lowercase VINs are upper-cased.
- Malformed entries are dropped with a warning.
- A clean file causes no save, because `kept != limits` compares the original objects.

**Branch → 1.3.x: sane.**
- 1.3.x TeslaBLE (`getNormalChargeLimit(vin)`), on its next restore (`limit == -1`), sends `outside` once for `[outside, -1]` and for `[outside, held]`, then removes the entry. A policy apply records `(outside, limit)`, as before.
- 1.3.x TeslaAPI looks entries up by numeric `vehicle.ID`, so it never sees VIN keys. It starts over: it records the car as newly arrived and writes new ID-keyed entries.
  - On a later re-upgrade, an ID entry whose VIN key already exists is discarded with an INFO line ("VIN present at load wins"). That is acceptable.
- The report's claim that "a 1.3.x TeslaAPI reads `(outside, -1)` as was-at-home" is wrong, though harmless: TeslaAPI cannot see VIN keys at all. This is a report error, not a code error.
- A downgrade cost of keeping `-1`: every car the branch ever saw now has an entry. 1.3.x BLE will blindly restore each car to a possibly stale `outside` once. Under the absence rule it would skip that car. This is minor: one command, toward the car's last known normal limit.
- Main's BLE iterates `settings["Vehicles"]` keys. If a user's Vehicles key is lowercase, the upper-cased chargeLimits key won't match after a downgrade. This is a minor edge case.

## 2. Concern 1: keep `[outside, -1]`? Yes, and apply it in c6 too
I verified the sequence against `Rules.decideChargeLimit` (Rules.py:51-130) at ab6df576:
- `current is None and sendWhenUnknown`, not a restore: saveOnSuccess is `HeldLimit(target if held is None else outside, target)` (Rules.py:99).
  - With the entry absent, a blind apply records `(target, target)`.
  - The next restore then passes `Reconciler.plan` (held.held is not None) and sends `outside == target` (Rules.py:88-95, also blind). It does nothing, and the normal limit is lost.
  - With `[outside, -1]`, the apply records `(outside, target)`, and the restore sends the real normal limit.
- With a known current limit, the stored `outside` of a nothing-held entry is ignored, because `normal = current` when `ours is None` (Rules.py:102-103). The stale-outside risk is therefore confined to the blind path. There, the absent alternative is strictly worse.
- No restore loop: `plan` clears a restore desire when `held.held is None` (Reconciler.py:284-287), and `Targets._restore` does the same (Targets.py:92-95). A `[outside,-1]` entry never triggers a blind re-send of the restore.

**The protection is incomplete.** c6 (Reconciler.py:279-282) handles a restore found already satisfied: the car's known limit equals `held.outside` while we hold a limit. It calls `heldLimits.remove(vin)`, which recreates the absent state. A following blind apply then records `(target, target)`, and the normal limit is lost exactly as above.

The smallest consistent rule: **once written, a VIN's entry stays; "nothing held" is always `[outside, -1]`. Only load/resolve drop entries (malformed or unlisted).**
- Change Reconciler.py:281 to `self._save(vehicle, held.outside, None)`.
- `HeldLimits.remove` (HeldLimits.py:210-218) then has no lib caller. Delete it, which saves −10 lib lines.
- I tried this in a scratch worktree, since removed. Exactly 5 tests fail, all of them pins of `remove()` or of c6 removal:
  - test_limit_wiring.py::test_a_satisfied_restore_removes_the_held_record (flip it to `get(VIN) == HeldLimit(outside, None)`)
  - test_held_limits.py::test_set_and_remove
  - test_held_limits.py::test_store_works_before_load_and_on_a_bare_master
  - test_vehicles_page.py:81
  - test_settings_lock.py:84 (swap it to `set(..., None)`, or drop the remove leg)
- Add a rules or wiring pin for `(current unknown, held=(x, None))` → saveOnSuccess `(x, target)`. Nothing pins it today, and that branch is the reason for the format choice.
- Add one clause to the HeldLimits.py header: "kept, not removed, so a blind send keeps the normal limit". That stops a later cleanup from reverting it.

## 3. Migration semantics: preserved
- Numeric IDs wait on disk, and `waiting()` is set only by `_migrate`.
- On the TeslaAPI side (unchanged by this task), the drop happens only when every usable slot's list returned a list and the combined list is non-empty (`resolveLegacyIds` ignores an empty `listed`).
- Each unlisted ID gets one warning.
- A VIN present at load (`_loadedVins`) wins over an ID. A VIN recorded later merges `[ID.outside, own.held]`.
- A clean 1.3.x file causes no save.
- Note: the "every slot's list came back *non-empty*" wording in the brief is stricter than the code. One slot returning `[]` while another lists cars still resolves. This predates Task 8 and is unchanged.

## 4. Tests
- All three deleted tests seed both `heldLimits` and `chargeLimits`, so they cannot exist with one key:
  - `test_an_existing_store_keeps_its_own_cars`
  - `test_both_keys_present_the_store_wins`
  - `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load`
- "VIN present at load wins" stays covered by `test_resolving_keeps_an_existing_vin_entry` and 3.5's `test_an_id_naming_a_vin_load_migrated_keeps_that_entry`.
- The renames and rewrites match the report's map.
- The brief's pins are present: the 1.3.x shapes, `[outside, held]` under the VIN, and restart persistence. "Restoring removes the entry" is replaced, deliberately, by the `[90,-1]` pin.
- Parity counts are unchanged.

## 5. Locks: OK
- `_migrate`, `set`, `remove` and `holding` touch the dict only under `settingsLock`. Logs and `queue_background_task` come after it is released.
- `get` is an unlocked single-key read, as before.
- `resolveHeldLimits` runs after `vehicleListLock` is released (TeslaAPI.py:563), so the GETs are not made under either lock. No new lock edges.

## 6. CHANGELOG / docs
- CHANGELOG.md:24 is accurate for TeslaBLE only. "A 1.3.x build still reads the VIN-keyed entries" overstates it: 1.3.x's Tesla API path reads only numeric-ID keys. Suggested wording: "…a 1.3.x build's BLE path still reads them after a downgrade; its Tesla API path, keyed by numeric ID, does not."
- CHANGELOG.md:37 "Removes … the -1 restore sentinel" (concern 2) now misleads:
  - docs/PolicyCustomization.md:83 still documents `charge_limit: -1` as "restore", and Policy.py:303 still uses it.
  - Settings now store `-1` again.
  - Either drop the phrase or say "the internal -1 restore argument to each module's applyChargeLimit".
- The adoption wording at :37 is correct: Desired.adopt is limit-only.
- There is no `heldLimits` settings key in lib, docs, CHANGELOG or tests. The `master.heldLimits` attribute remains, which the brief allows.

## 7. Further lib savings
- Deleting `remove()` after the c6 change saves −10. This is the only easy, material one.
- HeldLimits.py:131-132: `if not final: self._loadedVins = frozenset()` in the non-dict branch could fold into the common tail. That saves about 2 lines, which is marginal.

## Findings
| Severity | Where | Finding |
|---|---|---|
| Important | Reconciler.py:281 | c6 still `remove()`s the entry. A following blind apply records (target,target) and loses the normal limit, which defeats the reason for keeping `[outside,-1]`. Fix: `_save(vehicle, held.outside, None)`. |
| Minor | HeldLimits.py:210-218 | `remove()` is dead after the c6 fix; delete it (−10 lib lines). Update the 5 tests listed above. |
| Minor | tests (Rules/limit wiring) | Nothing pins `decideChargeLimit(current=None, held=(x,None), sendWhenUnknown=True)` → `(x, target)`, the branch the format choice rests on. |
| Minor | HeldLimits.py:1-5 | The header doesn't say why nothing-held is kept rather than removed, so a future cleanup could revert it. |
| Minor | CHANGELOG.md:24 | "A 1.3.x build still reads the VIN-keyed entries": true only of 1.3.x TeslaBLE. |
| Minor | CHANGELOG.md:37 | "the -1 restore sentinel" now collides with the documented policy `-1` and the on-disk `-1`. |
| Nit | task-8-report.md | The downgrade claim about 1.3.x TeslaAPI reading `(outside,-1)` is wrong: it reads ID keys only. |
