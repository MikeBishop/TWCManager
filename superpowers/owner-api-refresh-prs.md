# PR descriptions: Owner API token refresh

Two PRs: `fix/owner-api-refresh` into main (stacked on #679) and
`port-owner-api-refresh-1.3.4` into release/1.3.4 (stacked on #680).
release/1.3.3 needs no PR: it already refreshes Owner API tokens with
`client_id=ownerapi` at auth.tesla.com.

---

## PR 1: `fix/owner-api-refresh` -> main

**Title:** Refresh hand-pasted Owner API tokens the way 1.3.3 does

> Stacked on #679 (`fix/teslamate-token-sync`). Review and merge #679 first;
> until then this PR's diff also shows #679's commits.

### Summary

#679 classifies every bearer token by `aud`, so an Owner API token is used
read-only against owner-api. A hand-pasted Owner API token still could not be
refreshed: `apiRefresh` sent every refresh token to the Fleet auth host with
`teslaApiClientID`, and refused outright without a client ID. Tesla only
refreshes Owner API tokens at auth.tesla.com with `client_id=ownerapi`.

- **Refresh by token type.** `apiRefresh` uses the Owner refresh when the
  current bearer token is classified as an Owner API token (`readOnly`). With
  no bearer token (e.g. when only a refresh token was pasted), or one of
  unknown type, it uses the Owner refresh when the refresh token is a JWT
  whose `iss` is exactly `https://auth.tesla.com/oauth2/v3`, decoded without
  signature verification. Anything else, including an opaque or undecodable
  refresh token, gets the Fleet refresh, unchanged. The token-sync guard
  still comes first.
  - Checked on the live box, which uses a PKCE Fleet login
    (`teslaApiClientID` only, no secret): its Fleet refresh token is opaque
    (not a JWT, 67 characters), so opaque means Fleet holds for PKCE too.
    Owner API refresh tokens are JWTs with that `iss`.
- **`teslaApiClientID` is needed only for the Fleet refresh.**
- **A refresh token pasted on its own replaces the stored bearer token.**
  The stored bearer token may be of the other type (e.g. an expired Fleet
  token when switching to an Owner API token). A refresh token entered alone,
  on the Settings page (refresh field only) or as a bare token on the
  paste-back, first clears the bearer token, its classification and its
  expiry, then refreshes by its own type. When both tokens are pasted
  together, the access token is applied first (the form posts it first) and
  the refresh token is stored with it, with no clear and no refresh.
- **A bad paste never loses working tokens.** If Tesla rejects the pasted
  refresh token (4xx/5xx or an unusable body), or it needs a
  `teslaApiClientID` that isn't set, the previous bearer token, refresh
  token, expiry, classification and API error state are restored, and no
  save writes the cleared state. The page says "Tesla rejected the token
  you supplied. Your previous Tesla API tokens were kept." (or explains the
  missing configuration). With no response at all (network failure), the
  pasted token is kept and saved for a retry, and the page says TWCManager
  couldn't reach Tesla and will retry. The Settings page now reports these
  results too, by redirecting to the same pages.
- **An access token pasted on its own drops a refresh token of the other
  type.** A stored refresh token whose type (Owner JWT or opaque Fleet)
  differs from the pasted access token's would be sent to the wrong client
  when the access token expires. It is dropped with a WARNING; one of the
  same type is kept.
- **A 401 on refresh clears both tokens and the token type.** It cleared
  only the refresh token, because `setCarApiBearerToken("")` stores nothing.
  A new `clearCarApiBearerToken` clears the bearer token, `readOnly`,
  `baseURL` (reset to "" as for an unknown token; a configured `teslaProxy`
  is kept for the next Fleet token) and the expiry. `setCarApiBearerToken("")`
  keeps its meaning for other callers. The saved state loads back as no
  token.
- **No crash when a request never goes out.** `apiRefresh` and `wakeVehicle`
  read the response's status in their `RequestException` handlers even when
  there was no response (e.g. no network): `AttributeError` in `apiRefresh`,
  `UnboundLocalError` in `wakeVehicle`. Both now treat it as a failed request;
  `apiRefresh` keeps the tokens for a retry. The 401 log call passed a
  stray `"TeslaAPI"` argument as the message, so logging printed
  `--- Logging error ---` to stderr instead of the message (nothing reached
  the caller). It now logs the message.
- **Paste-back takes a bare token.** `/teslaAccount/saveToken` accepted only
  a Fleet login redirect URL. It now also takes a token on its own: an access
  token becomes the bearer token, anything else is handled as a refresh token
  pasted on its own (above). A URL without a code still stores nothing.
  While token sync is on it stores nothing and returns `token_sync`, as the
  redirect-URL path does. The form now says a bare access or refresh token
  can be pasted too.
- **Login pages (Default theme).** The success page says "Tesla API tokens"
  instead of "Tesla FleetAPI tokens". For a read-only Owner API token it no
  longer says the Vehicle Command proxy is needed: it says Tesla accepts no
  commands with that token and points at TeslaBLE, which sends commands over
  Bluetooth.

`refreshTokenIfNeeded` and `wakeVehicle`'s 401 refresh needed no change: they
refresh through `apiRefresh`. `wakeVehicle`'s 401 refresh only ever sees Fleet
tokens, because `refuseCommandIfReadOnly` returns before any request for an
Owner token.

### Matched to release/1.3.3

The Owner refresh request is the one release/1.3.3's `apiRefresh` sends
(`lib/TWCManager/Vehicle/TeslaAPI.py` @ release/1.3.3):

| | release/1.3.3 | this PR |
|---|---|---|
| URL | `refreshURL` = `https://auth.tesla.com/oauth2/v3/token` (:70, chosen at :166-170) | `authTokenURL`, the same URL |
| Headers | `accept` and `Content-Type`, both `application/json` (:159) | same |
| Body (JSON) | `client_id: "ownerapi"` (:47, :102-104), `grant_type: refresh_token`, `refresh_token`, `scope: offline_access` (:160-165) | same |
| Transport | `self.session.post` (:174); the session mounts `TLS13Adapter` on `https://auth.tesla.com` (:20-31, :115-117), added in b9fb027 because auth.tesla.com requires TLS 1.3 for Owner API tokens | same adapter class, mounted on `https://auth.tesla.com` |

A test transcribes that request as literals and compares the URL, both
headers and the JSON body, and checks that the request goes through the
session and that the session's auth.tesla.com adapter requires TLS 1.3.

### Tests

New `tests/unit/test_teslaapi_refresh.py` (46 tests; full suite 562 passed):

- the Owner refresh request equals 1.3.3's, through the TLS 1.3 session;
- the Fleet refresh request is unchanged and does not use the session;
  `wakeVehicle`'s 401 refresh of a Fleet token still goes to fleet-auth;
- a pasted Owner refresh token alone (via `setCarApiRefreshToken` and via the
  paste-back) gets the Owner refresh, and the new access token is classified
  Owner and read-only with the owner-api base URL; a pasted Owner access
  token is stored as the bearer token without a refresh; a URL without a
  code is not taken for a token and stores nothing;
- `refreshTokenIfNeeded` uses the Owner refresh for an expiring Owner token;
- a pasted opaque refresh token gets the Fleet refresh, even with a stale
  `readOnly` left from an earlier Owner token; a refresh JWT with the Fleet
  issuer (`.../oauth2/v3/nts`) is not taken for an Owner one;
- without `teslaApiClientID`, the Owner refresh works and the Fleet refresh
  is refused before any request;
- a refresh token pasted alone on the Settings page or the paste-back
  replaces a stale bearer token of the other type and gets its own type's
  refresh (Owner over an expired Fleet token, Fleet over a fresh Owner
  token); with both tokens pasted, the access token is applied and nothing
  refreshes;
- a connection error (no response) doesn't crash, for both refreshes and
  for `wakeVehicle`;
- a 401 on refresh clears both tokens, `readOnly`, `baseURL` and the expiry
  and queues a save; a configured proxy is used again for the next Fleet
  token; the saved state reloads as no token, with no refresh;
- a rejected paste (400, 401, 500, unusable 200) over a working Fleet token
  leaves every token and the classification intact, through the paste-back
  and the Settings refresh-only field; no queued save ever sees the cleared
  state, and the file saved afterwards holds the old tokens; a Fleet paste
  without `teslaApiClientID` keeps them too;
- a network failure keeps the pasted token, queues a save and reports
  `unreachable` (paste-back and Settings page); both result pages render
  their own message;
- an Owner refresh token beside a bearer token of unknown type gets the
  Owner refresh;
- an access token pasted alone drops a stored refresh token of the other
  type (both directions, paste-back and Settings page) with a WARNING that
  doesn't contain the token, and keeps one of the same type;
- the paste-back form mentions bare tokens; the success page points an
  Owner token at TeslaBLE and a Fleet token at the proxy;
- with token sync on, nothing refreshes and every paste path refuses.

`test_refresh_token_accepted_while_sync_off` in
`test_teslamate_token_sync.py` now expects the refresh that a refresh token
pasted on its own triggers.

Each test that covers a fix fails without it. The Fleet-unchanged,
opaque-to-Fleet, Fleet-issuer, Fleet-refused, both-tokens-pasted,
same-type-access-paste, Fleet-success-page and sync-on tests guard behaviour
that was already right, so they pass before too.

### Limitations

- **Pasting both tokens trusts that they belong together.** The refresh
  token is stored with the access token pasted beside it, and later
  refreshes by that access token's type.
- **After a clear, a restart with `teslaProxy` configured** points
  `baseURL` at the proxy until a token arrives, as at any startup with no
  token. No request is made without a token.
- **The paste-back form is shown only when Fleet login is configured**
  (`teslaApiClientID` and `teslaApiRedirectUri`). Without that, use the
  Settings page token fields; the route itself accepts a bare token either
  way.
- **A network failure during a paste keeps the pasted token**, with the
  bearer token cleared, so a mistyped token pasted while offline replaces
  the old ones; the retry then rejects it.
- The login page changes are in the Default theme only, like the rest of
  the login pages.
- Only the Owner refresh uses the TLS 1.3 session. Owner API reads still use
  plain `requests`, as before.
- There is still one token slot (#679's limitation).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## PR 2: `port-owner-api-refresh-1.3.4` -> release/1.3.4

**Title:** [1.3.4] Refresh hand-pasted Owner API tokens the way 1.3.3 does

> Port of the main PR, stacked on #680 (`port-teslamate-token-sync-1.3.4`).
> Review and merge #680 first; until then this PR's diff also shows #680's
> commits. Each commit is cherry-picked from main with `-x`.

### Summary

Same change as on main:

- `apiRefresh` uses the Owner refresh (`client_id=ownerapi` at
  auth.tesla.com, through a TLS 1.3 session) for an Owner API token, decided
  by the bearer token's classification or, with no bearer token, by the
  refresh token's `iss`; everything else gets the Fleet refresh.
  `teslaApiClientID` is needed only for the Fleet refresh. The token-sync
  guard stays first.
- A refresh token pasted on its own (Settings page or paste-back) clears the
  stored bearer token and its type first, then refreshes by its own type.
  Both tokens pasted together: access token first, no refresh.
- A 401 on refresh clears both tokens, the token type and the expiry
  (`clearCarApiBearerToken`).
- A rejected paste restores the previous tokens and says so; a network
  failure keeps the pasted token for a retry.
- An access token pasted alone drops a stored refresh token of the other
  type, with a WARNING.
- A bearer token of unknown type no longer decides the refresh type.
- The paste-back form mentions bare tokens; the success page points an
  Owner API token at TeslaBLE.
- No crash in `apiRefresh` or `wakeVehicle` when the request never goes out.
- `/teslaAccount/saveToken` also accepts a bare access or refresh token (a
  URL without a code still stores nothing), and refuses while token sync is
  on.

**Difference from main:** 1.3.4 already picks the Fleet refresh host by
client type (auth.tesla.com for a public PKCE client, fleet-auth for a
confidential one). That is kept as is. The Owner refresh is a separate path
in front of it, so a PKCE Fleet refresh and an Owner refresh both go to
auth.tesla.com and differ in `client_id` (and the session). A bare-pasted
PKCE Fleet refresh token is still told apart from an Owner one: on the live
box (PKCE Fleet login, `teslaApiClientID` only) the Fleet refresh token is
opaque (not a JWT, 67 characters), while Owner API refresh tokens are JWTs
with `iss` `https://auth.tesla.com/oauth2/v3`.

### Matched to release/1.3.3

Same request as on main: URL `https://auth.tesla.com/oauth2/v3/token`,
headers `accept`/`Content-Type` `application/json`, JSON body
`client_id: "ownerapi"`, `grant_type`, `refresh_token`,
`scope: offline_access`, sent through a session with `TLS13Adapter` on
auth.tesla.com (`TeslaAPI.py` :20-31, :47, :70, :102-104, :115-117, :159-174
@ release/1.3.3).

### Tests

The same `tests/unit/test_teslaapi_refresh.py`, adapted: the tests default
to a confidential Fleet client so the Fleet and Owner refreshes go to
different URLs, and one more test checks the public-client (PKCE) Fleet
refresh at auth.tesla.com with the Fleet `client_id` and without the session
(47 tests). `test_refresh_token_accepted_while_sync_off` looks for the Fleet
refresh at auth.tesla.com, where 1.3.4 sends a public client's refresh, and
the rejected-paste tests built on a real TWCMaster use a confidential client.
Full suite: 62 failed, 483 passed. The 62 failures are the same
pre-existing set as on #680's branch, compared test by test.

### Limitations

As on main: pasting both tokens trusts that they belong together; a
network failure during a paste keeps the pasted token; after a clear, a restart with `teslaProxy` points `baseURL` at the proxy until a
token arrives; the paste-back form is shown only when Fleet login is
configured (`teslaApiClientID` and `teslaApiRedirectUri`; the Settings page
fields work without it); only the Owner refresh uses the TLS 1.3 session;
one token slot.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
