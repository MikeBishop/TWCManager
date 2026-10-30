# Free cached vehicle reads (Fleet `vehicle_data_cached`)

Date: 2026-10-28. Status: design, awaiting approval.

## Intent

TWCManager pays for Fleet API `vehicle_data` reads (0.002 USD each), and a
cloud read of a sleeping car is impossible without a paid wake. Fleet also
offers `vehicle_data_cached`: free, no call to the car, works while the car
is asleep or offline, never wakes it. It returns the last snapshot the car
uploaded to Tesla.

The motivating case: the car stops a charge on its own (limit reached).
TWCManager used to answer with a start command, which the car refused as
"complete". Newer logic (`Belief.handsOff`, `uncompleted`) infers that
instead, but only from a fresh battery level and limit. Getting those after
the stop costs a paid read. The car uploads a snapshot within seconds of a
charge ending, so the whole stop / explain / don't-restart cycle can run with
no paid interaction.

**This changes how data is obtained, not what is done with it.** Every
consumer (`handsOff`, `uncompleted`, `satisfied`, Watch, Presence, policies)
keeps its current rules. The user was explicit: no new decision cases (for
example, no "respect a user stop" rule).

## What the live probes established (2026-10-28, box `twcmanager`)

- Fleet answers 200 with `charge_state`, `climate_state`, `gui_settings`,
  `vehicle_state`. Every block in one response carries the same `timestamp`
  (ms since epoch).
- `charge_state` has every field TWCManager reads except `charger_phases`
  and `scheduled_charging_pending` (it has `scheduled_charging_mode` and
  `scheduled_charging_start_time` instead; with no schedule: `"Off"`,
  `None`). It also has
  `charge_port_door_open`. `vehicle_state.vehicle_name` is present. No
  `drive_state` or location, ever.
- Owner API answers **412** `"Endpoint is only available on fleetapi"`.
- When the car uploads a snapshot:
  - on waking (seconds after);
  - 3-7 s after a charge ends;
  - ~16 s before it goes offline (sleep);
  - about every 5 minutes after charging activity (seen mid-charge and
    5:00 after a charge end);
  - **not** on charge start, **not** while awake and idle (no snapshot in
    4+ min awake), and **not** in response to TeslaMate's ~20 s Owner API
    `vehicle_data` polls.
- Values in a snapshot were correct as of its stamp (e.g. a limit restored
  by BLE 2-3 s before the stamp shows in it).
- `vehicle_data_cached` does not match `_PAID_PATH` (anchored `$`), so it is
  not counted as paid. The fleet-spend work (other session) adds a test that
  keeps it that way and leaves `_PAID`/`_PAID_PATH` unchanged.

## Goals

1. A free cached source for the charge fields, tried before paid Fleet
   `vehicle_data` in every read that already walks the provider order.
2. Correct freshness: a cached value counts only by the car's own stamp.
3. A short wait for an expected snapshot when the read is about a just-now
   event, so the post-event snapshot can satisfy it for free.
4. No change to any consumer's decisions.

## Non-goals

- Location, `shiftState`, `gpsAsOf`: the endpoint never has them; those
  reads stay on paid `vehicle_data`/BLE/telemetry.
- Owner API: it refuses the endpoint. Owner-only installs behave as today.
- New stop-reason rules or UI ("why did charging stop" stays implicit in
  the existing rules).
- Replacing live reads during a charge: snapshots are at best ~5 min apart
  then.

## Anti-goals (failure even if it "works")

- A cached 404/412 pausing or latching the whole Fleet slot. Today
  `_classify` treats a non-paid 403/410/412 as `slot.pause(latch=...)`,
  which would stop every Fleet read until the token is replaced.
- A stale snapshot satisfying a read it should not, because its age was
  measured from fetch time instead of the car's stamp.
- Any cached request on the Owner slot (412 there pauses Owner reads by the
  same path).
- The paid read getting slower in cases where no snapshot is coming (an
  awake, idle car), beyond a single fast fetch.
- Library growth beyond what the feature needs (see Constraints).

## Decided by the user

- **Freshness is judged by the car's stamp, against a cutoff.** A snapshot
  stamped at or after the cutoff satisfies the read, however long after the
  call it was fetched. Example: a snapshot fetched 10 s after the call,
  stamped 3 s after the event, satisfies a read whose cutoff is the event.
