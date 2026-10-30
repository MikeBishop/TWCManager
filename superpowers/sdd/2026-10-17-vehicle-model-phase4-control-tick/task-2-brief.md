### Task 2: Token refresh off the serial loop; one refresh per slot at a time (#690) (expected lib Δ ≈ +22)

Today `TWCManager.py:1006–1017` refreshes tokens on the serial thread, which is a POST of up to 10 s. Nothing stops two threads spending one single-use refresh token, since the worker, HTTP, Storm Watch and the background thread all refresh.

**Single-flight:**
- The first caller claims `_refreshing` under `_cond` and POSTs **without** the lock.
- A concurrent caller waits on `_cond` (the wait releases it) up to `REFRESH_TIMEOUT + 5` s and returns the first caller's result.
- An answer arriving after the slot's tokens changed (`changes` moved: a paste, a sync, a clear) is discarded. The refresh then returns `"success"` when the slot holds a token, else `"rejected"`. A late answer never overwrites a pasted token.
- **The 401 path too** (ruling F10): BASE `refresh` calls `self.clear()` on a 401 (TeslaTokenSlot.py:236–241). That clear also runs only if `changes` is unchanged since the claim, so a 401 for the old refresh token never wipes a token pasted during the POST.
- `setTokens`, `clear` and `restore` (:279) take `_cond` (a leaf, no I/O) so a reader on another thread never sees a half-written slot (F10).

**Files:**
- Modify `lib/TWCManager/Vehicle/TeslaTokenSlot.py` (`__init__`, `setTokens` :77, `clear` :109, `refresh` :204).
- Modify `lib/TWCManager/TWCManager.py`:
  - delete :1006–1017;
  - add a background handler `refreshTokens`, which calls `carapi.refreshTokenIfNeeded()`, then `carapi.loadList()` if `carapi.listPending()`, and re-queues itself with `delay=300` in a `finally`, so a raising refresh never ends the schedule (F10);
  - queue it once at startup with `delay=300`, next to `checkCharge`.
- Delete the now-unused `TWCMaster.lastTeslaTokenRefreshCheck` (:57).
- Tests: `tests/unit/test_teslatokenslot.py`, `tests/unit/test_twcmanager.py` (static), `test_limit_wiring.py:236–239` (it indexes the loop source on `lastTeslaTokenRefreshCheck`; point it at the `refreshTokens` handler's text, asserting the same `listPending()` → `loadList()` order: PLUMBING-ONLY, F11).

**Interfaces:**
- Produces:
  - `TeslaTokenSlot._cond: threading.Condition` (leaf);
  - `TeslaTokenSlot._refreshing: bool`;
  - `TeslaTokenSlot._lastRefresh: Optional[str]`.
- `refresh(now=None) -> str` keeps its four results and its signature.

- [ ] **Step 1: Write the failing tests.**

```python
def test_concurrent_refreshes_spend_the_refresh_token_once(requests_mock):
    gate = threading.Event()
    def slow(request, context): gate.wait(2); return {"access_token": tok(), "refresh_token": "r2", "expires_in": 28800}
    hit = requests_mock.post(URL, json=slow)
    s = slot(refreshToken="r1")
    results = []
    ts = [threading.Thread(target=lambda: results.append(s.refresh())) for _ in range(3)]
    [t.start() for t in ts]; time.sleep(0.2); gate.set(); [t.join(5) for t in ts]
    assert hit.call_count == 1 and results == ["success"] * 3 and s.refreshToken == "r2"

def test_a_refresh_answer_after_a_paste_is_discarded(requests_mock):
    # the POST callback calls s.setTokens(pasted, "rp") before answering
    assert s.refresh() == "success" and s.accessToken == pasted and s.refreshToken == "rp"

def test_a_401_after_a_paste_does_not_clear_the_pasted_token(requests_mock):   # F10
    # the POST callback pastes, then answers 401: s.accessToken == pasted afterwards
def test_restore_takes_the_slot_lock():                                        # F10
def test_no_lock_is_held_during_the_post(requests_mock):
    # inside the POST callback: s._cond.acquire(blocking=False) is True (then released)

def test_refresh_tokens_task_requeues_itself():
    # run the handler once with queue_background_task spied: it re-queues {"cmd": "refreshTokens"} with delay=300,
    # also when refreshTokenIfNeeded raises (F10)
def test_the_serial_loop_never_refreshes_tokens():
    src = loopSource()   # TWCManager.py text from "while True:" (the outer loop) to the shutdown
    assert "refreshTokenIfNeeded" not in src and "lastTeslaTokenRefreshCheck" not in src
```

- [ ] **Step 2: Run** → FAIL: the first test makes 3 POSTs; the static test finds `:1013`.
- [ ] **Step 3: Implement** as above. Keep `refresh`'s body as `_refreshOnce(now)` (BASE lines 204–264 unchanged), wrapped by the single-flight. **Discard rule:** read `changes` at the claim; apply `setTokens` only if `changes` is unchanged, under `_cond`.
- [ ] **Step 4: Run** `test_teslatokenslot.py test_teslaapi_refresh.py test_teslaapi_token_slots.py test_teslaapi_token_migration.py test_teslamate_token_sync.py` → PASS, unchanged.
- [ ] **Step 5: Full suite** → PASS.
- [ ] **Step 6: Commit.** `git commit -m "Refresh Tesla tokens off the serial loop, one refresh per slot at a time (#690)"`

---

