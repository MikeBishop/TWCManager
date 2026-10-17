### Task 13: Merge token slots (#692) and port the presence code to the slot API

**Files:**
- Conflicts: mainly `lib/TWCManager/Vehicle/TeslaAPI.py`, resolved as in `.superpowers/deploy-presence-2-merge-report.md` items 1–4.
- Port: `lib/TWCManager/PresenceSources.py`, `lib/TWCManager/PresenceHandlers.py`, `lib/TWCManager/Vehicle/TeslaAPI.py` (`vehicleOnlineStates`), and the tests that 92dae4d touched
- Test: `tests/unit/test_plug_presence_scenarios.py` (a deploy-level class)
- Create: `.superpowers/deploy-presence-3-merge-report.md` (same shape as the presence-2 report)

**Interfaces:**
- Consumes: the token-slot API: `slotFor("read" | "command") -> TeslaTokenSlot | None`, `slot.accessToken`, `slot.verifyCert`, `vehicleListURL(slot)`, `slotRequestFailed(slot, req)` and `storeToken(...)` in tests.
- Port mapping (from 92dae4d): `apiSource` uses `api.slotFor("read") is None` in place of `not api.getCarApiBearerToken()`. `hasRemoteChannel` uses `api.slotFor("command") is None`. `vehicleOnlineStates` reads `slotFor("read")` and `vehicleListURL(slot)`, sends `slot.accessToken` and `verify=slot.verifyCert`, and on 401/403/410/412 calls `slotRequestFailed`.

- [ ] **Step 1: Branch and merge**

```bash
git branch deploy/presence-3 presence/4-fleet-rate-queue
git checkout deploy/presence-3 && git merge --no-ff feat/token-slots   # fe764ff
```

- [ ] **Step 2: Resolve the conflicts as in the presence-2 report, then commit the merge**

The subject is `Merge feat/token-slots (#692) into deploy/presence-3`, and the message lists each conflict and how it was resolved. Then run the suite. The failures here should all come from removed accessors.

- [ ] **Step 3: Port the code, then check for leftover accessors**

Try `git cherry-pick -n 92dae4d` and resolve it against the new sources and handlers. Then run:
`git grep -nE 'getCarApiBearerToken|getCarApiBaseURL|carApiBearerToken\b|\.baseURL|(self|api|carapi)\.verifyCert' -- lib tests | grep -v TeslaTokenSlot.py | grep -v '"carApiBearerToken"'`. Expected: no output.

- [ ] **Step 4: Add the deploy-level regression class**

```python
class TestDeployRegression20261011:
    @pytest.mark.parametrize("slots", ["fleet_command", "owner_read_only"])
    def test_departing_car_inside_radius_gets_nothing_on_any_channel(self, slots):
        # same sequence as test_2026_10_11_..., with api.storeToken(fleet_token()) or an Owner-only slot
        assert ble_commands("charging-set-limit") == [] and fleet_posts("set_charge_limit") == []
    def test_fleet_fallback_restore_needs_a_command_slot(self):  # Owner slot only -> hasRemoteChannel False -> no restore queued
```

- [ ] **Step 5: Gate and commit**

Run: `<PY> -m pytest tests/unit -q` → all passed.
Run `black` on the conflicted and ported lib files only.
Run the token-in-log check from Task 10 over `git diff presence/4-fleet-rate-queue -- lib`.
Commit subject: `Port the plug-presence code to the Tesla API token slots`.
Write `.superpowers/deploy-presence-3-merge-report.md`: conflicts, port sites, test count, and the same "things to watch on the box" section.

---

## Decisions this plan makes (the spec left them open)

- **States:** `HOME`, `PRESUMED` (no entry, or no evidence), `DEPARTING` (after unplug evidence) and `NOT_HOME` (discovery found it unplugged or away). `isHome` is HOME or PRESUMED; `isPluggedHome` is HOME only.
- **Plug evidence:** kept in memory per VIN (`PlugRecord`). It isn't persisted, so a restart falls back to presumption.
- **Evidence strength:**
  - TWC and BLE evidence is strong. A strong record younger than `STRONG_EVIDENCE_HOLD` (300 s) beats conflicting weak evidence, and a TWC naming the car right now beats a weak unplug.
  - The one exception is carried from branch 4: a TWC unplug is ignored while live TeslaMate says the car is plugged in.
  - "Here" means inside the radius, or BLE reachable within 300 s, or named by a TWC.
  - Weak plugged evidence is always recorded. It takes effect once the "here" evidence arrives, in whatever order the two come.
  - A car that becomes HOME on weak evidence gets one probe, so that `bleSilent` is meaningful.
- **Edge versus read:**
  - An unplug edge (a TWC unplug or a telemetry change) moves a presumed car to DEPARTING, with a restore.
  - A read showing unplugged moves a presumed car to NOT_HOME and sends nothing.
  - Any unplug evidence moves a HOME car to DEPARTING.
- **`presenceSources`:** dropped (with a warning if set). It was never released, and evidence strength is fixed, so an order means nothing.
- **Probes:** `nominate` is a sleep-safe discovery: a BLE body-controller probe, a charge read only if the car is awake, live telemetry, and the API only for a car that's online. It runs once at startup, on a VIN-less plug or unplug, for DEPARTING cars, and from the HTTP checkArrival endpoint. The location-era TWC nominations are removed.
- **Attribution:**
  - `PresenceAttribution.pickPluggedCar` compares the pilot against the TWC's `reportedAmpsMax`, within ±1 A, and requires `ACSingleWireCAN`.
  - A BLE-reachable candidate beats a BLE-silent one.
  - An ambiguous plug makes no car HOME and logs one INFO per plug session.
  - An ambiguous VIN-less unplug is settled by BLE charge reads. If no read settles it, no car departs.
- **TWCSlave:** a plug is reported after any held 00 (even one that wasn't reported as an unplug), so an empty TWC's first plug-in counts.
- **DEPARTING timing:** a BLE-only probe every 60 s, slowing to every 600 s after 30 min, only while a BLE restore is pending. The remote fallback goes after BLE has been unreachable for 300 s (N = 5).
- **Handlers:** the signatures don't change. `onDeparting` picks BLE (`localOnly`) or remote (`remoteOnly`) through `bleApplies`. The HOME handler first cancels any pending restore for the VIN. A PRESUMED → HOME transition runs no handler, because the policy-wide apply already covers that car.
- **Synchronous gate:** `VehiclePresence.discover(...)` is the read-before-act check in TeslaBLE and TeslaAPI. Restores are never gated.
- **Counts:** `numCarsAtHome` and `minBatteryLevelAtHome` count HOME and PRESUMED cars.
- **Fleet EVSE:** only for a car that is HOME, never one that is presumed. On branch 4, a BLE-silent HOME car is exempt from #694's VIN-less exclusions.
- **Branches:** `presence/4-fleet-rate-queue` (the rebased branch 5) and `deploy/presence-3`. The old `presence/3-presence-tracker`, `presence/4-arrive-depart`, `presence/5-fleet-rate-queue` and `deploy/presence-2` are kept.

## Follow-ups (not in this plan)

- **HomeAssistant departure restore:** HA can't act on the `-1` restore sentinel. User's direction (2026-10-11): once 1.4.0's combined fallback (IntegrationOrder) exists, one piece of code reads the stored outside limit and sends that explicit value through whichever channel the order picks, instead of each module interpreting `-1`. Until then, HA installs get no departure restore (documented limitation).
- Several cars on VIN-less TWCs: the offset-current fingerprint.
