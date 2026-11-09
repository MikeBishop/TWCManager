### Task 5: `/api/getPolicyState` and the one policy walker

**Files:**
- Modify: `lib/TWCManager/Control/Views.py`, `HTTPControl.py` (route; template globals `policyTree`, `policyLayout`)
- Test: `tests/unit/test_policy_view.py`

**Interfaces:**
- Produces:
  - `Views.policyTree(policy) -> dict`: the root group `{"id": "g", "kind": "group", "op": "AND", "children": [...]}`; for each `(m, c, v)` of the group's zipped lists, a child is a group (op flipped, `id = parent + "-" + i`) when all three are lists, else a leaf `{"id", "kind": "leaf", "match": m, "condition": c, "value": v}`. Node ids index the raw nesting, so a one-item group keeps its own id.
  - `Views.policyState(mod_policy, tree) -> dict` id → state. Leaf: `{"match": policyValue(m), "value": policyValue(v), "truth": bool(doesConditionMatch(m, c, v, False))}`. Group: `{"truth": all(...)}` for AND, `any(...)` for OR over its children's truth. (`doesConditionMatch` logs at INFO8 per leaf; accepted, per spec.)
  - `Views.policyLayout(mod_policy) -> list` of blocks, porting `do_get_policy`'s bucketing (`HTTPControl.py:1516-1574`) exactly: `{"type": "policy", "index": i, "category": None|"Default"|"Default, Modified"|"Custom"}` or `{"type": "ext", "name": "Emergency"|"Before"|"After", "items": [policy blocks]}` (an ext block with empty `items` is the "no policies" marker).
  - `Views.policyStateView(master) -> {"fingerprint": fingerprint("policy", names), "now", "active": str(mod.active_policy), "policies": [{"name", "nodes": policyState(...)}]}` in `charge_policy` order.
  - Route `GET /api/getPolicyState`.

- [ ] **Step 1: Write the failing tests**

```python
NESTED = {"name": "N", "match": ["a", ["b", "c"]], "condition": ["eq", ["gt", "lt"]], "value": [1, [2, 3]]}

def test_tree_ids_and_ops():
    t = policyTree(NESTED)
    assert [c["id"] for c in t["children"]] == ["g-0", "g-1"]
    assert t["children"][1]["op"] == "OR" and t["children"][1]["children"][0]["id"] == "g-1-0"

def test_single_item_group_keeps_its_slot():
    t = policyTree({"name": "S", "match": [["x"]], "condition": [["eq"]], "value": [[1]]})
    assert t["children"][0]["kind"] == "group" and t["children"][0]["children"][0]["id"] == "g-0-0"

def test_state_resolves_both_sides_and_groups(policy_mod):  # Policy module over a fake master
    policy_mod.master.settings["x"] = 5
    p = {"name": "P", "match": ["settings.x", ["settings.x", "tm_hour"]],
         "condition": ["gt", ["eq", "lt"]], "value": [3, [4, -1]]}
    s = policyState(policy_mod, policyTree(p))
    assert s["g-0"] == {"match": 5, "value": 3, "truth": True}
    assert s["g-1"]["truth"] is False and s["g"]["truth"] is False

def test_layout_default_set(policy_mod): # default policies only
    blocks = policyLayout(policy_mod)
    assert [b["name"] for b in blocks if b["type"] == "ext"] == ["Emergency", "Before", "After"]
    assert all(b["category"] == "Default" for b in blocks if b["type"] == "policy")

def test_layout_custom_bucket_and_modified(policy_mod): ...  # an extension policy lands in the "Before" ext block's items; a renamed-condition default reads "Default, Modified"
def test_layout_replaced(policy_mod): ...  # override with no default names: every block is {"type": "policy", "category": "Custom"}

def test_policy_state_survives_odd_values(policy_mod):  # Review Focus 1
    policy_mod.master.modules = {"Odd": {}}
    policy_mod.master.getModuleByName = lambda n: SimpleNamespace(nan=float("nan"), obj=object())
    policy_mod.charge_policy = [{"name": "O", "match": ["modules.Odd.nan", "modules.Odd.obj"],
                                 "condition": ["eq", "eq"], "value": [1, 1]}]
    status, _, body = callAPI(policy_mod.master, "/api/getPolicyState")
    nodes = json.loads(body)["policies"][0]["nodes"]
    assert status == 200 and nodes["g-0"]["match"] is None and nodes["g-1"]["match"].startswith("<object")

def test_policy_fingerprint_follows_names(policy_mod): ...  # renaming a policy changes it; equals pageFingerprint(master, "policy")
```

Build `policy_mod` the way `tests/unit/test_policy.py` constructs the Policy module; give its master `getModuleByName("Policy")` → the module so `callAPI` works.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_policy_view.py -v`
Expected: FAIL on missing names.

- [ ] **Step 3: Implement `policyTree`, `policyState`, `policyLayout`, `policyStateView`, the route and the two template globals**

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/test_policy_view.py tests/unit/test_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A lib tests && git commit -m "Live pages: /api/getPolicyState from one policy walker"
```

---

