# Task 11 review: telemetry attaches to registry vehicles (a2a3e24..ac202a1)

Reviewed read-only in `wt-vm`; the focused test subset (8 files, 101 tests) passes; `black --check` clean on every touched file; commit trailer present. Risks (a) and (c) were reproduced with scratch scripts (`scratchpad/probe_a_c.py`, `probe_seen.py`) driving `TeslaMateVehicle.mqttMessage` with `retain=True` messages on an injected clock; outputs quoted below.

### Spec Compliance

**Verdict: the brief's interfaces are implemented and the seven controller rulings are each covered by a test, but the task's purpose (the 09:17 rule) is defeated by one reachable path, so it is not compliant until retained MQTT redelivery is handled.**

Per the brief / rulings:

- `TelmetryBase.registry` set before the enabled check; `registerLiveness` after it: `lib/TWCManager/Vehicle/Telemetry.py:51,71`. OK.
- `connected` set in `mqttConnect` (refused connect leaves it False, both paho v1 rc and v2 `is_failure`), cleared in `mqttDisconnect` and at the top of `resetMQTT`: `Telemetry.py:126-156`. Both subclasses call `super().mqttConnect` first and skip subscribing when not connected: `TeslaMateVehicle.py:372-375`, `FleetTelemetryMQTT.py:37-40`. OK (rulings 1, 5).
- `feedLiveAt` returns `registry.now()` while `connected and carHealthy(vehicle)`: `Telemetry.py:162-167`. Ruling 6 accepts the registry clock. OK.
- TeslaMate subscribes `cars/+/healthy`, routes to `noteHealthy`, `carHealthy` per mapped car id: `TeslaMateVehicle.py:148-167,380,398-399`. Deviation: `carHealthy` returns False for a vehicle this feed has not mapped (brief: "assume healthy"). Defensible on its own, but see Important #2 for where it bites.
- `vinFor` ×3, `loadCarVINs` (all four `db_*` present, `SELECT id, vin FROM cars`, `{}` on any failure, INFO log of the exception type only): `TeslaMateVehicle.py:108-146`, `FleetTelemetryMQTT.py:33-35`. OK (ruling 7).
- `updateVehicles` order (mapped → rename; VIN → `getOrCreate`; `findByName`; `loadVehicleList` only with `loadList=True`, i.e. never on the MQTT thread): `Telemetry.py:245-290`. OK.
- `applyDataToVehicle` observes with the feed's class name as source; no `syncSource`/`syncTimestamp` writes: `Telemetry.py:201-205`. OK (ruling 4).
- Event tables renamed to `lat`/`lon`/`state`; legacy `syncState`/`syncLat`/`syncLon`/`_legacySyncSource` and both setters removed, getters kept: `TeslaAPI.py:2093-2113`. OK.
- Fleet reads the previous state from the registry: `FleetTelemetryMQTT.py:59-64`. OK.
- Ruling 1 (healthy TeslaMate car, `update_location(0)` / `update_charge` with no API call, real clock): `tests/unit/test_telemetry_registry.py:196-202`. Ruling 2 (sleeping car stays telemetry-sourced; `_telemetryPluggedIn` live; unhealthy or disconnect flips it): `:217-231`. Ruling 3 (feed vouches for a re-observed equal value, not a different one): `:205-214`. Ruling 5: `:245-254`. Ruling 6: `:123-144`. All pass.
- Out-of-brief registry changes (Fields/Vehicle/VehicleRegistry) are small, explained, and tested; see (d) under Strengths.
- Global constraints: Py3.8 syntax (typing imports), no `Vehicle.read()` on the MQTT thread, no lock across I/O, no token in any new log line. OK.

### Strengths

