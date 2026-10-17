# Final whole-branch review: vehicle-model Phase 2 (providers and charging points)

Range reviewed: 8e07669..b72c79c (25 commits, 11 tasks) on `vehicle-model/phase2`.
Method: read the spec, plan constraints/decisions and ledger; read every new
module in full and the diff of every modified module; compared the façade and
distributor against the 8e07669 originals (`VehiclePriority`, `TeslaAPIEVSE`,
`TeslaAPIController`, `MergedEVSE`); re-used the probe-t9/probe-t11 findings;
ran four new real-object probes (`scratchpad/final2-scratch/test_probe_final.py`)
through `TWCMaster.distributeEVSEPower` and the real `TWCSlave` heartbeat path;
ran the 14 focused test files (231 passed). The full suite was not run here.

## Strengths

- The cost model is sound end to end. Every path that can reach Fleet was
  traced: façade walk (`VehiclePriority.modulesFor`), queued `setAmps`
  (`VehicleEndpoint.setTargetPower` → worker → `ProviderOrder.dispatch`),
  `VehicleEndpoint.isReadOnly`, the debug API (`ProviderOrder.debugCommand`),
  the read cascade (`orderReadSources` + per-slot `TeslaAPIReadSource.canRead`)
  and the Wall Connector reader (free endpoints only, rate-limited, latched off
  on refusal). For pure Gen2, BLE-only, Owner-only, Fleet-only, BLE+Fleet,
  Owner+Fleet, TeslaMate and Gen3 installs I found no new paid call and no
  higher frequency than 8e07669, other than the ruled ones (the façade's
  `setChargeRate` raise over Fleet, the cloud-VIN polls which are free). The
  one exception is Critical C1 below (Fleet+HA installs).
- The serial thread does no vehicle I/O and no HTTP: `distributeEVSEPower`,
  `chargingPoints()`, every endpoint/point property, `candidates()` and the
  providers' `ready()`/`ampsRange()` read registry values, claims, cached vitals
  and settings only; Gen3 vitals and the energy-site reads run on the
  background thread via a deduplicated `gen3Vitals` task; vehicle amps are
  queued to the worker. Lock order holds (`_bleLock` → `settingsLock` →
  registry → vehicle leaf; `Gen3TWCs._targetLock` → `_lock`, same order from
  the serial and background threads). Every poll is bounded (vitals 5/10 s,
  version 600 s backoff with 404 final, Wall Connector 60 s slowing to 600 s,
  products hourly).
- Wiring safety is layered: the distributor budgets per point and per
  controller, a point never holds two local members (stale `lastVIN` fix), and
  `TWCSlave.set_last_amps_offered` still clamps the wire offer to
  `wiringMaxAmpsPerTWC` and `wiringMaxAmpsAllTWCs`. My probe confirms the slave
  guard catches the idle-minimum spike (20+20 A charging, idle TWC spiked to 16
  A by the 6 A-limit workaround, clamped to 6 A on a 40 A feed). The Gen3
  water-fill keeps the sum of draws at the sum of targets and documents the
  one case it cannot (a zero-target unit beside a charging sibling).
- Behaviour preservation per `commandPolicy` and `chargeRateControl` is good:
  mode 2/3 still go through `TWCSlave._queueChargeRate` → façade
  `setChargeRate` (BLE first, Fleet second, both tried); `api_only` keeps BLE
  out of reads and commands; `ble_only` suppresses Fleet and HA commands only;
  Owner-only never commands (`FleetAPIProvider.available`). Attempt counts
  match the old priority table (local 3, cloud 2, HA 1).
- Security: no token appears in any new log line, repr, summary or page; the
  energy-site helpers log status codes and exception type names only.
- Back-compat: `commandPolicy`, `chargeRateControl`, `chargeStopMode` keep
  their values; `providerSuppressions`, `controller.Gen2TWCs.ranges` and the
  Gen3 `din` key are optional; the registry persists no claims, so the
  `TeslaAPI` → `OwnerAPI`/`FleetAPI` claim rename needs no migration.
- The documentation (Settings.md, Controller_Gen3TWCs.md) is accurate about
  what it covers and candid about what is unverified on hardware.

## Critical

### C1. Fleet+HA installs send a second, billed charge-limit command through Home Assistant after every successful Fleet apply

