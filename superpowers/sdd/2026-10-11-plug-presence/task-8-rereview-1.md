### Finding Verdicts
- **I1 broadcast wakes every HOME car** - ADDRESSED. TeslaAPI.py: car_api_available gains `vins=` and its wake loop skips VINs not in it; car_api_charge passes `vins=targetVINs` for a broadcast (an empty set wakes nothing), `vin=` for a targeted command, and no filter when presence is absent or fails. Test test_broadcast_wakes_only_candidates runs the real car_api_available and asserts wakeVehicle is called for V1 only.
- **I2 no test for the re-pick after vehicle list load** - ADDRESSED. test_targets_are_picked_after_the_vehicle_list_loads starts with an empty list, loads it in the mocked car_api_available, and asserts one charge_start to V1. The report says it fails with the re-pick line removed.
- **Controller ruling: TeslaBLE.setChargeRate(vehicle=None) commands every car** - ADDRESSED. TeslaBLE.py: the vin-None path uses `_broadcastTargets()` (configured cars intersected with broadcastVINs, with the same fallbacks as the charge start) and returns False without waking anything when there are no targets. Three tests cover candidates only, no presence, and no candidate.

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
