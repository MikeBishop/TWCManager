# Task 10 report: three user-reported issues (2026-10-19)

Branch `vehicle-model/phase5` in `scratchpad/wt-vm5`, parent a298c10f. Not pushed.

| Commit | Issue |
|---|---|
| c02cd836 | 1. Pending commands list a settled desire the car has drifted from |
| 84994a2b | 2. Shorten the held charge limit on the Vehicles list |
| bde1f152 | 3. Attribute a VIN-less plug on a Gen2 that reads VINs (plus a CHANGELOG clause) |

## Issue 1: "Nothing pending" while a desire is held

### What the box shows (read only)

- The box runs a298c10f. The service restarted at 12:51:11.
- 12:51:20: `chargeLimit setChargeLimit for <VIN> via TeslaBLE: satisfied rules: held: asleep`.
- 12:51:43: `Vehicle <car> telemetry being provided by TeslaMateVehicle`.
- After that, no chargeLimit line appears. The reconciler never acts on the limit again.
- The active policy is "Non Scheduled Charging". `nonScheduledLimit` is 50, so the desire is 50. It is not a raise.
- `settings.chargeLimits` is `[100, 50]`, meaning outside 100 and held 50.
- TeslaMate's retained MQTT values at 13:08: `charge_limit_soc 50`, `plugged_in true`, `state offline`.

### Root cause on the box

- The hold ran 23 s before TeslaMate's first readings, while no source knew the car's limit. This is inferred, not observed:
  - an attempt ran at all, so the limit was not known to be 50 at 12:51:20, and registry readings are not persisted across a restart, so `known` was None;
  - `allowWake` was False;
  - the attempt was quiet, the ping answered ASLEEP, and the limit was held.
- TeslaMate then reported 50, which equals the desire. From then on, `plan()` returns at its `R.satisfied` gate, and the page hides the row by the same test.
- So the page agreed with the reconciler. The car was already at 50%, and the log line was the only trace of a hold that no longer applied.
- **Not settledAt, not RELEASE, not a `known` mapping.**
  - A HELD outcome never sets `settledAt`.
  - The store was fresh after the restart.
  - `Targets._apply` clears RELEASE when nothing is held.
- **Pinned as characterization:** `test_pending_shows_a_limit_held_asleep_until_the_car_reports_it`.
  - The row reads "held: asleep via BLE …" while the limit is unknown.
  - Once TeslaMate reports 50, the page shows nothing and `pass_()` plans nothing.

### The real divergence, fixed

- `pendingCommands` hid any record with `settledAt`. The reconciler's own done check is different. `plan()` re-plans a settled desire once `newerReading(vehicle, aspect, settledAt)` is true and the car's value no longer satisfies the desire (after RETRY). In that case the page hid a desire the reconciler was about to send again. That is the drift case: newDesire is not called, so `settledAt` is left over.
- The page now hides a row only when one of these holds:
  - `satisfied(aspect, d.value, known(vehicle, aspect))`, which is plan's satisfied gate;
  - or `settledAt is not None and not newerReading(vehicle, aspect, settledAt)`, which is plan's settled gate without its RETRY timer. The timer only delays the send; it does not finish the desire.
- Held desires are still shown. A hold never sets `settledAt`, so a held, unsatisfied desire is never hidden.
- **Test (red first):** `test_pending_shows_a_settled_desire_the_car_drifted_from`. This is a real reconciler pass. AMPS 16 settles, then TeslaMate reads 32.
  - Before the fix the page showed `[]`, even though `pass_()` sent again after RETRY.
  - Now it lists AMPS until TeslaMate reads 16, and then the page shows nothing and `pass_() == 0`.
- The existing `test_pending_hides_a_desire_the_car_already_has_or_that_settled` passes unchanged: AMPS is settled with no reading since.

## Issue 2: held-limit text

- `heldLimitText` now returns `"50% (100%)"`, the held limit followed by the car's own limit.
- The column header changed from "Charge limit set by TWCManager" to "Charge limit (car's own)".
- Tests: `test_held_limit_reads_the_vin_store_after_adoption` and `test_list_renders_registry_rows` now assert the exact new strings.
  - They were red against the old text, failing on the two strings.
  - Both are INTENTIONALLY CHANGED (user request). No docs mention the old text.

## Issue 3: "Unknown car on TWC 8244"

### Root cause

- `_plugSession` skipped attribution on any TWC whose settings have `supportsVINQuery`. The car was asleep across the restart, so the TWC read no VIN.
- A VIN query starts only when current flows (`observeChargingSessions`, `reportedAmpsActual >= 1`). Nothing else could name the car, and the Vehicles list showed `Unknown car on TWC 8244`.

### Fix

1. **The skip is removed.** Every Gen2 anonymous session queues attribution. The flicker guard stays.
   - A queued job that runs after a VIN read finds the session named, and `attribute` returns None.
   - A VIN read still comes once the car draws current, because VIN queries are keyed on charging, not on the session.
2. **A VIN read overrides a guess.** In `observeTwcVin`'s one-car-per-point loop, a car losing the point whose plug reading from that point's source (`Gen2TWC`, or `Gen3TWC` for a `Gen3TWC-` point) is True now gets `pluggedIn False` from that source. That marks an unplug, as Gen3's cloud-VIN correction did.
   - Gen3's own copy of the correction is deleted, so the rule is shared.
   - `test_gen3_cloud_vin_still_corrects_a_guess` passes unchanged.
   - On Gen2, only attribution writes a `Gen2TWC` True, so a car named only by a real VIN read is never touched.
