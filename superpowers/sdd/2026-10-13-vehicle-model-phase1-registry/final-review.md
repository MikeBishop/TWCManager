# Final review: vehicle-model Phase 0-1 (registry and reads), eb457dc..2d872e4

Reviewer: Fable (whole-branch, cross-task). Checkout `scratchpad/wt-vm` at 2d872e4; diff package `review-final-eb457dc..2d872e4.diff` read in full; registry package read as final files. Focused tests run under the mandated memory cap: `test_registry_*`, `test_twcmaster_vin_confirmation`, `test_reads_no_wake`, `test_telemetry_registry`, `test_vehicles_page`, `test_vehicle_detail_page` -> 172 passed. Two scratch probes against the real registry classes (`final-review-scratch/vouch_probe*.py`) back the one Critical below.

Line numbers are the checkout's (final state), not the diff's.

## Strengths

- Lock discipline holds across every file I traced. Registry and vehicle locks are genuine leaves: no module call, I/O or claim callable runs under them (`Vehicle.tier` evaluates callables outside `_lock`; `expire` reads `keepsAlive` only). Documented order `_bleLock -> settingsLock -> registry -> vehicle` is respected in TeslaBLE's status bookkeeping (`_setBleStatus` releases `settingsLock` before touching the registry), in `saveSettings` (`toJSON` under `settingsLock`, file write outside) and in `loadSettings` (parse outside, assign under). I found no inversion: nothing takes `settingsLock` or a registry lock and then `_bleLock`.
- Serial thread stays dict-only: `_plugSession`, `recordVehicleVIN -> observeTwcVin`, `TWCSlave.getLastVehicle`, `num_cars_charging_now` do short locked dict work; the TWC home check moved to the background thread (a2a3e24), which is strictly better than main, where it did BLE on the serial loop.
- Reads never wake: `TeslaBLEReadSource` wakes only with `allowWake=True`, `TeslaAPIReadSource` never wakes and checks the free `vehicles/{vin}` state before a paid `vehicle_data`, and no caller passes `allowWake=True`. The old BLE wake-on-failed-read in `update_charge`/`update_location` is gone.
- Cost parity with main for the normal paths: `update_charge` now reuses a reading up to 300 s (fewer BLE/API reads than main), `update_location()` keeps main's deferral gating through `TeslaAPIReadSource.fetch`, and own-write stamps are on fields (`chargeLimit`, `availableCurrent`) that no `read()` caller reads in this phase, so the FEED_LAG re-fetch rule is dormant for cost.
- Registry lifecycle is coherent end to end: creation only from real sightings (TWC confirmation, account listing, HA discovery, live telemetry by VIN, BLE proof, user add); retained MQTT never creates or revives (verified in `Telemetry.updateVehicles`/`_observe`); write paths (`_stampWrite`, `_recordChargeRate`, HA `applyChargeLimit`) use non-creating `registry.get`; expiry skips anonymous, user-asserted and `keepsAlive` claims; unproven BLE seeds are `keepsAlive=False` so phantoms age out.
- Back-compat: an old `settings.json` loads unchanged (new keys `vehicleRegistry`, `Vehicles[vin].ble` optional; `load()` tolerates a missing/corrupt blob); every Vehicle module is still loaded on a pure-Gen2 install, so `saveSettings`' `carapi.fleetSlot` access is as safe as on main; no 3.9+ syntax (`str.isascii` is 3.7).
- Security: Jinja `autoescape=True` (`HTTPControl.py:253`), so `vin`, `addVehicleError`, car names and claim statuses are escaped; `/vehicle/add` and `/vehicle/localMgmt` validate the VIN shape before anything else; `cascade`, `sourceLiveAt`, `loadCarVINs` and `_safeNote` log exception type names only; I found no token in any new log line or page.
- Bounded loops and memory: `runPendingScans` is capped at 3 passes with a 10 s per-VIN debounce and a single follow-up requeue; `unknownVehicles` keeps the latest event per topic; VIN confirmation is capped at 3 reads and 6 re-queries; the delayed-task heap has a sequence tie-breaker.

## Critical

### C1. Recurring paid `vehicle_data` for a TeslaMate car after one feed outage

`lib/TWCManager/Vehicle/Registry/Vehicle.py:98-115` (`_liveAt`), `:138-152` (`read`), `lib/TWCManager/Vehicle/Registry/Sources.py:83-97`, `lib/TWCManager/Vehicle/TeslaAPI.py:2316-2326` (`update_location`, `maxAge=minInterval=0`).

