# Task X1: package re-exports (audit A1, ≈ −67)
Source of truth: /home/mbishop/github/TWCManager/.claude/worktrees/ble-threading-twcmanager-62cb96/.superpowers/sdd/2026-10-18-vehicle-model-phase5-presence/audit-report.md, finding **A1** (read that section; verify every claim by grep before acting).
- Empty Vehicle/Reconcile/__init__.py, Vehicle/Registry/__init__.py, Vehicle/Providers/__init__.py (leave each file present, empty or a one-line comment only if the repo convention needs one).
- Fix the two TWCMaster imports to import from the submodules.
- Move Order.py's lazy `Attempt` import to the top once the cycle is gone (verify the cycle is gone by importing TWCManager.TWCMaster in a fresh interpreter).
- Fix any test or lib import that used a package re-export (grep `from TWCManager.Vehicle.Reconcile import`, `...Registry import`, `...Providers import`).
Base: branch vehicle-model/phase5 in the wt-vm5 worktree. No behaviour change: tests/unit + tests/EMS stay green; tests/unit/test_command_path_parity.py counts and timings untouched. Comment rule applies (why, not history; no phase/PR/ruling IDs). Report the lib delta (git diff --shortstat <BASE> -- lib, net) against the estimate; if you can't reach the estimate, say which item fell short and why.
Commit: "Drop package re-exports nobody imports"
