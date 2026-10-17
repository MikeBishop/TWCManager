# Task 3 review: Gen2 TWC provider (02ed0d7..33dc48a)

Checkout: scratchpad/wt-vm2 at 33dc48a. Focused tests (test_gen2twc_provider, test_twcmaster, test_twcslave): 114 passed. `black --check` on the lib paths: clean.

## Verdicts

- **Spec compliance: PASS.** Every Interfaces name in the brief exists with the specified semantics. The amendments from the Option 1 ruling are applied: the heartbeat keeps the literal `< 6`, `minAmpsToOffer()` is a pure refactor, the mode-3 floor is `max(6, slave.minAmpsToOffer())`, and there is no CHANGELOG line. The brief's mode-3 test line was replaced by parametrized cases, which the ruling requires. The extras (`chargeRateControl()`, `_slaveForKey`) are harmless.
- **Task quality: PASS (Minor findings only).**

## Checks requested

- **Pure refactor of TWCSlave (TWCSlave.py:114-118, :756): confirmed.** `configConfig` is the same dict object as `config["config"]` (TWCSlave.py:75). `max(minAmpsPerTWC, minAmpsTWCSupports)` matches the old if/assign, ties included. The only difference is that a missing key now gives 6 where it used to raise KeyError. A running daemon cannot reach that case, because TWCManager.py:568 indexes the key at startup. The heartbeat's control flow and the mode-3 `elif` (:870) are byte-identical.
- **Mode-3 floor matches what the TWC carries.** In the heartbeat, the handoff fires only for `minAmpsToOffer <= T < 6`. For `T < minAmpsToOffer` the TWC offers 0 or `minAmpsTWCSupports` and does not hand off. For `T >= max(6, minAmpsToOffer)` the TWC carries the rate. So `max(6, minAmpsToOffer())` is exactly the floor at which the TWC carries the target, including the shipped `minAmpsPerTWC: 12` case.
- **Mode 1 and the `minAmps` override (report concern 1).** In mode 1 the TWC carries T only when `T >= minAmpsToOffer()`. Otherwise it offers 0 or the plug-detect minimum, and it never reads `controller.Gen2TWCs.ranges`. The provider's floor is `slave.minAmps`, which is the override or `minAmpsTWCSupports`. With the shipped config, the provider claims 6-11 A, which the TWC will not deliver, and `candidates()`'s localPath drops Fleet.
  - **Is Fleet wrongly dropped? No.** Mode 1 means "TWC exclusively", and today's heartbeat never calls the API in mode 1, so leaving Fleet out matches the setting.
  - **The actual defect.** `ampsRange` overstates what the TWC carries. When an override `minAmps` is above `minAmpsToOffer()`, it also understates it, which lets Fleet in for targets the TWC does carry.
  - **Phase 2 exposure: none.** `dispatch` skips module-None providers, the only SET_AMPS dispatch is `debugCommand`, and the distributor uses `minPower`, not `ampsRange`.
  - See M1 for the one-line fix.
- **ampsRange never None while ready(SET_AMPS): holds per call.** Both conditions depend on `slaveFor(vehicle) is not None`, and `ready()` evaluates `chargeRateControl()` first, so a bad setting fails `ready()` before `ampsRange()` can raise. The race across calls is M3.
- **stopRespondingToSlaves under settingsLock (TWCMaster.py:2096-2100): clean.** The lock covers two dict writes and `time.time()`, with no I/O and no nested lock. The serial thread already takes the lock (TWCSlave.py:574 → stopCarsCharging). The change also fixes a mode-2 write that used to run without the lock.
- **providerOrder on a pure-Gen2 install: no regression.**
  - `ProviderOrder` and `Suppressions` are built before `self.settings` exists. They read settings through `getattr(..., None)`, and the test constructor exercises that path.
  - `readSources()` calls the order function outside the registry lock (VehicleRegistry.py:260-265). Sources with no registered provider sort as `(9, 999, order, index)`, which is the same as the old `(order, index)` sort.
  - The distributor returns early when there are no non-Gen2 controllers.
  - Nothing new runs on the serial thread.

## Critical

None.

## Important

None.

## Minor

- **M1. The provider's range floor is not what the heartbeat enforces** (Gen2TWCProvider.py:78-79). The details are under "Mode 1 and the `minAmps` override" above. Fix: compute `floor = max(slave.minAmps, slave.minAmpsToOffer())`, return `(floor, max)` in mode 1 and `(max(6, floor), max)` in mode 3. This is one line and applies the user's own mode-3 principle ("provider floor = what TWCSlave carries") to mode 1. It departs from the brief's literal `(slave.minAmps, …)`, so the user can take it now or leave it to Phase 3.
- **M2. The `maxOfferAmps` override is not clamped to wiring** (Gen2TWC.py:164-170). With `ranges.<id>.maxAmps: 80` on a TWC wired for 32 A, the provider claims to cover 33-80 A, and the distributor's `maxPower` over-allocates. The heartbeat still clamps at TWCSlave.py:1180-1184, so this is not a safety problem. Fix: return `min(override, self.wiringMaxAmps)`.
- **M3. ready() and ampsRange() can disagree across calls** (Order.py:97-104, report concern 2). `vehicleKey` can change on the serial thread between the two calls. When `ready()` is True and `ampsRange()` then returns None, Gen2 is kept as a candidate, localPath becomes False, and Fleet is billed. Fix: in `candidates()`, read `ampsRange` once per provider and drop any provider whose range is None when `amps` is given. That is Task 2 code, so defer it to the final wave with Task 2's other minors.
- **M4. Mode-2 `stopCharging` ignores `vin`** (Gen2TWCProvider.py:89-95). It silences every TWC and returns True even for a car that no Gen2 serves. `ready()` guards the reconciler path, but mode 3 checks the slave. Fix: check `_slaveForKey(vin) is None` → False before branching on the mode.
- **M5. VIN case in `_slaveForKey`** (Gen2TWCProvider.py:46-50). `vehicleKey` is uppercased and the registry normalises with `.upper()` (VehicleRegistry.py:70/78), but `setAmps` and `stopCharging` match the raw `vin` exactly, so a lowercase VIN finds no slave. Phase 2 never reaches this. Fix: compare against `key.upper()` for non-anon keys, or have callers pass `vehicle.key`.
- **M6. The `minAmpsPerTWC` fallback is inconsistent across the codebase** (TWCSlave.py:118 uses 6, config.json:73 ships 12, TWCManager.py:575 falls back to 12, HTTPControl.py:265 falls back to 5). It is cosmetic, because a running daemon never takes the fallback. No change needed.
- **M7. `controller.Gen2TWCs.ranges.<TWCID>` is undocumented.** It also requires uppercase hex keys. The brief does not ask for docs and the ruling excludes a CHANGELOG line. Record it as a deferred docs item.
