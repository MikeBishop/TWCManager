### Finding Verdicts
1. ADDRESSED. Vehicle.py summary() now computes liveAt per field via _liveAt (outside any lock) and uses `_fields.age(f, now=now, liveAt=liveAt)`; `changedAge = now - o.at`. test_summary_field_age_is_liveness_aware fails on old code (age 600 != 100).
2. ADDRESSED. Vehicle.observe clamps `at = min(obs.at, self._clock())` before updating lastSeen. test_future_stamp_clamped_to_clock fails on old code.
3. ADDRESSED. summary() evaluates claims once and derives tier via `_tierOf` from that list. test_summary_tier_from_single_claim_evaluation fails on old code (2 calls vs 1).
4. ADDRESSED. Claim.commands wraps the call in try/except, logs at debug, returns False. test_raising_claim_counts_as_false fails on old code (RuntimeError propagates).
5. ADDRESSED. VIN.py `vin.isascii()` checked before upper(). test_vin_rejects_non_ascii fails on old code.

Non-vacuity: tree at 6271e89 with the two lib files restored from 08bcbb4 gives 6 failed / 8 passed (the 5 new tests plus test_attachments_and_summary, which now expects changedAge). Fix tree: 14 passed.
Changed existing tests: test_attachments_and_summary only gains a changedAge assertion (strengthened). test_rejected_older_stamp_...: clock set to 3000 so the 2000 stamp is not clamped; same assertion kept, so not weakened (needed because of the clamp).

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
None significant. (Several future-stamped observations all clamp to now, so the last writer wins lastSeenSource via >=; benign.)

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage
