**Deploy?** Yes

### Verdicts
- Merge claim: `git diff 8da7e41..1535e71` and `git diff 8233d6b..b8b2fbd` have identical +/- line sets (sorted, md5 equal). Spot-check only, not a hunk-order or context comparison.
- Important 1, TeslaBLE: addressed. `applyChargeLimit` passes `restore=limit == -1` to `telemetryChargeLimit`. When our write is newer than the last read (or the car was never read), it returns None, and the BLE path reads live. Applies pass restore=False and keep the written value, so the 2026-10-12 scenarios still guard them (test_teslable_presence and test_teslaapi_presence pass).
- Important 1, TeslaAPI: addressed. A restore with `ownWriteIsNewer` forces `update_charge(allowBle=False, forceLive=True)` for any syncSource. Applies are untouched (`limit == -1` gate).
- Minor 3: addressed. `_readChargeState` stamps vehicle.chargeLimit and chargeLimitReadAt via `noteChargeLimitReadFor`, so a BLE read counts as the latest read.
- Widening to syncSource "TeslaAPI" is correct and does not wake the car. In that mode `update_charge` already read over BLE (stamped, so not forced) or fetched `vehicle_data` (stamped, so not forced). Forcing only happens when the status deferral returned a cached value with no fetch.
  - Cost: one `vehicle_data` call on a restore that would previously have trusted the written value. It happens only when our write is newer than the read. After the fetch, readAt is at least the write time, so it does not repeat. `vehicle_data` does not wake the car (needToWake is False for -1, unchanged).
  - If the forced read fails, `decideChargeLimit(-1, None, ...)` returns "nothing sent" and stopTryingToApplyLimit stays False. Later passes retry, each resetting statusDeferral. This is the same retry exposure the existing needsLiveRead path has.
- ble_only: no new leak. applyChargeLimit is reached only through the VehiclePriority queue, which refuses TeslaAPI under ble_only. The forced read uses `allowBle=False`, as the existing live-read branch does.
- Tests are non-vacuous. Running the new tests against 1535e71 with the three lib files reverted (`git diff 8233d6b b8b2fbd -- lib` applied in reverse in a scratch copy) gives 4 failed: BLE restore, BLE stamp, and TeslaAPI TeslaMateVehicle and TeslaAPI. Current tip: test_teslaapi_presence, test_teslable_presence and test_teslaapi_chargerate give 189 passed.

### New breakage
None found.

### Out-of-scope / notes
- TeslaBLE restore uses sendWhenUnknown=True. If the forced BLE live read fails, it restores the saved normal limit over a possible hand-set value. This is the existing design, not a regression.
- The BLE thread now writes vehicle.chargeLimit. A lagging TeslaMate push can re-stamp over the fresher BLE read (the implementer flagged this). Low impact; the window is small and the same exposure already existed in update_charge's BLE branch.