- Where: `lib/TWCManager/Vehicle/VehiclePriority.py:257-282` (the walk treats
  anything but a truthy non-"error" return as failure and moves to the next
  provider), `lib/TWCManager/Vehicle/TeslaAPI.py:1065-1234`
  (`applyChargeLimit` returns `"error"` on its guard paths and **`None`** on
  success: there is no success return anywhere in the method),
  `lib/TWCManager/Vehicle/Providers/HomeAssistantProvider.py:29-31` (HA is now
  in the order, rank 6, tier billed).
- Scenario: Fleet token plus Home Assistant enabled, `commandPolicy`
  `prefer_ble` or `api_only`. The car arrives; `checkArrival` calls
  `vehicleModule.applyChargeLimit(limit=80, checkArrival=True)`
  (`TWCManager.py:333`). The façade walks TeslaAPI (Fleet `set_charge_limit`,
  $0.001, succeeds, returns `None`), reads `None` as failure, logs "failed
  after 2 attempts, trying next provider", and calls
  `HomeAssistant.applyChargeLimit(limit=80)`. HA's cached `charge_limit` is up
  to 30 s stale, so it calls `number.set_value` on its Tesla integration, which
  is commonly the user's own Fleet app: a second billed command per car per
  arrival and per policy transition. The same happens for a targeted
  `applyChargeLimit(limit, vin=...)` for a car HA holds. On the restore (`-1`)
  HA logs "Leaving existing limit unchanged" and sends nothing, so the restore
  itself is not duplicated.
- Why the per-task reviews missed it: the Task 9 probe harness and
  `tests/unit/test_vehicle_priority.py:50-65,187-200` mock
  `TeslaAPI.applyChargeLimit` to return `"success"`, which the real method
  never does. At 8e07669 the same `None` fell off the end of the walk harmlessly
  because nothing ranked after TeslaAPI; HA joining the order (Task 8/9) turned
  it into a paid fall-through. This violates the ruling that HA is "reached
  only after the free providers and Fleet have failed".
- Fix: make `TeslaAPI.applyChargeLimit` return `"success"` at the end of its
  success path (it already uses the `"error"` convention), and add a façade
  test with a module whose `applyChargeLimit` returns `None` asserting the walk
  continues, plus one with a real `TeslaAPI.applyChargeLimit` stub returning
  `"success"` asserting HA is not called. Also audit the other façade-walked
  reads: `TeslaAPI.updateChargeAtHome` (`TeslaAPI.py:2057-2061`) returns
  `None` too, so `HomeAssistant.updateChargeAtHome` now runs after every
  `checkCharge` (HA-local, free; harmless but new).

## Important

### I1. The idle-TWC minimum is zeroed on the wire when `minAmpsPerTWC` exceeds the TWC's own minimum, so plug detection is still not restored for the shipped default config

- Where: `lib/TWCManager/TWCMaster.py:613-625` (idle point gets
  `point.minPower`), `lib/TWCManager/EVSEInstance/Gen2TWC.py:159-161`
  (`minAmps` = `minAmpsTWCSupports`, 6 A, or the range override),
  `lib/TWCManager/TWCSlave.py:753-863` (`desiredAmpsOffered < minAmpsToOffer`
  with no car charging → 0).
