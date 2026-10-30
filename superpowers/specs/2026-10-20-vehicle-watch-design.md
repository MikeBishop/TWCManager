# 1.4.x vehicle watch: observing cars on chargers we don't control

Status: **approved** by Mike Bishop 2026-10-20 (builder-checked; rulings applied). Next: implementation plan.
Roadmap: **Phase 6** of the vehicle model (the Vehicles tab folded into Phase 5). Whether it lands before or after the 1.4.0 tag is the maintainer's call.
Inputs: `specs/2026-10-13-vehicle-model-design.md` (registry, providers, reconcilers, "Presence on top"), `phase5-presence-inventory.md` ("Presence model — final", 2026-10-18), `plans/2026-10-18-vehicle-model-phase5-presence.md`, `lib/TWCManager/Vehicle/Presence.py` at phase5 (`decide`, `asleep`, `checkPlug`, marks), `TeslaBLE.ping` / `_runPing` / `scanForVehicleInRange`, `TeslaAPI.onlineState` / `update_vehicle_data` (the `statusDeferral` ladder), `TWCMaster.updateChargeAtHome` (`checkCharge`).

## Intent and why

TWCManager started hardware-tethered: a Gen2 or Gen3 TWC on RS-485 tells it when a car plugs in, draws current, stops, unplugs. It now also allocates power to cars on chargers it does not control (a mobile connector, a third-party EVSE): the distributor models such a car as its own charging endpoint (`VehicleEndpoint`) and sets its amps over BLE or the cloud. Phase 5 decides where a car is from **events**: TWC plug sessions, BLE contact, pushed telemetry (TeslaMate, Fleet Telemetry), fixes, drive starts and ends, and the reads the reconciler makes anyway. It deliberately polls nothing ("no read is made just to learn presence"), and the phase5 docs say the remaining gap out loud: *a car charging away from a TWC with no telemetry feed is not watched for its departure; a separate feature for that is planned.*

This is that feature. For a car that no TWC names and no live feed covers, nothing today notices that it arrived, plugged in, started charging on its own schedule, finished, or left, except a read the reconciler happens to make for a command. The distributor then either never integrates the car into a fair share, or keeps allocating to a car that is done or gone.

The constraints that shape the answer:

- **BLE** reads are free but local only. Absence of a BLE answer is not absence of the car (RF), though it is suggestive once the car was reachable.
- **Owner API** is free, read-only for most cars, deprecated, may vanish.
- **Fleet API**: `GET /api/1/vehicles/{vin}` (online state) is free; `vehicle_data` $0.002; commands $0.001; `wake_up` $0.02; $10/month free credit. Easy to burn.
- **Sleep.** Polling `vehicle_data`, or any infotainment read, keeps the car awake. Owners notice. The phase5 anti-goal stands: never keep a car awake, never wake it to observe.

### The inference everything rests on

**An asleep car is not charging and not moving.** Charging holds the car awake; driving holds it awake; unplugging wakes it. Sleep state is free from every channel and reading it never wakes the car:

