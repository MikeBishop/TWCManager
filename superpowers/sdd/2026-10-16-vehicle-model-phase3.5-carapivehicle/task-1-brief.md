### Task 1: Held limits migrate in one pass; `chargeLimits` is the waiting list (expected lib Δ ≈ −48)

Final review I2 row 1. `HeldLimits.load()` (77 lines) and `resolveLegacyIds()` (55) are two versions of one merge. On top of that, `_waiting` is an in-memory copy of exactly what `load()` leaves in `settings["chargeLimits"]` (the well-formed numeric-ID entries), and the `"id:"` store keys were written only by unreleased development builds (Phase 3 Tasks 2–10; only `deploy/phase3-live` = db47522 carries the writer, and it also carries the cleaner. The controller has checked the box: its `heldLimits` holds no `"id:"` keys). One `_migrate(listed, final)` does both passes. The TeslaAPI side (`listPending`, `loadList`, `resolveHeldLimits`, which lists every usable slot) is unchanged: it is what implements semantics (a).

**Files:**
- Modify: `lib/TWCManager/Vehicle/Reconcile/HeldLimits.py`.
  - Delete `_waiting` and the `"id:"` handling (lines 118–123 and 214–215).
  - Delete the test-only `vins()` (lines 281–282; no lib caller; also reword the comment at :247 that names it).
  - Inline `_snapshot` (:275–279) into `holding()`, its only caller once `vins()` is gone (extra saving, ≈ −3).
  - `load()` and `resolveLegacyIds()` become thin callers of `_migrate`.
  - Trim the header comment to describe the one-pass rule.
- Test: `tests/unit/test_held_limits.py`, `tests/unit/test_limit_wiring.py`.

**Interfaces (all callers unchanged):**
- `HeldLimits._loadedVins: Optional[FrozenSet[str]] = None`. None means `load()` has not run, so nothing waits. Otherwise it is the VIN-shaped keys the store held **at the end of** `load()`, including the VINs `load()` itself migrated. This is today's line 154, computed after the loop. A resolve therefore keeps a load-migrated VIN's entry rather than merging into it.
- `HeldLimits.waiting() -> bool`: `legacy = self.master.settings.get(self.LEGACY_KEY)`; `return self._loadedVins is not None and isinstance(legacy, dict) and bool(legacy)`. The dict check is pre-flight F9: a truthy non-dict `chargeLimits` (hand-edited) must not leave `listPending()` True forever, which would list every 5 minutes. At BASE such a value is never waiting either.
- `HeldLimits.load() -> None`: `self._migrate({}, final=False)`.
- `HeldLimits.resolveLegacyIds(listed) -> None`:
  - `listed = {str(k): str(v).upper() for k, v in listed.items() if v}`;
  - `if listed and self.waiting(): self._migrate(listed, final=True)`.
- `HeldLimits._migrate(self, listed: Dict[str, str], final: bool) -> None`. One pass under `settingsLock`; logs and the save happen after it is released. The order of checks per legacy entry reproduces both of today's passes exactly:

```python
with self.master.settingsLock:
    settings = self.master.settings
    legacy, store = settings.get(self.LEGACY_KEY), settings.get(self.KEY)
    store = store if isinstance(store, dict) else {}
    # load: the store's own VINs before this pass (today's `vin in store`
    # with `vin not in origin`); resolve: the VINs held when load() ended
    loaded = self._loadedVins if final else frozenset(k for k in store if isWellFormedVIN(str(k)))
    if not isinstance(legacy, dict):
        if not final:
            self._loadedVins = loaded
        return
    keep, written = {}, {}
    for key, value in legacy.items():
        limit, discarded = _legacyEntry(value)
        if limit is None:                                   # load pass only: malformed
            warn("Dropped a malformed chargeLimits entry for %s while migrating", key); continue
        isVin = isWellFormedVIN(str(key))
        vin = str(key).upper() if isVin else listed.get(str(key))
        own = _storedEntry(store.get(vin)) if vin else None
        if vin in loaded and vin not in written and (isVin or own is not None):
            if not isVin:                                   # resolve pass: the store keeps its own
                info("Tesla vehicle ID %s is %s: kept normal limit %s%%, discarded %s%%",
                     key, vin, own.outside, limit.outside)
            continue                                        # a VIN key: silently, no "unheld" warning
        if discarded and not final:
            warn("Kept the normal limit but not the out-of-range held limit of the "
                 "chargeLimits entry for %s while migrating", key)
        if vin is None or not isWellFormedVIN(vin):
            if final:
                warn("Dropped the saved charge limit of Tesla vehicle ID %s, which no "
                     "Tesla account lists: its normal limit was %s%%", key, limit.outside)
            else:
                keep[key] = value                           # waits, on disk where it was
            continue
        if isVin and vin in written:                        # keys differing only in case
            warn("chargeLimits entries %s and %s name the same car; kept %s while "
                 "migrating", written[vin], key, key)
            store[vin] = _encode(limit)
        elif own is None:                                   # absent or malformed: legacy takes it
            store[vin] = _encode(limit)
        else:                                               # recorded since load: keep the hold
            store[vin] = _encode(HeldLimit(limit.outside, own.held))
            info("Tesla vehicle ID %s is %s: kept normal limit %s%%, discarded %s%%",
                 key, vin, limit.outside, own.outside)
        written[vin] = key
    settings[self.KEY] = store
    if keep:
        settings[self.LEGACY_KEY] = keep
    else:
        del settings[self.LEGACY_KEY]
    changed = keep != legacy
    if not final:
        self._loadedVins = frozenset(k for k in store if isWellFormedVIN(str(k)))
# outside the lock: the collected warnings, then the infos
if changed and not final:
    logger.info("Migrated chargeLimits to heldLimits")
if changed:
    self._save()
```