- **Event cutoff.** A caller that knows the event it is reacting to passes
  that event's time as the cutoff, and then a snapshot from before the event
  never satisfies the read, even one inside `maxAge`. Without an event
  cutoff, the cutoff is call time minus `maxAge` (today's rule).
- **Waiting.** When the read has an event cutoff and no snapshot clears it
  yet, the cached source re-fetches for a short window (the car posts 3-16 s
  after an event) before giving up to the next (paid) provider. Without an
  event cutoff: one fetch, then fall through.
- Scope is data acquisition only (see Intent).

### maxAge audit (who reads, with what)

| Caller | maxAge today | Reaches cached? | Event cutoff to pass |
|---|---|---|---|
| `Presence.checkPlug` (Presence.py:241) | 0, `force` | no (excluded; see below) | the charging point's edge, `since` (it already sets `car.staleBefore = since` and judges by `pluggedNow(..., since)`) |
| `Presence` BLE read (Presence.py:457) | 0, `force`, `providers=("TeslaBLE",)` | no | none; unchanged |
| Attempt pre-read (Run.py:175) | `None` for amps/blind retry; else `READ_MAX_AGE` + `PAID_AFTER` for paid (360 s charging, 600 s limit) | yes | the event that prompted the attempt where one exists (for the motivating case: the TWC current drop / charge end); otherwise none |
| `Watch._read` (Watch.py:350, calls `order.read` directly) | none | yes | its own last read time for that car: it wants a reading newer than the last one |

`maxAge=0` today means "after the edge", not "after the call"; the event
cutoff says that directly and lets a snapshot stamped between the edge and
the call count.

**Designer's call: `checkPlug` does not read the cached source.** Its read
exists only to give `pluggedNow(..., since)` plug evidence, and a
`"FleetAPICached"` reading is never plug evidence (below). A cached answer
would stop the cascade and leave `checkPlug` with nothing, where today's
paid read answers. So `checkPlug` passes `since` as its cutoff and leaves
the cached provider out of its read; it behaves as today. (It also runs on
the BLE worker, once per candidate car, so it must never wait.)

**Designer's call: liveness still counts.** "Fresh" keeps today's meaning
from `Vehicle.age()`/`_liveAt`: a healthy report-on-change feed (TeslaMate,
Fleet Telemetry) vouches for its value up to now. The cutoff test is "the
value's freshness time (its stamp, or the feed's liveness time when a live
feed vouches for it) is at or after the cutoff", reusing `_ageOf`/`trusted`.
Dropping liveness would push TeslaMate-covered cars onto paid reads.

## Design

### Provider

A new provider in `Vehicle/Providers/TeslaAPIProviders.py`, e.g.
`FleetCachedProvider`, on the TeslaAPI module's `fleetSlot`:

- Declares `READ_CHARGE: CLOUD_FREE` only (no commands, no wake, no
  Wall Connector VINs). Its cost tier sorts it ahead of paid `FleetAPI` and
  alongside the free Owner read.
- `FIELDS`: the `CHARGE_FIELDS` the snapshot actually carries, plus
  `scheduledChargingPending` inferred (below); drop `phases`; no
  `LOCATION_FIELDS`.
