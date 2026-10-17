### Task 4: Sweep, guard, line check and live check (expected lib Δ ≈ −5)

**Files:**
- Modify:
  - comments and docstrings Task 3's grep did not force: the `EVSEController/VehicleEndpoints.py:84–86` docstring, the `Reconcile/Targets.py` header and `TWCSlave.py:132`'s "registry order is list order". That last one was already false at BASE (`vehicles()` sorts by key); Task 3 rewrote the code beneath it, so reword it to say "registry (sorted VIN) order". `TeslaAPI.py:172`, `TeslaAPIProviders.py:139` and `Reconciler.py:64,74` are Task 3's (F18);
  - any orphan the sweep finds, deleted with its grep evidence;
  - `CHANGELOG.md:23` (not lib; F20). It says the older `chargeLimits` key is "kept but ignored, with a warning". At BASE and after, it is deleted silently when the store already holds the car (`test_both_keys_present_the_store_wins`). Correct the sentence.
- Test: `tests/unit/test_registry_callers.py::test_no_caller_outside_teslaapi_reaches_for_its_list` is extended rather than duplicated.

- [ ] **Step 1: Guard (fails if any name is reintroduced).** The test's patterns over `lib/TWCManager`, `html`, `tests/integration` and `tests/API`:

```python
["git", "grep", "-lE",
 r"carApiVehicles|getCarApiVehicles|CarApiVehicle|RegistryField|getVehicleByVIN"
 r"|lastVehicleAwake|_liveVehicle|startswith\(\"id:\"\)",
 "--", "lib/TWCManager", "html", "tests/integration", "tests/API"]
```
  Since Task 3, HomeAssistant has no `carApiVehicles` list either, so the BASE regex's `[^f]` exclusion goes.
  Add one more assertion: `git grep -n "\.forget(" -- lib/TWCManager` shows only the `ifUnattached=True` call in `forgetVehicle`.
- [ ] **Step 2: Orphan sweep.** For every `def` in the files Tasks 1–3 touched, `git grep -nw <name> -- lib html` (the templates are under lib). Delete any with no caller, unless policy reach applies (a property or data attribute on a module object). Report each with evidence. Expected: none or a handful.
- [ ] **Step 3: Full suite** → PASS. `black --check lib` passes.
- [ ] **Step 4: Line check (report; the target is a target, not something to fit).**

```bash
find lib -name '*.py' | xargs cat | wc -l                   # target ≤ 26,750; BASE 27,270
git diff --shortstat db47522 -- lib; git diff --shortstat origin/main -- lib
git diff --numstat db47522 -- lib | awk '{a+=$1; d+=$2} END {print "added", a, "removed", d; exit !(d > a)}'
```
  Expected: the awk exits 0. Record the total, the two shortstats, and each task's actual vs expected delta in the ledger and the commit message. If the total is over 26,750, report by how much and where (see "Line budget"). Do not pad deletions.
