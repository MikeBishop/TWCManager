# Task 15 review (cfb39fd..f1d11a2)

### Spec Compliance

**Compliant.** Every Interfaces item in the brief is implemented as specified:
- `Policy.py:273` and `TWCSlave.py:587` both loop over `vehicleRegistry.attached("TeslaAPI")`.
- `TWCSlave.getLastVehicle` (`TWCSlave.py:1238-1246`) checks currentVIN first, then lastVIN, using `reg.get()` and then `.attachment("TeslaAPI")`. It does not call `getOrCreate` or `read()`.
- `WebIPCControl.py:347-348` uses `summaries()`. That is equivalent to the carry-over's "`registry.get(VIN).summary()`, None-guarded": no None case can occur, and nothing goes through `vehicle.vehicle`.
- In `HTTPControl.py:209`, the `vehicles` global is now `lambda: master.vehicleRegistry.vehicles()`, so building the handler no longer touches TeslaAPI.
- `/api/sendTeslaAPICommand` (`HTTPControl.py:777-799`) reads `vehicleVIN` and returns 400 when TeslaAPI is absent.
- `debug.js:42` posts `vehicleVIN`.
- `debug.html.j2:74-75` skips anonymous vehicles, uses the VIN as the option value, and labels each option `name or key`.
- `settings.html.j2:256,268` lists only vehicles that have a location. It keeps the `lon,lat` order that `process_home_location` (`HTTPControl.py:1633`) splits.
- `CHANGELOG.md:26` notes the VIN-keyed debug API.
- Acceptance grep: `git grep -l getCarApiVehicles -- lib/TWCManager` returns exactly TeslaAPIController, HomeAssistant and TeslaAPI.

### Strengths
- **Same vehicle set for Policy and TWCSlave.** `attached("TeslaAPI")` returns the registry vehicles that carry a TeslaAPI attachment. Only `CarApiVehicle._bind` attaches one (`TeslaAPI.py:2086-2087`), and only for cloud-listed cars. Anonymous, BLE-only, TeslaMate-only and TWC-observed vehicles are never included.
  - Listed cars cannot drop out of the set. Their TeslaAPI claim is `keepsAlive=True`, so `expire()` skips them (`VehicleRegistry.py:141`). No code calls `registry.forget()` or drops the TeslaAPI claim. `carApiVehicles` is append-only. So the set stays equal to `carApiVehicles`.
  - `numCarsAtHome` and `minBatteryLevelAtHome` (`TeslaAPI.py:2002,2009`) still iterate `carApiVehicles` and are untouched, so the charging decisions they feed are unchanged.
- **Gen2 crash paths fixed as a side effect.** The old code called `getModuleByName("TeslaAPI").getCarApiVehicles()` without a guard in Policy (on every policy change), in the TWCSlave heartbeat (when amps ≥ 1), in `getLastVehicle` and when building the HTTP handler. Each one raised AttributeError on a pure-Gen2 install. All of them are now safe, so this moves toward the "pure Gen2 keeps working" constraint.
- **Serial thread does no I/O.**
  - The heartbeat path (`TWCSlave.py:587`, and `getLastVehicle` at `:666`) only takes the registry lock, then each vehicle's leaf lock, never both at once. No `read()` and no module calls.
  - The templates use only `.vin`, `.key`, `.name` and `.value()`, which read stored fields (`Vehicle.py:128-130,195-198`).
- **The settings page is better than before.** The old loop rendered the `RegistryField` default (10000) for cars with no fix. The new filter drops them.
- **Tests exercise real behaviour.** The template tests render the real theme loops against a real registry that contains named, unnamed and anonymous vehicles, with no TeslaAPI module. The 400 path is covered.
- **Focused run:** `test_registry_callers.py` plus `test_policy.py` give 79 passed.

### Issues

**Critical:** none.

**Important:** none.

