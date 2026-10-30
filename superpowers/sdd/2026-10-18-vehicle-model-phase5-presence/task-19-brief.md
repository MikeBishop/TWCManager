# Task 19: A TWC status change means "check the car", not "the car left" (user design, 2026-10-20)

## User's words
- "I wonder if we're approaching this the wrong way, trying to decipher the status twitches. What if it's like BLE
  presence — absence of evidence isn't evidence of absence. The status code tells us something changed, but we need to
  check the car to see what. What if a TWC status twitch just tells us to check awake/asleep over BLE/API, and if awake,
  check plug state? For a Teslamate vehicle, it will tell us momentarily anyway."
- "When nothing can check the car at all, detecting an unplug event almost doesn't matter -- none of the things we would
  trigger can work either. Fleet can do a paid read if it comes to that. If someone wants to avoid it, use any of the
  other options."

## Why
Gen2 status codes reflect the car↔TWC negotiation, not the plug. Every heuristic so far needed an exception: the wake 00 flicker, the 60 s plugged-run guard, the link grace, the 60 s debounce, the mid-run max drop, and our own 0 offer.

Box evidence (3 days):
- An awake idle car shows 00 at max 47 for 3–19 min, then 03 when it sleeps.
- Real unplugs showed 00 at max 0, either at the onset or later in a 00 run.
- A 27 s re-plug was blocked by the run guard.
- TeslaMate caught every unplug within ~15 s.

## Behaviour
1. **Trigger.** A Gen2 status edge on a point asks for a plug check of the car(s) that point concerns: the named car, or, for an anonymous session, its candidates. The edges are:
   - non-00 → 00;
   - a max drop to 0 during 00;
   - any change of plugged state.

   Coalesce: at most one pending check per point. A check already run for this edge is not repeated by a flicker (e.g. one check per point per 60 s, or per 00 run).
2. **The check, cheapest first, never waking:**
   - **Live telemetry feed** for the car (TeslaMate / Fleet Telemetry, `syncSource` live): wait for it. It reports plug changes within seconds, so no read is needed. If the feed says nothing new within a short window, fall through.
   - **BLE in range:** the sleep-safe ping.
     - Asleep → still plugged (an unplug wakes the car). Done, no read.
     - Awake → BLE charge-state read.
     - No answer → BLE absence, as today.
   - **Otherwise:** the registry read cascade for `chargingState` with `allowWake=False`. Owner is a free read. Fleet does a free online check, and only if the car is awake, the paid `vehicle_data`. Use the existing read cascade and provider order; don't build a new one.
   - **Nothing can check the car:** do nothing. No fallback heuristic.
3. **The result** feeds the registry like any reading.
   - A Disconnected/unplugged read becomes the unplug, through the existing flow: the `noteObservation` unplug mark → departure/restore, `_plugSession(slave, False)` / `endPlugSession`.
   - A plugged read keeps the session.
   - For an anonymous session: end it when the check shows no candidate plugged here. Keep the existing attribution path for naming.
4. **Delete** what this replaces: the unplug filter's guards and state in `TWCSlave.unplugStep` and `TWCMaster.observeChargingSessions`. That covers:
   - the plugged-run guard;
   - the link grace for unplugs;
   - the 60 s debounce;
   - mid-run drop detection;
   - the own-offer guard;
   - the `zeroMax`/`ampsMaxBefore`-based decisions;
   - the anonymous idle/short-run fallback.

   Keep only what is still needed to detect the edges and log them at INFO for diagnostics: one line per edge, e.g. "TWC 8244: 03 → 00, max 47 → 47: checking <VIN>", plus one line with the check's verdict.
5. **Plug-in side unchanged:** 00 → plugged begins a session, and attribution works as today. Exception: the plug-in edge can share the same coalesced check trigger if that removes code.

## Constraints
- The serial thread only notes the edge and queues the check, on the BLE worker or in the background as attribution does. No I/O, and no locks held across registry calls.
- Never wake. Paid only via the Fleet branch, only when its free online check says awake, at most once per edge.
- Net lib must shrink (target ≤ −20). Report the delta.
- Existing parity rows: unplug timing will move, because checks replace a 60 s debounce.
  - Report every move as old → new, with the reason.
  - Update a row only when the move follows from this design.
  - Rows that assert the TWC alone departs a car with no way to check it now expect no departure. That follows the user's second quote.
- Tests:
  - (a) The 2026-10-20 12:45–12:47 box sequences with BLE: the wake 00@47 followed by max→0 mid-run, and the 27 s re-plug followed by 00@0. Departure after the BLE read says Disconnected, no wake, paid (0,0,0).
  - (b) The same with TeslaMate live: no BLE read; the feed's plugged_in false departs.
  - (c) A car asleep on a 03 → 00 flicker: the ping says asleep → no unplug, no read.
  - (d) Fleet only. If the online check says awake: one paid vehicle_data, Disconnected → departs. If asleep: no read.
  - (e) Nothing can check the car: no unplug.
  - (f) An anonymous session with one candidate read Disconnected: the session ends.
  - (g) A 00/09 flicker during charging: at most one check per window.
- Comment rule; Python 3.8; black.
