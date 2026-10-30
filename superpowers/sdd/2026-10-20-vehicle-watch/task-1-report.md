# Task 1 report: charge-port door and keyless ping

Status: DONE. Commit `4e23c85c` on `vehicle-model/phase6` (wt-vm6), base 52a2652c.

## What changed

- `Registry/Fields.py`: new field `chargePortOpen` (VCSEC door, reported only while awake).
- `TeslaBLE.py`
  - `_tool`: `body-controller-state` runs with no `-key-file`, no `sendPrivateKey`, and no `settings["Vehicles"]` record needed. It does require a well-formed VIN (`isWellFormedVIN`), so an anonymous or garbage key never reaches tesla-control. Every other subcommand still checks the record and sends the key.
  - `_noteSleep`: parses `closureStatuses.chargePort`. OPEN gives True, CLOSED gives False, anything else records nothing. The sleep observation is unchanged.
  - `_runPing(vin, scan)` / `ping(vin, scan=True) -> Optional[bool]`: with `scan=False`, an unanswered run returns None and observes nothing.
- `Presence.py`
  - `_PLUG_FIELDS = ("pluggedIn", "chargingState", "chargePortOpen")` is used by `noteObservation`, `pluggedNow` and `unpluggedAt`.
  - `_plug("chargePortOpen", obs)`: False for a closed door, None otherwise.
  - New helpers: `_ble(master)` returns the TeslaBLE module or None. `_doorClosed(v, since)` checks for a TeslaBLE door reading that is False and at or after `since`.
  - `checkPlug`: the claim gate is gone, so any car is pinged whenever the BLE module exists. After an answered ping, asleep returns True, a closed door returns False, and anything else falls through to the read.
  - `pick.fits`: the pre-read ping now runs for any car. A closed door since the plug excludes the car before any read. The charge read still requires the `TeslaBLE` claim.

## Deviations

1. **The rule for marking an unplug from the door.** The brief said to add the door to the plug branch "by the same rule". Under that rule (`was = _plug(previous)`) the first door reading has no previous value, so nothing is marked, and `test_a_closed_charge_port_while_awake_marks_an_unplug` would fail. For the door, `was` is instead taken from the plug marks (`plugIn > unplug`), the same way a retained telemetry copy already works. The effect: a closed door marks an unplug only when the last plug event was a plug-in, and repeat closed readings don't mark it again.
2. **What `ping(scan=True)` returns.** The brief says behaviour with `scan=True` is "as today", and the existing test `test_an_unanswered_ping_is_absence_only_when_the_range_scan_misses` expects `False` when no scan is possible. So with `scan=True` the return is still a plain bool (`answer is True`). Only `scan=False` returns None. The `bleReach` observation is unchanged in both cases.
3. **Test plumbing**
   - `test_check_plug_answers_from_an_awake_closed_door_without_a_read` uses `home(ble())` and swaps in a `SimpleNamespace(ping=...)` module, because `home()` has no TeslaBLE provider.
   - `test_ping_runs_for_a_vin_with_no_key...` clears `master.settings["Vehicles"]`, because `make()` seeds VIN with a privKey.
   - Two `_runPing` fakes in `test_command_path_parity.py` now accept `scan=True`.
   - `test_registry_fields.test_constants` field count goes from 24 to 25.
   - Running black on `test_teslable_pairing_status.py` also rewrapped one existing list comprehension (around line 1114).

## Tests

- Added the 6 tests from the brief (3 in `test_presence.py`, 3 in `test_teslable_pairing_status.py`). They failed before the change as expected and pass now.
- Full suite: **2247 passed, 1 xfailed**, 1 warning (base was 2241 passed + 1 xfailed). The warning does not come from the touched test files.

## Lib lines

26413 before, 26455 after (+42). Most of the growth is in `_tool`'s keyless branch, the door parse, and the `_ble` and `_doorClosed` helpers. Black also wraps `unpluggedAt`'s comprehension onto three lines.

## Self-review / concerns

- `pick` now pings unclaimed candidate cars when `read=True` and their sleep state is unknown. That uses the default `scan=True`, so an unanswered ping can trigger an 8 s bluetoothctl scan for each such car. This is sleep-safe and runs on the BLE worker, but attribution can take longer when there are several unclaimed candidates. Later tasks may want `scan=False` here.
- `checkPlug` likewise pings unclaimed cars with `scan=True`; an unanswered ping marks `absent` after a scan miss, as for claimed cars.
- A closed-door reading older than `since` is ignored in `checkPlug` and `pick`, because the plug at `since` would have opened the door.

## Fix round 1 (amended; now `9fa1160b`)

- **Finding 1:** `checkPlug` and `pick.fits` now call `ping(v.vin, scan="TeslaBLE" in v.claims)`. A car with no key gets the door and sleep state from one tesla-control run, with no range scan and no new `absent` mark. Test added: `test_only_a_keyed_cars_unanswered_ping_falls_back_to_a_range_scan` (test_presence.py). It runs `checkPlug` and `pick` for an unclaimed car whose ping goes unanswered and checks that both pass `scan=False`. Once the car is claimed, both pass `scan=True`.
- **Finding 2:** `_doorClosed` now needs `since > NEVER` (`door.at >= since > NEVER`), so with no plug time an old closed reading excludes nothing.
- **Finding 3:** the `checkPlug` comment now covers the closed-door branch, and notes that a car with no key gets no range scan.
- **Finding 4:** the `ping` docstring now reads: True answered; False a range scan ran and missed the car; None (False with scan) no answer, no scan.
- **Finding 5:** renamed `_PLUG_FIELDS` to `_PLUGS` (with a one-line comment), so `unpluggedAt`'s comprehension fits on one line again.
- **Finding 6:** not applied. It would not save lines, because `ping` still has to turn None into False when `scan=True`.
- **Test plumbing:** the scripted `ping` fakes in `tests/unit/reconcile_helpers.py` (`bleAnswers`, and the module at :78) now accept `scan=True`. Without that, the swallowed TypeError broke `test_an_attributed_gen2_plug_ends_with_the_point_s_00_even_idle`.
- **Lib lines:** 26456, which is +43 against 26413 (+1 over round 0, from the `_PLUGS` comment and the longer `checkPlug` comment).
- **Full suite:** 2248 passed, 1 xfailed.