- The liveness model is clean: one callable per feed, registered only when the module is enabled, consulted with the lock released (`VehicleRegistry.py:267-278`), and the brief's own 09:17 test passes end to end through the adapter (`test_telemetry_registry.py:123-144`).
- (d) The three registry edits are sound. `Vehicle.age` reads `now` before the liveness callable (`Vehicle.py:104-109`) and `FieldStore.age` clamps at 0 (`Fields.py:133`), so a live feed's "now" never leaves a microsecond-positive age that misses `maxAge 0`; the implementer's mutation check confirms the ruling-1 test catches the regression. `sourceLiveAt(source, vehicle=None)` is a harmless widening. No lock is held across the liveness callable: `sourceLiveAt` releases `_lock` before the call, `FieldStore.reported()` copies under its lock and returns, `Vehicle._liveAt` iterates the copy, `summary()` releases `Vehicle._lock` before the field loop. `carHealthy` iterates `list(self.vehicles.items())`, a C-level copy, so a concurrent mapping change on the MQTT thread cannot raise.
- (b) The per-source vouch (`Vehicle.py:87-102`, `Fields.py:87-106`) only widens `liveAt`; `FieldStore.trusted` still requires `now - write.at > FEED_LAG` for anything not strictly newer than our write, so the own-write rule survives the vouch. A non-equal value is never vouched for and falls to a fetch (the safe direction). `_bySource` is bounded by sources × fields.
- (e) Both pre-existing crash fixes are correct and tested: `"/".join(topic[1:-3])` (`TeslaMateVehicle.py:391`, test `:265-270`) handles single- and multi-level prefixes; `message.payload!r` (`FleetTelemetryMQTT.py:51`, test `:337`) removes the NameError.
- (f) `loadCarVINs` logs only `type(e).__name__`, the caplog test asserts the password is absent (`test_telemetry_registry.py:294-314`), the query runs in `__init__` with no registry or vehicle lock held, and every failure returns `{}` so the module degrades to name matching.
- The "resumed" line is now a reconnect-after-drop event, not a per-message one, and the daily `resetMQTT` does not fire it.

### Issues

**Critical**

1. **Retained MQTT redelivery is stamped "now", which reproduces the 09:17 failure on every reconnect.** `applyDataToVehicle` (`Telemetry.py:205`) observes every message at the current clock and `mqttMessage` never looks at `message.retain` (`TeslaMateVehicle.py:386-400`, `FleetTelemetryMQTT.py:45-48`). TeslaMate publishes all `cars/+/*` topics retained, and the broker redelivers them on every SUBSCRIBE: the daily `resetMQTT` (`Telemetry.py:122-131`, a new client each day), paho's automatic reconnect after a drop, and the first connect. Reproduced on an injected clock: own write of `chargeLimit=100` at t=1000, reconnect at t=1005 redelivers the retained pre-write `50`:
   ```
   before reconnect trusted: None
   after retained replay at t+5 trusted: Observation(value=50, source='TeslaMateVehicle', at=1005.0)  (write at 1000, FEED_LAG 30.0)
   ```
   `_fresher` sees 1005 > 1000 and trusts the stale value inside FEED_LAG, which is exactly "a stale TeslaMate value trusted over our own write". `noteWrite` has no production caller yet, but this task owns the feed's stamping and its own test (`test_telemetry_registry.py:123-144`) states the rule; the rule does not hold on the real broker. Fix direction, for the controller to rule on: honour `message.retain` (paho exposes it on both API versions). A retained redelivery whose value equals this source's last stored report for the field (`vehicle._fields.reported(field).get(source)`) is not news: skip the observe (no restamp, no `lastSeen` bump; liveness already makes it age 0 while the feed is live). A retained value that differs is stamped `min(now, lastWrite.at)` when a write exists for that field, so `_fresher` fails and FEED_LAG governs; `FieldStore.observe` already tolerates a stamp older than `_latest`. Needs a test with `retain=True` across a `mqttConnect` after `noteWrite`.

**Important**

