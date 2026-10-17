# Task 11 report: telemetry attaches to registry vehicles (closes A34)

Status: DONE
Branch: vehicle-model/phase1 (worktree wt-vm)
Commit: ac202a1 (on a2a3e24)
Tests: `python -m pytest tests/unit -q`: 976 passed (was 952). Brief's Step 4 subset passes.

## What changed

- `Telemetry.py`
  - `registry = VehicleRegistry.forMaster(master)` is set before the enabled check.
  - `registerLiveness(className, feedLiveAt)` runs after the enabled check, so a disabled module never registers.
  - `connected`, `everConnected` and `lostConnection` flags. `mqttConnect` sets `connected`, and a refused connect (paho v1 rc != 0 or v2 `is_failure`) leaves it False. `mqttDisconnect` clears it. `resetMQTT` clears it first.
  - `feedLiveAt(vehicle=None)` returns `registry.now()` while the feed is connected and `carHealthy`, otherwise None.
  - `vinFor` and `carHealthy` base methods.
  - `applyDataToVehicle` calls `vehicle.observe(field, value, className)`.
  - `updateVehicles` follows the brief: mapped means a rename (the name is observed with the feed's source); otherwise VIN, then `findByName`, then `loadVehicleList` and `findByName` again.
- `TeslaMateVehicle.py`
  - Events renamed to `lat`/`lon`/`state`.
  - `loadCarVINs()` runs `SELECT id, vin FROM cars`. Errors are logged at INFO with the exception type only, never the message, because psycopg2 messages can name the host or user.
  - `vinFor`, `noteHealthy` (logs only on a transition) and `carHealthy`, which uses a reverse lookup over `list(self.vehicles.items())`. An unmapped vehicle returns False: the feed cannot vouch for a car it isn't attached to.
  - Subscribes to `cars/+/healthy`, and `mqttMessage` sends that topic to `noteHealthy`.
  - `mqttConnect` calls super first and subscribes only when connected.
- `FleetTelemetryMQTT.py`: events renamed (`syncState` maps to `state`), `vinFor` returns the topic id, `mqttConnect` calls super, and the previous state is read from the registry as the brief specifies.
- `TeslaAPI.py` (CarApiVehicle): removed the `syncSource`/`syncTimestamp` setters, `syncState`, `syncLat`, `syncLon`, `_observeLegacy` and `_legacySyncSource`. The getters stay.
- Changes to the registry, which are outside the brief's file list:
  - `FieldStore` keeps each source's latest observation per field (`reported(field)`).
  - `FieldStore.age` is clamped to >= 0.
  - `Vehicle._liveAt(field, obs)` lets a feed vouch for a value it also reported (item 3).
  - `Vehicle.age` reads `now` before liveness.
  - `VehicleRegistry.now()`, and `sourceLiveAt(source, vehicle=None)` (the brief's test calls it with one argument).
- Two existing bugs fixed in methods I was already editing:
  - In `TeslaMateVehicle.mqttMessage`, `topic[1:-3].join("/")` raised AttributeError for every user with a topic prefix.
  - In the Fleet JSON-decode branch, the warning logged `payload` before it was assigned, which raised NameError.

## Controller rulings

1. **Liveness, no API on a healthy feed.**
   - `test_healthy_teslamate_car_reads_without_api_calls` uses a real TeslaAPI and TeslaMateVehicle with the real clock and state "online". `update_location(0)` and `update_charge()` both return True, and `get_car_api` is never called.
   - On the real clock, `Vehicle.age` used to read `now` after the liveness callable. That left a microsecond-positive age, so maxAge 0 missed and the read went on to the cascade. I fixed it by reading `now` first and clamping the age at 0. A mutation check confirms the test catches the bug.
2. **syncSource uses liveness-aware age.** `syncSource` already derived from `vehicle.age("state")`, so the liveness covers it. `test_sleeping_car_on_healthy_feed_stays_telemetry_sourced` uses state and pluggedIn observed at t=0:
   - `syncSource` is TeslaMateVehicle, `_telemetryPluggedIn` is True, and `is_awake` is False with no API call.
   - Healthy=false flips `syncSource` to TeslaAPI and `_telemetryPluggedIn` to False. So does a disconnect.
3. **The feed vouching for values other sources observed.** Approach: the field store keeps each source's latest report per field. `Vehicle._liveAt` starts with the latest observation's own source liveness. For each other source whose latest report of that field equals the current value, it takes the max with that source's liveness; polled sources return NOT_TRACKED and are skipped.
   - So when the API or BLE re-observes the value a live feed last reported, the value counts as current. A different value is not vouched for: it ages and gets refetched.
   - The own-write rule still holds. A re-observation older than our write is trusted only after FEED_LAG on a live feed.
   - I rejected re-observing or restamping from the feed. A restamp at "now" would be newer than our write and would defeat `trusted()` (item 6), and `_store` rejects backdated stamps.
   - Tests: three Vehicle-level tests in `test_registry_vehicle.py` (vouch, different value, write plus FEED_LAG), one in `test_registry_fields.py`, and the end-to-end `test_feed_vouches_for_a_value_the_api_reobserved`. That test has the API re-observing the same lat (no call), then a different lat (the call happens). A mutation check confirms it.
4. **Feed source on every write.** `test_telemetry_writes_carry_the_feed_source` checks that chargeLimit, pluggedIn, chargingState, name and a rename (`display_name` on a mapped car) all carry the source TeslaMateVehicle.
5. **The resumed line.** It is now logged only in `mqttConnect` after an unexpected drop (`mqttDisconnect` with a nonzero reason). It does not fire per message or on the daily `resetMQTT`. `test_resumed_line_only_on_reconnect` covers it.
6. **The 09:17 shape.** The brief's test passes through the Probe adapter on a fake registry clock: not trusted at t+3 s, trusted at t+FEED_LAG+1, and not trusted again after a disconnect. `feedLiveAt` uses the registry clock (`registry.now()`) rather than `time.time()`, so ages under an injected clock are meaningful.
7. **TeslaMate identity.** VINs come from the DB when all four `db_*` settings are present; otherwise the car is matched by display name.
   - `test_load_car_vins_from_db` checks the query and the mapping, including that rows with a null VIN are dropped.
   - `test_load_car_vins_without_db_or_on_failure` checks there is no connect without settings, `{}` on a failure, and that the password is absent from the logs.

## Test files

- New: `tests/unit/test_telemetry_registry.py`. It holds the brief's tests verbatim (reformatted by black) plus the ruling tests, healthy-topic routing, the prefixed topic, Fleet state transitions and the undecodable payload, and a refused connect.
- Rewritten: `tests/unit/test_telemetry_mapping.py`. FakeCarApi now populates the registry, and the asserts check `t.vehicles["1"] is registry.get(VIN)` and observation sources.
- Changed: `tests/unit/test_carapivehicle_registry.py`. The legacy-setter test is replaced by a `syncTimestamp` getter test, the legacy-default asserts are trimmed, and the legacy feed test is rewritten against the registry.

## Concerns / known edges (not fixed)

- **Lat/lon equality.** The vouch compares with float equality. If the API's lat/lon differ from TeslaMate's in the last digits, there is no vouch and the read degrades to a fetch, which is the pre-item-3 behaviour.
- **Retained replay within FEED_LAG.** A reconnect within FEED_LAG of our own write re-delivers retained messages stamped "now". Those are newer than the write, so `trusted()` accepts the feed's value before FEED_LAG. The window is about 30 s around the daily `resetMQTT` or an unexpected drop.
- **Non-retaining brokers (Fleet).** The per-source record can be stale across a reconnect. The worst case is that the feed vouches for a value equal to its last report while the broker has nothing new.
- **A forget leaves the feed detached.** `TelmetryBase.vehicles` holds direct `Vehicle` references, as the brief specifies. After `registry.forget(vin)`, the feed's mapping still points at the orphaned object. Each retained display_name redelivery takes the already-mapped branch and renames the orphan, so the feed's observations land on an object the registry no longer holds until the process restarts. CarApiVehicle handles the same case with `_liveVehicle`.
  - Carry-over: in `updateVehicles` and `applyDataToVehicle`, drop the mapping when `self.registry.get(vehicle.key) is not vehicle`.
- **Unmapped cars.** `carHealthy` returns False for a vehicle the TeslaMate feed has not mapped. The base class (Probe/Fleet) returns True.
- **Registry timing confirmed.** `TWCMaster.__init__` sets `master.vehicleRegistry` (TWCMaster.py:118) before modules load, so `forMaster` returns the shared registry in production.
- **DB query at startup.** `loadCarVINs` runs a synchronous DB query in `__init__`, as `doSyncTokens` already does at startup. It is not on the serial or MQTT threads.

## Fix round 1

Commit 0f63241 (on ac202a1). Tests: 986 passed. The 10 new tests failed before the fix, as the brief requires (9 written first; the VIN-health test was added during the fix).

1. **Retained MQTT redelivery (Critical #1, Important #3).**
   - Both TeslaMate and Fleet now read `message.retain is True` and pass `retained` to `applyDataToVehicle`. Parked events keep the flag as a third list element.
   - `TelmetryBase._observe` handles retained messages:
     - A retained value equal to this source's own last report for the field (`Vehicle.reportedBy`) is skipped: no restamp and no `lastSeen` bump.
     - A retained value that differs is observed with `seen=False`. When we have our own write for the field, it is stamped `min(now, lastWrite.at)`, so FEED_LAG decides whether it stands.
   - Names are handled the same way: a retained `display_name` and a name replayed from `retryUnmappedVehicles` count as retained.
   - Tests:
     - A retained pre-write value redelivered across a reconnect is not trusted inside FEED_LAG and is not restamped.
     - A retained value that differs from ours is stamped at the write and trusted only after FEED_LAG; a later live report is trusted.
     - On an unhealthy feed, a retained replay 40 days later leaves `state` ageing from its last change and `lastSeen` unchanged, and `expire()` forgets the car.
     - A retained value we never saw is observed without counting as a sighting.
     - The retained flag survives parking.
2. **Forget (Important #2).**
   - `_dropIfOrphan` checks `registry.get(vehicle.key) is not vehicle`, drops the mapping, and maps the car again with no I/O: by VIN, else by name. If that fails, it parks the event and schedules a retry. Both `applyDataToVehicle` and `updateVehicles` use it.
   - `TeslaMateVehicle.carHealthy` for an unmapped vehicle now uses the health of the car id matching its VIN, else assumes healthy (as the brief says).
   - Tests: a forget followed by a re-create sends observations to the new vehicle, which the feed vouches for; a retained `display_name` after a forget maps the car again; an unmapped vehicle is assumed healthy unless its car's healthy topic is false.
3. **Minor fixes.**
   - Comment on the exact float comparison for lat/lon in `Vehicle._liveAt`.
   - `loadCarVINs` uses `connect_timeout=5`. A new `refreshIdentities()` hook runs at the start of `retryUnmappedVehicles`; TeslaMate reloads the VINs there when the earlier load failed. Tested.
   - `FieldStore.observe` now calls `_store` with an optional per-source table instead of duplicating its body.
   - The `_liveness` and `registerLiveness` type hints now use `Optional[Vehicle]`.

Remaining notes:
- A retained value that differs from ours, with an old own write, is stamped at that old write time. That is correct for FEED_LAG, but the value's age counts from the write.
- Names replayed by `retryUnmappedVehicles` are treated as retained, so they are not sightings. A vehicle created by the VIN path still gets its creation time as `lastSeen`.

## Fix round 2

Commit `1dda627` (on 0f63241). Tests: 991 passed. Five new tests failed before the fix. `test_forget_then_live_message_recreates_as_a_sighting` already passed, because round 1's orphan re-map behaved that way.

1. **A differing retained value is dropped (New Breakage #1).** `_observe` now clamps a differing retained value to `write.at` only when `mine is None or mine.at <= write.at`. Otherwise it stamps the value now, because the broker keeps only the latest publish.
   - `test_retained_change_published_after_the_echo_is_kept` replays probe D: 50, our write of 100 at 1000, the echo of 100 at 1010, then retained 80 at 5000. The latest value is 80 and it is trusted.
   - The C1 reproduction (`test_retained_replay_after_reconnect_does_not_beat_own_write`) and the differing-value FEED_LAG test still pass.
2. **Retained messages never create or revive a vehicle (New Breakage #2).**
   - `updateVehicles(retained=True)` uses `registry.get(vin)` instead of `getOrCreate`. The name path only ever matched existing vehicles.
   - `retryUnmappedVehicles` replays names as retained, so a retry never creates a vehicle either.
   - A live (non-retained) event for an unmapped car id attaches immediately on the MQTT thread with no I/O, once the car's name is known: by VIN, which may create or re-create the vehicle, or to an existing vehicle with that name. Parked events are replayed first.
   - With no name stored yet, a live event is still parked. The brief's verbatim test requires this.
   - Tests:
     - A forget followed by a retained name, retained data and the retry timer does not re-create the vehicle.
     - An expiry followed by the daily retained replay and a retry does not re-create it.
     - A forget followed by a live message re-creates it with `lastSeen` = now.
     - The VIN-reload test now attaches on a live report after the retry.
   - Consequence, as ruled: on a first boot with no saved registry, a TeslaMate-only car attaches on its first live message after its retained display_name.
3. **Fleet derives "online" (Out-of-Scope #1).** A retained `v/*` message no longer derives "online". `test_fleet_retained_value_does_not_mean_online` covers it. Retained Gear and DetailedChargeState messages can still derive driving/charging, which goes beyond the ruling. They pass through `_observe`'s retained rules.
4. **Calls with an empty name (cosmetic).** The re-map never calls `updateVehicles` with a missing name. `updateVehicles` with no name returns False without the "named ''" warning, and a retry is scheduled only when a name is stored. `test_orphan_without_a_stored_name_or_vin_does_not_warn` covers it.

Reviewer probes: p3 now shows "forget + live → present (1100, TeslaMateVehicle, 70)" and "forget + retained name → not present". p1 and p2 can no longer run as written, because they set up the car with retained messages only, which by this ruling no longer creates it. Probe D is covered by the new test.

Remaining note: after a forget or expiry, retained events for that car id are parked again on each daily replay, until a live message attaches the car (about 15 small entries a day).

## Fix round 3

Commit 0fe3413 (on 1dda627). Tests: 996 passed. The 5 new tests all failed before the fix.

1. **Bounded parked-events store.** `unknownVehicles[id]` keeps one entry per topic: a re-parked topic replaces its earlier entry and moves to the end. The list format is unchanged, so the brief's assertion still holds. `test_parked_store_keeps_one_entry_per_topic` covers it: 10 daily replays of 3 topics leave 3 entries, holding the latest value.
2. **Quieter unmapped-car retries.**
   - The "no known vehicle named" line is logged at WARNING once per car id, then at DEBUG. The record is cleared when the car id maps.
   - When the orphan check drops a car id's mapping because its vehicle was forgotten, the id goes into `orphanedIds`. The retry then calls `updateVehicles(..., loadList=False)`, so it never makes a vehicle-list GET that would re-create the car. The id leaves the set once it maps again.
   - Tests: `test_unmapped_retry_warns_once_per_car` and `test_retry_for_a_forgotten_car_never_loads_the_vehicle_list`.
3. **Fleet derives no state from retained values.** No state (online, driving or charging) is derived from any retained `v/*` message; only retained connectivity can set state. The values the message carries still go through the retained rules. `test_fleet_derives_no_state_from_retained_values` covers it.
4. **Fleet attaches by the VIN in the topic.** A new class attribute, `vinInTopic`, is True for Fleet. A live message for an unmapped Fleet car id attaches by that VIN without waiting for VehicleName, which may create the vehicle. TeslaMate and the base class still park nameless events, as the brief's test requires. `test_fleet_live_message_attaches_by_topic_vin_without_a_name` covers it: after a restart with no name seen, a live BatteryLevel creates and attaches the car, and its state is online.
