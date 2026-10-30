# Task 4 review (opus), e5267e5b..761b4296 — Needs fixes
Important 1: Presence.py:253-257 `named` (twcVin newer than leaving) overrides a newer "unplugged" reading. Probe: idle 0 A car on a VIN TWC (filter (a) can't fire), unplugged and parked home, Fleet only → startCarsCharging → wake + vehicle_data (Disconnected) → charge_start still sent, paid (1,1,1), repeats per desire. e5267e5b gave NOT_HERE. Fix: count `named` only when no plug reading newer than the naming says unplugged — e.g. plugEvidence(master, v, since=named.at) is not False (+1). Not plain `ev is not False` (a stale pre-plug Disconnected would block the midnight start). Test: Fleet Disconnected read after the naming → start NOT_HERE.
Important 2 (→ Task 5 brief): returning car on an unnamed Gen2 (filtered unplug, then back; BLE contact HOME; TWC 03 asleep; no VIN read yet) → plugEvidence False (stale Gen2TWC pluggedIn False), unplug mark, named False → car-addressed start "not here (not plugged in)". Task 5 attribution must turn "unnamed Gen2 00→03, single candidate" into plug-in evidence for that car, with a test.
Minor 1: quick re-link within 26 s doesn't re-arm the grace; cheapest guard `slaveTWC.pluggedSince = time.time()` at TWCManager.py:1231 (+1).
Minor 2 (→ Task 7 docs/box): idle 0 A car keeps twcVin; a later guest car at 03 on that TWC keeps the departed car HOME "named by its charging point" unless an outside fix or drive start exists.
Minor 3: sleeping-car parity row asserts only paid[1]==0; state the full tuple.
Minor 4 (→ Task 5 brief): single-candidate unplug fallback must exclude cars whose twcVin names another point (~1 line).
Minor 6: deleting the charge-stop end means a VIN rejected in one charge session stays rejected for that plug-in (endPlugSession popped _pending); cleared by the raw-00 anon close. Name it in the report/PR.
Minor 7: log the departing car at INFO on a non-veto unplug (+1).
Minor 8/9: offer at onset could be logged; spurious onset log for a slave not yet heard from (cosmetic).
Size cuts (behaviour-preserving, ≈ −9): fold plugEvidence into pluggedNow(master, v, unknown=False) (−4); vehicleAt/candidates fallback one-liner (−1); TWCMaster.py:1496-1499 comment (−2); TWCSlave.py:101-102 comment (−1); Presence.py:250-252 comment (−1).
Behaviour-changing cuts NOT taken: drop PLUGGED_RUN; drop single-candidate fallback.
Midnight without a held limit, car-addressed: doesn't start (unchanged; F20). Gen2 point start is ungated, so the TWC start is unaffected.
