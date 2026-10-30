Task 9 report. Commit on vehicle-model/phase6. Full suite 2338 passed, 1 xfailed (base 2333+1). Lib +29 net lines (30 ins, 1 del).
- master.watch = Watch(master) before controlTick; TWCMaster.watch defaults None; housekeeping runs it under _guarded.
- Watch.pass_ now a no-op when disabled (notWatched already returned "disabled").
- watchLine(master, v) global + one Watch cell after Presence.
- Tests: tick runs watch / error isolated; launcher order; check_green_energy (function read out of launcher source) calls loadSample; disabled pass_; page line. Mutation-checked three rules.
- Power start -> readNow through TWCMaster already covered by test_watch.py (updateChargeAtHome) and test_presence (checkCharge queued); the launcher's task dispatch itself is not importable, so not tested.

Fix round 1 (amended): a watched car with no status source shows "Not watched: no status source" (tested); the EMS poll plus loadSample moved into TWCMaster.pollEMS (loadSample fault logged, never raised), tested with a real master, source-reading test dropped; redundant getattr guards removed; watch comment reworded.
