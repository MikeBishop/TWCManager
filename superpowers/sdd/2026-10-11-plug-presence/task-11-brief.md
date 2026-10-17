### Task 11: Rebase the Fleet rate queue onto the new branch 3

**Files:** conflict resolution only. Expect `lib/TWCManager/EVSEController/TeslaAPIController.py` to conflict (Task 7 changed the vehicle filter that `ace0fef`/`e5478df` rewrite), and possibly `TWCSlave.py`/`TeslaAPI.py` where Tasks 6/8 touched lines near the #694 code.

**Interfaces:**
- Produces: `presence/4-fleet-rate-queue`, with the 8 commits of `presence/2-charge-limits`…: `ace0fef 680c5ec 52837bd 03a47e2 e5478df 5bda833 806ec3b b7e1623` replayed. `presence/5-fleet-rate-queue` stays where it is. In a probe, rebasing onto the Task 1 tip was clean (996 passed).
- Resolution rule for `allEVSEs`: the list comprehension keeps #694's `v.VIN not in served and not (unknown and self._telemetryPluggedIn(v))` and Task 7's `isPluggedHome` test in place of `v.atHome`. Then run `tests/unit/test_teslaapi_controller.py` and `tests/unit/test_teslaapi_controller_presence.py`. A #694 test that builds vehicles without presence keeps `v.atHome`, and that's the no-presence fallback.

- [ ] **Step 1: Rebase**

```bash
git branch presence/4-fleet-rate-queue presence/5-fleet-rate-queue
git rebase --onto presence/3-plug-presence presence/4-arrive-depart presence/4-fleet-rate-queue
```

- [ ] **Step 2: Resolve with the rule above, black the conflicted lib files, then `git rebase --continue`**

- [ ] **Step 3: Verify**

Run: `<PY> -m pytest tests/unit -q` → all passed.
Run: `git log --oneline presence/3-plug-presence..presence/4-fleet-rate-queue` → 8 commits.

---