- [ ] **Step 5: Commit.** `git commit -m "Guard the dissolved CarApiVehicle names; sweep comments and orphans"`
- [ ] **Step 6: Live check on `twcmanager`.** Deploys and restarts are pre-approved. The implementer does not run it; the user schedules it. Box: Gen2 in mode 1, `commandPolicy: ble_only`, a BLE-paired Model 3, a TeslaMate token synced to the Owner slot (read-only), a Fleet slot, and the Scheduled 70 / non-scheduled 50 policies.
  1. **Prepare.**
     - Record the box HEAD (the rollback target) and run `cp /etc/twcmanager/settings.json ~/twcmanager-settings.json.bak-phase3.5`.
     - Check the settings: `jq '{c: .chargeLimits, r: .chargeRateControl}' /etc/twcmanager/settings.json`. Expect no `chargeLimits` and `chargeRateControl` 1. **Done before Task 1:** the controller confirmed that the box's `heldLimits` holds no `"id:"` keys.
     - Set `logLevel` so INFO8 reaches the journal (every TeslaAPI request then logs `Car API <METHOD> <path>: HTTP <status>`).
     - Run `git -C ~/TWCManager diff` (must be empty) and `grep -rn "request.headers" ~/TWCManager/lib` (no log line).
     - Pause the watchdog cron if it is active.
  2. **Deploy.** Bundle `<box HEAD>..vehicle-model/phase3.5`, scp it, `git fetch <bundle> HEAD && git checkout --detach FETCH_HEAD`, then `sudo systemctl restart twcmanager`. Expect a `Providers: ...` boot line, no `Main loop stalled` after boot, and at most one free `Car API get products: HTTP 200` (the Owner list).
  3. **Restart with the car plugged in and asleep** (the 2026-10-16 regression).
     - Setup: the car plugged into the Gen2, asleep, held at 50, TeslaMate showing it at home and asleep.
     - Restart, then switch to Scheduled 70 (or wait for 00:00).
     - Expect:
       - an `anon:` plug session (TWC `lastVIN` empty);
       - BLE `wake`, `charging-set-limit 70`, then the BLE amps lift (`charging-set-amps 32`), then the start;
       - **zero** `Car API` lines for `vehicles/<VIN>`, `vehicle_data`, `wake_up` or `command/`. TeslaMate's fresh "asleep" answers `is_awake` without a GET;
       - the held limit 100/70 on the car's Vehicles page.
  4. **Surfaces.**
     - `curl -s localhost:8080/api/getSlaveTWCs | jq` shows `lastAtHome`, `lastBatterySOC`, `lastChargeLimit` and `lastTimeToFullCharge` with real values (once a read or TeslaMate has them).
     - The Vehicles tab and the car page render. Debug → "Send Tesla API Command" still lists the car. The listed car's page offers no Forget.
     - The policy page shows the same active policy as before deploying (it reads `minBatteryLevelAtHome`).
  5. **00:00 / 05:00 cycle.** Expect one BLE limit write each way, the BLE stop at 05:00, and no Fleet request.
  6. **Depart and return.**
     - Unplug and drive away: the held limit is restored over BLE in range, otherwise hourly, never a `wake_up`, and no Fleet request (ble_only).
     - Return and plug in: the policy limit is desired again, and nothing is sent while the car already sits at it.
  7. **Restart again with the car away**, then return. `heldLimits` is unchanged across the restart (`jq .heldLimits`), and no `chargeLimits` reappears.
  8. **Count paid calls** for the whole window: `journalctl -u twcmanager --since "<start>" | grep "Car API" | grep -oE "wake_up|vehicle_data|command/[a-z_]+" | sort | uniq -c`. Expect 0 under ble_only with BLE up. Price anything found at $0.02 / $0.002 / $0.001 and report it.
  9. **Record and roll back** (unless the user keeps it):
     - `git -C ~/TWCManager checkout --detach <box HEAD>`;
     - `sudo cp ~/twcmanager-settings.json.bak-phase3.5 /etc/twcmanager/settings.json`;
     - revert `logLevel`;
     - `sudo systemctl restart twcmanager`;
     - re-enable the watchdog;
     - confirm the boot log and one heartbeat.

**Review focus (Task 4):**
- The guard covers every removed name.
- The CHANGELOG correction matches what `HeldLimits` does.
- The line figures are exact.
- No deletion in the sweep is a module property or data attribute a policy could reach.

---

## Line budget (lib/ only; non-test `lib/**/*.py`)

Fixed points: origin/main 23,180; BASE db47522 27,270; target 26,750.

| Task | Expected lib Δ | Running total |
|---|---|---|
| 1 held limits in one pass (+ `_snapshot` inlined) | ≈ −48 (−40..−55) | ≈ 27,222 |
| 2 sync state on the registry; external readers | ≈ −20 (−10..−30) | ≈ 27,202 |
| 3 dissolve CarApiVehicle; atomic Forget; extra savings | ≈ −130 (−115..−145) | ≈ 27,072 |
| 4 sweep and guard | ≈ −5 (0..−15) | **≈ 27,067** |

