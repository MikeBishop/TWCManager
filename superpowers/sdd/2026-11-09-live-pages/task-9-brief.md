### Task 9: Policy page goes live

**Files:**
- Modify: `themes/Default/policy.html.j2`, `HTTPControl.py` (remove `do_get_policy`; `/policy` renders the template alone)
- Test: `tests/unit/test_policy_view.py`

**Interfaces:**
- Consumes: `policyTree`, `policyLayout`, `pageFingerprint` globals (Tasks 4–5); `resolved` format.
- Template: the `<style>` block from `do_get_policy` (`HTTPControl.py:1482-1513`) moves verbatim into the template. A recursive macro draws a node: a group with one child draws that child bare; a group draws `.policy-group` > `.group-bar` (`data-class-if="policies.<i>.nodes.<id>.truth" data-class-true="group-true" data-class-false="group-false"`, text `AND`/`OR`) > `.group-body`; a leaf draws `.policy-leaf` (same class hook with `leaf-true`/`leaf-false`) with `.policy-match` = literal `{{ leaf.match }}` + `<span data-field="policies.<i>.nodes.<id>.match" data-format="resolved" data-literal="{{ leaf.match|tojson|forceescape }}">`, `.policy-cond`, `.policy-value` likewise. Boxes: `.policy-box` with `data-policy="{{ name }}"`; header `name` + ` (<category>)`; an `Active` badge per box shown by `Live.onData` (adds `active` class and unhides the badge on the box whose `data-policy == data.active`, removes elsewhere). Ext blocks: `.ext-box` with `.ext-title` `"<name> Extension Point"`, or `.ext-marker` `"<name> Extension Point (no policies)"` when empty. Initial classes are neutral (no truth class) until first bind. `Live.start({urls: ["/api/getPolicyState"], interval: 5000, fingerprint})`.

- [ ] **Step 1: Write the failing tests**

```python
def test_policy_page_renders_structure_only(policy_page):  # render via the handler's templateEnv over a policy_mod master
    html = policy_page()
    assert html.count('class="policy-box') == len(policy_mod.charge_policy)
    assert "Emergency Extension Point" in html and 'data-format="resolved"' in html
    assert "leaf-true" not in html.split("<style>")[-1].split("</style>")[-1]  # no server-side truth
    assert "Live.start" in html and "/api/getPolicyState" in html

def test_do_get_policy_is_gone():
    from TWCManager.Control.HTTPControl import CreateHTTPHandlerClass
    assert not hasattr(CreateHTTPHandlerClass(Mock()), "do_get_policy")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_policy_view.py -v -k page`
Expected: FAIL.

- [ ] **Step 3: Rewrite the template; remove `do_get_policy`**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: Policy page fills from /api/getPolicyState"
```

---