2. **After `registry.forget`, the feed writes to the orphan forever and TeslaMate goes dark for the re-created car.** `TelmetryBase.vehicles` holds direct `Vehicle` references (`Telemetry.py:264,282`) and neither `updateVehicles` (`:250-254`, the mapped branch renames the orphan on every retained `display_name` redelivery) nor `applyDataToVehicle` (`:202-205`) re-resolves. Reproduced: after `forget(VIN)` then `getOrCreate(VIN, "TeslaAPI")`:
   ```
   after forget: registry has [] ; feed mapped to <orphan> ; orphan chargeLimit 60
   new vehicle chargeLimit: None ; orphan: 70 ; feedLiveAt(v2): None
   ```
   The last field matters most: because `carHealthy` returns False for an unmapped vehicle (`TeslaMateVehicle.py:159-167`), the new vehicle is never vouched for, so `syncSource` reverts to `TeslaAPI`, `is_awake` goes back to `get_car_api`, and `_telemetryPluggedIn` returns False, until restart. That is the paid-reads incident shape, reachable from the Vehicles tab "Forget" action (and `expire()`, `TWCMaster.py:1624`). `CarApiVehicle` already handles this with `_liveVehicle` (`TeslaAPI.py:2087-2101`). The implementer's own carry-over is the right fix: in both methods, when `self.registry.get(vehicle.key) is not vehicle`, drop the mapping and re-map (VIN → `getOrCreate`, else name). Needs a forget/re-create test.

3. **Retained redelivery restamps a stale value as current on an unhealthy feed and keeps `lastSeen` alive forever.** Same root as #1, different consequence. With `healthy=false` (TeslaMate stopped polling), a daily reconnect re-observes the retained `state`/`pluggedIn`/... at "now":
   ```
   unhealthy feed, retained state stamped at: 2000.0 age: 0.0 lastSeen: 2000.0
   ```
   so the spec's "when the feed is unhealthy, the value ages from its last change" is defeated for a full `syncTimeout` (1 h for `syncSource`, 15 min for `is_awake`'s "online" trust). And `Vehicle.observe` defaults `seen=True` (`Vehicle.py:66-82`), so every car TeslaMate still has retained topics for is "seen" daily:
   ```
   lastSeen after replay 40 days later: 3457000.0 ; expire() -> []
   ```
   `forgetAfterDays` can never fire for such a car. The skip-unchanged-retained rule in #1 fixes both; a test that `lastSeen` is unchanged by a redelivery is needed.

**Minor**

4. (b) Lat/lon vouch uses float equality (`Vehicle.py:96`). TeslaMate publishes the API's six-decimal value, so `float()` of the same text is equal in practice; a mismatch only degrades to a fetch. Acceptable as is; worth a comment.
5. The vouch trusts the feed's `_bySource` entry; on a non-retaining broker (Fleet) that entry can predate a change the feed missed while disconnected. Implementer-flagged; the #1 fix also keeps the entry's stamp honest. No action now.
6. `loadCarVINs` (`TeslaMateVehicle.py:115-120`) has no `connect_timeout`, matching `doSyncTokens` (`:302`); an unroutable DB host blocks startup until the TCP timeout. It also runs once: if the DB was down at boot, cars are name-matched until restart. A `connect_timeout=5` and a retry from `retryUnmappedVehicles` would close both.
7. `carHealthy` returning False for an unmapped vehicle deviates from the brief's "unpublished → assume healthy"; harmless today, but the deviation should be stated in the code comment (it is) and the brief, and it is what turns #2 from "lost observations" into "lost liveness".
8. `FieldStore.observe` (`Fields.py:87-101`) now duplicates `_store`'s body instead of calling it; fine, but the "equal replaces" comment lives only on `_store`.
9. `VehicleRegistry._liveness` is typed `Callable[[Vehicle], ...]` while `sourceLiveAt` now calls it with `None` (`VehicleRegistry.py:48,267`); update the hint to `Optional[Vehicle]`.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The interfaces, the rulings and the tests are all in place and the registry edits are careful, but the one behaviour this task exists to deliver, "a stale report-on-change value is never trusted over our own write inside FEED_LAG", fails on the real broker: every daily `resetMQTT` and every reconnect replays retained TeslaMate topics stamped "now", and the probe shows the pre-write value trusted five seconds after the write. The same stamping defeats the unhealthy-feed ageing rule and blocks expiry. Separately, a Forget leaves TeslaMate writing to an orphan and never vouching for the re-created car, which is the paid-reads shape. Both are reachable in normal operation, both have small, implementer-identified fixes, and both need a test (`retain=True` across reconnect after `noteWrite`; forget then re-create; `lastSeen` unchanged by redelivery). Approve once those land.
