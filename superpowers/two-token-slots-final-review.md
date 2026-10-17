# Final whole-branch review: two Tesla API token slots (PR 3)

Range: `b6645fe..c4fc492` (8 commits) on `feat/token-slots`. Reviewed against the spec (`.superpowers/specs/2026-10-10-two-token-slots-design.md`) and plan Tasks 1–6. Task 7 (1.3.4 port) is out of scope.

Evidence gathered: full `-w` diff read; checkout read for `TeslaTokenSlot.py`, `TeslaAPI.py` (slot plumbing, request paths, migration, paste), `TWCMaster.py`, `HTTPControl.py`, `TeslaMateVehicle.py`, `TeslaPowerwall2.py`, templates; `tests/unit`: **680 passed** (`-p no:randomly`); `black --check` clean on every touched `lib/` file (one touched test file fails black, but it fails at base too and CI excludes `tests/*`); two small probes run against `TeslaTokenSlot` (odd `scp` / odd `exp` claims). Reviewed in one pass; no subagents.

## Strengths

- **The anti-goal is closed by construction, not by policy.** `TeslaTokenSlot.setTokens` forces `refreshToken = ""` and `expireTime = exp` whenever `source == "synced"` (`TeslaTokenSlot.py:84-87`). Every entry path goes through it: `applySyncedToken` passes `""` (`TeslaAPI.py:1676`), `restoreSlot` passes the saved source (synced → dropped), `migrateSavedTokens` blanks the refresh token before writing settings (`TeslaAPI.py:1559-1561`), `fleetTokenExchange` stores `"login"`, and `storeToken` from the form stores `"pasted"`. The only write to `refreshToken` outside `setTokens` in `lib/` is `pasteRefreshToken` (`TeslaAPI.py:1434`), which sets `source = "pasted"` on the next line. `refresh()` returns `not_configured` with no request when `refreshToken` is falsy (`TeslaTokenSlot.py:175`), and `slotRequestFailed` additionally gates the 401-expired refresh on `source != "synced"` (`TeslaAPI.py:260-265`). `fetchLatestTokens` selects only `access` (`TeslaMateVehicle.py:202`). Tests pin each link: `test_refresh_column_neither_selected_nor_decrypted`, `test_sentinel_marks_synced_when_sync_off_at_load`, `test_owner_token_back_in_carapi_after_downgrade_migrates_again`, `test_synced_401_expired_clears_without_refresh`, `test_synced_slot_never_refreshes`.
- **No token value in any log line.** `tokenRoute` logs type and URL host only; the refresh logs "auth response received" (the old INFO4 dump is gone, as the spec hoped); `slotRequestFailed`, the sync-skip INFO, the sync-locked WARNING and the scope ERROR name the slot or scope, never the token; the INFO8 `empty carApiBearerToken '...'` line is gone. Thirteen `not in caplog.text` assertions cover the new lines, including `test_paste_refusal_names_the_slot_and_never_the_token`.
- **Command refusal makes no HTTP call.** All five command entry points (`car_api_charge:661`, `applyChargeLimit:990`, `setChargeRate:1684`, `wakeVehicle:1814`, `CarApiVehicle.apply_charge_limit:2325`) call `refuseCommandIfReadOnly` first and then `slotFor("command")`, returning before any `requests.post` when it is `None`. `test_command_refused_without_usable_fleet` asserts zero calls and no error time.
- **Load order is right and verified.** `TWCManager.py:696` instantiates modules (TeslaMate's startup sync runs in its `__init__`, `TeslaMateVehicle.py:81-82`), `:796` calls `loadSettings`, and `:801` starts the background thread. So the `saveSettings` that `migrateSavedTokens` queues cannot run before the two `restoreSlot` calls; the ledger's "fragile ordering" minor is in fact safe today. Migration keys off `syncTokens` in config rather than the runtime flag, closing the "sync self-disabled at startup" hole (Review Focus 1), and re-migrates when a downgraded release puts an Owner token or the sentinel back in `carApi*`.
- **One chooser, as the spec demanded.** `slotFor` is a four-line walk (`TeslaAPI.py:310-316`); read-only is `grants()` on the slot (`TeslaTokenSlot.py:125-131`), with no special case in the chooser. Nothing here will be dead code under 1.4.0's capability walk except the walk itself.
- **Test suite is behavioural.** Requests are asserted through `requests_mock` (which URL, which `Authorization` header, how many calls), settings round-trip through a real `master_with_settings`, and the TeslaMate fixture records the SQL actually executed.

## Issues

### Critical (must fix)

None.

### Important (should fix)

1. **Mismatched access/refresh pair pasted together is stored unchecked, and the wrong-type refresh then wipes a good access token** (pre-existing for pasted pairs; now the one remaining mismatch entry).
   - `TeslaAPI.py:1495-1535` (`storeToken`), called from `HTTPControl.py:1745-1750` with both form fields.
   - `storeToken` picks the slot from the *access* token and stores whatever refresh token came with it. Base behaved the same for a pair (`setCarApiBearerToken` then `setCarApiRefreshToken`, no type check); its `pasteAccessToken` guard only covered an access token pasted *alone* against a previously stored refresh token, a case the typed slots now make impossible. So `storeToken` is the single place left to close the mismatch, and it is unguarded.
   - Scenario: user pastes an Owner access token plus their opaque Fleet refresh token. Both land in `ownerSlot`. Within an hour of expiry `refreshTokenIfNeeded` POSTs the Fleet refresh token to `auth.tesla.com` with `client_id ownerapi`; Tesla answers 401; `refresh()` calls `clear()` and a still-valid Owner access token is gone, with `updateCarApiLastErrorTime` starting a backoff on top.
   - Fix: in `storeToken`, when `accessToken` and `refreshToken` are both non-empty and `self.refreshTokenType(refreshToken) != tokenType`, drop the refresh token with `pasteAccessToken`'s old warning (or refuse with a new result). One test. Not a spec requirement and not a regression, so not a merge gate; but it is one line, and doing it in this fix round means porting it once.

2. **Commands never retire a dead Fleet token** (spec gap, pre-existing behaviour; follow-up rather than blocker).
   - `setChargeRate` `TeslaAPI.py:1715-1724` (no status check: a 401 body is returned as a truthy dict), `car_api_charge:827-836`, `apply_charge_limit`. Only `wakeVehicle` reacts to 401 at all, and only to "expired".
   - `usable("command")` deliberately has no expiry test, so a pasted Fleet token with no refresh token stays the command slot after it dies at 8 h. Every command cycle POSTs with a dead token, `readOnly` stays False, the read-only gate never engages, and nothing tells the user why commands stopped. The spec scoped fallthrough to reads ("when a token stops working, log the error and fall through" was stated for reads), so this is not a plan deviation, but a reasonable user would expect a 401 on a command to clear a non-synced slot the way a 401 on a read does.
   - Fix (follow-up PR or issue): on a command 401, apply `slotRequestFailed`'s 401 rule (refresh once if expired and refreshable, otherwise clear + ERROR). Not required for this merge.

### Minor (nice to have)

3. **Hourly re-sync of the *same* access token resets slot state.** `storeToken` synced branch (`TeslaAPI.py:1535`) always calls `setTokens`, which zeroes `pausedUntil` and `scopeErrorsLogged` and bumps `changes` (`TeslaTokenSlot.py:76,92-93`). TeslaMate rotates every ~6 h and sync runs hourly, so most syncs re-store an identical token. Effects: an Owner 412 pause ends at the next hourly sync (≤1 h, then one more failed poll and ERROR per hour instead of once per hour-long pause); the "once per token" scope ERROR, the sync-skip INFO and the read-only refusal INFO re-fire hourly for synced slots (this is the mechanism behind the ledger's T2 "re-logs" minor). Fix: in the synced branch, `if slot.source == "synced" and accessToken == slot.accessToken: return "success"` before `setTokens`. Can stay; small.

4. **Login form gate uses `bool(fleetSlot.accessToken)`, not `empty()`.** `HTTPControl.py:1196`. An expired synced Fleet token (sync moved on, or sync turned off) is unlocked for login but still hides the form; the user has to press Remove first. Also hides the form behind an unknown-type or command-scope-less Fleet token (pre-existing). Fix: `not teslaapi.fleetSlot.empty()`. Can stay.

5. **Thread inventory (brief item 5): slot state has no lock; the only real race is pre-existing.** Writers: main loop (`TWCManager.py:950 refreshTokenIfNeeded`, `car_api_available` via `update_vehicle_data`), background-tasks thread (`car_api_charge`, `applyChargeLimit`, `saveSettings`), HTTP server thread (`HTTPControl.py:115`: paste, login, removeToken, settings render), TeslaMate `threading.Timer` (hourly `applySyncedToken`), EMS poll (`getStormWatch` → `refreshTokenIfNeeded`). Concrete race: `pasteRefreshToken` clears the slot and sets the refresh token, then blocks on Tesla; meanwhile the main loop's `refreshTokenIfNeeded` sees `needsRefresh()` true and fires a second refresh with the same single-use token; the loser gets 401 and `clear()`s the slot. Base had the identical window (`apiRefresh` from the same three places). The rest is benign (a cleared slot mid-request yields one failed poll; once-logging counters are advisory). Recommend a follow-up issue for a per-slot refresh lock; nothing to change here.

6. **`frozenset(scp)` raises on a nested `scp` claim** (ledger T1). `TeslaTokenSlot.py:75`. Confirmed by probe: `scp=[["a"]]` → `TypeError`. Only reachable from a hand-crafted JWT: a paste 500s that one HTTP request; a hand-edited `settings.json` would crash startup in `restoreSlot`. Tesla never issues one. Guard is one line (`try: frozenset(scp) except TypeError: None`). Can stay; trivial to fix.

7. **Ruling cost understated for a user-owned Fleet token marked synced at migration** (Task 5 Important 1). Such a token is `synced` and live, so `syncedSlotLocked(fleetSlot)` is true: the Fleet login form is hidden and `fleetTokenExchange` refuses until the token's `exp` or the user presses Remove. "Expires within 8 h; log in again" should read "... press Remove token, or wait up to 8 h, then log in again". Doc/CHANGELOG line only.

8. **`syncConfigured` ignores the TeslaMate module's `enabled` flag.** `TWCMaster.py:1106-1107`. A disabled TeslaMate module with `syncTokens: true` left in config still strips the refresh token from a user's pasted token at migration. Could check `enabled` too. Can stay.

9. **`tests/unit/test_teslapowerwall2_ems.py` fails `black --check`** with the venv's black 26.10. It fails identically at base and CI's autoblack excludes `tests/*`. Can stay.

10. **Two ledger lines are stale.** T3 "no test for get_car_api 401-expired refresh-retry": `test_get_car_api_expired_401_refreshes_once_and_retries` and `test_get_car_api_refreshes_at_most_once` exist (`test_teslaapi_token_slots.py:230,251`). T2 "TeslaMateVehicle.py:256 stale never-expire comment": already rewritten (`TeslaMateVehicle.py:250-251`). Mark both done.

## Triage of the ledger's "minor (deferred)" lines

Fix before merge: **none of the ledger's deferred minors is blocking**, and nothing new blocks either. Important 1 is recommended for this fix round on cost grounds (one line now, ported once), not as a gate.

| Task | Deferred minor | Ruling | Why |
|---|---|---|---|
| T1 | `frozenset(scp)` TypeError | can stay (trivial; do it if touching the file) | hand-crafted JWT only, see Minor 6 |
| T1 | synced token without `exp` → now+8h | can stay | moot: a non-JWT synced token classifies as unknown and is never usable; a JWT without `exp` from Tesla does not exist |
| T1 | unused `pytest` import | can stay | cosmetic |
| T1 | `owner_token` 2nd positional is `scp` | can stay | test helper only |
| T2 | `handle_teslalogin.html.j2:6` says "Owner API token" whenever readOnly | can stay | wording; a Fleet token lacking command scope already gets its own ERROR |
| T2 | `car_api_available` reason "no Tesla API token yet" for held-but-unusable | can stay | INFO8 only |
| T2 | test helpers imported across test modules | can stay | test hygiene |
| T2 | `TeslaMateVehicle.py:256` stale comment | **already fixed**; mark done | line 250 now describes the access-token-only behaviour |
| T2 | read-only refusal re-logs after every `fleetSlot` change | can stay | by design per spec ("once per state change"); hourly for synced slots only because of Minor 3 |
| T2 | `car_api_charge` `continue` vs `break` | can stay | reachable only if the Fleet slot vanishes between the gate and the loop (race) |
| T2b | owner-command test could assert `caplog.records == []` | can stay | test strength |
| T2b | `grants()` docstring | can stay | docs |
| T3 | Owner-slot Storm Watch 403 → generic warning every poll | can stay | Owner API energy 403 is rare; spec's once-per-token rule was written for Fleet scopes |
| T3 | `reportScopeRefused(refused=True)` says "lacks" when `scp` lists it | can stay | wording |
| T3 | second 401 "expired" after one refresh returns False without clearing | can stay | requires Tesla to hand back an already-expired token from a refresh |
| T3 | no test for 401-expired retry / vehicle-list 401 | **stale** for the retry (tests exist); vehicle-list 401 untested but shares `slotRequestFailed` with the tested 412 path; can stay |
| T4 | `make_jwt_unknown` defined after use | can stay | test layout |
| T4 | `lastSync` not set on kept/unknown | can stay | unused elsewhere |
| T4 | unknown-type sync ERROR repeats hourly | can stay | arguably desirable: the user needs to notice |
| T5 | deviation conditions not tested apart | can stay | the combined tests cover the live-box and downgrade paths |
| T5 | saved source not validated against `SOURCES` | can stay | a junk source neither locks the slot nor blocks sync ("kept" checks `pasted`/`login` explicitly) |
| T5 | queue `saveSettings` after `restoreSlot` | can stay | verified safe: background thread starts after `loadSettings` (`TWCManager.py:796,801`); reorder only for robustness |
| T6 | unknown-type paste log says "No Tesla API calls will be made" | can stay (cheap wording fix if convenient) | misleading when the other slot works, but it is the pre-existing `tokenRoute` text |
| T6 | refresh-token-only slot shows "none", no Remove button | can stay | only after an "unreachable" refresh-paste; the next refresh retry resolves it |
| T6 | `removeToken` does not reset `syncSkipLoggedAt` / error counters | can stay | `changes` bumps, so the sync INFO re-logs anyway; error counters keep their pre-existing meaning |

## Declined to judge

- `setChargeRate` does not check the HTTP status and returns a 401/4xx body as a truthy dict (`TeslaAPI.py:1715-1724`): pre-existing, unchanged by this PR (surfaces in Important 2).
- `TeslaPowerwall2.lastFetch` is a class-level dict shared across instances: pre-existing, already noted in the ledger.
- No CSRF protection on any POST route, the new `/teslaAccount/removeToken` included: the whole settings UI works this way; out of scope.
- `VehiclePriority` / `TeslaAPIEVSE` as `readOnly` readers (spec §2): neither reads it on this branch; only `handle_teslalogin.html.j2:6` does. Nothing to check.
- Migration of a TeslaMate Owner token saved by the 1.3.3 line (no sentinel) by a user who removed `syncTokens` from config before upgrading: treated as `pasted`, refresh token kept and refreshed. Undetectable from the data; the spec's rule.
- The 1.3.4 port (Task 7).

## Recommendations

- Do Important 1 now (one condition in `storeToken` plus a test) so it is ported once; it is pre-existing, so the user may equally choose to defer it.
- Open follow-up issues for Important 2 (command 401 retires a non-synced Fleet slot) and Minor 5 (per-slot refresh lock), both pre-existing.
- Fold Minors 3 and 4 into the fix round if cheap; they are each one line.
- Add the Remove-token note from Minor 7 to the CHANGELOG line.

## Assessment

**Ready to merge: Yes** (recommended fix round first: Important 1, Minors 3 and 4, each one line, so they are ported once).

**Reasoning:** The design goals and anti-goals hold: TeslaMate's refresh token can no longer enter TWCManager by any path, no new log line carries a token, refusals make no HTTP call, and the migration is idempotent and survives the sync-self-disabled and downgrade cases, all pinned by tests. No regression against base and no spec deviation was found; the Important items are pre-existing gaps the typed slots make cheap to close.
