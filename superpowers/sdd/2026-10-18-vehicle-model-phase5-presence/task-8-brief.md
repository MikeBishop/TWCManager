# Task 8: Leave a sleeping car alone (user, 2026-10-19)

User: "Rather than spamming the logs with 'no wake / failed' every time BLE tries again, maybe we should do a
pre-flight to see if the car is asleep and just not attempt a BLE send if it's asleep and we wouldn't wake. Once the car
is known to be sleeping, leave it alone until we decided it needs to wake or we see a sign of life from some other source."

Evidence (live box, events.log): 252 "no wake for … / BLE command … failed with return code 1" lines; the pattern is a
lowering (never wakes) retried against a sleeping car every ~5 min, each a failed BLE command plus a log line.

## Behaviour
1. **Pre-flight.** Before a BLE attempt that may not wake (a lowering, a release that lowers, a restore, any no-wake
   case the reconciler already computes), run the sleep-safe VCSEC check (`body-controller-state`, the ping's runner) and
   read the car's sleep status from its answer (e.g. `vehicleSleepStatus` ASLEEP/AWAKE — verify the field name in the
   tool's actual JSON; there's a parser for the ping's runner already). Observe it into the registry as the car's
   `state` from source TeslaBLE ("asleep" / "online"), so other code and the Vehicles page see it.
2. **Asleep and no wake allowed → don't send.** The attempt ends as a hold, reason "asleep", logged once per desire (not
   per retry). No BLE command is run, no failure is logged.
3. **Known asleep → skip the pre-flight too.** While the newest `state` (any source) is asleep and nothing newer shows
   life, a no-wake attempt holds without running anything.
4. **Sign of life re-opens.** The held desire re-plans when an observation newer than the asleep one shows the car awake:
   `state` not asleep/offline from any source (TeslaMate, Fleet online check, BLE), a drive/shift, a plug or unplug event,
   `chargingState` Charging, a TWC reporting current drawn for that car, or BLE contact with AWAKE. Repeated "asleep"
   readings do not re-plan. (Fit this to the existing hold mechanism: today a hold re-plans on any newer observation —
   narrow it for the "asleep" hold.)
5. **We decide it needs to wake → unaffected.** A message that may wake (raise/start under the existing rules, and not
   at 0 A offered) goes ahead and wakes as today; the wake itself is the sign of life.
6. Cloud paths are unchanged (Fleet already does a free online check before a no-wake send); but a Fleet "asleep" online
   check counts as known-asleep for rule 3 and should also suppress repeat BLE attempts.

## Constraints
- Never wakes; no paid calls; no polling (the pre-flight runs only when an attempt is due).
- BLE runs under `_bleLock` on the BLE worker; the pre-flight must not hold other locks.
- Lib growth small: reuse the ping runner, the hold mechanism and the `state` field. Target ≤ +20 net.
- Tests: lowering to a sleeping car → one pre-flight, no command, one log line, hold "asleep"; retries while asleep → no
  runs at all; TeslaMate state online → re-plan and send; a raise still wakes; parity counts unchanged except rows this
  intentionally changes (report each).
- Comment rule; black; Python 3.8.
