# Task 4 report: attribute a VIN-less TWC's plug and unplug

Status: DONE. Commit a0fbb5d on presence/3-plug-presence (wt-plug), on top of b7ab12d. Nothing pushed.

## Implemented
- `lib/TWCManager/PresenceAttribution.py` (new): `PILOT_MATCH_TOLERANCE = 1`, `Candidate` namedtuple, `pickPluggedCar(candidates, offeredAmps, actualAmps)` with rules 0-4 as in the brief. Extension: `offeredAmps=None` (TWC unreadable) skips the pilot drop/match so only rule 4 decides.
- `VehiclePresence`:
  - `_twcVin`, `_ambiguousLogged`, `vinForTwc(twc)`; new injectable `twcAmps: twc -> (offered, actual)` (default scans `master.getSlaveTWCs()` for `_presenceKey() == twc`, returns `(reportedAmpsMax, reportedAmpsActual)`, `(None, None)` on miss/error).
  - runPass: VIN-less "plug" and "unplug" observations are handled in order, outside the lock (like "proof"), by `_vinLessPlug` / `_vinLessUnplug`; the lock is taken only to decide. `ctx["known"]` is listed once per pass when such an observation is present.
  - `_vinLessPlug`: no-op if `_twcVin[twc]` names a HOME car. Otherwise full `_probe(v)` for every known VIN not in `twcVins()` and not attributed to another TWC; rate limit bypassed but `_lastProbe[v]` is updated; each result also goes through `_applyEvidence` (lands next pass, as for normal probes). Winner: `PlugRecord(True, "twc", at)`, removed from any other TWC's entry, `_twcVin[twc] = winner`, `_goHome` (onArrival from NOT_HOME, none from PRESUMED). No winner: one INFO per plug session, exact brief text.
  - `_vinLessUnplug`: discards `_ambiguousLogged[twc]`; target = `_twcVin.pop(twc)`; target goes through the named-VIN `_applyUnplug` (so the live-telemetry-plugged override applies). Else candidates = HOME/PRESUMED known cars, not excluded, not attributed elsewhere, not telemetry-plugged; one departs via `_leave`; several: each with `bleApplies` is probed `bleOnly=True` and every `pluggedIn is False` departs via `_applyUnplugged(vin, "ble", ...)`; none read that way: INFO, nobody departs.
  - `_setHome(vin, False)` removes every `_twcVin` entry for that car (single choke point for "leaving HOME").
  - VIN-reading `observePlug` stays a no-op (debug log).
- `TWCSlave._checkPlugState`: `_zeroHeld` set when a 00 reaches `UNPLUG_DEBOUNCE` (before the reported/qualified branching), the plugged branch runs on `_unplugReported or _zeroHeld`, both cleared when `observePlug` fires. The 00 run is now timed whenever `_unpluggedSince is None` (dropped the `previousState != 0x00` part): otherwise a TWC empty since link-up never times its 00 because the first heartbeat's previousState is the class default 00. Safe: that first-heartbeat 00 is never qualified as an unplug (`_runSince is None`). Power-start plug evidence unchanged.

## Offered-amps attribute: `reportedAmpsMax`
`reportedAmpsMax` is parsed from the slave's heartbeat: it is what the slave advertises on the pilot, which the car's `chargerPilotCurrent` (BLE `availableCurrent` -> evidence `pilot`) reflects (47 = 47 live). `lastAmpsOffered` is the master's desired value; `_amps_heartbeat` (TWCSlave.py ~1288) explicitly handles the two differing, so it is not what the car sees.

## Tests
- `tests/unit/test_presence_attribution.py` (new): the 9 brief tests + `test_tolerance_is_one_amp`.
- `tests/unit/test_vehicle_presence.py`: new `TestVinLessAttribution` with the 9 brief tests; `make()` gains `twcAmps` (default `(47, 0)`). `test_unplug_and_plug_without_a_vin_are_no_ops` renamed to `test_vin_less_unplug_and_plug_without_evidence_change_nothing` (it now exercises the VIN-less paths: two non-BLE candidates, no sources; still no transition).
- `tests/unit/test_twcslave.py` TestPlugDebounce: `test_plug_into_an_empty_twc_is_reported_after_the_debounce`; `test_no_plug_report_without_a_reported_unplug` now covers only a 00 shorter than the debounce.
- `test_two_sleeping_candidates_are_ambiguous_and_never_woken` uses the real `bleSource(master)`; asserts `get_charge_state` and `wakeVehicle` never called.
- Full suite: 994 passed (974 before).

## TDD RED/GREEN
- Attribution: RED on ImportError (module missing) -> GREEN 10/10.
- Presence: RED 9/9 new tests against HEAD's tracker with only the `twcAmps` kwarg stubbed in -> GREEN.
- Slave: RED 1/81 (empty-TWC plug) -> GREEN 81/81.

## Files
- /tmp/.../scratchpad/wt-plug/lib/TWCManager/PresenceAttribution.py (new)
- .../wt-plug/lib/TWCManager/VehiclePresence.py
- .../wt-plug/lib/TWCManager/TWCSlave.py
- .../wt-plug/tests/unit/test_presence_attribution.py (new)
- .../wt-plug/tests/unit/test_vehicle_presence.py
- .../wt-plug/tests/unit/test_twcslave.py
Black: the four other files `--check` clean; test_twcslave.py was not black-clean before and was not reformatted (new hunks hand-written in black style).

## Self-review / decisions beyond the brief
1. The winner gets a strong `PlugRecord(True, "twc", at)` even for a rule-4 "single candidate" (a guess). Effect: weak telemetry "unplugged" is ignored for STRONG_EVIDENCE_HOLD (300 s) for that car; a BLE read-unplugged still corrects it. Without it a sleeping rule-4 winner has no plug record and a stale weak unplug would depart it at once. Asymmetry: the single-candidate *unplug* departs with no plug record.
2. Target pop happens before the telemetry override (brief wording "the target is _twcVin.pop(twc)"): if telemetry says plugged, the unplug is ignored and the car stays HOME but unattributed; the next plug report re-sweeps.
3. Added guard: an attributed target that is in `excluded` (another TWC names it now) does not depart.
4. Unplug probes are `bleOnly=True` and do not touch `_lastProbe`; plug-sweep probes are full and set `_lastProbe`.
5. `_twcVin` values are not added to `twcVins()` (the "a TWC names the car" set); they are excluded from candidates separately.

## Concerns (carry forward)
- Power-start `observePlug(twc)` in `_checkPresenceTriggers` passes no `vinReading` and is gated on `not hasReportedVIN`. After a restart a VIN-reading TWC has `hasReportedVIN=False` until its first VIN answer, so its first plug-in may be swept as VIN-less and attribute a car before the proof arrives; `observeProof` carries no TWC key, so a wrong `_twcVin[twc]` is not corrected by the proof (only by that car leaving or the TWC's unplug). Low probability (the plugged car is awake and pilot-matches if BLE applies). Relevant to Task 8's `_chargeVIN` fallback (plugVIN comes before vinForTwc there, so mostly harmless).
- The plug sweep probes every known unnamed VIN on each unattributed plug report (debounced + power-start = up to two sweeps if ambiguous). All probes are sleep-safe; API probes only query online cars.
- No dedicated test for `_defaultTwcAmps` (slave scan / raising master); covered only by injection in tests.
