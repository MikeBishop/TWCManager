# Design audit: why is the vehicle-model stack 3,400 lines bigger than main, and what can go?

User goal (standing): the rearchitecture must make the code simpler and smaller. Lib growth is a red flag; find
duplication; never loosen the check. The user accepted the overage "for now", expecting Phases 4–5 to shrink it; Phase 5 is
instead heading up. User approved this audit before Phase 5 Tasks 4–6 (2026-10-19).

## Trees (read-only; do not modify either)
- Stack tip: `<scratchpad>/wt-audit` (detached at 2e6070f9 = main 03d79325 + Phases 1, 2, 3, 3.5, 4 + Phase 5 Tasks 0–3).
  `lib/` = 26,568 lines (`find lib -name '*.py' | xargs cat | wc -l`).
- Main: `<scratchpad>/wt-main` (detached at 03d79325). `lib/` = 23,180 lines.
- `<scratchpad>` = /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad
- Design: `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/specs/2026-10-13-vehicle-model-design.md`
  (the spec; the Vehicles tab section is now reduced, see its 2026-10-18 note).
- Remaining Phase 5 work (so you don't recommend cutting what's about to be built, and so you can say where it should live):
  `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/plans/2026-10-18-vehicle-model-phase5-presence.md`
  Tasks 4 (Gen2 unplug filters on TWCSlave), 5 (VIN-less attribution), 6 (Vehicles page presence + pending commands).

## Hard constraints (never recommend violating)
- Never cut Gen3 features (Gen3 is most deployed Wall Connectors).
- No new paid Tesla calls; never keep cars awake; no polling.
- Behaviour users rely on stays (check CHANGELOG 1.4.0 and the PR descriptions in
  `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/pr-drafts/` for what each phase promised).
- Features deliberately dropped are already dropped (6 A spike workaround, flex, Track Green dampening, manual-change adoption except limits).

## What to produce
1. **Where the growth is.** Per-directory/module table: main lines vs stack lines vs delta, for every module that differs by
   ≥ 50 lines (new modules included). Count with the same `cat | wc -l` measure.
2. **Structural findings, ranked by lines saved.** Look for, at minimum:
   - two mechanisms doing one job (old path kept alongside the new one: e.g. per-module presence/plug/home logic vs Presence;
     per-provider command code vs Reconciler; TWCMaster/TWCSlave helpers the distributor or ChargingPoint replaced; settings
     shims and migrations; VehiclePriority-era façades; CarApi leftovers; legacy config paths read alongside new ones);
   - abstraction layers with one implementation or one caller (classes/protocols/registries that a function would replace);
   - parallel provider modules (TeslaBLE/TeslaAPI/HomeAssistant/Telemetry/Gen2/Gen3 providers) repeating the same claim,
     capability, observe or outcome boilerplate that a shared base or table would collapse;
   - data carried twice (settings + registry, attachment + vehicle fields) with sync code between;
   - dead code: unused functions, constants, branches no config reaches (grep callers; tests alone don't count as callers);
   - long docstrings/comments restating code (lowest priority; count separately).
   For each finding: files:lines, what to merge/delete, estimated lines saved, behaviour risk (none/low/medium), test impact,
   and **which phase introduced it** (so it can land on the right branch: findings in Phase 5 code are cheap; findings in
   lower phases mean restacking open PRs #703–#706/#710 — say so).
3. **A recommended cut plan**: the set you'd take now, grouped into 2–5 implementable tasks (each with files, approach,
   expected Δ, tests to keep green), plus a realistic target for Phase 5's end state vs main.
4. **Guidance for Tasks 4–6**: how each can be built at ≤ 0 net (what existing code each should replace).

Be concrete and verify each claim in the code (grep for callers before calling something dead). Estimates must be
line counts you can defend, not percentages.

## Output
Write the report to
`/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/sdd/2026-10-18-vehicle-model-phase5-presence/audit-report.md`.
Reply with ONLY: the total achievable saving, the top 5 findings (one line each), and the report path.
