# Fleet-only charging: free snapshot polling and history backfill

Date: 2026-11-01. Size: project. Status: design, awaiting approval.

## Intent

A car that only the Fleet API sees (no TWC naming it, no BLE, no Fleet
Telemetry/TeslaMate feed) is watched by `Watch.py` on paid reads paced for
cost. On two nights running, the TWC-less instance on the box missed most or
all of a charge session in the charge history (`/api/getHistory`): its paid
reads landed just before current started and just after it ended, and the
EMS (Powerwall) load step in between produced no useful read.

The free `vehicle_data_cached` snapshot (provider `FleetAPICached`, landed in
#742) carries everything needed to reconstruct a session after the fact. The
user's position: **the history must be eventually correct, not timely.**
Anyone who needs to-the-moment data needs a source that is either a live feed
(Telemetry, BLE, a TWC/Gen3 reporting amps) or free to read. Live control does
not need live data either: we set the rate, so we know the most the car can
draw, and a wrong belief corrects itself through the command it provokes.

## Evidence

### Two missed nights (main instance, TWC-less, Fleet only, Powerwall EMS)

- 2026-10-31: TWC drew 01:12:12-01:34:31 (~5 kWh). Paid reads 01:12:01 (wake
  for a limit change, ~10 s before current) and 01:33:17 (the 20-min
  courtesy/location read). History showed 01:30-01:50: 20 min late, and
  48 A credited ~15 min after the stop.
- 2026-11-01: TWC drew ~00:06-00:23 (3.35 kWh). Paid reads 00:05:41 and
  00:26:51. History showed nothing. Powerwall consumption went
  ~1.3 kW -> ~13 kW at ~00:06; no read followed.

Why the load step produced nothing (code path; the DEBUG lines that would
confirm it were not logged): `loadSample` asked a read; `Watch._read` first
fetched the free snapshot with `cutoff=lastRead`, the watch's *own* last
read, which predates the reconciler's paid reads. The newest snapshot (from
before the start, saying `Complete`) cleared that cutoff, answered the read,
and the ask was consumed. An up step re-asks only after 1200 s
(`sleepCourtesySecs`).

### 24 h of free polling (once a minute, 2026-10-31 23:11 to 11-01 22:54)

TWC (fake master) as ground truth, 1-minute resolution:

| Session (TWC) | Snapshots seen | Main instance |
|---|---|---|
| 00:06-00:23, 3.35 kWh | 00:05:27 Complete 0.26 · **00:10:42 Charging 1.02 kWh 11 kW** · **00:23:05 Complete 3.28** · 00:28:05 · 00:33:17 | missed |
| 08:10-08:33, 0.64 kWh | 08:08 Complete · 08:43 Complete | missed (cabin preconditioning; see non-goals) |
| 19:31-19:37, 1.17 kWh | 19:26:48 Disconnected · **19:35:49 Charging 0.82 kWh** · **19:37:00 Complete 1.06** (1 s after our `set_charge_limit`) | 1 min |

Findings, with the #742 probes (2026-10-28) for comparison:

