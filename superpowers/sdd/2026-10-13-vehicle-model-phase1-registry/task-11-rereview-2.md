# Task 11 re-review 2 (0f63241..1dda627)

I reviewed this read-only. The probes ran against a `git archive 1dda627` copy at `scratchpad/rr2`, using `scratchpad/rr1probe/r2.py`. That script replaces p1/p2: it creates the car with a live message, because under the NB2 ruling retained messages no longer create one. Focused tests (the same 9 files as before): 135 passed.

### Finding Verdicts

- **NB1 (a differing retained value is dropped behind the feed's echo): ADDRESSED.** `Telemetry.py:257-260` clamps to `write.at` only when `mine is None or mine.at <= write.at`.
  - Probe D (50; our write of 100 at 1000; echo of 100 at 1010; retained 80 at 5000) now gives `latest 80@5000`, trusted, age 0.
  - The C1 reproduction (write 100 at 1005, retained 50) still gives `trusted: None`, with latest `50@1000`.
  - D2: when the feed's last report (1000) predates our write (1001), a differing retained 60 is stamped 1001. It is not trusted at t=1005 and is trusted at t=1040, after FEED_LAG. The clamp still works where it should.
  - Test: `test_telemetry_registry.py:508`.
- **NB2 (forget or expire, then retained replay re-creates the car): ADDRESSED.** `updateVehicles(retained=True)` uses `registry.get(vin)` (`Telemetry.py:320-323`). The live-only attach is at `:209-217`, and the retry replays names as retained.
  - Probe, forget then retained replay plus `retryUnmappedVehicles()`: the car is not present.
  - Probe, forget then a live `charge_limit_soc`: the car is re-created with `lastSeen` 1100, source `TeslaMateVehicle`, chargeLimit 70.
  - Probe, first boot with retained messages only: no vehicle, 3 events parked. The first live message creates the car (lastSeen now) and replays the parked events.
  - Tests: `test_telemetry_registry.py:461,473,484`.
- **I3 end to end: ADDRESSED.**
  - Setup: car created live at t=1000, then `healthy=false`, then 40 daily reconnects, each replaying retained `display_name`/`state`/`charge_limit_soc`/`plugged_in`.
  - During the 40 days: `state` stays stamped at 1000 (age 3,456,000 s) and `lastSeen` stays at 1000. `expire()` then returns the VIN.
  - After expiry: 10 more days of daily replays, each followed by a retry, do not bring the car back. A live message afterwards re-creates it with `lastSeen` = now.
- **OOS1 (Fleet derives "online" from a retained `v/*` message): ADDRESSED** at `FleetTelemetryMQTT.py:70-72`.
  - Probe: with the car offline (DISCONNECTED), a retained `ChargeLimitSoc` leaves `state` at `offline@1000`. Retained Gear P, DetailedChargeState Stopped and connectivity DISCONNECTED change nothing, and `lastSeen` is unchanged.
  - Test: `test_telemetry_registry.py:571`.
  - Retained Gear and DetailedChargeState still derive `driving`/`charging`; the probe, including a stale-Charging case, is in Out-of-Scope #1.
- **No `updateVehicles(id, "")`: ADDRESSED.** The orphan re-map passes the stored name only. `updateVehicles` returns False on an empty name without the warning (`Telemetry.py:336-337`), and the retry is scheduled only when a name is stored (`:218-219`). Test: `test_telemetry_registry.py:498`.

### New Breakage in the Fix Diff

None at Critical or Important. Two Minor consequences of the NB2 ruling:

1. **The parked-events store grows; it is not replaced.** `applyDataToVehicle` appends every retained event for an unattached car id (`Telemetry.py:221-229`) and never de-duplicates. Probe: 10 daily replays of 3 topics left 30 entries in `unknownVehicles["7"]`. At the implementer's ~15 topics a day, that is about 5,500 small lists a year per car. It grows without bound for a car TeslaMate keeps but that never sends a live message again, such as one sold or removed while still in TeslaMate's DB.
   - The memory cost is small, and a later live message drains the list: replayed equal values are skipped, and the first differing value is stamped now with `seen=False`.
   - Simple bound: keep one entry per event, so a retained re-park replaces the earlier one. Ordering inside a car id does not matter for retained copies of distinct topics.
2. **A forgotten car TeslaMate still retains now logs a WARNING forever.** Its stored name never maps, because retained replays only attach to existing vehicles. So `retryUnmappedVehicles` reschedules every `unmappedRetrySecs` (300 s; `Telemetry.py:296-298`), and `updateVehicles` logs "no known vehicle named 'C' ... will retry" each time: about 288 warnings a day.
   - It causes no repeated cloud calls. The retry still calls `updateVehicles` with `loadList=True`, but `loadVehicleList` returns early once `carApiVehicles` is non-empty (`TeslaAPI.py:351,1294-1296`), and `registry.forget` does not touch `carApiVehicles` (`VehicleRegistry.py:125-130`).
   - Two conditional exceptions. (a) If the API list was never loaded (for example BLE-only operation with a read slot) and the forgotten car is on the account, the first retry makes one `GET vehicles`. `addVehicle` then builds a `CarApiVehicle`, which brings the car back as an API-listed vehicle, and the feed attaches to it by name. That happens once, through TeslaAPI rather than telemetry. (b) If the account lists zero vehicles, every retry repeats the `GET`. That predates this round, for any name that does not match. Passing `loadList=False` from the retry for a car id that was orphaned would close (a), if the controller wants Forget to win over the API listing as well.
   - The same pattern already existed for a TeslaMate car that is not on the API account. But this round makes every forgotten car that TeslaMate still retains permanently unmappable.
   - Option: log the warning once per car id, or drop to debug after the first retry.

Checked with no issue found: no lock is held across I/O (the live attach uses `loadList=False` on the MQTT thread); the fix adds no log lines that could carry credentials; and replaying parked events inside the live attach (`:216`) re-enters `applyDataToVehicle` only after the mapping exists, so it cannot recurse into another attach.

### Out-of-Scope Observations

1. **Retained Gear and DetailedChargeState still derive `driving`/`charging` (`FleetTelemetryMQTT.py:82,87-88`).** The unchanged-value skip does not cover this. The derived `state` is compared against Fleet's own last `state` report, not against the field the message carries.
   - Probe: the car lost connectivity while charging (live Charging, then live DISCONNECTED, so `state=offline@2000`). On reconnect at 3000, the retained DetailedChargeState Charging is itself skipped (`chargingState` stays at 2000), but it derives `state=charging@3000`. The retained connectivity DISCONNECTED then derives `offline@3000`.
   - The final state depends on the order the broker redelivers in. If connectivity comes first, an offline car ends up `charging` with a fresh stamp, and the feed's liveness keeps it at age 0.
   - The usual sequence is benign: a car that parks or stops charging publishes P or Stopped before going offline, so the retained copy is current.
   - Exposure: this needs a Fleet broker that retains messages, which the team treats as not the case.
   - Fix direction if wanted: derive no `state` from a retained `v/*` message at all, and let retained `connectivity` be the only retained source of state.
2. **Fleet attaches a car only after its `VehicleName` is seen.** The live attach requires `name` (`Telemetry.py:214`), although Fleet's `vinFor` always knows the VIN from the topic. On a non-retaining broker, a Fleet car whose name does not change after a restart is never attached. This predates the round, because attach used to happen only on the name event. With VIN-keyed attach, the `name` requirement could be dropped when `vinFor(id)` is known; the brief's verbatim test that parks nameless events applies to TeslaMate's name path.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. NB1, NB2, OOS1, the empty-name cleanup and I3 are verified end to end by probe and tests. The parked-store growth and the perpetual retry warning are Minor follow-ups.
