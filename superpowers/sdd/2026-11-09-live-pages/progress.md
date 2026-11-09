# SDD ledger — plan: /root/src/TWCManager/docs/superpowers/plans/2026-11-09-live-pages.md

Spec: /root/src/TWCManager/docs/superpowers/specs/2026-10-30-live-pages-design.md
Branch: feat/live-pages (from upstream/main f094c7c8), working tree /root/src/TWCManager
Plan archived: origin/docs/vehicle-model-planning 64084560

## Pre-flight scan

| Pair / task | Produces → consumes | Finding |
|---|---|---|
| T1→T6 format.js | core fns → page fns | clean; T6 extends same file |
| T6 `not` predicate | uses "Live-truthy" semantics | format.js can't depend on live.js → Ruling R1 |
| T6 scheduledStart | listed `(status)`, test calls `(null, ctx)` | Ruling R2 |
| T6 resolved vs T9 template | `data-literal` from Jinja `tojson` | tojson escapes <>&' as \u00xx; raw string compare fragile → Ruling R3 |
| T2→T3/T4/T5 | fingerprint/sendJSON/callAPI | clean |
| T3 vs T4 | T3 uses fingerprint("home"); T4 adds pageFingerprint | must agree → Ruling R4 |
| T4 test_vehicle_entry | `vehicles[-1]` assumed VIN | registry sorts "5YJ…" before "anon:8244" → Ruling R5 |
| T4 test_no_secrets | asserts "token" not in body | readOnlyReason text may legitimately say "token" → Ruling R6 |
| T4 Views vs T8 removal | Views must not import HTTPControl helpers | Ruling R7 |
| T5→T9 | policyTree/policyLayout globals | clean |
| T7→T8/T9/T10 | hook vocabulary | clean |
| T7 vehicleImage → T10 Modern card | drawVehicleImage | clean |
| T8 test_page_carries_fingerprint | uses undefined `m` | trivial; implementer defines m |
| T10 status.js / T8 templates | loadVIN removal only in T10 | clean |
| T11 integration | api_get paths w/o /api prefix | matches existing tests, clean |
| T1..T11 self-consistency | tests vs code per task | no other contradictions found |
| Workflows | CI step | never commit .github/workflows (PAT); T11 hands off |

## Rulings

- R1: `Format.not(v)` implements the truthiness rule itself (false for null/undefined/false/0/""/[]) — format.js stays standalone — costs a duplicated 1-line rule if wrong.
- R2: `scheduledStart(value, ctx)` ignores value and reads ctx.data — the test is the more specific text — trivial if wrong.
- R3: `resolved` compares `JSON.stringify(v) === JSON.stringify(JSON.parse(el.dataset.literal))` — robust to Jinja escaping — none.
- R4: chargingPointsView uses `pageFingerprint(master, "home")` once T4 adds it; value equals `fingerprint("home")` — none.
- R5: tests select the vehicle entry by `key == VIN`, not by position — none.
- R6: secrets test asserts the fixture token value ("tok") is absent and no JSON key contains token/secret/webhook (keys, not values) — spec allows read-only reasons — if wrong, a value-level leak would go untested.
- R7: Views.py imports model modules (Presence, Desired, Outcome.RULES, Belief, Rules) directly, never HTTPControl — avoids a cycle — none.

