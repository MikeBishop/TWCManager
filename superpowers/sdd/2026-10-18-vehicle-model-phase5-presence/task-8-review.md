# Task 8 review (opus), 7c503a62 — Needs fixes
Critical 1: raise held at 0 A stays "asleep" after the offer rises — gate at Reconciler.py:221-227 returns before wakes recomputed. Fix: keep generic lastObservedAt<=heldAt gate at top; move the asleep test below `wakes = wakes and not idle` (Reconciler.py:318): `if rec.heldAt is not None and not wakes and last.detail == O.HELD + "asleep" and Presence.asleep(vehicle): return None`. Test: 0 A, then offer > 0 → wake.
Important 2: BLE wake not a sign of life (wakeVehicle observes only bleReach). Fix: observe state "online" in Run._wake on DONE for any provider; drop TeslaAPI.py:1554's own observe.
Important 3: TeslaBLE/Fleet `state` newer than shiftState masks driving (drivingNow Presence.py:173-177) → departing car HOME by BLE contact; breaks F7. Fix (0 lines): drivingNow uses v.telemetryState()[0] (feed's own state, fallback newest).
Important 4: every quiet BLE attempt pre-flights even when the car is visibly awake (BLE amps lowerings every 15 s while charging → doubles BLE sessions). Fix: skip the pre-flight when a sign of life is newer than the newest asleep reading.
Minor 5: pre-flight scan miss can demote HOME→PRESUMED (F9-consistent; bounded). Leave.
Minor 6: stops and NOT_HOME restores not pre-flighted — acceptable.
Minor 7: newer "offline" counts as life in asleep(); brief says not asleep/offline is life. Treat offline like asleep.
Minor 8: _noteSleep uses KeyError for control flow; use .get.
Minor 9: hold logged via report() generic line — cosmetic.
Cuts: asleep() life = max(plugIn/unplug/driveStart/driveEnd marks, actualCurrent >= 1) instead of _LIFE (≈ −6); _noteSleep comment fold (−1).
