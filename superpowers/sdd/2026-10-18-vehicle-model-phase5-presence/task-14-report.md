# Task 14: wait for telemetry before waking after a start

Commit 6d6caaef on vehicle-model/phase5 (not pushed).

- Rule: `Belief.whyQuiet` returns "waiting for telemetry after start" while any loaded feed (TeslaMateVehicle, FleetTelemetryMQTT) has `settleUntil` in the future. `TelmetryBase.settleUntil` is set to start + 60 s at construction and cleared when the feed's first message is applied to a car. Wakes only: a quiet reason already means no wake, so awake-car sends, free sends, restores and stops are unchanged. No new registry field.
- Tests (tests/unit/test_limit_reconciler.py, 5): full / below-limit report / silent 60 s / no feed / awake car. 3 fail without the lib change; the other two pin behaviour that already held.
- Suite: tests/unit + tests/EMS 2156 passed (baseline 2151 + 5).
- Parity: no existing row moved (no feed module is loaded in them).
- Lib delta: +9 lines (26298 -> 26307 total lib lines), against the 3-6 target.
- Concerns: (1) the grace ends at the feed's first message to a mapped car, so a reconcile pass between that message and the battery/limit messages can still see unknown values and wake; a few ms to 1 s window (TICK). (2) A held "asleep" message re-plans only on a newer observation, so the 60 s expiry relies on any observation (TWC heartbeats) arriving; the test models that. (3) A feed that is configured but never connects (syncTelemetry false) costs a 60 s wake delay after each start.
