# Squashed vehicle-model stack — commit lists

## Phase 1 (PR 703): 50 → 19 commits

1. `b95840bd` Key vehicle commands by (cmd, vin) and add explicit cancellation
1. `f32c363f` Add a settings lock taken by off-thread writers
1. `3ecfdfcf` Add the vehicle field store
1. `14ee31fd` Add the registry Vehicle with VIN or anonymous identity, claims and tiers
1. `5867cfcf` Add read sources and a freshness-bounded read cascade that never wakes
1. `00cb287b` Add VehicleRegistry with forgetting, persistence and user-asserted vehicles
1. `5376497e` Confirm TWC-reported VINs and track anonymous plug-session vehicles
1. `2a2232d2` Persist the vehicle registry in settings.json and forget unseen vehicles hourly
1. `411f83fa` Back CarApiVehicle fields with the registry
1. `94f72377` Read vehicle state through the registry cascade without waking cars
1. `99659f01` Attach telemetry to registry vehicles by VIN or name
1. `bc5066bd` Register Home Assistant vehicles, claims and reads in the registry
1. `bb886cc3` Track BLE pairing status per VIN
1. `1d20fd4f` Stamp the registry with our own charge-limit and charge-rate writes
1. `c2881e10` Read vehicles from the registry in Policy, TWCSlave and the web UI
1. `8082eee9` List the vehicle registry on the Vehicles page and add vehicles by VIN
1. `66efc80a` Show BLE pairing status and a range scan on the vehicle page
1. `6dc1356e` Only a well-formed VIN becomes a registry vehicle
1. `45c21341` Forget a vehicle added by VIN that nothing else knows

## Phase 2 (PR 704): 41 → 17 commits

1. `270af7a3` Add vehicle providers and a fixed provider order
1. `1e26e4bd` Add the Gen2 TWC provider
1. `6fcfa342` Add the Gen3 TWC provider with one shared headroom
1. `e78b27bf` Add the TeslaBLE provider
1. `d3fa5e64` Split the Tesla API into Owner and Fleet providers
1. `293e2f5f` Identify the car on a Gen3 TWC from the energy site's live_status
1. `edcba746` Add telemetry and HomeAssistant providers; register them at startup
1. `1cf65dfc` Make VehiclePriority a facade over the provider order
1. `535acb5d` Replace TeslaAPIEVSE/TeslaAPIController with vehicle endpoints
1. `7ddd20f0` Group charging endpoints into charging points and allocate per point
1. `86489bda` End a provider walk on a Fleet success, skip or wake hold
1. `9358856b` Let TeslaBLE and TeslaAPI take a targeted charge limit
1. `b8adba7a` Offer an idle Gen2 TWC the minimum its heartbeat sends
1. `028931d5` Let a TWC decide whether its charging point wants power
1. `e9dd2037` Drop provider declarations nothing reads
1. `c90a0e9c` Document the provider changes for users
1. `ff4eba64` Leave the idle TWC minimum out of every budget

## Phase 3 (PR 705): 97 → 19 commits

1. `76e3ac54` Add the desired-state store and VIN-keyed held charge limits
1. `cb3baa29` Run vehicle commands as classified provider outcomes on BLE and cloud workers
1. `b35bc3fa` Declare provider capabilities, costs and suppressions as tables
1. `9116d978` Add the reconciler: charge-limit rules, adoption and one paid fallback
1. `06563493` Set charge limits through desired state and delete the legacy limit path
1. `5ed7f9bc` Start and stop charging as desired state and delete the legacy path
1. `599b1e69` Set charge amps through desired state and delete the legacy rate path
1. `f2b3cc03` Carry main's remaining command behaviours onto the reconciler
1. `782b910d` Send one classified TeslaBLE command with one quick retry
1. `a34dba05` Read vehicle fields through the providers
1. `6466b704` Send every TeslaAPI request through one helper and status classifier
1. `08948cf0` Locate cars from their latest free position for presence
1. `e05696ab` Remove code the new command path orphaned or that was already dead
1. `7c0f7576` Document the reconciler, paid fallback and presence
1. `d94d7f86` Pin old-vs-new command behaviour per install type and fix what it found
1. `c970a915` Remove dead and test-only helpers
1. `bbca17a3` Log the Home Assistant host and exception types, not URLs or text
1. `c101a5cc` Check again after a cloud wake the car did not answer
1. `4998127b` Keep held limits in chargeLimits, keyed by VIN; never set an unknown limit

