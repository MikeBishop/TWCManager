# Task 3 review
Spec: compliant. Quality: approved (2 minor findings).

No-wake: bleSource reads charge only if probePresence says awake (missing/unparseable status counts as asleep); probePresence runs body-controller-state only; get_charge_state is `state charge` (no wake/ping). apiSource gates on vehicleOnlineStates == "online" (vehicle-list GET, no wake) before vehicle_data; offline/failed returns {}. Telemetry reads attributes only. No new log lines carry tokens.

Findings
- Minor, TeslaBLE.py blePluggedIn (~L38-47): any chargingState other than Disconnected/None is True, including "Unknown"/"SNA" or an empty `{}` enum (_enumKey returns {} for an empty dict, which is != "Disconnected"). A not-reported state then reads as plugged. Treat Unknown/SNA/{}/"" as None. The brief's wording permits the current code.
- Minor, PresenceSources.py apiSource (~L110): chargingState/fastChargerPresent are read from cached vehicle attributes. If vehicle_data returns True but charge_state was absent from the response, a stale chargingState becomes fresh evidence. Low likelihood.
- Note: the report admits no RED run for the TeslaBLE and TWCSlave changes. Tests are present and meaningful.

Verified
- _probe precedence (VehiclePresence.py _probe): reach from ble; pluggedIn ble > telemetry > api, source kept; inside telemetry > api; fastChargerPresent ble > api. None values never override. The API skip fires only when both pluggedIn and inside are already known. A BLE-asleep car with telemetry gives both, so the API is skipped; an asleep car with no telemetry falls to the API, which checks online itself. bleOnly calls only ble. Raising sources are skipped.
- _applyEvidence order is contact, plugState (edge False), location, as the brief requires. pluggedInSource is always set when pluggedIn is.
- start() nominates (None, "startup") once, after the thread-alive early return; the None key is expanded at pass time.
- Real enum fixtures ({"Engaged": {}}, {"SAE": {}}) covered by the tests; TWCSlave nominations removed and the "nominate nothing" test added.
