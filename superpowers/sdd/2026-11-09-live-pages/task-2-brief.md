### Task 2: Views module: fingerprint, JSON safety, handler harness

**Files:**
- Create: `lib/TWCManager/Control/Views.py`
- Modify: `lib/TWCManager/Control/HTTPControl.py` (add `sendJSON` method to the handler)
- Create: `tests/unit/live_helpers.py`
- Test: `tests/unit/test_live_views.py`

**Interfaces:**
- Produces:
  - `Views.STARTED: float` (module import time = service start)
  - `Views.fingerprint(*shape) -> str`: first 12 hex chars of `sha1(json.dumps([STARTED, *shape], sort_keys=True, default=str))`
  - `Views.jsonSafe(obj) -> obj`: recursively copies dicts (keys `str()`), lists/tuples/sets (→ list); non-finite floats → `None`; `bool/int/float/str/None` as-is; anything else → `str(obj)`
  - `HTTPControlHandler.sendJSON(self, data, code=200) -> None`: status `code`, `Content-type: application/json`, `Cache-Control: no-store`, body `json.dumps(Views.jsonSafe(data))`; swallows `BrokenPipeError` via `debugLogAPI`
  - `tests/unit/live_helpers.callAPI(master, path) -> (status: int, headers: dict, body: bytes)`: builds `CreateHTTPHandlerClass(master)`, makes an instance with `cls.__new__(cls)`, sets `path`, `url = urllib.parse.urlparse(path)`, `client_address = ("127.0.0.1", 0)`, `wfile = io.BytesIO()`, replaces `send_response`/`send_header`/`end_headers` with recorders, calls `do_API_GET()`

- [ ] **Step 1: Write the failing tests**

```python
def test_fingerprint_is_stable_and_shape_sensitive():
    assert fingerprint("a", ["x"]) == fingerprint("a", ["x"])
    assert fingerprint("a", ["x"]) != fingerprint("a", ["y"])
    assert len(fingerprint()) == 12

def test_fingerprint_changes_with_start_time(monkeypatch):
    before = fingerprint("a")
    monkeypatch.setattr(Views, "STARTED", Views.STARTED + 1)
    assert fingerprint("a") != before

def test_json_safe_non_finite_and_objects():
    out = jsonSafe({"a": float("nan"), "b": [float("inf"), 1.5], 3: object, "c": (1,)})
    assert out["a"] is None and out["b"] == [None, 1.5] and out["c"] == [1]
    assert out["3"].startswith("<class")
    json.loads(json.dumps(out, allow_nan=False))
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_live_views.py -v`
Expected: FAIL, `ModuleNotFoundError: TWCManager.Control.Views`.

- [ ] **Step 3: Implement `Views.STARTED`, `fingerprint`, `jsonSafe`, `HTTPControlHandler.sendJSON`, `live_helpers.callAPI`**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_live_views.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/TWCManager/Control/Views.py lib/TWCManager/Control/HTTPControl.py tests/unit/live_helpers.py tests/unit/test_live_views.py
git commit -m "Live pages: Views fingerprint, JSON-safe responses, handler harness"
```

---

