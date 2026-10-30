# Task 2 report: token refresh off the serial loop; one refresh per slot (#690)

Status: DONE_WITH_CONCERNS (minor: lib delta +32 vs expected +22). Commit b782b843 on vehicle-model/phase4 (BASE 874a20d9). Not pushed.

## Implemented
- `TeslaTokenSlot`:
  - `__init__` adds `_cond = threading.Condition()` (leaf), `_refreshing`, `_lastRefresh`.
  - `refresh(now=None)` is the single-flight wrapper. Under `_cond` it either claims (`_refreshing = True`, records `claimed = changes`) or `wait_for(not _refreshing, REFRESH_TIMEOUT + 5)` and returns the first caller's `_lastRefresh`. On a wait timeout it returns `"unreachable"`. The POST runs in `_refreshOnce(now, claimed)` without the lock. A `finally` releases the claim, records the result and `notify_all`s.
  - `_refreshOnce` is BASE's body with two edits:
    - Success: `setTokens(..., claimed)`.
    - 401: `clear(claimed)`.
    - If the slot changed since the claim (paste, sync or clear), the write is skipped and the result is `"success"` when the slot holds a token, else `"rejected"` (F10: a 401 never wipes a pasted token).
  - `setTokens(..., claimed=None)`, `clear(claimed=None)` and `restore(snap, claimed=None)` write under `_cond` and return whether they wrote.
    - `setTokens` decodes and runs `classify` *before* taking the lock, because TeslaAPI.tokenRoute logs. That keeps all I/O out of `_cond`.
    - `clear` is now `restore(EMPTY_SNAPSHOT, claimed)`, field-for-field identical to BASE's clear, and shrinks lib.
- `TWCManager.py`:
  - Deleted the loop's 5-minute refresh block (BASE :1010–1021).
  - Added a module-level `refreshTokens(master)`: `refreshTokenIfNeeded()`, then `loadList()` if `listPending()`, with `queue_background_task({"cmd": "refreshTokens"}, delay=300)` in a `finally`.
  - It is dispatched from `background_tasks_thread` and queued once at startup with `delay=300`, right after `checkCharge`.
  - The `"loadVehicleList"` background cmd branch had only one producer (the deleted loop block), so I removed it as dead code. `git grep "loadVehicleList['\"]"` now finds nothing. `TeslaAPI.loadVehicleList()` itself is untouched.
- `TWCMaster.lastTeslaTokenRefreshCheck` deleted. The grep `git grep -nwE 'lastTeslaTokenRefreshCheck' -- lib html tests/unit tests/integration tests/API docs` finds only the new negative assertion in test_twcmanager.py.

## Tests
- tests/unit/test_teslatokenslot.py (new):
  - test_concurrent_refreshes_spend_the_refresh_token_once
  - test_a_refresh_answer_after_a_paste_is_discarded
  - test_a_refresh_answer_after_a_clear_is_rejected
  - test_a_401_after_a_paste_does_not_clear_the_pasted_token (F10)
  - test_no_lock_is_held_during_the_post
  - test_slot_mutators_take_the_slot_lock[restore|setTokens|clear] (F10)
- tests/unit/test_twcmanager.py, new class TestTokenRefreshTask:
  - test_refresh_tokens_task_requeues_itself[True|False]
  - test_a_raising_refresh_still_requeues (F10)
  - test_without_teslaapi_it_still_requeues
  - test_it_is_dispatched_and_queued_at_startup
  - test_the_serial_loop_never_refreshes_tokens
  - The handler is compiled from source via ast, as in test_sigterm_shutdown.
- Deviation from the brief's sketch: the "no lock during POST" probe runs `acquire(blocking=False)` on **another thread**. `_cond` wraps an RLock, so a same-thread probe would always succeed and test nothing.

### TDD evidence
- RED: 14 failed, 71 passed.
  - The concurrency test failed with `assert (3 == 1)` (3 POSTs).
  - Paste/401/clear tests failed on wrong tokens or results.
  - Lock tests failed with no `_cond`.
  - The static test found the refresh in the loop.
- GREEN, focused: test_teslatokenslot, test_twcmanager, test_limit_wiring, test_teslaapi_refresh, test_teslaapi_token_slots, test_teslaapi_token_migration, test_teslamate_token_sync, test_rs485_serial_only: 251 passed.
- Mutation checks:
  - Making `restore` unlocked fails the [restore] and [clear] cases: the thread is no longer blocked.
  - Leaking `_cond` across the POST fails test_no_lock_is_held_during_the_post (`[True] == [False]`).
  - A first combined mutation run hung on the leaked lock and was killed by `timeout`. The file was restored from backup and verified clean.
