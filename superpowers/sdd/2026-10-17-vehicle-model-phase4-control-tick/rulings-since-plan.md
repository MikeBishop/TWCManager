# Requirement changes for Task 3 made after the brief was written (user/controller rulings)
1. (supersedes pre-flight F2) The control pass distributes whenever at least one charging endpoint with a working provider exists: a Gen2 slave, a Gen3 unit, or a VehicleEndpoint (BLE, Owner/Fleet API, HA). The countSlaveTWC() > 0 gate is removed. Gen3-only installs are controlled (tag (g)); vehicle-only installs are controlled (tag (h)), with paid spend bounded by the reconciler's existing rules and a parity row stating the paid counts.
2. Parity row 26's BLE order (charging-start before set-amps 32, 0 HTTP) is accepted under (d), marked INTENTIONALLY CHANGED; the reconciler's aspect order is not changed.
3. (h) is partial: a car known only to BLE/HA gets no VehicleEndpoint until Phase 5's presence port.
4. The control tick stays at 1 s.

# Carried into Task 4 and later
5. (user) When a rate and a start are due for the same car, the rate goes first (minimises overshoot when tracking solar). Row 26's BASE order (set-amps 32 before charging-start) is the desired order.
6. Task 3's rulings 1 and 3 stand; on a Gen2 install (RS-485 interface loaded) with no slave linked, home cars are blind.
