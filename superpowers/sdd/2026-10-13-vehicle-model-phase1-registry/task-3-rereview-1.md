### Finding Verdicts
1. ADDRESSED — lib/TWCManager/Vehicle/Registry/Fields.py:65-81 (`_store`): `obs.at < old.at` returns the old entry, equal `at` replaces; used by observe (:88) and noteWrite (:98). Tests cover older/equal for observations and writes.
2. ADDRESSED — Fields.py:76-77: `self._clock()` is read inside `with self._lock`. test_clock_read_inside_lock asserts the lock is held on both paths.

### New Breakage in the Fix Diff
None. 13/13 tests in tests/unit/test_registry_fields.py pass at 1c30ee8. The lock is non-reentrant, and the clock is only called under it; the default clock does not re-enter the store.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage
