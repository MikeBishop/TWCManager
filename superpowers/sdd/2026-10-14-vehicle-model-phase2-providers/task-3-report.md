# Task 3 report: Gen2 TWC provider

**Status: DONE**

Commits on `vehicle-model/phase2` (parent 02ed0d7):
- `8e86068`: Gen2 provider, endpoint properties, TWCMaster wiring, `minAmpsToOffer()` refactor.
- `33dc48a`: applies the user ruling on the mode-3 floor.

## History

The first pass returned NEEDS_CONTEXT. In `send_master_heartbeat`, the mode-2/3 handoff is an `elif` under `if desiredAmpsOffered < minAmpsToOffer:`. Changing the literal `< 6` to the minimum would have made the handoff unreachable.

The user chose Option 1, the least code; Phase 3's layered actuators replace this either way:
- The TWCSlave handoff stays exactly as today, with the literal `< 6`.
- Under mode 3, the provider floor is `max(6, slave.minAmpsToOffer())`, so the provider covers exactly what TWCSlave carries itself.
- No TWCSlave handoff test and no CHANGELOG line.
- `minAmpsToOffer()` falls back to a default when `minAmpsPerTWC` is unset.

## What was built

- `TWCSlave.minAmpsToOffer()` returns `max(configConfig.get("minAmpsPerTWC", 6), minAmpsTWCSupports)`, and the heartbeat's local `minAmpsToOffer` calls it. The heartbeat's mode-3 handoff is unchanged (`< 6`).
- `EVSEInstance` defaults: `vehicleKey` None, `occupied` None, `provider = ""`, `idleMinimum = False`.
- `Gen2TWC`:
  - `PLUGGED_STATES`, `twcid`, `provider = "Gen2TWC"`, `idleMinimum = True`.
  - `minAmps` and `maxOfferAmps`, each with a `controller.Gen2TWCs.ranges.<twcid>` override that applies only when it is a positive number.
  - `minPower` and `maxPower` use these.
  - `vehicleKey`: currentVIN, else the anon key, else lastVIN while in a plugged state, else None. `occupied` follows the brief.
- `Gen2TWCProvider` follows the brief:
  - `ampsRange` is `(minAmps, maxOfferAmps)`, or `(max(6, minAmpsToOffer()), maxOfferAmps)` under mode 3.
  - `setAmps` publishes through `setTargetPower`.
  - `stopCharging`: mode 2 calls `stopRespondingToSlaves()`, mode 3 calls `sendStopCommand(slave.TWCID)`, otherwise it returns False. Nothing calls it yet.
- `TWCMaster`:
  - `providerOrder` is created after `vehicleRegistry`, the Gen2 provider is registered, and `useReadOrder(orderReadSources)` is set.
  - `stopRespondingToSlaves()` sets the two settings under `settingsLock`, and `stopCarsCharging` mode 2 calls it.

### The minAmpsPerTWC default

No single default exists in the code:
- `TWCManager.py:161` (the minimal config when no config file is found under pytest) and `docs/config_examples.md` use 6.
- The shipped `etc/twcmanager/config.json` sets 12, and the startup warning at `TWCManager.py:575` falls back to 12.
- `HTTPControl.py:265` falls back to 5.

I used 6, from the default config dict at :161. The fallback never applies to a running daemon: `TWCManager.py:568` indexes the key at startup, so it always exists by then.

## Tests

`tests/unit/test_gen2twc_provider.py` has 13 tests:
- The brief's tests, with `minAmpsPerTWC: 6` added to CONFIG. The brief's mode-3 line is replaced by the cases below.
- Mode-3 floor, parametrized over protocol 2 (6/6), protocol 1 with minAmpsPerTWC 5 (5/5), 3-phase (6/1) and 3-phase with minAmpsPerTWC 1 (1/1). In every case the mode-3 range is `(6, 32)`: 6 A is covered and 5 A is not. Mode 1 keeps the plain `(minAmpsTWCSupports, 32)`.
- `minAmpsToOffer()`, including the fallback to 6 when the key is missing.
- The never-None invariant (ampsRange is not None whenever ready(SET_AMPS) is True), checked under modes 1 and 3 for VIN and anon keys.

Fail-before results:
- 8e86068: `ModuleNotFoundError: No module named 'TWCManager.Vehicle.Providers.Gen2TWCProvider'`.
- 33dc48a: the mode-3 cases failed with `assert (5, 32) == (6, 32)` and `assert (1, 32) == (6, 32)`, and the fallback case failed with `KeyError: 'minAmpsPerTWC'`.

Full capped suite: 1189 passed, 1 xfailed. Baseline was 1176; this task adds 13.

## Concerns (noted, no change needed per ruling)

1. The heartbeat never reads the `minAmps` config override (`controller.Gen2TWCs.ranges`). Under mode 1, the floor the provider advertises can differ from what the TWC enforces through `minAmpsToOffer`. The distributor owns that.
2. The never-None invariant holds per call only. `vehicleKey` can change on the serial thread between `ready()` and `ampsRange()`.
3. `registerProviders` is not yet called from TWCManager.py. That is outside this task's scope.
