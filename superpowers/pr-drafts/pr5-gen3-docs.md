Title: Gen3 Wall Connector docs for the vehicle model

This PR updates the Gen3 documentation to match how Phase 2 of the 1.4.0 vehicle-model rework drives Gen3 Wall Connectors. Docs only: `docs/Gen3_Status.md` and `docs/modules/Controller_Gen3TWCs.md`. Base `vehicle-model/phase2`.

## Where this sits

Phase 2 changed how Gen3 units are budgeted and how the car on one is named and commanded; these docs describe that. They are independent of Phases 3 and 3.5 and merge cleanly with both, so this can be reviewed and merged any time after Phase 2.

## Changes

- **Multiple units:** each Wall Connector is now its own target, as a Gen2 TWC is. Units on one bus still read the same emulated Neurio house load, so TWCManager picks the one house load at which the units with a target together draw the sum of their targets. A car drawing less than its headroom frees that share for the others; units with different fuse ratings can draw differently from their own targets. Replaces the old "share the total equally" description.
- **Which car is on a Gen3:** the vitals API cannot name the car. A connect starts an anonymous session, and TWCManager names the car by a free read of the energy site's `live_status`, which lists each Wall Connector by DIN with the connected car's VIN. This needs the unit registered in the Tesla app and a token that can read energy data (a Fleet API token with `energy_device_data`, added to the requirements table). A unit's optional `din` key fixes a wrong DIN guess.
- **How a car on a Gen3 is commanded:** charge rate only through the unit's target and the shared headroom (no charge-rate command to the car, and Charge Rate Control modes 2 and 3 add none); charge limit and wake through the vehicle providers in order, BLE first, then the cloud, under the Vehicle Command Policy and `providerSuppressions`; reads come from the unit's vitals, and the energy-site lookup never wakes the car.
- **No individual stop on a shared bus:** replaces "single Neurio instance". While more than one unit has a car connected, the Gen3 reports `NO_INDIVIDUAL_STOP`: a unit with a zero target can still draw up to the shared headroom, and a stop for that car goes to the car's own providers, never through the unit. Without a paired BLE key or a Fleet token that can command the car, nothing else can stop it. With one occupied unit, zero headroom stops it.
- **Unit-tested only:** both docs now list exactly what is unverified on hardware.

## Gen3 hardware check

@ngardiner, you added Gen3 support on `main` (6028077a). The vehicle model changes it and is unit-tested only; I have no Gen3 hardware. If you have a unit, or know someone who does, could these be checked before merge?

- Each unit is its own target, with the headroom shared on one bus.
- Whether `live_status` reports the car's VIN, and the DIN format.
- The zero-headroom stop.
- Whether the Owner token can read `live_status`.

Thank you. Anything that turns out different on hardware can be corrected here.

## Known limits

- These docs describe tested code that has not run on a Gen3; they say so in both files.
- How soon the energy site stops naming a car that has left is also unknown.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