- `scheduledChargingPending` (user's suggestion): the snapshot has
  `scheduled_charging_mode` and `scheduled_charging_start_time` instead.
  Proposed rule: pending when the mode is not `"Off"`, a start time is set,
  and `charging_state` is `"Stopped"` (plugged in, waiting). Mode `"Off"`
  (seen live, start time `None`) is not pending. Unverified for `StartAt`/
  `DepartBy`, including after the start time has passed; a wrong answer
  changes `handsOff` under `respectVehicleSchedule`. The plan includes a
  live check: set a `StartAt` schedule while plugged in and compare the
  inferred value to BLE's `scheduledChargingPending`, before and after the
  start time; adjust the rule to match.
- `ready`: the Fleet slot is usable for `"read"`, the car is attached to
  TeslaAPI, and the car is not latched unsupported (412). No `is_awake`
  gate: the point is to read a sleeping car.
- `worker`: cloud, like the other TeslaAPI providers.
- Observes with `at=` the snapshot's `charge_state.timestamp / 1000`, under
  its own source name, `"FleetAPICached"` (decided by the user). It is the
  car's own reading, so it joins `LIVE_READ_SOURCES` (Belief.py).
- **Not home-plug evidence (decided by the user).** A snapshot has no
  location, and Presence pairs a weak (cloud) plug reading with the newest
  stored fix however old (`_plugEvidence`, `inside()`). Every other cloud
  read carries a same-moment fix; a snapshot would pair a fresh charging
  state with a possibly hours-old home fix and call an away AC charge
  "plugged in here". So Presence never counts a `"FleetAPICached"` reading
  as plug evidence (neither plugged nor unplugged). This is the one Presence
  change, scoped to the new source; every existing source behaves as today.
  The reconciler's charging/battery/limit reads still use the snapshot.
- Never sets `statusDeferral` (that throttle is for paid reads).

### TeslaAPI request path

- A cached fetch method beside `update_vehicle_data`, using `_request` on
  `fleetSlot` with a new purpose (e.g. `"cached"`), and the same field
  mapping as `update_vehicle_data` (share it; don't copy it).
- `_classify` for that purpose: 404 means no snapshot for this car (an
  error, nothing latched); 412 latches **this car** unsupported for cached
  reads until the token changes; 401 keeps today's refresh handling; nothing
  calls `slot.pause` or `slot.refuse`.
- Never sent on `ownerSlot`.

### Read cascade freshness

`ProviderOrder.read` today returns as soon as a fetch succeeds and the field
has any value. That was safe because every source stamped at fetch time. It
must instead accept the field only when its newest observation is stamped
at or after the caller's cutoff, and otherwise continue to the next provider.

- `Vehicle.read` gains an optional event cutoff (`since`). The effective
  cutoff is `since` when given, else call time minus `maxAge`. The
  "already fresh" shortcut uses the same cutoff, so a value from before the
  event never short-circuits the read.
- `force=True` callers keep their meaning: skip the shortcut. The cascade
  still applies the cutoff.
- With no `maxAge` (None) and no `since`, nothing fetches, as today.
- `ProviderOrder.read` takes the cutoff from its callers (Vehicle.read,
  Watch) and checks it after each fetch.

### The wait

In the cached provider's fetch, only when the read carries an event
cutoff: if the snapshot is stamped before it, re-fetch every few seconds
for up to ~15 s (measured event-to-snapshot: 3-16 s), then return
not-fetched so the cascade moves on. The poll is free; its cost is latency
on the cloud worker, which already runs reads off the main loop.

### Watch

`Watch._read` takes `found[:1]`, spends the watch budget at that
provider's price up front, and restricts the read to it. With a free cached
provider first, a stale snapshot would end the read and the paid read would
never run. Change it to: free providers first, then the first paid one;
spend budget only if the paid fetch runs. Cadence choice (`chargingReadSecs`
vs `cloudChargingReadSecs`) follows the provider that actually answered, or
stays as today if that is simpler and equivalent. Watch's rule that it never
reads an asleep car (`HOME_ASLEEP`/`AWAY_ASLEEP`) is a decision, not data
acquisition: leave it.

### Docs and changelog

- `docs/modules/Vehicle_TeslaAPI.md`: one short FAQ-style note for
  installers: with a Fleet API token TWCManager reads the car's last
  reported charge state for free, including while it sleeps. Capabilities,
  not internals; "EVSE" not "charger".
- `CHANGELOG.md` under the upcoming release: one Features line. Not a
  Bugfixes line.

## Constraints

- Line budget: this is a feature, so some growth is expected, but keep it
  small and look for sharing (the field mapping with `update_vehicle_data`,
  the provider base class). No duplicated request or parsing code.
- Comments explain why the code is as it is, never history.
- Gen3 behaviour must not regress.
- The fleet-spend session lands first and touches only the paid-request
  block in `TeslaAPI.py`; rebase onto it.
- Unit tests for: cutoff semantics (stamp vs fetch time, `maxAge=0`, late
  fetch with early-enough stamp); cascade fall-through on a stale cached
  value; 412 latching one car and never pausing the slot; no cached request
  on the Owner slot; Watch spending budget only on the paid fetch; a
  `"FleetAPICached"` charging state with a stale home fix producing no plug
  evidence.
- Live verification on the box (deploys pre-approved; record rollback): a
  car-initiated stop (limit restore) produces no paid request and no start
  command; an asleep car's battery/limit read is free.

## Left to the builder

- Provider class and method names; whether the cached fetch lives on
  `_TeslaAPIProvider` or a sibling class.
- How the attempt pre-read learns its event time (from what the reconciler
  and registry already record), the re-fetch interval, and the ~15 s cap
  (tune against the measurements above).
- Whether Watch's last-read cutoff is an event cutoff (waits) or a plain
  cutoff (one fetch): a routine read has no event behind it, so one fetch
  is the default.
- Whether the provider's `name` equals its source name (as `OwnerAPI` and
  `FleetAPI` do today); check every place that maps a source name back to a
  provider or module (`sourceOf`, the `providers=` filter, the web UI).
- How the cutoff is threaded through `Vehicle.read`/`ProviderOrder.read`.
