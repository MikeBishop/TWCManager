# Task 11 re-review 1 (ac202a1..0f63241)

I reviewed this read-only. The probes ran against a `git archive 0f63241` copy at `scratchpad/rr1`. The probe scripts are `scratchpad/rr1probe/p1.py`, `p2.py` and `p3.py`, each run with the rr1 root as argv[1]. Focused tests (telemetry_registry, telemetry_mapping, telemetry_timers, registry_fields, registry_vehicle, registry_membership, carapivehicle_registry, registry_read_cascade, twcmaster_registry): 130 passed.

### Finding Verdicts

- **C1 (retained redelivery beats own write): ADDRESSED.** See `Telemetry.py:235-251`, where `_observe` skips an equal retained value at `:245` and stamps a differing one `min(now, write.at)` with `seen=False` at `:250-251`. TeslaMate passes `message.retain` at `TeslaMateVehicle.py:414`, and Fleet passes it at `FleetTelemetryMQTT.py:56`. I re-ran the reviewer's reproduction: own write `chargeLimit=100` at t=1000, then a reconnect at t=1005 redelivers retained 50. The result is `trusted: None` and latest `50@1000`, so 50 is not restamped and not trusted inside FEED_LAG. On the Fleet path the same case also gives `trusted: None`, with `lastSeen` unchanged. Parked events keep the flag (`Telemetry.py:220-224,260-262`). Tests are at `test_telemetry_registry.py:372-446`.
  - The fix itself adds a new problem: a differing retained value can now be dropped. See New Breakage #1.
