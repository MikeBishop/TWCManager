# Plug-based vehicle presence (revision of presence waves E and the arrive/depart features)

Date: 2026-10-11
Status: approved by the user 2026-10-11
Replaces: the presence state machine on the unopened stack `presence/3-presence-tracker` and `presence/4-arrive-depart` (ledger `.superpowers/sdd/2026-10-09-vehicle-presence/progress.md`; split report `.superpowers/presence-split-report.md`).

## Why

On 2026-10-11 the live box sent a paid Fleet API `set_charge_limit 50%` to a car that was driving away:
- The car became AWAY when BLE went silent, while still inside the large home radius (default `atHomeRadius` 10,560 ft). The location rule then took "away and inside the radius" as an arrival, and the car became ARRIVING in the same second.
- ARRIVING reports as UNKNOWN. The policy-wide charge-limit apply skips only AWAY, so it re-applied the 50% home limit, which the departure restore had un-deduped.
- BLE failed (out of range), and VehiclePriority fell through to the Fleet API, which the user had enabled that day. The car accepted the command.

The root cause is that BLE reachability and a coarse geofence are weak evidence for "the car is here". The user's insight, from another setup: **a car cannot drive while it is plugged in.** Being plugged into our TWC is strong evidence the car is home, and unplugging is a strong signal it is about to leave.

## Two independent dimensions (decided with the user, 2026-10-11, supersedes the state names below)

Per car, two questions are tracked separately:
1. **Presence:** home or not home, with a confidence (`evidence` from plug signals, or `presumed` at startup). Presence alone decides inclusion in wakes, charge commands and policy-wide applies. A presumed car gets no Fleet API EVSE, since that path sends rates without reading the car.
2. **Limit state:** whether TWCManager's policy limit is applied, or the user's outside limit is in place. It's already stored as the saved `[outside, lastApplied]` (lastApplied -1 means nothing is held).

The charge-limit actions come from comparing the two (a reconciler):

| Presence | Limit | Action |
|---|---|---|
| home | outside limit in place | apply the policy limit (read-before-write guards a presumed car) |
| home | policy limit applied | nothing |
| not home | policy limit applied (held) | restore: BLE now; retry while BLE reaches the car; remote fallback after BLE has been gone 5 min; remote immediately when the car has no BLE |
| not home | outside limit in place | nothing |

"Departing" in this document means *not home while a limit is held*; "presumed" means *home on weak grounds*. These are not separate tracker states. A held limit after a restart, a retried BLE restore, and no duplicate arrival apply all fall out of the reconciler.

## The model (decided with the user)

Two states per vehicle:

- **HOME**: the car is plugged in here. Charge-limit policy applies only to HOME cars.
- **NOT HOME** (internally DEPARTING after an unplug): everything else, including a car parked at home but not plugged in, a car driving, and a car charging elsewhere.

There is no AWAY and no ARRIVING. The user asked whether anything is lost with only these two states; working through every consumer below, nothing is lost for charging or charge limits:

| Consumer of the old states | Under the plug model |
|---|---|
| Policy-wide charge-limit apply skipped AWAY cars | Applies only to HOME (or presumed-present) cars; DEPARTING is always excluded |
| Don't wake or poll cars that aren't home (Fleet cost, battery) | NOT HOME is not home |
| Departure restore of the user's outside limit | On unplug, over BLE right away; remote fallback by timer (below) |
| Re-apply the policy limit on return | On plug-in (HOME), when the car is at the TWC and in BLE range |
| `numCarsAtHome`, `minBatteryLevelAtHome` | Count plugged-in cars; an unplugged car can't charge, so this is arguably more correct |

`CarApiVehicle.atHome` keeps reading the central presence tracker, and is True only for HOME.