What is wrong: a healthy report-on-change feed vouches for a field only when the latest observation is the feed's own, or when another source's value is *exactly equal* to the feed's last report. Once a cloud read has replaced the feed's value with a different one (even in the last digit), the feed stops vouching, the value ages from the cloud read, every `read()` past `maxAge` cascades again, the cloud writes a fresh (still different) value, and the loop repeats until the feed publishes a change for that field. Probe (`final-review-scratch/vouch_probe2.py`, real `VehicleRegistry`/`Vehicle`): feed down -> 1 cloud call; feed back up, parked car, six reads at 301 s -> six more cloud calls; identical digits -> none.

Scenario: TeslaMate + Fleet user (the maintainer's own setup). TWCManager starts before TeslaMate's MQTT is reachable (same host, boot order) or the broker blips. The first `car_api_charge`/`applyChargeLimit` cycle calls `update_location()` (maxAge 0): the feed is unhealthy, so the cascade pays one `vehicle_data`. TeslaMate reconnects, but the car is parked so `latitude` is never republished, and the API's `drive_state` latitude differs from TeslaMate's last published position in the trailing digits. From then on, every cycle while the car is awake at home pays one `vehicle_data` per `statusDeferral` window (300 s): about $0.024 per awake hour, every charging night, with no log line saying why. On main a TeslaMate-sourced car was never fetched. The Task 10 ruling named exactly this cost ("paid vehicle_data per deferral window per TeslaMate car") as the price of being wrong; the equality vouch added in response does not close it because the re-fetched value is different again. `batteryLevel` self-heals (ints, and it changes while charging); `lat` does not.

Fix (small): while a report-on-change source is healthy and has *any* report of the field for this vehicle, treat the field as current and prefer that source's own observation. Concretely, in `Vehicle.read()` before the age check: `for src, mine in self._fields.reported(field).items(): live = self._registry.sourceLiveAt(src, self); if live not in (NOT_TRACKED, None): return mine` (respecting `trusted()`/FEED_LAG for a pending own write). Equivalently, drop the `mine.value != obs.value` condition in `_liveAt` so a live feed vouches for the field regardless of value. The feed is authoritative while healthy by the spec's own rule ("a value can be old but current"); a value it last reported is at least as good as a polled value it has not contradicted. Add a test: feed down -> one fetch; feed back up, differing value -> no further fetch.

## Important

### I1. Add-by-VIN creates a permanent vehicle with no way to remove it

`lib/TWCManager/Control/HTTPControl.py:70-85`, `lib/TWCManager/Vehicle/Registry/VehicleRegistry.py:118-123`, `:132-152` (`expire` skips `userAsserted`).

The Task 16 ruling deferred Forget to Phase 6 (a Forget that leaves a `CarApiVehicle` behind would be undone by its next write). That reasoning does not apply to a user-asserted VIN with no attachments, which is the only kind Add-by-VIN makes. A mistyped VIN is now: a persisted registry entry that never expires, a `settings["Vehicles"]` record, a generated BLE keypair, a row on the Vehicles page, and (because TeslaBLE's all-vehicle `car_api_charge`/`applyChargeLimit`/`setChargeRate` iterate `settings["Vehicles"]`) one tesla-control timeout under `_bleLock` on every all-vehicle BLE command for as long as the install lives. The only remedy is editing `settings.json` by hand. The spec sells Add-by-VIN as the bootstrap path for BLE-only users, and lists Forget beside it; a reasonable user expects to undo a typo. Shipping the trap without the undo is a spec gap with ongoing cost (BLE lane time), not cosmetic.

Fix: a scoped Forget for vehicles that are user-asserted and have no attachments (`registry.forget(vin)`; `settings["Vehicles"].pop(vin)`; `queue saveSettings`), exposed on the per-car page. Fifteen lines plus a test. If the ruling stands, at minimum reject the add when a BLE scan is possible and says "not in range", and document the hand edit in the CHANGELOG.

### I2. TeslaBLE's all-vehicle commands still iterate `settings["Vehicles"]`, so refused and seeded phantoms keep costing BLE time

`lib/TWCManager/Vehicle/TeslaBLE.py:323` (`car_api_charge`), `:713` (`setChargeRate`), `:783` (`applyChargeLimit`); claims dropped at `:1859-1917`.

The registry now knows which VINs have a usable BLE key (claim present, status paired/unproven) and which the car refused (`_setBleStatus("refused")` drops the claim and the next boot skips it). The command loops do not consult it: a refused key, a history-only VIN or an Add-by-VIN typo still gets `wakeVehicle` + `sendCommand` (each a tesla-control run with a 5-15 s timeout, under `_bleLock`) on every all-vehicle command. `_execute_with_retry` stops retrying a refused key within one command (good), but the next command repeats it. Main did the same with three retries, so this is not a regression; it is the Phase 1 plan's "existing modules read the registry" promise left half-applied in the one place where the registry has new information. Scenario: two cars, one sold (key refused), Track Green Energy: every rate change spends a tesla-control timeout on the dead VIN before reaching the live one, and the BLE lane is also shared with the reads from the policy thread.

Fix: in the three loops, skip a VIN whose registry vehicle has no `TeslaBLE` claim (or whose stored `ble.status == "refused"`); `_claimKeyedVehicles` already encodes the rule. One helper, three call sites, one test.

### I3. `FleetTelemetryMQTT.vinFor` returns any topic segment, so a shared broker creates and persists junk vehicles

`lib/TWCManager/Vehicle/FleetTelemetryMQTT.py:34-36`; `Telemetry.py:184-230` (`vin and self.vinInTopic` creates on a live message).

Ledger lists this as a deferred minor; I am promoting it because it is a creation path. Fleet telemetry topics are `<prefix>/<vin>/v/<field>` and `<prefix>/<vin>/connectivity`, and the module subscribes to `<prefix>/#`. Any other live publisher under the same prefix (the telemetry server's own status topics, a second integration, a typo'd prefix) yields a live message whose second segment is not a VIN; `vinFor` returns it, `getOrCreate("STATUS", ...)` accepts anything ASCII, the vehicle is persisted in `settings["vehicleRegistry"]`, shown on the Vehicles page, and re-created on the next live message after it ages out. Fix: `return vehicle_id if isWellFormedVIN(vehicle_id) else None` (and the same guard in `TeslaMateVehicle.loadCarVINs` rows). One line each.

### I4. `getOrCreate` accepts any ASCII string as a VIN

`lib/TWCManager/Vehicle/Registry/VehicleRegistry.py:72-91`.

Related to I3 but a separate hole: `_getOrCreate` rejects only empty, non-str, non-ASCII and `anon:` keys. Callers that feed it today are the TWC (well-formed check in `observeTwcVin`), the Tesla account list, HA discovery (`VIN_REGEX`), TeslaBLE (well-formed check) and telemetry (I3). The registry is the one place that can hold the line for every future provider (Phase 2 adds several). A malformed key also breaks the Vehicles page's per-car link (`/vehicleDetail/<key>` renders, but `vin[9]` model-year lookups and the manufacturer table assume 17 chars). Fix: require `isWellFormedVIN` in `_getOrCreate`; keep `load()`'s tolerant path (skip, log once) so an older persisted blob with a bad key does not raise.

### I5. `endPlugSession` fires on charge stop, not unplug, so `twcVin`/`point` flap on every pause

`lib/TWCManager/TWCMaster.py:1286-1296` (`num_cars_charging_now`, 5 s below-threshold debounce), `VehicleRegistry.py:166-174`.

The registry's "plug session" is wired to `isCharging`, which TWCManager derives from amps. A car that stays plugged in but stops drawing (policy stop, charge complete, scheduled charging, preconditioning gap) ends the session: the anonymous vehicle is deleted, `twcVin` is observed `None`, the confirmation state is cleared, and when charging resumes the TWC re-queries the VIN and re-confirms. Nothing in Phase 1 decides on `twcVin`, so there is no behaviour cost today, but Phase 2 (charging points) and Phase 5 (presence) will build on `vehicleAt`/`pointFor`, and the spec says anonymous vehicles "end with the plug session". Flag now so the next plan does not inherit "session == charging" silently: either rename to `chargeSession` in the registry API, or keep the point attribution until the TWC reports no pilot/VIN. No code change required in this phase; a one-line docstring on `beginPlugSession`/`endPlugSession` stating the actual trigger would do.

## Minor

- M1. `TWCMaster.recordVehicleVIN` (`TWCMaster.py:1498-1517`) now takes `settingsLock` on the serial thread; it can wait on `saveSettings`' `json.dumps` or `process_save_schedule`. Both are CPU-only and short (settings is small), so this is acceptable, but it is the first lock the serial thread shares with HTTP threads. Keep the rule "nothing under `settingsLock` does I/O" written where future writers will see it (the lock's comment at `TWCMaster.py:113-116` says so; add "including on the serial thread").
- M2. `queue_background_task(delay>0)` is now called from the serial thread (`TWCMaster.py:1468-1471`) while `getBackgroundTask` pops the same list on the background thread, both unlocked. CPython list ops are individually atomic, so the worst case is a confirmation read dispatched a few seconds early or a slightly out-of-order heap; not a crash. Cheap to guard both sides with `backgroundTasksLock` (ledger Task 7 note).
- M3. `TeslaBLE._bluezAddresses` (`TeslaBLE.py:1767-1780`) returns an empty set when `bluetoothctl devices` exits non-zero with output, which reads as "Not in range" rather than "Range unknown". Ledger deferred minor; verdict below.
- M4. `HomeAssistant.setChargeRate` (`HomeAssistant.py:693`) does not stamp `availableCurrent`, unlike TeslaAPI and TeslaBLE. Ledger deferred minor; verdict below.
- M5. `process_home_location` "unset" (`HTTPControl.py:1719-1720`) still `del`s keys that may be absent, now inside `settingsLock`; a second click returns a 500. Pre-existing; one-line `pop(..., None)`.
- M6. `deleteSlaveTWC` (`TWCMaster.py:828`) does not end the point's plug session, so a retired TWC's "Unknown car on TWC xxxx" row stays until restart (not persisted). One call to `endPlugSession`.
- M7. `_setBleStatus` (`TeslaBLE.py:1859-1876`) creates a `settings["Vehicles"]` record for any well-formed VIN posted to `/vehicle/localMgmt op=pair`, even when pairing could not start (no key). Unauthenticated LAN POSTs can seed records; the UI is unauthenticated throughout, so this is consistent with the rest, but the record should not be created on `pairing_failed` with reason "Could not prepare the public key".
- M8. `CarApiVehicle.vehicle` (`TeslaAPI.py:2099-2106`) re-creates a forgotten vehicle on any attribute write. Documented and ruled (Task 9 carry to Phase 6); fine for a car the account lists, but Forget in Phase 6 must also drop the `CarApiVehicle`, as the ledger says.
- M9. The legacy placeholder VIN `00000000000000000` (still special-cased in `vehicleDetail.html.j2:31`) passes `isWellFormedVIN`; an old `settings["Vehicles"]` entry for it with a generated key would be seeded as an unproven BLE claim on the upgrade boot and listed as a car. Reject it in `isWellFormedVIN` or in `_claimKeyedVehicles`.
- M10. `vehicles.html.j2` and `vehicleDetail.html.j2` call `summary()` per row, which evaluates every claim callable and every liveness callable per field; trivial today (a few cars), but `summary()` is also what the WebIPC debug dump prints. No action.

## Deferred-minors verdicts (fix in the final wave: yes/no)

- T1 cherry-picked test line > 88 cols: no.
- T1 `startCarsCharging` no longer replaces pending stop; no-arg `cancelStopCarsCharging` cancels all: no (upstream design, covered by tests).
- T2 `respondToSlaves` writes reached from the policy thread: no (single-key).
- T2 comment pinning `json.dumps` default args: already done (`TWCMaster.py:1649-1651`); no.
- T2 TeslaBLE loops iterate `list(...)`: already done; no.
- T2 `addkWhDelivered` read-modify-write unlocked; `process_save_schedule` long lock: no.
- T3 read methods do not validate field names: no.
- T4 key/vin agreement, anon prefix: closed by Task 6's key rule; no.
- T6 `lastSeen` read without the vehicle lock; version never checked; garbage `lastSeen` loads as now: no.
- T7 entitlement run twice; `_plugSession` from HTTP thread; first session recorded late: no. Anon vehicle leak on `deleteSlaveTWC`: yes (M6, one line).
- T7 note `backgroundTasksDelayed` insort vs `pop(0)` unlocked: yes if cheap (M2); otherwise carry to Phase 4 where the task queue is reworked.
- T8 stale `vehicleRegistry` snapshot between saves; round-trip test gaps; wiring untested: no.
- T10 deferral with no stored value returns False; lat-then-missing-lon; home check no longer forces atHome when asleep; all-None BLE reply falls to cloud: no (ruled/accepted; equivalent to main where it matters).
- T10 note `vehicle_data` without drive/charge state sets no deferral: no (pre-existing).
- T11 `refreshIdentities` only while `carVINs` empty; empty cars table queried every retry: no.
- T11 final-wave items: `orphanedIds` in `_dropIfOrphan`: no (list load is a no-op after the first load; `vehicle` property re-creates anyway). Retained parked entry replacing a live one: no (creation happens on the name message, not on replay). Fleet multi-topic state ordering: no (pre-existing shape). 17-char VIN check in `FleetTelemetryMQTT.vinFor`: yes (promoted to I3).
- T12 HA claim static; batching at end of refresh: no.
- T13 refused car never trips the circuit breaker: no as stated, but see I2, which removes the cost at the source.
- T13 expired never-proven car regains its claim only on next boot: no (self-heals; commands still reach it).
- T14 `HomeAssistant.setChargeRate` does not stamp `availableCurrent`: yes (M4; Phase 3 will rely on stamps being uniform; three lines).
- T15 debug dump lost `CarApiVehicle` state; unchecked TeslaAPI uses in `WebIPCControl`/`Policy.py:316`: no (module always loads; released only on hard failure).
- T15 `process_home_location` del on unset raises: yes (M5, one line, user-visible 500).
- T16 raw `vin` field in `/vehicle/add` (int coercion drops leading zeros): no (no VIN starts with 0; 2b91330 already stringifies).
- T17 Pair synchronous on the HTTP thread under `_bleLock` up to 30 s; scans block the background thread ~8 s per VIN: no (same as main for pair; scan is user-initiated and debounced).
- T17 `_bluezAddresses` non-zero exit with output gives empty set: yes (M3; `if code != 0: return None`, one line, avoids a false "Not in range").
- T17 `TWCManager.py` requeue glue untested: no.
- T17 carry (live check): healthy `bluetoothctl --timeout 8 scan on` exit code on the box is still unknown; if it is non-zero, every miss reads "Range unknown". Not a code fix; must be checked on the box before the Vehicles-tab changelog line is believed.

## Declined to judge

- `is_awake()` pinning False forever when a dead telemetry feed's last state was "asleep": identical to main (main's stale-sync thread also required `is_awake()` True to switch back); pre-existing.
- `loadVehicleList` retry every 300 s from `retryUnmappedVehicles` for an unmappable TeslaMate name: pre-existing cadence; now warns once.
- Fleet `vehicles` list endpoint pricing: not in the price list the user supplied; unchanged call pattern from main.
- HTTP UI being unauthenticated (anyone on the LAN can add VINs, request scans, pair): pre-existing design of the whole UI; the new handlers validate inputs and escape output, which is all this phase can do.
- Whether TeslaMate's published `latitude` digits differ from `drive_state` for a parked car: I could not verify against a live feed; C1 is reported on the mechanism (probe-confirmed) with that as its stated precondition.
- Owner-API `vehicles/{vin}` path shape in `get_car_api`: unchanged.
- Commit trailers (Sonnet/Opus mix): ruled; cosmetic.
- Pure-Gen2 "no Vehicle module loaded" scenario: every Vehicle module is in `modules_available` and loads regardless of config, so `getModuleByName("TeslaAPI")` is None only after a hard release; the tests' no-module master is stricter than production.
- `.read()`/`maxAge` tuning per caller (300 s for charge, 0 for location): builder's call per spec; cost parity with main checked.

## Assessment

Ready to merge: **With fixes.**

Blocking: C1 (recurring paid read after a feed outage; small fix in `Vehicle.read`/`_liveAt`, probe and test provided). Strongly recommended before merge, since Docker `:latest` tracks main and both are user-visible on day one: I1 (Add-by-VIN with no undo) and I3/I4 (junk VINs can enter and persist). I2 and I5 can follow in the fix wave or the Phase 2 plan, but I5 must be written into the Phase 2 plan's assumptions if deferred. Deferred-minor "yes" items are each one to three lines.

Everything else I looked for in the brief's focus list (lock inversions, I/O under leaf locks, serial-thread blocking, token leakage, HTML escaping, unbounded loops, upgrade-boot behaviour, retained-MQTT revival, expiry) checks out.