- **I3 (unhealthy feed + replay; lastSeen; expiry): PARTIALLY ADDRESSED; a ruling is needed (New Breakage #2).**
  - What holds: with `healthy=false` and a retained `state` replay at t=2000, `state` stays stamped at 1000 (age 1000) and `lastSeen` stays 1000. Forty days later, `expire()` returns the VIN.
  - What fails: the car comes back at the next retained replay (details in New Breakage #2), so the outcome the ruling wanted, an expired car staying gone, does not happen.
  - Fleet: payload values are fixed. The `state` value Fleet derives from a message is not (Out-of-Scope #1).
- **I2 (forget → re-resolve): ADDRESSED.** `_dropIfOrphan` (`Telemetry.py:226-233`) is used in `applyDataToVehicle` (`:205-213`) and `updateVehicles` (`:301`).
  - Probe: after forget, a re-created v2 gets `chargeLimit=70`, the orphan keeps 50, the feed maps to v2, and `feedLiveAt(v2)` is now. It returns None when the car's healthy topic is false.
  - `TeslaMateVehicle.carHealthy` for an unmapped vehicle uses the health of the car id matching its VIN, else returns True (`TeslaMateVehicle.py:165-177`). `vehicle=None` returns True (`:166-167`).
  - Tests are at `test_telemetry_registry.py:449-470,502`.
- **Minor, float-equality comment: ADDRESSED** at `Vehicle.py:101-103`.
- **Minor, loadCarVINs `connect_timeout=5` and retry: ADDRESSED** at `TeslaMateVehicle.py:120`, with `refreshIdentities` at `:146-149` called from `Telemetry.py:280`. Tested at `test_telemetry_registry.py:476`.
- **Minor, FieldStore.observe uses `_store`: ADDRESSED** at `Fields.py:98`. The per-source rule is now in `_store` at `:83-87`.
- **Minor, `Optional[Vehicle]` hints: ADDRESSED** at `VehicleRegistry.py:48,262`.

### New Breakage in the Fix Diff

1. **Important (latent): a differing retained value stamped at an old own write is dropped when the feed has reported since that write. The stale value is then trusted indefinitely.** Location: `Telemetry.py:249-251`.
   - Why: `_observe` stamps the differing value `min(now, write.at)`. If this source's own report is newer than the write (for example its echo of the write), `FieldStore._store` (`Fields.py:83-91`) rejects the older stamp in both `_latest` and `_bySource`.
   - Probe D (p1.py) setup:
     - TeslaMate reports 50.
     - We write 100 at t=1000.
     - TeslaMate echoes 100 at t=1010.
     - The connection drops and the owner sets 80 in the app, which TeslaMate publishes and the broker retains.
     - We reconnect at t=5000 and receive retained 80.
   - Probe D output:
     ```
     latest: Observation(value=100, source='TeslaMateVehicle', at=1010.0) reportedBy TM: Observation(value=100, ..., at=1010.0)
     trusted: Observation(value=100, ...) age: 0.0
     next day: latest 100 age 0.0
     ```
   - Consequence: the change to 80 is lost. The feed vouches for 100 at age 0 on every reconnect until TeslaMate publishes the next change.
   - This answers the controller's cost question. Stamping at the old write does not force paid reads while the feed is live, because the feed's liveness keeps the age at 0. The risk runs the other way: a wrong value is trusted with no reads at all. When the feed is not live, the value's age counts from the old write, which at most brings a fetch forward (a small cost).
   - Why "latent": `noteWrite` has no production caller yet. C1 was raised under the same condition, so the same standard applies here.
   - Fix direction (checked on a scratch copy, `scratchpad/rr1fix`): clamp to `write.at` only when `mine is None or mine.at <= write.at`; otherwise stamp now. The broker keeps only the latest publish, so a retained value that differs from `mine` was published after `mine.at`. With that change, probe D keeps 80 and trusts it, the reviewer's reproduction still gives `trusted: None`, and `test_telemetry_registry.py` still passes (30 tests). This needs a test.
2. **Important (ruling needed): a forgotten or expired car is re-created by the feed's next message, retained or live, with `lastSeen` = now.**
   - Path: after a forget, `_dropIfOrphan` → `updateVehicles(..., retained=True)` → VIN → `registry.getOrCreate` (`Telemetry.py:205-213,308-315`) re-creates the car.
   - Probe p3, Forget in the UI: after forget, one live `charge_limit_soc` re-creates the car (`lastSeen 1100, source TeslaMateVehicle`). A retained `display_name` alone also re-creates it (`lastSeen 1200, source 'created'`).
   - Probe p2, expiry: after a 40-day `expire()`, the next daily retained replay re-creates the car with `lastSeen` = now, and its stale retained `state` is stamped now, because a fresh vehicle has no `reportedBy`.
   - Effect: `expire()` fires, but the forget is undone within a day for any car TeslaMate still retains, and a UI Forget lasts only until the next telemetry message.
   - Trade-off for the controller: retained messages could attach only to an existing vehicle (`registry.get`), with no `getOrCreate`. But then, on a first boot with no persisted registry and no TeslaAPI (BLE-only), the feed would never learn its cars. A middle option: a retained-only create gets an old `lastSeen` (or no sighting at all), and a forgotten VIN is not re-created from retained data.

There are no locking, I/O or credential regressions:
- `refreshIdentities` runs the DB query on the unmapped-retry timer thread with no lock held, using `connect_timeout=5`.
- Reassigning `carVINs` is atomic, so it is safe against `list(self.carVINs.items())` on the MQTT thread.
- The orphan re-map on the MQTT thread passes `loadList=False`, so it does no I/O.
- The fix adds no log lines that could carry credentials.

### Out-of-Scope Observations

1. **Fleet derives `state` from retained messages.** In `FleetTelemetryMQTT.py:70`, any `v/*` message sets `newSyncState="online"`, including a retained redelivery, and the result is a value differing from the stored one, stamped now.
   - Probe E: the last connectivity was DISCONNECTED (`state=offline`). A retained `ChargeLimitSoc` replay sets `state` to `online@3000`. On a reconnect, `state` swings online→offline with fresh stamps, and where it ends depends on redelivery order.
   - The broker re-sending a message says nothing about whether the car is online. Fix direction: don't derive `"online"` from a retained `v/*` message, and let retained `connectivity` be the only retained source of state.
   - Exposure: this matters only if the Fleet bridge's broker retains messages. The team treats it as non-retaining, which makes this conditional.
2. `refreshIdentities` reloads only while `carVINs` is empty and some name is still unmapped. If the DB was down at boot and every car then mapped by name, VINs are never reloaded. If the cars table is legitimately empty, the DB is queried on every retry. Both are low impact.
3. When a forget leaves a car unmapped and `vehicleNames` has no name for it, the re-map calls `updateVehicles(id, "")` (`Telemetry.py:208-210`). That logs a warning about a vehicle named `''` and schedules a retry. This is cosmetic.

### Verdict

**Fix round:** Findings remain open. C1, I2 and all minors are addressed. I3 is only partly met, because expiry and Forget are undone by re-creation from the feed (New Breakage #2, ruling needed). The fix also adds new Important breakage #1: a real change delivered as a differing retained value is dropped when the feed reported after our write. It is latent until `noteWrite` gets a production caller, and the one-line fix direction above is verified on a scratch copy.
