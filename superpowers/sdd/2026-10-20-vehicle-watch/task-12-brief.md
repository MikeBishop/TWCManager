# Task 12: One presence rule for cars only the Tesla API can see

The user approved this on 2026-10-21: "Approved, go ahead and build it."

The spec is the section "Addendum 2026-10-21: one presence rule for cars only the Tesla API can see" at the end of `.superpowers/specs/2026-10-20-vehicle-watch-design.md`. Read it in full. It is the requirement, including the user's two later decisions written into it: BLE installs make no cloud presence polls, and paid charging reads are kept to a minimum.

Base: vehicle-model/phase6 at b613a784 (Phase 6 rebased on the fixed Phase 5). This branch will be squashed afterwards, so delete the replaced paths outright. Nothing old should stay alive next to the new rule.

## Build
1. **API-only watched cars.** A car is in this class when it is watched, has a Tesla API attachment, and no BLE detector is usable: TeslaBLE isn't loaded, or `canScan()` is False and pings can't run. Pick the predicate from what the code exposes and state it in the report. These cars follow the addendum's rule:
   - Poll status outside a deferral, using the asleep and awake cadences.
   - Do one event read (charge state and position) on the asleep→awake edge anywhere, and whenever the car is awake with its last fix older than max(return time from that fix, sleepCourtesySecs).
   - Defer everything for that car until fix time + return time. Home counts as a return time of 0.
2. **Delete what the rule replaces:**
   - the away-location read (`_locate`), its once-per-awake-stretch bookkeeping and the driving re-read;
   - the cloud status checks for a car Bluetooth has lost in a BLE install.

   BLE installs use the scan back-off alone for arrival, and poll the cloud only while a Fleet command is held. Phase 5's hold check runs for unwatched cars. For watched cars the watch's status checks serve the hold, so make sure a BLE install still polls the cloud for a held Fleet command, at the hold's cadence, and at no other time.
3. **Charging reads:**
   - Free reads (BLE, Owner) keep `chargingReadSecs`.
   - Paid routine reads (Fleet) happen only when a policy condition reads that car's battery, at `cloudChargingReadSecs`. Find how policies reference `minBatteryLevelAtHome` or battery, and make the check a cheap, cached predicate.
   - The TWC-named read while current flows follows the same split.
4. **Keep everything else as it is:**
   - the BLE paths (ping and door, scans, back-off, lost car);
   - the consumption step;
   - the budget;
   - TWC-named cars;
   - restart seeding;
   - courtesy;
   - readNow;
   - Phase 5's rules.
5. **Docs:** update `docs/Settings.md` (the watch section and cadence table) and `docs/modules/Vehicle_FleetTelemetryMQTT.md` (Fleet Telemetry is recommended as the cheaper option, and API-only works), plus the CHANGELOG watch entry, to match the code.

## Tests (each must fail without its rule; mutation-check them)
- **API-only:**
  - an edge read on wake at home and away;
  - an awake car read once per courtesy window at home;
  - an away read deferred until the return time; a 3-hour fix means 3 hours with no request of any kind;
  - an awake car past its return time read and found home;
  - a departure while awake seen within one courtesy window.
- **BLE install with the API:**
  - no cloud status checks for a lost car;
  - a held Fleet command still gets its check at the hold cadence, and only while held.
- **Charging reads:**
  - Fleet-only, no battery policy: no routine charging reads, and the finish is learned from sleep;
  - Fleet-only with a battery policy: reads every `cloudChargingReadSecs`;
  - free reads unchanged.
- **Parity:** `tests/unit/test_command_path_parity.py` counts must not move. If one does, stop and report it.

## Constraints
- Never wake a car to observe it. Never keep a car awake. Paid reads go through the budget, event class for edges.
- No I/O on the tick. Lock order is unchanged.
- Python 3.8. Run black.
- Comments say why the code is what it is; no history, no phase, task or ruling IDs.
- Watch.py should shrink. Report lib lines and Watch.py lines before and after (BASE lib 27036).
- Full suite: `timeout 900 systemd-run --user --scope -q -p MemoryMax=2G /tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python -m pytest tests --ignore=tests/API --ignore=tests/integration -q --timeout=60 -p no:cacheprovider`. BASE is 2377 passed, 1 xfailed.
- One commit: "Read a car only the Tesla API can see on its wake, and not again before it could be back", ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Don't push. Never bare `git stash`.
