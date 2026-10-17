# Vehicle Presence — Design

Date: 2026-10-09
Branch: `fix/vehicle-presence`, stacked on `ble-command-worker` (PR #668)
Status: design approved section by section in chat; awaiting spec review

## Problem

On 2026-10-09 the live box (BLE-only commands, TeslaMate telemetry, Fleet API configured) failed to re-apply the 50% non-scheduled charge limit after a depart/return cycle. The car came back with a limit set by hand to 100% and charged at 48 A from 71%.

The causes, confirmed from code and the journal:

1. **The dedupe never clears.**
   - `TeslaBLE.applyChargeLimit` skips a vehicle when `_stopTryingToApplyLimit[vin]` is set and `_lastAppliedChargeLimit[vin] == limit`.
   - Only a `-1` restore clears those flags. The skip is logged at debug level.
   - At 14:07 the car started drawing power, `checkArrival` ran, and no BLE command was sent.
2. **Arrival/departure is a flag on a command.**
   - `applyChargeLimit(limit, checkArrival, checkDeparture)` is called through `VehiclePriority`, which tries BLE first.
   - TeslaBLE ignores both flags and returns success. So `TeslaAPI`'s location-based arrival/departure logic never runs, not even as a fallback.
3. **Departure is only inferred from a power drop.**
   - `TWCSlave` queues `checkDeparture` at +5, +20 and +45 min when the current falls from above 2 A to below 2 A.
   - At 13:07:33 the TWC went from state `03` to `00` (unplugged) while the car was idle at its limit, so nothing was queued.
4. **Nothing tracks presence per vehicle.**
   - TeslaMate pushes `latitude`/`longitude` into `vehicle.syncLat`/`syncLon`, but nothing reacts to them.
   - BLE contact proves a car is home, but that fact is thrown away.

Arrival and departure handling is also a client concern buried inside the vehicle interfaces. Each interface makes its own location and wake decisions. Normal limits are keyed by API `ID` in `TeslaAPI` and by VIN in `TeslaBLE`.

## Goals

- Track presence (home, away, unknown) per vehicle, keyed by VIN, as a client of the vehicle interfaces rather than as part of any one of them.
- Re-apply the current policy limit to a vehicle when it arrives, and restore its normal limit when it departs, through whichever command interface can reach it. Other vehicles' limit state is not disturbed.
- Support every configuration: with or without BLE, with or without TeslaMate, with or without the Fleet API, including Fleet-only.
- Never wake a sleeping car just to determine presence.
- Keep presence I/O off the serial main loop, the background-task thread and the vehicle command worker.

## Non-goals

- Changing how policy limits are chosen. Presence uses the policy's current limit (`master.lastChargeLimitApplied`) as it is.
- Fixing the existing wake-on-read in `TeslaAPI.update_charge` and `update_location`. Those call `wakeVehicle` when a BLE `state` read fails and the API hasn't been used for 2 minutes. That's noted for a follow-up.
- `checkCharge` (`updateChargeAtHome`), which is unrelated and stays.
- `fakeMaster != 1` behaviour beyond not starting the thread (see Lifecycle).

## Architecture

### `VehiclePresence` (new: `lib/TWCManager/VehiclePresence.py`, owned by `TWCMaster`)

This component holds per-VIN state behind a lock and owns one daemon thread.

**Public interface:**

```python
def start(self): ...                            # idempotent; daemon thread "VehiclePresence"
def stop(self): ...                             # no new probes/commands; returns immediately
def state(self, vin) -> str: ...                # "home" | "away" | "unknown"
def nominate(self, vin, reason, delays=(0,)): ... # vin may be None = all known vehicles
def observeContact(self, vin, reachable): ...   # from any BLE operation
def observeLocation(self, vin, atHome): ...     # from telemetry or the API
```

- **Known vehicles.** These are the union of the VINs in `master.settings["Vehicles"]` and `.VIN` across `TeslaAPI.getCarApiVehicles()`.
- **Observers only record.** `nominate`, `observeContact` and `observeLocation` record the observation or schedule, set the thread's wake event, and return. They do no I/O. They can be called from any thread: the main loop, the MQTT thread, the vehicle worker, or the background thread.
- **Scheduling.** Each VIN has a set of pending due times. `nominate(vin, reason, delays)` adds `now + d` for each `d`. A `None` VIN expands to every known vehicle at the time the check falls due.
- **The thread.** It waits on its wake event, with a timeout until the earliest due time. On each pass it:
  1. applies any recorded observations;
  2. probes every VIN that has a due time at or before now, subject to the rate limit;
  3. applies the decision rules;
  4. runs the arrival or departure handler for each vehicle whose state changed.
- **Rate limit.** No VIN is probed more than once per 60 s. A due time inside that window is satisfied by the recent result.

### Presence probe: source fallback

The setting `vehicle.presenceSources` is an ordered list. The default is `["telemetry", "ble", "api"]`. Entries can be removed; unknown entries are ignored with a warning. Each probe tries the sources in order, and the first source that gives a definite answer decides.

- **`telemetry`**
  - **Applies when:** a telemetry module (TeslaMate) is live for that VIN, meaning the vehicle's `syncSource` is the telemetry module.
  - **Presence:** decided by `is_location_home(syncLat, syncLon)`. TeslaMate keeps the last fix of a parked car, so a stale timestamp still gives the right position.
  - **Current limit:** `vehicle.chargeLimit`.
- **`ble`** (TeslaBLE loaded):
  - **Presence:** `tesla-control -ble body-controller-state`. It talks to VCSEC only and works while infotainment is asleep. This was verified live: it returned `VEHICLE_SLEEP_STATUS_ASLEEP` in 4.2 s without waking the car.
  - **Answers:** success means home; failure is a non-answer, but it counts toward the away rule below.
  - **Current limit:** read with `state charge`, but only when that probe reported the car awake. A sleeping car is never woken for this.
  - **Never used for presence:** `wake`, `state` (without a preceding awake probe) and `ping`.
- **`api`** (TeslaAPI loaded and token valid):
  - **Online check first:** read online status from the vehicle list endpoint, which doesn't wake the car.
  - **If online:** read the location and charge state. The location decides presence, and the charge state gives the current limit.
  - **If asleep or offline:** this is a non-answer. Presence stays as it was, because a sleeping car hasn't moved since it fell asleep.

### Decision rules

- **Home.** Any of these makes the VIN `home`:
  - a successful BLE probe;
  - a telemetry fix inside the geofence;
  - an API location inside the geofence.
  
  BLE success counts even if another source says away.
- **Away.** A telemetry or API fix outside the geofence makes the VIN `away`.
- **BLE-only away.** If no source after `ble` in the list gave a definite answer, and `telemetry` was not live, 2 consecutive failed BLE probes for a VIN make it `away`. A successful probe resets the count.
- **Unknown.** Every VIN starts `unknown`.
  - `unknown → home` runs the arrival handler. Re-applying the current limit once is safe.
  - `unknown → away` runs no handler, because there is no evidence the car was home.
- **Push observations follow the same rules.**
  - `observeLocation` (telemetry pushes, or API reads made elsewhere) applies the home and away rules immediately.
  - `observeContact(vin, True)` from any BLE operation applies the home rule.
  - `observeContact(vin, False)` from a non-probe BLE operation is ignored. Only probes count toward the away rule, because a failed command may be a command error and not proof of absence.

### Handlers (run on the presence thread; they only queue commands)

**Arrival** (`vin`):

1. Call `resetChargeLimitState(vin)` on each loaded vehicle module, through `VehiclePriority`'s fan-out (see Interfaces). This resets only this VIN.
2. Adopt a limit set by hand as the new normal:
   - **Condition:** the probe or observation supplied a current limit, the saved normal for this VIN has `lastApplied != -1`, and the current limit differs from `lastApplied`.
   - **Action:** `saveNormalChargeLimit(vin, current, lastApplied)`.
3. Queue `{"cmd": "applyChargeLimit", "limit": master.lastChargeLimitApplied or -1, "vin": vin}` on the vehicle queue.

**Departure** (`vin`):

1. Reset this VIN's limit state, as in arrival step 1.
2. Decide whether to restore:
   - **Current limit known and different from `lastApplied`:** you changed it. Save it as the new normal and don't restore.
   - **Otherwise:** if a remote command channel is available, queue `{"cmd": "applyChargeLimit", "limit": -1, "vin": vin, "remoteOnly": True}`. A remote channel means TeslaAPI is loaded and `commandPolicy` is not `ble_only`.
3. The restore is never sent over BLE. If BLE can't reach the car, it has left, so the restore fails. If BLE can reach it, it hasn't left, so the departure was a false conclusion. A BLE restore would succeed, mark the car home, and be overwritten by the arrival apply at once.
4. With no remote channel, nothing is queued. The handler logs at INFO that the restore can't be delivered (see Known limitations).
5. Undelivered restores are never replayed. If the car comes back while a restore is still pending in the vehicle queue, the arrival apply has the same coalescing key `(applyChargeLimit, vin)` and replaces it.

### Triggers

- **TWC events** (`TWCSlave.receive_slave_heartbeat`, main loop). The nominated VIN is `currentVIN`, else `lastVIN`, else `None`.
  - **Power starts** (current rises above 3 A from below): `nominate(vin, "power-start", delays=(0,))`.
  - **Power drops** (current falls below 2 A from above): `nominate(vin, "power-drop", delays=(300, 1200, 2700))`. This replaces queuing `checkDeparture`. The delays are kept because a TWC event usually means a departure is about to happen, not that it already has.
  - **Unplug** (`reportedState` changes from anything else to `0x00`): `nominate(vin, "unplug", delays=(300, 1200, 2700))`. State `00` is not always a real unplug. The live box showed it for a moment while plugged in, just before a scheduled start, at 2026-10-08 00:00:07. A false unplug only costs the delayed probes, which then find the car home, so no debounce is added.
  - **VIN recorded** for a session (`master.recordVehicleVIN`): `nominate(currentVIN, "vin", delays=(0,))`. The VIN usually arrives a few seconds after power starts.
- **Telemetry** (`Telemetry.applyDataToVehicle`, MQTT thread): after a `latitude` or `longitude` update, once both are valid, `observeLocation(vehicle.VIN, is_location_home(...))`.
- **BLE** (TeslaBLE): every `_sendCommand_internal`, `_fetch_state_json` and probe result reports `observeContact(vin, ok)`, with the probe flag set for probes.
- **API**: `TeslaAPI` reports `observeLocation` whenever it reads a location.

### Interfaces: vehicle modules become channels

- **`applyChargeLimit(limit, vin=None)`** on TeslaBLE, TeslaAPI and HomeAssistant.
  - **`vin=None`:** all vehicles. This is today's policy-wide apply, and its per-VIN dedupe is unchanged.
  - **`vin` given:** that vehicle only.
  - **Removed:** the `checkArrival` and `checkDeparture` parameters.
  - **Removed from TeslaAPI:** `applyChargeLimit` loses its `wasAtHome`/location/departure branches. It becomes "apply `limit` (or restore on `-1`) to at-home vehicles, honouring the per-vehicle dedupe". Presence is now the caller's decision.
- **`remoteOnly`.** `VehiclePriority` honours a `remoteOnly=True` keyword on `applyChargeLimit` by skipping TeslaBLE. The vehicle queue's `applyChargeLimit` dispatch passes it through.
- **`resetChargeLimitState(vin)`** clears per-vehicle dedupe flags for that VIN only.
  - **TeslaBLE:** `_stopTryingToApplyLimit[vin]` and `_lastAppliedChargeLimit[vin]`.
  - **TeslaAPI:** `vehicle.stopTryingToApplyLimit`.
  - **HomeAssistant:** its equivalent, if it has one.
  
  `VehiclePriority` exposes this as a fan-out to every loaded vehicle module. It is not a first-success call.
- **`probePresence(vin)`** on TeslaBLE: `body-controller-state`. It returns `{"reachable": bool, "awake": bool}` and is not decorated with `_execute_with_retry`. It runs once, under the BLE lock.
- **Normal limits are keyed by VIN.**
  - `get/save/removeNormalChargeLimit` callers in TeslaAPI switch from `vehicle.ID` to `vehicle.VIN`.
  - **One-time migration:** on load, any `settings["chargeLimits"]` key that matches an API `vehicle.ID` is moved to that vehicle's VIN, unless the VIN key already exists.
- **Removed:** the background task commands `checkArrival` and `checkDeparture`, their `background_tasks_thread` branches, and the `HTTPControl` `/api/checkArrival` and `/api/checkDeparture` endpoints. The endpoints become `nominate(None, "api", delays=(0,))` and keep returning `202`.

### Vehicle queue changes (on top of #668)

- **Generalised coalescing.** Every command is keyed `(cmd, vin)`. `vin` comes from `task["vin"]`, or from `task["vehicle"].VIN` for `setChargeRate`. `None` is a distinct VIN. This replaces #668's special case for `charge` and `applyChargeLimit`.
- **`cancel(cmd, match)`.** It removes pending (not running) entries whose task satisfies the predicate `match`, and returns the number removed.
- **`TWCMaster.cancelStopCarsCharging(vin=None)`** cancels pending `charge` stops through `cancel`, for that VIN, or all if `None`. This fixes #667 for the queue path. `TWCSlave` passes `self.currentVIN`.
- **`TWCMaster.stopCarsCharging(vin)`** cancels pending `charge` starts before it queues its stop.
- **`TWCMaster.startCarsCharging(vin)`** passes `vin` into its `charge` task in stop mode 1 (it currently drops it). That way most start/stop pairs share a key.

### Lifecycle

- **Start.** `TWCManager.py` calls `master.vehiclePresence.start()` after the vehicle queue starts, only when `fakeMaster == 1`. This is the same reasoning as #670: in the other modes nothing should send charge-limit commands to cars. Without the thread, observers still record, but nothing acts.
- **Stop.** `stop()` is called at the start of the shutdown block, next to `Policy.stop()`, before any draining. A probe that is already running finishes. Its handler may still queue commands, which the vehicle queue's drain then drops if they are low priority.

## Known limitations

- **No restore on departure without a remote command channel.** Restoring a departed car's normal limit needs a command that reaches the car away from home. In practice that's the Fleet API, through TeslaAPI and `commandPolicy` allowing it.
  - BLE is local only, so it can't reach a car that has left.
  - With the Fleet API disabled (`commandPolicy: ble_only`, or TeslaAPI not configured), presence can still conclude that the car has left, from telemetry or from repeated BLE probe failures. But the restore has no channel, so the car keeps the policy limit while away.
  - Departure therefore queues no restore. The next arrival applies the current policy limit directly; there is no restore followed by an overwrite. A limit set by hand while away becomes the new normal, if the current limit is readable at arrival.
  - This is inherent to a BLE-only setup and is logged when it happens: one INFO line per departure saying the restore couldn't be delivered.
- **Home Assistant is not a restore channel either.** `HomeAssistant.applyChargeLimit` exists, but:
  - it skips vehicles that aren't at home or aren't plugged in;
  - it treats `-1` (restore) as "leave the limit unchanged".
  
  So it can apply the policy limit on arrival but cannot restore on departure. Changing that is out of scope here. The module only gains the `vin` parameter and `resetChargeLimitState`, which is a no-op because it has no dedupe state.

## Error handling

- **Sources.** A failure, timeout or exception in any source is logged at debug level and counts as no answer. The probe moves on to the next source. When all sources give no answer, the state doesn't change, apart from the BLE-only away rule.
- **The thread.**
  - The thread loop wraps each pass in `try/except Exception`, logged with a traceback at error level, and keeps going.
  - It also has an outer `except BaseException` that logs and re-raises, as `Policy._run` and `VehicleCommandQueue._run` do.
- **Commands.**
  - If an arrival apply fails, that VIN's dedupe stays reset, so the next policy-wide apply retries it.
  - A departure restore that fails is dropped, not retried. The next arrival applies the policy limit, and never replays the restore first.
- **Locking.**
  - State changes happen under the presence lock.
  - Handlers run after the lock is released. They read their inputs from a snapshot taken under the lock.
  - Observers hold the lock only to record.

## Behaviour changes

- **Commands follow presence, per vehicle.**
  - Arrival and departure commands are sent per vehicle when presence changes, not as a side effect of TWC power events.
  - A car that arrives without plugging in gets the policy limit, if any source can see it.
- **Departures are seen sooner.** The unplug trigger notices a departure that happens while the car is idle.
- **TeslaAPI makes fewer calls.** It no longer polls location during `applyChargeLimit` calls.
- **No wakes for presence.** Presence checks never wake a car. Departure detection may be later for a car that falls asleep before it leaves. That's unlikely, because a departing car is awake.
- **`checkArrival`/`checkDeparture`** background tasks are gone. The HTTP endpoints remain, as presence nominations.
- **Queue coalescing.**
  - `applyChargeLimit` with a VIN no longer merges with the policy-wide apply.
  - `charge` start and stop for the same VIN still merge, newest wins.
  - A pending opposite `charge` is now cancelled explicitly.
- **`cancelStopCarsCharging` now works**, which closes #667.
- **Normal-limit keys** move from API ID to VIN, with a one-time migration.

## Testing

**Unit tests:**

- **`VehiclePresence`:**
  - each decision rule;
  - unknown → home runs arrival, and unknown → away runs nothing;
  - BLE-only away needs 2 consecutive failed probes, and a success resets the count;
  - push observations;
  - due-time batching with `None` expanding to the known VINs;
  - the 60 s rate limit;
  - events affect only the VIN concerned;
  - `start` is idempotent, and `stop` prevents new passes;
  - the thread survives an exception in a pass.
- **Source fallback:**
  - follows `presenceSources` order and skips removed entries;
  - telemetry is used only when live;
  - the BLE limit read only happens when the probe reports the car awake;
  - API location is read only when the vehicle list shows the car online.
- **Handlers:**
  - only that VIN's limit state is reset;
  - the departure restore is `remoteOnly`, and nothing is queued without a remote channel;
  - `VehiclePriority` skips TeslaBLE for `remoteOnly`;
  - a limit set by hand becomes the new normal on arrival;
  - departure is suppressed when the limit was changed;
  - queued commands carry `vin`.
- **Vehicle queue:**
  - generalised `(cmd, vin)` keying with `None` distinct;
  - `cancel()` leaves the running entry alone;
  - `cancelStopCarsCharging(vin)` and the stop-cancels-start rule.
- **TeslaBLE:**
  - per-VIN `applyChargeLimit`;
  - `resetChargeLimitState`;
  - `observeContact` reported from commands, reads and probes;
  - `probePresence` parses awake and asleep output;
  - the probe never runs `wake`, `state` or `ping`.
- **TeslaAPI:**
  - the flags are removed;
  - per-VIN apply works;
  - normal limits are keyed by VIN, with the migration;
  - the presence source checks online status before reading location.
- **Telemetry:** a location update calls `observeLocation` once both coordinates are valid.
- **TWCSlave:**
  - each trigger nominates the right VIN (`currentVIN`, then `lastVIN`, then `None`) with the right delays;
  - unplug without a power drop still nominates;
  - `recordVehicleVIN` nominates.
- **Removals:** the `checkArrival` and `checkDeparture` background branches are gone, and the HTTP endpoints nominate.

**Live testing**, on the box with #669 and #670:

- **Depart and return:** unplug, drive away, return. Departure is detected through TeslaMate, or the BLE probes at +5/+20/+45 min. On arrival, the policy limit is re-applied within about a minute of the geofence entry or the first BLE contact. That holds even if the limit was raised by hand while away, which is the incident case.
- **No wakes:** while the car is parked and asleep, probes never wake it. TeslaMate should show it staying `asleep` across a probe window.
- **No stalls:** no new main-loop stalls from the stall diagnostic.