- BLE `body-controller-state` (VCSEC domain): answers while the car is asleep, needs **no key** (verified on the user's box 2026-10-20: tesla-control logs "Skipping private key loading"), takes ~2 s. Returns `vehicleSleepStatus`, `userPresence`, `vehicleLockState`, and, **only while awake**, `closureStatuses` including `chargePort` (`CLOSURESTATE_OPEN` observed with the cable in; the whole block is omitted asleep).
- Cloud `vehicles/{vin}`: `online` / `asleep` / `offline`, free, no wake.

So the watch spends almost all its time asking the one free question, and asks anything else only when the answer changes.

## Goals

1. For every registry car that no TWC names and no live feed covers, keep four facts current enough for the distributor: **here**, **plugged in**, **drawing power (amps)**, **done**. Arrival, departure, spontaneous charge start and charge completion are noticed within the cadences below, without waking the car and within a paid budget.
2. One scheduler on the control tick replaces the leftover polling in phase5: the `statusDeferral` ladder in `TeslaAPI.update_vehicle_data` (300/1800/3600 s of paid `vehicle_data`) and the 1800 s `checkCharge` refresh of cars at home (`TeslaAPI.updateChargeAtHome` via `chargeUpdateInterval`). Lib ends at or below where Phase 6 starts.
3. The BLE sleep-safe ping gains the charge-port door and works for every VIN in BLE range, paired or not.
4. A consumption-meter step (the EMS modules already polled every policy interval) triggers an immediate read, so a car that starts charging on its own is integrated into the fair share within about a minute on installs with a meter, instead of waiting for the next status check.
5. Fleet-API-only installs with no BLE and no feed are told, in the docs, to add Fleet Telemetry for presence; the watch gives them only what the free rings and the paid budget allow.

## Non-goals

- No change to how Phase 5 decides presence from events. The watch **feeds** the registry (new observations and marks); `Presence.decide` keeps deciding.
- No new paid path for arrival/departure of Fleet-only cars beyond the budgeted reads below (user, 2026-10-20: tell them to add Fleet Telemetry).
- No neighbour-EVSE (D2) or fingerprint (T13) work.
- No Vehicles tab work beyond showing the watch's state per car (what it last asked, when it asks next).

## Anti-goals (a failure even if it works)

- Keeping a car awake: any infotainment read of a car that is awake but not charging more often than the car's own sleep timeout, so it never gets to sleep.
- Waking a car to observe it. Reads never wake; only commands the reconciler already allows to wake (raises, starts) do.
- A paid read made when a free source could have answered, or made while the car is known asleep, or made past the budget.
- Marking a car plugged in on the charge-port door alone and then sending it a start or amps. OPEN is presumed, not strong (below).
- Polling a car a live feed already covers, or a car a TWC names.
- Blocking the control tick or the RS-485 loop on any of this.

## Constraints

- Python 3.8+, existing module layout; config.json and settings.json backward compatible.
- Threading table from the vehicle-model spec: the control tick decides and dispatches; BLE work runs on the BLE worker under `_bleLock`; cloud work on the cloud lane. No I/O under any lock. Lock order unchanged: `TeslaBLE._bleLock → master.settingsLock → registry leaf`.
- Fleet prices as above; Owner API paced like Fleet though free. Rate limits per provider as declared.
- The BLE adapter is one serial channel shared by tesla-control and `bluetoothctl` scans (8 s each). A ping costs ~2 s plus a possible transient retry; a scan 8 s. Budget BLE time so that commands are not starved: the watch's BLE jobs are lowest priority on the worker.
- Comment rule (user, 2026-10-17): comments say why the code is what it is; no history, no phase or ruling names.
- Line budget (user, 2026-10-20): this is feature work, so lib may grow; minimise it. Anywhere the watch can replace or fold in an existing path is worth doing, with parity rows rewritten rather than kept: the ping-then-read in `Presence.checkPlug`, the pre-read ping in `Presence.pick`, the pre-command sleep ping in `Reconcile.Run.runAttempt`, the 120 s cache in `TeslaAPI.onlineState`, and HomeAssistant's own polling are the candidates. The named deletions (ladder, `checkCharge` interval) do not pay for the scheduler on their own.

## The model (decided)

### Who is watched

**User, 2026-10-20:** every registry car (accounts are not shared), **except** while a TWC names it (its state changes arrive on the heartbeat) and except while a **live feed covers it** (a report-on-change source whose registered liveness is current; `Vehicle.syncSource` is not `TeslaAPI`). Feed liveness suppresses the watch per car; when the feed goes down (broker or telemetry server; on phase5 a sleeping car never makes a feed stale) the watch resumes for that car at once. Anonymous (VIN-less) vehicles are never watched; they live on their charging point.

**Refinement (my call, after the builder check):** a TWC-named car is still read for **battery level and charge limit** while its TWC reports current flowing (`reportedAmpsActual` ≥ 1 A, or a Gen3 unit's vitals showing power), at the "HOME, charging" row's Ring 2 cadence, through the ordinary read cascade (BLE free, cloud against the budget). The heartbeat carries no state of charge and Gen3 is most of the installed base; `Policy.limitOverride` and user policies test `minBatteryLevelAtHome`, and a stale-low level makes that override land above the car's real charge. An idle TWC-named car is not read: its level does not change. The power-start `checkCharge` (F11) is the same read, requested at once.

### Three rings, cheapest first

| Ring | Sources | Cost | Sleep impact |
|---|---|---|---|
| **0 passive** | BLE advertisement scan (`scanForVehicleInRange`); EMS consumption step; TWC heartbeats; pushed feeds | 0 | none |
| **1 status** | BLE `body-controller-state` (`ping`): asleep/awake, in range, charge-port door while awake; cloud `vehicles/{vin}` (`onlineState`): online/asleep/offline | 0 | none |
| **2 read** | BLE `state charge` / `state location` (`TeslaBLEProvider.fetch`); cloud `vehicle_data` through the read cascade | 0 local; $0.002 cloud | resets the car's idle timer |

Ring 2 never runs on its own clock except while the car is **confirmed charging**. Otherwise it runs only on a **transition** Ring 0 or 1 reports, or on an EMS trigger. Ring 1 runs on a slow clock. Ring 0 scans run only when they can change something (an away car that BLE could catch arriving; an awake home car that may be leaving).

Source choice within a ring: local before cloud, as the provider order already says. A car with a BLE claim or in a BLE-capable install uses the ping; the cloud status check is for cars BLE cannot reach (no adapter, Docker without `bluetoothctl`, or two consecutive scan misses while the car is awake, which is the departure case).

### Cadences by situation

Defaults, all configurable; the builder may tune within the stated intent. "Ping" means the Ring 1 source for the car.

| Situation (from `Presence.decide` and `asleep`) | Ring 0 | Ring 1 | Ring 2 |
|---|---|---|---|
| HOME, asleep | none (it cannot leave or charge asleep) | 10–15 min | none |
| HOME, awake, not charging | none: an unanswered ping already falls back to a scan (`_runPing`), which is the departure check | 3–5 min | once at the asleep→awake transition (what woke it?); then not again for `sleepCourtesy` (20 min) unless a transition or trigger |
| HOME, charging (a read said Charging) | none | 5 min (asleep ⇒ finished, free) | amps every 5–10 min; BLE free; cloud counts against the budget |
| NOT_HOME, asleep | none (it cannot move asleep) | 15–30 min | none |
| NOT_HOME or PRESUMED, awake | BLE scan 2–3 min (arrival, free) when a scan is possible | 5 min | one location read, not before the minimum return time from the last fix (`is_far_from_home` logic), and only when no scan is possible; back to Ring 1 after |
| Feed reports `offline` (Fleet Telemetry says DISCONNECTED; a sleeping car looks like this) | as the asleep rows | BLE ping only, if possible; the cloud check would say the same | none |

Latency the user accepts (2026-10-20): such cars do not share a circuit, so a slow Ring 1 is not a safety issue; under Track Green Energy an unnoticed car is house load and the others back off by themselves. The cost of lateness is fairness only. Hence 10–15 min at home asleep, and the EMS trigger as the fast path where a meter exists.

### What each observation does

- **Ping answers (BLE).** Writes `state` (`asleep`/`online`, source TeslaBLE) and `bleReach` True as today. New: while awake, writes **`chargePortOpen`** (new registry field, bool, source TeslaBLE) from `closureStatuses.chargePort`. `_noteSleep` grows by the one field. The ping no longer requires `"TeslaBLE" in v.claims`; any well-formed VIN with `canScan()` may be pinged (the command is unauthenticated).
- **Charge-port door, asymmetric trust (my call, user did not object 2026-10-20):**
  - CLOSED while awake ⇒ **unplugged, strong**: `Presence._plug` returns False for it; `noteObservation` marks `unplug` exactly as for a `pluggedIn` False from TeslaBLE.
  - OPEN while awake ⇒ **presumed plugged**, not plug evidence: it never marks `plugIn`, never creates a `VehicleEndpoint`, never makes a start or amps applicable. It makes the watch do one free BLE charge read (Ring 2, local) to confirm; the read's `chargingState` is the strong evidence, as today.
  - Asleep ⇒ the block is absent; the last awake reading stands, because unplugging wakes the car.
- **Sleep transitions.** awake→asleep: nothing to read, and no reading is fabricated (never write a `chargingState` the car did not report). `VehicleEndpoint` consults `Presence.asleep(v)` (my call, after the builder check):
  - asleep ⇒ `isCharging` False and `currentAmps` 0: an asleep car draws nothing, whatever its last reading said.
  - asleep and the last `chargingState` was **Charging** ⇒ `wantsToCharge` False: something ended the session without us (the limit was reached, or the owner stopped it); a car that finished sleeps and stays asleep, so its share must be released now, not at the next wake.
  - asleep and the last reading was **Stopped** (paused by us or by its schedule) ⇒ `wantsToCharge` stays True: the distributor may offer it power, and a start is the one command allowed to wake a car, as today. Nothing else about paused-car resumes changes.
  - asleep→awake at home ⇒ one Ring 2 read, which settles Complete vs Stopped vs Charging from the car's own report.
- **Arrival read (user, 2026-10-20).** A car that has just arrived gets **at least one Ring 2 read** (battery level, charge limit, charge state), whatever brought it home: a TWC plug-in naming it, a pushed plug, BLE contact, a parked fix inside the radius. A policy that fires on a low battery (the user has one) can only see it through that read. The TWC rule above (read only while current flows) does not exempt a plug-in with no current, say a car waiting on its schedule: the plug-in itself is the event. Local first, cloud against the event class of the budget, never a wake.
- **Scan hit** on an away car: `bleReach` True, `contact` mark, so `decide` says HOME on BLE contact as today; then a ping; OPEN + awake ⇒ a confirming charge read.
- **Scan misses.** One miss says nothing (phase5 rule). Two consecutive misses while the car was last known **awake** and its last ping was CLOSED or unanswered ⇒ `bleReach` False, `absent` mark, as `scanForVehicleInRange` writes today; `decide` then re-opens HOME. A miss while the car is known asleep is RF, ignored, no mark.
- **Cloud status check** writes `state` with the slot's source, as `onlineState` does today.
- **Ring 2 reads** go through `vehicle.read(field, maxAge=0, force=True)` and the read cascade, never with `allowWake`.

### EMS trigger (user, 2026-10-20: build it)

- Runs on the policy thread where consumption is already fetched every `policyCheckInterval` (30 s default). Needs a consumption value (`master.getConsumption()` from a configured consumption source); with none it is inert.
- **Unexplained load** is the detector's input: consumption minus the draw TWCManager already knows about, computed **inside the detector** (my call, after the builder check): Gen2 `reportedAmpsActual`, Gen3 vitals power, and each watched car's last known `actualCurrent` while it is known Charging. Subtract only when `subtractChargerLoad` is set, since that setting says whether the meter sees the chargers at all. `getTotalAmpsInUse` today sums Gen2 slaves only (no Gen3, no vehicle endpoints), so `getChargerLoad` and the green-energy maths already treat a mobile-connector car's draw as house load; fixing that globally changes offers for every Track Green Energy user and is a **separate issue**, not this feature.
- **Step up:** unexplained load rises by at least the car minimum for the configured phases (5 A single-phase, 1 A per phase three-phase, times voltage and phases: ≈1.2 kW single-phase, ≈0.7 kW three-phase at 230 V), or a meter noise floor the builder sets if that is higher, between two consecutive polls and holds for the next one, while some watched car is HOME or PRESUMED, awake or of unknown sleep state, and not known Charging ⇒ Ring 2 read of that car now (BLE if possible; cloud against the budget). More than one candidate ⇒ read in presence order (HOME before PRESUMED), stop at the first that reports Charging.
- **Step down** of the same size while a watched car is known Charging ⇒ Ring 2 read now (finished or paused?).
- The step is a trigger only; it never decides. A dryer looks the same. Debounce: at most one triggered read per car per 5 min.

### Budget

- One **token bucket per account** (per cloud provider) for the watch's paid operations, filled from a monthly cap (config `watch.monthlyBudgetUSD`, default a fraction of the free tier, my call: $3). The free tier is a $10 credit a month that must cover **every** Fleet interaction: commands, wakes, `vehicle_data`, and Fleet Telemetry itself (cheap: $1 per 150k values sent; user, 2026-10-20). The default leaves room for the rest; the setting lets a user who runs no feed spend more. at a steady rate, holding at most one day's worth. Only the watch's own reads draw from it. Reconciler commands and the reads they make before a write, and attribution reads, do not: those are command costs under the per-desire paid budget that already exists; the two never share tokens.
- **Two token classes, ranked** (my call, after the builder check): **event reads** (a transition or an EMS trigger: a charge starting, finishing, a car arriving or leaving) may spend the whole bucket; **routine reads** (amps while a car is confirmed charging, the TWC-named battery refresh) may spend only what is above a floor (half the bucket, builder's call), so a day of routine reads never starves the reads that change an allocation. At $0.002 a read, $3 a month is about 50 reads a day; cloud routine amps reads therefore default to **15 min**, not 5–10, and a car no provider can control (`VehicleEndpoint.isReadOnly`) gets Ring 1 only, never routine Ring 2: nothing can act on its amps, and under Track Green Energy its draw is house load anyway.
- Empty bucket ⇒ cloud Ring 2 stops; Ring 1 continues (free). Inference degrades gracefully: asleep ⇒ not charging and not moving still holds; awake ⇒ the last known allocation stays until a transition, a trigger with a local read, or tokens return. Log once when the bucket first empties, once when it refills.
- Owner API reads are free but paced like Fleet; they draw a zero-price token so the pacing applies.

### What it replaces

- `TeslaAPI.update_vehicle_data`'s `statusDeferral` ladder and `is_far_from_home`'s only use: the watch owns when its cloud reads happen. **What throttles the other paid reads once the ladder is gone (answered after the builder check):** the read cascade's own freshness bound. The reconciler's read before a write and `update_charge` already ask with `maxAge=READ_MAX_AGE` (300 s), which is exactly the ladder's at-home deferral, so at home nothing changes; away, a read is made only for an applicable message, which `Presence.applicable` already denies to a NOT_HOME car except a restore, and restores back off hourly. The deferral field survives only as the two-thread dedupe inside `update_vehicle_data` (a read in flight on one thread makes the other wait for its result, not pay again); it is never set to a watch cadence, so a reconciler read never gets a stale stored value because the watch chose to wait. The watch's own reads pass `force=True`.
- `TeslaAPI.updateChargeAtHome`, `chargeUpdateInterval` (the `cloudUpdateInterval` config key, 1800 s) and the `checkCharge` queueing from `minBatteryLevelAtHome` go **entirely** (user, 2026-10-20): the arrival read, the reads while charging and the TWC-named refinement above keep every HOME car's battery level as current as the policy needs, so `minBatteryLevelAtHome` and `numCarsAtHome` read the registry and queue nothing. `cloudUpdateInterval` is accepted and ignored, logged once, noted in Settings.md and the changelog. The power-start read (F11) stays as a "read now" request to the watch from `TWCSlave`; whether the `checkCharge` task name survives as its carrier is the builder's call.
- **Line count** is `git ls-files lib | grep '\.py$'`, as every phase counts it; `HTTPControl.py` is in it, templates are not. The named deletions are about 60 lines; the builder estimates the additions at 250 or more before folding in the candidates listed under Constraints. Each task reports before and after, as in Phase 5.
- Docs, Fleet Telemetry: recommend `minimum_delta` in the telemetry config for values whose small changes nobody needs (`ChargerVoltage`, `ACChargingPower`, `BatteryLevel`), so a feed costs fewer values; the 60 s intervals stay. One paragraph in `Vehicle_FleetTelemetryMQTT.md`.
- Docs: the phase5 "no polling" paragraphs in `PolicyCustomization.md` and the `Vehicle_FleetTelemetryMQTT.md` fallback paragraph gain the watch: *status checks are free and never wake; reads happen on change; a car a feed or a TWC covers is not watched.*

### Vehicles tab

Per car, one line: watched or not (and why not: TWC names it / feed covers it), last Ring 1 answer and when, next check due, paid tokens left. No new page.

### Settings

`config.json` → `watch` (all optional): `enabled` (default true), `homeAsleepSecs`, `homeAwakeSecs`, `awayAsleepSecs`, `awayAwakeSecs`, `chargingReadSecs`, `sleepCourtesySecs`, `scanAwaySecs`, `monthlyBudgetUSD`, `emsTrigger` (default true when a consumption source exists). Names are the builder's; the set is the contract.

## Left to the builder

- Module layout: a leaf `Vehicle/Watch.py` holding the per-car schedule (next-due per ring, last answers) is the obvious shape; it is state, so it needs the registry's lock discipline. The control tick asks it "what is due" and dispatches to the workers; it never does I/O on the tick.
- Exact cadence defaults within the table's ranges, and hysteresis on the "two scan misses" rule.
- Token-bucket arithmetic, the routine-read floor, and persistence across restarts (a restart must not refill the month).
- A third priority level on `VehicleCommandQueue` (it has only `isHigh` today) so the watch's BLE jobs yield to commands and user-requested scans.
- The EMS step detector's exact window and how it reads the consumption source without blocking policy evaluation.
- Whether `is_far_from_home` survives as the away ETA rule or the ETA is computed from the fix and a configured speed; either is acceptable.
- Tests: parity rows for each cadence row above; a loop test that an awake-not-charging car at home gets at most one infotainment read per `sleepCourtesy`; a test that an asleep car is never read; a test that the EMS step triggers exactly one read and a dryer step with no awake watched car triggers none; a budget test that an empty bucket stops cloud reads and leaves Ring 1 running; a test that a feed going live suppresses the watch and going down resumes it; the chargePort asymmetry (CLOSED marks unplug, OPEN never marks plugIn).
- Live testing on the user's box via a deploy branch before the PR, as for every phase; the box has BLE and TeslaMate, so the feed-down case is tested by stopping the TeslaMate tunnel.

## Evidence

- 2026-10-20, user's box, car asleep and plugged at the TWC (status 09): `tesla-control -ble -vin … body-controller-state` answered in ~2 s without a key: `vehicleSleepStatus: ASLEEP`, `userPresence: NOT_PRESENT`, `vehicleLockState: UNLOCKED`, no `closureStatuses` (raw VCSEC payload has fields 3, 4, 8 only). Same command with the car awake: full `closureStatuses`, `chargePort: CLOSURESTATE_OPEN`.
- Fleet prices and the free `vehicles/{vin}`: vehicle-model spec, user 2026-10-14.

## Addendum 2026-10-21: one presence rule for cars only the Tesla API can see

Status: **draft for the user's approval** (discussed with Mike Bishop 2026-10-21; nothing built yet).

### Why

Asleep/awake says nothing about where a car is or whether it is plugged in. What polling learns is the **asleep→awake edge**, and a read on that edge learns the rest. The API is needed only where nothing else sees the car come and go. Installs with such a detector should make no presence polls at all.

| Install, for a watched car | How departure and arrival are seen | Cloud presence polling |
|---|---|---|
| A live feed (TeslaMate, Fleet Telemetry) | pushed | none (the car is not watched) |
| BLE loaded and usable | contact and misses at home, scan hits on return | none; reads on wake edges go over BLE (free) |
| Only the Tesla API (no BLE, or BLE unusable) | nothing | **this rule** |

A TWC alone is not a presence detector: it sees the car only while plugged in, and a car its TWC names is already not watched. A held command keeps its own wake check in every install (Phase 5's rule; for a watched car, the watch's status checks serve it).

### The rule (API-only watched cars)

Home is a return time of 0.

1. **Poll for the edge.** Outside a deferral, ask the free status question (`vehicles/{vin}`): homeAsleepSecs or awayAsleepSecs while it says asleep, homeAwakeSecs or awayAwakeSecs while awake.
2. **Read the car** (charge state and position, one event-class read through the cascade; Owner free, Fleet paid against the budget):
   - on the asleep→awake edge, anywhere; or
   - while it is awake and its last fix is older than max(return time from that fix, sleepCourtesySecs).
   At home this is one read per courtesy window while awake. A parked car usually sleeps within about 15 minutes, so in practice one read per wake. It cannot keep a car awake. Away, it reads again only once the car could be back.
3. **Defer.** After a read, nothing runs for that car before fix time + return time. Return time is the straight-line distance home at returnKph (120 km/h), at least 300 s. That means no status checks, no reads and no scans; a fix 3 hours out means 3 hours of silence. A new fix from any source moves it.
4. **While charging** (user, 2026-10-21: "paid charging reads should be minimal; that's fine for free ones"):
   - **Free reads (BLE, Owner)** keep the charging-read cadence (chargingReadSecs). They keep the battery level, the draw and Complete current.
   - **Paid routine charging reads (Fleet)** run only when something needs the battery level: a policy condition that reads it (`minBatteryLevelAtHome`, the policy limit override), at cloudChargingReadSecs. Otherwise there are none. The car's finish is learned from it falling asleep ("asleep after Charging" releases its share, about 15 minutes after it stops), and the consumption step works from the last known draw.
   - The TWC-named read while current flows follows the same split: free reads as now; paid only when a policy reads that car's battery.

### What it buys

Arrival, departure, plug and charge state for an API-only car, so that configuration is fully supported. Each read is bounded by the courtesy window and the distance. A departure while the car is awake is seen within one courtesy window, before the car sleeps elsewhere. That avoids the case where a later power offer pays for a wake (~$0.02) only to find the car gone.

### What it replaces

- The away-location read, its once-per-awake-stretch bookkeeping and the driving re-read.
- The cloud status checks for a car Bluetooth has lost in a BLE install (user, 2026-10-21: "BLE installs don't poll the cloud unless they're waiting to send a Fleet command"). This reverses the 2026-10-20 ruling that a lost car with a TeslaAPI source is scanned only while the cloud says it is awake. BLE installs use the scan back-off alone for arrival, and poll the cloud only while a Fleet command is held.
- Reading an awake car at home only on the edge and while charging: the edge read stays, and the courtesy-window reads are added for API-only cars.

### What stays

The BLE paths (ping with the door, scans with back-off, the lost-car rule), amps reads while charging off a TWC, the consumption-step trigger, the budget, and the TWC-named read while current flows.

### Cost

- **Owner API:** free.
- **Fleet only:** about one $0.002 read per wake at home, plus one per wake away once its return time has passed. For a car with a few trips a day, about $0.01 a day, out of the event-class budget. There are no routine charging reads unless a policy reads the battery.
- **Docs:** still recommend Fleet Telemetry for Fleet-only users, as the cheaper option, not the only one that works.

### Expected size

It should shrink Watch.py: one condition replaces three away-handling paths and their state. The builder reports the delta.
