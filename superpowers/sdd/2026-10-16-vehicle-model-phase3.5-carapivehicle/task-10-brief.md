# Task 10: Bring the Gen3 documentation up to date (docs only)

User, 2026-10-17: the Gen3 TWC documentation in the repo is outdated after the vehicle-model work.

Files: docs/Gen3_Status.md, docs/modules/Controller_Gen3TWCs.md, and the Gen3 parts of docs/README.md and docs/Settings.md.
Ground truth: the code at the vehicle-model/phase3.5 tip (EVSEController/Gen3TWCs.py, EVSEInstance/Gen3TWC.py,
Vehicle/Providers/Gen3TWCProvider.py, Vehicle/Providers/WallConnectorVins.py, ChargingPoint/VehicleEndpoint(s)) and the
CHANGELOG 1.4.0 Gen3 lines. Things known to have changed (verify each in code before writing):
- each Wall Connector is its own target; several units on one bus share the headroom (headroom solver);
- the car on a Gen3 is named by a free read of the energy site's `live_status` (needs the Gen3 registered in the Tesla app and
  a token that can read energy data — a Fleet API token with `energy_device_data`); a unit's optional `din` key fixes a wrong
  DIN guess;
- Gen3 can't stop one car individually on a shared bus (NO_INDIVIDUAL_STOP) — say what that means for the user;
- how a Gen3 car is commanded now (provider order: BLE, then cloud), and which settings apply;
- what is still unverified on hardware (Gen3 is unit-tested only).
Remove statements the code no longer supports; don't invent features. Keep the existing doc structure where it still fits.
No code changes. One commit; message ends with: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>.

## Placement (user, 2026-10-17)
Separate PR, branch `docs/gen3-vehicle-model` created from `vehicle-model/phase2` (31e5d185); PR base = vehicle-model/phase2.
Ground truth = the phase2 code, but every statement must also stay true at the vehicle-model/phase3.5 tip (check both; phase3
changed how commands reach a car). It must merge cleanly with phase3 and phase3.5: before committing, check
`git merge-tree --write-tree <your branch> vehicle-model/phase3.5` reports no conflicts. Avoid editing lines that later phases
also edit (e.g. the Vehicle Command Policy paragraph in docs/Settings.md) — prefer the Gen3-specific files.
