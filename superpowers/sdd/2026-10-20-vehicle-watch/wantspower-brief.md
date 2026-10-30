# A plugged-in car the power split ignores is never started

## The bug (live box, 2026-10-27 00:00)

The box runs TWC-less: the TWC is held at 48 A by a separate fake master, so for the real install the car is on an EVSE TWCManager doesn't control. The car is controlled car-side over BLE, with the Owner and Fleet APIs, and TeslaMate provides telemetry.

At 00:00 the Scheduled Charging policy started and wanted a higher charge limit. The car was asleep, had finished its previous session at its old limit, and was presumably at chargingState "Complete". The log shows `chargeLimit setChargeLimit ... via TeslaBLE: satisfied rules: held: asleep`, and nothing woke it. At 00:12 the user woke it by hand; the log then shows `TeslaBLE no wake ... before setChargeLimit: nothing offered`, the limit went through, and charging began.

This is a deadlock:
1. `VehicleEndpoint.wantsToCharge` (lib/TWCManager/EVSEInstance/VehicleEndpoint.py) is true only for chargingState "Charging" or "Stopped".
2. `TWCMaster.distributeEVSEPower` budgets only points that want to charge. Every other point gets 0, so `master.offered[car] = 0`.
3. `Belief.whyQuiet` (lib/TWCManager/Vehicle/Reconcile/Belief.py) says "nothing offered", so no wake is allowed for the limit raise or a start.
4. The car never wakes, so it never reports anything that would make it want to charge.

## The wider question (the user's)

> I also wonder if this represents a larger issue, where the distributor ignores cars that aren't actively charging, but then the distributor's failure to allocate them power causes them not to begin charging.

Answer it.

Audit every `wantsToCharge` (`Gen2TWC`, `Gen3TWC`, `VehicleEndpoint`, `ChargingPoint`) and everything that consumes it or `master.offered`: the distributor, `whyQuiet` and other wake/start gates, `controlPass` and the Gen2 `chargeGate`, `num_cars_charging_now`, and the watch.

For each EVSE kind, find whether a car that is plugged in but not currently drawing can be stuck the same way:
- asleep;
- at its limit ("Complete") with a pending raise;
- "Stopped" by us earlier;
- at 00 on a Gen2;
- a Gen3 in `complete`.

Note that `Gen3TWC.wantsToCharge` also excludes "complete". `Gen2TWC.wantsToCharge` needs `reportedAmpsMax > 0`, which a sleeping car may not report. The command-path parity file has rows about a sleeping car at 00 being woken for a raise "with 32 A to share", so check how Gen2 escapes this, if it does.

## Fix

**Intent:** "wants power" means a plugged-in car that would take power once the desires TWCManager is applying land. It does not mean only a car currently charging. Specifically:
- **Wants power:** a car plugged in here (`Presence.pluggedHere`/`pluggedNow`), whose effective limit (the pending desired limit, else held, else believed, the same resolution `whyQuiet` uses) is above its battery level, or unknown, and with no stop desired.
- **Does not want power:**
  - a car at its limit with no raise pending;
  - a car TWCManager wants stopped;
  - an unplugged car;
  - a car away from home.

The budget must not be handed to cars that won't take it.

Fix it at the level that covers every EVSE kind the audit finds affected. Prefer one shared rule over a separate patch per class: `ChargingPoint.wantsToCharge`, or a helper beside `whyQuiet` that both use, is a natural place. Do not duplicate `whyQuiet`'s limit logic; factor it so both share it.

Keep these existing behaviours:
- an idle Gen2 still gets its hardware minimum;
- a car asleep after "Charging" (finished) is still not counted;
- a car with no command path (read-only) gets no budget.

Also check `num_cars_charging_now` and any fair-share split. Allocating to a car that just woke and then won't charge must self-correct within a cycle or two, and must not starve a car that is charging.

## Tests

Write each test first and watch it fail:
1. **Replay of last night, car-side endpoint:**
   - setup: plugged in at home, asleep, chargingState "Complete", battery 70, limit 70, BLE provider able to set amps;
   - action: the policy wants limit 90 and amps available;
   - expect: offered > 0, `whyQuiet` None, and a wake allowed before the limit and start commands.
2. **The same car with no raise pending (limit 70):** offered 0, no wake.
3. **The same car with a stop desired:** no wake.
4. **Each other EVSE kind the audit finds affected:** a test of the same shape.
5. **A charging car and a "Complete" car with a raise sharing a limited budget:** both get a share, and once the second is found quiet it drops out.

## Constraints

- **Branch and base:** work in worktree `/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-fix`, branch `fix/car-side-wants-power`, based on `origin/vehicle-model/phase6` (1a0b7d67).
- **Commits:** commit the fix as one or more new commits on top. Don't push or rebase.
- **Running tests:** use the venv at `.../scratchpad/venv`:
  `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G <venv>/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`.
  Check pytest's exit code. Baseline: 2,459 passed, 1 xfailed.
- **Parity:** the paid counts in `tests/unit/test_command_path_parity.py` must not move. If a row's free counts move, explain each one in the report. If a paid count moves, stop and report.
- **Code style:**
  - Python 3.8 compatible.
  - Run black on touched code only, not whole files.
  - Comments say why the code is what it is; no history, and no phase or PR IDs.
- **Size:** lib lines should not grow much. Find what to share rather than add parallel logic.
- **Changelog:** add a CHANGELOG line under v1.4.1 Bugfixes, user-facing: e.g. "A plugged-in car at its old charge limit, on a charging station TWCManager doesn't control, is woken and started when a policy raises its limit."
- **No subagents.** The `advisor` tool is available if stuck, or for a check before finishing.
- **No personal data:** never print a VIN, coordinates or the car's name.

## Report

Write `wantspower-report.md` next to this brief, covering:
- **the audit:** per EVSE kind, whether it is affected and the evidence (`path:line`), and how Gen2 escapes if it does;
- **the fix and why it lives where it does;**
- **the tests**, with fail-before and pass-after;
- **suite counts, parity, and lib line delta.**

Return only: status, commits, a one-line audit answer, and any concerns.