- No snapshot on charge start; the first `Charging` snapshot came 4-5 min
  after current started, both times (#742: "not on charge start", "~5 min
  after charging activity").
- Mid-charge cadence is not a reliable 5 min: one 12-minute gap
  (00:10:42 -> 00:23:05) during a charge.
- A snapshot within a minute of a stop, both times (#742: 3-7 s after a
  charge ends). One came 1 s after a command.
- ~5-minute snapshots for a while after a stop; none while asleep (00:33 ->
  08:08).
- `charge_energy_added` resets at a new session, survives the stop (still
  readable hours later, drifting down slightly: 3.30 -> 3.18), and is
  battery-side: 91-98 % of what the TWC metered (1.06/1.17, 3.28/3.35).
- Back-calculating the start as `stamp - energy_added / power` gave
  00:05:06 (truth 00:05:46-00:06:46) and 19:31:21 (truth 19:30:47-19:31:47).
  The end from the energy delta between snapshots gave ~00:23:00 (TWC zero
  by 00:23:46).
- All 1,484 polls answered 200. Free polling at 1/min caused no visible
  problem. Neither of the two charges would have been missed.

## Goals

1. The charge history for a Fleet-only car is eventually correct: each
   session's start, end and energy are reconstructed from snapshots, to
   within about a minute and the battery/wall efficiency.
2. Detecting a charge needs no paid read: suspicion plus free polling until
   a snapshot newer than the suspicion arrives.
3. Control works from the commanded rate, an upper bound, and self-corrects
   through the command -> read loop instead of paid polling.
4. Fewer paid reads than today for a Fleet-only car, never more.

## Non-goals

- Live (to-the-moment) charge data from Fleet. Users who need it need a
  live feed or a free live read; user-facing docs say so.
- Cabin preconditioning or other non-charging wall draw (charge fields stay
  `Complete`, `charger_power` 0). Snapshot timing is not ours to control,
  so it cannot be reconstructed reliably (user's call).
- Location: snapshots never have it. The 20-minute courtesy/location read
  (`late`, `fix` in `Watch._visit`) stays paid and unchanged.
- Owner API installs (412 on the endpoint): behave as today.
- Cars a TWC names, or a live feed covers: unchanged; their sources already
  report live.
- The `charge_start` "not accepted" classification (see Related).

## Anti-goals

- Polling a sleeping car's snapshot on a clock (nothing changes; pointless
  traffic). Polling only while a suspicion or a session is open.
- A history that invents energy: when evidence is missing (car slept
  without a stop snapshot), the session ends at the last snapshot, losing
  energy rather than adding it.
- A paid read where a free poll would do.
- Library growth beyond the feature. Look for duplication with the
  existing watch read and history code; don't fork a second watch.
- Comments explaining history; comments say why the code is as it is.

## Approaches considered

1. **Free snapshot polling + backfill (chosen by the user).** Poll the free
   snapshot while a suspicion or session is open; reconstruct the session
   from `charge_energy_added`; control on the commanded rate. Eventually
   correct, zero marginal cost, late by one snapshot (~5 min at a start).
2. **Paid reads after each trigger, with the cutoff fixed.** Simple, and
   live within a minute, but each trigger costs 0.002 USD and the trigger
   rate on an average day (HVAC, dryer, every rate change) is unbounded by
   anything but the 20-minute courtesy window. Rejected on cost.
3. **Require a live feed for Fleet-only history.** Correct and simple, but
   abandons Fleet-only installs. Kept as the docs' advice for anyone who
   needs live data, not as the design.

## Design

### 1. Suspicion: what opens a poll

A per-car record "something may have changed since T" (T = the event's
time). Opened by:

- today's triggers in `Watch._visit`/`loadSample`: an up or down load step
  (T = the step's first sample), a wake, an arrival, a plug-in mark, the
  charge port opening;
- any command we send the car (start, stop, amps, limit) that the car
  accepted or answered (T = the command's send time);
- the staleness check (section 4).

An up step suspects every watched car at home that is awake or of
unknown state. A car believed asleep is not suspected; instead the step
asks its free, live online check at once (user's decision). Still asleep:
its snapshot stands, since a car uploads one ~16 s before sleeping and
cannot charge asleep. Awake: it is suspected like any awake car, with T
the step's time.

The 1200 s throttle on an up step goes: it existed to bound paid reads. A
free poll needs only to avoid piling up: a car with a suspicion open
extends it (keeps the earliest T) rather than opening a second.

### 2. The poll

While a suspicion is open, fetch the snapshot about once a minute
(builder tunes; the 24 h log used 60 s) until one is stamped at or after T.
Then:

- `Charging`: open a session (section 5) if none is open, starting at the
  earliest load-step T if one is recorded in the last ~10 min, else at
  `stamp - charge_energy_added / power`. Close the suspicion.
- Anything else with a session open: close the session (section 5).
- Anything else, no session: close the suspicion.

Give up after ~10 minutes with no newer snapshot (builder tunes; starts
took 4-5 min). Giving up does not pay; the next trigger or the courtesy
read catches up, and backfill corrects the history whenever a snapshot
does arrive.

This replaces the event read's "free snapshot first, else pay" for
Fleet-only cars: an event no longer buys a paid read. Routine paid reads
while charging (`cloudChargingReadSecs`) go too: an open session polls.
Policies that read battery level get it from snapshots, 5-12 min apart
while charging. That is enough for their purpose, offering power to a car
below a low threshold such as 20 %; some staleness and overshooting the
threshold is acceptable, and better resolution needs Telemetry or BLE
(user's decision).

The read's cutoff is the suspicion's T, never the watch's last-read time.
This uses the `cutoff` #742 added to `ProviderOrder.read`
(Order.py); its short in-fetch `wait` #742 built for "3-16 s after an event"
is not enough for a charge start, so the one-minute poll lives in the
watch, not the provider.

### 3. Control belief: the commanded rate

Today a cloud-read car's draw is its last `actualCurrent`, read by
`Watch.chargingAmps` (house-load subtraction) and by `_drawAmps`/`_drawing`
in TWCMaster (circuit allocation: what one charging point has taken from a
shared budget). Both change to one belief per car:

- After a command, until a reading stamped after the command arrives:
  **the higher of** the last reading and the commanded amps. An accepted
  start counts as charging at the commanded amps (the last reading was 0).
  A lowered rate or a stop keeps the old, higher draw.
- Otherwise: the last reading, as today.

Never allocate on the assumption that a car obeyed (user's decision).
Moving from one car to two, the second car gets its full share only once
a reading confirms the first has come down; until then it gets what is
left under the first car's old draw. A lowered rate therefore opens a
suspicion (section 1) so that confirmation comes as soon as a snapshot
does. Raising a rate is safe to believe at once: it is the upper bound.

Found while planning: circuit allocation already behaves this way. Its
`taken` (TWCMaster ~745) is `max(new share, _drawAmps)`, and a cloud
car's `_drawAmps` stays its last reading until a newer one, so a lowered
car holds its old draw and a started car counts at its share. Allocation
needs a test pinning that, not a change; only `Watch.chargingAmps` (house
load) moves to the belief.

The start/stop hold logic (TWCMaster ~656) keeps reading the car's actual
state, not this belief: it is about what the car did (designer's call).

Why this self-corrects (the user's argument):

- Car stopped unseen: we still subtract its believed draw, house load
  looks lower, the policy offers more, a rate change goes out, the command
  opens a suspicion, the poll sees `Complete`.
- Car started unseen: its draw counts as house load, the policy offers
  less, a rate change goes out, same loop.
- Rate pinned (scheduled at maximum, green at its floor): no command, no
  correction, but nothing to correct for control either. History is fixed
  by the stop snapshot and backfill.

### 4. Staleness check

If the charger load we believe (`getChargerLoad()`) exceeds the EMS's
`getConsumption()` by more than the step threshold
(`LoadStep.threshold`), on two consecutive samples (the car ramps
10-30 s after a rate change, while we credit the new rate at once), a
watched car believed charging cannot be drawing it: open a suspicion
(T = the first of the two samples) for each such car. Only with an EMS
that reports consumption and `subtractChargerLoad` on. It is a sharper
form of the down step: unthrottled, and still fires when the step itself
was lost in noise, but at a 6 A draw beside a 1-2 kW house it may not fire,
and the down step still covers that.

### 5. Sessions and history

`sampleHistory` today keeps one mean watt figure per 5-minute bucket
(`settings["history"]`, 2 days), appended at each boundary, summing every
charger `getChargerLoad` counts. Backfilling into those totals would mean
separating one car's share out of a sum after the fact.

Instead (designer's call):

- Buckets keep what is known live, as today: TWC slaves, Gen3 units, and
  watched cars whose charge readings come live (a feed, or BLE in range).
- A car whose charge readings come from the cloud (`cloudOnly`, or a BLE
  car the radio has lost and the watch reads through the cloud) gets a
  session ledger instead, and its draw leaves the buckets
  (designer's call: `getChargerLoad` for control is unchanged; history
  sums a variant without those cars). This ledger: segments `(start, end, watts)`,
  persisted in settings beside `history`, pruned at the same 2 days.
- `/api/getHistory` (and the live bucket from `historyWatts`) adds each
  segment's overlap with each bucket to the measured figure.

A session's segments:

- Open: from its start (section 2) to "now", at the believed rate
  (section 3). Provisional.
- Each new `Charging` snapshot S after the previous P: the segment
  `P.stamp -> S.stamp` gets `(S.energy - P.energy) / (S.stamp - P.stamp)`,
  scaled battery -> wall (below). The open segment continues from S.
- The closing snapshot C (not `Charging`): the session ended at
  `P.stamp + (C.energy - P.energy) / P.power`, capped at C's stamp; that
  segment is written, and anything credited after the end is trimmed.
- The car falls asleep or goes away with a session still open and no
  closing snapshot: end at the last `Charging` snapshot's stamp (anti-goal:
  never invent energy).
- First snapshot of a session: the segment from start to S.stamp gets
  `S.energy` over that span.

Battery -> wall: divide energy by an efficiency, default 0.93 from the
measured 0.91-0.98; or derive watts from the snapshot's
`charger_actual_current * charger_voltage` and use energy only for
durations. Builder picks after checking which matches the TWC better on the
logged sessions.

`charge_energy_added` must be observed: `_observeCharge` (TeslaAPI.py)
does not map it today. A drop between snapshots
of one session means a new session started: close the old at P and open a
new one.

### 6. What stays

- The free online/asleep status check and its cadence.
- The paid courtesy/location read for a cloud-only awake car.
- TWC, Gen3, BLE, Telemetry, TeslaMate paths.
- Watch budget accounting for whatever paid reads remain.
- The reconciler's pre-write reads (`Reconcile/Run.py`): already free
  snapshot first since #742; out of scope (designer's call).

### Docs and changelog

- `docs/modules/Vehicle_TeslaAPI.md`: an installer FAQ: with Fleet only,
  charge history fills in a few minutes late but correct; for live data
  (green tracking that follows the sun minute by minute), use Fleet
  Telemetry, BLE, or a TWC/Gen3 that reports current. Capabilities, not
  internals; "EVSE", not "charger".
- `CHANGELOG.md`: check the last release tag first. The missed history
  shipped in a release only if the TWC-less watch did; if it did, one
  Bugfixes line, else one Features line. 1-2 sentences, verb first.

## Constraints

- Lines: a feature, so some growth, but small. Candidates for sharing:
  the watch's existing read submission (`_submit`, `_settle`, workers),
  `LoadStep`, the cutoff plumbing from #742. Paid-read code that this
  retires (the event read's pay-if-stale branch and the routine charging
  read, for Fleet-only cars) comes out.
- Gen3 behavior must not regress (Gen3 units stay in the measured buckets).
- Rate limits: one free fetch per car per minute only while a suspicion
  or session is open; nothing while asleep with nothing open.
- Polling must not become near-continuous through ordinary house-load
  variation (anti-goal). First estimate, replaying `LoadStep` (threshold
  1200 W: 5 x 240 V x 1 phase on the TWC-less box) over the 24 h log's
  1-minute Powerwall readings: 10 up and 10 down steps in the day, at most
  ~166 poll-minutes if every step opened a 10-minute poll; only an up step
  with the car awake at home, or a down step with it charging, opens one,
  so far fewer. One day, one season, 1-minute samples: a 30-second load
  log over a couple of weeks (running on the box from 2026-11-01) settles
  it before the plan fixes the give-up time. If the rate is too high, the
  levers are the threshold and the give-up time, not paid reads.
- Tests (unit): suspicion cutoff ignores the watch's last read; an
  asleep car is polled on an up step and never woken; poll gives up without
  paying; session start from a load step vs from energy; segment watts
  from energy deltas; end from the closing snapshot; trim after a stale
  belief; sleep without a closing snapshot ends at the last `Charging`
  stamp; energy drop opens a new session; staleness check needs two
  samples; commanded amps replace `actualCurrent` until a newer reading;
  history API sums buckets and segments; settings round-trip and 2-day
  pruning.
- Live check on the box (deploys pre-approved; note rollback): one night
  of scheduled charging on the TWC-less instance, compared bucket by bucket
  with the fake master's history; and a count of paid requests before and
  after.

## Related, out of scope

- `TeslaAPI.command` keeps a refusal reason only if it is a bare
  `[a-z_]{1,40}` code. Through the vehicle-command proxy the 2026-10-31
  `charge_start` refusal (car already charging) came back "not accepted",
  classified ERROR, and got a blind paid retry. If the proxy wraps the
  reason in text, `is_charging` is lost. Worth its own fix; also a free
  signal that would open a session.

## Left to the builder

- Poll interval and give-up time (measured: start snapshot 4-5 min).
- Where the suspicion and session state live (the watch's `_last`/`_want`
  maps, or a small sibling object); keep it on the background/worker
  threads the watch already uses.
- Battery -> wall conversion (section 5), checked against the 24 h log
  (`~/cachelog/cached.jsonl` on the box, TWC readings in each line).
- Exact staleness margin and sample count.
- How the commanded amps and their time are read (the reconciler's
  desired state or the car's `chargeCurrentRequest` observation by our
  own source), and whether "accepted" includes a refusal that says the car
  already has it.
- Tests for section 3 also cover: a lowered rate keeps the old draw in
  allocation until a newer reading; a second car's share waits for that
  reading; an accepted start counts at the commanded amps.
- Settings key name and segment encoding.
