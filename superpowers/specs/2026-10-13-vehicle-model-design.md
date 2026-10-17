# 1.4.0 vehicle model: registry, providers, desired state, reconcilers

Status: draft for review (brainstormed with Mike Bishop, 2026-10-13).
Inputs: `.superpowers/gut-inventory.md` (39 deferred items, current architecture with file:line refs), `.superpowers/settings-history.md` (why `chargeRateControl`/`chargeStopMode` exist), `.superpowers/unified-integrations-proposal.md` §4 (the earlier IntegrationOrder sketch this replaces), `.superpowers/specs/2026-10-11-plug-presence-design.md` (presence rules that carry over).

## Intent and why

TWCManager talks to cars and chargers through many channels: Gen2 TWCs over RS-485, TeslaBLE, the Owner API (read-only), the Fleet API (paid commands), TeslaMate telemetry, HomeAssistant. Today each channel is its own island:

- Per-vehicle state lives in six places (`TeslaAPI.carApiVehicles`, `settings["Vehicles"]`, `Telemetry.vehicles`, HA's list, presence dicts, TeslaBLE's per-VIN dicts). TeslaMate attaches by display name, so a BLE-only install has no vehicle object at all.
- Reads aren't dispatched: callers reach into TeslaAPI directly. Commands go through `VehiclePriority`, a static priority table (BLE 20, API 10, HA unreachable) with `commandPolicy` bolted on.
- Commands are imperative and fire-and-forget. Charge-limit state has three copies of `lastChargeLimitApplied`, per-channel dedupe flags and a `-1` restore sentinel each module interprets itself. Different channels follow different rules (#698).
- The real failures this week all came from that shape: a stray paid Fleet `set_charge_limit` after a BLE failure fell through (2026-10-11); a restore and an arrival racing on two queued commands, with a stale telemetry read deciding the outcome (2026-10-12 09:17); a Fleet zero-share stop/resume that latched at queue time and lost commands (shelved).
- The one piece that worked well is the departure restore rebuilt as reconciliation: the saved table says what the car should have, a reconciler keeps trying with backoff until it's true.

The 1.4.0 rework generalises that: one vehicle model, providers that read and act, desired state set by the decision-makers, reconcilers that converge reality on it.

## Goals

1. **One registry** of vehicles keyed by VIN, holding all per-vehicle state, fed by every provider.
2. **Providers** (Gen2 TWC, TeslaBLE, Owner API, Fleet API, TeslaMate, HomeAssistant, later others such as Teslemetry #588) declare capabilities with ranges, cost and locality; the model picks among them by a fixed local-first order.
3. **Reads** return a field's value with its source and age; callers state the freshness they need; a fresh read cascades through providers without waking the car unless the caller allows it.
4. **Desired state + reconcilers**: policy, presence and the distributor set what each car (and each TWC) should have; reconcilers converge it through providers, one attempt in flight per car and aspect, with classified outcomes and time-aware fallback.
5. **Threading that keeps the RS-485 loop real-time**: protocol only on the serial loop; a ~1 s control tick for the distributor and target publication; vehicle I/O only on per-channel lanes.
6. **Presence rebuilt on top**, as state derived from provider-reported fields, keeping the plug-presence rules.
7. **The Vehicles tab** shows the registry and, per car, what each provider reports.

## Non-goals

- Nothing in the inventory is ruled out of 1.4.0. Multi-car VIN-less TWC attribution (fingerprinting) is mostly independent and can be built separately. The two-pass distributor (admission then allocation; pass-2 fairness to be compared when we get there) is a separate design, but it now lands in the one distributor every install uses, so it should follow the move to the control tick.
- No user-configurable provider order (see Decisions).
- No change to the Gen2 RS-485 protocol handling itself.

## Anti-goals (would be a failure even if it works)

- A paid Fleet command the user's settings forbid, or one sent because a local channel failed when the rules said wait.
- A charge-limit or charge command to a car that isn't plugged in here (presence rules), or to a phantom vehicle.
- Losing a held outside limit (the saved table must survive restarts and be restored eventually).
- Waking a car for no benefit (reads never wake unless asked; don't wake to lower a limit, #698).
- Anything that blocks or delays the RS-485 heartbeat loop.
- A decision taken on a value older than our own last write to it (the 09:17 bug).

## Constraints

- Python, existing module/plugin structure; config.json and settings.json stay backward compatible (old keys read and mapped; see Settings).
- Gen2 TWC timing: heartbeats ~1 s per slave; stall warnings over 1 s on the serial loop.
- Fleet API costs money per command; user's budget is the $10/month free tier. Commands must be suppressible per provider and capability.
- BLE is a single serial radio channel (tesla-control, one process at a time); BLE timeouts are 5-15 s and retried.
- Locks: today there is no lock on `settings`, token slots or the vehicle list contents (inventory B5); the rework must not add new unlocked cross-thread mutation.
- Existing lock order invariant: BLE lock → presence lock, never reverse; no lock held across I/O.

## The model (decided)

### Registry and vehicle lifecycle

- One `Vehicle` per car. **Identity is the VIN when known.** A car with no VIN (on a VIN-less TWC before attribution, or a non-Tesla car) is an **anonymous vehicle** tied to its charging point's plug session ("unknown car on TWC 8244"). It has a control path (the TWC's amps), so it is allocated power, but it gets no vehicle commands. It merges into a VIN vehicle when attribution names it, and it ends with the plug session. The vehicle holds every field (below), presence, the saved/held limit state, desired state per aspect, the attempt record per aspect, and which providers claim it.
- **Tiers** (they govern **vehicle commands** only; power allocation is per charging point and doesn't depend on tier):
  - **observed**: some source sees the car, possibly with a read path, but nothing can command it. Example: Owner API + BLE before the BLE key is paired; a car only a TWC has seen. Reads, presence and display still work.
  - **managed**: at least one provider can **command** it: BLE key on record as paired and proven; a Fleet slot listing it with command scope; an HA entity that accepts commands. Only managed vehicles get vehicle-command desired state, attempts, and inclusion in broadcasts.
  - Example: Owner API + BLE starts observed and becomes managed when the BLE key is paired.
- **Phantoms**: a TWC-reported VIN must be well-formed (17 chars, no I/O/Q). A VIN that matches no known vehicle is **confirmed by asking the TWC for the VIN again** (a second query in the same plug session, seconds later) before it creates a vehicle. A car plugged in for the first time is simply confirmed a few seconds later; it charges meanwhile, because power goes to the charging point regardless. A mis-heard VIN fails confirmation and creates nothing; if it ever got through, it's observed only (no command path) and ages out.
- **Forgetting**: an observed vehicle unseen for N days (default 30, builder may tune) drops out. A managed vehicle that loses its last command path drops to observed and ages out from there. **Session history** (kWh, sessions; today in `settings["Vehicles"]`) is a separate record, not part of the registry: it is never consulted for membership and never promotes a car back into it.
- **Bootstrap / manual add**: the Vehicles tab gets **Add vehicle by VIN**. The VIN is format-checked (17 chars, no I/O/Q) and enters the registry as observed, **user-asserted** (not subject to TWC VIN confirmation). The user then pairs BLE from its page, which makes it managed. This is the path for a VIN-less TWC with BLE only (today there is none: the list comes only from TWC session history). Other routes still work: a VIN-reading TWC charges once and the car's page offers pairing (a user action, so it may promote); TeslaMate or an Owner/Fleet token supplies the VIN.
- **BLE status on the car's page** replaces "Not Implemented": **Not in range**, **In range** (not paired), **Pairing** (key sent, waiting for the key-card tap in the car), **Paired** (the car accepted our key; we can talk to it), **Pairing failed**, **Key refused** (the car no longer accepts the key; re-pair). "Proven" stays internal (it's what moves Pairing to Paired); it isn't shown. "In range" comes from a BLE scan for the advertisement name derived from the VIN (Tesla's BLE local name is a hash of the VIN; builder verifies the exact scheme against tesla-control), so it also catches a mistyped VIN before pairing.
- **BLE claims** can't be checked passively: we hold one keypair and only learn the car dropped it when a command is refused. A BLE key refusal is a **refused** outcome; the BLE provider drops its claim on that VIN and the Vehicles tab says to re-pair.
- No Pin, no Dormant. A car that never visits never has desired ≠ known, so nothing is attempted. The one perpetual case, a held limit on a car that vanished, backs off to hourly, never wakes; a "give up after N days and log" rule is acceptable if it ever matters.

### Fields and reads

- Every field (state of charge, charge limit, plugged in, charging state, location, online/awake, actual amps, TWC VIN, BLE reach, ...) stores value, source, and time read.
- Telemetry, presence probes, command replies and TWC heartbeats all write to the same fields.
- Callers read with a freshness bound, e.g. `vehicle.read("chargeLimit", maxAge=...)`. Fresh enough → returned at once. Otherwise a read cascades through the read-capable providers in order. **Reads never wake the car** unless the caller explicitly allows it. (Today `update_charge`/`update_location` wake over BLE on a failed read; that goes.)
- **Report-on-change sources** (TeslaMate; likely Fleet Telemetry) send a value only when it changes, so a value can be **old but current**. For such a source, a field's freshness is the **source's liveness** (connection up and the source still polling the car), not the time the value last changed: `age = now - max(valueChangedAt, sourceLiveAt)`. When the feed is unhealthy, the value ages from its last change as usual. The builder decides how liveness is detected (MQTT connection state plus evidence the source is still polling).
- **Feed lag after our own write**: liveness alone mustn't vouch for a value that predates our write. A report-on-change value older than our last write is trusted only once the feed has had time to report a change (`now - writtenAt > feedLag` while healthy) and didn't; until then, use our written value (apply) or force a live read (restore). This is the 09:17 rule generalised.
- Our own successful write stamps the field. A stored value older than our last write is never trusted over it for an apply; a restore forces a fresh read in that case (current behaviour, carried over).

### Charging points (replaces the type-specific EVSE layer)

- Each provider exposes zero or more **charging endpoints**: a Gen2 or Gen3 TWC is one; a car whose amps the Fleet API, BLE or HA can set is one (today's `TeslaAPIEVSE`).
- Endpoints that are physically the same charging session (the TWC and the car plugged into it, correlated by VIN or attribution) are grouped into one **charging point**. **Everything is merged; the merge count may be one.** Grouping happens in one generic place, by correlation, not by knowing types (today `MergedEVSE`, `getDedupedEVSEs` and `TeslaAPIController` each know about the others).
- The distributor allocates power per charging point. Within a point, the layered-actuator rule (below) decides which member carries the target.
- The #483 principles carry over (power in watts, per-controller budgets, min/max per endpoint); the class zoo shrinks to endpoint + charging point.
- **Idle TWCs keep their minimum.** An empty TWC endpoint must be offered its minimum so a plug-in can be detected; when it's plugged in, the distributor reallocates to support the new session. (Current behaviour, must be kept.)

### Providers and capabilities

- Providers: **Gen2 TWC** (per TWC, attached to whichever car is plugged into it), **TeslaBLE**, **Owner API**, **Fleet API** (the two token slots are separate providers, same implementation), **TeslaMate**, **HomeAssistant**; Gen3 TWC and Teslemetry fit the same interface.
- Each declares capabilities with **ranges** and attributes:
  - reads (list, charge, location, plug, online, VIN, amps);
  - commands: charge limit, charge start/stop, amps, wake;
  - **cost per capability (per operation), not just per provider**, plus local or remote, ready or not. Today's rough tiers: 0 local, 1 cloud free, 2 billed. Billed operations differ in price (Fleet charges differ per command type); modelling which is which is **not a goal now, but the cost field must allow it** (don't foreclose). Known data point: Fleet `GET /api/1/vehicles/{vin}` (state, online/asleep; scope `vehicle_device_data`) is documented as "This endpoint is not charged"; `vehicle_data` is billed ("polling ... will be expensive"); `wake_up` is billed.
  - **Known Fleet API prices (user, 2026-10-14)**: `GET /api/1/vehicles/{vin}` (online state) and energy-site `live_status` are **free**; commands **$0.001**/call; `vehicle_data` **$0.002**/call; **wake $0.02**/call (20× a command). So within one provider, reads differ in cost (an online-state check is free; a data read is not), and a wake is the most expensive routine operation. Cost is per operation, and read cascades should prefer free operations (e.g. check online state before a paid `vehicle_data`, never wake to read).
  - **rate limits**: cloud providers declare their limits; the lane enforces them locally (or the design stays well clear of them; builder's call, but the declaration exists so it can be enforced).
  - Known ranges/quirks: **TWC minimum and maximum are per device**: today `minAmpsTWCSupports` is 5 A for protocol-1 TWCs, 6 A for protocol-2, and set to 1 A for 3-phase units (TWCManager.py ~1244-1251, ~1397-1399), though #510 reports a 3-phase Gen2 that still wouldn't offer below 6 A; maxima come from the TWC's reported max and wiring config. Ranges must be per endpoint, discovered and overridable, not constants; vehicle amps 1..max, never 0 (0 clamps to 1; a stop must be a stop command), amps below 5 sent twice; Gen2 has no clean local stop (newer firmware ignores 0 A).
- **Gen2 TWC as a provider**: reads plugged/VIN/actual amps/offered pilot (presence evidence too); commands amps for its car, instantly and free. Its "attempt" is publishing a target the serial loop sends on the next heartbeat.
- **Disruptive stops as very high cost**: Gen2 "stop responding to slaves" (shun; Teslas tolerate ~3 per session) and the RS-485 stop command (relay drop; "not recommended for Tesla") are stop capabilities with a **very high cost**, so ordering by cost naturally uses them only when no cheaper provider exists or succeeds. **Off by default**; when the user enables them, in practice they act when no other provider can be correlated with the activity on that TWC (non-Tesla car, credential-free setup).

### Order, policy and suppressions

- **Fixed order, by cost then locality**: TWC, BLE ahead of cloud (TeslaMate for reads, Owner, Fleet, HA); per-operation cost decides and pushes disruptive and billed operations last. Not user-reorderable. A suppression removes an operation from consideration.
- **User suppressions per provider and capability**, e.g. "Fleet: never set amps", "Fleet: no commands". **Default**: "Fleet: never set amps" is on **only when the charging point has a local way to set amps** (a TWC, or BLE). For a car whose only amps path is Fleet (a UMC car with no BLE), Fleet amps are allowed by default. `commandPolicy` maps onto these: `ble_only` = cloud providers suppressed for commands; `prefer_ble` = default; `api_only` has no remaining justification and maps to default with a log notice (builder may keep it as "local suppressed" if a reason surfaces).
- **Layered actuators (replaces `chargeRateControl`)**: the car draws min(TWC offer, car amps). For a target T:
  - T inside the preferred provider's range (TWC for ≥ 6 A): preferred sets T; the other side goes to its **maximum** so it never needs touching again.
  - T outside the preferred provider's range (e.g. 4 A on a Gen2): preferred holds at its **nearest extreme** (6 A), and the next provider carries T. Holding at the floor, not the max, keeps Track Green Energy flicker (4-6 A) from bouncing the TWC 6↔48 and bounds overshoot to 6 A if the car command lags.
  - Coming back into the TWC's range, the TWC takes over; the car's amps may stay low until a later reconcile raises them (undershoot is the safe direction). Hysteresis on raising the car's amps is the builder's call.
  - This is one generic rule for any pair of members of a charging point.
- **`chargeStopMode`** becomes the Gen2 provider's stop configuration: vehicle stop (default; the TWC declines the stop, the reconciler falls through), or one of the two disruptive stops (above).
- UI keeps both settings where sensible, relabelled: "API" means "a vehicle command, by whatever channel the order picks" (BLE already lives there).

### Desired state and reconcilers

- Decision-makers stop issuing commands; they set **desired state** per car and aspect:
  - charge limit (policy limit, or the outside value to restore);
  - charging on/off;
  - amps (from the distributor);
  - plus TWC targets.
- A **reconciler** compares desired vs known. When they differ it starts **one attempt via one provider**, and records per car and aspect: in flight, provider, since. While in flight it starts nothing else for that aspect.
- Attempts run on **per-channel lanes**: BLE serial; cloud separate. A BLE timeout for car A doesn't hold up a Fleet rate for car B (today's single worker does).
- The lane reports a **classified outcome** to the record and wakes the reconciler:
  - done;
  - already satisfied;
  - unsupported (provider declines, e.g. Gen2 stop);
  - unreachable;
  - refused: auth/scope/key; retires that slot or claim (#689);
  - error.
- The reconciler decides the next step from order, suppressions, cost and **time rules**: **a paid provider is tried only after the free ones have timed out**: the local channel unreachable for a while (5 min for charge limits, as for restores today; shorter, around 60 s, for start/stop; builder tunes). Today's immediate fall-through after BLE retries (the cause of the 2026-10-11 stray command) goes. If nothing can deliver, it backs off (current restore schedule: 600 s doubling to 1 h, reset on success/arrival/plug-in).
- **Read before every write**, honouring the own-write stamp, so a stale or duplicate attempt is harmless.
- **Latency**: a fallback taking a few control ticks is acceptable (user). Urgent cases are usually BLE-reachable, and the TWC enforces power limits directly within a heartbeat.
- **Three responses when known ≠ desired**, decided per divergence:
  - **Re-assert**: our attempt didn't land (failed, or the read predates our write). Try again per the fallback rules.
  - **Adopt**: a **vehicle read newer than our last write** confirms a different value (limit 80% set in the app; car reports Charging after we stopped it). That's the user's change (below).
  - **Hands off**: the divergence is unexplained or car-internal. Example: preconditioning draws current through the TWC while we hold the car stopped and the TWC offers its minimum; the car is not "Charging". Neither re-command nor adopt; leave it alone until a vehicle read says otherwise. TWC-observed current alone is never grounds to adopt "charging".
- **User changes are adopted, not undone.** How it's adopted depends on how often the aspect's desired value changes:
  - **Slow aspects** (charge limit; charging on/off as set by policy): the user's value replaces desired until the **next real decision**: a policy transition, unplug or plug-in. A hand-set limit also becomes the new outside value (today's rule).
  - **Fast aspects** (amps under Track Green Energy, distributor start/stop): desired changes constantly, so "until the next decision" would mean "immediately overwritten". Instead the user's change becomes a **bound for the plug session**: a car whose amps the user lowered to 16 A is treated as max 16 A by the distributor; a car the user started while we held it stopped is treated as wanting charge. Bounds clear on unplug.
- **One shared charge-limit rule** in the reconciler: don't wake a car to lower its limit (#698); wake for raises and restores per current rules.
- This **replaces**:
  - `VehiclePriority`;
  - per-channel dedupe flags (`stopTryingToApplyLimit`, BLE dicts, HA's);
  - the three `lastChargeLimitApplied` copies;
  - the `-1` sentinel: a restore is just "desired limit = outside value". This also fixes HA restore.
- `apiDebugInterface` goes through the same path.

### Presence on top

- Presence is derived from provider-reported fields with sources and ages:
  - plug evidence: TWC VIN, BLE plug read, telemetry;
  - BLE reach;
  - location.
- The plug-presence rules carry over unchanged:
  - TWC/BLE outrank telemetry/API;
  - BLE reach is presence, BLE silence isn't absence;
  - 1000 ft GPS fallback;
  - presumed present at startup with no wake to discover;
  - VIN-less attribution by single candidate or BLE pilot match;
  - targeted commands, broadcasts to candidates only.
- The departure restore stops being presence logic: on unplug, presence sets desired limit = outside value; the generic reconciler delivers it.
- The existing presence stack (`presence/1..4`, deployed as `deploy/presence-3`) is **not** landed upstream as-is. Its rules and tests are ported onto the new model. Until then main keeps the old GPS presence. (The user's box is on `release/1.3.4` for pre-tag testing as of 2026-10-12; `deploy/presence-3` is the fallback build.)

### Threading

| Tier | What runs there | Never does |
|---|---|---|
| RS-485 loop | Gen2 protocol only: heartbeats, sends the current Gen2 targets, records observations (plug/unplug/VIN/amps) | compute allocations, call vehicle modules, refresh tokens |
| Control tick, ~1 s | distributor; derives presence; reconcilers compare and dispatch attempts; publishes Gen2 targets and per-car desired state | block on I/O |
| Policy | own interval (30 s default), feeds the control tick (budget, policy limit) | — |
| Lanes | BLE lane (serial), cloud lane(s); one attempt at a time per lane; report outcomes | decide fallback |

- **Everyone moves to the new cycle**, pure-Gen2 installs included: today's per-slave allocation inside `TWCSlave.send_master_heartbeat` (fair share by cars charging, flex, dampening, 6 A spike workaround, 60 s start/stop gates, re-stopping a car drawing ≥ 4 A below the minimum) moves into the one distributor on the control tick. Minimise distinct code paths; the legacy path is retired, not kept beside the new one. Its behaviours become distributor rules with tests.
- Up to one tick (~1 s) of lag on Gen2 targets is acceptable (user: policy interval is 30 s; 60 s was "a bit slow").
- Token refresh moves off the serial loop; per-slot refresh lock (#690).
- `settings` gets a lock or a single writer.

### Vehicles tab

- **List**: each car's tier, claiming providers and their status, last seen and source, presence, held/outside limits, attempt in flight / backing off. Action: **Forget**.
- **Per-car page** (already reachable; BLE pairing lives there, and its "Status: Not Implemented" is replaced):
  - merged view: each field, with the source and age of the believed value;
  - one panel per provider:
    - claim status;
    - what it last reported (BLE contact and reads; Owner/Fleet account membership, online state, last `vehicle_data`; TeslaMate last fields; HA entities; TWC heartbeat);
  - reconciler state: desired vs known, attempt in flight, last outcome, backoff.

## Left to the builder

- Concrete class and module layout, names, and the plugin interface for providers.
- How the tick, reconcilers and lanes are scheduled (one control thread vs a few), as long as the threading table holds.
- Storage and locking for the registry and `settings` (lock vs single writer).
- Forgetting interval, sighting rule details, VIN validation beyond format.
- Staleness bounds per field and per caller.
- Hysteresis for layered amps.
- Migration shims: mapping `commandPolicy`, `chargeRateControl`, `chargeStopMode`, config `vehicle.*` keys; keeping the old `VehiclePriority` name as a façade during transition if useful.
- Live testing: each step is tested on the user's box via a deploy branch before it's proposed upstream (my call). Docker `:latest` tracks main, so either keep every main step non-regressing or pin Docker first; builder's choice.
- **What to reuse from the unlanded presence branches** (user: builder's call). My assessment, to be checked by the builder:
  - `presence/1-command-queue` (2 commits, small): per-VIN queue keys, `cancel`/`queued`; fixes #667 on main and is a natural substrate for lanes. Candidate to land on main early as a bug fix.
  - `presence/2-charge-limits` (15 commits): `ChargeLimitRules.py` (pure decision rules, live-read rule, own-write stamps added later) aligns and should be carried into the limit reconciler. Its large `VehiclePriority`/per-channel changes conflict with the design (VehiclePriority is replaced); cherry-pick the rules, don't merge the branch.
  - `presence/3-plug-presence`, `presence/4-fleet-rate-queue`: presence rules, attribution and their tests port onto the model; the restore reconciler is the prototype for the generic one; the Fleet rate queue becomes amps attempts. Don't merge as-is.
- PR staging. Suggested (my call, not the user's): registry + fields/reads → providers + capabilities + suppressions (VehiclePriority façade) → desired state + reconcilers + lanes (charge limit first, then charging on/off, then amps) → threading split (control tick, distributor off the serial loop) → presence port → Vehicles tab. Each step shippable on main.
- Fixing the deferred items that fall out naturally (inventory A) as each piece lands; anything not covered gets a line in the plan.