## Tasks
- R8: JS test command is `node --test tests/js/*.test.js` everywhere (plan and CI handoff updated) — Node 22 treats a directory argument as a module path and fails — none.
Task 1: complete (commits f094c7c..22838f8, review clean). Minor noted: usd() exact-binary ties (0.125) round half-up vs Python half-even; pyStr repr quoting edge cases — final-review candidates.
Task 2: complete (commits 22838f8..f26ab4c, review clean). Env: pytest at /root/venv/bin/pytest (Py3.14; no 3.8 locally — final review should try 3.8 via uv if reachable). Pre-existing urllib3 warning from Enphase tests.
Task 3: complete (commits f26ab4c..f18c806, review clean). Minor parked: Gen3 point fields unasserted; chargingPoints() called twice per request.
- R9: template global is `fingerprint(page, vin=None)`; Python function is `Views.pageFingerprint(master, page, vin=None)` (Task 8 Python tests call pageFingerprint; templates call fingerprint) — none.
Task 4: minor (deferred): pageFingerprint("vehicle") builds history dict under settingsLock just for groups
Task 4: minor (deferred): mid-module imports in test_live_views.py; black not run (repo has autoblack workflow)
Task 4: minor (deferred): bleStatus *Age fields from its own clock — JS uses epoch fields (since/scannedAt/attempt.at) vs now, so ages honour `now`
Task 4: minor (deferred): watch.status / bleStatus pass-through — confirm no secrets in final review
Task 4: fix round 1/5 (1 addressed, 0 open — vehicles fingerprint single source; commits ef825dc..f799afe)
Task 4: complete (commits f18c806..f799afe, review clean after 1 round)
- R10: template global `policyLayout()` takes no args (bound to the Policy module); `policyTree(policy)` takes a policy dict — carry into Task 9 — none.
Task 5: complete (commits f799afe..f0b6815, review clean). Minor deferred: no parity test policyLayout vs do_get_policy before removal (Task 9 should keep structure equivalence in mind); black line lengths in tests.
- R11: lib files must be black-clean (repo autoblack runs `black --exclude="setup.py|tests/*" --check .`); black installed at /root/venv/bin/black. Views.py currently not black-clean → Task 8 dispatch runs black on Views.py/HTTPControl.py — none.
- R12: surplus formatters show 0 / Watt / 0.00 when generation ≤ consumption (Modern previously left the last value standing) — plan text "0 when not positive"; fixes a stale display — none.
Task 6: complete (commits f0b6815..06a7a94, review clean). ⚠️ items verified: chargingSince None when ≤0; lastOutcome provider/at mapped; detail always str. Minor deferred: resolved() throws if data-literal missing (Task 9 must always emit it).
Task 7: complete (commits 06a7a94..c70fd35, review clean). Agent a180edfa2c8084efc owns follow-up.
Task 7: FOLLOW-UP PENDING (run once Playwright installed in scratchpad/livejs-check): browser check of DOM paths (harness at scratchpad/livejs-check/run.js) + minors 1 (isolate non-formatter throws: missing template, bad class token, drawVehicleImage throw), 2 (fetch timeout via AbortController ~2x interval), 3 (unknown/throwing row formatter: leave rows untouched even for empty arrays), 6 (once-guard "update failed" log). Minor 5 (reorder moves) deferred.
- R13: `.live-offline` notice CSS owned by Task 8 (add to lib/TWCManager/Control/static/css/styles.css; Modern also loads it? check). Server-rendered keyed entries must emit data-key = item.key ?? item.id exactly; <template> single root; data-list row formatter receives ctx.item = row.
- R13 amended: the two themes load different stylesheets, so live.js styles the `.live-offline` notice itself via el.style (part of the Task 7 follow-up), not Task 8 CSS.
- R14 (plan-mandated finding, Task 8): scan-blocked text must show only when !canScan && scanBlocked (old either/or) — spec "today's text" beats plan's data-show — none.
Task 8: minor (deferred/accepted): spacer <td>&nbsp;</td> columns dropped in data-list tables (data-list contract); totalkWh whole floats print "12" not "12.0" (JSON, same as R-pyStr); data-show elements hidden until first poll.
Task 8: fix round 1/5 (2 addressed, 0 open — scan-blocked either/or; ble null guards; commits 9801949..f8eca00)
Task 8: complete (commits c70fd35..f8eca00, review clean after 1 round)
Task 9: complete (commits f8eca00..a84ae05, review clean). Minor deferred: no test for ext-block policy's hook index / nested group truth hook. Re-read race moot (charge_policy changes only on restart).
Env: Playwright for Python + Chromium installed (/root/venv/bin/python, `from playwright.sync_api import sync_playwright`; chromium.launch() works). No npm/node playwright. Task 7 follow-up runs after Task 10 completes (no parallel implementers).
Task 7: follow-up round complete (commit 2bea435..1afe74d; minors 1,2,3,6 + R13 addressed; 36/36 Chromium harness checks at scratchpad/livejs-check/run.py). 404 loop moot: unknown-VIN page doesn't start live.js.
- R15 (plan-mandated findings, Task 10): Amps Offered rounded like round(x,2) via new Format.round2; Default Max Amps shows .gen2.maxAmps for Gen2 rows (matches Total), .maxAmps otherwise; car-only rows show .vin (spec: "the car it serves"); Modern volts rounded — spec "today's text" beats plan hook choices — none.
Task 10: minor (accepted): uppercase twcid label; "(Flex N)" now visible; Modern heading pluralises; "Last SoC" line gone; unknown limit shows "%"; Modern policy buttons neutral until first poll; duplicated server-time block in both jsrefresh hooks.
Task 10: fix round 1/5 (4 addressed, 0 open — round2 offered, gen2 max amps, car-only VIN, Modern volts; commits 1afe74d..f0519d1)
Task 10: complete (commits a84ae05..f0519d1 excluding 1afe74d, review clean after 1 round)
Task 11: fix round 1/5 (5 addressed (docs) — re-review running in parallel with final review; commits 64ab10a..265a887)
Task 11: complete pending re-review (commits f0519d1..265a887). Pre-existing, out of scope: fresh install without settings.json → /vehicles UndefinedError (VehicleGroups missing; also on base); Modern commonUI.js tooltip error (double jQuery + Bootstrap 5).
Task 11: complete (commits f0519d1..265a887, review clean after 1 round; minor: one unwrapped doc line)
Final review (opus, f094c7c..265a887): With fixes. #1 Important: vehicles.html.j2 hook paths use registry key; anon Gen3 key "anon:Gen3TWC-<ip>" contains dots → blank row. #2 Max Amps float noise (round2). #3 getChargingPoints.md `total` overstated. #4 stray </div> in policy.html.j2. #5 redundant ble *Age fields — Ruling: leave (harmless, documented pass-through of bleStatus) — cost: API clutter.
Ledger triage by final reviewer: no deferred item blocks merge.
Final fix wave: commits 265a887..379af8e (ce61cb6, 379af8e); re-review: all 4 addressed, no new Critical/Important.
Final: parked — history entries carry `key`, so an all-digit settings Vehicles key could shadow a positional index in live.js step() — Ruling: code stands; real keys are VINs (17 chars) — cost if wrong: one history cell misrouted.
