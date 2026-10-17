# Task 1 review (6a6c14e..d9939bf)

Spec compliance: PASS. Every name in the Interfaces block exists as written (Outcome.py, Desired.py, reconcile_helpers.py). The brief's 10 tests run verbatim and 13/13 pass.
Task quality: PASS WITH FINDINGS. No Critical findings. Two Important, for later tasks to pick up.

Checks: one clock domain (time.time default at Desired.py:259, production-clock test present); the lock is a leaf and callbacks run outside it (Desired.py:288); newDesire and backoff semantics match the brief (Desired.py:139-146, pinned by the paid-backoff test); per-key maps are bounded by ASPECTS and provider names.

## Concern 4 choices
- `by` change alone is not a new desire (Desired.py:331-341): ACCEPT, but see Minor 1 (release keys on the first writer).
- Same-value decision on an adopted desire takes over in place, returns False (Desired.py:340): ACCEPT. The car already has that value, and `at` is kept so settled() is unaffected. It has no test (Minor 2).
- newDesire leaves `excluded` (Desired.py:139-146): ACCEPT, since the brief says so. Hazard for Task 6, see Important 2.
- adopt(CHARGING) ignores odd values (Desired.py:407-408): ACCEPT. "Disconnected"/"NoPower" must not become bounds. It has no test (Minor 2).
- adopt doesn't check offering: ACCEPT. The brief puts the "requires both" rule in the Task 8 caller, and the docstring says so. Task 8 must actually check `offering`/`offeringSince`.

## Important
1. Desired.py:255-260 and :267: `_states` grows per key and nothing evicts it (no forget). The record/health/state/bounds accessors create entries on demand, so anon:... keys that churn leak for the life of the process. Fix: add `forget(key)` (under the lock, with no callback) and have the registry's forget call it. Task 6/8 or the wiring task can carry it. The store only ever gets entries from keys the registry knows, so this is slow growth.
2. Desired.py:139-146 with :150: `newDesire()` keeps `excluded`. An UNSUPPORTED outcome can be value-dependent (e.g. amps outside `ampsRange`), so after a new value a capable preferred provider stays skipped until `newRound()`. Fix: the Task 6 planner must call `newRound()` when it plans against a new `Desired.at`, or `newDesire()` should drop UNSUPPORTED exclusions (keeping REFUSED, which is retired). Decide in Task 6 and add a test there.

## Minor
1. Desired.py:331-341: when `by` changes alone, `by` is not updated. `release(value, by)` (:365) matches the first writer only, so a second writer's release of the same stop returns False and leaves it pending. Fix: either update `by` in place with no newDesire or callback, or document that release must be called with the original writer. Check the distributor/heartbeat call pattern in Task 8.
2. tests/unit/test_outcome_desired.py: no test pins the by-only no-op, the in-place decision takeover, adopt ignoring "Disconnected"/None, newRound keeping `paid`, or noteOffering True->False->True restamping offeringSince. These are the concern 4 behaviors. Fix: add one short test per behavior.
3. Desired.py:60-65: the lazy `from .Reconciler import satisfied` runs under the store lock (file I/O on first import) and `except ImportError` also hides a real ImportError inside Reconciler. Fix: resolve it before taking the lock, or drop the fallback once Task 6 lands.
4. Desired.py:410: `adopt(AMPS, None)` stores `maxAmps = None` and notifies. Harmless. Guard or ignore it if the caller can pass an unread value.
5. Desired.py:214 and :219: `SessionBounds.lifted` is never set by the store. That is fine for now (Task 8 owns it), but note it is unused here.
6. Report concerns 1 and 3 stand: AttemptRecord and ChannelHealth are mutated outside the lock (single-thread discipline for Task 6), and `reset()` drops `inFlight`, so report handling must compare by identity.
