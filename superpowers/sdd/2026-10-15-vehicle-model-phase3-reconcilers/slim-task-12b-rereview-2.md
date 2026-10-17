# Slim Task 12b re-review 2 (889e510..464d83c)

Read-only; wt-vm3 clean after every revert and mutation. test_amps_reconciler.py and test_provider_outcomes_cloud.py: 59 passed.

**N1: fixed.** Reverting TWCSlave.py to 889e510 fails test_an_anonymous_twc_rates_only_plugged_in_cars_else_vehicles_0.
Real chargingState values checked against each source:
- TeslaAPI: Tesla's charging_state is Disconnected, Stopped, Complete, Charging, Starting or NoPower. The default "Unknown" is excluded.
- Telemetry: `a[19:]` of DetailedChargeState<X> gives the same set, plus Unknown.
- BLE: the protobuf enum key is the same set, so no plugged state is excluded.
- TeslaMate: `str()` of the MQTT charging_state, which uses the same capitalised names. "None" is excluded.
- HA: only "Charging" or "Stopped"; HA "Stopped" is excluded on purpose.
- Gap, not a regression: an HA-only car that is plugged in but not charging is not counted. It falls back to vehicles[0].

**N2: fixed.** With `refreshSlot` called in the RequestException branch (TeslaAPI.py:1300), both parametrised cases fail.

New issues: none.

APPROVED
