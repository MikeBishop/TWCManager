# Common context for every task (read after your brief)

Project: TWCManager (Python 3.8+). Feature: Fleet-only charge history backfill.
Spec (binding authority; read only the sections your brief cites):
/home/mbishop/github/TWCManager/.superpowers/specs/2026-11-01-fleet-charge-backfill-design.md

Work ONLY in: /home/mbishop/github/TWCManager/.claude/worktrees/fleet-backfill
(branch feat/fleet-charge-backfill). Never cd to the main checkout.

## Running tests (important)

The shared .venv imports the main checkout's code unless PYTHONPATH points here. Always:

    PYTHONPATH=lib .venv/bin/python -m pytest -q <paths>

Full suite (once, before committing): 

    PYTHONPATH=lib .venv/bin/python -m pytest -q --ignore=tests/API --ignore=tests/integration

Never run bare `pytest` (tests/API and tests/integration need a live instance and stall). Baseline: 2585 passed, 1 xfailed (~5 min).

## Global constraints

- No new dependencies.
- Fleet-only means: a watched car whose charge readings come from the cloud: `Watch.cloudOnly(master, v)`, or a BLE car the radio has lost that the watch reads through the cloud. Cars reported live (TWC, Gen3, a feed, BLE in range) are unchanged.
- Never wake a car to poll; never poll a car believed asleep.
- No paid read for detection. The courtesy/location read (`late`/`fix` in `Watch._visit`) and the reconciler's pre-write reads are unchanged.
- Never invent energy: missing evidence ends a session at its last `Charging` snapshot.
- Battery -> wall efficiency: 0.93.
- Comments say why the code is as it is, never its history or what changed. Match surrounding comment density and naming (camelCase in this codebase).
- Tests match the dense style of tests/unit/test_watch_load_step.py and tests/unit/test_watch_cached.py; reuse their helpers (setup, placeAt, runPending, apiOnly, chargingFleetCar, later, passes, snapshotAt, counts, paid, FLEET, VIN).
- Library growth small: share code, remove paths the task retires, never duplicate request/parsing logic.
- Gen3 behavior must not regress.

## Commits

Small commits with the message the brief gives. End every commit message with:

    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Never push. Never touch .superpowers/ files except your report.

## Help

An `advisor` tool may be available; call it only if you are stuck.
