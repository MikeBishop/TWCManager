## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `tests --ignore=tests/API --ignore=tests/integration`.
  - BASE: **1954 passed, 1 xfailed** (on 57dcea94). The full suite passes after every task.
- **Behaviour changes allowed: only these.** Each is named in its task with its test; anything else is a defect. Where none is listed, BASE is kept (F11).
  - (a) **Presence from events** (Task 2): HOME, PRESUMED or NOT_HOME, as defined in Task 2. HA's zone state `"home"` without coordinates is no longer a location.
  - (b) **Send-time applicability** (Task 3, the table). A PRESUMED car with a real message may be woken and read on the paid path, close to main. This reverses phase4, where a car with no position and no hold got nothing.
  - (c) **A plug-in is a decision for that car only** (Task 3). `onArrival(master, vehicle)` is called once per plug-in event, by `noteObservation` or by the TWC paths. BASE's `checkArrival` re-decided every present car.
  - (d) `/api/checkArrival` and `/api/checkDeparture` answer 404 (Q9). The PR notes call it out. The internal 5/20/45-minute `checkDeparture` reads stay (Q6). The power start's `updateChargeAtHome` stays (F11), now queued as `checkCharge`.
  - (e) `atHomeRadius` defaults to 1,000 ft instead of 10,560; explicit values win; changelog line (Task 2).
  - (f) Home is never seeded from a first fix. It moves only from a car a TWC names whose registry fix is under 600 s old (Q5). The paid `update_location(v, 0)` goes (Task 2).
  - (g) A Gen2 plug session (`twcVin`) ends at the filtered unplug, not 5 s after charging stops (Q2, Task 4). `twcVin` is home evidence only while bounded by F2 (Task 2).
  - (h) VIN-less fan-out drops `vehicles[0]` (Q1). Gen3's guess goes through the same attribution, with BASE's single-car guess kept (Task 5).
  - (j) A car HOME and plugged here, with a ready `SET_AMPS` provider, gets a VehicleEndpoint, whichever module knows it (E2, Task 3).
  - (k) **Apply before the plug** (Task 3): a HOME, unplugged car with no departure seen, or with arriving newer than leaving, gets the policy limit. A car that never left, unplugged for hours, is not re-applied.
  - (l) **Near-home false positives narrowed** (Task 2): a fast charger, no cable, or charging power above the car's own AC maximum is not plug evidence.
  - (m) **Logging** (Tasks 1, 3, 4).
  - **Not changed, per F11:**
    - the away-car `statusDeferral` ladder (Q7's single value is withdrawn);
    - `updateChargeAtHome` at power start;
    - the broadcast audience (only cars BASE reached);
    - HA's "at home and on a TWC" broadcast rule;
    - `lastAtHome`, True only for HOME.
  - **Unchanged by design, each pinned by a test:**
    - held limits in settings `chargeLimits {VIN: [outside, held]}`, where absence means nothing is held;
    - never write a limit whose current value is unknown;
    - only the charge limit is adopted;
    - rate before start;
    - Gen3's cloud VIN wins;
    - a restore never wakes;
    - no read is made just to learn presence.
- **Not in scope:**
  - the fingerprint (T13), polling, the `bleSilent` exception (Q3), D2, #709, and the Vehicles tab;
  - Q7's single `statusDeferral`, which F11 withdraws.
- **Cost.**
  - Prices: `vehicle_data` $0.002, wake $0.02, command $0.001. Lists, `vehicles/{vin}` and `live_status` are free.
  - No task adds a paid request except where (b) resolves a PRESUMED car that phase4 treated as absent. Each such row is new and states its paid tuple.
  - **Existing `tests/unit/test_command_path_parity.py` counts and timings are not edited.** Traced in planning: rows 2, 4, 5, 6, 17a/b, 25 and 26, the pure-Gen2 row, the anonymous fan-out row and the mode-2 rows all keep their counts and timings under the Task 2/3 definitions. The trace is under "Parity rows traced".
    - The only edits are PLUMBING-ONLY:
      - `:1306` `api.locate(v)` → `presence(m, v) == HOME`;
      - the `realBle` ping stub (F5), which records pings in `b.pings`, not `b.runs`.
    - If any count or timing moves, stop and report (F1 rule).
  - Attribution reads never use TeslaAPI and never wake.
- **Gen3 stays whole:** the fake-Neurio solver, `WallConnectorVins`, cloud VIN, vitals `pluggedIn` writes, and the single-car guess (F12).
- **Policies, templates, `/api` fields keep working.**
  - `numCarsAtHome`/`minBatteryLevelAtHome` (TeslaAPI and HA) stay as properties, counting HOME and PRESUMED (R21).
  - `/api/getSlaveTWCs` `lastAtHome` is True only for HOME (F11).
- **Threading.**
  - Lock order unchanged: `TeslaBLE._bleLock → master.settingsLock → registry leaf`, and `TeslaAPI.vehicleListLock → settingsLock`.
  - No I/O under any lock. No RS-485 I/O off the serial thread.
  - `noteObservation` runs on the observing thread, after the store and outside the leaf lock. It reads `master.settings` home lat/lon without a lock (two floats), and writes marks max-merged under the vehicle leaf lock.
  - `noteObservation` uses the incoming observation's own value and time, never the kept one: `FieldStore._store` returns the kept observation when an older stamp arrives.
  - `onArrival` from the MQTT thread takes the Desired lock, then settings; no inversion.
  - The serial thread owns the slave's unplug state.
- **Grep scope for removed names**, every task: `git grep -nwE '<names>' -- lib html tests/unit tests/integration tests/API docs`.
- **Deleted-test rule.** Each task report maps every deleted or rewritten test to a replacement, PLUMBING-ONLY with the reason, or INTENTIONALLY CHANGED with its letter. The per-group fates of the presence-branch tests are in Task 6 (F18).
- **Test plumbing must not move a paid count** (F1). Row 26 (:1206) in particular: stop and report.
- **Line reporting** per task:
  - before and after `git ls-files lib | grep '\.py$' | xargs cat | wc -l`;
  - `git diff --shortstat <task BASE> -- lib`;
  - actual vs expected.
  More than 25 over: stop and report.
- Python 3.8; `black` on touched files only; commit trailer per the session's reminder.
- **Real objects in cross-module tests:** a real `TWCMaster`, `Gen2TWC`, `VehicleRegistry`/`DesiredStore`, `teslatokens.new_api` and `requests_mock`. Never mock a success value the real method never returns.

### Comment rule (user, 2026-10-17; binds every task)
Code must read as if it were designed this way from the start. Comments explain why the code is what it is — not how it used to be, when or why it changed, which review or ruling prompted it, or the many things it isn't. Mention an alternative only where the obvious approach isn't the right one. History goes in commit messages and PR descriptions. Keep comments short.
No phase names, PR/issue numbers, or review/ruling IDs (Q1, R14, (d) …) in code comments.

