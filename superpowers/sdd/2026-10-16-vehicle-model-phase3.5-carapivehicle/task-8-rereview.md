# Task 8 re-review (fix round 1, redirected): phase3 a678b9b5, phase3.5 ad029963

Verdict: addressed, with one open finding on load()'s save and two nits.

Verified
- Tests (tests/unit, temp worktrees, since removed): phase3 a678b9b5 1769 passed; phase3.5 ad029963 1854 passed. With the 9 outside-unit tests that matches the report's 1778 and 1863.
- Lib lines: 27,241 -> 27,215 (-26), as reported. Parity test: one edit, the adopted-limit assertion (`HeldLimit(80, None)` -> `None`); command and call counts unchanged.
- Rule on every write path: decideChargeLimit returns "nothing sent" (UNREACHABLE) whenever `current is None`, before any restore/apply branch, for all providers. The only send and save paths are beforeWrite (decision.saveNow / saveOnSuccess) and afterWrite, so the limit apply, the restore, the departure restore (Targets._restoreDeparted -> _restore -> desired restore -> same attempt path) and the adoption (plan, only from a trusted reading) are all covered. Debug one-shots (aspect None) record nothing.
- A reading from TeslaMate, Fleet Telemetry or the registry counts: `believed` is the latest non-excluded observation or our last write; there is no default or -1 in it (the -1 is only the legacy RegistryField view). Pinned by the new BLE-with-TeslaMate wiring test.
- Nothing records (target, target) blind: every saved outside is `normal`, which is either the known `current` or a stored `outside` that was itself recorded from a known value.
- No `[outside, -1]` writer remains: set() routes held None/0/-1 to remove(); `_encode` and sendWhenUnknown are gone; grep finds no leftovers.
- Probe of load()/set() (scratch, removed): a file holding real holds only: 0 saves, untouched. Nothing-held shapes (int, -1, 0, None, a numeric-ID key too) are dropped, and the numeric ID with a real hold waits. set(held=None) on an entry removes it; on a missing entry it is a no-op with no save.
- Forget/expiry: the registry calls `removed` outside its lock; _vehicleRemoved does desired.forget then heldLimits.remove, each taking settingsLock as a leaf and queuing the save after releasing it. set() calls remove() before taking the lock, so there is no nesting. No I/O under a lock.

Findings
1. Open (load): a file with only nothing-held entries (e.g. `{VIN: [80,-1]}`, or `"12345": 75`) triggers a save at load (`changed = kept != limits`; probe: saves=1, key deleted). The decision was "dropped on load without a save if nothing else changed"; only the real-holds-only file is save-free (that is what the new test pins). Fix: do not count a silent drop of a nothing-held entry as `changed` (drop it in memory only, or compare after excluding them) and pin it; warnings-driven drops (malformed, out of range, unlisted) may still save.
2. Nit (CHANGELOG): the line "Removes ... the -1 restore sentinel" was deleted from the reconciler entry. The release still removes main's per-module -1 restore sentinel; only the on-disk format no longer uses -1. Consider restoring that phrase.
3. Nit (HeldLimits.remove/set): after the last entry is removed at runtime, settings keeps `"chargeLimits": {}`, while load() deletes an emptied key. Harmless; no action required.
