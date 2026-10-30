# Task 6 review (opus), e9d2a813 — Needs fixes
Critical 1: Vehicle.py:359-371 dead old `return {...}` after the new return (refers to deleted locals). Delete (−13). A5 then actually saves ≈ −24 (with summaries() removal).
Important 2: HTTPControl.py:148 race — reads rec.lastOutcome then rec.heldAt without the lock; noteOutcome sets heldAt before lastOutcome → last None + heldAt set → AttributeError → 500. Fix: read last once and guard, or merge the held branch into the outcome line.
Important 3: HTTPControl.py:131 master.desired.record() creates entries (via _state) → a forget racing a render revives an empty ControlState. Use peek(key) once; read state.desired / state.records.
Important 4: size +73 vs ≤ 0.
Important 5: HTTPControl.py:155 "paid request limit reached" omits the reconciler's applicable != SEND condition → can be wrong. Cut the branch.
Important 6: HTTPControl.py:159 retry time ignores WAKE_CHECK when wakeCheckBy set. Cut; the outcome age stays.
Minor 7: drop the wake-skipped note ("not waking: nothing offered") — transient, cryptic, not a why-not-sent.
Minor 8: raw outcome details acceptable as diagnostics; no map.
Minor 9: add one row driven by a real noteOutcome HELD outcome, and one with heldAt set while lastOutcome is None.
Minor 10: tests/unit/test_vehicle_detail_page.py:4 `import time` order.
Minor 11: HTTPControl.py:121-123 duplicate registry lookup — take the vehicle (template passes regVehicle).

Smallest design (≈ +8..+11 net incl. A5 done properly):
```python
PRESENCE_TEXT = {HOME: "Home", PRESUMED: "Probably home", NOT_HOME: "Away"}

def pendingCommands(master, vehicle):
    """Each desire the car has not reached: in flight, or why it is not."""
    state, now, rows = master.desired.peek(vehicle.key), time.time(), []
    for aspect, d in list(state.desired.items()) if state else []:
        rec = state.records[aspect]          # .get if adopt can skip it
        sent, last = rec.inFlight, rec.lastOutcome
        why = master.reconciler.said(vehicle.key, aspect)
        if sent:
            why = "sending via %s, started %s" % (sourceName(sent.provider), ageText(now - sent.since))
        elif rec.settledAt or satisfied(aspect, d.value, known(vehicle, aspect)):
            continue
        elif last and not why:
            why = "%s via %s, %s" % (last.detail.replace(RULES, "") or last.kind, sourceName(rec.lastProvider), ageText(now - rec.lastOutcomeAt))
        rows.append({"aspect": aspect, "value": d.value, "why": why or "not tried yet"})
    return rows
```
Template does the wording (3-entry aspect name map; value: −1 → "car's own", "%", "A", start/stop). Globals: presence=lambda v: PRESENCE_TEXT[presence(master, v)], pendingCommands=lambda v: pendingCommands(master, v). Drop presenceText, _wanted, span, paid-budget, retry-time, wake-skip branches and their imports.