**Minor:**
0. `settings.html.j2:268` and `HTTPControl.py:1633`: the location filter can leave the home-location `<select>` with no options. That happens when TeslaAPI-listed cars have no fix yet; before this diff each of them rendered as `10000,10000`. It is also the normal state on a Gen2 install, whose web UI now builds where it used to fail.
   - With no options, the browser sends no `vehicle` field. `getFieldValue` returns None for a missing field (`HTTPControl.py:1594-1595`), so `.split(",")` raises AttributeError when the user clicks "Make Vehicle Location Home Location".
   - The damage is limited. `serve_forever`'s `handle_error` logs the exception and the server keeps running, so the cost is a dropped request on a button that has nothing to act on. No state changes, and the same failure already happened with an empty `carApiVehicles` list. That is why this is not rated Important.
   - The diff does make the failure reachable in more situations. It is worth a one-line fix in this task: guard `loc = (self.getFieldValue("vehicle") or "")` in `process_home_location`, or hide or disable the learn button when the list is empty.
1. `debug.html.j2:74`: the dropdown now lists every VIN-keyed registry vehicle, including BLE-only, TeslaMate-only and TWC-confirmed cars. `apiDebugInterface` resolves VINs only through `getCarApiVehicles` (`TeslaAPI.py:1285-1292`), so choosing one of the extra cars gives a silent 400. This matches the brief's literal spec, but `vehicles() if vehicle.attachment("TeslaAPI")` would offer only cars the command can reach. It is a debug page, so this is a judgement call.
2. The 400 for unknown or missing VINs (implementer's concern 3) is correct. `getVehicleByVIN` returns False for a non-string or unknown VIN, so `apiDebugInterface` returns False and the handler answers 400. It is just untested.
3. `WebIPCControl.py:293-345` (concern 1) is pre-existing. The `dumpState` block dereferences `carapi` with no guard, so it raises AttributeError with no TeslaAPI module. The new lines 347-348 come after that crash point and need no TeslaAPI, so the change does not make it worse; a guard around the carapi block would let the new registry dump work on Gen2. `WebIPCControl.py:134` (`getModuleByName("TeslaAPI").slotFor`) has the same unguarded pattern. Both are out of scope; worth a follow-up.
4. `test_registry_callers.py:14` runs `git grep` relative to the current directory. It passes only when pytest runs from the repo root, which the brief also assumed. Passing `cwd=` from `__file__` would make it robust.
5. `test_policy.py:418,515,594`: the fixtures still build a `mock_tesla_api` whose `getCarApiVehicles` stub is now gone. That is harmless leftover scaffolding.
6. `WebIPCControl.py:347-348`: the dump now prints `summary()`, which holds registry fields only. The old `vehicle.__dict__` also printed `CarApiVehicle` runtime state that lives on the object, not in the registry: `stopAskingToStartCharging`, `atHome`, `errorCount`, `lastAPIAccessTime`, `delayNextWakeAttempt`, `lastChargeRateSent`. That is the state someone runs `dumpState` for. The carry-over mandates `summary()`, so this is not a spec violation. It is for the whole-branch pass: decide whether the dump should also print `vars(a)` for each `attached("TeslaAPI")`.
7. CHANGELOG nuance: the old debug page already posted the VIN, under the name `vehicleID` (old `debug.html.j2` option value was `vehicle.VIN`), so the endpoint never actually took the numeric ID. The CHANGELOG line is still accurate about the parameter name.
8. Set-equivalence check: `VehicleRegistry.load()` is called once, from `TWCMaster.loadSettings()` at startup (`TWCMaster.py:1145`, `TWCManager.py:799`). It merges entries rather than replacing them, so a reload cannot drop attachments mid-run.
9. `Policy.py:316` (`getModuleByName("TeslaAPI").minBatteryLevelAtHome`) is still unguarded. It is pre-existing, outside this task's file list, and noted only for the whole-branch pass.

### Assessment

**Task quality:** Approved

**Reasoning:** Each caller keeps exactly the cloud-listed vehicle set it had before. TeslaAPI attachments come only from listings, and the keep-alive claim, the absence of any forget path and the append-only list keep that set stable. The only caller whose set grows is the debug-page dropdown, which is UI-only and follows the spec. The serial-thread paths do dict lookups under leaf locks only, never `read()` or I/O. The templates and handler construction no longer need TeslaAPI, and the tests render them without it. All carry-overs are met. The remaining items are a debug-page UX choice, untested edges, and pre-existing unguarded TeslaAPI dereferences that this change does not worsen.
