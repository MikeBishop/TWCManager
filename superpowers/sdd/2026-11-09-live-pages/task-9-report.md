# Task 9 report: Policy page goes live

Commit: a84ae05b "Live pages: Policy page fills from /api/getPolicyState"

## What I implemented
- `themes/Default/policy.html.j2` now draws the whole page:
  - The `<style>` block from `do_get_policy` moved over verbatim, into `<head>`.
  - `format.js` and `live.js` load in this template. `Live.start({urls: ["/api/getPolicyState"], interval: 5000, fingerprint: {{ fingerprint("policy")|tojson }}})`.
  - A `Live.onData` handler goes through every `.policy-box`. When `box.dataset.policy === data.active` it adds the `active` class and unhides the `.policy-active` badge; on every other box it removes the class and hides the badge. It compares through the dataset only and never builds a selector from a policy name.
  - Recursive macro `node(n, i)`:
    - Leaf: `.policy-leaf` with `data-class-if="policies.<i>.nodes.<id>.truth"` and `leaf-true`/`leaf-false`. `.policy-match` and `.policy-value` each hold the literal followed by `<span data-field=... data-format="resolved" data-literal="{{ x|tojson|forceescape }}">`. `.policy-cond` holds the literal condition.
    - Group with one child: draws the child bare.
    - Other groups: `.policy-group` > `.group-bar` (class hook with `group-true`/`group-false`, text AND/OR) > `.group-body`.
  - Macro `box(block)` reads the policy from `master.getModuleByName("Policy").charge_policy[block.index]`. Per R10, `policyLayout()` gives only the index. It draws `.policy-box data-policy="{{ name }}"` and a header: name, then ` (<category>)` when there is one, then ` <span class="badge badge-primary policy-active" hidden>Active</span>`.
  - Ext blocks: `.ext-box` / `.ext-title` "<name> Extension Point", or `.ext-marker` "<name> Extension Point (no policies)" when empty.
  - Names go through Jinja autoescape. The page renders no truth classes and no `active` class; they appear only after the first bind.
- `HTTPControl.py`: deleted `do_get_policy`. `/policy` now renders only the template. Black-clean.

## Structure parity check (one-off, before deleting do_get_policy)
Scripts are in the scratchpad: `/tmp/claude-0/-root-src-TWCManager/2fce5639-f717-5b59-ab39-7a2787979fe1/scratchpad/old.py`, `.../new.py`, `.../cmp.py`.
- Method: tokenised the tags and text of both outputs after the `</style>` and up to `</body>`. Normalisation:
  - Dropped data-* attributes and the empty resolved spans from the new output.
  - Dropped the server-side truth classes, the `active` box class and the Active badge from the old output.
  - Dropped the old " (resolved)" suffixes, which JS now fills.
- Default policy set: 161 tokens each, **identical**.
- Default set plus a custom policy "Mine <b>" (nested group) at index 1, which exercises the Before ext-box: 198 tokens each, **identical**.

## Tests
- RED: `/root/venv/bin/pytest tests/unit/test_policy_view.py -q -k "page or gone"` → 4 failed. The template had no structure yet and `do_get_policy` still existed; that failure was expected.
- GREEN: test_policy_view.py 15 passed. Full `/root/venv/bin/pytest tests/unit -q` → 2687 passed, 1 warning (the known urllib3 warning). `node --test tests/js/*.test.js` → 28 pass, 0 fail. `black --check HTTPControl.py` is clean.
- New tests:
  - `policy_page` fixture: renders through `CreateHTTPHandlerClass(master)`'s real `templateEnv` over the `policy_mod` master.
  - `test_policy_page_renders_structure_only`
  - `test_policy_page_hooks_match_state_paths`: every leaf id in policyStateView has its match/value hooks; the JSON literal and the class hook are present; "(Default)" and the badge are present.
  - `test_policy_page_escapes_names_and_marks_categories`: covers escaping, the Before ext-title, "(Default, Modified)", the "(no policies)" marker and "(Custom)".
  - `test_do_get_policy_is_gone`

## Deviation from brief
- The brief's assertion `"leaf-true" not in html-after-style` cannot pass alongside the brief's own required hook `data-class-true="leaf-true"`. I kept its intent: strip the `data-class-true`/`data-class-false` attribute values first, then assert that none of leaf-true, leaf-false, group-true or group-false remain. I also assert no `policy-box active` and that the badge renders `hidden`.

## Concerns / notes
- Until the first poll (immediate on load) the page shows no Active badge and no truth colours. That is the brief's "neutral until first bind".
- Old output put raw policy names straight into the HTML; they are now escaped (intended).
