# Task 6 report: VehicleRegistry

Status: DONE. Commits on vehicle-model/phase1: 8131814, plus follow-up (load key rule). 882 passed (860 + 22 new).

Files: lib/TWCManager/Vehicle/Registry/VehicleRegistry.py, __init__.py (exports VehicleRegistry), tests/unit/test_registry_membership.py.

Decisions / concerns:
- getOrCreate raises ValueError for empty, non-str or "anon:"-prefixed VINs (reserved prefix; not in brief). Task 7 serial-thread callers (recordVehicleVIN) must guard.
- load() accepts any non-empty ASCII, non-"anon:" string key (same rule as getOrCreate) so toJSON output always reloads; it does not require a well-formed VIN. Entries that are not dicts are skipped; bad field types fall back to defaults.
- load() clamps persisted times to now; into a new vehicle it keeps persisted firstSeen/lastSeen (not a sighting); into an existing one takes older firstSeen / newer lastSeen. Name restored as observation source "persisted", seen=False, stamped at lastSeen.
- expire() checks claims/lastSeen/userAsserted under the registry lock (Vehicle.claims takes only the leaf lock and calls no callables); logging after release. Anonymous vehicles never expire.
- sourceLiveAt: a raising liveness callable is treated as None (not live); exception text not logged.
- forget() only removes the entry (claims/attachments untouched). Spec section checked; nothing further.
- Commit trailer: global-constraints.md says "Claude Opus 5.5" but the harness attribution instruction says "Claude Sonnet 5.5"; used Sonnet. Amend if Opus is wanted.

## Fix round 1
- getOrCreate now requires ASCII (same rule as load); "ÿ1" no longer round-trips into a drop.
- sourceLiveAt returns the callable's result through _number(): non-number, bool or non-finite means None (not live).
- forgetAfterDays <= 0 or non-number falls back to 30 with a warning.
- "added (persisted)" is logged at DEBUG.
- Tests added for all five items; 1-3 and the log level were shown failing first (5 failures), then passing. Full suite 891 passed.
