# Docs refresh for 1.4.1 (post-Phase-6 PR)

## Context

TWCManager (github ngardiner/TWCManager) is getting a vehicle-model rework. Phases 1–3.5 are merged into `main` and shipped in 1.4.0 along with Gen3 support. Phases 4, 5 and 6 are open PRs that stack: #710, then #725, then #726. All of it targets **1.4.1**.

The worktree is `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-docs`, on branch `docs/1.4.1`. It is based on `vehicle-model/phase6` (d004b603), the code the docs must describe. This becomes a separate PR stacked on #726.

Source of truth, in order:
1. the code at this tip (`lib/TWCManager/...`, `etc/twcmanager/config.json`, `setup.py`/requirements, Dockerfile and compose files);
2. `CHANGELOG.md` (the v1.4.1 Upcoming and v1.4.0 sections say what changed and when);
3. the existing docs.

When code and docs disagree, the code wins. When you can't tell from the code, say so in the report rather than guess.

## Task

### 1. Audit, then write the gap list

Read `README.md`, `docs/README.md` and every file under `docs/`, including `docs/modules/`. Skip `tests/*.md`. For each doc, check it against the code and list the gaps:
- **Stale:** statements no longer true. Removed settings, changed defaults, removed behaviour (for example the Tesla API's deferral ladder and `cloudUpdateInterval` no longer setting the vehicle read cadence, `/api/checkArrival` and `/api/checkDeparture` now answering 404, the `atHomeRadius` default), old setup steps, wrong requirements.
- **Omitted:** pertinent things missing. Examples:
  - Gen3 Wall Connectors, and Gen3-only installs with no Gen2/RS-485;
  - BLE (TeslaBLE), TeslaMate, Fleet Telemetry, Home Assistant, Owner API vs Fleet API;
  - the vehicle watch (the `watch` config block);
  - the Vehicles page;
  - presence and home learning;
  - Docker BLE needs;
  - running with modules disabled.

Write the gap list to `/home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/sdd/2026-10-20-vehicle-watch/docs141-gaps.md`, grouped by file, with one line per gap and the code reference that proves it (`path:line`).

### 2. Fix the docs

**The framing the user wants, which the README and docs/README must lead with.** TWCManager supports any combination of chargers and car connections. Any one is sufficient, and more gets better. Recommended: at least one **command path** and one **telemetry source**. Build this around three groups:
- **Chargers TWCManager controls:**
  - Gen2 TWC over RS-485;
  - Gen3 Wall Connector over its local API.
- **Command paths to the car:**
  - BLE (TeslaBLE, free, local);
  - Tesla Owner API;
  - Tesla Fleet API (paid per command).
- **Telemetry sources:**
  - TeslaMate;
  - Fleet Telemetry;
  - Home Assistant;
  - the Tesla API's own reads;
  - BLE reads.

Also cover what each adds and what you lose without it. For instance:
- No charger: the car's own charge rate is commanded, and the vehicle watch covers it.
- No telemetry feed: the watch polls cheaply.
- No command path: TWCManager can only offer amps at a TWC.

Get these facts from the code (`Vehicle/Providers`, `Vehicle/Watch.py`, `Vehicle/Presence.py`, `Settings.md`), not from this brief. A small table or matrix is welcome if it reads well.

**Version notes.** Mark where support arrived, e.g. "Gen3 Wall Connectors (1.4.0)", "Gen3 without a Gen2 TWC (1.4.1)". Derive each from the CHANGELOG sections and the git history (`git log --oneline origin/main` vs the stack). 1.4.0 = what is on `origin/main` up to the 1.4.0 tag (`git tag -l 'v1.4*'`); 1.4.1 = Phases 1–6 (Phase 1 is on main but landed after the tag; check this). Don't mark old long-standing features. Mark only what is new in 1.4.0 or 1.4.1.

**Scope of edits.**
- Fix every stale statement you listed.
- Add the omitted items where a reader would look for them.
- Keep each module doc's existing structure.
- Don't rewrite docs that are still correct.
- Don't duplicate `Settings.md` content elsewhere; link to it.
- Add a v1.4.1 CHANGELOG line under Documentation (or the nearest existing category; check how the file categorizes).

**Commits.** Use logical commits, e.g. (1) the README and docs/README framing, (2) the stale fixes per area, (3) the new sections. Write messages in the repo's style, ending with:

    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## Style

- Plain, direct, present tense. Describe what is, never "used to" or "now" history (the CHANGELOG holds history). The "(1.4.1)" version markers are the one exception.
- Write for an installer, not a developer of TWCManager.
- No internal IDs: no phase numbers, PR numbers, or ruling names.
- No personal data: no VINs, coordinates, car names, or tokens. Use placeholders like `5YJ3E1EA1KF000000`.
- Match the existing Markdown conventions in each file.

## Don't

- Don't push. Don't touch code under `lib/` or tests (a doc-only PR). If you find a code bug, note it in the report.
- Don't modify .gitignore. Never use bare `git stash`.
- Don't spawn subagents. The `advisor` tool is available if you get stuck or want a check before finishing.

## Report

Write `docs141-report.md` next to the brief, covering:
- the commits;
- the files changed;
- any gaps you left unfixed and why;
- any code bugs found;
- the version markers you added, with the evidence for each.

Return only: status, commit list, a one-line summary, and concerns.
