# Review: Owner API token refresh (main + 1.3.4 port)

Ranges:
- main: 18f0c5d (fix/teslamate-token-sync) -> 312793b (fix/owner-api-refresh)
- 1.3.4: f7e30c9 (port-teslamate-token-sync-1.3.4) -> f79c4ea (port-owner-api-refresh-1.3.4)

I reviewed it in one pass. The two `lib/` diffs are the same apart from the
1.3.4 Fleet branch, which keeps `authTokenURL if self.usePKCE() else
fleetRefreshURL`. I compared the two diffs hunk by hunk, so every finding
below applies to both branches.

## Verification done

- Suites ran in temporary worktrees.
  - main @312793b: **542 passed**.
  - 1.3.4 @f79c4ea: **62 failed, 463 passed**.
  - 1.3.4 base @f7e30c9: 62 failed, 436 passed.
  - The FAILED lists on 1.3.4 head and base are identical (`diff` of the
    sorted lists is empty).
  - `tests/unit/test_teslaapi_refresh.py` has 26 tests on main (23
    functions plus parametrisation) and 27 on 1.3.4, which matches the PR
    text.
- Each fix test fails without its fix (main). For each commit I ran that
  commit's tests against its parent's `lib/`:
  - 73208a5: 2 fail.
  - 05dd362: 8 fail.
  - 2f940e6: 2 fail.
  - 4867d89: 4 fail.
  - 200bc0a: 5 fail.
  - 312793b: 1 fails.
  - The PR's claim holds.
- I compared the request with release/1.3.3 by reading
  `git show origin/release/1.3.3:lib/TWCManager/Vehicle/TeslaAPI.py`.
  - URL: `refreshURL` = `https://auth.tesla.com/oauth2/v3/token`, the same
    as `authTokenURL`.
  - Headers: the same.
  - JSON body: `client_id` "ownerapi", `grant_type`, `refresh_token`,
    `scope` offline_access. The same.
  - Transport: `self.session.post`, with `TLS13Adapter` (same body) mounted
    on `https://auth.tesla.com`. The same.
  - 1.3.3 also mounts the adapter on owner-api and the fleet hosts. That
    has no effect on the refresh request, and the PR's Limitations section
    says so.
- On 1.3.4, `test_refresh_token_accepted_while_sync_off` looks for the
  Fleet refresh at the auth.tesla.com endpoint with `client_id`
  `my-client-id`, which matches the PR text.
- I removed the temporary worktrees after use.
- I probed the bare-token paste-back behaviour (Important issue 1 below)
  with throwaway tests in a temporary worktree.

## Strengths

- **Faithful 1.3.3 request.** `test_owner_refresh_matches_release_1_3_3`
  pins the request as literals. `test_session_requires_tls_1_3_at_auth_tesla_com`
  checks that the adapter's `ssl_context.minimum_version` is TLS 1.3, not
  just that an adapter exists.
- **Fleet path unchanged.**
  - `clientID`, URL and `requests.post` are the same as before.
  - `test_fleet_refresh_request` asserts that the session is *not* used.
  - On 1.3.4 the PKCE/confidential URL choice is kept verbatim.
- **Token-sync guard stays first.** `apiRefresh` returns before
  classifying. `savePastedToken` refuses with `token_sync` before decoding.
  `pasteRefreshToken` does not clear anything while sync is on. All paths
  are covered by `TestSyncOn::test_no_refresh_while_sync_on`.
- **`decodeToken` refactor.**
  - It removes the duplicated `jwt.decode` call in `setCarApiBearerToken`.
  - It widens the caught exceptions to `TypeError`/`ValueError`, so a
    non-string token cannot crash classification.
  - It returns None for a non-dict payload.
- **Exact issuer match.** `refreshTokenIsOwner` matches the issuer exactly,
  so the Fleet `.../oauth2/v3/nts` issuer, which starts with the Owner
  issuer, is not taken for Owner. `test_fleet_issuer_is_not_owner` guards
  this.
- **`clearCarApiBearerToken` fixes a real pre-existing bug.**
  `setCarApiBearerToken("")` was a no-op, so a 401 left a stale bearer
  token and `readOnly` behind. The save-then-reload test
  (`test_cleared_tokens_save_and_reload_cleared`) checks that this
  persists correctly through `TWCMaster.saveSettings`/`loadSettings`.
