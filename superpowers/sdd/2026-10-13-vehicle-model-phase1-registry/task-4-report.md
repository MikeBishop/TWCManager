# Task 4 report
Status: DONE. Added Registry/VIN.py, Registry/Vehicle.py, tests/unit/test_registry_vehicle.py (brief tests plus liveness/trusted and twcVin/read-stub tests). Full unit suite: 841 passed. Black applied to touched files.
Notes: observe() sets lastSeen to the stored obs.at only if >= current lastSeen (late stamps don't regress it). tier/summary evaluate claim callables outside the vehicle lock. Commit trailer follows global-constraints (Opus 5.5), not the session attribution reminder (Sonnet 5.5).
Follow-up commit fixes lastSeenSource to use the stored obs.source (rejected older stamp no longer yields an inconsistent pair); test added. 842 passed.
Spec check: spec says "unseen for N days" and leaves sighting-rule details to the builder; lastSeen = stamp of stored observation (not wall clock), kept.
Concern: summary() field age ignores liveAt while age(f) is liveness-aware.

Fix round 1: summary field age liveness-aware plus changedAge; lastSeen clamped to clock; summary derives tier from one claim evaluation; raising claim callable counts False (debug log); VIN rejects non-ASCII. Tests added (written after the code, not before); 847 passed.