3. **The forced BLE read never wakes.** `pick.fits` skips the `state charge` read for a car `asleep(v)` says is asleep. A `state charge` read goes to the infotainment domain and may wake the car. That is unverified on the box; it is the assumption behind Task 8's pre-flight, which this mirrors.
   - When the car's sleep state is unknown (`asleep(v, now - REACH_WINDOW) is None`, the same bound Run uses), it runs `TeslaBLE.ping` first. That is `body-controller-state`, which is sleep-safe and observes the sleep state.
   - Only a car not known to be asleep is then read. Run's quiet attempts follow the same rule.
   - Gen3 passes no offer, so it never reads and never pings.

### What `pick` does for the box car

- The test case: one car; TeslaMate `pluggedIn` True from 600 s ago; TeslaMate position inside the radius; TeslaMate `state asleep`; BLE paired; no BLE contact.
- How `pick` handles it:
  - Stage 1 (plugged in within 120 s) does not apply.
  - `fits` returns None: no fresh BLE charge state, and the read is skipped because the car is known asleep.
  - It is not reached over BLE.
  - The **inside** stage picks it.
- **No new stage was needed or added.** Telemetry `pluggedIn` True inside the radius is not used directly. The single car is chosen by its position.
- With nothing known but the name (a TeslaMate-less moment right after a restart), the new pre-read ping answers. Its contact makes the car `_reached`, so it is picked as well.
- No BLE command, wake or charge read, and paid `(0, 0, 0)`.

### Tests (all three red before the lib change)

- `test_a_vin_reading_twc_attributes_a_sleeping_car_without_reading_it`:
  - a real master, TeslaBLE and TeslaAPI, with Fleet tokens;
  - `supportsVINQuery = 1`, the box state above, and the plug at 03 with no VIN;
  - result: named at 8244, `vehicleKey == VIN`, no fetch, no ping, no BLE run, paid (0, 0, 0).
  - Red: `twcVin` None.
- `test_an_unknown_sleep_state_is_checked_before_any_charge_read`:
  - unlocated, so only the name is known;
  - the ping answers asleep;
  - result: `pings == [VIN]`, no fetch, no runs, named, paid (0, 0, 0).
  - Red: no ping.
- `test_the_twcs_vin_read_overrides_an_attribution`:
  - after the attribution, the TWC reads VIN2, confirmed by a second read;
  - result: VIN2 is named and is the `vehicleKey`; the guessed car has no `twcVin`, its `Gen2TWC` `pluggedIn` is False, and it has an unplug mark at that time.
  - Red at the attribution step.

### Parity

- `test_command_path_parity.py` is untouched, with no row edited.
- All rows pass. The Gen2 attribution rows with `chargeRead` now ping once per unknown-sleep car before the read. They do not assert `b.pings`, and their commands and paid counts are unchanged.

## Results

- `tests/unit` + `tests/EMS`: **2131 passed** (baseline 2126, plus 5 new).
- Full suite (`tests --ignore=tests/API --ignore=tests/integration`): **2140 passed, 1 xfailed**.
- `black --check` is clean on the touched files.

## Lib delta

- `.py` lines: 26,249 → **26,253 (+4)**.
- `git diff --shortstat a298c10f -- lib`: 6 files, +21/−17. The 6 files include the template, which is a 1-line swap.

| Issue | Net | Where |
|---|---|---|
| 1 | +4 | the page's settled test |
| 2 | −2 | `heldLimitText` |
| 3 | +2 | ping and skip +4, override +4, Gen3 copy −5, `supportsVINQuery` lookup −1 |

## Docs

CHANGELOG line 58 (attribution) gains: "on a Gen2 that reads VINs, the VIN read replaces the match; the match never BLE-reads a car known asleep". No docs page described the skip or the pending-commands rule.

## Concerns

1. **The log line misleads.** "held: asleep" was the last word on the box, and when the car turned out to be at the desired value already, nothing logged it. A one-line INFO when a held desire becomes satisfied would have avoided the question. I did not add one.
2. **The override marks an unplug on the wrong car.** That car becomes NOT_HOME, unless it has newer home evidence, and its held limit is restored, never by waking. This matches Gen3's behaviour. A car that really is home but unplugged gets its own limit back, not the policy's.
3. **Attribution still runs once per session.** With no BLE, no position and no fresh plug reading when the job runs, the plug stays anonymous until the next session. Nothing re-tries attribution when telemetry arrives later. On the box, the BLE ping covers this.
4. **A right guess on a VIN-reading TWC arrives twice.** Attribution, then the VIN read's `recordVehicleVIN` → `onArrival`. As Task 5 noted, applying the same policy value twice changes nothing.
5. **The attribution ping can mark the car absent.** It runs the range scan when `body-controller-state` fails, and a scan miss marks `absent`. This is the same exposure as Task 8 concern 1.
6. **Unrelated, from the box log.** At 12:51:45 BLE woke the car for `setAmps` (offered 47 A), as existing AMPS rules allow. This is outside this task.
