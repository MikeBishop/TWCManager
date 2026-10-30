## Global Constraints

- **Pytest** (every run, verbatim):
  `PY=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/venv/bin/python`
  `timeout 300 systemd-run --user --scope -q -p MemoryMax=2G $PY -m pytest <targets> -q --timeout=60 -p no:cacheprovider`
  - The full suite is `tests --ignore=tests/API --ignore=tests/integration`.
  - BASE: **1868 passed, 1 xfailed** (run during planning). The full suite passes after every task.
- **Behaviour changes allowed: only these.** Each is named in the task that makes it, with its test. Anything else that changes is a defect.
  - (a) The 6 A spike workaround is dropped (user, 2026-10-17). The Phase 4 PR body must call this out for the maintainer, who may disagree. The `spikeAmpsProactively`/`spikeAmpsReactively` settings are then ignored.
  - (b) Installs with `vehicle.TeslaAPI.enabled: false` move from the legacy per-slave fair share to the one distributor (Decision 2). Every other install already runs the distributor at BASE, because TeslaAPI is enabled by default (`TeslaAPI.py:198`) and that registers `VehicleEndpoints`.
  - (c) **Flex is not ported** (user, 2026-10-17). `greenEnergyFlexAmps`, `useFlexAmpsToStartCharge` and a policy's `allowed_flex` are still read without error but ignored. On the default path flex was already zeroed whenever the distributor set a target (`TWCSlave.py:776`, since #483), so only TeslaAPI-disabled installs lose it (Decision 3).
  - (d) Gen2 target lag of up to one tick (~1 s), and the distributor runs once a second instead of once per full heartbeat round (≈ N × 1.1 s). The spec accepts it. As at BASE, nothing is distributed while no Gen2 slave is known (`countSlaveTWC() > 0`, `TWCManager.py:923`; ruling F2): Gen3-only and vehicle-only installs keep BASE's behaviour.
  - (e) The wiring cap is re-checked on every offer, not only when the offer changes (Decision 5).
  - (f) **Track Green dampening is not ported** (user, 2026-10-17). It held a drawing car at `minAmpsTWCSupports` for `startStopDelay` after its share crossed the minimum. On the default path it was mostly defeated at BASE: `Gen2TWC.setTargetPower` writes `lastAmpsDesired = target` every pass (`Gen2TWC.py:225`), so the flip check mostly compared the target with itself. The flip tracking (`lastAmpsDesired`, `timeLastAmpsDesiredFlipped`), the dampen rule and that compat write all go (Task 4). `startStopDelay` stays: the start/stop gates use it (Task 5) (Decision 9).
  - (a), (c) and (f) form the PR body's **"Not ported into the rearchitecture"** section (Task 6, Step 6).
  - Charging on/off and amps are never adopted from manual changes (spec amended). Nothing in this phase adds adoption.
