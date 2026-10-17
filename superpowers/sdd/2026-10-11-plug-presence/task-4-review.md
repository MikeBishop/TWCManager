# Task 4 review: attribute a VIN-less TWC's plug and unplug (b7ab12d..a0fbb5d)

### Spec Compliance

- ✅ Spec compliant. Rules 0-4 in `pickPluggedCar` (PresenceAttribution.py:50-92) match the brief; `_twcVin`, `_ambiguousLogged`, `vinForTwc`, no-op VIN-reading plug, no-op re-plug for an attributed HOME car (VehiclePresence.py:556-), the sweep over known VINs not named and not attributed elsewhere, the exact INFO text, the unplug target/candidate/BLE-read cascade (VehiclePresence.py:609-), "leaving home clears attribution" in `_setHome`, and `_zeroHeld` in `_checkPlugState` (TWCSlave.py:205,218) are all present. All brief tests are present, plus `test_tolerance_is_one_amp`.
- ⚠️ Cannot verify from diff: that `reportedAmpsMax` (not `lastAmpsOffered`) is what the car's BLE `chargerPilotCurrent` shows; the implementer's reasoning is plausible (heartbeat-reported pilot) and the brief names it, but confirm on the live box (pilot 47 vs reportedAmpsMax 47 while a master-desired value differs).
- ⚠️ A two-pilot-match "ambiguous" plug makes nobody home *from the plug*, but each candidate's BLE `pluggedIn True` read is fed to `_applyEvidence` (VehiclePresence.py:~579) and makes the car HOME next pass under the existing "a BLE charge read decides on its own" rule. Consistent with the evidence rules; noting it so nobody reads the ambiguous INFO as "both stay not home".

### Extras beyond the brief (judged on merit)

- Strong `PlugRecord(True, "twc", at)` for any winner, including a rule-4 guess (VehiclePresence.py:603): acceptable. Without it a sleeping winner would be departed by the first stale weak unplug. A wrong guess is corrected by a BLE read (strong) but holds off TeslaMate "unplugged" for 300 s; telemetry `pluggedIn False` at sweep time already removes the car from the candidates (rule 1), so the exposure is narrow. Minor at most (see below).
- Attributed target not departed when another TWC names it (`target in excluded`): correct, the car is plugged in elsewhere here.
- Unplug with live telemetry still plugged: car stays HOME but loses attribution. Correct to keep home (carried Gen2 steady-00 rule); losing attribution only costs a re-sweep on the next plug report. Minor.
- `_checkPlugState` timing a 00 run from the first heartbeat: safe. `_unpluggedSince` is only reset on a non-00 heartbeat, so `reportedState == 00 and _unpluggedSince is None` with previousState 00 occurs only on the first heartbeat, where `_runSince is None` makes `_unplugQualified` False, so it is never an unplug (covered by `test_startup_in_state_00_is_not_an_unplug`).
- `offeredAmps=None` skips pilot rules: sensible degradation.

### Implementer's concern: power-start plug before the first VIN answer

Checked TWCSlave.py:270-281 and TWCMaster.py:1464. After a restart `hasReportedVIN` is False, so a VIN-reading TWC's power-start plug is swept as VIN-less. In the common case the plugged car is charging (awake), so the pilot match picks the right car Y; a wrong pick X needs Y unreadable and X the sole reach/inside candidate. The worse part is not the proof: when that TWC later unplugs it reports Y's VIN, so the named path `_applyUnplug` (VehiclePresence.py:778) never pops `_twcVin[twc]`. X then stays attributed (and HOME, with a strong record) until X itself leaves, and is excluded from every other VIN-less sweep meanwhile. The proof path does not need to override `_twcVin` (it has no TWC key and Y's proof is already correct for Y). The cheap, sufficient fix is to `self._twcVin.pop(twc, None)` on every unplug from that TWC, named or not, which limits a wrong guess to one plug session. Optional: have TWCMaster pass the slave key so a proof drops that TWC's attribution. Rated Minor (rare, self-limiting with the fix); carry into Task 8, where `vinForTwc` is a fallback behind `plugVIN`.

### Strengths

- `pickPluggedCar` is a pure function with a focused unit-test file that covers each rule, including the pilot-without-field fall-through and the actual-current guard while drawing (test_presence_attribution.py).
- Probes and lookups run outside the lock, and the lock is taken only to decide. This matches the existing "proof" handling, and all mutation stays on the single pass thread (VehiclePresence.py:556-660).
- `_setHome(vin, False)` is the single choke point for clearing attribution, so every departure path gets it.
- `test_two_sleeping_candidates_are_ambiguous_and_never_woken` uses the real `bleSource` and asserts no `get_charge_state` or `wakeVehicle`, which tests the no-wake constraint for real.
- The once-per-session INFO is tested across a second report and a new session.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. VehiclePresence.py:778 / `_applyUnplug`: a named-VIN unplug does not clear `_twcVin[twc]`, so a wrong pre-VIN attribution (restart + power-start) outlives the plug session. Fix: pop `_twcVin[twc]` on any unplug from that TWC.
2. VehiclePresence.py:646: the single-candidate VIN-less unplug departs via `_leave` with no `PlugRecord(False, "twc", at)`, unlike the attributed-target path (via `_applyUnplug`) and the plug path. A stale weak "plugged" for a car still in range can bring it back home at once. Record the unplug record before `_leave`.
3. VehiclePresence.py:603: a rule-4 "single candidate" guess gets the same strong "twc" record as a proof or pilot match. Consider a separate source label (e.g. "twc-guess") if STRONG_EVIDENCE_HOLD should apply only to real evidence. Acceptable as is.
4. VehiclePresence.py:631-638: when live telemetry keeps the target HOME, attribution is dropped (it was popped first). Re-insert it when `_applyUnplug` ignores the unplug, so `vinForTwc` stays right for Task 8.
5. VehiclePresence.py:577 + TWCSlave power-start: an ambiguous plug is swept twice (debounced + power-start), and with Gen2 steady 00 plus `_zeroHeld` every charge start after a 60 s 00 re-sweeps all candidates. All sleep-safe, but it bypasses the rate limit each time. Consider skipping a sweep when `twc in _ambiguousLogged` and the last sweep is younger than PROBE_INTERVAL.
6. Tests: no test for `_defaultTwcAmps` (VehiclePresence.py:212; slave scan, raising master), the `target in excluded` guard, or the telemetry-plugged target. Coverage gap only.

### Assessment

**Task quality:** Approved

**Reasoning:** The brief's rules and tests are implemented faithfully with correct lock discipline and real no-wake testing. The beyond-brief choices are sound. The stale-attribution concern is real but rare, and it is best fixed by clearing `_twcVin[twc]` on every unplug from that TWC, not by changing the proof path.