- **`req is None` guards.** They fix real crashes:
  - an `AttributeError` in apiRefresh;
  - an `UnboundLocalError` in wakeVehicle, where `req` was never bound at
    the base.
- The stray `"TeslaAPI"` logging argument is removed.
- **URL-vs-token heuristic in `saveApiToken`.** A URL with a scheme or a
  `?` never becomes a token. It is tested with two URLs.
- The PR descriptions are accurate and disclose their limitations honestly.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **A mistaken bare paste on `/teslaAccount/saveToken` destroys a working
   token and reports "error".**
   - Where:
     - `lib/TWCManager/Vehicle/TeslaAPI.py` `savePastedToken` /
       `pasteRefreshToken` (main ~L1381-1416; 1.3.4 ~L1348-1383).
     - Reached from `saveApiToken`'s new bare-token branch (main ~L1375).
   - What happens:
     - Any string with no scheme and no `?` goes to `pasteRefreshToken`.
       Examples: the bare authorization code `NA_...`, the query string
       `code=abc&state=xyz` without its URL, or any typo.
     - `pasteRefreshToken` clears the bearer token, `readOnly`, `baseURL`
       and the expiry *before* it knows the pasted string is a valid
       refresh token.
     - It then stores the string as the refresh token and tries a refresh.
   - Probe results (fleet bearer `fleet_token()`, refresh `NA_goodrefresh`):
     - Fleet refresh returns 400:
       - `saveApiToken("NA_justthecode123")` returns `"error"`.
       - The bearer token becomes `''` and the refresh token becomes
         `NA_justthecode123`.
       - `saveSettings` is queued by apiRefresh's `RequestException`
         branch, so the loss is persisted.
     - No `teslaApiClientID`: the same end state, with `"error"`.
     - `"code=abc&state=xyz"`: the same, and the Fleet endpoint is called
       with it.
   - Why it matters:
     - Until this change, the paste-back route stored nothing on a bad
       paste (`fleetTokenExchange(None, None)` returned `"error"`).
     - Now a plausible user mistake silently drops working credentials,
       and the error page suggests nothing changed.
     - For a Fleet user, recovery means a fresh login. Pasting just the
       `code` value is a likely mistake, given that the page says "paste
       the redirect URL".
     - A reasonable user expects a rejected paste to leave the current
       tokens alone.
   - Fix:
     - Make the paste atomic: on failure, restore the previous bearer
       token, refresh token, classification and expiry.
     - Simplest form: snapshot `(carApiBearerToken, carApiRefreshToken,
       carApiTokenExpireTime, baseURL, verifyCert, readOnly)` in
       `pasteRefreshToken`, and restore it if `setCarApiRefreshToken`
       returns False.
     - Exception: a no-response (network) failure. Keeping the new token
       there for retry is defensible, but then don't return `"error"`.
     - Also, `apiRefresh`'s `RequestException` branch queues `saveSettings`
       even on a non-401 failure. Make sure the restore happens before that
       save runs; it does, because the save is only queued, but it is worth
       a test.
     - Add a test: a working Fleet token plus a 400 from a bare paste
       leaves both tokens intact.
   - The Settings page is affected in the same way, and it matters as much
     there:
     - Its refresh-only field goes through the same `pasteRefreshToken` ->
       `clearCarApiBearerToken` path.
     - It is the only token UI an Owner API user has, because the
       paste-back form renders only when Fleet login is configured.
     - Before this change, a typo there with a fresh bearer token stored
       only a bad refresh token. The bearer token was kept, and no refresh
       ran because the token was not expiring.
     - Now the typo wipes the bearer token, fails the refresh and persists
       the loss.
     - Snapshot/restore in `pasteRefreshToken` fixes both entry points.

### Minor (Nice to Have)

1. **A bearer token of unknown type falls to the Fleet refresh even when
   the refresh token is an Owner JWT.**
   - Where: `refreshTokenIsOwner` (main ~L260).
   - With any bearer token present, `readOnly` decides. `readOnly` is False
     for an "unknown" token too.
   - Effect: an Owner refresh JWT stored next to an unclassifiable bearer
     token is refreshed at fleet-auth with `teslaApiClientID`.
   - Fix: only trust `readOnly` when the bearer token classified as
     owner/fleet; otherwise fall back to the refresh token's `iss`.
   - This is a narrow case.