Note on exactness:
- The `(isVin or own is not None)` clause keeps two things as they are today:
  - At load, a VIN key whose store entry exists but is malformed is skipped (today's `vin in store`).
  - At resolve, an ID whose VIN entry is malformed is replaced (`test_resolving_replaces_a_malformed_vin_entry`).
- The collision rule applies only to VIN keys, as today. Two numeric IDs naming one VIN merge as `resolveLegacyIds` does today.
- **INTENTIONALLY CHANGED edge (pre-flight F10, accepted):** two numeric IDs naming one VIN whose entry was **loaded malformed**. BASE keeps the first ID's value: the second sees `kept` through `_loadedVins`. The plan merges the second as `(limit2.outside, own.held)`, because `vin not in written` blocks the skip. It has never been seen in practice: Tesla gives each car one ID. No test pins it, and none is added.
- At `final` every ID is either moved or dropped, so `keep == {}` and the save always runs, as `resolveLegacyIds` does today.
- Messages and levels are today's. Within one pass they come out as all warnings first, then the infos, in key order. Today's order was dropped, unheld, collided, then the infos (I2 merges before I2 drops). This is the only log difference; no test depends on interleaving.

- [ ] **Step 1: Characterization tests (must pass at BASE, then after).** Add to `test_held_limits.py`:
  - `test_waiting_is_false_before_load`: a bare `SimpleNamespace` master (as in `test_store_works_before_load_and_on_a_bare_master`; `load()` never runs) with `settings["chargeLimits"] = {"11": 80}`. `waiting()` is False, and `resolveLegacyIds({11: VIN})` changes nothing. Production has no writer of `chargeLimits` but the settings file, which `loadSettings` reads just before `load()`.
  - `test_an_id_naming_a_vin_load_migrated_keeps_that_entry`: legacy `{VIN: 70, "11": [90, 50]}` → `load()` → `resolveLegacyIds({11: VIN})`. Expect `get(VIN) == HeldLimit(70, None)` and the "kept normal limit 70%, discarded 90%" INFO line. This pins `_loadedVins` being taken after the load pass.
  - `test_an_id_keys_out_of_range_hold_warns_at_load_not_at_resolve`: `{"11": [80, 30]}`. One "Kept the normal limit" warning at `load()`; at `resolveLegacyIds({11: VIN})` no warning, and `get(VIN) == HeldLimit(80, None)`.
  - `test_a_malformed_store_entry_is_kept_over_a_vin_key_at_load`: store `{VIN: {"outside": "x"}}`, legacy `{VIN: 80}`. After `load()`, the store entry is unchanged and `chargeLimits` is gone.
  - `test_a_resolve_saves_once_and_logs_no_migrated_line`: after `load()` of `{"11": 80}`, `resolveLegacyIds({11: VIN})` queues exactly one `saveSettings` and logs no "Migrated chargeLimits" line.
- [ ] **Step 2: Retarget the `"id:"` fixture and `vins()` readers.**
  - `test_limit_wiring.py::test_legacy_ids_resolve_once_from_the_first_vehicle_list` (fixture plumbing): the unmatched entry moves from the dev-build store key `"id:44": {"outside": 75, …}` to `chargeLimits["44"]: 75`. **One expected value follows the fixture (pre-flight F4):** l.99's expected `chargeLimits` after load gains `"44": 75`. All other assertions stay: one warning naming 44 and 75%, the final `heldLimits` dict, and 1+1 list GETs. (Task 3 rewrites the same test's re-list at l.115.)
  - `test_held_limits.py` lines 142, 207, 252: `vins()` becomes `sorted(m.settings.get("heldLimits", {}))` or `holding()` (plumbing).
- [ ] **Step 3: Run Step 1 + `test_held_limits.py test_limit_wiring.py test_vehicles_page.py` at BASE** (scratch checkout) → PASS. Record it.
- [ ] **Step 4: Implement** the interfaces above; delete what they replace in the same commit.
- [ ] **Step 5: Full suite** → PASS. Grep `-w` for `_waiting|vins` in HeldLimits callers and `'"id:'` in lib: 0.
- [ ] **Step 6: Commit.** `git commit -m "Migrate held limits in one pass; chargeLimits is the waiting list"`

**Review focus (Task 1):**
- Semantics (a) and (b), and the four Review Focus 4 tests, are unchanged in assertion.
- The lock covers the whole read-modify-write.
- The save still lands in every case today's code saves.
- No `"id:"` handling is left in lib.
- `waiting()` requires a dict (F9).

---

