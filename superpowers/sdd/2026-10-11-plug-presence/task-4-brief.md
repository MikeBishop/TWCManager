### Task 4: Attribute a VIN-less TWC's plug and unplug

**Files:**
- Create: `lib/TWCManager/PresenceAttribution.py`
- Modify: `lib/TWCManager/VehiclePresence.py`, `lib/TWCManager/TWCSlave.py` (`_checkPlugState`)
- Test: `tests/unit/test_presence_attribution.py` (new), `tests/unit/test_vehicle_presence.py`, `tests/unit/test_twcslave.py`

**Interfaces:**
- Consumes: the Evidence dict from Task 3, and `_presenceKey()`, `reportedAmpsMax`, `reportedAmpsActual`, `plugVIN` and `NON_TESLA` on the slaves.
- Produces, in `PresenceAttribution.py`:
  - `PILOT_MATCH_TOLERANCE = 1` (amps).
  - `Candidate = namedtuple("Candidate", "vin reach inside pluggedIn pilot actual fastChargerType fastChargerPresent")`.
  - `pickPluggedCar(candidates: list[Candidate], offeredAmps: float, actualAmps: float) -> tuple[str | None, str]`, which returns `(vin or None, reason)`. The rules, in order:
    0. A candidate with `pluggedIn is True` and `pilot is None` (an awake read without the field) is neither dropped by rule 2 nor matched by rule 3. It goes on to rule 4.
    1. Drop every candidate whose `pluggedIn is False`.
    2. Drop every candidate whose `pluggedIn is True` and that has `fastChargerPresent is True` or `abs(pilot - offeredAmps) > PILOT_MATCH_TOLERANCE`. That car is on another charger.
    3. `matched` = the candidates with `pluggedIn is True`, `fastChargerType == "ACSingleWireCAN"`, a pilot within tolerance, and, when `actualAmps >= 1` and `actual` is known, `abs(actual - actualAmps) <= PILOT_MATCH_TOLERANCE`. Exactly one → `(vin, "BLE pilot match")`. More than one → `(None, "ambiguous")`.
    4. `pool` = the candidates with `reach` or `inside`. If any of them has `reach`, keep only those. Exactly one → `(vin, "single candidate")`. Otherwise `(None, "ambiguous")` or `(None, "no candidate")`.
- In `VehiclePresence`:
  - `_twcVin: dict[twcKey, vin]`, the attribution of each VIN-less TWC.
  - `_ambiguousLogged: set[twcKey]`, cleared on that TWC's unplug.
  - `vinForTwc(twc) -> str | None`.
  - `observePlug(twc, vinReading=True)` stays a no-op, because the VIN proof follows.
  - A VIN-less plug on a TWC whose `_twcVin` already names a HOME car is a no-op. This stops the debounced report and the carried power-start report from triggering two probe sweeps for one plug-in. A car leaving HOME has every `_twcVin` entry that points to it removed.
  - A VIN-less plug runs `_probe(v)` (rate limit bypassed) for every known VIN that isn't in `twcVins()` and isn't attributed to another TWC. It reads `offered`/`actual` from the slave whose `_presenceKey() == twc`. A winner becomes HOME (with `onArrival` from DEPARTING or NOT_HOME) and goes into `_twcVin[twc]`. With no winner, it logs one INFO per plug session: `"TWC %s plugged in; can't tell which car (%s); no car is home from it"`.
  - `unplug(twc, None, excluded)`: the target is `_twcVin.pop(twc)` if that's set. Otherwise the candidates are the HOME or PRESUMED cars that aren't excluded, aren't attributed to another TWC and aren't plugged in according to live telemetry. One candidate departs (`onDeparting(vin, True)`). With several, each one that BLE applies to is probed, and every car read as `pluggedIn is False` departs (`onDeparting(vin, True)`). If none is read that way, it logs INFO and no car departs.
- TWCSlave `_checkPlugState`: `observePlug` fires once when a plugged state (01/03/08) has held `UNPLUG_DEBOUNCE` after a 00 run that itself lasted at least `UNPLUG_DEBOUNCE`, whether or not that 00 was reported as an unplug (for example, an empty TWC since link-up). Track that with a new `_zeroHeld` flag, set when the 00 reaches the debounce and cleared once the plug is reported. The carried power-start plug evidence (`PLUG_EVIDENCE_WINDOW`) is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# test_presence_attribution.py (offered 47, actual 0 unless stated)
def test_single_candidate_inside_radius_wins():
def test_ble_pilot_match_picks_one_of_two():          # A pilot 47 ACSingleWireCAN, B reach only -> A, "BLE pilot match"
def test_two_pilot_matches_are_ambiguous():
def test_pilot_mismatch_means_another_charger():      # sole candidate pilot 32 -> (None, ...)
def test_fast_charger_is_never_the_twc():
def test_ble_reachable_beats_ble_silent_inside_radius():  # A reach, B inside only -> A
def test_read_unplugged_is_never_a_candidate():
def test_actual_current_must_match_while_drawing():   # actualAmps 30: candidate actual 12 -> not matched
def test_plugged_read_without_pilot_falls_through_to_reach():
# test_vehicle_presence.py
def test_vin_less_plug_with_one_candidate_comes_home_with_one_apply():
def test_vin_less_plug_two_candidates_attributed_by_pilot():
def test_ambiguous_plug_makes_nobody_home_and_logs_once(caplog):  # two plugs in one session -> one INFO
def test_two_sleeping_candidates_are_ambiguous_and_never_woken():  # probe reach True awake False for both; get_charge_state/wakeVehicle not called
def test_vin_less_unplug_departs_the_attributed_car():
def test_vin_less_unplug_with_two_presumed_cars_departs_the_one_read_unplugged():
def test_vin_reading_plug_is_left_to_the_proof():
def test_second_plug_report_for_an_attributed_twc_probes_nothing():
def test_leaving_home_clears_the_twc_attribution():
# test_twcslave.py: TestPlugDebounce
def test_plug_into_an_empty_twc_is_reported_after_the_debounce():   # 00 since link for 120 s, then 03 for 60 s -> observePlug once
```

Change `test_no_plug_report_without_a_reported_unplug` so that it covers only a 00 shorter than the debounce.

- [ ] **Step 2: Run the tests and confirm they fail**

- [ ] **Step 3: Implement `pickPluggedCar`, the tracker's VIN-less plug and unplug paths, and `_zeroHeld` in TWCSlave**

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `<PY> -m pytest tests/unit/test_presence_attribution.py tests/unit/test_vehicle_presence.py tests/unit/test_twcslave.py -q`.

- [ ] **Step 5: Commit**

Subject: `Attribute a VIN-less TWC's plug: single candidate or BLE pilot match`.

---