2. **A bare Owner *access* token pasted over a stored Fleet refresh token.**
   - Where: `savePastedToken`.
   - It keeps the old Fleet refresh token. When the Owner token expires,
     `refreshTokenIsOwner` returns True (readOnly), so the Fleet refresh
     token is sent to the ownerapi client. That probably gets a 401, which
     clears both tokens.
   - Arguably correct: the old refresh token no longer pairs with the
     bearer token.
   - Consider clearing the refresh token when a bare access token of a
     different type replaces the bearer token, or log a warning that the
     stored refresh token belongs to the old token.
3. **Paste-back UI text.**
   - `request_teslalogin.html.j2` still says only "paste the redirect URL",
     so the bare-token feature is undiscoverable from the page.
   - The success page still says "To drive charging ... you also need the
     Tesla Vehicle Command proxy". That is misleading for an Owner token,
     which is read-only and which the proxy will not take.
   - Cosmetic.
4. **Overstated wording in the PR description.** The stray `"TeslaAPI"`
   argument "made it raise a logging error". In fact logging catches the
   formatting error and prints `--- Logging error ---` to stderr; it does
   not raise into the caller.
5. **Unverified Fleet refresh-token shape.**
   - Where: `ownerTokenIssuer` / `refreshTokenIsOwner`.
   - The Owner-vs-Fleet decision for a bare refresh token assumes Fleet
     refresh tokens are opaque (`NA_...`) or carry a different `iss`.
   - On 1.3.4, PKCE Fleet tokens are minted at auth.tesla.com. If those
     refresh tokens are JWTs with `iss` `https://auth.tesla.com/oauth2/v3`,
     a bare-pasted PKCE Fleet refresh token would be sent with
     `client_id=ownerapi`.
   - I could not verify Tesla's token format from the repo. Worth one check
     against a real PKCE refresh token on the live box. If they are JWTs, a
     client claim (e.g. `azp`/`client_id`) may be a better discriminator.

## Recommendations

- Fix Important 1 before merge. It is the one behaviour change that can
  lose user state.
- Once fixed, the "refresh token pasted on its own replaces the bearer
  token" semantics are sound. Document in the PR that a failed paste leaves
  the previous tokens in place.
- Optionally confirm Minor 5 on the live TWCManager box with a real PKCE
  token (1.3.4).

## Declined to judge

- **Owner API reads use plain `requests`, not the TLS 1.3 session.** The
  requirement covers only the refresh, and the PR discloses it.
  `requests`/OpenSSL negotiate TLS 1.3 by default where it is available.
- **Thread-safety of the shared `requests.Session`.** It is used by
  apiRefresh from both the HTTP handler thread and the main loop. That
  concurrency exists today without the session, the requests session is
  generally tolerant of this, and it is outside this change's scope.
- **A synchronous refresh inside the HTTP request handler.** Pre-existing
  (`setCarApiRefreshToken` already refreshes inline).
- **The pre-existing `except Exception` / unbound `apiResponseDict` flow
  in apiRefresh** after a JSON decode error. Unchanged by this diff.
- **On 1.3.4, PKCE vs confidential Fleet refresh URL selection.** Carried
  over verbatim from the base and outside "Fleet behaviour unchanged".
- **`clearCarApiBearerToken` sets baseURL to "" rather than proxyURL.** It
  is intentional and disclosed: no request is made without a token, and
  the proxy comes back on the next Fleet token.
- **"Pasting both tokens trusts that they belong together."** A disclosed
  design limitation; the user approved the semantics.
- **The 62 pre-existing 1.3.4 failures** (e.g. `test_victron`). The same
  set as at the base, as required. Not examined further.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The Owner refresh exactly matches release/1.3.3, Fleet is
unchanged, the sync guard holds, and the tests are strong and verified to
fail without their fixes. However, the new bare-token paste-back clears
working credentials before validating the pasted string, and persists that
loss while reporting "error". That should be made atomic before merge.