- Scenario: `etc/twcmanager/config.json` ships `"minAmpsPerTWC": 12`. Gen2 TWC
  plus the TeslaAPI module (loaded by default, configured or not, so
  `VehicleEndpoints` is registered and the distributor runs). No car is
  charging. The distributor offers the idle TWC 6 A (probe: target 6.0), the
  heartbeat path computes `minAmpsToOffer() = 12`, takes the "no cars charging"
  branch and sends 0 A (probe: `lastAmpsOffered 0.0`, master heartbeat
  `05 0000`). With `minAmpsPerTWC` 6 the same probe sends 16 A (spike) then
  6 A. A TWC whose firmware honours 0 A then reports `04 00 00` for a newly
  plugged car, `Gen2TWC.wantsToCharge` stays False and the point never leaves
  idle. Newer TWC firmware ignores 0 A (README: "not effective for newer TWC
  chargers"), which is why the user's box has not shown this; old-firmware
  installs with the default config are stuck exactly as at 8e07669 and main.
- This is not a regression against 8e07669 (which offered 0 outright), but
  Decision 18 and the spec's "Idle TWCs keep their minimum ... must be kept"
  are only half delivered, and the deferred Task 3 minor ("range floor =
  max(slave.minAmps, minAmpsToOffer())") is the same bug seen from the
  provider side.
- Fix: make the idle offer the TWC's real floor: `Gen2TWC.minAmps` =
  `max(minAmpsTWCSupports, config minAmpsPerTWC)` honouring the range override
  (equivalently `TWCSlave.minAmpsToOffer()`), so `point.minPower` is what the
  heartbeat will actually send; add a real-object test with
  `minAmpsPerTWC` 12 that drives `receive_slave_heartbeat` +
  `send_master_heartbeat` and asserts a non-zero offer. Keep the Gen2 provider
  range floor consistent (mode 3: `max(6, minAmpsToOffer())` already).

## Minor

### M1. A merged TWC point wants power whenever the registry's `chargingState` says so, even when the TWC reports no car demand

- `lib/TWCManager/EVSEInstance/ChargingPoint.py:66-68` (`any`),
  `lib/TWCManager/EVSEInstance/VehicleEndpoint.py:263-266`.
- Scenario (probe): two TWCs, car A finished (TWC reports max 0, actual 0) but
  the registry still says "Charging" (stale until the next `vehicle_data` or
  telemetry update); car B charging. Offers are 20/20 instead of 6/32 until the
  registry refreshes. At 8e07669 a TWC-served car was excluded from the
  endpoint list, so the TWC alone decided. On firmware that echoes the offer
  the TWC already "wants" while plugged, so the window is small; on
  old-firmware TWCs it is the stale-read window.
- Fix (optional, Phase 3 territory): let a local member's `wantsToCharge`
  decide when one is present (`localEndpoints or endpoints`, as `currentAmps`
  already does).

### M2. Documentation and CHANGELOG gaps

- CHANGELOG has no line for: the Gen3 provider, shared headroom, the free
  cloud VIN lookup and the `din` device key; the `controller.Gen2TWCs.ranges`
  override (deferred minor, still undocumented anywhere); the settings-page
  relabels; HA as a billed-tier amps writer (Task 10 m2 asked for it).
- `docs/Settings.md` does not state the default rule that the Fleet API never
  sets amps when a local path (TWC or BLE) covers the rate. This is a visible
  behaviour change: a BLE-claimed car on no TWC (UMC) now gets its distributor
  rate over BLE only and no longer falls back to Fleet
  (`Order.py:107-114`, `VehicleEndpoint._candidates`). Spec-conformant, but
  users of the old `TeslaAPIEVSE` path should be told.
- CHANGELOG m5 ("an idle Gen2 TWC keeps its minimum") and m6 (the Bugfixes
  entry describes a bug that never shipped in a tag; fold into the
  Architecture line).

### M3. Dead or half-wired declarations

- `ProviderOrder.orderKey` (`Order.py:55-59`) has no caller.
- `Provider.readSource` (`Provider.py:17-18`) is set by the BLE, Owner, Fleet
  and HA providers but nothing reads it; `orderReadSources` keys on
  `ReadSource.provider` instead. Drop one or the other.
- `ChargingPoint.startCharging`/`stopCharging` (`ChargingPoint.py:152-163`)
  and `EVSEInstance.provider` / `Gen2TWC.provider` / `Gen3TWC.provider`
  (`EVSEInstance.py:111-112`) have no caller. `limitations()` /
  `NO_INDIVIDUAL_STOP`, `RateLimit` on Fleet, `summary()` and the Gen2
  disruptive stop are declared-for-later by plan and are fine.

### M4. `Suppressions.explicit()` re-parses both settings dicts on every `suppressed()` call

- `Suppressions.py:79-96`; called per provider per `candidates()`, several
  times per endpoint per distributor pass on the serial thread. Cheap today;
  cache on `id(settings.get("providerSuppressions"))` if the pass ever shows
  in a stall trace.

### M5. `Gen2TWCProvider._slaveForKey` compares the raw key

- `Gen2TWCProvider.py:46-50,81-87`: `vehicleKey` is upper-cased, so
  `setAmps("5yj...")` misses. Unreachable this phase (`dispatch` skips
  module-less providers); upper-case the key when Phase 3 wires it.

## Deferred-minors verdicts (fix in the final wave: yes/no)

- Task 1, `__all__` omits capability names: **no** (star import works; cosmetic).
- Task 2, OverflowError escapes `debugCommand`: **already fixed** (9e4e8f9).
- Task 3, range floor = `max(slave.minAmps, minAmpsToOffer())`: **yes** (this is I1).
- Task 3, M3 key race `ready()`/`ampsRange()`: **no** (one candidate dropped for one pass).
- Task 3, `maxAmps` override uncapped by wiring: **no** (`set_last_amps_offered` clamps on the wire).
- Task 3, mode-2 `stopCharging` ignores VIN: **no** (no caller until Phase 3; mode 2 is bus-wide by nature).
- Task 3, `_slaveForKey` lowercase VIN: **no** (M5; fix when wired).
- Task 3, `minAmpsPerTWC` default inconsistency (6/12/5): **no** (cosmetic; `TWCManager.py:581` uses 12 where the loader uses 6).
- Task 3, document `controller.Gen2TWCs.ranges`: **yes** (M2).
- Task 4, M3 documented: **no**. M5 ready/ampsRange race: **no**. M6 dedup by VIN: **done** in Task 11.
- Task 5, `ampsRange` inverted if `availableCurrent` in (0,1): **no** (pilot current is never fractional below 1 A).
- Task 7, M2 single-unit fallback counts VIN-bearing connectors: **no** (documented; hardware-unverified path anyway). M4 up to 10 s per request on the background thread: **no** (bounded, rate-limited). M5 hourly Owner/Fleet flap: **no** (free).
- Task 8, M-3 notice test: **no**. M-4 black on tests: **no**.
- Task 9, m-2 HA 10 s rate limit shared across cars: **no** (delayed, not lost). M5 debug dropdown BLE-only wake: **no** (Phase 6).
- Task 10, BLE-only endpoint positive test: **yes** (it is now the only amps path for a BLE-claimed car off a TWC; cheap). HA billed-tier amps writer: **no code**, CHANGELOG line (M2). `setAmps` dropped if VehiclePriority disabled: **no** (undocumented key, on by default). Lost controller-test coverage: **yes** (carried twice; five small tests). Blind pass resets last-sent: **no**. Gen3 occupied key None not blind: **done** (`VehicleEndpoints.py:430`).
- Task 11, m1 lost coverage: **yes** (same as above). m2 0 W goes out as `minAmpsTWCSupports` while another Gen2 charges: **no** (pre-existing TWCSlave rule; Phase 4). m5/m6 CHANGELOG wording: **yes** (M2).
- Task 6 m2, two claims shown per Tesla: **no** (Decision 15; the tab is meant to show which slot does what).
- Phase 5 carries (mode-2 `lastVIN` rate to a departed car; Gen2-00 sleeping-car paid path): **no**.

## Declined to judge

- `Gen2TWC.wantsToCharge` semantics (`reportedAmpsMax > 0`, i.e. whether a
  slave echoes the master's offer while unplugged, and whether old firmware
  really holds `04 00 00` under a 0 A offer): pre-existing from 6f075db, not
  changed by this branch, and only verifiable on hardware. I1's severity
  depends on it.
- The `live_status.wall_connectors` shape, the `<part>--<serial>` DIN format
  and the Owner API serving `live_status` at all: unverified on hardware by
  design (G7/G10 rulings); the code fails closed.
- Gen3 shared headroom and the zero-headroom stop on real units (G6).
- Whether an HA-only install would ever set `ble_only` (which now suppresses
  every command for it): a ruled consequence of Decision 7.
- Today's immediate BLE → Fleet fall-through on a BLE failure for
  `applyChargeLimit`/`car_api_charge` (the 2026-10-11 stray command): preserved
  on purpose until Phase 3's time rules.
- Merge/deploy sequencing: Phase 1 (8e07669) is not on `main`; Docker `:latest`
  tracks `main`, so this branch lands with Phase 1 or not at all. The branch is
  not deployed mid-phase (Task 10/11 ruling); Task 11 Step 6 live check is still
  pending.
- Full-suite result (caller runs it).

## Assessment

Ready to merge: **With fixes**.

- C1 (one-line return in `TeslaAPI.applyChargeLimit` plus two façade tests)
  must land before merge: it is a new billed call on Fleet+HA installs and
  breaks the "HA only after Fleet failed" ruling.
- I1 should land in the final wave: it is the deferred Task 3 range-floor
  minor, and without it the spec's idle-minimum rule does nothing for the
  shipped default `minAmpsPerTWC` 12 on TWCs that honour 0 A.
- M2 (docs/CHANGELOG) and the "yes" coverage items are cheap and should ride
  the same wave; M1, M3-M5 can wait for Phase 3.