## Phase 3.5 (PR 706): 22 → 9 commits

1. `d254b3ff` Pin the held-limit migration's edge cases
1. `f3103e6c` Answer sync state from the registry vehicle
1. `3a224467` Make Forget atomic with a listing
1. `1359c2be` Dissolve CarApiVehicle into TeslaAPI and an attached record
1. `40cf2d1d` Let the Owner API command cars listed with command_signing off
1. `8f151742` Log vehicle wake decisions at INFO
1. `036d12e5` Raise TeslaBLE's default command timeout to 15 s
1. `b0295eb9` Make the Vehicles page readable and drop Vehicle.tier
1. `b55af397` Record Tesla API observations under the slot that made them

## Phase 4 (PR 710): 28 → 15 commits

1. `fba85315` Send every RS-485 message from the serial loop
1. `6a723178` Refresh Tesla tokens off the serial loop, one refresh per slot at a time
1. `51303c71` Run the one distributor on a 1 s control tick for every install
1. `58fec4e3` Compute TWC offers on the control tick; charging points own car amps
1. `1a1d71ad` Plan a car's charge rate before its start command
1. `a934f758` Decide TWC start and stop on the control tick
1. `d98d9a9d` Collapse the EVSE scaffolding the second allocator needed; guard the retired names
1. `fc7e62f8` Keep one copy of the settings defaults
1. `5d601888` Make comments say why, not where they came from
1. `25217737` Run the serial loop and shutdown only when an interface is loaded
1. `b3c59046` Withdraw offers when the control pass keeps failing
1. `6ece1306` Drop the empty Advanced Settings section from the debug page
1. `81b9363c` Stop the solar export example recommending flex charging
1. `0cc1e261` Hold the offers during the chargeStopMode 2 silence
1. `3aa44301` Keep running when the Gen2 RS-485 adapter is absent

## Phase 5 (PR —): — → 20 commits

1. `adf1a27d` Read config defaults as one-liners
1. `30a20259` Log reconciler outcomes, paid requests and telemetry changes at INFO
1. `e16abc60` Compute presence from events; one home check
1. `b5733201` Decide each message by one applicability rule; hold within the paid budget
1. `c0796e68` Release the car's own limit when the policy has none
1. `d7ce0ae5` Trim the vehicle model
1. `7b4ee90e` Apply a charging point's own commands; plugged follows plug events
1. `43c2bb91` Attribute a VIN-less plug
1. `8b4927fc` Show presence and pending commands on the Vehicles pages
1. `e4372b86` Import vehicle-model modules by name; trim
1. `81755fbc` Leave a sleeping car alone until it shows life or must wake
1. `d834a310` Run BLE scans and attribution reads on the BLE worker
1. `ef5121fa` Only live evidence is a sign of life; a BLE range scan is a sighting
1. `c5004320` Wake a car only when it is expected to charge
1. `e727de3d` A returning car tries BLE first; restore at the drive start; hold a driving car quietly
1. `a17a9233` Check the car on a Gen2 status change; drop the timed departure reads
1. `d17d7ba9` Document leaving a sleeping car alone and how home is learned
1. `d59518ac` Map Fleet Telemetry's charger fields; document what presence needs
1. `84ef9b37` Suggest minimum_delta for numeric Fleet Telemetry fields; read typed values
1. `52a2652c` Warn when a car's Fleet Telemetry config lacks needed fields

