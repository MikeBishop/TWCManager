# Task 5 re-review 2: fix round 2 (098f7c8..39d7cfb), N1 only

**Verdict: N1 is fixed, and Task 5 is clean for its cost constraints.**
- No new Important or higher findings.
- One new Low finding (N3), below.

## Verification

- **Focused tests at 39d7cfb:** 131 passed across these files:
  - `test_provider_outcomes_cloud.py`
  - `test_teslaapi_token_slots.py`
  - `test_teslatokenslot.py`
  - `test_teslaapi_refresh.py`
- **`probe-p3t5/probe_rereview.py`:** 20 passed, 3 failed.
  - All 32 cases of the refused-token sweep still pass, including the expired-token-that-cannot-refresh cases. Each sends 1 paid post, then 0 over 40 rounds.
  - The 3 failures are the N1 finding tests (`test_transient_refresh_failure_deletes_the_token[500|503|400]`). They now fail because the defect is fixed.
- **`probe-p3t5/probe_rereview2.py` (new):** 10 passed.

## The four confirmations

**1. Tokens are never cleared on a transient refresh failure. Confirmed.**
- I tested a refresh that answers 500, 502 or 503, a 200 with a non-JSON body, or a 200 with no tokens. In every case:
  - the access token and the refresh token are both unchanged;
  - `slotFor("command")` is None;
  - 20 rounds of every Fleet method plus `wake` send **0** paid requests and **0** further refreshes from the command path.
- Only `refresh()` itself clears a slot, and it does so only on a 401 from the auth server.
- An unreachable auth server still gives `UNREACHABLE "token refresh"`, with the slot kept and not refused.

**2. A genuine invalid_grant behaves exactly as at base. Confirmed.**
- **Refresh answers 401:** `refresh()` clears the slot, including the refresh token, just as at base.
  - The new branch sees `slot.empty()`, so it adds no log line and no refusal. It returns `REFUSED "401"`.
  - The next 5 rounds send 0 posts.
- **Refresh answers 400 invalid_grant:**
  - Slot: base kept it (base clears only on 401), and so does this commit.
  - Commands: refused.
  - Background loop: it keeps retrying the free refresh every 5 minutes, as at base.

**3. The refusal lifts on the background refresh path, not only on a token change. Confirmed.**
- The main loop calls `refreshTokenIfNeeded()` every 5 minutes (`TWCManager.py:1031-1036`). For an expired slot, `needsRefresh()` is True.
  - While the auth server is still down, the next background refresh fails and the command purpose stays refused.
  - Once the auth server is back, that refresh calls `setTokens`, which clears `refusedPurposes`, and `slotFor("command")` is the Fleet slot again.
- The first command after that gets `UNREACHABLE "backoff"`. That backoff comes from the global error time that the failed refreshes set in `refreshSlot`, which is base behaviour. Once the backoff passes, the command returns DONE.
- A read-path refresh (`slotRequestFailed` → `refreshSlot`) lifts the refusal in the same way.

**4. No paid request reaches the refused slot in the meantime. Confirmed.** This holds both in the sweep and in the N1-specific probes above.

## New finding

**N3 (Low): a refusal can outlive the token's real expiry.**
- **Where:** `TeslaAPI.py`, the expired-refresh-failed branch of `_paidPost`, which calls `slot.refuse("command")`.
- **When:** Tesla answers "expired" while the slot's own `expireTime` (the JWT's `exp`) still shows more than an hour left. This needs a host clock skewed by over an hour, or an early revocation.
- **What happens:** `needsRefresh()` stays False, so the background loop never retries the refresh. The command purpose then stays refused until the token changes or the process restarts. Probe: `test_skewed_expiry_is_never_refreshed_in_background`.
- **Cost:** none (no paid requests). Commands are lost for the duration.
- **Fix:** in that branch, also set `slot.expireTime = min(slot.expireTime, self.now())`, so that the next background check retries the refresh.