- **Projected end: ≈ 27,065** (range ≈ 27,020–27,110). That is ≈ 315 over 26,750 and ≈ 17 % above main. These are the pre-flight's realistic figures (F11).
- **Task 1:** today's log messages cost about the same lines when collected for after the lock. Only the logic shrinks: about 70 lines become about 40, plus about 3 for the inlined `_snapshot`.
- **Task 3** was itemised as follows.
  - Removed: `CarApiVehicle` after Task 2 ≈ 384, `RegistryField` 21, `addVehicle` 9, `getVehicleByVIN` 9.
  - Re-homed: the record ≈ 23, `addVehicle` ≈ 12, `onlineState` + `is_awake` ≈ 30, `_ready` ≈ 25 (kept per F6), `get_car_api` ≈ 72, `_readFresh` 21, `update_location` 12, `locate` 7, `update_vehicle_data` ≈ 81, `update_charge` 2, one `car = …` line in about 8 methods, `_listed` ≈ 4, and the Targets plumbing ≈ 2.
  - Added for F7: `getOrCreate(attach=)` and `forget(ifUnattached=)` ≈ +8.
  - Extra savings: `_anonCars`, `allEVSEs`, `say()` and the HA list together ≈ −12.
- **Why not −300 + −135 as the audit and the final review projected:**
  - The audit's −300 assumed folding the wake hold and backoff into the reconciler's attempt record and moving `atHome` to Phase 5 presence. Both change behaviour (the wake hold and 429 backoff are per car and span reads, commands and wakes; presence is Phase 5's).
  - The final review's 120–150 for held limits assumed dropping the deferral (resolve once at the first list). The user kept semantics (a), so the deferral, the multi-slot listing in `resolveHeldLimits`, `_loadedVins` and `listPending` stay. What goes is the duplicated second pass, the shadow copy, `"id:"` and `vins()`.
- The rest of the gap is structural: Reconcile ≈ 1.9k, Providers, Registry; plus the user's kept Gen3 work (≈ 530) and Phase 4's distributor/heartbeat duplication (≈ 240, spec-mandated there).

## Decisions made in this plan

1. **The per-car bookkeeping is an attached record (`CarApiState`), not registry fields and not a TeslaAPI-side dict.**
   - Registry fields would make the online cache, backoff and wake hold observations: they would show in `Vehicle.summary()` (the Vehicles tab), and `observe()` bumps `lastSeen`, a forget-window change.
   - A TeslaAPI dict keyed by VIN would be a second per-car map beside the registry, the thing the spec's Goal 1 removes, and every listing check (`attachment("TeslaAPI")` in seven places and one template) would need rewiring.
   - The record keeps all of them, and `canForgetVehicle`'s refusal, unchanged.
2. **Method names stay** (`is_awake`, `update_vehicle_data`, …) with the registry vehicle as the first argument. Renaming would add churn and no lines.
3. **Nothing on a paid path is folded.**
   - `ready()` moves whole, keeping its second online check (F6). Folding it would pay one `vehicle_data` at the 120 s cache edge.
   - `update_vehicle_data` keeps its deferral re-check: under two concurrent reads it saves a paid `vehicle_data`.
   - Only the online cache's four flags become one internal three-state. That mapping is exact on every path, and callers still see today's booleans (F3).
4. **`_scheduleBlocksStart` stays** (it is not a duplicate of `Belief.handsOff`): it re-reads after the read-before-write, at run time, while `handsOff` runs at plan time. Only its `vin=None` dead branch goes.
5. **`TeslaAPI.carApiVehicles` goes** although a policy could name it: it is an undocumented list of internal objects that no comparison operator can use. `numCarsAtHome` and `minBatteryLevelAtHome` keep their values.
6. **The dev-build `"id:"` store keys go without migration code.** No release wrote them. The only deploy branch with the writer (`deploy/phase3-live` = db47522) also carries the cleaner, and the controller checked the box: it has no `"id:"` keys.
7. **Forget is one atomic registry operation** (F7, ruling): `forget(ifUnattached=True)` re-checks "user-asserted and unattached" under the registry lock, and listing attaches under the same lock. That replaces the rejoin-after-forget path rather than keeping it. HomeAssistant's attach uses the same call, so the same race closes for HA cars.
8. **INTENTIONALLY CHANGED edges, all accepted:**
   - F10: two IDs for one VIN whose entry was loaded malformed (Task 1).
   - A Tesla list entry with no `id` no longer raises (Task 3).
   - Per-car reads and HA's discovery log lines now come in sorted-VIN order (Task 3).

## Not taken (and why)

- **`HaVehicle`'s cached `battery_level`/`lat`/`lon`** (≈ −3 net): outside this phase's scope (not final review I2, not CarApiVehicle). `at_home` must stay: HA's home rule differs from TeslaAPI's (final-fix-report item 2).
- **One "is this car home" helper** (I2 row 2): the remaining copies differ in behaviour (home seeding, GPS age, the sunrise task). This is Phase 5.
- **`chargeStopMode`/`chargeRateControl` accessors** (I2 row 6): no saving (final-fix-report).
- **Compacting verbose log formatting** in the backoff helpers: cosmetic, not deduplication.

## Self-review (against db47522)

- **Every symbol planned for deletion exists:**
  - TeslaAPI.py: `RegistryField` :39, `CarApiVehicle` :1540, `carApiVehicles` :139, `getVehicleByVIN` :779;
  - `CarApiVehicle` members: `syncTimeout` :1592, `_telemetryState` :1639, `syncSource` :1649, `ready` :1655, `_bind` :1604, `_liveVehicle` :1622, `actualCurrent` :1949/1953, `lastCurrentChangeTime` :1586, `READ_MAX_AGE` :1565;
  - `Reconciler.READ_MAX_AGE` :75;
  - HeldLimits: `_waiting` :91, `"id:"` handling :118–123/:214–215, `vins` :281.
- **Every external caller is listed** in the member table and "Other callers checked":
  - `attachment("TeslaAPI")`: VehicleEndpoints:119, EVSEInstance/Gen3TWC:281, TWCSlave:136/1300, TeslaAPIProviders:46/77/108, Targets:25/35/64/134, debug.html.j2:74;
  - car methods: TeslaAPIProviders:55/163, Targets:26/137;
  - data reads: HTTPControl:511–514, TWCMaster:679–692, Targets:66, VehicleEndpoints:87–89;
  - `syncSource`: Targets:136, VehicleEndpoints:87;
  - `getLastVehicle`: HTTPControl:509, TWCMaster:679;
  - `located`: Targets, TWCSlave:113;
  - `getVehicleByVIN`: TeslaAPIProviders:140;
  - `vehicleScheduledChargingPending`: TeslaBLE:189;
  - `resolveLegacyIds`: TeslaAPI:544, tests.
  - `registry.forget`: HTTPControl:120 only (now `ifUnattached=True`). `getOrCreate` + `attach` pairs: TeslaAPI `addVehicle`, HomeAssistant:403–405. Both now go through `getOrCreate(attach=)`.
  - HomeAssistant `carApiVehicles`: :216, :263–268, :404, :579–596 and `test_homeassistant_registry.py:213`.
  - The 8 importers of `test_carapivehicle_registry.py` are listed in Task 3.
- **Surfaces.** `lib/TWCManager/Control/themes`, `html/`, `tests/integration`, `tests/API` and `docs/` reference none of the removed names at BASE (grep run during planning). The `attachment("TeslaAPI")` template use keeps working.
- **Green after every task.** Task 2 leaves `RegistryField` in place for `CarApiVehicle`'s own methods. Task 3 removes it together with every remaining user.

## Questions for the user

1. **The projection is ≈ 27,065, about 315 over 26,750, with no behaviour change.** This uses the pre-flight's realistic deltas and keeps `ready()`'s second check (F6). Accept it, or name a lever. The only one inside this phase is dropping the held-limit deferral (≈ −35: resolve and drop at the first non-empty list), which reverses your semantics (a). The other levers are behaviour changes for Phase 4/5 or the Gen3 work you kept.
2. **Decision 1 (an attached `CarApiState` record).** Confirm, or prefer the alternatives above. Default as written.