- **Not in scope:** two-pass admission (#709), presence (Phase 5), the Vehicles tab (Phase 6) and any RS-485 protocol change (spec non-goal).
- **Cost.**
  - Prices: `vehicle_data` $0.002, wake $0.02, command $0.001. Lists, `vehicles/{vin}` and `live_status` are free.
  - No task may add a paid request.
  - `tests/unit/test_command_path_parity.py` request counts are not edited. Its three `s._evseTargetAmps` assertions (lines 892, 897, 1082) become `s.offer.amps` (PLUMBING-ONLY; the values 6, 10, 10 stay).
- **Gen3 stays whole:** the fake-Neurio solver, `WallConnectorVins`, `_correlate` and cloud VIN. Gen3 changes only its base class (Task 6).
- **Policies, templates, `/api` fields keep working.**
  - `Policy.policyValue` reaches module attributes by name. `master.allowed_flex`/`getAllowedFlex`/`setAllowedFlex` go with flex (c): no shipped policy, template or doc reads them through `policyValue`, and a policy dict's `allowed_flex` key is simply no longer read.
  - Old `config.json`/`settings.json` keys (`greenEnergyFlexAmps`, `useFlexAmpsToStartCharge`, `spikeAmpsProactively`, `spikeAmpsReactively`) load without error and are ignored; Task 6's `test_retired_settings_keys_load_and_are_ignored` pins it.
  - `/api/getSlaveTWCs` keeps `lastAmpsOffered` and `lastChargingStart`.
  - The status keys `amps_offered`, `amps_desired` and `cars_charging` keep publishing.
  - `WebIPCControl` keeps `lastAmpsOffered`.
- **Threading.**
  - Lock order: `TeslaBLE._bleLock → master.settingsLock → registry leaf`, and `TeslaAPI.vehicleListLock → settingsLock`.
  - New: `TeslaTokenSlot._cond` is a leaf. Nothing is acquired under it and no I/O runs under it.
  - No I/O under any lock. One exception is pre-existing and out of scope: `loadVehicleList` holds `vehicleListLock` across its list GET and refresh at BASE (`TeslaAPI.py:561`). Phase 4 does not widen it.
  - No RS-485 I/O off the serial thread.
  - Ownership after Task 4 (one writer each):
    - the **serial thread** writes `reported*`, `heardFrom`, `timeReportedAmpsActualChangedSignificantly`, `isCharging`/sessions/VIN state, `plugSessions` (a counter bumped at each session end), `historyAvg*` and `masterHeartbeatData`;
    - the **tick** writes `offer`, `pointAmps`, `lastAmpsOffered`, `timeLastAmpsOfferedChanged`, `liftedSession` and `_lastKeys`.
    - Exception (ruling F14): `Gen2TWCProvider.setAmps` (a reconciler lane thread) also writes `pointAmps` through `setTargetPower`. It is benign: the next pass overwrites it, and the offer is computed on the tick only.
    - `stopTimeout` already has two writers at BASE (getStatus/policy and the serial thread); after Task 5 they are the serial thread and the tick. No new exposure.
    - The once-per-session lift is `liftedSession == plugSessions`: the serial thread only counts sessions and the tick only records which session it lifted, so neither overwrites the other (replaces the two-writer `vehicleRateRaised` bool; Task 4).
  - `master.getSlaveTWCs()` returns a copy (Task 3). The tick never iterates the live round-robin list; Task 3 also points `WebIPCControl.processIPC`'s `getSlaveTWCID(i)`/`slaveTWCRoundRobin[i]` reads (:179–193) at that copy (ruling F15).
- **Grep scope for removed names**, run in every task: `git grep -nwE '<names>' -- lib html tests/unit tests/integration tests/API docs` (tests/unit included: ruling F11). Templates live under `lib/TWCManager/Control/themes`. Expect hits only in the definitions being removed.
- **Deleted-test rule.** Each task report maps every deleted or rewritten test to one of:
  - a replacement test;
  - PLUMBING-ONLY, with the reason;
  - INTENTIONALLY CHANGED, naming one of (a)–(f).
- **Test plumbing must not move a paid count** (ruling F1). If a plumbing change to a helper moves any request count in `test_command_path_parity.py` (row 26, `test_restart_with_the_car_plugged_in_and_asleep_gets_the_scheduled_limit` at :1206, in particular), stop and report; never re-tag it.
- **Characterization tests** marked "BASE+after" must pass on a scratch checkout of 1029809b **and** after the task. The report records both runs.
  - They pin the default (distributor) path: a master with `VehicleEndpoints` registered, spike settings `0` at BASE.
  - They reproduce BASE's observable order (ruling F8). At BASE the distributor ran at the start of a round, before the slave's heartbeat and reply: **distribute → receive → send**. After the task the reply is recorded, then the tick computes, then the heartbeat sends: **receive → controlPass → send**.
  - The helper `tickThenBeat(m, s, state, maxA, actA)` encodes both orders: `if hasattr(m, "controlPass")` it runs receive → `m.controlPass()` → send, else `m.distributeEVSEPower()` → receive → send. Task 3 adds it to `tests/unit/gen2_helpers.py`.
  - The helper `offersThenBeat(m, s, state, maxA, actA)` is the **offers-only** beat (ruling F1): receive → `m.controlPass(distribute=False)` → send, so a target a test set by hand (`pt.setTargetPower`) is not overwritten. At Task 3 (offers still in `receive`), `controlPass(distribute=False)` does nothing.
- **Line reporting.** Each task reports:
  - `git ls-files lib | grep '\.py$' | xargs cat | wc -l` before and after;
  - `git diff --shortstat <task BASE> -- lib`;
  - actual vs expected Δ.
- Python 3.8 syntax; `black` on touched files only. Commit trailer per the session's attribution reminder.
- **Real objects in cross-module tests:** a real `TWCMaster`, a real `Gen2TWC`, a real `VehicleRegistry`/`DesiredStore`, `teslatokens.new_api` and `requests_mock`. Never mock a success value the real method never returns.


## Comment rule (user, 2026-10-17; binds every task from here on)
Code must read as if it were designed this way from the start. Comments explain why the code is what it is — not how it used to be, when or why it changed, which review or ruling prompted it, or the many things it isn't. Mention an alternative only where the obvious approach isn't the right one. History goes in commit messages and PR descriptions. Keep comments short.
No phase names, PR/issue numbers, or review/ruling IDs (F7, I2, (d) …) in code comments.
