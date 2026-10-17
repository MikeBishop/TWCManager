# Task 11 re-review 3 (1dda627..0fe3413)

I reviewed this read-only. The probes ran against a `git archive 0fe3413` copy at `scratchpad/rr3`, using `scratchpad/rr1probe/r2.py` (a regression re-run) and the new `scratchpad/rr1probe/r3.py`. Focused tests (the same 9 files as before): 140 passed.

### Finding Verdicts

- **Regression re-run (r2.py): no regressions.** Every r2 line matches round 2:
  - C1: `trusted: None`.
  - Probe D: 80 kept and trusted.
  - D2: not trusted at 1005, trusted at 1040.
  - I3: `state` stays at 1000, `lastSeen` stays at 1000, `expire()` fires, 10 days of replays plus retries do not revive the car, and a live message re-creates it with `lastSeen` = now.
  - Forget then retained: not present. Forget then live: present.
  - The parked count after 10 days is now 3 (it was 30).
- **(1) Bounded parked store: ADDRESSED** (`Telemetry.py:235-242`). One entry is kept per (car id, topic), replaced and moved to the end. Probe: 10 daily replays of 3 topics leave 3 entries. Test: `test_telemetry_registry.py:592`.
- **(2) WARNING once, then DEBUG: ADDRESSED** (`Telemetry.py:376-383`). Probe: one WARNING, then DEBUG on each retry; the record is cleared when the car id maps (`:349-350,371-372`). Test: `:607`.
- **(2) The retry for a forgotten car uses `loadList=False`: PARTIALLY ADDRESSED.** It works when the first message after the forget is a data event, but not when it is a retained display_name (Minor, New Breakage #1).
  - Probe, first post-forget message is retained data: `orphanedIds={'7'}`, 0 `loadVehicleList` calls.
  - Test: `:622`.
- **(3) Fleet derives no state from retained `v/*`: ADDRESSED** (`FleetTelemetryMQTT.py:101-104`).
  - The stale-Charging probe from round 2 now leaves `state` at `offline@2000`. Retained P, Stopped and ChargeLimitSoc change nothing. Test: `:639`.
  - **Can retained connectivity still mislead?** Mostly no, because of the unchanged-value skip:
    - Retained CONNECTED: when Fleet's last `state` is online, nothing is written (`syncState == newSyncState`). When it is driving or charging, CONNECTED is excluded by the existing rule. When another source has set a newer state, the `_observe` skip catches it, because Fleet's own last report equals "online".
    - Retained DISCONNECTED: when it differs from Fleet's last report, that is real news (the car disconnected while we were off the broker). It is stamped now with `seen=False`.
    - The one misleading case is Out-of-Scope #1.
- **(4) Fleet attaches by topic VIN on live messages: ADDRESSED, and it respects the ruling that retained data never creates or revives a vehicle.** The `vinInTopic` gate sits inside `if vehicle is None and not retained` (`Telemetry.py:217-228`).
  - Probe, retained BatteryLevel plus retained CONNECTED with no name: no vehicle is created, and both events are parked.
  - Probe, a live BatteryLevel with no name: the car is created, `lastSeen` is now, the parked events are replayed, and `state` is online.
  - After a forget: retained BatteryLevel, CONNECTED and VehicleName plus a retry do not revive the car, and the retry makes no `loadVehicleList` call because the id is in `orphanedIds`. A live connectivity message then re-creates it (live, as ruled).
  - Test: `:656`.

### New Breakage in the Fix Diff

None at Critical or Important. Minor:

1. **`orphanedIds` is filled only on the data-event path** (`Telemetry.py:213-216`), not where `updateVehicles` drops an orphan (`:330`).
   - If the first message after a forget or expiry is TeslaMate's retained `display_name`, the mapping is dropped without recording the id. Every later retry then passes `loadList=True`.
   - Probe: forget, then retained display_name, then two retries gives `orphanedIds=set()` and 2 `loadVehicleList` calls (mocked). The expiry path with display_name first gives 1 call.
   - TeslaMate subscribes `battery_level` and `charge_limit_soc` before `display_name` (`TeslaMateVehicle.py:63-66`), so retained data usually arrives first and the id is recorded. The order is not guaranteed.
   - Impact is the round-2 exception (a): in practice `loadVehicleList` returns early once the list is loaded (`TeslaAPI.py:351`). Only when the list was never loaded does it make one GET and bring the car back via TeslaAPI.
   - Fix: record the id in `_dropIfOrphan` itself (`:244-251`), which covers both call sites.
2. **A live parked entry can be replaced by a retained copy of the same topic** (`Telemetry.py:240-242`). Probe: a live `charge_limit_soc 60` for a car id that cannot be mapped yet (no name), then a retained `60`, leaves `[['charge_limit_soc', '60', True]]`. The live entry, and the sighting it would have counted on replay, is lost.
   - Small: a live message attaches immediately whenever it can, so this happens only before a name, VIN or registry match exists.
   - Fix if wanted: don't let a retained entry replace a live one.

Checked with no issue found:
- No lock is held across I/O. The Fleet live attach uses `loadList=False` on the MQTT thread.
- No new log line can carry credentials. The warning text is unchanged; only its level changes.
- Both `warnedUnmapped` and `orphanedIds` are cleared when the car id maps.

### Out-of-Scope Observations

1. **Fleet's `state` comes from several topics, so round 1's "a differing retained value is news" reasoning does not hold for it.** `_observe` stamps a retained value now when it differs from Fleet's last `state`. Probe: live DISCONNECTED at 2000, then live Gear D (state `driving@2100`) with no CONNECTED in between, then a reconnect at 3000 with retained DISCONNECTED gives `offline@3000`. The older connectivity value overrides the newer driving state.
   - This needs `v/*` data after a DISCONNECTED with no CONNECTED in between. fleet-telemetry normally emits CONNECTED on reconnect, so this is an anomaly path, and it matters only for a broker that retains messages.
   - Fix direction if wanted: compare retained connectivity against Fleet's last connectivity-derived state, or skip retained connectivity when Fleet's last `state` report is newer than any connectivity message seen.
2. **The registry accepts any non-empty ASCII string as a VIN** (`VehicleRegistry.py:72-79`). With topic-VIN attach, a live Fleet message whose second topic segment is not a VIN creates and persists a registry vehicle. Probe: `telemetry/notavin/v/BatteryLevel` created `NOTAVIN`.
   - fleet-telemetry always puts the VIN there, and only `v/` and `connectivity` reach `applyDataToVehicle`, so this is theoretical. It predates this round, because the name-then-VIN path accepted the same id.
   - Fix if wanted: a 17-character VIN shape check in `FleetTelemetryMQTT.vinFor`.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. One Minor gap: `orphanedIds` is not recorded when a retained display_name is the first message after a forget, and recording it in `_dropIfOrphan` fixes it. A retained copy replacing a live parked entry is a second small Minor.
