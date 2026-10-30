# Task 3 report: paid-read budget
Status: DONE. Commit on vehicle-model/phase6 (see git log HEAD).
Full suite: 2257 passed, 1 xfailed (base 2253 + 4 new).
Lib lines: 26464 -> 26533 (+62 WatchBudget.py, +7 TWCMaster.py).
Notes:
- spend() uses a 1e-9 epsilon: 0.1 - 49*0.002 float-drifts just under 0.002, which would refuse the 50th read and break the brief's refill assertions.
- A zero price refreshes the stamp but never flips the exhausted/available log flag.
- load() on None/malformed resets to full (not just leaves current state).
- Round-trip test stubs getModuleByName with a carapi whose token slots are plain strings (saveSettings needs it); make_master is tests/unit/test_gen2twc_provider.make.

## Fix round 1 (amended; commit 63fea432)
- Log flag flips only on EVENT spends (exhausted/available again); routine refusals never log; log is one line, no numbers.
- Leaf threading.Lock around tokens/spend/toJSON/load.
- load() clamps a future stamp to now.
- Added tests: future stamp / clock step back; mixed ROUTINE/EVENT logs exhausted once.
- Suite: 2259 passed, 1 xfailed. Lib lines 26464 -> 26540 (+76).
