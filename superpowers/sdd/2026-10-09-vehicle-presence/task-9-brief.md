### Task 9: Live verification (controller runs this)

**Files:** none changed. This task is run by the controller on the live box (`ssh twcmanager`; deploys and restarts are pre-approved per the memory note), with #669 and #670 in place.

**Interfaces:**
- Consumes: the whole branch.
- Produces: a pass/fail report against the spec's "Live testing" section.

- [ ] **Step 1: Deploy the branch and restart**

Run on the box: deploy `fix/vehicle-presence`, `systemctl restart twcmanager`, then `journalctl -u twcmanager -f`.
Expected: startup logs include `BLE module initialized`, no `VehiclePresence` errors, and one `Presence check for ... nominated` line within a few minutes of the first TWC heartbeat with power.

- [ ] **Step 2: No wakes while parked and asleep**

With the car parked at home and TeslaMate showing `asleep`, from a shell on the box run `curl -X POST http://<teslamate-host>:8088/api/checkArrival` and watch the journal.
Expected: `BLE presence probe: <VIN> reachable, status VEHICLE_SLEEP_STATUS_ASLEEP` within ~5 s; no `state charge` read (`BLE charge state fetch` absent); no `wake` command; TeslaMate still shows `asleep` five minutes later. Response code 202.

- [ ] **Step 3: Depart and return**

Unplug, drive out of the geofence, return and plug in.
Expected in the journal:
- within a minute of unplugging: `Presence check for <VIN> nominated (unplug) at +300,1200,2700 s`;
- departure detected by TeslaMate (`Vehicle <VIN> presence: home -> away`) or, without telemetry, after two failed BLE probes at +5/+20 min;
- `Vehicle <VIN> departed; restoring its normal charge limit` when the Fleet API is allowed, or the single INFO line `no remote command channel can restore` with `commandPolicy: ble_only`;
- on return: `Vehicle <VIN> presence: away -> home` and `Vehicle <VIN> arrived; applying charge limit <policy limit>` within about a minute of geofence entry or first BLE contact, followed by `Set <VIN> to charge limit <policy limit>%` from TeslaBLE (or TeslaAPI).

- [ ] **Step 4: The incident case**

While away, raise the charge limit by hand in the Tesla app, then return.
Expected: on arrival `Vehicle <VIN> charge limit was set to <hand value>% by hand; adopting it as the normal limit`, then the policy limit is applied. `settings.json` `chargeLimits[<VIN>]` reads `[<hand value>, <policy limit>]`.

- [ ] **Step 5: No new stalls**

Run: `journalctl -u twcmanager --since "-2h" | grep -c "Main loop stalled"`
Expected: no higher than before the deploy (compare with the same window on the previous day).

- [ ] **Step 6: Report**

Record the outcome of Steps 2-5 in the PR description for `fix/vehicle-presence`, including the relevant journal lines. Anything that fails goes back to the task that owns it.
