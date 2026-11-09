# Task 5 report: /api/getPolicyState and the one policy walker

Commit: f0b68150 Live pages: /api/getPolicyState from one policy walker

## Implemented
- `Views._policyFingerprint(policies)`: the one definition of the policy page shape
  (`fingerprint("policy", names)` in charge_policy order). `pageFingerprint(master, "policy")`
  and `policyStateView` both use it; the view passes its own snapshot of charge_policy.
- `Views.policyTree(policy)`: root `{"id": "g", "kind": "group", "op": "AND", "children"}`;
  group child when m, c, v are all lists (op flipped, id `parent-i`), else leaf
  `{"id","kind":"leaf","match","condition","value"}`. One-item groups keep their slot.
- `Views.policyState(mod_policy, tree)`: id -> leaf `{"match": policyValue(m), "value": policyValue(v),
  "truth": bool(doesConditionMatch(m, c, v, False))}`, group `{"truth": all/any}`.
- `Views.policyLayout(mod_policy)`: exact port of do_get_policy's bucketing
  (insertion_points {0: Emergency, 1: Before, 3: After}, `replaced`, conditions_match,
  flush). Blocks `{"type":"policy","index","category"}` and `{"type":"ext","name","items"}`;
  a flush with no ext name (j past the last insertion point) emits the bucket's policy blocks
  plainly with category None, as the HTML did.
- `Views.policyStateView(master)` and route `GET /api/getPolicyState` (via sendJSON).
- Template globals: `policyTree=Views.policyTree`, `policyLayout=lambda: Views.policyLayout(Policy module)`
  (zero-arg in templates). do_get_policy left untouched. Views.py does not import HTTPControl.

## Tests (tests/unit/test_policy_view.py, 11 tests)
Brief's tests plus: OR group truth, ext ordering relative to default slots, trailing extension
past the last insertion point, full route check (headers, active, names, node ids).

Deviation: in `test_policy_state_survives_odd_values` the brief's lambda returned the odd
namespace for every name, including "Policy", which would break the route; the test's
getModuleByName returns the Policy module for "Policy" and the namespace otherwise.
Fixture: Policy(master) with empty policy config, then `mod.charge_policy = deepcopy(default_policy)`
so tests mutating the list never touch the class-level list (Policy's class attribute is shared).

## TDD evidence
- RED: `git stash push lib; pytest tests/unit/test_policy_view.py -q` -> "ERROR tests/unit/test_policy_view.py
  ... 1 error during collection" (ImportError on the missing Views names), expected.
- GREEN: `pytest tests/unit/test_policy_view.py tests/unit/test_policy.py -q` -> 97 passed.
- Full: `/root/venv/bin/pytest tests/unit -q` -> 2700 passed, 1 warning (pre-existing, not from these tests).

## Files
- lib/TWCManager/Control/Views.py
- lib/TWCManager/Control/HTTPControl.py
- tests/unit/test_policy_view.py

## Concerns
- black not installed in venv; formatting kept by hand to 88 columns in new code.
