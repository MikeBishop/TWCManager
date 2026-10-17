### Spec Compliance
Compliant. Fields.py matches the brief's Interfaces and the spec's "Fields and reads" rules. The 9 tests pass (run against head 7cf8eb5).
- age (Fields.py:~91): NOT_TRACKED or None gives now - obs.at. A timestamp gives now - max(obs.at, liveAt). Correct.
- fresherThanWrite/_fresher: no write gives True. Otherwise obs.at > write.at, strictly, so an observation at the same instant as our write is not trusted (P1). Correct.
- trusted: no observation gives None. A fresher observation is returned whatever the feed state. Otherwise it is returned only if liveAt is a real timestamp and now - write.at > FEED_LAG (strict). Unhealthy (None) and polled (NOT_TRACKED) sources never get the lag exemption. In the second branch `write` cannot be None, because _fresher is True when write is None. This is correct, and the 09:17 shape test passes.
- Thread safety: every access to _latest/_writes is under one non-reentrant Lock. Nothing calls out while it is held: the clock is read outside the lock, and trusted() copies obs/write under the lock and then evaluates outside it. snapshot returns a dict copy, and Observation is immutable.
- KeyError is raised for an unknown field in observe and noteWrite. latest/lastWrite/age/trusted/fresherThanWrite with an unknown field just return None/True; the brief only requires KeyError for observe.

### Strengths
- Small and faithful to the brief. Logic is pure, with an injectable clock.
- `_fresher` is shared by fresherThanWrite and trusted, so the strictness rule lives in one place.
- Extra tests are good. They cover noteWrite KeyError, the constants, the polled-source lag exemption, exactly-FEED_LAG strictness and no-observation. All of them pin spec rules.
- The `__init__.py` re-exports are harmless and fit the brief's note that they grow. `FieldStore.NOT_TRACKED` is the same object as the module sentinel, so both spellings work.

### Issues
Critical: none.
Important: none.
Minor:
- Fields.py observe/noteWrite: an out-of-order `at` (an older report arriving after a newer one) overwrites the newer observation. The brief does not require a guard, so this is fine for now. Later tasks that feed it from several threads or sources may want "keep the newer".
- Fields.py observe/noteWrite: with at=None the clock is read outside the lock. Two concurrent callers can store in the opposite order to their stamps, a tiny window. Reading the clock inside the lock would remove it, and is safe because the clock is injected and not reentrant into the store.
- Unknown-field checks are not applied to the read methods. Acceptable per the brief.

### Assessment
**Task quality:** Approved
**Reasoning:** The freshness semantics (max(valueChangedAt, liveAt), strict-newer-than-write, FEED_LAG only for a healthy report-on-change feed, an unhealthy feed never vouching) match the spec and the brief. The store is correctly locked, the tests pass, and the extras are sound. The remaining points are optional hardening.
