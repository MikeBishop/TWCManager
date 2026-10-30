# Task 3 review (opus), d5cc8711 — Needs fixes

## Critical
1. Hold spends paid budget with no paid request (Desired.py:352, Reconciler.py:380): `paidSpent += paid * (attempt.wake + (attempt.maxAge is not None))` counts flags, not requests made. Probe (TeslaMate + Fleet, no BLE): car drives inside radius, TeslaMate pushes state=driving every 5 s, policy limit 80; two held attempts → paidSpent=4 with paid (0,0,0); car parks (HOME, arriving > leaving → apply should SEND) → nothing sent for an hour, lastOutcome "held: driving", car stays 50. TWC plug-in doesn't rescue: onArrival → desired.set same value is "unchanged", newDesire never resets budget. Fix: count only paid requests actually issued (wake POST, vehicle_data that hit the network), and/or the budget caps only attempts that end held so a hold never blocks the first paid send once applicable would SEND. Add the scenario as a parity row.

## Important
2. Restore to a car HOME and plugged re-created every policy pass (Targets.py:48-64, Reconciler.py:494-511): applyPolicyLimit(None) sets restore; applicable → HOME_NOW; clearIf clears; next pass sets again. Probe: 60 attempts/car/hour, 120 INFO lines, one paid vehicle_data when uncached. (Resolution depends on the user's ruling on restore-while-home.)

## Minor
3. test_presence.py:485 `car(P.PRESUMED, plugged=True)` is actually HOME (pluggedIn from Gen2TWC sets plugIn mark) → PRESUMED+plugged→SEND for apply untested. setup(here=True) default in test_limit_reconciler.py:10 uses pluggedIn from Gen2TWC, which lib never emits. Add a real PRESUMED+plugged row (e.g. plug-in then newer absent mark).
4. TeslaBLE.py:635-645 timeout/launch failure/non-zero rc records bleReach False; range scan treats timeout and tool errors as unknown (F9). Use `return None if ran is None or ran[2] is None else ran[2] == 0` (or classify timeouts/tool errors as None like the scan).
5. Reconciler.py:501 hold why = presence reason, not the cell's (HOME tie reads "held: BLE contact"). Task 6 reads rec.heldAt + rec.lastOutcome.detail; consider applicable returning (verdict, why).
6. fleetPoint (parity diff line 1306) now has a TeslaMate source; rows 13/14 "Fleet-only car on a TWC" no longer Fleet-only. Use a Fleet-sourced observation or TWC plug state.
7. learnHome (Presence.py:112 → :289) reads vehicle.latest lat/lon, possibly another source's or mixed; with the BLE trigger, use the triggering source's pair.
8. Two onArrival calls per TeslaMate-on-Gen2 plug-in (noteObservation + recordVehicleVIN); second normally a no-op. Note only.
9. Run.py pre-wake `_tagged(reconciler.inapplicable(...))` would raise on None; unreachable today. Guard cheaply or note.

## Size cut list (lib +100)
| Location | Change | Saved |
|---|---|---|
| TWCSlave.py:116-134 pluggedCars | use Presence._plug("chargingState", obs) for the inline HA/_PLUGGED mapping | ≈ −6 |
| Targets.py:80-87 _left + Presence.py:228 | one Presence departed(master, v) used by applicable's restore/apply HOME cells and Targets | ≈ −3 |
| Desired.py:348-354 | fold held branch into `if current:` | ≈ −2 |
| Presence.applicable start branch | one expression via heldLimits.holding() or shared helper (dup of Reconciler _held) | −1 |
| Reconciler heldLogged | use rec.heldAt is None as first hold; drop field | −1 (logs once per hold episode) |
| TeslaBLE _fetch_state_json | compute _settingsKey(vin) once | −1 |
| Total | | ≈ −14 |
