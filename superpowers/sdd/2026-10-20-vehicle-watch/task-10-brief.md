### Task 10: Docs and changelog

**Files:**
- Modify: `docs/Settings.md`, `docs/PolicyCustomization.md`, `docs/modules/Vehicle_TeslaBLE.md`, `docs/modules/Vehicle_FleetTelemetryMQTT.md`, `CHANGELOG.md`

- [ ] **Step 1: `docs/Settings.md`:** a `### Vehicle watch` section after Vehicle Command Policy: who is watched (every car no TWC names and no live feed covers), the three rings in one paragraph each, the cadence table from the spec with the defaults from `DEFAULTS`, the budget (`monthlyBudgetUSD`, default $3 of the $10 credit that also covers commands, wakes and Fleet Telemetry), the EMS trigger, and the `watch` config keys. Note `cloudUpdateInterval` is ignored.
- [ ] **Step 2: `docs/PolicyCustomization.md`:** in the Charge Limits presence text, replace "no Tesla API read is made just to place a car" and the "a car charging away from a TWC ... is not watched ... a separate feature ... is planned" sentences with: status checks are free and never wake; reads happen on change; a car a feed or a TWC covers is not watched; see Settings.
- [ ] **Step 3: `docs/modules/Vehicle_TeslaBLE.md`:** the sleep-safe check paragraph gains: it needs no pairing, and while the car is awake it also reports whether the charge-port door is open; a closed door counts as unplugged, an open one is confirmed by a charge read.
- [ ] **Step 4: `docs/modules/Vehicle_FleetTelemetryMQTT.md`:** one paragraph recommending `minimum_delta` for `ChargerVoltage`, `ACChargingPower` and `BatteryLevel` (values whose small changes nothing needs), with the Fleet Telemetry price ($1 per 150k values) and a note that the watch covers the car while the feed is down.
- [ ] **Step 5: `CHANGELOG.md`** under v1.4.0 Features (or the next version if 1.4.0 is tagged; ask): one entry for the watch (what it does, cadences, budget, EMS trigger), one for the charge-port door and keyless ping, one under Architecture for the removal of `cloudUpdateInterval`, the deferral ladder and the half-hourly battery refresh.
- [ ] **Step 6: Commit**

```bash
git add docs CHANGELOG.md
git commit -m "Document the vehicle watch"
```

---


## Controller additions (decisions made during Tasks 1–9; these override the plan text above where they differ)

- Step 4 (Fleet Telemetry doc): the minimum_delta recommendation already exists — don't duplicate it. Add only one sentence that the watch covers a car while its feed is down, plus the Fleet Telemetry price ($1 per 150k values).
- Cadences and rules to document as built (read `Watch.py` DEFAULTS/settingsOf for exact names and defaults):
  - The return time after a car leaves is the fix time plus straight-line distance to home at 120 km/h (75 mph, a `watch` setting), at least 300 s. Before it, nothing runs for that car.
  - Owner API location reads are free and allowed even where a scan is possible; Fleet's paid location read only where no scan is possible.
  - A car Bluetooth has lost (away, missed):
    - with a TeslaAPI status source, scanned every scanAwaySecs only while awake and after its return time;
    - with no such source, scanned (or pinged where no scan is possible) every scanAwaySecs for awayAsleepSecs after its last sign of life, then every awayAsleepSecs.
  - One bluetoothctl scan covers every car.
  - After a feed drops, the watch picks a car up at its next due check (up to one cadence), not instantly.
  - After a restart, the first pass reads nothing; a car first seen later still gets its arrival read.
  - The consumption step reads every candidate car at once and is off without a consumption meter.
- `cloudUpdateInterval`: the Powerwall module still uses it. Reword the shipped config comments (`etc/twcmanager/*.json`) and Settings.md so it is described as the Powerwall's cloud cache time, no longer used for car reads.
- Docker: add `- CAP_SYS_PTRACE  # nsenter opens the host's network namespace through /proc/1/ns` to cap_add in contrib/docker/docker-compose.yml (the same change as ngardiner/TWCManager#711). Make sure docs/modules/Vehicle_TeslaBLE.md's Docker paragraph names the /run/dbus mount, the DBUS env, bluez in the image and CAP_SYS_PTRACE.
- CHANGELOG: also note that a power start now reads cars at home only.