- Full suite: `timeout 600 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider` gives **1895 passed, 1 xfailed, 1 warning**. That is baseline 1881 plus 14 new tests. The warning is not from the touched test files: they run warning-free.
- black --check passes on the 3 lib files.

## Test map (rewritten or deleted)
- test_limit_wiring.py::test_a_failed_boot_list_load_recovers_without_an_arrival, source assertions at :237–240: PLUMBING-ONLY (F11).
  - It now indexes from `def refreshTokens(master):` and asserts `carapi.listPending()` comes before `carapi.loadList()` within 900 chars. Same listPending → loadList order; the load is now a direct call instead of a queued task.
  - It also asserts the `refreshTokens` dispatch exists, replacing the removed `loadVehicleList` dispatch check.
  - The behavioural half (two GETs, recovery) is unchanged.
- No other test was deleted or rewritten.

## Lib lines
- Before (BASE 874a20d9): 27,377. After: 27,409. Δ +32 (expected ≈ +22).
- `git diff --shortstat 874a20d9 -- lib`: 3 files changed, 102 insertions(+), 70 deletions(-).
- Over budget by 10. Black splits setTokens' longer signature (+4). Decode/classify had to move outside the lock, since tokenRoute logs, so the assignments were restructured, plus comments. Offsets: clear became a restore one-liner (−12), and the loadVehicleList dispatch was removed.

## Self-review / concerns
1. Timing change: BASE's first periodic refresh ran on the first loop pass (`lastTeslaTokenRefreshCheck = 0`). Now the first runs at +300 s, as the brief specifies. The boot `checkCharge` → `loadList` still refreshes before the list load when no list is attached.
2. A waiter that times out (more than 15 s) returns `"unreachable"` without POSTing. That is not in the brief's four-result contract text, but it is one of the four values.
3. `TeslaAPI.loadVehicleList` holds `vehicleListLock` across a refresh (pre-existing exception). A refresh there may now also *wait* up to 15 s on another thread's in-flight refresh. That is no worse than BASE's own 10 s POST plus retries, and the lock order is unchanged (`_cond` is a leaf; waiting releases it).
4. Callers sharing a result (for example `refreshSlot`'s save-on-failure) may each act on it, which at most means a redundant settings save. No paid calls are added: the token endpoint is free, and fewer POSTs are made.
5. No token text is logged (test_refresh_logs_no_token still passes).

## Fix round 1 (commit 984f889e)

Finding (Important 1): a refresh token pasted while a background refresh was in flight was answered with the in-flight (discarded) result, "token_rejected", and never POSTed; restore() then put back the spent r1.

Changes (TeslaTokenSlot.py):
- New `_claimedAt`: the slot's `changes` count when the in-flight refresh claimed the slot.
- `refresh()` now loops. A waiter records whether its slot's `changes` equals `_claimedAt` before it waits, and shares `_lastRefresh` only when they match.
- When they differ (a paste, sync or clear happened after the claim), the waiter goes round the loop once the in-flight refresh ends. It then waits again if another refresh is running, or claims the slot and POSTs its own refresh token.
- A successful in-flight refresh moves `changes` itself (its setTokens). That cannot trigger a second POST from a waiter, because the comparison uses the waiter's state at entry, not after the wait. test_concurrent_refreshes_spend_the_refresh_token_once still sees exactly 1 POST.

Test (new): tests/unit/test_teslaapi_token_paste.py::test_a_refresh_token_pasted_during_a_refresh_is_sent
- Uses a real `new_api()` and requests_mock. A background `fleetSlot.refresh()` of r1 blocks inside its POST, then `savePastedToken(OPAQUE_REFRESH)` runs on another thread.
- Asserts the result is ["success"], the POSTed refresh tokens are ["r1", OPAQUE_REFRESH], and the slot ends holding "r-pasted" with source "pasted".
- RED before the fix: `['token_rejected'] == ['success']` failed. GREEN after.

Commands / output:
- Covering tests: test_teslatokenslot, test_teslaapi_token_paste, test_teslaapi_refresh, test_teslaapi_token_slots, test_teslaapi_token_migration, test_teslamate_token_sync, test_twcmanager and test_limit_wiring gave 260 passed.
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): 1896 passed, 1 xfailed, 1 warning (the same unrelated warning).
- Lib: 27,416 (Δ from BASE 27,377: +39; this fix +7). `git diff --shortstat 874a20d9 -- lib`: 3 files changed, 109 insertions(+), 70 deletions(-).