**HOME is the single definition of "home" everywhere (decided with the user).** It covers charge limits, waking a car to charge, start/stop charging, `TeslaAPIController`'s Fleet API EVSEs, `updateChargeAtHome` and `vehicleScheduledChargingPending`. HOME means plugged in at home, on a TWC or on any other charger at home (e.g. a mobile connector, seen through TeslaMate/API plus location).
- **Asleep and plugged in:** HOME. It is woken to charge as needed.
- **Asleep and disconnected:** not HOME, never woken.
- Sending charge commands to every vehicle "at home" and then filtering out the ones that can't be plugged in is a legacy of not knowing which car is on the TWC. Commands now go to the car the plug evidence names. A broadcast survives only where plug evidence exists but names no car (a VIN-less TWC with no attributable candidate). There it goes only to the candidates (cars inside the radius or reachable over BLE), never to every car on the account.
- **How an asleep, plugged-in car is known to be plugged in:** the last plug evidence persists while the car sleeps (a TWC naming it; TeslaMate's retained `plugged_in` plus location; an earlier BLE charge read), until unplug evidence arrives. A TWC that can't report a VIN and reports a plugged state is attributed by the candidate rules below. At startup, with no evidence either way, the car is presumed present (see Startup); after an unplug it is DEPARTING until plug evidence returns.

**Unknown at startup:** presumed present until discovered otherwise (see Startup).

## Evidence

### Plugged in / unplugged

| Source | Counts as "plugged in here" when |
|---|---|
| A TWC that reports the car's VIN | always: our own hardware names the car |
| A TWC that can't report a VIN (plugged state, or drawing current) | when exactly one candidate car can be attributed to it (below) |
| TeslaMate `plugged_in`, or an API charge state | only together with location inside the home radius, or a TWC seeing a plug at the same time. A generic "plugged in" is true at a Supercharger too. |
| BLE `state charge` (`chargePortLatch` Engaged / `connChargeCable` SAE / `chargingState` not Disconnected) | the car is within BLE range, so it is here; BLE is local |

"Unplugged" from any source that names the car moves it HOME to DEPARTING. The existing TWC plug-debounce and link-grace rules carry over: a plugged run of at least 60 s before a change counts, there is a 300 s grace after a TWC re-link, and TeslaMate `plugged_in` overrides a Gen2 TWC's steady 00 for an idle plugged car. These protect against the unplug false-positives seen live.

### Attributing a plug at a TWC that can't report a VIN

Candidates are the cars that are either inside the home radius (any location source) or reachable over BLE. With one candidate, it's that car. With several:

- **Preferred, live-verified 2026-10-11:** the car's BLE charge state exposes `chargerPilotCurrent` and `chargeCurrentRequest`, which equal the amps the TWC offers (47 A on the box, matching the TWC heartbeat), and `chargerActualCurrent`, which is matched against the TWC's reported amps. `fastChargerType` `ACSingleWireCAN` with `fastChargerPresent` false identifies a Tesla wall connector. The car and the Gen2 TWC talk over single-wire CAN on the pilot line, but no TWC identity (serial or TWCID) is exposed to BLE.
- **Fingerprint, if still ambiguous:** briefly offer that TWC a distinctive current (1 A below its normal offer), read candidates' `chargerPilotCurrent` over BLE, and pick the car whose pilot follows. Restore the offer afterwards.
- If still ambiguous: no car becomes HOME from that TWC, which is the safe failure. Log it at INFO once per plug session.

BLE charge reads need the car awake. One worked live on an awake car (2026-10-11); a sleeping car is untested. A freshly plugged-in car is normally awake.

### Evidence strength (decided with the user)

BLE and the physical connection (a TWC) outrank GPS. A TWC naming the car, or a BLE charge read, decides on its own. TeslaMate/API plugged-in plus location is used when neither is available. When they disagree, BLE or the TWC wins.

### BLE reach is evidence of presence; BLE silence isn't evidence of absence (decided with the user)

- **BLE reachable:** the car is at home. A BLE charge read showing a plug is both "plugged in" and "here". That covers a Gen2 TWC's steady 00 without GPS.
- **BLE silent:** says nothing about whether the car is home. A car on a UMC at an outlet outside BLE range is home and plugged in. TeslaMate/API plugged-in plus location decides, so GPS matters for BLE-capable cars whenever BLE can't reach them.
- **BLE silent while plugged in at home** suggests the car is *not* on the TWC. It's an unlikely candidate for a VIN-less TWC's plug, and it can safely get a Fleet API EVSE (#694's controller). A BLE-reachable car plugged in at home is treated as possibly on the TWC.
- GPS is also used to learn `homeLat`/`homeLon` from a car at the TWC, which is not presence.

### Inside or outside the radius

A single radius, `atHomeRadius` (decided with the user). Its default becomes much tighter: **1,000 ft** instead of 10,560 ft. The setting stays configurable, so anyone with unreliable GPS can widen it. It was 2 miles because of reported GPS flakiness, but the user sees tight fixes; a car that has just left a 1,000 ft radius is clearly gone. Changelog note: existing configs that never set `atHomeRadius` get the tighter default; set it explicitly to keep 2 miles. *(The 1,000 ft value is my call.)*

Location matters only to qualify generic plugged-in signals and to find candidates. It no longer drives state transitions, so there's no need to poll location while a car is NOT HOME.

## Startup: presumed present, discovered on wake (decided with the user)

No wake is ever sent just to find out whether the car should be woken later; that's a wasted wake.
- At startup, a car with no plug evidence and no departure evidence is **presumed present**. It's treated as HOME for charging, so the normal charge flow wakes it when there's something to do (start charging, apply the policy limit). A sleep-safe BLE probe that happens to answer just confirms the presumption.
- **Discovery on wake:** once the car is online, every command path reads its state before acting: BLE's read-before-write, the API charge state, TeslaMate's fresh data. If it shows unplugged, or a location outside the radius with no BLE reach, the car becomes NOT HOME and nothing is sent.
- The presumption applies **only** to a car we know nothing about. A car seen unplugged is DEPARTING, which is known not to be home and never presumed. That's the difference from 2026-10-11, where a departed car was treated as possibly home.
- A car still presumed present when TeslaMate attaches, or when other evidence arrives, follows that evidence.

## Departure restore and re-apply on install types

- **BLE available (TeslaBLE loaded and the car paired):** as below. BLE goes first, with the timer fallback.
- **No BLE (Fleet-only, TeslaMate + Fleet, HomeAssistant):** on unplug, restore over the remote channel immediately. The car is awake right after an unplug, so it's one command. On plug-in (HOME), re-apply over the remote channel. *(My call: it matches the old behaviour's cost of one command per departure and one per arrival.)*

## Departure restore

On HOME to DEPARTING (unplug):
1. Restore the user's outside limit over BLE immediately, `localOnly`, while the car is still in range. This already works live.
2. If the BLE restore hasn't succeeded by the time BLE has been unreachable for `N` minutes (proposed 5), fall back to a remote restore through the normal command order, if `commandPolicy` allows a remote channel. This replaces the old "restore when AWAY".
3. A re-plug before the restore completes cancels it. HOME re-applies on its own schedule.

No GPS source is needed for any of this.

## BLE's role

BLE is a command channel, and a source of plug evidence while in range. It is no longer the primary presence signal. Removed from the presence stack:
- the arrival probes and ARRIVING state, the 600 s arrival-confirm timeout, and `_timeoutHome`;
- the BLE-silence away rule (`AWAY_AFTER_FAILED_PROBES`, `_failedProbes`, `_departingFailures`);
- location-driven HOME/AWAY transitions.

A periodic BLE probe is used only while DEPARTING with a pending restore (to know when BLE has gone, for the fallback timer). Body-controller-state stays the sleep-safe probe.

## Policy-wide applies

`VehiclePriority` / `TeslaBLE` / `TeslaAPI` policy-wide (`vin=None`) charge-limit applies target only cars whose presence is HOME, on every channel. A per-VIN apply (from the presence handlers) is unaffected. This is the second root cause of 2026-10-11, and it gets its own regression test: depart, then a policy cycle while the car is DEPARTING inside the radius, asserting that nothing is sent on any channel.

## Scope and delivery

- **Build (my call):** branches 3 and 4 collapse into one branch, `presence/3-plug-presence`, rewritten on top of `presence/2-charge-limits`. Commits that carry over unchanged in meaning are cherry-picked: plug debounce, link grace, TeslaMate `plugged_in`, the unplug BLE restore, and VIN-less TWC plug handling. The new tracker goes on top. Each branch must pass the full suite; individual commits needn't. Branch 5 (Fleet rate queue) is rebased onto the new branch 3. The token-slot port happens when the deploy branch is merged with #692, as before.

- Rework `presence/3-presence-tracker` and `presence/4-arrive-depart` on the unopened stack. Branches 1 (command queue) and 2 (charge-limit rules) are unchanged. Branch 5 (Fleet rate queue) and #694 are unaffected.
- The "TeslaMate plugged_in as presence signal" and "unplug false-positive" features carry over. "BLE-confirmed arrival" is dropped. "Departing on unplug with early BLE restore" stays.
- `vehicle.presenceSources` (telemetry/ble/api): keep it if it still makes sense as "which sources may supply plug or location evidence"; otherwise drop it. Builder's call, recorded in the plan.
- The live box stays on `commandPolicy: ble_only` until this is deployed.

## Goals

- Charge limits are applied only to a car plugged in here, and restored on unplug.
- No apply, wake or command to a car that isn't plugged in here, on any channel.
- Works with no GPS source (BLE + TWC only), with TeslaMate, and with API location.
- VIN-less TWCs still work for one car, and for several cars when BLE can attribute the plug.

## Non-goals

- No AWAY/ARRIVING display states.
- No location polling while a car isn't home.
- No change to the token-slot work (#692/#693), IntegrationOrder (1.4.0), or branches 1, 2 and 5.

## Anti-goals

- Any charge-limit command to a car that isn't plugged in here.
- Treating a Supercharger or a friend's TWC as home.
- Waking a sleeping car just to learn presence.

## Left to the builder

- `N` for the BLE-gone fallback (proposed 5 minutes), and the DEPARTING probe interval.
- Whether the fingerprint (offset current) is built now or left as a follow-up behind the simpler single-candidate rule. My recommendation: single-candidate plus the BLE pilot match now, fingerprint as a follow-up unless the user has more than one car on VIN-less TWCs.
- Data structures and handler names, reusing the existing VehiclePresence/PresenceHandlers where possible.

## Tests the user will expect

- The 2026-10-11 sequence (unplug, BLE silence, still inside the radius, policy cycles): nothing sent on BLE or Fleet.
- Plug-in (TWC with VIN; VIN-less with one candidate; VIN-less with two candidates attributed by BLE pilot; ambiguous goes nowhere) leads to HOME and one apply.
- TeslaMate `plugged_in` true outside the radius (a Supercharger) is not HOME.
- Unplug leads to an immediate BLE restore; BLE gone for N minutes with the restore not done leads to the remote restore (only when allowed); re-plug cancels it.
- Startup: an asleep car with no evidence is presumed present. No wake is sent until the charge flow needs one. On that wake, an unplugged car becomes NOT HOME and nothing is sent; a plugged car charges. A Gen2 steady-00 TWC doesn't block this.
- A BLE-reachable car is home without GPS. A BLE-silent car with TeslaMate plugged-in inside the radius (UMC case) is HOME and gets a Fleet API EVSE. A BLE-reachable plugged car is a VIN-less TWC candidate; a BLE-silent one is not preferred.
- A DEPARTING car is never presumed present.
- No GPS source: plug/unplug cycle works end to end.
- `numCarsAtHome` / `minBatteryLevelAtHome` count only plugged-in cars.
- An asleep, plugged-in car is HOME and is woken to start charging. An asleep, unplugged car is not HOME and is never woken or sent anything.
- Charge commands go to the car the plug evidence names, never to every car on the account. A VIN-less TWC broadcast goes only to the candidates.
- A BLE or TWC reading outranks a conflicting TeslaMate/API plugged-in.
- Fleet-only install: unplug leads to one remote restore immediately; plug-in leads to one remote re-apply.
- The `atHomeRadius` default is 1,000 ft, and an explicit config value still overrides it.
