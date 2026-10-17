# SDD ledger — plan: /home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/plans/2026-10-10-two-token-slots.md

Spec: .superpowers/specs/2026-10-10-two-token-slots-design.md (approved by user 2026-10-10).
Worktree: /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-slots (branch feat/token-slots from fix/owner-api-refresh b6645fe).
Setup: merged fix/teslaapi-request-crash into fix/owner-api-refresh (b6645fe, 572 pass; merge also fixes #682's test fixture to use a JWT, since PR1's baseURL guard needs a classified token) and port-teslaapi-request-crash-1.3.4 into port-owner-api-refresh-1.3.4 (5203b85, same 62 failures). Both local, not pushed.

## Pre-flight scan

| Rows | Produces vs consumes | Finding |
|---|---|---|
| T1 -> T2 | T2 consumes TeslaTokenSlot(kind, classify, refreshURL, clientID, post), usable(purpose incl. "energy"), setTokens, snapshot/restore, refresh, status | consistent |
| T1 -> T3 | T3 uses clear/pause/source/refreshToken, reportScopeRefused | consistent |
| T2 -> T3 | T3 replaces T2's get_car_api 401-expired branch with slotRequestFailed | consistent (planned replacement) |
| T2 -> T4 | applySyncedTokens (T2 shim) replaced by applySyncedToken in T4; storeToken synced branch extended | consistent |
| T2 -> T5 | restoreSlot extended (saved synced doesn't overwrite non-empty); loadSettings skip removed | consistent |
| T2 -> T6 | T6 replaces T2's blanket sync refusal in storeToken with syncedSlotLocked | consistent |
| T4 -> T5 | T5's sync-on test uses T4's fake_db single-column rows | consistent |
| T3 -> T7 | T7 table row 3 said "add slotRequestFailed call" to Powerwall | CONFLICT with T3 (Storm Watch never calls it) |
| T1 self | tests vs semantics (scope, pause, synced) | consistent |
| T2 self | port list omits test_teslaapi_request_errors.py (from merged #682), which uses removed accessors | GAP |
| T2 self | header base 1e72329 / 562 passing stale after merge | STALE |
| T3 self | Files list lacked TeslaPowerwall2.py; Step 3 said "three read paths" | CONFLICT with T3 Interfaces |
| T4 self | tests vs interfaces | consistent |
| T5 self | tests vs interfaces | consistent |
| T6 self | tests vs interfaces | consistent |
| T7 self | per-task table vs T1-T6 | row 3 fixed (see above) |

Ruling: T7 row 3 -> apply reportScopeRefused("energy"), not slotRequestFailed — spec §2 (Storm Watch never pauses/clears) — cost if wrong: none, spec explicit.
Ruling: T2 port list adds test_teslaapi_request_errors.py — required for T2's grep step to pass — cost if wrong: none.
Ruling: plan header base -> b6645fe, baseline -> 572 — reflects the approved merge — cost if wrong: none.
Ruling: T3 Files adds TeslaPowerwall2.py; Step 3 says two vehicle read paths + Storm Watch reportScopeRefused — matches T3 Interfaces and spec — cost if wrong: none.
Task 1: BASE b6645fe
Task 1: implementer dispatched (sonnet), id a5684ad4758891724
Ruling: black only on touched files — venv black 26.10 reformats ~45 untouched files; whole-tree runs would add noise to the PR — cost if wrong: none (CI does not run black on these branches).
Ruling: Co-Authored-By stays the plan's Opus line for all task commits — consistent attribution across the branch; commits are by Claude either way — cost if wrong: cosmetic.
Task 1: implementer DONE_WITH_CONCERNS 9c424fc (600 pass)
Task 1: minor (deferred): frozenset(scp) TypeError on unhashable scp items — guard
Task 1: minor (deferred): synced token without exp falls back to now+8h — pin with test/comment
Task 1: minor (deferred): unused pytest import in test_teslatokenslot.py
Task 1: minor (deferred): owner_token 2nd positional param now scp
Task 1: complete (commits b6645fe..9c424fc, review clean)
Task 2: BASE 9c424fc
Task 2: implementer dispatched (opus) a91b968b017846466
Ruling: added Task 2b (read-only as scope, uniform slotFor walk) — user-approved design change after planning; no behaviour change — cost if wrong: small refactor to revert.
Task 2: implementer DONE_WITH_CONCERNS ecc4446 (619 pass)
Ruling: refreshSlot does no error bookkeeping on not_configured — matches pre-existing behaviour; recording it would back off reads every poll for a Fleet slot without client ID — cost if wrong: a misconfigured Fleet refresh retries silently (ERROR already logged by the slot).
Task 2: concern 1 (spec walk) -> Task 2b; concern 3 (TeslaMateVehicle.py:259 stale comment) -> Task 4 dispatch.
Task 2: minor (deferred): handle_teslalogin.html.j2:6 says "read-only Owner API token" whenever readOnly (also Fleet w/o command scope)
Task 2: minor (deferred): car_api_available logs "no Tesla API token yet" when a token is held but unusable (expired synced / missing scope)
Task 2: minor (deferred): test_teslaapi_token_slots.py imports helpers from other test modules; move to teslatokens.py
Task 2: minor (deferred): TeslaMateVehicle.py:256 stale never-expire comment (Task 4)
Task 2: minor (deferred): read-only refusal re-logs after every fleetSlot change incl. refresh (~8h)
Task 2: minor (deferred): car_api_charge loop uses continue not break when no command slot (sleep+applyChargeLimit per remaining vehicle)
Task 2: complete (commits 9c424fc..ecc4446, review clean)
Task 2b: BASE ecc4446
Task 2b: implementer DONE 5ed5eba (621 pass)
Task 2b: minor (deferred): owner-command test could assert caplog.records == [] instead of "scope" not in text
Task 2b: minor (deferred): grants() docstring could note pause/empty stay in usable()
Task 2b: complete (commits ecc4446..5ed5eba, review clean)
Task 3: BASE 5ed5eba
Task 3: implementer DONE eeba8a1 (632 pass)
Task 3: note (out of scope): TeslaPowerwall2.lastFetch is a class-level dict shared across instances — pre-existing bug, candidate issue later.
Task 3: minor (deferred): Owner-slot Storm Watch 403 falls to generic warning every poll (spec says once per token as missing scope)
Task 3: minor (deferred): reportScopeRefused(refused=True) says token "lacks" scope even when scp lists it — wording
Task 3: minor (deferred): second 401 "expired" after one refresh returns False without clearing slot; repeats every poll
Task 3: minor (deferred): no test for get_car_api 401-expired refresh-retry or vehicle-list 401 path
Task 3: complete (commits 5ed5eba..eeba8a1, review clean)
Task 4: BASE eeba8a1
Task 4: implementer DONE a3ca28b (641 pass)
Task 4: minor (deferred): make_jwt_unknown helper defined at file bottom after use
Task 4: minor (deferred): lastSync not set on kept/unknown_type (unused elsewhere)
Task 4: minor (deferred): unknown-type sync ERROR repeats hourly (spec only limits INFO)
Task 4: complete (commits eeba8a1..a3ca28b, review clean)
Task 5: BASE a3ca28b
Task 5: implementer DONE 71bfed4 (659 pass)
Ruling: accept implementer deviation — carApiTokenSource only means migrated when carApi* holds no Owner token and no 99999^3 sentinel — closes upgrade/downgrade/upgrade hole that would refresh TeslaMate token at Fleet endpoint — cost if wrong: extra re-migration on load.
Ruling: migration treats an Owner token as synced when TeslaMate syncTokens is CONFIGURED (config), not only when tokenSyncEnabled() — sync turns itself off when the DB is unreachable at startup; anti-goal forbids refreshing TeslaMate token — cost if wrong: a user who hand-pasted an Owner token while syncTokens is configured loses its refresh token (it then expires; sync refills it). -> fix round with review findings.
Ruling (Task 5 Important 1): at migration, a carApi* token of ANY known type is synced when the TeslaMate module config has syncTokens true (configured, not runtime tokenSyncEnabled()), or the 99999^3 sentinel is present — covers sync self-disabled at startup and Fleet-typed TeslaMate tokens — cost if wrong: a user-owned Fleet token saved before enabling sync loses its refresh token at first upgrade (expires within 8h; log in again).
Task 5: minor (deferred): deviation conditions not tested apart (Owner token + carApiTokenSource w/o sentinel; Fleet/unknown + sentinel)
Task 5: minor (deferred): saved source value not validated against SOURCES before setTokens
Task 5: minor (deferred): queue saveSettings after the restoreSlot calls (ordering currently safe but fragile)
Task 5: fix round 1/5 dispatched (Important 1)
Task 5: fix round 1/5 (1 addressed, 0 open; commits 71bfed4..643ac98)
Task 5: complete (commits a3ca28b..643ac98, review clean)
Task 6: BASE 643ac98
Task 6: implementer DONE c4fc492 (680 pass); no clean RED run (tests+impl written together)
Task 6: minor (deferred): savePastedToken unknown branch calls tokenRoute only for its log, which says "No Tesla API calls will be made..." — misleading when other slots are fine
Task 6: minor (deferred): refresh-token-only slot shows "none" with no Remove button
Task 6: minor (deferred): removeToken does not reset syncSkipLoggedAt / error counters
Task 6: complete (commits 643ac98..c4fc492, review clean)
Ruling: run the final whole-branch review on the main line (b6645fe..c4fc492) BEFORE Task 7 port — fixes then get ported once instead of twice — cost if wrong: none.
Final review (fable): Ready to merge — Yes; 2 Important, 8 Minor.
Ruling: final fix wave = Important 1 (mismatched-type paste pair), Minor 3 (identical resync early-return), Minor 4 (login gate uses empty()), Minor 6 (scp guard), Minor 7 (CHANGELOG wording) — small, in touched code, ported once — cost if wrong: none.
Ruling: Important 2 (commands never retire a dead Fleet token; command 401 unhandled) -> follow-up issue, not this PR — pre-existing; spec scopes fallthrough to reads — cost if wrong: dead pasted Fleet token keeps being POSTed until replaced (same as today).
Ruling: Minor 5 (no per-slot refresh lock; double refresh race) -> follow-up issue — pre-existing at base — cost if wrong: rare double refresh of a single-use refresh token.
Ruling: Minor 8 (syncConfigured ignores TeslaMate enabled flag) -> keep — safer for TeslaMate per Task 5 ruling — cost if wrong: Owner token treated as synced when TeslaMate is disabled but syncTokens left true.
Minor 9/10: can stay / stale lines noted.
Final: fix wave dispatched (BASE c4fc492)
Final: fix wave DONE 8017385 (685 pass)
Final: re-review all 5 ADDRESSED, no new breakage. Main line complete b6645fe..8017385 (685 pass).
Task 7: BASE port-owner-api-refresh-1.3.4 5203b85; dispatching port (opus)
Task 7: implementer DONE 9ab2271 (62 failures identical; 606 pass)
Task 7: minor (deferred): new test files use confidential-client new_api on 1.3.4; PKCE Fleet refresh covered only by test_public_client_fleet_refresh_request + TeslaMate tests
Task 7: minor (deferred): black reflow of TeslaPowerwall2 403 condition unrelated hunk
Task 7: complete (commits 5203b85..9ab2271, review clean)
