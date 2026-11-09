Title: Show a Fleet-only car's charging in the charge history

A car that only the Fleet API can see is never watched while it charges. No TWC or Gen3 Wall Connector reports its current, and BLE, Fleet Telemetry and TeslaMate don't cover it. Its charging never appeared in the charge history, and nothing told the policy engine it was drawing power. Reading it often enough to follow a charge live costs money on the paid `vehicle_data` endpoint.

This branch fills in that charging a few minutes late, at no extra API cost, from the free cached snapshot (`vehicle_data_cached`) and the readings TWCManager already pays for.

- **Charge ledger** (`Vehicle/ChargeLedger.py`): for each such car, keeps charging segments built from the snapshots' `charge_energy_added` and charging state, for two days. A session first seen late is dated back at the car's maximum rate, to the latest start its energy allows. A charge resumed on the same plug-in counts only the energy it adds. The ledger's sessions join the charge history.
- **When to poll the snapshot** (`Vehicle/Watch.py`):
  - A suspicion opens on a load step, a wake, a sent command, or a believed charge the meter doesn't bear out. The watch then polls the free snapshot every minute, for up to ten.
  - Paid reads stay out of detection, apart from the cadence reads the watch already makes.
  - A car believed charging whose snapshots have gone quiet is also read on the cloud charging cadence. That covers Tesla's cache holding one snapshot for hours.
- **Load steps on the meter:** the step now samples the meter itself. A step the believed charger load moved through, the same way and within 120 s, is the belief catching up, and nothing acts on it. Before, a Fleet-only car's belief trailed the meter, so each stop made a false rise and each start a false fall.
- **Commanded rate:** a start or new rate the car accepted counts at that rate until a reading shows otherwise.
- **An away car coming home:** a car only the cloud reads is placed by its last fix, so after a drive it looks away until its next location read. Once it could be back, a load rise brings that read forward, once per `sleepCourtesySecs` window.
- **Too small to be a car:**
  - A rise under half the lowest rate cars start charging at here asks no car. A fall under half a charging car's draw doesn't ask that car.
  - The start rate is learned from each car's first reading while charging at home, plus the amps a command leaves it holding. It's pooled across cars, because the EVSE usually sets the cap.
  - Readings while unplugged, plugged in away, or plugged in but idle don't count. Idle readings reflect a Gen2 TWC's brief 6 A offer as the car goes idle.
  - Without this filter, a 2.5 kW house load spent the away car's one early read, and a real plug-in 14 minutes later waited about 10 minutes for the cadence read.

Docs: a new FAQ entry in `docs/modules/Vehicle_TeslaAPI.md`, "Why is my car's charging in the history a few minutes late?". The consumption-step section of `docs/Settings.md` now covers the away-car read and the size cutoff.

Evidence:
- Full unit suite (`pytest tests --ignore=tests/API --ignore=tests/integration --ignore=tests/scenarios`): 2769 passed, rebased on main f094c7c8.
- Ran on a live install (one car, one Gen2 TWC) in Fleet-only mode from 2026-10-30 to 2026-11-08. For the test, BLE and TeslaMate were off, and a second TWCManager instance held the TWC at 48 A, so the car looked like one on a third-party EVSE.
  - Commanded overnight starts, natural stops and uncommanded plug-ins were each dated within one meter sample (30 s).
  - A return on 2026-11-08 was read 58 s after plug-in, and Charge History recorded its 1.5-minute charge.
  - Replaying the meter log for the 20 hours since the size cutoff went in: unfiltered load rises would have kept the snapshot poll running 34% of the car's home, awake, not-charging time; with the cutoff, 0%.
  - On the box itself, no snapshot reads came from house load. The reads that did fall in that time followed charge stops and restart wakes.
- Pending before this opens: a day with the full stack back on (BLE, TeslaMate, TWC on the main instance), checking that a covered car gets no polls, no paid reads and no ledger entries.
- Not exercised on hardware: more than one car, or more than one EVSE. Unit tests only.

Changelog: "Show a Fleet-only car's charging in the charge history a few minutes late, at no API cost" (already in CHANGELOG.md under the unreleased section).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
